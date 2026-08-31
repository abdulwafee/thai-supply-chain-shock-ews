"""Task C11-R1 — specification-correction and outcome-access governance closure.

Corrects the formal methodological status of C11 without changing or suppressing
its mathematical findings, and issues a bounded D5 authorization if every closure
gate passes.

Two facts are kept apart throughout:

  1. The architecture decision is REPRODUCIBLE without any D-series result.
  2. The original C11 EXECUTION was not outcome-blind.

C11-R1 FITS NOTHING. No target join, no model, no performance, no channel
selection, no locked test, and the D3 result artifact is never reopened. The C11
record is preserved byte-for-byte; this is an overlay.

    docs/c11r1_governance_decision.{md,json}
    docs/c11_architecture_decision.errata.md
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

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.features import fuel_oil_development_matrix as DM  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_architecture_decision as AD  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_architecture_governance as GV  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_candidate_designs as CD  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_information_flow as IF  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "fuel_oil_architecture_governance.yaml"
C11_CONFIG = ROOT / "configs" / "fuel_oil_modeling_architecture.yaml"
C11_DECISION_JSON = DOCS / "c11_architecture_decision.json"
C11_DECISION_MD = DOCS / "c11_architecture_decision.md"
C11_PROTOCOL_MD = DOCS / "c11_architecture_decision_protocol.md"
C10_AUDIT = DOCS / "c10_design_matrix_audit.json"
C9_PHASE_A = DOCS / "c9_sector093_exposure_decision.json"
C8_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"

#: Source files whose read call sites are statically inspected. Includes the C11
#: chain, because the audit is about what the DECISION depends on.
INSPECTED_SOURCES = (
    ROOT / "scripts" / "run_c11_architecture_decision.py",
    ROOT / "scripts" / "run_c11r1_governance_closure.py",
    ROOT / "src" / "thai_supply_chain_ews" / "structure"
    / "fuel_oil_candidate_designs.py",
    ROOT / "src" / "thai_supply_chain_ews" / "structure"
    / "fuel_oil_architecture_decision.py",
    ROOT / "src" / "thai_supply_chain_ews" / "structure"
    / "fuel_oil_architecture_governance.py",
    ROOT / "src" / "thai_supply_chain_ews" / "structure"
    / "fuel_oil_information_flow.py",
)

CHANNEL_BY_VARIANT = {
    "fo600_direct_sector093": "eppo_fo600_channel",
    "fo1500_direct_sector093": "eppo_fo1500_channel",
}

#: Arbitrary, fabricated, and isolated. Never written anywhere, never read from
#: an artifact, and used only to show the reconstruction does not move.
FABRICATED_METRICS = {
    "macro_industry_mae": 999.0,
    "rmse": -17.5,
    "high_stress_outcome_rate": 0.42,
    "channel_performance_fo600": 1.0,
    "channel_performance_fo1500": 0.0,
}

CORRECTION_NARRATIVE = " ".join((
    "The original gate asked whether the prohibited preprocessing forces the",
    "entire stacked matrix to rank five. It does not, because the centred",
    "exposures carry both signs and +Xtilde and -Xtilde span two directions. The",
    "question the gate should have asked is whether per-industry standardisation",
    "preserves continuous exposure magnitude within an industry. It does not:",
    "standardize(E_g X) equals standardize(X) when E_g is positive and",
    "-standardize(X) when it is negative, so only the sign survives. No",
    "tolerance and no threshold moved; the gate was measuring the wrong",
    "quantity, and the quantity was corrected after the result was visible.",
))

INCIDENT_NARRATIVE = " ".join((
    "During C11 a development metric artifact was opened. The benchmark contract",
    "name it was opened for was already available in non-result documentation,",
    "so the file was not required. No metric value entered the C11 configuration,",
    "the candidate matrices, any checksum, the gate arithmetic or the",
    "architecture selection, and the decision reproduces exactly without it. A",
    "guard added afterwards prevents recurrence. It does not alter what happened,",
    "and a clean rerun does not restore an outcome-blind execution history.",
))


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def byte_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Reproduction of C11's mathematics, without any D-series path
# ---------------------------------------------------------------------------
def source_time_matrix(c8_rows, channel_id, reference_months, columns) -> list:
    indexed = {
        (row["channel_id"], row["reference_month"], row["transformation_id"]):
            (None if pd.isna(row["feature_value"]) else float(row["feature_value"]))
        for row in c8_rows
    }
    matrix = []
    for month in reference_months:
        row = []
        for column in columns:
            value = indexed.get((channel_id, month, column))
            if value is None:
                raise SystemExit(
                    f"C11-R1 stops: no C8 value for {channel_id} {month} {column}"
                )
            row.append(value)
        matrix.append(row)
    return matrix


def reproduce(config, opened) -> dict:
    """Rebuild every C11 invariant from C8/C9 alone."""
    expected = config["reproduction"]["expected"]
    phase_a = load_json(C9_PHASE_A)
    opened.append(C9_PHASE_A)
    c10 = load_json(C10_AUDIT)
    opened.append(C10_AUDIT)
    c11 = load_json(C11_DECISION_JSON)
    opened.append(C11_DECISION_JSON)
    c8_rows = pd.read_parquet(C8_PARQUET).to_dict("records")
    opened.append(C8_PARQUET)

    exposures = {
        row["industry_id"]: row["direct_exposure"] for row in phase_a["decisions"]
        if row["channel_id"] == "eppo_fo600_channel"
    }
    eligible = sorted(
        row["industry_id"] for row in phase_a["decisions"]
        if row["channel_id"] == "eppo_fo600_channel" and row["eligible"]
    )
    ind_04 = next(
        row for row in phase_a["decisions"]
        if row["industry_id"] == "IND-04"
        and row["channel_id"] == "eppo_fo600_channel"
    )
    issue_months = DM.month_range(DM.DEVELOPMENT_START, DM.DEVELOPMENT_END)
    reference_months = [DM.shift_month(m, -DM.POLICY_LAG_MONTHS) for m in issue_months]
    centered = CD.center_exposures(exposures, eligible)
    spread = CD.assert_exposure_varies(centered)

    per_variant, checks = {}, {}
    for variant_id in sorted(CHANNEL_BY_VARIANT):
        raw = source_time_matrix(
            c8_rows, CHANNEL_BY_VARIANT[variant_id], reference_months,
            CD.SOURCE_COLUMNS,
        )
        standardized = CD.standardize_source_block(raw, 0)["matrix"]
        design = CD.build_candidate_c_design(
            standardized, centered, issue_months, eligible, variant_id
        )
        ranks = CD.block_ranks(design)
        constant = CD.constant_exposure_interaction_report(
            design, standardized, issue_months
        )
        collapse = CD.per_industry_standardised_collapse(design)
        invalid = CD.build_candidate_c_design(
            standardized, centered, issue_months, eligible, variant_id,
            coding="global_intercept_plus_industry_indicators",
        )
        invalid_rank = CD.numerical_rank(invalid.matrix)
        projector_gaps = []
        for industry in eligible:
            report = CD.candidate_b_equivalence_report(
                CD.build_candidate_a_design(
                    standardized, issue_months, industry, variant_id
                ),
                CD.build_candidate_b_design(
                    standardized, issue_months, industry, exposures[industry],
                    variant_id,
                ),
                exposures[industry],
            )
            projector_gaps.append(report["column_space_projector_max_gap"])
            if not report["column_spaces_coincide"]:
                raise SystemExit(
                    f"C11-R1 stops: Candidate B no longer spans Candidate A for "
                    f"{industry}"
                )
        per_variant[variant_id] = {
            "source_block_rank": ranks["source_block_rank"],
            "interaction_block_rank": ranks["interaction_block_rank"],
            "combined_source_and_interaction_rank":
                ranks["combined_source_and_interaction_rank"],
            "full_design_rank": ranks["full_design_rank"],
            "full_design_columns": len(design.columns),
            "panel_rows": len(design.matrix),
            "constant_exposure_interaction_rank":
                constant["constant_exposure_interaction_rank"],
            "invalid_coding_rank": invalid_rank,
            "invalid_coding_columns": len(invalid.columns),
            "candidate_b_projector_residual_max": max(projector_gaps),
            "candidate_b_column_space_equivalent_to_candidate_a": True,
            "within_industry_combined_rank":
                max(collapse["per_industry_combined_ranks"]),
            "stacked_rank_under_prohibited_preprocessing":
                collapse["stacked_per_industry_standardized_combined_rank"],
            "interaction_blocks_intended":
                collapse["distinct_intended_interaction_blocks"],
            "interaction_blocks_after_prohibited_preprocessing":
                collapse["distinct_collapsed_interaction_blocks"],
            "sign_identity_residual": collapse["sign_identity_residual"],
            "design_checksum": CD.design_checksum(design),
        }

    for variant_id, entry in per_variant.items():
        for name in ("source_block_rank", "interaction_block_rank",
                     "combined_source_and_interaction_rank", "full_design_rank",
                     "full_design_columns", "constant_exposure_interaction_rank",
                     "invalid_coding_rank", "invalid_coding_columns", "panel_rows"):
            checks[f"{variant_id}.{name}"] = (entry[name], expected[name])
        checks[f"{variant_id}.candidate_b_projector_residual"] = (
            entry["candidate_b_projector_residual_max"]
            <= expected["candidate_b_projector_residual_max"], True,
        )
        checks[f"{variant_id}.design_checksum_matches_c11"] = (
            entry["design_checksum"],
            c11["identification"]["observed"][variant_id]["design_checksum"],
        )

    checks["eligible_industries"] = (len(eligible), expected["eligible_industries"])
    checks["unique_issue_months"] = (
        len(issue_months), expected["unique_issue_months"]
    )
    checks["exposure_cross_industry_spread_positive"] = (
        spread > 0, expected["exposure_cross_industry_spread_positive"]
    )
    checks["ind_04_eligible"] = (ind_04["eligible"], expected["ind_04_eligible"])
    checks["ind_04_direction_channel"] = (
        ind_04["direction_channel"], expected["ind_04_direction_channel"]
    )
    checks["ind_04_absent_from_the_panel"] = ("IND-04" in eligible, False)
    checks["channels_kept_separate"] = (
        sorted(per_variant) == sorted(CHANNEL_BY_VARIANT), True
    )
    upstream = config["reproduction"]["upstream_checksums"]
    checks["c9_phase_a_checksum"] = (
        phase_a["structural_decision_checksum"], upstream["c9_phase_a_checksum"]
    )
    checks["c10_content_checksum"] = (
        c10["content_checksum"], upstream["c10_content_checksum"]
    )
    checks["c10_diagnostic_contract_checksum"] = (
        c10["diagnostic_contract_checksum"],
        upstream["c10_diagnostic_contract_checksum"],
    )
    checks["c11_content_checksum"] = (
        c11["content_checksum"], upstream["c11_content_checksum"]
    )

    result = {
        name: {"actual": actual, "expected": want, "reproduced": actual == want}
        for name, (actual, want) in checks.items()
    }
    failed = sorted(name for name, check in result.items() if not check["reproduced"])
    return {
        "all_reproduced": not failed,
        "failed": failed,
        "checks": result,
        "per_variant": per_variant,
        "architecture": (
            AD.SELECTED_ARCHITECTURE_ID if not failed else None
        ),
        "expected_architecture": config["reproduction"]["expected_architecture"],
        "d_series_paths_opened": 0,
        "column_space_projector_method": {
            "c11_used": "unpivoted_qr_truncated_to_rank",
            "c11r1_uses": "svd_left_singular_vectors",
            "changed_after_c11": True,
            "why": (
                "Unpivoted QR does not order its basis by importance, so "
                "truncating it to `rank` columns is only correct for a matrix of "
                "full column rank. Every real C11 design IS full column rank, so "
                "the C11 conclusion is unaffected; the SVD basis is "
                "rank-revealing and correct for a rank-deficient matrix too."
            ),
            "affects_the_c11_conclusion": False,
            "residuals_differ_in_last_digits": True,
            "both_satisfy_the_preregistered_bound": True,
            "c11_was_not_rerun": True,
            "consequence_for_the_preservation_pin": (
                "The C11 artifacts pinned here were produced by the QR version "
                "and are byte-identical to their pins. A FUTURE rerun of C11 "
                "would move its projector residual in the last digits and "
                "therefore its content checksum. That would be a regeneration "
                "under a corrected projector, not tampering, and this field is "
                "the record that says so."
            ),
        },
        "c11_selection_agrees": (
            c11["selection"]["selected_architecture"]
            == config["reproduction"]["expected_architecture"]
        ),
    }


def make_reconstructor(reproduction: dict):
    """A reconstruction that consumes only permitted inputs.

    The metric-substitution fixture is handed to this function; it is never
    consulted, which is the point of the invariance check.
    """
    def reconstruct(inputs: dict):
        if not inputs.get("all_reproduced"):
            return None
        return inputs.get("architecture")

    return reconstruct, {
        "all_reproduced": reproduction["all_reproduced"],
        "architecture": reproduction["architecture"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()
    permitted = config["information_flow"]["permitted_inputs"]
    opened = [CONFIG_PATH]

    # --- freeze the corrected-gate specification -----------------------------
    spec_config = config["corrected_gate_specification"]
    correction = GV.CorrectedGateSpecification(
        correction_version=config["correction_version"],
        gate=spec_config["gate"],
        original_preregistered_expectation=spec_config["original"][
            "preregistered_expectation"],
        original_preregistered_stacked_rank_expectation=spec_config["original"][
            "original_preregistered_stacked_rank_expectation"],
        original_gate_condition=spec_config["original"][
            "gate_condition_as_originally_implemented"],
        original_gate_implementation_valid=spec_config["original"][
            "original_gate_implementation_valid"],
        original_preregistered_gate_set_passed=spec_config["original"][
            "original_preregistered_gate_set_passed"],
        observed_stacked_rank_under_prohibited_preprocessing=spec_config[
            "observed"]["observed_stacked_rank_under_prohibited_preprocessing"],
        centered_exposures_contain_both_signs=spec_config["observed"][
            "centered_exposures_contain_both_signs"],
        correct_measurements=dict(spec_config["correct_measurements"]),
        corrected_gate_condition=spec_config["corrected_gate_condition"],
        corrected_gate_set_passed=spec_config["corrected_gate_set_passed"],
        gate_implementation_corrected_after_observation=spec_config["status"][
            "gate_implementation_corrected_after_observation"],
        thresholds_changed_after_observation=spec_config["status"][
            "thresholds_changed_after_observation"],
        numerical_tolerance_changed=spec_config["status"][
            "numerical_tolerance_changed"],
        expectations_rewritten_as_preregistered=spec_config["status"][
            "expectations_rewritten_as_preregistered"],
        architecture_decision_cleanly_preregistered=spec_config["status"][
            "architecture_decision_cleanly_preregistered"],
        incorrect_question=spec_config["why_the_correction_is_justified"][
            "incorrect_question"],
        correct_question=spec_config["why_the_correction_is_justified"][
            "correct_question"],
        conclusion=spec_config["why_the_correction_is_justified"]["conclusion"],
    )
    correction_digest = GV.correction_checksum(correction)

    gate_status = {
        **spec_config["status"],
        "original_preregistered_stacked_rank_expectation": spec_config["original"][
            "original_preregistered_stacked_rank_expectation"],
        "observed_stacked_rank_under_prohibited_preprocessing": spec_config[
            "observed"]["observed_stacked_rank_under_prohibited_preprocessing"],
        "original_gate_implementation_valid": spec_config["original"][
            "original_gate_implementation_valid"],
        "original_preregistered_gate_set_passed": spec_config["original"][
            "original_preregistered_gate_set_passed"],
        "corrected_gate_set_passed": spec_config["corrected_gate_set_passed"],
    }
    missing = [f for f in GV.REQUIRED_GATE_STATUS_FIELDS if f not in gate_status]
    if missing:
        raise SystemExit(f"C11-R1 stops: gate status is missing {sorted(missing)}")
    GV.assert_original_gate_set_not_reported_as_passing(gate_status)
    GV.assert_correction_not_presented_as_preregistered(gate_status)
    GV.assert_correct_measurements_present(spec_config["correct_measurements"])

    incident = config["outcome_access_incident"]["status"]
    GV.assert_incident_recorded(incident)
    GV.assert_guard_does_not_erase_history(incident)

    # --- preservation --------------------------------------------------------
    pinned = config["preserved_c11_record"]
    observed_record = {
        "artifacts": {
            "decision_json": {"byte_sha256": byte_sha256(C11_DECISION_JSON)},
            "decision_markdown": {"byte_sha256": byte_sha256(C11_DECISION_MD)},
            "protocol_markdown": {"byte_sha256": byte_sha256(C11_PROTOCOL_MD)},
            "frozen_criteria": {"byte_sha256": byte_sha256(C11_CONFIG)},
        },
        "durable_checksums": {},
    }
    c11 = load_json(C11_DECISION_JSON)
    observed_record["durable_checksums"] = {
        "c11_content_checksum": c11["content_checksum"],
        "c11_decision_checksum": c11["decision_checksum"],
        "c11_decision_criteria_checksum": c11["decision_criteria_checksum"],
        "c11_lineage_checksum": c11["lineage"]["lineage_checksum"],
    }
    preservation = GV.assert_c11_record_preserved(pinned, observed_record)
    preservation["observed"] = observed_record
    preservation["disclosures_present"] = sorted(
        name for name in pinned["preserved_disclosures"]
    )
    preservation["c11_gate_correction_disclosure_present"] = bool(
        c11["preregistered_expectation_discrepancies"][
            "gate_implementation_corrected_after_observation"]
    )

    # --- reproduce the mathematics, without any D-series path ---------------
    reproduction = reproduce(config, opened)
    if not reproduction["all_reproduced"]:
        raise SystemExit(
            f"C11-R1 stops: the architecture did not reproduce: "
            f"{reproduction['failed']}"
        )

    # --- information-flow audit ---------------------------------------------
    reconstruct, reconstruction_inputs = make_reconstructor(reproduction)
    substitution = IF.metric_substitution_invariance(
        reconstruct, reconstruction_inputs, FABRICATED_METRICS
    )
    dependency = IF.dependency_report(
        INSPECTED_SOURCES, opened, permitted, reproduction, substitution
    )
    IF.assert_dependency_conclusion_bounded(dependency)
    dependency_digest = IF.flow_checksum(dependency)

    status = dict(config["decision_status"])
    GV.assert_status_is_exploratory(status)
    scope = config["architecture_scope"]
    outputs = dict(config["outputs"])

    closure_gates = GV.evaluate_closure_gates(
        preservation, gate_status, incident, reproduction, dependency, status,
        scope, outputs,
    )
    authorization = GV.authorize_d5(closure_gates)
    GV.assert_d5_authorization_bounded(authorization)
    governance_digest = GV.governance_checksum(
        preservation, correction_digest, incident, dependency_digest,
        closure_gates, authorization,
    )

    for narrative in (CORRECTION_NARRATIVE, INCIDENT_NARRATIVE,
                      correction.conclusion, dependency["does_not_prove"],
                      authorization["reason"]):
        GV.assert_not_described_as_a_tolerance_change(narrative)
        AD.assert_predictive_not_causal(narrative)

    payload = {
        "task": "C11-R1",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "correction_version": correction.correction_version,
        "supersedes_status_of": config["supersedes_status_of"],
        "supersedes_findings_of": config["supersedes_findings_of"],
        "preserved_c11_record": {**pinned, **preservation},
        "corrected_gate_specification": {
            **spec_config,
            "frozen": correction.to_dict(),
            "correction_checksum": correction_digest,
            "narrative": CORRECTION_NARRATIVE,
        },
        "gate_status": gate_status,
        "outcome_access_incident": {
            **config["outcome_access_incident"],
            "narrative": INCIDENT_NARRATIVE,
        },
        "information_flow": {
            **dependency,
            "flow_checksum": dependency_digest,
            "permitted_inputs": permitted,
        },
        "reproduction": reproduction,
        "decision_status": status,
        "architecture_scope": scope,
        "closure_gates": closure_gates,
        "all_closure_gates_passed": all(closure_gates.values()),
        "d5_authorization": {
            **config["d5_authorization"],
            "granted": authorization,
        },
        "governance_checksum": governance_digest,
        "outputs": outputs,
        "prohibited_in_c11r1": config["prohibited_in_c11r1"],
    }
    GV.assert_no_umbrella_outcome_free_claim(payload)
    payload["content_checksum"] = GV.content_checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    GV.assert_not_described_as_a_tolerance_change(serialized)
    with open(DOCS / "c11r1_governance_decision.json", "w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.write("\n")
    write_governance_markdown(payload)
    write_erratum(payload)

    print(json.dumps({
        "c11_record_preserved": preservation["durable_checksums_unchanged"],
        "c11_byte_identical": preservation["byte_identical"],
        "correction_checksum": correction_digest,
        "original_preregistered_gate_set_passed": gate_status[
            "original_preregistered_gate_set_passed"],
        "corrected_gate_set_passed": gate_status["corrected_gate_set_passed"],
        "architecture_decision_cleanly_preregistered": gate_status[
            "architecture_decision_cleanly_preregistered"],
        "development_metric_artifact_accessed": incident[
            "development_metric_artifact_accessed"],
        "outcome_free_execution": incident["outcome_free_execution"],
        "decision_reproducible_without_metric_artifact": incident[
            "decision_reproducible_without_metric_artifact"],
        "reproduction_all_reproduced": reproduction["all_reproduced"],
        "d_series_paths_opened": dependency["d_series_paths_opened"],
        "read_call_sites_inspected": dependency["static_inspection"][
            "read_call_sites"],
        "offending_read_calls": len(dependency["static_inspection"][
            "offending_read_calls"]),
        "metric_substitution_invariant": substitution["invariant"],
        "architecture_decision_dependency_clean": dependency[
            "architecture_decision_dependency_clean"],
        "architecture_decision_status": status["architecture_decision_status"],
        "all_closure_gates_passed": payload["all_closure_gates_passed"],
        "d5_authorized": {
            k: authorization[k] for k in sorted(GV.D5_AUTHORIZATION_FIELDS)
        },
        "flow_checksum": dependency_digest,
        "governance_checksum": governance_digest,
        "content_checksum": payload["content_checksum"],
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def _fmt(value, digits=6) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if abs(value) >= 1e6 or (value != 0 and abs(value) < 1e-4):
            return f"{value:.3e}"
        return f"{value:.{digits}f}"
    return str(value)


def write_governance_markdown(payload: dict) -> None:
    spec = payload["corrected_gate_specification"]
    incident = payload["outcome_access_incident"]
    flow = payload["information_flow"]
    lines = [
        "# Task C11-R1 - Specification-Correction and Outcome-Access Governance",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        f"**Supersedes the STATUS of `{payload['supersedes_status_of']}`. "
        f"Supersedes its findings: `{payload['supersedes_findings_of']}`.**",
        "",
        "C11-R1 corrects how the C11 architecture decision is formally described.",
        "It changes none of its mathematics, and it removes none of its",
        "disclosures. Two facts that C11 reported together are separated here and",
        "stay separated:",
        "",
        "1. **The decision is dependency-clean** - it reproduces exactly without",
        "   any D-series result.",
        "2. **The original execution was not outcome-blind** - a development",
        "   metric artifact was opened during it.",
        "",
        "No umbrella `outcome_free: true` is claimed anywhere.",
        "",
        "## The corrected decision status",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["decision_status"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines += [
        "",
        "## 1. The preserved C11 record",
        "",
        f"C11's durable checksums are unchanged: "
        f"{_flag(payload['preserved_c11_record']['durable_checksums_unchanged'])}. "
        f"Byte-identical: "
        f"{_flag(payload['preserved_c11_record']['byte_identical'])}. "
        f"Artifacts edited: "
        f"`{payload['preserved_c11_record']['artifacts_edited'] or 'none'}`.",
        "",
        "| artifact | byte sha256 | carries a timestamp |",
        "| --- | --- | --- |",
    ]
    for entry in payload["preserved_c11_record"]["artifacts"].values():
        lines.append(
            f"| `{entry['path']}` | `{entry['byte_sha256']}` | "
            f"{_flag(entry['carries_generation_timestamp'])} |"
        )
    lines += [
        "",
        "| durable checksum | value |",
        "| --- | --- |",
    ]
    for name, value in payload["preserved_c11_record"]["durable_checksums"].items():
        lines.append(f"| `{name}` | `{value}` |")
    lines += [
        "",
        "A **byte digest** is a forward integrity baseline only: the Markdown and",
        "JSON carry a generation timestamp, so a legitimate rerun moves them. The",
        "**content checksum** excludes timestamps and is the durable identity, so",
        "a change there would mean the record itself changed. C11 was not edited;",
        "this document is a sidecar, because a correction written into a generated",
        "file is erased by the next regeneration.",
        "",
        "Preserved disclosures: "
        + ", ".join(
            f"`{d}`" for d in payload["preserved_c11_record"]["preserved_disclosures"]
        ) + ".",
        "",
        "## 2. The original gate and the corrected gate, kept apart",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in GV.REQUIRED_GATE_STATUS_FIELDS:
        lines.append(f"| `{key}` | `{payload['gate_status'][key]}` |")
    lines += [
        "",
        f"**Gate:** `{spec['gate']}`",
        "",
        "### What was preregistered",
        "",
        f"> {spec['original']['preregistered_expectation'].strip()}",
        "",
        "As implemented: "
        + spec["original"]["gate_condition_as_originally_implemented"].strip(),
        "",
        "### What was observed",
        "",
        "| observation | value |",
        "| --- | --- |",
        f"| stacked combined rank under the prohibited preprocessing | "
        f"**{spec['observed']['observed_stacked_rank_under_prohibited_preprocessing']}** |",
        f"| centred exposures contain both signs | "
        f"{_flag(spec['observed']['centered_exposures_contain_both_signs'])} |",
        f"| positive / negative sign industries | "
        f"{spec['observed']['positive_sign_industries']} / "
        f"{spec['observed']['negative_sign_industries']} |",
        f"| per-industry standardisation maps the interaction to | "
        f"`{spec['observed']['per_industry_standardization_maps_interaction_to']}` |",
        f"| stacking both sign groups preserves two directions | "
        f"{_flag(spec['observed']['stacking_both_sign_groups_preserves_two_directions'])} |",
        "",
        "### The correct measurements",
        "",
        "| measurement | value |",
        "| --- | --- |",
    ]
    for key, value in spec["correct_measurements"].items():
        lines.append(f"| `{key}` | `{_fmt(value)}` |")
    lines += [
        "",
        "### Why the correction is justified",
        "",
        "**Incorrect measurement.** "
        + spec["why_the_correction_is_justified"]["incorrect_question"].strip(),
        "",
        "**Correct measurement.** "
        + spec["why_the_correction_is_justified"]["correct_question"].strip(),
        "",
        "> " + spec["why_the_correction_is_justified"]["conclusion"].strip(),
        "",
        spec["narrative"],
        "",
        f"Corrected gate: {spec['corrected_gate_condition'].strip()}",
        "",
        f"Frozen correction checksum `{spec['correction_checksum']}`.",
        "",
        "## 3. The outcome-access incident",
        "",
        incident["narrative"],
        "",
        f"**{incident['files_opened_count']}** D-series JSON documents were opened "
        f"during C11; **{incident['files_with_metric_values_displayed']}** had "
        "metric values displayed.",
        "",
        "| file | metric values present | metric values displayed | required |",
        "| --- | --- | --- | --- |",
    ]
    for entry in incident["files_opened"]:
        lines.append(
            f"| `{entry['path']}` | "
            f"{_flag(entry.get('contains_development_metric_values', False))} | "
            f"{_flag(entry.get('metric_values_displayed', False))} | "
            f"{_flag(entry.get('required_for_that_purpose', False))} |"
        )
    lines += ["", "| field | value |", "| --- | --- |"]
    for key in GV.REQUIRED_INCIDENT_STATUS_FIELDS:
        lines.append(f"| `{key}` | `{incident['status'][key]}` |")
    for key in ("locked_test_manifest_opened", "locked_test_outcomes_accessed",
                "umbrella_outcome_free_claim_made"):
        lines.append(f"| `{key}` | `{incident['status'][key]}` |")
    lines += [
        "",
        f"> {incident['status']['development_target_values_accessed_basis'].strip()}",
        "",
        f"> {incident['remediation']['remediation_note'].strip()}",
        "",
        "## 4. Information-flow audit",
        "",
        f"`architecture_decision_dependency_clean`: "
        f"**{flow['architecture_decision_dependency_clean']}**",
        "",
        "| instrument | result |",
        "| --- | --- |",
        f"| inputs opened (allowlist admitted) | {flow['inputs_opened_count']} |",
        f"| D-series paths opened | **{flow['d_series_paths_opened']}** |",
        f"| read call sites statically inspected | "
        f"{flow['static_inspection']['read_call_sites']} |",
        f"| read calls opening a forbidden path | "
        f"**{len(flow['static_inspection']['offending_read_calls'])}** |",
        f"| offending imports | `{flow['offending_imports'] or 'none'}` |",
        f"| metric-substitution invariance | "
        f"{_flag(flow['metric_substitution_invariance']['invariant'])} |",
        "",
        "Fabricated metric keys injected into an isolated fixture: "
        + ", ".join(
            f"`{k}`" for k in
            flow["metric_substitution_invariance"]["fabricated_metric_keys"]
        ) + ". "
        + "Written to disk: " + _flag(flow["metric_substitution_invariance"][
            "fabricated_values_written_to_disk"])
        + ". The selected architecture did not move.",
        "",
        "Permitted inputs are admitted by **name**, not by failing to match a",
        "forbidden pattern - a denylist admits every artifact nobody anticipated,",
        "which is how the original access happened.",
        "",
        f"**This proves:** {flow['proves']}",
        "",
        f"**This does not prove:** {flow['does_not_prove']}",
        "",
        "## 5. Reproduction without any D-series access",
        "",
        f"All reproduced: **{payload['reproduction']['all_reproduced']}** "
        f"({len(payload['reproduction']['checks'])} checks). "
        f"Architecture: `{payload['reproduction']['architecture']}`.",
        "",
        "| variant | source | interaction | combined | full / cols | const-exp | "
        "invalid coding | B projector |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant_id, entry in payload["reproduction"]["per_variant"].items():
        lines.append(
            f"| `{variant_id}` | {entry['source_block_rank']} | "
            f"{entry['interaction_block_rank']} | "
            f"{entry['combined_source_and_interaction_rank']} | "
            f"{entry['full_design_rank']} / {entry['full_design_columns']} | "
            f"{entry['constant_exposure_interaction_rank']} | "
            f"{entry['invalid_coding_rank']} / {entry['invalid_coding_columns']} | "
            f"{_fmt(entry['candidate_b_projector_residual_max'])} |"
        )
    lines += [
        "",
        "| variant | within-industry rank | stacked rank | interaction blocks | "
        "sign residual |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for variant_id, entry in payload["reproduction"]["per_variant"].items():
        lines.append(
            f"| `{variant_id}` | **{entry['within_industry_combined_rank']}** | "
            f"{entry['stacked_rank_under_prohibited_preprocessing']} | "
            f"**{entry['interaction_blocks_intended']} -> "
            f"{entry['interaction_blocks_after_prohibited_preprocessing']}** | "
            f"{_fmt(entry['sign_identity_residual'])} |"
        )

    lines += [
        "",
        "## 6. Architecture scope, preserved",
        "",
        f"`{payload['architecture_scope']['formula'].strip()}`",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["architecture_scope"].items():
        if key == "formula":
            continue
        lines.append(f"| `{key}` | `{value}` |")

    lines += ["", "## 7. Closure gates", "", "| gate | passed |", "| --- | --- |"]
    for gate, passed in payload["closure_gates"].items():
        lines.append(f"| `{gate}` | {_flag(passed)} |")

    granted = payload["d5_authorization"]["granted"]
    lines += [
        "",
        f"All closure gates passed: **{payload['all_closure_gates_passed']}**.",
        "",
        "## 8. Bounded D5 authorization",
        "",
        "> " + granted["reason"],
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in GV.D5_AUTHORIZATION_FIELDS:
        lines.append(f"| `{key}` | {_flag(granted[key])} |")
    lines += ["", "### Scope of the grant", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["d5_authorization"]["scope"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "The authorization is void if the dependency-clean reconstruction "
        "fails: " + _flag(payload["d5_authorization"][
            "authorization_void_if_dependency_reconstruction_fails"]) + ".",
        "",
        "## Checksums",
        "",
        f"Correction `{spec['correction_checksum']}`. "
        f"Information flow `{flow['flow_checksum']}`. "
        f"Governance `{payload['governance_checksum']}`. "
        f"Content `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c11r1_governance_decision.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_erratum(payload: dict) -> None:
    spec = payload["corrected_gate_specification"]
    incident = payload["outcome_access_incident"]
    lines = [
        "# Erratum - Task C11 Architecture Decision",
        "",
        "**Status:** active correction to the *methodological status* claimed in",
        "C11 reporting. **Raised and closed by:** Task C11-R1.",
        "**Applies to:** [`c11_architecture_decision.md`](c11_architecture_decision.md)",
        "and [`c11_architecture_decision_protocol.md`](c11_architecture_decision_protocol.md).",
        "",
        "This erratum is a **sidecar**. The correction lives here instead of being",
        "edited into the generated C11 documents - otherwise a later regeneration",
        "would silently erase it, and the record of what C11 actually claimed",
        "would be lost. The C11 files are unchanged and their digests are pinned",
        "in [`c11r1_governance_decision.json`](c11r1_governance_decision.json).",
        "",
        "**C11's mathematics is not corrected here.** Every rank, residual and",
        "identity it reported reproduces exactly, without opening any D-series",
        "file. What is corrected is how the decision may be described.",
        "",
        "---",
        "",
        "## 1. One of the nine gates did not pass as preregistered",
        "",
        "C11 reported that all nine mandatory gates passed. That is true of the",
        "**corrected** gate set, not of the **originally preregistered** one.",
        "",
        f"The gate `{spec['gate']}` was preregistered as:",
        "",
        f"> {spec['original']['preregistered_expectation'].strip()}",
        "",
        "The observed stacked rank was "
        f"**{spec['observed']['observed_stacked_rank_under_prohibited_preprocessing']}**, "
        "not 5. So the original gate, as implemented, **did not pass**.",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in GV.REQUIRED_GATE_STATUS_FIELDS:
        lines.append(f"| `{key}` | `{payload['gate_status'][key]}` |")
    lines += [
        "",
        "## 2. The correction is a change of quantity, not of tolerance",
        "",
        "No tolerance and no threshold moved. The rank tolerance, the",
        "duplicate-column tolerance and every residual tolerance stand exactly as",
        "preregistered. The gate was measuring the wrong quantity.",
        "",
        "**Incorrect question.** "
        + spec["why_the_correction_is_justified"]["incorrect_question"].strip(),
        "",
        "**Correct question.** "
        + spec["why_the_correction_is_justified"]["correct_question"].strip(),
        "",
        "The collapse C11 claimed is real; it simply is not visible in the stacked",
        "rank. Within an industry the combined block falls to rank",
        f"**{spec['correct_measurements']['within_industry_combined_rank']}**, and",
        f"**{spec['correct_measurements']['interaction_blocks_intended']}** distinct",
        "exposure-proportional interaction blocks collapse to",
        f"**{spec['correct_measurements']['sign_equivalence_groups']}** sign groups.",
        "",
        "> " + spec["why_the_correction_is_justified"]["conclusion"].strip(),
        "",
        "## 3. The execution was not outcome-blind",
        "",
        f"**{incident['files_opened_count']}** D-series JSON documents were opened",
        f"during C11 and **{incident['files_with_metric_values_displayed']}** had",
        "development metric values displayed. The file was not required: the",
        "benchmark contract name was already present in non-result documentation.",
        "",
        "No metric value entered the C11 configuration, the candidate matrices, any",
        "checksum, the gate arithmetic or the architecture selection, and C11-R1",
        "reproduces the decision without opening any of them. That makes the",
        "decision **dependency-clean**. It does not make the execution history",
        "outcome-blind, and a guard added afterwards does not reach backwards.",
        "",
        "## 4. The resulting status",
        "",
        f"`architecture_decision_status`: "
        f"**{payload['decision_status']['architecture_decision_status']}**",
        "",
        "The architecture is *mathematically supported* and *not confirmatory*. An",
        "imperfect process does not invalidate a reproduced identity, and a",
        "convincing correction does not upgrade an exploratory selection.",
        "",
        "Full record: "
        "[`c11r1_governance_decision.md`](c11r1_governance_decision.md).",
        "",
    ]
    (DOCS / "c11_architecture_decision.errata.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
