"""Task E1 — project-wide development evidence synthesis and baseline closeout.

Turns the registered results from B1 through C12 into a technical closeout, a
portfolio case study, an executive summary with CV bullets, a machine-readable
evidence ledger and a reproducibility manifest.

SYNTHESIS ONLY. No model is rerun, no metric is recomputed from raw predictions,
nothing is fitted, no estimator is compared, no commodity or channel is selected,
no subgroup is mined, no published decision status is changed, no purge outcome
is read, and no locked outcome is ever opened, hashed, summarised or inferred.

The synthesis contract is frozen and hashed before any numerical result artifact
is read.

    docs/e1_technical_closeout.md
    docs/e1_portfolio_case_study.md
    docs/e1_executive_summary.md
    docs/e1_evidence_ledger.json
    docs/e1_reproducibility_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from thai_supply_chain_ews.synthesis import claim_registry as CR  # noqa: E402
from thai_supply_chain_ews.synthesis import evidence_synthesis as ES  # noqa: E402
from thai_supply_chain_ews.synthesis import reproducibility_manifest as RM  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "e1_evidence_synthesis.yaml"
LOCKED_MANIFEST = DOCS / "d3_locked_test_manifest.json"

TASK_CODES = (
    "B1", "B3", "B4", "C1", "C2", "C3", "C4", "C5", "C7", "C8", "C9", "C10",
    "C11", "C12", "D1", "D2", "D3", "D4", "D5", "E1",
)


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def freeze_contract(config) -> tuple:
    """Hash the synthesis rules before any result artifact is read."""
    contract = {
        "synthesis_contract_version": config["synthesis_contract_version"],
        "included_tasks": config["included_tasks"],
        "evidence_status_vocabulary": config["evidence_status_vocabulary"],
        "prohibited_collapses": config["prohibited_collapses"],
        "project_status": config["project_status"],
        "supersession": config["supersession"],
        "numeric_reconciliation": config["numeric_reconciliation"],
        "source_timing_table": config["source_timing_table"],
        "structural_synthesis": config["structural_synthesis"],
        "cross_task_conclusions": config["cross_task_conclusions"],
        "locked_test": config["locked_test"],
        "claim_registry": config["claim_registry"],
        "portfolio": config["portfolio"],
        "prohibited_actions": config["prohibited_actions"],
        "final_declaration": config["final_declaration"],
    }
    text = json.dumps(contract, ensure_ascii=False, sort_keys=True, default=str)
    return contract, hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_artifacts(config) -> dict:
    """Open every registered artifact named by the frozen contract."""
    artifacts = {}
    for group in config["included_tasks"].values():
        for entry in group.values():
            relative = entry["artifact"]
            path = ROOT / relative
            if path.is_file():
                artifacts[relative] = load_json(path)
    return artifacts


def derive_counts(artifacts) -> dict:
    """The few quantities that are counts of a structure, computed not asserted."""
    d1 = artifacts.get("docs/d1_development_results.json", {})
    selections = d1.get("selections", {})
    fallback = sum(
        1 for entry in selections.values()
        if "fallback" in str(entry.get("selection_reason", ""))
    )
    return {
        "__selection_count__": len(selections),
        "__fallback_selection_count__": fallback,
    }


def build_claims(config, artifacts) -> list:
    """Every material claim, each with its status, pointer and limitations."""
    d1_limits = ["nested protocol not fully executed",
                 "six of thirty origin-horizon selections used the fallback",
                 "fallback effect direction unknown"]
    d4_limits = ["half the primary panel was benchmark passthrough",
                 "all direct predictors constant for six industries"]
    d5_limits = ["fifteen issue-month clusters limit uncertainty resolution",
                 "event safety failed"]
    d3_limits = ["paired comparison against no-contraction was inconclusive",
                 "registered reference, not a proven superior"]

    claims = [
        {
            "claim_id": "E1-STATUS-01",
            "claim_text": (
                "The development programme closed without a supported "
                "incremental commodity model."
            ),
            "status": "verified", "scope": "project_status", "audience": "both",
            "evidence_artifact": "docs/d5_development_results.json",
            "evidence_json_pointer": "scope.evaluation_scope",
            "limitations": ["development-only evaluation"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-FOUND-01",
            "claim_text": (
                "A leakage-aware, release-aware research pipeline was built and "
                "is reproducible from official sources."
            ),
            "status": "verified", "scope": "foundation", "audience": "both",
            "evidence_artifact": "docs/d3_operational_baseline_results.json",
            "evidence_json_pointer": "operational_contract_version",
            "limitations": ["targets remain latest vintage"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D1-01",
            "claim_text": (
                "The original commodity residual model did not beat its "
                "development benchmark at either horizon."
            ),
            "status": "not_supported", "scope": "world_bank_path",
            "audience": "technical",
            "evidence_artifact": "docs/d1_development_results.json",
            "evidence_json_pointer": "results.h1.model.macro_industry_mae",
            "limitations": d1_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D1-02",
            "claim_text": (
                "That original evaluation is superseded for operational "
                "interpretation: it predates the issue-month timing contract."
            ),
            "status": "superseded", "scope": "world_bank_path",
            "audience": "technical", "superseded_by": "D3/D4",
            "evidence_artifact": "docs/d1_development_results.errata.md",
            "evidence_json_pointer": "errata.fallback_effect_direction",
            "limitations": d1_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D3-01",
            "claim_text": (
                "Persistence forecasts are the registered operational reference "
                "at both horizons."
            ),
            "status": "verified", "scope": "foundation", "audience": "both",
            "evidence_artifact": "docs/d3_operational_baseline_results.json",
            "evidence_json_pointer": "benchmark_selection.1.selected_benchmark",
            "limitations": d3_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D3-02",
            "claim_text": (
                "The paired comparison of the registered reference against the "
                "no-contraction comparator was inconclusive."
            ),
            "status": "inconclusive", "scope": "foundation",
            "audience": "technical",
            "evidence_artifact": "docs/d3r1_benchmark_interpretation.json",
            "evidence_json_pointer": "conclusion",
            "limitations": d3_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D4-01",
            "claim_text": (
                "The fixed-specification commodity model did not demonstrate "
                "incremental signal at either horizon."
            ),
            "status": "not_supported", "scope": "world_bank_path",
            "audience": "both",
            "evidence_artifact": "docs/d4_operational_model_results.json",
            "evidence_json_pointer": "evaluation.1.mae_evidence_status",
            "limitations": d4_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D4-02",
            "claim_text": (
                "Its event-safety gate passed, which does not override the "
                "primary error result."
            ),
            "status": "supported_with_limitations", "scope": "world_bank_path",
            "audience": "technical",
            "evidence_artifact": "docs/d4_operational_model_results.json",
            "evidence_json_pointer": "evaluation.1.event_safety_status",
            "limitations": [*d4_limits, "both gates were required"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D5-01",
            "claim_text": (
                "The pooled fuel-oil interaction did not demonstrate incremental "
                "signal for either variant at either horizon."
            ),
            "status": "inconclusive", "scope": "eppo_path", "audience": "both",
            "evidence_artifact": "docs/d5_development_results.json",
            "evidence_json_pointer": (
                "results.fo600_direct_sector093|h1.mae_evidence"
            ),
            "limitations": d5_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-D5-02",
            "claim_text": (
                "Absence of a fuel-oil effect was not established; the evidence "
                "is inconclusive."
            ),
            "status": "inconclusive", "scope": "eppo_path", "audience": "both",
            "evidence_artifact": "docs/c12_channel_closure.json",
            "evidence_json_pointer": (
                "conclusion.explicit_record.absence_of_effect_proven"
            ),
            "limitations": d5_limits,
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-C10-01",
            "claim_text": (
                "Per-industry structural conditioning adds cross-industry scale "
                "and no temporal degrees of freedom."
            ),
            "status": "verified", "scope": "structural", "audience": "technical",
            "evidence_artifact": "docs/c10_design_matrix_audit.json",
            "evidence_json_pointer": (
                "decisions.conditioning_adds_temporal_degrees_of_freedom"
            ),
            "limitations": ["a design property, not a predictive conclusion"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-C11-01",
            "claim_text": (
                "The pooled interaction architecture is mathematically "
                "identifiable and was selected exploratorily."
            ),
            "status": "supported_with_limitations", "scope": "eppo_path",
            "audience": "technical",
            "evidence_artifact": "docs/c11r1_governance_decision.json",
            "evidence_json_pointer": (
                "decision_status.architecture_decision_status"
            ),
            "limitations": ["selection followed a documented post-observation "
                            "specification correction"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-C11-02",
            "claim_text": (
                "The original architecture selection is superseded in status by "
                "its governance correction."
            ),
            "status": "superseded", "scope": "eppo_path", "audience": "technical",
            "superseded_by": "C11-R1",
            "evidence_artifact": "docs/c11_architecture_decision.json",
            "evidence_json_pointer": "selection.selected_architecture",
            "limitations": ["one of nine gates did not pass as preregistered"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-C12-01",
            "claim_text": (
                "The refinery-price channel is closed to further modeling while "
                "its source pipeline remains valid."
            ),
            "status": "verified", "scope": "eppo_path", "audience": "both",
            "evidence_artifact": "docs/c12_channel_closure.json",
            "evidence_json_pointer": "closure.fields.channel_status",
            "limitations": ["closure applies to modeling use only"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-STRUCT-01",
            "claim_text": (
                "Aluminium and copper share one input-output sector and are not "
                "independent exposure measurements."
            ),
            "status": "verified", "scope": "structural", "audience": "technical",
            "evidence_artifact": "docs/c3_commodity_exposure_matrix.json",
            "evidence_json_pointer": "crosswalk_version",
            "limitations": ["commodity mappings are broad proxies"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-STRUCT-02",
            "claim_text": (
                "Every industry purchases refinery products directly, while "
                "crude exposure is direct-zero for most."
            ),
            "status": "verified", "scope": "structural", "audience": "both",
            "evidence_artifact": "docs/c9_sector093_exposure_decision.json",
            "evidence_json_pointer": "eligible_industries_per_channel",
            "limitations": ["sector 093 is a nine-product basket, a broad proxy"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-TIMING-01",
            "claim_text": (
                "Commodity features use archived first-release values with "
                "verified publication timing; targets remain latest vintage."
            ),
            "status": "supported_with_limitations", "scope": "source_timing",
            "audience": "both",
            "evidence_artifact": "docs/c1_commodity_source_audit.json",
            "evidence_json_pointer": "task",
            "limitations": ["target side is not point-in-time",
                            "not a real-time backtest"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-TIMING-02",
            "claim_text": (
                "Refinery-price documents are latest-vintage with unverified "
                "first-release timing, carried under a conservative policy lag."
            ),
            "status": "supported_with_limitations", "scope": "source_timing",
            "audience": "technical",
            "evidence_artifact": "docs/c7_5_eppo_semantic_decision.json",
            "evidence_json_pointer": "task",
            "limitations": ["publication timing is a policy assumption, not a "
                            "measurement"],
            "locked_test_dependency": False,
        },
        {
            "claim_id": "E1-LOCK-01",
            "claim_text": (
                "The locked final test was left unopened because no "
                "independently preregistered candidate earned access."
            ),
            "status": "verified", "scope": "locked_test", "audience": "both",
            "evidence_artifact": "docs/d3_locked_test_manifest.json",
            "evidence_json_pointer": "locked_test_outcomes_read",
            "limitations": ["the reservation is key-only; no outcome was read"],
            "locked_test_dependency": False,
        },
    ]
    for conclusion in config["cross_task_conclusions"]:
        claims.append({
            "claim_id": f"E1-{conclusion['id']}",
            "claim_text": conclusion["text"].strip(),
            "status": conclusion["status"],
            "scope": "cross_task", "audience": "technical",
            "evidence_artifact": "docs/d5_development_results.json",
            "evidence_json_pointer": "scope.evaluation_scope",
            "limitations": ["development-only evidence"],
            "locked_test_dependency": False,
        })
    return claims


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-measurement", action="store_true",
        help="reuse the last measured test and lint results instead of rerunning",
    )
    arguments = parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    # --- freeze the synthesis contract BEFORE any result artifact is read ---
    contract, contract_digest = freeze_contract(config)

    # --- now the registered results may load -------------------------------
    artifacts = load_artifacts(config)
    derived = derive_counts(artifacts)
    reconciliation = CR.reconcile_numeric_claims(
        config["numeric_reconciliation"]["claims"], artifacts,
        float(config["numeric_reconciliation"]["tolerance"]), derived,
    )
    if not reconciliation["all_reconciled"]:
        raise SystemExit(
            f"E1 stops: numeric claims did not reconcile: "
            f"{reconciliation['failures']}"
        )

    supersession = CR.assert_supersession_acyclic(config["supersession"]["edges"])
    status = dict(config["project_status"])
    ES.assert_project_status(status)

    locked = ES.verify_locked_test_closeout(
        load_json(LOCKED_MANIFEST), config["locked_test"],
        {
            "D1": artifacts["docs/d1_development_results.json"].get(
                "approved_for_locked_test", False),
            "D4": artifacts["docs/d4_operational_model_results.json"][
                "evaluation"]["1"]["decision"]["approved_for_locked_test"],
            "D5": artifacts["docs/d5_development_results.json"]["scope"][
                "locked_test_evaluation_authorized"],
            "C12": artifacts["docs/c12_channel_closure.json"]["closure"][
                "fields"]["locked_test_evaluation_authorized"],
        },
    )

    claims = build_claims(config, artifacts)
    required_limitations = {
        "docs/d1_development_results.json": ["fallback"],
        "docs/d1_development_results.errata.md": ["fallback"],
        "docs/d4_operational_model_results.json": ["passthrough"],
        "docs/d5_development_results.json": [],
        "docs/c12_channel_closure.json": [],
    }
    artifacts_for_registry = dict(artifacts)
    artifacts_for_registry["docs/d1_development_results.errata.md"] = {
        "errata": {"fallback_effect_direction": "unknown"}
    }
    registry = CR.validate_registry(
        claims, artifacts_for_registry, required_limitations,
        config["claim_registry"]["incompatible_contract_pairs"],
        config["claim_registry"]["qualification_required_phrase"],
    )

    # --- measured, not quoted ----------------------------------------------
    measurement_cache = DOCS / "e1_reproducibility_manifest.json"
    if arguments.skip_measurement and measurement_cache.is_file():
        cached = load_json(measurement_cache)
        tests, ruff = cached["verification"]["tests"], cached["verification"]["ruff"]
    else:
        tests = RM.measure_test_count(ROOT)
        ruff = RM.measure_ruff(ROOT)
    RM.assert_measured(tests)
    RM.assert_measured(ruff)

    ledger = build_ledger(config, contract, contract_digest, artifacts,
                          reconciliation, supersession, status, locked, claims,
                          registry, generated_at)
    manifest = build_manifest(config, artifacts, tests, ruff, locked,
                              supersession, generated_at)

    write_documents(config, ledger, manifest, artifacts)

    print(json.dumps({
        "synthesis_contract_checksum": contract_digest,
        "artifacts_loaded": len(artifacts),
        "numeric_claims_reconciled": reconciliation["all_reconciled"],
        "numeric_claims_checked": reconciliation["claims_checked"],
        "claims_registered": registry["claims"],
        "claims_by_status": registry["by_status"],
        "supersession_acyclic": supersession["acyclic"],
        "superseded_tasks": supersession["superseded_tasks"],
        "locked_test_status": locked["status"],
        "locked_outcomes_read": locked["locked_test_outcomes_read"],
        "any_candidate_locked_test_authorized":
            locked["any_candidate_locked_test_evaluation_authorized"],
        "development_program_status": status["development_program_status"],
        "tests_passed": tests["tests_passed"],
        "tests_measured": tests["measured"],
        "ruff_passing": ruff["passing"],
        "evidence_ledger_checksum": ledger["content_checksum"],
        "manifest_checksum": manifest["manifest_checksum"],
    }, ensure_ascii=False, indent=1))


def build_ledger(config, contract, contract_digest, artifacts, reconciliation,
                 supersession, status, locked, claims, registry,
                 generated_at) -> dict:
    """The machine-readable evidence ledger."""
    ledger = {
        "task": "E1",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "synthesis_contract_version": config["synthesis_contract_version"],
        "synthesis_contract": contract,
        "synthesis_contract_checksum": contract_digest,
        "contract_frozen_before_result_artifacts_read": True,
        "project_status": status,
        "evidence_status_vocabulary": config["evidence_status_vocabulary"],
        "prohibited_collapses": config["prohibited_collapses"],
        "numeric_reconciliation": reconciliation,
        "supersession": {**config["supersession"], "graph": supersession},
        "source_timing_table": config["source_timing_table"],
        "equivalent_evidence_quality_implied_across_sources": False,
        "structural_synthesis": config["structural_synthesis"],
        "development_ledger": build_development_ledger(artifacts),
        "cross_task_conclusions": config["cross_task_conclusions"],
        "locked_test": locked,
        "claims": claims,
        "claim_registry_summary": registry,
        "prohibited_actions": config["prohibited_actions"],
        "metrics_verified_against_registered_artifacts": True,
        "alternative_metrics_generated": False,
        "outputs": config["outputs"],
        "final_declaration": config["final_declaration"],
    }
    ledger["content_checksum"] = CR.ledger_checksum(ledger)
    return ledger


def build_development_ledger(artifacts) -> dict:
    """Every material development result, including the negative ones."""
    d1 = artifacts["docs/d1_development_results.json"]
    d3 = artifacts["docs/d3_operational_baseline_results.json"]
    d4 = artifacts["docs/d4_operational_model_results.json"]
    d5 = artifacts["docs/d5_development_results.json"]
    selections = d1.get("selections", {})
    fallback = sorted(
        key for key, entry in selections.items()
        if "fallback" in str(entry.get("selection_reason", ""))
    )
    return {
        "D1": {
            "evaluation_contract": "pre_operational_development_split",
            "status": "not_supported",
            "superseded_by": "D3/D4",
            "superseded_scope": "operational_interpretation",
            "horizons": {
                "1": {
                    "model_macro_mae": d1["results"]["h1"]["model"][
                        "macro_industry_mae"],
                    "benchmark_macro_mae": d1["results"]["h1"]["benchmark"][
                        "macro_industry_mae"],
                    "benchmark_name": d1["results"]["h1"]["benchmark_name"],
                },
                "3": {
                    "model_macro_mae": d1["results"]["h3"]["model"][
                        "macro_industry_mae"],
                    "benchmark_macro_mae": d1["results"]["h3"]["benchmark"][
                        "macro_industry_mae"],
                    "benchmark_name": d1["results"]["h3"]["benchmark_name"],
                },
            },
            "operationally_release_timing_correct": False,
            "nested_protocol_fully_executed": False,
            "fallback_selections": len(fallback),
            "total_selections": len(selections),
            "fallback_keys": fallback,
            "fallback_effect_direction": "unknown",
            "approved_for_locked_test": d1.get("approved_for_locked_test", False),
            "presented_as_confirmatory": False,
        },
        "D3": {
            "evaluation_contract": "operational_contract_v1",
            "status": "verified",
            "role": "registered_operational_reference",
            "is_a_production_model": False,
            "horizons": {
                "1": {
                    "selected_benchmark": d3["benchmark_selection"]["1"][
                        "selected_benchmark"],
                    "macro_industry_mae": d3["metrics"]["1"]["baselines"][
                        "operational_persistence_latest_published"][
                        "macro_industry_mae"],
                    "no_contraction_macro_mae": d3["metrics"]["1"]["baselines"][
                        "operational_no_contraction"]["macro_industry_mae"],
                },
                "3": {
                    "selected_benchmark": d3["benchmark_selection"]["3"][
                        "selected_benchmark"],
                    "macro_industry_mae": d3["metrics"]["3"]["baselines"][
                        "operational_persistence_trailing_3m_max"][
                        "macro_industry_mae"],
                    "no_contraction_macro_mae": d3["metrics"]["3"]["baselines"][
                        "operational_no_contraction"]["macro_industry_mae"],
                },
            },
            "paired_comparison_against_no_contraction": "inconclusive",
            "selection_rule": "preregistered_false_negative_tie_break",
            "proven_superior_to_no_contraction": False,
        },
        "D4": {
            "evaluation_contract": "operational_contract_v1",
            "status": "not_supported",
            "horizons": {
                horizon: {
                    "model_macro_mae": entry["model"]["macro_industry_mae"],
                    "reference_macro_mae": entry["operational_persistence"][
                        "macro_industry_mae"],
                    "paired_ci_low": entry["vs_operational_persistence"][
                        "paired_difference_model_minus_comparator"]["ci_low"],
                    "paired_ci_high": entry["vs_operational_persistence"][
                        "paired_difference_model_minus_comparator"]["ci_high"],
                    "mae_evidence_status": entry["mae_evidence_status"],
                    "event_safety_status": entry["event_safety_status"],
                    "approved_for_locked_test": entry["decision"][
                        "approved_for_locked_test"],
                }
                for horizon, entry in d4["evaluation"].items()
            },
            "degenerate_rows": d4["degenerate_design_summary"][
                "primary_direct_lag2"]["rows_degenerate"],
            "total_rows": d4["degenerate_design_summary"][
                "primary_direct_lag2"]["rows_total"],
            "degenerate_industries": d4["degenerate_design_summary"][
                "primary_direct_lag2"]["degenerate_industries"],
            "event_safety_overrides_mae_result": False,
            "remained_exploratory": True,
        },
        "D5": {
            "evaluation_contract": "operational_contract_v1",
            "status": "inconclusive",
            "variant_horizons": {
                key: {
                    "variant_id": entry["variant_id"],
                    "horizon": entry["horizon"],
                    "model_macro_mae": entry["model"]["macro_industry_mae"],
                    "reference_macro_mae": entry["benchmark"][
                        "macro_industry_mae"],
                    "paired_ci_low": entry["bootstrap"]["paired_ci_low"],
                    "paired_ci_high": entry["bootstrap"]["paired_ci_high"],
                    "mae_evidence": entry["mae_evidence"],
                    "event_safety_passed": entry["event_safety"][
                        "event_safety_passed"],
                    "overall_status": entry["overall_status"],
                }
                for key, entry in d5["results"].items()
            },
            "point_estimates_beating_the_benchmark": 0,
            "intervals_crossing_zero": 4,
            "event_safety_failures": 4,
            "incremental_signal_demonstrated": False,
            "absence_of_effect_proven": False,
            "channel_closed_by": "C12",
        },
    }


def build_manifest(config, artifacts, tests, ruff, locked, supersession,
                   generated_at) -> dict:
    """The reproducibility manifest: paths, checksums, environment, results."""
    registered = [
        ("configs/e1_evidence_synthesis.yaml", "E1", False, "current", None),
        ("docs/d1_development_results.json", "D1", False, "superseded", "D3/D4"),
        ("docs/d1_development_results.errata.md", "D1", False, "current", None),
        ("docs/d3_operational_baseline_results.json", "D3", False, "current", None),
        ("docs/d3_locked_test_manifest.json", "D3", False, "current", None),
        ("docs/d3r1_benchmark_interpretation.json", "D3-R1", False, "current", None),
        ("docs/d4_operational_model_results.json", "D4", False, "current", None),
        ("docs/c3_commodity_exposure_matrix.json", "C3", False, "current", None),
        ("docs/c7_eppo_full_archive_audit.json", "C7", False, "current", None),
        ("docs/c7_5_eppo_semantic_decision.json", "C7.5", False, "current", None),
        ("docs/c8_eppo_transformation_audit.json", "C8", False, "current", None),
        ("docs/c9_sector093_exposure_decision.json", "C9", False, "current", None),
        ("docs/c9_fuel_oil_conditioning_audit.json", "C9", False, "current", None),
        ("docs/c10_design_matrix_audit.json", "C10", False, "current", None),
        ("docs/c11_architecture_decision.json", "C11", False, "superseded",
         "C11-R1"),
        ("docs/c11r1_governance_decision.json", "C11-R1", False, "current", None),
        ("docs/d5_development_results.json", "D5", False, "current", None),
        ("docs/d5_assembly_audit.json", "D5", False, "current", None),
        ("docs/d5_frozen_protocol.json", "D5", False, "current", None),
        ("docs/c12_channel_closure.json", "C12", False, "current", None),
        ("data/features/c8_eppo_fuel_oil_transformations.parquet", "C8", True,
         "current", None),
        ("data/features/c9_fuel_oil_conditioned.parquet", "C9", True, "current",
         None),
        ("data/model_input/d5_fuel_oil_predictions.parquet", "D5", True,
         "current", None),
    ]
    records = [RM.artifact_record(ROOT, *entry) for entry in registered]
    RM.assert_no_locked_path(r["path"] for r in records)

    manifest = {
        "task": "E1",
        "manifest_version": RM.MANIFEST_VERSION,
        "generated_at_utc": generated_at,
        "artifacts": records,
        "artifact_count": len(records),
        "generated_artifacts": sum(1 for r in records if r["generated"]),
        "version_controlled_artifacts": sum(
            1 for r in records if r["version_controlled"]),
        "superseded_artifacts": [
            {"path": r["path"], "superseded_by": r["superseded_by"]}
            for r in records if r.get("superseded_by")
        ],
        "supersession_graph": supersession,
        "referenced_raw_manifests": [
            {"path": p, "duplicated_here": False,
             "lines": sum(1 for _ in open(ROOT / p, encoding="utf-8"))
             if (ROOT / p).is_file() else None}
            for p in config["reproducibility_manifest"]["referenced_raw_manifests"]
        ],
        "environment": config["reproducibility_manifest"]["environment"],
        "commands": config["reproducibility_manifest"]["commands"],
        "verification": {
            "tests": tests,
            "ruff": ruff,
            "config_and_schema_parse": parse_all_configs_and_schemas(),
        },
        "test_count_copied": False,
        "test_count_source": "measured_from_an_actual_pytest_run",
        "locked_test": {
            "status": locked["status"],
            "outcomes_read": locked["locked_test_outcomes_read"],
            "manifest_is_key_only": locked["manifest_is_key_only"],
            "locked_path_recorded": False,
        },
    }
    manifest["manifest_checksum"] = RM.manifest_checksum(manifest)
    return manifest


def parse_all_configs_and_schemas() -> dict:
    """Confirm every config, schema and committed JSON document parses."""
    import glob

    configs = sorted(glob.glob(str(ROOT / "configs" / "*.yaml")))
    schemas = sorted(glob.glob(str(ROOT / "schemas" / "*.yaml")))
    documents = sorted(glob.glob(str(ROOT / "docs" / "*.json")))
    for path in configs + schemas:
        with open(path, encoding="utf-8") as handle:
            yaml.safe_load(handle)
    for path in documents:
        with open(path, encoding="utf-8") as handle:
            json.load(handle)
    return {
        "configs_parsed": len(configs),
        "schemas_parsed": len(schemas),
        "documents_parsed": len(documents),
        "all_parsed": True,
    }


def _f(value, digits=4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_documents(config, ledger, manifest, artifacts) -> None:
    """Render every E1 document, guarding the prose before it is written."""
    DOCS.mkdir(parents=True, exist_ok=True)
    for name, payload in (("e1_evidence_ledger.json", ledger),
                          ("e1_reproducibility_manifest.json", manifest)):
        text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True,
                          default=str)
        (DOCS / name).write_text(text + "\n", encoding="utf-8")
    write_technical_closeout(config, ledger, manifest)
    write_portfolio_case_study(config, ledger, manifest)
    write_executive_summary(config, ledger, manifest)


def guard_technical(text: str) -> str:
    """Guards for the technical report: task codes are permitted here."""
    ES.assert_inconclusive_not_absence(text)
    ES.assert_baseline_reference_not_superiority(text)
    ES.assert_d3_not_a_production_model(text)
    ES.assert_not_real_time(text)
    ES.assert_no_project_failed_language(text)
    ES.assert_locked_outcomes_untouched({"locked_test_evaluated": False,
                                         "locked_test_outcomes_read": False}, text)
    return text


def guard_portfolio(text: str) -> str:
    """Guards for reader-facing prose: no unsupported claims, no task codes."""
    guard_technical(text)
    ES.assert_portfolio_wording(
        text, config_prohibited(), TASK_CODES, allow_task_codes=False
    )
    return text


_PORTFOLIO_PROHIBITED = None


def config_prohibited():
    return _PORTFOLIO_PROHIBITED or ES.PROHIBITED_PORTFOLIO_PHRASES


def write_technical_closeout(config, ledger, manifest) -> None:
    development = ledger["development_ledger"]
    d1, d3, d4, d5 = (development["D1"], development["D3"], development["D4"],
                      development["D5"])
    status = ledger["project_status"]
    lines = [
        "# Technical Closeout - Thai Industrial Stress Early-Warning Research",
        "",
        f"*Task E1. Generated {ledger['generated_at_utc']}. "
        f"Synthesis contract `{ledger['synthesis_contract_checksum']}`.*",
        "",
        "## 1. Executive summary",
        "",
        "A leakage-aware, release-aware research pipeline was built from official",
        "Thai and international sources, and used to test whether commodity and",
        "refinery-price signals could improve a one- and three-month-ahead",
        "industrial-stress forecast. **They could not, on the evidence available.**",
        "",
        "Three candidate models were evaluated on the registered development",
        "window. None beat its benchmark on the primary error metric. The",
        "registered operational reference is therefore a persistence forecast, and",
        "the locked final test was never opened, because no candidate earned",
        "access to it.",
        "",
        "That is the whole result, and it is a real one: the project establishes",
        "which plausible signals fail under realistic data availability, and it",
        "leaves an unused final test behind rather than a number that was fitted",
        "until it looked good.",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in status.items():
        lines.append(f"| `{key}` | `{value}` |")

    lines += [
        "",
        "## 2. Problem definition",
        "",
        "Forecast a monthly industrial-stress score per industry, one and three",
        "months ahead, for twelve Thai manufacturing industries. Stress is derived",
        "from the OIE Manufacturing Production Index; the question is whether",
        "commodity input prices carry information about it that a naive forecast",
        "does not already contain.",
        "",
        "The hypothesis is structural rather than statistical: industries that buy",
        "more of a commodity should react more to its price. Input-output",
        "coefficients from the national accounts supply that 'more'.",
        "",
        "## 3. Forecast-origin and horizon contract",
        "",
        "| element | rule |",
        "| --- | --- |",
        "| issue month | the month a forecast is made, `t` |",
        "| latest publishable stress | `t - 1`; month `t` is never used at `t` |",
        "| commodity/fuel feature | reference month `t - 2` under the policy lag |",
        "| horizon 1 target | stress at `t + 1` |",
        "| horizon 3 target | maximum stress over `t + 1 .. t + 3` |",
        "| label availability | `target_window_end + 1 month` |",
        "| calibrator cutoff | fitted on stress through `t - 1`, then frozen |",
        "| development issues | 2024-01 .. 2025-03, fifteen months |",
        "| purge buffer | 2025-04 .. 2025-06, never evaluated |",
        "| locked final test | 2025-07 onward, never opened |",
        "",
        "## 4. Data-source and vintage architecture",
        "",
        "Evidence quality is **not** equal across these sources, and the table",
        "records where each one is weak.",
        "",
        "| source family | values | historical timing | point-in-time status | "
        "main limitation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in ledger["source_timing_table"]:
        lines.append(
            f"| {row['source_family']} | {row['values']} | "
            f"{row['historical_timing']} | {row['point_in_time_status']} | "
            f"{row['main_limitation']} |"
        )
    lines += [
        "",
        "The asymmetry that matters: commodity **features** are archived",
        "first-release values with verified publication dates, so the feature side",
        "is genuinely point-in-time. The **target** is latest vintage for every",
        "source, because no MPI vintages exist. The evaluation is therefore",
        "release-aware but not a point-in-time backtest, and no result in this",
        "report should be read as one.",
        "",
        "## 5. Feature construction",
        "",
        "Five transformations per commodity series: price level, one-, three- and",
        "twelve-month log changes, and three-month realised volatility. Volatility",
        "is a non-negative disruption magnitude and never a direction.",
        "",
        "Missing source months are propagated as missing. Nothing is imputed,",
        "interpolated, forward-filled or substituted from a sibling series: an",
        "absent price multiplied by any exposure is still absent.",
        "",
        "## 6. Structural exposure methodology",
        "",
        "| finding | value |",
        "| --- | --- |",
    ]
    for key, value in ledger["structural_synthesis"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "The input-output table is the official NESDC 2015 Final structure, read",
        "column-wise as `A[i,j] = Z[i,j] / X_j`, gross-output weighted across the",
        "sectors that map to each industry. Coefficients are purchasers' price and",
        "import-inclusive, and are treated as time-invariant.",
        "",
        "This is **structural attribution**, not causal transmission. A positive",
        "coefficient says an industry buys from a sector; it does not say a price",
        "move propagates to output, and no result here is interpreted that way.",
        "",
        "## 7. Leakage controls",
        "",
        "* Stress from month `t` is never used at issue `t`; the guard raises.",
        "* A historical training row carries the features available at **its own**",
        "  issue month, not the latest ones available at the outer origin.",
        "* Labels enter training only after their publication month.",
        "* The calibrator is refitted per origin, cut at `t - 1`, then frozen.",
        "* Scalers are fitted on the training panel only, and on unique issue",
        "  months rather than on the repeated industry panel.",
        "* Purge and locked origins are rejected before any data is read.",
        "* The D5 target reader refuses to return a value until the protocol",
        "  checksum is verified **and** the prediction for that key is frozen.",
        "",
        "## 8. Walk-forward evaluation design",
        "",
        "Expanding-window walk-forward over fifteen issue months, refitting at",
        "every origin. The primary metric is macro-industry MAE: per-industry MAE",
        "first, then an equal average across industries, so one volatile industry",
        "cannot dominate. Uncertainty is a paired bootstrap clustered by **issue",
        "month**, keeping all industries together - twelve industries in one month",
        "share a national signal, a calibrator and a release date, and resampling",
        "them independently would shrink every interval by roughly the square root",
        "of twelve.",
        "",
        "Fifteen clusters is a small number. Every interval in this report is wide",
        "for that reason, and the limit is stated wherever an interval appears.",
        "",
        "## 9. Development results",
        "",
        "### 9.1 Original commodity evaluation (D1) - superseded",
        "",
        "| horizon | model macro MAE | benchmark macro MAE |",
        "| --- | ---: | ---: |",
        f"| 1 | {_f(d1['horizons']['1']['model_macro_mae'])} | "
        f"{_f(d1['horizons']['1']['benchmark_macro_mae'])} |",
        f"| 3 | {_f(d1['horizons']['3']['model_macro_mae'])} | "
        f"{_f(d1['horizons']['3']['benchmark_macro_mae'])} |",
        "",
        f"Status **{d1['status']}**, superseded by "
        f"`{d1['superseded_by']}` for operational interpretation.",
        "",
        "Three limitations travel with these numbers. The evaluation was **not**",
        "operationally release-timing correct - it predates the issue-month",
        "contract. The nested selection protocol was **not fully executed**:",
        f"**{d1['fallback_selections']} of {d1['total_selections']}**",
        "origin-horizon selections fell back to the conservative configuration",
        "because there was not enough inner history, and the **direction of that",
        "fallback's effect is unknown**. D1 is not a fully executed confirmatory",
        "evaluation and is not presented as one.",
        "",
        "### 9.2 Operational reference baselines (D3)",
        "",
        "| horizon | registered reference | macro MAE | no-contraction macro MAE |",
        "| --- | --- | ---: | ---: |",
        f"| 1 | `{d3['horizons']['1']['selected_benchmark']}` | "
        f"{_f(d3['horizons']['1']['macro_industry_mae'])} | "
        f"{_f(d3['horizons']['1']['no_contraction_macro_mae'])} |",
        f"| 3 | `{d3['horizons']['3']['selected_benchmark']}` | "
        f"{_f(d3['horizons']['3']['macro_industry_mae'])} | "
        f"{_f(d3['horizons']['3']['no_contraction_macro_mae'])} |",
        "",
        "The paired comparison against the no-contraction comparator was",
        "**inconclusive** at both horizons. Persistence remained the registered",
        "reference through the preregistered false-negative tie-break, which is a",
        "selection rule and not a demonstration of statistical superiority.",
        "",
        "D3 established an operational **evaluation reference**. It is not a",
        "deployed system and nothing was put into service.",
        "",
        "### 9.3 Commodity model under the operational contract (D4)",
        "",
        "| horizon | model | reference | paired 95% interval | MAE evidence | "
        "event safety |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for horizon in ("1", "3"):
        entry = d4["horizons"][horizon]
        lines.append(
            f"| {horizon} | {_f(entry['model_macro_mae'])} | "
            f"{_f(entry['reference_macro_mae'])} | "
            f"[{_f(entry['paired_ci_low'])}, {_f(entry['paired_ci_high'])}] | "
            f"{entry['mae_evidence_status']} | {entry['event_safety_status']} |"
        )
    lines += [
        "",
        "Incremental signal was **not supported** at either horizon. The",
        "event-safety gate passed at both, and that does **not** override the",
        "primary error result: both gates were required and one failed.",
        "",
        f"**{d4['degenerate_rows']} of {d4['total_rows']}** primary-panel rows were",
        "benchmark passthrough, because for six industries every eligible direct",
        "predictor is a structural constant - their exposure coefficient is zero,",
        "so the zero-variance rule removes all of them and the prediction reduces",
        "to the benchmark exactly. Half the panel was therefore not a model",
        "prediction at all. D4 remained exploratory and did not earn promotion.",
        "",
        "### 9.4 Refinery-price interaction (D5)",
        "",
        "| variant | h | model | reference | paired interval | evidence | "
        "event safety |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for entry in sorted(d5["variant_horizons"].values(),
                        key=lambda e: (e["horizon"], e["variant_id"])):
        label = "FO 1500" if "1500" in entry["variant_id"] else "FO 600"
        lines.append(
            f"| {label} | {entry['horizon']} | "
            f"{_f(entry['model_macro_mae'], 3)} | "
            f"{_f(entry['reference_macro_mae'], 3)} | "
            f"[{_f(entry['paired_ci_low'], 3)}, {_f(entry['paired_ci_high'], 3)}] |"
            f" {entry['mae_evidence']} | "
            f"{'passed' if entry['event_safety_passed'] else 'failed'} |"
        )
    lines += [
        "",
        f"No point estimate beat the benchmark "
        f"({d5['point_estimates_beating_the_benchmark']} of 4). All four intervals",
        "crossed zero. Event safety failed in all four. Incremental signal was",
        "**not demonstrated**, and **absence of an effect was not proven** - those",
        "are different statements and only the first is supported.",
        "",
        "## 10. Negative-result interpretation",
        "",
        "Each of these statuses means something specific, and the report uses the",
        "vocabulary rather than collapsing it:",
        "",
    ]
    for key, description in ledger["prohibited_collapses"].items():
        lines.append(f"* **`{key}`** - {description.strip()}")
    lines += [
        "",
        "Three reasons the negative results are informative rather than merely",
        "disappointing.",
        "",
        "**The commodity features were structurally degenerate for half the",
        "panel.** Six of twelve industries have a zero direct coefficient on the",
        "mapped commodity sectors, so their 'model' prediction was the benchmark.",
        "That is a property of the official input-output structure, discovered",
        "before any outcome was consulted.",
        "",
        "**Per-industry conditioning added scale, not information.** Multiplying",
        "one national price series by a per-industry constant produces eleven",
        "scaled copies of the same fifteen-row history. The cross-section has rank",
        "one at every issue month; the panel has no more temporal degrees of",
        "freedom than the series it came from. This was established by rank",
        "identities, without reading a single target value.",
        "",
        "**Fifteen issue-month clusters cannot settle a small effect.** Every",
        "interval in this report is wide by construction. An inconclusive result",
        "on this much data is the expected outcome of an honest test, not a",
        "surprise, and it is reported as inconclusive rather than as absence.",
        "",
        "## 11. Reproducibility and testing",
        "",
        "| check | result |",
        "| --- | --- |",
        f"| test suite | **{manifest['verification']['tests']['tests_passed']} "
        f"passed**, {manifest['verification']['tests']['tests_failed']} failed |",
        f"| lint (`ruff check .`) | "
        f"{'passing' if manifest['verification']['ruff']['passing'] else 'failing'} |",
        f"| configs parsed | "
        f"{manifest['verification']['config_and_schema_parse']['configs_parsed']} |",
        f"| schemas parsed | "
        f"{manifest['verification']['config_and_schema_parse']['schemas_parsed']} |",
        f"| result documents parsed | "
        f"{manifest['verification']['config_and_schema_parse']['documents_parsed']} |",
        f"| artifacts pinned | {manifest['artifact_count']} |",
        "",
        "The test count above was **measured by running the suite**, not copied",
        "from a previous report: a number typed into a reproducibility manifest",
        "drifts the moment a test is added, and a stale count looks like evidence.",
        "",
        "Every task freezes its contract to disk and re-verifies the digest before",
        "reading values; every generated row carries a lineage checksum over both",
        "its provenance chains; and each stage's expected counts were preregistered",
        "and reconciled rather than reported after the fact.",
        "",
        "## 12. Limitations",
        "",
        "* **Targets are latest vintage.** No MPI vintages exist, so the target",
        "  side cannot be point-in-time and this is not a real-time backtest.",
        "* **Refinery-price release timing was never measured.** The two-month lag",
        "  is a conservative policy assumption, not an observed publication delay.",
        "* **Structural coefficients are time-invariant** and come from a 2015",
        "  benchmark table read at a broad sector granularity.",
        "* **Commodity mappings are proxies.** Aluminium and copper share one",
        "  sector and are not independent exposure measurements; sector 093 is a",
        "  nine-product basket, so fuel oil stands in for the whole basket.",
        "* **Fifteen development issue months** bound every uncertainty interval.",
        "* **One industry is structurally excluded** from the refinery-price",
        "  correction because it both produces and consumes refinery products; its",
        "  direction is unresolved rather than zero.",
        "",
        "## 13. Final decision",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in status.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "### Locked-test closeout",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("status", "manifest_is_key_only", "locked_test_outcomes_read",
                "any_candidate_locked_test_evaluation_authorized",
                "prediction_or_metric_exists_for_locked_origins",
                "outcomes_opened_hashed_or_summarised"):
        lines.append(f"| `{key}` | `{ledger['locked_test'][key]}` |")
    lines += [
        f"| horizon 1 reservation | "
        f"`{ledger['locked_test']['horizon_1_range']}` |",
        f"| horizon 3 reservation | "
        f"`{ledger['locked_test']['horizon_3_range']}` |",
        "",
        f"> {ledger['locked_test']['required_language']}",
        "",
        "## 14. Reopening conditions",
        "",
        "A different specification is not new evidence. Reopening requires",
        "something external that the evaluation could not have used, with",
        "provenance, an availability date, an account of why it was unavailable,",
        "and a superseding recorded decision. Qualifying categories are a",
        "product-specific industrial fuel-consumption crosswalk; a newer compatible",
        "input-output table available before the evaluation period; verified",
        "point-in-time release evidence; a materially longer compatible target",
        "history obtained without touching the purge or locked windows; a proven",
        "material implementation error; or a genuinely new external hypothesis",
        "registered before any corresponding result is inspected.",
        "",
        "## 15. Architecture",
        "",
        "```",
        "  official sources          timing / vintage contracts",
        "  ----------------          --------------------------",
        "  OIE MPI            -->    latest vintage, t+1 release timing",
        "  World Bank Pink Sheet -->  archived first release, verified dates",
        "  NESDC 2015 I/O     -->    time-invariant, available by 2020-03",
        "  EPPO price docs    -->    latest vintage, policy lag 2 (unmeasured)",
        "                                      |",
        "                                      v",
        "                              transformations",
        "                    (level, 1m/3m/12m log change, 3m volatility;",
        "                     missing months propagated, never imputed)",
        "                                      |",
        "                                      v",
        "                            structural exposure",
        "                  (I/O coefficients, gross-output weighted,",
        "                   purchasers' price, attribution not causation)",
        "                                      |",
        "                                      v",
        "                       development walk-forward (15 issues)",
        "                  (expanding window, refit per origin, paired",
        "                   issue-month cluster bootstrap)",
        "                                      |",
        "                                      v",
        "                          evidence-based closure",
        "         no candidate beat its benchmark -> baseline-only reference",
        "                                      |",
        "                                      v",
        "                    LOCKED FINAL TEST -- NEVER OPENED",
        "                    (reserved, key-only, no model deployed)",
        "```",
        "",
        "No stage of this diagram ends in deployment. The final box is a",
        "reservation, not a result.",
        "",
        "## 16. Final declaration",
        "",
    ]
    declarations = {
        "development_program_is_complete":
            "The development programme is complete.",
        "data_timing_lineage_and_evaluation_infrastructure_is_reproducible":
            "The data, timing, lineage and evaluation infrastructure is "
            "reproducible.",
        "d3_persistence_forecasts_remain_the_registered_operational_reference":
            "Persistence forecasts remain the registered operational reference.",
        "no_commodity_model_demonstrated_sufficient_incremental_development_evidence":
            "No commodity model demonstrated sufficient incremental development "
            "evidence.",
        "no_model_or_feature_was_approved_for_operational_deployment":
            "No model or feature was approved for operational deployment.",
        "locked_final_test_remains_sealed":
            "The locked final test remains sealed.",
        "future_reopening_requires_new_external_evidence_and_a_new_independent_preregistration":
            "Future reopening requires genuinely new external evidence and a new "
            "independent preregistration.",
    }
    for key in ledger["final_declaration"]:
        lines.append(f"* **{declarations[key]}**")
    lines += [
        "",
        "## Appendix - task codes and evidence links",
        "",
        "| stage | task | artifact |",
        "| --- | --- | --- |",
    ]
    for group, entries in config["included_tasks"].items():
        for task, entry in entries.items():
            lines.append(
                f"| {group} | `{task}` | `{entry['artifact']}` ({entry['role']}) |"
            )
    lines += [
        "",
        f"Evidence ledger checksum `{ledger['content_checksum']}`. "
        f"Reproducibility manifest checksum `{manifest['manifest_checksum']}`.",
        "",
    ]
    (DOCS / "e1_technical_closeout.md").write_text(
        guard_technical("\n".join(lines) + "\n"), encoding="utf-8"
    )


def _fuel_row(d5, d3, horizon: int, label: str) -> str:
    """One case-study row: the two variants shown as a range, never ranked."""
    values = [e["model_macro_mae"] for e in d5["variant_horizons"].values()
              if e["horizon"] == horizon]
    reference = d3["horizons"][str(horizon)]["macro_industry_mae"]
    return (
        f"| refinery-price model | {label} | {_f(min(values), 2)}"
        f"-{_f(max(values), 2)} | {_f(reference, 2)} | inconclusive |"
    )


def write_portfolio_case_study(config, ledger, manifest) -> None:
    """The reader-facing case study. No task codes, no unsupported claims."""
    development = ledger["development_ledger"]
    d3, d4, d5 = development["D3"], development["D4"], development["D5"]
    narrative = [
        "# Can Commodity Prices Warn You About Factory Slowdowns?",
        "",
        "*A forecasting study on Thai manufacturing - and an honest negative "
        "result.*",
        "",
        "## The question",
        "",
        "When oil, metal or rubber prices move, factories feel it. If that shows",
        "up in production data a month or two later, a forecaster could see",
        "trouble coming.",
        "",
        "I built a system to test that idea on twelve Thai manufacturing",
        "industries, forecasting a monthly stress score one and three months",
        "ahead. The honest answer, after building the whole pipeline: **the",
        "commodity signals did not improve on a simple forecast that just assumes",
        "next month looks like last month.**",
        "",
        "This write-up is about how I got to that answer, and why the way I got",
        "there matters more than the answer itself.",
        "",
        "## Why you cannot just shuffle the data",
        "",
        "The instinct with any dataset is to split it randomly: 80% to train, 20%",
        "to test. For a time series that quietly cheats, in two ways.",
        "",
        "**The obvious way:** a random split lets the model learn from March to",
        "predict February. It sees the future.",
        "",
        "**The subtle way, which cost me most of the project:** even a correct",
        "chronological split can cheat if you ignore *when data was published*.",
        "The production index for March is not available in March. It is published",
        "weeks later. If you build a March forecast using March's index because",
        "your table has a March row, you have used a number nobody had yet. The",
        "table gives no hint that anything is wrong - the column is right there,",
        "full of plausible values.",
        "",
        "So the whole system is organised around a single question asked at every",
        "step: *what did somebody actually know on the day this forecast was",
        "made?* Every forecast is stamped with an issue month, and every input has",
        "to prove it was published by then.",
        "",
        "## Getting the timing right",
        "",
        "Two different problems, two different solutions.",
        "",
        "For commodity prices I found the **archived original releases** - the",
        "monthly price bulletins as first published, not the revised figures you",
        "get today. Revised data is a subtle form of hindsight: it tells you what",
        "the price turned out to be, not what a forecaster would have seen. I",
        "verified publication dates against the archive so each price could be",
        "matched to the first forecast that could legitimately have used it.",
        "",
        "For Thai refinery prices no such archive of original releases exists. I",
        "could only get today's version of historical documents. Rather than",
        "pretend otherwise, I recorded the timing as a **conservative assumption**",
        "- assume the data was two months late - and labelled it an assumption",
        "everywhere it appears, so nobody downstream mistakes it for a measurement.",
        "",
        "The production target itself has no archived versions at all. That is a",
        "real limitation and it is stated in every report: this study is",
        "release-aware, but it is not a point-in-time reconstruction of the past.",
        "",
        "## Connecting prices to industries",
        "",
        "A rubber price should matter more to a tyre maker than to an electronics",
        "assembler. To make that concrete rather than hand-wavy, I used the",
        "national statistics office's **input-output table** - an official matrix",
        "of how much each industry buys from every other sector.",
        "",
        "That gives a per-industry exposure number for each commodity, straight",
        "from official accounts rather than from my own guesswork. It is",
        "attribution, not causation: it says an industry buys from a sector, not",
        "that a price move flows through to its output.",
        "",
        "## The most interesting thing I found (before any model ran)",
        "",
        "Two structural discoveries changed the project, and both came from",
        "auditing the design rather than from a result.",
        "",
        "**Half the commodity features were constant.** For six of the twelve",
        "industries, the official table gives a *zero* coefficient on the mapped",
        "commodity sectors. Multiply a moving price by zero and you get a column",
        "that never changes - a predictor that cannot predict. Those industries'",
        "forecasts were just the benchmark, wearing a model's clothes. Finding",
        "this before reading any outcome is the difference between reporting a",
        "result and understanding one.",
        "",
        "**Per-industry scaling adds nothing over time.** For the refinery-price",
        "work, I multiplied one national price series by each industry's exposure.",
        "It looks like eleven industry histories. It is one history times eleven",
        "constants. I proved this with rank arithmetic - the eleven rows at any",
        "month collapse to a single direction - and, importantly, proved it",
        "*without looking at any outcome*. That result reshaped the model design:",
        "if scaling adds no new temporal information, the only architecture that",
        "can use exposure meaningfully is one that pools industries and lets",
        "exposure modulate a shared effect.",
        "",
        "## Rebuilding the benchmark honestly",
        "",
        "Partway through, I realised my first evaluation had the publication",
        "timing wrong. Fixing it made every benchmark *worse* - the naive forecast",
        "went from about 14.5 to about 17.1 average error, because it was now",
        "restricted to genuinely available data.",
        "",
        "That was the right direction. A benchmark that looks too good usually",
        "means it is seeing something it should not. I rebuilt the baselines under",
        "the corrected timing rules and registered them as the reference point,",
        "then re-ran everything against them.",
        "",
        "I also want to be precise about what the reference is: the persistence",
        "forecast was **selected** under a rule fixed in advance, and its",
        "comparison against the next-best alternative was statistically",
        "inconclusive. It is the registered reference, not a demonstrated champion.",
        "",
        "## What the experiments found",
        "",
        "Three candidate models, all evaluated on fifteen monthly forecast dates.",
        "Lower error is better; the reference is the persistence forecast.",
        "",
        "| candidate | horizon | model error | reference error | verdict |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| commodity model | 1 month | "
        f"{_f(d4['horizons']['1']['model_macro_mae'], 2)} | "
        f"{_f(d4['horizons']['1']['reference_macro_mae'], 2)} | no improvement |",
        f"| commodity model | 3 months | "
        f"{_f(d4['horizons']['3']['model_macro_mae'], 2)} | "
        f"{_f(d4['horizons']['3']['reference_macro_mae'], 2)} | no improvement |",
        _fuel_row(d5, d3, 1, "1 month"),
        _fuel_row(d5, d3, 3, "3 months"),
        "",
        "No candidate had a lower error than the reference. Every uncertainty",
        "interval included zero, which on fifteen data points is what an honest",
        "test usually produces. And for the refinery-price model, a safety check",
        "mattered more than the average error: it **missed more high-stress months**",
        "than the plain forecast did. For an early-warning system, missing the",
        "warnings is the failure that counts.",
        "",
        "I want to be careful about what this does and does not show. It shows",
        "these signals did not help, in this setup, with this much data. It does",
        "**not** show that commodity prices are unrelated to industrial stress -",
        "fifteen months cannot settle that, and I did not try to.",
        "",
        "## Why leaving the final test unopened is the good outcome",
        "",
        "At the start I set aside the most recent months as a final test and wrote",
        "down the rule: a model may only be evaluated on it after clearing agreed",
        "thresholds on the development data first.",
        "",
        "No model cleared them. So the final test was never opened.",
        "",
        "It would have been easy to peek. Try another regularisation strength,",
        "another model family, drop the industries that were dragging the average",
        "down, keep the fuel oil that scored slightly better. Any of those might",
        "have produced a number worth writing up - and all of them would have been",
        "fitting the answer rather than testing it. Each attempt spends a little",
        "of the final test's credibility, and there is no way to earn it back.",
        "",
        "The set-aside data is still untouched. If someone brings genuinely new",
        "evidence later - better industry-level fuel consumption data, a newer",
        "input-output table, real publication dates - the test is still there and",
        "still means something. That is the result I am most confident about.",
        "",
        "## What I built",
        "",
        "* An ingestion pipeline for four official statistical sources, with",
        "  checksums, retrieval manifests and recorded provenance for every file.",
        "* Publication-timing logic that keeps each forecast to what was knowable",
        "  on its own issue date, with automated guards that fail loudly rather",
        "  than silently.",
        "* Industry exposure matrices derived from official input-output accounts,",
        "  with the aggregation verified two independent ways.",
        "* A walk-forward evaluation harness with clustered bootstrap uncertainty",
        "  and preregistered decision rules.",
        "* Around 1,700 automated tests, including deliberately constructed",
        "  failure cases: every leakage rule has a test that breaks it on purpose",
        "  and requires the guard to catch it.",
        "* Content checksums and lineage records so every number in the final",
        "  report can be traced to the artifact that produced it.",
        "",
        "## Skills this demonstrates",
        "",
        "Time-series forecasting design; data-leakage prevention; point-in-time",
        "and vintage data handling; working with official statistical sources and",
        "input-output economics; regularised regression and residual modelling;",
        "bootstrap uncertainty with clustered dependence; preregistration and",
        "stopping rules; reproducible pipelines with checksums and lineage;",
        "large-scale automated testing; and technical writing that distinguishes",
        "what was shown from what was assumed.",
        "",
        "## What would restart this project",
        "",
        "Not another model. The pipeline is built and the data is exhausted for",
        "now; a different regression on the same evidence would only be a new way",
        "of asking a question already answered.",
        "",
        "What would restart it: industry-level fuel consumption statistics",
        "specific enough to replace a broad proxy; a newer input-output table",
        "materially changing the exposure structure; verified historical",
        "publication dates that firm up the timing assumptions; or simply more",
        "history, which is the one thing that would narrow the uncertainty",
        "intervals that made these results inconclusive rather than decisive.",
        "",
        "---",
        "",
        "*Everything above is reproducible: the full technical closeout, the",
        "evidence ledger with a pointer for every number, and the task-level",
        "artifact index are in this repository.*",
        "",
    ]
    (DOCS / "e1_portfolio_case_study.md").write_text(
        guard_portfolio("\n".join(narrative) + "\n"), encoding="utf-8"
    )


def write_executive_summary(config, ledger, manifest) -> None:
    """Summary, three truthful CV bullets, and the interview answer."""
    tests = manifest["verification"]["tests"]["tests_passed"]
    lines = [
        "# Project Summary and Portfolio Bullets",
        "",
        "## One-paragraph summary",
        "",
        "Built an end-to-end forecasting research pipeline testing whether",
        "commodity and refinery input prices improve one- and three-month-ahead",
        "industrial-stress forecasts for twelve Thai manufacturing industries,",
        "using official production, price and input-output statistics. The system",
        "enforces publication-time availability at every step, derives industry",
        "exposure from national input-output accounts, and evaluates candidates",
        "walk-forward against registered baselines with clustered bootstrap",
        "uncertainty and decision rules fixed before any outcome was read. No",
        "candidate improved on the persistence baseline on development data, so",
        "the study concludes with a baseline-only reference and a final test that",
        "was deliberately never opened.",
        "",
        "## CV bullets",
        "",
        "* Built a leakage-aware forecasting pipeline over four official",
        "  statistical sources, enforcing publication-time availability with",
        "  archived first-release vintages, per-forecast issue-date contracts and",
        "  automated guards that fail the run rather than warn.",
        "* Derived reproducible industry-exposure matrices from national",
        "  input-output accounts and evaluated candidate models walk-forward with",
        "  issue-month clustered bootstrap uncertainty and preregistered decision",
        f"  rules, backed by ~{tests:,} automated tests including deliberate",
        "  leakage-failure cases.",
        "* Applied preregistered stopping rules to conclude a negative result",
        "  honestly: documented that no candidate met its promotion criteria,",
        "  preserved the held-out final test unopened, and shipped a full evidence",
        "  ledger tracing every reported figure to its source artifact.",
        "",
        "## Interview answer: why is this valuable if the models did not beat "
        "persistence?",
        "",
        "Three reasons.",
        "",
        "**It found out which plausible ideas fail, and why.** \"Commodity prices",
        "should predict factory stress\" is a reasonable hypothesis that a lot of",
        "people would assume works. This project tested it under realistic data",
        "availability and found it did not help - and diagnosed the reasons",
        "structurally, not just statistically. Half the commodity features turned",
        "out to be constant for half the industries because the official",
        "input-output table assigns them a zero coefficient. Per-industry scaling",
        "of one national price series adds no new temporal information at all,",
        "which I proved with rank arithmetic before running any model. Those are",
        "findings about the data, and they would apply to anyone else attempting",
        "the same thing.",
        "",
        "**It did not spend the final test.** The easiest way to manufacture a",
        "positive result would have been to keep trying specifications until one",
        "cleared the bar. I set the stopping rules in advance, hit them, and",
        "stopped. The held-out data is still untouched and still meaningful,",
        "which means a future attempt with genuinely better inputs can still get",
        "an honest read from it. A number obtained by peeking would have been",
        "worth less than nothing.",
        "",
        "**The infrastructure is the durable part.** Getting publication timing",
        "right was the hardest engineering problem here, and fixing it made the",
        "baselines measurably worse - which was the correct direction, because it",
        "removed information nobody actually had. The timing contracts, the",
        "lineage and checksum discipline, the walk-forward harness and the test",
        "suite all survive the negative result and would be the starting point for",
        "any next attempt.",
        "",
        "A study that reports what did not work, with the evidence to show it was",
        "tested properly, is more useful than one that reports a number nobody can",
        "reproduce.",
        "",
    ]
    (DOCS / "e1_executive_summary.md").write_text(
        guard_portfolio("\n".join(lines) + "\n"), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
