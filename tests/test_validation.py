"""Unit tests for the shared validation rules (Section 6b)."""
import pytest

from validation import MANDATORY_FIELDS, validate_record


def fields(errors):
    return {f for f, _ in errors}


def test_valid_record_passes(valid_record):
    assert validate_record(valid_record) == []


def test_height_600_is_blocked(valid_record):
    """The exact case shown in the demo."""
    valid_record["plant_height_cm"] = 600
    assert "plant_height_cm" in fields(validate_record(valid_record))


@pytest.mark.parametrize("field", MANDATORY_FIELDS)
def test_each_mandatory_field_is_required(valid_record, field):
    valid_record[field] = None
    assert field in fields(validate_record(valid_record))


@pytest.mark.parametrize("field,bad", [
    ("plant_height_cm", 0), ("plant_height_cm", 500), ("plant_height_cm", -3),
    ("leaf_count", -1), ("leaf_count", 500), ("leaf_count", 3.5),
    ("ph_level", 14.1), ("ph_level", -0.1), ("ec_level", 10.5),
    ("dissolved_oxygen", 21), ("temperature_c", 61), ("temperature_c", -11),
    ("humidity_pct", 101), ("nitrate_mg_l", 0), ("nitrate_mg_l", 1000),
    ("phosphate_mg_l", 500), ("spad_index", 100.5), ("root_length_cm", 200),
    ("fresh_weight_g", 10000), ("plant_height_cm", "abc"),
])
def test_out_of_range_or_non_numeric_is_blocked(valid_record, field, bad):
    valid_record[field] = bad
    assert field in fields(validate_record(valid_record))


@pytest.mark.parametrize("field,good", [
    ("ph_level", 0), ("ph_level", 14), ("spad_index", 0), ("spad_index", 100),
    ("temperature_c", -10), ("temperature_c", 60), ("humidity_pct", 100),
    ("leaf_count", 0), ("leaf_count", 499),
])
def test_boundary_values_that_are_allowed(valid_record, field, good):
    valid_record[field] = good
    assert validate_record(valid_record) == []


def test_optional_fields_may_be_blank(valid_record):
    for f in ("fresh_weight_g", "dry_weight_g", "ph_level", "nitrate_mg_l", "notes", ""):
        valid_record[f] = None
    assert validate_record(valid_record) == []


def test_dry_weight_cannot_exceed_fresh_weight(valid_record):
    valid_record.update(fresh_weight_g=100, dry_weight_g=150)
    assert "dry_weight_g" in fields(validate_record(valid_record))


def test_dry_weight_check_skipped_when_fresh_is_blank(valid_record):
    valid_record.update(fresh_weight_g=None, dry_weight_g=150)
    assert validate_record(valid_record) == []


@pytest.mark.parametrize("field,bad", [
    ("visit_type", "VISIT"), ("treatment_group_id", "TGID-6"), ("trial_week", "TW-0"),
    ("trial_week", "week 3"), ("observer_id", "OID-12"), ("entry_date", "12/10/2026"),
])
def test_format_rules(valid_record, field, bad):
    valid_record[field] = bad
    assert field in fields(validate_record(valid_record))
