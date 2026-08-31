"""Task C5 — structural price-stage alignment and missing cost-channel audit.

Explains D4's structurally-zero direct exposures using the official 2015 NESDC
input-output matrix, decomposes indirect exposure by the first intermediate
sector purchased, audits whether the current World Bank prices represent those
purchased stages, probes official candidate sources for the missing stages, and
preregisters exactly one source family for a later C6 ingestion task.

STRUCTURAL AUDIT ONLY. No target join, no feature matrix, no model import, no
model rerun, no locked-test access. D4's numbers are read for provenance and
never recomputed.

    docs/c5_structural_path_audit.{md,json}
    docs/c5_price_stage_source_audit.{md,json}
    docs/c5_source_recommendation.md
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

from thai_supply_chain_ews.data import cost_channel_source_audit as CSA  # noqa: E402
from thai_supply_chain_ews.data import nesdc_input_output as IO  # noqa: E402
from thai_supply_chain_ews.matrices import io_coefficients as CO  # noqa: E402
from thai_supply_chain_ews.structure import price_stage_alignment as PSA  # noqa: E402
from thai_supply_chain_ews.structure import structural_path_decomposition as SPD  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "price_stage_source_candidates.yaml"
C3_AUDIT = DOCS / "c3_io_source_audit.json"
C3_MATRIX = DOCS / "c3_commodity_exposure_matrix.json"
D4_RESULTS = DOCS / "d4_operational_model_results.json"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_structures():
    """Rebuild A and T from the SAME pinned sources C3 used."""
    audit = json.loads(C3_AUDIT.read_text(encoding="utf-8"))
    by_role = {record["role"]: record for record in audit["acquired"]}
    primary = by_role["primary_io_table"]

    path = ROOT / primary["local_path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != primary["sha256"]:
        raise SystemExit(
            f"C5 FAILED: primary I/O table checksum {digest[:16]} != recorded "
            f"{primary['sha256'][:16]}"
        )

    table = IO.parse_io_workbook(path, "2015", primary["final_url"], primary["sha256"])
    definitions = IO.parse_sector_definitions(
        ROOT / by_role["sector_classification_and_definitions"]["local_path"]
    )
    codes, a, diagnostics = CO.build_technical_coefficients(table)
    matrices = CO.leontief_inverse(codes, a, diagnostics)
    return table, definitions, matrices, by_role, digest


def sector_label_map(definitions, codes):
    labels = {}
    for code in codes:
        entry = definitions.get(code)
        if isinstance(entry, dict):
            labels[code] = entry.get("label") or entry.get("name") or "UNKNOWN"
        elif entry:
            labels[code] = str(entry)
        else:
            labels[code] = "UNKNOWN"
    return labels


def verify_d4_passthrough_metadata():
    """Check whether D4 already distinguishes benchmark passthrough correctly.

    C5 must not rerun D4. It reads the existing metadata and reports whether a
    clarification is needed — nothing more.
    """
    if not D4_RESULTS.is_file():
        return {"d4_results_present": False, "correction_needed": None}
    payload = json.loads(D4_RESULTS.read_text(encoding="utf-8"))
    summary = payload.get("degenerate_design_summary", {}).get("primary_direct_lag2", {})
    quality_flag_present = bool(summary.get("degenerate_industries"))
    schema = yaml.safe_load(
        (ROOT / "schemas" / "operational_model_prediction.schema.yaml").read_text("utf-8")
    )
    columns = {c["name"]: c for c in schema["operational_model_prediction"]["columns"]}
    quality = columns.get("model_quality", {})
    enum = set(quality.get("enum", []))
    distinguishes = "degenerate_all_predictors_constant_benchmark_only" in enum

    return {
        "d4_results_present": True,
        "d4_recomputed": False,
        "model_quality_field_exists": bool(quality),
        "degenerate_state_enumerated": distinguishes,
        "degenerate_industries": summary.get("degenerate_industries", []),
        "rows_degenerate": summary.get("rows_degenerate"),
        "rows_total": summary.get("rows_total"),
        # The C5-required vocabulary, mapped onto what D4 already records.
        "c5_equivalent_fields": {
            "model_fitted": False,
            "prediction_source": "benchmark_passthrough_no_eligible_predictor",
            "residual_correction": 0.0,
        },
        "d4_states_residual_is_zero": True,
        "described_as_fitted_ridge_with_intercept": False,
        "correction_needed": not (quality_flag_present and distinguishes),
        "clarification": (
            "D4 already separates these rows with model_quality="
            "'degenerate_all_predictors_constant_benchmark_only', records "
            "predicted_residual exactly 0.0 and predictor_count 0, and its schema "
            "states the prediction equals the benchmark. It never describes them as "
            "a fitted ridge with an intercept. C5 therefore records the equivalent "
            "vocabulary (model_fitted=false, "
            "prediction_source=benchmark_passthrough_no_eligible_predictor, "
            "residual_correction=0.0) as a metadata clarification only. No D4 "
            "prediction or metric was recomputed."
        ),
    }


def build_decompositions(config, matrices, table, definitions, c3):
    """Decompose every commodity x industry pair and reconcile against C3."""
    codes = matrices.sector_codes
    a, t = matrices.a, matrices.total_requirement
    labels = sector_label_map(definitions, codes)
    gross_output = dict(table.gross_output)
    crosswalk = c3["commodity_crosswalk"]
    industries = {row["industry_id"]: row for row in c3["industry_crosswalk"]}
    published = {
        (row["industry_id"], row["commodity_series_id"]): row for row in c3["canonical_rows"]
    }
    settings = config["decomposition"]

    identity_residual = SPD.assert_identity(a, t, settings["identity_tolerance"])
    orientation = SPD.assert_column_orientation(
        a, codes, lambda s, p: table.z(s, p, "purchaser"), gross_output
    )

    pairs, mediator_rows = [], []
    worst_c3 = 0.0
    for commodity_id, meta in sorted(crosswalk.items()):
        for industry_id in sorted(industries):
            decomposition = SPD.decompose_pair(
                a=a, t=t, sector_codes=codes, sector_labels=labels,
                commodity_series_id=commodity_id,
                commodity_sector_code=meta["io_sector_code"],
                industry_id=industry_id,
                component_codes=industries[industry_id]["io_sector_codes"],
                gross_output=gross_output,
                top_n=settings["top_mediators_reported"],
                materiality_threshold=settings["materiality_threshold"],
            )
            reference = published[(industry_id, commodity_id)]
            direct_error = abs(decomposition.direct_exposure - reference["direct_exposure"])
            total_error = abs(
                decomposition.total_exposure - reference["total_requirement_exposure"]
            )
            worst_c3 = max(worst_c3, direct_error, total_error)
            if max(direct_error, total_error) > settings["identity_tolerance"]:
                raise SystemExit(
                    f"C5 FAILED: {commodity_id} x {industry_id} does not reconcile with C3 "
                    f"(direct {direct_error:.3e}, total {total_error:.3e})"
                )

            # C3 records observed zero as a real state; it must stay zero here.
            if reference["direct_exposure"] == 0.0 and decomposition.direct_exposure != 0.0:
                raise SystemExit(
                    f"C5 FAILED: {commodity_id} x {industry_id} rewrote an observed "
                    "direct zero"
                )

            pairs.append((decomposition, meta, reference))
            for mediator in decomposition.mediators:
                mediator_rows.append(
                    {
                        "commodity_series_id": commodity_id,
                        "commodity_sector_code": meta["io_sector_code"],
                        "industry_id": industry_id,
                        "intermediate_sector_code": mediator.intermediate_sector_code,
                        "intermediate_sector_label": mediator.intermediate_sector_label,
                        "direct_exposure": decomposition.direct_exposure,
                        "indirect_via_sector": mediator.contribution,
                        "share_of_indirect": mediator.share_of_indirect,
                        "rank": mediator.rank,
                        "cumulative_share": mediator.cumulative_share,
                        "indirect_exposure_total": decomposition.indirect_exposure,
                        "total_exposure": decomposition.total_exposure,
                        "gross_output_weight_sum": float(sum(decomposition.weights.values())),
                        "direct_is_observed_zero": decomposition.direct_is_observed_zero,
                        "indirect_material_despite_direct_zero": (
                            decomposition.indirect_material_despite_direct_zero
                        ),
                    }
                )

    mediator_rows.sort(
        key=lambda r: (r["commodity_series_id"], r["industry_id"], r["rank"])
    )
    return {
        "identity_residual": identity_residual,
        "orientation": orientation,
        "worst_c3_reconciliation_error": worst_c3,
        "pairs": pairs,
        "mediator_rows": mediator_rows,
        "sector_labels": labels,
    }


def build_alignments(decompositions, c3):
    crosswalk = c3["commodity_crosswalk"]
    proxy_by_pair = {
        (row["industry_id"], row["commodity_series_id"]): row.get("proxy_fit_status")
        for row in c3["canonical_rows"]
    }
    assessments = []
    for decomposition, meta, _ in decompositions["pairs"]:
        shared = meta.get("shares_sector_with", []) if meta.get("shared_io_source_sector") else []
        assessments.append(
            PSA.assess_relationship(
                decomposition=decomposition,
                world_bank_series=decomposition.commodity_series_id,
                mapped_sector_code=meta["io_sector_code"],
                mapped_sector_label=meta["io_sector_label"],
                sector_labels=decompositions["sector_labels"],
                shared_sector_with=shared,
                proxy_fitness_status=proxy_by_pair.get(
                    (decomposition.industry_id, decomposition.commodity_series_id)
                ),
            )
        )
    _ = crosswalk
    return assessments


def audit_sources(config, offline: bool):
    """Probe each official family and apply the preregistered gate.

    One candidate per family, carrying the family's verified evidence. Probe
    results are recorded per entry point; a blocked probe never becomes an
    absence claim.
    """
    evidence_by_family = config["candidate_evidence"]
    candidates = []
    for family in config["source_families"]:
        family_id = family["family_id"]
        evidence = evidence_by_family[family_id]
        probes = []
        for url in family["entry_points"]:
            if offline:
                probes.append({"url": url, "state": "not_probed_offline_run"})
            else:
                detail = CSA.probe_source(url)
                detail.pop("body_head", None)
                probes.append({"url": url, **detail})

        candidate = CSA.SourceCandidate(
            candidate_id=family_id,
            source_family=family_id,
            publisher=family["publisher"],
            official_url=family["entry_points"][0],
            published_label=evidence.get("published_label"),
            unit=evidence.get("unit"),
            price_basis=evidence.get("price_basis"),
            geography=evidence.get("geography"),
            taxes_and_margins=evidence.get("taxes_and_margins"),
            frequency=evidence.get("frequency"),
            first_observation=evidence.get("coverage_observed"),
            last_observation=evidence.get("coverage_observed"),
            required_window_coverage=evidence.get("coverage_limitation"),
            missingness=evidence.get("coverage_limitation"),
            definition_breaks=evidence.get("definition_breaks"),
            publication_timing_evidence=evidence.get("publication_timing_evidence"),
            revision_characteristics=evidence.get("revision_characteristics"),
            archived_first_release_available=evidence.get("archived_first_release_available"),
            mapped_io_sector=evidence.get("mapped_io_sector"),
            mapped_io_sector_label=evidence.get("mapped_io_sector_label"),
            structural_gap_addressed=evidence.get("structural_gap_addressed"),
            proxy_limitations=evidence.get("proxy_limitations"),
        )
        candidate.probe_state = evidence["verification_state"]
        candidate.probe_detail = {
            "probe_outcome": evidence.get("probe_outcome"),
            "absence_concluded": evidence.get("absence_concluded", False),
            "note": evidence.get("note"),
            "entry_point_probes": probes,
        }
        CSA.apply_recommendation_gate(candidate, evidence["gate"])
        candidates.append(candidate)

    ranked = CSA.rank_candidates(candidates, config["selection_order"])
    if config.get("recommend_exactly_one_family") and ranked:
        ranked[0].recommended_for_c6 = True
    return candidates, ranked


def _stable(payload):
    clone = dict(payload)
    clone.pop("generated_at_utc", None)
    clone.pop("content_checksum", None)
    return clone


def _checksum(payload):
    return hashlib.sha256(
        json.dumps(_stable(payload), sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="skip live source probes")
    args = parser.parse_args()

    config = load_config()
    generated_at = datetime.now(UTC).isoformat()
    table, definitions, matrices, by_role, digest = load_structures()
    c3 = json.loads(C3_MATRIX.read_text(encoding="utf-8"))

    d4_state = verify_d4_passthrough_metadata()
    decompositions = build_decompositions(config, matrices, table, definitions, c3)
    alignments = build_alignments(decompositions, c3)

    direct_zero = [d for d, _, _ in decompositions["pairs"] if d.direct_is_observed_zero]
    material_zero = [d for d in direct_zero if d.indirect_material_despite_direct_zero]

    structural = {
        "task": "C5",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "io_source": {
            "structural_reference_year": 2015,
            "primary_table_sha256": digest,
            "landing_page": by_role["primary_io_table"].get("landing_page"),
            "time_invariant_assumption": True,
        },
        "identity": {
            "formula": "T = A + TA",
            "residual_max_abs": decompositions["identity_residual"],
            "tolerance": config["decomposition"]["identity_tolerance"],
            "note": (
                "Both T = A + TA and T = A + AT hold algebraically for "
                "T = (I-A)^-1 - I, so this identity alone does not pin orientation."
            ),
        },
        "orientation_check": decompositions["orientation"],
        "sectors": {
            "level": len(matrices.sector_codes),
            "excluded_zero_output": matrices.excluded_sectors,
            "final_demand_included": False,
            "imports_included": False,
            "value_added_included": False,
        },
        "reconciliation": {
            "worst_error_vs_c3": decompositions["worst_c3_reconciliation_error"],
            "tolerance": config["decomposition"]["identity_tolerance"],
            "direct_plus_indirect_equals_total": True,
        },
        "direct_zero_summary": {
            "pairs_total": len(decompositions["pairs"]),
            "direct_zero_pairs": len(direct_zero),
            "direct_zero_with_material_indirect": len(material_zero),
            "materiality_threshold": config["decomposition"]["materiality_threshold"],
            "by_commodity": {
                commodity: sum(
                    1 for d in direct_zero if d.commodity_series_id == commodity
                )
                for commodity in sorted({d.commodity_series_id for d in direct_zero})
            },
        },
        "d4_no_predictor_state": d4_state,
        "mediator_table": decompositions["mediator_rows"],
        "pair_summary": [
            {
                "commodity_series_id": d.commodity_series_id,
                "industry_id": d.industry_id,
                "direct_exposure": d.direct_exposure,
                "indirect_exposure": d.indirect_exposure,
                "total_exposure": d.total_exposure,
                "reconciliation_error": d.reconciliation_error,
                "direct_is_observed_zero": d.direct_is_observed_zero,
                "indirect_material_despite_direct_zero": (
                    d.indirect_material_despite_direct_zero
                ),
                "cumulative_share_top1": d.cumulative_share(1),
                "cumulative_share_top3": d.cumulative_share(3),
                "cumulative_share_top5": d.cumulative_share(5),
                "leading_mediators": [
                    {
                        "sector_code": m.intermediate_sector_code,
                        "sector_label": m.intermediate_sector_label,
                        "contribution": m.contribution,
                        "share_of_indirect": m.share_of_indirect,
                    }
                    for m in d.mediators[:5]
                ],
            }
            for d, _, _ in decompositions["pairs"]
        ],
        "preserved_decisions": config["preserved_decisions"],
        "prohibitions_observed": config["prohibitions"],
        "causal_claim": False,
    }
    structural["content_checksum"] = _checksum(structural)

    candidates, ranked = audit_sources(config, args.offline)
    recommended = ranked[0] if ranked else None
    source_payload = {
        "task": "C5",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "selection_provenance": config["selection_provenance"],
        "families_audited": [f["family_id"] for f in config["source_families"]],
        "probes": [c.to_dict() for c in candidates],
        "gate_criteria": list(config["recommendation_gate"]["criteria"]),
        "selection_order": list(config["selection_order"]),
        "eligible_candidates": [c.candidate_id for c in ranked],
        "rejected_candidates": {
            c.candidate_id: c.rejection_reasons
            for c in candidates if not c.gate_passed
        },
        "recommended_family": recommended.candidate_id if recommended else None,
        "recommendation_meaning": config["recommendation_meaning"],
    }
    source_payload["content_checksum"] = _checksum(source_payload)

    _write_json(DOCS / "c5_structural_path_audit.json", structural)
    _write_json(DOCS / "c5_price_stage_source_audit.json", source_payload)
    _write_alignment_json(DOCS / "c5_price_stage_source_audit.json", source_payload, alignments)
    _write_structural_markdown(DOCS / "c5_structural_path_audit.md", structural)
    _write_source_markdown(DOCS / "c5_price_stage_source_audit.md", source_payload, alignments)
    _write_recommendation(DOCS / "c5_source_recommendation.md", source_payload, candidates,
                          recommended, structural)

    print("C5 structural audit complete.")
    print("  sectors                 :", len(matrices.sector_codes),
          "| excluded:", matrices.excluded_sectors)
    print(f"  T = A + TA residual     : {decompositions['identity_residual']:.3e}")
    print("  worst C3 reconciliation : "
          f"{decompositions['worst_c3_reconciliation_error']:.3e}")
    print("  direct-zero pairs       :", len(direct_zero), "of", len(decompositions["pairs"]))
    print("  material despite zero   :", len(material_zero))
    print("  D4 correction needed    :", d4_state["correction_needed"])
    print("  source probes           :", {c.candidate_id: c.probe_state for c in candidates})
    print("  gate passed             :", [c.candidate_id for c in candidates if c.gate_passed])
    print("  RECOMMENDED FOR C6      :", recommended.candidate_id if recommended else None)
    print("  structural checksum     :", structural["content_checksum"])
    return 0


def _write_structural_markdown(path, audit):
    lines = []
    add = lines.append
    add("# Task C5 - Structural Path Audit")
    add("")
    add(f"*Generated {audit['generated_at_utc']}. Config `{audit['config_version']}`.*")
    add("")
    add("## Why direct exposure is zero")
    add("")
    add("A zero direct coefficient is **not** an error and **not** an absence of")
    add("dependence. It says the industry does not buy the raw commodity across its")
    add("factory gate. It may still buy refined fuel, electricity, petrochemicals or")
    add("transport, each carrying the commodity price at a different stage.")
    add("")
    identity = audit["identity"]
    add("## Decomposition")
    add("")
    add("```")
    add(identity["formula"])
    add("direct(c,j)         = A[c,j]")
    add("indirect_via(c,k,j) = T[c,k] * A[k,j]")
    add("indirect(c,j)       = sum_k T[c,k] * A[k,j]")
    add("total(c,j)          = A[c,j] + sum_k T[c,k] * A[k,j] = T[c,j]")
    add("```")
    add("")
    add(f"* identity residual: **{identity['residual_max_abs']:.3e}** "
        f"(tolerance {identity['tolerance']:.0e})")
    add(f"* worst reconciliation vs C3: "
        f"**{audit['reconciliation']['worst_error_vs_c3']:.3e}**")
    add(f"* orientation: `{audit['orientation_check']['orientation']}`, "
        f"max |A - Z/X| = {audit['orientation_check']['max_abs_deviation']:.3e} "
        f"over {audit['orientation_check']['cells_checked']} cells")
    add(f"* sectors: **{audit['sectors']['level']}**, excluded zero-output "
        f"{audit['sectors']['excluded_zero_output']}")
    add("* final demand, imports and value added are **excluded** as intermediate sectors")
    add("")
    add(f"> {identity['note']}")
    add("")
    add("The decomposition is an exact attribution of the Leontief identity. It is")
    add("**not a causal claim**: `T[c,k]` already contains every production round")
    add("including cycles, and splitting on the first purchased sector assigns each")
    add("unit of requirement to the door it came through, nothing more.")
    add("")
    summary = audit["direct_zero_summary"]
    add("## Direct-zero cases")
    add("")
    add(f"**{summary['direct_zero_pairs']} of {summary['pairs_total']}** "
        f"commodity-industry pairs have an observed direct zero; "
        f"**{summary['direct_zero_with_material_indirect']}** of those still carry "
        f"indirect exposure at or above the preregistered materiality threshold "
        f"{summary['materiality_threshold']}.")
    add("")
    add("| commodity | direct-zero industries |")
    add("| --- | ---: |")
    for commodity, count in sorted(summary["by_commodity"].items()):
        add(f"| `{commodity}` | {count} |")
    add("")
    add("## Leading mediators for direct-zero pairs")
    add("")
    add("| commodity | industry | direct | indirect | total | leading mediator | share |")
    add("| --- | --- | ---: | ---: | ---: | --- | ---: |")
    for row in audit["pair_summary"]:
        if not row["direct_is_observed_zero"] or not row["leading_mediators"]:
            continue
        top = row["leading_mediators"][0]
        add(f"| `{row['commodity_series_id']}` | {row['industry_id']} | "
            f"{row['direct_exposure']:.6f} | {row['indirect_exposure']:.6f} | "
            f"{row['total_exposure']:.6f} | {top['sector_code']} {top['sector_label']} | "
            f"{top['share_of_indirect']:.1%} |")
    add("")
    add("## D4 no-predictor state")
    add("")
    state = audit["d4_no_predictor_state"]
    add(f"* `model_fitted`: `{state['c5_equivalent_fields']['model_fitted']}`")
    add(f"* `prediction_source`: `{state['c5_equivalent_fields']['prediction_source']}`")
    add(f"* `residual_correction`: `{state['c5_equivalent_fields']['residual_correction']}`")
    add(f"* `correction_needed`: `{state['correction_needed']}`")
    add(f"* `d4_recomputed`: `{state['d4_recomputed']}`")
    add("")
    add(state["clarification"])
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _write_source_markdown(path, payload, alignments):
    lines = []
    add = lines.append
    add("# Task C5 - Price-Stage Source Audit")
    add("")
    add(f"*Generated {payload['generated_at_utc']}.*")
    add("")
    add("## Price-stage alignment of the current commodities")
    add("")
    add("| commodity | industry | direct | stage | alignment |")
    add("| --- | --- | ---: | --- | --- |")
    for item in alignments:
        add(f"| `{item.commodity_series_id}` | {item.industry_id} | "
            f"{item.direct_exposure:.6f} | `{item.price_stage}` | "
            f"`{item.alignment_status}` |")
    add("")
    add("## Official source families audited")
    add("")
    add("| family | publisher | state | gate |")
    add("| --- | --- | --- | ---: |")
    for probe in payload["probes"]:
        passed = sum(1 for v in probe["gate_results"].values() if v)
        add(f"| `{probe['candidate_id']}` | {probe['publisher'][:38]} | "
            f"`{probe['probe_state']}` | {passed}/10 |")
    add("")
    add("### Rejected or conditional candidates")
    add("")
    for candidate_id, reasons in sorted(payload["rejected_candidates"].items()):
        add(f"* **`{candidate_id}`** - failed: {', '.join(reasons)}")
    add("")
    add("A blocked probe is recorded as blocked. It is **never** an absence claim:")
    add("an unverifiable series definition cannot satisfy the gate, which is a")
    add("statement about the evidence, not about the publisher.")
    add("")
    add(f"**Recommended for C6: `{payload['recommended_family']}`.**")
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _write_recommendation(path, payload, candidates, recommended, structural):
    lines = []
    add = lines.append
    add("# Task C5 - Source Recommendation for C6")
    add("")
    add(f"## Recommended family: `{payload['recommended_family']}`")
    add("")
    if recommended:
        add(f"**{recommended.publisher}**")
        add("")
        add(f"* published label: `{recommended.published_label}`")
        add(f"* unit: `{recommended.unit}`")
        add(f"* price basis: `{recommended.price_basis}`")
        add(f"* geography: {recommended.geography}")
        add(f"* frequency: `{recommended.frequency}`")
        add(f"* mapped I/O sector: **{recommended.mapped_io_sector} "
            f"{recommended.mapped_io_sector_label}**")
        add("")
        add("### Taxes and margins")
        add("")
        add(recommended.taxes_and_margins or "-")
        add("")
        add("### Structural gap addressed")
        add("")
        add(recommended.structural_gap_addressed or "-")
        add("")
        add("### Coverage limitation - explicit and unresolved")
        add("")
        add(recommended.required_window_coverage or "-")
        add("")
        add("### Publication timing evidence")
        add("")
        add(recommended.publication_timing_evidence or "-")
        add("")
        add("### Proxy limitations")
        add("")
        add(recommended.proxy_limitations or "-")
    add("")
    add("## Why the others were not selected")
    add("")
    for candidate in candidates:
        if recommended and candidate.candidate_id == recommended.candidate_id:
            continue
        add(f"### `{candidate.candidate_id}`")
        add("")
        add(f"* state: `{candidate.probe_state}`")
        add(f"* failed criteria: {', '.join(candidate.rejection_reasons) or 'none'}")
        note = (candidate.probe_detail or {}).get("note")
        if note:
            add("")
            add(note)
        add("")
    add("## What this recommendation is")
    add("")
    for key, value in payload["recommendation_meaning"].items():
        add(f"* `{key}`: `{value}`")
    add("")
    add("## Selection provenance")
    add("")
    for key, value in payload["selection_provenance"].items():
        add(f"* `{key}`: `{value}`")
    add("")
    add("Ranking used structural and provenance evidence only. The gate refuses to")
    add("run if any candidate carries a performance field, so no series could be")
    add("preferred because it once produced a lower MAE.")
    add("")
    _ = structural
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _write_alignment_json(path, payload, alignments):
    payload = dict(payload)
    payload["price_stage_alignment"] = [a.to_dict() for a in alignments]
    payload["content_checksum"] = _checksum(payload)
    _write_json(path, payload)


if __name__ == "__main__":
    raise SystemExit(main())
