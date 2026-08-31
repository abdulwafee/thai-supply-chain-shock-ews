"""Development metrics, uncertainty and the preregistered verdict — Task D1.

The metric functions and the bootstrap come from B4; D1 reuses them rather than
reimplementing, so the model and the benchmark are judged by identical code.

The verdict rule is preregistered and mechanical. It exists so that a
disappointing result cannot be talked up, and a lucky one cannot be talked into
significance:

``incremental_signal_supported``
    Model macro MAE lower AND the paired 95% CI lies entirely below zero.
``inconclusive``
    Point estimate lower, but the CI includes zero.
``incremental_signal_not_supported``
    Model macro MAE equal to or worse than the benchmark.

High-stress metrics and sensitivity runs may qualify the discussion. They may
not override the rule.
"""

from __future__ import annotations

import numpy as np

from thai_supply_chain_ews.evaluation import bootstrap as BS
from thai_supply_chain_ews.evaluation import metrics as MT

__all__ = [
    "EVIDENCE_STATUSES",
    "HIGH_STRESS_THRESHOLD",
    "SEVERE_THRESHOLD",
    "development_metrics",
    "high_stress_metrics",
    "paired_origin_differences",
    "assign_evidence_status",
]

EVIDENCE_STATUSES = (
    "incremental_signal_supported",
    "inconclusive",
    "incremental_signal_not_supported",
)

HIGH_STRESS_THRESHOLD = MT.HIGH_STRESS_SCORE_THRESHOLD  # 85.0, never tuned
SEVERE_THRESHOLD = MT.SEVERE_SCORE_THRESHOLD  # 95.0


def _frame(rows, prediction_key: str):
    """B4's metric functions take a DataFrame with fixed column names."""
    import pandas as pd

    return pd.DataFrame(
        {
            "forecast_origin_month": [r["forecast_origin_month"] for r in rows],
            "industry_id": [r["industry_id"] for r in rows],
            "observed_score": [float(r["observed_score"]) for r in rows],
            "predicted_score": [float(r[prediction_key]) for r in rows],
        }
    )


def development_metrics(rows, prediction_key: str, block_key: str = "block") -> dict:
    """Macro and pooled metrics, computed by B4's own metric functions.

    Macro and pooled are reported SEPARATELY throughout: they coincide only on a
    balanced panel, and reporting one as if it were the other would hide which
    industries carry the error.
    """
    frame = _frame(rows, prediction_key)
    observed = frame["observed_score"].to_numpy(float)
    predicted = frame["predicted_score"].to_numpy(float)

    per_industry = {
        str(industry): MT.mae(
            sub["observed_score"].to_numpy(float),
            sub["predicted_score"].to_numpy(float),
        )
        for industry, sub in frame.groupby("industry_id", observed=True)
    }

    by_block = {}
    blocks = {row.get(block_key) for row in rows if row.get(block_key)}
    for block in sorted(blocks):
        subset = [r for r in rows if r.get(block_key) == block]
        block_frame = _frame(subset, prediction_key)
        by_block[str(block)] = {
            "rows": len(subset),
            "macro_industry_mae": MT.macro_industry_mae(block_frame),
            "pooled_mae": MT.pooled_mae(block_frame),
        }

    absolute_errors = np.abs(observed - predicted)
    return {
        "rows": len(rows),
        "macro_industry_mae": MT.macro_industry_mae(frame),
        "pooled_mae": MT.pooled_mae(frame),
        "macro_industry_rmse": MT.macro_industry_rmse(frame),
        "pooled_rmse": MT.pooled_rmse(frame),
        "median_absolute_error": float(np.median(absolute_errors)),
        "pooled_spearman": MT.spearman_correlation(observed, predicted),
        "per_industry_mae": per_industry,
        "by_block": by_block,
        "clipped_predictions": sum(1 for r in rows if r.get("clipped")),
    }


def high_stress_metrics(rows, prediction_key: str) -> dict:
    """Event metrics at the FIXED score >= 85 threshold.

    The threshold is not tuned. Precision and PR-AUC are reported as ``None``
    when undefined rather than as zero — no predicted events is a different
    fact from every predicted event being wrong.
    """
    observed_event = [
        float(r["observed_score"]) >= HIGH_STRESS_THRESHOLD for r in rows
    ]
    predicted_event = [
        float(r[prediction_key]) >= HIGH_STRESS_THRESHOLD for r in rows
    ]
    pairs = list(zip(observed_event, predicted_event, strict=True))
    true_positive = sum(1 for o, p in pairs if o and p)
    false_positive = sum(1 for o, p in pairs if p and not o)
    false_negative = sum(1 for o, p in pairs if o and not p)

    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive) > 0 else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative) > 0 else None
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )

    # PR-AUC over the continuous score; undefined without a positive case.
    pr_auc = None
    if any(observed_event):
        scores = np.array([float(r[prediction_key]) for r in rows])
        truth = np.array(observed_event, dtype=bool)
        order = np.argsort(-scores, kind="mergesort")
        truth_sorted = truth[order]
        cumulative_tp = np.cumsum(truth_sorted)
        precisions = cumulative_tp / np.arange(1, len(truth_sorted) + 1)
        recalls = cumulative_tp / truth.sum()
        pr_auc = float(np.trapezoid(precisions, recalls)) if len(recalls) > 1 else None

    severe_observed = sum(
        1 for r in rows if float(r["observed_score"]) >= SEVERE_THRESHOLD
    )
    severe_predicted = sum(
        1 for r in rows if float(r[prediction_key]) >= SEVERE_THRESHOLD
    )
    return {
        "threshold": HIGH_STRESS_THRESHOLD,
        "threshold_tuned": False,
        "observed_event_count": int(sum(observed_event)),
        "predicted_event_count": int(sum(predicted_event)),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pr_auc": pr_auc,
        "severe_threshold": SEVERE_THRESHOLD,
        "severe_observed_count": severe_observed,
        "severe_predicted_count": severe_predicted,
    }


def paired_origin_differences(rows, model_key: str, benchmark_key: str) -> dict:
    """Per-origin macro MAE difference. Negative favours the model."""
    differences = {}
    for origin in sorted({r["forecast_origin_month"] for r in rows}):
        subset = [r for r in rows if r["forecast_origin_month"] == origin]
        model_macro = MT.macro_industry_mae(_frame(subset, model_key))
        benchmark_macro = MT.macro_industry_mae(_frame(subset, benchmark_key))
        differences[str(origin)] = {
            "model_macro_mae": model_macro,
            "benchmark_macro_mae": benchmark_macro,
            "difference": model_macro - benchmark_macro,
        }
    values = [item["difference"] for item in differences.values()]
    return {
        "by_origin": differences,
        "origins": len(differences),
        "mean_difference": float(np.mean(values)) if values else None,
        "origins_favouring_model": sum(1 for v in values if v < 0),
        "origins_favouring_benchmark": sum(1 for v in values if v > 0),
    }


def bootstrap_intervals(rows, model_key: str, benchmark_key: str, config: dict) -> dict:
    """Clustered moving-block CIs, using B4's own bootstrap implementation."""
    model_matrix = BS.build_error_matrix(_frame(rows, model_key))
    benchmark_matrix = BS.build_error_matrix(_frame(rows, benchmark_key))
    model_ci = BS.bootstrap_macro_mae_ci(model_matrix, config)
    paired = BS.bootstrap_paired_macro_mae_difference(
        model_matrix, benchmark_matrix, config
    )
    return {
        "replications": int(config["replications"]),
        "block_length_months": int(config["block_length_months"]),
        "seed": int(config["random_seed"]),
        "confidence_level": float(config["confidence_level"]),
        "clustered_by": "forecast_origin_month",
        "industries_kept_together": True,
        "model_macro_mae_ci": model_ci,
        "paired_macro_mae_difference_ci": paired,
    }


def assign_evidence_status(
    model_macro_mae: float, benchmark_macro_mae: float, paired_ci: dict
) -> dict:
    """Apply the preregistered rule. Mechanical, and not open to argument."""
    low = paired_ci.get("ci_low")
    high = paired_ci.get("ci_high")
    lower = model_macro_mae < benchmark_macro_mae

    if not lower:
        status = "incremental_signal_not_supported"
        reason = (
            f"Model macro MAE {model_macro_mae:.4f} is not lower than the "
            f"benchmark's {benchmark_macro_mae:.4f}."
        )
    elif low is not None and high is not None and high < 0:
        status = "incremental_signal_supported"
        reason = (
            f"Model macro MAE {model_macro_mae:.4f} < benchmark "
            f"{benchmark_macro_mae:.4f}, and the paired 95% CI "
            f"[{low:.4f}, {high:.4f}] lies entirely below zero."
        )
    else:
        status = "inconclusive"
        reason = (
            f"Model macro MAE {model_macro_mae:.4f} < benchmark "
            f"{benchmark_macro_mae:.4f}, but the paired 95% CI "
            f"[{low}, {high}] includes zero."
        )
    skill = (
        1.0 - (model_macro_mae / benchmark_macro_mae)
        if benchmark_macro_mae else None
    )
    return {
        "evidence_status": status,
        "reason": reason,
        "model_macro_mae": model_macro_mae,
        "benchmark_macro_mae": benchmark_macro_mae,
        "mae_skill": skill,
        "paired_ci_low": low,
        "paired_ci_high": high,
        "approved_for_locked_test": False,
        "high_stress_or_sensitivity_may_override": False,
    }
