"""Development-only issue snapshots of the conditioned fuel-oil features (C9).

At forecast issue month *t* the latest source reference month readable under the
two-month policy is *t-2*. A snapshot takes that month and lays out the twelve
industries against the five transformations, once per variant.

Three cell states are kept apart, because collapsing any pair of them is how a
gap becomes a number:

* an **ineligible** pair is ``None`` with a mask flag — the structure is
  unresolved, not zero;
* an **observed structural zero** is numeric ``0.0`` — a measured absence of
  direct purchase, which is a fact and not a gap;
* a **source-null** cell is rejected outright — an absent price cannot be
  conditioned at all.

The snapshot is development-only. Purge and locked coverage are reported from
**issue-key ranges alone**: how many keys exist and which reference month each
would read. No target value, prediction or metric is opened to say that, and
nothing is materialised for those splits.

The two variants never share a row. They carry the same sector-093 exposure, so
one model-ready row holding both would double-count that coefficient.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from thai_supply_chain_ews.features.fuel_oil_industry_conditioning import (
    VARIANT_BY_CHANNEL,
    ConditioningError,
    assert_no_fuel_oil_combination,
)

__all__ = [
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "POLICY_LAG_MONTHS",
    "SNAPSHOT_CELL_STATES",
    "SnapshotError",
    "SnapshotCell",
    "build_development_snapshot",
    "issue_key_range_coverage",
    "latest_permitted_reference_month",
    "shift_month",
]

DEVELOPMENT_START = "2024-01"
DEVELOPMENT_END = "2025-03"
POLICY_LAG_MONTHS = 2

SNAPSHOT_CELL_STATES = (
    "numeric",
    "structural_zero",
    "masked_ineligible",
    "rejected_source_null",
)


class SnapshotError(ConditioningError):
    """A snapshot was asked to expose something the contract withholds."""


def shift_month(month: str, delta: int) -> str:
    year, index = int(str(month)[:4]), int(str(month)[5:7])
    total = year * 12 + (index - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_range(start: str, end: str) -> list:
    months, cursor = [], str(start)[:7]
    while cursor <= str(end)[:7]:
        months.append(cursor)
        cursor = shift_month(cursor, 1)
    return months


def latest_permitted_reference_month(issue_month: str,
                                     lag_months: int = POLICY_LAG_MONTHS) -> str:
    """Latest conditioned reference month readable at issue month *t*: ``t - lag``."""
    return shift_month(str(issue_month)[:7], -lag_months)


@dataclass
class SnapshotCell:
    """One development-snapshot cell, with its state named rather than implied."""

    issue_month: str
    variant_id: str
    industry_id: str
    transformation_id: str
    reference_month: str
    value: float = None
    cell_state: str = "numeric"
    masked: bool = False
    mask_reason: str = None
    conditioned_status: str = None
    conditioned_policy_available_month: str = None
    conditioned_lineage_checksum: str = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SnapshotSummary:
    issue_months: int = 0
    variants: int = 0
    industries: int = 0
    transformations: int = 0
    cells: int = 0
    state_counts: dict = field(default_factory=dict)
    rejected_source_null_cells: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_development_snapshot(conditioned_rows, industries, transformations,
                               start: str = DEVELOPMENT_START,
                               end: str = DEVELOPMENT_END,
                               lag_months: int = POLICY_LAG_MONTHS) -> tuple:
    """Lay the conditioned grid out by issue month, for development only.

    Every issue month keeps all twelve industries and all five transformations,
    so the shape does not change with eligibility; what changes is the state of
    the cell. A source-null cell is rejected rather than emitted, and the
    rejection is listed instead of being silently absent.
    """
    issue_months = month_range(start, end)
    indexed = {
        (row["variant_id"], row["industry_id"], row["reference_month"],
         row["transformation_id"]): row
        for row in conditioned_rows
    }
    variants = sorted(set(VARIANT_BY_CHANNEL.values()))
    cells, rejected = [], []
    for issue_month in issue_months:
        reference_month = latest_permitted_reference_month(issue_month, lag_months)
        for variant_id in variants:
            for industry_id in sorted(industries):
                for transformation_id in transformations:
                    row = indexed.get(
                        (variant_id, industry_id, reference_month, transformation_id)
                    )
                    if row is None:
                        raise SnapshotError(
                            f"no conditioned row for {variant_id} {industry_id} "
                            f"{reference_month} {transformation_id}"
                        )
                    cell = _snapshot_cell(issue_month, row)
                    if cell.cell_state == "rejected_source_null":
                        rejected.append({
                            "issue_month": issue_month, "variant_id": variant_id,
                            "industry_id": industry_id,
                            "transformation_id": transformation_id,
                            "reference_month": reference_month,
                            "conditioned_status": row["conditioned_status"],
                        })
                    cells.append(cell)

    summary = SnapshotSummary(
        issue_months=len(issue_months),
        variants=len(variants),
        industries=len(industries),
        transformations=len(transformations),
        cells=len(cells),
        state_counts=dict(sorted(Counter(c.cell_state for c in cells).items())),
        rejected_source_null_cells=rejected,
    )
    return cells, summary


def _snapshot_cell(issue_month: str, row: dict) -> SnapshotCell:
    status = row["conditioned_status"]
    cell = SnapshotCell(
        issue_month=issue_month,
        variant_id=row["variant_id"],
        industry_id=row["industry_id"],
        transformation_id=row["transformation_id"],
        reference_month=row["reference_month"],
        conditioned_status=status,
        conditioned_policy_available_month=row["conditioned_policy_available_month"],
        conditioned_lineage_checksum=row["conditioned_lineage_checksum"],
    )
    if status in ("not_generated_due_to_direction_ambiguity",
                  "not_generated_due_to_proxy_ineligibility",
                  "structural_exposure_unresolved"):
        cell.value, cell.cell_state = None, "masked_ineligible"
        cell.masked, cell.mask_reason = True, row.get("exclusion_reason") or status
        return cell
    if status.startswith("source_"):
        cell.value, cell.cell_state = None, "rejected_source_null"
        cell.masked, cell.mask_reason = True, status
        return cell
    if status == "zero_due_to_observed_zero_exposure":
        cell.value, cell.cell_state = 0.0, "structural_zero"
        return cell
    cell.value, cell.cell_state = row["conditioned_value"], "numeric"
    return cell


def assert_single_variant_per_row(variant_ids, operation: str) -> str:
    """Raise unless a model-ready row draws on exactly one fuel-oil variant."""
    return assert_no_fuel_oil_combination(variant_ids, operation)


def issue_key_range_coverage(splits: dict, conditioned_rows,
                             lag_months: int = POLICY_LAG_MONTHS) -> dict:
    """Coverage for every split, derived from issue-key ranges alone.

    Reports how many keys each split holds and which reference month each would
    read. No target value, prediction or metric is opened, and nothing is
    materialised outside development.
    """
    indexed = {}
    for row in conditioned_rows:
        indexed.setdefault(
            (row["variant_id"], row["reference_month"]), []
        ).append(row)

    coverage = {}
    for split_name, (start, end) in sorted(splits.items()):
        issue_months = month_range(start, end)
        per_variant = {}
        for variant_id in sorted(set(VARIANT_BY_CHANNEL.values())):
            references, blocked = [], []
            for issue_month in issue_months:
                reference_month = latest_permitted_reference_month(
                    issue_month, lag_months
                )
                references.append(reference_month)
                rows = indexed.get((variant_id, reference_month), [])
                if any(r["conditioned_status"].startswith("source_") for r in rows):
                    blocked.append(reference_month)
            per_variant[variant_id] = {
                "issue_months": len(issue_months),
                "reference_month_range": [references[0], references[-1]],
                "reference_months_with_a_source_gap": sorted(set(blocked)),
                "materialised": split_name == "development",
            }
        coverage[split_name] = per_variant
    coverage["target_values_read"] = False
    coverage["model_predictions_read"] = False
    coverage["locked_test_outcomes_read"] = False
    return coverage
