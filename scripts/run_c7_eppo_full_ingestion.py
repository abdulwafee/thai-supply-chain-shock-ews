"""Task C7 — full EPPO daily archive ingestion and monthly source table.

Retrieves, validates and productionizes the complete discovered EPPO ex-refinery
archive for 2021-01-01 through 2026-05-31, then aggregates it to a monthly
source table under the C6.5 latest-vintage policy.

SOURCE INGESTION AND SOURCE-LEVEL AGGREGATION ONLY. A monthly mean of a
published price is an ingestion step, not a predictive feature. No
transformation, no exposure multiplication, no MPI join, no target association,
no model, no locked-test access.

    data/interim/c7_eppo_daily_prices.parquet      (git-ignored)
    data/interim/c7_eppo_monthly_source.parquet    (git-ignored)
    data/raw/EPPO_PRICE_STRUCTURE/**               (git-ignored)
    data/raw/_manifests/EPPO_PRICE_STRUCTURE_manifest.jsonl
    docs/c7_eppo_full_archive_audit.{md,json}
    docs/c7_eppo_monthly_source_decision.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.data import eppo_daily_prices as DP  # noqa: E402
from thai_supply_chain_ews.data import eppo_full_archive as FA  # noqa: E402
from thai_supply_chain_ews.data import eppo_monthly_prices as MP  # noqa: E402
from thai_supply_chain_ews.data import eppo_source_availability as AV  # noqa: E402
from thai_supply_chain_ews.data import eppo_source_lineage as LIN  # noqa: E402
from thai_supply_chain_ews.data.eppo_price_structure import (  # noqa: E402
    AUDITED_PRODUCTS,
    detect_magic,
    normalize_label,
)

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "eppo_monthly_source.yaml"
POLICY_PATH = ROOT / "configs" / "eppo_latest_vintage_policy.yaml"
C6_AUDIT = DOCS / "c6_eppo_archive_audit.json"
C6_5_DECISION = DOCS / "c6_5_eppo_latest_vintage_decision.json"
DISCOVERY_CACHE = ROOT / "data" / "interim" / "c6_eppo_cache" / "discovery.json"
DAILY_PARQUET = ROOT / "data" / "interim" / "c7_eppo_daily_prices.parquet"
MONTHLY_PARQUET = ROOT / "data" / "interim" / "c7_eppo_monthly_source.parquet"

#: Series C5/C6 selected. H-DIESEL is conditional because of the January 2024
#: semantic gap and never blocks the two fuel oils.
REQUIRED_SERIES = ("eppo_ex_refinery_fo600_2s", "eppo_ex_refinery_fo1500_2s")
CONDITIONAL_SERIES = ("eppo_ex_refinery_hsd",)


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 1. Upstream invariants. C7 may not proceed on an archive whose established
#    facts no longer hold, and may not silently repair an upstream artifact.
# ---------------------------------------------------------------------------
def reproduce_upstream_invariants(documents) -> dict:
    c6 = load_json(C6_AUDIT)
    c65 = load_json(C6_5_DECISION)
    policy = load_yaml(POLICY_PATH)

    dated = [d for d in documents if d.get("effective_date_filename")]
    effective_dates = sorted({d["effective_date_filename"] for d in dated})
    parity = [d for d in effective_dates if "2021-01-01" <= d <= "2026-05-31"]
    operational = [d for d in effective_dates if "2022-01-01" <= d <= "2026-05-31"]

    checks = {
        "discovered_media_documents": (len(documents), 5233),
        "distinct_effective_dates": (len(effective_dates), 4976),
        "parity_document_days": (len(parity), 1315),
        "operational_document_days": (len(operational), 1076),
        "parity_months": (len({d[:7] for d in parity}), 65),
        "operational_months": (len({d[:7] for d in operational}), 53),
        "c6_documents_retrieved": (
            c6["retrieval_and_validation"]["documents_retrieved"], 256,
        ),
        "c6_documents_validated": (c6["retrieval_and_validation"]["valid"], 254),
        "c6_partial_audit_rows": (c6["canonical_table"]["rows"], 722),
        "c6_table_is_partial_audit": (
            c6["canonical_table"]["is_partial_audit_table"], True,
        ),
        "c6_daily_ingestion_incomplete": (
            c65["ingestion_levels"]["complete_daily_documents_downloaded"], False,
        ),
        "c6_daily_validation_incomplete": (
            c65["ingestion_levels"]["complete_daily_documents_validated"], False,
        ),
        "monthly_aggregation_unapproved_upstream": (
            c65["ingestion_levels"]["monthly_aggregation_contract_approved"], False,
        ),
        "operational_policy_lag_months": (policy["policy"]["operational_policy_lag_months"], 2),
        "operational_lag_is_measured": (policy["policy"]["operational_lag_is_measured"], False),
        "minimum_verified_publication_lag_months": (
            policy["policy"]["minimum_verified_publication_lag_months"], None,
        ),
        "point_in_time_values_supported": (
            policy["policy"]["point_in_time_values_supported"], False,
        ),
        "hsd_missing_days_january_2024": (
            len(c65["c6_invariants"]["hsd_missing_days"]), 22,
        ),
        "hsd_gaps_all_in_january_2024": (
            all(d[:7] == "2024-01" for d in c65["c6_invariants"]["hsd_missing_days"]),
            True,
        ),
        "fo600_label_stable": (
            sorted({r["exact_label"] for r in c6["semantic_regimes"]
                    if r["series_id"] == "eppo_ex_refinery_fo600_2s"}),
            ["FO 600 (1) 2%S"],
        ),
        "fo1500_label_stable": (
            sorted({r["exact_label"] for r in c6["semantic_regimes"]
                    if r["series_id"] == "eppo_ex_refinery_fo1500_2s"}),
            ["FO 1500 (2) 2%S"],
        ),
    }
    result = {
        name: {"actual": actual, "expected": expected, "reproduced": actual == expected}
        for name, (actual, expected) in checks.items()
    }
    failed = sorted(n for n, c in result.items() if not c["reproduced"])
    return {
        "all_reproduced": not failed,
        "failed": failed,
        "checks": result,
        "c6_hsd_missing_days_january_2024": c65["c6_invariants"]["hsd_missing_days"],
    }


# ---------------------------------------------------------------------------
# 2. Parsing and day resolution.
# ---------------------------------------------------------------------------
_INTERNAL_DATE = re.compile(r"document says (\d{4}-\d{2}-\d{2})")


def _internal_date(item) -> str:
    found = _INTERNAL_DATE.search(str(item.get("rejection_reason", "")))
    return found.group(1) if found else None


def parse_records(records) -> dict:
    """Parse every successfully retrieved file and validate it against its listing."""
    parsed = {}
    for record in records:
        if not record.succeeded or not record.raw_relative_path:
            parsed[record.media_id] = (None, None)
            continue
        path = ROOT / record.raw_relative_path
        payload = path.read_bytes()
        discovery = DP.discover_layout(path, detect_magic(payload))
        validation = DP.validate_against_listing(
            payload, discovery, record.effective_date_filename
        )
        parsed[record.media_id] = (discovery, validation)
    return parsed


def resolve_days(days, records, parsed) -> dict:
    by_media = {record.media_id: record for record in records}
    resolutions = {}
    for date, candidates in days.items():
        triples = []
        for candidate in candidates:
            record = by_media.get(candidate.media_id)
            if record is None:
                continue
            discovery, validation = parsed.get(candidate.media_id, (None, None))
            if discovery is None:
                discovery = DP.LayoutDiscovery(magic=record.magic or "unknown")
                validation = {
                    "valid": False,
                    "rejection_reason": record.rejection_reason or record.retrieval_status,
                }
            triples.append((record, discovery, validation))
        resolutions[date] = DP.resolve_document_day(date, triples)
    return resolutions


def layout_regime_report(parsed, records) -> dict:
    """First and last effective date of every observed layout regime."""
    by_media = {r.media_id: r for r in records}
    spans = defaultdict(list)
    signatures, sheet_names = {}, defaultdict(set)
    for media_id, (discovery, validation) in parsed.items():
        if discovery is None or not (validation or {}).get("valid"):
            continue
        record = by_media[media_id]
        spans[discovery.layout_regime].append(record.effective_date_filename)
        signatures[discovery.layout_regime] = {
            "signature": discovery.signature,
            "regime_status": discovery.regime_status,
            "sheet_used": discovery.sheet_used,
            "tax_column_label": discovery.tax_column_label,
            "label_column_header": discovery.label_column_header,
            "unit_label": discovery.unit_label,
            "date_representation": discovery.date_representation,
            "header_labels": discovery.header_labels,
            "resolved_columns": discovery.resolved_columns,
        }
        for name in discovery.sheet_names:
            sheet_names[discovery.layout_regime].add(name)
    report = {}
    for regime, dates in sorted(spans.items()):
        dates = sorted(dates)
        report[regime] = {
            **signatures[regime],
            "documents": len(dates),
            "first_effective_date": dates[0],
            "last_effective_date": dates[-1],
            "sheet_names_observed": sorted(sheet_names[regime]),
        }
    return report


def transition_interval_report(parsed, records, start: str, end: str) -> dict:
    """What the previously unsampled February–June 2023 interval actually contains."""
    by_media = {r.media_id: r for r in records}
    rows = []
    for media_id, (discovery, validation) in parsed.items():
        record = by_media[media_id]
        date = record.effective_date_filename
        if not (start <= date <= end):
            continue
        rows.append({
            "effective_date": date,
            "layout_regime": discovery.layout_regime if discovery else None,
            "regime_status": discovery.regime_status if discovery else "unresolved",
            "sheet_used": discovery.sheet_used if discovery else None,
            "tax_column_label": discovery.tax_column_label if discovery else None,
            "valid": bool((validation or {}).get("valid")),
        })
    rows.sort(key=lambda r: r["effective_date"])
    by_regime = defaultdict(list)
    for row in rows:
        by_regime[row["layout_regime"]].append(row["effective_date"])
    return {
        "interval": {"start": start, "end": end},
        "prior_status": "unsampled_transition_interval",
        "documents_inspected": len(rows),
        "documents_valid": sum(1 for r in rows if r["valid"]),
        "regimes_observed": {
            regime: {
                "documents": len(dates),
                "first_effective_date": min(dates),
                "last_effective_date": max(dates),
            }
            for regime, dates in sorted(by_regime.items()) if regime
        },
        "additional_regime_discovered": sorted(
            {r["layout_regime"] for r in rows
             if r["regime_status"] == "newly_observed_regime"}
        ),
        "resolved_status": (
            "resolved_into_known_regimes"
            if not any(r["regime_status"] == "newly_observed_regime" for r in rows)
            else "additional_regime_registered"
        ),
    }


# ---------------------------------------------------------------------------
# 3. H-DIESEL January 2024, decided from the FULL month rather than a sample.
# ---------------------------------------------------------------------------
def product_label_history(parsed, records) -> dict:
    """Every exact product label the archive published, with its own span.

    Built from the full window rather than a sample, which is how the two label
    findings below became visible at all.
    """
    by_media = {r.media_id: r for r in records}
    spans = defaultdict(list)
    for media_id, (discovery, validation) in parsed.items():
        if discovery is None or not (validation or {}).get("valid"):
            continue
        date = by_media[media_id].effective_date_filename
        for label in discovery.all_product_labels:
            spans[label.strip()].append(date)
    return {
        label: {
            "document_days": len(set(dates)),
            "first_effective_date": min(dates),
            "last_effective_date": max(dates),
            "audited_series": AUDITED_PRODUCTS.get(normalize_label(label)),
            "unconfirmed_variant_of": DP.UNCONFIRMED_LABEL_VARIANTS.get(label.strip()),
            "is_blend_label": normalize_label(label) in {
                normalize_label(b) for b in DP.BLEND_LABELS
            },
        }
        for label, dates in sorted(spans.items())
    }


def _contiguous_spans(flagged_dates, all_dates) -> list:
    """Contiguous runs over DOCUMENT-DAYS, not calendar days.

    A run is bounded by the days the archive actually published, so a weekend
    inside a run never breaks it and never becomes a missing document either.
    """
    flagged, spans, current = set(flagged_dates), [], None
    for date in sorted(all_dates):
        if date in flagged:
            current = [date, date] if current is None else [current[0], date]
        elif current:
            spans.append({"start": current[0], "end": current[1]})
            current = None
    if current:
        spans.append({"start": current[0], "end": current[1]})
    for span in spans:
        span["document_days"] = sum(
            1 for d in flagged if span["start"] <= d <= span["end"]
        )
    return spans


def ordinary_h_diesel_availability(parsed, records) -> dict:
    """Where ordinary H-DIESEL is published, and where only blends are.

    C6 reported the product absent for 22 audited document-days in January 2024.
    That was true of everything C6 sampled; the full archive shows how far the
    absence actually runs.
    """
    by_media = {r.media_id: r for r in records}
    normalized = normalize_label("H-DIESEL")
    present, blend_only, valid_days = set(), set(), set()
    blend_label_days = defaultdict(set)
    for media_id, (discovery, validation) in parsed.items():
        if discovery is None or not (validation or {}).get("valid"):
            continue
        date = by_media[media_id].effective_date_filename
        valid_days.add(date)
        if any(normalize_label(x) == normalized for x in discovery.all_product_labels):
            present.add(date)
        elif discovery.blend_labels_present:
            blend_only.add(date)
            for label in discovery.blend_labels_present:
                blend_label_days[label.strip()].add(date)
    return {
        "valid_document_days": len(valid_days),
        "days_with_ordinary_h_diesel": len(present),
        "days_with_blend_only": len(blend_only),
        "absence_spans": _contiguous_spans(blend_only, valid_days),
        "blend_labels_published_during_absence": {
            label: len(dates) for label, dates in sorted(blend_label_days.items())
        },
        "c6_reported_absent_days": 22,
        "c6_reported_month": "2024-01",
        "c6_finding_contradicted": False,
        "c6_finding_extended_by_full_archive": True,
        "note": (
            "C6 sampled 254 of 1,315 document-days. The only sampled days that "
            "fell inside the absence were the 22 in January 2024, so C6's "
            "finding was correct for what it observed and understated the "
            "extent. No blend price is substituted for any of these days."
        ),
    }


def h_diesel_january_2024(parsed, records, resolutions) -> dict:
    by_media = {r.media_id: r for r in records}
    normalized_hsd = normalize_label("H-DIESEL")
    present, blend_only, labels = [], [], Counter()
    for media_id, (discovery, validation) in parsed.items():
        record = by_media[media_id]
        if not record.effective_date_filename.startswith("2024-01"):
            continue
        if discovery is None or not (validation or {}).get("valid"):
            continue
        labels.update(discovery.all_product_labels)
        has_plain = any(
            normalize_label(label) == normalized_hsd
            for label in discovery.all_product_labels
        )
        if has_plain:
            present.append(record.effective_date_filename)
        elif discovery.blend_labels_present:
            blend_only.append(record.effective_date_filename)
    valid_days = sorted({
        date for date, resolution in resolutions.items()
        if date.startswith("2024-01") and resolution.status in (
            "resolved", "same_date_conflicting_value"
        )
    })
    return {
        "month": "2024-01",
        "valid_document_days_in_month": len(valid_days),
        "days_with_ordinary_h_diesel": sorted(set(present)),
        "days_with_blend_only": sorted(set(blend_only)),
        "absent_for_entire_month": not present and bool(blend_only),
        "c6_audited_absent_days": 22,
        "full_month_absent_days": len(set(blend_only)),
        "blend_labels_observed": sorted(
            label for label in labels
            if normalize_label(label) in {normalize_label(b) for b in DP.BLEND_LABELS}
        ),
        "monthly_value": None,
        "aggregation_status": "semantic_definition_gap",
        "quality_flag": MP.H_DIESEL_GAP_FLAG,
        "blend_substitution_permitted": False,
        "interpolation_permitted": False,
        "month_removed_silently": False,
        "zero_stored": False,
    }


def blend_only_day_counts(parsed, records) -> dict:
    """How many valid days in each (series, month) published blends but no plain product."""
    by_media = {r.media_id: r for r in records}
    counts = Counter()
    normalized_hsd = normalize_label("H-DIESEL")
    for media_id, (discovery, validation) in parsed.items():
        if discovery is None or not (validation or {}).get("valid"):
            continue
        record = by_media[media_id]
        month = record.effective_date_filename[:7]
        has_plain = any(
            normalize_label(label) == normalized_hsd
            for label in discovery.all_product_labels
        )
        if not has_plain and discovery.blend_labels_present:
            counts[("eppo_ex_refinery_hsd", month)] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# 4. Completeness, reported against the DISCOVERED inventory.
# ---------------------------------------------------------------------------
def completeness_report(inventories, daily_rows, series_ids) -> list:
    by_series_month = defaultdict(list)
    for row in daily_rows:
        by_series_month[(row["series_id"], row["effective_date"][:7])].append(row)
    report = []
    for month in sorted(inventories):
        inventory = inventories[month]
        for series_id in sorted(series_ids):
            rows = by_series_month.get((series_id, month), [])
            valued = [r for r in rows if r.get("value") is not None]
            report.append({
                "month": month,
                "series_id": series_id,
                "expected_issue_count": None,
                "expected_schedule_status": "unresolved",
                "discovered_document_days": inventory.discovered_document_days,
                "retrieval_attempted_days": inventory.retrieval_attempted_days,
                "successfully_retrieved_days": inventory.successfully_retrieved_days,
                "content_valid_document_days": inventory.content_valid_document_days,
                "valid_product_observations": len(valued),
                "duplicate_days": inventory.duplicate_days,
                "rejected_days": inventory.rejected_days,
                "unresolved_days": inventory.unresolved_days,
                "observed_weekdays": inventory.observed_weekdays,
                "first_effective_date": (
                    valued[0]["effective_date"] if valued else None
                ),
                "last_effective_date": (
                    valued[-1]["effective_date"] if valued else None
                ),
                "inventory_retrieval_fraction": inventory.inventory_retrieval_fraction,
                "product_observation_fraction": (
                    len(valued) / inventory.content_valid_document_days
                    if inventory.content_valid_document_days else None
                ),
            })
    return report


# ---------------------------------------------------------------------------
# 5. Output.
# ---------------------------------------------------------------------------
def write_parquet(rows, path, list_columns=()):
    frame = pd.DataFrame(rows)
    for column in list_columns:
        if column in frame.columns:
            frame[column] = frame[column].apply(lambda v: list(v or []))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame



# ---------------------------------------------------------------------------
# 6. Markdown. Generated from the same payload the JSON is written from, so a
#    number can never drift between the two documents.
# ---------------------------------------------------------------------------
def _bool(value) -> str:
    return f"`{value}`"


def write_audit_markdown(payload: dict) -> None:
    denominator = payload["denominator"]
    lines = [
        "# Task C7 - Full EPPO Daily Archive Ingestion",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        "Source ingestion and source-level aggregation only. A monthly mean of a",
        "published price is not a predictive feature, and none was created.",
        "",
        "## Upstream invariants",
        "",
        f"All C6/C6.5 invariants reproduced: "
        f"**{payload['upstream_invariants']['all_reproduced']}** "
        f"({len(payload['upstream_invariants']['checks'])} checks).",
        "",
        "| check | expected | actual |",
        "| --- | --- | --- |",
    ]
    for name, check in payload["upstream_invariants"]["checks"].items():
        lines.append(
            f"| `{name}` | `{check['expected']}` | `{check['actual']}` |"
        )

    lines += [
        "",
        "## Ingestion denominator",
        "",
        "The denominator is the officially discovered inventory, and each stage",
        "can only shrink. A discovered day is **not** a validated day.",
        "",
        "| state | count |",
        "| --- | --- |",
    ]
    for key in (
        "discovered_media_records", "distinct_document_days",
        "document_days_with_one_attachment",
        "document_days_with_multiple_attachment_candidates",
        "retrieval_attempts", "http_successes", "format_valid_files",
        "content_valid_files", "rejected_attachments", "duplicate_files",
        "content_equivalent_duplicate_files", "conflicting_same_date_files",
        "valid_canonical_document_days", "unresolved_document_days",
    ):
        lines.append(f"| `{key}` | {denominator[key]} |")
    lines += [
        "",
        f"`discovered_days_reported_as_validated`: "
        f"{_bool(denominator['discovered_days_reported_as_validated'])}",
        "",
        "Retrieval status counts: "
        + ", ".join(f"`{k}` {v}" for k, v in denominator["retrieval_status_counts"].items()),
        "",
        "## Workbook layout regimes",
        "",
        "Every sheet of every document was inspected and every column resolved by",
        "label. No positional fallback exists, so an unrecognised layout is",
        "rejected rather than guessed.",
        "",
        "| regime | status | sheet | tax column | first | last | documents |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for regime, entry in payload["layout_regimes"].items():
        lines.append(
            f"| `{regime}` | `{entry['regime_status']}` | `{entry['sheet_used']}` | "
            f"`{entry['tax_column_label']}` | {entry['first_effective_date']} | "
            f"{entry['last_effective_date']} | {entry['documents']} |"
        )

    transition = payload["transition_interval"]
    lines += [
        "",
        "### February-June 2023, previously unsampled",
        "",
        f"Prior status `{transition['prior_status']}`. "
        f"{transition['documents_inspected']} documents inspected, "
        f"{transition['documents_valid']} valid. "
        f"Resolution: `{transition['resolved_status']}`.",
        "",
        "| regime | documents | first | last |",
        "| --- | --- | --- | --- |",
    ]
    for regime, entry in transition["regimes_observed"].items():
        lines.append(
            f"| `{regime}` | {entry['documents']} | {entry['first_effective_date']} "
            f"| {entry['last_effective_date']} |"
        )
    lines += [
        "",
        f"Additional regime discovered inside the interval: "
        f"`{transition['additional_regime_discovered'] or 'none'}`.",
        "",
        "## Product identity",
        "",
        f"Price stage `{payload['product_identity']['price_stage']}`, unit "
        f"`{payload['product_identity']['unit']}`. Units observed: "
        + ", ".join(f"`{u}`" for u in payload["product_identity"]["units_observed"])
        + ".",
        "",
        "| series | exact labels in the daily table |",
        "| --- | --- |",
    ]
    for series_id, labels in payload["product_identity"]["series"].items():
        lines.append(f"| `{series_id}` | " + ", ".join(f"`{x}`" for x in labels) + " |")

    lines += [
        "",
        "### Every label the archive published",
        "",
        "| exact label | days | first | last | audited series | blend |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for label, entry in payload["product_label_history"].items():
        if not (entry["audited_series"] or entry["unconfirmed_variant_of"]
                or entry["is_blend_label"]):
            continue
        lines.append(
            f"| `{label}` | {entry['document_days']} | {entry['first_effective_date']} "
            f"| {entry['last_effective_date']} | "
            f"`{entry['audited_series'] or entry['unconfirmed_variant_of'] or '-'}`"
            f"{' (variant)' if entry['unconfirmed_variant_of'] else ''} | "
            f"{_bool(entry['is_blend_label'])} |"
        )

    variants = payload["unconfirmed_label_variants"]
    lines += [
        "",
        "### Unconfirmed fuel-oil label variant",
        "",
        f"{variants['daily_rows_flagged']} daily rows carry a label that drops the",
        "table's ordinal index. The documents are kept; the equivalence is not",
        f"asserted (`equivalence_established`: {_bool(variants['equivalence_established'])}),",
        "and every month that touches one is blocked from approval.",
        "",
        "> " + variants["note"],
        "",
        "## Ordinary H-DIESEL availability",
        "",
    ]
    hsd = payload["ordinary_h_diesel_availability"]
    lines += [
        f"Ordinary `H-DIESEL` is published on {hsd['days_with_ordinary_h_diesel']} of",
        f"{hsd['valid_document_days']} validated document-days. On",
        f"{hsd['days_with_blend_only']} days only blend-specific products appear.",
        "",
        "| absence span | document-days |",
        "| --- | --- |",
    ]
    for span in hsd["absence_spans"]:
        lines.append(f"| {span['start']} .. {span['end']} | {span['document_days']} |")
    lines += [
        "",
        "Blend labels published during the absence: "
        + ", ".join(
            f"`{k}` ({v} days)"
            for k, v in hsd["blend_labels_published_during_absence"].items()
        )
        + ".",
        "",
        "> " + hsd["note"],
        "",
        "### January 2024, the month C6 reported",
        "",
    ]
    jan = payload["h_diesel_january_2024"]
    lines += [
        "| field | value |",
        "| --- | --- |",
        f"| valid document-days in month | {jan['valid_document_days_in_month']} |",
        f"| days with ordinary H-DIESEL | {len(jan['days_with_ordinary_h_diesel'])} |",
        f"| days with blend only | {len(jan['days_with_blend_only'])} |",
        f"| absent for the entire month | {_bool(jan['absent_for_entire_month'])} |",
        f"| monthly value | `{jan['monthly_value']}` |",
        f"| aggregation status | `{jan['aggregation_status']}` |",
        f"| quality flag | `{jan['quality_flag']}` |",
        f"| blend substitution permitted | {_bool(jan['blend_substitution_permitted'])} |",
        f"| interpolation permitted | {_bool(jan['interpolation_permitted'])} |",
        f"| month removed silently | {_bool(jan['month_removed_silently'])} |",
        f"| zero stored | {_bool(jan['zero_stored'])} |",
        "",
        "## Duplicates, conflicts and wrong-date attachments",
        "",
        "| finding | count |",
        "| --- | --- |",
        f"| byte-identical duplicate documents | "
        f"{payload['document_identity']['duplicate_documents']} |",
        f"| content-equivalent duplicates | "
        f"{payload['document_identity']['content_equivalent_duplicates']} |",
        f"| same-date conflicting values | "
        f"{len(payload['document_identity']['same_date_conflicting_values'])} |",
        f"| wrong-date attachments | "
        f"{len(payload['document_identity']['wrong_date_attachments'])} |",
        f"| unresolved document-days | "
        f"{len(payload['document_identity']['unresolved_document_days'])} |",
        "",
    ]
    for item in payload["document_identity"]["wrong_date_attachments"]:
        lines += [
            f"* `{item['filename']}` is listed under {item['listing_date']} but its",
            f"  content is dated {item['internal_date']}. It is not reassigned and not",
            "  counted for the listing date. A separately valid official document",
            f"  covers the listing date: {_bool(item['listing_date_separately_covered'])}; "
            f"the internal date: {_bool(item['internal_date_separately_covered'])}.",
        ]
    if payload["document_identity"]["unresolved_document_days"]:
        lines += [
            "",
            "Unresolved document-days (discovered officially, attachment not usable): "
            + ", ".join(payload["document_identity"]["unresolved_document_days"])
            + ".",
        ]

    lines += [
        "",
        "## Canonical daily table",
        "",
        f"`{payload['daily_table']['output']}` - "
        f"{payload['daily_table']['rows']} rows, key "
        f"`{' + '.join(payload['daily_table']['unique_key'])}`, "
        f"{payload['daily_table']['first_effective_date']} to "
        f"{payload['daily_table']['last_effective_date']}.",
        "",
        "| series | rows |",
        "| --- | --- |",
    ]
    for series_id, count in sorted(payload["daily_table"]["series_counts"].items()):
        lines.append(f"| `{series_id}` | {count} |")

    lines += [
        "",
        "## Monthly aggregation",
        "",
        f"Rule `{payload['monthly_aggregation']['aggregation_rule']}` "
        f"(version `{payload['monthly_aggregation']['aggregation_rule_version']}`), "
        f"unit `{payload['monthly_aggregation']['unit']}`.",
        "",
        "> " + payload["monthly_aggregation"]["statistic_description"].strip(),
        "",
        "It is not a calendar-day mean, not a trading-day mean, not a transaction",
        "price, and not a point-in-time value.",
        "",
        f"{payload['monthly_aggregation']['rows']} rows covering "
        f"{payload['monthly_aggregation']['reference_month_range'][0]} to "
        f"{payload['monthly_aggregation']['reference_month_range'][1]}.",
        "",
        "| status | product-months |",
        "| --- | --- |",
    ]
    for status, count in sorted(payload["monthly_aggregation"]["status_counts"].items()):
        lines.append(f"| `{status}` | {count} |")

    lines += [
        "",
        "### Approval",
        "",
        f"`monthly_aggregation_contract_approved`: "
        f"**{payload['approval']['monthly_aggregation_contract_approved']}**"
        + (
            ". Blocking series: "
            + ", ".join(f"`{s}`" for s in payload["approval"]["blocking_series"])
            if payload["approval"]["blocking_series"] else "."
        ),
        "",
        "| series | approved months | not approved | series approved |",
        "| --- | --- | --- | --- |",
    ]
    for series_id, entry in payload["approval"]["per_series"].items():
        approved = entry["status_counts"].get("approved", 0)
        lines.append(
            f"| `{series_id}` | {approved}/{entry['months_required']} | "
            + ", ".join(
                f"{month} `{status}`" for month, status in entry["months_not_approved"]
            )
            + f" | {_bool(entry['series_approved'])} |"
        )

    lines += [
        "",
        "## Availability",
        "",
        f"`source_available_as_of` is null in "
        f"{payload['availability']['source_available_as_of_null_rows']} of "
        f"{payload['availability']['monthly_rows']} monthly rows.",
        "",
        "| issue month | latest permitted reference month |",
        "| --- | --- |",
    ]
    for example in payload["availability"]["policy_available_month_examples"]:
        lines.append(
            f"| {example['issue_month']} | **{example['latest_permitted_reference_month']}** |"
        )
    lines += [
        "",
        f"`policy_available_month` = reference month + "
        f"{payload['inherited_policy']['operational_policy_lag_months']} months, "
        f"basis `{payload['inherited_policy']['availability_basis']}`, "
        f"`operational_lag_is_measured` "
        f"{_bool(payload['inherited_policy']['operational_lag_is_measured'])}, "
        f"`minimum_verified_publication_lag_months` "
        f"`{payload['inherited_policy']['minimum_verified_publication_lag_months']}`.",
        "",
        "## Transformation status",
        "",
        "| series | source ready for transformation | feature created |",
        "| --- | --- | --- |",
    ]
    for series_id, entry in payload["series_readiness"].items():
        lines.append(
            f"| `{series_id}` | {_bool(entry['source_ready_for_transformation'])} | "
            f"{_bool(entry['feature_transformations_created'])} |"
        )
    lines += [
        "",
        "No log change, percentage change, lagged price, realized volatility,",
        "z-score, shock flag, exposure interaction, correlation, mutual",
        "information, Granger test, feature importance or predictive metric was",
        "calculated. No MPI target was joined and no model was trained.",
        "",
        f"Content checksum `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c7_eppo_full_archive_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_decision_markdown(payload: dict) -> None:
    approval = payload["approval"]
    lines = [
        "# Task C7 - Monthly EPPO Source Aggregation Decision",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        "## The rule",
        "",
        f"`{payload['monthly_aggregation']['aggregation_rule']}`, version "
        f"`{payload['monthly_aggregation']['aggregation_rule_version']}`.",
        "",
        "Preregistered before the archive was retrieved, and selected from source",
        "publication semantics, archive completeness and deterministic",
        "reproducibility. It was **not** selected from predictive performance;",
        "no predictive quantity exists in this task.",
        "",
        "> " + payload["monthly_aggregation"]["statistic_description"].strip(),
        "",
        "### What the rule refuses",
        "",
        "| refusal | reason |",
        "| --- | --- |",
        "| no weekend or holiday observation is synthesised | the archive publishes "
        "on working days; a synthetic day would be our number, not EPPO's |",
        "| no forward fill of an unchanged price | that would silently convert the "
        "statistic into a calendar-day mean |",
        "| no duration weighting | it would require proof that a published price "
        "stays in force until superseded, which this project does not have |",
        "| no partial issue-month observation | the same reference month would "
        "otherwise take different values depending on when it was computed |",
        "| each document-day counted once | byte-identical or content-equivalent "
        "republications are one observation, not two |",
        "",
        "## Approval gate",
        "",
        f"`monthly_aggregation_contract_approved`: "
        f"**{approval['monthly_aggregation_contract_approved']}**",
        "",
    ]
    if approval["blocking_series"]:
        lines += [
            "The gate **fails**. It is reported as a failure rather than forced:",
            "",
        ]
        for series_id in approval["blocking_series"]:
            entry = approval["per_series"][series_id]
            lines.append(f"* `{series_id}`:")
            for month, status in entry["months_not_approved"]:
                lines.append(f"  * {month} - `{status}`")
        lines.append("")
    lines += [
        "## Why each month failed",
        "",
        "| cause | months | what it means |",
        "| --- | --- | --- |",
        "| `unresolved_document_retrieval` | every discovered attachment for the "
        "day returned an error | the official media record exists but its file "
        "does not; an actual unresolved inventory item, not a schedule gap |",
        "| `unresolved_document_identity` | the attachment's internal date belongs "
        "to another day | not reassigned, not counted for the listing date |",
        "| `unit_or_definition_break` | the month rests on a label variant whose "
        "equivalence with the audited label is not established | averaging it "
        "would assert an equivalence nobody made |",
        "| `semantic_definition_gap` | the product was not published on some or all "
        "validated document-days | a blend price is never substituted |",
        "",
        "## H-DIESEL",
        "",
        "H-DIESEL is a conditional series. It never blocks the fuel oils, and no",
        "value is fabricated to make one of its months pass.",
        "",
    ]
    hsd = payload["ordinary_h_diesel_availability"]
    for span in hsd["absence_spans"]:
        lines.append(
            f"* Ordinary `H-DIESEL` is absent from {span['start']} to "
            f"{span['end']} ({span['document_days']} document-days)."
        )
    lines += [
        "",
        "C6 reported the product absent for 22 audited document-days in January",
        "2024. That was true of every day C6 sampled. The full archive shows the",
        "absence is longer; C6 is extended, not contradicted.",
        "",
        "## Availability",
        "",
        "| field | value |",
        "| --- | --- |",
        "| `source_available_as_of` | `None` in every row |",
        f"| `policy_available_month` | reference month + "
        f"{payload['inherited_policy']['operational_policy_lag_months']} months |",
        f"| `availability_basis` | "
        f"`{payload['inherited_policy']['availability_basis']}` |",
        f"| `operational_lag_is_measured` | "
        f"{_bool(payload['inherited_policy']['operational_lag_is_measured'])} |",
        f"| `minimum_verified_publication_lag_months` | "
        f"`{payload['inherited_policy']['minimum_verified_publication_lag_months']}` |",
        "| `latest_vintage_used` | `True` |",
        "| `point_in_time_supported` | `False` |",
        "",
        "## What C7 did not do",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in sorted(payload["transformations"].items()):
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {_bool(value)} |")
    for key, value in sorted(payload["provenance"].items()):
        lines.append(f"| `{key}` | {_bool(value)} |")
    lines += [
        "",
        "A monthly source-level mean is an ingestion aggregation. It is not",
        "authorization for predictive feature engineering, and the next task must",
        "take that decision explicitly.",
        "",
    ]
    (DOCS / "c7_eppo_monthly_source_decision.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="use only files already on disk; make no requests")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()
    window = config["required_window"]

    # Guards that must hold before anything is computed, not after.
    AV.assert_measured_lag_not_claimed(config["inherited_policy"])
    MP.assert_statistic_description(
        config["monthly_aggregation"]["statistic_description"]
    )

    documents = load_json(DISCOVERY_CACHE)["documents"]
    invariants = reproduce_upstream_invariants(documents)
    if not invariants["all_reproduced"]:
        raise SystemExit(
            "C7 stops: upstream C6/C6.5 invariants did not reproduce: "
            f"{invariants['failed']}. Upstream artifacts are not repaired here."
        )

    days = FA.document_days(documents, window["start"], window["end"])
    if args.offline:
        records = FA.records_from_checkpoint(days, ROOT)
        acquisition = FA.summarize(records, days)
    else:
        records, acquisition, days = FA.acquire_window(
            documents, window["start"], window["end"], ROOT, limit=args.limit,
        )

    parsed = parse_records(records)
    resolutions = resolve_days(days, records, parsed)

    format_valid = sum(
        1 for r in records if r.succeeded and r.magic in ("xls_ole2", "xlsx_zip")
    )
    content_valid = sum(
        1 for _, (d, v) in parsed.items() if d is not None and (v or {}).get("valid")
    )
    rejected = [
        {
            "media_id": media_id,
            "effective_date": next(
                r.effective_date_filename for r in records if r.media_id == media_id
            ),
            "reason": (v or {}).get("rejection_reason"),
        }
        for media_id, (d, v) in sorted(parsed.items())
        if d is not None and not (v or {}).get("valid")
    ]

    # ---- daily table -----------------------------------------------------
    daily_rows = DP.build_daily_rows(
        [resolutions[date] for date in sorted(resolutions)],
        price_stage=config["price_stage_id"],
    )
    for row in daily_rows:
        availability = AV.monthly_availability_fields(row["effective_date"][:7])
        row["source_available_as_of"] = availability.source_available_as_of
        row["candidate_monthly_policy_available_month"] = (
            availability.policy_available_month
        )
        row["availability_basis"] = availability.availability_basis
        row["latest_vintage_used"] = availability.latest_vintage_used
        row["point_in_time_supported"] = availability.point_in_time_supported
    MP.attach_daily_lineage(daily_rows)

    # ---- monthly table ---------------------------------------------------
    inventories = MP.monthly_inventory(
        days, resolutions, window["start"][:7], window["end"][:7]
    )
    monthly_table = MP.build_monthly_table(
        daily_rows, inventories, sorted(AUDITED_PRODUCTS.values()),
        window["start"][:7], window["end"][:7],
        blend_only_days=blend_only_day_counts(parsed, records),
    )
    approval = MP.dataset_approval(
        monthly_table, REQUIRED_SERIES, window["start"][:7], window["end"][:7],
        conditional_series=CONDITIONAL_SERIES,
    )

    FA.assert_denominator_consistent(
        acquisition.distinct_document_days, acquisition.retrieval_attempts,
        acquisition.http_successes, content_valid,
    )
    for row in monthly_table:
        MP.assert_monthly_row_defensible(row, inventories[row["reference_month"]])
    MP.assert_no_transformation_columns(daily_rows[0].keys())
    MP.assert_no_transformation_columns(monthly_table[0].keys())

    daily_frame = write_parquet(daily_rows, DAILY_PARQUET)
    monthly_frame = write_parquet(
        monthly_table, MONTHLY_PARQUET, list_columns=("semantic_regime_ids",)
    )

    # ---- audit payload ---------------------------------------------------
    conflicts = [c for r in resolutions.values() for c in r.conflicts]
    wrong_date = [
        dict(item, listing_date=date, internal_date=_internal_date(item))
        for date, r in sorted(resolutions.items()) for item in r.rejected_candidates
        if str(item.get("rejection_reason", "")).startswith("wrong_date_attachment")
    ]
    unresolved_days = sorted(
        date for date, r in resolutions.items()
        if r.status not in ("resolved", "same_date_conflicting_value")
    )
    series_readiness = {}
    for series_id in sorted(AUDITED_PRODUCTS.values()):
        entry = approval["per_series"].get(series_id, {})
        series_readiness[series_id] = {
            "monthly_rows": sum(1 for r in monthly_table if r["series_id"] == series_id),
            "approved_months": sum(
                1 for r in monthly_table
                if r["series_id"] == series_id and r["aggregation_status"] == "approved"
            ),
            "series_approved": entry.get("series_approved", False),
            "series_conditionally_approved": entry.get(
                "series_conditionally_approved", False
            ),
            "source_ready_for_transformation": bool(
                entry.get("series_approved") or entry.get("series_conditionally_approved")
            ),
            "feature_transformations_created": False,
            "industry_conditioned_matrix_created": False,
            "model_feature_approved": False,
        }

    covered_days = {
        row["effective_date"] for row in daily_rows if row.get("value") is not None
    }

    payload = {
        "task": "C7",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "inherited_policy": config["inherited_policy"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "upstream_invariants": invariants,
        "required_window": window,
        "denominator": {
            "primary": config["denominator"]["primary"],
            "discovered_media_records": acquisition.discovered_media_records,
            "distinct_document_days": acquisition.distinct_document_days,
            "document_days_with_one_attachment": acquisition.document_days_single_candidate,
            "document_days_with_multiple_attachment_candidates": (
                acquisition.document_days_multiple_candidates
            ),
            "retrieval_attempts": acquisition.retrieval_attempts,
            "http_successes": acquisition.http_successes,
            "format_valid_files": format_valid,
            "content_valid_files": content_valid,
            "rejected_attachments": len(rejected),
            "duplicate_files": sum(r.duplicate_documents for r in resolutions.values()),
            "content_equivalent_duplicate_files": sum(
                r.content_equivalent_duplicates for r in resolutions.values()
            ),
            "conflicting_same_date_files": len(conflicts),
            "valid_canonical_document_days": sum(
                1 for r in resolutions.values()
                if r.status in ("resolved", "same_date_conflicting_value")
            ),
            "unresolved_document_days": len(unresolved_days),
            "discovered_days_reported_as_validated": False,
            "retrieval_status_counts": acquisition.status_counts,
        },
        "acquisition": {
            **{k: v for k, v in config["acquisition"].items()},
            "records_written_to_manifest": len(records),
            "downloaded_this_run": acquisition.downloaded,
            "cached_checksum_verified_this_run": acquisition.cached_checksum_verified,
        },
        "layout_regimes": layout_regime_report(parsed, records),
        "transition_interval": transition_interval_report(
            parsed, records, *DP.TRANSITION_INTERVAL
        ),
        "unknown_layout_documents": [
            r for r in rejected if str(r["reason"]).startswith("unknown_layout")
        ],
        "product_identity": {
            "price_stage": config["price_stage"],
            "unit": config["unit"],
            "series": {
                series_id: sorted({
                    row["source_product_label"] for row in daily_rows
                    if row["series_id"] == series_id and row["source_product_label"]
                })
                for series_id in sorted(AUDITED_PRODUCTS.values())
            },
            "units_observed": sorted({row["unit"] for row in daily_rows}),
            "stage_columns_kept_distinct": config["stage_columns_kept_distinct"],
            "forbidden_substitutions": config["forbidden_substitutions"],
        },
        "document_identity": {
            "duplicate_documents": sum(r.duplicate_documents for r in resolutions.values()),
            "content_equivalent_duplicates": sum(
                r.content_equivalent_duplicates for r in resolutions.values()
            ),
            "same_date_conflicting_values": conflicts,
            "wrong_date_attachments": [
                {
                    **item,
                    "reassigned_to_internal_date": False,
                    "counted_as_valid_for_listing_date": False,
                    "listing_date_separately_covered": item["listing_date"] in covered_days,
                    "internal_date_separately_covered": (
                        item["internal_date"] in covered_days
                    ),
                    "internal_date_discovered_in_inventory": (
                        item["internal_date"] in days
                    ),
                }
                for item in wrong_date
            ],
            "rejected_attachments": rejected,
            "unresolved_document_days": unresolved_days,
            "successive_effective_dates_are_revisions": False,
        },
        "h_diesel_january_2024": h_diesel_january_2024(parsed, records, resolutions),
        "ordinary_h_diesel_availability": ordinary_h_diesel_availability(parsed, records),
        "product_label_history": product_label_history(parsed, records),
        "semantic_breaks": {
            "ordinary_h_diesel_absence": ordinary_h_diesel_availability(
                parsed, records
            )["absence_spans"],
            "fuel_oil_label_variant": {
                label: {
                    "first_effective_date": entry["first_effective_date"],
                    "last_effective_date": entry["last_effective_date"],
                    "document_days": entry["document_days"],
                }
                for label, entry in product_label_history(parsed, records).items()
                if entry["unconfirmed_variant_of"]
            },
            "layout_regime_changes": {
                regime: {
                    "first_effective_date": entry["first_effective_date"],
                    "last_effective_date": entry["last_effective_date"],
                    "regime_status": entry["regime_status"],
                }
                for regime, entry in layout_regime_report(parsed, records).items()
            },
            "spliced_silently": False,
            "imputed": False,
            "forward_filled": False,
        },
        "unconfirmed_label_variants": {
            "labels": DP.UNCONFIRMED_LABEL_VARIANTS,
            "daily_rows_flagged": sum(
                1 for r in daily_rows
                if r.get("label_variant_status") == DP.UNCONFIRMED_LABEL_VARIANT
            ),
            "equivalence_established": False,
            "months_blocked": sorted({
                (r["series_id"], r["reference_month"]) for r in monthly_table
                if r["aggregation_status"] == "unit_or_definition_break"
            }),
            "note": (
                "The archive drops the table's ordinal index from both fuel-oil "
                "labels for a bounded interval. C7 keeps the documents, marks "
                "the rows, and refuses to average a month that touches one; "
                "whether the labels name the same series is a semantic decision "
                "outside an ingestion task."
            ),
        },
        "daily_table": {
            "rows": len(daily_rows),
            "unique_key": ["series_id", "effective_date", "semantic_regime_id"],
            "series_counts": dict(Counter(r["series_id"] for r in daily_rows)),
            "quality_flag_counts": dict(Counter(r["quality_flag"] for r in daily_rows)),
            "first_effective_date": min(r["effective_date"] for r in daily_rows),
            "last_effective_date": max(r["effective_date"] for r in daily_rows),
            "is_partial_audit_table": False,
            "output": str(DAILY_PARQUET.relative_to(ROOT)).replace("\\", "/"),
        },
        "monthly_aggregation": {
            **config["monthly_aggregation"],
            "rows": len(monthly_table),
            "reference_month_range": [
                monthly_table[0]["reference_month"], monthly_table[-1]["reference_month"],
            ],
            "status_counts": dict(Counter(
                r["aggregation_status"] for r in monthly_table
            )),
            "output": str(MONTHLY_PARQUET.relative_to(ROOT)).replace("\\", "/"),
        },
        "monthly_completeness": completeness_report(
            inventories, daily_rows, sorted(AUDITED_PRODUCTS.values())
        ),
        "monthly_rows": monthly_table,
        "approval": approval,
        "availability": {
            **config["availability"],
            "source_available_as_of_null_rows": sum(
                1 for r in monthly_table if r["source_available_as_of"] is None
            ),
            "monthly_rows": len(monthly_table),
            "policy_available_month_examples": [
                {
                    "issue_month": example["issue_month"],
                    "latest_permitted_reference_month": AV.permitted_reference_month(
                        example["issue_month"]
                    ),
                    "matches_config": AV.permitted_reference_month(
                        example["issue_month"]
                    ) == example["latest_permitted_reference_month"],
                }
                for example in config["availability"]["examples"]
            ],
            "selected_rows_at_2026_05": len(
                AV.select_monthly_source_available_at_issue(monthly_table, "2026-05")
            ),
        },
        "transformations": config["transformations"],
        "series_readiness": series_readiness,
        "c8_authorization": {
            "monthly_source_table_available": True,
            "predictive_feature_creation_authorized": False,
            "industry_exposure_multiplication_authorized": False,
            "target_join_authorized": False,
            "modeling_authorized": False,
            "note": (
                "C7 delivers a source-level monthly mean. Authorizing a "
                "transformation is a separate decision that has not been taken."
            ),
        },
    }
    payload["content_checksum"] = LIN.content_checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    with open(DOCS / "c7_eppo_full_archive_audit.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")

    write_audit_markdown(payload)
    write_decision_markdown(payload)

    print(json.dumps({
        "invariants_reproduced": invariants["all_reproduced"],
        "discovered_document_days": acquisition.distinct_document_days,
        "retrieval_attempts": acquisition.retrieval_attempts,
        "content_valid_files": content_valid,
        "daily_rows": len(daily_rows),
        "monthly_rows": len(monthly_table),
        "monthly_status_counts": payload["monthly_aggregation"]["status_counts"],
        "monthly_aggregation_contract_approved": approval[
            "monthly_aggregation_contract_approved"
        ],
        "content_checksum": payload["content_checksum"],
        "daily_parquet_shape": list(daily_frame.shape),
        "monthly_parquet_shape": list(monthly_frame.shape),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
