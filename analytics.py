"""Statistics: univariate 95% confidence intervals (Student's t) and plot yield."""
import math

import numpy as np
from scipy import stats

from config import MIN_N


def mean_ci(values, confidence: float = 0.95) -> dict:
    """Mean and confidence interval of one group using Student's t-distribution."""
    data = np.asarray(values, dtype=float)
    n = len(data)
    if n < 2:
        raise ValueError("At least 2 values are needed for a confidence interval.")
    mean = float(data.mean())
    sd = float(data.std(ddof=1))                     # sample standard deviation
    sem = sd / math.sqrt(n)                          # standard error of the mean
    t_crit = float(stats.t.ppf(1 - (1 - confidence) / 2, n - 1))
    margin = t_crit * sem
    return {"n": n, "mean": mean, "sd": sd, "sem": sem, "t_value": t_crit,
            "margin": margin, "ci_lower": mean - margin, "ci_upper": mean + margin}


def _clean(values) -> list:
    """Blank (None) nitrate values are ignored and do not count towards n."""
    out = []
    for v in values:
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        out.append(float(v))
    return [v for v in out if not math.isnan(v)]


def compare_nitrate(control_values, variant_values, min_n: int = MIN_N) -> dict:
    """Control vs variant nitrate comparison.

    The chart is only produced when BOTH groups have at least min_n readings.
    """
    control, variant = _clean(control_values), _clean(variant_values)
    result = {"n_control": len(control), "n_variant": len(variant), "min_n": min_n}
    if len(control) < min_n or len(variant) < min_n:
        result.update(sufficient=False, notice=(
            f"More records needed: at least {min_n} nitrate readings per treatment group "
            f"are required for a 95% confidence interval "
            f"(control has {len(control)}, variant has {len(variant)})."))
        return result

    c, v = mean_ci(control), mean_ci(variant)
    overlap = not (c["ci_upper"] < v["ci_lower"] or v["ci_upper"] < c["ci_lower"])
    difference = v["mean"] - c["mean"]
    result.update(
        sufficient=True, control=c, variant=v, overlap=overlap,
        difference=difference,
        difference_pct=(difference / c["mean"] * 100) if c["mean"] else None,
        # Green: intervals do not overlap (clear difference). Yellow: they overlap.
        band="yellow" if overlap else "green",
        band_text=("The 95% intervals overlap: no clear difference yet."
                   if overlap else "The 95% intervals do not overlap: clear difference."))
    return result


def plot_yield(harvest_records: list, area_m2) -> float:
    """Yield in g/m2 = total fresh weight of the plot's harvest records / plot area.

    Returns None while no harvest has been marked complete ("Harvest in progress").
    """
    if not area_m2 or not any(r.get("is_harvest_complete") for r in harvest_records):
        return None
    total = sum(float(r["fresh_weight_g"]) for r in harvest_records
                if r.get("fresh_weight_g") is not None)
    return total / float(area_m2)


def compare_all_groups(control_values, variant_values_by_group: dict, min_n: int = MIN_N) -> list:
    """Compare the control with EVERY treatment group (TGID-1 to TGID-5).

    Returns one compare_nitrate() result per group, each with a "group" key added.
    """
    results = []
    for group, values in variant_values_by_group.items():
        result = compare_nitrate(control_values, values, min_n)
        result["group"] = group
        results.append(result)
    return results


def summarise(values) -> dict:
    """n, mean and sample SD of the non-blank values (no confidence interval)."""
    data = _clean(values)
    n = len(data)
    return {"n": n,
            "mean": float(np.mean(data)) if n else None,
            "sd": float(np.std(data, ddof=1)) if n > 1 else None}


def verdict(result: dict) -> str:
    """Plain-words result of one control-vs-group comparison."""
    if not result["sufficient"]:
        return "Insufficient data"
    if result["overlap"]:
        return "No clear difference"
    return "Clear difference (higher)" if result["difference"] > 0 else "Clear difference (lower)"
