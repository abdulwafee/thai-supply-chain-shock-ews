"""Task E1 tests — project-wide evidence synthesis and baseline closeout.

A closeout report is a long list of assertions, and the dangerous ones are the
flattering ones. Four failure modes are checked rather than trusted.

**A number that does not match its artifact.** Every figure in the report is
registered with a pointer, resolved, and compared. A closeout that quotes a
value its own evidence does not contain is worse than one that omits it.

**A collapse of the evidence vocabulary.** Inconclusive is not no effect; not
supported is not disproven; a selected reference is not a proven superior; a
development evaluation is not a production validation; a latest-vintage
evaluation is not a real-time backtest. Each has its own guard, because each is
a different mistake.

**A superseded result presented as current.** D1 predates the issue-month
contract and D3/D4 replaced it. It stays in the ledger — deleting a negative
result is how a record starts lying — but it carries its marker, and the
supersession graph is checked for cycles.

**A test count that was typed rather than measured.** A stale number in a
reproducibility manifest looks like evidence. The manifest runs the suite and
parses its own summary line, and the guard refuses a supplied literal.

Nothing here opens, hashes or summarises a locked outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.synthesis import claim_registry as CR
from thai_supply_chain_ews.synthesis import evidence_synthesis as ES
from thai_supply_chain_ews.synthesis import reproducibility_manifest as RM

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "e1_evidence_synthesis.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
CLAIM_SCHEMA = ROOT / "schemas" / "e1_claim_registry.schema.yaml"
MANIFEST_SCHEMA = ROOT / "schemas" / "e1_reproducibility_manifest.schema.yaml"
LEDGER = ROOT / "docs" / "e1_evidence_ledger.json"
MANIFEST = ROOT / "docs" / "e1_reproducibility_manifest.json"
CLOSEOUT = ROOT / "docs" / "e1_technical_closeout.md"
CASE_STUDY = ROOT / "docs" / "e1_portfolio_case_study.md"
SUMMARY = ROOT / "docs" / "e1_executive_summary.md"
RUNNER = ROOT / "scripts" / "run_e1_evidence_synthesis.py"
DECISION_LOG = ROOT / "docs" / "architecture" / "decision_log.md"
LOCKED_MANIFEST = ROOT / "docs" / "d3_locked_test_manifest.json"

requires_run = pytest.mark.skipif(not LEDGER.is_file(), reason="E1 has not been run")


def _ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _status(**overrides):
    status = dict(CONFIG["project_status"])
    status.update(overrides)
    return status


def _claim(**overrides):
    claim = {
        "claim_id": "TEST-01",
        "claim_text": "A statement supported by an artifact.",
        "status": "verified",
        "scope": "foundation",
        "audience": "technical",
        "evidence_artifact": "docs/d3_operational_baseline_results.json",
        "evidence_json_pointer": "operational_contract_version",
        "limitations": ["targets remain latest vintage"],
        "locked_test_dependency": False,
    }
    claim.update(overrides)
    return claim


# ---------------------------------------------------------------------------
# Configuration and schemas
# ---------------------------------------------------------------------------
def test_the_config_parses_and_freezes_the_vocabulary():
    assert tuple(CONFIG["evidence_status_vocabulary"]) == ES.__dict__.get(
        "_UNUSED", tuple(CONFIG["evidence_status_vocabulary"])
    )
    assert set(CONFIG["evidence_status_vocabulary"]) == set(CR.EVIDENCE_STATUSES)
    assert set(CONFIG["prohibited_collapses"]) == {
        "inconclusive_into_no_effect", "not_supported_into_disproven",
        "unresolved_into_absent", "selected_reference_into_proven_superiority",
        "development_evaluation_into_production_validation",
        "latest_vintage_into_real_time_backtesting",
    }


def test_the_schemas_parse_and_pin_the_measurement_rule():
    claims = yaml.safe_load(CLAIM_SCHEMA.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    assert claims["project_failed_language_permitted"] is False
    assert manifest["verification"]["tests"]["copied"] is False
    assert manifest["referenced_raw_manifests"]["duplicated_here"] is False
    assert "test_count_literal" in manifest["prohibited_fields"]["fields"]


def test_the_required_project_status_is_the_frozen_one():
    ES.assert_project_status(_status())
    for name, expected in ES.REQUIRED_PROJECT_STATUS.items():
        assert CONFIG["project_status"][name] == expected, name


# ---------------------------------------------------------------------------
# Pointer resolution and reconciliation
# ---------------------------------------------------------------------------
def test_pointers_resolve_through_keys_containing_dots_and_pipes():
    payload = {"results": {"fo600_direct_sector093|h1": {"model": {"mae": 1.5}}},
               "metrics": {"1": {"baselines": {"a.b": {"v": 2}}}}}
    assert CR.resolve_pointer(
        payload, "results.fo600_direct_sector093|h1.model.mae") == 1.5
    assert CR.resolve_pointer(payload, "metrics.1.baselines.a.b.v") == 2
    with pytest.raises(CR.ClaimRegistryError, match="no match"):
        CR.resolve_pointer(payload, "results.nope")


def test_numeric_reconciliation_catches_a_wrong_figure():
    artifacts = {"a.json": {"x": {"y": 10.0}}}
    good = [{"id": "G", "value": 10.0, "artifact": "a.json", "pointer": "x.y"}]
    bad = [{"id": "B", "value": 11.0, "artifact": "a.json", "pointer": "x.y"}]
    assert CR.reconcile_numeric_claims(good, artifacts)["all_reconciled"] is True
    result = CR.reconcile_numeric_claims(bad, artifacts)
    assert result["all_reconciled"] is False
    assert result["failures"] == ["B"]


def test_derived_pointers_must_be_supplied_not_assumed():
    claims = [{"id": "D", "value": 6, "artifact": "a.json",
               "pointer": "__fallback_selection_count__"}]
    with pytest.raises(CR.ClaimRegistryError, match="was not supplied"):
        CR.reconcile_numeric_claims(claims, {"a.json": {}})
    assert CR.reconcile_numeric_claims(
        claims, {"a.json": {}}, derived={"__fallback_selection_count__": 6}
    )["all_reconciled"] is True


# ---------------------------------------------------------------------------
# The guards
# ---------------------------------------------------------------------------
def test_the_guards_allow_a_denial_and_refuse_an_assertion():
    """The report has to be able to say what it is NOT claiming."""
    ES.assert_inconclusive_not_absence(
        "A model that did not beat its benchmark has not disproved the hypothesis."
    )
    ES.assert_inconclusive_not_absence(
        "Prohibited: `fuel_oil_has_no_effect`."
    )
    with pytest.raises(ES.SynthesisError):
        ES.assert_inconclusive_not_absence(
            "The study disproved the commodity hypothesis."
        )


def test_the_production_guard_permits_production_data():
    """`production data` is manufacturing output, not a deployment."""
    ES.assert_d3_not_a_production_model(
        "The target is derived from industrial production data."
    )
    with pytest.raises(ES.SynthesisError, match="deployed production model"):
        ES.assert_d3_not_a_production_model("The D3 production model runs nightly.")


def test_the_superiority_guard_separates_registered_from_proven():
    ES.assert_baseline_reference_not_superiority(
        "Persistence is the registered reference; the comparison was inconclusive."
    )
    with pytest.raises(ES.SynthesisError, match="claims statistical superiority"):
        ES.assert_baseline_reference_not_superiority(
            "Persistence is statistically superior to no-contraction."
        )


def test_the_real_time_guard_refuses_the_upgrade():
    with pytest.raises(ES.SynthesisError, match="real-time backtest"):
        ES.assert_not_real_time("This is a fully real-time evaluation.")
    with pytest.raises(ES.SynthesisError, match="it is not"):
        ES.assert_not_real_time("", _status(fully_real_time_backtest=True))


def test_project_failed_language_is_refused():
    with pytest.raises(ES.SynthesisError, match="misstates the outcome"):
        ES.assert_no_project_failed_language("Ultimately the project failed.")
    ES.assert_no_project_failed_language(
        "The programme completed; the candidates did not earn promotion."
    )


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------
def test_the_supersession_graph_is_acyclic_and_named():
    graph = CR.assert_supersession_acyclic(CONFIG["supersession"]["edges"])
    assert graph["acyclic"] is True
    assert "D1" in graph["superseded_tasks"]
    assert "C11" in graph["superseded_tasks"]


def test_a_supersession_cycle_is_caught():
    with pytest.raises(CR.ClaimRegistryError, match="cycle"):
        CR.assert_supersession_acyclic([
            {"superseded": "A", "superseded_by": "B"},
            {"superseded": "B", "superseded_by": "A"},
        ])


# ---------------------------------------------------------------------------
# Locked test
# ---------------------------------------------------------------------------
def test_the_locked_manifest_is_key_only():
    manifest = json.loads(LOCKED_MANIFEST.read_text(encoding="utf-8"))
    ES.assert_locked_outcomes_untouched(manifest)
    assert manifest["locked_test_evaluated"] is False
    assert manifest["locked_test_outcomes_read"] is False
    for key in manifest:
        assert not any(token in key.lower() for token in
                       ("score", "mae", "rmse", "prediction", "observed")), key


def test_an_outcome_shaped_field_in_the_locked_manifest_is_caught():
    with pytest.raises(ES.SynthesisError, match="outcome-shaped"):
        ES.assert_locked_outcomes_untouched({
            "locked_test_evaluated": False, "locked_test_outcomes_read": False,
            "macro_industry_mae": 12.0,
        })


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
def test_a_supplied_test_count_is_refused():
    with pytest.raises(RM.ManifestError, match="supplied rather than measured"):
        RM.assert_measured({"tests_passed": 1234})
    with pytest.raises(RM.ManifestError, match="supplied rather than measured"):
        RM.assert_measured(1234)
    with pytest.raises(RM.ManifestError, match="record the command"):
        RM.assert_measured({"measured": True, "tests_passed": 1, "command": ""})
    RM.assert_measured({"measured": True, "command": "python -m pytest -q",
                        "tests_passed": 1})


def test_the_manifest_refuses_to_record_a_locked_path():
    RM.assert_no_locked_path(["docs/d5_development_results.json"])
    with pytest.raises(RM.ManifestError, match="locked-test path"):
        RM.assert_no_locked_path(["data/locked_test/holdout.parquet"])


# ---------------------------------------------------------------------------
# The generated artifacts
# ---------------------------------------------------------------------------
@requires_run
def test_every_numeric_claim_reconciles():
    reconciliation = _ledger()["numeric_reconciliation"]
    assert reconciliation["all_reconciled"] is True
    assert reconciliation["failures"] == []
    assert reconciliation["claims_checked"] >= 25
    for row in reconciliation["rows"]:
        assert row["reconciled"] is True, row["id"]
        assert abs(row["actual"] - row["expected"]) <= reconciliation["tolerance"]


@requires_run
def test_the_registry_is_complete_and_locked_free():
    ledger = _ledger()
    summary = ledger["claim_registry_summary"]
    assert summary["all_valid"] is True
    assert summary["locked_test_dependencies"] == 0
    assert summary["claims"] == summary["distinct_claim_ids"]
    for claim in ledger["claims"]:
        CR.validate_claim(claim)
        assert claim["locked_test_dependency"] is False
        assert claim["status"] in CR.EVIDENCE_STATUSES
        if claim["status"] == "superseded":
            assert claim["superseded_by"]


@requires_run
def test_the_development_ledger_keeps_the_negative_results():
    ledger = _ledger()["development_ledger"]
    d1, d3, d4, d5 = ledger["D1"], ledger["D3"], ledger["D4"], ledger["D5"]
    assert d1["status"] == "not_supported"
    assert d1["superseded_by"] == "D3/D4"
    assert d1["operationally_release_timing_correct"] is False
    assert d1["nested_protocol_fully_executed"] is False
    assert d1["fallback_selections"] == 6
    assert d1["total_selections"] == 30
    assert d1["fallback_effect_direction"] == "unknown"
    assert d1["presented_as_confirmatory"] is False
    assert d3["is_a_production_model"] is False
    assert d3["paired_comparison_against_no_contraction"] == "inconclusive"
    assert d3["proven_superior_to_no_contraction"] is False
    assert d4["status"] == "not_supported"
    assert d4["event_safety_overrides_mae_result"] is False
    assert d4["degenerate_rows"] == 180
    assert d4["total_rows"] == 360
    assert d5["point_estimates_beating_the_benchmark"] == 0
    assert d5["intervals_crossing_zero"] == 4
    assert d5["event_safety_failures"] == 4
    assert d5["incremental_signal_demonstrated"] is False
    assert d5["absence_of_effect_proven"] is False


@requires_run
def test_the_headline_figures_match_the_task_table():
    ledger = _ledger()["development_ledger"]
    assert round(ledger["D1"]["horizons"]["1"]["model_macro_mae"], 4) == 15.3073
    assert round(ledger["D1"]["horizons"]["1"]["benchmark_macro_mae"], 4) == 14.5287
    assert round(ledger["D1"]["horizons"]["3"]["model_macro_mae"], 4) == 16.1072
    assert round(ledger["D1"]["horizons"]["3"]["benchmark_macro_mae"], 4) == 14.6985
    assert round(ledger["D3"]["horizons"]["1"]["macro_industry_mae"], 4) == 17.0945
    assert round(ledger["D3"]["horizons"]["3"]["macro_industry_mae"], 4) == 16.6338
    assert round(
        ledger["D3"]["horizons"]["1"]["no_contraction_macro_mae"], 4) == 19.4453
    assert round(
        ledger["D3"]["horizons"]["3"]["no_contraction_macro_mae"], 4) == 16.9791
    assert round(ledger["D4"]["horizons"]["1"]["model_macro_mae"], 4) == 17.5616
    assert round(ledger["D4"]["horizons"]["3"]["model_macro_mae"], 4) == 17.9051
    for entry in ledger["D5"]["variant_horizons"].values():
        assert entry["mae_evidence"] == "inconclusive"
        assert entry["event_safety_passed"] is False


@requires_run
def test_the_locked_test_closeout_is_sealed():
    locked = _ledger()["locked_test"]
    assert locked["status"] == "sealed_unopened"
    assert locked["locked_test_outcomes_read"] is False
    assert locked["manifest_is_key_only"] is True
    assert locked["any_candidate_locked_test_evaluation_authorized"] is False
    assert locked["prediction_or_metric_exists_for_locked_origins"] is False
    assert locked["outcomes_opened_hashed_or_summarised"] is False
    assert locked["horizon_1_range_matches"] is True
    assert locked["horizon_3_range_matches"] is True
    assert locked["reserved_months_match"] is True
    assert not any(locked["candidate_authorizations"].values())
    assert "intentionally left unopened" in locked["required_language"]
    assert "intentionally left unopened" in CLOSEOUT.read_text(encoding="utf-8")


@requires_run
def test_the_manifest_measured_its_own_numbers():
    manifest = _manifest()
    tests = manifest["verification"]["tests"]
    ruff = manifest["verification"]["ruff"]
    RM.assert_measured(tests)
    RM.assert_measured(ruff)
    assert manifest["test_count_copied"] is False
    assert tests["tests_passed"] > 1000
    assert tests["command"] == "python -m pytest -q"
    assert ruff["command"] == "python -m ruff check ."
    assert manifest["verification"]["config_and_schema_parse"]["all_parsed"] is True
    assert manifest["locked_test"]["locked_path_recorded"] is False
    for entry in manifest["referenced_raw_manifests"]:
        assert entry["duplicated_here"] is False


@requires_run
def test_every_artifact_record_names_its_checksum_kind():
    for record in _manifest()["artifacts"]:
        if not record["exists"]:
            continue
        assert record["checksum"], record["path"]
        assert record["checksum_kind"] in (
            "content_checksum_timestamps_excluded", "byte_sha256"
        )
        assert record["version_controlled"] is (not record["generated"])


@requires_run
def test_the_portfolio_documents_make_no_unsupported_claim():
    for path in (CASE_STUDY, SUMMARY):
        text = path.read_text(encoding="utf-8")
        ES.assert_portfolio_wording(text)
        ES.assert_inconclusive_not_absence(text)
        ES.assert_not_real_time(text)
        ES.assert_no_project_failed_language(text)
        ES.assert_d3_not_a_production_model(text)


@requires_run
def test_the_case_study_keeps_task_codes_out_of_the_narrative():
    text = CASE_STUDY.read_text(encoding="utf-8")
    import re

    for code in ("C10", "C11", "D1", "D3", "D4", "D5", "C12"):
        assert not re.search(rf"\b{code}\b", text), code
    assert CONFIG["portfolio"]["internal_task_codes_in_main_narrative"] is False


@requires_run
def test_the_case_study_explains_what_it_must():
    text = CASE_STUDY.read_text(encoding="utf-8").lower()
    for token in ("random", "publish", "input-output", "constant", "benchmark",
                  "final test", "skills", "restart"):
        assert token in text, token


@requires_run
def test_the_summary_has_three_bullets_and_the_interview_answer():
    text = SUMMARY.read_text(encoding="utf-8")
    bullets = [line for line in text.splitlines() if line.startswith("* ")]
    assert len(bullets) == CONFIG["portfolio"]["cv_bullets"]
    assert "interview answer" in text.lower()
    assert "did not beat persistence" in text.lower()


@requires_run
def test_the_ledger_checksum_reproduces():
    ledger = _ledger()
    stored = ledger.pop("content_checksum")
    assert CR.ledger_checksum(ledger) == stored


@requires_run
def test_no_model_prediction_or_metric_artifact_was_created():
    outputs = _ledger()["outputs"]
    assert outputs["model_artifact_created"] is False
    assert outputs["prediction_artifact_created"] is False
    assert outputs["metric_artifact_created"] is False
    assert _ledger()["alternative_metrics_generated"] is False
    assert _ledger()["metrics_verified_against_registered_artifacts"] is True


def test_prior_decision_log_entries_are_untouched():
    text = DECISION_LOG.read_text(encoding="utf-8")
    for entry in ("AD-R149", "AD-R150", "AD-R151", "AD-R152", "AD-R153"):
        assert text.count(f"| {entry} |") == 1, entry
    assert "AD-R154" in text, "E1 must append rather than edit"


@pytest.mark.skipif(not RUNNER.is_file(), reason="the E1 runner is absent")
def test_the_runner_fits_nothing_and_computes_no_metric():
    """Checked on the CODE, not the prose.

    The case study legitimately contains the words "regression" and "bootstrap"
    when describing what was built; a substring scan over the whole file would
    forbid the report from naming its own methods. The AST sees only calls and
    imports.
    """
    import ast

    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    banned_modules = ("models", "modeling", "evaluation", "sklearn",
                      "statsmodels", "targets")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for module in names:
            assert not any(f".{b}" in f".{module}" for b in banned_modules), module

    banned_calls = ("fit", "predict", "fit_transform", "lstsq", "solve",
                    "macro_industry_mae", "pooled_mae", "bootstrap_macro_mae_ci",
                    "paired_macro_mae_interval", "fit_fixed_pooled_partial_ridge")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else None)
        assert name not in banned_calls, name


# ===========================================================================
# The twenty required synthetic failures.
# ===========================================================================
def test_synthetic_1_d3_is_called_a_deployed_model():
    for claim in ("The D3 production model is in service.",
                  "the deployed model runs monthly",
                  "the reference is deployed to production"):
        with pytest.raises(ES.SynthesisError, match="deployed production model"):
            ES.assert_d3_not_a_production_model(claim)


def test_synthetic_2_persistence_claimed_superior_to_no_contraction():
    for claim in ("persistence is statistically superior to no-contraction",
                  "the reference significantly outperforms no-contraction",
                  "proven superiority over the comparator"):
        with pytest.raises(ES.SynthesisError, match="statistical superiority"):
            ES.assert_baseline_reference_not_superiority(claim)


@requires_run
def test_synthetic_3_d1_is_described_as_fully_executed():
    d1 = _ledger()["development_ledger"]["D1"]
    assert d1["nested_protocol_fully_executed"] is False
    assert d1["presented_as_confirmatory"] is False
    assert d1["fallback_selections"] > 0
    text = CLOSEOUT.read_text(encoding="utf-8")
    assert "not fully executed" in text.lower() or "not fully executed" in (
        " ".join(d1.keys()).lower()
    )
    assert "fully executed confirmatory" in text.lower()


@requires_run
def test_synthetic_4_d1_used_as_the_current_operational_evaluation():
    ledger = _ledger()
    d1_claims = [c for c in ledger["claims"] if "D1" in c["claim_id"]]
    assert any(c["status"] == "superseded" for c in d1_claims)
    assert ledger["development_ledger"]["D1"]["superseded_by"] == "D3/D4"
    with pytest.raises(CR.ClaimRegistryError, match="names no successor"):
        CR.validate_claim(_claim(status="superseded"))


@requires_run
def test_synthetic_5_d4_event_safety_overrides_its_mae_result():
    d4 = _ledger()["development_ledger"]["D4"]
    assert d4["event_safety_overrides_mae_result"] is False
    assert d4["status"] == "not_supported"
    for horizon in d4["horizons"].values():
        assert horizon["mae_evidence_status"] == "incremental_signal_not_supported"
        assert horizon["event_safety_status"] == "event_safety_passed"
        assert horizon["approved_for_locked_test"] is False


def test_synthetic_6_d5_inconclusive_becomes_proof_of_absence():
    for claim in ("fuel oil has no effect on industrial stress",
                  "there is no predictive relationship",
                  "the hypothesis was disproved"):
        with pytest.raises(ES.SynthesisError):
            ES.assert_inconclusive_not_absence(claim)


@requires_run
def test_synthetic_7_an_eppo_channel_is_promoted():
    closure = json.loads(
        (ROOT / "docs" / "c12_channel_closure.json").read_text(encoding="utf-8")
    )
    assert closure["closure"]["fields"]["channel_selection_authorized"] is False
    assert closure["closure"][
        "either_variant_labelled_preferred_primary_or_less_bad"] is False
    d5 = _ledger()["development_ledger"]["D5"]
    assert len(d5["variant_horizons"]) == 4
    assert {e["mae_evidence"] for e in d5["variant_horizons"].values()} == {
        "inconclusive"
    }


@requires_run
def test_synthetic_8_a_commodity_model_is_called_locked_test_eligible():
    locked = _ledger()["locked_test"]
    assert not any(locked["candidate_authorizations"].values())
    assert locked["any_candidate_locked_test_evaluation_authorized"] is False
    with pytest.raises(ES.SynthesisError, match="locked-test authorized"):
        ES.verify_locked_test_closeout(
            json.loads(LOCKED_MANIFEST.read_text(encoding="utf-8")),
            CONFIG["locked_test"], {"D4": True},
        )


def test_synthetic_9_the_project_is_called_fully_real_time():
    for claim in ("a fully real-time backtest", "this is a real-time backtest",
                  "a true real-time evaluation"):
        with pytest.raises(ES.SynthesisError):
            ES.assert_not_real_time(claim)
    with pytest.raises(ES.SynthesisError):
        ES.assert_project_status(_status(fully_real_time_backtest=True))


@requires_run
def test_synthetic_10_feature_side_point_in_time_extended_to_the_target():
    table = {row["source_family"]: row for row in _ledger()["source_timing_table"]}
    assert table["World Bank Pink Sheet"]["point_in_time_status"] == (
        "feature side supported"
    )
    assert table["World Bank Pink Sheet"]["main_limitation"] == (
        "target side remains latest vintage"
    )
    assert table["OIE MPI target"]["point_in_time_status"] == (
        "target vintages unavailable"
    )
    assert _ledger()["project_status"]["latest_vintage_target_evaluation"] is True
    assert _ledger()["project_status"]["fully_real_time_backtest"] is False


def test_synthetic_11_an_unsupported_claim_lacks_an_artifact_pointer():
    with pytest.raises(CR.ClaimRegistryError, match="no evidence pointer"):
        CR.validate_claim(_claim(evidence_json_pointer=""))
    with pytest.raises(CR.ClaimRegistryError, match="no evidence pointer"):
        CR.validate_claim(_claim(evidence_artifact=""))
    with pytest.raises(CR.ClaimRegistryError, match="not loaded"):
        CR.validate_registry([_claim(evidence_artifact="docs/nope.json")], {})


def test_synthetic_12_a_superseded_claim_lacks_its_marker():
    with pytest.raises(CR.ClaimRegistryError, match="names no successor"):
        CR.validate_claim(_claim(status="superseded"))
    CR.validate_claim(_claim(status="superseded", superseded_by="D3/D4"))


@requires_run
def test_synthetic_13_negative_development_evidence_is_omitted():
    ledger = _ledger()["development_ledger"]
    assert set(ledger) == {"D1", "D3", "D4", "D5"}
    statuses = {task: entry["status"] for task, entry in ledger.items()}
    assert statuses["D1"] == "not_supported"
    assert statuses["D4"] == "not_supported"
    assert statuses["D5"] == "inconclusive"
    text = CLOSEOUT.read_text(encoding="utf-8")
    for figure in ("15.3073", "17.5616", "17.9051"):
        assert figure in text, figure


def test_synthetic_14_locked_outcomes_are_opened_or_hashed():
    with pytest.raises(ES.SynthesisError, match="outcome-shaped"):
        ES.assert_locked_outcomes_untouched({
            "locked_test_evaluated": False, "locked_test_outcomes_read": False,
            "locked_observed_score": 42.0,
        })
    with pytest.raises(ES.SynthesisError, match="outcomes as read"):
        ES.assert_locked_outcomes_untouched({"locked_test_outcomes_read": True})
    with pytest.raises(RM.ManifestError, match="locked-test path"):
        RM.assert_no_locked_path(["data/locked_test/outcomes.parquet"])


@requires_run
def test_synthetic_15_a_new_metric_or_model_artifact_is_created():
    ledger = _ledger()
    assert ledger["alternative_metrics_generated"] is False
    for key in ("model_artifact_created", "prediction_artifact_created",
                "metric_artifact_created"):
        assert ledger["outputs"][key] is False
    generated = {r["path"] for r in _manifest()["artifacts"] if r["generated"]}
    assert not any("e1_" in path for path in generated)


@requires_run
def test_synthetic_16_portfolio_text_claims_the_model_beat_the_benchmark():
    for claim in ("our model beat the benchmark", "the model beats the baseline",
                  "it outperformed the benchmark",
                  "a deployable early-warning model"):
        with pytest.raises(ES.SynthesisError, match="not supported"):
            ES.assert_portfolio_wording(claim)
    text = CASE_STUDY.read_text(encoding="utf-8")
    ES.assert_portfolio_wording(text)


@requires_run
def test_synthetic_17_test_counts_are_copied_rather_than_measured():
    tests = _manifest()["verification"]["tests"]
    assert tests["measured"] is True
    assert tests["command"] == "python -m pytest -q"
    assert "measured_at_utc" in tests
    with pytest.raises(RM.ManifestError, match="supplied rather than measured"):
        RM.assert_measured({"tests_passed": tests["tests_passed"]})


@requires_run
def test_synthetic_18_an_upstream_result_artifact_is_modified():
    """Every pinned upstream checksum still matches its live artifact."""
    for record in _manifest()["artifacts"]:
        if not record["exists"] or record["task"] == "E1":
            continue
        path = ROOT / record["path"]
        if record["checksum_kind"] == "content_checksum_timestamps_excluded":
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload["content_checksum"] == record["checksum"], record["path"]
        else:
            import hashlib

            assert hashlib.sha256(path.read_bytes()).hexdigest() == (
                record["checksum"]
            ), record["path"]


@requires_run
def test_synthetic_19_source_validity_confused_with_modeling_eligibility():
    closure = json.loads(
        (ROOT / "docs" / "c12_channel_closure.json").read_text(encoding="utf-8")
    )
    validity = closure["validity_versus_eligibility"]
    assert validity["official_eppo_source_documents_still_valid_evidence"] is True
    assert validity["c8_transformations_reproducible"] is True
    assert validity["may_enter_further_operational_modeling"] is False
    assert validity["predictive_utility_demonstrated_on_development_data"] is False
    from thai_supply_chain_ews.structure import fuel_oil_channel_closure as CL

    with pytest.raises(CL.ChannelClosureError, match="MODELING USE"):
        CL.assert_source_validity_preserved({
            **validity, "c8_transformations_reproducible": False,
        })


def test_synthetic_20_the_c12_reopening_guard_is_bypassed():
    from thai_supply_chain_ews.structure import fuel_oil_channel_closure as CL

    policy = yaml.safe_load(
        (ROOT / "configs" / "fuel_oil_channel_closure.yaml").read_text(
            encoding="utf-8")
    )["enforcement"]
    with pytest.raises(CL.ClosedChannelError, match="closed_after_registered"):
        CL.assert_modeling_entry_permitted(
            ["fo600_direct_sector093"], "modeling", policy
        )
    with pytest.raises(CL.ReopeningEvidenceError, match="missing"):
        CL.assert_modeling_entry_permitted(
            ["fo600_direct_sector093"], "modeling", policy,
            superseding_decision={"new_evidence_id": "X", "active": True},
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_the_ledger_checksum_ignores_the_generation_timestamp():
    assert CR.ledger_checksum({"a": 1, "generated_at_utc": "2026-01-01"}) == (
        CR.ledger_checksum({"a": 1, "generated_at_utc": "2026-08-30"})
    )


def test_the_manifest_checksum_ignores_measurement_timestamps():
    first = {"a": 1, "verification": {"tests": {"measured_at_utc": "2026-01-01"}}}
    second = {"a": 1, "verification": {"tests": {"measured_at_utc": "2026-08-30"}}}
    assert RM.manifest_checksum(first) == RM.manifest_checksum(second)
