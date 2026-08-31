"""Task C7 tests — full EPPO archive ingestion and the monthly source table.

Two failure modes drive most of this file.

The first is a **count that quietly changes meaning**. 1,315 document-days were
discovered; fewer were retrieved, fewer still validated, and a month is only
approved when its whole discovered inventory reconciles. Every test that touches
a number checks which of those it is.

The second is a **number that survives review because it looks ordinary**. A
monthly mean built by forward-filling weekends, a blend diesel standing in for
ordinary H-DIESEL, a wholesale column read as ex-refinery, a policy month written
into an evidence field — each produces a plausible float. The synthetic-failure
tests at the end construct exactly those situations and require an explicit
raise, because a silent pass is what the whole task is designed to prevent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.data import eppo_daily_prices as DP
from thai_supply_chain_ews.data import eppo_full_archive as FA
from thai_supply_chain_ews.data import eppo_monthly_prices as MP
from thai_supply_chain_ews.data import eppo_source_availability as AV
from thai_supply_chain_ews.data import eppo_source_lineage as LIN
from thai_supply_chain_ews.data.eppo_latest_vintage_policy import PolicyError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load(
    (ROOT / "configs" / "eppo_monthly_source.yaml").read_text(encoding="utf-8")
)
POLICY = yaml.safe_load(
    (ROOT / "configs" / "eppo_latest_vintage_policy.yaml").read_text(encoding="utf-8")
)
AUDIT = ROOT / "docs" / "c7_eppo_full_archive_audit.json"
C6_AUDIT = ROOT / "docs" / "c6_eppo_archive_audit.json"
C6_5 = ROOT / "docs" / "c6_5_eppo_latest_vintage_decision.json"
DAILY_PARQUET = ROOT / "data" / "interim" / "c7_eppo_daily_prices.parquet"
MONTHLY_PARQUET = ROOT / "data" / "interim" / "c7_eppo_monthly_source.parquet"

requires_run = pytest.mark.skipif(not AUDIT.is_file(), reason="C7 has not been run")
requires_parquet = pytest.mark.skipif(
    not (DAILY_PARQUET.is_file() and MONTHLY_PARQUET.is_file()),
    reason="C7 parquet outputs are not present",
)


def _audit():
    return json.loads(AUDIT.read_text(encoding="utf-8"))


# ===========================================================================
# Fixtures: synthetic workbooks, built so a layout test never depends on the
# live archive being present.
# ===========================================================================
def _write_xlsx(path, sheets):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets:
        sheet = workbook.create_sheet(title=name)
        for row in rows:
            sheet.append(list(row))
    workbook.save(path)
    return path


def _xlsx_2023_rows(date=dt.datetime(2023, 7, 3), hsd=21.7, fo600=16.1659,
                    fo1500=15.3175, hsd_label="H-DIESEL",
                    fo600_label="FO 600 (1) 2%S", fo1500_label="FO 1500 (2) 2%S"):
    return [
        (None, "PRICE STRUCTURE OF PETROLEUM PRODUCT IN BANGKOK"),
        (None, None),
        (None, date),
        (None, None),
        (None, "UNIT: BAHT/LITRE", "EX-REFIN. ", "EXCISE TAX ", "M. TAX ",
         "OIL FUND ", " CONSV. FUND ", "WHOLESALE \n(WS)", "VAT (WS)", "WS&VAT ",
         "MARKETING MARGIN ", "VAT (MM)", "RETAIL "),
        (None, "ULG95", 21.0192, 6.5, 0.65, 9.08, 0.05, 37.2992, 2.61, 39.91,
         2.83, 0.19, 42.94),
        (None, "H-DIESEL B7", 99.0, 1.34, 0.134, 4.5, 0.05, 27.73, 1.94, 29.67,
         2.11, 0.14, 31.94),
        (None, hsd_label, hsd, 1.34, 0.134, 4.5, 0.05, 27.7334, 1.94, 29.67,
         2.11, 0.14, 31.94),
        (None, fo600_label, fo600, 0.64, 0.064, 0.06, 0.05, 16.9799, 1.18, 18.16),
        (None, fo1500_label, fo1500, 0.64, 0.064, 0.06, 0.05, 16.1315, 1.12, 17.26),
        (None, "LPG (BAHT/KILOGRAM)", 17.9256, 2.17, 0.217, 0.6053, 0, 20.91,
         1.46, 22.38, 3.25, 0.22, 25.86),
        (None, None),
        (None, "UNIT: BAHT/LITRE", dt.datetime(2021, 1, 1), dt.datetime(2022, 1, 1)),
        (None, "AVERAGE MARKETING MARGIN OF GASOLINE", 2.14, 1.78),
    ]


@pytest.fixture
def xlsx_2023(tmp_path):
    return _write_xlsx(
        tmp_path / "pt-price-st-2023-7-3.xlsx",
        [("Oil Price Structure", _xlsx_2023_rows())],
    )


@pytest.fixture
def xls_2021(tmp_path):
    """A real ``xls_2021`` workbook, written through xlwt-free means.

    ``xlrd`` only reads legacy ``.xls``; writing one is not worth a dependency,
    so the grid is exercised through :func:`DP.discover_layout` on an ``.xlsx``
    that carries the *xls-era* header vocabulary instead, and the genuine
    ``.xls`` regime is asserted against the live archive where it exists.
    """
    rows = [
        ("PRICE STRUCTURE OF PETROLEUM PRODUCT IN BANGKOK",),
        (dt.datetime(2021, 1, 4),),
        (None,),
        ("UNIT:BAHT/LITRE", "EX-REFIN.", "TAX", "M. TAX", "OIL", "CONSV.",
         "WHOLESALE ", "VAT", "WS&VAT", "MARKETING", "VAT", "RETAIL"),
        ("ULG ", 11.0144, 6.5, 0.65, 6.58, 0.1, 24.8444, 1.73, 26.58, 3.34,
         0.23, 30.16),
        ("H-DIESEL B7", 12.88, 5.99, 0.599, 1.0, 0.1, 20.57, 1.43, 22.01, 2.03,
         0.14, 24.19),
        ("H-DIESEL ", 13.619856, 5.8, 0.58, -2.5, 0.1, 17.599856, 1.23, 18.83,
         2.20, 0.15, 21.19),
        ("FO 600 (1) 2%S", 9.4463, 0.64, 0.064, 0.06, 0.07, 10.2803, 0.71, 10.99),
        ("FO 1500 (2) 2%S", 9.2056, 0.64, 0.064, 0.06, 0.07, 10.0396, 0.70, 10.74),
        ("LPG (UNIT:BAHT/KILO)", 16.6103, 2.17, 0.217, -4.62, 0.0, 14.37, 1.00,
         15.38, 3.25, 0.22, 18.86),
    ]
    return _write_xlsx(tmp_path / "pt-price-st-2021-1-4.xlsx",
                       [("โครงสร้างราคา ", rows)])


def _record(media_id=1, date="2023-07-03", filename="pt-price-st-2023-7-3.xlsx",
            sha256="a" * 64, status="downloaded", path="data/raw/x.xlsx"):
    return FA.RetrievalRecord(
        media_id=media_id, effective_date_filename=date, filename=filename,
        attachment_url=f"https://www.eppo.go.th/wp-content/uploads/{filename}",
        retrieval_status=status, sha256=sha256, bytes=1000, magic="xlsx_zip",
        raw_relative_path=path, downloaded_at_utc="2026-08-28T00:00:00+00:00",
    )


def _daily_row(series="eppo_ex_refinery_fo600_2s", date="2024-01-02", value=10.0,
               label="FO 600 (1) 2%S", media_id=1, flag="ok",
               variant=DP.EXACT_AUDITED_LABEL):
    row = {
        "series_id": series, "source_product_label": label,
        "semantic_regime_id": DP.semantic_regime_id(series, "xlsx_2023", label),
        "effective_date": date, "value": value, "unit": "BAHT/LITRE",
        "price_stage": "ex_refinery", "source_name": "EPPO petroleum price structure",
        "media_id": media_id, "source_url": "https://www.eppo.go.th/x.xlsx",
        "raw_filename": "x.xlsx", "raw_file_sha256": "b" * 64,
        "source_document_sha256": "b" * 64,
        "discovery_method": "official_wordpress_rest",
        "label_variant_status": variant, "quality_flag": flag,
        "downloaded_at_utc": "2026-08-28T00:00:00+00:00",
    }
    row["daily_lineage_checksum"] = LIN.daily_lineage_checksum(row)
    return row


def _inventory(month="2024-01", discovered=2, valid=2, unresolved=(),
               unresolved_kind="identity"):
    inventory = MP.MonthlyInventory(
        month=month, discovered_document_days=discovered,
        retrieval_attempted_days=discovered, successfully_retrieved_days=valid,
        content_valid_document_days=valid, unresolved_days=list(unresolved),
    )
    # monthly_inventory() always splits unresolved days by cause; a helper that
    # left them empty would let a status test pass against an impossible month.
    if unresolved_kind == "identity":
        inventory.unresolved_identity_days = list(unresolved)
    else:
        inventory.unresolved_retrieval_days = list(unresolved)
    return inventory


# ===========================================================================
# 1. Upstream invariants
# ===========================================================================
@requires_run
def test_all_c6_and_c6_5_invariants_reproduced():
    invariants = _audit()["upstream_invariants"]
    assert invariants["all_reproduced"] is True
    assert invariants["failed"] == []
    assert len(invariants["checks"]) >= 20
    for name, check in invariants["checks"].items():
        assert check["reproduced"] is True, name


@requires_run
def test_upstream_counts_match_c6_artifacts_exactly():
    checks = _audit()["upstream_invariants"]["checks"]
    expected = {
        "discovered_media_documents": 5233,
        "distinct_effective_dates": 4976,
        "parity_document_days": 1315,
        "operational_document_days": 1076,
        "parity_months": 65,
        "operational_months": 53,
        "c6_documents_retrieved": 256,
        "c6_documents_validated": 254,
        "c6_partial_audit_rows": 722,
    }
    for name, value in expected.items():
        assert checks[name]["actual"] == value, name


def test_c6_5_policy_fields_are_inherited_not_redecided():
    inherited = CONFIG["inherited_policy"]
    assert inherited["operational_policy_lag_months"] == 2
    assert inherited["operational_lag_is_measured"] is False
    assert inherited["minimum_verified_publication_lag_months"] is None
    assert inherited["point_in_time_values_supported"] is False
    assert inherited["same_month_use_permitted"] is False
    assert inherited["publication_lag_1m_use_permitted"] is False
    for key in ("operational_policy_lag_months", "operational_lag_is_measured",
                "minimum_verified_publication_lag_months",
                "point_in_time_values_supported"):
        assert inherited[key] == POLICY["policy"][key], key


def test_preserved_decisions_and_provenance_are_all_false():
    for key, value in CONFIG["preserved_decisions"].items():
        assert value is False, key
    for key, value in CONFIG["provenance"].items():
        assert value is False, key


# ===========================================================================
# 2. The retrieval denominator
# ===========================================================================
@requires_run
def test_retrieval_attempt_denominator_is_the_1315_discovered_days():
    denominator = _audit()["denominator"]
    assert denominator["distinct_document_days"] == 1315
    assert denominator["discovered_media_records"] >= 1315
    assert denominator["retrieval_attempts"] == denominator["discovered_media_records"]
    assert (denominator["document_days_with_one_attachment"]
            + denominator["document_days_with_multiple_attachment_candidates"]
            == 1315)
    assert denominator["discovered_days_reported_as_validated"] is False


@requires_run
def test_denominator_stages_only_shrink():
    denominator = _audit()["denominator"]
    assert denominator["http_successes"] <= denominator["retrieval_attempts"]
    assert denominator["format_valid_files"] <= denominator["http_successes"]
    assert denominator["content_valid_files"] <= denominator["format_valid_files"]
    assert (denominator["valid_canonical_document_days"]
            + denominator["unresolved_document_days"]
            == denominator["distinct_document_days"])


def test_document_days_grouping_is_deterministic_and_bounded():
    documents = [
        {"media_id": 30, "filename": "pt-price-st-2021-1-8.xls",
         "attachment_url": "u30", "effective_date_filename": "2021-01-08"},
        {"media_id": 10, "filename": "pt-price-st-2021-1-8_1610.xls",
         "attachment_url": "u10", "effective_date_filename": "2021-01-08"},
        {"media_id": 20, "filename": "pt-price-st-2020-12-31.xls",
         "attachment_url": "u20", "effective_date_filename": "2020-12-31"},
    ]
    days = FA.document_days(documents, "2021-01-01", "2021-12-31")
    assert list(days) == ["2021-01-08"]
    assert [c.media_id for c in days["2021-01-08"]] == [10, 30]


def test_denominator_guard_rejects_validated_before_retrieved():
    with pytest.raises(FA.AcquisitionError, match="cannot validate before it arrives"):
        FA.assert_denominator_consistent(1315, 1336, 1000, 1200)


# ===========================================================================
# 3. Acquisition: resumable, idempotent, bounded, WAF-aware
# ===========================================================================
def test_resumable_acquisition_reuses_verified_bytes_without_a_request(tmp_path):
    candidate = FA.CandidateAttachment(
        media_id=7, filename="pt-price-st-2021-1-4.xls",
        attachment_url="https://example.invalid/f.xls",
        effective_date_filename="2021-01-04",
    )
    path = FA.raw_path_for(tmp_path, "2021-01-04", candidate.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"\xd0\xcf\x11\xe0payload"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    calls = []

    def fetch(url):
        calls.append(url)
        return b"", 200, {}

    record = FA.retrieve_candidate(
        candidate, tmp_path, fetch_fn=fetch, sleep_fn=lambda _: None,
        known_record={"sha256": digest, "retrieved_at": "2026-01-01T00:00:00Z"},
    )
    assert calls == []
    assert record.retrieval_status == "cached_checksum_verified"
    assert record.sha256 == digest
    assert record.downloaded_at_utc == "2026-01-01T00:00:00Z"


def test_changed_bytes_on_disk_force_a_refetch(tmp_path):
    candidate = FA.CandidateAttachment(
        media_id=7, filename="f.xls", attachment_url="https://example.invalid/f.xls",
        effective_date_filename="2021-01-04",
    )
    path = FA.raw_path_for(tmp_path, "2021-01-04", "f.xls")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xd0\xcf\x11\xe0tampered")
    fresh = b"\xd0\xcf\x11\xe0fresh"
    record = FA.retrieve_candidate(
        candidate, tmp_path, fetch_fn=lambda url: (fresh, 200, {}),
        sleep_fn=lambda _: None, known_record={"sha256": "0" * 64},
    )
    assert record.retrieval_status == "downloaded"
    assert path.read_bytes() == fresh


def test_manifest_rewrite_is_idempotent_by_checksum_and_media_id(tmp_path):
    records = [_record(media_id=2, date="2021-01-05"), _record(media_id=1)]
    FA.write_checkpoint(tmp_path, records)
    first = FA.manifest_path(tmp_path).read_text(encoding="utf-8")
    FA.write_checkpoint(tmp_path, list(reversed(records)))
    assert FA.manifest_path(tmp_path).read_text(encoding="utf-8") == first
    index = FA.checkpoint_by_media_id(FA.load_checkpoint(tmp_path))
    assert sorted(index) == [1, 2]


def test_bounded_retries_stop_at_max_attempts(tmp_path):
    candidate = FA.CandidateAttachment(
        media_id=1, filename="f.xls", attachment_url="u",
        effective_date_filename="2021-01-04",
    )
    attempts, waits = [], []
    def fetch(url):
        attempts.append(url)
        return None, "TimeoutError", {}
    record = FA.retrieve_candidate(
        candidate, tmp_path, fetch_fn=fetch, sleep_fn=waits.append,
        max_attempts=3, request_interval=0.0,
    )
    assert len(attempts) == 3
    assert record.attempts == 3
    assert record.retrieval_status == "network_error"
    assert waits == list(FA.RETRY_BACKOFF_SECONDS)


def test_http_404_is_not_retried(tmp_path):
    candidate = FA.CandidateAttachment(
        media_id=1, filename="f.xlsx", attachment_url="u",
        effective_date_filename="2026-04-17",
    )
    attempts = []
    def fetch(url):
        attempts.append(url)
        return None, 404, {}
    record = FA.retrieve_candidate(
        candidate, tmp_path, fetch_fn=fetch, sleep_fn=lambda _: None,
        request_interval=0.0,
    )
    assert len(attempts) == 1
    assert record.retrieval_status == "http_error"
    assert record.rejection_reason == "http_404"


def test_html_and_waf_responses_are_rejected_and_never_stored(tmp_path):
    candidate = FA.CandidateAttachment(
        media_id=1, filename="pt-price-st-2024-1-2.xlsx", attachment_url="u",
        effective_date_filename="2024-01-02",
    )
    body = b"<!DOCTYPE html><html><head><title>Attention Required</title>"
    record = FA.retrieve_candidate(
        candidate, tmp_path, fetch_fn=lambda url: (body, 200, {}),
        sleep_fn=lambda _: None, request_interval=0.0,
    )
    assert record.retrieval_status == "waf_or_html_response"
    assert not FA.raw_path_for(tmp_path, "2024-01-02", candidate.filename).exists()


def test_throttle_statuses_classify_as_throttled_not_as_a_missing_document():
    for status in FA.THROTTLE_HTTP_STATUSES:
        outcome, _, reason = FA.classify_response(b"", status, None)
        assert outcome == "throttled", status
        assert str(status) in reason


def test_repeated_throttling_aborts_and_keeps_what_was_verified(tmp_path):
    documents = [
        {"media_id": i, "filename": f"pt-price-st-2021-1-{i}.xls",
         "attachment_url": f"u{i}", "effective_date_filename": f"2021-01-{i:02d}"}
        for i in range(1, 12)
    ]
    with pytest.raises(FA.ThrottleDetected):
        FA.acquire_window(
            documents, "2021-01-01", "2021-01-31", tmp_path,
            fetch_fn=lambda url: (None, 429, {}), sleep_fn=lambda _: None,
            max_consecutive_throttles=3,
        )
    assert FA.manifest_path(tmp_path).is_file()


def test_magic_bytes_decide_format_not_the_extension():
    assert FA.classify_response(b"PK\x03\x04zip", 200, None)[0] == "downloaded"
    assert FA.classify_response(b"\xd0\xcf\x11\xe0ole", 200, None)[0] == "downloaded"
    assert FA.classify_response(b"not a workbook", 200, None)[0] == "unaccepted_format"
    assert FA.classify_response(
        b"PK\x03\x04zip", 200, "text/html; charset=UTF-8"
    )[0] == "waf_or_html_response"


def test_raw_path_follows_the_repository_convention(tmp_path):
    path = FA.raw_path_for(tmp_path, "2024-01-02", "pt-price-st-2024-1-2.xlsx")
    relative = path.relative_to(tmp_path).as_posix()
    assert relative == (
        "data/raw/EPPO_PRICE_STRUCTURE/2024-01/2024-01-02__pt-price-st-2024-1-2.xlsx"
    )


def test_raw_directory_and_generated_parquet_stay_git_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/*" in ignore
    assert "data/interim/*" in ignore
    assert "!data/raw/_manifests/" in ignore


# ===========================================================================
# 4. Layout discovery
# ===========================================================================
def test_known_xlsx_layout_is_recognised_from_its_own_content(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    assert discovery.regime_status == "known_regime"
    assert discovery.layout_regime == "xlsx_2023"
    assert discovery.sheet_used == "Oil Price Structure"
    assert discovery.tax_column_label == "EXCISE TAX"
    assert discovery.unit_label == "BAHT/LITRE"
    assert discovery.embedded_document_date == "2023-07-03"
    assert discovery.date_representation == "datetime_cell"


def test_xls_era_header_vocabulary_resolves_to_the_xls_regime_signature(xls_2021):
    discovery = DP.discover_layout(xls_2021, "xlsx_zip")
    # Same sheet and tax vocabulary as the .xls regime; only the container
    # differs, and the signature says so rather than silently matching.
    assert discovery.tax_column_label == "TAX"
    assert discovery.signature[1] == "โครงสร้างราคา"
    assert DP.layout_signature("xls_ole2", "โครงสร้างราคา ", "TAX") in (
        DP.KNOWN_LAYOUT_SIGNATURES
    )
    assert DP.KNOWN_LAYOUT_SIGNATURES[
        DP.layout_signature("xls_ole2", "โครงสร้างราคา ", "TAX")
    ] == "xls_2021"


@requires_run
def test_live_archive_contains_both_known_regimes_with_reported_spans():
    regimes = _audit()["layout_regimes"]
    assert "xls_2021" in regimes
    assert "xlsx_2023" in regimes
    assert regimes["xls_2021"]["regime_status"] == "known_regime"
    assert regimes["xlsx_2023"]["regime_status"] == "known_regime"
    for entry in regimes.values():
        assert entry["first_effective_date"] <= entry["last_effective_date"]
        assert entry["documents"] >= 1


@requires_run
def test_transition_interval_layout_was_discovered_not_assumed():
    transition = _audit()["transition_interval"]
    assert transition["interval"]["start"] == "2023-02-01"
    assert transition["interval"]["end"] == "2023-06-30"
    assert transition["prior_status"] == "unsampled_transition_interval"
    assert transition["documents_inspected"] > 0
    assert transition["documents_valid"] == transition["documents_inspected"]
    assert set(transition["regimes_observed"]) <= {
        "xls_2021", "xlsx_2023", *transition["additional_regime_discovered"],
    }
    for entry in transition["regimes_observed"].values():
        assert entry["first_effective_date"] <= entry["last_effective_date"]


@requires_run
def test_a_third_regime_is_registered_only_from_an_actual_document():
    regimes = _audit()["layout_regimes"]
    new = {k: v for k, v in regimes.items()
           if v["regime_status"] == "newly_observed_regime"}
    for name, entry in new.items():
        assert entry["documents"] >= 1, name
        assert entry["sheet_used"], name
        assert entry["resolved_columns"].get("ex_refinery") is not None, name


def test_unknown_layout_is_rejected_rather_than_positionally_guessed(tmp_path):
    path = _write_xlsx(tmp_path / "junk.xlsx", [
        ("Sheet1", [("PRICE STRUCTURE OF PETROLEUM PRODUCT",), ("A", "B", "C")]),
    ])
    discovery = DP.discover_layout(path, "xlsx_zip")
    assert discovery.regime_status == "unknown_layout"
    assert discovery.sheet_used is None
    assert discovery.products == []
    validation = DP.validate_against_listing(b"PK\x03\x04", discovery, "2024-01-02")
    assert validation["valid"] is False
    assert validation["rejection_reason"].startswith("unknown_layout")


def test_every_sheet_is_inspected_not_only_the_first(tmp_path):
    path = _write_xlsx(tmp_path / "two.xlsx", [
        ("รายงานราคาน้ำมัน", [("cover sheet",), ("nothing here",)]),
        ("Oil Price Structure", _xlsx_2023_rows()),
    ])
    discovery = DP.discover_layout(path, "xlsx_zip")
    assert discovery.sheet_names == ["รายงานราคาน้ำมัน", "Oil Price Structure"]
    assert discovery.sheet_used == "Oil Price Structure"
    assert len(discovery.products) == 3


def test_forcing_a_document_into_the_wrong_regime_raises(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    with pytest.raises(DP.LayoutError, match="not 'xls_2021'"):
        DP.assert_regime(discovery, "xls_2021")


# ===========================================================================
# 5. Price stage and product identity
# ===========================================================================
def test_ex_refinery_is_extracted_and_never_the_wholesale_column(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    fo600 = next(p for p in discovery.products
                 if p.series_id == "eppo_ex_refinery_fo600_2s")
    assert fo600.ex_refinery == pytest.approx(16.1659)
    assert fo600.wholesale == pytest.approx(16.9799)
    assert fo600.ex_refinery != fo600.wholesale


def test_every_price_stage_is_kept_in_its_own_field(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    hsd = next(p for p in discovery.products if p.series_id == "eppo_ex_refinery_hsd")
    assert hsd.ex_refinery == pytest.approx(21.7)
    assert hsd.excise_tax == pytest.approx(1.34)
    assert hsd.municipal_tax == pytest.approx(0.134)
    assert hsd.wholesale == pytest.approx(27.7334)
    assert hsd.retail == pytest.approx(31.94)
    assert len({hsd.ex_refinery, hsd.wholesale, hsd.retail}) == 3


def test_blend_diesel_is_never_read_as_ordinary_h_diesel(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    hsd = next(p for p in discovery.products if p.series_id == "eppo_ex_refinery_hsd")
    assert hsd.source_product_label == "H-DIESEL"
    # The B7 row carries a deliberately unmistakable 99.0; it must not appear.
    assert hsd.ex_refinery != 99.0
    assert "H-DIESEL B7" in discovery.blend_labels_present


def test_fuel_oil_grades_are_isolated(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    values = {p.series_id: p.ex_refinery for p in discovery.products}
    assert values["eppo_ex_refinery_fo600_2s"] == pytest.approx(16.1659)
    assert values["eppo_ex_refinery_fo1500_2s"] == pytest.approx(15.3175)
    assert (values["eppo_ex_refinery_fo600_2s"]
            != values["eppo_ex_refinery_fo1500_2s"])


def test_lpg_in_baht_per_kilogram_is_excluded_entirely(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    assert all("LPG" not in p.source_product_label for p in discovery.products)
    assert {p.unit for p in discovery.products} == {"BAHT/LITRE"}


def test_exact_label_guard_rejects_substitution():
    with pytest.raises(DP.LayoutError, match="not the exact audited label"):
        DP.assert_exact_product_label("H-DIESEL B7", "eppo_ex_refinery_hsd")
    with pytest.raises(DP.LayoutError, match="not the exact audited label"):
        DP.assert_exact_product_label("FO 1500 (2) 2%S", "eppo_ex_refinery_fo600_2s")
    DP.assert_exact_product_label("H-DIESEL ", "eppo_ex_refinery_hsd")


def test_unconfirmed_label_variant_may_not_be_used_as_the_audited_series():
    with pytest.raises(DP.LayoutError, match="UNCONFIRMED variant"):
        DP.assert_exact_product_label("FO 600 2%S", "eppo_ex_refinery_fo600_2s")


def test_label_variant_is_parsed_but_flagged(tmp_path):
    path = _write_xlsx(tmp_path / "variant.xlsx", [
        ("Oil Price Structure",
         _xlsx_2023_rows(fo600_label="FO 600 2%S", fo1500_label="FO 1500 2%S")),
    ])
    discovery = DP.discover_layout(path, "xlsx_zip")
    variants = {p.series_id: p.label_variant_status for p in discovery.products}
    assert variants["eppo_ex_refinery_fo600_2s"] == DP.UNCONFIRMED_LABEL_VARIANT
    assert variants["eppo_ex_refinery_hsd"] == DP.EXACT_AUDITED_LABEL


@requires_run
def test_reported_labels_and_units_are_exact():
    audit = _audit()
    assert audit["product_identity"]["unit"] == "BAHT/LITRE"
    assert audit["product_identity"]["units_observed"] == ["BAHT/LITRE"]
    labels = audit["product_identity"]["series"]
    assert "H-DIESEL" in labels["eppo_ex_refinery_hsd"]
    assert "FO 600 (1) 2%S" in labels["eppo_ex_refinery_fo600_2s"]
    assert "FO 1500 (2) 2%S" in labels["eppo_ex_refinery_fo1500_2s"]
    for series, series_labels in labels.items():
        for label in series_labels:
            assert "B7" not in label and "B10" not in label and "B20" not in label, series


# ===========================================================================
# 6. Internal-date validation and attachment ranking
# ===========================================================================
def test_internal_date_must_match_the_listing_date(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    good = DP.validate_against_listing(b"PK\x03\x04", discovery, "2023-07-03")
    assert good["valid"] is True
    bad = DP.validate_against_listing(b"PK\x03\x04", discovery, "2023-07-04")
    assert bad["valid"] is False
    assert bad["rejection_reason"].startswith("wrong_date_attachment")
    assert "2023-07-03" in bad["rejection_reason"]


def test_a_wrong_date_document_is_not_accepted_because_of_its_filename(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    validation = DP.validate_against_listing(b"PK\x03\x04", discovery, "2023-07-04")
    with pytest.raises(DP.LayoutError, match="wrong_date_attachment"):
        DP.assert_document_valid(validation, "pt-price-st-2023-7-4.xlsx")


def test_attachment_ranking_is_content_derived_not_encounter_order(xlsx_2023,
                                                                  tmp_path):
    right = DP.discover_layout(xlsx_2023, "xlsx_zip")
    wrong_path = _write_xlsx(tmp_path / "wrong.xlsx", [
        ("Oil Price Structure", _xlsx_2023_rows(date=dt.datetime(2022, 5, 5))),
    ])
    wrong = DP.discover_layout(wrong_path, "xlsx_zip")
    # The WRONG document is first in encounter order and has the lower media ID.
    candidates = [
        (_record(media_id=1, date="2023-07-03"), wrong,
         DP.validate_against_listing(b"PK\x03\x04", wrong, "2023-07-03")),
        (_record(media_id=9, date="2023-07-03", sha256="c" * 64), right,
         DP.validate_against_listing(b"PK\x03\x04", right, "2023-07-03")),
    ]
    ranked = DP.rank_document_candidates(candidates)
    assert ranked[0]["media_id"] == 9
    assert ranked[0]["internal_date_matches_listing"] is True
    assert ranked[1]["accepted"] is False


def test_ranking_is_stable_across_input_orderings(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    validation = DP.validate_against_listing(b"PK\x03\x04", discovery, "2023-07-03")
    candidates = [
        (_record(media_id=m, date="2023-07-03", sha256=str(m) * 64), discovery,
         validation)
        for m in (5, 2, 9)
    ]
    first = [e["media_id"] for e in DP.rank_document_candidates(candidates)]
    second = [e["media_id"] for e in
              DP.rank_document_candidates(list(reversed(candidates)))]
    assert first == second == [2, 5, 9]


# ===========================================================================
# 7. Duplicates, equivalence and conflicts
# ===========================================================================
def _triple(media_id, discovery, date="2023-07-03", sha=None):
    record = _record(media_id=media_id, date=date, sha256=sha or f"{media_id:064d}")
    return (record, discovery,
            DP.validate_against_listing(b"PK\x03\x04", discovery, date))


def test_byte_identical_documents_contribute_once(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    resolution = DP.resolve_document_day("2023-07-03", [
        _triple(1, discovery, sha="d" * 64), _triple(2, discovery, sha="d" * 64),
    ])
    assert resolution.duplicate_documents == 1
    assert resolution.status == "resolved"
    rows = DP.build_daily_rows([resolution])
    assert len(rows) == 3
    assert {r["quality_flag"] for r in rows} == {"duplicate_document"}


def test_content_equivalent_duplicates_contribute_once(xlsx_2023, tmp_path):
    first = DP.discover_layout(xlsx_2023, "xlsx_zip")
    other = _write_xlsx(tmp_path / "same-values.xlsx",
                        [("Oil Price Structure", _xlsx_2023_rows())])
    second = DP.discover_layout(other, "xlsx_zip")
    resolution = DP.resolve_document_day("2023-07-03", [
        _triple(1, first, sha="a" * 64), _triple(2, second, sha="b" * 64),
    ])
    assert resolution.conflicts == []
    assert resolution.content_equivalent_duplicates == 3
    rows = DP.build_daily_rows([resolution])
    assert len(rows) == 3
    assert {r["quality_flag"] for r in rows} == {"content_equivalent_duplicate"}


def test_same_date_conflicting_values_block_rather_than_pick(xlsx_2023, tmp_path):
    first = DP.discover_layout(xlsx_2023, "xlsx_zip")
    other = _write_xlsx(tmp_path / "different.xlsx",
                        [("Oil Price Structure", _xlsx_2023_rows(fo600=99.99))])
    second = DP.discover_layout(other, "xlsx_zip")
    resolution = DP.resolve_document_day("2023-07-03", [
        _triple(1, first, sha="a" * 64), _triple(2, second, sha="b" * 64),
    ])
    assert resolution.status == "same_date_conflicting_value"
    conflict = next(c for c in resolution.conflicts
                    if c["series_id"] == "eppo_ex_refinery_fo600_2s")
    assert sorted(conflict["values"]) == [16.1659, 99.99]
    rows = {r["series_id"]: r for r in DP.build_daily_rows([resolution])}
    blocked = rows["eppo_ex_refinery_fo600_2s"]
    assert blocked["value"] is None
    assert blocked["quality_flag"] == "same_date_conflicting_value"


def test_a_day_whose_only_attachment_fails_is_unresolved_not_absent():
    failed = FA.RetrievalRecord(
        media_id=1, effective_date_filename="2026-04-17", filename="f.xlsx",
        attachment_url="u", retrieval_status="http_error",
        rejection_reason="http_404",
    )
    resolution = DP.resolve_document_day("2026-04-17", [
        (failed, DP.LayoutDiscovery(magic="unknown"),
         {"valid": False, "rejection_reason": "http_404"}),
    ])
    assert resolution.status == "unresolved_document_retrieval"
    assert resolution.products == {}
    assert DP.build_daily_rows([resolution]) == []


@requires_run
def test_wrong_date_attachments_are_reported_without_reassignment():
    for item in _audit()["document_identity"]["wrong_date_attachments"]:
        assert item["reassigned_to_internal_date"] is False
        assert item["counted_as_valid_for_listing_date"] is False
        assert item["listing_date"] != item["internal_date"]
        assert "listing_date_separately_covered" in item
        assert "internal_date_separately_covered" in item


# ===========================================================================
# 8. Canonical daily table
# ===========================================================================
def test_daily_keys_are_unique_and_deterministically_ordered(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    resolutions = [
        DP.resolve_document_day(date, [_triple(index, discovery, date=date)])
        for index, date in enumerate(["2023-07-04", "2023-07-03"], start=1)
    ]
    rows = DP.build_daily_rows(resolutions)
    keys = [(r["series_id"], r["effective_date"], r["semantic_regime_id"])
            for r in rows]
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys)


def test_duplicate_canonical_keys_raise(xlsx_2023):
    discovery = DP.discover_layout(xlsx_2023, "xlsx_zip")
    resolution = DP.resolve_document_day(
        "2023-07-03", [_triple(1, discovery, sha="e" * 64)]
    )
    assert len(DP.build_daily_rows([resolution])) == 3
    with pytest.raises(DP.LayoutError, match="duplicate canonical daily key"):
        DP.build_daily_rows([resolution, resolution])


@requires_parquet
def test_daily_parquet_matches_its_schema():
    import pandas as pd

    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_daily_price.schema.yaml").read_text(encoding="utf-8")
    )
    frame = pd.read_parquet(DAILY_PARQUET)
    declared = [c["name"] for c in schema["observation"]["columns"]]
    assert set(declared) <= set(frame.columns)
    key = schema["observation"]["grain"]
    assert not frame.duplicated(subset=key).any()
    assert frame["source_available_as_of"].isna().all()
    assert (frame["unit"] == "BAHT/LITRE").all()
    assert (frame["price_stage"] == "ex_refinery").all()
    assert frame["point_in_time_supported"].eq(False).all()
    assert frame["latest_vintage_used"].eq(True).all()


@requires_parquet
def test_daily_table_has_no_transformation_or_target_columns():
    import pandas as pd

    frame = pd.read_parquet(DAILY_PARQUET)
    MP.assert_no_transformation_columns(frame.columns)


# ===========================================================================
# 9. Monthly inventory and completeness
# ===========================================================================
def test_expected_issue_count_stays_null_while_the_schedule_is_undocumented():
    inventory = MP.MonthlyInventory(month="2024-01")
    assert inventory.expected_issue_count is None
    assert inventory.expected_schedule_status == "unresolved"
    assert CONFIG["completeness"]["expected_issue_count"] is None
    assert CONFIG["completeness"]["expected_schedule_status"] == "unresolved"
    assert CONFIG["completeness"][
        "weekday_without_discovered_entry_is_missing_document"
    ] is False


@requires_run
def test_monthly_inventory_reconciles_to_the_discovery_denominator():
    audit = _audit()
    per_month = {}
    for entry in audit["monthly_completeness"]:
        per_month[entry["month"]] = entry["discovered_document_days"]
    assert sum(per_month.values()) == audit["denominator"]["distinct_document_days"]
    for entry in audit["monthly_completeness"]:
        assert (entry["content_valid_document_days"] + len(entry["unresolved_days"])
                == entry["discovered_document_days"]), entry["month"]
        assert entry["expected_issue_count"] is None
        assert entry["expected_schedule_status"] == "unresolved"


@requires_run
def test_a_discovered_document_that_failed_is_reported_not_dropped():
    audit = _audit()
    unresolved = audit["document_identity"]["unresolved_document_days"]
    assert audit["denominator"]["unresolved_document_days"] == len(unresolved)
    months = {m["month"]: m for m in audit["monthly_completeness"]}
    for day in unresolved:
        assert day in months[day[:7]]["unresolved_days"]


@requires_run
def test_only_weekdays_and_observed_days_appear_no_weekend_synthesis():
    for entry in _audit()["monthly_completeness"]:
        for weekday, count in entry["observed_weekdays"].items():
            assert count >= 1, weekday
        first, last = entry["first_effective_date"], entry["last_effective_date"]
        if first and last:
            assert first[:7] == entry["month"] and last[:7] == entry["month"]


# ===========================================================================
# 10. Monthly aggregation
# ===========================================================================
def test_arithmetic_mean_of_observed_document_days():
    rows = [_daily_row(date="2024-03-01", value=10.0),
            _daily_row(date="2024-03-04", value=12.0),
            _daily_row(date="2024-03-05", value=14.0)]
    result = MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows,
        _inventory("2024-03", discovered=3, valid=3),
    )
    assert result["monthly_value"] == pytest.approx(12.0)
    assert result["valid_document_day_count"] == 3
    assert result["aggregation_status"] == "approved"
    assert result["first_effective_date"] == "2024-03-01"
    assert result["last_effective_date"] == "2024-03-05"


def test_the_mean_is_not_duration_weighted_and_not_forward_filled():
    # 2024-03-01 stands for four calendar days before the next issue; a
    # duration-weighted or forward-filled mean would be pulled toward 10.0.
    rows = [_daily_row(date="2024-03-01", value=10.0),
            _daily_row(date="2024-03-05", value=20.0)]
    result = MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows,
        _inventory("2024-03", discovered=2, valid=2),
    )
    assert result["monthly_value"] == pytest.approx(15.0)


def test_a_document_day_contributes_once_however_many_copies_carried_it():
    rows = [_daily_row(date="2024-03-01", value=10.0, media_id=1,
                       flag="duplicate_document"),
            _daily_row(date="2024-03-04", value=20.0, media_id=2)]
    result = MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows,
        _inventory("2024-03", discovered=2, valid=2),
    )
    assert result["valid_document_day_count"] == 2
    assert result["monthly_value"] == pytest.approx(15.0)


def test_duplicate_effective_dates_in_the_daily_rows_raise():
    rows = [_daily_row(date="2024-03-01", value=10.0, media_id=1),
            _daily_row(date="2024-03-01", value=20.0, media_id=2)]
    with pytest.raises(MP.AggregationError, match="appears twice"):
        MP.aggregate_series_month(
            "eppo_ex_refinery_fo600_2s", "2024-03", rows, _inventory("2024-03"),
        )


def test_partial_issue_month_observations_are_refused_by_configuration():
    aggregation = CONFIG["monthly_aggregation"]
    assert aggregation["partial_issue_month_observations_used"] is False
    assert aggregation["forward_fill_unchanged_prices"] is False
    assert aggregation["duration_weighting"] is False
    assert aggregation["weekend_or_holiday_observation_synthesised"] is False
    assert aggregation["all_calendar_day_mean"] is False
    assert aggregation["each_valid_document_day_counted_once"] is True


def test_the_statistic_may_not_be_described_as_something_it_is_not():
    MP.assert_statistic_description(MP.MONTHLY_STATISTIC_DESCRIPTION)
    for banned in ("a calendar day mean of ex-refinery prices",
                   "the trading day mean",
                   "the transaction price paid by refiners",
                   "a point in time monthly mean"):
        with pytest.raises(MP.AggregationError):
            MP.assert_statistic_description(banned)


def test_month_range_and_month_key():
    assert MP.month_range("2024-11", "2025-02") == [
        "2024-11", "2024-12", "2025-01", "2025-02",
    ]
    assert MP.month_key("2024-01-31") == "2024-01"


# ===========================================================================
# 11. Approval gate
# ===========================================================================
def test_an_unresolved_document_blocks_approval():
    rows = [_daily_row(date="2024-03-01", value=10.0)]
    result = MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows,
        _inventory("2024-03", discovered=2, valid=1, unresolved=["2024-03-04"]),
    )
    assert result["aggregation_status"] != "approved"
    assert "2024-03-04" in result["quality_flag"]


def test_retrieval_and_identity_failures_get_different_statuses():
    rows = [_daily_row(date="2024-03-01", value=10.0)]
    retrieval = _inventory("2024-03", discovered=2, valid=1,
                           unresolved=["2024-03-04"], unresolved_kind="retrieval")
    assert MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows, retrieval,
    )["aggregation_status"] == "unresolved_document_retrieval"

    identity = _inventory("2024-03", discovered=2, valid=1,
                          unresolved=["2024-03-04"], unresolved_kind="identity")
    assert MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows, identity,
    )["aggregation_status"] == "unresolved_document_identity"

    mixed = _inventory("2024-03", discovered=3, valid=1,
                       unresolved=["2024-03-04", "2024-03-05"])
    mixed.unresolved_retrieval_days = ["2024-03-05"]
    mixed.unresolved_identity_days = ["2024-03-04"]
    assert MP.aggregate_series_month(
        "eppo_ex_refinery_fo600_2s", "2024-03", rows, mixed,
    )["aggregation_status"] == "incomplete_inventory_validation"


def test_every_allowed_status_is_declared_in_the_config():
    assert set(MP.MONTHLY_STATUSES) == set(CONFIG["approval_gate"]["allowed_statuses"])


def test_dataset_approval_lets_a_conditional_series_keep_its_gap():
    table = [
        {"series_id": "eppo_ex_refinery_fo600_2s", "reference_month": "2024-01",
         "aggregation_status": "approved"},
        {"series_id": "eppo_ex_refinery_hsd", "reference_month": "2024-01",
         "aggregation_status": "semantic_definition_gap"},
    ]
    approval = MP.dataset_approval(
        table, ["eppo_ex_refinery_fo600_2s"], "2024-01", "2024-01",
        conditional_series=["eppo_ex_refinery_hsd"],
    )
    assert approval["monthly_aggregation_contract_approved"] is True
    assert approval["per_series"]["eppo_ex_refinery_hsd"][
        "series_conditionally_approved"] is True
    assert approval["blocking_series"] == []


def test_dataset_approval_fails_when_a_required_series_month_fails():
    table = [
        {"series_id": "eppo_ex_refinery_fo600_2s", "reference_month": "2024-01",
         "aggregation_status": "unresolved_document_retrieval"},
    ]
    approval = MP.dataset_approval(
        table, ["eppo_ex_refinery_fo600_2s"], "2024-01", "2024-01",
    )
    assert approval["monthly_aggregation_contract_approved"] is False
    assert approval["blocking_series"] == ["eppo_ex_refinery_fo600_2s"]


@requires_run
def test_reported_approval_is_not_forced():
    audit = _audit()
    approval = audit["approval"]
    blocked = {
        (row["series_id"], row["reference_month"])
        for row in audit["monthly_rows"] if row["aggregation_status"] != "approved"
    }
    for series_id, entry in approval["per_series"].items():
        for month, _status in entry["months_not_approved"]:
            assert (series_id, month) in blocked
        if entry["months_not_approved"]:
            assert entry["series_approved"] is False


# ===========================================================================
# 12. H-DIESEL January 2024
# ===========================================================================
def test_a_blend_only_month_is_a_semantic_gap_with_a_null_value():
    result = MP.aggregate_series_month(
        "eppo_ex_refinery_hsd", "2024-01", [],
        _inventory("2024-01", discovered=22, valid=22), blend_only_days=22,
    )
    assert result["monthly_value"] is None
    assert result["aggregation_status"] == "semantic_definition_gap"
    assert result["quality_flag"] == (
        "ordinary_h_diesel_not_published_blend_substitution_prohibited"
    )


def test_a_partially_published_month_is_a_gap_not_a_shorter_mean():
    rows = [_daily_row(series="eppo_ex_refinery_hsd", date="2023-09-01", value=10.0,
                       label="H-DIESEL")]
    result = MP.aggregate_series_month(
        "eppo_ex_refinery_hsd", "2023-09", rows,
        _inventory("2023-09", discovered=20, valid=20), blend_only_days=19,
    )
    assert result["aggregation_status"] == "semantic_definition_gap"
    assert result["monthly_value"] is None
    assert "1_of_20" in result["quality_flag"]


@requires_run
def test_january_2024_h_diesel_is_null_with_the_documented_gap_status():
    audit = _audit()
    january = audit["h_diesel_january_2024"]
    assert january["absent_for_entire_month"] is True
    assert january["days_with_ordinary_h_diesel"] == []
    assert january["monthly_value"] is None
    assert january["aggregation_status"] == "semantic_definition_gap"
    assert january["blend_substitution_permitted"] is False
    assert january["interpolation_permitted"] is False
    assert january["month_removed_silently"] is False
    assert january["zero_stored"] is False

    row = next(r for r in audit["monthly_rows"]
               if r["series_id"] == "eppo_ex_refinery_hsd"
               and r["reference_month"] == "2024-01")
    assert row["monthly_value"] is None
    assert row["aggregation_status"] == "semantic_definition_gap"
    assert row["quality_flag"] == (
        "ordinary_h_diesel_not_published_blend_substitution_prohibited"
    )


@requires_run
def test_the_h_diesel_absence_is_reported_from_the_full_archive():
    availability = _audit()["ordinary_h_diesel_availability"]
    assert availability["absence_spans"]
    assert availability["c6_reported_absent_days"] == 22
    assert availability["c6_finding_contradicted"] is False
    for span in availability["absence_spans"]:
        assert span["start"] <= span["end"]
        assert span["document_days"] >= 1
    assert (availability["days_with_ordinary_h_diesel"]
            + availability["days_with_blend_only"]
            == availability["valid_document_days"])


@requires_run
def test_no_blend_price_reached_the_h_diesel_series():
    import pandas as pd

    if not DAILY_PARQUET.is_file():
        pytest.skip("daily parquet absent")
    frame = pd.read_parquet(DAILY_PARQUET)
    hsd = frame[frame.series_id == "eppo_ex_refinery_hsd"]
    labels = set(hsd["source_product_label"].dropna())
    assert labels == {"H-DIESEL"}


# ===========================================================================
# 13. Availability contract
# ===========================================================================
def test_policy_available_month_is_reference_plus_two():
    fields = AV.monthly_availability_fields("2024-01")
    assert fields.policy_available_month == "2024-03"
    assert fields.source_available_as_of is None
    assert fields.availability_basis == (
        "conservative_policy_not_historical_measurement"
    )
    assert fields.latest_vintage_used is True
    assert fields.point_in_time_supported is False


def test_writing_a_policy_date_into_the_evidence_field_raises():
    with pytest.raises(PolicyError, match="only carry an evidenced date"):
        AV.monthly_availability_fields("2024-01", source_available_as_of="2024-03")


@pytest.mark.parametrize("issue_month,latest", [
    ("2024-01", "2023-11"), ("2025-03", "2025-01"), ("2026-05", "2026-03"),
])
def test_permitted_reference_month_examples(issue_month, latest):
    assert AV.permitted_reference_month(issue_month) == latest


def _monthly_rows(months):
    return [
        {
            "series_id": "eppo_ex_refinery_fo600_2s", "reference_month": month,
            "monthly_value": 10.0, "source_available_as_of": None,
            "policy_available_month": AV.policy_available_month(month),
        }
        for month in months
    ]


def test_selector_permits_only_reference_months_two_months_back():
    table = _monthly_rows(["2023-10", "2023-11", "2023-12", "2024-01"])
    selected = AV.select_monthly_source_available_at_issue(table, "2024-01")
    months = [r["reference_month"] for r in selected]
    assert months == ["2023-10", "2023-11"]
    assert "2023-12" not in months
    assert "2024-01" not in months


def test_selector_rejects_a_row_whose_policy_stamp_disagrees():
    table = _monthly_rows(["2023-11"])
    table[0]["policy_available_month"] = "2023-12"
    with pytest.raises(PolicyError, match="availability stamps are inconsistent"):
        AV.select_monthly_source_available_at_issue(table, "2024-01")


def test_selector_rejects_a_row_carrying_source_available_as_of():
    table = _monthly_rows(["2023-11"])
    table[0]["source_available_as_of"] = "2023-12-15"
    with pytest.raises(PolicyError, match="must stay null"):
        AV.select_monthly_source_available_at_issue(table, "2024-01")


def test_selector_reads_no_target_or_model_artifact():
    source = Path(
        ROOT / "src" / "thai_supply_chain_ews" / "data" / "eppo_source_availability.py"
    ).read_text(encoding="utf-8")
    for banned in ("targets", "evaluation", "modeling", "build_panel", "mpi"):
        assert f"import {banned}" not in source
        assert f"from .{banned}" not in source


def test_measured_lag_may_not_be_claimed():
    AV.assert_measured_lag_not_claimed(CONFIG["inherited_policy"])
    with pytest.raises(PolicyError, match="conservative project"):
        AV.assert_measured_lag_not_claimed({"operational_lag_is_measured": True})
    with pytest.raises(PolicyError, match="must stay null"):
        AV.assert_measured_lag_not_claimed(
            {"minimum_verified_publication_lag_months": 2}
        )


@requires_run
def test_every_monthly_row_keeps_the_two_availability_fields_apart():
    for row in _audit()["monthly_rows"]:
        assert row["source_available_as_of"] is None
        assert row["policy_available_month"] == AV.policy_available_month(
            row["reference_month"]
        )
        assert row["availability_basis"] == (
            "conservative_policy_not_historical_measurement"
        )
        assert row["latest_vintage_used"] is True
        assert row["point_in_time_supported"] is False


@requires_run
def test_daily_policy_field_is_named_as_a_candidate_not_an_availability_date():
    audit = _audit()
    assert audit["availability"]["daily_policy_field_name"] == (
        "candidate_monthly_policy_available_month"
    )
    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_daily_price.schema.yaml").read_text(encoding="utf-8")
    )
    names = {c["name"] for c in schema["observation"]["columns"]}
    assert "candidate_monthly_policy_available_month" in names
    assert "policy_available_month" not in names


# ===========================================================================
# 14. Lineage
# ===========================================================================
def test_daily_lineage_is_deterministic_and_excludes_acquisition_time():
    row = _daily_row()
    first = LIN.daily_lineage_checksum(row)
    row["downloaded_at_utc"] = "2030-01-01T00:00:00+00:00"
    assert LIN.daily_lineage_checksum(row) == first
    row["value"] = row["value"] + 1e-9
    assert LIN.daily_lineage_checksum(row) != first


def test_daily_lineage_requires_every_declared_field():
    row = _daily_row()
    del row["media_id"]
    with pytest.raises(LIN.LineageError, match="missing lineage fields"):
        LIN.daily_lineage_checksum(row)


def test_monthly_lineage_is_order_independent_but_content_sensitive():
    rows = [_daily_row(date="2024-03-01", value=10.0, media_id=1),
            _daily_row(date="2024-03-04", value=12.0, media_id=2)]
    first = LIN.monthly_lineage_checksum(
        "eppo_ex_refinery_fo600_2s", "2024-03", "c7_v1", rows
    )
    shuffled = LIN.monthly_lineage_checksum(
        "eppo_ex_refinery_fo600_2s", "2024-03", "c7_v1", list(reversed(rows))
    )
    assert first == shuffled
    rows[0]["value"] = 11.0
    rows[0]["daily_lineage_checksum"] = LIN.daily_lineage_checksum(rows[0])
    assert LIN.monthly_lineage_checksum(
        "eppo_ex_refinery_fo600_2s", "2024-03", "c7_v1", rows
    ) != first


def test_monthly_lineage_changes_with_the_rule_version():
    rows = [_daily_row(date="2024-03-01", value=10.0)]
    assert LIN.monthly_lineage_checksum(
        "eppo_ex_refinery_fo600_2s", "2024-03", "c7_v1", rows
    ) != LIN.monthly_lineage_checksum(
        "eppo_ex_refinery_fo600_2s", "2024-03", "c7_v2", rows
    )


@requires_run
def test_monthly_lineage_re_derives_independently_from_the_daily_rows():
    import pandas as pd

    if not DAILY_PARQUET.is_file():
        pytest.skip("daily parquet absent")
    daily = pd.read_parquet(DAILY_PARQUET).to_dict("records")
    checked = 0
    for row in _audit()["monthly_rows"]:
        contributions = [
            r for r in daily
            if r["series_id"] == row["series_id"]
            and str(r["effective_date"])[:7] == row["reference_month"]
            and r["value"] is not None and not pd.isna(r["value"])
        ]
        expected = LIN.monthly_lineage_checksum(
            row["series_id"], row["reference_month"],
            row["aggregation_rule_version"], contributions,
        )
        assert expected == row["monthly_lineage_checksum"], (
            row["series_id"], row["reference_month"]
        )
        checked += 1
    assert checked == 195


@requires_run
def test_monthly_values_re_derive_from_the_canonical_daily_rows():
    import pandas as pd

    if not DAILY_PARQUET.is_file():
        pytest.skip("daily parquet absent")
    daily = pd.read_parquet(DAILY_PARQUET)
    daily = daily[daily["value"].notna()].to_dict("records")
    for row in _audit()["monthly_rows"]:
        if row["monthly_value"] is None:
            continue
        rebuilt = MP.reconstruct_monthly_value(
            daily, row["series_id"], row["reference_month"]
        )
        assert rebuilt == pytest.approx(row["monthly_value"], rel=1e-12)


def test_content_checksum_ignores_generation_time():
    payload = {"a": 1, "generated_at_utc": "2026-01-01", "rows": [
        {"downloaded_at_utc": "2026-01-01", "value": 1.0},
    ]}
    other = {"a": 1, "generated_at_utc": "2030-12-31", "rows": [
        {"downloaded_at_utc": "2030-12-31", "value": 1.0},
    ]}
    assert LIN.content_checksum(payload) == LIN.content_checksum(other)


# ===========================================================================
# 15. Monthly table shape
# ===========================================================================
@requires_run
def test_every_series_month_has_exactly_one_row_including_null_months():
    rows = _audit()["monthly_rows"]
    keys = [(r["series_id"], r["reference_month"], r["aggregation_rule_version"])
            for r in rows]
    assert len(keys) == len(set(keys))
    months = MP.month_range("2021-01", "2026-05")
    for series_id in {r["series_id"] for r in rows}:
        present = sorted(r["reference_month"] for r in rows
                         if r["series_id"] == series_id)
        assert present == months, series_id


@requires_run
def test_null_rows_exist_and_carry_a_status_that_explains_them():
    for row in _audit()["monthly_rows"]:
        if row["monthly_value"] is None:
            assert row["aggregation_status"] != "approved"
            assert row["quality_flag"]
        else:
            assert row["aggregation_status"] in (
                "approved", "unresolved_document_retrieval",
                "unresolved_document_identity", "incomplete_inventory_validation",
            )


@requires_parquet
def test_monthly_parquet_matches_its_schema():
    import pandas as pd

    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_monthly_source.schema.yaml").read_text(
            encoding="utf-8")
    )
    frame = pd.read_parquet(MONTHLY_PARQUET)
    declared = [c["name"] for c in schema["observation"]["columns"]]
    assert set(declared) <= set(frame.columns)
    assert not frame.duplicated(subset=schema["observation"]["grain"]).any()
    assert frame["source_available_as_of"].isna().all()
    MP.assert_no_transformation_columns(frame.columns)


@requires_parquet
def test_parquet_output_is_deterministic_for_identical_content():
    import pandas as pd

    frame = pd.read_parquet(MONTHLY_PARQUET)
    first, second = io.BytesIO(), io.BytesIO()
    frame.to_parquet(first, index=False)
    frame.to_parquet(second, index=False)
    assert first.getvalue() == second.getvalue()


# ===========================================================================
# 16. No transformations, no targets, no models
# ===========================================================================
#: Package modules C7 may never import. Compared against the dotted module
#: path, never as a substring of the whole import line: ``eppo_price_structure``
#: legitimately contains ``structure``, and a substring test would fail on it
#: while missing ``from x import structure``.
FORBIDDEN_IMPORT_MODULES = {
    "modeling", "evaluation", "features", "targets", "structure", "build_panel",
    "sklearn", "joblib", "statsmodels",
}


def _imported_modules(source: str) -> set:
    import ast

    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules.add(base)
            modules.update(f"{base}.{alias.name}".strip(".") for alias in node.names)
    return {segment for module in modules for segment in module.split(".")}


def test_c7_modules_import_no_target_evaluation_or_model_code():
    package = ROOT / "src" / "thai_supply_chain_ews" / "data"
    for name in ("eppo_full_archive", "eppo_daily_prices", "eppo_monthly_prices",
                 "eppo_source_availability", "eppo_source_lineage"):
        source = (package / f"{name}.py").read_text(encoding="utf-8")
        assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES), name


def test_the_runner_never_touches_the_locked_test_or_a_model():
    source = (ROOT / "scripts" / "run_c7_eppo_full_ingestion.py").read_text(
        encoding="utf-8")
    assert not (_imported_modules(source) & FORBIDDEN_IMPORT_MODULES)
    # No path the runner opens may point at an evaluation, model or locked-test
    # artifact. Prose mentioning "locked-test access" is not an access.
    for fragment in ("locked_test", "final_test", "d1_development_predictions",
                     "d3_operational_predictions", "d4_operational_model_predictions",
                     "b4_walk_forward", "targets_table", "industry_month_panel"):
        assert fragment not in source, fragment


def test_transformation_names_are_absent_from_the_config_outputs():
    assert CONFIG["transformations"]["feature_transformations_created"] is False
    assert CONFIG["transformations"]["industry_conditioned_matrix_created"] is False
    assert CONFIG["transformations"]["model_feature_approved"] is False
    for name in ("log_change", "realized_volatility", "z_score", "shock_flag"):
        assert name in CONFIG["transformations"]["prohibited_in_c7"]


def test_transformation_column_guard_catches_a_feature_column():
    MP.assert_no_transformation_columns(["series_id", "monthly_value", "unit"])
    for column in ("log_change_1m_pct", "realized_volatility_3m",
                   "fo600_lag_1", "industry_exposure", "mpi_target"):
        with pytest.raises(MP.AggregationError):
            MP.assert_no_transformation_columns(["series_id", column])


@requires_run
def test_no_exposure_join_or_target_association_is_recorded():
    audit = _audit()
    for key, value in audit["provenance"].items():
        assert value is False, key
    assert audit["c8_authorization"]["predictive_feature_creation_authorized"] is False
    assert audit["c8_authorization"]["target_join_authorized"] is False
    assert audit["c8_authorization"]["modeling_authorized"] is False
    assert audit["c8_authorization"][
        "industry_exposure_multiplication_authorized"] is False


# ===========================================================================
# 17. Upstream artifacts unchanged
# ===========================================================================
@requires_run
def test_c6_and_c6_5_production_artifacts_are_untouched():
    c6 = json.loads(C6_AUDIT.read_text(encoding="utf-8"))
    c65 = json.loads(C6_5.read_text(encoding="utf-8"))
    assert c6["canonical_table"]["rows"] == 722
    assert c6["canonical_table"]["is_partial_audit_table"] is True
    assert c6["retrieval_and_validation"]["documents_retrieved"] == 256
    assert c6["outcome"] == "values_retrievable_timing_unresolved"
    assert c65["decision"] == "proceed_exploratory_release_lag_aware_latest_vintage"
    assert c65["policy"]["operational_policy_lag_months"] == 2
    assert c65["policy"]["operational_lag_is_measured"] is False
    assert c65["ingestion_levels"]["complete_daily_documents_validated"] is False


@requires_run
def test_c7_does_not_rewrite_the_c6_partial_audit_table():
    audit = _audit()
    assert audit["daily_table"]["is_partial_audit_table"] is False
    assert audit["daily_table"]["output"] != (
        "data/interim/c6_eppo_source_observations.parquet"
    )
    schema = yaml.safe_load(
        (ROOT / "schemas" / "eppo_daily_price.schema.yaml").read_text(encoding="utf-8")
    )
    assert schema["supersedes"]["table"] == (
        "data/interim/c6_eppo_source_observations.parquet"
    )


# ===========================================================================
# 18. Synthetic failures. Each must raise explicitly.
# ===========================================================================
def test_synthetic_discovered_days_reported_as_validated():
    with pytest.raises(FA.AcquisitionError):
        FA.assert_denominator_consistent(
            distinct_document_days=1315, retrieval_attempts=0,
            http_successes=0, content_valid_files=1315,
        )


def test_synthetic_transition_file_forced_into_the_wrong_layout(tmp_path):
    path = _write_xlsx(tmp_path / "pt-price-st-2023-3-1.xlsx", [
        ("Oil Price Structure", _xlsx_2023_rows(date=dt.datetime(2023, 3, 1))),
    ])
    discovery = DP.discover_layout(path, "xlsx_zip")
    with pytest.raises(DP.LayoutError, match="refusing to parse it as a layout"):
        DP.assert_regime(discovery, "xls_2021")


def test_synthetic_first_attachment_link_is_the_wrong_one(xlsx_2023, tmp_path):
    wrong_path = _write_xlsx(tmp_path / "wrong.xlsx", [
        ("Oil Price Structure", _xlsx_2023_rows(date=dt.datetime(2019, 1, 1))),
    ])
    wrong = DP.discover_layout(wrong_path, "xlsx_zip")
    validation = DP.validate_against_listing(b"PK\x03\x04", wrong, "2023-07-03")
    with pytest.raises(DP.LayoutError, match="wrong_date_attachment"):
        DP.assert_document_valid(validation, "first link")


def test_synthetic_wrong_date_document_accepted_because_of_its_filename(tmp_path):
    path = _write_xlsx(tmp_path / "pt-price-st-2022-12-5.xlsx", [
        ("Oil Price Structure", _xlsx_2023_rows(date=dt.datetime(2022, 12, 6))),
    ])
    discovery = DP.discover_layout(path, "xlsx_zip")
    validation = DP.validate_against_listing(b"PK\x03\x04", discovery, "2022-12-05")
    assert validation["valid"] is False
    with pytest.raises(DP.LayoutError):
        DP.assert_document_valid(validation, "pt-price-st-2022-12-5.xlsx")


def test_synthetic_conflicting_same_day_values_silently_averaged():
    rows = [
        _daily_row(date="2024-03-01", value=10.0, media_id=1,
                   flag="same_date_conflicting_value"),
    ]
    with pytest.raises(MP.AggregationError, match="never averaged away"):
        MP.aggregate_series_month(
            "eppo_ex_refinery_fo600_2s", "2024-03", rows, _inventory("2024-03"),
        )


def test_synthetic_wholesale_column_parsed_as_ex_refinery(tmp_path):
    rows = _xlsx_2023_rows()
    header = list(rows[4])
    header[2] = "EX-REFIN. WHOLESALE (WS)"      # one column claiming both stages
    header[7] = "WHOLESALE (WS)"
    rows[4] = tuple(header)
    path = _write_xlsx(tmp_path / "collision.xlsx", [("Oil Price Structure", rows)])
    with pytest.raises(DP.LayoutError, match="stage collision"):
        DP.discover_layout(path, "xlsx_zip")


def test_synthetic_h_diesel_b7_used_for_ordinary_h_diesel():
    with pytest.raises(DP.LayoutError, match="substituting a different product"):
        DP.assert_exact_product_label("H-DIESEL B7", "eppo_ex_refinery_hsd")


def test_synthetic_january_2024_filled_by_interpolation():
    row = {
        "series_id": "eppo_ex_refinery_hsd", "reference_month": "2024-01",
        "aggregation_status": "semantic_definition_gap",
        "monthly_value": 21.5,            # interpolated between Dec and Feb
        "valid_document_day_count": 0, "source_available_as_of": None,
        "point_in_time_supported": False,
    }
    with pytest.raises(MP.AggregationError, match="may not be filled"):
        MP.assert_monthly_row_defensible(row, _inventory("2024-01", 22, 22))


def test_synthetic_failed_document_silently_omitted_from_the_monthly_mean():
    row = {
        "series_id": "eppo_ex_refinery_fo600_2s", "reference_month": "2026-04",
        "aggregation_status": "approved", "monthly_value": 22.5,
        "valid_document_day_count": 24, "source_available_as_of": None,
        "point_in_time_supported": False,
    }
    inventory = _inventory("2026-04", discovered=27, valid=24,
                           unresolved=["2026-04-17", "2026-04-18", "2026-04-19"])
    with pytest.raises(MP.AggregationError, match="may not be silently omitted"):
        MP.assert_monthly_row_defensible(row, inventory)


def test_synthetic_duplicate_bytes_counted_twice():
    rows = [_daily_row(date="2024-03-01", value=10.0, media_id=1),
            _daily_row(date="2024-03-01", value=10.0, media_id=1)]
    with pytest.raises(MP.AggregationError, match="may only contribute once"):
        MP.aggregate_series_month(
            "eppo_ex_refinery_fo600_2s", "2024-03", rows, _inventory("2024-03"),
        )


def test_synthetic_policy_lag_described_as_measured():
    with pytest.raises(PolicyError, match="conservative project policy"):
        AV.assert_measured_lag_not_claimed({
            "operational_lag_is_measured": True,
            "operational_policy_lag_months": 2,
        })


def test_synthetic_source_available_as_of_populated_from_policy():
    with pytest.raises(PolicyError, match="present an assumption as provenance"):
        AV.monthly_availability_fields(
            "2024-01", source_available_as_of=AV.policy_available_month("2024-01")
        )
    row = {
        "series_id": "eppo_ex_refinery_fo600_2s", "reference_month": "2024-01",
        "aggregation_status": "approved", "monthly_value": 10.0,
        "valid_document_day_count": 2, "source_available_as_of": "2024-03",
        "point_in_time_supported": False,
    }
    with pytest.raises(MP.AggregationError, match="release timing was never measured"):
        MP.assert_monthly_row_defensible(row, _inventory("2024-01"))


def test_synthetic_t_minus_1_observation_returned_at_issue_t():
    table = _monthly_rows(["2023-12"])
    assert AV.select_monthly_source_available_at_issue(table, "2024-01") == []
    from thai_supply_chain_ews.data.eppo_latest_vintage_policy import (
        assert_reference_month_permitted,
    )
    with pytest.raises(PolicyError, match="exceeds the latest permitted"):
        assert_reference_month_permitted("2023-12", "2024-01")


def test_synthetic_monthly_value_described_as_point_in_time():
    with pytest.raises(MP.AggregationError, match="point_in_time_monthly_mean"):
        MP.assert_statistic_description(
            "the point in time monthly mean of ex-refinery prices"
        )
    row = {
        "series_id": "eppo_ex_refinery_fo600_2s", "reference_month": "2024-01",
        "aggregation_status": "approved", "monthly_value": 10.0,
        "valid_document_day_count": 2, "source_available_as_of": None,
        "point_in_time_supported": True,
    }
    with pytest.raises(MP.AggregationError, match="claims point-in-time"):
        MP.assert_monthly_row_defensible(row, _inventory("2024-01"))


def test_synthetic_log_change_or_volatility_feature_created_in_c7():
    for column in ("fo600_log_change_1m_pct", "fo600_realized_volatility_3m_pct"):
        with pytest.raises(MP.AggregationError, match="predictive transformation"):
            MP.assert_no_transformation_columns(
                ["series_id", "reference_month", column]
            )


# ===========================================================================
# 19. Reconciliation against the acquired archive itself
# ===========================================================================
MANIFEST = ROOT / "data" / "raw" / "_manifests" / "EPPO_PRICE_STRUCTURE_manifest.jsonl"
requires_manifest = pytest.mark.skipif(
    not MANIFEST.is_file(), reason="the EPPO manifest has not been written"
)


def _manifest_records():
    return [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@requires_manifest
def test_manifest_covers_every_discovered_candidate_exactly_once():
    records = _manifest_records()
    media_ids = [r["extra"]["media_id"] for r in records]
    assert len(media_ids) == len(set(media_ids))
    assert len({r["source_vintage"] for r in records}) == 1315


@requires_manifest
def test_manifest_checksums_match_the_files_on_disk():
    checked = 0
    for record in _manifest_records():
        if record["extra"].get("retrieval_status") not in (
            "downloaded", "cached_checksum_verified"
        ):
            continue
        path = ROOT / record["file_path"]
        if not path.is_file():
            pytest.fail(f"manifest records a missing file: {record['file_path']}")
        assert FA.sha256_bytes(path.read_bytes()) == record["sha256"], path.name
        checked += 1
    assert checked >= 1300


@requires_manifest
def test_no_error_page_was_stored_under_a_spreadsheet_name():
    for record in _manifest_records():
        if record["extra"].get("retrieval_status") not in (
            "downloaded", "cached_checksum_verified"
        ):
            continue
        head = (ROOT / record["file_path"]).read_bytes()[:8]
        assert head[:4] in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0"), record["file_path"]


@requires_parquet
@requires_manifest
def test_no_effective_date_was_synthesised():
    import pandas as pd

    discovered = {r["source_vintage"] for r in _manifest_records()}
    frame = pd.read_parquet(DAILY_PARQUET)
    observed = {str(d) for d in frame["effective_date"]}
    assert observed <= discovered
    # And nothing was carried into a day the archive did not publish.
    assert not (observed - discovered)


@requires_parquet
def test_every_daily_value_belongs_to_its_own_reference_month():
    import pandas as pd

    daily = pd.read_parquet(DAILY_PARQUET)
    monthly = pd.read_parquet(MONTHLY_PARQUET)
    valued = daily[daily["value"].notna()]
    for row in monthly.to_dict("records"):
        if row["monthly_value"] is None or pd.isna(row["monthly_value"]):
            continue
        subset = valued[
            (valued["series_id"] == row["series_id"])
            & (valued["effective_date"].astype(str).str[:7] == row["reference_month"])
        ]
        assert len(subset) == row["valid_document_day_count"]
        assert subset["value"].mean() == pytest.approx(row["monthly_value"], rel=1e-12)
        assert str(subset["effective_date"].min()) == row["first_effective_date"]
        assert str(subset["effective_date"].max()) == row["last_effective_date"]


@requires_parquet
def test_daily_rows_carry_no_imputed_or_forward_filled_value():
    import pandas as pd

    daily = pd.read_parquet(DAILY_PARQUET).sort_values(
        ["series_id", "effective_date"]
    )
    for series_id, group in daily.groupby("series_id"):
        values = group["value"].dropna()
        # A forward-filled series repeats its previous value across most days;
        # the published archive changes price on the large majority of issues.
        repeats = (values.diff() == 0).mean()
        assert repeats < 0.5, (series_id, repeats)


@requires_run
@requires_parquet
def test_reported_daily_row_counts_match_the_parquet():
    import pandas as pd

    audit = _audit()
    frame = pd.read_parquet(DAILY_PARQUET)
    assert len(frame) == audit["daily_table"]["rows"]
    counts = frame["series_id"].value_counts().to_dict()
    assert counts == audit["daily_table"]["series_counts"]
