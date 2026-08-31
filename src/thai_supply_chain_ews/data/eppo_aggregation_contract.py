"""The EPPO aggregation contract, split into the things it was conflating (C7.5).

C7 reported one field, ``monthly_aggregation_contract_approved``, and it was
carrying three different questions at once:

* is the **rule** — arithmetic mean of validated observed official document-days
  — semantically valid and reproducible?
* is every required product-month actually **covered** by a valid value?
* may a later task **transform** the series, letting its gaps propagate?

Those have different answers. The rule can be sound while three days in April
2026 are still missing, and a series can be transformable at the months that are
complete while the incomplete ones simply produce no output. Reporting one
boolean forced all three to the worst of them, which reads as "the method is
wrong" when the method is fine.

Two failure modes are guarded explicitly. Method approval must never be
described as coverage — :func:`assert_method_approval_is_not_coverage` raises on
that reading. And a month that is *descriptively* summarised over the days that
exist must never become a transformation input —
:func:`assert_transformation_input_permitted` raises, because that is how an
incomplete mean silently becomes a feature.

Every month therefore carries two values: a **strict** one, which is null unless
the month's whole discovered inventory validated, and a **descriptive** one,
which may summarise the days that do exist and is always labelled incomplete.
Only the strict value is ever a transformation input.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

__all__ = [
    "AGGREGATION_RULE",
    "AGGREGATION_RULE_VERSION",
    "COMPLETE_STATUSES",
    "MONTHLY_STATUSES",
    "SHARED_CHANNEL_RULES",
    "add_months",
    "AggregationContractError",
    "MonthlyContractRow",
    "SeriesContract",
    "assert_method_approval_is_not_coverage",
    "assert_no_additive_fuel_oil_aggregate",
    "assert_transformation_input_permitted",
    "issue_months_affected",
    "monthly_contract_row",
    "operational_relevance",
    "series_contract",
]

AGGREGATION_RULE = "arithmetic_mean_of_validated_observed_official_document_days"
AGGREGATION_RULE_VERSION = "c7_v1"

MONTHLY_STATUSES = (
    "approved_complete_inventory",
    "approved_with_source_label_variant",
    "known_document_gap",
    "semantic_definition_gap",
    "unit_or_definition_break",
    "document_identity_unresolved",
    "document_retrieval_unresolved",
)

#: Statuses whose month is complete and may feed a later transformation.
COMPLETE_STATUSES = (
    "approved_complete_inventory",
    "approved_with_source_label_variant",
)

#: FO 600 and FO 1500 both map to I/O sector 093. They are different products
#: and the shared sector coefficient cannot separate them, so it can never be
#: used to justify combining them.
SHARED_CHANNEL_RULES = {
    "shared_price_stage_group": "io_sector_093_fuel_oil",
    "additive_aggregation_allowed": False,
    "simple_average_allowed": False,
    "automatic_composite_index_allowed": False,
    "simultaneous_model_entry_approved": False,
    "channel_selection_by_target_performance_allowed": False,
}


class AggregationContractError(ValueError):
    """The aggregation contract was asked to approve something it separates."""


def assert_method_approval_is_not_coverage(method_approved: bool,
                                           coverage_complete: bool,
                                           described_as: str) -> None:
    """Raise when method approval is presented as complete source coverage.

    The sentence this exists to stop is "the aggregation is approved, so the
    series is complete". Approving a rule says nothing about whether every month
    has a value.
    """
    description = str(described_as).lower()
    claims_coverage = any(
        phrase in description
        for phrase in ("complete coverage", "complete source coverage",
                       "full coverage", "every month has a value",
                       "series is complete", "no gaps")
    )
    if method_approved and claims_coverage and not coverage_complete:
        raise AggregationContractError(
            "aggregation_method_semantics_approved describes the RULE. It is "
            "being read as complete source coverage while "
            "full_requested_window_coverage_complete is false; those are "
            "separate fields with separate answers"
        )


def assert_transformation_input_permitted(row: dict) -> None:
    """Raise unless a monthly row may be used as a transformation input.

    A descriptive value over the days that happen to exist is a summary, not the
    month. Letting it through would put an incomplete mean into a feature with
    nothing marking it as different from a complete one.
    """
    status = row.get("aggregation_status")
    if status not in MONTHLY_STATUSES:
        raise AggregationContractError(f"unknown monthly status {status!r}")
    if status not in COMPLETE_STATUSES:
        raise AggregationContractError(
            f"{row.get('series_id')} {row.get('reference_month')} has status "
            f"{status!r} and may not be a transformation input; its gap must "
            "propagate rather than be filled"
        )
    if row.get("monthly_value_strict") is None:
        raise AggregationContractError(
            f"{row.get('series_id')} {row.get('reference_month')} has no strict "
            "value; a descriptive value may never be substituted for one"
        )
    if not row.get("coverage_complete"):
        raise AggregationContractError(
            f"{row.get('series_id')} {row.get('reference_month')} is not covered "
            "completely and may not be a transformation input"
        )


def assert_no_additive_fuel_oil_aggregate(series_ids, operation: str) -> None:
    """Raise on any attempt to add or average the two fuel oils together.

    They are distinct products that share one I/O sector coefficient. Summing
    them would double-count the shared exposure; averaging them would invent a
    price nobody publishes.
    """
    fuel_oils = {s for s in series_ids
                 if s in ("eppo_ex_refinery_fo600_2s", "eppo_ex_refinery_fo1500_2s")}
    if len(fuel_oils) > 1:
        raise AggregationContractError(
            f"{operation!r} would combine {sorted(fuel_oils)} into one quantity. "
            "FO 600 and FO 1500 are distinct products sharing I/O sector 093; "
            "they must stay separate, mutually exclusive channel variants"
        )


@dataclass
class MonthlyContractRow:
    """One product-month under the C7.5 contract, with both value views."""

    series_id: str
    canonical_product_id: str
    reference_month: str
    aggregation_rule: str = AGGREGATION_RULE
    aggregation_rule_version: str = AGGREGATION_RULE_VERSION
    aggregation_status: str = "known_document_gap"
    monthly_value_strict: float = None
    monthly_value_descriptive: float = None
    coverage_complete: bool = False
    valid_document_day_count: int = 0
    discovered_document_day_count: int = 0
    unresolved_document_day_count: int = 0
    unresolved_day_status: str = None
    source_product_labels_raw: list = field(default_factory=list)
    label_variant_days: int = 0
    approved_transformation_input: bool = False
    quality_flag: str = None

    def to_dict(self) -> dict:
        return asdict(self)


def monthly_contract_row(series_id: str, canonical_product_id: str,
                         reference_month: str, observations,
                         discovered_days: int, unresolved_days,
                         unresolved_day_status: str = None,
                         semantic_gap: bool = False,
                         equivalence_established: bool = True,
                         label_variant_days: int = 0) -> MonthlyContractRow:
    """Build one month's contract row from its canonical daily observations.

    ``observations`` are ``(effective_date, value, raw_label)`` triples already
    filtered to this series-month. Nothing is invented here: a month with no
    observation gets no value in either view.
    """
    values = [v for _, v, _ in observations if v is not None]
    labels = sorted({label for _, _, label in observations if label})
    descriptive = sum(values) / len(values) if values else None
    unresolved = sorted(unresolved_days)
    complete = bool(values) and not unresolved and len(values) == discovered_days

    if semantic_gap:
        status = "semantic_definition_gap"
        strict, descriptive_value, complete = None, None, False
        flag = "ordinary_product_not_published_blend_substitution_prohibited"
    elif label_variant_days and not equivalence_established:
        status = "unit_or_definition_break"
        strict, descriptive_value, complete = None, None, False
        flag = "unconfirmed_label_variant_equivalence_not_established"
    elif unresolved:
        status = "known_document_gap"
        strict, descriptive_value = None, descriptive
        flag = (
            f"incomplete_month_{len(values)}_of_{discovered_days}_discovered_"
            f"document_days_validated"
        )
    elif not values:
        status = "document_identity_unresolved"
        strict, descriptive_value = None, None
        flag = "no_validated_observation_for_this_product"
    elif label_variant_days:
        status = "approved_with_source_label_variant"
        strict = descriptive_value = descriptive
        flag = f"{label_variant_days}_document_days_carry_the_source_label_variant"
    else:
        status = "approved_complete_inventory"
        strict = descriptive_value = descriptive
        flag = "ok"

    row = MonthlyContractRow(
        series_id=series_id,
        canonical_product_id=canonical_product_id,
        reference_month=str(reference_month)[:7],
        aggregation_status=status,
        monthly_value_strict=strict,
        monthly_value_descriptive=descriptive_value,
        coverage_complete=bool(complete and status in COMPLETE_STATUSES),
        valid_document_day_count=len(values),
        discovered_document_day_count=discovered_days,
        unresolved_document_day_count=len(unresolved),
        unresolved_day_status=unresolved_day_status,
        source_product_labels_raw=labels,
        label_variant_days=label_variant_days,
        quality_flag=flag,
    )
    row.approved_transformation_input = bool(
        row.aggregation_status in COMPLETE_STATUSES
        and row.monthly_value_strict is not None
        and row.coverage_complete
    )
    return row


@dataclass
class SeriesContract:
    """The three separated approvals, per series."""

    series_id: str
    aggregation_method_semantics_approved: bool = False
    full_requested_window_coverage_complete: bool = False
    series_ready_for_transformation_with_explicit_gaps: bool = False
    feature_semantics_approved: bool = False
    model_feature_approved: bool = False
    months_required: int = 0
    months_complete: int = 0
    months_incomplete: list = field(default_factory=list)
    blocking_reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def series_contract(series_id: str, rows, method_approved: bool,
                    ready_permitted: bool, blocking_reasons=()) -> SeriesContract:
    """Aggregate month rows into the three separated approvals.

    ``ready_permitted`` is the semantic precondition — an unresolved equivalence
    or a 15-month definition gap makes a series unready however many of its
    individual months happen to be complete.
    """
    months = list(rows)
    complete = [r for r in months if r.approved_transformation_input]
    incomplete = sorted(
        (r.reference_month, r.aggregation_status)
        for r in months if not r.approved_transformation_input
    )
    return SeriesContract(
        series_id=series_id,
        aggregation_method_semantics_approved=bool(method_approved),
        full_requested_window_coverage_complete=bool(months) and not incomplete,
        series_ready_for_transformation_with_explicit_gaps=bool(
            method_approved and ready_permitted and complete
        ),
        feature_semantics_approved=False,
        model_feature_approved=False,
        months_required=len(months),
        months_complete=len(complete),
        months_incomplete=incomplete,
        blocking_reasons=sorted(blocking_reasons),
    )


def add_months(month: str, delta: int) -> str:
    """Shift a ``YYYY-MM`` key by ``delta`` months, in either direction."""
    year, index = int(str(month)[:4]), int(str(month)[5:7])
    total = year * 12 + (index - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def issue_months_affected(reference_month: str, lag_months: int = 2,
                          max_prehistory_months: int = 0) -> list:
    """Issue months whose inputs would include ``reference_month``.

    With a level feature the reach is a single issue month, ``m + lag``. A
    transformation with prehistory reaches further: a twelve-month change issued
    at ``t`` reads reference months ``t-lag-12 .. t-lag``, so one reference month
    feeds up to thirteen origins. Both are reported because reporting only the
    direct one would understate which origins a gap can touch.
    """
    first = add_months(reference_month, lag_months)
    months, cursor = [], first
    for _ in range(max_prehistory_months + 1):
        months.append(cursor)
        cursor = add_months(cursor, 1)
    return months


def operational_relevance(reference_month: str, splits: dict, lag_months: int = 2,
                          max_prehistory_months: int = 0) -> dict:
    """Which preregistered issue-origin ranges a reference month can reach.

    ``splits`` maps a split name to ``(start, end)`` issue months. Only issue-month
    keys and configuration ranges are read; no target value, prediction or metric
    is touched.
    """
    reach = issue_months_affected(reference_month, lag_months, max_prehistory_months)
    affected = {}
    for name, (start, end) in splits.items():
        hits = [m for m in reach if str(start)[:7] <= m <= str(end)[:7]]
        affected[name] = hits
    return {
        "reference_month": str(reference_month)[:7],
        "policy_lag_months": lag_months,
        "direct_issue_month": reach[0],
        "max_prehistory_months": max_prehistory_months,
        "issue_month_reach": [reach[0], reach[-1]],
        "affected_issue_origins": {k: v for k, v in affected.items() if v},
        "affects_any_preregistered_issue_origin": any(affected.values()),
        "note": (
            "Derived from preregistered issue-month ranges and the two-month "
            "policy lag only. No target value, prediction or metric was read."
        ),
    }
