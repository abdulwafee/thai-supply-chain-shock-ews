"""Task C10 tests — development-only design-matrix identifiability audit.

Three failures here would survive every downstream check.

The first is **an inflated sample**. C9 produced 165 eligible rows per variant,
and every one of them is the same 15 x 5 source-time matrix multiplied by that
industry's positive sector-093 exposure. A rank, a condition number or a
correlation computed on the stacked panel is arithmetically fine and rhetorically
false, because it presents fifteen distinct temporal rows as though there were
165. The primary-input guard and the independence-claim guard are both exercised.

The second is **a threshold that moved**. The rank tolerance, the near-zero
variance threshold, the two residual tolerances and the standardisation ``ddof``
were written before a single C9 value was read and hashed into a frozen
contract. A tolerance chosen after seeing a singular value is not a tolerance,
so the contract digest is re-asserted before the load and after the diagnostics.

The third is **an absence turned into a measurement**. IND-04's design is
unresolved, not zero and not missing. Dropping its rows would make the table
rectangular by deleting the one row that records a structural limitation;
zero-filling them would assert an exposure nobody measured. Both collapses are
constructed here and required to raise.

Everything in this module is outcome-free: no target, no prediction, no metric,
no locked test.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.features import fuel_oil_development_matrix as DM
from thai_supply_chain_ews.features import fuel_oil_identifiability as ID
from thai_supply_chain_ews.features import fuel_oil_industry_conditioning as C9
from thai_supply_chain_ews.features import fuel_oil_matrix_lineage as ML
from thai_supply_chain_ews.features import fuel_oil_standardization as ST

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "fuel_oil_development_matrix.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
SCHEMA_PATH = ROOT / "schemas" / "fuel_oil_development_matrix.schema.yaml"
AUDIT = ROOT / "docs" / "c10_design_matrix_audit.json"
PROTOCOL = ROOT / "docs" / "c10_design_matrix_protocol.md"
AUDIT_MD = ROOT / "docs" / "c10_design_matrix_audit.md"
RUNNER = ROOT / "scripts" / "run_c10_design_matrix_audit.py"
SNAPSHOT = ROOT / "data" / "features" / "c9_fuel_oil_development_snapshot.parquet"
PHASE_A = ROOT / "docs" / "c9_sector093_exposure_decision.json"
WIDE = ROOT / "data" / "features" / "c10_fuel_oil_development_wide.parquet"
MASK = ROOT / "data" / "features" / "c10_fuel_oil_development_mask.parquet"

V600, V1500 = "fo600_direct_sector093", "fo1500_direct_sector093"
COLUMNS = list(DM.TRANSFORMATION_COLUMNS)

requires_run = pytest.mark.skipif(not AUDIT.is_file(), reason="C10 has not been run")
requires_snapshot = pytest.mark.skipif(
    not SNAPSHOT.is_file(), reason="the C9 development snapshot is not present"
)


def _audit():
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def _phase_a():
    return json.loads(PHASE_A.read_text(encoding="utf-8"))


def _exposures():
    return {
        row["industry_id"]: row["direct_exposure"]
        for row in _phase_a()["decisions"]
        if row["channel_id"] == "eppo_fo600_channel"
    }


# ---------------------------------------------------------------------------
# Synthetic fixtures. Small, hand-built, and independent of the real snapshot,
# so a failure here is a failure of the guard and not of the data.
# ---------------------------------------------------------------------------
MONTHS = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
INDUSTRIES = ["IND-01", "IND-02", "IND-04"]
BASE = [
    [1.0, 2.0, 3.0, 40.0, 5.0],
    [1.5, 2.5, 3.5, 41.0, 5.5],
    [2.0, 1.0, 4.0, 42.0, 6.5],
    [0.5, 3.0, 2.5, 43.5, 4.5],
    [3.0, 0.5, 5.0, 44.5, 7.5],
    [2.5, 1.5, 1.5, 45.0, 3.5],
]
FAKE_EXPOSURES = {"IND-01": 0.01, "IND-02": 0.04, "IND-04": 0.02}


def _cells(variant_id=V600, industries=INDUSTRIES, months=MONTHS,
           ineligible=("IND-04",), columns=COLUMNS):
    cells = []
    for month_index, month in enumerate(months):
        reference = DM.shift_month(month, -DM.POLICY_LAG_MONTHS)
        for industry in industries:
            masked = industry in ineligible
            for column_index, column in enumerate(columns):
                value = None if masked else (
                    BASE[month_index][column_index] * FAKE_EXPOSURES[industry]
                )
                cells.append({
                    "variant_id": variant_id,
                    "issue_month": month,
                    "industry_id": industry,
                    "transformation_id": column,
                    "reference_month": reference,
                    "value": value,
                    "cell_state": "masked_ineligible" if masked else "numeric",
                    "masked": masked,
                    "mask_reason": (
                        "direction_unresolved_mixed_producer_consumer"
                        if masked else None
                    ),
                    "conditioned_status": (
                        "not_generated_due_to_direction_ambiguity" if masked
                        else "available_nonzero"
                    ),
                    "conditioned_policy_available_month": month,
                    "conditioned_lineage_checksum": f"c9-{industry}-{month}-{column}",
                })
    return cells


def _matrix(**kwargs):
    cells = kwargs.pop("cells", None) or _cells(**kwargs)
    return DM.build_development_matrix(
        cells, kwargs.get("variant_id", V600),
        kwargs.get("industries", INDUSTRIES), kwargs.get("months", MONTHS),
    )


def _source_branch(**overrides):
    branch = {
        "c8_transformation_id": "price_level",
        "c8_transformation_lineage_checksum": "c8-checksum",
        "c8_required_input_months": ["2023-11"],
        "c8_transformation_status": "available",
        "c7_5_semantic_checksum": "c75-checksum",
    }
    branch.update(overrides)
    return branch


def _structural_branch(**overrides):
    branch = {
        "io_sector_code": "093",
        "sector_093_direct_exposure": 0.0085557229,
        "nesdc_workbook_sha256": "nesdc-sha",
        "industry_crosswalk_version": "v1",
        "gross_output_weights": {"093": 1.0},
        "proxy_fit": "adequate",
        "direction_channel": "cost_pressure",
        "direction_multiplier": 1.0,
        "c9_phase_a_checksum": ML.C9_PHASE_A_CHECKSUM,
        "structural_available_month": "2020-03",
    }
    branch.update(overrides)
    return branch


def _lineage_cell(**overrides):
    cell = {
        "variant_id": V600, "issue_month": "2024-01", "industry_id": "IND-01",
        "transformation_id": "price_level", "reference_month": "2023-11",
        "value": 0.38, "cell_state": "numeric", "masked": False,
        "mask_reason": None, "conditioned_lineage_checksum": "c9-checksum",
    }
    cell.update(overrides)
    return cell


def _contract(**overrides):
    spec = CONFIG["diagnostic_contract"]
    fields = {
        "contract_version": CONFIG["contract_version"],
        "matrix_key": list(spec["matrix_key"]),
        "expected_variants": list(spec["expected_variants"]),
        "expected_issue_months": spec["expected_issue_months"],
        "expected_industries": spec["expected_industries"],
        "expected_transformation_columns":
            list(spec["expected_transformation_columns"]),
        "expected_rows_per_variant": spec["expected_rows_per_variant"],
        "expected_cells_per_variant": spec["expected_cells_per_variant"],
        "expected_numeric_cells_per_variant":
            spec["expected_numeric_cells_per_variant"],
        "expected_masked_cells_per_variant":
            spec["expected_masked_cells_per_variant"],
        "rank_tolerance": float(spec["rank_tolerance"]),
        "near_zero_variance_threshold": float(spec["near_zero_variance_threshold"]),
        "reconstruction_tolerance": float(spec["reconstruction_tolerance"]),
        "standardization_tolerance": float(spec["standardization_tolerance"]),
        "standardization_ddof": int(spec["standardization_ddof"]),
        "standardization_formula": spec["standardization_formula"],
        "missingness_precedence": list(spec["missingness_precedence"]),
        "permitted_statistics": list(spec["permitted_statistics"]),
        "primary_diagnostic_input": spec["primary_diagnostic_input"],
        "channel_selection_permitted": spec["channel_selection_permitted"],
        "feature_removal_permitted": spec["feature_removal_permitted"],
        "target_or_model_access_permitted": spec["target_or_model_access_permitted"],
        "significance_testing_permitted": spec["significance_testing_permitted"],
    }
    fields.update(overrides)
    return ML.DiagnosticContract(**fields)


# ---------------------------------------------------------------------------
# Configuration and contract
# ---------------------------------------------------------------------------
def test_the_config_parses_and_declares_its_thresholds():
    spec = CONFIG["diagnostic_contract"]
    assert float(spec["rank_tolerance"]) == 1e-10
    assert float(spec["near_zero_variance_threshold"]) == 1e-12
    assert float(spec["reconstruction_tolerance"]) == 1e-9
    assert float(spec["standardization_tolerance"]) == 1e-9
    assert int(spec["standardization_ddof"]) == 0
    assert spec["primary_diagnostic_input"] == "source_time_matrix_15x5"


def test_the_schema_parses_and_forbids_target_columns():
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    prohibited = set(schema["prohibited_columns"]["columns"])
    assert {"stress_score", "y_true", "prediction", "residual"} <= prohibited
    tables = {t["table"] for t in schema["tables"]}
    assert "features/c10_fuel_oil_development_wide" in tables


def test_the_config_refuses_channel_selection_and_feature_removal():
    spec = CONFIG["diagnostic_contract"]
    assert spec["channel_selection_permitted"] is False
    assert spec["feature_removal_permitted"] is False
    assert spec["target_or_model_access_permitted"] is False
    assert spec["significance_testing_permitted"] is False


def test_the_contract_checksum_is_stable_and_order_independent():
    first = ML.contract_checksum(_contract())
    second = ML.contract_checksum(_contract())
    assert first == second
    assert ML.assert_contract_frozen(_contract(), first) == first


def test_the_units_and_interpretation_survive_from_c9():
    units = CONFIG["units"]
    assert units["price_level"] == "baht_per_litre_x_io_coefficient"
    assert units["realized_volatility_3m_pct"].endswith("_x_io_coefficient")
    interpretation = CONFIG["interpretation"]
    assert interpretation["structural_interaction_only"] is True
    for field in ("currency_cost_per_unit_of_industrial_output", "elasticity",
                  "pass_through", "causal_effect", "forecast_coefficient"):
        assert interpretation[field] is False
    assert "purchasers_price" in interpretation["valuation_basis_alignment"]


# ---------------------------------------------------------------------------
# Matrix assembly
# ---------------------------------------------------------------------------
def test_the_matrix_keeps_every_industry_and_masks_the_ineligible_one():
    matrix = _matrix()
    assert matrix.industry_ids == sorted(INDUSTRIES)
    assert matrix.eligible_industries == ["IND-01", "IND-02"]
    assert matrix.masked_industries == ["IND-04"]
    assert matrix.fully_numeric_rows == 12
    assert matrix.fully_masked_rows == 6
    assert matrix.numeric_cells == 60
    assert matrix.masked_cells == 30


def test_the_reference_month_comes_from_the_recorded_field():
    matrix = _matrix()
    assert matrix.reference_months == [
        DM.shift_month(month, -2) for month in MONTHS
    ]


def test_a_masked_row_has_no_numeric_design():
    matrix = _matrix()
    with pytest.raises(DM.MatrixAssemblyError, match="masked_ineligible"):
        matrix.row("2024-01", "IND-04")


def test_the_stacked_panel_is_the_source_time_matrix_repeated():
    matrix = _matrix()
    stacked = matrix.stacked_eligible_panel()
    assert len(stacked) == len(matrix.eligible_industries) * len(MONTHS)
    assert ID.numerical_rank(stacked) == ID.numerical_rank(
        matrix.source_time_matrix(FAKE_EXPOSURES)
    )


# ---------------------------------------------------------------------------
# Identifiability
# ---------------------------------------------------------------------------
def test_the_cross_section_at_every_issue_month_has_rank_one():
    matrix = _matrix()
    designs = {g: matrix.industry_design(g) for g in matrix.eligible_industries}
    for index in range(len(MONTHS)):
        assert ID.cross_sectional_rank(designs, index) == 1


def test_every_industry_matrix_has_the_source_time_rank():
    matrix = _matrix()
    source_time = matrix.source_time_matrix(FAKE_EXPOSURES)
    expected = ID.numerical_rank(source_time)
    for industry in matrix.eligible_industries:
        assert ID.numerical_rank(matrix.industry_design(industry)) == expected


def test_variance_separates_a_constant_column_from_a_zero_observation():
    matrix = [[0.0, 7.0], [1.0, 7.0], [0.0, 7.0]]
    report = ID.variance_report(matrix, ["varies_with_zeros", "constant"])
    assert report["constant"]["exact_zero_variance"] is True
    assert report["constant"]["exact_zero_observations"] == 0
    assert report["varies_with_zeros"]["exact_zero_variance"] is False
    assert report["varies_with_zeros"]["exact_zero_observations"] == 2
    assert all(entry["retained"] for entry in report.values())


def test_standardize_leaves_a_constant_column_centred_not_scaled():
    standardized = ID.standardize([[7.0], [7.0], [7.0]])
    assert standardized == [[0.0], [0.0], [0.0]]


def test_duplicate_columns_are_found_algebraically_not_by_correlation():
    matrix = [[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]]
    assert ID.correlation_matrix(matrix, ["a", "b"])["a|b"] == pytest.approx(1.0)
    assert ID.duplicate_columns(matrix, ["a", "b"]) == []


# ---------------------------------------------------------------------------
# Standardization invariance
# ---------------------------------------------------------------------------
def test_exposure_normalisation_recovers_one_source_time_matrix():
    matrix = _matrix()
    report = ST.reconstruction_report(
        matrix, FAKE_EXPOSURES, matrix.eligible_industries, BASE
    )
    assert report.distinct_raw_fingerprints == 2
    assert report.normalized_equivalence_classes == 1
    assert report.all_designs_are_scalar_multiples is True
    assert report.max_residual < 1e-12
    assert report.source_reconciliation_residual < 1e-12


def test_positive_scalar_exposure_does_not_survive_standardization():
    matrix = _matrix()
    report = ST.standardization_invariance_report(
        matrix, FAKE_EXPOSURES, matrix.eligible_industries
    )
    assert report["standardized_equivalence_classes"] == 1
    assert report["identity_holds"] is True
    assert report["exposure_survives_per_industry_standardization"] is False
    assert report["industry_specific_temporal_pattern_present"] is False


def test_the_ineligible_industry_is_never_exposure_normalised():
    with pytest.raises(ST.StandardizationError, match="structurally ineligible"):
        ST.assert_positive_exposure("IND-04", 0.0097966621, eligible=False)


def test_equivalence_classes_use_the_tolerance_not_the_fingerprint():
    a = [[1.0, 2.0], [3.0, 4.0]]
    b = [[1.0 + 1e-15, 2.0], [3.0, 4.0]]
    assert ID.fingerprint(a, 20) != ID.fingerprint(b, 20)
    assert len(ST.equivalence_classes({"a": a, "b": b}, 1e-9)) == 1


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------
def test_lineage_carries_both_provenance_branches():
    record = ML.matrix_cell_lineage_record(
        _lineage_cell(), _source_branch(), _structural_branch(),
        "one variant per matrix", "contract-digest",
    )
    for field in ML.SOURCE_BRANCH_FIELDS:
        assert field in record["source_branch"]
    for field in ML.STRUCTURAL_BRANCH_FIELDS:
        assert field in record["structural_branch"]
    assert len(ML.matrix_cell_lineage_checksum(record)) == 64


def test_a_masked_cell_still_carries_lineage():
    record = ML.matrix_cell_lineage_record(
        _lineage_cell(value=None, cell_state="masked_ineligible", masked=True,
                      mask_reason="direction_unresolved"),
        _source_branch(), _structural_branch(), "rule", "digest",
    )
    assert record["value"] is None
    assert record["mask_reason"] == "direction_unresolved"
    assert len(ML.matrix_cell_lineage_checksum(record)) == 64


def test_lineage_changes_when_either_branch_changes():
    base = ML.matrix_cell_lineage_checksum(ML.matrix_cell_lineage_record(
        _lineage_cell(), _source_branch(), _structural_branch(), "rule", "digest"))
    source_changed = ML.matrix_cell_lineage_checksum(ML.matrix_cell_lineage_record(
        _lineage_cell(), _source_branch(c8_transformation_lineage_checksum="other"),
        _structural_branch(), "rule", "digest"))
    structural_changed = ML.matrix_cell_lineage_checksum(ML.matrix_cell_lineage_record(
        _lineage_cell(), _source_branch(),
        _structural_branch(sector_093_direct_exposure=0.5), "rule", "digest"))
    assert len({base, source_changed, structural_changed}) == 3


def test_content_checksum_ignores_the_generation_timestamp():
    first = ML.content_checksum({"a": 1, "generated_at_utc": "2026-01-01"})
    second = ML.content_checksum({"a": 1, "generated_at_utc": "2026-08-29"})
    assert first == second


# ---------------------------------------------------------------------------
# Static separation
# ---------------------------------------------------------------------------
def test_c10_modules_import_no_target_evaluation_or_model_code():
    banned = ("targets", "evaluation", "models", "backtest")
    for name in ("fuel_oil_development_matrix", "fuel_oil_identifiability",
                 "fuel_oil_standardization", "fuel_oil_matrix_lineage"):
        path = ROOT / "src" / "thai_supply_chain_ews" / "features" / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for module in names:
                assert not any(f".{b}" in f".{module}" for b in banned), (
                    f"{name} imports {module}"
                )


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C10 runner is not present")
def test_the_runner_reads_no_target_or_locked_artifact():
    """No line that opens a file may name a target, prediction or locked path.

    Denial fields such as ``locked_test_accessed: false`` mention the same
    words, so the check is on the *reads*, not on the whole file.
    """
    reads = ("read_parquet", "read_text", "load_json(", "load_yaml(", "open(")
    banned = ("target", "production_stress", "prediction", "residual",
              "locked", "holdout", "evaluation", "walk_forward")
    for line in RUNNER.read_text(encoding="utf-8").splitlines():
        if not any(read in line for read in reads):
            continue
        lowered = line.lower()
        for fragment in banned:
            assert fragment not in lowered, line.strip()


# ---------------------------------------------------------------------------
# The generated audit
# ---------------------------------------------------------------------------
@requires_run
def test_the_audit_reports_both_variants_separately():
    payload = _audit()
    assert sorted(payload["per_variant"]) == sorted([V600, V1500])
    for entry in payload["per_variant"].values():
        assert entry["matrix_dimensions"] == {"rows": 180, "columns": 5, "cells": 900}
        assert entry["numeric_cells"] == 825
        assert entry["masked_cells"] == 75
        assert entry["fully_numeric_rows"] == 165
        assert entry["fully_masked_rows"] == 15
        assert entry["masked_industries"] == ["IND-04"]
        assert len(entry["eligible_industries"]) == 11


@requires_run
def test_the_audit_reports_every_required_conclusion():
    required = (
        "matrix_dimensions", "numeric_cells", "masked_cells",
        "unique_temporal_rows", "source_time_rank", "stacked_panel_rank",
        "cross_sectional_rank_by_issue", "singular_values",
        "raw_condition_number", "standardized_condition_number", "variance",
        "pearson", "spearman", "exposure_normalization",
        "standardization_invariance",
    )
    for entry in _audit()["per_variant"].values():
        for field in required:
            assert field in entry, field
        assert entry["exposure_normalization"]["distinct_raw_fingerprints"] == 11
        assert "distinct_normalized_fingerprints" in entry["exposure_normalization"]
        assert "distinct_standardized_fingerprints" in (
            entry["standardization_invariance"]
        )


@requires_run
def test_the_audit_reports_every_required_decision_field():
    decisions = _audit()["decisions"]
    assert decisions["development_matrix_assembled"] is True
    assert decisions["conditioning_adds_cross_industry_scale"] is True
    assert decisions["conditioning_adds_temporal_degrees_of_freedom"] is False
    assert decisions["per_industry_standardization_removes_exposure_scale"] is True
    for field in ("predictive_utility_assessed", "channel_selected",
                  "target_joined", "model_trained", "model_feature_approved",
                  "locked_test_accessed", "target_join_authorized",
                  "modeling_authorized",
                  "variant_promoted_to_modeling_readiness"):
        assert decisions[field] is False, field


@requires_run
def test_full_rank_does_not_promote_a_variant_to_modeling_readiness():
    payload = _audit()
    assert all(e["source_time_rank"] == 5 for e in payload["per_variant"].values())
    assert payload["decisions"]["variant_promoted_to_modeling_readiness"] is False
    assert payload["decisions"]["modeling_authorized"] is False


@requires_run
def test_the_stacked_panel_is_never_presented_as_independent():
    payload = _audit()
    assert payload["structural_findings"][
        "stacked_rows_are_independent_claim_permitted"] is False
    assert payload["structural_findings"][
        "temporal_independence_claim_permitted"] is False
    for entry in payload["per_variant"].values():
        assert entry["unique_temporal_rows"] == 15
        assert entry["stacked_panel_rows"] == 165
        assert entry["stacked_panel_rank"] == entry["source_time_rank"]
    for document in (PROTOCOL, AUDIT_MD):
        ID.assert_no_independence_claim(document.read_text(encoding="utf-8"))


@requires_run
def test_the_cross_sectional_rank_is_one_at_every_issue_month():
    for entry in _audit()["per_variant"].values():
        ranks = set(entry["cross_sectional_rank_by_issue"].values())
        assert ranks == {1}
        assert len(entry["cross_sectional_rank_by_issue"]) == 15


@requires_run
def test_the_identities_hold_within_the_frozen_tolerances():
    contract = _audit()["diagnostic_contract"]
    for entry in _audit()["per_variant"].values():
        normalization = entry["exposure_normalization"]
        invariance = entry["standardization_invariance"]
        assert normalization["max_residual"] <= contract["reconstruction_tolerance"]
        assert normalization["normalized_equivalence_classes"] == 1
        assert normalization["source_reconciliation_residual"] <= (
            contract["reconstruction_tolerance"]
        )
        assert invariance["max_standardized_design_residual"] <= (
            contract["standardization_tolerance"]
        )
        assert invariance["standardized_equivalence_classes"] == 1
        assert invariance["identity_holds"] is True


@requires_run
def test_no_transformation_was_removed_and_no_column_is_degenerate():
    for entry in _audit()["per_variant"].values():
        assert sorted(entry["variance"]) == sorted(COLUMNS)
        assert entry["features_removed"] == []
        for stats in entry["variance"].values():
            assert stats["retained"] is True
            assert stats["exact_zero_variance"] is False
            assert stats["near_zero_variance"] is False
        assert entry["exact_duplicate_columns"] == []
        assert entry["variance_classification_agreement"][
            "all_eligible_industries_agree"] is True


@requires_run
def test_correlations_are_descriptive_and_select_nothing():
    payload = _audit()
    assert payload["identifiability"]["significance_tests_reported"] is False
    assert payload["identifiability"]["correlations_used_to_select_a_channel"] is False
    assert payload["identifiability"][
        "correlations_used_to_remove_a_transformation"] is False
    for entry in payload["per_variant"].values():
        assert entry["significance_tested"] is False
        assert entry["channel_selected"] is False
        assert len(entry["pearson"]) == 10
        assert len(entry["spearman"]) == 10
        for value in entry["pearson"].values():
            assert -1.0 <= value <= 1.0


@requires_run
def test_availability_is_checked_against_the_recorded_fields():
    for entry in _audit()["per_variant"].values():
        availability = entry["availability"]
        assert availability["lag_two_violations"] == 0
        assert availability["policy_availability_violations"] == 0
        assert availability["backdated_to_reference_year"] is False
        assert availability["source_available_as_of"] is None
        assert availability["latest_vintage_used"] is True
        assert availability["point_in_time_supported"] is False
        assert availability["fully_real_time_backtest"] is False
        assert availability[
            "checked_against_recorded_fields_not_positional_shift"] is True


@requires_run
def test_lineage_covers_all_1800_development_cells():
    payload = _audit()
    total = sum(
        entry["lineage"]["cells_with_a_checksum"]
        for entry in payload["per_variant"].values()
    )
    assert total == 1800
    for entry in payload["per_variant"].values():
        assert entry["lineage"]["distinct_checksums"] == 900


@requires_run
def test_the_two_channels_are_never_combined():
    payload = _audit()
    assert payload["matrices"]["variants_horizontally_concatenated"] is False
    assert payload["matrices"]["ten_column_modeling_matrix_created"] is False
    assert payload["channels"]["preferred_channel_produced"] is False
    assert payload["channels"]["artifacts_kept_separate"] is True


@requires_run
def test_ind_04_is_kept_masked_and_not_zeroed():
    payload = _audit()
    assert payload["matrices"]["ind_04_rows_dropped"] is False
    assert payload["matrices"]["ind_04_masks_converted_to_zero"] is False
    assert payload["matrices"]["rows_removed_to_make_a_complete_case_table"] is False


@requires_run
def test_the_contract_was_frozen_before_and_after_the_values_loaded():
    payload = _audit()
    assert payload["contract_frozen_before_values_loaded"] is True
    assert payload["contract_reasserted_after_diagnostics"] is True
    contract = ML.DiagnosticContract(**payload["diagnostic_contract"])
    assert ML.contract_checksum(contract) == payload[
        "diagnostic_contract_checksum"]


@requires_run
def test_upstream_invariants_all_reproduced():
    invariants = _audit()["upstream_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 25


@requires_run
def test_preregistered_discrepancies_are_reported_not_relaxed():
    block = _audit()["preregistered_expectation_discrepancies"]
    assert block["thresholds_changed_after_observation"] is False
    assert block["expectations_relaxed_to_obtain_a_pass"] is False
    for item in block["items"]:
        assert item["preregistered_value"] != item["observed_value"]
        assert item["threshold_changed_after_observation"] is False


@requires_run
def test_the_content_checksum_reproduces_from_the_payload():
    payload = _audit()
    stored = payload.pop("content_checksum")
    assert ML.content_checksum(payload) == stored


@pytest.mark.skipif(not WIDE.is_file(), reason="the C10 wide matrix is not present")
def test_the_generated_tables_have_no_target_or_model_column():
    import pandas as pd

    banned = ("stress", "target", "y_true", "y_pred", "prediction", "residual",
              "mae", "rmse", "metric", "locked")
    for path in (WIDE, MASK):
        columns = [c.lower() for c in pd.read_parquet(path).columns]
        for column in columns:
            assert not any(b in column for b in banned), f"{path.name}:{column}"


@pytest.mark.skipif(not WIDE.is_file(), reason="the C10 wide matrix is not present")
def test_the_wide_table_holds_360_rows_and_keeps_ind_04():
    import pandas as pd

    frame = pd.read_parquet(WIDE)
    assert len(frame) == 360
    assert frame["industry_id"].nunique() == 12
    masked = frame[frame["industry_id"] == "IND-04"]
    assert len(masked) == 30
    assert bool(masked["masked"].all())
    assert bool(masked[COLUMNS].isna().all().all())


@requires_snapshot
def test_the_real_snapshot_reconstructs_one_source_time_matrix_per_variant():
    """An independent reconstruction, built here rather than read from the audit."""
    import pandas as pd

    snapshot = pd.read_parquet(SNAPSHOT)
    exposures = _exposures()
    industries = sorted(snapshot["industry_id"].unique())
    months = sorted(snapshot["issue_month"].unique())
    for variant_id in (V600, V1500):
        rows = snapshot[snapshot["variant_id"] == variant_id].to_dict("records")
        cells = [{
            **row,
            "value": None if pd.isna(row["value"]) else float(row["value"]),
            "masked": bool(row["masked"]),
            "mask_reason": (
                row["mask_reason"] if isinstance(row["mask_reason"], str) else None
            ),
        } for row in rows]
        matrix = DM.build_development_matrix(cells, variant_id, industries, months)
        source_time = matrix.source_time_matrix(exposures)
        assert len(source_time) == 15
        assert ID.numerical_rank(source_time) == 5
        assert ID.numerical_rank(matrix.stacked_eligible_panel()) == 5
        report = ST.reconstruction_report(
            matrix, exposures, matrix.eligible_industries, source_time
        )
        assert report.normalized_equivalence_classes == 1
        assert report.max_residual < 1e-9
        designs = {g: matrix.industry_design(g) for g in matrix.eligible_industries}
        for index in range(15):
            assert ID.cross_sectional_rank(designs, index) == 1


# ===========================================================================
# The eighteen required synthetic failures.
# ===========================================================================
def test_synthetic_1_phase_a_checksum_changed():
    with pytest.raises(ML.MatrixLineageError, match="Phase-A"):
        ML.matrix_cell_lineage_record(
            _lineage_cell(), _source_branch(),
            _structural_branch(c9_phase_a_checksum="0" * 64), "rule", "digest",
        )


def test_synthetic_2_sector_031_substituted_for_093():
    with pytest.raises(ML.MatrixLineageError, match="crude petroleum"):
        ML.matrix_cell_lineage_record(
            _lineage_cell(), _source_branch(),
            _structural_branch(io_sector_code="031"), "rule", "digest",
        )


def test_synthetic_3_the_two_fuel_oil_variants_combined():
    with pytest.raises(DM.MatrixAssemblyError, match="same"):
        DM.assert_variants_not_combined(
            [V600, V1500], "a ten-column simultaneous modeling matrix"
        )
    with pytest.raises(DM.MatrixAssemblyError):
        DM.build_development_matrix(
            _cells(V600) + _cells(V1500), V600, INDUSTRIES, MONTHS
        )


def test_synthetic_4_ind_04_dropped_from_the_matrix():
    cells = [c for c in _cells() if c["industry_id"] != "IND-04"]
    with pytest.raises(DM.MatrixAssemblyError, match="missing matrix keys"):
        DM.build_development_matrix(cells, V600, INDUSTRIES, MONTHS)


def test_synthetic_5_ind_04_masks_converted_to_zero():
    cells = _cells()
    for cell in cells:
        if cell["industry_id"] == "IND-04":
            cell["value"] = 0.0
    with pytest.raises(DM.MatrixAssemblyError, match="not zero"):
        DM.build_development_matrix(cells, V600, INDUSTRIES, MONTHS)


def test_synthetic_6_a_source_null_converted_to_zero():
    cell = {
        "variant_id": V600, "industry_id": "IND-01", "issue_month": "2024-01",
        "transformation_id": "price_level", "cell_state": "rejected_source_null",
        "masked": True, "mask_reason": "source_insufficient_history", "value": 0.0,
    }
    with pytest.raises(DM.MatrixAssemblyError, match="not zero"):
        DM.assert_mask_not_zeroed(cell)
    with pytest.raises(C9.ConditioningError, match="still absent"):
        C9.assert_null_not_converted_to_zero({
            "variant_id": V600, "industry_id": "IND-01",
            "reference_month": "2023-11", "transformation_id": "price_level",
            "conditioned_status": "source_insufficient_history",
            "conditioned_value": 0.0,
        })


def test_synthetic_7_stacked_rows_reported_as_independent():
    for claim in ("the panel provides 165 independent observations",
                  "165 observations across eleven industries",
                  "an effective sample size of 165 rows"):
        with pytest.raises(ID.IdentifiabilityError):
            ID.assert_no_independence_claim(claim)


def test_synthetic_8_primary_diagnostics_use_the_stacked_panel():
    matrix = _matrix()
    stacked = matrix.stacked_eligible_panel()
    with pytest.raises(ID.IdentifiabilityError, match="inflate the apparent sample"):
        ID.assert_primary_input_is_source_time(
            stacked, len(MONTHS), "rank diagnostics"
        )


def test_synthetic_9_exposure_normalised_fingerprints_disagree():
    matrix = _matrix()
    wrong = dict(FAKE_EXPOSURES)
    wrong["IND-02"] = wrong["IND-02"] * 1.05
    with pytest.raises(ST.StandardizationError, match="reconstructions differ"):
        ST.reconstruction_report(matrix, wrong, matrix.eligible_industries)


def test_synthetic_10_positive_exposure_changes_the_standardized_design():
    """A conditioning error that scale alone cannot produce.

    IND-02's design is given an extra additive tilt, so it is no longer a
    scalar multiple of the source-time matrix. The standardised designs then
    genuinely differ and the invariance report must say so.
    """
    cells = _cells()
    for cell in cells:
        if cell["industry_id"] == "IND-02" and cell["value"] is not None:
            cell["value"] = cell["value"] + 0.5 * MONTHS.index(cell["issue_month"])
    matrix = DM.build_development_matrix(cells, V600, INDUSTRIES, MONTHS)
    report = ST.standardization_invariance_report(
        matrix, FAKE_EXPOSURES, matrix.eligible_industries
    )
    assert report["identity_holds"] is False
    assert report["exposure_survives_per_industry_standardization"] is True
    assert report["industry_specific_temporal_pattern_present"] is True
    assert report["standardized_equivalence_classes"] > 1


def test_synthetic_11_rank_tolerance_altered_after_values_are_loaded():
    frozen = ML.contract_checksum(_contract())
    loosened = _contract(rank_tolerance=1e-6)
    with pytest.raises(ML.ContractError, match="may not change"):
        ML.assert_contract_frozen(loosened, frozen)


def test_synthetic_12_a_transformation_removed_on_a_diagnostic():
    kept = [c for c in COLUMNS if c != "realized_volatility_3m_pct"]
    with pytest.raises(DM.MatrixAssemblyError, match="preserves every transformation"):
        DM.assert_no_feature_removal(kept, "dropping a collinear column")


def test_synthetic_13_a_channel_selected_using_feature_diagnostics():
    for claim in ("fo600 is the preferred channel on condition number",
                  "we select the channel with the better rank",
                  "fo1500 is the primary variant"):
        with pytest.raises(ID.IdentifiabilityError):
            ID.assert_no_channel_selection(claim)


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C10 runner is not present")
def test_synthetic_14_a_target_or_locked_outcome_is_accessed():
    import importlib.util

    spec = importlib.util.spec_from_file_location("c10_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path in ("data/targets/industry_month_targets.parquet",
                 "data/interim/production_stress_month.parquet",
                 "data/predictions/d4_operational_model_predictions.parquet",
                 "data/locked_test/holdout.parquet"):
        with pytest.raises(SystemExit, match="prohibited artifact"):
            module.assert_no_prohibited_artifact([path])
    for claim in ("the feature will predict the stress outcome",
                  "conditioning adds no signal", "this improves accuracy"):
        with pytest.raises(ID.IdentifiabilityError):
            ST.assert_no_performance_claim(claim)


def test_synthetic_15_issue_and_reference_months_violate_lag_two():
    with pytest.raises(DM.MatrixAssemblyError, match="policy lag requires"):
        DM.assert_lag_two("2024-03", "2024-02")
    cells = _cells()
    cells[0]["reference_month"] = "2023-12"
    with pytest.raises(DM.MatrixAssemblyError):
        DM.build_development_matrix(cells, V600, INDUSTRIES, MONTHS)


def test_synthetic_16_a_duplicate_or_missing_matrix_key_is_accepted():
    duplicated = _cells()
    duplicated.append(dict(duplicated[0]))
    with pytest.raises(DM.MatrixAssemblyError, match="duplicate matrix keys"):
        DM.build_development_matrix(duplicated, V600, INDUSTRIES, MONTHS)
    truncated = _cells()[:-1]
    with pytest.raises(DM.MatrixAssemblyError, match="missing matrix keys"):
        DM.build_development_matrix(truncated, V600, INDUSTRIES, MONTHS)


def test_synthetic_17_lineage_omits_either_branch():
    source = _source_branch()
    del source["c7_5_semantic_checksum"]
    with pytest.raises(ML.MatrixLineageError, match="C8 source branch is missing"):
        ML.matrix_cell_lineage_record(
            _lineage_cell(), source, _structural_branch(), "rule", "digest"
        )
    structural = _structural_branch()
    del structural["gross_output_weights"]
    with pytest.raises(ML.MatrixLineageError, match="structural branch is missing"):
        ML.matrix_cell_lineage_record(
            _lineage_cell(), _source_branch(), structural, "rule", "digest"
        )


def test_synthetic_18_a_structural_interaction_described_as_a_cost_or_effect():
    for claim in ("the conditioned value is the baht cost per unit of output",
                  "this is the elasticity of output to the fuel price",
                  "the coefficient measures pass-through rate",
                  "a causal effect of the fuel-oil price",
                  "the forecast coefficient on fuel oil"):
        with pytest.raises(C9.ConditioningError):
            C9.assert_valuation_claim_permitted(claim)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_the_assembly_is_deterministic():
    first, second = _matrix(), _matrix()
    assert first.rows == second.rows
    assert first.mask_cells == second.mask_cells
    assert ID.fingerprint(first.source_time_matrix(FAKE_EXPOSURES)) == (
        ID.fingerprint(second.source_time_matrix(FAKE_EXPOSURES))
    )


def test_the_singular_values_are_finite_and_ordered():
    values = ID.singular_values(BASE)
    assert all(math.isfinite(v) for v in values)
    assert values == sorted(values, reverse=True)
