"""Task C3-R1 — 58-sector source correction and the commodity-proxy gate.

Two things are being defended here:

* that a NEGATIVE discovery result is never again reported as a fact about the
  publisher — C3 said the 58-sector workbook did not exist because one discovery
  mechanism did not find it;
* that a valid coefficient is never mistaken for a valid PROXY.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.data import nesdc_input_output as IO  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import taxonomy as TX  # noqa: E402
from thai_supply_chain_ews.matrices import aggregation_reconciliation as AR  # noqa: E402
from thai_supply_chain_ews.matrices import industry_crosswalk as XW  # noqa: E402
from thai_supply_chain_ews.matrices import proxy_fitness as PF  # noqa: E402

CONFIG = yaml.safe_load(
    (ROOT / "configs" / "industry_exposure.yaml").read_text(encoding="utf-8")
)
SOURCE_AUDIT_JSON = ROOT / "docs" / "c3_io_source_audit.json"
MATRIX_JSON = ROOT / "docs" / "c3_commodity_exposure_matrix.json"


@pytest.fixture(scope="module")
def source_audit():
    return json.loads(SOURCE_AUDIT_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix():
    return json.loads(MATRIX_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(matrix):
    return matrix["canonical_rows"]


@pytest.fixture(scope="module")
def by_role(source_audit):
    return {record["role"]: record for record in source_audit["acquired"]}


@pytest.fixture(scope="module")
def table_180(by_role):
    record = by_role["primary_io_table"]
    return IO.parse_io_workbook(
        ROOT / record["local_path"], "2015", record["final_url"], record["sha256"]
    )


@pytest.fixture(scope="module")
def table_58(by_role):
    record = by_role["aggregation_validation_source_58"]
    return IO.parse_io_workbook(
        ROOT / record["local_path"], "2015", record["final_url"], record["sha256"],
        sector_count=58,
    )


@pytest.fixture(scope="module")
def definitions(by_role):
    return IO.parse_sector_definitions(
        ROOT / by_role["sector_classification_and_definitions"]["local_path"]
    )


# --- WAF transport ------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload=b"ok", status=200, url="https://x/y"):
        self._payload = payload
        self.status = status
        self._url = url
        self.headers = {"Content-Type": "application/octet-stream"}

    def read(self):
        return self._payload

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Opener:
    """Answers with N cookie-challenge 302s, then succeeds."""

    def __init__(self, challenges: int, forever: bool = False):
        self.remaining = challenges
        self.forever = forever
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        if self.forever or self.remaining > 0:
            self.remaining -= 1
            raise urllib.error.HTTPError(
                request.full_url, 302, "Found", {}, None
            )
        return _FakeResponse(url=request.full_url)


def test_cookie_aware_bounded_waf_retry_succeeds():
    opener = _Opener(challenges=1)
    payload, meta = IO.fetch("https://www.nesdc.go.th/x", opener=opener)
    assert payload == b"ok"
    assert meta["waf_attempts"] == 2
    assert opener.calls == 2


def test_same_url_redirect_loop_is_bounded_not_infinite():
    """Synthetic: a WAF that never yields must stop, not spin forever."""
    opener = _Opener(challenges=0, forever=True)
    with pytest.raises(IO.WafChallengeError, match="after 3 attempts"):
        IO.fetch("https://www.nesdc.go.th/x", opener=opener)
    assert opener.calls == IO.WAF_MAX_ATTEMPTS


def test_non_302_errors_are_not_swallowed():
    class Boom:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 500, "Server", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        IO.fetch("https://www.nesdc.go.th/x", opener=Boom())


def test_404_with_body_accepted_only_when_the_caller_opts_in():
    class NotFound:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 404, "NF", {"Content-Type": "text/html"}, None
            )

    class NotFoundWithBody(NotFound):
        def open(self, request, timeout=None):
            error = urllib.error.HTTPError(
                request.full_url, 404, "NF", {"Content-Type": "text/html"}, None
            )
            error.read = lambda: b"<html>content</html>"
            error.url = request.full_url
            raise error

    with pytest.raises(urllib.error.HTTPError):
        IO.fetch("https://x/y", opener=NotFound())  # default: file-download strictness
    payload, meta = IO.fetch(
        "https://x/y", opener=NotFoundWithBody(), accept_statuses=(200, 404)
    )
    assert b"content" in payload
    assert meta["http_status"] == 404


# --- 58-sector workbook -------------------------------------------------------


def test_58_sector_workbook_acquired_and_validated(by_role):
    record = by_role["aggregation_validation_source_58"]
    assert record["original_filename"] == "DataIO2015x58.xlsx"
    assert record["content_length"] == 239507
    assert record["sha256"] == (
        "67c921a83fae15edb52d02e36dc05a83f8f26bbf15826a4b201d0b3a947b5190"
    )
    assert record["sheets"] == ["DataIO2015x58"]
    assert record["internal_title"] == (
        "INPUT - OUTPUT TABLE OF THAILAND 2015 (58 Sectors)"
    )
    assert record["sector_count"] == 58
    assert record["discovery_method"] == "official_wordpress_media_rest_api"
    assert record["http_status"] == 200
    assert record["waf_retry_count"] >= 1
    assert (ROOT / record["local_path"]).is_file()
    assert SM.sha256_of_file(ROOT / record["local_path"]) == record["sha256"]


def test_58_sector_universe_is_exactly_58(table_58):
    assert len(table_58.sector_codes) == 58
    assert table_58.sector_codes[0] == "001"
    assert table_58.sector_codes[-1] == "058"
    assert len(set(table_58.sector_codes)) == 58
    assert table_58.diagnostics["duplicate_cell_keys"] == 0
    assert table_58.diagnostics["max_column_identity_residual"] < 1e-9


def test_58_sector_workbook_is_in_the_source_manifest():
    entries = SM.read_manifest("NESDC_IO")
    checksums = {entry["sha256"] for entry in entries}
    assert (
        "67c921a83fae15edb52d02e36dc05a83f8f26bbf15826a4b201d0b3a947b5190"
        in checksums
    )
    record = next(
        entry for entry in entries
        if entry["original_filename"] == "DataIO2015x58.xlsx"
    )
    assert record["url_discovery_method"] == "official_wordpress_media_rest_api"
    assert record["notes"] == "aggregation_validation_source_58"


def test_raw_58_sector_file_is_git_ignored():
    result = subprocess.run(
        ["git", "check-ignore", "data/raw/NESDC_IO/DataIO2015x58.xlsx"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_html_saved_as_xlsx_is_rejected(tmp_path):
    """Synthetic: an error page under an .xlsx name must not pass as a workbook."""
    fake = tmp_path / "DataIO2015x58.xlsx"
    fake.write_bytes(b"<html><body>Access denied</body></html>")
    with pytest.raises(IO.WorkbookIdentityError, match="not a ZIP-based workbook"):
        IO.validate_workbook_identity(fake, "58 Sectors", "DataIO2015x58")


def test_wrong_internal_title_is_rejected(tmp_path):
    """Synthetic: a real workbook that is a DIFFERENT table must be refused."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "DataIO2015x58"
    sheet.append(["INPUT - OUTPUT TABLE OF THAILAND 2015 (Final)"])
    sheet.append(["ROW", "COLUMN", "PURCHASER", "WHOLESALE", "RETAIL", "TRANSPORT", "IMPORT"])
    path = tmp_path / "wrong.xlsx"
    workbook.save(path)
    with pytest.raises(IO.WorkbookIdentityError, match="does not contain"):
        IO.validate_workbook_identity(path, "58 Sectors", "DataIO2015x58")
    # And a wrong sheet name is caught too.
    with pytest.raises(IO.WorkbookIdentityError, match="expected"):
        IO.validate_workbook_identity(path, "Final", "NotThisSheet")


def test_c3_claim_is_superseded_not_silently_dropped(source_audit):
    defect = source_audit["source_discovery_defect"]
    assert defect["claim_status"] == "FALSE"
    assert "58-sector" in defect["claim_made_by_c3"]
    assert "MEDIA LIBRARY" in defect["root_cause_primary"]
    # Causes that were investigated and ruled out are named, not omitted.
    ruled_out = defect["causes_ruled_out"]
    for key in ("waf_cookie_handling", "same_url_redirect_handling",
                "http_404_with_content_handling"):
        assert "NOT a cause" in ruled_out[key]
    assert CONFIG["expected_vs_actual"]["c3_claim_status"] == (
        "FALSE_superseded_by_c3_r1"
    )


# --- reconciliation -----------------------------------------------------------


def test_180_to_58_crosswalk_is_not_established_and_fails_explicitly():
    with pytest.raises(AR.AggregationCrosswalkUnavailable, match="refuses to infer"):
        AR.build_180_to_58_crosswalk({"001": {}}, None)
    assert CONFIG["sector_aggregation_reconciliation"]["crosswalk_status"] == (
        "not_established"
    )


def test_incomplete_crosswalk_is_rejected():
    """Synthetic: a partial concordance cannot aggregate a table."""
    definitions = {f"{i:03d}": {} for i in range(1, 181)}
    partial = {"001": ["001", "002"]}  # 178 sectors unmapped
    with pytest.raises(AR.ReconciliationError, match="Incomplete concordance"):
        AR.build_180_to_58_crosswalk(definitions, partial)
    duplicated = {"001": ["001"], "002": ["001"]}
    with pytest.raises(AR.ReconciliationError, match="appears in both"):
        AR.build_180_to_58_crosswalk(definitions, duplicated)


def test_partition_invariant_reconciliation_passes_exactly(source_audit):
    reconciliation = source_audit["aggregation_reconciliation"]
    invariant = reconciliation["partition_invariant"]
    assert invariant["all_passed"] is True
    assert invariant["checks"] == 12
    assert invariant["exact_matches"] == 12
    assert invariant["max_absolute_difference"] == 0.0
    assert invariant["failed"] == []
    quantities = {item["quantity"] for item in invariant["comparisons"]}
    for expected in ("gross_output_total", "value_added_total",
                     "intermediate_purchaser_signed_total",
                     "intermediate_import_signed_total",
                     "intermediate_wholesale_absolute_total"):
        assert expected in quantities


def test_sector_level_reconciliation_is_not_executed_not_passed(source_audit):
    """NOT EXECUTED is a third state, distinct from passed and failed."""
    sector = source_audit["aggregation_reconciliation"]["sector_level"]
    assert sector["status"] == "not_executed_official_crosswalk_unavailable"
    assert sector["unexplained_discrepancies"] is None
    assert sector["crosswalk_coverage"] == 0
    assert "distinct from passed" in sector["note"]


def test_tolerance_is_preregistered_and_source_based(source_audit):
    reconciliation = source_audit["aggregation_reconciliation"]
    assert reconciliation["tolerance"] == 0.5
    assert reconciliation["tolerance_preregistered"] is True
    assert "thousand Baht" in reconciliation["tolerance_basis"]
    assert CONFIG["sector_aggregation_reconciliation"]["tolerance"] == 0.5
    assert CONFIG["sector_aggregation_reconciliation"]["tolerance_preregistered"] is True


def test_tolerance_boundary_behaviour(table_180, table_58):
    class Shifted:
        def __init__(self, inner, delta):
            self.inner = inner
            self.gross_output = dict(inner.gross_output)
            self.gross_output["001"] += delta
            self.value_added = inner.value_added
            self.sector_codes = inner.sector_codes

        def z(self, row, column, measure="purchaser"):
            return self.inner.z(row, column, measure)

    # Just inside the tolerance passes; just outside fails.
    inside = AR.reconcile(table_180, Shifted(table_58, 0.4))
    assert inside["partition_invariant"]["all_passed"] is True
    outside = AR.reconcile(table_180, Shifted(table_58, 0.6))
    assert outside["partition_invariant"]["all_passed"] is False
    assert "gross_output_total" in outside["partition_invariant"]["failed"]


def test_unexplained_aggregate_mismatch_is_rejected(table_180, table_58):
    """Synthetic: a material mismatch must be visible, not absorbed."""
    class Broken:
        def __init__(self, inner):
            self.inner = inner
            self.gross_output = {k: v * 1.01 for k, v in inner.gross_output.items()}
            self.value_added = inner.value_added
            self.sector_codes = inner.sector_codes

        def z(self, row, column, measure="purchaser"):
            return self.inner.z(row, column, measure)

    result = AR.reconcile(table_180, Broken(table_58))
    assert result["partition_invariant"]["all_passed"] is False
    assert result["partition_invariant"]["max_relative_difference"] > 1e-3


def test_180_sector_matrix_remains_primary(source_audit, matrix):
    assert source_audit["primary_table"]["table_year"] == "2015"
    assert CONFIG["primary_source_decision"]["primary_remains"] == (
        "180_sector_2015_final"
    )
    assert CONFIG["primary_source_decision"]["replaced_automatically"] is False
    assert CONFIG["aggregation_validation_source"]["is_primary_structural_source"] is False
    assert matrix["io_source"]["sector_count"] == 180


# --- 2021 status --------------------------------------------------------------


def test_2021_status_is_unresolved_and_not_inferred(source_audit):
    status = source_audit["newer_table_status_audit"]
    assert status["status"] == "unresolved"
    assert status["finality_inferred_from_structural_compatibility"] is False
    assert status["retained_as"] == "audit_only"
    assert status["replaces_2015_production_source"] is False
    assert status["internal_title"] == "INPUT - OUTPUT TABLE OF THAILAND 2021"
    assert "(Final)" not in status["internal_title"]
    # The 2015 table, by contrast, marks itself final in two places.
    assert source_audit["primary_table"]["diagnostics"]["sheet_name"] == (
        "Data IO2015 Final"
    )


# --- proxy fitness gate -------------------------------------------------------


def test_quantitative_resolution_is_distinct_from_proxy_fitness(rows):
    assert all(r["quantitative_coefficient_status"] == "resolved" for r in rows)
    statuses = {r["commodity_proxy_fit_status"] for r in rows}
    assert len(statuses) > 1, "all-resolved must not imply all-fit"
    assert "not_fit_for_commodity_specific_use" in statuses
    assert CONFIG["commodity_proxy_fitness"]["medium_confidence_implies_eligibility"] is False
    # Every pair is `medium` crosswalk confidence, yet not every pair is eligible.
    assert {r["mapping_confidence"] for r in rows} == {"medium"}
    assert not all(r["industry_pair_feature_eligible"] for r in rows)


def test_all_48_pairs_carry_the_gate_fields(rows):
    assert len(rows) == 48
    for row in rows:
        for field in ("quantitative_coefficient_status", "commodity_proxy_fit_status",
                      "commodity_proxy_scope", "commodity_proxy_evidence",
                      "industry_pair_feature_eligible", "feature_eligibility_reason",
                      "shared_io_source_sector", "double_counting_risk"):
            assert field in row, field
        assert row["commodity_proxy_fit_status"] in PF.PROXY_FIT_STATUSES
        assert len(row["commodity_proxy_evidence"]) > 40


def test_numeric_coefficient_preserved_when_feature_ineligible(rows):
    ineligible = [r for r in rows if not r["industry_pair_feature_eligible"]]
    assert ineligible, "the gate must actually exclude something"
    for row in ineligible:
        assert row["direct_exposure"] is not None
        assert row["total_requirement_exposure"] is not None
        assert row["quantitative_coefficient_status"] == "resolved"


def test_ineligible_is_not_converted_to_zero(rows):
    ineligible = [r for r in rows if not r["industry_pair_feature_eligible"]]
    nonzero = [r for r in ineligible if r["direct_exposure"] != 0.0]
    assert nonzero, "ineligible pairs must keep their real magnitudes"
    for row in nonzero:
        assert row["direct_exposure"] > 0
    assert CONFIG["commodity_proxy_fitness"]["ineligible_pair_converted_to_zero"] is False


def test_ineligible_pairs_are_not_removed_from_the_audit_table(rows, matrix):
    """Synthetic guard: the table must still contain every one of the 48 pairs."""
    keys = {(r["industry_id"], r["commodity_series_id"]) for r in rows}
    assert len(keys) == 48
    industries = {r["industry_id"] for r in rows}
    assert len(industries) == 12
    for industry in industries:
        assert len([r for r in rows if r["industry_id"] == industry]) == 4
    listed = matrix["proxy_fitness_gate"]["ineligible_pairs"]
    for entry in listed:
        assert (entry["industry_id"], entry["commodity_series_id"]) in keys
    assert CONFIG["commodity_proxy_fitness"]["ineligible_pair_removed_from_audit_table"] is False


def test_ind_12_aluminum_and_copper_are_gated(rows):
    """Required by C3-R1 §8: jewellery-dominated, so not commodity-specific."""
    for commodity in ("aluminum_usd_mt", "copper_usd_mt"):
        row = next(
            r for r in rows
            if r["industry_id"] == "IND-12" and r["commodity_series_id"] == commodity
        )
        assert row["commodity_proxy_fit_status"] in (
            "not_fit_for_commodity_specific_use", "unresolved"
        )
        assert row["industry_pair_feature_eligible"] is False
        assert row["direct_exposure"] == pytest.approx(0.209637, abs=1e-5)
        assert row["dominant_purchasing_component"] == "132"
        assert row["dominant_purchasing_component_share"] > 0.9
        evidence = row["commodity_proxy_evidence"].lower()
        assert "132" in evidence
        assert "precious metal" in evidence or "gold" in evidence


def test_aluminum_copper_double_counting_flag(rows):
    shared = [r for r in rows if r["shared_io_source_sector"]]
    assert len(shared) == 24
    for row in shared:
        assert row["double_counting_risk"] == (
            "shared_io_sector_must_not_be_summed_or_averaged"
        )
    risks = CONFIG["known_proxy_risks"]["aluminum_copper_shared_sector"]
    assert risks["coefficients_independently_measured"] is False
    assert risks["must_not_be_summed"] is True
    assert risks["must_not_be_averaged"] is True
    # Fitness is evaluated per industry, not once for the shared sector.
    by_industry = {}
    for row in shared:
        by_industry.setdefault(row["industry_id"], set()).add(
            row["commodity_proxy_fit_status"]
        )
    assert len({frozenset(v) for v in by_industry.values()}) > 1


def test_unresolved_or_ineligible_cannot_enter_the_default_c4_matrix(matrix):
    policy = matrix["c4_policy"]
    assert policy["c4_matrix_created_in_this_task"] is False
    assert policy["default_matrix_membership"] == (
        "industry_pair_feature_eligible_true_only"
    )
    assert policy["ineligible_or_unresolved_pairs"] == (
        "documented_but_generate_no_default_feature"
    )
    assert policy["primary_structural_matrix"] == "direct_exposure"
    assert policy["sensitivity_matrix"] == "total_requirement_exposure"
    assert policy["sensitivity_is_default"] is False
    for prohibited in ("mixed_or_ambiguous_into_cost_pressure",
                       "missing_proxy_fitness_into_sign_zero",
                       "producer_channel_into_consumer_cost_channel"):
        assert prohibited in policy["forced_conversions_prohibited"]


def test_ambiguous_direction_never_becomes_eligible(rows):
    mixed = [r for r in rows if r["direction_channel"] == "mixed_or_ambiguous"]
    assert len(mixed) == 3
    for row in mixed:
        assert row["price_increase_to_stress_sign"] is None
        assert row["industry_pair_feature_eligible"] is False
        assert row["direct_exposure"] is not None  # coefficient still preserved


def test_broad_category_is_not_automatically_feature_eligible(
    table_180, definitions
):
    """Synthetic: a displaced aggregate must be gated even when resolved."""
    decomposition = {
        "dominant_component": "132",
        "dominant_share": 0.96,
        "contributing_components": 5,
        "direct_purchases_observed": True,
    }
    status, scope, evidence = PF.classify_proxy_fitness(
        "aluminum_usd_mt", "107", "IND-XX", decomposition, definitions,
        CONFIG["commodity_proxy_fitness"]["rules"],
    )
    assert status == "not_fit_for_commodity_specific_use"
    assert scope == "aggregate_dominated_by_precious_metals"
    assert "132" in evidence


def test_eligibility_cannot_be_granted_past_contrary_evidence(rows):
    broken = deepcopy(rows)
    for row in broken:
        if row["commodity_proxy_fit_status"] == "not_fit_for_commodity_specific_use":
            row["industry_pair_feature_eligible"] = True
    with pytest.raises(PF.ProxyFitnessError, match="eligible despite proxy status"):
        PF._validate_gate(broken)


def test_removing_an_ineligible_pair_is_rejected(rows):
    truncated = [r for r in deepcopy(rows) if r["industry_pair_feature_eligible"]]
    with pytest.raises(PF.ProxyFitnessError, match="Expected 48 gated rows"):
        PF._validate_gate(truncated)


def test_shared_sector_without_a_risk_flag_is_rejected(rows):
    broken = deepcopy(rows)
    for row in broken:
        if row["shared_io_source_sector"]:
            row["double_counting_risk"] = "none"
    with pytest.raises(PF.ProxyFitnessError, match="no double-counting risk flag"):
        PF._validate_gate(broken)


def test_target_information_cannot_determine_eligibility(matrix):
    assert matrix["proxy_fitness_gate"]["determined_from_target_information"] is False
    assert CONFIG["commodity_proxy_fitness"]["determined_from_target_information"] is False
    assert matrix["target_association_computed"] is False
    assert matrix["exposure_weights_tuned_on_outcomes"] is False
    assert matrix["locked_test_accessed"] is False
    source = (ROOT / "src" / "thai_supply_chain_ews" / "matrices" /
              "proxy_fitness.py").read_text(encoding="utf-8")
    for forbidden in ("mpi", "target", "correlation", "predict"):
        assert f"import {forbidden}" not in source.lower()
    for forbidden in ("thai_supply_chain_ews.targets",
                      "thai_supply_chain_ews.evaluation"):
        assert forbidden not in source


def test_brent_broad_scope_flag_retained(rows, matrix):
    entry = matrix["commodity_crosswalk"]["brent_crude_usd_bbl"]
    assert entry["broader_than_commodity"] is True
    refining = next(
        r for r in rows
        if r["industry_id"] == "IND-04"
        and r["commodity_series_id"] == "brent_crude_usd_bbl"
    )
    # Refining is the one industry where the aggregate is crude-dominated.
    assert refining["commodity_proxy_fit_status"] == "fit_for_structural_use"
    assert refining["commodity_proxy_scope"] == "crude_petroleum_specific"
    others = [
        r for r in rows
        if r["commodity_series_id"] == "brent_crude_usd_bbl"
        and r["industry_id"] != "IND-04"
    ]
    assert all(
        r["commodity_proxy_fit_status"] == "broad_proxy_use_with_caution"
        for r in others
    )
    assert all(
        r["commodity_proxy_scope"] == "petroleum_and_natural_gas_aggregate"
        for r in others
    )


def test_rubber_raw_versus_fabricated_distinction_retained(rows, matrix):
    entry = matrix["commodity_crosswalk"]["rubber_rss3_usd_kg"]
    assert entry["io_sector_code"] == "095"
    assert CONFIG["known_proxy_risks"]["rubber_raw_versus_fabricated_distinction_retained"] is True
    tyres = next(
        r for r in rows
        if r["industry_id"] == "IND-06"
        and r["commodity_series_id"] == "rubber_rss3_usd_kg"
    )
    assert tyres["dominant_purchasing_component"] == "096"
    assert tyres["commodity_proxy_fit_status"] == "fit_for_structural_use"
    # But IND-06 contains sector 095 itself, so direction stays ambiguous.
    assert tyres["direction_channel"] == "mixed_or_ambiguous"
    assert tyres["industry_pair_feature_eligible"] is False


# --- upstream integrity -------------------------------------------------------


def test_c2_feature_values_remain_unchanged():
    audit = json.loads(
        (ROOT / "docs" / "c2_commodity_feature_audit.json").read_text(encoding="utf-8")
    )
    assert audit["canonical_row_count"] == 1224
    assert audit["expected_canonical_row_count"] == 1224
    assert audit["sensitivity_row_count"] == 1224
    assert audit["reconciliation"]["reconciled"] is True
    assert audit["reconciliation"]["mismatches"] == 0
    assert audit["integrity"]["distinct_lineage_checksums"] == 1224


def test_c3_numeric_exposures_unchanged_by_the_gate(rows):
    """The gate adds fields; it must never move a number."""
    expected = {
        ("IND-04", "brent_crude_usd_bbl"): 0.7102503906879029,
        ("IND-12", "aluminum_usd_mt"): 0.209637,
        ("IND-08", "brent_crude_usd_bbl"): 0.0,
    }
    for (industry, commodity), value in expected.items():
        row = next(
            r for r in rows
            if r["industry_id"] == industry and r["commodity_series_id"] == commodity
        )
        assert row["direct_exposure"] == pytest.approx(value, abs=1e-6)
        assert row["direct_exposure"] + row["indirect_exposure"] == pytest.approx(
            row["total_requirement_exposure"], abs=1e-12
        )


def test_industry_dimension_still_reproduces_b1(rows):
    taxonomy = TX.load_taxonomy()
    assert {r["industry_id"] for r in rows} == set(taxonomy.industry_ids)
    assert len(taxonomy.industries) == 12


def test_crosswalk_module_still_rejects_equal_weights(definitions):
    taxonomy = TX.load_taxonomy()
    crosswalks = XW.load_industry_crosswalk(CONFIG, taxonomy, definitions)
    assert len(crosswalks) == 12
    assert CONFIG["industry_crosswalk_aggregation"]["equal_weights_used"] is False
