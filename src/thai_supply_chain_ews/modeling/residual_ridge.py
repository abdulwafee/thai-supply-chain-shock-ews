"""Industry-specific ridge residual correction — Task D1.

The model predicts what the B4 persistence benchmark MISSES, not the target::

    r = y - b            residual beyond the benchmark
    y_hat = b + r_hat    prediction

Framing it this way means the benchmark is the floor by construction: a model
that learns nothing predicts ``r_hat = 0`` and reproduces persistence exactly.
The comparison then asks the only question worth asking — does the commodity
information add anything *beyond* what persistence already captures?

One model per (outer origin, horizon, industry). **Coefficients are never
pooled across industries**: a coefficient fitted on food processing has no claim
on refineries, and pooling would let a strong industry's signal carry a weak
one's prediction.

Ridge is solved in closed form. With ~20-40 predictors and a few hundred rows
that is exact, fast, and free of solver-level nondeterminism.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "RidgeError",
    "ZeroVarianceError",
    "SCORE_FLOOR",
    "SCORE_CEILING",
    "StandardScaler",
    "RidgeResidualModel",
    "fit_ridge_residual",
    "clip_score",
]

# Preregistered and NOT tuned. The calibrated score is a percentile by
# construction, so anything outside [0, 100] is out of range by definition.
SCORE_FLOOR = 0.0
SCORE_CEILING = 100.0

_ZERO_VARIANCE_TOLERANCE = 1e-12


class RidgeError(ValueError):
    """The ridge model could not be fitted or applied as specified."""


class ZeroVarianceError(RidgeError):
    """Every predictor was constant in training."""


@dataclass
class StandardScaler:
    """Mean/standard-deviation scaler fitted on TRAINING ROWS ONLY.

    Fitting on the whole development period — even without touching targets —
    would leak the distribution of future predictors into every earlier fit.
    """

    names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray

    @classmethod
    def fit(cls, names, matrix: np.ndarray) -> StandardScaler:
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0, ddof=0)
        return cls(names=tuple(names), mean=mean, scale=std)

    def transform(self, matrix: np.ndarray) -> np.ndarray:
        return (matrix - self.mean) / self.scale

    def checksum(self) -> str:
        payload = json.dumps(
            {
                "names": list(self.names),
                "mean": [repr(float(v)) for v in self.mean],
                "scale": [repr(float(v)) for v in self.scale],
            },
            separators=(",", ":"), sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class RidgeResidualModel:
    """One fitted industry-specific residual model."""

    industry_id: str
    horizon: int
    alpha: float
    non_ferrous_channel: str
    retained_predictors: tuple[str, ...]
    omitted_zero_variance: tuple[str, ...]
    omitted_ineligible: tuple[str, ...]
    coefficients: np.ndarray
    intercept: float
    scaler: StandardScaler
    training_rows: int
    diagnostics: dict = field(default_factory=dict)

    def predict(self, values_by_name: dict[str, float]) -> float:
        missing = [n for n in self.retained_predictors if n not in values_by_name]
        if missing:
            raise RidgeError(
                f"{self.industry_id}: evaluation row is missing {missing}."
            )
        raw = np.array(
            [values_by_name[name] for name in self.retained_predictors], dtype=float
        )
        scaled = self.scaler.transform(raw.reshape(1, -1))
        return float(self.intercept + float((scaled @ self.coefficients)[0]))

    def checksum(self) -> str:
        payload = json.dumps(
            {
                "industry_id": self.industry_id,
                "horizon": self.horizon,
                "alpha": repr(self.alpha),
                "non_ferrous_channel": self.non_ferrous_channel,
                "predictors": list(self.retained_predictors),
                "coefficients": [repr(float(v)) for v in self.coefficients],
                "intercept": repr(self.intercept),
                "scaler": self.scaler.checksum(),
                "training_rows": self.training_rows,
            },
            separators=(",", ":"), sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _assert_no_shared_non_ferrous(names) -> None:
    """Aluminum and Copper read one coefficient; both in a model double-counts it."""
    has_aluminum = any(name.startswith("aluminum_usd_mt__") for name in names)
    has_copper = any(name.startswith("copper_usd_mt__") for name in names)
    if has_aluminum and has_copper:
        raise RidgeError(
            "Aluminum and Copper predictors appear in the same design matrix. "
            "They share I/O sector 107, so fitting both would count one "
            "structural exposure twice while looking like two signals."
        )


def fit_ridge_residual(
    industry_id: str,
    horizon: int,
    predictor_names,
    training_matrix: np.ndarray,
    residuals: np.ndarray,
    alpha: float,
    non_ferrous_channel: str,
    omitted_ineligible=(),
) -> RidgeResidualModel:
    """Fit one industry's ridge on the benchmark residual.

    Preprocessing order matters and is fixed: zero-variance detection uses **X
    only** (never the outcome), the scaler is fitted on training rows only, and
    the intercept is fitted rather than assumed.
    """
    names = list(predictor_names)
    _assert_no_shared_non_ferrous(names)

    if training_matrix.ndim != 2 or training_matrix.shape[1] != len(names):
        raise RidgeError(
            f"{industry_id}: matrix {training_matrix.shape} does not match "
            f"{len(names)} predictors."
        )
    if training_matrix.shape[0] != residuals.shape[0]:
        raise RidgeError(f"{industry_id}: rows disagree with residuals.")
    if alpha <= 0:
        raise RidgeError(f"Ridge alpha must be positive; got {alpha}.")

    # Zero variance is a property of the PREDICTOR, detected without the
    # outcome. Using y here would be outcome-based filtering.
    std = training_matrix.std(axis=0, ddof=0)
    keep = std > _ZERO_VARIANCE_TOLERANCE
    omitted = tuple(name for name, k in zip(names, keep, strict=True) if not k)
    retained = tuple(name for name, k in zip(names, keep, strict=True) if k)
    if not retained:
        raise ZeroVarianceError(
            f"{industry_id}: every predictor is constant in training."
        )

    matrix = training_matrix[:, keep]
    scaler = StandardScaler.fit(retained, matrix)
    scaled = scaler.transform(matrix)

    # Closed-form ridge with a centred outcome; the intercept is the mean and
    # is therefore never penalised.
    target_mean = float(residuals.mean())
    centred = residuals - target_mean
    gram = scaled.T @ scaled
    coefficients = np.linalg.solve(
        gram + alpha * np.eye(gram.shape[0]), scaled.T @ centred
    )

    return RidgeResidualModel(
        industry_id=industry_id,
        horizon=int(horizon),
        alpha=float(alpha),
        non_ferrous_channel=non_ferrous_channel,
        retained_predictors=retained,
        omitted_zero_variance=omitted,
        omitted_ineligible=tuple(omitted_ineligible),
        coefficients=coefficients,
        intercept=target_mean,
        scaler=scaler,
        training_rows=int(training_matrix.shape[0]),
        diagnostics={
            "predictors_supplied": len(names),
            "predictors_retained": len(retained),
            "predictors_omitted_zero_variance": len(omitted),
            "predictors_omitted_ineligible": len(omitted_ineligible),
            "residual_mean": target_mean,
            "residual_std": float(residuals.std(ddof=0)),
        },
    )


def clip_score(value: float) -> tuple[float, bool]:
    """Clip to the calibrated score's own range. Bounds are never tuned."""
    clipped = min(max(value, SCORE_FLOOR), SCORE_CEILING)
    return float(clipped), bool(clipped != value)
