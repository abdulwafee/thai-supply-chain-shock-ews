"""Development-only design-matrix assembly for the conditioned fuel oils (C10).

Lays the C9 development snapshot out as one wide matrix per variant, keyed on
``(issue_month, industry_id)``, with the five C8 transformations as columns.

Three things are refused here rather than downstream.

**The two variants are never one matrix.** They share the sector-093 exposure
vector, so a ten-column table holding both would present one coefficient twice.
:func:`assert_variants_not_combined` raises on any attempt, including one framed
as picking whichever channel has the better rank or condition number.

**IND-04 stays in the matrix.** Its direction is unresolved, not zero, and not
absent. Dropping it would make the table rectangular by deleting the one row that
records a structural limitation; converting it to zero would assert an exposure
of zero that nobody measured. The rows are kept with an explicit cell-level mask
and :func:`assert_mask_not_zeroed` raises on the conversion.

**A key is either present exactly once or the assembly fails.** A duplicate, a
missing month, a mixed variant or an issue/reference pair that breaks the
two-month lag each raise, because every one of them produces a table that still
looks like a design matrix.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

__all__ = [
    "CELL_STATES",
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "MASKED_INDUSTRY_STATES",
    "POLICY_LAG_MONTHS",
    "TRANSFORMATION_COLUMNS",
    "VARIANT_IDS",
    "DevelopmentMatrix",
    "MatrixAssemblyError",
    "assert_lag_two",
    "assert_mask_not_zeroed",
    "assert_no_feature_removal",
    "assert_variants_not_combined",
    "build_development_matrix",
    "month_range",
    "shift_month",
]

DEVELOPMENT_START = "2024-01"
DEVELOPMENT_END = "2025-03"
POLICY_LAG_MONTHS = 2

VARIANT_IDS = ("fo600_direct_sector093", "fo1500_direct_sector093")

#: Column order is fixed. A diagnostic that depends on column order — a
#: condition number does not, a QR pivot does — must not shift under a rename.
TRANSFORMATION_COLUMNS = (
    "log_change_12m_pct",
    "log_change_1m_pct",
    "log_change_3m_pct",
    "price_level",
    "realized_volatility_3m_pct",
)

CELL_STATES = ("numeric", "structural_zero", "masked_ineligible",
               "rejected_source_null")

#: States whose cell carries no value and must never be read as one.
MASKED_INDUSTRY_STATES = ("masked_ineligible", "rejected_source_null")


class MatrixAssemblyError(ValueError):
    """A design matrix was asked to hold something it cannot hold honestly."""


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


def assert_lag_two(issue_month: str, reference_month: str,
                   lag_months: int = POLICY_LAG_MONTHS) -> None:
    """Raise unless the recorded reference month is exactly ``issue - lag``.

    Checked against the *recorded* field, never inferred by shifting rows: a
    positional shift reproduces the right answer on a complete table and hides
    the error on an incomplete one.
    """
    expected = shift_month(str(issue_month)[:7], -lag_months)
    if str(reference_month)[:7] != expected:
        raise MatrixAssemblyError(
            f"issue month {issue_month} carries reference month {reference_month}, "
            f"but the {lag_months}-month policy lag requires {expected}"
        )


def assert_variants_not_combined(variant_ids, operation: str) -> str:
    """Raise unless exactly one variant is in play.

    Both variants are conditioned on the SAME sector-093 exposure vector.
    Concatenating them into one ten-column matrix, averaging them, or running a
    joint decomposition would use one coefficient twice while presenting it as
    two independent measurements.
    """
    variants = sorted(set(variant_ids))
    unknown = [v for v in variants if v not in VARIANT_IDS]
    if unknown:
        raise MatrixAssemblyError(f"unknown fuel-oil variant(s) {unknown}")
    if not variants:
        raise MatrixAssemblyError(f"{operation!r} names no variant")
    if len(variants) > 1:
        raise MatrixAssemblyError(
            f"{operation!r} would use {variants} together. Both carry the same "
            "sector-093 exposure vector, so combining them counts one coefficient "
            "twice; they are mutually exclusive variants and no feature diagnostic "
            "may choose between them"
        )
    return variants[0]


def assert_mask_not_zeroed(cell: dict) -> None:
    """Raise if a masked cell has acquired a value."""
    if cell.get("cell_state") in MASKED_INDUSTRY_STATES:
        if cell.get("value") is not None:
            raise MatrixAssemblyError(
                f"{cell.get('variant_id')} {cell.get('industry_id')} "
                f"{cell.get('issue_month')} {cell.get('transformation_id')} is "
                f"{cell['cell_state']} yet carries {cell['value']}; a structural "
                "mask means the design is unresolved, not zero"
            )
        if not cell.get("masked"):
            raise MatrixAssemblyError(
                f"{cell.get('industry_id')} {cell.get('issue_month')} is "
                f"{cell['cell_state']} but is not flagged as masked"
            )


def assert_no_feature_removal(columns, operation: str) -> None:
    """Raise if a transformation has been dropped from the design.

    C10 is an audit. A degenerate or highly correlated column is a *finding*;
    removing it would turn the finding into a silent change of the design.
    """
    missing = [c for c in TRANSFORMATION_COLUMNS if c not in tuple(columns)]
    if missing:
        raise MatrixAssemblyError(
            f"{operation!r} dropped {missing}. C10 preserves every transformation, "
            "including a degenerate one: removing a feature on a rank or "
            "correlation finding is a design change, not an audit"
        )


@dataclass
class DevelopmentMatrix:
    """One variant's wide development design, with its mask kept beside it."""

    variant_id: str
    issue_months: list = field(default_factory=list)
    industry_ids: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    mask_cells: list = field(default_factory=list)
    eligible_industries: list = field(default_factory=list)
    masked_industries: list = field(default_factory=list)
    numeric_cells: int = 0
    masked_cells: int = 0
    fully_numeric_rows: int = 0
    fully_masked_rows: int = 0
    reference_months: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def source_time_matrix(self, exposures: dict, industry_id: str = None) -> list:
        """The 15 x 5 exposure-normalised design, from one eligible industry.

        This is the object every rank and correlation diagnostic runs on. The
        165-row stacked panel is eleven scaled copies of it and is never the
        primary input.
        """
        industry_id = industry_id or (self.eligible_industries or [None])[0]
        if industry_id is None:
            raise MatrixAssemblyError("no eligible industry to normalise from")
        exposure = exposures.get(industry_id)
        if not exposure or exposure <= 0:
            raise MatrixAssemblyError(
                f"{industry_id} has exposure {exposure!r}; an exposure-normalised "
                "design needs a strictly positive one"
            )
        matrix = []
        for issue_month in self.issue_months:
            row = self.row(issue_month, industry_id)
            matrix.append([value / exposure for value in row])
        return matrix

    def row(self, issue_month: str, industry_id: str) -> list:
        for record in self.rows:
            if (record["issue_month"] == issue_month
                    and record["industry_id"] == industry_id):
                if record["row_state"] != "numeric":
                    raise MatrixAssemblyError(
                        f"{industry_id} {issue_month} is {record['row_state']}; "
                        "a masked row has no numeric design"
                    )
                return [record["values"][column] for column in self.columns]
        raise MatrixAssemblyError(f"no row for {industry_id} {issue_month}")

    def industry_design(self, industry_id: str) -> list:
        return [self.row(m, industry_id) for m in self.issue_months]

    def stacked_eligible_panel(self) -> list:
        """The 165 x 5 panel. Reported, never used as the primary diagnostic."""
        return [
            self.row(month, industry)
            for industry in self.eligible_industries
            for month in self.issue_months
        ]


def build_development_matrix(cells, variant_id: str, expected_industries,
                             expected_issue_months=None,
                             columns=TRANSFORMATION_COLUMNS) -> DevelopmentMatrix:
    """Assemble one variant's wide matrix from the C9 snapshot cells.

    Every expected key must appear exactly once. A duplicate, an absent key, a
    stray variant or a lag violation raises rather than producing a table that
    is quietly the wrong shape.
    """
    variant = assert_variants_not_combined(
        {cell["variant_id"] for cell in cells} | {variant_id},
        f"assembly of {variant_id}",
    )
    columns = tuple(columns)
    assert_no_feature_removal(columns, "matrix assembly")

    issue_months = sorted(expected_issue_months or {c["issue_month"] for c in cells})
    industries = sorted(expected_industries)
    seen = Counter()
    indexed, reference_by_issue = {}, {}
    for cell in cells:
        assert_mask_not_zeroed(cell)
        assert_lag_two(cell["issue_month"], cell["reference_month"])
        recorded = reference_by_issue.setdefault(
            cell["issue_month"], cell["reference_month"]
        )
        if recorded != cell["reference_month"]:
            raise MatrixAssemblyError(
                f"issue month {cell['issue_month']} carries two reference months: "
                f"{recorded} and {cell['reference_month']}"
            )
        key = (cell["issue_month"], cell["industry_id"], cell["transformation_id"])
        seen[key] += 1
        indexed[key] = cell

    duplicates = sorted(k for k, n in seen.items() if n > 1)
    if duplicates:
        raise MatrixAssemblyError(f"duplicate matrix keys: {duplicates[:5]}")

    expected_keys = {
        (month, industry, column)
        for month in issue_months for industry in industries for column in columns
    }
    missing = sorted(expected_keys - set(indexed))
    if missing:
        raise MatrixAssemblyError(f"missing matrix keys: {missing[:5]}")
    extra = sorted(set(indexed) - expected_keys)
    if extra:
        raise MatrixAssemblyError(f"unexpected matrix keys: {extra[:5]}")

    rows, mask_cells = [], []
    numeric_cells = masked = 0
    for month in issue_months:
        for industry in industries:
            values, states = {}, {}
            for column in columns:
                cell = indexed[(month, industry, column)]
                values[column] = cell["value"]
                states[column] = cell["cell_state"]
                mask_cells.append({
                    "variant_id": variant, "issue_month": month,
                    "industry_id": industry, "transformation_id": column,
                    "reference_month": cell["reference_month"],
                    "cell_state": cell["cell_state"],
                    "masked": bool(cell["masked"]),
                    "mask_reason": cell.get("mask_reason"),
                    "conditioned_status": cell.get("conditioned_status"),
                    "conditioned_lineage_checksum":
                        cell.get("conditioned_lineage_checksum"),
                })
                if cell["cell_state"] == "numeric":
                    numeric_cells += 1
                else:
                    masked += 1
            distinct = set(states.values())
            if len(distinct) > 1:
                raise MatrixAssemblyError(
                    f"{industry} {month} mixes cell states {sorted(distinct)}; a "
                    "structural mask applies to the whole row or to none of it"
                )
            row_state = "numeric" if distinct == {"numeric"} else distinct.pop()
            rows.append({
                "variant_id": variant, "issue_month": month,
                "industry_id": industry,
                "reference_month": reference_by_issue[month],
                "row_state": row_state, "values": values,
                "masked": row_state != "numeric",
            })

    eligible = sorted({r["industry_id"] for r in rows if r["row_state"] == "numeric"})
    masked_industries = sorted({
        r["industry_id"] for r in rows if r["row_state"] != "numeric"
    })
    overlap = set(eligible) & set(masked_industries)
    if overlap:
        raise MatrixAssemblyError(
            f"{sorted(overlap)} are numeric in some issue months and masked in "
            "others; structural eligibility does not vary by month"
        )

    return DevelopmentMatrix(
        variant_id=variant,
        issue_months=issue_months,
        industry_ids=industries,
        columns=list(columns),
        rows=rows,
        mask_cells=mask_cells,
        eligible_industries=eligible,
        masked_industries=masked_industries,
        numeric_cells=numeric_cells,
        masked_cells=masked,
        fully_numeric_rows=sum(1 for r in rows if r["row_state"] == "numeric"),
        fully_masked_rows=sum(1 for r in rows if r["row_state"] != "numeric"),
        reference_months=[reference_by_issue[m] for m in issue_months],
    )
