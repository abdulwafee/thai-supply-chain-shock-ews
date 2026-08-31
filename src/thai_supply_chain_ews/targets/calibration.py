"""Leakage-safe industry-relative calibration (Task B3).

`IndustryStressCalibrator` turns a raw `mpi_adverse_yoy` value into an
industry-relative empirical percentile in 0-100, using ONLY reference
observations the caller's training cutoff permits.

Why a fit/transform split matters here: the whole point of the score is that a
raw stress value means something different in a volatile industry than in a
stable one. Calibrating against the full sample would encode information from
months the model has not been allowed to see, so a backtest built on it would
report an optimistic number that cannot be reproduced live.

This deliberately does NOT reuse Task B2's `diagnostic_only_full_sample_rank` —
that quantity was full-sample by construction and explicitly labelled not
leakage-safe.

Guarantees:
  * `fit` rejects any reference observation dated after the declared cutoff.
  * `transform` never refits and never mutates the fitted state.
  * An industry with too little history is recorded as excluded, not silently
    dropped; transforming it raises.
  * An unseen industry raises rather than falling back to a pooled distribution.
  * Serialization is deterministic: same fit -> byte-identical JSON.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "CalibratorNotFittedError",
    "IndustryReference",
    "IndustryStressCalibrator",
    "InsufficientReferenceError",
    "LeakageError",
    "UnknownIndustryError",
    "assign_risk_levels",
    "risk_level_for_score",
]


class CalibratorNotFittedError(RuntimeError):
    """transform() was called before fit()."""


class LeakageError(ValueError):
    """Reference data extends past the declared training cutoff."""


class InsufficientReferenceError(ValueError):
    """An industry has fewer reference observations than the configured minimum."""


class UnknownIndustryError(KeyError):
    """An industry was never fitted. No pooled fallback is applied."""


@dataclass(frozen=True)
class IndustryReference:
    industry_id: str
    n: int
    sorted_values: tuple[float, ...]
    start_month: str
    end_month: str
    fingerprint: str

    def to_dict(self) -> dict:
        return {
            "industry_id": self.industry_id,
            "n": self.n,
            "sorted_values": [float(v) for v in self.sorted_values],
            "start_month": self.start_month,
            "end_month": self.end_month,
            "fingerprint": self.fingerprint,
        }


def _fingerprint(industry_id: str, values: np.ndarray, start: str, end: str) -> str:
    payload = json.dumps(
        {
            "industry_id": industry_id,
            "start_month": start,
            "end_month": end,
            # repr at fixed precision keeps the fingerprint stable across runs
            "values": [format(float(v), ".12g") for v in values],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class IndustryStressCalibrator:
    """Empirical-CDF calibrator, fitted per industry on permitted history only.

    score = 100 * (count(reference < x) + 0.5 * count(reference == x)) / n
    """

    def __init__(
        self,
        min_reference_observations: int = 24,
        version: str = "industry_stress_calibrator_v1",
        value_column: str = "mpi_adverse_yoy",
        month_column: str = "reference_month",
        industry_column: str = "industry_id",
    ) -> None:
        self.min_reference_observations = int(min_reference_observations)
        self.version = version
        self.value_column = value_column
        self.month_column = month_column
        self.industry_column = industry_column
        self._references: dict[str, IndustryReference] = {}
        self._excluded: dict[str, dict] = {}
        self._training_cutoff_month: str | None = None
        self._fitted = False

    # --- fit -----------------------------------------------------------------

    def fit(self, reference: pd.DataFrame, training_cutoff_month: str) -> IndustryStressCalibrator:
        """Fit on reference rows at or before `training_cutoff_month`.

        The cutoff is not a filter applied for the caller's convenience — it is
        an assertion. Passing data beyond it raises `LeakageError` rather than
        quietly trimming, so a caller that accidentally hands over validation or
        test months finds out immediately.
        """
        if training_cutoff_month is None:
            raise ValueError(
                "training_cutoff_month is required — an implicit cutoff is not allowed"
            )
        cutoff = str(training_cutoff_month)

        months = reference[self.month_column].astype(str)
        offending = sorted(months[months > cutoff].unique().tolist())
        if offending:
            raise LeakageError(
                f"Reference data contains {len(offending)} month(s) after the training cutoff "
                f"{cutoff} (first offending: {offending[0]}). Refusing to fit — this would leak "
                "future information into the calibration."
            )

        self._references = {}
        self._excluded = {}
        for industry_id, sub in reference.groupby(self.industry_column, observed=True):
            values = sub[self.value_column].to_numpy(dtype=float)
            values = values[~np.isnan(values)]
            sub_months = sorted(sub[self.month_column].astype(str).tolist())
            if len(values) < self.min_reference_observations:
                self._excluded[str(industry_id)] = {
                    "industry_id": str(industry_id),
                    "n": int(len(values)),
                    "required": self.min_reference_observations,
                    "reason": "insufficient_reference_observations",
                }
                continue
            ordered = np.sort(values, kind="mergesort")
            start, end = (sub_months[0], sub_months[-1]) if sub_months else ("", "")
            self._references[str(industry_id)] = IndustryReference(
                industry_id=str(industry_id),
                n=int(len(ordered)),
                sorted_values=tuple(float(v) for v in ordered),
                start_month=start,
                end_month=end,
                fingerprint=_fingerprint(str(industry_id), ordered, start, end),
            )

        self._training_cutoff_month = cutoff
        self._fitted = True
        return self

    # --- state ---------------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_cutoff_month(self) -> str | None:
        return self._training_cutoff_month

    @property
    def fitted_industries(self) -> list[str]:
        return sorted(self._references)

    @property
    def excluded_industries(self) -> dict[str, dict]:
        """Industries that failed the minimum-history rule. Recorded, not dropped."""
        return dict(self._excluded)

    def reference_for(self, industry_id: str) -> IndustryReference:
        self._require_fitted()
        key = str(industry_id)
        if key in self._excluded:
            raise InsufficientReferenceError(
                f"{key} has {self._excluded[key]['n']} reference observation(s), below the "
                f"required minimum of {self.min_reference_observations}; it was excluded at fit "
                "time and cannot be transformed."
            )
        if key not in self._references:
            raise UnknownIndustryError(
                f"{key} was not fitted. No pooled fallback distribution is applied — an unseen "
                "industry must be handled by an explicit, tested policy."
            )
        return self._references[key]

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise CalibratorNotFittedError("fit() must be called before transform()")

    # --- transform -----------------------------------------------------------

    def transform(self, industry_id: str, values) -> np.ndarray:
        """Raw adverse-YoY values -> industry-relative percentile scores (0-100).

        Never refits and never mutates fitted state.
        """
        ref = self.reference_for(industry_id)
        arr = np.atleast_1d(np.asarray(values, dtype=float))
        sorted_ref = np.asarray(ref.sorted_values, dtype=float)
        n = ref.n
        # searchsorted on a sorted array gives both counts without a Python loop
        less = np.searchsorted(sorted_ref, arr, side="left")
        less_or_equal = np.searchsorted(sorted_ref, arr, side="right")
        equal = less_or_equal - less
        scores = 100.0 * (less + 0.5 * equal) / n
        return scores

    def transform_frame(self, frame: pd.DataFrame, value_column: str | None = None) -> pd.Series:
        """Vectorized transform over a frame carrying industry_id + a value column."""
        self._require_fitted()
        column = value_column or self.value_column
        out = pd.Series(np.nan, index=frame.index, dtype=float)
        for industry_id, sub in frame.groupby(self.industry_column, observed=True):
            out.loc[sub.index] = self.transform(str(industry_id), sub[column].to_numpy(float))
        return out

    # --- serialization -------------------------------------------------------

    def to_dict(self) -> dict:
        self._require_fitted()
        return {
            "calibrator_version": self.version,
            "min_reference_observations": self.min_reference_observations,
            "training_cutoff_month": self._training_cutoff_month,
            "value_column": self.value_column,
            "formula": (
                "score = 100 * (count(reference < x) + 0.5 * count(reference == x)) / n"
            ),
            "output_range": [0, 100],
            "fitted_industries": [
                self._references[k].to_dict() for k in sorted(self._references)
            ],
            "excluded_industries": [self._excluded[k] for k in sorted(self._excluded)],
        }

    def to_json(self, path: Path) -> Path:
        """Write a byte-stable artifact.

        newline="\\n" is explicit: the default would translate to CRLF on
        Windows, so the same fit would serialize to different bytes on
        different platforms and break checksum comparison.
        """
        path = Path(path)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=False)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        return path

    @classmethod
    def from_dict(cls, payload: dict) -> IndustryStressCalibrator:
        calibrator = cls(
            min_reference_observations=int(payload["min_reference_observations"]),
            version=payload["calibrator_version"],
            value_column=payload.get("value_column", "mpi_adverse_yoy"),
        )
        calibrator._references = {
            entry["industry_id"]: IndustryReference(
                industry_id=entry["industry_id"],
                n=int(entry["n"]),
                sorted_values=tuple(float(v) for v in entry["sorted_values"]),
                start_month=entry["start_month"],
                end_month=entry["end_month"],
                fingerprint=entry["fingerprint"],
            )
            for entry in payload["fitted_industries"]
        }
        calibrator._excluded = {e["industry_id"]: e for e in payload.get("excluded_industries", [])}
        calibrator._training_cutoff_month = payload["training_cutoff_month"]
        calibrator._fitted = True
        return calibrator


# --- risk levels -------------------------------------------------------------


def risk_level_for_score(score: float, risk_levels: list[dict]) -> str:
    """Map a 0-100 score to a policy risk band.

    Bands are half-open [min, max) except the top band, which is closed at 100.
    These are presentation thresholds, not observed ground-truth classes.
    """
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "Unknown"
    for band in risk_levels:
        low = float(band["min_score"])
        if "max_score_exclusive" in band:
            if low <= score < float(band["max_score_exclusive"]):
                return band["name"]
        else:
            if low <= score <= float(band["max_score_inclusive"]):
                return band["name"]
    raise ValueError(f"Score {score} falls outside the configured risk bands")


def assign_risk_levels(scores, risk_levels: list[dict]) -> list[str]:
    return [risk_level_for_score(float(s), risk_levels) for s in np.atleast_1d(scores)]
