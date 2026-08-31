"""Task B3 — Industry Production Stress Score target tests.

FIXTURE POLICY: synthetic values are TEST FIXTURES using round, implausible
numbers (100.0, 90.0, 60.0) so they can never be mistaken for real OIE
observations. Tests reading the real artifact are named "real_" or "snapshot".

Several tests deliberately ATTEMPT temporal leakage and assert it is refused.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.targets.calibration import (  # noqa: E402
    CalibratorNotFittedError,
    IndustryStressCalibrator,
    InsufficientReferenceError,
    LeakageError,
    UnknownIndustryError,
    assign_risk_levels,
    risk_level_for_score,
)
from thai_supply_chain_ews.targets.labels import (  # noqa: E402
    add_months,
    build_forecast_labels,
)
from thai_supply_chain_ews.targets.production_stress import (  # noqa: E402
    DEFAULT_PANEL_PATH,
    B3InvariantError,
    ComponentSemanticsError,
    build_monthly_stress,
    load_target_config,
    mpi_adverse_yoy,
)

CONFIG = load_target_config()
METADATA_PATH = ROOT / "docs" / "b3_target_build_metadata.json"


def real_panel() -> pd.DataFrame:
    if not DEFAULT_PANEL_PATH.is_file():
        pytest.skip("B1 panel not built — run scripts/run_b1_ingestion.py")
    return pd.read_parquet(DEFAULT_PANEL_PATH)


def monthly():
    return build_monthly_stress(real_panel(), CONFIG)


def labels():
    return build_forecast_labels(monthly().frame, CONFIG)


# --- formula, direction, denominator ----------------------------------------


def test_mpi_adverse_yoy_formula():
    # TEST FIXTURE: 100 -> 90 is a 10% fall, adverse = +10
    assert mpi_adverse_yoy(np.array([90.0]), np.array([100.0]))[0] == pytest.approx(10.0)
    assert mpi_adverse_yoy(np.array([80.0]), np.array([100.0]))[0] == pytest.approx(20.0)


def test_adverse_direction_is_positive_for_decline():
    assert mpi_adverse_yoy(np.array([90.0]), np.array([100.0]))[0] > 0  # decline
    assert mpi_adverse_yoy(np.array([100.0]), np.array([100.0]))[0] == 0.0  # unchanged
    assert mpi_adverse_yoy(np.array([110.0]), np.array([100.0]))[0] < 0  # improvement


def test_zero_and_negative_denominator_are_rejected():
    with pytest.raises(ComponentSemanticsError, match="non-positive"):
        mpi_adverse_yoy(np.array([100.0]), np.array([0.0]))
    with pytest.raises(ComponentSemanticsError, match="non-positive"):
        mpi_adverse_yoy(np.array([100.0]), np.array([-1.0]))


# --- monthly raw stress ------------------------------------------------------


def test_preliminary_months_are_excluded():
    result = monthly()
    assert "2026-06-01" not in set(result.frame["reference_month"])
    panel = real_panel()
    prelim = {
        str(m)
        for m in panel.loc[
            panel["mpi_is_preliminary"] | panel["capu_is_preliminary"], "reference_month"
        ]
    }
    assert prelim == {"2026-06-01"}


def test_first_twelve_months_remain_unavailable():
    result = monthly()
    present = set(result.frame["reference_month"])
    for m in [f"2021-{i:02d}-01" for i in range(1, 13)]:
        assert m not in present
    assert result.frame["mpi_adverse_yoy"].notna().all()
    assert CONFIG["raw_stress"]["impute_first_twelve_months"] is False


def test_636_monthly_raw_stress_rows():
    result = monthly()
    assert len(result.frame) == 636 == 53 * 12
    counts = result.frame.groupby("industry_id").size()
    assert set(counts.unique()) == {53}
    assert result.months[0] == "2022-01-01"
    assert result.months[-1] == "2026-05-01"


def test_audit_columns_are_retained_and_consistent():
    frame = monthly().frame
    for column in ("mpi_level", "mpi_level_lagged", "lag_source_month"):
        assert column in frame.columns
    assert (frame["mpi_level_lagged"] > 0).all()
    sample = frame.head(40)
    recomputed = -100.0 * (sample["mpi_level"] / sample["mpi_level_lagged"] - 1.0)
    assert np.allclose(recomputed.to_numpy(), sample["mpi_adverse_yoy"].to_numpy())
    for _, row in sample.iterrows():
        assert add_months(row["lag_source_month"], 12) == row["reference_month"]


def test_no_winsorizing_or_clipping_occurs():
    frame = monthly().frame
    assert CONFIG["raw_stress"]["winsorize"] is False
    assert CONFIG["raw_stress"]["clip"] is False
    # extremes survive: the observed range is far wider than any clip band
    assert frame["mpi_adverse_yoy"].max() > 20 or frame["mpi_adverse_yoy"].min() < -20


# --- horizon label counts and ranges ----------------------------------------


def test_624_one_month_target_rows_with_exact_origin_range():
    frame = labels().for_horizon(1)
    assert len(frame) == 624 == 52 * 12
    origins = sorted(frame["forecast_origin_month"].unique())
    assert origins[0] == "2022-01-01"
    assert origins[-1] == "2026-04-01"
    assert set(frame.groupby("industry_id").size().unique()) == {52}


def test_600_three_month_target_rows_with_exact_origin_range():
    frame = labels().for_horizon(3)
    assert len(frame) == 600 == 50 * 12
    origins = sorted(frame["forecast_origin_month"].unique())
    assert origins[0] == "2022-01-01"
    assert origins[-1] == "2026-02-01"
    assert set(frame.groupby("industry_id").size().unique()) == {50}


def test_1224_combined_target_rows():
    frame = labels().frame
    assert len(frame) == 1224 == 624 + 600
    assert not frame.duplicated(
        subset=["forecast_origin_month", "industry_id", "horizon_months"]
    ).any()


# --- alignment ---------------------------------------------------------------


def test_one_month_target_aligns_to_origin_plus_one():
    monthly_frame = monthly().frame
    lookup = {
        (r["industry_id"], r["reference_month"]): r["mpi_adverse_yoy"]
        for _, r in monthly_frame.iterrows()
    }
    frame = labels().for_horizon(1)
    for _, row in frame.head(60).iterrows():
        expected_month = add_months(row["forecast_origin_month"], 1)
        assert row["target_window_start"] == expected_month
        assert row["target_window_end"] == expected_month
        assert row["target_raw_value"] == pytest.approx(
            lookup[(row["industry_id"], expected_month)]
        )
        assert row["target_peak_month"] == expected_month
        assert row["target_peak_lead_month"] == 1


def test_three_month_target_is_the_maximum_over_the_window():
    monthly_frame = monthly().frame
    lookup = {
        (r["industry_id"], r["reference_month"]): r["mpi_adverse_yoy"]
        for _, r in monthly_frame.iterrows()
    }
    frame = labels().for_horizon(3)
    for _, row in frame.head(60).iterrows():
        window = [add_months(row["forecast_origin_month"], k) for k in (1, 2, 3)]
        values = [lookup[(row["industry_id"], m)] for m in window]
        assert row["target_raw_value"] == pytest.approx(max(values))
        assert row["target_window_start"] == window[0]
        assert row["target_window_end"] == window[2]
        assert row["target_peak_month"] == window[values.index(max(values))]


def test_earliest_peak_month_wins_a_tie():
    """TEST FIXTURE: identical values in all three window months — the peak must
    resolve to the earliest, deterministically.
    """
    months = [f"2022-{m:02d}-01" for m in range(1, 7)]
    frame = pd.DataFrame(
        {
            "reference_month": months,
            "industry_id": "IND-T",
            "mpi_adverse_yoy": [0.0, 5.0, 5.0, 5.0, 1.0, 1.0],
        }
    )
    # Deep copy, then keep ONLY the copy's own nested objects — re-linking to
    # CONFIG["horizons"][3] here would alias the shared config and mutate it.
    config = json.loads(json.dumps(CONFIG, default=str))
    config["horizons_months"] = [3]
    config["horizons"] = {3: config["horizons"]["3"]}
    config["horizons"][3]["expected"] = {
        "first_origin": "2022-01-01", "last_origin": "2022-03-01",
        "origins_per_industry": 3, "rows": 3,
    }
    config["expected_combined_label_rows"] = 3
    result = build_forecast_labels(frame, config)
    first = result.frame[result.frame["forecast_origin_month"] == "2022-01-01"].iloc[0]
    assert first["target_raw_value"] == pytest.approx(5.0)
    assert first["target_peak_month"] == "2022-02-01"  # earliest of the tied months
    assert first["target_peak_lead_month"] == 1


# --- no window may cross into preliminary data ------------------------------


def test_no_target_window_reaches_the_preliminary_month():
    frame = labels().frame
    for column in ("target_window_start", "target_window_end", "target_peak_month"):
        assert "2026-06-01" not in set(frame[column])
    assert CONFIG["excluded_target_months"] == ["2026-06-01"] or [
        str(m) for m in CONFIG["excluded_target_months"]
    ] == ["2026-06-01"]


def test_incomplete_window_is_dropped_not_truncated():
    """2026-03 has only 2 future months available, so it must NOT appear as a
    3-month origin — a max over 2 months is a different quantity.
    """
    frame = labels().for_horizon(3)
    origins = set(frame["forecast_origin_month"])
    assert "2026-03-01" not in origins
    assert "2026-04-01" not in origins
    assert "2026-02-01" in origins


# --- ECDF calibrator ---------------------------------------------------------


def _toy_reference(values, industry_id="IND-T", start_month="2022-01-01"):
    months = [add_months(start_month, i) for i in range(len(values))]
    return pd.DataFrame(
        {"reference_month": months, "industry_id": industry_id, "mpi_adverse_yoy": values}
    )


def test_ecdf_formula_matches_manual_calculation():
    # TEST FIXTURE reference: 0..23 inclusive, n=24
    reference = _toy_reference([float(v) for v in range(24)])
    cal = IndustryStressCalibrator(min_reference_observations=24).fit(
        reference, training_cutoff_month="2099-01-01"
    )
    # x = 10 -> count(<10)=10, count(==10)=1 -> 100*(10+0.5)/24
    assert cal.transform("IND-T", 10.0)[0] == pytest.approx(100.0 * 10.5 / 24)
    # x = 5.5 (between values) -> count(<)=6, count(==)=0
    assert cal.transform("IND-T", 5.5)[0] == pytest.approx(100.0 * 6 / 24)


def test_ecdf_boundaries_reach_zero_and_one_hundred():
    reference = _toy_reference([float(v) for v in range(24)])
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month="2099-01-01")
    assert cal.transform("IND-T", -999.0)[0] == 0.0
    assert cal.transform("IND-T", 999.0)[0] == 100.0
    scores = cal.transform("IND-T", np.array([-999.0, 999.0]))
    assert scores.min() >= 0.0 and scores.max() <= 100.0


def test_ecdf_tie_handling_is_deterministic_and_midpoint():
    # TEST FIXTURE: 24 observations, twelve 5.0 and twelve 9.0
    reference = _toy_reference([5.0] * 12 + [9.0] * 12)
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month="2099-01-01")
    score = cal.transform("IND-T", 5.0)[0]
    assert score == pytest.approx(100.0 * (0 + 0.5 * 12) / 24)  # == 25.0
    assert cal.transform("IND-T", 5.0)[0] == score  # repeatable


def test_calibration_is_industry_specific():
    """The same raw value must score differently in a calm vs a volatile
    industry — that is the entire point of industry-relative calibration.
    """
    calm = _toy_reference([float(v) for v in range(24)], industry_id="IND-CALM")
    volatile = _toy_reference([float(v) * 10 for v in range(24)], industry_id="IND-VOL")
    reference = pd.concat([calm, volatile], ignore_index=True)
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month="2099-01-01")
    assert cal.transform("IND-CALM", 20.0)[0] > cal.transform("IND-VOL", 20.0)[0]


def test_minimum_reference_observations_failure_is_recorded_not_silent():
    reference = _toy_reference([float(v) for v in range(10)], industry_id="IND-SHORT")
    cal = IndustryStressCalibrator(min_reference_observations=24).fit(
        reference, training_cutoff_month="2099-01-01"
    )
    assert "IND-SHORT" not in cal.fitted_industries
    assert "IND-SHORT" in cal.excluded_industries  # recorded, not silently dropped
    assert cal.excluded_industries["IND-SHORT"]["n"] == 10
    with pytest.raises(InsufficientReferenceError, match="below the required minimum"):
        cal.transform("IND-SHORT", 1.0)


def test_unseen_industry_is_rejected_with_no_pooled_fallback():
    reference = _toy_reference([float(v) for v in range(24)])
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month="2099-01-01")
    with pytest.raises(UnknownIndustryError, match="not fitted"):
        cal.transform("IND-NEVER-SEEN", 1.0)


def test_transform_before_fit_is_rejected():
    with pytest.raises(CalibratorNotFittedError):
        IndustryStressCalibrator().transform("IND-T", 1.0)


def test_transform_is_frozen_and_does_not_refit():
    reference = _toy_reference([float(v) for v in range(24)])
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month="2099-01-01")
    fingerprint_before = cal.reference_for("IND-T").fingerprint
    n_before = cal.reference_for("IND-T").n
    # transform an extreme value many times
    for _ in range(5):
        cal.transform("IND-T", 10_000.0)
    assert cal.reference_for("IND-T").fingerprint == fingerprint_before
    assert cal.reference_for("IND-T").n == n_before
    assert CONFIG["calibration"]["refit_during_transform"] is False


def test_calibrator_serialization_is_deterministic_and_round_trips(tmp_path):
    reference = _toy_reference([float(v) for v in range(24)])
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month="2099-01-01")
    first = cal.to_json(tmp_path / "a.json").read_bytes()
    second = IndustryStressCalibrator().fit(
        reference, training_cutoff_month="2099-01-01"
    ).to_json(tmp_path / "b.json").read_bytes()
    assert first == second
    restored = IndustryStressCalibrator.from_dict(json.loads(first.decode("utf-8")))
    assert restored.transform("IND-T", 10.0)[0] == pytest.approx(cal.transform("IND-T", 10.0)[0])
    assert restored.training_cutoff_month == cal.training_cutoff_month


# --- leakage: deliberate attempts that must be refused ----------------------


def test_explicit_cutoff_is_required():
    reference = _toy_reference([float(v) for v in range(24)])
    with pytest.raises(ValueError, match="training_cutoff_month is required"):
        IndustryStressCalibrator().fit(reference, training_cutoff_month=None)


def test_leakage_attempt_future_months_in_reference_is_refused():
    """Deliberate leakage attempt: hand the calibrator months beyond the cutoff."""
    reference = _toy_reference([float(v) for v in range(30)])  # runs into 2024
    with pytest.raises(LeakageError, match="after the training cutoff"):
        IndustryStressCalibrator().fit(reference, training_cutoff_month="2023-01-01")


def test_leakage_attempt_validation_values_cannot_enter_fit():
    """Deliberate leakage attempt: append a single held-out extreme observation
    dated after the cutoff and confirm fitting is refused rather than absorbing it.
    """
    train = _toy_reference([float(v) for v in range(24)], start_month="2022-01-01")
    cutoff = train["reference_month"].max()
    held_out = pd.DataFrame(
        {
            "reference_month": [add_months(cutoff, 1)],
            "industry_id": ["IND-T"],
            "mpi_adverse_yoy": [9_999.0],
        }
    )
    contaminated = pd.concat([train, held_out], ignore_index=True)
    with pytest.raises(LeakageError):
        IndustryStressCalibrator().fit(contaminated, training_cutoff_month=cutoff)
    # fitting on the clean training data alone succeeds and never saw 9999
    clean = IndustryStressCalibrator().fit(train, training_cutoff_month=cutoff)
    assert 9_999.0 not in clean.reference_for("IND-T").sorted_values
    assert clean.reference_for("IND-T").n == 24


def test_real_fold_calibrator_never_saw_post_cutoff_months():
    result = monthly()
    cutoff = "2024-12-01"
    reference = result.frame[result.frame["reference_month"] <= cutoff]
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month=cutoff)
    for industry_id in cal.fitted_industries:
        assert cal.reference_for(industry_id).end_month <= cutoff


def test_b2_diagnostic_rank_is_not_reused():
    assert CONFIG["calibration"]["reuse_b2_diagnostic_rank"] is False
    frame = monthly().frame
    for column in frame.columns:
        assert "diagnostic_only_full_sample" not in column


def test_no_full_sample_calibrated_score_is_persisted():
    for path in (ROOT / "data" / "targets").glob("*.parquet"):
        columns = set(pd.read_parquet(path).columns)
        assert not any("score" in c for c in columns), f"{path.name} persists a score column"
        assert not any("risk_level" in c for c in columns)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    assert metadata["calibrated_scores_persisted_as_production_output"] is False


# --- risk levels -------------------------------------------------------------


def test_risk_level_boundaries_at_70_85_95():
    bands = CONFIG["risk_levels"]
    assert risk_level_for_score(0.0, bands) == "Normal"
    assert risk_level_for_score(69.999, bands) == "Normal"
    assert risk_level_for_score(70.0, bands) == "Watch"  # boundary is inclusive-low
    assert risk_level_for_score(84.999, bands) == "Watch"
    assert risk_level_for_score(85.0, bands) == "High"
    assert risk_level_for_score(94.999, bands) == "High"
    assert risk_level_for_score(95.0, bands) == "Severe"
    assert risk_level_for_score(100.0, bands) == "Severe"


def test_assign_risk_levels_vectorized():
    bands = CONFIG["risk_levels"]
    assert assign_risk_levels([0.0, 70.0, 85.0, 95.0], bands) == [
        "Normal", "Watch", "High", "Severe"
    ]


def test_risk_levels_are_documented_as_policy_not_ground_truth():
    policy = CONFIG["risk_level_policy"]
    assert policy["primary_ml_task"] == "continuous_prediction"
    assert policy["risk_levels_are_derived_presentation_outputs"] is True
    assert policy["tune_thresholds_on_final_test_period"] is False
    assert policy["class_frequencies_may_be_imbalanced_by_design"] is True


# --- monotonicity equivalence ------------------------------------------------


def test_score_then_max_equals_max_then_score():
    """The ECDF is monotone non-decreasing, so scoring each month and taking the
    maximum score must agree with scoring the maximum raw value.
    """
    result = monthly()
    cutoff = "2024-12-01"
    reference = result.frame[result.frame["reference_month"] <= cutoff]
    cal = IndustryStressCalibrator().fit(reference, training_cutoff_month=cutoff)

    lookup = {
        (r["industry_id"], r["reference_month"]): r["mpi_adverse_yoy"]
        for _, r in result.frame.iterrows()
    }
    three_month = build_forecast_labels(result.frame, CONFIG).for_horizon(3)
    checked = 0
    for _, row in three_month.head(120).iterrows():
        window = [add_months(row["forecast_origin_month"], k) for k in (1, 2, 3)]
        values = np.array([lookup[(row["industry_id"], m)] for m in window])
        max_then_score = cal.transform(row["industry_id"], row["target_raw_value"])[0]
        score_then_max = cal.transform(row["industry_id"], values).max()
        assert max_then_score == pytest.approx(score_then_max)
        checked += 1
    assert checked == 120


# --- CapU exclusion ----------------------------------------------------------


def test_capu_columns_never_appear_in_target_artifacts():
    for frame in (monthly().frame, labels().frame):
        for column in frame.columns:
            assert "capu" not in column.lower()
            assert "capacity" not in column.lower()


def test_perturbing_capu_cannot_change_the_target():
    """Strongest form of the exclusion check: corrupt CapU wholesale and confirm
    the target is bit-for-bit identical.
    """
    panel = real_panel()
    baseline = build_monthly_stress(panel.copy(), CONFIG).frame
    perturbed_panel = panel.copy()
    perturbed_panel["capacity_utilization_rate"] = (
        perturbed_panel["capacity_utilization_rate"] * 3.0 + 17.0
    )
    perturbed = build_monthly_stress(perturbed_panel, CONFIG).frame
    pd.testing.assert_frame_equal(baseline, perturbed)


def test_config_records_capu_as_auxiliary_and_excluded():
    import yaml

    targets = yaml.safe_load((ROOT / "configs" / "targets.yaml").read_text(encoding="utf-8"))
    capu = [c for c in targets["components"] if c["component_id"] == "capu_decline"][0]
    assert capu["target_role"] == "auxiliary"
    assert capu["included_in_primary_target"] is False
    assert capu["target_approved"] is False
    assert capu["contemporaneous_or_future_use_prohibited"] is True
    mpi = [c for c in targets["components"] if c["component_id"] == "mpi_decline"][0]
    assert mpi["target_role"] == "primary"
    assert mpi["included_in_primary_target"] is True
    assert mpi["target_approved"] is True


def test_b2_equal_weight_rejection_is_preserved():
    import yaml

    targets = yaml.safe_load((ROOT / "configs" / "targets.yaml").read_text(encoding="utf-8"))
    assert targets["aggregation"]["equal_weight_composite_status"] == "rejected"
    assert targets["aggregation"]["redundancy_status"] == "redundant"


# --- upstream data integrity and determinism --------------------------------


def test_b1_panel_is_not_modified_by_b3():
    before = DEFAULT_PANEL_PATH.read_bytes()
    build_forecast_labels(build_monthly_stress(real_panel(), CONFIG).frame, CONFIG)
    assert DEFAULT_PANEL_PATH.read_bytes() == before
    if METADATA_PATH.is_file():
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        assert metadata["b1_panel_unmodified"] is True


def test_b3_stops_when_a_b1_invariant_fails():
    panel = real_panel()
    broken = panel[panel["industry_id"] != "IND-05"]
    with pytest.raises(B3InvariantError, match="industry_count"):
        build_monthly_stress(broken, CONFIG)


def test_generated_artifacts_are_deterministic():
    first = build_monthly_stress(real_panel(), CONFIG).frame
    second = build_monthly_stress(real_panel(), CONFIG).frame
    pd.testing.assert_frame_equal(first, second)
    l1 = build_forecast_labels(first, CONFIG).frame
    l2 = build_forecast_labels(second, CONFIG).frame
    pd.testing.assert_frame_equal(l1, l2)


def test_example_calibrator_artifact_is_reproducible():
    artifact = ROOT / "docs" / "b3_example_calibrator.json"
    if not artifact.is_file():
        pytest.skip("run scripts/run_b3_target_build.py first")
    stored = artifact.read_bytes()
    result = monthly()
    cutoff = "2024-12-01"
    reference = result.frame[result.frame["reference_month"] <= cutoff]
    cal = IndustryStressCalibrator(
        min_reference_observations=int(CONFIG["calibration"]["min_reference_observations"]),
        version=CONFIG["calibration"]["calibrator_version"],
    ).fit(reference, training_cutoff_month=cutoff)
    rebuilt = json.dumps(cal.to_dict(), indent=2, ensure_ascii=False, sort_keys=False)
    assert hashlib.sha256(rebuilt.encode("utf-8")).hexdigest() == hashlib.sha256(
        stored
    ).hexdigest()


def test_metadata_matches_recomputed_artifacts():
    if not METADATA_PATH.is_file():
        pytest.skip("run scripts/run_b3_target_build.py first")
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    assert metadata["monthly_raw_stress"]["rows"] == len(monthly().frame)
    assert metadata["forecast_labels"]["combined_rows"] == len(labels().frame)
    assert metadata["target_name"] == "industry_production_stress_score"
    assert metadata["primary_component_count"] == 1
    assert metadata["point_in_time_backtest_supported"] is False
