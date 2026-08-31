"""Retrieval manifests for external sources (Task C1).

Generalizes the manifest convention already used for the OIE files: one JSONL
line per acquisition recording where a file came from, when, what the server
said, and what it hashed to. Raw files stay git-ignored; the manifest is tracked,
so provenance survives even though the bytes do not.

Manifest writing is idempotent by checksum: re-running an acquisition that
produced the same bytes does not append a duplicate line. A genuinely new
vintage (different SHA-256) does append, because that is a new fact.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "ManifestEntry",
    "ChecksumMismatchError",
    "append_manifest_entry",
    "manifest_path_for",
    "parse_response_headers",
    "read_manifest",
    "sha256_of_file",
    "utc_now_iso",
    "verify_file_checksum",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
MANIFEST_DIR = RAW_DIR / "_manifests"


class ChecksumMismatchError(RuntimeError):
    """A file on disk does not match the checksum recorded for it."""


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_path_for(source_id: str) -> Path:
    return MANIFEST_DIR / f"{source_id}_manifest.jsonl"


@dataclass
class ManifestEntry:
    source_id: str
    file_path: str
    source_url: str
    retrieved_at: str
    sha256: str
    content_length: int | None = None
    http_status: int | None = None
    http_content_type: str | None = None
    http_last_modified: str | None = None
    original_filename: str | None = None
    source_vintage: str | None = None
    url_discovery_method: str | None = None
    landing_page: str | None = None
    notes: str | None = None
    extra: dict = field(default_factory=dict)

    def to_json_line(self) -> str:
        payload = {k: v for k, v in asdict(self).items() if v not in (None, {}, "")}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_response_headers(path: Path) -> dict:
    """Parse a curl `-D` header dump into the fields the manifest records.

    Only the last response block is used, so a redirect chain reports the
    headers of the response that actually delivered the bytes.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = [b for b in re.split(r"\r?\n\r?\n", text) if b.strip()]
    if not blocks:
        return {}
    last = blocks[-1]
    status = None
    status_match = re.search(r"^HTTP/[\d.]+\s+(\d{3})", last, re.MULTILINE)
    if status_match:
        status = int(status_match.group(1))

    def header(name: str) -> str | None:
        match = re.search(rf"^{name}:\s*(.+?)\s*$", last, re.MULTILINE | re.IGNORECASE)
        return match.group(1) if match else None

    length = header("Content-Length")
    return {
        "http_status": status,
        "http_content_type": header("Content-Type"),
        "http_last_modified": header("Last-Modified"),
        "content_length": int(length) if length and length.isdigit() else None,
    }


def read_manifest(source_id: str) -> list[dict]:
    path = manifest_path_for(source_id)
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_manifest_entry(entry: ManifestEntry) -> bool:
    """Append unless an entry with the same checksum already exists.

    Returns True if a line was written. Idempotent re-runs return False rather
    than growing the manifest with identical records.
    """
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    existing = read_manifest(entry.source_id)
    if any(record.get("sha256") == entry.sha256 for record in existing):
        return False
    path = manifest_path_for(entry.source_id)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry.to_json_line() + "\n")
    return True


def verify_file_checksum(path: Path, expected_sha256: str) -> str:
    """Raise unless the file hashes to `expected_sha256`. Returns the actual hash."""
    actual = sha256_of_file(path)
    if actual != expected_sha256:
        raise ChecksumMismatchError(
            f"{Path(path).name}: expected SHA-256 {expected_sha256}, found {actual}. "
            "Refusing to proceed — the file on disk is not the file that was verified."
        )
    return actual
