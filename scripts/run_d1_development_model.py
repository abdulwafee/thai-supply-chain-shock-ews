"""Task D1 — leakage-safe development model and benchmark comparison.

Takes NO command-line arguments. There is no flag, mode or environment variable
that can evaluate the locked test: the origin list comes from the development
split and every modelling entry point rejects an origin outside it.

All computation lives in the package.

    python scripts/run_d1_development_model.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.evaluation import baselines as BL  # noqa: E402
from thai_supply_chain_ews.evaluation import splits as SP  # noqa: E402
from thai_supply_chain_ews.evaluation import walk_forward as WF  # noqa: E402
from thai_supply_chain_ews.modeling import development_comparison as DC  # noqa: E402
from thai_supply_chain_ews.modeling import feature_target_assembly as FA  # noqa: E402
from thai_supply_chain_ews.modeling import nested_walk_forward as NW  # noqa: E402
from thai_supply_chain_ews.targets.calibration import IndustryStressCalibrator  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "d1_development_models.yaml"
C4_PARQUET = PROJECT_ROOT / "data" / "features" / "c4_canonical_long.parquet"
C4_AUDIT = PROJECT_ROOT / "docs" / "c4_industry_conditioned_feature_audit.json"
ASSEMBLY_JSON = PROJECT_ROOT / "docs" / "d1_feature_target_assembly_audit.json"
RESULTS_JSON = PROJECT_ROOT / "docs" / "d1_development_results.json"
MODEL_INPUT_DIR = PROJECT_ROOT / "data" / "model_input"

BENCHMARKS = {1: "persistence_current_month", 3: "persistence_trailing_3m_max"}


def content_checksum(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=== D1 - development model vs B4 persistence benchmarks ===")

    # --- 1. reproduce upstream invariants ------------------------------------
    monthly, labels = WF.load_b3_artifacts()
    b3 = WF.validate_b3_invariants(monthly, labels)
    expected3 = config["upstream_invariants"]["b3"]
    problems = []
    if b3["monthly_rows"] != expected3["monthly_stress_rows"]:
        problems.append(f"monthly rows {b3['monthly_rows']}")
    if b3["combined_rows"] != expected3["combined_labels"]:
        problems.append(f"combined labels {b3['combined_rows']}")
    h1 = int((labels["horizon_months"] == 1).sum())
    h3 = int((labels["horizon_months"] == 3).sum())
    if h1 != expected3["h1_labels"] or h3 != expected3["h3_labels"]:
        problems.append(f"labels h1={h1} h3={h3}")
    if b3["duplicate_keys"] != 0 or b3["primary_component_count"] != 1:
        problems.append("duplicate keys or component count")
    if str(monthly["reference_month"].astype(str).max())[:7] >= "2026-06":
        problems.append("2026-06 present in monthly stress")
    if problems:
        raise SystemExit(f"D1 FAILED: B3 invariants: {problems}")
    print(f"B3 invariants            : {b3['monthly_rows']} monthly, "
          f"h1={h1}, h3={h3}, combined={b3['combined_rows']}")

    plan = SP.load_walk_forward_plan()
    expected4 = config["upstream_invariants"]["b4"]
    if [str(o)[:10] for o in plan.development_origins] != [
        str(o)[:10] for o in SP.month_range(
            str(expected4["development_first_origin"]),
            str(expected4["development_last_origin"]),
        )
    ]:
        raise SystemExit("D1 FAILED: development origins do not match B4.")
    origins = [str(o)[:10] for o in plan.development_origins]
    purge = {str(o)[:10] for o in plan.purge_origins}
    # Locked-test ORIGIN KEYS only, for the non-overlap assertion. No locked
    # target outcome is read, joined, summarised or hashed anywhere in D1.
    locked = set()
    for horizon in plan.horizons:
        locked.update(str(o)[:10] for o in plan.locked_test_origins(horizon))
    if len(origins) != 15:
        raise SystemExit(f"D1 FAILED: {len(origins)} development origins.")
    print(f"B4 plan                  : {len(origins)} origins "
          f"{origins[0]}..{origins[-1]}, purge {sorted(purge)}, "
          f"locked reserved ({len(locked)} origins, outcomes unread)")

    c4_audit = json.loads(C4_AUDIT.read_text(encoding="utf-8"))
    expectedc4 = config["upstream_invariants"]["c4"]
    c4_problems = []
    if c4_audit["canonical_row_count"] != expectedc4["combined_rows"]:
        c4_problems.append("combined rows")
    if set(c4_audit["rows_per_variant"].values()) != {expectedc4["rows_per_variant"]}:
        c4_problems.append("rows per variant")
    if c4_audit["eligible_pairs"] != expectedc4["eligible_pairs"]:
        c4_problems.append("eligible pairs")
    if len(c4_audit["excluded_pairs"]) != expectedc4["ineligible_pairs"]:
        c4_problems.append("ineligible pairs")
    if c4_audit["combined_double_sensitivity_variant_created"] is not False:
        c4_problems.append("combined lag1+total variant exists")
    if c4_audit["structural_availability"]["structural_available_by"] != str(
        expectedc4["structural_available_by"]
    ):
        c4_problems.append("structural_available_by")
    snapshot = c4_audit["development_snapshot"]["dimensions"]
    if (snapshot["eligible_feature_cells"], snapshot["ineligible_feature_cells"]) != (
        expectedc4["eligible_cells"], expectedc4["ineligible_cells"]
    ):
        c4_problems.append("snapshot cells")
    if c4_problems:
        raise SystemExit(f"D1 FAILED: C4 invariants: {c4_problems}")
    print(f"C4 invariants            : {c4_audit['canonical_row_count']} rows, "
          f"{c4_audit['eligible_pairs']} eligible pairs, structural available "
          f"{c4_audit['structural_availability']['structural_available_by']}")

    # --- 2. inputs ------------------------------------------------------------
    frame = pd.read_parquet(C4_PARQUET)
    for column in ("reference_month", "conditioned_available_month"):
        frame[column] = frame[column].astype(str).str[:10]
    feature_rows = frame.to_dict("records")

    monthly_records = monthly.copy()
    monthly_records["reference_month"] = monthly_records["reference_month"].astype(str).str[:10]
    label_records = labels.copy()
    for column in ("forecast_origin_month", "target_window_end"):
        label_records[column] = label_records[column].astype(str).str[:10]
    label_list = label_records.to_dict("records")
    labels_by_key = {
        (r["industry_id"], r["forecast_origin_month"], int(r["horizon_months"])): r
        for r in label_list
    }
    industries = sorted(monthly_records["industry_id"].unique().tolist())

    raw_by_industry_month = {
        (r["industry_id"], r["reference_month"]): float(r["mpi_adverse_yoy"])
        for r in monthly_records.to_dict("records")
    }

    def make_calibrator(cutoff_month: str):
        reference = monthly_records[
            monthly_records["reference_month"] <= cutoff_month
        ]
        return IndustryStressCalibrator().fit(reference, cutoff_month)

    def benchmark_for(industry_id, origin, horizon, calibrator):
        """B4's own baseline implementation — reused, never copied."""
        history = {
            month: value
            for (ind, month), value in raw_by_industry_month.items()
            if ind == industry_id and month <= origin
        }
        context = BL.BaselineContext(
            origin=origin, industry_id=industry_id, horizon=int(horizon),
            calibrator=calibrator, raw_stress_by_month=history, training_scores=[],
        )
        try:
            _, score = BL.predict_baseline(BENCHMARKS[int(horizon)], context)
        except BL.InsufficientHistoryError:
            return None
        return float(score)

    indexes = {
        variant: FA.build_feature_index(feature_rows, variant)
        for variant in (
            expectedc4["primary_variant"],
            expectedc4["timing_sensitivity_variant"],
            expectedc4["structural_sensitivity_variant"],
        )
    }
    primary_variant = expectedc4["primary_variant"]

    # --- 3. outer loop --------------------------------------------------------
    all_predictions: list[dict] = []
    selections: dict[str, dict] = {}
    assembly_audit: list[dict] = []
    calibrator_audit: list[dict] = []

    for horizon in (1, 3):
        for origin in origins:
            plan.assert_not_locked_test([origin])
            if origin in purge or origin in locked:
                raise SystemExit(f"D1 FAILED: {origin} is a purge/locked origin.")

            calibrator = make_calibrator(origin)
            reference_months = sorted(
                monthly_records[monthly_records["reference_month"] <= origin][
                    "reference_month"
                ].unique().tolist()
            )
            calibration_record = {
                "forecast_origin_month": origin,
                "horizon_months": horizon,
                "calibration_reference_start": reference_months[0],
                "calibration_reference_end": reference_months[-1],
                "calibration_observations": int(
                    (monthly_records["reference_month"] <= origin).sum()
                ),
                "calibration_version": calibrator.version,
                "calibration_checksum": hashlib.sha256(
                    json.dumps(
                        sorted(
                            f"{industry}:"
                            f"{calibrator.reference_for(industry).fingerprint}"
                            for industry in calibrator.fitted_industries
                        ),
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
            if calibration_record["calibration_reference_end"] > origin:
                raise SystemExit("D1 FAILED: calibration reference exceeds origin.")
            calibrator_audit.append(calibration_record)

            # Inner validation origins: expanding, inside the outer window.
            # Three constraints bind at once — the calibrator's 24-observation
            # minimum, the feature-history gate, and the inner label window.
            inner_origins = []
            for candidate in SP.month_range("2022-03-01", origin):
                if candidate >= origin:
                    continue
                if str(SP.add_months(candidate, horizon)) > origin:
                    continue  # the inner validation label is not yet closed
                reference_count = int(
                    (monthly_records["reference_month"] <= candidate).sum()
                ) // len(industries)
                if reference_count < 24:
                    continue  # a calibrator cannot be fitted here
                permitted_inner = [
                    u for u in FA.label_permitted_origins(
                        label_list, candidate, horizon
                    )
                    if u >= "2022-03-01"
                ]
                if len(permitted_inner) < NW.MIN_INNER_TRAINING_ORIGINS:
                    continue
                inner_origins.append(candidate)

            selection = NW.select_configuration(
                indexes[primary_variant], labels_by_key, industries, horizon,
                origin, inner_origins, make_calibrator, benchmark_for, label_list,
            )
            selections[f"h{horizon}|{origin}"] = {
                "forecast_origin_month": origin,
                "horizon_months": horizon,
                "selected_alpha": selection["selected"].alpha,
                "selected_non_ferrous_channel": selection["selected"].non_ferrous_channel,
                "selection_reason": selection["selection_reason"],
                "selected_inner_macro_mae": selection["selected_inner_macro_mae"],
                "inner_origins_considered": selection["inner_origins_considered"],
                "inner_origins_covered": selection["inner_origins_covered"],
                "earliest_inner_origin": inner_origins[0] if inner_origins else None,
                "candidates": selection["candidates"],
            }

            for variant_key, variant in (
                ("primary", expectedc4["primary_variant"]),
                ("timing_sensitivity", expectedc4["timing_sensitivity_variant"]),
                ("structural_sensitivity", expectedc4["structural_sensitivity_variant"]),
            ):
                result = NW.fit_and_predict_origin(
                    indexes[variant], labels_by_key, industries, horizon, origin,
                    calibrator, benchmark_for, label_list, selection["selected"],
                    variant,
                )
                for prediction in result.predictions:
                    # THE TARGET IS READ ONLY NOW — the prediction is frozen.
                    label = labels_by_key[
                        (prediction["industry_id"], origin, horizon)
                    ]
                    raw = float(label["target_raw_value"])
                    observed = float(
                        calibrator.transform(prediction["industry_id"], raw)[0]
                    )
                    prediction.update(
                        variant_key=variant_key,
                        model_name="industry_specific_ridge_residual_correction",
                        benchmark_baseline_name=BENCHMARKS[horizon],
                        observed_raw_target=raw,
                        observed_score=observed,
                        block=plan.block_for_origin(origin),
                        split="development",
                        target_definition_version=str(
                            label.get("target_definition_version", "")
                        ),
                        evaluation_harness_version=plan.harness_version,
                        model_version=config["model_version"],
                        inner_validation_origin_count=selection["inner_origins_covered"],
                        inner_selection_score=selection["selected_inner_macro_mae"],
                        **calibration_record,
                    )
                    all_predictions.append(prediction)
                if variant_key == "primary":
                    for industry_id, assembly in result.assemblies.items():
                        assembly_audit.append(
                            {
                                "forecast_origin_month": origin,
                                "horizon_months": horizon,
                                "industry_id": industry_id,
                                "label_permitted_origins": assembly[
                                    "label_permitted_origins"
                                ],
                                "feature_usable_rows": assembly["feature_usable_rows"],
                                "excluded_for_feature_history": assembly[
                                    "excluded_for_feature_history"
                                ],
                                "earliest_usable_origin": assembly[
                                    "earliest_usable_origin"
                                ],
                                "latest_usable_origin": assembly["latest_usable_origin"],
                                "max_training_target_window_end": assembly[
                                    "max_training_target_window_end"
                                ],
                            }
                        )
        print(f"h={horizon} outer origins fitted  : {len(origins)}")

    # --- 4. counts ------------------------------------------------------------
    counts: dict[str, int] = {}
    for prediction in all_predictions:
        key = f"{prediction['variant_key']}|h{prediction['horizon_months']}"
        counts[key] = counts.get(key, 0) + 1
    expected_counts = {
        f"{variant}|h{horizon}": 180
        for variant in ("primary", "timing_sensitivity", "structural_sensitivity")
        for horizon in (1, 3)
    }
    if counts != expected_counts:
        raise SystemExit(f"D1 FAILED: prediction counts {counts}.")
    if len(all_predictions) != 1080:
        raise SystemExit(f"D1 FAILED: {len(all_predictions)} predictions, expected 1080.")
    print(f"predictions              : {len(all_predictions)} total, {counts}")

    keys = {
        (p["forecast_origin_month"], p["industry_id"], p["horizon_months"],
         p["variant_key"]) for p in all_predictions
    }
    if len(keys) != len(all_predictions):
        raise SystemExit("D1 FAILED: duplicate prediction keys.")

    # --- 5. metrics -----------------------------------------------------------
    bootstrap_config = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "evaluation_splits.yaml").read_text(encoding="utf-8")
    )["bootstrap"]

    results: dict[str, dict] = {}
    for horizon in (1, 3):
        primary_rows = [
            p for p in all_predictions
            if p["variant_key"] == "primary" and p["horizon_months"] == horizon
        ]
        model_metrics = DC.development_metrics(primary_rows, "predicted_score")
        benchmark_metrics = DC.development_metrics(
            primary_rows, "benchmark_prediction"
        )
        paired = DC.paired_origin_differences(
            primary_rows, "predicted_score", "benchmark_prediction"
        )
        intervals = DC.bootstrap_intervals(
            primary_rows, "predicted_score", "benchmark_prediction", bootstrap_config
        )
        status = DC.assign_evidence_status(
            model_metrics["macro_industry_mae"],
            benchmark_metrics["macro_industry_mae"],
            intervals["paired_macro_mae_difference_ci"],
        )
        sensitivities = {}
        for variant_key in ("timing_sensitivity", "structural_sensitivity"):
            rows = [
                p for p in all_predictions
                if p["variant_key"] == variant_key and p["horizon_months"] == horizon
            ]
            sensitivities[variant_key] = {
                "rows": len(rows),
                "metrics": DC.development_metrics(rows, "predicted_score"),
                "reused_primary_hyperparameters": True,
                "may_change_primary_status": False,
            }
        results[f"h{horizon}"] = {
            "horizon_months": horizon,
            "benchmark_name": BENCHMARKS[horizon],
            "model": model_metrics,
            "benchmark": benchmark_metrics,
            "model_high_stress": DC.high_stress_metrics(primary_rows, "predicted_score"),
            "benchmark_high_stress": DC.high_stress_metrics(
                primary_rows, "benchmark_prediction"
            ),
            "paired_origin_differences": paired,
            "bootstrap": intervals,
            "evidence": status,
            "sensitivity": sensitivities,
        }
        print(f"h={horizon}: model macro MAE {model_metrics['macro_industry_mae']:.4f} "
              f"vs benchmark {benchmark_metrics['macro_industry_mae']:.4f} "
              f"-> {status['evidence_status']}")

    # --- 6. artifacts ---------------------------------------------------------
    MODEL_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    predictions_path = MODEL_INPUT_DIR / "d1_development_predictions.parquet"
    prediction_frame = pd.DataFrame(all_predictions).sort_values(
        ["variant_key", "horizon_months", "forecast_origin_month", "industry_id"]
    )
    for column in ("predictor_names", "zero_variance_predictors_omitted",
                   "ineligible_predictors_omitted", "c2_lineage_checksums",
                   "c3_exposure_checksums"):
        prediction_frame[column] = prediction_frame[column].apply(
            lambda v: ";".join(map(str, v))
        )
    prediction_frame.to_parquet(predictions_path, index=False)

    assembly_output = {
        "task": "D1",
        "generated_at": generated_at,
        "label_rule": config["cutoffs"]["label_rule"],
        "historical_feature_rule": config["cutoffs"]["historical_feature_rule"],
        "first_complete_primary_origin": str(
            config["feature_history_gate"]["first_complete_primary_origin"]
        ),
        "rows": assembly_audit,
        "summary": {
            f"h{horizon}_at_{origin}": {
                "label_permitted_rows": sum(
                    a["label_permitted_origins"] for a in assembly_audit
                    if a["horizon_months"] == horizon
                    and a["forecast_origin_month"] == origin
                ),
                "feature_usable_rows": sum(
                    a["feature_usable_rows"] for a in assembly_audit
                    if a["horizon_months"] == horizon
                    and a["forecast_origin_month"] == origin
                ),
            }
            for horizon in (1, 3) for origin in (origins[0], origins[-1])
        },
        "calibrators": calibrator_audit,
        "content_checksum": content_checksum(assembly_audit),
    }
    ASSEMBLY_JSON.write_text(
        json.dumps(assembly_output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )

    results_output = {
        "task": "D1",
        "model_version": config["model_version"],
        "generated_at": generated_at,
        "split": "development",
        "development_origins": origins,
        "purge_origins_excluded": sorted(purge),
        "locked_test_origins_reserved": len(locked),
        "locked_test_outcomes_read": False,
        "approved_for_locked_test": False,
        "prediction_counts": counts,
        "total_model_predictions": len(all_predictions),
        "selections": selections,
        "results": results,
        "upstream_invariants_reproduced": {
            "b3": b3, "b4_origins": len(origins),
            "c4_rows": c4_audit["canonical_row_count"],
        },
        "outputs": {
            "predictions_parquet": str(
                predictions_path.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
            "predictions_sha256": hashlib.sha256(
                predictions_path.read_bytes()
            ).hexdigest(),
        },
        "content_checksum": content_checksum(all_predictions),
    }
    RESULTS_JSON.write_text(
        json.dumps(results_output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"content checksum         : {results_output['content_checksum'][:16]}")
    print(f"written                  : {RESULTS_JSON.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
