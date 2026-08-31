"""Issue inventory, coverage and revision logic for the EPPO archive (Task C6).

Three distinctions carry this module.

**Dates are not interchangeable.** ``reference_date``, ``effective_date``,
``page_first_published_at``, ``attachment_last_modified``,
``embedded_document_date``, ``downloaded_at_utc`` and ``available_as_of`` are
separate fields with separate meanings, and the download timestamp is never
availability.

**A price change is not a revision.** EPPO publishes a new structure whenever
the price changes, so a different value on a different effective date is
ordinary market movement. A revision can only be assessed when two documents
describe the **same** product on the **same** effective date within the same
semantic regime.

**A gap is not automatically a missing issue.** The observed weekday profile
shows a working-day schedule, so weekends are expected absences. Where the
schedule cannot be verified from official documentation the gap is recorded as
``schedule_unresolved`` rather than counted as a failure.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

__all__ = [
    "GAP_STATUSES",
    "REVISION_CLASSES",
    "ArchiveIssue",
    "classify_gap",
    "classify_revision",
    "monthly_coverage",
    "weekday_profile",
]

GAP_STATUSES = (
    "weekend",
    "verified_public_holiday",
    "no_new_issue_expected",
    "possible_missing_issue",
    "schedule_unresolved",
    "document_retrieval_failure",
)

REVISION_CLASSES = (
    "single_vintage_only",
    "same_date_same_value",
    "same_date_revised_value",
    "duplicate_document",
    "incomparable_definition",
    "unresolved",
)


@dataclass
class ArchiveIssue:
    """One dated archive entry. Every date concept has its own field."""

    reference_date: str = None
    effective_date: str = None
    page_title: str = None
    detail_page_url: str = None
    discovery_method: str = None
    attachment_url: str = None
    attachment_filename: str = None
    page_first_published_at: str = None
    page_modified_at: str = None
    attachment_last_modified: str = None
    filename_embedded_timestamp: str = None
    embedded_document_date: str = None
    file_size_bytes: int = None
    mime_type: str = None
    magic_format: str = None
    sha256: str = None
    duplicate_content_group: str = None
    retrieval_status: str = None
    validation_status: str = None
    rejection_reason: str = None
    downloaded_at_utc: str = None
    available_as_of: str = None
    availability_evidence_status: str = "unresolved"
    available_as_of_verified: bool = False
    historical_point_in_time_value_supported: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def weekday_profile(dates) -> dict:
    """Empirical weekday counts, used to infer the publication schedule."""
    counter = Counter()
    for value in dates:
        counter[dt.date.fromisoformat(str(value)).strftime("%a")] += 1
    return dict(counter)


def classify_gap(day: str, observed_dates, schedule_verified: bool,
                 holidays=()) -> str:
    """Classify a calendar day with no document.

    ``schedule_verified`` must come from official documentation. When it is
    false, an unexplained weekday gap is ``schedule_unresolved`` — reporting it
    as a missing issue would assert a publication obligation that has not been
    established.
    """
    if day in set(observed_dates):
        raise ValueError(f"{day} has a document; it is not a gap")
    weekday = dt.date.fromisoformat(day).weekday()
    if weekday >= 5:
        return "weekend"
    if day in set(holidays):
        return "verified_public_holiday"
    if not schedule_verified:
        return "schedule_unresolved"
    return "possible_missing_issue"


def classify_revision(observations) -> str:
    """Classify documents sharing ``(series_id, effective_date, regime)``.

    Only same-key documents are comparable. A value that differs across
    different effective dates is ordinary price movement and never reaches this
    function.
    """
    if not observations:
        return "unresolved"
    if len(observations) == 1:
        return "single_vintage_only"

    regimes = {o.get("semantic_regime_id") for o in observations}
    if len(regimes) > 1:
        return "incomparable_definition"

    digests = {o.get("source_document_sha256") for o in observations}
    values = {round(float(o["value"]), 10) for o in observations if o.get("value") is not None}

    if len(digests) == 1:
        return "duplicate_document"
    if len(values) == 1:
        return "same_date_same_value"
    return "same_date_revised_value"


def monthly_coverage(issues, start_month: str, end_month: str,
                     schedule_verified: bool = False, holidays=()) -> list:
    """Per-month coverage of the archive, without inventing a gap taxonomy.

    ``expected_issue_count`` is reported as ``None`` when the publication
    schedule is unverified, because an expectation that cannot be sourced is
    not an expectation.
    """
    by_month = defaultdict(list)
    for issue in issues:
        date = issue.effective_date or issue.reference_date
        if date:
            by_month[str(date)[:7]].append(issue)

    months, cursor = [], start_month
    while cursor <= end_month:
        entries = by_month.get(cursor, [])
        valid = [e for e in entries if e.validation_status == "valid"]
        distinct = sorted({e.effective_date for e in valid if e.effective_date})

        year, month = int(cursor[:4]), int(cursor[5:7])
        last_day = (dt.date(year + (month == 12), (month % 12) + 1, 1)
                    - dt.timedelta(days=1)).day
        all_days = [f"{cursor}-{d:02d}" for d in range(1, last_day + 1)]
        observed = set(distinct)
        working_days = [d for d in all_days
                        if dt.date.fromisoformat(d).weekday() < 5]
        gaps = {}
        for day in all_days:
            if day not in observed:
                gaps[day] = classify_gap(day, observed, schedule_verified, holidays)

        months.append({
            "month": cursor,
            "expected_issue_count": len(working_days) if schedule_verified else None,
            "observed_entry_count": len(entries),
            "valid_attachment_count": len(valid),
            "distinct_effective_dates": len(distinct),
            "earliest_date": distinct[0] if distinct else None,
            "latest_date": distinct[-1] if distinct else None,
            "working_days_in_month": len(working_days),
            "document_day_coverage_fraction": (
                len(distinct) / len(working_days) if working_days else None
            ),
            "gap_status_counts": dict(Counter(gaps.values())),
            "unresolved_days": sorted(d for d, s in gaps.items()
                                      if s == "schedule_unresolved"),
            "has_at_least_one_valid_observation": bool(valid),
            "complete_monthly_aggregation_defensible": (
                bool(valid) and schedule_verified and not any(
                    s == "possible_missing_issue" for s in gaps.values()
                )
            ),
        })
        month += 1
        if month == 13:
            year, month = year + 1, 1
        cursor = f"{year:04d}-{month:02d}"
    return months
