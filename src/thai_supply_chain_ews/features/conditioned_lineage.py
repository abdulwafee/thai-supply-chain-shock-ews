"""Combined lineage for conditioned features — Task C4.

A conditioned feature is a product of three provenances: the C2 commodity
observation, the C3 exposure coefficient, and the structural source they came
from. Its lineage checksum binds all three, so no part can be swapped without
the digest moving.

The rule that matters: **an incomplete lineage fails.** A feature whose C2 or C3
lineage is missing cannot be traced back to evidence, and an untraceable
predictor is exactly the thing this project spends its effort preventing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

__all__ = [
    "ConditionedLineageError",
    "ConditionedLineageInput",
    "conditioned_lineage_checksum",
    "exposure_row_checksum",
]

TRANSFORMATION_VERSION = "c4_industry_conditioning_v1"


class ConditionedLineageError(ValueError):
    """A lineage input was missing or malformed."""


def exposure_row_checksum(exposure_row: dict) -> str:
    """Stable digest of one C3 exposure row's identifying content.

    Covers the numbers and the decisions that qualify them, so a changed
    eligibility verdict or proxy status moves the digest just as a changed
    coefficient would.
    """
    fields = [
        "industry_id", "commodity_series_id", "commodity_io_sector_code",
        "direct_exposure", "indirect_exposure", "total_requirement_exposure",
        "direction_channel", "price_increase_to_stress_sign",
        "commodity_proxy_fit_status", "industry_pair_feature_eligible",
        "shared_io_source_sector", "crosswalk_version", "io_source_sha256",
    ]
    missing = [name for name in fields if name not in exposure_row]
    if missing:
        raise ConditionedLineageError(
            f"C3 exposure row is missing {missing}; its lineage is incomplete."
        )
    payload = json.dumps(
        [f"{exposure_row[name]!r}" for name in fields],
        separators=(",", ":"), ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConditionedLineageInput:
    """Everything that identifies one conditioned feature value."""

    c2_lineage_checksum: str
    industry_id: str
    commodity_series_id: str
    c3_exposure_checksum: str
    exposure_value: float
    direction_sign: int
    proxy_fit_status: str
    eligibility_status: bool
    matrix_variant: str
    transformation_version: str
    structural_source_checksum: str

    def checksum_tuple(self) -> list[str]:
        return [
            self.c2_lineage_checksum,
            self.industry_id,
            self.commodity_series_id,
            self.c3_exposure_checksum,
            f"{self.exposure_value!r}",
            f"{self.direction_sign!r}",
            self.proxy_fit_status,
            f"{self.eligibility_status!r}",
            self.matrix_variant,
            self.transformation_version,
            self.structural_source_checksum,
        ]


def conditioned_lineage_checksum(item: ConditionedLineageInput) -> str:
    """Deterministic SHA-256 over the ordered combined lineage.

    Every field must be present and non-empty: a blank C2 or C3 checksum would
    silently produce a well-formed digest for an untraceable feature.
    """
    required = {
        "c2_lineage_checksum": item.c2_lineage_checksum,
        "c3_exposure_checksum": item.c3_exposure_checksum,
        "structural_source_checksum": item.structural_source_checksum,
        "industry_id": item.industry_id,
        "commodity_series_id": item.commodity_series_id,
        "matrix_variant": item.matrix_variant,
        "proxy_fit_status": item.proxy_fit_status,
        "transformation_version": item.transformation_version,
    }
    blank = sorted(name for name, value in required.items() if not value)
    if blank:
        raise ConditionedLineageError(
            f"Incomplete conditioned lineage: {blank} is/are empty. A feature "
            "that cannot be traced to its inputs is not emitted."
        )
    if item.direction_sign is None:
        raise ConditionedLineageError(
            "Conditioned lineage requires a non-null direction sign."
        )
    payload = json.dumps(
        item.checksum_tuple(), separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
