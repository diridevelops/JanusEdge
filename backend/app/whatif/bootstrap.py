"""Bootstrap utilities for what-if stop analysis."""

from __future__ import annotations

import math
import random
from typing import Dict, List, TypedDict


CONFIDENCE = 0.95
DEGENERACY_EPSILON = 1e-12
ADJUSTMENT_DENOMINATOR_EPSILON = 1e-12
TIE_EPSILON = 1e-12
DEFAULT_BOOTSTRAP_SAMPLES = 5_000
DEFAULT_RANDOM_SEED = 42
METRIC_KEYS = (
    "mean",
    "median",
    "p75",
    "p90",
    "p95",
    "iqr",
)


class ConfidenceInterval(TypedDict):
    """Lower and upper confidence interval bounds."""

    lower: float
    upper: float


def sort_numbers(values: List[float]) -> List[float]:
    """Return a sorted copy of numeric values."""
    return sorted(values)


def quantile_sorted(
    sorted_values: List[float], probability: float
) -> float:
    """Compute a linear-interpolated quantile from sorted values."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    rank = probability * (len(sorted_values) - 1)
    low_index = math.floor(rank)
    high_index = min(low_index + 1, len(sorted_values) - 1)
    weight = rank - low_index
    low_value = float(sorted_values[low_index])
    high_value = float(sorted_values[high_index])
    return low_value + ((high_value - low_value) * weight)


def summarize(values: List[float]) -> Dict[str, float]:
    """Compute stop-analysis summary metrics for overshoot values."""
    if not values:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "iqr": 0.0,
        }

    sorted_values = sort_numbers(values)
    mean = sum(values) / len(values)
    median = quantile_sorted(sorted_values, 0.5)
    p75 = quantile_sorted(sorted_values, 0.75)
    p90 = quantile_sorted(sorted_values, 0.9)
    p95 = quantile_sorted(sorted_values, 0.95)
    p25 = quantile_sorted(sorted_values, 0.25)

    return {
        "mean": mean,
        "median": median,
        "p75": p75,
        "p90": p90,
        "p95": p95,
        "iqr": p75 - p25,
    }


def clamp_probability(probability: float) -> float:
    """Clamp a probability away from exact 0 and 1."""
    epsilon = 1e-10
    return min(1 - epsilon, max(epsilon, probability))


def normal_cdf(value: float) -> float:
    """Approximate the standard normal CDF."""
    abs_value = abs(value)
    t = 1 / (1 + (0.2316419 * abs_value))
    d = 0.3989423 * math.exp((-value * value) / 2)
    probability = d * t * (
        0.3193815
        + t
        * (
            -0.3565638
            + t * (1.781478 + t * (-1.821256 + (t * 1.330274)))
        )
    )
    probability = 1 - probability
    return 1 - probability if value < 0 else probability


def normal_quantile(probability: float) -> float:
    """Approximate the inverse CDF of the standard normal."""
    p = clamp_probability(probability)
    a = (
        -39.69683028665376,
        220.9460984245205,
        -275.9285104469687,
        138.357751867269,
        -30.66479806614716,
        2.506628277459239,
    )
    b = (
        -54.47609879822406,
        161.5858368580409,
        -155.6989798598866,
        66.80131188771972,
        -13.28068155288572,
    )
    c = (
        -0.007784894002430293,
        -0.3223964580411365,
        -2.400758277161838,
        -2.549732539343734,
        4.374664141464968,
        2.938163982698783,
    )
    d = (
        0.007784695709041462,
        0.3224671290700398,
        2.445134137142996,
        3.754408661907416,
    )

    low = 0.02425
    high = 1 - low

    if p < low:
        q = math.sqrt(-2 * math.log(p))
        numerator = (
            (((((c[0] * q) + c[1]) * q + c[2]) * q + c[3]) * q + c[4])
            * q
        ) + c[5]
        denominator = ((((d[0] * q) + d[1]) * q + d[2]) * q + d[3]) * q + 1
        return numerator / denominator

    if p > high:
        q = math.sqrt(-2 * math.log(1 - p))
        numerator = (
            (((((c[0] * q) + c[1]) * q + c[2]) * q + c[3]) * q + c[4])
            * q
        ) + c[5]
        denominator = ((((d[0] * q) + d[1]) * q + d[2]) * q + d[3]) * q + 1
        return -(numerator / denominator)

    q = p - 0.5
    r = q * q
    numerator = (
        (((((a[0] * r) + a[1]) * r + a[2]) * r + a[3]) * r + a[4])
        * r
    ) + a[5]
    denominator = (
        (((((b[0] * r) + b[1]) * r + b[2]) * r + b[3]) * r + b[4])
        * r
    ) + 1
    return (numerator * q) / denominator


def percentile_from_sorted(
    sorted_values: List[float], probability: float
) -> float:
    """Compute a percentile from pre-sorted values."""
    return quantile_sorted(sorted_values, clamp_probability(probability))


def values_are_nearly_equal(left: float, right: float) -> bool:
    """Return whether two floating-point values are effectively equal."""
    scale = max(1, abs(left), abs(right))
    return abs(left - right) <= (TIE_EPSILON * scale)


def compute_bias_correction_probability(
    bootstrap_stats: List[float], theta_hat: float
) -> float:
    """Compute the BCa bias correction probability."""
    less_count = 0
    equal_count = 0

    for value in bootstrap_stats:
        if values_are_nearly_equal(value, theta_hat):
            equal_count += 1
        elif value < theta_hat:
            less_count += 1

    probability = (less_count + (0.5 * equal_count)) / len(bootstrap_stats)
    return clamp_probability(probability)


def adjusted_bca_probability(
    z0: float, z_alpha: float, acceleration: float
) -> float:
    """Adjust a probability using BCa bias and acceleration terms."""
    numerator = z0 + z_alpha
    denominator = 1 - (acceleration * (z0 + z_alpha))

    if abs(denominator) < ADJUSTMENT_DENOMINATOR_EPSILON:
        if abs(numerator) < ADJUSTMENT_DENOMINATOR_EPSILON:
            return normal_cdf(z0)
        return 1.0 if numerator * denominator > 0 else 0.0

    return normal_cdf(z0 + (numerator / denominator))


def bca_interval(
    values: List[float],
    metric_key: str,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> ConfidenceInterval:
    """Compute a BCa bootstrap confidence interval for one metric."""
    if not values:
        return {"lower": 0.0, "upper": 0.0}

    theta_hat = summarize(values)[metric_key]
    if len(values) < 2:
        return {"lower": theta_hat, "upper": theta_hat}

    rng = random.Random(random_seed)
    bootstrap_stats: List[float] = []
    for _ in range(bootstrap_samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        bootstrap_stats.append(summarize(sample)[metric_key])

    sorted_bootstrap = sort_numbers(bootstrap_stats)
    if (
        sorted_bootstrap[-1] - sorted_bootstrap[0]
    ) < DEGENERACY_EPSILON:
        return {
            "lower": sorted_bootstrap[0],
            "upper": sorted_bootstrap[0],
        }

    z0 = normal_quantile(
        compute_bias_correction_probability(bootstrap_stats, theta_hat)
    )

    jackknife_stats: List[float] = []
    for index in range(len(values)):
        jackknife_sample = [
            value
            for value_index, value in enumerate(values)
            if value_index != index
        ]
        if not jackknife_sample:
            jackknife_stats.append(theta_hat)
        else:
            jackknife_stats.append(
                summarize(jackknife_sample)[metric_key]
            )

    jackknife_mean = sum(jackknife_stats) / len(jackknife_stats)
    centered = [jackknife_mean - value for value in jackknife_stats]
    numerator = sum(value ** 3 for value in centered)
    denominator_base = sum(value ** 2 for value in centered)
    denominator = 6 * (denominator_base ** 1.5)
    acceleration = 0.0 if denominator == 0 else numerator / denominator

    alpha_low = (1 - CONFIDENCE) / 2
    alpha_high = 1 - alpha_low
    adjusted_low = adjusted_bca_probability(
        z0, normal_quantile(alpha_low), acceleration
    )
    adjusted_high = adjusted_bca_probability(
        z0, normal_quantile(alpha_high), acceleration
    )

    lower = percentile_from_sorted(sorted_bootstrap, adjusted_low)
    upper = percentile_from_sorted(sorted_bootstrap, adjusted_high)
    if lower <= upper:
        return {"lower": lower, "upper": upper}
    return {"lower": upper, "upper": lower}


def build_confidence_intervals(
    values: List[float],
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> Dict[str, ConfidenceInterval]:
    """Compute BCa confidence intervals for all stop-analysis metrics."""
    intervals: Dict[str, ConfidenceInterval] = {}
    for index, metric_key in enumerate(METRIC_KEYS):
        intervals[metric_key] = bca_interval(
            values,
            metric_key,
            bootstrap_samples=bootstrap_samples,
            random_seed=random_seed + (index * 9973),
        )
    return intervals


def empty_confidence_intervals() -> Dict[str, ConfidenceInterval]:
    """Return an empty confidence-interval payload."""
    return {
        metric_key: {"lower": 0.0, "upper": 0.0}
        for metric_key in METRIC_KEYS
    }