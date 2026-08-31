"""The one fixed estimator D5 is permitted to fit (``fixed_pooled_partial_ridge_v1``).

Minimises ``(1/n) * sum_i (r_i - rhat_i)^2 + lambda * (||beta||^2 + ||theta||^2)``
with ``lambda = 1.0``, the five source and five interaction coefficients
penalised and the eleven industry fixed effects **not**.

Three details decide whether this is the estimator that was preregistered or a
different one wearing its name.

**The loss is averaged by n.** With an unnormalised sum, the same ``lambda``
means a weaker penalty every time the training panel grows — and it grows at
every outer issue month, from 231 rows to 385. The specification would then
drift across the walk-forward without anyone changing a number.
:func:`assert_loss_is_normalised` raises on the unnormalised form.

**The fixed effects are unpenalised.** Shrinking an industry intercept toward
zero shrinks it toward a stress score of zero, which is not a neutral prior; it
is a strong claim about industries with high baseline stress. The penalty matrix
is explicit and :func:`assert_penalty_matrix` checks it block by block.

**There is no global intercept.** Eleven indicators already span the intercept,
so adding one makes the normal equations singular — solvable only by the ridge
term leaking into a block it must not touch.

Nothing here searches. No alpha grid, no inner CV, no model averaging, no
fallback, no outcome-based feature removal. The normal-equation residual is
returned so the solve can be verified rather than trusted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

__all__ = [
    "ESTIMATOR_NAME",
    "FIXED_LAMBDA",
    "INTERACTION_BLOCK",
    "PENALIZED_BLOCKS",
    "SOURCE_BLOCK",
    "EstimatorError",
    "PooledRidgeFit",
    "assert_loss_is_normalised",
    "assert_no_global_intercept",
    "assert_penalty_matrix",
    "assert_training_variance",
    "clip_score",
    "coefficient_checksum",
    "fit_fixed_pooled_partial_ridge",
    "penalty_matrix",
]

ESTIMATOR_NAME = "fixed_pooled_partial_ridge_v1"

#: Preregistered in configs/d5_fuel_oil_interaction.yaml. Not a starting point,
#: not a grid centre: the one value this estimator may ever use.
FIXED_LAMBDA = 1.0

SOURCE_BLOCK = "source"
INTERACTION_BLOCK = "interaction"
PENALIZED_BLOCKS = (SOURCE_BLOCK, INTERACTION_BLOCK)

SCORE_FLOOR = 0.0
SCORE_CEILING = 100.0

_ZERO_VARIANCE_TOLERANCE = 1e-12


class EstimatorError(ValueError):
    """The frozen estimator was asked to be a different estimator."""


def assert_loss_is_normalised(normalised: bool, lambda_value: float) -> None:
    """Raise if the loss drops the ``1/n`` while keeping the same ``lambda``.

    An unnormalised sum with ``lambda = 1.0`` is a *different* specification at
    every outer issue month, because the training panel grows from 231 rows to
    385 across the walk-forward. The penalty would weaken monotonically without
    a single number being edited.
    """
    if not normalised:
        raise EstimatorError(
            f"the loss is not averaged by n while lambda is still {lambda_value}. "
            "An unnormalised sum makes the same lambda a weaker penalty on every "
            "larger training panel, so the specification would drift across the "
            "walk-forward without being changed"
        )


def assert_no_global_intercept(column_names, fixed_effect_count: int) -> None:
    """Raise on an intercept alongside a full industry-indicator block.

    The indicators already sum to the intercept, so the normal equations become
    singular and only the ridge term makes them solvable — by shrinking a block
    the specification says is unpenalised.
    """
    lowered = [str(name).lower() for name in column_names]
    if any(name in ("intercept", "const", "_intercept", "global_intercept")
           for name in lowered):
        raise EstimatorError(
            "a global intercept was added alongside the full industry-indicator "
            f"block of {fixed_effect_count} columns. The indicators already span "
            "the intercept; adding one makes the design rank-deficient"
        )


def assert_training_variance(matrix, column_names,
                             tolerance: float = _ZERO_VARIANCE_TOLERANCE) -> None:
    """Raise if a predictor has zero or invalid variance in the training panel.

    A constant predictor cannot be standardised and cannot be identified; the
    correct response is to stop, not to drop the column, because dropping it is
    an outcome-blind feature removal the protocol forbids.
    """
    array = np.asarray(matrix, dtype=float)
    if not np.isfinite(array).all():
        bad = sorted({column_names[j] for j in np.where(~np.isfinite(array).all(0))[0]})
        raise EstimatorError(f"non-finite training values in {bad}")
    variances = array.var(axis=0, ddof=0)
    degenerate = [
        column_names[j] for j, value in enumerate(variances)
        if not np.isfinite(value) or value <= tolerance
    ]
    if degenerate:
        raise EstimatorError(
            f"predictors {sorted(degenerate)} have zero or invalid training "
            "variance. D5 stops rather than removing a feature: an outcome-blind "
            "column drop is still a design change"
        )


def penalty_matrix(blocks, lambda_value: float = FIXED_LAMBDA):
    """The explicit diagonal penalty: ``lambda`` on source and interaction, 0 elsewhere."""
    diagonal = np.array(
        [lambda_value if block in PENALIZED_BLOCKS else 0.0 for block in blocks],
        dtype=float,
    )
    return np.diag(diagonal)


def assert_penalty_matrix(matrix, blocks, lambda_value: float = FIXED_LAMBDA) -> None:
    """Raise unless exactly the source and interaction blocks are penalised."""
    array = np.asarray(matrix, dtype=float)
    if array.shape != (len(blocks), len(blocks)):
        raise EstimatorError(
            f"penalty matrix is {array.shape}, expected "
            f"({len(blocks)}, {len(blocks)})"
        )
    off_diagonal = array - np.diag(np.diag(array))
    if np.abs(off_diagonal).max(initial=0.0) > 0:
        raise EstimatorError("the penalty matrix must be diagonal")
    for index, block in enumerate(blocks):
        expected = lambda_value if block in PENALIZED_BLOCKS else 0.0
        if array[index, index] != expected:
            raise EstimatorError(
                f"column {index} is in block {block!r} and carries penalty "
                f"{array[index, index]}, expected {expected}. Industry fixed "
                "effects are unpenalised: shrinking an industry intercept toward "
                "zero shrinks it toward a stress score of zero, which is a strong "
                "claim rather than a neutral prior"
            )


@dataclass
class PooledRidgeFit:
    """One frozen fit. No selection was performed to produce it."""

    estimator_name: str = ESTIMATOR_NAME
    lambda_value: float = FIXED_LAMBDA
    loss_normalised_by_n: bool = True
    column_names: tuple = ()
    blocks: tuple = ()
    coefficients: tuple = ()
    n_training_rows: int = 0
    n_training_issue_months: int = 0
    normal_equation_residual: float = 0.0
    penalized_columns: int = 0
    unpenalized_columns: int = 0
    hyperparameter_search_performed: bool = False
    inner_cv_performed: bool = False
    model_averaging_performed: bool = False
    fallback_estimator_used: bool = False
    features_removed: tuple = ()
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def coefficient_map(self) -> dict:
        return dict(zip(self.column_names, self.coefficients, strict=True))

    def predict(self, matrix) -> np.ndarray:
        return np.asarray(matrix, dtype=float) @ np.asarray(
            self.coefficients, dtype=float
        )


def fit_fixed_pooled_partial_ridge(matrix, residuals, column_names, blocks,
                                   lambda_value: float = FIXED_LAMBDA,
                                   loss_normalised_by_n: bool = True,
                                   n_training_issue_months: int = 0,
                                   tolerance: float = 1e-8) -> PooledRidgeFit:
    """Solve ``(X'X/n + lambda*P) w = X'r/n`` for the frozen specification.

    Averaging both sides by ``n`` is what makes ``lambda`` mean the same thing
    on a 231-row panel and a 385-row one. ``P`` is the explicit penalty matrix,
    checked block by block before the solve, and the normal-equation residual is
    returned so the solution can be verified rather than assumed.
    """
    assert_loss_is_normalised(loss_normalised_by_n, lambda_value)
    if lambda_value != FIXED_LAMBDA:
        raise EstimatorError(
            f"lambda is {lambda_value}, not the frozen {FIXED_LAMBDA}. D5 fits one "
            "specification: no grid, no inner CV, no tuning of any kind"
        )
    column_names = tuple(column_names)
    blocks = tuple(blocks)
    if len(column_names) != len(blocks):
        raise EstimatorError("every column needs a block label")
    assert_no_global_intercept(
        column_names, sum(1 for b in blocks if b not in PENALIZED_BLOCKS)
    )

    design = np.asarray(matrix, dtype=float)
    target = np.asarray(residuals, dtype=float)
    if design.ndim != 2 or design.shape[0] != target.shape[0]:
        raise EstimatorError(
            f"design {design.shape} does not match {target.shape[0]} residuals"
        )
    n = design.shape[0]
    if n == 0:
        raise EstimatorError("no training rows")
    assert_training_variance(
        design[:, [i for i, b in enumerate(blocks) if b in PENALIZED_BLOCKS]],
        [c for c, b in zip(column_names, blocks, strict=True) if b in PENALIZED_BLOCKS],
    )

    penalty = penalty_matrix(blocks, lambda_value)
    assert_penalty_matrix(penalty, blocks, lambda_value)

    gram = design.T @ design / n
    moment = design.T @ target / n
    system = gram + penalty
    coefficients = np.linalg.solve(system, moment)
    residual = float(np.abs(system @ coefficients - moment).max())
    if residual > tolerance:
        raise EstimatorError(
            f"the normal-equation residual is {residual!r}, above {tolerance}; the "
            "linear system was not solved to the required precision"
        )

    return PooledRidgeFit(
        column_names=column_names,
        blocks=blocks,
        coefficients=tuple(float(value) for value in coefficients),
        n_training_rows=int(n),
        n_training_issue_months=int(n_training_issue_months),
        normal_equation_residual=residual,
        penalized_columns=sum(1 for b in blocks if b in PENALIZED_BLOCKS),
        unpenalized_columns=sum(1 for b in blocks if b not in PENALIZED_BLOCKS),
        diagnostics={
            "gram_condition_number": float(np.linalg.cond(system)),
            "solver": "explicit_penalty_matrix_normal_equations",
        },
    )


def clip_score(value: float) -> tuple[float, bool]:
    """Clip to the fixed [0, 100] score range and say whether it bound."""
    numeric = float(value)
    clipped = min(max(numeric, SCORE_FLOOR), SCORE_CEILING)
    return clipped, clipped != numeric


def coefficient_checksum(fit: PooledRidgeFit, digits: int = 12) -> str:
    """Digest of the fitted coefficients and the specification that produced them."""
    import hashlib
    import json

    payload = {
        "estimator_name": fit.estimator_name,
        "lambda": fit.lambda_value,
        "loss_normalised_by_n": fit.loss_normalised_by_n,
        "column_names": list(fit.column_names),
        "blocks": list(fit.blocks),
        "coefficients": [f"{value:.{digits}e}" for value in fit.coefficients],
        "n_training_rows": fit.n_training_rows,
        "n_training_issue_months": fit.n_training_issue_months,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
