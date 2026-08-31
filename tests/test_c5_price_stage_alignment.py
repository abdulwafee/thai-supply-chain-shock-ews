"""Task C5 tests — structural decomposition and price-stage source semantics.

The decomposition is an algebraic identity, so most of these tests pin the
things algebra cannot check on its own: that the matrix is the right way round,
that final demand never enters, that an observed zero stays a zero rather than
becoming a null or an indirect effect, and that no source is preferred because
of a model outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from thai_supply_chain_ews.data import cost_channel_source_audit as CSA
from thai_supply_chain_ews.structure import price_stage_alignment as PSA
from thai_supply_chain_ews.structure import structural_path_decomposition as SPD

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "price_stage_source_candidates.yaml").read_text(encoding="utf-8")
)
STRUCTURAL = ROOT / "docs" / "c5_structural_path_audit.json"
SOURCES = ROOT / "docs" / "c5_price_stage_source_audit.json"
C3_MATRIX = ROOT / "docs" / "c3_commodity_exposure_matrix.json"
D4_RESULTS = ROOT / "docs" / "d4_operational_model_results.json"

requires_run = pytest.mark.skipif(not STRUCTURAL.is_file(), reason="C5 has not been run")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _toy():
    """Small column-oriented system with a known answer."""
    a = np.array([
        [0.0, 0.0, 0.2],
        [0.5, 0.0, 0.0],
        [0.0, 0.3, 0.0],
    ])
    t = np.linalg.inv(np.eye(3) - a) - np.eye(3)
    return a, t


# ---------------------------------------------------------------------------
# 1. The identity and the orientation
# ---------------------------------------------------------------------------
def test_identity_holds_on_a_known_system():
    a, t = _toy()
    residual = SPD.assert_identity(a, t)
    assert residual < 1e-12


def test_identity_raises_when_t_is_wrong():
    """Synthetic failure: mediator contributions that cannot reconcile."""
    a, t = _toy()
    with pytest.raises(SPD.DecompositionError):
        SPD.assert_identity(a, t * 1.05)


def test_transposed_a_is_caught_by_the_orientation_check():
    """Synthetic failure: transposed A.

    A transposed matrix still satisfies the Leontief identity, so only a check
    against the source flows can catch it.
    """
    codes = ["1", "2"]
    gross = {"1": 100.0, "2": 200.0}
    # Deliberately asymmetric: a symmetric A would equal its own transpose and
    # the test would prove nothing.
    flows = {("1", "1"): 10.0, ("1", "2"): 40.0, ("2", "1"): 50.0, ("2", "2"): 30.0}

    def z(supplying, producing):
        return flows[(supplying, producing)]

    correct = np.array([[10 / 100, 40 / 200], [50 / 100, 30 / 200]])
    assert not np.allclose(correct, correct.T), "fixture must be asymmetric"
    SPD.assert_column_orientation(correct, codes, z, gross)
    with pytest.raises(SPD.DecompositionError):
        SPD.assert_column_orientation(correct.T, codes, z, gross)


def test_identity_requires_square_matching_shapes():
    with pytest.raises(SPD.DecompositionError):
        SPD.assert_identity(np.zeros((2, 3)), np.zeros((2, 3)))


# ---------------------------------------------------------------------------
# 2. Decomposition arithmetic
# ---------------------------------------------------------------------------
def _decompose_toy(industry_codes=("3",)):
    a, t = _toy()
    codes = ["1", "2", "3"]
    labels = {"1": "commodity", "2": "mediator", "3": "producer"}
    gross = {"1": 100.0, "2": 100.0, "3": 100.0}
    return SPD.decompose_pair(
        a=a, t=t, sector_codes=codes, sector_labels=labels,
        commodity_series_id="toy", commodity_sector_code="1",
        industry_id="IND-X", component_codes=list(industry_codes),
        gross_output=gross, materiality_threshold=0.01,
    )


def test_mediator_contributions_sum_to_indirect():
    result = _decompose_toy()
    total = sum(m.contribution for m in result.mediators)
    assert abs(total - result.indirect_exposure) < 1e-12


def test_direct_plus_indirect_equals_total():
    result = _decompose_toy()
    assert abs(result.direct_exposure + result.indirect_exposure - result.total_exposure) < 1e-12
    assert result.reconciliation_error < 1e-12


def test_cumulative_shares_are_monotone_and_bounded():
    result = _decompose_toy()
    shares = [m.cumulative_share for m in result.mediators]
    assert shares == sorted(shares)
    assert all(s <= 1.0 + 1e-12 for s in shares)


def test_unknown_sector_code_raises():
    """Synthetic failure: an unknown sector code."""
    a, t = _toy()
    with pytest.raises(SPD.DecompositionError):
        SPD.decompose_pair(
            a=a, t=t, sector_codes=["1", "2", "3"], sector_labels={},
            commodity_series_id="toy", commodity_sector_code="999",
            industry_id="IND-X", component_codes=["3"],
            gross_output={"1": 1.0, "2": 1.0, "3": 1.0},
        )


def test_industry_weights_sum_to_one_and_reject_zero_output():
    weights = SPD.industry_weights(["1", "2"], {"1": 30.0, "2": 70.0}, ["1", "2", "3"])
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    assert weights["2"] == pytest.approx(0.7)
    with pytest.raises(SPD.DecompositionError):
        SPD.industry_weights(["1"], {"1": 0.0}, ["1"])


def test_sector_absent_from_matrix_is_dropped_before_normalizing():
    """A component sector outside the coefficient matrix must not get weight."""
    weights = SPD.industry_weights(["1", "179"], {"1": 50.0, "179": 50.0}, ["1", "2"])
    assert set(weights) == {"1"}
    assert weights["1"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. Observed zero stays a zero
# ---------------------------------------------------------------------------
@requires_run
def test_observed_direct_zero_remains_exactly_zero():
    """Synthetic failure guard: direct zero rewritten as missing."""
    audit = _load(STRUCTURAL)
    c3 = {
        (r["industry_id"], r["commodity_series_id"]): r
        for r in _load(C3_MATRIX)["canonical_rows"]
    }
    for row in audit["pair_summary"]:
        reference = c3[(row["industry_id"], row["commodity_series_id"])]
        if reference["direct_exposure"] == 0.0:
            assert row["direct_exposure"] == 0.0
            assert row["direct_exposure"] is not None
            assert row["direct_is_observed_zero"] is True


@requires_run
def test_indirect_is_never_rewritten_as_direct():
    """Synthetic failure guard: indirect exposure promoted to direct."""
    audit = _load(STRUCTURAL)
    c3 = {
        (r["industry_id"], r["commodity_series_id"]): r
        for r in _load(C3_MATRIX)["canonical_rows"]
    }
    for row in audit["pair_summary"]:
        reference = c3[(row["industry_id"], row["commodity_series_id"])]
        assert row["direct_exposure"] == pytest.approx(reference["direct_exposure"], abs=1e-12)
        if row["indirect_exposure"] > 0 and reference["direct_exposure"] == 0.0:
            assert row["direct_exposure"] == 0.0


@requires_run
def test_direct_zero_counts_are_reported():
    summary = _load(STRUCTURAL)["direct_zero_summary"]
    assert summary["pairs_total"] == 48
    assert summary["direct_zero_pairs"] == 18
    assert summary["direct_zero_with_material_indirect"] >= 1
    assert summary["by_commodity"]["brent_crude_usd_bbl"] == 10


# ---------------------------------------------------------------------------
# 4. Reconciliation with C3 and scope exclusions
# ---------------------------------------------------------------------------
@requires_run
def test_reconciles_with_c3_within_tolerance():
    audit = _load(STRUCTURAL)
    assert audit["reconciliation"]["worst_error_vs_c3"] < 1e-12
    assert audit["identity"]["residual_max_abs"] < 1e-12
    assert audit["reconciliation"]["direct_plus_indirect_equals_total"] is True


@requires_run
def test_final_demand_imports_and_value_added_are_excluded():
    """Synthetic failure guard: final-demand leakage."""
    sectors = _load(STRUCTURAL)["sectors"]
    assert sectors["final_demand_included"] is False
    assert sectors["imports_included"] is False
    assert sectors["value_added_included"] is False
    assert sectors["level"] == 179
    assert sectors["excluded_zero_output"] == ["179"]


@requires_run
def test_mediator_rows_reconcile_and_resolve_labels():
    audit = _load(STRUCTURAL)
    by_pair = {}
    for row in audit["mediator_table"]:
        by_pair.setdefault((row["commodity_series_id"], row["industry_id"]), []).append(row)
        assert row["intermediate_sector_label"] != "UNKNOWN"
        assert row["intermediate_sector_code"]
        assert abs(row["gross_output_weight_sum"] - 1.0) < 1e-12
    for rows in by_pair.values():
        ranks = [r["rank"] for r in rows]
        assert ranks == sorted(ranks)
        assert rows[0]["cumulative_share"] == pytest.approx(rows[0]["share_of_indirect"])


@requires_run
def test_decomposition_is_not_called_causal():
    audit = _load(STRUCTURAL)
    assert audit["causal_claim"] is False
    report = (ROOT / "docs" / "c5_structural_path_audit.md").read_text("utf-8")
    assert "not a causal claim" in report


# ---------------------------------------------------------------------------
# 5. Shared aluminum/copper sector protection
# ---------------------------------------------------------------------------
@requires_run
def test_aluminum_and_copper_share_a_sector_and_are_never_summed():
    """Synthetic failure guard: shared exposure counted twice."""
    c3 = _load(C3_MATRIX)
    crosswalk = c3["commodity_crosswalk"]
    assert crosswalk["aluminum_usd_mt"]["io_sector_code"] == "107"
    assert crosswalk["copper_usd_mt"]["io_sector_code"] == "107"
    payload = _load(SOURCES)
    for row in payload["price_stage_alignment"]:
        if row["commodity_series_id"] in {"aluminum_usd_mt", "copper_usd_mt"}:
            assert row["shared_source_sector_warning"]
            assert "never be summed" in row["shared_source_sector_warning"]
            assert row["alignment_status"] == "broad_proxy_with_caution"


@requires_run
def test_no_aggregate_adds_the_duplicated_exposure():
    audit = _load(STRUCTURAL)
    alu = {(r["industry_id"]): r for r in audit["pair_summary"]
           if r["commodity_series_id"] == "aluminum_usd_mt"}
    cop = {(r["industry_id"]): r for r in audit["pair_summary"]
           if r["commodity_series_id"] == "copper_usd_mt"}
    # They are reported separately; no combined non-ferrous row exists.
    assert set(alu) == set(cop)
    ids = {r["commodity_series_id"] for r in audit["pair_summary"]}
    assert not any("non_ferrous" in i or "nonferrous" in i for i in ids)
    assert CONFIG["prohibitions"]["sum_shared_sector_aluminum_copper_exposure"] is False


# ---------------------------------------------------------------------------
# 6. Price-stage classification
# ---------------------------------------------------------------------------
def test_stage_classification_uses_structure_not_accuracy():
    assert PSA.classify_stage(0.5, ["093"]) == "raw_commodity_direct_purchase"
    assert PSA.classify_stage(0.0, ["135"]) == "electricity_purchase"
    assert PSA.classify_stage(0.0, ["093"]) == "refined_energy_purchase"
    assert PSA.classify_stage(0.0, ["140"]) == "transport_or_logistics_purchase"
    assert PSA.classify_stage(0.0, ["086"]) == "processed_material_purchase"
    assert PSA.classify_stage(0.0, []) == "broad_or_unresolved_proxy"


def test_declared_stages_and_statuses_match_the_schema():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "price_stage_candidate.schema.yaml").read_text("utf-8")
    )
    assert set(schema["price_stages"]) == set(PSA.PRICE_STAGES)
    assert set(schema["alignment_statuses"]) == set(PSA.ALIGNMENT_STATUSES)


@requires_run
def test_every_alignment_row_uses_a_declared_status():
    payload = _load(SOURCES)
    for row in payload["price_stage_alignment"]:
        assert row["alignment_status"] in PSA.ALIGNMENT_STATUSES
        assert row["price_stage"] in PSA.PRICE_STAGES
        assert row["evidence"]
        assert row["limitations"]


@requires_run
def test_brent_is_stage_misaligned_where_direct_is_zero():
    payload = _load(SOURCES)
    rows = [r for r in payload["price_stage_alignment"]
            if r["commodity_series_id"] == "brent_crude_usd_bbl"]
    zero_rows = [r for r in rows if r["direct_exposure"] == 0.0]
    assert len(zero_rows) == 10
    for row in zero_rows:
        assert row["alignment_status"] == "stage_misaligned"
        assert row["world_bank_price_represents_purchased_stage"] is False
        assert row["additional_series_could_close_gap"] is True


# ---------------------------------------------------------------------------
# 7. Source audit and the gate
# ---------------------------------------------------------------------------
def test_no_probe_state_means_the_source_is_absent():
    assert "absent" not in " ".join(CSA.PROBE_STATES)
    assert "does_not_exist" not in " ".join(CSA.PROBE_STATES)
    schema = yaml.safe_load(
        (ROOT / "schemas" / "price_stage_candidate.schema.yaml").read_text("utf-8")
    )
    assert schema["absence_may_be_concluded_from_a_probe"] is False


def test_gate_requires_every_criterion():
    candidate = CSA.SourceCandidate(
        candidate_id="X", source_family="X", publisher="P", official_url="u"
    )
    passing = dict.fromkeys(CSA.GATE_CRITERIA, True)
    CSA.apply_recommendation_gate(candidate, passing)
    assert candidate.gate_passed is True

    failing = dict(passing, coverage_adequate_or_limitations_explicit=False)
    CSA.apply_recommendation_gate(candidate, failing)
    assert candidate.gate_passed is False
    assert "coverage_adequate_or_limitations_explicit" in candidate.rejection_reasons


def test_gate_raises_on_a_missing_criterion():
    candidate = CSA.SourceCandidate("X", "X", "P", "u")
    with pytest.raises(CSA.CandidateGateError):
        CSA.apply_recommendation_gate(candidate, {"official_publisher": True})


def test_ranking_refuses_a_candidate_carrying_a_model_outcome():
    """Synthetic failure: a candidate chosen using development MAE."""

    class Contaminated(CSA.SourceCandidate):
        def to_dict(self):
            payload = super().to_dict()
            payload["development_mae"] = 12.3
            return payload

    candidate = Contaminated("X", "X", "P", "u")
    CSA.apply_recommendation_gate(candidate, dict.fromkeys(CSA.GATE_CRITERIA, True))
    with pytest.raises(CSA.CandidateGateError):
        CSA.rank_candidates([candidate], CONFIG["selection_order"])


def test_insufficient_coverage_is_not_promoted_automatically():
    """Synthetic failure: a source with insufficient coverage promoted."""
    candidate = CSA.SourceCandidate("X", "X", "P", "u")
    CSA.apply_recommendation_gate(
        candidate,
        dict.fromkeys(CSA.GATE_CRITERIA, True)
        | {"coverage_adequate_or_limitations_explicit": False},
    )
    ranked = CSA.rank_candidates([candidate], CONFIG["selection_order"])
    assert ranked == []
    assert candidate.recommended_for_c6 is False


def test_retail_price_is_not_described_as_a_producer_price():
    """Synthetic failure: a retail price silently called a producer price."""
    evidence = CONFIG["candidate_evidence"]["EPPO_PETROLEUM"]
    basis = evidence["price_basis"]
    assert "ex_refinery" in basis
    assert "before_excise" in basis
    # the taxes it excludes are named, so the stage cannot be confused
    for token in ("EXCISE TAX", "MUNICIPAL TAX", "OIL FUND", "WHOLESALE"):
        assert token in evidence["taxes_and_margins"]


def test_exchange_rate_is_not_mapped_to_a_commodity_sector():
    family = next(f for f in CONFIG["source_families"] if f["family_id"] == "BOT_FX")
    assert family["is_io_commodity_sector_price"] is False
    assert family["audit_scope"] == "transmission_factor_only"
    evidence = CONFIG["candidate_evidence"]["BOT_FX"]
    assert evidence["gate"]["maps_to_purchased_intermediate_sector"] is False


@requires_run
def test_exactly_one_family_is_recommended():
    payload = _load(SOURCES)
    recommended = [p for p in payload["probes"] if p["recommended_for_c6"]]
    assert len(recommended) == 1
    assert recommended[0]["gate_passed"] is True
    assert payload["recommended_family"] == recommended[0]["candidate_id"]


@requires_run
def test_recommendation_is_ingestion_approval_only():
    payload = _load(SOURCES)
    meaning = payload["recommendation_meaning"]
    assert meaning["source_selected_for_c6_audit"] is True
    assert meaning["feature_semantics_approved"] is False
    assert meaning["model_feature_approved"] is False
    assert meaning["ingested_into_production"] is False


@requires_run
def test_selection_provenance_declares_no_target_outcomes():
    payload = _load(SOURCES)
    provenance = payload["selection_provenance"]
    assert provenance["selection_used_target_outcomes"] is False
    assert provenance["d4_metrics_used_for_source_ranking"] is False
    assert provenance["locked_test_accessed"] is False


@requires_run
def test_blocked_candidates_record_reasons_not_absence():
    payload = _load(SOURCES)
    for probe in payload["probes"]:
        if probe["gate_passed"]:
            continue
        assert probe["rejection_reasons"]
        assert probe["probe_detail"].get("absence_concluded", False) is False


@requires_run
def test_candidate_ranking_is_deterministic():
    payload = _load(SOURCES)
    first = list(payload["eligible_candidates"])
    assert first == sorted(set(first), key=first.index)
    assert len(first) == len(set(first))


# ---------------------------------------------------------------------------
# 8. Upstream decisions preserved; nothing modelled
# ---------------------------------------------------------------------------
def test_preserved_decisions_are_declared():
    preserved = CONFIG["preserved_decisions"]
    for key in (
        "b3_targets_or_calibrator_changed", "d3_contract_changed",
        "split_periods_changed", "d3_benchmarks_changed",
        "d4_results_or_status_changed", "c2_archived_first_release_changed",
        "c3_coefficients_changed", "c3r1_eligibility_changed",
        "c4_variants_changed", "promote_total_requirement_because_of_d4",
        "promote_publication_lag_1m_because_of_h1_point_estimate",
        "hybrid_exposure_chosen_by_development_mae",
    ):
        assert preserved[key] is False, key
    assert preserved["registered_primary_exposure"] == "direct_exposure"
    assert preserved["total_requirement_role"] == "structural_sensitivity_only"


@requires_run
def test_d4_no_predictor_state_is_benchmark_passthrough():
    state = _load(STRUCTURAL)["d4_no_predictor_state"]
    fields = state["c5_equivalent_fields"]
    assert fields["model_fitted"] is False
    assert fields["prediction_source"] == "benchmark_passthrough_no_eligible_predictor"
    assert fields["residual_correction"] == 0.0
    assert state["described_as_fitted_ridge_with_intercept"] is False
    assert state["d4_recomputed"] is False


@requires_run
def test_d4_results_are_not_recomputed():
    """C5 reads D4 provenance; it must never regenerate D4 numbers."""
    state = _load(STRUCTURAL)["d4_no_predictor_state"]
    assert state["d4_recomputed"] is False
    d4 = _load(D4_RESULTS)
    assert d4["prediction_counts"]["total"] == 1080
    for horizon in ("1", "3"):
        assert d4["evaluation"][horizon]["mae_evidence_status"] == (
            "incremental_signal_not_supported"
        )


def test_c5_imports_no_model_or_evaluation_module():
    import inspect
    for module in (SPD, PSA, CSA):
        source = inspect.getsource(module)
        for forbidden in ("modeling", "residual_ridge", "operational_walk_forward",
                          "walk_forward", "metrics", "bootstrap"):
            assert forbidden not in source, f"{module.__name__} imports {forbidden}"
    runner = (ROOT / "scripts" / "audit_c5_price_stage_alignment.py").read_text("utf-8")
    for forbidden in ("fit_ridge", "run_operational_walk_forward", "train", "predict_baseline"):
        assert forbidden not in runner


def test_no_feature_matrix_or_target_join_is_created():
    runner = (ROOT / "scripts" / "audit_c5_price_stage_alignment.py").read_text("utf-8")
    for forbidden in ("load_b3_artifacts", "target_raw_value", "observed_score",
                      "industry_month", "to_parquet"):
        assert forbidden not in runner
    assert CONFIG["prohibitions"]["create_industry_month_feature_matrix"] is False
    assert CONFIG["prohibitions"]["join_to_mpi_targets"] is False


def test_locked_test_is_untouched():
    runner = (ROOT / "scripts" / "audit_c5_price_stage_alignment.py").read_text("utf-8")
    assert "locked_test_origins" not in runner
    assert CONFIG["selection_provenance"]["locked_test_accessed"] is False


@requires_run
def test_json_ordering_is_deterministic():
    audit = _load(STRUCTURAL)
    rows = audit["mediator_table"]
    keys = [(r["commodity_series_id"], r["industry_id"], r["rank"]) for r in rows]
    assert keys == sorted(keys)
    pairs = [(r["commodity_series_id"], r["industry_id"]) for r in audit["pair_summary"]]
    assert pairs == sorted(pairs)
