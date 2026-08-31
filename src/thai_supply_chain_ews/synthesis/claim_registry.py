"""The claim registry: every material statement carries its evidence (Task E1).

A closeout report is a long list of assertions. Most of them are true and a few
of them are the ones that would embarrass the project in an interview, so each
one is registered with a status from a fixed vocabulary, a pointer into the
artifact that supports it, the limitations that artifact requires, and an
explicit ``locked_test_dependency: false``.

Five failure modes are checked rather than trusted.

**A number that does not match its source.** ``15.3073`` is easy to type and
easy to mistype, and a closeout that quotes a figure the artifact does not
contain is worse than one that omits it. :func:`reconcile_numeric_claims`
resolves each pointer and compares.

**A superseded result presented as current.** D1's evaluation was not
release-timing correct and D3/D4 replaced it for operational interpretation. It
stays in the ledger — deleting a negative result is how a record starts lying —
but it carries its ``superseded_by`` marker, and the supersession graph is
checked for cycles.

**A claim that depends on a locked outcome.** There are none, and the registry
refuses to hold one.

**A missing limitation.** Every artifact that states a limitation propagates it:
D1 without its fallback caveat, or D4 without its degenerate-design caveat, is a
different and friendlier claim than the one the evidence supports.

**Two incompatible evaluation contracts compared without qualification.** D1 ran
before the D3 issue-month contract existed. Putting its 15.31 beside D4's 17.56
without saying so invites a comparison the numbers cannot bear.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "AUDIENCES",
    "EVIDENCE_STATUSES",
    "REQUIRED_CLAIM_FIELDS",
    "ClaimRegistryError",
    "assert_no_locked_dependency",
    "assert_no_unqualified_contract_comparison",
    "assert_required_limitations",
    "assert_supersession_acyclic",
    "ledger_checksum",
    "reconcile_numeric_claims",
    "resolve_pointer",
    "validate_claim",
    "validate_registry",
]

EVIDENCE_STATUSES = (
    "verified",
    "supported_with_limitations",
    "inconclusive",
    "not_supported",
    "unresolved",
    "not_attempted",
    "superseded",
)

AUDIENCES = ("technical", "portfolio", "both")

REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "claim_text",
    "status",
    "scope",
    "audience",
    "evidence_artifact",
    "evidence_json_pointer",
    "limitations",
    "locked_test_dependency",
)


class ClaimRegistryError(ValueError):
    """A claim was registered without the evidence it needs to stand on."""


def resolve_pointer(payload, pointer: str):
    """Walk a dotted pointer, tolerating keys that themselves contain dots.

    D5's result keys look like ``fo600_direct_sector093|h1``, and D3's baseline
    keys are numeric strings. A naive split would not find either, so each
    segment is matched greedily against the keys actually present.
    """
    node = payload
    remaining = str(pointer)
    while remaining:
        if not isinstance(node, dict):
            raise ClaimRegistryError(
                f"pointer {pointer!r} descends into a {type(node).__name__}"
            )
        for key in sorted(node, key=len, reverse=True):
            if remaining == key:
                return node[key]
            if remaining.startswith(f"{key}."):
                node = node[key]
                remaining = remaining[len(key) + 1:]
                break
        else:
            raise ClaimRegistryError(
                f"pointer {pointer!r} has no match at {sorted(node)[:6]}"
            )
    return node


def reconcile_numeric_claims(claims, artifacts, tolerance: float = 1e-3,
                             derived=None) -> dict:
    """Resolve every frozen numeric claim against its artifact and compare.

    ``derived`` supplies the handful of quantities that are counts of a
    structure rather than a stored field — how many D1 selections used the
    fallback, for instance. They are computed from the artifact, never asserted.
    """
    derived = derived or {}
    rows, failures = [], []
    for claim in claims:
        pointer = claim["pointer"]
        artifact = claim["artifact"]
        if pointer.startswith("__") and pointer.endswith("__"):
            actual = derived.get(pointer)
            if actual is None:
                raise ClaimRegistryError(
                    f"derived pointer {pointer!r} was not supplied"
                )
        else:
            payload = artifacts.get(artifact)
            if payload is None:
                raise ClaimRegistryError(f"artifact {artifact!r} was not loaded")
            actual = resolve_pointer(payload, pointer)
        expected = float(claim["value"])
        agrees = abs(float(actual) - expected) <= tolerance
        rows.append({
            "id": claim["id"], "artifact": artifact, "pointer": pointer,
            "expected": expected, "actual": float(actual), "reconciled": agrees,
        })
        if not agrees:
            failures.append(claim["id"])
    return {
        "claims_checked": len(rows),
        "tolerance": tolerance,
        "all_reconciled": not failures,
        "failures": failures,
        "rows": rows,
    }


def validate_claim(claim: dict) -> None:
    """Raise unless one registry entry carries everything a claim needs."""
    missing = [f for f in REQUIRED_CLAIM_FIELDS if f not in claim]
    if missing:
        raise ClaimRegistryError(
            f"claim {claim.get('claim_id')!r} is missing {sorted(missing)}"
        )
    if claim["status"] not in EVIDENCE_STATUSES:
        raise ClaimRegistryError(
            f"claim {claim['claim_id']!r} has status {claim['status']!r}, which is "
            f"not one of {list(EVIDENCE_STATUSES)}"
        )
    if claim["audience"] not in AUDIENCES:
        raise ClaimRegistryError(
            f"claim {claim['claim_id']!r} has audience {claim['audience']!r}"
        )
    if not claim["evidence_artifact"] or not claim["evidence_json_pointer"]:
        raise ClaimRegistryError(
            f"claim {claim['claim_id']!r} has no evidence pointer. An unsupported "
            "numerical or narrative claim is exactly what this registry exists to "
            "catch"
        )
    if claim["status"] == "superseded" and not claim.get("superseded_by"):
        raise ClaimRegistryError(
            f"claim {claim['claim_id']!r} is superseded but names no successor. A "
            "superseded result stays in the ledger and says so; it is not "
            "silently presented as current"
        )
    if claim.get("locked_test_dependency"):
        raise ClaimRegistryError(
            f"claim {claim['claim_id']!r} depends on a locked outcome. No claim in "
            "this project may: the locked test was never opened"
        )


def assert_no_locked_dependency(claims) -> None:
    """Raise if any claim rests on a locked-test outcome."""
    offenders = sorted(
        c["claim_id"] for c in claims if c.get("locked_test_dependency")
    )
    if offenders:
        raise ClaimRegistryError(
            f"claims {offenders} depend on locked outcomes, which were never read"
        )


def assert_required_limitations(claims, required_by_artifact: dict) -> None:
    """Raise if a claim drops a limitation its source artifact requires.

    D1 without the fallback caveat and D4 without the degenerate-design caveat
    are both friendlier than the evidence, and both are refused.
    """
    for claim in claims:
        required = required_by_artifact.get(claim["evidence_artifact"], ())
        text = " ".join(claim.get("limitations") or []).lower()
        missing = [token for token in required if token.lower() not in text]
        if missing:
            raise ClaimRegistryError(
                f"claim {claim['claim_id']!r} cites "
                f"{claim['evidence_artifact']} but omits required limitation(s) "
                f"{missing}"
            )


def assert_no_unqualified_contract_comparison(text, incompatible_pairs,
                                              qualification: str) -> None:
    """Raise if two incompatible evaluation contracts are compared silently.

    D1 predates the D3 issue-month contract. Its numbers may appear beside D4's,
    but only in a passage that says the contracts differ.
    """
    lowered = str(text).lower()
    for first, second in incompatible_pairs:
        if first.lower() in lowered and second.lower() in lowered:
            if qualification.lower() not in lowered:
                raise ClaimRegistryError(
                    f"{first} and {second} appear together without the "
                    f"qualification {qualification!r}. They ran under different "
                    "evaluation contracts and their metrics are not directly "
                    "comparable"
                )


def assert_supersession_acyclic(edges) -> dict:
    """Raise on a cycle in the supersession graph, and return its topology."""
    successors = {}
    for edge in edges:
        successors.setdefault(edge["superseded"], set()).add(edge["superseded_by"])
    state = {}

    def visit(node, trail):
        if state.get(node) == "done":
            return
        if state.get(node) == "open":
            raise ClaimRegistryError(
                f"the supersession graph has a cycle: {' -> '.join([*trail, node])}"
            )
        state[node] = "open"
        for nxt in sorted(successors.get(node, ())):
            visit(nxt, [*trail, node])
        state[node] = "done"

    for node in sorted(successors):
        visit(node, [])
    return {
        "nodes": sorted(set(successors) | {v for s in successors.values() for v in s}),
        "edges": len(edges),
        "acyclic": True,
        "superseded_tasks": sorted(successors),
    }


def validate_registry(claims, artifacts, required_by_artifact=None,
                      incompatible_pairs=(), qualification: str = "") -> dict:
    """Validate every entry, then the registry as a whole."""
    seen = set()
    for claim in claims:
        validate_claim(claim)
        if claim["claim_id"] in seen:
            raise ClaimRegistryError(f"duplicate claim_id {claim['claim_id']!r}")
        seen.add(claim["claim_id"])
        artifact = claim["evidence_artifact"]
        if artifact not in artifacts:
            raise ClaimRegistryError(
                f"claim {claim['claim_id']!r} cites {artifact!r}, which was not "
                "loaded; a pointer into an artifact nobody opened is not evidence"
            )
    assert_no_locked_dependency(claims)
    if required_by_artifact:
        assert_required_limitations(claims, required_by_artifact)
    if incompatible_pairs and qualification:
        for claim in claims:
            assert_no_unqualified_contract_comparison(
                claim["claim_text"], incompatible_pairs, qualification
            )
    by_status = {}
    for claim in claims:
        by_status[claim["status"]] = by_status.get(claim["status"], 0) + 1
    return {
        "claims": len(claims),
        "distinct_claim_ids": len(seen),
        "by_status": dict(sorted(by_status.items())),
        "by_audience": {
            audience: sum(1 for c in claims if c["audience"] == audience)
            for audience in AUDIENCES
        },
        "locked_test_dependencies": 0,
        "all_valid": True,
    }


def ledger_checksum(payload) -> str:
    """Stable digest of the evidence ledger, generation timestamps excluded."""
    dropped = {"generated_at_utc", "run_started_at_utc", "run_finished_at_utc"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
