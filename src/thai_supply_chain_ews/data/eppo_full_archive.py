"""Resumable acquisition of the full EPPO price-structure archive (Task C7).

C6 discovered 5,233 official media documents and retrieved 256 of them as an
audit sample. C7 has to retrieve the whole required window, which turns three
things that did not matter at sample scale into hard requirements.

**The denominator is the officially discovered inventory.** Every distinct
document-day found through EPPO's own WordPress REST index is one retrieval
attempt that must be accounted for. A day whose attachment cannot be fetched is
an *unresolved inventory item*, reported as such; it never quietly disappears
from the count, and 1,315 discovered days are never reported as 1,315 validated
days.

**A response is not a document.** Cloudflare sits in front of this host, so an
HTML challenge page can arrive with HTTP 200 and a spreadsheet filename. Magic
bytes are checked *before* anything is written, so an error page is never stored
under an ``.xls`` or ``.xlsx`` name — a later parse would otherwise fail in a way
that looks like a bad workbook rather than a bad request.

**Acquisition must survive interruption.** Progress is checkpointed to the
repository's tracked manifest after every batch, keyed by WordPress media ID, and
a rerun verifies the bytes already on disk by checksum instead of re-fetching
them. A failure late in the run therefore never invalidates or deletes what
earlier requests already proved.

Acquisition timestamps live in the manifest, never in a dataset checksum: when
the bytes are identical, the dataset is identical, whatever hour it was fetched.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .eppo_archive_discovery import USER_AGENT, fetch, parse_filename_effective_date
from .eppo_price_structure import ACCEPTED_MAGIC, detect_magic

__all__ = [
    "MAX_ATTEMPTS",
    "RAW_SOURCE_ID",
    "REQUEST_INTERVAL_SECONDS",
    "RETRIEVAL_STATUSES",
    "RETRY_BACKOFF_SECONDS",
    "THROTTLE_HTTP_STATUSES",
    "USER_AGENT",
    "AcquisitionError",
    "CandidateAttachment",
    "RetrievalRecord",
    "ThrottleDetected",
    "acquire_window",
    "assert_denominator_consistent",
    "checkpoint_by_media_id",
    "classify_response",
    "document_days",
    "load_checkpoint",
    "manifest_path",
    "raw_path_for",
    "records_from_checkpoint",
    "retrieve_candidate",
    "sha256_bytes",
    "summarize",
    "write_checkpoint",
]

#: Raw-file convention: data/raw/<SOURCE_ID>/... plus a tracked JSONL manifest
#: in data/raw/_manifests/, exactly as OIE_MPI and WB_PINKSHEET already do.
RAW_SOURCE_ID = "EPPO_PRICE_STRUCTURE"

#: Documented polite request rate. EPPO is a small public agency behind
#: Cloudflare; roughly three requests a second is well under what an ordinary
#: browsing session generates and is applied to every request including retries.
REQUEST_INTERVAL_SECONDS = 0.35

MAX_ATTEMPTS = 3

#: Bounded backoff. The tuple length caps the wait schedule, so a hostile
#: server cannot stretch the run indefinitely.
RETRY_BACKOFF_SECONDS = (2.0, 6.0)

THROTTLE_HTTP_STATUSES = (403, 408, 429, 503, 509)

RETRIEVAL_STATUSES = (
    "downloaded",
    "cached_checksum_verified",
    "http_error",
    "network_error",
    "throttled",
    "waf_or_html_response",
    "empty_response",
    "unaccepted_format",
)

#: Statuses whose bytes are on disk and usable.
_SUCCESS_STATUSES = ("downloaded", "cached_checksum_verified")

#: Statuses worth another bounded attempt. A 404 is not one of them.
_RETRYABLE_STATUSES = ("network_error", "throttled", "empty_response")


class AcquisitionError(RuntimeError):
    """Acquisition was asked to do something its evidence cannot support."""


class ThrottleDetected(AcquisitionError):
    """The server throttled repeatedly; the run stops rather than manufacture failures.

    Aborting is deliberate. Recording a long tail of "failed" days that were
    only ever refused by a rate limiter would look like archive gaps, and gaps
    are a finding about the source, not about our request pattern.
    """


def assert_denominator_consistent(
    distinct_document_days: int,
    retrieval_attempts: int,
    http_successes: int,
    content_valid_files: int,
) -> None:
    """Raise if a count claims more than the step before it could support.

    The failure this exists to stop is reporting the DISCOVERED day count as
    though it were validated. Discovery says an item exists; only retrieval and
    content validation can say it is usable, and each stage can only shrink.
    """
    if retrieval_attempts < distinct_document_days:
        raise AcquisitionError(
            f"{retrieval_attempts} retrieval attempts cannot cover "
            f"{distinct_document_days} discovered document-days"
        )
    if http_successes > retrieval_attempts:
        raise AcquisitionError(
            f"{http_successes} successes exceed {retrieval_attempts} attempts"
        )
    if content_valid_files > http_successes:
        raise AcquisitionError(
            f"{content_valid_files} content-valid files exceed {http_successes} "
            "successful retrievals; a document cannot validate before it arrives"
        )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CandidateAttachment:
    """One officially discovered media record, before any retrieval."""

    media_id: int
    filename: str
    attachment_url: str
    effective_date_filename: str
    discovery_method: str = "official_wordpress_rest"
    mime_type: str = None
    media_upload_date: str = None
    media_upload_date_gmt: str = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalRecord:
    """What one retrieval attempt actually established."""

    media_id: int
    effective_date_filename: str
    filename: str
    attachment_url: str
    retrieval_status: str
    attempts: int = 0
    http_status: object = None
    content_type: str = None
    http_last_modified: str = None
    content_length: int = None
    bytes: int = None
    sha256: str = None
    magic: str = None
    raw_relative_path: str = None
    downloaded_at_utc: str = None
    rejection_reason: str = None
    discovery_method: str = "official_wordpress_rest"
    mime_type: str = None
    media_upload_date: str = None

    @property
    def succeeded(self) -> bool:
        return self.retrieval_status in _SUCCESS_STATUSES

    def to_dict(self) -> dict:
        return asdict(self)


def document_days(documents, start: str, end: str) -> OrderedDict[str, list]:
    """Group discovered media records into document-days inside ``[start, end]``.

    Ordering is deterministic and never encounter order: days ascend, and the
    candidates within a day ascend by media ID. Which candidate is *used* is
    decided later by content, not by this ordering — see
    :func:`eppo_daily_prices.rank_document_candidates`.
    """
    grouped = defaultdict(list)
    for document in documents:
        date = document.get("effective_date_filename") or parse_filename_effective_date(
            document.get("filename", "")
        )
        if not date or not (start <= date <= end):
            continue
        grouped[date].append(
            CandidateAttachment(
                media_id=int(document["media_id"]),
                filename=document["filename"],
                attachment_url=document["attachment_url"],
                effective_date_filename=date,
                discovery_method=document.get(
                    "discovery_method", "official_wordpress_rest"
                ),
                mime_type=document.get("mime_type"),
                media_upload_date=document.get("media_upload_date"),
                media_upload_date_gmt=document.get("media_upload_date_gmt"),
            )
        )
    ordered = OrderedDict()
    for date in sorted(grouped):
        ordered[date] = sorted(grouped[date], key=lambda c: c.media_id)
    return ordered


def raw_path_for(root: Path, effective_date: str, filename: str) -> Path:
    """``data/raw/EPPO_PRICE_STRUCTURE/<YYYY-MM>/<date>__<filename>``.

    The date prefix keeps the archive item's own date visible on disk while the
    original source filename is preserved verbatim beside it.
    """
    return (
        Path(root)
        / "data"
        / "raw"
        / RAW_SOURCE_ID
        / str(effective_date)[:7]
        / f"{effective_date}__{filename}"
    )


def manifest_path(root: Path) -> Path:
    return Path(root) / "data" / "raw" / "_manifests" / f"{RAW_SOURCE_ID}_manifest.jsonl"


def _header(headers, name: str):
    for key, value in (headers or {}).items():
        if str(key).lower() == name.lower():
            return value
    return None


def classify_response(payload, status, content_type: str = None) -> tuple:
    """Decide what a response *is*, from its bytes rather than its filename.

    Returns ``(retrieval_status, magic, reason)``. An HTML body arriving with
    HTTP 200 and a spreadsheet content type is the Cloudflare challenge case and
    is classified as a WAF response, not as a document.
    """
    if status in THROTTLE_HTTP_STATUSES:
        return "throttled", None, f"server_returned_{status}"
    if payload is None:
        if isinstance(status, int):
            return "http_error", None, f"http_{status}"
        return "network_error", None, f"transport_{status}"
    if not payload:
        return "empty_response", None, "zero_byte_response"

    magic = detect_magic(payload)
    if magic == "html_masquerade" or "text/html" in str(content_type or "").lower():
        return "waf_or_html_response", magic, "html_or_challenge_page_served_as_document"
    if magic not in ACCEPTED_MAGIC.values():
        return "unaccepted_format", magic, f"unaccepted_format_{magic}"
    if status != 200:
        return "http_error", magic, f"http_{status}"
    return "downloaded", magic, None


def retrieve_candidate(
    candidate: CandidateAttachment,
    root: Path,
    fetch_fn=fetch,
    sleep_fn=time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
    request_interval: float = REQUEST_INTERVAL_SECONDS,
    backoff=RETRY_BACKOFF_SECONDS,
    known_record: dict = None,
) -> RetrievalRecord:
    """Retrieve one candidate, resuming from disk when the bytes are already proven.

    ``known_record`` is this media ID's line from the checkpoint manifest. When
    the file exists and still hashes to the recorded digest, no request is made
    at all — that is what makes a rerun cheap and an interrupted run safe to
    restart. The manifest's own response metadata is carried forward rather than
    blanked, so re-running never erases what the server said the first time.
    """
    known_record = known_record or {}
    known_sha256 = known_record.get("sha256")
    path = raw_path_for(root, candidate.effective_date_filename, candidate.filename)
    if known_sha256 and path.is_file():
        payload = path.read_bytes()
        if sha256_bytes(payload) == known_sha256:
            return RetrievalRecord(
                media_id=candidate.media_id,
                effective_date_filename=candidate.effective_date_filename,
                filename=candidate.filename,
                attachment_url=candidate.attachment_url,
                retrieval_status="cached_checksum_verified",
                attempts=0,
                http_status=known_record.get("http_status"),
                content_type=known_record.get("http_content_type"),
                http_last_modified=known_record.get("http_last_modified"),
                content_length=known_record.get("content_length"),
                bytes=len(payload),
                sha256=known_sha256,
                magic=detect_magic(payload),
                raw_relative_path=str(path.relative_to(root)).replace("\\", "/"),
                downloaded_at_utc=known_record.get("retrieved_at"),
                discovery_method=candidate.discovery_method,
                mime_type=candidate.mime_type,
                media_upload_date=candidate.media_upload_date,
            )

    record = RetrievalRecord(
        media_id=candidate.media_id,
        effective_date_filename=candidate.effective_date_filename,
        filename=candidate.filename,
        attachment_url=candidate.attachment_url,
        retrieval_status="network_error",
        discovery_method=candidate.discovery_method,
        mime_type=candidate.mime_type,
        media_upload_date=candidate.media_upload_date,
    )

    for attempt in range(1, max(1, max_attempts) + 1):
        record.attempts = attempt
        if request_interval:
            sleep_fn(request_interval)
        payload, status, headers = fetch_fn(candidate.attachment_url)
        content_type = _header(headers, "Content-Type")
        outcome, magic, reason = classify_response(payload, status, content_type)

        record.http_status = status
        record.content_type = content_type
        record.http_last_modified = _header(headers, "Last-Modified")
        length = _header(headers, "Content-Length")
        record.content_length = int(length) if str(length or "").isdigit() else None
        record.magic = magic
        record.retrieval_status = outcome
        record.rejection_reason = reason

        if outcome == "downloaded":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            record.bytes = len(payload)
            record.sha256 = sha256_bytes(payload)
            record.raw_relative_path = str(path.relative_to(root)).replace("\\", "/")
            record.downloaded_at_utc = _utc_now()
            record.rejection_reason = None
            return record

        # A rejected body is never written under a spreadsheet name; its digest
        # is still recorded so the rejection is reproducible.
        if payload:
            record.bytes = len(payload)
            record.sha256 = sha256_bytes(payload)

        if outcome not in _RETRYABLE_STATUSES or attempt >= max_attempts:
            return record
        if backoff:
            sleep_fn(backoff[min(attempt - 1, len(backoff) - 1)])

    return record


def load_checkpoint(root: Path) -> list:
    path = manifest_path(root)
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def checkpoint_by_media_id(records) -> dict:
    """Index manifest lines by media ID.

    Keying on media ID rather than checksum is deliberate: two different days
    can legitimately share byte-identical bytes, and a checksum-keyed manifest
    would drop one of them.
    """
    index = {}
    for record in records:
        media_id = record.get("extra", {}).get("media_id", record.get("media_id"))
        if media_id is not None:
            index[int(media_id)] = record
    return index


@dataclass
class AcquisitionSummary:
    """Counts that keep the denominator honest. Every field is a distinct state."""

    discovered_media_records: int = 0
    distinct_document_days: int = 0
    document_days_single_candidate: int = 0
    document_days_multiple_candidates: int = 0
    retrieval_attempts: int = 0
    http_successes: int = 0
    cached_checksum_verified: int = 0
    downloaded: int = 0
    failed_retrievals: int = 0
    status_counts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def records_from_checkpoint(days, root: Path) -> list:
    """Rebuild retrieval records from the manifest without making any request.

    This is the offline path and the checksum-verification path at once: a file
    still on disk is re-hashed against its manifest line, and a candidate whose
    earlier attempt failed keeps the status that attempt recorded rather than
    being re-labelled as a fresh failure. Re-labelling would turn three HTTP 404s
    into three "network errors" and misdescribe the archive.
    """
    known = checkpoint_by_media_id(load_checkpoint(root))
    records = []
    for candidates in days.values():
        for candidate in candidates:
            entry = known.get(candidate.media_id)
            if entry is None:
                records.append(RetrievalRecord(
                    media_id=candidate.media_id,
                    effective_date_filename=candidate.effective_date_filename,
                    filename=candidate.filename,
                    attachment_url=candidate.attachment_url,
                    retrieval_status="network_error",
                    rejection_reason="not_in_checkpoint_manifest",
                    discovery_method=candidate.discovery_method,
                    mime_type=candidate.mime_type,
                    media_upload_date=candidate.media_upload_date,
                ))
                continue
            extra = entry.get("extra", {})
            status = extra.get("retrieval_status", "network_error")
            path = raw_path_for(root, candidate.effective_date_filename,
                                candidate.filename)
            digest, size = entry.get("sha256"), extra.get("bytes")
            if status in _SUCCESS_STATUSES:
                if not path.is_file():
                    status = "network_error"
                    reason = "manifest_records_a_file_that_is_no_longer_on_disk"
                else:
                    payload = path.read_bytes()
                    actual = sha256_bytes(payload)
                    if actual != digest:
                        raise AcquisitionError(
                            f"{path.name}: manifest records SHA-256 {digest}, file "
                            f"hashes to {actual}; refusing to ingest bytes that are "
                            "not the bytes that were verified"
                        )
                    status, reason = "cached_checksum_verified", None
                    size = len(payload)
            else:
                reason = extra.get("rejection_reason")
            records.append(RetrievalRecord(
                media_id=candidate.media_id,
                effective_date_filename=candidate.effective_date_filename,
                filename=candidate.filename,
                attachment_url=candidate.attachment_url,
                retrieval_status=status,
                attempts=extra.get("attempts", 0),
                http_status=entry.get("http_status"),
                content_type=entry.get("http_content_type"),
                http_last_modified=entry.get("http_last_modified"),
                content_length=entry.get("content_length"),
                bytes=size,
                sha256=digest,
                magic=extra.get("magic"),
                raw_relative_path=entry.get("file_path"),
                downloaded_at_utc=entry.get("retrieved_at"),
                rejection_reason=reason,
                discovery_method=candidate.discovery_method,
                mime_type=candidate.mime_type,
                media_upload_date=candidate.media_upload_date,
            ))
    return records


def summarize(records, days) -> AcquisitionSummary:
    """Acquisition counts from a record set, however it was produced."""
    counts = {}
    for record in records:
        counts[record.retrieval_status] = counts.get(record.retrieval_status, 0) + 1
    return AcquisitionSummary(
        discovered_media_records=sum(len(v) for v in days.values()),
        distinct_document_days=len(days),
        document_days_single_candidate=sum(1 for v in days.values() if len(v) == 1),
        document_days_multiple_candidates=sum(1 for v in days.values() if len(v) > 1),
        retrieval_attempts=len(records),
        http_successes=sum(1 for r in records if r.succeeded),
        cached_checksum_verified=counts.get("cached_checksum_verified", 0),
        downloaded=counts.get("downloaded", 0),
        failed_retrievals=sum(1 for r in records if not r.succeeded),
        status_counts=dict(sorted(counts.items())),
    )


def _manifest_line(record: RetrievalRecord) -> str:
    payload = {
        "source_id": RAW_SOURCE_ID,
        "file_path": record.raw_relative_path,
        "source_url": record.attachment_url,
        "retrieved_at": record.downloaded_at_utc,
        "sha256": record.sha256,
        "content_length": record.content_length,
        "http_status": record.http_status if isinstance(record.http_status, int) else None,
        "http_content_type": record.content_type,
        "http_last_modified": record.http_last_modified,
        "original_filename": record.filename,
        "source_vintage": record.effective_date_filename,
        "url_discovery_method": record.discovery_method,
        "extra": {
            "media_id": record.media_id,
            "retrieval_status": record.retrieval_status,
            "magic": record.magic,
            "bytes": record.bytes,
            "attempts": record.attempts,
            "rejection_reason": record.rejection_reason,
        },
    }
    payload["extra"] = {k: v for k, v in payload["extra"].items() if v is not None}
    payload = {k: v for k, v in payload.items() if v not in (None, {}, "")}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def write_checkpoint(root: Path, records) -> int:
    """Rewrite the manifest from the full record set, ordered deterministically.

    Rewriting rather than appending keeps the manifest a faithful index of the
    current archive: a rerun that re-verifies cached bytes produces exactly the
    same file, so the manifest never grows on repeat runs.
    """
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: (r.effective_date_filename, r.media_id))
    lines = [_manifest_line(record) for record in ordered]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def acquire_window(
    documents,
    start: str,
    end: str,
    root: Path,
    fetch_fn=fetch,
    sleep_fn=time.sleep,
    checkpoint_every: int = 50,
    max_consecutive_throttles: int = 8,
    progress_fn=None,
    limit: int = 0,
) -> tuple:
    """Retrieve every discovered candidate in the window, resumably.

    Returns ``(records, summary, days)``. Every discovered candidate produces a
    record — success or failure — so the retrieval denominator can be
    reconciled against discovery without inference.
    """
    days = document_days(documents, start, end)
    known = checkpoint_by_media_id(load_checkpoint(root))

    records, consecutive_throttles, processed = [], 0, 0
    for date, candidates in days.items():
        for candidate in candidates:
            record = retrieve_candidate(
                candidate,
                root,
                fetch_fn=fetch_fn,
                sleep_fn=sleep_fn,
                known_record=known.get(candidate.media_id),
            )
            records.append(record)
            processed += 1

            if record.retrieval_status == "throttled":
                consecutive_throttles += 1
                if consecutive_throttles >= max_consecutive_throttles:
                    write_checkpoint(root, records)
                    raise ThrottleDetected(
                        f"{consecutive_throttles} consecutive throttled responses "
                        f"ending at {candidate.attachment_url}. Stopping with "
                        f"{processed} candidates processed; already-verified files "
                        "are retained and the run can resume."
                    )
            else:
                consecutive_throttles = 0

            if checkpoint_every and processed % checkpoint_every == 0:
                write_checkpoint(root, records)
                if progress_fn:
                    progress_fn(processed, sum(len(v) for v in days.values()), date)
            if limit and processed >= limit:
                break
        if limit and processed >= limit:
            break

    write_checkpoint(root, records)
    return records, summarize(records, days), days
