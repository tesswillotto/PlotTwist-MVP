"""Reset everything and load the demo data. Run before EVERY video take:

    python seed_demo.py

Creates (in the cloud store AND a fresh local database):
  * site SITE-WINELANDS-01 (start 2026-09-01), Tomato plots TGID-0..5 (10 m2 each)
  * protocol text for every treatment group
  * logins:  farmer102 / farmer102pw  (OID-102, Small Farmer)
             dalrrd01  / dalrrd01pw   (OID-900, DALRRD Regulatory Official)
             uwc01     / uwc01pw      (OID-901, UWC Researcher)
  * TW-5: control 5 + TGID-1 5 nitrate readings        -> chart shows straight away
  * TW-6: control 6, TGID-1 only 4 (needs 1 more!), TGID-2 only 3 -> "more records needed"
    Live demo trick: as the farmer, add ONE TGID-1 nitrate record for TW-6 while offline,
    sync, then refresh the dashboard: the chart appears.
  * a completed harvest for TGID-0 and TGID-1 (yield 420 vs 510 g/m2)
"""
import os
import sys
from datetime import date, timedelta

import config
import database as db
from cloud_store import get_store
from security import hash_password

SITE, CROP, ENV = "SITE-WINELANDS-01", "Tomato", "Greenhouse"
SITE_START = date(2026, 9, 1)
PLOT_AREA = 10.0

PROTOCOL_BASE = (
    "- Crop: Tomato, grown in a greenhouse\n"
    "- Site: SITE-WINELANDS-01, trial start 2026-09-01\n"
    "- Plot size: 10 m2 per treatment group\n"
    "- Irrigation: standard fertigation schedule, same for all groups\n"
    "- Monitoring: weekly visits at the same time of day (trial weeks TW-1, TW-2, ...)\n"
    "- Recorded: plant height, leaf count, nitrate (mg/L) and other optional readings; "
    "fresh weight at harvest\n"
)

PROTOCOLS = {
    "TGID-0": "**Control (TGID-0).** Standard fertigation only. No biostimulant applied.\n\n"
              + PROTOCOL_BASE,
    **{f"TGID-{i}": f"**Biostimulant variant {i} (TGID-{i}).** Standard fertigation plus "
                    f"biostimulant variant {i}. Product, application rate, method and "
                    f"frequency: [to be supplied by the Eduponics research team].\n\n"
                    + PROTOCOL_BASE
                    + "- _Variant details to be confirmed by the Eduponics research team._"
       for i in range(1, 6)},
}

USERS = [
    ("farmer102", "farmer102pw", "Small Farmer", "Demo Farmer", "OID-102"),
    ("dalrrd01", "dalrrd01pw", "DALRRD Regulatory Official", "Demo DALRRD Official", "OID-900"),
    ("uwc01", "uwc01pw", "UWC Researcher", "Demo UWC Researcher", "OID-901"),
]

# nitrate readings (mg/L): variant is clearly higher than control
NITRATE = {
    ("TGID-0", "TW-5"): [108, 112, 105, 110, 107],
    ("TGID-1", "TW-5"): [132, 138, 129, 141, 135],
    ("TGID-0", "TW-6"): [111, 115, 109, 118, 113, 116],
    ("TGID-1", "TW-6"): [137, 142, 134, 146],          # only 4: the live demo adds the 5th
    ("TGID-2", "TW-6"): [120, 125, 118],               # only 3: shows the notice
}
WEEK_START = {"TW-5": date(2026, 9, 29), "TW-6": date(2026, 10, 6)}


def make_record(tgid, week, index, nitrate=None, **extra):
    day = WEEK_START[week] + timedelta(days=min(index, 4))
    rec = {
        "local_id": f"seed-{tgid}-{week}-{index}-{extra.get('visit_type', 'R')}",
        "created_timestamp": f"{day.isoformat()} 09:{index:02d}:00",
        "entry_date": day.isoformat(), "site_id": SITE, "environment_id": ENV, "crop_id": CROP,
        "treatment_group_id": tgid, "plot_id": db.plot_id_for(SITE, CROP, tgid),
        "trial_week": week, "visit_type": "ROUTINE_MONITORING", "observer_id": "OID-102",
        "plant_height_cm": 38.0 + index * 1.5 + int(week[-1]), "leaf_count": 14 + index,
        "ph_level": 6.2, "ec_level": 1.8, "temperature_c": 24.5, "humidity_pct": 62.0,
        "nitrate_mg_l": nitrate, "is_harvest_complete": False,
    }
    rec.update(extra)
    return rec


def seed(reset_local: bool = True):
    store = get_store()
    store.reset()

    store.create_site_if_absent(SITE, SITE_START.isoformat())
    for tgid in config.TREATMENT_GROUPS:
        store.create_plot_if_absent({
            "plot_id": db.plot_id_for(SITE, CROP, tgid), "site_id": SITE, "crop_id": CROP,
            "treatment_group_id": tgid, "area_m2": PLOT_AREA})
        store.set_protocol(tgid, PROTOCOLS[tgid])

    for username, password, role, name, oid in USERS:
        salt, pw_hash = hash_password(password)
        store.create_user(username, role, name, "demo@example.com", salt, pw_hash, oid=oid)

    count = 0
    for (tgid, week), values in NITRATE.items():
        for i, value in enumerate(values):
            store.upsert_trial(make_record(tgid, week, i, nitrate=value))
            count += 1
    # Completed harvests (3 visits each; the last one is the confirmed final entry)
    for tgid, weights in (("TGID-0", [1300, 1400, 1500]), ("TGID-1", [1600, 1700, 1800])):
        for i, grams in enumerate(weights):
            store.upsert_trial(make_record(
                tgid, "TW-6", 10 + i, visit_type="HARVEST_VISIT", fresh_weight_g=float(grams),
                dry_weight_g=grams * 0.07, is_harvest_complete=(i == len(weights) - 1)))
            count += 1

    if reset_local:
        for suffix in ("", "-journal"):
            if os.path.exists(config.DB_PATH + suffix):
                os.remove(config.DB_PATH + suffix)
        db.init_sqlite_db()
    print(f"Seeded {count} trial records into the '{store.name}' cloud store.")
    print("Logins: farmer102/farmer102pw, dalrrd01/dalrrd01pw, uwc01/uwc01pw")


if __name__ == "__main__":
    seed(reset_local="--keep-local" not in sys.argv)
