# Running the Obsidian vault generator

The generator writes a read-only *view* of this repository into an Obsidian
vault. It writes **outside** the repository, so `git status` stays clean and the
release manifest is untouched.

The vault is not under version control. That single fact shapes everything
below: there is no `git checkout` to undo a bad run, so the run has to be
undoable by itself.

> **This is a post-release feature.** Release `v1.0.0` predates it. A checkout of
> the `v1.0.0` tag has neither the generator's safety layer nor this document,
> and the version of the script released there derived its destination
> implicitly. Use `main`.

## Interpreter

**Python 3.12** is the supported and tested version. It is the floor in
`pyproject.toml`, the version both locks were resolved on, and the only version
CI runs.

Local development in this working tree currently uses **Python 3.14.3** in
`.venv`, which is one minor version above anything CI has verified. Treat a
green local run as necessary but not sufficient: CI on 3.12 is the check that
counts before merging.

## The three commands

Every command names the vault explicitly. Nothing is inferred from where the
repository happens to sit.

```
python scripts/build_obsidian_vault.py --help
python scripts/build_obsidian_vault.py --vault-root PATH --dry-run
python scripts/build_obsidian_vault.py --vault-root PATH --apply --backup-root PATH
python scripts/build_obsidian_vault.py --vault-root PATH --rollback MANIFEST_PATH
```

| option | meaning |
| --- | --- |
| `--help` | Prints usage and exits. Reads no vault and writes nothing. |
| `--config PATH` | A different contract. Defaults to `configs/obsidian_vault.yaml`. |
| `--vault-root PATH` | The Obsidian vault. **Required** for `--dry-run` and `--apply`. Must already exist, and must be outside this repository. |
| `--dry-run` | Prints the complete plan and changes nothing at all. |
| `--apply` | Writes the plan inside one backed-up transaction. Requires `--backup-root`. |
| `--backup-root PATH` | Where the backup transaction is written. **Must already exist** — it is never created for you, so a misspelled path fails instead of becoming an empty directory nobody would look in. Must be outside the repository and outside the managed folders. |
| `--rollback MANIFEST` | Undoes one recorded transaction. |

`--dry-run`, `--apply` and `--rollback` are mutually exclusive. Running with no
arguments prints usage and exits 2 — it does not pick a default action.

**There is no `--force` and no overwrite bypass.** A note edited by hand, a file
this generator did not write, and an archive destination that already exists are
each reported and left alone.

Exit codes: `0` success, `1` a rollback that could not complete, `2` a usage
error or a refused path.

### `--help` is safe now, and was not before

Before this change the script parsed no arguments at all. Any flag — `--help`
included — was ignored, and the generator ran against a vault derived from
`repository/..`. If you are on an older checkout, do not use `--help` to explore
it.

## Recommended order

1. **Dry run first**, always. Read the plan: how many notes are new, how many
   would be updated, which are protected, which archive moves would happen, and
   whether the Obsidian settings would change.
2. **Apply with a backup root** once the plan says what you expected.
3. Keep the manifest path printed at the end. It is what `--rollback` needs.

## Windows PowerShell examples

Replace the placeholders with your own paths. `<VAULT>` is the Obsidian vault
folder that contains this checkout; `<BACKUPS>` is an **existing** directory
outside both the repository and the vault's managed folders. Create it yourself
first — the generator refuses a backup root that does not exist rather than
creating one, so a typo cannot turn into a backup you will never find.

```powershell
# 1. See what would happen. Changes nothing.
.\.venv\Scripts\python.exe scripts\build_obsidian_vault.py `
    --vault-root "<VAULT>" --dry-run

# 2. Apply, with every disturbed file copied first.
.\.venv\Scripts\python.exe scripts\build_obsidian_vault.py `
    --vault-root "<VAULT>" --apply --backup-root "<BACKUPS>"

# 3. Undo that transaction if you want it back.
.\.venv\Scripts\python.exe scripts\build_obsidian_vault.py `
    --vault-root "<VAULT>" `
    --rollback "<BACKUPS>\20260903T093000Z-1a2b3c4d\manifest.json"
```

On Linux or macOS use `.venv/bin/python` and forward slashes.

## What the generator manages

Inside the vault you name, and nowhere else:

- `Knowledge Graph/` — the generated notes and `Thai Supply Chain EWS.canvas`
- `_archive/` — the seven early-snapshot documents, moved here, plus a generated
  `README.md` explaining what superseded each
- `.obsidian/app.json` — only the `userIgnoreFilters` list, only by appending

The folder names come from `configs/obsidian_vault.yaml`. The **root** they hang
from does not: it is `--vault-root`, every time.

## What it refuses to touch

- **A hand-edited generated note.** Every generated note carries a checksum of
  its own body. If the body no longer matches, the note is reported as
  `hand_edited` and skipped.
- **A file it did not write.** No `generated: true` and no `content_sha256` in
  the frontmatter means `foreign`, and foreign files are never modified.
- **An archive destination that already exists.** The move is reported as
  blocked and the source stays where it is.
- **Existing ignore filters.** Filters you added, and filters left over from an
  older checkout name, are preserved. The generator only appends.
- **Anything inside this repository.** A managed path that resolves inside the
  checkout is refused before any write.
- **Anything outside the vault you named.** Configured paths must be relative,
  and the *resolved* destination must stay inside the vault — so a symbolic link
  pointing out of it is caught rather than followed.

## Backups and recovery

`--apply` creates one directory per run, beneath the existing root you named:

```
<BACKUPS>/<transaction id>/
    manifest.json      the record of the run
    files/...          a copy of every file replaced or moved, by vault-relative path
```

The manifest is a versioned JSON **journal**, and it exists before the first
change to your vault. The sequence is fixed: validate the plan, check that the
backup root already exists, create the transaction directory, copy and verify
every backup, write the journal with state `prepared`, and only then begin. Each
completed operation is journalled before the next starts, so a process killed at
any moment leaves a record of exactly what finished.

Transaction states: `prepared` → `applying` → `applied`, and then
`rolled_back` or `rollback_failed`. A journal left in `prepared` or `applying`
is an interrupted run — `--rollback` accepts it and reports the transaction as
INCOMPLETE rather than as a success.

Each operation moves through `pending` → `intent` → `completed`, and the
`intent` record — carrying the expected before *and after* digests, both known
in advance — is fsynced **before** the vault is touched. That closes the window
where a mutation lands and the machine stops before anything records it: the
journal says what was about to happen and exactly what it would look like either
way, so recovery can tell which side of the mutation the crash fell on. Rollback
resolves every `intent` and `completed` operation against the disk before
restoring anything, and if even one is ambiguous it performs **zero** changes.

A journal is treated as untrusted structured input. Every path it carries is
stored relative — to the vault root, or to the transaction directory — and
re-validated against the roots you gave on the command line. Absolute and
drive-qualified paths, leading separators, `..`, malformed records, duplicate or
contradictory operations, a `backup_directory` that is not the directory the
journal lives in, a backup key pointing outside that directory, and operations
aimed at the journal itself are each refused before any restoration. This is
structural confinement, not cryptographic trust: it cannot stop somebody who can
already write wherever they like, and it is not meant to.

If a crash leaves an atomic-write temporary file (dotted, ending `.tmp`), it is
never authoritative. Rollback removes one only when the journal names it *and*
its raw digest matches what that operation announced; anything else is left in
place and reported.

**Digests are raw SHA-256 over the exact file bytes.** Every integrity decision
uses them, so a change from LF to CRLF after an apply counts as drift and makes
rollback refuse. Canonical (newline-normalised) digests are recorded too, under
separate `canonical_sha256_*` names, purely so a reader can tell a genuine edit
from a line-ending conversion; they never authorise anything.

The journal also records the repository and vault identities, the transaction id
and timestamp, every operation with its source, destination and status, and the
files and directories the transaction created. Manifest writes go to a
same-directory dotted `.tmp` file, are flushed and `fsync`ed, then moved into
place with `os.replace`, so a torn write can never be mistaken for the record.
Directory `fsync` is deliberately not attempted: it is not portable.

**If an apply fails part-way**, it rolls itself back immediately, writes the
manifest anyway, and exits non-zero reporting both the original failure and
whether the rollback completed. It never leaves a half-applied vault silently.

**To undo a completed apply**, pass its manifest to `--rollback`. Before
changing anything, rollback checks every affected path against the digests the
apply recorded. If any of them has moved on — most importantly, if you have
edited a generated note since — the whole rollback is **refused** and nothing is
touched. There is no way to force it: restoring old bytes over your later edit
would be a second loss, not a recovery. Rollback restores exact original bytes
and locations, removes only files that transaction created, removes directories
only when they are empty, and never touches anything else in the vault. Running
it twice is safe; the second run reports `already rolled back`.

Backups and manifests are deliberately **not** in git. Keep `<BACKUPS>` outside
the repository.

## Related

- `configs/obsidian_vault.yaml` — the frozen contract: note types, relationships,
  provenance, archive plan, ignore filters and prohibited content
- `tests/test_obsidian_vault.py`, `tests/test_obsidian_vault_cli.py`,
  `tests/test_obsidian_vault_transaction.py` — every test runs against temporary
  directories only
