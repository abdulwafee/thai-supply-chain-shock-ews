"""Task B1 — production ingestion and panel-builder tests.

Covers the 23 required validation cases.

FIXTURE POLICY: every synthetic value in this file is a TEST FIXTURE, built to
exercise parsing and aggregation logic. Fixture numbers are deliberately round
and implausible (100.0, 200.0, weights of 30/70) so they can never be mistaken
for real OIE observations. Real-data assertions are confined to the tests
explicitly named "snapshot", which read the actual verified source files.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.data import oie  # noqa: E402
from thai_supply_chain_ews.data.build_panel import (  # noqa: E402
    AggregationError,
    aggregate_industry_value,
    build_industry_panel,
    write_outputs,
)
from thai_supply_chain_ews.data.ingest import (  # noqa: E402
    SourceIntegrityError,
    SourceSpec,
    build_division_month_table,
    load_source_config,
    resolve_source_file,
    verify_source_integrity,
)
from thai_supply_chain_ews.data.taxonomy import (  # noqa: E402
    TaxonomyError,
    load_taxonomy,
)

# --- shared synthetic fixtures ----------------------------------------------

THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค."]


def fixture_rows(
    *,
    be_year: int = 2564,
    preliminary_last: bool = False,
    divisions: tuple[tuple[int, float, list], ...] = ((10, 30.0, [100.0, 110.0, 120.0]),),
    label_col: int = 0,
) -> list[tuple]:
    """Build a TEST FIXTURE workbook-shaped row list matching the verified OIE
    header layout (year row above a Thai-month row; weight column immediately
    after the label column).
    """
    month_start = label_col + 2
    months = list(THAI_MONTHS)
    if preliminary_last:
        months[-1] = months[-1] + "*"

    width = month_start + len(months)
    year_row = [None] * width
    year_row[month_start] = be_year
    month_row = [None] * width
    for i, m in enumerate(months):
        month_row[month_start + i] = m

    rows = [tuple([None] * width), tuple(year_row), tuple(month_row)]
    for division, weight, values in divisions:
        row = [None] * width
        row[label_col] = f"TSIC : {division:02d} ชื่ออุตสาหกรรมทดสอบ"
        row[label_col + 1] = weight
        for i, v in enumerate(values):
            row[month_start + i] = v
        rows.append(tuple(row))
    return rows


def write_fixture_workbook(path: Path, rows: list[tuple]) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)
    return path


def division_records(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame.from_records(rows)


# --- (1) Thai Buddhist-year header conversion -------------------------------


def test_buddhist_year_converts_to_gregorian():
    assert oie.buddhist_to_gregorian_year(2564) == 2021
    assert oie.buddhist_to_gregorian_year(2569) == 2026
    assert oie.BUDDHIST_TO_GREGORIAN_YEAR_OFFSET == 543


def test_buddhist_year_conversion_rejects_an_already_gregorian_year():
    """Silently subtracting 543 from 2021 would shift the series to 1478."""
    with pytest.raises(oie.OieParseError, match="Buddhist-Era"):
        oie.buddhist_to_gregorian_year(2021)


# --- (2) Thai month parsing --------------------------------------------------


def test_thai_month_abbreviations_parse_to_correct_dates():
    rows = fixture_rows()
    month_col = oie.find_first_month_column(rows, 0)
    parsed = oie.parse_monthly_dates(rows, month_col)
    assert parsed.dates == [date(2021, 1, 1), date(2021, 2, 1), date(2021, 3, 1)]
    assert parsed.is_chronological is True
    assert parsed.has_duplicates is False
    assert parsed.gap_months == []


def test_first_month_column_is_not_the_weight_column():
    """The weight column sits immediately after the label and is numeric;
    detection must read header text, not a data row's first numeric cell.
    """
    rows = fixture_rows(divisions=((10, 16.67, [100.0, 110.0, 120.0]),))
    assert oie.find_first_month_column(rows, 0) == 2  # not column 1 (weight 16.67)


# --- (3) Preliminary-marker parsing -----------------------------------------


def test_preliminary_marker_is_parsed_and_retained():
    rows = fixture_rows(preliminary_last=True)
    parsed = oie.parse_monthly_dates(rows, oie.find_first_month_column(rows, 0))
    assert parsed.preliminary_flags == [False, False, True]
    assert parsed.dates[-1] == date(2021, 3, 1)  # date still parsed, marker not lost


# --- (4) Division-row identification ----------------------------------------


def test_division_row_identification_detects_the_label_column():
    assert oie.find_tsic_label_column(fixture_rows(label_col=0)) == 0
    assert oie.find_tsic_label_column(fixture_rows(label_col=2)) == 2


def test_only_two_digit_division_totals_are_treated_as_division_rows(tmp_path):
    rows = fixture_rows(divisions=((10, 30.0, [100.0, 110.0, 120.0]),))
    group_row = [None] * len(rows[0])
    group_row[0] = "TSIC : 1010 กลุ่มย่อยทดสอบ"  # four-digit group, must be ignored
    group_row[1] = 5.0
    rows.append(tuple(group_row))
    parsed = oie.parse_workbook(write_fixture_workbook(tmp_path / "f.xlsx", rows))
    assert parsed.division_numbers == [10]


# --- (5) Duplicate division detection ---------------------------------------


def test_duplicate_division_raises(tmp_path):
    rows = fixture_rows(
        divisions=((10, 30.0, [100.0, 110.0, 120.0]), (10, 40.0, [200.0, 210.0, 220.0]))
    )
    with pytest.raises(oie.DuplicateDivisionError, match="more than once"):
        oie.parse_workbook(write_fixture_workbook(tmp_path / "dup.xlsx", rows))


# --- (6) Numeric-value validation -------------------------------------------


def test_non_numeric_value_is_recorded_missing_not_coerced(tmp_path):
    rows = fixture_rows(divisions=((10, 30.0, [100.0, "n/a", 120.0]),))
    parsed = oie.parse_workbook(write_fixture_workbook(tmp_path / "nn.xlsx", rows))
    row = parsed.divisions[10]
    assert date(2021, 2, 1) not in row.values_by_month  # not zero-filled
    assert date(2021, 2, 1) in row.non_numeric_months
    assert row.values_by_month[date(2021, 1, 1)] == 100.0


# --- (7) Source-weight validation -------------------------------------------


def test_non_numeric_source_weight_raises(tmp_path):
    rows = fixture_rows(divisions=((10, "-", [100.0, 110.0, 120.0]),))
    with pytest.raises(oie.OieParseError, match="non-numeric source weight"):
        oie.parse_workbook(write_fixture_workbook(tmp_path / "w.xlsx", rows))


def test_non_positive_source_weight_raises(tmp_path):
    rows = fixture_rows(divisions=((10, 0.0, [100.0, 110.0, 120.0]),))
    with pytest.raises(oie.OieParseError, match="non-positive source weight"):
        oie.parse_workbook(write_fixture_workbook(tmp_path / "w0.xlsx", rows))


# --- (8) mapping covers all 22 reported divisions exactly once ---------------


def test_taxonomy_covers_exactly_the_22_reported_divisions():
    taxonomy = load_taxonomy()
    expected = [10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22,
                23, 24, 25, 26, 27, 28, 29, 30, 31, 32]
    assert taxonomy.all_divisions == expected
    assert len(expected) == 22
    assert len(taxonomy.industries) == 12
    assert 18 in taxonomy.excluded_divisions
    assert 33 in taxonomy.excluded_divisions


def test_tsic_12_is_assigned_to_ind01():
    """The draft mapping omitted TSIC 12 entirely — a real gap B1 closes."""
    taxonomy = load_taxonomy()
    assert 12 in taxonomy.industries["IND-01"].tsic_divisions
    assert taxonomy.industry_for_division(12) == "IND-01"


# --- (9) no mapped division appears in multiple industries ------------------


def test_no_division_is_assigned_to_two_industries():
    taxonomy = load_taxonomy()
    seen: dict[int, str] = {}
    for industry in taxonomy.industries.values():
        for division in industry.tsic_divisions:
            assert division not in seen, (
                f"{division} in {seen.get(division)} and {industry.industry_id}"
            )
            seen[division] = industry.industry_id
    assert len(seen) == 22


def test_taxonomy_loader_rejects_a_double_assigned_division(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: 1\ntaxonomy_version: t\n"
        "industries:\n"
        "  IND-A: {name_en: A, name_th: ก, tsic_divisions: [10, 11]}\n"
        "  IND-B: {name_en: B, name_th: ข, tsic_divisions: [11]}\n"
        "expected_division_coverage: [10, 11]\n",
        encoding="utf-8",
    )
    with pytest.raises(TaxonomyError, match="assigned to both"):
        load_taxonomy(bad)


# --- (10) weighted aggregation against a manual toy fixture -----------------


def test_weighted_aggregation_matches_a_manual_calculation():
    """TEST FIXTURE values: 100.0 at weight 30, 200.0 at weight 70.
    Manual expected value = 0.3*100 + 0.7*200 = 170.0
    """
    records = division_records([
        {"tsic_division": 10, "source_value": 100.0, "source_weight": 30.0,
         "is_preliminary": False},
        {"tsic_division": 11, "source_value": 200.0, "source_weight": 70.0,
         "is_preliminary": False},
    ])
    result = aggregate_industry_value(records, "IND-T", (10, 11), date(2021, 1, 1), "MPI")
    assert result.value == pytest.approx(170.0)
    assert result.value != pytest.approx(150.0), "must not fall back to equal weighting"


def test_aggregation_never_uses_equal_weights():
    records = division_records([
        {"tsic_division": 10, "source_value": 100.0, "source_weight": 90.0,
         "is_preliminary": False},
        {"tsic_division": 11, "source_value": 200.0, "source_weight": 10.0,
         "is_preliminary": False},
    ])
    result = aggregate_industry_value(records, "IND-T", (10, 11), date(2021, 1, 1), "MPI")
    assert result.value == pytest.approx(110.0)
    assert result.normalized_weights[10] == pytest.approx(0.9)


# --- (11) normalized industry weights sum to one ----------------------------


def test_normalized_weights_sum_to_one():
    records = division_records([
        {"tsic_division": 10, "source_value": 100.0, "source_weight": 16.671088,
         "is_preliminary": False},
        {"tsic_division": 11, "source_value": 200.0, "source_weight": 3.814524,
         "is_preliminary": False},
        {"tsic_division": 12, "source_value": 300.0, "source_weight": 0.722105,
         "is_preliminary": False},
    ])
    result = aggregate_industry_value(records, "IND-01", (10, 11, 12), date(2021, 1, 1), "MPI")
    assert sum(result.normalized_weights.values()) == pytest.approx(1.0)


def test_real_snapshot_normalized_weights_sum_to_one_for_every_industry_month():
    panel = build_industry_panel()
    assert panel.weights_used
    for entry in panel.weights_used:
        assert sum(entry["normalized_weights"].values()) == pytest.approx(1.0)


# --- (12) single-division aggregation ---------------------------------------


def test_single_division_industry_returns_the_division_value():
    records = division_records([
        {"tsic_division": 19, "source_value": 101.72089058816593, "source_weight": 5.5,
         "is_preliminary": False},
    ])
    result = aggregate_industry_value(records, "IND-04", (19,), date(2021, 1, 1), "MPI")
    assert result.value == pytest.approx(101.72089058816593)
    assert result.normalized_weights == {19: pytest.approx(1.0)}


# --- (13) missing-division rejection ----------------------------------------


def test_missing_division_is_rejected_not_silently_dropped():
    records = division_records([
        {"tsic_division": 10, "source_value": 100.0, "source_weight": 30.0,
         "is_preliminary": False},
    ])
    with pytest.raises(AggregationError, match="missing division"):
        aggregate_industry_value(records, "IND-01", (10, 11, 12), date(2021, 1, 1), "MPI")


def test_duplicate_division_row_is_rejected_during_aggregation():
    records = division_records([
        {"tsic_division": 10, "source_value": 100.0, "source_weight": 30.0,
         "is_preliminary": False},
        {"tsic_division": 10, "source_value": 105.0, "source_weight": 30.0,
         "is_preliminary": False},
    ])
    with pytest.raises(AggregationError, match="duplicate division"):
        aggregate_industry_value(records, "IND-T", (10,), date(2021, 1, 1), "MPI")


# --- (14) missing-month rejection -------------------------------------------


def test_missing_value_for_a_month_is_rejected_not_imputed():
    records = division_records([
        {"tsic_division": 10, "source_value": 100.0, "source_weight": 30.0,
         "is_preliminary": False},
        {"tsic_division": 11, "source_value": None, "source_weight": 70.0,
         "is_preliminary": False},
    ])
    with pytest.raises(AggregationError, match="no\\s+numeric value"):
        aggregate_industry_value(records, "IND-T", (10, 11), date(2021, 1, 1), "MPI")


def test_gap_in_the_month_header_is_detected():
    """TEST FIXTURE: January then March, skipping February."""
    rows = fixture_rows()
    rows[2] = (None, None, "ม.ค.", "มี.ค.", None)
    rows[1] = (None, None, 2564, None, None)
    parsed = oie.parse_monthly_dates(rows, 2)
    assert parsed.gap_months == ["2021-02"]


# --- (15) checksum mismatch rejection ---------------------------------------


def _spec(**overrides) -> SourceSpec:
    base = dict(
        source_id="TEST", component="MPI", manifest=Path("nowhere.jsonl"),
        expected_sha256="0" * 64, expected_edition="2021_based", expected_base_year=2021,
        expected_classification="TSIC", source_url=None,
        snapshot={"first_month": "2021-01"},
    )
    base.update(overrides)
    return SourceSpec(**base)


def _parsed_stub(sha: str, first: date) -> oie.ParsedWorkbook:
    dates = oie.MonthlyDateAudit(
        dates=[first], preliminary_flags=[False], earliest=first, latest=first,
        is_chronological=True, has_duplicates=False, gap_months=[],
    )
    return oie.ParsedWorkbook(
        file_path=Path("f.xlsx"), sha256=sha, dates=dates, divisions={}
    )


def test_checksum_mismatch_fails_loudly():
    with pytest.raises(SourceIntegrityError, match="SHA-256 mismatch"):
        verify_source_integrity(
            _spec(), Path("f.xlsx"), _parsed_stub("d" * 64, date(2021, 1, 1))
        )


def test_matching_checksum_passes():
    verify_source_integrity(
        _spec(expected_sha256="a" * 64), Path("f.xlsx"),
        _parsed_stub("a" * 64, date(2021, 1, 1)),
    )


# --- (16) edition mismatch rejection ----------------------------------------


def test_edition_mismatch_fails_loudly():
    """A 2016-based workbook starts 2016-01, not 2021-01."""
    with pytest.raises(SourceIntegrityError, match="edition mismatch"):
        verify_source_integrity(
            _spec(expected_sha256="a" * 64), Path("f.xlsx"),
            _parsed_stub("a" * 64, date(2016, 1, 1)),
        )


# --- (17) manifest-based path resolution ------------------------------------


def test_source_is_resolved_through_its_manifest_not_a_hard_coded_path():
    specs, _ = load_source_config()
    for spec in specs.values():
        path, entry = resolve_source_file(spec)
        assert path.is_file()
        assert entry["file_path"] in str(path).replace("\\", "/")
        assert "retrieved_at" in entry


def test_missing_manifest_raises():
    with pytest.raises(FileNotFoundError, match="manifest missing"):
        resolve_source_file(_spec(manifest=ROOT / "data" / "raw" / "_manifests" / "NOPE.jsonl"))


def test_no_absolute_path_or_retrieval_date_is_hard_coded_in_the_config():
    text = (ROOT / "configs" / "sources.yaml").read_text(encoding="utf-8")
    assert "D:\\" not in text and "C:\\" not in text
    assert "2026-08-26" not in text, "config must not pin one retrieval date"


# --- (18) preliminary retained but model-ineligible --------------------------


def test_preliminary_rows_are_retained_but_not_model_eligible():
    panel = build_industry_panel().frame
    preliminary = panel[panel["mpi_is_preliminary"] | panel["capu_is_preliminary"]]
    assert len(preliminary) > 0, "preliminary rows must be retained, not dropped"
    assert not preliminary["is_model_eligible"].any()
    assert preliminary["mpi_level"].notna().all(), "values retained, not blanked"
    assert (preliminary["data_quality_flag"] == "preliminary").all()


# --- (19) no duplicate industry-month keys ----------------------------------


def test_no_duplicate_industry_month_keys():
    panel = build_industry_panel().frame
    assert not panel.duplicated(subset=["reference_month", "industry_id"]).any()


# --- (20) exactly 12 industries per complete month --------------------------


def test_exactly_twelve_industries_per_month():
    panel = build_industry_panel().frame
    counts = panel.groupby("reference_month")["industry_id"].nunique()
    assert set(counts.unique()) == {12}


# --- (21) current snapshot produces expected row counts ---------------------


def test_snapshot_row_counts_match_configured_expectations():
    specs, raw = load_source_config()
    expected = raw["panel_snapshot"]
    result = build_industry_panel()
    panel = result.frame
    division = result.division_table.frame

    months = sorted({str(m) for m in panel["reference_month"]})
    assert len(months) == expected["months_total"] == 66
    assert months[0] == "2021-01-01" and months[-1] == "2026-06-01"
    assert panel["industry_id"].nunique() == expected["industries"] == 12
    assert len(panel) == expected["rows_total"] == 792
    assert int(panel["is_model_eligible"].sum()) == expected["model_eligible_rows"] == 780
    assert division["tsic_division"].nunique() == 22
    # 22 divisions x 66 months x 2 components
    assert len(division) == 22 * 66 * 2

    non_preliminary_months = {
        str(m) for m in panel.loc[~panel["mpi_is_preliminary"], "reference_month"]
    }
    assert len(non_preliminary_months) == expected["non_preliminary_months"] == 65
    assert "2026-06-01" not in non_preliminary_months


def test_snapshot_has_no_missing_current_edition_months():
    table = build_division_month_table()
    for parsed in table.parsed_by_component.values():
        assert parsed.dates.gap_months == []
        assert parsed.dates.is_chronological
        assert not parsed.dates.has_duplicates


# --- (22) deterministic output ----------------------------------------------


def test_parquet_output_is_deterministic(tmp_path):
    panel = build_industry_panel()
    first = write_outputs(panel, processed_dir=tmp_path / "a", write_csv_preview=False)
    second = write_outputs(panel, processed_dir=tmp_path / "b", write_csv_preview=False)
    for key in ("division_month", "industry_panel"):
        left = pd.read_parquet(first[key])
        right = pd.read_parquet(second[key])
        sort_cols = (
            ["reference_month", "industry_id"]
            if key == "industry_panel"
            else ["component", "reference_month", "tsic_division"]
        )
        pd.testing.assert_frame_equal(
            left.sort_values(sort_cols).reset_index(drop=True),
            right.sort_values(sort_cols).reset_index(drop=True),
        )


def test_two_full_ingestion_runs_produce_identical_content():
    first = build_industry_panel().frame
    second = build_industry_panel().frame
    pd.testing.assert_frame_equal(first, second)


def test_parquet_schema_has_expected_typed_columns():
    from thai_supply_chain_ews.data.build_panel import PANEL_COLUMNS

    panel = build_industry_panel().frame
    assert list(panel.columns) == PANEL_COLUMNS
    assert panel["mpi_level"].dtype == "float64"
    assert panel["is_model_eligible"].dtype == "bool"
    assert panel["source_base_year"].dtype == "int16"


# --- (23) audit scripts remain compatible after the shared-parsing refactor --


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_audit_script_still_exposes_its_original_parsing_api():
    audit = _load_script("audit_target_sources")
    for attr in ("find_tsic_label_column", "find_first_month_column", "parse_monthly_dates",
                 "MonthlyDateAudit", "DuplicateDivisionError", "INDUSTRY_TSIC_DIVISIONS",
                 "THAI_MONTH_TO_NUMBER", "BUDDHIST_TO_GREGORIAN_YEAR_OFFSET"):
        assert hasattr(audit, attr), f"audit script lost {attr} after the refactor"
    # and they must be the production implementation, not a second copy
    assert audit.find_tsic_label_column is oie.find_tsic_label_column
    assert audit.parse_monthly_dates is oie.parse_monthly_dates
    assert audit.MonthlyDateAudit is oie.MonthlyDateAudit


def test_audit_script_keeps_the_frozen_draft_taxonomy_not_the_production_one():
    """The A1/A2 bridge artifacts are checksum-pinned against the draft mapping.
    Production must not leak into them.
    """
    audit = _load_script("audit_target_sources")
    assert audit.INDUSTRY_TSIC_DIVISIONS is audit.DRAFT_INDUSTRY_TSIC_DIVISIONS_A1A2_FROZEN
    assert audit.INDUSTRY_TSIC_DIVISIONS["IND-01"] == [10, 11]  # draft: no TSIC 12
    assert 12 not in {d for v in audit.INDUSTRY_TSIC_DIVISIONS.values() for d in v}
    # production differs, deliberately
    assert load_taxonomy().industries["IND-01"].tsic_divisions == (10, 11, 12)


def test_bridge_validation_scripts_still_import_and_expose_their_constants():
    v1 = _load_script("validate_oie_overlap")
    assert len(v1.CANDIDATE_INDUSTRIES) == 11
    assert v1.IND03_EXCLUDED_ID == "IND-03"


# --- provenance / temporal honesty -------------------------------------------


def test_release_date_and_available_as_of_are_null_because_unverified():
    table = build_division_month_table()
    frame = table.frame
    assert frame["release_date"].isna().all()
    assert frame["available_as_of"].isna().all()


def test_division_table_carries_full_provenance():
    frame = build_division_month_table().frame
    for col in ("source_file", "source_sha256", "retrieved_at", "source_edition",
                "source_base_year"):
        assert frame[col].notna().all()
    assert set(frame["source_edition"].unique()) == {"2021_based"}


def test_b1_metadata_file_matches_the_panel():
    meta_path = ROOT / "docs" / "b1_ingestion_metadata.json"
    if not meta_path.is_file():
        pytest.skip("run scripts/run_b1_ingestion.py first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    panel = build_industry_panel().frame
    assert meta["panel_row_count"] == len(panel)
    assert meta["model_eligible_row_count"] == int(panel["is_model_eligible"].sum())
    assert meta["evaluation_framing"] == "latest_vintage_historical_data"
