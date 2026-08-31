"""Run Task B4: walk-forward baselines on the development period.

The locked final test period is RESERVED. This runner emits a manifest of its
keys and checksums and nothing else — no metric, no distribution, no plot. There
is deliberately NO command-line flag that evaluates it: unlocking is a separate,
explicit task, and an accidental `--include-test` is exactly the mistake that
would silently burn the test set.

Usage:
    python scripts/run_b4_baselines.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from thai_supply_chain_ews.evaluation import metrics as M  # noqa: E402
from thai_supply_chain_ews.evaluation.bootstrap import (  # noqa: E402
    bootstrap_macro_mae_ci,
    bootstrap_paired_macro_mae_difference,
    build_error_matrix,
)
from thai_supply_chain_ews.evaluation.splits import load_walk_forward_plan  # noqa: E402
from thai_supply_chain_ews.evaluation.walk_forward import (  # noqa: E402
    LABELS_PATH,
    MONTHLY_STRESS_PATH,
    load_b3_artifacts,
    run_walk_forward,
)

OUT_DIR = PROJECT_ROOT / "data" / "model_input"
RESULTS_JSON = PROJECT_ROOT / "docs" / "b4_baseline_results.json"
LOCKED_MANIFEST = PROJECT_ROOT / "docs" / "b4_locked_test_manifest.json"
B1_PANEL = PROJECT_ROOT / "data" / "processed" / "industry_month_panel.parquet"

SKILL_REFERENCE = "industry_historical_mean"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_safe(obj):
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if hasattr(obj, "item"):
        return json_safe(obj.item())
    return obj


def evaluate_baseline(frame: pd.DataFrame, bootstrap_cfg: dict, seed_offset: int) -> dict:
    result = {
        "n_rows": int(len(frame)),
        "n_origins": int(frame["forecast_origin_month"].nunique()),
        "n_industries": int(frame["industry_id"].nunique()),
        "macro_industry_mae": M.macro_industry_mae(frame),
        "pooled_mae": M.pooled_mae(frame),
        "macro_industry_rmse": M.macro_industry_rmse(frame),
        "pooled_rmse": M.pooled_rmse(frame),
        "median_absolute_error": M.median_absolute_error(frame),
        "pooled_spearman": M.spearman_correlation(
            frame["observed_score"].to_numpy(float), frame["predicted_score"].to_numpy(float)
        ),
        "per_industry_mae": M.per_industry_mae(frame),
        "high_stress_event": M.high_stress_event_metrics(frame),
        "severe_event": M.severe_event_counts(frame),
        "by_block": {
            str(block): {
                "n_rows": int(len(sub)),
                "macro_industry_mae": M.macro_industry_mae(sub),
                "pooled_mae": M.pooled_mae(sub),
            }
            for block, sub in frame.groupby("split_name", observed=True)
        },
    }
    result["macro_mae_ci"] = bootstrap_macro_mae_ci(
        build_error_matrix(frame), bootstrap_cfg, seed_offset=seed_offset
    )
    return result


def main() -> None:
    plan = load_walk_forward_plan()
    bootstrap_cfg = plan.config["bootstrap"]

    b1_before = sha256_of(B1_PANEL)
    b3_before = {p.name: sha256_of(p) for p in (MONTHLY_STRESS_PATH, LABELS_PATH)}

    monthly, labels = load_b3_artifacts()
    result = run_walk_forward(monthly, labels, plan)
    predictions = result.predictions

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    predictions_path = OUT_DIR / "b4_walk_forward_predictions.parquet"
    predictions.to_parquet(predictions_path, index=False, engine="pyarrow")

    # --- metrics per horizon and baseline -----------------------------------
    by_horizon: dict[str, dict] = {}
    seed_offset = 0
    for horizon in plan.horizons:
        horizon_frame = predictions[predictions["horizon_months"] == horizon]
        baselines = sorted(horizon_frame["baseline_name"].unique().tolist())
        per_baseline: dict[str, dict] = {}
        for name in baselines:
            seed_offset += 1
            per_baseline[name] = evaluate_baseline(
                horizon_frame[horizon_frame["baseline_name"] == name],
                bootstrap_cfg,
                seed_offset,
            )

        reference_mae = per_baseline[SKILL_REFERENCE]["macro_industry_mae"]
        reference_frame = horizon_frame[horizon_frame["baseline_name"] == SKILL_REFERENCE]
        for name, stats in per_baseline.items():
            stats["mae_skill_vs_historical_mean"] = M.mae_skill(
                stats["macro_industry_mae"], reference_mae
            )
            if name == SKILL_REFERENCE:
                stats["skill_ci"] = None
                stats["paired_difference_vs_reference"] = None
                continue
            seed_offset += 1
            stats["paired_difference_vs_reference"] = bootstrap_paired_macro_mae_difference(
                build_error_matrix(horizon_frame[horizon_frame["baseline_name"] == name]),
                build_error_matrix(reference_frame),
                bootstrap_cfg,
                seed_offset=seed_offset,
            )

        # paired differences by forecast origin, versus the reference
        origin_diffs: dict[str, dict[str, float]] = {}
        for name in baselines:
            sub = horizon_frame[horizon_frame["baseline_name"] == name]
            origin_diffs[name] = {
                str(origin): M.macro_industry_mae(group)
                for origin, group in sub.groupby("forecast_origin_month", observed=True)
            }

        # --- baseline selection (development only) --------------------------
        ranked = sorted(
            per_baseline.items(),
            key=lambda kv: (
                kv[1]["macro_industry_mae"],
                kv[1]["high_stress_event"]["false_negative"],
            ),
        )
        best_name, best_stats = ranked[0]
        runner_up_name, runner_up_stats = ranked[1]
        seed_offset += 1
        tie_check = bootstrap_paired_macro_mae_difference(
            build_error_matrix(horizon_frame[horizon_frame["baseline_name"] == best_name]),
            build_error_matrix(horizon_frame[horizon_frame["baseline_name"] == runner_up_name]),
            bootstrap_cfg,
            seed_offset=seed_offset,
        )
        effectively_tied = tie_check["verdict"] == "inconclusive"
        selection_reason = "lowest_development_macro_industry_mae"
        if effectively_tied:
            best_fn = best_stats["high_stress_event"]["false_negative"]
            runner_fn = runner_up_stats["high_stress_event"]["false_negative"]
            if runner_fn < best_fn:
                best_name, best_stats = runner_up_name, runner_up_stats
                selection_reason = "effective_tie_broken_by_lower_false_negative_count"
            elif runner_fn == best_fn:
                selection_reason = "effective_tie_broken_by_simplicity"
            else:
                selection_reason = "effective_tie_but_leader_also_had_fewer_false_negatives"

        by_horizon[str(horizon)] = {
            "baselines": per_baseline,
            "macro_mae_by_origin": origin_diffs,
            "selected_benchmark": best_name,
            "selection_reason": selection_reason,
            "selection_used_locked_test_information": False,
            "leader_vs_runner_up": {
                "leader": ranked[0][0],
                "runner_up": runner_up_name,
                "paired_macro_mae_difference": tie_check,
                "conclusive": not effectively_tied,
            },
        }

    # --- locked test manifest — keys and checksums ONLY ----------------------
    locked_entries = {}
    for horizon in plan.horizons:
        spec = plan.config["locked_test"]["horizons"][int(horizon)]
        origins = plan.locked_test_origins(horizon)
        keys = labels[
            (labels["horizon_months"] == horizon)
            & (labels["forecast_origin_month"].isin(origins))
        ][["forecast_origin_month", "industry_id", "horizon_months"]].sort_values(
            ["forecast_origin_month", "industry_id"]
        )
        key_blob = "\n".join(
            f"{r.forecast_origin_month}|{r.industry_id}|{r.horizon_months}"
            for r in keys.itertuples()
        )
        locked_entries[str(horizon)] = {
            "first_origin": str(spec["first_origin"]),
            "last_origin": str(spec["last_origin"]),
            "origin_count": len(origins),
            "expected_rows": int(spec["expected_rows"]),
            "actual_rows": int(len(keys)),
            "rows_match_expected": len(keys) == int(spec["expected_rows"]),
            "key_sha256": hashlib.sha256(key_blob.encode("utf-8")).hexdigest(),
        }
    locked_manifest = {
        "task": "B4",
        "evaluated_in_b4": False,
        "manifest_only": True,
        "statement": (
            "This period is RESERVED. B4 computed no target distribution, metric, "
            "risk-level frequency, plot, or model comparison on it. The runner exposes "
            "no flag to evaluate it."
        ),
        "prohibited_outputs": plan.config["locked_test"]["prohibited_outputs"],
        "horizons": locked_entries,
        "target_definition_version": plan.config["target_definition_version"],
        "evaluation_harness_version": plan.harness_version,
    }
    with LOCKED_MANIFEST.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(json_safe(locked_manifest), indent=2, ensure_ascii=False))

    b1_after = sha256_of(B1_PANEL)
    b3_after = {p.name: sha256_of(p) for p in (MONTHLY_STRESS_PATH, LABELS_PATH)}

    output = {
        "task": "B4",
        "evaluation_harness_version": plan.harness_version,
        "target_definition_version": plan.config["target_definition_version"],
        "b3_invariants": result.b3_findings,
        "development": {
            "first_origin": result.origins[0],
            "last_origin": result.origins[-1],
            "origin_count": len(result.origins),
            "rows_per_horizon_per_baseline": int(
                plan.config["development"]["expected_rows_per_horizon"]
            ),
            "total_prediction_rows": int(len(predictions)),
            "blocks": [b["name"] for b in plan.config["development"]["blocks"]],
        },
        "purge_buffer": {
            "first_origin": str(plan.config["purge_buffer"]["first_origin"]),
            "last_origin": str(plan.config["purge_buffer"]["last_origin"]),
            "metrics_reported": False,
        },
        "locked_test_evaluated": False,
        "information_rules": plan.config["information_rules"],
        "bootstrap": plan.config["bootstrap"],
        "by_horizon": by_horizon,
        "upstream_artifacts_unmodified": {
            "b1_panel": b1_before == b1_after,
            "b3_monthly_stress": b3_before[MONTHLY_STRESS_PATH.name]
            == b3_after[MONTHLY_STRESS_PATH.name],
            "b3_labels": b3_before[LABELS_PATH.name] == b3_after[LABELS_PATH.name],
        },
    }
    with RESULTS_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(json_safe(output), indent=2, ensure_ascii=False))

    # --- console summary -----------------------------------------------------
    print("=== Task B4 — walk-forward baselines (development only) ===")
    print(f"B3 invariants reproduced : {result.b3_findings['all_invariants_reproduced']}")
    print(f"development origins      : {len(result.origins)} "
          f"({result.origins[0]} .. {result.origins[-1]})")
    print(f"prediction rows          : {len(predictions)}")
    print("locked test evaluated    : False (manifest only)")
    for horizon in plan.horizons:
        info = by_horizon[str(horizon)]
        print(f"\n--- horizon {horizon}m ---")
        print(f"{'baseline':<30} {'macroMAE':>9} {'pooled':>8} {'skill':>7} "
              f"{'FN@85':>6} {'macroMAE 95% CI':>22}")
        for name, stats in sorted(
            info["baselines"].items(), key=lambda kv: kv[1]["macro_industry_mae"]
        ):
            ci = stats["macro_mae_ci"]
            ci_text = (
                f"[{ci['ci_low']:.2f}, {ci['ci_high']:.2f}]"
                if ci["ci_low"] is not None
                else "n/a"
            )
            print(f"{name:<30} {stats['macro_industry_mae']:9.3f} "
                  f"{stats['pooled_mae']:8.3f} "
                  f"{stats['mae_skill_vs_historical_mean']:7.3f} "
                  f"{stats['high_stress_event']['false_negative']:6d} {ci_text:>22}")
        lead = info["leader_vs_runner_up"]
        print(f"selected benchmark       : {info['selected_benchmark']} "
              f"({info['selection_reason']})")
        print(f"leader vs runner-up      : {lead['leader']} vs {lead['runner_up']} -> "
              f"{lead['paired_macro_mae_difference']['verdict']}")

    print(f"\nupstream artifacts unmodified: {output['upstream_artifacts_unmodified']}")
    print(f"\nwritten:\n  {predictions_path.relative_to(PROJECT_ROOT)}"
          f"\n  {RESULTS_JSON.relative_to(PROJECT_ROOT)}"
          f"\n  {LOCKED_MANIFEST.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
