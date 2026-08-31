"""Task C7.5 tests — product semantics and the split aggregation contract.

The decision this task makes is a merge: two label forms become one series. A
merge is the kind of change that looks harmless and is very hard to undo, so
most of this file is about what may *not* justify it.

Numeric continuity may not. String similarity may not. An assumption about what
``(1)`` and ``(2)`` mean may not. The gate needs direct semantic evidence, and
the synthetic-failure tests at the end construct each of those shortcuts and
require an explicit raise.

The second half guards the other conflation C7 left behind: an approved
aggregation *method* is not complete *coverage*, and a descriptive mean over the
days that happen to exist is not a transformation input.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.data import eppo_aggregation_contract as AC
from thai_supply_chain_ews.data import eppo_product_semantics as PS

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "eppo_product_semantics.yaml").read_text(encoding="utf-8")
)
DECISION = ROOT / "docs" / "c7_5_eppo_semantic_decision.json"
C7_AUDIT = ROOT / "docs" / "c7_eppo_full_archive_audit.json"
C7_DAILY = ROOT / "data" / "interim" / "c7_eppo_daily_prices.parquet"
C7_MONTHLY = ROOT / "data" / "interim" / "c7_eppo_monthly_source.parquet"
SEMANTIC_PARQUET = ROOT / "data" / "interim" / "c7_5_eppo_monthly_semantic.parquet"

FO600 = "eppo_ex_refinery_fo600_2s"
FO1500 = "eppo_ex_refinery_fo1500_2s"
HSD = "eppo_ex_refinery_hsd"

requires_run = pytest.mark.skipif(not DECISION.is_file(), reason="C7.5 has not been run")
requires_parquet = pytest.mark.skipif(
    not SEMANTIC_PARQUET.is_file(), reason="the semantic overlay is not present"
)


def _decision():
    return json.loads(DECISION.read_text(encoding="utf-8"))


# ===========================================================================
# Fixtures
# ===========================================================================
def _direct_evidence(kind="source_controlled_schema_or_data_dictionary"):
    return PS.SemanticEvidence(
        evidence_class="direct_semantic", kind=kind,
        statement="the workbook's own bilingual sheet names one product",
        source="EPPO workbook sheet โครงสร้างราคาน้ำมัน",
        observed_in_documents=471,
    )


def _structural(kind="same_unit"):
    return PS.SemanticEvidence(
        evidence_class="strong_structural_corroboration", kind=kind,
        statement="uniform across the archive", source="full-archive sweep",
    )


def _numeric():
    return PS.SemanticEvidence(
        evidence_class="numeric_corroboration_only",
        kind="series_continuous_across_boundary",
        statement="prices either side of the boundary are close",
        source="C7 canonical daily table",
    )


def _candidate(**overrides):
    base = {
        "canonical_product_id": FO600,
        "label_a": "FO 600 (1) 2%S",
        "label_b": "FO 600  2%S",
        "unit_a": "BAHT/LITRE", "unit_b": "BAHT/LITRE",
        "price_stage_a": "EX-REFIN.", "price_stage_b": "EX-REFIN.",
        "documents_a": 679, "documents_b": 66,
        "co_occurring_documents": 0,
        "forms_replace_one_another": True,
        "row_position_consistent": True,
        "neighbours_consistent": True,
        "downstream_treatment_identical": True,
        "contradictory_evidence": [],
        "evidence": [_direct_evidence(), _structural(), _numeric()],
    }
    base.update(overrides)
    return PS.EquivalenceCandidate(**base)


def _month(**overrides):
    base = {
        "series_id": FO600, "canonical_product_id": FO600,
        "reference_month": "2024-08", "aggregation_status": "approved_complete_inventory",
        "monthly_value_strict": 16.75, "monthly_value_descriptive": 16.75,
        "coverage_complete": True, "valid_document_day_count": 21,
        "discovered_document_day_count": 21, "approved_transformation_input": True,
    }
    base.update(overrides)
    return base


# ===========================================================================
# 1. C7 invariants
# ===========================================================================
@requires_run
def test_all_c7_invariants_reproduced():
    invariants = _decision()["c7_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 24
    for name, check in invariants["checks"].items():
        assert check["reproduced"] is True, name


@requires_run
def test_c7_headline_counts_match_the_brief():
    checks = _decision()["c7_invariants"]["checks"]
    expected = {
        "discovered_media_records": 1336,
        "distinct_document_days": 1315,
        "http_successes": 1333,
        "content_valid_files": 1331,
        "byte_identical_duplicates": 21,
        "conflicting_same_date_values": 0,
        "wrong_date_attachments": 2,
        "failed_retrievals": 3,
        "valid_canonical_document_days": 1310,
        "unresolved_document_days": 5,
        "canonical_daily_rows": 3625,
        "monthly_rows": 195,
        "fo600_daily_rows": 1310,
        "fo1500_daily_rows": 1310,
        "hsd_daily_rows": 1005,
        "fo600_monthly_approved": 58,
        "fo1500_monthly_approved": 58,
        "hsd_monthly_approved": 46,
        "fuel_oil_variant_document_days": 66,
        "ordinary_hsd_absent_document_days": 305,
        "hsd_gap_start": "2023-09-18",
        "hsd_gap_end": "2024-12-17",
        "aggregation_rule_version": "c7_v1",
        "monthly_aggregation_contract_approved": False,
    }
    for name, value in expected.items():
        assert checks[name]["actual"] == value, name


def test_inherited_timing_policy_is_unchanged():
    policy = CONFIG["inherited_policy"]
    assert policy["latest_vintage_values_used"] is True
    assert policy["historical_release_timing_verified"] is False
    assert policy["point_in_time_values_supported"] is False
    assert policy["fully_real_time_backtest"] is False
    assert policy["minimum_verified_publication_lag_months"] is None
    assert policy["operational_policy_lag_months"] == 2
    assert policy["operational_lag_is_measured"] is False
    assert policy["source_available_as_of"] is None


def test_preserved_decisions_and_provenance_are_all_false():
    for key, value in CONFIG["preserved_decisions"].items():
        assert value is False, key
    for key, value in CONFIG["provenance"].items():
        assert value is False, key


# ===========================================================================
# 2. The equivalence gate
# ===========================================================================
def test_direct_semantic_evidence_is_required():
    without_direct = _candidate(evidence=[_structural(), _numeric()])
    decision = PS.evaluate_equivalence(without_direct)
    assert decision.decision == "equivalence_unresolved"
    assert "direct_semantic_evidence_present" in decision.failed_conditions


def test_numeric_continuity_alone_cannot_establish_equivalence():
    with pytest.raises(PS.EquivalenceError, match="only evidence offered is numeric"):
        PS.assert_not_numeric_only_equivalence([_numeric()])
    decision = PS.evaluate_equivalence(_candidate(evidence=[_numeric()]))
    assert decision.decision != "equivalence_established"


def test_numeric_evidence_may_not_be_reclassified_as_direct():
    # Promoting numeric corroboration to any stronger class is refused...
    with pytest.raises(PS.EquivalenceError, match="may never be promoted"):
        PS.SemanticEvidence(
            evidence_class="strong_structural_corroboration",
            kind="series_continuous_across_boundary",
            statement="the numbers line up", source="daily table",
        )
    # ...and so is calling it direct semantic evidence.
    with pytest.raises(PS.EquivalenceError, match="not direct semantic evidence"):
        PS.SemanticEvidence(
            evidence_class="direct_semantic",
            kind="series_continuous_across_boundary",
            statement="the numbers line up", source="daily table",
        )
    with pytest.raises(PS.EquivalenceError, match="not direct semantic evidence"):
        PS.SemanticEvidence(
            evidence_class="direct_semantic", kind="same_unit",
            statement="unit matches", source="sweep",
        )


def test_unit_price_stage_number_and_sulphur_must_all_match():
    assert PS.evaluate_equivalence(
        _candidate(unit_b="BAHT/KILOGRAM")
    ).failed_conditions == ["unit_unchanged"]
    assert PS.evaluate_equivalence(
        _candidate(price_stage_b="WHOLESALE")
    ).failed_conditions == ["price_stage_unchanged"]
    mismatch = PS.evaluate_equivalence(
        _candidate(label_b="FO 1500 2%S")
    )
    assert "product_number_unchanged" in mismatch.failed_conditions
    assert mismatch.decision == "equivalence_rejected"
    sulphur = PS.evaluate_equivalence(_candidate(label_b="FO 600  3%S"))
    assert "sulphur_grade_unchanged" in sulphur.failed_conditions
    assert sulphur.decision == "equivalence_rejected"


def test_co_occurring_labels_reject_equivalence():
    decision = PS.evaluate_equivalence(_candidate(co_occurring_documents=1))
    assert decision.decision != "equivalence_established"
    assert "labels_never_co_occur" in decision.failed_conditions


def test_contradictory_evidence_rejects_equivalence():
    decision = PS.evaluate_equivalence(
        _candidate(contradictory_evidence=["Thai companion names differ"])
    )
    assert decision.decision == "equivalence_rejected"
    assert "no_contradictory_evidence" in decision.failed_conditions


def test_structural_corroboration_must_be_consistent():
    decision = PS.evaluate_equivalence(_candidate(row_position_consistent=False))
    assert "structural_corroboration_consistent" in decision.failed_conditions
    assert decision.decision == "equivalence_unresolved"


def test_a_complete_candidate_passes_and_records_what_carried_it():
    decision = PS.evaluate_equivalence(_candidate())
    assert decision.decision == "equivalence_established"
    assert decision.failed_conditions == []
    assert decision.direct_evidence_count == 1
    assert decision.numeric_evidence_load_bearing is False
    assert decision.rule_id == "fo_ordinal_index_dropped_v1"
    assert decision.ordinal_marker_meaning == "not_established_from_inspected_sources"


def test_every_allowed_decision_is_declared_in_the_config():
    assert set(PS.EQUIVALENCE_DECISIONS) == set(
        CONFIG["equivalence_gate"]["allowed_decisions"]
    )
    assert set(PS.DIRECT_SEMANTIC_EVIDENCE_KINDS) == set(
        CONFIG["evidence_hierarchy"]["direct_semantic"]
    )
    assert set(PS.NUMERIC_ONLY_EVIDENCE_KINDS) == set(
        CONFIG["evidence_hierarchy"]["numeric_corroboration_only"]
    )
    assert CONFIG["evidence_hierarchy"]["numeric_alone_can_establish_equivalence"] is False
    assert CONFIG["equivalence_gate"]["gate_lowered_to_obtain_a_complete_series"] is False


def test_label_parsing_keeps_grade_and_ordinal_apart():
    assert PS.parse_fuel_oil_label("FO 600 (1) 2%S") == {
        "raw_label": "FO 600 (1) 2%S", "product_number": "600",
        "ordinal": "1", "sulphur_grade": "2%S",
    }
    assert PS.parse_fuel_oil_label("FO 600  2%S")["ordinal"] is None
    assert PS.parse_fuel_oil_label("FO 600  2%S")["product_number"] == "600"
    assert PS.parse_fuel_oil_label("H-DIESEL") is None


# ===========================================================================
# 3. The evidence that was actually found
# ===========================================================================
@requires_run
def test_the_decision_rests_on_direct_evidence_not_numbers():
    equivalence = _decision()["equivalence"]
    assert equivalence["numeric_evidence_load_bearing"] is False
    for decision in equivalence["decisions"]:
        assert decision["decision"] in PS.EQUIVALENCE_DECISIONS
        if decision["decision"] == "equivalence_established":
            assert decision["direct_evidence_count"] >= 1
            assert decision["failed_conditions"] == []


@requires_run
def test_direct_evidence_records_its_source_and_quotation():
    for block in _decision()["equivalence"]["candidates"].values():
        direct = [e for e in block["evidence"]
                  if e["evidence_class"] == "direct_semantic"]
        assert direct
        for item in direct:
            assert item["kind"] in PS.DIRECT_SEMANTIC_EVIDENCE_KINDS
            assert item["source"]
            assert item["observed_in_documents"] > 0
            assert item["quotation"]


@requires_run
def test_hidden_rows_notes_and_comments_were_inspected():
    scope = _decision()["inspection_scope"]["workbook_features"]
    for feature in ("hidden_rows", "hidden_columns", "hidden_sheets",
                    "cell_comments_and_notes", "merged_cells", "defined_names",
                    "formulas", "print_areas", "headers_and_footers",
                    "footnote_references", "thai_language_notes",
                    "document_metadata"):
        assert feature in scope, feature
    detail = _decision()["equivalence"]["candidates"][FO600]["detail"]
    assert detail["documents_with_a_note_mentioning_the_ordinal"] == 0
    assert "documents_with_cell_comments" in detail
    assert "documents_with_hidden_rows_carrying_text" in detail


@requires_run
def test_official_sources_beyond_the_workbook_were_recorded():
    sources = _decision()["inspection_scope"]["official_sources"]
    assert "wordpress_rest_media_records" in sources
    assert "eppo_oil_api_oil_structure_prices" in sources
    assert _decision()["equivalence"]["ordinal_marker_meaning"] == (
        "not_established_from_inspected_sources"
    )
    note = _decision()["equivalence"]["ordinal_marker_note"]
    assert "not proof" in note


@requires_run
def test_the_two_fuel_oils_remain_distinct_products():
    decisions = _decision()["equivalence"]["decisions"]
    canonical = {d["canonical_product_id"] for d in decisions}
    assert canonical == {FO600, FO1500}
    for decision in decisions:
        parsed_a = PS.parse_fuel_oil_label(decision["label_a"])
        parsed_b = PS.parse_fuel_oil_label(decision["label_b"])
        assert parsed_a["product_number"] == parsed_b["product_number"]
    numbers = {
        PS.parse_fuel_oil_label(d["label_a"])["product_number"] for d in decisions
    }
    assert numbers == {"600", "1500"}


# ===========================================================================
# 4. Raw-label preservation and canonical identity
# ===========================================================================
def test_canonical_identity_never_rewrites_the_raw_label():
    decision = PS.evaluate_equivalence(_candidate())
    identity = PS.canonical_identity("FO 600  2%S", [decision])
    assert identity["source_product_label_raw"] == "FO 600  2%S"
    assert identity["canonical_product_id"] == FO600
    assert identity["label_variant_status"] == (
        "source_label_variant_equivalence_established"
    )
    assert identity["semantic_equivalence_rule_id"] == "fo_ordinal_index_dropped_v1"
    assert identity["canonical_identity_version"] == PS.CANONICAL_IDENTITY_VERSION


def test_canonical_identity_is_withheld_when_equivalence_is_not_established():
    unresolved = PS.evaluate_equivalence(_candidate(evidence=[_structural()]))
    identity = PS.canonical_identity("FO 600  2%S", [unresolved])
    assert identity["canonical_product_id"] is None
    assert identity["label_variant_status"] == "equivalence_not_established"


def test_raw_label_preservation_guard_raises_on_a_rewrite():
    PS.assert_raw_label_preserved(
        {"source_product_label_raw": "FO 600  2%S"}, "FO 600  2%S"
    )
    with pytest.raises(PS.EquivalenceError, match="never a rewrite"):
        PS.assert_raw_label_preserved(
            {"source_product_label_raw": "FO 600 (1) 2%S"}, "FO 600  2%S"
        )


@requires_run
def test_both_raw_label_forms_survive_into_the_overlay():
    preservation = _decision()["raw_label_preservation"]
    assert preservation["raw_labels_overwritten"] is False
    assert preservation["c7_daily_parquet_modified"] is False
    assert preservation["c7_monthly_audit_artifact_overwritten"] is False
    # C7 stored the whitespace-collapsed spelling; both label FORMS survive, and
    # the double-spaced displayed string is recorded in the config beside it.
    labels = {PS.collapse_label(x) for x in preservation["labels_retained"]}
    assert {"FO 600 (1) 2%S", "FO 600 2%S",
            "FO 1500 (2) 2%S", "FO 1500 2%S"} <= labels
    pair = CONFIG["label_pairs_under_question"][FO600]
    assert pair["label_b"] == "FO 600  2%S"
    assert pair["label_b_as_stored_by_c7"] == "FO 600 2%S"
    assert PS.collapse_label(pair["label_b"]) == pair["label_b_as_stored_by_c7"]


# ===========================================================================
# 5. H-DIESEL
# ===========================================================================
def test_h_diesel_gap_is_recorded_in_full():
    hsd = CONFIG["h_diesel"]
    assert hsd["ordinary_label_gap_start"] == "2023-09-18"
    assert hsd["ordinary_label_gap_end"] == "2024-12-17"
    assert hsd["missing_document_days"] == 305
    assert hsd["affected_reference_months"] == "2023-09 through 2024-12"
    assert hsd["blend_substitution_permitted"] is False
    assert hsd["imputation_permitted"] is False


def test_h_diesel_is_not_eligible_for_any_c8_transformation():
    hsd = CONFIG["h_diesel"]
    assert hsd["eligible_for_c8_primary_transformation"] is False
    assert hsd["eligible_for_c8_sensitivity_transformation"] is False
    assert hsd["status"] == "not_ready_long_semantic_definition_gap"


def test_the_h_diesel_decision_does_not_invalidate_the_documents():
    hsd = CONFIG["h_diesel"]
    assert hsd["documents_invalid"] is False
    assert hsd["blend_products_invalid"] is False
    assert hsd["observations_preserved"] is True
    assert hsd["blend_provenance_preserved"] is True


@requires_run
def test_h_diesel_gap_months_carry_no_value_in_either_view():
    rows = [r for r in _decision()["monthly_rows"] if r["series_id"] == HSD]
    gap = [r for r in rows if "2023-09" <= r["reference_month"] <= "2024-12"]
    assert len(gap) == 16
    for row in gap:
        assert row["aggregation_status"] == "semantic_definition_gap"
        assert row["monthly_value_strict"] is None
        assert row["monthly_value_descriptive"] is None
        assert row["approved_transformation_input"] is False


@requires_run
def test_h_diesel_observations_outside_the_gap_are_preserved():
    rows = [r for r in _decision()["monthly_rows"] if r["series_id"] == HSD]
    assert len(rows) == 65
    kept = [r for r in rows if r["approved_transformation_input"]]
    assert len(kept) >= 45
    assert all(r["monthly_value_strict"] is not None for r in kept)


# ===========================================================================
# 6. Bounded recovery
# ===========================================================================
def test_recovery_is_bounded_to_a_fixed_channel_list():
    permitted = set(CONFIG["recovery"]["permitted_channels"])
    assert set(PS.RECOVERY_CHANNELS) <= permitted
    assert CONFIG["recovery"]["termination_condition"]
    for prohibited in ("broad_guessed_filename_enumeration",
                       "silent_reassignment_of_a_wrong_date_document",
                       "copying_a_neighbouring_price", "interpolating_a_value",
                       "sending_an_email_or_external_message"):
        assert prohibited in CONFIG["recovery"]["prohibited"], prohibited


def test_a_wrong_date_document_is_not_reassigned_on_the_filename_alone():
    attempt = PS.classify_recovery(
        listing_date="2022-12-05", media_id=21054,
        channels_inspected=["wordpress_media_record"],
        attachment_retrievable=True, internal_date="2022-12-06",
        parent_post_date=None, parent_post_title_date=None,
    )
    assert attempt.status == "wrong_date_attachment_unresolved"
    assert attempt.recovered_effective_date is None


def test_one_corroborating_source_is_not_enough_to_reassign():
    attempt = PS.classify_recovery(
        listing_date="2022-12-05", media_id=21054,
        channels_inspected=["wordpress_media_record", "parent_post"],
        attachment_retrievable=True, internal_date="2022-12-06",
        parent_post_date="2022-12-06T02:37:00", parent_post_title_date=None,
    )
    assert attempt.status == "wrong_date_attachment_unresolved"


def test_two_independent_official_sources_permit_a_documented_reassignment():
    attempt = PS.classify_recovery(
        listing_date="2022-12-05", media_id=21054,
        channels_inspected=["wordpress_media_record", "parent_post"],
        attachment_retrievable=True, internal_date="2022-12-06",
        parent_post_date="2022-12-06T02:37:00",
        parent_post_title_date="2022-12-06", sha256="a" * 64,
    )
    assert attempt.status == "recovered_and_validated"
    assert attempt.recovered_effective_date == "2022-12-06"
    assert set(attempt.corroborating_sources) == {
        "parent_post_publication_date", "parent_post_title_date",
        "document_internal_date",
    }


def test_an_unretrievable_attachment_stays_explicit():
    attempt = PS.classify_recovery(
        listing_date="2026-04-17", media_id=46232,
        channels_inspected=list(PS.RECOVERY_CHANNELS),
        attachment_retrievable=False,
    )
    assert attempt.status == "official_attachment_unretrievable"
    assert attempt.reason == "official_document_not_recovered_from_inspected_channels"
    assert attempt.termination_condition == "all_official_channels_exhausted"
    assert attempt.recovered_effective_date is None


def test_thai_buddhist_era_titles_parse_to_gregorian_dates():
    assert PS.thai_date_to_iso("โครงสร้างราคาขายปลีกน้ำมัน 6 ธันวาคม  2565") == "2022-12-06"
    assert PS.thai_date_to_iso("โครงสร้างราคาขายปลีกน้ำมัน 24 มกราคม 2568") == "2025-01-24"
    assert PS.thai_date_to_iso("no date here") is None


@requires_run
def test_each_of_the_five_targets_has_an_explicit_outcome():
    attempts = _decision()["recovery"]["attempts"]
    assert len(attempts) == 5
    listings = {a["listing_date"] for a in attempts}
    assert listings == {"2022-12-05", "2025-01-25",
                        "2026-04-17", "2026-04-18", "2026-04-19"}
    for attempt in attempts:
        assert attempt["status"] in PS.RECOVERY_STATUSES
        assert attempt["termination_condition"]
        assert attempt["channels_inspected"]
        assert attempt["web_archive_used"] is False
    assert _decision()["recovery"]["silent_reassignment"] is False


@requires_run
def test_unrecovered_days_use_the_required_wording():
    unrecovered = [a for a in _decision()["recovery"]["attempts"]
                   if a["status"] != "recovered_and_validated"]
    assert len(unrecovered) == 3
    for attempt in unrecovered:
        assert attempt["reason"] == (
            "official_document_not_recovered_from_inspected_channels"
        )


# ===========================================================================
# 7. Method approval versus coverage
# ===========================================================================
def test_the_three_approvals_are_separate_fields():
    approvals = CONFIG["separated_approvals"]
    assert set(approvals) == {
        "aggregation_method_semantics_approved",
        "full_requested_window_coverage_complete",
        "series_ready_for_transformation_with_explicit_gaps",
    }
    assert approvals["aggregation_method_semantics_approved"]["is_not"] == (
        "complete_source_coverage"
    )


def test_method_approval_may_not_be_described_as_coverage():
    AC.assert_method_approval_is_not_coverage(
        True, False, "the rule is semantically valid and reproducible"
    )
    with pytest.raises(AC.AggregationContractError, match="separate fields"):
        AC.assert_method_approval_is_not_coverage(
            True, False, "the aggregation is approved so the series is complete"
        )
    with pytest.raises(AC.AggregationContractError):
        AC.assert_method_approval_is_not_coverage(
            True, False, "approved, giving full coverage of the window"
        )


def test_a_descriptive_value_is_never_a_transformation_input():
    AC.assert_transformation_input_permitted(_month())
    gap = _month(aggregation_status="known_document_gap",
                 monthly_value_strict=None, monthly_value_descriptive=24.6477,
                 coverage_complete=False, approved_transformation_input=False)
    with pytest.raises(AC.AggregationContractError, match="gap must "):
        AC.assert_transformation_input_permitted(gap)


def test_a_complete_status_without_a_strict_value_still_raises():
    row = _month(monthly_value_strict=None)
    with pytest.raises(AC.AggregationContractError, match="no strict"):
        AC.assert_transformation_input_permitted(row)
    row = _month(coverage_complete=False)
    with pytest.raises(AC.AggregationContractError, match="not covered"):
        AC.assert_transformation_input_permitted(row)


def test_every_monthly_status_is_declared_in_the_config():
    assert set(AC.MONTHLY_STATUSES) == set(CONFIG["monthly_status_vocabulary"])
    for required in ("approved_complete_inventory", "approved_with_source_label_variant",
                     "known_document_gap", "semantic_definition_gap",
                     "unit_or_definition_break", "document_identity_unresolved",
                     "document_retrieval_unresolved"):
        assert required in AC.MONTHLY_STATUSES, required


def test_monthly_contract_row_separates_strict_from_descriptive():
    observations = [("2026-04-01", 24.0, "FO 600 (1) 2%S"),
                    ("2026-04-02", 25.0, "FO 600 (1) 2%S")]
    complete = AC.monthly_contract_row(
        FO600, FO600, "2026-04", observations, discovered_days=2, unresolved_days=[],
    )
    assert complete.aggregation_status == "approved_complete_inventory"
    assert complete.monthly_value_strict == pytest.approx(24.5)
    assert complete.approved_transformation_input is True

    gapped = AC.monthly_contract_row(
        FO600, FO600, "2026-04", observations, discovered_days=3,
        unresolved_days=["2026-04-03"],
        unresolved_day_status="official_attachment_unretrievable",
    )
    assert gapped.aggregation_status == "known_document_gap"
    assert gapped.monthly_value_strict is None
    assert gapped.monthly_value_descriptive == pytest.approx(24.5)
    assert gapped.coverage_complete is False
    assert gapped.approved_transformation_input is False
    assert "2_of_3" in gapped.quality_flag


def test_an_unresolved_equivalence_keeps_a_variant_month_blocked():
    observations = [("2024-08-01", 16.0, "FO 600  2%S")]
    row = AC.monthly_contract_row(
        FO600, FO600, "2024-08", observations, discovered_days=1, unresolved_days=[],
        equivalence_established=False, label_variant_days=1,
    )
    assert row.aggregation_status == "unit_or_definition_break"
    assert row.monthly_value_strict is None
    assert row.approved_transformation_input is False


def test_series_contract_reports_the_three_answers_independently():
    rows = [
        AC.MonthlyContractRow(series_id=FO600, canonical_product_id=FO600,
                              reference_month="2024-08",
                              aggregation_status="approved_complete_inventory",
                              monthly_value_strict=16.0, coverage_complete=True,
                              approved_transformation_input=True),
        AC.MonthlyContractRow(series_id=FO600, canonical_product_id=FO600,
                              reference_month="2026-04",
                              aggregation_status="known_document_gap"),
    ]
    contract = AC.series_contract(FO600, rows, method_approved=True,
                                  ready_permitted=True)
    assert contract.aggregation_method_semantics_approved is True
    assert contract.full_requested_window_coverage_complete is False
    assert contract.series_ready_for_transformation_with_explicit_gaps is True
    assert contract.months_incomplete == [("2026-04", "known_document_gap")]
    assert contract.feature_semantics_approved is False
    assert contract.model_feature_approved is False


def test_a_semantic_block_makes_a_series_unready_however_many_months_are_complete():
    rows = [
        AC.MonthlyContractRow(series_id=HSD, canonical_product_id=HSD,
                              reference_month=f"2021-{m:02d}",
                              aggregation_status="approved_complete_inventory",
                              monthly_value_strict=20.0, coverage_complete=True,
                              approved_transformation_input=True)
        for m in range(1, 13)
    ]
    contract = AC.series_contract(HSD, rows, method_approved=True,
                                  ready_permitted=False,
                                  blocking_reasons=["long_definition_gap"])
    assert contract.months_complete == 12
    assert contract.series_ready_for_transformation_with_explicit_gaps is False
    assert contract.blocking_reasons == ["long_definition_gap"]


@requires_run
def test_reported_approvals_keep_method_and_coverage_apart():
    approvals = _decision()["separated_approvals"]
    assert set(approvals) == {FO600, FO1500, HSD}
    for series_id, contract in approvals.items():
        assert contract["aggregation_method_semantics_approved"] is True, series_id
        assert contract["full_requested_window_coverage_complete"] is False, series_id
        assert contract["feature_semantics_approved"] is False, series_id
        assert contract["model_feature_approved"] is False, series_id
    assert approvals[HSD]["series_ready_for_transformation_with_explicit_gaps"] is False
    assert _decision()["method_approval_is_not_coverage"] is True


# ===========================================================================
# 8. The semantic overlay
# ===========================================================================
@requires_run
def test_every_series_month_has_exactly_one_overlay_row():
    rows = _decision()["monthly_rows"]
    keys = [(r["series_id"], r["reference_month"]) for r in rows]
    assert len(keys) == len(set(keys)) == 195
    for series_id in (FO600, FO1500, HSD):
        months = sorted(r["reference_month"] for r in rows if r["series_id"] == series_id)
        assert months[0] == "2021-01" and months[-1] == "2026-05"
        assert len(months) == 65


@requires_run
def test_a_null_month_is_never_presented_as_an_approved_value():
    for row in _decision()["monthly_rows"]:
        if row["monthly_value_strict"] is None:
            assert row["approved_transformation_input"] is False
            assert row["aggregation_status"] not in AC.COMPLETE_STATUSES
        else:
            assert row["coverage_complete"] is True
            assert row["aggregation_status"] in AC.COMPLETE_STATUSES


@requires_run
def test_a_known_document_gap_stays_labelled_incomplete():
    gaps = [r for r in _decision()["monthly_rows"]
            if r["aggregation_status"] == "known_document_gap"]
    assert gaps
    for row in gaps:
        assert row["monthly_value_strict"] is None
        assert row["coverage_complete"] is False
        assert row["unresolved_document_day_count"] > 0
        assert row["valid_document_day_count"] < row["discovered_document_day_count"]
        assert "incomplete_month" in row["quality_flag"]


@requires_run
def test_availability_fields_are_unchanged_by_the_overlay():
    for row in _decision()["monthly_rows"]:
        assert row["source_available_as_of"] is None
        assert row["availability_basis"] == (
            "conservative_policy_not_historical_measurement"
        )
        assert row["latest_vintage_used"] is True
        assert row["point_in_time_supported"] is False
        assert row["policy_available_month"] == AC.add_months(row["reference_month"], 2)


@requires_parquet
def test_semantic_overlay_parquet_matches_its_schema():
    import pandas as pd

    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_product_semantics.schema.yaml").read_text(
            encoding="utf-8")
    )
    frame = pd.read_parquet(SEMANTIC_PARQUET)
    declared = [c["name"] for c in schema["observation"]["columns"]]
    assert set(declared) <= set(frame.columns)
    assert not frame.duplicated(subset=schema["observation"]["grain"]).any()
    assert frame["source_available_as_of"].isna().all()
    assert schema["mutates_c7_raw_or_daily_artifacts"] is False
    assert schema["overwrites_c7_monthly_audit_artifact"] is False


@requires_parquet
def test_overlay_has_no_transformation_or_target_column():
    import pandas as pd

    frame = pd.read_parquet(SEMANTIC_PARQUET)
    for column in frame.columns:
        name = column.lower()
        for fragment in ("log_change", "pct_change", "volatility", "zscore",
                         "shock", "exposure", "mpi", "target", "lag_"):
            assert fragment not in name, column


@requires_run
def test_overlay_lineage_is_present_and_versioned():
    for row in _decision()["monthly_rows"]:
        assert row["lineage_checksum"]
        assert len(row["lineage_checksum"]) == 64
        assert row["semantic_overlay_version"] == "c7_5_semantic_v1"
        assert row["canonical_identity_version"] == PS.CANONICAL_IDENTITY_VERSION


# ===========================================================================
# 9. Coverage views
# ===========================================================================
def test_issue_month_reach_is_derived_from_the_lag_not_guessed():
    assert AC.issue_months_affected("2023-11", 2, 0) == ["2024-01"]
    reach = AC.issue_months_affected("2023-11", 2, 12)
    assert reach[0] == "2024-01" and reach[-1] == "2025-01" and len(reach) == 13


def test_operational_relevance_reads_only_issue_month_ranges():
    splits = {"development": ("2024-01", "2025-03"),
              "purge": ("2025-04", "2025-06"),
              "locked_test": ("2025-07", "2026-04")}
    relevance = AC.operational_relevance("2023-11", splits, 2, 0)
    assert relevance["direct_issue_month"] == "2024-01"
    assert list(relevance["affected_issue_origins"]) == ["development"]
    assert relevance["affects_any_preregistered_issue_origin"] is True
    beyond = AC.operational_relevance("2026-04", splits, 2, 12)
    assert beyond["affected_issue_origins"] == {}
    assert beyond["affects_any_preregistered_issue_origin"] is False
    assert "No target value" in relevance["note"]


@requires_run
def test_full_window_and_operational_window_are_reported_separately():
    coverage = _decision()["coverage_views"]
    assert coverage["full_source_audit_window"] == {"start": "2021-01", "end": "2026-05"}
    assert coverage["maximum_preregistered_issue_month"] == "2026-04"
    assert coverage["maximum_required_source_reference_month"] == "2026-02"
    assert coverage["target_outcomes_read"] is False
    assert set(coverage["preregistered_issue_month_ranges"]) == {
        "development", "purge", "locked_test"
    }


@requires_run
def test_april_2026_is_documented_even_though_no_origin_needs_it():
    coverage = _decision()["coverage_views"]
    assert coverage["april_2026_documented"] is True
    april = [r for r in coverage["incomplete_month_relevance"]
             if r["reference_month"] == "2026-04"]
    assert len(april) == 3
    for row in april:
        assert row["direct_level_reach"]["affects_any_preregistered_issue_origin"] is False
        assert row["maximum_prehistory_reach"][
            "affects_any_preregistered_issue_origin"] is False


@requires_run
def test_the_h_diesel_gap_reaches_preregistered_origins():
    relevance = _decision()["coverage_views"]["incomplete_month_relevance"]
    hsd = [r for r in relevance if r["series_id"] == HSD
           and r["aggregation_status"] == "semantic_definition_gap"]
    assert hsd
    assert any(
        r["direct_level_reach"]["affects_any_preregistered_issue_origin"] for r in hsd
    )


# ===========================================================================
# 10. Shared fuel-oil channel
# ===========================================================================
def test_the_two_fuel_oils_may_not_be_added_or_averaged():
    AC.assert_no_additive_fuel_oil_aggregate([FO600], "level")
    AC.assert_no_additive_fuel_oil_aggregate([FO1500, HSD], "level")
    for operation in ("sum", "simple average", "composite index"):
        with pytest.raises(AC.AggregationContractError, match="distinct products"):
            AC.assert_no_additive_fuel_oil_aggregate([FO600, FO1500], operation)


def test_shared_channel_rules_forbid_every_combination_route():
    for source in (AC.SHARED_CHANNEL_RULES, CONFIG["shared_fuel_oil_channel"]):
        assert source["additive_aggregation_allowed"] is False
        assert source["simple_average_allowed"] is False
        assert source["automatic_composite_index_allowed"] is False
        assert source["simultaneous_model_entry_approved"] is False
    assert CONFIG["shared_fuel_oil_channel"]["both_series_preserved"] is True
    assert CONFIG["shared_fuel_oil_channel"][
        "selection_by_target_performance_allowed"] is False
    assert CONFIG["shared_fuel_oil_channel"]["selection_requires"] == (
        "independent_structural_rule"
    )


@requires_run
def test_both_fuel_oils_survive_as_separate_series():
    rows = _decision()["monthly_rows"]
    assert {r["series_id"] for r in rows} == {FO600, FO1500, HSD}
    for month in ("2024-08", "2025-05"):
        values = {
            r["series_id"]: r["monthly_value_strict"] for r in rows
            if r["reference_month"] == month and r["series_id"] in (FO600, FO1500)
        }
        assert len(values) == 2
        assert values[FO600] != values[FO1500]


# ===========================================================================
# 11. C8 boundary and isolation
# ===========================================================================
@requires_run
def test_c8_authorization_matches_the_gate_outcome():
    authorization = _decision()["c8_authorization"]
    equivalence = {
        d["canonical_product_id"]: d["decision"]
        for d in _decision()["equivalence"]["decisions"]
    }
    assert authorization["c8_fo600_transformation_authorized"] == (
        equivalence[FO600] == "equivalence_established"
    )
    assert authorization["c8_fo1500_transformation_authorized"] == (
        equivalence[FO1500] == "equivalence_established"
    )
    assert authorization["c8_hsd_transformation_authorized"] is False
    assert authorization["c8_industry_conditioning_authorized"] is False
    assert authorization["c8_target_join_authorized"] is False
    assert authorization["c8_modeling_authorized"] is False
    assert authorization["c8_imputation_authorized"] is False
    assert authorization["c8_outcome_based_channel_selection_authorized"] is False
    assert authorization["c8_simultaneous_additive_fuel_oil_use_authorized"] is False
    assert authorization["c8_locked_test_evaluation_authorized"] is False


FORBIDDEN_IMPORT_MODULES = {
    "modeling", "evaluation", "features", "targets", "structure", "build_panel",
    "sklearn", "joblib", "statsmodels",
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


def test_c7_5_modules_import_no_target_evaluation_or_model_code():
    package = ROOT / "src" / "thai_supply_chain_ews" / "data"
    for name in ("eppo_product_semantics", "eppo_aggregation_contract"):
        source = (package / f"{name}.py").read_text(encoding="utf-8")
        assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES), name


def test_the_runner_touches_no_model_evaluation_or_locked_test_artifact():
    source = (ROOT / "scripts" / "decide_c7_5_eppo_semantics.py").read_text(
        encoding="utf-8")
    assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES)
    for fragment in ("locked_test_predictions", "d1_development_predictions",
                     "d3_operational_predictions", "d4_operational_model_predictions",
                     "b4_walk_forward", "targets_table", "industry_month_panel",
                     "c3_commodity_exposure", "c4_wide_primary"):
        assert fragment not in source, fragment


@requires_run
def test_no_target_outcome_entered_the_semantic_decision():
    decision = _decision()
    for key, value in decision["provenance"].items():
        assert value is False, key
    assert decision["coverage_views"]["target_outcomes_read"] is False
    assert decision["equivalence"]["numeric_evidence_load_bearing"] is False


@requires_run
def test_upstream_c7_artifacts_are_unchanged():
    audit = json.loads(C7_AUDIT.read_text(encoding="utf-8"))
    assert audit["daily_table"]["rows"] == 3625
    assert audit["monthly_aggregation"]["rows"] == 195
    assert audit["approval"]["monthly_aggregation_contract_approved"] is False
    assert audit["denominator"]["valid_canonical_document_days"] == 1310
    assert _decision()["semantic_overlay"]["output"] != (
        "data/interim/c7_eppo_monthly_source.parquet"
    )
    assert _decision()["semantic_overlay"]["overwrites_c7_monthly_audit_artifact"] is False


@requires_parquet
def test_the_overlay_is_a_separate_file_from_the_c7_tables():
    assert SEMANTIC_PARQUET.name == "c7_5_eppo_monthly_semantic.parquet"
    assert C7_MONTHLY.is_file() and C7_DAILY.is_file()
    assert SEMANTIC_PARQUET != C7_MONTHLY


# ===========================================================================
# 12. Synthetic failures. Each must raise explicitly.
# ===========================================================================
def test_synthetic_equivalence_approved_from_numeric_similarity_only():
    with pytest.raises(PS.EquivalenceError, match="never establish"):
        PS.assert_not_numeric_only_equivalence([_numeric(), _numeric()])


def test_collapsing_whitespace_is_not_rewriting_a_label():
    assert PS.collapse_label("FO 600  2%S") == "FO 600 2%S"
    established = PS.evaluate_equivalence(_candidate())
    for spelling in ("FO 600  2%S", "FO 600 2%S"):
        identity = PS.canonical_identity(spelling, [established])
        assert identity["source_product_label_raw"] == spelling
        assert identity["canonical_product_id"] == FO600
        assert identity["label_variant_status"] == (
            "source_label_variant_equivalence_established"
        )


def test_synthetic_ordinals_stripped_without_provenance():
    stripped = _candidate(evidence=[_structural(), _numeric()])
    decision = PS.evaluate_equivalence(stripped)
    assert decision.decision != "equivalence_established"
    identity = PS.canonical_identity("FO 600  2%S", [decision])
    assert identity["canonical_product_id"] is None
    with pytest.raises(PS.EquivalenceError, match="never a rewrite"):
        PS.assert_raw_label_preserved(
            {"source_product_label_raw": "FO 600 2%S"}, "FO 600  2%S"
        )


def test_synthetic_different_sulphur_grades_merged():
    decision = PS.evaluate_equivalence(_candidate(label_b="FO 600  3.5%S"))
    assert decision.decision == "equivalence_rejected"
    assert "sulphur_grade_unchanged" in decision.failed_conditions


def test_synthetic_co_occurring_labels_merged():
    decision = PS.evaluate_equivalence(_candidate(co_occurring_documents=3))
    assert decision.decision != "equivalence_established"
    assert "labels_never_co_occur" in decision.failed_conditions
    identity = PS.canonical_identity("FO 600  2%S", [decision])
    assert identity["canonical_product_id"] is None


def test_synthetic_wrong_date_file_reassigned_silently():
    attempt = PS.classify_recovery(
        listing_date="2025-01-25", media_id=21759,
        channels_inspected=["wordpress_media_record"],
        attachment_retrievable=True, internal_date="2025-01-24",
    )
    assert attempt.status == "wrong_date_attachment_unresolved"
    assert attempt.recovered_effective_date is None
    with pytest.raises(AC.AggregationContractError):
        AC.assert_transformation_input_permitted(_month(
            aggregation_status="document_identity_unresolved",
            monthly_value_strict=None, coverage_complete=False,
        ))


def test_synthetic_one_missing_official_day_marked_complete():
    row = AC.monthly_contract_row(
        FO600, FO600, "2026-04",
        [("2026-04-01", 24.0, "FO 600 (1) 2%S")],
        discovered_days=2, unresolved_days=["2026-04-02"],
    )
    assert row.coverage_complete is False
    forced = row.to_dict()
    forced["aggregation_status"] = "approved_complete_inventory"
    with pytest.raises(AC.AggregationContractError, match="no strict value"):
        AC.assert_transformation_input_permitted(forced)


def test_synthetic_method_approval_read_as_full_coverage():
    with pytest.raises(AC.AggregationContractError, match="separate fields"):
        AC.assert_method_approval_is_not_coverage(
            True, False,
            "aggregation approved, so the series is complete across the window",
        )


def test_synthetic_null_h_diesel_month_transformed():
    row = _month(series_id=HSD, canonical_product_id=HSD, reference_month="2024-01",
                 aggregation_status="semantic_definition_gap",
                 monthly_value_strict=None, monthly_value_descriptive=None,
                 coverage_complete=False, approved_transformation_input=False)
    with pytest.raises(AC.AggregationContractError, match="gap must propagate"):
        AC.assert_transformation_input_permitted(row)


def test_synthetic_h_diesel_b7_substituted():
    with pytest.raises(PS.EquivalenceError):
        PS.SemanticEvidence(
            evidence_class="direct_semantic",
            kind="adjacent_values_close",
            statement="B7 tracks ordinary H-DIESEL closely",
            source="daily table",
        )
    assert PS.parse_fuel_oil_label("H-DIESEL B7") is None
    blend = PS.canonical_identity("H-DIESEL B7", [PS.evaluate_equivalence(_candidate())])
    assert blend["canonical_product_id"] is None


def test_synthetic_fuel_oils_averaged():
    with pytest.raises(AC.AggregationContractError, match="mutually exclusive"):
        AC.assert_no_additive_fuel_oil_aggregate(
            [FO600, FO1500], "average of the two fuel oils"
        )


def test_synthetic_target_mae_used_to_choose_a_fuel_oil_channel():
    assert CONFIG["shared_fuel_oil_channel"][
        "selection_by_target_performance_allowed"] is False
    assert AC.SHARED_CHANNEL_RULES[
        "channel_selection_by_target_performance_allowed"] is False
    with pytest.raises(AC.AggregationContractError):
        AC.assert_no_additive_fuel_oil_aggregate(
            [FO600, FO1500], "pick the channel with the lower development MAE"
        )


def test_synthetic_c7_monthly_artifact_overwritten():
    semantic_output = CONFIG["semantic_overlay"]["output"]
    assert semantic_output != "data/interim/c7_eppo_monthly_source.parquet"
    assert CONFIG["semantic_overlay"]["overwrites_c7_monthly_audit_artifact"] is False
    assert CONFIG["semantic_overlay"]["mutates_c7_raw_or_daily_artifacts"] is False
    source = (ROOT / "scripts" / "decide_c7_5_eppo_semantics.py").read_text(
        encoding="utf-8")
    assert "c7_eppo_monthly_source.parquet\", \"w" not in source
    assert "C7_MONTHLY, \"w" not in source
    assert "to_parquet(C7_MONTHLY" not in source
    assert "to_parquet(C7_DAILY" not in source
