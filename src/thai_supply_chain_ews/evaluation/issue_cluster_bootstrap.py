"""Paired issue-month cluster bootstrap for the D5 development evaluation.

The unit of resampling is the **issue month**, never the industry row. Twelve
industries at one issue month share one national fuel-oil signal, one calibrator
and one release date; resampling them independently would treat twelve views of
the same month as twelve independent draws and shrink every interval by roughly
a factor of the square root of twelve.

Two shapes, one for each horizon:

* ``h=1`` — a plain cluster bootstrap over the fifteen issue months (block
  length one). Consecutive one-month-ahead errors are the least overlapping
  case available here.
* ``h=3`` — a moving-block bootstrap with block length three, because the
  three-month-ahead target windows of adjacent issue months overlap by
  construction and a plain cluster bootstrap would ignore that dependence.

**The model and the benchmark see the identical resamples.** The comparison of
interest is paired: the same fifteen months, the same reordering, both series.
Drawing separate resamples would add a difference that the data does not
contain. :func:`assert_paired_resamples` checks it rather than trusting it.

Fifteen clusters is a small number and the intervals are correspondingly wide;
that is reported alongside every interval rather than left to be inferred.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = [
    "CLUSTER_UNIT",
    "BootstrapError",
    "assert_no_row_level_resampling",
    "assert_paired_resamples",
    "block_positions",
    "issue_month_matrix",
    "paired_macro_mae_interval",
    "resample_plan",
]

CLUSTER_UNIT = "issue_month"

#: Fifteen development issue months. Small enough that the resolution limit is
#: stated with every interval instead of being left implicit.
RESOLUTION_NOTE = (
    "Fifteen issue clusters provide limited uncertainty resolution; these "
    "intervals are wide by construction."
)


class BootstrapError(ValueError):
    """A resampling scheme was asked to treat dependent rows as independent."""


def assert_no_row_level_resampling(unit: str) -> None:
    """Raise unless whole issue months are the resampling unit."""
    if str(unit) != CLUSTER_UNIT:
        raise BootstrapError(
            f"the resampling unit is {unit!r}, not {CLUSTER_UNIT!r}. Industry rows "
            "within one issue month share a national signal, a calibrator and a "
            "release date; resampling them independently would treat twelve views "
            "of one month as twelve independent draws"
        )


def issue_month_matrix(frame, month_column="issue_month", industry_column="industry_id",
                       observed_column="observed_score",
                       predicted_column="predicted_score"):
    """Absolute errors as a dense (issue month x industry) matrix.

    Raises on a missing or duplicated cell: either would silently change what
    the macro average means, and both are cheap to detect here.
    """
    months = sorted(frame[month_column].astype(str).unique().tolist())
    industries = sorted(frame[industry_column].astype(str).unique().tolist())
    expected = len(months) * len(industries)
    if len(frame) != expected:
        raise BootstrapError(
            f"expected one row per (issue month, industry): {len(months)} x "
            f"{len(industries)} = {expected}, found {len(frame)}"
        )
    errors = (
        frame[observed_column].astype(float) - frame[predicted_column].astype(float)
    ).abs().to_numpy()
    index = {(m, i): position for position, (m, i) in enumerate(
        zip(frame[month_column].astype(str), frame[industry_column].astype(str),
            strict=True)
    )}
    if len(index) != expected:
        raise BootstrapError("duplicate (issue month, industry) keys in the frame")
    values = np.array(
        [[errors[index[(m, i)]] for i in industries] for m in months], dtype=float
    )
    if not np.isfinite(values).all():
        raise BootstrapError("the error matrix has non-finite cells")
    return {"values": values, "months": months, "industries": industries}


def block_positions(n_months: int, block_length: int, rng) -> np.ndarray:
    """Month positions for one moving-block resample.

    ``block_length = 1`` is the plain cluster bootstrap; larger blocks keep
    consecutive months together so overlapping target windows travel as a unit.
    """
    if block_length < 1:
        raise BootstrapError(f"block length {block_length} must be at least 1")
    if n_months < block_length:
        raise BootstrapError(
            f"{n_months} issue months cannot supply a block of {block_length}"
        )
    starts = rng.integers(0, n_months - block_length + 1,
                          size=math.ceil(n_months / block_length))
    positions = np.concatenate(
        [np.arange(s, s + block_length) for s in starts]
    )[:n_months]
    return positions


def resample_plan(n_months: int, block_length: int, replications: int,
                  seed: int) -> list:
    """The full list of resamples, generated once and reused for both series.

    Generating the plan up front is what makes the comparison paired: the model
    and the benchmark are evaluated on the identical reorderings rather than on
    two independent draws that would differ by chance alone.
    """
    rng = np.random.default_rng(int(seed))
    return [
        block_positions(n_months, block_length, rng).tolist()
        for _ in range(int(replications))
    ]


def assert_paired_resamples(model_plan, benchmark_plan) -> None:
    """Raise unless model and benchmark were resampled identically."""
    if list(model_plan) != list(benchmark_plan):
        raise BootstrapError(
            "the model and the benchmark were resampled differently. The paired "
            "difference would then include variation the data does not contain"
        )


def _macro_mae(values) -> float:
    """Per-industry MAE first, then an equal average across industries."""
    if values.size == 0:
        return float("nan")
    return float(values.mean(axis=0).mean())


def _percentile_interval(estimates, level: float):
    if not estimates:
        return None, None
    tail = (1.0 - float(level)) / 2.0
    array = np.asarray(estimates, dtype=float)
    return (float(np.quantile(array, tail)),
            float(np.quantile(array, 1.0 - tail)))


def paired_macro_mae_interval(model_matrix, benchmark_matrix, block_length: int,
                              replications: int, seed: int,
                              confidence_level: float = 0.95,
                              cluster_unit: str = CLUSTER_UNIT) -> dict:
    """Model, benchmark and paired-difference intervals from one shared plan."""
    assert_no_row_level_resampling(cluster_unit)
    model_values = model_matrix["values"]
    benchmark_values = benchmark_matrix["values"]
    if model_matrix["months"] != benchmark_matrix["months"]:
        raise BootstrapError(
            "the model and the benchmark cover different issue months, so the "
            "comparison cannot be paired"
        )
    if model_values.shape != benchmark_values.shape:
        raise BootstrapError("model and benchmark error matrices differ in shape")

    n_months = model_values.shape[0]
    plan = resample_plan(n_months, block_length, replications, seed)
    assert_paired_resamples(plan, plan)

    model_estimates, benchmark_estimates, differences = [], [], []
    for positions in plan:
        index = np.asarray(positions, dtype=int)
        model_mae = _macro_mae(model_values[index])
        benchmark_mae = _macro_mae(benchmark_values[index])
        model_estimates.append(model_mae)
        benchmark_estimates.append(benchmark_mae)
        differences.append(model_mae - benchmark_mae)

    model_point = _macro_mae(model_values)
    benchmark_point = _macro_mae(benchmark_values)
    per_month_difference = (
        model_values.mean(axis=1) - benchmark_values.mean(axis=1)
    )
    model_low, model_high = _percentile_interval(model_estimates, confidence_level)
    bench_low, bench_high = _percentile_interval(benchmark_estimates, confidence_level)
    diff_low, diff_high = _percentile_interval(differences, confidence_level)

    return {
        "cluster_unit": cluster_unit,
        "keep_all_industries_together": True,
        "resample_individual_industry_rows": False,
        "block_length_months": int(block_length),
        "method": ("issue_month_cluster_bootstrap" if block_length == 1
                   else "moving_block_issue_month_bootstrap"),
        "replications": int(replications),
        "seed": int(seed),
        "confidence_level": float(confidence_level),
        "issue_month_clusters": int(n_months),
        "paired_resamples_identical": True,
        "model_macro_mae": model_point,
        "model_ci_low": model_low,
        "model_ci_high": model_high,
        "benchmark_macro_mae": benchmark_point,
        "benchmark_ci_low": bench_low,
        "benchmark_ci_high": bench_high,
        "paired_difference_point": model_point - benchmark_point,
        "paired_ci_low": diff_low,
        "paired_ci_high": diff_high,
        "paired_sign_convention": "negative means the model is better",
        "issue_months_model_beats_benchmark": int((per_month_difference < 0).sum()),
        "issue_months_total": int(n_months),
        "resolution_note": RESOLUTION_NOTE,
    }
