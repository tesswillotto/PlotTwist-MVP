"""DALRRD Act 36 dossier: a ZIP with anonymised CSV data + Markdown protocol text."""
import io
import zipfile

import pandas as pd

# Only these columns are exported. Farmer names and contact details live in the
# auth table and are never in trial rows. Free-text notes are left out because a
# farmer could type a name into them. GPS is not collected at all.
EXPORT_COLUMNS = [
    "record_id", "entry_date", "site_id", "environment_id", "crop_id",
    "treatment_group_id", "plot_id", "trial_week", "visit_type", "observer_id",
    "plant_height_cm", "leaf_count", "fresh_weight_g", "dry_weight_g", "spad_index",
    "root_length_cm", "ph_level", "ec_level", "dissolved_oxygen", "temperature_c",
    "humidity_pct", "nitrate_mg_l", "phosphate_mg_l", "is_harvest_complete",
]


def anonymise(records: list) -> pd.DataFrame:
    """Keep only the whitelisted columns (Observer ID kept for audit traceability)."""
    frame = pd.DataFrame(records)
    for col in EXPORT_COLUMNS:
        if col not in frame:
            frame[col] = None
    return frame[EXPORT_COLUMNS]


def combine_protocols(control_text, variant_text, variant_id: str) -> str:
    """Control protocol (TGID-0) followed by the selected variant's protocol."""
    return (
        "# Treatment Protocol Description\n\n"
        "## Control group (TGID-0)\n\n"
        f"{control_text or '_Protocol text not yet confirmed by the Eduponics research team._'}\n\n"
        f"## Variant group ({variant_id})\n\n"
        f"{variant_text or '_Protocol text not yet confirmed by the Eduponics research team._'}\n")


def build_dossier(records: list, control_protocol, variant_protocol, variant_id: str) -> bytes:
    """Return the dossier ZIP as bytes."""
    csv_text = anonymise(records).to_csv(index=False)
    protocol_md = combine_protocols(control_protocol, variant_protocol, variant_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("trial_observation_data.csv", csv_text)
        z.writestr("treatment_protocol_description.md", protocol_md)
    return buffer.getvalue()
