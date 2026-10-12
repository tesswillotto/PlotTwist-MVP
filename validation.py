"""Shared validation rules (Milestone 1, Section 6b).

The SAME function runs on the phone (before saving) and in the API (before
writing to the cloud), so a record that passes on the phone is judged by the
same rules as the one the cloud applies.
"""
import math
import re
from datetime import date

from config import TREATMENT_GROUPS, VISIT_TYPES

# The 11 mandatory fields (Milestone 1, Section 2c).
MANDATORY_FIELDS = (
    "local_id",            # Record ID (temporary on the device)
    "entry_date",
    "site_id",
    "environment_id",
    "crop_id",
    "treatment_group_id",
    "visit_type",
    "trial_week",
    "observer_id",
    "plant_height_cm",
    "leaf_count",
)

# field: (low, high, low_inclusive, high_inclusive, label)
RANGE_RULES = {
    "plant_height_cm": (0.0, 500.0, False, False, "Plant height (cm)"),
    "leaf_count": (0, 500, True, False, "Leaf count"),
    "fresh_weight_g": (0.0, 10000.0, False, False, "Fresh weight (g)"),
    "dry_weight_g": (0.0, 10000.0, False, False, "Dry weight (g)"),
    "spad_index": (0.0, 100.0, True, True, "SPAD index"),
    "root_length_cm": (0.0, 200.0, False, False, "Root length (cm)"),
    "ph_level": (0.0, 14.0, True, True, "pH"),
    "ec_level": (0.0, 10.0, True, True, "EC (mS/cm)"),
    "dissolved_oxygen": (0.0, 20.0, True, True, "Dissolved O2 (mg/L)"),
    "temperature_c": (-10.0, 60.0, True, True, "Temperature (C)"),
    "humidity_pct": (0.0, 100.0, True, True, "Humidity (%)"),
    "nitrate_mg_l": (0.0, 1000.0, False, False, "Nitrate (mg/L)"),
    "phosphate_mg_l": (0.0, 500.0, False, False, "Phosphate (mg/L)"),
}

_TRIAL_WEEK = re.compile(r"^TW-[1-9][0-9]*$")
_OBSERVER = re.compile(r"^OID-[0-9]{3}$")


def is_blank(value) -> bool:
    """True for None, empty/whitespace strings and NaN."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _to_number(value) -> float:
    """Convert to a finite float or raise ValueError."""
    if isinstance(value, bool):
        raise ValueError("must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("must be a number")
    if math.isnan(number) or math.isinf(number):
        raise ValueError("must be a number")
    return number


def _range_text(low, high, low_inc, high_inc) -> str:
    low_word = "at least" if low_inc else "more than"
    high_word = "at most" if high_inc else "less than"
    return f"must be {low_word} {low} and {high_word} {high}"


def validate_record(rec: dict) -> list:
    """Validate one trial record.

    Returns a list of (field, message) tuples. An empty list means the record
    is valid. Optional fields may be blank; if filled they must be in range.
    """
    errors = []

    # 1. Mandatory fields present
    for field in MANDATORY_FIELDS:
        if is_blank(rec.get(field)):
            errors.append((field, "is mandatory"))

    # 2. Format checks on the identifier-style fields
    iso = rec.get("entry_date")
    if not is_blank(iso):
        try:
            date.fromisoformat(str(iso))
        except ValueError:
            errors.append(("entry_date", "must be a valid date (YYYY-MM-DD)"))
    if not is_blank(rec.get("visit_type")) and rec["visit_type"] not in VISIT_TYPES:
        errors.append(("visit_type", "must be ROUTINE_MONITORING or HARVEST_VISIT"))
    if (not is_blank(rec.get("treatment_group_id"))
            and rec["treatment_group_id"] not in TREATMENT_GROUPS):
        errors.append(("treatment_group_id", "must be TGID-0 to TGID-5"))
    if not is_blank(rec.get("trial_week")) and not _TRIAL_WEEK.match(str(rec["trial_week"])):
        errors.append(("trial_week", "must look like TW-1, TW-2, ..."))
    if not is_blank(rec.get("observer_id")) and not _OBSERVER.match(str(rec["observer_id"])):
        errors.append(("observer_id", "must look like OID-###"))

    # 3. Numeric ranges (mandatory metrics are already reported as missing above)
    numbers = {}
    for field, (low, high, low_inc, high_inc, label) in RANGE_RULES.items():
        value = rec.get(field)
        if is_blank(value):
            continue
        try:
            number = _to_number(value)
        except ValueError as exc:
            errors.append((field, f"{label} {exc}"))
            continue
        if field == "leaf_count" and not number.is_integer():
            errors.append((field, "Leaf count must be a whole number"))
            continue
        ok_low = number >= low if low_inc else number > low
        ok_high = number <= high if high_inc else number < high
        if not (ok_low and ok_high):
            errors.append((field, f"{label} {_range_text(low, high, low_inc, high_inc)}"))
        else:
            numbers[field] = number

    # 4. Null-safe cross-field rule: dry weight <= fresh weight (only if both filled)
    if "dry_weight_g" in numbers and "fresh_weight_g" in numbers:
        if numbers["dry_weight_g"] > numbers["fresh_weight_g"]:
            errors.append(("dry_weight_g", "Dry weight cannot be more than fresh weight"))

    return errors


def format_errors(errors: list) -> str:
    """Turn the error list into one readable sentence for the UI / API."""
    return "; ".join(f"{field}: {message}" for field, message in errors)
