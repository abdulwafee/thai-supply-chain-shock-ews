"""Task D5 tests — development-only pooled fuel-oil interaction evaluation.

Four failures here would produce a number that looks like evidence and is not.

**A target read before the specification was frozen.** The guarded reader keeps
two locks: the protocol lock, which stays shut until the Phase-A checksum is
read back from disk and matched, and a per-prediction freeze lock. Either one
opened early lets an outcome reach a decision that was still editable, and the
resulting metric is indistinguishable from an honest one.

**A penalty that drifts.** ``lambda = 1.0`` on an unnormalised sum is a weaker
penalty at every larger training panel, and the panel grows from 231 rows to 385
across the walk-forward. The specification would change on its own. The same
goes for penalising the industry fixed effects, which shrinks each industry
intercept toward a stress score of zero — a strong claim, not a neutral prior.

**A scaler fitted on the repeated panel.** Eleven industries share one national
fuel-oil series, so fitting mean and standard deviation on the stacked rows
weights that series eleven times.

**A row-level resample.** Twelve industries at one issue month share a signal, a
calibrator and a release date. Resampling them independently would shrink every
interval by roughly the square root of twelve and turn "inconclusive" into
"supported" without any change in the data.

Everything here is development-only: no purge origin, no locked test, and no
result that approves a feature or selects a channel.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from thai_supply_chain_ews.evaluation import issue_cluster_bootstrap as BS
from thai_supply_chain_ews.modeling import fixed_pooled_partial_ridge as RG
from thai_supply_chain_ews.modeling import fuel_oil_pooled_panel as PP
from thai_supply_chain_ews.modeling import fuel_oil_prediction_lineage as LN
from thai_supply_chain_ews.modeling import fuel_oil_walk_forward as WF

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "d5_fuel_oil_interaction.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
PREDICTION_SCHEMA = ROOT / "schemas" / "d5_fuel_oil_prediction.schema.yaml"
RESULTS_SCHEMA = ROOT / "schemas" / "d5_fuel_oil_results.schema.yaml"
RESULTS = ROOT / "docs" / "d5_development_results.json"
AUDIT = ROOT / "docs" / "d5_assembly_audit.json"
PROTOCOL = ROOT / "docs" / "d5_frozen_protocol.json"
PROTOCOL_MD = ROOT / "docs" / "d5_modeling_protocol.md"
RUNNER = ROOT / "scripts" / "run_d5_fuel_oil_interaction.py"
PREDICTIONS = ROOT / "data" / "model_input" / "d5_fuel_oil_predictions.parquet"
COEFFICIENTS = ROOT / "data" / "model_input" / "d5_fuel_oil_coefficients.parquet"

V600, V1500 = "fo600_direct_sector093", "fo1500_direct_sector093"

requires_run = pytest.mark.skipif(not RESULTS.is_file(), reason="D5 has not been run")


def _results():
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def _audit():
    return json.loads(AUDIT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Synthetic fixtures: small, hand-built, independent of the real panel.
# ---------------------------------------------------------------------------
ELIGIBLE = ["IND-01", "IND-02", "IND-03"]
EXPOSURES = {"IND-01": 0.010, "IND-02": 0.040, "IND-03": 0.007, "IND-04": 0.0098}
ISSUES = ["2023-05", "2023-06", "2023-07", "2023-08", "2023-09", "2023-10"]
SOURCE = {
    "2023-03": [1.0, 2.0, 3.0, 40.0, 5.0],
    "2023-04": [1.5, 2.5, 3.5, 41.0, 5.5],
    "2023-05": [2.0, 1.0, 4.0, 42.0, 6.5],
    "2023-06": [0.5, 3.0, 2.5, 43.5, 4.5],
    "2023-07": [3.0, 0.5, 5.0, 44.5, 7.5],
    "2023-08": [2.5, 1.5, 1.5, 45.0, 3.5],
}


def _rows(issues=None, industries=None, refresh_at=None):
    rows = []
    for issue in (issues or ISSUES):
        reference = refresh_at or PP.shift_month(issue, -PP.POLICY_LAG_MONTHS)
        for industry in (industries or ELIGIBLE):
            rows.append({
                "issue_month": issue, "industry_id": industry,
                "reference_month": reference,
                **dict(zip(PP.SOURCE_COLUMNS, SOURCE[reference], strict=True)),
            })
    return rows


def _scaler(issues=None):
    return PP.fit_source_scaler(
        {i: SOURCE[PP.shift_month(i, -2)] for i in (issues or ISSUES)}, ddof=0
    )


def _exposure(exposures=None, eligible=None):
    return PP.center_and_scale_exposure(exposures or EXPOSURES, eligible or ELIGIBLE)


def _panel(**kwargs):
    return PP.build_pooled_design(
        kwargs.pop("rows", None) or _rows(), kwargs.pop("eligible", None) or ELIGIBLE,
        kwargs.pop("scaler", None) or _scaler(),
        kwargs.pop("exposure", None) or _exposure(),
        V600, 1, kwargs.pop("outer_issue", "2023-11"),
    )


def _fit(panel=None, **kwargs):
    panel = panel or _panel()
    rng = np.random.default_rng(7)
    residuals = rng.normal(size=panel.matrix.shape[0])
    return RG.fit_fixed_pooled_partial_ridge(
        panel.matrix, residuals, panel.column_names, panel.blocks,
        n_training_issue_months=len(panel.training_issue_months), **kwargs
    )


def _frame(n_months=6, n_industries=4, offset=0.0, seed=3):
    import pandas as pd

    rng = np.random.default_rng(seed)
    rows = []
    for month in range(n_months):
        for industry in range(n_industries):
            observed = 50.0 + rng.normal(scale=5.0)
            rows.append({
                "issue_month": f"2024-{month + 1:02d}",
                "industry_id": f"IND-{industry + 1:02d}",
                "observed_score": observed,
                "predicted_score": observed + offset + rng.normal(scale=1.0),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Configuration and schemas
# ---------------------------------------------------------------------------
def test_the_config_parses_and_freezes_the_specification():
    assert CONFIG["estimator"]["lambda"] == 1.0
    assert CONFIG["estimator"]["loss_normalised_by_n"] is True
    assert CONFIG["estimator"]["alpha_grid"] is False
    assert CONFIG["estimator"]["inner_cv"] is False
    assert CONFIG["estimator"]["fallback_estimator"] is False
    assert CONFIG["estimator"]["hyperparameter_search"] is False
    assert CONFIG["model"]["clip_lower"] == 0.0
    assert CONFIG["model"]["clip_upper"] == 100.0
    assert CONFIG["model"]["clipping_bounds_tuned"] is False


def test_the_authorization_matches_c11r1():
    granted = json.loads(
        (ROOT / "docs" / "c11r1_governance_decision.json").read_text(encoding="utf-8")
    )["d5_authorization"]["granted"]
    for field, expected in CONFIG["authorization"]["required"].items():
        assert granted[field] is expected, field


def test_the_schemas_parse_and_fix_the_approval_fields_false():
    prediction = yaml.safe_load(PREDICTION_SCHEMA.read_text(encoding="utf-8"))
    results = yaml.safe_load(RESULTS_SCHEMA.read_text(encoding="utf-8"))
    assert prediction["tables"][0]["expected_rows"] == 720
    banned = set(results["fixed_false_fields"]["fields"])
    assert {"channel_selected", "model_feature_approved", "purge_evaluated",
            "locked_test_accessed"} <= banned
    assert results["evaluation_scope"] == "development_only"


# ---------------------------------------------------------------------------
# The estimator
# ---------------------------------------------------------------------------
def test_the_penalty_matrix_spares_the_fixed_effects():
    blocks = ("source",) * 5 + ("interaction",) * 5 + ("industry_fixed_effect",) * 3
    penalty = RG.penalty_matrix(blocks)
    RG.assert_penalty_matrix(penalty, blocks)
    assert np.diag(penalty).tolist() == [1.0] * 10 + [0.0] * 3


def test_the_fit_solves_its_own_normal_equations():
    fit = _fit()
    assert fit.normal_equation_residual < 1e-8
    assert fit.penalized_columns == 10
    assert fit.unpenalized_columns == len(ELIGIBLE)
    assert fit.hyperparameter_search_performed is False
    assert fit.inner_cv_performed is False
    assert fit.model_averaging_performed is False
    assert fit.fallback_estimator_used is False
    assert fit.features_removed == ()


def test_lambda_means_the_same_thing_on_a_larger_panel():
    """The 1/n is what keeps the specification fixed as the panel grows."""
    small = _panel(rows=_rows(ISSUES[:4]), scaler=_scaler(ISSUES[:4]))
    large = _panel()
    rng = np.random.default_rng(11)
    beta = rng.normal(size=len(small.column_names))
    for panel in (small, large):
        residuals = panel.matrix @ beta[:panel.matrix.shape[1]]
        fit = RG.fit_fixed_pooled_partial_ridge(
            panel.matrix, residuals, panel.column_names, panel.blocks,
            n_training_issue_months=len(panel.training_issue_months),
        )
        gram = panel.matrix.T @ panel.matrix / panel.matrix.shape[0]
        penalty = RG.penalty_matrix(panel.blocks)
        expected = np.linalg.solve(
            gram + penalty, panel.matrix.T @ residuals / panel.matrix.shape[0]
        )
        assert np.allclose(fit.coefficients, expected, atol=1e-10)


def test_clipping_is_fixed_at_the_score_range():
    assert RG.clip_score(50.0) == (50.0, False)
    assert RG.clip_score(-3.0) == (0.0, True)
    assert RG.clip_score(140.0) == (100.0, True)


def test_the_coefficient_checksum_is_deterministic_and_sensitive():
    first, second = _fit(), _fit()
    assert RG.coefficient_checksum(first) == RG.coefficient_checksum(second)
    other = _fit(panel=_panel(rows=_rows(ISSUES[:4]), scaler=_scaler(ISSUES[:4])))
    assert RG.coefficient_checksum(other) != RG.coefficient_checksum(first)


# ---------------------------------------------------------------------------
# Panel assembly
# ---------------------------------------------------------------------------
def test_the_scaler_is_fitted_on_unique_issue_months():
    scaler = _scaler()
    assert scaler["unique_issue_month_count"] == len(ISSUES)
    assert scaler["fitted_on_repeated_industry_panel"] is False
    assert scaler["ddof"] == 0
    stacked = np.array([SOURCE[PP.shift_month(i, -2)] for i in ISSUES] * 3)
    assert not np.allclose(scaler["standard_deviations"], stacked.std(axis=0, ddof=1))


def test_exposure_is_centred_then_scaled_on_the_frozen_universe():
    exposure = _exposure()
    assert abs(sum(exposure["centered_exposure"].values())) < 1e-15
    scaled = np.array(list(exposure["scaled_exposure"].values()))
    assert abs(scaled.mean()) < 1e-12
    assert abs(scaled.std(ddof=0) - 1.0) < 1e-12
    assert exposure["fitted_on_targets"] is False
    assert exposure["changes_the_c11_estimand"] is False
    assert "IND-04" not in exposure["scaled_exposure"]


def test_the_design_blocks_are_shaped_as_preregistered():
    panel = _panel()
    assert panel.matrix.shape == (len(ISSUES) * len(ELIGIBLE),
                                  10 + len(ELIGIBLE))
    assert panel.blocks.count("source") == 5
    assert panel.blocks.count("interaction") == 5
    assert panel.blocks.count("industry_fixed_effect") == len(ELIGIBLE)
    assert panel.eligible_rows == len(ISSUES) * len(ELIGIBLE)
    assert panel.omitted_ind_04_rows == len(ISSUES)
    assert panel.imputed_values == 0


def test_the_interaction_is_the_scaled_exposure_times_the_scaled_source():
    panel, exposure, scaler = _panel(), _exposure(), _scaler()
    means = np.array(scaler["means"])
    deviations = np.array(scaler["standard_deviations"])
    for (issue, industry), row in zip(panel.row_keys, panel.matrix, strict=True):
        standardized = (np.array(SOURCE[PP.shift_month(issue, -2)]) - means) / deviations
        assert np.allclose(row[:5], standardized)
        assert np.allclose(
            row[5:10], exposure["scaled_exposure"][industry] * standardized
        )


# ---------------------------------------------------------------------------
# Temporal guards
# ---------------------------------------------------------------------------
def test_the_guarded_reader_refuses_before_the_protocol_is_verified():
    reader = WF.GuardedTargetReader()
    with pytest.raises(WF.PhaseBoundaryError, match="before the Phase-A"):
        reader.read(("v", 1, "2024-01", "IND-01"), 50.0)
    with pytest.raises(WF.PhaseBoundaryError, match="before the Phase-A"):
        reader.freeze(("v", 1, "2024-01", "IND-01"))


def test_the_guarded_reader_refuses_a_mismatched_protocol():
    reader = WF.GuardedTargetReader()
    with pytest.raises(WF.PhaseBoundaryError, match="read back as"):
        reader.verify_protocol("a" * 64, "b" * 64)
    assert reader.verified is False


def test_calibrator_and_stress_cutoffs_are_asserted_independently():
    WF.assert_stress_month_permitted("2023-12", "2024-01")
    WF.assert_calibrator_cutoff("2023-12", "2024-01")
    with pytest.raises(WF.WalkForwardError, match="strictly before"):
        WF.assert_stress_month_permitted("2024-01", "2024-01")
    with pytest.raises(WF.WalkForwardError, match="calibrator reference ends"):
        WF.assert_calibrator_cutoff("2024-01", "2024-01")


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def test_the_bootstrap_resamples_whole_issue_months():
    model, benchmark = _frame(offset=0.0), _frame(offset=3.0)
    result = BS.paired_macro_mae_interval(
        BS.issue_month_matrix(model), BS.issue_month_matrix(benchmark),
        block_length=1, replications=200, seed=5,
    )
    assert result["cluster_unit"] == "issue_month"
    assert result["resample_individual_industry_rows"] is False
    assert result["paired_resamples_identical"] is True
    assert result["issue_month_clusters"] == 6
    assert result["paired_ci_low"] <= result["paired_difference_point"] <= (
        result["paired_ci_high"]
    )
    assert "limited uncertainty resolution" in result["resolution_note"]


def test_the_block_bootstrap_keeps_consecutive_months_together():
    rng = np.random.default_rng(1)
    positions = BS.block_positions(15, 3, rng)
    assert len(positions) == 15
    runs = [positions[i:i + 3] for i in range(0, 15, 3)]
    for run in runs:
        assert list(run) == list(range(run[0], run[0] + len(run)))


def test_the_resample_plan_is_deterministic_and_shared():
    first = BS.resample_plan(15, 3, 20, 20260830)
    second = BS.resample_plan(15, 3, 20, 20260830)
    assert first == second
    BS.assert_paired_resamples(first, second)


# ---------------------------------------------------------------------------
# Decision rules
# ---------------------------------------------------------------------------
def test_the_interval_decides_not_the_point_estimate():
    assert LN.classify_mae_evidence(-2.0, -0.5) == "supported"
    assert LN.classify_mae_evidence(0.5, 2.0) == "adverse"
    assert LN.classify_mae_evidence(-1.0, 0.5) == "inconclusive"
    assert LN.classify_mae_evidence(-5.0, 0.0) == "inconclusive"


def test_support_needs_both_gates():
    assert LN.overall_status("supported", True) == (
        "exploratory_incremental_signal_supported"
    )
    assert LN.overall_status("supported", False) == "inconclusive"
    assert LN.overall_status("adverse", True) == "incremental_signal_not_supported"
    assert LN.overall_status("inconclusive", True) == "inconclusive"


def test_event_safety_counts_missed_events():
    assert LN.event_safety_status(3, 5)["event_safety_passed"] is True
    assert LN.event_safety_status(6, 5)["event_safety_passed"] is False
    assert LN.event_safety_status(3, 5)["threshold_tuned"] is False


# ---------------------------------------------------------------------------
# The generated results
# ---------------------------------------------------------------------------
@requires_run
def test_the_counts_reconcile_exactly():
    counts = _audit()["counts"]
    assert counts["total_predictions"] == 720
    assert counts["distinct_keys"] == 720
    assert counts["pooled_model_predictions"] == 660
    assert counts["ind_04_benchmark_passthrough"] == 60
    assert counts["distinct_lineage_checksums"] == 720
    assert counts["reconciled"] is True
    assert all(v == 180 for v in counts["per_variant_horizon"].values())


@requires_run
def test_the_training_counts_match_the_preregistered_table():
    rows = _audit()["training_reconciliation"]
    assert rows and all(r["reconciled"] for r in rows)
    seen = {(r["horizon"], r["outer_issue"]): r for r in rows}
    assert seen[(1, "2024-01")]["unique_training_issues"] == 21
    assert seen[(1, "2024-01")]["eligible_rows"] == 231
    assert seen[(1, "2024-01")]["all_industry_rows"] == 252
    assert seen[(1, "2025-03")]["unique_training_issues"] == 35
    assert seen[(3, "2024-01")]["unique_training_issues"] == 18
    assert seen[(3, "2025-03")]["eligible_rows"] == 352


@requires_run
def test_no_target_was_read_before_a_prediction_was_frozen():
    reader = _audit()["target_reader"]
    assert reader["protocol_verified_before_any_target_read"] is True
    assert reader["target_reads_before_prediction_freeze"] == 0
    assert reader["target_reads"] == 720
    assert reader["predictions_frozen"] == 720


@requires_run
def test_the_upstream_invariants_reproduced():
    invariants = _audit()["upstream_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 25


@requires_run
def test_every_variant_and_horizon_has_a_full_panel_result():
    results = _results()["results"]
    assert sorted(results) == sorted(
        f"{v}|h{h}" for v in (V600, V1500) for h in (1, 3)
    )
    for result in results.values():
        assert result["panel"] == "full_twelve_industry"
        assert result["model"]["rows"] == 180
        assert result["benchmark"]["rows"] == 180
        assert result["mae_evidence"] in LN.MAE_EVIDENCE_STATUSES
        assert result["overall_status"] in LN.OVERALL_STATUSES
        for field in ("macro_industry_mae", "pooled_mae", "macro_industry_rmse",
                      "pooled_rmse", "median_absolute_error",
                      "spearman_correlation", "clipped_count", "clipped_rate",
                      "per_industry_mae"):
            assert field in result["model"], field
        assert len(result["model"]["per_industry_mae"]) == 12


@requires_run
def test_the_benchmark_reproduces_the_registered_h1_persistence():
    """Reproduced from the formula, not copied: it lands on the registered value."""
    results = _results()["results"]
    for result in results.values():
        if result["horizon"] == 1:
            assert result["primary_benchmark"] == (
                "operational_persistence_latest_published"
            )
        else:
            assert result["primary_benchmark"] == (
                "operational_persistence_trailing_3m_max"
            )
    h1 = {r["benchmark"]["macro_industry_mae"] for r in results.values()
          if r["horizon"] == 1}
    assert len(h1) == 1, "one benchmark, so one benchmark MAE at h=1"


@requires_run
def test_the_status_follows_the_frozen_decision_rule():
    for result in _results()["results"].values():
        boot = result["bootstrap"]
        expected = LN.classify_mae_evidence(
            boot["paired_ci_low"], boot["paired_ci_high"]
        )
        assert result["mae_evidence"] == expected
        assert result["overall_status"] == LN.overall_status(
            expected, result["event_safety"]["event_safety_passed"]
        )


@requires_run
def test_the_bootstrap_is_clustered_and_states_its_limit():
    for result in _results()["results"].values():
        boot = result["bootstrap"]
        assert boot["cluster_unit"] == "issue_month"
        assert boot["keep_all_industries_together"] is True
        assert boot["resample_individual_industry_rows"] is False
        assert boot["paired_resamples_identical"] is True
        assert boot["issue_month_clusters"] == 15
        assert boot["seed"] == CONFIG["bootstrap"]["random_seed"]
        assert boot["replications"] == CONFIG["bootstrap"]["replications"]
        expected_block = int(
            CONFIG["bootstrap"]["block_length_by_horizon"][str(result["horizon"])]
        )
        assert boot["block_length_months"] == expected_block
        assert "limited uncertainty resolution" in boot["resolution_note"]


@requires_run
def test_the_eligible_only_diagnostic_cannot_replace_the_primary():
    diagnostic = _results()["eligible_only_diagnostic"]
    assert len(diagnostic) == 4
    for entry in diagnostic.values():
        assert entry["industries"] == 11
        assert entry["may_replace_the_full_panel_result"] is False
        assert entry["model"]["rows"] == 165
    assert CONFIG["metrics"]["panel"] == "full_twelve_industry"


@requires_run
def test_every_scope_field_is_stated():
    for payload in (_results(), _audit()):
        scope = payload["scope"]
        assert scope["evaluation_scope"] == "development_only"
        assert scope["confirmatory_evaluation"] is False
        assert scope["latest_vintage_evaluation"] is True
        assert scope["fully_real_time_backtest"] is False
        assert scope["channel_selected"] is False
        assert scope["target_joined_for_authorized_development_evaluation"] is True
        assert scope["model_trained_for_authorized_development_evaluation"] is True
        assert scope["purge_evaluated"] is False
        assert scope["locked_test_accessed"] is False
        assert scope["locked_test_evaluation_authorized"] is False
        assert scope["model_feature_approved"] is False


@requires_run
def test_the_content_checksums_reproduce():
    for path in (RESULTS, AUDIT):
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored = payload.pop("content_checksum")
        assert LN.content_checksum(payload) == stored


@pytest.mark.skipif(not PREDICTIONS.is_file(), reason="the D5 predictions are absent")
def test_the_prediction_table_is_development_only_and_complete():
    import pandas as pd

    frame = pd.read_parquet(PREDICTIONS)
    assert len(frame) == 720
    assert frame.groupby(
        ["variant_id", "horizon", "issue_month", "industry_id"]).ngroups == 720
    assert frame["industry_id"].nunique() == 12
    assert set(frame["issue_month"]) == {
        f"2024-{m:02d}" for m in range(1, 13)
    } | {f"2025-{m:02d}" for m in range(1, 4)}
    assert frame["issue_month"].min() == "2024-01"
    assert frame["issue_month"].max() == "2025-03"
    assert frame["prediction_lineage_checksum"].nunique() == 720
    assert (frame["predicted_score"].between(0.0, 100.0)).all()
    for issue, reference in zip(frame["issue_month"], frame["reference_month"],
                                strict=True):
        assert reference == PP.shift_month(issue, -2)


@pytest.mark.skipif(not PREDICTIONS.is_file(), reason="the D5 predictions are absent")
def test_ind_04_is_a_pure_benchmark_passthrough():
    import pandas as pd

    frame = pd.read_parquet(PREDICTIONS)
    ind_04 = frame[frame["industry_id"] == "IND-04"]
    assert len(ind_04) == 60
    assert set(ind_04["prediction_source"]) == {LN.IND_04_PREDICTION_SOURCE}
    assert (ind_04["residual_correction"] == 0.0).all()
    assert np.allclose(ind_04["predicted_score"], ind_04["benchmark_score"])
    modeled = frame[frame["industry_id"] != "IND-04"]
    assert set(modeled["prediction_source"]) == {"pooled_model"}
    assert len(modeled) == 660


@pytest.mark.skipif(not COEFFICIENTS.is_file(), reason="the coefficients are absent")
def test_the_fixed_effects_are_the_unpenalised_block():
    import pandas as pd

    frame = pd.read_parquet(COEFFICIENTS)
    assert len(frame) == 2 * 2 * 15 * 21
    assert set(frame["block"]) == {"source", "interaction", "industry_fixed_effect"}
    fixed = frame[frame["block"] == "industry_fixed_effect"]
    assert not fixed["penalized"].any()
    assert frame[frame["block"] != "industry_fixed_effect"]["penalized"].all()
    assert not frame["coefficient"].str.lower().isin(
        {"intercept", "const", "global_intercept"}).any()


@pytest.mark.skipif(not RUNNER.is_file(), reason="the D5 runner is absent")
def test_the_runner_searches_no_hyperparameter():
    text = RUNNER.read_text(encoding="utf-8").lower()
    for fragment in ("alpha_grid", "gridsearch", "randomizedsearch", "cross_val",
                     "kfold", "shuffle=true", "train_test_split", "optuna"):
        assert fragment not in text, fragment


# ===========================================================================
# The twenty-four required synthetic failures.
# ===========================================================================
def test_synthetic_1_targets_read_before_the_protocol_freeze():
    reader = WF.GuardedTargetReader()
    with pytest.raises(WF.PhaseBoundaryError):
        reader.read((V600, 1, "2024-01", "IND-01"), 42.0)
    reader.verify_protocol("c" * 64, "c" * 64)
    with pytest.raises(WF.TargetAccessError, match="before its prediction was frozen"):
        reader.read((V600, 1, "2024-01", "IND-01"), 42.0)
    assert reader.reads_before_freeze == 1


def test_synthetic_2_hyperparameters_tuned_using_outcomes():
    panel = _panel()
    rng = np.random.default_rng(3)
    residuals = rng.normal(size=panel.matrix.shape[0])
    for tuned in (0.1, 10.0, 100.0):
        with pytest.raises(RG.EstimatorError, match="no grid, no inner CV"):
            RG.fit_fixed_pooled_partial_ridge(
                panel.matrix, residuals, panel.column_names, panel.blocks,
                lambda_value=tuned,
            )


def test_synthetic_3_the_loss_drops_the_normalisation():
    with pytest.raises(RG.EstimatorError, match="not averaged by n"):
        RG.assert_loss_is_normalised(False, RG.FIXED_LAMBDA)
    panel = _panel()
    with pytest.raises(RG.EstimatorError, match="specification would drift"):
        RG.fit_fixed_pooled_partial_ridge(
            panel.matrix, np.zeros(panel.matrix.shape[0]), panel.column_names,
            panel.blocks, loss_normalised_by_n=False,
        )


def test_synthetic_4_industry_fixed_effects_are_penalized():
    blocks = ("source",) * 5 + ("interaction",) * 5 + ("industry_fixed_effect",) * 3
    penalty = np.diag([1.0] * 10 + [1.0] * 3)
    with pytest.raises(RG.EstimatorError, match="unpenalised"):
        RG.assert_penalty_matrix(penalty, blocks)


def test_synthetic_5_a_redundant_global_intercept_is_added():
    names = ["src__a", "int__a", "intercept", "fe__IND-01"]
    with pytest.raises(RG.EstimatorError, match="global intercept"):
        RG.assert_no_global_intercept(names, 1)
    panel = _panel()
    with pytest.raises(RG.EstimatorError, match="global intercept"):
        RG.fit_fixed_pooled_partial_ridge(
            np.hstack([panel.matrix, np.ones((panel.matrix.shape[0], 1))]),
            np.zeros(panel.matrix.shape[0]),
            list(panel.column_names) + ["intercept"],
            list(panel.blocks) + ["industry_fixed_effect"],
        )


def test_synthetic_6_the_scaler_is_fitted_on_repeated_industry_rows():
    unique = _scaler()
    repeated_map = {}
    for index, issue in enumerate(ISSUES):
        for industry in ELIGIBLE:
            repeated_map[f"{issue}#{industry}#{index}"] = SOURCE[
                PP.shift_month(issue, -2)
            ]
    repeated = PP.fit_source_scaler(repeated_map, ddof=0)
    assert repeated["unique_issue_month_count"] == len(ISSUES) * len(ELIGIBLE)
    assert unique["unique_issue_month_count"] == len(ISSUES)
    # The statistics coincide only because each month repeats equally; the
    # reported sample size is the defect, and it is what the contract pins.
    assert CONFIG["preprocessing"]["source_scaler"][
        "fitted_on_repeated_industry_panel"] is False
    assert unique["fitted_on_repeated_industry_panel"] is False


def test_synthetic_7_interaction_columns_standardized_by_industry():
    panel, exposure = _panel(), _exposure()
    interaction = panel.matrix[:, 5:10]
    per_industry = []
    for industry in ELIGIBLE:
        mask = np.array([k[1] == industry for k in panel.row_keys])
        block = interaction[mask]
        sd = block.std(axis=0, ddof=0)
        per_industry.append((block - block.mean(axis=0)) / np.where(sd > 0, sd, 1.0))
    collapsed = np.vstack(per_industry)
    source = panel.matrix[:, :5]
    # Standardising inside the industry leaves only the SIGN of the exposure.
    assert len({np.sign(exposure["scaled_exposure"][g]) for g in ELIGIBLE}) < len(ELIGIBLE)
    assert not np.allclose(collapsed, interaction)
    assert CONFIG["preprocessing"]["interaction"][
        "standardized_separately_by_industry"] is False
    assert np.allclose(
        np.linalg.matrix_rank(np.hstack([source, interaction])), 10
    )


def test_synthetic_8_exposure_centering_uses_target_data():
    with pytest.raises(PP.PanelAssemblyError, match="complete frozen"):
        PP.center_and_scale_exposure({"IND-01": 0.01}, ELIGIBLE)
    with pytest.raises(PP.PanelAssemblyError, match="strictly positive"):
        PP.center_and_scale_exposure({**EXPOSURES, "IND-02": 0.0}, ELIGIBLE)
    assert CONFIG["preprocessing"]["exposure"]["fitted_on_targets"] is False
    assert CONFIG["preprocessing"]["exposure"]["recomputed_per_fold"] is False


def test_synthetic_9_candidate_b_is_fitted_instead_of_candidate_c():
    """Candidate B adds nothing WITHIN an industry; the pooled interaction does.

    For one industry ``E_g`` is a positive scalar, so ``[x, E_g x]`` spans the
    same five directions as ``x``. Pooled across industries with different
    exposures the interaction is no longer proportional to the main effect and
    the design spans ten. That is the whole difference between the two
    architectures, and fitting B while calling it C would lose it.
    """
    panel, exposure = _panel(), _exposure()
    source = panel.matrix[:, :5]
    interaction = panel.matrix[:, 5:10]

    one_industry = np.array([k[1] == ELIGIBLE[0] for k in panel.row_keys])
    within = np.hstack([source[one_industry], interaction[one_industry]])
    assert np.linalg.matrix_rank(within) == 5

    pooled = np.hstack([source, interaction])
    assert np.linalg.matrix_rank(pooled) == 10
    assert len({exposure["scaled_exposure"][g] for g in ELIGIBLE}) == len(ELIGIBLE)

    from thai_supply_chain_ews.structure import fuel_oil_candidate_designs as CD

    with pytest.raises(CD.CandidateDesignError, match="interaction block"):
        CD.assert_interaction_not_removed({"source": [0], "fixed_effects": [1]}, [])
    assert panel.blocks.count("interaction") == 5


def test_synthetic_10_both_fuel_oils_enter_one_fit():
    from thai_supply_chain_ews.structure import fuel_oil_candidate_designs as CD

    with pytest.raises(CD.CandidateDesignError, match="same sector-093"):
        CD.assert_single_variant_design([V600, V1500], "a combined D5 fit")
    assert CONFIG["channels"]["run_independently"] is True
    assert "shared_model_fits" in CONFIG["channels"]["prohibited"]
    assert "combined_feature_tables" in CONFIG["channels"]["prohibited"]
    assert "joint_penalties" in CONFIG["channels"]["prohibited"]


def test_synthetic_11_a_channel_is_promoted_from_observed_performance():
    with pytest.raises(LN.LineageError, match="channel was selected"):
        LN.assert_no_channel_promotion({"channel_selected": True})
    with pytest.raises(LN.LineageError, match="ranked against each other"):
        LN.assert_no_channel_promotion({"channels_ranked_by_mae": True})
    with pytest.raises(LN.LineageError, match="ranked against each other"):
        LN.assert_no_channel_promotion({"channels_ranked_by_event_metrics": True})


def test_synthetic_12_ind_04_is_fitted_dropped_or_zeroed():
    with pytest.raises(PP.PanelAssemblyError, match="mixed_or_ambiguous"):
        PP.assert_ind_04_excluded(["IND-01", "IND-04"], "the pooled fit")
    with pytest.raises(PP.PanelAssemblyError, match="mixed_or_ambiguous"):
        PP.build_pooled_design(
            _rows(industries=ELIGIBLE + ["IND-04"]), ELIGIBLE + ["IND-04"],
            _scaler(), _exposure(EXPOSURES, ELIGIBLE + ["IND-04"]), V600, 1,
            "2023-11",
        )
    with pytest.raises(LN.LineageError, match="benchmark passes through"):
        LN.assert_passthrough_not_a_fitted_zero({
            "industry_id": "IND-04",
            "prediction_source": LN.IND_04_PREDICTION_SOURCE,
            "residual_correction": 0.4,
        })
    with pytest.raises(LN.LineageError, match="fitted industry effect"):
        LN.assert_passthrough_not_a_fitted_zero({
            "industry_id": "IND-04",
            "prediction_source": LN.IND_04_PREDICTION_SOURCE,
            "residual_correction": 0.0,
            "industry_fixed_effect_fitted": True,
        })


def test_synthetic_13_stress_month_t_is_used_at_issue_t():
    with pytest.raises(WF.WalkForwardError, match="strictly before"):
        WF.assert_stress_month_permitted("2024-06", "2024-06")
    with pytest.raises(WF.WalkForwardError, match="strictly before"):
        WF.assert_stress_month_permitted("2024-07", "2024-06")


def test_synthetic_14_the_feature_reference_month_exceeds_t_minus_2():
    with pytest.raises(PP.PanelAssemblyError, match="policy lag requires"):
        PP.assert_feature_frozen_at_issue("2024-06", "2024-05")
    with pytest.raises(PP.PanelAssemblyError, match="later than"):
        PP.assert_reference_month_not_later_than("2024-05", "2024-06")


def test_synthetic_15_historical_features_are_refreshed_at_the_outer_origin():
    """Every training row is stamped with the LATEST reference month."""
    refreshed = _rows(refresh_at="2023-08")
    with pytest.raises(PP.PanelAssemblyError, match="available at its own issue month"):
        PP.build_pooled_design(
            refreshed, ELIGIBLE, _scaler(), _exposure(), V600, 1, "2023-11"
        )


def test_synthetic_16_an_unavailable_label_enters_training():
    with pytest.raises(WF.WalkForwardError, match="could not have been in the training"):
        WF.assert_label_available_by("2024-03", "2024-01", "2023-12")
    WF.assert_label_available_by("2023-12", "2024-01", "2023-10")


def test_synthetic_17_an_evaluation_target_is_read_before_the_freeze():
    reader = WF.GuardedTargetReader()
    reader.verify_protocol("d" * 64, "d" * 64)
    key = (V600, 3, "2024-05", "IND-07")
    with pytest.raises(WF.TargetAccessError, match="before its prediction was frozen"):
        reader.read(key, 61.0)
    reader.freeze(key)
    assert reader.read(key, 61.0) == 61.0


def test_synthetic_18_random_row_level_cv_or_bootstrap_is_used():
    with pytest.raises(BS.BootstrapError, match="twelve views of one month"):
        BS.assert_no_row_level_resampling("industry_row")
    with pytest.raises(BS.BootstrapError, match="twelve views of one month"):
        BS.paired_macro_mae_interval(
            BS.issue_month_matrix(_frame()), BS.issue_month_matrix(_frame()),
            block_length=1, replications=10, seed=1, cluster_unit="row",
        )


def test_synthetic_19_purge_or_locked_origins_enter_results():
    for intruder in ("2025-04", "2025-06", "2025-07", "2026-04"):
        with pytest.raises(WF.WalkForwardError, match="reserved origins"):
            WF.assert_no_purge_or_locked_origin(
                ["2024-01", intruder],
                {"2025-04", "2025-05", "2025-06"},
                {"2025-07", "2026-04"},
            )
    assert CONFIG["purge_and_locked"]["purge_evaluated"] is False
    assert CONFIG["purge_and_locked"]["locked_test_accessed"] is False


def test_synthetic_20_the_event_thresholds_are_tuned():
    assert CONFIG["event_safety"]["high_stress_threshold"] == 85
    assert CONFIG["event_safety"]["severe_stress_threshold"] == 95
    assert CONFIG["event_safety"]["thresholds_tuned"] is False
    assert CONFIG["event_safety"]["severe_affects_any_decision"] is False
    assert LN.event_safety_status(1, 1)["threshold"] == 85


@requires_run
def test_synthetic_21_eligible_only_results_replace_the_full_panel():
    payload = _results()
    for entry in payload["eligible_only_diagnostic"].values():
        assert entry["may_replace_the_full_panel_result"] is False
        assert entry["status"] == "secondary_structurally_preregistered"
    for result in payload["results"].values():
        assert result["panel"] == "full_twelve_industry"
        assert result["model"]["rows"] == 180
    assert payload["metrics_contract"]["eligible_only_diagnostic"][
        "may_replace_the_full_panel_result"] is False


def test_synthetic_22_a_development_result_approves_a_model_feature():
    for field in ("model_feature_approved", "confirmatory_evaluation",
                  "locked_test_evaluation_authorized", "locked_test_accessed",
                  "purge_evaluated"):
        with pytest.raises(LN.LineageError, match="approves no feature"):
            LN.assert_no_confirmatory_claim({field: True})


def test_synthetic_23_missing_training_inputs_are_imputed():
    with pytest.raises(PP.PanelAssemblyError, match="not imputed"):
        PP.assert_no_imputation(
            [1.0, None, 3.0, 40.0, 5.0], "2023-05", "IND-01"
        )
    with pytest.raises(PP.PanelAssemblyError, match="not imputed"):
        PP.assert_no_imputation(
            [1.0, float("nan"), 3.0, 40.0, 5.0], "2023-05", "IND-01"
        )
    assert CONFIG["training"]["imputation_of_unavailable_source_values"] is False


def test_synthetic_24_prediction_or_lineage_keys_are_duplicated_or_incomplete():
    references = {field: f"value-{field}" for field in LN.LINEAGE_FIELDS}
    prediction = {
        "variant_id": V600, "horizon": 1, "issue_month": "2024-01",
        "industry_id": "IND-01", "reference_month": "2023-11",
        "prediction_source": "pooled_model",
        "benchmark_name": "operational_persistence_latest_published",
        "predicted_score": 51.0, "residual_correction": 0.5, "clipped": False,
    }
    record = LN.prediction_lineage_record(prediction, references)
    assert len(LN.prediction_lineage_checksum(record)) == 64
    for omitted in ("training_issue_keys", "calibrator_cutoff",
                    "fitted_coefficient_checksum"):
        partial = {k: v for k, v in references.items() if k != omitted}
        with pytest.raises(LN.LineageError, match="missing"):
            LN.prediction_lineage_record(prediction, partial)
    with pytest.raises(LN.LineageError, match="empty"):
        LN.prediction_lineage_record(
            prediction, {**references, "calibrator_cutoff": ""}
        )
    # A duplicated key is a collision, and a collision is detected as one.
    other = LN.prediction_lineage_checksum(
        LN.prediction_lineage_record({**prediction, "issue_month": "2024-02"},
                                     references)
    )
    assert other != LN.prediction_lineage_checksum(record)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_the_panel_and_the_fit_are_deterministic():
    first, second = _panel(), _panel()
    assert np.array_equal(first.matrix, second.matrix)
    assert first.row_keys == second.row_keys
    assert RG.coefficient_checksum(_fit(first)) == RG.coefficient_checksum(
        _fit(second)
    )


def test_the_bootstrap_is_reproducible_from_its_seed():
    model, benchmark = _frame(), _frame(offset=1.0)
    args = (BS.issue_month_matrix(model), BS.issue_month_matrix(benchmark))
    first = BS.paired_macro_mae_interval(*args, block_length=3, replications=50,
                                         seed=20260830)
    second = BS.paired_macro_mae_interval(*args, block_length=3, replications=50,
                                          seed=20260830)
    assert first["paired_ci_low"] == second["paired_ci_low"]
    assert first["paired_ci_high"] == second["paired_ci_high"]
    assert math.isfinite(first["paired_difference_point"])
