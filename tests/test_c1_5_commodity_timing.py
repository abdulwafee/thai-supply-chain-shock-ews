"""Task C1.5 — publication timing, first-release extraction, and revision audit.

FIXTURE POLICY: synthetic issues are TEST FIXTURES using round, implausible
numbers. Tests reading real artifacts are named "real_" or "snapshot".

Synthetic failure tests deliberately construct incorrect PDF month alignment, an
issue dated before its reference month is complete, a later vintage offered as a
first release, a revision hidden as rounding, same-month approval without an
issuance date, and a future-published value used at a forecast origin. Each must
fail explicitly.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.data import commodity_timing as CT  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import world_bank_pink_sheet_vintages as V  # noqa: E402

AUDIT_JSON = ROOT / "docs" / "c1_5_commodity_timing_audit.json"
CONFIG = CT.load_timing_config()

GUARDED = {
    "b1_panel": ROOT / "data" / "processed" / "industry_month_panel.parquet",
    "b3_monthly": ROOT / "data" / "targets" / "production_stress_month.parquet",
    "b3_labels": ROOT / "data" / "targets" / "forecast_target_raw.parquet",
    "b4_predictions": ROOT / "data" / "model_input" / "b4_walk_forward_predictions.parquet",
    "c1_table": ROOT / "data" / "interim" / "commodity_month.parquet",
}


def audit() -> dict:
    if not AUDIT_JSON.is_file():
        pytest.skip("run scripts/audit_c1_5_commodity_timing.py first")
    return json.loads(AUDIT_JSON.read_text(encoding="utf-8"))


# --- synthetic issue fixture -------------------------------------------------


@dataclass
class FakeIssue:
    """TEST FIXTURE standing in for a parsed PinkSheetIssue."""

    issue_name: str
    issue_month: str
    issue_date: str | None
    url: str = "https://example.invalid/fixture.pdf"
    monthly_reference_months: tuple = ()
    observations: dict = None

    def __post_init__(self):
        if self.observations is None:
            self.observations = {}

    @property
    def latest_reference_month(self) -> str | None:
        # Mirrors PinkSheetIssue: the newest monthly column, in order.
        months = list(self.monthly_reference_months)
        return months[-1] if months else None


def make_issue(issue_month: str, issue_date: str | None, months: list[str]) -> FakeIssue:
    return FakeIssue(
        issue_name=f"ISSUE-{issue_month}",
        issue_month=issue_month,
        issue_date=issue_date,
        monthly_reference_months=months,
    )


# --- discovery ---------------------------------------------------------------


def test_official_issue_discovery_from_html():
    html = """
      <a href="https://thedocs.worldbank.org/en/doc/abc-1/related/CMO-Pink-Sheet-July-2026.pdf">Jul</a>
      <a href="https://thedocs.worldbank.org/en/doc/abc-1/related/CMO-Pink-Sheet-August-2026.pdf">Aug</a>
    """
    found = V.discover_issue_urls(html)
    assert [f["issue_month"] for f in found] == ["2026-07-01", "2026-08-01"]
    assert found[0]["issue_name"] == "CMO-Pink-Sheet-July-2026"


def test_duplicate_issue_links_are_deduplicated():
    url = "https://thedocs.worldbank.org/en/doc/abc-1/related/CMO-Pink-Sheet-July-2026.pdf"
    html = f'<a href="{url}">a</a><a href="{url}">b</a>'
    found = V.discover_issue_urls(html)
    assert len(found) == 1


def test_discovery_finds_nothing_when_no_issues_are_linked():
    assert V.discover_issue_urls("<html><body>no pink sheets here</body></html>") == []


def test_real_discovery_labels_probed_issues_separately():
    """C1.5-R1: with the official detail/RELATED pages parsed, no pattern probe
    is needed at all. A probe must never be counted as official discovery.
    """
    output = audit()
    discovery = output["discovery"]
    assert discovery["construct_urls_from_guessed_hash"] is False
    by_method = discovery["by_method"]
    assert by_method["official_related_href"] >= 60
    assert by_method["official_detail_main_document"] >= 1
    assert by_method["pattern_probe_within_discovered_folder"] == 0
    entries = SM.read_manifest("WB_PINKSHEET_VINTAGES")
    methods = {e["url_discovery_method"] for e in entries}
    assert methods <= set(V.DISCOVERY_METHODS)
    assert "pattern_probe_within_discovered_folder" not in methods


# --- PDF issue-date extraction ----------------------------------------------


def test_pdf_issue_date_extraction():
    assert V.parse_pdf_creation_date("D:20260804131056-04'00'") == date(2026, 8, 4)
    assert V.parse_pdf_creation_date("D:20260602084933-04'00'") == date(2026, 6, 2)
    assert V.parse_pdf_creation_date("not a date") is None


def test_real_issue_dates_come_from_the_pdf_not_the_download():
    output = audit()
    downloads = {str(e.get("retrieved_at"))[:10] for e in SM.read_manifest(
        "WB_PINKSHEET_VINTAGES"
    )}
    dated = [r for r in output["expected_issue_inventory"]
             if r["internal_pdf_creation_date"]]
    assert len(dated) >= 60
    for row in dated:
        # the issue's own creation date must precede the download date
        assert row["internal_pdf_creation_date"] < min(downloads) or (
            row["internal_pdf_creation_date"] not in downloads
        )
        assert row["document_date"] == row["internal_pdf_creation_date"]


def test_download_timestamp_is_never_used_as_availability():
    output = audit()
    downloads = {e.get("retrieved_at") for e in SM.read_manifest("WB_PINKSHEET_VINTAGES")}
    for row in output["publication_timing"]:
        if row["first_seen_issue_date"]:
            assert row["first_seen_issue_date"] not in {str(d)[:10] for d in downloads}


# --- month alignment ---------------------------------------------------------


def test_month_header_alignment_on_a_valid_fixture():
    text = (
        "World Bank Commodities Price Data\n"
        "Jan-Dec Jan-Dec Apr-Jun May June July\n"
        "Unit 2023 2024 2026 2026 2026 2026\n"
        "Crude oil, Brent $/bbl a/ 82.6 80.7 67.8 107.5 85.4 83.4\n"
    )
    months = V._parse_monthly_headers(text, date(2026, 8, 1))
    assert months == ["2026-05-01", "2026-06-01", "2026-07-01"]


def test_incorrect_month_alignment_is_rejected_when_a_column_is_an_aggregate():
    """Synthetic: the trailing column is a quarter, not a month."""
    text = (
        "hdr\nJan-Dec May June Jul-Sep\nUnit 2023 2026 2026 2026\nCrude oil, Brent $/bbl 1 2 3 4\n"
    )
    with pytest.raises(V.MonthAlignmentError, match="aggregate"):
        V._parse_monthly_headers(text, date(2026, 8, 1))


def test_issue_dated_before_its_reference_month_is_complete_is_rejected():
    """Synthetic: a June issue claiming June data — June is not complete yet."""
    text = (
        "hdr\nJan-Dec April May June\nUnit 2023 2026 2026 2026\nCrude oil, Brent $/bbl 1 2 3 4\n"
    )
    with pytest.raises(V.MonthAlignmentError, match="not\\s+yet complete"):
        V._parse_monthly_headers(text, date(2026, 6, 1))


def test_non_chronological_month_columns_are_rejected():
    text = (
        "hdr\nJan-Dec July June May\nUnit 2023 2026 2026 2026\nCrude oil, Brent $/bbl 1 2 3 4\n"
    )
    with pytest.raises(V.MonthAlignmentError, match="chronological"):
        V._parse_monthly_headers(text, date(2026, 8, 1))


def test_missing_header_rows_are_rejected():
    with pytest.raises(V.MonthAlignmentError, match="header rows"):
        V._parse_monthly_headers("just some text\nno unit row\n", date(2026, 8, 1))


def test_month_name_parsing():
    assert V.month_name_to_number("July") == 7
    assert V.month_name_to_number("jul") == 7
    with pytest.raises(V.MonthAlignmentError):
        V.month_name_to_number("Smarch")


# --- earliest-issue selection ------------------------------------------------


def test_earliest_issue_is_selected_as_first_release():
    early = make_issue("2026-06-01", "2026-06-02", ["2026-03-01", "2026-04-01", "2026-05-01"])
    late = make_issue("2026-07-01", "2026-07-01", ["2026-04-01", "2026-05-01", "2026-06-01"])
    chosen = V.select_first_release_issue([late, early], "2026-05-01")
    assert chosen.issue_month == "2026-06-01"


def test_later_vintage_is_never_returned_as_first_release():
    """Synthetic: pass the issues in reverse order; the later one must not win."""
    early = make_issue("2026-06-01", "2026-06-02", ["2026-05-01"])
    later = make_issue("2026-08-01", "2026-08-04", ["2026-05-01"])
    for ordering in ([early, later], [later, early]):
        assert V.select_first_release_issue(ordering, "2026-05-01").issue_month == "2026-06-01"


def test_missing_issue_returns_none_rather_than_a_substitute():
    issues = [make_issue("2026-08-01", "2026-08-04", ["2026-07-01"])]
    assert V.select_first_release_issue(issues, "2024-01-01") is None


# --- reference-month to availability mapping --------------------------------


def test_true_first_release_versus_upper_bound():
    """An issue two months later than t+1 gives an UPPER BOUND, not a delay."""
    issues = [make_issue("2026-07-01", "2026-07-01", ["2026-04-01", "2026-05-01", "2026-06-01"])]
    rows = CT.build_publication_timing_table(["2026-04-01", "2026-06-01"], issues)
    by_month = {r.reference_month: r for r in rows}
    assert by_month["2026-06-01"].is_true_first_release is True
    assert by_month["2026-06-01"].availability_status == "verified_from_archived_issue"
    assert by_month["2026-04-01"].is_true_first_release is False
    assert by_month["2026-04-01"].availability_status == "upper_bound_only"


def test_upper_bound_rows_are_excluded_from_delay_statistics():
    issues = [make_issue("2026-07-01", "2026-07-01", ["2026-04-01", "2026-05-01", "2026-06-01"])]
    rows = CT.build_publication_timing_table(["2026-04-01", "2026-06-01"], issues)
    stats = CT.publication_delay_stats(rows)
    assert stats["verified_months"] == 1
    assert stats["upper_bound_only_months"] == 1
    assert stats["max_delay_days"] == 1  # 2026-06-30 -> 2026-07-01


def test_publication_delay_calculation():
    issues = [make_issue("2026-08-01", "2026-08-04", ["2026-07-01"])]
    rows = CT.build_publication_timing_table(["2026-07-01"], issues)
    assert rows[0].calendar_delay_days == 4  # 2026-07-31 -> 2026-08-04
    assert rows[0].available_month == "2026-08-01"


def test_missing_months_are_recorded_not_interpolated():
    issues = [make_issue("2026-08-01", "2026-08-04", ["2026-07-01"])]
    rows = CT.build_publication_timing_table(["2024-01-01", "2026-07-01"], issues)
    missing = next(r for r in rows if r.reference_month == "2024-01-01")
    assert missing.availability_status == "no_archived_issue"
    assert missing.calendar_delay_days is None
    assert missing.first_seen_issue_date is None
    assert "not_interpolated" in missing.quality_flag


def test_issue_without_a_publication_date_is_not_given_one():
    issues = [make_issue("2026-08-01", None, ["2026-07-01"])]
    rows = CT.build_publication_timing_table(["2026-07-01"], issues)
    assert rows[0].availability_status == "issue_found_publication_date_missing"
    assert rows[0].calendar_delay_days is None
    assert "not_inferred" in rows[0].quality_flag


def test_month_end_helper():
    assert CT.month_end("2026-05-01") == date(2026, 5, 31)
    assert CT.month_end("2026-02-01") == date(2026, 2, 28)
    assert CT.month_end("2024-02-01") == date(2024, 2, 29)
    assert CT.month_end("2026-12-01") == date(2026, 12, 31)


# --- forecast-origin cutoff --------------------------------------------------


def test_same_month_use_is_rejected_without_verified_issuance_timing():
    assert CONFIG["same_reference_month_available_at_calendar_origin"] is False
    assert CONFIG["lag_zero_prohibited"] is True
    assert CONFIG["operational_release_contract_supported"] is False
    assert CONFIG["forecast_issuance_contract"] == "calendar_boundary_month_based"
    output = audit()
    decisions = output["timing_decisions"]
    assert decisions["same_reference_month_available_at_calendar_origin"] is False
    assert decisions["lag_zero_prohibited"] is True


def test_month_t_is_published_during_month_t_plus_1_not_within_month_t():
    """The structural fact that makes same-month use impossible."""
    output = audit()
    verified = [
        r for r in output["publication_timing"]
        if r["availability_status"] == "verified_from_archived_issue"
    ]
    assert verified, "expected at least one verified month"
    for row in verified:
        assert row["calendar_delay_days"] > 0
        assert row["available_month"] > row["reference_month"]


def test_future_published_value_cannot_be_used_at_an_earlier_origin():
    """Synthetic leakage attempt: a value published in t+1 offered at origin t."""
    issues = [make_issue("2026-08-01", "2026-08-04", ["2026-07-01"])]
    rows = CT.build_publication_timing_table(["2026-07-01"], issues)
    row = rows[0]
    origin = "2026-07-01"  # forecast origin inside the reference month
    assert row["available_month"] if isinstance(row, dict) else row.available_month > origin
    # available_month (2026-08) is strictly after the origin month (2026-07)
    assert row.available_month == "2026-08-01"
    assert row.available_month > origin


def test_publication_lag_is_measured_even_when_some_origins_lack_evidence():
    """Missing coverage downgrades the STATUS; it does not erase a measured lag."""
    rows = CT.build_publication_timing_table(
        ["2026-07-01"], [make_issue("2026-08-01", "2026-08-04", ["2026-07-01"])]
    )
    decision = CT.decide_timing_contract(rows, ["2024-01-01", "2026-07-01"], {})
    assert decision["minimum_publication_lag_months"] == 1
    assert decision["publication_timing_status"] == "partially_verified"
    assert decision["archived_first_release_backtest_eligible"] is False


def test_revision_leakage_does_not_null_the_publication_lag():
    """The central C1.5-R1 separation: revisions affect revision safety only.

    The first C1.5 run let a revision finding null `minimum_safe_lag_months`,
    conflating "when was it published" with "when does it stop changing".
    """
    rows = CT.build_publication_timing_table(
        ["2026-07-01"], [make_issue("2026-08-01", "2026-08-04", ["2026-07-01"])]
    )
    decision = CT.decide_timing_contract(
        rows, ["2026-07-01"],
        {"lng_japan_usd_mmbtu": {"revisions_beyond_rounding": 9,
                                 "comparable_observations": 10}},
    )
    assert decision["minimum_publication_lag_months"] == 1  # NOT nulled
    assert decision["publication_timing_status"] == "verified"
    assert decision["revision_safe_lag_months"] is None
    assert decision["revision_audit_status"] == "revisions_observed"


def test_real_timing_decisions_are_separated_and_measured():
    output = audit()
    decisions = output["timing_decisions"]
    assert decisions["minimum_publication_lag_months"] == 1
    assert decisions["publication_timing_status"] == "verified"
    assert decisions["typical_publication_lag_months"] == 1
    assert decisions["revision_safe_lag_months"] is None
    assert decisions["revision_audit_status"] == "revisions_observed"
    assert decisions["recommended_operational_lag_months"] == 2
    assert CONFIG["minimum_publication_lag_months"] == 1
    assert CONFIG["revision_safe_lag_months"] is None
    assert CONFIG["recommended_operational_lag_months"] == 2
    assert "POLICY, not measurement" in CONFIG["recommended_operational_lag_basis"]


# --- first-release extraction ------------------------------------------------


def test_series_row_parsing_extracts_trailing_monthly_values():
    line = "Crude oil, Brent $/bbl a/ 82.6      80.7      69.0    107.5   85.4   83.4"
    values, texts, unit, markers, definition = V._parse_series_row(line, "Crude oil, Brent")
    assert values == [107.5, 85.4, 83.4]
    assert texts == ["107.5", "85.4", "83.4"]
    assert unit == "$/bbl"
    # C1.5-R3: the RAW token, not a boolean. "a/" means energy-index membership.
    assert markers == "a/"
    assert V.footnote_meaning(markers) == "included_in_the_energy_index"
    assert definition is False


def test_thousands_separators_and_definition_markers_are_handled():
    line = "Coal, Australia ** $/mt a/ 172.8 136.1 136.9 138.5 131.9"
    values, _, unit, estimate, definition = V._parse_series_row(line, "Coal, Australia")
    assert values == [136.9, 138.5, 131.9]
    assert definition is True
    line2 = "Copper $/mt b/ 8,490 9,142 13,543 13,552 13,543"
    values2, texts2, _, _, _ = V._parse_series_row(line2, "Copper")
    assert values2 == [13543.0, 13552.0, 13543.0]
    assert texts2[0] == "13,543"


def test_row_with_too_few_values_fails_explicitly():
    with pytest.raises(V.IssueParseError, match="fewer than"):
        V._parse_series_row("Copper $/mt b/ 1.0 2.0", "Copper")


def test_real_first_release_coverage_for_every_series():
    output = audit()
    issues = output["issues"]
    assert len(issues) >= 60
    for issue in issues:
        assert set(issue["observations"]) <= set(V.CANDIDATE_PDF_LABELS)
        for series_id, rows in issue["observations"].items():
            # a series may legitimately have fewer than three rows when the
            # issue did not publish some monthly cells
            assert 0 <= len(rows) <= 3, f"{issue['issue_name']} {series_id}"
            for row in rows:
                assert row["displayed_text"], f"{issue['issue_name']} {series_id}"
                assert row["displayed_value"] is not None


def test_every_series_has_first_release_values_across_the_window():
    output = audit()
    by_series: dict[str, set] = {}
    for issue in output["issues"]:
        for series_id, rows in issue["observations"].items():
            by_series.setdefault(series_id, set()).update(r["reference_month"] for r in rows)
    for series_id in V.CANDIDATE_PDF_LABELS:
        assert len(by_series.get(series_id, set())) >= 50, series_id


def test_pdf_labels_are_recorded_and_differ_from_workbook_labels():
    """The PDF says 'Coal, Australia'; the workbook says 'Coal, Australian'."""
    assert V.CANDIDATE_PDF_LABELS["coal_australia_usd_mt"] == "Coal, Australia"
    c1_audit = ROOT / "docs" / "c1_commodity_source_audit.json"
    if c1_audit.is_file():
        c1 = json.loads(c1_audit.read_text(encoding="utf-8"))
        coal = next(
            c for c in c1["candidates"] if c["candidate_id"] == "coal_australia_usd_mt"
        )
        assert coal["resolved_source_label"] == "Coal, Australian"


# --- rounding vs genuine revision -------------------------------------------


def test_display_rounding_is_not_reported_as_a_revision():
    """PDF prints 136.9; the workbook holds 136.85 — same number, shown coarser."""
    status, absolute, _ = CT.classify_revision(136.9, 136.85, decimal_places=1,
                                               is_documented_estimate=False)
    assert absolute == 0.0
    assert status in ("first_release_observed", "rounding_only_difference")


def test_genuine_revision_is_detected_beyond_rounding():
    status, absolute, percentage = CT.classify_revision(15.77, 12.88, decimal_places=2,
                                                        is_documented_estimate=True)
    assert status == "latest_vintage_revised"
    assert absolute == pytest.approx(-2.89)
    assert percentage == pytest.approx(-18.326, abs=0.01)


def test_revision_hidden_as_rounding_is_still_caught():
    """Synthetic: a change larger than the display tolerance must not be excused
    as rounding just because the printed precision is coarse.
    """
    status, absolute, _ = CT.classify_revision(1140.0, 1136.0, decimal_places=0,
                                               is_documented_estimate=False)
    assert status == "latest_vintage_revised"
    assert absolute == pytest.approx(-4.0)


def test_round_to_display():
    assert CT.round_to_display(136.849, 1) == 136.8
    assert CT.round_to_display(13543.4, 0) == 13543.0


def test_same_vintage_comparison_is_unresolved_not_stable():
    status, _, _ = CT.classify_revision(11.80, 11.80, 2, is_documented_estimate=True,
                                        same_vintage=True)
    assert status == "revision_status_unresolved"


def test_real_revision_audit_finds_the_lng_revision():
    output = audit()
    lng = output["revision_audit"]["by_series"]["lng_japan_usd_mmbtu"]
    assert lng["revisions_beyond_rounding"] >= 1
    assert lng["max_percentage_revision"] > 10.0
    assert CONFIG["estimated_value_policy"]["lng_japan_primary_feature_eligible"] is False


def test_estimate_status_is_preserved_through_the_audit():
    """SUPERSEDES the R1/R2 test that asserted a boolean `estimate_marker`."""
    output = audit()
    records = output["revision_audit"]["records"]
    assert any(
        r["estimate_status"] == "source_documented_estimate" for r in records
    )
    for record in records:
        assert "estimate_marker" not in record
        assert record["estimate_status"] in V.ESTIMATE_STATUSES
        assert record["status"] in CT.REVISION_STATUSES


# --- definition breaks are not revisions -------------------------------------


def test_definition_breaks_are_not_counted_as_numerical_revisions():
    policy = CONFIG["conditional_series_policy"]
    for series_id in ("coal_australia_usd_mt", "palm_oil_usd_mt"):
        assert policy[series_id]["classified_as_numerical_revision"] is False
        assert policy[series_id]["remains_excluded_from_primary_feature_set"] is True
    assert policy["coal_australia_usd_mt"]["definition_break"] == "spot_to_futures_at_2022_02"


def test_conditional_series_are_not_approved_as_features():
    assert CONFIG["approval_state"]["model_feature_approved"] is False
    assert CONFIG["approval_state"]["feature_semantics_approved"] is False
    # timing approval is now earned; the other two are still withheld
    assert CONFIG["approval_state"]["timing_approved"] is True
    output = audit()
    assert output["model_feature_approved_set"] is False


# --- scope guards ------------------------------------------------------------


def test_no_feature_target_join_or_locked_test():
    output = audit()
    assert output["features_created"] is False
    assert output["target_joined"] is False
    assert output["target_association_computed"] is False
    assert output["locked_test_accessed"] is False


def test_audit_script_does_not_import_target_or_evaluation_modules():
    source = (ROOT / "scripts" / "audit_c1_5_commodity_timing.py").read_text(encoding="utf-8")
    for forbidden in ("targets.production_stress", "targets.labels",
                      "evaluation.walk_forward", "evaluation.baselines"):
        assert forbidden not in source


def test_point_in_time_support_is_available_from_archived_releases():
    """SUPERSEDES the first C1.5 run (which called point-in-time impossible) and
    C1.5-R1 (which withheld eligibility for one apparently-bounded month). All 65
    months are measured, so coverage is complete on the FEATURE side.
    """
    assert CONFIG["point_in_time_supported"] == "full"
    assert CONFIG["archived_first_release_backtest_eligible"] is True
    assert CONFIG["latest_vintage_is_point_in_time"] is False
    assert CONFIG["timing_status"] == "verified"
    coverage = CONFIG["archived_first_release_coverage"]
    assert coverage["verified_reference_months"] == 65
    assert coverage["reference_months_examined"] == 65
    assert coverage["missing_origins"] == []


# --- upstream immutability and determinism ----------------------------------


def test_upstream_artifacts_are_unchanged():
    output = audit()
    assert output["upstream_artifacts_unmodified"] is True
    for name, path in GUARDED.items():
        assert path.is_file(), f"{name} missing"


def test_manifest_checksums_match_files_on_disk():
    for entry in SM.read_manifest("WB_PINKSHEET_VINTAGES"):
        path = ROOT / entry["file_path"]
        assert path.is_file(), entry["file_path"]
        assert SM.sha256_of_file(path) == entry["sha256"]


def test_timing_table_is_deterministically_ordered():
    output = audit()
    months = [r["reference_month"] for r in output["publication_timing"]]
    assert months == sorted(months)
    assert len(months) == len(set(months))


def test_timing_computation_is_deterministic():
    issues = [
        make_issue("2026-06-01", "2026-06-02", ["2026-05-01"]),
        make_issue("2026-07-01", "2026-07-01", ["2026-06-01"]),
    ]
    months = ["2026-05-01", "2026-06-01"]
    first = [r.__dict__ for r in CT.build_publication_timing_table(months, issues)]
    second = [r.__dict__ for r in CT.build_publication_timing_table(months, issues)]
    assert first == second


# --- C1.5-R1: corrected archive discovery ------------------------------------


def test_parsing_main_document_links():
    """MAIN DOCUMENT hrefs use a squashed filename; missing this form is why the
    first run could not see February 2021.
    """
    html = (
        "<h4>MAIN DOCUMENT</h4><ul><li><p><a href='/en/doc/804991612306143358-"
        "0050022021/original/CMOPinkSheetFebruary2021.pdf'>"
        "CMO-Pink-Sheet-February-2021.pdf</a></p></li></ul>"
    )
    found = V.discover_issue_urls(html, source_page="seed")
    assert len(found) == 1
    assert found[0]["issue_month"] == "2021-02-01"
    assert found[0]["discovery_method"] == "official_detail_main_document"
    assert found[0]["url"].startswith("https://thedocs.worldbank.org/")


def test_parsing_related_links():
    html = (
        "<a href='https://thedocs.worldbank.org/en/doc/abc-1/related/"
        "CMO-Pink-Sheet-April-2023.pdf'>Apr</a>"
    )
    found = V.discover_issue_urls(html, source_page="seed")
    assert found[0]["issue_month"] == "2023-04-01"
    assert found[0]["discovery_method"] == "official_related_href"


def test_main_document_outranks_related_and_probe_for_the_same_issue():
    html = (
        "<a href='https://thedocs.worldbank.org/en/doc/x/related/"
        "CMO-Pink-Sheet-February-2021.pdf'>rel</a>"
        "<a href='/en/doc/y/original/CMOPinkSheetFebruary2021.pdf'>main</a>"
    )
    found = V.discover_issue_urls(html)
    assert len(found) == 1
    assert found[0]["discovery_method"] == "official_detail_main_document"


def test_discovering_an_individual_document_with_a_unique_hash():
    html = (
        "<a href='/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
        "CMO-Pink-Sheet-March-2021.pdf'>Mar</a>"
    )
    found = V.discover_issue_urls(html)
    assert "5d903e848db1d1b83e0ec8f744e55570-0350012021" in found[0]["url"]


def test_no_guessed_document_hash_anywhere():
    output = audit()
    assert output["discovery"]["construct_urls_from_guessed_hash"] is False
    assert CONFIG["discovery"]["construct_urls_from_guessed_hash"] is False
    # Structural check: every acquired URL carries a discovery method drawn from
    # the allowed set, and each recorded source URL appears under a document
    # folder that a parsed href supplied.
    for entry in SM.read_manifest("WB_PINKSHEET_VINTAGES"):
        assert entry["url_discovery_method"] in V.DISCOVERY_METHODS
        assert entry["url_discovery_method"] != "pattern_probe_within_discovered_folder"
        assert entry["source_url"].startswith("https://thedocs.worldbank.org/en/doc/")
    inventory = output["expected_issue_inventory"]
    for row in inventory:
        if row["pdf_url"]:
            assert row["discovery_method"] in V.DISCOVERY_METHODS


def test_expected_issue_range_is_february_2021_through_june_2026():
    output = audit()
    span = output["discovery"]["expected_issue_range"]
    assert span["first"] == "2021-02-01"
    assert span["last"] == "2026-06-01"
    assert span["count"] == 65
    inventory = output["expected_issue_inventory"]
    assert len(inventory) == 65
    assert inventory[0]["expected_issue_month"] == "2021-02-01"
    assert inventory[-1]["expected_issue_month"] == "2026-06-01"


def test_missing_issue_search_through_the_official_document_service():
    """Any issue absent from the seed pages must be searched for, and the
    attempt preserved as evidence even when it returns nothing.
    """
    output = audit()
    missing = output["discovery"]["missing_after_seed_pages"]
    attempts = output["discovery"]["public_documents_search_attempts"]
    assert len(attempts) == len(missing)
    for attempt in attempts:
        assert attempt["document_name"].startswith("CMO-Pink-Sheet-")
        assert "search_url" in attempt


def test_issue_and_reference_month_alignment_across_the_inventory():
    output = audit()
    for row in output["expected_issue_inventory"]:
        expected_reference = CT.add_months(row["expected_issue_month"], -1)
        assert row["reference_month_first_exposed"] == expected_reference
        if row["validation_status"] == "validated":
            assert row["latest_displayed_reference_month"] == expected_reference


def test_no_duplicate_issue_or_reference_month():
    output = audit()
    issue_months = [r["expected_issue_month"] for r in output["expected_issue_inventory"]]
    assert len(issue_months) == len(set(issue_months))
    reference_months = [r["reference_month"] for r in output["publication_timing"]]
    assert len(reference_months) == len(set(reference_months))
    names = [i["issue_name"] for i in output["issues"]]
    assert len(names) == len(set(names))


def test_one_issue_does_not_represent_multiple_first_release_months():
    """Each issue newly completes exactly ONE reference month, even though it
    displays three monthly columns.
    """
    output = audit()
    index = output["first_release_index"]
    window = output["required_window"]
    from collections import Counter

    # Scope to the required reference window. The EARLIEST issue held is a
    # genuine boundary case: with no earlier issue to compare against, all three
    # of its columns are "first seen" — but only the newest of them falls inside
    # the window, so the boundary cannot inflate coverage.
    in_window = {
        month: issue for month, issue in index.items()
        if window["start"] <= month <= window["end"]
    }
    per_issue = Counter(in_window.values())
    assert per_issue, "no first-release index"

    multi = {issue: n for issue, n in per_issue.items() if n > 1}
    # Only a documented publication skip may let one issue first-publish two
    # months: February 2025 omitted January 2025, so March 2025 carries both.
    assert set(multi) <= {"CMO-Pink-Sheet-March-2025"}, multi
    for count in multi.values():
        assert count == 2


def test_deterministic_archive_inventory():
    output = audit()
    inventory = output["expected_issue_inventory"]
    months = [r["expected_issue_month"] for r in inventory]
    assert months == sorted(months)
    timing = [r["reference_month"] for r in output["publication_timing"]]
    assert timing == sorted(timing)


# --- C1.5-R2 regression tests -----------------------------------------------
# These replace two C1.5-R1 tests that asserted the OPPOSITE conclusions:
#   test_duplicate_issue_content_is_rejected_not_counted_as_coverage
#   test_january_2025_is_bounded_not_measured_and_drives_the_lag
# Both encoded a fetch defect as an archive fact. They are superseded, not
# disabled, and AD-R40 records why.


def test_r2_february_2025_is_a_distinct_validated_issue():
    """R1 called February 2025 byte-identical to January. It is not."""
    output = audit()
    feb = next(
        r for r in output["expected_issue_inventory"]
        if r["expected_issue_month"] == "2025-02-01"
    )
    jan = next(
        r for r in output["expected_issue_inventory"]
        if r["expected_issue_month"] == "2025-01-01"
    )
    assert feb["validation_status"] == "validated"
    assert feb["sha256"] != jan["sha256"]
    assert feb["file_size_bytes"] != jan["file_size_bytes"]
    assert feb["internal_pdf_creation_date"] == "2025-02-04"
    assert feb["latest_displayed_reference_month"] == "2025-01-01"
    assert jan["latest_displayed_reference_month"] == "2024-12-01"


def test_r2_february_2025_resolves_to_the_related_url_not_original():
    """The root cause: /original/ is filename-agnostic and must never win."""
    output = audit()
    feb = next(
        r for r in output["expected_issue_inventory"]
        if r["expected_issue_month"] == "2025-02-01"
    )
    assert "/related/" in feb["pdf_url"]
    assert "/original/" not in feb["pdf_url"]
    assert feb["discovery_method"] == "official_related_href"


def test_r2_related_href_outranks_family_original_href():
    """Ranking, not first-seen order, decides which candidate is tried first."""
    html = (
        '<a href="/en/doc/abc-001/original/CMO-Pink-Sheet-February-2025.pdf">x</a>'
        '<a href="/en/doc/abc-001/related/CMO-Pink-Sheet-February-2025.pdf">y</a>'
    )
    issues = V.discover_issue_urls(html, source_page="seed")
    feb = next(i for i in issues if i["issue_month"] == "2025-02-01")
    # The /original/ href appears FIRST in the markup and must still lose.
    assert feb["discovery_method"] == "official_related_href"
    assert "/related/" in feb["url"]
    methods = [c["discovery_method"] for c in feb["candidates"]]
    assert methods.index("official_related_href") < methods.index(
        "official_family_original_href"
    )
    # The losing candidate is retained, not discarded.
    assert any("/original/" in c["url"] for c in feb["candidates"])


def test_r2_issue_identity_rejects_a_file_from_the_wrong_month():
    """The check that would have caught R1's defect on arrival."""
    january = FakeIssue(
        issue_name="CMO-Pink-Sheet-January-2025",
        issue_month="2025-01-01",
        issue_date="2025-01-03",
        monthly_reference_months=["2024-10-01", "2024-11-01", "2024-12-01"],
    )
    ok, problems = V.validate_issue_identity(january, "2025-02-01")
    assert ok is False
    assert problems
    ok_self, problems_self = V.validate_issue_identity(january, "2025-01-01")
    assert ok_self is True
    assert problems_self == []


def test_r2_storage_identity_is_collision_safe_on_the_document_hash():
    """Two families can use the same basename; the path must still differ."""
    a = V.storage_identity(
        "https://thedocs.worldbank.org/en/doc/AAA-001/related/CMO-Pink-Sheet-June-2025.pdf",
        "CMO-Pink-Sheet-June-2025.pdf",
    )
    b = V.storage_identity(
        "https://thedocs.worldbank.org/en/doc/BBB-002/related/CMO-Pink-Sheet-June-2025.pdf",
        "CMO-Pink-Sheet-June-2025.pdf",
    )
    assert a != b
    assert a.startswith("AAA-001__") and b.startswith("BBB-002__")
    assert a.endswith("CMO-Pink-Sheet-June-2025.pdf")


def test_r2_every_expected_issue_is_validated_with_a_distinct_checksum():
    """Derived, not assumed: 65 expected, 65 validated, 65 distinct hashes."""
    output = audit()
    inventory = output["expected_issue_inventory"]
    assert len(inventory) == 65
    assert all(r["validation_status"] == "validated" for r in inventory)
    checksums = [r["sha256"] for r in inventory]
    assert len(set(checksums)) == 65
    coverage = output["coverage"]
    assert coverage["distinct_issues_obtained"] == 65
    assert coverage["duplicate_content_issues"] == []
    assert coverage["missing_issue_months"] == []
    assert CONFIG["distinct_issues_obtained"] == 65
    assert CONFIG["duplicate_content_issues"] == []


def test_r2_all_65_reference_months_are_measured_not_bounded():
    output = audit()
    assert len(output["months_with_evidence"]) == 65
    assert output["months_upper_bound_only"] == []
    assert output["months_without_evidence_count"] == 0
    january = next(
        r for r in output["publication_timing"] if r["reference_month"] == "2025-01-01"
    )
    assert january["availability_status"] == "verified_from_archived_issue"
    assert january["is_true_first_release"] is True
    assert january["first_seen_issue"] == "CMO-Pink-Sheet-February-2025"


def test_r2_minimum_publication_lag_is_one_because_every_month_is_t_plus_1():
    """Lag 2 was an artefact of the wrong February file and is not retained."""
    output = audit()
    decisions = output["timing_decisions"]
    assert decisions["minimum_publication_lag_months"] == 1
    assert decisions["publication_timing_status"] == "verified"
    assert decisions["upper_bound_only_months"] == []
    assert decisions["publication_lag_month_distribution"] == {"1": 65}
    stats = output["publication_delay_stats"]
    assert stats["months_available_in_t_plus_1"] == 65
    assert stats["all_verified_available_by_end_of_following_month"] is True
    # The conservative margin survives, but only where it is labelled policy.
    assert decisions["recommended_operational_lag_months"] == 2
    assert "POLICY" in decisions["recommended_operational_lag_basis"].upper()


def test_r2_eligibility_fields_are_present_and_separate():
    output = audit()
    decisions = output["timing_decisions"]
    assert decisions["eligible_for_primary_backtest"] is True
    assert decisions["eligible_for_sensitivity_analysis"] is True
    assert decisions["point_in_time_supported"] == "full"
    assert decisions["coverage_fraction"] == 1.0
    assert decisions["publication_timing_verified"] is True
    assert decisions["revision_status"] == "revisions_observed"
    # Timing verified and revisions observed must be able to coexist: they
    # answer different questions.
    assert decisions["revision_safe_lag_months"] is None
    for field in (
        "eligible_for_primary_backtest", "eligible_for_sensitivity_analysis",
        "point_in_time_supported", "coverage_fraction",
        "publication_timing_verified", "revision_status",
    ):
        assert field in CONFIG, field


def test_r2_revisions_are_scoped_to_the_required_window():
    """No series may report more comparable months than the window contains."""
    output = audit()
    audit_block = output["revision_audit"]
    assert audit_block["in_window_reference_months"] == 65
    for series_id, stats in audit_block["by_series"].items():
        assert stats["comparable_observations"] <= 65, series_id
    out_of_window = audit_block["out_of_window"]
    assert out_of_window["reference_months"] == ["2020-11-01", "2020-12-01"]
    assert out_of_window["count"] == 2
    assert out_of_window["observations"] == 14
    assert all(
        r["reference_month"] >= "2021-01-01" for r in audit_block["records"]
    )


def test_r2_no_commodity_series_is_approved_as_a_model_feature():
    """Timing approval is not feature approval, per series and overall."""
    output = audit()
    assert output["model_feature_approved_set"] is False
    assert CONFIG["approval_state"]["model_feature_approved"] is False
    assert CONFIG["approval_state"]["feature_semantics_approved"] is False
    per_series = CONFIG["series_model_feature_approval"]
    assert len(per_series) == 7
    assert all(v["model_feature_approved"] is False for v in per_series.values())
    # C1's exclusions survive R2 untouched.
    conditional = CONFIG["conditional_series_policy"]
    for series_id in ("coal_australia_usd_mt", "palm_oil_usd_mt"):
        assert conditional[series_id]["remains_excluded_from_primary_feature_set"] is True
        assert conditional[series_id]["classified_as_numerical_revision"] is False
    assert CONFIG["estimated_value_policy"]["lng_japan_primary_feature_eligible"] is False


def test_missing_monthly_cells_produce_no_observation():
    """Older issues print an ellipsis for unreported months. Reading "the last
    three numbers" there pulls QUARTERLY values and fabricates a first release —
    the bug that produced a spurious +118% coal revision.
    """
    ellipsis = chr(0x2026)
    line = (
        "Coal, Australia $/mt a/ 77.9 60.8 138.1 109.7 169.1 183.9 197.0 "
        + " ".join([ellipsis] * 4)
    )
    values, texts, _, _, _ = V._parse_series_row(line, "Coal, Australia")
    assert values == [None, None, None]
    assert texts == ["", "", ""]


def test_definition_break_attribution_requires_a_regime_change_after_first_release():
    # coal's break is 2022-02; a month first published in 2022-08 was already in
    # the futures regime, so a later difference is an ordinary revision
    assert CT.definition_break_applies("coal_australia_usd_mt", "2022-07-01", "2022-08-01") is None
    # but a month whose governing regime began after it was published is a break
    assert CT.definition_break_applies(
        "palm_oil_usd_mt", "2025-03-01", "2024-06-01"
    ) == "2025-02-01"
    assert CT.definition_break_applies("brent_crude_usd_bbl", "2023-01-01", "2023-02-01") is None


def test_definition_breaks_never_counted_as_numerical_revisions():
    output = audit()
    for series_id in ("coal_australia_usd_mt", "palm_oil_usd_mt"):
        stats = output["revision_audit"]["by_series"][series_id]
        assert "definition_break_observations" in stats
        assert stats["comparable_observations"] >= 0
    records = output["revision_audit"]["records"]
    for record in records:
        if record["status"] == "definition_break":
            assert record["series_id"] in CT.DEFINITION_BREAKS


def test_lng_workbook_differences_measured_across_the_full_window():
    """RENAMED in C1.5-R3. The old name claimed the later value was FINAL.

    The numbers are unchanged; what they are called is not.
    """
    output = audit()
    stats = output["revision_audit"]["by_series"]["lng_japan_usd_mmbtu"]
    assert 60 <= stats["comparable_observations"] <= 65
    assert stats["documented_estimates_differing_from_latest_vintage"] >= 50
    assert "estimate_to_final_transitions" not in stats
    assert stats["revision_frequency"] > 0.9
    assert stats["max_percentage_revision"] > 20
    assert CONFIG["estimated_value_policy"]["lng_japan_primary_feature_eligible"] is False


# --- C1.5-R3: footnote and estimate semantics -------------------------------


def make_observation(series_id, reference_month, value=10.0, marker="a/",
                     status="not_documented_as_estimate"):
    return V.SeriesObservation(
        series_id=series_id, pdf_label=series_id, unit="$/x",
        reference_month=reference_month, displayed_value=value,
        displayed_text=f"{value:.2f}", decimal_places=2,
        source_footnote_marker=marker,
        source_footnote_meaning=V.footnote_meaning(marker),
        estimate_status=status, estimate_evidence_type="none",
        estimate_evidence_text="", estimate_rule_version=V.ESTIMATE_RULE_VERSION,
        estimate_evidence_url="https://example.invalid/x.pdf",
        definition_marker=False,
    )


LNG_NOTE = (
    "Liquefied natural gas (Japan), LNG, import price, cif; recent two months' "
    "averages are estimates."
)


def test_footnote_meanings_are_stable_and_index_only():
    assert V.FOOTNOTE_MEANINGS == {
        "a/": "included_in_the_energy_index",
        "b/": "included_in_the_non_energy_index",
        "c/": "included_in_the_precious_metals_index",
        "d/": "index_definition_footnote",
    }
    for meaning in V.FOOTNOTE_MEANINGS.values():
        assert "estimate" not in meaning
    assert V.footnote_meaning("z/") == "unknown_footnote_marker"


def test_footnote_marker_never_implies_estimate_status():
    """The central C1.5-R3 rule, asserted for every documented token."""
    for marker in V.FOOTNOTE_MEANINGS:
        status, evidence_type, _ = V.classify_estimate_status(
            "brent_crude_usd_bbl", "2024-01-01", ["2024-01-01"], None
        )
        assert status == "not_documented_as_estimate"
        assert evidence_type == "none"
        # The marker plays no part in the classification at all.
        assert marker not in status


def test_brent_carrying_the_energy_marker_is_not_an_estimate():
    """Synthetic: an energy-index member that is NOT estimated."""
    observation = make_observation("brent_crude_usd_bbl", "2024-01-01", marker="a/")
    assert observation.source_footnote_marker == "a/"
    assert observation.source_footnote_meaning == "included_in_the_energy_index"
    assert observation.estimate_status == "not_documented_as_estimate"
    status, _, _ = V.classify_estimate_status(
        "brent_crude_usd_bbl", "2024-01-01",
        ["2023-11-01", "2023-12-01", "2024-01-01"], None,
    )
    assert status == "not_documented_as_estimate"


def test_lng_estimate_status_comes_from_evidence_not_the_marker():
    months = ["2024-01-01", "2024-02-01", "2024-03-01"]
    evidence = V.find_estimate_rule_evidence(LNG_NOTE, "lng_japan_usd_mmbtu")
    assert evidence is not None
    assert evidence["months_covered"] == 2
    # With evidence: the two newest displayed months are estimates.
    for month in ("2024-03-01", "2024-02-01"):
        status, evidence_type, text = V.classify_estimate_status(
            "lng_japan_usd_mmbtu", month, months, evidence
        )
        assert status == "source_documented_estimate"
        assert evidence_type == "description_note_two_most_recent_months"
        assert "estimates" in text
    # Without evidence the SAME month is unknown, not an estimate.
    status, evidence_type, _ = V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-03-01", months, None
    )
    assert status == "unknown"
    assert evidence_type == "description_note_absent"


def test_third_latest_lng_month_is_outside_the_estimate_rule():
    months = ["2024-01-01", "2024-02-01", "2024-03-01"]
    evidence = V.find_estimate_rule_evidence(LNG_NOTE, "lng_japan_usd_mmbtu")
    status, _, _ = V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-01-01", months, evidence
    )
    assert status == "not_covered_by_current_estimate_rule"
    # And that is NOT a claim of finality.
    assert "final" not in status


def test_absent_description_note_yields_unknown_never_false():
    assert V.find_estimate_rule_evidence("no such note here", "lng_japan_usd_mmbtu") is None
    status, _, _ = V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-03-01",
        ["2024-01-01", "2024-02-01", "2024-03-01"], None,
    )
    assert status == "unknown"
    assert "false" not in V.ESTIMATE_STATUSES
    assert False not in V.ESTIMATE_STATUSES


def test_misordered_monthly_columns_do_not_shift_the_estimate_window():
    """Synthetic: position is taken from SORTED months, not input order."""
    scrambled = ["2024-03-01", "2024-01-01", "2024-02-01"]
    evidence = V.find_estimate_rule_evidence(LNG_NOTE, "lng_japan_usd_mmbtu")
    assert V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-01-01", scrambled, evidence
    )[0] == "not_covered_by_current_estimate_rule"
    assert V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-03-01", scrambled, evidence
    )[0] == "source_documented_estimate"


def test_single_monthly_column_is_handled_explicitly():
    """Synthetic: one column — the only month is the newest, so it is covered."""
    evidence = V.find_estimate_rule_evidence(LNG_NOTE, "lng_japan_usd_mmbtu")
    status, _, _ = V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-03-01", ["2024-03-01"], evidence
    )
    assert status == "source_documented_estimate"
    # A month the issue does not display cannot be classified from it.
    absent, evidence_type, _ = V.classify_estimate_status(
        "lng_japan_usd_mmbtu", "2024-02-01", ["2024-03-01"], evidence
    )
    assert absent == "unknown"
    assert evidence_type == "reference_month_not_in_issue_columns"


def test_non_energy_series_with_an_independent_note_is_not_inferred_from_b():
    """Synthetic: a non-energy member is classified by rule, not by its token."""
    observation = make_observation("aluminum_usd_mt", "2024-01-01", marker="b/")
    assert observation.source_footnote_meaning == "included_in_the_non_energy_index"
    assert observation.estimate_status == "not_documented_as_estimate"
    # Aluminum has no documented estimate rule, so evidence lookup returns None
    # even when an LNG note is present in the same document.
    assert V.find_estimate_rule_evidence(LNG_NOTE, "aluminum_usd_mt") is None
    status, evidence_type, _ = V.classify_estimate_status(
        "aluminum_usd_mt", "2024-01-01", ["2024-01-01"], None
    )
    assert status == "not_documented_as_estimate"
    assert evidence_type == "none"


def test_real_issues_classify_brent_and_lng_differently():
    output = audit()
    issue = max(output["issues"], key=lambda i: i["issue_month"])
    newest = issue["latest_reference_month"]
    brent = {o["reference_month"]: o for o in issue["observations"]["brent_crude_usd_bbl"]}
    lng = {o["reference_month"]: o for o in issue["observations"]["lng_japan_usd_mmbtu"]}
    # Both carry the energy-index token.
    assert brent[newest]["source_footnote_marker"] == "a/"
    assert lng[newest]["source_footnote_marker"] == "a/"
    # Only LNG has a documented estimate rule.
    assert brent[newest]["estimate_status"] == "not_documented_as_estimate"
    assert lng[newest]["estimate_status"] == "source_documented_estimate"


def test_finality_is_never_claimed():
    """No artifact may describe an observation as final."""
    output = audit()
    transitions = output["estimate_transition_audit"]
    assert transitions["finality_claimed"] is False
    for series_stats in transitions["by_series"].values():
        for record in series_stats["records"]:
            for key in record:
                assert "final" not in key or key.startswith("first_non_estimated")
    # The old name may still appear in comments that explain the rename; what
    # must not survive is an emitted FIELD carrying it.
    emitted = json.dumps(output)
    assert '"estimate_to_final_transitions"' not in emitted
    for series_stats in output["revision_audit"]["by_series"].values():
        assert "estimate_to_final_transitions" not in series_stats
        assert "documented_estimates_differing_from_latest_vintage" in series_stats


def test_right_censored_transitions_are_reported_explicitly():
    output = audit()
    lng = output["estimate_transition_audit"]["by_series"]["lng_japan_usd_mmbtu"]
    assert lng["first_releases_documented_as_estimates"] == 65
    assert lng["estimate_status_unknown"] == 0
    # 63 resolved + 2 right-censored, never folded together.
    assert lng["estimates_with_a_later_non_estimated_vintage"] == 63
    assert lng["right_censored_or_unresolved"] == 2
    assert lng["right_censored_months"] == ["2026-04-01", "2026-05-01"]
    assert (
        lng["estimates_with_a_later_non_estimated_vintage"]
        + lng["right_censored_or_unresolved"]
        == lng["first_releases_documented_as_estimates"]
    )
    assert (
        lng["estimates_revised_before_first_non_estimated_vintage"]
        + lng["estimates_unchanged_at_first_non_estimated_vintage"]
        == lng["estimates_with_a_later_non_estimated_vintage"]
    )
    for record in lng["records"]:
        if record["transition_status"].startswith("right_censored"):
            assert record["first_non_estimated_vintage"] is None
            assert record["revised_before_first_non_estimated_vintage"] is None


def test_numerical_revisions_are_independent_of_estimate_status():
    """The correction must not have moved a single revision figure."""
    output = audit()
    expected = {
        "aluminum_usd_mt": (65, 1), "brent_crude_usd_bbl": (65, 0),
        "coal_australia_usd_mt": (57, 2), "copper_usd_mt": (65, 2),
        "lng_japan_usd_mmbtu": (65, 65), "palm_oil_usd_mt": (65, 20),
        "rubber_rss3_usd_kg": (65, 0),
    }
    for series_id, (comparable, revised) in expected.items():
        stats = output["revision_audit"]["by_series"][series_id]
        assert stats["comparable_observations"] == comparable, series_id
        assert stats["revisions_beyond_rounding"] == revised, series_id
    lng = output["revision_audit"]["by_series"]["lng_japan_usd_mmbtu"]
    assert lng["max_percentage_revision"] == pytest.approx(34.10454155955442)
    # classify_revision's estimate argument changes only the LABEL of a
    # zero-difference row, never whether a difference counts as a revision.
    for flag in (True, False):
        status, absolute, _ = CT.classify_revision(15.77, 12.88, 2,
                                                   is_documented_estimate=flag)
        assert status == "latest_vintage_revised"
        assert absolute == pytest.approx(-2.89)


def test_footnote_semantics_recorded_in_the_audit_and_config():
    output = audit()
    semantics = output["footnote_semantics"]
    assert semantics["markers"] == V.FOOTNOTE_MEANINGS
    assert semantics["index_membership_implies_estimate"] is False
    config = CONFIG["source_footnote_semantics"]
    assert config["index_membership_implies_estimate_status"] is False
    assert config["raw_marker_preserved_verbatim"] is True
    assert {k: v for k, v in config["markers"].items()} == V.FOOTNOTE_MEANINGS
    superseded = CONFIG["superseded_estimate_fields"]
    assert superseded["lng_estimate_to_final_transitions"]["previous_value"] == 65
    assert superseded["estimate_marker"]["status"] == "REPLACED"


def test_lng_remains_excluded_regardless_of_the_corrected_counts():
    assert CONFIG["estimated_value_policy"]["lng_japan_primary_feature_eligible"] is False
    features = yaml.safe_load(
        (ROOT / "configs" / "commodity_features.yaml").read_text(encoding="utf-8")
    )
    assert "lng_japan_usd_mmbtu" in features["excluded_series"]
    assert "lng_japan_usd_mmbtu" not in features["primary_series"]


def test_no_target_or_locked_test_access_in_this_correction():
    output = audit()
    assert output["target_association_computed"] is False
    assert output["locked_test_accessed"] is False
    assert output["features_created"] is False
    assert output["model_feature_approved_set"] is False
