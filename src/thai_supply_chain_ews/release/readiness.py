"""Release-readiness decision and its language guards (Task E2).

The readiness vocabulary has three values and they are not interchangeable.
*Ready* means every gate was measured and passed. *Ready with documented
non-blocking limitations* means the same, plus limitations a reader must know
about and that do not endanger anyone who installs the package. *Blocked* means
at least one blocker is live, and a blocker cannot be argued away by pointing at
the other gates that passed.

**A passing working directory is not readiness.** The working directory has the
raw data, an editable install and an exported environment variable; the release
tree has none of those. Only the clean-tree measurements feed this decision, and
:func:`decide` refuses a readiness input that carries no clean-tree evidence.

The guards below protect three specific overstatements that release documents
drift towards: that an unresolved licence question is a licence, that a clean
secret scan is a security guarantee, and that a public download URL is a
redistribution right. Each strips backticked and quoted spans and skips negated
occurrences, so the release notes can name the rule they enforce.
"""

from __future__ import annotations

import re

__all__ = [
    "BLOCKER_ORDER",
    "STATUSES",
    "ReadinessError",
    "assert_no_invented_owner_metadata",
    "assert_no_license_asserted",
    "assert_no_permanent_security_guarantee",
    "assert_no_redistribution_inference",
    "assert_not_ready_on_working_directory_alone",
    "collect_blockers",
    "decide",
]

STATUSES = (
    "release_candidate_ready",
    "release_candidate_ready_with_documented_nonblocking_limitations",
    "release_candidate_blocked",
)

#: Reported in this order so the most consequential blocker is read first.
BLOCKER_ORDER = (
    "secret_or_credential_exposure",
    "locked_outcome_present_in_intended_release_or_history",
    "missing_owner_license_decision",
    "clean_installation_failure",
    "hermetic_ci_failure",
    "package_includes_prohibited_files",
    "unresolved_redistribution_of_included_raw_data",
    "dependency_vulnerability_without_accepted_resolution",
    "tests_mutate_the_release_worktree",
)

_NEGATIONS = ("not", "never", "no", "cannot", "without", "refuses", "refused",
              "denies", "denied", "must not", "does not", "is not", "are not",
              "neither", "nor", "rather than", "instead of")
_NEGATION_WINDOW = 28


def _strip_quoted(text: str) -> str:
    """Blank out backticked and quoted spans so a rule may name itself."""
    for expression in (r"`{1,3}[^`]*`{1,3}", r'"[^"\n]{0,200}"', r"'[^'\n]{0,200}'"):
        text = re.sub(expression, lambda m: " " * len(m.group(0)), text)
    return text


def _check(text: str, phrases, message: str) -> None:
    stripped = _strip_quoted(text)
    lowered = stripped.lower()
    offences = []
    for phrase in phrases:
        for match in re.finditer(re.escape(phrase.lower()), lowered):
            window = lowered[max(0, match.start() - _NEGATION_WINDOW):match.start()]
            if any(negation in window for negation in _NEGATIONS):
                continue
            line = stripped.count("\n", 0, match.start()) + 1
            offences.append(f"line {line}: {phrase!r}")
    if offences:
        raise ReadinessError(f"{message} Found {offences}.")


class ReadinessError(ValueError):
    """A readiness claim exceeds what was measured."""


def assert_no_license_asserted(text: str) -> None:
    """A licence the owner has not chosen may not be stated as the project's."""
    _check(
        text,
        ["licensed under the mit", "released under the mit",
         "this project is mit", "licensed under apache", "licensed under bsd",
         "licensed under the gpl", "the project license is",
         "we have licensed", "license: mit"],
        "No LICENSE file exists and the owner has not made a licensing "
        "decision. A recommendation may be offered; a licence may not be "
        "asserted on the owner's behalf.",
    )


def assert_no_redistribution_inference(text: str) -> None:
    """Public download access is not a redistribution right."""
    _check(
        text,
        ["publicly available so we can redistribute",
         "public download grants redistribution",
         "freely downloadable therefore redistributable",
         "open access means we may republish",
         "since it is public we may redistribute"],
        "Public download access does not grant redistribution rights. Where "
        "terms are unclear the raw files are excluded and the acquisition code, "
        "URLs and checksums are published instead.",
    )


def assert_no_permanent_security_guarantee(text: str) -> None:
    """A clean audit is one database on one day."""
    _check(
        text,
        ["no vulnerabilities exist", "guaranteed secure", "permanently secure",
         "free of vulnerabilities forever", "proven to contain no secrets",
         "cannot contain a secret"],
        "A clean scan is a statement about one tool and one advisory database "
        "at one moment, not a permanent property of the release.",
    )


def assert_no_invented_owner_metadata(text: str, permitted_placeholders) -> None:
    """No name, address, ORCID or affiliation the owner did not supply."""
    offences = []
    permitted = tuple(p.lower() for p in permitted_placeholders)
    for match in re.finditer(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", text
    ):
        if match.group(0).lower() not in permitted:
            offences.append(f"email {match.group(0)[:2]}<redacted>")
    if re.search(r"\b(?:orcid\.org/)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", text):
        offences.append("orcid identifier")
    if offences:
        raise ReadinessError(
            "The release documents may not carry owner metadata the owner has "
            f"not supplied. Found {sorted(set(offences))}."
        )


def assert_not_ready_on_working_directory_alone(evidence: dict) -> None:
    """Refuse a readiness verdict backed only by the developer's own machine."""
    required = (
        "clean_tree_install_ok", "clean_tree_hermetic_tests_ok",
        "clean_tree_package_build_ok", "clean_tree_unchanged_by_tests",
    )
    missing = [key for key in required if key not in evidence]
    if missing:
        raise ReadinessError(
            f"readiness was asked for without clean-tree evidence {missing}. A "
            "suite that passes in the working directory says nothing about what "
            "a stranger gets from the published files"
        )


def collect_blockers(evidence: dict) -> list:
    """Every live blocker, in reporting order, each with the fact behind it."""
    live = {
        "secret_or_credential_exposure":
            evidence.get("credential_exposure_present", True),
        "locked_outcome_present_in_intended_release_or_history":
            bool(evidence.get("locked_paths_in_release", 0))
            or bool(evidence.get("locked_paths_in_history", 0))
            or bool(evidence.get("locked_paths_packaged", 0)),
        "missing_owner_license_decision":
            bool(evidence.get("owner_license_decision_required", True)),
        "clean_installation_failure":
            not evidence.get("clean_tree_install_ok", False),
        "hermetic_ci_failure":
            not evidence.get("clean_tree_hermetic_tests_ok", False),
        "package_includes_prohibited_files":
            not evidence.get("package_contents_clean", False),
        "unresolved_redistribution_of_included_raw_data":
            bool(evidence.get("unresolved_redistribution_included_bytes", 0)),
        "dependency_vulnerability_without_accepted_resolution":
            bool(evidence.get("unaccepted_vulnerabilities", 0)),
        "tests_mutate_the_release_worktree":
            not evidence.get("clean_tree_unchanged_by_tests", False),
    }
    return [name for name in BLOCKER_ORDER if live[name]]


def decide(evidence: dict, limitations) -> dict:
    """The readiness verdict, with every blocker and limitation attached."""
    assert_not_ready_on_working_directory_alone(evidence)
    blockers = collect_blockers(evidence)
    if blockers:
        status = "release_candidate_blocked"
    elif limitations:
        status = "release_candidate_ready_with_documented_nonblocking_limitations"
    else:
        status = "release_candidate_ready"
    return {
        "status": status,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "documented_nonblocking_limitations": list(limitations),
        "ready_because_working_directory_passes_tests": False,
        "evidence": dict(sorted(evidence.items())),
        "published": False,
        "committed": False,
        "tagged": False,
        "pushed": False,
        "released_on_github": False,
        "uploaded_to_pypi": False,
    }
