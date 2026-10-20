"""Reset everything and load the demo data. Run before EVERY video take and before Dragons' Den:

    python seed_demo.py

Creates (in the cloud store AND a fresh local database):
  * site SITE-WINELANDS-01, Tomato plots TGID-0..5 (10 m2 each). The site start date is set to
    35 days before TODAY, so today is always the first day of TW-6. The live demo therefore
    works on the day you run this (and for the 6 days after).
  * protocol text for every treatment group
  * logins:  sam      / sampw        (OID-102, Small Farmer, shown as "Sam")
             dalrrd01 / dalrrd01pw   (OID-900, DALRRD Regulatory Official)
             uwc01    / uwc01pw      (OID-901, UWC Researcher)
  * Nitrate readings for ALL 6 treatment groups in TW-1 to TW-6 (about 200 records), so every
    week and every group gives a proper 95% confidence interval:
      - TGID-1, TGID-2 and TGID-4 are clearly higher than the control (green)
      - TGID-3 and TGID-5 overlap with the control (yellow: no clear difference)
  * TW-6 live demo trick: TGID-1 has only 4 readings (needs 1 more!). As Sam, add ONE TGID-1
    nitrate record while offline, sync, then refresh the dashboard: TGID-1 joins the chart.
  * a completed harvest for every group (yield 420, 510, 470, 440, 540, 425 g/m2)
"""
import os
import random
import sys
from datetime import date, timedelta

import config
import database as db
from cloud_store import get_store
from security import hash_password

SITE, CROP, ENV = "SITE-WINELANDS-01", "Tomato", "Greenhouse"
# The trial week of a new record is calculated from today's date, so the seed data is
# built backwards from today: today is day 35 of the trial = the first day of TW-6.
TODAY = date.today()
SITE_START = TODAY - timedelta(days=35)
PLOT_AREA = 10.0

PROTOCOL_BASE = (
    "- Crop: Tomato, grown in a greenhouse\n"
    f"- Site: SITE-WINELANDS-01, trial start {SITE_START.isoformat()}\n"
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
    ("sam", "sampw", "Small Farmer", "Sam", "OID-102"),
    ("dalrrd01", "dalrrd01pw", "DALRRD Regulatory Official", "Demo DALRRD Official", "OID-900"),
    ("uwc01", "uwc01pw", "UWC Researcher", "Demo UWC Researcher", "OID-901"),
]

# ------------------------------------------------------------ nitrate data --
# Typical nitrate (mg/L) per treatment group. TGID-0 is the control.
GROUP_MEAN = {"TGID-0": 110, "TGID-1": 136, "TGID-2": 124,
              "TGID-3": 114, "TGID-4": 147, "TGID-5": 108}
NITRATE_SD = 4.0

# Hand-picked values kept from the first version, so the numbers in TESTING.md still match
# (TW-5: control mean 108.4, TGID-1 mean 135).
HAND_PICKED = {
    ("TGID-0", "TW-5"): [108, 112, 105, 110, 107],
    ("TGID-1", "TW-5"): [132, 138, 129, 141, 135],
    ("TGID-0", "TW-6"): [111, 115, 109, 118, 113, 116],
    ("TGID-1", "TW-6"): [137, 142, 134, 146],          # only 4: the live demo adds the 5th
}


def build_nitrate() -> dict:
    """(group, week) -> list of nitrate readings, for TW-1..TW-6 and all 6 groups.

    The random numbers are seeded per group and week, so the data is identical every run.
    """
    data = {}
    for week_no in range(1, 7):
        week = f"TW-{week_no}"
        for tgid in config.TREATMENT_GROUPS:
            if (tgid, week) in HAND_PICKED:
                data[(tgid, week)] = HAND_PICKED[(tgid, week)]
                continue
            rng = random.Random(f"{tgid}-{week}")
            mean = GROUP_MEAN[tgid] + 1.5 * (week_no - 3)      # slight rise over the weeks
            count = 5 + (week_no % 2)                          # 5 or 6 readings per group
            data[(tgid, week)] = [round(rng.gauss(mean, NITRATE_SD), 1) for _ in range(count)]
    return data


NITRATE = build_nitrate()

# Fresh weight (g) of three harvest visits per plot; yield = total / 10 m2.
HARVEST = {
    "TGID-0": [1300, 1400, 1500],   # 420 g/m2
    "TGID-1": [1600, 1700, 1800],   # 510
    "TGID-2": [1500, 1600, 1600],   # 470
    "TGID-3": [1400, 1500, 1500],   # 440
    "TGID-4": [1700, 1800, 1900],   # 540
    "TGID-5": [1350, 1400, 1500],   # 425
}
GROWTH_BONUS = {"TGID-0": 0.0, "TGID-1": 4.0, "TGID-2": 2.5,
                "TGID-3": 0.5, "TGID-4": 5.0, "TGID-5": -0.5}
WEEK_START = {f"TW-{n}": SITE_START + timedelta(days=7 * (n - 1)) for n in range(1, 7)}


def make_record(tgid, week, index, nitrate=None, **extra):
    week_no = int(week[3:])
    day = min(WEEK_START[week] + timedelta(days=min(index, 4)), TODAY)  # never in the future
    rec = {
        "local_id": f"seed-{tgid}-{week}-{index}-{extra.get('visit_type', 'R')}",
        "created_timestamp": f"{day.isoformat()} 09:{index:02d}:00",
        "entry_date": day.isoformat(), "site_id": SITE, "environment_id": ENV, "crop_id": CROP,
        "treatment_group_id": tgid, "plot_id": db.plot_id_for(SITE, CROP, tgid),
        "trial_week": week, "visit_type": "ROUTINE_MONITORING", "observer_id": "OID-102",
        # plants grow week by week; biostimulant plots grow a little faster
        "plant_height_cm": round(14 + 6.5 * week_no + GROWTH_BONUS[tgid] + index * 0.4, 1),
        "leaf_count": int(6 + 2 * week_no + GROWTH_BONUS[tgid] // 2 + index % 3),
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
    for tgid, weights in HARVEST.items():
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
    print("Logins: sam/sampw, dalrrd01/dalrrd01pw, uwc01/uwc01pw")


if __name__ == "__main__":
    seed(reset_local="--keep-local" not in sys.argv)
