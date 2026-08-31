"""Input lineage for commodity features — Task C2.

Every calculated feature names the exact observations it consumed, and hashes
them. The checksum is what makes a claim like "this 12-month change used these
two archived first releases" checkable rather than asserted: change any input
value, issue date, or source checksum and the lineage checksum moves.

The tuple is ordered and fully specified, so the same inputs always produce the
same digest across runs, machines, and Python versions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

__all__ = [
    "LineageError",
    "LineageInput",
    "lineage_checksum",
    "lineage_records",
]


class LineageError(ValueError):
    """A lineage rule was violated."""


@dataclass(frozen=True)
class LineageInput:
    """One archived first-release observation consumed by a feature."""

    series_id: str
    reference_month: str
    displayed_value: float
    displayed_text: str
    decimal_places: int
    source_issue_name: str
    source_issue_date: str
    source_issue_url: str
    source_issue_sha256: str
    source_available_month: str
    # Index-membership token and its documented meaning. Deliberately NOT part
    # of `checksum_tuple`: they describe the observation, they are not the
    # observation, and C1.5-R3 must not perturb existing lineage digests.
    source_footnote_marker: str
    source_footnote_meaning: str = ""
    estimate_status: str = "not_documented_as_estimate"

    def checksum_tuple(self) -> list:
        """The ordered fields that define this input's identity.

        Deliberately includes the DISPLAYED text as well as the float: the PDF's
        printed precision is the actual evidence, and two different displayed
        strings must never collide onto one digest.
        """
        return [
            self.series_id,
            self.reference_month,
            self.displayed_text,
            f"{self.displayed_value!r}",
            self.source_issue_date,
            self.source_issue_sha256,
        ]


def lineage_checksum(inputs: list[LineageInput]) -> str:
    """Deterministic SHA-256 over the ordered input tuples.

    Inputs are hashed in the order given — chronological order, as consumed —
    because a transformation that reads the same months in a different order is
    a different transformation.
    """
    if not inputs:
        raise LineageError("Cannot compute a lineage checksum from zero inputs.")
    payload = json.dumps(
        [item.checksum_tuple() for item in inputs],
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lineage_records(inputs: list[LineageInput]) -> list[dict]:
    """Human-readable lineage rows for the audit artifact."""
    return [
        {
            "series_id": item.series_id,
            "reference_month": item.reference_month,
            "displayed_text": item.displayed_text,
            "displayed_value": item.displayed_value,
            "source_issue_name": item.source_issue_name,
            "source_issue_date": item.source_issue_date,
            "source_issue_sha256": item.source_issue_sha256,
            "source_available_month": item.source_available_month,
        }
        for item in inputs
    ]
