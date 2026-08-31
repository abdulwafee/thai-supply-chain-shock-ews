"""OIE MPI source discovery and reachability probing (Task D2).

One rule shapes this module: **a mechanism that fails reports how it failed, not
that the source is absent.**

Two earlier tasks were corrected for exactly that conflation. C1.5-R1 mislabelled
a February issue because one path-based lookup was filename-agnostic. C3-R1
declared an official 58-sector workbook non-existent because a single discovery
route (sitemap to download page) missed it, when it was in the media library all
along. So :func:`probe_entry_point` returns a specific state --
``dns_failure``, ``tls_hostname_mismatch``, ``http_error``, ``timeout`` -- and
:data:`ABSENCE_STATES` is deliberately empty: no probe outcome in this module is
permitted to mean "does not exist".

Establishing absence would require exhausting every discovery mechanism and
saying so explicitly. Nothing here does that, so nothing here claims it.
"""

from __future__ import annotations

import hashlib
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field

__all__ = [
    "ABSENCE_STATES",
    "PROBE_STATES",
    "USER_AGENT",
    "ProbeResult",
    "discover_entry_points",
    "fetch",
    "probe_entry_point",
    "summarize_discovery",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PROBE_STATES = (
    "reachable",
    "http_error",
    "dns_failure",
    "tls_hostname_mismatch",
    "tls_error",
    "timeout",
    "connection_error",
    "not_probed",
)

#: Intentionally empty. No probe state in this module means "the source does not
#: exist". Reachability is a statement about one mechanism at one moment.
ABSENCE_STATES = ()


@dataclass
class ProbeResult:
    entry_point_id: str
    url: str
    state: str
    http_status: object = None
    content_length: int = None
    content_type: str = None
    last_modified: str = None
    sha256: str = None
    detail: str = None
    supports_absence_claim: bool = field(default=False, init=False)

    def to_dict(self) -> dict:
        payload = dict(self.__dict__)
        payload["supports_absence_claim"] = False
        return payload


def fetch(url, timeout=60, accept_statuses=(200,), method="GET"):
    """Fetch a URL, returning ``(body, status, headers)``.

    ``accept_statuses`` lets an HTML endpoint that serves a full body under a
    404 router be read anyway (observed on NESDC in Task C3). It is opt-in and
    must never be used for a file download, where a 404 body is not the file.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        body = error.read() if error.code in accept_statuses else b""
        return body, error.code, dict(error.headers or {})


def probe_entry_point(entry_point, timeout=60) -> ProbeResult:
    """Probe one entry point and classify the outcome specifically."""
    url = entry_point["url"]
    identifier = entry_point["id"]
    try:
        body, status, headers = fetch(url, timeout=timeout, accept_statuses=(200, 404))
    except socket.gaierror as error:
        return ProbeResult(identifier, url, "dns_failure", detail=str(error))
    except ssl.SSLCertVerificationError as error:
        state = (
            "tls_hostname_mismatch"
            if "Hostname mismatch" in str(error)
            else "tls_error"
        )
        return ProbeResult(identifier, url, state, detail=str(error))
    except ssl.SSLError as error:
        return ProbeResult(identifier, url, "tls_error", detail=str(error))
    except TimeoutError as error:
        return ProbeResult(identifier, url, "timeout", detail=str(error))
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, socket.gaierror):
            return ProbeResult(identifier, url, "dns_failure", detail=str(reason))
        if isinstance(reason, ssl.SSLCertVerificationError):
            state = (
                "tls_hostname_mismatch"
                if "Hostname mismatch" in str(reason)
                else "tls_error"
            )
            return ProbeResult(identifier, url, state, detail=str(reason))
        return ProbeResult(identifier, url, "connection_error", detail=str(reason))
    except OSError as error:
        return ProbeResult(identifier, url, "connection_error", detail=str(error))

    state = "reachable" if status == 200 else "http_error"
    return ProbeResult(
        entry_point_id=identifier,
        url=url,
        state=state,
        http_status=status,
        content_length=len(body) if body else 0,
        content_type=headers.get("Content-Type"),
        last_modified=headers.get("Last-Modified"),
        sha256=hashlib.sha256(body).hexdigest() if body else None,
    )


def discover_entry_points(config, timeout=60) -> list:
    return [probe_entry_point(item, timeout=timeout) for item in config["entry_points"]]


def summarize_discovery(results) -> dict:
    """Aggregate probe outcomes without inferring absence from any of them."""
    by_state = {}
    for result in results:
        by_state.setdefault(result.state, []).append(result.entry_point_id)
    return {
        "probed": len(results),
        "reachable": sorted(by_state.get("reachable", [])),
        "unreachable_by_state": {
            state: sorted(ids)
            for state, ids in sorted(by_state.items())
            if state != "reachable"
        },
        "absence_established_for": [],
        "absence_claim_supported": False,
        "note": (
            "Unreachability here is a property of one mechanism at one moment. "
            "It is not evidence that a source does not exist."
        ),
    }
