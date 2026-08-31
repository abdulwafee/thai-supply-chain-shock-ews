"""180-sector vs official 58-sector reconciliation — Task C3-R1.

NESDC publishes the 2015 table at several aggregation levels (180, 58, 26, 16).
C3 wrongly reported that no official 58-sector workbook existed. It does, and it
is a genuine independent check on the 180-sector calculations.

Two kinds of comparison, and the distinction is the whole point of this module:

**Partition-invariant totals** — grand totals of gross output, value added,
intermediate transactions, imports and margins. These are identical under ANY
correct aggregation, so they can be compared with NO crosswalk at all. They are
computed here.

**Sector-level comparison** — requires knowing which 180 sectors compose each 58
sector. That mapping is a published classification, not something to be inferred.
Deriving it by subset-sum search over gross output would be exactly the
"numeric proximity" inference the task forbids, and it is not even unique. When
no official concordance can be found, this module raises rather than guessing,
and the reconciliation is recorded as NOT EXECUTED — which is a different state
from "passed" and from "failed".
"""

from __future__ import annotations

__all__ = [
    "AggregationCrosswalkUnavailable",
    "ReconciliationError",
    "PARTITION_INVARIANT_TOLERANCE",
    "TOLERANCE_BASIS",
    "partition_invariant_totals",
    "build_180_to_58_crosswalk",
    "reconcile",
]

# PREREGISTERED before any comparison was run. The published figures are whole
# numbers in thousand Baht (confirmed by the official 2015 publication), so an
# exact aggregation must agree to well under one unit; 0.5 is half the last
# published digit. This tolerance was NOT chosen after seeing discrepancies.
PARTITION_INVARIANT_TOLERANCE = 0.5
TOLERANCE_BASIS = (
    "Source precision: values are published as whole numbers in thousand Baht "
    "(Book_IO2015_EN.pdf, 'Table of Input Structure (180 Sectors) (in Thousand "
    "Baht)'). 0.5 is half of the last published digit, so any correct "
    "aggregation must agree within it. Preregistered before comparison."
)

MEASURES = ("purchaser", "wholesale", "retail", "transport", "import")


class AggregationCrosswalkUnavailable(RuntimeError):
    """No official 180-to-58 concordance could be established.

    Raised rather than resolved by inference. A subset-sum search over gross
    output would fit *a* partition, but fitting is not evidence, and the result
    would not be unique.
    """


class ReconciliationError(ValueError):
    """A reconciliation check failed."""


def _sector_codes(count: int) -> list[str]:
    return [f"{i:03d}" for i in range(1, count + 1)]


def partition_invariant_totals(table, sector_count: int) -> dict:
    """Grand totals that any correct aggregation must preserve."""
    codes = _sector_codes(sector_count)
    totals = {
        "gross_output_total": sum(table.gross_output[code] for code in codes),
        "value_added_total": sum(table.value_added[code] for code in codes),
    }
    for measure in MEASURES:
        signed = sum(
            table.z(row, column, measure) for row in codes for column in codes
        )
        absolute = sum(
            abs(table.z(row, column, measure)) for row in codes for column in codes
        )
        totals[f"intermediate_{measure}_signed_total"] = signed
        totals[f"intermediate_{measure}_absolute_total"] = absolute
    return totals


def build_180_to_58_crosswalk(
    sector_definitions_180: dict,
    official_concordance: dict | None,
) -> dict[str, str]:
    """Map each 180-sector code to its 58-sector code, from OFFICIAL material only.

    ``official_concordance`` must come from published NESDC classification
    material. There is no fallback: if it is absent, this raises.
    """
    if not official_concordance:
        raise AggregationCrosswalkUnavailable(
            "No official NESDC 180-to-58 concordance is available. The "
            "Input-Output Description document contains no 58-sector material, "
            "the official 2015 publication has no classification or concordance "
            "section, and the media library publishes only the aggregated DATA "
            "files (x58/x26/x16) without a mapping. C3-R1 refuses to infer the "
            "mapping from row order, label similarity, numeric proximity or "
            "subset-sum fitting: none of those is evidence, and the result would "
            "not be unique."
        )

    mapping: dict[str, str] = {}
    for code_58, members in official_concordance.items():
        for code_180 in members:
            if code_180 in mapping:
                raise ReconciliationError(
                    f"180-sector {code_180} appears in both {mapping[code_180]} "
                    f"and {code_58}."
                )
            if code_180 not in sector_definitions_180:
                raise ReconciliationError(
                    f"{code_180} is not a known 180-sector code."
                )
            mapping[code_180] = code_58

    missing = sorted(set(sector_definitions_180) - set(mapping))
    if missing:
        raise ReconciliationError(
            f"Incomplete concordance: {len(missing)} of the 180 sectors are "
            f"unmapped, e.g. {missing[:5]}. A partial crosswalk cannot aggregate "
            "a table."
        )
    return mapping


def reconcile(
    table_180,
    table_58,
    official_concordance: dict | None = None,
    tolerance: float = PARTITION_INVARIANT_TOLERANCE,
) -> dict:
    """Compare the two official tables at every level the evidence supports."""
    totals_180 = partition_invariant_totals(table_180, 180)
    totals_58 = partition_invariant_totals(table_58, 58)

    comparisons = []
    for key in sorted(totals_180):
        a, b = totals_180[key], totals_58[key]
        absolute = abs(a - b)
        relative = absolute / max(abs(a), 1.0)
        comparisons.append(
            {
                "quantity": key,
                "value_180": a,
                "value_58": b,
                "absolute_difference": absolute,
                "relative_difference": relative,
                "within_tolerance": absolute <= tolerance,
                "exact": absolute == 0.0,
            }
        )

    exact = sum(1 for item in comparisons if item["exact"])
    within = sum(1 for item in comparisons if item["within_tolerance"])
    failed = [item["quantity"] for item in comparisons if not item["within_tolerance"]]

    result = {
        "tolerance": tolerance,
        "tolerance_basis": TOLERANCE_BASIS,
        "tolerance_preregistered": True,
        "partition_invariant": {
            "comparisons": comparisons,
            "checks": len(comparisons),
            "exact_matches": exact,
            "within_tolerance": within,
            "failed": failed,
            "max_absolute_difference": max(
                item["absolute_difference"] for item in comparisons
            ),
            "max_relative_difference": max(
                item["relative_difference"] for item in comparisons
            ),
            "all_passed": not failed,
        },
    }

    try:
        mapping = build_180_to_58_crosswalk(
            {code: {} for code in _sector_codes(180)}, official_concordance
        )
    except AggregationCrosswalkUnavailable as exc:
        result["sector_level"] = {
            "status": "not_executed_official_crosswalk_unavailable",
            "reason": str(exc),
            "crosswalk_coverage": 0,
            "sectors_mapped": 0,
            "unexplained_discrepancies": None,
            "note": (
                "NOT EXECUTED is a third state, distinct from passed and from "
                "failed. No sector-level discrepancy was found because no "
                "sector-level comparison was run."
            ),
        }
        return result

    # An official concordance is available: aggregate and compare per sector.
    codes_58 = _sector_codes(58)
    aggregated = {code: 0.0 for code in codes_58}
    for code_180 in _sector_codes(180):
        aggregated[mapping[code_180]] += table_180.gross_output[code_180]
    per_sector = []
    for code in codes_58:
        a, b = aggregated[code], table_58.gross_output[code]
        per_sector.append(
            {
                "sector_58": code,
                "aggregated_180": a,
                "official_58": b,
                "absolute_difference": abs(a - b),
                "within_tolerance": abs(a - b) <= tolerance,
            }
        )
    failures = [item for item in per_sector if not item["within_tolerance"]]
    result["sector_level"] = {
        "status": "executed",
        "crosswalk_coverage": len(mapping),
        "sectors_mapped": len(set(mapping.values())),
        "per_sector": per_sector,
        "exact_matches": sum(1 for item in per_sector if item["absolute_difference"] == 0),
        "within_tolerance": len(per_sector) - len(failures),
        "unexplained_discrepancies": len(failures),
        "affected_sectors": [item["sector_58"] for item in failures],
        "all_passed": not failures,
    }
    return result
