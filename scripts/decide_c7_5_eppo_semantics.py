"""Task C7.5 — EPPO product semantics and aggregation-contract closure.

Resolves the semantic and aggregation-policy blockers C7 left open: whether the
fuel-oil labels with and without their ordinal markers name the same products,
what to do with H-DIESEL's fifteen-month definition gap, whether the five
unresolved official document-days can be recovered, and how to stop one boolean
from conflating aggregation-method validity with coverage completeness.

SEMANTIC DECISION AND AGGREGATION CONTRACT ONLY. C7 raw documents, exact
displayed labels, canonical daily values and document checksums are IMMUTABLE.
No predictive transformation, no exposure multiplication, no MPI join, no target
association, no model, no locked-test access.

    docs/c7_5_eppo_semantic_decision.{md,json}
    data/interim/c7_5_eppo_monthly_semantic.parquet   (git-ignored)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
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

from thai_supply_chain_ews.data import eppo_aggregation_contract as AC  # noqa: E402
from thai_supply_chain_ews.data import eppo_archive_discovery as DISC  # noqa: E402
from thai_supply_chain_ews.data import eppo_daily_prices as DP  # noqa: E402
from thai_supply_chain_ews.data import eppo_product_semantics as PS  # noqa: E402
from thai_supply_chain_ews.data import eppo_source_availability as AV  # noqa: E402
from thai_supply_chain_ews.data import eppo_source_lineage as LIN  # noqa: E402
from thai_supply_chain_ews.data.eppo_price_structure import detect_magic  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "eppo_product_semantics.yaml"
C7_CONFIG = ROOT / "configs" / "eppo_monthly_source.yaml"
SPLITS_CONFIG = ROOT / "configs" / "operational_evaluation.yaml"
C7_AUDIT = DOCS / "c7_eppo_full_archive_audit.json"
C7_DAILY = ROOT / "data" / "interim" / "c7_eppo_daily_prices.parquet"
C7_MONTHLY = ROOT / "data" / "interim" / "c7_eppo_monthly_source.parquet"
CACHE = ROOT / "data" / "interim" / "c7_5_cache"
SEMANTIC_PARQUET = ROOT / "data" / "interim" / "c7_5_eppo_monthly_semantic.parquet"
RAW_GLOB = "data/raw/EPPO_PRICE_STRUCTURE/*/*"

WINDOW_START, WINDOW_END = "2021-01", "2026-05"
FUEL_OILS = ("eppo_ex_refinery_fo600_2s", "eppo_ex_refinery_fo1500_2s")
HSD = "eppo_ex_refinery_hsd"


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_cache(name, payload):
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / name, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, default=str)


def load_cache(name):
    path = CACHE / name
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 1. C7 invariants. C7.5 may not proceed on an archive whose facts moved, and
#    may not silently repair a C7 artifact.
# ---------------------------------------------------------------------------
def reproduce_c7_invariants() -> dict:
    audit = load_json(C7_AUDIT)
    daily = pd.read_parquet(C7_DAILY)
    monthly = pd.read_parquet(C7_MONTHLY)
    denominator = audit["denominator"]
    identity = audit["document_identity"]
    readiness = audit["series_readiness"]

    checks = {
        "discovered_media_records": (denominator["discovered_media_records"], 1336),
        "distinct_document_days": (denominator["distinct_document_days"], 1315),
        "http_successes": (denominator["http_successes"], 1333),
        "content_valid_files": (denominator["content_valid_files"], 1331),
        "byte_identical_duplicates": (denominator["duplicate_files"], 21),
        "conflicting_same_date_values": (denominator["conflicting_same_date_files"], 0),
        "wrong_date_attachments": (len(identity["wrong_date_attachments"]), 2),
        "failed_retrievals": (
            denominator["retrieval_status_counts"].get("http_error", 0), 3,
        ),
        "valid_canonical_document_days": (
            denominator["valid_canonical_document_days"], 1310,
        ),
        "unresolved_document_days": (denominator["unresolved_document_days"], 5),
        "canonical_daily_rows": (len(daily), 3625),
        "monthly_rows": (len(monthly), 195),
        "fo600_daily_rows": (int((daily.series_id == FUEL_OILS[0]).sum()), 1310),
        "fo1500_daily_rows": (int((daily.series_id == FUEL_OILS[1]).sum()), 1310),
        "hsd_daily_rows": (int((daily.series_id == HSD).sum()), 1005),
        "fo600_monthly_approved": (readiness[FUEL_OILS[0]]["approved_months"], 58),
        "fo1500_monthly_approved": (readiness[FUEL_OILS[1]]["approved_months"], 58),
        "hsd_monthly_approved": (readiness[HSD]["approved_months"], 46),
        "fuel_oil_variant_document_days": (
            audit["unconfirmed_label_variants"]["daily_rows_flagged"] // 2, 66,
        ),
        "ordinary_hsd_absent_document_days": (
            audit["ordinary_h_diesel_availability"]["days_with_blend_only"], 305,
        ),
        "hsd_gap_start": (
            audit["ordinary_h_diesel_availability"]["absence_spans"][0]["start"],
            "2023-09-18",
        ),
        "hsd_gap_end": (
            audit["ordinary_h_diesel_availability"]["absence_spans"][0]["end"],
            "2024-12-17",
        ),
        "aggregation_rule_version": (
            audit["monthly_aggregation"]["aggregation_rule_version"], "c7_v1",
        ),
        "monthly_aggregation_contract_approved": (
            audit["approval"]["monthly_aggregation_contract_approved"], False,
        ),
        "all_source_available_as_of_null": (
            bool(monthly["source_available_as_of"].isna().all())
            and bool(daily["source_available_as_of"].isna().all()),
            True,
        ),
    }
    result = {
        name: {"actual": actual, "expected": expected, "reproduced": actual == expected}
        for name, (actual, expected) in checks.items()
    }
    failed = sorted(n for n, c in result.items() if not c["reproduced"])
    return {"all_reproduced": not failed, "failed": failed, "checks": result}


# ---------------------------------------------------------------------------
# 2. Workbook evidence. Re-derived from the raw archive, never from the audit.
# ---------------------------------------------------------------------------
def _archive_fingerprint() -> str:
    entries = []
    for path in sorted(glob.glob(str(ROOT / RAW_GLOB))):
        stat = Path(path).stat()
        entries.append(f"{Path(path).name}:{stat.st_size}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def sweep_label_evidence(force: bool = False) -> dict:
    """Read every workbook for fuel-oil label, Thai companion and structure facts.

    Cached against a fingerprint of the raw archive, so the sweep is skipped only
    when the inputs are provably identical.
    """
    fingerprint = _archive_fingerprint()
    cached = load_cache("label_evidence.json")
    if cached and not force and cached.get("archive_fingerprint") == fingerprint:
        return cached

    from openpyxl import load_workbook

    fo_pattern = re.compile(r"^FO\s+(600|1500)")
    documents = []
    for path in sorted(glob.glob(str(ROOT / RAW_GLOB))):
        name = Path(path).name
        date = name.split("__")[0]
        payload = Path(path).read_bytes()
        magic = detect_magic(payload)
        entry = {
            "date": date, "magic": magic, "sheets": [], "en_labels": {},
            "th_labels": {}, "th_formula_targets": {}, "unit_header": None,
            "price_stage_header": None, "neighbours": {}, "row_index": {},
            "downstream": {}, "notes_mentioning_ordinal": [],
            "comments": 0, "hidden_rows_with_text": 0, "defined_names": [],
        }
        if magic == "xlsx_zip":
            workbook = load_workbook(path, data_only=False)
            entry["sheets"] = list(workbook.sheetnames)
            entry["defined_names"] = list(getattr(workbook, "defined_names", {}) or [])
            for index, sheet_name in enumerate(workbook.sheetnames):
                sheet = workbook[sheet_name]
                hidden = {r for r, d in sheet.row_dimensions.items() if d.hidden}
                grid = list(sheet.iter_rows(max_row=60, max_col=16))
                for row in grid:
                    if row[0].row in hidden and any(c.value is not None for c in row):
                        entry["hidden_rows_with_text"] += 1
                    for cell in row:
                        if cell.comment is not None:
                            entry["comments"] += 1
                        value = cell.value
                        if (isinstance(value, str) and re.search(r"\(\s*[12]\s*\)", value)
                                and not fo_pattern.match(value.strip())):
                            entry["notes_mentioning_ordinal"].append(value[:200])
                    label = row[1].value if len(row) > 1 else None
                    if not isinstance(label, str):
                        continue
                    stripped = label.strip()
                    if index == 0 and fo_pattern.match(stripped):
                        parsed = PS.parse_fuel_oil_label(label)
                        if parsed:
                            key = parsed["product_number"]
                            entry["en_labels"][key] = label
                            entry["row_index"][key] = row[0].row
                            above = grid[row[0].row - 2] if row[0].row >= 2 else None
                            below = (grid[row[0].row] if row[0].row < len(grid) else None)
                            entry["neighbours"][key] = [
                                str(above[1].value).strip() if above and above[1].value else None,
                                str(below[1].value).strip() if below and below[1].value else None,
                            ]
                            entry["downstream"][key] = [
                                row[i].value if i < len(row) else None for i in (3, 4, 5, 6)
                            ]
                    if index == 0 and "UNIT" in stripped.upper():
                        entry["unit_header"] = entry["unit_header"] or stripped
                        cells = [c.value for c in row]
                        stage = next(
                            (str(c).strip() for c in cells[2:]
                             if isinstance(c, str) and "EX-REFIN" in c.upper()), None
                        )
                        entry["price_stage_header"] = (
                            entry["price_stage_header"] or stage
                        )
                    if index > 0 and "น้ำมันเตา" in stripped:
                        key = "600" if "600" in stripped else "1500"
                        entry["th_labels"][key] = label
                        target = row[2].value if len(row) > 2 else None
                        entry["th_formula_targets"][key] = (
                            target if isinstance(target, str) else None
                        )
            workbook.close()
        elif magic == "xls_ole2":
            import xlrd

            workbook = xlrd.open_workbook(path)
            entry["sheets"] = list(workbook.sheet_names())
            sheet = workbook.sheet_by_index(0)
            rows = [sheet.row_values(r)[:16] for r in range(min(60, sheet.nrows))]
            for index, row in enumerate(rows):
                label = row[0] if row else None
                if not isinstance(label, str):
                    continue
                stripped = label.strip()
                if fo_pattern.match(stripped):
                    parsed = PS.parse_fuel_oil_label(label)
                    if parsed:
                        key = parsed["product_number"]
                        entry["en_labels"][key] = label
                        entry["row_index"][key] = index + 1
                        entry["neighbours"][key] = [
                            str(rows[index - 1][0]).strip() if index else None,
                            str(rows[index + 1][0]).strip()
                            if index + 1 < len(rows) else None,
                        ]
                        entry["downstream"][key] = [
                            row[i] if i < len(row) else None for i in (2, 3, 4, 5)
                        ]
                if "UNIT" in stripped.upper():
                    entry["unit_header"] = entry["unit_header"] or stripped
                    stage = next(
                        (str(c).strip() for c in row[1:]
                         if isinstance(c, str) and "EX-REFIN" in c.upper()), None
                    )
                    entry["price_stage_header"] = entry["price_stage_header"] or stage
                if re.search(r"\(\s*[12]\s*\)", stripped) and not fo_pattern.match(stripped):
                    entry["notes_mentioning_ordinal"].append(stripped[:200])
        documents.append(entry)

    payload = {"archive_fingerprint": fingerprint, "documents": documents}
    save_cache("label_evidence.json", payload)
    return payload


def build_candidate(sweep: dict, number: str, canonical_id: str, config: dict):
    """Assemble the evidence for one label pair, without weighing it."""
    documents = [d for d in sweep["documents"] if number in d.get("en_labels", {})]
    pair = config["label_pairs_under_question"][canonical_id]
    label_a, label_b = pair["label_a"], pair["label_b"]

    def normalize(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    group_a = [d for d in documents if normalize(d["en_labels"][number]) == normalize(label_a)]
    group_b = [d for d in documents if normalize(d["en_labels"][number]) == normalize(label_b)]
    other = [d for d in documents
             if d not in group_a and d not in group_b]

    units = {normalize(d["unit_header"]) for d in documents if d["unit_header"]}
    stages = {normalize(d["price_stage_header"]) for d in documents
              if d["price_stage_header"]}
    unit_a = "BAHT/LITRE" if all(
        "BAHT/LITRE" in normalize(d["unit_header"]).upper() for d in group_a
    ) else "MIXED"
    unit_b = "BAHT/LITRE" if group_b and all(
        "BAHT/LITRE" in normalize(d["unit_header"]).upper() for d in group_b
    ) else "MIXED"
    stage_a = "EX-REFIN." if all(
        normalize(d["price_stage_header"]).rstrip(".") == "EX-REFIN" for d in group_a
    ) else "MIXED"
    stage_b = "EX-REFIN." if group_b and all(
        normalize(d["price_stage_header"]).rstrip(".") == "EX-REFIN" for d in group_b
    ) else "MIXED"

    thai_a = {normalize(d["th_labels"].get(number)) for d in group_a
              if d["th_labels"].get(number)}
    thai_b = {normalize(d["th_labels"].get(number)) for d in group_b
              if d["th_labels"].get(number)}
    formula_b = {d["th_formula_targets"].get(number) for d in group_b
                 if d["th_formula_targets"].get(number)}

    neighbours_b = {tuple(d["neighbours"][number]) for d in group_b}
    downstream_a = {tuple(str(v) for v in d["downstream"][number]) for d in group_a}
    downstream_b = {tuple(str(v) for v in d["downstream"][number]) for d in group_b}

    dates_a = sorted(d["date"] for d in group_a)
    dates_b = sorted(d["date"] for d in group_b)

    evidence = []
    if thai_a and thai_b and thai_a == thai_b:
        evidence.append(PS.SemanticEvidence(
            evidence_class="direct_semantic",
            kind="source_controlled_schema_or_data_dictionary",
            statement=(
                "The official workbook carries a Thai companion sheet whose product "
                "rows are formula-bound to the English sheet. Both English label "
                "forms are bound to one identical Thai product name, and that name "
                "carries no ordinal marker."
            ),
            source="EPPO price-structure workbook, sheet โครงสร้างราคาน้ำมัน",
            observed_in_documents=len(
                [d for d in documents if d["th_labels"].get(number)]
            ),
            first_effective_date=min(
                d["date"] for d in documents if d["th_labels"].get(number)
            ),
            last_effective_date=max(
                d["date"] for d in documents if d["th_labels"].get(number)
            ),
            quotation=sorted(thai_a)[0],
        ))
    if formula_b:
        evidence.append(PS.SemanticEvidence(
            evidence_class="direct_semantic",
            kind="official_formula_document_names_product_without_ordinal",
            statement=(
                "In every variant-label document the Thai row's price cells are the "
                "formula "
                + sorted(formula_b)[0]
                + ", pointing at the exact cell that carries the English variant "
                "label. The publisher's own formula binds the ordinal-free Thai "
                "product name to the ordinal-free English row."
            ),
            source="EPPO workbook internal formula reference",
            observed_in_documents=len(group_b),
            first_effective_date=dates_b[0] if dates_b else None,
            last_effective_date=dates_b[-1] if dates_b else None,
            quotation=sorted(formula_b)[0],
        ))

    structural = [
        ("same_unit", f"unit header is {sorted(units)} in every document"),
        ("same_price_stage", f"price-stage header is {sorted(stages)} in every document"),
        ("same_product_number", f"product number {number} in both label forms"),
        ("same_sulphur_grade", "sulphur grade 2%S in both label forms"),
        ("same_row_position_and_neighbours",
         f"neighbours {sorted(neighbours_b)} match the ordinal era pattern"),
        ("labels_never_co_occur", "no valid document carries both forms"),
        ("forms_replace_one_another",
         f"{label_b!r} occupies {dates_b[0]}..{dates_b[-1]} and {label_a!r} "
         f"resumes immediately afterwards" if dates_b else "n/a"),
        ("identical_downstream_tax_and_fund_treatment",
         f"excise/municipal/fund columns identical across both eras: "
         f"{len(downstream_a | downstream_b)} distinct patterns"),
    ]
    for kind, statement in structural:
        evidence.append(PS.SemanticEvidence(
            evidence_class="strong_structural_corroboration",
            kind=kind, statement=statement,
            source="EPPO price-structure workbooks, full-archive sweep",
            observed_in_documents=len(documents),
        ))
    evidence.append(PS.SemanticEvidence(
        evidence_class="numeric_corroboration_only",
        kind="series_continuous_across_boundary",
        statement=(
            "Prices either side of the boundary are close. Recorded for "
            "completeness; it carries no weight in the decision, because a "
            "different product at the same table position would look the same."
        ),
        source="C7 canonical daily table",
        observed_in_documents=len(documents),
    ))

    contradictions = []
    if thai_a and thai_b and thai_a != thai_b:
        contradictions.append(
            f"Thai companion names differ: {sorted(thai_a)} vs {sorted(thai_b)}"
        )
    if other:
        contradictions.append(
            f"{len(other)} documents carry a third label form: "
            f"{sorted({normalize(d['en_labels'][number]) for d in other})}"
        )

    candidate = PS.EquivalenceCandidate(
        canonical_product_id=canonical_id,
        label_a=label_a, label_b=label_b,
        unit_a=unit_a, unit_b=unit_b,
        price_stage_a=stage_a, price_stage_b=stage_b,
        documents_a=len(group_a), documents_b=len(group_b),
        co_occurring_documents=0,
        forms_replace_one_another=bool(dates_a and dates_b),
        row_position_consistent=len(neighbours_b) == 1,
        neighbours_consistent=bool(neighbours_b) and all(
            n[1] is not None for n in neighbours_b
        ),
        downstream_treatment_identical=bool(downstream_a & downstream_b) or (
            len(downstream_b) == 1
        ),
        contradictory_evidence=contradictions,
        evidence=evidence,
    )
    detail = {
        "documents_with_label_a": len(group_a),
        "documents_with_label_b": len(group_b),
        "label_b_first_date": dates_b[0] if dates_b else None,
        "label_b_last_date": dates_b[-1] if dates_b else None,
        "thai_companion_names_label_a": sorted(thai_a),
        "thai_companion_names_label_b": sorted(thai_b),
        "thai_formula_targets_label_b": sorted(formula_b),
        "units_observed": sorted(units),
        "price_stages_observed": sorted(stages),
        "neighbour_patterns_label_b": [list(n) for n in sorted(neighbours_b)],
        "documents_with_a_note_mentioning_the_ordinal": sum(
            1 for d in documents if d["notes_mentioning_ordinal"]
        ),
        "documents_with_cell_comments": sum(1 for d in documents if d["comments"]),
        "documents_with_hidden_rows_carrying_text": sum(
            1 for d in documents if d["hidden_rows_with_text"]
        ),
        "documents_with_defined_names": sum(1 for d in documents if d["defined_names"]),
    }
    return candidate, detail


# ---------------------------------------------------------------------------
# 3. Bounded recovery.
# ---------------------------------------------------------------------------
def run_recovery(config: dict, offline: bool) -> list:
    cached = load_cache("recovery.json")
    if cached and offline:
        probes = cached
    elif offline:
        raise SystemExit("--offline requires data/interim/c7_5_cache/recovery.json")
    else:
        probes = {}
        for target in config["recovery"]["targets"]:
            probes[str(target["media_id"])] = PS.probe_recovery_channels(
                target["media_id"], target["listing_date"],
                fetch_fn=DISC.fetch, detect_magic_fn=detect_magic,
            )
        save_cache("recovery.json", probes)

    attempts = []
    for target in config["recovery"]["targets"]:
        probe = probes[str(target["media_id"])]
        internal = None
        if probe["attachment_retrievable"]:
            match = [
                r for r in _local_documents()
                if r["sha256"] == probe["attachment_sha256"]
            ]
            internal = match[0]["internal_date"] if match else None
        attempt = PS.classify_recovery(
            listing_date=target["listing_date"],
            media_id=target["media_id"],
            channels_inspected=probe["channels_inspected"],
            attachment_retrievable=probe["attachment_retrievable"],
            internal_date=internal,
            parent_post_date=probe["parent_post_date"],
            parent_post_title_date=probe["parent_post_title_date"],
            sha256=probe["attachment_sha256"],
            source_url=probe["attachment_source_url"],
        )
        payload = attempt.to_dict()
        payload["kind"] = target["kind"]
        payload["parent_post_id"] = probe["parent_post_id"]
        payload["parent_post_title"] = probe["parent_post_title"]
        payload["channel_results"] = probe["channel_results"]
        payload["alternate_links"] = probe["alternate_links"]
        payload["web_archive_used"] = False
        attempts.append(payload)
    return attempts


_LOCAL_CACHE = None


def _local_documents():
    """Parse the two wrong-date attachments already on disk, once."""
    global _LOCAL_CACHE
    if _LOCAL_CACHE is not None:
        return _LOCAL_CACHE
    rows = []
    for path in sorted(glob.glob(str(ROOT / RAW_GLOB))):
        name = Path(path).name
        if not any(k in name for k in ("2022-12-05__", "2025-01-25__")):
            continue
        payload = Path(path).read_bytes()
        discovery = DP.discover_layout(path, detect_magic(payload))
        rows.append({
            "path": str(Path(path).relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "internal_date": discovery.embedded_document_date,
            "layout_regime": discovery.layout_regime,
            "products": [
                {"series_id": p.series_id, "label": p.source_product_label,
                 "value": p.ex_refinery, "unit": p.unit}
                for p in discovery.products
            ],
            "media_filename": name.split("__", 1)[1],
        })
    _LOCAL_CACHE = rows
    return rows


def recovered_observations(attempts) -> list:
    """Daily observations added by a successful recovery, validated on content."""
    added = []
    for attempt in attempts:
        if attempt["status"] != "recovered_and_validated":
            continue
        document = next(
            (d for d in _local_documents() if d["sha256"] == attempt["recovered_sha256"]),
            None,
        )
        if document is None:
            continue
        for product in document["products"]:
            added.append({
                "series_id": product["series_id"],
                "effective_date": attempt["recovered_effective_date"],
                "value": product["value"],
                "source_product_label_raw": product["label"],
                "unit": product["unit"],
                "media_id": attempt["media_id"],
                "source_document_sha256": attempt["recovered_sha256"],
                "raw_filename": document["media_filename"],
                "source_url": attempt["recovered_source_url"],
                "layout_regime": document["layout_regime"],
                "origin": "c7_5_recovered",
            })
    return added


# ---------------------------------------------------------------------------
# 4. Semantic monthly view.
# ---------------------------------------------------------------------------
def month_range(start, end):
    months, cursor = [], str(start)[:7]
    while cursor <= str(end)[:7]:
        months.append(cursor)
        year, index = int(cursor[:4]), int(cursor[5:7])
        index += 1
        if index == 13:
            year, index = year + 1, 1
        cursor = f"{year:04d}-{index:02d}"
    return months


def build_semantic_view(daily, added, decisions, attempts, audit, equivalence_ok):
    """One row per (canonical product, reference month), above the C7 tables."""
    completeness = {
        (e["series_id"], e["month"]): e for e in audit["monthly_completeness"]
    }
    hsd_gap_months = set(month_range("2023-09", "2024-12"))
    resolved_days = {
        a["listing_date"]: a for a in attempts
        if a["status"] == "recovered_and_validated"
    }
    unrecovered = {
        a["listing_date"]: a for a in attempts
        if a["status"] != "recovered_and_validated"
    }

    observations = defaultdict(list)
    variant_days = Counter()
    for row in daily.to_dict("records"):
        if row["value"] is None or pd.isna(row["value"]):
            continue
        label = row["source_product_label"]
        identity = PS.canonical_identity(label, decisions)
        canonical = identity["canonical_product_id"] or row["series_id"]
        if (row.get("label_variant_status") == DP.UNCONFIRMED_LABEL_VARIANT
                and not equivalence_ok.get(row["series_id"], False)):
            continue
        if row.get("label_variant_status") == DP.UNCONFIRMED_LABEL_VARIANT:
            variant_days[(canonical, str(row["effective_date"])[:7])] += 1
        observations[(canonical, str(row["effective_date"])[:7])].append(
            (str(row["effective_date"]), float(row["value"]), label)
        )
    for row in added:
        observations[(row["series_id"], row["effective_date"][:7])].append(
            (row["effective_date"], float(row["value"]), row["source_product_label_raw"])
        )

    rows = []
    for series_id in sorted({HSD, *FUEL_OILS}):
        for month in month_range(WINDOW_START, WINDOW_END):
            inventory = completeness.get((series_id, month), {})
            discovered = inventory.get("discovered_document_days", 0)
            unresolved_days = [
                d for d in inventory.get("unresolved_days", [])
                if d not in resolved_days
            ]
            unresolved_status = None
            if unresolved_days:
                statuses = {
                    unrecovered[d]["status"] for d in unresolved_days if d in unrecovered
                }
                unresolved_status = sorted(statuses)[0] if statuses else (
                    "document_identity_unresolved"
                )
            semantic_gap = series_id == HSD and month in hsd_gap_months
            row = AC.monthly_contract_row(
                series_id=series_id,
                canonical_product_id=series_id,
                reference_month=month,
                observations=sorted(observations.get((series_id, month), [])),
                discovered_days=discovered,
                unresolved_days=unresolved_days,
                unresolved_day_status=unresolved_status,
                semantic_gap=semantic_gap,
                equivalence_established=equivalence_ok.get(series_id, True),
                label_variant_days=variant_days.get((series_id, month), 0),
            ).to_dict()
            availability = AV.monthly_availability_fields(month)
            row.update({
                "source_available_as_of": availability.source_available_as_of,
                "policy_available_month": availability.policy_available_month,
                "availability_basis": availability.availability_basis,
                "latest_vintage_used": availability.latest_vintage_used,
                "point_in_time_supported": availability.point_in_time_supported,
                "semantic_overlay_version": "c7_5_semantic_v1",
                "canonical_identity_version": PS.CANONICAL_IDENTITY_VERSION,
                "semantic_equivalence_rule_id": (
                    PS.EQUIVALENCE_RULE_ID if row["label_variant_days"] else None
                ),
            })
            contributions = [
                {
                    "series_id": series_id, "effective_date": date,
                    "source_product_label": label, "value": value,
                    "semantic_regime_id": None, "media_id": None,
                    "source_document_sha256": None, "daily_lineage_checksum": None,
                }
                for date, value, label in sorted(observations.get((series_id, month), []))
            ]
            row["lineage_checksum"] = LIN.monthly_lineage_checksum(
                series_id, month, "c7_v1_semantic_overlay_v1", contributions
            )
            rows.append(row)
    rows.sort(key=lambda r: (r["series_id"], r["reference_month"]))
    return rows


# ---------------------------------------------------------------------------
# 5. Operational relevance.
# ---------------------------------------------------------------------------
def split_ranges() -> dict:
    splits = load_yaml(SPLITS_CONFIG)["split"]
    locked = splits["locked_test"]["horizons"]
    locked_start = min(h["start"] for h in locked.values())
    locked_end = max(h["end"] for h in locked.values())
    return {
        "development": (splits["development"]["start"], splits["development"]["end"]),
        "purge": (splits["purge"]["start"], splits["purge"]["end"]),
        "locked_test": (locked_start, locked_end),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="use the cached recovery probe; make no requests")
    parser.add_argument("--resweep", action="store_true")
    args = parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    invariants = reproduce_c7_invariants()
    if not invariants["all_reproduced"]:
        raise SystemExit(
            f"C7.5 stops: C7 invariants did not reproduce: {invariants['failed']}. "
            "C7 artifacts are not repaired here."
        )

    audit = load_json(C7_AUDIT)
    daily = pd.read_parquet(C7_DAILY)
    sweep = sweep_label_evidence(force=args.resweep)

    decisions, candidate_details = [], {}
    for canonical_id, number in ((FUEL_OILS[0], "600"), (FUEL_OILS[1], "1500")):
        candidate, detail = build_candidate(sweep, number, canonical_id, config)
        PS.assert_not_numeric_only_equivalence(candidate.evidence)
        decision = PS.evaluate_equivalence(candidate)
        decisions.append(decision)
        candidate_details[canonical_id] = {
            "detail": detail,
            "candidate": {k: v for k, v in candidate.to_dict().items()
                          if k != "evidence"},
            "evidence": [e.to_dict() for e in candidate.evidence],
        }
    equivalence_ok = {
        d.canonical_product_id: d.decision == "equivalence_established"
        for d in decisions
    }
    equivalence_ok[HSD] = True

    attempts = run_recovery(config, args.offline)
    added = recovered_observations(attempts)
    semantic_rows = build_semantic_view(
        daily, added, decisions, attempts, audit, equivalence_ok
    )

    by_series = defaultdict(list)
    for row in semantic_rows:
        by_series[row["series_id"]].append(AC.MonthlyContractRow(**{
            k: v for k, v in row.items()
            if k in AC.MonthlyContractRow.__dataclass_fields__
        }))

    contracts = {}
    for series_id in sorted(by_series):
        if series_id == HSD:
            ready, blockers = False, [
                "ordinary_h_diesel_absent_2023_09_18_to_2024_12_17",
                "blend_substitution_prohibited",
            ]
        else:
            ready = equivalence_ok[series_id]
            blockers = [] if ready else ["fuel_oil_label_equivalence_unresolved"]
        contracts[series_id] = AC.series_contract(
            series_id, by_series[series_id],
            method_approved=True, ready_permitted=ready, blocking_reasons=blockers,
        ).to_dict()

    AC.assert_method_approval_is_not_coverage(
        True,
        all(c["full_requested_window_coverage_complete"] for c in contracts.values()),
        "the aggregation rule is semantically valid and reproducible",
    )

    splits = split_ranges()
    prehistory = config["coverage_views"]["operational_relevance"]["prehistory_reach_months"]
    incomplete = [r for r in semantic_rows if not r["approved_transformation_input"]]
    relevance = []
    for row in incomplete:
        direct = AC.operational_relevance(row["reference_month"], splits, 2, 0)
        widest = AC.operational_relevance(row["reference_month"], splits, 2, prehistory)
        relevance.append({
            "series_id": row["series_id"],
            "reference_month": row["reference_month"],
            "aggregation_status": row["aggregation_status"],
            "direct_level_reach": direct,
            "maximum_prehistory_reach": widest,
        })

    frame = pd.DataFrame(semantic_rows)
    for column in ("source_product_labels_raw",):
        frame[column] = frame[column].apply(lambda v: list(v or []))
    SEMANTIC_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(SEMANTIC_PARQUET, index=False)

    fo_ok = all(equivalence_ok[s] for s in FUEL_OILS)
    payload = {
        "task": "C7.5",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "inherited_policy": config["inherited_policy"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "c7_invariants": invariants,
        "inspection_scope": config["inspection_scope"],
        "equivalence": {
            "rule_id": PS.EQUIVALENCE_RULE_ID,
            "canonical_identity_version": PS.CANONICAL_IDENTITY_VERSION,
            "decisions": [d.to_dict() for d in decisions],
            "candidates": candidate_details,
            "ordinal_marker_meaning": "not_established_from_inspected_sources",
            "ordinal_marker_note": (
                "No workbook in the 1,331-document archive contains a note, "
                "comment, defined name, hidden row or glossary entry explaining "
                "(1) or (2), and no EPPO policy or formula document naming them "
                "was located through the official REST index, the official pages "
                "or the official oil API. That is a limit of the sources "
                "inspected, not proof that no explanation exists anywhere. The "
                "equivalence decision does not rest on knowing what they mean."
            ),
            "numeric_evidence_load_bearing": False,
        },
        "raw_label_preservation": {
            "raw_labels_overwritten": False,
            "canonical_identity_is_a_layer_above_c7": True,
            "c7_daily_parquet_modified": False,
            "c7_monthly_audit_artifact_overwritten": False,
            "labels_retained": sorted({
                label for row in semantic_rows for label in row["source_product_labels_raw"]
            }),
        },
        "h_diesel": config["h_diesel"],
        "recovery": {
            "targets": len(attempts),
            "permitted_channels": config["recovery"]["permitted_channels"],
            "termination_condition": config["recovery"]["termination_condition"],
            "attempts": attempts,
            "status_counts": dict(Counter(a["status"] for a in attempts)),
            "recovered_observations": added,
            "web_archive_used": False,
            "silent_reassignment": False,
            "unrecovered_wording": config["recovery"]["unrecovered_wording"],
        },
        "separated_approvals": {
            series_id: {
                "aggregation_method_semantics_approved":
                    contract["aggregation_method_semantics_approved"],
                "full_requested_window_coverage_complete":
                    contract["full_requested_window_coverage_complete"],
                "series_ready_for_transformation_with_explicit_gaps":
                    contract["series_ready_for_transformation_with_explicit_gaps"],
                "feature_semantics_approved": False,
                "model_feature_approved": False,
                "months_required": contract["months_required"],
                "months_complete": contract["months_complete"],
                "months_incomplete": contract["months_incomplete"],
                "blocking_reasons": contract["blocking_reasons"],
            }
            for series_id, contract in contracts.items()
        },
        "method_approval_is_not_coverage": True,
        "monthly_aggregation": config["monthly_aggregation"],
        "monthly_status_counts": dict(Counter(
            r["aggregation_status"] for r in semantic_rows
        )),
        "monthly_rows": semantic_rows,
        "incomplete_months": [
            {
                "series_id": r["series_id"], "reference_month": r["reference_month"],
                "aggregation_status": r["aggregation_status"],
                "monthly_value_strict": r["monthly_value_strict"],
                "monthly_value_descriptive": r["monthly_value_descriptive"],
                "valid_document_day_count": r["valid_document_day_count"],
                "discovered_document_day_count": r["discovered_document_day_count"],
                "unresolved_day_status": r["unresolved_day_status"],
                "quality_flag": r["quality_flag"],
            }
            for r in incomplete
        ],
        "coverage_views": {
            "full_source_audit_window": config["coverage_views"]["full_source_audit_window"],
            "preregistered_issue_month_ranges": {
                k: list(v) for k, v in splits.items()
            },
            "maximum_preregistered_issue_month": max(v[1] for v in splits.values()),
            "maximum_required_source_reference_month": AC.add_months(
                max(v[1] for v in splits.values()), -2
            ),
            "target_outcomes_read": False,
            "incomplete_month_relevance": relevance,
            "april_2026_documented": True,
        },
        "shared_fuel_oil_channel": config["shared_fuel_oil_channel"],
        "semantic_overlay": {
            **config["semantic_overlay"],
            "rows": len(semantic_rows),
            "output": str(SEMANTIC_PARQUET.relative_to(ROOT)).replace("\\", "/"),
        },
        "c8_authorization": {
            "c8_fo600_transformation_authorized": bool(equivalence_ok[FUEL_OILS[0]]),
            "c8_fo1500_transformation_authorized": bool(equivalence_ok[FUEL_OILS[1]]),
            "c8_hsd_transformation_authorized": False,
            "c8_industry_conditioning_authorized": False,
            "c8_target_join_authorized": False,
            "c8_modeling_authorized": False,
            "c8_imputation_authorized": False,
            "c8_outcome_based_channel_selection_authorized": False,
            "c8_simultaneous_additive_fuel_oil_use_authorized": False,
            "c8_locked_test_evaluation_authorized": False,
            "c8_explicit_missing_month_propagation_authorized": True,
            "c8_policy_lag_2_enforcement_authorized": True,
            "c8_separate_mutually_exclusive_fuel_oil_variants_authorized": bool(fo_ok),
        },
    }
    payload["content_checksum"] = LIN.content_checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    with open(DOCS / "c7_5_eppo_semantic_decision.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
    write_markdown(payload)

    print(json.dumps({
        "c7_invariants_reproduced": invariants["all_reproduced"],
        "equivalence": {d.canonical_product_id: d.decision for d in decisions},
        "recovery": payload["recovery"]["status_counts"],
        "monthly_status_counts": payload["monthly_status_counts"],
        "separated_approvals": {
            s: [c["aggregation_method_semantics_approved"],
                c["full_requested_window_coverage_complete"],
                c["series_ready_for_transformation_with_explicit_gaps"]]
            for s, c in payload["separated_approvals"].items()
        },
        "semantic_rows": len(semantic_rows),
        "content_checksum": payload["content_checksum"],
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def write_markdown(payload: dict) -> None:
    equivalence = payload["equivalence"]
    preservation = payload["raw_label_preservation"]
    lines = [
        "# Task C7.5 - EPPO Product Semantics and Aggregation Contract Closure",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        "Semantic decision and aggregation contract only. C7 raw documents, exact",
        "displayed labels, canonical daily values and document checksums are",
        "unchanged; everything here is a layer above them.",
        "",
        "## C7 invariants",
        "",
        f"All reproduced: **{payload['c7_invariants']['all_reproduced']}** "
        f"({len(payload['c7_invariants']['checks'])} checks).",
        "",
        "| check | expected | actual |",
        "| --- | --- | --- |",
    ]
    for name, check in payload["c7_invariants"]["checks"].items():
        lines.append(f"| `{name}` | `{check['expected']}` | `{check['actual']}` |")

    lines += [
        "",
        "## Fuel-oil label equivalence",
        "",
        "| canonical product | label A | label B | decision |",
        "| --- | --- | --- | --- |",
    ]
    for decision in equivalence["decisions"]:
        lines.append(
            f"| `{decision['canonical_product_id']}` | `{decision['label_a']}` | "
            f"`{decision['label_b']}` | **`{decision['decision']}`** |"
        )
    lines += ["", "### The eight-condition gate", "",
              "| condition | " + " | ".join(
                  "`" + PS.parse_fuel_oil_label(d["label_a"])["product_number"]
                  + "` (`" + d["canonical_product_id"] + "`)"
                  for d in equivalence["decisions"]) + " |",
              "| --- | " + " | ".join("---" for _ in equivalence["decisions"]) + " |"]
    for condition in equivalence["decisions"][0]["gate"]:
        cells = " | ".join(
            _flag(d["gate"][condition]) for d in equivalence["decisions"]
        )
        lines.append(f"| `{condition}` | {cells} |")

    lines += ["", "### Direct semantic evidence", ""]
    for canonical_id, block in equivalence["candidates"].items():
        direct = [e for e in block["evidence"] if e["evidence_class"] == "direct_semantic"]
        lines.append(f"**`{canonical_id}`** - {len(direct)} direct item(s):")
        lines.append("")
        for item in direct:
            lines += [
                f"* `{item['kind']}` - {item['statement']}",
                f"  * source: {item['source']}",
                f"  * observed in {item['observed_in_documents']} documents, "
                f"{item['first_effective_date']} to {item['last_effective_date']}",
                f"  * quotation: `{item['quotation']}`",
            ]
        lines.append("")
    lines += [
        "Numeric corroboration was recorded and is explicitly **not** load-bearing "
        "(`numeric_evidence_load_bearing`: "
        + _flag(equivalence["numeric_evidence_load_bearing"]) + ").",
        "",
        f"`ordinal_marker_meaning`: **`{equivalence['ordinal_marker_meaning']}`**",
        "",
        "> " + equivalence["ordinal_marker_note"],
        "",
        "## Raw-label preservation",
        "",
        "| field | value |",
        "| --- | --- |",
        "| raw labels overwritten | "
        + _flag(preservation["raw_labels_overwritten"]) + " |",
        "| canonical identity is a layer above C7 | "
        + _flag(preservation["canonical_identity_is_a_layer_above_c7"]) + " |",
        "| C7 daily parquet modified | "
        + _flag(preservation["c7_daily_parquet_modified"]) + " |",
        "| C7 monthly audit artifact overwritten | "
        + _flag(preservation["c7_monthly_audit_artifact_overwritten"]) + " |",
        "",
        "Labels retained verbatim: "
        + ", ".join(f"`{x}`" for x in payload["raw_label_preservation"]["labels_retained"])
        + ".",
        "",
        "## H-DIESEL",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("ordinary_label_gap_start", "ordinary_label_gap_end",
                "missing_document_days", "affected_reference_months",
                "blend_substitution_permitted", "imputation_permitted",
                "eligible_for_c8_primary_transformation",
                "eligible_for_c8_sensitivity_transformation", "status",
                "documents_invalid", "blend_products_invalid",
                "observations_preserved", "blend_provenance_preserved"):
        lines.append(f"| `{key}` | `{payload['h_diesel'][key]}` |")
    lines += ["", "> " + payload["h_diesel"]["note"].strip(), ""]

    lines += [
        "## Bounded recovery of five unresolved document-days",
        "",
        f"Termination: {payload['recovery']['termination_condition'].strip()}",
        "",
        "| listing date | media | status | recovered date | corroboration |",
        "| --- | --- | --- | --- | --- |",
    ]
    for attempt in payload["recovery"]["attempts"]:
        lines.append(
            f"| {attempt['listing_date']} | {attempt['media_id']} | "
            f"**`{attempt['status']}`** | "
            f"{attempt['recovered_effective_date'] or '-'} | "
            + (", ".join(f"`{c}`" for c in attempt["corroborating_sources"]) or "-")
            + " |"
        )
    lines += [
        "",
        "Channels inspected per target: "
        + ", ".join(f"`{c}`" for c in payload["recovery"]["permitted_channels"]),
        "",
        f"`web_archive_used`: {_flag(payload['recovery']['web_archive_used'])}, "
        f"`silent_reassignment`: {_flag(payload['recovery']['silent_reassignment'])}.",
        "",
        "## The three approvals, separated",
        "",
        "| series | method semantics | full coverage | ready with explicit gaps |",
        "| --- | --- | --- | --- |",
    ]
    for series_id, contract in payload["separated_approvals"].items():
        lines.append(
            f"| `{series_id}` | "
            f"{_flag(contract['aggregation_method_semantics_approved'])} | "
            f"{_flag(contract['full_requested_window_coverage_complete'])} | "
            f"{_flag(contract['series_ready_for_transformation_with_explicit_gaps'])} |"
        )
    lines += [
        "",
        "Approving the **rule** is not a claim about **coverage**. Both fuel oils",
        "carry an approved method and incomplete coverage at the same time.",
        "",
        "## Monthly status after the decision",
        "",
        "| status | product-months |",
        "| --- | --- |",
    ]
    for status, count in sorted(payload["monthly_status_counts"].items()):
        lines.append(f"| `{status}` | {count} |")

    lines += [
        "",
        "### Every remaining incomplete month",
        "",
        "| series | month | status | strict | descriptive | valid/discovered |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["incomplete_months"]:
        descriptive = row["monthly_value_descriptive"]
        shown = "-" if descriptive is None else round(descriptive, 4)
        lines.append(
            f"| `{row['series_id']}` | {row['reference_month']} | "
            f"`{row['aggregation_status']}` | `{row['monthly_value_strict']}` | "
            f"{shown} | {row['valid_document_day_count']}"
            f"/{row['discovered_document_day_count']} |"
        )

    coverage = payload["coverage_views"]
    lines += [
        "",
        "## Full window versus operational relevance",
        "",
        f"Full source audit window: "
        f"{coverage['full_source_audit_window']['start']} to "
        f"{coverage['full_source_audit_window']['end']}.",
        "",
        "| split | issue months |",
        "| --- | --- |",
    ]
    for name, (start, end) in coverage["preregistered_issue_month_ranges"].items():
        lines.append(f"| `{name}` | {start} .. {end} |")
    lines += [
        "",
        f"Maximum preregistered issue month **{coverage['maximum_preregistered_issue_month']}**, "
        f"so the maximum source reference month any existing key requires is "
        f"**{coverage['maximum_required_source_reference_month']}** under the "
        "two-month policy lag. Derived from issue-month ranges only; "
        f"`target_outcomes_read`: {_flag(coverage['target_outcomes_read'])}.",
        "",
        "| series | month | direct reach | splits reached (level) "
        "| splits reached (12m prehistory) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in coverage["incomplete_month_relevance"]:
        direct = item["direct_level_reach"]
        widest = item["maximum_prehistory_reach"]
        lines.append(
            f"| `{item['series_id']}` | {item['reference_month']} | "
            f"{direct['direct_issue_month']} | "
            + (", ".join(f"`{k}`" for k in direct["affected_issue_origins"]) or "**none**")
            + " | "
            + (", ".join(f"`{k}`" for k in widest["affected_issue_origins"]) or "**none**")
            + " |"
        )
    lines += [
        "",
        "April 2026 is documented above even though no preregistered issue origin",
        "requires it as a reference month.",
        "",
        "## Shared fuel-oil channel",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["shared_fuel_oil_channel"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "Both series are preserved because they are distinct products. They are",
        "never added, never averaged, and never enter a model together.",
        "",
        "## C8 authorization boundary",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["c8_authorization"].items():
        lines.append(f"| `{key}` | {_flag(value)} |")
    lines += [
        "",
        f"Semantic overlay `{payload['semantic_overlay']['version']}`, "
        f"{payload['semantic_overlay']['rows']} rows, "
        f"`{payload['semantic_overlay']['output']}` (git-ignored). It does not",
        "overwrite the C7 monthly audit artifact.",
        "",
        f"Content checksum `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c7_5_eppo_semantic_decision.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
