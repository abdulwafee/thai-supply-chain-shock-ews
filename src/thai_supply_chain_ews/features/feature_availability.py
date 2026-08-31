"""When a commodity feature becomes usable — Task C2.

Three different months are kept apart on purpose, because collapsing them is
how a feature silently becomes available before its evidence existed:

``source_available_month``
    When the underlying observation was actually first PUBLISHED, measured from
    the archived issue that carried it (C1.5-R2, verified for all 65 months).

``policy_available_month``
    Reference month plus the project's operational lag. A POLICY choice.

``feature_available_month``
    ``max`` of the policy month and EVERY input's source-available month. A
    multi-month transformation is only as available as its latest input, never
    as available as its final reference month alone.

The measured publication lag (1) and the operational lag (2) are separate
numbers and are stored separately. The operational lag is a margin for estimate
settling; it is not a measurement, and nothing here may present it as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = [
    "LagZeroProhibitedError",
    "AvailabilityError",
    "AvailabilityPolicy",
    "PRIMARY_POLICY",
    "SENSITIVITY_POLICY",
    "POLICIES",
    "add_months",
    "policy_available_month",
    "feature_available_month",
    "assert_inputs_published_by",
]


class AvailabilityError(ValueError):
    """An availability rule was violated."""


class LagZeroProhibitedError(AvailabilityError):
    """A zero (or negative) lag was requested.

    Month t's completed value does not exist at any forecast origin inside
    month t. This is structural (C1.5 AD-R36), not a gap in evidence, so a
    zero lag is rejected rather than warned about.
    """


def add_months(month: str, delta: int) -> str:
    """Shift an ISO month-start date by whole calendar months."""
    anchor = date.fromisoformat(month)
    total = anchor.year * 12 + (anchor.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1).isoformat()


@dataclass(frozen=True)
class AvailabilityPolicy:
    """A lag policy. Exactly one policy is primary; the rest are sensitivity."""

    name: str
    operational_lag_months: int
    minimum_publication_lag_months: int
    is_primary: bool
    label: str
    basis: str

    def __post_init__(self) -> None:
        if self.operational_lag_months <= 0:
            raise LagZeroProhibitedError(
                f"Policy {self.name!r} requests operational_lag_months="
                f"{self.operational_lag_months}. Lag zero is prohibited: the "
                "completed value for month t does not exist at any forecast "
                "origin inside month t."
            )
        if self.operational_lag_months < self.minimum_publication_lag_months:
            raise AvailabilityError(
                f"Policy {self.name!r} would use a lag of "
                f"{self.operational_lag_months} month(s), below the MEASURED "
                f"minimum publication lag of {self.minimum_publication_lag_months}."
            )
        if not self.is_primary and self.label != "sensitivity_only":
            raise AvailabilityError(
                f"Non-primary policy {self.name!r} must be labelled "
                f"'sensitivity_only', not {self.label!r}."
            )
        if self.is_primary and self.label == "sensitivity_only":
            raise AvailabilityError(
                f"Policy {self.name!r} cannot be both primary and sensitivity_only."
            )


# The measured publication lag is 1 month (C1.5-R2, all 65 reference months
# available at t+1). The PRIMARY policy adds one month of margin because the
# newest months of each issue are subject to revision. That margin is a policy
# choice and is labelled as one everywhere it appears.
PRIMARY_POLICY = AvailabilityPolicy(
    name="operational_lag_2m",
    operational_lag_months=2,
    minimum_publication_lag_months=1,
    is_primary=True,
    label="primary",
    basis=(
        "Measured minimum publication lag of 1 month (C1.5-R2, verified across "
        "all 65 reference months) plus one month of POLICY margin for revision "
        "settling. The margin is not a measurement."
    ),
)

# Available for a labelled sensitivity run only. It rests on the same archived
# publication evidence, so it is not speculative — but it carries no revision
# margin, and it is never the default output.
SENSITIVITY_POLICY = AvailabilityPolicy(
    name="publication_lag_1m",
    operational_lag_months=1,
    minimum_publication_lag_months=1,
    is_primary=False,
    label="sensitivity_only",
    basis=(
        "The MEASURED publication lag with no revision margin. Permitted for a "
        "clearly-labelled sensitivity comparison only; never the primary table, "
        "and not compared against any target in C2."
    ),
)

POLICIES: dict[str, AvailabilityPolicy] = {
    PRIMARY_POLICY.name: PRIMARY_POLICY,
    SENSITIVITY_POLICY.name: SENSITIVITY_POLICY,
}


def policy_available_month(reference_month: str, policy: AvailabilityPolicy) -> str:
    """Reference month shifted by the policy's operational lag."""
    return add_months(reference_month, policy.operational_lag_months)


def feature_available_month(
    reference_month: str,
    source_available_months: list[str],
    policy: AvailabilityPolicy,
) -> str:
    """The later of the policy month and every input's publication month.

    Taking only the final month's availability would let a 12-month change be
    published before one of its own inputs existed whenever an early input was
    delayed. The max is over ALL inputs.
    """
    if not source_available_months:
        raise AvailabilityError(
            f"No source-available months supplied for {reference_month}; "
            "availability cannot be derived from nothing."
        )
    return max([policy_available_month(reference_month, policy), *source_available_months])


def assert_inputs_published_by(
    available_month: str,
    source_available_months: list[str],
    context: str,
) -> None:
    """Fail if any lineage input was first published after the feature is usable."""
    late = sorted(m for m in source_available_months if m > available_month)
    if late:
        raise AvailabilityError(
            f"{context}: input observation(s) first published in {late} are after "
            f"the feature's available month {available_month}. Using this feature "
            "at that origin would consume data that did not yet exist."
        )
