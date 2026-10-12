"""Integration tests: phone database -> sync worker -> FastAPI -> cloud store -> analytics -> dossier.

The FastAPI TestClient stands in for the network, so the whole offline-to-cloud
path runs without starting a server.
"""
import io
import zipfile

import pytest

import database as db
import sync_worker
from conftest import DALRRD, FARMER


def sync(client, local_db):
    """Run the real sync worker against the test API."""
    return sync_worker.sync_pending_records(local_db, api_url="", post=client.post, get=client.get)


# ------------------------------------------------------------ health / roles --
def test_health(client):
    body = client.get("/health").json()
    assert body["api"] == "ok" and body["cloud"] is True


def test_wrong_role_is_forbidden(client, valid_record):
    assert client.post("/api/v1/trials", json=valid_record, headers=DALRRD).status_code == 403
    assert client.get("/api/v1/trials", headers=FARMER).status_code == 403
    assert client.get("/api/v1/dossier", headers=FARMER, params={
        "site_id": "s", "crop_id": "c", "variant_group_id": "TGID-1"}).status_code == 403


# ---------------------------------------------------------- the offline demo --
def test_offline_record_stays_pending_then_syncs(client, local_db, valid_record):
    db.save_local_record(valid_record, local_db)
    db.set_setting("offline_mode", "1", local_db)

    result = sync(client, local_db)                      # offline: nothing is sent
    assert result["online"] is False
    assert db.count_by_status(local_db)["PENDING"] == 1
    assert client.get("/api/v1/trials", headers=DALRRD).json() == []

    db.set_setting("offline_mode", "0", local_db)        # reconnect
    result = sync(client, local_db)
    assert result["synced"] == 1
    row = db.list_records(local_db)[0]
    assert row["sync_status"] == "SYNCED" and row["cloud_record_id"] == "EP-T101"
    assert len(client.get("/api/v1/trials", headers=DALRRD).json()) == 1


def test_resync_does_not_create_duplicates(client, local_db, valid_record):
    db.save_local_record(valid_record, local_db)
    sync(client, local_db)
    db.save_local_record(valid_record, local_db)         # edit -> PENDING again
    sync(client, local_db)
    rows = client.get("/api/v1/trials", headers=DALRRD).json()
    assert len(rows) == 1 and rows[0]["record_id"] == "EP-T101"


def test_record_ids_are_sequential_in_arrival_order(client, local_db, valid_record):
    for i, uid in enumerate(["a", "b", "c"]):
        rec = dict(valid_record, local_id=uid, created_timestamp=f"2026-10-12 08:0{i}:00")
        db.save_local_record(rec, local_db)
    sync(client, local_db)
    ids = [r["cloud_record_id"] for r in db.list_records(local_db, oldest_first=True)]
    assert ids == ["EP-T101", "EP-T102", "EP-T103"]


def test_cloud_rejection_flags_the_record_with_a_reason(client, local_db, valid_record):
    # TW-0 passes the phone's simple check but fails the API's stricter rule.
    valid_record["trial_week"] = "TW-0"
    db.save_local_record(valid_record, local_db)
    result = sync(client, local_db)
    row = db.list_records(local_db)[0]
    assert result["flagged"] == 1
    assert row["sync_status"] == "FLAGGED_FOR_REVIEW" and "trial_week" in row["rejection_reason"]


def test_api_rejects_out_of_range_directly(client, valid_record):
    valid_record["ph_level"] = 15
    resp = client.post("/api/v1/trials", json=valid_record, headers=FARMER)
    assert resp.status_code == 422 and resp.json()["status"] == "REJECTED"


def test_cloud_down_keeps_records_pending(client, local_db, valid_record, monkeypatch):
    import cloud_store
    db.save_local_record(valid_record, local_db)
    monkeypatch.setattr(cloud_store.get_store(), "ping", lambda: False)  # e.g. Supabase paused
    result = sync(client, local_db)
    assert result["online"] is False and db.count_by_status(local_db)["PENDING"] == 1


# ------------------------------------------------------- setup: Server Wins --
def test_server_wins_on_site_start_date(client, local_db):
    db.upsert_site("SITE-WINELANDS-01", "2026-09-01", local_db)
    sync(client, local_db)                                # first to sync sets the baseline
    db.upsert_site("SITE-WINELANDS-01", "2026-09-15", local_db)   # another phone disagrees
    sync(client, local_db)
    assert db.get_site("SITE-WINELANDS-01", local_db)["start_date"] == "2026-09-01"


# ------------------------------------------------------------------ auth -----
def test_signup_and_login(client):
    r = client.post("/auth/signup", json={"username": "newfarmer", "password": "secret1",
                                          "full_name": "N F", "contact": "x@y.z"})
    assert r.status_code == 200 and r.json()["oid"] == "OID-101"
    assert r.json()["role"] == "Small Farmer"
    assert client.post("/auth/login", json={"username": "newfarmer", "password": "secret1"}).status_code == 200
    assert client.post("/auth/login", json={"username": "newfarmer", "password": "nope"}).status_code == 401
    assert client.post("/auth/signup", json={"username": "newfarmer", "password": "secret1"}).status_code == 409


# -------------------------------------------------- analytics and dossier -----
def seed_nitrate(client, local_db, valid_record, control_n, variant_n):
    n = 0
    for tgid, count in (("TGID-0", control_n), ("TGID-1", variant_n)):
        for i in range(count):
            n += 1
            base = 110 if tgid == "TGID-0" else 140
            rec = dict(valid_record, local_id=f"r{n}", treatment_group_id=tgid,
                       plot_id=db.plot_id_for("SITE-WINELANDS-01", "Tomato", tgid),
                       nitrate_mg_l=base + i, created_timestamp=f"2026-10-12 08:{n:02d}:00")
            db.save_local_record(rec, local_db)
    sync(client, local_db)


CI_PARAMS = {"site_id": "SITE-WINELANDS-01", "crop_id": "Tomato",
             "variant_group_id": "TGID-1", "trial_week": "TW-7"}


def test_ci_endpoint_needs_five_per_group(client, local_db, valid_record):
    seed_nitrate(client, local_db, valid_record, control_n=5, variant_n=4)
    body = client.get("/api/v1/analytics/nitrate-ci", params=CI_PARAMS, headers=DALRRD).json()
    assert body["sufficient"] is False and body["n_variant"] == 4

    db.save_local_record(dict(valid_record, local_id="extra", nitrate_mg_l=145.0,
                              created_timestamp="2026-10-12 09:00:00"), local_db)
    sync(client, local_db)                                # the 5th variant reading
    body = client.get("/api/v1/analytics/nitrate-ci", params=CI_PARAMS, headers=DALRRD).json()
    assert body["sufficient"] is True and body["variant"]["n"] == 5


def test_ci_endpoint_rejects_control_as_variant(client):
    bad = dict(CI_PARAMS, variant_group_id="TGID-0")
    assert client.get("/api/v1/analytics/nitrate-ci", params=bad, headers=DALRRD).status_code == 400


def test_dossier_zip_contents_and_privacy(client, local_db, valid_record):
    import cloud_store
    store = cloud_store.get_store()
    store.set_protocol("TGID-0", "Control protocol text")
    store.set_protocol("TGID-1", "Variant protocol text")
    store.create_user("someone", "Small Farmer", "Secret Name", "secret@contact.com", "s", "h", oid="OID-102")
    seed_nitrate(client, local_db, valid_record, 5, 5)

    resp = client.get("/api/v1/dossier", headers=DALRRD, params={
        "site_id": "SITE-WINELANDS-01", "crop_id": "Tomato", "variant_group_id": "TGID-1"})
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    assert set(z.namelist()) == {"trial_observation_data.csv", "treatment_protocol_description.md"}
    csv = z.read("trial_observation_data.csv").decode()
    md = z.read("treatment_protocol_description.md").decode()
    assert "EP-T101" in csv and "OID-102" in csv
    assert "Secret Name" not in csv and "secret@contact.com" not in csv
    assert "Control protocol text" in md and "Variant protocol text" in md
