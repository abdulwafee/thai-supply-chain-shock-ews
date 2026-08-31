"""Tests for scripts/validate_oie_overlap.py — Task A2 empirical overlap-window
bridge validation.

Synthetic fixtures are used for all unit-level tests (never fabricated real
observations). One integration-style test (`test_main_produces_one_row_per_industry_component`)
exercises the real pipeline end-to-end against the actual downloaded OIE files,
consistent with this project's existing tests in test_audit_target_sources.py
and test_audit_history_extension.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_oie_overlap.py"
_spec = importlib.util.spec_from_file_location("validate_oie_overlap", SCRIPT_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_oie_overlap"] = mod
_spec.loader.exec_module(mod)


def _make_series(edition_id, component, weights, values):
    return mod.DivisionValueSeries(
        edition_id=edition_id,
        component=component,
        file_path="toy.xlsx",
        sha256="deadbeef",
        classification_label="TSIC",
        weights=weights,
        values=values,
        dates=sorted({d for by_date in values.values() for d in by_date}),
    )


def _overlap_values(division_first_value, n=36, step=1.0):
    months = mod.overlap_month_list()
    return {m: division_first_value + i * step for i, m in enumerate(months)}


# --- (1) exactly 36 overlap months ------------------------------------------


def test_overlap_month_list_has_exactly_36_months():
    months = mod.overlap_month_list()
    assert len(months) == 36
    assert months[0] == "2021-01-01"
    assert months[-1] == "2023-12-01"


def test_restrict_to_overlap_rejects_incomplete_series_without_imputing():
    months = mod.overlap_month_list()
    incomplete_values = {m: 100.0 for m in months[:-2]}  # missing last 2 months
    series = _make_series("current", "MPI", {10: 50.0}, {10: incomplete_values})
    with pytest.raises(mod.OverlapIncompleteError):
        mod.restrict_to_overlap(series, 10)


# --- (2) same division composition across compared editions ----------------
# --- (3) IND-03 exclusion ----------------------------------------------------


def test_ind03_excluded_from_candidate_industries():
    assert mod.IND03_EXCLUDED_ID not in mod.CANDIDATE_INDUSTRIES
    assert len(mod.CANDIDATE_INDUSTRIES) == 11


def test_effective_divisions_rejects_inconsistent_composition():
    current = _make_series("current", "MPI", {16: 1.0, 17: 1.0}, {16: {}, 17: {}})
    older = _make_series("2016_based", "MPI", {17: 1.0}, {17: {}})
    divisions, consistent, reason = mod.effective_divisions_for_industry(
        [16, 17], current, older
    )
    assert consistent is False
    assert divisions == []
    assert reason is not None


def test_effective_divisions_allows_consistently_partial_coverage():
    """The IND-12-style case: division 33 missing from BOTH editions is not a
    composition change — the effective set (31, 32) is identical across
    editions.
    """
    current = _make_series("current", "MPI", {31: 1.0, 32: 1.0}, {31: {}, 32: {}})
    older = _make_series("2016_based", "MPI", {31: 1.0, 32: 1.0}, {31: {}, 32: {}})
    divisions, consistent, reason = mod.effective_divisions_for_industry(
        [31, 32, 33], current, older
    )
    assert consistent is True
    assert divisions == [31, 32]
    assert reason is None


# --- (4) ISIC edition excluded from approval --------------------------------


def test_scope_excludes_the_2011_isic_edition():
    assert "2554_2011" in mod.EXCLUDED_EDITIONS
    assert "2554_2011" not in mod.SCOPE_EDITIONS
    assert set(mod.SCOPE_EDITIONS) == {"current", "2016_based"}


# --- (5) no duplicate industry-month keys -----------------------------------


def test_aggregate_industry_series_has_no_duplicate_month_keys():
    values = {10: _overlap_values(100.0), 11: _overlap_values(200.0)}
    series = _make_series("current", "MPI", {10: 60.0, 11: 40.0}, values)
    aggregated, _ = mod.aggregate_industry_series(series, [10, 11])
    months = mod.overlap_month_list()
    assert list(aggregated.keys()) == months
    assert len(aggregated) == len(set(aggregated.keys())) == 36


# --- (6) correct weighted aggregation ----------------------------------------


def test_aggregate_industry_series_matches_manual_weighted_calculation():
    values = {10: _overlap_values(100.0, step=0.0), 11: _overlap_values(200.0, step=0.0)}
    series = _make_series("current", "MPI", {10: 30.0, 11: 70.0}, values)
    aggregated, normalized = mod.aggregate_industry_series(series, [10, 11])
    expected = 0.3 * 100.0 + 0.7 * 200.0
    first_month = mod.overlap_month_list()[0]
    assert aggregated[first_month] == pytest.approx(expected)
    assert normalized == {10: pytest.approx(0.3), 11: pytest.approx(0.7)}


# --- (7) weight renormalization ----------------------------------------------


def test_aggregate_industry_series_renormalizes_when_weights_do_not_sum_to_one():
    """Only divisions {10, 11} are used even though the edition's official
    weights include a third division {12} outside this industry — the used
    weights must renormalize to sum to 1 across exactly {10, 11}, not stay at
    their original (0.3 + 0.4 = 0.7) sum.
    """
    values = {10: _overlap_values(100.0, step=0.0), 11: _overlap_values(200.0, step=0.0)}
    series = _make_series("current", "MPI", {10: 30.0, 11: 40.0, 12: 30.0}, values)
    _, normalized = mod.aggregate_industry_series(series, [10, 11])
    assert sum(normalized.values()) == pytest.approx(1.0)
    assert normalized[10] == pytest.approx(30.0 / 70.0)
    assert normalized[11] == pytest.approx(40.0 / 70.0)


# --- (8) MoM calculation ------------------------------------------------------


def test_build_representations_mom_matches_manual_calculation():
    raw = np.array([100.0, 110.0, 99.0] + [100.0] * 33)
    reps = mod.build_representations(raw)
    assert np.isnan(reps["mom_pct"][0])
    assert reps["mom_pct"][1] == pytest.approx(10.0)
    assert reps["mom_pct"][2] == pytest.approx((99.0 / 110.0 - 1.0) * 100.0)


# --- (9) YoY calculation ------------------------------------------------------


def test_build_representations_yoy_matches_manual_calculation():
    raw = np.array([100.0 + i for i in range(36)])
    reps = mod.build_representations(raw)
    assert np.all(np.isnan(reps["yoy_pct"][:12]))
    expected_month_12 = (raw[12] / raw[0] - 1.0) * 100.0
    assert reps["yoy_pct"][12] == pytest.approx(expected_month_12)


# --- (10) level-link calculation ---------------------------------------------


def test_level_link_factor_is_median_ratio_not_mean():
    current = np.array([100.0, 100.0, 100.0, 400.0])  # one outlier ratio
    older = np.array([50.0, 50.0, 50.0, 50.0])
    factor = mod.level_link_factor(current, older)
    assert factor == pytest.approx(2.0)  # median of [2,2,2,8] == 2, not mean 3.5


# --- (11) no invalid cross-edition lag ---------------------------------------


def test_representations_never_fill_missing_lag_from_another_series():
    """MoM at the first overlap month and YoY at the first 12 overlap months
    must stay NaN — this function must never reach into a different edition's
    values to manufacture a missing lag.
    """
    raw = np.arange(100.0, 136.0)
    reps = mod.build_representations(raw)
    assert np.isnan(reps["mom_pct"][0])
    assert np.all(np.isnan(reps["yoy_pct"][:12]))


# --- (12) metric calculation with missing pairs ------------------------------


def test_compute_metrics_excludes_nan_pairs_from_n_valid():
    months = mod.overlap_month_list()
    a = np.array([100.0] * 36)
    b = np.array([100.0] * 36)
    a[5] = np.nan
    metrics = mod.compute_metrics(a, b, months)
    assert metrics.n_valid == 35
    assert metrics.mean_abs_diff == pytest.approx(0.0)


def test_compute_metrics_applies_absolute_floor_to_discontinuity_detection():
    """Regression test for the real edge case found in IND-04 CapU: when the
    median |diff| is at floating-point noise (~0), a pure relative multiplier
    would flag any nonzero difference as a discontinuity. An absolute floor
    must prevent that.
    """
    months = mod.overlap_month_list()
    a = np.array([100.0] * 36)
    b = a + 1e-13  # floating-point-noise-level baseline diff, like real IND-04 CapU
    b[10] = 100.5  # tiny but real, plausible difference
    metrics_no_floor = mod.compute_metrics(a, b, months, abs_floor=0.0)
    metrics_with_floor = mod.compute_metrics(a, b, months, abs_floor=1.0)
    assert months[10] in metrics_no_floor.discontinuity_months
    assert months[10] not in metrics_with_floor.discontinuity_months


# --- (13) approval status generated from documented criteria ----------------


def _metrics(pearson_r, mean_signed_diff=0.0, n_valid=36, discontinuity=None, per_year=None):
    return mod.RepresentationMetrics(
        n_valid=n_valid,
        pearson_r=pearson_r,
        spearman_r=pearson_r,
        mean_abs_diff=abs(mean_signed_diff),
        median_abs_diff=abs(mean_signed_diff),
        mean_signed_diff=mean_signed_diff,
        max_abs_diff=abs(mean_signed_diff),
        per_year=per_year or {"2021": {"pearson_r": pearson_r, "n_valid": 12}},
        discontinuity_months=discontinuity or [],
    )


def test_approval_criteria_approves_when_all_documented_thresholds_met():
    c = mod.PROVISIONAL_APPROVAL_CRITERIA
    rebased = _metrics(c["rebased_level_min_pearson"] + 0.01)
    mom = _metrics(c["mom_min_pearson"] + 0.01, mean_signed_diff=0.5)
    yoy = _metrics(c["yoy_min_pearson"] + 0.01, mean_signed_diff=0.5)
    status, reasons = mod.apply_approval_criteria(rebased, mom, yoy)
    assert status == "Approved"


def test_approval_criteria_rejects_on_low_rebased_correlation():
    c = mod.PROVISIONAL_APPROVAL_CRITERIA
    rebased = _metrics(0.3)  # well below 0.5 hard-fail line
    mom = _metrics(c["mom_min_pearson"] + 0.01)
    yoy = _metrics(c["yoy_min_pearson"] + 0.01)
    status, reasons = mod.apply_approval_criteria(rebased, mom, yoy)
    assert status == "Rejected"
    assert any("Pearson" in r for r in reasons)


def test_approval_criteria_marks_insufficient_evidence_below_min_valid_pairs():
    c = mod.PROVISIONAL_APPROVAL_CRITERIA
    rebased = _metrics(0.99, n_valid=c["min_valid_pairs_full_confidence"] - 1)
    mom = _metrics(0.99)
    yoy = _metrics(0.99)
    status, reasons = mod.apply_approval_criteria(rebased, mom, yoy)
    assert status == "Insufficient evidence"


def test_approval_criteria_conditional_on_soft_mom_yoy_miss_only():
    c = mod.PROVISIONAL_APPROVAL_CRITERIA
    rebased = _metrics(c["rebased_level_min_pearson"] + 0.01)
    mom = _metrics(c["mom_min_pearson"] - 0.05)  # soft miss, not below 0.5
    yoy = _metrics(c["yoy_min_pearson"] + 0.01)
    status, reasons = mod.apply_approval_criteria(rebased, mom, yoy)
    assert status == "Conditional"


# --- (14) machine-readable count matches actual result rows -----------------


def test_main_produces_one_row_per_industry_component_against_real_data():
    mod.main()
    out_path = mod.PROJECT_ROOT / "docs" / "oie_overlap_validation_output.json"
    output = json.loads(out_path.read_text(encoding="utf-8"))
    results = output["results"]
    assert len(results) == len(mod.CANDIDATE_INDUSTRIES) * len(mod.COMPONENTS)
    pairs = [(r["industry_id"], r["component"]) for r in results]
    assert len(pairs) == len(set(pairs))  # no duplicate industry-component rows
    for r in results:
        assert r["approval_status"] in (
            "Approved", "Conditional", "Rejected", "Insufficient evidence"
        )


# --- (15) deterministic output -----------------------------------------------


def test_compute_metrics_is_deterministic():
    months = mod.overlap_month_list()
    rng_a = np.array([100.0 + (i * 1.3) % 7 for i in range(36)])
    rng_b = np.array([100.0 + (i * 0.9) % 5 for i in range(36)])
    m1 = mod.compute_metrics(rng_a, rng_b, months, abs_floor=1.0)
    m2 = mod.compute_metrics(rng_a, rng_b, months, abs_floor=1.0)
    assert m1 == m2


def test_pearson_spearman_deterministic_and_symmetric():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([2.0, 1.0, 4.0, 3.0, 5.0])
    assert mod.pearson(a, b) == mod.pearson(a, b)
    assert mod.pearson(a, b) == pytest.approx(mod.pearson(b, a))
    assert mod.spearman(a, b) == pytest.approx(mod.spearman(b, a))
