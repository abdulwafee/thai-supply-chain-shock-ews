"""Task C9 — sector-093 fuel-oil exposure and industry-conditioned features.

Runs in two explicit phases. **Phase A** derives direct exposure to I/O sector
093, decides proxy fitness, direction and eligibility from structural evidence
only, writes the decision artifact and freezes its checksum. **Phase B** reasserts
that checksum, then loads the C8 numeric values and conditions them. Any change
to eligibility after the values are loaded raises.

STRUCTURAL CONDITIONING ONLY. No MPI join, no target association, no
outcome-based channel selection, no model, no locked-test access. C3, C5, C7,
C7.5 and C8 artifacts are read-only.

    docs/c9_sector093_exposure_decision.{md,json}
    docs/c9_fuel_oil_conditioning_audit.{md,json}
    data/features/c9_fuel_oil_conditioned.parquet             (git-ignored)
    data/features/c9_fuel_oil_development_snapshot.parquet    (git-ignored)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.data import nesdc_input_output as IO  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import taxonomy as TX  # noqa: E402
from thai_supply_chain_ews.features import (  # noqa: E402
    fuel_oil_conditioned_lineage as CL,
)
from thai_supply_chain_ews.features import (  # noqa: E402
    fuel_oil_industry_conditioning as FC,
)
from thai_supply_chain_ews.features import fuel_oil_issue_snapshots as SN  # noqa: E402
from thai_supply_chain_ews.matrices import industry_crosswalk as XW  # noqa: E402
from thai_supply_chain_ews.matrices import io_coefficients as CO  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_proxy_fitness as PF  # noqa: E402
from thai_supply_chain_ews.structure import sector093_exposure as EX  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "fuel_oil_industry_conditioning.yaml"
C3_CONFIG = ROOT / "configs" / "industry_exposure.yaml"
SPLITS_CONFIG = ROOT / "configs" / "operational_evaluation.yaml"
C3_SOURCE_AUDIT = DOCS / "c3_io_source_audit.json"
C3_MATRIX = DOCS / "c3_commodity_exposure_matrix.json"
C7_5_DECISION = DOCS / "c7_5_eppo_semantic_decision.json"
C8_AUDIT = DOCS / "c8_eppo_transformation_audit.json"
C8_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"
PHASE_A_JSON = DOCS / "c9_sector093_exposure_decision.json"
CONDITIONED_PARQUET = ROOT / "data" / "features" / "c9_fuel_oil_conditioned.parquet"
SNAPSHOT_PARQUET = (
    ROOT / "data" / "features" / "c9_fuel_oil_development_snapshot.parquet"
)


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 1. Upstream invariants
# ---------------------------------------------------------------------------
def reproduce_upstream_invariants(table, codes, crosswalks, definitions) -> dict:
    c8 = load_json(C8_AUDIT)
    c3 = load_json(C3_MATRIX)
    c8_counts = c8["counts"]["totals"]
    readiness = c8["readiness"]
    channels = c8["channels"]

    assigned = [code for cw in crosswalks for code in cw.io_sector_codes]
    checks = {
        "c8_source_transformation_rows": (c8_counts["feature_grid_rows"], 650),
        "c8_finite_rows": (c8_counts["finite_feature_rows"], 598),
        "c8_null_rows": (c8_counts["null_feature_rows"], 52),
        "c8_rows_per_channel": (
            sorted({v["rows"] for v in readiness.values()}), [325],
        ),
        "c8_finite_per_channel": (
            sorted({v["finite_rows"] for v in readiness.values()}), [299],
        ),
        "c8_null_per_channel": (
            sorted({v["null_rows"] for v in readiness.values()}), [26],
        ),
        "c8_transformation_definitions": (len(c8["transformations"]), 5),
        "c8_policy_lag_months": (c8["timing_policy"]["operational_policy_lag_months"], 2),
        "c8_lag_is_measured": (c8["timing_policy"]["operational_lag_is_measured"], False),
        "c8_source_available_as_of_null_rows": (
            c8["availability"]["source_available_as_of_null_rows"], 650,
        ),
        "c8_latest_vintage_used": (c8["timing_policy"]["latest_vintage_values_used"], True),
        "c8_point_in_time_supported": (
            c8["timing_policy"]["point_in_time_values_supported"], False,
        ),
        "c8_shared_price_stage_group": (
            channels["shared_price_stage_group"], "io_sector_093_fuel_oil",
        ),
        "c8_channels": (sorted(channels["channel_ids"]),
                        ["eppo_fo1500_channel", "eppo_fo600_channel"]),
        "c8_hsd_absent": (
            "eppo_hsd_channel" not in channels["channel_ids"], True,
        ),
        "c8_fo600_ready": (
            readiness["eppo_fo600_channel"][
                "source_transformations_ready_for_structural_conditioning"], True,
        ),
        "c8_fo1500_ready": (
            readiness["eppo_fo1500_channel"][
                "source_transformations_ready_for_structural_conditioning"], True,
        ),
        "c3_valid_io_sectors": (len(codes), 179),
        "c3_excluded_zero_output_sector": (
            c3["io_accounting"]["zero_or_negative_gross_output_sectors"], ["179"],
        ),
        "c3_coefficient_measure": (c3["coefficients"]["measure"], "purchaser"),
        "c3_valuation_price_basis": (
            c3["io_source"]["valuation"]["price_basis"], "purchasers_prices",
        ),
        "c3_import_treatment": (
            c3["io_source"]["valuation"]["import_treatment"], "import_inclusive",
        ),
        "c3_production_industries": (len(crosswalks), 12),
        "c3_no_duplicate_sector_assignment": (
            len(assigned) == len(set(assigned)), True,
        ),
        "c3_structural_available_by": (
            load_yaml(ROOT / "configs" / "industry_conditioned_features.yaml")[
                "structural_availability"]["structural_available_by"].isoformat(),
            "2020-03-31",
        ),
        "c3_target_outcomes_used_in_crosswalk": (
            c3["exposure_weights_tuned_on_outcomes"], False,
        ),
        "sector_093_present_exactly_once": (codes.count("093"), 1),
        "sector_093_official_label": (definitions["093"]["label"], "Petroleum refineries"),
        "gross_output_positive_for_every_used_sector": (
            all(table.gross_output[code] > 0 for code in codes), True,
        ),
    }
    result = {
        name: {"actual": actual, "expected": expected, "reproduced": actual == expected}
        for name, (actual, expected) in checks.items()
    }
    failed = sorted(n for n, c in result.items() if not c["reproduced"])
    return {"all_reproduced": not failed, "failed": failed, "checks": result}


# ---------------------------------------------------------------------------
# 2. Phase A — the structural decision, taken without any C8 value
# ---------------------------------------------------------------------------
def run_phase_a(config, table, crosswalks, definitions, io_source) -> dict:
    exposures, decisions = {}, []
    permitted_sources = config["proxy_fitness"][
        "product_specific_evidence_sources_permitted_in_phase_a"
    ]
    for crosswalk in crosswalks:
        exposure = EX.industry_exposure(table, crosswalk)
        for contribution in exposure.contributions:
            contribution.io_sector_label = definitions[
                contribution.io_sector_code
            ]["label"]
        exposures[crosswalk.industry_id] = exposure

        fitness = PF.decide_proxy_fitness(
            exposure, product_specific_evidence=None,
            inspected_sources=permitted_sources,
        )
        direction = PF.decide_direction(exposure)
        PF.assert_direction_not_forced(exposure, direction)
        eligibility = PF.decide_eligibility(exposure, fitness, direction)

        for channel_id in sorted(FC.VARIANT_BY_CHANNEL):
            row = {
                "industry_id": exposure.industry_id,
                "industry_name": exposure.industry_name,
                "channel_id": channel_id,
                "variant_id": FC.VARIANT_BY_CHANNEL[channel_id],
                "io_sector_code": EX.FUEL_OIL_SECTOR_CODE,
                "io_sector_label": EX.FUEL_OIL_SECTOR_LABEL,
                "direct_exposure": exposure.direct_exposure,
                "exposure_weighted_mean_form": exposure.weighted_mean_form,
                "exposure_summed_flow_form": exposure.summed_flow_form,
                "exposure_reconciliation_residual": exposure.reconciliation_residual,
                "observed_zero": exposure.observed_zero,
                "industry_contains_the_producer_sector":
                    exposure.industry_contains_the_producer_sector,
                "component_sector_codes": [
                    c.io_sector_code for c in exposure.contributions
                ],
                "gross_output_weights": {
                    c.io_sector_code: c.output_weight for c in exposure.contributions
                },
                "proxy_fit": fitness["proxy_fit"],
                "confidence": fitness["confidence"],
                "product_specific_evidence_available":
                    fitness["product_specific_evidence_available"],
                "proxy_reason": fitness["reason"],
                "direction_channel": direction["direction_channel"],
                "direction_multiplier": direction["direction_multiplier"],
                "direction_interpretation_level":
                    direction["direction_interpretation_level"],
                "direction_interpretation_volatility":
                    direction["direction_interpretation_volatility"],
                "eligible": eligibility["eligible"],
                "exclusion_reason": eligibility["exclusion_reason"],
                "quality_flag": eligibility["quality_flag"],
                "valuation_basis_alignment":
                    config["valuation"]["valuation_basis_alignment"],
                "structural_source_checksum": io_source["sha256"],
                "target_outcomes_used": False,
                "contributions": [c.to_dict() for c in exposure.contributions],
            }
            row["exposure_row_checksum"] = PF.exposure_row_checksum(row)
            decisions.append(row)

    # Nothing that reached Phase A may carry a C8 numeric value.
    PF.assert_no_numeric_source_values(decisions, "Phase A decision table")

    checksum = PF.phase_a_checksum(decisions)
    for row in decisions:
        row["phase_a_decision_checksum"] = checksum

    eligible_industries = sorted({
        r["industry_id"] for r in decisions
        if r["channel_id"] == "eppo_fo600_channel" and r["eligible"]
    })
    ineligible_industries = sorted({
        r["industry_id"] for r in decisions
        if r["channel_id"] == "eppo_fo600_channel" and not r["eligible"]
    })
    per_channel = {}
    for channel_id in sorted(FC.VARIANT_BY_CHANNEL):
        rows = [r for r in decisions if r["channel_id"] == channel_id]
        per_channel[channel_id] = {
            "eligible": sorted(r["industry_id"] for r in rows if r["eligible"]),
            "ineligible": sorted(r["industry_id"] for r in rows if not r["eligible"]),
        }

    expected = {}
    for channel_id, entry in per_channel.items():
        expected[channel_id] = FC.expected_conditioned_counts(
            source_finite=config["expected_counts"]["c8_source_finite_rows"] // 2,
            source_null=config["expected_counts"]["c8_source_null_rows"] // 2,
            eligible_industries=len(entry["eligible"]),
            ineligible_industries=len(entry["ineligible"]),
            rows_per_channel_pair=(
                config["expected_counts"]["c8_rows_per_channel_pair"] // 2
            ),
        )
    combined = {
        key: sum(entry[key] for entry in expected.values())
        for key in ("full_grid_rows", "source_numeric_rows", "source_gap_rows",
                    "ineligible_rows")
    }

    return {
        "phase": "A",
        "phase_a_version": PF.PHASE_A_VERSION,
        "structural_decision_checksum": checksum,
        "decisions": decisions,
        "exposure_summary": EX.exposure_summary(list(exposures.values())),
        "eligible_industries_per_channel": len(eligible_industries),
        "ineligible_industries_per_channel": len(ineligible_industries),
        "eligible_industries": eligible_industries,
        "ineligible_industries": ineligible_industries,
        "per_channel_eligibility": per_channel,
        "expected_phase_b_counts_per_channel": expected,
        "expected_phase_b_counts": combined,
        "c8_numeric_values_read": False,
        "mpi_values_read": False,
        "targets_read": False,
        "predictions_read": False,
        "evaluation_metrics_read": False,
    }


# ---------------------------------------------------------------------------
# 3. Phase B — conditioning, only after the freeze is reasserted
# ---------------------------------------------------------------------------
def load_c8_rows() -> list:
    frame = pd.read_parquet(C8_PARQUET)
    rows = frame.to_dict("records")
    for row in rows:
        value = row["feature_value"]
        row["feature_value"] = None if pd.isna(value) else float(value)
        for column in ("required_input_months", "missing_input_months"):
            row[column] = [str(x) for x in (row[column] if row[column] is not None else [])]
    return rows


def run_phase_b(config, phase_a, c8_rows, definitions, io_source,
                c7_5_checksum) -> tuple:
    frozen = phase_a["structural_decision_checksum"]
    PF.assert_phase_a_frozen(phase_a["decisions"], frozen)

    decisions = {
        (row["industry_id"], row["channel_id"]): row for row in phase_a["decisions"]
    }
    months = sorted({row["reference_month"] for row in c8_rows})
    structural_month = config["availability"]["structural_available_month"]
    records = {}

    def lineage(row, decision, source):
        structural = CL.StructuralLineage(
            io_sector_code=decision["io_sector_code"],
            io_sector_label=decision["io_sector_label"],
            nesdc_workbook_sha256=io_source["sha256"],
            industry_id=decision["industry_id"],
            crosswalk_version=config["config_version"],
            component_sector_codes=list(decision["component_sector_codes"]),
            gross_output_weights=dict(decision["gross_output_weights"]),
            direct_exposure=decision["direct_exposure"],
            exposure_weighted_mean_form=decision["exposure_weighted_mean_form"],
            exposure_summed_flow_form=decision["exposure_summed_flow_form"],
            proxy_fit=decision["proxy_fit"],
            proxy_confidence=decision["confidence"],
            direction_channel=decision["direction_channel"],
            direction_multiplier=decision["direction_multiplier"],
            structural_available_month=structural_month,
            structural_availability_evidence=config["availability"]["evidence_type"],
            phase_a_decision_checksum=decision["phase_a_decision_checksum"],
        )
        record = CL.conditioned_lineage_record(
            row, structural, c7_5_checksum, FC.CONDITIONING_FORMULA_VERSION
        )
        records[(row.variant_id, row.industry_id, row.reference_month,
                 row.transformation_id)] = record
        _ = source
        return CL.conditioned_lineage_checksum(record)

    rows = FC.build_conditioned_grid(
        c8_rows, decisions, months, structural_month, lineage
    )
    # Eligibility must be identical AFTER the values were seen.
    PF.assert_phase_a_frozen(phase_a["decisions"], frozen)
    _ = definitions
    return rows, records


def reconcile_counts(rows, phase_a) -> dict:
    expected = phase_a["expected_phase_b_counts"]
    statuses = Counter(row.conditioned_status for row in rows)
    ineligible = sum(
        count for status, count in statuses.items()
        if status in ("not_generated_due_to_direction_ambiguity",
                      "not_generated_due_to_proxy_ineligibility",
                      "structural_exposure_unresolved")
    )
    source_gap = sum(
        count for status, count in statuses.items() if status.startswith("source_")
    )
    numeric = statuses["available_nonzero"] + statuses[
        "zero_due_to_observed_zero_exposure"
    ]
    observed = {
        "full_grid_rows": len(rows),
        "source_numeric_rows": numeric,
        "source_gap_rows": source_gap,
        "ineligible_rows": ineligible,
    }
    disagreements = [
        {"field": key, "expected": expected[key], "observed": observed[key]}
        for key in expected if expected[key] != observed[key]
    ]
    return {
        "expected": expected,
        "expected_per_channel": phase_a["expected_phase_b_counts_per_channel"],
        "observed": observed,
        "status_counts": dict(sorted(statuses.items())),
        "disagreements": disagreements,
        "counts_reconciled": not disagreements,
        "expected_counts_edited_after_conditioning": False,
    }


def split_ranges() -> dict:
    splits = load_yaml(SPLITS_CONFIG)["split"]
    locked = splits["locked_test"]["horizons"]
    return {
        "development": (splits["development"]["start"], splits["development"]["end"]),
        "purge": (splits["purge"]["start"], splits["purge"]["end"]),
        "locked_test": (min(h["start"] for h in locked.values()),
                        max(h["end"] for h in locked.values())),
    }


def write_parquet(rows, path, list_columns=(), dict_columns=()):
    frame = pd.DataFrame(rows)
    for column in list_columns:
        if column in frame.columns:
            frame[column] = frame[column].apply(lambda v: list(v or []))
    for column in dict_columns:
        if column in frame.columns:
            frame[column] = frame[column].apply(
                lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True)
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    # --- shared structural inputs ------------------------------------------
    source_audit = load_json(C3_SOURCE_AUDIT)
    by_role = {record["role"]: record for record in source_audit["acquired"]}
    io_source = by_role["primary_io_table"]
    for role, record in by_role.items():
        path = ROOT / record["local_path"]
        if not path.is_file():
            raise SystemExit(f"C9 stops: {role} missing at {path}")
        actual = SM.sha256_of_file(path)
        if actual != record["sha256"]:
            raise SystemExit(
                f"C9 stops: {role} checksum {actual[:16]} != recorded "
                f"{record['sha256'][:16]}"
            )
    table = IO.parse_io_workbook(
        ROOT / io_source["local_path"], "2015", io_source["final_url"],
        io_source["sha256"],
    )
    definitions = IO.parse_sector_definitions(
        ROOT / by_role["sector_classification_and_definitions"]["local_path"]
    )
    codes, _a, _diag = CO.build_technical_coefficients(table)
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(
        load_yaml(C3_CONFIG), taxonomy, definitions
    )

    invariants = reproduce_upstream_invariants(table, codes, crosswalks, definitions)
    if not invariants["all_reproduced"]:
        raise SystemExit(
            f"C9 stops: upstream invariants did not reproduce: {invariants['failed']}. "
            "Upstream artifacts are not repaired here."
        )
    EX.assert_sector_is_093(
        EX.FUEL_OIL_SECTOR_CODE, definitions[EX.FUEL_OIL_SECTOR_CODE]["label"]
    )
    EX.assert_no_final_demand_or_value_added(codes, table.sector_codes)

    # --- Phase A ------------------------------------------------------------
    phase_a = run_phase_a(config, table, crosswalks, definitions, io_source)
    phase_a_payload = {
        "task": "C9",
        "phase": "A",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "phase_a_version": phase_a["phase_a_version"],
        "phases": config["phases"],
        "upstream_invariants": invariants,
        "exposure": {
            **config["exposure"],
            "summary": phase_a["exposure_summary"],
            "sector_093_definition": definitions[EX.FUEL_OIL_SECTOR_CODE],
        },
        "valuation": config["valuation"],
        "proxy_fitness": config["proxy_fitness"],
        "direction": config["direction"],
        "eligibility": config["eligibility"],
        "structural_audit_grid": {
            **config["structural_audit_grid"],
            "rows_built": len(phase_a["decisions"]),
        },
        "decisions": phase_a["decisions"],
        "eligible_industries": phase_a["eligible_industries"],
        "ineligible_industries": phase_a["ineligible_industries"],
        "eligible_industries_per_channel": phase_a["eligible_industries_per_channel"],
        "ineligible_industries_per_channel": phase_a["ineligible_industries_per_channel"],
        "per_channel_eligibility": phase_a["per_channel_eligibility"],
        "expected_phase_b_counts": phase_a["expected_phase_b_counts"],
        "expected_phase_b_counts_per_channel":
            phase_a["expected_phase_b_counts_per_channel"],
        "structural_decision_checksum": phase_a["structural_decision_checksum"],
        "c8_numeric_values_read": False,
        "mpi_values_read": False,
        "targets_read": False,
        "predictions_read": False,
        "evaluation_metrics_read": False,
    }
    phase_a_payload["content_checksum"] = CL.content_checksum(phase_a_payload)
    DOCS.mkdir(parents=True, exist_ok=True)
    with open(PHASE_A_JSON, "w", encoding="utf-8") as handle:
        json.dump(phase_a_payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")

    # --- the freeze: re-read the written artifact before any value is loaded --
    frozen = load_json(PHASE_A_JSON)
    PF.assert_phase_a_frozen(
        frozen["decisions"], frozen["structural_decision_checksum"]
    )
    if frozen["structural_decision_checksum"] != phase_a["structural_decision_checksum"]:
        raise SystemExit("C9 stops: the written Phase-A artifact does not match")

    # --- Phase B ------------------------------------------------------------
    c8_rows = load_c8_rows()
    c7_5_checksum = load_json(C7_5_DECISION)["content_checksum"]
    rows, lineage_records = run_phase_b(
        config, frozen, c8_rows, definitions, io_source, c7_5_checksum
    )
    counts = reconcile_counts(rows, frozen)
    if not counts["counts_reconciled"]:
        raise SystemExit(
            "C9 stops: Phase-B count reconciliation failed. "
            f"{json.dumps(counts['disagreements'], ensure_ascii=False)}"
        )

    table_rows = [row.to_dict() for row in rows]
    for row in table_rows:
        FC.assert_null_not_converted_to_zero(row)
    FC.assert_valuation_claim_permitted(
        config["valuation"]["valuation_basis_alignment"]
    )

    industries = sorted({row["industry_id"] for row in table_rows})
    transformations = sorted({row["transformation_id"] for row in table_rows})
    cells, snapshot_summary = SN.build_development_snapshot(
        table_rows, industries, transformations,
        config["development_snapshot"]["issue_month_start"],
        config["development_snapshot"]["issue_month_end"],
    )
    coverage = SN.issue_key_range_coverage(split_ranges(), table_rows)

    conditioned_frame = write_parquet(
        table_rows, CONDITIONED_PARQUET,
        list_columns=("source_required_input_months", "source_missing_input_months"),
    )
    snapshot_frame = write_parquet(
        [cell.to_dict() for cell in cells], SNAPSHOT_PARQUET
    )

    availability_violations = [
        row for row in table_rows
        if row["conditioned_policy_available_month"] != max(
            row["source_policy_available_month"], row["structural_available_month"]
        )
        or row["source_available_as_of"] is not None
    ]
    if availability_violations:
        raise SystemExit(
            f"C9 stops: {len(availability_violations)} rows violate the "
            "availability rule"
        )

    readiness = {}
    for variant_id in sorted(FC.VARIANT_BY_CHANNEL.values()):
        variant_rows = [r for r in table_rows if r["variant_id"] == variant_id]
        numeric = [r for r in variant_rows if r["conditioned_value"] is not None]
        readiness[variant_id] = {
            "industry_conditioned_features_created": True,
            "ready_for_development_only_assembly": bool(
                counts["counts_reconciled"] and numeric
                and all(r["conditioned_lineage_checksum"] for r in variant_rows)
                and all(r["source_available_as_of"] is None for r in variant_rows)
                and all(not r["additive_aggregation_allowed"] for r in variant_rows)
            ),
            "rows": len(variant_rows),
            "numeric_rows": len(numeric),
            "null_rows": len(variant_rows) - len(numeric),
            "feature_semantics_approved": False,
            "model_feature_approved": False,
        }

    audit = {
        "task": "C9",
        "phase": "B",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "conditioning_formula_version": FC.CONDITIONING_FORMULA_VERSION,
        "phase_a_decision_checksum": frozen["structural_decision_checksum"],
        "phase_a_content_checksum": frozen["content_checksum"],
        "phase_a_reasserted_before_loading_values": True,
        "phase_a_reasserted_after_conditioning": True,
        "upstream_invariants": invariants,
        "inherited_status": config["inherited_status"],
        "inherited_restrictions": config["inherited_restrictions"],
        "timing_policy": config["timing_policy"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "exposure_summary": frozen["exposure"]["summary"],
        "valuation": config["valuation"],
        "conditioning": config["conditioning"],
        "status_precedence": config["status_precedence"],
        "counts": counts,
        "conditioned_table": {
            "rows": len(table_rows),
            "unique_key": ["variant_id", "industry_id", "reference_month",
                           "transformation_id"],
            "output": str(CONDITIONED_PARQUET.relative_to(ROOT)).replace("\\", "/"),
            "status_counts": counts["status_counts"],
            "by_variant": {
                variant: dict(sorted(Counter(
                    r["conditioned_status"] for r in table_rows
                    if r["variant_id"] == variant
                ).items()))
                for variant in sorted(FC.VARIANT_BY_CHANNEL.values())
            },
            "units": FC.CONDITIONED_UNITS,
            "model_feature_approved_rows": sum(
                1 for r in table_rows if r["model_feature_approved"]
            ),
        },
        "variants": {
            **config["variant_restrictions"],
            "shared_structural_exposure_group": FC.SHARED_STRUCTURAL_EXPOSURE_GROUP,
            "variant_ids": sorted(FC.VARIANT_BY_CHANNEL.values()),
        },
        "availability": {
            **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
               for k, v in config["availability"].items()},
            "rows_checked": len(table_rows),
            "violations": 0,
            "source_policy_dominates_rows": sum(
                1 for r in table_rows
                if r["conditioned_policy_available_month"]
                == r["source_policy_available_month"]
            ),
            "source_available_as_of_null_rows": sum(
                1 for r in table_rows if r["source_available_as_of"] is None
            ),
        },
        "lineage": {
            "lineage_version": CL.CONDITIONED_LINEAGE_VERSION,
            "rows_with_a_checksum": sum(
                1 for r in table_rows if r["conditioned_lineage_checksum"]
            ),
            "distinct_checksums": len({
                r["conditioned_lineage_checksum"] for r in table_rows
            }),
            "null_rows_with_complete_lineage": sum(
                1 for key, record in lineage_records.items()
                if record["conditioned_value"] is None
                and record["structural_chain"]["phase_a_decision_checksum"]
                and record["source_chain"]["source_transformation_lineage_checksum"]
            ),
            "source_chain_fields": list(CL.SOURCE_CHAIN_FIELDS),
            "structural_chain_fields": list(CL.STRUCTURAL_CHAIN_FIELDS),
            "c7_5_semantic_mapping_checksum": c7_5_checksum,
        },
        "development_snapshot": {
            **config["development_snapshot"],
            **snapshot_summary.to_dict(),
            "output": str(SNAPSHOT_PARQUET.relative_to(ROOT)).replace("\\", "/"),
        },
        "issue_key_coverage": coverage,
        "readiness": readiness,
        "authorization_after_c9": {
            **config["authorization_after_c9"],
            "ready_for_development_only_assembly": {
                variant: entry["ready_for_development_only_assembly"]
                for variant, entry in readiness.items()
            },
        },
    }
    audit["content_checksum"] = CL.content_checksum(audit)
    with open(DOCS / "c9_fuel_oil_conditioning_audit.json", "w", encoding="utf-8") as h:
        json.dump(audit, h, ensure_ascii=False, indent=1, sort_keys=True)
        h.write("\n")

    write_phase_a_markdown(phase_a_payload)
    write_audit_markdown(audit)

    print(json.dumps({
        "upstream_invariants_reproduced": invariants["all_reproduced"],
        "phase_a_decision_checksum": frozen["structural_decision_checksum"],
        "structural_audit_rows": len(frozen["decisions"]),
        "eligible_industries_per_channel": frozen["eligible_industries_per_channel"],
        "ineligible_industries": frozen["ineligible_industries"],
        "conditioned_rows": len(table_rows),
        "status_counts": counts["status_counts"],
        "counts_reconciled": counts["counts_reconciled"],
        "snapshot_cells": snapshot_summary.cells,
        "snapshot_states": snapshot_summary.state_counts,
        "readiness": {
            k: v["ready_for_development_only_assembly"] for k, v in readiness.items()
        },
        "content_checksum": audit["content_checksum"],
        "conditioned_shape": list(conditioned_frame.shape),
        "snapshot_shape": list(snapshot_frame.shape),
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def write_phase_a_markdown(payload: dict) -> None:
    summary = payload["exposure"]["summary"]
    lines = [
        "# Task C9 Phase A - Sector-093 Exposure and Structural Decision",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`, "
        f"version `{payload['phase_a_version']}`.*",
        "",
        "Decided from I/O and domain evidence only. No C8 numeric value, MPI value,",
        "target, prediction or metric was read; the table below was hashed and frozen",
        "before Phase B opened the C8 file.",
        "",
        f"**Frozen structural decision checksum:** `{payload['structural_decision_checksum']}`",
        "",
        "## The sector",
        "",
        f"`{payload['exposure']['io_sector_code']}` "
        f"**{payload['exposure']['io_sector_label']}**",
        "",
        "> " + payload["exposure"]["sector_093_definition"]["definition"],
        "",
        "Fuel oil is **one of nine** named products in that basket, which is why a",
        "positive coefficient proves purchase from the refinery-products sector and",
        "not purchase of FO 600 or FO 1500.",
        "",
        "## Exposure formula",
        "",
        f"* direct: `{payload['exposure']['direct_coefficient_formula']}`",
        f"* weighted: `{payload['exposure']['industry_aggregation_weighted_form']}`",
        f"* exact:    `{payload['exposure']['industry_aggregation_exact_form']}`",
        "",
        "Both aggregation forms are calculated independently and must agree within",
        f"`{payload['exposure']['reconciliation_tolerance']}`. Observed worst residual: "
        f"**{summary['max_reconciliation_residual']:.3e}**.",
        "",
        "## Exposure by industry",
        "",
        "| industry | name | direct exposure | observed zero | contains 093 |",
        "| --- | --- | --- | --- | --- |",
    ]
    seen = set()
    for row in payload["decisions"]:
        if row["industry_id"] in seen:
            continue
        seen.add(row["industry_id"])
        lines.append(
            f"| `{row['industry_id']}` | {row['industry_name']} | "
            f"{row['direct_exposure']:.10f} | {_flag(row['observed_zero'])} | "
            f"{_flag(row['industry_contains_the_producer_sector'])} |"
        )
    lines += [
        "",
        f"minimum {summary['minimum']:.10f}, median {summary['median']:.10f}, "
        f"maximum {summary['maximum']:.10f}; observed zeros "
        f"**{summary['observed_zero_count']}**; unresolved "
        f"**{summary['unresolved_count']}**.",
        "",
        "> " + summary["note"],
        "",
        "## Price stage versus valuation basis",
        "",
        "| field | value |",
        "| --- | --- |",
        f"| EPPO price stage | `{payload['valuation']['eppo_price_stage']}` |",
        f"| I/O valuation basis | `{payload['valuation']['io_valuation_basis']}` |",
        f"| I/O import treatment | `{payload['valuation']['io_import_treatment']}` |",
        f"| alignment | `{payload['valuation']['valuation_basis_alignment']}` |",
        f"| structural interaction only | "
        f"{_flag(payload['valuation']['structural_interaction_only'])} |",
        f"| monetary cost measure | "
        f"{_flag(payload['valuation']['monetary_cost_measure'])} |",
        f"| elasticity | {_flag(payload['valuation']['elasticity'])} |",
        f"| causal effect | {_flag(payload['valuation']['causal_effect'])} |",
        "",
        "> " + payload["valuation"]["prohibited_claim"].strip(),
        "",
        "## Proxy fitness, direction and eligibility",
        "",
        "| industry | proxy fit | confidence | direction | multiplier | eligible "
        "| exclusion reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    seen = set()
    for row in payload["decisions"]:
        if row["industry_id"] in seen:
            continue
        seen.add(row["industry_id"])
        lines.append(
            f"| `{row['industry_id']}` | `{row['proxy_fit']}` | "
            f"`{row['confidence']}` | `{row['direction_channel']}` | "
            f"`{row['direction_multiplier']}` | {_flag(row['eligible'])} | "
            f"`{row['exclusion_reason']}` |"
        )
    lines += [
        "",
        "Both channels receive identical structural decisions: the exposure vector",
        "and the direction depend on the industry, not on which fuel oil is used.",
        "",
        f"Eligible industries per channel: **{payload['eligible_industries_per_channel']}** "
        f"({', '.join(payload['eligible_industries'])}).",
        "",
        f"Ineligible: **{payload['ineligible_industries_per_channel']}** "
        f"({', '.join(payload['ineligible_industries']) or 'none'}).",
        "",
        "## Preregistered Phase-B counts",
        "",
        "| field | rows |",
        "| --- | --- |",
    ]
    for key, value in payload["expected_phase_b_counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines += [
        "",
        "Derived from the frozen eligibility before any C8 value was read, and not",
        "edited afterwards.",
        "",
    ]
    (DOCS / "c9_sector093_exposure_decision.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_audit_markdown(payload: dict) -> None:
    counts = payload["counts"]
    lines = [
        "# Task C9 Phase B - Industry-Conditioned Fuel-Oil Features",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`, formula "
        f"`{payload['conditioning_formula_version']}`.*",
        "",
        f"Phase-A decision checksum `{payload['phase_a_decision_checksum']}`, "
        "reasserted before the C8 values were loaded and again after conditioning.",
        "",
        "## Upstream invariants",
        "",
        f"All reproduced: **{payload['upstream_invariants']['all_reproduced']}** "
        f"({len(payload['upstream_invariants']['checks'])} checks).",
        "",
        "| check | expected | actual |",
        "| --- | --- | --- |",
    ]
    for name, check in payload["upstream_invariants"]["checks"].items():
        lines.append(f"| `{name}` | `{check['expected']}` | `{check['actual']}` |")

    lines += [
        "",
        "## Conditioned grid",
        "",
        f"`{payload['conditioned_table']['output']}` - "
        f"**{payload['conditioned_table']['rows']}** rows, key "
        f"`{' + '.join(payload['conditioned_table']['unique_key'])}`. "
        f"Counts reconciled: **{counts['counts_reconciled']}**.",
        "",
        "| field | expected | observed |",
        "| --- | --- | --- |",
    ]
    for key, value in counts["expected"].items():
        lines.append(f"| `{key}` | {value} | {counts['observed'][key]} |")
    lines += ["", "| status | rows |", "| --- | --- |"]
    for status, count in counts["status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines += ["", "### By variant", "",
              "| variant | " + " | ".join(
                  f"`{s}`" for s in counts["status_counts"]) + " |",
              "| --- | " + " | ".join("---" for _ in counts["status_counts"]) + " |"]
    for variant, statuses in payload["conditioned_table"]["by_variant"].items():
        cells = " | ".join(
            str(statuses.get(status, 0)) for status in counts["status_counts"]
        )
        lines.append(f"| `{variant}` | {cells} |")

    lines += [
        "",
        "## Conditioning formula and units",
        "",
        f"`{payload['conditioning']['formula']}`",
        "",
        "| transformation | conditioned unit |",
        "| --- | --- |",
    ]
    for name, unit in payload["conditioned_table"]["units"].items():
        lines.append(f"| `{name}` | `{unit}` |")
    lines += [
        "",
        f"`not_a_currency_cost`: {_flag(payload['conditioning']['not_a_currency_cost'])}, "
        f"`not_an_elasticity`: {_flag(payload['conditioning']['not_an_elasticity'])}, "
        f"`not_a_forecast_coefficient`: "
        f"{_flag(payload['conditioning']['not_a_forecast_coefficient'])}.",
        "",
        "Status precedence: "
        + " -> ".join(f"`{s}`" for s in payload["status_precedence"]) + ".",
        "",
        "## Variants",
        "",
        f"Shared exposure group `{payload['variants']['shared_structural_exposure_group']}`; "
        "both variants carry the SAME sector-093 vector, which is exactly why they",
        "are never combined.",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["variants"].items():
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {_flag(value)} |")

    availability = payload["availability"]
    lines += [
        "",
        "## Availability",
        "",
        f"`conditioned_policy_available_month = {availability['rule']}`. "
        f"Structural availability **{availability['structural_available_by']}** "
        f"(reference year {availability['structural_reference_year']}); "
        f"`backdated_to_reference_year`: "
        f"{_flag(availability['backdated_to_reference_year'])}, "
        f"`download_timestamp_used`: {_flag(availability['download_timestamp_used'])}.",
        "",
        f"The source policy dominates in "
        f"{availability['source_policy_dominates_rows']} of "
        f"{availability['rows_checked']} rows; "
        f"`source_available_as_of` is null in "
        f"{availability['source_available_as_of_null_rows']}.",
        "",
        "## Lineage",
        "",
        f"`{payload['lineage']['lineage_version']}` - "
        f"{payload['lineage']['rows_with_a_checksum']} rows carry a checksum, "
        f"{payload['lineage']['distinct_checksums']} distinct, and "
        f"{payload['lineage']['null_rows_with_complete_lineage']} null rows carry "
        "the full source and structural chains.",
        "",
        "## Development snapshot",
        "",
        f"`{payload['development_snapshot']['output']}` - "
        f"{payload['development_snapshot']['issue_months']} issue months x "
        f"{payload['development_snapshot']['variants']} variants x "
        f"{payload['development_snapshot']['industries']} industries x "
        f"{payload['development_snapshot']['transformations']} transformations = "
        f"**{payload['development_snapshot']['cells']}** cells.",
        "",
        "| cell state | cells |",
        "| --- | --- |",
    ]
    for state, count in payload["development_snapshot"]["state_counts"].items():
        lines.append(f"| `{state}` | {count} |")

    lines += [
        "",
        "## Issue-key coverage",
        "",
        "From key ranges only; no target value, prediction or metric was read.",
        "",
        "| split | variant | issue months | reference range | materialised |",
        "| --- | --- | --- | --- | --- |",
    ]
    for split_name, per_variant in payload["issue_key_coverage"].items():
        if not isinstance(per_variant, dict):
            continue
        for variant_id, entry in per_variant.items():
            lines.append(
                f"| `{split_name}` | `{variant_id}` | {entry['issue_months']} | "
                f"{entry['reference_month_range'][0]} .. "
                f"{entry['reference_month_range'][1]} | "
                f"{_flag(entry['materialised'])} |"
            )

    lines += [
        "",
        "## Readiness and authorization",
        "",
        "| variant | rows | numeric | null | ready for development-only assembly |",
        "| --- | --- | --- | --- | --- |",
    ]
    for variant_id, entry in payload["readiness"].items():
        lines.append(
            f"| `{variant_id}` | {entry['rows']} | {entry['numeric_rows']} | "
            f"{entry['null_rows']} | "
            f"{_flag(entry['ready_for_development_only_assembly'])} |"
        )
    lines += ["", "| field | value |", "| --- | --- |"]
    for key, value in payload["authorization_after_c9"].items():
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {_flag(value)} |")
    lines += [
        "",
        "> " + payload["authorization_after_c9"]["note"].strip(),
        "",
        f"Content checksum `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c9_fuel_oil_conditioning_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
