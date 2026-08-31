"""Walk-forward evaluator for the pooled fuel-oil interaction (Task D5).

Runs one variant and one horizon across the fifteen development issue months,
refitting at every outer issue ``t`` on the panel the live system could have had
at ``t``.

**The target reader is a gate, not a convention.** :class:`GuardedTargetReader`
refuses to return a single target value until the Phase-A protocol checksum has
been verified from disk, and refuses again for any prediction whose freeze has
not been recorded. A target read before the freeze raises and terminates the run
rather than producing a slightly optimistic number that nothing downstream can
detect.

The ordering at each ``(t, h)`` is fixed and each step is asserted rather than
assumed:

1. calibrator fitted on stress up to ``t-1`` and frozen;
2. training panel assembled from issues ``u < t`` whose labels were published by
   ``t`` and whose features stand at ``u-2``;
3. source scaler fitted on the **unique** training issue months;
4. coefficients solved;
5. benchmark and model prediction produced and **frozen**;
6. only then the evaluation target is read.

Step 6 is where every leak in this project would have lived, which is why the
reader counts its own calls and reports them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from thai_supply_chain_ews.modeling import fuel_oil_pooled_panel as PP

__all__ = [
    "GuardedTargetReader",
    "PhaseBoundaryError",
    "TargetAccessError",
    "WalkForwardError",
    "assert_calibrator_cutoff",
    "assert_label_available_by",
    "assert_no_purge_or_locked_origin",
    "assert_stress_month_permitted",
    "eligible_training_issues",
]


class WalkForwardError(ValueError):
    """A rule of the operational walk-forward was violated."""


class PhaseBoundaryError(WalkForwardError):
    """Phase B was entered before the Phase-A protocol freeze was verified."""


class TargetAccessError(WalkForwardError):
    """A target value was requested before its prediction was frozen."""


# ---------------------------------------------------------------------------
# The two-phase boundary
# ---------------------------------------------------------------------------
@dataclass
class GuardedTargetReader:
    """The only way D5 may read a target value.

    Two locks. The **protocol lock** stays closed until the Phase-A checksum has
    been read back from disk and matched, so no target can be touched while the
    specification is still editable. The **freeze lock** is per prediction: a
    key must have been registered as frozen before its observed value is
    returned, so an evaluation label cannot influence the prediction it scores.
    """

    protocol_checksum: str = None
    verified: bool = False
    frozen_keys: set = field(default_factory=set)
    reads: int = 0
    reads_before_freeze: int = 0

    def verify_protocol(self, expected: str, observed: str) -> str:
        """Open the protocol lock, or refuse to."""
        if not expected or not observed:
            raise PhaseBoundaryError(
                "the Phase-A protocol checksum is missing; targets stay closed"
            )
        if expected != observed:
            raise PhaseBoundaryError(
                f"the frozen protocol read back as {observed}, not {expected}. The "
                "specification changed between the freeze and the evaluation"
            )
        self.protocol_checksum = expected
        self.verified = True
        return expected

    def assert_open(self) -> None:
        if not self.verified:
            raise PhaseBoundaryError(
                "a target value was requested before the Phase-A protocol "
                "checksum was verified. Phase B may not begin while the "
                "specification is still editable"
            )

    def freeze(self, key) -> None:
        """Record that a prediction is final and may now be scored."""
        self.assert_open()
        self.frozen_keys.add(tuple(key))

    def read(self, key, observed):
        """Return an observed target, but only for a frozen prediction."""
        self.assert_open()
        if tuple(key) not in self.frozen_keys:
            self.reads_before_freeze += 1
            raise TargetAccessError(
                f"the evaluation target for {tuple(key)} was read before its "
                "prediction was frozen. The label would then be able to influence "
                "the number it is meant to score"
            )
        self.reads += 1
        return float(observed)

    def to_dict(self) -> dict:
        return {
            "protocol_checksum": self.protocol_checksum,
            "protocol_verified_before_any_target_read": bool(self.verified),
            "target_reads": int(self.reads),
            "target_reads_before_prediction_freeze": int(self.reads_before_freeze),
            "predictions_frozen": len(self.frozen_keys),
        }


# ---------------------------------------------------------------------------
# Temporal assertions, made independently of the shared contract implementation
# ---------------------------------------------------------------------------
def assert_stress_month_permitted(stress_month: str, outer_issue: str) -> None:
    """Raise if stress from month ``t`` (or later) is used at issue ``t``."""
    if str(stress_month)[:7] >= str(outer_issue)[:7]:
        raise WalkForwardError(
            f"stress month {stress_month} is not strictly before issue month "
            f"{outer_issue}; the latest publishable month at t is t-1"
        )


def assert_calibrator_cutoff(reference_end: str, outer_issue: str) -> None:
    """Raise unless the calibrator was cut at ``t-1`` or earlier."""
    ceiling = PP.shift_month(str(outer_issue)[:7], -1)
    if str(reference_end)[:7] > ceiling:
        raise WalkForwardError(
            f"the calibrator reference ends {reference_end}, after {ceiling}. A "
            f"calibrator fitted through month {outer_issue} would carry that "
            "month's stress into every historical score"
        )


def assert_label_available_by(available_month: str, outer_issue: str,
                              origin: str) -> None:
    """Raise if a training label was not yet published at the outer issue."""
    if str(available_month)[:7] > str(outer_issue)[:7]:
        raise WalkForwardError(
            f"the label for training origin {origin} becomes available "
            f"{available_month}, after the outer issue month {outer_issue}; it "
            "could not have been in the training set"
        )


def assert_no_purge_or_locked_origin(origins, purge_months, locked_months) -> None:
    """Raise if a reserved origin reached the evaluation."""
    reserved = set(purge_months) | set(locked_months)
    intruders = sorted({str(o)[:7] for o in origins} & reserved)
    if intruders:
        raise WalkForwardError(
            f"reserved origins {intruders} entered the D5 evaluation. Purge "
            "evaluation and locked-test access are both unauthorized"
        )


def eligible_training_issues(label_origins, outer_issue: str,
                             feature_months: set,
                             benchmark_available,
                             lag: int = PP.POLICY_LAG_MONTHS) -> dict:
    """Which historical issues may train the model at outer issue ``t``.

    An issue survives only if all three of its clocks agree: its label was
    published by ``t``, its feature reference month ``u-2`` carries all five
    transformations, and its operational benchmark history was complete at ``u``.
    The three exclusions are counted separately, because "not enough price
    history" and "not enough stress history" are different facts and a single
    total would hide which one is binding.
    """
    accepted, no_feature, no_benchmark = [], [], []
    for origin in label_origins:
        month = str(origin)[:7]
        if month >= str(outer_issue)[:7]:
            raise WalkForwardError(
                f"training origin {month} is not before the outer issue "
                f"{outer_issue}"
            )
        reference = PP.shift_month(month, -lag)
        if reference not in feature_months:
            no_feature.append(month)
            continue
        if not benchmark_available(month):
            no_benchmark.append(month)
            continue
        accepted.append(month)
    return {
        "accepted": sorted(accepted),
        "accepted_count": len(accepted),
        "excluded_no_complete_feature_row": sorted(no_feature),
        "excluded_no_operational_benchmark_history": sorted(no_benchmark),
        "label_origins_considered": len(list(label_origins)),
    }


# ---------------------------------------------------------------------------
@dataclass
class OriginFit:
    """One (variant, horizon, outer issue) fit and its predictions."""

    variant_id: str
    horizon: int
    outer_issue: str
    training_issue_months: tuple = ()
    training_rows: int = 0
    all_industry_training_rows: int = 0
    scaler: dict = field(default_factory=dict)
    exposure: dict = field(default_factory=dict)
    coefficients: dict = field(default_factory=dict)
    coefficient_checksum: str = ""
    normal_equation_residual: float = 0.0
    predictions: list = field(default_factory=list)
    exclusions: dict = field(default_factory=dict)
    calibration_reference_end: str = ""
    latest_available_stress_month: str = ""


def standardize_row(values, scaler) -> np.ndarray:
    """Apply the frozen training scaler to one issue month's source values."""
    means = np.asarray(scaler["means"], dtype=float)
    deviations = np.asarray(scaler["standard_deviations"], dtype=float)
    return (np.asarray(values, dtype=float) - means) / deviations
