"""Unit tests for the local SQLite layer."""
import sqlite3

import pytest

import database as db


def test_save_local_record_is_pending(local_db, valid_record):
    db.save_local_record(valid_record, local_db)
    rows = db.list_records(local_db)
    assert len(rows) == 1 and rows[0]["sync_status"] == "PENDING"
    assert db.count_by_status(local_db)["PENDING"] == 1


def test_database_check_constraints_block_bad_data(local_db, valid_record):
    valid_record["plant_height_cm"] = 600
    with pytest.raises(sqlite3.IntegrityError):
        db.save_local_record(valid_record, local_db)


def test_editing_a_flagged_record_resets_it_to_pending(local_db, valid_record):
    db.save_local_record(valid_record, local_db)
    db.mark_flagged(valid_record["local_id"], "bad", local_db)
    assert db.count_by_status(local_db)["FLAGGED_FOR_REVIEW"] == 1
    db.save_local_record(valid_record, local_db)       # farmer fixes and re-saves
    assert db.count_by_status(local_db) == {"PENDING": 1, "SYNCED": 0, "FLAGGED_FOR_REVIEW": 0}


@pytest.mark.parametrize("entry,week", [
    ("2026-09-01", "TW-1"), ("2026-09-07", "TW-1"), ("2026-09-08", "TW-2"),
    ("2026-10-11", "TW-6"), ("2026-10-12", "TW-6"), ("2026-10-13", "TW-7"),
])
def test_trial_week_calculation(entry, week):
    assert db.calculate_trial_week("2026-09-01", entry) == week


def test_entry_before_site_start_has_no_trial_week():
    assert db.calculate_trial_week("2026-09-01", "2026-08-30") is None


def test_offline_login_uses_salted_hash(local_db):
    db.cache_user("OID-102", "farmer102", "Small Farmer", "Demo", "secret123", local_db)
    assert db.verify_local_user("farmer102", "secret123", local_db)["oid"] == "OID-102"
    assert db.verify_local_user("farmer102", "wrong", local_db) is None
    with db.connect(local_db) as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert "secret123" not in stored


def test_offline_switch(local_db):
    assert db.is_offline_mode(local_db) is False
    db.set_setting("offline_mode", "1", local_db)
    assert db.is_offline_mode(local_db) is True


def test_harvest_missing_fresh_weight_count(local_db, valid_record):
    valid_record.update(visit_type="HARVEST_VISIT", fresh_weight_g=None)
    db.save_local_record(valid_record, local_db)
    assert db.count_harvest_missing_fresh(valid_record["plot_id"], db_path=local_db) == 1
    assert db.count_harvest_missing_fresh(valid_record["plot_id"],
                                          exclude_local_id=valid_record["local_id"],
                                          db_path=local_db) == 0
