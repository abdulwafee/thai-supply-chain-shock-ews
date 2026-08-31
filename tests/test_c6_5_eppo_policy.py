"""Task C6.5 tests — the EPPO latest-vintage policy and availability contract.

The whole risk in this decision is that a conservative assumption starts being
read as a measurement, or that "we could not find it" starts being read as "it
does not exist". Most of these tests exist to make either drift fail loudly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.data import eppo_latest_vintage_policy as POLICY

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "eppo_latest_vintage_policy.yaml").read_text(encoding="utf-8")
)
DECISION = ROOT / "docs" / "c6_5_eppo_latest_vintage_decision.json"
requires_run = pytest.mark.skipif(not DECISION.is_file(), reason="C6.5 has not been run")


def _decision():
    return json.loads(DECISION.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. C6 invariants reproduce
# ---------------------------------------------------------------------------
@requires_run
def test_all_c6_invariants_reproduced():
    invariants = _decision()["c6_invariants"]
    assert invariants["all_reproduced"] is True
    for name, entry in invariants["checks"].items():
        assert entry["reproduced"] is True, name


@requires_run
@pytest.mark.parametrize("name,expected", [
    ("discovered_media_documents", 5233),
    ("distinct_effective_dates", 4976),
    ("retrieved_documents", 256),
    ("validated_documents", 254),
    ("parity_months", 65),
    ("operational_months", 53),
    ("parity_document_days", 1315),
    ("operational_document_days", 1076),
    ("canonical_partial_rows", 722),
    ("independent_captures", 43),
    ("capture_overlap_with_validated", 0),
    ("verified_available_as_of", 0),
    ("single_vintage_only", 707),
    ("duplicate_document", 15),
    ("same_date_revised_value", 0),
    ("hsd_missing_days_january_2024", 22),
])
def test_named_c6_invariant(name, expected):
    checks = _decision()["c6_invariants"]["checks"]
    assert checks[name]["actual"] == expected


@requires_run
def test_validated_count_is_never_inflated_to_the_document_day_count():
    """Synthetic failure: 254 validated described as 1,315 validated."""
    levels = _decision()["ingestion_levels"]
    assert levels["audited_sample_documents"] == 254
    assert levels["discovered_document_days_parity_window"] == 1315
    assert levels["audited_sample_documents"] != levels["discovered_document_days_parity_window"]
    assert "audit sample" in levels["note"].lower()
    text = (ROOT / "docs" / "c6_5_eppo_latest_vintage_decision.md").read_text("utf-8")
    assert "1,315 validated" not in text
    assert "1315 validated" not in text


# ---------------------------------------------------------------------------
# 2. Evidence-boundary wording
# ---------------------------------------------------------------------------
def test_evidence_boundary_fields_are_bounded():
    boundaries = CONFIG["evidence_boundaries"]
    assert boundaries["legacy_archive_status"] == (
        "tested_legacy_urls_no_longer_expose_original_archive"
    )
    assert boundaries["historical_timing_status"] == (
        "not_reconstructable_from_sources_inspected_in_c6"
    )
    assert boundaries["monthly_presence_coverage"] == "complete"
    assert boundaries["complete_daily_document_validation"] is False
    assert boundaries["point_in_time_values_supported"] is False
    assert boundaries["absence_from_inspected_mechanisms_is_not_proof_of_universal_absence"] is True


def test_search_failure_is_not_proof_of_nonexistence():
    """Synthetic failure guard: inspected-source limits written as impossibility."""
    statement = CONFIG["evidence_boundaries"]["statement"]
    assert "not proof" in statement
    assert "never exercised" in statement or "not exercised" in statement


@pytest.mark.parametrize("relative", [
    "docs/data_source_inventory.md",
    "docs/c6_5_eppo_latest_vintage_decision.md",
    "README.md",
])
def test_no_document_claims_universal_impossibility(relative):
    """The claim must not be ASSERTED. Quoting it as superseded is required."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    for line in text.splitlines():
        # a struck-through or explicitly-superseded line is quoting, not claiming
        if line.lstrip().startswith(("* ~~", "~~", "* \"", "- \"")):
            continue
        for forbidden in ("legacy archive gone", "no longer exists",
                          "can never be verified", "never be verified"):
            assert forbidden not in line, f"{relative} asserts {forbidden!r}: {line[:80]}"


@requires_run
def test_superseded_wording_is_listed():
    superseded = _decision()["evidence_boundaries"]["superseded_wording"]
    assert "the legacy archive no longer exists" in superseded
    assert "historical timing can never be verified" in superseded
    assert any("65/65" in s for s in superseded)


# ---------------------------------------------------------------------------
# 3. Ingestion levels stay distinct
# ---------------------------------------------------------------------------
@requires_run
def test_monthly_presence_and_daily_validation_are_distinct():
    """Synthetic failure: 65/65 presence presented as complete daily validation."""
    levels = _decision()["ingestion_levels"]
    assert levels["monthly_document_presence_verified"] is True
    assert levels["complete_daily_inventory_discovered"] is True
    assert levels["complete_daily_documents_downloaded"] is False
    assert levels["complete_daily_documents_validated"] is False
    assert levels["monthly_aggregation_contract_approved"] is False


@requires_run
def test_partial_audit_table_is_not_called_a_production_series():
    text = (ROOT / "docs" / "c6_5_eppo_latest_vintage_decision.md").read_text("utf-8")
    assert "partial audit table" in text.lower()
    assert _decision()["ingestion_levels"]["monthly_aggregation_contract_approved"] is False


# ---------------------------------------------------------------------------
# 4. Capture interpretation
# ---------------------------------------------------------------------------
def test_capture_never_proves_a_first_release_date():
    """Synthetic failure: an upper-bound capture reported as first release."""
    assessment = POLICY.classify_capture(
        "2022-06-06", "2022-06-08", source_identity_validated=True
    )
    assert assessment.proves_first_release_date is False
    assert assessment.evidence_class == "contemporaneous_capture_upper_bound"
    assert assessment.provides_upper_bound_only is True


def test_retrospective_capture_is_not_timing_evidence():
    assessment = POLICY.classify_capture(
        "2020-06-25", "2021-07-27", source_identity_validated=True
    )
    assert assessment.evidence_class == "retrospective_capture_not_timing_evidence"
    assert assessment.provides_upper_bound_only is False
    assert assessment.delay_days == 397


def test_unvalidated_capture_identity_is_recorded_as_such():
    assessment = POLICY.classify_capture("2022-06-06", "2022-06-08")
    assert assessment.evidence_class == "capture_identity_unverified"
    assert assessment.source_identity_validated is False
    assert assessment.provides_upper_bound_only is False


def test_capture_before_effective_date_is_unresolved():
    assessment = POLICY.classify_capture(
        "2022-06-06", "2022-06-01", source_identity_validated=True
    )
    assert assessment.evidence_class == "unresolved"


def test_delay_statistics_come_from_upper_bounds_only():
    good = POLICY.classify_capture("2022-06-06", "2022-06-08", source_identity_validated=True)
    late = POLICY.classify_capture("2020-06-25", "2021-07-27", source_identity_validated=True)
    summary = POLICY.summarize_captures([good, late])
    assert summary["usable_upper_bounds"] == 1
    assert summary["upper_bound_delay_days"]["n"] == 1
    assert summary["minimum_verified_publication_lag_months"] is None
    assert summary["any_capture_proves_first_release"] is False


@requires_run
def test_reported_captures_are_classified_and_prove_nothing():
    capture = _decision()["capture_audit"]
    assert capture["captures_total"] == 43
    assert capture["any_capture_proves_first_release"] is False
    assert capture["capture_date_is_first_publication_date"] is False
    assert capture["minimum_verified_publication_lag_months"] is None
    for name in capture["evidence_class_counts"]:
        assert name in POLICY.CAPTURE_EVIDENCE_CLASSES
    assert capture["window_is_a_convention_not_a_measurement"] is True


# ---------------------------------------------------------------------------
# 5. Measured versus policy lag
# ---------------------------------------------------------------------------
@requires_run
def test_minimum_verified_lag_stays_null():
    """Synthetic failure: lag 2 reported as empirically measured."""
    policy = _decision()["policy"]
    assert policy["minimum_verified_publication_lag_months"] is None
    assert policy["operational_policy_lag_months"] == 2
    assert policy["operational_lag_is_measured"] is False
    assert policy["operational_lag_basis"] == "conservative_project_policy"


@requires_run
def test_markdown_states_no_delay_was_measured():
    text = (ROOT / "docs" / "c6_5_eppo_latest_vintage_decision.md").read_text("utf-8")
    assert "No publication delay was measured" in text
    assert "not an observation about EPPO" in text


# ---------------------------------------------------------------------------
# 6. The reference-month rule
# ---------------------------------------------------------------------------
def test_latest_permitted_reference_month_is_t_minus_two():
    assert POLICY.permitted_reference_month("2024-01") == "2023-11"
    assert POLICY.permitted_reference_month("2026-05") == "2026-03"


@pytest.mark.parametrize("reference", ["2023-12", "2024-01", "2024-02"])
def test_reference_month_later_than_t_minus_two_is_rejected(reference):
    with pytest.raises(POLICY.PolicyError):
        POLICY.assert_reference_month_permitted(reference, "2024-01")


def test_permitted_reference_month_is_accepted():
    POLICY.assert_reference_month_permitted("2023-11", "2024-01")
    POLICY.assert_reference_month_permitted("2023-06", "2024-01")


def test_lag_zero_and_lag_one_are_rejected_by_policy():
    assert CONFIG["policy"]["same_month_use_permitted"] is False
    assert CONFIG["policy"]["publication_lag_1m_use_permitted"] is False
    assert CONFIG["policy"]["operational_lag_2m_use_permitted"] is True
    # under the 2-month policy, the month a lag-0 or lag-1 rule would admit fails
    with pytest.raises(POLICY.PolicyError):
        POLICY.assert_reference_month_permitted("2024-01", "2024-01")
    with pytest.raises(POLICY.PolicyError):
        POLICY.assert_reference_month_permitted("2023-12", "2024-01")


def test_policy_available_month_adds_the_policy_lag():
    assert POLICY.policy_available_month("2022-01") == "2022-03"
    assert POLICY.policy_available_month("2023-12") == "2024-02"


# ---------------------------------------------------------------------------
# 7. Availability fields never collapse
# ---------------------------------------------------------------------------
def test_policy_date_cannot_populate_source_available_as_of():
    """Synthetic failure: a policy date written into source_available_as_of."""
    availability = POLICY.observation_availability("2022-01")
    assert availability.source_available_as_of is None
    assert availability.policy_available_month == "2022-03"
    assert availability.availability_basis == (
        "conservative_policy_not_historical_measurement"
    )
    assert availability.historical_timing_verified is False
    with pytest.raises(POLICY.PolicyError):
        POLICY.observation_availability(
            "2022-01", source_available_as_of="2022-03-01",
            historical_timing_verified=False,
        )


def test_verified_timing_may_carry_a_source_date():
    availability = POLICY.observation_availability(
        "2022-01", source_available_as_of="2022-02-04", historical_timing_verified=True
    )
    assert availability.source_available_as_of == "2022-02-04"
    assert availability.availability_basis == "verified_historical_measurement"


@requires_run
def test_reported_availability_examples_keep_source_date_null():
    for example in _decision()["availability_examples"]:
        assert example["source_available_as_of"] is None
        assert example["historical_timing_verified"] is False
        assert example["availability_basis"] == (
            "conservative_policy_not_historical_measurement"
        )


# ---------------------------------------------------------------------------
# 8. Vintage status
# ---------------------------------------------------------------------------
@requires_run
def test_latest_vintage_true_point_in_time_false():
    """Synthetic failure: a latest-vintage result described as point-in-time."""
    policy = _decision()["policy"]
    assert policy["latest_vintage_values_used"] is True
    assert policy["point_in_time_values_supported"] is False
    assert policy["fully_real_time_backtest"] is False
    assert policy["historical_release_timing_verified"] is False


@requires_run
def test_exploratory_only_never_locked_test_eligible():
    """Synthetic failure: an exploratory source marked locked-test eligible."""
    policy = _decision()["policy"]
    assert policy["eligible_for_exploratory_development"] is True
    assert policy["eligible_for_confirmatory_claims"] is False
    assert policy["eligible_for_locked_test"] is False
    assert policy["feature_semantics_approved"] is False
    assert policy["model_feature_approved"] is False


# ---------------------------------------------------------------------------
# 9. Series decisions
# ---------------------------------------------------------------------------
@requires_run
@pytest.mark.parametrize("series,label", [
    ("eppo_ex_refinery_fo600_2s", "FO 600 (1) 2%S"),
    ("eppo_ex_refinery_fo1500_2s", "FO 1500 (2) 2%S"),
])
def test_fuel_oil_series_are_eligible_with_exact_labels(series, label):
    entry = _decision()["series_decisions"][series]
    assert entry["exact_label"] == label
    assert entry["unit"] == "BAHT/LITRE"
    assert entry["eligible_for_c7_full_archive_ingestion"] is True
    assert entry["semantic_status"] == "stable_in_audited_window"
    assert entry["timing_basis"] == "latest_vintage_policy_lag_2m"
    assert entry["feature_semantics_approved"] is False


@requires_run
def test_hsd_is_conditional_and_the_january_gap_stands():
    """Synthetic failure: H-DIESEL B7 substituted for H-DIESEL."""
    entry = _decision()["series_decisions"]["eppo_ex_refinery_hsd"]
    assert entry["eligible_for_c7_full_archive_ingestion"] == "conditional"
    assert entry["semantic_status"] == "january_2024_definition_gap"
    assert entry["ordinary_h_diesel_missing_days"] == 22
    assert entry["silent_blend_substitution_permitted"] is False
    assert entry["imputation_permitted"] is False
    for blend in ("H-DIESEL B7", "H-DIESEL B10", "H-DIESEL B20"):
        assert blend in entry["forbidden_substitutes"]
    assert "neither filled" in entry["january_2024_handling"]


# ---------------------------------------------------------------------------
# 10. Transformation status
# ---------------------------------------------------------------------------
@requires_run
def test_depth_and_readiness_are_separate_for_every_transformation():
    """Synthetic failure: a transformation approved before full ingestion."""
    status = _decision()["transformation_status"]
    expected = {"price_level", "log_change_1m_pct", "log_change_3m_pct",
                "log_change_12m_pct", "realized_volatility_3m_pct"}
    assert set(status) == expected
    for name, entry in status.items():
        assert entry["historical_depth_sufficient"] is True, name
        assert entry["source_ready_for_transformation"] is False, name


@requires_run
def test_readiness_blockers_are_stated():
    blockers = _decision()["transformation_readiness_blockers"]
    assert any("daily ingestion" in b for b in blockers)
    assert any("aggregation" in b for b in blockers)


def test_no_transformation_is_created():
    assert CONFIG["transformations_created_in_c6_5"] is False
    source = (ROOT / "scripts" / "decide_c6_5_eppo_policy.py").read_text(encoding="utf-8")
    for forbidden in ("log_change", "rolling", "pct_change", "std(", "resample"):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------------------
# 11. C7 boundary and isolation
# ---------------------------------------------------------------------------
@requires_run
def test_c7_authorization_boundary():
    authorization = _decision()["c7_authorization"]
    assert authorization["c7_full_archive_ingestion_authorized"] is True
    assert authorization["c7_monthly_source_aggregation_authorized"] == "conditional"
    assert authorization["c7_predictive_feature_creation_authorized"] is False
    assert authorization["c7_target_join_authorized"] is False
    assert authorization["c7_modeling_authorized"] is False


@requires_run
def test_provenance_declares_no_target_model_or_locked_test():
    provenance = _decision()["provenance"]
    for key in ("target_joined", "target_association_computed", "model_trained",
                "locked_test_accessed", "feature_semantics_approved",
                "model_feature_approved"):
        assert provenance[key] is False, key


@requires_run
def test_preserved_decisions_include_no_d4_recalculation():
    preserved = _decision()["preserved_decisions"]
    assert preserved["d4_metrics_recalculated"] is False
    assert preserved["d4_results_changed"] is False
    assert preserved["c6_raw_inventory_or_parsed_values_changed"] is False


def test_runner_imports_no_target_evaluation_or_model_module():
    """Check the IMPORT lines: 'modeling' also appears in c7_modeling_authorized."""
    source = (ROOT / "scripts" / "decide_c6_5_eppo_policy.py").read_text(encoding="utf-8")
    imports = [line for line in source.splitlines()
               if line.startswith(("import ", "from "))]
    for line in imports:
        for forbidden in ("modeling", "evaluation", "targets", "models"):
            assert forbidden not in line, f"runner imports {forbidden}: {line}"
    for forbidden in ("load_b3_artifacts", "walk_forward", "locked_test_origins",
                      "predict_baseline", "fit_ridge"):
        assert forbidden not in source, forbidden


def test_policy_module_touches_no_target_field():
    import inspect
    source = inspect.getsource(POLICY)
    for forbidden in ("target_raw_value", "observed_score", "mpi_adverse_yoy", "industry_id"):
        assert forbidden not in source, forbidden


@requires_run
def test_decision_is_a_declared_value():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_latest_vintage_policy.schema.yaml").read_text("utf-8")
    )
    assert _decision()["decision"] in schema["decision_values"]
    assert schema["task"] == "C6.5"
