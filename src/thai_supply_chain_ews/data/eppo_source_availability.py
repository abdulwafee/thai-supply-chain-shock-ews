"""Source-level availability selection under the C6.5 policy (Task C7).

C6.5 decided that EPPO enters the project on a **release-lag-aware latest-vintage**
footing: the values are the current ones, their historical release timing was
never measured, and the project imposes a conservative two-month lag on itself
instead of pretending to know one.

This module is where that decision becomes executable. Two fields are kept apart
everywhere:

``source_available_as_of``
    Evidence. "The source is demonstrably public by this date." It is ``None``
    for every historical EPPO observation and writing a policy date into it
    raises, because that would manufacture provenance out of an assumption.

``policy_available_month``
    Assumption. ``reference_month + 2`` under the conservative policy, with
    ``availability_basis`` naming it as policy rather than measurement.

The selector answers one question — *what may a forecast issued in month t see?*
— and answers it from timing metadata alone. No target value, no evaluation
output and no model artifact is read to decide it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .eppo_latest_vintage_policy import (
    POLICY_LAG_MONTHS,
    PolicyError,
    permitted_reference_month,
    policy_available_month,
)

__all__ = [
    "AVAILABILITY_BASIS",
    "assert_measured_lag_not_claimed",
    "POLICY_LAG_MONTHS",
    "MonthlyAvailability",
    "PolicyError",
    "monthly_availability_fields",
    "permitted_reference_month",
    "policy_available_month",
    "select_monthly_source_available_at_issue",
]

AVAILABILITY_BASIS = "conservative_policy_not_historical_measurement"


@dataclass
class MonthlyAvailability:
    """The availability block attached to one monthly source row."""

    reference_month: str
    source_available_as_of: str = None
    policy_available_month: str = None
    availability_basis: str = AVAILABILITY_BASIS
    latest_vintage_used: bool = True
    point_in_time_supported: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def monthly_availability_fields(reference_month: str,
                                lag_months: int = POLICY_LAG_MONTHS,
                                source_available_as_of: str = None,
                                historical_timing_verified: bool = False
                                ) -> MonthlyAvailability:
    """Build a monthly row's availability fields without conflating the two kinds.

    Passing a date into ``source_available_as_of`` while timing is unverified
    raises — that is the one mistake this contract exists to prevent.
    """
    if source_available_as_of is not None and not historical_timing_verified:
        raise PolicyError(
            "source_available_as_of may only carry an evidenced date. The "
            "conservative policy month belongs in policy_available_month; "
            "writing it here would present an assumption as provenance."
        )
    return MonthlyAvailability(
        reference_month=str(reference_month)[:7],
        source_available_as_of=source_available_as_of,
        policy_available_month=policy_available_month(reference_month, lag_months),
        availability_basis=(
            "verified_historical_measurement" if historical_timing_verified
            else AVAILABILITY_BASIS
        ),
        latest_vintage_used=True,
        point_in_time_supported=bool(historical_timing_verified),
    )


def assert_measured_lag_not_claimed(policy: dict) -> None:
    """Raise if the conservative policy lag is presented as a measurement.

    Two months is what this project imposes on itself, not what EPPO was
    observed to do. Once a policy number is described as measured, every
    downstream reader is entitled to treat it as evidence, and there is none.
    """
    if policy.get("operational_lag_is_measured"):
        raise PolicyError(
            "operational_lag_is_measured is true, but no EPPO publication delay "
            "was ever measured; the two-month lag is a conservative project "
            "policy and must be recorded as one"
        )
    if policy.get("minimum_verified_publication_lag_months") is not None:
        raise PolicyError(
            "minimum_verified_publication_lag_months is set to "
            f"{policy['minimum_verified_publication_lag_months']}, but no capture "
            "or listing established a first-release date; it must stay null"
        )
    basis = str(policy.get("availability_basis", ""))
    if basis and basis != AVAILABILITY_BASIS:
        raise PolicyError(
            f"availability_basis is {basis!r}; EPPO availability rests on the "
            f"conservative policy and must be recorded as {AVAILABILITY_BASIS!r}"
        )


def select_monthly_source_available_at_issue(monthly_source_table, issue_month: str,
                                             lag_months: int = POLICY_LAG_MONTHS) -> list:
    """Rows a forecast issued in ``issue_month`` is permitted to read.

    A row qualifies only when ``policy_available_month <= issue_month``, which is
    the same rule as ``reference_month <= issue_month - lag``. Both are checked;
    a row whose stored policy month disagrees with its reference month raises
    rather than being quietly accepted, because a mis-stamped row is exactly how
    a leak would enter unnoticed.
    """
    issue = str(issue_month)[:7]
    latest = permitted_reference_month(issue, lag_months)
    selected = []
    for row in monthly_source_table:
        reference = str(row.get("reference_month"))[:7]
        stamped = row.get("policy_available_month")
        expected = policy_available_month(reference, lag_months)
        if stamped is not None and str(stamped)[:7] != expected:
            raise PolicyError(
                f"row for {reference} carries policy_available_month {stamped}, "
                f"but the {lag_months}-month policy gives {expected}; refusing to "
                "select from a table whose availability stamps are inconsistent"
            )
        if row.get("source_available_as_of") is not None:
            raise PolicyError(
                f"row for {reference} carries source_available_as_of "
                f"{row['source_available_as_of']}, but EPPO historical release "
                "timing was never measured; this field must stay null"
            )
        if str(expected)[:7] <= issue and reference <= latest:
            selected.append(row)
    selected.sort(key=lambda r: (r.get("series_id", ""), str(r.get("reference_month"))))
    return selected
