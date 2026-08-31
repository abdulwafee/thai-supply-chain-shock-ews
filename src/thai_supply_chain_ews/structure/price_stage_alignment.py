"""Price-stage alignment between a commodity series and what is purchased (Task C5).

A price series is only a cost signal for an industry if it represents the stage
that industry actually buys. Brent is a *crude oil* price; almost no Thai
manufacturer buys crude. They buy diesel, fuel oil, electricity, petrochemicals
and transport — each of which carries crude's influence, but through a
different price with its own taxes, margins and lags.

This module classifies each existing commodity-industry relationship by the
stage the decomposition says is actually purchased, and records whether the
World Bank series in hand represents that stage. Nothing here consults model
accuracy: a series is aligned or not on **semantics**, and a proxy that happened
to fit well would still be misaligned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

__all__ = [
    "ALIGNMENT_STATUSES",
    "PRICE_STAGES",
    "AlignmentError",
    "StageAssessment",
    "assess_relationship",
    "classify_stage",
]

PRICE_STAGES = (
    "raw_commodity_direct_purchase",
    "processed_material_purchase",
    "refined_energy_purchase",
    "electricity_purchase",
    "transport_or_logistics_purchase",
    "exchange_rate_passthrough",
    "broad_or_unresolved_proxy",
)

ALIGNMENT_STATUSES = (
    "stage_aligned",
    "broad_proxy_with_caution",
    "stage_misaligned",
    "unresolved",
)

#: Sector-code families that identify a purchased stage. Codes are the official
#: 2015 NESDC 179-sector codes; labels are carried for evidence, never matched on.
_ELECTRICITY = {"135"}
_REFINERY = {"093"}
_PETROCHEMICAL = {"086", "084"}
_TRANSPORT = {"140", "141", "142", "143", "144", "145", "146", "147"}
_RUBBER_PRODUCTS = {"094", "095", "096", "097"}
_PLASTIC = {"098"}
_NON_FERROUS = {"107"}


class AlignmentError(ValueError):
    """A price-stage classification was asked to assert more than the evidence."""


def classify_stage(direct_exposure: float, leading_sector_codes) -> str:
    """Infer the purchased stage from the decomposition, not from accuracy."""
    if direct_exposure > 0.0:
        return "raw_commodity_direct_purchase"
    leading = list(leading_sector_codes)
    if not leading:
        return "broad_or_unresolved_proxy"
    top = leading[0]
    if top in _ELECTRICITY:
        return "electricity_purchase"
    if top in _REFINERY:
        return "refined_energy_purchase"
    if top in _TRANSPORT:
        return "transport_or_logistics_purchase"
    if top in _PETROCHEMICAL | _RUBBER_PRODUCTS | _PLASTIC | _NON_FERROUS:
        return "processed_material_purchase"
    return "processed_material_purchase"


@dataclass
class StageAssessment:
    commodity_series_id: str
    industry_id: str
    world_bank_series: str
    mapped_raw_io_sector: str
    mapped_raw_io_sector_label: str
    leading_purchased_sectors: list
    direct_exposure: float
    indirect_exposure: float
    total_exposure: float
    price_stage: str
    world_bank_price_represents_purchased_stage: bool
    alignment_status: str
    evidence: str
    limitations: str
    additional_series_could_close_gap: bool
    shared_source_sector_warning: str = None
    proxy_fitness_status: str = None
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def assess_relationship(
    decomposition,
    world_bank_series: str,
    mapped_sector_code: str,
    mapped_sector_label: str,
    sector_labels: dict,
    shared_sector_with=(),
    proxy_fitness_status: str = None,
    top_n: int = 5,
) -> StageAssessment:
    """Assess one commodity-industry relationship on structural evidence only."""
    leading = [
        {
            "sector_code": m.intermediate_sector_code,
            "sector_label": m.intermediate_sector_label,
            "contribution": m.contribution,
            "share_of_indirect": m.share_of_indirect,
        }
        for m in decomposition.mediators[:top_n]
    ]
    codes = [item["sector_code"] for item in leading]
    stage = classify_stage(decomposition.direct_exposure, codes)

    # Does the World Bank series price the stage that is actually purchased?
    represents = stage == "raw_commodity_direct_purchase" and mapped_sector_code in codes[:1]
    if decomposition.direct_exposure > 0.0:
        represents = True

    if represents and not shared_sector_with:
        status = "stage_aligned"
    elif shared_sector_with:
        status = "broad_proxy_with_caution"
    elif decomposition.total_exposure == 0.0:
        status = "unresolved"
    else:
        status = "stage_misaligned"

    top_label = leading[0]["sector_label"] if leading else "none"
    top_share = leading[0]["share_of_indirect"] if leading else 0.0
    if decomposition.direct_exposure > 0.0:
        evidence = (
            f"Direct coefficient {decomposition.direct_exposure:.6f} is positive, so the "
            f"industry purchases sector {mapped_sector_code} ({mapped_sector_label}) across "
            "the factory gate. The World Bank series prices that sector's output."
        )
    else:
        evidence = (
            f"Direct coefficient is exactly zero: the industry buys no "
            f"{mapped_sector_label} directly. Indirect exposure "
            f"{decomposition.indirect_exposure:.6f} "
            f"reaches it through {top_label} "
            f"({top_share:.1%} of indirect), so the purchased price stage is "
            f"{stage}, not the raw commodity."
        )

    limitations = (
        "The 2015 I/O structure is held time-invariant; coefficients describe 2015 "
        "purchasing patterns, not the evaluation period. The decomposition is an "
        "exact attribution of the Leontief identity, not a causal claim."
    )
    warning = None
    if shared_sector_with:
        warning = (
            f"Source sector {mapped_sector_code} is shared with {sorted(shared_sector_with)}. "
            "The coefficient cannot separate them, so the two series are NOT independent "
            "measurements and their exposures must never be summed."
        )
        limitations += " " + warning

    return StageAssessment(
        commodity_series_id=decomposition.commodity_series_id,
        industry_id=decomposition.industry_id,
        world_bank_series=world_bank_series,
        mapped_raw_io_sector=mapped_sector_code,
        mapped_raw_io_sector_label=mapped_sector_label,
        leading_purchased_sectors=leading,
        direct_exposure=decomposition.direct_exposure,
        indirect_exposure=decomposition.indirect_exposure,
        total_exposure=decomposition.total_exposure,
        price_stage=stage,
        world_bank_price_represents_purchased_stage=bool(represents),
        alignment_status=status,
        evidence=evidence,
        limitations=limitations,
        additional_series_could_close_gap=status in {
            "stage_misaligned", "broad_proxy_with_caution"
        },
        shared_source_sector_warning=warning,
        proxy_fitness_status=proxy_fitness_status,
        diagnostics={
            "cumulative_share_top1": decomposition.cumulative_share(1),
            "cumulative_share_top3": decomposition.cumulative_share(3),
            "cumulative_share_top5": decomposition.cumulative_share(5),
            "direct_is_observed_zero": decomposition.direct_is_observed_zero,
            "indirect_material_despite_direct_zero": (
                decomposition.indirect_material_despite_direct_zero
            ),
        },
    )
