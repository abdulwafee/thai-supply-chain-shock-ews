"""Deterministic baselines (Task B4).

These are not models. They are the floor a future ML model must clear to justify
its complexity, and they run under exactly the same walk-forward information
constraints a real model would face: every baseline receives only the calibrator
frozen at the current origin and only history the origin permits.

None of them is tuned, searched, or blended. Tuning a benchmark quietly consumes
development data and blurs the line between "floor" and "model".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from thai_supply_chain_ews.evaluation.splits import add_months

__all__ = [
    "BaselineContext",
    "InsufficientHistoryError",
    "DEFAULT_BASELINE_CONFIG_PATH",
    "BASELINE_NAMES",
    "industry_historical_mean",
    "load_baseline_config",
    "no_contraction",
    "persistence_current_month",
    "persistence_trailing_3m_max",
    "predict_baseline",
    "seasonal_naive",
]

DEFAULT_BASELINE_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "baselines.yaml"
)

BASELINE_NAMES = (
    "persistence_current_month",
    "persistence_trailing_3m_max",
    "industry_historical_mean",
    "seasonal_naive",
    "no_contraction",
)


class InsufficientHistoryError(ValueError):
    """A baseline lacks the history it needs for this industry and origin.

    Raised rather than silently falling back to a pooled or cross-industry
    value — a quiet fallback would make the benchmark look better than the
    information available actually allows.
    """


def load_baseline_config(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else DEFAULT_BASELINE_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Baseline config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class BaselineContext:
    """Everything a baseline is allowed to see at one forecast origin.

    `raw_stress_by_month` contains only months <= origin, and `training_scores`
    only labels whose target window closed at or before the origin. The
    calibrator is already fitted and frozen.
    """

    origin: str
    industry_id: str
    horizon: int
    calibrator: object
    raw_stress_by_month: dict[str, float]
    training_scores: list[float]


def _transform(context: BaselineContext, raw_value: float) -> float:
    return float(context.calibrator.transform(context.industry_id, float(raw_value))[0])


def persistence_current_month(context: BaselineContext) -> tuple[float | None, float]:
    """Predict that future stress equals the origin month's calibrated stress."""
    raw = context.raw_stress_by_month.get(context.origin)
    if raw is None:
        raise InsufficientHistoryError(
            f"persistence_current_month: no stress observation at origin {context.origin} "
            f"for {context.industry_id}"
        )
    return float(raw), _transform(context, raw)


def persistence_trailing_3m_max(context: BaselineContext) -> tuple[float | None, float]:
    """Maximum calibrated monthly stress over t-2, t-1, t.

    The maximum is taken over CALIBRATED scores, matching the config's stated
    rule. Because the calibrator is monotone this equals the score of the raw
    maximum, but the raw maximum is still reported as the predicted raw value.
    """
    months = [add_months(context.origin, k) for k in (-2, -1, 0)]
    missing = [m for m in months if m not in context.raw_stress_by_month]
    if missing:
        raise InsufficientHistoryError(
            f"persistence_trailing_3m_max: missing stress month(s) {missing} for "
            f"{context.industry_id} at origin {context.origin}"
        )
    raws = [context.raw_stress_by_month[m] for m in months]
    scores = [_transform(context, r) for r in raws]
    return float(max(raws)), float(max(scores))


def industry_historical_mean(context: BaselineContext) -> tuple[float | None, float]:
    """Mean calibrated target score across this industry's completed labels.

    Industries are never pooled. If this industry has no completed labels for
    this horizon, that is an error, not an invitation to borrow another
    industry's history.
    """
    if not context.training_scores:
        raise InsufficientHistoryError(
            f"industry_historical_mean: no completed training labels for "
            f"{context.industry_id} h={context.horizon} at origin {context.origin}"
        )
    return None, float(np.mean(context.training_scores))


def seasonal_naive(context: BaselineContext) -> tuple[float | None, float]:
    """Last year's raw stress for the corresponding target window.

    h=1: the target month shifted back 12 months.
    h=3: the maximum over the t+1..t+3 window shifted back 12 months.
    Every source month is <= origin by construction (t+3-12 = t-9 <= t), and
    that is asserted rather than assumed.
    """
    if context.horizon == 1:
        offsets = [1]
    else:
        offsets = [1, 2, 3]
    source_months = [add_months(context.origin, o - 12) for o in offsets]

    late = [m for m in source_months if m > context.origin]
    if late:
        raise InsufficientHistoryError(
            f"seasonal_naive: source month(s) {late} are after origin {context.origin}"
        )
    missing = [m for m in source_months if m not in context.raw_stress_by_month]
    if missing:
        raise InsufficientHistoryError(
            f"seasonal_naive: missing stress month(s) {missing} for {context.industry_id} "
            f"at origin {context.origin}"
        )
    raw = max(context.raw_stress_by_month[m] for m in source_months)
    return float(raw), _transform(context, raw)


def no_contraction(context: BaselineContext) -> tuple[float | None, float]:
    """Predict zero year-over-year contraction, then calibrate that zero."""
    return 0.0, _transform(context, 0.0)


_DISPATCH = {
    "persistence_current_month": persistence_current_month,
    "persistence_trailing_3m_max": persistence_trailing_3m_max,
    "industry_historical_mean": industry_historical_mean,
    "seasonal_naive": seasonal_naive,
    "no_contraction": no_contraction,
}


def predict_baseline(name: str, context: BaselineContext) -> tuple[float | None, float]:
    if name not in _DISPATCH:
        raise KeyError(f"Unknown baseline: {name}")
    return _DISPATCH[name](context)
