"""Obsidian vault export.

The vault is a **view** of this repository, never a second copy of it. Every
note is rendered from a file that was read during the run, carries the paths it
came from, and carries a checksum of its own body.

That checksum is the point. This vault already drifted once: seven documents sat
at its root as an early snapshot while the repository moved on, and one of them
showed four decisions where the repository had a hundred and seventy. A
generator that silently overwrites is how the *next* drift would happen in the
other direction, so :func:`notes.classify_existing` compares a note's body
against the checksum the note declares about itself, and a note that has been
edited by hand is reported and left alone.

Nothing here writes inside the repository. The notes go to the Obsidian vault
that contains it, so the working tree stays clean and the release manifest is
untouched.
"""

from __future__ import annotations

__all__ = ["emit", "harvest", "notes"]
