"""Audit the World Bank Pink Sheet workbook against the preregistered gate (C1).

Discovery-and-audit only: resolves the current official download URL from the
World Bank landing page, acquires the workbook if it is not already present,
records provenance in a manifest, inspects every sheet, and applies the
eligibility gate in `configs/upstream_commodity_sources.yaml`.

Calls the package implementation — no parsing logic lives here.

Usage:
    python scripts/audit_world_bank_commodities.py
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import world_bank_commodities as WBC  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"
AUDIT_JSON = PROJECT_ROOT / "docs" / "c1_commodity_source_audit.json"
USER_AGENT = "Mozilla/5.0 (research; thai-supply-chain-ews)"


def _opener() -> urllib.request.OpenerDirector:
    context = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))


def discover_workbook_url(landing_page: str, workbook_family: str) -> tuple[str, dict]:
    """Extract the current workbook href from the official landing page.

    Deliberately NOT a hard-coded constant: the World Bank rotates a document
    hash in the path each month, so a URL that worked last month is not evidence
    about this month. The discovery evidence is returned alongside the URL.
    """
    request = urllib.request.Request(landing_page, headers={"User-Agent": USER_AGENT})
    with _opener().open(request, timeout=90) as response:
        status = response.status
        html = response.read().decode("utf-8", errors="replace")
    pattern = re.compile(r'https://[^"\'\s]*' + re.escape(workbook_family))
    matches = sorted(set(pattern.findall(html)))
    if not matches:
        raise RuntimeError(
            f"No {workbook_family} link found on {landing_page}. The page layout may have "
            "changed; refusing to fall back to a stale hard-coded URL."
        )
    vintage = None
    vintage_match = re.findall(r"CMO-Pink-Sheet-([A-Za-z]+-\d{4})", html)
    if vintage_match:
        vintage = vintage_match[0]
    evidence = {
        "landing_page": landing_page,
        "landing_page_http_status": status,
        "method": "extract_href_from_landing_page_html",
        "candidate_urls_found": matches,
        "pink_sheet_vintage_label_on_page": vintage,
    }
    return matches[0], evidence


def acquire(url: str, destination: Path) -> dict:
    """Download unless already present. Returns HTTP metadata."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        header_file = destination.parent / "_response_headers.txt"
        meta = SM.parse_response_headers(header_file) if header_file.is_file() else {}
        meta["already_present"] = True
        return meta
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener().open(request, timeout=180) as response:
        payload = response.read()
        headers = dict(response.headers)
        status = response.status
    destination.write_bytes(payload)
    (destination.parent / "_response_headers.txt").write_text(
        "\n".join(f"{k}: {v}" for k, v in headers.items()), encoding="utf-8"
    )
    return {
        "http_status": status,
        "http_content_type": headers.get("Content-Type"),
        "http_last_modified": headers.get("Last-Modified"),
        "content_length": int(headers["Content-Length"])
        if headers.get("Content-Length", "").isdigit()
        else len(payload),
        "already_present": False,
    }


def main() -> None:
    config = WBC.load_commodity_config()
    primary = config["primary_source"]

    try:
        url, discovery = discover_workbook_url(
            primary["landing_page"], primary["workbook_family"]
        )
    except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
        url = primary["resolved_url_at_last_acquisition"]
        discovery = {
            "landing_page": primary["landing_page"],
            "method": "discovery_failed_fell_back_to_recorded_url",
            "error": str(exc),
            "note": (
                "Discovery could not run in this environment. The recorded URL is used "
                "and this fallback is reported explicitly rather than presented as a "
                "fresh discovery."
            ),
        }

    retrieved_at = SM.utc_now_iso()
    dated_dir = RAW_DIR / "WB_PINKSHEET" / retrieved_at[:10]
    destination = dated_dir / primary["workbook_family"]
    http_meta = acquire(url, destination)

    checksum = SM.sha256_of_file(destination)
    entry = SM.ManifestEntry(
        source_id="WB_PINKSHEET",
        file_path=str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        source_url=url,
        retrieved_at=retrieved_at,
        sha256=checksum,
        content_length=http_meta.get("content_length"),
        http_status=http_meta.get("http_status"),
        http_content_type=http_meta.get("http_content_type"),
        http_last_modified=http_meta.get("http_last_modified"),
        original_filename=primary["workbook_family"],
        source_vintage=discovery.get("pink_sheet_vintage_label_on_page"),
        url_discovery_method=discovery.get("method"),
        landing_page=primary["landing_page"],
    )
    appended = SM.append_manifest_entry(entry)

    workbook = WBC.parse_workbook(destination, config)
    provenance = {
        "source_url": url,
        "downloaded_at_utc": retrieved_at,
        "sha256": checksum,
        "source_vintage": discovery.get("pink_sheet_vintage_label_on_page"),
        "updated_on_in_workbook": workbook.updated_on,
    }
    audits = WBC.audit_candidates(workbook, config, provenance)

    output = {
        "task": "C1",
        "audit_version": config["audit_version"],
        "discovery": discovery,
        "provenance": provenance,
        "manifest_line_appended": appended,
        "workbook": {
            "file": str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "sheets_inspected": workbook.sheet_names,
            "data_sheet": primary["data_sheet"],
            "description_sheet": primary["description_sheet"],
            "labelled_series_columns": len(workbook.labels_by_column),
            "observation_rows": len(workbook.months),
            "first_month": workbook.months[0].isoformat(),
            "last_month": workbook.months[-1].isoformat(),
            "updated_on": workbook.updated_on,
            "description_entries": len(workbook.description_entries),
        },
        "candidates": [asdict(a) for a in audits],
        "status_counts": {
            status: sum(1 for a in audits if a.status == status)
            for status in config["allowed_statuses"]
        },
        "timing": config["timing"],
        "not_in_scope_for_c1": config["not_in_scope_for_c1"],
    }
    with AUDIT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(output, indent=2, ensure_ascii=False, default=str))

    print("=== C1 — World Bank Pink Sheet source audit ===")
    print(f"discovery      : {discovery['method']}")
    print(f"resolved URL   : {url}")
    print(f"vintage        : {provenance['source_vintage']} | {workbook.updated_on}")
    print(f"sha256         : {checksum}")
    print(f"manifest line  : {'appended' if appended else 'already recorded (idempotent)'}")
    print(f"sheets         : {workbook.sheet_names}")
    print(f"series columns : {len(workbook.labels_by_column)} | observations "
          f"{workbook.months[0]} .. {workbook.months[-1]} ({len(workbook.months)} rows)")
    print()
    print(f"{'candidate':<24} {'label':<30} {'unit':<10} {'cover':<9} {'miss%':>6}  status")
    for audit in audits:
        cover = f"{audit.first_observation or '-'}"[:7]
        print(f"{audit.candidate_id:<24} {audit.resolved_source_label:<30} {audit.unit:<10} "
              f"{cover:<9} {audit.missingness_pct:6.2f}  {audit.status}")
        for reason in audit.reasons:
            if audit.status != "source_verified":
                print(f"    - {reason}")
    print()
    print("status counts:", output["status_counts"])
    print(f"\naudit written: {AUDIT_JSON.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
