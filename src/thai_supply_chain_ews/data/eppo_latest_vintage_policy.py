"""The EPPO latest-vintage use policy and its availability contract (C6.5).

C6 established two facts that pull in opposite directions: the ex-refinery
values are retrievable with complete monthly presence, and their historical
release timing cannot be reconstructed from the sources inspected. C6.5 turns
that into an explicit decision instead of letting it drift.

The decision is to proceed on a **release-lag-aware latest-vintage** basis, the
same footing D3 already put the MPI target on. What makes that safe to state is
keeping two things apart that look alike:

* a **measured** publication delay, which does not exist here, so
  ``minimum_verified_publication_lag_months`` stays ``None``; and
* a **policy** delay, a conservative two-month assumption the project imposes
  on itself, recorded as ``operational_policy_lag_months = 2`` with
  ``operational_lag_is_measured = False``.

A policy date is therefore never written into ``source_available_as_of``. That
field means "the source is evidenced to have been public by this date" and
stays ``None`` for every historical observation; the policy lives in
``policy_available_month`` beside it, with ``availability_basis`` naming which
is which. Collapsing them would manufacture provenance out of an assumption.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

__all__ = [
    "CAPTURE_EVIDENCE_CLASSES",
    "CONTEMPORANEOUS_WINDOW_DAYS",
    "POLICY_LAG_MONTHS",
    "PolicyError",
    "CaptureAssessment",
    "ObservationAvailability",
    "assert_reference_month_permitted",
    "classify_capture",
    "observation_availability",
    "permitted_reference_month",
    "policy_available_month",
]

#: The conservative project policy. NOT a measurement.
POLICY_LAG_MONTHS = 2

#: Preregistered classification convention, not an empirical finding: a capture
#: within this many days of the effective date is treated as contemporaneous
#: enough to serve as an upper bound. A wider gap says nothing about first
#: release, because the archiver may simply have visited late.
CONTEMPORANEOUS_WINDOW_DAYS = 31

CAPTURE_EVIDENCE_CLASSES = (
    "contemporaneous_capture_upper_bound",
    "retrospective_capture_not_timing_evidence",
    "capture_identity_unverified",
    "capture_after_effective_date_only",
    "unresolved",
)


class PolicyError(ValueError):
    """The latest-vintage policy was asked to permit something it forbids."""


def _add_months(month: str, delta: int) -> str:
    year, index = int(str(month)[:4]), int(str(month)[5:7])
    total = year * 12 + (index - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def policy_available_month(reference_month: str, lag_months: int = POLICY_LAG_MONTHS) -> str:
    """``reference_month + lag`` under the conservative policy.

    This is an assumption the project imposes, not a date the source states.
    """
    if lag_months < 0:
        raise PolicyError(f"policy lag must be non-negative; got {lag_months}")
    return _add_months(reference_month, lag_months)


def permitted_reference_month(issue_month: str, lag_months: int = POLICY_LAG_MONTHS) -> str:
    """Latest reference month usable at operational issue month *t*: ``t - lag``."""
    return _add_months(issue_month, -lag_months)


def assert_reference_month_permitted(
    reference_month: str, issue_month: str, lag_months: int = POLICY_LAG_MONTHS
) -> None:
    """Raise unless ``reference_month <= issue_month - lag``.

    Lag 0 (same month) and lag 1 are both rejected by construction, because the
    policy is two months and nothing measured justifies a shorter one.
    """
    latest = permitted_reference_month(issue_month, lag_months)
    if str(reference_month)[:7] > latest:
        raise PolicyError(
            f"reference month {reference_month} exceeds the latest permitted "
            f"{latest} at issue month {issue_month} under the {lag_months}-month "
            "conservative policy lag"
        )


@dataclass
class CaptureAssessment:
    """One third-party capture record, classified for what it can support."""

    effective_date: str
    capture_date: str
    capture_provider: str
    captured_url: str
    delay_days: int
    contemporaneous: bool
    original_bytes_available: bool
    source_identity_validated: bool
    proves_first_release_date: bool
    provides_upper_bound_only: bool
    evidence_class: str
    note: str = None

    def to_dict(self) -> dict:
        return asdict(self)


def classify_capture(
    effective_date: str,
    capture_date: str,
    capture_provider: str = "internet_archive_cdx",
    captured_url: str = None,
    original_bytes_available: bool = False,
    source_identity_validated: bool = False,
    window_days: int = CONTEMPORANEOUS_WINDOW_DAYS,
) -> CaptureAssessment:
    """Classify what a capture record actually supports.

    A capture NEVER proves a first-release date. At best it shows the document
    was public by the capture date, which is an upper bound. If the bytes were
    not fetched and the identity not checked, even that is weakened, and the
    record is marked ``capture_identity_unverified``.
    """
    delay = (dt.date.fromisoformat(str(capture_date))
             - dt.date.fromisoformat(str(effective_date))).days
    contemporaneous = 0 <= delay <= window_days

    if delay < 0:
        evidence = "unresolved"
        note = (
            f"capture {capture_date} precedes the effective date {effective_date}; "
            "incoherent and not accepted as evidence"
        )
    elif not source_identity_validated:
        evidence = "capture_identity_unverified"
        note = (
            "The capture record was read from the index only; the archived bytes "
            "were not fetched and the document identity was not validated, so the "
            "record cannot be relied on even as an upper bound."
        )
    elif contemporaneous:
        evidence = "contemporaneous_capture_upper_bound"
        note = (
            f"Captured {delay} days after the effective date, so the document was "
            "public by then. This is an UPPER BOUND on availability, never the "
            "first-release date."
        )
    else:
        evidence = "retrospective_capture_not_timing_evidence"
        note = (
            f"Captured {delay} days after the effective date. The archiver may "
            "simply have visited late, so this says nothing about when the "
            "document first appeared."
        )

    return CaptureAssessment(
        effective_date=str(effective_date),
        capture_date=str(capture_date),
        capture_provider=capture_provider,
        captured_url=captured_url,
        delay_days=delay,
        contemporaneous=contemporaneous,
        original_bytes_available=bool(original_bytes_available),
        source_identity_validated=bool(source_identity_validated),
        # No capture, however close, establishes a first release.
        proves_first_release_date=False,
        provides_upper_bound_only=(evidence == "contemporaneous_capture_upper_bound"),
        evidence_class=evidence,
        note=note,
    )


@dataclass
class ObservationAvailability:
    """Availability fields for one historical observation, kept separate."""

    reference_month: str
    source_available_as_of: str = None
    policy_available_month: str = None
    availability_basis: str = "conservative_policy_not_historical_measurement"
    historical_timing_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def observation_availability(
    reference_month: str,
    source_available_as_of: str = None,
    historical_timing_verified: bool = False,
    lag_months: int = POLICY_LAG_MONTHS,
) -> ObservationAvailability:
    """Build the availability fields, refusing to conflate policy with evidence.

    ``source_available_as_of`` may only be set when timing is actually verified.
    Passing a policy-derived date into it raises.
    """
    if source_available_as_of is not None and not historical_timing_verified:
        raise PolicyError(
            "source_available_as_of may only carry an evidenced date. A "
            "policy-derived month belongs in policy_available_month, and writing "
            "it here would present an assumption as provenance."
        )
    return ObservationAvailability(
        reference_month=str(reference_month)[:7],
        source_available_as_of=source_available_as_of,
        policy_available_month=policy_available_month(reference_month, lag_months),
        availability_basis=(
            "verified_historical_measurement" if historical_timing_verified
            else "conservative_policy_not_historical_measurement"
        ),
        historical_timing_verified=bool(historical_timing_verified),
    )


def summarize_captures(assessments) -> dict:
    """Delay statistics over UPPER-BOUND records only.

    Retrospective and unverified records are counted but excluded from the
    statistics, because averaging them would describe archiver behaviour rather
    than publisher behaviour.
    """
    items = list(assessments)
    upper = [a for a in items if a.evidence_class == "contemporaneous_capture_upper_bound"]
    counts = {}
    for assessment in items:
        counts[assessment.evidence_class] = counts.get(assessment.evidence_class, 0) + 1
    summary = {
        "captures_total": len(items),
        "evidence_class_counts": dict(sorted(counts.items())),
        "usable_upper_bounds": len(upper),
        "any_capture_proves_first_release": False,
        "minimum_verified_publication_lag_months": None,
        "note": (
            "No first-release date is established by any capture, so the minimum "
            "verified publication lag stays null. Delay statistics below, if any, "
            "describe upper bounds only and are never used to set the operational "
            "lag."
        ),
    }
    if upper:
        delays = sorted(a.delay_days for a in upper)
        summary["upper_bound_delay_days"] = {
            "min": delays[0],
            "median": delays[len(delays) // 2],
            "max": delays[-1],
            "n": len(delays),
        }
    return summary
