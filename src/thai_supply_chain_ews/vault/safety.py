"""Path safety for the vault generator: where it may write, and where it may not.

The generator writes **outside** the repository, into somebody's Obsidian vault.
That is the whole reason this module exists. A tool that writes into a directory
the user did not name, or that follows a symbolic link out of it, is a tool that
can damage files nobody asked it to touch, and the vault is not under version
control so there is nothing to recover from.

Three rules, and each is checked before any write happens rather than while one
is in progress.

**The destination is named, never inferred.** The vault root arrives as an
explicit argument. Earlier this generator derived it as ``repository/..`` from a
configuration value, which meant running it at all wrote into whatever directory
happened to contain the checkout. That is convenient exactly once and dangerous
every time after.

**A configured path is a relative path.** An absolute path, a drive-qualified
path, a leading separator or a ``..`` component in the contract would let the
configuration reach anywhere on the machine. Each is refused by name, so the
message says which rule was broken rather than only that something was wrong.

**Resolution is what counts, not spelling.** ``vault/notes`` may be a symbolic
link to somewhere else entirely, so every destination is resolved and required
to remain inside the resolved vault root. ``os.path.realpath`` resolves the
existing prefix of a path that does not exist yet, which is what a plan needs:
the check has to happen before the directory is created, not after.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

__all__ = [
    "VaultPathError",
    "assert_disjoint",
    "assert_outside",
    "real_path",
    "relative_parts",
    "require_directory",
    "resolve_within",
]


class VaultPathError(ValueError):
    """A path is not somewhere this generator is allowed to read or write."""


def real_path(path) -> Path:
    """The fully resolved path, following links, for paths that do not exist yet.

    ``Path.resolve()`` would do, but ``realpath`` states the intent plainly: the
    answer must be about where this lands on disk, not about how it was spelled.
    """
    return Path(os.path.realpath(str(path)))


def relative_parts(value: str, *, field: str) -> tuple:
    """Split a configured path, refusing everything that could escape.

    Returns the POSIX components. Each refusal is separate so the error names
    the rule rather than merely reporting that the value was unacceptable.
    """
    if not isinstance(value, str) or not value.strip():
        raise VaultPathError(f"{field} must be a non-empty relative path")
    if value.startswith(("/", "\\")):
        raise VaultPathError(
            f"{field} {value!r} starts with a separator, so it is not relative "
            "to the vault root"
        )
    if len(value) > 1 and value[1] == ":":
        raise VaultPathError(
            f"{field} {value!r} is drive-qualified; configured paths are "
            "relative to the vault root and name no drive"
        )
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute():
        raise VaultPathError(f"{field} {value!r} is an absolute path")
    if ".." in candidate.parts:
        raise VaultPathError(
            f"{field} {value!r} traverses upward; a managed path may not point "
            "outside the vault root it is relative to"
        )
    parts = tuple(part for part in candidate.parts if part != ".")
    if not parts:
        raise VaultPathError(f"{field} {value!r} names nothing")
    return parts


def resolve_within(base: Path, value: str, *, field: str) -> Path:
    """A configured relative path, resolved and confined to ``base``.

    The confinement check is on the **resolved** result, so a symbolic link
    inside the vault that points elsewhere is caught rather than followed.
    """
    resolved_base = real_path(base)
    candidate = resolved_base.joinpath(*relative_parts(value, field=field))
    resolved = real_path(candidate)
    if resolved != resolved_base and not _is_within(resolved, resolved_base):
        raise VaultPathError(
            f"{field} {value!r} resolves to {resolved}, which is outside the "
            f"vault root {resolved_base}. A symbolic link out of the vault is "
            "still a path out of the vault"
        )
    return candidate


def assert_outside(path, repository_root, *, field: str) -> Path:
    """Refuse a destination that lands inside the repository.

    The vault is a view. A generated view committed beside its source is the
    duplication this export exists to remove, and it would also make the release
    manifest describe files nobody wrote by hand.
    """
    resolved = real_path(path)
    repository = real_path(repository_root)
    if _is_within(resolved, repository) or resolved == repository:
        raise VaultPathError(
            f"{field} resolves to {resolved}, which is inside the repository "
            f"{repository}. The vault is a view of this repository and is never "
            "written inside it"
        )
    return resolved


def assert_disjoint(first, second, *, first_field: str, second_field: str) -> None:
    """Two directories must not contain one another.

    Used for the backup root against every managed output directory: a backup
    written inside the directory being modified is not a backup, and rolling one
    back would restore a copy of itself.
    """
    a, b = real_path(first), real_path(second)
    if a == b:
        raise VaultPathError(
            f"{first_field} and {second_field} are the same directory ({a})"
        )
    if _is_within(a, b):
        raise VaultPathError(
            f"{first_field} ({a}) is inside {second_field} ({b}); a backup kept "
            "inside the directory it protects is lost with it"
        )
    if _is_within(b, a):
        raise VaultPathError(
            f"{second_field} ({b}) is inside {first_field} ({a}); a managed "
            "output directory may not live inside the backup root"
        )


def require_directory(path, *, field: str) -> Path:
    """The path must already exist and be a directory.

    Creating a missing vault root would mean writing a vault somewhere nobody
    has one, which is a typo turning into a directory tree.
    """
    if path is None:
        raise VaultPathError(f"{field} is required and was not given")
    candidate = Path(path)
    if not candidate.exists():
        raise VaultPathError(
            f"{field} {candidate} does not exist. It is named explicitly and is "
            "never created for you"
        )
    if not candidate.is_dir():
        raise VaultPathError(f"{field} {candidate} is not a directory")
    return real_path(candidate)


def _is_within(candidate: Path, base: Path) -> bool:
    try:
        candidate.relative_to(base)
    except ValueError:
        return False
    return True
