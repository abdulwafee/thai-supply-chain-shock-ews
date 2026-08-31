"""Publication-timing table, revision audit, and timing decision (Task C1.5).

Production implementation. Answers three separable questions and keeps them
separable:

1. **When did reference month t first become public?** — from archived issue
   publication dates, never from the current download timestamp.
2. **Has the latest workbook revised what was first published?** — comparing
   like with like, by rounding the workbook value to the precision the archived
   PDF actually displayed, so display rounding is never mistaken for a revision.
3. **What lag is therefore safe?** — set only if the evidence covers every
   required forecast origin, and left null with a stated blocker otherwise.

A lag decision is never guessed. A month label is never treated as a release
timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

__all__ = [
    "REVISION_STATUSES",
    "RevisionRecord",
    "TimingRow",
    "build_publication_timing_table",
    "classify_revision",
    "decide_timing_contract",
    "default_timing_config_path",
    "load_timing_config",
    "month_end",
    "publication_delay_stats",
    "revision_audit",
    "round_to_display",
    "estimate_transition_audit",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]

REVISION_STATUSES = (
    "first_release_observed",
    "first_release_documented_estimate",
    "latest_vintage_revised",
    "rounding_only_difference",
    "definition_break",
    "revision_status_unresolved",
)

# C1 established these pricing-benchmark changes. A month at or after a break is
# not comparable across vintages as a NUMERICAL revision: the two vintages are
# quoting different things. Counting such a month as a revision inflates the
# statistics with a semantic change — the coal spot-to-futures switch would
# otherwise appear as a triple-digit "revision".
DEFINITION_BREAKS = {
    "coal_australia_usd_mt": ["2022-02-01"],
    "palm_oil_usd_mt": ["2021-01-01", "2024-11-01", "2025-02-01"],
}


def definition_break_applies(
    series_id: str, reference_month: str, first_release_issue_month: str | None = None
) -> str | None:
    """Return the break month that makes this observation non-comparable, if any.

    A definition break only breaks the FIRST-RELEASE vs LATEST comparison when
    the regime now governing the month began AFTER the month was first
    published — that is the case where the two vintages genuinely describe
    different things.

    A break that was already in force at first release does not: both vintages
    quote the same benchmark, so any difference is an ordinary revision. Being
    loose here over-attributes — palm oil's -0.35% move in 2025-11 is a routine
    revision, not a consequence of the February 2025 benchmark change.
    """
    breaks = sorted(DEFINITION_BREAKS.get(series_id, []))
    governing = [b for b in breaks if reference_month >= b]
    if not governing:
        return None
    latest_break = governing[-1]
    if first_release_issue_month is None:
        return latest_break
    return latest_break if latest_break > first_release_issue_month else None


def default_timing_config_path() -> Path:
    return PROJECT_ROOT / "configs" / "commodity_timing.yaml"


def load_timing_config(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else default_timing_config_path()
    if not path.is_file():
        raise FileNotFoundError(f"Timing config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def month_end(month: str) -> date:
    """Last calendar day of the month given a first-of-month string."""
    d = date.fromisoformat(str(month))
    first_of_next = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return first_of_next - timedelta(days=1)


def add_months(month: str, delta: int) -> str:
    d = date.fromisoformat(str(month))
    total = d.year * 12 + (d.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1).isoformat()


# --- publication timing ------------------------------------------------------


@dataclass
class TimingRow:
    reference_month: str
    first_seen_issue: str | None
    first_seen_issue_date: str | None
    web_publish_date: str | None
    reference_month_end: str
    calendar_delay_days: int | None
    available_month: str | None
    availability_evidence_url: str | None
    availability_status: str
    quality_flag: str
    # True only when the first-seen issue is the month IMMEDIATELY following the
    # reference month. With a sparse archive the earliest issue that happens to
    # CONTAIN month t may be several issues later, in which case its publication
    # date is an UPPER BOUND on availability, not the actual first release.
    # Averaging upper bounds into a delay statistic would overstate the lag.
    is_true_first_release: bool = False


def build_publication_timing_table(
    required_months: list[str], issues: list
) -> list[TimingRow]:
    """One row per required reference month.

    A month with no archived issue is reported as `no_archived_issue` with null
    delay — never interpolated from neighbouring months, because an interpolated
    release date would be indistinguishable from a measured one downstream.
    """
    from thai_supply_chain_ews.data.world_bank_pink_sheet_vintages import (
        select_first_release_issue,
    )

    rows: list[TimingRow] = []
    for month in required_months:
        issue = select_first_release_issue(issues, month)
        end = month_end(month)
        if issue is None:
            rows.append(
                TimingRow(
                    reference_month=month,
                    first_seen_issue=None,
                    first_seen_issue_date=None,
                    web_publish_date=None,
                    reference_month_end=end.isoformat(),
                    calendar_delay_days=None,
                    available_month=None,
                    availability_evidence_url=None,
                    availability_status="no_archived_issue",
                    quality_flag="availability_unverified_not_interpolated",
                    is_true_first_release=False,
                )
            )
            continue

        issue_date = issue.issue_date
        delay = None
        available_month = None
        expected_first_issue_month = add_months(month, 1)
        is_true_first = issue.issue_month == expected_first_issue_month

        # Refinement backed by direct evidence: if the t+1 issue WAS obtained and
        # verifiably does not carry this reference month, then the earliest issue
        # that does carry it really is the first release, not an upper bound.
        # The World Bank's February 2025 issue is exactly this case — it skipped
        # January 2025, which first appeared in the March 2025 issue.
        if not is_true_first:
            expected_issue = next(
                (i for i in issues if i.issue_month == expected_first_issue_month), None
            )
            if expected_issue is not None and (
                month not in expected_issue.monthly_reference_months
            ):
                is_true_first = True
                skipped_note = (
                    f"issue {expected_first_issue_month} was obtained and does not "
                    f"contain {month}; first appearance in {issue.issue_month} is "
                    "therefore the true first release"
                )
            else:
                skipped_note = None
        else:
            skipped_note = None

        if issue_date:
            delay = (date.fromisoformat(issue_date) - end).days
            available_month = date.fromisoformat(issue_date).replace(day=1).isoformat()
            if is_true_first:
                status = "verified_from_archived_issue"
                flag = skipped_note or "ok"
            else:
                status = "upper_bound_only"
                flag = (
                    "earliest_archived_issue_is_later_than_t_plus_1; delay is an upper "
                    "bound, not the first release"
                )
        else:
            status = "issue_found_publication_date_missing"
            flag = "publication_date_unknown_not_inferred"
        rows.append(
            TimingRow(
                reference_month=month,
                first_seen_issue=issue.issue_name,
                first_seen_issue_date=issue_date,
                # The World Bank web-publish date is not exposed independently of
                # the PDF; recorded as null rather than assumed equal to it.
                web_publish_date=None,
                reference_month_end=end.isoformat(),
                calendar_delay_days=delay,
                available_month=available_month,
                availability_evidence_url=issue.url,
                availability_status=status,
                quality_flag=flag,
                is_true_first_release=is_true_first,
            )
        )
    return rows


def publication_delay_stats(rows: list[TimingRow]) -> dict:
    # Only TRUE first releases may enter the delay statistics; upper-bound rows
    # would inflate every figure.
    verified = [r for r in rows if r.availability_status == "verified_from_archived_issue"]
    delays = sorted(
        r.calendar_delay_days for r in verified if r.calendar_delay_days is not None
    )
    upper_bound_rows = [r for r in rows if r.availability_status == "upper_bound_only"]
    next_month_ok = [
        r for r in verified
        if r.available_month == add_months(r.reference_month, 1)
    ]
    if not delays:
        return {
            "verified_months": 0,
            "upper_bound_only_months": len(upper_bound_rows),
            "min_delay_days": None, "median_delay_days": None, "max_delay_days": None,
            "delay_distribution": {},
            "months_available_in_t_plus_1": 0,
            "all_verified_available_by_end_of_following_month": None,
            "note": "No archived issue supplied a publication date.",
        }
    middle = len(delays) // 2
    median = (
        float(delays[middle])
        if len(delays) % 2
        else (delays[middle - 1] + delays[middle]) / 2.0
    )
    return {
        "verified_months": len(verified),
        "upper_bound_only_months": len(upper_bound_rows),
        "min_delay_days": delays[0],
        "median_delay_days": median,
        "max_delay_days": delays[-1],
        "delay_distribution": {str(d): delays.count(d) for d in sorted(set(delays))},
        "months_available_in_t_plus_1": len(next_month_ok),
        "all_verified_available_by_end_of_following_month": len(next_month_ok) == len(verified),
    }


# --- revision audit ----------------------------------------------------------


def round_to_display(value: float, decimal_places: int) -> float:
    """Round a latest-vintage value to the precision the PDF actually displayed.

    Without this, a workbook value of 136.85 and a printed 136.9 would register
    as a revision when they are the same number shown at different precision.
    """
    return round(float(value), int(decimal_places))


@dataclass
class RevisionRecord:
    series_id: str
    reference_month: str
    first_release_value: float
    first_release_text: str
    decimal_places: int
    latest_value: float
    latest_rounded_to_display: float
    absolute_revision: float
    percentage_revision: float | None
    status: str
    # C1.5-R3: the DOCUMENTED estimate status, derived from the Description
    # rule — not from the "a/" index-membership token that R1/R2 misread.
    estimate_status: str
    first_seen_issue: str
    notes: list[str] = field(default_factory=list)


def classify_revision(
    first_release: float,
    latest: float,
    decimal_places: int,
    is_documented_estimate: bool,
    same_vintage: bool = False,
) -> tuple[str, float, float | None]:
    """Return (status, absolute_revision, percentage_revision).

    ``is_documented_estimate`` affects only the LABEL of a zero-difference row.
    It never changes whether a difference is counted as a revision, so the
    numerical revision results are independent of estimate classification —
    which is the separation C1.5-R3 exists to restore.

    `same_vintage` marks the degenerate case where the archived issue and the
    workbook are the SAME release — an apparent zero difference then proves
    nothing about stability, because the value has had no opportunity to be
    revised yet.
    """
    latest_rounded = round_to_display(latest, decimal_places)
    absolute = latest_rounded - first_release
    percentage = (absolute / first_release * 100.0) if first_release else None

    if same_vintage:
        return "revision_status_unresolved", absolute, percentage

    # A latest-vintage value within half a display unit of the printed value is
    # THE SAME NUMBER shown at coarser precision, not a revision. The tolerance
    # is the primary test: comparing rounded values alone is wrong, because
    # Python's round() is banker's rounding while the publisher's spreadsheet
    # rounds half away from zero, so 136.85 printed as "136.9" would round back
    # to 136.8 here and register a phantom 0.1 revision.
    tolerance = 0.5 * (10 ** -int(decimal_places))
    difference = latest - first_release
    # Epsilon guard: a value exactly half a display unit away lands on the
    # boundary, where binary floating point puts |136.85 - 136.9| at
    # 0.05000000000001 and a bare <= would call it a revision.
    if abs(difference) <= tolerance + 1e-9:
        if absolute == 0:
            return (
                "first_release_documented_estimate"
                if is_documented_estimate
                else "first_release_observed"
            ), 0.0, 0.0
        return "rounding_only_difference", 0.0, 0.0
    return "latest_vintage_revised", absolute, percentage


def revision_audit(
    issues: list,
    latest_values: dict[str, dict[str, float]],
    workbook_vintage_month: str | None = None,
    required_window: tuple[str, str] | None = None,
) -> dict:
    """Compare each series' first-release value with the latest workbook value.

    ``required_window`` scopes the headline statistics to the reference months the
    project actually needs. Archived issues also display months from before the
    window (the February 2021 issue carries late-2020 columns), and counting those
    inflates every per-series total above the number of months under contract.
    Out-of-window months are reported separately rather than dropped.
    """
    from thai_supply_chain_ews.data.world_bank_pink_sheet_vintages import (
        select_first_release_issue,
    )

    records: list[RevisionRecord] = []
    all_months = sorted({m for i in issues for m in i.monthly_reference_months})
    if required_window is None:
        in_window = set(all_months)
    else:
        low, high = required_window
        in_window = {m for m in all_months if low <= m <= high}
    out_of_window = sorted(set(all_months) - in_window)
    for month in all_months:
        issue = select_first_release_issue(issues, month)
        if issue is None:
            continue
        same_vintage = (
            workbook_vintage_month is not None
            and issue.issue_month == workbook_vintage_month
        )
        for series_id, observations in issue.observations.items():
            observation = next(
                (o for o in observations if o.reference_month == month), None
            )
            if observation is None:
                continue
            latest = latest_values.get(series_id, {}).get(month)
            if latest is None:
                records.append(
                    RevisionRecord(
                        series_id=series_id, reference_month=month,
                        first_release_value=observation.displayed_value,
                        first_release_text=observation.displayed_text,
                        decimal_places=observation.decimal_places,
                        latest_value=float("nan"), latest_rounded_to_display=float("nan"),
                        absolute_revision=float("nan"), percentage_revision=None,
                        status="revision_status_unresolved",
                        estimate_status=observation.estimate_status,
                        first_seen_issue=issue.issue_name,
                        notes=["No latest-vintage value available for comparison."],
                    )
                )
                continue
            status, absolute, percentage = classify_revision(
                observation.displayed_value, latest, observation.decimal_places,
                observation.estimate_status == "source_documented_estimate",
                same_vintage,
            )
            notes = []
            break_month = definition_break_applies(series_id, month, issue.issue_month)
            if break_month and status == "latest_vintage_revised":
                # A semantic change, not a numerical revision.
                status = "definition_break"
                notes.append(
                    f"Governed by the documented definition break at {break_month}; "
                    "excluded from numerical revision statistics."
                )
            if same_vintage:
                notes.append(
                    "Archived issue and workbook are the SAME vintage; an apparent "
                    "zero difference is not evidence of stability."
                )
            records.append(
                RevisionRecord(
                    series_id=series_id, reference_month=month,
                    first_release_value=observation.displayed_value,
                    first_release_text=observation.displayed_text,
                    decimal_places=observation.decimal_places,
                    latest_value=float(latest),
                    latest_rounded_to_display=round_to_display(
                        latest, observation.decimal_places
                    ),
                    absolute_revision=absolute, percentage_revision=percentage,
                    status=status, estimate_status=observation.estimate_status,
                    first_seen_issue=issue.issue_name, notes=notes,
                )
            )

    out_of_window_records = [r for r in records if r.reference_month not in in_window]
    records = [r for r in records if r.reference_month in in_window]

    by_series: dict[str, dict] = {}
    for series_id in sorted({r.series_id for r in records}):
        rows = [r for r in records if r.series_id == series_id]
        definition_break_rows = [r for r in rows if r.status == "definition_break"]
        comparable = [
            r for r in rows
            if r.status not in ("revision_status_unresolved", "definition_break")
        ]
        revised = [r for r in comparable if r.status == "latest_vintage_revised"]
        unchanged = [
            r for r in comparable
            if r.status in ("first_release_observed",
                            "first_release_documented_estimate")
        ]
        rounding_only = [r for r in comparable if r.status == "rounding_only_difference"]
        absolutes = sorted(abs(r.absolute_revision) for r in revised)
        percentages = sorted(
            abs(r.percentage_revision) for r in revised if r.percentage_revision is not None
        )
        largest = sorted(
            revised, key=lambda r: abs(r.absolute_revision), reverse=True
        )[:3]
        by_series[series_id] = {
            "comparable_observations": len(comparable),
            "unresolved_observations": len(rows) - len(comparable),
            "apparent_unchanged": len(unchanged),
            "rounding_only_differences": len(rounding_only),
            "revisions_beyond_rounding": len(revised),
            "revision_frequency": (len(revised) / len(comparable)) if comparable else None,
            "median_absolute_revision": (
                absolutes[len(absolutes) // 2] if absolutes else None
            ),
            "max_absolute_revision": absolutes[-1] if absolutes else None,
            "median_percentage_revision": (
                percentages[len(percentages) // 2] if percentages else None
            ),
            "max_percentage_revision": percentages[-1] if percentages else None,
            "largest_revision_months": [
                {
                    "reference_month": r.reference_month,
                    "first_release": r.first_release_value,
                    "latest": r.latest_value,
                    "absolute_revision": r.absolute_revision,
                    "percentage_revision": r.percentage_revision,
                }
                for r in largest
            ],
            "documented_estimate_observations": sum(
                1 for r in rows if r.estimate_status == "source_documented_estimate"
            ),
            "estimate_status_unknown_observations": sum(
                1 for r in rows if r.estimate_status == "unknown"
            ),
            "definition_break_observations": len(definition_break_rows),
            "definition_break_months": sorted(
                r.reference_month for r in definition_break_rows
            ),
            # RENAMED in C1.5-R3. This counts documented first-release
            # estimates whose value DIFFERS FROM THE CURRENT WORKBOOK. It was
            # previously called `estimate_to_final_transitions`, which claimed
            # two things the evidence does not support: that the "a/" token
            # meant estimate, and that the latest vintage is final.
            "documented_estimates_differing_from_latest_vintage": sum(
                1 for r in rows
                if r.estimate_status == "source_documented_estimate"
                and r.status == "latest_vintage_revised"
            ),
            "unresolved_same_vintage_comparisons": sum(
                1 for r in rows if r.status == "revision_status_unresolved"
            ),
        }
    oow_by_series: dict[str, dict] = {}
    for series_id in sorted({r.series_id for r in out_of_window_records}):
        rows = [r for r in out_of_window_records if r.series_id == series_id]
        oow_by_series[series_id] = {
            "observations": len(rows),
            "revisions_beyond_rounding": sum(
                1 for r in rows if r.status == "latest_vintage_revised"
            ),
        }
    return {
        "records": [r.__dict__ for r in records],
        "by_series": by_series,
        "statuses_used": sorted({r.status for r in records}),
        "required_window": list(required_window) if required_window else None,
        "in_window_reference_months": len(in_window),
        "out_of_window": {
            "reference_months": out_of_window,
            "count": len(out_of_window),
            "observations": len(out_of_window_records),
            "by_series": oow_by_series,
            "note": (
                "Displayed by archived issues but outside the contracted reference "
                "window. Reported for completeness; excluded from headline "
                "per-series statistics so no series can exceed the window's month "
                "count."
            ),
        },
    }


def estimate_transition_audit(
    issues: list,
    latest_values: dict[str, dict[str, float]],
    required_window: tuple[str, str] | None = None,
) -> dict:
    """Track documented estimates forward through later archived issues.

    C1.5-R1/R2 reported ``estimate_to_final_transitions``. That name asserted
    FINALITY, which no Pink Sheet issue establishes — a later value is simply a
    later vintage. This audit replaces the claim with what the archive can
    actually show:

    * ``first_non_estimated_vintage`` — the first issue in which the month is no
      longer among the two most recent displayed months, i.e. no longer covered
      by the documented estimate rule. It is NOT a claim of permanent finality.
    * months with no such later issue in the archive are **right-censored** and
      are reported as unresolved rather than folded into either outcome.
    """
    from thai_supply_chain_ews.data.world_bank_pink_sheet_vintages import (
        ESTIMATE_RULE_SERIES,
        select_first_release_issue,
    )

    ordered_issues = sorted(issues, key=lambda i: i.issue_month)
    low, high = required_window if required_window else (None, None)

    per_series: dict[str, dict] = {}
    for series_id in sorted(ESTIMATE_RULE_SERIES):
        months = sorted(
            {
                observation.reference_month
                for issue in ordered_issues
                for observation in issue.observations.get(series_id, [])
            }
        )
        if low is not None:
            months = [m for m in months if low <= m <= high]

        records = []
        for month in months:
            first_issue = select_first_release_issue(ordered_issues, month)
            if first_issue is None:
                continue
            first_observation = first_issue.observation(series_id, month)
            if first_observation is None:
                continue

            record = {
                "reference_month": month,
                "first_release_issue": first_issue.issue_name,
                "first_release_issue_month": first_issue.issue_month,
                "first_release_value": first_observation.displayed_value,
                "first_release_text": first_observation.displayed_text,
                "first_release_estimate_status": first_observation.estimate_status,
                "estimate_evidence_type": first_observation.estimate_evidence_type,
            }

            # Walk forward for the first issue where the rule no longer covers
            # this month. Only later issues count; the first-release issue
            # itself never qualifies.
            qualifying = None
            for issue in ordered_issues:
                if issue.issue_month <= first_issue.issue_month:
                    continue
                observation = issue.observation(series_id, month)
                if observation is None:
                    continue
                if observation.estimate_status == "not_covered_by_current_estimate_rule":
                    qualifying = (issue, observation)
                    break

            if qualifying is None:
                record.update(
                    transition_status="right_censored_no_later_qualifying_issue",
                    first_non_estimated_vintage=None,
                    first_non_estimated_value=None,
                    revised_before_first_non_estimated_vintage=None,
                    note=(
                        "No archived issue displays this month outside the two "
                        "most recent columns, so whether the estimate settled "
                        "cannot be observed. Reported as unresolved, not as "
                        "unchanged."
                    ),
                )
            else:
                issue, observation = qualifying
                changed = observation.displayed_value != first_observation.displayed_value
                record.update(
                    transition_status="first_non_estimated_vintage_observed",
                    first_non_estimated_vintage=issue.issue_name,
                    first_non_estimated_vintage_month=issue.issue_month,
                    first_non_estimated_value=observation.displayed_value,
                    first_non_estimated_estimate_status=observation.estimate_status,
                    revised_before_first_non_estimated_vintage=changed,
                    note=(
                        "`first_non_estimated_vintage` means only that the "
                        "documented two-month estimate rule no longer covers "
                        "this month in that issue. It is NOT a claim that the "
                        "value is permanently final."
                    ),
                )

            latest = latest_values.get(series_id, {}).get(month)
            if latest is None:
                record["latest_vintage_difference"] = None
            else:
                rounded = round_to_display(
                    float(latest), first_observation.decimal_places
                )
                record["latest_vintage_value"] = float(latest)
                record["latest_vintage_difference"] = (
                    rounded - first_observation.displayed_value
                )
            records.append(record)

        documented = [
            r for r in records
            if r["first_release_estimate_status"] == "source_documented_estimate"
        ]
        resolved = [
            r for r in documented
            if r["transition_status"] == "first_non_estimated_vintage_observed"
        ]
        censored = [
            r for r in documented
            if r["transition_status"] == "right_censored_no_later_qualifying_issue"
        ]
        revised = [
            r for r in resolved
            if r["revised_before_first_non_estimated_vintage"] is True
        ]
        unchanged = [
            r for r in resolved
            if r["revised_before_first_non_estimated_vintage"] is False
        ]
        differs_from_workbook = [
            r for r in documented
            if r.get("latest_vintage_difference") not in (None, 0.0)
        ]

        per_series[series_id] = {
            "reference_months_examined": len(records),
            "first_releases_documented_as_estimates": len(documented),
            "estimate_status_unknown": sum(
                1 for r in records
                if r["first_release_estimate_status"] == "unknown"
            ),
            "estimates_with_a_later_non_estimated_vintage": len(resolved),
            "estimates_revised_before_first_non_estimated_vintage": len(revised),
            "estimates_unchanged_at_first_non_estimated_vintage": len(unchanged),
            "right_censored_or_unresolved": len(censored),
            "right_censored_months": [r["reference_month"] for r in censored],
            "documented_estimates_differing_from_latest_vintage": len(
                differs_from_workbook
            ),
            "records": records,
        }

    return {
        "estimate_rule_series": sorted(ESTIMATE_RULE_SERIES),
        "by_series": per_series,
        "finality_claimed": False,
        "terminology_note": (
            "No observation is described as `final`. `first_non_estimated_vintage` "
            "records the first archived issue in which the documented estimate "
            "rule no longer covers the month; later revision remains possible and "
            "is measured separately."
        ),
    }


# --- timing decision ---------------------------------------------------------


def decide_timing_contract(
    timing_rows: list[TimingRow],
    required_origins: list[str],
    revision_by_series: dict,
) -> dict:
    """Separate PUBLICATION timing from REVISION safety.

    The first C1.5 run collapsed the two into a single `minimum_safe_lag_months`
    and then set it to null partly because revisions exist. That conflated two
    different questions:

    * **When was the observation first published?** — answerable from archived
      issue dates alone. Revision behaviour is irrelevant to it, so a measured
      publication lag must never be nulled by revision findings.
    * **When does a value stop changing?** — a separate question that archived
      first releases can only answer if a fixed lag guarantees finality. It may
      legitimately stay null.

    A month with no verified issue stays unavailable and is never interpolated.
    """
    verified = [r for r in timing_rows if r.availability_status == "verified_from_archived_issue"]
    upper_bound_rows = [r for r in timing_rows if r.availability_status == "upper_bound_only"]
    verified_months = {r.reference_month for r in verified}
    delays = [r.calendar_delay_days for r in verified if r.calendar_delay_days is not None]
    covered_origins = [o for o in required_origins if o in verified_months]
    missing_origins = [o for o in required_origins if o not in verified_months]

    # --- publication timing ---------------------------------------------------
    # The lag is measured in MONTHS between a reference month and the month its
    # value first became available. An earlier version asked only "is every
    # month published in t+1?" and returned null the moment one issue slipped —
    # which discards a perfectly measurable fact. The smallest lag that is
    # ALWAYS sufficient is the maximum observed month-gap, not the typical one.
    month_gaps: list[int] = []
    for row in verified:
        if not row.available_month:
            continue
        reference = date.fromisoformat(row.reference_month)
        available = date.fromisoformat(row.available_month)
        month_gaps.append(
            (available.year - reference.year) * 12 + (available.month - reference.month)
        )

    gap_distribution = {str(g): month_gaps.count(g) for g in sorted(set(month_gaps))}
    typical_gap = (
        max(gap_distribution, key=lambda k: gap_distribution[k]) if gap_distribution else None
    )

    # Upper-bound months carry real information about the WORST case even though
    # their exact first release is unknown: we know the value was available by
    # the issue that carried it. A lag rule that ignored them would be proven
    # only for the months that happened to be easy, so their bounds are folded
    # into the always-sufficient lag while staying out of the measured
    # distribution above.
    upper_bound_gaps: list[int] = []
    for row in upper_bound_rows:
        if not row.available_month:
            continue
        reference = date.fromisoformat(row.reference_month)
        available = date.fromisoformat(row.available_month)
        upper_bound_gaps.append(
            (available.year - reference.year) * 12 + (available.month - reference.month)
        )

    if not verified or not month_gaps:
        publication_lag = None
        publication_status = "unresolved"
        publication_basis = "No verified archived issue supplied a publication date."
    else:
        publication_lag = max(month_gaps + upper_bound_gaps)
        no_evidence_rows = [
            r for r in timing_rows if r.availability_status == "no_archived_issue"
        ]
        publication_status = (
            "verified" if not missing_origins and not no_evidence_rows
            else "partially_verified"
        )
        late = [
            r.reference_month for r in verified
            if r.available_month
            and (
                (date.fromisoformat(r.available_month).year
                 - date.fromisoformat(r.reference_month).year) * 12
                + (date.fromisoformat(r.available_month).month
                   - date.fromisoformat(r.reference_month).month)
            )
            > int(typical_gap)
        ]
        bound_note = ""
        if upper_bound_gaps:
            bound_months = [r.reference_month for r in upper_bound_rows]
            bound_note = (
                f" {len(upper_bound_rows)} month(s) {bound_months} have an UPPER BOUND "
                f"only (available by t+{max(upper_bound_gaps)}), and that bound is "
                "folded into the always-sufficient lag."
            )
        publication_basis = (
            f"{len(verified)} reference months have a verified first-release issue. "
            f"{gap_distribution.get(typical_gap, 0)} of them became available in month "
            f"t+{typical_gap} ({min(delays)}-{max(delays)} days after month end). "
            f"The smallest lag sufficient for EVERY observed month is "
            f"t+{publication_lag}"
            + (f", because {late} slipped to a later issue." if late else ".")
            + bound_note
        )

    # Under the calendar-boundary contract, a value first published after its own
    # month end does not exist at an origin inside that month.
    same_month_available = bool(verified) and all(
        (r.calendar_delay_days or 0) <= 0 for r in verified
    )

    # --- revision safety ------------------------------------------------------
    revised_series = {
        series_id: stats.get("revisions_beyond_rounding") or 0
        for series_id, stats in revision_by_series.items()
        if (stats.get("revisions_beyond_rounding") or 0) > 0
    }
    comparable_total = sum(
        (stats.get("comparable_observations") or 0) for stats in revision_by_series.values()
    )
    if not revision_by_series or comparable_total == 0:
        revision_status = "unresolved"
        revision_safe_lag = None
        revision_basis = ["No comparable first-release observations were available."]
    elif not revised_series:
        revision_status = "verified_no_revisions_observed"
        revision_safe_lag = None
        revision_basis = [
            "No revision beyond display rounding was observed, but absence of observed "
            "revision over this sample does not guarantee finality at any fixed lag."
        ]
    else:
        revision_status = "revisions_observed"
        revision_safe_lag = None
        revision_basis = [
            f"Revisions beyond display rounding observed in {sorted(revised_series)}.",
            "No fixed lag is shown to guarantee final values, so revision_safe_lag_months "
            "stays null. This does NOT null the publication lag, which measures a "
            "different thing.",
        ]

    archived_coverage = (
        len(verified_months & set(required_origins)) / len(required_origins)
        if required_origins
        else 0.0
    )

    coverage_fraction = (
        len(verified_months) / len(timing_rows) if timing_rows else 0.0
    )
    # --- eligibility, stated as separate decisions -------------------------
    # Publication timing and revision safety answer different questions, so
    # they get different fields. A series can be perfectly timed and still
    # revise; nothing here may collapse the two.
    publication_timing_verified = publication_status == "verified"
    point_in_time_supported = (
        "full"
        if publication_timing_verified and coverage_fraction == 1.0 and not missing_origins
        else "partial"
        if verified_months
        else "none"
    )
    eligible_for_primary_backtest = (
        point_in_time_supported == "full" and not upper_bound_rows
    )

    return {
        "minimum_publication_lag_months": publication_lag,
        # R2 §6 eligibility contract.
        "eligible_for_primary_backtest": eligible_for_primary_backtest,
        "eligible_for_primary_backtest_basis": (
            "Every required reference month has a MEASURED first release from a "
            "validated issue, and every required forecast origin is covered."
            if eligible_for_primary_backtest
            else "Withheld: coverage is incomplete or some months are bounded only."
        ),
        # Latest-vintage series stay available for a labelled sensitivity run
        # regardless of point-in-time coverage; that is what they are for.
        "eligible_for_sensitivity_analysis": True,
        "point_in_time_supported": point_in_time_supported,
        "coverage_fraction": coverage_fraction,
        "publication_timing_verified": publication_timing_verified,
        "revision_status": revision_status,
        "publication_timing_status": publication_status,
        "publication_timing_basis": publication_basis,
        "publication_delay_days_range": (
            [min(delays), max(delays)] if delays else None
        ),
        "same_reference_month_available_at_calendar_origin": same_month_available,
        "lag_zero_prohibited": not same_month_available,
        # Latest-vintage data is eligible for a LATEST-VINTAGE historical
        # evaluation only. Lagging it does not make it point-in-time.
        "latest_vintage_backtest_eligible": True,
        "latest_vintage_is_point_in_time": False,
        "upper_bound_only_months": [r.reference_month for r in upper_bound_rows],
        "archived_first_release_backtest_eligible": bool(verified) and not missing_origins,
        "archived_first_release_caveat": (
            f"{len(upper_bound_rows)} month(s) have an upper-bound availability only; "
            "their first-release value comes from the earliest obtainable issue and must "
            "be treated as available no earlier than that issue."
            if upper_bound_rows else None
        ),
        "publication_lag_month_distribution": gap_distribution,
        "typical_publication_lag_months": int(typical_gap) if typical_gap else None,
        "archived_first_release_coverage": {
            "verified_reference_months": len(verified_months),
            "reference_months_examined": len(timing_rows),
            "fraction_of_reference_window": (
                len(verified_months) / len(timing_rows) if timing_rows else 0.0
            ),
            "required_forecast_origins": len(required_origins),
            "covered_origins": len(covered_origins),
            "origin_coverage_fraction": archived_coverage,
            "missing_origins": missing_origins,
        },
        "revision_audit_status": revision_status,
        "revision_safe_lag_months": revision_safe_lag,
        "revision_basis": revision_basis,
        # Operational recommendation = publication requirement, plus a margin for
        # estimate settling. Labelled as policy, never as measurement.
        "recommended_operational_lag_months": (
            (publication_lag + 1) if publication_lag is not None else None
        ),
        "recommended_operational_lag_basis": (
            "Publication requirement plus one month of margin, because the most recent "
            "months of each issue are estimates. The margin is a POLICY choice, not a "
            "measured quantity."
        ),
        "months_without_verified_issue_remain_unavailable": True,
    }
