"""Monthly source-level aggregation of the EPPO daily archive (Task C7).

The rule is preregistered and deliberately dull:

    arithmetic mean of validated observed official document-days

Each distinct valid official document-day inside the reference month counts
once. Nothing is synthesised for a weekend, nothing is carried forward when a
price does not change, and no value is weighted by how long it stood. Those
three refusals are what stop the statistic from quietly becoming something else:

* forward-filling would turn it into a calendar-day mean, which would need a
  proof that a published price stays in force until superseded — a proof this
  project does not have;
* duration weighting would need the same proof and would additionally change the
  meaning of a month with an unusual publication pattern;
* using observations from an incomplete current month would make a value that
  changes as the month fills, so the same reference month would take different
  values depending on when it was computed.

What the number means, exactly: *the mean ex-refinery price across the validated
official EPPO document-days observed in the completed reference month*. It is not
a calendar-day mean, not a trading-day mean, not a transaction price, and not a
point-in-time value.

Approval is per product-month and it is a gate, not a summary. A month is
``approved`` only when its entire discovered inventory was attempted, retrieved,
validated and reconciled. Everything else keeps a status that names what is
missing, and January 2024 H-DIESEL keeps a null value with an explicit semantic
gap rather than a blend price standing in for a product that was not published.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from .eppo_source_availability import monthly_availability_fields
from .eppo_source_lineage import daily_lineage_checksum, monthly_lineage_checksum

__all__ = [
    "AGGREGATION_RULE",
    "AGGREGATION_RULE_VERSION",
    "MONTHLY_STATUSES",
    "MONTHLY_STATISTIC_DESCRIPTION",
    "PROHIBITED_DESCRIPTIONS",
    "AggregationError",
    "assert_monthly_row_defensible",
    "assert_no_transformation_columns",
    "assert_statistic_description",
    "MonthlyInventory",
    "aggregate_series_month",
    "build_monthly_table",
    "dataset_approval",
    "month_key",
    "month_range",
    "monthly_inventory",
]

AGGREGATION_RULE = "arithmetic_mean_of_validated_observed_official_document_days"
AGGREGATION_RULE_VERSION = "c7_v1"

MONTHLY_STATISTIC_DESCRIPTION = (
    "Mean ex-refinery price across validated official EPPO document-days "
    "observed in the completed reference month."
)

#: Descriptions this statistic must never be given. Kept as data so the tests
#: can assert against the same list the documentation is generated from.
PROHIBITED_DESCRIPTIONS = (
    "calendar_day_mean",
    "trading_day_mean",
    "transaction_price",
    "price_paid_by_every_industrial_purchaser",
    "point_in_time_monthly_mean",
)

MONTHLY_STATUSES = (
    "approved",
    "semantic_definition_gap",
    "no_valid_product_observation",
    "unresolved_document_retrieval",
    "unresolved_document_identity",
    "same_date_conflicting_value",
    "incomplete_inventory_validation",
    "unknown_layout",
    "unit_or_definition_break",
)

#: Blend diesels published in January 2024 in place of ordinary H-DIESEL. Named
#: here only so the gap can be *described*; never used as a value.
H_DIESEL_GAP_FLAG = (
    "ordinary_h_diesel_not_published_blend_substitution_prohibited"
)


class AggregationError(ValueError):
    """Aggregation was asked to produce a number its inputs cannot support."""


#: Column-name fragments that would make this a feature table rather than a
#: source table. C7 creates none of them.
PROHIBITED_COLUMN_FRAGMENTS = (
    "log_change", "logchange", "pct_change", "percentage_change", "return",
    "lag_", "_lag", "lagged", "volatility", "zscore", "z_score", "shock",
    "exposure", "interaction", "correlation", "mutual_information",
    "granger", "importance", "mpi", "target",
)


def assert_statistic_description(description: str) -> None:
    """Raise if the monthly mean is given a description it cannot carry.

    Calling it a calendar-day mean, a trading-day mean, a transaction price or a
    point-in-time value each asserts something the source has not established,
    and each would survive review precisely because it sounds ordinary.
    """
    normalized = re.sub(r"[^a-z0-9]+", "_", str(description).lower()).strip("_")
    for banned in PROHIBITED_DESCRIPTIONS:
        if banned in normalized:
            raise AggregationError(
                f"the monthly statistic may not be described as {banned!r}: "
                f"{MONTHLY_STATISTIC_DESCRIPTION}"
            )


def assert_no_transformation_columns(columns) -> None:
    """Raise if a source table has grown a predictive-feature column."""
    for column in columns:
        name = str(column).lower()
        for fragment in PROHIBITED_COLUMN_FRAGMENTS:
            if fragment in name:
                raise AggregationError(
                    f"column {column!r} looks like a predictive transformation "
                    f"({fragment!r}); C7 is source ingestion and creates none"
                )


def assert_monthly_row_defensible(row: dict, inventory: MonthlyInventory) -> None:
    """Raise unless a monthly row's status, value and inventory agree.

    Three failures this catches: an approved month that quietly rests on an
    unresolved document, a gap month carrying an interpolated value, and any row
    that presents the policy month as measured availability.
    """
    status = row["aggregation_status"]
    if status not in MONTHLY_STATUSES:
        raise AggregationError(f"unknown aggregation status {status!r}")
    if row.get("source_available_as_of") is not None:
        raise AggregationError(
            f"{row['series_id']} {row['reference_month']} carries "
            "source_available_as_of, but EPPO release timing was never measured"
        )
    if row.get("point_in_time_supported"):
        raise AggregationError(
            f"{row['series_id']} {row['reference_month']} claims point-in-time "
            "support, which no EPPO observation has"
        )
    if status in (
        "semantic_definition_gap", "no_valid_product_observation",
        "same_date_conflicting_value", "unit_or_definition_break",
    ) and row.get("monthly_value") is not None:
        raise AggregationError(
            f"{row['series_id']} {row['reference_month']} has status {status} but "
            f"carries the value {row['monthly_value']}; a month whose definition "
            "is absent or contested may not be filled"
        )
    if status == "approved":
        if inventory.unresolved_days:
            raise AggregationError(
                f"{row['series_id']} {row['reference_month']} is approved while "
                f"{len(inventory.unresolved_days)} discovered document-days are "
                "unresolved; a failed document may not be silently omitted"
            )
        if row.get("monthly_value") is None:
            raise AggregationError(
                f"{row['series_id']} {row['reference_month']} is approved with no "
                "value"
            )
        if row["valid_document_day_count"] != inventory.content_valid_document_days:
            raise AggregationError(
                f"{row['series_id']} {row['reference_month']} averages "
                f"{row['valid_document_day_count']} days but "
                f"{inventory.content_valid_document_days} validated"
            )


def month_range(start_month: str, end_month: str) -> list:
    months, cursor = [], str(start_month)[:7]
    end = str(end_month)[:7]
    while cursor <= end:
        months.append(cursor)
        year, index = int(cursor[:4]), int(cursor[5:7])
        index += 1
        if index == 13:
            year, index = year + 1, 1
        cursor = f"{year:04d}-{index:02d}"
    return months


def month_key(date: str) -> str:
    """``YYYY-MM`` of an ISO date, so month grouping never compares day strings."""
    return str(date)[:7]


@dataclass
class MonthlyInventory:
    """Completeness of one month, measured against the discovered inventory.

    ``expected_issue_count`` stays ``None``: EPPO publishes no schedule document,
    so an expectation would be invented rather than sourced. A weekday with no
    discovered entry is therefore not a missing document; a discovered entry that
    could not be retrieved or validated *is* an unresolved inventory item.
    """

    month: str
    expected_issue_count: object = None
    expected_schedule_status: str = "unresolved"
    discovered_document_days: int = 0
    retrieval_attempted_days: int = 0
    successfully_retrieved_days: int = 0
    content_valid_document_days: int = 0
    duplicate_days: int = 0
    rejected_days: int = 0
    unresolved_days: list = field(default_factory=list)
    unresolved_retrieval_days: list = field(default_factory=list)
    unresolved_identity_days: list = field(default_factory=list)
    conflicting_days: list = field(default_factory=list)
    observed_weekdays: dict = field(default_factory=dict)
    first_effective_date: str = None
    last_effective_date: str = None
    inventory_retrieval_fraction: float = None

    def to_dict(self) -> dict:
        return asdict(self)


def monthly_inventory(days, resolutions, start_month: str, end_month: str) -> dict:
    """Per-month inventory reconciliation from discovery through validation.

    ``days`` maps effective date to its discovered candidates; ``resolutions``
    maps effective date to its :class:`DayResolution`. Every discovered day
    appears in exactly one month, so the monthly counts sum back to the
    discovery denominator without inference.
    """
    by_month = {m: MonthlyInventory(month=m) for m in month_range(start_month, end_month)}
    for date in sorted(days):
        key = month_key(date)
        if key not in by_month:
            continue
        entry = by_month[key]
        entry.discovered_document_days += 1
        resolution = resolutions.get(date)
        if resolution is None:
            entry.unresolved_days.append(date)
            continue
        entry.retrieval_attempted_days += 1
        retrieved = resolution.accepted_candidates > 0 or any(
            item.get("retrieval_status") in ("downloaded", "cached_checksum_verified")
            for item in resolution.rejected_candidates
        )
        if retrieved:
            entry.successfully_retrieved_days += 1
        if resolution.status in ("resolved", "same_date_conflicting_value"):
            entry.content_valid_document_days += 1
            weekday = dt.date.fromisoformat(date).strftime("%a")
            entry.observed_weekdays[weekday] = entry.observed_weekdays.get(weekday, 0) + 1
            if entry.first_effective_date is None:
                entry.first_effective_date = date
            entry.last_effective_date = date
        else:
            entry.unresolved_days.append(date)
            if resolution.status == "unresolved_document_retrieval":
                entry.unresolved_retrieval_days.append(date)
            else:
                entry.unresolved_identity_days.append(date)
        if resolution.rejected_candidates:
            entry.rejected_days += 1
        if resolution.duplicate_documents or resolution.content_equivalent_duplicates:
            entry.duplicate_days += 1
        if resolution.conflicts:
            entry.conflicting_days.append(date)

    for entry in by_month.values():
        entry.observed_weekdays = dict(sorted(entry.observed_weekdays.items()))
        entry.unresolved_days = sorted(entry.unresolved_days)
        entry.unresolved_retrieval_days = sorted(entry.unresolved_retrieval_days)
        entry.unresolved_identity_days = sorted(entry.unresolved_identity_days)
        entry.inventory_retrieval_fraction = (
            entry.content_valid_document_days / entry.discovered_document_days
            if entry.discovered_document_days else None
        )
    return by_month


def _mean(values) -> float:
    return sum(values) / len(values)


def aggregate_series_month(series_id: str, reference_month: str, daily_rows,
                           inventory: MonthlyInventory,
                           blend_only_days: int = 0,
                           rule_version: str = AGGREGATION_RULE_VERSION,
                           lag_months: int = None) -> dict:
    """Aggregate one product-month and decide its approval status.

    ``daily_rows`` are the canonical daily rows of this series whose effective
    date falls inside ``reference_month``. They are used exactly as given: no
    day is invented, none is dropped, and a day appears once however many
    byte-identical documents carried it.

    Whether a status carries a value follows one line: a month whose *definition*
    is intact keeps the mean of every day that validated, even when some
    discovered document could not be retrieved — that mean is exactly what the
    rule describes. A month whose definition is absent, partial or contested
    carries ``None``, because the surviving days would produce a number that does
    not mean what the column says it means.
    """
    rows = sorted(
        (r for r in daily_rows if month_key(r["effective_date"]) == month_key(reference_month)),
        key=lambda r: (r["effective_date"], r.get("media_id") or 0),
    )
    valued = [r for r in rows if r.get("value") is not None]
    conflicting = [r for r in rows
                   if r.get("quality_flag") == "same_date_conflicting_value"]
    for row in conflicting:
        if row.get("value") is not None:
            raise AggregationError(
                f"{series_id} {row['effective_date']} is flagged as a same-date "
                "conflict yet carries a value; the conflict must be resolved from "
                "the documents, never averaged away"
            )

    seen_days = set()
    contributions = []
    for row in valued:
        if row["effective_date"] in seen_days:
            raise AggregationError(
                f"{series_id} {reference_month}: effective date "
                f"{row['effective_date']} appears twice in the canonical daily "
                "rows; a document-day may only contribute once"
            )
        seen_days.add(row["effective_date"])
        contributions.append(row)

    labels = {r["source_product_label"] for r in contributions}
    units = {r["unit"] for r in contributions}
    variants = {
        r.get("label_variant_status") for r in contributions
        if r.get("label_variant_status")
    }

    availability = monthly_availability_fields(
        reference_month, **({"lag_months": lag_months} if lag_months is not None else {})
    )

    value = _mean([float(r["value"]) for r in contributions]) if contributions else None
    lineage = monthly_lineage_checksum(
        series_id, reference_month, rule_version, contributions
    )

    # Days whose document validated but which did not publish this product at
    # all. A month with some of these is a PARTIAL definition gap, and a mean
    # over the surviving days is not the month's mean.
    product_absent_days = max(
        0, inventory.content_valid_document_days - len(contributions)
    )

    if conflicting:
        status = "same_date_conflicting_value"
        value = None
        quality = "unresolved_same_date_conflict_blocks_the_month"
    elif not contributions and blend_only_days > 0:
        status = "semantic_definition_gap"
        value = None
        quality = H_DIESEL_GAP_FLAG
    elif not contributions:
        status = "no_valid_product_observation"
        value = None
        quality = "no_validated_document_day_published_this_product"
    elif len(units) > 1 or len(labels) > 1:
        status = "unit_or_definition_break"
        value = None
        quality = f"multiple_definitions_in_one_month: {sorted(labels)} {sorted(units)}"
    elif variants - {"exact_audited_label"}:
        # The month rests on a label that is close to the audited one but not
        # identical. Averaging it would assert an equivalence nobody established.
        status = "unit_or_definition_break"
        value = None
        quality = (
            "unconfirmed_label_variant_equivalence_not_established: "
            f"{sorted(labels)}"
        )
    elif product_absent_days:
        # The month straddles the start or end of a definition gap. Averaging
        # the days that survive would publish a number that is not comparable
        # with a full month under the same label.
        status = "semantic_definition_gap"
        value = None
        quality = (
            f"product_published_on_{len(contributions)}_of_"
            f"{inventory.content_valid_document_days}_validated_document_days_"
            "substitution_and_imputation_prohibited"
        )
    elif inventory.unresolved_days:
        # Name WHY the inventory is incomplete. A discovered attachment that
        # 404s and one whose content belongs to another day are different
        # failures and lead to different follow-up work.
        retrieval = bool(inventory.unresolved_retrieval_days)
        identity = bool(inventory.unresolved_identity_days)
        if retrieval and not identity:
            status = "unresolved_document_retrieval"
        elif identity and not retrieval:
            status = "unresolved_document_identity"
        else:
            status = "incomplete_inventory_validation"
        quality = (
            f"{len(inventory.unresolved_days)}_discovered_document_days_unresolved: "
            f"retrieval={inventory.unresolved_retrieval_days} "
            f"identity={inventory.unresolved_identity_days}"
        )
    elif inventory.content_valid_document_days < inventory.discovered_document_days:
        status = "incomplete_inventory_validation"
        quality = "content_valid_days_below_discovered_days"
    else:
        status = "approved"
        quality = "ok"

    return {
        "series_id": series_id,
        "source_product_label": sorted(labels)[0] if labels else None,
        "reference_month": month_key(reference_month),
        "monthly_value": value,
        "unit": sorted(units)[0] if units else "BAHT/LITRE",
        "aggregation_rule": AGGREGATION_RULE,
        "aggregation_rule_version": rule_version,
        "aggregation_status": status,
        "valid_document_day_count": len(contributions),
        "discovered_document_day_count": inventory.discovered_document_days,
        "rejected_document_day_count": inventory.rejected_days,
        "first_effective_date": contributions[0]["effective_date"] if contributions else None,
        "last_effective_date": contributions[-1]["effective_date"] if contributions else None,
        "source_available_as_of": availability.source_available_as_of,
        "policy_available_month": availability.policy_available_month,
        "availability_basis": availability.availability_basis,
        "latest_vintage_used": availability.latest_vintage_used,
        "point_in_time_supported": availability.point_in_time_supported,
        "semantic_regime_ids": sorted(
            {r["semantic_regime_id"] for r in contributions if r.get("semantic_regime_id")}
        ),
        "quality_flag": quality,
        "monthly_lineage_checksum": lineage,
    }


def build_monthly_table(daily_rows, inventories, series_ids, start_month: str,
                        end_month: str, blend_only_days=None,
                        rule_version: str = AGGREGATION_RULE_VERSION,
                        lag_months: int = None) -> list:
    """One explicit row per ``(series_id, reference_month, rule_version)``.

    A month with no value still gets a row. An absent row would be indistinguishable
    from a month nobody looked at, and the January 2024 H-DIESEL gap is exactly
    the case that must stay visible.
    """
    blend_only_days = blend_only_days or {}
    by_series = defaultdict(list)
    for row in daily_rows:
        by_series[row["series_id"]].append(row)

    table = []
    for series_id in sorted(series_ids):
        for month in month_range(start_month, end_month):
            inventory = inventories.get(month, MonthlyInventory(month=month))
            table.append(
                aggregate_series_month(
                    series_id, month, by_series.get(series_id, []), inventory,
                    blend_only_days=blend_only_days.get((series_id, month), 0),
                    rule_version=rule_version, lag_months=lag_months,
                )
            )
    table.sort(key=lambda r: (r["series_id"], r["reference_month"]))
    seen = set()
    for row in table:
        key = (row["series_id"], row["reference_month"], row["aggregation_rule_version"])
        if key in seen:
            raise AggregationError(f"duplicate canonical monthly key {key}")
        seen.add(key)
    return table


def reconstruct_monthly_value(daily_rows, series_id: str, reference_month: str):
    """Independent re-derivation of one monthly mean, used only for verification.

    Written separately from :func:`aggregate_series_month` on purpose: a check
    that shares the production code path can only prove the code ran twice.
    """
    values = [
        float(row["value"])
        for row in daily_rows
        if row["series_id"] == series_id
        and str(row["effective_date"])[:7] == str(reference_month)[:7]
        and row.get("value") is not None
    ]
    if not values:
        return None
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def dataset_approval(monthly_table, required_series, required_start: str,
                     required_end: str, conditional_series=()) -> dict:
    """Dataset-level approval.

    ``monthly_aggregation_contract_approved`` requires every required month of
    every *required* series to pass. A series listed as conditional — H-DIESEL,
    because of the January 2024 semantic gap — may carry that one documented gap
    without blocking the fuel oils, and fabricating an H-DIESEL value to unblock
    it is exactly what the gap status exists to prevent.
    """
    months = set(month_range(required_start, required_end))
    per_series, failures = {}, []
    for series_id in sorted(set(required_series) | set(conditional_series)):
        rows = [r for r in monthly_table
                if r["series_id"] == series_id and r["reference_month"] in months]
        statuses = {}
        for row in rows:
            statuses[row["aggregation_status"]] = statuses.get(
                row["aggregation_status"], 0
            ) + 1
        not_approved = sorted(
            (r["reference_month"], r["aggregation_status"])
            for r in rows if r["aggregation_status"] != "approved"
        )
        conditional = series_id in set(conditional_series)
        gaps_only = all(
            status == "semantic_definition_gap" for _, status in not_approved
        )
        approved = not not_approved
        per_series[series_id] = {
            "months_required": len(months),
            "months_present": len(rows),
            "status_counts": dict(sorted(statuses.items())),
            "months_not_approved": not_approved,
            "series_approved": approved,
            "series_conditionally_approved": bool(
                conditional and not approved and gaps_only
            ),
            "transformation_readiness_blocked_by": (
                [] if approved else sorted({s for _, s in not_approved})
            ),
        }
        if not approved and not (conditional and gaps_only):
            failures.append(series_id)

    return {
        "required_window": {"start": required_start, "end": required_end},
        "per_series": per_series,
        "monthly_aggregation_contract_approved": not failures,
        "blocking_series": failures,
        "note": (
            "Approval is granted per product-month and aggregated up. A "
            "conditional series keeps its documented semantic gap; no value is "
            "fabricated to make a month pass."
        ),
    }


def attach_daily_lineage(daily_rows) -> list:
    """Stamp each canonical daily row with its lineage checksum, in place."""
    for row in daily_rows:
        row["daily_lineage_checksum"] = daily_lineage_checksum(row)
    return daily_rows
