"""Generate the Obsidian vault view of this repository.

It writes to an Obsidian vault **outside** this repository, so `git status`
stays clean and the release manifest is untouched. Only this script, its
contract and its tests are version-controlled.

**The destination is always named.** ``--vault-root`` is required for every
operation that looks at a vault. Until this version the root was derived from
the contract as ``repository/..``, which meant running the script with no
arguments at all wrote into whichever directory happened to contain the
checkout. Convenient once; a hazard every time after, and a hazard that could
not be tested without copying the whole repository somewhere else.

**Nothing is written until a plan has been built and checked.** ``--dry-run``
prints exactly what would happen -- new notes, updates, files left alone,
archive moves, settings changes -- and creates nothing at all. ``--apply``
builds the same plan, validates it, copies everything it could disturb into a
backup transaction, and only then writes.

**A failure undoes itself.** Every write is atomic, every overwritten or moved
file is backed up first, and a failure part-way through rolls the whole
transaction back and exits non-zero. A partial vault is not a smaller success.

**A hand edit is never overwritten.** A note whose body no longer matches the
checksum in its own frontmatter is reported and skipped, and a file this
generator did not write is never touched. There is no ``--force``.

Run it after any task that changes documents, decisions or configuration:

    python scripts/build_obsidian_vault.py --vault-root PATH --dry-run

This vault already drifted once -- seven documents sat at its root as a snapshot
from around Task A1 while the repository moved on, one of them showing four
decisions where the repository had a hundred and seventy -- and a generator that
overwrites silently is how the same thing would happen in the other direction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.vault import (  # noqa: E402
    emit,
    harvest,
    notes,
    safety,
    transaction,
)

DEFAULT_CONFIG_PATH = ROOT / "configs" / "obsidian_vault.yaml"

CANVAS_NAME = "Thai Supply Chain EWS.canvas"
ARCHIVE_README = "README.md"


class IgnoreFilterError(ValueError):
    """A configured ignore filter is not a usable repository-relative path."""


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

def load_contract(path: Path = None) -> dict:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise SystemExit(f"no contract at {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def assert_outside_repository(target: Path) -> None:
    """The vault must not be written inside the repository.

    Kept as a named function because it is the one refusal that would otherwise
    recreate the duplication this export exists to remove.
    """
    try:
        safety.assert_outside(target, ROOT, field="destination")
    except safety.VaultPathError as error:
        raise SystemExit(
            f"refusing to write to {target}: it is inside the repository. The "
            "vault is a view, and a generated view committed alongside its "
            f"source is the duplication this export exists to remove. {error}"
        ) from error


def managed_paths(contract: dict, vault_root: Path) -> dict:
    """Every directory and file this generator may touch, resolved and confined."""
    target = contract["target"]
    notes_folder = safety.resolve_within(
        vault_root, target["notes_folder"], field="target.notes_folder")
    archive_folder = safety.resolve_within(
        vault_root, target["archive_folder"], field="target.archive_folder")
    settings = safety.resolve_within(
        vault_root, target["obsidian_config"], field="target.obsidian_config")
    for path in (notes_folder, archive_folder, settings):
        assert_outside_repository(path)
    return {"notes": notes_folder, "archive": archive_folder,
            "settings": settings}


# ---------------------------------------------------------------------------
# Ignore filters
# ---------------------------------------------------------------------------

def render_ignore_filters(contract: dict, repository_name: str) -> list:
    """Turn repository-relative entries into vault-relative Obsidian filters.

    Obsidian filters are relative to the **vault**, and the vault contains this
    checkout, so the checkout's directory name is genuinely part of what
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
    """Additive, idempotent update of Obsidian's user ignore filters.

    Filters already present are left as they are, and filters somebody added by
    hand are never removed -- this generator does not get to decide that a
    person's own setting was a mistake.
    """
    filters = render_ignore_filters(contract, Path(repository_root).name)
    path = Path(vault_root) / contract["target"]["obsidian_config"]
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
    transaction.atomic_write_text(
        path, json.dumps(settings, indent=2) + "\n")
    return {"updated": True, "added": wanted, "rendered": filters,
            "filters": len(settings["userIgnoreFilters"])}


def settings_payload(contract: dict, settings_path: Path,
                     repository_name: str) -> tuple:
    """The filters to add and the resulting document, without writing anything."""
    filters = render_ignore_filters(contract, repository_name)
    if not settings_path.is_file():
        return [], None, filters
    settings = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
    existing = list(settings.get("userIgnoreFilters") or [])
    wanted = [value for value in filters if value not in existing]
    if not wanted:
        return [], None, filters
    settings["userIgnoreFilters"] = existing + wanted
    return wanted, json.dumps(settings, indent=2) + "\n", filters


# ---------------------------------------------------------------------------
# The plan: what would happen, computed without touching anything
# ---------------------------------------------------------------------------

def build_plan(contract: dict, vault_root: Path,
               repository_root: Path = ROOT) -> dict:
    """Everything an apply would do, in a fixed order, having written nothing.

    Reads the vault to classify what is already there. It creates no directory,
    writes no file and moves nothing, so a dry run is a genuine preview rather
    than an apply with the writes commented out.
    """
    vault_root = Path(vault_root)
    paths = managed_paths(contract, vault_root)
    data = harvest.harvest(repository_root)
    rendered = emit.build_notes(data, contract)
    generated_by = contract["frontmatter"]["generated_by"]
    prohibitions = contract["prohibitions"]

    actions, protected = [], []
    for note in sorted(rendered, key=lambda n: n.filename):
        note.guard(prohibitions)
        path = paths["notes"] / note.filename
        verdict = notes.classify_existing(path, note.body)
        if verdict in ("hand_edited", "foreign"):
            protected.append({"kind": verdict, "path": str(path),
                              "name": note.filename})
            continue
        if verdict == "unchanged":
            actions.append({"kind": "note_unchanged", "path": str(path),
                            "name": note.filename})
            continue
        actions.append({"kind": "note_new" if verdict == "new" else "note_update",
                        "path": str(path), "name": note.filename,
                        "text": note.render(generated_by)})

    canvas_text = emit.build_canvas(data, contract["target"]["notes_folder"])
    canvas_path = paths["notes"] / CANVAS_NAME
    if canvas_path.is_file() and canvas_path.read_text(encoding="utf-8") == canvas_text:
        actions.append({"kind": "canvas_unchanged", "path": str(canvas_path)})
    else:
        actions.append({
            "kind": "canvas_new" if not canvas_path.exists() else "canvas_update",
            "path": str(canvas_path), "text": canvas_text})

    moves, blocked, absent = [], [], []
    for entry in contract["archive"]["files"]:
        source = safety.resolve_within(
            vault_root, entry["name"], field="archive.files[].name")
        destination = paths["archive"] / entry["name"]
        if not source.is_file():
            absent.append(entry["name"])
            continue
        if destination.exists():
            blocked.append({"name": entry["name"], "path": str(destination)})
            continue
        moves.append({"kind": "archive_move", "path": str(destination),
                      "moved_from": str(source), "name": entry["name"]})
    actions.extend(moves)

    readme_path = paths["archive"] / ARCHIVE_README
    readme_text = None
    if moves or paths["archive"].exists():
        readme_text = archive_readme_text(contract, [m["name"] for m in moves])
        if readme_path.is_file() and readme_path.read_text(
                encoding="utf-8") == readme_text:
            actions.append({"kind": "archive_readme_unchanged",
                            "path": str(readme_path)})
        else:
            actions.append({
                "kind": ("archive_readme_new" if not readme_path.exists()
                         else "archive_readme_update"),
                "path": str(readme_path), "text": readme_text})

    added, settings_text, filters = settings_payload(
        contract, paths["settings"], Path(repository_root).name)
    if not paths["settings"].is_file():
        settings = {"kind": "settings_absent", "path": str(paths["settings"]),
                    "added": [], "rendered": filters}
    elif not added:
        settings = {"kind": "settings_unchanged", "path": str(paths["settings"]),
                    "added": [], "rendered": filters}
    else:
        settings = {"kind": "settings_update", "path": str(paths["settings"]),
                    "added": added, "text": settings_text, "rendered": filters}
    actions.append(settings)

    return {
        "vault_root": str(safety.real_path(vault_root)),
        "repository_root": str(safety.real_path(repository_root)),
        "notes_folder": str(paths["notes"]),
        "archive_folder": str(paths["archive"]),
        "settings_path": str(paths["settings"]),
        "actions": actions,
        "protected": protected,
        "archive_blocked": blocked,
        "archive_absent": sorted(absent),
        "counts": _counts(actions, protected, blocked, absent),
    }


def _counts(actions, protected, blocked, absent) -> dict:
    counts = {}
    for action in actions:
        counts[action["kind"]] = counts.get(action["kind"], 0) + 1
    for item in protected:
        key = f"protected_{item['kind']}"
        counts[key] = counts.get(key, 0) + 1
    counts["archive_blocked"] = len(blocked)
    counts["archive_absent"] = len(absent)
    return dict(sorted(counts.items()))


def archive_readme_text(contract: dict, moved_names) -> str:
    """The archive README, rendered from the contract rather than from disk."""
    plan = contract["archive"]
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
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

WRITE_KINDS = ("note_new", "note_update", "canvas_new", "canvas_update",
               "archive_readme_new", "archive_readme_update", "settings_update")


def print_plan(plan: dict, mode: str) -> None:
    print(f"mode          : {mode}")
    print(f"repository    : {plan['repository_root']}")
    print(f"vault root    : {plan['vault_root']}")
    print(f"notes folder  : {plan['notes_folder']}")
    print(f"archive folder: {plan['archive_folder']}")
    print(f"settings      : {plan['settings_path']}")
    print()
    for kind, count in plan["counts"].items():
        print(f"  {kind:28} {count}")
    print()
    for action in plan["actions"]:
        if action["kind"] in WRITE_KINDS:
            print(f"  {action['kind']:28} {action['path']}")
        elif action["kind"] == "archive_move":
            print(f"  {action['kind']:28} {action['moved_from']} -> "
                  f"{action['path']}")
    for item in plan["protected"]:
        print(f"  PROTECTED ({item['kind']}): {item['path']} — left alone")
    for item in plan["archive_blocked"]:
        print(f"  BLOCKED archive move: {item['path']} already exists — "
              "left alone")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def planned_operations(plan: dict) -> tuple:
    """The plan's mutations, in order, plus the kind of each for reporting."""
    operations, kinds = [], {}
    for action in plan["actions"]:
        if action["kind"] in WRITE_KINDS:
            operations.append({"op": "write", "path": action["path"],
                               "text": action["text"]})
        elif action["kind"] == "archive_move":
            operations.append({"op": "move", "source": action["moved_from"],
                               "destination": action["path"]})
        else:
            continue
        kinds[len(operations) - 1] = action["kind"]
    return operations, kinds


def apply_plan(plan: dict, backup_root: Path, after_stage=None,
               at_boundary=None) -> dict:
    """Execute a validated plan inside one write-ahead journalled transaction.

    ``prepare`` copies and verifies every backup, computes the exact bytes each
    write will produce, and writes a durable ``prepared`` journal. Then each
    operation is announced as ``intent`` and fsynced *before* its mutation, and
    marked ``completed`` after. A process killed anywhere in that sequence
    leaves a journal that says which side of the mutation it stopped on, so a
    later ``--rollback`` can recover -- without this process having survived to
    catch its own exception.

    ``after_stage`` and ``at_boundary`` are test seams, not escape hatches: the
    tests raise from them to prove each crash window is recoverable.
    """
    operations, kinds = planned_operations(plan)
    txn = transaction.Transaction(
        backup_root=backup_root,
        repository_root=plan["repository_root"],
        vault_root=plan["vault_root"],
    )
    txn.prepare(operations)
    try:
        return txn.execute(after_stage=after_stage, kinds=kinds,
                           at_boundary=at_boundary)
    except BaseException as error:
        undo = txn.rollback()
        raise SystemExit(
            "apply failed: " + str(error) + "\nrollback: "
            + ("complete" if undo["rolled_back"] else str(undo["problems"]))
            + "\nstate: " + str(txn.state)
            + "\nmanifest: " + str(txn.manifest_path)
        ) from error


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_obsidian_vault.py",
        description=(
            "Generate the Obsidian vault view of this repository. The vault is "
            "always named explicitly; nothing is written without --apply, and "
            "--apply always writes a backup first."
        ),
        epilog=(
            "There is no --force. A note edited by hand, a file this generator "
            "did not write, and an archive destination that already exists are "
            "reported and left alone."
        ),
    )
    parser.add_argument("--config", metavar="PATH", type=Path,
                        help="contract to read (default: configs/obsidian_vault.yaml)")
    parser.add_argument("--vault-root", metavar="PATH", type=Path,
                        help="the Obsidian vault to inspect or write. Required "
                             "for --dry-run and --apply; never inferred")
    parser.add_argument("--backup-root", metavar="PATH", type=Path,
                        help="an existing directory where --apply writes its "
                             "backup transaction. Required for --apply; never "
                             "created for you")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="print the plan and change nothing at all")
    mode.add_argument("--apply", action="store_true",
                      help="write the plan inside a backed-up transaction")
    mode.add_argument("--rollback", metavar="MANIFEST_PATH", type=Path,
                      help="undo a recorded transaction using its manifest")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if not (arguments.dry_run or arguments.apply or arguments.rollback):
        parser.print_usage(sys.stderr)
        print("\nchoose exactly one of --dry-run, --apply or --rollback. "
              "Running with no arguments does nothing, on purpose: this "
              "generator writes outside the repository and never guesses "
              "where.", file=sys.stderr)
        return 2

    try:
        contract = load_contract(arguments.config)
        vault_root = safety.require_directory(
            arguments.vault_root, field="--vault-root")
        safety.assert_outside(vault_root, ROOT, field="--vault-root")

        if arguments.rollback:
            manifest_path = Path(arguments.rollback)
            manifest = transaction.load_manifest(manifest_path)
            result = transaction.rollback_manifest(
                manifest, vault_root, ROOT, manifest_path=manifest_path)
            print(f"journal    : {transaction.describe(manifest)}")
            print(f"rollback   : {result['reason']}")
            print(f"state      : {result.get('state', manifest['state'])}")
            print(f"restored   : {result['restored']} file(s)")
            print(f"removed    : {result['removed']} file(s) this transaction "
                  "created")
            print(f"directories: {result['directories_removed']} removed "
                  "(only if empty)")
            for stray in result.get("temporary_files_left", []):
                print(f"  LEFT IN PLACE: {stray} — a temporary file this "
                      "journal names, holding bytes it did not announce")
            return 0 if result["rolled_back"] or result[
                "reason"] == "already rolled back" else 1

        plan = build_plan(contract, vault_root, ROOT)

        if arguments.dry_run:
            print_plan(plan, "dry-run — nothing is created, written or moved")
            return 0

        if arguments.backup_root is None:
            print("--apply requires --backup-root: every file this run could "
                  "overwrite or move is copied there first, and the vault is "
                  "not under version control.", file=sys.stderr)
            return 2
        # Required to exist already, exactly like --vault-root. Creating it
        # would turn a misspelled path into a new empty directory and a backup
        # nobody would think to look for.
        backup_root = safety.require_directory(
            arguments.backup_root, field="--backup-root")
        safety.assert_outside(backup_root, ROOT, field="--backup-root")
        for field, directory in (("target.notes_folder", plan["notes_folder"]),
                                 ("target.archive_folder", plan["archive_folder"])):
            safety.assert_disjoint(backup_root, Path(directory),
                                   first_field="--backup-root",
                                   second_field=field)

        print_plan(plan, "apply")
        result = apply_plan(plan, backup_root)
        print()
        print(f"transaction: {result['transaction_id']}")
        print(f"manifest   : {result['manifest']}")
        print(f"operations : {result['operations']}")
        print("\nrepository: untouched — the vault is written outside it.")
        return 0

    except (safety.VaultPathError, transaction.TransactionError,
            IgnoreFilterError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
