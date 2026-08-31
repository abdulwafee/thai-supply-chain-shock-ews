"""Archived Pink Sheet issue discovery and first-release extraction (Task C1.5).

Production implementation. Scripts call this module; extraction logic does not
live in a script.

WHAT AN "ISSUE" IS. The World Bank publishes a monthly Pink Sheet PDF whose
filename carries the ISSUE month (e.g. `CMO-Pink-Sheet-August-2026.pdf`). The
issue's own publication timestamp is read from the PDF's `/CreationDate`
metadata — a date printed into the document by the producer — never from the
time this repository happened to download it. Confusing those two is how a
"point-in-time" dataset silently becomes a latest-vintage one.

WHICH REFERENCE MONTHS AN ISSUE CONTAINS. The price table's last three columns
are monthly; earlier columns are annual and quarterly aggregates. The monthly
column headers are read from the header rows and paired with the year row, so
alignment is verified rather than assumed. An issue published in month M carries
completed reference months through M-1.

FIRST RELEASE means the earliest archived issue that contains a given completed
reference month. A later issue's value for that month is a REVISION, not a first
release, and selecting one would understate revision exposure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

__all__ = [
    "CANDIDATE_PDF_LABELS",
    "IssueParseError",
    "MonthAlignmentError",
    "PinkSheetIssue",
    "SeriesObservation",
    "discover_issue_urls",
    "document_hash",
    "storage_identity",
    "IssueIdentityError",
    "validate_issue_identity",
    "extract_issue_date",
    "first_release_index",
    "month_name_to_number",
    "parse_issue_pdf",
    "select_first_release_issue",
]

try:
    import pypdf
except ImportError as exc:  # pragma: no cover
    raise ImportError("pypdf is required to read archived Pink Sheet issues") from exc

PROJECT_ROOT = Path(__file__).resolve().parents[3]

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

ISSUE_FILENAME = re.compile(r"CMO-Pink-Sheet-([A-Za-z]+)-(\d{4})\.pdf", re.IGNORECASE)
PDF_DATE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")
NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")

# The PDF prints labels differently from the historical workbook. Recording both
# prevents a silent mismatch: the workbook says "Coal, Australian", the PDF says
# "Coal, Australia **".
CANDIDATE_PDF_LABELS = {
    "brent_crude_usd_bbl": "Crude oil, Brent",
    "coal_australia_usd_mt": "Coal, Australia",
    "lng_japan_usd_mmbtu": "Liquefied natural gas, Japan",
    "aluminum_usd_mt": "Aluminum",
    "copper_usd_mt": "Copper",
    "rubber_rss3_usd_kg": "Rubber, RSS3",
    "palm_oil_usd_mt": "Palm oil",
}

# Number of trailing monthly columns in the Pink Sheet price table.
MONTHLY_COLUMN_COUNT = 3


class IssueParseError(ValueError):
    """An archived issue does not match the verified Pink Sheet PDF layout."""


class MonthAlignmentError(IssueParseError):
    """Monthly column headers could not be aligned to unambiguous calendar months.

    Raised rather than falling back to positional guessing — a one-column
    misalignment silently attributes one month's price to another.
    """


def month_name_to_number(name: str) -> int:
    key = str(name).strip().lower().rstrip(".")
    if key in MONTH_NAMES:
        return MONTH_NAMES[key]
    if key[:3] in MONTH_ABBR:
        return MONTH_ABBR[key[:3]]
    raise MonthAlignmentError(f"Unrecognized month name {name!r}")


DISCOVERY_METHODS = (
    "official_detail_main_document",
    "official_related_href",
    "official_family_original_href",
    "official_public_documents_search",
    "pattern_probe_within_discovered_folder",
)

# Precedence, lowest rank wins. `/related/` outranks `/original/` deliberately —
# see the R2 note on _FAMILY_ORIGINAL_HREF below.
_METHOD_RANK = {name: i for i, name in enumerate(DISCOVERY_METHODS)}

# A `/related/` href names one specific issue inside a document family.
_RELATED_HREF = re.compile(
    r"""(?:https://thedocs\.worldbank\.org)?"""
    r"""(/en/doc/[^"'\s]+?/related/CMO-Pink-Sheet-([A-Za-z]+)-(\d{4})\.pdf)"""
)

# An `/original/` href addresses the document family's MAIN document and is
# FILENAME-AGNOSTIC on the server: under a given document hash,
# `/original/CMO-Pink-Sheet-NONSENSE-9999.pdf` returns exactly the same bytes as
# `/original/CMO-Pink-Sheet-June-2025.pdf`. The filename in that path is
# decoration, not identity.
#
# This is the C1.5-R2 defect. The 2025 family page carries BOTH
# `/original/CMO-Pink-Sheet-February-2025.pdf` (which serves the family's main
# document — the January issue) and the correct
# `/related/CMO-Pink-Sheet-February-2025.pdf`. R1 treated the two path segments
# as equivalent, took whichever appeared first, and so filed January's bytes as
# February — then concluded from the checksum clash that no February issue
# existed at all. A pipeline defect became a claim about the world.
#
# `/original/` links are still collected, because on an INDIVIDUAL document
# detail page the family's main document genuinely is the issue being described.
# They are simply outranked, and every candidate must pass identity validation
# before it is accepted.
_FAMILY_ORIGINAL_HREF = re.compile(
    r"""(?:https://thedocs\.worldbank\.org)?"""
    r"""(/en/doc/[^"'\s]+?/original/CMO-Pink-Sheet-([A-Za-z]+)-(\d{4})\.pdf)"""
)

# MAIN DOCUMENT links on an individual detail page squash the filename.
_MAIN_DOCUMENT_HREF = re.compile(
    r"""href=['"]([^'"]*?/en/doc/[^'"]+?/original/CMOPinkSheet([A-Za-z]+)(\d{4})\.pdf)['"]"""
)

_DOC_HASH = re.compile(r"/en/doc/([^/]+)/")


def document_hash(url: str) -> str | None:
    """The opaque per-release document hash embedded in a thedocs URL."""
    match = _DOC_HASH.search(url)
    return match.group(1) if match else None


def storage_identity(url: str, filename: str) -> str:
    """Collision-safe local identity: document hash + filename.

    Different World Bank document families reuse the same basename, so a
    basename-only filename (or cache key) lets one family's file overwrite or
    satisfy a lookup for another's. That is precisely how the February 2025
    request was served January 2025 bytes without anything noticing.
    """
    prefix = document_hash(url) or "nohash"
    return f"{prefix}__{filename}"


def _absolute(href: str) -> str:
    return href if href.startswith("http") else "https://thedocs.worldbank.org" + href


def discover_issue_urls(html: str, source_page: str | None = None) -> list[dict]:
    """Extract Pink Sheet issue URLs from official page HTML.

    Returns one record per issue month, carrying EVERY candidate URL found for
    it (ranked, best first) rather than only the winner — so a candidate that
    fails identity validation can be replaced by the next one instead of the
    issue being written off.

    Discovery only: no document hash is ever constructed or guessed.
    """
    candidates: dict[str, list[dict]] = {}

    def record(issue_month: date, url: str, method: str, anchor_text: str | None = None) -> None:
        key = issue_month.isoformat()
        entry = {
            "url": url,
            "discovery_method": method,
            "document_hash": document_hash(url),
            "filename": url.rsplit("/", 1)[-1],
            "anchor_text": anchor_text,
            "source_page": source_page,
        }
        bucket = candidates.setdefault(key, [])
        if any(c["url"] == url for c in bucket):
            return
        bucket.append(entry)

    for pattern, method in (
        (_RELATED_HREF, "official_related_href"),
        (_FAMILY_ORIGINAL_HREF, "official_family_original_href"),
    ):
        for path, month_name, year in pattern.findall(html):
            try:
                issue_month = date(int(year), month_name_to_number(month_name), 1)
            except MonthAlignmentError:
                continue
            record(issue_month, _absolute(path), method)

    for href, month_name, year in _MAIN_DOCUMENT_HREF.findall(html):
        try:
            issue_month = date(int(year), month_name_to_number(month_name), 1)
        except MonthAlignmentError:
            continue
        record(issue_month, _absolute(href), "official_detail_main_document")

    out: list[dict] = []
    for key in sorted(candidates):
        ranked = sorted(
            candidates[key], key=lambda c: _METHOD_RANK[c["discovery_method"]]
        )
        best = ranked[0]
        month = date.fromisoformat(key)
        out.append(
            {
                "issue_name": f"CMO-Pink-Sheet-{month.strftime('%B')}-{month.year}",
                "issue_month": key,
                "url": best["url"],
                "filename": best["filename"],
                "discovery_method": best["discovery_method"],
                "document_hash": best["document_hash"],
                "source_page": source_page,
                "candidates": ranked,
            }
        )
    return out


class IssueIdentityError(ValueError):
    """A downloaded PDF is not the issue it was requested as.

    Raised rather than accepted, because silently filing one issue's bytes under
    another issue's name corrupts every downstream timing and revision figure.
    """


def validate_issue_identity(issue, expected_issue_month: str) -> tuple[bool, list[str]]:
    """Confirm a parsed PDF really is the expected issue.

    Two independent checks, both from the document's own contents:
      * the internal creation date falls inside the expected issue month;
      * the newest monthly column is the month immediately before it.
    """
    problems: list[str] = []
    expected = date.fromisoformat(expected_issue_month)

    if issue.issue_date is None:
        problems.append("PDF carries no internal creation date")
    else:
        actual = date.fromisoformat(issue.issue_date)
        if (actual.year, actual.month) != (expected.year, expected.month):
            problems.append(
                f"internal issue date {issue.issue_date} is not inside expected issue "
                f"month {expected_issue_month}"
            )

    total = expected.year * 12 + (expected.month - 1) - 1
    expected_reference = date(total // 12, total % 12 + 1, 1).isoformat()
    if issue.latest_reference_month != expected_reference:
        problems.append(
            f"newest monthly column is {issue.latest_reference_month}, expected "
            f"{expected_reference}"
        )
    return (not problems), problems


def extract_issue_date(reader) -> tuple[date | None, str | None]:
    """Read the issue's own publication date from PDF metadata.

    Returns (date, raw_string). Never falls back to the download time — an
    absent date is reported as None so the caller must handle it explicitly.
    """
    metadata = reader.metadata or {}
    raw = metadata.get("/CreationDate")
    if not raw:
        return None, None
    match = PDF_DATE.match(str(raw))
    if not match:
        return None, str(raw)
    year, month, day = (int(g) for g in match.groups())
    return date(year, month, day), str(raw)


# --- footnote and estimate semantics (C1.5-R3) --------------------------------
# CORRECTION. C1.5 read the table token "a/" as an estimate marker. It is not.
# The Pink Sheet's own footnote block defines the single-letter tokens as INDEX
# MEMBERSHIP, and index membership says nothing about whether a number is
# estimated. Brent carries "a/" in all 65 issues and is never described as an
# estimate anywhere in the document.
#
# Estimate status comes from a SEPARATE Description statement, and is derived
# only where that statement is actually present in the issue being parsed.
ESTIMATE_RULE_VERSION = "pink_sheet_description_rule_v1"

FOOTNOTE_MEANINGS: dict[str, str] = {
    "a/": "included_in_the_energy_index",
    "b/": "included_in_the_non_energy_index",
    "c/": "included_in_the_precious_metals_index",
    "d/": "index_definition_footnote",
}

# Estimate-status vocabulary. `false` is deliberately absent: a marker we could
# not parse is `unknown`, never a claim that the value is final.
ESTIMATE_STATUSES = (
    "source_documented_estimate",
    "not_covered_by_current_estimate_rule",
    "not_documented_as_estimate",
    "unknown",
)

_FOOTNOTE_TOKEN = re.compile(r"(?<![A-Za-z0-9/])([a-d])/")

# "Liquefied natural gas (Japan), LNG, import price, cif; recent two months'
# averages are estimates." Present in all 65 archived issues; matched rather
# than assumed, so an issue that drops it yields `unknown` instead of a guess.
_LNG_ESTIMATE_NOTE = re.compile(
    r"Liquefied natural gas[^.]*?recent\s+two\s+months.{0,3}\s*averages\s+are\s+estimates\.",
    re.IGNORECASE | re.DOTALL,
)
# How many of the newest displayed months the rule covers.
_LNG_ESTIMATE_MONTHS = 2

# Series whose estimate status is governed by a documented Description rule.
ESTIMATE_RULE_SERIES = {
    "lng_japan_usd_mmbtu": {
        "pattern": _LNG_ESTIMATE_NOTE,
        "months_covered": _LNG_ESTIMATE_MONTHS,
        "evidence_type": "description_note_two_most_recent_months",
    },
}


def footnote_meaning(marker: str) -> str:
    """Map a raw footnote token to its DOCUMENTED meaning, and nothing else."""
    return FOOTNOTE_MEANINGS.get(marker, "unknown_footnote_marker")


def extract_footnote_markers(remainder: str) -> str:
    """Return the raw footnote token(s) on a series row, exactly as displayed.

    Preserved verbatim and ';'-joined. No token is translated into an estimate
    claim here or anywhere downstream.
    """
    return ";".join(f"{token}/" for token in _FOOTNOTE_TOKEN.findall(remainder))


def find_estimate_rule_evidence(text: str, series_id: str) -> dict | None:
    """Locate the Description statement that governs a series' estimate status.

    Returns None when the issue does not carry it — which produces `unknown`,
    not `false`. Absence of parsed evidence is not evidence of finality.
    """
    rule = ESTIMATE_RULE_SERIES.get(series_id)
    if rule is None:
        return None
    match = rule["pattern"].search(text)
    if match is None:
        return None
    return {
        "evidence_type": rule["evidence_type"],
        "evidence_text": " ".join(match.group(0).split()),
        "months_covered": rule["months_covered"],
    }


def classify_estimate_status(
    series_id: str,
    reference_month: str,
    ordered_months: list[str],
    evidence: dict | None,
) -> tuple[str, str, str]:
    """Derive (status, evidence_type, evidence_text) for one observation.

    Position is measured against the issue's own ORDERED monthly columns, so a
    misordered or short header cannot silently shift which months the rule
    covers.
    """
    if series_id not in ESTIMATE_RULE_SERIES:
        # No documented rule for this series. That is not the same as knowing
        # the value is final, and it is certainly not derivable from "a/".
        return "not_documented_as_estimate", "none", ""

    if evidence is None:
        return (
            "unknown",
            "description_note_absent",
            "",
        )

    ordered = sorted(ordered_months)
    if reference_month not in ordered:
        return "unknown", "reference_month_not_in_issue_columns", ""

    # 0 = newest displayed month, 1 = next newest, ...
    position_from_newest = len(ordered) - 1 - ordered.index(reference_month)
    if position_from_newest < evidence["months_covered"]:
        status = "source_documented_estimate"
    else:
        status = "not_covered_by_current_estimate_rule"
    return status, evidence["evidence_type"], evidence["evidence_text"]


@dataclass(frozen=True)
class SeriesObservation:
    series_id: str
    pdf_label: str
    unit: str
    reference_month: str
    displayed_value: float
    displayed_text: str
    decimal_places: int
    # Raw table token, preserved exactly as displayed ("a/", "b/", ...). It
    # denotes INDEX MEMBERSHIP only.
    source_footnote_marker: str
    source_footnote_meaning: str
    # Estimate status, derived from independent Description evidence.
    estimate_status: str
    estimate_evidence_type: str
    estimate_evidence_text: str
    estimate_rule_version: str
    estimate_evidence_url: str
    definition_marker: bool


@dataclass
class PinkSheetIssue:
    issue_name: str
    issue_month: str
    issue_date: str | None
    issue_date_raw: str | None
    url: str
    file_path: str
    sha256: str
    downloaded_at_utc: str
    monthly_reference_months: list[str]
    latest_reference_month: str | None
    observations: dict[str, list[SeriesObservation]] = field(default_factory=dict)
    completeness: str = "complete"
    notes: list[str] = field(default_factory=list)

    def observation(self, series_id: str, reference_month: str) -> SeriesObservation | None:
        for row in self.observations.get(series_id, []):
            if row.reference_month == reference_month:
                return row
        return None


def _parse_monthly_headers(text: str, issue_month: date) -> list[str]:
    """Align the trailing monthly columns to calendar months.

    The header block looks like:
        ... Jan-Mar Apr-Jun May June July
        Unit 2023 2024 2025 ... 2026 2026 2026
    so the last MONTHLY_COLUMN_COUNT tokens of the period row are month names
    and the last tokens of the year row are their years.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    period_row = year_row = None
    # The year row is identified structurally, not by a fixed prefix: issues
    # before ~2024 begin it with "Commodity Unit ..." while later ones begin
    # with "Unit ...". Requiring one literal prefix silently failed to parse
    # 31 of 65 archived issues on the first C1.5-R1 pass.
    for i, line in enumerate(lines[:12]):
        if i == 0:
            continue
        if "Unit" not in line.split():
            continue
        if len(re.findall(r"(?:19|20)[0-9]{2}", line)) >= 4:
            period_row, year_row = lines[i - 1], line
            break
    if period_row is None or year_row is None:
        raise MonthAlignmentError(
            "Could not locate the period/year header rows in the issue PDF."
        )

    period_tokens = period_row.split()
    year_tokens = [t for t in year_row.split() if re.fullmatch(r"\d{4}", t)]
    month_tokens = period_tokens[-MONTHLY_COLUMN_COUNT:]
    year_values = year_tokens[-MONTHLY_COLUMN_COUNT:]
    if len(month_tokens) != MONTHLY_COLUMN_COUNT or len(year_values) != MONTHLY_COLUMN_COUNT:
        raise MonthAlignmentError(
            f"Expected {MONTHLY_COLUMN_COUNT} trailing monthly columns; found "
            f"{month_tokens} / {year_values}."
        )

    months: list[str] = []
    for token, year in zip(month_tokens, year_values, strict=True):
        if "-" in token:
            raise MonthAlignmentError(
                f"Trailing column {token!r} is an aggregate, not a single month; "
                "the table layout changed."
            )
        months.append(date(int(year), month_name_to_number(token), 1).isoformat())

    if months != sorted(months):
        raise MonthAlignmentError(f"Monthly columns are not chronological: {months}")

    # An issue can only report months already completed before it was published.
    latest = date.fromisoformat(months[-1])
    if (latest.year, latest.month) >= (issue_month.year, issue_month.month):
        raise MonthAlignmentError(
            f"Issue {issue_month:%Y-%m} claims a reference month {latest:%Y-%m} that is not "
            "yet complete at publication — alignment is wrong or the issue is mislabelled."
        )
    return months


def _parse_series_row(
    line: str, label: str
) -> tuple[list[float | None], list[str], str, bool, bool]:
    """Return (values, texts, unit, footnote_markers, definition_marker).

    CRITICAL: the row is tokenised into a sequence of NUMBER-or-MISSING cells,
    not just numbers. Older issues print an ellipsis for months a series has not
    yet reported — e.g. Coal, Australia in the 2022 issues reads
    ``... 183.9 197.0 … … … …``. Taking "the last three numbers" there silently
    reaches back into the QUARTERLY columns and fabricates a first-release value
    that was never published; that bug produced an apparent +118% coal revision
    which was pure artifact. Missing cells stay missing.
    """
    remainder = line[len(label):].strip()
    definition_marker = remainder.startswith("**")
    unit_match = re.match(r"\**\s*([\$A-Za-z0-9/=%\.]+)", remainder)
    unit = unit_match.group(1) if unit_match else ""
    # Strip the leading label/unit block so only the footnote region and data
    # cells remain.
    body = remainder
    if unit_match:
        body = remainder[unit_match.end():]

    # C1.5-R3: capture the RAW footnote token(s) from the region BEFORE the
    # first data cell — the footnote block itself — rather than a fixed-width
    # window, so a longer unit or a second marker cannot fall outside it.
    # Previously this set an `estimate_marker` boolean from "a/", which means
    # "included in the energy index"; that misreading made every Brent
    # observation look estimated.
    first_cell = re.search(r"(-?\d[\d,]*\.?\d*)|(…|\.\.\.)", body)
    footnote_region = body[: first_cell.start()] if first_cell else body
    footnote_markers = extract_footnote_markers(footnote_region)

    body = re.sub(r"^\s*(?:[a-z]/\s*)+", "", body)

    cells: list[str | None] = []
    for token in re.finditer(r"(-?\d[\d,]*\.?\d*)|(\u2026|\.\.\.)", body):
        cells.append(token.group(1) if token.group(1) else None)

    if len(cells) < MONTHLY_COLUMN_COUNT:
        raise IssueParseError(
            f"Row {label!r} has fewer than {MONTHLY_COLUMN_COUNT} trailing data cells."
        )
    tail = cells[-MONTHLY_COLUMN_COUNT:]
    values: list[float | None] = [
        float(t.replace(",", "")) if t is not None else None for t in tail
    ]
    texts = [t if t is not None else "" for t in tail]
    return values, texts, unit, footnote_markers, definition_marker


def _decimal_places(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def parse_issue_pdf(
    path: Path,
    issue_name: str,
    issue_month: str,
    url: str,
    sha256: str,
    downloaded_at_utc: str,
    candidates: dict[str, str] | None = None,
) -> PinkSheetIssue:
    """Parse one archived issue into aligned first-release observations."""
    candidates = candidates or CANDIDATE_PDF_LABELS
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    reader = pypdf.PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    issue_date, issue_date_raw = extract_issue_date(reader)

    issue_month_date = date.fromisoformat(issue_month)
    months = _parse_monthly_headers(text, issue_month_date)

    notes: list[str] = []
    if issue_date is None:
        notes.append("PDF carries no CreationDate; publication date unknown, not inferred.")
    elif (issue_date.year, issue_date.month) != (issue_month_date.year, issue_month_date.month):
        notes.append(
            f"PDF CreationDate {issue_date.isoformat()} is outside its own issue month "
            f"{issue_month} — recorded as-is, not corrected."
        )

    observations: dict[str, list[SeriesObservation]] = {}
    estimate_rules_found: dict[str, dict] = {}
    missing: list[str] = []
    for series_id, label in candidates.items():
        row_line = None
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(label):
                row_line = stripped
                break
        if row_line is None:
            missing.append(series_id)
            continue
        values, texts, unit, markers, definition = _parse_series_row(row_line, label)
        evidence = find_estimate_rule_evidence(text, series_id)
        if evidence is not None:
            estimate_rules_found[series_id] = evidence
        observations[series_id] = [
            SeriesObservation(
                series_id=series_id,
                pdf_label=label,
                unit=unit,
                reference_month=month,
                displayed_value=value,
                displayed_text=text_value,
                decimal_places=_decimal_places(text_value),
                source_footnote_marker=markers,
                source_footnote_meaning=";".join(
                    footnote_meaning(m) for m in markers.split(";") if m
                ),
                **dict(
                    zip(
                        ("estimate_status", "estimate_evidence_type",
                         "estimate_evidence_text"),
                        classify_estimate_status(series_id, month, months, evidence),
                        strict=True,
                    )
                ),
                estimate_rule_version=ESTIMATE_RULE_VERSION,
                estimate_evidence_url=url,
                definition_marker=definition,
            )
            # A cell the issue did not publish produces NO observation. It is
            # never back-filled from an adjacent column.
            for month, value, text_value in zip(months, values, texts, strict=True)
            if value is not None
        ]
    if missing:
        notes.append(f"Series not found in this issue: {sorted(missing)}")
    for series_id in ESTIMATE_RULE_SERIES:
        if series_id in observations and series_id not in estimate_rules_found:
            notes.append(
                f"{series_id}: the documented estimate note was not found in this "
                "issue; its observations are recorded as `unknown` rather than "
                "assumed final."
            )

    return PinkSheetIssue(
        issue_name=issue_name,
        issue_month=issue_month,
        issue_date=issue_date.isoformat() if issue_date else None,
        issue_date_raw=issue_date_raw,
        url=url,
        file_path=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        sha256=sha256,
        downloaded_at_utc=downloaded_at_utc,
        monthly_reference_months=months,
        latest_reference_month=months[-1] if months else None,
        observations=observations,
        completeness="complete" if not missing else "partial",
        notes=notes,
    )


def select_first_release_issue(
    issues: list[PinkSheetIssue], reference_month: str
) -> PinkSheetIssue | None:
    """Earliest archived issue containing `reference_month`.

    Ordered by the issue's own publication date where available, falling back to
    issue month. Picking any later issue would report a revision as a first
    release.
    """
    containing = [i for i in issues if reference_month in i.monthly_reference_months]
    if not containing:
        return None
    return sorted(containing, key=lambda i: (i.issue_date or i.issue_month, i.issue_month))[0]


def first_release_index(issues: list[PinkSheetIssue]) -> dict[str, str]:
    """reference_month -> issue_name of its first archived appearance."""
    index: dict[str, str] = {}
    for month in sorted({m for i in issues for m in i.monthly_reference_months}):
        issue = select_first_release_issue(issues, month)
        if issue:
            index[month] = issue.issue_name
    return index


def parse_pdf_creation_date(raw: str) -> date | None:
    """Public helper for tests: 'D:20260804131056-04'00'' -> date(2026, 8, 4)."""
    match = PDF_DATE.match(str(raw))
    if not match:
        return None
    return date(*(int(g) for g in match.groups()))


def month_end(month: str) -> date:
    """Last calendar day of a first-of-month date string."""
    d = date.fromisoformat(month)
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - (datetime(1, 1, 2) - datetime(1, 1, 1))
