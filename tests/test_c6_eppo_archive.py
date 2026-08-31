"""Task C6 tests — EPPO archive discovery, validation and availability.

The archive is easy to over-claim: 5,000 retrievable documents look like a
point-in-time source until you notice every upload timestamp comes from one
migration. Most of these tests exist to keep those two facts apart, and to stop
a filename, a guessed path or a search hit from standing in for provenance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.data import eppo_archive_discovery as DISC
from thai_supply_chain_ews.data import eppo_archive_inventory as INV
from thai_supply_chain_ews.data import eppo_availability as AVAIL
from thai_supply_chain_ews.data import eppo_price_structure as EPS

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "eppo_ex_refinery_archive.yaml").read_text(encoding="utf-8")
)
AUDIT = ROOT / "docs" / "c6_eppo_archive_audit.json"
requires_run = pytest.mark.skipif(not AUDIT.is_file(), reason="C6 has not been run")


def _audit():
    return json.loads(AUDIT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. C5 granted an audit, not an approval
# ---------------------------------------------------------------------------
def test_c5_designation_is_audit_only():
    designation = CONFIG["c5_designation"]
    assert designation["source_selected_for_c6_audit"] is True
    assert designation["historical_archive_verified"] is False
    assert designation["point_in_time_supported"] is False
    assert designation["feature_semantics_approved"] is False
    assert designation["model_feature_approved"] is False


def test_provenance_flags_declare_no_target_or_model_contact():
    provenance = CONFIG["provenance"]
    for key in ("selection_used_target_outcomes", "d4_metrics_used_for_source_ranking",
                "target_joined", "model_trained", "locked_test_accessed",
                "model_feature_approved"):
        assert provenance[key] is False, key


def test_preserved_decisions_declared():
    for key, value in CONFIG["preserved_decisions"].items():
        assert value is False, key


# ---------------------------------------------------------------------------
# 2. Discovery provenance
# ---------------------------------------------------------------------------
def test_guessed_paths_and_search_hits_are_not_official_discovery():
    assert DISC.is_official_discovery("official_wordpress_rest") is True
    assert DISC.is_official_discovery("official_attachment_href") is True
    assert DISC.is_official_discovery("pattern_probe") is False
    assert DISC.is_official_discovery("search_engine_seed_only") is False
    assert "pattern_probe" not in DISC.OFFICIAL_METHODS
    assert "search_engine_seed_only" not in DISC.OFFICIAL_METHODS


def test_unknown_discovery_method_raises():
    with pytest.raises(DISC.DiscoveryError):
        DISC.is_official_discovery("found_it_somewhere")


def test_config_marks_non_official_methods():
    assert set(CONFIG["discovery"]["non_official_methods"]) == {
        "search_engine_seed_only", "pattern_probe"
    }
    assert CONFIG["discovery"]["guessed_path_counts_as_discovery"] is False
    assert CONFIG["discovery"]["first_spreadsheet_link_selected_blindly"] is False


def test_filename_effective_date_parsing():
    assert DISC.parse_filename_effective_date("pt-price-st-2022-1-4.xlsx") == "2022-01-04"
    assert DISC.parse_filename_effective_date("pt-price-st-2026-8-28.xlsx") == "2026-08-28"
    assert DISC.parse_filename_effective_date("retail-2018-06-30.xls") is None
    assert DISC.parse_filename_effective_date("") is None


def test_attachments_are_ranked_not_taken_in_encounter_order():
    """The first spreadsheet link is not automatically the right one."""
    candidates = [
        "https://x/other.xlsx",
        "https://x/pt-price-st-2022-3-9.xlsx",
        "https://x/pt-price-st-2022-3-1.xlsx",
    ]
    ranked = DISC.rank_attachment_candidates(candidates, "2022-03-09")
    assert ranked[0]["filename"] == "pt-price-st-2022-3-9.xlsx"
    assert ranked[0]["rank_reason"] == "filename_date_matches_item_date"
    assert len(ranked) == 3, "all candidate links must be preserved"


def test_pagination_stops_on_each_bounded_terminal_condition():
    calls = {"n": 0}

    def empty_after_two(url, timeout=90, method="GET"):
        calls["n"] += 1
        if calls["n"] <= 2:
            name = f"a/pt-price-st-2022-1-{calls['n']}.xlsx"
            body = json.dumps([{"id": calls["n"], "source_url": name}])
            return body.encode(), 200, {}
        return b"[]", 200, {}

    docs, termination = DISC.walk_rest_media(fetch_fn=empty_after_two)
    assert termination == "empty_page_at_3"
    assert len(docs) == 2


def test_pagination_stops_on_documented_api_termination():
    def four_hundred(url, timeout=90, method="GET"):
        return b"", 400, {}

    docs, termination = DISC.walk_rest_media(fetch_fn=four_hundred)
    assert termination == "api_termination_400_at_page_1"
    assert docs == []


def test_cyclic_pagination_is_detected():
    """Synthetic failure: cyclic pagination."""
    def same_page(url, timeout=90, method="GET"):
        body = json.dumps([{"id": 1, "source_url": "a/pt-price-st-2022-1-4.xlsx"}])
        return body.encode(), 200, {}

    docs, termination = DISC.walk_rest_media(fetch_fn=same_page)
    assert termination.startswith("repeated_content_at_page_")
    assert len(docs) == 1


@requires_run
def test_recorded_termination_is_a_bounded_condition():
    discovery = _audit()["discovery"]
    assert discovery["termination"].startswith(
        ("empty_page_at_", "repeated_content_at_page_", "api_termination_400_at_page_")
    )
    assert discovery["guessed_paths_counted"] == 0
    assert discovery["search_engine_seeds_counted"] == 0


# ---------------------------------------------------------------------------
# 3. Document validation against its own content
# ---------------------------------------------------------------------------
def test_magic_bytes_decide_format_not_the_extension():
    assert EPS.detect_magic(b"PK\x03\x04rest") == "xlsx_zip"
    assert EPS.detect_magic(b"\xd0\xcf\x11\xe0rest") == "xls_ole2"
    assert EPS.detect_magic(b"<!DOCTYPE html><html>") == "html_masquerade"
    assert EPS.detect_magic(b"random") == "unknown"


def test_html_served_as_a_document_is_rejected():
    """Synthetic failure: an HTML WAF page returned with HTTP 200."""
    result = EPS.validate_document(
        b"<!DOCTYPE html><html><body>Access denied</body></html>", "x.xlsx", "2022-01-04"
    )
    assert result["valid"] is False
    assert result["html_masquerade"] is True
    assert result["rejection_reason"] == "html_page_served_as_document"


def test_zero_byte_file_is_rejected():
    result = EPS.validate_document(b"", "x.xlsx", "2022-01-04")
    assert result["valid"] is False
    assert result["rejection_reason"] == "zero_byte_file"


class _Doc:
    def __init__(self, title="PRICE STRUCTURE OF PETROLEUM PRODUCTS",
                 date="2022-01-04", observations=None, regime="xlsx_2023"):
        self.internal_title = title
        self.embedded_document_date = date
        self.layout_regime = regime
        self.observations = observations if observations is not None else [
            EPS.ProductObservation("eppo_ex_refinery_hsd", "H-DIESEL", "H-DIESEL",
                                   ex_refinery=21.7)
        ]


def test_wrong_dated_attachment_is_rejected():
    """Synthetic failure: a detail page linking to the wrong dated document."""
    result = EPS.validate_document(
        b"PK\x03\x04", "x.xlsx", "2022-01-04", parsed=_Doc(date="2022-01-05")
    )
    assert result["valid"] is False
    assert result["rejection_reason"].startswith("wrong_date_attachment")


def test_non_price_structure_document_is_rejected():
    result = EPS.validate_document(
        b"PK\x03\x04", "x.xlsx", "2022-01-04", parsed=_Doc(title="ANNUAL REPORT")
    )
    assert result["valid"] is False
    assert result["rejection_reason"] == "internal_title_is_not_a_price_structure"


def test_formula_template_without_observations_is_rejected():
    empty = EPS.ProductObservation("eppo_ex_refinery_hsd", "H-DIESEL", "H-DIESEL",
                                   ex_refinery=None)
    result = EPS.validate_document(
        b"PK\x03\x04", "x.xlsx", "2022-01-04", parsed=_Doc(observations=[empty])
    )
    assert result["valid"] is False
    assert result["rejection_reason"] == "formula_template_without_observations"


def test_document_with_no_audited_products_is_rejected():
    result = EPS.validate_document(
        b"PK\x03\x04", "x.xlsx", "2022-01-04", parsed=_Doc(observations=[])
    )
    assert result["valid"] is False
    assert result["rejection_reason"] == "no_audited_product_observations"


@requires_run
def test_wrong_date_attachments_were_actually_caught():
    reasons = _audit()["retrieval_and_validation"]["rejection_reasons"]
    assert any(r.startswith("wrong_date_attachment") for r in reasons)


# ---------------------------------------------------------------------------
# 4. Product identity and substitution
# ---------------------------------------------------------------------------
def test_label_normalization_keeps_distinct_products_distinct():
    assert EPS.normalize_label("H-DIESEL ") == "H-DIESEL"
    assert EPS.normalize_label("H-DIESEL") == "H-DIESEL"
    assert EPS.normalize_label("H-DIESEL  B20") == "H-DIESEL B20"
    assert EPS.normalize_label("H-DIESEL B7") != EPS.normalize_label("H-DIESEL")
    assert EPS.normalize_label("H-DIESEL B10") != EPS.normalize_label("H-DIESEL")


@pytest.mark.parametrize("blend", ["H-DIESEL B7", "H-DIESEL B10", "H-DIESEL B20"])
def test_diesel_blends_are_not_the_plain_hsd_series(blend):
    """Synthetic failure: a diesel definition break silently substituted."""
    assert EPS.normalize_label(blend) not in EPS.AUDITED_PRODUCTS
    assert EPS.AUDITED_PRODUCTS[EPS.normalize_label("H-DIESEL")] == "eppo_ex_refinery_hsd"


def test_fuel_oil_grades_are_not_interchangeable():
    """Synthetic failure: a fuel-oil grade substitution."""
    fo600 = EPS.AUDITED_PRODUCTS["FO 600 (1) 2%S"]
    fo1500 = EPS.AUDITED_PRODUCTS["FO 1500 (2) 2%S"]
    assert fo600 != fo1500
    assert EPS.normalize_label("FO 600 (1) 1%S") not in EPS.AUDITED_PRODUCTS


def test_forbidden_substitutions_are_declared():
    forbidden = CONFIG["forbidden_substitutions"]
    assert "wholesale_or_retail_for_ex_refinery" in forbidden
    assert "lpg_baht_per_kg_for_petroleum_baht_per_litre" in forbidden
    assert "diesel_blend_for_another_diesel_definition" in forbidden
    assert "fuel_oil_sulphur_grade_for_another" in forbidden


def test_price_stage_columns_stay_distinct():
    """Synthetic failure guard: swapped wholesale and ex-refinery columns."""
    assert "ex_refinery" in EPS.PRICE_STAGE_COLUMNS
    assert "wholesale" in EPS.PRICE_STAGE_COLUMNS
    assert EPS.PRICE_STAGE_COLUMNS.index("ex_refinery") != (
        EPS.PRICE_STAGE_COLUMNS.index("wholesale")
    )
    observation = EPS.ProductObservation(
        "eppo_ex_refinery_hsd", "H-DIESEL", "H-DIESEL",
        ex_refinery=21.7, wholesale=27.7,
    )
    assert observation.ex_refinery != observation.wholesale


@requires_run
def test_only_baht_per_litre_series_are_audited():
    audit = _audit()
    for regime in audit["semantic_regimes"]:
        assert regime["series_id"] in CONFIG["audited_products"]
    assert "LPG" not in json.dumps(audit["semantic_regimes"])


@requires_run
def test_semantic_regimes_are_recorded_per_layout():
    regimes = _audit()["semantic_regimes"]
    layouts = {r["layout_regime"] for r in regimes}
    assert layouts == {"xls_2021", "xlsx_2023"}
    for regime in regimes:
        assert regime["regime_start"] <= regime["regime_end"]
        assert regime["exact_label"]


@requires_run
def test_hsd_gap_is_not_filled_by_a_blend():
    """The plain H-DIESEL series has fewer observations; blends never fill it."""
    regimes = {(r["series_id"], r["layout_regime"]): r for r in _audit()["semantic_regimes"]}
    hsd = regimes[("eppo_ex_refinery_hsd", "xlsx_2023")]
    fo600 = regimes[("eppo_ex_refinery_fo600_2s", "xlsx_2023")]
    assert hsd["observations"] < fo600["observations"]
    assert EPS.normalize_label(hsd["exact_label"]) == "H-DIESEL"


# ---------------------------------------------------------------------------
# 5. Revisions vs ordinary price movement
# ---------------------------------------------------------------------------
def test_price_movement_across_dates_is_not_a_revision():
    """Synthetic failure: a revision confused with ordinary daily movement."""
    assert INV.classify_revision([
        {"value": 21.0, "semantic_regime_id": "r", "source_document_sha256": "a"},
    ]) == "single_vintage_only"
    revision = CONFIG["revision"]
    assert revision["price_change_between_different_effective_dates_is_a_revision"] is False
    assert revision["comparison_key"] == [
        "series_id", "effective_date", "semantic_regime_id"
    ]


def test_same_date_changed_value_is_a_revision():
    assert INV.classify_revision([
        {"value": 21.0, "semantic_regime_id": "r", "source_document_sha256": "a"},
        {"value": 22.0, "semantic_regime_id": "r", "source_document_sha256": "b"},
    ]) == "same_date_revised_value"


def test_same_date_same_value_and_duplicates_are_distinguished():
    assert INV.classify_revision([
        {"value": 21.0, "semantic_regime_id": "r", "source_document_sha256": "a"},
        {"value": 21.0, "semantic_regime_id": "r", "source_document_sha256": "b"},
    ]) == "same_date_same_value"
    assert INV.classify_revision([
        {"value": 21.0, "semantic_regime_id": "r", "source_document_sha256": "a"},
        {"value": 21.0, "semantic_regime_id": "r", "source_document_sha256": "a"},
    ]) == "duplicate_document"


def test_cross_regime_comparison_is_incomparable():
    assert INV.classify_revision([
        {"value": 21.0, "semantic_regime_id": "r1", "source_document_sha256": "a"},
        {"value": 22.0, "semantic_regime_id": "r2", "source_document_sha256": "b"},
    ]) == "incomparable_definition"


@requires_run
def test_reported_revisions_use_the_same_date_key_only():
    revisions = _audit()["revisions"]
    assert revisions["price_change_between_dates_counted_as_revision"] is False
    assert set(revisions["class_counts"]) <= set(INV.REVISION_CLASSES)


# ---------------------------------------------------------------------------
# 6. Availability evidence
# ---------------------------------------------------------------------------
def test_migration_timestamp_never_becomes_availability():
    """Synthetic failure: migration timestamp used as availability."""
    assessment = AVAIL.assess_issue_availability(
        effective_date="2022-01-04", migration_upload_date="2026-04-15"
    )
    assert assessment.availability_evidence_status == "migration_timestamp_only"
    assert assessment.available_as_of is None
    assert assessment.available_as_of_verified is False
    assert assessment.historical_point_in_time_value_supported is False


def test_reference_date_alone_does_not_prove_availability():
    assessment = AVAIL.assess_issue_availability(effective_date="2022-01-04")
    assert assessment.availability_evidence_status == "reference_date_only"
    assert assessment.historical_point_in_time_value_supported is False


def test_independent_capture_corroborates_availability():
    assessment = AVAIL.assess_issue_availability(
        effective_date="2022-06-06", independent_capture_date="2022-06-10",
        migration_upload_date="2026-04-15",
    )
    assert assessment.availability_evidence_status == "attachment_timestamp_corroborated"
    assert assessment.available_as_of == "2022-06-10"
    assert assessment.historical_point_in_time_value_supported is True


def test_capture_before_effective_date_is_incoherent_and_rejected():
    assessment = AVAIL.assess_issue_availability(
        effective_date="2022-06-06", independent_capture_date="2022-06-01"
    )
    assert assessment.availability_evidence_status == "unresolved"
    assert assessment.historical_point_in_time_value_supported is False


def test_supporting_statuses_exclude_migration_and_reference_only():
    assert "migration_timestamp_only" not in AVAIL.SUPPORTING_STATUSES
    assert "reference_date_only" not in AVAIL.SUPPORTING_STATUSES
    assert "attachment_last_modified_only" not in AVAIL.SUPPORTING_STATUSES


def test_dataset_status_full_requires_every_observation():
    """Synthetic failure: an incomplete archive promoted to full."""
    supported = AVAIL.assess_issue_availability("2022-06-06", independent_capture_date="2022-06-10")
    unsupported = AVAIL.assess_issue_availability("2022-06-07", migration_upload_date="2026-04-15")
    assert AVAIL.dataset_point_in_time_status([supported])["status"] == "full"
    assert AVAIL.dataset_point_in_time_status([supported, unsupported])["status"] == "partial"
    assert AVAIL.dataset_point_in_time_status([unsupported])["status"] == "not_supported"


@requires_run
def test_reported_point_in_time_status_matches_its_evidence():
    availability = _audit()["availability"]["point_in_time"]
    assert availability["status"] in AVAIL.POINT_IN_TIME_STATUSES
    if availability["status"] == "full":
        assert availability["supported"] == availability["total"]
    if availability["supported"] == 0:
        assert availability["status"] == "not_supported"


# ---------------------------------------------------------------------------
# 7. Coverage, schedule and transformation prehistory
# ---------------------------------------------------------------------------
def test_weekend_gap_is_not_a_missing_issue():
    status = INV.classify_gap("2022-01-08", ["2022-01-07"], schedule_verified=True)
    assert status == "weekend"


def test_unverified_schedule_yields_schedule_unresolved():
    """Synthetic failure guard: an unresolved schedule reported as missing."""
    status = INV.classify_gap("2022-01-06", ["2022-01-07"], schedule_verified=False)
    assert status == "schedule_unresolved"
    assert INV.classify_gap("2022-01-06", ["2022-01-07"], schedule_verified=True) == (
        "possible_missing_issue"
    )


def test_expected_issue_count_is_null_when_schedule_unverified():
    issues = [INV.ArchiveIssue(effective_date="2022-01-04", validation_status="valid")]
    coverage = INV.monthly_coverage(issues, "2022-01", "2022-01", schedule_verified=False)
    assert coverage[0]["expected_issue_count"] is None
    assert coverage[0]["has_at_least_one_valid_observation"] is True
    assert coverage[0]["complete_monthly_aggregation_defensible"] is False


def test_twelve_month_change_needs_2021_prehistory():
    """Synthetic failure: 2022 coverage claimed sufficient for 12-month parity."""
    from_2022 = AVAIL.transformation_eligibility("2022-01-03", "2022-01-01", 12)
    assert from_2022["eligible"] is False
    assert from_2022["earliest_source_date_needed"].startswith("2021-01")
    from_2021 = AVAIL.transformation_eligibility("2021-01-04", "2022-01-01", 12)
    assert from_2021["eligible"] is True


def test_level_price_needs_no_prehistory():
    assert AVAIL.transformation_eligibility("2022-01-03", "2022-01-01", 0)["eligible"] is True


@requires_run
def test_both_required_windows_are_reported_separately():
    windows = _audit()["required_windows"]
    assert set(windows) == {"operational_level_price", "transformation_parity"}
    assert windows["transformation_parity"]["start"] == "2021-01-01"
    assert windows["operational_level_price"]["start"] == "2022-01-01"


@requires_run
def test_transformation_eligibility_is_reported_per_transformation():
    eligibility = _audit()["transformation_eligibility"]
    assert set(eligibility) == set(CONFIG["transformation_prehistory_months"])
    for name, entry in eligibility.items():
        assert "eligible" in entry and "months_of_prehistory_needed" in entry
        assert entry["months_of_prehistory_needed"] == (
            CONFIG["transformation_prehistory_months"][name]
        )


# ---------------------------------------------------------------------------
# 8. Operational boundary and aggregation
# ---------------------------------------------------------------------------
def test_observation_after_the_issue_date_raises():
    """Synthetic failure: a post-issue observation entering aggregation."""
    AVAIL.assert_not_after_issue_date("2024-01-30", "2024-01-31")
    with pytest.raises(AVAIL.AvailabilityError):
        AVAIL.assert_not_after_issue_date("2024-02-01", "2024-01-31")


def test_completed_reference_month_is_t_minus_one():
    assert AVAIL.completed_reference_month("2024-01") == "2023-12"
    assert AVAIL.completed_reference_month("2024-12") == "2024-11"


def test_aggregation_contract_defaults_to_the_completed_month():
    aggregation = CONFIG["monthly_aggregation"]
    assert aggregation["default_reference_month"] == "completed_t_minus_1"
    assert aggregation["same_month_partial_aggregation_permitted"] is False
    assert aggregation["observations_after_issue_date_permitted"] is False
    assert aggregation["production_table_created_in_c6"] is False
    assert aggregation["selected_from_predictive_performance"] is False


@requires_run
def test_no_aggregation_rule_is_approved_yet():
    assert _audit()["eligibility"]["monthly_aggregation_contract_approved"] is False


# ---------------------------------------------------------------------------
# 9. Output discipline
# ---------------------------------------------------------------------------
@requires_run
def test_canonical_table_is_labelled_partial():
    table = _audit()["canonical_table"]
    assert table["is_partial_audit_table"] is True
    assert "not a production feature table" in table["label"]
    assert table["unique_key"] == ["series_id", "effective_date", "semantic_regime_id"]


@requires_run
def test_canonical_rows_are_unique_and_ordered():
    path = ROOT / "data" / "interim" / "c6_eppo_source_observations.parquet"
    if not path.is_file():
        pytest.skip("observation table not built")
    import pandas as pd

    frame = pd.read_parquet(path)
    key = ["series_id", "effective_date", "semantic_regime_id"]
    assert not frame.duplicated(subset=key).any()
    ordered = frame.sort_values(key, kind="mergesort").reset_index(drop=True)
    pd.testing.assert_frame_equal(frame, ordered)
    assert set(frame["unit"]) == {"BAHT/LITRE"}
    assert set(frame["price_stage"]) == {"ex_refinery"}


@requires_run
def test_no_feature_transformation_column_exists():
    path = ROOT / "data" / "interim" / "c6_eppo_source_observations.parquet"
    if not path.is_file():
        pytest.skip("observation table not built")
    import pandas as pd

    columns = [c.lower() for c in pd.read_parquet(path).columns]
    for forbidden in ("log_change", "volatility", "zscore", "shock",
                      "industry_id", "mpi", "stress"):
        assert not any(forbidden in c for c in columns), forbidden
    # match "lag" as a whole token, so quality_flag does not trip it
    assert not any(c == "lag" or c.endswith("_lag") or c.startswith("lag_")
                   for c in columns)


def test_runner_imports_no_model_or_evaluation_module():
    source = (ROOT / "scripts" / "audit_c6_eppo_archive.py").read_text(encoding="utf-8")
    for forbidden in ("modeling", "operational_walk_forward", "residual_ridge",
                      "load_b3_artifacts", "locked_test", "predict_baseline"):
        assert forbidden not in source, forbidden


def test_no_target_join_in_the_modules():
    import inspect
    for module in (DISC, EPS, INV, AVAIL):
        source = inspect.getsource(module)
        for forbidden in ("target_raw_value", "observed_score", "mpi_adverse_yoy"):
            assert forbidden not in source, f"{module.__name__} touches {forbidden}"


@requires_run
def test_outcome_is_one_of_the_declared_values():
    assert _audit()["outcome"] in CONFIG["outcomes"]
    assert CONFIG["force_positive_result"] is False


@requires_run
def test_eligibility_never_claims_feature_approval():
    eligibility = _audit()["eligibility"]
    assert eligibility["feature_semantics_approved"] is False
    assert eligibility["model_feature_approved"] is False


@pytest.mark.parametrize("name", ["eppo_archive_issue", "eppo_ex_refinery_observation"])
def test_schema_parses_and_declares_task(name):
    schema = yaml.safe_load(
        (ROOT / "schemas" / f"{name}.schema.yaml").read_text(encoding="utf-8")
    )
    assert schema["task"] == "C6"
    assert schema["schema_version"] == 1
