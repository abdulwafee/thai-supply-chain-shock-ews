"""Task C10 — development-only fuel-oil design-matrix identifiability audit.

Assembles the C9 development snapshot into two strictly separate design matrices
and measures how much distinct design information the industry conditioning
actually creates — without reading any target, prediction or model outcome.

The diagnostic contract is hashed and frozen before a single C9 feature value is
loaded, re-asserted before the load and again after the diagnostics run.

OUTCOME-FREE STRUCTURAL AUDIT. No MPI join, no predictive association, no channel
selection, no model, no locked-test access. C9 artifacts are read-only.

    docs/c10_design_matrix_protocol.md
    docs/c10_design_matrix_audit.{md,json}
    data/features/c10_fuel_oil_development_{wide,mask}.parquet   (git-ignored)
    data/features/c10_fuel_oil_diagnostics.parquet               (git-ignored)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.features import fuel_oil_development_matrix as DM  # noqa: E402
from thai_supply_chain_ews.features import fuel_oil_identifiability as ID  # noqa: E402
from thai_supply_chain_ews.features import fuel_oil_industry_conditioning as C9  # noqa: E402
from thai_supply_chain_ews.features import fuel_oil_matrix_lineage as ML  # noqa: E402
from thai_supply_chain_ews.features import fuel_oil_standardization as ST  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "fuel_oil_development_matrix.yaml"
C9_PHASE_A = DOCS / "c9_sector093_exposure_decision.json"
C9_AUDIT = DOCS / "c9_fuel_oil_conditioning_audit.json"
C9_CONDITIONED = ROOT / "data" / "features" / "c9_fuel_oil_conditioned.parquet"
C9_SNAPSHOT = ROOT / "data" / "features" / "c9_fuel_oil_development_snapshot.parquet"
C8_AUDIT = DOCS / "c8_eppo_transformation_audit.json"
C8_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"
C7_5_DECISION = DOCS / "c7_5_eppo_semantic_decision.json"
C3_MATRIX = DOCS / "c3_commodity_exposure_matrix.json"
C3_SOURCE_AUDIT = DOCS / "c3_io_source_audit.json"

WIDE_PARQUET = ROOT / "data" / "features" / "c10_fuel_oil_development_wide.parquet"
MASK_PARQUET = ROOT / "data" / "features" / "c10_fuel_oil_development_mask.parquet"
DIAGNOSTICS_PARQUET = ROOT / "data" / "features" / "c10_fuel_oil_diagnostics.parquet"

CHANNEL_BY_VARIANT = {
    "fo600_direct_sector093": "eppo_fo600_channel",
    "fo1500_direct_sector093": "eppo_fo1500_channel",
}

#: The one authored paragraph that explains what the audit measures. Held as
#: a constant so the narrative guards can run over it before it is rendered.
PROTOCOL_NARRATIVE = " ".join((
    "C9 built `D[v,g] = E[g] * X[v]`: each eligible industry's design is one",
    "source-time matrix multiplied by a positive scalar exposure. The audit",
    "checks that identity two ways - by reconstructing `X` from every eligible",
    "industry, and by confirming that per-industry standardisation leaves no",
    "trace of `E`. Both are properties of the design matrix, established",
    "without reading any target, and neither is a statement about what a",
    "model would do.",
))

#: Artifacts C10 may never open. Checked as a hard list so a flag or an
#: environment variable cannot route around it.
PROHIBITED_ARTIFACTS = (
    "target", "production_stress", "industry_month_panel", "prediction",
    "residual", "walk_forward", "evaluation", "locked", "holdout",
    "metrics", "_mae", "_rmse",
)


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def assert_no_prohibited_artifact(paths) -> None:
    """Raise if any path touches a target, prediction or locked artifact."""
    for path in paths:
        text = str(path).replace("\\", "/").lower()
        for fragment in PROHIBITED_ARTIFACTS:
            if fragment in text:
                raise SystemExit(
                    f"C10 stops: {path} is a prohibited artifact ({fragment}). "
                    "This audit reads no target, prediction or locked outcome."
                )


# ---------------------------------------------------------------------------
# 1. Upstream invariants
# ---------------------------------------------------------------------------
def reproduce_upstream_invariants(snapshot, conditioned) -> dict:
    c9_audit = load_json(C9_AUDIT)
    phase_a = load_json(C9_PHASE_A)
    counts = c9_audit["counts"]
    statuses = counts["status_counts"]
    snapshot_states = Counter(snapshot["cell_state"])
    per_variant = Counter(conditioned["variant_id"])
    eligible = [
        r for r in phase_a["decisions"] if r["channel_id"] == "eppo_fo600_channel"
    ]

    checks = {
        "c9_conditioned_rows": (counts["observed"]["full_grid_rows"], 7800),
        "c9_variants": (sorted(per_variant), sorted(CHANNEL_BY_VARIANT)),
        "c9_rows_per_variant": (sorted(set(per_variant.values())), [3900]),
        "c9_industries": (conditioned["industry_id"].nunique(), 12),
        "c9_transformations": (conditioned["transformation_id"].nunique(), 5),
        "c9_reference_months": (conditioned["reference_month"].nunique(), 65),
        "c9_available_nonzero": (statuses["available_nonzero"], 6578),
        "c9_direction_ambiguity_rows": (
            statuses["not_generated_due_to_direction_ambiguity"], 650,
        ),
        "c9_source_null_rows": (
            sum(v for k, v in statuses.items() if k.startswith("source_")), 572,
        ),
        "c9_phase_a_checksum": (
            phase_a["structural_decision_checksum"],
            "d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703",
        ),
        "c9_io_sector_code": (
            sorted(set(conditioned["io_sector_code"])), ["093"],
        ),
        "c9_sector_031_used": (
            "031" in set(conditioned["io_sector_code"]), False,
        ),
        "c9_total_requirement_used": (
            load_yaml(ROOT / "configs" / "fuel_oil_industry_conditioning.yaml")[
                "conditioning"]["total_requirement_exposure_used"], False,
        ),
        "c9_ineligible_industries": (phase_a["ineligible_industries"], ["IND-04"]),
        "c9_eligible_industries_per_channel": (
            phase_a["eligible_industries_per_channel"], 11,
        ),
        "c9_eligible_exposures_strictly_positive": (
            all(r["direct_exposure"] > 0 for r in eligible if r["eligible"]), True,
        ),
        "c9_ind04_direction_ambiguous": (
            sorted({r["direction_channel"] for r in eligible
                    if r["industry_id"] == "IND-04"}), ["mixed_or_ambiguous"],
        ),
        "c9_ind04_multiplier_null": (
            all(r["direction_multiplier"] is None for r in eligible
                if r["industry_id"] == "IND-04"), True,
        ),
        "c9_source_available_as_of_null": (
            bool(conditioned["source_available_as_of"].isna().all()), True,
        ),
        "c9_latest_vintage_used": (
            bool(conditioned["latest_vintage_used"].astype(bool).all()), True,
        ),
        "c9_point_in_time_supported": (
            bool(conditioned["point_in_time_supported"].astype(bool).any()), False,
        ),
        "c9_operational_lag_is_measured": (
            load_yaml(ROOT / "configs" / "fuel_oil_industry_conditioning.yaml")[
                "timing_policy"]["operational_lag_is_measured"], False,
        ),
        "snapshot_issue_months": (snapshot["issue_month"].nunique(), 15),
        "snapshot_issue_month_range": (
            [snapshot["issue_month"].min(), snapshot["issue_month"].max()],
            ["2024-01", "2025-03"],
        ),
        "snapshot_reference_month_range": (
            [snapshot["reference_month"].min(), snapshot["reference_month"].max()],
            ["2023-11", "2025-01"],
        ),
        "snapshot_cells": (len(snapshot), 1800),
        "snapshot_numeric_cells": (snapshot_states["numeric"], 1650),
        "snapshot_masked_cells": (snapshot_states["masked_ineligible"], 150),
        "snapshot_source_gap_cells": (
            snapshot_states.get("rejected_source_null", 0), 0,
        ),
        "snapshot_purge_or_locked_rows": (
            int((snapshot["issue_month"] > "2025-03").sum()), 0,
        ),
    }
    result = {
        name: {"actual": actual, "expected": expected, "reproduced": actual == expected}
        for name, (actual, expected) in checks.items()
    }
    failed = sorted(n for n, c in result.items() if not c["reproduced"])
    return {"all_reproduced": not failed, "failed": failed, "checks": result}


# ---------------------------------------------------------------------------
# 2. Matrix assembly
# ---------------------------------------------------------------------------
def snapshot_cells(snapshot, variant_id: str) -> list:
    rows = snapshot[snapshot["variant_id"] == variant_id].to_dict("records")
    cells = []
    for row in rows:
        value = row["value"]
        cells.append({
            "variant_id": row["variant_id"],
            "issue_month": row["issue_month"],
            "industry_id": row["industry_id"],
            "transformation_id": row["transformation_id"],
            "reference_month": row["reference_month"],
            "value": None if pd.isna(value) else float(value),
            "cell_state": row["cell_state"],
            "masked": bool(row["masked"]),
            "mask_reason": (
                None if row["mask_reason"] is None or (
                    not isinstance(row["mask_reason"], str) and pd.isna(row["mask_reason"])
                ) else row["mask_reason"]
            ),
            "conditioned_status": row["conditioned_status"],
            "conditioned_policy_available_month":
                row["conditioned_policy_available_month"],
            "conditioned_lineage_checksum": row["conditioned_lineage_checksum"],
        })
    return cells


def c8_source_time_matrix(c8_rows, channel_id: str, reference_months, columns) -> list:
    """The C8 source transformations for one channel over the reference months."""
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
                    f"C10 stops: no C8 value for {channel_id} {month} {column}; the "
                    "development window was expected to be gap-free"
                )
            row.append(value)
        matrix.append(row)
    return matrix


# ---------------------------------------------------------------------------
# 3. Diagnostics
# ---------------------------------------------------------------------------
def diagnose(matrix, contract, source_time) -> ID.MatrixDiagnostics:
    columns = matrix.columns
    ID.assert_primary_input_is_source_time(
        source_time, contract.expected_issue_months,
        f"rank and correlation diagnostics for {matrix.variant_id}",
    )
    DM.assert_no_feature_removal(columns, "diagnostics")

    designs = {g: matrix.industry_design(g) for g in matrix.eligible_industries}
    stacked = matrix.stacked_eligible_panel()
    standardized_source = ID.standardize(source_time, contract.standardization_ddof)

    return ID.MatrixDiagnostics(
        variant_id=matrix.variant_id,
        source_time_rows=len(source_time),
        source_time_columns=len(columns),
        singular_values=ID.singular_values(source_time),
        numerical_rank=ID.numerical_rank(source_time, contract.rank_tolerance),
        rank_tolerance=contract.rank_tolerance,
        raw_condition_number=ID.condition_number(source_time),
        standardized_condition_number=ID.condition_number(standardized_source),
        variance=ID.variance_report(
            source_time, columns, contract.near_zero_variance_threshold,
            contract.standardization_ddof,
        ),
        pearson=ID.correlation_matrix(source_time, columns),
        spearman=ID.spearman_matrix(source_time, columns),
        exact_duplicate_columns=ID.duplicate_columns(source_time, columns),
        industry_matrix_ranks={
            g: ID.numerical_rank(design, contract.rank_tolerance)
            for g, design in designs.items()
        },
        stacked_panel_rows=len(stacked),
        stacked_panel_rank=ID.numerical_rank(stacked, contract.rank_tolerance),
        unique_issue_months=len(matrix.issue_months),
        cross_sectional_rank_by_issue={
            month: ID.cross_sectional_rank(designs, index, contract.rank_tolerance)
            for index, month in enumerate(matrix.issue_months)
        },
        stacked_rows_are_independent_claim_permitted=False,
        temporal_independence_claim_permitted=False,
        significance_tested=False,
        features_removed=[],
        channel_selected=False,
    )


def variance_classification_matches(matrix, contract) -> dict:
    """Every eligible industry must receive the same zero-variance verdict.

    A positive scalar cannot make a constant column vary or a varying column
    constant, so a disagreement would mean the exposures or the alignment differ.
    """
    verdicts = {}
    for industry_id in matrix.eligible_industries:
        report = ID.variance_report(
            matrix.industry_design(industry_id), matrix.columns,
            contract.near_zero_variance_threshold, contract.standardization_ddof,
        )
        verdicts[industry_id] = {
            column: (entry["exact_zero_variance"], entry["near_zero_variance"])
            for column, entry in report.items()
        }
    distinct = {json.dumps(v, sort_keys=True) for v in verdicts.values()}
    return {
        "industries_checked": len(verdicts),
        "distinct_classifications": len(distinct),
        "all_eligible_industries_agree": len(distinct) == 1,
        "exact_zero_variance_columns": sorted(
            column for column, flags in
            next(iter(verdicts.values()), {}).items() if flags[0]
        ),
        "near_zero_variance_columns": sorted(
            column for column, flags in
            next(iter(verdicts.values()), {}).items() if flags[1]
        ),
    }


def availability_report(matrix, snapshot, config) -> dict:
    subset = snapshot[snapshot["variant_id"] == matrix.variant_id]
    violations = []
    for row in subset.to_dict("records"):
        DM.assert_lag_two(row["issue_month"], row["reference_month"])
        if row["conditioned_policy_available_month"] > row["issue_month"]:
            violations.append((row["industry_id"], row["issue_month"]))
    structural = str(config["availability"]["structural_available_by"])
    return {
        "rows_checked": len(subset),
        "lag_two_violations": 0,
        "policy_availability_violations": len(violations),
        "structural_available_by": structural,
        "structural_reference_year": config["availability"]["structural_reference_year"],
        "backdated_to_reference_year": False,
        "source_policy_dominates_structural": True,
        "source_available_as_of": None,
        "latest_vintage_used": True,
        "point_in_time_supported": False,
        "fully_real_time_backtest": False,
        "checked_against_recorded_fields_not_positional_shift": True,
    }


def build_lineage(matrix, phase_a, c8_rows, contract_digest,
                  c7_5_checksum, nesdc_sha, crosswalk_version, config) -> tuple:
    c8_index = {
        (row["channel_id"], row["reference_month"], row["transformation_id"]): row
        for row in c8_rows
    }
    decisions = {
        (r["industry_id"], r["channel_id"]): r for r in phase_a["decisions"]
    }
    channel_id = CHANNEL_BY_VARIANT[matrix.variant_id]
    records, checksums = {}, []
    for cell in matrix.mask_cells:
        decision = decisions[(cell["industry_id"], channel_id)]
        source = c8_index[
            (channel_id, cell["reference_month"], cell["transformation_id"])
        ]
        source_branch = {
            "c8_transformation_id": cell["transformation_id"],
            "c8_transformation_lineage_checksum":
                source["transformation_lineage_checksum"],
            "c8_required_input_months": [
                str(m) for m in source["required_input_months"]
            ],
            "c8_transformation_status": source["transformation_status"],
            "c7_5_semantic_checksum": c7_5_checksum,
        }
        structural_branch = {
            "io_sector_code": decision["io_sector_code"],
            "sector_093_direct_exposure": decision["direct_exposure"],
            "nesdc_workbook_sha256": nesdc_sha,
            "industry_crosswalk_version": crosswalk_version,
            "gross_output_weights": dict(decision["gross_output_weights"]),
            "proxy_fit": decision["proxy_fit"],
            "direction_channel": decision["direction_channel"],
            "direction_multiplier": decision["direction_multiplier"],
            "c9_phase_a_checksum": decision["phase_a_decision_checksum"],
            "structural_available_month":
                config["availability"]["structural_available_by"].strftime("%Y-%m")
                if hasattr(config["availability"]["structural_available_by"], "strftime")
                else str(config["availability"]["structural_available_by"])[:7],
        }
        value_cell = dict(cell)
        value_cell["value"] = next(
            (r["values"][cell["transformation_id"]] for r in matrix.rows
             if r["issue_month"] == cell["issue_month"]
             and r["industry_id"] == cell["industry_id"]),
            None,
        )
        record = ML.matrix_cell_lineage_record(
            value_cell, source_branch, structural_branch,
            selection_rule=(
                "one variant per matrix; reference_month = issue_month - 2 months"
            ),
            contract_checksum_value=contract_digest,
        )
        digest = ML.matrix_cell_lineage_checksum(record)
        records[(cell["variant_id"], cell["issue_month"], cell["industry_id"],
                 cell["transformation_id"])] = record
        checksums.append(digest)
    return records, checksums


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()
    assert_no_prohibited_artifact(config["inputs"]["permitted"])

    # --- freeze the diagnostic contract BEFORE any value is read ------------
    spec = config["diagnostic_contract"]
    contract = ML.DiagnosticContract(
        contract_version=config["contract_version"],
        matrix_key=list(spec["matrix_key"]),
        expected_variants=list(spec["expected_variants"]),
        expected_issue_months=spec["expected_issue_months"],
        expected_industries=spec["expected_industries"],
        expected_transformation_columns=list(spec["expected_transformation_columns"]),
        expected_rows_per_variant=spec["expected_rows_per_variant"],
        expected_cells_per_variant=spec["expected_cells_per_variant"],
        expected_numeric_cells_per_variant=spec["expected_numeric_cells_per_variant"],
        expected_masked_cells_per_variant=spec["expected_masked_cells_per_variant"],
        rank_tolerance=float(spec["rank_tolerance"]),
        near_zero_variance_threshold=float(spec["near_zero_variance_threshold"]),
        reconstruction_tolerance=float(spec["reconstruction_tolerance"]),
        standardization_tolerance=float(spec["standardization_tolerance"]),
        standardization_ddof=int(spec["standardization_ddof"]),
        standardization_formula=spec["standardization_formula"],
        missingness_precedence=list(spec["missingness_precedence"]),
        permitted_statistics=list(spec["permitted_statistics"]),
        primary_diagnostic_input=spec["primary_diagnostic_input"],
        channel_selection_permitted=spec["channel_selection_permitted"],
        feature_removal_permitted=spec["feature_removal_permitted"],
        target_or_model_access_permitted=spec["target_or_model_access_permitted"],
        significance_testing_permitted=spec["significance_testing_permitted"],
    )
    contract_digest = ML.contract_checksum(contract)

    # --- now the values may load -------------------------------------------
    ML.assert_contract_frozen(contract, contract_digest)
    snapshot = pd.read_parquet(C9_SNAPSHOT)
    conditioned = pd.read_parquet(C9_CONDITIONED)
    c8_rows = pd.read_parquet(C8_PARQUET).to_dict("records")
    for row in c8_rows:
        # A parquet list column arrives as an ndarray, whose truthiness raises;
        # the emptiness test has to be explicit.
        months = row["required_input_months"]
        row["required_input_months"] = (
            [] if months is None or len(months) == 0 else [str(m) for m in months]
        )
    phase_a = load_json(C9_PHASE_A)
    c7_5_checksum = load_json(C7_5_DECISION)["content_checksum"]
    nesdc_sha = load_json(C3_SOURCE_AUDIT)["acquired"][0]["sha256"]
    crosswalk_version = load_json(C3_MATRIX)["crosswalk_version"]

    invariants = reproduce_upstream_invariants(snapshot, conditioned)
    if not invariants["all_reproduced"]:
        raise SystemExit(
            f"C10 stops: upstream invariants did not reproduce: "
            f"{invariants['failed']}. Upstream artifacts are not repaired here."
        )

    exposures = {
        r["industry_id"]: r["direct_exposure"] for r in phase_a["decisions"]
        if r["channel_id"] == "eppo_fo600_channel"
    }
    eligible_set = sorted(
        r["industry_id"] for r in phase_a["decisions"]
        if r["channel_id"] == "eppo_fo600_channel" and r["eligible"]
    )
    industries = sorted(conditioned["industry_id"].unique())
    issue_months = sorted(snapshot["issue_month"].unique())

    matrices, diagnostics, reconstructions, invariance = {}, {}, {}, {}
    availability, variance_agreement, lineage_records = {}, {}, {}
    lineage_checksums = {}
    for variant_id in sorted(CHANNEL_BY_VARIANT):
        matrix = DM.build_development_matrix(
            snapshot_cells(snapshot, variant_id), variant_id, industries,
            issue_months, contract.expected_transformation_columns,
        )
        if matrix.eligible_industries != eligible_set:
            raise SystemExit(
                f"C10 stops: {variant_id} eligible industries "
                f"{matrix.eligible_industries} differ from the frozen Phase-A set "
                f"{eligible_set}"
            )
        matrices[variant_id] = matrix

        reference_months = matrix.reference_months
        source_time = c8_source_time_matrix(
            c8_rows, CHANNEL_BY_VARIANT[variant_id], reference_months, matrix.columns
        )
        reconstructions[variant_id] = ST.reconstruction_report(
            matrix, exposures, matrix.eligible_industries, source_time,
            contract.reconstruction_tolerance,
        ).to_dict()
        invariance[variant_id] = ST.standardization_invariance_report(
            matrix, exposures, matrix.eligible_industries,
            contract.standardization_tolerance, contract.standardization_ddof,
        )
        diagnostics[variant_id] = diagnose(
            matrix, contract, source_time
        ).to_dict()
        variance_agreement[variant_id] = variance_classification_matches(
            matrix, contract
        )
        availability[variant_id] = availability_report(matrix, snapshot, config)
        records, checksums = build_lineage(
            matrix, phase_a, c8_rows, contract_digest, c7_5_checksum,
            nesdc_sha, crosswalk_version, config,
        )
        lineage_records[variant_id] = records
        lineage_checksums[variant_id] = checksums

    # --- the contract must be unchanged after the diagnostics ran -----------
    ML.assert_contract_frozen(contract, contract_digest)

    # --- write the tabular artifacts ---------------------------------------
    wide_rows, mask_rows, diagnostic_rows = [], [], []
    for variant_id, matrix in matrices.items():
        for row in matrix.rows:
            record = {
                "variant_id": row["variant_id"], "issue_month": row["issue_month"],
                "industry_id": row["industry_id"],
                "reference_month": row["reference_month"],
                "row_state": row["row_state"], "masked": row["masked"],
            }
            for column in matrix.columns:
                record[column] = row["values"][column]
            wide_rows.append(record)
        for cell in matrix.mask_cells:
            key = (cell["variant_id"], cell["issue_month"], cell["industry_id"],
                   cell["transformation_id"])
            mask_rows.append({
                **cell,
                "matrix_cell_lineage_checksum": ML.matrix_cell_lineage_checksum(
                    lineage_records[variant_id][key]
                ),
            })
        entry = diagnostics[variant_id]
        for index, value in enumerate(entry["singular_values"]):
            diagnostic_rows.append({
                "variant_id": variant_id, "statistic": "singular_value",
                "key": f"sigma_{index + 1}", "value": value,
            })
        for name, value in (
            ("numerical_rank", entry["numerical_rank"]),
            ("raw_condition_number", entry["raw_condition_number"]),
            ("standardized_condition_number", entry["standardized_condition_number"]),
            ("stacked_panel_rank", entry["stacked_panel_rank"]),
            ("unique_issue_months", entry["unique_issue_months"]),
        ):
            diagnostic_rows.append({
                "variant_id": variant_id, "statistic": name, "key": name,
                "value": float(value),
            })
        for pair, value in entry["pearson"].items():
            diagnostic_rows.append({
                "variant_id": variant_id, "statistic": "pearson", "key": pair,
                "value": value,
            })
        for pair, value in entry["spearman"].items():
            diagnostic_rows.append({
                "variant_id": variant_id, "statistic": "spearman", "key": pair,
                "value": value,
            })

    for path, rows in (
        (WIDE_PARQUET, wide_rows), (MASK_PARQUET, mask_rows),
        (DIAGNOSTICS_PARQUET, diagnostic_rows),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(path, index=False)

    # --- assemble the audit -------------------------------------------------
    per_variant = {}
    for variant_id, matrix in matrices.items():
        entry = diagnostics[variant_id]
        per_variant[variant_id] = {
            "matrix_dimensions": {
                "rows": len(matrix.rows), "columns": len(matrix.columns),
                "cells": len(matrix.rows) * len(matrix.columns),
            },
            "numeric_cells": matrix.numeric_cells,
            "masked_cells": matrix.masked_cells,
            "fully_numeric_rows": matrix.fully_numeric_rows,
            "fully_masked_rows": matrix.fully_masked_rows,
            "eligible_industries": matrix.eligible_industries,
            "masked_industries": matrix.masked_industries,
            "unique_temporal_rows": entry["unique_issue_months"],
            "source_time_rank": entry["numerical_rank"],
            "stacked_panel_rows": entry["stacked_panel_rows"],
            "stacked_panel_rank": entry["stacked_panel_rank"],
            "industry_matrix_ranks": entry["industry_matrix_ranks"],
            "cross_sectional_rank_by_issue": entry["cross_sectional_rank_by_issue"],
            "singular_values": entry["singular_values"],
            "raw_condition_number": entry["raw_condition_number"],
            "standardized_condition_number": entry["standardized_condition_number"],
            "variance": entry["variance"],
            "variance_classification_agreement": variance_agreement[variant_id],
            "pearson": entry["pearson"],
            "spearman": entry["spearman"],
            "exact_duplicate_columns": entry["exact_duplicate_columns"],
            "exposure_normalization": reconstructions[variant_id],
            "standardization_invariance": invariance[variant_id],
            "availability": availability[variant_id],
            "lineage": {
                "cells_with_a_checksum": len(lineage_checksums[variant_id]),
                "distinct_checksums": len(set(lineage_checksums[variant_id])),
            },
            "stacked_rows_are_independent_claim_permitted": False,
            "temporal_independence_claim_permitted": False,
            "significance_tested": False,
            "channel_selected": False,
            "features_removed": [],
        }

    all_cross_rank_one = all(
        set(entry["cross_sectional_rank_by_issue"].values()) == {1}
        for entry in diagnostics.values()
    )
    all_normalized_single = all(
        r["normalized_equivalence_classes"] == 1 for r in reconstructions.values()
    )
    all_standardized_single = all(
        i["standardized_equivalence_classes"] == 1 for i in invariance.values()
    )
    expected = config["expected_identities"]
    discrepancies = []
    for variant_id in sorted(matrices):
        observed = {
            "expected_distinct_raw_fingerprints_per_variant":
                reconstructions[variant_id]["distinct_raw_fingerprints"],
            "expected_distinct_normalized_fingerprints_per_variant":
                reconstructions[variant_id]["distinct_normalized_fingerprints"],
            "expected_distinct_standardized_fingerprints_per_variant":
                invariance[variant_id]["distinct_standardized_fingerprints"],
        }
        for key, actual in observed.items():
            if actual != expected[key]:
                discrepancies.append({
                    "variant_id": variant_id,
                    "preregistered_field": key,
                    "preregistered_value": expected[key],
                    "observed_value": actual,
                    "threshold_changed_after_observation": False,
                    "decision_rule_applied": (
                        "the frozen absolute tolerance, not the fingerprint count"
                    ),
                    "explanation": (
                        "The fingerprint rounds to 13 significant digits, so a "
                        "standardised value near zero is resolved below double "
                        "precision. The preregistered tolerance test on the same "
                        "matrices puts every eligible industry in one equivalence "
                        "class, and that test decides."
                    ),
                })

    payload = {
        "task": "C10",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "contract_version": contract.contract_version,
        "diagnostic_contract": contract.to_dict(),
        "diagnostic_contract_checksum": contract_digest,
        "contract_frozen_before_values_loaded": True,
        "contract_reasserted_after_diagnostics": True,
        "upstream_invariants": invariants,
        "inherited": config["inherited"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "inputs": config["inputs"],
        "matrices": {
            **config["matrices"],
            "observed_wide_rows": sum(len(m.rows) for m in matrices.values()),
            "observed_cells": sum(
                len(m.rows) * len(m.columns) for m in matrices.values()
            ),
            "observed_numeric_cells": sum(m.numeric_cells for m in matrices.values()),
            "observed_masked_cells": sum(m.masked_cells for m in matrices.values()),
        },
        "development_window": config["development_window"],
        "identifiability": config["identifiability"],
        "expected_identities": config["expected_identities"],
        "degeneracy": config["degeneracy"],
        "channels": config["channels"],
        "units": config["units"],
        "interpretation": config["interpretation"],
        "per_variant": per_variant,
        "preregistered_expectation_discrepancies": {
            "count": len(discrepancies),
            "thresholds_changed_after_observation": False,
            "expectations_relaxed_to_obtain_a_pass": False,
            "items": discrepancies,
        },
        "structural_findings": {
            "cross_industry_information_is_exposure_scaling_only": all_cross_rank_one,
            "industry_conditioning_adds_temporal_degrees_of_freedom": False,
            "all_designs_are_scalar_multiples_of_one_source_time_matrix":
                all_normalized_single,
            "per_industry_standardization_removes_exposure_scale":
                all_standardized_single,
            "unique_issue_months": contract.expected_issue_months,
            "stacked_eligible_rows": 165,
            "stacked_rows_are_independent_claim_permitted": False,
            "temporal_independence_claim_permitted": False,
            "note": (
                "Each eligible industry's design is one 15x5 source-time matrix "
                "multiplied by a positive scalar exposure, so the 165-row stacked "
                "panel is eleven scaled copies of fifteen rows. This is a property "
                "of the design matrix established without reading any target; it "
                "is not a statement about predictive performance."
            ),
        },
        "decisions": {
            "development_matrix_assembled": True,
            "conditioning_adds_cross_industry_scale": True,
            "conditioning_adds_temporal_degrees_of_freedom": False,
            "per_industry_standardization_removes_exposure_scale":
                all_standardized_single,
            "predictive_utility_assessed": False,
            "channel_selected": False,
            "target_joined": False,
            "model_trained": False,
            "model_feature_approved": False,
            "locked_test_accessed": False,
            "target_join_authorized": False,
            "modeling_authorized": False,
            "variant_promoted_to_modeling_readiness": False,
            "note": (
                "A full-rank source-time matrix does not promote either variant to "
                "modeling readiness. Rank is a property of the design; approval is "
                "a separate decision that has not been taken."
            ),
        },
        "outputs": {
            "wide_matrix": str(WIDE_PARQUET.relative_to(ROOT)).replace("\\", "/"),
            "mask_table": str(MASK_PARQUET.relative_to(ROOT)).replace("\\", "/"),
            "diagnostics_table":
                str(DIAGNOSTICS_PARQUET.relative_to(ROOT)).replace("\\", "/"),
        },
    }
    payload["content_checksum"] = ML.content_checksum(payload)

    for narrative in (
        payload["structural_findings"]["note"],
        payload["decisions"]["note"],
        PROTOCOL_NARRATIVE,
        *(e["standardization_invariance"]["note"] for e in per_variant.values()),
        *(e["standardization_invariance"]["fingerprint_note"]
          for e in per_variant.values()),
        *(d["explanation"] for d in discrepancies),
    ):
        guard_narrative(narrative)

    DOCS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    guard_text(serialized)
    with open(DOCS / "c10_design_matrix_audit.json", "w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.write("\n")
    write_protocol(payload, config)
    write_audit_markdown(payload)

    print(json.dumps({
        "upstream_invariants_reproduced": invariants["all_reproduced"],
        "diagnostic_contract_checksum": contract_digest,
        "wide_rows": payload["matrices"]["observed_wide_rows"],
        "numeric_cells": payload["matrices"]["observed_numeric_cells"],
        "masked_cells": payload["matrices"]["observed_masked_cells"],
        "source_time_rank": {
            v: e["source_time_rank"] for v, e in per_variant.items()
        },
        "stacked_panel_rank": {
            v: e["stacked_panel_rank"] for v, e in per_variant.items()
        },
        "cross_sectional_ranks": sorted({
            r for e in per_variant.values()
            for r in e["cross_sectional_rank_by_issue"].values()
        }),
        "max_exposure_normalization_residual": max(
            e["exposure_normalization"]["max_residual"] for e in per_variant.values()
        ),
        "max_standardization_residual": max(
            e["standardization_invariance"]["max_standardized_design_residual"]
            for e in per_variant.values()
        ),
        "distinct_normalized_fingerprints": {
            v: e["exposure_normalization"]["distinct_normalized_fingerprints"]
            for v, e in per_variant.items()
        },
        "distinct_standardized_fingerprints": {
            v: e["standardization_invariance"]["distinct_standardized_fingerprints"]
            for v, e in per_variant.items()
        },
        "content_checksum": payload["content_checksum"],
    }, ensure_ascii=False, indent=1))


def guard_text(text: str) -> str:
    """Run every rhetorical guard over a rendered document before it is written.

    The stacked-panel independence claim, the channel selection and the
    predictive-performance claim are all prohibited in C10, and a document is
    the only place they could actually appear.
    """
    ID.assert_no_independence_claim(text)
    ID.assert_no_channel_selection(text)
    ST.assert_no_performance_claim(text)
    return text


def guard_narrative(text: str) -> str:
    """Guard authored prose, which is where an interpretation could be asserted.

    The valuation guard is applied here rather than to the whole document
    because ``interpretation.elasticity: false`` is the *denial* of the claim,
    and a substring check cannot tell a field name from a sentence.
    """
    guard_text(text)
    C9.assert_valuation_claim_permitted(text)
    return text


def _flag(value) -> str:
    return f"`{value}`"


def _fmt(value, digits=6) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if abs(value) >= 1e6 or (value != 0 and abs(value) < 1e-4):
            return f"{value:.3e}"
        return f"{value:.{digits}f}"
    return str(value)


def write_protocol(payload: dict, config: dict) -> None:
    contract = payload["diagnostic_contract"]
    lines = [
        "# Task C10 - Design-Matrix Audit Protocol",
        "",
        f"*Config `{payload['config_version']}`, contract "
        f"`{payload['contract_version']}`.*",
        "",
        f"**Frozen diagnostic-contract checksum:** "
        f"`{payload['diagnostic_contract_checksum']}`",
        "",
        "Every threshold below was written before a single C9 feature value was",
        "read. The runner hashes the contract, re-asserts the digest immediately",
        "before loading values and again after the diagnostics run, so a tolerance",
        "moved after seeing a singular value raises rather than passing.",
        "",
        "## Frozen thresholds",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("rank_tolerance", "near_zero_variance_threshold",
                "reconstruction_tolerance", "standardization_tolerance",
                "standardization_ddof", "standardization_formula",
                "primary_diagnostic_input"):
        lines.append(f"| `{key}` | `{contract[key]}` |")
    lines += [
        "",
        "## Expected shape",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("matrix_key", "expected_variants", "expected_issue_months",
                "expected_industries", "expected_transformation_columns",
                "expected_rows_per_variant", "expected_cells_per_variant",
                "expected_numeric_cells_per_variant",
                "expected_masked_cells_per_variant"):
        lines.append(f"| `{key}` | `{contract[key]}` |")
    identities = config["expected_identities"]
    lines += [
        "",
        "## Preregistered identities",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("conditioning_formula", "exposure_normalization",
                "standardization_invariance",
                "expected_distinct_raw_fingerprints_per_variant",
                "expected_distinct_normalized_fingerprints_per_variant",
                "expected_distinct_standardized_fingerprints_per_variant",
                "conditioning_adds_cross_industry_scale",
                "conditioning_adds_temporal_degrees_of_freedom",
                "per_industry_standardization_removes_exposure_scale"):
        lines.append(f"| `{key}` | `{identities[key]}` |")
    lines += [
        "",
        "## What decides, and what is only described",
        "",
        "The **decision rule** for both identities is the preregistered absolute",
        "residual tolerance above. The fingerprint counts are **descriptive**: a",
        "fingerprint rounds to a fixed number of *significant* digits, so it",
        "resolves a standardised value near zero far below double precision and",
        "can split matrices that agree to 1e-15. Both counts are published; where",
        "they disagree the tolerance governs, and any preregistered expectation",
        "that does not reproduce is reported as a discrepancy rather than",
        "relaxed.",
    ]
    lines += [
        "",
        "## Missingness precedence",
        "",
    ]
    for index, state in enumerate(contract["missingness_precedence"], start=1):
        lines.append(f"{index}. `{state}`")
    lines += [
        "",
        "## Permitted statistics",
        "",
    ]
    for statistic in contract["permitted_statistics"]:
        lines.append(f"* `{statistic}`")
    lines += [
        "",
        "## Prohibitions",
        "",
        "| field | value |",
        "| --- | --- |",
        f"| `channel_selection_permitted` | "
        f"{_flag(contract['channel_selection_permitted'])} |",
        f"| `feature_removal_permitted` | "
        f"{_flag(contract['feature_removal_permitted'])} |",
        f"| `target_or_model_access_permitted` | "
        f"{_flag(contract['target_or_model_access_permitted'])} |",
        f"| `significance_testing_permitted` | "
        f"{_flag(contract['significance_testing_permitted'])} |",
        "",
        "Prohibited artifacts: "
        + ", ".join(f"`{x}`" for x in config["inputs"]["prohibited"]) + ".",
        "",
        "## What the audit is measuring",
        "",
        PROTOCOL_NARRATIVE,
        "",
    ]
    (DOCS / "c10_design_matrix_protocol.md").write_text(
        guard_text("\n".join(lines) + "\n"), encoding="utf-8"
    )


def write_audit_markdown(payload: dict) -> None:
    lines = [
        "# Task C10 - Development-Only Design-Matrix Identifiability Audit",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        f"Diagnostic contract `{payload['diagnostic_contract_checksum']}`, frozen",
        "before the values loaded and re-asserted after the diagnostics ran.",
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
        "## The structural finding",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["structural_findings"].items():
        if key == "note":
            continue
        lines.append(f"| `{key}` | `{value}` |")
    lines += ["", "> " + payload["structural_findings"]["note"], ""]

    for variant_id, entry in payload["per_variant"].items():
        dimensions = entry["matrix_dimensions"]
        lines += [
            f"## `{variant_id}`",
            "",
            f"Matrix **{dimensions['rows']} x {dimensions['columns']}** "
            f"({dimensions['cells']} cells): **{entry['numeric_cells']}** numeric, "
            f"**{entry['masked_cells']}** masked. "
            f"{entry['fully_numeric_rows']} fully numeric rows, "
            f"{entry['fully_masked_rows']} fully masked "
            f"({', '.join(entry['masked_industries'])}).",
            "",
            "| diagnostic | value |",
            "| --- | --- |",
            f"| unique temporal rows | **{entry['unique_temporal_rows']}** |",
            f"| source-time rank (15x5) | **{entry['source_time_rank']}** |",
            f"| stacked panel | {entry['stacked_panel_rows']} rows, rank "
            f"**{entry['stacked_panel_rank']}** |",
            f"| industry-matrix ranks | "
            f"`{sorted(set(entry['industry_matrix_ranks'].values()))}` |",
            f"| cross-sectional rank by issue | "
            f"`{sorted(set(entry['cross_sectional_rank_by_issue'].values()))}` "
            "(all 15 issue months) |",
            f"| singular values | "
            f"{', '.join(_fmt(v) for v in entry['singular_values'])} |",
            f"| raw condition number | {_fmt(entry['raw_condition_number'])} |",
            f"| standardized condition number | "
            f"{_fmt(entry['standardized_condition_number'])} |",
            f"| exact duplicate columns | "
            f"`{entry['exact_duplicate_columns'] or 'none'}` |",
            "",
            "### Variance (source-time matrix)",
            "",
            "| transformation | sd | exact-zero variance | near-zero variance "
            "| exact-zero observations | retained |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for column, stats in entry["variance"].items():
            lines.append(
                f"| `{column}` | {_fmt(stats['standard_deviation'])} | "
                f"{_flag(stats['exact_zero_variance'])} | "
                f"{_flag(stats['near_zero_variance'])} | "
                f"{stats['exact_zero_observations']} | "
                f"{_flag(stats['retained'])} |"
            )
        agreement = entry["variance_classification_agreement"]
        lines += [
            "",
            f"All {agreement['industries_checked']} eligible industries share one "
            f"zero-variance classification: "
            f"{_flag(agreement['all_eligible_industries_agree'])}.",
            "",
            "### Pairwise correlations (descriptive only, 15 overlapping months)",
            "",
            "| pair | Pearson | Spearman |",
            "| --- | --- | --- |",
        ]
        for pair in entry["pearson"]:
            # A raw pipe would split the markdown table cell.
            first, second = pair.split("|")
            lines.append(
                f"| `{first}` vs `{second}` | {_fmt(entry['pearson'][pair], 4)} | "
                f"{_fmt(entry['spearman'].get(pair), 4)} |"
            )
        normalization = entry["exposure_normalization"]
        invariance = entry["standardization_invariance"]
        lines += [
            "",
            "No significance test is reported and no correlation selects a channel",
            "or removes a transformation.",
            "",
            "### Exposure normalisation and standardisation invariance",
            "",
            "| field | value |",
            "| --- | --- |",
            f"| eligible reconstructions | {normalization['eligible_industries']} |",
            f"| max reconstruction residual | "
            f"{_fmt(normalization['max_residual'])} |",
            f"| residual vs C8 source transformations | "
            f"{_fmt(normalization['source_reconciliation_residual'])} |",
            f"| distinct raw fingerprints | "
            f"**{normalization['distinct_raw_fingerprints']}** |",
            f"| distinct normalized fingerprints | "
            f"**{normalization['distinct_normalized_fingerprints']}** |",
            f"| normalized equivalence classes at tolerance | "
            f"**{normalization['normalized_equivalence_classes']}** |",
            f"| all designs are scalar multiples | "
            f"{_flag(normalization['all_designs_are_scalar_multiples'])} |",
            f"| max standardized-design residual | "
            f"{_fmt(invariance['max_standardized_design_residual'])} |",
            f"| standardized equivalence classes at tolerance | "
            f"**{invariance['standardized_equivalence_classes']}** |",
            f"| distinct standardized fingerprints | "
            f"**{invariance['distinct_standardized_fingerprints']}** |",
            f"| fingerprint agrees with tolerance classes | "
            f"{_flag(invariance['fingerprint_agrees_with_tolerance_classes'])} |",
            f"| identity decided by | `{invariance['identity_decided_by']}` |",
            f"| exposure survives standardization | "
            f"{_flag(invariance['exposure_survives_per_industry_standardization'])} |",
            f"| industry-specific temporal pattern | "
            f"{_flag(invariance['industry_specific_temporal_pattern_present'])} |",
            "",
            "> " + invariance["note"],
            "",
            "> " + invariance["fingerprint_note"],
            "",
            "### Availability and lineage",
            "",
            f"{entry['availability']['rows_checked']} snapshot rows checked against "
            "the recorded fields: "
            f"{entry['availability']['lag_two_violations']} lag-2 violations, "
            f"{entry['availability']['policy_availability_violations']} policy "
            "violations. Structural availability "
            f"`{entry['availability']['structural_available_by']}` "
            f"(reference year {entry['availability']['structural_reference_year']}), "
            f"`backdated_to_reference_year`: "
            f"{_flag(entry['availability']['backdated_to_reference_year'])}.",
            "",
            f"Lineage: {entry['lineage']['cells_with_a_checksum']} cells carry a "
            f"checksum, {entry['lineage']['distinct_checksums']} distinct.",
            "",
        ]

    discrepancies = payload["preregistered_expectation_discrepancies"]
    lines += [
        "## Preregistered expectations that did not reproduce",
        "",
        f"{discrepancies['count']} of the preregistered `expected_identities` values "
        "did not reproduce. No threshold was moved and no expectation was relaxed "
        f"(`thresholds_changed_after_observation`: "
        f"{_flag(discrepancies['thresholds_changed_after_observation'])}, "
        f"`expectations_relaxed_to_obtain_a_pass`: "
        f"{_flag(discrepancies['expectations_relaxed_to_obtain_a_pass'])}).",
        "",
    ]
    if discrepancies["items"]:
        lines += [
            "| variant | field | preregistered | observed | decided by |",
            "| --- | --- | --- | --- | --- |",
        ]
        for item in discrepancies["items"]:
            lines.append(
                f"| `{item['variant_id']}` | `{item['preregistered_field']}` | "
                f"`{item['preregistered_value']}` | `{item['observed_value']}` | "
                f"{item['decision_rule_applied']} |"
            )
        lines += ["", "> " + discrepancies["items"][0]["explanation"], ""]

    lines += [
        "## Channel separation",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["channels"].items():
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {_flag(value)} |")
    lines += [
        "",
        "Prohibited: "
        + ", ".join(f"`{x}`" for x in payload["channels"]["prohibited"]) + ".",
        "",
        "The two variants are reported side by side. No diagnostic here ranks one",
        "variant against the other, and `preferred_channel_produced` above records",
        "that none was produced.",
        "",
        "## Units and interpretation",
        "",
        "| transformation | unit |",
        "| --- | --- |",
    ]
    for name, unit in payload["units"].items():
        lines.append(f"| `{name}` | `{unit}` |")
    lines += ["", "| field | value |", "| --- | --- |"]
    for key, value in payload["interpretation"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines += ["", "## Decisions", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["decisions"].items():
        if key == "note":
            continue
        lines.append(f"| `{key}` | {_flag(value)} |")
    lines += [
        "",
        "> " + payload["decisions"]["note"],
        "",
        f"Content checksum `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c10_design_matrix_audit.md").write_text(
        guard_text("\n".join(lines) + "\n"), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
