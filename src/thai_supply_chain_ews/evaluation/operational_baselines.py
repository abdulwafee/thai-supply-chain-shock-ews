"""Operational deterministic baselines (Task D3).

These are the release-aware replacements for B4's baselines. Two of B4's
formulas shift by one month because the newest published stress at issue month
*t* is *t-1*, not *t*; the other three are unchanged and are **reused from the
production module** rather than reimplemented, so there is one definition of
each formula in the codebase.

===============================================  ==============================
``operational_persistence_latest_published``     new    ``C_t(S_{t-1})``
``operational_persistence_trailing_3m_max``      new    ``max C_t(S_{t-3..t-1})``
``operational_industry_historical_mean``         reused ``industry_historical_mean``
``operational_seasonal_naive``                   reused ``seasonal_naive``
``operational_no_contraction``                   reused ``no_contraction``
===============================================  ==============================

The reused three need no shift. ``seasonal_naive`` reads *t-11* (h=1) and
*t-11..t-9* (h=3), all of which are at or before *t-1*; ``no_contraction``
reads no month at all; ``industry_historical_mean`` reads labels, which the
availability rule has already gated. Publication is enforced structurally: the
context's stress map contains only months at or before *t-1*, so a baseline that
reaches for *t* raises ``InsufficientHistoryError`` from the shared helper
rather than quietly returning something.

Nothing here is tuned, blended, or weight-averaged.
"""

from __future__ import annotations

from thai_supply_chain_ews.evaluation.baselines import (
    BaselineContext,
    InsufficientHistoryError,
    industry_historical_mean,
    no_contraction,
    seasonal_naive,
)
from thai_supply_chain_ews.evaluation.splits import add_months

__all__ = [
    "OPERATIONAL_BASELINE_NAMES",
    "OPERATIONAL_BASELINES_BY_HORIZON",
    "operational_industry_historical_mean",
    "operational_no_contraction",
    "operational_persistence_latest_published",
    "operational_persistence_trailing_3m_max",
    "operational_seasonal_naive",
    "predict_operational_baseline",
]

OPERATIONAL_BASELINE_NAMES = (
    "operational_persistence_latest_published",
    "operational_persistence_trailing_3m_max",
    "operational_industry_historical_mean",
    "operational_seasonal_naive",
    "operational_no_contraction",
)

#: h=3 carries the latest-published persistence alongside the trailing-3m one,
#: which is why h=3 has five baselines and h=1 has four.
OPERATIONAL_BASELINES_BY_HORIZON = {
    1: (
        "operational_persistence_latest_published",
        "operational_industry_historical_mean",
        "operational_seasonal_naive",
        "operational_no_contraction",
    ),
    3: (
        "operational_persistence_latest_published",
        "operational_persistence_trailing_3m_max",
        "operational_industry_historical_mean",
        "operational_seasonal_naive",
        "operational_no_contraction",
    ),
}


def _transform(context: BaselineContext, raw_value: float) -> float:
    return float(context.calibrator.transform(context.industry_id, float(raw_value))[0])


def _require_month(context: BaselineContext, month: str, baseline: str) -> float:
    raw = context.raw_stress_by_month.get(month)
    if raw is None:
        raise InsufficientHistoryError(
            f"{baseline}: stress month {month} is not available for "
            f"{context.industry_id} at issue month {context.origin}. The operational "
            "stress map holds only months published by the issue date."
        )
    return float(raw)


def operational_persistence_latest_published(context: BaselineContext):
    """``C_t(S_{t-1})`` — the newest month OIE has actually published.

    Deliberately does NOT read ``S_t``. At issue month *t* that value does not
    exist yet, which is the defect this whole contract exists to remove.
    """
    month = add_months(context.origin, -1)
    raw = _require_month(context, month, "operational_persistence_latest_published")
    return float(raw), _transform(context, raw)


def operational_persistence_trailing_3m_max(context: BaselineContext):
    """``max{C_t(S_{t-3}), C_t(S_{t-2}), C_t(S_{t-1})}``.

    All three months must be published by the issue date; a missing one raises
    rather than shrinking the window to whatever happens to be present.
    """
    months = [add_months(context.origin, k) for k in (-3, -2, -1)]
    raws = [
        _require_month(context, month, "operational_persistence_trailing_3m_max")
        for month in months
    ]
    scores = [_transform(context, raw) for raw in raws]
    return float(max(raws)), float(max(scores))


def operational_industry_historical_mean(context: BaselineContext):
    """Reuses the production formula; industries are never pooled."""
    return industry_historical_mean(context)


def operational_seasonal_naive(context: BaselineContext):
    """Reuses the production formula.

    h=1 reads *t-11*; h=3 reads *t-11..t-9*. Both are at or before *t-1*, so the
    B4 formula remains applicable unchanged.
    """
    return seasonal_naive(context)


def operational_no_contraction(context: BaselineContext):
    """Reuses the production formula: predict raw zero, then calibrate it."""
    return no_contraction(context)


_DISPATCH = {
    "operational_persistence_latest_published": operational_persistence_latest_published,
    "operational_persistence_trailing_3m_max": operational_persistence_trailing_3m_max,
    "operational_industry_historical_mean": operational_industry_historical_mean,
    "operational_seasonal_naive": operational_seasonal_naive,
    "operational_no_contraction": operational_no_contraction,
}


def predict_operational_baseline(name: str, context: BaselineContext):
    if name not in _DISPATCH:
        raise KeyError(f"Unknown operational baseline: {name}")
    return _DISPATCH[name](context)
