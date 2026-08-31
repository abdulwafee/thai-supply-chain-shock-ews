"""Task C9 tests — sector-093 exposure and industry-conditioned fuel-oil features.

Two errors would pass every downstream check if they got through here.

The first is **using the wrong coefficient**. C3's sector-031 crude exposure and
C9's sector-093 refinery exposure are both plausible numbers about petroleum;
relabelling one as the other, transposing the matrix, letting a final-demand
column into ``Z`` or weighting the component sectors equally each produces a
coefficient that looks entirely ordinary. Every one of those is constructed here
and required to raise.

The second is **letting an absence become a measurement**. IND-04's direction is
unresolved, not zero. A missing April 2026 price is absent, not zero, even where
exposure is zero. An observed zero exposure *is* zero — but only when the price
exists. The status precedence keeps those three apart and the synthetic failures
try each collapse in turn.

The rest guards the phase boundary: Phase A must not be able to see a C8 value,
and eligibility must be frozen and re-checked before and after the values load.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.features import fuel_oil_conditioned_lineage as CL
from thai_supply_chain_ews.features import fuel_oil_industry_conditioning as FC
from thai_supply_chain_ews.features import fuel_oil_issue_snapshots as SN
from thai_supply_chain_ews.structure import fuel_oil_proxy_fitness as PF
from thai_supply_chain_ews.structure import sector093_exposure as EX

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "fuel_oil_industry_conditioning.yaml").read_text(
        encoding="utf-8")
)
PHASE_A = ROOT / "docs" / "c9_sector093_exposure_decision.json"
AUDIT = ROOT / "docs" / "c9_fuel_oil_conditioning_audit.json"
C8_AUDIT = ROOT / "docs" / "c8_eppo_transformation_audit.json"
C8_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"
CONDITIONED = ROOT / "data" / "features" / "c9_fuel_oil_conditioned.parquet"
SNAPSHOT = ROOT / "data" / "features" / "c9_fuel_oil_development_snapshot.parquet"

CH600, CH1500 = "eppo_fo600_channel", "eppo_fo1500_channel"
V600, V1500 = "fo600_direct_sector093", "fo1500_direct_sector093"

requires_run = pytest.mark.skipif(not AUDIT.is_file(), reason="C9 has not been run")
requires_parquet = pytest.mark.skipif(
    not CONDITIONED.is_file(), reason="the C9 conditioned table is not present"
)


def _phase_a():
    return json.loads(PHASE_A.read_text(encoding="utf-8"))


def _audit():
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def _conditioned():
    import pandas as pd

    frame = pd.read_parquet(CONDITIONED)
    rows = frame.to_dict("records")
    for row in rows:
        for key in ("conditioned_value", "source_feature_value"):
            value = row[key]
            row[key] = None if value is None or pd.isna(value) else float(value)
        for key in ("source_required_input_months", "source_missing_input_months"):
            raw = row[key]
            row[key] = [] if raw is None else [str(x) for x in raw]
        if row["direction_multiplier"] is not None and pd.isna(
            row["direction_multiplier"]
        ):
            row["direction_multiplier"] = None
    return rows


# ===========================================================================
# Fixtures: a synthetic I/O table, so a formula test never needs the workbook.
# ===========================================================================
class _Table:
    """A minimal stand-in for the parsed NESDC workbook."""

    def __init__(self, flows, gross_output, sector_codes=None):
        self._flows = flows
        self.gross_output = gross_output
        self.sector_codes = list(sector_codes or gross_output)

    def z(self, row_code, col_code, measure="purchaser"):
        return self._flows.get((row_code, col_code), 0.0)


class _Crosswalk:
    def __init__(self, industry_id, codes, name="Test industry"):
        self.industry_id = industry_id
        self.industry_name = name
        self.io_sector_codes = tuple(codes)


def _simple_table():
    # Two component sectors of very different size, so equal weighting and
    # output weighting cannot coincide by accident.
    return _Table(
        flows={("093", "A"): 10.0, ("093", "B"): 1.0},
        gross_output={"A": 1000.0, "B": 100.0, "093": 500.0},
        sector_codes=["A", "B", "093"],
    )


def _exposure(industry_id="IND-XX", codes=("A", "B")):
    return EX.industry_exposure(_simple_table(), _Crosswalk(industry_id, codes))


def _decision(**overrides):
    base = {
        "industry_id": "IND-01", "industry_name": "Food", "channel_id": CH600,
        "variant_id": V600, "io_sector_code": "093",
        "io_sector_label": "Petroleum refineries",
        "direct_exposure": 0.01, "exposure_weighted_mean_form": 0.01,
        "exposure_summed_flow_form": 0.01,
        "exposure_reconciliation_residual": 0.0, "observed_zero": False,
        "industry_contains_the_producer_sector": False,
        "component_sector_codes": ["A"], "gross_output_weights": {"A": 1.0},
        "proxy_fit": "broad_proxy_use_with_caution", "confidence": "medium",
        "product_specific_evidence_available": False, "proxy_reason": "basket",
        "direction_channel": "cost_pressure", "direction_multiplier": 1,
        "direction_interpretation_level": "cost",
        "direction_interpretation_volatility": "disruption_magnitude_nonnegative",
        "eligible": True, "exclusion_reason": None, "quality_flag": "ok",
        "valuation_basis_alignment":
            "partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price",
        "structural_source_checksum": "s" * 64, "target_outcomes_used": False,
        "phase_a_decision_checksum": "p" * 64,
    }
    base.update(overrides)
    return base


def _source_row(**overrides):
    base = {
        "channel_id": CH600, "reference_month": "2024-03",
        "transformation_id": "price_level", "feature_value": 20.0,
        "transformation_status": "available_numeric",
        "required_input_months": ["2024-03"], "missing_input_months": [],
        "policy_available_month": "2024-05",
        "transformation_lineage_checksum": "c" * 64,
    }
    base.update(overrides)
    return base


def _source_rows(**overrides):
    """One C8 row per transformation, because the grid demands the full set."""
    from thai_supply_chain_ews.features.eppo_fuel_oil_transformations import (
        TRANSFORMATION_IDS,
    )

    return [
        _source_row(transformation_id=name, **overrides)
        for name in TRANSFORMATION_IDS
    ]


def _grid(decisions, source_rows, months=("2024-03",), structural_month="2020-03"):
    records = {}

    def lineage(row, decision, source):
        structural = CL.StructuralLineage(
            io_sector_code=decision["io_sector_code"],
            io_sector_label=decision["io_sector_label"],
            nesdc_workbook_sha256="n" * 64,
            industry_id=decision["industry_id"],
            crosswalk_version="test",
            component_sector_codes=list(decision["component_sector_codes"]),
            gross_output_weights=dict(decision["gross_output_weights"]),
            direct_exposure=decision["direct_exposure"],
            exposure_weighted_mean_form=decision["exposure_weighted_mean_form"],
            exposure_summed_flow_form=decision["exposure_summed_flow_form"],
            proxy_fit=decision["proxy_fit"],
            proxy_confidence=decision["confidence"],
            direction_channel=decision["direction_channel"],
            direction_multiplier=decision["direction_multiplier"],
            structural_available_month=structural_month,
            structural_availability_evidence="test",
            phase_a_decision_checksum=decision["phase_a_decision_checksum"],
        )
        record = CL.conditioned_lineage_record(
            row, structural, "x" * 64, FC.CONDITIONING_FORMULA_VERSION
        )
        records[(row.variant_id, row.industry_id, row.reference_month,
                 row.transformation_id)] = record
        _ = source
        return CL.conditioned_lineage_checksum(record)

    indexed = {(d["industry_id"], d["channel_id"]): d for d in decisions}
    rows = FC.build_conditioned_grid(
        source_rows, indexed, list(months), structural_month, lineage
    )
    return rows, records


def _cell(rows, industry_id, transformation_id="price_level", variant_id=V600,
          reference_month="2024-03"):
    return next(
        r for r in rows
        if r.industry_id == industry_id and r.transformation_id == transformation_id
        and r.variant_id == variant_id and r.reference_month == reference_month
    )


# ===========================================================================
# 1. Upstream invariants
# ===========================================================================
@requires_run
def test_all_upstream_invariants_reproduced():
    invariants = _audit()["upstream_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 26
    for name, check in invariants["checks"].items():
        assert check["reproduced"] is True, name


@requires_run
def test_c8_and_c3_headline_facts_match_the_brief():
    checks = _audit()["upstream_invariants"]["checks"]
    expected = {
        "c8_source_transformation_rows": 650,
        "c8_finite_rows": 598,
        "c8_null_rows": 52,
        "c8_transformation_definitions": 5,
        "c8_policy_lag_months": 2,
        "c8_lag_is_measured": False,
        "c8_latest_vintage_used": True,
        "c8_point_in_time_supported": False,
        "c8_shared_price_stage_group": "io_sector_093_fuel_oil",
        "c8_hsd_absent": True,
        "c8_fo600_ready": True,
        "c8_fo1500_ready": True,
        "c3_valid_io_sectors": 179,
        "c3_coefficient_measure": "purchaser",
        "c3_valuation_price_basis": "purchasers_prices",
        "c3_import_treatment": "import_inclusive",
        "c3_production_industries": 12,
        "c3_no_duplicate_sector_assignment": True,
        "c3_structural_available_by": "2020-03-31",
        "c3_target_outcomes_used_in_crosswalk": False,
        "sector_093_present_exactly_once": 1,
        "sector_093_official_label": "Petroleum refineries",
    }
    for name, value in expected.items():
        assert checks[name]["actual"] == value, name
    assert checks["c8_rows_per_channel"]["actual"] == [325]
    assert checks["c8_finite_per_channel"]["actual"] == [299]
    assert checks["c8_null_per_channel"]["actual"] == [26]


def test_inherited_status_and_restrictions_are_preserved():
    status = CONFIG["inherited_status"]
    assert status["eppo_fo600_channel"][
        "source_transformations_ready_for_structural_conditioning"] is True
    assert status["eppo_fo1500_channel"][
        "source_transformations_ready_for_structural_conditioning"] is True
    assert status["eppo_hsd"]["authorized"] is False
    for key, value in CONFIG["inherited_restrictions"].items():
        assert value is False, key
    for key, value in CONFIG["provenance"].items():
        assert value is False, key
    for key, value in CONFIG["preserved_decisions"].items():
        assert value is False, key


# ===========================================================================
# 2. The phase boundary
# ===========================================================================
def test_phase_a_cannot_read_a_c8_numeric_value():
    for payload in (
        {"feature_value": 1.0},
        [{"industry_id": "IND-01", "monthly_value_strict": 20.0}],
        {"rows": [{"nested": {"conditioned_value": 3.0}}]},
        {"price_level": 12.0},
    ):
        with pytest.raises(PF.PhaseAError, match="without reading C8 values"):
            PF.assert_no_numeric_source_values(payload)
    PF.assert_no_numeric_source_values(
        [_decision()], "structural decision table"
    )


def test_phase_a_module_does_not_import_the_c8_feature_modules():
    source = (ROOT / "src" / "thai_supply_chain_ews" / "structure"
              / "fuel_oil_proxy_fitness.py").read_text(encoding="utf-8")
    modules = _imported_modules(source)
    assert "eppo_fuel_oil_transformations" not in modules
    assert "features" not in modules
    exposure = (ROOT / "src" / "thai_supply_chain_ews" / "structure"
                / "sector093_exposure.py").read_text(encoding="utf-8")
    assert "features" not in _imported_modules(exposure)


def test_eligibility_freezes_before_phase_b():
    rows = [_decision(), _decision(channel_id=CH1500, variant_id=V1500)]
    checksum = PF.phase_a_checksum(rows)
    assert PF.assert_phase_a_frozen(rows, checksum) == checksum
    changed = [dict(row) for row in rows]
    changed[0]["eligible"] = False
    changed[0]["exposure_row_checksum"] = PF.exposure_row_checksum(changed[0])
    with pytest.raises(PF.PhaseAError, match="may not change after C8"):
        PF.assert_phase_a_frozen(changed, checksum)


@requires_run
def test_the_run_recorded_that_phase_a_saw_no_values():
    phase_a = _phase_a()
    for key in ("c8_numeric_values_read", "mpi_values_read", "targets_read",
                "predictions_read", "evaluation_metrics_read"):
        assert phase_a[key] is False, key
    audit = _audit()
    assert audit["phase_a_reasserted_before_loading_values"] is True
    assert audit["phase_a_reasserted_after_conditioning"] is True
    assert audit["phase_a_decision_checksum"] == (
        phase_a["structural_decision_checksum"]
    )


@requires_run
def test_the_frozen_checksum_re_derives_from_the_written_table():
    phase_a = _phase_a()
    assert PF.phase_a_checksum(phase_a["decisions"]) == (
        phase_a["structural_decision_checksum"]
    )
    for row in phase_a["decisions"]:
        assert PF.exposure_row_checksum(row) == row["exposure_row_checksum"]
        assert row["phase_a_decision_checksum"] == (
            phase_a["structural_decision_checksum"]
        )


# ===========================================================================
# 3. Sector identity and exposure arithmetic
# ===========================================================================
def test_sector_093_is_required_and_031_is_refused():
    EX.assert_sector_is_093("093", "Petroleum refineries")
    with pytest.raises(EX.ExposureError, match="crude"):
        EX.assert_sector_is_093("031")
    with pytest.raises(EX.ExposureError, match="conditions on sector 093 only"):
        EX.assert_sector_is_093("086")
    with pytest.raises(EX.ExposureError, match="label"):
        EX.assert_sector_is_093("093", "Petroleum and natural gas")


def test_direct_coefficient_is_column_oriented():
    table = _simple_table()
    assert EX.direct_coefficient(table, "A") == pytest.approx(10.0 / 1000.0)
    assert EX.direct_coefficient(table, "B") == pytest.approx(1.0 / 100.0)
    # A transposed read would divide by the ROW sector's output instead.
    assert EX.direct_coefficient(table, "A") != pytest.approx(10.0 / 500.0)


def test_both_aggregation_forms_agree():
    exposure = _exposure()
    weighted = (1000 / 1100) * 0.01 + (100 / 1100) * 0.01
    exact = (10.0 + 1.0) / 1100.0
    assert exposure.weighted_mean_form == pytest.approx(weighted)
    assert exposure.summed_flow_form == pytest.approx(exact)
    assert exposure.reconciliation_residual <= EX.RECONCILIATION_TOLERANCE
    assert exposure.direct_exposure == pytest.approx(exact)


def test_gross_output_weighting_is_not_equal_weighting():
    table = _Table(
        flows={("093", "A"): 100.0, ("093", "B"): 0.0},
        gross_output={"A": 1000.0, "B": 100.0, "093": 500.0},
        sector_codes=["A", "B", "093"],
    )
    exposure = EX.industry_exposure(table, _Crosswalk("IND-XX", ("A", "B")))
    assert exposure.direct_exposure == pytest.approx(100.0 / 1100.0)
    equal_weighted = 0.5 * (100.0 / 1000.0) + 0.5 * 0.0
    assert exposure.direct_exposure != pytest.approx(equal_weighted)
    assert exposure.weight_sum == pytest.approx(1.0)


def test_final_demand_and_value_added_are_refused():
    with pytest.raises(EX.ExposureError, match="non-sector codes"):
        EX.assert_no_final_demand_or_value_added(["A", "301"], ["A", "B"])
    with pytest.raises(EX.ExposureError, match="non-sector codes"):
        EX.assert_no_final_demand_or_value_added(["190"], ["A", "B"])
    EX.assert_no_final_demand_or_value_added(["A", "B"], ["A", "B", "093"])


def test_zero_output_and_negative_coefficients_raise():
    table = _Table(flows={}, gross_output={"A": 0.0, "093": 1.0},
                   sector_codes=["A", "093"])
    with pytest.raises(EX.ExposureError, match="undefined"):
        EX.direct_coefficient(table, "A")
    negative = _Table(flows={("093", "A"): -1.0}, gross_output={"A": 10.0, "093": 1.0},
                      sector_codes=["A", "093"])
    with pytest.raises(EX.ExposureError, match="negative"):
        EX.direct_coefficient(negative, "A")


def test_no_total_requirement_anywhere_in_c9():
    for path in (
        ROOT / "src" / "thai_supply_chain_ews" / "structure" / "sector093_exposure.py",
        ROOT / "src" / "thai_supply_chain_ews" / "structure"
        / "fuel_oil_proxy_fitness.py",
        ROOT / "src" / "thai_supply_chain_ews" / "features"
        / "fuel_oil_industry_conditioning.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "leontief_inverse" not in source, path.name
        assert "total_requirement" not in source.replace(
            "total_requirement_used", ""
        ).replace("total_requirement_exposure_used", ""), path.name
    assert CONFIG["conditioning"]["total_requirement_exposure_used"] is False
    assert "total_requirement_exposure" in CONFIG["exposure"]["prohibited"]
    assert "total_requirement_T_equals_L_minus_I" in CONFIG["exposure"]["prohibited"]


@requires_run
def test_reported_exposures_cover_twelve_industries():
    phase_a = _phase_a()
    summary = phase_a["exposure"]["summary"]
    assert summary["industries"] == 12
    assert summary["io_sector_code"] == "093"
    assert summary["io_sector_label"] == "Petroleum refineries"
    assert summary["max_reconciliation_residual"] <= 1e-12
    assert summary["normalised_across_industries"] is False
    assert summary["total_requirement_used"] is False
    industries = {row["industry_id"] for row in phase_a["decisions"]}
    assert len(industries) == 12
    for row in phase_a["decisions"]:
        assert row["direct_exposure"] >= 0
        assert math.isfinite(row["direct_exposure"])
        assert row["exposure_reconciliation_residual"] <= 1e-12
        assert abs(sum(row["gross_output_weights"].values()) - 1.0) < 1e-9


@requires_run
def test_observed_zero_count_is_reported_and_distinct_from_unresolved():
    summary = _phase_a()["exposure"]["summary"]
    assert "observed_zero_count" in summary
    assert "unresolved_count" in summary
    assert summary["unresolved_count"] == 0
    zeros = [r for r in _phase_a()["decisions"] if r["observed_zero"]]
    assert len(zeros) == summary["observed_zero_count"] * 2 or not zeros
    for row in zeros:
        assert row["quality_flag"] == "observed_zero_direct_exposure"
        assert row["direct_exposure"] == 0.0


# ===========================================================================
# 4. Valuation mismatch
# ===========================================================================
def test_valuation_mismatch_is_documented():
    valuation = CONFIG["valuation"]
    assert valuation["eppo_price_stage"] == "ex_refinery"
    assert valuation["io_valuation_basis"] == "purchasers_prices"
    assert valuation["io_import_treatment"] == "import_inclusive"
    assert valuation["valuation_basis_alignment"] == (
        "partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price"
    )
    assert valuation["structural_interaction_only"] is True
    assert valuation["monetary_cost_measure"] is False
    assert valuation["elasticity"] is False
    assert valuation["causal_effect"] is False
    for component in ("excise_tax", "municipal_tax", "oil_fund",
                      "conservation_fund", "vat", "marketing_margin",
                      "retail_margin"):
        assert component in valuation["eppo_excluded_components"], component


def test_a_monetary_cost_claim_raises():
    FC.assert_valuation_claim_permitted(
        "a structural interaction between an ex-refinery price and an I/O coefficient"
    )
    for claim in ("baht cost per unit of output", "the monetary cost of fuel",
                  "an elasticity of output to price", "the pass-through rate",
                  "a causal effect on production", "a forecast coefficient"):
        with pytest.raises(FC.ConditioningError, match="structural"):
            FC.assert_valuation_claim_permitted(claim)


# ===========================================================================
# 5. Proxy fitness
# ===========================================================================
def test_fuel_oil_use_is_not_inferred_from_a_positive_coefficient():
    with pytest.raises(PF.PhaseAError, match="not purchase of FO 600"):
        PF.assert_not_inferred_from_coefficient(0.05, evidence="")
    PF.assert_not_inferred_from_coefficient(0.05, evidence="a documented survey")
    PF.assert_not_inferred_from_coefficient(0.0, evidence="")


def test_default_confidence_is_never_high_without_product_evidence():
    fitness = PF.decide_proxy_fitness(_exposure(), product_specific_evidence=None)
    assert fitness["proxy_fit"] == "broad_proxy_use_with_caution"
    assert fitness["confidence"] != "high"
    assert fitness["product_specific_evidence_available"] is False
    assert "fuel oil" in fitness["reason"]


def test_product_specific_evidence_permits_a_stronger_status():
    fitness = PF.decide_proxy_fitness(
        _exposure(), product_specific_evidence="official fuel-oil consumption table"
    )
    assert fitness["proxy_fit"] == "fit_for_structural_use"
    assert fitness["confidence"] == "medium"
    assert fitness["product_specific_evidence_available"] is True


def test_the_official_basket_is_recorded_and_names_nine_products():
    assert len(PF.SECTOR_093_PRODUCT_BASKET) == 9
    assert "fuel oil" in PF.SECTOR_093_PRODUCT_BASKET
    assert "diesel" in PF.SECTOR_093_PRODUCT_BASKET
    assert set(CONFIG["proxy_fitness"]["sector_093_official_basket"]) == set(
        PF.SECTOR_093_PRODUCT_BASKET
    )
    assert CONFIG["proxy_fitness"][
        "fuel_oil_use_inferred_from_a_positive_coefficient"] is False
    assert CONFIG["proxy_fitness"][
        "default_confidence_high_without_product_specific_evidence"] is False


def test_proxy_fitness_reads_no_target_outcome():
    source = (ROOT / "src" / "thai_supply_chain_ews" / "structure"
              / "fuel_oil_proxy_fitness.py").read_text(encoding="utf-8")
    assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES)


@requires_run
def test_reported_proxy_fitness_by_industry_and_channel():
    decisions = _phase_a()["decisions"]
    assert len(decisions) == 24
    for row in decisions:
        assert row["proxy_fit"] in PF.PROXY_FIT_STATUSES
        assert row["confidence"] in PF.CONFIDENCE_LEVELS
        assert row["target_outcomes_used"] is False
        if not row["product_specific_evidence_available"]:
            assert row["confidence"] != "high", row["industry_id"]
    # Both channels get identical structural decisions for one industry.
    by_industry = {}
    for row in decisions:
        by_industry.setdefault(row["industry_id"], []).append(row)
    for industry_id, rows in by_industry.items():
        assert len(rows) == 2, industry_id
        assert rows[0]["direct_exposure"] == rows[1]["direct_exposure"]
        assert rows[0]["proxy_fit"] == rows[1]["proxy_fit"]
        assert rows[0]["eligible"] == rows[1]["eligible"]


# ===========================================================================
# 6. Direction and eligibility
# ===========================================================================
def test_a_consuming_industry_gets_cost_pressure():
    direction = PF.decide_direction(_exposure())
    assert direction["direction_channel"] == "cost_pressure"
    assert direction["direction_multiplier"] == 1
    assert direction["direction_interpretation_volatility"] == (
        "disruption_magnitude_nonnegative"
    )


def test_an_industry_containing_the_producer_sector_is_mixed():
    exposure = _exposure(codes=("A", "093"))
    assert exposure.industry_contains_the_producer_sector is True
    direction = PF.decide_direction(exposure)
    assert direction["direction_channel"] == "mixed_or_ambiguous"
    assert direction["direction_multiplier"] is None


def test_mixed_direction_may_not_be_forced_to_plus_one():
    exposure = _exposure(codes=("A", "093"))
    PF.assert_direction_not_forced(exposure, PF.decide_direction(exposure))
    with pytest.raises(PF.PhaseAError, match="net sign nobody established"):
        PF.assert_direction_not_forced(
            exposure, {"direction_channel": "cost_pressure", "direction_multiplier": 1}
        )


def test_volatility_is_a_disruption_magnitude_not_a_price_increase():
    direction = PF.decide_direction(_exposure())
    assert direction["direction_interpretation_volatility"] == (
        "disruption_magnitude_nonnegative"
    )
    assert "price" not in direction["direction_interpretation_volatility"]
    assert CONFIG["direction"]["volatility_called_a_price_increase"] is False


def test_eligibility_gate_and_the_three_distinct_states():
    exposure = _exposure()
    fitness = PF.decide_proxy_fitness(exposure)
    direction = PF.decide_direction(exposure)
    assert PF.decide_eligibility(exposure, fitness, direction) == {
        "eligible": True, "exclusion_reason": None, "quality_flag": "ok",
    }
    mixed = _exposure(codes=("A", "093"))
    verdict = PF.decide_eligibility(
        mixed, PF.decide_proxy_fitness(mixed), PF.decide_direction(mixed)
    )
    assert verdict["eligible"] is False
    assert verdict["exclusion_reason"] == (
        "direction_ambiguous_industry_contains_producer_sector"
    )


def test_observed_zero_stays_eligible_with_its_own_flag():
    table = _Table(flows={}, gross_output={"A": 1000.0, "093": 500.0},
                   sector_codes=["A", "093"])
    exposure = EX.industry_exposure(table, _Crosswalk("IND-ZZ", ("A",)))
    assert exposure.observed_zero is True
    fitness = PF.decide_proxy_fitness(exposure)
    direction = PF.decide_direction(exposure)
    verdict = PF.decide_eligibility(exposure, fitness, direction)
    assert verdict["eligible"] is True
    assert verdict["quality_flag"] == "observed_zero_direct_exposure"
    assert verdict["exclusion_reason"] is None


@requires_run
def test_ind_04_is_ineligible_and_retained():
    phase_a = _phase_a()
    assert phase_a["ineligible_industries"] == ["IND-04"]
    assert phase_a["eligible_industries_per_channel"] == 11
    assert phase_a["ineligible_industries_per_channel"] == 1
    ind04 = [r for r in phase_a["decisions"] if r["industry_id"] == "IND-04"]
    assert len(ind04) == 2
    for row in ind04:
        assert row["industry_contains_the_producer_sector"] is True
        assert row["direction_channel"] == "mixed_or_ambiguous"
        assert row["direction_multiplier"] is None
        assert row["eligible"] is False
        assert row["exclusion_reason"] == (
            "direction_ambiguous_industry_contains_producer_sector"
        )
    assert CONFIG["eligibility"][
        "ineligible_pairs_deleted_from_the_audit_table"] is False


# ===========================================================================
# 7. The conditioned grid
# ===========================================================================
def test_conditioning_formula():
    assert FC.condition_value(20.0, 0.05, 1) == pytest.approx(1.0)
    assert FC.condition_value(-3.0, 0.02, 1) == pytest.approx(-0.06)
    with pytest.raises(FC.ConditioningError, match="multiplier is null"):
        FC.condition_value(20.0, 0.05, None)
    with pytest.raises(FC.ConditioningError, match="negative or non-finite"):
        FC.condition_value(20.0, -0.05, 1)


def test_units_are_transformation_specific():
    assert FC.CONDITIONED_UNITS["price_level"] == "baht_per_litre_x_io_coefficient"
    for name in ("log_change_1m_pct", "log_change_3m_pct", "log_change_12m_pct"):
        assert FC.CONDITIONED_UNITS[name] == (
            "percentage_point_log_change_x_io_coefficient"
        )
    assert FC.CONDITIONED_UNITS["realized_volatility_3m_pct"] == (
        "percentage_point_log_change_volatility_x_io_coefficient"
    )
    assert CONFIG["conditioning"]["not_a_currency_cost"] is True
    assert CONFIG["conditioning"]["not_an_elasticity"] is True
    assert CONFIG["conditioning"]["not_a_forecast_coefficient"] is True


def test_source_null_propagates_null_even_when_exposure_is_zero():
    decisions = [_decision(industry_id="IND-Z", direct_exposure=0.0,
                           observed_zero=True,
                           quality_flag="observed_zero_direct_exposure")]
    rows, _ = _grid(decisions, _source_rows(
        feature_value=None, transformation_status="current_month_source_gap",
        missing_input_months=["2024-03"],
    ))
    cell = _cell(rows, "IND-Z")
    assert cell.conditioned_value is None
    assert cell.conditioned_status == "source_current_month_gap"


def test_zero_exposure_produces_zero_only_when_the_source_value_is_present():
    decisions = [_decision(industry_id="IND-Z", direct_exposure=0.0,
                           observed_zero=True,
                           quality_flag="observed_zero_direct_exposure")]
    rows, _ = _grid(decisions, _source_rows())
    cell = _cell(rows, "IND-Z")
    assert cell.conditioned_value == 0.0
    assert cell.conditioned_status == "zero_due_to_observed_zero_exposure"


def test_an_ineligible_pair_is_null_not_zero():
    decisions = [_decision(
        industry_id="IND-04", eligible=False, direction_multiplier=None,
        direction_channel="mixed_or_ambiguous",
        exclusion_reason="direction_ambiguous_industry_contains_producer_sector",
    )]
    rows, _ = _grid(decisions, _source_rows())
    cell = _cell(rows, "IND-04")
    assert cell.conditioned_value is None
    assert cell.conditioned_status == "not_generated_due_to_direction_ambiguity"


def test_status_precedence_puts_ineligibility_first():
    assert list(FC.STATUS_PRECEDENCE) == CONFIG["status_precedence"]
    decisions = [_decision(
        industry_id="IND-04", eligible=False, direction_multiplier=None,
        direction_channel="mixed_or_ambiguous",
        exclusion_reason="direction_ambiguous_industry_contains_producer_sector",
    )]
    rows, _ = _grid(decisions, _source_rows(
        feature_value=None, transformation_status="insufficient_feature_history",
        missing_input_months=["2023-03"],
    ))
    # Both an ineligibility and a source gap apply; ineligibility wins.
    assert _cell(rows, "IND-04").conditioned_status == (
        "not_generated_due_to_direction_ambiguity"
    )


def test_null_to_zero_collapses_raise():
    FC.assert_null_not_converted_to_zero({
        "conditioned_status": "available_nonzero", "conditioned_value": 1.0,
    })
    with pytest.raises(FC.ConditioningError, match="structure is unresolved"):
        FC.assert_null_not_converted_to_zero({
            "conditioned_status": "not_generated_due_to_direction_ambiguity",
            "conditioned_value": 0.0,
        })
    with pytest.raises(FC.ConditioningError, match="still absent"):
        FC.assert_null_not_converted_to_zero({
            "conditioned_status": "source_current_month_gap",
            "conditioned_value": 0.0,
        })
    with pytest.raises(FC.ConditioningError, match="must produce exactly 0"):
        FC.assert_null_not_converted_to_zero({
            "conditioned_status": "zero_due_to_observed_zero_exposure",
            "conditioned_value": 1.0,
        })


@requires_run
def test_the_grid_is_exactly_7800_rows_with_reconciled_counts():
    counts = _audit()["counts"]
    assert counts["counts_reconciled"] is True
    assert counts["expected"]["full_grid_rows"] == 7800
    assert counts["observed"]["full_grid_rows"] == 7800
    assert counts["expected"]["source_numeric_rows"] == 598 * 11
    assert counts["expected"]["source_gap_rows"] == 52 * 11
    assert counts["expected"]["ineligible_rows"] == 650 * 1
    assert counts["expected"] == counts["observed"]
    assert counts["expected_counts_edited_after_conditioning"] is False


@requires_run
def test_expected_counts_were_derived_after_the_phase_a_freeze():
    phase_a = _phase_a()
    expected = phase_a["expected_phase_b_counts"]
    assert expected["full_grid_rows"] == 7800
    assert expected["source_numeric_rows"] == 6578
    assert expected["source_gap_rows"] == 572
    assert expected["ineligible_rows"] == 650
    assert CONFIG["expected_counts"]["derived_after_phase_a_freeze"] is True
    assert CONFIG["expected_counts"]["edited_after_conditioning_begins"] is False


@requires_parquet
def test_every_conditioned_row_is_consistent_with_its_status():
    rows = _conditioned()
    assert len(rows) == 7800
    keys = [(r["variant_id"], r["industry_id"], r["reference_month"],
             r["transformation_id"]) for r in rows]
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys)
    for row in rows:
        assert row["conditioned_status"] in FC.CONDITIONED_STATUSES
        if row["conditioned_value"] is None:
            assert row["conditioned_status"] != "available_nonzero"
        else:
            assert row["eligible"] is True
            assert row["source_missing_input_months"] == []


@requires_parquet
def test_conditioned_values_reconstruct_from_source_and_exposure():
    checked = 0
    for row in _conditioned():
        if row["conditioned_status"] != "available_nonzero":
            continue
        expected = (
            row["source_feature_value"] * row["direct_exposure"]
            * row["direction_multiplier"]
        )
        assert row["conditioned_value"] == pytest.approx(expected, rel=1e-12)
        checked += 1
    assert checked == 6578


# ===========================================================================
# 8. Channel separation
# ===========================================================================
def test_the_two_variants_are_never_combined():
    assert FC.assert_no_fuel_oil_combination([V600], "level") == V600
    for operation in ("sum", "average", "combined fuel oil index", "pca"):
        with pytest.raises(FC.ConditioningError, match="mutually exclusive"):
            FC.assert_no_fuel_oil_combination([V600, V1500], operation)
    with pytest.raises(FC.ConditioningError, match="unknown conditioned variant"):
        FC.assert_no_fuel_oil_combination(["hsd_direct_sector093"], "level")


def test_variant_restrictions_are_declared():
    restrictions = CONFIG["variant_restrictions"]
    for key in ("additive_aggregation_allowed", "simple_average_allowed",
                "automatic_composite_index_allowed",
                "simultaneous_model_entry_approved",
                "outcome_based_variant_selection_allowed"):
        assert restrictions[key] is False, key
    for construction in ("added_conditioned_features", "averaged_conditioned_features",
                         "combined_fuel_oil_index", "pca",
                         "two_independent_exposure_measurements_claim",
                         "primary_variant_chosen_from_target_performance"):
        assert construction in restrictions["prohibited_constructions"], construction
    assert CONFIG["shared_structural_exposure_group"] == "io_sector_093"


@requires_parquet
def test_both_variants_carry_the_same_exposure_and_stay_separate():
    rows = _conditioned()
    assert {r["variant_id"] for r in rows} == {V600, V1500}
    by_key = {}
    for row in rows:
        by_key.setdefault(
            (row["industry_id"], row["reference_month"], row["transformation_id"]), {}
        )[row["variant_id"]] = row
    sample = list(by_key.values())[:200]
    for pair in sample:
        assert len(pair) == 2
        assert pair[V600]["direct_exposure"] == pair[V1500]["direct_exposure"]
        assert pair[V600]["shared_structural_exposure_group"] == "io_sector_093"
    for row in rows:
        assert bool(row["additive_aggregation_allowed"]) is False
        assert bool(row["simultaneous_model_entry_approved"]) is False


# ===========================================================================
# 9. Availability
# ===========================================================================
def test_conditioned_availability_is_the_later_of_the_two():
    assert FC.conditioned_policy_available_month("2024-05", "2020-03") == "2024-05"
    assert FC.conditioned_policy_available_month("2019-01", "2020-03") == "2020-03"
    with pytest.raises(FC.ConditioningError):
        FC.conditioned_policy_available_month("", "2020-03")


def test_structural_availability_is_not_backdated_to_the_reference_year():
    availability = CONFIG["availability"]
    assert str(availability["structural_available_by"]) == "2020-03-31"
    assert availability["structural_reference_year"] == 2015
    assert availability["structural_available_month"] == "2020-03"
    assert availability["backdated_to_reference_year"] is False
    assert availability["download_timestamp_used"] is False
    assert FC.conditioned_policy_available_month("2015-01", "2020-03") == "2020-03"


@requires_parquet
def test_every_row_preserves_the_availability_contract():
    for row in _conditioned():
        assert row["source_available_as_of"] is None
        assert row["availability_basis"] == (
            "conservative_policy_not_historical_measurement"
        )
        assert bool(row["latest_vintage_used"]) is True
        assert bool(row["point_in_time_supported"]) is False
        assert bool(row["fully_real_time_backtest"]) is False
        assert row["structural_available_month"] == "2020-03"
        assert row["conditioned_policy_available_month"] == max(
            row["source_policy_available_month"], row["structural_available_month"]
        )


@requires_run
def test_the_source_policy_dominates_every_row():
    availability = _audit()["availability"]
    assert availability["violations"] == 0
    assert availability["rows_checked"] == 7800
    assert availability["source_policy_dominates_rows"] == 7800
    assert availability["source_available_as_of_null_rows"] == 7800


# ===========================================================================
# 10. Lineage
# ===========================================================================
def test_lineage_carries_both_chains():
    rows, records = _grid([_decision()], _source_rows())
    record = records[(V600, "IND-01", "2024-03", "price_level")]
    for field in CL.SOURCE_CHAIN_FIELDS:
        assert field in record["source_chain"], field
    for field in CL.STRUCTURAL_CHAIN_FIELDS:
        assert field in record["structural_chain"], field
    assert record["structural_chain"]["phase_a_decision_checksum"]
    assert record["source_chain"]["source_transformation_lineage_checksum"]
    assert rows[0].conditioned_lineage_checksum


def test_null_and_ineligible_rows_carry_complete_lineage():
    decisions = [
        _decision(industry_id="IND-04", eligible=False, direction_multiplier=None,
                  direction_channel="mixed_or_ambiguous",
                  exclusion_reason=(
                      "direction_ambiguous_industry_contains_producer_sector")),
        _decision(industry_id="IND-01"),
    ]
    rows, records = _grid(decisions, _source_rows(
        feature_value=None, transformation_status="input_window_source_gap",
        missing_input_months=["2024-02"],
        required_input_months=["2024-02", "2024-03"],
    ))
    for row in rows:
        assert row.conditioned_value is None
        assert row.conditioned_lineage_checksum
        record = records[(row.variant_id, row.industry_id, row.reference_month,
                          row.transformation_id)]
        assert record["structural_chain"]["phase_a_decision_checksum"]
        assert record["conditioned_status"] != "available_nonzero"
    ineligible = _cell(rows, "IND-04")
    gapped = _cell(rows, "IND-01")
    assert (ineligible.conditioned_lineage_checksum
            != gapped.conditioned_lineage_checksum)


def test_lineage_refuses_a_value_on_an_ineligible_pair():
    rows, _ = _grid([_decision()], _source_rows())
    row = rows[0]
    row.eligible = False
    structural = CL.StructuralLineage(
        io_sector_code="093", io_sector_label="Petroleum refineries",
        nesdc_workbook_sha256="n" * 64, industry_id="IND-01",
        crosswalk_version="test", phase_a_decision_checksum="p" * 64,
    )
    with pytest.raises(CL.ConditionedLineageError, match="ineligible pair"):
        CL.conditioned_lineage_record(row, structural, "x" * 64, "v1")


def test_lineage_requires_the_frozen_phase_a_checksum():
    rows, _ = _grid([_decision()], _source_rows())
    structural = CL.StructuralLineage(
        io_sector_code="093", io_sector_label="Petroleum refineries",
        nesdc_workbook_sha256="n" * 64, industry_id="IND-01",
        crosswalk_version="test", phase_a_decision_checksum=None,
    )
    with pytest.raises(CL.ConditionedLineageError, match="frozen Phase-A"):
        CL.conditioned_lineage_record(rows[0], structural, "x" * 64, "v1")


def test_lineage_is_deterministic_and_content_sensitive():
    first, _ = _grid([_decision()], _source_rows())
    second, _ = _grid([_decision()], _source_rows())
    assert (first[0].conditioned_lineage_checksum
            == second[0].conditioned_lineage_checksum)
    other, _ = _grid([_decision(direct_exposure=0.02)], _source_rows())
    assert (first[0].conditioned_lineage_checksum
            != other[0].conditioned_lineage_checksum)


@requires_run
def test_reported_lineage_covers_every_row():
    lineage = _audit()["lineage"]
    assert lineage["rows_with_a_checksum"] == 7800
    assert lineage["distinct_checksums"] == 7800
    assert lineage["null_rows_with_complete_lineage"] == 1222
    assert lineage["lineage_version"] == CL.CONDITIONED_LINEAGE_VERSION


# ===========================================================================
# 11. Development snapshot
# ===========================================================================
def test_latest_permitted_reference_month_under_lag_two():
    assert SN.latest_permitted_reference_month("2024-01") == "2023-11"
    assert SN.latest_permitted_reference_month("2025-03") == "2025-01"


@requires_run
def test_the_development_snapshot_is_exactly_1800_cells():
    snapshot = _audit()["development_snapshot"]
    assert snapshot["issue_months"] == 15
    assert snapshot["variants"] == 2
    assert snapshot["industries"] == 12
    assert snapshot["transformations"] == 5
    assert snapshot["cells"] == 1800
    assert snapshot["issue_month_start"] == "2024-01"
    assert snapshot["issue_month_end"] == "2025-03"
    assert snapshot["targets_read"] is False
    assert snapshot["channels_combined_in_one_model_ready_row"] is False
    assert sum(snapshot["state_counts"].values()) == 1800


@requires_run
def test_snapshot_states_keep_ineligible_and_zero_apart():
    states = _audit()["development_snapshot"]["state_counts"]
    assert set(states) <= set(SN.SNAPSHOT_CELL_STATES)
    assert states.get("masked_ineligible", 0) == 15 * 2 * 1 * 5
    assert states.get("numeric", 0) == 15 * 2 * 11 * 5


@pytest.mark.skipif(not SNAPSHOT.is_file(), reason="snapshot parquet absent")
def test_snapshot_cells_carry_their_mask_and_lineage():
    import pandas as pd

    frame = pd.read_parquet(SNAPSHOT)
    assert len(frame) == 1800
    assert set(frame["cell_state"]) <= set(SN.SNAPSHOT_CELL_STATES)
    masked = frame[frame["cell_state"] == "masked_ineligible"]
    assert masked["value"].isna().all()
    assert masked["masked"].astype(bool).all()
    assert masked["mask_reason"].notna().all()
    numeric = frame[frame["cell_state"] == "numeric"]
    assert numeric["value"].notna().all()
    assert frame["conditioned_lineage_checksum"].notna().all()
    assert set(frame["variant_id"]) == {V600, V1500}


@requires_run
def test_purge_and_locked_coverage_comes_from_key_ranges_only():
    coverage = _audit()["issue_key_coverage"]
    assert coverage["target_values_read"] is False
    assert coverage["model_predictions_read"] is False
    assert coverage["locked_test_outcomes_read"] is False
    assert coverage["development"][V600]["materialised"] is True
    assert coverage["purge"][V600]["materialised"] is False
    assert coverage["locked_test"][V600]["materialised"] is False
    assert coverage["purge"][V600]["issue_months"] == 3
    assert coverage["locked_test"][V600]["issue_months"] == 10
    assert coverage["locked_test"][V600]["reference_month_range"] == [
        "2025-05", "2026-02"
    ]


# ===========================================================================
# 12. Isolation and authorization
# ===========================================================================
FORBIDDEN_IMPORT_MODULES = {
    "modeling", "evaluation", "targets", "build_panel", "sklearn", "joblib",
    "statsmodels", "commodity_exposure",
}


def _imported_modules(source: str) -> set:
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules.add(base)
            modules.update(f"{base}.{alias.name}".strip(".") for alias in node.names)
    return {segment for module in modules for segment in module.split(".")}


def test_c9_modules_import_no_target_evaluation_or_model_code():
    paths = [
        ROOT / "src" / "thai_supply_chain_ews" / "structure" / "sector093_exposure.py",
        ROOT / "src" / "thai_supply_chain_ews" / "structure"
        / "fuel_oil_proxy_fitness.py",
        ROOT / "src" / "thai_supply_chain_ews" / "features"
        / "fuel_oil_industry_conditioning.py",
        ROOT / "src" / "thai_supply_chain_ews" / "features"
        / "fuel_oil_conditioned_lineage.py",
        ROOT / "src" / "thai_supply_chain_ews" / "features"
        / "fuel_oil_issue_snapshots.py",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES), path.name


def test_the_runner_touches_no_target_or_locked_test_artifact():
    source = (ROOT / "scripts" / "run_c9_fuel_oil_conditioning.py").read_text(
        encoding="utf-8")
    assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES)
    for fragment in ("industry_month_panel", "targets_table", "forecast_target",
                     "production_stress", "d1_development_predictions",
                     "d3_operational_predictions",
                     "d4_operational_model_predictions", "b4_walk_forward",
                     "locked_test_predictions", "c3_commodity_exposure.parquet",
                     "c4_wide_primary"):
        assert fragment not in source, fragment


@requires_run
def test_authorization_after_c9_is_bounded():
    authorization = _audit()["authorization_after_c9"]
    assert authorization["industry_conditioned_features_created"] is True
    assert authorization["feature_semantics_approved"] is False
    assert authorization["model_feature_approved"] is False
    assert authorization["target_join_authorized"] is False
    assert authorization["modeling_authorized"] is False
    assert authorization["locked_test_evaluation_authorized"] is False
    readiness = authorization["ready_for_development_only_assembly"]
    assert set(readiness) == {V600, V1500}
    for key, value in _audit()["provenance"].items():
        assert value is False, key
    assert _audit()["conditioned_table"]["model_feature_approved_rows"] == 0


@requires_parquet
def test_the_table_has_no_target_or_model_column():
    rows = _conditioned()
    for column in rows[0]:
        name = column.lower()
        for fragment in ("mpi", "target", "prediction", "residual", "stress",
                         "total_requirement"):
            assert fragment not in name, column


@requires_run
def test_upstream_artifacts_are_unchanged():
    c8 = json.loads(C8_AUDIT.read_text(encoding="utf-8"))
    assert c8["counts"]["totals"]["feature_grid_rows"] == 650
    assert c8["counts"]["totals"]["finite_feature_rows"] == 598
    assert _audit()["conditioned_table"]["output"] != (
        "data/features/c8_eppo_fuel_oil_transformations.parquet"
    )
    assert C8_PARQUET.is_file()


# ===========================================================================
# 13. Synthetic failures. Each must raise explicitly.
# ===========================================================================
def test_synthetic_brent_sector_031_relabelled_as_093():
    with pytest.raises(EX.ExposureError, match="factories buy crude"):
        EX.assert_sector_is_093("031")
    table = _simple_table()
    with pytest.raises(EX.ExposureError):
        EX.direct_coefficient(table, "A", sector_code="031")


def test_synthetic_transposed_coefficient_matrix():
    # A transposed read divides by the ROW sector's output. Build the transposed
    # flow and require the two to differ.
    table = _simple_table()
    correct = EX.direct_coefficient(table, "A")
    transposed = table.z("093", "A") / table.gross_output["093"]
    assert correct != pytest.approx(transposed)
    assert correct == pytest.approx(10.0 / 1000.0)


def test_synthetic_final_demand_column_included():
    with pytest.raises(EX.ExposureError, match="Final-demand columns"):
        EX.assert_no_final_demand_or_value_added(["A", "305"], ["A", "B"])
    crosswalk = _Crosswalk("IND-XX", ("A", "305"))
    with pytest.raises(EX.ExposureError):
        EX.industry_exposure(_simple_table(), crosswalk)


def test_synthetic_equal_industry_weighting():
    table = _Table(
        flows={("093", "A"): 100.0, ("093", "B"): 0.0},
        gross_output={"A": 1000.0, "B": 100.0, "093": 500.0},
        sector_codes=["A", "B", "093"],
    )
    exposure = EX.industry_exposure(table, _Crosswalk("IND-XX", ("A", "B")))
    equal = 0.5 * (100.0 / 1000.0) + 0.5 * 0.0
    assert exposure.direct_exposure != pytest.approx(equal)
    weights = {c.io_sector_code: c.output_weight for c in exposure.contributions}
    assert weights["A"] != pytest.approx(0.5)


def test_synthetic_eligibility_changed_after_values_are_loaded():
    rows = [_decision(), _decision(channel_id=CH1500, variant_id=V1500)]
    frozen = PF.phase_a_checksum(rows)
    tampered = [dict(r) for r in rows]
    tampered[0]["eligible"] = False
    tampered[0]["exclusion_reason"] = "proxy_not_fit_for_product_specific_use"
    tampered[0]["exposure_row_checksum"] = PF.exposure_row_checksum(tampered[0])
    with pytest.raises(PF.PhaseAError, match="may not change after C8"):
        PF.assert_phase_a_frozen(tampered, frozen)


def test_synthetic_ind_04_forced_to_cost_pressure():
    exposure = _exposure(codes=("A", "093"))
    with pytest.raises(PF.PhaseAError, match="net sign nobody established"):
        PF.assert_direction_not_forced(
            exposure,
            {"direction_channel": "cost_pressure", "direction_multiplier": 1},
        )


def test_synthetic_broad_exposure_called_fuel_oil_specific():
    with pytest.raises(PF.PhaseAError, match="refinery-products sector"):
        PF.assert_not_inferred_from_coefficient(0.0642, evidence="")


def test_synthetic_purchasers_price_coefficient_called_ex_refinery_cost():
    with pytest.raises(FC.ConditioningError, match="purchasers"):
        FC.assert_valuation_claim_permitted(
            "the ex-refinery baht cost per unit of output for this industry"
        )


def test_synthetic_total_requirement_exposure_used():
    assert CONFIG["conditioning"]["total_requirement_exposure_used"] is False
    module = (ROOT / "src" / "thai_supply_chain_ews" / "structure"
              / "sector093_exposure.py").read_text(encoding="utf-8")
    assert "leontief" not in module.lower()
    assert "L - I" not in module
    assert "total_requirement" in CONFIG["exposure"]["prohibited"][3]


def test_synthetic_ineligible_pair_converted_to_zero():
    with pytest.raises(FC.ConditioningError, match="not that the exposure is zero"):
        FC.assert_null_not_converted_to_zero({
            "variant_id": V600, "industry_id": "IND-04",
            "reference_month": "2024-03", "transformation_id": "price_level",
            "conditioned_status": "not_generated_due_to_direction_ambiguity",
            "conditioned_value": 0.0,
        })


def test_synthetic_source_null_multiplied_into_zero():
    with pytest.raises(FC.ConditioningError, match="zero exposure included"):
        FC.assert_null_not_converted_to_zero({
            "variant_id": V600, "industry_id": "IND-01",
            "reference_month": "2026-04", "transformation_id": "price_level",
            "conditioned_status": "source_current_month_gap",
            "conditioned_value": 0.0,
        })


def test_synthetic_both_channels_combined():
    with pytest.raises(FC.ConditioningError, match="double-counts one coefficient"):
        FC.assert_no_fuel_oil_combination([V600, V1500], "combined fuel oil index")
    with pytest.raises(FC.ConditioningError):
        SN.assert_single_variant_per_row([V600, V1500], "one model-ready row")


def test_synthetic_outcome_used_to_select_a_variant():
    assert CONFIG["variant_restrictions"][
        "outcome_based_variant_selection_allowed"] is False
    assert CONFIG["inherited_restrictions"][
        "outcome_based_channel_selection_allowed"] is False
    with pytest.raises(FC.ConditioningError, match="mutually exclusive"):
        FC.assert_no_fuel_oil_combination(
            [V600, V1500], "keep whichever variant has the lower development MAE"
        )


def test_synthetic_target_joined_in_c9():
    with pytest.raises(PF.PhaseAError, match="without reading C8 values"):
        PF.assert_no_numeric_source_values(
            {"industry_id": "IND-01", "mpi_target": 101.2, "feature_value": 3.0}
        )
    for key, value in CONFIG["provenance"].items():
        assert value is False, key
    runner = (ROOT / "scripts" / "run_c9_fuel_oil_conditioning.py").read_text(
        encoding="utf-8")
    assert "industry_month_panel" not in runner
    assert "forecast_target" not in runner
