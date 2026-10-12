"""Offline-first sync engine (Module 5).

Records are always saved on the phone first as PENDING. When the phone is
online, this worker pushes them (oldest first) to the FastAPI engine, which
validates and writes to Supabase:

    200 SUCCESS  -> SYNCED, cloud Record ID (EP-T###) stored locally
    422 REJECTED -> FLAGGED_FOR_REVIEW with the reason (farmer can fix it)
    anything else (timeout, 5xx, no connection) -> stays PENDING, retried later

`post` and `get` can be swapped for a test client so the whole path can be
tested without a running server.
"""
import threading
import time

import requests

import config
import database as db

HEADERS = {"X-User-Role": config.ROLE_FARMER}


def is_online(db_path: str = None, api_url: str = None, get=requests.get) -> bool:
    """Online = demo offline switch is OFF, the API answers, and the cloud is reachable."""
    if db.is_offline_mode(db_path):
        return False
    try:
        resp = get(f"{api_url if api_url is not None else config.API_URL}/health", timeout=3)
        return resp.status_code == 200 and bool(resp.json().get("cloud"))
    except Exception:
        return False


def sync_setup_data(db_path: str = None, api_url: str = None, post=requests.post,
                    get=requests.get) -> None:
    """Push local site/plot setup, then pull the cloud's version ("Server Wins")."""
    base = api_url if api_url is not None else config.API_URL
    for site in db.list_sites(db_path):
        resp = post(f"{base}/api/v1/sites", json=site, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            db.upsert_site(resp.json()["site_id"], resp.json()["start_date"], db_path)
    for plot in db.list_plots(db_path):
        resp = post(f"{base}/api/v1/plots", json=plot, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            p = resp.json()
            db.upsert_plot(p["plot_id"], p["site_id"], p["crop_id"],
                           p["treatment_group_id"], p["area_m2"], db_path)
    # Pull anything the cloud already has (e.g. set up by another farmer)
    any_role = {"X-User-Role": config.ROLE_FARMER}
    for site in get(f"{base}/api/v1/sites", headers=any_role, timeout=5).json():
        db.upsert_site(site["site_id"], site["start_date"], db_path)
    for p in get(f"{base}/api/v1/plots", headers=any_role, timeout=5).json():
        db.upsert_plot(p["plot_id"], p["site_id"], p["crop_id"],
                       p["treatment_group_id"], p["area_m2"], db_path)


def sync_pending_records(db_path: str = None, api_url: str = None, post=requests.post,
                         get=requests.get) -> dict:
    """Push every PENDING record, oldest first. Returns a summary dict."""
    base = api_url if api_url is not None else config.API_URL
    pending = db.list_records(db_path, status="PENDING", oldest_first=True)
    summary = {"online": True, "synced": 0, "flagged": 0, "pending_left": 0,
               "message": ""}

    if not is_online(db_path, base, get):
        summary.update(online=False, pending_left=len(pending),
                       message=f"Offline mode: {len(pending)} record(s) stored locally. "
                               f"Awaiting internet connection.")
        return summary

    try:
        sync_setup_data(db_path, base, post, get)
    except Exception:
        pass  # setup sync is best effort; records can still be pushed

    for rec in pending:
        payload = {c: rec[c] for c in db.PAYLOAD_COLUMNS}
        payload["is_harvest_complete"] = bool(rec["is_harvest_complete"])
        try:
            resp = post(f"{base}/api/v1/trials", json=payload, headers=HEADERS, timeout=8)
        except Exception:
            break  # connection dropped: leave the rest PENDING and retry later
        if resp.status_code == 200 and resp.json().get("status") == "SUCCESS":
            db.mark_synced(rec["local_id"], resp.json()["cloud_record_id"], db_path)
            summary["synced"] += 1
        elif resp.status_code == 422:
            db.mark_flagged(rec["local_id"], resp.json().get("error", "Rejected by cloud"), db_path)
            summary["flagged"] += 1
        # any other status (e.g. 503): stays PENDING

    summary["pending_left"] = db.count_by_status(db_path)["PENDING"]
    summary["message"] = (f"Cloud sync completed: {summary['synced']} synced, "
                          f"{summary['flagged']} flagged, {summary['pending_left']} pending.")
    return summary


def start_background_sync(db_path: str = None, api_url: str = None, interval: int = 15):
    """Daemon thread: whenever records are PENDING and the phone is online, sync them."""
    def loop():
        while True:
            try:
                if db.count_by_status(db_path)["PENDING"] > 0:
                    sync_pending_records(db_path, api_url)
            except Exception:
                pass
            time.sleep(interval)

    thread = threading.Thread(target=loop, daemon=True, name="agritrial-sync")
    thread.start()
    return thread
