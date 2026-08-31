"""Task D2 tests — publication timing, the numerical guard, and the splice gate.

The tests that matter most here are the negative ones: that the guard refuses,
that a failed probe never becomes an absence claim, that a re-estimated edition
pair is never spliced, and that the July spelling variant does not silently
become a coverage gap.
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.data import oie_mpi_discovery as DISCOVERY
from thai_supply_chain_ews.data import oie_mpi_history as HISTORY
from thai_supply_chain_ews.data import oie_mpi_release_inventory as INVENTORY
from thai_supply_chain_ews.data import oie_mpi_vintages as VINTAGES
from thai_supply_chain_ews.data import target_timing_contract as CONTRACT

ROOT = Path(__file__).resolve().parents[1]
CONFIG = VINTAGES.load_timing_config()
CUTOFF = CONFIG["numerical_audit_cutoff_month"]
AUDIT_JSON = ROOT / "docs" / "d2_oie_mpi_source_audit.json"
DECISION_JSON = ROOT / "docs" / "d2_target_timing_decision.json"

LIVE = ROOT / "data/raw/OIE_MPI/2026-08-26/Prodidx1.xlsx"
HIST_2016 = ROOT / "data/raw/OIE_MPI_HIST_2559_2566/2026-08-26/extracted/Prodidx1.xlsx"
HIST_2011 = ROOT / "data/raw/OIE_MPI_HIST_2554_2561/2026-08-26/extracted/Prodidx1.xlsx"

requires_live = pytest.mark.skipif(not LIVE.exists(), reason="live MPI workbook not present")
requires_audit = pytest.mark.skipif(not AUDIT_JSON.exists(), reason="D2 audit not yet run")


# --------------------------------------------------------------------------
# Config is preregistered
# --------------------------------------------------------------------------
def test_config_declares_cutoff_and_outcomes():
    assert CONFIG["numerical_audit_cutoff_month"] == "2025-06"
    assert len(CONFIG["timing_evidence_classes"]) == 7
    assert len(CONFIG["revision_classes"]) == 8
    assert set(CONFIG["evidence_outcomes"]) == {
        "point_in_time_extension_supported",
        "latest_vintage_extension_only",
        "timing_only_supported",
        "extension_not_supported",
    }


def test_config_forbids_weakening_the_gate():
    immutability = CONFIG["immutability"]
    assert immutability["may_weaken_gate_to_make_d1_rerunnable"] is False
    assert immutability["may_rerun_d1_models"] is False
    assert immutability["may_change_b4_split"] is False
    assert immutability["may_read_locked_test_outcomes"] is False
    assert immutability["may_rewrite_prior_decision_log_entries"] is False
    assert CONFIG["base_year_compatibility_gate"]["silent_splicing_permitted"] is False


def test_history_requirements_are_the_stated_ones():
    requirements = CONFIG["history_extension_requirements"]
    assert requirements["raw_start_required"] == "2020-04"
    assert requirements["stress_start_required"] == "2021-04"
    assert len(requirements["required_divisions"]) == 22
    assert 16 in requirements["required_divisions"]


# --------------------------------------------------------------------------
# The numerical guard
# --------------------------------------------------------------------------
@requires_live
def test_guard_refuses_month_after_cutoff():
    reader = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    with pytest.raises(VINTAGES.NumericalCutoffError):
        reader.value_at(10, "2025-07")
    with pytest.raises(VINTAGES.NumericalCutoffError):
        reader.value_at(10, "2026-06")


@requires_live
def test_guard_permits_cutoff_month_itself():
    reader = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    assert reader.is_readable(CUTOFF)
    assert reader.value_at(10, CUTOFF) is not None


@requires_live
def test_series_never_contains_a_month_after_cutoff():
    reader = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    for division in reader.divisions():
        series = reader.division_series(division)
        assert all(month <= CUTOFF for month in series), division


@requires_live
def test_series_omits_rather_than_nulls_beyond_cutoff():
    """Omission records 'not read'; null would assert 'read and empty'."""
    reader = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    series = reader.division_series(10)
    assert "2026-06" not in series
    assert None not in series.values()


@requires_live
def test_allow_beyond_cutoff_raises_rather_than_widening():
    reader = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    with pytest.raises(VINTAGES.NumericalCutoffError):
        reader.division_series(10, allow_beyond_cutoff=True)


@requires_live
def test_structural_metadata_readable_beyond_cutoff():
    """The guard blocks values, not the month labels a timing audit needs."""
    reader = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    start, end = reader.coverage()
    assert start == "2021-01"
    assert end > CUTOFF
    assert reader.marked_months() == ["2026-06"]


# --------------------------------------------------------------------------
# Header parsing
# --------------------------------------------------------------------------
def test_buddhist_era_conversion():
    month, marker, year = VINTAGES.parse_thai_month_header("2569", "ม.ค.", None)
    assert (month, marker, year) == ("2026-01", None, 2026)


def test_year_is_carried_forward_across_blank_cells():
    _, _, year = VINTAGES.parse_thai_month_header("2564", "ม.ค.", None)
    month, _, year = VINTAGES.parse_thai_month_header(None, "ก.พ.", year)
    assert month == "2021-02"


def test_marker_is_returned_not_silently_stripped():
    month, marker, _ = VINTAGES.parse_thai_month_header("2569", "มิ.ย.*", None)
    assert month == "2026-06"
    assert marker == "*"


def test_non_month_header_yields_no_month():
    month, _, _ = VINTAGES.parse_thai_month_header(None, "% Change", 2026)
    assert month is None


# --------------------------------------------------------------------------
# Reference-month parsing, including the July spelling variant
# --------------------------------------------------------------------------
def test_standard_july_spelling_parses():
    assert INVENTORY.parse_reference_month("ภาพรวมดัชนีอุตสาหกรรมเดือนกรกฎาคม 2566") == "2023-07"


def test_variant_july_spelling_parses():
    """Five archive entries use กรกฏาคม (ฏ). Rejecting it invents coverage gaps."""
    assert INVENTORY.parse_reference_month("ภาพรวมดัชนีอุตสาหกรรมเดือนกรกฏาคม 2566") == "2023-07"


def test_both_july_spellings_agree():
    standard = INVENTORY.parse_reference_month("เดือนกรกฎาคม 2565")
    variant = INVENTORY.parse_reference_month("เดือนกรกฏาคม 2565")
    assert standard == variant == "2022-07"


def test_unparseable_title_returns_none_not_a_guess():
    assert INVENTORY.parse_reference_month("ภาพรวมดัชนีอุตสาหกรรม") is None


def test_filename_timestamp_converts_from_bangkok_local():
    stamp = INVENTORY.parse_filename_timestamp("100520250730115615.pdf", offset_hours=7)
    assert stamp == datetime(2025, 7, 30, 4, 56, 15, tzinfo=UTC)


def test_filename_without_timestamp_returns_none():
    assert INVENTORY.parse_filename_timestamp("overview.pdf") is None


def test_month_end_handles_february_and_leap_years():
    assert INVENTORY.month_end("2021-02").day == 28
    assert INVENTORY.month_end("2024-02").day == 29
    assert INVENTORY.month_end("2025-12").day == 31


# --------------------------------------------------------------------------
# Timing-evidence classification
# --------------------------------------------------------------------------
def _record(**kwargs):
    record = INVENTORY.ReleaseRecord(reference_month="2022-06")
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_corroborated_when_both_timestamps_agree():
    record = _record(
        attachment_last_modified_utc="2022-08-01T01:57:59+00:00",
        attachment_filename_timestamp_utc="2022-08-01T01:57:59+00:00",
        listing_timestamp_utc="2022-08-01T02:00:00+00:00",
        timestamps_agree=True,
        publication_lag_days=32,
    )
    assert INVENTORY.classify_timing_evidence(record, CONFIG, {}) == "attachment_corroborated"


def test_rehost_detected_when_listing_is_later_than_attachment():
    record = _record(
        attachment_last_modified_utc="2022-08-01T01:57:59+00:00",
        attachment_filename_timestamp_utc="2022-08-01T01:57:59+00:00",
        listing_timestamp_utc="2023-07-27T11:08:53+00:00",
        timestamps_agree=True,
        publication_lag_days=32,
    )
    assert (
        INVENTORY.classify_timing_evidence(record, CONFIG, {})
        == "rehosted_listing_later_than_attachment"
    )


def test_migration_batch_when_shared_stamp_and_implausible_lag():
    record = _record(
        reference_month="2016-01",
        attachment_last_modified_utc="2017-06-13T00:00:00+00:00",
        listing_timestamp_utc="2017-06-13T00:00:00+00:00",
        timestamps_agree=False,
        publication_lag_days=498,
    )
    batches = {"2017-06-13": 16}
    assert (
        INVENTORY.classify_timing_evidence(record, CONFIG, batches)
        == "migration_batch_contaminated"
    )


def test_listing_only_is_distinct_from_migration_contaminated():
    """No attachment is not the same as an implausible date."""
    record = _record(
        reference_month="2020-03",
        listing_timestamp_utc="2020-04-29T12:37:09+00:00",
        publication_lag_days=29,
    )
    assert INVENTORY.classify_timing_evidence(record, CONFIG, {}) == "listing_timestamp_only"


def test_no_evidence_when_nothing_is_present():
    assert (
        INVENTORY.classify_timing_evidence(_record(), CONFIG, {})
        == INVENTORY.NO_TIMING_EVIDENCE
    )


def test_directly_observed_release_outranks_everything():
    record = _record(
        reference_month="2026-07",
        listing_timestamp_utc="2026-08-27T00:00:00+00:00",
        publication_lag_days=27,
    )
    assert (
        INVENTORY.classify_timing_evidence(record, CONFIG, {}, ["2026-07"])
        == "directly_observed_release"
    )


def test_migration_batches_need_the_configured_minimum():
    rows = [
        {"listing_timestamp_raw": "6/13/2017 12:00:00 AM"},
        {"listing_timestamp_raw": "6/13/2017 12:00:00 AM"},
        {"listing_timestamp_raw": "1/2/2018 12:00:00 AM"},
    ]
    batches = INVENTORY.detect_migration_batches(rows, 3)
    assert batches == {}
    batches = INVENTORY.detect_migration_batches(rows, 2)
    assert batches == {"2017-06-13": 2}


# --------------------------------------------------------------------------
# Revision taxonomy — comparability outranks magnitude
# --------------------------------------------------------------------------
def test_scheme_change_outranks_numerical_difference():
    assert (
        VINTAGES.classify_revision(
            10.0, 99.0, earlier_scheme="ISIC", later_scheme="TSIC",
            earlier_base_year=2011, later_base_year=2016,
        )
        == "classification_change"
    )


def test_base_year_change_is_not_an_ordinary_revision():
    assert (
        VINTAGES.classify_revision(100.0, 118.0, earlier_base_year=2016, later_base_year=2021)
        == "base_year_rebasing"
    )


def test_division_set_change_is_flagged_before_comparison():
    assert (
        VINTAGES.classify_revision(
            100.0, 100.0, earlier_divisions=[10, 11], later_divisions=[10, 11, 16]
        )
        == "industry_definition_change"
    )


def test_rounding_is_not_reported_as_a_revision():
    assert VINTAGES.classify_revision(97.351, 97.354, displayed_decimals=2) == "rounding_only"


def test_difference_beyond_display_precision_is_a_revision():
    assert VINTAGES.classify_revision(97.35, 98.90, displayed_decimals=2) == "ordinary_revision"


def test_marked_earlier_value_yields_preliminary_to_later():
    assert (
        VINTAGES.classify_revision(97.35, 98.90, displayed_decimals=2, earlier_was_marked=True)
        == "preliminary_to_later"
    )


def test_missing_value_is_not_comparable():
    assert VINTAGES.classify_revision(None, 98.9) == "not_comparable"


def test_every_class_is_declared_in_config():
    assert set(VINTAGES.REVISION_CLASSES) == set(CONFIG["revision_classes"])


# --------------------------------------------------------------------------
# Discovery never establishes absence
# --------------------------------------------------------------------------
def test_absence_states_is_empty():
    assert DISCOVERY.ABSENCE_STATES == ()


def test_summary_never_claims_absence():
    results = [
        DISCOVERY.ProbeResult("a", "https://x", "dns_failure"),
        DISCOVERY.ProbeResult("b", "https://y", "tls_hostname_mismatch"),
    ]
    summary = DISCOVERY.summarize_discovery(results)
    assert summary["absence_claim_supported"] is False
    assert summary["absence_established_for"] == []
    assert summary["reachable"] == []


def test_probe_result_cannot_support_absence():
    result = DISCOVERY.ProbeResult("a", "https://x", "dns_failure")
    assert result.to_dict()["supports_absence_claim"] is False


@pytest.mark.parametrize(
    "error,expected",
    [
        (urllib.error.URLError(socket.gaierror("nodename nor servname provided")), "dns_failure"),
        (
            urllib.error.URLError(
                ssl.SSLCertVerificationError("Hostname mismatch, certificate is not valid")
            ),
            "tls_hostname_mismatch",
        ),
        (urllib.error.URLError(ConnectionResetError("reset")), "connection_error"),
    ],
)
def test_failures_get_specific_states(monkeypatch, error, expected):
    def boom(*args, **kwargs):
        raise error

    monkeypatch.setattr(DISCOVERY, "fetch", boom)
    result = DISCOVERY.probe_entry_point({"id": "x", "url": "https://x"})
    assert result.state == expected
    assert result.state in DISCOVERY.PROBE_STATES


# --------------------------------------------------------------------------
# Edition profiles and the splice gate
# --------------------------------------------------------------------------
@requires_live
def test_editions_differ_in_base_year_and_scheme():
    live = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    older = VINTAGES.GuardedMonthlyReader.from_config(HIST_2011, CONFIG)
    assert live.base_year() == 2021
    assert live.classification_scheme() == "TSIC"
    assert older.base_year() == 2011
    assert older.classification_scheme() == "ISIC"


@requires_live
def test_primary_edition_does_not_reach_required_start():
    live = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    start, _ = live.coverage()
    assert start > CONFIG["history_extension_requirements"]["raw_start_required"]


@requires_live
def test_older_editions_are_missing_a_required_division():
    older = VINTAGES.GuardedMonthlyReader.from_config(HIST_2016, CONFIG)
    assert 16 not in older.divisions()
    assert 16 in CONFIG["history_extension_requirements"]["required_divisions"]


@requires_live
def test_splice_gate_rejects_a_re_estimated_edition_pair():
    older = VINTAGES.GuardedMonthlyReader.from_config(HIST_2016, CONFIG)
    newer = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    result = HISTORY.evaluate_base_year_compatibility(older, newer, CONFIG)
    assert result["splice_admissible"] is False
    assert result["divisions_re_estimated"] > 0
    assert result["blockers"]


@requires_live
def test_compatibility_reads_no_month_after_cutoff():
    older = VINTAGES.GuardedMonthlyReader.from_config(HIST_2016, CONFIG)
    newer = VINTAGES.GuardedMonthlyReader.from_config(LIVE, CONFIG)
    result = HISTORY.evaluate_base_year_compatibility(older, newer, CONFIG)
    for row in result["per_division"]:
        assert row["overlap_months"] <= 36


def test_pure_rescaling_passes_the_gate():
    """A genuine rebasing must not be rejected — the gate is not a blanket no."""

    class Fake:
        def __init__(self, scale, base):
            self.scale, self.base = scale, base

        def divisions(self):
            return [10, 11]

        def division_series(self, division):
            return {f"2021-{m:02d}": 100.0 * self.scale + division for m in range(1, 13)}

        def base_year(self):
            return self.base

        def classification_scheme(self):
            return "TSIC"

    result = HISTORY.evaluate_base_year_compatibility(Fake(1.0, 2016), Fake(1.0, 2021), CONFIG)
    assert result["splice_admissible"] is True
    assert result["divisions_re_estimated"] == 0


def test_gate_rejects_differing_division_sets_even_when_ratios_are_constant():
    class Fake:
        def __init__(self, divisions):
            self._divisions = divisions

        def divisions(self):
            return self._divisions

        def division_series(self, division):
            return {f"2021-{m:02d}": 100.0 for m in range(1, 13)}

        def base_year(self):
            return 2016

        def classification_scheme(self):
            return "TSIC"

    result = HISTORY.evaluate_base_year_compatibility(Fake([10, 11]), Fake([10, 11, 16]), CONFIG)
    assert result["splice_admissible"] is False
    assert any("division sets differ" in b for b in result["blockers"])


def test_month_sequence_is_inclusive_and_crosses_years():
    months = HISTORY.month_sequence("2020-11", "2021-02")
    assert months == ["2020-11", "2020-12", "2021-01", "2021-02"]


# --------------------------------------------------------------------------
# Timing contract and the B4 consequence
# --------------------------------------------------------------------------
def _credible(month, lag):
    return INVENTORY.ReleaseRecord(
        reference_month=month,
        publication_lag_days=lag,
        first_publication_estimate_utc="2021-01-01T00:00:00+00:00",
        timing_evidence_class="attachment_corroborated",
        first_publication_is_credible=True,
    )


def test_contract_reports_lag_and_one_month_availability():
    records = [_credible(m, 29) for m in HISTORY.month_sequence("2020-04", "2025-06")]
    contract = CONTRACT.build_timing_contract(records, "2020-04", "2025-06")
    assert contract.publication_lag_days_median == 29
    assert contract.availability_lag_months == 1
    assert contract.same_month_availability_supported is False
    assert contract.required_window_fully_evidenced is True
    assert contract.contract_status == "resolved"


def test_contract_is_unresolved_when_the_window_has_holes():
    records = [_credible(m, 29) for m in HISTORY.month_sequence("2020-04", "2024-12")]
    contract = CONTRACT.build_timing_contract(records, "2020-04", "2025-06")
    assert contract.required_window_fully_evidenced is False
    assert contract.contract_status == "unresolved"
    assert contract.required_window_missing_months


def test_b4_assumption_is_violated_by_a_positive_lag():
    records = [_credible(m, 29) for m in HISTORY.month_sequence("2020-04", "2025-06")]
    contract = CONTRACT.build_timing_contract(records, "2020-04", "2025-06")
    verdict = CONTRACT.evaluate_b4_assumption(contract)
    assert verdict["assumption_status"] == "violated"
    assert verdict["affects_b4_baselines"] is True
    assert verdict["b4_split_changed"] is False
    assert verdict["remedy_deferred"] is True


def test_b4_assumption_would_hold_with_same_month_publication():
    records = [_credible(m, -2) for m in HISTORY.month_sequence("2020-04", "2025-06")]
    contract = CONTRACT.build_timing_contract(records, "2020-04", "2025-06")
    verdict = CONTRACT.evaluate_b4_assumption(contract)
    assert verdict["assumption_status"] == "holds"


def test_marker_semantics_are_not_asserted():
    records = [_credible(m, 29) for m in HISTORY.month_sequence("2020-04", "2025-06")]
    contract = CONTRACT.build_timing_contract(
        records, "2020-04", "2025-06", marker_months=["2026-06"]
    )
    assert contract.marker_semantics_documented is False
    assert "not asserted" in contract.marker_note


# --------------------------------------------------------------------------
# Audit output
# --------------------------------------------------------------------------
@requires_audit
def test_audit_assigns_exactly_one_declared_outcome():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    assert audit["evidence_outcome"] in CONFIG["evidence_outcomes"]
    assert audit["evidence_outcome"] == "timing_only_supported"


@requires_audit
def test_audit_records_the_d1_limitation_fields():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    limitation = audit["d1_limitation"]
    assert limitation["d1_primary_result"] == "incremental_signal_not_supported"
    assert limitation["d1_nested_protocol_fully_executed"] is False
    assert limitation["d1_fallback_count"] == 6
    assert (
        limitation["d1_protocol_deviation_reason"]
        == "insufficient_pre_origin_calibration_history"
    )
    assert limitation["fallback_strongly_shrinks_toward_benchmark"] is True
    assert limitation["fallback_guaranteed_to_worsen_model"] is False
    assert limitation["fallback_effect_direction"] == "unknown"
    assert limitation["d1_approved_for_locked_test"] is False


@requires_audit
def test_audit_observed_restrictions():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    for key, value in audit["restrictions_observed"].items():
        assert value is False, key


@requires_audit
def test_audit_inventory_has_no_duplicate_months_and_no_gaps():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    months = [
        r["reference_month"] for r in audit["release_inventory"]["records"]
        if r["reference_month"]
    ]
    assert len(months) == len(set(months))
    expected = HISTORY.month_sequence(min(months), max(months))
    assert sorted(months) == expected


@requires_audit
def test_audit_every_record_carries_a_declared_evidence_class():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    declared = set(CONFIG["timing_evidence_classes"])
    for record in audit["release_inventory"]["records"]:
        assert record["timing_evidence_class"] in declared


@requires_audit
def test_audit_credibility_matches_class():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    weak = {"migration_batch_contaminated", "listing_timestamp_only", "no_timing_evidence"}
    for record in audit["release_inventory"]["records"]:
        if record["timing_evidence_class"] in weak:
            assert record["first_publication_is_credible"] is False
        else:
            assert record["first_publication_is_credible"] is True


@requires_audit
def test_audit_records_without_attachment_are_not_attachment_classified():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    for record in audit["release_inventory"]["records"]:
        if not record["attachment_filename"]:
            assert record["timing_evidence_class"] not in {
                "attachment_corroborated",
                "attachment_last_modified_only",
                "rehosted_listing_later_than_attachment",
            }


@requires_audit
def test_audit_reports_no_complete_vintages_but_scopes_the_claim():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    finding = audit["vintage_finding"]
    assert finding["complete_12_industry_vintages_available"] is False
    assert "not proof" in finding["absence_claim_scope"]


@requires_audit
def test_audit_extension_is_infeasible_with_stated_blockers():
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    extension = audit["history_extension"]
    assert extension["latest_vintage_extension_feasible"] is False
    assert extension["point_in_time_extension_feasible"] is False
    assert extension["d1_fallback_remedied"] is False
    assert extension["blockers"]


@requires_audit
def test_decision_document_reports_violated_assumption():
    decision = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    assert decision["b4_assumption"]["assumption_status"] == "violated"
    assert decision["b4_assumption"]["b4_split_changed"] is False
    assert decision["timing_contract"]["availability_lag_months"] == 1


@requires_audit
def test_no_record_estimate_is_taken_from_the_download_timestamp():
    """Acquisition time must never become a publication date."""
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    for record in audit["release_inventory"]["records"]:
        estimate = record["first_publication_estimate_utc"]
        if estimate:
            assert estimate in {
                record["attachment_last_modified_utc"],
                record["attachment_filename_timestamp_utc"],
                record["listing_timestamp_utc"],
            }


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["oie_mpi_release", "oie_mpi_vintage"])
def test_schema_parses_and_declares_task(name):
    path = ROOT / "schemas" / (f"{name}.schema.yaml")
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert schema["task"] == "D2"
    assert schema["schema_version"] == 1


def test_release_schema_enum_matches_config():
    path = ROOT / "schemas" / "oie_mpi_release.schema.yaml"
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    column = next(
        c for c in schema["release_record"]["columns"] if c["name"] == "timing_evidence_class"
    )
    assert set(column["enum"]) == set(CONFIG["timing_evidence_classes"])


def test_vintage_schema_pins_the_cutoff():
    path = ROOT / "schemas" / "oie_mpi_vintage.schema.yaml"
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert schema["numerical_guard"]["cutoff_value"] == CUTOFF
