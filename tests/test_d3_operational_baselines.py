"""Task D3 tests — the operational forecast-origin contract.

The load-bearing tests here are the negative ones. It is easy to write an
evaluation that *looks* release-aware; what proves it is that reaching for
stress month *t*, admitting an unpublished label, trusting a migration
timestamp, or passing a locked origin through an internal API all raise.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thai_supply_chain_ews.evaluation import metrics as MT
from thai_supply_chain_ews.evaluation import operational_availability as OA
from thai_supply_chain_ews.evaluation import operational_baselines as OB
from thai_supply_chain_ews.evaluation import operational_contract as OC
from thai_supply_chain_ews.evaluation import operational_walk_forward as OWF
from thai_supply_chain_ews.evaluation import walk_forward as WF
from thai_supply_chain_ews.evaluation.baselines import (
    BaselineContext,
    InsufficientHistoryError,
)
from thai_supply_chain_ews.evaluation.splits import add_months, load_walk_forward_plan

ROOT = Path(__file__).resolve().parents[1]
CONFIG = OC.load_operational_config()
RESULTS_JSON = ROOT / "docs" / "d3_operational_baseline_results.json"
LOCKED_MANIFEST = ROOT / "docs" / "d3_locked_test_manifest.json"
ERRATUM = ROOT / "docs" / "d1_development_results.errata.md"

requires_results = pytest.mark.skipif(
    not RESULTS_JSON.is_file(), reason="D3 has not been run"
)


@pytest.fixture(scope="module")
def artifacts():
    monthly, labels = WF.load_b3_artifacts()
    return monthly, labels


@pytest.fixture(scope="module")
def run(artifacts):
    monthly, labels = artifacts
    return OWF.run_operational_walk_forward(monthly=monthly, labels=labels, config=CONFIG)


# ---------------------------------------------------------------------------
# 1. D1 restoration and the erratum
# ---------------------------------------------------------------------------
D1_DOCS = ("docs/d1_development_results.md", "docs/d1_modeling_protocol.md")


@pytest.mark.parametrize("relative", D1_DOCS)
def test_restored_d1_documents_carry_no_correction_text(relative):
    """The correction lives in the erratum, never inside a generated D1 file."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    for marker in ("AD-R66", "Task D2", "Correction (Task D2", "withdrawn as unsupported"):
        assert marker not in text, f"{relative} still contains {marker!r}"


@pytest.mark.parametrize("relative", D1_DOCS)
def test_restored_d1_documents_still_contain_their_original_claim(relative):
    """Restoration means the original wording is back, not deleted."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert "never better" in text


@pytest.mark.parametrize("relative", D1_DOCS)
def test_restored_d1_document_checksums_are_recorded(relative):
    """The restored checksum is pinned, so later drift is detectable."""
    pinned = json.loads((ROOT / "docs" / "d3_restored_d1_checksums.json").read_text("utf-8"))
    digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    assert pinned["restored"][relative] == digest


def test_erratum_exists_and_states_every_corrected_field():
    text = ERRATUM.read_text(encoding="utf-8")
    for required in (
        "incremental_signal_not_supported",
        "d1_nested_protocol_fully_executed",
        "fallback_strongly_shrinks_toward_benchmark",
        "fallback_guaranteed_to_worsen_model",
        "fallback_effect_direction",
        "unknown",
        "d1_approved_for_locked_test",
        "AD-R59",
        "AD-R67",
    ):
        assert required in text, required
    assert "6" in text and "30" in text


def test_erratum_is_discoverable_from_the_expected_documents():
    for relative in (
        "README.md",
        "docs/methodology.md",
        "docs/d2_target_timing_decision.md",
        "docs/architecture/decision_log.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "d1_development_results.errata" in text, relative


# ---------------------------------------------------------------------------
# 2. Config and split
# ---------------------------------------------------------------------------
def test_config_declares_the_operational_framing():
    assert CONFIG["evaluation_framing"] == "release_lag_aware_latest_vintage_evaluation"
    assert CONFIG["release_timing_aware"] is True
    assert CONFIG["latest_vintage_target_values"] is True
    assert CONFIG["point_in_time_target_values"] is False
    assert CONFIG["fully_real_time_backtest"] is False
    assert CONFIG["same_month_stress_used"] is False


def test_config_forbids_touching_upstream_tasks():
    immutability = CONFIG["immutability"]
    for key in (
        "may_change_b1_source_data",
        "may_change_b3_raw_targets_or_windows",
        "may_change_b4_artifacts_or_metrics",
        "may_change_d1_predictions_or_metrics",
        "may_change_d2_release_inventory",
        "may_change_c1_to_c4_data_or_features",
        "may_change_split_date_ranges",
        "may_train_model",
        "may_use_commodity_features",
        "may_evaluate_locked_test",
        "may_overwrite_b4_or_d1_outputs",
    ):
        assert immutability[key] is False, key


def test_exactly_fifteen_development_issue_months(run):
    assert len(run.origins) == 15
    assert OC.month_label(run.origins[0]) == "2024-01"
    assert OC.month_label(run.origins[-1]) == "2025-03"


def test_purge_and_locked_windows_match_the_brief():
    assert sorted(OC.purge_month_set(CONFIG)) == ["2025-04", "2025-05", "2025-06"]
    locked = CONFIG["split"]["locked_test"]["horizons"]
    assert (locked[1]["start"], locked[1]["end"]) == ("2025-07", "2026-04")
    assert (locked[3]["start"], locked[3]["end"]) == ("2025-07", "2026-02")


# ---------------------------------------------------------------------------
# 3. Issue dates and the t-1 rule
# ---------------------------------------------------------------------------
def test_every_issue_date_is_verified_and_inside_its_issue_month(run):
    for origin, contract in sorted(run.contracts.items()):
        assert contract.forecast_issue_date[:7] == OC.month_label(origin)
        assert contract.publication_month == OC.month_label(origin)
        assert contract.timing_evidence_class in {
            "attachment_corroborated",
            "attachment_last_modified_only",
            "rehosted_listing_later_than_attachment",
            "directly_observed_release",
        }


def test_latest_available_stress_month_is_always_t_minus_one(run):
    for origin, contract in run.contracts.items():
        assert contract.latest_available_stress_month == add_months(origin, -1)
        assert contract.calibration_reference_end == add_months(origin, -1)


def test_issue_dates_reconcile_against_d2(run):
    index = OC.load_release_index()
    for origin, contract in run.contracts.items():
        record = index[add_months(origin, -1)]
        assert contract.forecast_issue_date == record["release_date"]
        OC.assert_issue_date_not_before_release(contract, index)


def test_requesting_current_month_stress_raises(run):
    contract = run.contracts["2024-06-01"]
    with pytest.raises(OC.CurrentMonthStressError):
        contract.assert_stress_month_permitted("2024-06-01")
    contract.assert_stress_month_permitted("2024-05-01")


# ---------------------------------------------------------------------------
# 4. Calibration
# ---------------------------------------------------------------------------
def test_calibration_reference_end_is_always_before_the_issue_month(run):
    predictions = run.predictions
    assert (
        predictions["calibration_reference_end"] < predictions["forecast_origin_month"]
    ).all()
    assert (
        predictions["calibration_reference_end"]
        == predictions["latest_available_stress_month"]
    ).all()


def test_calibration_minimum_is_twenty_four(run):
    assert (run.predictions["calibration_observation_count"] >= 24).all()
    assert CONFIG["calibration"]["min_reference_observations"] == 24


def test_expected_calibration_counts(run):
    first = run.predictions[run.predictions["forecast_origin_month"] == "2024-01-01"]
    last = run.predictions[run.predictions["forecast_origin_month"] == "2025-03-01"]
    assert first["calibration_reference_end"].unique().tolist() == ["2023-12-01"]
    assert first["calibration_observation_count"].unique().tolist() == [24]
    assert last["calibration_reference_end"].unique().tolist() == ["2025-02-01"]
    assert last["calibration_observation_count"].unique().tolist() == [38]


def test_calibrator_refits_at_every_origin(run):
    fingerprints = run.calibrator_fingerprints
    assert len(fingerprints) == 15
    assert len(set(fingerprints.values())) == 15


def test_calibration_never_admits_the_issue_month(artifacts):
    """Synthetic failure: current-month stress inserted into calibration."""
    monthly, _ = artifacts
    contaminated = {"2024-05-01": 1.0, "2024-06-01": 2.0}
    with pytest.raises(OC.CurrentMonthStressError):
        OA.assert_no_future_stress(contaminated, "2024-05-01")


# ---------------------------------------------------------------------------
# 5. Training-label availability
# ---------------------------------------------------------------------------
def test_target_available_month_is_window_end_plus_one():
    assert OA.target_available_month("2023-12-01") == "2024-01-01"
    assert OA.target_available_month("2024-12-01") == "2025-01-01"


def test_exact_training_label_counts(artifacts):
    _, labels = artifacts
    expected = [
        (1, "2024-01-01", "2023-11-01", 276),
        (1, "2025-03-01", "2025-01-01", 444),
        (3, "2024-01-01", "2023-09-01", 252),
        (3, "2025-03-01", "2024-11-01", 420),
    ]
    for horizon, issue, latest, rows in expected:
        subset = labels[labels["horizon_months"] == horizon]
        summary = OA.summarize_availability(subset, issue, horizon)
        assert summary.latest_permitted_label_origin == latest
        assert summary.row_count == rows


def test_training_availability_never_exceeds_the_issue_month(run):
    predictions = run.predictions
    assert (
        predictions["max_training_target_available_month"]
        <= predictions["forecast_origin_month"]
    ).all()


def test_old_b4_rule_would_admit_more_labels(artifacts):
    """The operational rule is strictly stricter than B4's."""
    _, labels = artifacts
    subset = labels[labels["horizon_months"] == 1]
    b4_rule = subset[subset["target_window_end"] <= "2024-01-01"]
    d3_rule = OA.available_training_labels(subset, "2024-01-01")
    assert len(b4_rule) > len(d3_rule)
    assert len(b4_rule) - len(d3_rule) == 12


def test_unpublished_label_raises_rather_than_being_dropped():
    """Synthetic failure: a window that closed but has not been published."""
    frame = pd.DataFrame(
        {
            "forecast_origin_month": ["2023-12-01"],
            "target_window_end": ["2024-01-01"],  # available 2024-02, after issue
            "target_raw_value": [1.0],
            "industry_id": ["IND-01"],
        }
    )
    with pytest.raises(OA.LabelAvailabilityError):
        OA.assert_labels_available(frame, "2024-01-01")


def test_evaluation_label_is_never_available_at_its_own_issue_month(run):
    predictions = run.predictions
    assert (
        predictions["target_available_month"] > predictions["forecast_origin_month"]
    ).all()


# ---------------------------------------------------------------------------
# 6. Baseline formulas
# ---------------------------------------------------------------------------
class _Calibrator:
    """Identity calibrator: keeps the formula visible in the assertion."""

    def transform(self, industry_id, value):
        import numpy as np

        return np.atleast_1d(np.asarray(value, dtype=float))


def _context(origin, horizon, stress, training=None):
    return BaselineContext(
        origin=origin,
        industry_id="IND-01",
        horizon=horizon,
        calibrator=_Calibrator(),
        raw_stress_by_month=stress,
        training_scores=list(training or []),
    )


def test_latest_published_persistence_reads_t_minus_one():
    stress = {"2024-05-01": 7.0, "2024-04-01": 3.0}
    raw, score = OB.operational_persistence_latest_published(
        _context("2024-06-01", 1, stress)
    )
    assert raw == 7.0 and score == 7.0


def test_latest_published_persistence_refuses_to_use_current_month():
    """Synthetic failure: S_t present but must not be reachable."""
    stress = {"2024-06-01": 99.0}  # only month t
    with pytest.raises(InsufficientHistoryError):
        OB.operational_persistence_latest_published(_context("2024-06-01", 1, stress))


def test_trailing_three_month_max_uses_t3_t2_t1():
    stress = {"2024-03-01": 1.0, "2024-04-01": 9.0, "2024-05-01": 4.0, "2024-06-01": 99.0}
    raw, score = OB.operational_persistence_trailing_3m_max(
        _context("2024-06-01", 3, stress)
    )
    assert raw == 9.0 and score == 9.0  # 99.0 at month t is ignored


def test_trailing_three_month_max_requires_all_three_published():
    stress = {"2024-04-01": 9.0, "2024-05-01": 4.0}  # t-3 missing
    with pytest.raises(InsufficientHistoryError):
        OB.operational_persistence_trailing_3m_max(_context("2024-06-01", 3, stress))


def test_seasonal_naive_alignment_h1_is_t_minus_eleven():
    stress = {"2023-07-01": 5.0}
    raw, _ = OB.operational_seasonal_naive(_context("2024-06-01", 1, stress))
    assert raw == 5.0


def test_seasonal_naive_alignment_h3_is_t_minus_eleven_to_nine():
    stress = {"2023-07-01": 5.0, "2023-08-01": 8.0, "2023-09-01": 2.0}
    raw, _ = OB.operational_seasonal_naive(_context("2024-06-01", 3, stress))
    assert raw == 8.0


def test_seasonal_naive_rejects_a_future_source_month():
    """Synthetic failure: a source month after the issue date."""
    stress = {"2023-08-01": 8.0, "2023-09-01": 2.0}  # t-11 missing
    with pytest.raises(InsufficientHistoryError):
        OB.operational_seasonal_naive(_context("2024-06-01", 3, stress))


def test_no_contraction_predicts_calibrated_zero():
    raw, score = OB.operational_no_contraction(_context("2024-06-01", 1, {}))
    assert raw == 0.0 and score == 0.0


def test_industry_mean_uses_only_this_industry_and_raises_when_empty():
    raw, score = OB.operational_industry_historical_mean(
        _context("2024-06-01", 1, {}, training=[10.0, 20.0])
    )
    assert raw is None and score == 15.0
    with pytest.raises(InsufficientHistoryError):
        OB.operational_industry_historical_mean(_context("2024-06-01", 1, {}, training=[]))


def test_no_cross_industry_fallback(run):
    """Each industry's mean must differ; a pooled value would collapse them."""
    frame = run.predictions[
        (run.predictions["baseline_name"] == "operational_industry_historical_mean")
        & (run.predictions["horizon_months"] == 1)
        & (run.predictions["forecast_origin_month"] == "2024-01-01")
    ]
    assert len(frame) == 12
    assert frame["predicted_score"].nunique() > 1


def test_horizon_baseline_membership():
    assert len(OB.OPERATIONAL_BASELINES_BY_HORIZON[1]) == 4
    assert len(OB.OPERATIONAL_BASELINES_BY_HORIZON[3]) == 5
    assert (
        "operational_persistence_trailing_3m_max"
        not in OB.OPERATIONAL_BASELINES_BY_HORIZON[1]
    )
    assert (
        "operational_persistence_latest_published"
        in OB.OPERATIONAL_BASELINES_BY_HORIZON[3]
    )


# ---------------------------------------------------------------------------
# 7. Prediction counts and keys
# ---------------------------------------------------------------------------
def test_prediction_counts(run):
    predictions = run.predictions
    assert len(predictions) == 1620
    assert int((predictions["horizon_months"] == 1).sum()) == 720
    assert int((predictions["horizon_months"] == 3).sum()) == 900


def test_one_hundred_eighty_rows_per_baseline_and_horizon(run):
    grouped = run.predictions.groupby(["horizon_months", "baseline_name"]).size()
    assert set(grouped.unique().tolist()) == {180}


def test_twelve_industries_per_origin_horizon_baseline(run):
    grouped = run.predictions.groupby(
        ["forecast_origin_month", "horizon_months", "baseline_name"]
    ).size()
    assert set(grouped.unique().tolist()) == {12}


def test_keys_are_unique_and_ordering_is_deterministic(run):
    key = ["forecast_origin_month", "industry_id", "horizon_months", "baseline_name"]
    assert not run.predictions.duplicated(subset=key).any()
    ordered = run.predictions.sort_values(
        ["horizon_months", "baseline_name", "industry_id", "forecast_origin_month"],
        kind="mergesort",
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(run.predictions, ordered)


def test_no_purge_or_locked_origin_appears(run):
    months = {OC.month_label(m) for m in run.predictions["forecast_origin_month"]}
    assert not (months & OC.purge_month_set(CONFIG))
    assert not (months & OC.locked_month_set(CONFIG))


def test_dataset_flags(run):
    flags = run.dataset_flags
    assert flags["release_timing_aware"] is True
    assert flags["latest_vintage_target_values"] is True
    assert flags["point_in_time_target_values"] is False
    assert flags["fully_real_time_backtest"] is False
    assert flags["same_month_stress_used"] is False
    assert flags["locked_test_accessed"] is False


def test_every_schema_column_is_present(run):
    schema = yaml.safe_load(
        (ROOT / "schemas" / "operational_prediction.schema.yaml").read_text("utf-8")
    )
    declared = [c["name"] for c in schema["operational_prediction"]["columns"]]
    assert list(run.predictions.columns) == OWF.OPERATIONAL_PREDICTION_COLUMNS
    for name in declared:
        assert name in run.predictions.columns, name


# ---------------------------------------------------------------------------
# 8. The locked test is unreachable
# ---------------------------------------------------------------------------
def test_locked_origin_through_internal_api_raises():
    """Synthetic failure: a locked origin passed through an internal API."""
    index = OC.load_release_index()
    with pytest.raises(OC.LockedOriginError):
        OC.build_origin_contracts(["2025-08-01"], CONFIG, index)


def test_purge_origin_is_rejected_by_the_runner(artifacts):
    monthly, labels = artifacts
    plan = load_walk_forward_plan()

    class _Plan:
        development_origins = ["2025-05-01"]
        horizons = plan.horizons
        harness_version = plan.harness_version

        def assert_not_locked_test(self, origins):
            return None

        def block_for_origin(self, origin):
            return "PURGE"

    with pytest.raises(OC.OperationalContractError):
        OWF.run_operational_walk_forward(
            monthly=monthly, labels=labels, plan=_Plan(), config=CONFIG
        )


def test_runner_exposes_no_locked_evaluation_switch():
    import inspect

    signature = inspect.signature(OWF.run_operational_walk_forward)
    for name in signature.parameters:
        assert "lock" not in name.lower()
        assert "test" not in name.lower()
    source = inspect.getsource(OWF)
    assert "locked_test_origins" not in source


def test_runner_script_has_no_locked_flag():
    source = (ROOT / "scripts" / "run_d3_operational_baselines.py").read_text("utf-8")
    assert "--locked" not in source
    assert "locked_test_origins" not in source
    # no environment-variable escape hatch (the phrase "environment variable"
    # appears in the docstring, so match actual API use, not the English word)
    assert "os.environ" not in source
    assert "getenv" not in source


@requires_results
def test_locked_manifest_is_key_only():
    manifest = json.loads(LOCKED_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["locked_test_evaluated"] is False
    assert manifest["locked_test_outcomes_read"] is False
    assert manifest["runner_can_reach_locked_origins"] is False
    text = LOCKED_MANIFEST.read_text(encoding="utf-8")
    for forbidden in ("observed_score", "observed_raw_target", "macro_industry_mae"):
        assert forbidden not in text


# ---------------------------------------------------------------------------
# 9. Metrics, bootstrap, selection
# ---------------------------------------------------------------------------
def test_macro_and_pooled_mae_are_reported_separately(run):
    frame = run.predictions[
        (run.predictions["horizon_months"] == 1)
        & (run.predictions["baseline_name"] == "operational_no_contraction")
    ]
    assert MT.macro_industry_mae(frame) == pytest.approx(MT.pooled_mae(frame))


def test_high_stress_threshold_is_eighty_five():
    assert CONFIG["metrics"]["high_stress"]["threshold"] == 85
    assert CONFIG["metrics"]["high_stress"]["threshold_tuned"] is False
    assert MT.HIGH_STRESS_SCORE_THRESHOLD == 85


def test_bootstrap_settings_match_the_brief():
    bootstrap = CONFIG["bootstrap"]
    assert bootstrap["block_length_months"] == 3
    assert bootstrap["replications"] >= 1000
    assert bootstrap["cluster_by"] == "issue_month"
    assert bootstrap["preserve_all_industries"] is True
    assert isinstance(bootstrap["random_seed"], int)


@requires_results
def test_bootstrap_is_clustered_and_deterministic():
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    interval = payload["metrics"]["1"]["baselines"]["operational_no_contraction"][
        "macro_mae_ci"
    ]
    assert interval["cluster_unit"] == "forecast_origin_month"
    assert interval["n_month_clusters"] == 15
    assert interval["keeps_all_industries_together"] is True
    assert interval["block_length_months"] == 3
    assert interval["replications"] >= 1000
    assert interval["ci_low"] <= interval["point_estimate"] <= interval["ci_high"]


@requires_results
def test_benchmark_selection_used_no_locked_information():
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    for horizon in ("1", "3"):
        selection = payload["benchmark_selection"][horizon]
        assert selection["selection_used_only_development_data"] is True
        assert selection["selected_benchmark"] in OB.OPERATIONAL_BASELINE_NAMES
        for forbidden in ("locked_outcomes", "purge_outcomes", "d1_model_performance"):
            assert forbidden in selection["excluded_from_selection"]


@requires_results
def test_selected_benchmark_has_the_lowest_macro_mae():
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    for horizon in ("1", "3"):
        block = payload["metrics"][horizon]["baselines"]
        selection = payload["benchmark_selection"][horizon]
        best = min(block[n]["macro_industry_mae"] for n in block)
        assert block[selection["selected_benchmark"]]["macro_industry_mae"] == pytest.approx(best)


@requires_results
def test_operational_penalty_is_reported_and_attributed_honestly():
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    for horizon in ("1", "3"):
        selection = payload["benchmark_selection"][horizon]
        assert "operational_penalty" in selection
        expected = (
            selection["macro_industry_mae"] - selection["b4_reference_macro_industry_mae"]
        )
        assert selection["operational_penalty"] == pytest.approx(expected)
        assert "NOT attributable solely to publication lag" in (
            selection["operational_penalty_attribution"]
        )


@requires_results
def test_contract_status_and_separate_validity_flags():
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    status = payload["contract_status"]
    assert status["status"] == "operational_month_timing_supported"
    assert status["all_development_issue_dates_verified"] is True
    assert status["no_same_month_stress_used"] is True
    assert status["label_availability_enforced"] is True
    # timing validity and vintage validity must not be one boolean
    assert status["point_in_time_values_supported"] is False
    assert status["latest_vintage_evaluation"] is True
    assert status["fully_real_time_backtest"] is False


@requires_results
def test_latest_vintage_is_never_labelled_fully_real_time():
    """Synthetic failure guard: the two claims must not both be true."""
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    flags = payload["dataset_flags"]
    assert not (flags["latest_vintage_target_values"] and flags["fully_real_time_backtest"])
    text = (ROOT / "docs" / "d3_operational_baseline_results.md").read_text("utf-8")
    assert "not** a" in text or "not a" in text


# ---------------------------------------------------------------------------
# 10. Upstream artifacts unchanged, and no model / feature module touched
# ---------------------------------------------------------------------------
def test_b3_invariants_still_hold(run):
    findings = run.b3_findings
    assert findings["primary_component"] == "mpi_adverse_yoy"


def test_d3_reuses_b3_raw_targets_unchanged(run, artifacts):
    _, labels = artifacts
    predictions = run.predictions
    merged = predictions.merge(
        labels,
        left_on=["forecast_origin_month", "industry_id", "horizon_months"],
        right_on=["forecast_origin_month", "industry_id", "horizon_months"],
        how="left",
    )
    assert merged["observed_raw_target"].equals(merged["target_raw_value"].astype(float))
    assert merged["target_window_start_x"].equals(merged["target_window_start_y"])
    assert merged["target_window_end_x"].equals(merged["target_window_end_y"])


def test_no_model_or_commodity_feature_module_is_imported():
    import inspect

    for module in (OWF, OB, OA, OC):
        source = inspect.getsource(module)
        for forbidden in (
            "modeling",
            "residual_ridge",
            "nested_walk_forward",
            "commodity_features",
            "industry_conditioning",
            "feature_target_assembly",
        ):
            assert forbidden not in source, f"{module.__name__} imports {forbidden}"


def test_d3_does_not_write_b4_or_d1_outputs():
    source = (ROOT / "scripts" / "run_d3_operational_baselines.py").read_text("utf-8")
    for protected in (
        "b4_baseline_results.json",
        "d1_development_results.json",
        "b4_locked_test_manifest.json",
    ):
        assert 'w", encoding' not in source.split(protected)[0][-80:], protected
    assert "d3_operational_predictions.parquet" in source


@requires_results
def test_migration_timestamp_is_never_used_as_an_issue_date():
    """Synthetic failure: a migration-batch date must not become an issue date."""
    payload = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    audit = json.loads(
        (ROOT / "docs" / "d2_oie_mpi_source_audit.json").read_text(encoding="utf-8")
    )
    contaminated = {
        r["reference_month"]
        for r in audit["release_inventory"]["records"]
        if r["timing_evidence_class"] == "migration_batch_contaminated"
    }
    for contract in payload["origin_contracts"]:
        assert OC.month_label(contract["release_reference_month"]) not in contaminated


def test_unresolved_release_date_raises():
    """Synthetic failure: no credible release evidence for the required month."""
    with pytest.raises(OC.UnresolvedReleaseError):
        OC.build_origin_contracts(["2024-01-01"], CONFIG, {})


def test_issue_date_before_release_raises():
    """Synthetic failure: issue date earlier than the OIE release."""
    index = OC.load_release_index()
    contract = OC.OriginContract(
        forecast_origin_month="2024-01-01",
        forecast_issue_date="2024-01-02",  # before the real 2024-01-31 release
        forecast_issue_datetime_utc="2024-01-02T00:00:00+00:00",
        latest_available_stress_month="2023-12-01",
        calibration_reference_end="2023-12-01",
        release_reference_month="2023-12-01",
        publication_month="2024-01",
        publication_lag_days=30,
        timing_evidence_class="attachment_corroborated",
    )
    with pytest.raises(OC.ReleaseTimingError):
        OC.assert_issue_date_not_before_release(contract, index)


def test_reference_month_that_is_not_t_minus_one_raises():
    """Synthetic failure: release record describes the wrong reference month."""
    index = {
        "2023-12-01": {
            "reference_month": "2023-11-01",  # wrong month
            "release_datetime_utc": "2024-01-31T00:00:00+00:00",
            "release_date": "2024-01-31",
            "publication_month": "2024-01",
            "timing_evidence_class": "attachment_corroborated",
            "publication_lag_days": 30,
        }
    }
    with pytest.raises(OC.ReleaseTimingError):
        OC.build_origin_contracts(["2024-01-01"], CONFIG, index)


@requires_results
def test_results_are_deterministic_across_reruns(run):
    """Re-running the walk-forward reproduces identical predictions."""
    monthly, labels = WF.load_b3_artifacts()
    again = OWF.run_operational_walk_forward(
        monthly=monthly, labels=labels, config=CONFIG
    )
    pd.testing.assert_frame_equal(run.predictions, again.predictions)
