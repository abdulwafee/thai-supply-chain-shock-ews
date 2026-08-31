"""Task D4 tests — the frozen operational commodity model.

The specification is frozen, so most of these tests exist to prove it cannot be
unfrozen by accident: alpha cannot move off 100, no grid can be introduced, and
neither shared-sector metal can reach a matrix, a scaler or an artifact. The
synthetic failures matter more than the happy paths.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from thai_supply_chain_ews.evaluation.splits import add_months
from thai_supply_chain_ews.modeling import feature_target_assembly as FTA
from thai_supply_chain_ews.modeling import fixed_operational_ridge as FOR
from thai_supply_chain_ews.modeling import operational_feature_target_assembly as OFTA
from thai_supply_chain_ews.modeling import operational_model_comparison as CMP
from thai_supply_chain_ews.modeling.operational_model_artifacts import (
    OPERATIONAL_MODEL_PREDICTION_COLUMNS,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "d4_operational_model.yaml").read_text(encoding="utf-8")
)
RESULTS = ROOT / "docs" / "d4_operational_model_results.json"
PREDICTIONS = ROOT / "data" / "model_input" / "d4_operational_model_predictions.parquet"
PRIMARY = "primary_direct_lag2"

requires_run = pytest.mark.skipif(not RESULTS.is_file(), reason="D4 has not been run")


def _results():
    return json.loads(RESULTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def predictions():
    if not PREDICTIONS.is_file():
        pytest.skip("D4 predictions not built")
    return pd.read_parquet(PREDICTIONS)


@pytest.fixture(scope="module")
def index():
    rows = pd.read_parquet(ROOT / "data/features/c4_canonical_long.parquet").to_dict("records")
    return FTA.build_feature_index(rows, PRIMARY)


# ---------------------------------------------------------------------------
# 1. Framing: exploratory, never confirmatory
# ---------------------------------------------------------------------------
def test_config_declares_the_evaluation_exploratory():
    framing = CONFIG["evidence_framing"]
    assert framing["specification_frozen_after_d1_results"] is True
    assert framing["confirmatory_evaluation"] is False
    assert framing["exploratory_development_evaluation"] is True
    assert framing["nested_model_selection_performed"] is False
    assert framing["locked_test_eligible"] is False
    assert framing["preregistered_before_all_development_outcomes"] is False


@requires_run
def test_results_never_claim_preregistration_or_approval():
    payload = _results()
    assert payload["evidence_framing"]["confirmatory_evaluation"] is False
    for key in ("approved_for_locked_test", "production_model_approved", "confirmatory_result"):
        assert payload["safety"][key] is False
    for horizon in ("1", "3"):
        decision = payload["evaluation"][horizon]["decision"]
        assert decision["approved_for_locked_test"] is False
        assert decision["production_model_approved"] is False
        assert decision["confirmatory_result"] is False


# ---------------------------------------------------------------------------
# 2. Upstream invariants
# ---------------------------------------------------------------------------
@requires_run
def test_d3_invariants_reproduced():
    d3 = _results()["upstream_invariants"]["d3"]
    assert d3["issue_months"] == 15
    assert d3["development_start"] == "2024-01"
    assert d3["development_end"] == "2025-03"
    assert d3["latest_stress_is_t_minus_1"] is True
    assert d3["calibration_ends_at_t_minus_1"] is True
    assert d3["benchmarks"]["1"] == "operational_persistence_latest_published"
    assert d3["benchmarks"]["3"] == "operational_persistence_trailing_3m_max"
    assert d3["secondary_comparator"] == "operational_no_contraction"
    assert d3["locked_test_evaluated"] is False


@requires_run
def test_c4_invariants_reproduced():
    c4 = _results()["upstream_invariants"]["c4"]
    assert c4["eligible_pairs"] == 43
    assert c4["ineligible_pairs"] == 5
    assert c4["ind06_rubber_eligible"] is False
    assert c4["forbidden_variant_absent"] is True
    assert set(c4["variants_present"]) == {
        PRIMARY, "timing_sensitivity_direct_lag1", "structural_sensitivity_total_lag2"
    }


@requires_run
def test_history_ceiling_recorded_and_not_retested():
    ceiling = _results()["upstream_invariants"]["history_ceiling"]
    assert ceiling["raw_stress_begins"] == "2022-01"
    assert ceiling["first_origin_with_24_observations"] == "2024-01"
    assert ceiling["compatible_pre_2022_history_available"] is False
    assert ceiling["cross_base_splicing_permitted"] is False
    assert ceiling["development_origin_extension_supported"] is False
    assert ceiling["development_origin_count_ceiling"] == 15
    assert ceiling["new_feasibility_test_performed"] is False


@requires_run
def test_no_origin_before_2024_01_is_evaluated(predictions):
    assert predictions["forecast_origin_month"].min() == "2024-01-01"
    assert predictions["forecast_origin_month"].max() == "2025-03-01"
    assert predictions["forecast_origin_month"].nunique() == 15


# ---------------------------------------------------------------------------
# 3. The specification is frozen
# ---------------------------------------------------------------------------
def test_alpha_and_channel_are_constants():
    assert FOR.FIXED_ALPHA == 100.0
    assert FOR.FIXED_CHANNEL == "none"
    assert CONFIG["model"]["alpha"] == 100.0
    assert CONFIG["model"]["nonferrous_channel"] == "none"


def _tiny_design(n=8, k=3, seed=0):
    rng = np.random.default_rng(seed)
    names = [f"brent_crude_usd_bbl__f{i}" for i in range(k)]
    return names, rng.normal(size=(n, k)), rng.normal(size=n)


def test_changing_alpha_raises():
    """Synthetic failure: alpha moved off 100."""
    names, matrix, residuals = _tiny_design()
    with pytest.raises(FOR.FrozenSpecificationError):
        FOR.fit_fixed_operational_ridge("IND-01", 1, names, matrix, residuals, alpha=10.0)
    with pytest.raises(FOR.FrozenSpecificationError):
        FOR.fit_fixed_operational_ridge("IND-01", 1, names, matrix, residuals, alpha=100.5)


def test_changing_channel_raises():
    names, matrix, residuals = _tiny_design()
    with pytest.raises(FOR.FrozenSpecificationError):
        FOR.fit_fixed_operational_ridge(
            "IND-01", 1, names, matrix, residuals, non_ferrous_channel="copper"
        )


def test_fitted_model_always_reports_alpha_100():
    names, matrix, residuals = _tiny_design()
    model = FOR.fit_fixed_operational_ridge("IND-01", 1, names, matrix, residuals)
    assert model.alpha == 100.0
    assert model.non_ferrous_channel == "none"


def test_no_grid_or_inner_validation_exists_in_d4_code():
    """Synthetic failure: an inner grid search added."""
    for module in (FOR, OFTA):
        source = inspect.getsource(module)
        for forbidden in ("ALPHA_GRID", "select_configuration", "inner_validation",
                          "nested_walk_forward", "GridSearch"):
            assert forbidden not in source, f"{module.__name__} contains {forbidden}"
    runner = (ROOT / "scripts" / "run_d4_operational_model.py").read_text(encoding="utf-8")
    for forbidden in ("ALPHA_GRID", "select_configuration", "GridSearch", "alpha_grid"):
        assert forbidden not in runner


@requires_run
def test_every_row_carries_the_frozen_specification(predictions):
    assert (predictions["fixed_alpha"] == 100.0).all()
    assert (predictions["fixed_nonferrous_channel"] == "none").all()
    assert (predictions["model_name"] == FOR.MODEL_NAME).all()


# ---------------------------------------------------------------------------
# 4. Aluminum and Copper never appear
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("metal", ["aluminum_usd_mt", "copper_usd_mt"])
def test_inserting_a_metal_predictor_raises(metal):
    """Synthetic failure: Aluminum or Copper inserted."""
    names = ["brent_crude_usd_bbl__price_level", f"{metal}__price_level"]
    rng = np.random.default_rng(1)
    with pytest.raises(FOR.FrozenSpecificationError):
        FOR.fit_fixed_operational_ridge(
            "IND-01", 1, names, rng.normal(size=(8, 2)), rng.normal(size=8)
        )


@pytest.mark.parametrize("metal", ["aluminum_usd_mt", "copper_usd_mt"])
def test_assert_no_excluded_commodity_catches_each_metal(metal):
    with pytest.raises(FOR.FrozenSpecificationError):
        FOR.assert_no_excluded_commodity([f"{metal}__log_change_1m_pct"], "test")


@requires_run
def test_no_metal_predictor_in_any_prediction_row(predictions):
    for column in ("predictor_names", "omitted_zero_variance_predictors"):
        joined = " ".join(predictions[column].fillna("").astype(str))
        assert "aluminum_usd_mt__" not in joined
        assert "copper_usd_mt__" not in joined
    assert not predictions["aluminum_predictors_present"].any()
    assert not predictions["copper_predictors_present"].any()
    assert not predictions["shared_io_sector_107_used"].any()


@requires_run
def test_results_declare_sector_107_unused():
    spec = _results()["frozen_specification"]
    assert spec["aluminum_predictors_present"] is False
    assert spec["copper_predictors_present"] is False
    assert spec["shared_io_sector_107_used"] is False
    assert set(spec["excluded_commodities"]) == {"aluminum_usd_mt", "copper_usd_mt"}


# ---------------------------------------------------------------------------
# 5. Predictors: transformations, IND-06, no zero-filling
# ---------------------------------------------------------------------------
def test_all_five_transformations_are_registered():
    assert list(CONFIG["transformations"]) == list(FTA.REGISTERED_TRANSFORMATIONS)
    assert len(CONFIG["transformations"]) == 5


def test_eligible_industry_receives_five_transformations_per_commodity(index):
    vector = FTA.features_as_of(index, "2024-01-01", "IND-01", non_ferrous_channel="none")
    names = vector["predictor_names"]
    assert len(names) == 10
    for commodity in ("brent_crude_usd_bbl", "rubber_rss3_usd_kg"):
        got = {n.split("__", 1)[1] for n in names if n.startswith(commodity + "__")}
        assert got == set(FTA.REGISTERED_TRANSFORMATIONS)


def test_ind06_receives_no_rubber_predictor(index):
    """Synthetic failure guard: Rubber inserted for IND-06."""
    vector = FTA.features_as_of(index, "2024-01-01", "IND-06", non_ferrous_channel="none")
    names = vector["predictor_names"]
    assert len(names) == 5
    assert all(n.startswith("brent_crude_usd_bbl__") for n in names)
    assert not any("rubber" in n for n in names)


def test_ind06_rubber_is_omitted_not_zero_filled(index):
    """Synthetic failure guard: ineligible predictor replaced with zero."""
    vector = FTA.features_as_of(index, "2024-01-01", "IND-06", non_ferrous_channel="none")
    omitted = vector["omitted_ineligible_predictors"]
    assert len(omitted) == 5
    assert all(n.startswith("rubber_rss3_usd_kg__") for n in omitted)
    assert not any(n in vector["predictor_names"] for n in omitted)
    assert len(vector["values"]) == len(vector["predictor_names"])


@requires_run
def test_ind06_rows_never_carry_rubber(predictions):
    rows = predictions[
        (predictions["industry_id"] == "IND-06")
        & (predictions["feature_variant"] == PRIMARY)
    ]
    assert len(rows) == 30
    assert not rows["predictor_names"].astype(str).str.contains("rubber").any()
    assert rows["omitted_ineligible_predictors"].astype(str).str.contains("rubber").all()


# ---------------------------------------------------------------------------
# 6. Temporal cutoffs
# ---------------------------------------------------------------------------
@requires_run
def test_calibration_ends_at_t_minus_one(predictions):
    expected = predictions["forecast_origin_month"].map(lambda o: add_months(o, -1))
    assert (predictions["calibration_reference_end"] == expected).all()
    assert (predictions["latest_available_stress_month"] == expected).all()
    assert (
        predictions["latest_available_stress_month"] < predictions["forecast_origin_month"]
    ).all()


@requires_run
def test_training_label_availability_never_exceeds_issue_origin(predictions):
    assert (
        predictions["max_training_target_available_month"]
        <= predictions["forecast_origin_month"]
    ).all()


def test_historical_benchmark_uses_stress_before_u():
    stress = {f"2023-{m:02d}-01": float(m) for m in range(1, 13)}
    assert OFTA.historical_benchmark_raw(stress, "2023-06-01", 1) == 5.0
    assert OFTA.historical_benchmark_raw(stress, "2023-06-01", 3) == 5.0
    # month u itself is never read: raising u's value must not change the answer
    stress["2023-06-01"] = 999.0
    assert OFTA.historical_benchmark_raw(stress, "2023-06-01", 1) == 5.0
    assert OFTA.historical_benchmark_raw(stress, "2023-06-01", 3) == 5.0


def test_historical_benchmark_rejects_an_unsupported_horizon():
    """Synthetic failure: a horizon whose window is not defined."""
    stress = {f"2023-{m:02d}-01": float(m) for m in range(1, 13)}
    with pytest.raises(OFTA.OperationalAssemblyError):
        OFTA.historical_benchmark_raw(stress, "2023-06-01", 0)
    with pytest.raises(OFTA.OperationalAssemblyError):
        OFTA.historical_benchmark_raw(stress, "2023-06-01", 6)


def test_historical_benchmark_never_reads_month_u_itself():
    """Synthetic failure guard: use of stress S_t at the training origin."""
    stress = {f"2023-{m:02d}-01": float(m) for m in range(1, 13)}
    baseline_h1 = OFTA.historical_benchmark_raw(stress, "2023-06-01", 1)
    baseline_h3 = OFTA.historical_benchmark_raw(stress, "2023-06-01", 3)
    poisoned = dict(stress)
    poisoned["2023-06-01"] = 10_000.0
    poisoned["2023-07-01"] = 10_000.0
    assert OFTA.historical_benchmark_raw(poisoned, "2023-06-01", 1) == baseline_h1
    assert OFTA.historical_benchmark_raw(poisoned, "2023-06-01", 3) == baseline_h3


def test_historical_benchmark_returns_none_before_series_start():
    """A window reaching before the series began is not a timing violation."""
    stress = {f"2022-{m:02d}-01": float(m) for m in range(1, 13)}
    assert OFTA.historical_benchmark_raw(stress, "2022-03-01", 3) is None
    assert OFTA.historical_benchmark_raw(stress, "2022-03-01", 1) == 2.0


def test_label_available_after_outer_origin_raises():
    """Synthetic failure: label available after the outer issue date."""
    labels_by_key = {
        ("2023-12-01", "IND-01", 1): {
            "target_window_end": "2024-01-01",   # available 2024-02
            "target_raw_value": 1.0,
        }
    }

    class _Calibrator:
        def transform(self, industry_id, value):
            return np.atleast_1d(np.asarray(value, dtype=float))

    with pytest.raises(OFTA.OperationalAssemblyError):
        OFTA.assemble_operational_training(
            index=None,
            labels_by_key=labels_by_key,
            permitted_origins=["2023-12-01"],
            industry_id="IND-01",
            horizon=1,
            outer_origin="2024-01-01",
            calibrator=_Calibrator(),
            stress_by_month={},
        )


def test_non_none_channel_is_rejected_by_the_assembly():
    with pytest.raises(OFTA.OperationalAssemblyError):
        OFTA.assemble_operational_training(
            index=None, labels_by_key={}, permitted_origins=[], industry_id="IND-01",
            horizon=1, outer_origin="2024-01-01", calibrator=None, stress_by_month={},
            non_ferrous_channel="copper",
        )


def test_historical_features_are_frozen_at_u_not_refreshed_at_t(index):
    """Synthetic failure guard: historical row refreshed with future info."""
    early = FTA.features_as_of(index, "2023-01-01", "IND-04", non_ferrous_channel="none")
    late = FTA.features_as_of(index, "2024-01-01", "IND-04", non_ferrous_channel="none")
    assert early["reference_months"] != late["reference_months"]
    for reference in early["reference_months"].values():
        assert str(reference) <= "2023-01-01"


# ---------------------------------------------------------------------------
# 7. Training counts
# ---------------------------------------------------------------------------
@requires_run
def test_training_count_reconciliation_is_reported():
    rows = _results()["training_count_reconciliation"]
    assert len(rows) == 4
    for row in rows:
        assert row["label_permitted_matches"] is True, row


@requires_run
def test_h1_training_counts_match_the_brief_exactly():
    rows = {
        (r["horizon"], r["outer_origin"]): r
        for r in _results()["training_count_reconciliation"]
    }
    for origin, expected in (("2024-01", 252), ("2025-03", 420)):
        row = rows[(1, origin)]
        assert row["feature_usable_actual"] == expected
        assert row["feature_usable_matches"] is True


@requires_run
def test_h3_deviation_is_reported_with_its_reason():
    """h=3 loses one more origin than the brief anticipated, and says why."""
    rows = {
        (r["horizon"], r["outer_origin"]): r
        for r in _results()["training_count_reconciliation"]
    }
    for origin, expected_actual in (("2024-01", 216), ("2025-03", 384)):
        row = rows[(3, origin)]
        assert row["feature_usable_actual"] == expected_actual
        assert row["feature_usable_matches"] is False
        assert "2022-03-01" in row["excluded_benchmark_origins"]
        assert "before" in row["deviation_reason"]
        assert "not imputed" in row["deviation_reason"]


@requires_run
def test_feature_gate_excludes_exactly_the_two_pre_2022_03_origins():
    for row in _results()["training_count_reconciliation"]:
        assert row["excluded_feature_origins"] == ["2022-01-01", "2022-02-01"]


# ---------------------------------------------------------------------------
# 8. Residual formula, benchmark choice, clipping
# ---------------------------------------------------------------------------
@requires_run
def test_prediction_equals_benchmark_plus_residual_then_clipped(predictions):
    unclipped = predictions["d3_benchmark_prediction"] + predictions["predicted_residual"]
    assert np.allclose(unclipped, predictions["unclipped_prediction"])
    expected = unclipped.clip(0.0, 100.0)
    assert np.allclose(expected, predictions["predicted_score"])
    assert (predictions["clipped"] == (unclipped != expected)).all()
    assert predictions["predicted_score"].between(0.0, 100.0).all()


@requires_run
def test_each_horizon_uses_its_own_d3_benchmark(predictions):
    h1 = predictions[predictions["horizon_months"] == 1]
    h3 = predictions[predictions["horizon_months"] == 3]
    assert set(h1["d3_benchmark_name"]) == {"operational_persistence_latest_published"}
    assert set(h3["d3_benchmark_name"]) == {"operational_persistence_trailing_3m_max"}


@requires_run
def test_degenerate_rows_predict_exactly_the_benchmark(predictions):
    degenerate = predictions[predictions["model_quality"] != "ok"]
    assert (degenerate["predicted_residual"] == 0.0).all()
    assert np.allclose(
        degenerate["unclipped_prediction"], degenerate["d3_benchmark_prediction"]
    )
    assert (degenerate["predictor_count"] == 0).all()


@requires_run
def test_degenerate_summary_is_reported():
    summary = _results()["degenerate_design_summary"][PRIMARY]
    assert summary["rows_degenerate"] > 0
    assert summary["degenerate_industries"]
    assert "structural constant" in summary["meaning"]


# ---------------------------------------------------------------------------
# 9. Counts, keys, ordering
# ---------------------------------------------------------------------------
@requires_run
def test_primary_and_structural_have_exactly_180_rows_per_horizon(predictions):
    for variant in (PRIMARY, "structural_sensitivity_total_lag2"):
        for horizon in (1, 3):
            subset = predictions[
                (predictions["feature_variant"] == variant)
                & (predictions["horizon_months"] == horizon)
            ]
            assert len(subset) == 180, (variant, horizon)


@requires_run
def test_timing_sensitivity_rows_match_verified_available_origins(predictions):
    availability = _results()["timing_sensitivity_availability"]
    expected = len(availability["available_origins"]) * 12
    for horizon in (1, 3):
        subset = predictions[
            (predictions["feature_variant"] == "timing_sensitivity_direct_lag1")
            & (predictions["horizon_months"] == horizon)
        ]
        assert len(subset) == expected
    assert availability["imputed"] is False
    assert availability["substituted_with_primary"] is False


@requires_run
def test_timing_day_level_check_compares_publication_to_issue_date():
    availability = _results()["timing_sensitivity_availability"]
    assert availability["rule"].startswith("commodity_first_seen_issue_date")
    for row in availability["per_origin"]:
        if row["state"] == "available":
            assert row["commodity_publication_date"] <= row["d3_issue_date"]
            assert row["availability_status"] == "verified_from_archived_issue"


@requires_run
def test_total_prediction_count_within_maximum(predictions):
    assert len(predictions) <= CONFIG["expected_prediction_counts"]["maximum_total"]
    assert len(predictions) == _results()["prediction_counts"]["total"]


@requires_run
def test_keys_unique_and_ordering_deterministic(predictions):
    key = ["forecast_origin_month", "industry_id", "horizon_months", "feature_variant"]
    assert not predictions.duplicated(subset=key).any()
    ordered = predictions.sort_values(
        ["feature_variant", "horizon_months", "industry_id", "forecast_origin_month"],
        kind="mergesort",
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(predictions, ordered)


@requires_run
def test_schema_columns_match_the_written_table(predictions):
    schema = yaml.safe_load(
        (ROOT / "schemas" / "operational_model_prediction.schema.yaml").read_text("utf-8")
    )
    declared = [c["name"] for c in schema["operational_model_prediction"]["columns"]]
    assert list(predictions.columns) == OPERATIONAL_MODEL_PREDICTION_COLUMNS
    for name in declared:
        assert name in predictions.columns, name


@requires_run
def test_no_purge_or_locked_origin(predictions):
    months = {str(m)[:7] for m in predictions["forecast_origin_month"]}
    assert not (months & {"2025-04", "2025-05", "2025-06"})
    assert max(months) <= "2025-03"


# ---------------------------------------------------------------------------
# 10. Evidence and safety decisions
# ---------------------------------------------------------------------------
def test_mae_evidence_requires_the_whole_interval_below_zero():
    assert CMP.assign_mae_evidence(10.0, 12.0, {"ci_low": -3.0, "ci_high": -1.0}) == (
        "incremental_signal_supported"
    )
    assert CMP.assign_mae_evidence(10.0, 12.0, {"ci_low": -3.0, "ci_high": 1.0}) == (
        "incremental_signal_inconclusive"
    )
    assert CMP.assign_mae_evidence(12.0, 12.0, {"ci_low": -3.0, "ci_high": -1.0}) == (
        "incremental_signal_not_supported"
    )
    assert CMP.assign_mae_evidence(13.0, 12.0, {"ci_low": -3.0, "ci_high": -1.0}) == (
        "incremental_signal_not_supported"
    )


def test_event_safety_boundary_is_inclusive():
    assert CMP.assign_event_safety(5, 5) == "event_safety_passed"
    assert CMP.assign_event_safety(4, 5) == "event_safety_passed"
    assert CMP.assign_event_safety(6, 5) == "event_safety_failed"


def test_advancement_requires_both_gates():
    assert CMP.advancement_decision(
        "incremental_signal_supported", "event_safety_passed"
    )["development_candidate_supported"] is True
    for mae, event in (
        ("incremental_signal_supported", "event_safety_failed"),
        ("incremental_signal_inconclusive", "event_safety_passed"),
        ("incremental_signal_not_supported", "event_safety_passed"),
    ):
        decision = CMP.advancement_decision(mae, event)
        assert decision["development_candidate_supported"] is False
        assert decision["approved_for_locked_test"] is False


def test_high_stress_threshold_is_85_and_untuned():
    assert CONFIG["metrics"]["high_stress"]["threshold"] == 85
    assert CONFIG["metrics"]["high_stress"]["threshold_tuned"] is False


def test_bootstrap_settings_are_dependence_aware():
    bootstrap = CONFIG["bootstrap"]
    assert bootstrap["cluster_by"] == "issue_month"
    assert bootstrap["preserve_all_industries"] is True
    assert bootstrap["block_length_months"] == 3
    assert bootstrap["replications"] >= 1000
    assert bootstrap["rows_treated_as_independent"] is False


@requires_run
def test_reported_statuses_follow_the_registered_rule():
    payload = _results()
    for horizon in ("1", "3"):
        block = payload["evaluation"][horizon]
        model_mae = block["model"]["macro_industry_mae"]
        benchmark_mae = block["operational_persistence"]["macro_industry_mae"]
        paired = block["vs_operational_persistence"][
            "paired_difference_model_minus_comparator"
        ]
        assert block["mae_evidence_status"] == CMP.assign_mae_evidence(
            model_mae, benchmark_mae, paired
        )
        assert block["event_safety_status"] == CMP.assign_event_safety(
            block["model"]["high_stress"]["false_negative"],
            block["operational_persistence"]["high_stress"]["false_negative"],
        )


@requires_run
def test_no_contraction_reported_as_secondary_comparator():
    for horizon in ("1", "3"):
        block = _results()["evaluation"][horizon]
        assert "operational_no_contraction" in block
        assert "vs_no_contraction" in block
        assert block["vs_operational_persistence"]["paired_sign_convention"].startswith(
            "negative"
        )


# ---------------------------------------------------------------------------
# 11. Sensitivities cannot promote themselves
# ---------------------------------------------------------------------------
@requires_run
def test_sensitivities_are_reported_separately_and_cannot_change_primary():
    """Synthetic failure guard: a sensitivity result replacing the primary."""
    payload = _results()
    for horizon in ("1", "3"):
        block = payload["evaluation"][horizon]
        for variant, sensitivity in block["sensitivities"].items():
            assert variant != PRIMARY
            if sensitivity.get("rows"):
                assert sensitivity["reported_separately"] is True
                assert sensitivity["may_change_primary_status"] is False
        # the status must be derivable from the PRIMARY numbers alone
        assert block["mae_evidence_status"] == CMP.assign_mae_evidence(
            block["model"]["macro_industry_mae"],
            block["operational_persistence"]["macro_industry_mae"],
            block["vs_operational_persistence"]["paired_difference_model_minus_comparator"],
        )
    assert CONFIG["variants"]["sensitivity_may_change_primary_status"] is False
    assert CONFIG["advancement_gate"]["sensitivity_may_rescue_failed_primary"] is False


def test_forbidden_lag1_total_variant_is_never_built():
    assert CONFIG["variants"]["forbidden_combination"] == "lag1_plus_total_requirement"
    rows = pd.read_parquet(ROOT / "data/features/c4_canonical_long.parquet")
    assert "lag1_plus_total_requirement" not in set(rows["matrix_variant"])
    runner = (ROOT / "scripts" / "run_d4_operational_model.py").read_text(encoding="utf-8")
    assert "lag1_plus_total" not in runner


# ---------------------------------------------------------------------------
# 12. Isolation from upstream artifacts and the locked test
# ---------------------------------------------------------------------------
def test_d4_does_not_overwrite_d1_or_d3_outputs():
    runner = (ROOT / "scripts" / "run_d4_operational_model.py").read_text(encoding="utf-8")
    for protected in (
        "d1_development_results.json",
        "d3_operational_baseline_results.json",
        "d3_operational_predictions.parquet",
    ):
        assert f'"{protected}"' not in runner
    assert "d4_operational_model_predictions.parquet" in runner


def test_runner_cannot_reach_the_locked_test():
    """Synthetic failure guard: a locked origin through an internal API."""
    runner = (ROOT / "scripts" / "run_d4_operational_model.py").read_text(encoding="utf-8")
    assert "locked_test_origins" not in runner
    assert "--locked" not in runner
    assert "os.environ" not in runner
    source = inspect.getsource(OFTA)
    assert "locked" not in source.lower() or "locked_test_origins" not in source


@requires_run
def test_locked_test_remains_unopened():
    payload = _results()
    assert payload["safety"]["locked_test_accessed"] is False
    assert payload["upstream_invariants"]["d3"]["locked_test_evaluated"] is False


def test_industry_models_are_not_pooled():
    source = inspect.getsource(OFTA.assemble_operational_training)
    assert "industry_id" in source
    names, matrix, residuals = _tiny_design(seed=3)
    a = FOR.fit_fixed_operational_ridge("IND-01", 1, names, matrix, residuals)
    names_b, matrix_b, residuals_b = _tiny_design(seed=7)
    b = FOR.fit_fixed_operational_ridge("IND-02", 1, names_b, matrix_b, residuals_b)
    assert a.checksum() != b.checksum()


def test_zero_variance_detection_ignores_the_outcome():
    """Changing y must not change which predictors are retained."""
    names, matrix, residuals = _tiny_design(seed=11)
    first = FOR.fit_fixed_operational_ridge("IND-01", 1, names, matrix, residuals)
    second = FOR.fit_fixed_operational_ridge("IND-01", 1, names, matrix, residuals * 5.0 + 3.0)
    assert first.retained_predictors == second.retained_predictors
    assert first.omitted_zero_variance == second.omitted_zero_variance
    assert first.scaler.checksum() == second.scaler.checksum()
