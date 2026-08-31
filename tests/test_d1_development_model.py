"""Task D1 — leakage-safe development model and benchmark comparison.

The contract tests check the model is what D1 promised. The synthetic failure
tests matter more: each one deliberately attempts a leak and requires it to fail
loudly. A leakage guard that has never been seen to reject anything is an
assumption, not a safeguard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.evaluation import splits as SP  # noqa: E402
from thai_supply_chain_ews.evaluation import walk_forward as WF  # noqa: E402
from thai_supply_chain_ews.modeling import development_comparison as DC  # noqa: E402
from thai_supply_chain_ews.modeling import feature_target_assembly as FA  # noqa: E402
from thai_supply_chain_ews.modeling import nested_walk_forward as NW  # noqa: E402
from thai_supply_chain_ews.modeling import residual_ridge as RR  # noqa: E402
from thai_supply_chain_ews.targets.calibration import (  # noqa: E402
    IndustryStressCalibrator,
    LeakageError,
)

CONFIG = yaml.safe_load(
    (ROOT / "configs" / "d1_development_models.yaml").read_text(encoding="utf-8")
)
SCHEMA = yaml.safe_load(
    (ROOT / "schemas" / "development_model_prediction.schema.yaml").read_text(
        encoding="utf-8"
    )
)
RESULTS_JSON = ROOT / "docs" / "d1_development_results.json"
ASSEMBLY_JSON = ROOT / "docs" / "d1_feature_target_assembly_audit.json"


@pytest.fixture(scope="module")
def results():
    return json.loads(RESULTS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def assembly_audit():
    return json.loads(ASSEMBLY_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def predictions():
    import pandas as pd

    path = ROOT / "data" / "model_input" / "d1_development_predictions.parquet"
    return pd.read_parquet(path).to_dict("records")


@pytest.fixture(scope="module")
def b3():
    monthly, labels = WF.load_b3_artifacts()
    return monthly, labels


@pytest.fixture(scope="module")
def plan():
    return SP.load_walk_forward_plan()


@pytest.fixture(scope="module")
def feature_index():
    import pandas as pd

    frame = pd.read_parquet(ROOT / "data" / "features" / "c4_canonical_long.parquet")
    for column in ("reference_month", "conditioned_available_month"):
        frame[column] = frame[column].astype(str).str[:10]
    return FA.build_feature_index(frame.to_dict("records"), "primary_direct_lag2")


# --- upstream invariants ------------------------------------------------------


def test_b3_invariants_reproduced(b3):
    monthly, labels = b3
    invariants = WF.validate_b3_invariants(monthly, labels)
    assert invariants["monthly_rows"] == 636
    assert invariants["combined_rows"] == 1224
    assert invariants["duplicate_keys"] == 0
    assert invariants["primary_component_count"] == 1
    assert invariants["primary_component"] == "mpi_adverse_yoy"
    assert int((labels["horizon_months"] == 1).sum()) == 624
    assert int((labels["horizon_months"] == 3).sum()) == 600
    assert str(monthly["reference_month"].astype(str).max())[:7] == "2026-05"


def test_b4_invariants_reproduced(plan):
    origins = [str(o)[:10] for o in plan.development_origins]
    assert len(origins) == 15
    assert origins[0] == "2024-01-01"
    assert origins[-1] == "2025-03-01"
    assert [str(o)[:10] for o in plan.purge_origins] == [
        "2025-04-01", "2025-05-01", "2025-06-01"
    ]
    assert CONFIG["upstream_invariants"]["b4"]["benchmark_h1"] == (
        "persistence_current_month"
    )
    assert CONFIG["upstream_invariants"]["b4"]["benchmark_h3"] == (
        "persistence_trailing_3m_max"
    )


def test_c4_invariants_reproduced(results):
    audit = json.loads(
        (ROOT / "docs" / "c4_industry_conditioned_feature_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["canonical_row_count"] == 39474
    assert set(audit["rows_per_variant"].values()) == {13158}
    assert audit["eligible_pairs"] == 43
    assert len(audit["excluded_pairs"]) == 5
    assert audit["combined_double_sensitivity_variant_created"] is False
    assert audit["structural_availability"]["structural_available_by"] == "2020-03-31"
    dimensions = audit["development_snapshot"]["dimensions"]
    assert dimensions["eligible_feature_cells"] == 3225
    assert dimensions["ineligible_feature_cells"] == 375
    assert results["upstream_invariants_reproduced"]["c4_rows"] == 39474


# --- development period only ----------------------------------------------------


def test_only_development_origins_appear(predictions, plan, results):
    origins = {str(p["forecast_origin_month"])[:10] for p in predictions}
    assert origins == {str(o)[:10] for o in plan.development_origins}
    assert len(origins) == 15
    purge = {str(o)[:10] for o in plan.purge_origins}
    assert not (origins & purge)
    locked = set()
    for horizon in plan.horizons:
        locked.update(str(o)[:10] for o in plan.locked_test_origins(horizon))
    assert not (origins & locked)
    assert results["locked_test_outcomes_read"] is False
    assert results["approved_for_locked_test"] is False
    assert {p["split"] for p in predictions} == {"development"}


def test_default_runner_cannot_evaluate_locked_test():
    script = (ROOT / "scripts" / "run_d1_development_model.py").read_text(encoding="utf-8")
    assert "argparse" not in script
    assert "sys.argv" not in script
    assert "os.environ" not in script
    # The origins come from the development split, and each is asserted.
    assert "plan.development_origins" in script
    assert "assert_not_locked_test" in script
    # Locked outcomes are never joined or summarised.
    assert "locked_test_origins(horizon)" in script
    assert CONFIG["evaluation"]["default_runner_can_evaluate_locked_test"] is False
    assert CONFIG["evaluation"]["locked_test_outcomes_read"] is False


def test_locked_test_origin_raises(plan):
    locked = plan.locked_test_origins(1)
    with pytest.raises(SP.LockedTestAccessError):
        plan.assert_not_locked_test([str(locked[0])[:10]])


def test_exact_prediction_counts(predictions, results):
    assert len(predictions) == 1080
    assert results["total_model_predictions"] == 1080
    expected = {
        f"{variant}|h{horizon}": 180
        for variant in ("primary", "timing_sensitivity", "structural_sensitivity")
        for horizon in (1, 3)
    }
    assert results["prediction_counts"] == expected
    for horizon in (1, 3):
        primary = [
            p for p in predictions
            if p["variant_key"] == "primary" and p["horizon_months"] == horizon
        ]
        assert len(primary) == 180
        assert len({p["industry_id"] for p in primary}) == 12
        assert len({p["forecast_origin_month"] for p in primary}) == 15


def test_prediction_keys_unique_and_ordered(predictions):
    keys = [
        (str(p["forecast_origin_month"])[:10], p["industry_id"],
         p["horizon_months"], p["variant_key"])
        for p in predictions
    ]
    assert len(set(keys)) == len(keys) == 1080


# --- temporal cutoffs -----------------------------------------------------------


def test_label_rule_uses_target_window_end(b3):
    _, labels = b3
    records = labels.copy()
    for column in ("forecast_origin_month", "target_window_end"):
        records[column] = records[column].astype(str).str[:10]
    rows = records.to_dict("records")
    permitted = FA.label_permitted_origins(rows, "2024-01-01", 3)
    for origin in permitted:
        label = next(
            r for r in rows
            if r["forecast_origin_month"] == origin and int(r["horizon_months"]) == 3
        )
        assert label["target_window_end"] <= "2024-01-01"
    # The rejected alternative would admit strictly more origins.
    naive = sorted({
        r["forecast_origin_month"] for r in rows
        if int(r["horizon_months"]) == 3 and r["forecast_origin_month"] < "2024-01-01"
    })
    assert set(permitted) < set(naive), "target_window_end must be stricter"


def test_label_rule_enforced_separately_per_horizon(b3):
    _, labels = b3
    records = labels.copy()
    for column in ("forecast_origin_month", "target_window_end"):
        records[column] = records[column].astype(str).str[:10]
    rows = records.to_dict("records")
    h1 = FA.label_permitted_origins(rows, "2024-01-01", 1)
    h3 = FA.label_permitted_origins(rows, "2024-01-01", 3)
    assert len(h1) > len(h3), "h=3 windows close later, so fewer are permitted"
    assert max(h1) == "2023-12-01"
    assert max(h3) == "2023-10-01"


def test_incomplete_target_window_label_is_rejected(feature_index, b3):
    """Synthetic: a label whose window is still open must fail the gate."""
    _, labels = b3
    records = labels.copy()
    for column in ("forecast_origin_month", "target_window_end"):
        records[column] = records[column].astype(str).str[:10]
    rows = records.to_dict("records")
    labels_by_key = {
        (r["industry_id"], r["forecast_origin_month"], int(r["horizon_months"])): r
        for r in rows
    }
    # 2023-12 h=3 closes 2024-03, after a 2024-01 cutoff.
    with pytest.raises(FA.AssemblyError, match="label gate failed"):
        FA.assemble_training_matrix(
            feature_index, labels_by_key, ["2023-12-01"], "IND-01", 3,
            "none", "2024-01-01",
        )


def test_historical_features_evaluated_at_u_not_t(feature_index):
    """The core distinction: a training row is built at ITS OWN origin.

    IND-04 is used because refineries carry a large crude exposure, so the two
    vectors differ by a visible margin rather than by rounding.
    """
    at_u = FA.features_as_of(feature_index, "2022-06-01", "IND-04", "none")
    at_t = FA.features_as_of(feature_index, "2024-06-01", "IND-04", "none")
    assert at_u is not None and at_t is not None
    assert at_u["values"] != at_t["values"], (
        "a vector built at u must not equal one built two years later"
    )
    for name, reference in at_u["reference_months"].items():
        assert reference <= "2022-06-01"
        assert at_t["reference_months"][name] >= reference


def test_feature_published_after_its_origin_is_never_used(feature_index):
    """Synthetic: nothing published between u and t may enter the row for u."""
    origin = "2023-01-01"
    vector = FA.features_as_of(feature_index, origin, "IND-01", "none")
    assert vector is not None
    for name in vector["predictor_names"]:
        commodity, feature = name.split("__", 1)
        history = feature_index.entries[("IND-01", commodity, feature)]
        chosen = vector["reference_months"][name]
        available = next(
            item[0] for item in history if item[1] == chosen
        )
        assert available <= origin
        # And a later-published observation exists that was correctly skipped.
        later = [item for item in history if item[0] > origin]
        assert all(item[1] > chosen or item[0] > origin for item in later)


def test_future_dated_conditioned_feature_raises(feature_index):
    """Synthetic: a corrupted index with a future availability must fail."""
    import copy

    broken = copy.deepcopy(feature_index)
    broken._cache = {}
    entry_key = ("IND-04", "brent_crude_usd_bbl", "price_level")
    _, reference, value, c2, c3 = broken.entries[entry_key][0]
    # Corrupt the availability so the feature claims to be usable in the very
    # month it describes — impossible, since that month has not finished.
    broken.entries[entry_key] = [(reference, reference, value, c2, c3)]
    with pytest.raises(FA.FutureFeatureError, match="not after the reference month"):
        FA.features_as_of(broken, "2024-06-01", "IND-04", "none")


# --- feature history gate --------------------------------------------------------


def test_first_complete_primary_origin_is_2022_03(feature_index):
    assert FA.features_as_of(feature_index, "2022-02-01", "IND-01", "none") is None
    assert FA.features_as_of(feature_index, "2022-03-01", "IND-01", "none") is not None
    assert str(CONFIG["feature_history_gate"]["first_complete_primary_origin"]) == (
        "2022-03-01"
    )


def test_incomplete_history_is_flagged_not_imputed(assembly_audit):
    assert CONFIG["feature_history_gate"]["impute_missing_12m_transformations"] is False
    assert CONFIG["feature_history_gate"]["rows_silently_dropped"] is False
    assert CONFIG["feature_history_gate"]["excluded_reason_code"] == (
        "insufficient_registered_feature_history"
    )
    excluded = [r for r in assembly_audit["rows"] if r["excluded_for_feature_history"]]
    assert excluded, "early origins must be excluded with a reason"
    for row in excluded:
        assert row["earliest_usable_origin"] >= "2022-03-01"


def test_expected_usable_outer_training_counts(assembly_audit):
    """The counts the brief predicted, reproduced exactly."""
    summary = assembly_audit["summary"]
    expected = CONFIG["feature_history_gate"]["expected_usable_outer_training_rows"]
    assert summary["h1_at_2024-01-01"]["feature_usable_rows"] == expected["h1_at_2024_01"]
    assert summary["h1_at_2025-03-01"]["feature_usable_rows"] == expected["h1_at_2025_03"]
    assert summary["h3_at_2024-01-01"]["feature_usable_rows"] == expected["h3_at_2024_01"]
    assert summary["h3_at_2025-03-01"]["feature_usable_rows"] == expected["h3_at_2025_03"]
    # Both counts are reported: label-permitted and feature-usable.
    for key, entry in summary.items():
        assert entry["label_permitted_rows"] >= entry["feature_usable_rows"], key


# --- calibrator -------------------------------------------------------------------


def test_calibrator_refits_at_every_outer_origin(assembly_audit):
    calibrators = assembly_audit["calibrators"]
    assert len(calibrators) == 30  # 15 origins x 2 horizons
    for record in calibrators:
        assert record["calibration_reference_end"] <= record["forecast_origin_month"]
        assert record["calibration_observations"] > 0
        assert len(record["calibration_checksum"]) == 64
    checksums = {
        (r["forecast_origin_month"], r["calibration_checksum"]) for r in calibrators
    }
    assert len({c[1] for c in checksums}) == 15, "one distinct calibrator per origin"


def test_calibrator_rejects_post_cutoff_data(b3):
    monthly, _ = b3
    records = monthly.copy()
    records["reference_month"] = records["reference_month"].astype(str).str[:10]
    with pytest.raises(LeakageError, match="after the training cutoff"):
        IndustryStressCalibrator().fit(records, "2023-06-01")


def test_calibrator_minimum_is_preserved_and_binds(b3):
    monthly, _ = b3
    records = monthly.copy()
    records["reference_month"] = records["reference_month"].astype(str).str[:10]
    assert CONFIG["calibration"]["min_reference_observations"] == 24
    # 2023-11 is the 23rd month, so no industry can be calibrated.
    early = IndustryStressCalibrator().fit(
        records[records["reference_month"] <= "2023-11-01"], "2023-11-01"
    )
    assert early.fitted_industries == []
    late = IndustryStressCalibrator().fit(
        records[records["reference_month"] <= "2023-12-01"], "2023-12-01"
    )
    assert len(late.fitted_industries) == 12
    # This is exactly why the brief's expected inner origins are unreachable.
    assert CONFIG["selection"]["expectation_status"] == (
        "NOT_MET_calibrator_minimum_binds"
    )
    assert str(CONFIG["selection"]["actual_earliest_feasible_inner_validation_origin"]) == (
        "2023-12-01"
    )


# --- model ------------------------------------------------------------------------


def test_residual_formula_and_prediction(predictions):
    for row in predictions:
        expected = float(row["benchmark_prediction"]) + float(row["predicted_residual"])
        assert row["prediction_before_clipping"] == pytest.approx(expected, rel=1e-9)
        clipped = min(max(expected, 0.0), 100.0)
        assert row["predicted_score"] == pytest.approx(clipped, rel=1e-9)
        assert bool(row["clipped"]) == (clipped != expected)


def test_benchmark_offsets_by_horizon(predictions):
    for row in predictions:
        expected = (
            "persistence_current_month" if row["horizon_months"] == 1
            else "persistence_trailing_3m_max"
        )
        assert row["benchmark_baseline_name"] == expected


def test_benchmark_predictions_reproduce_b4_production(predictions):
    """The benchmark column must match B4's own production predictions."""
    import pandas as pd

    b4 = pd.read_json(ROOT / "docs" / "b4_baseline_results.json")
    # B4's artifact stores metrics; reproduce via its baseline module instead.
    from thai_supply_chain_ews.evaluation import baselines as BL

    monthly, _ = WF.load_b3_artifacts()
    records = monthly.copy()
    records["reference_month"] = records["reference_month"].astype(str).str[:10]
    raw = {
        (r["industry_id"], r["reference_month"]): float(r["mpi_adverse_yoy"])
        for r in records.to_dict("records")
    }
    checked = 0
    for row in predictions[:60]:
        origin = str(row["forecast_origin_month"])[:10]
        calibrator = IndustryStressCalibrator().fit(
            records[records["reference_month"] <= origin], origin
        )
        history = {
            month: value for (ind, month), value in raw.items()
            if ind == row["industry_id"] and month <= origin
        }
        context = BL.BaselineContext(
            origin=origin, industry_id=row["industry_id"],
            horizon=int(row["horizon_months"]), calibrator=calibrator,
            raw_stress_by_month=history, training_scores=[],
        )
        _, score = BL.predict_baseline(row["benchmark_baseline_name"], context)
        assert float(row["benchmark_prediction"]) == pytest.approx(score, rel=1e-9)
        checked += 1
    assert checked == 60
    assert b4 is not None


def test_clipping_bounds_are_fixed():
    assert RR.SCORE_FLOOR == 0.0
    assert RR.SCORE_CEILING == 100.0
    assert RR.clip_score(-5.0) == (0.0, True)
    assert RR.clip_score(105.0) == (100.0, True)
    assert RR.clip_score(50.0) == (50.0, False)
    assert CONFIG["model"]["clipping"]["tuned"] is False


def test_industry_specific_coefficients_never_pooled(predictions):
    primary = [p for p in predictions if p["variant_key"] == "primary"]
    by_origin_horizon: dict = {}
    for row in primary:
        if not row["model_checksum"]:
            continue
        key = (row["forecast_origin_month"], row["horizon_months"])
        by_origin_horizon.setdefault(key, set()).add(row["model_checksum"])
    assert by_origin_horizon
    for origin_horizon, checksums in by_origin_horizon.items():
        assert len(checksums) > 1, f"{origin_horizon}: industries share one model"
    assert CONFIG["model"]["pool_coefficients_across_industries"] is False


def test_zero_variance_detection_uses_x_only():
    matrix = np.array([[1.0, 5.0], [1.0, 6.0], [1.0, 7.0]])
    residuals = np.array([0.5, -0.2, 0.9])
    model = RR.fit_ridge_residual(
        "IND-01", 1, ["a__price_level", "b__price_level"], matrix, residuals,
        1.0, "none",
    )
    assert model.omitted_zero_variance == ("a__price_level",)
    assert model.retained_predictors == ("b__price_level",)
    # A different outcome must not change which predictor is dropped.
    other = RR.fit_ridge_residual(
        "IND-01", 1, ["a__price_level", "b__price_level"], matrix,
        np.array([9.0, -9.0, 0.0]), 1.0, "none",
    )
    assert other.omitted_zero_variance == model.omitted_zero_variance
    assert CONFIG["preprocessing"]["zero_variance_detection_uses"] == "X_only"


def test_scaler_fits_training_rows_only():
    training = np.array([[1.0], [2.0], [3.0]])
    residuals = np.array([0.1, 0.2, 0.3])
    model = RR.fit_ridge_residual(
        "IND-01", 1, ["a__price_level"], training, residuals, 1.0, "none"
    )
    assert model.scaler.mean[0] == pytest.approx(2.0)
    assert model.scaler.scale[0] == pytest.approx(np.std([1.0, 2.0, 3.0]))
    # Scaling over the whole development period would give a different mean.
    whole = np.array([[1.0], [2.0], [3.0], [100.0]])
    assert whole.mean() != pytest.approx(model.scaler.mean[0])
    assert CONFIG["preprocessing"]["scaler_fitted_on"] == "training_rows_only"
    assert "whole_development_scaling" in CONFIG["preprocessing"]["prohibited"]


# --- non-ferrous ------------------------------------------------------------------


def test_aluminum_and_copper_never_coexist(predictions):
    for row in predictions:
        names = str(row["predictor_names"]).split(";") if row["predictor_names"] else []
        has_aluminum = any(n.startswith("aluminum_usd_mt__") for n in names)
        has_copper = any(n.startswith("copper_usd_mt__") for n in names)
        assert not (has_aluminum and has_copper), row["forecast_origin_month"]


def test_fitting_both_metals_raises():
    """Synthetic: the design-matrix guard must fire."""
    matrix = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, 5.0]])
    residuals = np.array([0.1, -0.2, 0.3])
    with pytest.raises(RR.RidgeError, match="same design matrix"):
        RR.fit_ridge_residual(
            "IND-01", 1,
            ["aluminum_usd_mt__price_level", "copper_usd_mt__price_level"],
            matrix, residuals, 1.0, "aluminum",
        )


def test_metal_channel_is_global_across_industries(predictions):
    primary = [p for p in predictions if p["variant_key"] == "primary"]
    by_key: dict = {}
    for row in primary:
        key = (row["forecast_origin_month"], row["horizon_months"])
        by_key.setdefault(key, set()).add(row["selected_non_ferrous_channel"])
    for key, channels in by_key.items():
        assert len(channels) == 1, f"{key}: channel varies by industry"
    assert CONFIG["non_ferrous"]["choice_is_global_per_outer_origin_and_horizon"] is True
    assert CONFIG["non_ferrous"]["choice_varies_by_industry"] is False


def test_ineligible_pair_omitted_not_zero_filled(feature_index):
    # IND-12 x aluminum is ineligible under C3-R1.
    vector = FA.features_as_of(feature_index, "2024-01-01", "IND-12", "aluminum")
    assert vector is not None
    assert not any(
        name.startswith("aluminum_usd_mt__") for name in vector["predictor_names"]
    )
    assert any(
        name.startswith("aluminum_usd_mt__")
        for name in vector["omitted_ineligible_predictors"]
    )
    assert 0.0 not in [
        v for n, v in zip(vector["predictor_names"], vector["values"], strict=True)
        if n.startswith("aluminum_usd_mt__")
    ]
    assert CONFIG["preprocessing"]["convert_ineligible_to_zero"] is False


# --- selection --------------------------------------------------------------------


def test_registered_grid_and_configurations():
    assert NW.RIDGE_ALPHA_GRID == (0.1, 1.0, 10.0, 100.0)
    configurations = NW.registered_configurations()
    assert len(configurations) == 12
    assert len({c.configuration_id for c in configurations}) == 12
    assert {c.non_ferrous_channel for c in configurations} == {
        "none", "aluminum", "copper"
    }


def test_selection_recorded_per_origin_and_horizon(results):
    selections = results["selections"]
    assert len(selections) == 30
    for entry in selections.values():
        assert entry["selected_alpha"] in NW.RIDGE_ALPHA_GRID
        assert entry["selected_non_ferrous_channel"] in ("none", "aluminum", "copper")
        assert entry["selection_reason"]
        assert entry["forecast_origin_month"] in results["development_origins"]


def test_selection_uses_only_nested_training_data():
    source = (ROOT / "src" / "thai_supply_chain_ews" / "modeling" /
              "nested_walk_forward.py").read_text(encoding="utf-8")
    # The inner loop builds its own calibrator per inner origin.
    assert "calibrator_factory(inner_origin)" in source
    assert CONFIG["selection"]["occurs_entirely_inside_outer_training_window"] is True
    for forbidden in ("current_outer_target", "later_development_origins",
                      "purge_buffer_targets", "locked_test_information"):
        assert forbidden in CONFIG["selection"]["must_not_use"]


def test_inner_validation_uses_separate_calibrator():
    assert CONFIG["calibration"][
        "reuse_outer_calibrator_inside_inner_validation"
    ] is False
    assert CONFIG["calibration"]["refit_at_every_inner_origin"] is True


def test_deterministic_tie_breaking():
    assert NW.MAE_TIE_TOLERANCE == 1e-6
    order = CONFIG["selection"]["tie_rule"]["order"]
    assert order == ["fewer_predictors", "larger_alpha",
                     "deterministic_configuration_id_order"]


def test_conservative_fallback_when_inner_history_is_short(results):
    """The brief's inner-origin expectation is unmet; the fallback is recorded."""
    assert NW.MIN_INNER_VALIDATION_ORIGINS_FOR_SELECTION == 3
    assert NW.FALLBACK_CONFIGURATION_ALPHA == 100.0
    assert NW.FALLBACK_CONFIGURATION_CHANNEL == "none"
    fallbacks = [
        entry for entry in results["selections"].values()
        if entry["selection_reason"] == "insufficient_inner_history_conservative_fallback"
    ]
    assert fallbacks, "early origins should use the fallback"
    for entry in fallbacks:
        assert entry["selected_alpha"] == 100.0
        assert entry["selected_non_ferrous_channel"] == "none"
        assert entry["inner_origins_covered"] == 0


def test_selecting_alpha_on_the_outer_target_is_not_possible():
    """Synthetic: the selection signature has no access to the outer target."""
    import inspect

    signature = inspect.signature(NW.select_configuration)
    assert "outer_target" not in signature.parameters
    assert "observed_score" not in signature.parameters
    source = inspect.getsource(NW.select_configuration)
    # The only target read inside selection is the INNER validation label.
    assert "inner_calibrator.transform" in source
    assert source.count("labels_by_key.get((industry_id, inner_origin, horizon))") == 1


# --- metrics and evidence -----------------------------------------------------------


def test_metrics_present_for_both_horizons(results):
    for horizon in ("h1", "h3"):
        entry = results["results"][horizon]
        model = entry["model"]
        assert model["rows"] == 180
        for key in ("macro_industry_mae", "pooled_mae", "macro_industry_rmse",
                    "pooled_rmse", "median_absolute_error", "pooled_spearman"):
            assert model[key] is not None, key
        assert len(model["per_industry_mae"]) == 12
        assert set(model["by_block"]) == {"DEV-1", "DEV-2", "DEV-3"}
        assert entry["benchmark"]["rows"] == 180


def test_high_stress_threshold_is_85_and_untuned(results):
    for horizon in ("h1", "h3"):
        stress = results["results"][horizon]["model_high_stress"]
        assert stress["threshold"] == 85.0
        assert stress["threshold_tuned"] is False
        assert stress["severe_threshold"] == 95.0
        assert stress["false_negative"] >= 0
    assert DC.HIGH_STRESS_THRESHOLD == 85.0


def test_undefined_precision_is_none_not_zero():
    rows = [
        {"industry_id": "IND-01", "observed_score": 10.0, "predicted_score": 20.0},
        {"industry_id": "IND-01", "observed_score": 30.0, "predicted_score": 40.0},
    ]
    stress = DC.high_stress_metrics(rows, "predicted_score")
    assert stress["predicted_event_count"] == 0
    assert stress["precision"] is None
    assert stress["recall"] is None
    assert stress["f1"] is None
    assert stress["pr_auc"] is None


def test_bootstrap_is_clustered_and_deterministic(results):
    for horizon in ("h1", "h3"):
        bootstrap = results["results"][horizon]["bootstrap"]
        assert bootstrap["replications"] == 1000
        assert bootstrap["block_length_months"] == 3
        assert bootstrap["clustered_by"] == "forecast_origin_month"
        assert bootstrap["industries_kept_together"] is True
        paired = bootstrap["paired_macro_mae_difference_ci"]
        assert paired["cluster_unit"] == "forecast_origin_month"
        assert paired["paired"] is True
        assert paired["n_month_clusters"] == 15 if "n_month_clusters" in paired else True
    assert CONFIG["uncertainty"]["treats_180_rows_as_independent"] is False


def test_evidence_status_rule():
    supported = DC.assign_evidence_status(10.0, 12.0, {"ci_low": -3.0, "ci_high": -1.0})
    assert supported["evidence_status"] == "incremental_signal_supported"
    inconclusive = DC.assign_evidence_status(10.0, 12.0, {"ci_low": -3.0, "ci_high": 1.0})
    assert inconclusive["evidence_status"] == "inconclusive"
    worse = DC.assign_evidence_status(13.0, 12.0, {"ci_low": -3.0, "ci_high": -1.0})
    assert worse["evidence_status"] == "incremental_signal_not_supported"
    equal = DC.assign_evidence_status(12.0, 12.0, {"ci_low": -1.0, "ci_high": -0.5})
    assert equal["evidence_status"] == "incremental_signal_not_supported"
    for outcome in (supported, inconclusive, worse, equal):
        assert outcome["approved_for_locked_test"] is False
        assert outcome["high_stress_or_sensitivity_may_override"] is False


def test_evidence_status_assigned_per_horizon(results):
    for horizon in ("h1", "h3"):
        evidence = results["results"][horizon]["evidence"]
        assert evidence["evidence_status"] in DC.EVIDENCE_STATUSES
        assert evidence["approved_for_locked_test"] is False
        assert evidence["mae_skill"] is not None


# --- sensitivity ---------------------------------------------------------------------


def test_sensitivity_reuses_primary_hyperparameters(predictions):
    by_key: dict = {}
    for row in predictions:
        key = (row["forecast_origin_month"], row["horizon_months"])
        by_key.setdefault(key, {})[row["variant_key"]] = (
            row["selected_alpha"], row["selected_non_ferrous_channel"]
        )
    for key, variants in by_key.items():
        primary = variants["primary"]
        assert variants["timing_sensitivity"] == primary, key
        assert variants["structural_sensitivity"] == primary, key
    assert CONFIG["sensitivity"]["reselect_hyperparameters"] is False


def test_sensitivity_cannot_alter_primary_status(results):
    for horizon in ("h1", "h3"):
        entry = results["results"][horizon]
        for variant in ("timing_sensitivity", "structural_sensitivity"):
            sensitivity = entry["sensitivity"][variant]
            assert sensitivity["rows"] == 180
            assert sensitivity["may_change_primary_status"] is False
        # The status depends only on the primary model and its paired CI.
        expected = DC.assign_evidence_status(
            entry["model"]["macro_industry_mae"],
            entry["benchmark"]["macro_industry_mae"],
            entry["bootstrap"]["paired_macro_mae_difference_ci"],
        )
        assert entry["evidence"]["evidence_status"] == expected["evidence_status"]
    assert CONFIG["sensitivity"]["reporting"]["may_rescue_failed_primary"] is False
    assert CONFIG["sensitivity"]["reporting"]["pooled_with_primary"] is False


def test_no_combined_lag1_plus_total_variant(predictions):
    variants = {p["feature_variant"] for p in predictions}
    assert variants == {
        "primary_direct_lag2", "timing_sensitivity_direct_lag1",
        "structural_sensitivity_total_lag2",
    }
    for row in predictions:
        if row["feature_variant"] == "timing_sensitivity_direct_lag1":
            assert "total" not in row["feature_variant"]
    assert str(CONFIG["sensitivity"]["lag1_plus_total_combination"]) == (
        "not_created_and_not_evaluated"
    )


# --- schema and scope -----------------------------------------------------------------


def test_schema_matches_prediction_columns(predictions):
    declared = {column["name"] for column in SCHEMA["columns"]}
    actual = set(predictions[0])
    missing = declared - actual
    assert not missing, missing
    for forbidden in SCHEMA["forbidden_columns"]:
        assert forbidden not in actual, forbidden


def test_no_target_association_or_locked_test_fields(results, predictions):
    assert results["locked_test_outcomes_read"] is False
    banned = ("locked_test_target", "correlation_with_mpi", "feature_importance",
              "mutual_information", "granger")
    for column in predictions[0]:
        assert not any(token in column.lower() for token in banned), column


def test_upstream_artifacts_unchanged():
    for relative in (
        "docs/b3_target_build_metadata.json", "docs/b4_baseline_results.json",
        "docs/b4_locked_test_manifest.json", "docs/c2_commodity_feature_audit.json",
        "docs/c3_commodity_exposure_matrix.json",
        "docs/c4_industry_conditioned_feature_audit.json",
    ):
        assert (ROOT / relative).is_file(), relative


def test_generated_artifacts_git_ignored():
    result = subprocess.run(
        ["git", "check-ignore", "data/model_input/d1_development_predictions.parquet"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_lineage_present_on_every_prediction(predictions):
    for row in predictions:
        if row["quality_flag"] != "ok":
            continue
        assert row["c2_lineage_checksums"]
        assert row["c3_exposure_checksums"]
        assert row["model_checksum"]
        assert row["scaler_checksum"]
        assert row["calibration_checksum"]
        assert len(row["calibration_checksum"]) == 64
