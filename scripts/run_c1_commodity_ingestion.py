"""Run C1 ingestion: canonical commodity table + Brent cross-check.

Produces LEVELS ONLY. No MoM, YoY, lag, volatility, z-score or shock flag is
computed; no unit is converted; the forecast target is never loaded, so no
target association can be calculated even accidentally; and B4's locked test is
never touched.

Calls the package implementation — no parsing logic lives here.

Usage:
    python scripts/run_c1_commodity_ingestion.py
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from thai_supply_chain_ews.data import source_manifests as SM  # noqa: E402
from thai_supply_chain_ews.data import world_bank_commodities as WBC  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUT_DIR = PROJECT_ROOT / "data" / "interim"
AUDIT_JSON = PROJECT_ROOT / "docs" / "c1_commodity_source_audit.json"
METADATA_JSON = PROJECT_ROOT / "docs" / "c1_commodity_ingestion_metadata.json"
USER_AGENT = "Mozilla/5.0 (research; thai-supply-chain-ews)"

# Upstream artifacts that C1 must leave untouched.
GUARDED_ARTIFACTS = [
    PROJECT_ROOT / "data" / "processed" / "industry_month_panel.parquet",
    PROJECT_ROOT / "data" / "targets" / "production_stress_month.parquet",
    PROJECT_ROOT / "data" / "targets" / "forecast_target_raw.parquet",
    PROJECT_ROOT / "data" / "model_input" / "b4_walk_forward_predictions.parquet",
]


def try_fetch_fred(series_id: str, url: str) -> tuple[Path | None, dict]:
    """Attempt the FRED cross-check download. Never fabricates on failure."""
    dated_dir = RAW_DIR / "FRED_BRENT" / SM.utc_now_iso()[:10]
    destination = dated_dir / f"{series_id}.csv"
    if destination.is_file() and destination.stat().st_size > 0:
        return destination, {"already_present": True, "http_status": None}
    dated_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        context = ssl.create_default_context()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
        with opener.open(request, timeout=60) as response:
            payload = response.read()
            status = response.status
        destination.write_bytes(payload)
        return destination, {"already_present": False, "http_status": status}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {
            "error": f"{type(exc).__name__}: {exc}",
            "url": url,
            "note": (
                "FRED was unreachable from this environment. No cross-check numbers are "
                "reported — a blocked source is recorded as blocked, never estimated."
            ),
        }


def main() -> None:
    config = WBC.load_commodity_config()
    before = {p: SM.sha256_of_file(p) for p in GUARDED_ARTIFACTS if p.is_file()}

    if not AUDIT_JSON.is_file():
        raise SystemExit(
            "Run scripts/audit_world_bank_commodities.py first — ingestion consumes its audit."
        )
    audit_output = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    provenance = audit_output["provenance"]

    workbook_path = PROJECT_ROOT / audit_output["workbook"]["file"]
    SM.verify_file_checksum(workbook_path, provenance["sha256"])

    workbook = WBC.parse_workbook(workbook_path, config)
    audits = WBC.audit_candidates(workbook, config, provenance)
    table = WBC.build_canonical_table(workbook, audits, config, provenance)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table_path = OUT_DIR / "commodity_month.parquet"
    table.to_parquet(table_path, index=False, engine="pyarrow")

    # --- independent Brent cross-check --------------------------------------
    cross = config["cross_check_source"]
    window = config["cross_check_classification"]["overlap_window"]
    start, end = window["start"], window["end"]
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)

    fred_path, fred_meta = try_fetch_fred(cross["series"], cross["url"])
    if fred_path is None:
        cross_check = {
            "status": config["cross_check_classification"]["not_executed_state"],
            "reasons": [fred_meta["note"], fred_meta["error"]],
            "metrics": None,
            "fred_provenance": fred_meta,
            "world_bank_series_replaced": False,
        }
    else:
        fred_sha = SM.sha256_of_file(fred_path)
        SM.append_manifest_entry(
            SM.ManifestEntry(
                source_id="FRED_BRENT",
                file_path=str(fred_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                source_url=cross["url"],
                retrieved_at=SM.utc_now_iso(),
                sha256=fred_sha,
                http_status=fred_meta.get("http_status"),
                original_filename=fred_path.name,
                notes="Cross-check only; never a production feature.",
            )
        )
        fred_series = WBC.parse_fred_monthly_csv(fred_path, cross["series"])
        brent = table[table["series_id"] == "brent_crude_usd_bbl"]
        wb_series = dict(zip(brent["month"], brent["value"].astype(float), strict=True))
        metrics = WBC.compute_cross_check_metrics(wb_series, fred_series, start, end)
        status, reasons = WBC.classify_cross_check(metrics, config)
        cross_check = {
            "status": status,
            "reasons": reasons,
            "metrics": metrics,
            "fred_provenance": {
                "series": cross["series"], "url": cross["url"],
                "file": str(fred_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": fred_sha, **fred_meta,
            },
            "world_bank_series_replaced": False,
        }

    after = {p: SM.sha256_of_file(p) for p in GUARDED_ARTIFACTS if p.is_file()}
    metadata = {
        "task": "C1",
        "audit_version": config["audit_version"],
        "canonical_table": {
            "file": str(table_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "rows": int(len(table)),
            "series": sorted(table["series_id"].unique().tolist()),
            "series_count": int(table["series_id"].nunique()),
            "first_month": str(table["month"].min()),
            "last_month": str(table["month"].max()),
            "unique_series_month_keys": bool(
                not table.duplicated(subset=["series_id", "month"]).any()
            ),
            "rows_by_series": {
                str(k): int(v) for k, v in table["series_id"].value_counts().sort_index().items()
            },
        },
        "provenance": provenance,
        "status_counts": audit_output["status_counts"],
        "brent_cross_check": cross_check,
        "timing": config["timing"],
        "feature_transformations_created": False,
        "unit_conversions_applied": False,
        "target_joined": False,
        "target_association_computed": False,
        "locked_test_accessed": False,
        "model_feature_approved_any_candidate": any(
            a.model_feature_approved for a in audits
        ),
        "upstream_artifacts_unmodified": before == after,
    }
    with METADATA_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(metadata, indent=2, ensure_ascii=False, default=str))

    print("=== C1 — commodity ingestion ===")
    print(f"canonical table : {len(table)} rows, {table['series_id'].nunique()} series, "
          f"{table['month'].min()} .. {table['month'].max()}")
    for series_id, count in table["series_id"].value_counts().sort_index().items():
        audit = next(a for a in audits if a.candidate_id == series_id)
        print(f"  {series_id:<24} {count:>4} rows  {audit.unit:<8} {audit.status}")
    print(f"\nbrent cross-check: {cross_check['status']}")
    for reason in cross_check["reasons"]:
        print(f"  - {reason}")
    print(f"\nfeature transformations created : {metadata['feature_transformations_created']}")
    print(f"target joined / association      : {metadata['target_joined']} / "
          f"{metadata['target_association_computed']}")
    print(f"locked test accessed             : {metadata['locked_test_accessed']}")
    print(f"model_feature_approved (any)     : {metadata['model_feature_approved_any_candidate']}")
    print(f"upstream artifacts unmodified    : {metadata['upstream_artifacts_unmodified']}")
    print(f"\nwritten:\n  {table_path.relative_to(PROJECT_ROOT)}"
          f"\n  {METADATA_JSON.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
