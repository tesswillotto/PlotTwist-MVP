"""Extra edge-case tests for analytics.py (Role 6: Analytics, Reports and Testing).

Add this file to the tests/ folder. Four of these tests need the two small
fixes to analytics.py (mean_ci guard and a stricter _clean) and fail until
those fixes are made.
"""
import pytest

from analytics import compare_nitrate, mean_ci, plot_yield


# ---------------------------------------------------------------- mean_ci ----
@pytest.mark.parametrize("values", [[], [5.0]])
def test_mean_ci_needs_at_least_two_values(values):
    """One value has no sample SD (NaN); empty has no mean. Both must be refused."""
    with pytest.raises(ValueError):
        mean_ci(values)


def test_identical_values_give_zero_width_interval():
    r = mean_ci([100, 100, 100, 100, 100])
    assert r["mean"] == pytest.approx(100.0)
    assert r["sd"] == pytest.approx(0.0)
    assert r["margin"] == pytest.approx(0.0)
    assert r["ci_lower"] == r["ci_upper"] == pytest.approx(100.0)


# ------------------------------------------------------- compare_nitrate -----
def test_blank_strings_and_nan_do_not_count_towards_n():
    """A blank form field ('') or a NaN from a CSV must not crash or poison the mean."""
    control = ["", 110, 112, 108, 111, 109, float("nan")]
    variant = [140, 142, 138, 141, 139]
    result = compare_nitrate(control, variant)
    assert result["n_control"] == 5
    assert result["sufficient"] is True
    assert result["control"]["mean"] == pytest.approx(110.0)


def test_four_in_control_blocks_even_when_variant_has_five():
    result = compare_nitrate([1, 2, 3, 4], [1, 2, 3, 4, 5])
    assert result["sufficient"] is False
    assert (result["n_control"], result["n_variant"]) == (4, 5)
    assert "control has 4, variant has 5" in result["notice"]


def test_both_groups_empty_gives_notice_not_crash():
    result = compare_nitrate([], [])
    assert result["sufficient"] is False
    assert (result["n_control"], result["n_variant"]) == (0, 0)


def test_identical_groups_are_yellow():
    same = [10, 11, 12, 13, 14]
    result = compare_nitrate(same, list(same))
    assert result["sufficient"] is True
    assert result["overlap"] is True and result["band"] == "yellow"


# -------------------------------------------------------------- plot_yield ---
def test_yield_ignores_blank_fresh_weights():
    rows = [{"fresh_weight_g": None, "is_harvest_complete": False},
            {"fresh_weight_g": 2000, "is_harvest_complete": True}]
    assert plot_yield(rows, 10) == pytest.approx(200.0)


def test_yield_is_none_for_zero_area():
    assert plot_yield([{"fresh_weight_g": 100, "is_harvest_complete": True}], 0) is None
