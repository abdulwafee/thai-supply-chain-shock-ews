"""Task C3 — build the commodity–industry structural exposure matrix.

Takes no arguments, for the same reason the B4 and C2 runners take none: there
is no flag that can widen the commodity allowlist, normalize the exposures,
swap the structural reference year, or reach a target.

All computation lives in the package. This file orchestrates and reports.

    python scripts/audit_c3_io_sources.py     # first: acquire the sources
    python scripts/run_c3_industry_exposure.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import yaml  # noqa: E402

from thai_supply_chain_ews.data import nesdc_input_output as IO  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import taxonomy as TX  # noqa: E402
from thai_supply_chain_ews.matrices import commodity_exposure as CE  # noqa: E402
from thai_supply_chain_ews.matrices import industry_crosswalk as XW  # noqa: E402
from thai_supply_chain_ews.matrices import io_coefficients as CO  # noqa: E402
from thai_supply_chain_ews.matrices import proxy_fitness as PF  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "industry_exposure.yaml"
SOURCE_AUDIT = PROJECT_ROOT / "docs" / "c3_io_source_audit.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "NESDC_IO"
OUT_JSON = PROJECT_ROOT / "docs" / "c3_commodity_exposure_matrix.json"
FEATURE_DIR = PROJECT_ROOT / "data" / "features"


def content_checksum(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=== C3 - commodity-industry structural exposure matrix ===")

    if not SOURCE_AUDIT.is_file():
        raise SystemExit(
            "C3 FAILED: run scripts/audit_c3_io_sources.py first — the official "
            "sources must be discovered and checksummed before they are used."
        )
    source_audit = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    by_role = {record["role"]: record for record in source_audit["acquired"]}

    # --- 1. reproduce the production industry dimension EXACTLY --------------
    taxonomy = TX.load_taxonomy()
    industries = [taxonomy.industries[key] for key in taxonomy.industry_ids]
    if len(industries) != 12:
        raise SystemExit(
            f"C3 FAILED: production taxonomy has {len(industries)} industries, "
            "expected 12. C3 stops rather than inventing a dimension."
        )
    ids = [industry.industry_id for industry in industries]
    if len(set(ids)) != 12:
        raise SystemExit(f"C3 FAILED: duplicate industry ids in {ids}.")
    print(f"production industries    : {len(industries)} ({ids[0]}..{ids[-1]})")

    # --- 2. verify the raw files still match their recorded checksums --------
    for role, record in by_role.items():
        path = PROJECT_ROOT / record["local_path"]
        if not path.is_file():
            raise SystemExit(f"C3 FAILED: {role} missing at {path}.")
        actual = SM.sha256_of_file(path)
        if actual != record["sha256"]:
            raise SystemExit(
                f"C3 FAILED: {role} checksum {actual[:16]} != recorded "
                f"{record['sha256'][:16]}."
            )
    print(f"raw source checksums     : {len(by_role)} verified")

    # --- 3. parse, build A and L --------------------------------------------
    primary = by_role["primary_io_table"]
    table = IO.parse_io_workbook(
        PROJECT_ROOT / primary["local_path"], "2015", primary["final_url"],
        primary["sha256"],
    )
    definitions = IO.parse_sector_definitions(
        PROJECT_ROOT / by_role["sector_classification_and_definitions"]["local_path"]
    )
    codes, a, coefficient_diagnostics = CO.build_technical_coefficients(table)
    matrices = CO.leontief_inverse(codes, a, coefficient_diagnostics)
    print(f"A matrix                 : {a.shape[0]}x{a.shape[1]} "
          f"(excluded {coefficient_diagnostics['sectors_excluded_zero_output']})")
    print(f"column sums              : "
          f"{coefficient_diagnostics['column_sum_min']:.4f} .. "
          f"{coefficient_diagnostics['column_sum_max']:.4f}")
    print(f"condition number         : {matrices.diagnostics['condition_number']:.4g}")
    print(f"Leontief residual        : "
          f"{matrices.diagnostics['reconstruction_residual_max_abs']:.3e}")

    # --- 4. crosswalks and the canonical table -------------------------------
    crosswalks = XW.load_industry_crosswalk(config, taxonomy, definitions)
    print(f"industry crosswalks      : {len(crosswalks)} "
          f"({sum(len(c.io_sector_codes) for c in crosswalks)} I/O sectors mapped)")

    rows = CE.build_exposure_table(table, matrices, crosswalks, config, definitions)
    print(f"canonical rows           : {len(rows)} (12 industries x 4 commodities)")

    # --- 4b. C3-R1 proxy-fitness gate ----------------------------------------
    # Adds fields only. Numeric exposures are never touched: an ineligible pair
    # keeps its coefficient, because eligibility is a usage decision and
    # deleting the number would make "unsuitable" look like "no exposure".
    rows = PF.apply_proxy_gate(rows, table, crosswalks, definitions, config)
    fit_counts: dict[str, int] = {}
    for row in rows:
        key = row["commodity_proxy_fit_status"]
        fit_counts[key] = fit_counts.get(key, 0) + 1
    eligible = [r for r in rows if r["industry_pair_feature_eligible"]]
    print(f"proxy fitness            : {fit_counts}")
    print(f"feature-eligible pairs   : {len(eligible)} / {len(rows)}")

    # --- 5. descriptive summary ONLY -----------------------------------------
    resolved = [r for r in rows if r["direct_exposure"] is not None]
    direct = [r["direct_exposure"] for r in resolved]
    indirect = [r["indirect_exposure"] for r in resolved]
    total = [r["total_requirement_exposure"] for r in resolved]
    observed_zero = [r for r in resolved if r["direct_exposure"] == 0.0]
    unresolved = [r for r in rows if r["direct_exposure"] is None]

    confidence_counts: dict[str, int] = {}
    for row in rows:
        confidence_counts[row["mapping_confidence"]] = (
            confidence_counts.get(row["mapping_confidence"], 0) + 1
        )
    channel_counts: dict[str, int] = {}
    for row in rows:
        channel_counts[row["direction_channel"]] = (
            channel_counts.get(row["direction_channel"], 0) + 1
        )

    largest = sorted(resolved, key=lambda r: r["total_requirement_exposure"], reverse=True)[:10]
    print(f"resolved / unresolved    : {len(resolved)} / {len(unresolved)}")
    print(f"observed zeros           : {len(observed_zero)}")
    print(f"confidence               : {confidence_counts}")
    print(f"direction channels       : {channel_counts}")
    print("largest total exposures  :")
    for row in largest[:5]:
        print(f"   {row['industry_id']} x {row['commodity_series_id']:<22} "
              f"direct={row['direct_exposure']:.6f} total={row['total_requirement_exposure']:.6f}")

    # --- 6. git-ignored parquet, derived from the canonical rows -------------
    import pandas as pd

    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = FEATURE_DIR / "c3_commodity_exposure.parquet"
    pd.DataFrame(rows).to_parquet(parquet_path, index=False)

    output = {
        "task": "C3",
        "crosswalk_version": config["crosswalk_version"],
        "generated_at": generated_at,
        "structural_reference_year": str(config["io_source"]["structural_reference_year"]),
        "time_invariant_assumption": True,
        "io_source": {
            "table": config["io_source"]["table"],
            "sha256": table.sha256,
            "final_url": primary["final_url"],
            "sector_count": IO.SECTOR_CODE_COUNT,
            "valuation": table.diagnostics["valuation"],
        },
        "industry_dimension": [
            {
                "industry_id": industry.industry_id,
                "name_en": industry.name_en,
                "name_th": industry.name_th,
                "tsic_divisions": list(industry.tsic_divisions),
            }
            for industry in industries
        ],
        "io_accounting": {
            key: table.diagnostics[key]
            for key in (
                "sheet_name", "data_cells", "duplicate_cell_keys",
                "gross_output_equals_total_input_row",
                "max_column_identity_residual",
                "zero_or_negative_gross_output_sectors",
                "gross_output_total", "value_added_total", "intermediate_total",
                "import_content_total", "sector_codes_absent_entirely",
            )
        },
        "coefficients": {
            key: matrices.diagnostics[key]
            for key in (
                "measure", "sectors_used", "sectors_excluded_zero_output",
                "column_sum_min", "column_sum_max", "column_sum_mean",
                "columns_with_sum_ge_1", "negative_coefficient_count",
                "observed_zero_coefficients", "matrix_size", "condition_number",
                "reconstruction_residual_max_abs", "reconstruction_tolerance",
                "identity_term_removed", "total_requirement_negative_cells",
                "total_requirement_min", "total_requirement_max",
                "interpretation",
            )
        },
        "commodity_crosswalk": {
            commodity_id: {
                "io_sector_code": entry["io_sector_code"],
                "io_sector_label": definitions[str(entry["io_sector_code"])]["label"],
                "io_sector_definition": definitions[str(entry["io_sector_code"])][
                    "definition"
                ],
                "mapping_type": entry["mapping_type"],
                "confidence": entry["confidence"],
                "broader_than_commodity": entry.get("broader_than_commodity", False),
                "scope_difference": entry.get("scope_difference", ""),
                "shared_io_source_sector": entry.get("shared_io_source_sector", False),
                "shares_sector_with": entry.get("shares_sector_with", []),
            }
            for commodity_id, entry in sorted(config["commodity_crosswalk"].items())
        },
        "industry_crosswalk": [
            {
                "industry_id": crosswalk.industry_id,
                "industry_name": crosswalk.industry_name,
                "tsic_divisions": list(crosswalk.tsic_divisions),
                "io_sector_codes": list(crosswalk.io_sector_codes),
                "io_sector_labels": list(crosswalk.io_sector_labels),
                "mapping_relationship": crosswalk.mapping_relationship,
                "confidence": crosswalk.confidence,
                "scope_note": crosswalk.scope_note,
                "aggregation_weight_source": config[
                    "industry_crosswalk_aggregation"
                ]["weight_source"],
                "output_weights": XW.output_weights(crosswalk, table.gross_output),
            }
            for crosswalk in crosswalks
        ],
        "canonical_rows": rows,
        "summary": {
            "rows": len(rows),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "observed_zero_direct": len(observed_zero),
            "direct_min": min(direct) if direct else None,
            "direct_max": max(direct) if direct else None,
            "indirect_min": min(indirect) if indirect else None,
            "indirect_max": max(indirect) if indirect else None,
            "total_min": min(total) if total else None,
            "total_max": max(total) if total else None,
            "mapping_confidence_counts": confidence_counts,
            "direction_channel_counts": channel_counts,
            "shared_sector_rows": sum(1 for r in rows if r["shared_io_source_sector"]),
            "largest_total_exposures": [
                {
                    "industry_id": r["industry_id"],
                    "commodity_series_id": r["commodity_series_id"],
                    "direct_exposure": r["direct_exposure"],
                    "indirect_exposure": r["indirect_exposure"],
                    "total_requirement_exposure": r["total_requirement_exposure"],
                }
                for r in largest
            ],
        },
        "proxy_fitness_gate": {
            "statuses": list(PF.PROXY_FIT_STATUSES),
            "fit_status_counts": fit_counts,
            "feature_eligible_pairs": len(eligible),
            "feature_ineligible_pairs": len(rows) - len(eligible),
            "ineligible_pairs": [
                {
                    "industry_id": r["industry_id"],
                    "commodity_series_id": r["commodity_series_id"],
                    "commodity_proxy_fit_status": r["commodity_proxy_fit_status"],
                    "direction_channel": r["direction_channel"],
                    "direct_exposure": r["direct_exposure"],
                    "feature_eligibility_reason": r["feature_eligibility_reason"],
                }
                for r in rows if not r["industry_pair_feature_eligible"]
            ],
            "coefficients_preserved_for_ineligible_pairs": all(
                r["direct_exposure"] is not None
                for r in rows
                if not r["industry_pair_feature_eligible"]
                and r["quantitative_coefficient_status"] == "resolved"
            ),
            "determined_from_target_information": False,
        },
        "c4_policy": config["c4_policy"],
        "normalization_across_commodities": "none",
        "matrix_variants": config["matrix_variants"],
        "outputs": {
            "parquet": str(parquet_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "parquet_sha256": hashlib.sha256(parquet_path.read_bytes()).hexdigest(),
        },
        "content_checksum": content_checksum(rows),
        # Scope guards, recorded so the claim is auditable.
        "joined_to_mpi_targets": False,
        "target_association_computed": False,
        "exposure_weights_tuned_on_outcomes": False,
        "predictive_interactions_created": False,
        "model_trained": False,
        "b4_baselines_compared": False,
        "locked_test_accessed": False,
        "industry_conditioned_feature_matrix_created": False,
        "model_feature_approved_set": False,
    }
    OUT_JSON.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"content checksum         : {output['content_checksum'][:16]}")
    print(f"written                  : {OUT_JSON.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
