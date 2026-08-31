"""Lineage for EPPO source transformations, including the null rows (C8).

C2's lineage hashes the inputs a feature consumed, and refuses an empty list —
reasonable there, because C2 emits no row without inputs. C8 does emit such
rows: a month whose source is missing still occupies its place in the grid, and
that row has to explain itself. A null with no lineage is indistinguishable from
a null nobody looked at.

So a C8 lineage digest covers the *specification* as well as the inputs: which
transformation, which formula version, which channel, which months the formula
declared, which of them were actually available, which were missing, why, and
what came out. A row that produced 3.7 from four months and a row that produced
null because one month was absent therefore hash differently, and so do two null
rows that are null for different reasons.

Acquisition timestamps are excluded, as everywhere else in this project: the
same bytes are the same dataset whatever hour they were read.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

__all__ = [
    "LINEAGE_VERSION",
    "SOURCE_INPUT_FIELDS",
    "EppoTransformationLineageError",
    "SourceInputLineage",
    "source_input_lineage",
    "transformation_lineage_checksum",
    "transformation_lineage_record",
]

LINEAGE_VERSION = "c8_eppo_transformation_lineage_v1"

#: Ordered and fixed. The order is part of the digest contract, not an
#: implementation detail.
SOURCE_INPUT_FIELDS = (
    "series_id",
    "reference_month",
    "monthly_value_strict",
    "source_product_label",
    "semantic_equivalence_rule_id",
    "aggregation_rule_version",
    "monthly_lineage_checksum",
    "aggregation_status",
    "approved_transformation_input",
    "policy_available_month",
)


class EppoTransformationLineageError(ValueError):
    """Lineage was asked to describe something it cannot describe reproducibly."""


@dataclass
class SourceInputLineage:
    """One monthly source observation as it entered a transformation."""

    series_id: str
    reference_month: str
    monthly_value_strict: float = None
    source_product_label: str = None
    semantic_equivalence_rule_id: str = None
    aggregation_rule_version: str = None
    monthly_lineage_checksum: str = None
    aggregation_status: str = None
    approved_transformation_input: bool = False
    policy_available_month: str = None

    def to_dict(self) -> dict:
        return asdict(self)

    def checksum_tuple(self) -> list:
        return [_token(getattr(self, field)) for field in SOURCE_INPUT_FIELDS]


def _token(value):
    if value is None:
        return "\x00null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    return str(value)


def source_input_lineage(observation) -> SourceInputLineage:
    """Project a C7.5 monthly source row onto the lineage fields."""
    return SourceInputLineage(
        series_id=observation.series_id,
        reference_month=observation.reference_month,
        monthly_value_strict=observation.monthly_value_strict,
        source_product_label=observation.source_product_label,
        semantic_equivalence_rule_id=observation.semantic_equivalence_rule_id,
        aggregation_rule_version=observation.aggregation_rule_version,
        monthly_lineage_checksum=observation.monthly_lineage_checksum,
        aggregation_status=observation.aggregation_status,
        approved_transformation_input=observation.approved_transformation_input,
        policy_available_month=observation.policy_available_month,
    )


def transformation_lineage_record(
    transformation_id: str,
    transformation_formula_version: str,
    channel_id: str,
    reference_month: str,
    required_input_months,
    available_inputs,
    missing_input_months,
    feature_value,
    transformation_status: str,
    availability_policy_version: str,
    feature_unit: str = None,
) -> dict:
    """The complete, ordered lineage of one grid cell — value or null.

    ``required_input_months`` is what the formula declared; ``available_inputs``
    is what it actually got, in the same chronological order;
    ``missing_input_months`` is the difference and is stated explicitly rather
    than left to be inferred.
    """
    required = [str(m)[:7] for m in required_input_months]
    inputs = [
        item if isinstance(item, SourceInputLineage) else source_input_lineage(item)
        for item in available_inputs
    ]
    missing = sorted(str(m)[:7] for m in missing_input_months)
    if len(inputs) + len(missing) != len(required):
        raise EppoTransformationLineageError(
            f"{channel_id} {reference_month} {transformation_id}: "
            f"{len(inputs)} available + {len(missing)} missing does not account "
            f"for the {len(required)} declared input months"
        )
    if feature_value is not None and missing:
        raise EppoTransformationLineageError(
            f"{channel_id} {reference_month} {transformation_id}: a value was "
            f"produced while {missing} were missing; a partial input window may "
            "never yield a number"
        )
    return {
        "lineage_version": LINEAGE_VERSION,
        "transformation_id": transformation_id,
        "transformation_formula_version": transformation_formula_version,
        "channel_id": channel_id,
        "reference_month": str(reference_month)[:7],
        "feature_unit": feature_unit,
        "availability_policy_version": availability_policy_version,
        "expected_input_months": required,
        "available_input_months": [item.reference_month for item in inputs],
        "missing_input_months": missing,
        "missingness_reason": (
            None if transformation_status == "available_numeric"
            else transformation_status
        ),
        "input_ordering": "chronological_oldest_first_as_declared",
        "output_value": feature_value,
        "output_status": transformation_status,
        "source_inputs": [item.to_dict() for item in inputs],
    }


def transformation_lineage_checksum(record: dict) -> str:
    """SHA-256 over the ordered lineage record.

    Hashes the specification and the inputs together, so a null row still has a
    digest and two nulls with different causes do not collide.
    """
    payload = [
        record["lineage_version"],
        record["transformation_id"],
        record["transformation_formula_version"],
        record["channel_id"],
        record["reference_month"],
        _token(record.get("feature_unit")),
        record["availability_policy_version"],
        record["input_ordering"],
        _token(record["output_value"]),
        record["output_status"],
        _token(record["missingness_reason"]),
        "\x1e".join(record["expected_input_months"]),
        "\x1e".join(record["available_input_months"]),
        "\x1e".join(record["missing_input_months"]),
    ]
    for item in record["source_inputs"]:
        payload.append(
            "\x1f".join(_token(item.get(field)) for field in SOURCE_INPUT_FIELDS)
        )
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_checksum(payload) -> str:
    """Stable digest of a JSON-serialisable payload, generation time excluded."""
    dropped = {"generated_at_utc", "run_started_at_utc", "run_finished_at_utc",
               "downloaded_at_utc", "retrieved_at"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
