"""Owner-decision application and source-release closure (Task E2-R1).

Three owner decisions arrived after Task E2 recorded its findings: the code is
MIT, the release is a public GitHub **source checkout**, and the supported
Python floor is **3.12**. This module applies them and refuses the four ways
that application could go wrong.

**It supersedes rather than edits.** E2's blocked status, its missing-licence
finding, its original 3.11 expectation and its post-observation correction are
pinned by checksum and re-checked before anything else happens. A superseded
finding that gets edited to agree with a later decision stops being a record of
what was known when.

**The MIT grant is scoped.** It covers this project's own code and
documentation. It reaches no World Bank, NESDC, OIE or EPPO material, and
:func:`assert_mit_not_applied_to_third_party_data` raises on any sentence that
says otherwise -- an over-broad licence claim about someone else's data is not
a generosity, it is a false statement about rights this project never held.

**A supported version must agree everywhere.** Packaging metadata, both locks,
CI and the setup instructions are read and compared. Version drift is the
defect that makes a reproduction guide untrue without anyone noticing, so a
disagreement is a blocker rather than a note.

**Permitted is not tested.** The metadata admits 3.13 and later; nothing here
has run on them, so nothing here says they work.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import byte_provenance as BP

__all__ = [
    "MIT_REQUIRED_PHRASES",
    "SOURCE_RELEASE_BLOCKERS",
    "SourceReleaseError",
    "assert_limitation_is_documented",
    "assert_mit_not_applied_to_third_party_data",
    "assert_no_active_python_311_claim",
    "assert_no_build_artifact_in_manifest",
    "assert_no_citation_file_without_identity",
    "assert_no_invented_author_identity",
    "assert_source_checkout_scope",
    "decide_source_release",
    "python_consistency",
    "verify_documentation_links",
    "verify_e2_pins",
    "verify_license",
]

#: Reported in this order, most consequential first.
SOURCE_RELEASE_BLOCKERS = (
    "secret_or_credential_exposure",
    "locked_outcome_present_in_intended_release_or_history",
    "e2_historical_record_modified",
    "missing_owner_license_decision",
    "license_inconsistent_with_metadata",
    "mit_attributed_to_third_party_data",
    "python_version_inconsistency",
    "dependency_lock_rejects_supported_python",
    "clean_installation_failure",
    "hermetic_ci_failure",
    "build_artifact_in_public_release_manifest",
    "package_includes_prohibited_files",
    "unresolved_redistribution_of_included_raw_data",
    "dependency_vulnerability_without_accepted_resolution",
    "tests_mutate_the_release_worktree",
)

#: Sentences the MIT text must contain to still be the MIT licence. Checked as
#: normalised phrases rather than a whole-file digest, so a copyright year or a
#: scope note can be added without the check turning into a tripwire for
#: whitespace.
MIT_REQUIRED_PHRASES = (
    "mit license",
    "permission is hereby granted, free of charge",
    "the above copyright notice and this permission notice shall be included",
    'the software is provided "as is", without warranty of any kind',
    "in no event shall the authors or copyright holders be liable",
)

_NEGATIONS = (
    "not", "never", "no longer", "no ", "withdrawn", "originally", "was found",
    "were found", "incompatible", "historical", "history", "preserved",
    "superseded", "e2 ", "previously", "used to", "rather than", "instead of",
    "cannot", "does not", "is not", "are not", "unsupported", "dropped",
    "refused", "expected", "prior", "earlier", "unverified",
)
_NEGATION_WINDOW = 90


class SourceReleaseError(ValueError):
    """An owner decision was applied wrongly, or a superseded record moved."""


def _strip_quoted(text: str) -> str:
    """Blank out backticked and quoted spans so a rule may name itself."""
    for expression in (r"```.*?```", r"`[^`\n]*`", r'"[^"\n]{0,300}"',
                       r"'[^'\n]{0,300}'"):
        text = re.sub(expression, lambda m: " " * len(m.group(0)), text,
                      flags=re.DOTALL)
    return text


def _offences(text: str, phrases, *, window: int = _NEGATION_WINDOW) -> list:
    stripped = _strip_quoted(text)
    lowered = stripped.lower()
    found = []
    for phrase in phrases:
        for match in re.finditer(re.escape(phrase.lower()), lowered):
            before = lowered[max(0, match.start() - window):match.start()]
            if any(negation in before for negation in _NEGATIONS):
                continue
            line = stripped.count("\n", 0, match.start()) + 1
            found.append(f"line {line}: {phrase!r}")
    return found


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------

def verify_e2_pins(root: Path, pinned: dict) -> dict:
    """Confirm every E2 artifact that records a finding is unchanged.

    Three of E2's pins were taken from a Windows working tree, where the file
    was CRLF on disk while Git stored LF, so a Linux checkout holds the same
    text and different bytes. ``configs/line_ending_provenance.yaml`` declares
    which pin that applies to and in which representation; content that differs
    in any other way is still a modification.
    """
    root = Path(root)
    provenance = BP.provenance_entries(root)
    rows, moved, missing = {}, [], []
    for relative, expected in sorted(pinned.items()):
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            rows[relative] = {"present": False, "expected_sha256": expected}
            continue
        content = path.read_bytes()
        observed = BP.digest(content)
        matched = ("recorded_bytes" if observed == expected else
                   BP.match_declared_representation(
                       content, expected, provenance.get(relative)))
        rows[relative] = {"present": True, "expected_sha256": expected,
                          "observed_sha256": observed,
                          "canonical_sha256": BP.canonical_digest(content),
                          "matched_as": matched,
                          "unchanged": matched is not None}
        if matched is None:
            moved.append(relative)
    if missing or moved:
        raise SourceReleaseError(
            f"E2's historical record has changed: missing {missing}, modified "
            f"{moved}. E2-R1 supersedes E2's decision; it does not edit E2's "
            "findings, and a finding edited to agree with a later decision "
            "stops being a record of what was known when"
        )
    return {
        "artifacts": rows,
        "e2_original_readiness_preserved": True,
        "historical_findings_rewritten": False,
        "pinned_count": len(rows),
    }


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------

def verify_license(root: Path, config: dict, pyproject_text: str) -> dict:
    """The licence file, the metadata and the scope statement must agree."""
    root = Path(root)
    rules = config["license"]
    path = root / rules["license_file"]
    if not path.is_file():
        raise SourceReleaseError(
            f"{rules['license_file']} is absent. The owner chose MIT; a licence "
            "that is declared in metadata but not shipped grants nothing"
        )
    text = path.read_text(encoding="utf-8")
    normalised = re.sub(r"\s+", " ", text).lower()
    missing = [p for p in MIT_REQUIRED_PHRASES if p not in normalised]
    if missing:
        raise SourceReleaseError(
            f"{rules['license_file']} is not the MIT licence: {len(missing)} "
            f"required passage(s) absent, first {missing[0]!r}. An altered "
            "licence grants something other than what was decided"
        )
    if rules["copyright_line"].lower() not in normalised:
        raise SourceReleaseError(
            "the LICENSE copyright line does not match the one the owner "
            "supplied; a copyright holder is not something to paraphrase"
        )

    import tomllib

    project = tomllib.loads(pyproject_text).get("project", {})
    declared = project.get("license")
    if declared != rules["spdx_identifier"]:
        raise SourceReleaseError(
            f"packaging metadata declares license={declared!r}, expected the "
            f"SPDX expression {rules['spdx_identifier']!r}"
        )
    if "unlicensed" in pyproject_text.lower():
        raise SourceReleaseError(
            "the placeholder 'Unlicensed' is still present in packaging "
            "metadata. The owner has chosen a licence; a stale placeholder "
            "beside it tells a reader two different things"
        )
    classifiers = project.get("classifiers", [])
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    if license_classifiers:
        raise SourceReleaseError(
            f"deprecated licence classifier(s) {license_classifiers} sit beside "
            "an SPDX expression; setuptools 77+ rejects that combination"
        )
    return {
        "code_license": rules["code_license"],
        "spdx_identifier": declared,
        "license_file": rules["license_file"],
        "license_file_sha256": BP.canonical_digest(path.read_bytes()),
        "license_files_declared": project.get("license-files", []),
        "copyright_line": rules["copyright_line"],
        "unlicensed_placeholder_removed": True,
        "osi_classifier_used": False,
        "owner_license_decision_required": False,
        "license_blocker_cleared": True,
        "author_metadata": [a.get("name") for a in project.get("authors", [])],
    }


def assert_mit_not_applied_to_third_party_data(text: str) -> None:
    """Refuse any sentence that extends the MIT grant to somebody else's data."""
    offences = _offences(text, [
        "mit licence applies to world bank", "mit license applies to world bank",
        "mit licence applies to nesdc", "mit license applies to nesdc",
        "mit licence applies to oie", "mit license applies to oie",
        "mit licence applies to eppo", "mit license applies to eppo",
        "mit licence covers the data", "mit license covers the data",
        "mit licence covers third-party", "mit license covers third-party",
        "we relicense", "relicensed under mit", "relicensing the data",
        "the data is mit licensed", "the data is mit-licensed",
        "all files in this repository are mit",
    ])
    if offences:
        raise SourceReleaseError(
            "the MIT grant covers this project's own code and documentation "
            "only. It reaches no World Bank, NESDC, OIE or EPPO material, and "
            "an over-broad claim about someone else's data is a false statement "
            f"about rights this project never held. Found {offences}."
        )


def assert_no_invented_author_identity(text: str, permitted) -> None:
    """No personal name, address or identifier the owner has not supplied."""
    permitted_lower = {p.lower() for p in permitted}
    offences = []
    for match in re.finditer(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", text
    ):
        if match.group(0).lower() not in permitted_lower:
            offences.append("an email address")
    if re.search(r"\b(?:orcid\.org/)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", text):
        offences.append("an ORCID identifier")
    if offences:
        raise SourceReleaseError(
            "release metadata may not carry owner identity the owner has not "
            f"supplied. Found {sorted(set(offences))}."
        )


# ---------------------------------------------------------------------------
# The Python contract
# ---------------------------------------------------------------------------

def python_consistency(root: Path, config: dict) -> dict:
    """Read the supported Python version from every site and compare."""
    root = Path(root)
    expected = config["consistency"]["expected_python"]
    observed = {}

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    requires = re.search(r'requires-python\s*=\s*"([^"]+)"', pyproject)
    observed["pyproject_requires_python"] = requires.group(1) if requires else None
    target = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', pyproject)
    observed["ruff_target_version"] = (
        f"{target.group(1)}.{target.group(2)}" if target else None
    )

    for name, relative in (("runtime_lock", "requirements.lock.txt"),
                           ("development_lock", "requirements-dev.lock.txt")):
        text = (root / relative).read_text(encoding="utf-8")
        match = re.search(r"resolved on: CPython (\d+\.\d+)", text)
        observed[name] = match.group(1) if match else None

    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(r'python-version:\s*"([^"]+)"', workflow)
    observed["ci_workflow"] = match.group(1) if match else None

    for name, relative in (
        ("readme_setup", "README.md"),
        ("reproducibility_guide", "docs/e2r1_reproducibility_guide.md"),
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        match = re.search(r"Python (3\.\d+)", text)
        observed[name] = match.group(1) if match else None

    def normalise(value):
        if value is None:
            return None
        found = re.search(r"(\d+\.\d+)", value)
        return found.group(1) if found else value

    normalised = {name: normalise(value) for name, value in observed.items()}
    disagreements = sorted(
        name for name, value in normalised.items() if value != expected
    )
    return {
        "expected_python": expected,
        "observed": observed,
        "normalised": normalised,
        "disagreements": disagreements,
        "consistent": not disagreements,
        "minimum_supported_python": expected,
        "tested_python_versions": config["python_contract"]["tested_python_versions"],
        "python_311_supported": False,
        "python_311_compatibility_claim_withdrawn": True,
        "python_floor_changed_after_e2_observation": True,
    }


def assert_no_active_python_311_claim(text: str) -> None:
    """Refuse text telling a reader that 3.11 is supported.

    A *record* of what E2 expected is allowed and necessary; a *claim* that
    3.11 works is not. The two are separated by looking at what precedes the
    mention, the same way the other guards in this project separate a
    prohibition from the thing it prohibits.
    """
    offences = _offences(text, [
        "requires python 3.11", "python 3.11+", "python 3.11 or later",
        "requires-python = \">=3.11\"", "supports python 3.11",
        "python 3.11 is supported", "tested on python 3.11",
        "use python 3.11", "install python 3.11", "python-version: \"3.11\"",
    ])
    if offences:
        raise SourceReleaseError(
            "Python 3.11 is not supported: the resolved dependency set requires "
            "3.12 and above, and nothing here has been run on 3.11. A record of "
            "what Task E2 originally expected is permitted; a claim that 3.11 "
            f"works is not. Found {offences}."
        )


# ---------------------------------------------------------------------------
# Release scope
# ---------------------------------------------------------------------------

def assert_source_checkout_scope(text: str) -> None:
    """Refuse any claim that the built distribution is a supported runtime."""
    offences = _offences(text, [
        "pip install thai-supply-chain-ews",
        "available on pypi", "published to pypi", "upload to pypi",
        "twine upload", "install the wheel to use", "install from pypi",
        "installing the wheel gives you", "the wheel is a supported",
        "production package", "deployable service", "production-ready package",
    ])
    if offences:
        raise SourceReleaseError(
            "this release is a source checkout. The wheel and sdist are built "
            "for content inspection only, PyPI publication is neither supported "
            "nor authorised, and 15 modules resolve repository resources beside "
            f"the source tree so an installed distribution cannot run. Found {offences}."
        )


def assert_no_build_artifact_in_manifest(paths, config: dict) -> None:
    """A diagnostic artifact is not a deliverable and never a manifest row."""
    prohibited = (".whl", ".tar.gz")
    roots = ("dist/", "build/")
    offenders = sorted(
        str(path) for path in paths
        if str(path).replace("\\", "/").lower().endswith(prohibited)
        or str(path).replace("\\", "/").startswith(roots)
    )
    if offenders:
        raise SourceReleaseError(
            f"build artifact(s) {offenders} reached the public-release manifest. "
            "The wheel and sdist are built for content inspection and labelled "
            "diagnostic; shipping them would advertise a runtime this scope "
            "does not support"
        )


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def verify_documentation_links(root: Path, relative_paths, pending=()) -> dict:
    """Every relative link in a released document must resolve to a real file.

    ``pending`` names files this run is about to write. A link to one of them is
    not broken; it is early, and the runner asserts separately that every one
    was written before it finishes.
    """
    root = Path(root)
    expected = {
        (root / str(path).replace("\\", "/")).resolve() for path in pending
    }
    broken, checked, deferred = [], 0, 0
    for relative in sorted(relative_paths):
        if not str(relative).endswith(".md"):
            continue
        source = root / relative
        text = source.read_text(encoding="utf-8")
        for match in _MARKDOWN_LINK.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            checked += 1
            resolved = (source.parent / target.split("#", 1)[0]).resolve()
            if resolved in expected:
                deferred += 1
                continue
            if not resolved.exists():
                broken.append(f"{relative} -> {target}")
    return {
        "relative_links_checked": checked,
        "links_to_outputs_of_this_run": deferred,
        "broken_links": sorted(broken),
        "all_resolve": not broken,
    }


def assert_limitation_is_documented(text: str, required_phrases) -> None:
    """The installed-distribution limitation may not be quietly dropped.

    A limitation that stops being written down stops being a limitation and
    becomes a surprise. This checks the text still says it, rather than trusting
    that nobody deleted the paragraph.
    """
    lowered = text.lower()
    missing = [p for p in required_phrases if p.lower() not in lowered]
    if missing:
        raise SourceReleaseError(
            f"the installed-distribution limitation is no longer stated: "
            f"missing {missing}. It is the reason PyPI publication is not "
            "supported, and hiding it would make the release scope look like a "
            "preference rather than a consequence"
        )


def assert_no_citation_file_without_identity(root: Path, config: dict) -> None:
    """No ``CITATION.cff`` while the owner's identity is unverified."""
    path = Path(root) / "CITATION.cff"
    if path.exists() and config["citation"][
        "citation_metadata_deferred_until_owner_identity_provided"
    ]:
        raise SourceReleaseError(
            "CITATION.cff exists while owner identity is still deferred. A "
            "citation file names a person as the author of this work; writing "
            "one from metadata nobody verified puts a real person's name on a "
            "claim they never made"
        )


def decide_source_release(evidence: dict, limitations, config: dict) -> dict:
    """The E2-R1 readiness verdict.

    Separate from Task E2's decision function on purpose. E2-R1 gates on things
    E2 had no reason to check -- licence consistency, version agreement across
    five files, build artifacts in the manifest, the integrity of E2's own
    record -- and folding them into E2's blocker list would quietly change what
    E2's own tests were asserting about E2.
    """
    required = ("clean_install_verified", "hermetic_ci_verified",
                "clean_tree_unchanged_by_tests", "source_checkout_contract_verified")
    absent = [key for key in required if key not in evidence]
    if absent:
        raise SourceReleaseError(
            f"readiness was asked for without clean-tree evidence {absent}. A "
            "suite that passes in the working directory says nothing about what "
            "a stranger gets from a fresh clone"
        )
    live = {
        "secret_or_credential_exposure":
            bool(evidence.get("secret_findings", 1)),
        "locked_outcome_present_in_intended_release_or_history":
            not evidence.get("locked_test_release_excluded", False)
            or bool(evidence.get("locked_paths_in_release", 1))
            or bool(evidence.get("locked_paths_in_history", 1)),
        "e2_historical_record_modified":
            not evidence.get("e2_original_readiness_preserved", False),
        "missing_owner_license_decision":
            bool(evidence.get("owner_license_decision_required", True)),
        "license_inconsistent_with_metadata":
            not evidence.get("license_blocker_cleared", False),
        "mit_attributed_to_third_party_data":
            bool(evidence.get("mit_overreach_findings", 1)),
        "python_version_inconsistency":
            not evidence.get("python_contract_blocker_cleared", False),
        "dependency_lock_rejects_supported_python":
            not evidence.get("dependency_lock_python_compatible", False),
        "clean_installation_failure":
            not evidence.get("clean_install_verified", False),
        "hermetic_ci_failure":
            not evidence.get("hermetic_ci_verified", False),
        "build_artifact_in_public_release_manifest":
            bool(evidence.get("build_artifacts_in_manifest", 1)),
        "package_includes_prohibited_files":
            not evidence.get("diagnostic_package_contents_clean", False),
        "unresolved_redistribution_of_included_raw_data":
            bool(evidence.get("unresolved_redistribution_included_bytes", 1)),
        "dependency_vulnerability_without_accepted_resolution":
            bool(evidence.get("dependency_vulnerability_blockers", 1)),
        "tests_mutate_the_release_worktree":
            not evidence.get("clean_tree_unchanged_by_tests", False),
    }
    blockers = [name for name in SOURCE_RELEASE_BLOCKERS if live[name]]
    identifiers = {entry["id"] for entry in limitations}
    required_limitations = set(config["readiness"]["required_nonblocking_limitations"])
    absent_limitations = sorted(required_limitations - identifiers)
    if absent_limitations and not blockers:
        raise SourceReleaseError(
            f"required non-blocking limitation(s) {absent_limitations} are not "
            "recorded. A limitation that stops being written down stops being a "
            "limitation and becomes a surprise"
        )
    if blockers:
        status = "release_candidate_blocked"
    elif limitations:
        status = "release_candidate_ready_with_documented_nonblocking_limitations"
    else:
        status = "release_candidate_ready"
    return {
        "status": status,
        "supersedes_release_decision": "E2",
        "blockers": blockers,
        "blocker_count": len(blockers),
        "documented_nonblocking_limitations": list(limitations),
        "ready_because_working_directory_passes_tests": False,
        "evidence": dict(sorted(evidence.items())),
        "published": False,
        "committed": False,
        "tagged": False,
        "pushed": False,
        "github_repository_created": False,
        "released_on_github": False,
        "uploaded_to_pypi": False,
        "next_task": config["next_task"],
    }
