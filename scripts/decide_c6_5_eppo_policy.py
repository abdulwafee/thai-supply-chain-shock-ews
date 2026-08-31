"""Task C6.5 — EPPO latest-vintage use decision and availability contract.

Reproduces the C6 invariants from production artifacts, audits the 43 capture
records for what they can actually support, and records the project policy
decision on whether EPPO may be used in a release-lag-aware latest-vintage
exploratory analysis.

DECISION AND AUDIT ONLY. No petroleum feature, no monthly aggregation, no MPI
join, no target association, no model, no locked-test access. D4 metrics are
read for nothing and never recalculated.

    docs/c6_5_eppo_latest_vintage_decision.{md,json}
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

from thai_supply_chain_ews.data import eppo_latest_vintage_policy as POLICY  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "eppo_latest_vintage_policy.yaml"
C6_AUDIT = DOCS / "c6_eppo_archive_audit.json"
CACHE = ROOT / "data" / "interim" / "c6_eppo_cache"
OBSERVATIONS = ROOT / "data" / "interim" / "c6_eppo_source_observations.parquet"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_cached(name):
    with open(CACHE / name, encoding="utf-8") as handle:
        return json.load(handle)


def reproduce_c6_invariants() -> dict:
    """Recompute every C6 invariant from production artifacts.

    Stops the task if a material invariant fails — a policy decision built on
    numbers that no longer reproduce would be worthless.
    """
    audit = json.loads(C6_AUDIT.read_text(encoding="utf-8"))
    discovery = load_cached("discovery.json")
    retrieval = load_cached("retrieval.json")
    parsed = load_cached("parsed.json")
    captures = load_cached("wayback.json")
    frame = pd.read_parquet(OBSERVATIONS)

    effective = sorted({
        d["effective_date_filename"] for d in discovery["documents"]
        if d["effective_date_filename"]
    })
    valid = [r for r in retrieval if r["validation"]["valid"]]
    valid_dates = {r["effective_date_filename"] for r in valid}
    operational = [d for d in effective if "2022-01-01" <= d <= "2026-05-31"]
    parity = [d for d in effective if "2021-01-01" <= d <= "2026-05-31"]
    revisions = audit["revisions"]["class_counts"]

    hsd_dates = {p["effective_date"] for p in parsed
                 if p["series_id"] == "eppo_ex_refinery_hsd"}
    all_dates = {p["effective_date"] for p in parsed}
    hsd_missing = sorted(all_dates - hsd_dates)

    def labels(series_id):
        return {p["source_product_label"] for p in parsed if p["series_id"] == series_id}

    checks = {
        "discovered_media_documents": (len(discovery["documents"]), 5233),
        "distinct_effective_dates": (len(effective), 4976),
        "discovery_earliest": (effective[0], "2002-02-03"),
        "discovery_latest": (effective[-1], "2026-08-28"),
        "retrieved_documents": (len(retrieval), 256),
        "validated_documents": (len(valid), 254),
        "parity_months": (len({d[:7] for d in parity}), 65),
        "operational_months": (len({d[:7] for d in operational}), 53),
        "parity_document_days": (len(parity), 1315),
        "operational_document_days": (len(operational), 1076),
        "canonical_partial_rows": (len(frame), 722),
        "independent_captures": (len(captures), 43),
        "capture_overlap_with_validated": (len(set(captures) & valid_dates), 0),
        "verified_available_as_of": (audit["availability"]["point_in_time"]["supported"], 0),
        "single_vintage_only": (revisions.get("single_vintage_only"), 707),
        "duplicate_document": (revisions.get("duplicate_document"), 15),
        "same_date_revised_value": (revisions.get("same_date_revised_value", 0), 0),
        "hsd_missing_days_january_2024": (len(hsd_missing), 22),
        "hsd_gaps_all_in_january_2024": (
            all(d.startswith("2024-01") for d in hsd_missing), True
        ),
        "fo600_label_stable": (labels("eppo_ex_refinery_fo600_2s"), {"FO 600 (1) 2%S"}),
        "fo1500_label_stable": (labels("eppo_ex_refinery_fo1500_2s"), {"FO 1500 (2) 2%S"}),
    }

    results, failures = {}, []
    for name, (actual, expected) in checks.items():
        passed = actual == expected
        if not passed:
            failures.append(f"{name}: expected {expected}, got {actual}")
        results[name] = {
            "actual": sorted(actual) if isinstance(actual, set) else actual,
            "expected": sorted(expected) if isinstance(expected, set) else expected,
            "reproduced": passed,
        }
    if failures:
        raise SystemExit("C6.5 FAILED: C6 invariants did not reproduce: " + "; ".join(failures))

    return {
        "all_reproduced": True,
        "checks": results,
        "captures": captures,
        "hsd_missing_days": hsd_missing,
    }


def audit_captures(config, captures) -> dict:
    """Classify every capture record for what it can support."""
    settings = config["capture_audit"]
    assessments = [
        POLICY.classify_capture(
            effective_date=effective,
            capture_date=capture,
            capture_provider=settings["provider"],
            captured_url=None,
            original_bytes_available=settings["archived_bytes_fetched"],
            source_identity_validated=settings["source_identity_validated"],
            window_days=settings["contemporaneous_window_days"],
        )
        for effective, capture in sorted(captures.items())
    ]
    summary = POLICY.summarize_captures(assessments)
    summary["records"] = [a.to_dict() for a in assessments]
    summary["capture_date_is_first_publication_date"] = False
    summary["archived_bytes_fetched"] = settings["archived_bytes_fetched"]
    summary["source_identity_validated"] = settings["source_identity_validated"]
    summary["contemporaneous_window_days"] = settings["contemporaneous_window_days"]
    summary["window_is_a_convention_not_a_measurement"] = True
    return summary


def build_availability_examples(config) -> list:
    """Show the availability contract on concrete months."""
    lag = config["policy"]["operational_policy_lag_months"]
    examples = []
    for reference in ("2022-01", "2024-01", "2026-05"):
        availability = POLICY.observation_availability(reference, lag_months=lag)
        examples.append(availability.to_dict())
    return examples


def build_permitted_examples(config) -> list:
    lag = config["policy"]["operational_policy_lag_months"]
    rows = []
    for issue in ("2024-01", "2025-03", "2026-05"):
        rows.append({
            "issue_month": issue,
            "latest_permitted_reference_month": POLICY.permitted_reference_month(issue, lag),
            "same_month_permitted": False,
            "lag_1m_permitted": False,
        })
    return rows


def checksum(payload) -> str:
    clone = {k: v for k, v in payload.items()
             if k not in {"generated_at_utc", "content_checksum"}}
    return hashlib.sha256(
        json.dumps(clone, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_config()
    invariants = reproduce_c6_invariants()
    captures = audit_captures(config, invariants.pop("captures"))

    payload = {
        "task": "C6.5",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "config_version": config["config_version"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "c6_invariants": invariants,
        "evidence_boundaries": config["evidence_boundaries"],
        "ingestion_levels": config["ingestion_levels"],
        "capture_audit": captures,
        "decision": config["decision"],
        "policy": config["policy"],
        "interpretation": config["interpretation"],
        "observation_availability_fields": config["observation_availability_fields"],
        "availability_examples": build_availability_examples(config),
        "permitted_reference_months": build_permitted_examples(config),
        "rationale_for": config["rationale_for"],
        "rationale_against": config["rationale_against"],
        "series_decisions": config["series_decisions"],
        "transformation_status": config["transformation_status"],
        "transformation_readiness_blockers": config["transformation_readiness_blockers"],
        "c7_authorization": config["c7_authorization"],
    }
    payload["content_checksum"] = checksum(payload)

    write_json(DOCS / "c6_5_eppo_latest_vintage_decision.json", payload)
    write_markdown(DOCS / "c6_5_eppo_latest_vintage_decision.md", payload)

    print("C6.5 policy decision recorded.")
    print("  C6 invariants reproduced :", invariants["all_reproduced"],
          f"({len(invariants['checks'])} checks)")
    print("  captures classified      :", captures["evidence_class_counts"])
    print("  usable upper bounds      :", captures["usable_upper_bounds"])
    print("  minimum VERIFIED lag     :", captures["minimum_verified_publication_lag_months"])
    print("  DECISION                 :", payload["decision"])
    print("  policy lag (not measured):", payload["policy"]["operational_policy_lag_months"],
          "| measured:", payload["policy"]["operational_lag_is_measured"])
    print("  point-in-time supported  :", payload["policy"]["point_in_time_values_supported"])
    authorization = payload["c7_authorization"]
    print("  C7 ingestion authorized  :",
          authorization["c7_full_archive_ingestion_authorized"])
    print("  C7 aggregation           :",
          authorization["c7_monthly_source_aggregation_authorized"])
    print("  C7 features / modeling   :",
          authorization["c7_predictive_feature_creation_authorized"], "/",
          authorization["c7_modeling_authorized"])
    print("  checksum                 :", payload["content_checksum"])
    return 0


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def write_markdown(path, payload):
    lines = []
    add = lines.append
    policy = payload["policy"]
    add("# Task C6.5 - EPPO Latest-Vintage Use Decision")
    add("")
    add(f"*Generated {payload['generated_at_utc']}. Config `{payload['config_version']}`.*")
    add("")
    add(f"## Decision: `{payload['decision']}`")
    add("")
    add("EPPO ex-refinery prices may be used in a **release-lag-aware latest-vintage")
    add("exploratory** analysis, on the same footing D3 already put the MPI target.")
    add("That permission is narrow, and the fields below say exactly how narrow.")
    add("")
    add("## Measured lag versus policy lag")
    add("")
    add("| field | value |")
    add("| --- | --- |")
    measured = policy["minimum_verified_publication_lag_months"]
    add(f"| `minimum_verified_publication_lag_months` | **`{measured}`** |")
    add(f"| `operational_policy_lag_months` | **{policy['operational_policy_lag_months']}** |")
    add(f"| `operational_lag_is_measured` | **`{policy['operational_lag_is_measured']}`** |")
    add(f"| `operational_lag_basis` | `{policy['operational_lag_basis']}` |")
    add("")
    add("**No publication delay was measured.** The two-month lag is a conservative")
    add("assumption the project imposes on itself, not an observation about EPPO.")
    add("")
    add(f"> {payload['interpretation']['meaning']}")
    add("")
    add("| issue month *t* | latest permitted reference month |")
    add("| --- | --- |")
    for row in payload["permitted_reference_months"]:
        add(f"| {row['issue_month']} | **{row['latest_permitted_reference_month']}** |")
    add("")
    add("`same_month_use_permitted: false`, `publication_lag_1m_use_permitted: false`.")
    add("")
    add("## Availability fields stay separate")
    add("")
    add("| reference month | `source_available_as_of` | `policy_available_month` | basis |")
    add("| --- | --- | --- | --- |")
    for example in payload["availability_examples"]:
        add(f"| {example['reference_month']} | `{example['source_available_as_of']}` | "
            f"`{example['policy_available_month']}` | `{example['availability_basis']}` |")
    add("")
    add("A policy-derived month is **never** written into `source_available_as_of`;")
    add("that field means the source is evidenced to have been public by that date,")
    add("and it stays null for every historical observation.")
    add("")
    add("## Evidence boundaries")
    add("")
    boundaries = payload["evidence_boundaries"]
    for key in ("legacy_archive_status", "historical_timing_status",
                "monthly_presence_coverage", "complete_daily_document_validation",
                "point_in_time_values_supported"):
        add(f"* `{key}`: `{boundaries[key]}`")
    add("")
    add(f"> {boundaries['statement']}")
    add("")
    add("Superseded wording:")
    for claim in boundaries["superseded_wording"]:
        add(f"* ~~{claim}~~")
    add("")
    add("## Archive presence is not complete ingestion")
    add("")
    levels = payload["ingestion_levels"]
    add("| level | status |")
    add("| --- | --- |")
    for key in ("monthly_document_presence_verified", "complete_daily_inventory_discovered",
                "complete_daily_documents_downloaded", "complete_daily_documents_validated",
                "monthly_aggregation_contract_approved"):
        add(f"| `{key}` | `{levels[key]}` |")
    add("")
    add(f"> {levels['note']}")
    add("")
    add("## The 43 captures")
    add("")
    capture = payload["capture_audit"]
    add("| evidence class | records |")
    add("| --- | ---: |")
    for name, count in capture["evidence_class_counts"].items():
        add(f"| `{name}` | {count} |")
    add("")
    add(f"* usable upper bounds: **{capture['usable_upper_bounds']}**")
    proves = capture["any_capture_proves_first_release"]
    add(f"* any capture proves a first release: **`{proves}`**")
    add(f"* archived bytes fetched: `{capture['archived_bytes_fetched']}`, "
        f"identity validated: `{capture['source_identity_validated']}`")
    add("")
    add(f"> {capture['note']}")
    add("")
    add("## Rationale")
    add("")
    add("**For:**")
    for item in payload["rationale_for"]:
        add(f"* {item}")
    add("")
    add("**Against:**")
    for item in payload["rationale_against"]:
        add(f"* {item}")
    add("")
    add("## Series decisions")
    add("")
    add("| series | exact label | C7 ingestion | semantic status |")
    add("| --- | --- | --- | --- |")
    for series, entry in sorted(payload["series_decisions"].items()):
        add(f"| `{series}` | `{entry['exact_label']}` | "
            f"`{entry['eligible_for_c7_full_archive_ingestion']}` | "
            f"`{entry['semantic_status']}` |")
    add("")
    hsd = payload["series_decisions"]["eppo_ex_refinery_hsd"]
    add(f"H-DIESEL is **conditional**: {hsd['ordinary_h_diesel_missing_days']} days in")
    add("January 2024 publish only blend definitions. "
        f"`silent_blend_substitution_permitted: {hsd['silent_blend_substitution_permitted']}`, ")
    add(f"`imputation_permitted: {hsd['imputation_permitted']}`. {hsd['january_2024_handling']}")
    add("")
    add("## Transformation status")
    add("")
    add("| transformation | historical depth sufficient | source ready |")
    add("| --- | --- | --- |")
    for name, entry in payload["transformation_status"].items():
        add(f"| `{name}` | `{entry['historical_depth_sufficient']}` | "
            f"`{entry['source_ready_for_transformation']}` |")
    add("")
    add("Depth and readiness are different questions. Blockers:")
    for blocker in payload["transformation_readiness_blockers"]:
        add(f"* {blocker}")
    add("")
    add("## C7 authorization boundary")
    add("")
    for key, value in payload["c7_authorization"].items():
        if key == "aggregation_condition":
            continue
        add(f"* `{key}`: `{value}`")
    add("")
    add(f"> {payload['c7_authorization']['aggregation_condition']}")
    add("")
    add(f"`eligible_for_confirmatory_claims: {policy['eligible_for_confirmatory_claims']}`, ")
    add(f"`eligible_for_locked_test: {policy['eligible_for_locked_test']}`, ")
    add(f"`feature_semantics_approved: {policy['feature_semantics_approved']}`, ")
    add(f"`model_feature_approved: {policy['model_feature_approved']}`.")
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
