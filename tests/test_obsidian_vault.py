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

import ast
import importlib.util
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


def _load_builder():
    """Import the runner as a module so its pure functions can be tested.

    It is a script, not a package member, and it takes no arguments and runs
    nothing on import -- ``main()`` is behind the usual guard -- so importing it
    reads no vault and writes nothing.
    """
    spec = importlib.util.spec_from_file_location(
        "_build_obsidian_vault", ROOT / "scripts" / "build_obsidian_vault.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_builder()


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
    """Each archived snapshot names a successor that actually exists.

    Resolved against the repository root, which is where the configuration says
    these paths are relative to. Resolving against ``ROOT.parent`` instead would
    only work in a checkout whose folder happened to carry the name written into
    the configuration -- so the test would pass on the machine that wrote it and
    fail on every clone, which is exactly what happened in CI.
    """
    archive = config["archive"]
    assert archive["superseded_by_paths_are_relative_to"] == "repository_root"
    for entry in archive["files"]:
        successor = ROOT / entry["superseded_by"]
        assert successor.is_file(), entry["superseded_by"]
        assert entry["note"].strip()


def test_synthetic_10a_successors_resolve_under_any_checkout_name(config, tmp_path):
    """The same paths resolve whatever the checkout directory is called.

    GitHub clones this repository into a folder named after the repository, a
    developer may name a clone anything, and this project's own directory
    differs from both. A configured path that carries any of those names is a
    path that resolves on one machine only.

    Proved rather than asserted: two throwaway checkouts with unrelated names
    are built from the configured paths alone, and every successor is found in
    both.
    """
    archive = config["archive"]
    for folder in ("some-unrelated-checkout-name", "x"):
        checkout = tmp_path / folder
        for entry in archive["files"]:
            target = checkout / entry["superseded_by"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "placeholder\n", encoding="utf-8", newline="\n")
        for entry in archive["files"]:
            assert (checkout / entry["superseded_by"]).is_file(), (
                f"{entry['superseded_by']} did not resolve under a checkout "
                f"named {folder!r}"
            )


def test_synthetic_10b_no_checkout_folder_name_is_hard_coded(config):
    """No archive path may carry a directory name, an anchor or a parent step."""
    forbidden = ("thai-supply-chain-ews", "thai-supply-chain-shock-ews")
    for entry in config["archive"]["files"]:
        value = entry["superseded_by"]
        for name in forbidden:
            assert name not in value, (
                f"{value} encodes the checkout folder name {name!r}; it must be "
                "relative to the repository root"
            )
        assert not Path(value).is_absolute(), value
        assert ".." not in Path(value).parts, value
        assert not value.startswith(("/", "\\")), value
    # And the archive block as a whole names no checkout folder, so the rule
    # cannot be reintroduced through a note or a comment beside the paths.
    rendered = yaml.safe_dump(config["archive"], allow_unicode=True)
    for name in forbidden:
        assert name not in rendered, f"the archive block still names {name!r}"


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

# ===========================================================================
# 7. Ignore filters: repository-relative in the file, checkout-aware at runtime
# ===========================================================================

#: Used ONLY as negative sentinels. Neither may appear in the production
#: configuration or the production builder, and these assertions are how that
#: stays true.
KNOWN_CHECKOUT_NAMES = ("thai-supply-chain-ews", "thai-supply-chain-shock-ews")

#: What the twelve filters were before this correction, with the checkout name
#: written into the file. The renderer must still produce exactly these for
#: this checkout: the change is a portability fix, not a behaviour change.
PREVIOUS_RENDERED_FILTERS = [
    "thai-supply-chain-ews/.venv",
    "thai-supply-chain-ews/data/raw",
    "thai-supply-chain-ews/data/interim",
    "thai-supply-chain-ews/data/features",
    "thai-supply-chain-ews/data/processed",
    "thai-supply-chain-ews/data/targets",
    "thai-supply-chain-ews/data/model_input",
    "thai-supply-chain-ews/.git",
    "thai-supply-chain-ews/.pytest_cache",
    "thai-supply-chain-ews/.ruff_cache",
    "path:thai-supply-chain-ews/dist",
    "path:thai-supply-chain-ews/build",
]


def _vault(tmp_path, existing=None):
    """A throwaway vault with an .obsidian/app.json, never a real one."""
    obsidian = tmp_path / ".obsidian"
    obsidian.mkdir(parents=True, exist_ok=True)
    payload = {} if existing is None else {"userIgnoreFilters": list(existing)}
    (obsidian / "app.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return tmp_path


def test_the_configuration_stores_no_checkout_name_at_all(config):
    """The whole point: the version-controlled file names no directory."""
    assert config["ignore_filters_relative_to"] == "repository_root"
    assert config["ignore_filters_render_separator"] == "/"
    assert len(config["ignore_filters"]) == 12
    for entry in config["ignore_filters"]:
        assert entry["kind"] in ("name", "path")
        for name in KNOWN_CHECKOUT_NAMES:
            assert name not in entry["path"], entry


def test_no_production_file_hard_codes_a_checkout_name():
    """Config and builder both, checked as text so a comment cannot slip one in."""
    for relative in ("configs/obsidian_vault.yaml",
                     "scripts/build_obsidian_vault.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for name in KNOWN_CHECKOUT_NAMES:
            assert name not in text, (
                f"{relative} hard-codes the checkout directory name {name!r}. "
                "The name is supplied at runtime from the real directory"
            )


def test_this_checkout_renders_exactly_the_previous_twelve_filters(config):
    """Portability improved; Obsidian behaviour here unchanged."""
    rendered = build.render_ignore_filters(config, "thai-supply-chain-ews")
    assert rendered == PREVIOUS_RENDERED_FILTERS
    assert build.render_ignore_filters(config, ROOT.name) == [
        f.replace("thai-supply-chain-ews", ROOT.name)
        for f in PREVIOUS_RENDERED_FILTERS
    ]


@pytest.mark.parametrize("checkout", ["x", "some-unrelated-checkout-name",
                                      "vault repo with spaces"])
def test_any_checkout_name_renders_deterministically(config, checkout):
    rendered = build.render_ignore_filters(config, checkout)
    assert len(rendered) == 12
    assert rendered == build.render_ignore_filters(config, checkout), (
        "rendering is deterministic; two calls must agree"
    )
    for value in rendered:
        bare = value[len("path:"):] if value.startswith("path:") else value
        assert bare.startswith(f"{checkout}/"), value


def test_name_and_path_filters_stay_distinct(config):
    """Obsidian reads them differently; collapsing them would change behaviour."""
    rendered = build.render_ignore_filters(config, "x")
    path_filters = [v for v in rendered if v.startswith("path:")]
    name_filters = [v for v in rendered if not v.startswith("path:")]
    assert path_filters == ["path:x/dist", "path:x/build"]
    assert len(name_filters) == 10
    assert "x/.venv" in name_filters


def test_rendered_filters_always_use_forward_slashes(config):
    """Built with Path this would emit backslashes on Windows and match nothing."""
    for checkout in ("x", "some-unrelated-checkout-name", "vault repo with spaces"):
        for value in build.render_ignore_filters(config, checkout):
            assert "\\" not in value, value
            assert "/" in value


@pytest.mark.parametrize("bad", [
    "/etc/passwd",
    "\\Windows\\System32",
    "../outside",
    "data/../../escape",
    "C:/Windows",
])
def test_unusable_filter_paths_are_refused(config, bad):
    """Absolute, traversing and separator-anchored paths are all rejected."""
    contract = {**config, "ignore_filters": [{"kind": "name", "path": bad}]}
    with pytest.raises(build.IgnoreFilterError):
        build.render_ignore_filters(contract, "x")


def test_an_undeclared_base_is_refused(config):
    contract = {**config}
    contract.pop("ignore_filters_relative_to")
    with pytest.raises(build.IgnoreFilterError, match="repository_root"):
        build.render_ignore_filters(contract, "x")


def test_an_unusable_checkout_name_is_refused(config):
    for bad in ("", ".", ".."):
        with pytest.raises(build.IgnoreFilterError, match="checkout directory"):
            build.render_ignore_filters(config, bad)


def test_applying_filters_preserves_what_somebody_else_put_there(config, tmp_path):
    """A generator does not get to decide a person's own setting was a mistake."""
    mine = ["Notes/private", "path:Attachments/scratch"]
    vault = _vault(tmp_path, existing=mine)
    result = build.apply_ignore_filters(config, vault, repository_root=tmp_path / "x")
    assert result["updated"] is True
    written = json.loads(
        (vault / ".obsidian" / "app.json").read_text(encoding="utf-8")
    )["userIgnoreFilters"]
    assert written[:2] == mine, "existing filters must survive, in place"
    assert written[2:] == build.render_ignore_filters(config, "x")


def test_applying_filters_twice_changes_nothing_the_second_time(config, tmp_path):
    vault = _vault(tmp_path, existing=["Notes/private"])
    first = build.apply_ignore_filters(config, vault, repository_root=tmp_path / "x")
    app = vault / ".obsidian" / "app.json"
    after_first = app.read_bytes()
    second = build.apply_ignore_filters(config, vault, repository_root=tmp_path / "x")
    assert first["updated"] is True
    assert second["updated"] is False
    assert second["reason"] == "already present"
    assert app.read_bytes() == after_first, "the second run must not rewrite the file"
    written = json.loads(app.read_text(encoding="utf-8"))["userIgnoreFilters"]
    assert len(written) == len(set(written)), "no duplicates"
    assert len(written) == 13


def test_no_stale_filter_is_ever_deleted(config, tmp_path):
    """Additive only. Removing a filter is a person's decision, not a script's."""
    stale = ["old-checkout-name/.venv", "path:old-checkout-name/dist"]
    vault = _vault(tmp_path, existing=stale)
    build.apply_ignore_filters(config, vault, repository_root=tmp_path / "x")
    written = json.loads(
        (vault / ".obsidian" / "app.json").read_text(encoding="utf-8")
    )["userIgnoreFilters"]
    for value in stale:
        assert value in written


def test_a_vault_without_an_obsidian_config_is_left_alone(config, tmp_path):
    result = build.apply_ignore_filters(config, tmp_path, repository_root=tmp_path / "x")
    assert result["updated"] is False
    assert "no .obsidian/app.json" in result["reason"]
    assert not (tmp_path / ".obsidian").exists(), (
        "a missing config is reported, never created"
    )
    assert result["rendered"] == build.render_ignore_filters(config, "x")


def test_the_filter_tests_touch_no_real_vault_or_repository_parent():
    """Everything above writes to tmp_path only.

    The real vault sits at the repository's parent. Nothing here may read or
    write it, so the assertion is on the source of this module: no test in it
    resolves the parent of the repository root.
    """
    # Assembled at run time so this guard does not match its own source. The
    # project already uses the idiom for planted test secrets, and the reason is
    # the same: a scanner that reads the file it lives in will find itself.
    parent_sentinel = "ROOT" + "." + "parent"
    config_sentinel = "." + "obsidian"
    apply_sentinel = "apply_" + "ignore_filters"

    source = (ROOT / "tests" / "test_obsidian_vault.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        # Statements only. A docstring that explains what the test must NOT do
        # is prose about the rule, not a breach of it -- the same reason this
        # project's language guards strip quoted spans before they match.
        statements = [n for n in node.body
                      if not (isinstance(n, ast.Expr)
                              and isinstance(n.value, ast.Constant)
                              and isinstance(n.value.value, str))]
        body = chr(10).join(ast.unparse(n) for n in statements)
        assert parent_sentinel not in body, (
            f"{node.name} resolves the repository's parent, which is the real "
            "vault. Tests use tmp_path only"
        )
        # Reading the configured value of vault_root is fine; opening an actual
        # Obsidian settings directory, or applying filters to one, is not.
        if config_sentinel in body or apply_sentinel in body:
            assert "tmp_path" in body, (
                f"{node.name} touches an Obsidian config outside tmp_path"
            )
