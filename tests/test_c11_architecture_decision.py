"""Task C11 tests — outcome-free fuel-oil modeling-architecture decision.

Three failures here would produce a decision that looks entirely reasonable.

The first is **choosing a reparameterisation**. Within one industry the
sector-093 exposure is a positive scalar, so fitting ``E_g x_t`` per industry
spans exactly the same column space as fitting ``x_t`` per industry. No data can
distinguish them; only the printed coefficients differ. Presenting that as a
second architecture is a claim about coordinates dressed up as a claim about
designs, and the column-space projector is compared here rather than argued.

The second is **an interaction that identifies nothing**. Three constructions
destroy the exposure-associated heterogeneity while leaving a design that still
fits: standardising the interaction inside each industry (which reduces it to
the *sign* of the exposure), replacing exposure with a constant (which makes the
block identically zero), and adding a global intercept to a full set of industry
indicators (which is rank-deficient by exactly one while reporting twenty-two
columns). All three are built and required to fail.

The third is **a selection that becomes a permit**. C11 chooses a design and
authorizes nothing; the authorization guard raises if a selection sets
target-join, modeling or locked-test permission.

Everything in this module is outcome-free: no target, no prediction, no metric,
no locked test, no fitted coefficient.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.features import fuel_oil_industry_conditioning as C9M
from thai_supply_chain_ews.structure import fuel_oil_architecture_decision as AD
from thai_supply_chain_ews.structure import fuel_oil_candidate_designs as CD
from thai_supply_chain_ews.structure import fuel_oil_proxy_fitness as PF
from thai_supply_chain_ews.structure import sector093_exposure as EX

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "fuel_oil_modeling_architecture.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
SCHEMA_PATH = ROOT / "schemas" / "fuel_oil_candidate_design.schema.yaml"
DECISION = ROOT / "docs" / "c11_architecture_decision.json"
PROTOCOL = ROOT / "docs" / "c11_architecture_decision_protocol.md"
DECISION_MD = ROOT / "docs" / "c11_architecture_decision.md"
RUNNER = ROOT / "scripts" / "run_c11_architecture_decision.py"
DESIGN_PARQUET = ROOT / "data" / "features" / "c11_fuel_oil_candidate_c_design.parquet"
BLOCKS_PARQUET = ROOT / "data" / "features" / "c11_fuel_oil_candidate_blocks.parquet"
C10_AUDIT = ROOT / "docs" / "c10_design_matrix_audit.json"

V600, V1500 = "fo600_direct_sector093", "fo1500_direct_sector093"

requires_run = pytest.mark.skipif(
    not DECISION.is_file(), reason="C11 has not been run"
)


def _decision():
    return json.loads(DECISION.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Synthetic fixtures. Small and hand-built, so a failure is a failure of the
# guard rather than of the real data.
# ---------------------------------------------------------------------------
MONTHS = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
ELIGIBLE = ["IND-01", "IND-02", "IND-03"]
RAW_SOURCE = [
    [1.0, 2.0, 3.0, 40.0, 5.0],
    [1.5, 2.5, 3.5, 41.0, 5.5],
    [2.0, 1.0, 4.0, 42.0, 6.5],
    [0.5, 3.0, 2.5, 43.5, 4.5],
    [3.0, 0.5, 5.0, 44.5, 7.5],
    [2.5, 1.5, 1.5, 45.0, 3.5],
]
EXPOSURES = {"IND-01": 0.010, "IND-02": 0.040, "IND-03": 0.007, "IND-04": 0.0098}


def _standardized():
    return CD.standardize_source_block(RAW_SOURCE, 0)["matrix"]


def _centered(exposures=None, eligible=None):
    return CD.center_exposures(exposures or EXPOSURES, eligible or ELIGIBLE)


def _design(coding=CD.VALID_FIXED_EFFECT_CODING, **kwargs):
    return CD.build_candidate_c_design(
        kwargs.pop("standardized", None) or _standardized(),
        kwargs.pop("centered", None) or _centered(),
        MONTHS, ELIGIBLE, kwargs.pop("variant_id", V600), coding=coding, **kwargs
    )


def _criteria(**overrides):
    spec = CONFIG["decision_rule"]
    estimand = CONFIG["estimand"]
    pre = CONFIG["preprocessing"]
    ident = CONFIG["identification"]
    fields = {
        "criteria_version": CONFIG["criteria_version"],
        "estimand_statement": estimand["statement"],
        "estimand_kind": estimand["kind"],
        "estimand_requires_exposure_heterogeneity": estimand[
            "requires_exposure_associated_heterogeneity"],
        "causal_effect_claimed": estimand["causal_effect"],
        "estimated_elasticity_claimed": estimand["estimated_elasticity"],
        "monetary_cost_claimed": estimand["monetary_cost_per_unit_of_output"],
        "candidate_ids": sorted(CONFIG["candidates"]),
        "mandatory_gates": list(spec["mandatory_gates"]),
        "all_gates_must_pass": spec["all_gates_must_pass"],
        "decision_ordering": list(spec["ordering"]),
        "tie_handling": spec["tie_handling"],
        "expected_selection": spec["expected_selection"],
        "expectation_overrides_a_failed_gate": spec[
            "expectation_overrides_a_failed_gate"],
        "exposure_centering_rule": pre["exposure_centering"]["rule"],
        "exposure_centering_universe": pre["exposure_centering"]["universe"],
        "source_scaling_rule": pre["source_feature_scaling"]["rule"],
        "source_scaling_ddof": int(pre["source_feature_scaling"]["ddof"]),
        "permitted_training_issue_months": [
            str(m) for m in
            pre["source_feature_scaling"]["permitted_training_issue_months"]
        ],
        "interaction_per_industry_standardization": pre["interaction"][
            "per_industry_standardization_applied_to_the_interaction"],
        "industry_fixed_effect_coding": pre["industry_fixed_effects"]["coding"],
        "redundant_global_intercept": pre["industry_fixed_effects"][
            "redundant_global_intercept"],
        "rank_tolerance": float(ident["rank_tolerance"]),
        "duplicate_column_tolerance": float(ident["duplicate_column_tolerance"]),
        "expected_source_block_rank": ident["expected_source_block_rank"],
        "expected_interaction_block_rank": ident["expected_interaction_block_rank"],
        "expected_combined_source_and_interaction_rank": ident[
            "expected_combined_source_and_interaction_rank"],
        "expected_full_design_rank": ident["expected_full_design_rank"],
        "expected_panel_rows": ident["panel_rows"],
        "expected_unique_issue_months": ident["unique_issue_months"],
        "expected_eligible_industries": ident["eligible_industries"],
        "equivalence_rule": CONFIG["c10_fingerprint_discrepancy"][
            "equivalence_rule_used_for_the_decision"],
        "rounded_fingerprint_count_used_for_the_decision": CONFIG[
            "c10_fingerprint_discrepancy"][
            "rounded_fingerprint_count_used_for_the_decision"],
        "channel_selection_permitted": CONFIG["channels"]["primary_channel_selected"],
        "transformation_removal_permitted": CONFIG["transformations"][
            "outcome_based_removal_permitted"],
        "target_or_outcome_access_permitted": False,
        "prohibited_artifacts": list(CONFIG["prohibited_inputs"]["artifacts"]),
        "prohibited_statistics": list(CONFIG["prohibited_inputs"]["statistics"]),
    }
    fields.update(overrides)
    return AD.DecisionCriteria(**fields)


def _lineage_references(**overrides):
    references = {field: f"value-{field}" for field in AD.LINEAGE_FIELDS}
    references.update(overrides)
    return references


# ---------------------------------------------------------------------------
# Configuration, schema and the frozen criteria
# ---------------------------------------------------------------------------
def test_the_config_parses_and_freezes_its_criteria():
    ident = CONFIG["identification"]
    assert float(ident["rank_tolerance"]) == 1e-10
    assert ident["expected_source_block_rank"] == 5
    assert ident["expected_interaction_block_rank"] == 5
    assert ident["expected_combined_source_and_interaction_rank"] == 10
    assert ident["expected_full_design_rank"] == 21
    assert CONFIG["decision_rule"]["expectation_overrides_a_failed_gate"] is False


def test_the_schema_parses_and_forbids_outcome_columns():
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    prohibited = set(schema["prohibited_columns"]["columns"])
    assert {"y_true", "prediction", "residual", "mae", "coefficient"} <= prohibited
    assert schema["information_accounting"][
        "panel_rows_are_independent_temporal_observations"] is False


def test_the_criteria_checksum_is_stable():
    first, second = AD.criteria_checksum(_criteria()), AD.criteria_checksum(_criteria())
    assert first == second
    assert AD.assert_criteria_frozen(_criteria(), first) == first


def test_the_estimand_is_predictive_and_non_causal():
    estimand = CONFIG["estimand"]
    assert estimand["kind"] == "predictive_interaction"
    for field in ("causal_effect", "estimated_elasticity",
                  "monetary_cost_per_unit_of_output", "point_in_time_backtest",
                  "fuel_oil_determines_industrial_stress"):
        assert estimand[field] is False, field
    assert estimand["sector_093_exposure_is_a_structural_proxy"] is True
    assert estimand["requires_exposure_associated_heterogeneity"] is True
    assert "purchasers_price" in estimand["valuation_basis_alignment"]
    assert estimand["io_coefficient_basis"] == "purchasers_price_import_inclusive"
    assert estimand["eppo_price_stage"] == "ex_refinery"


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------
def test_source_scaling_is_fitted_before_replication_across_industries():
    scaling = CD.standardize_source_block(RAW_SOURCE, 0)
    assert scaling["training_rows"] == len(RAW_SOURCE)
    assert scaling["fitted_on_targets_or_folds"] is False
    for column in zip(*scaling["matrix"], strict=True):
        assert abs(sum(column) / len(column)) < 1e-12
        assert abs(math.sqrt(sum(v * v for v in column) / len(column)) - 1) < 1e-12


def test_exposure_centering_uses_the_frozen_eleven_industry_universe():
    centered = _centered()
    assert abs(sum(centered.values())) < 1e-15
    assert set(centered) == set(ELIGIBLE)
    assert "IND-04" not in centered


def test_the_interaction_is_built_after_standardization_and_not_rescaled():
    design = _design()
    standardized = _standardized()
    centered = _centered()
    for (month, industry), row in zip(design.row_keys, design.matrix, strict=True):
        index = MONTHS.index(month)
        for position, column in enumerate(CD.SOURCE_COLUMNS):
            source = row[design.blocks["source"][position]]
            interaction = row[design.blocks["interaction"][position]]
            assert source == pytest.approx(standardized[index][position])
            assert interaction == pytest.approx(centered[industry] * source)
            assert column in design.columns[design.blocks["source"][position]]


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------
def test_the_pooled_design_is_identifiable_block_by_block():
    design = _design()
    ranks = CD.block_ranks(design)
    assert ranks["source_block_rank"] == 5
    assert ranks["interaction_block_rank"] == 5
    assert ranks["combined_source_and_interaction_rank"] == 10
    assert ranks["full_design_rank"] == len(design.columns)
    assert CD.duplicate_columns(design.matrix, design.columns) == []


def test_the_panel_has_one_row_per_industry_month():
    design = _design()
    assert len(design.matrix) == len(ELIGIBLE) * len(MONTHS)
    assert len(set(design.row_keys)) == len(design.row_keys)
    assert len(design.columns) == 10 + len(ELIGIBLE)


def test_a_valid_reference_coding_is_also_full_rank():
    design = _design(coding="reference_industry_dummies_plus_global_intercept")
    ranks = CD.block_ranks(design)
    assert ranks["full_design_rank"] == len(design.columns)
    CD.assert_valid_fixed_effect_coding(
        design.fixed_effect_coding, len(design.columns), ranks["full_design_rank"]
    )


def test_candidate_b_spans_candidate_a():
    standardized = _standardized()
    candidate_a = CD.build_candidate_a_design(
        standardized, MONTHS, "IND-01", V600
    )
    candidate_b = CD.build_candidate_b_design(
        standardized, MONTHS, "IND-01", EXPOSURES["IND-01"], V600
    )
    report = CD.candidate_b_equivalence_report(
        candidate_a, candidate_b, EXPOSURES["IND-01"]
    )
    assert report["column_spaces_coincide"] is True
    assert report["is_exact_column_rescaling"] is True
    assert report["per_industry_standardization_removes_exposure"] is True
    assert report["separate_conditioned_model_is_distinct_architecture"] is False


def test_per_industry_standardization_keeps_only_the_sign_of_the_exposure():
    design = _design()
    collapse = CD.per_industry_standardised_collapse(design)
    assert collapse["intended_combined_rank"] == 10
    assert collapse["per_industry_combined_ranks"] == [5]
    assert collapse["distinct_intended_interaction_blocks"] == len(ELIGIBLE)
    assert collapse["distinct_collapsed_interaction_blocks"] < len(ELIGIBLE)
    assert collapse["sign_identity_residual"] < 1e-12
    assert collapse["heterogeneity_collapses"] is True


def test_a_constant_exposure_makes_the_interaction_identically_zero():
    design = _design()
    report = CD.constant_exposure_interaction_report(
        design, _standardized(), MONTHS
    )
    assert report["constant_exposure_interaction_rank"] == 0
    assert report["all_zero"] is True
    assert report["identifies_heterogeneity"] is False


def test_the_design_checksum_is_deterministic_and_shape_sensitive():
    first, second = CD.design_checksum(_design()), CD.design_checksum(_design())
    assert first == second
    other = CD.design_checksum(
        _design(coding="reference_industry_dummies_plus_global_intercept")
    )
    assert other != first


# ---------------------------------------------------------------------------
# Lineage and decision mechanics
# ---------------------------------------------------------------------------
def test_lineage_requires_every_reference():
    record = AD.architecture_lineage_record(
        _lineage_references(), "criteria-digest", {V600: "design-digest"}
    )
    for field in AD.LINEAGE_FIELDS:
        assert field in record["references"]
    assert len(AD.architecture_lineage_checksum(record)) == 64


def test_the_decision_checksum_changes_with_the_selection():
    gates = dict.fromkeys(AD.MANDATORY_GATES, True)
    passed = AD.select_architecture(gates, _criteria())
    failed_gates = {**gates, "exposure_varies_across_eligible_industries": False}
    failed = AD.select_architecture(failed_gates, _criteria())
    assert passed["selected_architecture"] == AD.SELECTED_ARCHITECTURE_ID
    assert failed["selected_architecture"] is None
    assert failed["blocker"] == "exposure_varies_across_eligible_industries"
    assert AD.decision_checksum(passed, gates, "lin") != AD.decision_checksum(
        failed, failed_gates, "lin"
    )


def test_a_failed_gate_selects_nothing_even_though_c_is_expected():
    criteria = _criteria()
    assert criteria.expected_selection == (
        "pooled_common_effect_plus_centered_sector093_interaction"
    )
    assert criteria.expectation_overrides_a_failed_gate is False
    gates = dict.fromkeys(AD.MANDATORY_GATES, True)
    gates["combined_feature_only_design_is_identifiable"] = False
    result = AD.select_architecture(gates, criteria)
    assert result["selected_architecture"] is None
    assert result["expectation_overridden"] is False


def test_content_checksum_ignores_the_generation_timestamp():
    assert AD.content_checksum({"a": 1, "generated_at_utc": "2026-01-01"}) == (
        AD.content_checksum({"a": 1, "generated_at_utc": "2026-08-30"})
    )


# ---------------------------------------------------------------------------
# Static separation
# ---------------------------------------------------------------------------
def test_c11_modules_import_no_model_evaluation_or_target_code():
    banned = ("targets", "evaluation", "models", "modeling", "backtest")
    for name in ("fuel_oil_candidate_designs", "fuel_oil_architecture_decision"):
        path = ROOT / "src" / "thai_supply_chain_ews" / "structure" / f"{name}.py"
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


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C11 runner is not present")
def test_the_runner_reads_no_target_prediction_or_locked_artifact():
    """No line that opens a file may name a target, prediction or locked path."""
    reads = ("read_parquet", "read_text", "load_json(", "load_yaml(", "open(")
    banned = ("target", "production_stress", "prediction", "residual", "locked",
              "holdout", "d1_development_results", "d3_operational",
              "d4_operational", "walk_forward")
    for line in RUNNER.read_text(encoding="utf-8").splitlines():
        if not any(read in line for read in reads):
            continue
        lowered = line.lower()
        for fragment in banned:
            assert fragment not in lowered, line.strip()


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C11 runner is not present")
def test_the_runner_fits_nothing():
    text = RUNNER.read_text(encoding="utf-8").lower()
    for fragment in ("lstsq", ".fit(", "ridge", "lasso", "regress", "sklearn",
                     "statsmodels", "np.linalg.solve", "pinv"):
        assert fragment not in text, fragment


# ---------------------------------------------------------------------------
# The generated decision
# ---------------------------------------------------------------------------
@requires_run
def test_the_decision_selects_candidate_c_on_all_nine_gates():
    payload = _decision()
    assert payload["selection"]["selected_architecture"] == (
        "pooled_common_effect_plus_centered_sector093_interaction"
    )
    assert payload["selection"]["all_gates_passed"] is True
    assert payload["selection"]["failed_gates"] == []
    assert payload["selection"]["expectation_overridden"] is False
    assert sorted(payload["gates"]) == sorted(AD.MANDATORY_GATES)
    assert all(payload["gates"].values())


@requires_run
def test_the_decision_reports_every_required_authorization_field():
    authorization = _decision()["authorization"]
    assert authorization["modeling_architecture_selected"] == (
        "pooled_common_effect_plus_centered_sector093_interaction"
    )
    assert authorization["predictive_estimand_defined"] is True
    assert authorization["pooled_exposure_interaction_identifiable"] is True
    assert authorization[
        "separate_conditioned_architecture_rejected_as_reparameterization"] is True
    for field in ("architecture_selected_from_outcomes", "primary_channel_selected",
                  "target_values_read", "target_joined", "model_fitted",
                  "predictive_performance_computed", "locked_test_accessed",
                  "model_feature_approved", "target_join_authorized",
                  "development_modeling_authorized",
                  "locked_test_evaluation_authorized"):
        assert authorization[field] is False, field
    AD.assert_authorization_not_granted(authorization)


@requires_run
def test_the_decision_reproduces_the_c10_invariants():
    invariants = _decision()["upstream_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 25
    checks = invariants["checks"]
    assert checks["c10_content_checksum_recomputes"]["reproduced"] is True
    assert checks["c10_source_time_rank"]["actual"] == [5]
    assert checks["c10_cross_sectional_rank"]["actual"] == [1]
    assert checks["c10_eligible_industries"]["actual"] == [11]
    assert checks["c10_masked_industries"]["actual"] == [["IND-04"]]


@requires_run
def test_the_decision_preserves_c10s_fingerprint_discrepancy():
    discrepancy = _decision()["c10_fingerprint_discrepancy"]
    assert discrepancy["rounded_fingerprint_count_fo600"] == 11
    assert discrepancy["absolute_tolerance_equivalence_classes_fo600"] == 1
    assert discrepancy["equivalence_rule_used_for_the_decision"] == (
        "absolute_tolerance_equivalence_class"
    )
    assert discrepancy["rounded_fingerprint_count_used_for_the_decision"] is False
    assert discrepancy["discrepancy_suppressed"] is False
    assert discrepancy["c10_rewritten"] is False
    AD.assert_tolerance_rule_governs(discrepancy)
    c10 = json.loads(C10_AUDIT.read_text(encoding="utf-8"))
    assert c10["per_variant"][V600]["standardization_invariance"][
        "distinct_standardized_fingerprints"] == 11
    assert c10["per_variant"][V600]["standardization_invariance"][
        "standardized_equivalence_classes"] == 1


@requires_run
def test_the_decision_reports_its_own_failed_expectation():
    block = _decision()["preregistered_expectation_discrepancies"]
    assert block["preregistered_values_changed"] is False
    assert block["expectations_relaxed_to_obtain_a_pass"] is False
    assert block["gate_implementation_corrected_after_observation"] is True
    assert block["gate_correction"]["gate"] == (
        "pooled_interaction_survives_the_specified_preprocessing"
    )
    for item in block["items"]:
        assert item["preregistered_value"] != item["observed_value"]
        assert item["preregistered_value_changed"] is False
        corrected = item["corrected_measurement"]
        assert corrected["per_industry_combined_ranks"] == [5]
        assert corrected["distinct_intended_interaction_blocks"] == 11
        assert corrected["distinct_collapsed_interaction_blocks"] == 2


@requires_run
def test_the_identification_audit_matches_the_preregistered_ranks():
    payload = _decision()
    criteria = payload["decision_criteria"]
    for audit in payload["identification"]["observed"].values():
        assert audit["rows"] == criteria["expected_panel_rows"]
        assert audit["columns"] == 21
        assert audit["source_block_rank"] == criteria["expected_source_block_rank"]
        assert audit["interaction_block_rank"] == (
            criteria["expected_interaction_block_rank"]
        )
        assert audit["combined_source_and_interaction_rank"] == (
            criteria["expected_combined_source_and_interaction_rank"]
        )
        assert audit["full_design_rank"] == criteria["expected_full_design_rank"]
        assert audit["full_design_is_full_column_rank"] is True
        assert audit["exact_duplicate_columns"] == []
        assert audit["interaction_columns_removed_by_preprocessing"] == 0
        assert audit["exposure_has_nonzero_cross_industry_variance"] is True
        assert audit["constant_exposure_check"][
            "constant_exposure_interaction_rank"] == 0
        invalid = audit["invalid_fixed_effect_coding"]
        assert invalid["columns"] == 22
        assert invalid["rank"] == 21
        assert invalid["rank_deficient"] is True
        assert invalid["guard_raised"] is True


@requires_run
def test_candidate_b_is_rejected_as_a_reparameterization_for_every_industry():
    for report in _decision()["candidate_b_equivalence"].values():
        assert report["industries_checked"] == 11
        assert report["all_column_spaces_coincide"] is True
        assert report["all_are_exact_column_rescalings"] is True
        assert report["max_column_space_projector_gap"] < 1e-9
        assert report["separate_conditioned_model_is_distinct_architecture"] is False


@requires_run
def test_the_accounting_separates_rows_from_histories():
    accounting = _decision()["accounting"]
    assert accounting["panel_rows"] == 165
    assert accounting["unique_issue_months"] == 15
    assert accounting["observed_issue_month_clusters"] == 15
    assert accounting["source_slopes_per_horizon"] == 5
    assert accounting["interaction_slopes_per_horizon"] == 5
    assert accounting["industry_fixed_effects"] == 11
    assert accounting["redundant_global_intercept"] is False
    assert accounting[
        "cross_sectional_rows_help_identify_exposure_heterogeneity"] is True
    assert accounting["cross_sectional_rows_create_additional_fuel_oil_histories"] \
        is False
    assert accounting["full_rank_is_evidence_of_predictive_usefulness"] is False
    assert accounting["parameter_feasibility_equals_statistical_power"] is False
    for field in ("p_values_computed", "coefficient_uncertainty_computed",
                  "outcome_related_effective_sample_size_computed"):
        assert accounting[field] is False, field


@requires_run
def test_ind_04_is_excluded_without_being_zeroed():
    ind_04 = _decision()["ind_04"]
    assert ind_04["excluded_from_fuel_oil_correction"] is True
    assert ind_04["converted_to_observed_zero"] is False
    assert ind_04["direction_forced_to_plus_one"] is False
    assert ind_04["retains_operational_benchmark_prediction"] is True
    assert ind_04["silently_dropped_from_evaluation_denominators"] is False
    assert ind_04["fuel_oil_residual_correction"] == "structurally_unavailable"
    AD.assert_ind_04_not_converted(ind_04)


@requires_run
def test_the_two_channels_stay_co_equal_and_separate():
    channels = _decision()["channels"]
    assert channels["co_equal_separate_structural_variants"] is True
    assert channels["primary_channel_selected"] is False
    assert channels["structural_basis_for_channel_preference_available"] is False
    assert channels["parallel_exploratory_variants_permitted_in_future_design"] is True
    assert channels["outcome_based_channel_selection_permitted"] is False
    assert channels["simultaneous_channel_entry_permitted"] is False
    assert channels["described_as_independent_structural_channels"] is False
    assert channels["joint_design_refused"] is True
    AD.assert_no_channel_preference(channels)


@requires_run
def test_no_transformation_was_removed():
    transformations = _decision()["transformations"]
    assert sorted(transformations["retained"]) == sorted(CD.SOURCE_COLUMNS)
    assert transformations["removed"] == []
    assert transformations["outcome_based_removal_permitted"] is False
    assert transformations["realized_volatility_interpretation"] == (
        "nonnegative_disruption_magnitude"
    )
    assert transformations["realized_volatility_is_a_price_increase_direction"] is False


@requires_run
def test_the_availability_contract_is_carried_forward():
    availability = _decision()["availability"]
    assert availability["operational_source_lag_months"] == 2
    assert availability["lag_basis"] == "conservative_policy_not_historical_measurement"
    assert availability["source_available_as_of"] is None
    assert availability["latest_vintage_source_values"] is True
    assert availability["point_in_time_source_support"] is False
    assert availability["structural_available_by"].startswith("2020-03")
    assert availability["development_issue_months"] == ["2024-01", "2025-03"]
    assert availability["purge_issue_months"] == ["2025-04", "2025-06"]
    assert availability["purge_or_locked_feature_target_rows_materialised"] is False
    assert availability["intact"] is True


@requires_run
def test_the_criteria_were_frozen_before_and_after_the_designs_were_built():
    payload = _decision()
    assert payload["criteria_frozen_before_candidate_designs_built"] is True
    assert payload["criteria_reasserted_after_identification_audit"] is True
    criteria = AD.DecisionCriteria(**payload["decision_criteria"])
    assert AD.criteria_checksum(criteria) == payload["decision_criteria_checksum"]


@requires_run
def test_the_content_checksum_reproduces_from_the_payload():
    payload = _decision()
    stored = payload.pop("content_checksum")
    assert AD.content_checksum(payload) == stored


@requires_run
def test_no_model_prediction_or_metric_artifact_was_created():
    outputs = _decision()["outputs"]
    assert outputs["model_artifact_created"] is False
    assert outputs["prediction_artifact_created"] is False
    assert outputs["metric_artifact_created"] is False
    assert outputs["target_joined_artifact_created"] is False


@pytest.mark.skipif(not DESIGN_PARQUET.is_file(), reason="the C11 design is absent")
def test_the_generated_design_is_feature_only_and_excludes_ind_04():
    import pandas as pd

    frame = pd.read_parquet(DESIGN_PARQUET)
    assert len(frame) == 330
    assert frame["industry_id"].nunique() == 11
    assert "IND-04" not in set(frame["industry_id"])
    assert frame["variant_id"].nunique() == 2
    banned = ("stress", "target", "y_true", "y_pred", "prediction", "residual",
              "mae", "rmse", "metric", "locked", "coefficient")
    for column in (c.lower() for c in frame.columns):
        assert not any(b in column for b in banned), column
    assert sum(1 for c in frame.columns if c.startswith("src__")) == 5
    assert sum(1 for c in frame.columns if c.startswith("int__")) == 5
    assert sum(1 for c in frame.columns if c.startswith("fe__")) == 11
    # The two variants are separate ROW groups, never a ten-column table.
    for variant_id in (V600, V1500):
        assert len(frame[frame["variant_id"] == variant_id]) == 165


@pytest.mark.skipif(not BLOCKS_PARQUET.is_file(), reason="the block table is absent")
def test_the_block_table_names_every_column_once_per_variant():
    import pandas as pd

    frame = pd.read_parquet(BLOCKS_PARQUET)
    assert len(frame) == 42
    assert set(frame["block"]) == {"source", "interaction", "fixed_effects"}
    for variant_id in (V600, V1500):
        subset = frame[frame["variant_id"] == variant_id]
        assert len(subset) == 21
        assert subset["column"].nunique() == 21


# ===========================================================================
# The eighteen required synthetic failures.
# ===========================================================================
def test_synthetic_1_candidate_b_presented_as_distinct():
    standardized = _standardized()
    report = CD.candidate_b_equivalence_report(
        CD.build_candidate_a_design(standardized, MONTHS, "IND-01", V600),
        CD.build_candidate_b_design(
            standardized, MONTHS, "IND-01", EXPOSURES["IND-01"], V600
        ),
        EXPOSURES["IND-01"],
    )
    with pytest.raises(AD.ArchitectureDecisionError, match="distinct architecture"):
        AD.assert_separate_conditioned_not_distinct(report, claimed_distinct=True)


def test_synthetic_2_exposure_removed_by_per_industry_interaction_scaling():
    collapse = CD.per_industry_standardised_collapse(_design())
    assert collapse["heterogeneity_collapses"] is True
    assert collapse["per_industry_combined_ranks"] == [5]
    assert collapse["distinct_collapsed_interaction_blocks"] < (
        collapse["distinct_intended_interaction_blocks"]
    )
    # The contract must record that this preprocessing is not applied.
    assert CONFIG["preprocessing"]["interaction"][
        "per_industry_standardization_applied_to_the_interaction"] is False
    criteria = _criteria(interaction_per_industry_standardization=True)
    frozen = AD.criteria_checksum(_criteria())
    with pytest.raises(AD.CriteriaError):
        AD.assert_criteria_frozen(criteria, frozen)


def test_synthetic_3_constant_exposure_reported_as_identifying_heterogeneity():
    flat = dict.fromkeys(ELIGIBLE, 0.02)
    centered = CD.center_exposures(flat, ELIGIBLE)
    assert set(centered.values()) == {0.0}
    with pytest.raises(CD.CandidateDesignError, match="cannot identify slope"):
        CD.assert_exposure_varies(centered)
    with pytest.raises(CD.CandidateDesignError, match="identically zero"):
        CD.build_candidate_c_design(
            _standardized(), centered, MONTHS, ELIGIBLE, V600,
        )


def test_synthetic_4_candidate_c_omits_the_common_source_main_effect():
    with pytest.raises(CD.CandidateDesignError, match="common source main effect"):
        CD.assert_main_effect_present(
            {"interaction": [0], "fixed_effects": [1]}, estimand_changed=False
        )
    # Declaring the new estimand is permitted; deleting a block silently is not.
    CD.assert_main_effect_present(
        {"interaction": [0], "fixed_effects": [1]}, estimand_changed=True
    )


def test_synthetic_5_exposure_centering_uses_target_or_outcome_data():
    for source in ("b3_target_values", "development_fold_residuals",
                   "d3_operational_baseline_results"):
        with pytest.raises(CD.CandidateDesignError, match="never from a target"):
            CD.center_exposures(EXPOSURES, ELIGIBLE, source=source)


def test_synthetic_6_sector_031_replaces_sector_093():
    with pytest.raises(EX.ExposureError, match="031"):
        EX.assert_sector_is_093("031")


def test_synthetic_7_ind_04_forced_to_cost_pressure():
    from types import SimpleNamespace

    exposure = SimpleNamespace(
        industry_id="IND-04", industry_contains_the_producer_sector=True
    )
    with pytest.raises(PF.PhaseAError, match="mixed"):
        PF.assert_direction_not_forced(
            exposure,
            {"direction_channel": "cost_pressure", "direction_multiplier": 1},
        )
    with pytest.raises(AD.ArchitectureDecisionError, match="forced to"):
        AD.assert_ind_04_not_converted({
            **CONFIG["ind_04"], "direction_forced_to_plus_one": True,
        })


def test_synthetic_8_ind_04_converted_to_observed_zero():
    with pytest.raises(AD.ArchitectureDecisionError, match="not measured at zero"):
        AD.assert_ind_04_not_converted({
            **CONFIG["ind_04"], "converted_to_observed_zero": True,
        })
    with pytest.raises(C9M.ConditioningError, match="unresolved, not"):
        C9M.assert_null_not_converted_to_zero({
            "variant_id": V600, "industry_id": "IND-04",
            "reference_month": "2023-11", "transformation_id": "price_level",
            "conditioned_status": "not_generated_due_to_direction_ambiguity",
            "conditioned_value": 0.0,
        })


def test_synthetic_9_both_fuel_oils_enter_the_same_design():
    with pytest.raises(CD.CandidateDesignError, match="same sector-093"):
        CD.assert_single_variant_design([V600, V1500], "a joint pooled design")
    with pytest.raises(C9M.ConditioningError):
        C9M.assert_no_fuel_oil_combination([V600, V1500], "a ten-column design")


def test_synthetic_10_a_channel_is_selected_from_diagnostics_or_outcomes():
    with pytest.raises(AD.ArchitectureDecisionError, match="primary fuel-oil channel"):
        AD.assert_no_channel_preference({
            **CONFIG["channels"], "primary_channel_selected": True,
        })
    with pytest.raises(AD.ArchitectureDecisionError, match="no structural basis"):
        AD.assert_no_channel_preference({
            **CONFIG["channels"],
            "structural_basis_for_channel_preference_available": True,
        })
    with pytest.raises(AD.ArchitectureDecisionError, match="outcome statistic"):
        AD.assert_no_outcome_statistic(["development_mae_by_channel"])


def test_synthetic_11_a_transformation_is_removed_on_rank_or_correlation():
    from thai_supply_chain_ews.features import fuel_oil_development_matrix as DM

    kept = [c for c in CD.SOURCE_COLUMNS if c != "realized_volatility_3m_pct"]
    with pytest.raises(DM.MatrixAssemblyError, match="preserves every transformation"):
        DM.assert_no_feature_removal(kept, "dropping a collinear column")
    assert CONFIG["transformations"]["outcome_based_removal_permitted"] is False


def test_synthetic_12_panel_rows_called_independent_temporal_observations():
    from thai_supply_chain_ews.features import fuel_oil_identifiability as ID

    for claim in ("the panel gives 165 independent observations",
                  "165 independent temporal rows",
                  "an effective sample size of 165"):
        with pytest.raises(ID.IdentifiabilityError):
            ID.assert_no_independence_claim(claim)


def test_synthetic_13_an_invalid_fixed_effect_encoding_is_rank_deficient():
    design = _design(coding="global_intercept_plus_industry_indicators")
    rank = CD.numerical_rank(design.matrix)
    assert len(design.columns) == 10 + len(ELIGIBLE) + 1
    assert rank == len(design.columns) - 1
    with pytest.raises(CD.CandidateDesignError, match="rank-deficient"):
        CD.assert_valid_fixed_effect_coding(
            design.fixed_effect_coding, len(design.columns), rank
        )


def test_synthetic_14_the_interaction_described_causally_or_as_a_cost():
    for claim in ("theta is the causal effect of the fuel-oil price",
                  "the interaction measures the elasticity of output",
                  "this is the pass-through rate to industrial stress",
                  "the coefficient is the monetary cost of fuel oil"):
        with pytest.raises(AD.ArchitectureDecisionError):
            AD.assert_predictive_not_causal(claim)
    with pytest.raises(C9M.ConditioningError):
        C9M.assert_valuation_claim_permitted(
            "the conditioned value is the baht cost per unit of output"
        )


def test_synthetic_15_a_target_prediction_or_locked_artifact_is_accessed():
    for path in ("data/targets/industry_month_targets.parquet",
                 "data/interim/production_stress_month.parquet",
                 "data/predictions/d4_operational_model_predictions.parquet",
                 "docs/d3_operational_baseline_results.json",
                 "data/locked_test/holdout.parquet"):
        with pytest.raises(AD.ArchitectureDecisionError, match="prohibited artifact"):
            AD.assert_no_prohibited_artifact([path])
    for statistic in ("macro_industry_mae", "rmse_by_horizon",
                      "high_stress_outcome_rate", "coefficient_estimate",
                      "p_value_for_theta"):
        with pytest.raises(AD.ArchitectureDecisionError, match="outcome statistic"):
            AD.assert_no_outcome_statistic([statistic])


def test_synthetic_16_criteria_change_after_candidate_matrices_are_built():
    frozen = AD.criteria_checksum(_criteria())
    for changed in (
        _criteria(rank_tolerance=1e-6),
        _criteria(expected_combined_source_and_interaction_rank=5),
        _criteria(mandatory_gates=list(AD.MANDATORY_GATES[:4])),
        _criteria(expectation_overrides_a_failed_gate=True),
        _criteria(industry_fixed_effect_coding="global_intercept_plus_industry_indicators"),
    ):
        with pytest.raises(AD.CriteriaError, match="may not change"):
            AD.assert_criteria_frozen(changed, frozen)


def test_synthetic_17_c10s_rounding_discrepancy_hidden_or_used_as_the_rule():
    base = dict(CONFIG["c10_fingerprint_discrepancy"])
    with pytest.raises(AD.ArchitectureDecisionError, match="suppressed"):
        AD.assert_tolerance_rule_governs({**base, "discrepancy_suppressed": True})
    with pytest.raises(AD.ArchitectureDecisionError, match="rewritten"):
        AD.assert_tolerance_rule_governs({**base, "c10_rewritten": True})
    with pytest.raises(AD.ArchitectureDecisionError, match="ABSOLUTE tolerance"):
        AD.assert_tolerance_rule_governs({
            **base, "rounded_fingerprint_count_used_for_the_decision": True,
        })
    with pytest.raises(AD.ArchitectureDecisionError, match="incomplete"):
        AD.assert_tolerance_rule_governs({
            k: v for k, v in base.items() if k != "rounded_fingerprint_count_fo600"
        })


def test_synthetic_18_selection_silently_grants_modeling_authorization():
    base = dict(CONFIG["authorization"])
    base["modeling_architecture_selected"] = AD.SELECTED_ARCHITECTURE_ID
    AD.assert_authorization_not_granted(base)
    for field in ("target_join_authorized", "development_modeling_authorized",
                  "locked_test_evaluation_authorized", "model_fitted",
                  "target_joined", "model_feature_approved",
                  "predictive_performance_computed", "locked_test_accessed",
                  "primary_channel_selected",
                  "architecture_selected_from_outcomes"):
        with pytest.raises(AD.AuthorizationError, match="grants no permission"):
            AD.assert_authorization_not_granted({**base, field: True})


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_the_candidate_design_is_deterministic():
    first, second = _design(), _design()
    assert first.matrix == second.matrix
    assert first.row_keys == second.row_keys
    assert first.columns == second.columns
    assert CD.design_checksum(first) == CD.design_checksum(second)
