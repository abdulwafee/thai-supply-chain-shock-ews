"""Task D5 — preregistered development-only pooled fuel-oil interaction evaluation.

Evaluates the C11 pooled architecture on the fifteen registered development issue
months, with FO 600 and FO 1500 as co-equal separate variants, against the
operational D3 benchmarks reproduced from their registered formulas.

Two phases. Phase A freezes the protocol, writes it to disk and reads it back;
only then does the guarded target reader open. A target value read before that
checksum is verified raises and terminates the run.

DEVELOPMENT ONLY, EXPLORATORY. No channel is selected, no purge origin is
evaluated, the locked test stays closed, and no result approves a model feature
or supports a confirmatory claim.

    docs/d5_frozen_protocol.json
    docs/d5_modeling_protocol.md
    docs/d5_assembly_audit.{md,json}
    docs/d5_development_results.{md,json}
    data/model_input/d5_fuel_oil_{predictions,coefficients}.parquet  (git-ignored)
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.evaluation import issue_cluster_bootstrap as BS  # noqa: E402
from thai_supply_chain_ews.evaluation import metrics as MT  # noqa: E402
from thai_supply_chain_ews.evaluation.operational_availability import (  # noqa: E402
    target_available_month,
)
from thai_supply_chain_ews.evaluation.operational_contract import (  # noqa: E402
    load_operational_config,
    load_release_index,
    month_label,
)
from thai_supply_chain_ews.evaluation.operational_walk_forward import (  # noqa: E402
    run_operational_walk_forward,
)
from thai_supply_chain_ews.evaluation.splits import load_walk_forward_plan  # noqa: E402
from thai_supply_chain_ews.evaluation.walk_forward import load_b3_artifacts  # noqa: E402
from thai_supply_chain_ews.modeling import fuel_oil_pooled_panel as PP  # noqa: E402
from thai_supply_chain_ews.modeling import fuel_oil_prediction_lineage as LN  # noqa: E402
from thai_supply_chain_ews.modeling import fuel_oil_walk_forward as WF  # noqa: E402
from thai_supply_chain_ews.modeling.fixed_pooled_partial_ridge import (  # noqa: E402
    ESTIMATOR_NAME,
    FIXED_LAMBDA,
    clip_score,
    coefficient_checksum,
    fit_fixed_pooled_partial_ridge,
)
from thai_supply_chain_ews.modeling.operational_feature_target_assembly import (  # noqa: E402
    historical_benchmark_raw,
    operational_label_origins,
)
from thai_supply_chain_ews.targets.calibration import IndustryStressCalibrator  # noqa: E402
from thai_supply_chain_ews.targets.production_stress import load_target_config  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "d5_fuel_oil_interaction.yaml"
FROZEN_PROTOCOL = DOCS / "d5_frozen_protocol.json"
C11R1 = DOCS / "c11r1_governance_decision.json"
C11 = DOCS / "c11_architecture_decision.json"
C10 = DOCS / "c10_design_matrix_audit.json"
C9_PHASE_A = DOCS / "c9_sector093_exposure_decision.json"
C8_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"
PREDICTIONS_PATH = ROOT / "data" / "model_input" / "d5_fuel_oil_predictions.parquet"
COEFFICIENTS_PATH = ROOT / "data" / "model_input" / "d5_fuel_oil_coefficients.parquet"

CHANNEL_BY_VARIANT = {
    "fo600_direct_sector093": "eppo_fo600_channel",
    "fo1500_direct_sector093": "eppo_fo1500_channel",
}
PRIMARY_BENCHMARK = {
    1: "operational_persistence_latest_published",
    3: "operational_persistence_trailing_3m_max",
}
SECONDARY_COMPARATOR = "operational_no_contraction"


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Phase A — upstream reproduction and the protocol freeze
# ---------------------------------------------------------------------------
def reproduce_upstream(config) -> dict:
    c11r1 = load_json(C11R1)
    c11 = load_json(C11)
    c10 = load_json(C10)
    phase_a = load_json(C9_PHASE_A)
    granted = c11r1["d5_authorization"]["granted"]
    required = config["authorization"]["required"]
    up = config["upstream"]

    checks = {
        f"authorization.{name}": (granted[name], expected)
        for name, expected in required.items()
    }
    checks["c11r1_content_checksum"] = (
        c11r1["content_checksum"], config["authorization"]["c11r1_content_checksum"]
    )
    checks["c11r1_governance_checksum"] = (
        c11r1["governance_checksum"],
        config["authorization"]["c11r1_governance_checksum"],
    )
    checks["c11_content_checksum"] = (
        c11["content_checksum"], up["c11"]["content_checksum"]
    )
    checks["c11_decision_checksum"] = (
        c11["decision_checksum"], up["c11"]["decision_checksum"]
    )
    checks["c11_selected_architecture"] = (
        c11["selection"]["selected_architecture"], up["c11"]["selected_architecture"]
    )
    checks["c11_architecture_status"] = (
        c11r1["decision_status"]["architecture_decision_status"],
        up["c11"]["architecture_status"],
    )
    for name in ("source_block_rank", "interaction_block_rank",
                 "combined_source_and_interaction_rank", "full_design_rank"):
        checks[f"c11_{name}"] = (
            sorted({e[name] for e in c11["identification"]["observed"].values()}),
            [up["c11"][name]],
        )
    checks["c11_full_design_columns"] = (
        sorted({e["columns"] for e in c11["identification"]["observed"].values()}),
        [up["c11"]["full_design_columns"]],
    )
    checks["c11_candidate_b_is_distinct"] = (
        any(r["separate_conditioned_model_is_distinct_architecture"]
            for r in c11["candidate_b_equivalence"].values()),
        up["c11"]["candidate_b_is_distinct_architecture"],
    )
    checks["c10_content_checksum"] = (
        c10["content_checksum"], up["c10"]["content_checksum"]
    )
    checks["c10_diagnostic_contract_checksum"] = (
        c10["diagnostic_contract_checksum"],
        up["c10"]["diagnostic_contract_checksum"],
    )
    checks["c10_unique_issue_months"] = (
        sorted({e["unique_temporal_rows"] for e in c10["per_variant"].values()}),
        [up["c10"]["unique_issue_months"]],
    )
    checks["c10_eligible_feature_rows_per_variant"] = (
        sorted({e["fully_numeric_rows"] for e in c10["per_variant"].values()}),
        [up["c10"]["eligible_feature_rows_per_variant"]],
    )
    checks["c10_masked_ind_04_rows_per_variant"] = (
        sorted({e["fully_masked_rows"] for e in c10["per_variant"].values()}),
        [up["c10"]["fully_masked_ind_04_rows_per_variant"]],
    )
    checks["c9_phase_a_checksum"] = (
        phase_a["structural_decision_checksum"], up["c9"]["phase_a_checksum"]
    )
    checks["c9_eligible_industries"] = (
        phase_a["eligible_industries_per_channel"], up["c11"]["eligible_industries"]
    )
    ind_04 = next(
        r for r in phase_a["decisions"]
        if r["industry_id"] == "IND-04" and r["channel_id"] == "eppo_fo600_channel"
    )
    checks["c9_ind_04_eligible"] = (ind_04["eligible"], up["c11"]["ind_04_eligible"])
    checks["c9_ind_04_direction"] = (
        ind_04["direction_channel"], up["c11"]["ind_04_direction_channel"]
    )
    checks["c9_variants"] = (sorted(CHANNEL_BY_VARIANT), sorted(up["c9"]["variants"]))

    result = {
        name: {"actual": a, "expected": e, "reproduced": a == e}
        for name, (a, e) in checks.items()
    }
    failed = sorted(n for n, c in result.items() if not c["reproduced"])
    return {"all_reproduced": not failed, "failed": failed, "checks": result}


def freeze_protocol(config) -> tuple:
    """Write the frozen protocol, then read it back and hash what is on disk."""
    protocol = {
        "task": "D5",
        "protocol_version": config["protocol_version"],
        "model": config["model"],
        "estimator": config["estimator"],
        "preprocessing": config["preprocessing"],
        "training": config["training"],
        "evaluation_contract": config["evaluation_contract"],
        "benchmarks": config["benchmarks"],
        "predictions": config["predictions"],
        "ind_04": config["ind_04"],
        "channels": config["channels"],
        "metrics": config["metrics"],
        "event_safety": config["event_safety"],
        "bootstrap": config["bootstrap"],
        "decision_rules": config["decision_rules"],
        "guards": config["guards"],
        "purge_and_locked": config["purge_and_locked"],
        "scope": config["scope"],
    }
    text = json.dumps(protocol, ensure_ascii=False, indent=1, sort_keys=True,
                      default=str)
    FROZEN_PROTOCOL.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_PROTOCOL.write_text(text + "\n", encoding="utf-8")
    written = hashlib.sha256(text.encode("utf-8")).hexdigest()
    # Read it back from disk: an in-memory checksum proves nothing about the
    # artifact a later reader would see.
    reloaded = json.dumps(load_json(FROZEN_PROTOCOL), ensure_ascii=False, indent=1,
                          sort_keys=True, default=str)
    observed = hashlib.sha256(reloaded.encode("utf-8")).hexdigest()
    return protocol, written, observed


# ---------------------------------------------------------------------------
# Feature side
# ---------------------------------------------------------------------------
def load_source_by_month(c8_rows, channel_id) -> dict:
    """Reference month -> the five transformations, only where ALL five exist."""
    indexed = {}
    for row in c8_rows:
        if row["channel_id"] != channel_id:
            continue
        value = row["feature_value"]
        indexed.setdefault(str(row["reference_month"])[:7], {})[
            row["transformation_id"]
        ] = None if pd.isna(value) else float(value)
    complete = {}
    for month, values in indexed.items():
        ordered = [values.get(name) for name in PP.SOURCE_COLUMNS]
        if all(v is not None and np.isfinite(v) for v in ordered):
            complete[month] = ordered
    return complete


def build_origin(variant_id, horizon, outer_issue, source_by_month, exposure,
                 eligible, labels, stress_by_industry, calibrator,
                 benchmark_rows, reader, config, references):
    """Fit one (variant, horizon, outer issue) and produce its 12 predictions."""
    lag = PP.POLICY_LAG_MONTHS
    outer = month_label(outer_issue)
    reference_end = PP.shift_month(outer, -1)
    WF.assert_calibrator_cutoff(reference_end, outer)

    # --- training issues: three clocks must agree ---------------------------
    label_origins = operational_label_origins(labels, f"{outer}-01", horizon)
    first_stress_industry = sorted(stress_by_industry)[0]

    def benchmark_available(month):
        return historical_benchmark_raw(
            stress_by_industry[first_stress_industry], f"{month}-01", horizon
        ) is not None

    selection = WF.eligible_training_issues(
        [month_label(o) for o in label_origins], outer, set(source_by_month),
        benchmark_available, lag,
    )
    accepted = selection["accepted"]

    # --- the training panel, one row per (accepted issue, eligible industry) -
    labels_by_key = {
        (month_label(r["forecast_origin_month"]), r["industry_id"]): r
        for _, r in labels[labels["horizon_months"] == horizon].iterrows()
    }
    rows, residuals, source_by_issue = [], [], {}
    for issue in accepted:
        reference = PP.shift_month(issue, -lag)
        values = source_by_month[reference]
        source_by_issue[issue] = values
        for industry_id in eligible:
            label = labels_by_key.get((issue, industry_id))
            if label is None:
                raise WF.WalkForwardError(
                    f"training issue {issue} has no h={horizon} label for "
                    f"{industry_id}"
                )
            available = str(label["target_available_month"])[:7]
            WF.assert_label_available_by(available, outer, issue)
            benchmark_raw = historical_benchmark_raw(
                stress_by_industry[industry_id], f"{issue}-01", horizon
            )
            if benchmark_raw is None:
                raise WF.WalkForwardError(
                    f"training issue {issue} lost its benchmark for {industry_id}"
                )
            observed_score = float(
                calibrator.transform(industry_id, [float(label["target_raw_value"])])[0]
            )
            benchmark_score = float(
                calibrator.transform(industry_id, [benchmark_raw])[0]
            )
            rows.append({
                "issue_month": issue, "industry_id": industry_id,
                "reference_month": reference,
                **dict(zip(PP.SOURCE_COLUMNS, values, strict=True)),
            })
            residuals.append(observed_score - benchmark_score)

    scaler = PP.fit_source_scaler(source_by_issue, ddof=0)
    panel = PP.build_pooled_design(
        rows, eligible, scaler, exposure, variant_id, horizon, outer
    )
    fit = fit_fixed_pooled_partial_ridge(
        panel.matrix, np.array(residuals, dtype=float), panel.column_names,
        panel.blocks, lambda_value=FIXED_LAMBDA, loss_normalised_by_n=True,
        n_training_issue_months=len(accepted),
    )
    digest = coefficient_checksum(fit)

    # --- prediction at the outer issue --------------------------------------
    evaluation_reference = PP.shift_month(outer, -lag)
    if evaluation_reference not in source_by_month:
        raise WF.WalkForwardError(
            f"no complete fuel-oil row at {evaluation_reference} for outer issue "
            f"{outer}; the development window was expected to be gap-free"
        )
    PP.assert_feature_frozen_at_issue(outer, evaluation_reference)
    standardized = WF.standardize_row(source_by_month[evaluation_reference], scaler)
    scaled_exposure = exposure["scaled_exposure"]
    coefficients = np.asarray(fit.coefficients, dtype=float)
    index = {name: position for position, name in enumerate(fit.column_names)}

    predictions = []
    for record in benchmark_rows:
        industry_id = record["industry_id"]
        benchmark_score = float(record["predicted_score"])
        if industry_id == PP.IND_04:
            correction = 0.0
            source = LN.IND_04_PREDICTION_SOURCE
        else:
            design = np.zeros(len(fit.column_names), dtype=float)
            for position, name in enumerate(PP.SOURCE_COLUMNS):
                design[index[f"src__{name}"]] = standardized[position]
                design[index[f"int__e093z_x_{name}"]] = (
                    scaled_exposure[industry_id] * standardized[position]
                )
            design[index[f"fe__{industry_id}"]] = 1.0
            correction = float(design @ coefficients)
            source = "pooled_model"
        predicted, clipped = clip_score(benchmark_score + correction)
        key = (variant_id, int(horizon), outer, industry_id)
        # --- freeze, and only then read the observed target -----------------
        reader.freeze(key)
        observed = reader.read(key, record["observed_score"])
        predictions.append({
            "variant_id": variant_id, "horizon": int(horizon), "issue_month": outer,
            "industry_id": industry_id, "reference_month": evaluation_reference,
            "prediction_source": source,
            "benchmark_name": PRIMARY_BENCHMARK[int(horizon)],
            "benchmark_score": benchmark_score,
            "residual_correction": correction,
            "predicted_score": predicted, "clipped": bool(clipped),
            "observed_score": observed,
            "latest_available_stress_month": reference_end,
            "calibration_reference_end": reference_end,
            "target_window_start": str(record["target_window_start"])[:7],
            "target_window_end": str(record["target_window_end"])[:7],
            "target_available_month": str(record["target_available_month"])[:7],
            "training_issue_count": len(accepted),
            "training_row_count": panel.eligible_rows,
            "fitted_coefficient_checksum": digest,
        })

    return WF.OriginFit(
        variant_id=variant_id, horizon=int(horizon), outer_issue=outer,
        training_issue_months=tuple(accepted), training_rows=panel.eligible_rows,
        all_industry_training_rows=len(accepted) * (len(eligible) + 1),
        scaler=scaler, exposure=exposure, coefficients=fit.coefficient_map(),
        coefficient_checksum=digest,
        normal_equation_residual=fit.normal_equation_residual,
        predictions=predictions, exclusions=selection,
        calibration_reference_end=reference_end,
        latest_available_stress_month=reference_end,
    ), fit


def evaluate(model_frame, benchmark_frame, horizon, config, threshold=85.0):
    """Metrics, event safety and the paired interval for one comparison."""
    bootstrap = config["bootstrap"]
    block = int(bootstrap["block_length_by_horizon"][str(int(horizon))])
    model_matrix = BS.issue_month_matrix(model_frame)
    benchmark_matrix = BS.issue_month_matrix(benchmark_frame)
    interval = BS.paired_macro_mae_interval(
        model_matrix, benchmark_matrix, block,
        int(bootstrap["replications"]), int(bootstrap["random_seed"]),
        float(bootstrap["confidence_level"]),
    )

    def describe(frame):
        events = MT.high_stress_event_metrics(frame, threshold=threshold)
        observed = frame["observed_score"].to_numpy(float)
        predicted = frame["predicted_score"].to_numpy(float)
        positives = predicted >= threshold
        actual = observed >= threshold
        return {
            "rows": int(len(frame)),
            "macro_industry_mae": MT.macro_industry_mae(frame),
            "pooled_mae": MT.pooled_mae(frame),
            "macro_industry_rmse": MT.macro_industry_rmse(frame),
            "pooled_rmse": MT.pooled_rmse(frame),
            "median_absolute_error": MT.median_absolute_error(frame),
            "spearman_correlation": MT.spearman_correlation(observed, predicted),
            "per_industry_mae": MT.per_industry_mae(frame),
            "clipped_count": int(frame["clipped"].sum())
            if "clipped" in frame.columns else 0,
            "clipped_rate": float(frame["clipped"].mean())
            if "clipped" in frame.columns else 0.0,
            "observed_event_count": int(actual.sum()),
            "predicted_event_count": int(positives.sum()),
            "precision": events.get("precision"),
            "recall": events.get("recall"),
            "false_negatives": int((actual & ~positives).sum()),
            "false_positives": int((~actual & positives).sum()),
            "severe_observed_count": int((observed >= 95.0).sum()),
            "severe_predicted_count": int((predicted >= 95.0).sum()),
        }

    model = describe(model_frame)
    benchmark = describe(benchmark_frame)
    safety = LN.event_safety_status(
        model["false_negatives"], benchmark["false_negatives"]
    )
    mae_evidence = LN.classify_mae_evidence(
        interval["paired_ci_low"], interval["paired_ci_high"]
    )
    return {
        "model": model,
        "benchmark": benchmark,
        "mae_skill_relative_to_primary_benchmark": MT.mae_skill(
            model["macro_industry_mae"], benchmark["macro_industry_mae"]
        ),
        "paired_difference_model_minus_benchmark":
            interval["paired_difference_point"],
        "bootstrap": interval,
        "event_safety": {
            **safety,
            "precision_trade_off": {
                "model_precision": model["precision"],
                "benchmark_precision": benchmark["precision"],
                "model_false_positives": model["false_positives"],
                "benchmark_false_positives": benchmark["false_positives"],
            },
            "severe_stress_descriptive_only": {
                "model_predicted": model["severe_predicted_count"],
                "benchmark_predicted": benchmark["severe_predicted_count"],
                "observed": model["severe_observed_count"],
                "affects_any_decision": False,
            },
        },
        "mae_evidence": mae_evidence,
        "overall_status": LN.overall_status(
            mae_evidence, safety["event_safety_passed"]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    # ================= PHASE A =============================================
    invariants = reproduce_upstream(config)
    if not invariants["all_reproduced"]:
        raise SystemExit(
            f"D5 stops: upstream invariants did not reproduce: "
            f"{invariants['failed']}. Upstream artifacts are not repaired here."
        )
    protocol, expected_digest, observed_digest = freeze_protocol(config)
    reader = WF.GuardedTargetReader()
    reader.verify_protocol(expected_digest, observed_digest)

    # ================= PHASE B =============================================
    plan = load_walk_forward_plan()
    operational_config = load_operational_config()
    release_index = load_release_index()
    monthly, labels = load_b3_artifacts()
    target_config = load_target_config()

    origins = [month_label(o) for o in plan.development_origins]
    WF.assert_no_purge_or_locked_origin(
        origins,
        set(_month_range(config["purge_and_locked"]["purge_issue_months"])),
        set(_month_range(config["purge_and_locked"]["locked_issue_months"])),
    )

    baseline = run_operational_walk_forward(
        monthly=monthly, labels=labels, plan=plan, config=operational_config,
        release_index=release_index,
    )
    benchmarks = baseline.predictions
    benchmarks["issue_month"] = benchmarks["forecast_origin_month"].map(month_label)

    phase_a = load_json(C9_PHASE_A)
    exposures = {
        r["industry_id"]: r["direct_exposure"] for r in phase_a["decisions"]
        if r["channel_id"] == "eppo_fo600_channel"
    }
    eligible = sorted(
        r["industry_id"] for r in phase_a["decisions"]
        if r["channel_id"] == "eppo_fo600_channel" and r["eligible"]
    )
    exposure = PP.center_and_scale_exposure(exposures, eligible)
    c8_rows = pd.read_parquet(C8_PARQUET).to_dict("records")

    # The registered D3 rule, reused rather than re-implemented: a label becomes
    # available the month AFTER its target window ends.
    labels_with_availability = labels.copy()
    labels_with_availability["target_available_month"] = (
        labels_with_availability["target_window_end"].map(target_available_month)
    )

    c11r1 = load_json(C11R1)
    c11 = load_json(C11)
    c10 = load_json(C10)
    references_base = {
        "d5_protocol_checksum": expected_digest,
        "c11r1_authorization_checksum": c11r1["governance_checksum"],
        "c11_architecture_checksum": c11["decision_checksum"],
        "c10_design_matrix_checksum": c10["content_checksum"],
        "sector_093_exposure_and_centering_scaling_rule": {
            "raw_exposure": exposure["raw_exposure"],
            "mean": exposure["mean"],
            "structural_standard_deviation": exposure["structural_standard_deviation"],
            "centering_source": exposure["centering_source"],
        },
        "penalty_specification": {
            "estimator": ESTIMATOR_NAME, "lambda": FIXED_LAMBDA,
            "penalized_blocks": ["source", "interaction"],
            "loss_normalised_by_n": True,
        },
    }

    all_predictions, coefficient_rows, origin_audit = [], [], []
    for variant_id in sorted(CHANNEL_BY_VARIANT):
        source_by_month = load_source_by_month(
            c8_rows, CHANNEL_BY_VARIANT[variant_id]
        )
        for horizon in (1, 3):
            for outer_issue in plan.development_origins:
                outer = month_label(outer_issue)
                reference_end = PP.shift_month(outer, -1)
                # The stress table is keyed by ISO dates, so a YYYY-MM ceiling
                # would compare as GREATER than the month it means to include.
                reference_end_iso = f"{reference_end}-01"
                permitted = monthly[monthly["reference_month"] <= reference_end_iso]
                stress_by_industry = {}
                for industry_id, sub in permitted.groupby("industry_id",
                                                          observed=True):
                    series = dict(zip(
                        sub["reference_month"],
                        sub["mpi_adverse_yoy"].astype(float), strict=True,
                    ))
                    # Independent of the shared contract: no stress month may
                    # reach the issue month it is predicting from.
                    for month in series:
                        WF.assert_stress_month_permitted(month_label(month), outer)
                    stress_by_industry[industry_id] = series
                calibrator = IndustryStressCalibrator(
                    min_reference_observations=int(
                        operational_config["calibration"]["min_reference_observations"]
                    ),
                    version=target_config["calibration"]["calibrator_version"],
                ).fit(permitted, training_cutoff_month=reference_end_iso)

                rows = benchmarks[
                    (benchmarks["issue_month"] == outer)
                    & (benchmarks["horizon_months"] == horizon)
                    & (benchmarks["baseline_name"] == PRIMARY_BENCHMARK[horizon])
                ].to_dict("records")
                for record in rows:
                    record["target_available_month"] = month_label(
                        record["target_available_month"]
                    )
                fit_result, fit = build_origin(
                    variant_id, horizon, outer, source_by_month, exposure, eligible,
                    labels_with_availability, stress_by_industry, calibrator, rows,
                    reader, config, references_base,
                )
                all_predictions.extend(fit_result.predictions)
                origin_audit.append({
                    "variant_id": variant_id, "horizon": horizon,
                    "outer_issue": outer,
                    "unique_training_issues": len(fit_result.training_issue_months),
                    "eligible_training_rows": fit_result.training_rows,
                    "all_industry_training_rows":
                        fit_result.all_industry_training_rows,
                    "first_training_issue": fit_result.training_issue_months[0],
                    "last_training_issue": fit_result.training_issue_months[-1],
                    "excluded_no_complete_feature_row":
                        len(fit_result.exclusions["excluded_no_complete_feature_row"]),
                    "excluded_no_operational_benchmark_history":
                        len(fit_result.exclusions[
                            "excluded_no_operational_benchmark_history"]),
                    "calibration_reference_end": fit_result.calibration_reference_end,
                    "normal_equation_residual":
                        fit_result.normal_equation_residual,
                    "coefficient_checksum": fit_result.coefficient_checksum,
                    "scaler_unique_issue_months":
                        fit_result.scaler["unique_issue_month_count"],
                })
                for name, value in fit_result.coefficients.items():
                    coefficient_rows.append({
                        "variant_id": variant_id, "horizon": horizon,
                        "outer_issue": outer, "coefficient": name,
                        "block": dict(zip(fit.column_names, fit.blocks,
                                          strict=True))[name],
                        "value": float(value),
                        "penalized": name.startswith(("src__", "int__")),
                    })

    frame = pd.DataFrame(all_predictions)
    write_outputs(frame, coefficient_rows, origin_audit, benchmarks, config,
                   invariants, protocol, expected_digest, reader, exposure,
                   generated_at, references_base)


def _month_range(pair):
    """Inclusive YYYY-MM range. Local arithmetic: the shared helper takes dates."""
    start, end = str(pair[0])[:7], str(pair[1])[:7]
    months, cursor = [], start
    while cursor <= end:
        months.append(cursor)
        cursor = PP.shift_month(cursor, 1)
    return months


def write_outputs(frame, coefficient_rows, origin_audit, benchmarks, config,
                  invariants, protocol, protocol_digest, reader, exposure,
                  generated_at, references_base):
    """Lineage, metrics, tables and documents. Nothing is fitted from here."""
    scope = dict(config["scope"])

    # --- lineage for all 720 predictions ------------------------------------
    lineage_by_key, checksums = {}, []
    audit_by_key = {
        (r["variant_id"], r["horizon"], r["outer_issue"]): r for r in origin_audit
    }
    for record in frame.to_dict("records"):
        key = (record["variant_id"], int(record["horizon"]),
               record["issue_month"], record["industry_id"])
        audit = audit_by_key[(key[0], key[1], key[2])]
        references = {
            **references_base,
            "c9_conditioned_feature_row": (
                f"{record['variant_id']}|{record['reference_month']}|"
                f"{record['industry_id']}"
            ),
            "c8_transformation_lineage": (
                f"{CHANNEL_BY_VARIANT[record['variant_id']]}|"
                f"{record['reference_month']}|{len(PP.SOURCE_COLUMNS)}_transformations"
            ),
            "training_issue_keys": [
                audit["first_training_issue"], audit["last_training_issue"],
                audit["unique_training_issues"],
            ],
            "scaler_statistics": audit["scaler_unique_issue_months"],
            "fitted_coefficient_checksum": record["fitted_coefficient_checksum"],
            "benchmark_lineage": (
                f"{record['benchmark_name']}|{record['issue_month']}|"
                f"operational_contract_v1"
            ),
            "calibrator_cutoff": record["calibration_reference_end"],
            "label_availability_cutoff": record["target_available_month"],
            "prediction_clipping_state": (
                "clipped" if record["clipped"] else "within_bounds"
            ),
            "ind_04_passthrough_reason": (
                "direction_mixed_or_ambiguous_structural_exclusion"
                if record["industry_id"] == "IND-04" else None
            ),
        }
        lineage = LN.prediction_lineage_record(record, references)
        digest = LN.prediction_lineage_checksum(lineage)
        lineage_by_key[key] = digest
        checksums.append(digest)

    frame = frame.copy()
    frame["prediction_lineage_checksum"] = [
        lineage_by_key[(r["variant_id"], int(r["horizon"]), r["issue_month"],
                        r["industry_id"])]
        for r in frame.to_dict("records")
    ]

    # --- metrics, per variant and horizon -----------------------------------
    threshold = float(config["event_safety"]["high_stress_threshold"])
    benchmarks = benchmarks.copy()
    benchmarks["clipped"] = False
    results, eligible_only = {}, {}
    for variant_id in sorted(CHANNEL_BY_VARIANT):
        for horizon in (1, 3):
            model_frame = frame[
                (frame["variant_id"] == variant_id) & (frame["horizon"] == horizon)
            ].sort_values(["issue_month", "industry_id"]).reset_index(drop=True)
            benchmark_frame = benchmarks[
                (benchmarks["horizon_months"] == horizon)
                & (benchmarks["baseline_name"] == PRIMARY_BENCHMARK[horizon])
            ].sort_values(["issue_month", "industry_id"]).reset_index(drop=True)
            secondary_frame = benchmarks[
                (benchmarks["horizon_months"] == horizon)
                & (benchmarks["baseline_name"] == SECONDARY_COMPARATOR)
            ].sort_values(["issue_month", "industry_id"]).reset_index(drop=True)
            key = f"{variant_id}|h{horizon}"
            results[key] = {
                "variant_id": variant_id, "horizon": horizon,
                "primary_benchmark": PRIMARY_BENCHMARK[horizon],
                "panel": "full_twelve_industry",
                **evaluate(model_frame, benchmark_frame, horizon, config, threshold),
                "secondary_comparator": {
                    "name": SECONDARY_COMPARATOR,
                    **evaluate(model_frame, secondary_frame, horizon, config,
                               threshold),
                },
            }
            modeled = model_frame[model_frame["industry_id"] != "IND-04"]
            benchmark_eligible = benchmark_frame[
                benchmark_frame["industry_id"] != "IND-04"
            ]
            eligible_only[key] = {
                "industries": 11,
                "status": "secondary_structurally_preregistered",
                "may_replace_the_full_panel_result": False,
                **evaluate(modeled, benchmark_eligible, horizon, config, threshold),
            }

    # --- tables (git-ignored) -----------------------------------------------
    PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = frame.sort_values(
        ["variant_id", "horizon", "issue_month", "industry_id"], kind="mergesort"
    ).reset_index(drop=True)
    ordered.to_parquet(PREDICTIONS_PATH, index=False)
    pd.DataFrame(coefficient_rows).sort_values(
        ["variant_id", "horizon", "outer_issue", "coefficient"], kind="mergesort"
    ).reset_index(drop=True).to_parquet(COEFFICIENTS_PATH, index=False)

    # --- the audit and results payloads -------------------------------------
    counts = {
        "total_predictions": int(len(frame)),
        "distinct_keys": int(frame.groupby(
            ["variant_id", "horizon", "issue_month", "industry_id"]).ngroups),
        "pooled_model_predictions": int(
            (frame["prediction_source"] == "pooled_model").sum()),
        "ind_04_benchmark_passthrough": int(
            (frame["prediction_source"] != "pooled_model").sum()),
        "per_variant_horizon": {
            f"{v}|h{h}": int(len(frame[(frame['variant_id'] == v)
                                       & (frame['horizon'] == h)]))
            for v in sorted(CHANNEL_BY_VARIANT) for h in (1, 3)
        },
        "distinct_lineage_checksums": len(set(checksums)),
    }
    expected = config["predictions"]
    counts_reconciled = (
        counts["total_predictions"] == expected["total"]
        and counts["distinct_keys"] == expected["distinct_keys_required"]
        and counts["pooled_model_predictions"] == expected["pooled_model_predictions"]
        and counts["ind_04_benchmark_passthrough"] == expected["ind_04_benchmark_passthrough"]
        and all(v == expected["per_variant_horizon_total"]
                for v in counts["per_variant_horizon"].values())
        and counts["distinct_lineage_checksums"] == expected["total"]
    )
    if not counts_reconciled:
        raise SystemExit(f"D5 stops: prediction counts did not reconcile: {counts}")

    training_reconciled = []
    for row in origin_audit:
        expected_key = f"h{row['horizon']}_at_{row['outer_issue'].replace('-', '_')}"
        want = config["training"]["expected_counts"].get(expected_key)
        if want is None:
            continue
        training_reconciled.append({
            "variant_id": row["variant_id"], "horizon": row["horizon"],
            "outer_issue": row["outer_issue"],
            "unique_training_issues": row["unique_training_issues"],
            "expected_unique_training_issues": want["unique_training_issues"],
            "eligible_rows": row["eligible_training_rows"],
            "expected_eligible_rows": want["eligible_rows"],
            "all_industry_rows": row["all_industry_training_rows"],
            "expected_all_industry_rows": want["all_industry_rows"],
            "reconciled": (
                row["unique_training_issues"] == want["unique_training_issues"]
                and row["eligible_training_rows"] == want["eligible_rows"]
                and row["all_industry_training_rows"] == want["all_industry_rows"]
            ),
        })
    if not all(r["reconciled"] for r in training_reconciled):
        raise SystemExit("D5 stops: training counts did not reconcile")

    decision = {
        **scope,
        "channels_ranked_by_mae": False,
        "channels_ranked_by_event_metrics": False,
        "primary_channel_selected": False,
    }
    LN.assert_no_channel_promotion(decision)
    LN.assert_no_confirmatory_claim(decision)

    audit_payload = {
        "task": "D5",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "protocol_version": config["protocol_version"],
        "frozen_protocol_checksum": protocol_digest,
        "phase_a_frozen_before_any_target_read": True,
        "target_reader": reader.to_dict(),
        "upstream_invariants": invariants,
        "counts": {**counts, "reconciled": counts_reconciled,
                   "expected": expected},
        "training_reconciliation": training_reconciled,
        "origin_audit": origin_audit,
        "exposure": {
            "raw_exposure": exposure["raw_exposure"],
            "mean": exposure["mean"],
            "centered_exposure": exposure["centered_exposure"],
            "structural_standard_deviation":
                exposure["structural_standard_deviation"],
            "scaled_exposure": exposure["scaled_exposure"],
            "centering_universe": exposure["centering_universe"],
            "centering_source": exposure["centering_source"],
            "fitted_on_targets": exposure["fitted_on_targets"],
            "scaling_is_a_fixed_column_reparameterization":
                exposure["scaling_is_a_fixed_column_reparameterization"],
            "changes_the_c11_estimand": exposure["changes_the_c11_estimand"],
        },
        "evaluation_contract": config["evaluation_contract"],
        "benchmarks": config["benchmarks"],
        "ind_04": config["ind_04"],
        "channels": config["channels"],
        "guards": config["guards"],
        "purge_and_locked": config["purge_and_locked"],
        "lineage": {
            "fields": list(LN.LINEAGE_FIELDS),
            "predictions_with_a_checksum": len(checksums),
            "distinct_checksums": len(set(checksums)),
            "re_derived_independently": True,
        },
        "scope": scope,
    }
    audit_payload["content_checksum"] = LN.content_checksum(audit_payload)

    results_payload = {
        "task": "D5",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "protocol_version": config["protocol_version"],
        "frozen_protocol_checksum": protocol_digest,
        "model_name": config["model_name"],
        "estimator": config["estimator"],
        "decision_rules": config["decision_rules"],
        "metrics_contract": config["metrics"],
        "event_safety_contract": config["event_safety"],
        "bootstrap_contract": config["bootstrap"],
        "results": results,
        "eligible_only_diagnostic": eligible_only,
        "counts": counts,
        "authorization": config["authorization"]["required"],
        "scope": scope,
        "decision": {
            "channel_selected": False,
            "model_feature_approved": False,
            "locked_evaluation_authorized": False,
            "confirmatory_claim_made": False,
            "note": (
                "A development result of any sign selects no channel, approves no "
                "feature and opens no locked test. D5 holds none of those "
                "authorizations."
            ),
        },
    }
    results_payload["content_checksum"] = LN.content_checksum(results_payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    for name, payload in (("d5_assembly_audit.json", audit_payload),
                          ("d5_development_results.json", results_payload)):
        text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True,
                          default=str)
        (DOCS / name).write_text(text + "\n", encoding="utf-8")

    write_protocol_markdown(config, protocol_digest)
    write_audit_markdown(audit_payload)
    write_results_markdown(results_payload)

    print(json.dumps({
        "upstream_invariants_reproduced": invariants["all_reproduced"],
        "frozen_protocol_checksum": protocol_digest,
        "target_reads_before_prediction_freeze":
            reader.to_dict()["target_reads_before_prediction_freeze"],
        "predictions": counts["total_predictions"],
        "distinct_keys": counts["distinct_keys"],
        "modeled": counts["pooled_model_predictions"],
        "passthrough": counts["ind_04_benchmark_passthrough"],
        "distinct_lineage_checksums": counts["distinct_lineage_checksums"],
        "counts_reconciled": counts_reconciled,
        "training_reconciled": all(r["reconciled"] for r in training_reconciled),
        "macro_mae": {
            k: [round(v["model"]["macro_industry_mae"], 6),
                round(v["benchmark"]["macro_industry_mae"], 6)]
            for k, v in results.items()
        },
        "paired_ci": {
            k: [round(v["bootstrap"]["paired_ci_low"], 6),
                round(v["bootstrap"]["paired_ci_high"], 6)]
            for k, v in results.items()
        },
        "mae_evidence": {k: v["mae_evidence"] for k, v in results.items()},
        "event_safety_passed": {
            k: v["event_safety"]["event_safety_passed"] for k, v in results.items()
        },
        "overall_status": {k: v["overall_status"] for k, v in results.items()},
        "channel_selected": False,
        "model_feature_approved": False,
        "audit_content_checksum": audit_payload["content_checksum"],
        "results_content_checksum": results_payload["content_checksum"],
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def _fmt(value, digits=4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "nan"
        if abs(value) >= 1e6 or (value != 0 and abs(value) < 1e-4):
            return f"{value:.3e}"
        return f"{value:.{digits}f}"
    return str(value)


def write_protocol_markdown(config, protocol_digest: str) -> None:
    lines = [
        "# Task D5 - Pooled Fuel-Oil Interaction Modeling Protocol",
        "",
        f"*Config `{config['config_version']}`, protocol "
        f"`{config['protocol_version']}`.*",
        "",
        f"**Frozen protocol checksum:** `{protocol_digest}`",
        "",
        "Everything below was written, hashed and **read back from disk** before",
        "the guarded target reader opened. A target value requested before that",
        "checksum is verified raises and terminates the run, so the specification",
        "cannot still be editable while an outcome is visible.",
        "",
        "Authorized by C11-R1 as a **development-only exploratory** evaluation.",
        "Channel selection, purge metrics, confirmatory claims and the locked test",
        "are outside the grant and stay outside it whatever the numbers say.",
        "",
        "## The model",
        "",
        f"Residual: `{config['model']['residual_definition']}`",
        "",
        f"Fit: `{config['model']['equation']}`",
        "",
        f"Prediction: `{config['model']['final_prediction']}`",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("pooled_across_eligible_industries", "industry_specific",
                "horizons_fit_separately", "variants_fit_separately",
                "clip_lower", "clip_upper", "clipping_bounds_tuned",
                "estimand_changed_from_c11", "interpretation"):
        lines.append(f"| `{key}` | `{config['model'][key]}` |")

    lines += ["", "## The estimator", "", "| field | value |", "| --- | --- |"]
    for key, value in config["estimator"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "The loss is averaged by `n`. With an unnormalised sum the same `lambda`",
        "would be a weaker penalty on every larger training panel - and the panel",
        "grows from 231 rows to 385 across the walk-forward - so the specification",
        "would drift without a single number being edited. Industry fixed effects",
        "are unpenalised: shrinking an industry intercept toward zero shrinks it",
        "toward a stress score of zero, which is a strong claim rather than a",
        "neutral prior.",
        "",
        "## Preprocessing",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for block, entries in config["preprocessing"].items():
        if isinstance(entries, dict):
            for key, value in entries.items():
                lines.append(f"| `{block}.{key}` | `{value}` |")
        else:
            lines.append(f"| `{block}` | `{entries}` |")
    lines += [
        "",
        "The source scaler is fitted on the **unique** permitted training issue",
        "months. Fitting it on the stacked panel would weight one national series",
        "eleven times and report a sample size the data does not have. Exposure",
        "scaling is a fixed column reparameterisation for numerical conditioning:",
        "it multiplies the interaction column by a constant and divides theta by",
        "the same constant, so the C11 estimand is unchanged.",
        "",
        "## Training rules",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in config["training"].items():
        if key == "expected_counts":
            continue
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "| horizon and outer issue | unique training issues | eligible rows | "
        "all-industry rows |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, want in config["training"]["expected_counts"].items():
        lines.append(
            f"| `{key}` | {want['unique_training_issues']} | "
            f"{want['eligible_rows']} | {want['all_industry_rows']} |"
        )

    lines += [
        "",
        "## Evaluation contract and benchmarks",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in config["evaluation_contract"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += ["", "| benchmark | formula |", "| --- | --- |"]
    for name, formula in config["benchmarks"]["formulas"].items():
        lines.append(f"| `{name}` | `{formula}` |")
    lines += [
        "",
        f"Primary h=1: `{config['benchmarks']['primary']['1']}`. "
        f"Primary h=3: `{config['benchmarks']['primary']['3']}`. "
        f"Secondary comparator: `{config['benchmarks']['secondary_comparator']}`.",
        "",
        "Benchmarks are **reproduced from their registered formulas** by running",
        "the operational walk-forward, not copied from a D3 result artifact. No D3",
        "metric is a model input or an optimisation criterion.",
        "",
        "## Metrics, event safety and uncertainty",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in config["metrics"].items():
        lines.append(f"| `metrics.{key}` | `{value}` |")
    for key, value in config["event_safety"].items():
        lines.append(f"| `event_safety.{key}` | `{value}` |")
    for key, value in config["bootstrap"].items():
        lines.append(f"| `bootstrap.{key}` | `{value}` |")

    lines += ["", "## Decision rules", "", "| field | value |", "| --- | --- |"]
    for key, value in config["decision_rules"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines += ["", "## Guards", ""]
    for guard in config["guards"]:
        lines.append(f"* `{guard}`")
    lines += ["", "## Scope", "", "| field | value |", "| --- | --- |"]
    for key, value in config["scope"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.append("")
    (DOCS / "d5_modeling_protocol.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_audit_markdown(payload: dict) -> None:
    counts = payload["counts"]
    lines = [
        "# Task D5 - Assembly Audit",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        f"Frozen protocol `{payload['frozen_protocol_checksum']}`, verified from "
        "disk before the guarded target reader opened.",
        "",
        "## The two-phase boundary",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["target_reader"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "`target_reads_before_prediction_freeze` is the count that matters: every",
        "observed value was read only after its prediction was final.",
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
        lines.append(
            f"| `{name}` | `{_fmt(check['expected'])}` | `{_fmt(check['actual'])}` |"
        )

    lines += [
        "",
        "## Prediction counts",
        "",
        "| quantity | expected | observed |",
        "| --- | ---: | ---: |",
        f"| total predictions | {counts['expected']['total']} | "
        f"**{counts['total_predictions']}** |",
        f"| distinct canonical keys | "
        f"{counts['expected']['distinct_keys_required']} | "
        f"**{counts['distinct_keys']}** |",
        f"| pooled-model predictions | "
        f"{counts['expected']['pooled_model_predictions']} | "
        f"**{counts['pooled_model_predictions']}** |",
        f"| IND-04 benchmark passthrough | "
        f"{counts['expected']['ind_04_benchmark_passthrough']} | "
        f"**{counts['ind_04_benchmark_passthrough']}** |",
        f"| distinct lineage checksums | {counts['expected']['total']} | "
        f"**{counts['distinct_lineage_checksums']}** |",
        "",
        f"Reconciled: **{counts['reconciled']}**.",
        "",
        "## Training-count reconciliation",
        "",
        "| variant | h | outer issue | issues | expected | eligible rows | "
        "expected | all-industry | expected | ok |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["training_reconciliation"]:
        lines.append(
            f"| `{row['variant_id']}` | {row['horizon']} | `{row['outer_issue']}` | "
            f"{row['unique_training_issues']} | "
            f"{row['expected_unique_training_issues']} | {row['eligible_rows']} | "
            f"{row['expected_eligible_rows']} | {row['all_industry_rows']} | "
            f"{row['expected_all_industry_rows']} | {_flag(row['reconciled'])} |"
        )

    exclusions = payload["origin_audit"][0]
    lines += [
        "",
        "Exclusions are counted separately, because *not enough price history* and",
        "*not enough stress history* are different facts and one total would hide",
        "which is binding. At the first outer issue: "
        f"{exclusions['excluded_no_complete_feature_row']} issues lacked a complete "
        "five-transformation feature row, "
        f"{exclusions['excluded_no_operational_benchmark_history']} lacked "
        "operational benchmark history.",
        "",
        f"Maximum normal-equation residual across all fits: "
        f"{_fmt(max(r['normal_equation_residual'] for r in payload['origin_audit']))}.",
        "",
        "## Exposure preprocessing",
        "",
        "| industry | raw sector-093 exposure | centred | scaled |",
        "| --- | ---: | ---: | ---: |",
    ]
    exposure = payload["exposure"]
    for industry in sorted(exposure["raw_exposure"]):
        lines.append(
            f"| `{industry}` | {_fmt(exposure['raw_exposure'][industry], 6)} | "
            f"{_fmt(exposure['centered_exposure'][industry], 6)} | "
            f"{_fmt(exposure['scaled_exposure'][industry], 6)} |"
        )
    lines += [
        "",
        f"Mean {_fmt(exposure['mean'], 6)}, structural standard deviation "
        f"{_fmt(exposure['structural_standard_deviation'], 6)}, centring universe "
        f"`{exposure['centering_universe']}` from "
        f"`{exposure['centering_source']}`. Fitted on targets: "
        f"{_flag(exposure['fitted_on_targets'])}. Changes the C11 estimand: "
        f"{_flag(exposure['changes_the_c11_estimand'])}.",
        "",
        "## IND-04",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["ind_04"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines += [
        "",
        "## Lineage",
        "",
        f"{payload['lineage']['predictions_with_a_checksum']} predictions carry a "
        f"checksum, {payload['lineage']['distinct_checksums']} distinct, over "
        f"{len(payload['lineage']['fields'])} required references.",
        "",
    ]
    for field in payload["lineage"]["fields"]:
        lines.append(f"* `{field}`")
    lines += ["", "## Scope", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["scope"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += ["", f"Content checksum `{payload['content_checksum']}`.", ""]
    (DOCS / "d5_assembly_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_results_markdown(payload: dict) -> None:
    lines = [
        "# Task D5 - Development-Only Pooled Fuel-Oil Interaction Results",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        f"Frozen protocol `{payload['frozen_protocol_checksum']}`. Estimator "
        f"`{payload['model_name']}`, lambda "
        f"`{payload['estimator']['lambda']}`, no search of any kind.",
        "",
        "**Development-only and exploratory.** FO 600 and FO 1500 are reported",
        "side by side as co-equal variants. No channel is selected, no purge",
        "origin is evaluated, the locked test is closed, and no result here",
        "approves a model feature or supports a confirmatory claim.",
        "",
        "## Headline",
        "",
        "| variant | h | model macro MAE | benchmark macro MAE | paired delta | "
        "95% paired interval | MAE evidence | event safety | status |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for result in payload["results"].values():
        boot = result["bootstrap"]
        lines.append(
            f"| `{result['variant_id']}` | {result['horizon']} | "
            f"{_fmt(result['model']['macro_industry_mae'])} | "
            f"{_fmt(result['benchmark']['macro_industry_mae'])} | "
            f"{_fmt(result['paired_difference_model_minus_benchmark'])} | "
            f"[{_fmt(boot['paired_ci_low'])}, {_fmt(boot['paired_ci_high'])}] | "
            f"**{result['mae_evidence']}** | "
            f"{_flag(result['event_safety']['event_safety_passed'])} | "
            f"**{result['overall_status']}** |"
        )
    lines += [
        "",
        "The sign convention is `delta = MAE_model - MAE_benchmark`, so negative",
        "means the model is better. Support requires the **entire** interval below",
        "zero; a lower point estimate whose interval still touches zero is",
        "inconclusive, which on fifteen issue clusters is the common case.",
        "",
    ]

    for result in payload["results"].values():
        boot = result["bootstrap"]
        model, benchmark = result["model"], result["benchmark"]
        lines += [
            f"## `{result['variant_id']}` - horizon {result['horizon']}",
            "",
            f"Primary benchmark `{result['primary_benchmark']}`, full "
            f"{model['rows']}-row twelve-industry panel.",
            "",
            "| metric | model | benchmark |",
            "| --- | ---: | ---: |",
        ]
        for label, field in (
            ("macro-industry MAE (primary)", "macro_industry_mae"),
            ("pooled MAE", "pooled_mae"),
            ("macro RMSE", "macro_industry_rmse"),
            ("pooled RMSE", "pooled_rmse"),
            ("median absolute error", "median_absolute_error"),
            ("Spearman correlation", "spearman_correlation"),
            ("clipped count", "clipped_count"),
            ("clipped rate", "clipped_rate"),
        ):
            lines.append(
                f"| {label} | {_fmt(model[field])} | {_fmt(benchmark[field])} |"
            )
        lines += [
            f"| MAE skill vs primary benchmark | "
            f"{_fmt(result['mae_skill_relative_to_primary_benchmark'])} | - |",
            "",
            "### Event safety (high stress >= 85, threshold frozen)",
            "",
            "| quantity | model | benchmark |",
            "| --- | ---: | ---: |",
            f"| observed events | {model['observed_event_count']} | "
            f"{benchmark['observed_event_count']} |",
            f"| predicted events | {model['predicted_event_count']} | "
            f"{benchmark['predicted_event_count']} |",
            f"| precision | {_fmt(model['precision'])} | "
            f"{_fmt(benchmark['precision'])} |",
            f"| recall | {_fmt(model['recall'])} | {_fmt(benchmark['recall'])} |",
            f"| false negatives | **{model['false_negatives']}** | "
            f"**{benchmark['false_negatives']}** |",
            f"| false positives | {model['false_positives']} | "
            f"{benchmark['false_positives']} |",
            "",
            f"`event_safety_passed`: "
            f"{_flag(result['event_safety']['event_safety_passed'])} "
            "(model false negatives <= benchmark false negatives). Severe stress "
            ">= 95 is descriptive only: observed "
            f"{result['event_safety']['severe_stress_descriptive_only']['observed']}, "
            "model predicted "
            f"{result['event_safety']['severe_stress_descriptive_only']['model_predicted']}"
            ", benchmark predicted "
            f"{result['event_safety']['severe_stress_descriptive_only']['benchmark_predicted']}"
            ". It affects no decision.",
            "",
            "### Uncertainty",
            "",
            "| interval | low | point | high |",
            "| --- | ---: | ---: | ---: |",
            f"| model macro MAE | {_fmt(boot['model_ci_low'])} | "
            f"{_fmt(boot['model_macro_mae'])} | {_fmt(boot['model_ci_high'])} |",
            f"| benchmark macro MAE | {_fmt(boot['benchmark_ci_low'])} | "
            f"{_fmt(boot['benchmark_macro_mae'])} | "
            f"{_fmt(boot['benchmark_ci_high'])} |",
            f"| paired model - benchmark | {_fmt(boot['paired_ci_low'])} | "
            f"{_fmt(boot['paired_difference_point'])} | "
            f"{_fmt(boot['paired_ci_high'])} |",
            "",
            f"Method `{boot['method']}`, block length "
            f"{boot['block_length_months']}, {boot['replications']} replications, "
            f"seed {boot['seed']}, clustered by `{boot['cluster_unit']}` with all "
            "industries kept together. The model beats the benchmark in "
            f"**{boot['issue_months_model_beats_benchmark']} of "
            f"{boot['issue_months_total']}** issue months.",
            "",
            f"> {boot['resolution_note']}",
            "",
            "### Secondary comparator",
            "",
            f"Against `{result['secondary_comparator']['name']}`: model macro MAE "
            f"{_fmt(result['secondary_comparator']['model']['macro_industry_mae'])} "
            "versus "
            f"{_fmt(result['secondary_comparator']['benchmark']['macro_industry_mae'])}"
            f", paired interval "
            f"[{_fmt(result['secondary_comparator']['bootstrap']['paired_ci_low'])}, "
            f"{_fmt(result['secondary_comparator']['bootstrap']['paired_ci_high'])}]"
            f", evidence **{result['secondary_comparator']['mae_evidence']}**.",
            "",
        ]

    lines += [
        "## Eligible-only diagnostic (secondary, preregistered)",
        "",
        "Eleven modelled industries, IND-04 excluded. This is a **diagnostic** and",
        "cannot replace the full twelve-industry result above.",
        "",
        "| variant | h | model macro MAE | benchmark macro MAE | paired interval | "
        "evidence |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for key, result in payload["eligible_only_diagnostic"].items():
        boot = result["bootstrap"]
        variant, horizon = key.split("|h")
        lines.append(
            f"| `{variant}` | {horizon} | "
            f"{_fmt(result['model']['macro_industry_mae'])} | "
            f"{_fmt(result['benchmark']['macro_industry_mae'])} | "
            f"[{_fmt(boot['paired_ci_low'])}, {_fmt(boot['paired_ci_high'])}] | "
            f"{result['mae_evidence']} |"
        )

    lines += [
        "",
        "## Per-industry MAE, full panel",
        "",
        "| variant | h | industry | model | benchmark |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for result in payload["results"].values():
        for industry in sorted(result["model"]["per_industry_mae"]):
            lines.append(
                f"| `{result['variant_id']}` | {result['horizon']} | "
                f"`{industry}` | "
                f"{_fmt(result['model']['per_industry_mae'][industry])} | "
                f"{_fmt(result['benchmark']['per_industry_mae'][industry])} |"
            )

    lines += ["", "## Decision", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["decision"].items():
        if key == "note":
            continue
        lines.append(f"| `{key}` | {_flag(value)} |")
    lines += ["", "> " + payload["decision"]["note"], ""]

    lines += ["## Scope", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["scope"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += ["", f"Content checksum `{payload['content_checksum']}`.", ""]
    (DOCS / "d5_development_results.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
