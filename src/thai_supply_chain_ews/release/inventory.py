"""Filesystem inventory and the fail-closed public-release allowlist (Task E2).

The inventory is walked from the **filesystem**, cross-checked against git, and
never inferred from documentation — a README that says what ships is a claim,
and the point of this module is to check the claim.

**The allowlist fails closed.** A path that matches no include rule is
*excluded* and reported as unclassified. That inversion is the whole design:
the file that leaks is never the one somebody considered and got wrong, it is
the one nobody thought about — a stray `.env.local`, a notebook with output
still in it, a cached response someone dropped into `data/`. An allowlist that
admits by default would ship all three.

**Locked paths are identified from path metadata alone.** They are matched by
name fragment, never opened, never hashed, never handed to a scanner and never
copied. Hashing a locked outcome would still be reading it, and a size read is
already an inference about its contents, so :func:`locked_paths` returns paths
and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = [
    "DEFAULT_SKIP_DIRECTORIES",
    "FileRecord",
    "InventoryError",
    "assert_no_locked_path",
    "build_inventory",
    "categorise",
    "classify_release",
    "git_paths",
    "glob_match",
    "locked_paths",
    "manifest_checksum",
    "release_manifest",
]

DEFAULT_SKIP_DIRECTORIES = (
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "node_modules",
)


class InventoryError(ValueError):
    """The inventory was asked to admit or touch something it may not."""


@dataclass
class FileRecord:
    """One path, its size, its category and its release verdict."""

    path: str
    size_bytes: int = 0
    category: str = "unclassified"
    tracked: bool = False
    ignored: bool = False
    in_release: bool = False
    reason: str = ""
    locked: bool = False
    sha256: str = None

    def to_dict(self) -> dict:
        return {
            "path": self.path, "size_bytes": self.size_bytes,
            "category": self.category, "tracked": self.tracked,
            "ignored": self.ignored, "in_release": self.in_release,
            "reason": self.reason, "locked": self.locked, "sha256": self.sha256,
        }


def _run_git(root: Path, *arguments) -> list:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *arguments], cwd=str(root), capture_output=True, text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def git_paths(root: Path) -> dict:
    """Tracked, ignored and would-be-staged paths, measured from git itself."""
    tracked = {line.strip() for line in _run_git(root, "ls-files")}
    ignored = {
        line[3:].strip().strip('"')
        for line in _run_git(root, "status", "--porcelain", "--ignored")
        if line.startswith("!!")
    }
    staged_dry_run = {
        line.split("'", 1)[1].rsplit("'", 1)[0]
        for line in _run_git(root, "add", "-A", "--dry-run")
        if "'" in line
    }
    commits = _run_git(root, "rev-list", "--count", "HEAD")
    return {
        "tracked": tracked,
        "ignored": ignored,
        "would_be_staged": staged_dry_run,
        "commit_count": int(commits[0]) if commits else 0,
    }


def locked_paths(paths, fragments) -> list:
    """Locked-outcome paths, matched by NAME only.

    No file is opened, stat-ed or hashed here. A size read is already an
    inference about contents, and this function is the one place that must be
    able to say it made none.
    """
    lowered = tuple(f.lower() for f in fragments)
    return sorted(
        path for path in paths
        if any(fragment in str(path).replace("\\", "/").lower()
               for fragment in lowered)
    )


def assert_no_locked_path(paths, fragments, operation: str) -> None:
    """Raise if a locked-outcome path would be touched by ``operation``."""
    offenders = locked_paths(paths, fragments)
    if offenders:
        raise InventoryError(
            f"{operation} would touch locked-outcome path(s) {offenders}. The "
            "locked final test is sealed: its paths are identified by name and "
            "never opened, hashed, scanned, packaged or copied"
        )


def categorise(path: str, categories: dict) -> str:
    """The first category whose root and suffix both match, or ``unclassified``.

    Order matters and the caller controls it: ``data/raw/_manifests/`` has to be
    tested before ``data/raw/``, because the manifests ship and the workbooks do
    not.
    """
    normalised = str(path).replace("\\", "/")
    suffix = Path(normalised).suffix.lower()
    for name, rule in categories.items():
        roots = rule.get("roots") or [""]
        suffixes = [s.lower() for s in (rule.get("suffixes") or [])]
        for root in roots:
            if root and not normalised.startswith(root):
                continue
            if root == "" and "/" in normalised:
                continue
            if suffixes and suffix not in suffixes:
                continue
            return name
    return "unclassified"


@lru_cache(maxsize=512)
def _compiled(pattern: str):
    """Translate a glob to a regex, giving ``**`` its recursive meaning.

    ``fnmatch`` is not usable here: its ``*`` crosses directory separators, so
    ``src/**/*.py`` would silently fail to match ``src/config.py`` while
    ``docs/*.md`` would match ``docs/architecture/decision_log.md``. Both errors
    change what ships.
    """
    out, index = [], 0
    while index < len(pattern):
        character = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:[^/]+/)*")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif character == "*":
            out.append("[^/]*")
            index += 1
        elif character == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(character))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def glob_match(path: str, pattern: str) -> bool:
    """Whether ``path`` matches one release glob."""
    return bool(_compiled(pattern).match(str(path).replace("\\", "/")))


def classify_release(path: str, include_globs, exclude_globs,
                     exemptions=()) -> tuple:
    """Decide whether one path ships. Exclusion wins; unmatched fails closed.

    An ``exemption`` lets a single file escape a directory-wide exclusion, and it
    is deliberately awkward to use: it must be a **literal path**, and the file
    must *also* match an include glob. Two independent decisions are required to
    admit anything from an excluded directory, so an exemption cannot widen the
    release the way a stray wildcard could.
    """
    normalised = str(path).replace("\\", "/")
    exempt = normalised in {str(e).replace("\\", "/") for e in exemptions}
    if exempt and any("*" in str(e) or "?" in str(e) for e in exemptions):
        raise InventoryError(
            "exclude exemptions must be literal paths; a wildcard exemption "
            "would let an excluded directory reopen without anyone deciding to"
        )
    excluded_by = next(
        (p for p in exclude_globs if glob_match(normalised, p)), None
    )
    included_by = next(
        (p for p in include_globs if glob_match(normalised, p)), None
    )
    if excluded_by and not (exempt and included_by):
        return False, f"excluded_by:{excluded_by}"
    if included_by:
        return True, (f"exempted_from:{excluded_by}" if excluded_by
                      else f"included_by:{included_by}")
    return False, "fail_closed_unclassified"


def build_inventory(root: Path, config: dict) -> dict:
    """Walk the filesystem, categorise every file, and decide what ships."""
    inventory_rules = config["inventory"]
    allow = config["allowlist"]
    locked_fragments = config["locked_test"]["outcome_path_fragments"]
    skip = set(inventory_rules.get("skip_directories") or DEFAULT_SKIP_DIRECTORIES)
    large_threshold = int(inventory_rules["large_file_threshold_bytes"])

    git = git_paths(root)
    records = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            absolute = Path(dirpath) / name
            relative = absolute.relative_to(root).as_posix()
            is_locked = bool(locked_paths([relative], locked_fragments))
            record = FileRecord(
                path=relative,
                # A locked path is never stat-ed: its size is metadata about
                # contents we have undertaken not to learn.
                size_bytes=0 if is_locked else absolute.stat().st_size,
                category=categorise(relative, inventory_rules["categories"]),
                tracked=relative in git["tracked"],
                ignored=relative in git["ignored"],
                locked=is_locked,
            )
            in_release, reason = classify_release(
                relative, allow["include_globs"], allow["exclude_globs"],
                allow.get("exclude_exemptions", ()),
            )
            if is_locked:
                in_release, reason = False, "locked_test_path_excluded_by_name"
            record.in_release, record.reason = in_release, reason
            records.append(record)

    by_category = {}
    for record in records:
        entry = by_category.setdefault(
            record.category, {"files": 0, "bytes": 0, "in_release": 0}
        )
        entry["files"] += 1
        entry["bytes"] += record.size_bytes
        entry["in_release"] += int(record.in_release)

    unclassified = sorted(r.path for r in records if r.category == "unclassified")
    fail_closed = sorted(
        r.path for r in records if r.reason == "fail_closed_unclassified"
    )
    return {
        "root": str(root),
        "source": "filesystem_and_git",
        "inferred_from_documentation": False,
        "total_files": len(records),
        "total_bytes": sum(r.size_bytes for r in records),
        "by_category": dict(sorted(by_category.items())),
        "release_files": sum(1 for r in records if r.in_release),
        "release_bytes": sum(r.size_bytes for r in records if r.in_release),
        "large_files": sorted(
            (r.path for r in records if r.size_bytes >= large_threshold),
        ),
        "large_file_threshold_bytes": large_threshold,
        "unclassified_paths": unclassified,
        "fail_closed_exclusions": len(fail_closed),
        "fail_closed_examples": fail_closed[:10],
        "git": {
            "tracked": len(git["tracked"]),
            "ignored": len(git["ignored"]),
            "would_be_staged": len(git["would_be_staged"]),
            "commit_count": git["commit_count"],
        },
        "locked_paths_seen": sorted(r.path for r in records if r.locked),
        "records": records,
    }


def release_manifest(records, root: Path, config: dict,
                     redistribution: dict = None,
                     package_members: set = None,
                     self_referential: tuple = ()) -> dict:
    """The deterministic release-candidate manifest.

    Hashes are computed for release files only, and never for a locked path.
    Acquisition timestamps are deliberately absent from the digest so the
    manifest checksum is a statement about *content*, not about when the tree
    was assembled.

    ``self_referential`` names the documents that record this manifest's own
    checksum. They ship, but their digests are not rows: a manifest that listed
    the report quoting its own digest could never reach a fixed point, and its
    checksum would change on every run whether or not anything else did. This is
    the same reason a ``SHA256SUMS`` file does not list itself.
    """
    redistribution = redistribution or {}
    package_members = package_members or set()
    excluded = {str(p).replace("\\", "/") for p in self_referential}
    locked_fragments = config["locked_test"]["outcome_path_fragments"]
    rows = []
    for record in sorted((r for r in records if r.in_release),
                         key=lambda r: r.path):
        if record.path in excluded:
            continue
        assert_no_locked_path([record.path], locked_fragments, "manifest hashing")
        digest = hashlib.sha256((root / record.path).read_bytes()).hexdigest()
        record.sha256 = digest
        rows.append({
            "path": record.path,
            "sha256": digest,
            "size_bytes": record.size_bytes,
            "category": record.category,
            "redistribution_status": redistribution.get(
                record.category, "project_owned"
            ),
            "generated": record.category in (
                "generated_tables", "model_and_prediction_tables"
            ),
            "tracked": record.tracked,
            "package_included": record.path in package_members,
            "ci_included": record.category in (
                "source_code", "tests_and_fixtures", "configuration", "schemas",
                "packaging_and_ci",
            ),
            "locked_test_dependency": False,
            "license_status": redistribution.get(
                f"{record.category}__license", "project_code_license_undecided"
            ),
            "reproduction_tier": _tier_for(record.category),
        })
    return {
        "release_contract_version": config["release_contract_version"],
        "release_candidate_version": config["release_candidate_version"],
        "file_count": len(rows),
        "release_file_count": sum(1 for r in records if r.in_release),
        "total_bytes": sum(r["size_bytes"] for r in rows),
        "acquisition_timestamps_in_checksum": False,
        "generation_timestamps_in_checksum": False,
        "self_referential_exclusions": sorted(excluded),
        "self_referential_exclusion_reason": (
            "These documents ship with the release but are not rows in it: they "
            "record this manifest's own checksum, so hashing them here could "
            "never reach a fixed point. A SHA256SUMS file does not list itself "
            "for the same reason."
        ),
        "files": rows,
    }


def _tier_for(category: str) -> str:
    if category in ("raw_third_party_documents", "cached_downloads",
                    "retrieval_manifests"):
        return "tier_2_source_audit_reproduction"
    if category in ("generated_tables", "model_and_prediction_tables"):
        return "tier_3_full_historical_reproduction"
    return "tier_1_code_verification"


def manifest_checksum(manifest: dict) -> str:
    """Digest over the ordered manifest rows, timestamps excluded by construction."""
    payload = [
        [row["path"], row["sha256"], row["size_bytes"], row["category"],
         row["redistribution_status"], row["generated"], row["package_included"],
         row["ci_included"], row["locked_test_dependency"], row["license_status"],
         row["reproduction_tier"]]
        for row in manifest["files"]
    ]
    text = json.dumps(
        {"version": manifest["release_contract_version"], "files": payload},
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
