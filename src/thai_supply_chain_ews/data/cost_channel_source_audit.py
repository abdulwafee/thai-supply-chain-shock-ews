"""Official candidate source audit and the C6 recommendation gate (Task C5).

C5 looks for price series that represent the stages industries actually buy —
refined fuel, electricity, processed materials — rather than the raw commodities
already in hand. This module probes the official publishers, records what each
one actually documents, and applies a **preregistered** gate.

Two disciplines are load-bearing:

* **A blocked probe is not an absent source.** An HTTP 403, a timeout or a DNS
  failure is a fact about one mechanism at one moment. Candidates that cannot be
  verified are recorded ``not_executed_source_unreachable`` or ``unresolved``
  and are then **ineligible for recommendation**, because an unverifiable series
  definition cannot satisfy the gate — not because the source was judged absent.
* **No target outcome may enter ranking.** The gate refuses to run if any
  candidate carries a performance field, so a series cannot be preferred because
  it once produced a lower MAE.
"""

from __future__ import annotations

import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field

__all__ = [
    "FORBIDDEN_RANKING_FIELDS",
    "GATE_CRITERIA",
    "PROBE_STATES",
    "USER_AGENT",
    "CandidateGateError",
    "SourceCandidate",
    "apply_recommendation_gate",
    "probe_source",
    "rank_candidates",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PROBE_STATES = (
    "reachable",
    "http_error",
    "http_forbidden",
    "dns_failure",
    "tls_error",
    "timeout",
    "connection_error",
    "not_executed_source_unreachable",
)

#: Ranking must never see a model outcome. Presence of any of these raises.
FORBIDDEN_RANKING_FIELDS = (
    "mae", "macro_industry_mae", "rmse", "skill", "d4_metric", "development_mae",
    "false_negative", "accuracy", "score_improvement",
)

GATE_CRITERIA = (
    "official_publisher",
    "series_definition_and_unit_documented",
    "maps_to_purchased_intermediate_sector",
    "addresses_documented_structural_gap",
    "operational_timing_establishable",
    "coverage_adequate_or_limitations_explicit",
    "no_unresolved_definition_break",
    "availability_representable_without_download_time",
    "not_duplicative_without_semantic_distinction",
    "selection_free_of_target_outcomes",
)


class CandidateGateError(ValueError):
    """The recommendation gate was asked to do something it forbids."""


def probe_source(url: str, timeout: int = 60, method: str = "GET"):
    """Probe one official URL and classify the outcome specifically.

    ``http_forbidden`` is kept distinct from ``http_error`` because a 403 is
    usually a bot filter, not a statement about the resource — and because this
    site family blocks HEAD while serving GET, which would otherwise read as a
    missing file.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "th,en;q=0.8"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return {
                "state": "reachable",
                "http_status": response.status,
                "content_length": len(body),
                "content_type": response.headers.get("Content-Type"),
                "last_modified": response.headers.get("Last-Modified"),
                "body_head": body[:200],
            }
    except urllib.error.HTTPError as error:
        state = "http_forbidden" if error.code == 403 else "http_error"
        return {"state": state, "http_status": error.code, "content_length": 0,
                "content_type": None, "last_modified": None, "body_head": b""}
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, socket.gaierror):
            state = "dns_failure"
        elif isinstance(reason, ssl.SSLError):
            state = "tls_error"
        elif isinstance(reason, TimeoutError):
            state = "timeout"
        else:
            state = "connection_error"
        return {"state": state, "http_status": None, "content_length": 0,
                "content_type": None, "last_modified": None,
                "detail": str(reason)[:120], "body_head": b""}
    except TimeoutError:
        return {"state": "timeout", "http_status": None, "content_length": 0,
                "content_type": None, "last_modified": None, "body_head": b""}
    except OSError as error:
        return {"state": "connection_error", "http_status": None, "content_length": 0,
                "content_type": None, "last_modified": None,
                "detail": str(error)[:120], "body_head": b""}


@dataclass
class SourceCandidate:
    candidate_id: str
    source_family: str
    publisher: str
    official_url: str
    published_label: str = None
    unit: str = None
    price_basis: str = None
    geography: str = None
    taxes_and_margins: str = None
    frequency: str = None
    first_observation: str = None
    last_observation: str = None
    required_window_coverage: str = None
    missingness: str = None
    definition_breaks: str = None
    publication_timing_evidence: str = None
    revision_characteristics: str = None
    archived_first_release_available: bool = None
    mapped_io_sector: str = None
    mapped_io_sector_label: str = None
    structural_gap_addressed: str = None
    proxy_limitations: str = None
    probe_state: str = "not_executed_source_unreachable"
    probe_detail: dict = field(default_factory=dict)
    gate_results: dict = field(default_factory=dict)
    gate_passed: bool = False
    rejection_reasons: list = field(default_factory=list)
    recommended_for_c6: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["probe_detail"] = {
            k: v for k, v in payload["probe_detail"].items() if k != "body_head"
        }
        return payload


def _assert_no_outcome_fields(candidates) -> None:
    for candidate in candidates:
        payload = candidate.to_dict() if isinstance(candidate, SourceCandidate) else dict(candidate)
        for key in payload:
            lowered = str(key).lower()
            for forbidden in FORBIDDEN_RANKING_FIELDS:
                if forbidden in lowered:
                    raise CandidateGateError(
                        f"candidate carries ranking field {key!r}; selection must not use "
                        "target outcomes or model performance"
                    )


def apply_recommendation_gate(candidate: SourceCandidate, assessment: dict) -> SourceCandidate:
    """Evaluate the ten preregistered criteria for one candidate.

    ``assessment`` supplies each criterion's boolean verdict from the audit
    evidence. Every criterion must pass; a single failure records a reason and
    leaves the candidate ineligible.
    """
    missing = [name for name in GATE_CRITERIA if name not in assessment]
    if missing:
        raise CandidateGateError(f"gate assessment is missing criteria: {missing}")

    results = {name: bool(assessment[name]) for name in GATE_CRITERIA}
    reasons = [name for name, passed in results.items() if not passed]
    candidate.gate_results = results
    candidate.rejection_reasons = reasons
    candidate.gate_passed = not reasons
    return candidate


def rank_candidates(candidates, selection_order) -> list:
    """Deterministic ranking on structural and provenance evidence only."""
    _assert_no_outcome_fields(candidates)
    eligible = [c for c in candidates if c.gate_passed]

    def key(candidate):
        return tuple(
            -int(candidate.gate_results.get(criterion, False))
            for criterion in selection_order
        ) + (candidate.candidate_id,)

    return sorted(eligible, key=key)
