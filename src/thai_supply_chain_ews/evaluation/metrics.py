"""Regression and early-warning evaluation metrics.

Pure, dependency-light functions (numpy only — no scikit-learn/scipy
dependency added for this) implementing the metric list from
docs/project_roadmap.md §4. These are deterministic formulas, not model
training, so they are implemented now rather than stubbed.

All functions operate on 1-D array-likes of equal length and ignore NaNs
pairwise unless noted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def mae(y_true, y_pred) -> float:
    """Mean absolute error."""
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    return float(np.nanmean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> float:
    """Root mean squared error."""
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.nanmean((y_true - y_pred) ** 2)))


def spearman_correlation(y_true, y_pred) -> float:
    """Spearman rank correlation, computed without a scipy dependency.

    Implemented as the Pearson correlation of the rank-transformed inputs
    (the standard equivalent definition). Returns NaN if either input has
    zero variance in rank (e.g., all values tied).
    """
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) < 2:
        return float("nan")
    rank_true = _rank_average_ties(y_true)
    rank_pred = _rank_average_ties(y_pred)
    if np.std(rank_true) == 0 or np.std(rank_pred) == 0:
        return float("nan")
    return float(np.corrcoef(rank_true, rank_pred)[0, 1])


def _rank_average_ties(values: np.ndarray) -> np.ndarray:
    """Average ranks (1-based), ties averaged — no pandas/scipy dependency."""
    order = values.argsort(kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    sorted_vals = values[order]
    i = 0
    while i < len(sorted_vals):
        j = i
        while j + 1 < len(sorted_vals) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg_rank
        i = j + 1
    return ranks


_RISK_LEVELS = ("Normal", "Watch", "High", "Severe")


def recall_precision_for_levels(
    y_true, y_pred, positive_levels: tuple[str, ...] = ("High", "Severe")
) -> dict[str, float]:
    """Recall and precision for a combined positive class (e.g. {High, Severe}).

    y_true / y_pred are array-likes of risk-level strings from _RISK_LEVELS.
    """
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    true_positive_class = np.isin(y_true, positive_levels)
    pred_positive_class = np.isin(y_pred, positive_levels)

    tp = int(np.sum(true_positive_class & pred_positive_class))
    fn = int(np.sum(true_positive_class & ~pred_positive_class))
    fp = int(np.sum(~true_positive_class & pred_positive_class))

    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    return {"recall": recall, "precision": precision, "tp": tp, "fp": fp, "fn": fn}


def macro_f1(y_true, y_pred, levels: tuple[str, ...] = _RISK_LEVELS) -> float:
    """Macro-averaged F1 across all risk levels (unweighted mean of per-class F1)."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    f1_scores = []
    for level in levels:
        tp = int(np.sum((y_true == level) & (y_pred == level)))
        fp = int(np.sum((y_true != level) & (y_pred == level)))
        fn = int(np.sum((y_true == level) & (y_pred != level)))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        f1_scores.append(f1)
    return float(np.mean(f1_scores))


def false_alert_rate(
    y_true, y_pred, alert_levels: tuple[str, ...] = ("Watch", "High", "Severe")
) -> float:
    """Fraction of actually-Normal rows for which the model raised any alert level."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    actually_normal = y_true == "Normal"
    if not np.any(actually_normal):
        return float("nan")
    alerted = np.isin(y_pred[actually_normal], alert_levels)
    return float(np.mean(alerted))


def missed_event_rate(
    y_true,
    y_pred,
    event_levels: tuple[str, ...] = ("Severe",),
    missed_predictions: tuple[str, ...] = ("Normal", "Watch"),
) -> float:
    """Fraction of actual Severe (by default) rows the model predicted as Normal/Watch."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    actual_event = np.isin(y_true, event_levels)
    if not np.any(actual_event):
        return float("nan")
    missed = np.isin(y_pred[actual_event], missed_predictions)
    return float(np.mean(missed))


# --- Task B4: score-based evaluation metrics ---------------------------------
# Appended. The risk-level functions above operate on categorical labels and are
# unchanged; what follows works on the 0-100 Industry Production Stress Score.
#
# MACRO vs POOLED is a real distinction, not a formatting choice: macro computes
# each industry's error first and then averages the 12 equally, so a single
# volatile industry cannot dominate model selection. Pooled averages all rows
# together and is reported alongside, never instead.

HIGH_STRESS_SCORE_THRESHOLD = 85.0
SEVERE_SCORE_THRESHOLD = 95.0


def macro_industry_mae(
    frame: pd.DataFrame,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
    industry_column: str = "industry_id",
) -> float:
    """PRIMARY model-selection metric: mean of per-industry MAEs, equally weighted."""
    if frame.empty:
        return float("nan")
    per_industry = [
        mae(sub[observed_column].to_numpy(float), sub[predicted_column].to_numpy(float))
        for _, sub in frame.groupby(industry_column, observed=True)
    ]
    return float(np.mean(per_industry)) if per_industry else float("nan")


def pooled_mae(
    frame: pd.DataFrame,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
) -> float:
    if frame.empty:
        return float("nan")
    return mae(
        frame[observed_column].to_numpy(float), frame[predicted_column].to_numpy(float)
    )


def macro_industry_rmse(
    frame: pd.DataFrame,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
    industry_column: str = "industry_id",
) -> float:
    if frame.empty:
        return float("nan")
    per_industry = [
        rmse(sub[observed_column].to_numpy(float), sub[predicted_column].to_numpy(float))
        for _, sub in frame.groupby(industry_column, observed=True)
    ]
    return float(np.mean(per_industry)) if per_industry else float("nan")


def pooled_rmse(
    frame: pd.DataFrame,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
) -> float:
    if frame.empty:
        return float("nan")
    return rmse(
        frame[observed_column].to_numpy(float), frame[predicted_column].to_numpy(float)
    )


def median_absolute_error(
    frame: pd.DataFrame,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
) -> float:
    if frame.empty:
        return float("nan")
    errors = np.abs(
        frame[observed_column].to_numpy(float) - frame[predicted_column].to_numpy(float)
    )
    return float(np.median(errors))


def per_industry_mae(
    frame: pd.DataFrame,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
    industry_column: str = "industry_id",
) -> dict[str, float]:
    return {
        str(industry_id): mae(
            sub[observed_column].to_numpy(float), sub[predicted_column].to_numpy(float)
        )
        for industry_id, sub in frame.groupby(industry_column, observed=True)
    }


def high_stress_event_metrics(
    frame: pd.DataFrame,
    threshold: float = HIGH_STRESS_SCORE_THRESHOLD,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
) -> dict:
    """Precision/recall/F1/PR-AUC for `score >= threshold`.

    PR-AUC is reported as None with an explicit reason when it is not
    mathematically defined (no positive observations), rather than silently
    emitted as 0.0 — a fabricated 0.0 would read as a real, poor score.
    """
    observed = frame[observed_column].to_numpy(float) >= threshold
    predicted = frame[predicted_column].to_numpy(float) >= threshold

    true_positive = int(np.sum(observed & predicted))
    false_positive = int(np.sum(~observed & predicted))
    false_negative = int(np.sum(observed & ~predicted))

    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive) > 0
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative) > 0
        else None
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )

    pr_auc, pr_auc_reason = _average_precision(
        observed, frame[predicted_column].to_numpy(float)
    )

    return {
        "threshold": threshold,
        "observed_events": int(np.sum(observed)),
        "predicted_events": int(np.sum(predicted)),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pr_auc": pr_auc,
        "pr_auc_undefined_reason": pr_auc_reason,
    }


def _average_precision(observed: np.ndarray, scores: np.ndarray) -> tuple[float | None, str | None]:
    """Average precision over descending score thresholds.

    Returns (None, reason) when undefined instead of a misleading number.
    """
    positives = int(np.sum(observed))
    if positives == 0:
        return None, "no observed positive events — PR-AUC is undefined"
    if len(observed) < 2:
        return None, "fewer than two observations"
    order = np.argsort(-scores, kind="mergesort")
    ordered = observed[order]
    cumulative_tp = np.cumsum(ordered)
    ranks = np.arange(1, len(ordered) + 1)
    precision_at_k = cumulative_tp / ranks
    return float(np.sum(precision_at_k * ordered) / positives), None


def severe_event_counts(
    frame: pd.DataFrame,
    threshold: float = SEVERE_SCORE_THRESHOLD,
    observed_column: str = "observed_score",
    predicted_column: str = "predicted_score",
) -> dict:
    """Descriptive counts only — too few events for stable rate metrics."""
    observed = frame[observed_column].to_numpy(float) >= threshold
    predicted = frame[predicted_column].to_numpy(float) >= threshold
    return {
        "threshold": threshold,
        "observed_events": int(np.sum(observed)),
        "predicted_events": int(np.sum(predicted)),
        "both": int(np.sum(observed & predicted)),
        "reporting": "descriptive_counts_only",
        "note": "Too few events for stable rate metrics; not used for selection.",
    }


def mae_skill(model_mae: float, reference_mae: float) -> float:
    """skill = 1 - model_mae / reference_mae. Positive means better than reference."""
    if reference_mae is None or reference_mae == 0 or np.isnan(reference_mae):
        return float("nan")
    return float(1.0 - model_mae / reference_mae)
