"""Monthly OIE MPI release inventory and publication-timing evidence (Task D2).

What this module answers: *when did reference month t first become public?*

The naive answer is the timestamp the archive listing shows. That answer is
wrong for a quarter of the archive. The listing timestamp is a content-management
field that moves when a page is edited or migrated, and OIE has migrated this
archive at least twice -- sixteen 2016 entries all carry a single 2017-06-13
stamp, fifteen more share 2023-07-27.

The attached PDF is better evidence, for two independent reasons that can be
cross-checked against each other: its HTTP ``Last-Modified``, and the upload
timestamp encoded in its own filename (``...YYYYMMDDhhmmss.pdf``, Bangkok local
time). When those two agree the date is corroborated by two mechanisms; when the
listing is *later* than a corroborated attachment, the listing is a re-host and
the attachment wins.

None of these is a stated publication date. They are supporting metadata, and
this module labels every month with which kind of evidence it actually has --
including :data:`NO_TIMING_EVIDENCE` and ``listing_timestamp_only``, which are
distinct states, not degrees of the same one. A month with no attachment is not
a month with an implausible date.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from .oie_mpi_discovery import fetch

__all__ = [
    "ARCHIVE_BASE_URL",
    "DETAIL_BASE_URL",
    "NO_TIMING_EVIDENCE",
    "THAI_MONTH_NAMES",
    "ReleaseRecord",
    "build_release_inventory",
    "classify_timing_evidence",
    "detect_migration_batches",
    "month_end",
    "parse_filename_timestamp",
    "parse_listing_timestamp",
    "parse_reference_month",
    "walk_archive",
]

ARCHIVE_BASE_URL = "https://i.index.oie.go.th/List_industrial.aspx"
DETAIL_BASE_URL = "https://i.index.oie.go.th/Read_industrial.aspx"
ATTACHMENT_BASE_URL = "https://i.index.oie.go.th/attachment/"

NO_TIMING_EVIDENCE = "no_timing_evidence"

# Full Thai month names as they appear in archive entry titles.
#
# July appears in TWO spellings in the live archive: the standard กรกฎาคม (ฎ)
# and the variant กรกฏาคม (ฏ). Five of 127 entries use the variant. Accepting
# only the standard spelling silently drops those five months and would have
# been reported as a coverage gap that does not exist.
THAI_MONTH_NAMES = {
    "มกราคม": 1,
    "กุมภาพันธ์": 2,
    "มีนาคม": 3,
    "เมษายน": 4,
    "พฤษภาคม": 5,
    "มิถุนายน": 6,
    "กรกฎาคม": 7,
    "กรกฏาคม": 7,
    "สิงหาคม": 8,
    "กันยายน": 9,
    "ตุลาคม": 10,
    "พฤศจิกายน": 11,
    "ธันวาคม": 12,
}

_BUDDHIST_ERA_OFFSET = 543
_ID_PATTERN = re.compile(r"idContent=(\d+)")
_TITLE_PATTERN = re.compile(r"(ภาพรวมดัชนี[^<]{0,80})")
_STAMP_PATTERN = re.compile(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M)")
_ATTACHMENT_PATTERN = re.compile(r"attachment/([^\"'\s<>]+\.pdf)", re.IGNORECASE)
_FILENAME_STAMP_PATTERN = re.compile(r"(\d{14})\.pdf$")


def parse_reference_month(title):
    """Buddhist-Era month title to ``YYYY-MM``. Tolerates the July variant."""
    if not title:
        return None
    for name, number in THAI_MONTH_NAMES.items():
        if name in title:
            year = re.search(r"(25\d\d)", title)
            if year:
                return f"{int(year.group(1)) - _BUDDHIST_ERA_OFFSET:04d}-{number:02d}"
    return None


def month_end(reference_month):
    year, month = int(reference_month[:4]), int(reference_month[5:7])
    last = calendar.monthrange(year, month)[1]
    return datetime(year, month, last, 23, 59, 59, tzinfo=UTC)


def parse_listing_timestamp(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y %I:%M:%S %p").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None


def parse_filename_timestamp(filename, offset_hours=7):
    """Upload stamp encoded in the attachment filename, converted to UTC."""
    if not filename:
        return None
    found = _FILENAME_STAMP_PATTERN.search(filename)
    if not found:
        return None
    try:
        local = datetime.strptime(found.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return local.replace(tzinfo=UTC) - timedelta(hours=offset_hours)


@dataclass
class ReleaseRecord:
    reference_month: str = None
    id_content: str = None
    title: str = None
    detail_url: str = None
    attachment_filename: str = None
    attachment_url: str = None
    attachment_last_modified_utc: str = None
    attachment_filename_timestamp_utc: str = None
    attachment_content_length: int = None
    listing_timestamp_utc: str = None
    listing_batch_size: int = 1
    timestamps_agree: bool = None
    first_publication_estimate_utc: str = None
    publication_lag_days: int = None
    timing_evidence_class: str = NO_TIMING_EVIDENCE
    first_publication_is_credible: bool = False
    evidence_note: str = None

    def to_dict(self):
        return asdict(self)


def walk_archive(config, fetch_fn=fetch):
    """Page through the archive until an OBSERVED empty or repeated page."""
    pagination = config["archive_pagination"]
    parameter = pagination["page_parameter"]
    rows, digests, page, stop_reason = [], {}, 1, "max_pages_reached"
    while page <= pagination["max_pages"]:
        body, _, _ = fetch_fn(f"{ARCHIVE_BASE_URL}?{parameter}={page}")
        html = body.decode("utf-8", "replace") if body else ""
        identifiers = _ID_PATTERN.findall(html)
        if not identifiers and pagination.get("stop_on_empty_page", True):
            stop_reason = f"empty_page_at_{page}"
            break
        digest = hash(html)
        if pagination.get("stop_on_repeated_page_digest", True) and digest in digests:
            stop_reason = f"repeated_page_{page}_matches_{digests[digest]}"
            break
        digests[digest] = page

        titles = _TITLE_PATTERN.findall(html)
        stamps = _STAMP_PATTERN.findall(html)
        unique = []
        for identifier in identifiers:
            if identifier not in unique:
                unique.append(identifier)
        for position, identifier in enumerate(unique):
            rows.append(
                {
                    "id_content": identifier,
                    "title": titles[position].strip() if position < len(titles) else None,
                    "listing_timestamp_raw": stamps[position] if position < len(stamps) else None,
                }
            )
        page += 1
    return rows, stop_reason


def detect_migration_batches(rows, minimum_entries):
    """Listing dates shared by enough entries to indicate a bulk migration."""
    counts = {}
    for row in rows:
        parsed = parse_listing_timestamp(row.get("listing_timestamp_raw"))
        if parsed:
            counts[parsed.date().isoformat()] = counts.get(parsed.date().isoformat(), 0) + 1
    return {day: n for day, n in counts.items() if n >= minimum_entries}


def classify_timing_evidence(record, config, batches, observed_release_months=()):
    """Assign exactly one timing-evidence class, most specific first."""
    window = config["plausible_first_publication_lag_days"]
    if record.reference_month in set(observed_release_months):
        return "directly_observed_release"

    attachment = record.attachment_last_modified_utc
    listing = record.listing_timestamp_utc
    lag = record.publication_lag_days
    implausible = lag is None or not (window["min"] <= lag <= window["max"])

    listing_day = listing[:10] if listing else None
    in_batch = listing_day in batches if listing_day else False

    if attachment:
        if implausible and in_batch:
            return "migration_batch_contaminated"
        if record.timestamps_agree:
            listing_parsed = parse_listing_timestamp_iso(listing)
            attachment_parsed = parse_listing_timestamp_iso(attachment)
            if (
                listing_parsed
                and attachment_parsed
                and listing_parsed > attachment_parsed + timedelta(days=2)
            ):
                return "rehosted_listing_later_than_attachment"
            return "attachment_corroborated"
        return "attachment_last_modified_only"

    if listing:
        if in_batch and implausible:
            return "migration_batch_contaminated"
        return "listing_timestamp_only"
    return NO_TIMING_EVIDENCE


def parse_listing_timestamp_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_release_inventory(
    rows,
    config,
    detail_fetch_fn=None,
    observed_release_months=(),
):
    """Turn raw archive rows into classified release records.

    ``detail_fetch_fn(id_content)`` returns ``(attachment_filename,
    last_modified_header, content_length)`` -- injected so the audit can run
    from cached crawl output without re-hitting the site.
    """
    offset = config.get("attachment_filename_timezone_offset_hours", 7)
    tolerance = config.get("attachment_timestamp_agreement_seconds", 120)
    batches = detect_migration_batches(rows, config["migration_batch_min_entries"])

    records = []
    for row in rows:
        record = ReleaseRecord(
            reference_month=parse_reference_month(row.get("title")),
            id_content=row.get("id_content"),
            title=row.get("title"),
            detail_url="{}?idContent={}".format(DETAIL_BASE_URL, row.get("id_content")),
        )
        listing = parse_listing_timestamp(row.get("listing_timestamp_raw"))
        if listing:
            record.listing_timestamp_utc = listing.isoformat()
            record.listing_batch_size = batches.get(listing.date().isoformat(), 1)

        if detail_fetch_fn is not None:
            filename, last_modified, content_length = detail_fetch_fn(row.get("id_content"))
            if filename:
                record.attachment_filename = filename
                record.attachment_url = ATTACHMENT_BASE_URL + filename
                record.attachment_content_length = content_length
                stamp = parse_filename_timestamp(filename, offset)
                if stamp:
                    record.attachment_filename_timestamp_utc = stamp.isoformat()
                if last_modified:
                    try:
                        parsed = parsedate_to_datetime(last_modified)
                    except (TypeError, ValueError):
                        parsed = None
                    if parsed:
                        record.attachment_last_modified_utc = parsed.isoformat()
                        if stamp:
                            record.timestamps_agree = (
                                abs((parsed - stamp).total_seconds()) < tolerance
                            )

        best = (
            record.attachment_last_modified_utc
            or record.attachment_filename_timestamp_utc
            or record.listing_timestamp_utc
        )
        if best and record.reference_month:
            parsed_best = parse_listing_timestamp_iso(best)
            if parsed_best:
                record.first_publication_estimate_utc = best
                record.publication_lag_days = (
                    parsed_best - month_end(record.reference_month)
                ).days

        record.timing_evidence_class = classify_timing_evidence(
            record, config, batches, observed_release_months
        )
        record.first_publication_is_credible = record.timing_evidence_class in {
            "directly_observed_release",
            "attachment_corroborated",
            "attachment_last_modified_only",
            "rehosted_listing_later_than_attachment",
        }
        if record.timing_evidence_class == "migration_batch_contaminated":
            record.evidence_note = (
                "Listing timestamp shared across a bulk migration batch and lag "
                "outside the plausible window; no surviving first-publication evidence."
            )
        elif record.timing_evidence_class == "listing_timestamp_only":
            record.evidence_note = (
                "No attachment found for this entry; the listing timestamp is the "
                "only evidence and is uncorroborated."
            )
        records.append(record)
    return records
