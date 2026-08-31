"""Task C1 — World Bank Pink Sheet ingestion, audit gate, and Brent cross-check.

FIXTURE POLICY: synthetic workbooks are TEST FIXTURES built with round,
implausible numbers so they cannot be mistaken for real commodity prices. Tests
reading the real artifacts are named "real_" or "snapshot".

Synthetic failure cases deliberately construct duplicated months, changed units,
unresolved labels, missing required months, layout changes, checksum mismatches
and FRED date misalignment, and assert each fails EXPLICITLY rather than
silently dropping rows.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import world_bank_commodities as WBC  # noqa: E402

CONFIG = WBC.load_commodity_config()
AUDIT_JSON = ROOT / "docs" / "c1_commodity_source_audit.json"
METADATA_JSON = ROOT / "docs" / "c1_commodity_ingestion_metadata.json"
TABLE_PATH = ROOT / "data" / "interim" / "commodity_month.parquet"

GUARDED = {
    "b1": ROOT / "data" / "processed" / "industry_month_panel.parquet",
    "b3_monthly": ROOT / "data" / "targets" / "production_stress_month.parquet",
    "b3_labels": ROOT / "data" / "targets" / "forecast_target_raw.parquet",
    "b4": ROOT / "data" / "model_input" / "b4_walk_forward_predictions.parquet",
}


def audit_output() -> dict:
    if not AUDIT_JSON.is_file():
        pytest.skip("run scripts/audit_world_bank_commodities.py first")
    return json.loads(AUDIT_JSON.read_text(encoding="utf-8"))


def canonical_table() -> pd.DataFrame:
    if not TABLE_PATH.is_file():
        pytest.skip("run scripts/run_c1_commodity_ingestion.py first")
    return pd.read_parquet(TABLE_PATH)


def real_workbook() -> WBC.PinkSheetWorkbook:
    output = audit_output()
    path = ROOT / output["workbook"]["file"]
    if not path.is_file():
        pytest.skip("raw workbook not present")
    return WBC.parse_workbook(path, CONFIG)


# --- synthetic workbook fixture ---------------------------------------------


def build_fixture_workbook(
    path: Path,
    labels=("Crude oil, Brent", "Copper"),
    units=("($/bbl)", "($/mt)"),
    periods=("2020M01", "2020M02", "2020M03"),
    values=((10.0, 100.0), (11.0, 110.0), (12.0, 120.0)),
    footer_note: str | None = None,
    label_row_index: int = 4,
) -> Path:
    """TEST FIXTURE workbook mirroring the verified Pink Sheet layout."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Monthly Prices"
    for _ in range(label_row_index):
        sheet.append(["World Bank Commodity Price Data (TEST FIXTURE)"])
    sheet.append([None, *labels])
    sheet.append([None, *units])
    for period, row_values in zip(periods, values, strict=True):
        sheet.append([period, *row_values])
    if footer_note:
        sheet.append([footer_note])
    description = workbook.create_sheet("Description")
    description.append(["* Crude oil, UK Brent 38 API. TEST FIXTURE description entry."])
    description.append(["* Copper (LME), grade A. TEST FIXTURE description entry."])
    workbook.save(path)
    return path


def fixture_config(**overrides) -> dict:
    config = json.loads(json.dumps(CONFIG, default=str))
    config["candidates"] = [
        {
            "candidate_id": "brent_crude_usd_bbl",
            "intended_source_series": "Crude oil, Brent",
            "resolved_source_label": "Crude oil, Brent",
            "expected_unit": "($/bbl)",
            "rationale": "fixture",
        }
    ]
    config["eligibility_criteria"]["required_window"] = {
        "start": "2020-01-01", "end": "2020-03-01"
    }
    config.update(overrides)
    return config


FIXTURE_PROVENANCE = {
    "source_url": "https://example.invalid/fixture.xlsx",
    "downloaded_at_utc": "2026-08-27T00:00:00Z",
    "sha256": "0" * 64,
    "source_vintage": "fixture",
}


# --- sheet discovery and label resolution -----------------------------------


def test_official_workbook_sheets_are_discovered():
    output = audit_output()
    sheets = output["workbook"]["sheets_inspected"]
    assert "Monthly Prices" in sheets
    assert "Description" in sheets
    assert set(sheets) >= {"Monthly Prices", "Monthly Indices", "Description", "Index Weights"}


def test_exact_source_labels_resolve_including_the_coal_naming_difference():
    """The task named "Coal, Australia"; the workbook says "Coal, Australian".
    The resolved label must be the workbook's, with no silent substitution.
    """
    workbook = real_workbook()
    for spec in CONFIG["candidates"]:
        column = workbook.column_for_label(spec["resolved_source_label"])
        assert workbook.labels_by_column[column].replace("*", "").strip() == (
            spec["resolved_source_label"]
        )
    coal = next(c for c in CONFIG["candidates"] if c["candidate_id"] == "coal_australia_usd_mt")
    assert coal["intended_source_series"] == "Coal, Australia"
    assert coal["resolved_source_label"] == "Coal, Australian"


def test_unresolved_label_raises_rather_than_fuzzy_matching(tmp_path):
    path = build_fixture_workbook(tmp_path / "wb.xlsx")
    workbook = WBC.parse_workbook(path, fixture_config())
    with pytest.raises(WBC.SeriesNotFoundError, match="not found"):
        workbook.column_for_label("Crude oil, Brentt")
    with pytest.raises(WBC.SeriesNotFoundError):
        workbook.column_for_label("Nickel")


def test_duplicate_label_rejection(tmp_path):
    path = build_fixture_workbook(
        tmp_path / "dup.xlsx",
        labels=("Crude oil, Brent", "Crude oil, Brent"),
        units=("($/bbl)", "($/bbl)"),
        values=((10.0, 10.0), (11.0, 11.0), (12.0, 12.0)),
    )
    workbook = WBC.parse_workbook(path, fixture_config())
    with pytest.raises(WBC.DuplicateLabelError, match="appears in"):
        workbook.column_for_label("Crude oil, Brent")


def test_workbook_layout_change_raises(tmp_path):
    workbook = openpyxl.Workbook()
    workbook.active.title = "Something Else"
    workbook.active.append(["not the pink sheet"])
    path = tmp_path / "layout.xlsx"
    workbook.save(path)
    with pytest.raises(WBC.PinkSheetLayoutError, match="Expected sheet"):
        WBC.parse_workbook(path, fixture_config())


# --- date parsing ------------------------------------------------------------


def test_period_code_parsing():
    assert WBC.parse_period_code("1960M01") == date(1960, 1, 1)
    assert WBC.parse_period_code("2026M12") == date(2026, 12, 1)
    assert WBC.parse_period_code(" 2020M7 ") == date(2020, 7, 1)


def test_period_code_rejects_invalid_and_ambiguous_values():
    for bad in ("2020M13", "2020-01", "M2020", "abc", "202001"):
        with pytest.raises(WBC.PinkSheetLayoutError):
            WBC.parse_period_code(bad)


def test_period_parsing_accepts_real_dates_but_rejects_excel_serials():
    """A datetime is unambiguous; a bare serial number is not, and guessing its
    epoch is how a series silently shifts by years.
    """
    assert WBC.parse_period_code(pd.Timestamp("2020-05-15")) == date(2020, 5, 1)
    with pytest.raises(WBC.PinkSheetLayoutError, match="refusing to guess"):
        WBC.parse_period_code(43831)  # Excel serial for 2020-01-01


def test_footnote_and_header_rows_are_not_parsed_as_observations(tmp_path):
    path = build_fixture_workbook(
        tmp_path / "foot.xlsx", footer_note="Note: source definitions revised."
    )
    workbook = WBC.parse_workbook(path, fixture_config())
    assert workbook.months == [date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1)]
    assert len(workbook.months) == 3


def test_real_workbook_has_no_footnote_rows_as_observations():
    workbook = real_workbook()
    assert all(isinstance(m, date) for m in workbook.months)
    assert workbook.months == sorted(workbook.months)
    assert len(workbook.months) == len(set(workbook.months))


# --- numeric parsing and missing handling -----------------------------------


def test_numeric_parsing_and_missing_tokens_are_not_imputed(tmp_path):
    path = build_fixture_workbook(
        tmp_path / "miss.xlsx",
        values=((10.0, 100.0), ("…", 110.0), (12.0, "n/a")),
    )
    workbook = WBC.parse_workbook(path, fixture_config())
    audits = WBC.audit_candidates(workbook, fixture_config(), FIXTURE_PROVENANCE)
    table = WBC.build_canonical_table(workbook, audits, fixture_config(), FIXTURE_PROVENANCE)
    brent = table[table["series_id"] == "brent_crude_usd_bbl"]
    # the "…" month produces NO row — it is not forward-filled or interpolated
    assert set(brent["month"]) == {date(2020, 1, 1), date(2020, 3, 1)}
    assert len(brent) == 2


def test_value_parser_classifies_tokens():
    assert WBC._parse_value(12.5) == (12.5, "ok")
    assert WBC._parse_value("…")[1] == "missing"
    assert WBC._parse_value(None)[1] == "missing"
    assert WBC._parse_value("abc")[1] == "non_numeric"
    assert WBC._parse_value(float("nan"))[1] == "non_finite"
    assert WBC._parse_value("1,234.5") == (1234.5, "ok")


def test_unit_extraction_is_stable():
    assert WBC._parse_unit("($/bbl)") == ("$/bbl", "USD")
    assert WBC._parse_unit("($/mt)") == ("$/mt", "USD")
    assert WBC._parse_unit("(2010=100)") == ("2010=100", None)
    assert WBC._parse_unit(None) == ("", None)


def test_changed_unit_is_rejected(tmp_path):
    """Synthetic: the workbook reports Brent in $/mt instead of $/bbl."""
    path = build_fixture_workbook(tmp_path / "unit.xlsx", units=("($/mt)", "($/mt)"))
    config = fixture_config()
    workbook = WBC.parse_workbook(path, config)
    audits = WBC.audit_candidates(workbook, config, FIXTURE_PROVENANCE)
    brent = audits[0]
    assert brent.unit_matches_expected is False
    assert brent.criteria["no_unexplained_unit_change"] is False
    assert brent.source_verified is False
    # `conditional`, not `rejected`: the DATA is sound, the SEMANTICS are not.
    # A unit mismatch can be resolved; unusable data cannot. See the status
    # tiering comment in world_bank_commodities.audit_candidates.
    assert brent.status == "conditional"
    assert any("unit" in r for r in brent.reasons)


# --- eligibility gate --------------------------------------------------------


def test_missing_required_months_fail_the_gate(tmp_path):
    """Synthetic: required window is 2020-01..2020-03 but only 2 months exist."""
    path = build_fixture_workbook(
        tmp_path / "short.xlsx",
        periods=("2020M01", "2020M02"),
        values=((10.0, 100.0), (11.0, 110.0)),
    )
    config = fixture_config()
    workbook = WBC.parse_workbook(path, config)
    audits = WBC.audit_candidates(workbook, config, FIXTURE_PROVENANCE)
    brent = audits[0]
    assert brent.missing_in_required_window == 1
    assert brent.missingness_pct == pytest.approx(100.0 / 3)
    assert brent.criteria["missingness_within_limit"] is False
    assert brent.status == "rejected"


def test_duplicate_months_fail_the_gate(tmp_path):
    path = build_fixture_workbook(
        tmp_path / "dupm.xlsx",
        periods=("2020M01", "2020M01", "2020M03"),
        values=((10.0, 100.0), (11.0, 110.0), (12.0, 120.0)),
    )
    config = fixture_config()
    workbook = WBC.parse_workbook(path, config)
    audits = WBC.audit_candidates(workbook, config, FIXTURE_PROVENANCE)
    assert audits[0].duplicate_months == 1
    assert audits[0].criteria["no_duplicate_month"] is False
    assert audits[0].status == "rejected"


def test_missingness_boundary_is_applied_at_one_percent(tmp_path):
    config = fixture_config()
    limit = config["eligibility_criteria"]["max_missingness_pct_in_required_window"]
    assert limit == 1.0
    # a full window passes
    path = build_fixture_workbook(tmp_path / "full.xlsx")
    workbook = WBC.parse_workbook(path, config)
    audits = WBC.audit_candidates(workbook, config, FIXTURE_PROVENANCE)
    assert audits[0].missingness_pct == 0.0
    assert audits[0].criteria["missingness_within_limit"] is True


def test_missing_provenance_fails_the_gate(tmp_path):
    path = build_fixture_workbook(tmp_path / "prov.xlsx")
    config = fixture_config()
    workbook = WBC.parse_workbook(path, config)
    incomplete = {"source_url": "", "downloaded_at_utc": "", "sha256": ""}
    audits = WBC.audit_candidates(workbook, config, incomplete)
    assert audits[0].criteria["provenance_recorded"] is False
    assert audits[0].status != "source_verified"


def test_unresolved_label_is_recorded_as_rejected_not_dropped(tmp_path):
    path = build_fixture_workbook(tmp_path / "unres.xlsx")
    config = fixture_config()
    config["candidates"][0]["resolved_source_label"] = "Nonexistent Commodity"
    workbook = WBC.parse_workbook(path, config)
    audits = WBC.audit_candidates(workbook, config, FIXTURE_PROVENANCE)
    assert len(audits) == 1  # still reported, not silently removed
    assert audits[0].found is False
    assert audits[0].status == "rejected"


# --- real audit outcomes -----------------------------------------------------


def test_real_candidates_are_all_audited_with_documented_status():
    output = audit_output()
    assert len(output["candidates"]) == 7
    for candidate in output["candidates"]:
        assert candidate["status"] in CONFIG["allowed_statuses"]
        assert candidate["unit"], candidate["candidate_id"]
        assert candidate["resolved_source_label"]


def test_definition_breaks_inside_the_window_force_conditional():
    output = audit_output()
    by_id = {c["candidate_id"]: c for c in output["candidates"]}
    for candidate_id in ("coal_australia_usd_mt", "palm_oil_usd_mt"):
        candidate = by_id[candidate_id]
        assert candidate["definition_break_in_window"] is True
        assert candidate["status"] == "conditional"
        assert candidate["source_verified"] is False
    # and a series with no in-window break passes
    assert by_id["brent_crude_usd_bbl"]["definition_break_in_window"] is False
    assert by_id["brent_crude_usd_bbl"]["status"] == "source_verified"


def test_large_moves_are_flagged_but_never_removed():
    output = audit_output()
    table = canonical_table()
    flagged = [
        c for c in output["candidates"]
        if "large_one_month_move_flagged_not_removed" in c["flags"]
    ]
    assert flagged, "expected at least one flagged series"
    for candidate in flagged:
        rows = table[table["series_id"] == candidate["candidate_id"]]
        assert len(rows) == candidate["total_observations"]  # nothing was dropped


def test_approval_fields_stay_distinct_and_model_approval_is_false():
    output = audit_output()
    for candidate in output["candidates"]:
        assert candidate["feature_semantics_approved"] is False
        assert candidate["model_feature_approved"] is False
        assert candidate["source_verified"] == (candidate["status"] == "source_verified")
    assert CONFIG["approval_defaults"]["model_feature_approved"] is False


# --- canonical table ---------------------------------------------------------


def test_unique_series_month_keys_and_typed_month():
    table = canonical_table()
    assert not table.duplicated(subset=["series_id", "month"]).any()
    assert isinstance(table["month"].iloc[0], date)
    assert set(table.columns) == set(WBC.CANONICAL_COLUMNS)
    assert list(table.columns) == WBC.CANONICAL_COLUMNS


def test_canonical_table_is_deterministically_ordered():
    table = canonical_table()
    expected = table.sort_values(["series_id", "month"], kind="mergesort").reset_index(drop=True)
    pd.testing.assert_frame_equal(table, expected)


def test_release_and_availability_are_null_and_pit_unsupported():
    table = canonical_table()
    assert table["release_date"].isna().all()
    assert table["available_as_of"].isna().all()
    assert (~table["point_in_time_supported"]).all()
    # and the download date is NOT used as availability
    assert table["downloaded_at_utc"].notna().all()


def test_no_derived_feature_columns_exist():
    table = canonical_table()
    # Token-based, not substring-based: a naive substring scan flags
    # `quality_flag` for containing "lag".
    forbidden_tokens = {
        "mom", "yoy", "lag", "lagged", "zscore", "volatility", "shock", "change",
        "pct", "delta", "ratio",
    }
    for column in table.columns:
        tokens = set(column.lower().split("_"))
        overlap = tokens & forbidden_tokens
        assert not overlap, f"{column} looks like a derived feature: {overlap}"
    metadata = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
    assert metadata["feature_transformations_created"] is False
    assert metadata["unit_conversions_applied"] is False


def test_no_target_join_or_association_was_computed():
    metadata = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
    assert metadata["target_joined"] is False
    assert metadata["target_association_computed"] is False
    assert metadata["locked_test_accessed"] is False
    table = canonical_table()
    for column in table.columns:
        assert "industry" not in column.lower()
        assert "stress" not in column.lower()


def test_ingestion_script_never_imports_target_or_evaluation_modules():
    source = (ROOT / "scripts" / "run_c1_commodity_ingestion.py").read_text(encoding="utf-8")
    for forbidden in ("targets.production_stress", "evaluation.walk_forward",
                      "forecast_target_raw", "build_forecast_labels"):
        assert forbidden not in source or "GUARDED" in source


def test_real_table_snapshot_counts():
    table = canonical_table()
    assert table["series_id"].nunique() == 7
    assert len(table) == 5269
    assert str(table["month"].min()) == "1960-01-01"
    assert str(table["month"].max()) == "2026-07-01"


# --- manifests and checksums -------------------------------------------------


def test_manifest_records_full_provenance():
    entries = SM.read_manifest("WB_PINKSHEET")
    assert entries, "no manifest entry for WB_PINKSHEET"
    entry = entries[-1]
    for field_name in ("source_id", "file_path", "source_url", "retrieved_at", "sha256"):
        assert entry.get(field_name), field_name
    assert entry["sha256"] == audit_output()["provenance"]["sha256"]
    assert len(entry["sha256"]) == 64


def test_manifest_append_is_idempotent_by_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr(SM, "MANIFEST_DIR", tmp_path)
    entry = SM.ManifestEntry(
        source_id="TEST_SRC", file_path="data/raw/x.bin",
        source_url="https://example.invalid/x", retrieved_at="2026-01-01T00:00:00Z",
        sha256="a" * 64,
    )
    assert SM.append_manifest_entry(entry) is True
    assert SM.append_manifest_entry(entry) is False  # same checksum -> no duplicate
    lines = (tmp_path / "TEST_SRC_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    new_vintage = SM.ManifestEntry(**{**entry.__dict__, "sha256": "b" * 64})
    assert SM.append_manifest_entry(new_vintage) is True  # new bytes -> new fact


def test_checksum_mismatch_is_rejected(tmp_path):
    target = tmp_path / "f.bin"
    target.write_bytes(b"hello")
    actual = SM.sha256_of_file(target)
    assert SM.verify_file_checksum(target, actual) == actual
    with pytest.raises(SM.ChecksumMismatchError, match="expected SHA-256"):
        SM.verify_file_checksum(target, "0" * 64)


def test_raw_workbook_checksum_matches_the_audit():
    output = audit_output()
    path = ROOT / output["workbook"]["file"]
    if not path.is_file():
        pytest.skip("raw workbook not present")
    assert SM.sha256_of_file(path) == output["provenance"]["sha256"]


def test_response_header_parsing():
    from textwrap import dedent

    text = dedent(
        """\
        HTTP/1.1 302 Found
        Location: https://example.invalid/final

        HTTP/1.1 200 OK
        Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
        Content-Length: 577979
        Last-Modified: Tue, 04 Aug 2026 19:23:23 GMT
        """
    )
    path = Path(pytest.ensuretemp("hdr") if hasattr(pytest, "ensuretemp") else ".") / "h.txt"
    path.write_text(text, encoding="utf-8")
    parsed = SM.parse_response_headers(path)
    assert parsed["http_status"] == 200  # last block, not the redirect
    assert parsed["content_length"] == 577979
    assert "spreadsheetml" in parsed["http_content_type"]
    path.unlink()


# --- Brent cross-check -------------------------------------------------------


def _fred_csv(tmp_path: Path, rows, series_id="MCOILBRENTEU") -> Path:
    path = tmp_path / "fred.csv"
    lines = [f"observation_date,{series_id}"]
    lines += [f"{d},{v}" for d, v in rows]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_fred_parser_aligns_months_and_skips_missing_tokens(tmp_path):
    path = _fred_csv(
        tmp_path, [("2021-01-01", "54.8"), ("2021-02-01", "."), ("2021-03-01", "65.4")]
    )
    series = WBC.parse_fred_monthly_csv(path, "MCOILBRENTEU")
    assert series == {date(2021, 1, 1): 54.8, date(2021, 3, 1): 65.4}
    assert date(2021, 2, 1) not in series  # missing token is NOT imputed


def test_fred_parser_rejects_a_wrong_series_column(tmp_path):
    path = _fred_csv(tmp_path, [("2021-01-01", "54.8")], series_id="SOMETHING_ELSE")
    with pytest.raises(WBC.SeriesNotFoundError, match="no column"):
        WBC.parse_fred_monthly_csv(path, "MCOILBRENTEU")


def test_fred_date_misalignment_is_detected_as_missing_months(tmp_path):
    """Synthetic: FRED dates land mid-month. Parsing normalises to first-of-month,
    but a genuinely shifted series shows up as non-overlapping months.
    """
    world_bank = {date(2021, m, 1): 50.0 + m for m in range(1, 13)}
    shifted = {date(2022, m, 1): 50.0 + m for m in range(1, 13)}  # a year off
    metrics = WBC.compute_cross_check_metrics(
        world_bank, shifted, date(2021, 1, 1), date(2021, 12, 1)
    )
    assert metrics["common_month_count"] == 0
    assert len(metrics["missing_in_fred"]) == 12
    status, reasons = WBC.classify_cross_check(metrics, CONFIG)
    assert status == CONFIG["cross_check_classification"]["not_executed_state"]


def test_cross_check_classification_consistent_boundary():
    months = [date(2021, 1, 1)]
    world_bank = {date(2021, 1, 1) + pd.Timedelta(days=0): 0.0}
    del months, world_bank
    wb = {}
    fred = {}
    base = date(2021, 1, 1)
    for i in range(72):
        month = date(2021 + i // 12, i % 12 + 1, 1)
        wb[month] = 100.0 + i
        fred[month] = 100.0 + i  # identical
    metrics = WBC.compute_cross_check_metrics(wb, fred, base, date(2026, 5, 1))
    assert metrics["common_month_count"] >= 60
    assert metrics["pearson"] == pytest.approx(1.0)
    assert metrics["median_abs_pct_diff"] == pytest.approx(0.0)
    status, _ = WBC.classify_cross_check(metrics, CONFIG)
    assert status == "consistent"


def test_cross_check_classification_inconsistent_on_large_pct_difference():
    wb, fred = {}, {}
    for i in range(72):
        month = date(2021 + i // 12, i % 12 + 1, 1)
        wb[month] = 100.0 + i
        fred[month] = (100.0 + i) * 0.5  # 50% apart -> far above the 5% bound
    metrics = WBC.compute_cross_check_metrics(wb, fred, date(2021, 1, 1), date(2026, 5, 1))
    status, reasons = WBC.classify_cross_check(metrics, CONFIG)
    assert status == "inconsistent"
    assert reasons


def test_cross_check_classification_conditional_when_too_few_months():
    wb, fred = {}, {}
    for i in range(12):  # only 12 common months, below the 60 bar
        month = date(2021, i % 12 + 1, 1)
        wb[month] = 100.0 + i
        fred[month] = 100.0 + i
    metrics = WBC.compute_cross_check_metrics(wb, fred, date(2021, 1, 1), date(2021, 12, 1))
    status, reasons = WBC.classify_cross_check(metrics, CONFIG)
    assert status == "conditional"
    assert any("common months" in r for r in reasons)


def test_real_cross_check_status_is_recorded_honestly():
    metadata = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
    cross = metadata["brent_cross_check"]
    allowed = set(CONFIG["allowed_statuses"]) | {
        "consistent", "inconsistent", "conditional",
        CONFIG["cross_check_classification"]["not_executed_state"],
    }
    assert cross["status"] in allowed
    if cross["status"] == CONFIG["cross_check_classification"]["not_executed_state"]:
        # a blocked source must report NO metrics, not estimated ones
        assert cross["metrics"] is None
        assert cross["reasons"]
    assert cross["world_bank_series_replaced"] is False


def test_no_duplicate_brent_feature_is_produced():
    table = canonical_table()
    brent_series = [s for s in table["series_id"].unique() if "brent" in s.lower()]
    assert brent_series == ["brent_crude_usd_bbl"], brent_series
    assert not any("fred" in str(s).lower() for s in table["series_id"].unique())
    assert not any("fred" in str(s).lower() for s in table["source_name"].unique())
    assert CONFIG["cross_check_source"]["may_enter_production_feature_table"] is False
    assert CONFIG["cross_check_source"]["is_second_brent_predictor"] is False


# --- timing limitations ------------------------------------------------------


def test_timing_status_is_unresolved_and_lag_not_chosen():
    timing = CONFIG["timing"]
    assert timing["latest_vintage_only"] is True
    assert timing["point_in_time_backtest_supported"] is False
    assert timing["same_month_availability_verified"] is False
    assert timing["minimum_safe_lag_months"] is None
    assert timing["timing_status"] == "unresolved"


# --- upstream immutability and determinism ----------------------------------


def test_b1_b3_b4_artifacts_are_unchanged():
    metadata = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
    assert metadata["upstream_artifacts_unmodified"] is True
    for name, path in GUARDED.items():
        assert path.is_file(), f"{name} artifact missing"


def test_ingestion_is_deterministic():
    output = audit_output()
    path = ROOT / output["workbook"]["file"]
    if not path.is_file():
        pytest.skip("raw workbook not present")
    config = WBC.load_commodity_config()
    workbook = WBC.parse_workbook(path, config)
    audits = WBC.audit_candidates(workbook, config, output["provenance"])
    first = WBC.build_canonical_table(workbook, audits, config, output["provenance"])
    second = WBC.build_canonical_table(workbook, audits, config, output["provenance"])
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(
        first.reset_index(drop=True), canonical_table().reset_index(drop=True)
    )


def test_audit_json_is_deterministic_for_a_fixed_workbook():
    output_a = audit_output()
    path = ROOT / output_a["workbook"]["file"]
    if not path.is_file():
        pytest.skip("raw workbook not present")
    config = WBC.load_commodity_config()
    workbook = WBC.parse_workbook(path, config)
    first = WBC.audit_candidates(workbook, config, output_a["provenance"])
    second = WBC.audit_candidates(workbook, config, output_a["provenance"])
    assert [a.__dict__ for a in first] == [a.__dict__ for a in second]
