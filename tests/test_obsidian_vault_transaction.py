"""Apply, backup, automatic rollback and explicit rollback — in temp vaults only.

The vault is outside version control. That single fact drives every test here:
there is no `git checkout` to undo a bad run, so the run has to undo itself.

Three properties are worth more than the rest.

**A failure leaves the vault as it was**, not partly written. Each mutation
stage gets a test that raises immediately after it and requires the vault to
come back byte-for-byte, including files the run had already replaced and files
it had already moved.

**A rollback refuses rather than guesses.** If anything the transaction wrote
has changed since — most importantly, if somebody edited a generated note — the
whole rollback is refused and nothing is touched. Restoring old bytes over a
later edit is a second loss wearing a recovery's clothes, so there is no flag to
force it.

**Unrelated files are invisible to all of it.** A note the operator wrote, a
filter they added, a file that merely happens to sit in the vault: none is
backed up, moved, overwritten or removed, before or after.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.vault import transaction  # noqa: E402

RUNNER = ROOT / "scripts" / "build_obsidian_vault.py"
CONFIG_PATH = ROOT / "configs" / "obsidian_vault.yaml"


def _load_builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_txn_build_vault", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_builder()


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _snapshot(root: Path) -> dict:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


@pytest.fixture
def vault(tmp_path):
    """A vault holding the operator's own files as well as archivable ones."""
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    (root / ".obsidian" / "app.json").write_text(
        json.dumps({"userIgnoreFilters": ["Personal/journal",
                                          "path:Attachments/scratch"]},
                   indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "Unrelated.md").write_text("mine\n", encoding="utf-8", newline="\n")
    (root / "Notes").mkdir()
    (root / "Notes" / "Diary.md").write_text("private\n", encoding="utf-8",
                                             newline="\n")
    (root / "decision_log.md").write_text("early snapshot\n", encoding="utf-8",
                                          newline="\n")
    (root / "project_roadmap.md").write_text("early roadmap\n", encoding="utf-8",
                                             newline="\n")
    return root


@pytest.fixture
def backups(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    return root


def _apply(config, vault, backups, after_stage=None):
    plan = build.build_plan(config, vault, ROOT)
    return build.apply_plan(plan, backups, after_stage=after_stage)


def _untouched(before: dict, after: dict) -> None:
    """The operator's own files must be identical on both sides."""
    for key in ("Unrelated.md", "Notes/Diary.md"):
        assert after[key] == before[key], key


# ---------------------------------------------------------------------------
# A successful apply
# ---------------------------------------------------------------------------

def test_apply_writes_the_plan_and_records_a_complete_manifest(config, vault,
                                                               backups):
    before = _snapshot(vault)
    result = _apply(config, vault, backups)

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == transaction.MANIFEST_VERSION
    assert manifest["transaction_id"] == result["transaction_id"]
    assert manifest["created_at_utc"].endswith("Z")
    assert manifest["repository"]["root"] == str(Path(ROOT).resolve())
    assert manifest["vault"]["root"] == str(vault.resolve())
    assert manifest["state"] == transaction.STATE_APPLIED
    assert manifest["integrity_digest"] == "raw_bytes"
    assert manifest["canonical_digests_are_diagnostic_only"] is True
    assert manifest["operations"], "an apply that recorded nothing did nothing"

    assert manifest["paths_are_relative_to"] == {
        "operations": "vault_root", "backups": "transaction_directory"}
    for record in manifest["operations"]:
        assert record["op"] in ("write", "move")
        assert record["status"] == transaction.STATUS_COMPLETED
        assert record["existed_before"] in (True, False)
        # Paths are relative; nothing absolute is stored in a journal.
        assert not Path(record["path"]).is_absolute()
        assert ".." not in record["path"].split("/")
        target = vault.joinpath(*record["path"].split("/"))
        # The authoritative digests are raw bytes, recomputed here from disk.
        assert record["sha256_after"] == transaction.raw_digest_file(target)
        if record["existed_before"]:
            assert record["backup"], f"{record['path']} was replaced without a copy"
            assert record["sha256_before"]
            backup = Path(manifest["backup_directory"]) / "files"
            backup = backup.joinpath(*record["backup"].split("/"))
            assert backup.is_file()
            assert transaction.raw_digest_file(backup) == record["sha256_before"], (
                "the stored copy must match the digest the journal recorded"
            )
        if record["op"] == "move":
            assert record["moved_from"]
            assert not Path(record["moved_from"]).is_absolute()

    after = _snapshot(vault)
    assert (vault / "Knowledge Graph").is_dir()
    _untouched(before, after)
    assert "decision_log.md" not in after
    assert "_archive/decision_log.md" in after


def test_apply_is_idempotent(config, vault, backups):
    _apply(config, vault, backups)
    after_first = _snapshot(vault)
    second = _apply(config, vault, backups)
    assert _snapshot(vault) == after_first, (
        "a second identical apply changed content; the generator is supposed "
        "to recognise what it already wrote"
    )
    plan = build.build_plan(config, vault, ROOT)
    for action in plan["actions"]:
        assert action["kind"] not in ("note_update", "canvas_update",
                                      "settings_update"), action
    assert second["transaction_id"]


def test_apply_preserves_user_filters_and_adds_its_own(config, vault, backups):
    _apply(config, vault, backups)
    settings = json.loads(
        (vault / ".obsidian" / "app.json").read_text(encoding="utf-8"))
    filters = settings["userIgnoreFilters"]
    assert filters[:2] == ["Personal/journal", "path:Attachments/scratch"]
    assert len(filters) == len(set(filters))
    assert any(value.endswith("/.venv") for value in filters)


def test_generated_text_uses_lf(config, vault, backups):
    _apply(config, vault, backups)
    for path in (vault / "Knowledge Graph").rglob("*"):
        if path.is_file():
            assert b"\r\n" not in path.read_bytes(), path


def test_a_hand_edited_note_survives_an_apply(config, vault, backups):
    _apply(config, vault, backups)
    victim = next((vault / "Knowledge Graph").glob("*.md"))
    edited = victim.read_text(encoding="utf-8") + "\nmy own paragraph\n"
    victim.write_text(edited, encoding="utf-8", newline="\n")

    plan = build.build_plan(config, vault, ROOT)
    assert any(item["path"] == str(victim) and item["kind"] == "hand_edited"
               for item in plan["protected"])
    build.apply_plan(plan, backups)
    assert victim.read_text(encoding="utf-8") == edited


def test_a_blocked_archive_destination_is_not_overwritten(config, vault, backups):
    archive = vault / "_archive"
    archive.mkdir()
    (archive / "decision_log.md").write_text("already here\n", encoding="utf-8",
                                             newline="\n")
    plan = build.build_plan(config, vault, ROOT)
    assert any(item["name"] == "decision_log.md"
               for item in plan["archive_blocked"])
    build.apply_plan(plan, backups)
    assert (archive / "decision_log.md").read_text(encoding="utf-8") == "already here\n"
    assert (vault / "decision_log.md").is_file(), "a blocked move leaves the source"


# ---------------------------------------------------------------------------
# Failure part-way through
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage", ["note_new", "canvas_new", "archive_move",
                                   "archive_readme_new", "settings_update"])
def test_a_failure_at_any_stage_rolls_the_whole_apply_back(config, vault,
                                                           backups, stage):
    """Injected failure after each mutation kind; the vault must come back."""
    before = _snapshot(vault)
    seen = []

    def explode(kind):
        seen.append(kind)
        if kind == stage:
            raise RuntimeError(f"injected failure after {kind}")

    with pytest.raises(SystemExit) as raised:
        _apply(config, vault, backups, after_stage=explode)

    message = str(raised.value)
    assert "injected failure" in message
    assert "rollback: complete" in message
    assert stage in seen, "the stage under test never ran"
    assert _snapshot(vault) == before, (
        f"the vault did not return to its previous state after {stage}"
    )


def test_a_failed_apply_still_writes_its_manifest(config, vault, backups):
    def explode(kind):
        if kind == "archive_move":
            raise RuntimeError("injected")

    with pytest.raises(SystemExit):
        _apply(config, vault, backups, after_stage=explode)
    manifests = list(backups.rglob("manifest.json"))
    assert len(manifests) == 1, "a failed run must still leave its record"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["operations"], "the record must say what it had done"


# ---------------------------------------------------------------------------
# Explicit rollback
# ---------------------------------------------------------------------------

def test_rollback_restores_exact_bytes_and_locations(config, vault, backups):
    before = _snapshot(vault)
    result = _apply(config, vault, backups)
    assert _snapshot(vault) != before

    manifest = transaction.load_manifest(result["manifest"])
    undone = transaction.rollback_manifest(manifest, vault, ROOT)
    assert undone["rolled_back"] is True
    assert undone["reason"] == "restored"
    assert _snapshot(vault) == before, "rollback must be byte-exact"
    assert (vault / "decision_log.md").is_file(), "a moved file returns home"
    assert not (vault / "_archive" / "decision_log.md").exists()


def test_rollback_is_idempotent(config, vault, backups):
    before = _snapshot(vault)
    result = _apply(config, vault, backups)
    manifest = transaction.load_manifest(result["manifest"])
    transaction.rollback_manifest(manifest, vault, ROOT)
    again = transaction.rollback_manifest(manifest, vault, ROOT)
    assert again["reason"] == "already rolled back"
    assert _snapshot(vault) == before


def test_rollback_refuses_when_a_generated_file_was_edited_afterwards(
        config, vault, backups):
    """No force. A refusal that changes nothing beats a silent second loss."""
    result = _apply(config, vault, backups)
    applied = _snapshot(vault)
    victim = next((vault / "Knowledge Graph").glob("*.md"))
    victim.write_text("edited after the apply\n", encoding="utf-8", newline="\n")
    changed = _snapshot(vault)

    manifest = transaction.load_manifest(result["manifest"])
    with pytest.raises(transaction.TransactionError, match="refusing the rollback"):
        transaction.rollback_manifest(manifest, vault, ROOT)
    assert _snapshot(vault) == changed, "a refused rollback changes nothing"
    assert applied != changed


def test_rollback_refuses_a_different_vault(config, vault, backups, tmp_path):
    result = _apply(config, vault, backups)
    other = tmp_path / "someone elses vault"
    other.mkdir()
    manifest = transaction.load_manifest(result["manifest"])
    with pytest.raises(transaction.TransactionError, match="records vault"):
        transaction.rollback_manifest(manifest, other, ROOT)
    assert not any(other.iterdir()), "the wrong vault must be left empty"


def test_rollback_refuses_an_unreadable_or_unknown_manifest(tmp_path, vault):
    missing = tmp_path / "nothing.json"
    with pytest.raises(transaction.TransactionError, match="no backup manifest"):
        transaction.load_manifest(missing)

    broken_directory = tmp_path / "broken"
    broken_directory.mkdir()
    broken = broken_directory / "manifest.json"
    broken.write_text("{not json", encoding="utf-8", newline="\n")
    with pytest.raises(transaction.TransactionError, match="readable JSON"):
        transaction.load_manifest(broken)

    future = tmp_path / "manifest.json"
    future.write_text(json.dumps({"manifest_version": 99}) + "\n",
                      encoding="utf-8", newline="\n")
    with pytest.raises(transaction.TransactionError, match="manifest_version"):
        transaction.load_manifest(future)

    # Only manifest.json is authoritative, so a stray file is refused by name.
    stray = tmp_path / "not-the-journal.json"
    stray.write_text("{}\n", encoding="utf-8", newline="\n")
    with pytest.raises(transaction.TransactionError, match="not a transaction"):
        transaction.load_manifest(stray)


def test_rollback_leaves_unrelated_files_alone(config, vault, backups):
    before = _snapshot(vault)
    result = _apply(config, vault, backups)
    (vault / "Added later.md").write_text("after the apply\n", encoding="utf-8",
                                          newline="\n")
    manifest = transaction.load_manifest(result["manifest"])
    transaction.rollback_manifest(manifest, vault, ROOT)
    after = _snapshot(vault)
    _untouched(before, after)
    assert after["Added later.md"] == b"after the apply\n", (
        "rollback removes only what the transaction created"
    )


# ---------------------------------------------------------------------------
# Backup-root placement
# ---------------------------------------------------------------------------

def test_a_backup_root_inside_the_notes_folder_is_refused(config, vault):
    from thai_supply_chain_ews.vault import safety

    inside = vault / "Knowledge Graph" / "backups"
    inside.mkdir(parents=True)
    with pytest.raises(safety.VaultPathError, match="inside"):
        safety.assert_disjoint(inside, vault / "Knowledge Graph",
                               first_field="--backup-root",
                               second_field="target.notes_folder")


def test_a_transaction_never_reuses_another_runs_directory(vault, backups):
    first = transaction.Transaction(backups, ROOT, vault, transaction_id="fixed")
    first.prepare([])
    second = transaction.Transaction(backups, ROOT, vault, transaction_id="fixed")
    with pytest.raises(transaction.TransactionError, match="already exists"):
        second.prepare([])


def test_a_transaction_refuses_to_mutate_before_it_is_prepared(vault, backups):
    """Backups and the journal come first, or nothing happens at all."""
    txn = transaction.Transaction(backups, ROOT, vault)
    with pytest.raises(transaction.TransactionError, match="not prepared"):
        txn.execute()
    assert not txn.directory.exists()


def test_a_transaction_refuses_a_backup_root_that_does_not_exist(vault, tmp_path):
    absent = tmp_path / "no backups here"
    txn = transaction.Transaction(absent, ROOT, vault)
    with pytest.raises(transaction.TransactionError, match="does not exist"):
        txn.prepare([])
    assert not absent.exists(), "a misspelled backup path must not be created"


def test_a_transaction_refuses_a_backup_root_that_is_a_file(vault, tmp_path):
    regular = tmp_path / "backups.txt"
    regular.write_text("not a directory\n", encoding="utf-8", newline="\n")
    txn = transaction.Transaction(regular, ROOT, vault)
    with pytest.raises(transaction.TransactionError, match="not a directory"):
        txn.prepare([])


def test_atomic_write_leaves_no_temporary_behind(tmp_path):
    target = tmp_path / "note.md"
    transaction.atomic_write_text(target, "body\n")
    assert target.read_bytes() == b"body\n"
    assert [p.name for p in tmp_path.iterdir()] == ["note.md"]


# ---------------------------------------------------------------------------
# Correction 1: integrity is raw bytes, never a normalised digest
# ---------------------------------------------------------------------------

LF_BYTES = b"alpha\nbeta\ngamma\n"
CRLF_BYTES = b"alpha\r\nbeta\r\ngamma\r\n"


def test_lf_and_crlf_have_different_raw_digests(tmp_path):
    """The premise. If these matched, none of the checks below could work."""
    lf, crlf = tmp_path / "lf.md", tmp_path / "crlf.md"
    lf.write_bytes(LF_BYTES)
    crlf.write_bytes(CRLF_BYTES)
    assert transaction.raw_digest_file(lf) != transaction.raw_digest_file(crlf)
    # And the diagnostic digest deliberately does not distinguish them, which is
    # exactly why it may not decide anything.
    assert (transaction.canonical_digest_file(lf)
            == transaction.canonical_digest_file(crlf))


def test_the_journal_records_raw_digests_not_canonical_ones(vault, backups):
    """A CRLF file's recorded digest must be of its CRLF bytes."""
    target = vault / "Notes" / "Crlf.md"
    target.write_bytes(CRLF_BYTES)
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "replacement\n"}])
    record = txn.operations[0]
    assert record["sha256_before"] == transaction.raw_digest_bytes(CRLF_BYTES)
    assert record["sha256_before"] != transaction.raw_digest_bytes(LF_BYTES)
    assert record["canonical_sha256_before"] == transaction.raw_digest_bytes(
        LF_BYTES), "the canonical field is the normalised one, kept separate"


def test_exact_original_bytes_are_restored_including_line_endings(vault, backups):
    """Rollback returns the CRLF file as CRLF, not as its normalised form."""
    target = vault / "Notes" / "Crlf.md"
    target.write_bytes(CRLF_BYTES)
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "replacement\n"}])
    txn.execute()
    assert target.read_bytes() == b"replacement\n"

    manifest = transaction.load_manifest(txn.manifest_path)
    transaction.rollback_manifest(manifest, vault, ROOT)
    assert target.read_bytes() == CRLF_BYTES, (
        "a byte-exact restore means the carriage returns come back too"
    )


def test_a_line_ending_only_change_after_apply_refuses_the_rollback(vault, backups):
    """The case a normalised digest would have missed entirely.

    Nothing about the file's *text* changed. Its bytes did, so the file this
    transaction wrote is no longer the file on disk, and restoring over it would
    discard a change somebody made.
    """
    target = vault / "Notes" / "Written.md"
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "one\ntwo\n"}])
    txn.execute()
    assert target.read_bytes() == b"one\ntwo\n"

    target.write_bytes(b"one\r\ntwo\r\n")
    drifted = _snapshot(vault)

    manifest = transaction.load_manifest(txn.manifest_path)
    with pytest.raises(transaction.TransactionError, match="refusing the rollback"):
        transaction.rollback_manifest(manifest, vault, ROOT)
    assert _snapshot(vault) == drifted, "a refused rollback changes nothing"
    assert target.read_bytes() == b"one\r\ntwo\r\n"


def test_no_transaction_decision_consults_a_canonical_digest():
    """Structural, so a future edit cannot quietly reintroduce normalisation.

    Every comparison that authorises something must read a raw digest. The
    canonical helper may only be *stored*.
    """
    source = (ROOT / "src" / "thai_supply_chain_ews" / "vault"
              / "transaction.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.Compare):
            rendered = ast.unparse(node)
            assert "canonical_digest_file" not in rendered, (
                f"a canonical digest is being compared: {rendered}"
            )
        if isinstance(node, ast.Assert):
            assert "canonical_digest_file" not in ast.unparse(node)


# ---------------------------------------------------------------------------
# Correction 2: the journal is durable before the first mutation
# ---------------------------------------------------------------------------

def test_the_journal_exists_before_the_first_managed_mutation(config, vault,
                                                              backups):
    """Prepared and on disk, with the vault still untouched."""
    before = _snapshot(vault)
    operations, kinds = build.planned_operations(
        build.build_plan(config, vault, ROOT))
    txn = transaction.Transaction(backups, ROOT, vault)
    manifest_path = txn.prepare(operations)

    assert manifest_path.is_file(), "no journal before the first write"
    manifest = transaction.load_manifest(manifest_path)
    assert manifest["state"] == transaction.STATE_PREPARED
    assert manifest["operations"], "a prepared journal lists what it will do"
    assert all(record["status"] == transaction.STATUS_PENDING
               for record in manifest["operations"])
    # The post-state digest is known before the mutation, which is what lets a
    # crash between the write and its confirmation be resolved either way.
    assert all(record["sha256_after"] for record in manifest["operations"])
    assert all(record["temporary"] or record["op"] == "move"
               for record in manifest["operations"])
    assert _snapshot(vault) == before, "prepare must not touch the vault"
    assert not (vault / "Knowledge Graph").exists()
    del kinds


def test_every_backup_is_verified_during_prepare(vault, backups):
    target = vault / "Unrelated.md"
    original = target.read_bytes()
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "new\n"}])
    copy = txn.backup_directory / "Unrelated.md"
    assert copy.is_file()
    assert copy.read_bytes() == original
    assert transaction.raw_digest_file(copy) == txn.operations[0]["sha256_before"]
    assert target.read_bytes() == original, "prepare copies; it does not write"


class Interrupted(BaseException):
    """Not an Exception: nothing in the transaction may catch this.

    Simulates the machine stopping, so recovery has to come from the journal on
    disk rather than from an exception handler that happened to run.
    """


def _interrupt_after(config, vault, backups, completed_count):
    """Run an apply and abandon the process after N completed operations.

    Simulates an abrupt interruption by leaving the transaction object behind
    without rolling it back, so what remains on disk is only the journal. The
    recovery below then goes through the ordinary ``--rollback`` path, reading
    that journal from scratch.
    """
    operations, kinds = build.planned_operations(
        build.build_plan(config, vault, ROOT))
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare(operations)

    done = []

    def stop(_kind):
        done.append(_kind)
        if len(done) >= completed_count:
            raise Interrupted

    try:
        txn.execute(after_stage=stop, kinds=kinds)
    except Interrupted:
        pass
    return txn


@pytest.mark.parametrize("completed_count", [1, 2, 3, 5])
def test_an_interrupted_transaction_is_recoverable_from_its_journal(
        config, vault, backups, completed_count):
    """No caught exception, no in-memory state: only what is on disk."""
    before = _snapshot(vault)
    txn = _interrupt_after(config, vault, backups, completed_count)
    interrupted = _snapshot(vault)
    assert interrupted != before, "the interruption must happen mid-apply"

    # A separate read of the journal, exactly as a later invocation would do.
    manifest = transaction.load_manifest(txn.manifest_path)
    assert manifest["state"] == transaction.STATE_APPLYING
    completed = [r for r in manifest["operations"] if r["status"] == "completed"]
    assert len(completed) == completed_count
    assert all(r["sha256_after"] for r in completed)
    assert transaction.describe(manifest).endswith(
        "this transaction did not finish")

    result = transaction.rollback_manifest(
        manifest, vault, ROOT, manifest_path=txn.manifest_path)
    assert result["rolled_back"] is True
    assert _snapshot(vault) == before, (
        f"recovery from {completed_count} completed operations was not exact"
    )
    after = _snapshot(vault)
    _untouched(before, after)


def test_an_interrupted_transaction_reports_itself_as_incomplete(config, vault,
                                                                 backups):
    txn = _interrupt_after(config, vault, backups, 2)
    manifest = transaction.load_manifest(txn.manifest_path)
    description = transaction.describe(manifest)
    assert "INCOMPLETE" in description
    assert "2 of" in description
    assert manifest["state"] != transaction.STATE_APPLIED, (
        "an unfinished transaction must never read as a success"
    )


def test_a_rollback_of_a_prepared_but_unstarted_transaction_is_accepted(
        config, vault, backups):
    before = _snapshot(vault)
    operations, _ = build.planned_operations(build.build_plan(config, vault, ROOT))
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare(operations)
    manifest = transaction.load_manifest(txn.manifest_path)
    assert manifest["state"] == transaction.STATE_PREPARED
    result = transaction.rollback_manifest(manifest, vault, ROOT)
    assert result["reason"] == "already rolled back"
    assert _snapshot(vault) == before


def test_a_partially_written_journal_is_never_authoritative(config, vault,
                                                            backups):
    """A torn temporary file must not be mistaken for the record."""
    txn = _interrupt_after(config, vault, backups, 2)
    torn = txn.directory / ".manifest.json.deadbeef.tmp"
    torn.write_text('{"manifest_version": 2, "state": "appl',
                    encoding="utf-8", newline="\n")

    with pytest.raises(transaction.TransactionError, match="not a transaction"):
        transaction.load_manifest(torn)

    # The real journal is still readable and still correct.
    manifest = transaction.load_manifest(txn.manifest_path)
    assert manifest["state"] == transaction.STATE_APPLYING
    assert torn.name.startswith(".") and torn.name.endswith(".tmp")


def test_the_journal_state_reaches_applied_then_rolled_back(config, vault,
                                                            backups):
    result = _apply(config, vault, backups)
    manifest = transaction.load_manifest(result["manifest"])
    assert manifest["state"] == transaction.STATE_APPLIED

    undone = transaction.rollback_manifest(manifest, vault, ROOT)
    assert undone["state"] == transaction.STATE_ROLLED_BACK
    persisted = transaction.load_manifest(result["manifest"])
    assert persisted["state"] == transaction.STATE_ROLLED_BACK
    assert persisted["rolled_back_at_utc"].endswith("Z")


def test_a_failed_rollback_is_recorded_as_such(vault, backups):
    """The state must say so, and keep enough to try again later."""
    target = vault / "Unrelated.md"
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "new\n"}])
    txn.execute()
    # Remove the stored copy so the restore cannot succeed.
    (txn.backup_directory / "Unrelated.md").unlink()
    result = txn.rollback()
    assert result["rolled_back"] is False
    assert txn.state == transaction.STATE_ROLLBACK_FAILED
    manifest = transaction.load_manifest(txn.manifest_path)
    assert manifest["state"] == transaction.STATE_ROLLBACK_FAILED
    assert manifest["operations"][0]["status"] == "completed", (
        "a failed rollback keeps the record needed for a later retry"
    )

# ---------------------------------------------------------------------------
# The three crash windows, for both kinds of mutation
# ---------------------------------------------------------------------------

WRITE_PLAN_INDEX = 0
BOUNDARIES = ("after_intent", "after_mutation", "after_completed")


def _stop_at(boundary_name, target_index):
    """A boundary seam that stops the machine at one exact point."""
    def hook(name, index):
        if name == boundary_name and index == target_index:
            raise Interrupted
    return hook


def _crash(config, vault, backups, boundary_name, target_index):
    """Run until the chosen boundary, then abandon the process entirely.

    The transaction object is thrown away without rolling back, so the only
    thing recovery can use is the journal that reached the disk.
    """
    operations, kinds = build.planned_operations(
        build.build_plan(config, vault, ROOT))
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare(operations)
    try:
        txn.execute(kinds=kinds, at_boundary=_stop_at(boundary_name, target_index))
    except Interrupted:
        pass
    return txn


def _recover(manifest_path, vault):
    """Recovery exactly as a later, separate invocation would do it."""
    manifest = transaction.load_manifest(manifest_path)
    return manifest, transaction.rollback_manifest(
        manifest, vault, ROOT, manifest_path=manifest_path)


def _first_index_of(config, vault, op_kind):
    operations, _ = build.planned_operations(build.build_plan(config, vault, ROOT))
    for index, entry in enumerate(operations):
        if entry["op"] == op_kind:
            return index
    raise AssertionError(f"the plan contains no {op_kind} operation")


@pytest.mark.parametrize("boundary_name", BOUNDARIES)
@pytest.mark.parametrize("op_kind", ["write", "move"])
def test_every_crash_window_is_recoverable(config, vault, backups,
                                           boundary_name, op_kind):
    """Interrupt at each boundary, for each mutation kind, and recover.

    ``after_intent`` is the window the write-ahead record exists for: the
    journal already says what was about to happen, and the vault has not been
    touched yet. ``after_mutation`` is the one that used to be unrecoverable --
    the change landed but was never confirmed -- and it is resolved by comparing
    the file against the digest the intent record announced in advance.
    """
    before = _snapshot(vault)
    index = _first_index_of(config, vault, op_kind)
    txn = _crash(config, vault, backups, boundary_name, index)

    # Read the journal as it was left, before the rollback rewrites it.
    interrupted = transaction.load_manifest(txn.manifest_path)
    assert interrupted["state"] == transaction.STATE_APPLYING
    statuses = [record["status"] for record in interrupted["operations"]]
    if boundary_name == "after_intent":
        assert transaction.STATUS_INTENT in statuses

    _, result = _recover(txn.manifest_path, vault)
    assert _snapshot(vault) == before, (
        f"recovery after {boundary_name} on a {op_kind} was not byte-exact"
    )
    assert result["problems"] == []
    _untouched(before, _snapshot(vault))


@pytest.mark.parametrize("op_kind", ["write", "move"])
def test_the_window_between_mutation_and_confirmation_is_the_hard_one(
        config, vault, backups, op_kind):
    """Prove the mutation really did land before recovery undid it.

    Without this the ``after_mutation`` case above could pass vacuously, by the
    interruption happening before anything changed.
    """
    before = _snapshot(vault)
    index = _first_index_of(config, vault, op_kind)
    txn = _crash(config, vault, backups, "after_mutation", index)

    mid = _snapshot(vault)
    assert mid != before, "the mutation under test did not happen"

    manifest = transaction.load_manifest(txn.manifest_path)
    unconfirmed = [r for r in manifest["operations"]
                   if r["status"] == transaction.STATUS_INTENT]
    assert unconfirmed, "the operation must still be recorded as unconfirmed"
    assert "announced but unconfirmed" in transaction.describe(manifest)

    _, result = _recover(txn.manifest_path, vault)
    assert result["rolled_back"] is True
    assert _snapshot(vault) == before


def test_a_created_file_is_removed_only_when_its_post_state_matches(
        config, vault, backups):
    """An unconfirmed creation whose bytes are somebody else's is not deleted."""
    before = _snapshot(vault)
    index = _first_index_of(config, vault, "write")
    txn = _crash(config, vault, backups, "after_mutation", index)

    manifest = transaction.load_manifest(txn.manifest_path)
    record = next(r for r in manifest["operations"]
                  if r["status"] == transaction.STATUS_INTENT)
    target = vault.joinpath(*record["path"].split("/"))
    target.write_text("somebody else got here first\n", encoding="utf-8",
                      newline="\n")
    tampered = _snapshot(vault)

    with pytest.raises(transaction.TransactionError, match="refusing the rollback"):
        _recover(txn.manifest_path, vault)
    assert _snapshot(vault) == tampered, "a refused rollback deletes nothing"
    assert target.read_text(encoding="utf-8") == "somebody else got here first\n"
    del before


def test_an_ambiguous_move_refuses_the_whole_rollback(config, vault, backups):
    """Source and destination both present is a state no move produces."""
    index = _first_index_of(config, vault, "move")
    txn = _crash(config, vault, backups, "after_completed", index)

    manifest = transaction.load_manifest(txn.manifest_path)
    record = next(r for r in manifest["operations"] if r["op"] == "move")
    source = vault.joinpath(*record["moved_from"].split("/"))
    source.write_text("a duplicate appeared\n", encoding="utf-8", newline="\n")
    tampered = _snapshot(vault)

    with pytest.raises(transaction.TransactionError, match="refusing the rollback"):
        _recover(txn.manifest_path, vault)
    assert _snapshot(vault) == tampered


def test_a_prepared_transaction_with_no_intents_is_a_safe_no_op(config, vault,
                                                                backups):
    before = _snapshot(vault)
    operations, _ = build.planned_operations(build.build_plan(config, vault, ROOT))
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare(operations)
    manifest, result = _recover(txn.manifest_path, vault)
    assert manifest["state"] == transaction.STATE_PREPARED
    assert result["reason"] == "already rolled back"
    assert _snapshot(vault) == before


# ---------------------------------------------------------------------------
# Temporary files a crash may leave
# ---------------------------------------------------------------------------

def test_a_stray_temporary_holding_the_announced_bytes_is_removed(vault, backups):
    target = vault / "Notes" / "Written.md"
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "body\n"}])
    record = txn.operations[0]
    stray = vault.joinpath(*record["temporary"].split("/"))
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"body\n")           # exactly what the journal announced

    manifest = transaction.load_manifest(txn.manifest_path)
    result = transaction.rollback_manifest(manifest, vault, ROOT,
                                           manifest_path=txn.manifest_path)
    assert not stray.exists(), "an accounted-for temporary is cleaned up"
    assert result["temporary_files_left"] == []


def test_a_stray_temporary_with_unexpected_bytes_is_left_and_reported(vault,
                                                                      backups):
    """An unexplained file in somebody's vault is not this tool's to delete."""
    target = vault / "Notes" / "Written.md"
    txn = transaction.Transaction(backups, ROOT, vault)
    txn.prepare([{"op": "write", "path": str(target), "text": "body\n"}])
    record = txn.operations[0]
    stray = vault.joinpath(*record["temporary"].split("/"))
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"not what was announced\n")

    manifest = transaction.load_manifest(txn.manifest_path)
    result = transaction.rollback_manifest(manifest, vault, ROOT,
                                           manifest_path=txn.manifest_path)
    assert stray.is_file(), "an unaccounted-for file must survive"
    assert stray.read_bytes() == b"not what was announced\n"
    assert [Path(p).name for p in result["temporary_files_left"]] == [stray.name]


# ---------------------------------------------------------------------------
# A journal is untrusted structured input
# ---------------------------------------------------------------------------

@pytest.fixture
def sentinel(tmp_path):
    """A file outside the vault that no tampered manifest may reach."""
    path = tmp_path / "sentinel.txt"
    path.write_bytes(b"do not touch me\n")
    return path


def _applied(config, vault, backups):
    result = _apply(config, vault, backups)
    path = Path(result["manifest"])
    return path, json.loads(path.read_text(encoding="utf-8"))


def _tamper(manifest_path: Path, manifest: dict) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8", newline="\n")


ESCAPES = [
    "../sentinel.txt",
    "../../sentinel.txt",
    "/etc/passwd",
    "C:/Windows/system32/x",
    "\\\\server\\share\\x",
    "Notes/../../sentinel.txt",
]


@pytest.mark.parametrize("field", ["path", "moved_from", "backup", "temporary"])
@pytest.mark.parametrize("escape", ESCAPES)
def test_a_tampered_operation_path_is_refused(config, vault, backups, sentinel,
                                              field, escape):
    """Every path-bearing field, pointed at a sentinel outside the vault."""
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before, sentinel_before = _snapshot(vault), sentinel.read_bytes()

    record = next((r for r in manifest["operations"] if field in r and r[field]),
                  None)
    if record is None:
        pytest.skip(f"no operation in this plan carries {field!r}")
    record[field] = escape
    _tamper(manifest_path, manifest)

    with pytest.raises(transaction.TransactionError):
        _recover(manifest_path, vault)

    assert sentinel.read_bytes() == sentinel_before, "the sentinel was touched"
    assert _snapshot(vault) == vault_before, "the vault was changed"
    assert not (sentinel.parent / "Notes").exists(), (
        "validation must not create a parent directory on the way out"
    )


@pytest.mark.parametrize("field", ["created_files", "created_directories"])
def test_a_tampered_created_list_is_refused(config, vault, backups, sentinel,
                                            field):
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before, sentinel_before = _snapshot(vault), sentinel.read_bytes()
    manifest[field] = ["../sentinel.txt"]
    _tamper(manifest_path, manifest)

    with pytest.raises(transaction.TransactionError, match="traverses upward"):
        _recover(manifest_path, vault)
    assert sentinel.read_bytes() == sentinel_before
    assert _snapshot(vault) == vault_before


def test_a_relocated_backup_directory_is_refused(config, vault, backups,
                                                  sentinel):
    """The journal must live in the directory it claims its backups are in."""
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before = _snapshot(vault)
    manifest["backup_directory"] = str(sentinel.parent)
    _tamper(manifest_path, manifest)

    with pytest.raises(transaction.TransactionError, match="backup_directory"):
        _recover(manifest_path, vault)
    assert _snapshot(vault) == vault_before
    assert sentinel.read_bytes() == b"do not touch me\n"


def test_an_operation_targeting_the_journal_itself_is_refused(config, vault,
                                                              backups):
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before = _snapshot(vault)
    # Reach the transaction directory from the vault by traversal; refused
    # before the target is even compared.
    manifest["operations"][0]["path"] = "../backups/x/manifest.json"
    _tamper(manifest_path, manifest)
    with pytest.raises(transaction.TransactionError):
        _recover(manifest_path, vault)
    assert _snapshot(vault) == vault_before


def test_duplicate_operation_records_are_refused(config, vault, backups):
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before = _snapshot(vault)
    manifest["operations"].append(dict(manifest["operations"][0]))
    _tamper(manifest_path, manifest)
    with pytest.raises(transaction.TransactionError,
                       match="more than one operation"):
        _recover(manifest_path, vault)
    assert _snapshot(vault) == vault_before


def test_a_replaced_file_without_a_backup_record_is_refused(config, vault,
                                                            backups):
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before = _snapshot(vault)
    record = next(r for r in manifest["operations"] if r["existed_before"])
    record["backup"] = None
    _tamper(manifest_path, manifest)
    with pytest.raises(transaction.TransactionError, match="no backup copy"):
        _recover(manifest_path, vault)
    assert _snapshot(vault) == vault_before


MALFORMED = [
    (lambda m: m["operations"].insert(0, "not an object"), "not an object"),
    (lambda m: m["operations"][0].pop("status"), "missing required field"),
    (lambda m: m["operations"][0].update(op="delete"), "unknown op"),
    (lambda m: m["operations"][0].update(status="finished"), "unknown status"),
    (lambda m: m["operations"][0].update(path=""), "non-empty"),
    (lambda m: m.update(operations={}), "must be a list"),
]


@pytest.mark.parametrize(("mutate", "pattern"), MALFORMED,
                         ids=[pattern for _, pattern in MALFORMED])
def test_malformed_operation_records_are_refused(config, vault, backups,
                                                 mutate, pattern):
    """One fresh vault per case.

    Reusing one would have applied twice, and the second apply is correctly a
    no-op -- leaving an empty operation list with nothing to tamper with.
    """
    manifest_path, manifest = _applied(config, vault, backups)
    vault_before = _snapshot(vault)
    mutate(manifest)
    _tamper(manifest_path, manifest)
    with pytest.raises(transaction.TransactionError, match=pattern):
        _recover(manifest_path, vault)
    assert _snapshot(vault) == vault_before

# ---------------------------------------------------------------------------
# This module's own boundary
# ---------------------------------------------------------------------------

def test_no_test_in_this_module_touches_a_real_vault():
    parent_sentinel = "ROOT" + "." + "parent"
    source = Path(__file__).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        statements = [n for n in node.body
                      if not (isinstance(n, ast.Expr)
                              and isinstance(n.value, ast.Constant)
                              and isinstance(n.value.value, str))]
        body = chr(10).join(ast.unparse(n) for n in statements)
        assert parent_sentinel not in body, node.name
        # Keyed to mutation, not to the word "vault": a static test that merely
        # reads this repository's own source mentions the package directory
        # without touching anything, and flagging it taught nothing.
        mutates = any(verb in body for verb in
                      ("write_text", "write_bytes", "mkdir", "unlink",
                       "apply_plan", ".prepare(", ".execute(", "rollback_manifest"))
        if mutates:
            fixtures = {argument.arg for argument in node.args.args}
            assert "tmp_path" in body or fixtures & {"tmp_path", "vault", "backups"}, (
                f"{node.name} mutates something without a temporary-directory "
                "fixture"
            )
