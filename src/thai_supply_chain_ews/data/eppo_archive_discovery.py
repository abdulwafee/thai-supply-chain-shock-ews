"""Official discovery of the EPPO petroleum price-structure archive (Task C6).

C5 verified the *semantics* of one current workbook. C6 has to establish whether
a reproducible historical archive exists behind it, and the difference between
those two questions is the whole task.

Discovery is classified by **mechanism**, because provenance is not a boolean.
A URL found in EPPO's own WordPress REST index is evidence; the same URL guessed
from a filename pattern is not. :data:`OFFICIAL_METHODS` lists what counts, and
``pattern_probe`` and ``search_engine_seed_only`` are deliberately excluded from
it — they may seed a search, but an issue discovered only that way is not an
officially discovered issue.

Pagination stops on an **observed** terminal condition — an empty page, repeated
content, or the API's own error response — never on a page count read off the
interface. EPPO's REST API refuses ``page`` beyond the last with HTTP 400, which
is a documented termination and is recorded as such.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

__all__ = [
    "DISCOVERY_METHODS",
    "OFFICIAL_METHODS",
    "REST_MEDIA_ENDPOINT",
    "USER_AGENT",
    "DiscoveryError",
    "DiscoveredDocument",
    "fetch",
    "is_official_discovery",
    "parse_filename_effective_date",
    "walk_rest_media",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REST_MEDIA_ENDPOINT = "https://www.eppo.go.th/wp-json/wp/v2/media"

DISCOVERY_METHODS = (
    "official_current_archive_href",
    "official_current_detail_href",
    "official_wordpress_rest",
    "official_wordpress_sitemap",
    "official_rss_feed",
    "official_legacy_archive_href",
    "official_legacy_item_href",
    "official_attachment_href",
    "search_engine_seed_only",
    "pattern_probe",
)

#: A guessed path and a search-engine hit are NOT official provenance.
OFFICIAL_METHODS = tuple(m for m in DISCOVERY_METHODS if m.startswith("official_"))

_FILENAME_DATE = re.compile(r"pt-price-st-(\d{4})-(\d{1,2})-(\d{1,2})", re.IGNORECASE)


class DiscoveryError(RuntimeError):
    """A discovery mechanism was used in a way its evidence cannot support."""


def is_official_discovery(method: str) -> bool:
    """Only mechanisms EPPO itself exposes count as discovery."""
    if method not in DISCOVERY_METHODS:
        raise DiscoveryError(f"unknown discovery method {method!r}")
    return method in OFFICIAL_METHODS


def fetch(url: str, timeout: int = 90, method: str = "GET"):
    """Fetch a URL, returning ``(body, status, headers)``.

    HEAD is blocked across this host while GET is served, so a 403 from HEAD
    says nothing about whether the resource exists. Callers use GET.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "th,en;q=0.8"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return None, error.code, dict(error.headers or {})
    except Exception as error:                                    # noqa: BLE001
        return None, type(error).__name__, {}


def parse_filename_effective_date(filename: str):
    """``pt-price-st-YYYY-M-D.xlsx`` -> ``YYYY-MM-DD``.

    This is the date the SOURCE encodes in the filename. It is a claim to be
    validated against the document's own internal date, never accepted as
    identity on its own.
    """
    found = _FILENAME_DATE.search(filename or "")
    if not found:
        return None
    year, month, day = (int(found.group(i)) for i in (1, 2, 3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


@dataclass
class DiscoveredDocument:
    media_id: int
    filename: str
    attachment_url: str
    discovery_method: str
    effective_date_filename: str = None
    media_upload_date: str = None
    media_upload_date_gmt: str = None
    media_modified_gmt: str = None
    mime_type: str = None
    detail_page_url: str = None
    rejection_reason: str = None
    candidate_links: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def walk_rest_media(
    search: str = "pt-price-st",
    per_page: int = 100,
    max_pages: int = 200,
    fetch_fn=fetch,
) -> tuple:
    """Page the WordPress REST media index to a bounded terminal condition.

    Returns ``(documents, termination)``. The termination string records WHICH
    bounded condition ended the walk, so a truncated crawl can never be
    mistaken for a complete one.
    """
    fields = "id,date,date_gmt,modified,modified_gmt,source_url,title,mime_type"
    documents, seen, page = [], set(), 1
    termination = f"max_pages_reached_{max_pages}"

    while page <= max_pages:
        query = urllib.parse.urlencode({
            "search": search, "per_page": per_page, "page": page,
            "_fields": fields, "orderby": "date", "order": "desc",
        })
        body, status, _ = fetch_fn(f"{REST_MEDIA_ENDPOINT}?{query}")

        if status == 400:
            # WordPress answers a page beyond the last with 400; a documented
            # API termination, not a failure.
            termination = f"api_termination_400_at_page_{page}"
            break
        if body is None or status != 200:
            termination = f"http_{status}_at_page_{page}"
            break

        try:
            batch = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            termination = f"unparseable_response_at_page_{page}: {type(error).__name__}"
            break

        if not batch:
            termination = f"empty_page_at_{page}"
            break

        fresh = [item for item in batch if item.get("id") not in seen]
        if not fresh:
            termination = f"repeated_content_at_page_{page}"
            break

        for item in fresh:
            seen.add(item["id"])
            url = str(item.get("source_url") or "")
            filename = url.rsplit("/", 1)[-1]
            documents.append(
                DiscoveredDocument(
                    media_id=item["id"],
                    filename=filename,
                    attachment_url=url,
                    discovery_method="official_wordpress_rest",
                    effective_date_filename=parse_filename_effective_date(filename),
                    media_upload_date=item.get("date"),
                    media_upload_date_gmt=item.get("date_gmt"),
                    media_modified_gmt=item.get("modified_gmt"),
                    mime_type=item.get("mime_type"),
                )
            )
        page += 1

    return documents, termination


def rank_attachment_candidates(candidates, item_date: str) -> list:
    """Rank a detail page's attachments by verified relationship to the item.

    Encounter order is meaningless — C1.5-R2 was caused by taking the first
    matching link. A candidate whose filename date matches the item's date
    outranks one that merely happens to be a spreadsheet.
    """
    ranked = []
    for url in candidates:
        filename = str(url).rsplit("/", 1)[-1]
        parsed = parse_filename_effective_date(filename)
        if parsed and item_date and parsed == item_date:
            score, reason = 0, "filename_date_matches_item_date"
        elif parsed:
            score, reason = 1, "filename_date_present_but_differs_from_item_date"
        elif filename.lower().endswith((".xls", ".xlsx")):
            score, reason = 2, "spreadsheet_without_parseable_date"
        else:
            score, reason = 3, "not_a_spreadsheet"
        ranked.append({
            "url": url, "filename": filename, "filename_date": parsed,
            "rank_score": score, "rank_reason": reason,
        })
    ranked.sort(key=lambda entry: (entry["rank_score"], entry["filename"]))
    return ranked
