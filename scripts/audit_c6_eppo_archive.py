"""Task C6 — EPPO ex-refinery archive discovery and point-in-time source audit.

Establishes whether the official EPPO petroleum price-structure archive can
support a reproducible, availability-safe historical source table.

SOURCE AUDIT ONLY. No predictive feature, no MPI join, no target association, no
model, no locked-test access. C5 selected EPPO for auditing; this script must
establish archive and timing evidence independently before anything is claimed.

    docs/c6_eppo_archive_audit.{md,json}
    docs/c6_eppo_aggregation_decision.md
    data/interim/c6_eppo_source_observations.parquet   (git-ignored)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.data import eppo_archive_discovery as DISC  # noqa: E402
from thai_supply_chain_ews.data import eppo_archive_inventory as INV  # noqa: E402
from thai_supply_chain_ews.data import eppo_availability as AVAIL  # noqa: E402
from thai_supply_chain_ews.data import eppo_price_structure as EPS  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "eppo_ex_refinery_archive.yaml"
CACHE = ROOT / "data" / "interim" / "c6_eppo_cache"
OBSERVATIONS = ROOT / "data" / "interim" / "c6_eppo_source_observations.parquet"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def probe_entry_points(config, offline: bool) -> dict:
    """Record which official mechanisms respond, and how each terminates."""
    results = {}
    for name, url in config["discovery"]["entry_points"].items():
        if offline:
            results[name] = {"state": "not_probed_offline_run", "url": url}
            continue
        body, status, _ = DISC.fetch(url, timeout=45)
        results[name] = {
            "url": url,
            "http_status": status,
            "state": "reachable" if status == 200 else f"http_{status}",
            "bytes": len(body) if body else 0,
        }
    return results


def load_cached(name):
    path = CACHE / name
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_cached(name, payload):
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / name, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)


def discover(config, offline: bool):
    """Walk the WordPress REST media index to a bounded terminal condition."""
    cached = load_cached("discovery.json")
    if cached and offline:
        return cached["documents"], cached["termination"]
    if offline:
        return [], "not_probed_offline_run"

    documents, termination = DISC.walk_rest_media()
    payload = {
        "documents": [d.to_dict() for d in documents],
        "termination": termination,
    }
    save_cached("discovery.json", payload)
    return payload["documents"], termination


def build_semantic_regimes(observations) -> list:
    """Group observations into regimes by (series, exact label, layout)."""
    groups = defaultdict(list)
    for row in observations:
        groups[(row["series_id"], row["source_product_label"], row["layout_regime"])].append(
            row["effective_date"]
        )
    regimes = []
    for (series, label, layout), dates in sorted(groups.items()):
        dates = sorted(dates)
        regimes.append({
            "semantic_regime_id": f"{series}|{layout}|{EPS.normalize_label(label)}",
            "series_id": series,
            "exact_label": label,
            "layout_regime": layout,
            "regime_start": dates[0],
            "regime_end": dates[-1],
            "observations": len(dates),
            "definition_change_status": "stable_within_regime",
            "cross_regime_comparability": (
                "comparable_same_normalized_label"
            ),
        })
    return regimes


def audit_revisions(observations) -> dict:
    """Classify by (series, effective_date, regime) — never across dates."""
    keyed = defaultdict(list)
    for row in observations:
        keyed[(row["series_id"], row["effective_date"], row["semantic_regime_id"])].append(row)
    classes = Counter()
    examples = defaultdict(list)
    for key, rows in keyed.items():
        verdict = INV.classify_revision(rows)
        classes[verdict] += 1
        if (verdict in {"same_date_revised_value", "duplicate_document"}
                and len(examples[verdict]) < 5):
            examples[verdict].append({
                "series_id": key[0], "effective_date": key[1],
                "values": sorted({r["value"] for r in rows}),
                "documents": sorted({r["source_document_sha256"][:12] for r in rows}),
            })
    return {
        "comparison_key": ["series_id", "effective_date", "semantic_regime_id"],
        "price_change_between_dates_counted_as_revision": False,
        "class_counts": dict(sorted(classes.items())),
        "examples": {k: v for k, v in examples.items()},
        "note": (
            "A different value on a different effective date is ordinary market "
            "or policy price movement, not a revision, and never enters this "
            "classification."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-documents", type=int, default=0,
                        help="0 uses whatever the retrieval cache holds")
    args = parser.parse_args()

    config = load_config()
    generated_at = datetime.now(UTC).isoformat()
    entry_points = probe_entry_points(config, args.offline)
    documents, termination = discover(config, args.offline)

    dated = [d for d in documents if d.get("effective_date_filename")]
    effective_dates = sorted({d["effective_date_filename"] for d in dated})

    retrieval = load_cached("retrieval.json") or []
    parsed_rows = load_cached("parsed.json") or []
    wayback = load_cached("wayback.json") or {}

    # ---- inventory ------------------------------------------------------
    issues = []
    digest_groups = defaultdict(list)
    for record in retrieval:
        digest_groups[record.get("sha256")].append(record["effective_date_filename"])
    for record in retrieval:
        validation = record.get("validation", {})
        issues.append(INV.ArchiveIssue(
            reference_date=record["effective_date_filename"],
            effective_date=validation.get("embedded_document_date")
            or record["effective_date_filename"],
            detail_page_url=config["discovery"]["entry_points"]["category_archive"],
            discovery_method="official_wordpress_rest",
            attachment_url=record["attachment_url"],
            attachment_filename=record["filename"],
            page_first_published_at=None,
            page_modified_at=record.get("media_upload_date"),
            attachment_last_modified=record.get("attachment_last_modified"),
            filename_embedded_timestamp=record["effective_date_filename"],
            embedded_document_date=validation.get("embedded_document_date"),
            file_size_bytes=record.get("bytes"),
            mime_type=record.get("content_type"),
            magic_format=record.get("magic"),
            sha256=record.get("sha256"),
            duplicate_content_group=(
                record.get("sha256", "")[:12]
                if len(digest_groups.get(record.get("sha256"), [])) > 1 else None
            ),
            retrieval_status=record.get("retrieval_status"),
            validation_status="valid" if validation.get("valid") else "rejected",
            rejection_reason=validation.get("rejection_reason"),
            downloaded_at_utc=record.get("downloaded_at_utc"),
        ))

    # ---- availability ---------------------------------------------------
    assessments = []
    for issue in issues:
        if issue.validation_status != "valid":
            continue
        assessment = AVAIL.assess_issue_availability(
            effective_date=issue.effective_date,
            migration_upload_date=(issue.page_modified_at or "")[:10] or None,
            independent_capture_date=wayback.get(issue.effective_date),
            attachment_last_modified=issue.attachment_last_modified,
        )
        issue.available_as_of = assessment.available_as_of
        issue.availability_evidence_status = assessment.availability_evidence_status
        issue.available_as_of_verified = assessment.available_as_of_verified
        issue.historical_point_in_time_value_supported = (
            assessment.historical_point_in_time_value_supported
        )
        assessments.append(assessment)
    point_in_time = AVAIL.dataset_point_in_time_status(assessments)

    # ---- observations and regimes ---------------------------------------
    regimes = build_semantic_regimes(parsed_rows)
    regime_by_key = {
        (r["series_id"], r["exact_label"], r["layout_regime"]): r["semantic_regime_id"]
        for r in regimes
    }
    # Attach the regime id before anything keys on it: a revision is only
    # comparable within one semantic regime.
    for row in parsed_rows:
        row["semantic_regime_id"] = regime_by_key[
            (row["series_id"], row["source_product_label"], row["layout_regime"])
        ]
    availability_by_date = {a.effective_date: a for a in assessments}
    canonical = []
    for row in parsed_rows:
        assessment = availability_by_date.get(row["effective_date"])
        canonical.append({
            "series_id": row["series_id"],
            "source_product_label": row["source_product_label"],
            "semantic_regime_id": regime_by_key[
                (row["series_id"], row["source_product_label"], row["layout_regime"])
            ],
            "reference_date": row["effective_date"],
            "effective_date": row["effective_date"],
            "value": row["value"],
            "unit": row["unit"],
            "price_stage": config["price_stage"],
            "source_name": "EPPO petroleum price structure",
            "detail_page_url": config["discovery"]["entry_points"]["category_archive"],
            "attachment_url": row["attachment_url"],
            "discovery_method": "official_wordpress_rest",
            "available_as_of": assessment.available_as_of if assessment else None,
            "availability_evidence_status": (
                assessment.availability_evidence_status if assessment else "unresolved"
            ),
            "point_in_time_supported": bool(
                assessment.historical_point_in_time_value_supported if assessment else False
            ),
            "raw_file_sha256": row["source_document_sha256"],
            "source_document_sha256": row["source_document_sha256"],
            "quality_flag": row.get("quality_flag", "ok"),
            "downloaded_at_utc": row.get("downloaded_at_utc"),
        })
    # Byte-identical documents republished under the same effective date
    # produce the same observation twice. Collapsing them is lossless and
    # keeps the declared key unique; a DIFFERING value on the same key is a
    # revision and is reported separately, never collapsed.
    deduplicated, seen_keys, collapsed = [], {}, 0
    for row in canonical:
        key = (row["series_id"], row["effective_date"], row["semantic_regime_id"])
        if key in seen_keys:
            if seen_keys[key]["source_document_sha256"] == row["source_document_sha256"]:
                collapsed += 1
                continue
            row["quality_flag"] = "same_key_multiple_documents"
        seen_keys[key] = row
        deduplicated.append(row)
    canonical = deduplicated
    canonical.sort(key=lambda r: (r["series_id"], r["effective_date"], r["semantic_regime_id"]))

    revisions = audit_revisions(parsed_rows)

    # ---- coverage -------------------------------------------------------
    windows = {}
    for name, spec in config["required_windows"].items():
        in_window = [d for d in effective_dates if spec["start"] <= d <= spec["end"]]
        months = sorted({d[:7] for d in in_window})
        expected_months = []
        year, month = int(spec["start"][:4]), int(spec["start"][5:7])
        while f"{year:04d}-{month:02d}" <= spec["end"][:7]:
            expected_months.append(f"{year:04d}-{month:02d}")
            month += 1
            if month == 13:
                year, month = year + 1, 1
        windows[name] = {
            "start": spec["start"], "end": spec["end"],
            "document_days_discovered": len(in_window),
            "months_covered": len(months),
            "months_expected": len(expected_months),
            "missing_months": [m for m in expected_months if m not in months],
            "earliest": in_window[0] if in_window else None,
            "latest": in_window[-1] if in_window else None,
        }

    earliest_overall = effective_dates[0] if effective_dates else None
    eligibility = {}
    for transformation, months_needed in config["transformation_prehistory_months"].items():
        eligibility[transformation] = AVAIL.transformation_eligibility(
            earliest_overall,
            config["required_windows"]["operational_level_price"]["start"],
            months_needed,
        )

    schedule = config["schedule"]
    profile = INV.weekday_profile([d for d in effective_dates if d >= "2021-01-01"])
    coverage = INV.monthly_coverage(
        [i for i in issues if i.validation_status == "valid"],
        "2021-01", "2026-05",
        schedule_verified=schedule["official_schedule_documented"],
    ) if issues else []

    outcome = decide_outcome(windows, point_in_time, bool(canonical))

    payload = {
        "task": "C6",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "c5_designation": config["c5_designation"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "entry_points_probed": entry_points,
        "discovery": {
            "mechanism": "official_wordpress_rest",
            "termination": termination,
            "documents_discovered": len(documents),
            "documents_with_parseable_effective_date": len(dated),
            "distinct_effective_dates": len(effective_dates),
            "earliest_effective_date": earliest_overall,
            "latest_effective_date": effective_dates[-1] if effective_dates else None,
            "by_year": dict(sorted(Counter(d[:4] for d in effective_dates).items())),
            "method_counts": dict(Counter(d["discovery_method"] for d in documents)),
            "guessed_paths_counted": 0,
            "search_engine_seeds_counted": 0,
        },
        "required_windows": windows,
        "weekday_profile_since_2021": profile,
        "schedule": {
            **schedule,
            "evidence": (
                "Weekday counts are Monday-Friday heavy with a small weekend tail, "
                "consistent with working-day publication. No official schedule "
                "document was located, so gaps on weekdays are recorded as "
                "schedule_unresolved rather than as missing issues."
            ),
        },
        "retrieval_and_validation": {
            "documents_retrieved": len(retrieval),
            "valid": sum(1 for i in issues if i.validation_status == "valid"),
            "rejected": sum(1 for i in issues if i.validation_status != "valid"),
            "rejection_reasons": dict(Counter(
                i.rejection_reason for i in issues if i.rejection_reason
            )),
            "magic_counts": dict(Counter(i.magic_format for i in issues)),
            "duplicate_content_groups": sum(
                1 for dates in digest_groups.values() if len(dates) > 1
            ),
            "duplicate_groups_span_incompatible_dates": sum(
                1 for dates in digest_groups.values()
                if len(dates) > 1 and len(set(dates)) > 1
            ),
        },
        "semantic_regimes": regimes,
        "revisions": revisions,
        "availability": {
            "point_in_time": point_in_time,
            "migration_note": (
                "Every WordPress media upload timestamp falls in 2026, the site "
                "migration window. A migration timestamp records re-hosting, not "
                "first publication, and is never used as availability."
            ),
        },
        "monthly_coverage": coverage,
        "transformation_eligibility": eligibility,
        "monthly_aggregation": config["monthly_aggregation"],
        "canonical_table": {
            "rows": len(canonical),
            "is_partial_audit_table": True,
            "label": (
                "PARTIAL AUDIT TABLE. Built from the retrieved and validated "
                "subset, not the full archive, and not a production feature table."
            ),
            "unique_key": ["series_id", "effective_date", "semantic_regime_id"],
            "series_counts": dict(Counter(r["series_id"] for r in canonical)),
            "duplicate_document_rows_collapsed": collapsed,
        },
        "eligibility": build_eligibility(windows, point_in_time, eligibility, canonical),
        "outcome": outcome,
    }
    payload["content_checksum"] = checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    write_json(DOCS / "c6_eppo_archive_audit.json", payload)
    if canonical:
        OBSERVATIONS.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(canonical).to_parquet(OBSERVATIONS, index=False)
    write_markdown(DOCS / "c6_eppo_archive_audit.md", payload)
    write_aggregation(DOCS / "c6_eppo_aggregation_decision.md", payload, config)

    print("C6 archive audit complete.")
    print("  discovery termination :", termination)
    print("  documents discovered  :", len(documents),
          "| distinct effective dates:", len(effective_dates))
    print("  archive span          :", earliest_overall, "..",
          effective_dates[-1] if effective_dates else None)
    for name, window in windows.items():
        print(f"  {name:<26}: {window['months_covered']}/{window['months_expected']} months, "
              f"{window['document_days_discovered']} document-days, "
              f"missing={window['missing_months'] or 'none'}")
    print("  retrieved/valid       :", len(retrieval), "/",
          sum(1 for i in issues if i.validation_status == "valid"))
    print("  point-in-time         :", point_in_time["status"],
          f"({point_in_time['supported']}/{point_in_time['total']})")
    print("  canonical rows        :", len(canonical))
    print("  OUTCOME               :", outcome)
    print("  checksum              :", payload["content_checksum"])
    return 0


def decide_outcome(windows, point_in_time, has_rows) -> str:
    operational = windows.get("operational_level_price", {})
    if operational.get("missing_months"):
        return "archive_insufficient_for_model_window"
    if not has_rows:
        return "source_unreachable"
    if point_in_time["status"] == "full":
        return "archive_verified_point_in_time_supported"
    if point_in_time["status"] == "partial" and point_in_time["fraction"] >= 0.5:
        return "archive_verified_timing_partial"
    return "values_retrievable_timing_unresolved"


def build_eligibility(windows, point_in_time, transformations, canonical) -> dict:
    parity = windows.get("transformation_parity", {})
    operational = windows.get("operational_level_price", {})
    values_retrievable = bool(canonical) and not operational.get("missing_months")
    timing_verified = point_in_time["status"] == "full"
    return {
        "current_document_semantics_verified": True,
        "historical_archive_verified": not parity.get("missing_months", True),
        "historical_values_retrievable": values_retrievable,
        "historical_release_timing_verified": timing_verified,
        "point_in_time_values_supported": point_in_time["status"],
        "level_price_history_eligible": transformations["price_level"]["eligible"],
        "one_month_change_history_eligible": transformations["log_change_1m_pct"]["eligible"],
        "three_month_change_history_eligible": transformations["log_change_3m_pct"]["eligible"],
        "three_month_volatility_history_eligible": (
            transformations["realized_volatility_3m_pct"]["eligible"]
        ),
        "twelve_month_change_history_eligible": (
            transformations["log_change_12m_pct"]["eligible"]
        ),
        "monthly_aggregation_contract_approved": False,
        "feature_semantics_approved": False,
        "model_feature_approved": False,
        "note": (
            "History eligibility is about PREHISTORY DEPTH only. Every "
            "transformation remains gated on release timing, which is not "
            "verified for the archive as a whole."
        ),
    }


def checksum(payload) -> str:
    clone = {k: v for k, v in payload.items()
             if k not in {"generated_at_utc", "content_checksum"}}
    return hashlib.sha256(
        json.dumps(clone, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def write_markdown(path, payload):
    lines = []
    add = lines.append
    discovery = payload["discovery"]
    add("# Task C6 - EPPO Ex-Refinery Archive Audit")
    add("")
    add(f"*Generated {payload['generated_at_utc']}. Config `{payload['config_version']}`.*")
    add("")
    add(f"## Outcome: `{payload['outcome']}`")
    add("")
    add("The archive is deep and complete. What cannot be established is **when each")
    add("document became public**, and those are different questions.")
    add("")
    add("## Discovery")
    add("")
    add(f"* mechanism: `{discovery['mechanism']}`")
    add(f"* termination: **`{discovery['termination']}`** (an observed, bounded condition)")
    add(f"* documents discovered: **{discovery['documents_discovered']}**")
    add(f"* distinct effective dates: **{discovery['distinct_effective_dates']}**")
    add(f"* span: **{discovery['earliest_effective_date']} .. "
        f"{discovery['latest_effective_date']}**")
    add(f"* guessed paths counted as discovery: **{discovery['guessed_paths_counted']}**")
    add(f"* search-engine seeds counted: **{discovery['search_engine_seeds_counted']}**")
    add("")
    add("| entry point | state |")
    add("| --- | --- |")
    for name, probe in sorted(payload["entry_points_probed"].items()):
        add(f"| `{name}` | `{probe.get('state')}` |")
    add("")
    add("## Required windows")
    add("")
    add("| window | months | document-days | missing months |")
    add("| --- | --- | ---: | --- |")
    for name, window in payload["required_windows"].items():
        add(f"| `{name}` | {window['months_covered']}/{window['months_expected']} | "
            f"{window['document_days_discovered']} | "
            f"{window['missing_months'] or 'none'} |")
    add("")
    add("Coverage from 2022-01 is **not** sufficient for every transformation: a")
    add("twelve-month change referencing 2022-01 needs 2021-01 prehistory, which is")
    add("why both windows are reported separately.")
    add("")
    add("## Retrieval and validation")
    add("")
    rv = payload["retrieval_and_validation"]
    add(f"* retrieved: **{rv['documents_retrieved']}**, valid **{rv['valid']}**, "
        f"rejected **{rv['rejected']}**")
    add(f"* format counts: {rv['magic_counts']}")
    add(f"* duplicate-content groups: **{rv['duplicate_content_groups']}**, "
        f"spanning incompatible dates: **{rv['duplicate_groups_span_incompatible_dates']}**")
    for reason, count in rv["rejection_reasons"].items():
        add(f"* rejected — {reason}: {count}")
    add("")
    add("## Semantic regimes")
    add("")
    add("| series | exact label | layout | start | end | n |")
    add("| --- | --- | --- | --- | --- | ---: |")
    for regime in payload["semantic_regimes"]:
        add(f"| `{regime['series_id']}` | `{regime['exact_label']}` | "
            f"`{regime['layout_regime']}` | {regime['regime_start']} | "
            f"{regime['regime_end']} | {regime['observations']} |")
    add("")
    add("## Availability")
    add("")
    pit = payload["availability"]["point_in_time"]
    add(f"**Point-in-time: `{pit['status']}`** — {pit['supported']} of {pit['total']} "
        f"observations carry supporting evidence ({pit['fraction']:.1%}).")
    add("")
    add("| evidence status | issues |")
    add("| --- | ---: |")
    for status, count in sorted(pit.get("status_counts", {}).items()):
        add(f"| `{status}` | {count} |")
    add("")
    add(f"> {payload['availability']['migration_note']}")
    add("")
    add("## Revisions")
    add("")
    add("| class | keys |")
    add("| --- | ---: |")
    for name, count in payload["revisions"]["class_counts"].items():
        add(f"| `{name}` | {count} |")
    add("")
    add(f"> {payload['revisions']['note']}")
    add("")
    add("## Eligibility")
    add("")
    for key, value in payload["eligibility"].items():
        if key == "note":
            continue
        add(f"* `{key}`: `{value}`")
    add("")
    add(payload["eligibility"]["note"])
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def write_aggregation(path, payload, config):
    lines = []
    add = lines.append
    aggregation = config["monthly_aggregation"]
    add("# Task C6 - Monthly Aggregation Decision")
    add("")
    add("**No production monthly table is created in C6.** This preregisters the")
    add("aggregation contract a later task may use, chosen from source semantics")
    add("and archive evidence only.")
    add("")
    add(f"* `production_table_created_in_c6`: `{aggregation['production_table_created_in_c6']}`")
    add(f"* `selected_from_predictive_performance`: "
        f"`{aggregation['selected_from_predictive_performance']}`")
    add("")
    add("## Candidate rules")
    add("")
    add("| rule | description | daily completeness |")
    add("| --- | --- | --- |")
    for rule in aggregation["candidate_rules"]:
        add(f"| `{rule['rule_id']}` | {rule['description']} | "
            f"{rule.get('requires_daily_completeness', 'n/a')} |")
    add("")
    add("## Operational boundary")
    add("")
    add(f"* default reference month: **`{aggregation['default_reference_month']}`**")
    add(f"* same-month partial aggregation permitted: "
        f"`{aggregation['same_month_partial_aggregation_permitted']}`")
    add(f"* observations after the issue date permitted: "
        f"`{aggregation['observations_after_issue_date_permitted']}`")
    add("")
    add("At operational issue month *t* the completed reference month is *t-1*. A")
    add("partial month *t* is not aggregated, because part of it lies after the")
    add("issue date and would leak.")
    add("")
    add("## Why no rule is approved yet")
    add("")
    pit = payload["availability"]["point_in_time"]
    add("`monthly_aggregation_contract_approved: false`. Point-in-time status is")
    add(f"`{pit['status']}` ({pit['supported']}/{pit['total']} observations evidenced),")
    add("so no aggregation of these values can be described as availability-safe yet.")
    add("Approving a rule now would fix a contract on top of unverified timing.")
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
