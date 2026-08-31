"""Task B2 — component semantics and redundancy-gate tests.

FIXTURE POLICY: synthetic values are TEST FIXTURES built to exercise formulas
and gate logic. They use round, implausible numbers (100.0, 60.0, weights of
30/70) so they can never be mistaken for real OIE observations. Tests named
"real_" or "snapshot" read the actual B1 artifact.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.targets.component_diagnostics import (  # noqa: E402
    B2InvariantError,
    ComponentSemanticsError,
    build_diagnostic_sample,
    capu_adverse_yoy_pp,
    classify_redundancy,
    decide_approvals,
    diagnostic_percentile_rank,
    high_stress_overlap,
    lead_lag_table,
    load_gate,
    moving_block_spearman_ci,
    mpi_adverse_yoy,
    pooled_correlations,
    run_diagnostics,
    spearman,
    validate_b1_invariants,
)

PANEL_PATH = ROOT / "data" / "processed" / "industry_month_panel.parquet"
OUTPUT_PATH = ROOT / "docs" / "b2_component_validation_output.json"
GATE = load_gate()


def real_panel() -> pd.DataFrame:
    if not PANEL_PATH.is_file():
        pytest.skip("B1 panel not built — run scripts/run_b1_ingestion.py")
    return pd.read_parquet(PANEL_PATH)


def load_output() -> dict:
    if not OUTPUT_PATH.is_file():
        pytest.skip("run scripts/run_b2_component_validation.py first")
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


# --- MPI adverse-change formula and direction --------------------------------


def test_mpi_adverse_formula_and_direction():
    # TEST FIXTURE: 100 -> 90 is a 10% production fall = +10 adverse
    assert mpi_adverse_yoy(np.array([90.0]), np.array([100.0]))[0] == pytest.approx(10.0)
    # improvement is negative
    assert mpi_adverse_yoy(np.array([110.0]), np.array([100.0]))[0] == pytest.approx(-10.0)
    # unchanged is exactly zero
    assert mpi_adverse_yoy(np.array([100.0]), np.array([100.0]))[0] == 0.0


def test_mpi_adverse_rejects_non_positive_denominator():
    with pytest.raises(ComponentSemanticsError, match="non-positive"):
        mpi_adverse_yoy(np.array([100.0]), np.array([0.0]))
    with pytest.raises(ComponentSemanticsError, match="non-positive"):
        mpi_adverse_yoy(np.array([100.0]), np.array([-5.0]))


# --- CapU additive percentage-point formula and direction -------------------


def test_capu_adverse_is_additive_percentage_points():
    # TEST FIXTURE: 60% -> 55% is a 5 PERCENTAGE POINT fall = +5 adverse
    assert capu_adverse_yoy_pp(np.array([55.0]), np.array([60.0]))[0] == pytest.approx(5.0)
    assert capu_adverse_yoy_pp(np.array([65.0]), np.array([60.0]))[0] == pytest.approx(-5.0)
    assert capu_adverse_yoy_pp(np.array([60.0]), np.array([60.0]))[0] == 0.0


def test_capu_is_never_treated_as_a_relative_percentage_change():
    """60 -> 55 is +5.0 pp. A relative change would be +8.333%. The two must
    not be confused, and the pp figure must never be produced by a ratio.
    """
    pp = capu_adverse_yoy_pp(np.array([55.0]), np.array([60.0]))[0]
    relative_would_be = -100.0 * (55.0 / 60.0 - 1.0)
    assert pp == pytest.approx(5.0)
    assert relative_would_be == pytest.approx(8.3333, abs=1e-4)
    assert not math.isclose(pp, relative_would_be)


def test_capu_adverse_is_scale_shift_invariant_unlike_a_ratio():
    """An additive difference depends only on the gap; a ratio would not."""
    a = capu_adverse_yoy_pp(np.array([55.0]), np.array([60.0]))[0]
    b = capu_adverse_yoy_pp(np.array([35.0]), np.array([40.0]))[0]
    assert a == pytest.approx(b) == pytest.approx(5.0)
    assert -100.0 * (55.0 / 60.0 - 1.0) != pytest.approx(-100.0 * (35.0 / 40.0 - 1.0))


def test_gate_forbids_relative_change_for_capu():
    assert GATE["components"]["capu"]["forbid_relative_percentage_change"] is True
    assert GATE["components"]["capu"]["forbid_multiplicative_ratio"] is True
    assert GATE["components"]["capu"]["unit"] == "percentage_points"
    assert GATE["components"]["mpi"]["unit"] == "percent"


# --- sample construction -----------------------------------------------------


def test_preliminary_observations_are_excluded_from_the_sample():
    panel = real_panel()
    sample = build_diagnostic_sample(panel, GATE)
    prelim_months = {
        str(m)
        for m in panel.loc[
            panel["mpi_is_preliminary"] | panel["capu_is_preliminary"], "reference_month"
        ]
    }
    assert prelim_months == {"2026-06-01"}
    assert not (set(sample.frame["reference_month"]) & prelim_months)


def test_exactly_53_usable_months_per_industry():
    sample = build_diagnostic_sample(real_panel(), GATE)
    counts = sample.frame.groupby("industry_id").size()
    assert set(counts.unique()) == {53}
    assert len(counts) == 12


def test_exactly_636_diagnostic_rows():
    sample = build_diagnostic_sample(real_panel(), GATE)
    assert sample.observation_count == 636 == 53 * 12


def test_first_and_last_usable_months():
    sample = build_diagnostic_sample(real_panel(), GATE)
    assert sample.months[0] == "2022-01-01"
    assert sample.months[-1] == "2026-05-01"


def test_first_twelve_months_are_absent_not_imputed():
    """2021-01..2021-12 have no 12-month lag source and must simply not exist."""
    sample = build_diagnostic_sample(real_panel(), GATE)
    present = set(sample.frame["reference_month"])
    for month in [f"2021-{m:02d}-01" for m in range(1, 13)]:
        assert month not in present
    assert sample.frame["mpi_adverse_yoy"].notna().all()
    assert sample.frame["capu_adverse_yoy_pp"].notna().all()
    assert GATE["sample"]["impute_first_twelve_months"] is False


def test_lag_source_is_exactly_twelve_months_earlier():
    sample = build_diagnostic_sample(real_panel(), GATE)
    for _, row in sample.frame.head(50).iterrows():
        month = pd.Timestamp(row["reference_month"])
        lag = pd.Timestamp(row["lag_source_month"])
        assert (month.year - lag.year) * 12 + (month.month - lag.month) == 12


# --- deterministic percentile and tie handling -------------------------------


def test_percentile_rank_is_deterministic_and_uses_average_ties():
    values = np.array([10.0, 20.0, 20.0, 40.0])
    ranks = diagnostic_percentile_rank(values)
    assert ranks[1] == pytest.approx(ranks[2])  # ties share one averaged rank
    assert ranks[0] == pytest.approx(0.25)
    assert ranks[3] == pytest.approx(1.0)  # largest maps to 1.0
    assert np.allclose(ranks, diagnostic_percentile_rank(values))


def test_percentile_rank_is_order_independent():
    values = np.array([3.0, 1.0, 2.0])
    shuffled_idx = np.array([1, 2, 0])
    direct = diagnostic_percentile_rank(values)
    reordered = diagnostic_percentile_rank(values[shuffled_idx])
    assert np.allclose(direct[shuffled_idx], reordered)


def test_high_stress_uses_top_20_percent_deterministically():
    result = load_output()
    for row in result["high_stress_overlap"]:
        # 53 obs, percentile > 0.80 -> ranks 43..53 = 11 months
        assert row["mpi_high_stress_count"] == 11
        assert row["capu_high_stress_count"] == 11
        assert row["union_count"] == (
            row["intersection_count"] + row["mpi_only_count"] + row["capu_only_count"]
        )


# --- pooled correlation uses industry-relative diagnostics -------------------


def test_pooled_correlation_is_computed_on_industry_relative_ranks():
    sample = build_diagnostic_sample(real_panel(), GATE)
    pooled = pooled_correlations(sample)
    assert pooled["primary_basis"] == "industry_relative_diagnostic_ranks"
    assert pooled["n"] == 636
    # the naive raw figure is reported but must be a distinct, secondary number
    assert "secondary_naive_pooled_spearman_raw" in pooled
    assert pooled["spearman_on_ranks"] != pytest.approx(
        pooled["secondary_naive_pooled_spearman_raw"]
    )


def test_diagnostic_ranks_are_labelled_and_not_leakage_safe():
    sample = build_diagnostic_sample(real_panel(), GATE)
    assert "mpi_diagnostic_only_full_sample_rank" in sample.frame.columns
    assert "capu_diagnostic_only_full_sample_rank" in sample.frame.columns
    assert GATE["diagnostic_normalization"]["leakage_safe"] is False
    assert GATE["diagnostic_normalization"]["may_enter_production_panel"] is False


def test_diagnostic_ranks_never_enter_the_production_panel():
    panel = pd.read_parquet(PANEL_PATH) if PANEL_PATH.is_file() else None
    if panel is None:
        pytest.skip("B1 panel not built")
    for column in panel.columns:
        assert "diagnostic" not in column
        assert "rank" not in column


# --- bootstrap reproducibility -----------------------------------------------


def test_moving_block_bootstrap_is_reproducible():
    rng = np.random.default_rng(0)
    a = rng.normal(size=53)
    b = a * 0.7 + rng.normal(size=53) * 0.5
    first = moving_block_spearman_ci(a, b, GATE, industry_index=3)
    second = moving_block_spearman_ci(a, b, GATE, industry_index=3)
    assert first == second
    assert first["replications"] >= 1000 * 0.9
    assert first["block_length"] == 6
    assert first["seed"] == GATE["bootstrap"]["random_seed"]


def test_bootstrap_differs_by_industry_index_but_is_stable_per_index():
    rng = np.random.default_rng(1)
    a = rng.normal(size=53)
    b = a * 0.5 + rng.normal(size=53)
    one = moving_block_spearman_ci(a, b, GATE, industry_index=0)
    two = moving_block_spearman_ci(a, b, GATE, industry_index=1)
    assert one["point_estimate"] == pytest.approx(two["point_estimate"])  # same data
    assert one["ci_low"] != two["ci_low"]  # independent resampling streams
    assert one == moving_block_spearman_ci(a, b, GATE, industry_index=0)


def test_bootstrap_ci_brackets_the_point_estimate_for_a_strong_relationship():
    a = np.linspace(0, 10, 53)
    b = a * 2.0
    result = moving_block_spearman_ci(a, b, GATE, industry_index=0)
    assert result["point_estimate"] == pytest.approx(1.0)
    assert result["ci_low"] <= result["point_estimate"] <= result["ci_high"] + 1e-9


# --- lag sign convention -----------------------------------------------------


def test_lag_sign_convention_is_documented_and_applied():
    convention = GATE["lead_lag"]["sign_convention"]
    assert "k>0 means MPI leads CapU" in convention
    assert GATE["lead_lag"]["causal_interpretation_permitted"] is False
    result = load_output()
    assert result["lead_lag"]["causal_interpretation_permitted"] is False
    assert result["lead_lag"]["lags"] == [-3, -2, -1, 0, 1, 2, 3]


def test_lag_convention_detects_a_constructed_lead():
    """TEST FIXTURE: CapU is MPI shifted one month LATER, so the strongest
    association must appear at k = +1 (MPI leads CapU).
    """
    months = pd.date_range("2022-01-01", periods=53, freq="MS").strftime("%Y-%m-%d")
    base = np.sin(np.arange(53) / 3.0) * 10
    mpi = base
    capu = np.concatenate([[np.nan], base[:-1]])  # capu[t] = mpi[t-1]
    frame = pd.DataFrame(
        {
            "reference_month": months,
            "industry_id": "IND-T",
            "mpi_adverse_yoy": mpi,
            "capu_adverse_yoy_pp": capu,
        }
    )
    frame["mpi_diagnostic_only_full_sample_rank"] = diagnostic_percentile_rank(mpi)
    frame["capu_diagnostic_only_full_sample_rank"] = diagnostic_percentile_rank(capu)

    class _S:
        pass

    sample = _S()
    sample.frame = frame
    sample.industries = ["IND-T"]
    table = lead_lag_table(sample, GATE)
    # capu[t] = mpi[t-1]  =>  mpi[t] == capu[t+1]  =>  peak at k = +1
    assert table["per_industry"][0]["strongest_abs_lag"] == 1


# --- Jaccard -----------------------------------------------------------------


def test_jaccard_calculation_on_a_toy_fixture():
    months = pd.date_range("2022-01-01", periods=10, freq="MS").strftime("%Y-%m-%d")
    # TEST FIXTURE: top-20% of 10 = ranks above 0.8 -> the top 2 values
    mpi = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    capu = np.array([10, 9, 8, 7, 6, 5, 4, 3, 2, 1], dtype=float)  # exactly reversed
    frame = pd.DataFrame(
        {"reference_month": months, "industry_id": "IND-T",
         "mpi_adverse_yoy": mpi, "capu_adverse_yoy_pp": capu}
    )
    frame["mpi_diagnostic_only_full_sample_rank"] = diagnostic_percentile_rank(mpi)
    frame["capu_diagnostic_only_full_sample_rank"] = diagnostic_percentile_rank(capu)

    class _S:
        pass

    sample = _S()
    sample.frame = frame
    sample.industries = ["IND-T"]
    row = high_stress_overlap(sample, GATE)[0]
    assert row["mpi_high_stress_count"] == 2
    assert row["capu_high_stress_count"] == 2
    assert row["intersection_count"] == 0  # reversed series share no top months
    assert row["union_count"] == 4
    assert row["jaccard"] == pytest.approx(0.0)
    assert row["mpi_only_count"] == 2 and row["capu_only_count"] == 2


def test_jaccard_is_one_for_identical_series():
    result = load_output()
    identical = [r for r in result["high_stress_overlap"] if r["jaccard"] == 1.0]
    for row in identical:
        assert row["mpi_only_count"] == 0 and row["capu_only_count"] == 0
        assert row["intersection_count"] == row["union_count"]


# --- synthetic decision-gate cases -------------------------------------------


def _gate_inputs(spearman_values, jaccards, mpi_only, capu_only, pooled_rho):
    per_industry = [
        {"industry_id": f"IND-{i:02d}", "spearman": v, "n": 53}
        for i, v in enumerate(spearman_values, start=1)
    ]
    overlap = [
        {
            "industry_id": f"IND-{i:02d}", "jaccard": j,
            "mpi_only_count": m, "capu_only_count": c,
            "intersection_count": 5, "union_count": 10,
            "mpi_high_stress_count": 11, "capu_high_stress_count": 11,
        }
        for i, (j, m, c) in enumerate(zip(jaccards, mpi_only, capu_only, strict=True), start=1)
    ]
    quality = [
        {"industry_id": f"IND-{i:02d}", "component": comp, "flags": [],
         "is_constant_or_near_constant": False}
        for i in range(1, 13) for comp in ("mpi", "capu")
    ]
    pooled = {"spearman_on_ranks": pooled_rho}
    return pooled, per_industry, overlap, quality


def test_gate_classifies_an_obviously_duplicated_pair_as_redundant():
    pooled, per_industry, overlap, quality = _gate_inputs(
        spearman_values=[0.97] * 12, jaccards=[0.95] * 12,
        mpi_only=[0] * 12, capu_only=[0] * 12, pooled_rho=0.98,
    )
    result = classify_redundancy(pooled, per_industry, overlap, quality, GATE, True)
    assert result["redundancy_status"] == "redundant"


def test_gate_classifies_an_obviously_distinct_pair_as_non_redundant():
    pooled, per_industry, overlap, quality = _gate_inputs(
        spearman_values=[0.10] * 12, jaccards=[0.05] * 12,
        mpi_only=[6] * 12, capu_only=[6] * 12, pooled_rho=0.08,
    )
    result = classify_redundancy(pooled, per_industry, overlap, quality, GATE, True)
    assert result["redundancy_status"] == "non_redundant"


def test_gate_classifies_an_inconclusive_pair():
    """Redundant rule fails, but so does non-redundant: too few industries
    carry component-specific high-stress months.
    """
    pooled, per_industry, overlap, quality = _gate_inputs(
        spearman_values=[0.80] * 12, jaccards=[0.70] * 12,
        mpi_only=[0] * 12, capu_only=[0] * 12, pooled_rho=0.80,
    )
    result = classify_redundancy(pooled, per_industry, overlap, quality, GATE, True)
    assert result["redundancy_status"] == "inconclusive"


def test_unresolved_semantics_failure_blocks_non_redundant():
    pooled, per_industry, overlap, quality = _gate_inputs(
        spearman_values=[0.10] * 12, jaccards=[0.05] * 12,
        mpi_only=[6] * 12, capu_only=[6] * 12, pooled_rho=0.08,
    )
    result = classify_redundancy(pooled, per_industry, overlap, quality, GATE, semantics_ok=False)
    assert result["redundancy_status"] == "inconclusive"


def test_non_redundant_is_never_described_as_independence():
    pooled, per_industry, overlap, quality = _gate_inputs(
        spearman_values=[0.10] * 12, jaccards=[0.05] * 12,
        mpi_only=[6] * 12, capu_only=[6] * 12, pooled_rho=0.08,
    )
    result = classify_redundancy(pooled, per_industry, overlap, quality, GATE, True)
    note = result["interpretation_note"].lower()
    assert "not mean the components are statistically" in note
    assert "independent" in note


# --- approval fields cannot be enabled when prerequisites fail ---------------


def _semantics(ok: bool = True) -> dict:
    return {
        comp: {
            "transform_verified": ok, "direction_verified": ok, "unit_verified": ok,
            "unit": "percent" if comp == "mpi" else "percentage_points",
            "adverse_transform": "x",
        }
        for comp in ("mpi", "capu")
    }


def _stability_ok():
    return [{"name": "early", "pooled_spearman_on_ranks": 0.9, "observations": 100}]


def test_equal_weight_cannot_be_approved_when_pair_is_redundant():
    classification = {"redundancy_status": "redundant"}
    approvals = decide_approvals(classification, [], _stability_ok(), _semantics(True), GATE)
    assert approvals["equal_weight_composite_status"] == "rejected"


def test_equal_weight_cannot_be_approved_when_semantics_fail():
    classification = {"redundancy_status": "non_redundant"}
    approvals = decide_approvals(classification, [], _stability_ok(), _semantics(False), GATE)
    assert approvals["components"]["mpi"]["component_semantics_approved"] is False
    assert approvals["equal_weight_composite_status"] != "approved"


def test_equal_weight_approved_only_when_both_conditions_hold():
    classification = {"redundancy_status": "non_redundant"}
    approvals = decide_approvals(classification, [], _stability_ok(), _semantics(True), GATE)
    assert approvals["equal_weight_composite_status"] == "approved"
    assert "not an estimated optimal weight" in approvals["equal_weight_rationale"]


def test_composite_index_is_not_built_in_b2():
    result = load_output()
    assert result["approvals"]["composite_index_built_in_b2"] is False
    assert GATE["approval"]["composite_index_built_in_b2"] is False


# --- B1 invariants and immutability ------------------------------------------


def test_b1_invariants_are_independently_reproduced():
    findings = validate_b1_invariants(real_panel(), GATE)
    assert findings["all_invariants_reproduced"] is True
    assert findings["panel_rows"] == 792
    assert findings["model_eligible_rows"] == 780
    assert findings["preliminary_rows"] == 12
    assert findings["preliminary_months"] == ["2026-06-01"]
    assert findings["non_preliminary_months"] == 65
    assert findings["editions"] == ["2021_based"]


def test_b2_stops_when_a_material_b1_invariant_fails():
    panel = real_panel().copy()
    panel = panel[panel["industry_id"] != "IND-12"]  # break the 12-industry invariant
    with pytest.raises(B2InvariantError, match="industry_count"):
        validate_b1_invariants(panel, GATE)


def test_production_b1_panel_is_not_modified_by_b2():
    before = PANEL_PATH.read_bytes()
    run_diagnostics(real_panel(), GATE)
    assert PANEL_PATH.read_bytes() == before
    result = load_output()
    assert result["b1_panel_unmodified"] is True


def test_b2_does_not_use_older_editions():
    result = load_output()
    assert result["edition_scope"] == "current_2021_based_only"
    assert result["b1_invariants"]["editions"] == ["2021_based"]


# --- determinism -------------------------------------------------------------


def test_diagnostics_are_deterministic_across_runs():
    first = run_diagnostics(real_panel(), GATE)
    second = run_diagnostics(real_panel(), GATE)
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        second, sort_keys=True, default=str
    )


def test_spearman_helper_is_symmetric_and_deterministic():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([2.0, 1.0, 4.0, 3.0, 5.0])
    assert spearman(a, b) == pytest.approx(spearman(b, a))
    assert spearman(a, b) == spearman(a, b)


def test_output_json_matches_recomputed_diagnostics():
    """The Markdown report must read numbers from this JSON, so the JSON has to
    match a fresh computation rather than drifting from it.
    """
    stored = load_output()
    fresh = run_diagnostics(real_panel(), GATE)
    assert stored["classification"]["redundancy_status"] == fresh["classification"][
        "redundancy_status"
    ]
    assert stored["pooled_correlations"]["spearman_on_ranks"] == pytest.approx(
        fresh["pooled_correlations"]["spearman_on_ranks"]
    )
    assert stored["sample"]["observations"] == fresh["sample"]["observations"]
