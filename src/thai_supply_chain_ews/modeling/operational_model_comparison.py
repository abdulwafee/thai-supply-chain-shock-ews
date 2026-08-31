"""Metrics, uncertainty and the two D4 decisions (Task D4).

Two statuses are assigned per horizon and they are deliberately **separate**:

* **MAE evidence** — is the model more accurate on average, and is that
  difference distinguishable from zero given only 15 origin clusters?
* **Event safety** — does the model miss more high-stress events than the
  benchmark it is meant to improve on?

A model can win the first and lose the second. Merging them into one verdict
would hide exactly that trade-off, and for an early-warning system a missed
high-stress month is the expensive error. Advancement therefore requires
**both**, and no sensitivity variant can rescue a failed primary.

The bootstrap clusters by issue month and keeps all 12 industries together,
because 180 rows are 15 dependent clusters, not 180 independent observations.
"""

from __future__ import annotations

from thai_supply_chain_ews.evaluation import bootstrap as BS
from thai_supply_chain_ews.evaluation import metrics as MT

__all__ = [
    "EVENT_SAFETY_STATUSES",
    "MAE_EVIDENCE_STATUSES",
    "advancement_decision",
    "assign_event_safety",
    "assign_mae_evidence",
    "compare_against_comparators",
    "describe_frame",
]

MAE_EVIDENCE_STATUSES = (
    "incremental_signal_supported",
    "incremental_signal_inconclusive",
    "incremental_signal_not_supported",
)

EVENT_SAFETY_STATUSES = ("event_safety_passed", "event_safety_failed")


def describe_frame(frame, threshold: float = 85.0, severe: float = 95.0) -> dict:
    """Full metric block for one prediction frame."""
    return {
        "rows": int(len(frame)),
        "macro_industry_mae": MT.macro_industry_mae(frame),
        "pooled_mae": MT.pooled_mae(frame),
        "macro_industry_rmse": MT.macro_industry_rmse(frame),
        "pooled_rmse": MT.pooled_rmse(frame),
        "median_absolute_error": MT.median_absolute_error(frame),
        "pooled_spearman": MT.spearman_correlation(
            frame["observed_score"].to_numpy(float),
            frame["predicted_score"].to_numpy(float),
        ),
        "per_industry_mae": MT.per_industry_mae(frame),
        "by_development_block": {
            str(block): MT.macro_industry_mae(sub)
            for block, sub in frame.groupby("split_name", observed=True)
        },
        "clipped_prediction_count": (
            int(frame["clipped"].sum()) if "clipped" in frame.columns else 0
        ),
        "high_stress": MT.high_stress_event_metrics(frame, threshold=threshold),
        "severe_counts": MT.severe_event_counts(frame, threshold=severe),
    }


def assign_mae_evidence(model_mae: float, benchmark_mae: float, paired: dict) -> str:
    """Lower MAE alone is not support; the interval has to exclude zero.

    ``paired`` is the bootstrap of ``model - benchmark``, so a negative point
    estimate means the model is better and support requires the whole interval
    to sit below zero.
    """
    if model_mae >= benchmark_mae:
        return "incremental_signal_not_supported"
    if paired["ci_high"] < 0.0:
        return "incremental_signal_supported"
    return "incremental_signal_inconclusive"


def assign_event_safety(model_false_negatives: int, benchmark_false_negatives: int) -> str:
    if int(model_false_negatives) <= int(benchmark_false_negatives):
        return "event_safety_passed"
    return "event_safety_failed"


def compare_against_comparators(model_frame, benchmark_frame, config, seed_offset: int = 0):
    """Model versus one comparator: metrics, paired interval, skill interval."""
    bootstrap_config = config["bootstrap"]
    model_matrix = BS.build_error_matrix(model_frame)
    benchmark_matrix = BS.build_error_matrix(benchmark_frame)
    paired = BS.bootstrap_paired_macro_mae_difference(
        model_matrix, benchmark_matrix, bootstrap_config, seed_offset=seed_offset
    )
    model_mae = MT.macro_industry_mae(model_frame)
    benchmark_mae = MT.macro_industry_mae(benchmark_frame)
    return {
        "model_macro_mae": model_mae,
        "comparator_macro_mae": benchmark_mae,
        "mae_skill": MT.mae_skill(model_mae, benchmark_mae),
        "paired_difference_model_minus_comparator": paired,
        "paired_sign_convention": "negative means the model is better",
        "model_better_on_point_estimate": model_mae < benchmark_mae,
        "paired_ci_excludes_zero": bool(
            paired["ci_high"] < 0.0 or paired["ci_low"] > 0.0
        ),
    }


def advancement_decision(mae_status: str, event_status: str) -> dict:
    """Both gates must pass. Neither result opens the locked test."""
    supported = (
        mae_status == "incremental_signal_supported"
        and event_status == "event_safety_passed"
    )
    return {
        "mae_evidence_status": mae_status,
        "event_safety_status": event_status,
        "development_candidate_supported": supported,
        "requires_both_gates": True,
        "sensitivity_may_rescue_failed_primary": False,
        # Unconditional, whatever the two gates said.
        "approved_for_locked_test": False,
        "production_model_approved": False,
        "confirmatory_result": False,
    }
