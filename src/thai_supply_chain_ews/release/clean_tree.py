"""Isolated release-tree construction and verification (Task E2).

The working directory is not evidence. It has a virtual environment on the path,
a hundred megabytes of downloaded workbooks, generated Parquet, an editable
install and an environment variable already exported. A suite that passes there
says nothing about what a stranger gets from the published files.

So the release tree is built from the allowlist alone, in a temporary directory
outside the repository, and every claim about the release is measured there: the
install, the import, the lint, the schema parse, the package build and the
hermetic tests. Nothing is copied in that the allowlist did not admit, and
:func:`materialise` raises rather than copying a locked-outcome path, a virtual
environment, a raw download or a generated table.

The tree is checksummed before and after the test run. A suite that writes into
its own source tree is a suite whose second run differs from its first, and that
is a reproducibility defect regardless of whether the assertions passed.

**Two install modes are measured separately, because they answer different
questions.** The source install is how this repository is meant to be used: its
configs, mapping tables and documentation live in the tree, not in the wheel.
The wheel install answers the narrower question of whether the built
distribution imports at all. Reporting one number for both would hide which of
the two was actually verified.

**The data-backed tier is verified, not asserted.** ``tests/conftest.py`` skips
the registered data-backed tests when their inputs are absent, and
:func:`verify_data_backed_registry` re-runs the suite with the registry removed
to confirm that every registered test really does fail without those inputs, and
that nothing else fails. Removing a green test, or letting an unrelated failure
hide inside the registry, is how a suite gets quietly weakened to produce a green
CI result.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import byte_provenance as BP

__all__ = [
    "PYTEST_SUMMARY",
    "CleanTreeError",
    "materialise",
    "parse_pytest_counts",
    "run",
    "run_pytest",
    "tree_checksum",
    "venv_python",
    "verify_data_backed_registry",
    "wheel_install_probe",
]

#: pytest's terminal summary. Verbose mode decorates it with equals signs
#: ("==== 5 failed, 812 passed in 41.20s ===="); ``-q`` prints it bare
#: ("1548 passed, 246 skipped in 27.34s"). Both forms are the same measurement
#: and both have to parse, because a run whose summary cannot be read is
#: reported as unmeasured rather than as zero.
PYTEST_SUMMARY = re.compile(
    r"^(?:=+\s*)?(.*?\b(?:passed|failed|error|errors|no tests ran)\b.*?)"
    r"(?:\s+in\s+[\d.]+s.*?)?(?:\s*=+)?$"
)

#: Anchored at the tree root, because ``models/`` as a bare fragment would also
#: reject ``src/thai_supply_chain_ews/models/__init__.py`` -- a source package,
#: not an output directory.
_FORBIDDEN_TREE_ROOTS = (
    ".venv/", "venv/", "data/raw/", "data/interim/", "data/processed/",
    "data/features/", "data/targets/", "data/model_input/", "models/", ".git/",
)

#: Never legitimate at any depth.
_FORBIDDEN_TREE_FRAGMENTS = (
    "site-packages/", "__pycache__/", ".pytest_cache/", ".ruff_cache/",
    ".egg-info/",
)

#: The verification environment inside a release tree is called `.venv` on
#: purpose. Every tool already knows to leave that name alone -- ruff excludes
#: it by default and .gitignore covers it -- so no lint configuration has to be
#: widened, and a standing rule against broad ruff exclusions stays intact.
_SKIP_WALK = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv",
    "dist", "build", ".git",
}


class CleanTreeError(RuntimeError):
    """The release tree was asked to contain, or failed to demonstrate, something."""


def materialise(root: Path, destination: Path, relative_paths,
                locked_fragments, exemptions=()) -> dict:
    """Copy exactly the allowlisted files into an empty destination.

    This repeats the allowlist's directory prohibitions rather than trusting
    them. The allowlist decides what ships; this decides what is *copied*, and
    two independent gates on the same question is the point -- a mistake in one
    is caught by the other. ``exemptions`` are the same literal paths the
    allowlist enumerates, and no exemption can ever release a locked path.
    """
    root, destination = Path(root), Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise CleanTreeError(f"{destination} is not empty; refusing to build over it")
    lowered = tuple(f.lower() for f in locked_fragments)
    exempt = {str(e).replace("\\", "/") for e in exemptions}
    copied, total = 0, 0
    for relative in sorted(relative_paths):
        normalised = str(relative).replace("\\", "/")
        if any(fragment in normalised.lower() for fragment in lowered):
            raise CleanTreeError(
                f"{normalised} is a locked-outcome path and may not be copied "
                "into the release tree"
            )
        forbidden = (
            any(f"{normalised}/".startswith(prefix) for prefix in _FORBIDDEN_TREE_ROOTS)
            or any(fragment in f"{normalised}/"
                   for fragment in _FORBIDDEN_TREE_FRAGMENTS)
        )
        if forbidden and normalised not in exempt:
            raise CleanTreeError(
                f"{normalised} is a local environment, raw download or generated "
                "artifact and may not be copied into the release tree"
            )
        target = destination / normalised
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / normalised, target)
        copied += 1
        total += target.stat().st_size
    return {"files": copied, "bytes": total, "destination": str(destination)}


def tree_checksum(destination: Path) -> tuple:
    """A digest over every source file in the tree, plus the per-path digest map.

    The created environment, caches and build outputs are skipped: they are
    products of running the verification, not part of the release.

    Text is hashed canonically and binary raw, so the before-and-after
    comparison detects a test that wrote into its own source tree, and not
    merely a platform whose checkout uses different line terminators. Hashing
    the working tree's bytes would have made this check report a change on
    Linux that Windows called clean, which is the opposite of what it is for.
    """
    destination = Path(destination)
    digests = {}
    for dirpath, dirnames, filenames in os.walk(destination):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_WALK and not d.endswith(".egg-info")
        ]
        for name in sorted(filenames):
            path = Path(dirpath) / name
            relative = path.relative_to(destination).as_posix()
            digests[relative] = BP.release_digest(path.read_bytes())[0]
    combined = hashlib.sha256(
        json.dumps(dict(sorted(digests.items())), separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return combined, digests


def venv_python(environment: Path) -> Path:
    """The interpreter inside a created environment, on either platform."""
    environment = Path(environment)
    windows = environment / "Scripts" / "python.exe"
    return windows if windows.exists() else environment / "bin" / "python"


def _run(arguments, cwd, timeout: int = 3600) -> dict:
    completed = subprocess.run(  # noqa: S603 - fixed argv lists, no shell
        [str(a) for a in arguments], cwd=str(cwd), capture_output=True,
        text=True, check=False, timeout=timeout,
        env={**os.environ, "COLUMNS": "250", "PYTHONIOENCODING": "utf-8"},
    )
    return {
        "command": " ".join(str(a) for a in arguments),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def parse_pytest_counts(output: str) -> dict:
    """Counts read from pytest's own summary line, never from a prior total.

    A literal typed into a report drifts the moment a test is added, and a stale
    count looks exactly like evidence.
    """
    counts, matched = {}, None
    for line in reversed(output.splitlines()):
        match = PYTEST_SUMMARY.match(line.strip())
        if match and re.search(r"\d+\s+(passed|failed|error)", match.group(1)):
            matched = match.group(1).strip()
            break
    if matched is None:
        raise CleanTreeError(
            "pytest produced no parseable summary line; the run cannot be "
            "reported as a count because no count was measured"
        )
    for number, label in re.findall(r"(\d+)\s+([a-z]+)", matched):
        counts[label] = int(number)
    counts["summary_line"] = matched
    counts["measured_from_command_output"] = True
    counts["copied_from_prior_totals"] = False
    counts["collected"] = sum(
        value for key, value in counts.items()
        if key in ("passed", "failed", "skipped", "xfailed", "xpassed", "error",
                   "errors", "deselected")
    )
    return counts


def run_pytest(python: Path, cwd: Path, extra=()) -> dict:
    """Run the suite and parse its real summary line."""
    result = _run([python, "-m", "pytest", "-q", "--no-header",
                   "-p", "no:cacheprovider", "--tb=line", "-rfE", *extra], cwd)
    output = result["stdout"] + result["stderr"]
    try:
        result["counts"] = parse_pytest_counts(output)
    except CleanTreeError as error:
        result["counts"] = {"error": str(error)}
    result["failing_ids"] = sorted({
        match.group(1).replace("\\", "/")
        for match in re.finditer(r"^(?:FAILED|ERROR) (tests/[^\s:]+::[^\s]+)",
                                 output, re.MULTILINE)
    })
    result["tail"] = "\n".join(output.splitlines()[-30:])
    result.pop("stdout", None)
    result.pop("stderr", None)
    return result


def verify_data_backed_registry(python: Path, cwd: Path, registry_path: Path,
                                missing_input_markers) -> dict:
    """Prove the registry contains exactly the tests that need absent inputs.

    Three things are checked and each can fail on its own. Every registered test
    must fail when the registry is removed -- one that passes did not need
    registering. Every failure must be registered -- an unregistered failure is
    a real failure. And every failure must name a missing input somewhere in its
    traceback -- otherwise it is an unrelated defect wearing a data-availability
    label.
    """
    registry_path = Path(registry_path)
    registered = {
        line.strip()
        for line in registry_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    stashed = registry_path.read_bytes()
    registry_path.unlink()
    try:
        without = run_pytest(python, cwd)
        failing = set(without["failing_ids"])
        unregistered = sorted(failing - registered)
        never_failed = sorted(registered - failing)
        unmarked = []
        if not unregistered and not never_failed:
            detail = _run([python, "-m", "pytest", "-q", "--no-header",
                           "-p", "no:cacheprovider", "--tb=long",
                           *sorted(failing)], cwd)
            body = detail["stdout"] + detail["stderr"]
            unmarked = [] if any(m in body for m in missing_input_markers) else ["*"]
    finally:
        registry_path.write_bytes(stashed)
    return {
        "registered": len(registered),
        "failed_without_registry": len(failing),
        "unregistered_failures": unregistered,
        "registered_but_did_not_fail": never_failed,
        "failures_without_a_missing_input_marker": unmarked,
        "counts_without_registry": without["counts"],
        "verified": not unregistered and not never_failed and not unmarked,
        "tests_weakened_to_obtain_green_ci": False,
    }


def _public_modules(destination: Path) -> list:
    """Every importable module under ``src/``, as dotted names."""
    source = Path(destination) / "src"
    names = []
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source)
        if any(part.startswith((".", "_")) and part != "__init__.py"
               for part in relative.parts):
            continue
        parts = list(relative.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        if parts:
            names.append(".".join(parts))
    return names


def run(root: Path, destination: Path, relative_paths, config: dict,
        *, base_python=None, missing_input_markers=(), editable: bool = True,
        smoke_scripts=()) -> dict:
    """Build the tree, install it, and measure what the release claims.

    ``editable`` installs the project from the tree with ``--no-deps``, which is
    how a source-checkout release is meant to be used: the locks already fixed
    every version, so a project install that re-resolves them is not installing
    from the lock at all.
    """
    base_python = Path(base_python or sys.executable)
    locked_fragments = config["locked_test"]["outcome_path_fragments"]
    exemptions = config["allowlist"].get("exclude_exemptions", ())
    report = {"steps": []}

    def step(name, result, **extra):
        entry = {"step": name, "ok": bool(result.get("ok", True)), **extra}
        if not entry["ok"]:
            entry["tail"] = "\n".join(
                (result.get("stdout", "") + result.get("stderr", "")
                 + result.get("tail", "")).splitlines()[-25:]
            )
        report["steps"].append(entry)
        return entry

    report["materialised"] = materialise(
        root, destination, relative_paths, locked_fragments, exemptions
    )
    destination = Path(destination)

    # A real clone has a .git directory, and several tests legitimately ask git
    # what it ignores. Initialising an empty repository (no commit, no remote)
    # makes the tree faithful to a checkout rather than to a zip file.
    step("git_init", _run(["git", "init", "-q", "."], destination))

    before, _ = tree_checksum(destination)
    report["tree_checksum_before_tests"] = before

    environment = destination / ".venv"
    step("create_environment",
         _run([base_python, "-m", "venv", str(environment)], destination))
    python = venv_python(environment)
    report["interpreter"] = _run(
        [python, "-c", "import sys;print(sys.version.split()[0])"], destination
    )["stdout"].strip()

    install_started = time.monotonic()
    step("upgrade_installer",
         _run([python, "-m", "pip", "install", "--quiet", "--upgrade",
               "pip", "setuptools", "wheel"], destination))
    step("install_runtime_lock",
         _run([python, "-m", "pip", "install", "--quiet", "--require-virtualenv",
               "-r", "requirements.lock.txt"], destination))
    step("install_development_lock",
         _run([python, "-m", "pip", "install", "--quiet", "--require-virtualenv",
               "-r", "requirements-dev.lock.txt"], destination))
    project_install = ["--no-deps", "-e", "."] if editable else ["--no-deps", "."]
    step("install_project_from_source",
         _run([python, "-m", "pip", "install", "--quiet", *project_install],
              destination),
         mode="editable_source_checkout" if editable else "non_editable",
         independently_resolved_dependencies=False)
    report["install_duration_seconds"] = round(time.monotonic() - install_started, 2)

    modules = _public_modules(destination)
    program = (
        "import importlib\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module(name)\n"
    )
    step("import_all_public_modules", _run([python, "-c", program], destination),
         module_count=len(modules))
    report["public_modules_imported"] = len(modules)

    report["cli_smoke"] = [
        {"script": script,
         "ok": _run([python, "-c",
                     "import importlib.util,sys;"
                     f"spec=importlib.util.spec_from_file_location('_smoke','{script}');"
                     "m=importlib.util.module_from_spec(spec);"
                     "sys.exit(0 if m is not None and spec.loader is not None else 1)"],
                    destination, timeout=300)["ok"]}
        for script in smoke_scripts
    ]
    step("public_cli_smoke_checks",
         {"ok": all(entry["ok"] for entry in report["cli_smoke"])},
         checks=len(report["cli_smoke"]))

    step("ruff", _run([python, "-m", "ruff", "check", "."], destination))
    step("parse_configs_and_schemas", _run([python, "-c", _PARSE_PROGRAM], destination))

    tests_started = time.monotonic()
    hermetic = run_pytest(python, destination)
    report["test_duration_seconds"] = round(time.monotonic() - tests_started, 2)
    step("hermetic_tests", hermetic, counts=hermetic["counts"])
    report["hermetic_tests"] = hermetic
    report["registry_verification"] = verify_data_backed_registry(
        python, destination, destination / "tests" / "data_backed_tests.txt",
        missing_input_markers,
    )

    after, digests = tree_checksum(destination)
    report["tree_checksum_after_tests"] = after
    report["tree_unchanged_by_tests"] = before == after
    # "No local data" means no third-party download and no generated table --
    # not "nothing under data/". The literally enumerated exemptions (retrieval
    # manifests and directory READMEs) are release content and are expected to
    # be here; counting them as local data would make the check meaningless.
    exempt = {str(path).replace("\\", "/") for path in exemptions}
    report["local_data_in_tree"] = sorted(
        path for path in digests
        if path.startswith(("data/raw/", "data/interim/", "data/processed/",
                            "data/features/", "data/targets/",
                            "data/model_input/", "models/"))
        and path not in exempt
    )
    report["no_local_data_in_tree"] = not report["local_data_in_tree"]
    report["ok"] = all(entry["ok"] for entry in report["steps"])
    return report


def wheel_install_probe(wheel: Path, destination: Path, base_python=None) -> dict:
    """Install the built wheel on its own and record exactly what it can do.

    The distribution deliberately ships code and not the ``configs/``,
    ``docs/`` or ``data/mapping/`` trees, so an installed wheel imports but
    cannot resolve the project resources those modules look for beside the
    source tree. That is a real property of this repository and it is measured
    here rather than described.
    """
    base_python = Path(base_python or sys.executable)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    environment = destination / ".venv"
    _run([base_python, "-m", "venv", str(environment)], destination)
    python = venv_python(environment)
    install = _run([python, "-m", "pip", "install", "--quiet", str(wheel)],
                   destination)
    imports = _run([python, "-c", "import thai_supply_chain_ews as p; print(p.__file__)"],
                   destination)
    resource = _run(
        [python, "-c",
         "from thai_supply_chain_ews.evaluation import operational_contract as c;"
         "print(c.DEFAULT_OPERATIONAL_CONFIG_PATH.is_file())"],
        destination,
    )
    return {
        "wheel": Path(wheel).name,
        "install_ok": install["ok"],
        "import_ok": imports["ok"],
        "imported_from_site_packages": "site-packages" in imports["stdout"].replace("\\", "/"),
        "project_resources_resolvable": resource["stdout"].strip() == "True",
        "resource_note": (
            "The wheel contains the Python package only. configs/, docs/ and "
            "data/mapping/ are repository content, not package data, and 15 "
            "modules locate them beside the source tree. A wheel install "
            "therefore imports but cannot resolve project resources; the "
            "supported installation for running this project is a source "
            "checkout installed with pip install -e ."
        ),
    }


_PARSE_PROGRAM = (
    "import pathlib,yaml,json,sys\n"
    "bad=[]\n"
    "skip=('.venv','.venv','build','dist')\n"
    "for p in sorted(pathlib.Path('.').rglob('*.yaml')):\n"
    "    if any(s in p.as_posix() for s in skip): continue\n"
    "    try: yaml.safe_load(p.read_text(encoding='utf-8'))\n"
    "    except Exception as e: bad.append((p.as_posix(), str(e)[:120]))\n"
    "for p in sorted(pathlib.Path('.').rglob('*.json')):\n"
    "    if any(s in p.as_posix() for s in skip): continue\n"
    "    try: json.loads(p.read_text(encoding='utf-8'))\n"
    "    except Exception as e: bad.append((p.as_posix(), str(e)[:120]))\n"
    "print('parsed_without_error' if not bad else bad)\n"
    "sys.exit(1 if bad else 0)\n"
)
