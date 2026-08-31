"""Task E2 — reproducible portfolio release preparation.

The tests are in two halves and the second half is the one that matters.

The first half checks the artifacts E2 produced against the repository as it
stands: the allowlist fails closed, the locked test is untouched, the package is
clean, the dependency set reconciles, the CI workflow pins its actions.

The second half is a battery of **synthetic failures**. Each one plants exactly
one defect into a synthetic tree or a synthetic report and requires the
machinery to catch it. A guard that has never been shown to fire is not a
guard — it is a comment that happens to be executable — and every prohibition in
the E2 contract needs a test that proves it is load-bearing.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.release import clean_tree as CT
from thai_supply_chain_ews.release import dependencies as DEP
from thai_supply_chain_ews.release import inventory as INV
from thai_supply_chain_ews.release import package_audit as PKG
from thai_supply_chain_ews.release import readiness as RDY
from thai_supply_chain_ews.release import security_audit as SEC

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "e2_release_preparation.yaml"
READINESS_PATH = ROOT / "docs" / "e2_release_readiness.json"
MANIFEST_PATH = ROOT / "docs" / "e2_release_candidate_manifest.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
REGISTRY_PATH = ROOT / "tests" / "data_backed_tests.txt"


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _report_describes_this_tree(report: dict) -> bool:
    """Whether an E2 report was produced from the checkout it is sitting in.

    A release-readiness report is a statement about one tree. The release tree
    carries a copy of the report produced in the *source* repository, which
    describes a different and much larger filesystem, so asserting the source
    report's measurements there would be asserting something about somewhere
    else. Counted from the filesystem, the way the report itself was.
    """
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    skip = set(config["inventory"]["skip_directories"])
    total = 0
    for path in ROOT.rglob("*"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & skip or not path.is_file():
            continue
        total += 1
    return report.get("inventory", {}).get("total_files") == total


def _load_report(path: Path, kind: str) -> dict:
    if not path.is_file():
        pytest.skip(f"E2 has not been run in this checkout ({kind} absent)")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def readiness():
    report = _load_report(READINESS_PATH, "readiness report")
    if not _report_describes_this_tree(report):
        pytest.skip(
            "the E2 readiness report describes the tree as it was under Task E2. "
            "It is a superseded historical record, pinned by checksum in "
            "configs/e2r1_source_release.yaml, and must NOT be regenerated: the "
            "current release decision is docs/e2r1_source_release_decision.json"
        )
    return report


@pytest.fixture(scope="module")
def manifest():
    report = _load_report(READINESS_PATH, "readiness report")
    if not _report_describes_this_tree(report):
        pytest.skip("the release manifest describes a different tree than this one")
    return _load_report(MANIFEST_PATH, "release manifest")


@pytest.fixture
def tiny_config():
    """The smallest contract the allowlist machinery accepts."""
    return {
        "release_contract_version": "test_v1",
        "release_candidate_version": "0.0.1",
        "inventory": {
            "large_file_threshold_bytes": 1024,
            "skip_directories": [".git"],
            "categories": {
                "source_code": {"roots": ["src/"], "suffixes": [".py"]},
                "documentation": {"roots": ["docs/"], "suffixes": [".md"]},
            },
        },
        "allowlist": {
            "fail_closed": True,
            "include_globs": ["src/**/*.py", "docs/**/*.md", "README.md"],
            "exclude_globs": ["**/*.pyc", "data/raw/**", "**/*.parquet"],
            "exclude_exemptions": [],
        },
        "locked_test": {
            "outcome_path_fragments": ["locked_test/", "locked_outcome"],
        },
        "package": {
            "prohibited_members": [".parquet", ".pdf", ".xls"],
            "prohibited_member_fragments": ["data/raw/", "locked_test", ".env"],
        },
    }


# ===========================================================================
# 1. The contract, and what it froze
# ===========================================================================

def test_the_contract_parses_and_declares_its_prohibitions(config):
    assert config["task"] == "E2"
    assert config["allowlist"]["fail_closed"] is True
    assert config["allowlist"]["unknown_path_admitted_by_default"] is False
    assert config["allowlist"]["exclude_overrides_include"] is True
    for action in ("commit", "tag", "push", "publish_to_pypi",
                   "create_a_github_release", "read_locked_outcomes"):
        assert action in config["prohibited_actions"]


def test_locked_outcomes_may_not_be_opened_hashed_scanned_packaged_or_copied(config):
    prohibited = config["locked_test"]["prohibited_operations"]
    assert "open_locked_outcome_contents" in prohibited
    assert "hash_locked_outcome_contents" in prohibited
    assert "pass_locked_outcomes_to_a_secret_scanner" in prohibited
    assert "include_locked_outcomes_in_a_package_build" in prohibited
    assert "copy_locked_outcomes_into_the_release_tree" in prohibited
    assert "infer_locked_values_from_size_or_serialization_metadata" in prohibited
    required = config["locked_test"]["required_fields"]
    assert required["locked_test_status"] == "sealed_unopened"
    assert required["locked_paths_opened"] == 0
    assert required["locked_paths_hashed"] == 0
    assert required["locked_paths_packaged"] == 0
    assert required["locked_paths_secret_scanned"] == 0


def test_the_e1_closeout_is_preserved_not_restated(config):
    preserved = config["preserved_closeout"]
    assert preserved["development_program_status"] == (
        "closed_without_supported_incremental_commodity_model"
    )
    assert preserved["operational_model_selected"] is False
    assert preserved["production_deployment_authorized"] is False
    assert preserved["locked_test_status"] == "sealed_unopened"
    assert preserved["fully_real_time_backtest"] is False
    assert preserved["scientific_artifacts_modified"] is False


def test_no_second_dependency_manager_was_introduced():
    DEP.assert_single_dependency_manager(ROOT, "pip_with_setuptools")


def test_e2_recorded_that_the_licence_decision_was_the_owners_to_make(config):
    """A historical assertion, and deliberately only that.

    Task E2 found no licence and refused to choose one. Task E2-R1 later applied
    the owner's decision, so the *current* state of `LICENSE` is E2-R1's to
    assert; this test checks what E2 recorded, which does not change when a
    later task acts on it.
    """
    licensing = config["licensing"]["code"]
    assert licensing["owner_license_decision_required"] is True
    assert licensing["license_chosen_automatically"] is False
    assert licensing["recommendation_permitted"] is True
    assert "MIT" in licensing["recommendation"]


def test_public_download_access_is_not_treated_as_a_redistribution_right(config):
    data = config["licensing"]["data"]
    assert data["public_download_access_implies_redistribution"] is False
    assert data["raw_bytes_included_in_release"] is False
    for family in data["publisher_families"]:
        assert family["raw_bytes_in_release"] is False
        assert family["redistribution_status"] in (
            "unresolved", "likely_permitted_but_not_confirmed_inline",
        )


def test_owner_metadata_is_not_invented(config):
    attribution = config["attribution"]
    assert attribution["owner_metadata_invented"] is False
    assert attribution["citation_cff_created"] is False
    assert not (ROOT / "CITATION.cff").exists()


# ===========================================================================
# 2. The allowlist, as measured
# ===========================================================================

def test_the_allowlist_fails_closed_on_an_unknown_path(tiny_config):
    allow = tiny_config["allowlist"]
    admitted, reason = INV.classify_release(
        "some/path/nobody/considered.bin",
        allow["include_globs"], allow["exclude_globs"],
    )
    assert admitted is False
    assert reason == "fail_closed_unclassified"


def test_exclusion_beats_inclusion(tiny_config):
    allow = tiny_config["allowlist"]
    admitted, reason = INV.classify_release(
        "src/thing.pyc", allow["include_globs"], allow["exclude_globs"]
    )
    assert admitted is False
    assert reason.startswith("excluded_by:")


def test_a_double_star_glob_matches_at_every_depth_including_zero():
    assert INV.glob_match("src/config.py", "src/**/*.py")
    assert INV.glob_match("src/a/b/c.py", "src/**/*.py")
    # A single star must not cross a separator, or docs/*.md would silently
    # admit every nested document.
    assert not INV.glob_match("docs/architecture/log.md", "docs/*.md")


def test_an_exemption_needs_a_literal_path_and_a_matching_include(tiny_config):
    allow = tiny_config["allowlist"]
    include = [*allow["include_globs"], "data/raw/_manifests/*.jsonl"]
    admitted, reason = INV.classify_release(
        "data/raw/_manifests/x.jsonl", include, allow["exclude_globs"],
        exemptions=["data/raw/_manifests/x.jsonl"],
    )
    assert admitted is True
    assert reason.startswith("exempted_from:")
    # Without the include glob the same exemption admits nothing.
    admitted, _ = INV.classify_release(
        "data/raw/_manifests/x.jsonl", allow["include_globs"],
        allow["exclude_globs"], exemptions=["data/raw/_manifests/x.jsonl"],
    )
    assert admitted is False


def test_the_intended_release_contains_no_prohibited_file_type(manifest):
    prohibited = (".parquet", ".xls", ".xlsx", ".pdf", ".zip", ".pkl",
                  ".joblib", ".pyc")
    offenders = [
        row["path"] for row in manifest["files"]
        if row["path"].lower().endswith(prohibited)
    ]
    assert offenders == []


def test_the_intended_release_contains_no_raw_or_generated_directory(manifest):
    allowed_exceptions = {"data/raw/_manifests/", "data/raw/README.md"}
    offenders = [
        row["path"] for row in manifest["files"]
        if row["path"].startswith(("data/raw/", "data/interim/",
                                   "data/processed/", "data/features/",
                                   "data/targets/", "data/model_input/",
                                   "models/"))
        and not any(row["path"].startswith(allowed) for allowed in allowed_exceptions)
        and not row["path"].endswith("/README.md")
    ]
    assert offenders == []


def test_every_release_row_carries_a_resolved_redistribution_status(manifest):
    unresolved = [
        row["path"] for row in manifest["files"]
        if row["redistribution_status"] == "third_party_source_terms_unresolved"
    ]
    assert unresolved == []
    assert all(row["locked_test_dependency"] is False for row in manifest["files"])


def test_the_manifest_excludes_the_documents_that_quote_its_own_checksum(
        manifest, config):
    declared = sorted(config["allowlist"]["self_referential_outputs"])
    assert manifest["self_referential_exclusions"] == declared
    listed = {row["path"] for row in manifest["files"]}
    assert not (listed & set(declared))
    # They ship; they are simply not rows.
    assert all((ROOT / path).is_file() for path in declared)


def test_the_manifest_checksum_is_reproducible(manifest, readiness):
    assert (readiness["release_manifest_checksum"]
            == readiness["release_manifest_checksum_recomputed"])
    assert INV.manifest_checksum(manifest) == readiness["release_manifest_checksum"]


def test_no_timestamp_enters_the_manifest_checksum(manifest):
    assert manifest["acquisition_timestamps_in_checksum"] is False
    assert manifest["generation_timestamps_in_checksum"] is False


# ===========================================================================
# 3. The locked test, still sealed
# ===========================================================================

def test_no_locked_outcome_path_reaches_the_release(config, manifest):
    fragments = config["locked_test"]["outcome_path_fragments"]
    assert INV.locked_paths([row["path"] for row in manifest["files"]],
                            fragments) == []


def test_the_only_locked_documents_on_disk_are_key_only_manifests(config):
    """The reservation documents carry keys, never observations.

    Checked over the JSON structure rather than the serialised text: these
    documents state in prose that they contain no outcome, no prediction and no
    metric, and a substring scan cannot tell a denial from an admission.
    """
    # Matched on whole key tokens, not substrings: `actual_rows` is a count of
    # reserved key rows and `expected_rows` is the number it must equal. Neither
    # is an observation, and a substring rule that rejected them would be
    # objecting to the manifest proving it reserved what it said it reserved.
    outcome_tokens = {"observed", "mae", "rmse", "prediction", "predicted",
                      "score", "residual", "interval", "metric"}

    def offending(node, trail=""):
        if isinstance(node, dict):
            for key, value in node.items():
                tokens = set(re.split(r"[_\W]+", key.lower()))
                if tokens & outcome_tokens and isinstance(value, (int, float)):
                    yield f"{trail}/{key}"
                yield from offending(value, f"{trail}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from offending(value, f"{trail}/{index}")

    for relative in config["locked_test"]["contracts"]:
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        assert list(offending(payload)) == [], relative


def test_git_history_carries_no_locked_outcome(readiness):
    # Measured, not assumed: the repository has no commits, so there is no
    # history in which a locked outcome could ever have been tracked.
    assert readiness["inventory"]["git"]["commit_count"] == 0
    assert readiness["readiness"]["evidence"]["locked_paths_in_history"] == 0
    assert readiness["readiness"]["evidence"]["locked_paths_packaged"] == 0


# ===========================================================================
# 4. Dependencies and the lock
# ===========================================================================

def test_every_third_party_import_is_declared(readiness):
    assert readiness["dependencies"]["undeclared_runtime_imports"] == []


def test_every_declared_dependency_is_used_or_justified(readiness, config):
    unjustified = readiness["dependencies"]["unused_and_unjustified"]
    assert unjustified == []
    for name in readiness["dependencies"]["unused_but_justified"]:
        assert name in config["dependencies"]["justified_dependencies"]


def test_pypdf_is_declared_because_the_source_imports_it():
    declared = DEP.declared_dependencies(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert "pypdf" in declared["runtime"]


def test_python_dotenv_was_removed_because_nothing_imports_it():
    declared = DEP.declared_dependencies(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert "python-dotenv" not in declared["runtime"]
    imports = DEP.scan_imports([ROOT / "src", ROOT / "scripts"],
                               "thai_supply_chain_ews")
    assert "python-dotenv" not in imports


def test_both_locks_exist_and_pin_exact_versions():
    for name in ("requirements.lock.txt", "requirements-dev.lock.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        pins = [line for line in text.splitlines()
                if line.strip() and not line.startswith("#")]
        assert pins, name
        assert all("==" in pin for pin in pins), name
        assert "resolved on:" in text


def test_the_lock_is_declared_platform_scoped_rather_than_universal(config):
    assert config["dependencies"]["cross_platform_lock_guaranteed"] is False
    assert "platform" in (ROOT / "requirements.lock.txt").read_text(
        encoding="utf-8").lower()


def test_the_ci_interpreter_correction_is_recorded_not_backdated(config):
    correction = config["dependencies"]["ci_python_correction"]
    assert correction["changed_after_observation"] is True
    assert correction["ci_python_frozen"] == "3.11"
    assert correction["ci_python_effective"] != correction["ci_python_frozen"]
    # The frozen value is preserved rather than rewritten.
    assert config["ci"]["python_version"] == correction["ci_python_frozen"]
    assert config["ci"]["python_version_effective"] == correction["ci_python_effective"]
    assert correction["declared_floor_verified"] is False


def test_the_effective_ci_interpreter_is_admitted_by_every_pin(readiness, config):
    effective = config["ci"]["python_version_effective"]
    for name, specifier in readiness["dependencies"]["requires_python_by_pin"].items():
        assert DEP.requires_python_admits(specifier or "", effective), name


def test_requires_python_refuses_a_constraint_it_cannot_parse():
    assert DEP.requires_python_admits("", "3.14") is True
    assert DEP.requires_python_admits(">=3.12", "3.11") is False
    # An unreadable constraint is not a satisfied one.
    assert DEP.requires_python_admits("wobble", "3.14") is False


def test_a_lock_comment_edit_does_not_change_the_lock_checksum():
    text = (ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
    assert DEP.lock_checksum(text) == DEP.lock_checksum(
        text.replace("# scope:", "# SCOPE:")
    )


# ===========================================================================
# 5. The clean tree
# ===========================================================================

def test_readiness_was_decided_from_clean_tree_evidence(readiness):
    clean = readiness["clean_tree"]
    assert clean["ok"] is True
    assert clean["tree_unchanged_by_tests"] is True
    assert clean["no_local_data_in_tree"] is True
    assert readiness["readiness"]["ready_because_working_directory_passes_tests"] is False


def test_the_hermetic_count_was_measured_not_quoted(readiness):
    counts = readiness["clean_tree"]["hermetic_tests"]["counts"]
    assert counts["measured_from_command_output"] is True
    assert counts["copied_from_prior_totals"] is False
    assert counts.get("failed", 0) == 0
    assert counts.get("errors", 0) == 0
    assert counts["passed"] > 0


def test_the_data_backed_registry_is_verified_rather_than_trusted(readiness):
    verification = readiness["clean_tree"]["registry_verification"]
    assert verification["verified"] is True
    assert verification["unregistered_failures"] == []
    assert verification["registered_but_did_not_fail"] == []
    assert verification["failures_without_a_missing_input_marker"] == []
    assert verification["tests_weakened_to_obtain_green_ci"] is False


def test_the_tier_gate_reads_the_filesystem_and_not_a_flag():
    """The gate must not be switchable by anything but the data being there.

    Loaded from its path rather than imported as ``tests.conftest``: ``tests``
    is not a package, and an import that only works because pytest happens to
    put the root on the path is a test of the runner rather than of the gate.
    """
    spec = importlib.util.spec_from_file_location(
        "_e2_conftest", ROOT / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert isinstance(module.local_inputs_present(), bool)
    source = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    for escape in ("os.environ", "getenv", "argparse", "--data"):
        assert escape not in source
    # An absent registry is not a defect here: the E2 verification removes it on
    # purpose, to prove that every entry really does fail without it. Failing in
    # that run would make this test the thing the verification tripped over.
    if not REGISTRY_PATH.is_file():
        pytest.skip("registry temporarily removed by the E2 registry verification")
    registered = [
        line.strip()
        for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert registered, "an empty registry would make the tier gate inert"


def test_a_skipped_data_backed_test_is_never_counted_as_passing(readiness, config):
    assert config["test_tiers"]["data_backed"][
        "silently_skipped_and_counted_as_clean"] is False
    counts = readiness["clean_tree"]["hermetic_tests"]["counts"]
    registered = len([
        line for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ])
    assert counts["skipped"] >= registered


def test_the_wheel_install_probe_reports_what_it_could_not_do(readiness):
    probe = readiness["wheel_install_probe"]
    assert probe["install_ok"] is True
    assert probe["import_ok"] is True
    assert probe["imported_from_site_packages"] is True
    # Recorded as a measurement rather than described in prose.
    assert isinstance(probe["project_resources_resolvable"], bool)


# ===========================================================================
# 6. The built package
# ===========================================================================

def test_the_built_distributions_contain_nothing_prohibited(readiness):
    package = readiness["package"]
    for kind in ("wheel", "sdist"):
        assert package[kind]["prohibited_by_suffix"] == [], kind
        assert package[kind]["prohibited_by_fragment"] == [], kind
        assert package[kind]["locked_members"] == [], kind
        assert package[kind]["clean"] is True, kind


def test_two_builds_agree_on_members_and_say_why_bytes_differ(readiness):
    comparison = readiness["package"]["comparison"]
    assert comparison["member_sets_identical"] is True
    assert comparison["archive_member_timestamps_compared"] is False
    assert comparison["archive_timestamp_difference_documented"] is True


def test_the_package_metadata_matches_the_contract(readiness, config):
    metadata = readiness["package"]["metadata"]
    required = config["package"]["required_metadata"]
    assert metadata["name"] == required["name"]
    assert metadata["version"] == required["version"]
    assert metadata["requires_python"] == required["requires_python"]


def test_nothing_was_published(readiness):
    assert readiness["package"]["published"] is False
    decision = readiness["readiness"]
    for key in ("published", "committed", "tagged", "pushed",
                "released_on_github", "uploaded_to_pypi"):
        assert decision[key] is False
    assert all(value is False
               for value in readiness["prohibited_actions_taken"].values())


# ===========================================================================
# 7. Security and privacy
# ===========================================================================

def test_no_credential_reached_the_intended_release(readiness):
    assert readiness["security"]["credential_findings"] == 0
    assert readiness["security"]["credential_exposure_present"] is False
    assert readiness["security"]["secret_values_printed"] is False


def test_every_finding_is_reviewed_or_reported_never_silently_dropped(readiness):
    review = readiness["security"]["review"]
    assert review["unreviewed_count"] == 0
    assert review["review_entries_that_matched_nothing"] == []
    for entry in review["reviewed_and_not_credentials"]:
        assert entry["review"].strip()


def test_a_finding_never_carries_its_value(readiness):
    for finding in readiness["security"]["findings"]:
        assert finding["value_reported"] is False
        assert re.fullmatch(r"[0-9a-f]{0,12}", finding["fingerprint"])
        assert finding["masked"] in ("<not disclosed>",) or finding[
            "masked"].startswith("<")


def test_the_dependency_audit_ran_and_is_not_called_a_guarantee(readiness):
    audits = readiness["security"]["dependency_audits"]
    assert audits
    for audit in audits:
        assert audit["state"] == "ran"
        assert audit["clean_audit_is_a_permanent_guarantee"] is False
        assert audit["silent_upgrade_performed"] is False
        assert audit["vulnerabilities"] == []


def test_the_high_entropy_split_is_a_check_not_a_blanket_dismissal(readiness):
    classification = readiness["security"]["high_entropy_classification"]
    assert classification["declared_content_checksums"] > 0
    assert "enclosing mapping key" in classification["rule"]


# ===========================================================================
# 8. Continuous integration
# ===========================================================================

@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_the_workflow_is_read_only_and_secretless(workflow):
    # PyYAML parses the bare key `on:` as the boolean True.
    assert workflow[True] is not None
    assert workflow["permissions"] == {"contents": "read"}
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "${{ secrets" not in text


def test_every_action_is_pinned_to_a_commit_sha():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses
    for reference in uses:
        _, _, version = reference.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", version), reference


def test_e2_recorded_an_effective_interpreter_different_from_its_frozen_one(config):
    """Also historical. The live workflow is Task E2-R1's to assert."""
    assert config["ci"]["python_version"] == "3.11"
    assert config["ci"]["python_version_effective"] != config["ci"]["python_version"]


def test_every_job_and_step_has_a_timeout(workflow):
    for job in workflow["jobs"].values():
        assert job.get("timeout-minutes")
        for step in job["steps"]:
            assert step.get("timeout-minutes"), step.get("name")


def test_the_cache_key_is_derived_from_the_lock_contents():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "hashFiles('requirements.lock.txt', 'requirements-dev.lock.txt')" in text


def test_ci_downloads_no_official_dataset_and_reads_no_locked_artifact():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for forbidden in ("oie.go.th", "worldbank.org", "eppo.go.th", "nesdc.go.th",
                      "curl ", "wget "):
        assert forbidden not in text
    # The workflow may name the locked-path contract it enforces; what it may
    # not do is reference a path inside one.
    assert not re.search(r"[\"'][^\"'\s]*locked_test/[^\"'\s]*[\"']", text)
    assert "outcome_path_fragments" in text, (
        "the package audit must be handed the locked-path fragments"
    )


# ===========================================================================
# 9. Synthetic failures. Each plants one defect and requires it to be caught.
# ===========================================================================

def _write(base: Path, relative: str, text: str = "x") -> Path:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_synthetic_01_an_unknown_path_is_excluded_not_admitted(tmp_path, tiny_config):
    _write(tmp_path, "src/pkg/module.py", "print(1)\n")
    _write(tmp_path, "mystery/thing.bin")
    inventory = INV.build_inventory(tmp_path, tiny_config)
    admitted = {r.path for r in inventory["records"] if r.in_release}
    assert "mystery/thing.bin" not in admitted
    assert "mystery/thing.bin" in inventory["unclassified_paths"]
    assert inventory["fail_closed_exclusions"] == 1


def test_synthetic_02_a_locked_outcome_file_is_refused_by_the_release(tmp_path,
                                                                     tiny_config):
    _write(tmp_path, "docs/locked_test/outcomes.md", "# x\n")
    inventory = INV.build_inventory(tmp_path, tiny_config)
    record = next(r for r in inventory["records"]
                  if "locked_test" in r.path)
    assert record.in_release is False
    assert record.reason == "locked_test_path_excluded_by_name"
    # And its size was never read.
    assert record.size_bytes == 0


def test_synthetic_03_hashing_a_locked_path_raises(tiny_config):
    with pytest.raises(INV.InventoryError, match="never opened, hashed"):
        INV.assert_no_locked_path(
            ["docs/locked_test/outcomes.json"],
            tiny_config["locked_test"]["outcome_path_fragments"],
            "manifest hashing",
        )


def test_synthetic_04_copying_a_locked_path_into_the_tree_raises(tmp_path,
                                                                 tiny_config):
    source = tmp_path / "source"
    _write(source, "docs/locked_outcome.json", "{}")
    with pytest.raises(CT.CleanTreeError, match="locked-outcome path"):
        CT.materialise(source, tmp_path / "tree", ["docs/locked_outcome.json"],
                       tiny_config["locked_test"]["outcome_path_fragments"])


def test_synthetic_05_scanning_a_locked_path_raises(tiny_config):
    with pytest.raises(SEC.SecurityError, match="reached the scan set"):
        SEC.scan_paths(Path("."), ["docs/locked_test/x.json"],
                       tiny_config["locked_test"]["outcome_path_fragments"])


def test_synthetic_06_a_locked_member_in_a_wheel_raises(tmp_path, tiny_config):
    archive = tmp_path / "pkg-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pkg/__init__.py", "")
        handle.writestr("pkg/locked_test/outcomes.json", "{}")
    with pytest.raises(PKG.PackageAuditError, match="locked-outcome member"):
        PKG.audit_members(archive, tiny_config,
                          tiny_config["locked_test"]["outcome_path_fragments"])


def test_synthetic_07_a_raw_download_may_not_be_copied_into_the_tree(tmp_path,
                                                                    tiny_config):
    source = tmp_path / "source"
    _write(source, "data/raw/OIE_MPI/2026-08/index.xlsx", "binary")
    with pytest.raises(CT.CleanTreeError, match="raw download or generated"):
        CT.materialise(source, tmp_path / "tree",
                       ["data/raw/OIE_MPI/2026-08/index.xlsx"],
                       tiny_config["locked_test"]["outcome_path_fragments"])


def test_synthetic_08_a_virtual_environment_may_not_be_copied_into_the_tree(
        tmp_path, tiny_config):
    source = tmp_path / "source"
    _write(source, ".venv/Lib/site-packages/thing.py", "")
    with pytest.raises(CT.CleanTreeError, match="local environment"):
        CT.materialise(source, tmp_path / "tree",
                       [".venv/Lib/site-packages/thing.py"],
                       tiny_config["locked_test"]["outcome_path_fragments"])


def test_synthetic_09_a_generated_parquet_never_reaches_the_release(tmp_path,
                                                                    tiny_config):
    _write(tmp_path, "data/features/c4_canonical_long.parquet", "PAR1")
    inventory = INV.build_inventory(tmp_path, tiny_config)
    record = next(r for r in inventory["records"] if r.path.endswith(".parquet"))
    assert record.in_release is False


def test_synthetic_10_a_wildcard_exemption_is_refused(tiny_config):
    allow = tiny_config["allowlist"]
    with pytest.raises(INV.InventoryError, match="literal paths"):
        INV.classify_release("data/raw/anything.jsonl",
                             [*allow["include_globs"], "data/raw/*.jsonl"],
                             allow["exclude_globs"],
                             exemptions=["data/raw/*.jsonl",
                                         "data/raw/anything.jsonl"])


def test_synthetic_11_a_planted_api_key_is_found_and_never_echoed():
    # Assembled at run time. A well-formed key written as a literal here would
    # be found by the scanner in this very file, and a test fixture is not a
    # credential — but a file containing one is indistinguishable from a file
    # that leaked one, which is the whole reason the rule exists.
    planted = "AKIA" + "Q7WOULDNTYOULIKE"
    findings = SEC.scan_text(f"aws_key = {planted}\n", "fake.py")
    assert findings
    assert all(finding["value_reported"] is False for finding in findings)
    rendered = json.dumps(findings)
    assert planted not in rendered


def test_synthetic_12_a_report_that_leaks_a_value_is_refused():
    # Named `planted`, not `secret`: a keyword scanner matching its own test
    # fixture is a finding about the test, not about the release.
    planted = "hunter" + "2hunter2"
    with pytest.raises(SEC.SecurityError, match="appear verbatim"):
        SEC.assert_no_secret_values_printed(f"the value is {planted}", [planted])


def test_synthetic_13_an_absent_scanner_is_not_recorded_as_clean(tmp_path):
    result = SEC.run_detect_secrets(tmp_path, [], tmp_path / "no-such-python")
    assert result["state"] == "not_run"
    assert result["counted_as_clean"] is False
    audit = SEC.run_pip_audit(tmp_path / "lock.txt", None, runtime_or_dev="runtime")
    assert audit["state"] == "not_run"
    assert audit["counted_as_clean"] is False


def test_synthetic_14_a_published_checksum_is_separated_only_when_named(tmp_path):
    digest = hashlib.sha256(b"x").hexdigest()
    _write(tmp_path, "named.json",
           f'{{\n  "byte_checksums": {{\n    "a.parquet": "{digest}"\n  }}\n}}\n')
    _write(tmp_path, "unnamed.json",
           f'{{\n  "documents": [\n    "{digest}"\n  ]\n}}\n')
    named = SEC.classify_entropy_findings(tmp_path, [
        {"family": "Hex High Entropy String", "path": "named.json", "line": 3,
         "fingerprint": "a" * 12},
    ])
    unnamed = SEC.classify_entropy_findings(tmp_path, [
        {"family": "Hex High Entropy String", "path": "unnamed.json", "line": 3,
         "fingerprint": "b" * 12},
    ])
    assert named["declared_content_checksums"] == 1
    assert unnamed["unexplained_count"] == 1


def test_synthetic_15_an_unreviewed_finding_stays_unreviewed():
    findings = [{"family": "Secret Keyword", "path": "a.yaml", "line": 3,
                 "fingerprint": "abc123abc123"}]
    result = SEC.classify_reviewed(findings, [])
    assert result["unreviewed_count"] == 1
    assert result["reviewed_count"] == 0


def test_synthetic_16_a_review_entry_that_matches_nothing_is_reported():
    result = SEC.classify_reviewed([], [{"path": "gone.yaml",
                                         "family": "Secret Keyword",
                                         "fingerprint": "deadbeefdead",
                                         "reason": "it moved"}])
    assert result["review_entries_that_matched_nothing"] == [
        "gone.yaml::Secret Keyword::deadbeefdead"
    ]


def test_synthetic_17_a_prohibited_member_makes_the_package_audit_fail(tmp_path,
                                                                       tiny_config):
    archive = tmp_path / "pkg-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pkg/__init__.py", "")
        handle.writestr("pkg/data/table.parquet", "PAR1")
    report = PKG.audit_members(archive, tiny_config,
                               tiny_config["locked_test"]["outcome_path_fragments"])
    assert report["clean"] is False
    assert report["prohibited_by_suffix"] == ["pkg/data/table.parquet"]


def test_synthetic_18_a_missing_pytest_summary_is_unmeasured_not_zero():
    with pytest.raises(CT.CleanTreeError, match="no parseable summary"):
        CT.parse_pytest_counts("collecting ...\ninterrupted\n")


def test_synthetic_19_a_mutating_test_run_is_detected(tmp_path):
    _write(tmp_path, "src/a.py", "print(1)\n")
    before, _ = CT.tree_checksum(tmp_path)
    _write(tmp_path, "src/a.py", "print(2)\n")
    after, _ = CT.tree_checksum(tmp_path)
    assert before != after


def test_synthetic_20_readiness_without_clean_tree_evidence_is_refused():
    with pytest.raises(RDY.ReadinessError, match="without clean-tree evidence"):
        RDY.decide({"credential_exposure_present": False}, [])


def test_synthetic_21_each_blocker_can_be_made_live_on_its_own():
    clean = {
        "credential_exposure_present": False,
        "locked_paths_in_release": 0, "locked_paths_in_history": 0,
        "locked_paths_packaged": 0,
        "owner_license_decision_required": False,
        "clean_tree_install_ok": True, "clean_tree_hermetic_tests_ok": True,
        "clean_tree_package_build_ok": True,
        "clean_tree_unchanged_by_tests": True,
        "package_contents_clean": True,
        "unresolved_redistribution_included_bytes": 0,
        "unaccepted_vulnerabilities": 0,
    }
    assert RDY.decide(clean, [])["status"] == "release_candidate_ready"
    for key, bad in (
        ("credential_exposure_present", True),
        ("locked_paths_in_release", 1),
        ("owner_license_decision_required", True),
        ("clean_tree_install_ok", False),
        ("clean_tree_hermetic_tests_ok", False),
        ("package_contents_clean", False),
        ("unresolved_redistribution_included_bytes", 1),
        ("unaccepted_vulnerabilities", 1),
        ("clean_tree_unchanged_by_tests", False),
    ):
        decision = RDY.decide({**clean, key: bad}, [])
        assert decision["status"] == "release_candidate_blocked", key
        assert len(decision["blockers"]) == 1, key


def test_synthetic_22_a_limitation_never_upgrades_a_blocked_candidate():
    blocked = {
        "credential_exposure_present": False,
        "locked_paths_in_release": 0, "locked_paths_in_history": 0,
        "locked_paths_packaged": 0,
        "owner_license_decision_required": True,
        "clean_tree_install_ok": True, "clean_tree_hermetic_tests_ok": True,
        "clean_tree_package_build_ok": True,
        "clean_tree_unchanged_by_tests": True,
        "package_contents_clean": True,
        "unresolved_redistribution_included_bytes": 0,
        "unaccepted_vulnerabilities": 0,
    }
    decision = RDY.decide(blocked, [{"id": "x", "statement": "y",
                                     "why_not_blocking": "z"}])
    assert decision["status"] == "release_candidate_blocked"
    assert decision["documented_nonblocking_limitations"]


def test_synthetic_23_asserting_an_unchosen_licence_is_refused():
    with pytest.raises(RDY.ReadinessError, match="may not be asserted"):
        RDY.assert_no_license_asserted("This project is licensed under the MIT "
                                       "License.")
    # The rule may name itself: quoted and backticked spans are stripped.
    RDY.assert_no_license_asserted(
        'The report may not say "licensed under the MIT License" because the '
        "owner has not chosen one."
    )


def test_synthetic_24_inferring_redistribution_from_public_access_is_refused():
    with pytest.raises(RDY.ReadinessError, match="does not grant redistribution"):
        RDY.assert_no_redistribution_inference(
            "The workbook is publicly available so we can redistribute it."
        )


def test_synthetic_25_a_permanent_security_guarantee_is_refused():
    with pytest.raises(RDY.ReadinessError, match="one advisory database"):
        RDY.assert_no_permanent_security_guarantee(
            "The pinned set is guaranteed secure."
        )
    # A denial of the same claim must pass.
    RDY.assert_no_permanent_security_guarantee(
        "The pinned set is not guaranteed secure, and no scan can make it so."
    )


def test_synthetic_26_invented_owner_metadata_is_refused():
    with pytest.raises(RDY.ReadinessError, match="owner metadata"):
        RDY.assert_no_invented_owner_metadata(
            # A reserved example-domain address: it must still be refused as owner
            # metadata, while not being a scannable address in this repository.
            "Contact the author at nobody@example.com",
            permitted_placeholders=(),
        )
    with pytest.raises(RDY.ReadinessError, match="owner metadata"):
        RDY.assert_no_invented_owner_metadata(
            "ORCID 0000-0002-1825-0097", permitted_placeholders=()
        )


def test_synthetic_27_a_competing_dependency_manager_is_refused(tmp_path):
    (tmp_path / "poetry.lock").write_text("", encoding="utf-8")
    with pytest.raises(DEP.DependencyError, match="second dependency manager"):
        DEP.assert_single_dependency_manager(tmp_path, "pip_with_setuptools")


def test_synthetic_28_an_unpinnable_dependency_refuses_to_become_a_lock():
    with pytest.raises(DEP.DependencyError,
                       match="not installed in the resolving environment"):
        DEP.render_lock({"ghost": {"version": None, "requires_python": "",
                                   "installed": False}}, ["header"])


def test_synthetic_29_an_undeclared_import_fails_reconciliation():
    result = DEP.reconcile(
        {"requests": {"import_name": "requests", "sites": ["a.py:1"]}},
        {"runtime": set(), "development": set()},
        {},
    )
    assert result["undeclared_runtime_imports"] == ["requests"]
    assert result["reconciled"] is False


def test_synthetic_30_an_unused_declaration_fails_unless_justified():
    unjustified = DEP.reconcile({}, {"runtime": {"leftover"},
                                     "development": set()}, {})
    assert unjustified["unused_and_unjustified"] == ["leftover"]
    assert unjustified["reconciled"] is False
    justified = DEP.reconcile({}, {"runtime": {"pyarrow"}, "development": set()},
                              {"pyarrow": "reached through the pandas engine"})
    assert justified["unused_and_unjustified"] == []
    assert justified["reconciled"] is True


def test_synthetic_31_building_over_a_non_empty_tree_is_refused(tmp_path,
                                                                tiny_config):
    destination = tmp_path / "tree"
    _write(destination, "leftover.txt")
    with pytest.raises(CT.CleanTreeError, match="not empty"):
        CT.materialise(tmp_path, destination, [],
                       tiny_config["locked_test"]["outcome_path_fragments"])


def test_synthetic_32_an_import_inside_a_docstring_is_not_an_import(tmp_path):
    _write(tmp_path, "m.py",
           '"""This module would import requests if it needed it.\n\n'
           'import requests\n"""\nimport json\n')
    found = DEP.scan_imports([tmp_path], "thai_supply_chain_ews")
    assert "requests" not in found


# ===========================================================================
# 10. The runner itself
# ===========================================================================

def test_the_runner_takes_no_arguments_and_offers_no_escape_hatch():
    source = (ROOT / "scripts" / "run_e2_release_preparation.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    assert not main.args.args and not main.args.kwonlyargs
    for escape in ("argparse", "sys.argv[1", "os.environ", "getenv",
                   "--publish", "--force", "--skip"):
        assert escape not in source


def test_the_runner_never_calls_a_publishing_command():
    """No publishing command is ever handed to a subprocess.

    Checked over the argument lists at the ``subprocess.run`` call sites rather
    than over the file's text. The runner's docstring promises it does not
    upload to PyPI and its report states that nothing was committed, tagged or
    pushed; a substring scan cannot tell those sentences from a call, and would
    force the runner to stop saying what it refuses to do.
    """
    tree = ast.parse(
        (ROOT / "scripts" / "run_e2_release_preparation.py").read_text(
            encoding="utf-8")
    )
    argv_literals, call_sites = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = getattr(target, "attr", getattr(target, "id", ""))
        if name != "run":
            continue
        call_sites += 1
        for argument in node.args:
            if isinstance(argument, (ast.List, ast.Tuple)):
                argv_literals.extend(
                    element.value.lower() for element in argument.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                )
    assert call_sites, "no subprocess call site was found to inspect"
    for forbidden in ("commit", "tag", "push", "twine", "pypi", "upload",
                      "release"):
        offenders = [text for text in argv_literals if forbidden in text]
        assert offenders == [], (forbidden, offenders)
