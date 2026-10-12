"""Local (on-phone) SQLite storage: records, setup data, offline logins, settings.

Every function takes an optional db_path so tests can use a temporary database.
"""
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

import config
from security import hash_password, verify_password

SCHEMA_FILE = Path(__file__).resolve().parent / "sql" / "schema_sqlite.sql"

# Every column of trial_measurements, in schema order.
RECORD_COLUMNS = [
    "local_id", "cloud_record_id", "created_timestamp", "entry_date", "site_id",
    "environment_id", "crop_id", "treatment_group_id", "plot_id", "trial_week",
    "visit_type", "observer_id", "plant_height_cm", "leaf_count",
    "fresh_weight_g", "dry_weight_g", "spad_index", "root_length_cm",
    "ph_level", "ec_level", "dissolved_oxygen", "temperature_c", "humidity_pct",
    "nitrate_mg_l", "phosphate_mg_l", "notes",
    "sync_status", "rejection_reason", "is_harvest_complete",
    "last_edited_by", "last_edited_timestamp",
]

# What is sent to the cloud: everything except the phone-only sync fields.
PAYLOAD_COLUMNS = [c for c in RECORD_COLUMNS
                   if c not in ("cloud_record_id", "sync_status", "rejection_reason")]


def connect(db_path: str = None) -> sqlite3.Connection:
    """Open a connection (rows behave like dicts)."""
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_sqlite_db(db_path: str = None) -> None:
    """Create all local tables if they do not exist yet."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- settings --
def get_setting(key: str, default: str = None, db_path: str = None):
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str, db_path: str = None) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def is_offline_mode(db_path: str = None) -> bool:
    """The demo 'Offline mode' switch (forces the app to behave as if offline)."""
    return get_setting("offline_mode", "0", db_path) == "1"


# ------------------------------------------------------------------- users --
def cache_user(oid: str, username: str, role: str, full_name: str, password: str,
               db_path: str = None) -> None:
    """Store a salted hash locally so this user can log in offline later."""
    salt, pw_hash = hash_password(password)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (oid, username, role, full_name, salt, password_hash) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(oid) DO UPDATE SET "
            "username = excluded.username, role = excluded.role, full_name = excluded.full_name, "
            "salt = excluded.salt, password_hash = excluded.password_hash",
            (oid, username, role, full_name, salt, pw_hash))


def verify_local_user(username: str, password: str, db_path: str = None):
    """Offline login. Returns the user dict, or None if unknown / wrong password."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and verify_password(password, row["salt"], row["password_hash"]):
        return {"oid": row["oid"], "username": row["username"],
                "role": row["role"], "full_name": row["full_name"]}
    return None


# ----------------------------------------------------- site / plot setup ----
def plot_id_for(site_id: str, crop_id: str, treatment_group_id: str) -> str:
    """A plot is one site + one crop + one treatment group."""
    return f"{site_id}-{crop_id}-{treatment_group_id}"


def upsert_site(site_id: str, start_date: str, db_path: str = None) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT INTO sites (site_id, start_date) VALUES (?, ?) "
                     "ON CONFLICT(site_id) DO UPDATE SET start_date = excluded.start_date",
                     (site_id, start_date))


def get_site(site_id: str, db_path: str = None):
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sites WHERE site_id = ?", (site_id,)).fetchone()
    return dict(row) if row else None


def list_sites(db_path: str = None) -> list:
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM sites")]


def upsert_plot(plot_id: str, site_id: str, crop_id: str, treatment_group_id: str,
                area_m2: float, db_path: str = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO plots (plot_id, site_id, crop_id, treatment_group_id, area_m2) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(plot_id) DO UPDATE SET area_m2 = excluded.area_m2",
            (plot_id, site_id, crop_id, treatment_group_id, area_m2))


def get_plot(plot_id: str, db_path: str = None):
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM plots WHERE plot_id = ?", (plot_id,)).fetchone()
    return dict(row) if row else None


def list_plots(db_path: str = None) -> list:
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM plots")]


def calculate_trial_week(start_date: str, entry_date: str):
    """Days 0-6 after the start date are TW-1, days 7-13 are TW-2, and so on.

    Returns None if the entry date is before the site start date.
    """
    days = (date.fromisoformat(entry_date) - date.fromisoformat(start_date)).days
    if days < 0:
        return None
    return f"TW-{days // 7 + 1}"


# ----------------------------------------------------------------- records --
def new_local_id() -> str:
    return str(uuid.uuid4())


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_local_record(rec: dict, db_path: str = None) -> dict:
    """Save (or re-save after an edit) a record as PENDING. Works with no internet."""
    rec = dict(rec)
    rec.setdefault("local_id", new_local_id())
    rec.setdefault("created_timestamp", now_timestamp())
    rec["sync_status"] = "PENDING"
    rec["rejection_reason"] = None
    rec["is_harvest_complete"] = 1 if rec.get("is_harvest_complete") else 0
    values = [rec.get(c) for c in RECORD_COLUMNS]
    placeholders = ", ".join("?" for _ in RECORD_COLUMNS)
    with connect(db_path) as conn:
        conn.execute(f"INSERT OR REPLACE INTO trial_measurements "
                     f"({', '.join(RECORD_COLUMNS)}) VALUES ({placeholders})", values)
    return rec


def list_records(db_path: str = None, observer_id: str = None, status: str = None,
                 oldest_first: bool = False) -> list:
    sql, args = "SELECT * FROM trial_measurements WHERE 1=1", []
    if observer_id:
        sql += " AND observer_id = ?"
        args.append(observer_id)
    if status:
        sql += " AND sync_status = ?"
        args.append(status)
    sql += " ORDER BY created_timestamp " + ("ASC" if oldest_first else "DESC")
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def count_by_status(db_path: str = None) -> dict:
    counts = {"PENDING": 0, "SYNCED": 0, "FLAGGED_FOR_REVIEW": 0}
    with connect(db_path) as conn:
        for row in conn.execute("SELECT sync_status, COUNT(*) AS n FROM trial_measurements "
                                "GROUP BY sync_status"):
            counts[row["sync_status"]] = row["n"]
    return counts


def mark_synced(local_id: str, cloud_record_id: str, db_path: str = None) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE trial_measurements SET sync_status = 'SYNCED', "
                     "cloud_record_id = ?, rejection_reason = NULL WHERE local_id = ?",
                     (cloud_record_id, local_id))


def mark_flagged(local_id: str, reason: str, db_path: str = None) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE trial_measurements SET sync_status = 'FLAGGED_FOR_REVIEW', "
                     "rejection_reason = ? WHERE local_id = ?", (reason, local_id))


def count_harvest_missing_fresh(plot_id: str, exclude_local_id: str = None,
                                db_path: str = None) -> int:
    """Stored harvest records for a plot that have no fresh weight (completeness warning)."""
    sql = ("SELECT COUNT(*) AS n FROM trial_measurements WHERE plot_id = ? "
           "AND visit_type = 'HARVEST_VISIT' AND fresh_weight_g IS NULL")
    args = [plot_id]
    if exclude_local_id:
        sql += " AND local_id != ?"
        args.append(exclude_local_id)
    with connect(db_path) as conn:
        return conn.execute(sql, args).fetchone()["n"]
