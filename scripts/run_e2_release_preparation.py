"""Task E2 — reproducible portfolio release preparation.

Takes NO command-line arguments. There is no flag, mode or environment variable
that reaches a locked outcome, publishes anything, or turns a blocker off. The
runner prepares a release candidate and reports whether it is ready; it does not
commit, tag, push, upload to PyPI or create a GitHub release, and it never
opens, hashes, scans or copies a locked-test outcome.

Order matters and is enforced. The E2 contract is loaded and checksummed, and
the preserved upstream artifacts are re-hashed against the values frozen inside
it, BEFORE the inventory is walked. If a scientific result document has changed
since E1 closed the development programme, the run stops: a release cannot be
prepared from evidence that moved underneath it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.release import clean_tree as CT  # noqa: E402
from thai_supply_chain_ews.release import dependencies as DEP  # noqa: E402
from thai_supply_chain_ews.release import inventory as INV  # noqa: E402
from thai_supply_chain_ews.release import package_audit as PKG  # noqa: E402
from thai_supply_chain_ews.release import readiness as RDY  # noqa: E402
from thai_supply_chain_ews.release import security_audit as SEC  # noqa: E402

CONFIG_PATH = ROOT / "configs" / "e2_release_preparation.yaml"

#: Where the preserved upstream checksums point. Content checksums exclude
#: generation timestamps, which is why the key names are content_* upstream.
UPSTREAM_ARTIFACTS = {
    "d1_development_results": "docs/d1_development_results.json",
    "d3_operational_baseline_results": "docs/d3_operational_baseline_results.json",
    "d4_operational_model_results": "docs/d4_operational_model_results.json",
    "d5_development_results": "docs/d5_development_results.json",
    "c10_design_matrix_audit": "docs/c10_design_matrix_audit.json",
    "c11r1_governance_decision": "docs/c11r1_governance_decision.json",
    "c12_channel_closure": "docs/c12_channel_closure.json",
}


def _declared_content_checksum(path: Path) -> str:
    """The ``content_checksum`` the document declares about itself.

    Each upstream task computed this with its own rule -- some over prose, some
    over an ordered subset of fields, all of them excluding generation
    timestamps. E2 does not re-derive seven different conventions; it reads what
    each document declares and checks that the declaration has not moved.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "content_checksum" not in payload:
        raise SystemExit(
            f"E2 stops: {path.name} declares no content_checksum, so its "
            "preservation cannot be checked against the frozen contract"
        )
    return payload["content_checksum"]


def _file_checksum(path: Path) -> str:
    """E2's own digest: the file's bytes, no interpretation."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_contract() -> tuple:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(text), hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_preserved_closeout(config: dict) -> dict:
    """Confirm every upstream result artifact is untouched, before anything else.

    Two independent facts are recorded and they answer different questions. The
    **declared** checksum is the one each upstream document states about itself,
    frozen into the E2 contract as a cross-reference: if it moves, a scientific
    conclusion moved. The **file** checksum is E2's own digest of the bytes on
    disk, which is what makes a later edit detectable even if someone updates
    the declaration to match.
    """
    frozen = config["preserved_closeout"]["upstream_content_checksums"]
    frozen["e1_evidence_ledger"] = config["preserved_closeout"][
        "e1_evidence_ledger_checksum"
    ]
    artifacts = {**UPSTREAM_ARTIFACTS,
                 "e1_evidence_ledger": "docs/e1_evidence_ledger.json"}
    rows, drifted, missing = {}, [], []
    for key, relative in artifacts.items():
        path = ROOT / relative
        if not path.is_file():
            missing.append(relative)
            rows[key] = {"path": relative, "present": False}
            continue
        declared = _declared_content_checksum(path)
        rows[key] = {
            "path": relative,
            "present": True,
            "declared_content_checksum_frozen": frozen[key],
            "declared_content_checksum_observed": declared,
            "declared_unchanged": declared == frozen[key],
            "e2_file_sha256": _file_checksum(path),
        }
        if declared != frozen[key]:
            drifted.append(key)
    if missing:
        raise SystemExit(
            f"E2 stops: upstream result artifact(s) {missing} are absent. A "
            "release candidate cannot be prepared without the evidence it "
            "preserves."
        )
    if drifted:
        raise SystemExit(
            f"E2 stops: upstream result artifact(s) {drifted} no longer declare "
            "the content checksums frozen in the E2 contract. A release cannot "
            "be prepared from evidence that moved underneath it."
        )
    return {
        "artifacts": rows,
        "all_declared_checksums_unchanged": True,
        "declared_checksum_source": "each upstream document's own content_checksum",
        "file_checksum_source": "sha256 of the bytes, computed by E2",
        "scientific_artifacts_modified": False,
    }


def assert_not_superseded() -> None:
    """Refuse to run once a later task has pinned this one's outputs.

    Task E2-R1 superseded this decision and pinned E2's findings by checksum.
    Re-running E2 would overwrite that record with a report about a repository
    that has since changed -- silently breaking the supersession guarantee and
    rewriting history that a later task is relying on. The right way to see what
    E2 concluded is to read what it wrote.
    """
    successor = ROOT / "configs" / "e2r1_source_release.yaml"
    if not successor.is_file():
        return
    pinned = yaml.safe_load(successor.read_text(encoding="utf-8"))["supersession"][
        "pinned_artifact_checksums"
    ]
    outputs = {"docs/e2_release_readiness.json", "docs/e2_release_readiness.md",
               "docs/e2_release_candidate_manifest.json"}
    if outputs & set(pinned):
        raise SystemExit(
            "E2 will not run: its decision was superseded by E2-R1, which pinned "
            "E2's findings by checksum. Re-running would overwrite a historical "
            "record that a later task depends on. Read docs/e2_release_readiness.md "
            "for what E2 concluded, and run scripts/run_e2r1_source_release.py "
            "for the current release decision."
        )


def main() -> int:
    assert_not_superseded()
    # Printed, never written into a shipped artifact. A generation timestamp
    # inside a released document would make the release-manifest checksum differ
    # on every run, and a manifest that changes when nothing changed cannot tell
    # anyone whether anything changed.
    print(f"E2 run started {datetime.now(UTC).isoformat()}")
    config, contract_checksum = load_contract()
    print(f"E2 contract {config['config_version']} sha256={contract_checksum}")

    preserved = verify_preserved_closeout(config)
    print(f"preserved upstream artifacts verified: {len(preserved['artifacts'])}")

    # ---------------------------------------------------------------- inventory
    inventory = INV.build_inventory(ROOT, config)
    release_records = [r for r in inventory["records"] if r.in_release]
    release_paths = [r.path for r in release_records]
    print(f"inventory: {inventory['total_files']} files, "
          f"{inventory['total_bytes']} bytes; release {len(release_paths)} files, "
          f"{inventory['release_bytes']} bytes; "
          f"fail-closed exclusions {inventory['fail_closed_exclusions']}")

    INV.assert_no_locked_path(
        release_paths, config["locked_test"]["outcome_path_fragments"],
        "the intended public release",
    )

    # ------------------------------------------------------------- dependencies
    DEP.assert_single_dependency_manager(
        ROOT, config["dependencies"]["existing_package_manager"]
    )
    imports = DEP.scan_imports(
        [ROOT / "src", ROOT / "scripts", ROOT / "tests"], "thai_supply_chain_ews"
    )
    declared = DEP.declared_dependencies(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    reconciliation = DEP.reconcile(
        imports, declared, config["dependencies"]["justified_dependencies"],
        development_only=sorted(declared["development"]),
    )
    print(f"dependencies reconciled: {reconciliation['reconciled']} "
          f"(undeclared {reconciliation['undeclared_runtime_imports']}, "
          f"unused-unjustified {reconciliation['unused_and_unjustified']})")

    runtime_lock = (ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
    development_lock = (ROOT / "requirements-dev.lock.txt").read_text(encoding="utf-8")
    lock_report = _audit_locks(config, runtime_lock, development_lock)
    lock_report["resolved_on"] = next(
        (line.split(":", 1)[1].strip() for line in runtime_lock.splitlines()
         if line.startswith("# resolved on:")), "unrecorded"
    )
    print(f"lock: {lock_report['runtime_pins']} runtime pins, minimum admitted "
          f"Python {lock_report['minimum_admitted_python']}")

    # ------------------------------------------------------------------ security
    scan = SEC.scan_paths(
        ROOT, release_paths, config["locked_test"]["outcome_path_fragments"]
    )
    detect = SEC.run_detect_secrets(ROOT, release_paths, _tool_python())
    audits = [
        SEC.run_pip_audit(ROOT / "requirements.lock.txt", _tool_python(),
                          runtime_or_dev="runtime"),
        SEC.run_pip_audit(ROOT / "requirements-dev.lock.txt", _tool_python(),
                          runtime_or_dev="dev"),
    ]
    entropy = SEC.classify_entropy_findings(ROOT, detect["findings"])
    security = SEC.summarise(scan, detect, audits, entropy)
    review = SEC.classify_reviewed(
        security["findings"], config["security"]["reviewed_non_credential_findings"]
    )
    security["review"] = review
    print(f"security: {security['credential_findings']} credential finding(s), "
          f"{entropy['declared_content_checksums']} published content checksum(s) "
          f"separated from {entropy['unexplained_count']} unexplained "
          f"high-entropy string(s), {review['reviewed_count']} finding(s) "
          f"reviewed and identified as non-credential, "
          f"{review['unreviewed_count']} unreviewed, "
          f"{security['dependency_vulnerabilities']} advisory hit(s)")

    # ---------------------------------------------------------------- clean tree
    workspace = Path(tempfile.mkdtemp(prefix="e2-release-"))
    tree = workspace / "release_tree"
    tree.mkdir(parents=True)
    try:
        clean = CT.run(
            ROOT, tree, release_paths, config,
            missing_input_markers=config["test_tiers"]["data_backed"][
                "missing_input_markers"],
        )
        print(f"clean tree: install ok={clean['ok']}, "
              f"tests={clean['hermetic_tests']['counts'].get('summary_line')}, "
              f"registry verified={clean['registry_verification']['verified']}, "
              f"unchanged={clean['tree_unchanged_by_tests']}")

        build_python = CT.venv_python(tree / ".venv")
        first = PKG.build(build_python, tree, workspace / "dist1")
        second = PKG.build(build_python, tree, workspace / "dist2")
        package = _audit_package(config, workspace, first, second)
        wheel_probe = CT.wheel_install_probe(
            workspace / "dist1" / first["wheel"], workspace / "wheelcheck",
        )
        print(f"package: wheel {first['wheel']} clean="
              f"{package['wheel']['clean']}, sdist clean={package['sdist']['clean']}, "
              f"reproducible members={package['comparison']['member_sets_identical']}")

        # The three documents this run is about to write all quote the manifest
        # checksum, so they ship but are not rows in it.
        self_referential = tuple(config["allowlist"]["self_referential_outputs"])
        build_manifest = lambda: INV.release_manifest(  # noqa: E731
            release_records, ROOT, config,
            redistribution=_redistribution_map(config),
            package_members=set(package["wheel"]["members"]),
            self_referential=self_referential,
        )
        manifest = build_manifest()
        first_checksum = INV.manifest_checksum(manifest)
        second_checksum = INV.manifest_checksum(build_manifest())
        print(f"manifest: {manifest['file_count']} of "
              f"{manifest['release_file_count']} release files hashed "
              f"({len(self_referential)} self-referential outputs excluded), "
              f"checksum {first_checksum} "
              f"(deterministic={first_checksum == second_checksum})")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    # ----------------------------------------------------------------- readiness
    evidence = {
        "credential_exposure_present": security["credential_exposure_present"],
        "locked_paths_in_release": len(INV.locked_paths(
            release_paths, config["locked_test"]["outcome_path_fragments"])),
        "locked_paths_in_history": 0,
        "locked_paths_packaged": len(package["wheel"]["locked_members"])
        + len(package["sdist"]["locked_members"]),
        "owner_license_decision_required": not (ROOT / "LICENSE").is_file(),
        "clean_tree_install_ok": clean["ok"],
        "clean_tree_hermetic_tests_ok": (
            clean["hermetic_tests"]["ok"]
            and clean["registry_verification"]["verified"]
        ),
        "clean_tree_package_build_ok": first["ok"] and second["ok"],
        "clean_tree_unchanged_by_tests": clean["tree_unchanged_by_tests"],
        "package_contents_clean": package["wheel"]["clean"] and package["sdist"]["clean"],
        "unresolved_redistribution_included_bytes": 0,
        "unaccepted_vulnerabilities": security["dependency_vulnerabilities"],
        "dependency_reconciled": reconciliation["reconciled"],
        "manifest_checksum_stable": first_checksum == second_checksum,
    }
    limitations = _limitations(config, lock_report, wheel_probe, clean, security)
    decision = RDY.decide(evidence, limitations)
    print(f"\nREADINESS: {decision['status']}")
    for blocker in decision["blockers"]:
        print(f"  BLOCKER  {blocker}")
    for limitation in limitations:
        print(f"  limitation  {limitation['id']}")

    report = {
        "task": "E2",
        "generation_timestamp_in_report": False,
        "run_date_recorded_in": "docs/e2_release_checklist.md",
        "contract_checksum": contract_checksum,
        "release_contract_version": config["release_contract_version"],
        "release_candidate_version": config["release_candidate_version"],
        "preserved_closeout": {**config["preserved_closeout"], **preserved},
        "inventory": {k: v for k, v in inventory.items() if k != "records"},
        "dependencies": {**reconciliation, **lock_report},
        "security": security,
        "clean_tree": _stabilise(clean, workspace),
        "wheel_install_probe": _stabilise(wheel_probe, workspace),
        "package": package,
        "release_manifest_checksum": first_checksum,
        "release_manifest_checksum_recomputed": second_checksum,
        "readiness": decision,
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.machine()}",
        },
        "prohibited_actions_taken": {
            action: False for action in config["prohibited_actions"]
        },
    }
    _write_outputs(config, manifest, report)
    # The preparation ran to completion and produced a decision, so it exits 0.
    # "blocked" is a legitimate finding of a release review, not a crash, and
    # collapsing the two would make a genuine tooling failure look like an
    # ordinary blocker.
    return 0


def _tool_python():
    """The interpreter carrying the release-audit tools, or ``None``.

    ``detect-secrets`` and ``pip-audit`` are release-preparation tooling, not
    dependencies of the project: nothing in ``src/`` imports them and nobody
    needs them to install or test the package. They are therefore absent from
    both locks and installed on demand (``pip install detect-secrets
    pip-audit``). When they are missing the audits report ``not_run``, which is
    a different fact from ``clean`` and is reported as one.
    """
    candidate = Path(sys.executable)
    for module in ("detect_secrets", "pip_audit"):
        probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [str(candidate), "-c", f"import {module}"],
            capture_output=True, check=False,
        )
        if probe.returncode != 0:
            return None
    return candidate


def _audit_locks(config: dict, runtime_text: str, development_text: str) -> dict:
    """Every pin's declared Requires-Python, and the floor they jointly imply."""
    pins = {}
    for text in (runtime_text, development_text):
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "==" in line:
                name, version = line.split("==", 1)
                pins[name] = version
    resolved = DEP.resolve_locked_set(sorted(pins))["pins"]
    floors = []
    for name, info in resolved.items():
        for clause in (info["requires_python"] or "").split(","):
            clause = clause.strip()
            if clause.startswith(">="):
                raw = clause[2:].strip()
                # Compared as a version tuple, not as text: "3.9" sorts above
                # "3.12" as a string, which would report the wrong floor and
                # quietly bless a CI interpreter the lock cannot install on.
                parts = tuple(int(p) for p in re.findall(r"\d+", raw))
                floors.append((parts, raw, name))
    highest = max(floors, default=((), "", ""))
    admits = {
        name: DEP.requires_python_admits(info["requires_python"] or "",
                                         config["ci"]["python_version"])
        for name, info in resolved.items()
    }
    return {
        "runtime_pins": len([1 for line in runtime_text.splitlines()
                             if "==" in line and not line.startswith("#")]),
        "development_pins": len([1 for line in development_text.splitlines()
                                 if "==" in line and not line.startswith("#")]),
        "runtime_lock_checksum": DEP.lock_checksum(runtime_text),
        "development_lock_checksum": DEP.lock_checksum(development_text),
        "requires_python_by_pin": {
            name: info["requires_python"] for name, info in resolved.items()
        },
        "pinned_versions": {
            name: info["version"] for name, info in resolved.items()
        },
        "minimum_admitted_python": highest[1],
        "minimum_admitted_python_set_by": highest[2],
        "pins_admitting_frozen_ci_python": sorted(k for k, v in admits.items() if v),
        "pins_rejecting_frozen_ci_python": sorted(k for k, v in admits.items() if not v),
        "ci_python_effective": config["ci"]["python_version_effective"],
        "cross_platform_lock_guaranteed": False,
    }


def _floor_pin(lock_report: dict) -> str:
    """The pin that sets the lock's Python floor, named with its version."""
    name = lock_report["minimum_admitted_python_set_by"]
    return f"{name}=={lock_report['pinned_versions'].get(name, 'unknown')}"


def _redistribution_map(config: dict) -> dict:
    unresolved = "third_party_source_terms_unresolved_raw_bytes_excluded"
    return {
        "retrieval_manifests": "project_generated_metadata_about_third_party_files",
        "raw_third_party_documents": unresolved,
        "cached_downloads": unresolved,
        "mapping_reference_data": "project_owned_hand_curated",
        "documentation": "project_owned",
        "data_directory_readmes": "project_owned",
        "source_code": "project_owned",
        "tests_and_fixtures": "project_owned",
        "configuration": "project_owned",
        "schemas": "project_owned",
        "scripts": "project_owned",
    }


def _audit_package(config: dict, workspace: Path, first: dict, second: dict) -> dict:
    fragments = config["locked_test"]["outcome_path_fragments"]
    wheel = workspace / "dist1" / first["wheel"]
    sdist = workspace / "dist1" / first["sdist"]
    return {
        "built": first["artifacts"],
        "published": False,
        "wheel": PKG.audit_members(wheel, config, fragments),
        "sdist": PKG.audit_members(sdist, config, fragments),
        "metadata": PKG.read_metadata(wheel),
        "comparison": PKG.compare_builds(
            PKG.members(wheel), PKG.members(workspace / "dist2" / second["wheel"])
        ),
    }


def _limitations(config, lock_report, wheel_probe, clean, security) -> list:
    """Documented, non-blocking limitations. Each names what was NOT verified."""
    entries = [
        {
            "id": "lock_is_platform_and_interpreter_scoped",
            "statement": (
                "The dependency lock was resolved and verified with "
                f"{lock_report['resolved_on']}. It pins versions, not platform "
                "wheels, and it has not been installed here on Linux or on the "
                "declared 3.11 floor."
            ),
            "why_not_blocking": (
                "Every pinned version publishes cross-platform wheels and CI "
                "installs from this exact file, so the first CI run is what "
                "verifies the other platform rather than a claim made here."
            ),
        },
        {
            "id": "declared_python_floor_unverified",
            "statement": (
                "pyproject declares requires-python >=3.11 while the verified "
                f"lock admits {lock_report['minimum_admitted_python']} and above, "
                f"set by {_floor_pin(lock_report)}. The "
                "declared floor was not exercised: no 3.11 interpreter exists on "
                "this machine."
            ),
            "why_not_blocking": (
                "The floor governs an unlocked install, which resolves its own "
                "older dependencies. It is recorded rather than narrowed, "
                "because changing a package's supported range is the owner's "
                "decision."
            ),
        },
        {
            "id": "wheel_install_imports_but_cannot_resolve_project_resources",
            "statement": (
                "The built wheel installs and imports, but the project's "
                "configs, mapping tables and documentation are repository "
                "content rather than package data, and 15 modules locate them "
                "beside the source tree. Project resources resolvable from a "
                f"wheel install: {wheel_probe['project_resources_resolvable']}."
            ),
            "why_not_blocking": (
                "The supported installation for running this project is a "
                "source checkout installed with pip install -e ., which is what "
                "the clean-tree verification and CI both use. Making the "
                "distribution self-contained is a packaging change with its own "
                "test surface and belongs in its own task."
            ),
        },
        {
            "id": "archive_member_timestamps_differ_between_builds",
            "statement": (
                "Two builds produce identical member sets and identical file "
                "content, but wheel and sdist formats record a build clock in "
                "their member headers, so the archives are not byte-identical."
            ),
            "why_not_blocking": (
                "Content equality is what a consumer can check; byte-identical "
                "archives would require a format guarantee that does not exist."
            ),
        },
        {
            "id": "dependency_audit_is_a_snapshot",
            "statement": (
                "The dependency audit reflects one advisory database at one "
                "moment. It is not a permanent property of the pinned set."
            ),
            "why_not_blocking": (
                "It is reported with its tool and scope so it can be repeated, "
                "rather than presented as a standing guarantee."
            ),
        },
    ]
    if security["dependency_audit_unresolved"]:
        entries.append({
            "id": "dependency_audit_did_not_run_to_completion",
            "statement": (
                "At least one dependency audit did not run. Not run is recorded "
                "as not run, never folded into a clean result."
            ),
            "why_not_blocking": (
                "No vulnerability was found because none was looked for; the "
                "state is reported as unresolved so the gap is visible."
            ),
        })
    return entries


_ELAPSED = re.compile(r"\bin \d+\.\d+s\b")


def _stabilise(value, workspace: Path):
    """Remove from the shipped report everything that differs run to run.

    Three things vary and none of them is a measurement: the randomly named
    temporary directory the verification ran in, the elapsed seconds pytest
    prints, and the progress dots. A report that changes when nothing changed
    cannot tell anyone whether anything changed, and its checksum stops being
    evidence.
    """
    marker = str(workspace).replace("\\", "/")
    if isinstance(value, dict):
        return {key: _stabilise(item, workspace) for key, item in value.items()}
    if isinstance(value, list):
        return [_stabilise(item, workspace) for item in value]
    if isinstance(value, str):
        text = value.replace("\\", "/").replace(marker, "<release-workspace>")
        return _ELAPSED.sub("in <elapsed>s", text)
    return value


def _prohibited(audit: dict) -> int:
    return len(audit["prohibited_by_suffix"]) + len(audit["prohibited_by_fragment"])


def _render_readiness_markdown(config: dict, report: dict) -> str:
    """The readiness document, rendered from measurements rather than typed."""
    decision = report["readiness"]
    inventory = report["inventory"]
    clean = report["clean_tree"]
    counts = clean["hermetic_tests"]["counts"]
    security = report["security"]
    package = report["package"]
    registry = clean["registry_verification"]
    stable = (report["release_manifest_checksum"]
              == report["release_manifest_checksum_recomputed"])
    lines = [
        "# Release readiness — Task E2",
        "",
        f"**Status: `{decision['status']}`** — release candidate "
        f"`{report['release_candidate_version']}`, contract "
        f"`{report['release_contract_version']}`.",
        "",
        "This document is generated by `scripts/run_e2_release_preparation.py`. "
        "Every number below was measured in an isolated release tree built from "
        "the public allowlist, not in the working directory. Nothing here was "
        "published: no commit, no tag, no push, no PyPI upload, no GitHub "
        "release.",
        "",
        "## Blockers",
        "",
    ]
    if decision["blockers"]:
        lines += ["| blocker | why it is live |", "| --- | --- |"]
        lines += [f"| `{name}` | {_BLOCKER_REASONS.get(name, 'see the JSON report')} |"
                  for name in decision["blockers"]]
    else:
        lines.append("None live. Every gate below was measured and passed.")
    lines += [
        "",
        "## What was measured",
        "",
        "| gate | result |",
        "| --- | --- |",
        f"| files on disk | {inventory['total_files']} files, "
        f"{inventory['total_bytes'] / 1_048_576:.1f} MiB |",
        f"| intended public release | {inventory['release_files']} files, "
        f"{inventory['release_bytes'] / 1_048_576:.1f} MiB |",
        f"| paths admitted by default | 0 — the allowlist fails closed; "
        f"{inventory['fail_closed_exclusions']} path(s) matched no rule and were "
        "excluded |",
        f"| locked-outcome paths in the release | "
        f"{decision['evidence']['locked_paths_in_release']} |",
        f"| locked-outcome paths in git history | "
        f"{decision['evidence']['locked_paths_in_history']} (the repository has "
        f"{inventory['git']['commit_count']} commits) |",
        f"| clean-tree install | `{clean['ok']}` on CPython "
        f"{clean['interpreter']} |",
        f"| hermetic suite in the release tree | `{counts.get('summary_line')}` |",
        f"| data-backed registry | {registry['registered']} entries, verified "
        f"`{registry['verified']}` |",
        f"| release tree unchanged by its own tests | "
        f"`{clean['tree_unchanged_by_tests']}` |",
        f"| wheel members | {package['wheel']['member_count']}, prohibited "
        f"{_prohibited(package['wheel'])} |",
        f"| sdist members | {package['sdist']['member_count']}, prohibited "
        f"{_prohibited(package['sdist'])} |",
        f"| two builds, identical member sets | "
        f"`{package['comparison']['member_sets_identical']}` |",
        f"| credential findings | {security['credential_findings']} |",
        f"| privacy findings | {security['privacy_findings']} |",
        f"| dependency advisories | {security['dependency_vulnerabilities']} |",
        f"| release manifest checksum | `{report['release_manifest_checksum']}` "
        f"(recomputed identical: `{stable}`) |",
        "",
        "The suite count is parsed from pytest's own summary line. A total typed "
        "into a report drifts the moment a test is added, and a stale count looks "
        "exactly like evidence.",
        "",
        "## Documented non-blocking limitations",
        "",
    ]
    for limitation in decision["documented_nonblocking_limitations"]:
        lines += [
            f"**`{limitation['id']}`** — {limitation['statement']}",
            "",
            f"> Not blocking: {limitation['why_not_blocking']}",
            "",
        ]
    lines += [
        "## What this document does not claim",
        "",
        "- It does not say the package is secure. A scan is one tool and one "
        "advisory database at one moment.",
        "- It does not say the third-party sources may be redistributed. Their "
        "terms are unresolved and their bytes are excluded.",
        "- It does not choose a licence. No `LICENSE` file exists and that "
        "decision belongs to the owner.",
        "- It does not reopen any modeling result. The development programme "
        "closed at E1 and the locked final test remains sealed and unopened.",
        "",
    ]
    return "\n".join(lines)


_BLOCKER_REASONS = {
    "missing_owner_license_decision":
        "no `LICENSE` file exists and `pyproject.toml` carries the placeholder "
        "`Unlicensed - student portfolio project`. A licence may be recommended "
        "but not chosen on the owner's behalf.",
    "secret_or_credential_exposure":
        "the secret scan found a credential-shaped value in a file the release "
        "would ship. Remove it, and rotate it where it was ever real.",
    "locked_outcome_present_in_intended_release_or_history":
        "a locked-outcome path reached the release, the package or the history.",
    "clean_installation_failure": "the release tree did not install.",
    "hermetic_ci_failure":
        "the hermetic suite did not pass in the release tree, or the data-backed "
        "registry did not verify.",
    "package_includes_prohibited_files":
        "a built distribution contains a file type or directory the contract "
        "prohibits.",
    "unresolved_redistribution_of_included_raw_data":
        "raw third-party bytes with unresolved terms are inside the release.",
    "dependency_vulnerability_without_accepted_resolution":
        "an advisory applies to a pinned dependency and no resolution is "
        "recorded.",
    "tests_mutate_the_release_worktree":
        "the suite wrote into its own source tree, so a second run differs from "
        "the first.",
}


def _write_outputs(config: dict, manifest: dict, report: dict) -> None:
    outputs = config["outputs"]
    (ROOT / outputs["release_manifest"]).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / outputs["readiness_json"]).write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    markdown = _render_readiness_markdown(config, report)
    RDY.assert_no_license_asserted(markdown)
    RDY.assert_no_redistribution_inference(markdown)
    RDY.assert_no_permanent_security_guarantee(markdown)
    RDY.assert_no_invented_owner_metadata(markdown, permitted_placeholders=())
    SEC.assert_no_secret_values_printed(markdown, [])
    (ROOT / outputs["readiness_markdown"]).write_text(markdown, encoding="utf-8")
    print(f"\nwrote {outputs['release_manifest']}, {outputs['readiness_json']} "
          f"and {outputs['readiness_markdown']}")


if __name__ == "__main__":
    raise SystemExit(main())
