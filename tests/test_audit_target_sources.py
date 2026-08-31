"""Tests for scripts/audit_target_sources.py — the Task A1 quality-gate fixes.

scripts/ is a one-off tooling directory, not part of the installable package,
so this file loads the script by path via importlib rather than a normal
import. All fixture data below is synthetic and clearly toy (small integers,
placeholder Thai month/division labels) — none of it represents or resembles
real OIE data, consistent with this project's restriction against fabricated
observations standing in for real ones. These tests exercise the *parsing
and validation logic*, never a claimed real coverage number.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_target_sources.py"
_spec = importlib.util.spec_from_file_location("audit_target_sources", SCRIPT_PATH)
audit = importlib.util.module_from_spec(_spec)
sys.modules["audit_target_sources"] = audit
_spec.loader.exec_module(audit)


# --- duplicate TSIC division detection (quality-gate point 2) --------------


def test_audit_oie_file_raises_on_duplicate_division_label(tmp_path, monkeypatch):
    """A TSIC division label appearing twice must raise, never silently
    overwrite the first occurrence's data (the bug this task flagged).
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "รายเดือน"
    # header rows: blank, blank, blank, weight/year row, month row
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append([None, None, "น้ำหนัก", 2564, None])
    ws.append([None, None, None, "ม.ค.", "ก.พ."])
    # a TSIC division row, then a DUPLICATE of the same division
    ws.append([None, None, "TSIC : 10 อาหาร", 50.0, 100.0, 99.0])
    ws.append([None, None, "TSIC : 10 อาหาร", 50.0, 200.0, 199.0])  # duplicate!

    path = tmp_path / "duplicate_test.xlsx"
    wb.save(path)

    with pytest.raises(audit.DuplicateDivisionError):
        audit.audit_oie_file(path)


def test_audit_oie_file_succeeds_with_no_duplicates(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "รายเดือน"
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append([None, None, "น้ำหนัก", 2564, None])
    ws.append([None, None, None, "ม.ค.", "ก.พ."])
    ws.append([None, None, "TSIC : 10 อาหาร", 50.0, 100.0, 99.0])
    ws.append([None, None, "TSIC : 19 ปิโตรเลียม", 50.0, 80.0, 82.0])

    path = tmp_path / "no_duplicate_test.xlsx"
    wb.save(path)

    result = audit.audit_oie_file(path)
    assert result.tsic_divisions_found == [10, 19]
    assert result.weight_sum == pytest.approx(100.0)


# --- coverage classification: full vs. partial vs. none (quality-gate point 1) ---


def test_industry_coverage_separates_full_and_partial(monkeypatch):
    """IND-03 needs TSIC {16,17,18}; if only 16 is present, it must be
    reported as PARTIAL, never silently counted the same as a full match.
    """
    monkeypatch.setattr(
        audit,
        "INDUSTRY_TSIC_DIVISIONS",
        {"IND-A": [16, 17, 18], "IND-B": [19]},
    )
    coverage = audit.IndustryCoverage()
    found_divisions = {16, 19}  # 18 and 17 missing for IND-A; IND-B fully present
    for industry_id, divisions in audit.INDUSTRY_TSIC_DIVISIONS.items():
        present = [d for d in divisions if d in found_divisions]
        if len(present) == len(divisions):
            coverage.fully_covered.append(industry_id)
        elif present:
            coverage.partially_covered[industry_id] = sorted(set(divisions) - set(present))
        else:
            coverage.not_covered.append(industry_id)

    assert coverage.fully_covered == ["IND-B"]
    assert coverage.partially_covered == {"IND-A": [17, 18]}
    assert coverage.any_coverage_count == 2  # "any coverage" is NOT the same as "full"
    assert coverage.full_coverage_count == 1
    assert coverage.partial_coverage_count == 1


# --- date parsing: BE->CE conversion, ordering, duplicates, gaps (quality-gate point 3) ---


def _build_rows(year_be: int, months: list[str], month_col_start: int = 3):
    """Build a minimal synthetic row set matching the OIE header layout:
    a year row, then a month-abbreviation row at month_col_start.
    """
    year_row = [None] * month_col_start + [year_be] + [None] * (len(months) - 1)
    month_row = [None] * month_col_start + list(months)
    return [
        [None] * 6,
        [None] * 6,
        year_row,
        month_row,
    ]


def test_parse_monthly_dates_converts_buddhist_to_gregorian_year():
    rows = _build_rows(2564, ["ม.ค.", "ก.พ.", "มี.ค."])
    result = audit.parse_monthly_dates(rows, month_col_start=3)
    assert result.dates == [date(2021, 1, 1), date(2021, 2, 1), date(2021, 3, 1)]


def test_parse_monthly_dates_strips_preliminary_marker_and_flags_it():
    rows = _build_rows(2564, ["ม.ค.", "ก.พ.", "มี.ค.*"])
    result = audit.parse_monthly_dates(rows, month_col_start=3)
    assert result.dates[-1] == date(2021, 3, 1)
    assert result.preliminary_flags == [False, False, True]


def test_parse_monthly_dates_detects_chronological_order():
    rows = _build_rows(2564, ["ม.ค.", "ก.พ.", "มี.ค."])
    result = audit.parse_monthly_dates(rows, month_col_start=3)
    assert result.is_chronological is True
    assert result.has_duplicates is False
    assert result.gap_months == []


def test_parse_monthly_dates_detects_gap():
    """Skip February entirely (Jan, then Mar) to confirm the gap is caught."""
    month_col_start = 3
    rows = [
        [None] * 6,
        [None] * 6,
        [None] * month_col_start + [2564, None],
        [None] * month_col_start + ["ม.ค.", "มี.ค."],
    ]
    result = audit.parse_monthly_dates(rows, month_col_start)
    assert result.dates == [date(2021, 1, 1), date(2021, 3, 1)]
    assert result.gap_months == ["2021-02"]


def test_parse_monthly_dates_raises_when_no_month_header_found():
    rows = [[None, None, None], [None, None, None]]
    with pytest.raises(ValueError, match="month-abbreviation header row"):
        audit.parse_monthly_dates(rows, month_col_start=0)


# --- eligibility-constant cross-check against configs/targets.yaml (quality-gate point 9) ---


def test_eligibility_constants_match_config_passes_against_real_config():
    """This is the one test that touches the real repo config on purpose —
    it is exactly what this function exists to guard, so a fixture copy
    would defeat the point.
    """
    audit.check_eligibility_constants_match_config()  # must not raise


def test_eligibility_constants_mismatch_is_detected(tmp_path, monkeypatch):
    stale_config = tmp_path / "targets.yaml"
    stale_config.write_text(
        "eligibility_criteria:\n"
        "  minimum_time_coverage_months: 999\n"  # deliberately wrong
        "  minimum_industry_coverage: 11\n"
        "  maximum_missingness_pct: 10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(audit, "TARGETS_CONFIG_PATH", stale_config)
    with pytest.raises(audit.EligibilityConstantMismatchError):
        audit.check_eligibility_constants_match_config()
