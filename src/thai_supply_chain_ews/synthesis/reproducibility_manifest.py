"""The reproducibility manifest (Task E1).

Records what a stranger needs to rebuild the evidence: artifact paths and their
content checksums, task statuses and supersession, which files are generated and
which are version-controlled, the environment and commands, and the current test
and lint results.

**The test count is measured, not quoted.** A number typed into a report drifts
from the suite the moment a test is added, and a stale count in a
reproducibility manifest is worse than none — it looks like evidence.
:func:`measure_test_count` runs the suite and parses its summary line, and
:func:`assert_measured` raises if a caller tries to hand in a literal instead.

**Raw-file manifests are referenced, not copied.** ``EPPO_PRICE_STRUCTURE_manifest.jsonl``
has 1,336 lines recording every acquired attachment. Duplicating it here would
create a second copy to drift; the manifest points at the original.

**Nothing here reaches a locked outcome.** The manifest records that the locked
test is sealed by reading the key-only reservation, and it stores no locked
path, digest or summary.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "MANIFEST_VERSION",
    "ManifestError",
    "artifact_record",
    "assert_measured",
    "assert_no_locked_path",
    "manifest_checksum",
    "measure_ruff",
    "measure_test_count",
]

MANIFEST_VERSION = "e1_reproducibility_manifest_v1"

_PYTEST_SUMMARY = re.compile(r"(\d+) passed")
_PYTEST_FAILED = re.compile(r"(\d+) failed")

#: Any path fragment that would mean the manifest itself touched locked data.
_LOCKED_FRAGMENTS = ("locked_test/", "locked_outcome", "locked_target",
                     "locked_prediction", "locked_score")


class ManifestError(ValueError):
    """The manifest was asked to record something it must measure, or must not."""


def assert_measured(value: dict) -> dict:
    """Raise unless a count came from a run rather than from a literal."""
    if not isinstance(value, dict) or not value.get("measured"):
        raise ManifestError(
            "the test count was supplied rather than measured. A number typed "
            "into a reproducibility manifest drifts from the suite the moment a "
            "test is added, and a stale count looks like evidence"
        )
    if value.get("command") in (None, ""):
        raise ManifestError("a measured result must record the command that produced it")
    return value


def assert_no_locked_path(paths) -> None:
    """Raise if the manifest would record a locked-test path."""
    offenders = sorted(
        str(p) for p in paths
        if any(fragment in str(p).replace("\\", "/").lower()
               for fragment in _LOCKED_FRAGMENTS)
    )
    if offenders:
        raise ManifestError(
            f"the manifest would record locked-test path(s) {offenders}. The "
            "locked reservation is key-only and no locked artifact is referenced"
        )


def measure_test_count(root: Path, timeout: int = 900) -> dict:
    """Run the suite and read the count off its own summary line."""
    command = [sys.executable, "-m", "pytest", "-q"]
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command, cwd=str(root), capture_output=True, text=True, timeout=timeout,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    passed = _PYTEST_SUMMARY.search(output)
    failed = _PYTEST_FAILED.search(output)
    if passed is None:
        raise ManifestError(
            "pytest produced no summary line, so the test count could not be "
            f"measured. Exit code {completed.returncode}"
        )
    return {
        "measured": True,
        "command": " ".join(["python", "-m", "pytest", "-q"]),
        "tests_passed": int(passed.group(1)),
        "tests_failed": int(failed.group(1)) if failed else 0,
        "exit_code": completed.returncode,
        "all_passing": completed.returncode == 0 and not failed,
        "measured_at_utc": datetime.now(UTC).isoformat(),
    }


def measure_ruff(root: Path, timeout: int = 300) -> dict:
    """Run the linter and record what it actually said."""
    command = [sys.executable, "-m", "ruff", "check", "."]
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command, cwd=str(root), capture_output=True, text=True, timeout=timeout,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    return {
        "measured": True,
        "command": "python -m ruff check .",
        "exit_code": completed.returncode,
        "passing": completed.returncode == 0,
        "summary": output.splitlines()[-1] if output else "",
        "measured_at_utc": datetime.now(UTC).isoformat(),
    }


def artifact_record(root: Path, relative: str, task: str, generated: bool,
                    status: str, superseded_by: str = None) -> dict:
    """One artifact: where it is, what it hashes to, and whether it is generated.

    A *content* checksum is used where the document carries one, because it
    excludes generation timestamps and is therefore the durable identity. A byte
    digest is recorded otherwise, and labelled as such so nobody mistakes a
    timestamped file's digest for a stable one.
    """
    path = root / relative
    record = {
        "path": relative.replace("\\", "/"),
        "task": task,
        "exists": path.is_file(),
        "generated": bool(generated),
        "version_controlled": not generated,
        "status": status,
    }
    if superseded_by:
        record["superseded_by"] = superseded_by
    if not path.is_file():
        record["checksum"] = None
        record["checksum_kind"] = None
        return record
    if path.suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("content_checksum"):
            record["checksum"] = payload["content_checksum"]
            record["checksum_kind"] = "content_checksum_timestamps_excluded"
            return record
    record["checksum"] = hashlib.sha256(path.read_bytes()).hexdigest()
    record["checksum_kind"] = "byte_sha256"
    return record


def manifest_checksum(payload) -> str:
    """Digest of the manifest, excluding the timestamps of its own measurements."""
    dropped = {"generated_at_utc", "measured_at_utc", "run_started_at_utc",
               "run_finished_at_utc"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
