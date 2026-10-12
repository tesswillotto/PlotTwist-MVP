"""Unit tests for the confidence-interval engine and yield calculation."""
import math

import numpy as np
import pytest
from scipy import stats

from analytics import compare_nitrate, mean_ci, plot_yield


def test_mean_ci_matches_hand_calculation():
    data = [10, 12, 11, 13, 14]
    r = mean_ci(data)
    sd = np.std(data, ddof=1)
    margin = stats.t.ppf(0.975, 4) * sd / math.sqrt(5)
    assert r["mean"] == pytest.approx(12.0)
    assert r["margin"] == pytest.approx(margin)
    assert r["ci_lower"] == pytest.approx(12.0 - margin)
    assert r["ci_upper"] == pytest.approx(12.0 + margin)
    assert r["t_value"] == pytest.approx(2.776, abs=1e-3)  # t(0.975, df=4)


def test_fewer_than_five_blocks_the_chart():
    result = compare_nitrate([1, 2, 3, 4, 5], [1, 2, 3, 4])
    assert result["sufficient"] is False
    assert "More records needed" in result["notice"]
    assert (result["n_control"], result["n_variant"]) == (5, 4)


def test_blank_nitrate_values_do_not_count_towards_n():
    result = compare_nitrate([1, 2, None, 4, 5, None], [1, 2, 3, 4, 5])
    assert result["n_control"] == 4 and result["sufficient"] is False


def test_five_in_both_groups_gives_ci():
    result = compare_nitrate([110, 112, 108, 111, 109], [140, 142, 138, 141, 139])
    assert result["sufficient"] is True
    assert result["band"] == "green" and result["overlap"] is False


def test_overlapping_intervals_are_yellow():
    result = compare_nitrate([100, 120, 90, 130, 110], [105, 125, 95, 128, 112])
    assert result["sufficient"] is True and result["band"] == "yellow"


def test_yield_is_total_fresh_weight_over_area():
    rows = [{"fresh_weight_g": 1300, "is_harvest_complete": False},
            {"fresh_weight_g": 1500, "is_harvest_complete": True}]
    assert plot_yield(rows, 10) == pytest.approx(280.0)


def test_yield_is_none_until_harvest_complete():
    assert plot_yield([{"fresh_weight_g": 1300, "is_harvest_complete": False}], 10) is None
    assert plot_yield([], 10) is None
    assert plot_yield([{"fresh_weight_g": 5, "is_harvest_complete": True}], None) is None
