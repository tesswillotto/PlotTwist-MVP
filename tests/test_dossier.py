"""Unit tests for dossier.py: the anonymised DALRRD export.

The integration test in test_api_and_sync.py only proves that names stored in the
login table don't appear. These tests feed personal fields straight into the
export function, so they prove the column whitelist itself works.
"""
import csv
import io
import zipfile

from dossier import EXPORT_COLUMNS, anonymise, build_dossier

PERSONAL = {
    "full_name": "Secret Name",
    "contact": "secret@contact.com",
    "email": "secret@contact.com",
    "username": "farmer102",
    "notes": "Spoke to Mr Jacobs about the north field",
    "gps_lat": -33.9321,
    "gps_lng": 18.8602,
}


def record(**extra):
    base = {"record_id": "EP-T101", "entry_date": "2026-10-12", "site_id": "SITE-WINELANDS-01",
            "treatment_group_id": "TGID-1", "observer_id": "OID-102", "nitrate_mg_l": 141.0}
    return dict(base, **extra)


def test_personal_fields_are_dropped():
    frame = anonymise([record(**PERSONAL)])
    assert list(frame.columns) == EXPORT_COLUMNS
    text = frame.to_csv(index=False)
    for value in ("Secret Name", "secret@contact.com", "farmer102", "Mr Jacobs", "-33.9321", "18.8602"):
        assert value not in text


def test_observer_oid_is_kept_for_audit_traceability():
    frame = anonymise([record()])
    assert frame.loc[0, "observer_id"] == "OID-102"


def test_missing_columns_are_filled_not_crashed():
    frame = anonymise([{"record_id": "EP-T101"}])
    assert list(frame.columns) == EXPORT_COLUMNS
    assert frame.loc[0, "record_id"] == "EP-T101"


def test_dossier_zip_has_csv_and_protocol():
    data = build_dossier([record(**PERSONAL), record(record_id="EP-T102")],
                         "Control text", "Variant text", "TGID-1")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert set(z.namelist()) == {"trial_observation_data.csv", "treatment_protocol_description.md"}
    rows = list(csv.DictReader(io.StringIO(z.read("trial_observation_data.csv").decode())))
    assert len(rows) == 2
    assert rows[0]["record_id"] == "EP-T101" and rows[0]["nitrate_mg_l"] == "141.0"
    md = z.read("treatment_protocol_description.md").decode()
    assert "Control text" in md and "Variant text" in md and "TGID-1" in md


def test_missing_protocol_text_shows_placeholder():
    data = build_dossier([record()], None, "", "TGID-1")
    md = zipfile.ZipFile(io.BytesIO(data)).read("treatment_protocol_description.md").decode()
    assert md.count("not yet confirmed") == 2


def test_no_records_gives_header_only_csv():
    data = build_dossier([], "c", "v", "TGID-1")
    text = zipfile.ZipFile(io.BytesIO(data)).read("trial_observation_data.csv").decode()
    assert text.strip().split(",") == EXPORT_COLUMNS
