"""Canonical byte digests, and the provenance of the ones that are not (Task CI-R1).

Some of this project's earliest checksums recorded the platform instead of the
content. A runner wrote a document with ``Path.write_text`` on Windows, where
``\\n`` becomes ``\\r\\n`` on disk, hashed the file it had just written, and
recorded that digest as a permanent claim. Git normalised the same file to LF on
commit, so on any Linux checkout the file no longer matches the pin that was
supposed to prove it had not been edited. Nothing was ever edited. The digest was
simply a measurement of the working tree rather than of the text.

Two rules follow, and they are separate on purpose.

**Going forward, every digest of a text file is canonical.** ``\\r\\n`` is
normalised to ``\\n`` before hashing, so the value means the same thing on every
platform. Binary artifacts keep raw-byte hashing -- normalising a Parquet file or
a PNG would corrupt it -- and each such site is declared rather than assumed.

**Going backward, the ten historical pins are neither edited nor abandoned.** For
each affected path a sidecar declares which representation its pin was taken
from. Verification then does two independent things: it checks the canonical
content against the immutable v1.0.0 blob, and it re-renders that canonical
content in the declared representation and requires the *original, unmodified*
pin to come back out. A content edit fails both; a line-ending difference is
tolerated only for a path that says so, in the exact representation it declares.

Three paths cannot be re-rendered at all. Their working trees mixed CRLF with
bare LF at generation time, and that pattern is not recoverable from content. They
are declared ``unreproducible`` and verified on canonical content alone. Claiming
otherwise would repeat the original mistake in a new place.

**Everything historical is read from git objects, never from the working tree.**
A branch that edits ``docs/architecture/decision_log.md`` -- as the branch
introducing this module does -- must not thereby change what the v1.0.0 record
says. All reads go through ``git cat-file`` against a pinned commit, and no
operation here touches the network.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import yaml

__all__ = [
    "CANONICAL_LF",
    "CRLF",
    "LF",
    "RAW_BYTES",
    "LineEndingError",
    "UNREPRODUCIBLE",
    "WINDOWS_CRLF_WORKTREE",
    "bare_lf_count",
    "blob_content",
    "blob_object_id",
    "canonical_bytes",
    "canonical_digest",
    "digest",
    "is_git_checkout",
    "is_pure",
    "load_provenance",
    "looks_binary",
    "match_declared_representation",
    "provenance_entries",
    "release_digest",
    "render",
    "require_commit_present",
    "require_subject_history",
    "resolve",
    "verify_legacy_pin",
]

LF = b"\n"
CRLF = b"\r\n"

#: The one representation every new pin is taken from.
CANONICAL_LF = "canonical_lf"

#: Binary content, hashed exactly as it is. Normalising a Parquet file or a
#: workbook would corrupt it, so these are never canonicalised.
RAW_BYTES = "raw_bytes"

#: A digest taken from a Windows working tree, where the file was CRLF on disk
#: while git stored it as LF.
WINDOWS_CRLF_WORKTREE = "windows_crlf_worktree"

#: The generation-time bytes mixed CRLF and bare LF. Content alone cannot
#: reconstruct that, so the pin is preserved and verified as preserved, never
#: re-derived.
UNREPRODUCIBLE = "unreproducible_mixed_worktree"

PROVENANCE_PATH = "configs/line_ending_provenance.yaml"


class LineEndingError(ValueError):
    """A digest could not be verified, or a representation claim is unsound."""


# ---------------------------------------------------------------------------
# Bytes
# ---------------------------------------------------------------------------

def canonical_bytes(data: bytes) -> bytes:
    """``data`` with CRLF collapsed to LF. Idempotent."""
    return data.replace(CRLF, LF)


def digest(data: bytes) -> str:
    """SHA-256 of exactly these bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_digest(data: bytes) -> str:
    """SHA-256 of the canonical form. **Use this for every new text pin.**"""
    return digest(canonical_bytes(data))


def looks_binary(data: bytes) -> bool:
    """Whether content must be hashed raw rather than canonicalised.

    A NUL byte near the start is the signal Git itself uses, and it is decisive
    here: every binary this project ships -- Parquet, workbooks, PNG, archives
    -- carries one, and no text file it ships does.
    """
    return b"\x00" in data[:8000]


def release_digest(data: bytes) -> tuple[str, str]:
    """The digest to record for release content, and what it was taken from.

    Text is canonical, so the value means the same thing on Windows and Linux.
    Binary is raw. The representation travels *with* the digest instead of being
    remembered somewhere else, which is exactly what the historical pins failed
    to do.
    """
    if looks_binary(data):
        return digest(data), RAW_BYTES
    return canonical_digest(data), CANONICAL_LF


def bare_lf_count(data: bytes) -> int:
    """Line feeds that are not part of a CRLF pair."""
    return data.replace(CRLF, b"").count(LF)


def is_pure(data: bytes) -> bool:
    """Whether the line endings are uniform, so a representation is well defined.

    Uniform means all CRLF or all LF. A partially converted file is neither, has
    no single representation, and must not be given one -- tolerating a mixture
    is how a real change would hide behind a line-ending excuse.
    """
    without_pairs = data.replace(CRLF, b"")
    if b"\r" in without_pairs:
        return False
    return CRLF not in data or LF not in without_pairs


def render(canonical: bytes, representation: str) -> bytes:
    """Re-express canonical content in a declared representation."""
    if representation == CANONICAL_LF:
        return canonical
    if representation == WINDOWS_CRLF_WORKTREE:
        return canonical.replace(LF, CRLF)
    raise LineEndingError(
        f"{representation!r} cannot be rendered from content. "
        f"{UNREPRODUCIBLE!r} is declared precisely because it cannot be, and a "
        "renderer for it would be a fabrication"
    )


# ---------------------------------------------------------------------------
# Read-only git object access. Local objects only; never the working tree.
# ---------------------------------------------------------------------------

def _git(root: Path, *arguments) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, no network
        ["git", *arguments], cwd=str(root), capture_output=True, check=False,
    )


def resolve(root: Path, revision: str) -> str:
    """Resolve a revision to a commit id, or raise."""
    completed = _git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if completed.returncode != 0:
        raise LineEndingError(
            f"{revision!r} does not resolve to a commit in this repository. "
            "Historical verification reads only local git objects and never "
            "fetches, so a missing object is reported rather than worked around"
        )
    return completed.stdout.decode().strip()


def require_commit_present(root: Path, commit: str) -> str:
    """The subject commit must be in this clone. A shallow clone fails loudly."""
    resolved = resolve(root, commit)
    if resolved != commit:
        raise LineEndingError(
            f"{commit!r} resolved to {resolved!r}; the subject commit must be "
            "given as a full immutable id"
        )
    return resolved


def is_git_checkout(root: Path) -> bool:
    """Whether there is a git object database here at all.

    False in a release tree built from the allowlist, or in a downloaded
    archive. Those cannot verify history because they have none -- which is a
    different situation from a clone that has history and did not fetch it.
    """
    return _git(Path(root), "rev-parse", "--git-dir").returncode == 0


def require_subject_history(root: Path, commit: str, tag: str) -> dict:
    """The subject commit and its tag must be present, and must agree.

    Raises rather than returning a verdict. A shallow clone is a fetch setting
    somebody can change, so turning it into a pass would hide a fixable gap, and
    turning it into a bare skip would hide it just as effectively while looking
    tidier. The message says exactly what to change.
    """
    root = Path(root)
    if _git(root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        raise LineEndingError(
            f"the subject commit {commit} is not in this clone, so the "
            "historical record cannot be read. GitHub Actions checks out a "
            "single commit by default; set fetch-depth: 0 on actions/checkout "
            "so the full history and tags are fetched. Nothing here fetches "
            "over the network on its own"
        )
    completed = _git(root, "rev-parse", "--verify", f"{tag}^{{commit}}")
    if completed.returncode != 0:
        raise LineEndingError(
            f"the annotated tag {tag!r} is not in this clone. actions/checkout "
            "fetches tags only with fetch-depth: 0; without it the release this "
            "record describes cannot be identified"
        )
    dereferenced = completed.stdout.decode().strip()
    if dereferenced != commit:
        raise LineEndingError(
            f"{tag!r} dereferences to {dereferenced}, not to the subject commit "
            f"{commit}. The tag has moved, and every pin here describes the "
            "commit rather than whatever the tag now points at"
        )
    return {"commit": commit, "tag": tag, "tag_object": _git(
        root, "rev-parse", tag).stdout.decode().strip(), "dereferences_to": commit}


def blob_object_id(root: Path, commit: str, path: str) -> str:
    """Git's object id for a path at a commit. NOT a SHA-256 of the content."""
    completed = _git(root, "rev-parse", f"{commit}:{path}")
    if completed.returncode != 0:
        raise LineEndingError(f"{path!r} is not present in the tree at {commit}")
    return completed.stdout.decode().strip()


def blob_content(root: Path, commit: str, path: str) -> bytes:
    """The exact content bytes of a path at a commit, from the object database."""
    completed = _git(root, "cat-file", "blob", f"{commit}:{path}")
    if completed.returncode != 0:
        raise LineEndingError(f"{path!r} is not present in the tree at {commit}")
    return completed.stdout


# ---------------------------------------------------------------------------
# The provenance sidecar
# ---------------------------------------------------------------------------

def load_provenance(root: Path) -> dict:
    """The declared representation of every historical pin."""
    text = (Path(root) / PROVENANCE_PATH).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def provenance_entries(root: Path) -> dict:
    """The sidecar's entries by path, or nothing at all if it is not there.

    A tree without the sidecar simply carries no declarations, so every pin has
    to match its recorded bytes outright. Absence never becomes permission.
    """
    try:
        loaded = load_provenance(root)
    except (FileNotFoundError, NotADirectoryError):
        return {}
    return {entry["path"]: entry for entry in loaded.get("entries", [])}


def match_declared_representation(content: bytes, historical_pin: str,
                                  entry: dict | None) -> str | None:
    """Whether unchanged content explains a pin taken on another platform.

    Returns the declared representation when it does, ``None`` when it does not.

    This is deliberately not a search over representations. The sidecar names
    one representation for one path, the canonical content has to agree first,
    and the declared render must reproduce the original pin exactly. A file
    whose text really changed fails all three, so nothing hides behind a
    line-ending excuse.
    """
    if entry is None or entry.get("legacy_sha256") != historical_pin:
        return None
    if canonical_digest(content) != entry["canonical_git_blob_content_sha256"]:
        return None
    representation = entry["legacy_representation"]
    if representation == UNREPRODUCIBLE:
        return representation if entry.get(
            "independently_reproducible") is False else None
    if not is_pure(content):
        return None
    rendered = render(canonical_bytes(content), representation)
    return representation if digest(rendered) == historical_pin else None


def verify_legacy_pin(root: Path, path: str, historical_pin: str,
                      entry: dict, commit: str) -> dict:
    """Verify one pin against the immutable tree, without editing it.

    Four gates, each able to fail on its own:

    0. the file's line endings are uniform, so its representation is defined;
    1. canonical content matches the digest the sidecar declares;
    2. re-rendering that content in the declared representation reproduces the
       original pin, byte for byte;
    3. the sidecar has not restated the pin differently from the document it
       was copied from.
    """
    root = Path(root)
    representation = entry["legacy_representation"]
    content = blob_content(root, commit, path)
    canonical = canonical_bytes(content)

    if entry["legacy_sha256"] != historical_pin:
        raise LineEndingError(
            f"the sidecar records {entry['legacy_sha256'][:12]}… for {path} while "
            f"its source document records {historical_pin[:12]}…. The sidecar "
            "copies a pin; it never becomes a second place one is stated"
        )

    if canonical_digest(content) != entry["canonical_git_blob_content_sha256"]:
        raise LineEndingError(
            f"{path} canonical content does not match its declared digest. This "
            "is a content change, not a line-ending difference"
        )

    if representation == UNREPRODUCIBLE:
        # The declaration must actively refute reproducibility, so that a later
        # relabelling to a rendered representation cannot pass quietly.
        if entry.get("independently_reproducible") is not False:
            raise LineEndingError(
                f"{path} is declared {UNREPRODUCIBLE!r} but does not record "
                "independently_reproducible: false"
            )
        if digest(render(canonical, WINDOWS_CRLF_WORKTREE)) == historical_pin:
            raise LineEndingError(
                f"{path} is declared unreproducible, yet a uniform CRLF render "
                "does reproduce its pin. The declaration is wrong"
            )
        return {"path": path, "representation": representation,
                "canonical_verified": True, "legacy_reproduced": False,
                "independently_reproducible": False}

    if not is_pure(content):
        raise LineEndingError(
            f"{path} has mixed line endings ({bare_lf_count(content)} bare line "
            f"feeds), so {representation!r} is not a well-defined claim about it"
        )

    if digest(render(canonical, representation)) != historical_pin:
        raise LineEndingError(
            f"{path} does not reproduce its historical pin when rendered as "
            f"{representation!r}"
        )

    return {"path": path, "representation": representation,
            "canonical_verified": True, "legacy_reproduced": True,
            "independently_reproducible": True}
