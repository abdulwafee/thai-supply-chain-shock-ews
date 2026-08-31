"""Walk-forward evaluation harness (Task B4).

Produces honest out-of-fold development predictions by rebuilding the calibrator
and every baseline's information set independently at each monthly forecast
origin. There is deliberately no code path that fits one calibrator across the
whole development period.

Two rules do the real leakage work here:

* **Calibration cutoff**: `stress_month <= origin`. The origin month's own
  observation is allowed, because the historical-evaluation contract assumes the
  value at the forecast origin is in hand when the forecast is made.
* **Training-label cutoff**: `target_window_end <= origin`, enforced per horizon.
  Filtering on the label's ORIGIN date instead would admit 3-month labels whose
  window reaches past t — i.e. the very outcome being predicted.

The locked final test period is never evaluated here. `run_walk_forward` refuses
origins inside it, and the runner exposes no flag to override that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from thai_supply_chain_ews.evaluation.baselines import (
    BaselineContext,
    load_baseline_config,
    predict_baseline,
)
from thai_supply_chain_ews.evaluation.splits import (
    WalkForwardPlan,
    load_walk_forward_plan,
)
from thai_supply_chain_ews.targets.calibration import (
    IndustryStressCalibrator,
    risk_level_for_score,
)
from thai_supply_chain_ews.targets.production_stress import (
    B3InvariantError,
    load_target_config,
)

__all__ = [
    "B4InvariantError",
    "FeatureAvailabilityError",
    "PREDICTION_COLUMNS",
    "WalkForwardResult",
    "assert_feature_availability",
    "load_b3_artifacts",
    "run_walk_forward",
    "validate_b3_invariants",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONTHLY_STRESS_PATH = PROJECT_ROOT / "data" / "targets" / "production_stress_month.parquet"
LABELS_PATH = PROJECT_ROOT / "data" / "targets" / "forecast_target_raw.parquet"

B4InvariantError = B3InvariantError

PREDICTION_COLUMNS = [
    "forecast_origin_month",
    "industry_id",
    "horizon_months",
    "baseline_name",
    "predicted_raw_value",
    "predicted_score",
    "observed_raw_target",
    "observed_score",
    "observed_risk_level",
    "calibration_reference_start",
    "calibration_reference_end",
    "calibration_observation_count",
    "calibration_fingerprint",
    "max_training_target_window_end",
    "training_label_count",
    "split_name",
    "target_definition_version",
    "evaluation_harness_version",
]


class FeatureAvailabilityError(ValueError):
    """A feature carries an availability month after the forecast origin.

    NOTE ON WHAT THIS CAN AND CANNOT CATCH: this is a MONTH-BASED
    LATEST-VINTAGE rule, not a real-time release-date rule. Verified publication
    dates do not exist for these sources, so a value that was published late
    within its own reference month is indistinguishable from one published on
    time. The rule prevents obvious future-dated features; it does not make the
    evaluation a real-time backtest.
    """


def assert_feature_availability(
    frame: pd.DataFrame,
    origin_column: str = "forecast_origin_month",
    availability_column: str = "feature_available_month",
) -> None:
    """Reusable contract for every future feature table.

    Violations raise. Rows are never silently dropped — a silently shrinking
    feature table is how a leakage bug becomes a quiet accuracy gain.
    """
    if availability_column not in frame.columns:
        raise FeatureAvailabilityError(
            f"Feature table has no `{availability_column}` column; availability cannot be "
            "verified, and an unverifiable feature table must not be used."
        )
    late = frame[
        frame[availability_column].astype(str) > frame[origin_column].astype(str)
    ]
    if not late.empty:
        first = late.iloc[0]
        raise FeatureAvailabilityError(
            f"{len(late)} feature row(s) have {availability_column} after "
            f"{origin_column} (first: {first[availability_column]} > {first[origin_column]}). "
            "Refusing to proceed; violating rows are never dropped silently."
        )


def load_b3_artifacts() -> tuple[pd.DataFrame, pd.DataFrame]:
    for path in (MONTHLY_STRESS_PATH, LABELS_PATH):
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} not found — run scripts/run_b3_target_build.py first."
            )
    monthly = pd.read_parquet(MONTHLY_STRESS_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    monthly["reference_month"] = monthly["reference_month"].astype(str)
    for column in (
        "forecast_origin_month", "target_window_start", "target_window_end",
        "target_peak_month",
    ):
        labels[column] = labels[column].astype(str)
    return monthly, labels


def validate_b3_invariants(monthly: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """Re-derive B3's facts from the artifacts. Stop on any material failure."""
    findings: dict = {}
    failures: list[str] = []

    months = sorted(monthly["reference_month"].unique().tolist())
    findings["monthly_rows"] = int(len(monthly))
    findings["monthly_industries"] = int(monthly["industry_id"].nunique())
    findings["monthly_months_per_industry"] = sorted(
        monthly.groupby("industry_id", observed=True).size().unique().tolist()
    )
    findings["monthly_first"] = months[0] if months else None
    findings["monthly_last"] = months[-1] if months else None

    expectations = [
        ("monthly_rows", 636), ("monthly_industries", 12),
        ("monthly_first", "2022-01-01"), ("monthly_last", "2026-05-01"),
    ]
    for key, want in expectations:
        if findings[key] != want:
            failures.append(f"{key}: expected {want}, found {findings[key]}")
    if findings["monthly_months_per_industry"] != [53]:
        failures.append(
            f"months per industry: expected [53], found {findings['monthly_months_per_industry']}"
        )

    horizon_expectations = {
        1: {"rows": 624, "per_industry": 52, "first": "2022-01-01", "last": "2026-04-01"},
        3: {"rows": 600, "per_industry": 50, "first": "2022-01-01", "last": "2026-02-01"},
    }
    findings["horizons"] = {}
    for horizon, want in horizon_expectations.items():
        sub = labels[labels["horizon_months"] == horizon]
        origins = sorted(sub["forecast_origin_month"].unique().tolist())
        observed = {
            "rows": int(len(sub)),
            "per_industry": sorted(
                sub.groupby("industry_id", observed=True).size().unique().tolist()
            ),
            "first": origins[0] if origins else None,
            "last": origins[-1] if origins else None,
        }
        findings["horizons"][str(horizon)] = observed
        if observed["rows"] != want["rows"]:
            failures.append(f"h={horizon} rows: expected {want['rows']}, found {observed['rows']}")
        if observed["per_industry"] != [want["per_industry"]]:
            failures.append(
                f"h={horizon} per-industry origins: expected [{want['per_industry']}], "
                f"found {observed['per_industry']}"
            )
        if observed["first"] != want["first"] or observed["last"] != want["last"]:
            failures.append(
                f"h={horizon} origin range: expected {want['first']}..{want['last']}, "
                f"found {observed['first']}..{observed['last']}"
            )

    findings["combined_rows"] = int(len(labels))
    if findings["combined_rows"] != 1224:
        failures.append(f"combined rows: expected 1224, found {findings['combined_rows']}")

    excluded = "2026-06-01"
    touches = [
        column
        for column in ("target_window_start", "target_window_end", "target_peak_month")
        if excluded in set(labels[column])
    ]
    findings["uses_2026_06"] = touches
    if touches:
        failures.append(f"2026-06 appears in {touches}")
    if excluded in set(monthly["reference_month"]):
        failures.append("2026-06 appears in the monthly stress table")

    findings["duplicate_keys"] = int(
        labels.duplicated(subset=["forecast_origin_month", "industry_id", "horizon_months"]).sum()
    )
    if findings["duplicate_keys"]:
        failures.append(f"{findings['duplicate_keys']} duplicate industry-origin-horizon keys")

    versions = sorted(labels["target_definition_version"].unique().tolist())
    findings["target_definition_versions"] = versions
    target_config = load_target_config()
    if versions != [target_config["target_definition_version"]]:
        failures.append(f"unexpected target_definition_version(s): {versions}")
    findings["primary_component_count"] = int(target_config["primary_component_count"])
    findings["primary_component"] = target_config["primary_component"]
    if findings["primary_component_count"] != 1:
        failures.append("target is not a K=1 definition")
    if findings["primary_component"] != "mpi_adverse_yoy":
        failures.append(f"primary component is {findings['primary_component']}, expected MPI")

    findings["all_invariants_reproduced"] = not failures
    findings["failures"] = failures
    if failures:
        raise B4InvariantError(
            "B3 artifacts failed material invariants; B4 stops rather than repairing them:\n  - "
            + "\n  - ".join(failures)
        )
    return findings


@dataclass
class WalkForwardResult:
    predictions: pd.DataFrame
    b3_findings: dict
    plan: WalkForwardPlan
    origins: list[str] = field(default_factory=list)
    calibrator_fingerprints: dict[str, str] = field(default_factory=dict)


def run_walk_forward(
    monthly: pd.DataFrame | None = None,
    labels: pd.DataFrame | None = None,
    plan: WalkForwardPlan | None = None,
    baseline_config: dict | None = None,
) -> WalkForwardResult:
    """Generate out-of-fold development predictions, one origin at a time."""
    plan = plan or load_walk_forward_plan()
    baseline_config = baseline_config or load_baseline_config()
    if monthly is None or labels is None:
        monthly, labels = load_b3_artifacts()
    b3_findings = validate_b3_invariants(monthly, labels)

    origins = plan.development_origins
    # Hard guard: the reserved period is not reachable from this function.
    plan.assert_not_locked_test(origins)

    target_config = load_target_config()
    risk_levels = target_config["risk_levels"]
    min_reference = int(
        plan.config["information_rules"]["calibration"]["min_reference_observations"]
    )
    calibrator_version = target_config["calibration"]["calibrator_version"]

    baselines_by_horizon: dict[int, list[dict]] = {h: [] for h in plan.horizons}
    for spec in baseline_config["baselines"]:
        for horizon in spec["horizons"]:
            if int(horizon) in baselines_by_horizon:
                baselines_by_horizon[int(horizon)].append(spec)

    industries = sorted(monthly["industry_id"].unique().tolist())
    rows: list[dict] = []
    fingerprints: dict[str, str] = {}

    for origin in origins:
        # --- 1. historically available monthly stress (stress_month <= t) ----
        permitted_stress = monthly[monthly["reference_month"] <= origin]

        # --- 3-4. fit a fresh calibrator at THIS origin, then freeze ---------
        calibrator = IndustryStressCalibrator(
            min_reference_observations=min_reference, version=calibrator_version
        ).fit(permitted_stress, training_cutoff_month=origin)
        fingerprints[origin] = ";".join(
            calibrator.reference_for(i).fingerprint for i in calibrator.fitted_industries
        )

        stress_by_industry = {
            industry_id: dict(
                zip(sub["reference_month"], sub["mpi_adverse_yoy"].astype(float), strict=True)
            )
            for industry_id, sub in permitted_stress.groupby("industry_id", observed=True)
        }

        for horizon in plan.horizons:
            horizon_labels = labels[labels["horizon_months"] == horizon]

            # --- 2. historically COMPLETED training labels -------------------
            # window END, not origin date.
            completed = horizon_labels[horizon_labels["target_window_end"] <= origin]

            # --- 5. transform permitted historical labels with frozen state --
            training_scores: dict[str, list[float]] = {}
            for industry_id, sub in completed.groupby("industry_id", observed=True):
                training_scores[industry_id] = calibrator.transform(
                    industry_id, sub["target_raw_value"].to_numpy(float)
                ).tolist()
            max_window_end = (
                completed["target_window_end"].max() if not completed.empty else None
            )

            # the evaluation label for THIS origin — resolved only after the
            # calibrator is frozen, and never part of `completed` above
            current = horizon_labels[horizon_labels["forecast_origin_month"] == origin]
            observed_by_industry = dict(
                zip(current["industry_id"], current["target_raw_value"].astype(float), strict=True)
            )

            for industry_id in industries:
                if industry_id not in observed_by_industry:
                    continue
                context = BaselineContext(
                    origin=origin,
                    industry_id=industry_id,
                    horizon=horizon,
                    calibrator=calibrator,
                    raw_stress_by_month=stress_by_industry.get(industry_id, {}),
                    training_scores=training_scores.get(industry_id, []),
                )
                reference = calibrator.reference_for(industry_id)

                for spec in baselines_by_horizon[horizon]:
                    # --- 6-7. predict, then freeze -------------------------
                    predicted_raw, predicted_score = predict_baseline(spec["name"], context)
                    # --- 8. only now transform the observed future target ---
                    observed_raw = observed_by_industry[industry_id]
                    observed_score = float(
                        calibrator.transform(industry_id, observed_raw)[0]
                    )
                    rows.append(
                        {
                            "forecast_origin_month": origin,
                            "industry_id": industry_id,
                            "horizon_months": int(horizon),
                            "baseline_name": spec["name"],
                            "predicted_raw_value": predicted_raw,
                            "predicted_score": float(predicted_score),
                            "observed_raw_target": float(observed_raw),
                            "observed_score": observed_score,
                            "observed_risk_level": risk_level_for_score(
                                observed_score, risk_levels
                            ),
                            "calibration_reference_start": reference.start_month,
                            "calibration_reference_end": reference.end_month,
                            "calibration_observation_count": reference.n,
                            "calibration_fingerprint": reference.fingerprint,
                            "max_training_target_window_end": max_window_end,
                            "training_label_count": int(
                                len(training_scores.get(industry_id, []))
                            ),
                            "split_name": plan.block_for_origin(origin),
                            "target_definition_version": target_config[
                                "target_definition_version"
                            ],
                            "evaluation_harness_version": plan.harness_version,
                        }
                    )

    predictions = pd.DataFrame.from_records(rows, columns=PREDICTION_COLUMNS)
    predictions = predictions.sort_values(
        ["horizon_months", "baseline_name", "industry_id", "forecast_origin_month"],
        kind="mergesort",
    ).reset_index(drop=True)

    _assert_prediction_expectations(predictions, plan)
    return WalkForwardResult(
        predictions=predictions,
        b3_findings=b3_findings,
        plan=plan,
        origins=origins,
        calibrator_fingerprints=fingerprints,
    )


def _assert_prediction_expectations(predictions: pd.DataFrame, plan: WalkForwardPlan) -> None:
    failures: list[str] = []
    dev = plan.config["development"]
    expected_rows = int(dev["expected_rows_per_horizon"])

    origins = sorted(predictions["forecast_origin_month"].unique().tolist())
    if len(origins) != int(dev["origin_count"]):
        failures.append(f"origins: expected {dev['origin_count']}, found {len(origins)}")
    if origins and origins[0] != str(dev["first_origin"]):
        failures.append(f"first origin: expected {dev['first_origin']}, found {origins[0]}")
    if origins and origins[-1] != str(dev["last_origin"]):
        failures.append(f"last origin: expected {dev['last_origin']}, found {origins[-1]}")

    for horizon in plan.horizons:
        sub = predictions[predictions["horizon_months"] == horizon]
        for baseline_name, group in sub.groupby("baseline_name", observed=True):
            if len(group) != expected_rows:
                failures.append(
                    f"h={horizon} {baseline_name}: expected {expected_rows} rows, found "
                    f"{len(group)}"
                )
            per_origin = group.groupby("forecast_origin_month", observed=True).size()
            if set(per_origin.unique().tolist()) != {int(dev["industries"])}:
                failures.append(
                    f"h={horizon} {baseline_name}: expected {dev['industries']} predictions per "
                    f"origin, found {sorted(per_origin.unique().tolist())}"
                )

    # calibration must never reach past its own origin
    late = predictions[
        predictions["calibration_reference_end"] > predictions["forecast_origin_month"]
    ]
    if not late.empty:
        failures.append(f"{len(late)} row(s) have calibration reference beyond the origin")
    late_training = predictions[
        predictions["max_training_target_window_end"].notna()
        & (predictions["max_training_target_window_end"] > predictions["forecast_origin_month"])
    ]
    if not late_training.empty:
        failures.append(
            f"{len(late_training)} row(s) used a training label whose window ends after the origin"
        )

    if failures:
        raise B4InvariantError(
            "Walk-forward predictions violate the preregistered plan:\n  - "
            + "\n  - ".join(failures)
        )
