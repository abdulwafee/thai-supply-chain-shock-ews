"""Industry-conditioned fuel-oil features (Task C9, Phase B).

Multiplies each C8 source transformation by the frozen sector-093 exposure and
the frozen direction multiplier. The arithmetic is trivial; everything that
matters is what is refused.

**Three kinds of absence stay apart.** An ineligible pair produces null, not
zero — IND-04's direction is unresolved, and writing zero there would assert
"no exposure" where the truth is "we do not know the sign". A missing source
month produces null, not zero, *even when exposure is zero* — multiplying an
absent price by anything is still absent. An observed zero exposure produces a
numeric **zero**, but only when the source value exists. The status precedence
enforces that order, and :func:`assert_null_not_converted_to_zero` raises on the
two collapses.

**The grid is complete.** 2 channels x 12 industries x 65 months x 5
transformations = 7,800 rows, and none is dropped for being ineligible, null or
zero. An omitted row and a null row are indistinguishable downstream only when
the null row is missing.

**The two channels never meet.** Both use the *same* sector-093 exposure vector,
which is exactly why summing or averaging them would double-count one
coefficient while looking like two independent measurements.

What the product means: a structural interaction between a published ex-refinery
price and a purchasers'-price I/O coefficient. It is **not** baht of cost per
unit of output — the price stage and the valuation basis do not match — and it is
neither an elasticity nor a forecast coefficient.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from thai_supply_chain_ews.features.eppo_fuel_oil_transformations import (
    TRANSFORMATION_IDS,
    TRANSFORMATION_UNITS,
)

__all__ = [
    "CONDITIONED_STATUSES",
    "CONDITIONED_UNITS",
    "CONDITIONING_FORMULA_VERSION",
    "SHARED_STRUCTURAL_EXPOSURE_GROUP",
    "STATUS_PRECEDENCE",
    "VARIANT_BY_CHANNEL",
    "ConditionedRow",
    "ConditioningError",
    "assert_no_fuel_oil_combination",
    "assert_null_not_converted_to_zero",
    "assert_valuation_claim_permitted",
    "build_conditioned_grid",
    "condition_value",
    "conditioned_policy_available_month",
    "expected_conditioned_counts",
]

CONDITIONING_FORMULA_VERSION = "c9_fuel_oil_direct_sector093_v1"

SHARED_STRUCTURAL_EXPOSURE_GROUP = "io_sector_093"

VARIANT_BY_CHANNEL = {
    "eppo_fo600_channel": "fo600_direct_sector093",
    "eppo_fo1500_channel": "fo1500_direct_sector093",
}

#: Transformation-specific, and never a currency. The I/O coefficient is
#: dimensionless in baht-per-baht terms, so the product keeps the source unit
#: with the coefficient named alongside it rather than silently absorbed.
CONDITIONED_UNITS = {
    "price_level": "baht_per_litre_x_io_coefficient",
    "log_change_1m_pct": "percentage_point_log_change_x_io_coefficient",
    "log_change_3m_pct": "percentage_point_log_change_x_io_coefficient",
    "log_change_12m_pct": "percentage_point_log_change_x_io_coefficient",
    "realized_volatility_3m_pct":
        "percentage_point_log_change_volatility_x_io_coefficient",
}

CONDITIONED_STATUSES = (
    "available_nonzero",
    "zero_due_to_observed_zero_exposure",
    "source_insufficient_history",
    "source_current_month_gap",
    "source_input_window_gap",
    "not_generated_due_to_direction_ambiguity",
    "not_generated_due_to_proxy_ineligibility",
    "structural_exposure_unresolved",
)

#: Structural ineligibility first, then a missing source, then a zero exposure,
#: then a value. Reordering these is how a "we do not know" becomes a "zero".
STATUS_PRECEDENCE = (
    "structural_ineligibility",
    "source_transformation_null",
    "structural_exposure_zero",
    "available_nonzero",
)

_SOURCE_STATUS_MAP = {
    "insufficient_feature_history": "source_insufficient_history",
    "current_month_source_gap": "source_current_month_gap",
    "input_window_source_gap": "source_input_window_gap",
}

_INELIGIBILITY_STATUS = {
    "direction_ambiguous_industry_contains_producer_sector":
        "not_generated_due_to_direction_ambiguity",
    "proxy_not_fit_for_product_specific_use":
        "not_generated_due_to_proxy_ineligibility",
    "structural_exposure_unresolved": "structural_exposure_unresolved",
    "negative_or_nonfinite_exposure": "structural_exposure_unresolved",
}


class ConditioningError(ValueError):
    """A conditioned value was asked to mean more than its inputs support."""


def assert_valuation_claim_permitted(description: str) -> None:
    """Raise when the conditioned value is described as a monetary cost.

    EPPO measures the ex-refinery stage; the I/O coefficient is in purchasers'
    prices. Their product is a structural interaction, and calling it baht of
    cost per unit of output would assert an alignment that does not hold.
    """
    text = str(description).lower()
    banned = (
        "baht cost per unit", "cost per unit of output", "monetary cost",
        "baht of cost", "elasticity", "pass-through rate", "causal effect",
        "forecast coefficient",
    )
    for phrase in banned:
        if phrase in text:
            raise ConditioningError(
                f"the conditioned value may not be described as {phrase!r}: EPPO "
                "measures the ex-refinery stage while the I/O coefficient is in "
                "purchasers' prices, so their product is a structural "
                "interaction only"
            )


def assert_no_fuel_oil_combination(variant_ids, operation: str) -> str:
    """Raise unless exactly one fuel-oil variant is in play.

    Both variants carry the *same* sector-093 exposure. Adding or averaging them
    would count one coefficient twice and present it as two measurements.
    """
    variants = sorted(set(variant_ids))
    unknown = [v for v in variants if v not in set(VARIANT_BY_CHANNEL.values())]
    if unknown:
        raise ConditioningError(f"unknown conditioned variant(s) {unknown}")
    if not variants:
        raise ConditioningError(f"{operation!r} names no fuel-oil variant")
    if len(variants) > 1:
        raise ConditioningError(
            f"{operation!r} would use {variants} together. Both are conditioned on "
            f"the SAME {SHARED_STRUCTURAL_EXPOSURE_GROUP} exposure vector, so "
            "combining them double-counts one coefficient; they are mutually "
            "exclusive variants"
        )
    return variants[0]


def assert_null_not_converted_to_zero(row: dict) -> None:
    """Raise on the two collapses that make an absence look like a measurement."""
    status = row.get("conditioned_status")
    value = row.get("conditioned_value")
    if status in _INELIGIBILITY_STATUS.values() and value is not None:
        raise ConditioningError(
            f"{row.get('variant_id')} {row.get('industry_id')} "
            f"{row.get('reference_month')} {row.get('transformation_id')}: an "
            f"ineligible pair carries the value {value}; ineligible means the "
            "structure is unresolved, not that the exposure is zero"
        )
    if status in _SOURCE_STATUS_MAP.values() and value is not None:
        raise ConditioningError(
            f"{row.get('variant_id')} {row.get('industry_id')} "
            f"{row.get('reference_month')} {row.get('transformation_id')}: a "
            f"missing source transformation produced {value}; an absent price "
            "multiplied by any exposure is still absent, zero exposure included"
        )
    if status == "zero_due_to_observed_zero_exposure" and value != 0:
        raise ConditioningError(
            "an observed-zero exposure with a present source value must produce "
            f"exactly 0, got {value}"
        )


def condition_value(source_value: float, exposure: float, multiplier) -> float:
    """``z = x * E * s``. No normalisation, across anything."""
    if multiplier is None:
        raise ConditioningError(
            "the direction multiplier is null; a mixed producer-consumer industry "
            "has no resolved sign and may not be conditioned"
        )
    if exposure != exposure or exposure < 0:
        raise ConditioningError(f"exposure {exposure} is negative or non-finite")
    return float(source_value) * float(exposure) * float(multiplier)


def conditioned_policy_available_month(source_policy_month: str,
                                       structural_available_month: str) -> str:
    """``max(source policy month, structural available month)``.

    The structural month is the I/O table's *publication*, 2020-03, not its 2015
    reference year. Backdating to the reference year would hand a 2024 origin
    four years of structure nobody could read.
    """
    source = str(source_policy_month)[:7]
    structural = str(structural_available_month)[:7]
    if not source or not structural:
        raise ConditioningError("both availability months are required")
    return max(source, structural)


def expected_conditioned_counts(source_finite: int, source_null: int,
                                eligible_industries: int,
                                ineligible_industries: int,
                                rows_per_channel_pair: int) -> dict:
    """Phase-B counts derived from the frozen eligibility, before any value loads.

    ``source_finite`` and ``source_null`` are the C8 totals across both channels,
    so multiplying by the per-channel industry counts reproduces the full grid.
    """
    numeric = source_finite * eligible_industries
    gaps = source_null * eligible_industries
    ineligible = rows_per_channel_pair * ineligible_industries
    return {
        "full_grid_rows": numeric + gaps + ineligible,
        "source_numeric_rows": numeric,
        "source_gap_rows": gaps,
        "ineligible_rows": ineligible,
        "eligible_industries_per_channel": eligible_industries,
        "ineligible_industries_per_channel": ineligible_industries,
    }


@dataclass
class ConditionedRow:
    """One conditioned cell: a value, a structural zero, or an explained absence."""

    variant_id: str
    channel_id: str
    shared_structural_exposure_group: str
    industry_id: str
    industry_name: str
    io_sector_code: str
    reference_month: str
    transformation_id: str
    conditioning_formula_version: str
    conditioned_value: float = None
    conditioned_unit: str = None
    conditioned_status: str = "available_nonzero"
    source_feature_value: float = None
    source_transformation_status: str = None
    source_unit: str = None
    direct_exposure: float = 0.0
    direction_channel: str = None
    direction_multiplier: object = None
    direction_interpretation: str = None
    proxy_fit: str = None
    proxy_confidence: str = None
    eligible: bool = False
    exclusion_reason: str = None
    quality_flag: str = None
    valuation_basis_alignment: str = None
    structural_interaction_only: bool = True
    monetary_cost_measure: bool = False
    not_a_currency_cost: bool = True
    not_an_elasticity: bool = True
    not_a_forecast_coefficient: bool = True
    source_required_input_months: list = field(default_factory=list)
    source_missing_input_months: list = field(default_factory=list)
    source_policy_available_month: str = None
    structural_available_month: str = None
    conditioned_policy_available_month: str = None
    source_available_as_of: str = None
    availability_basis: str = "conservative_policy_not_historical_measurement"
    latest_vintage_used: bool = True
    point_in_time_supported: bool = False
    fully_real_time_backtest: bool = False
    additive_aggregation_allowed: bool = False
    simultaneous_model_entry_approved: bool = False
    source_transformation_lineage_checksum: str = None
    phase_a_decision_checksum: str = None
    conditioned_lineage_checksum: str = None
    model_feature_approved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def build_conditioned_grid(source_rows, decisions, months, structural_available_month,
                           lineage_fn) -> list:
    """The complete conditioned grid, one row per channel x industry x month x transform.

    ``decisions`` is the frozen Phase-A table indexed by ``(industry_id,
    channel_id)``. Nothing here may change it: eligibility was decided before any
    source value was read, and this function only applies it.
    """
    indexed_source = {
        (row["channel_id"], row["reference_month"], row["transformation_id"]): row
        for row in source_rows
    }
    if len(indexed_source) != len(list(source_rows)):
        raise ConditioningError("duplicate C8 source key")

    rows = []
    for (industry_id, channel_id), decision in sorted(decisions.items()):
        variant_id = VARIANT_BY_CHANNEL[channel_id]
        for reference_month in months:
            for transformation_id in TRANSFORMATION_IDS:
                source = indexed_source.get(
                    (channel_id, reference_month, transformation_id)
                )
                if source is None:
                    raise ConditioningError(
                        f"no C8 row for {channel_id} {reference_month} "
                        f"{transformation_id}; the grid cannot be completed"
                    )
                row = _condition_cell(
                    variant_id, channel_id, industry_id, decision, source,
                    reference_month, transformation_id, structural_available_month,
                )
                assert_null_not_converted_to_zero(row.to_dict())
                row.conditioned_lineage_checksum = lineage_fn(row, decision, source)
                rows.append(row)

    keys = [
        (r.variant_id, r.industry_id, r.reference_month, r.transformation_id)
        for r in rows
    ]
    if len(keys) != len(set(keys)):
        raise ConditioningError("duplicate conditioned grid key")
    rows.sort(key=lambda r: (r.variant_id, r.industry_id, r.reference_month,
                             r.transformation_id))
    return rows


def _condition_cell(variant_id, channel_id, industry_id, decision, source,
                    reference_month, transformation_id, structural_available_month):
    exposure = float(decision["direct_exposure"])
    multiplier = decision["direction_multiplier"]
    source_value = source.get("feature_value")
    source_status = source.get("transformation_status")

    row = ConditionedRow(
        variant_id=variant_id,
        channel_id=channel_id,
        shared_structural_exposure_group=SHARED_STRUCTURAL_EXPOSURE_GROUP,
        industry_id=industry_id,
        industry_name=decision["industry_name"],
        io_sector_code=decision["io_sector_code"],
        reference_month=reference_month,
        transformation_id=transformation_id,
        conditioning_formula_version=CONDITIONING_FORMULA_VERSION,
        conditioned_unit=CONDITIONED_UNITS[transformation_id],
        source_feature_value=source_value,
        source_transformation_status=source_status,
        source_unit=TRANSFORMATION_UNITS[transformation_id],
        direct_exposure=exposure,
        direction_channel=decision["direction_channel"],
        direction_multiplier=multiplier,
        direction_interpretation=(
            decision["direction_interpretation_volatility"]
            if transformation_id == "realized_volatility_3m_pct"
            else decision["direction_interpretation_level"]
        ),
        proxy_fit=decision["proxy_fit"],
        proxy_confidence=decision["confidence"],
        eligible=bool(decision["eligible"]),
        exclusion_reason=decision["exclusion_reason"],
        quality_flag=decision["quality_flag"],
        valuation_basis_alignment=decision["valuation_basis_alignment"],
        source_required_input_months=list(source.get("required_input_months") or []),
        source_missing_input_months=list(source.get("missing_input_months") or []),
        source_policy_available_month=source.get("policy_available_month"),
        structural_available_month=str(structural_available_month)[:7],
        source_transformation_lineage_checksum=source.get(
            "transformation_lineage_checksum"
        ),
        phase_a_decision_checksum=decision["phase_a_decision_checksum"],
    )
    row.conditioned_policy_available_month = conditioned_policy_available_month(
        row.source_policy_available_month, structural_available_month
    )

    # 1. structural ineligibility
    if not decision["eligible"]:
        row.conditioned_status = _INELIGIBILITY_STATUS.get(
            decision["exclusion_reason"], "structural_exposure_unresolved"
        )
        row.conditioned_value = None
        return row
    # 2. source transformation null
    if source_value is None:
        row.conditioned_status = _SOURCE_STATUS_MAP.get(
            source_status, "structural_exposure_unresolved"
        )
        row.conditioned_value = None
        return row
    # 3. structural exposure zero
    if exposure == 0.0:
        row.conditioned_status = "zero_due_to_observed_zero_exposure"
        row.conditioned_value = 0.0
        return row
    # 4. a value
    row.conditioned_status = "available_nonzero"
    row.conditioned_value = condition_value(source_value, exposure, multiplier)
    return row
