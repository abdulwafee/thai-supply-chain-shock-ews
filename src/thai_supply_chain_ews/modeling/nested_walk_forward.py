"""Nested walk-forward selection and outer prediction — Task D1.

Two nested loops, and the whole point is that the inner one never sees anything
the outer origin has not already permitted.

**Outer**: for each development origin *t* and horizon *h*, fit a fresh
calibrator on ``stress_month <= t``, assemble training rows under the label and
feature gates, fit one ridge per industry, and predict. The target belonging to
*t* is read only after the prediction is frozen.

**Inner**: at each inner validation origin *v* inside the outer training window,
fit a SEPARATE calibrator on ``stress_month <= v``. Reusing the outer
calibrator inside inner validation would leak the outer origin's distribution
into every inner score — the selection would then be made with information the
inner fold was supposed not to have.

Selection is over at most 12 registered configurations: 4 alphas x 3 non-ferrous
channels. Outcome-based selection is permitted **here and only here** — inside
the nested procedure, on inner folds. It never reaches back into C2 source
eligibility, C3 exposure eligibility, or C4 feature generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from thai_supply_chain_ews.modeling.feature_target_assembly import (
    NON_FERROUS_CHANNELS,
    assemble_training_matrix,
    features_as_of,
    label_permitted_origins,
)
from thai_supply_chain_ews.modeling.residual_ridge import (
    RidgeError,
    fit_ridge_residual,
)

__all__ = [
    "SelectionError",
    "InsufficientInnerHistoryError",
    "RIDGE_ALPHA_GRID",
    "MIN_INNER_TRAINING_ORIGINS",
    "MIN_INNER_VALIDATION_ORIGINS_FOR_SELECTION",
    "MAE_TIE_TOLERANCE",
    "Configuration",
    "registered_configurations",
    "select_configuration",
    "fit_and_predict_origin",
]

# Preregistered grid. Not widened, and not re-searched if the result disappoints.
RIDGE_ALPHA_GRID: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)
MIN_INNER_TRAINING_ORIGINS = 12
MAE_TIE_TOLERANCE = 1e-6

# Preregistered fallback. B3's monthly stress begins 2022-01, so a calibrator
# meeting the 24-observation minimum cannot exist before 2023-12 — which leaves
# too few inner validation origins at the earliest outer origins. Rather than
# weaken the calibrator guard to manufacture inner folds, D1 falls back to the
# most regularized, smallest configuration. That shrinks the residual toward
# zero and pulls the model toward the benchmark, so the fallback can only make
# the model look worse, never better.
MIN_INNER_VALIDATION_ORIGINS_FOR_SELECTION = 3
FALLBACK_CONFIGURATION_ALPHA = 100.0
FALLBACK_CONFIGURATION_CHANNEL = "none"


class SelectionError(ValueError):
    """Model selection could not proceed as specified."""


class InsufficientInnerHistoryError(SelectionError):
    """Not enough inner history exists to validate a configuration."""


@dataclass(frozen=True)
class Configuration:
    """One registered (alpha, non-ferrous channel) combination."""

    alpha: float
    non_ferrous_channel: str

    @property
    def configuration_id(self) -> str:
        return f"alpha={self.alpha!r}|metal={self.non_ferrous_channel}"


def registered_configurations() -> tuple[Configuration, ...]:
    """The at-most-12 registered configurations, in a fixed deterministic order."""
    return tuple(
        Configuration(alpha=alpha, non_ferrous_channel=channel)
        for channel in NON_FERROUS_CHANNELS
        for alpha in RIDGE_ALPHA_GRID
    )


def _matrix_from_rows(rows, names):
    return np.array(
        [[row["features"]["values"][row["features"]["predictor_names"].index(n)]
          for n in names] for row in rows],
        dtype=float,
    )


def _residual_design(
    index, labels_by_key, calibrator, benchmark_fn, industry_id, horizon,
    channel, cutoff_origin, permitted_origins, cache,
):
    """Assemble and compute residuals once per (industry, horizon, cutoff, channel).

    The design does not depend on alpha, so it is shared across the four alphas
    of a configuration sweep. The calibrator is keyed by cutoff, so a cached
    design can never carry another origin's scale.
    """
    key = (industry_id, int(horizon), cutoff_origin, channel)
    if key in cache:
        return cache[key]
    assembly = assemble_training_matrix(
        index, labels_by_key, permitted_origins, industry_id, horizon,
        channel, cutoff_origin,
    )
    rows = assembly["rows"]
    residuals, kept = [], []
    for row in rows:
        raw = float(row["label"]["target_raw_value"])
        # Historical target and historical benchmark BOTH expressed on the
        # calibrator frozen at this cutoff — a residual computed across two
        # different scales would not be a residual.
        observed = calibrator.transform(industry_id, raw)[0]
        benchmark = benchmark_fn(industry_id, row["origin"], horizon, calibrator)
        if benchmark is None:
            continue
        residuals.append(float(observed) - float(benchmark))
        kept.append(row)
    result = (assembly, kept, residuals)
    cache[key] = result
    return result


def _fit_industry(
    index, labels_by_key, calibrator, benchmark_fn, industry_id, horizon,
    configuration, cutoff_origin, permitted_origins, design_cache=None,
):
    """Assemble, compute residuals on the frozen scale, and fit one industry."""
    cache = design_cache if design_cache is not None else {}
    assembly, kept, residuals = _residual_design(
        index, labels_by_key, calibrator, benchmark_fn, industry_id, horizon,
        configuration.non_ferrous_channel, cutoff_origin, permitted_origins, cache,
    )
    if len(kept) < 2:
        return None, assembly

    names = kept[0]["features"]["predictor_names"]
    matrix = _matrix_from_rows(kept, names)
    try:
        model = fit_ridge_residual(
            industry_id, horizon, names, matrix, np.array(residuals, dtype=float),
            configuration.alpha, configuration.non_ferrous_channel,
            omitted_ineligible=kept[0]["features"]["omitted_ineligible_predictors"],
        )
    except RidgeError:
        return None, assembly
    assembly["training_rows_used"] = len(kept)
    return model, assembly


def select_configuration(
    index, labels_by_key, industries, horizon, outer_origin,
    inner_origins, calibrator_factory, benchmark_fn, label_lookup,
    configurations=None,
):
    """Choose (alpha, channel) by expanding inner walk-forward validation.

    The channel choice is GLOBAL across all 12 industries for this outer origin
    and horizon, so a single structural assumption is not varied industry by
    industry to flatter the score.
    """
    configurations = configurations or registered_configurations()
    design_cache: dict = {}
    inner_calibrators: dict = {}
    permitted_cache: dict = {}
    if len(inner_origins) < MIN_INNER_VALIDATION_ORIGINS_FOR_SELECTION:
        # Too little evidence to select on. Use the conservative fallback and
        # say so, rather than selecting on one or two noisy folds.
        return {
            "selected": Configuration(
                alpha=FALLBACK_CONFIGURATION_ALPHA,
                non_ferrous_channel=FALLBACK_CONFIGURATION_CHANNEL,
            ),
            "selection_reason": "insufficient_inner_history_conservative_fallback",
            "selected_inner_macro_mae": None,
            "inner_origins_covered": 0,
            "inner_origins_considered": len(inner_origins),
            "tied_configurations": 0,
            "fallback_used": True,
            "candidates": [],
        }

    candidates = []
    for configuration in configurations:
        per_industry_errors: dict[str, list[float]] = {}
        covered_origins = set()
        for inner_origin in inner_origins:
            # A SEPARATE calibrator per inner origin, built once and reused for
            # every configuration at THAT origin — never across origins.
            if inner_origin not in inner_calibrators:
                inner_calibrators[inner_origin] = calibrator_factory(inner_origin)
                permitted_cache[inner_origin] = label_permitted_origins(
                    label_lookup, inner_origin, horizon
                )
            inner_calibrator = inner_calibrators[inner_origin]
            permitted = permitted_cache[inner_origin]
            for industry_id in industries:
                model, assembly = _fit_industry(
                    index, labels_by_key, inner_calibrator, benchmark_fn,
                    industry_id, horizon, configuration, inner_origin, permitted,
                    design_cache,
                )
                if model is None:
                    continue
                if assembly["feature_usable_rows"] < MIN_INNER_TRAINING_ORIGINS:
                    continue
                vector = features_as_of(
                    index, inner_origin, industry_id,
                    configuration.non_ferrous_channel,
                )
                label = labels_by_key.get((industry_id, inner_origin, horizon))
                if vector is None or label is None:
                    continue
                benchmark = benchmark_fn(
                    industry_id, inner_origin, horizon, inner_calibrator
                )
                if benchmark is None:
                    continue
                values = dict(zip(vector["predictor_names"], vector["values"], strict=True))
                try:
                    predicted_residual = model.predict(values)
                except RidgeError:
                    continue
                prediction = min(max(benchmark + predicted_residual, 0.0), 100.0)
                # The inner validation TARGET is read only now, after the
                # inner prediction exists.
                observed = inner_calibrator.transform(
                    industry_id, float(label["target_raw_value"])
                )[0]
                per_industry_errors.setdefault(industry_id, []).append(
                    abs(prediction - float(observed))
                )
                covered_origins.add(inner_origin)

        if not per_industry_errors:
            candidates.append(
                {
                    "configuration_id": configuration.configuration_id,
                    "alpha": configuration.alpha,
                    "non_ferrous_channel": configuration.non_ferrous_channel,
                    "inner_macro_mae": None,
                    "inner_origins_covered": 0,
                    "industries_scored": 0,
                    "mean_predictor_count": None,
                }
            )
            continue

        macro = float(
            np.mean([float(np.mean(errors)) for errors in per_industry_errors.values()])
        )
        # Predictor count for the tie rule, from X only.
        sample = features_as_of(
            index, outer_origin, industries[0], configuration.non_ferrous_channel
        )
        candidates.append(
            {
                "configuration_id": configuration.configuration_id,
                "alpha": configuration.alpha,
                "non_ferrous_channel": configuration.non_ferrous_channel,
                "inner_macro_mae": macro,
                "inner_origins_covered": len(covered_origins),
                "industries_scored": len(per_industry_errors),
                "mean_predictor_count": (
                    len(sample["predictor_names"]) if sample else None
                ),
            }
        )

    scored = [c for c in candidates if c["inner_macro_mae"] is not None]
    if not scored:
        raise InsufficientInnerHistoryError(
            f"No configuration could be scored at outer origin {outer_origin} "
            f"for h={horizon}."
        )

    best = min(c["inner_macro_mae"] for c in scored)
    # Tie rule, applied in the registered order: fewer predictors, then larger
    # alpha, then the deterministic configuration-ID order.
    tied = [c for c in scored if c["inner_macro_mae"] - best <= MAE_TIE_TOLERANCE]
    ordered = sorted(
        tied,
        key=lambda c: (
            c["mean_predictor_count"] if c["mean_predictor_count"] is not None else 1e9,
            -c["alpha"],
            c["configuration_id"],
        ),
    )
    winner = ordered[0]
    reason = (
        "lowest_inner_macro_mae"
        if len(tied) == 1
        else "tie_broken_by_fewer_predictors_then_larger_alpha_then_config_id"
    )
    return {
        "selected": Configuration(
            alpha=winner["alpha"], non_ferrous_channel=winner["non_ferrous_channel"]
        ),
        "selection_reason": reason,
        "fallback_used": False,
        "selected_inner_macro_mae": winner["inner_macro_mae"],
        "inner_origins_covered": winner["inner_origins_covered"],
        "inner_origins_considered": len(inner_origins),
        "tied_configurations": len(tied),
        "candidates": candidates,
    }


@dataclass
class OriginResult:
    """Everything produced at one outer origin and horizon."""

    origin: str
    horizon: int
    predictions: list[dict] = field(default_factory=list)
    selection: dict = field(default_factory=dict)
    assemblies: dict = field(default_factory=dict)


def fit_and_predict_origin(
    index, labels_by_key, industries, horizon, outer_origin, calibrator,
    benchmark_fn, label_lookup, configuration, variant: str,
) -> OriginResult:
    """Fit every industry at one outer origin and predict, target unread."""
    permitted = label_permitted_origins(label_lookup, outer_origin, horizon)
    result = OriginResult(origin=outer_origin, horizon=int(horizon))

    for industry_id in industries:
        model, assembly = _fit_industry(
            index, labels_by_key, calibrator, benchmark_fn, industry_id, horizon,
            configuration, outer_origin, permitted,
        )
        vector = features_as_of(
            index, outer_origin, industry_id, configuration.non_ferrous_channel
        )
        benchmark = benchmark_fn(industry_id, outer_origin, horizon, calibrator)
        if benchmark is None:
            raise SelectionError(
                f"{industry_id}: no benchmark prediction at {outer_origin}."
            )

        if model is None or vector is None:
            predicted_residual = 0.0
            quality = (
                "no_model_fitted_benchmark_only"
                if model is None else "no_feature_vector_benchmark_only"
            )
            model_checksum = None
            scaler_checksum = None
            retained: tuple = ()
            omitted_zero_variance: tuple = ()
        else:
            values = dict(zip(vector["predictor_names"], vector["values"], strict=True))
            predicted_residual = model.predict(values)
            quality = "ok"
            model_checksum = model.checksum()
            scaler_checksum = model.scaler.checksum()
            retained = model.retained_predictors
            omitted_zero_variance = model.omitted_zero_variance

        unclipped = float(benchmark) + float(predicted_residual)
        clipped = min(max(unclipped, 0.0), 100.0)
        result.predictions.append(
            {
                "forecast_origin_month": outer_origin,
                "industry_id": industry_id,
                "horizon_months": int(horizon),
                "feature_variant": variant,
                "benchmark_prediction": float(benchmark),
                "predicted_residual": float(predicted_residual),
                "prediction_before_clipping": unclipped,
                "predicted_score": float(clipped),
                "clipped": bool(clipped != unclipped),
                "selected_alpha": configuration.alpha,
                "selected_non_ferrous_channel": configuration.non_ferrous_channel,
                "predictor_count": len(retained),
                "predictor_names": list(retained),
                "zero_variance_predictors_omitted": list(omitted_zero_variance),
                "ineligible_predictors_omitted": list(
                    vector["omitted_ineligible_predictors"] if vector else []
                ),
                "model_checksum": model_checksum,
                "scaler_checksum": scaler_checksum,
                "c2_lineage_checksums": (
                    vector["c2_lineage_checksums"] if vector else []
                ),
                "c3_exposure_checksums": (
                    vector["c3_exposure_checksums"] if vector else []
                ),
                "label_permitted_training_rows": assembly["label_permitted_origins"],
                "feature_usable_training_rows": assembly["feature_usable_rows"],
                "excluded_for_feature_history": assembly[
                    "excluded_for_feature_history"
                ],
                "earliest_usable_training_origin": assembly["earliest_usable_origin"],
                "latest_usable_training_origin": assembly["latest_usable_origin"],
                "max_training_target_window_end": assembly[
                    "max_training_target_window_end"
                ],
                "quality_flag": quality,
            }
        )
        result.assemblies[industry_id] = assembly
    return result
