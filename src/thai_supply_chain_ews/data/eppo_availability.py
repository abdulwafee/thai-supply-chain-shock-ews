"""Historical availability evidence for the EPPO archive (Task C6).

The archive's values are retrievable. When they became *public* is a different
question, and this module refuses to let the first answer stand in for the
second.

Every EPPO attachment now sits in a WordPress media library whose upload
timestamps are all from the 2026 site migration. A migration timestamp says when
the file was re-hosted, not when it was first published — the same trap D2 found
in the OIE i-Index archive, where sixteen 2016 issues shared one 2017 stamp.
So ``migration_timestamp_only`` is a distinct status, and it does **not**
support a point-in-time value.

Independent corroboration (a third-party capture observed at or after the
effective date) is what upgrades an issue. Absent that, an issue whose only
evidence is its own internal date is ``reference_date_only``: the document
asserts what day it describes, not that anyone could read it that day.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

__all__ = [
    "AVAILABILITY_STATUSES",
    "POINT_IN_TIME_STATUSES",
    "SUPPORTING_STATUSES",
    "AvailabilityError",
    "AvailabilityAssessment",
    "assess_issue_availability",
    "dataset_point_in_time_status",
    "transformation_eligibility",
]

AVAILABILITY_STATUSES = (
    "direct_original_publication_evidence",
    "attachment_timestamp_corroborated",
    "legacy_listing_corroborated",
    "current_and_legacy_listing_corroborated",
    "rehosted_with_original_date_evidence",
    "migration_timestamp_only",
    "attachment_last_modified_only",
    "reference_date_only",
    "unresolved",
)

#: Statuses that actually support a point-in-time value. A migration timestamp
#: and a bare reference date do not appear here, by design.
SUPPORTING_STATUSES = (
    "direct_original_publication_evidence",
    "attachment_timestamp_corroborated",
    "legacy_listing_corroborated",
    "current_and_legacy_listing_corroborated",
    "rehosted_with_original_date_evidence",
)

POINT_IN_TIME_STATUSES = ("full", "partial", "not_supported")


class AvailabilityError(ValueError):
    """Availability evidence was asked to support more than it can."""


@dataclass
class AvailabilityAssessment:
    effective_date: str
    availability_evidence_status: str
    available_as_of: str = None
    available_as_of_verified: bool = False
    historical_point_in_time_value_supported: bool = False
    evidence_note: str = None
    independent_capture_date: str = None
    migration_upload_date: str = None

    def to_dict(self) -> dict:
        return asdict(self)


def assess_issue_availability(
    effective_date: str,
    migration_upload_date: str = None,
    independent_capture_date: str = None,
    legacy_listing_date: str = None,
    attachment_last_modified: str = None,
    original_publication_date: str = None,
) -> AvailabilityAssessment:
    """Classify one issue's availability evidence, most specific first."""
    if original_publication_date:
        return AvailabilityAssessment(
            effective_date=effective_date,
            availability_evidence_status="direct_original_publication_evidence",
            available_as_of=original_publication_date,
            available_as_of_verified=True,
            historical_point_in_time_value_supported=True,
            evidence_note="The publisher states the original publication date.",
            migration_upload_date=migration_upload_date,
        )

    if independent_capture_date:
        # A capture BEFORE the effective date would be incoherent and is not
        # accepted as corroboration of that issue.
        if independent_capture_date < effective_date:
            return AvailabilityAssessment(
                effective_date=effective_date,
                availability_evidence_status="unresolved",
                evidence_note=(
                    f"independent capture {independent_capture_date} precedes the "
                    f"effective date {effective_date}; incoherent, not accepted"
                ),
                independent_capture_date=independent_capture_date,
                migration_upload_date=migration_upload_date,
            )
        status = ("current_and_legacy_listing_corroborated" if legacy_listing_date
                  else "attachment_timestamp_corroborated")
        return AvailabilityAssessment(
            effective_date=effective_date,
            availability_evidence_status=status,
            available_as_of=independent_capture_date,
            available_as_of_verified=True,
            historical_point_in_time_value_supported=True,
            evidence_note=(
                "An independent capture observed the document at or after its "
                "effective date, so it was public by the capture date. The "
                "capture date is an UPPER BOUND on availability, not the "
                "publication date itself."
            ),
            independent_capture_date=independent_capture_date,
            migration_upload_date=migration_upload_date,
        )

    if legacy_listing_date:
        return AvailabilityAssessment(
            effective_date=effective_date,
            availability_evidence_status="legacy_listing_corroborated",
            available_as_of=legacy_listing_date,
            available_as_of_verified=True,
            historical_point_in_time_value_supported=True,
            migration_upload_date=migration_upload_date,
        )

    if migration_upload_date:
        return AvailabilityAssessment(
            effective_date=effective_date,
            availability_evidence_status="migration_timestamp_only",
            available_as_of=None,
            available_as_of_verified=False,
            historical_point_in_time_value_supported=False,
            evidence_note=(
                "The only timestamp is the 2026 WordPress migration upload. It "
                "records when the file was re-hosted, NOT when it was first "
                "published, so it cannot date availability."
            ),
            migration_upload_date=migration_upload_date,
        )

    if attachment_last_modified:
        return AvailabilityAssessment(
            effective_date=effective_date,
            availability_evidence_status="attachment_last_modified_only",
            available_as_of=None,
            available_as_of_verified=False,
            historical_point_in_time_value_supported=False,
            migration_upload_date=migration_upload_date,
        )

    return AvailabilityAssessment(
        effective_date=effective_date,
        availability_evidence_status="reference_date_only",
        available_as_of=None,
        available_as_of_verified=False,
        historical_point_in_time_value_supported=False,
        evidence_note=(
            "The document asserts which day it describes. That is not evidence "
            "that anyone could read it on that day."
        ),
    )


def dataset_point_in_time_status(assessments) -> dict:
    """Aggregate to a dataset-level status.

    ``full`` requires EVERY required observation to carry supporting evidence.
    Anything less is ``partial`` or ``not_supported`` — a mostly-evidenced
    dataset is not a point-in-time dataset.
    """
    items = list(assessments)
    if not items:
        return {"status": "not_supported", "supported": 0, "total": 0, "fraction": 0.0}
    supported = [a for a in items if a.historical_point_in_time_value_supported]
    fraction = len(supported) / len(items)
    if len(supported) == len(items):
        status = "full"
    elif supported:
        status = "partial"
    else:
        status = "not_supported"
    return {
        "status": status,
        "supported": len(supported),
        "total": len(items),
        "fraction": fraction,
        "status_counts": {
            s: sum(1 for a in items if a.availability_evidence_status == s)
            for s in sorted({a.availability_evidence_status for a in items})
        },
    }


def transformation_eligibility(earliest_date: str, required_start: str,
                               months_of_prehistory_needed: int) -> dict:
    """Whether a transformation's required PREHISTORY exists.

    Coverage from 2022-01 is sufficient for a level and for short changes, but a
    twelve-month change referencing 2022-01 needs 2021-01 data. Reporting one
    eligibility for all transformations would hide exactly that.
    """
    if not earliest_date:
        return {"eligible": False, "reason": "no observations"}
    year, month = int(required_start[:4]), int(required_start[5:7])
    total = year * 12 + (month - 1) - months_of_prehistory_needed
    needed = f"{total // 12:04d}-{total % 12 + 1:02d}-01"
    # Month granularity: the first document of a month covers that month even
    # when it is dated the 3rd rather than the 1st.
    eligible = str(earliest_date)[:7] <= needed[:7]
    return {
        "eligible": eligible,
        "required_start": required_start,
        "months_of_prehistory_needed": months_of_prehistory_needed,
        "earliest_source_date_needed": needed,
        "earliest_source_date_observed": str(earliest_date),
        "reason": (
            "prehistory present"
            if eligible
            else f"needs data from {needed}, earliest observed is {earliest_date}"
        ),
    }


def assert_not_after_issue_date(observation_date: str, issue_date: str) -> None:
    """An observation after the operational issue date may never be used."""
    if str(observation_date) > str(issue_date):
        raise AvailabilityError(
            f"observation {observation_date} falls after the operational issue date "
            f"{issue_date}; it was not available when the forecast was issued"
        )


def completed_reference_month(issue_month: str) -> str:
    """The completed month *t-1* for operational issue month *t*."""
    year, month = int(str(issue_month)[:4]), int(str(issue_month)[5:7])
    total = year * 12 + (month - 1) - 1
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_bounds(month: str):
    year, index = int(month[:4]), int(month[5:7])
    first = dt.date(year, index, 1)
    last = dt.date(year + (index == 12), (index % 12) + 1, 1) - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()
