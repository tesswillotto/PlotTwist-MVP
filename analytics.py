"""Statistics: univariate 95% confidence intervals (Student's t) and plot yield."""
import math

import numpy as np
from scipy import stats

from config import MIN_N


def mean_ci(values, confidence: float = 0.95) -> dict:
    """Mean and confidence interval of one group using Student's t-distribution."""
    data = np.asarray(values, dtype=float)
    n = len(data)
    mean = float(data.mean())
    sd = float(data.std(ddof=1))                     # sample standard deviation
    sem = sd / math.sqrt(n)                          # standard error of the mean
    t_crit = float(stats.t.ppf(1 - (1 - confidence) / 2, n - 1))
    margin = t_crit * sem
    return {"n": n, "mean": mean, "sd": sd, "sem": sem, "t_value": t_crit,
            "margin": margin, "ci_lower": mean - margin, "ci_upper": mean + margin}


def _clean(values) -> list:
    """Blank (None) nitrate values are ignored and do not count towards n."""
    return [float(v) for v in values if v is not None]


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
    result.update(
        sufficient=True, control=c, variant=v, overlap=overlap,
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
