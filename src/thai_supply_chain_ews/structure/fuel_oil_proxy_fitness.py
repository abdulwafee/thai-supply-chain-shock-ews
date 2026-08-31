"""Proxy fitness, direction and the Phase-A freeze for fuel oil (Task C9).

Sector 093 is a basket. The official NESDC definition says so in its own words —
*"Products of this sector are gasoline, jet oil, LPG, asphalt, paraffin, sulfur,
kerosene, diesel and fuel oil"* — nine named products, of which fuel oil is one.
A positive sector-093 coefficient therefore proves that an industry buys from the
refinery-products sector. It does not prove that the industry buys **FO 600** or
**FO 1500**, and :func:`assert_not_inferred_from_coefficient` refuses that
inference explicitly, because it is the one an ordinary reading of the number
invites.

Direction is decided from structure, not from correlation. An industry that buys
refinery products and does not contain the producer sector faces cost pressure,
multiplier ``+1``. **IND-04 contains sector 093 itself**: a higher refinery-product
price is simultaneously its revenue and its input cost, so its direction is
``mixed_or_ambiguous`` with a **null** multiplier, and forcing it to ``+1`` raises.
Realized volatility carries a third reading again — magnitude of disruption, not a
price increase — recorded in its own field so the sign of a level and the size of
a wobble are never conflated.

Phase A ends by freezing. The decision table is hashed and the digest must be
presented back before any C8 numeric value is loaded; :func:`assert_phase_a_frozen`
raises on a mismatch. That is what makes "the structural decision was taken
without seeing the data" a checkable claim rather than a promise.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "CONFIDENCE_LEVELS",
    "DIRECTION_CHANNELS",
    "ELIGIBILITY_REASONS",
    "PHASE_A_VERSION",
    "PROXY_FIT_STATUSES",
    "SECTOR_093_PRODUCT_BASKET",
    "PhaseAError",
    "StructuralDecision",
    "assert_direction_not_forced",
    "assert_not_inferred_from_coefficient",
    "assert_phase_a_frozen",
    "assert_no_numeric_source_values",
    "decide_direction",
    "decide_eligibility",
    "decide_proxy_fitness",
    "phase_a_checksum",
]

PHASE_A_VERSION = "c9_phase_a_structural_decision_v1"

PROXY_FIT_STATUSES = (
    "fit_for_structural_use",
    "broad_proxy_use_with_caution",
    "not_fit_for_product_specific_use",
    "unresolved",
)

CONFIDENCE_LEVELS = ("high", "medium", "low", "unresolved")

DIRECTION_CHANNELS = ("cost_pressure", "mixed_or_ambiguous", "unresolved")

ELIGIBILITY_REASONS = (
    "eligible",
    "direction_ambiguous_industry_contains_producer_sector",
    "proxy_not_fit_for_product_specific_use",
    "structural_exposure_unresolved",
    "negative_or_nonfinite_exposure",
)

#: The official basket, quoted from the NESDC sector definition. Fuel oil is one
#: of nine named products, which is exactly why a 093 coefficient is a broad
#: proxy and not a fuel-oil measurement.
SECTOR_093_PRODUCT_BASKET = (
    "gasoline", "jet oil", "LPG", "asphalt", "paraffin", "sulfur", "kerosene",
    "diesel", "fuel oil",
)


class PhaseAError(ValueError):
    """A structural decision was asked to rest on evidence it does not have."""


def assert_no_numeric_source_values(payload, context: str = "Phase A") -> None:
    """Raise if a C8 numeric feature value reaches a Phase-A function.

    Phase A decides structure. Letting a price or a log change in — even as an
    unused argument — would make "the decision was frozen before the data was
    seen" unverifiable.
    """
    forbidden = {
        "feature_value", "monthly_value_strict", "monthly_value_descriptive",
        "conditioned_value", "price_level", "log_change_1m_pct",
        "log_change_3m_pct", "log_change_12m_pct", "realized_volatility_3m_pct",
    }

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in forbidden:
                    raise PhaseAError(
                        f"{context} was given {key!r} at {path or '<root>'}; "
                        "structural decisions are made without reading C8 values"
                    )
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    walk(payload)


def assert_not_inferred_from_coefficient(exposure: float, evidence: str) -> None:
    """Raise when fuel-oil use is claimed from a sector-093 coefficient alone.

    A positive coefficient means the industry buys refinery products. The basket
    holds nine named products; fuel oil is one of them.
    """
    if exposure > 0 and not evidence:
        raise PhaseAError(
            "a positive sector-093 coefficient proves purchase from the "
            "refinery-products sector, not purchase of FO 600 or FO 1500. The "
            f"official basket is {list(SECTOR_093_PRODUCT_BASKET)}; "
            "product-specific evidence is required before claiming fuel-oil use"
        )


def decide_proxy_fitness(exposure, product_specific_evidence: str = None,
                         inspected_sources=()) -> dict:
    """Classify how far a sector-093 coefficient can stand in for fuel oil.

    Without product-specific evidence the best available status is
    ``broad_proxy_use_with_caution`` — never ``fit_for_structural_use``, and never
    confidence ``high``. Absence of that evidence from the sources Phase A is
    permitted to read is recorded as a limit of the inspection, not as proof that
    no such evidence exists anywhere.
    """
    if exposure.direct_exposure < 0 or exposure.direct_exposure != exposure.direct_exposure:
        return {
            "proxy_fit": "unresolved", "confidence": "unresolved",
            "product_specific_evidence_available": False,
            "reason": "exposure is negative or non-finite",
            "inspected_sources": sorted(inspected_sources),
        }
    if exposure.observed_zero:
        return {
            "proxy_fit": "broad_proxy_use_with_caution",
            "confidence": "low",
            "product_specific_evidence_available": bool(product_specific_evidence),
            "reason": (
                "observed zero direct purchase from sector 093; the exposure is a "
                "measured zero, not a missing value"
            ),
            "inspected_sources": sorted(inspected_sources),
        }
    if product_specific_evidence:
        assert_not_inferred_from_coefficient(
            exposure.direct_exposure, product_specific_evidence
        )
        return {
            "proxy_fit": "fit_for_structural_use", "confidence": "medium",
            "product_specific_evidence_available": True,
            "reason": product_specific_evidence,
            "inspected_sources": sorted(inspected_sources),
        }
    return {
        "proxy_fit": "broad_proxy_use_with_caution",
        "confidence": "medium",
        "product_specific_evidence_available": False,
        "reason": (
            "The industry buys from sector 093, whose official basket is "
            + ", ".join(SECTOR_093_PRODUCT_BASKET)
            + ". No source Phase A may read identifies which of those products "
            "it buys, so FO 600 / FO 1500 stand in for the whole basket and the "
            "conditioned value is a structural interaction, not a fuel-oil cost."
        ),
        "inspected_sources": sorted(inspected_sources),
    }


def decide_direction(exposure) -> dict:
    """Decide the structural direction for one industry.

    An industry containing the producer sector is not given ``+1``: the same
    price move raises its revenue and its input bill, and the net sign is a
    question this project has not answered.
    """
    if exposure.industry_contains_the_producer_sector:
        return {
            "direction_channel": "mixed_or_ambiguous",
            "direction_multiplier": None,
            "direction_interpretation_level": (
                "a higher refinery-product price is simultaneously revenue and "
                "input cost for this industry; the net sign is unresolved"
            ),
            "direction_interpretation_volatility": (
                "disruption_magnitude_nonnegative"
            ),
        }
    return {
        "direction_channel": "cost_pressure",
        "direction_multiplier": 1,
        "direction_interpretation_level": (
            "the industry purchases refinery products as inputs and does not "
            "produce them, so a higher price is a cost increase"
        ),
        "direction_interpretation_volatility": "disruption_magnitude_nonnegative",
    }


def assert_direction_not_forced(exposure, direction: dict) -> None:
    """Raise if a mixed producer-consumer industry was given a ``+1``."""
    if (exposure.industry_contains_the_producer_sector
            and direction.get("direction_multiplier") is not None):
        raise PhaseAError(
            f"{exposure.industry_id} contains sector 093 itself, so its direction "
            f"is mixed; forcing multiplier {direction['direction_multiplier']} "
            "would assert a net sign nobody established"
        )


def decide_eligibility(exposure, fitness: dict, direction: dict) -> dict:
    """Apply the seven-condition eligibility gate.

    An observed zero stays eligible and keeps its own flag: zero, unresolved and
    ineligible are three different states and collapsing them would hide which
    one a downstream null came from.
    """
    value = exposure.direct_exposure
    if value != value or value in (float("inf"), float("-inf")) or value < 0:
        reason = "negative_or_nonfinite_exposure"
    elif fitness["proxy_fit"] == "unresolved":
        reason = "structural_exposure_unresolved"
    elif fitness["proxy_fit"] == "not_fit_for_product_specific_use":
        reason = "proxy_not_fit_for_product_specific_use"
    elif direction["direction_channel"] != "cost_pressure":
        reason = "direction_ambiguous_industry_contains_producer_sector"
    elif direction["direction_multiplier"] is None:
        reason = "direction_ambiguous_industry_contains_producer_sector"
    else:
        reason = "eligible"
    return {
        "eligible": reason == "eligible",
        "exclusion_reason": None if reason == "eligible" else reason,
        "quality_flag": (
            "observed_zero_direct_exposure" if exposure.observed_zero else "ok"
        ),
    }


@dataclass
class StructuralDecision:
    """One frozen industry x channel structural decision."""

    industry_id: str
    industry_name: str
    channel_id: str
    io_sector_code: str
    io_sector_label: str
    direct_exposure: float
    observed_zero: bool
    industry_contains_the_producer_sector: bool
    proxy_fit: str
    confidence: str
    product_specific_evidence_available: bool
    proxy_reason: str
    direction_channel: str
    direction_multiplier: object
    direction_interpretation_level: str
    direction_interpretation_volatility: str
    eligible: bool
    exclusion_reason: str
    quality_flag: str
    valuation_basis_alignment: str
    structural_source_checksum: str
    exposure_row_checksum: str = None
    target_outcomes_used: bool = False
    contributions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def exposure_row_checksum(decision: dict) -> str:
    """Digest of one structural row, over the fields a decision rests on."""
    fields = (
        "industry_id", "channel_id", "io_sector_code", "io_sector_label",
        "direct_exposure", "observed_zero",
        "industry_contains_the_producer_sector", "proxy_fit", "confidence",
        "product_specific_evidence_available", "direction_channel",
        "direction_multiplier", "eligible", "exclusion_reason", "quality_flag",
        "valuation_basis_alignment", "structural_source_checksum",
    )
    payload = [
        "\x00null" if decision.get(f) is None
        else repr(decision[f]) if isinstance(decision.get(f), float)
        else ("true" if decision[f] else "false") if isinstance(decision.get(f), bool)
        else str(decision.get(f))
        for f in fields
    ]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def phase_a_checksum(rows) -> str:
    """Digest of the whole frozen Phase-A table, in deterministic key order."""
    ordered = sorted(rows, key=lambda r: (r["industry_id"], r["channel_id"]))
    payload = [PHASE_A_VERSION] + [
        row.get("exposure_row_checksum") or exposure_row_checksum(row)
        for row in ordered
    ]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_phase_a_frozen(rows, expected_checksum: str) -> str:
    """Raise unless the Phase-A table still hashes to its frozen digest.

    Phase B calls this before it opens the C8 table, and again over the rows it
    actually used. An eligibility that changed after the values were seen is the
    failure this makes impossible to hide.
    """
    actual = phase_a_checksum(rows)
    if actual != expected_checksum:
        raise PhaseAError(
            f"the Phase-A structural decision checksum is {actual}, not the frozen "
            f"{expected_checksum}. Structural eligibility may not change after C8 "
            "numeric values are loaded"
        )
    return actual
