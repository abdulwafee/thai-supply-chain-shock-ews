"""Audit Pink Sheet publication timing and revisions (Task C1.5, revised C1.5-R1).

C1.5-R1 CORRECTION. The first run searched only the commodity-markets landing
page and the report-archive page, and matched only the hyphenated filename form
`CMO-Pink-Sheet-<Month>-<Year>.pdf`. It found 3 issues and concluded 62 of 65
were missing. That conclusion was wrong: it was incomplete discovery, not
evidence of absence. Official document-detail pages expose older issues through
MAIN DOCUMENT links (which use a squashed filename) and RELATED link lists.

This revision discovers from four official seed pages, builds a full 65-row
expected-issue inventory, and reconstructs first-release values from the
earliest verified issue for each completed reference month.

Calls package implementations — no extraction or timing logic lives here.

Creates no features, joins nothing to MPI, computes no target association, and
never touches B4's locked test.

Usage:
    python scripts/audit_c1_5_commodity_timing.py
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from thai_supply_chain_ews.data import commodity_timing as CT  # noqa: E402
from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import world_bank_pink_sheet_vintages as V  # noqa: E402

AUDIT_JSON = PROJECT_ROOT / "docs" / "c1_5_commodity_timing_audit.json"
C1_TABLE = PROJECT_ROOT / "data" / "interim" / "commodity_month.parquet"
USER_AGENT = "Mozilla/5.0 (research; thai-supply-chain-ews)"

# Required issue range: February 2021 .. June 2026, which first exposes
# reference months 2021-01 .. 2026-05.
FIRST_EXPECTED_ISSUE = date(2021, 2, 1)
LAST_EXPECTED_ISSUE = date(2026, 6, 1)

GUARDED = {
    "b1_panel": PROJECT_ROOT / "data" / "processed" / "industry_month_panel.parquet",
    "b3_monthly": PROJECT_ROOT / "data" / "targets" / "production_stress_month.parquet",
    "b3_labels": PROJECT_ROOT / "data" / "targets" / "forecast_target_raw.parquet",
    "b4_predictions": PROJECT_ROOT / "data" / "model_input"
    / "b4_walk_forward_predictions.parquet",
    "c1_commodity_table": C1_TABLE,
}


def _opener():
    context = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))


def fetch_text(url: str) -> tuple[str, int]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener().open(request, timeout=120) as response:
        return response.read().decode("utf-8", errors="replace"), response.status


def fetch_bytes(url: str) -> tuple[bytes, dict]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener().open(request, timeout=180) as response:
        payload = response.read()
        return payload, {
            "http_status": response.status,
            "http_content_type": response.headers.get("Content-Type"),
            "http_last_modified": response.headers.get("Last-Modified"),
            "content_length": len(payload),
            # Redirects are recorded, not discarded: the URL that actually
            # served the bytes is part of the document's identity.
            "final_url": response.geturl(),
        }


def expected_issue_months() -> list[str]:
    months, cursor = [], FIRST_EXPECTED_ISSUE
    while cursor <= LAST_EXPECTED_ISSUE:
        months.append(cursor.isoformat())
        cursor = date.fromisoformat(CT.add_months(cursor.isoformat(), 1))
    return months


def main() -> None:
    config = CT.load_timing_config()
    before = {k: SM.sha256_of_file(p) for k, p in GUARDED.items() if p.is_file()}

    # --- 1. discovery from official seed pages -------------------------------
    pages = [
        config["discovery"]["landing_page"],
        config["discovery"]["report_archive_page"],
        *config["discovery"]["seed_pages"],
    ]
    discovered: dict[str, dict] = {}
    candidate_urls: dict[str, list[dict]] = {}
    page_status: dict[str, object] = {}
    for page in pages:
        try:
            html, status = fetch_text(page)
            page_status[page] = status
            for entry in V.discover_issue_urls(html, source_page=page):
                key = entry["issue_month"]
                # Merge CANDIDATES across pages rather than keeping one winner.
                # R1 kept only the first equal-ranked hit, so a filename-agnostic
                # /original/ link could shadow the correct /related/ one with no
                # way to recover.
                bucket = candidate_urls.setdefault(key, [])
                for candidate in entry["candidates"]:
                    if not any(c["url"] == candidate["url"] for c in bucket):
                        bucket.append(candidate)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            page_status[page] = f"unreachable: {type(exc).__name__}: {exc}"

    # Rank each issue month's candidates; best first.
    for key, bucket in candidate_urls.items():
        ranked = sorted(bucket, key=lambda c: V._METHOD_RANK[c["discovery_method"]])
        stamp = date.fromisoformat(key)
        discovered[key] = {
            "issue_name": f"CMO-Pink-Sheet-{stamp.strftime('%B')}-{stamp.year}",
            "issue_month": key,
            "url": ranked[0]["url"],
            "filename": ranked[0]["filename"],
            "discovery_method": ranked[0]["discovery_method"],
            "document_hash": ranked[0]["document_hash"],
            "source_page": ranked[0]["source_page"],
            "candidates": ranked,
        }

    expected = expected_issue_months()
    missing_after_seeds = [m for m in expected if m not in discovered]

    # --- 2. official Public Documents search for any remaining gap -----------
    search_attempts: list[dict] = []
    for month in missing_after_seeds:
        stamp = date.fromisoformat(month)
        name = f"CMO-Pink-Sheet-{stamp.strftime('%B')}-{stamp.year}"
        url = (
            "https://search.worldbank.org/api/v2/wds?format=json&rows=5"
            f"&qterm={urllib.parse.quote(name)}&fl=docdt,display_title,pdfurl"
        )
        attempt = {"issue_month": month, "document_name": name, "search_url": url}
        try:
            body, status = fetch_text(url)
            attempt["http_status"] = status
            payload = json.loads(body)
            attempt["total_hits"] = payload.get("total")
            hits = [
                v.get("pdfurl")
                for k, v in (payload.get("documents") or {}).items()
                if k != "facets" and isinstance(v, dict) and v.get("pdfurl")
            ]
            attempt["pdf_urls"] = hits
            if hits:
                discovered[month] = {
                    "issue_name": name,
                    "issue_month": month,
                    "url": hits[0],
                    "filename": hits[0].rsplit("/", 1)[-1],
                    "discovery_method": "official_public_documents_search",
                    "source_page": url,
                }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
        search_attempts.append(attempt)

    # --- 3. acquire, validate, and build the expected-issue inventory --------
    retrieved_at = SM.utc_now_iso()
    raw_dir = PROJECT_ROOT / "data" / "raw" / "WB_PINKSHEET_VINTAGES" / retrieved_at[:10]
    raw_dir.mkdir(parents=True, exist_ok=True)

    issues: list[V.PinkSheetIssue] = []
    inventory: list[dict] = []
    checksum_to_issue: dict[str, str] = {}
    for issue_month in expected:
        stamp = date.fromisoformat(issue_month)
        reference_month = CT.add_months(issue_month, -1)
        row = {
            "expected_issue_month": issue_month,
            "expected_issue_name": (
                f"CMO-Pink-Sheet-{stamp.strftime('%B')}-{stamp.year}"
            ),
            "reference_month_first_exposed": reference_month,
            "discovery_status": "not_found",
            "discovery_method": None,
            "detail_page_url": None,
            "pdf_url": None,
            "document_date": None,
            # The World Bank does not expose a web-publish date separately from
            # the document; recorded null rather than assumed equal to it.
            "web_publish_date": None,
            "internal_pdf_creation_date": None,
            "latest_displayed_reference_month": None,
            "sha256": None,
            "document_hash": None,
            "storage_identity": None,
            "file_size_bytes": None,
            "candidate_attempts": [],
            "validation_status": "no_issue_obtained",
        }
        meta = discovered.get(issue_month)
        if meta is None:
            inventory.append(row)
            continue

        # Try candidates in precedence order and ACCEPT ONLY a document whose own
        # contents identify it as this issue. R1 accepted whatever the first
        # matching href returned, which is how January's bytes were filed as
        # February.
        accepted = None
        attempts: list[dict] = []
        for candidate in meta["candidates"]:
            attempt = {
                "requested_url": candidate["url"],
                "discovery_method": candidate["discovery_method"],
                "document_hash": candidate["document_hash"],
                "source_page": candidate["source_page"],
            }
            identity = V.storage_identity(candidate["url"], candidate["filename"])
            destination = raw_dir / identity
            try:
                if not destination.is_file():
                    payload, http_meta = fetch_bytes(candidate["url"])
                    destination.write_bytes(payload)
                    attempt.update(
                        final_url=http_meta.get("final_url", candidate["url"]),
                        http_status=http_meta.get("http_status"),
                        content_length=http_meta.get("content_length"),
                    )
                else:
                    attempt["cached"] = True
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                attempt["error"] = f"{type(exc).__name__}: {exc}"
                attempts.append(attempt)
                continue

            checksum = SM.sha256_of_file(destination)
            attempt["sha256"] = checksum
            attempt["storage_identity"] = identity
            attempt["file_size_bytes"] = destination.stat().st_size
            try:
                issue = V.parse_issue_pdf(
                    destination, meta["issue_name"], issue_month, candidate["url"],
                    checksum, retrieved_at,
                )
            except (V.IssueParseError, FileNotFoundError) as exc:
                attempt["parse_error"] = f"{type(exc).__name__}: {exc}"
                attempts.append(attempt)
                continue

            ok, problems = V.validate_issue_identity(issue, issue_month)
            attempt["internal_pdf_creation_date"] = issue.issue_date
            attempt["latest_displayed_reference_month"] = issue.latest_reference_month
            attempt["identity_valid"] = ok
            attempt["identity_problems"] = problems
            attempts.append(attempt)
            if ok:
                accepted = (candidate, destination, checksum, issue)
                break

        row["candidate_attempts"] = attempts
        if accepted is None:
            row["validation_status"] = (
                "no_candidate_passed_identity_validation: "
                + "; ".join(
                    p for a in attempts for p in a.get("identity_problems", [])
                )[:300]
            )
            inventory.append(row)
            continue

        candidate, destination, checksum, issue = accepted

        # A checksum shared by two DIFFERENT expected issue months is a defect,
        # not a fact about the archive. Both cannot have passed identity
        # validation, so raise rather than quietly declaring one a duplicate —
        # R1's silent "duplicate_content" verdict is what turned a fetch bug
        # into a false claim that no February 2025 issue existed.
        if checksum in checksum_to_issue and checksum_to_issue[checksum] != issue_month:
            raise V.IssueIdentityError(
                f"SHA-256 {checksum[:16]} is shared by validated issues "
                f"{checksum_to_issue[checksum]} and {issue_month}. Both passed "
                "identity validation, which is impossible; investigate before "
                "recording either."
            )
        checksum_to_issue[checksum] = issue_month

        SM.append_manifest_entry(
            SM.ManifestEntry(
                source_id="WB_PINKSHEET_VINTAGES",
                file_path=str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                source_url=candidate["url"],
                retrieved_at=retrieved_at,
                sha256=checksum,
                content_length=destination.stat().st_size,
                original_filename=candidate["filename"],
                source_vintage=meta["issue_name"],
                url_discovery_method=candidate["discovery_method"],
                landing_page=candidate["source_page"],
                notes="Archived Pink Sheet issue; identity validated against its own PDF.",
            )
        )
        issues.append(issue)
        row.update(
            discovery_status="validated",
            discovery_method=candidate["discovery_method"],
            detail_page_url=candidate["source_page"],
            pdf_url=candidate["url"],
            document_hash=candidate["document_hash"],
            storage_identity=V.storage_identity(candidate["url"], candidate["filename"]),
            file_size_bytes=destination.stat().st_size,
            sha256=checksum,
            internal_pdf_creation_date=issue.issue_date,
            document_date=issue.issue_date,
            latest_displayed_reference_month=issue.latest_reference_month,
            validation_status="validated",
        )
        inventory.append(row)

    # --- 4. publication-timing table -----------------------------------------
    window = config["required_reference_window"]
    start, end = str(window["start"]), str(window["end"])
    required_months, cursor = [], start
    while cursor <= end:
        required_months.append(cursor)
        cursor = CT.add_months(cursor, 1)

    timing_rows = CT.build_publication_timing_table(required_months, issues)
    delay_stats = CT.publication_delay_stats(timing_rows)

    # --- 5. revision audit vs the C1 latest-vintage workbook -----------------
    latest_values: dict[str, dict[str, float]] = {}
    if C1_TABLE.is_file():
        table = pd.read_parquet(C1_TABLE)
        for series_id, sub in table.groupby("series_id", observed=True):
            latest_values[str(series_id)] = {
                str(m): float(v)
                for m, v in zip(sub["month"].astype(str), sub["value"], strict=True)
            }
    workbook_vintage_month = None
    c1_audit = PROJECT_ROOT / "docs" / "c1_commodity_source_audit.json"
    if c1_audit.is_file():
        vintage = json.loads(c1_audit.read_text(encoding="utf-8"))["provenance"].get(
            "source_vintage"
        )
        if vintage:
            try:
                name, year = vintage.split("-")
                workbook_vintage_month = date(
                    int(year), V.month_name_to_number(name), 1
                ).isoformat()
            except (ValueError, KeyError):
                workbook_vintage_month = None

    revisions = CT.revision_audit(
        issues, latest_values, workbook_vintage_month,
        required_window=(start, end),
    )
    # C1.5-R3: estimate status is now derived from the Description rule and is
    # tracked SEPARATELY from the numerical revision measurement.
    estimate_transitions = CT.estimate_transition_audit(
        issues, latest_values, required_window=(start, end)
    )

    # --- 6. timing decisions --------------------------------------------------
    b4_config_path = PROJECT_ROOT / "configs" / "evaluation_splits.yaml"
    development_origins: list[str] = []
    if b4_config_path.is_file():
        import yaml

        b4 = yaml.safe_load(b4_config_path.read_text(encoding="utf-8"))
        cursor = str(b4["development"]["first_origin"])
        last = str(b4["development"]["last_origin"])
        while cursor <= last:
            development_origins.append(cursor)
            cursor = CT.add_months(cursor, 1)

    decisions = CT.decide_timing_contract(
        timing_rows, development_origins, revisions["by_series"]
    )

    after = {k: SM.sha256_of_file(p) for k, p in GUARDED.items() if p.is_file()}
    obtained = [r for r in inventory if r["validation_status"] == "validated"]
    still_missing = [r for r in inventory if r["validation_status"] != "validated"]

    output = {
        "task": "C1.5-R2",
        "audit_version": config["audit_version"],
        "supersedes": (
            "the first C1.5 run's archive-coverage conclusion (superseded by R1) "
            "and R1's February 2025 duplicate-content finding (superseded by R2)"
        ),
        "discovery": {
            "pages_fetched": page_status,
            "method": config["discovery"]["method"],
            "construct_urls_from_guessed_hash": False,
            "expected_issue_range": {
                "first": FIRST_EXPECTED_ISSUE.isoformat(),
                "last": LAST_EXPECTED_ISSUE.isoformat(),
                "count": len(expected),
            },
            "issues_discovered": len(discovered),
            "by_method": {
                method: sum(
                    1 for m in expected
                    if discovered.get(m, {}).get("discovery_method") == method
                )
                for method in V.DISCOVERY_METHODS
            },
            "missing_after_seed_pages": missing_after_seeds,
            "public_documents_search_attempts": search_attempts,
        },
        "expected_issue_inventory": inventory,
        "coverage": {
            "expected": len(expected),
            "validated": len(obtained),
            "distinct_issues_obtained": len(issues),
            "duplicate_content_issues": [
                r["expected_issue_month"] for r in inventory
                if r["discovery_status"] == "duplicate_content"
            ],
            "missing_or_invalid": len(still_missing),
            "missing_issue_months": [r["expected_issue_month"] for r in still_missing],
        },
        "issues": [
            {
                **{k: v for k, v in asdict(i).items() if k != "observations"},
                "observations": {
                    series_id: [asdict(o) for o in rows]
                    for series_id, rows in i.observations.items()
                },
            }
            for i in issues
        ],
        "first_release_index": V.first_release_index(issues),
        "publication_timing": [asdict(r) for r in timing_rows],
        "publication_delay_stats": delay_stats,
        "required_window": {"start": start, "end": end, "months": len(required_months)},
        "months_with_evidence": [
            r.reference_month for r in timing_rows
            if r.availability_status == "verified_from_archived_issue"
        ],
        "months_upper_bound_only": [
            r.reference_month for r in timing_rows
            if r.availability_status == "upper_bound_only"
        ],
        "months_without_evidence_count": sum(
            1 for r in timing_rows if r.availability_status == "no_archived_issue"
        ),
        "b4_development_origins": {
            "count": len(development_origins),
            "first": development_origins[0] if development_origins else None,
            "last": development_origins[-1] if development_origins else None,
            "with_archived_evidence": sum(
                1 for r in timing_rows
                if r.reference_month in development_origins
                and r.availability_status == "verified_from_archived_issue"
            ),
        },
        "revision_audit": revisions,
        "estimate_transition_audit": estimate_transitions,
        "footnote_semantics": {
            "markers": V.FOOTNOTE_MEANINGS,
            "estimate_rule_version": V.ESTIMATE_RULE_VERSION,
            "estimate_statuses": list(V.ESTIMATE_STATUSES),
            "index_membership_implies_estimate": False,
            "correction": (
                "C1.5-R1/R2 read the table token 'a/' as an estimate marker. The "
                "Pink Sheet's own footnote block defines it as 'Included in the "
                "energy index'. Index membership never implies estimate status; "
                "estimate status comes from a separate Description statement."
            ),
        },
        "workbook_vintage_month": workbook_vintage_month,
        "timing_decisions": decisions,
        "features_created": False,
        "target_joined": False,
        "target_association_computed": False,
        "locked_test_accessed": False,
        "model_feature_approved_set": False,
        "upstream_artifacts_unmodified": before == after,
    }
    with AUDIT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(output, indent=2, ensure_ascii=False, default=str))

    print("=== C1.5-R2 - Pink Sheet issue identity & timing audit ===")
    print(f"expected issues   : {len(expected)} "
          f"({FIRST_EXPECTED_ISSUE} .. {LAST_EXPECTED_ISSUE})")
    active = {k: v for k, v in output["discovery"]["by_method"].items() if v}
    print(f"discovered        : {len(discovered)}  by method {active}")
    print(f"validated         : {len(obtained)} / {len(expected)}")
    if still_missing:
        print(f"MISSING/INVALID   : {[r['expected_issue_month'] for r in still_missing]}")
    print(f"\nreference months verified : {len(output['months_with_evidence'])} / "
          f"{len(required_months)}")
    print(f"upper-bound only          : {len(output['months_upper_bound_only'])}")
    print(f"no evidence               : {output['months_without_evidence_count']}")
    print(f"delay stats       : min={delay_stats.get('min_delay_days')} "
          f"median={delay_stats.get('median_delay_days')} "
          f"max={delay_stats.get('max_delay_days')} "
          f"in_t_plus_1={delay_stats.get('months_available_in_t_plus_1')}")
    print(f"B4 dev origins with evidence: "
          f"{output['b4_development_origins']['with_archived_evidence']} / "
          f"{len(development_origins)}")
    print("\nrevision audit (first release vs latest workbook):")
    for series_id, stats in revisions["by_series"].items():
        frequency = stats["revision_frequency"]
        print(f"  {series_id:24s} comparable={stats['comparable_observations']:3d} "
              f"revised={stats['revisions_beyond_rounding']:3d} "
              f"freq={frequency if frequency is None else round(frequency, 3)} "
              f"max_pct={stats['max_percentage_revision']}")
    print("\ntiming decisions:")
    for key, value in decisions.items():
        if isinstance(value, list):
            print(f"  {key}:")
            for item in value:
                print(f"    - {item}")
        else:
            print(f"  {key}: {value}")
    print(f"\nupstream artifacts unmodified: {output['upstream_artifacts_unmodified']}")
    print(f"audit written: {AUDIT_JSON.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
