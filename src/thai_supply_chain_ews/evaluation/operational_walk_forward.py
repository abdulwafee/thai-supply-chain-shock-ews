"""Release-aware operational walk-forward (Task D3).

The B4 runner is left untouched and still reproduces its historical numbers.
This is a **separate, versioned** runner implementing the operational contract:
at forecast issue month *t* the newest published stress month is *t-1*, so the
calibrator, the baselines and the training labels all stop one month earlier
than they did in B4.

Three cutoffs move together, and they are deliberately enforced in three
different places so they cannot silently drift into one another:

1. **stress map** — built from ``reference_month <= t-1``, then asserted.
2. **calibrator** — fitted with ``training_cutoff_month = t-1``, then frozen.
3. **training labels** — ``target_available_month <= t``, then asserted.

The evaluation target for origin *t* is resolved **only after** every prediction
at that origin is frozen, and it is never a member of the training set.

There is no argument, environment variable, or alternate path through this
module that evaluates a locked origin. Locked months are rejected by
``build_origin_contracts`` before any data is read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from thai_supply_chain_ews.evaluation.baselines import BaselineContext
from thai_supply_chain_ews.evaluation.operational_availability import (
    assert_labels_available,
    assert_no_future_stress,
    available_training_labels,
    summarize_availability,
    target_available_month,
)
from thai_supply_chain_ews.evaluation.operational_baselines import (
    OPERATIONAL_BASELINES_BY_HORIZON,
    predict_operational_baseline,
)
from thai_supply_chain_ews.evaluation.operational_contract import (
    CurrentMonthStressError,
    build_origin_contracts,
    load_operational_config,
    load_release_index,
    locked_month_set,
    month_label,
    purge_month_set,
    release_inventory_checksum,
)
from thai_supply_chain_ews.evaluation.splits import add_months, load_walk_forward_plan
from thai_supply_chain_ews.evaluation.walk_forward import (
    load_b3_artifacts,
    validate_b3_invariants,
)
from thai_supply_chain_ews.targets.calibration import (
    IndustryStressCalibrator,
    risk_level_for_score,
)
from thai_supply_chain_ews.targets.production_stress import load_target_config

__all__ = [
    "OPERATIONAL_PREDICTION_COLUMNS",
    "OperationalWalkForwardResult",
    "run_operational_walk_forward",
]

OPERATIONAL_PREDICTION_COLUMNS = [
    "forecast_origin_month",
    "forecast_issue_date",
    "latest_available_stress_month",
    "industry_id",
    "horizon_months",
    "baseline_name",
    "predicted_raw_value",
    "predicted_score",
    "observed_raw_target",
    "observed_score",
    "observed_risk_level",
    "target_window_start",
    "target_window_end",
    "target_available_month",
    "calibration_reference_start",
    "calibration_reference_end",
    "calibration_observation_count",
    "calibration_fingerprint",
    "max_training_target_window_end",
    "max_training_target_available_month",
    "training_label_count",
    "release_inventory_checksum",
    "target_definition_version",
    "operational_contract_version",
    "evaluation_harness_version",
    "split_name",
    "latest_vintage_target_values",
    "point_in_time_target_values_supported",
    "locked_test_accessed",
]


@dataclass
class OperationalWalkForwardResult:
    predictions: pd.DataFrame
    contracts: dict
    availability: list
    b3_findings: dict
    plan: object
    origins: list
    calibrator_fingerprints: dict = field(default_factory=dict)
    dataset_flags: dict = field(default_factory=dict)


def run_operational_walk_forward(
    monthly=None,
    labels=None,
    plan=None,
    config=None,
    release_index=None,
):
    """Generate operational development predictions, one issue month at a time."""
    plan = plan or load_walk_forward_plan()
    config = config or load_operational_config()
    release_index = release_index if release_index is not None else load_release_index()
    if monthly is None or labels is None:
        monthly, labels = load_b3_artifacts()
    b3_findings = validate_b3_invariants(monthly, labels)

    origins = list(plan.development_origins)
    # Belt and braces: the harness guard, then the contract guard.
    plan.assert_not_locked_test(origins)
    reserved = locked_month_set(config) | purge_month_set(config)
    intruders = [o for o in origins if month_label(o) in reserved]
    if intruders:
        raise CurrentMonthStressError(
            f"development origins overlap reserved months: {intruders}"
        )

    contracts = build_origin_contracts(origins, config, release_index, plan=plan)

    target_config = load_target_config()
    risk_levels = target_config["risk_levels"]
    calibration_config = config["calibration"]
    min_reference = int(calibration_config["min_reference_observations"])
    calibrator_version = target_config["calibration"]["calibrator_version"]
    contract_version = config["operational_contract_version"]
    inventory_checksum = release_inventory_checksum()

    industries = sorted(monthly["industry_id"].unique().tolist())
    rows, fingerprints, availability = [], {}, []

    for origin in origins:
        contract = contracts[str(origin)]
        reference_end = contract.calibration_reference_end

        # --- 1. stress published by the issue date: reference_month <= t-1 ---
        permitted_stress = monthly[monthly["reference_month"] <= reference_end]
        if permitted_stress.empty:
            raise CurrentMonthStressError(f"no published stress at issue month {origin}")
        latest_seen = permitted_stress["reference_month"].max()
        contract.assert_stress_month_permitted(latest_seen)
        if reference_end >= origin:
            raise CurrentMonthStressError(
                f"calibration reference end {reference_end} is not before issue month {origin}"
            )

        # --- 2. fresh calibrator per origin, cut at t-1, then frozen ---------
        calibrator = IndustryStressCalibrator(
            min_reference_observations=min_reference, version=calibrator_version
        ).fit(permitted_stress, training_cutoff_month=reference_end)
        fingerprints[str(origin)] = ";".join(
            calibrator.reference_for(i).fingerprint for i in calibrator.fitted_industries
        )

        stress_by_industry = {}
        for industry_id, sub in permitted_stress.groupby("industry_id", observed=True):
            series = dict(
                zip(sub["reference_month"], sub["mpi_adverse_yoy"].astype(float), strict=True)
            )
            assert_no_future_stress(series, reference_end)
            stress_by_industry[industry_id] = series

        for horizon in plan.horizons:
            horizon_labels = labels[labels["horizon_months"] == horizon]

            # --- 3. labels PUBLISHED by the issue month ----------------------
            permitted_labels = available_training_labels(horizon_labels, origin)
            assert_labels_available(permitted_labels, origin)
            summary = summarize_availability(horizon_labels, origin, horizon)
            availability.append(summary)

            training_scores = {}
            for industry_id, sub in permitted_labels.groupby("industry_id", observed=True):
                training_scores[industry_id] = calibrator.transform(
                    industry_id, sub["target_raw_value"].to_numpy(float)
                ).tolist()

            # --- 4. the evaluation label, resolved AFTER the calibrator ------
            current = horizon_labels[horizon_labels["forecast_origin_month"] == origin]
            observed_by_industry = dict(
                zip(current["industry_id"], current["target_raw_value"].astype(float), strict=True)
            )
            window_by_industry = dict(
                zip(
                    current["industry_id"],
                    zip(current["target_window_start"], current["target_window_end"], strict=True),
                    strict=True,
                )
            )
            # The current label must never have been admitted as training data.
            if not current.empty:
                current_available = target_available_month(
                    current["target_window_end"].iloc[0]
                )
                if current_available <= origin:
                    raise CurrentMonthStressError(
                        f"evaluation label at origin {origin} (h={horizon}) is "
                        f"available {current_available}, i.e. at or before the issue "
                        "month; it would also be a training label"
                    )

            for industry_id in industries:
                if industry_id not in observed_by_industry:
                    continue
                context = BaselineContext(
                    origin=origin,
                    industry_id=industry_id,
                    horizon=int(horizon),
                    calibrator=calibrator,
                    raw_stress_by_month=stress_by_industry.get(industry_id, {}),
                    training_scores=training_scores.get(industry_id, []),
                )
                reference = calibrator.reference_for(industry_id)
                window_start, window_end = window_by_industry[industry_id]

                for name in OPERATIONAL_BASELINES_BY_HORIZON[int(horizon)]:
                    # --- 5. predict, and freeze ---------------------------
                    predicted_raw, predicted_score = predict_operational_baseline(name, context)
                    # --- 6. only now touch the observed future target -----
                    observed_raw = observed_by_industry[industry_id]
                    observed_score = float(calibrator.transform(industry_id, observed_raw)[0])
                    rows.append(
                        {
                            "forecast_origin_month": origin,
                            "forecast_issue_date": contract.forecast_issue_date,
                            "latest_available_stress_month": contract.latest_available_stress_month,
                            "industry_id": industry_id,
                            "horizon_months": int(horizon),
                            "baseline_name": name,
                            "predicted_raw_value": predicted_raw,
                            "predicted_score": float(predicted_score),
                            "observed_raw_target": float(observed_raw),
                            "observed_score": observed_score,
                            "observed_risk_level": risk_level_for_score(
                                observed_score, risk_levels
                            ),
                            "target_window_start": window_start,
                            "target_window_end": window_end,
                            "target_available_month": target_available_month(window_end),
                            "calibration_reference_start": reference.start_month,
                            "calibration_reference_end": reference.end_month,
                            "calibration_observation_count": reference.n,
                            "calibration_fingerprint": reference.fingerprint,
                            "max_training_target_window_end": summary.max_target_window_end,
                            "max_training_target_available_month": (
                                summary.max_target_available_month
                            ),
                            "training_label_count": int(
                                len(training_scores.get(industry_id, []))
                            ),
                            "release_inventory_checksum": inventory_checksum,
                            "target_definition_version": target_config[
                                "target_definition_version"
                            ],
                            "operational_contract_version": contract_version,
                            "evaluation_harness_version": plan.harness_version,
                            "split_name": plan.block_for_origin(origin),
                            "latest_vintage_target_values": True,
                            "point_in_time_target_values_supported": False,
                            "locked_test_accessed": False,
                        }
                    )

    predictions = pd.DataFrame.from_records(rows, columns=OPERATIONAL_PREDICTION_COLUMNS)
    predictions = predictions.sort_values(
        ["horizon_months", "baseline_name", "industry_id", "forecast_origin_month"],
        kind="mergesort",
    ).reset_index(drop=True)

    _assert_operational_expectations(predictions, plan, config)

    dataset_flags = {
        "evaluation_framing": config["evaluation_framing"],
        "release_timing_aware": True,
        "latest_vintage_target_values": True,
        "point_in_time_target_values": False,
        "fully_real_time_backtest": False,
        "same_month_stress_used": False,
        "locked_test_accessed": False,
    }
    return OperationalWalkForwardResult(
        predictions=predictions,
        contracts=contracts,
        availability=availability,
        b3_findings=b3_findings,
        plan=plan,
        origins=origins,
        calibrator_fingerprints=fingerprints,
        dataset_flags=dataset_flags,
    )


def _assert_operational_expectations(predictions, plan, config) -> None:
    expected = config["expected_prediction_counts"]
    reserved = locked_month_set(config) | purge_month_set(config)

    seen = {month_label(m) for m in predictions["forecast_origin_month"].unique()}
    overlap = sorted(seen & reserved)
    if overlap:
        raise CurrentMonthStressError(f"predictions contain reserved months: {overlap}")

    development = config["split"]["development"]
    if len(seen) != int(development["expected_issue_months"]):
        raise ValueError(
            f"expected {development['expected_issue_months']} issue months, "
            f"produced {len(seen)}"
        )

    for horizon, key in ((1, "horizon_1"), (3, "horizon_3")):
        spec = expected[key]
        subset = predictions[predictions["horizon_months"] == horizon]
        if len(subset) != int(spec["total"]):
            raise ValueError(
                f"h={horizon}: expected {spec['total']} rows, produced {len(subset)}"
            )
        names = sorted(subset["baseline_name"].unique())
        if len(names) != int(spec["baselines"]):
            raise ValueError(
                f"h={horizon}: expected {spec['baselines']} baselines, "
                f"found {len(names)} ({names})"
            )
        for name in names:
            rows = subset[subset["baseline_name"] == name]
            if len(rows) != int(spec["rows_per_baseline"]):
                raise ValueError(
                    f"h={horizon} {name}: expected "
                    f"{spec['rows_per_baseline']} rows, produced {len(rows)}"
                )
            per_origin = rows.groupby("forecast_origin_month").size()
            bad = per_origin[per_origin != int(expected["per_issue_month_horizon_baseline"])]
            if not bad.empty:
                raise ValueError(
                    f"h={horizon} {name}: origins without "
                    f"{expected['per_issue_month_horizon_baseline']} industries: "
                    f"{bad.to_dict()}"
                )

    if len(predictions) != int(expected["combined"]):
        raise ValueError(
            f"expected {expected['combined']} combined rows, "
            f"produced {len(predictions)}"
        )

    key = expected["unique_key"]
    if predictions.duplicated(subset=key).any():
        raise ValueError(f"duplicate prediction keys on {key}")

    # Every prediction must have been issued after its own release, and must
    # never reference a stress month at or after its issue month.
    late = predictions[
        predictions["latest_available_stress_month"] >= predictions["forecast_origin_month"]
    ]
    if not late.empty:
        raise CurrentMonthStressError(
            f"{len(late)} prediction(s) claim a latest available stress month at or "
            "after the issue month"
        )
    for origin, issue_date in zip(
        predictions["forecast_origin_month"], predictions["forecast_issue_date"], strict=False
    ):
        if not (origin <= issue_date <= add_months(origin, 1)):
            raise ValueError(
                f"issue date {issue_date} is not inside issue month {origin}"
            )
