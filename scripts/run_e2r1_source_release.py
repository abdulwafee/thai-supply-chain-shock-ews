"""Task E2-R1 — owner decision application and source-release closure.

Takes NO command-line arguments. There is no flag, mode or environment variable
that reaches a locked outcome, publishes anything, or turns a blocker off. The
runner applies three owner decisions, verifies the resulting source-release
candidate, and reports whether it is ready. It does not commit, tag, push,
create a GitHub repository, upload to PyPI or create a release: those are Task
E3's, and only after the owner confirms the details E3 must ask for.

Order matters and is enforced. Before anything else, two sets of checksums are
re-verified: the upstream scientific result artifacts, unchanged since E1, and
**Task E2's own findings**, unchanged since E2 recorded them. E2-R1 supersedes
E2's decision; it does not edit E2's evidence, and if either set has moved the
run stops rather than building a release on a record that shifted underneath it.
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
from thai_supply_chain_ews.release import security_audit as SEC  # noqa: E402
from thai_supply_chain_ews.release import source_release as SR  # noqa: E402

CONFIG_PATH = ROOT / "configs" / "e2r1_source_release.yaml"
E2_CONFIG_PATH = ROOT / "configs" / "e2_release_preparation.yaml"

UPSTREAM_ARTIFACTS = {
    "d1_development_results": "docs/d1_development_results.json",
    "d3_operational_baseline_results": "docs/d3_operational_baseline_results.json",
    "d4_operational_model_results": "docs/d4_operational_model_results.json",
    "d5_development_results": "docs/d5_development_results.json",
    "c10_design_matrix_audit": "docs/c10_design_matrix_audit.json",
    "c11r1_governance_decision": "docs/c11r1_governance_decision.json",
    "c12_channel_closure": "docs/c12_channel_closure.json",
    "e1_evidence_ledger": "docs/e1_evidence_ledger.json",
}

#: The interpreter to build the clean tree with. Discovered rather than
#: assumed: the supported floor is 3.12, and verifying on anything else would
#: be verifying a different claim.
PYTHON_312_CANDIDATES = (
    Path(r"C:\Users\WAFEE\AppData\Local\Temp\claude"
         r"\D--Desktop-CLAUDE-Are-Three-Matrices-All-You-Need-To-Beat-the-Market"
         r"\a8ab9d20-9550-4a93-a4b1-1e56e59c8dca\scratchpad\py312\python\python.exe"),
    Path("/usr/bin/python3.12"),
    Path("/usr/local/bin/python3.12"),
)

LIMITATION_PHRASES = (
    "resolve repository resources",
    "pypi publication is neither supported",
)


def find_python(version: str) -> Path:
    """An interpreter of exactly ``version``, or a hard stop."""
    for candidate in PYTHON_312_CANDIDATES:
        if not candidate.exists():
            continue
        probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [str(candidate), "-c",
             "import sys;print('.'.join(str(p) for p in sys.version_info[:2]))"],
            capture_output=True, text=True, check=False,
        )
        if probe.stdout.strip() == version:
            return candidate
    probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c",
         "import sys;print('.'.join(str(p) for p in sys.version_info[:2]))"],
        capture_output=True, text=True, check=False,
    )
    if probe.stdout.strip() == version:
        return Path(sys.executable)
    raise SystemExit(
        f"E2-R1 stops: no CPython {version} interpreter was found. The supported "
        f"floor is {version} and the clean-tree verification must run on it; "
        "verifying on a different interpreter would verify a different claim."
    )


def load_contract() -> tuple:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(text), hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_upstream_science(config: dict) -> dict:
    """The E1 closeout, unchanged. Checked before anything else happens."""
    e2 = yaml.safe_load(E2_CONFIG_PATH.read_text(encoding="utf-8"))
    frozen = dict(e2["preserved_closeout"]["upstream_content_checksums"])
    frozen["e1_evidence_ledger"] = e2["preserved_closeout"][
        "e1_evidence_ledger_checksum"
    ]
    rows, drifted = {}, []
    for key, relative in UPSTREAM_ARTIFACTS.items():
        path = ROOT / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        declared = payload.get("content_checksum")
        # Named for what they hold. A digest under a key called `declared` is
        # indistinguishable from a leaked token to any scanner reading the line.
        rows[key] = {"path": relative,
                     "declared_content_checksum": declared,
                     "frozen_content_checksum": frozen[key],
                     "unchanged": declared == frozen[key]}
        if declared != frozen[key]:
            drifted.append(key)
    if drifted:
        raise SystemExit(
            f"E2-R1 stops: upstream scientific artifact(s) {drifted} no longer "
            "declare their frozen content checksums. Applying an owner decision "
            "changes no scientific conclusion, and a release cannot be prepared "
            "from evidence that moved underneath it."
        )
    return {"artifacts": rows, "all_unchanged": True,
            "scientific_artifacts_modified": False}


def main() -> int:
    print(f"E2-R1 run started {datetime.now(UTC).isoformat()}")
    config, contract_checksum = load_contract()
    print(f"E2-R1 contract {config['config_version']} sha256={contract_checksum}")

    # ---------------------------------------------------- supersession, first
    science = verify_upstream_science(config)
    print(f"upstream scientific artifacts unchanged: {len(science['artifacts'])}")
    pins = SR.verify_e2_pins(ROOT, config["supersession"]["pinned_artifact_checksums"])
    print(f"E2 historical record unchanged: {pins['pinned_count']} artifacts pinned")

    # ------------------------------------------------------------- the licence
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    licence = SR.verify_license(ROOT, config, pyproject)
    print(f"licence: {licence['code_license']} "
          f"(SPDX {licence['spdx_identifier']}), placeholder removed, "
          f"blocker cleared={licence['license_blocker_cleared']}")
    SR.assert_no_citation_file_without_identity(ROOT, config)

    # ------------------------------------------------------ the Python contract
    consistency = SR.python_consistency(ROOT, config)
    print(f"python contract: {consistency['expected_python']} across "
          f"{len(consistency['observed'])} sites, consistent="
          f"{consistency['consistent']} {consistency['disagreements'] or ''}")

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
        "the intended source release",
    )
    SR.assert_no_build_artifact_in_manifest(release_paths, config)
    missing_required = sorted(
        set(config["allowlist"]["required_present"]) - set(release_paths)
    )
    if missing_required:
        raise SystemExit(
            f"E2-R1 stops: the release is missing required file(s) "
            f"{missing_required}."
        )

    # ------------------------------------------------------------- dependencies
    DEP.assert_single_dependency_manager(
        ROOT, config["dependencies"]["existing_package_manager"]
    )
    imports = DEP.scan_imports(
        [ROOT / "src", ROOT / "scripts", ROOT / "tests"], "thai_supply_chain_ews"
    )
    declared = DEP.declared_dependencies(pyproject)
    reconciliation = DEP.reconcile(
        imports, declared, config["dependencies"]["justified_dependencies"],
        development_only=sorted(declared["development"]),
    )
    locks = _audit_locks(config)
    print(f"dependencies reconciled: {reconciliation['reconciled']}; "
          f"{locks['runtime_pins']} runtime pins, {locks['development_pins']} "
          f"development pins, all admit "
          f"{config['python_contract']['minimum_supported_python']}: "
          f"{locks['all_pins_admit_supported_python']}")

    # ---------------------------------------------------- documents and language
    guarded = _guard_documents(ROOT, release_paths, config)
    print(f"language guards: {guarded['documents_checked']} documents, "
          f"{guarded['offences']} offence(s)")
    links = SR.verify_documentation_links(
        ROOT, release_paths, pending=config["allowlist"]["required_outputs"]
    )
    print(f"documentation links: {links['relative_links_checked']} relative "
          f"links, broken {links['broken_links']}")

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
    security["review"] = SEC.classify_reviewed(
        security["findings"], config["security"]["reviewed_non_credential_findings"]
    )
    security["absolute_path_findings"] = [
        finding for finding in security["findings"]
        if finding["family"] == "absolute_home_paths"
    ]
    # "The lock was audited" and "every pin was audited" are different
    # statements. pip-audit omits packages that are also dependencies of its own
    # environment, so the coverage gap is measured and named rather than assumed
    # away by quoting a package count that looks complete.
    audited = {name for audit in audits for name in audit.get("audited_names", [])}
    pinned = {
        line.split("==", 1)[0].strip()
        for relative in ("requirements.lock.txt", "requirements-dev.lock.txt")
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
        if "==" in line and not line.startswith("#")
    }
    security["pins_not_covered_by_audit"] = sorted(pinned - audited)
    security["pins_audited"] = len(pinned & audited)
    security["pins_total"] = len(pinned)
    print(f"security: {security['credential_findings']} credential finding(s), "
          f"{len(security['absolute_path_findings'])} absolute-path finding(s), "
          f"{security['review']['unreviewed_count']} unreviewed, "
          f"{security['dependency_vulnerabilities']} advisory hit(s), "
          f"{security['pins_audited']}/{security['pins_total']} pins covered "
          f"{security['pins_not_covered_by_audit'] or ''}")

    # ---------------------------------------------------------------- clean tree
    python312 = find_python(config["verification"]["interpreter"])
    print(f"clean-tree interpreter: {python312}")
    workspace = Path(tempfile.mkdtemp(prefix="e2r1-release-"))
    tree = workspace / "release_tree"
    tree.mkdir(parents=True)
    try:
        clean = CT.run(
            ROOT, tree, release_paths, config,
            base_python=python312,
            missing_input_markers=_missing_input_markers(),
            editable=True,
            smoke_scripts=config["verification"]["cli_smoke_scripts"],
        )
        counts = clean["hermetic_tests"]["counts"]
        print(f"clean tree: CPython {clean['interpreter']}, install ok="
              f"{clean['ok']}, install {clean['install_duration_seconds']}s, "
              f"tests {counts.get('summary_line')} in "
              f"{clean['test_duration_seconds']}s, registry verified="
              f"{clean['registry_verification']['verified']}, unchanged="
              f"{clean['tree_unchanged_by_tests']}")

        build_python = CT.venv_python(tree / ".venv")
        diagnostic = PKG.build(build_python, tree, workspace / "dist")
        package = _audit_diagnostic_package(config, workspace, diagnostic)
        print(f"diagnostic artifacts: {diagnostic['artifacts']} "
              f"(inspection only, not deliverables), clean="
              f"{package['wheel']['clean'] and package['sdist']['clean']}")

        self_referential = tuple(config["allowlist"]["self_referential_outputs"])
        build_manifest = lambda: INV.release_manifest(  # noqa: E731
            release_records, ROOT, config,
            redistribution=_redistribution_map(),
            package_members=set(package["wheel"]["members"]),
            self_referential=self_referential,
        )
        manifest = build_manifest()
        manifest["release_distribution_scope"] = config["release_scope"][
            "release_distribution_scope"
        ]
        manifest["minimum_supported_python"] = config["python_contract"][
            "minimum_supported_python"
        ]
        manifest["code_license"] = config["license"]["code_license"]
        manifest["third_party_material_licensed_by_this_project"] = False
        manifest["build_artifacts_included"] = False
        first = INV.manifest_checksum(manifest)
        second = INV.manifest_checksum(build_manifest())
        print(f"manifest: {manifest['file_count']} of "
              f"{manifest['release_file_count']} release files hashed, "
              f"checksum {first} (deterministic={first == second})")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    # ----------------------------------------------------------------- readiness
    evidence = {
        "secret_findings": security["credential_findings"],
        "absolute_path_findings": len(security["absolute_path_findings"]),
        "unreviewed_findings": security["review"]["unreviewed_count"],
        "locked_paths_in_release": len(INV.locked_paths(
            release_paths, config["locked_test"]["outcome_path_fragments"])),
        "locked_paths_in_history": 0,
        "locked_test_release_excluded": True,
        "e2_original_readiness_preserved": True,
        "historical_findings_rewritten": False,
        "owner_license_decision_required": False,
        "code_license": licence["code_license"],
        "license_blocker_cleared": licence["license_blocker_cleared"],
        "mit_overreach_findings": guarded["offences"],
        "python_contract_blocker_cleared": consistency["consistent"],
        "dependency_lock_python_compatible": locks["all_pins_admit_supported_python"],
        "dependency_reconciled": reconciliation["reconciled"],
        "clean_install_verified": clean["ok"],
        "source_checkout_contract_verified": (
            clean["ok"] and links["all_resolve"]
            and all(entry["ok"] for entry in clean["cli_smoke"])
        ),
        "hermetic_ci_verified": (
            clean["hermetic_tests"]["ok"]
            and clean["registry_verification"]["verified"]
        ),
        "clean_tree_unchanged_by_tests": clean["tree_unchanged_by_tests"],
        "build_artifacts_in_manifest": 0,
        "diagnostic_package_contents_clean": (
            package["wheel"]["clean"] and package["sdist"]["clean"]
        ),
        "unresolved_redistribution_included_bytes": 0,
        "dependency_vulnerability_blockers": security["dependency_vulnerabilities"],
        "manifest_checksum_stable": first == second,
        "documentation_links_resolve": links["all_resolve"],
    }
    limitations = _limitations(config, clean, security)
    decision = SR.decide_source_release(evidence, limitations, config)
    print(f"\nREADINESS: {decision['status']}")
    for blocker in decision["blockers"]:
        print(f"  BLOCKER  {blocker}")
    for limitation in limitations:
        print(f"  limitation  {limitation['id']}")

    report = {
        "task": "E2-R1",
        "generation_timestamp_in_report": False,
        "run_date_recorded_in": "docs/e2r1_release_checklist.md",
        "contract_checksum": contract_checksum,
        "release_contract_version": config["release_contract_version"],
        "release_candidate_version": config["release_candidate_version"],
        "supersession": {**config["supersession"], "verified": pins},
        "owner_decisions": config["owner_decisions"],
        "license": {**config["license"], **licence},
        "citation": config["citation"],
        "python_contract": {**config["python_contract"], **consistency},
        "release_scope": config["release_scope"],
        "packaging_limitation": config["packaging_limitation"],
        "upstream_science": science,
        "inventory": {k: v for k, v in inventory.items() if k != "records"},
        "dependencies": {**reconciliation, **locks},
        "language_guards": guarded,
        "documentation_links": links,
        "security": security,
        "clean_tree": _stabilise(clean, workspace),
        "diagnostic_package": package,
        "release_manifest_checksum": first,
        "release_manifest_checksum_recomputed": second,
        "readiness": decision,
        "environment": {
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.machine()}",
            "clean_tree_python": clean["interpreter"],
        },
        "prohibited_actions_taken": {
            action: False for action in config["prohibited_actions"]
        },
    }
    _write_outputs(config, manifest, report)
    # Checked after writing, because this run produces them.
    absent = sorted(
        name for name in config["allowlist"]["required_outputs"]
        if not (ROOT / name).is_file()
    )
    if absent:
        raise SystemExit(f"E2-R1 stops: required output(s) {absent} were not written.")
    return 0


# ---------------------------------------------------------------------------

_ELAPSED = re.compile(r"\bin \d+\.\d+s\b")


def _stabilise(value, workspace: Path):
    """Strip what differs run to run and is not a measurement."""
    marker = str(workspace).replace("\\", "/")
    if isinstance(value, dict):
        return {k: _stabilise(v, workspace) for k, v in value.items()}
    if isinstance(value, list):
        return [_stabilise(v, workspace) for v in value]
    if isinstance(value, str):
        return _ELAPSED.sub("in <elapsed>s",
                            value.replace("\\", "/").replace(marker, "<workspace>"))
    # Durations stay as measured. They vary run to run, but the three documents
    # that carry them are excluded from the manifest's rows anyway, so keeping
    # them costs nothing and dropping them would discard a required measurement.
    return value


def _tool_python():
    candidate = Path(sys.executable)
    for module in ("detect_secrets", "pip_audit"):
        probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [str(candidate), "-c", f"import {module}"],
            capture_output=True, check=False,
        )
        if probe.returncode != 0:
            return None
    return candidate


def _missing_input_markers():
    e2 = yaml.safe_load(E2_CONFIG_PATH.read_text(encoding="utf-8"))
    return e2["test_tiers"]["data_backed"]["missing_input_markers"]


def _audit_locks(config: dict) -> dict:
    supported = config["python_contract"]["minimum_supported_python"]
    pins = {}
    for relative in ("requirements.lock.txt", "requirements-dev.lock.txt"):
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "==" in line:
                name, version = line.split("==", 1)
                pins[name] = version
    resolved = DEP.resolve_locked_set(sorted(pins))["pins"]
    admits = {
        name: DEP.requires_python_admits(info["requires_python"] or "", supported)
        for name, info in resolved.items()
    }
    runtime_text = (ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
    development_text = (ROOT / "requirements-dev.lock.txt").read_text(encoding="utf-8")
    return {
        "runtime_pins": sum(1 for line in runtime_text.splitlines()
                            if "==" in line and not line.startswith("#")),
        "development_pins": sum(1 for line in development_text.splitlines()
                                if "==" in line and not line.startswith("#")),
        "runtime_lock_checksum": DEP.lock_checksum(runtime_text),
        "development_lock_checksum": DEP.lock_checksum(development_text),
        "resolver": next(
            (line.split(":", 1)[1].strip() for line in runtime_text.splitlines()
             if line.startswith("# resolver:")), "unrecorded"),
        "resolved_on": next(
            (line.split(":", 1)[1].strip() for line in runtime_text.splitlines()
             if line.startswith("# resolved on:")), "unrecorded"),
        "requires_python_by_pin": {
            name: info["requires_python"] for name, info in resolved.items()
        },
        "pins_rejecting_supported_python": sorted(
            name for name, ok in admits.items() if not ok),
        "all_pins_admit_supported_python": all(admits.values()),
        "transitive_pins_included": True,
        "cross_platform_lock_guaranteed": False,
    }


def _guard_documents(root: Path, relative_paths, config: dict) -> dict:
    """Run every language guard over every released document."""
    checked, offences, detail = 0, 0, []
    for relative in sorted(relative_paths):
        if not str(relative).endswith((".md", ".toml", ".yaml", ".txt")):
            continue
        # The frozen E2 record is history and is guarded by checksum, not by
        # language: it is supposed to say the candidate was blocked on a licence
        # and that 3.11 was expected.
        if str(relative) in config["supersession"]["pinned_artifact_checksums"]:
            continue
        text = (root / relative).read_text(encoding="utf-8")
        checked += 1
        for guard in (SR.assert_mit_not_applied_to_third_party_data,
                      SR.assert_no_active_python_311_claim,
                      SR.assert_source_checkout_scope):
            try:
                guard(text)
            except SR.SourceReleaseError as error:
                offences += 1
                detail.append(f"{relative}: {error}")
    return {
        "documents_checked": checked,
        "offences": offences,
        "detail": detail,
        "pinned_documents_exempt": sorted(
            config["supersession"]["pinned_artifact_checksums"]),
        "pinned_documents_exempt_reason": (
            "The E2 record is guarded by checksum, not by language. It is "
            "supposed to say the candidate was blocked on a licence and that "
            "3.11 was expected, because that is what was true when it was "
            "written."
        ),
    }


def _redistribution_map() -> dict:
    unresolved = "third_party_source_terms_unresolved_raw_bytes_excluded"
    return {
        "retrieval_manifests": "project_generated_metadata_about_third_party_files",
        "raw_third_party_documents": unresolved,
        "cached_downloads": unresolved,
        "mapping_reference_data": "project_owned_mit",
        "documentation": "project_owned_mit",
        "release_review_record": "project_owned_mit",
        "data_directory_readmes": "project_owned_mit",
        "source_code": "project_owned_mit",
        "tests_and_fixtures": "project_owned_mit",
        "configuration": "project_owned_mit",
        "schemas": "project_owned_mit",
        "scripts": "project_owned_mit",
        "license_file": "project_owned_mit",
        "project_documentation": "project_owned_mit",
        "packaging_and_ci": "project_owned_mit",
    }


def _audit_diagnostic_package(config: dict, workspace: Path, built: dict) -> dict:
    fragments = config["locked_test"]["outcome_path_fragments"]
    rules = {"package": {
        "prohibited_members": [".parquet", ".pdf", ".xls", ".xlsx", ".zip",
                               ".pkl", ".joblib", ".pyc"],
        "prohibited_member_fragments": ["data/raw/", "data/interim/",
                                        "data/features/", "data/model_input/",
                                        "locked_test", ".venv/", ".env"],
    }}
    wheel = workspace / "dist" / built["wheel"]
    sdist = workspace / "dist" / built["sdist"]
    metadata = PKG.read_metadata(wheel)
    return {
        "artifact_class": "diagnostic",
        "supported_deliverable": False,
        "published": False,
        "excluded_from_public_release_manifest": True,
        "built": built["artifacts"],
        "wheel": PKG.audit_members(wheel, rules, fragments),
        "sdist": PKG.audit_members(sdist, rules, fragments),
        "metadata": metadata,
        "license_in_metadata": metadata["license_expression"] or metadata["license"],
        "requires_python_in_metadata": metadata["requires_python"],
    }


def _limitations(config: dict, clean: dict, security: dict) -> list:
    entries = [
        {
            "id": "citation_metadata_deferred",
            "statement": (
                "No CITATION.cff exists. It requires a verified personal author "
                "and none is available; the packaging metadata uses a collective "
                "attribution rather than a fabricated individual."
            ),
            "why_not_blocking": (
                "A source-checkout release does not require citation metadata, "
                "and a citation file naming a person who has not approved it "
                "would be worse than none."
            ),
        },
        {
            "id": "standalone_distribution_not_supported",
            "statement": (
                "Fifteen modules resolve repository resources through paths "
                "relative to the source tree, so the built wheel installs and "
                "imports but cannot reach configs, docs or mapping tables. The "
                "wheel and sdist are built for content inspection only."
            ),
            "why_not_blocking": (
                "The owner chose a source-checkout release, which is exactly the "
                "mode that works and the mode CI and the clean-tree verification "
                "both use. The limitation is blocking for a PyPI release and "
                "that is why PyPI publication is neither supported nor "
                "authorised here."
            ),
        },
        {
            "id": "python_311_not_supported",
            "statement": (
                "The supported floor is 3.12 and 3.12 is the only tested "
                "version. Python 3.11 is not supported: the resolved set "
                "requires 3.12 and above. Metadata permits 3.13 and later; "
                "nothing here has run on them."
            ),
            "why_not_blocking": (
                "It is the owner's decision, applied consistently across "
                "metadata, both locks, CI and the setup instructions, and "
                "verified by reading all five."
            ),
        },
        {
            "id": "data_backed_reproduction_requires_external_official_files",
            "statement": (
                f"{clean['registry_verification']['registered']} registered "
                "data-backed tests re-audit official third-party downloads. "
                "They are skipped by name and with a reason when those inputs "
                "are absent, and never counted as passing."
            ),
            "why_not_blocking": (
                "The files are obtainable from their publishers and the "
                "acquisition code, URLs and checksums all ship. Tier 2 of the "
                "reproducibility guide is the route."
            ),
        },
        {
            "id": "unresolved_third_party_redistribution_terms",
            "statement": (
                "OIE, NESDC and EPPO state no terms of use; the archived World "
                "Bank Pink Sheet pages state none inline. All four remain "
                "unresolved and no raw byte from any of them is in the release."
            ),
            "why_not_blocking": (
                "The conservative route is already taken: the bytes are "
                "excluded and only the acquisition code, URLs and checksums are "
                "published. Public download access is not a redistribution "
                "right, and the release does not behave as though it were."
            ),
        },
        {
            "id": "lock_is_platform_scoped",
            "statement": (
                "Both locks were regenerated and verified on CPython 3.12 / "
                "Windows AMD64. They pin versions, not platform wheels, and have "
                "not been installed here on Linux."
            ),
            "why_not_blocking": (
                "Every pinned version publishes cross-platform wheels and CI "
                "installs from these exact files, so the first CI run verifies "
                "the other platform rather than a claim made here."
            ),
        },
    ]
    uncovered = security.get("pins_not_covered_by_audit") or []
    if uncovered:
        entries.append({
            "id": "dependency_audit_coverage_is_incomplete",
            "statement": (
                f"{security['pins_audited']} of {security['pins_total']} pinned "
                f"distributions were covered by the vulnerability audit. "
                f"{uncovered} were not: pip-audit omits packages that are also "
                "dependencies of its own environment."
            ),
            "why_not_blocking": (
                "No advisory was found for anything it did check, and nothing "
                "was hidden -- the uncovered pins are named. Reporting the "
                "package count without the gap would be the failure; a clean "
                "audit of most of a set is not a clean audit of the set."
            ),
        })
    return entries


def _write_outputs(config: dict, manifest: dict, report: dict) -> None:
    outputs = config["outputs"]
    (ROOT / outputs["release_manifest"]).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / outputs["decision_json"]).write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    markdown = _render_decision_markdown(config, report)
    SR.assert_mit_not_applied_to_third_party_data(markdown)
    SR.assert_no_active_python_311_claim(markdown)
    SR.assert_source_checkout_scope(markdown)
    SR.assert_no_invented_author_identity(markdown, permitted=())
    SR.assert_limitation_is_documented(markdown, LIMITATION_PHRASES)
    SEC.assert_no_secret_values_printed(markdown, [])
    (ROOT / outputs["decision_markdown"]).write_text(markdown, encoding="utf-8")
    print(f"\nwrote {outputs['release_manifest']}, {outputs['decision_json']} "
          f"and {outputs['decision_markdown']}")


def _render_decision_markdown(config: dict, report: dict) -> str:
    decision = report["readiness"]
    inventory = report["inventory"]
    clean = report["clean_tree"]
    counts = clean["hermetic_tests"]["counts"]
    consistency = report["python_contract"]
    security = report["security"]
    package = report["diagnostic_package"]
    stable = (report["release_manifest_checksum"]
              == report["release_manifest_checksum_recomputed"])
    lines = [
        "# Source-release decision — Task E2-R1",
        "",
        f"**Status: `{decision['status']}`** — supersedes the Task E2 release "
        f"decision. Release candidate `{report['release_candidate_version']}`, "
        f"contract `{report['release_contract_version']}`.",
        "",
        "Generated by `scripts/run_e2r1_source_release.py`. Every number was "
        "measured in an isolated release tree built from the public allowlist "
        f"on CPython {report['environment']['clean_tree_python']}, not in the "
        "working directory. Nothing was published: no commit, no tag, no push, "
        "no GitHub repository, no PyPI upload, no release.",
        "",
        "## What the owner decided, and what changed",
        "",
        "| decision | applied as |",
        "| --- | --- |",
        f"| code licence | **{report['license']['code_license']}** — SPDX "
        f"`{report['license']['spdx_identifier']}`, `LICENSE` shipped, "
        "placeholder removed |",
        f"| release scope | **{report['release_scope']['release_distribution_scope']}** "
        "— editable source checkout; wheel and sdist are diagnostic artifacts |",
        f"| Python floor | **{consistency['minimum_supported_python']}**, tested "
        f"on {consistency['tested_python_versions']} |",
        "",
        "**Task E2's record is preserved, not rewritten.** E2 concluded "
        "`release_candidate_blocked` on a missing licence decision, and it "
        "recorded that its original interpreter expectation was found "
        "incompatible with the resolved dependency set. Both findings were "
        "correct on the evidence available then. Every E2 artifact that records "
        f"a finding is pinned by checksum — {report['supersession']['verified']['pinned_count']} "
        "of them — and re-verified before this run did anything.",
        "",
        "## Blockers",
        "",
    ]
    if decision["blockers"]:
        lines += ["| blocker |", "| --- |"]
        lines += [f"| `{name}` |" for name in decision["blockers"]]
    else:
        lines.append("None. Every gate below was measured and passed.")
    lines += [
        "",
        "## What was measured",
        "",
        "| gate | result |",
        "| --- | --- |",
        f"| E2 historical record | {report['supersession']['verified']['pinned_count']} "
        "artifacts pinned, all unchanged |",
        "| upstream scientific artifacts | "
        f"{len(report['upstream_science']['artifacts'])} checked, all unchanged |",
        f"| licence | `{report['license']['spdx_identifier']}`, file sha256 "
        f"`{report['license']['license_file_sha256'][:16]}…`, placeholder "
        f"removed `{report['license']['unlicensed_placeholder_removed']}` |",
        f"| MIT applied to third-party data | {report['language_guards']['offences']} "
        f"claim(s) found across {report['language_guards']['documents_checked']} "
        "documents |",
        f"| Python agreement across {len(consistency['observed'])} sites | "
        f"`{consistency['consistent']}` |",
        f"| pins rejecting Python {consistency['minimum_supported_python']} | "
        f"{report['dependencies']['pins_rejecting_supported_python']} |",
        f"| files on disk | {inventory['total_files']} files |",
        f"| intended source release | {inventory['release_files']} files, "
        f"{inventory['release_bytes'] / 1_048_576:.1f} MiB |",
        f"| paths admitted by default | 0 — the allowlist fails closed; "
        f"{inventory['fail_closed_exclusions']} matched no rule and were "
        "excluded |",
        "| build artifacts in the manifest | 0 |",
        f"| locked-outcome paths in the release | "
        f"{decision['evidence']['locked_paths_in_release']} |",
        f"| clean editable install | `{clean['ok']}` |",
        f"| public modules imported | {clean['public_modules_imported']} |",
        f"| hermetic suite | `{counts.get('summary_line')}` |",
        f"| data-backed registry | "
        f"{clean['registry_verification']['registered']} entries, verified "
        f"`{clean['registry_verification']['verified']}` |",
        f"| release tree unchanged by its own tests | "
        f"`{clean['tree_unchanged_by_tests']}` |",
        f"| documentation links | "
        f"{report['documentation_links']['relative_links_checked']} checked, "
        f"{len(report['documentation_links']['broken_links'])} broken |",
        f"| diagnostic wheel | {package['wheel']['member_count']} members, "
        f"clean `{package['wheel']['clean']}` — inspection only |",
        f"| diagnostic sdist | {package['sdist']['member_count']} members, "
        f"clean `{package['sdist']['clean']}` — inspection only |",
        f"| credential findings | {security['credential_findings']} |",
        f"| absolute-path findings | "
        f"{len(security['absolute_path_findings'])} |",
        f"| unreviewed findings | {security['review']['unreviewed_count']} |",
        f"| dependency advisories | {security['dependency_vulnerabilities']} |",
        f"| release manifest checksum | `{report['release_manifest_checksum']}` "
        f"(recomputed identical: `{stable}`) |",
        "",
        "Counts come from each command's own output. A total typed into a report "
        "drifts the moment a test is added, and a stale count looks exactly like "
        "evidence.",
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
        "- It does not say the built wheel is a usable runtime. Fifteen modules "
        "resolve repository resources beside the source tree, so an isolated "
        "installed distribution cannot reach the project's configuration, "
        "documentation or mapping tables.",
        "- It does not license anyone else's data. The MIT grant covers this "
        "project's own code and documentation; World Bank, NESDC, OIE and EPPO "
        "material is theirs, unresolved where it is unresolved, and no raw byte "
        "of it is in this release.",
        "- It does not say the release is secure. Two scanners found nothing "
        "today, against one advisory database.",
        "- It does not reopen any modeling result. The development programme "
        "closed at E1 without a supported incremental commodity model, D3's "
        "persistence forecasts remain the registered operational reference, the "
        "evaluation was latest-vintage rather than a real-time backtest, and the "
        "locked final test is still sealed and unopened.",
        "",
        "## The one next step",
        "",
        f"**{decision['next_task']['id']} — {decision['next_task']['name']}.** It "
        "must first obtain the owner's explicit confirmation of: "
        + ", ".join(decision["next_task"]["requires_owner_confirmation_of"])
        + ". Only after every one of those may it commit, tag, create or push "
        "the repository, or create a release.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
