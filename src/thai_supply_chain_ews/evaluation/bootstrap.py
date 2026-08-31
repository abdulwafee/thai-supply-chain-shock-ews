"""Deterministic moving-block bootstrap over forecast-origin months (Task B4).

Why the resampling unit is the MONTH, not the row: all 12 industries share
common calendar shocks, year-over-year observations overlap by 11 of 12 months,
and 3-month target windows overlap further. Treating 180 industry-month rows as
180 independent observations would produce confidence intervals far too narrow
to be honest. So an entire origin month — all 12 industries together — is the
cluster, and blocks of consecutive months are resampled to retain short-run
dependence between adjacent origins.

Implementation note: the statistic is computed on a dense
(n_months x n_industries) absolute-error matrix rather than by re-slicing a
DataFrame per replication. Macro MAE is exactly `errors[idx].mean(axis=0).mean()`
under that layout — mean over the sampled months per industry, then an equal
average across industries — so the vectorized form is not an approximation of
the frame-based one, it is the same quantity computed without 10,000 pandas
concatenations.

Every interval produced here is descriptive. A CI that crosses zero means the
comparison is INCONCLUSIVE on this development sample; it is not evidence that
two baselines are equivalent, and nothing here supports a causal claim.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

__all__ = [
    "ErrorMatrix",
    "block_indices",
    "bootstrap_macro_mae_ci",
    "bootstrap_paired_macro_mae_difference",
    "build_error_matrix",
    "describe_interval",
    "macro_mae_from_matrix",
]


class ErrorMatrix:
    """Absolute errors laid out as (month, industry), with the axis labels."""

    def __init__(self, values: np.ndarray, months: list[str], industries: list[str]) -> None:
        self.values = values
        self.months = months
        self.industries = industries

    @property
    def n_months(self) -> int:
        return len(self.months)

    @property
    def n_industries(self) -> int:
        return len(self.industries)


def build_error_matrix(
    frame: pd.DataFrame,
    month_column: str = "forecast_origin_month",
    industry_column: str = "industry_id",
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
) -> ErrorMatrix:
    """Pivot one baseline-horizon slice into a dense absolute-error matrix.

    Raises if the slice is not exactly one row per (month, industry) — a missing
    or duplicated cell would silently change what the macro average means.
    """
    months = sorted(frame[month_column].unique().tolist())
    industries = sorted(frame[industry_column].unique().tolist())
    expected = len(months) * len(industries)
    if len(frame) != expected:
        raise ValueError(
            f"Expected exactly one row per (month, industry): {len(months)} x "
            f"{len(industries)} = {expected}, found {len(frame)} rows."
        )
    errors = (
        (frame[observed_column].astype(float) - frame[predicted_column].astype(float))
        .abs()
        .to_numpy()
    )
    pivot = pd.DataFrame(
        {
            "month": frame[month_column].to_numpy(),
            "industry": frame[industry_column].to_numpy(),
            "error": errors,
        }
    ).pivot(index="month", columns="industry", values="error")
    pivot = pivot.reindex(index=months, columns=industries)
    if pivot.isna().to_numpy().any():
        raise ValueError("Error matrix has missing (month, industry) cells.")
    return ErrorMatrix(pivot.to_numpy(dtype=float), months, industries)


def macro_mae_from_matrix(values: np.ndarray) -> float:
    """Per-industry MAE first, then an equal average across industries."""
    if values.size == 0:
        return float("nan")
    return float(values.mean(axis=0).mean())


def block_indices(
    n_months: int, block_length: int, rng: np.random.Generator
) -> np.ndarray:
    """Month-position indices for one moving-block resample."""
    if n_months < block_length:
        return np.arange(n_months)
    n_starts = n_months - block_length + 1
    n_blocks = math.ceil(n_months / block_length)
    starts = rng.integers(0, n_starts, size=n_blocks)
    return np.concatenate([np.arange(s, s + block_length) for s in starts])[:n_months]


def _percentile_interval(estimates: list[float], level: float) -> tuple[float | None, float | None]:
    if not estimates:
        return None, None
    alpha = (1.0 - level) / 2.0
    return (
        float(np.percentile(estimates, 100 * alpha)),
        float(np.percentile(estimates, 100 * (1 - alpha))),
    )


def bootstrap_macro_mae_ci(
    matrix: ErrorMatrix, config: dict, seed_offset: int = 0
) -> dict:
    """Bootstrap macro-industry MAE by resampling whole origin months in blocks."""
    block_length = int(config["block_length_months"])
    replications = int(config["replications"])
    level = float(config["confidence_level"])
    seed = int(config["random_seed"])

    rng = np.random.default_rng([seed, seed_offset])
    point = macro_mae_from_matrix(matrix.values)
    estimates = []
    for _ in range(replications):
        idx = block_indices(matrix.n_months, block_length, rng)
        estimates.append(macro_mae_from_matrix(matrix.values[idx]))

    low, high = _percentile_interval(estimates, level)
    return {
        "point_estimate": point,
        "ci_low": low,
        "ci_high": high,
        "replications": len(estimates),
        "block_length_months": block_length,
        "seed": seed,
        "cluster_unit": "forecast_origin_month",
        "n_month_clusters": matrix.n_months,
        "keeps_all_industries_together": True,
    }


def bootstrap_paired_macro_mae_difference(
    matrix_a: ErrorMatrix, matrix_b: ErrorMatrix, config: dict, seed_offset: int = 0
) -> dict:
    """Bootstrap macro-MAE(A) − macro-MAE(B) on PAIRED month draws.

    Both baselines see the same resampled months, so the interval reflects the
    difference between them rather than the sum of two independent sampling
    errors.
    """
    if matrix_a.months != matrix_b.months:
        raise ValueError("Paired bootstrap requires identical month axes")

    block_length = int(config["block_length_months"])
    replications = int(config["replications"])
    level = float(config["confidence_level"])
    seed = int(config["random_seed"])

    rng = np.random.default_rng([seed, seed_offset])
    point = macro_mae_from_matrix(matrix_a.values) - macro_mae_from_matrix(matrix_b.values)
    estimates = []
    for _ in range(replications):
        idx = block_indices(matrix_a.n_months, block_length, rng)
        estimates.append(
            macro_mae_from_matrix(matrix_a.values[idx])
            - macro_mae_from_matrix(matrix_b.values[idx])
        )

    low, high = _percentile_interval(estimates, level)
    verdict = describe_interval(low, high)
    return {
        "point_estimate": point,
        "ci_low": low,
        "ci_high": high,
        "replications": len(estimates),
        "block_length_months": block_length,
        "seed": seed,
        "cluster_unit": "forecast_origin_month",
        "paired": True,
        "verdict": verdict,
        "conclusive": verdict == "excludes_zero",
    }


def describe_interval(low: float | None, high: float | None) -> str:
    """A CI spanning zero means inconclusive — never 'no difference'."""
    if low is None or high is None:
        return "undefined"
    if low <= 0.0 <= high:
        return "inconclusive"
    return "excludes_zero"
