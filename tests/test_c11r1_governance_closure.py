"""Task C11-R1 tests — specification-correction and outcome-access governance.

Three failures here would produce a record that reads as clean when it is not.

The first is **a corrected gate described as a preregistered one**. C11's
original gate expected the stacked rank to fall from ten to five under a
prohibited preprocessing. It does not, because the centred exposures carry both
signs. The gate was measuring the wrong quantity and was corrected *after* the
result was visible; the guards raise on any wording that turns that into
preregistration, or into a tolerance change — no tolerance moved.

The second is **a dependency argument used to launder a history**. The decision
reproduces without any D-series file. That is a fact about value flow. It is not
a fact about what was opened during C11, and no umbrella ``outcome_free: true``
may merge them. A guard added afterwards prevents recurrence and reaches
backwards not at all.

The third is **an authorization that outruns its closure**. D5 is granted only
if every closure gate passes, and a failed dependency reconstruction voids the
whole grant rather than trimming it.

Everything in this module is outcome-free in the only sense available to it: it
opens no target, prediction, metric or locked artifact, and it never reopens the
D3 result file whose access it documents.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.release import byte_provenance as BP
from thai_supply_chain_ews.structure import fuel_oil_architecture_decision as AD
from thai_supply_chain_ews.structure import fuel_oil_architecture_governance as GV
from thai_supply_chain_ews.structure import fuel_oil_candidate_designs as CD
from thai_supply_chain_ews.structure import fuel_oil_information_flow as IF

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "fuel_oil_architecture_governance.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
SCHEMA_PATH = ROOT / "schemas" / "fuel_oil_governance_decision.schema.yaml"
GOVERNANCE = ROOT / "docs" / "c11r1_governance_decision.json"
GOVERNANCE_MD = ROOT / "docs" / "c11r1_governance_decision.md"
ERRATUM = ROOT / "docs" / "c11_architecture_decision.errata.md"
RUNNER = ROOT / "scripts" / "run_c11r1_governance_closure.py"
C11_DECISION = ROOT / "docs" / "c11_architecture_decision.json"
C11_DECISION_MD = ROOT / "docs" / "c11_architecture_decision.md"
C11_PROTOCOL_MD = ROOT / "docs" / "c11_architecture_decision_protocol.md"
C11_CONFIG = ROOT / "configs" / "fuel_oil_modeling_architecture.yaml"
DECISION_LOG = ROOT / "docs" / "architecture" / "decision_log.md"

V600, V1500 = "fo600_direct_sector093", "fo1500_direct_sector093"

requires_run = pytest.mark.skipif(
    not GOVERNANCE.is_file(), reason="C11-R1 has not been run"
)


def _governance():
    return json.loads(GOVERNANCE.read_text(encoding="utf-8"))


def _c11():
    return json.loads(C11_DECISION.read_text(encoding="utf-8"))


def _gate_status(**overrides):
    status = {
        **CONFIG["corrected_gate_specification"]["status"],
        "original_preregistered_stacked_rank_expectation":
            CONFIG["corrected_gate_specification"]["original"][
                "original_preregistered_stacked_rank_expectation"],
        "observed_stacked_rank_under_prohibited_preprocessing":
            CONFIG["corrected_gate_specification"]["observed"][
                "observed_stacked_rank_under_prohibited_preprocessing"],
        "original_gate_implementation_valid":
            CONFIG["corrected_gate_specification"]["original"][
                "original_gate_implementation_valid"],
        "original_preregistered_gate_set_passed":
            CONFIG["corrected_gate_specification"]["original"][
                "original_preregistered_gate_set_passed"],
        "corrected_gate_set_passed":
            CONFIG["corrected_gate_specification"]["corrected_gate_set_passed"],
    }
    status.update(overrides)
    return status


def _incident(**overrides):
    status = dict(CONFIG["outcome_access_incident"]["status"])
    status.update(overrides)
    return status


def _correction(**overrides):
    spec = CONFIG["corrected_gate_specification"]
    fields = {
        "correction_version": CONFIG["correction_version"],
        "gate": spec["gate"],
        "original_preregistered_expectation":
            spec["original"]["preregistered_expectation"],
        "original_preregistered_stacked_rank_expectation":
            spec["original"]["original_preregistered_stacked_rank_expectation"],
        "original_gate_condition":
            spec["original"]["gate_condition_as_originally_implemented"],
        "original_gate_implementation_valid":
            spec["original"]["original_gate_implementation_valid"],
        "original_preregistered_gate_set_passed":
            spec["original"]["original_preregistered_gate_set_passed"],
        "observed_stacked_rank_under_prohibited_preprocessing":
            spec["observed"]["observed_stacked_rank_under_prohibited_preprocessing"],
        "centered_exposures_contain_both_signs":
            spec["observed"]["centered_exposures_contain_both_signs"],
        "correct_measurements": dict(spec["correct_measurements"]),
        "corrected_gate_condition": spec["corrected_gate_condition"],
        "corrected_gate_set_passed": spec["corrected_gate_set_passed"],
        "gate_implementation_corrected_after_observation":
            spec["status"]["gate_implementation_corrected_after_observation"],
        "thresholds_changed_after_observation":
            spec["status"]["thresholds_changed_after_observation"],
        "numerical_tolerance_changed": spec["status"]["numerical_tolerance_changed"],
        "expectations_rewritten_as_preregistered":
            spec["status"]["expectations_rewritten_as_preregistered"],
        "architecture_decision_cleanly_preregistered":
            spec["status"]["architecture_decision_cleanly_preregistered"],
        "incorrect_question":
            spec["why_the_correction_is_justified"]["incorrect_question"],
        "correct_question":
            spec["why_the_correction_is_justified"]["correct_question"],
        "conclusion": spec["why_the_correction_is_justified"]["conclusion"],
    }
    fields.update(overrides)
    return GV.CorrectedGateSpecification(**fields)


def _closure_gates(**overrides):
    gates = dict.fromkeys(GV.CLOSURE_GATES, True)
    gates.update(overrides)
    return gates


# ---------------------------------------------------------------------------
# Configuration and schema
# ---------------------------------------------------------------------------
def test_the_config_parses_and_states_both_facts_separately():
    incident = CONFIG["outcome_access_incident"]["status"]
    assert incident["development_metric_artifact_accessed"] is True
    assert incident["outcome_free_execution"] is False
    assert incident["decision_reproducible_without_metric_artifact"] is True
    assert CONFIG["information_flow"]["conclusion_permitted"] == (
        "architecture_decision_dependency_clean"
    )
    assert CONFIG["information_flow"]["conclusion_does_not_prove"] == (
        "original_execution_was_outcome_blind"
    )


def test_the_schema_parses_and_forbids_the_merging_fields():
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    prohibited = set(schema["prohibited_fields"]["fields"])
    assert {"outcome_free", "original_gates_passed", "process_was_clean",
            "retroactively_compliant"} <= prohibited
    assert schema["sections"]["information_flow"]["must_state_its_limit"] is True


def test_the_correction_checksum_is_stable():
    first, second = (GV.correction_checksum(_correction()),
                     GV.correction_checksum(_correction()))
    assert first == second
    assert GV.assert_correction_frozen(_correction(), first) == first


def test_c11r1_supersedes_the_status_not_the_findings():
    assert CONFIG["supersedes_status_of"] == "C11"
    assert CONFIG["supersedes_findings_of"] == "none"
    assert CONFIG["original_artifacts_modified"] is False
    assert CONFIG["existing_decision_log_entries_modified"] is False


# ---------------------------------------------------------------------------
# The information-flow instruments
# ---------------------------------------------------------------------------
def test_the_path_guard_is_an_allowlist_not_a_denylist():
    permitted = CONFIG["information_flow"]["permitted_inputs"]
    assert IF.assert_permitted_input(
        "docs/c10_design_matrix_audit.json", permitted
    ).endswith("c10_design_matrix_audit.json")
    # A brand-new artifact that matches no forbidden pattern is still refused.
    with pytest.raises(IF.InformationFlowError, match="allowlist"):
        IF.assert_permitted_input("docs/some_future_audit.json", permitted)


def test_static_inspection_reads_call_sites_not_prohibition_lists():
    source = (
        "FORBIDDEN = ('docs/d3_operational_baseline_results.json',)\n"
        "SAFE = Path('docs/c10_design_matrix_audit.json')\n"
        "def go():\n"
        "    return load_json(SAFE)\n"
    )
    targets = IF.read_call_targets(source)
    assert len(targets) == 1
    assert "c10_design_matrix_audit" in targets[0]["resolved"]
    assert IF.forbidden_fragments_in(targets[0]["resolved"]) == []


def test_static_inspection_catches_a_forbidden_read(tmp_path):
    offender = tmp_path / "offender.py"
    offender.write_text(
        "from pathlib import Path\n"
        "RESULTS = Path('docs/d3_operational_baseline_results.json')\n"
        "def go():\n"
        "    return load_json(RESULTS)\n",
        encoding="utf-8",
    )
    report = IF.static_dependency_report([offender])
    assert report["no_forbidden_read_call"] is False
    assert report["offending_read_calls"][0]["forbidden_fragments"]


def test_unresolved_read_arguments_are_reported_not_swallowed(tmp_path):
    helper = tmp_path / "helper.py"
    helper.write_text(
        "def load_json(path):\n"
        "    return open(path)\n",
        encoding="utf-8",
    )
    report = IF.static_dependency_report([helper])
    assert report["unresolved_read_call_count"] == 1
    assert report["no_forbidden_read_call"] is True
    assert "call sites" in report["unresolved_note"]


def test_metric_substitution_leaves_the_architecture_untouched():
    def reconstruct(inputs):
        return inputs.get("architecture")

    result = IF.metric_substitution_invariance(
        reconstruct, {"architecture": AD.SELECTED_ARCHITECTURE_ID},
        {"macro_industry_mae": 999.0, "rmse": -3.0},
    )
    assert result["invariant"] is True
    assert result["fabricated_values_written_to_disk"] is False
    assert result["baseline_architecture"] == AD.SELECTED_ARCHITECTURE_ID


def test_the_dependency_conclusion_must_state_its_limit():
    report = {"architecture_decision_dependency_clean": True,
              "original_execution_outcome_blind": False, "does_not_prove": ""}
    with pytest.raises(IF.InformationFlowError, match="without stating its limit"):
        IF.assert_dependency_conclusion_bounded(report)


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------
@requires_run
def test_the_c11_record_is_preserved_byte_for_byte():
    """The C11 record is unchanged -- as content, on any platform.

    Three of these four pins were taken from a Windows working tree, where the
    file was CRLF on disk while Git stored LF. On a Linux checkout the text is
    identical and the bytes are not, so hashing the working tree would report
    the record as edited when nothing had been edited. Only one of the three was
    ever visible: this loop stops at the first mismatch, so CI reported the
    decision JSON and never reached the two files after it.

    The pins themselves are untouched. Where the recorded bytes do not match,
    ``configs/line_ending_provenance.yaml`` must already declare that path, its
    canonical content must agree, and re-rendering that content in the declared
    representation must reproduce the original pin exactly. A real edit fails
    every one of those.
    """
    payload = _governance()["preserved_c11_record"]
    assert payload["durable_checksums_unchanged"] is True
    assert payload["artifacts_edited"] == []
    provenance = BP.provenance_entries(ROOT)
    for name, path in (("decision_json", C11_DECISION),
                       ("decision_markdown", C11_DECISION_MD),
                       ("protocol_markdown", C11_PROTOCOL_MD),
                       ("frozen_criteria", C11_CONFIG)):
        pinned = payload["artifacts"][name]["byte_sha256"]
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() == pinned:
            continue
        relative = path.relative_to(ROOT).as_posix()
        matched = BP.match_declared_representation(
            content, pinned, provenance.get(relative)
        )
        assert matched is not None, (
            f"{name} ({relative}) does not match its pinned digest, and no "
            "declared line-ending provenance explains it. That is a content "
            "change to a preserved record"
        )
        assert BP.canonical_digest(content) == provenance[relative][
            "canonical_git_blob_content_sha256"], name


@requires_run
def test_the_c11_disclosures_are_still_present_in_c11():
    c11 = _c11()
    block = c11["preregistered_expectation_discrepancies"]
    assert block["gate_implementation_corrected_after_observation"] is True
    assert block["items"], "the original observed gate result must remain in C11"
    assert block["items"][0]["preregistered_value"] == 5
    assert block["items"][0]["observed_value"] == 10


def test_prior_decision_log_entries_are_untouched():
    text = DECISION_LOG.read_text(encoding="utf-8")
    for entry in ("AD-R134", "AD-R135", "AD-R136", "AD-R137", "AD-R138"):
        assert text.count(f"| {entry} |") == 1, entry
    assert "AD-R139" in text, "C11-R1 must append rather than edit"


# ---------------------------------------------------------------------------
# The generated governance record
# ---------------------------------------------------------------------------
@requires_run
def test_every_closure_gate_passed_and_d5_is_bounded():
    payload = _governance()
    assert sorted(payload["closure_gates"]) == sorted(GV.CLOSURE_GATES)
    assert all(payload["closure_gates"].values())
    assert payload["all_closure_gates_passed"] is True
    granted = payload["d5_authorization"]["granted"]
    for field, expected in GV.D5_AUTHORIZATION_FIELDS.items():
        assert granted[field] is expected, field
    GV.assert_d5_authorization_bounded(granted)


@requires_run
def test_the_gate_status_keeps_the_two_sets_apart():
    status = _governance()["gate_status"]
    for field, expected in GV.REQUIRED_GATE_STATUS_FIELDS.items():
        assert status[field] == expected, field
    GV.assert_original_gate_set_not_reported_as_passing(status)
    GV.assert_correction_not_presented_as_preregistered(status)


@requires_run
def test_the_incident_is_recorded_in_both_directions():
    incident = _governance()["outcome_access_incident"]
    status = incident["status"]
    for field, expected in GV.REQUIRED_INCIDENT_STATUS_FIELDS.items():
        assert status[field] is expected, field
    GV.assert_incident_recorded(status)
    GV.assert_guard_does_not_erase_history(status)
    # Every D-series document opened is listed, not only the metric one.
    assert incident["files_opened_count"] == len(incident["files_opened"])
    assert incident["files_opened_count"] >= 1
    assert incident["files_with_metric_values_displayed"] == sum(
        1 for f in incident["files_opened"] if f.get("metric_values_displayed")
    )
    assert any("d3_operational_baseline_results" in f["path"]
               for f in incident["files_opened"])
    assert status["locked_test_outcomes_accessed"] is False


@requires_run
def test_the_correct_measurements_are_present_and_show_the_collapse():
    measurements = _governance()["corrected_gate_specification"][
        "correct_measurements"]
    GV.assert_correct_measurements_present(measurements)
    assert measurements["within_industry_combined_rank"] == 5
    assert measurements["intended_combined_rank"] == 10
    assert measurements["interaction_blocks_intended"] == 11
    assert measurements["interaction_blocks_after_prohibited_preprocessing"] == 2
    assert measurements["sign_equivalence_groups"] == 2
    assert measurements["sign_identity_residual_approx"] < 1e-12
    assert measurements["selected_preprocessing_retains_interaction_rank"] is True


@requires_run
def test_the_architecture_reproduced_without_any_d_series_path():
    payload = _governance()
    reproduction = payload["reproduction"]
    assert reproduction["all_reproduced"] is True
    assert reproduction["failed"] == []
    assert reproduction["d_series_paths_opened"] == 0
    assert reproduction["architecture"] == reproduction["expected_architecture"]
    assert reproduction["c11_selection_agrees"] is True
    for entry in reproduction["per_variant"].values():
        assert entry["source_block_rank"] == 5
        assert entry["interaction_block_rank"] == 5
        assert entry["combined_source_and_interaction_rank"] == 10
        assert entry["full_design_rank"] == 21
        assert entry["full_design_columns"] == 21
        assert entry["constant_exposure_interaction_rank"] == 0
        assert entry["invalid_coding_rank"] == 21
        assert entry["invalid_coding_columns"] == 22
        assert entry["panel_rows"] == 165
        assert entry["candidate_b_projector_residual_max"] < 1e-12
        assert entry["within_industry_combined_rank"] == 5
        assert entry["stacked_rank_under_prohibited_preprocessing"] == 10


@requires_run
def test_the_reproduced_design_checksums_match_c11():
    c11 = _c11()
    for variant_id, entry in _governance()["reproduction"]["per_variant"].items():
        assert entry["design_checksum"] == (
            c11["identification"]["observed"][variant_id]["design_checksum"]
        )


@requires_run
def test_the_dependency_audit_is_clean_and_bounded():
    flow = _governance()["information_flow"]
    assert flow["architecture_decision_dependency_clean"] is True
    assert flow["d_series_paths_opened"] == 0
    assert flow["static_inspection"]["no_forbidden_read_call"] is True
    assert flow["static_inspection"]["offending_read_calls"] == []
    assert flow["static_inspection"]["read_call_sites"] > 0
    assert flow["offending_imports"] == []
    assert flow["metric_substitution_invariance"]["invariant"] is True
    assert flow["original_execution_outcome_blind"] is False
    assert flow["does_not_prove"]
    IF.assert_dependency_conclusion_bounded(flow)


@requires_run
def test_the_decision_status_is_exploratory():
    status = _governance()["decision_status"]
    assert status["architecture_decision_status"] == GV.DECISION_STATUS
    assert status["architecture_mathematically_supported"] is True
    assert status["architecture_confirmatorily_selected"] is False
    assert status[
        "architecture_selection_outcome_independence_proven_by_dependency"] is True
    assert status["original_process_outcome_blind"] is False
    assert status["eligible_for_confirmatory_claims"] is False
    assert status["eligible_for_locked_test"] is False
    GV.assert_status_is_exploratory(status)


@requires_run
def test_the_architecture_scope_is_preserved():
    scope = _governance()["architecture_scope"]
    assert scope["per_industry_interaction_standardization"] is False
    assert scope["industry_fixed_effects_without_redundant_global_intercept"] is True
    assert scope["interaction_constructed_after_source_scaling"] is True
    assert scope["horizons_fitted_separately"] is True
    assert scope["ind_04_benchmark_passthrough"] is True
    assert scope["fo600_and_fo1500_separate_variants"] is True
    assert scope["simultaneous_channel_entry"] is False
    assert scope["outcome_based_channel_promotion"] is False
    assert scope["interpretation"] == "non_causal_predictive_interaction"


@requires_run
def test_no_umbrella_outcome_free_claim_anywhere():
    payload = _governance()
    GV.assert_no_umbrella_outcome_free_claim(payload)
    assert "outcome_free_execution" in json.dumps(payload)
    assert '"outcome_free": true' not in json.dumps(payload).lower()


@requires_run
def test_no_artifact_of_a_kind_c11r1_may_not_create():
    outputs = _governance()["outputs"]
    assert outputs["model_artifact_created"] is False
    assert outputs["prediction_artifact_created"] is False
    assert outputs["metric_artifact_created"] is False
    assert outputs["target_joined_artifact_created"] is False


@requires_run
def test_the_content_checksum_reproduces_from_the_payload():
    payload = _governance()
    stored = payload.pop("content_checksum")
    assert GV.content_checksum(payload) == stored


@requires_run
def test_the_documents_do_not_describe_a_tolerance_change():
    for path in (GOVERNANCE_MD, ERRATUM):
        GV.assert_not_described_as_a_tolerance_change(
            path.read_text(encoding="utf-8")
        )


@requires_run
def test_the_erratum_is_a_sidecar_and_names_what_it_corrects():
    text = ERRATUM.read_text(encoding="utf-8")
    assert "sidecar" in text.lower()
    assert "c11_architecture_decision.md" in text
    assert "did not pass" in text
    assert "dependency-clean" in text
    assert GV.DECISION_STATUS in text


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C11-R1 runner is absent")
def test_the_runner_never_reopens_the_d3_result_artifact():
    source = RUNNER.read_text(encoding="utf-8")
    for target in IF.read_call_targets(source):
        assert IF.forbidden_fragments_in(target["resolved"]) == [], target
    tree = ast.parse(source)
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for module in names:
            assert not any(f".{b}" in f".{module}"
                           for b in ("targets", "evaluation", "models", "modeling"))


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C11-R1 runner is absent")
def test_the_runner_fits_nothing():
    text = RUNNER.read_text(encoding="utf-8").lower()
    for fragment in ("lstsq", ".fit(", "ridge", "lasso", "regress", "sklearn",
                     "statsmodels", "np.linalg.solve", "pinv"):
        assert fragment not in text, fragment


# ===========================================================================
# The eighteen required synthetic failures.
# ===========================================================================
def test_synthetic_1_original_gate_set_reported_as_passing():
    with pytest.raises(GV.GovernanceError, match="ORIGINAL preregistered gate set"):
        GV.assert_original_gate_set_not_reported_as_passing(
            _gate_status(original_preregistered_gate_set_passed=True)
        )
    with pytest.raises(GV.GovernanceError, match="original gate implementation"):
        GV.assert_original_gate_set_not_reported_as_passing(
            _gate_status(original_gate_implementation_valid=True)
        )


def test_synthetic_2_correction_presented_as_preregistered():
    with pytest.raises(GV.GovernanceError, match="not recorded as having been made"):
        GV.assert_correction_not_presented_as_preregistered(
            _gate_status(gate_implementation_corrected_after_observation=False)
        )
    with pytest.raises(GV.GovernanceError, match="recorded as preregistered"):
        GV.assert_correction_not_presented_as_preregistered(
            _gate_status(expectations_rewritten_as_preregistered=True)
        )
    with pytest.raises(GV.GovernanceError, match="cleanly preregistered"):
        GV.assert_correction_not_presented_as_preregistered(
            _gate_status(architecture_decision_cleanly_preregistered=True)
        )


def test_synthetic_3_outcome_free_execution_claimed():
    with pytest.raises(GV.GovernanceError, match="recorded as outcome-free"):
        GV.assert_guard_does_not_erase_history(_incident(outcome_free_execution=True))
    with pytest.raises(GV.GovernanceError, match="outcome_free_execution"):
        GV.assert_incident_recorded(_incident(outcome_free_execution=True))
    with pytest.raises(GV.GovernanceError, match="umbrella"):
        GV.assert_no_umbrella_outcome_free_claim(
            {"summary": {"outcome_free": True}}
        )


def test_synthetic_4_later_guard_claimed_to_erase_the_access():
    with pytest.raises(GV.GovernanceError, match="does not change what happened"):
        GV.assert_guard_does_not_erase_history(
            _incident(later_guard_retroactively_erases_access=True)
        )


def test_synthetic_5_clean_rerun_claimed_to_restore_outcome_blindness():
    with pytest.raises(GV.GovernanceError, match="execution history is unchanged"):
        GV.assert_guard_does_not_erase_history(
            _incident(clean_rerun_restores_original_outcome_blindness=True)
        )


def test_synthetic_6_the_d3_result_artifact_is_opened_during_c11r1(tmp_path):
    permitted = CONFIG["information_flow"]["permitted_inputs"]
    with pytest.raises(IF.InformationFlowError, match="allowlist"):
        IF.assert_permitted_input(
            "docs/d3_operational_baseline_results.json", permitted
        )
    offender = tmp_path / "reopen.py"
    offender.write_text(
        "from pathlib import Path\n"
        "R = Path('docs/d3_operational_baseline_results.json')\n"
        "x = open(R)\n",
        encoding="utf-8",
    )
    report = IF.static_dependency_report([offender])
    assert report["no_forbidden_read_call"] is False


def test_synthetic_7_d3_metrics_enter_the_dependency_graph(tmp_path):
    offender = tmp_path / "leaky.py"
    offender.write_text(
        "from pathlib import Path\n"
        "M = Path('data/predictions/d4_operational_model_predictions.parquet')\n"
        "def go():\n"
        "    return read_parquet(M)\n",
        encoding="utf-8",
    )
    report = IF.dependency_report(
        [offender], [], CONFIG["information_flow"]["permitted_inputs"],
        {"all_reproduced": True}, {"invariant": True},
    )
    assert report["architecture_decision_dependency_clean"] is False
    assert report["static_inspection"]["offending_read_calls"]


def test_synthetic_8_architecture_moves_when_metrics_are_substituted():
    def leaky(inputs):
        fixture = inputs.get("forbidden_fixture") or {}
        if fixture.get("macro_industry_mae", 0) > 100:
            return "some_other_architecture"
        return AD.SELECTED_ARCHITECTURE_ID

    result = IF.metric_substitution_invariance(
        leaky, {"architecture": AD.SELECTED_ARCHITECTURE_ID},
        {"macro_industry_mae": 999.0},
    )
    assert result["invariant"] is False
    report = IF.dependency_report(
        [RUNNER], [], CONFIG["information_flow"]["permitted_inputs"],
        {"all_reproduced": True}, result,
    )
    assert report["architecture_decision_dependency_clean"] is False


def test_synthetic_9_the_wrong_stacked_rank_used_as_the_corrected_rule():
    """The corrected rule is about the SPECIFIED preprocessing, not the stack."""
    spec = CONFIG["corrected_gate_specification"]
    assert spec["observed"]["observed_stacked_rank_under_prohibited_preprocessing"] \
        == 10
    assert spec["original"]["original_preregistered_stacked_rank_expectation"] == 5
    assert "specified preprocessing" in spec["corrected_gate_condition"].lower()
    assert "stacked" not in spec["corrected_gate_condition"].lower()
    # A specification whose corrected rule still asserts the stacked drop is a
    # different specification, and the frozen digest catches it.
    frozen = GV.correction_checksum(_correction())
    with pytest.raises(GV.GovernanceError, match="may not move"):
        GV.assert_correction_frozen(
            _correction(
                corrected_gate_condition="the stacked rank must fall from 10 to 5"
            ),
            frozen,
        )


def test_synthetic_10_within_industry_or_sign_group_collapse_omitted():
    measurements = dict(CONFIG["corrected_gate_specification"]["correct_measurements"])
    for omitted in ("within_industry_combined_rank", "sign_equivalence_groups",
                    "interaction_blocks_after_prohibited_preprocessing"):
        partial = {k: v for k, v in measurements.items() if k != omitted}
        with pytest.raises(GV.GovernanceError, match="incomplete"):
            GV.assert_correct_measurements_present(partial)
    with pytest.raises(GV.GovernanceError, match="no collapse"):
        GV.assert_correct_measurements_present(
            {**measurements, "within_industry_combined_rank": 10}
        )
    with pytest.raises(GV.GovernanceError, match="does not collapse"):
        GV.assert_correct_measurements_present({
            **measurements, "interaction_blocks_after_prohibited_preprocessing": 11,
        })


def test_synthetic_11_c11_original_artifacts_overwritten():
    pinned = CONFIG["preserved_c11_record"]
    observed = {
        "artifacts": {
            name: {"byte_sha256": entry["byte_sha256"]}
            for name, entry in pinned["artifacts"].items()
        },
        "durable_checksums": dict(pinned["durable_checksums"]),
    }
    GV.assert_c11_record_preserved(pinned, observed)
    # A changed durable checksum is an overwrite.
    tampered = {**observed, "durable_checksums": {
        **observed["durable_checksums"], "c11_content_checksum": "0" * 64}}
    with pytest.raises(GV.PreservationError, match="durable checksums changed"):
        GV.assert_c11_record_preserved(pinned, tampered)
    # A byte change on a file with NO timestamp is an edit, not a regeneration.
    edited = {**observed, "artifacts": {
        **observed["artifacts"], "protocol_markdown": {"byte_sha256": "1" * 64}}}
    with pytest.raises(GV.PreservationError, match="that is an edit"):
        GV.assert_c11_record_preserved(pinned, edited)


def test_synthetic_12_candidate_b_restored_as_a_distinct_architecture():
    standardized = CD.standardize_source_block(
        [[1.0, 2.0, 3.0, 40.0, 5.0], [1.5, 2.5, 3.5, 41.0, 5.5],
         [2.0, 1.0, 4.0, 42.0, 6.5], [0.5, 3.0, 2.5, 43.5, 4.5]], 0
    )["matrix"]
    months = ["2024-01", "2024-02", "2024-03", "2024-04"]
    report = CD.candidate_b_equivalence_report(
        CD.build_candidate_a_design(standardized, months, "IND-01", V600),
        CD.build_candidate_b_design(standardized, months, "IND-01", 0.01, V600),
        0.01,
    )
    assert report["column_spaces_coincide"] is True
    assert report["per_industry_standardization_removes_exposure"] is True
    with pytest.raises(AD.ArchitectureDecisionError, match="distinct"):
        AD.assert_separate_conditioned_not_distinct(report, claimed_distinct=True)
    assert CONFIG["architecture_scope"]["formula"].strip().startswith("r[g,t,h]")


def test_synthetic_13_ind_04_forced_into_the_interaction():
    with pytest.raises(AD.ArchitectureDecisionError, match="not measured at zero"):
        AD.assert_ind_04_not_converted({
            "excluded_from_fuel_oil_correction": True,
            "converted_to_observed_zero": True,
            "retains_operational_benchmark_prediction": True,
        })
    with pytest.raises(AD.ArchitectureDecisionError, match="unresolved direction"):
        AD.assert_ind_04_not_converted({
            "excluded_from_fuel_oil_correction": False,
            "used_to_estimate_the_cost_pressure_interaction": True,
            "retains_operational_benchmark_prediction": True,
        })
    assert CONFIG["architecture_scope"]["ind_04_benchmark_passthrough"] is True


def test_synthetic_14_fo600_and_fo1500_combined_or_ranked():
    with pytest.raises(CD.CandidateDesignError, match="same sector-093"):
        CD.assert_single_variant_design([V600, V1500], "a combined design")
    with pytest.raises(AD.ArchitectureDecisionError, match="primary fuel-oil channel"):
        AD.assert_no_channel_preference({"primary_channel_selected": True})
    assert CONFIG["architecture_scope"]["simultaneous_channel_entry"] is False
    assert CONFIG["d5_authorization"]["scope"][
        "combined_or_selected_fuel_oil_channel"] is False


def test_synthetic_15_d5_receives_a_permission_outside_the_grant():
    granted = GV.authorize_d5(_closure_gates())
    GV.assert_d5_authorization_bounded(granted)
    for field in ("d5_locked_test_evaluation_authorized",
                  "d5_purge_evaluation_authorized",
                  "d5_confirmatory_claims_authorized",
                  "d5_channel_selection_authorized"):
        with pytest.raises(GV.AuthorizationError, match="outside the grant"):
            GV.assert_d5_authorization_bounded({**granted, field: True})


def test_synthetic_16_d5_authorized_despite_a_failed_reconstruction():
    for failed in ("architecture_reproduced_without_d_series_access",
                   "architecture_decision_dependency_clean",
                   "c11_original_record_preserved"):
        granted = GV.authorize_d5(_closure_gates(**{failed: False}))
        assert granted["all_closure_gates_passed"] is False
        assert granted["blocker"] is not None
        for field in GV.D5_AUTHORIZATION_FIELDS:
            assert granted[field] is False, field
    forced = {
        **dict.fromkeys(GV.D5_AUTHORIZATION_FIELDS, False),
        "d5_exploratory_modeling_authorized": True,
        "all_closure_gates_passed": False,
        "blocker": "architecture_decision_dependency_clean",
    }
    with pytest.raises(GV.AuthorizationError, match="despite a failed closure gate"):
        GV.assert_d5_authorization_bounded(forced)


@requires_run
def test_synthetic_17_target_prediction_or_metric_artifacts_created():
    payload = _governance()
    banned = ("mae", "rmse", "stress_score", "y_true", "y_pred", "residual",
              "coefficient_estimate", "locked_test_outcome")
    for key in ("model_artifact_created", "prediction_artifact_created",
                "metric_artifact_created", "target_joined_artifact_created"):
        assert payload["outputs"][key] is False
    # No metric VALUE anywhere in the record; the incident names files, not scores.
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not any(b == str(key).lower() for b in banned), key
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(payload)
    assert not any(
        (ROOT / "data" / d).exists() and any((ROOT / "data" / d).iterdir())
        for d in ("predictions_c11r1",)
    )


def test_synthetic_18_the_correction_described_as_a_tolerance_change():
    for claim in ("we loosened the tolerance until the gate passed",
                  "the rank tolerance was changed after observation",
                  "the threshold was relaxed to admit the result",
                  "we widened the tolerance on the stacked rank"):
        with pytest.raises(GV.GovernanceError, match="numerical change"):
            GV.assert_not_described_as_a_tolerance_change(claim)
    assert CONFIG["corrected_gate_specification"]["status"][
        "numerical_tolerance_changed"] is False
    assert CONFIG["corrected_gate_specification"]["status"][
        "thresholds_changed_after_observation"] is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_the_governance_checksum_is_deterministic_and_sensitive():
    args = (
        {"durable_checksums_unchanged": True}, "correction-digest",
        _incident(), "flow-digest", _closure_gates(), GV.authorize_d5(_closure_gates()),
    )
    assert GV.governance_checksum(*args) == GV.governance_checksum(*args)
    changed = list(args)
    changed[4] = _closure_gates(architecture_decision_dependency_clean=False)
    assert GV.governance_checksum(*changed) != GV.governance_checksum(*args)


def test_content_checksum_ignores_the_generation_timestamp():
    assert GV.content_checksum({"a": 1, "generated_at_utc": "2026-01-01"}) == (
        GV.content_checksum({"a": 1, "generated_at_utc": "2026-08-30"})
    )
