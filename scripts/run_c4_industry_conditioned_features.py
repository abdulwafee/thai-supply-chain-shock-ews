"""Task C4 — build the industry-conditioned commodity feature matrix.

Takes no arguments, for the same reason the B4, C2 and C3 runners take none:
no flag can widen the pair allowlist, promote a sensitivity variant, backdate
the I/O structure, or reach a target.

All computation lives in the package.

    python scripts/run_c4_industry_conditioned_features.py
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

from thai_supply_chain_ews.features import commodity_features as CF  # noqa: E402
from thai_supply_chain_ews.features import feature_snapshots as FS  # noqa: E402
from thai_supply_chain_ews.features import industry_conditioning as IC  # noqa: E402
from thai_supply_chain_ews.features.conditioned_availability import (  # noqa: E402
    StructuralAvailability,
)
from thai_supply_chain_ews.features.feature_availability import (  # noqa: E402
    PRIMARY_POLICY,
    SENSITIVITY_POLICY,
)

CONFIG_PATH = PROJECT_ROOT / "configs" / "industry_conditioned_features.yaml"
C1_5_AUDIT = PROJECT_ROOT / "docs" / "c1_5_commodity_timing_audit.json"
C3_MATRIX = PROJECT_ROOT / "docs" / "c3_commodity_exposure_matrix.json"
OUT_JSON = PROJECT_ROOT / "docs" / "c4_industry_conditioned_feature_audit.json"
FEATURE_DIR = PROJECT_ROOT / "data" / "features"


def content_checksum(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=== C4 - industry-conditioned commodity feature matrix ===")

    # --- 1. reproduce C2, and CHECK its invariants ---------------------------
    expected = config["inputs"]["c2"]
    loaded = CF.load_first_release_observations(C1_5_AUDIT)
    c2_rows = {
        PRIMARY_POLICY.name: CF.build_feature_table(
            loaded["observations"], loaded["required_months"], PRIMARY_POLICY
        ),
        SENSITIVITY_POLICY.name: CF.build_feature_table(
            loaded["observations"], loaded["required_months"], SENSITIVITY_POLICY
        ),
    }
    problems = []
    for policy, rows in c2_rows.items():
        if len(rows) != expected["rows_per_availability_policy"]:
            problems.append(f"{policy}: {len(rows)} rows")
    primary_rows = c2_rows[PRIMARY_POLICY.name]
    series = sorted({row["series_id"] for row in primary_rows})
    features = sorted({row["feature_name"] for row in primary_rows})
    if len(series) != expected["commodity_series"]:
        problems.append(f"{len(series)} commodity series")
    if len(features) != expected["base_feature_definitions"]:
        problems.append(f"{len(features)} base features")
    for name in series:
        count = sum(1 for row in primary_rows if row["series_id"] == name)
        if count != expected["observations_per_series"]:
            problems.append(f"{name}: {count} observations")
    if {row["source_value_type"] for row in primary_rows} != {"archived_first_release"}:
        problems.append("C2 values are not all archived first releases")
    if problems:
        raise SystemExit(f"C4 FAILED: C2 invariants violated: {problems}")
    print(f"C2 invariants            : {len(series)} series x {len(features)} features"
          f" x {expected['observations_per_series']} obs = "
          f"{len(primary_rows)} rows per policy")

    # --- 2. reproduce C3-R1, and CHECK its invariants ------------------------
    c3 = json.loads(C3_MATRIX.read_text(encoding="utf-8"))
    exposure_rows = c3["canonical_rows"]
    expected3 = config["inputs"]["c3"]
    eligible = [r for r in exposure_rows if r["industry_pair_feature_eligible"]]
    ineligible = [r for r in exposure_rows if not r["industry_pair_feature_eligible"]]
    checks = {
        "pairs": (len(exposure_rows), expected3["pairs"]),
        "industries": (len({r["industry_id"] for r in exposure_rows}),
                       expected3["industries"]),
        "commodities": (len({r["commodity_series_id"] for r in exposure_rows}),
                        expected3["commodities"]),
        "eligible": (len(eligible), expected3["eligible_pairs"]),
        "ineligible": (len(ineligible), expected3["ineligible_pairs"]),
        "shared_rows": (sum(1 for r in exposure_rows if r["shared_io_source_sector"]),
                        expected3["shared_sector_rows"]),
        "direction_ambiguous": (
            sum(1 for r in exposure_rows
                if r["direction_channel"] == "mixed_or_ambiguous"),
            expected3["direction_ambiguous_pairs"],
        ),
        "proxy_ineligible": (
            sum(1 for r in exposure_rows
                if r["commodity_proxy_fit_status"]
                == "not_fit_for_commodity_specific_use"),
            expected3["proxy_ineligible_pairs"],
        ),
    }
    mismatched = {k: v for k, v in checks.items() if v[0] != v[1]}
    if mismatched:
        raise SystemExit(f"C4 FAILED: C3-R1 invariants violated: {mismatched}")
    print(f"C3-R1 invariants         : {len(exposure_rows)} pairs, "
          f"{len(eligible)} eligible, {len(ineligible)} excluded")

    # --- 3. structural availability -----------------------------------------
    spec = config["structural_availability"]
    availability = StructuralAvailability(
        structural_reference_year=str(spec["structural_reference_year"]),
        structural_available_by=str(spec["structural_available_by"]),
        evidence_type=spec["evidence_type"],
        evidence_url=spec["evidence_url"],
        document_date=str(spec["document_date"]),
        publication_date=str(spec["publication_date"]),
        evidence_checksum=c3["io_source"]["sha256"],
        status=spec["status"],
        byte_identity_verified_at_that_date=spec[
            "byte_identity_verified_at_that_date"
        ],
        notes=spec["byte_identity_caveat"],
    )
    availability.assert_supports_primary(str(spec["first_development_origin"]))
    print(f"structural availability  : {availability.structural_available_by} "
          f"({availability.status}); reference year "
          f"{availability.structural_reference_year} is NOT the publication date")

    # --- 4. the canonical matrix --------------------------------------------
    rows = IC.build_conditioned_matrix(
        c2_rows, exposure_rows, availability, c3["io_source"]["sha256"]
    )
    per_variant = {
        variant.name: sum(1 for r in rows if r["matrix_variant"] == variant.name)
        for variant in IC.MATRIX_VARIANTS
    }
    if len(rows) != config["expected_counts"]["combined_canonical_rows"]:
        raise SystemExit(
            f"C4 FAILED: {len(rows)} canonical rows, expected "
            f"{config['expected_counts']['combined_canonical_rows']}."
        )
    print(f"canonical rows           : {len(rows)} = {per_variant}")

    # --- 5. independent lineage re-derivation --------------------------------
    from thai_supply_chain_ews.features.conditioned_lineage import (
        TRANSFORMATION_VERSION,
        ConditionedLineageInput,
        conditioned_lineage_checksum,
    )

    verified = 0
    for row in rows:
        expected_checksum = conditioned_lineage_checksum(
            ConditionedLineageInput(
                c2_lineage_checksum=row["c2_lineage_checksum"],
                industry_id=row["industry_id"],
                commodity_series_id=row["commodity_series_id"],
                c3_exposure_checksum=row["c3_exposure_checksum"],
                exposure_value=row["exposure_value"],
                direction_sign=row["price_increase_to_stress_sign"],
                proxy_fit_status=row["proxy_fit_status"],
                eligibility_status=True,
                matrix_variant=row["matrix_variant"],
                transformation_version=TRANSFORMATION_VERSION,
                structural_source_checksum=c3["io_source"]["sha256"],
            )
        )
        if expected_checksum != row["conditioned_lineage_checksum"]:
            raise SystemExit("C4 FAILED: lineage checksum mismatch.")
        verified += 1
    print(f"lineage re-derived       : {verified}/{len(rows)} match")

    # --- 6. shared-sector validator ------------------------------------------
    # Prove the guard fires: an aggregate drawing both aluminum and copper for
    # one industry must be rejected.
    sample_industry = eligible[0]["industry_id"]
    both = [
        r for r in rows
        if r["industry_id"] == "IND-01" and r["shared_io_source_sector"]
        and r["matrix_variant"] == "primary_direct_lag2"
        and r["base_feature_name"] == "price_level"
        and r["reference_month"] == "2021-01-01"
    ]
    shared_guard_fires = False
    if len(both) > 1:
        try:
            IC.assert_no_duplicate_shared_sector_aggregate(both, "self-check")
        except IC.ConditioningError:
            shared_guard_fires = True
    print(f"shared-sector guard      : fires={shared_guard_fires} "
          f"(sample industry {sample_industry})")

    # --- 7. development snapshot ---------------------------------------------
    snapshot_spec = config["development_snapshot"]
    industries = sorted({r["industry_id"] for r in exposure_rows})
    commodities = sorted({r["commodity_series_id"] for r in exposure_rows})
    eligible_pairs = {
        (r["industry_id"], r["commodity_series_id"]) for r in eligible
    }
    origins = FS.development_origins(
        str(snapshot_spec["first_origin"]), str(snapshot_spec["last_origin"])
    )
    snapshot = FS.build_development_snapshot(
        rows, industries, commodities, features, eligible_pairs, origins,
        matrix_variant=snapshot_spec["matrix_variant"],
    )
    expected_snapshot = snapshot_spec["expected"]
    for key, value in expected_snapshot.items():
        if snapshot["dimensions"][key] != value:
            raise SystemExit(
                f"C4 FAILED: snapshot {key} is {snapshot['dimensions'][key]}, "
                f"expected {value}."
            )
    print(f"development snapshot     : {snapshot['dimensions']['industry_origin_rows']}"
          f" rows, {snapshot['dimensions']['eligible_feature_cells']} eligible cells, "
          f"{snapshot['dimensions']['ineligible_feature_cells']} ineligible")

    # --- 8. wide view, pivoted from the canonical table ----------------------
    wide = IC.to_wide_table(rows, "primary_direct_lag2")
    mismatches = 0
    index = {(r["reference_month"], r["industry_id"]): r for r in wide}
    for row in rows:
        if row["matrix_variant"] != "primary_direct_lag2":
            continue
        cell = index[(row["reference_month"], row["industry_id"])]
        column = f"{row['commodity_series_id']}__{row['base_feature_name']}"
        if cell.get(column) != row["conditioned_feature_value"]:
            mismatches += 1
    if mismatches:
        raise SystemExit(f"C4 FAILED: {mismatches} long/wide mismatches.")
    print(f"long<->wide              : reconciled ({len(wide)} rows, 0 mismatches)")

    # --- 9. git-ignored parquet ----------------------------------------------
    import pandas as pd

    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for name, payload in (
        ("canonical_long", rows),
        ("wide_primary", wide),
        ("development_snapshot", snapshot["rows"]),
    ):
        path = FEATURE_DIR / f"c4_{name}.parquet"
        pd.DataFrame(payload).to_parquet(path, index=False)
        outputs[name] = {
            "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "rows": len(payload),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    zero_counts: dict[str, int] = {}
    for row in rows:
        zero_counts[row["zero_reason"]] = zero_counts.get(row["zero_reason"], 0) + 1

    output = {
        "task": "C4",
        "transformation_version": IC.MATRIX_VARIANTS[0].name and config[
            "transformation_version"
        ],
        "generated_at": generated_at,
        "inputs": {
            "c2": {
                "commodity_series": len(series),
                "base_features": features,
                "observations_per_series": expected["observations_per_series"],
                "rows_per_policy": {k: len(v) for k, v in c2_rows.items()},
                "point_in_time_first_release_only": True,
            },
            "c3": {name: value[0] for name, value in checks.items()},
            "c3_matrix_checksum": c3["content_checksum"],
        },
        "structural_availability": {
            "structural_reference_year": availability.structural_reference_year,
            "structural_available_by": availability.structural_available_by,
            "status": availability.status,
            "evidence_type": availability.evidence_type,
            "evidence_url": availability.evidence_url,
            "document_date": availability.document_date,
            "publication_date": availability.publication_date,
            "evidence_checksum": availability.evidence_checksum,
            "byte_identity_verified_at_that_date": (
                availability.byte_identity_verified_at_that_date
            ),
            "reference_year_treated_as_publication_date": False,
            "download_timestamp_used_as_availability": False,
            "first_development_origin": str(spec["first_development_origin"]),
            "primary_matrix_permitted": True,
            "fully_real_time": False,
            "notes": availability.notes,
        },
        "matrix_variants": [
            {
                "name": v.name,
                "availability_policy": v.availability_policy,
                "exposure_field": v.exposure_field,
                "is_primary": v.is_primary,
                "label": v.label,
                "varies_from_primary": v.varies_from_primary,
                "rows": per_variant[v.name],
            }
            for v in IC.MATRIX_VARIANTS
        ],
        "combined_double_sensitivity_variant_created": False,
        "canonical_row_count": len(rows),
        "expected_canonical_row_count": config["expected_counts"][
            "combined_canonical_rows"
        ],
        "rows_per_variant": per_variant,
        "eligible_pairs": len(eligible),
        "excluded_pairs": [
            {
                "industry_id": r["industry_id"],
                "commodity_series_id": r["commodity_series_id"],
                "exclusion_reason": (
                    "commodity_proxy_fitness"
                    if r["commodity_proxy_fit_status"]
                    == "not_fit_for_commodity_specific_use"
                    else "mixed_or_ambiguous_direction"
                ),
                "commodity_proxy_fit_status": r["commodity_proxy_fit_status"],
                "direction_channel": r["direction_channel"],
                "direct_exposure_retained": r["direct_exposure"],
                "total_requirement_exposure_retained": r[
                    "total_requirement_exposure"
                ],
                "converted_to_zero": False,
                "conditioned_features_generated": 0,
            }
            for r in sorted(
                ineligible, key=lambda r: (r["industry_id"], r["commodity_series_id"])
            )
        ],
        "zero_reason_counts": zero_counts,
        "lineage_rows_verified": verified,
        "shared_sector": {
            "shared_exposure_group": "io_sector_107",
            "rows_flagged": sum(1 for r in rows if r["shared_io_source_sector"]),
            "additive_aggregation_allowed": False,
            "duplicate_aggregate_validator_fires": shared_guard_fires,
            "combined_non_ferrous_index_created": False,
            "pca_or_weighted_average_created": False,
        },
        "development_snapshot": {
            "matrix_variant": snapshot["matrix_variant"],
            "dimensions": snapshot["dimensions"],
            "cell_status_counts": snapshot["cell_status_counts"],
            "selection_rule": snapshot["selection_rule"],
            "positional_shift_used": snapshot["positional_shift_used"],
            "target_columns_attached": snapshot["target_columns_attached"],
            "first_origin": origins[0],
            "last_origin": origins[-1],
        },
        "wide_reconciliation": {
            "rows": len(wide),
            "mismatches": mismatches,
            "reconciled": True,
            "derived_from_long_table": True,
        },
        "outputs": outputs,
        "content_checksums": {
            "canonical_long": content_checksum(rows),
            "wide_primary": content_checksum(wide),
            "development_snapshot": content_checksum(snapshot["rows"]),
            "development_mask": content_checksum(snapshot["mask"]),
        },
        "normalized_across_commodities": False,
        "normalized_across_industries": False,
        # Scope guards, recorded so the claim is auditable.
        "joined_to_mpi_targets": False,
        "target_association_computed": False,
        "feature_selection_using_outcomes": False,
        "model_trained": False,
        "b4_baselines_compared": False,
        "locked_test_accessed": False,
        "model_feature_approved_set": False,
    }
    OUT_JSON.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"content checksum         : {output['content_checksums']['canonical_long'][:16]}")
    print(f"written                  : {OUT_JSON.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
