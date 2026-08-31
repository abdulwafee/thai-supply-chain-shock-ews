"""Task C12 — EPPO fuel-oil modeling-channel closure.

Records and enforces the closure of the EPPO sector-093 fuel-oil channel for
further predictive modeling, after the preregistered D5 development evaluation
failed to demonstrate incremental signal.

GOVERNANCE AND EVIDENCE PRESERVATION ONLY. No model is rerun, no metric is
recomputed, no specification is tuned, no channel is selected, no purge origin
is evaluated and the locked final test stays closed. C7 through D5 are read-only.

The closure applies to MODELING USE. The EPPO archive, the semantic decisions,
the transformations, the structural exposure and every provenance artifact
remain valid within their stated limitations, and D5 must stay reproducible.

    docs/c12_channel_closure.{md,json}
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

from thai_supply_chain_ews.structure import fuel_oil_channel_closure as CL  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "fuel_oil_channel_closure.yaml"
D5_RESULTS = DOCS / "d5_development_results.json"
D5_AUDIT = DOCS / "d5_assembly_audit.json"

#: The prose C12 authors. Held as constants so the language guards run over
#: every sentence before anything is rendered.
CLOSURE_NARRATIVE = " ".join((
    "The registered development evaluation did not demonstrate incremental",
    "signal for either fuel-oil variant at either horizon. No point estimate",
    "beat its benchmark, every paired interval straddled zero, and event safety",
    "failed in all four cases. Fifteen issue-month clusters cannot settle the",
    "question either way, so this is a failure to demonstrate rather than a",
    "demonstration of failure. The preregistered stop rule nevertheless supports",
    "closing further investment in this channel: that is a project-governance",
    "decision about where to spend effort, and it is not a population-level",
    "scientific conclusion.",
))

CHAIN_NARRATIVE = " ".join((
    "C10 established a design limitation - the industry conditioning contributes",
    "cross-industry scale and no temporal degrees of freedom - as a property of",
    "the design matrix, without reading any target. That is not the same as",
    "showing the channel carries nothing. D5 supplied the development evidence,",
    "and D5 was inconclusive. Attributing the closure to C10 alone would",
    "overstate what a rank identity can establish, and attributing it to D5",
    "alone would lose the reason the architecture was constrained to begin with.",
))

PRESERVATION_NARRATIVE = " ".join((
    "Every artifact from C7 through D5 is preserved unchanged and pinned here.",
    "Preservation supports audit and portfolio reproducibility; it does not",
    "imply continued modeling eligibility, and the existing runners remain able",
    "to reproduce their historical outputs under their own frozen contracts.",
))


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def byte_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guard_text(text: str) -> str:
    """Authored prose, checked verbatim: nothing here may name a prohibited term."""
    CL.assert_no_absence_claim(text, strip_named_terms=False)
    return text


def guard_document(text: str) -> str:
    """A rendered document, checked with backticked and quoted spans removed.

    The closure publishes its own prohibition list, so a term appearing inside
    backticks is being NAMED. Prose outside them is still checked verbatim.
    """
    CL.assert_no_absence_claim(text)
    return text


# ---------------------------------------------------------------------------
# 1. Terminal D5 evidence, reproduced from the frozen artifacts
# ---------------------------------------------------------------------------
def reproduce_terminal_evidence(config) -> dict:
    results = load_json(D5_RESULTS)
    audit = load_json(D5_AUDIT)
    terminal = config["terminal_evidence"]
    tolerance = float(terminal["metric_tolerance"])
    aggregate = terminal["aggregate_expectations"]

    checks = {
        "d5_frozen_protocol_checksum": (
            results["frozen_protocol_checksum"],
            terminal["d5_frozen_protocol_checksum"],
        ),
        "d5_results_content_checksum": (
            results["content_checksum"], terminal["d5_results_content_checksum"],
        ),
        "d5_assembly_audit_content_checksum": (
            audit["content_checksum"],
            terminal["d5_assembly_audit_content_checksum"],
        ),
    }

    worse, straddling, failed, supported = 0, 0, 0, 0
    per_variant_horizon = {}
    for key, entry in results["results"].items():
        variant, horizon = entry["variant_id"], str(entry["horizon"])
        expected = terminal["expected"][variant][horizon]
        boot = entry["bootstrap"]
        observed = {
            "model_macro_mae": entry["model"]["macro_industry_mae"],
            "benchmark_macro_mae": entry["benchmark"]["macro_industry_mae"],
            "paired_ci_low": boot["paired_ci_low"],
            "paired_ci_high": boot["paired_ci_high"],
            "mae_evidence": entry["mae_evidence"],
            "event_safety_passed": entry["event_safety"]["event_safety_passed"],
        }
        for name, want in expected.items():
            actual = observed[name]
            agrees = (abs(float(actual) - float(want)) <= tolerance
                      if isinstance(want, (int, float)) and not isinstance(want, bool)
                      else actual == want)
            checks[f"{key}.{name}"] = (actual, want, agrees)
        worse += observed["model_macro_mae"] > observed["benchmark_macro_mae"]
        straddling += observed["paired_ci_low"] <= 0.0 <= observed["paired_ci_high"]
        failed += not observed["event_safety_passed"]
        supported += entry["overall_status"] == (
            "exploratory_incremental_signal_supported"
        )
        per_variant_horizon[key] = {
            **observed,
            "overall_status": entry["overall_status"],
            "model_false_negatives": entry["model"]["false_negatives"],
            "benchmark_false_negatives": entry["benchmark"]["false_negatives"],
        }

    counts = audit["counts"]
    reader = audit["target_reader"]
    scope = results["scope"]
    checks["model_worse_than_benchmark_on_point_estimate"] = (
        worse, aggregate["model_worse_than_benchmark_on_point_estimate"]
    )
    checks["paired_intervals_including_zero"] = (
        straddling, aggregate["paired_intervals_including_zero"]
    )
    checks["event_safety_gates_failed"] = (
        failed, aggregate["event_safety_gates_failed"]
    )
    checks["variant_horizons_evaluated"] = (
        len(results["results"]), aggregate["variant_horizons_evaluated"]
    )
    checks["any_result_reached_supported"] = (
        bool(supported), aggregate["any_result_reached_supported"]
    )
    for key, entry in per_variant_horizon.items():
        if entry.get("mae_evidence") and key.endswith("|h1"):
            variant = key.split("|h")[0]
            checks[f"{variant}.h1_model_false_negatives"] = (
                entry["model_false_negatives"],
                aggregate["h1_model_false_negatives"][variant],
            )
            checks[f"{variant}.h1_benchmark_false_negatives"] = (
                entry["benchmark_false_negatives"],
                aggregate["h1_benchmark_false_negatives"],
            )
    checks["prediction_rows"] = (
        counts["total_predictions"], aggregate["prediction_rows"]
    )
    checks["modeled_predictions"] = (
        counts["pooled_model_predictions"], aggregate["modeled_predictions"]
    )
    checks["ind_04_benchmark_passthrough"] = (
        counts["ind_04_benchmark_passthrough"],
        aggregate["ind_04_benchmark_passthrough"],
    )
    checks["variants_combined"] = (
        bool(results["scope"].get("channels_combined")), aggregate["variants_combined"]
    )
    checks["variant_selected"] = (scope["channel_selected"],
                                  aggregate["variant_selected"])
    checks["purge_evaluated"] = (scope["purge_evaluated"],
                                 aggregate["purge_evaluated"])
    checks["locked_test_accessed"] = (scope["locked_test_accessed"],
                                      aggregate["locked_test_accessed"])
    checks["protocol_frozen_before_target_access"] = (
        reader["protocol_verified_before_any_target_read"],
        aggregate["protocol_frozen_before_target_access"],
    )
    checks["target_reads_before_prediction_freeze"] = (
        reader["target_reads_before_prediction_freeze"],
        aggregate["target_reads_before_prediction_freeze"],
    )
    checks["confirmatory_evaluation"] = (
        scope["confirmatory_evaluation"], aggregate["confirmatory_evaluation"]
    )

    result = {}
    for name, value in checks.items():
        if len(value) == 3:
            actual, expected, agrees = value
        else:
            actual, expected = value
            agrees = actual == expected
        result[name] = {"actual": actual, "expected": expected,
                        "reproduced": bool(agrees)}
    failed_checks = sorted(n for n, c in result.items() if not c["reproduced"])
    return {
        "all_reproduced": not failed_checks,
        "failed": failed_checks,
        "checks": result,
        "per_variant_horizon": per_variant_horizon,
        "metrics_recomputed_in_c12": False,
        "d5_rerun_in_c12": False,
    }


# ---------------------------------------------------------------------------
# 2. Preservation
# ---------------------------------------------------------------------------
def verify_preservation(config) -> dict:
    preservation = config["preservation"]
    pinned, observed = {}, {}
    for name, digest in preservation["content_checksums"].items():
        pinned[f"content:{name}"] = digest
        path = DOCS / f"{name}.json"
        observed[f"content:{name}"] = (
            load_json(path)["content_checksum"] if path.is_file() else None
        )
    for path, digest in preservation["byte_checksums"].items():
        pinned[f"byte:{path}"] = digest
        target = ROOT / path
        observed[f"byte:{path}"] = byte_sha256(target) if target.is_file() else None
    report = CL.assert_artifacts_preserved(pinned, observed)
    return {
        **report,
        "content_checksums": preservation["content_checksums"],
        "byte_checksums": preservation["byte_checksums"],
        "historical_runners_remain_able_to_reproduce_their_outputs": True,
        "preservation_implies_continued_modeling_eligibility": False,
        "preservation_supports": preservation["preservation_supports"],
        "narrative": PRESERVATION_NARRATIVE,
    }


# ---------------------------------------------------------------------------
# 3. Enforcement, exercised against permitted and prohibited consumers
# ---------------------------------------------------------------------------
def exercise_enforcement(policy) -> dict:
    probes = []
    for purpose in policy["permitted_purposes"]:
        outcome = CL.assert_modeling_entry_permitted(
            policy["closed_feature_ids"], purpose, policy
        )
        probes.append({"purpose": purpose, "feature_group": "closed_feature_ids",
                       "permitted": outcome["permitted"],
                       "reason": outcome["reason"]})
    for purpose in policy["blocked_purposes"]:
        for group in ("closed_feature_ids", "closed_aliases",
                      "closed_composite_forms", "closed_upstream_feature_tables"):
            try:
                CL.assert_modeling_entry_permitted(policy[group], purpose, policy)
            except CL.ClosedChannelError as error:
                probes.append({
                    "purpose": purpose, "feature_group": group,
                    "permitted": False,
                    "reason": "closed_channel",
                    "reason_is_specific": "closed_after_registered" in str(error),
                    "reported_as_missing": "not found" in str(error).lower(),
                })
            else:  # pragma: no cover - a permitted modeling entry is a failure
                raise SystemExit(
                    f"C12 stops: {group} passed the guard for purpose {purpose}"
                )
    open_feature = CL.assert_modeling_entry_permitted(
        ["brent_usd_bbl", "rubber_rss3_usd_kg"], "modeling", policy
    )
    return {
        "probes": probes,
        "permitted_purposes_all_allowed": all(
            p["permitted"] for p in probes if p["purpose"] in policy["permitted_purposes"]
        ),
        "blocked_purposes_all_refused": all(
            not p["permitted"] for p in probes
            if p["purpose"] in policy["blocked_purposes"]
        ),
        "closure_reason_is_specific": all(
            p.get("reason_is_specific", True) for p in probes
        ),
        "closed_features_reported_as_missing": any(
            p.get("reported_as_missing") for p in probes
        ),
        "unrelated_features_unaffected": open_feature["permitted"],
        "generic_upstream_feature_creation_altered": False,
        "historical_d5_reproducibility_preserved": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    for narrative in (CLOSURE_NARRATIVE, CHAIN_NARRATIVE, PRESERVATION_NARRATIVE,
                      config["evidence_chain"]["attribution"]["note"]):
        guard_text(narrative)

    evidence = reproduce_terminal_evidence(config)
    if not evidence["all_reproduced"]:
        raise SystemExit(
            f"C12 stops: terminal D5 evidence did not reproduce: "
            f"{evidence['failed']}. D5 is not recomputed or repaired here."
        )

    preservation = verify_preservation(config)
    policy = config["enforcement"]
    policy["prohibited_reopening_reasons"] = config["prohibited_reopening_reasons"]
    enforcement = exercise_enforcement(policy)

    closure_fields = config["closure"]["fields"]
    CL.assert_closure_fields(closure_fields)
    CL.assert_both_variants_closed(config["closure"])
    CL.assert_no_channel_preference({**config["closure"], **closure_fields})
    CL.assert_source_validity_preserved(config["validity_versus_eligibility"])
    CL.assert_prohibited_reasons_recorded(config["prohibited_reopening_reasons"])
    CL.assert_no_absence_claim(config["conclusion"]["statement"])

    record = CL.ClosureRecord(
        closure_version=config["closure_version"],
        channel_id=config["closure"]["channel_id"],
        variants=tuple(config["closure"]["variants"]),
        conclusion=config["conclusion"]["statement"],
        fields=dict(closure_fields),
        terminal_evidence_checksums={
            "d5_frozen_protocol": config["terminal_evidence"][
                "d5_frozen_protocol_checksum"],
            "d5_results": config["terminal_evidence"]["d5_results_content_checksum"],
            "d5_assembly_audit": config["terminal_evidence"][
                "d5_assembly_audit_content_checksum"],
        },
        preserved_artifacts=dict(config["preservation"]["content_checksums"]),
    )
    closure_digest = CL.closure_checksum(record)

    payload = {
        "task": "C12",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "closure_version": config["closure_version"],
        "supersedes": config["supersedes"],
        "superseded_by": config["superseded_by"],
        "conclusion": {**config["conclusion"], "narrative": CLOSURE_NARRATIVE},
        "terminal_evidence": {
            **{k: v for k, v in config["terminal_evidence"].items()
               if k != "expected"},
            "expected": config["terminal_evidence"]["expected"],
            "reproduction": evidence,
        },
        "evidence_chain": {**config["evidence_chain"],
                           "narrative": CHAIN_NARRATIVE},
        "closure": {**config["closure"], "closure_checksum": closure_digest},
        "preservation": preservation,
        "validity_versus_eligibility": config["validity_versus_eligibility"],
        "prohibited_reopening_reasons": config["prohibited_reopening_reasons"],
        "new_specification_alone_is_new_evidence": config[
            "new_specification_alone_is_new_evidence"],
        "permitted_reopening_evidence": config["permitted_reopening_evidence"],
        "enforcement": {**config["enforcement"], "exercised": enforcement},
        "prohibited_in_c12": config["prohibited_in_c12"],
        "outputs": config["outputs"],
        "final_declaration": config["final_declaration"],
    }
    payload["content_checksum"] = CL.content_checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True,
                            default=str)
    # JSON keys and values are named terms; the prose is guarded above.
    CL.assert_no_absence_claim(" ".join(
        line for line in serialized.splitlines()
        if "narrative" in line or "note" in line
    ))
    (DOCS / "c12_channel_closure.json").write_text(serialized + "\n",
                                                   encoding="utf-8")
    write_closure_markdown(payload)

    print(json.dumps({
        "terminal_evidence_reproduced": evidence["all_reproduced"],
        "checks": len(evidence["checks"]),
        "metrics_recomputed_in_c12": False,
        "d5_rerun_in_c12": False,
        "artifacts_pinned": preservation["artifacts_pinned"],
        "artifacts_deleted": preservation["artifacts_deleted"],
        "artifacts_modified": preservation["artifacts_modified"],
        "channel_id": payload["closure"]["channel_id"],
        "channel_status": closure_fields["channel_status"],
        "conclusion": payload["conclusion"]["statement"],
        "absence_of_effect_proven": closure_fields["absence_of_effect_proven"],
        "source_pipeline_remains_valid": closure_fields[
            "source_pipeline_remains_valid"],
        "enforcement": {
            "permitted_purposes_all_allowed":
                enforcement["permitted_purposes_all_allowed"],
            "blocked_purposes_all_refused":
                enforcement["blocked_purposes_all_refused"],
            "closed_features_reported_as_missing":
                enforcement["closed_features_reported_as_missing"],
            "unrelated_features_unaffected":
                enforcement["unrelated_features_unaffected"],
            "probes": len(enforcement["probes"]),
        },
        "closure_checksum": closure_digest,
        "content_checksum": payload["content_checksum"],
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def _fmt(value, digits=3) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_closure_markdown(payload: dict) -> None:
    closure = payload["closure"]
    evidence = payload["terminal_evidence"]["reproduction"]
    lines = [
        "# Task C12 - EPPO Fuel-Oil Modeling-Channel Closure",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        f"**Channel `{closure['channel_id']}` is "
        f"`{closure['fields']['channel_status']}`.**",
        "",
        f"Conclusion: **`{payload['conclusion']['statement']}`**",
        "",
        payload["conclusion"]["narrative"],
        "",
        "The closure applies to **predictive modeling use**. It does not",
        "invalidate or delete the EPPO archive, the semantic decisions, the",
        "transformations, the structural exposure or any provenance artifact.",
        "",
        "## 1. Terminal D5 evidence",
        "",
        f"Reproduced from the frozen artifacts: **{evidence['all_reproduced']}** "
        f"({len(evidence['checks'])} checks). "
        f"`metrics_recomputed_in_c12`: "
        f"{_flag(evidence['metrics_recomputed_in_c12'])}, `d5_rerun_in_c12`: "
        f"{_flag(evidence['d5_rerun_in_c12'])}.",
        "",
        "| variant | h | model macro MAE | benchmark | paired 95% interval | "
        "MAE evidence | event safety | status |",
        "| --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for key, entry in payload["terminal_evidence"]["reproduction"][
            "per_variant_horizon"].items():
        variant, horizon = key.split("|h")
        lines.append(
            f"| `{variant}` | {horizon} | {_fmt(entry['model_macro_mae'])} | "
            f"{_fmt(entry['benchmark_macro_mae'])} | "
            f"[{_fmt(entry['paired_ci_low'])}, {_fmt(entry['paired_ci_high'])}] | "
            f"{entry['mae_evidence']} | "
            f"{_flag(entry['event_safety_passed'])} | {entry['overall_status']} |"
        )
    aggregate = payload["terminal_evidence"]["aggregate_expectations"]
    lines += [
        "",
        "| aggregate | value |",
        "| --- | ---: |",
    ]
    for key, value in aggregate.items():
        if isinstance(value, dict):
            continue
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        f"| `h1_model_false_negatives` | "
        f"`{aggregate['h1_model_false_negatives']}` |",
        "",
        "## 2. What this conclusion does and does not say",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["conclusion"]["explicit_record"].items():
        lines.append(f"| `{key}` | {_flag(value)} |")
    lines += [
        "",
        "Prohibited conclusions, refused by name: "
        + ", ".join(f"`{c}`" for c in payload["conclusion"]["prohibited_conclusions"])
        + ".",
        "",
        "## 3. The evidence chain",
        "",
        payload["evidence_chain"]["narrative"],
        "",
    ]
    for stage in ("c7_c7_5", "c8", "c9", "c10", "c11_c11r1", "d5"):
        lines += [f"### {stage.upper().replace('_', '/')}", "",
                  "| field | value |", "| --- | --- |"]
        for key, value in payload["evidence_chain"][stage].items():
            lines.append(f"| `{key}` | `{value}` |")
        lines.append("")
    lines += [
        "> " + payload["evidence_chain"]["attribution"]["note"].strip(),
        "",
        "## 4. The closure decision",
        "",
        f"Applied identically to both variants: "
        f"{_flag(closure['applied_identically_to_both_variants'])}. Either "
        "variant labelled preferred, primary or less bad: "
        f"{_flag(closure['either_variant_labelled_preferred_primary_or_less_bad'])}.",
        "",
        "| field | value |",
        "| --- | --- |",
        f"| `channel_id` | `{closure['channel_id']}` |",
        f"| `variants` | `{closure['variants']}` |",
    ]
    for key, value in closure["fields"].items():
        lines.append(f"| `{key}` | `{value}` |")

    preservation = payload["preservation"]
    lines += [
        "",
        f"Closure checksum `{closure['closure_checksum']}`.",
        "",
        "## 5. Preservation",
        "",
        preservation["narrative"],
        "",
        f"**{preservation['artifacts_pinned']}** artifacts pinned, "
        f"**{preservation['artifacts_deleted']}** deleted, "
        f"**{preservation['artifacts_modified']}** modified. "
        f"`preservation_implies_continued_modeling_eligibility`: "
        f"{_flag(preservation['preservation_implies_continued_modeling_eligibility'])}.",
        "",
        "| artifact | content checksum |",
        "| --- | --- |",
    ]
    for name, digest in preservation["content_checksums"].items():
        lines.append(f"| `{name}` | `{digest}` |")
    lines += ["", "| generated table | byte checksum |", "| --- | --- |"]
    for path, digest in preservation["byte_checksums"].items():
        lines.append(f"| `{path}` | `{digest}` |")

    lines += [
        "",
        "## 6. Source validity is not modeling eligibility",
        "",
        "| question | status |",
        "| --- | --- |",
    ]
    questions = (
        ("Are the official EPPO source documents still valid evidence?",
         "official_eppo_source_documents_still_valid_evidence"),
        ("Are C7/C7.5 semantic decisions retained?",
         "c7_c7_5_semantic_decisions_retained"),
        ("Are C8 transformations reproducible?", "c8_transformations_reproducible"),
        ("Is sector-093 exposure reproducible?", "sector_093_exposure_reproducible"),
        ("Is the interaction architecture mathematically identifiable?",
         "interaction_architecture_mathematically_identifiable"),
        ("Was predictive utility demonstrated on development data?",
         "predictive_utility_demonstrated_on_development_data"),
        ("May the channel enter further operational modeling?",
         "may_enter_further_operational_modeling"),
        ("May the locked test be opened for this channel?",
         "may_open_the_locked_test_for_this_channel"),
    )
    for question, key in questions:
        value = payload["validity_versus_eligibility"][key]
        lines.append(f"| {question} | **{'Yes' if value else 'No'}** |")

    lines += [
        "",
        "## 7. Prohibited reopening reasons",
        "",
        "A new specification alone is not new evidence "
        f"(`new_specification_alone_is_new_evidence`: "
        f"{_flag(payload['new_specification_alone_is_new_evidence'])}). Each of "
        "these re-describes the evidence D5 already produced:",
        "",
    ]
    for reason in payload["prohibited_reopening_reasons"]:
        lines.append(f"* `{reason}`")

    lines += ["", "## 8. Permitted reopening evidence", ""]
    for name, description in payload["permitted_reopening_evidence"][
            "categories"].items():
        lines.append(f"* **`{name}`** - {description.strip()}")
    lines += [
        "",
        "Every reopening request must carry all of:",
        "",
    ]
    for field_name in payload["permitted_reopening_evidence"]["required_fields"]:
        lines.append(f"* `{field_name}`")
    lines += [
        "",
        "Without them, modeling entry "
        f"`{payload['permitted_reopening_evidence']['modeling_entry_without_these_fields']}`s.",
        "",
        "## 9. Enforcement",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    exercised = payload["enforcement"]["exercised"]
    for key in ("permitted_purposes_all_allowed", "blocked_purposes_all_refused",
                "closure_reason_is_specific", "closed_features_reported_as_missing",
                "unrelated_features_unaffected",
                "generic_upstream_feature_creation_altered",
                "historical_d5_reproducibility_preserved"):
        lines.append(f"| `{key}` | {_flag(exercised[key])} |")
    lines += [
        "",
        f"{len(exercised['probes'])} guard probes run against permitted and "
        "prohibited consumers. Blocked: "
        + ", ".join(f"`{p}`" for p in payload["enforcement"]["blocked_purposes"])
        + ". Permitted: "
        + ", ".join(f"`{p}`" for p in payload["enforcement"]["permitted_purposes"])
        + ".",
        "",
        "A closed feature is refused **with its closure reason**, never reported",
        "as missing - \"not found\" would send the next reader looking for a bug",
        "that does not exist.",
        "",
        "## 10. Final declaration",
        "",
    ]
    declarations = {
        "eppo_fuel_oil_modeling_channel_closed":
            "The EPPO fuel-oil modeling channel is closed.",
        "incremental_signal_was_not_demonstrated":
            "Incremental signal was not demonstrated.",
        "absence_of_an_effect_was_not_proven":
            "Absence of an effect was not proven.",
        "official_source_and_structural_artifacts_remain_preserved_and_valid_within_their_stated_limitations":
            "Official source and structural artifacts remain preserved and valid "
            "within their stated limitations.",
        "neither_fuel_oil_variant_is_selected":
            "Neither fuel-oil variant is selected.",
        "no_further_specification_search_is_authorized":
            "No further specification search is authorized.",
        "locked_final_test_remains_unopened":
            "The locked final test remains unopened.",
        "reopening_requires_genuinely_new_external_evidence":
            "Reopening requires genuinely new external evidence.",
    }
    for key in payload["final_declaration"]:
        lines.append(f"* **{declarations[key]}**")
    lines += ["", f"Content checksum `{payload['content_checksum']}`.", ""]
    (DOCS / "c12_channel_closure.md").write_text(
        guard_document("\n".join(lines) + "\n"), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
