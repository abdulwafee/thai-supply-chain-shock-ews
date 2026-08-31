"""Lineage for industry-conditioned fuel-oil features (Task C9).

A conditioned value is the product of two chains: a price that came through
EPPO's archive, C7's ingestion, C7.5's semantics and C8's transformation, and a
coefficient that came through NESDC's workbook, C3's crosswalk and C9's Phase-A
decision. A digest over only the first would let the structural half change
invisibly, which is the half a reader is least able to check.

So every row hashes both, plus the decision that joined them: the C8
transformation checksum and its declared input window, the C7.5 semantic mapping
digest, the sector-093 row and the NESDC workbook checksum, the crosswalk and its
gross-output weights, the exposure arithmetic, the proxy-fitness and direction
decisions, the frozen Phase-A digest, the structural availability evidence and
the conditioning formula version.

Null and ineligible rows carry the same lineage. A row that produced nothing
because IND-04's direction is unresolved and a row that produced nothing because
April 2026 is missing are different facts, and their digests differ.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "CONDITIONED_LINEAGE_VERSION",
    "SOURCE_CHAIN_FIELDS",
    "STRUCTURAL_CHAIN_FIELDS",
    "ConditionedLineageError",
    "StructuralLineage",
    "conditioned_lineage_checksum",
    "conditioned_lineage_record",
    "content_checksum",
]

CONDITIONED_LINEAGE_VERSION = "c9_fuel_oil_conditioned_lineage_v1"

SOURCE_CHAIN_FIELDS = (
    "channel_id",
    "transformation_id",
    "source_feature_value",
    "source_transformation_status",
    "source_required_input_months",
    "source_missing_input_months",
    "source_policy_available_month",
    "source_transformation_lineage_checksum",
    "c7_5_semantic_mapping_checksum",
)

STRUCTURAL_CHAIN_FIELDS = (
    "io_sector_code",
    "io_sector_label",
    "nesdc_workbook_sha256",
    "industry_id",
    "crosswalk_version",
    "component_sector_codes",
    "gross_output_weights",
    "direct_exposure",
    "exposure_weighted_mean_form",
    "exposure_summed_flow_form",
    "proxy_fit",
    "proxy_confidence",
    "direction_channel",
    "direction_multiplier",
    "structural_available_month",
    "structural_availability_evidence",
    "phase_a_decision_checksum",
)


class ConditionedLineageError(ValueError):
    """Lineage was asked to describe something it cannot describe reproducibly."""


def _token(value):
    if value is None:
        return "\x00null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\x1e".join(_token(item) for item in value)
    if isinstance(value, dict):
        return "\x1e".join(f"{k}={_token(v)}" for k, v in sorted(value.items()))
    return str(value)


@dataclass
class StructuralLineage:
    """The structural half of a conditioned row's provenance."""

    io_sector_code: str
    io_sector_label: str
    nesdc_workbook_sha256: str
    industry_id: str
    crosswalk_version: str
    component_sector_codes: list = field(default_factory=list)
    gross_output_weights: dict = field(default_factory=dict)
    direct_exposure: float = 0.0
    exposure_weighted_mean_form: float = 0.0
    exposure_summed_flow_form: float = 0.0
    proxy_fit: str = None
    proxy_confidence: str = None
    direction_channel: str = None
    direction_multiplier: object = None
    structural_available_month: str = None
    structural_availability_evidence: str = None
    phase_a_decision_checksum: str = None

    def to_dict(self) -> dict:
        return asdict(self)


def conditioned_lineage_record(row, structural: StructuralLineage,
                               c7_5_semantic_mapping_checksum: str,
                               conditioning_formula_version: str) -> dict:
    """The complete lineage of one conditioned cell, value or not."""
    source_chain = {
        "channel_id": row.channel_id,
        "transformation_id": row.transformation_id,
        "source_feature_value": row.source_feature_value,
        "source_transformation_status": row.source_transformation_status,
        "source_required_input_months": list(row.source_required_input_months),
        "source_missing_input_months": list(row.source_missing_input_months),
        "source_policy_available_month": row.source_policy_available_month,
        "source_transformation_lineage_checksum":
            row.source_transformation_lineage_checksum,
        "c7_5_semantic_mapping_checksum": c7_5_semantic_mapping_checksum,
    }
    missing_source = [f for f in SOURCE_CHAIN_FIELDS if f not in source_chain]
    if missing_source:
        raise ConditionedLineageError(
            f"source chain is missing {sorted(missing_source)}"
        )
    structural_chain = structural.to_dict()
    missing_structural = [
        f for f in STRUCTURAL_CHAIN_FIELDS if f not in structural_chain
    ]
    if missing_structural:
        raise ConditionedLineageError(
            f"structural chain is missing {sorted(missing_structural)}"
        )
    if not structural_chain["phase_a_decision_checksum"]:
        raise ConditionedLineageError(
            "the frozen Phase-A decision checksum is required on every row"
        )
    if row.conditioned_value is not None and not row.eligible:
        raise ConditionedLineageError(
            f"{row.variant_id} {row.industry_id} {row.reference_month} "
            f"{row.transformation_id}: an ineligible pair carries a value"
        )
    return {
        "lineage_version": CONDITIONED_LINEAGE_VERSION,
        "conditioning_formula_version": conditioning_formula_version,
        "variant_id": row.variant_id,
        "industry_id": row.industry_id,
        "reference_month": row.reference_month,
        "transformation_id": row.transformation_id,
        "conditioned_value": row.conditioned_value,
        "conditioned_status": row.conditioned_status,
        "conditioned_unit": row.conditioned_unit,
        "conditioned_policy_available_month": row.conditioned_policy_available_month,
        "eligible": row.eligible,
        "exclusion_reason": row.exclusion_reason,
        "quality_flag": row.quality_flag,
        "valuation_basis_alignment": row.valuation_basis_alignment,
        "source_chain": source_chain,
        "structural_chain": structural_chain,
    }


def conditioned_lineage_checksum(record: dict) -> str:
    """SHA-256 over both provenance chains and the decision that joined them."""
    payload = [
        record["lineage_version"],
        record["conditioning_formula_version"],
        record["variant_id"],
        record["industry_id"],
        record["reference_month"],
        record["transformation_id"],
        _token(record["conditioned_value"]),
        record["conditioned_status"],
        _token(record["conditioned_unit"]),
        _token(record["conditioned_policy_available_month"]),
        _token(record["eligible"]),
        _token(record["exclusion_reason"]),
        _token(record["quality_flag"]),
        _token(record["valuation_basis_alignment"]),
    ]
    payload += [
        _token(record["source_chain"][field]) for field in SOURCE_CHAIN_FIELDS
    ]
    payload += [
        _token(record["structural_chain"][field]) for field in STRUCTURAL_CHAIN_FIELDS
    ]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_checksum(payload) -> str:
    """Stable digest of a JSON-serialisable payload, generation time excluded."""
    dropped = {"generated_at_utc", "run_started_at_utc", "run_finished_at_utc"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
