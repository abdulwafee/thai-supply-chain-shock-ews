"""Task D4 — frozen-specification operational commodity model comparison.

Runs ONE frozen model (alpha 100.0, channel `none`, Brent + Rubber only) under
the D3 release-aware contract on the 15 development issue months, against the
selected D3 persistence benchmark and the no-contraction secondary comparator.

EXPLORATORY. The specification was frozen after D1's development results were
already observed, so no outcome here is confirmatory and none of it makes the
model locked-test eligible.

This script tunes nothing, searches no feature subset, changes no target
definition, splices no history, evaluates no purge origin, and cannot reach the
locked final test.

    docs/d4_operational_model_results.{md,json}
    data/model_input/d4_operational_model_predictions.parquet   (git-ignored)
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

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.evaluation.operational_contract import (  # noqa: E402
    load_operational_config,
    load_release_index,
    month_label,
)
from thai_supply_chain_ews.evaluation.operational_walk_forward import (  # noqa: E402
    run_operational_walk_forward,
)
from thai_supply_chain_ews.evaluation.splits import add_months, load_walk_forward_plan  # noqa: E402
from thai_supply_chain_ews.evaluation.walk_forward import load_b3_artifacts  # noqa: E402
from thai_supply_chain_ews.modeling import feature_target_assembly as FTA  # noqa: E402
from thai_supply_chain_ews.modeling import operational_model_comparison as CMP  # noqa: E402
from thai_supply_chain_ews.modeling.fixed_operational_ridge import (  # noqa: E402
    FIXED_ALPHA,
    FIXED_CHANNEL,
    MODEL_NAME,
    assert_no_excluded_commodity,
    clip_score,
    fit_fixed_operational_ridge,
)
from thai_supply_chain_ews.modeling.operational_feature_target_assembly import (  # noqa: E402
    OperationalAssemblyError,
    assemble_operational_training,
    operational_label_origins,
)
from thai_supply_chain_ews.modeling.operational_model_artifacts import (  # noqa: E402
    OPERATIONAL_MODEL_PREDICTION_COLUMNS,
    checksum_mapping,
    feature_snapshot_checksum,
)
from thai_supply_chain_ews.modeling.residual_ridge import ZeroVarianceError  # noqa: E402
from thai_supply_chain_ews.targets.calibration import (  # noqa: E402
    IndustryStressCalibrator,
    risk_level_for_score,
)
from thai_supply_chain_ews.targets.production_stress import load_target_config  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "d4_operational_model.yaml"
C4_PARQUET = ROOT / "data" / "features" / "c4_canonical_long.parquet"
C1_5_TIMING = DOCS / "c1_5_commodity_timing_audit.json"
PREDICTIONS_PATH = ROOT / "data" / "model_input" / "d4_operational_model_predictions.parquet"
NO_CONTRACTION = "operational_no_contraction"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def verify_upstream(config, d3_result, index_by_variant, labels, monthly):
    """Reproduce the D3, C4 and history-ceiling invariants D4 depends on."""
    d3 = config["d3_contract"]
    c4 = config["c4_contract"]
    ceiling = config["history_ceiling"]
    predictions = d3_result.predictions
    origins = [str(o) for o in d3_result.origins]

    findings = {
        "d3": {
            "issue_months": len(origins),
            "issue_months_expected": d3["expected_issue_months"],
            "development_start": month_label(origins[0]),
            "development_end": month_label(origins[-1]),
            "latest_stress_is_t_minus_1": bool(
                (
                    predictions["latest_available_stress_month"]
                    == predictions["forecast_origin_month"].map(lambda o: add_months(o, -1))
                ).all()
            ),
            "calibration_ends_at_t_minus_1": bool(
                (
                    predictions["calibration_reference_end"]
                    == predictions["forecast_origin_month"].map(lambda o: add_months(o, -1))
                ).all()
            ),
            "label_rule": d3["label_rule"],
            "benchmarks": {str(k): v for k, v in d3["benchmarks"].items()},
            "secondary_comparator": d3["secondary_comparator"],
            "locked_test_evaluated": False,
        },
        "c4": {
            "variants_present": sorted(index_by_variant),
            "primary_variant": c4["primary_variant"],
            "eligible_pairs": len(index_by_variant[c4["primary_variant"]].eligible_pairs),
            "eligible_pairs_expected": c4["eligible_pairs"],
            "ineligible_pairs": 48 - len(index_by_variant[c4["primary_variant"]].eligible_pairs),
            "ind06_rubber_eligible": (
                ("IND-06", "rubber_rss3_usd_kg")
                in index_by_variant[c4["primary_variant"]].eligible_pairs
            ),
            "forbidden_variant_absent": c4["forbidden_variant"] not in index_by_variant,
        },
        "history_ceiling": {
            "raw_stress_begins": str(monthly["reference_month"].min())[:7],
            "raw_stress_begins_expected": ceiling["raw_stress_begins"],
            "first_origin_with_24_observations": ceiling["first_origin_with_24_observations"],
            "compatible_pre_2022_history_available": False,
            "cross_base_splicing_permitted": False,
            "development_origin_extension_supported": False,
            "development_origin_count_ceiling": ceiling["development_origin_count_ceiling"],
            "new_feasibility_test_performed": False,
        },
    }

    problems = []
    if findings["d3"]["issue_months"] != d3["expected_issue_months"]:
        problems.append("issue month count")
    if not findings["d3"]["latest_stress_is_t_minus_1"]:
        problems.append("latest stress month")
    if not findings["d3"]["calibration_ends_at_t_minus_1"]:
        problems.append("calibration reference end")
    if findings["c4"]["eligible_pairs"] != c4["eligible_pairs"]:
        problems.append("C4 eligible pairs")
    if findings["c4"]["ind06_rubber_eligible"]:
        problems.append("IND-06 rubber eligibility")
    if not findings["c4"]["forbidden_variant_absent"]:
        problems.append("forbidden lag1+total variant present")
    if findings["history_ceiling"]["raw_stress_begins"] != ceiling["raw_stress_begins"]:
        problems.append("raw stress start")
    if len(origins) != ceiling["development_origin_count_ceiling"]:
        problems.append("origin ceiling")
    if problems:
        raise OperationalAssemblyError(f"upstream invariants failed: {problems}")
    findings["all_reproduced"] = True
    return findings


def verify_timing_day_availability(config, release_index, origins):
    """Day-level check for the lag-1 timing sensitivity.

    The lag-1 variant claims a feature for reference month *t-1* is usable at
    issue month *t*. That is only true if the Pink Sheet issue carrying *t-1*
    was published on or before the verified OIE issue date. Where the day-level
    evidence is missing, the origin is marked UNAVAILABLE rather than assumed.
    """
    with open(C1_5_TIMING, encoding="utf-8") as handle:
        timing = json.load(handle)
    published = {row["reference_month"]: row for row in timing["publication_timing"]}

    available, unavailable, detail = [], [], []
    for origin in origins:
        issue_date = release_index[add_months(origin, -1)]["release_date"]
        reference = add_months(origin, -1)
        record = published.get(reference)
        verified = (
            record is not None
            and record.get("availability_status") == "verified_from_archived_issue"
            and record.get("first_seen_issue_date")
        )
        if verified and record["first_seen_issue_date"] <= issue_date:
            available.append(origin)
            state = "available"
        else:
            unavailable.append(origin)
            state = "unavailable_unverified_day_level_publication"
        detail.append(
            {
                "forecast_origin_month": origin,
                "d3_issue_date": issue_date,
                "commodity_reference_month": reference,
                "commodity_publication_date": (
                    record.get("first_seen_issue_date") if record else None
                ),
                "calendar_delay_days": record.get("calendar_delay_days") if record else None,
                "availability_status": record.get("availability_status") if record else None,
                "state": state,
            }
        )
    return {
        "rule": config["timing_sensitivity_day_check"]["rule"],
        "available_origins": available,
        "unavailable_origins": unavailable,
        "fully_available": not unavailable,
        "imputed": False,
        "substituted_with_primary": False,
        "per_origin": detail,
    }


def run_variant(
    variant,
    index,
    d3_predictions,
    labels_by_key,
    labels,
    monthly,
    plan,
    contracts,
    config,
    permitted_origins_cache,
    allowed_origins=None,
):
    """Fit and predict the frozen model across origins, horizons, industries."""
    target_config = load_target_config()
    risk_levels = target_config["risk_levels"]
    d3_config = config["d3_contract"]
    benchmarks = {int(k): v for k, v in d3_config["benchmarks"].items()}
    min_reference = 24
    calibrator_version = target_config["calibration"]["calibrator_version"]
    industries = sorted(index.industries)

    rows, diagnostics = [], []
    for origin in [str(o) for o in plan.development_origins]:
        if allowed_origins is not None and origin not in allowed_origins:
            continue
        contract = contracts[origin]
        reference_end = contract.calibration_reference_end

        permitted_stress = monthly[monthly["reference_month"] <= reference_end]
        calibrator = IndustryStressCalibrator(
            min_reference_observations=min_reference, version=calibrator_version
        ).fit(permitted_stress, training_cutoff_month=reference_end)

        stress_by_industry = {
            industry: dict(
                zip(sub["reference_month"], sub["mpi_adverse_yoy"].astype(float), strict=True)
            )
            for industry, sub in permitted_stress.groupby("industry_id", observed=True)
        }

        for horizon in plan.horizons:
            horizon = int(horizon)
            cache_key = (origin, horizon)
            if cache_key not in permitted_origins_cache:
                permitted_origins_cache[cache_key] = operational_label_origins(
                    labels, origin, horizon
                )
            permitted_origins = permitted_origins_cache[cache_key]
            benchmark_name = benchmarks[horizon]

            for industry in industries:
                training = assemble_operational_training(
                    index=index,
                    labels_by_key=labels_by_key,
                    permitted_origins=permitted_origins,
                    industry_id=industry,
                    horizon=horizon,
                    outer_origin=origin,
                    calibrator=calibrator,
                    stress_by_month=stress_by_industry.get(industry, {}),
                    non_ferrous_channel=FIXED_CHANNEL,
                )
                # Registered D1 precedent (nested_walk_forward): when the
                # design matrix is degenerate the model cannot be fitted, the
                # residual is 0.0 and the prediction reduces to the benchmark.
                # This is NOT a tuning choice -- for several industries BOTH
                # Brent and Rubber DIRECT exposures are structurally zero, so
                # every conditioned predictor is a constant and the X-only
                # zero-variance rule removes all of them.
                try:
                    model = fit_fixed_operational_ridge(
                        industry_id=industry,
                        horizon=horizon,
                        predictor_names=training.predictor_names,
                        training_matrix=training.matrix,
                        residuals=training.residuals,
                        omitted_ineligible=training.omitted_ineligible,
                    )
                    model_quality = "ok"
                except ZeroVarianceError:
                    model = None
                    model_quality = "degenerate_all_predictors_constant_benchmark_only"

                evaluation = FTA.features_as_of(
                    index, origin, industry, non_ferrous_channel=FIXED_CHANNEL
                )
                if not evaluation:
                    raise OperationalAssemblyError(
                        f"no evaluation feature row for {industry} at {origin}"
                    )
                assert_no_excluded_commodity(
                    evaluation["predictor_names"], f"{industry} evaluation row"
                )
                values = dict(
                    zip(evaluation["predictor_names"], evaluation["values"], strict=True)
                )

                # --- benchmark from D3, then residual, then clip -------------
                benchmark_rows = d3_predictions[
                    (d3_predictions["forecast_origin_month"] == origin)
                    & (d3_predictions["horizon_months"] == horizon)
                    & (d3_predictions["industry_id"] == industry)
                    & (d3_predictions["baseline_name"] == benchmark_name)
                ]
                if len(benchmark_rows) != 1:
                    raise OperationalAssemblyError(
                        f"expected one D3 benchmark row for {industry} {origin} h={horizon}"
                    )
                benchmark_row = benchmark_rows.iloc[0]
                benchmark_score = float(benchmark_row["predicted_score"])

                residual = float(model.predict(values)) if model is not None else 0.0
                unclipped = benchmark_score + residual
                final, clipped = clip_score(unclipped)

                # --- only now is the evaluation target read ------------------
                observed_raw = float(benchmark_row["observed_raw_target"])
                observed_score = float(calibrator.transform(industry, observed_raw)[0])

                reference = calibrator.reference_for(industry)
                rows.append(
                    {
                        "forecast_origin_month": origin,
                        "forecast_issue_date": contract.forecast_issue_date,
                        "latest_available_stress_month": contract.latest_available_stress_month,
                        "industry_id": industry,
                        "horizon_months": horizon,
                        "model_name": MODEL_NAME,
                        "feature_variant": variant,
                        "d3_benchmark_name": benchmark_name,
                        "d3_benchmark_prediction": benchmark_score,
                        "predicted_residual": residual,
                        "model_quality": model_quality,
                        "unclipped_prediction": float(unclipped),
                        "predicted_score": float(final),
                        "clipped": bool(clipped),
                        "observed_raw_target": observed_raw,
                        "observed_score": observed_score,
                        "observed_risk_level": risk_level_for_score(observed_score, risk_levels),
                        "calibration_reference_end": reference.end_month,
                        "calibration_fingerprint": reference.fingerprint,
                        "max_training_target_window_end": (
                            training.max_training_target_window_end
                        ),
                        "max_training_target_available_month": (
                            training.max_training_target_available_month
                        ),
                        "label_permitted_rows": training.label_permitted_rows,
                        "feature_usable_rows": training.feature_usable_rows,
                        "predictor_names": (
                            ";".join(model.retained_predictors) if model else ""
                        ),
                        "predictor_count": (
                            len(model.retained_predictors) if model else 0
                        ),
                        "omitted_ineligible_predictors": ";".join(training.omitted_ineligible),
                        "omitted_zero_variance_predictors": (
                            ";".join(model.omitted_zero_variance) if model
                            else ";".join(training.predictor_names)
                        ),
                        "fixed_alpha": FIXED_ALPHA,
                        "fixed_nonferrous_channel": FIXED_CHANNEL,
                        "aluminum_predictors_present": False,
                        "copper_predictors_present": False,
                        "shared_io_sector_107_used": False,
                        "scaler_checksum": model.scaler.checksum() if model else None,
                        "model_checksum": model.checksum() if model else None,
                        "feature_snapshot_checksum": feature_snapshot_checksum(evaluation),
                        "c2_lineage_checksums": checksum_mapping(
                            evaluation.get("c2_lineage_checksums")
                        ),
                        "c3_exposure_checksums": checksum_mapping(
                            evaluation.get("c3_exposure_checksums")
                        ),
                        "operational_contract_version": "operational_contract_v1",
                        "model_version": config["model_version"],
                        "split_name": plan.block_for_origin(origin),
                        "exploratory_development_evaluation": True,
                        "confirmatory_result": False,
                        "locked_test_accessed": False,
                    }
                )
                if industry == industries[0]:
                    diagnostics.append(
                        {
                            "variant": variant,
                            "forecast_origin_month": origin,
                            "horizon": horizon,
                            "label_permitted_rows": training.label_permitted_rows,
                            "feature_usable_rows": training.feature_usable_rows,
                            "excluded_feature_origins": list(training.excluded_origins),
                            "excluded_feature_reason": training.excluded_reason,
                            "excluded_benchmark_origins": list(
                                training.excluded_benchmark_origins
                            ),
                            "excluded_benchmark_reason": training.excluded_benchmark_reason,
                        }
                    )

    frame = pd.DataFrame.from_records(rows, columns=OPERATIONAL_MODEL_PREDICTION_COLUMNS)
    frame = frame.sort_values(
        ["feature_variant", "horizon_months", "industry_id", "forecast_origin_month"],
        kind="mergesort",
    ).reset_index(drop=True)
    return frame, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    config = load_config()
    operational_config = load_operational_config()
    plan = load_walk_forward_plan()
    release_index = load_release_index()
    monthly, labels = load_b3_artifacts()

    d3_result = run_operational_walk_forward(
        monthly=monthly, labels=labels, plan=plan, config=operational_config
    )
    d3_predictions = d3_result.predictions

    feature_rows = pd.read_parquet(C4_PARQUET).to_dict("records")
    variants = [config["variants"]["primary"]] + list(config["variants"]["sensitivities"])
    index_by_variant = {v: FTA.build_feature_index(feature_rows, v) for v in variants}

    invariants = verify_upstream(config, d3_result, index_by_variant, labels, monthly)

    origins = [str(o) for o in plan.development_origins]
    timing_availability = verify_timing_day_availability(config, release_index, origins)

    labels_by_key = {
        (str(r["forecast_origin_month"]), r["industry_id"], int(r["horizon_months"])): r
        for r in labels.to_dict("records")
    }

    cache = {}
    frames, diagnostics = {}, []
    for variant in variants:
        allowed = None
        if variant == "timing_sensitivity_direct_lag1":
            allowed = set(timing_availability["available_origins"])
        frame, diag = run_variant(
            variant=variant,
            index=index_by_variant[variant],
            d3_predictions=d3_predictions,
            labels_by_key=labels_by_key,
            labels=labels,
            monthly=monthly,
            plan=plan,
            contracts=d3_result.contracts,
            config=config,
            permitted_origins_cache=cache,
            allowed_origins=allowed,
        )
        frames[variant] = frame
        diagnostics.extend(diag)

    all_predictions = pd.concat(list(frames.values()), ignore_index=True)
    all_predictions = all_predictions.sort_values(
        ["feature_variant", "horizon_months", "industry_id", "forecast_origin_month"],
        kind="mergesort",
    ).reset_index(drop=True)
    _assert_counts(frames, config, timing_availability)

    evaluation = evaluate(frames, d3_predictions, config)

    payload = {
        "task": "D4",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "model_version": config["model_version"],
        "model_name": MODEL_NAME,
        "evidence_framing": config["evidence_framing"],
        "frozen_specification": {
            "alpha": FIXED_ALPHA,
            "nonferrous_channel": FIXED_CHANNEL,
            "fit_intercept": True,
            "allowed_commodities": config["commodities"]["allowed"],
            "excluded_commodities": config["commodities"]["excluded"],
            "aluminum_predictors_present": False,
            "copper_predictors_present": False,
            "shared_io_sector_107_used": False,
            "hyperparameter_search": False,
            "inner_cross_validation": False,
            "model_averaging": False,
            "outcome_based_feature_selection": False,
        },
        "upstream_invariants": invariants,
        "timing_sensitivity_availability": timing_availability,
        "training_diagnostics": diagnostics,
        "training_count_reconciliation": _reconcile_training_counts(
            diagnostics, config
        ),
        "degenerate_design_summary": _degenerate_summary(all_predictions),
        "prediction_counts": {
            "total": int(len(all_predictions)),
            "by_variant_horizon": {
                f"{v}__h{h}": int(
                    ((frames[v]["horizon_months"] == h)).sum()
                )
                for v in variants
                for h in (1, 3)
            },
        },
        "evaluation": evaluation,
        "safety": config["safety"],
    }
    payload["content_checksum"] = hashlib.sha256(
        json.dumps(_stable(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    if not args.print_only:
        PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        all_predictions.to_parquet(PREDICTIONS_PATH, index=False)
        payload["outputs"] = {
            "predictions_path": str(PREDICTIONS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "predictions_sha256": hashlib.sha256(
                pd.util.hash_pandas_object(all_predictions, index=False).values.tobytes()
            ).hexdigest(),
        }
        _write_json(DOCS / "d4_operational_model_results.json", payload)
        _write_markdown(DOCS / "d4_operational_model_results.md", payload)

    _print_summary(payload)
    return 0


def _assert_counts(frames, config, timing_availability):
    expected = config["expected_prediction_counts"]
    per = int(expected["per_variant_per_horizon"])
    for variant, frame in frames.items():
        for horizon in (1, 3):
            subset = frame[frame["horizon_months"] == horizon]
            if variant == "timing_sensitivity_direct_lag1":
                allowed = len(timing_availability["available_origins"]) * 12
                if len(subset) != allowed:
                    raise OperationalAssemblyError(
                        f"{variant} h={horizon}: expected {allowed} rows, got {len(subset)}"
                    )
                continue
            if len(subset) != per:
                raise OperationalAssemblyError(
                    f"{variant} h={horizon}: expected {per} rows, got {len(subset)}"
                )
        key = ["forecast_origin_month", "industry_id", "horizon_months", "feature_variant"]
        if frame.duplicated(subset=key).any():
            raise OperationalAssemblyError(f"{variant}: duplicate prediction keys")


def evaluate(frames, d3_predictions, config):
    primary_variant = config["variants"]["primary"]
    threshold = float(config["metrics"]["high_stress"]["threshold"])
    severe = float(config["metrics"]["high_stress"]["severe_threshold"])
    benchmarks = {int(k): v for k, v in config["d3_contract"]["benchmarks"].items()}

    out = {}
    for horizon in (1, 3):
        model_frame = frames[primary_variant]
        model_frame = model_frame[model_frame["horizon_months"] == horizon]
        benchmark_frame = d3_predictions[
            (d3_predictions["horizon_months"] == horizon)
            & (d3_predictions["baseline_name"] == benchmarks[horizon])
        ]
        secondary_frame = d3_predictions[
            (d3_predictions["horizon_months"] == horizon)
            & (d3_predictions["baseline_name"] == NO_CONTRACTION)
        ]

        model_metrics = CMP.describe_frame(model_frame, threshold, severe)
        benchmark_metrics = CMP.describe_frame(benchmark_frame, threshold, severe)
        secondary_metrics = CMP.describe_frame(secondary_frame, threshold, severe)

        vs_benchmark = CMP.compare_against_comparators(
            model_frame, benchmark_frame, config, seed_offset=horizon
        )
        vs_secondary = CMP.compare_against_comparators(
            model_frame, secondary_frame, config, seed_offset=horizon + 10
        )
        model_ci = __import__(
            "thai_supply_chain_ews.evaluation.bootstrap", fromlist=["x"]
        ).bootstrap_macro_mae_ci(
            __import__(
                "thai_supply_chain_ews.evaluation.bootstrap", fromlist=["x"]
            ).build_error_matrix(model_frame),
            config["bootstrap"],
            seed_offset=horizon,
        )

        mae_status = CMP.assign_mae_evidence(
            model_metrics["macro_industry_mae"],
            benchmark_metrics["macro_industry_mae"],
            vs_benchmark["paired_difference_model_minus_comparator"],
        )
        event_status = CMP.assign_event_safety(
            model_metrics["high_stress"]["false_negative"],
            benchmark_metrics["high_stress"]["false_negative"],
        )
        decision = CMP.advancement_decision(mae_status, event_status)

        sensitivities = {}
        for variant in config["variants"]["sensitivities"]:
            frame = frames[variant]
            frame = frame[frame["horizon_months"] == horizon]
            if frame.empty:
                sensitivities[variant] = {"rows": 0, "status": "no_available_origins"}
                continue
            sensitivities[variant] = {
                **CMP.describe_frame(frame, threshold, severe),
                "reported_separately": True,
                "may_change_primary_status": False,
                "origins_covered": sorted({str(o) for o in frame["forecast_origin_month"]}),
            }

        out[str(horizon)] = {
            "benchmark_name": benchmarks[horizon],
            "model": model_metrics,
            "model_macro_mae_ci": model_ci,
            "operational_persistence": benchmark_metrics,
            "operational_no_contraction": secondary_metrics,
            "vs_operational_persistence": vs_benchmark,
            "vs_no_contraction": vs_secondary,
            "mae_evidence_status": mae_status,
            "event_safety_status": event_status,
            "decision": decision,
            "sensitivities": sensitivities,
        }
    return out


def _reconcile_training_counts(diagnostics, config):
    """Compare produced counts against the brief, per industry x 12."""
    produced = {}
    for row in diagnostics:
        if row["variant"] != config["variants"]["primary"]:
            continue
        key = (int(row["horizon"]), row["forecast_origin_month"][:7])
        produced[key] = row

    out = []
    for spec in config["expected_training_counts"]:
        key = (int(spec["horizon"]), spec["outer_origin"])
        row = produced.get(key)
        if row is None:
            continue
        label_total = row["label_permitted_rows"] * 12
        usable_total = row["feature_usable_rows"] * 12
        out.append(
            {
                "horizon": key[0],
                "outer_origin": key[1],
                "label_permitted_expected": spec["label_permitted"],
                "label_permitted_actual": label_total,
                "label_permitted_matches": label_total == spec["label_permitted"],
                "feature_usable_expected": spec["feature_usable"],
                "feature_usable_actual": usable_total,
                "feature_usable_matches": usable_total == spec["feature_usable"],
                "excluded_feature_origins": row["excluded_feature_origins"],
                "excluded_benchmark_origins": row["excluded_benchmark_origins"],
                "deviation_reason": (
                    None
                    if usable_total == spec["feature_usable"]
                    else (
                        "The h=3 operational benchmark reads max(S_{u-3}, S_{u-2}, "
                        "S_{u-1}). At u=2022-03 that window reaches 2021-12, before "
                        "B3's stress series begins in 2022-01, so no achievable "
                        "benchmark exists at that origin and no residual can be "
                        "defined against one. The brief's expected count accounts "
                        "only for the feature-history gate and does not anticipate "
                        "this additional operational-benchmark boundary. The row is "
                        "excluded and reported, not imputed."
                    )
                ),
            }
        )
    return out


def _degenerate_summary(predictions):
    """Industries whose every conditioned predictor is a structural constant."""
    out = {}
    for variant, frame in predictions.groupby("feature_variant", observed=True):
        degenerate = frame[frame["model_quality"] != "ok"]
        out[str(variant)] = {
            "rows_total": int(len(frame)),
            "rows_degenerate": int(len(degenerate)),
            "degenerate_industries": sorted(degenerate["industry_id"].unique().tolist()),
            "fitted_industries": sorted(
                frame[frame["model_quality"] == "ok"]["industry_id"].unique().tolist()
            ),
            "meaning": (
                "For a degenerate industry every eligible conditioned predictor is a "
                "structural constant (the exposure coefficient is zero), so the "
                "X-only zero-variance rule removes all of them, the residual is 0.0 "
                "and the prediction equals the D3 benchmark exactly."
            ),
        }
    return out

def _stable(payload):
    clone = dict(payload)
    clone.pop("generated_at_utc", None)
    clone.pop("content_checksum", None)
    clone.pop("outputs", None)
    return clone


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_markdown(path, payload):
    lines = []
    add = lines.append
    add("# Task D4 — Frozen-Specification Operational Model Results")
    add("")
    add(f"*Generated {payload['generated_at_utc']}. Model `{payload['model_version']}`.*")
    add("")
    add("> **Exploratory, not confirmatory.** The specification was frozen *after* D1's")
    add("> development results were observed, so nothing here is a confirmatory test and")
    add("> no outcome makes the model locked-test eligible.")
    add("")
    add("## Frozen specification")
    add("")
    spec = payload["frozen_specification"]
    add(f"alpha **{spec['alpha']}**, channel **`{spec['nonferrous_channel']}`**, "
        f"commodities **{', '.join(spec['allowed_commodities'])}**.")
    add(f"Aluminum and Copper excluded (`shared_io_sector_107_used: "
        f"{spec['shared_io_sector_107_used']}`). No hyperparameter search, no inner")
    add("validation, no model averaging, no outcome-based feature selection.")
    add("")
    add("## Prediction counts")
    add("")
    for key, value in sorted(payload["prediction_counts"]["by_variant_horizon"].items()):
        add(f"* `{key}`: {value}")
    add(f"* **total**: {payload['prediction_counts']['total']}")
    add("")
    for horizon in ("1", "3"):
        block = payload["evaluation"][horizon]
        add(f"## h={horizon}")
        add("")
        add("| series | macro MAE | pooled MAE | macro RMSE | median AE |"
            " Spearman | FN | clipped |")
        add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for label, key in (
            ("**model**", "model"),
            (f"`{block['benchmark_name']}`", "operational_persistence"),
            ("`operational_no_contraction`", "operational_no_contraction"),
        ):
            m = block[key]
            add(f"| {label} | {m['macro_industry_mae']:.4f} | {m['pooled_mae']:.4f} | "
                f"{m['macro_industry_rmse']:.4f} | {m['median_absolute_error']:.4f} | "
                f"{m['pooled_spearman']:.4f} | {m['high_stress']['false_negative']} | "
                f"{m['clipped_prediction_count']} |")
        add("")
        ci = block["model_macro_mae_ci"]
        add(f"Model macro MAE 95% CI: **[{ci['ci_low']:.4f}, {ci['ci_high']:.4f}]**.")
        add("")
        for label, key in (("operational persistence", "vs_operational_persistence"),
                           ("no-contraction", "vs_no_contraction")):
            cmp_block = block[key]
            paired = cmp_block["paired_difference_model_minus_comparator"]
            add(f"* vs {label}: paired **{paired['point_estimate']:+.4f}** "
                f"CI [{paired['ci_low']:.4f}, {paired['ci_high']:.4f}] "
                f"({paired['verdict']}); skill {cmp_block['mae_skill']:+.4f}")
        add("")
        add(f"**MAE evidence: `{block['mae_evidence_status']}`.**")
        add(f"**Event safety: `{block['event_safety_status']}`** "
            f"(model {block['model']['high_stress']['false_negative']} FN vs benchmark "
            f"{block['operational_persistence']['high_stress']['false_negative']} FN).")
        add(f"**Development candidate supported: "
            f"`{block['decision']['development_candidate_supported']}`.**")
        add("")
        add("### Sensitivities — reported separately, cannot change the primary status")
        add("")
        add("| variant | rows | macro MAE | FN |")
        add("| --- | ---: | ---: | ---: |")
        for variant, block2 in sorted(block["sensitivities"].items()):
            if block2.get("rows"):
                add(f"| `{variant}` | {block2['rows']} | "
                    f"{block2['macro_industry_mae']:.4f} | "
                    f"{block2['high_stress']['false_negative']} |")
            else:
                add(f"| `{variant}` | 0 | — | — |")
        add("")
    add("## Safety")
    add("")
    for key, value in payload["safety"].items():
        add(f"* `{key}`: `{value}`")
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _print_summary(payload):
    print("D4 operational model complete.")
    print("  model            :", payload["model_name"], payload["model_version"])
    print("  exploratory      :", payload["evidence_framing"]["exploratory_development_evaluation"])
    print("  predictions      :", payload["prediction_counts"]["total"])
    timing = payload["timing_sensitivity_availability"]
    print("  timing day-check :", "fully available" if timing["fully_available"]
          else f"{len(timing['unavailable_origins'])} unavailable")
    for horizon in ("1", "3"):
        block = payload["evaluation"][horizon]
        print(f"  h={horizon}: model {block['model']['macro_industry_mae']:.4f} vs "
              f"{block['benchmark_name']} "
              f"{block['operational_persistence']['macro_industry_mae']:.4f} | "
              f"FN {block['model']['high_stress']['false_negative']}/"
              f"{block['operational_persistence']['high_stress']['false_negative']} | "
              f"{block['mae_evidence_status']} | {block['event_safety_status']} | "
              f"advance={block['decision']['development_candidate_supported']}")
    print("  locked test      :", payload["safety"]["locked_test_accessed"])
    print("  checksum         :", payload["content_checksum"])


if __name__ == "__main__":
    raise SystemExit(main())
