"""Operational training-label availability (Task D3).

B4 admitted a historical training label as soon as its target window had closed:
``target_window_end <= t``. That is not when the label exists. If a window ends
at month *e*, the last MPI observation it needs is published during *e+1*, so at
forecast issue month *t* the label is knowable only when::

    target_available_month = target_window_end + 1 month
    target_available_month <= forecast_issue_month

The difference is one month, and it is not cosmetic: under the old rule the most
recent training label at every origin depended on an MPI value that had not been
published yet, which is the same defect the forecast itself had.

A label that fails the rule is a **hard error**, not something to filter out.
Silently dropping it would make an unavailable label indistinguishable from one
that never existed, and the count reconciliation that proves the rule is applied
would pass either way.
"""

from __future__ import annotations

from dataclasses import dataclass

from thai_supply_chain_ews.evaluation.splits import add_months

__all__ = [
    "LabelAvailabilityError",
    "LabelAvailability",
    "assert_labels_available",
    "available_training_labels",
    "target_available_month",
]


class LabelAvailabilityError(ValueError):
    """A training label is not yet published at the forecast issue month."""


def target_available_month(target_window_end) -> str:
    """The month in which a target window's final MPI observation is published."""
    return add_months(str(target_window_end), 1)


@dataclass(frozen=True)
class LabelAvailability:
    forecast_origin_month: str
    horizon: int
    latest_permitted_label_origin: str
    row_count: int
    max_target_window_end: str = None
    max_target_available_month: str = None

    def to_dict(self) -> dict:
        return {
            "forecast_origin_month": self.forecast_origin_month,
            "horizon": int(self.horizon),
            "latest_permitted_label_origin": self.latest_permitted_label_origin,
            "row_count": int(self.row_count),
            "max_target_window_end": self.max_target_window_end,
            "max_target_available_month": self.max_target_available_month,
        }


def available_training_labels(horizon_labels, issue_month: str):
    """Labels whose availability month is at or before the issue month.

    ``horizon_labels`` is a B3 label frame already filtered to one horizon. The
    raw target values are used unchanged — D3 reuses B3's windows and raw
    values, and only the calibration applied to them differs.
    """
    month = str(issue_month)
    available = horizon_labels["target_window_end"].map(target_available_month)
    permitted = horizon_labels[available <= month]
    return permitted


def summarize_availability(horizon_labels, issue_month: str, horizon: int) -> LabelAvailability:
    permitted = available_training_labels(horizon_labels, issue_month)
    if permitted.empty:
        return LabelAvailability(str(issue_month), int(horizon), None, 0)
    origins = permitted["forecast_origin_month"].map(str)
    ends = permitted["target_window_end"].map(str)
    return LabelAvailability(
        forecast_origin_month=str(issue_month),
        horizon=int(horizon),
        latest_permitted_label_origin=max(origins),
        row_count=int(len(permitted)),
        max_target_window_end=max(ends),
        max_target_available_month=target_available_month(max(ends)),
    )


def assert_labels_available(permitted, issue_month: str) -> None:
    """Raise if any admitted label is not yet published at the issue month."""
    month = str(issue_month)
    if permitted.empty:
        return
    offending = [
        (str(origin), str(end), target_available_month(end))
        for origin, end in zip(
            permitted["forecast_origin_month"], permitted["target_window_end"], strict=False
        )
        if target_available_month(end) > month
    ]
    if offending:
        raise LabelAvailabilityError(
            f"{len(offending)} training label(s) are not published at issue month "
            f"{month}; first offender: label origin {offending[0][0]} with window "
            f"ending {offending[0][1]}, available {offending[0][2]}. A label whose "
            "window has closed is not yet knowable until the following month."
        )


def assert_no_future_stress(stress_by_month, latest_available_stress_month: str) -> None:
    """Raise if a stress map carries any month beyond the latest published one."""
    late = sorted(m for m in stress_by_month if m > latest_available_stress_month)
    if late:
        from thai_supply_chain_ews.evaluation.operational_contract import (
            CurrentMonthStressError,
        )

        raise CurrentMonthStressError(
            f"stress map contains unpublished month(s) {late[:3]}; "
            f"latest published is {latest_available_stress_month}"
        )
