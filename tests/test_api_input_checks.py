"""Tests for the API input checks: site, plot and crop validation, hidden notes, unknown plots."""
from conftest import DALRRD, FARMER

SITE = "SITE-WINELANDS-01"


def make_site(client):
    return client.post("/api/v1/sites", json={"site_id": SITE, "start_date": "2026-09-01"},
                       headers=FARMER)


def test_unknown_site_is_rejected(client):
    resp = client.post("/api/v1/sites", json={"site_id": "NOT-A-SITE", "start_date": "2026-09-01"},
                       headers=FARMER)
    assert resp.status_code == 400


def test_known_site_is_created(client):
    resp = make_site(client)
    assert resp.status_code == 200 and resp.json()["site_id"] == SITE


def test_plot_id_is_built_by_the_server(client):
    make_site(client)
    resp = client.post("/api/v1/plots", json={
        "plot_id": "made-up-by-the-client", "site_id": SITE, "crop_id": "Tomato",
        "treatment_group_id": "TGID-1", "area_m2": 10}, headers=FARMER)
    assert resp.status_code == 200
    assert resp.json()["plot_id"] == f"{SITE}-Tomato-TGID-1"


def test_plot_with_unknown_group_or_crop_is_rejected(client):
    make_site(client)
    base = {"site_id": SITE, "crop_id": "Tomato", "treatment_group_id": "TGID-1", "area_m2": 10}
    for bad in ({"treatment_group_id": "TGID-9"}, {"crop_id": "Unicorn"}):
        resp = client.post("/api/v1/plots", json=dict(base, **bad), headers=FARMER)
        assert resp.status_code == 400


def test_reports_reject_unknown_crop(client):
    params = {"site_id": SITE, "crop_id": "Unicorn", "variant_group_id": "TGID-1",
              "trial_week": "TW-1"}
    assert client.get("/api/v1/analytics/nitrate-ci", params=params, headers=DALRRD).status_code == 400
    assert client.get("/api/v1/dossier", params=params, headers=DALRRD).status_code == 400
    assert client.get("/api/v1/dossier-pdf", params=params, headers=DALRRD).status_code == 400


def test_trials_endpoint_hides_free_text_notes(client, valid_record):
    rec = dict(valid_record, notes="Spoke to Mr Jacobs about the north field")
    assert client.post("/api/v1/trials", json=rec, headers=FARMER).status_code == 200
    rows = client.get("/api/v1/trials", headers=DALRRD).json()
    assert len(rows) == 1 and "notes" not in rows[0]


def test_yield_for_a_plot_that_is_not_set_up_is_not_an_error(client):
    resp = client.get("/api/v1/analytics/plot-yield", headers=DALRRD, params={
        "site_id": SITE, "crop_id": "Tomato", "treatment_group_id": "TGID-3"})
    assert resp.status_code == 200
    assert resp.json()["yield_g_m2"] is None and resp.json()["status"] == "Plot not set up"
