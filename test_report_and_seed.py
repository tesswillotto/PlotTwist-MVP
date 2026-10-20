"""Tests for the all-groups comparison, the PDF report and the demo seed data (Role 6)."""
import analytics
import cloud_store
import config
from report_pdf import build_pdf_report, collect_report_data
from validation import validate_record

SITE, CROP = "SITE-WINELANDS-01", "Tomato"


def _fill(store, nitrate_by_group, week="TW-3"):
    """A small cloud store: one site, 6 plots, protocols and the given nitrate readings."""
    store.create_site_if_absent(SITE, "2026-09-01")
    for g in config.TREATMENT_GROUPS:
        plot_id = f"{SITE}-{CROP}-{g}"
        store.create_plot_if_absent({"plot_id": plot_id, "site_id": SITE, "crop_id": CROP,
                                     "treatment_group_id": g, "area_m2": 10.0})
        store.set_protocol(g, f"**{g} protocol.** Standard fertigation.\n\n- Crop: Tomato\n")
    n = 0
    for g, values in nitrate_by_group.items():
        for value in values:
            n += 1
            store.upsert_trial({
                "local_id": f"r{n}", "created_timestamp": "2026-09-20 08:00:00",
                "entry_date": "2026-09-20", "site_id": SITE, "environment_id": "Greenhouse",
                "crop_id": CROP, "treatment_group_id": g, "plot_id": f"{SITE}-{CROP}-{g}",
                "trial_week": week, "visit_type": "ROUTINE_MONITORING", "observer_id": "OID-102",
                "plant_height_cm": 40.0, "leaf_count": 12, "nitrate_mg_l": value,
                "notes": "Spoke to Mr Jacobs", "is_harvest_complete": False})


CONTROL = [110, 112, 108, 111, 109]
HIGH = [140, 142, 138, 141, 139]
SAME = [109, 113, 107, 112, 110]


# ------------------------------------------------------------- analytics ----
def test_compare_all_groups_gives_one_result_per_group():
    results = analytics.compare_all_groups(
        CONTROL, {"TGID-1": HIGH, "TGID-2": SAME, "TGID-3": [1, 2, 3]})
    assert [r["group"] for r in results] == ["TGID-1", "TGID-2", "TGID-3"]
    assert [analytics.verdict(r) for r in results] == [
        "Clear difference (higher)", "No clear difference", "Insufficient data"]


def test_difference_from_control_is_reported():
    r = analytics.compare_nitrate(CONTROL, HIGH)
    assert abs(r["difference"] - 30.0) < 1e-9
    assert abs(r["difference_pct"] - 30.0 / 110.0 * 100) < 1e-9


def test_a_lower_group_is_called_a_clear_difference_lower():
    low = [80, 82, 78, 81, 79]
    assert analytics.verdict(analytics.compare_nitrate(CONTROL, low)) == "Clear difference (lower)"


def test_summarise_ignores_blanks():
    s = analytics.summarise([10, None, "", 20, float("nan")])
    assert s["n"] == 2 and s["mean"] == 15.0
    assert analytics.summarise([])["mean"] is None


# ----------------------------------------------------------- PDF report ----
def test_report_compares_every_group(tmp_path):
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    _fill(store, {"TGID-0": CONTROL, "TGID-1": HIGH, "TGID-2": SAME})
    data = collect_report_data(store, SITE, CROP)
    assert data["trial_week"] == "TW-3"
    assert [r["group"] for r in data["results"]] == list(config.VARIANT_GROUPS)
    verdicts = {r["group"]: analytics.verdict(r) for r in data["results"]}
    assert verdicts["TGID-1"] == "Clear difference (higher)"
    assert verdicts["TGID-2"] == "No clear difference"
    assert verdicts["TGID-3"] == "Insufficient data"


def test_pdf_is_a_real_pdf_with_the_group_comparison(tmp_path):
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    _fill(store, {"TGID-0": CONTROL, "TGID-1": HIGH})
    pdf = build_pdf_report(store, SITE, CROP, compress=False)
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
    for text in (b"Group 3 Biostimulant Trial Report", b"TGID-1", b"Clear difference"):
        assert text in pdf


def test_pdf_contains_no_personal_data(tmp_path):
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    _fill(store, {"TGID-0": CONTROL, "TGID-1": HIGH})
    store.create_user("someone", "Small Farmer", "Secret Name", "secret@contact.com", "s", "h",
                      oid="OID-102")
    pdf = build_pdf_report(store, SITE, CROP, compress=False)
    for text in (b"Secret Name", b"secret@contact.com", b"Jacobs", b"someone"):
        assert text not in pdf


def test_pdf_with_no_data_does_not_crash(tmp_path):
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    pdf = build_pdf_report(store, SITE, CROP)
    assert pdf.startswith(b"%PDF")


def test_pdf_with_too_little_control_data_explains_why(tmp_path):
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    _fill(store, {"TGID-0": [1, 2, 3], "TGID-1": HIGH})
    pdf = build_pdf_report(store, SITE, CROP, compress=False)
    assert b"fewer than 5 valid nitrate readings" in pdf


# -------------------------------------------------------------- demo seed ----
def test_seed_loads_enough_records_for_proper_results(tmp_path):
    import seed_demo
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    cloud_store.set_store(store)
    seed_demo.seed(reset_local=False)

    assert store.get_user("sam")["full_name"] == "Sam"
    rows = store.list_trials(site_id=SITE, crop_id=CROP)
    assert len(rows) > 150

    def nitrate(group, week):
        return [r["nitrate_mg_l"] for r in rows
                if r["treatment_group_id"] == group and r["trial_week"] == week
                and r["nitrate_mg_l"] is not None]       # harvest visits have no nitrate

    for week in ("TW-1", "TW-2", "TW-3", "TW-4", "TW-5"):       # every group, every week
        for group in config.TREATMENT_GROUPS:
            assert len(nitrate(group, week)) >= config.MIN_N, (group, week)
    assert len(nitrate("TGID-1", "TW-6")) == 4                   # the live demo trick
    assert len(nitrate("TGID-0", "TW-6")) >= config.MIN_N


def test_every_seeded_record_passes_validation(tmp_path):
    import seed_demo
    store = cloud_store.MockCloudStore(str(tmp_path / "cloud.db"))
    cloud_store.set_store(store)
    seed_demo.seed(reset_local=False)
    for row in store.list_trials(site_id=SITE, crop_id=CROP):
        assert validate_record(dict(row, local_id=row["client_uuid"])) == [], row["client_uuid"]
