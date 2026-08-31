"""The frozen D4 model specification (Task D4).

There is exactly one model here and it has no knobs. Alpha is 100.0, the
non-ferrous channel is ``none``, and both are constants that this module
**refuses** to vary: passing a different alpha raises rather than fitting.
That is the point. D1 showed the nested selection choosing maximum
regularization at 27 of 30 origin-horizons, and D2 showed the history cannot be
extended to support a real selection procedure. Freezing the D1 fallback avoids
inventing a tuning process that 15 origins cannot justify.

Aluminum and Copper never appear. They read the same I/O sector 107 coefficient,
so admitting either would allow one shared exposure to be used twice, a channel
to be chosen on outcomes, and two series to be reported as independent
measurements. Excluding both removes the choice rather than managing it — and
excluded predictors are **omitted**, never replaced with zero, because a zero is
a claim about the world while an omission is a claim about knowledge.

Fitting itself is delegated to the D1 production implementation, so the
preprocessing order (X-only zero-variance detection, training-only scaler,
fitted intercept) has one definition in the codebase rather than two.
"""

from __future__ import annotations

from thai_supply_chain_ews.modeling.residual_ridge import (
    SCORE_CEILING,
    SCORE_FLOOR,
    RidgeError,
    clip_score,
    fit_ridge_residual,
)

__all__ = [
    "EXCLUDED_COMMODITIES",
    "FIXED_ALPHA",
    "FIXED_CHANNEL",
    "MODEL_NAME",
    "SCORE_CEILING",
    "SCORE_FLOOR",
    "FrozenSpecificationError",
    "assert_no_excluded_commodity",
    "clip_score",
    "fit_fixed_operational_ridge",
]

MODEL_NAME = "operational_fixed_ridge_residual"
FIXED_ALPHA = 100.0
FIXED_CHANNEL = "none"
EXCLUDED_COMMODITIES = ("aluminum_usd_mt", "copper_usd_mt")


class FrozenSpecificationError(ValueError):
    """An attempt to vary something the D4 specification fixes."""


def assert_no_excluded_commodity(names, where: str) -> None:
    """Raise if an Aluminum or Copper predictor appears anywhere.

    Applied to the training matrix, the evaluation row, the scaler and the
    fitted artifact separately, so no single check is load-bearing.
    """
    offenders = [
        name
        for name in names
        if any(name.startswith(commodity + "__") for commodity in EXCLUDED_COMMODITIES)
    ]
    if offenders:
        raise FrozenSpecificationError(
            f"{where}: excluded non-ferrous predictor(s) {offenders}. Aluminum and "
            "Copper share I/O sector 107 and are excluded from D4 entirely."
        )


def fit_fixed_operational_ridge(
    industry_id: str,
    horizon: int,
    predictor_names,
    training_matrix,
    residuals,
    alpha: float = FIXED_ALPHA,
    non_ferrous_channel: str = FIXED_CHANNEL,
    omitted_ineligible=(),
):
    """Fit the one frozen model. Any deviation from the specification raises."""
    if float(alpha) != FIXED_ALPHA:
        raise FrozenSpecificationError(
            f"D4 alpha is frozen at {FIXED_ALPHA}; got {alpha}. D4 performs no "
            "hyperparameter search."
        )
    if non_ferrous_channel != FIXED_CHANNEL:
        raise FrozenSpecificationError(
            f"D4 non-ferrous channel is frozen at {FIXED_CHANNEL!r}; got "
            f"{non_ferrous_channel!r}."
        )
    names = list(predictor_names)
    assert_no_excluded_commodity(names, f"{industry_id} training matrix")
    if not names:
        raise RidgeError(f"{industry_id}: no predictors survived eligibility.")

    model = fit_ridge_residual(
        industry_id=industry_id,
        horizon=int(horizon),
        predictor_names=names,
        training_matrix=training_matrix,
        residuals=residuals,
        alpha=FIXED_ALPHA,
        non_ferrous_channel=FIXED_CHANNEL,
        omitted_ineligible=tuple(omitted_ineligible),
    )
    # The fitted artifact is checked independently of its inputs.
    assert_no_excluded_commodity(model.retained_predictors, f"{industry_id} model artifact")
    assert_no_excluded_commodity(model.scaler.names, f"{industry_id} scaler")
    if model.alpha != FIXED_ALPHA:
        raise FrozenSpecificationError(f"{industry_id}: fitted alpha {model.alpha}")
    return model
