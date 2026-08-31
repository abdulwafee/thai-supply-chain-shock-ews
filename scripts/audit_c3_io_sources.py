"""Task C3 — discover, acquire and audit the official NESDC I/O sources.

Takes no arguments. Discovery walks NESDC's own sitemap to the official download
pages rather than trusting a remembered file URL, because NESDC migrated their
site and the historical I/O page now serves unrelated content.

    python scripts/audit_c3_io_sources.py
"""

from __future__ import annotations

import http.cookiejar
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import yaml  # noqa: E402

from thai_supply_chain_ews.data import nesdc_input_output as IO  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.matrices import (  # noqa: E402
    aggregation_reconciliation as AR,
)

CONFIG_PATH = PROJECT_ROOT / "configs" / "industry_exposure.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "NESDC_IO"
AUDIT_JSON = PROJECT_ROOT / "docs" / "c3_io_source_audit.json"

SOURCE_ID = "NESDC_IO"

# The three files C3 needs, and what each is for.
WANTED = {
    "https://www.nesdc.go.th/download/i-o-table-of-thailand-2015/": {
        "role": "primary_io_table",
        "table_year": "2015",
        "file_kind": "excel",
    },
    "https://www.nesdc.go.th/download/input-output-classification/": {
        "role": "sector_classification_and_definitions",
        "table_year": None,
        "file_kind": "pdf",
    },
    "https://www.nesdc.go.th/download/i-o-table-of-thailand-2021-180-sectors/": {
        "role": "newer_table_audited_not_used",
        "table_year": "2021",
        "file_kind": "excel",
    },
}

EXTENSIONS = {"excel": ".xlsx", "pdf": ".pdf", "word": ".docx"}


def build_opener() -> urllib.request.OpenerDirector:
    """An opener carrying a cookie jar, for NESDC's WAF challenge."""
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    opener = build_opener()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("=== C3 - official NESDC I/O source discovery and audit ===")

    # --- 1. discovery from NESDC's own sitemap -------------------------------
    sitemap_index, index_meta = IO.fetch(
        IO.NESDC_SITEMAP_INDEX, opener=opener, accept_statuses=(200, 404)
    )
    sitemap_urls = [
        line.split("<loc>")[1].split("</loc>")[0]
        for line in sitemap_index.decode("utf-8", "replace").splitlines()
        if "<loc>" in line and "downloads-sitemap" in line
    ]
    discovered: list[str] = []
    for url in sitemap_urls:
        payload, _ = IO.fetch(url, opener=opener, accept_statuses=(200, 404))
        discovered.extend(
            IO.discover_io_downloads(payload.decode("utf-8", "replace"))
        )
    discovered = sorted(set(discovered))
    print(f"sitemap sections scanned : {len(sitemap_urls)}")
    print(f"official I/O download pages discovered: {len(discovered)}")

    legacy_payload, legacy_meta = IO.fetch(
        IO.NESDC_IO_LEGACY_PAGE, opener=opener, accept_statuses=(200, 404)
    )
    legacy_html = legacy_payload.decode("utf-8", "replace")
    legacy_has_io_files = any(
        token in legacy_html for token in (".xlsx", "ddl=")
    ) and "i-o-table" in legacy_html.lower()

    # --- 2. acquisition ------------------------------------------------------
    acquired = []
    for page_url, spec in WANTED.items():
        if page_url not in discovered:
            raise SystemExit(
                f"C3 FAILED: {page_url} was not found by official sitemap "
                "discovery. Refusing to fall back to a hard-coded file URL."
            )
        page_payload, page_meta = IO.fetch(
            page_url, opener=opener, accept_statuses=(200, 404)
        )
        links = IO.resolve_download_url(page_payload.decode("utf-8", "replace"))
        matching = [link for link in links if link["file_kind"] == spec["file_kind"]]
        if not matching:
            raise SystemExit(
                f"C3 FAILED: no {spec['file_kind']} download link on {page_url}; "
                f"found {links}."
            )
        link = matching[0]
        payload, http_meta = IO.fetch(link["url"], opener=opener)

        final = http_meta["final_url"]
        original_filename = final.rsplit("/", 1)[-1].split("?")[0]
        stem = page_url.rstrip("/").rsplit("/", 1)[-1]
        destination = RAW_DIR / f"{stem}{EXTENSIONS[spec['file_kind']]}"
        destination.write_bytes(payload)
        checksum = SM.sha256_of_file(destination)

        SM.append_manifest_entry(
            SM.ManifestEntry(
                source_id=SOURCE_ID,
                file_path=str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                source_url=link["url"],
                retrieved_at=retrieved_at,
                sha256=checksum,
                content_length=http_meta["content_length"],
                http_status=http_meta["http_status"],
                http_content_type=http_meta["http_content_type"],
                http_last_modified=http_meta["http_last_modified"],
                original_filename=original_filename,
                source_vintage=spec["table_year"],
                url_discovery_method="official_sitemap_then_download_page_ddl",
                landing_page=page_url,
                notes=spec["role"],
            )
        )
        record = {
            "role": spec["role"],
            "table_year": spec["table_year"],
            "landing_page": page_url,
            "ddl_url": link["url"],
            "final_url": final,
            "original_filename": original_filename,
            "local_path": str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "http_status": http_meta["http_status"],
            "http_content_type": http_meta["http_content_type"],
            "http_last_modified": http_meta["http_last_modified"],
            "content_length": http_meta["content_length"],
            "sha256": checksum,
            "retrieved_at": retrieved_at,
        }
        acquired.append(record)
        print(f"  {spec['role']:<38} {http_meta['content_length']:>9,} bytes "
              f"sha={checksum[:16]}")

    # --- 2b. C3-R1: the MEDIA LIBRARY, which C3 never queried ---------------
    # The aggregated workbooks are not linked from any /download/ page. Missing
    # this mechanism is why C3 wrongly reported that no 58-sector table exists.
    media_wanted = {
        "DataIO2015x58": {
            "role": "aggregation_validation_source_58",
            "table_year": "2015",
            "sector_count": 58,
            "expected_title": "58 Sectors",
            "expected_sheet": "DataIO2015x58",
            "stem": "DataIO2015x58",
        },
        "Book_IO2015_EN": {
            "role": "official_publication_2015",
            "table_year": "2015",
            "sector_count": None,
            "expected_title": None,
            "expected_sheet": None,
            "stem": "Book_IO2015_EN",
        },
    }
    media_index = {}
    for search in sorted(media_wanted) + ["DataIO2015x26", "DataIO2015x16"]:
        payload, _ = IO.fetch(
            f"{IO.NESDC_MEDIA_API}?search={search}&per_page=20",
            opener=opener, accept_statuses=(200, 404),
        )
        for record in IO.discover_media_files(payload):
            media_index.setdefault(record["title"], record)
    print(f"media-library files discovered: {len(media_index)} "
          f"({sorted(media_index)})")

    for search, spec in media_wanted.items():
        record = media_index.get(search)
        if record is None:
            raise SystemExit(
                f"C3-R1 FAILED: {search} not found via the official media API."
            )
        payload, http_meta = IO.fetch(record["url"], opener=opener)
        suffix = ".pdf" if record["filename"].lower().endswith(".pdf") else ".xlsx"
        destination = RAW_DIR / f"{spec['stem']}{suffix}"
        destination.write_bytes(payload)
        checksum = SM.sha256_of_file(destination)

        identity = None
        if spec["expected_title"]:
            identity = IO.validate_workbook_identity(
                destination, spec["expected_title"], spec["expected_sheet"]
            )

        SM.append_manifest_entry(
            SM.ManifestEntry(
                source_id=SOURCE_ID,
                file_path=str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                source_url=record["url"],
                retrieved_at=retrieved_at,
                sha256=checksum,
                content_length=http_meta["content_length"],
                http_status=http_meta["http_status"],
                http_content_type=http_meta["http_content_type"],
                http_last_modified=http_meta["http_last_modified"],
                original_filename=record["filename"],
                source_vintage=spec["table_year"],
                url_discovery_method="official_wordpress_media_rest_api",
                landing_page=IO.NESDC_MEDIA_API,
                notes=spec["role"],
            )
        )
        acquired.append(
            {
                "role": spec["role"],
                "table_year": spec["table_year"],
                "landing_page": IO.NESDC_MEDIA_API,
                "ddl_url": record["url"],
                "final_url": http_meta["final_url"],
                "requested_url": http_meta["requested_url"],
                "original_filename": record["filename"],
                "local_path": str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "http_status": http_meta["http_status"],
                "http_content_type": http_meta["http_content_type"],
                "http_last_modified": http_meta["http_last_modified"],
                "content_length": http_meta["content_length"],
                "sha256": checksum,
                "retrieved_at": retrieved_at,
                "waf_retry_count": http_meta.get("waf_attempts"),
                "redirect_followed": http_meta["final_url"] != http_meta["requested_url"],
                "media_id": record["media_id"],
                "media_date": record["date"],
                "sheets": identity["sheets"] if identity else None,
                "internal_title": identity["internal_title"] if identity else None,
                "sector_count": spec["sector_count"],
                "discovery_method": "official_wordpress_media_rest_api",
            }
        )
        print(f"  {spec['role']:<38} {http_meta['content_length']:>9,} bytes "
              f"sha={checksum[:16]}")

    by_role = {record["role"]: record for record in acquired}

    # --- 3. parse and validate the primary table -----------------------------
    primary = by_role["primary_io_table"]
    table = IO.parse_io_workbook(
        PROJECT_ROOT / primary["local_path"], "2015", primary["final_url"],
        primary["sha256"],
    )
    diagnostics = table.diagnostics
    print()
    print(f"primary sheet            : {diagnostics['sheet_name']!r}")
    print(f"data cells               : {diagnostics['data_cells']:,}")
    print(f"duplicate cell keys      : {diagnostics['duplicate_cell_keys']}")
    print(f"gross output == row 210  : {diagnostics['gross_output_equals_total_input_row']}")
    print(f"max column residual      : {diagnostics['max_column_identity_residual']:.3e}")
    print(f"zero-output sectors      : {diagnostics['zero_or_negative_gross_output_sectors']}")

    definitions = IO.parse_sector_definitions(
        PROJECT_ROOT / by_role["sector_classification_and_definitions"]["local_path"]
    )
    print(f"sector labels parsed     : {len(definitions)}")

    # --- 4. audit the newer 2021 table, without substituting it --------------
    newer = by_role["newer_table_audited_not_used"]
    newer_table = IO.parse_io_workbook(
        PROJECT_ROOT / newer["local_path"], "2021", newer["final_url"], newer["sha256"]
    )
    newer_diagnostics = dict(newer_table.diagnostics)
    newer_diagnostics["internal_title"] = IO.validate_workbook_identity(
        PROJECT_ROOT / newer["local_path"], "THAILAND 2021"
    )["internal_title"]
    newer_audit = {
        "table": "I/O TABLE OF THAILAND 2021 (180 Sectors)",
        "used_as_primary_source": False,
        "sheet_name": newer_diagnostics["sheet_name"],
        "data_cells": newer_diagnostics["data_cells"],
        "sector_count": IO.SECTOR_CODE_COUNT,
        "structurally_compatible_with_2015": (
            newer_diagnostics["header"] == diagnostics["header"]
            and newer_table.sector_codes == table.sector_codes
        ),
        "compatibility_basis": (
            "Identical column header and identical 001-180 sector code universe."
        ),
        "gross_output_equals_total_input_row": newer_diagnostics[
            "gross_output_equals_total_input_row"
        ],
        "max_column_identity_residual": newer_diagnostics[
            "max_column_identity_residual"
        ],
        "zero_output_sectors": newer_diagnostics[
            "zero_or_negative_gross_output_sectors"
        ],
        "completeness": (
            "complete"
            if newer_diagnostics["max_column_identity_residual"] < 1e-9
            else "accounting residual present"
        ),
        "final_or_preliminary": (
            "The 2015 file is titled '(Final)' in its own header; the 2021 file "
            "carries no such marker in the sheet, so its final/preliminary status "
            "is NOT established from the file itself and is left unresolved."
        ),
        "decision": (
            "Audited and NOT substituted. Changing the structural reference year "
            "is an explicit decision, not a silent default."
        ),
    }
    print()
    print(f"newer 2021 table         : compatible="
          f"{newer_audit['structurally_compatible_with_2015']} "
          f"used={newer_audit['used_as_primary_source']}")

    # --- 5. classification-vintage caveat ------------------------------------
    classification_caveat = {
        "document_header_states": "Input - Output Table of Thailand 2021",
        "applied_to_table_year": "2015",
        "compatibility_evidence": (
            "Both the 2015 and 2021 workbooks use the same 001-180 code "
            "universe and the same column header, and every code used by C3's "
            "crosswalks resolves to a label in this document."
        ),
        "status": "assumed_stable_across_2015_and_2021_not_independently_verified",
        "note": (
            "NESDC publishes ONE 'I/O Classification and Definition' document, "
            "whose current edition is headed 2021. Whether any sector definition "
            "changed between the 2015 and 2021 vintages is NOT established by "
            "the evidence in hand, and is recorded as a limitation rather than "
            "asserted away."
        ),
    }

    # --- 6. C3-R1: aggregate the 180 table against the official 58 table ----
    record_58 = by_role["aggregation_validation_source_58"]
    table_58 = IO.parse_io_workbook(
        PROJECT_ROOT / record_58["local_path"], "2015", record_58["final_url"],
        record_58["sha256"], sector_count=58,
    )
    reconciliation = AR.reconcile(table, table_58, official_concordance=None)
    invariant = reconciliation["partition_invariant"]
    print()
    print(f"58-sector internal title : {record_58['internal_title']!r}")
    print(f"partition-invariant      : {invariant['exact_matches']}/"
          f"{invariant['checks']} exact, max abs diff "
          f"{invariant['max_absolute_difference']:.3g}")
    print(f"sector-level             : {reconciliation['sector_level']['status']}")
    if not invariant["all_passed"]:
        raise SystemExit(
            "C3-R1 FAILED: a partition-invariant total differs between the "
            f"official 180- and 58-sector tables: {invariant['failed']}. The "
            "180-sector exposure matrix is NOT approved for C4."
        )

    # --- 7. C3-R1: 2021 status from official metadata, never inferred -------
    status_2021 = {
        "table": "I/O TABLE OF THAILAND 2021 (180 Sectors)",
        "internal_title": newer_diagnostics.get("internal_title"),
        "sheet_name": newer_diagnostics["sheet_name"],
        "status": "unresolved",
        "status_evidence": (
            "The 2015 workbook marks its status twice — internal title "
            "'INPUT - OUTPUT TABLE OF THAILAND 2015 (Final)' and sheet name "
            "'Data IO2015 Final'. The 2021 workbook carries NO status marker in "
            "either place, and no official NESDC metadata located here states "
            "whether it is final, preliminary, revised or experimental."
        ),
        "finality_inferred_from_structural_compatibility": False,
        "retained_as": "audit_only",
        "replaces_2015_production_source": False,
    }
    print(f"2021 status              : {status_2021['status']} (audit-only)")

    output = {
        "task": "C3-R1",
        "supersedes": (
            "C3's statement that no official 2015 58-sector workbook exists"
        ),
        "source_discovery_defect": config["source_discovery_defect"],
        "aggregation_reconciliation": reconciliation,
        "newer_table_status_audit": status_2021,
        "crosswalk_version": config["crosswalk_version"],
        "generated_at": retrieved_at,
        "discovery": {
            "sitemap_index": IO.NESDC_SITEMAP_INDEX,
            "sitemap_sections_scanned": len(sitemap_urls),
            "io_download_pages_discovered": discovered,
            "method": "official_sitemap_then_download_page_then_ddl_redirect",
            "hard_coded_file_url_used": False,
            "legacy_io_page": IO.NESDC_IO_LEGACY_PAGE,
            "legacy_io_page_http_status": legacy_meta["http_status"],
            "legacy_io_page_still_lists_io_files": legacy_has_io_files,
            "legacy_io_page_note": (
                "The historical NESDC I/O page returns a WordPress page with no "
                "I/O download links, which is why discovery starts from the "
                "sitemap."
            ),
        },
        "acquired": acquired,
        "primary_table": {
            "table_year": "2015",
            "sha256": primary["sha256"],
            "diagnostics": diagnostics,
        },
        "sector_definitions_parsed": len(definitions),
        "newer_table_audit": newer_audit,
        "classification_vintage_caveat": classification_caveat,
        "expected_vs_actual": config["expected_vs_actual"],
        "target_association_computed": False,
        "locked_test_accessed": False,
        "model_feature_approved_set": False,
    }
    AUDIT_JSON.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"audit written            : {AUDIT_JSON.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
