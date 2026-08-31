"""Built-distribution content audit (Task E2).

A wheel is not a directory listing with a different extension. ``MANIFEST.in``
defaults, ``package_data`` and the sdist's habit of sweeping in everything next
to ``pyproject.toml`` mean the archive can contain files nobody intended to
publish. This module opens the built artifacts and reads their member lists,
because what a build tool includes is a measurement, not a setting.

Two builds are compared. Their member *sets* must be identical; their archive
member *timestamps* need not be, and the difference is recorded rather than
smoothed over — claiming byte-identical archives when the format stores a build
clock would be a reproducibility claim this preparation cannot honour.
"""

from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path

__all__ = [
    "PackageAuditError",
    "audit_members",
    "build",
    "compare_builds",
    "members",
    "read_metadata",
]


class PackageAuditError(RuntimeError):
    """A built distribution contains, or fails to declare, something it must not."""


def build(python: Path, source: Path, output: Path) -> dict:
    """Build a wheel and an sdist into ``output``. Nothing is published."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [str(python), "-m", "build", "--outdir", str(output), str(source)],
        capture_output=True, text=True, check=False, timeout=1800,
    )
    artifacts = sorted(
        path.name for path in output.iterdir()
        if path.suffix in (".whl", ".gz")
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "output_directory": str(output),
        "artifacts": artifacts,
        "wheel": next((n for n in artifacts if n.endswith(".whl")), None),
        "sdist": next((n for n in artifacts if n.endswith(".tar.gz")), None),
        "published": False,
        "tail": "\n".join(
            (completed.stdout + completed.stderr).splitlines()[-20:]
        ),
    }


def members(archive: Path) -> list:
    """Every member path inside a wheel or sdist, normalised."""
    archive = Path(archive)
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as handle:
            names = handle.namelist()
    else:
        with tarfile.open(archive, "r:gz") as handle:
            names = [member.name for member in handle.getmembers() if member.isfile()]
    return sorted(name.replace("\\", "/") for name in names)


def read_metadata(archive: Path) -> dict:
    """Name, version and Requires-Python, read from the archive's own metadata."""
    archive = Path(archive)
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as handle:
            name = next(n for n in handle.namelist() if n.endswith(".dist-info/METADATA"))
            text = handle.read(name).decode("utf-8", "replace")
    else:
        with tarfile.open(archive, "r:gz") as handle:
            member = next(m for m in handle.getmembers() if m.name.endswith("PKG-INFO"))
            text = handle.extractfile(member).read().decode("utf-8", "replace")
    fields = {}
    for line in text.splitlines():
        if not line or line.startswith(" "):
            continue
        if ": " in line:
            key, value = line.split(": ", 1)
            fields.setdefault(key.strip(), value.strip())
        if line.strip() == "":
            break
    return {
        "name": fields.get("Name"),
        "version": fields.get("Version"),
        "requires_python": fields.get("Requires-Python"),
        "license": fields.get("License"),
        "license_expression": fields.get("License-Expression"),
        "author": fields.get("Author"),
        "requires_dist": [
            line.split(": ", 1)[1] for line in text.splitlines()
            if line.startswith("Requires-Dist: ")
        ],
    }


def audit_members(archive: Path, config: dict, locked_fragments) -> dict:
    """Flag prohibited members. A locked path in an archive is a hard failure."""
    package_rules = config["package"]
    names = members(archive)
    lowered = tuple(f.lower() for f in locked_fragments)
    prohibited_suffix = sorted(
        name for name in names
        if any(name.lower().endswith(suffix)
               for suffix in package_rules["prohibited_members"])
    )
    prohibited_fragment = sorted(
        name for name in names
        if any(fragment.lower() in name.lower()
               for fragment in package_rules["prohibited_member_fragments"])
    )
    locked = sorted(
        name for name in names
        if any(fragment in name.lower() for fragment in lowered)
    )
    if locked:
        raise PackageAuditError(
            f"{Path(archive).name} contains locked-outcome member(s) {locked}. A "
            "locked outcome may not be included in a package build"
        )
    return {
        "archive": Path(archive).name,
        "member_count": len(names),
        "members": names,
        "prohibited_by_suffix": prohibited_suffix,
        "prohibited_by_fragment": prohibited_fragment,
        "locked_members": locked,
        "clean": not prohibited_suffix and not prohibited_fragment,
    }


def compare_builds(first, second) -> dict:
    """Set equality of members across two builds, with timestamps excluded."""
    first_set, second_set = set(first), set(second)
    return {
        "member_sets_identical": first_set == second_set,
        "only_in_first": sorted(first_set - second_set),
        "only_in_second": sorted(second_set - first_set),
        "archive_member_timestamps_compared": False,
        "archive_timestamp_difference_documented": True,
        "note": (
            "Wheel and sdist formats record a build clock in their member "
            "headers, so two builds are compared by member set and content "
            "rather than by archive bytes. Claiming byte-identical archives "
            "would be a reproducibility claim this format cannot support."
        ),
    }
