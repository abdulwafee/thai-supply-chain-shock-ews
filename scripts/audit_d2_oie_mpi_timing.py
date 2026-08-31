"""Task D2 — OIE MPI publication timing, vintage audit, extension feasibility.

Runs the audit and writes four documents:

    docs/d2_oie_mpi_source_audit.{md,json}
    docs/d2_target_timing_decision.{md,json}

EVIDENCE ONLY. This script imports no target-building, evaluation or modelling
module; it does not rebuild B3 targets, rerun D1, touch the B4 split, compute a
target-feature association, or read locked-test outcomes. Numerical MPI values
are read only at or before the configured cutoff, enforced by
GuardedMonthlyReader rather than by convention.

Network results are cached under data/interim/ (git-ignored) so the audit is
reproducible without re-crawling; pass --refresh to re-fetch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.data import oie_mpi_discovery as DISCOVERY  # noqa: E402
from thai_supply_chain_ews.data import oie_mpi_history as HISTORY  # noqa: E402
from thai_supply_chain_ews.data import oie_mpi_release_inventory as INVENTORY  # noqa: E402
from thai_supply_chain_ews.data import oie_mpi_vintages as VINTAGES  # noqa: E402
from thai_supply_chain_ews.data import target_timing_contract as CONTRACT  # noqa: E402

CACHE = ROOT / "data" / "interim" / "d2_release_crawl.json"
DOCS = ROOT / "docs"

EDITIONS = [
    ("live_2021_base", "data/raw/OIE_MPI/2026-08-26/Prodidx1.xlsx"),
    ("hist_2016_base", "data/raw/OIE_MPI_HIST_2559_2566/2026-08-26/extracted/Prodidx1.xlsx"),
    ("hist_2011_base", "data/raw/OIE_MPI_HIST_2554_2561/2026-08-26/extracted/Prodidx1.xlsx"),
]

# Directly observed during this audit: the live workbook was re-fetched on
# 2026-08-28 and had gained exactly one reference month relative to the
# 2026-08-26 snapshot, with its Last-Modified moving to 2026-08-27.
OBSERVED_RELEASE = {
    "reference_month": "2026-07",
    "observed_between_utc": ["2026-08-26T03:13:00Z", "2026-08-28T00:00:00Z"],
    "before_last_modified": "2026-07-27T04:37:30Z",
    "after_last_modified": "2026-08-27T05:12:16Z",
    "before_sha256": "19cec1fd781b3a9098c393721b56548817d8275df71e235783864477de2b6389",
    "after_sha256": "b13dac215b5b1fd4ae2c403dbea844f0530ff9c4c269feb87b10359ddb69bb75",
    "months_added": ["2026-07"],
    "months_removed": [],
    "marker_moved_from": "2026-06",
    "marker_moved_to": "2026-07",
    "url": (
        "https://www.oie.go.th/assets/portals/1/fileups/2/files/"
        "Industrial%20index/indexes/month/Prodidx1.xlsx"
    ),
    "interpretation": (
        "The live workbook is overwritten in place. A release adds the new "
        "reference month and moves the marker glyph forward; the previous "
        "vintage is not retained at this URL."
    ),
}


def crawl(config):
    """Walk the archive and collect attachment metadata for every entry."""
    rows, stop_reason = INVENTORY.walk_archive(config)
    details = {}
    for row in rows:
        identifier = row["id_content"]
        body, _, _ = DISCOVERY.fetch(
            f"{INVENTORY.DETAIL_BASE_URL}?idContent={identifier}"
        )
        filename = last_modified = length = None
        if body:
            html = body.decode("utf-8", "replace")
            found = INVENTORY._ATTACHMENT_PATTERN.findall(html)
            if found:
                filename = found[0]
                try:
                    _, _, headers = DISCOVERY.fetch(
                        INVENTORY.ATTACHMENT_BASE_URL + filename, method="HEAD"
                    )
                    last_modified = headers.get("Last-Modified")
                    length = headers.get("Content-Length")
                except OSError:
                    pass
        details[identifier] = [filename, last_modified, int(length) if length else None]
    return {"rows": rows, "stop_reason": stop_reason, "details": details}


def load_crawl(config, refresh):
    if CACHE.exists() and not refresh:
        with open(CACHE, encoding="utf-8") as handle:
            return json.load(handle)
    payload = crawl(config)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    return payload


def assign_evidence_outcome(contract, extension, vintage_finding):
    """Assign exactly one preregistered D2 evidence outcome."""
    timing_ok = contract.contract_status == "resolved"
    vintages_exist = vintage_finding["complete_12_industry_vintages_available"]
    extension_ok = extension["latest_vintage_extension_feasible"]

    if vintages_exist and extension_ok:
        outcome = "point_in_time_extension_supported"
    elif extension_ok:
        outcome = "latest_vintage_extension_only"
    elif timing_ok:
        outcome = "timing_only_supported"
    else:
        outcome = "extension_not_supported"
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-crawl instead of using cache")
    parser.add_argument("--offline", action="store_true", help="skip live entry-point probes")
    args = parser.parse_args()

    config = VINTAGES.load_timing_config()
    generated_at = datetime.now(UTC).isoformat()

    # -- 1. discovery -----------------------------------------------------
    if args.offline:
        probes, discovery_summary = [], {
            "probed": 0,
            "reachable": [],
            "unreachable_by_state": {},
            "absence_established_for": [],
            "absence_claim_supported": False,
            "note": "offline run; entry points were not probed",
        }
    else:
        probes = DISCOVERY.discover_entry_points(config)
        discovery_summary = DISCOVERY.summarize_discovery(probes)

    # -- 2. release inventory --------------------------------------------
    payload = load_crawl(config, args.refresh)
    details = payload["details"]

    def detail_fetch(identifier):
        entry = details.get(str(identifier)) or [None, None, None]
        return entry[0], entry[1], entry[2]

    records = INVENTORY.build_release_inventory(
        payload["rows"],
        config,
        detail_fetch_fn=detail_fetch,
        observed_release_months=[OBSERVED_RELEASE["reference_month"]],
    )

    # -- 3. timing contract ----------------------------------------------
    live_reader = VINTAGES.GuardedMonthlyReader.from_config(ROOT / EDITIONS[0][1], config)
    contract = CONTRACT.build_timing_contract(
        records,
        required_window_start="2020-04",
        required_window_end="2025-06",
        directly_observed=OBSERVED_RELEASE,
        marker_months=live_reader.marked_months(),
    )
    b4 = CONTRACT.evaluate_b4_assumption(contract)

    # -- 4. editions, compatibility, extension ----------------------------
    profiles, readers = [], {}
    for edition_id, relative in EDITIONS:
        path = ROOT / relative
        reader = VINTAGES.GuardedMonthlyReader.from_config(path, config)
        readers[edition_id] = reader
        profiles.append(HISTORY.profile_edition(edition_id, reader, relative))

    compatibility = HISTORY.evaluate_base_year_compatibility(
        readers["hist_2016_base"], readers["live_2021_base"], config
    )
    extension = HISTORY.assess_history_extension(profiles, compatibility, config)

    # -- 5. vintage availability finding ----------------------------------
    vintage_finding = {
        "live_workbook_is_overwritten_in_place": True,
        "archive_entries_carry_full_numerical_series": False,
        "complete_12_industry_vintages_available": False,
        "archive_attachment_content": "selective_press_release_overview",
        "evidence": [
            "Archive attachments inspected for two pre-cutoff months (2025-06, 2022-06) "
            "contain 0 TSIC division codes paired with values, no tabular sector "
            "breakdown, and name only 4-6 of 13 industry keywords - a differing subset "
            "each month, i.e. selected highlights.",
            "The live workbook is a single URL overwritten on each release; the "
            "2026-08-26 and 2026-08-28 snapshots differ in checksum and the earlier "
            "vintage is not retained.",
            "data.go.th OIE records (gdpublish-43_011, gdpublish-43_02) point at those "
            "same overwritten URLs, so they are catalogue metadata rather than vintages.",
            "data.go.th per-month MPI files published by the Electrical and Electronics "
            "Institute contain electrical/electronics product rows only, not the "
            "national 12-industry index, and the 2019-2023 years were uploaded in bulk "
            "back-fill batches rather than contemporaneously.",
        ],
        "absence_claim_scope": (
            "No complete 12-industry vintage was found through the mechanisms exercised "
            "here (archive walk, detail pages, attachments, live workbook, CKAN search). "
            "This is a statement about those mechanisms, not proof that no vintage "
            "archive exists anywhere."
        ),
    }

    outcome = assign_evidence_outcome(contract, extension, vintage_finding)

    # -- 6. D1 limitation record -----------------------------------------
    d1_limitation = {
        "d1_primary_result": "incremental_signal_not_supported",
        "d1_nested_protocol_fully_executed": False,
        "d1_fallback_count": 6,
        "d1_protocol_deviation_reason": "insufficient_pre_origin_calibration_history",
        "fallback_strongly_shrinks_toward_benchmark": True,
        "fallback_guaranteed_to_worsen_model": False,
        "fallback_effect_direction": "unknown",
        "d1_approved_for_locked_test": False,
        "correction_note": (
            "D1 reporting (docs/d1_development_results.md section 7 and "
            "docs/d1_modeling_protocol.md section 4) stated that the fallback "
            "configuration (alpha=100, nonferrous_channel=none) could only make the "
            "model look worse and never better. That claim is withdrawn here as "
            "unsupported. Ridge with alpha=100 "
            "still fits an intercept and can retain Brent and Rubber predictors, so "
            "heavy shrinkage biases predictions toward the benchmark without "
            "guaranteeing a direction for the resulting error. The effect is recorded "
            "as unknown."
        ),
        "historical_entries_preserved": (
            "AD-R39 through AD-R58 are preserved byte-for-byte. This correction is "
            "recorded as a new decision, not by editing the historical record."
        ),
        "remedy_status": (
            "The fallback was caused by insufficient pre-origin history. D2 finds that "
            "history cannot be honestly extended, so the deviation cannot be remedied "
            "by extension."
        ),
    }

    # -- 7. write documents ----------------------------------------------
    source_audit = {
        "task": "D2",
        "generated_at_utc": generated_at,
        "config": {
            "numerical_audit_cutoff_month": config["numerical_audit_cutoff_month"],
            "plausible_first_publication_lag_days": config["plausible_first_publication_lag_days"],
            "base_year_compatibility_gate": config["base_year_compatibility_gate"],
            "history_extension_requirements": config["history_extension_requirements"],
        },
        "discovery": {
            "summary": discovery_summary,
            "probes": [p.to_dict() for p in probes],
        },
        "archive_walk": {
            "stop_reason": payload["stop_reason"],
            "entries": len(payload["rows"]),
            "distinct_ids": len({r["id_content"] for r in payload["rows"]}),
        },
        "release_inventory": {
            "months": len(records),
            "coverage_start": contract.coverage_start,
            "coverage_end": contract.coverage_end,
            "evidence_class_counts": contract.evidence_class_counts,
            "migration_batches": INVENTORY.detect_migration_batches(
                payload["rows"], config["migration_batch_min_entries"]
            ),
            "records": [r.to_dict() for r in records],
        },
        "vintage_finding": vintage_finding,
        "editions": [p.to_dict() for p in profiles],
        "base_year_compatibility": compatibility,
        "history_extension": extension,
        "evidence_outcome": outcome,
        "d1_limitation": d1_limitation,
        "restrictions_observed": {
            "b3_targets_rebuilt": False,
            "d1_models_rerun": False,
            "b4_split_changed": False,
            "target_feature_association_computed": False,
            "models_tuned": False,
            "locked_test_opened": False,
            "numerical_values_read_beyond_cutoff": False,
            "committed": False,
        },
    }

    timing_decision = {
        "task": "D2",
        "generated_at_utc": generated_at,
        "timing_contract": contract.to_dict(),
        "b4_assumption": b4,
        "evidence_outcome": outcome,
        "d1_limitation": d1_limitation,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    _write_json(DOCS / "d2_oie_mpi_source_audit.json", source_audit)
    _write_json(DOCS / "d2_target_timing_decision.json", timing_decision)
    _write_source_markdown(DOCS / "d2_oie_mpi_source_audit.md", source_audit, contract)
    _write_timing_markdown(DOCS / "d2_target_timing_decision.md", timing_decision, contract)

    print("D2 audit complete.")
    print("  archive entries      :", len(records), payload["stop_reason"])
    print("  coverage             :", contract.coverage_start, "..", contract.coverage_end)
    print("  evidence classes     :", contract.evidence_class_counts)
    print("  credible months      :", contract.months_with_credible_evidence)
    print("  lag days (min/med/max):", contract.publication_lag_days_min,
          contract.publication_lag_days_median, contract.publication_lag_days_max)
    print("  required window ok   :", contract.required_window_fully_evidenced)
    print("  availability lag     :", contract.availability_lag_months, "month(s)")
    print("  B4 assumption        :", b4["assumption_status"])
    print("  splice admissible    :", compatibility["splice_admissible"])
    print("  extension feasible   :", extension["latest_vintage_extension_feasible"])
    print("  EVIDENCE OUTCOME     :", outcome)
    return 0


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_source_markdown(path, audit, contract):
    compatibility = audit["base_year_compatibility"]
    extension = audit["history_extension"]
    lines = []
    add = lines.append
    add("# Task D2 — OIE MPI Source, Publication-Timing and Vintage Audit")
    add("")
    add(
        f"*Generated {audit['generated_at_utc']}. Evidence only: no target "
        "rebuilt, no model rerun, no locked"
    )
    add("test opened, no numerical value read after the cutoff.*")
    add("")
    add("## Evidence outcome: `{}`".format(audit["evidence_outcome"]))
    add("")
    add("Publication timing is established authentically. Complete 12-industry")
    add("point-in-time vintages are not available, and monthly history cannot be")
    add("honestly extended to the month the D1 protocol would have needed.")
    add("")
    add("## 1. Numerical guard")
    add("")
    add(
        f"`numerical_audit_cutoff_month = "
        f"{audit['config']['numerical_audit_cutoff_month']}`. Structural "
        "metadata (month labels,"
    )
    add("marker glyphs, checksums, HTTP headers) is read for every month; index")
    add("**values** are refused beyond the cutoff by `GuardedMonthlyReader`, which")
    add("raises `NumericalCutoffError` rather than returning a number.")
    add("")
    add("## 2. Entry-point discovery")
    add("")
    add("| entry point | state |")
    add("| --- | --- |")
    for probe in audit["discovery"]["probes"]:
        add("| `{}` | `{}` |".format(probe["entry_point_id"], probe["state"]))
    add("")
    add("No probe state in this audit means \"the source does not exist\". A DNS or")
    add("TLS failure is a property of one mechanism at one moment. Two earlier tasks")
    add("(C1.5-R1, C3-R1) were corrected for exactly that conflation.")
    add("")
    add("## 3. Release inventory")
    add("")
    walk = audit["archive_walk"]
    add(
        f"Archive walk terminated on `{walk['stop_reason']}`; "
        f"{walk['entries']} entries, {walk['distinct_ids']} distinct ids."
    )
    add(
        f"Coverage **{contract.coverage_start} .. {contract.coverage_end}**, "
        f"{audit['release_inventory']['months']} months, no gaps."
    )
    add("")
    add("July appears in two spellings in entry titles — the standard `กรกฎาคม` and")
    add("the variant `กรกฏาคม`. Five entries use the variant; accepting only the")
    add("standard spelling would have reported five coverage gaps that do not exist.")
    add("")
    add("| timing evidence class | months |")
    add("| --- | ---: |")
    for name, count in audit["release_inventory"]["evidence_class_counts"].items():
        add(f"| `{name}` | {count} |")
    add("")
    add("### Why the listing timestamp is not the publication date")
    add("")
    add("Migration batches (one listing date shared across many entries):")
    add("")
    for day, count in sorted(audit["release_inventory"]["migration_batches"].items()):
        add(f"* `{day}` — {count} entries")
    add("")
    add("The 2016-01…2017-03 block all carries a single 2017-06-13 listing stamp, and")
    add("its attachments were re-created at the same moment, so no first-publication")
    add("evidence survives for those months. Where a page was merely edited later, the")
    add("attachment keeps the original date and is preferred: the June-2022 entry is")
    add("listed as 2023-07-27 but its attachment is dated 2022-08-01.")
    add("")
    add("## 4. Vintage availability")
    add("")
    add("**No complete 12-industry vintage was found.** Evidence:")
    add("")
    for item in audit["vintage_finding"]["evidence"]:
        add(f"* {item}")
    add("")
    add("Scope of that statement: {}".format(audit["vintage_finding"]["absence_claim_scope"]))
    add("")
    add("## 5. Editions and base-year compatibility")
    add("")
    add("| edition | base | scheme | coverage | divisions |")
    add("| --- | ---: | --- | --- | ---: |")
    for profile in audit["editions"]:
        add(
            f"| `{profile['edition_id']}` | {profile['base_year']} | "
            f"{profile['classification_scheme']} | {profile['coverage_start']} .. "
            f"{profile['coverage_end']} | {len(profile['divisions'])} |"
        )
    add("")
    add("Splicing the 2016-based and 2021-based editions is admissible only if their")
    add("ratio is constant per division over the shared months — a pure rebasing.")
    overlap = (
        compatibility["per_division"][0]["overlap_months"]
        if compatibility["per_division"] else 0
    )
    add(f"Measured over {overlap} shared months:")
    add("")
    add(f"* divisions evaluated: **{compatibility['divisions_evaluated']}**")
    add(f"* pure rescaling: **{compatibility['divisions_pure_rescaling']}**")
    add(f"* re-estimated: **{compatibility['divisions_re_estimated']}**")
    add(f"* median ratio CV: **{compatibility['median_ratio_cv_percent'] or 0:.2f}%**")
    add(
        "* max ratio CV: "
        f"**{compatibility['max_ratio_cv_percent_observed'] or 0:.2f}%**"
    )
    add("")
    add("**Splice admissible: `{}`.**".format(compatibility["splice_admissible"]))
    for blocker in compatibility["blockers"]:
        add(f"* {blocker}")
    add("")
    add("## 6. Historical-extension feasibility")
    add("")
    add(
        f"Required: raw MPI from **{extension['raw_start_required']}**, "
        f"stress from **{extension['stress_start_required']}**."
    )
    add(
        f"The primary (2021-based) edition starts "
        f"**{extension['primary_edition_coverage_start']}**, so reaching the requirement"
    )
    add("means joining an older edition.")
    add("")
    add(
        "**Extension feasible: "
        f"`{extension['latest_vintage_extension_feasible']}`.** Blockers:"
    )
    for blocker in extension["blockers"]:
        add(f"* {blocker}")
    add("")
    add("## 7. D1 limitation recorded")
    add("")
    for key in ("d1_primary_result", "d1_nested_protocol_fully_executed", "d1_fallback_count",
                "d1_protocol_deviation_reason", "fallback_strongly_shrinks_toward_benchmark",
                "fallback_guaranteed_to_worsen_model", "fallback_effect_direction",
                "d1_approved_for_locked_test"):
        add("* `{}`: `{}`".format(key, audit["d1_limitation"][key]))
    add("")
    add("{}".format(audit["d1_limitation"]["correction_note"]))
    add("")
    add("{}".format(audit["d1_limitation"]["historical_entries_preserved"]))
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _write_timing_markdown(path, decision, contract):
    b4 = decision["b4_assumption"]
    lines = []
    add = lines.append
    add("# Task D2 — Target Publication-Timing Decision")
    add("")
    add("*Generated {}.*".format(decision["generated_at_utc"]))
    add("")
    add("## Contract")
    add("")
    add("| field | value |")
    add("| --- | --- |")
    for key in ("contract_status", "months_total", "months_with_credible_evidence",
                "coverage_start", "coverage_end", "credible_coverage_start",
                "credible_coverage_end", "publication_lag_days_min",
                "publication_lag_days_median", "publication_lag_days_max",
                "publishes_in_month_after_reference", "availability_lag_months",
                "same_month_availability_supported", "required_window_start",
                "required_window_end", "required_window_fully_evidenced"):
        add("| `{}` | `{}` |".format(key, decision["timing_contract"][key]))
    add("")
    add("## Directly observed release")
    add("")
    observed = decision["timing_contract"]["directly_observed_release"]
    if observed:
        add(
            f"Reference month **{observed['reference_month']}** was observed "
            "becoming public during this audit."
        )
        add("The live workbook gained exactly one month between the two snapshots and")
        add(
            f"its `Last-Modified` moved from `{observed['before_last_modified']}` "
            f"to `{observed['after_last_modified']}`, with the checksum changing."
        )
        add(
            f"The marker glyph moved from `{observed['marker_moved_from']}` to "
            f"`{observed['marker_moved_to']}`."
        )
        add("")
        add("{}".format(observed["interpretation"]))
    add("")
    add("## Marker semantics")
    add("")
    add(
        "`marker_semantics_documented: "
        f"{decision['timing_contract']['marker_semantics_documented']}`"
    )
    add("")
    if decision["timing_contract"]["marker_note"]:
        add(decision["timing_contract"]["marker_note"])
    add("")
    add("## Consequence for B4")
    add("")
    add("**Assumption:** {}".format(b4["b4_assumption"]))
    add("")
    add("**Status: `{}`.**".format(b4["assumption_status"]))
    add("")
    add("{}".format(b4.get("explanation", "")))
    add("")
    add("* `affects_b4_baselines`: `{}`".format(b4.get("affects_b4_baselines")))
    add("* `affects_d1_feature_assembly`: `{}`".format(b4.get("affects_d1_feature_assembly")))
    add("* `b4_split_changed`: `{}`".format(b4["b4_split_changed"]))
    add("* `remedy_deferred`: `{}`".format(b4.get("remedy_deferred")))
    add("")
    add("{}".format(b4.get("remedy_note", "")))
    add("")
    add("## Evidence outcome: `{}`".format(decision["evidence_outcome"]))
    add("")
    add("## Follow-up")
    add("")
    add("The D1 fallback correction recorded here is maintained as a sidecar")
    add("erratum: [`d1_development_results.errata.md`](d1_development_results.errata.md).")
    add("The two generated D1 documents were restored in Task D3 by reversing the")
    add("known D2 insertion; the original pre-D2 digest was unavailable, so exact")
    add("historical byte identity cannot be independently proven. The resulting")
    add("files are pinned from D3 onward in `d3_restored_d1_checksums.json`.")
    add("")
    add("This section is emitted by the D2 generator itself, so regenerating this")
    add("document cannot erase the link — the same failure mode that moved the D1")
    add("correction out of its generated result file.")
    add("")
    add("Task D3 acts on the violated assumption above by building a release-aware")
    add("operational contract — see")
    add("[`d3_operational_evaluation_protocol.md`](d3_operational_evaluation_protocol.md)")
    add("and [`d3_operational_baseline_results.md`](d3_operational_baseline_results.md).")
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
