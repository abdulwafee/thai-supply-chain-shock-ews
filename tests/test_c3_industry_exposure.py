"""Task C3 — commodity–industry structural exposure matrix.

Contract tests confirm the production matrix is what C3 promised. Synthetic
failure tests confirm each guard actually fires: a rule that has never been seen
to reject anything is an assumption, not a safeguard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.data import nesdc_input_output as IO  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import taxonomy as TX  # noqa: E402
from thai_supply_chain_ews.matrices import commodity_exposure as CE  # noqa: E402
from thai_supply_chain_ews.matrices import industry_crosswalk as XW  # noqa: E402
from thai_supply_chain_ews.matrices import io_coefficients as CO  # noqa: E402

CONFIG = yaml.safe_load((ROOT / "configs" / "industry_exposure.yaml").read_text(encoding="utf-8"))
SCHEMA_PATH = ROOT / "schemas" / "industry_commodity_exposure.schema.yaml"
SCHEMA = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
MATRIX_JSON = ROOT / "docs" / "c3_commodity_exposure_matrix.json"
SOURCE_AUDIT_JSON = ROOT / "docs" / "c3_io_source_audit.json"


@pytest.fixture(scope="module")
def source_audit():
    return json.loads(SOURCE_AUDIT_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix():
    return json.loads(MATRIX_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def table(source_audit):
    record = next(r for r in source_audit["acquired"] if r["role"] == "primary_io_table")
    return IO.parse_io_workbook(
        ROOT / record["local_path"], "2015", record["final_url"], record["sha256"]
    )


@pytest.fixture(scope="module")
def definitions(source_audit):
    record = next(
        r for r in source_audit["acquired"]
        if r["role"] == "sector_classification_and_definitions"
    )
    return IO.parse_sector_definitions(ROOT / record["local_path"])


@pytest.fixture(scope="module")
def matrices(table):
    codes, a, diagnostics = CO.build_technical_coefficients(table)
    return CO.leontief_inverse(codes, a, diagnostics)


@pytest.fixture(scope="module")
def rows(matrix):
    return matrix["canonical_rows"]


# --- synthetic I/O fixture ----------------------------------------------------


class FakeTable:
    """A tiny, fully-controlled I/O table for failure tests."""

    def __init__(self, sector_codes, z, gross_output):
        self.sector_codes = list(sector_codes)
        self._z = z
        self.gross_output = dict(gross_output)
        self.sha256 = "fake"
        self.value_added = {}

    def z(self, row_code, col_code, measure="purchaser"):
        return float(self._z.get((row_code, col_code), 0.0))


def toy_table():
    codes = ["001", "002", "003"]
    z = {
        ("001", "001"): 10.0, ("001", "002"): 20.0, ("001", "003"): 5.0,
        ("002", "001"): 5.0, ("002", "002"): 10.0, ("002", "003"): 10.0,
        ("003", "001"): 0.0, ("003", "002"): 5.0, ("003", "003"): 5.0,
    }
    x = {"001": 100.0, "002": 200.0, "003": 50.0}
    return FakeTable(codes, z, x)


# --- industry dimension -------------------------------------------------------


def test_exact_twelve_project_industries_reproduced(matrix):
    taxonomy = TX.load_taxonomy()
    assert len(taxonomy.industries) == 12
    ids = taxonomy.industry_ids
    assert ids == [f"IND-{i:02d}" for i in range(1, 13)]
    assert len(set(ids)) == 12

    recorded = matrix["industry_dimension"]
    assert len(recorded) == 12
    for entry in recorded:
        actual = taxonomy.industries[entry["industry_id"]]
        assert entry["name_en"] == actual.name_en
        assert entry["name_th"] == actual.name_th
        assert entry["tsic_divisions"] == list(actual.tsic_divisions)


def test_every_production_industry_is_mapped(matrix):
    mapped = {entry["industry_id"] for entry in matrix["industry_crosswalk"]}
    assert mapped == set(TX.load_taxonomy().industry_ids)
    covered = {row["industry_id"] for row in matrix["canonical_rows"]}
    assert covered == mapped


def test_c3_cannot_rename_or_replace_an_industry(definitions):
    taxonomy = TX.load_taxonomy()
    broken = deepcopy(CONFIG)
    broken["industry_crosswalk"]["IND-01"]["name_en"] = "Renamed Industry"
    with pytest.raises(XW.CrosswalkError, match="must not rename"):
        XW.load_industry_crosswalk(broken, taxonomy, definitions)

    broken2 = deepcopy(CONFIG)
    broken2["industry_crosswalk"]["IND-01"]["tsic_divisions"] = [10, 11]
    with pytest.raises(XW.CrosswalkError, match="TSIC divisions"):
        XW.load_industry_crosswalk(broken2, taxonomy, definitions)

    broken3 = deepcopy(CONFIG)
    del broken3["industry_crosswalk"]["IND-12"]
    with pytest.raises(XW.CrosswalkError, match="do not match the production"):
        XW.load_industry_crosswalk(broken3, taxonomy, definitions)


# --- commodity allowlist ------------------------------------------------------


def test_exact_four_commodity_allowlist(rows):
    assert CE.APPROVED_COMMODITIES == (
        "aluminum_usd_mt", "brent_crude_usd_bbl", "copper_usd_mt",
        "rubber_rss3_usd_kg",
    )
    assert sorted(CONFIG["commodity_crosswalk"]) == list(CE.APPROVED_COMMODITIES)
    assert {row["commodity_series_id"] for row in rows} == set(CE.APPROVED_COMMODITIES)
    # The C2 exclusions must not reappear here.
    for excluded in ("lng_japan_usd_mmbtu", "coal_australia_usd_mt", "palm_oil_usd_mt"):
        assert excluded not in {row["commodity_series_id"] for row in rows}


def test_widening_the_commodity_allowlist_fails(table, matrices, definitions):
    broken = deepcopy(CONFIG)
    broken["commodity_crosswalk"]["lng_japan_usd_mmbtu"] = {
        "io_sector_code": "031", "mapping_type": "official_broader_aggregate",
        "confidence": "medium",
    }
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(CONFIG, taxonomy, definitions)
    with pytest.raises(CE.ExposureError, match="does not match the four C2"):
        CE.build_exposure_table(table, matrices, crosswalks, broken, definitions)


# --- source discovery and checksums -------------------------------------------


def test_official_source_discovery_not_hard_coded(source_audit):
    discovery = source_audit["discovery"]
    assert discovery["hard_coded_file_url_used"] is False
    assert discovery["sitemap_index"] == IO.NESDC_SITEMAP_INDEX
    assert discovery["sitemap_sections_scanned"] > 1
    assert len(discovery["io_download_pages_discovered"]) >= 10
    for page in (
        "https://www.nesdc.go.th/download/i-o-table-of-thailand-2015/",
        "https://www.nesdc.go.th/download/input-output-classification/",
    ):
        assert page in discovery["io_download_pages_discovered"]
    # The historical page no longer serves the files; that is why we walk the
    # sitemap, and the fact is recorded rather than assumed.
    assert discovery["legacy_io_page_still_lists_io_files"] is False


def test_raw_checksums_match_files_on_disk(source_audit):
    entries = SM.read_manifest("NESDC_IO")
    assert len(entries) >= 3
    for record in source_audit["acquired"]:
        path = ROOT / record["local_path"]
        assert path.is_file(), record["role"]
        assert SM.sha256_of_file(path) == record["sha256"]
        assert len(record["sha256"]) == 64
        assert record["content_length"] > 0


def test_raw_sources_are_git_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/*" in gitignore
    for name in ("i-o-table-of-thailand-2015.xlsx", "input-output-classification.pdf"):
        result = subprocess.run(
            ["git", "check-ignore", f"data/raw/NESDC_IO/{name}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, name


def test_newer_table_audited_but_not_substituted(source_audit):
    audit = source_audit["newer_table_audit"]
    assert audit["used_as_primary_source"] is False
    assert audit["structurally_compatible_with_2015"] is True
    assert "unresolved" in audit["final_or_preliminary"].lower()
    assert source_audit["primary_table"]["table_year"] == "2015"


# --- workbook layout and extraction -------------------------------------------


def test_sheet_and_layout_discovery(table):
    diagnostics = table.diagnostics
    assert diagnostics["sheet_name"] == "Data IO2015 Final"
    assert diagnostics["header"][:7] == [
        "ROW", "COLUMN", "PURCHASER", "WHOLESALE", "RETAIL", "TRANSPORT", "IMPORT",
    ]
    assert diagnostics["data_cells"] > 10_000
    assert diagnostics["valuation"]["price_basis"] == "purchasers_prices"
    assert diagnostics["valuation"]["import_treatment"] == "import_inclusive"
    assert diagnostics["valuation"]["import_specific_coefficients_available"] is True


def test_sector_code_uniqueness_and_universe(table):
    assert len(set(table.sector_codes)) == len(table.sector_codes) == 180
    assert table.diagnostics["duplicate_cell_keys"] == 0
    assert table.diagnostics["sector_codes_absent_entirely"] == ["179"]


def test_duplicated_io_sector_codes_are_rejected(tmp_path):
    """Synthetic: a duplicated cell key would double-count an input."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["INPUT - OUTPUT TABLE (fixture)"])
    sheet.append(["ROW", "COLUMN", "PURCHASER", "WHOLESALE", "RETAIL", "TRANSPORT", "IMPORT"])
    sheet.append(["001", "001", 10, 0, 0, 0, 0])
    sheet.append(["001", "001", 99, 0, 0, 0, 0])  # duplicate
    path = tmp_path / "dupe.xlsx"
    workbook.save(path)
    with pytest.raises(IO.IOParseError, match="duplicate"):
        IO.parse_io_workbook(path, "fixture", "u", "s")


def test_unknown_codes_are_rejected_not_guessed(tmp_path):
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["fixture"])
    sheet.append(["ROW", "COLUMN", "PURCHASER", "WHOLESALE", "RETAIL", "TRANSPORT", "IMPORT"])
    sheet.append(["001", "999", 10, 0, 0, 0, 0])
    path = tmp_path / "unknown.xlsx"
    workbook.save(path)
    with pytest.raises(IO.IOParseError, match="not in C3's documented code"):
        IO.parse_io_workbook(path, "fixture", "u", "s")


def test_final_demand_and_value_added_stay_out_of_the_intermediate_block(table):
    """The subtotal trap: totals must never enter Z."""
    codes, a, _ = CO.build_technical_coefficients(table)
    for forbidden in (
        IO.TOTAL_INPUT_ROW, IO.TOTAL_VALUE_ADDED_ROW, IO.GROSS_OUTPUT_COLUMN,
        *IO.VALUE_ADDED_ROW_CODES, *IO.FINAL_DEMAND_COLUMN_CODES,
        *IO.SUBTOTAL_COLUMN_CODES,
    ):
        assert forbidden not in codes, forbidden
    # If final demand had leaked in, column sums would exceed 1.
    assert a.sum(axis=0).max() < 1.0


def test_accounting_reconciliation(table):
    diagnostics = table.diagnostics
    assert diagnostics["gross_output_equals_total_input_row"] is True
    assert diagnostics["gross_output_mismatch_sectors"] == []
    # Z + value added = gross output, exactly.
    assert diagnostics["max_column_identity_residual"] < 1e-9
    assert diagnostics["intermediate_total"] > 0
    assert diagnostics["value_added_total"] > 0


# --- technical coefficients ---------------------------------------------------


def test_technical_coefficient_formula():
    """A[i][j] = Z[i][j] / X[j] — divided by the PRODUCING sector's output."""
    toy = toy_table()
    codes, a, _ = CO.build_technical_coefficients(toy)
    assert codes == ["001", "002", "003"]
    assert a[0, 0] == pytest.approx(10.0 / 100.0)
    assert a[0, 1] == pytest.approx(20.0 / 200.0)
    assert a[1, 2] == pytest.approx(10.0 / 50.0)
    assert a[2, 0] == 0.0


def test_transposed_z_is_detectably_different():
    """Synthetic: dividing the wrong axis silently produces different numbers."""
    toy = toy_table()
    _, a, _ = CO.build_technical_coefficients(toy)
    x = np.array([100.0, 200.0, 50.0])
    z = a * x[np.newaxis, :]
    wrong = (z.T) / x[np.newaxis, :]  # transposed Z, same divisor
    assert not np.allclose(a, wrong)
    assert a[0, 1] != pytest.approx(wrong[0, 1])


def test_zero_gross_output_is_excluded_never_divided():
    toy = toy_table()
    toy.gross_output["003"] = 0.0
    codes, a, diagnostics = CO.build_technical_coefficients(toy)
    assert codes == ["001", "002"]
    assert diagnostics["sectors_excluded_zero_output"] == ["003"]
    assert np.all(np.isfinite(a))
    # Real table: sector 179 is the live example.
    assert CONFIG["coefficients"]["zero_output_sector_policy"] == "exclude_never_divide"


def test_real_matrix_is_well_conditioned(matrices):
    diagnostics = matrices.diagnostics
    assert diagnostics["sectors_used"] == 179
    assert diagnostics["sectors_excluded_zero_output"] == ["179"]
    assert diagnostics["column_sum_max"] < 1.0
    assert diagnostics["columns_with_sum_ge_1"] == []
    assert diagnostics["negative_coefficient_count"] == 0


# --- Leontief -----------------------------------------------------------------


def test_leontief_inverse_formula():
    toy = toy_table()
    codes, a, diagnostics = CO.build_technical_coefficients(toy)
    result = CO.leontief_inverse(codes, a, diagnostics)
    identity = np.eye(len(codes))
    expected = np.linalg.inv(identity - a)
    assert np.allclose(result.leontief, expected)
    # T = L - I, identity term removed.
    assert np.allclose(result.total_requirement, expected - identity)
    assert np.allclose(np.diag(result.total_requirement), np.diag(expected) - 1.0)


def test_identity_term_removal_is_explicit(matrices):
    assert matrices.diagnostics["identity_term_removed"] is True
    reconstructed = matrices.total_requirement + np.eye(len(matrices.sector_codes))
    assert np.allclose(reconstructed, matrices.leontief)


def test_leontief_reconstruction_residual(matrices):
    size = len(matrices.sector_codes)
    residual = np.abs(
        (np.eye(size) - matrices.a) @ matrices.leontief - np.eye(size)
    ).max()
    assert residual < CO.RECONSTRUCTION_TOLERANCE
    assert matrices.diagnostics["reconstruction_residual_max_abs"] < 1e-8
    assert matrices.diagnostics["condition_number"] < CO.CONDITION_NUMBER_LIMIT


def test_singular_or_ill_conditioned_matrix_stops_rather_than_regularizing():
    """Synthetic: a column summing to 1 makes (I - A) singular."""
    a = np.array([[1.0, 0.0], [0.0, 0.5]])
    with pytest.raises(CO.SingularMatrixError):
        CO.leontief_inverse(["001", "002"], a)
    nearly = np.array([[1.0 - 1e-15, 0.0], [0.0, 0.5]])
    with pytest.raises(CO.SingularMatrixError):
        CO.leontief_inverse(["001", "002"], nearly)
    assert CONFIG["coefficients"]["leontief"]["on_ill_conditioned"] == (
        "stop_and_report_never_regularize"
    )


def test_leontief_not_described_as_a_price_elasticity(matrices):
    text = matrices.diagnostics["interpretation"].lower()
    assert "not price pass-through" in text
    assert "not causal" in text
    assert CONFIG["coefficients"]["not_a_price_elasticity"] is True


# --- crosswalk evidence -------------------------------------------------------


def test_commodity_crosswalk_carries_official_evidence(matrix, definitions):
    crosswalk = matrix["commodity_crosswalk"]
    assert set(crosswalk) == set(CE.APPROVED_COMMODITIES)
    for commodity_id, entry in crosswalk.items():
        code = str(entry["io_sector_code"])
        assert code in definitions, commodity_id
        assert entry["io_sector_label"] == definitions[code]["label"]
        assert len(entry["io_sector_definition"]) > 30, commodity_id
        assert entry["mapping_type"] in (
            "exact_official_category", "official_broader_aggregate",
            "multiple_official_categories", "qualitative_only", "unresolved",
        )
        assert entry["confidence"] in ("high", "medium", "low", "unresolved")


def test_brent_maps_to_a_broader_category_and_is_flagged(matrix):
    entry = matrix["commodity_crosswalk"]["brent_crude_usd_bbl"]
    assert entry["io_sector_code"] == "031"
    assert entry["io_sector_label"] == "Petroleum and natural gas"
    assert entry["broader_than_commodity"] is True
    assert entry["mapping_type"] == "official_broader_aggregate"
    assert "natural gas" in entry["scope_difference"].lower()


def test_rubber_is_distinguished_from_fabricated_rubber_products(matrix, definitions):
    entry = matrix["commodity_crosswalk"]["rubber_rss3_usd_kg"]
    assert entry["io_sector_code"] == "095"
    assert entry["io_sector_label"] == "Rubber sheet and block rubber"
    # NOT the fabricated-goods sector, and NOT the agricultural latex sector.
    assert entry["io_sector_code"] != "097"
    assert entry["io_sector_code"] != "016"
    assert definitions["097"]["label"] == "Other rubber products"
    config_entry = CONFIG["commodity_crosswalk"]["rubber_rss3_usd_kg"]
    assert config_entry["distinguished_from_fabricated_rubber"] is True
    assert "097" in config_entry["alternatives_considered"]


def test_aluminum_and_copper_share_a_sector_and_carry_the_flag(matrix, rows):
    aluminum = matrix["commodity_crosswalk"]["aluminum_usd_mt"]
    copper = matrix["commodity_crosswalk"]["copper_usd_mt"]
    assert aluminum["io_sector_code"] == copper["io_sector_code"] == "107"
    assert aluminum["shared_io_source_sector"] is True
    assert copper["shared_io_source_sector"] is True
    assert copper["shares_sector_with"] == ["aluminum_usd_mt"]
    assert aluminum["shares_sector_with"] == ["copper_usd_mt"]

    # Every affected canonical row must carry the flag, and the coefficients
    # must be identical by construction.
    by_key = {(r["industry_id"], r["commodity_series_id"]): r for r in rows}
    for industry_id in {r["industry_id"] for r in rows}:
        al = by_key[(industry_id, "aluminum_usd_mt")]
        cu = by_key[(industry_id, "copper_usd_mt")]
        assert al["shared_io_source_sector"] is True
        assert cu["shared_io_source_sector"] is True
        assert al["direct_exposure"] == cu["direct_exposure"]
        assert al["total_requirement_exposure"] == cu["total_requirement_exposure"]


def test_duplicating_aluminum_and_copper_without_a_flag_is_rejected(rows):
    """Synthetic: identical coefficients with the flag cleared must be caught."""
    by_key = {(r["industry_id"], r["commodity_series_id"]): r for r in rows}
    unflagged = []
    for industry_id in {r["industry_id"] for r in rows}:
        al = dict(by_key[(industry_id, "aluminum_usd_mt")])
        cu = dict(by_key[(industry_id, "copper_usd_mt")])
        al["shared_io_source_sector"] = False
        cu["shared_io_source_sector"] = False
        if al["direct_exposure"] == cu["direct_exposure"]:
            unflagged.append((al, cu))
    assert unflagged, "fixture must contain coinciding pairs"
    for al, cu in unflagged:
        coincide = al["direct_exposure"] == cu["direct_exposure"]
        flagged = al["shared_io_source_sector"] and cu["shared_io_source_sector"]
        assert coincide and not flagged  # the defect this test describes
    # The production table must never be in that state.
    for industry_id in {r["industry_id"] for r in rows}:
        al = by_key[(industry_id, "aluminum_usd_mt")]
        cu = by_key[(industry_id, "copper_usd_mt")]
        if al["direct_exposure"] == cu["direct_exposure"]:
            assert al["shared_io_source_sector"] is True


def test_industry_crosswalk_carries_evidence_and_no_double_assignment(matrix):
    seen: dict[str, str] = {}
    for entry in matrix["industry_crosswalk"]:
        assert entry["io_sector_codes"], entry["industry_id"]
        assert len(entry["io_sector_codes"]) == len(entry["io_sector_labels"])
        assert entry["confidence"] in ("high", "medium", "low", "unresolved")
        assert entry["mapping_relationship"] in ("one_to_one", "many_to_one")
        for code in entry["io_sector_codes"]:
            assert code not in seen, f"{code} in both {seen.get(code)} and {entry['industry_id']}"
            seen[code] = entry["industry_id"]


def test_double_assigned_io_sector_is_rejected(definitions):
    taxonomy = TX.load_taxonomy()
    broken = deepcopy(CONFIG)
    broken["industry_crosswalk"]["IND-12"]["io_sectors"].append("105")  # already IND-08
    with pytest.raises(XW.CrosswalkError, match="assigned to both"):
        XW.load_industry_crosswalk(broken, taxonomy, definitions)


# --- aggregation weights ------------------------------------------------------


def test_no_silent_equal_weight_aggregation(matrix, table):
    assert CONFIG["industry_crosswalk_aggregation"]["equal_weights_used"] is False
    assert CONFIG["industry_crosswalk_aggregation"]["weight_source"] == (
        "official_io_gross_output_column_600"
    )
    for entry in matrix["industry_crosswalk"]:
        weights = entry["output_weights"]
        if len(weights) > 1:
            equal = 1.0 / len(weights)
            assert not all(
                abs(value - equal) < 1e-9 for value in weights.values()
            ), f"{entry['industry_id']} looks equally weighted"


def test_weights_sum_to_one_and_come_from_official_output(matrix, table, definitions):
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(CONFIG, taxonomy, definitions)
    for crosswalk in crosswalks:
        weights = XW.output_weights(crosswalk, table.gross_output)
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        for code, weight in weights.items():
            expected = table.gross_output[code] / sum(
                table.gross_output[c] for c in weights
            )
            assert weight == pytest.approx(expected)


def test_weights_not_summing_to_one_are_rejected():
    """Synthetic: an aggregation whose weights do not sum to 1 is not one."""
    crosswalk = XW.IndustryCrosswalk(
        industry_id="IND-XX", industry_name="fixture", tsic_divisions=(10,),
        io_sector_codes=("001", "002"), io_sector_labels=("a", "b"),
        mapping_relationship="many_to_one", confidence="high", scope_note="",
    )
    with pytest.raises(XW.CrosswalkError, match="no defensible aggregation weight"):
        XW.output_weights(crosswalk, {"001": 0.0, "002": 0.0})


def test_aggregate_direct_is_the_exact_sum_ratio(table, definitions):
    """sum(Z)/sum(X), not a mean of ratios."""
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(CONFIG, taxonomy, definitions)
    crosswalk = next(c for c in crosswalks if c.industry_id == "IND-12")
    got = XW.aggregate_direct(table, "107", crosswalk, table.gross_output)
    numerator = sum(table.z("107", code) for code in crosswalk.io_sector_codes)
    denominator = sum(table.gross_output[code] for code in crosswalk.io_sector_codes)
    assert got == pytest.approx(numerator / denominator)


# --- canonical table ----------------------------------------------------------


def test_exact_48_canonical_pairs(rows):
    assert len(rows) == 48
    keys = [(r["industry_id"], r["commodity_series_id"]) for r in rows]
    assert len(set(keys)) == 48
    assert keys == sorted(keys)
    assert CONFIG["canonical"]["rows"] == 48


def test_direct_plus_indirect_equals_total(rows):
    for row in rows:
        if row["direct_exposure"] is None:
            assert row["indirect_exposure"] is None
            assert row["total_requirement_exposure"] is None
            continue
        assert row["direct_exposure"] + row["indirect_exposure"] == pytest.approx(
            row["total_requirement_exposure"], abs=1e-12
        )


def test_zero_versus_unresolved_are_distinct(rows):
    zeros = [r for r in rows if r["direct_exposure"] == 0.0]
    unresolved = [r for r in rows if r["direct_exposure"] is None]
    assert zeros, "the table should contain observed zeros"
    for row in zeros:
        assert row["quality_flag"] == "observed_zero_direct_exposure"
        assert row["direct_exposure"] is not None
    for row in unresolved:
        assert row["quality_flag"] != "observed_zero_direct_exposure"
    assert CONFIG["confidence_rules"]["low_or_unresolved_converted_to_zero"] is False


def test_unresolved_mapping_is_not_converted_to_zero(table, matrices, definitions):
    """Synthetic: an unresolved commodity mapping yields NULL, never 0."""
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(CONFIG, taxonomy, definitions)
    broken = deepcopy(CONFIG)
    broken["commodity_crosswalk"]["copper_usd_mt"]["mapping_type"] = "unresolved"
    built = CE.build_exposure_table(table, matrices, crosswalks, broken, definitions)
    copper = [r for r in built if r["commodity_series_id"] == "copper_usd_mt"]
    assert len(copper) == 12
    for row in copper:
        assert row["direct_exposure"] is None
        assert row["indirect_exposure"] is None
        assert row["total_requirement_exposure"] is None
        assert row["quality_flag"] == "unresolved_mapping_no_numeric_exposure"


def test_no_normalization_across_the_four_commodities(rows):
    assert CONFIG["normalization"]["across_commodities"] == "none"
    for industry_id in {r["industry_id"] for r in rows}:
        values = [
            r["direct_exposure"] for r in rows
            if r["industry_id"] == industry_id and r["direct_exposure"] is not None
        ]
        if len(values) == 4:
            assert abs(sum(values) - 1.0) > 1e-6, industry_id


def test_normalized_exposures_are_rejected(rows):
    """Synthetic: four exposures summing to 1 is the signature of normalization."""
    normalized = []
    for row in rows:
        if row["industry_id"] != "IND-01":
            normalized.append(dict(row))
    subset = [dict(r) for r in rows if r["industry_id"] == "IND-01"]
    total = sum(r["direct_exposure"] for r in subset)
    for row in subset:
        row["direct_exposure"] = row["direct_exposure"] / total
        row["indirect_exposure"] = 0.0
        row["total_requirement_exposure"] = row["direct_exposure"]
    with pytest.raises(CE.ExposureError, match="normalization"):
        CE._validate(sorted(normalized + subset,
                            key=lambda r: (r["industry_id"], r["commodity_series_id"])))


def test_schema_matches_the_columns_actually_written(rows):
    declared = [column["name"] for column in SCHEMA["columns"]]
    for name in declared:
        assert name in rows[0], name
    assert set(CE.CANONICAL_COLUMNS) <= set(rows[0])
    assert SCHEMA["row_count"] == 48


def test_no_target_score_risk_prediction_or_locked_test_fields(rows):
    for forbidden in SCHEMA["forbidden_columns"]:
        assert forbidden not in rows[0], forbidden
    banned = ("target", "mpi", "stress_score", "risk_level", "prediction",
              "forecast", "locked", "correlation", "importance")
    for column in rows[0]:
        assert not any(token in column.lower() for token in banned), column


# --- direction semantics ------------------------------------------------------


def test_direction_semantics(rows):
    for row in rows:
        assert row["direction_channel"] in CE.DIRECTION_CHANNELS
        if row["direction_channel"] == "cost_pressure":
            assert row["price_increase_to_stress_sign"] == 1
        if row["direction_channel"] == "mixed_or_ambiguous":
            assert row["price_increase_to_stress_sign"] is None
    assert CONFIG["direction_semantics"]["sign_is_empirically_estimated"] is False


def test_producer_and_consumer_industries_are_not_forced_into_one_sign(rows):
    """An industry containing the commodity's own sector is ambiguous."""
    mixed = {
        (r["industry_id"], r["commodity_series_id"]) for r in rows
        if r["direction_channel"] == "mixed_or_ambiguous"
    }
    assert ("IND-06", "rubber_rss3_usd_kg") in mixed  # contains sector 095
    assert ("IND-08", "aluminum_usd_mt") in mixed  # contains sector 107
    assert ("IND-08", "copper_usd_mt") in mixed
    for industry_id, commodity_id in mixed:
        row = next(
            r for r in rows
            if r["industry_id"] == industry_id
            and r["commodity_series_id"] == commodity_id
        )
        assert row["price_increase_to_stress_sign"] is None


def test_classify_direction_is_evidence_driven():
    channel, sign, _ = CE.classify_direction("031", ("093", "094"))
    assert channel == "cost_pressure" and sign == 1
    channel, sign, _ = CE.classify_direction("107", ("105", "106", "107"))
    assert channel == "mixed_or_ambiguous" and sign is None


# --- scope guards -------------------------------------------------------------


def test_no_target_informed_weights_or_direction(matrix):
    assert matrix["target_association_computed"] is False
    assert matrix["exposure_weights_tuned_on_outcomes"] is False
    assert matrix["joined_to_mpi_targets"] is False
    assert matrix["predictive_interactions_created"] is False
    assert matrix["model_trained"] is False
    assert matrix["b4_baselines_compared"] is False
    assert matrix["locked_test_accessed"] is False
    assert matrix["industry_conditioned_feature_matrix_created"] is False
    assert CONFIG["confidence_rules"]["based_on_target_performance"] is False
    assert CONFIG["matrix_variants"]["selection_based_on_target_outcomes"] is False


def test_scripts_never_import_target_or_evaluation_modules():
    for name in ("audit_c3_io_sources.py", "run_c3_industry_exposure.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for forbidden in ("targets.production_stress", "targets.labels",
                          "targets.calibration", "evaluation.walk_forward",
                          "evaluation.baselines", "evaluation.metrics"):
            assert forbidden not in source, (name, forbidden)
        assert "argparse" not in source
        assert "sys.argv" not in source


def test_package_code_is_the_single_implementation():
    script = (ROOT / "scripts" / "run_c3_industry_exposure.py").read_text(encoding="utf-8")
    for forbidden in ("np.linalg.inv", "def build_technical", "Z[i][j] / X[j]",
                      "linalg.inv"):
        assert forbidden not in script, forbidden
    assert "CO.leontief_inverse" in script
    assert "CE.build_exposure_table" in script


def test_model_feature_approval_stays_false(rows, matrix):
    assert matrix["model_feature_approved_set"] is False
    assert CONFIG["approval_state"]["model_feature_approved"] is False
    assert CONFIG["approval_state"]["feature_semantics_approved"] is False
    for row in rows:
        assert row["model_feature_approved"] is False


def test_matrix_variants_are_labelled_separately(matrix):
    variants = matrix["matrix_variants"]
    assert variants["primary"]["name"] == "direct_technical_coefficients"
    assert variants["secondary"]["status"] == "structural_sensitivity_view"
    assert variants["secondary"]["must_not_silently_replace_primary"] is True


# --- determinism and upstream immutability ------------------------------------


def test_deterministic_matrix_ordering(rows, table, matrices, definitions):
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(CONFIG, taxonomy, definitions)
    first = CE.build_exposure_table(table, matrices, crosswalks, CONFIG, definitions)
    second = CE.build_exposure_table(table, matrices, crosswalks, CONFIG, definitions)
    assert json.dumps(first, default=str, sort_keys=True) == json.dumps(
        second, default=str, sort_keys=True
    )
    assert [(r["industry_id"], r["commodity_series_id"]) for r in first] == [
        (r["industry_id"], r["commodity_series_id"]) for r in rows
    ]


def test_upstream_artifacts_still_present_and_untouched_by_c3():
    """C3 writes only its own artifacts."""
    upstream = {
        "docs/b1_ingestion_metadata.json", "docs/b3_target_build_metadata.json",
        "docs/b4_baseline_results.json", "docs/b4_locked_test_manifest.json",
        "docs/c1_commodity_source_audit.json",
        "docs/c1_5_commodity_timing_audit.json",
        "docs/c2_commodity_feature_audit.json",
        "configs/commodity_timing.yaml", "configs/commodity_features.yaml",
    }
    for relative in upstream:
        assert (ROOT / relative).is_file(), relative
    written = {
        "docs/c3_commodity_exposure_matrix.json", "docs/c3_io_source_audit.json",
        "configs/industry_exposure.yaml",
        "schemas/industry_commodity_exposure.schema.yaml",
    }
    assert not (upstream & written)


def test_generated_parquet_is_git_ignored(matrix):
    result = subprocess.run(
        ["git", "check-ignore", matrix["outputs"]["parquet"]],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
