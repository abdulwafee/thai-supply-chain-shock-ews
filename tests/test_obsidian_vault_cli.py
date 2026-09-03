"""The vault generator's command line, and the destination it will not guess.

Every test here builds its own vault in a pytest temporary directory. None reads
or writes the vault on anybody's machine, and a test at the end proves that by
inspecting this module's own source.

The defect this module exists to prevent is not a crash. It is a *successful*
run against a directory nobody named. The previous generator took no arguments
at all, which reads as cautious and was the opposite: with nothing parsed, every
flag was ignored, ``--help`` ran the generator, and the destination came from a
configuration value that resolved to whatever directory happened to contain the
checkout. The vault is outside version control, so there was nothing to undo it
with.

So: the root is required, ``--dry-run`` writes nothing, ``--apply`` needs a
backup root, and the three modes are mutually exclusive.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thai_supply_chain_ews.vault import safety  # noqa: E402

RUNNER = ROOT / "scripts" / "build_obsidian_vault.py"
CONFIG_PATH = ROOT / "configs" / "obsidian_vault.yaml"

#: Used only as negative sentinels; neither may appear in production code.
KNOWN_CHECKOUT_NAMES = ("thai-supply-chain-ews", "thai-supply-chain-shock-ews")


def _load_builder():
    """Import the runner as a module. It parses nothing and writes nothing on import."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_cli_build_vault", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_builder()


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _snapshot(root: Path) -> dict:
    """Every file under a directory, by relative path and bytes."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


@pytest.fixture
def vault(tmp_path):
    """A throwaway vault with settings, an unrelated note and archivable files."""
    root = tmp_path / "a vault"
    (root / ".obsidian").mkdir(parents=True)
    (root / ".obsidian" / "app.json").write_text(
        json.dumps({"userIgnoreFilters": ["Personal/journal"]}, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    (root / "Unrelated.md").write_text("mine, not the generator's\n",
                                       encoding="utf-8", newline="\n")
    (root / "decision_log.md").write_text("an early snapshot\n",
                                          encoding="utf-8", newline="\n")
    return root


def _run(*arguments):
    """Invoke the runner as a subprocess, the way an operator would."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(RUNNER), *[str(a) for a in arguments]],
        capture_output=True, text=True, check=False, timeout=600,
    )


# ---------------------------------------------------------------------------
# The interface itself
# ---------------------------------------------------------------------------

def test_help_exits_zero_and_touches_no_vault(vault):
    """The single most dangerous thing about the previous version.

    With no argument parsing, ``--help`` was an unrecognised string that got
    ignored, and the generator ran. Now it prints and exits.
    """
    before = _snapshot(vault)
    completed = _run("--help")
    assert completed.returncode == 0
    assert "--vault-root" in completed.stdout
    assert "--dry-run" in completed.stdout
    assert _snapshot(vault) == before


def test_no_arguments_fails_and_touches_no_vault(vault):
    before = _snapshot(vault)
    completed = _run()
    assert completed.returncode == 2
    assert "usage" in (completed.stderr + completed.stdout).lower()
    assert _snapshot(vault) == before


def test_an_unknown_argument_fails_and_touches_no_vault(vault):
    before = _snapshot(vault)
    completed = _run("--wipe-everything", "--vault-root", vault)
    assert completed.returncode != 0
    assert _snapshot(vault) == before


def test_the_modes_are_mutually_exclusive(vault):
    before = _snapshot(vault)
    for pair in (("--dry-run", "--apply"),
                 ("--dry-run", "--rollback", "m.json"),
                 ("--apply", "--rollback", "m.json")):
        completed = _run("--vault-root", vault, *pair)
        assert completed.returncode != 0, pair
        assert "not allowed with" in completed.stderr
    assert _snapshot(vault) == before


def test_dry_run_without_a_vault_root_is_refused(vault):
    before = _snapshot(vault)
    completed = _run("--dry-run")
    assert completed.returncode == 2
    assert "--vault-root" in completed.stderr
    assert _snapshot(vault) == before


def test_apply_without_a_backup_root_is_refused(vault):
    """A backup that was never requested is a backup that does not exist."""
    before = _snapshot(vault)
    completed = _run("--vault-root", vault, "--apply")
    assert completed.returncode == 2
    assert "--backup-root" in completed.stderr
    assert _snapshot(vault) == before


def test_a_missing_vault_root_is_refused_rather_than_created(tmp_path):
    absent = tmp_path / "no vault here"
    completed = _run("--vault-root", absent, "--dry-run")
    assert completed.returncode == 2
    assert "does not exist" in completed.stderr
    assert not absent.exists(), "a typo must not become a directory tree"


def test_a_vault_root_inside_the_repository_is_refused():
    completed = _run("--vault-root", ROOT / "docs", "--dry-run")
    assert completed.returncode == 2
    assert "inside the repository" in completed.stderr


# ---------------------------------------------------------------------------
# The implicit destination is gone
# ---------------------------------------------------------------------------

def test_the_contract_can_no_longer_select_a_vault(config):
    target = config["target"]
    assert "vault_root" not in target
    assert target["vault_root_is_configured"] is False
    assert target["vault_root_source"] == "command_line_argument"


def test_no_production_file_derives_a_vault_from_the_repository_parent():
    """``ROOT / ".."`` was the implicit destination. It must not return.

    Sentinels are assembled at run time so this guard cannot match its own
    source -- the project already uses the idiom for planted test secrets.
    """
    parent_sentinel = "ROOT / '" + ".." + "'"
    for relative in ("scripts/build_obsidian_vault.py",
                     "src/thai_supply_chain_ews/vault/safety.py",
                     "src/thai_supply_chain_ews/vault/transaction.py"):
        # Code only. Comments vanish through unparse and docstrings are dropped
        # explicitly, because a module that explains the destination it no
        # longer derives would otherwise fail its own rule.
        module = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        module.body = [n for n in module.body
                       if not (isinstance(n, ast.Expr)
                               and isinstance(n.value, ast.Constant))]
        code = _strip_docstrings(module)
        assert parent_sentinel not in code, relative
        for name in KNOWN_CHECKOUT_NAMES:
            assert name not in code, f"{relative} hard-codes {name!r}"

    # The contract is checked as data: does it actually still select a root?
    contract = yaml.safe_load(
        (ROOT / "configs" / "obsidian_vault.yaml").read_text(encoding="utf-8"))
    assert "vault_root" not in contract["target"]
    assert ".." not in _values(contract["target"])


def _strip_docstrings(module) -> str:
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            node.body = [n for n in node.body
                         if not (isinstance(n, ast.Expr)
                                 and isinstance(n.value, ast.Constant)
                                 and isinstance(n.value.value, str))] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(module))


def _values(mapping) -> set:
    return {value for value in mapping.values() if isinstance(value, str)}


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def test_dry_run_creates_and_changes_nothing(vault):
    before = _snapshot(vault)
    completed = _run("--vault-root", vault, "--dry-run")
    assert completed.returncode == 0, completed.stderr
    assert "dry-run" in completed.stdout
    assert _snapshot(vault) == before
    assert not (vault / "Knowledge Graph").exists()
    assert not (vault / "_archive").exists()


def test_the_dry_run_plan_is_deterministic(config, vault):
    first = build.build_plan(config, vault, ROOT)
    second = build.build_plan(config, vault, ROOT)
    assert [a["kind"] for a in first["actions"]] == [
        a["kind"] for a in second["actions"]]
    assert [a["path"] for a in first["actions"]] == [
        a["path"] for a in second["actions"]]
    assert first["counts"] == second["counts"]
    assert _snapshot(vault)  # the vault still exists and was not emptied


def test_the_plan_names_every_outcome_kind(config, vault):
    plan = build.build_plan(config, vault, ROOT)
    kinds = {action["kind"] for action in plan["actions"]}
    assert any(kind.startswith("note_") for kind in kinds)
    assert any(kind.startswith("canvas_") for kind in kinds)
    assert "archive_move" in kinds
    assert any(kind.startswith("settings_") for kind in kinds)
    assert "archive_blocked" in plan["counts"]
    assert "archive_absent" in plan["counts"]
    assert isinstance(plan["protected"], list)


def test_a_traversing_configured_folder_is_refused_before_any_write(config, vault):
    before = _snapshot(vault)
    for bad in ("../escape", "/etc", "C:/Windows", "..\\escape"):
        contract = {**config, "target": {**config["target"], "notes_folder": bad}}
        with pytest.raises(safety.VaultPathError):
            build.build_plan(contract, vault, ROOT)
    assert _snapshot(vault) == before


def test_a_symlinked_notes_folder_that_escapes_the_vault_is_refused(config, tmp_path):
    """Spelling stays inside the vault; resolution does not."""
    vault_root = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault_root.mkdir()
    outside.mkdir()
    try:
        (vault_root / "Knowledge Graph").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform or account cannot create a directory symlink; "
                    "the confinement rule is unchanged, it simply cannot be "
                    "demonstrated here")
    with pytest.raises(safety.VaultPathError, match="outside the vault root"):
        build.build_plan(config, vault_root, ROOT)


# ---------------------------------------------------------------------------
# Correction 3: the backup root must already exist
# ---------------------------------------------------------------------------

def test_a_missing_backup_root_is_refused_and_never_created(vault, tmp_path):
    """A misspelled backup path must fail, not quietly become a directory.

    An empty directory created from a typo is worse than an error: the run
    looks backed up, and the copies are somewhere nobody will look.
    """
    before = _snapshot(vault)
    absent = tmp_path / "backpus"          # deliberately misspelled
    completed = _run("--vault-root", vault, "--apply", "--backup-root", absent)
    assert completed.returncode == 2
    assert "--backup-root" in completed.stderr
    assert "does not exist" in completed.stderr
    assert not absent.exists(), "the typo created a directory"
    assert _snapshot(vault) == before


def test_a_backup_root_that_is_a_regular_file_is_refused(vault, tmp_path):
    before = _snapshot(vault)
    regular = tmp_path / "backups.txt"
    regular.write_text("not a directory\n", encoding="utf-8", newline="\n")
    completed = _run("--vault-root", vault, "--apply", "--backup-root", regular)
    assert completed.returncode == 2
    assert "not a directory" in completed.stderr
    assert regular.read_text(encoding="utf-8") == "not a directory\n"
    assert _snapshot(vault) == before


def test_a_backup_root_inside_the_repository_is_refused(vault):
    before = _snapshot(vault)
    completed = _run("--vault-root", vault, "--apply",
                     "--backup-root", ROOT / "docs")
    assert completed.returncode == 2
    assert "inside the repository" in completed.stderr
    assert _snapshot(vault) == before


def test_a_backup_root_inside_a_managed_output_directory_is_refused(vault,
                                                                    tmp_path):
    """A backup kept inside the folder it protects is lost with it."""
    before = _snapshot(vault)
    inside = vault / "Knowledge Graph" / "backups"
    inside.mkdir(parents=True)
    completed = _run("--vault-root", vault, "--apply", "--backup-root", inside)
    assert completed.returncode == 2
    assert "inside" in completed.stderr
    assert list((vault / "Knowledge Graph").glob("*.md")) == [], (
        "no note may be written when the backup root is refused"
    )
    assert _snapshot(vault) == before | {
        key: value for key, value in _snapshot(vault).items()
        if key.startswith("Knowledge Graph/")
    }, "only the empty directory this test created may differ"
    del tmp_path


def test_a_backup_root_symlink_escaping_into_the_repository_is_refused(vault,
                                                                       tmp_path):
    link = tmp_path / "backups-link"
    try:
        link.symlink_to(ROOT / "docs", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform or account cannot create a directory "
                    "symlink; the resolution rule is unchanged, it simply "
                    "cannot be demonstrated here")
    completed = _run("--vault-root", vault, "--apply", "--backup-root", link)
    assert completed.returncode == 2
    assert "inside the repository" in completed.stderr


def test_an_existing_backup_root_is_accepted_and_gets_one_subdirectory(vault,
                                                                       tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    completed = _run("--vault-root", vault, "--apply", "--backup-root", backups)
    assert completed.returncode == 0, completed.stderr
    children = list(backups.iterdir())
    assert len(children) == 1 and children[0].is_dir(), (
        "exactly one transaction directory beneath the root the operator named"
    )
    assert (children[0] / "manifest.json").is_file()


def test_the_documentation_says_the_backup_root_must_exist():
    text = (ROOT / "docs" / "obsidian_vault_usage.md").read_text(
        encoding="utf-8").lower()
    assert "must already exist" in text
    assert "never created for you" in text
    assert "raw sha-256 over the exact file bytes" in text
    assert "prepared" in text and "rollback_failed" in text

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
