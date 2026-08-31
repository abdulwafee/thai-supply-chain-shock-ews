"""Task E2-R1 — owner decision application and source-release closure.

Two halves, and the second is the one that matters.

The first checks what E2-R1 produced against the repository as it stands: the
MIT licence is real and scoped, the Python contract agrees in seven places, the
release is a source checkout, E2's record is untouched.

The second is the required battery of **synthetic failures**. Each plants one
defect and requires the machinery to catch it. A guard that has never been shown
to fire is not a guard, and the twenty ways this task could go wrong each need a
test that proves the corresponding rule is load-bearing.
"""

from __future__ import annotations

import ast
import json
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.release import inventory as INV
from thai_supply_chain_ews.release import source_release as SR

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "e2r1_source_release.yaml"
DECISION_PATH = ROOT / "docs" / "e2r1_source_release_decision.json"
MANIFEST_PATH = ROOT / "docs" / "e2r1_release_manifest.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
LICENSE_PATH = ROOT / "LICENSE"
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _report_describes_this_tree(report: dict) -> bool:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    skip = set(config["inventory"]["skip_directories"])
    total = sum(
        1 for path in ROOT.rglob("*")
        if path.is_file() and not set(path.relative_to(ROOT).parts) & skip
    )
    return report.get("inventory", {}).get("total_files") == total


@pytest.fixture(scope="module")
def decision():
    if not DECISION_PATH.is_file():
        pytest.skip("E2-R1 has not been run in this checkout")
    report = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    if not _report_describes_this_tree(report):
        pytest.skip(
            "the decision describes a different tree than this one; re-run "
            "scripts/run_e2r1_source_release.py here to refresh it"
        )
    return report


@pytest.fixture(scope="module")
def manifest(decision):  # noqa: ARG001 - ordering dependency, not a value
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def tiny_config():
    return {
        "license": {
            "code_license": "MIT",
            "spdx_identifier": "MIT",
            "license_file": "LICENSE",
            "copyright_line": "Copyright (c) 2026 Thai Supply Chain Shock EWS contributors",
        },
        "citation": {
            "citation_metadata_deferred_until_owner_identity_provided": True,
        },
        "consistency": {"expected_python": "3.12"},
        "python_contract": {"tested_python_versions": ["3.12"]},
        "readiness": {"required_nonblocking_limitations": []},
        "next_task": {"id": "E3", "name": "x", "requires_owner_confirmation_of": []},
    }


@pytest.fixture
def clean_evidence():
    return {
        "secret_findings": 0,
        "locked_paths_in_release": 0,
        "locked_paths_in_history": 0,
        "locked_test_release_excluded": True,
        "e2_original_readiness_preserved": True,
        "owner_license_decision_required": False,
        "license_blocker_cleared": True,
        "mit_overreach_findings": 0,
        "python_contract_blocker_cleared": True,
        "dependency_lock_python_compatible": True,
        "clean_install_verified": True,
        "source_checkout_contract_verified": True,
        "hermetic_ci_verified": True,
        "clean_tree_unchanged_by_tests": True,
        "build_artifacts_in_manifest": 0,
        "diagnostic_package_contents_clean": True,
        "unresolved_redistribution_included_bytes": 0,
        "dependency_vulnerability_blockers": 0,
    }


# ===========================================================================
# 1. Supersession
# ===========================================================================

def test_the_contract_declares_the_supersession_fields(config):
    supersession = config["supersession"]
    assert supersession["supersedes_release_decision"] == "E2"
    assert supersession["e2_original_readiness_preserved"] is True
    assert supersession["owner_decision_received_after_e2"] is True
    assert supersession["historical_findings_rewritten"] is False


def test_e2s_original_findings_are_recorded_verbatim(config):
    findings = config["supersession"]["e2_original_findings"]
    assert findings["readiness_status"] == "release_candidate_blocked"
    assert findings["blockers"] == ["missing_owner_license_decision"]
    assert findings["original_python_expectation"] == "3.11"
    assert "numpy" in findings["post_observation_python_correction"]
    assert re.fullmatch(r"[0-9a-f]{64}",
                        findings["public_release_manifest_checksum"])


def test_every_pinned_e2_artifact_is_byte_unchanged(config):
    SR.verify_e2_pins(ROOT, config["supersession"]["pinned_artifact_checksums"])


def test_the_e2_decision_still_says_it_was_blocked():
    """The superseded record must still read as it did when it was true."""
    e2 = json.loads(
        (ROOT / "docs" / "e2_release_readiness.json").read_text(encoding="utf-8")
    )
    assert e2["readiness"]["status"] == "release_candidate_blocked"
    assert e2["readiness"]["blockers"] == ["missing_owner_license_decision"]


# ===========================================================================
# 2. The licence
# ===========================================================================

def test_the_mit_licence_is_present_and_intact(config):
    report = SR.verify_license(ROOT, config, PYPROJECT)
    assert report["code_license"] == "MIT"
    assert report["spdx_identifier"] == "MIT"
    assert report["owner_license_decision_required"] is False
    assert report["license_blocker_cleared"] is True


def test_the_copyright_line_is_the_one_the_owner_supplied():
    text = LICENSE_PATH.read_text(encoding="utf-8")
    assert "Copyright (c) 2026 Thai Supply Chain Shock EWS contributors" in text


def test_the_placeholder_is_gone_from_packaging_metadata():
    assert "Unlicensed" not in PYPROJECT
    assert 'license = "MIT"' in PYPROJECT
    assert 'license-files = ["LICENSE"]' in PYPROJECT


def test_no_deprecated_licence_classifier_sits_beside_the_spdx_expression():
    import tomllib

    project = tomllib.loads(PYPROJECT)["project"]
    assert not [c for c in project.get("classifiers", [])
                if c.startswith("License ::")]


def test_the_licence_states_what_it_does_not_cover():
    text = LICENSE_PATH.read_text(encoding="utf-8")
    for publisher in ("World Bank", "NESDC", "OIE", "EPPO"):
        assert publisher in text
    assert "does NOT cover" in text or "does not cover" in text


def test_no_released_document_extends_mit_to_third_party_data(decision):
    assert decision["language_guards"]["offences"] == 0
    assert decision["language_guards"]["documents_checked"] > 100


def test_no_personal_identity_was_invented():
    import tomllib

    authors = tomllib.loads(PYPROJECT)["project"].get("authors", [])
    assert authors == [{"name": "Thai Supply Chain Shock EWS contributors"}]
    assert not any("email" in author for author in authors)
    for path in (LICENSE_PATH, ROOT / "THIRD_PARTY_NOTICES.md"):
        SR.assert_no_invented_author_identity(
            path.read_text(encoding="utf-8"), permitted=()
        )


def test_no_citation_file_exists_while_identity_is_deferred(config):
    assert config["citation"]["citation_file_created"] is False
    assert config["citation"]["author_metadata_invented"] is False
    assert config["citation"][
        "citation_metadata_deferred_until_owner_identity_provided"] is True
    assert config["citation"]["blocking"] is False
    SR.assert_no_citation_file_without_identity(ROOT, config)


# ===========================================================================
# 3. The Python contract
# ===========================================================================

def test_the_supported_version_agrees_across_every_site(config):
    report = SR.python_consistency(ROOT, config)
    assert report["disagreements"] == []
    assert report["consistent"] is True
    assert report["minimum_supported_python"] == "3.12"
    assert len(report["observed"]) == len(config["consistency"]["must_agree_on_python"])


def test_packaging_metadata_declares_the_floor():
    assert 'requires-python = ">=3.12"' in PYPROJECT
    assert 'target-version = "py312"' in PYPROJECT


def test_no_active_claim_that_311_is_supported():
    for relative in ("README.md", "docs/e2r1_reproducibility_guide.md",
                     "docs/e2r1_release_checklist.md",
                     ".github/workflows/ci.yml", "requirements.lock.txt"):
        SR.assert_no_active_python_311_claim(
            (ROOT / relative).read_text(encoding="utf-8")
        )


def test_the_historical_311_record_is_still_permitted_and_present():
    """The guard must allow a record of what E2 expected."""
    lock = (ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
    assert "3.11" in lock, "the historical note should still be there"
    SR.assert_no_active_python_311_claim(lock)


def test_later_versions_are_not_claimed_as_tested(config, decision):
    assert config["python_contract"]["tested_python_versions"] == ["3.12"]
    assert config["python_contract"]["later_versions_tested"] is False
    assert decision["python_contract"]["tested_python_versions"] == ["3.12"]


def test_every_pin_admits_the_supported_floor(decision):
    assert decision["dependencies"]["pins_rejecting_supported_python"] == []
    assert decision["dependencies"]["all_pins_admit_supported_python"] is True


def test_both_locks_were_regenerated_under_the_supported_floor():
    for name in ("requirements.lock.txt", "requirements-dev.lock.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "resolved on: CPython 3.12" in text
        assert "# resolver:" in text
        pins = [line for line in text.splitlines()
                if line.strip() and not line.startswith("#")]
        assert pins and all("==" in pin for pin in pins)


def test_pypdf_stays_declared_and_python_dotenv_stays_removed():
    import tomllib

    runtime = " ".join(tomllib.loads(PYPROJECT)["project"]["dependencies"])
    assert "pypdf" in runtime
    assert "python-dotenv" not in runtime


# ===========================================================================
# 4. Source-checkout scope
# ===========================================================================

def test_the_scope_fields_say_source_checkout_only(config):
    scope = config["release_scope"]
    assert scope["release_distribution_scope"] == "github_source_checkout"
    assert scope["supported_install_mode"] == "editable_source_checkout"
    assert scope["wheel_runtime_supported"] is False
    assert scope["sdist_runtime_supported"] is False
    assert scope["pypi_publication_supported"] is False
    assert scope["pypi_publication_authorized"] is False
    assert scope["standalone_installed_distribution_supported"] is False


def test_the_readme_leads_with_the_supported_path():
    raw = (ROOT / "README.md").read_text(encoding="utf-8")
    # Compared with whitespace normalised: the requirement is about what the
    # README states, not about where a line happens to wrap.
    text = re.sub(r"[\s>]+", " ", raw)
    assert "source-checkout research project" in text
    assert "Standalone wheel/PyPI installation is not currently supported" in text
    text = raw
    assert "python3.12 -m venv .venv" in text
    assert "-r requirements.lock.txt -r requirements-dev.lock.txt" in text
    assert "--no-deps -e ." in text
    assert "pytest -q" in text
    for forbidden in ("production package", "deployable service"):
        assert forbidden not in text.lower()


def test_the_readme_still_states_the_scientific_position():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "closed without a supported incremental commodity model" in text
    assert "persistence forecasts" in text
    assert "sealed, unopened" in text
    assert "latest-vintage" in text
    assert "not a real-time backtest" in text


def test_no_released_document_presents_the_wheel_as_a_runtime(decision):
    assert decision["language_guards"]["offences"] == 0
    assert decision["release_scope"]["wheel_runtime_supported"] is False


def test_the_packaging_limitation_is_still_stated(config, decision):
    limitation = config["packaging_limitation"]
    assert limitation["installed_distribution_resource_resolution_complete"] is False
    assert limitation["packaging_limitation_documented"] is True
    assert limitation["packaging_limitation_blocking_for_source_checkout_release"] is False
    assert limitation["packaging_limitation_blocking_for_pypi_release"] is True
    assert limitation["resource_resolution_refactor_authorized"] is False
    identifiers = {
        entry["id"]
        for entry in decision["readiness"]["documented_nonblocking_limitations"]
    }
    assert "standalone_distribution_not_supported" in identifiers
    SR.assert_limitation_is_documented(
        (ROOT / "docs" / "e2r1_source_release_decision.md").read_text(
            encoding="utf-8"),
        ("resolve repository resources", "pypi publication is neither supported"),
    )


def test_the_built_artifacts_are_labelled_diagnostic(decision):
    package = decision["diagnostic_package"]
    assert package["artifact_class"] == "diagnostic"
    assert package["supported_deliverable"] is False
    assert package["published"] is False
    assert package["excluded_from_public_release_manifest"] is True
    assert package["wheel"]["clean"] is True
    assert package["sdist"]["clean"] is True


# ===========================================================================
# 5. The release manifest
# ===========================================================================

def test_the_licence_is_in_the_release_manifest(manifest):
    assert "LICENSE" in {row["path"] for row in manifest["files"]}


def test_no_build_artifact_is_in_the_manifest(manifest, config):
    SR.assert_no_build_artifact_in_manifest(
        [row["path"] for row in manifest["files"]], config
    )
    assert manifest["build_artifacts_included"] is False


def test_the_manifest_records_the_scope_and_the_licence(manifest):
    assert manifest["release_distribution_scope"] == "github_source_checkout"
    assert manifest["minimum_supported_python"] == "3.12"
    assert manifest["code_license"] == "MIT"
    assert manifest["third_party_material_licensed_by_this_project"] is False


def test_no_raw_document_generated_table_or_locked_outcome_ships(manifest, config):
    prohibited = (".parquet", ".xls", ".xlsx", ".pdf", ".zip", ".pkl",
                  ".joblib", ".pyc", ".whl", ".tar.gz")
    paths = [row["path"] for row in manifest["files"]]
    assert [p for p in paths if p.lower().endswith(prohibited)] == []
    assert INV.locked_paths(
        paths, config["locked_test"]["outcome_path_fragments"]) == []
    leaked = [
        p for p in paths
        if p.startswith(("data/raw/", "data/interim/", "data/processed/",
                         "data/features/", "data/targets/", "data/model_input/",
                         "models/"))
        and p not in set(config["allowlist"]["exclude_exemptions"])
    ]
    assert leaked == []


def test_the_manifest_checksum_is_reproducible(manifest, decision):
    assert (decision["release_manifest_checksum"]
            == decision["release_manifest_checksum_recomputed"])
    assert INV.manifest_checksum(manifest) == decision["release_manifest_checksum"]


def test_the_manifest_excludes_the_documents_that_quote_it(manifest, config):
    declared = sorted(config["allowlist"]["self_referential_outputs"])
    assert manifest["self_referential_exclusions"] == declared
    assert not ({row["path"] for row in manifest["files"]} & set(declared))
    assert all((ROOT / path).is_file() for path in declared)


# ===========================================================================
# 6. Clean-tree verification and CI
# ===========================================================================

def test_the_clean_tree_ran_on_the_supported_interpreter(decision):
    assert decision["environment"]["clean_tree_python"].startswith("3.12")
    assert decision["clean_tree"]["ok"] is True


def test_the_project_was_installed_editable_from_the_lock(decision):
    step = next(s for s in decision["clean_tree"]["steps"]
                if s["step"] == "install_project_from_source")
    assert step["mode"] == "editable_source_checkout"
    assert step["independently_resolved_dependencies"] is False
    assert step["ok"] is True


def test_every_public_module_imported_and_the_smoke_checks_passed(decision):
    assert decision["clean_tree"]["public_modules_imported"] > 50
    assert all(entry["ok"] for entry in decision["clean_tree"]["cli_smoke"])


def test_the_measured_counts_and_durations_are_recorded(decision):
    clean = decision["clean_tree"]
    counts = clean["hermetic_tests"]["counts"]
    assert counts["measured_from_command_output"] is True
    assert counts["copied_from_prior_totals"] is False
    assert counts.get("failed", 0) == 0
    assert counts.get("errors", 0) == 0
    assert counts["passed"] > 0
    assert counts["skipped"] > 0
    assert isinstance(clean["install_duration_seconds"], (int, float))
    assert isinstance(clean["test_duration_seconds"], (int, float))


def test_the_release_tree_is_unchanged_by_its_own_tests(decision):
    clean = decision["clean_tree"]
    assert clean["tree_checksum_before_tests"] == clean["tree_checksum_after_tests"]
    assert clean["tree_unchanged_by_tests"] is True


def test_the_data_backed_registry_is_verified(decision):
    verification = decision["clean_tree"]["registry_verification"]
    assert verification["verified"] is True
    assert verification["unregistered_failures"] == []
    assert verification["registered_but_did_not_fail"] == []
    assert verification["tests_weakened_to_obtain_green_ci"] is False


def test_documentation_links_all_resolve(decision):
    assert decision["documentation_links"]["broken_links"] == []


def test_ci_targets_the_supported_interpreter_and_installs_editable():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in text
    assert "py3.12" in text
    assert "pip install --no-deps -e ." in text
    assert "-r requirements.lock.txt" in text
    assert "-r requirements-dev.lock.txt" in text


def test_ci_carries_no_active_311_reference():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert '"3.11"' not in text
    assert "py3.11" not in text
    SR.assert_no_active_python_311_claim(text)


def test_ci_reports_the_data_backed_tier_separately_and_publishes_nothing():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "data-backed tests NOT RUN here" in text
    assert "They were skipped, not" in text
    assert "diagnostic artifact" in text.lower()
    for forbidden in ("twine", "pypi-publish", "gh release", "secrets."):
        assert forbidden not in text
    workflow = yaml.safe_load(text)
    assert workflow["permissions"] == {"contents": "read"}
    for reference in re.findall(r"uses:\s*(\S+)", text):
        assert re.fullmatch(r"[0-9a-f]{40}", reference.split("@")[1])


# ===========================================================================
# 7. Readiness
# ===========================================================================

def test_the_candidate_is_ready_with_documented_limitations(decision):
    readiness = decision["readiness"]
    assert readiness["status"] == (
        "release_candidate_ready_with_documented_nonblocking_limitations"
    )
    assert readiness["blockers"] == []
    assert readiness["supersedes_release_decision"] == "E2"


def test_every_cleared_field_is_cleared(decision, config):
    evidence = decision["readiness"]["evidence"]
    assert evidence["owner_license_decision_required"] is False
    assert evidence["code_license"] == "MIT"
    assert evidence["license_blocker_cleared"] is True
    assert evidence["python_contract_blocker_cleared"] is True
    assert evidence["source_checkout_contract_verified"] is True
    assert evidence["clean_install_verified"] is True
    assert evidence["hermetic_ci_verified"] is True
    assert evidence["secret_findings"] == 0
    assert evidence["dependency_vulnerability_blockers"] == 0
    assert evidence["locked_test_release_excluded"] is True


def test_every_required_limitation_is_recorded(decision, config):
    identifiers = {
        entry["id"]
        for entry in decision["readiness"]["documented_nonblocking_limitations"]
    }
    assert set(config["readiness"]["required_nonblocking_limitations"]) <= identifiers
    for entry in decision["readiness"]["documented_nonblocking_limitations"]:
        assert entry["statement"].strip()
        assert entry["why_not_blocking"].strip()


def test_nothing_was_published(decision):
    readiness = decision["readiness"]
    for key in ("published", "committed", "tagged", "pushed",
                "github_repository_created", "released_on_github",
                "uploaded_to_pypi"):
        assert readiness[key] is False
    assert all(value is False
               for value in decision["prohibited_actions_taken"].values())
    assert not (ROOT / "dist").exists() or not any((ROOT / "dist").iterdir())


def test_the_next_task_requires_owner_confirmation(decision):
    nxt = decision["readiness"]["next_task"]
    assert nxt["id"] == "E3"
    assert nxt["may_act_only_after_all_confirmations"] is True
    for requirement in ("github_account_or_organization", "repository_name",
                        "public_visibility", "initial_release_version",
                        "commit_and_tag_authorization",
                        "author_identity_used_by_git",
                        "final_public_release_manifest_checksum"):
        assert requirement in nxt["requires_owner_confirmation_of"]


def test_security_and_upstream_science_are_clean(decision):
    security = decision["security"]
    assert security["credential_findings"] == 0
    assert security["absolute_path_findings"] == []
    assert security["review"]["unreviewed_count"] == 0
    assert security["dependency_vulnerabilities"] == 0
    for audit in security["dependency_audits"]:
        assert audit["state"] == "ran"
        assert audit["clean_audit_is_a_permanent_guarantee"] is False
    assert decision["upstream_science"]["all_unchanged"] is True
    assert decision["upstream_science"]["scientific_artifacts_modified"] is False


# ===========================================================================
# 8. The twenty required synthetic failures
# ===========================================================================

def _write(base: Path, relative: str, text: str) -> Path:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


_GOOD_PYPROJECT = '''[project]
name = "x"
version = "0.1.0"
requires-python = ">=3.12"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Thai Supply Chain Shock EWS contributors" }]
'''


@pytest.fixture
def mit_tree(tmp_path, tiny_config):
    _write(tmp_path, "LICENSE", LICENSE_PATH.read_text(encoding="utf-8"))
    return tmp_path


def test_synthetic_01_a_missing_or_altered_licence_is_refused(tmp_path, tiny_config,
                                                              mit_tree):
    # Missing.
    with pytest.raises(SR.SourceReleaseError, match="is absent"):
        SR.verify_license(tmp_path / "empty", tiny_config, _GOOD_PYPROJECT)
    # Altered: the warranty disclaimer removed.
    mangled = LICENSE_PATH.read_text(encoding="utf-8").replace(
        'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND', "")
    _write(mit_tree, "LICENSE", mangled)
    with pytest.raises(SR.SourceReleaseError, match="not the MIT licence"):
        SR.verify_license(mit_tree, tiny_config, _GOOD_PYPROJECT)


def test_synthetic_02_an_unlicensed_placeholder_in_metadata_is_refused(mit_tree,
                                                                       tiny_config):
    stale = _GOOD_PYPROJECT + '\ndescription = "Unlicensed - student portfolio"\n'
    with pytest.raises(SR.SourceReleaseError, match="Unlicensed"):
        SR.verify_license(mit_tree, tiny_config, stale)


def test_synthetic_03_claiming_mit_over_third_party_data_is_refused():
    for claim in ("The MIT licence applies to World Bank data as well.",
                  "The MIT license applies to NESDC workbooks.",
                  "All files in this repository are MIT licensed.",
                  "We relicense the OIE index under MIT."):
        with pytest.raises(SR.SourceReleaseError, match="own code and documentation"):
            SR.assert_mit_not_applied_to_third_party_data(claim)
    # The rule may state itself: quoted spans are stripped, negations skipped.
    SR.assert_mit_not_applied_to_third_party_data(
        'This document may not say "the MIT licence applies to World Bank data", '
        "and the grant does not cover NESDC workbooks."
    )


def test_synthetic_04_invented_personal_metadata_is_refused():
    # Assembled at run time. A literal address written here would be found by
    # this project's own scanner in this very file, and a test fixture is not a
    # leak -- but a file containing one is indistinguishable from a file that
    # leaked one, which is the whole reason the rule exists.
    planted = "someone" + "@" + "somewhere.invalid"
    with pytest.raises(SR.SourceReleaseError, match="owner identity"):
        SR.assert_no_invented_author_identity(
            f"Author: {planted}", permitted=()
        )
    with pytest.raises(SR.SourceReleaseError, match="owner identity"):
        SR.assert_no_invented_author_identity(
            "ORCID 0000-0002-1825-0097", permitted=()
        )
    SR.assert_no_invented_author_identity(
        "Thai Supply Chain Shock EWS contributors", permitted=()
    )


def test_synthetic_05_a_citation_file_without_identity_is_refused(tmp_path,
                                                                  tiny_config):
    _write(tmp_path, "CITATION.cff", "cff-version: 1.2.0\n")
    with pytest.raises(SR.SourceReleaseError, match="owner identity is still deferred"):
        SR.assert_no_citation_file_without_identity(tmp_path, tiny_config)


def test_synthetic_06_an_active_311_support_claim_is_refused():
    for claim in ("This project requires Python 3.11 or later.",
                  "Supports Python 3.11 and above.",
                  "Tested on Python 3.11."):
        with pytest.raises(SR.SourceReleaseError, match="not supported"):
            SR.assert_no_active_python_311_claim(claim)
    # A historical record must pass.
    SR.assert_no_active_python_311_claim(
        "Task E2 originally expected Python 3.11 and found it incompatible with "
        "the resolved dependency set."
    )


def test_synthetic_07_ci_and_the_locks_disagreeing_is_refused(tmp_path, tiny_config):
    _write(tmp_path, "pyproject.toml",
           _GOOD_PYPROJECT + '\n[tool.ruff]\ntarget-version = "py312"\n')
    _write(tmp_path, "requirements.lock.txt", "# resolved on: CPython 3.12, X\nnumpy==1\n")
    _write(tmp_path, "requirements-dev.lock.txt", "# resolved on: CPython 3.12, X\n")
    _write(tmp_path, ".github/workflows/ci.yml", 'python-version: "3.11"\n')
    _write(tmp_path, "README.md", "Requires Python 3.12.\n")
    _write(tmp_path, "docs/e2r1_reproducibility_guide.md", "Python 3.12.\n")
    report = SR.python_consistency(tmp_path, tiny_config)
    assert report["consistent"] is False
    assert "ci_workflow" in report["disagreements"]


def test_synthetic_08_a_pin_that_rejects_the_floor_is_detected():
    from thai_supply_chain_ews.release import dependencies as DEP

    assert DEP.requires_python_admits(">=3.12", "3.12") is True
    assert DEP.requires_python_admits(">=3.13", "3.12") is False
    assert DEP.requires_python_admits("<3.12", "3.12") is False


def test_synthetic_09_a_project_install_that_reresolves_is_refused(config):
    assert config["dependencies"]["install_must_use_lock_contract_only"] is True
    assert config["dependencies"][
        "independent_resolution_during_project_install_is_a_failure"] is True
    assert set(config["dependencies"]["editable_install_flags"]) == {"--no-deps", "-e"}
    # The clean-tree runner must pass both flags.
    source = (ROOT / "src" / "thai_supply_chain_ews" / "release"
              / "clean_tree.py").read_text(encoding="utf-8")
    assert '["--no-deps", "-e", "."] if editable else ["--no-deps", "."]' in source


def test_synthetic_10_presenting_the_wheel_as_a_runtime_is_refused():
    for claim in ("Install the wheel to use the package.",
                  "The wheel is a supported runtime.",
                  "This is a production package.",
                  "This is a deployable service."):
        with pytest.raises(SR.SourceReleaseError, match="source checkout"):
            SR.assert_source_checkout_scope(claim)


def test_synthetic_11_pypi_publication_instructions_are_refused():
    for claim in ("Run twine upload dist/*.",
                  "The package is available on PyPI.",
                  "pip install thai-supply-chain-ews"):
        with pytest.raises(SR.SourceReleaseError, match="source checkout"):
            SR.assert_source_checkout_scope(claim)


def test_synthetic_12_hiding_the_installed_distribution_limitation_is_refused():
    with pytest.raises(SR.SourceReleaseError, match="no longer stated"):
        SR.assert_limitation_is_documented(
            "Everything works everywhere.",
            ("resolve repository resources",),
        )


def test_synthetic_13_a_build_artifact_in_the_manifest_is_refused(config):
    for offender in ("dist/thai_supply_chain_ews-0.1.0-py3-none-any.whl",
                     "dist/thai_supply_chain_ews-0.1.0.tar.gz",
                     "build/lib/thing.py"):
        with pytest.raises(SR.SourceReleaseError, match="build artifact"):
            SR.assert_no_build_artifact_in_manifest(["src/a.py", offender], config)
    SR.assert_no_build_artifact_in_manifest(["src/a.py", "LICENSE"], config)


def test_synthetic_14_a_failed_editable_install_blocks_readiness(clean_evidence,
                                                                 tiny_config):
    blocked = SR.decide_source_release(
        {**clean_evidence, "clean_install_verified": False}, [], tiny_config
    )
    assert blocked["status"] == "release_candidate_blocked"
    assert blocked["blockers"] == ["clean_installation_failure"]


def test_synthetic_15_hermetic_tests_may_not_depend_on_local_raw_data(decision):
    """Proved by removal, not asserted.

    The clean tree has no official downloads. With the data-backed registry
    removed, every registered test must fail there and nothing else may, which
    is what shows the hermetic tier does not quietly read the developer's data.
    """
    verification = decision["clean_tree"]["registry_verification"]
    assert verification["verified"] is True
    assert verification["failed_without_registry"] >= verification["registered"]
    assert verification["unregistered_failures"] == []
    assert decision["clean_tree"]["no_local_data_in_tree"] is True


def test_synthetic_16_a_mutating_test_run_blocks_readiness(clean_evidence,
                                                           tiny_config):
    blocked = SR.decide_source_release(
        {**clean_evidence, "clean_tree_unchanged_by_tests": False}, [], tiny_config
    )
    assert blocked["blockers"] == ["tests_mutate_the_release_worktree"]


def test_synthetic_17_prohibited_content_never_enters_the_release(tmp_path, config):
    allow = config["allowlist"]
    for offender in ("data/raw/OIE_MPI/2026-08/Prodidx1.xlsx",
                     "data/features/c4_canonical_long.parquet",
                     "data/model_input/predictions.parquet",
                     "models/h1/model.joblib",
                     "docs/locked_test/outcomes.json",
                     "dist/thing.whl",
                     ".venv/Lib/site-packages/x.py"):
        admitted, _ = INV.classify_release(
            offender, allow["include_globs"], allow["exclude_globs"],
            allow["exclude_exemptions"],
        )
        assert admitted is False, offender
    # And a locked path is refused by name even before the allowlist speaks.
    with pytest.raises(INV.InventoryError):
        INV.assert_no_locked_path(
            ["docs/locked_test/outcomes.json"],
            config["locked_test"]["outcome_path_fragments"], "the release",
        )


def test_synthetic_18_a_secret_or_absolute_path_blocks_readiness(clean_evidence,
                                                                 tiny_config):
    from thai_supply_chain_ews.release import security_audit as SEC

    blocked = SR.decide_source_release(
        {**clean_evidence, "secret_findings": 1}, [], tiny_config
    )
    assert blocked["blockers"] == ["secret_or_credential_exposure"]
    # An absolute home path is found, and never echoed.
    findings = SEC.scan_text("root = " + "C:" + chr(92) + "Users" + chr(92)
                             + "someone" + chr(92) + "project\n", "fake.py")
    assert any(f["family"] == "absolute_home_paths" for f in findings)
    assert all(f["value_reported"] is False for f in findings)


def test_synthetic_19_overwriting_e2s_blocked_decision_is_refused(tmp_path, config):
    pinned = config["supersession"]["pinned_artifact_checksums"]
    relative, expected = next(iter(pinned.items()))
    _write(tmp_path, relative, "a later decision, written over the record\n")
    with pytest.raises(SR.SourceReleaseError, match="historical record has changed"):
        SR.verify_e2_pins(tmp_path, {relative: expected})
    # And a missing record is refused too, not silently skipped.
    with pytest.raises(SR.SourceReleaseError, match="historical record has changed"):
        SR.verify_e2_pins(tmp_path / "empty", {relative: expected})


def test_the_superseded_e2_runner_refuses_to_overwrite_its_own_record():
    """Re-running E2 would rewrite a record E2-R1 pinned. It must not be able to.

    A supersession promise that depends on nobody happening to run the old
    script is not a guarantee, so the old script checks whether its outputs are
    pinned and stops.
    """
    import subprocess
    import sys as _sys

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [_sys.executable, str(ROOT / "scripts" / "run_e2_release_preparation.py")],
        capture_output=True, text=True, check=False, cwd=str(ROOT), timeout=300,
    )
    assert completed.returncode != 0
    assert "superseded by E2-R1" in completed.stdout + completed.stderr
    # And it stopped before writing: E2's pinned record is still intact.
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    SR.verify_e2_pins(ROOT, config["supersession"]["pinned_artifact_checksums"])


def test_synthetic_20_no_e3_publication_action_is_attempted(config):
    """E3's actions are prohibited here and absent from the runner."""
    for action in ("commit", "tag", "push", "create_a_github_repository",
                   "publish_to_pypi", "create_a_github_release"):
        assert action in config["prohibited_actions"]
    tree = ast.parse(
        (ROOT / "scripts" / "run_e2r1_source_release.py").read_text(encoding="utf-8")
    )
    argv_literals, call_sites = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", getattr(node.func, "id", "")) != "run":
            continue
        call_sites += 1
        for argument in node.args:
            if isinstance(argument, (ast.List, ast.Tuple)):
                argv_literals.extend(
                    element.value.lower() for element in argument.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                )
    assert call_sites
    for forbidden in ("commit", "tag", "push", "twine", "pypi", "upload",
                      "release", "gh "):
        assert [text for text in argv_literals if forbidden in text] == []
    assert config["next_task"]["may_act_only_after_all_confirmations"] is True


# ===========================================================================
# 9. The runner itself
# ===========================================================================

def test_the_runner_takes_no_arguments_and_offers_no_escape_hatch():
    source = (ROOT / "scripts" / "run_e2r1_source_release.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    assert not main.args.args and not main.args.kwonlyargs
    for escape in ("argparse", "sys.argv[1", "os.environ", "getenv",
                   "--publish", "--force", "--skip", "--allow"):
        assert escape not in source


def test_a_synthetic_wheel_with_a_locked_member_is_refused(tmp_path, config):
    from thai_supply_chain_ews.release import package_audit as PKG

    archive = tmp_path / "pkg-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pkg/__init__.py", "")
        handle.writestr("pkg/locked_test/outcomes.json", "{}")
    rules = {"package": {"prohibited_members": [".parquet"],
                         "prohibited_member_fragments": ["data/raw/"]}}
    with pytest.raises(PKG.PackageAuditError, match="locked-outcome member"):
        PKG.audit_members(archive, rules,
                          config["locked_test"]["outcome_path_fragments"])
