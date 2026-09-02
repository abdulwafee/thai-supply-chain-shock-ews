"""Obsidian vault export.

Hermetic: everything here runs against the repository's own text files and a
temporary directory. No official download, no generated table, no vault on the
developer's machine.

The synthetic failures are the point. A generator that writes documents about a
project is a generator that can quietly publish a locked path, somebody's home
directory, a link to a note that does not exist, or an edit somebody made by
hand. Each of those has a test that plants it and requires the machinery to
refuse.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.vault import emit, harvest, notes

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "obsidian_vault.yaml"


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def data():
    return harvest.harvest(ROOT)


@pytest.fixture(scope="module")
def rendered(data, config):
    return emit.build_notes(data, config)


# ===========================================================================
# 1. The contract
# ===========================================================================

def test_the_contract_writes_outside_the_repository(config):
    assert config["target"]["writes_inside_repository"] is False
    assert config["target"]["vault_root"] == ".."


def test_the_contract_refuses_to_overwrite_a_hand_edit(config):
    assert config["frontmatter"]["hand_edit_policy"] == "report_and_skip"
    assert "content_sha256" in config["frontmatter"]["required_keys"]


def test_the_contract_names_what_may_never_appear(config):
    prohibitions = config["prohibitions"]
    assert prohibitions["no_absolute_paths"] is True
    assert prohibitions["no_invented_numbers"] is True
    assert "locked_test/" in prohibitions["locked_outcome_path_fragments"]


def test_the_contract_records_what_it_deliberately_does_not_produce(config):
    absent = config["not_produced"]
    for key in ("dataview_queries", "base_files", "one_note_per_decision"):
        assert absent[key]["reason"].strip()


# ===========================================================================
# 2. Harvesting
# ===========================================================================

def test_task_codes_reconcile_across_all_four_filename_shapes():
    assert harvest.normalise_task("b1") == "B1"
    assert harvest.normalise_task("c11r1") == "C11-R1"
    assert harvest.normalise_task("e2r1") == "E2-R1"
    assert harvest.normalise_task("d3r1") == "D3-R1"
    assert harvest.normalise_task("c1_5") == "C1.5"
    assert harvest.normalise_task("notatask") == ""


def test_every_decision_row_is_accounted_for(data):
    decisions = data["decisions"]
    tagged = sum(len(rows) for rows in decisions["by_task"].values())
    assert tagged + len(decisions["untagged"]) == decisions["total"]
    assert decisions["total"] > 0


def test_untagged_decisions_are_collected_not_guessed(data, rendered):
    """A decision with no task tag must not be attached to a task."""
    untagged_ids = {row["id"] for row in data["decisions"]["untagged"]}
    assert untagged_ids, "the fixture assumes some rows carry no tag"
    for task in data["tasks"].values():
        assert not {row["id"] for row in task["decisions"]} & untagged_ids
    report = next(n for n in rendered if n.kind == "report")
    assert all(identifier in report.body for identifier in untagged_ids)


def test_facts_are_read_from_files_not_estimated(data):
    facts = data["facts"]
    for key in ("panel_source", "release_source", "ledger_source"):
        assert (ROOT / facts[key]).is_file()
    assert facts["industries"] == 12
    assert facts["month_count"] > 0


# ===========================================================================
# 3. Notes
# ===========================================================================

def test_every_note_declares_its_provenance_and_a_checksum(rendered, config):
    generated_by = config["frontmatter"]["generated_by"]
    for note in rendered:
        assert note.generated_from, note.title
        text = note.render(generated_by)
        meta, body = notes.parse_frontmatter(text)
        for key in config["frontmatter"]["required_keys"]:
            assert key in meta, (note.title, key)
        assert meta["content_sha256"] == notes.body_checksum(body)


def test_every_declared_source_file_exists(rendered):
    for note in rendered:
        for relative in note.generated_from:
            path = ROOT / relative
            assert path.exists(), f"{note.title} cites a missing {relative}"


def test_every_wikilink_points_at_a_note_that_exists(rendered):
    """A link to a note that does not exist is a broken claim in a graph."""
    titles = {notes.slug(note.title) for note in rendered}
    broken = []
    for note in rendered:
        for target in re.findall(r"\[\[([^\]|#]+)", note.body):
            if target.strip() not in titles:
                broken.append(f"{note.title} -> {target.strip()}")
    assert broken == []


def test_note_filenames_are_unique_and_safe(rendered):
    names = [note.filename for note in rendered]
    assert len(names) == len(set(names))
    for name in names:
        assert not re.search(r'[\\/:*?"<>|#^\[\]]', name)


def test_the_index_links_every_task_and_package(rendered, data):
    index = next(n for n in rendered if n.kind == "index")
    for code in data["tasks"]:
        assert notes.slug(f"Task {code}") in index.body, code
    for package in data["packages"]:
        assert notes.slug(f"Package {package['name']}") in index.body


def test_supersession_is_recorded_in_both_directions(rendered):
    by_title = {note.title: note for note in rendered}
    for earlier, later in emit.SUPERSESSION.items():
        if f"Task {earlier}" not in by_title or f"Task {later}" not in by_title:
            continue
        assert "Superseded by" in by_title[f"Task {earlier}"].body, earlier
        assert "Supersedes" in by_title[f"Task {later}"].body, later


# ===========================================================================
# 4. The canvas
# ===========================================================================

def test_the_canvas_is_valid_and_points_at_real_notes(data, rendered):
    canvas = json.loads(emit.build_canvas(data, "Knowledge Graph"))
    files = {n["file"] for n in canvas["nodes"] if n["type"] == "file"}
    existing = {f"Knowledge Graph/{note.filename}" for note in rendered}
    assert files
    assert files <= existing
    identifiers = {n["id"] for n in canvas["nodes"]}
    for edge in canvas["edges"]:
        assert edge["fromNode"] in identifiers
        assert edge["toNode"] in identifiers


def test_the_canvas_isolates_the_locked_test(data):
    canvas = json.loads(emit.build_canvas(data, "Knowledge Graph"))
    sealed = next(n for n in canvas["nodes"] if n["id"] == "sealed")
    assert "Sealed and unopened" in sealed["text"]
    touching = [e for e in canvas["edges"]
                if "sealed" in (e["fromNode"], e["toNode"])]
    assert touching == [], "the sealed node must have no edge in or out"


# ===========================================================================
# 5. Synthetic failures
# ===========================================================================

def _note(body: str) -> notes.Note:
    return notes.Note(title="T", kind="task", body=body,
                      generated_from=["README.md"])


def test_synthetic_01_a_locked_path_in_a_note_is_refused(config):
    with pytest.raises(notes.NoteError, match="locked-outcome path"):
        _note("see docs/locked_test/outcomes.json").guard(config["prohibitions"])


def test_synthetic_02_an_absolute_home_path_in_a_note_is_refused(config):
    planted = "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "vault"
    with pytest.raises(notes.NoteError, match="absolute local path"):
        _note(f"built at {planted}").guard(config["prohibitions"])
    with pytest.raises(notes.NoteError, match="absolute local path"):
        _note("built at /home/someone/vault").guard(config["prohibitions"])


def test_synthetic_03_a_note_with_no_provenance_is_refused(config):
    orphan = notes.Note(title="T", kind="task", body="x", generated_from=[])
    with pytest.raises(notes.NoteError, match="declares no source file"):
        orphan.guard(config["prohibitions"])


def test_synthetic_04_a_hand_edited_note_is_detected_and_not_overwritten(tmp_path):
    note = _note("original body")
    path = tmp_path / note.filename
    path.write_text(note.render("scripts/build_obsidian_vault.py"), encoding="utf-8")
    assert notes.classify_existing(path, note.body) == "unchanged"

    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("original body", "edited by a person"),
                    encoding="utf-8")
    assert notes.classify_existing(path, note.body) == "hand_edited"


def test_synthetic_05_a_repository_change_marks_the_note_stale(tmp_path):
    note = _note("original body")
    path = tmp_path / note.filename
    path.write_text(note.render("scripts/build_obsidian_vault.py"), encoding="utf-8")
    assert notes.classify_existing(path, "the repository moved") == "stale"


def test_synthetic_06_a_file_this_generator_did_not_write_is_never_touched(tmp_path):
    path = tmp_path / "T.md"
    path.write_text("# somebody else's note\n", encoding="utf-8")
    assert notes.classify_existing(path, "anything") == "foreign"


def test_synthetic_07_trailing_whitespace_is_not_mistaken_for_an_edit():
    assert notes.body_checksum("a\nb") == notes.body_checksum("a   \nb\t")


def test_synthetic_08_writing_inside_the_repository_is_refused():
    """The one thing that would recreate the duplication this export removes."""
    source = (ROOT / "scripts" / "build_obsidian_vault.py").read_text(encoding="utf-8")
    assert "assert_outside_repository" in source
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'" + str(ROOT / "src") + "');"
         "sys.argv=['x'];"
         "import importlib.util, pathlib;"
         "spec=importlib.util.spec_from_file_location('b', r'"
         + str(ROOT / "scripts" / "build_obsidian_vault.py") + "');"
         "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
         "m.assert_outside_repository(pathlib.Path(r'" + str(ROOT / "docs") + "'))"],
        capture_output=True, text=True, check=False, timeout=300,
    )
    assert completed.returncode != 0
    assert "inside the repository" in completed.stdout + completed.stderr


def test_synthetic_09_the_archive_moves_and_never_deletes(config):
    plan = config["archive"]
    assert plan["move_not_delete"] is True
    source = (ROOT / "scripts" / "build_obsidian_vault.py").read_text(encoding="utf-8")
    assert "shutil.move" in source
    for verb in ("os.remove", "unlink(", "rmtree", "write_text(stub"):
        assert verb not in source


def test_synthetic_10_every_archived_file_names_its_successor(config):
    for entry in config["archive"]["files"]:
        successor = ROOT.parent / entry["superseded_by"]
        assert successor.is_file(), entry["superseded_by"]
        assert entry["note"].strip()


# ===========================================================================
# 6. The runner
# ===========================================================================

def test_the_runner_takes_no_arguments_and_offers_no_escape_hatch():
    import ast

    source = (ROOT / "scripts" / "build_obsidian_vault.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    assert not main.args.args and not main.args.kwonlyargs
    for escape in ("argparse", "sys.argv[1", "--force", "--overwrite", "--inside"):
        assert escape not in source
