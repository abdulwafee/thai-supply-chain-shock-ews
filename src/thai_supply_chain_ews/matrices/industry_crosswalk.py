"""Project industry <-> official I/O sector crosswalk — Task C3.

Aggregating an industry's exposure across several I/O sectors needs weights, and
inventing them is the failure this module exists to prevent. It uses OFFICIAL
GROSS OUTPUT from the same table as the coefficients:

    A[c][IND] = sum_j Z[c][j] / sum_j X[j]

That is not an average of coefficients with made-up weights — it is the exact
aggregate technical coefficient for the combined sector, obtained by summing the
numerator and the denominator. Equal weighting is never used, because nothing in
the project's aggregation definition supports it.

For total-requirement coefficients no such exact identity exists, so the
output-weighted mean is used and is labelled as a weighted mean rather than an
exact aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CrosswalkError",
    "EqualWeightError",
    "IndustryCrosswalk",
    "load_industry_crosswalk",
    "output_weights",
    "aggregate_direct",
    "aggregate_total",
]


class CrosswalkError(ValueError):
    """A crosswalk could not be resolved against the official classification."""


class EqualWeightError(CrosswalkError):
    """Equal weights were requested where the project does not support them."""


@dataclass(frozen=True)
class IndustryCrosswalk:
    """One project industry and the official I/O sectors it resolves to."""

    industry_id: str
    industry_name: str
    tsic_divisions: tuple[int, ...]
    io_sector_codes: tuple[str, ...]
    io_sector_labels: tuple[str, ...]
    mapping_relationship: str
    confidence: str
    scope_note: str


def load_industry_crosswalk(
    config: dict, taxonomy, sector_definitions: dict
) -> list[IndustryCrosswalk]:
    """Build the crosswalk, checking it against BOTH official classifications.

    Refuses to proceed unless the configured industries reproduce the production
    taxonomy exactly — same ids, same names, same TSIC divisions — so a C3
    mapping can never drift from the dimension B1 and B3 actually use.
    """
    configured = config["industry_crosswalk"]
    production = dict(taxonomy.industries)

    if set(configured) != set(production):
        raise CrosswalkError(
            "C3 industry ids do not match the production taxonomy. "
            f"Only in C3: {sorted(set(configured) - set(production))}; "
            f"only in production: {sorted(set(production) - set(configured))}."
        )

    crosswalks = []
    for industry_id in sorted(configured):
        entry = configured[industry_id]
        actual = production[industry_id]
        if entry["name_en"] != actual.name_en:
            raise CrosswalkError(
                f"{industry_id}: C3 name {entry['name_en']!r} != production "
                f"name {actual.name_en!r}. C3 must not rename an industry."
            )
        if tuple(entry["tsic_divisions"]) != tuple(actual.tsic_divisions):
            raise CrosswalkError(
                f"{industry_id}: C3 TSIC divisions {entry['tsic_divisions']} != "
                f"production {list(actual.tsic_divisions)}."
            )
        codes = tuple(str(code) for code in entry["io_sectors"])
        if len(set(codes)) != len(codes):
            raise CrosswalkError(f"{industry_id}: duplicate I/O sector codes {codes}.")
        unknown = [code for code in codes if code not in sector_definitions]
        if unknown:
            raise CrosswalkError(
                f"{industry_id}: I/O codes absent from the official "
                f"classification document: {unknown}."
            )
        crosswalks.append(
            IndustryCrosswalk(
                industry_id=industry_id,
                industry_name=entry["name_en"],
                tsic_divisions=tuple(entry["tsic_divisions"]),
                io_sector_codes=codes,
                io_sector_labels=tuple(
                    sector_definitions[code]["label"] for code in codes
                ),
                mapping_relationship=entry["mapping_relationship"],
                confidence=entry["confidence"],
                scope_note=entry.get("scope_note", ""),
            )
        )

    # No I/O sector may serve two industries: that would double-count output.
    assigned: dict[str, str] = {}
    for crosswalk in crosswalks:
        for code in crosswalk.io_sector_codes:
            if code in assigned:
                raise CrosswalkError(
                    f"I/O sector {code} is assigned to both {assigned[code]} and "
                    f"{crosswalk.industry_id}."
                )
            assigned[code] = crosswalk.industry_id
    return crosswalks


def output_weights(
    crosswalk: IndustryCrosswalk, gross_output: dict[str, float]
) -> dict[str, float]:
    """Official gross-output shares across an industry's component sectors."""
    usable = {
        code: gross_output.get(code, 0.0)
        for code in crosswalk.io_sector_codes
        if gross_output.get(code, 0.0) > 0
    }
    total = sum(usable.values())
    if total <= 0:
        raise CrosswalkError(
            f"{crosswalk.industry_id}: component sectors have no positive gross "
            "output, so no defensible aggregation weight exists."
        )
    weights = {code: value / total for code, value in usable.items()}
    residual = abs(sum(weights.values()) - 1.0)
    if residual > 1e-9:
        raise CrosswalkError(
            f"{crosswalk.industry_id}: weights sum to {sum(weights.values())!r}, "
            "not 1. An aggregation whose weights do not sum to one is not an "
            "aggregation."
        )
    return weights


def aggregate_direct(
    table,
    commodity_code: str,
    crosswalk: IndustryCrosswalk,
    gross_output: dict[str, float],
    measure: str = "purchaser",
) -> float:
    """Exact aggregate direct coefficient: sum(Z) / sum(X) over the components."""
    usable = [
        code for code in crosswalk.io_sector_codes if gross_output.get(code, 0.0) > 0
    ]
    if not usable:
        raise CrosswalkError(
            f"{crosswalk.industry_id}: no component sector has positive output."
        )
    numerator = sum(table.z(commodity_code, code, measure) for code in usable)
    denominator = sum(gross_output[code] for code in usable)
    return numerator / denominator


def aggregate_total(
    matrices,
    commodity_code: str,
    crosswalk: IndustryCrosswalk,
    gross_output: dict[str, float],
) -> float:
    """Output-weighted mean total-requirement coefficient.

    A weighted MEAN, not an exact aggregate — the Leontief inverse of an
    aggregated matrix is not the aggregate of the inverse, and C3 does not
    pretend otherwise.
    """
    weights = output_weights(crosswalk, gross_output)
    available = {
        code: weight for code, weight in weights.items()
        if code in matrices.sector_codes
    }
    total_weight = sum(available.values())
    if total_weight <= 0:
        raise CrosswalkError(
            f"{crosswalk.industry_id}: no component sector survives into the "
            "coefficient matrix."
        )
    return sum(
        matrices.total(commodity_code, code) * (weight / total_weight)
        for code, weight in available.items()
    )
