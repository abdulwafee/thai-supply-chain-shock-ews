"""Tests for scripts/validate_oie_overlap_v2.py — Task A2.1 corrections.

Covers the 15 required regression cases. Unit fixtures are synthetic; two
integration tests exercise the real pipeline end-to-end, matching the pattern
already used by this project's other audit tests.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from thai_supply_chain_ews.release import byte_provenance as BP

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "validate_oie_overlap_v2.py"
_spec = importlib.util.spec_from_file_location("validate_oie_overlap_v2", SCRIPT_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_oie_overlap_v2"] = mod
_spec.loader.exec_module(mod)

V2_OUTPUT = ROOT / "docs" / "oie_overlap_validation_output_v2.json"


def _load_v2():
    assert V2_OUTPUT.is_file(), "run scripts/validate_oie_overlap_v2.py first"
    return json.loads(V2_OUTPUT.read_text(encoding="utf-8"))


def _metrics(**kw):
    base = dict(
        n_valid=36, pearson_r=0.99, spearman_r=0.99, mean_abs_error=0.1, rmse=0.1,
        median_abs_error=0.1, mean_signed_bias=0.0, max_abs_error=0.2,
        normalized_mae_iqr=0.05, normalized_bias_iqr=0.01,
        per_year={"2021": {"pearson_r": 0.99, "n_valid": 12}},
        discontinuity_months=[],
    )
    base.update(kw)
    return mod.ErrorMetrics(**base)


def _clean_splice():
    return {
        "boundary_jump": 0.5, "boundary_jump_unit": "percent_growth",
        "boundary_jump_vs_p99_ratio": 0.1, "invalid_cross_edition_lag_used": False,
        "level_no_gaps": True, "level_no_duplicate_keys": True,
    }


# --- (1) positive and negative errors cannot cancel in MAE -------------------


def test_mae_does_not_let_positive_and_negative_errors_cancel():
    months = mod.OVERLAP_MONTHS
    current = np.array([100.0] * 36)
    other = np.array([105.0, 95.0] * 18)  # alternating +5 / -5 errors
    m = mod.compute_error_metrics(current, other, months)
    assert m.mean_signed_bias == pytest.approx(0.0, abs=1e-9)  # cancels
    assert m.mean_abs_error == pytest.approx(5.0)  # does not cancel
    assert m.mean_abs_error > abs(m.mean_signed_bias)


# --- (2) approval uses mean_abs_error, not abs(mean_signed_bias) ------------


def test_approval_gates_on_mean_abs_error_not_signed_bias():
    """A pair whose MoM errors cancel to ~zero bias but carry a large mean
    absolute error must NOT be approved. This is the exact v1 defect.
    """
    bad_mom = _metrics(mean_abs_error=2.8, mean_signed_bias=0.02)
    status, reasons = mod.apply_approval_criteria_v2(
        "MPI", _metrics(), bad_mom, _metrics(), _clean_splice(), []
    )
    assert status != mod.STATUS_APPROVED
    assert any("ABSOLUTE error" in r for r in reasons)
    # and the same pair judged on signed bias alone would have passed
    assert abs(bad_mom.mean_signed_bias) <= mod.CRITERIA["mpi"]["mom_growth"]["max_mae_pp"]


def test_v1_reclassification_examples_now_fail_their_mae_bar():
    """The five pairs the review named, using v1's own recorded MAE values."""
    cases = [
        ("MPI", "mom", 2.0005), ("MPI", "mom", 2.8054), ("MPI", "mom", 2.5531),
        ("MPI", "yoy", 4.0252), ("CapU", "mom", 2.1267), ("CapU", "mom", 2.3920),
        ("CapU", "yoy", 3.7137),
    ]
    for component, rep, mae in cases:
        ck = mod.CRITERIA[mod.CRITERIA_KEY[component]]
        key = (
            ("mom_growth" if rep == "mom" else "yoy_growth")
            if component == "MPI"
            else ("mom_change" if rep == "mom" else "yoy_change")
        )
        assert mae > ck[key]["max_mae_pp"], f"{component} {rep} {mae} should breach its bar"


# --- (3) MPI uses percentage growth -----------------------------------------


def test_mpi_mom_and_yoy_are_ratio_growth_in_percent():
    x = np.array([100.0, 110.0] + [100.0] * 34)
    mom = mod.component_mom(x, "MPI")
    assert np.isnan(mom[0])
    assert mom[1] == pytest.approx(10.0)  # ratio growth, not a 10-point difference
    y = np.array([100.0 + i for i in range(36)])
    yoy = mod.component_yoy(y, "MPI")
    assert yoy[12] == pytest.approx((y[12] / y[0] - 1.0) * 100.0)


# --- (4) CapU uses percentage-point differences -----------------------------


def test_capu_mom_and_yoy_are_percentage_point_differences():
    x = np.array([60.0, 66.0] + [60.0] * 34)
    mom = mod.component_mom(x, "CapU")
    assert np.isnan(mom[0])
    assert mom[1] == pytest.approx(6.0)  # 66 - 60 = 6 pp, NOT 10%
    assert mom[1] != pytest.approx(10.0)
    y = np.array([60.0 + i for i in range(36)])
    yoy = mod.component_yoy(y, "CapU")
    assert yoy[12] == pytest.approx(12.0)  # 72 - 60 pp


def test_capu_and_mpi_transforms_differ_on_identical_input():
    x = np.array([50.0, 55.0] + [50.0] * 34)
    assert mod.component_mom(x, "MPI")[1] == pytest.approx(10.0)  # +10 %
    assert mod.component_mom(x, "CapU")[1] == pytest.approx(5.0)  # +5 pp


# --- (5) MPI multiplicative linking -----------------------------------------


def test_mpi_multiplicative_link_uses_median_ratio():
    current = np.array([100.0, 100.0, 100.0, 400.0])
    older = np.array([50.0, 50.0, 50.0, 50.0])
    f = mod.multiplicative_link_factor(current, older)
    assert f == pytest.approx(2.0)  # median of [2,2,2,8], robust to the outlier
    linked = mod.apply_link(older, "multiplicative_median_ratio", f)
    assert linked[0] == pytest.approx(100.0)


# --- (6) CapU additive linking ----------------------------------------------


def test_capu_additive_link_uses_median_offset_and_is_not_multiplicative():
    """A rising utilisation rate offset by a constant 10pp. Additive alignment
    recovers it exactly; a multiplicative factor cannot, because a constant pp
    offset is not a constant ratio. This is why a percent rate must not get the
    index-number treatment.
    """
    older = np.array([60.0, 65.0, 70.0, 75.0])
    current = older + 10.0
    off = mod.additive_link_offset(current, older)
    assert off == pytest.approx(10.0)
    additive_linked = mod.apply_link(older, "additive_median_offset", off)
    assert np.allclose(additive_linked, current)  # exact recovery

    factor = mod.multiplicative_link_factor(current, older)
    multiplicative_linked = mod.apply_link(older, "multiplicative_median_ratio", factor)
    assert not np.allclose(multiplicative_linked, current)
    assert np.mean(np.abs(current - additive_linked)) < np.mean(
        np.abs(current - multiplicative_linked)
    )


def test_capu_alignment_selection_rule_is_documented_in_config():
    rule = mod.CRITERIA["capacity_utilization"]["alignment_selection_rule"]
    assert rule == "adopt_additive_only_if_it_reduces_linked_level_mae"
    assert mod.CRITERIA["capacity_utilization"]["link_method"] == "additive_median_offset"
    assert mod.CRITERIA["mpi"]["link_method"] == "multiplicative_median_ratio"


# --- (7) actual linked-level metrics are calculated -------------------------


def test_linked_level_metrics_are_computed_against_the_linked_series():
    """Not against two independently rebased series — that was the v1 defect
    which forced both to start at 100 and hid the level gap.
    """
    current = np.array([100.0 + i for i in range(36)])
    older = current / 2.0  # perfectly linkable at factor 2
    f = mod.multiplicative_link_factor(current, older)
    m = mod.compute_error_metrics(current, mod.apply_link(older, "multiplicative_median_ratio", f),
                                  mod.OVERLAP_MONTHS, reference_for_iqr=current)
    assert m.mean_abs_error == pytest.approx(0.0, abs=1e-9)
    # an unlinked comparison would have shown a huge error
    unlinked = mod.compute_error_metrics(current, older, mod.OVERLAP_MONTHS)
    assert unlinked.mean_abs_error > 20.0


def test_real_output_reports_linked_level_error_fields():
    d = _load_v2()
    scored = [r for r in d["results"] if "linked_mean_abs_error" in r]
    assert scored, "no scored rows"
    for r in scored:
        for fld in ("linked_mean_abs_error", "linked_rmse", "linked_median_abs_error",
                    "linked_mean_signed_bias", "linked_max_abs_error",
                    "linked_normalized_mae_iqr", "linked_pearson_r", "linked_spearman_r",
                    "linked_per_year"):
            assert fld in r, f"{fld} missing from {r['industry_id']} {r['component']}"


# --- (8) MoM switch does not use an invalid current-edition lag -------------


def test_mom_switch_month_is_one_month_after_the_level_switch():
    d = _load_v2()
    sw = d["switch_months"]
    assert sw["level"] == "2021-01-01"
    assert sw["mom"] == "2021-02-01", "current edition has no 2020-12, so no native MoM at 2021-01"
    for r in d["results"]:
        sp = r.get("splice")
        if not sp:
            continue
        assert sp["invalid_cross_edition_lag_used"] is False
        # the month at the level switch must take its MoM from the older edition
        assert sp["mom_source_by_month"]["2021-01-01"] == "2016_based_native"
        assert sp["mom_source_by_month"]["2021-02-01"] == "current_native"


# --- (9) YoY switch only when 12 native current-edition months exist --------


def test_yoy_switch_waits_for_twelve_native_current_months():
    d = _load_v2()
    assert d["switch_months"]["yoy"] == "2022-01-01"
    for r in d["results"]:
        sp = r.get("splice")
        if not sp:
            continue
        for month, src in sp["yoy_source_by_month"].items():
            if month < "2022-01-01":
                assert src == "2016_based_native", f"{month} would need a cross-edition 12m lag"
            else:
                assert src == "current_native"


def test_switch_months_are_recorded_separately_per_representation():
    d = _load_v2()
    sw = d["switch_months"]
    assert len({sw["level"], sw["mom"], sw["yoy"]}) == 3, "all three must be distinct"


# --- (10) spliced output has no gaps or duplicates --------------------------


def test_spliced_series_has_no_gaps_or_duplicate_month_keys():
    d = _load_v2()
    for r in d["results"]:
        sp = r.get("splice")
        if not sp:
            continue
        months = sp["level_months"]
        assert len(months) == mod.CRITERIA["splice"]["expected_months"] == 126
        assert len(months) == len(set(months))
        assert sp["level_no_gaps"] is True
        assert sp["level_no_duplicate_keys"] is True
        assert sorted(months) == months


# --- (11) boundary jump is calculated ---------------------------------------


def test_boundary_jump_is_calculated_and_compared_to_ordinary_changes():
    d = _load_v2()
    for r in d["results"]:
        sp = r.get("splice")
        if not sp:
            continue
        for fld in ("boundary_jump", "boundary_jump_unit", "ordinary_abs_change_p99",
                    "boundary_jump_vs_p99_ratio", "boundary_jump_percentile_rank"):
            assert fld in sp
        expected_unit = "percent_growth" if r["component"] == "MPI" else "percentage_points"
        assert sp["boundary_jump_unit"] == expected_unit


def test_boundary_jump_hard_fails_when_it_would_manufacture_a_shock():
    splice = _clean_splice()
    splice["boundary_jump_vs_p99_ratio"] = 5.0
    status, reasons = mod.apply_approval_criteria_v2(
        "MPI", _metrics(), _metrics(), _metrics(), splice, []
    )
    assert status == mod.STATUS_REJECTED
    assert any("manufacture a shock" in r for r in reasons)


# --- (12) version 1 outputs remain preserved --------------------------------


V1_PINNED_SHA256 = {
    "docs/oie_overlap_validation.md":
        "20dc38144bd983764105a2f43a0a0d69c3c985d0cfe48c967d0f216b985f36e4",
    "docs/oie_overlap_validation_output.json":
        "f22809f455a09bf17007c67dc637c77697aea9c3eded700277aa7997f51fa1b5",
    "scripts/validate_oie_overlap.py":
        "3b2745dc8965e020e7ac378addc02753370f09cb2dc591146f8015ebc6d5ba45",
}


def test_version_1_outputs_are_preserved_byte_for_byte():
    """v2 changed nothing in v1 -- checked as content, not as platform bytes.

    One of these three pins was taken from a Windows working tree, where the
    file was CRLF on disk while Git stored LF. The other two carry no CR at all
    and have always matched on both platforms, which is why the difference went
    unnoticed until a Linux run.

    No pin is edited. A path whose recorded bytes do not match must already be
    declared in ``configs/line_ending_provenance.yaml``, its canonical content
    must agree with what that file declares, and the declared representation
    must reproduce the original pin. Anything else is a modification.
    """
    provenance = BP.provenance_entries(ROOT)
    for rel, expected in V1_PINNED_SHA256.items():
        p = ROOT / rel
        assert p.is_file(), f"v1 artifact {rel} is missing — it must be preserved"
        content = p.read_bytes()
        if hashlib.sha256(content).hexdigest() == expected:
            continue
        matched = BP.match_declared_representation(
            content, expected, provenance.get(rel)
        )
        assert matched is not None, f"v1 artifact {rel} was modified by v2 work"
        assert BP.canonical_digest(content) == provenance[rel][
            "canonical_git_blob_content_sha256"], rel


def test_v2_writes_to_separate_files_from_v1():
    assert (ROOT / "docs" / "oie_overlap_validation_output_v2.json").is_file()
    assert (ROOT / "docs" / "oie_overlap_validation_output.json").is_file()
    assert (ROOT / "scripts" / "validate_oie_overlap_v2.py").is_file()
    assert (ROOT / "scripts" / "validate_oie_overlap.py").is_file()


# --- (13) every non-approved pair has diagnostic plots ----------------------


def test_every_non_approved_pair_has_diagnostic_plots_on_disk():
    d = _load_v2()
    non_approved = [
        r for r in d["results"]
        if r["approval_status"] != mod.STATUS_APPROVED and "linked_mean_abs_error" in r
    ]
    assert non_approved, "expected at least one non-approved pair"
    for r in non_approved:
        plots = r.get("diagnostic_plots") or []
        assert plots, f"{r['industry_id']} {r['component']} has no diagnostic plot"
        assert any("diagnostic" in p for p in plots)
        for rel in plots:
            assert (ROOT / rel).is_file(), f"missing plot file {rel}"


# --- (14) status counts equal the machine-readable rows ---------------------


def test_status_counts_match_actual_result_rows():
    d = _load_v2()
    counts = d["status_counts"]
    assert sum(counts.values()) == len(d["results"]) == d["result_row_count"]
    for status, n in counts.items():
        assert n == sum(1 for r in d["results"] if r["approval_status"] == status)
    for r in d["results"]:
        assert r["approval_status"] in mod.ALL_STATUSES


def test_approved_both_equals_intersection_of_component_lists():
    d = _load_v2()
    expected = sorted(
        set(d["approved_by_component"]["MPI"]) & set(d["approved_by_component"]["CapU"])
    )
    assert d["approved_both_components"] == expected


# --- (15) deterministic version 2 output ------------------------------------


def test_v2_output_is_deterministic_across_reruns():
    before = V2_OUTPUT.read_bytes()
    mod.main()
    after = V2_OUTPUT.read_bytes()
    assert before == after, "v2 output changed between identical runs"


def test_error_metrics_are_deterministic():
    months = mod.OVERLAP_MONTHS
    a = np.array([100.0 + (i * 1.3) % 7 for i in range(36)])
    b = np.array([100.0 + (i * 0.9) % 5 for i in range(36)])
    # reference_for_iqr supplied so the normalized fields are finite; comparing
    # dataclasses containing NaN would fail on NaN != NaN regardless of
    # determinism, which would test nothing.
    first = mod.compute_error_metrics(a, b, months, reference_for_iqr=a)
    second = mod.compute_error_metrics(a, b, months, reference_for_iqr=a)
    assert not np.isnan(first.normalized_mae_iqr)
    assert first == second


# --- supporting: statuses, discontinuity handling, aggregation --------------


def test_unexplained_discontinuity_yields_needs_source_review_not_rejected():
    """v1 hard-rejected on any flagged month. v2 must route an unresolved cause
    to Needs source review instead.
    """
    findings = [{"month": "2023-01-01", "cause_resolved": False, "cause": "unresolved"}]
    status, reasons = mod.apply_approval_criteria_v2(
        "MPI", _metrics(), _metrics(), _metrics(), _clean_splice(), findings
    )
    assert status == mod.STATUS_NEEDS_REVIEW
    assert any("unresolved" in r for r in reasons)


def test_resolved_discontinuity_does_not_force_needs_source_review():
    findings = [{"month": "2023-01-01", "cause_resolved": True,
                 "cause": "aggregation_weight_difference"}]
    status, _ = mod.apply_approval_criteria_v2(
        "MPI", _metrics(), _metrics(), _metrics(), _clean_splice(), findings
    )
    assert status == mod.STATUS_APPROVED


def test_gross_level_misfit_is_rejected_even_without_discontinuity():
    """The other half of the v1 defect: persistent large error used to pass."""
    bad = _metrics(normalized_mae_iqr=0.9, mean_abs_error=40.0)
    status, reasons = mod.apply_approval_criteria_v2(
        "MPI", bad, _metrics(), _metrics(), _clean_splice(), []
    )
    assert status == mod.STATUS_REJECTED
    assert any("gross-misfit" in r for r in reasons)


def test_insufficient_evidence_when_too_few_paired_months():
    few = _metrics(n_valid=10)
    status, _ = mod.apply_approval_criteria_v2(
        "MPI", few, _metrics(), _metrics(), _clean_splice(), []
    )
    assert status == mod.STATUS_INSUFFICIENT


def test_aggregation_renormalizes_official_weights_and_never_equal_weights():
    months = mod.OVERLAP_MONTHS
    series = mod.v1.DivisionValueSeries(
        edition_id="toy", component="MPI", file_path="t.xlsx", sha256="x",
        classification_label="TSIC", weights={10: 30.0, 11: 40.0, 12: 30.0},
        values={10: {m: 100.0 for m in months}, 11: {m: 200.0 for m in months},
                12: {m: 999.0 for m in months}},
        dates=months,
    )
    agg, norm = mod.aggregate_over_months(series, [10, 11], months)
    assert sum(norm.values()) == pytest.approx(1.0)
    assert norm[10] == pytest.approx(30.0 / 70.0)
    assert norm[11] == pytest.approx(40.0 / 70.0)
    assert norm[10] != pytest.approx(0.5), "must not fall back to equal weighting"
    assert agg[months[0]] == pytest.approx(30 / 70 * 100.0 + 40 / 70 * 200.0)


def test_aggregation_refuses_to_impute_a_missing_month():
    months = mod.OVERLAP_MONTHS
    series = mod.v1.DivisionValueSeries(
        edition_id="toy", component="MPI", file_path="t.xlsx", sha256="x",
        classification_label="TSIC", weights={10: 100.0},
        values={10: {m: 100.0 for m in months[:-1]}}, dates=months[:-1],
    )
    with pytest.raises(mod.SeriesIncompleteError):
        mod.aggregate_over_months(series, [10], months)


def test_ind03_excluded_and_reported_separately():
    d = _load_v2()
    assert mod.IND03_EXCLUDED_ID not in mod.CANDIDATE_INDUSTRIES
    assert len(mod.CANDIDATE_INDUSTRIES) == 11
    assert d["ind03_excluded"]["decision_made_in_this_task"] is False
    assert len(d["ind03_excluded"]["future_choices"]) == 3


def test_early_overlap_transient_is_diagnostic_only():
    d = _load_v2()
    for r in d["results"]:
        diag = r.get("early_overlap_transient_diagnostic")
        if diag:
            assert diag["gating"] is False
