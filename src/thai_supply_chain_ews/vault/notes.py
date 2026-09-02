"""The note model: frontmatter, checksums, links and the content guards.

A note is a rendered view of repository files, and it says so about itself. Its
frontmatter carries the paths it was generated from and a SHA-256 of its own
body, which makes two different things detectable:

*   the **repository** moved — the freshly rendered body differs from the one on
    disk, and the note is rewritten;
*   the **note** moved — the body on disk no longer matches the checksum that
    note declares, so somebody edited it by hand. That note is reported and left
    exactly as it is.

The second case is the one that matters. A generator that overwrites hand edits
teaches people not to trust it, and a generator that quietly keeps them creates
a second record that diverges. Reporting is the only option that does neither.

Three guards run over every body before it is written. None of them is
theoretical: a locked-outcome path in a note would be a read of a sealed file by
another name, an absolute path would publish somebody's home directory, and a
number that came from nowhere is the failure this whole project is built to
avoid.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Note",
    "NoteError",
    "assert_no_absolute_path",
    "assert_no_locked_path",
    "assert_sourced",
    "body_checksum",
    "classify_existing",
    "link",
    "parse_frontmatter",
    "slug",
]

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)

#: Characters Obsidian will not accept in a note filename.
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')


class NoteError(ValueError):
    """A note was asked to contain something it must not."""


def slug(title: str) -> str:
    """A filename Obsidian accepts, keeping the title readable."""
    cleaned = _UNSAFE.sub("", title).strip()
    return re.sub(r"\s+", " ", cleaned)


def link(title: str, alias: str = "") -> str:
    """A wikilink, aliased only when the display text genuinely differs."""
    target = slug(title)
    return f"[[{target}|{alias}]]" if alias and alias != target else f"[[{target}]]"


def body_checksum(body: str) -> str:
    """SHA-256 of a note body with trailing whitespace normalised.

    Normalised because an editor that strips trailing spaces on save would
    otherwise look like a hand edit, and a guard that cries wolf gets switched
    off.
    """
    normalised = "\n".join(line.rstrip() for line in body.strip().splitlines())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def parse_frontmatter(text: str) -> tuple:
    """Split a note into its frontmatter lines and its body.

    Deliberately not a YAML parse: this reads notes it wrote itself, in a shape
    it controls, and pulling in a parser to read back four scalar keys would be
    the more fragile choice.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta, current = {}, None
    for line in match.group(1).splitlines():
        if line.startswith("  - ") and current:
            meta[current].append(line[4:].strip())
        elif ": " in line and not line.startswith(" "):
            key, value = line.split(": ", 1)
            meta[key.strip()] = value.strip().strip('"')
            current = None
        elif line.endswith(":") and not line.startswith(" "):
            # A list key: `generated_from:` with its items on the lines below.
            current = line[:-1].strip()
            meta[current] = []
    return meta, match.group(2)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def assert_no_locked_path(body: str, fragments, where: str) -> None:
    """Refuse a note that names a locked-outcome path."""
    lowered = body.lower()
    offenders = sorted({f for f in fragments if f.lower() in lowered})
    if offenders:
        raise NoteError(
            f"{where} names locked-outcome path fragment(s) {offenders}. The "
            "locked final test is sealed: a note that points at it is a read of "
            "it by another name"
        )


def assert_no_absolute_path(body: str, patterns, where: str) -> None:
    """Refuse a note carrying somebody's home directory."""
    offenders = sorted({p for p in patterns if re.search(p, body)})
    if offenders:
        raise NoteError(
            f"{where} contains an absolute local path matching {offenders}. A "
            "note is a shareable document; a home directory in one publishes "
            "whose machine it was built on"
        )


def assert_sourced(note) -> None:
    """Refuse a note that claims to be generated from nothing."""
    if not note.generated_from:
        raise NoteError(
            f"{note.title!r} declares no source file. A note with no provenance "
            "is a claim nobody can check, which is the one thing this vault "
            "exists not to contain"
        )


# ---------------------------------------------------------------------------
# The note
# ---------------------------------------------------------------------------

@dataclass
class Note:
    """One generated note: a title, a body, and where both came from."""

    title: str
    kind: str
    body: str
    generated_from: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return f"{slug(self.title)}.md"

    def render(self, generated_by: str) -> str:
        """The complete note, frontmatter first."""
        checksum = body_checksum(self.body)
        lines = [
            "---",
            f"type: {self.kind}",
            "generated: true",
            f"generated_by: {generated_by}",
            f"content_sha256: {checksum}",
        ]
        for key, value in self.extra.items():
            if isinstance(value, (list, tuple)):
                lines.append(f"{key}:")
                lines.extend(f"  - {item}" for item in value)
            else:
                lines.append(f"{key}: {value}")
        lines.append("generated_from:")
        lines.extend(f"  - {path}" for path in self.generated_from)
        if self.tags:
            lines.append("tags:")
            lines.extend(f"  - {tag}" for tag in self.tags)
        lines.append("---")
        lines.append("")
        lines.append(self.body.strip())
        lines.append("")
        return "\n".join(lines)

    def guard(self, prohibitions: dict) -> None:
        """Run every content guard over this note before it can be written."""
        assert_sourced(self)
        where = f"note {self.title!r}"
        assert_no_locked_path(
            self.body, prohibitions["locked_outcome_path_fragments"], where
        )
        if prohibitions.get("no_absolute_paths"):
            assert_no_absolute_path(
                self.body, prohibitions["absolute_path_patterns"], where
            )


def classify_existing(path: Path, fresh_body: str) -> str:
    """What to do with a note that is already on disk.

    ``new`` — nothing there yet.
    ``unchanged`` — the freshly rendered body matches; leave the file alone so
    its modification time does not churn on every run.
    ``stale`` — the repository moved; rewrite it.
    ``hand_edited`` — the body on disk no longer matches the checksum the note
    declares about itself. Report it and write nothing.
    ``foreign`` — a file with this name exists but was not written by this
    generator. Never touched.
    """
    path = Path(path)
    if not path.exists():
        return "new"
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    if meta.get("generated") != "true" or "content_sha256" not in meta:
        return "foreign"
    if body_checksum(body) != meta["content_sha256"]:
        return "hand_edited"
    return "unchanged" if body_checksum(fresh_body) == meta["content_sha256"] else "stale"
