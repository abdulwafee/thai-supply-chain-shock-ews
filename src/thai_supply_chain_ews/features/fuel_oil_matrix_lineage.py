"""Lineage and the frozen diagnostic contract for the C10 audit.

Two jobs.

**The contract is frozen before the values load.** Rank tolerance, near-zero
variance threshold, standardisation ``ddof``, expected dimensions, missingness
precedence and the list of permitted statistics are hashed first; the digest is
re-asserted before any C9 feature value is read and again after the diagnostics
run. A threshold moved after seeing a singular value is not a threshold, and
:func:`assert_contract_frozen` makes that unhideable rather than a promise.

**Every cell keeps both provenance branches.** A conditioned value came through
EPPO -> C7 -> C7.5 -> C8 on one side and NESDC -> C3 -> C9 Phase A on the other.
A digest over one branch would let the other change invisibly, so
:func:`matrix_cell_lineage_record` requires both and raises when either is
missing — including for the masked IND-04 cells, which have no value but do have
a reason.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "MATRIX_LINEAGE_VERSION",
    "SOURCE_BRANCH_FIELDS",
    "STRUCTURAL_BRANCH_FIELDS",
    "ContractError",
    "DiagnosticContract",
    "MatrixLineageError",
    "C9_PHASE_A_CHECKSUM",
    "SECTOR_093",
    "assert_contract_frozen",
    "assert_upstream_structure_unchanged",
    "contract_checksum",
    "content_checksum",
    "matrix_cell_lineage_checksum",
    "matrix_cell_lineage_record",
]

MATRIX_LINEAGE_VERSION = "c10_fuel_oil_matrix_lineage_v1"

#: Frozen in C9 Phase A, before any numeric feature value was read. C10 restates
#: it; it is not re-decided here.
C9_PHASE_A_CHECKSUM = (
    "d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703"
)

#: Petroleum refineries. Sector 031 is crude petroleum and was refused in C9:
#: a refinery input coefficient is not a refined-product purchase.
SECTOR_093 = "093"

SOURCE_BRANCH_FIELDS = (
    "c8_transformation_id",
    "c8_transformation_lineage_checksum",
    "c8_required_input_months",
    "c8_transformation_status",
    "c7_5_semantic_checksum",
)

STRUCTURAL_BRANCH_FIELDS = (
    "io_sector_code",
    "sector_093_direct_exposure",
    "nesdc_workbook_sha256",
    "industry_crosswalk_version",
    "gross_output_weights",
    "proxy_fit",
    "direction_channel",
    "direction_multiplier",
    "c9_phase_a_checksum",
    "structural_available_month",
)


class MatrixLineageError(ValueError):
    """A matrix cell was asked to justify itself with half its provenance."""


class ContractError(ValueError):
    """The diagnostic contract changed after the values were loaded."""


@dataclass
class DiagnosticContract:
    """Everything frozen before a C9 numeric value is read."""

    contract_version: str
    matrix_key: list = field(default_factory=list)
    expected_variants: list = field(default_factory=list)
    expected_issue_months: int = 0
    expected_industries: int = 0
    expected_transformation_columns: list = field(default_factory=list)
    expected_rows_per_variant: int = 0
    expected_cells_per_variant: int = 0
    expected_numeric_cells_per_variant: int = 0
    expected_masked_cells_per_variant: int = 0
    rank_tolerance: float = 1e-10
    near_zero_variance_threshold: float = 1e-12
    reconstruction_tolerance: float = 1e-9
    standardization_tolerance: float = 1e-9
    standardization_ddof: int = 0
    standardization_formula: str = "(x - mean) / std"
    missingness_precedence: list = field(default_factory=list)
    permitted_statistics: list = field(default_factory=list)
    primary_diagnostic_input: str = "source_time_matrix_15x5"
    channel_selection_permitted: bool = False
    feature_removal_permitted: bool = False
    target_or_model_access_permitted: bool = False
    significance_testing_permitted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def contract_checksum(contract) -> str:
    """Digest of the frozen contract, over its fields in declared order."""
    payload = contract.to_dict() if hasattr(contract, "to_dict") else dict(contract)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_contract_frozen(contract, expected_checksum: str) -> str:
    """Raise unless the contract still hashes to its frozen digest."""
    actual = contract_checksum(contract)
    if actual != expected_checksum:
        raise ContractError(
            f"the diagnostic contract now hashes to {actual}, not the frozen "
            f"{expected_checksum}. Tolerances and thresholds may not change after "
            "singular values, correlations or condition numbers have been seen"
        )
    return actual


def assert_upstream_structure_unchanged(structural_branch: dict) -> None:
    """Raise if the frozen Phase-A decision or the I/O sector moved under C10.

    Substituting sector 031 for 093 would silently swap a crude-oil input
    coefficient for a refined-product purchase, and every downstream number
    would still look well formed.
    """
    sector = structural_branch.get("io_sector_code")
    if str(sector) != SECTOR_093:
        raise MatrixLineageError(
            f"the structural branch carries I/O sector {sector!r}, not "
            f"{SECTOR_093!r}. Sector 031 is crude petroleum and was refused in C9; "
            "C10 restates the sector-093 decision and does not re-take it"
        )
    checksum = structural_branch.get("c9_phase_a_checksum")
    if checksum != C9_PHASE_A_CHECKSUM:
        raise MatrixLineageError(
            f"the C9 Phase-A decision now hashes to {checksum}, not the frozen "
            f"{C9_PHASE_A_CHECKSUM}. C10 audits that decision and may not run "
            "against a changed one"
        )


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


def matrix_cell_lineage_record(cell: dict, source_branch: dict,
                               structural_branch: dict,
                               selection_rule: str,
                               contract_checksum_value: str) -> dict:
    """The complete provenance of one development-matrix cell, masked or not."""
    missing_source = [f for f in SOURCE_BRANCH_FIELDS if f not in source_branch]
    if missing_source:
        raise MatrixLineageError(
            f"the C8 source branch is missing {sorted(missing_source)}; a cell "
            "traced through only one provenance chain is not traced"
        )
    missing_structural = [
        f for f in STRUCTURAL_BRANCH_FIELDS if f not in structural_branch
    ]
    if missing_structural:
        raise MatrixLineageError(
            f"the structural branch is missing {sorted(missing_structural)}; a cell "
            "traced through only one provenance chain is not traced"
        )
    if not structural_branch.get("c9_phase_a_checksum"):
        raise MatrixLineageError("the frozen C9 Phase-A checksum is required")
    assert_upstream_structure_unchanged(structural_branch)
    if cell.get("value") is not None and cell.get("cell_state") != "numeric":
        raise MatrixLineageError(
            f"{cell.get('industry_id')} {cell.get('issue_month')} is "
            f"{cell.get('cell_state')} yet carries a value"
        )
    if cell.get("value") is None and not cell.get("mask_reason"):
        raise MatrixLineageError(
            f"{cell.get('industry_id')} {cell.get('issue_month')} has no value and "
            "no masking reason"
        )
    return {
        "lineage_version": MATRIX_LINEAGE_VERSION,
        "variant_id": cell["variant_id"],
        "issue_month": cell["issue_month"],
        "industry_id": cell["industry_id"],
        "transformation_id": cell["transformation_id"],
        "reference_month": cell["reference_month"],
        "value": cell.get("value"),
        "cell_state": cell["cell_state"],
        "masked": bool(cell.get("masked")),
        "mask_reason": cell.get("mask_reason"),
        "conditioned_lineage_checksum": cell.get("conditioned_lineage_checksum"),
        "variant_and_issue_selection_rule": selection_rule,
        "diagnostic_contract_checksum": contract_checksum_value,
        "source_branch": dict(source_branch),
        "structural_branch": dict(structural_branch),
    }


def matrix_cell_lineage_checksum(record: dict) -> str:
    """SHA-256 over both provenance branches and the selection rule."""
    payload = [
        record["lineage_version"], record["variant_id"], record["issue_month"],
        record["industry_id"], record["transformation_id"],
        record["reference_month"], _token(record["value"]), record["cell_state"],
        _token(record["masked"]), _token(record["mask_reason"]),
        _token(record["conditioned_lineage_checksum"]),
        record["variant_and_issue_selection_rule"],
        record["diagnostic_contract_checksum"],
    ]
    payload += [_token(record["source_branch"][f]) for f in SOURCE_BRANCH_FIELDS]
    payload += [
        _token(record["structural_branch"][f]) for f in STRUCTURAL_BRANCH_FIELDS
    ]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_checksum(payload) -> str:
    """Stable digest of a JSON payload, generation timestamps excluded."""
    dropped = {"generated_at_utc", "run_started_at_utc", "run_finished_at_utc"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
