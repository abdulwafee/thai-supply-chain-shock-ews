"""Deterministic lineage checksums for the EPPO source tables (Task C7).

A monthly mean is only trustworthy if you can say exactly which documents made
it. These checksums hash the **ordered set of contributing facts** — series,
effective date, exact source label, source value, semantic regime, WordPress
media ID, document checksum, the daily lineage checksum and the aggregation rule
version — so a month whose inputs changed cannot keep the same lineage digest.

Two things are deliberately excluded.

``downloaded_at_utc`` and every other acquisition timestamp are absent: identical
bytes are an identical dataset, whatever hour they were fetched. Including them
would make every rerun look like a new dataset and destroy the determinism check
that the whole verification rests on.

Floats are serialised with :func:`repr`, which round-trips exactly in CPython.
Rounding to a display precision here would let two genuinely different published
prices hash to the same value.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "DAILY_LINEAGE_FIELDS",
    "MONTHLY_LINEAGE_FIELDS",
    "LineageError",
    "content_checksum",
    "daily_lineage_checksum",
    "monthly_lineage_checksum",
    "strip_acquisition_timestamps",
]

#: Ordered and fixed. Reordering would silently change every digest, so the
#: order is part of the contract rather than an implementation detail.
DAILY_LINEAGE_FIELDS = (
    "series_id",
    "effective_date",
    "source_product_label",
    "value",
    "unit",
    "price_stage",
    "semantic_regime_id",
    "media_id",
    "source_document_sha256",
)

MONTHLY_LINEAGE_FIELDS = (
    "series_id",
    "effective_date",
    "source_product_label",
    "value",
    "semantic_regime_id",
    "media_id",
    "source_document_sha256",
    "daily_lineage_checksum",
)

#: Fields that record *when we fetched*, never *what the source said*.
ACQUISITION_TIMESTAMP_FIELDS = (
    "downloaded_at_utc",
    "retrieved_at",
    "generated_at_utc",
    "run_started_at_utc",
    "run_finished_at_utc",
)


class LineageError(ValueError):
    """Lineage was asked to hash something it cannot hash reproducibly."""


def _token(value) -> str:
    if value is None:
        return "\x00null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    return str(value)


def daily_lineage_checksum(row) -> str:
    """Hash one canonical daily row over :data:`DAILY_LINEAGE_FIELDS`."""
    missing = [f for f in DAILY_LINEAGE_FIELDS if f not in row]
    if missing:
        raise LineageError(f"daily row is missing lineage fields: {sorted(missing)}")
    payload = "\x1f".join(_token(row[field]) for field in DAILY_LINEAGE_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def monthly_lineage_checksum(series_id: str, reference_month: str,
                             aggregation_rule_version: str, contributing_rows) -> str:
    """Hash a month over its complete ordered set of contributing daily rows.

    Contributions are sorted by effective date and media ID before hashing, so
    the digest depends on the *set* of documents that fed the month and never on
    the order in which they happened to be read.
    """
    rows = sorted(
        contributing_rows,
        key=lambda r: (str(r.get("effective_date")), r.get("media_id") or 0),
    )
    parts = [series_id, str(reference_month)[:7], str(aggregation_rule_version)]
    for row in rows:
        missing = [f for f in MONTHLY_LINEAGE_FIELDS if f not in row]
        if missing:
            raise LineageError(
                f"contributing row is missing lineage fields: {sorted(missing)}"
            )
        parts.append("\x1f".join(_token(row[field]) for field in MONTHLY_LINEAGE_FIELDS))
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()


def strip_acquisition_timestamps(payload):
    """Recursively drop acquisition timestamps before checksumming a document."""
    if isinstance(payload, dict):
        return {
            key: strip_acquisition_timestamps(value)
            for key, value in payload.items()
            if key not in ACQUISITION_TIMESTAMP_FIELDS
        }
    if isinstance(payload, list):
        return [strip_acquisition_timestamps(item) for item in payload]
    return payload


def content_checksum(payload) -> str:
    """Stable digest of a JSON-serialisable payload, timestamps excluded."""
    stripped = strip_acquisition_timestamps(payload)
    text = json.dumps(stripped, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
