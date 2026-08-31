"""Task C2 — build the point-in-time commodity feature table.

Takes NO command-line arguments, for the same reason the B4 runner does not:
there is no flag that can widen the series allowlist, lower the lag, promote the
sensitivity table to primary, or reach a target. Everything this script can do,
it does the same way every run.

All transformation logic lives in
``thai_supply_chain_ews.features.commodity_features``. This file orchestrates
and reports; it never computes a formula of its own.

    python scripts/run_c2_commodity_features.py
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
from thai_supply_chain_ews.features.feature_availability import (  # noqa: E402
    PRIMARY_POLICY,
    SENSITIVITY_POLICY,
)

AUDIT_INPUT = PROJECT_ROOT / "docs" / "c1_5_commodity_timing_audit.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "commodity_features.yaml"
FEATURE_DIR = PROJECT_ROOT / "data" / "features"
AUDIT_JSON = PROJECT_ROOT / "docs" / "c2_commodity_feature_audit.json"

# B4's split configuration is read for ORIGIN COVERAGE only. No target value and
# no evaluation outcome is opened by this script; a test asserts the target and
# evaluation modules are never imported here.
SPLITS_PATH = PROJECT_ROOT / "configs" / "evaluation_splits.yaml"


def content_checksum(rows: list[dict]) -> str:
    """Deterministic digest of table content, independent of file encoding."""
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_parquet(rows: list[dict], path: Path) -> dict:
    """Write a git-ignored Parquet file and report what went into it."""
    import pandas as pd

    frame = pd.DataFrame(rows)
    for column in frame.columns:
        if column.endswith("_month") or column in (
            "reference_month", "input_window_start", "input_window_end",
            "source_issue_date",
        ):
            frame[column] = pd.to_datetime(frame[column])
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {
        "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def development_origin_coverage(rows: list[dict]) -> dict:
    """Do the primary features cover every B4 development forecast origin?

    Reads only the ORIGIN MONTHS from the split configuration. Target values and
    evaluation results are not opened, and the locked test period is not touched.
    """
    splits = yaml.safe_load(SPLITS_PATH.read_text(encoding="utf-8"))
    development = splits["development"]
    start, end = str(development["first_origin"]), str(development["last_origin"])

    origins, cursor = [], start
    while cursor <= end:
        origins.append(cursor)
        cursor = CF.add_months(cursor, 1)

    # An origin counts as covered only when EVERY series/feature pair has at
    # least one reference month usable by then. "Some feature exists" would be
    # trivially true and would hide a series that starts late.
    expected_pairs = {
        (series_id, definition.name)
        for series_id in CF.PRIMARY_SERIES
        for definition in CF.FEATURE_DEFINITIONS
    }
    covered, per_origin = [], {}
    for origin in origins:
        usable = {
            (r["series_id"], r["feature_name"])
            for r in rows
            if r["feature_available_month"] <= origin
        }
        missing = sorted(expected_pairs - usable)
        per_origin[origin] = {
            "series_feature_pairs_usable": len(usable),
            "missing_pairs": missing,
        }
        if not missing:
            covered.append(origin)
    return {
        "development_origin_start": start,
        "development_origin_end": end,
        "required_origins": len(origins),
        "expected_series_feature_pairs": len(expected_pairs),
        "fully_covered_origins": len(covered),
        "fully_covered": len(covered) == len(origins),
        "per_origin": per_origin,
        "locked_test_period_read": False,
        "target_values_read": False,
    }


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=== C2 - point-in-time commodity feature construction ===")

    # --- 1. authoritative input ---------------------------------------------
    loaded = CF.load_first_release_observations(AUDIT_INPUT)
    observations = loaded["observations"]
    required_months = loaded["required_months"]
    print(f"input dataset      : {AUDIT_INPUT.name} (C1.5-R2)")
    print(f"contract           : {loaded['contract']}")
    print(f"reference months   : {len(required_months)} "
          f"({required_months[0]} .. {required_months[-1]})")

    per_series_inputs = {
        series_id: len(observations.get(series_id, {}))
        for series_id in CF.PRIMARY_SERIES
    }
    print(f"primary inputs     : {per_series_inputs}")

    # --- 2. primary canonical table ------------------------------------------
    primary = CF.build_feature_table(
        observations, required_months, PRIMARY_POLICY, CF.PRIMARY_SERIES
    )
    expected_per_series = CF.expected_row_counts()
    expected_total = sum(expected_per_series.values()) * len(CF.PRIMARY_SERIES)
    if len(primary) != expected_total:
        raise SystemExit(
            f"C2 FAILED: produced {len(primary)} canonical rows, expected "
            f"{expected_total}. No value is manufactured to close the gap."
        )
    print(f"canonical rows     : {len(primary)} (expected {expected_total})")

    # --- 3. sensitivity table, clearly labelled ------------------------------
    sensitivity = CF.build_feature_table(
        observations, required_months, SENSITIVITY_POLICY, CF.PRIMARY_SERIES
    )
    print(f"sensitivity rows   : {len(sensitivity)} "
          f"(label={SENSITIVITY_POLICY.label}, NOT the default output)")

    # --- 4. wide view, pivoted from the canonical table ----------------------
    wide = CF.to_wide_table(primary)
    print(f"wide rows          : {len(wide)} (derived from the long table)")

    # --- 5. write git-ignored artifacts --------------------------------------
    outputs = {
        "canonical_long": write_parquet(
            primary, FEATURE_DIR / "commodity_features_long.parquet"
        ),
        "wide": write_parquet(wide, FEATURE_DIR / "commodity_features_wide.parquet"),
        "sensitivity_long": write_parquet(
            sensitivity,
            FEATURE_DIR / "commodity_features_long_sensitivity_lag1.parquet",
        ),
    }

    # --- 6. per-feature and per-series reporting -----------------------------
    per_feature: dict[str, dict] = {}
    for definition in CF.FEATURE_DEFINITIONS:
        rows = [r for r in primary if r["feature_name"] == definition.name]
        months = sorted({r["reference_month"] for r in rows})
        per_feature[definition.name] = {
            "rows_total": len(rows),
            "rows_per_series": len(rows) // len(CF.PRIMARY_SERIES),
            "expected_rows_per_series": expected_per_series[definition.name],
            "earliest_reference_month": months[0],
            "latest_reference_month": months[-1],
            "input_observation_count": rows[0]["input_observation_count"],
            "earliest_feature_available_month": min(
                r["feature_available_month"] for r in rows
            ),
        }
        print(f"  {definition.name:<28} rows={len(rows):>4} "
              f"per_series={len(rows) // len(CF.PRIMARY_SERIES):>3} "
              f"months={months[0]}..{months[-1]}")

    per_series = {}
    for series_id in CF.PRIMARY_SERIES:
        rows = [r for r in primary if r["series_id"] == series_id]
        per_series[series_id] = {
            "rows": len(rows),
            "features": sorted({r["feature_name"] for r in rows}),
            "reference_month_start": min(r["reference_month"] for r in rows),
            "reference_month_end": max(r["reference_month"] for r in rows),
            "unit_price_level": next(
                r["unit"] for r in rows if r["feature_name"] == "price_level"
            ),
            "source_series_label": rows[0]["source_series_label"],
            "model_feature_approved": False,
        }

    # --- 7. integrity checks reported, not assumed ---------------------------
    integrity = {
        "unique_canonical_keys": len(
            {(r["series_id"], r["feature_name"], r["reference_month"],
              r["availability_policy"]) for r in primary}
        ) == len(primary),
        "all_values_finite": all(
            isinstance(r["feature_value"], float) and r["feature_value"] == r["feature_value"]
            and abs(r["feature_value"]) != float("inf")
            for r in primary
        ),
        "source_available_never_after_feature_available": all(
            r["source_available_month"] <= r["feature_available_month"]
            for r in primary
        ),
        "policy_available_never_after_feature_available": all(
            r["policy_available_month"] <= r["feature_available_month"]
            for r in primary
        ),
        "all_operational_lags_are_two": {
            r["operational_lag_months"] for r in primary
        } == {2},
        "all_minimum_publication_lags_are_one": {
            r["minimum_publication_lag_months"] for r in primary
        } == {1},
        "no_excluded_series_present": not (
            {r["series_id"] for r in primary} & set(CF.EXCLUDED_SERIES)
        ),
        "all_values_archived_first_release": {
            r["source_value_type"] for r in primary
        } == {"archived_first_release"},
        "sensitivity_labelled_sensitivity_only": {
            r["availability_policy_label"] for r in sensitivity
        } == {"sensitivity_only"},
        "distinct_lineage_checksums": len(
            {r["input_lineage_checksum"] for r in primary}
        ),
    }
    for name, value in integrity.items():
        if value is False:
            raise SystemExit(f"C2 FAILED integrity check: {name}")

    # --- 8. canonical-to-wide reconciliation ---------------------------------
    mismatches = 0
    wide_index = {(r["reference_month"], r["series_id"]): r for r in wide}
    for row in primary:
        cell = wide_index[(row["reference_month"], row["series_id"])]
        column = f"{row['series_id']}__{row['feature_name']}"
        if cell.get(column) != row["feature_value"]:
            mismatches += 1
    reconciliation = {
        "long_rows": len(primary),
        "wide_cells_checked": len(primary),
        "mismatches": mismatches,
        "reconciled": mismatches == 0,
    }
    if mismatches:
        raise SystemExit(f"C2 FAILED: {mismatches} long/wide mismatches.")
    print(f"long<->wide        : reconciled ({len(primary)} cells, 0 mismatches)")

    coverage = development_origin_coverage(primary)
    print(f"B4 dev origins     : {coverage['fully_covered_origins']}"
          f"/{coverage['required_origins']} fully covered")

    output = {
        "task": "C2",
        "feature_definition_version": CF.FEATURE_DEFINITION_VERSION,
        "generated_at": generated_at,
        "input": {
            "dataset": str(AUDIT_INPUT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "dataset_task": "C1.5-R2",
            "contract": loaded["contract"],
            "reference_month_start": required_months[0],
            "reference_month_end": required_months[-1],
            "reference_months": len(required_months),
            "monthly_inputs_per_primary_series": per_series_inputs,
            "latest_vintage_substitution_permitted": False,
        },
        "series": {
            "primary": list(CF.PRIMARY_SERIES),
            "excluded": CF.EXCLUDED_SERIES,
            "substitutes_for_excluded": [],
        },
        "availability": {
            "minimum_publication_lag_months": 1,
            "operational_lag_months": PRIMARY_POLICY.operational_lag_months,
            "primary_policy": PRIMARY_POLICY.name,
            "primary_policy_basis": PRIMARY_POLICY.basis,
            "sensitivity_policy": SENSITIVITY_POLICY.name,
            "sensitivity_policy_label": SENSITIVITY_POLICY.label,
            "sensitivity_policy_basis": SENSITIVITY_POLICY.basis,
            "lag_zero_prohibited": True,
            "derived_from_download_date": False,
        },
        "feature_definitions": {
            definition.name: {
                "description": definition.description,
                "input_lags": list(definition.input_lags),
                "min_history_months": definition.min_history_months,
                "unit_kind": definition.unit_kind,
            }
            for definition in CF.FEATURE_DEFINITIONS
        },
        "per_feature": per_feature,
        "per_series": per_series,
        "canonical_row_count": len(primary),
        "expected_canonical_row_count": expected_total,
        "sensitivity_row_count": len(sensitivity),
        "wide_row_count": len(wide),
        "integrity": integrity,
        "reconciliation": reconciliation,
        "b4_development_origin_coverage": coverage,
        "content_checksums": {
            "canonical_long": content_checksum(primary),
            "wide": content_checksum(wide),
            "sensitivity_long": content_checksum(sensitivity),
        },
        "outputs": outputs,
        "data_handling": {
            "imputation": "none",
            "forward_fill": "none",
            "interpolation": "none",
            "clipping": "none",
            "winsorization": "none",
            "rounding_of_calculated_features": "none",
            "manufactured_early_window_values": 0,
        },
        # Scope guards, recorded so the claim is auditable rather than asserted
        # in prose only.
        "industry_dependency_matrix_created": False,
        "features_joined_to_target": False,
        "target_association_computed": False,
        "feature_selection_using_target": False,
        "model_trained": False,
        "b4_baselines_compared": False,
        "locked_test_accessed": False,
        "model_feature_approved_set": False,
        "feature_semantics_approved_set": False,
        "config_expected_rows_match": (
            config["expected_primary_canonical_rows"] == expected_total
        ),
    }
    AUDIT_JSON.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"audit written      : {AUDIT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"content checksum   : {output['content_checksums']['canonical_long'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
