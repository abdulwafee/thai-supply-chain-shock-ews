"""Task A1 history-extension audit — correction pass.

The previous history-extension section of docs/task_a1_report.md had three
real problems this script exists to fix:

1. **An arithmetic contradiction.** It asserted both 18 and 19 as the count
   of TSIC divisions common to the current and 2016-based editions, without
   ever computing the intersection in code. This script computes every
   division set and every pairwise intersection with real Python `set`
   operations — nothing is typed in by hand anywhere in this file or in the
   report it generates.
2. **Capacity Utilization was never inspected for the older editions** — only
   older MPI was. This script audits MPI and Capacity Utilization from every
   edition **separately**; nothing assumes they match.
3. **The 2011-based edition (`index2554_2561.zip`) was never downloaded.**
   This script downloads it for real, persists it with a full manifest (not
   a temporary file deleted before the result could be reproduced), and
   inspects it exactly like the other two editions.

A genuinely new finding surfaces from that last point: **the 2011-based
edition labels its division rows "ISIC :", not "TSIC :"** — the two later
editions (2016-based and current) both use "TSIC :". This script treats
that as a recorded fact (`classification_label` per edition), not something
to silently normalize away — whether "ISIC" here means the same division
boundaries as "TSIC 2009" is not confirmed by anything in the archive (no
methodology document was found in any of the three editions' file listings)
and is treated as an open question in the report, not assumed either way.

This script does **not** perform level-linking or growth-rate-linking. It
produces the evidence a future, separate task would need to decide whether
and how to bridge editions — per this task's explicit restriction.

Usage:
    python scripts/audit_history_extension.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:  # pragma: no cover
    print("openpyxl is required: pip install openpyxl", file=sys.stderr)
    raise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Reuse the header-scanning primitives from audit_target_sources.py (month
# column / date parsing does not depend on the TSIC-vs-ISIC label, so no
# duplication is needed there) rather than reimplementing them.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_target_sources as base_audit  # noqa: E402

DIVISION_LABEL_PATTERN = re.compile(r"^(TSIC|ISIC)\s*:\s*(\d\d)\s")

INDUSTRY_TSIC_DIVISIONS = base_audit.INDUSTRY_TSIC_DIVISIONS

# --- editions under audit ---------------------------------------------------
# The "current" edition's files are the ones already verified and persisted
# under data/raw/OIE_MPI/ and data/raw/OIE_CAPU/ by audit_target_sources.py's
# own manifest — resolved the same way, not a second hard-coded path.
EDITION_ARCHIVE_SOURCES = {
    "2559_2016": {
        "label": "2016-based edition (ปี 2559)",
        "url": "https://www.oie.go.th/assets/portals/1/fileups/2/files/Industrial%20index/indexes/index2559_2566.zip",
        "manifest_dir": RAW_DIR / "OIE_MPI_HIST_2559_2566" / "2026-08-26",
        "zip_name": "index2559_2566.zip",
        "mpi_filename": "Prodidx1.xlsx",
        "capu_filename": "capidx.xlsx",
    },
    "2554_2011": {
        "label": "2011-based edition (ปี 2554)",
        "url": "https://www.oie.go.th/assets/portals/1/fileups/2/files/Industrial%20index/indexes/index2554_2561.zip",
        "manifest_dir": RAW_DIR / "OIE_MPI_HIST_2554_2561" / "2026-08-26",
        "zip_name": "index2554_2561.zip",
        "mpi_filename": "Prodidx1.xlsx",
        "capu_filename": "capidx.xlsx",
    },
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class ManifestEntry:
    source_id: str
    official_url: str
    retrieved_at: str
    http_status: int
    file_name: str
    file_size_bytes: int
    sha256: str
    edition_label: str
    archive_contents: list[str]


def write_manifest(source_id: str, entry: ManifestEntry) -> Path:
    manifest_dir = RAW_DIR / "_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{source_id}_manifest.jsonl"
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    return manifest_path


@dataclass
class EditionComponentAudit:
    edition_id: str
    component: str  # "MPI" or "CapU"
    file_path: str
    classification_label: str  # "TSIC" or "ISIC" — recorded, never assumed
    divisions_found: list[int] = field(default_factory=list)
    weight_sum: float = 0.0
    duplicate_divisions: dict[int, int] = field(default_factory=dict)  # division -> occurrence #
    earliest_month: str = ""
    latest_month: str = ""
    month_count: int = 0
    is_chronological: bool = True
    has_duplicate_months: bool = False
    gap_months: list[str] = field(default_factory=list)


def find_division_label_column_generalized(rows: list[tuple]) -> tuple[int, str]:
    """Like base_audit.find_tsic_label_column, but also matches "ISIC :"
    (found in the 2011-based edition) and reports which prefix was used.
    """
    for row in rows[:50]:
        for col_idx, value in enumerate(row[:6]):
            if isinstance(value, str):
                m = DIVISION_LABEL_PATTERN.match(value)
                if m:
                    return col_idx, m.group(1)
    raise ValueError("Could not locate a TSIC- or ISIC-labeled row in the first 50 rows")


def audit_edition_component(edition_id: str, component: str, path: Path) -> EditionComponentAudit:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))

    label_col, classification_label = find_division_label_column_generalized(rows)
    month_col_start = base_audit.find_first_month_column(rows, label_col)
    date_audit = base_audit.parse_monthly_dates(rows, month_col_start)
    month_count = len(date_audit.dates)
    weight_col = label_col + 1

    divisions_found: list[int] = []
    occurrence_count: dict[int, int] = {}
    weight_sum = 0.0
    for row in rows:
        label = row[label_col] if label_col < len(row) else None
        if not isinstance(label, str):
            continue
        m = DIVISION_LABEL_PATTERN.match(label)
        if not m:
            continue
        division = int(m.group(2))
        occurrence_count[division] = occurrence_count.get(division, 0) + 1
        if occurrence_count[division] == 1:
            divisions_found.append(division)
            weight_val = row[weight_col] if weight_col < len(row) else None
            try:
                weight_sum += float(weight_val)
            except (TypeError, ValueError):
                pass

    duplicates = {d: n for d, n in occurrence_count.items() if n > 1}

    return EditionComponentAudit(
        edition_id=edition_id,
        component=component,
        file_path=str(path.relative_to(PROJECT_ROOT)),
        classification_label=classification_label,
        divisions_found=sorted(divisions_found),
        weight_sum=round(weight_sum, 4),
        duplicate_divisions=duplicates,
        earliest_month=date_audit.earliest.isoformat(),
        latest_month=date_audit.latest.isoformat(),
        month_count=month_count,
        is_chronological=date_audit.is_chronological,
        has_duplicate_months=date_audit.has_duplicates,
        gap_months=date_audit.gap_months,
    )


def retrieve_and_manifest_edition(edition_key: str) -> None:
    """Download (if not already present), extract, and write a full
    manifest for one older edition. Idempotent: does not re-download if the
    zip already exists on disk with the expected name.
    """
    import urllib.request

    spec = EDITION_ARCHIVE_SOURCES[edition_key]
    manifest_dir = spec["manifest_dir"]
    zip_path = manifest_dir / spec["zip_name"]
    extract_dir = manifest_dir / "extracted"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    already_downloaded = zip_path.is_file()
    http_status = None
    if not already_downloaded:
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            http_status = resp.status
            zip_path.write_bytes(resp.read())

    if not extract_dir.is_dir() or not any(extract_dir.iterdir()):
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

    if already_downloaded:
        # Idempotent re-run against an already-retrieved file: do not append
        # a new manifest line claiming a fresh retrieval that did not
        # happen. The original manifest entry (written the first time this
        # ran) remains the accurate record.
        return

    archive_contents = sorted(p.name for p in extract_dir.iterdir() if p.is_file())

    entry = ManifestEntry(
        source_id=f"OIE_MPI_HIST_{edition_key}",
        official_url=spec["url"],
        retrieved_at=datetime.now(UTC).isoformat(),
        http_status=http_status,
        file_name=spec["zip_name"],
        file_size_bytes=zip_path.stat().st_size,
        sha256=sha256_of(zip_path),
        edition_label=spec["label"],
        archive_contents=archive_contents,
    )
    write_manifest(f"OIE_MPI_HIST_{edition_key}", entry)


def compute_pairwise_comparison(
    edition_a: str, set_a: list[int], edition_b: str, set_b: list[int]
) -> dict:
    """Real set operations — the intersection count is ALWAYS len() of the
    intersection list computed here, never typed in separately anywhere.
    """
    a, b = set(set_a), set(set_b)
    intersection = sorted(a & b)
    only_a = sorted(a - b)
    only_b = sorted(b - a)
    return {
        "edition_a": edition_a,
        "edition_b": edition_b,
        "divisions_a": sorted(a),
        "divisions_b": sorted(b),
        "intersection": intersection,
        "intersection_count": len(intersection),
        "only_in_a": only_a,
        "only_in_b": only_b,
    }


def build_industry_bridge_table(
    edition_a_id: str,
    audit_a: EditionComponentAudit,
    edition_b_id: str,
    audit_b: EditionComponentAudit,
) -> dict[str, dict]:
    """Per-industry, 4-stage bridge status for ONE pair of editions.

    Task A2 quality-gate revision: `bridge_possible` (a single collapsed
    boolean) is replaced by four explicit stages, computed in this order —
    each is a precondition for the next, and this function only ever sets
    the first two. `overlap_validated` and `bridge_approved` require real
    empirical evidence (Pearson/Spearman correlation, bias, stability across
    years — `scripts/validate_oie_overlap.py`) that this structural-only
    audit does not compute, so they are always `False` here regardless of
    how clean the division composition looks. Do not treat a `True`
    `composition_consistent` as if it were `bridge_approved` — that
    conflation is exactly what this revision corrects.

    - `composition_consistent`: the same *set* of required divisions is
      present in both editions (the same check as the previous revision's
      `composition_identical_across_editions`, renamed to make clear this is
      only the first of four gates, not the final word).
    - `classification_compatible`: `True` only when both editions use the
      identical classification label (`"TSIC"` in both, or `"ISIC"` in both).
      When the labels differ (the current/2016-based TSIC editions vs. the
      2011-based ISIC edition), this is the string `"unresolved"` — an
      explicit non-boolean sentinel, not `False`, because "incompatible" and
      "not yet confirmed compatible" are different claims and this project
      has no methodology document to tell them apart (docs/task_a1_report.md
      §7.1). Identical division *numbers* alone (§7.2's finding that the
      2011 and 2016 editions share the same 21 divisions) does NOT imply
      classification compatibility — that would be inferring semantic
      equivalence from numeric coincidence, which this function refuses to
      do.
    - `overlap_validated`: always `False` here — set by a downstream,
      evidence-producing script only.
    - `bridge_approved`: always `False` here, for the same reason.
    """
    table = {}
    both_tsic = audit_a.classification_label == audit_b.classification_label == "TSIC"
    both_isic = audit_a.classification_label == audit_b.classification_label == "ISIC"
    if both_tsic or both_isic:
        classification_compatible: bool | str = True
    else:
        classification_compatible = "unresolved"

    for industry_id, required in INDUSTRY_TSIC_DIVISIONS.items():
        required_set = set(required)
        present_a = sorted(required_set & set(audit_a.divisions_found))
        present_b = sorted(required_set & set(audit_b.divisions_found))
        composition_consistent = present_a == present_b and len(present_a) > 0

        coverage = {
            edition_a_id: (
                "full" if len(present_a) == len(required) else "partial" if present_a else "none"
            ),
            edition_b_id: (
                "full" if len(present_b) == len(required) else "partial" if present_b else "none"
            ),
        }

        reason = None
        if not composition_consistent:
            reason = (
                "Present-division set differs across editions — a series built from "
                "different divisions in different periods changes meaning at the "
                "bridge date and is not a clean bridge, regardless of edition-level "
                "coverage counts."
            )
        elif classification_compatible != True:  # noqa: E712 — "unresolved" must not shortcut here
            reason = (
                "Classification label differs between editions (TSIC vs. ISIC) and no "
                "methodology document confirms semantic equivalence — treated as "
                "unresolved, not assumed compatible."
            )

        table[industry_id] = {
            "required_divisions": sorted(required),
            "present_by_edition": {edition_a_id: present_a, edition_b_id: present_b},
            "coverage_by_edition": coverage,
            "composition_consistent": composition_consistent,
            "classification_compatible": classification_compatible,
            "overlap_validated": False,
            "bridge_approved": False,
            "reason_if_blocked": reason,
        }
    return table


def main() -> None:
    print("Retrieving and manifesting older editions (idempotent)...")
    for edition_key in EDITION_ARCHIVE_SOURCES:
        retrieve_and_manifest_edition(edition_key)

    current_mpi_path = base_audit.resolve_retrieval_path("OIE_MPI")
    current_capu_path = base_audit.resolve_retrieval_path("OIE_CAPU")

    audits: dict[str, EditionComponentAudit] = {}
    audits["current_MPI"] = audit_edition_component("current", "MPI", current_mpi_path)
    audits["current_CapU"] = audit_edition_component("current", "CapU", current_capu_path)

    for edition_key, spec in EDITION_ARCHIVE_SOURCES.items():
        extract_dir = spec["manifest_dir"] / "extracted"
        audits[f"{edition_key}_MPI"] = audit_edition_component(
            edition_key, "MPI", extract_dir / spec["mpi_filename"]
        )
        audits[f"{edition_key}_CapU"] = audit_edition_component(
            edition_key, "CapU", extract_dir / spec["capu_filename"]
        )

    # Pairwise comparisons, per component, computed with real set operations.
    pairwise: dict[str, dict] = {}
    for component in ("MPI", "CapU"):
        keys = [k for k in audits if k.endswith(f"_{component}")]
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                pairwise[f"{a}__vs__{b}"] = compute_pairwise_comparison(
                    a, audits[a].divisions_found, b, audits[b].divisions_found
                )

    # Per-industry, PER-PAIR bridge tables (4-stage status), computed
    # independently for MPI and CapU. Task A2: a table is now built once per
    # edition pair, not once across all editions at once — this is what lets
    # classification_compatible correctly read "unresolved" only for pairs
    # that actually involve the ISIC edition, rather than poisoning the
    # current/2016-based TSIC-only comparison.
    bridge_tables: dict[str, dict[str, dict]] = {}
    for component in ("MPI", "CapU"):
        editions_for_component = {
            k.rsplit(f"_{component}", 1)[0]: v
            for k, v in audits.items()
            if k.endswith(f"_{component}")
        }
        edition_ids = list(editions_for_component.keys())
        for i in range(len(edition_ids)):
            for j in range(i + 1, len(edition_ids)):
                a_id, b_id = edition_ids[i], edition_ids[j]
                pair_key = f"{component}__{a_id}__vs__{b_id}"
                bridge_tables[pair_key] = build_industry_bridge_table(
                    a_id,
                    editions_for_component[a_id],
                    b_id,
                    editions_for_component[b_id],
                )

    # Task A2: patch the current-vs-2016-based bridge tables with the real
    # empirical evidence from scripts/validate_oie_overlap.py, if it has been
    # run. overlap_validated=True whenever that script actually computed
    # metrics for the pair (Approved/Conditional/Rejected all count as
    # "validated" — a Rejected pair was still empirically checked, just
    # failed); bridge_approved=True only for pairs whose status is Approved.
    # Never inferred from composition/classification alone (task_a1_report.md
    # explicit restriction).
    overlap_evidence_path = PROJECT_ROOT / "docs" / "oie_overlap_validation_output.json"
    if overlap_evidence_path.is_file():
        overlap_output = json.loads(overlap_evidence_path.read_text(encoding="utf-8"))
        evidence_by_industry_component = {
            (r["industry_id"], r["component"]): r for r in overlap_output["results"]
        }
        for component in ("MPI", "CapU"):
            pair_key = f"{component}__current__vs__2559_2016"
            table = bridge_tables.get(pair_key)
            if table is None:
                continue
            for industry_id, entry in table.items():
                evidence = evidence_by_industry_component.get((industry_id, component))
                if evidence is None:
                    continue  # e.g. IND-03, excluded from Task A2's candidate set
                status = evidence["approval_status"]
                entry["overlap_validated"] = status in ("Approved", "Conditional", "Rejected")
                entry["bridge_approved"] = status == "Approved"
                entry["overlap_validation_status"] = status
                entry["overlap_validation_reasons"] = evidence["reasons"]
                entry["overlap_validation_bridge_version"] = evidence["bridge_version"]

    output = {
        "edition_component_audits": {k: asdict(v) for k, v in audits.items()},
        "pairwise_division_comparisons": pairwise,
        "industry_bridge_tables": bridge_tables,
    }
    out_path = PROJECT_ROOT / "docs" / "task_a1_history_extension_output.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Edition/component summary ===")
    for key, a in audits.items():
        print(
            f"{key}: label={a.classification_label} divisions={len(a.divisions_found)} "
            f"months={a.month_count} ({a.earliest_month}..{a.latest_month}) "
            f"chronological={a.is_chronological} dup_months={a.has_duplicate_months} "
            f"gaps={len(a.gap_months)} weight_sum={a.weight_sum} "
            f"dup_divisions={a.duplicate_divisions or 'none'}"
        )

    print("\n=== Pairwise division intersections (component-specific) ===")
    for name, cmp in pairwise.items():
        print(
            f"{name}: intersection_count={cmp['intersection_count']} "
            f"only_in_a={cmp['only_in_a']} only_in_b={cmp['only_in_b']}"
        )

    print("\n=== Industry bridge status, per edition pair (4-stage) ===")
    for pair_key, table in bridge_tables.items():
        consistent = [i for i, v in table.items() if v["composition_consistent"]]
        inconsistent = [i for i, v in table.items() if not v["composition_consistent"]]
        sample = next(iter(table.values()))
        print(
            f"{pair_key}: classification_compatible={sample['classification_compatible']} "
            f"| composition_consistent={len(consistent)}/12 {sorted(consistent)} "
            f"| NOT consistent={len(inconsistent)}/12 {sorted(inconsistent)}"
        )
        if any("overlap_validation_status" in v for v in table.values()):
            approved = [i for i, v in table.items() if v.get("bridge_approved")]
            validated_not_approved = [
                i
                for i, v in table.items()
                if v.get("overlap_validated") and not v.get("bridge_approved")
            ]
            print(
                f"    overlap_validated evidence applied (docs/oie_overlap_validation.md): "
                f"bridge_approved={sorted(approved)} "
                f"validated_but_not_approved={sorted(validated_not_approved)}"
            )
        else:
            print(
                "    overlap_validated / bridge_approved: False for all industries in this "
                "structural-only audit — see docs/oie_overlap_validation.md for the "
                "empirically-validated status."
            )
        for industry_id in inconsistent:
            print(f"    {industry_id}: {table[industry_id]['reason_if_blocked']}")

    print(f"\nMachine-readable output written to {out_path.relative_to(PROJECT_ROOT)}")
    if overlap_evidence_path.is_file():
        print(
            "\nThis script performs no level-linking or growth-rate-linking itself. "
            "The current-vs-2016-based bridge tables above were patched with real "
            "empirical evidence from scripts/validate_oie_overlap.py "
            f"({overlap_evidence_path.relative_to(PROJECT_ROOT)}). All ISIC-involving "
            "pairs remain overlap_validated=False / bridge_approved=False — they were "
            "never in that script's scope."
        )
    else:
        print(
            "\nNo level-linking or growth-rate-linking was performed by THIS script. "
            "overlap_validated and bridge_approved are always False here by design — "
            "run scripts/validate_oie_overlap.py first, then re-run this script, to "
            "populate them for the current-vs-2016-based pairs."
        )


if __name__ == "__main__":
    main()
