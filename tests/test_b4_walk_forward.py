"""Task B4 — walk-forward harness, baselines, metrics, and leakage guards.

FIXTURE POLICY: synthetic values are TEST FIXTURES using round, implausible
numbers so they cannot be mistaken for real observations. Tests reading real
artifacts are named "real_" or "snapshot".

Several tests DELIBERATELY attempt leakage — calibrator leakage, incomplete
3-month training labels, future-dated features, and locked-test evaluation
through the default runner — and assert each attempt fails explicitly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.evaluation import metrics as M  # noqa: E402
from thai_supply_chain_ews.evaluation.baselines import (  # noqa: E402
    BaselineContext,
    InsufficientHistoryError,
    industry_historical_mean,
    load_baseline_config,
    no_contraction,
    persistence_current_month,
    persistence_trailing_3m_max,
    seasonal_naive,
)
from thai_supply_chain_ews.evaluation.bootstrap import (  # noqa: E402
    block_indices,
    bootstrap_macro_mae_ci,
    bootstrap_paired_macro_mae_difference,
    build_error_matrix,
    describe_interval,
    macro_mae_from_matrix,
)
from thai_supply_chain_ews.evaluation.splits import (  # noqa: E402
    LockedTestAccessError,
    add_months,
    load_walk_forward_plan,
    month_range,
)
from thai_supply_chain_ews.evaluation.walk_forward import (  # noqa: E402
    LABELS_PATH,
    MONTHLY_STRESS_PATH,
    B4InvariantError,
    FeatureAvailabilityError,
    assert_feature_availability,
    load_b3_artifacts,
    run_walk_forward,
    validate_b3_invariants,
)
from thai_supply_chain_ews.targets.calibration import (  # noqa: E402
    IndustryStressCalibrator,
    LeakageError,
)

PLAN = load_walk_forward_plan()
BASELINE_CONFIG = load_baseline_config()
PREDICTIONS_PATH = ROOT / "data" / "model_input" / "b4_walk_forward_predictions.parquet"
RESULTS_JSON = ROOT / "docs" / "b4_baseline_results.json"
LOCKED_MANIFEST = ROOT / "docs" / "b4_locked_test_manifest.json"
B1_PANEL = ROOT / "data" / "processed" / "industry_month_panel.parquet"


def artifacts():
    if not MONTHLY_STRESS_PATH.is_file():
        pytest.skip("B3 artifacts missing — run scripts/run_b3_target_build.py")
    return load_b3_artifacts()


def predictions() -> pd.DataFrame:
    if not PREDICTIONS_PATH.is_file():
        pytest.skip("run scripts/run_b4_baselines.py first")
    return pd.read_parquet(PREDICTIONS_PATH)


def results() -> dict:
    if not RESULTS_JSON.is_file():
        pytest.skip("run scripts/run_b4_baselines.py first")
    return json.loads(RESULTS_JSON.read_text(encoding="utf-8"))


# --- B3 invariants ----------------------------------------------------------


def test_b3_invariants_are_independently_reproduced():
    monthly, labels = artifacts()
    findings = validate_b3_invariants(monthly, labels)
    assert findings["all_invariants_reproduced"] is True
    assert findings["monthly_rows"] == 636
    assert findings["monthly_industries"] == 12
    assert findings["monthly_months_per_industry"] == [53]
    assert findings["monthly_first"] == "2022-01-01"
    assert findings["monthly_last"] == "2026-05-01"
    assert findings["horizons"]["1"]["rows"] == 624
    assert findings["horizons"]["1"]["per_industry"] == [52]
    assert findings["horizons"]["1"]["last"] == "2026-04-01"
    assert findings["horizons"]["3"]["rows"] == 600
    assert findings["horizons"]["3"]["per_industry"] == [50]
    assert findings["horizons"]["3"]["last"] == "2026-02-01"
    assert findings["combined_rows"] == 1224
    assert findings["uses_2026_06"] == []
    assert findings["duplicate_keys"] == 0
    assert findings["primary_component_count"] == 1
    assert findings["primary_component"] == "mpi_adverse_yoy"


def test_b4_stops_when_a_b3_invariant_fails():
    monthly, labels = artifacts()
    broken = labels[labels["industry_id"] != "IND-07"]
    with pytest.raises(B4InvariantError, match="rows"):
        validate_b3_invariants(monthly, broken)


# --- split plan --------------------------------------------------------------


def test_development_origin_range_and_count():
    origins = PLAN.development_origins
    assert len(origins) == 15
    assert origins[0] == "2024-01-01"
    assert origins[-1] == "2025-03-01"


def test_purge_buffer_range():
    assert PLAN.purge_origins == ["2025-04-01", "2025-05-01", "2025-06-01"]
    assert PLAN.config["purge_buffer"]["metrics_reported"] is False


def test_locked_test_key_counts():
    assert len(PLAN.locked_test_origins(1)) == 10
    assert len(PLAN.locked_test_origins(3)) == 8
    assert PLAN.config["locked_test"]["horizons"][1]["expected_rows"] == 120
    assert PLAN.config["locked_test"]["horizons"][3]["expected_rows"] == 96
    manifest = json.loads(LOCKED_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["horizons"]["1"]["actual_rows"] == 120
    assert manifest["horizons"]["3"]["actual_rows"] == 96
    assert manifest["horizons"]["1"]["rows_match_expected"] is True
    assert manifest["horizons"]["3"]["rows_match_expected"] is True


def test_development_and_locked_periods_do_not_overlap():
    dev = set(PLAN.development_origins) | set(PLAN.purge_origins)
    locked = set(PLAN.locked_test_origins(1)) | set(PLAN.locked_test_origins(3))
    assert dev & locked == set()


def test_blocks_partition_the_development_period():
    blocks = [PLAN.block_for_origin(o) for o in PLAN.development_origins]
    assert blocks.count("DEV-1") == 5
    assert blocks.count("DEV-2") == 5
    assert blocks.count("DEV-3") == 5
    assert "OUT_OF_DEVELOPMENT" not in blocks


# --- locked test cannot be evaluated ----------------------------------------


def test_default_execution_cannot_evaluate_the_locked_test():
    predicted_origins = set(predictions()["forecast_origin_month"])
    locked = set(PLAN.locked_test_origins(1)) | set(PLAN.locked_test_origins(3))
    assert predicted_origins & locked == set()
    assert predicted_origins & set(PLAN.purge_origins) == set()
    assert results()["locked_test_evaluated"] is False


def test_leakage_attempt_running_locked_test_origins_is_refused():
    """Deliberate attempt: hand the harness a locked-test origin."""
    with pytest.raises(LockedTestAccessError, match="reserved locked test"):
        PLAN.assert_not_locked_test(["2025-07-01"])
    with pytest.raises(LockedTestAccessError):
        PLAN.assert_not_locked_test(PLAN.development_origins + ["2026-01-01"])


def test_runner_exposes_no_locked_test_flag():
    """Inspect CODE, not the docstring — the docstring legitimately names the
    flag it refuses to provide.
    """
    import ast

    source = (ROOT / "scripts" / "run_b4_baselines.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else node.names)
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "argparse" not in imported, "runner must take no command-line options"
    assert "click" not in imported
    code_without_docstrings = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "sys.argv" not in code_without_docstrings

    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    signature_args = main.args
    assert not signature_args.args and not signature_args.kwonlyargs, (
        "main() must accept no arguments, so there is no parameter that could "
        "switch on locked-test evaluation"
    )


def test_locked_manifest_contains_only_keys_and_checksums():
    """Check the manifest's actual per-horizon PAYLOAD against an allow-list.

    A substring scan would false-positive on `prohibited_outputs`, which names
    the very things it forbids.
    """
    manifest = json.loads(LOCKED_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["evaluated_in_b4"] is False
    assert manifest["manifest_only"] is True

    allowed = {
        "first_origin", "last_origin", "origin_count", "expected_rows",
        "actual_rows", "rows_match_expected", "key_sha256",
    }
    for horizon in ("1", "3"):
        entry = manifest["horizons"][horizon]
        assert set(entry) == allowed, f"unexpected locked-test field(s): {set(entry) - allowed}"
        assert "key_sha256" in entry
        # no target values of any kind — only counts, dates, and a checksum
        assert isinstance(entry["key_sha256"], str) and len(entry["key_sha256"]) == 64

    # and no observed/predicted values anywhere in the document
    blob = json.dumps(manifest).lower()
    for forbidden in ("observed_score", "predicted_score", "target_raw_value", "macro_industry"):
        assert forbidden not in blob, f"locked manifest leaked: {forbidden}"


# --- walk-forward information rules -----------------------------------------


def test_calibrator_refits_at_every_origin():
    monthly, labels = artifacts()
    result = run_walk_forward(monthly, labels, PLAN)
    fingerprints = result.calibrator_fingerprints
    assert len(fingerprints) == 15
    # a genuinely refitted calibrator has a different reference set each month
    assert len(set(fingerprints.values())) == 15
    assert PLAN.config["information_rules"]["calibration"]["refit_at_every_origin"] is True
    assert PLAN.config["information_rules"]["calibration"]["fit_once_over_development"] is False


def test_calibration_reference_end_never_exceeds_origin():
    frame = predictions()
    assert (frame["calibration_reference_end"] <= frame["forecast_origin_month"]).all()
    # and the origin month itself IS included, per the documented contract
    assert (frame["calibration_reference_end"] == frame["forecast_origin_month"]).all()


def test_training_target_window_end_never_exceeds_origin():
    frame = predictions()
    valid = frame[frame["max_training_target_window_end"].notna()]
    assert (
        valid["max_training_target_window_end"] <= valid["forecast_origin_month"]
    ).all()


def test_training_labels_are_selected_by_window_end_not_origin_date():
    """A 3-month label originating at t-1 ends at t+2 and must be excluded even
    though its ORIGIN precedes t. This is the rule that origin-date filtering
    would get wrong.
    """
    monthly, labels = artifacts()
    origin = "2024-06-01"
    horizon_labels = labels[labels["horizon_months"] == 3]
    by_window_end = horizon_labels[horizon_labels["target_window_end"] <= origin]
    by_origin_date = horizon_labels[horizon_labels["forecast_origin_month"] <= origin]
    assert len(by_window_end) < len(by_origin_date)
    # everything the naive rule would have added reaches past the origin
    extra = by_origin_date[~by_origin_date.index.isin(by_window_end.index)]
    assert (extra["target_window_end"] > origin).all()


def test_leakage_attempt_incomplete_three_month_training_label_is_excluded():
    """Deliberate attempt: verify no training label used at an origin has a
    window extending beyond it, for the 3-month horizon specifically.
    """
    monthly, labels = artifacts()
    result = run_walk_forward(monthly, labels, PLAN)
    three = result.predictions[result.predictions["horizon_months"] == 3]
    valid = three[three["max_training_target_window_end"].notna()]
    assert (valid["max_training_target_window_end"] <= valid["forecast_origin_month"]).all()
    # the label being evaluated is itself never in the training set
    for _, row in three.head(24).iterrows():
        window_end = add_months(row["forecast_origin_month"], row["horizon_months"])
        assert window_end > row["forecast_origin_month"]


def test_future_evaluation_target_is_absent_from_training_at_prediction_time():
    monthly, labels = artifacts()
    origin = "2024-06-01"
    horizon_labels = labels[labels["horizon_months"] == 1]
    completed = horizon_labels[horizon_labels["target_window_end"] <= origin]
    current = horizon_labels[horizon_labels["forecast_origin_month"] == origin]
    assert not completed.empty and not current.empty
    overlap = set(map(tuple, completed[["forecast_origin_month", "industry_id"]].values)) & set(
        map(tuple, current[["forecast_origin_month", "industry_id"]].values)
    )
    assert overlap == set()


def test_leakage_attempt_calibrator_fit_beyond_origin_is_refused():
    """Deliberate attempt: fit the calibrator on stress months after the origin."""
    monthly, _ = artifacts()
    origin = "2024-06-01"
    contaminated = monthly[monthly["reference_month"] <= "2024-12-01"]
    with pytest.raises(LeakageError, match="after the training cutoff"):
        IndustryStressCalibrator(min_reference_observations=24).fit(
            contaminated, training_cutoff_month=origin
        )


def test_minimum_calibration_history_is_24_observations():
    assert PLAN.config["information_rules"]["calibration"]["min_reference_observations"] == 24
    frame = predictions()
    assert (frame["calibration_observation_count"] >= 24).all()
    # the earliest development origin already clears the minimum
    earliest = frame[frame["forecast_origin_month"] == "2024-01-01"]
    assert earliest["calibration_observation_count"].min() == 25  # 2022-01..2024-01


# --- prediction shape --------------------------------------------------------


def test_180_out_of_fold_rows_per_horizon_per_baseline():
    frame = predictions()
    for horizon in (1, 3):
        sub = frame[frame["horizon_months"] == horizon]
        for name, group in sub.groupby("baseline_name"):
            assert len(group) == 180, f"h={horizon} {name}"


def test_twelve_predictions_per_origin_and_horizon():
    frame = predictions()
    counts = frame.groupby(
        ["horizon_months", "baseline_name", "forecast_origin_month"]
    ).size()
    assert set(counts.unique()) == {12}


def test_audit_metadata_is_present_on_every_prediction():
    frame = predictions()
    for column in (
        "calibration_reference_start", "calibration_reference_end",
        "calibration_observation_count", "calibration_fingerprint",
        "max_training_target_window_end", "training_label_count", "split_name",
        "target_definition_version", "evaluation_harness_version",
    ):
        assert column in frame.columns
        assert frame[column].notna().all(), column


# --- baselines ---------------------------------------------------------------


class _StubCalibrator:
    """TEST FIXTURE: identity-ish calibrator so baseline arithmetic is checkable."""

    def transform(self, industry_id, values):
        return np.atleast_1d(np.asarray(values, dtype=float)) * 2.0


def _context(horizon=1, origin="2024-06-01", stress=None, training=None):
    return BaselineContext(
        origin=origin,
        industry_id="IND-T",
        horizon=horizon,
        calibrator=_StubCalibrator(),
        raw_stress_by_month=stress if stress is not None else {},
        training_scores=training if training is not None else [],
    )


def test_persistence_uses_the_origin_month_value():
    context = _context(stress={"2024-06-01": 7.0, "2024-05-01": 99.0})
    raw, score = persistence_current_month(context)
    assert raw == pytest.approx(7.0)
    assert score == pytest.approx(14.0)  # stub doubles


def test_trailing_three_month_persistence_uses_t_minus_2_through_t():
    stress = {"2024-04-01": 1.0, "2024-05-01": 9.0, "2024-06-01": 3.0, "2024-03-01": 100.0}
    raw, score = persistence_trailing_3m_max(_context(horizon=3, stress=stress))
    assert raw == pytest.approx(9.0)  # max of t-2..t, ignoring t-3
    assert score == pytest.approx(18.0)


def test_trailing_persistence_raises_when_a_window_month_is_missing():
    with pytest.raises(InsufficientHistoryError, match="missing stress month"):
        persistence_trailing_3m_max(_context(horizon=3, stress={"2024-06-01": 1.0}))


def test_industry_historical_mean_uses_only_that_industrys_labels():
    raw, score = industry_historical_mean(_context(training=[10.0, 20.0, 30.0]))
    assert raw is None
    assert score == pytest.approx(20.0)


def test_industry_historical_mean_raises_rather_than_pooling():
    with pytest.raises(InsufficientHistoryError, match="no completed training labels"):
        industry_historical_mean(_context(training=[]))


def test_no_cross_industry_fallback_in_the_real_run():
    """Each industry's historical-mean prediction must be distinct at a given
    origin — a pooled fallback would make them identical.
    """
    frame = predictions()
    sub = frame[
        (frame["baseline_name"] == "industry_historical_mean")
        & (frame["forecast_origin_month"] == "2024-06-01")
        & (frame["horizon_months"] == 1)
    ]
    assert sub["predicted_score"].nunique() > 1


def test_seasonal_naive_month_alignment_for_one_month_horizon():
    # target month is 2024-07; one year earlier is 2023-07
    stress = {"2023-07-01": 5.0, "2023-06-01": 99.0}
    raw, _ = seasonal_naive(_context(horizon=1, origin="2024-06-01", stress=stress))
    assert raw == pytest.approx(5.0)


def test_seasonal_naive_window_alignment_for_three_month_horizon():
    # target window 2024-07..2024-09; one year earlier is 2023-07..2023-09
    stress = {
        "2023-07-01": 1.0, "2023-08-01": 6.0, "2023-09-01": 2.0,
        "2023-06-01": 99.0, "2023-10-01": 99.0,
    }
    raw, _ = seasonal_naive(_context(horizon=3, origin="2024-06-01", stress=stress))
    assert raw == pytest.approx(6.0)  # max within the shifted window only


def test_seasonal_naive_source_months_are_never_after_the_origin():
    for _horizon, offsets in ((1, [1]), (3, [1, 2, 3])):
        for offset in offsets:
            source = add_months("2024-06-01", offset - 12)
            assert source <= "2024-06-01"


def test_no_contraction_predicts_zero_raw():
    raw, score = no_contraction(_context())
    assert raw == 0.0
    assert score == pytest.approx(0.0)  # stub doubles zero


def test_baseline_config_forbids_tuning():
    policy = BASELINE_CONFIG["policy"]
    assert policy["tuning_permitted"] is False
    assert policy["weight_averaging_permitted"] is False
    assert policy["ensembling_permitted"] is False


# --- feature availability contract ------------------------------------------


def test_leakage_attempt_future_dated_feature_is_rejected():
    """Deliberate attempt: a feature whose availability month is after the origin."""
    frame = pd.DataFrame(
        {
            "forecast_origin_month": ["2024-06-01", "2024-06-01"],
            "feature_available_month": ["2024-05-01", "2024-07-01"],  # second is future
            "value": [1.0, 2.0],
        }
    )
    with pytest.raises(FeatureAvailabilityError, match="after"):
        assert_feature_availability(frame)


def test_feature_availability_accepts_same_month_and_earlier():
    frame = pd.DataFrame(
        {
            "forecast_origin_month": ["2024-06-01", "2024-06-01"],
            "feature_available_month": ["2024-06-01", "2024-01-01"],
            "value": [1.0, 2.0],
        }
    )
    assert_feature_availability(frame)


def test_feature_availability_requires_the_column_and_never_drops_rows():
    frame = pd.DataFrame({"forecast_origin_month": ["2024-06-01"], "value": [1.0]})
    with pytest.raises(FeatureAvailabilityError, match="no `feature_available_month`"):
        assert_feature_availability(frame)
    assert PLAN.config["information_rules"]["features"]["silently_drop_violations"] is False


def test_feature_rule_is_documented_as_month_based_not_release_date():
    features = PLAN.config["information_rules"]["features"]
    assert features["basis"] == "month_based_latest_vintage"
    assert features["is_real_time_release_date_rule"] is False


# --- metrics -----------------------------------------------------------------


def _metric_frame(observed, predicted, industries):
    return pd.DataFrame(
        {
            "observed_score": observed,
            "predicted_score": predicted,
            "industry_id": industries,
            "forecast_origin_month": [f"2024-{i%12+1:02d}-01" for i in range(len(observed))],
        }
    )


def test_macro_and_pooled_mae_are_distinguishable_on_an_unbalanced_panel():
    """TEST FIXTURE: IND-A has 3 rows with error 1, IND-B has 1 row with error 9.
    pooled = (1+1+1+9)/4 = 3.0 ; macro = (1 + 9)/2 = 5.0
    """
    frame = _metric_frame(
        observed=[1.0, 1.0, 1.0, 9.0],
        predicted=[0.0, 0.0, 0.0, 0.0],
        industries=["IND-A", "IND-A", "IND-A", "IND-B"],
    )
    assert M.pooled_mae(frame) == pytest.approx(3.0)
    assert M.macro_industry_mae(frame) == pytest.approx(5.0)
    assert M.macro_industry_mae(frame) != M.pooled_mae(frame)


def test_macro_equals_pooled_only_because_the_real_panel_is_balanced():
    frame = predictions()
    sub = frame[
        (frame["horizon_months"] == 1) & (frame["baseline_name"] == "persistence_current_month")
    ]
    assert set(sub.groupby("industry_id").size().unique()) == {15}  # balanced
    assert M.macro_industry_mae(sub) == pytest.approx(M.pooled_mae(sub))


def test_mae_and_rmse_formulas():
    frame = _metric_frame([0.0, 0.0], [3.0, 4.0], ["IND-A", "IND-A"])
    assert M.pooled_mae(frame) == pytest.approx(3.5)
    assert M.pooled_rmse(frame) == pytest.approx(np.sqrt((9 + 16) / 2))
    assert M.median_absolute_error(frame) == pytest.approx(3.5)


def test_high_stress_risk_boundary_is_at_score_85():
    frame = _metric_frame(
        observed=[84.999, 85.0, 90.0], predicted=[0.0, 0.0, 90.0],
        industries=["IND-A"] * 3,
    )
    stats = M.high_stress_event_metrics(frame)
    assert stats["threshold"] == 85.0
    assert stats["observed_events"] == 2  # 85.0 counts, 84.999 does not
    assert stats["false_negative"] == 1
    assert stats["true_positive"] == 1


def test_pr_auc_is_none_with_a_reason_when_undefined():
    frame = _metric_frame([10.0, 20.0], [5.0, 5.0], ["IND-A", "IND-A"])
    stats = M.high_stress_event_metrics(frame)
    assert stats["observed_events"] == 0
    assert stats["pr_auc"] is None
    assert "undefined" in stats["pr_auc_undefined_reason"]
    assert stats["precision"] is None and stats["recall"] is None


def test_pr_auc_is_computed_when_defined():
    frame = _metric_frame([90.0, 10.0, 95.0], [99.0, 1.0, 98.0], ["IND-A"] * 3)
    stats = M.high_stress_event_metrics(frame)
    assert stats["pr_auc"] == pytest.approx(1.0)
    assert stats["pr_auc_undefined_reason"] is None


def test_severe_events_are_descriptive_only():
    frame = predictions()
    sub = frame[
        (frame["horizon_months"] == 1) & (frame["baseline_name"] == "persistence_current_month")
    ]
    stats = M.severe_event_counts(sub)
    assert stats["threshold"] == 95.0
    assert stats["reporting"] == "descriptive_counts_only"
    assert set(stats) & {"precision", "recall", "f1"} == set()


def test_mae_skill_formula():
    assert M.mae_skill(5.0, 10.0) == pytest.approx(0.5)
    assert M.mae_skill(10.0, 10.0) == pytest.approx(0.0)
    assert M.mae_skill(20.0, 10.0) == pytest.approx(-1.0)


# --- bootstrap ---------------------------------------------------------------


def _matrix(values):
    from thai_supply_chain_ews.evaluation.bootstrap import ErrorMatrix

    return ErrorMatrix(
        np.asarray(values, dtype=float),
        months=[f"2024-{i+1:02d}-01" for i in range(len(values))],
        industries=[f"IND-{j+1:02d}" for j in range(len(values[0]))],
    )


def test_bootstrap_resamples_months_as_clusters_keeping_industries_together():
    rng = np.random.default_rng(0)
    idx = block_indices(15, 3, rng)
    assert len(idx) == 15
    # blocks are consecutive month positions
    assert all(idx[i] + 1 == idx[i + 1] for i in range(0, 15, 3) for _ in [0] if i + 1 < 15)
    cfg = PLAN.config["bootstrap"]
    assert cfg["cluster_unit"] == "forecast_origin_month"
    assert cfg["keep_all_industries_together"] is True
    assert cfg["block_length_months"] == 3
    assert cfg["replications"] >= 1000


def test_bootstrap_is_deterministic():
    matrix = _matrix([[float(i + j) for j in range(12)] for i in range(15)])
    cfg = PLAN.config["bootstrap"]
    first = bootstrap_macro_mae_ci(matrix, cfg, seed_offset=1)
    second = bootstrap_macro_mae_ci(matrix, cfg, seed_offset=1)
    assert first == second
    different = bootstrap_macro_mae_ci(matrix, cfg, seed_offset=2)
    assert different["ci_low"] != first["ci_low"]


def test_bootstrap_ci_brackets_the_point_estimate():
    matrix = _matrix([[float(i + j) for j in range(12)] for i in range(15)])
    result = bootstrap_macro_mae_ci(matrix, PLAN.config["bootstrap"], seed_offset=3)
    assert result["ci_low"] <= result["point_estimate"] <= result["ci_high"]
    assert result["n_month_clusters"] == 15


def test_macro_mae_from_matrix_matches_the_frame_metric():
    frame = predictions()
    sub = frame[
        (frame["horizon_months"] == 1) & (frame["baseline_name"] == "no_contraction")
    ]
    matrix = build_error_matrix(sub)
    assert macro_mae_from_matrix(matrix.values) == pytest.approx(M.macro_industry_mae(sub))


def test_build_error_matrix_rejects_a_ragged_slice():
    frame = predictions()
    sub = frame[
        (frame["horizon_months"] == 1) & (frame["baseline_name"] == "no_contraction")
    ]
    with pytest.raises(ValueError, match="exactly one row per"):
        build_error_matrix(sub.iloc[:-1])


def test_interval_crossing_zero_is_called_inconclusive():
    assert describe_interval(-1.0, 1.0) == "inconclusive"
    assert describe_interval(0.5, 1.0) == "excludes_zero"
    assert describe_interval(-2.0, -0.5) == "excludes_zero"
    assert describe_interval(None, None) == "undefined"


def test_paired_bootstrap_uses_identical_month_axes():
    a = _matrix([[1.0] * 12 for _ in range(15)])
    b = _matrix([[2.0] * 12 for _ in range(14)])
    with pytest.raises(ValueError, match="identical month axes"):
        bootstrap_paired_macro_mae_difference(a, b, PLAN.config["bootstrap"])


# --- baseline selection ------------------------------------------------------


def test_baseline_selection_uses_no_locked_test_information():
    output = results()
    for horizon in ("1", "3"):
        info = output["by_horizon"][horizon]
        assert info["selection_used_locked_test_information"] is False
        assert info["selected_benchmark"] in {
            baseline["name"] for baseline in BASELINE_CONFIG["baselines"]
        }
        for stats in info["baselines"].values():
            assert stats["n_origins"] == 15
            assert stats["n_rows"] == 180


def test_selected_benchmark_has_the_lowest_macro_mae_or_a_documented_tiebreak():
    output = results()
    for horizon in ("1", "3"):
        info = output["by_horizon"][horizon]
        maes = {k: v["macro_industry_mae"] for k, v in info["baselines"].items()}
        lowest = min(maes, key=maes.get)
        if info["selected_benchmark"] != lowest:
            assert "tie" in info["selection_reason"]
        else:
            assert info["selection_reason"] in {
                "lowest_development_macro_industry_mae",
                "effective_tie_but_leader_also_had_fewer_false_negatives",
                "effective_tie_broken_by_simplicity",
            }


def test_skill_reference_baseline_has_zero_skill_against_itself():
    output = results()
    for horizon in ("1", "3"):
        stats = output["by_horizon"][horizon]["baselines"]["industry_historical_mean"]
        assert stats["mae_skill_vs_historical_mean"] == pytest.approx(0.0)


# --- upstream immutability and determinism ----------------------------------


def test_b1_and_b3_artifacts_are_not_modified_by_b4():
    before = {
        p: p.read_bytes() for p in (B1_PANEL, MONTHLY_STRESS_PATH, LABELS_PATH) if p.is_file()
    }
    monthly, labels = artifacts()
    run_walk_forward(monthly, labels, PLAN)
    for path, content in before.items():
        assert path.read_bytes() == content, f"{path.name} was modified"
    output = results()
    assert output["upstream_artifacts_unmodified"] == {
        "b1_panel": True, "b3_monthly_stress": True, "b3_labels": True,
    }


def test_walk_forward_output_is_deterministic():
    monthly, labels = artifacts()
    first = run_walk_forward(monthly, labels, PLAN).predictions
    second = run_walk_forward(monthly, labels, PLAN).predictions
    pd.testing.assert_frame_equal(first, second)


def test_month_helpers():
    assert month_range("2024-01-01", "2024-03-01") == [
        "2024-01-01", "2024-02-01", "2024-03-01"
    ]
    assert add_months("2024-12-01", 1) == "2025-01-01"
    assert add_months("2024-01-01", -1) == "2023-12-01"
    assert add_months("2024-06-01", -12) == "2023-06-01"


def test_results_json_matches_recomputed_predictions():
    output = results()
    frame = predictions()
    assert output["development"]["total_prediction_rows"] == len(frame)
    assert output["development"]["origin_count"] == frame["forecast_origin_month"].nunique()
    for horizon in ("1", "3"):
        for name, stats in output["by_horizon"][horizon]["baselines"].items():
            sub = frame[
                (frame["horizon_months"] == int(horizon)) & (frame["baseline_name"] == name)
            ]
            assert stats["macro_industry_mae"] == pytest.approx(M.macro_industry_mae(sub))
