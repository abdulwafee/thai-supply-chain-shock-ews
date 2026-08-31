"""Operational feature/target assembly for the D4 model (Task D4).

D1 assembled its training rows on the calendar-boundary contract: stress month
*t* was readable at origin *t*. D3 established that OIE does not publish month
*t* until month *t+1*, so this module rebuilds the assembly under the
release-aware contract. Three cutoffs move together and are enforced separately:

===================  ======================================================
calibrator           ``stress_month <= t-1``
training labels      ``target_available_month <= t``
historical features  ``conditioned_available_month <= u``  (u, **not** t)
===================  ======================================================

The third is the subtle one and it is unchanged from D1's hardest lesson: a
training row belonging to historical origin *u* must carry only what was known
at *u*. Refreshing it with everything known at the outer origin *t* would make
the model learn from a version of history that never existed.

The benchmark also moves. At historical origin *u* the operational persistence
prediction may read stress only up to *u-1*, mirroring what the live benchmark
could see — so the residual the model learns is a residual against a benchmark
that was actually achievable, not a hindsight one.

Every violation raises. Nothing is silently dropped, because a silently dropped
row is indistinguishable from a row that never existed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from thai_supply_chain_ews.evaluation.operational_availability import (
    available_training_labels,
    target_available_month,
)
from thai_supply_chain_ews.evaluation.splits import add_months
from thai_supply_chain_ews.modeling.feature_target_assembly import (
    FutureFeatureError,
    features_as_of,
)

__all__ = [
    "OperationalAssemblyError",
    "OperationalTrainingMatrix",
    "assemble_operational_training",
    "historical_benchmark_raw",
    "operational_label_origins",
]


class OperationalAssemblyError(ValueError):
    """A temporal or structural rule of the operational assembly was violated."""


def operational_label_origins(labels, outer_origin: str, horizon: int) -> list:
    """Historical origins whose labels are published by the outer issue month."""
    horizon_labels = labels[labels["horizon_months"] == horizon]
    permitted = available_training_labels(horizon_labels, outer_origin)
    origins = sorted({str(o) for o in permitted["forecast_origin_month"]})
    for origin in origins:
        if origin >= outer_origin:
            raise OperationalAssemblyError(
                f"training origin {origin} is not before the outer issue origin "
                f"{outer_origin}"
            )
    return origins


def historical_benchmark_raw(stress_by_month: dict, origin: str, horizon: int):
    """Reconstruct the D3 operational persistence benchmark at origin ``u``.

    h=1 reads ``S_{u-1}``; h=3 reads ``max(S_{u-3}, S_{u-2}, S_{u-1})``. Every
    month is strictly before ``u``, which is what makes this the benchmark the
    live system could actually have produced at that moment.

    Returns ``None`` when a required month falls **before B3's stress series
    begins**. That is a series-start boundary, not a release-timing violation,
    and the two are kept apart: a month at or after ``u`` still raises, because
    that would be the model reading the future.
    """
    if int(horizon) not in (1, 3):
        raise OperationalAssemblyError(
            f"unsupported horizon {horizon}; D4 evaluates h=1 and h=3 only"
        )
    offsets = (-1,) if int(horizon) == 1 else (-3, -2, -1)
    months = [add_months(origin, offset) for offset in offsets]
    # Defence in depth: the offsets above are all negative, so this cannot fire
    # from inside this function. It fires if a future caller supplies its own
    # offsets, and it is cheaper to keep than to rediscover.
    late = [m for m in months if m >= origin]
    if late:
        raise OperationalAssemblyError(
            f"historical benchmark at {origin} would read unpublished month(s) {late}"
        )
    if not stress_by_month:
        return None
    series_start = min(stress_by_month)
    before_start = [m for m in months if m < series_start]
    if before_start:
        return None
    missing = [m for m in months if m not in stress_by_month]
    if missing:
        raise OperationalAssemblyError(
            f"historical benchmark at {origin} is missing stress month(s) {missing} "
            "inside the series range"
        )
    return float(max(stress_by_month[m] for m in months))


@dataclass
class OperationalTrainingMatrix:
    industry_id: str
    horizon: int
    outer_origin: str
    predictor_names: tuple
    matrix: np.ndarray
    residuals: np.ndarray
    training_origins: tuple
    label_permitted_rows: int
    feature_usable_rows: int
    excluded_origins: tuple = ()
    excluded_reason: str = "insufficient_registered_feature_history"
    excluded_benchmark_origins: tuple = ()
    excluded_benchmark_reason: str = "insufficient_operational_benchmark_history"
    omitted_ineligible: tuple = ()
    max_training_target_window_end: str = None
    max_training_target_available_month: str = None
    diagnostics: dict = field(default_factory=dict)


def assemble_operational_training(
    index,
    labels_by_key: dict,
    permitted_origins,
    industry_id: str,
    horizon: int,
    outer_origin: str,
    calibrator,
    stress_by_month: dict,
    non_ferrous_channel: str = "none",
) -> OperationalTrainingMatrix:
    """Build one industry's operational residual training set at outer origin *t*.

    ``labels_by_key[(origin, industry, horizon)]`` supplies the B3 **raw** target
    value, which is reused unchanged; only the calibration applied to it belongs
    to D4. Both the historical target and the historical benchmark are expressed
    through the SAME calibrator frozen at *t-1* — a residual computed across two
    different scales would not be a residual.
    """
    if non_ferrous_channel != "none":
        raise OperationalAssemblyError(
            f"D4 is frozen to nonferrous_channel='none'; got {non_ferrous_channel!r}"
        )

    rows, residuals, used_origins = [], [], []
    excluded_feature, excluded_benchmark = [], []
    names = None
    omitted_ineligible = ()
    label_permitted = 0
    window_ends, available_months = [], []

    for origin in permitted_origins:
        key = (origin, industry_id, int(horizon))
        label = labels_by_key.get(key)
        if label is None:
            continue
        label_permitted += 1

        window_end = str(label["target_window_end"])
        available = target_available_month(window_end)
        if available > outer_origin:
            raise OperationalAssemblyError(
                f"training label at origin {origin} (h={horizon}) becomes available "
                f"{available}, after the outer issue origin {outer_origin}"
            )
        window_ends.append(window_end)
        available_months.append(available)

        # Features frozen at u. features_as_of filters on availability <= u, so
        # the outer origin cannot leak in through this call.
        vector = features_as_of(
            index, origin, industry_id, non_ferrous_channel=non_ferrous_channel
        )
        if not vector:
            excluded_feature.append(origin)
            continue

        # `features_as_of` selects on `conditioned_available_month <= origin`,
        # so the freeze at *u* is enforced inside the index rather than here.
        # What this level can still check is that the row it handed back really
        # describes months at or before its own origin.
        for predictor, reference in vector["reference_months"].items():
            if reference and str(reference) > origin:
                raise FutureFeatureError(
                    f"historical feature {predictor} for {industry_id} at {origin} "
                    f"describes reference month {reference}, after its own origin"
                )

        if names is None:
            names = tuple(vector["predictor_names"])
            omitted_ineligible = tuple(vector["omitted_ineligible_predictors"])
        elif tuple(vector["predictor_names"]) != names:
            raise OperationalAssemblyError(
                f"{industry_id}: predictor set changed between origins "
                f"({names} vs {tuple(vector['predictor_names'])})"
            )

        benchmark_raw = historical_benchmark_raw(stress_by_month, origin, horizon)
        if benchmark_raw is None:
            # The operational benchmark window reaches before B3's stress
            # series begins, so no achievable benchmark exists at this origin
            # and no residual can be defined against one.
            excluded_benchmark.append(origin)
            continue

        target_score = float(
            calibrator.transform(industry_id, float(label["target_raw_value"]))[0]
        )
        benchmark_score = float(calibrator.transform(industry_id, benchmark_raw)[0])

        rows.append([float(v) for v in vector["values"]])
        residuals.append(target_score - benchmark_score)
        used_origins.append(origin)

    if names is None:
        raise OperationalAssemblyError(
            f"{industry_id} h={horizon} at {outer_origin}: no feature-usable "
            "training rows"
        )

    return OperationalTrainingMatrix(
        industry_id=industry_id,
        horizon=int(horizon),
        outer_origin=outer_origin,
        predictor_names=names,
        matrix=np.array(rows, dtype=float),
        residuals=np.array(residuals, dtype=float),
        training_origins=tuple(used_origins),
        label_permitted_rows=label_permitted,
        feature_usable_rows=len(rows),
        excluded_origins=tuple(sorted(set(excluded_feature))),
        excluded_benchmark_origins=tuple(sorted(set(excluded_benchmark))),
        omitted_ineligible=omitted_ineligible,
        max_training_target_window_end=max(window_ends) if window_ends else None,
        max_training_target_available_month=(
            max(available_months) if available_months else None
        ),
    )
