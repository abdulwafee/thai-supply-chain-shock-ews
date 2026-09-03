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

Nothing here writes inside the repository. The notes go to an Obsidian vault
named explicitly on the command line, so the working tree stays clean and the
release manifest is untouched.

:mod:`safety` decides where the generator may write -- every configured path is
relative, resolved, and confined to the vault the operator named -- and
:mod:`transaction` makes an apply all-or-nothing: it copies whatever it could
disturb, writes atomically, and undoes the whole run if any step fails. The
vault is not under version control, so a half-finished run would have nothing to
recover from.
"""

from __future__ import annotations

__all__ = ["emit", "harvest", "notes", "safety", "transaction"]
