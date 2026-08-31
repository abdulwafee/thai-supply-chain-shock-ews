"""When a conditioned feature becomes usable — Task C4.

A conditioned feature depends on TWO things: a commodity observation and an I/O
exposure coefficient. It is available only when BOTH are, so:

    conditioned_available_month = max(base_feature_available_month,
                                      structural_available_by)

The second term is the one that is easy to get wrong. The I/O table's
**reference year is 2015**, but that is the year it DESCRIBES, not the date it
was published. Backdating the matrix to 2015 would hand a 2024 forecast origin a
structure that nobody could read until 2020 — a four-year leak that would look
like nothing at all in the output.

Equally, the download timestamp is not historical availability: these files were
re-hosted during NESDC's 2025 site migration, and using that date would make the
matrix look unavailable for the entire development window.

What is used instead is the publisher's own stated publication date for the
download item.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = [
    "StructuralAvailabilityError",
    "FutureDatedInputError",
    "AVAILABILITY_STATUSES",
    "StructuralAvailability",
    "add_months",
    "conditioned_available_month",
    "assert_not_future_dated",
]

AVAILABILITY_STATUSES = (
    "verified_before_development",
    "verified_after_development_start",
    "upper_bound_only",
    "unresolved",
)


class StructuralAvailabilityError(ValueError):
    """The structural source's availability does not support the requested use."""


class FutureDatedInputError(StructuralAvailabilityError):
    """An input claims to be available before it could possibly have existed."""


def add_months(month: str, delta: int) -> str:
    anchor = date.fromisoformat(month)
    total = anchor.year * 12 + (anchor.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1).isoformat()


@dataclass(frozen=True)
class StructuralAvailability:
    """When the I/O structure became usable, and on what evidence."""

    structural_reference_year: str
    structural_available_by: str
    evidence_type: str
    evidence_url: str
    document_date: str | None
    publication_date: str | None
    evidence_checksum: str
    status: str
    byte_identity_verified_at_that_date: bool
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in AVAILABILITY_STATUSES:
            raise StructuralAvailabilityError(f"Unknown status {self.status!r}.")
        reference_start = f"{self.structural_reference_year}-01-01"
        if self.structural_available_by <= reference_start:
            raise StructuralAvailabilityError(
                f"structural_available_by {self.structural_available_by} is not "
                f"after the reference year {self.structural_reference_year}. The "
                "reference year is what the table DESCRIBES, never when it was "
                "published; backdating it would leak years of structure."
            )

    def supports_origin(self, origin_month: str) -> bool:
        """Was the structure readable by this forecast origin?"""
        return self.structural_available_by[:7] <= origin_month[:7]

    def assert_supports_primary(self, first_development_origin: str) -> None:
        """The primary matrix may proceed only if the structure predates development."""
        if self.status == "unresolved":
            raise StructuralAvailabilityError(
                "Structural availability is unresolved; the primary conditioned "
                "matrix may not proceed."
            )
        if not self.supports_origin(first_development_origin):
            raise StructuralAvailabilityError(
                f"The structure became available {self.structural_available_by}, "
                f"after the first development origin {first_development_origin}. "
                "The primary matrix may not proceed."
            )


def conditioned_available_month(
    base_feature_available_month: str, availability: StructuralAvailability
) -> str:
    """The LATER of the commodity feature and the structural source.

    Never earlier than either input: a feature built from two things is only as
    available as the slower one.
    """
    structural_month = availability.structural_available_by[:7] + "-01"
    return max(base_feature_available_month, structural_month)


def assert_not_future_dated(
    reference_month: str, available_month: str, context: str
) -> None:
    """A feature may not be usable before the month it describes has ended."""
    if available_month <= reference_month:
        raise FutureDatedInputError(
            f"{context}: available month {available_month} is not after reference "
            f"month {reference_month}. A completed month's value cannot be usable "
            "at or before that month's own start."
        )
