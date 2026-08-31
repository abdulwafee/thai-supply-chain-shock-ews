"""Direct industry exposure to I/O sector 093, Petroleum refineries (Task C9).

C3 measured exposure to sector **031**, *Petroleum and natural gas* — crude. C5
then showed why that produced ten direct-zeros: factories do not buy crude, they
buy refined fuel and power. Sector **093** is the refinery-products sector, and
this module derives exposure to it from the same official table, the same
orientation and the same gross-output weights C3 used.

Reusing C3's number under a new name would be the easy error, so the sector code
is a required argument everywhere and :func:`assert_sector_is_093` refuses
anything else. Total requirement is not computed here at all: C9 is a
*direct*-exposure task, and having ``T`` in scope is how it eventually gets used.

The aggregation is calculated **twice by different routes** — an output-weighted
mean of the sector coefficients, and the exact ratio of summed flows to summed
output — and the two must agree to 1e-12. They are algebraically identical, so a
disagreement means a weight, a filter or an orientation is wrong, and that is
precisely the class of error that otherwise produces a plausible number.

What the coefficient *is*: baht of sector-093 output purchased per baht of the
industry's gross output, in the table's purchasers'-price, import-inclusive
basis, from one 2015 benchmark under fixed proportions. It is not an elasticity,
not a pass-through rate and not a causal effect.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

__all__ = [
    "FUEL_OIL_SECTOR_CODE",
    "FUEL_OIL_SECTOR_LABEL",
    "RECONCILIATION_TOLERANCE",
    "CRUDE_SECTOR_CODE",
    "ExposureError",
    "SectorExposure",
    "SectorContribution",
    "assert_no_final_demand_or_value_added",
    "assert_sector_is_093",
    "direct_coefficient",
    "industry_exposure",
    "exposure_summary",
]

FUEL_OIL_SECTOR_CODE = "093"
FUEL_OIL_SECTOR_LABEL = "Petroleum refineries"

#: The sector C3 used. Named here only so it can be refused.
CRUDE_SECTOR_CODE = "031"

RECONCILIATION_TOLERANCE = 1e-12


class ExposureError(ValueError):
    """An exposure was asked to rest on evidence that cannot support it."""


def assert_sector_is_093(sector_code: str, sector_label: str = None) -> None:
    """Raise unless the sector really is 093, Petroleum refineries.

    C3's sector-031 crude exposure and C9's sector-093 refinery exposure are
    different numbers about different goods. Relabelling one as the other would
    survive every downstream check, because both are plausible coefficients.
    """
    if str(sector_code) == CRUDE_SECTOR_CODE:
        raise ExposureError(
            f"sector {CRUDE_SECTOR_CODE} is 'Petroleum and natural gas' (crude), "
            f"the commodity C3 measured. C9 requires sector {FUEL_OIL_SECTOR_CODE}, "
            f"{FUEL_OIL_SECTOR_LABEL!r}; reusing the crude coefficient here would "
            "assert that factories buy crude, which C5 showed they do not"
        )
    if str(sector_code) != FUEL_OIL_SECTOR_CODE:
        raise ExposureError(
            f"C9 conditions on sector {FUEL_OIL_SECTOR_CODE} only; got "
            f"{sector_code!r}"
        )
    if sector_label is not None and str(sector_label).strip() != FUEL_OIL_SECTOR_LABEL:
        raise ExposureError(
            f"sector {FUEL_OIL_SECTOR_CODE} label is {sector_label!r}, not "
            f"{FUEL_OIL_SECTOR_LABEL!r}; the official classification must match"
        )


def assert_no_final_demand_or_value_added(sector_codes, table_sector_codes) -> None:
    """Raise if a non-sector code reached the intermediate block.

    The parsed workbook carries final-demand columns and value-added rows
    alongside the intermediate flows. Either entering ``Z`` would change what the
    coefficient measures while leaving it looking like a coefficient.
    """
    official = set(table_sector_codes)
    intruders = sorted(code for code in sector_codes if code not in official)
    if intruders:
        raise ExposureError(
            f"non-sector codes reached the intermediate block: {intruders}. "
            "Final-demand columns and value-added rows are not intermediate flows"
        )


def direct_coefficient(table, producing_code: str, sector_code: str = FUEL_OIL_SECTOR_CODE,
                       measure: str = "purchaser") -> float:
    """``A[093, j] = Z[093, j] / X_j`` for one producing sector.

    Column-oriented by construction: the denominator is the *purchasing* sector's
    gross output. A transposed matrix satisfies most self-consistency checks
    while dividing each flow by the wrong sector's output.
    """
    assert_sector_is_093(sector_code)
    output = table.gross_output.get(producing_code, 0.0)
    if output <= 0:
        raise ExposureError(
            f"sector {producing_code} has gross output {output}; its coefficient "
            "is undefined and substituting zero would assert it requires nothing"
        )
    coefficient = table.z(sector_code, producing_code, measure) / output
    if not (coefficient == coefficient) or coefficient in (float("inf"), float("-inf")):
        raise ExposureError(f"non-finite coefficient for sector {producing_code}")
    if coefficient < 0:
        raise ExposureError(
            f"negative direct coefficient {coefficient} for sector {producing_code}"
        )
    return coefficient


@dataclass
class SectorContribution:
    """One component sector's share of an industry's sector-093 exposure."""

    io_sector_code: str
    io_sector_label: str
    direct_coefficient: float
    gross_output: float
    output_weight: float
    weighted_contribution: float
    contribution_share: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SectorExposure:
    """One industry's direct exposure to sector 093, with both derivations."""

    industry_id: str
    industry_name: str
    io_sector_code: str = FUEL_OIL_SECTOR_CODE
    io_sector_label: str = FUEL_OIL_SECTOR_LABEL
    direct_exposure: float = 0.0
    weighted_mean_form: float = 0.0
    summed_flow_form: float = 0.0
    reconciliation_residual: float = 0.0
    observed_zero: bool = False
    component_sector_count: int = 0
    component_sectors_with_zero_coefficient: int = 0
    industry_contains_the_producer_sector: bool = False
    weight_sum: float = 0.0
    contributions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["contributions"] = [c.to_dict() for c in self.contributions]
        return payload


def industry_exposure(table, crosswalk, sector_code: str = FUEL_OIL_SECTOR_CODE,
                      measure: str = "purchaser",
                      tolerance: float = RECONCILIATION_TOLERANCE) -> SectorExposure:
    """Aggregate sector-093 exposure for one industry, derived two ways.

    Weights are the official gross-output shares C3 uses. Equal weighting is not
    offered: it would silently give a tiny component sector the same standing as
    one twenty times its size.
    """
    assert_sector_is_093(sector_code)
    assert_no_final_demand_or_value_added(crosswalk.io_sector_codes, table.sector_codes)

    usable = [
        code for code in crosswalk.io_sector_codes
        if table.gross_output.get(code, 0.0) > 0
    ]
    if not usable:
        raise ExposureError(
            f"{crosswalk.industry_id}: no component sector has positive gross "
            "output, so no defensible aggregation weight exists"
        )
    if len(set(usable)) != len(usable):
        raise ExposureError(f"{crosswalk.industry_id}: duplicate component sector")

    total_output = sum(table.gross_output[code] for code in usable)
    contributions, weighted_total = [], 0.0
    for code in usable:
        coefficient = direct_coefficient(table, code, sector_code, measure)
        weight = table.gross_output[code] / total_output
        weighted = weight * coefficient
        weighted_total += weighted
        contributions.append(SectorContribution(
            io_sector_code=code,
            io_sector_label="",
            direct_coefficient=coefficient,
            gross_output=table.gross_output[code],
            output_weight=weight,
            weighted_contribution=weighted,
            contribution_share=0.0,
        ))

    # The exact aggregate: sum of flows over sum of output. Algebraically the
    # same as the weighted mean, computed independently on purpose.
    summed_flow = (
        sum(table.z(sector_code, code, measure) for code in usable) / total_output
    )
    residual = abs(weighted_total - summed_flow)
    if residual > tolerance:
        raise ExposureError(
            f"{crosswalk.industry_id}: the weighted-mean form {weighted_total!r} and "
            f"the summed-flow form {summed_flow!r} disagree by {residual!r}, above "
            f"{tolerance}. The two are algebraically identical, so a disagreement "
            "means a weight, a filter or the matrix orientation is wrong"
        )

    weight_sum = sum(c.output_weight for c in contributions)
    if abs(weight_sum - 1.0) > 1e-9:
        raise ExposureError(
            f"{crosswalk.industry_id}: aggregation weights sum to {weight_sum!r}, "
            "not 1; that is not an aggregation"
        )
    for contribution in contributions:
        contribution.contribution_share = (
            contribution.weighted_contribution / weighted_total
            if weighted_total > 0 else 0.0
        )
    contributions.sort(key=lambda c: (-c.weighted_contribution, c.io_sector_code))

    return SectorExposure(
        industry_id=crosswalk.industry_id,
        industry_name=crosswalk.industry_name,
        direct_exposure=weighted_total,
        weighted_mean_form=weighted_total,
        summed_flow_form=summed_flow,
        reconciliation_residual=residual,
        observed_zero=weighted_total == 0.0,
        component_sector_count=len(usable),
        component_sectors_with_zero_coefficient=sum(
            1 for c in contributions if c.direct_coefficient == 0.0
        ),
        industry_contains_the_producer_sector=sector_code in crosswalk.io_sector_codes,
        weight_sum=weight_sum,
        contributions=contributions,
    )


def exposure_summary(exposures) -> dict:
    """Distribution of the twelve industry exposures, without normalising them.

    Exposures are reported on their own scale. Normalising across industries
    would turn a structural ratio into a ranking and hide that every industry
    buys refinery products.
    """
    items = sorted(exposures, key=lambda e: e.industry_id)
    values = sorted(e.direct_exposure for e in items)
    if not values:
        raise ExposureError("no exposures to summarise")
    middle = len(values) // 2
    median = (
        values[middle] if len(values) % 2
        else (values[middle - 1] + values[middle]) / 2
    )
    ranked = sorted(items, key=lambda e: -e.direct_exposure)
    return {
        "io_sector_code": FUEL_OIL_SECTOR_CODE,
        "io_sector_label": FUEL_OIL_SECTOR_LABEL,
        "industries": len(items),
        "minimum": values[0],
        "maximum": values[-1],
        "median": median,
        "observed_zero_count": sum(1 for e in items if e.observed_zero),
        "unresolved_count": 0,
        "industries_containing_the_producer_sector": [
            e.industry_id for e in items if e.industry_contains_the_producer_sector
        ],
        "max_reconciliation_residual": max(e.reconciliation_residual for e in items),
        "top_exposed_industries": [
            {"industry_id": e.industry_id, "industry_name": e.industry_name,
             "direct_exposure": e.direct_exposure}
            for e in ranked[:5]
        ],
        "normalised_across_industries": False,
        "total_requirement_used": False,
        "note": (
            "Baht of sector-093 output purchased per baht of industry gross "
            "output, purchasers' prices, import-inclusive, one 2015 benchmark "
            "under fixed proportions. Not an elasticity, not a pass-through "
            "rate, not a causal effect. A large exposure is a structural fact, "
            "not an error."
        ),
    }
