"""Generate the Obsidian vault view of this repository.

Takes NO command-line arguments. There is no flag that makes it write inside the
repository, overwrite a hand-edited note, or emit a locked-outcome path.

It writes to the Obsidian vault that *contains* this repository, so `git status`
stays clean and the release manifest is untouched. Only this script, its
contract and its tests are version-controlled.

Run it after any task that changes documents, decisions or configuration:

    python scripts/build_obsidian_vault.py

A note that somebody has edited by hand is reported and left alone. That is the
whole design. This vault already drifted once — seven documents sat at its root
as a snapshot from around Task A1 while the repository moved on, one of them
showing four decisions where the repository had a hundred and seventy — and a
generator that overwrites silently is how the same thing would happen again in
the other direction.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.vault import emit, harvest, notes  # noqa: E402

CONFIG_PATH = ROOT / "configs" / "obsidian_vault.yaml"


def load_contract() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def assert_outside_repository(target: Path) -> None:
    """The vault must not be written inside the repository."""
    try:
        target.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return
    raise SystemExit(
        f"refusing to write to {target}: it is inside the repository. The vault "
        "is a view, and a generated view committed alongside its source is the "
        "duplication this export exists to remove."
    )


def write_notes(rendered, folder: Path, generated_by: str, prohibitions: dict) -> dict:
    """Write what changed, skip what did not, and never touch a hand edit."""
    folder.mkdir(parents=True, exist_ok=True)
    tally = {"written": 0, "unchanged": 0, "hand_edited": [], "foreign": []}
    for note in rendered:
        note.guard(prohibitions)
        path = folder / note.filename
        verdict = notes.classify_existing(path, note.body)
        if verdict == "hand_edited":
            tally["hand_edited"].append(note.filename)
            continue
        if verdict == "foreign":
            tally["foreign"].append(note.filename)
            continue
        if verdict == "unchanged":
            tally["unchanged"] += 1
            continue
        path.write_text(note.render(generated_by), encoding="utf-8",
                        newline="\n")
        tally["written"] += 1
    return tally


def archive_superseded(contract: dict, vault_root: Path) -> dict:
    """Move the early-snapshot duplicates aside, preserving every one.

    Moved rather than deleted or replaced with a pointer. Every line unique to
    these files is either a path that has since changed or a statement the
    project has superseded, so nothing unique and still true is lost — but a
    superseded record is still a record, and this project does not delete those.
    """
    plan = contract["archive"]
    folder = vault_root / contract["target"]["archive_folder"]
    moved, absent, blocked = [], [], []
    for entry in plan["files"]:
        source = vault_root / entry["name"]
        if not source.is_file():
            absent.append(entry["name"])
            continue
        destination = folder / entry["name"]
        if destination.exists():
            blocked.append(entry["name"])
            continue
        folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved.append(entry)

    if moved or folder.exists():
        lines = [
            "---",
            "type: report",
            "generated: true",
            f"generated_by: {contract['frontmatter']['generated_by']}",
            "tags:",
            "  - ews/report",
            "---",
            "",
            "# Archived early snapshots",
            "",
            "> These sat at the vault root as a snapshot from around Task A1 "
            "while the repository moved on.",
            "",
            "They are **moved, not deleted and not replaced with a pointer**. "
            "Every line unique to them is either a path that has since changed "
            "or a statement the project has superseded, so nothing unique and "
            "still true was lost — but a superseded record is still a record, "
            "and deleting one is how a record starts lying.",
            "",
            "| archived file | superseded by | why |",
            "| --- | --- | --- |",
        ]
        for entry in plan["files"]:
            note = " ".join(entry["note"].split())
            lines.append(f"| `{entry['name']}` | `{entry['superseded_by']}` | {note} |")
        lines += ["", "Read the current versions in the repository, not these."]
        (folder / "README.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    return {"moved": [entry["name"] for entry in moved],
            "already_absent": absent, "left_alone": blocked}


class IgnoreFilterError(ValueError):
    """A configured ignore filter is not a usable repository-relative path."""


def render_ignore_filters(contract: dict, repository_name: str) -> list:
    """Turn repository-relative entries into vault-relative Obsidian filters.

    Obsidian filters are relative to the **vault**, and the vault is the parent
    of this checkout, so the checkout's directory name is genuinely part of what
    Obsidian must be told. It is supplied here, at runtime, from the real
    directory -- never written into the configuration, where it would only ever
    be right on the machine that typed it.

    ``kind`` is carried through rather than guessed: Obsidian reads a bare
    string as a name filter and a ``path:``-prefixed string as a path filter,
    and the two do different things.

    Separators are forced to ``/`` because Obsidian stores its filters that way
    on every platform. Building them with ``Path`` would emit backslashes on
    Windows and produce filters that silently match nothing.
    """
    if contract.get("ignore_filters_relative_to") != "repository_root":
        raise IgnoreFilterError(
            "ignore_filters must declare ignore_filters_relative_to: "
            "repository_root, so a reader knows what the paths are relative to "
            "without inferring it"
        )
    separator = contract.get("ignore_filters_render_separator", "/")
    if not repository_name or repository_name in (".", ".."):
        raise IgnoreFilterError(
            f"{repository_name!r} is not a usable checkout directory name"
        )

    rendered = []
    for entry in contract["ignore_filters"]:
        kind, relative = entry["kind"], entry["path"]
        if kind not in ("name", "path"):
            raise IgnoreFilterError(
                f"{kind!r} is not an Obsidian filter kind; use 'name' or 'path'"
            )
        if relative.startswith(("/", "\\")):
            raise IgnoreFilterError(
                f"{relative!r} starts with a separator, so it is not relative "
                "to the repository root"
            )
        candidate = PurePosixPath(relative.replace("\\", "/"))
        if candidate.is_absolute() or relative[1:3] in (":/", ":\\"):
            raise IgnoreFilterError(f"{relative!r} is an absolute path")
        if ".." in candidate.parts:
            raise IgnoreFilterError(
                f"{relative!r} traverses upward; an ignore filter may not point "
                "outside the repository it describes"
            )
        joined = separator.join((repository_name, *candidate.parts))
        rendered.append(f"path:{joined}" if kind == "path" else joined)
    return rendered


def apply_ignore_filters(contract: dict, vault_root: Path,
                         repository_root: Path = ROOT) -> dict:
    """Stop Obsidian indexing the virtual environment and the raw downloads.

    Additive and idempotent. Filters already present are left as they are, and
    filters somebody added by hand are never removed -- this generator does not
    get to decide that a person's own setting was a mistake.
    """
    filters = render_ignore_filters(contract, Path(repository_root).name)
    path = vault_root / contract["target"]["obsidian_config"]
    if not path.exists():
        return {"updated": False, "reason": "no .obsidian/app.json in this vault",
                "rendered": filters}
    settings = json.loads(path.read_text(encoding="utf-8") or "{}")
    existing = list(settings.get("userIgnoreFilters") or [])
    wanted = [f for f in filters if f not in existing]
    if not wanted:
        return {"updated": False, "reason": "already present",
                "filters": len(existing), "rendered": filters}
    settings["userIgnoreFilters"] = existing + wanted
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8",
                    newline="\n")
    return {"updated": True, "added": wanted, "rendered": filters,
            "filters": len(settings["userIgnoreFilters"])}


def main() -> int:
    contract = load_contract()
    target = contract["target"]
    vault_root = (ROOT / target["vault_root"]).resolve()
    folder = vault_root / target["notes_folder"]
    assert_outside_repository(folder)

    print(f"vault root : {vault_root.name}/")
    print(f"notes      : {target['notes_folder']}/  (outside the repository)")

    data = harvest.harvest(ROOT)
    print(f"harvested  : {len(data['tasks'])} tasks, "
          f"{data['decisions']['total']} decisions "
          f"({len(data['decisions']['untagged'])} untagged), "
          f"{len(data['packages'])} packages, "
          f"{len(data['manifests'])} retrieval manifests")

    rendered = emit.build_notes(data, contract)
    tally = write_notes(
        rendered, folder,
        contract["frontmatter"]["generated_by"],
        contract["prohibitions"],
    )
    print(f"notes      : {len(rendered)} rendered — {tally['written']} written, "
          f"{tally['unchanged']} unchanged")
    if tally["hand_edited"]:
        print(f"  SKIPPED (edited by hand, left alone): {tally['hand_edited']}")
    if tally["foreign"]:
        print(f"  SKIPPED (not written by this generator): {tally['foreign']}")

    canvas = emit.build_canvas(data, target["notes_folder"])
    canvas_path = folder / "Thai Supply Chain EWS.canvas"
    if not canvas_path.exists() or canvas_path.read_text(encoding="utf-8") != canvas:
        canvas_path.write_text(canvas, encoding="utf-8", newline="\n")
        print(f"canvas     : {canvas_path.name} written")
    else:
        print(f"canvas     : {canvas_path.name} unchanged")

    archived = archive_superseded(contract, vault_root)
    print(f"archive    : moved {len(archived['moved'])}, "
          f"already absent {len(archived['already_absent'])}, "
          f"left alone {len(archived['left_alone'])}")

    ignored = apply_ignore_filters(contract, vault_root)
    print(f"obsidian   : ignore filters "
          f"{'updated' if ignored['updated'] else 'unchanged'} "
          f"({ignored.get('reason', '')})".rstrip(" ()"))

    print("\nrepository: untouched — the vault is written outside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
