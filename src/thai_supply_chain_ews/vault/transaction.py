"""Write-ahead journalled application of a vault plan, and its recovery.

The vault is not under version control. There is no ``git checkout`` to undo a
bad run, so the run has to be undoable from what survives on disk -- including
when nothing survives of the process itself.

**Integrity is raw bytes.** ``sha256_before`` and ``sha256_after`` are SHA-256
over exact file bytes, and every decision compares those. This project
canonicalises digests elsewhere on purpose: a *content* claim about a released
document should survive the difference between a Windows and a Linux checkout. A
transaction claim is the opposite kind of claim -- it is about the bytes on this
disk right now -- so normalising them would hide a change from LF to CRLF from
the check whose whole job is to notice the file moved on. Canonical digests are
recorded under separate ``canonical_sha256_*`` names and are diagnostic only.

**Every mutation is announced before it happens.** Recording a completed
operation *after* mutating leaves a window: the write lands, the machine stops,
and the journal still says the operation never ran. So each operation passes
through ``pending`` → ``intent`` → ``completed``, and the ``intent`` record --
carrying the expected before *and after* digests, computed in advance -- is
fsynced to disk before the filesystem is touched. A crash in the window then
leaves a journal that says "this was about to happen, here is exactly what it
would look like either way", and recovery can tell which side of the mutation
the machine stopped on.

**A manifest is untrusted structured input.** It is a file on disk that anybody
could edit. Every path in it is stored relative -- to the vault root, or to the
transaction directory -- and re-validated against the roots given on the command
line before a single byte is restored. An absolute path, a ``..``, a symlink out
of the vault, a duplicate record, a backup key pointing outside the transaction
directory, or an operation aimed at the journal itself: each is refused, and
refused *before* any mutation. This is structural confinement, not cryptographic
trust; it cannot stop somebody who can already write wherever they like, and it
is not meant to.

**Ambiguity refuses everything.** Rollback resolves the true state of every
recorded operation first. If even one is ambiguous or has drifted, zero
rollback mutations happen.

Deletion lives here and nowhere else. The runner never removes a file; this
module removes only paths its own journal records as created, and only after
their recorded post-state digest matches what is on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from . import safety

__all__ = [
    "MANIFEST_VERSION",
    "ROLLBACKABLE_STATES",
    "STATE_APPLIED",
    "STATE_APPLYING",
    "STATE_PREPARED",
    "STATE_ROLLBACK_FAILED",
    "STATE_ROLLED_BACK",
    "STATUS_COMPLETED",
    "STATUS_INTENT",
    "STATUS_PENDING",
    "Transaction",
    "TransactionError",
    "atomic_write_text",
    "canonical_digest_file",
    "describe",
    "load_manifest",
    "raw_digest_bytes",
    "raw_digest_file",
    "rollback_manifest",
    "validate_manifest",
]

#: Bumped whenever the manifest's meaning changes. Version 3 stores every path
#: relative to a declared root and adds the write-ahead ``intent`` status.
MANIFEST_VERSION = 3

MANIFEST_NAME = "manifest.json"
BACKUP_SUBDIRECTORY = "files"

STATE_PREPARED = "prepared"
STATE_APPLYING = "applying"
STATE_APPLIED = "applied"
STATE_ROLLED_BACK = "rolled_back"
STATE_ROLLBACK_FAILED = "rollback_failed"

#: A transaction interrupted mid-apply is exactly what rollback exists for, so
#: both in-progress states are accepted as well as a completed one.
ROLLBACKABLE_STATES = (STATE_PREPARED, STATE_APPLYING, STATE_APPLIED,
                       STATE_ROLLBACK_FAILED)

STATUS_PENDING = "pending"
STATUS_INTENT = "intent"
STATUS_COMPLETED = "completed"
STATUSES = (STATUS_PENDING, STATUS_INTENT, STATUS_COMPLETED)

#: Resolved states of a recorded operation.
NOT_APPLIED = "not_applied"
APPLIED = "applied"
AMBIGUOUS = "ambiguous"


class TransactionError(RuntimeError):
    """An apply or rollback could not be completed safely."""


# ---------------------------------------------------------------------------
# Digests
# ---------------------------------------------------------------------------

def raw_digest_bytes(data: bytes) -> str:
    """SHA-256 over exactly these bytes. The only digest that authorises anything."""
    return hashlib.sha256(data).hexdigest()


def raw_digest_file(path) -> str:
    """SHA-256 over a file's exact bytes, line endings included."""
    return raw_digest_bytes(Path(path).read_bytes())


def canonical_digest_file(path) -> str:
    """Diagnostic only: the same content with CRLF collapsed to LF."""
    data = Path(path).read_bytes()
    if b"\x00" in data[:8000]:
        return raw_digest_bytes(data)
    return raw_digest_bytes(data.replace(b"\r\n", b"\n"))


def _encode(text: str) -> bytes:
    """Exactly the bytes :func:`atomic_write_text` will put on disk."""
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------

def atomic_write_text(path, text: str, *, fsync: bool = False,
                      temporary=None) -> Path:
    """Write LF text so a reader sees either the old file or the whole new one.

    The temporary file is created in the destination's own directory, because
    ``os.replace`` is atomic only within a filesystem. Its name is dotted and
    ends in ``.tmp`` so a half-written file can never be mistaken for the
    document, and it can be **named in advance** so the journal knows what a
    crash might leave behind.

    ``fsync`` flushes to the device before the replace, which is what makes the
    journal survive a power loss rather than only a process crash. Directory
    fsync is deliberately not attempted: it is not portable, and Windows has no
    equivalent.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(temporary) if temporary else path.with_name(
        f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if fsync:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise
    return temporary


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Relative-path handling. Manifests store nothing absolute.
# ---------------------------------------------------------------------------

def _relative_to(path, root) -> str:
    """A path expressed beneath a root, as POSIX, or an error."""
    resolved, base = safety.real_path(path), safety.real_path(root)
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError as error:
        raise TransactionError(
            f"{path} is not inside {base}; a transaction records only paths "
            "beneath the roots it was given"
        ) from error


def _under(root: Path, relative: str, *, field: str) -> Path:
    """Resolve a manifest-supplied relative path, confined to ``root``.

    The confinement check is on the resolved result, so a symbolic link that
    points out of the root is caught rather than followed.
    """
    if not isinstance(relative, str) or not relative.strip():
        raise TransactionError(f"{field} must be a non-empty relative path")
    if relative.startswith(("/", "\\")):
        raise TransactionError(
            f"{field} {relative!r} starts with a separator; manifest paths are "
            "relative to a declared root")
    if len(relative) > 1 and relative[1] == ":":
        raise TransactionError(f"{field} {relative!r} is drive-qualified")
    candidate = PurePosixPath(relative.replace("\\", "/"))
    if candidate.is_absolute():
        raise TransactionError(f"{field} {relative!r} is an absolute path")
    parts = [part for part in candidate.parts if part != "."]
    if not parts:
        raise TransactionError(f"{field} {relative!r} names nothing")
    if ".." in parts:
        raise TransactionError(
            f"{field} {relative!r} traverses upward; a rollback may not reach "
            "outside the root it was given")
    base = safety.real_path(root)
    target = base.joinpath(*parts)
    resolved = safety.real_path(target)
    if resolved != base and not _is_within(resolved, base):
        raise TransactionError(
            f"{field} {relative!r} resolves to {resolved}, outside {base}. A "
            "symbolic link out of the root is still a path out of the root")
    return target


def _is_within(candidate: Path, base: Path) -> bool:
    try:
        candidate.relative_to(base)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# The transaction
# ---------------------------------------------------------------------------

class Transaction:
    """One apply: its backups, its write-ahead journal, and its undo.

    :meth:`prepare` copies and verifies every backup, computes the exact bytes
    each write will produce, and writes a durable ``prepared`` journal. Only
    then may :meth:`execute` touch the vault, and each operation is announced as
    ``intent`` -- fsynced -- before its mutation and marked ``completed`` after.
    """

    def __init__(self, backup_root, repository_root, vault_root,
                 transaction_id: str = None):
        self.backup_root = Path(backup_root)
        self.repository_root = safety.real_path(repository_root)
        self.vault_root = safety.real_path(vault_root)
        self.transaction_id = transaction_id or (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid.uuid4().hex[:8])
        self.directory = self.backup_root / self.transaction_id
        self.state = None
        self.operations = []
        self.created_files = []
        self.created_directories = []
        self._prepared = False

    @property
    def manifest_path(self) -> Path:
        return self.directory / MANIFEST_NAME

    @property
    def backup_directory(self) -> Path:
        return self.directory / BACKUP_SUBDIRECTORY

    # -- phase one ---------------------------------------------------------

    def prepare(self, planned) -> Path:
        """Copy and verify every backup, then make the journal durable.

        Nothing in the vault is touched. Post-state digests for writes are
        computed here, from the text, so the ``intent`` record can carry them.
        """
        if self.backup_root.exists() and not self.backup_root.is_dir():
            raise TransactionError(
                f"backup root {self.backup_root} is not a directory")
        if not self.backup_root.is_dir():
            raise TransactionError(
                f"backup root {self.backup_root} does not exist. It is named "
                "explicitly and is never created for you: a misspelled path "
                "must fail, not become a directory")
        if self.directory.exists():
            raise TransactionError(
                f"backup directory {self.directory} already exists; a "
                "transaction never reuses another run's directory")
        self.backup_directory.mkdir(parents=True)

        for entry in planned:
            if entry["op"] == "write":
                self.operations.append(self._prepare_write(entry))
            elif entry["op"] == "move":
                self.operations.append(self._prepare_move(entry))
            else:
                raise TransactionError(f"unknown planned operation {entry['op']!r}")

        self.state = STATE_PREPARED
        self._prepared = True
        self._journal()
        return self.manifest_path

    def _prepare_write(self, entry) -> dict:
        path = Path(entry["path"])
        relative = _relative_to(path, self.vault_root)
        existed = path.is_file()
        payload = _encode(entry["text"])
        record = {
            "op": "write",
            "status": STATUS_PENDING,
            "path": relative,
            "existed_before": existed,
            "backup": self._back_up(path) if existed else None,
            "sha256_before": raw_digest_file(path) if existed else None,
            "canonical_sha256_before": (canonical_digest_file(path)
                                        if existed else None),
            # Known in advance: this is what the file will contain, so an
            # interrupted run can be told apart from one that never started.
            "sha256_after": raw_digest_bytes(payload),
            "canonical_sha256_after": raw_digest_bytes(
                payload.replace(b"\r\n", b"\n")),
            "temporary": _temporary_name(relative),
        }
        record["_text"] = entry["text"]
        for parent in _missing_parents(path.parent):
            self._record_directory(parent)
        if not existed:
            self.created_files.append(relative)
        return record

    def _prepare_move(self, entry) -> dict:
        source, destination = Path(entry["source"]), Path(entry["destination"])
        if not source.is_file():
            raise TransactionError(f"{source} is not a file and cannot be moved")
        if destination.exists():
            raise TransactionError(
                f"{destination} already exists; a move never overwrites, and a "
                "blocked destination is reported instead")
        digest = raw_digest_file(source)
        record = {
            "op": "move",
            "status": STATUS_PENDING,
            "path": _relative_to(destination.parent, self.vault_root)
                    + "/" + destination.name,
            "moved_from": _relative_to(source, self.vault_root),
            "existed_before": True,
            "backup": self._back_up(source),
            "sha256_before": digest,
            "canonical_sha256_before": canonical_digest_file(source),
            # A move does not change bytes, so the destination will hold these.
            "sha256_after": digest,
            "canonical_sha256_after": canonical_digest_file(source),
            "temporary": None,
        }
        for parent in _missing_parents(destination.parent):
            self._record_directory(parent)
        return record

    def _back_up(self, path: Path) -> str:
        """Copy a file into this transaction and verify the copy, byte for byte."""
        relative = _relative_to(path, self.vault_root)
        destination = self.backup_directory.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if raw_digest_file(destination) != raw_digest_file(path):
            raise TransactionError(
                f"the backup copy of {path} does not match the original. "
                "Nothing is mutated when a backup cannot be trusted")
        return relative

    def _record_directory(self, path) -> None:
        relative = _relative_to(path, self.vault_root)
        if relative not in self.created_directories:
            self.created_directories.append(relative)

    # -- phase two: announce, mutate, confirm -------------------------------

    def execute(self, after_stage=None, kinds=None, at_boundary=None) -> dict:
        """Perform the prepared operations, announcing each before it happens.

        ``at_boundary(name, index)`` is a test seam, not an escape hatch. The
        tests raise from it at ``after_intent``, ``after_mutation`` and
        ``after_completed`` to prove every crash window is recoverable. It
        writes nothing and skips nothing.
        """
        if not self._prepared:
            raise TransactionError(
                "the transaction was not prepared; backups and the journal come "
                "before the first mutation, never alongside it")
        self.state = STATE_APPLYING
        self._journal()

        for index, record in enumerate(self.operations):
            # 1. Announce, and make the announcement durable.
            record["status"] = STATUS_INTENT
            self._journal()
            if at_boundary:
                at_boundary("after_intent", index)

            # 2. Mutate.
            if record["op"] == "write":
                atomic_write_text(
                    self._absolute(record["path"]), record["_text"],
                    temporary=self._absolute(record["temporary"]))
            else:
                destination = self._absolute(record["path"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(self._absolute(record["moved_from"])),
                            str(destination))
            if at_boundary:
                at_boundary("after_mutation", index)

            # 3. Confirm.
            observed = raw_digest_file(self._absolute(record["path"]))
            if observed != record["sha256_after"]:
                raise TransactionError(
                    f"{record['path']} does not hold the bytes this operation "
                    "announced it would write")
            record["status"] = STATUS_COMPLETED
            self._journal()
            if at_boundary:
                at_boundary("after_completed", index)
            if after_stage:
                after_stage((kinds or {}).get(index, record["op"]))

        self.state = STATE_APPLIED
        self._journal()
        return {"transaction_id": self.transaction_id,
                "manifest": str(self.manifest_path),
                "backup_directory": str(self.directory),
                "operations": len(self.operations),
                "state": self.state}

    def _absolute(self, relative: str) -> Path:
        return self.vault_root.joinpath(*PurePosixPath(relative).parts)

    # -- journal -----------------------------------------------------------

    def manifest(self) -> dict:
        return {
            "manifest_version": MANIFEST_VERSION,
            "generator": "scripts/build_obsidian_vault.py",
            "transaction_id": self.transaction_id,
            "state": self.state,
            "created_at_utc": _now(),
            "digest_algorithm": "sha256",
            "integrity_digest": "raw_bytes",
            "canonical_digests_are_diagnostic_only": True,
            "paths_are_relative_to": {"operations": "vault_root",
                                      "backups": "transaction_directory"},
            "repository": {"root": str(self.repository_root),
                           "name": self.repository_root.name},
            "vault": {"root": str(self.vault_root),
                      "name": self.vault_root.name},
            "backup_directory": str(self.directory),
            "operations": [{k: v for k, v in record.items()
                            if not k.startswith("_")}
                           for record in self.operations],
            "created_files": list(self.created_files),
            "created_directories": list(self.created_directories),
        }

    def _journal(self) -> Path:
        atomic_write_text(
            self.manifest_path,
            json.dumps(self.manifest(), indent=2, ensure_ascii=False) + "\n",
            fsync=True)
        return self.manifest_path

    # -- undo --------------------------------------------------------------

    def rollback(self) -> dict:
        """Undo this run from its own journal, through the same public path."""
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        try:
            result = rollback_manifest(manifest, self.vault_root,
                                       self.repository_root,
                                       manifest_path=self.manifest_path)
        except TransactionError as error:
            self.state = STATE_ROLLBACK_FAILED
            self._journal()
            return {"rolled_back": False, "problems": [str(error)],
                    "restored": 0, "removed": 0, "directories_removed": 0,
                    "state": self.state}
        self.state = result.get("state", STATE_ROLLED_BACK)
        return result


# ---------------------------------------------------------------------------
# Reading and validating a journal
# ---------------------------------------------------------------------------

def load_manifest(path) -> dict:
    """Read a journal, or refuse it.

    Only ``manifest.json`` is ever authoritative. A partially written journal
    lives under a dotted ``.tmp`` name until ``os.replace`` makes it the
    manifest, so it is never read here at all.
    """
    path = Path(path)
    if not path.is_file():
        raise TransactionError(f"no backup manifest at {path}")
    if path.name != MANIFEST_NAME:
        raise TransactionError(
            f"{path.name!r} is not a transaction journal; the authoritative "
            f"record is always {MANIFEST_NAME}, and an in-progress temporary "
            "file is never it")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TransactionError(f"{path} is not readable JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise TransactionError(f"{path} is not a JSON object")
    version = manifest.get("manifest_version")
    if version != MANIFEST_VERSION:
        raise TransactionError(
            f"{path} declares manifest_version {version!r}; this generator "
            f"understands {MANIFEST_VERSION}. A journal it cannot read is "
            "refused rather than partially interpreted")
    for key in ("transaction_id", "state", "repository", "vault", "operations",
                "created_files", "created_directories", "backup_directory"):
        if key not in manifest:
            raise TransactionError(f"{path} is missing required field {key!r}")
    if manifest["state"] not in ROLLBACKABLE_STATES + (STATE_ROLLED_BACK,):
        raise TransactionError(
            f"{path} is in state {manifest['state']!r}, which this generator "
            "does not know how to undo")
    return manifest


def validate_manifest(manifest: dict, vault_root, manifest_path) -> dict:
    """Confine every path a journal carries, before anything is restored.

    A manifest is a file on disk; treat it as untrusted structured input. This
    resolves each path against the roots given on the command line and refuses
    anything that escapes, duplicates or contradicts. It changes nothing.
    """
    manifest_path = Path(manifest_path)
    transaction_directory = safety.real_path(manifest_path.parent)
    vault = safety.real_path(vault_root)

    declared = manifest.get("backup_directory")
    if not isinstance(declared, str) or safety.real_path(declared) != \
            transaction_directory:
        raise TransactionError(
            f"the journal declares backup_directory {declared!r}, which is not "
            f"the directory it lives in ({transaction_directory}). A record "
            "that points its backups elsewhere is refused")

    backups_root = transaction_directory / BACKUP_SUBDIRECTORY
    operations = manifest["operations"]
    if not isinstance(operations, list):
        raise TransactionError("operations must be a list")

    resolved, seen_targets, seen_sources = [], set(), set()
    for index, record in enumerate(operations):
        if not isinstance(record, dict):
            raise TransactionError(f"operation {index} is not an object")
        for key in ("op", "status", "path", "existed_before"):
            if key not in record:
                raise TransactionError(
                    f"operation {index} is missing required field {key!r}")
        if record["op"] not in ("write", "move"):
            raise TransactionError(
                f"operation {index} has unknown op {record['op']!r}")
        if record["status"] not in STATUSES:
            raise TransactionError(
                f"operation {index} has unknown status {record['status']!r}")

        target = _under(vault, record["path"], field=f"operations[{index}].path")
        _refuse_journal_target(target, transaction_directory, manifest_path,
                               field=f"operations[{index}].path")
        if record["path"] in seen_targets:
            raise TransactionError(
                f"{record['path']} is the target of more than one operation; a "
                "journal with contradictory records is refused")
        seen_targets.add(record["path"])

        entry = {"index": index, "record": record, "target": target,
                 "source": None, "backup": None, "temporary": None}

        if record["op"] == "move":
            if "moved_from" not in record:
                raise TransactionError(f"operation {index} records no source")
            source = _under(vault, record["moved_from"],
                            field=f"operations[{index}].moved_from")
            _refuse_journal_target(source, transaction_directory, manifest_path,
                                   field=f"operations[{index}].moved_from")
            if record["moved_from"] in seen_sources:
                raise TransactionError(
                    f"{record['moved_from']} is moved by more than one operation")
            seen_sources.add(record["moved_from"])
            entry["source"] = source

        if record.get("backup"):
            entry["backup"] = _under(backups_root, record["backup"],
                                     field=f"operations[{index}].backup")
        elif record["existed_before"]:
            raise TransactionError(
                f"operation {index} replaced an existing file but records no "
                "backup copy")

        if record.get("temporary"):
            entry["temporary"] = _under(vault, record["temporary"],
                                        field=f"operations[{index}].temporary")
        resolved.append(entry)

    created_files = [_under(vault, value, field="created_files[]")
                     for value in manifest["created_files"]]
    created_directories = [_under(vault, value, field="created_directories[]")
                           for value in manifest["created_directories"]]
    for path in created_files + created_directories:
        _refuse_journal_target(path, transaction_directory, manifest_path,
                               field="created paths")

    return {"operations": resolved,
            "created_files": {str(p) for p in created_files},
            "created_directories": created_directories,
            "transaction_directory": transaction_directory,
            "vault_root": vault}


def _refuse_journal_target(path: Path, transaction_directory: Path,
                           manifest_path: Path, *, field: str) -> None:
    resolved = safety.real_path(path)
    if resolved == safety.real_path(manifest_path):
        raise TransactionError(
            f"{field} targets the journal itself; a rollback may not rewrite "
            "the record it is reading")
    if resolved == transaction_directory or _is_within(resolved,
                                                       transaction_directory):
        raise TransactionError(
            f"{field} targets the transaction directory; the backups a "
            "rollback restores from are not something it may modify")


def describe(manifest: dict) -> str:
    """A one-line account of what a journal says happened."""
    statuses = [record.get("status") for record in manifest["operations"]]
    completed = statuses.count(STATUS_COMPLETED)
    announced = statuses.count(STATUS_INTENT)
    total = len(statuses)
    incomplete = manifest["state"] in (STATE_PREPARED, STATE_APPLYING)
    suffix = (" — INCOMPLETE: this transaction did not finish"
              if incomplete else "")
    return (f"state {manifest['state']}, {completed} of {total} operations "
            f"completed, {announced} announced but unconfirmed{suffix}")


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def _resolve_state(entry) -> str:
    """What actually happened to one recorded operation, from the disk.

    An ``intent`` record is the interesting case: the machine may have stopped
    on either side of the mutation, and the journal carries both digests
    precisely so the two can be told apart.
    """
    record, target = entry["record"], entry["target"]
    before, after = record.get("sha256_before"), record.get("sha256_after")

    if record["op"] == "move":
        source = entry["source"]
        source_ok = source.is_file() and before and raw_digest_file(source) == before
        target_ok = target.is_file() and after and raw_digest_file(target) == after
        if source_ok and not target.exists():
            return NOT_APPLIED
        if target_ok and not source.exists():
            return APPLIED
        return AMBIGUOUS

    if not record["existed_before"]:
        if not target.exists():
            return NOT_APPLIED
        if target.is_file() and after and raw_digest_file(target) == after:
            return APPLIED
        return AMBIGUOUS

    if not target.is_file():
        return AMBIGUOUS
    observed = raw_digest_file(target)
    if before and observed == before:
        return NOT_APPLIED
    if after and observed == after:
        return APPLIED
    return AMBIGUOUS


def rollback_manifest(manifest: dict, vault_root, repository_root,
                      manifest_path=None) -> dict:
    """Undo a recorded transaction, or refuse and change nothing.

    Accepts an interrupted transaction: ``prepared`` and ``applying`` are the
    states a crash leaves behind, and they are exactly when an undo is wanted.

    Every ``intent`` and ``completed`` operation is resolved against the disk
    **before** the first restoration. One ambiguity refuses the whole rollback.
    There is no flag to override that: restoring over a later edit is a second
    loss, not a recovery.
    """
    recorded_vault = safety.real_path(manifest["vault"]["root"])
    given_vault = safety.real_path(vault_root)
    if recorded_vault != given_vault:
        raise TransactionError(
            f"this journal records vault {recorded_vault}, and {given_vault} "
            "was given. The vault is named explicitly so a rollback cannot be "
            "pointed at the wrong one")
    recorded_repository = safety.real_path(manifest["repository"]["root"])
    if recorded_repository != safety.real_path(repository_root):
        raise TransactionError(
            f"this journal was written for repository {recorded_repository}, "
            f"not {safety.real_path(repository_root)}")

    manifest_path = Path(manifest_path or
                         Path(manifest["backup_directory"]) / MANIFEST_NAME)
    checked = validate_manifest(manifest, given_vault, manifest_path)

    interesting = [entry for entry in checked["operations"]
                   if entry["record"]["status"] in (STATUS_INTENT,
                                                    STATUS_COMPLETED)]
    drifted, applied = [], []
    for entry in interesting:
        state = _resolve_state(entry)
        if state == APPLIED:
            applied.append(entry)
        elif state == AMBIGUOUS:
            drifted.append(
                f"{entry['record']['path']}: neither the bytes this "
                "transaction recorded before it, nor the ones it announced "
                "it would write")

    if drifted:
        raise TransactionError(
            "refusing the rollback: " + "; ".join(drifted[:5])
            + (f" (and {len(drifted) - 5} more)" if len(drifted) > 5 else "")
            + ". Nothing was changed. A line-ending change counts here, because "
            "a transaction is a claim about bytes on disk. Restoring over a "
            "later edit would be a second loss, so there is no way to force this")

    strays = _stray_temporaries(checked["operations"])
    if not applied:
        return {"rolled_back": False, "reason": "already rolled back",
                "restored": 0, "removed": 0, "directories_removed": 0,
                "state": manifest.get("state"), "problems": [],
                "temporary_files_left": strays}

    result = _undo(applied, checked["created_files"],
                   checked["created_directories"])
    result["reason"] = "restored"
    result["temporary_files_left"] = _stray_temporaries(checked["operations"])
    result["state"] = (STATE_ROLLED_BACK if result["rolled_back"]
                       else STATE_ROLLBACK_FAILED)

    manifest["state"] = result["state"]
    if result["rolled_back"]:
        for record in manifest["operations"]:
            if record.get("status") in (STATUS_INTENT, STATUS_COMPLETED):
                record["status"] = STATUS_PENDING
    manifest["rolled_back_at_utc"] = _now()
    if not result["rolled_back"]:
        manifest["rollback_problems"] = result["problems"]
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", fsync=True)
    return result


def _stray_temporaries(entries) -> list:
    """Temporary files a crash may have left, removed only when accounted for.

    A stray is removed only if the journal named it *and* it holds the bytes
    that operation announced. Anything else is reported and left where it is:
    an unexplained file in somebody's vault is not this tool's to delete.
    """
    left = []
    for entry in entries:
        temporary = entry["temporary"]
        if temporary is None or not temporary.is_file():
            continue
        expected = entry["record"].get("sha256_after")
        if expected and raw_digest_file(temporary) == expected:
            temporary.unlink()
            continue
        left.append(str(temporary))
    return left


def _undo(entries, created_files, created_directories) -> dict:
    """Reverse resolved operations, newest first, touching nothing else."""
    restored = removed = 0
    problems = []

    for entry in reversed(list(entries)):
        record, target = entry["record"], entry["target"]
        try:
            if record["op"] == "move":
                origin = entry["source"]
                origin.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(origin))
                if raw_digest_file(origin) != record["sha256_before"]:
                    problems.append(
                        f"{origin}: restored bytes do not match the original")
                else:
                    restored += 1
                continue
            if not record["existed_before"]:
                if str(target) in created_files:
                    target.unlink()
                    removed += 1
                else:
                    problems.append(
                        f"{target}: created by this transaction but not listed "
                        "in created_files; left in place")
                continue
            source = entry["backup"]
            if source is None or not source.is_file():
                problems.append(f"{target}: no backup copy recorded")
                continue
            shutil.copy2(source, target)
            if raw_digest_file(target) != record["sha256_before"]:
                problems.append(
                    f"{target}: restored bytes do not match the original digest")
            else:
                restored += 1
        except OSError as error:  # noqa: PERF203 - one failure must not stop the rest
            problems.append(f"{target}: {error}")

    directories_removed = 0
    for directory in sorted(created_directories, key=lambda p: len(str(p)),
                            reverse=True):
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
                directories_removed += 1
        except OSError as error:
            problems.append(f"{directory}: {error}")

    return {"rolled_back": not problems, "restored": restored, "removed": removed,
            "directories_removed": directories_removed, "problems": problems}


def _temporary_name(relative: str) -> str:
    """The temporary file a write will use, chosen before the write happens."""
    parts = PurePosixPath(relative).parts
    stem = f".{parts[-1]}.{uuid.uuid4().hex[:8]}.tmp"
    return "/".join((*parts[:-1], stem))


def _missing_parents(directory) -> list:
    """Directories that do not exist yet, outermost first."""
    directory = Path(directory)
    missing = []
    while not directory.exists() and directory != directory.parent:
        missing.append(directory)
        directory = directory.parent
    return list(reversed(missing))
