"""The 48-row commodity–industry structural exposure table — Task C3.

One row for each of the 12 project industries x 4 approved commodity series.
Each row carries three exposures — direct, indirect, total — together with the
mapping evidence that justifies them and the confidence that qualifies them.

Three states that must never be merged
--------------------------------------
``numeric zero``
    The I/O matrix provides an OBSERVED zero under a verified crosswalk. The
    industry genuinely used none of that input in the benchmark year.

``null / unresolved``
    The crosswalk could not be resolved, so no number is claimed.

``missing``
    The pair was not evaluated at all.

Collapsing unresolved into zero would turn "we don't know" into "there is no
exposure", which is the single most consequential error available here.
"""

from __future__ import annotations

import math

from thai_supply_chain_ews.matrices.industry_crosswalk import (
    aggregate_direct,
    aggregate_total,
    output_weights,
)

__all__ = [
    "ExposureError",
    "CANONICAL_COLUMNS",
    "APPROVED_COMMODITIES",
    "DIRECTION_CHANNELS",
    "build_exposure_table",
    "classify_direction",
]

# The four series C2 approved. C3 does not widen this list.
APPROVED_COMMODITIES: tuple[str, ...] = (
    "aluminum_usd_mt",
    "brent_crude_usd_bbl",
    "copper_usd_mt",
    "rubber_rss3_usd_kg",
)

DIRECTION_CHANNELS: tuple[str, ...] = (
    "cost_pressure",
    "producer_revenue",
    "mixed_or_ambiguous",
    "no_verified_channel",
    "unresolved",
)

CANONICAL_COLUMNS: tuple[str, ...] = (
    "industry_id",
    "industry_name",
    "commodity_series_id",
    "commodity_source_label",
    "commodity_io_sector_code",
    "commodity_io_sector_label",
    "industry_io_sector_codes",
    "direct_exposure",
    "indirect_exposure",
    "total_requirement_exposure",
    "exposure_unit",
    "direction_channel",
    "price_increase_to_stress_sign",
    "mapping_type",
    "mapping_confidence",
    "shared_io_source_sector",
    "shared_with",
    "structural_reference_year",
    "time_invariant_assumption",
    "valuation_basis",
    "aggregation_weight_source",
    "evidence_urls",
    "crosswalk_version",
    "io_source_sha256",
    "quality_flag",
    "model_feature_approved",
)


class ExposureError(ValueError):
    """The exposure table could not be built as specified."""


def classify_direction(
    commodity_io_code: str, industry_io_codes: tuple[str, ...]
) -> tuple[str, int | None, str]:
    """Return (channel, sign, rationale) from the classification alone.

    An industry that CONTAINS the commodity's own I/O sector both produces and
    consumes it. That sign is genuinely ambiguous and is left null rather than
    forced — a wrong sign is worse than an absent one.
    """
    if commodity_io_code in industry_io_codes:
        return (
            "mixed_or_ambiguous",
            None,
            (
                f"The industry's I/O sectors include {commodity_io_code}, the "
                "commodity's own sector, so it is both a producer and a "
                "consumer. The net sign is not established by the classification "
                "and is deliberately left null."
            ),
        )
    return (
        "cost_pressure",
        1,
        (
            f"Sector {commodity_io_code} enters the industry's sectors as an "
            "intermediate input, so a higher commodity price is greater "
            "input-cost pressure. A DOMAIN direction, not an estimated sign."
        ),
    )


def build_exposure_table(
    table,
    matrices,
    crosswalks,
    config: dict,
    sector_definitions: dict,
) -> list[dict]:
    """Build the canonical 48-row table."""
    commodity_config = config["commodity_crosswalk"]
    configured = tuple(sorted(commodity_config))
    if configured != APPROVED_COMMODITIES:
        raise ExposureError(
            f"C3 commodity allowlist {configured} does not match the four C2 "
            f"approved series {APPROVED_COMMODITIES}."
        )

    reference_year = str(config["io_source"]["structural_reference_year"])
    valuation = config["valuation_basis"]["price_basis"]
    weight_source = config["industry_crosswalk_aggregation"]["weight_source"]
    crosswalk_version = config["crosswalk_version"]
    evidence_urls = list(config["io_source"]["landing_pages"])

    rows: list[dict] = []
    for crosswalk in sorted(crosswalks, key=lambda c: c.industry_id):
        for commodity_id in APPROVED_COMMODITIES:
            entry = commodity_config[commodity_id]
            commodity_code = str(entry["io_sector_code"])
            channel, sign, rationale = classify_direction(
                commodity_code, crosswalk.io_sector_codes
            )

            direct = indirect = total = None
            quality = "ok"
            if entry["mapping_type"] in ("qualitative_only", "unresolved"):
                # No defensible quantitative crosswalk: the number stays NULL.
                quality = "unresolved_mapping_no_numeric_exposure"
            elif commodity_code not in matrices.sector_codes:
                quality = "commodity_sector_absent_from_coefficient_matrix"
            else:
                direct = aggregate_direct(
                    table, commodity_code, crosswalk, table.gross_output
                )
                total = aggregate_total(
                    matrices, commodity_code, crosswalk, table.gross_output
                )
                indirect = total - direct
                for name, value in (("direct", direct), ("total", total)):
                    if not math.isfinite(value):
                        raise ExposureError(
                            f"{crosswalk.industry_id}/{commodity_id}: non-finite "
                            f"{name} exposure."
                        )
                if direct == 0.0:
                    quality = "observed_zero_direct_exposure"

            weights = output_weights(crosswalk, table.gross_output)
            rows.append(
                {
                    "industry_id": crosswalk.industry_id,
                    "industry_name": crosswalk.industry_name,
                    "commodity_series_id": commodity_id,
                    "commodity_source_label": entry.get(
                        "commodity_source_label", commodity_id
                    ),
                    "commodity_io_sector_code": commodity_code,
                    "commodity_io_sector_label": sector_definitions[commodity_code][
                        "label"
                    ],
                    "industry_io_sector_codes": ";".join(crosswalk.io_sector_codes),
                    "direct_exposure": direct,
                    "indirect_exposure": indirect,
                    "total_requirement_exposure": total,
                    "exposure_unit": "io_technical_coefficient_ratio",
                    "direction_channel": channel,
                    "price_increase_to_stress_sign": sign,
                    "direction_rationale": rationale,
                    "mapping_type": entry["mapping_type"],
                    "mapping_confidence": entry["confidence"],
                    "shared_io_source_sector": bool(
                        entry.get("shared_io_source_sector", False)
                    ),
                    "shared_with": ";".join(entry.get("shares_sector_with", []) or []),
                    "industry_mapping_confidence": crosswalk.confidence,
                    "industry_component_sector_count": len(crosswalk.io_sector_codes),
                    "aggregation_weight_source": weight_source,
                    "aggregation_weights_sum": round(sum(weights.values()), 12),
                    "structural_reference_year": reference_year,
                    "time_invariant_assumption": True,
                    "valuation_basis": valuation,
                    "evidence_urls": ";".join(evidence_urls),
                    "crosswalk_version": crosswalk_version,
                    "io_source_sha256": table.sha256,
                    "quality_flag": quality,
                    "model_feature_approved": False,
                }
            )

    rows.sort(key=lambda r: (r["industry_id"], r["commodity_series_id"]))
    _validate(rows)
    return rows


def _validate(rows: list[dict]) -> None:
    """Fail loudly on any violation of the canonical contract."""
    if len(rows) != 48:
        raise ExposureError(f"Expected 48 canonical rows; built {len(rows)}.")

    keys = [(row["industry_id"], row["commodity_series_id"]) for row in rows]
    if len(set(keys)) != 48:
        raise ExposureError("Canonical keys are not unique across 48 pairs.")

    for row in rows:
        direct = row["direct_exposure"]
        indirect = row["indirect_exposure"]
        total = row["total_requirement_exposure"]
        present = [value is not None for value in (direct, indirect, total)]
        if any(present) and not all(present):
            raise ExposureError(
                f"{row['industry_id']}/{row['commodity_series_id']}: partial "
                "exposure. Direct, indirect and total are resolved together or "
                "not at all."
            )
        if all(present) and abs((direct + indirect) - total) > 1e-12:
            raise ExposureError(
                f"{row['industry_id']}/{row['commodity_series_id']}: "
                f"direct + indirect ({direct + indirect!r}) != total ({total!r})."
            )
        if row["direction_channel"] not in DIRECTION_CHANNELS:
            raise ExposureError(f"Unknown direction channel {row['direction_channel']!r}.")
        if row["direction_channel"] == "cost_pressure" and row[
            "price_increase_to_stress_sign"
        ] != 1:
            raise ExposureError("cost_pressure must carry sign +1.")
        if row["direction_channel"] == "mixed_or_ambiguous" and row[
            "price_increase_to_stress_sign"
        ] is not None:
            raise ExposureError("mixed_or_ambiguous must not carry a forced sign.")
        if row["model_feature_approved"] is not False:
            raise ExposureError("C3 must not set model_feature_approved true.")

    # The four exposures must remain ABSOLUTE. If any industry's four direct
    # coefficients sum to exactly 1, that is the signature of normalization.
    for industry_id in {row["industry_id"] for row in rows}:
        values = [
            row["direct_exposure"] for row in rows
            if row["industry_id"] == industry_id and row["direct_exposure"] is not None
        ]
        if len(values) == 4 and abs(sum(values) - 1.0) < 1e-9:
            raise ExposureError(
                f"{industry_id}: the four direct exposures sum to 1, which "
                "indicates normalization across commodities. C3 preserves "
                "absolute coefficients."
            )
