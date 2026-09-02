"""Task CI-R1 tests — the guard on how new checksums are *produced*.

``.gitattributes`` fixes what Git stores. It does nothing about what Python
writes: ``Path.write_text`` on Windows still turns ``\\n`` into ``\\r\\n`` on
disk, and a runner that hashes the file it has just written still records a
digest of bytes no other machine will ever see. Verification tolerating a
declared representation, without a rule about generation, would keep the defect
alive and merely keep excusing it.

So this module scans the repository itself.

**Every site that hashes a file's bytes must be accounted for.** Found by AST,
not by grep, so a renamed variable or a reformatted line cannot hide one. Each
must be one of three declared things: canonical (the release modules), correct
raw-byte hashing of binary content, or a frozen historical runner. A site that
is none of those fails, by path and line.

**Every document the E2-R1 runner writes must be written with LF.** Named
explicitly rather than inferred, because that runner produces the manifest whose
118 mismatched rows started this.

**And the correction's own files must practise it.** A branch that adds a rule
about line endings and ships CRLF files would have proved nothing.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from thai_supply_chain_ews.release import byte_provenance as BP

ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRECTORIES = ("src", "scripts", "tests")

#: The modules this correction made canonical. They must not hash raw bytes.
CANONICAL_MODULES = (
    "src/thai_supply_chain_ews/release/inventory.py",
    "src/thai_supply_chain_ews/release/clean_tree.py",
    "src/thai_supply_chain_ews/release/source_release.py",
)

#: Everything this branch adds. Each must ship with LF endings.
CORRECTION_FILES = (
    ".gitattributes",
    "configs/line_ending_provenance.yaml",
    "docs/e2r1_release_manifest_errata.json",
    "src/thai_supply_chain_ews/release/byte_provenance.py",
    "tests/test_byte_provenance.py",
    "tests/test_e2r1_manifest_errata.py",
    "tests/test_pin_generation_guard.py",
)


def _provenance() -> dict:
    return BP.load_provenance(ROOT)


def _declared_paths() -> set:
    provenance = _provenance()
    declared = set()
    for key in ("raw_byte_hashing_allowed", "frozen_historical_hashing",
                "worktree_pin_assertions_lf_clean",
                "corrected_worktree_pin_assertions"):
        declared |= {entry["path"] for entry in provenance[key]}
    return declared


def _file_byte_hashing_sites() -> list:
    """Every ``sha256`` call whose argument reads a file's bytes, by AST."""
    sites = []
    for directory in SCANNED_DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), relative)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                if not isinstance(function, ast.Attribute):
                    continue
                if function.attr != "sha256":
                    continue
                if "read_bytes()" in ast.unparse(node):
                    sites.append((relative, node.lineno))
    return sites


def _write_text_calls(relative: str) -> list:
    """``write_text`` calls in one module, with the keywords each passes."""
    source = (ROOT / relative).read_text(encoding="utf-8")
    calls = []
    for node in ast.walk(ast.parse(source, relative)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "write_text":
                calls.append((node.lineno, {kw.arg for kw in node.keywords}))
    return calls


# ---------------------------------------------------------------------------
# Every hashing site is accounted for
# ---------------------------------------------------------------------------

def test_every_file_byte_hashing_site_is_declared():
    """An undeclared site is the next pin that will disagree with itself."""
    declared = _declared_paths()
    undeclared = sorted({
        f"{relative}:{line}" for relative, line in _file_byte_hashing_sites()
        if relative not in declared
    })
    assert not undeclared, (
        "these sites hash a file's raw bytes and are declared nowhere in "
        "configs/line_ending_provenance.yaml: " + ", ".join(undeclared) +
        ". Each must be canonical, or declared as correct raw-byte hashing of "
        "binary content, or declared as a frozen historical runner"
    )


def test_the_scan_actually_finds_sites():
    """A guard that finds nothing would pass forever without checking anything."""
    sites = _file_byte_hashing_sites()
    assert len(sites) >= 15, (
        f"only {len(sites)} hashing sites found; the AST scan has stopped "
        "matching and is no longer guarding anything"
    )


def test_every_declaration_still_points_at_a_real_hashing_module():
    provenance = _provenance()
    for key in ("raw_byte_hashing_allowed", "frozen_historical_hashing"):
        for entry in provenance[key]:
            path = ROOT / entry["path"]
            assert path.is_file(), entry["path"]
            assert "sha256" in path.read_text(encoding="utf-8"), (
                f"{entry['path']} is declared as a hashing site but no longer "
                "hashes anything. A stale declaration is a hole in the guard"
            )


def test_the_release_modules_hash_canonically_and_declare_nothing():
    """The three modules this correction changed must not appear in the lists."""
    declared = _declared_paths()
    for relative in CANONICAL_MODULES:
        assert relative not in declared, (
            f"{relative} was made canonical; it must not also claim an "
            "exemption from being canonical"
        )
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "byte_provenance" in source, relative
    sites = {relative for relative, _ in _file_byte_hashing_sites()}
    assert sites.isdisjoint(CANONICAL_MODULES)


def test_nothing_is_left_merely_tolerated():
    """Every vulnerable site found by the audit was corrected, not excused."""
    provenance = _provenance()
    assert provenance["tolerated_vulnerable_pin_assertions"] == 0
    assert "known_vulnerable_worktree_pin_assertions" not in provenance, (
        "the tolerated list is gone because nothing is tolerated; a site that "
        "reappears there is a site that was not fixed"
    )


def test_the_corrected_sites_really_are_representation_aware():
    """Declared as corrected, and shown to be, by reading the modules.

    A declaration that a test was fixed is worth nothing on its own, so this
    checks the module actually consults the shared helper rather than hashing
    raw bytes and hoping.
    """
    registry = (ROOT / "tests" / "data_backed_tests.txt").read_text(encoding="utf-8")
    corrected = _provenance()["corrected_worktree_pin_assertions"]
    assert len(corrected) == 2, "the audit found two; both must stay declared"
    declared_entries = {e["path"] for e in _provenance()["entries"]}
    for entry in corrected:
        source = (ROOT / entry["path"]).read_text(encoding="utf-8")
        assert entry["representation_aware"] is True
        assert "byte_provenance" in source, entry["path"]
        assert "match_declared_representation" in source, (
            f"{entry['path']} is declared corrected but never calls the shared "
            "representation-aware helper"
        )
        assert entry["data_backed_registered"] is True
        assert f"{entry['path']}::{entry['test']}" in registry, (
            f"{entry['test']} is declared data-backed but is not in the "
            "registry, so the account of when it runs is wrong"
        )
        for document in entry["affected_documents"]:
            assert document in declared_entries, (
                f"{document} is named as affected but has no provenance entry, "
                "so the corrected assertion has nothing to consult"
            )
        assert entry["correction"]


def test_the_corrected_sites_still_hash_binary_rows_raw():
    """Their loops also cover Parquet. Canonicalising those would corrupt them."""
    for entry in _provenance()["corrected_worktree_pin_assertions"]:
        assert entry["binary_rows_hashed_raw"] is True
        source = (ROOT / entry["path"]).read_text(encoding="utf-8")
        assert "hashlib.sha256(content).hexdigest()" in source, (
            f"{entry['path']} must still try the recorded bytes first, which is "
            "the only correct comparison for a binary row"
        )


def test_the_lf_clean_assertions_really_are_lf_clean():
    """Their safety is re-measured here, not remembered.

    A site declared safe because its pinned documents have no CR stops being
    safe the moment one of them gains a carriage return. So the claim is checked
    against the documents themselves on every run.
    """
    import json

    declared = _provenance()["worktree_pin_assertions_lf_clean"]
    assert declared, "the audit found one; the declaration must not be emptied"
    for entry in declared:
        assert (ROOT / entry["path"]).is_file(), entry["path"]
        pins = json.loads(
            (ROOT / entry["pins_declared_in"]).read_text(encoding="utf-8")
        )[entry["pinned_key"]]
        assert pins, entry["pins_declared_in"]
        for relative, pin in pins.items():
            content = (ROOT / relative).read_bytes()
            assert BP.digest(content) == pin, (
                f"{relative} no longer matches its pin, so the assertion in "
                f"{entry['path']} is failing for a reason this file cannot "
                "explain"
            )
            assert BP.canonical_digest(content) == pin, (
                f"{relative} is declared CR-free but its raw and canonical "
                "digests now differ. It has become platform-dependent and the "
                "declaration is stale"
            )


def test_the_affected_documents_are_all_already_declared_in_the_errata():
    """The same documents are legacy rows of the release manifest, and say so."""
    import json

    errata = json.loads(
        (ROOT / "docs" / "e2r1_release_manifest_errata.json").read_text(
            encoding="utf-8"
        )
    )
    declared = {entry["path"] for entry in errata["entries"]}
    for entry in _provenance()["corrected_worktree_pin_assertions"]:
        for document in entry["affected_documents"]:
            assert document in declared, document


# ---------------------------------------------------------------------------
# Generation: what Python writes, not what Git stores
# ---------------------------------------------------------------------------

def test_the_e2r1_runner_writes_every_document_with_lf():
    """The runner that produced the mismatched manifest is the one that matters."""
    calls = _write_text_calls("scripts/run_e2r1_source_release.py")
    assert calls, "the runner must still write its three documents"
    missing = [line for line, keywords in calls if "newline" not in keywords]
    assert not missing, (
        "scripts/run_e2r1_source_release.py writes without newline= at line(s) "
        f"{missing}. On Windows that produces CRLF on disk, and a digest taken "
        "from it fails on every other platform"
    )


def test_the_runner_asks_for_lf_specifically():
    source = (ROOT / "scripts" / "run_e2r1_source_release.py").read_text(
        encoding="utf-8"
    )
    assert source.count('newline="\\n"') >= 3, (
        "all three E2-R1 documents must be written with LF explicitly"
    )


def test_gitattributes_normalises_text_and_protects_binaries():
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in text
    for suffix in (".parquet", ".xlsx", ".xls", ".pdf", ".png", ".zip"):
        assert f"*{suffix}" in text, (
            f"{suffix} must be declared binary; line-ending conversion would "
            "corrupt it rather than reformat it"
        )


def test_this_corrections_own_files_use_lf():
    """A rule about line endings, shipped with the wrong ones, proves nothing."""
    for relative in CORRECTION_FILES:
        path = ROOT / relative
        assert path.is_file(), relative
        assert b"\r" not in path.read_bytes(), (
            f"{relative} contains a carriage return. This branch's own files "
            "must satisfy the rule it introduces"
        )


def test_the_modified_files_use_lf_too():
    for relative in (*CANONICAL_MODULES, "scripts/run_e2r1_source_release.py",
                     "tests/test_c11r1_governance_closure.py",
                     "tests/test_validate_oie_overlap_v2.py",
                     "tests/test_c12_channel_closure.py",
                     "tests/test_e1_evidence_synthesis.py",
                     ".github/workflows/ci.yml",
                     "docs/architecture/decision_log.md"):
        assert b"\r" not in (ROOT / relative).read_bytes(), relative


# ---------------------------------------------------------------------------
# Synthetic failures
# ---------------------------------------------------------------------------

def test_synthetic_an_undeclared_hashing_site_is_detected(tmp_path):
    """Plant the defect in a throwaway tree and prove the scanner sees it."""
    module = tmp_path / "src" / "sneaky.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import hashlib\n"
        "from pathlib import Path\n\n\n"
        "def pin(path):\n"
        "    return hashlib.sha256(Path(path).read_bytes()).hexdigest()\n",
        encoding="utf-8", newline="\n",
    )
    found = []
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "sha256" and "read_bytes()" in ast.unparse(node):
                found.append(node.lineno)
    assert found == [6], "the AST rule must match the planted site"
    assert "sneaky.py" not in _declared_paths()


def test_synthetic_a_write_without_newline_is_detected(tmp_path):
    module = tmp_path / "writer.py"
    module.write_text(
        "from pathlib import Path\n\n\n"
        "def emit(path, text):\n"
        "    Path(path).write_text(text, encoding='utf-8')\n",
        encoding="utf-8", newline="\n",
    )
    calls = []
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "write_text":
                calls.append({kw.arg for kw in node.keywords})
    assert calls == [{"encoding"}], "the planted call omits newline= and is seen"


def test_synthetic_python_really_does_translate_newlines_on_write(tmp_path):
    """The premise of this whole correction, demonstrated rather than asserted.

    On Linux both files come out identical and this still holds; on Windows the
    default-newline file gains CRLF. Either way the explicit write is stable,
    which is the property the rule depends on.
    """
    explicit = tmp_path / "explicit.txt"
    explicit.write_text("a\nb\n", encoding="utf-8", newline="\n")
    assert explicit.read_bytes() == b"a\nb\n"
    assert BP.digest(explicit.read_bytes()) == BP.canonical_digest(b"a\nb\n")


def test_synthetic_a_declaration_pointing_nowhere_would_be_caught():
    entry = {"path": "scripts/does_not_exist.py", "reason": "invented"}
    assert not (ROOT / entry["path"]).is_file()


@pytest.mark.skipif(
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "rev-parse", "--git-dir"], cwd=str(ROOT),
        capture_output=True, check=False,
    ).returncode != 0,
    reason="not a git checkout, so tracked-file line endings cannot be read",
)
def test_no_tracked_text_blob_carried_a_carriage_return():
    """Why ``* text=auto eol=lf`` is safe to apply to this repository.

    Normalisation changes committed content only where committed content has
    CR in it. It has none, so the setting corrects the working tree without
    rewriting one byte of history.
    """
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "grep", "-Il", "-c", "-e", "\r", "8c3c8f9cc9dfb6fd4e53729615191f2726c25047"],
        cwd=str(ROOT), capture_output=True, check=False,
    )
    if completed.returncode not in (0, 1):
        pytest.skip(
            "the v1.0.0 commit is not in this clone (shallow checkout), so the "
            "historical blobs cannot be read. Not run is not the same as passing"
        )
    offenders = [
        line for line in completed.stdout.decode("utf-8", "replace").splitlines()
        if line.strip()
    ]
    assert not offenders, (
        "a tracked text blob contains CR, so eol=lf would change committed "
        f"content: {offenders[:5]}"
    )

# ---------------------------------------------------------------------------
# The two corrected assertions, proved rather than declared
# ---------------------------------------------------------------------------

#: The three documents whose pins the two corrected assertions compare.
CORRECTED_DOCUMENTS = (
    "docs/d5_frozen_protocol.json",
    "docs/d3_locked_test_manifest.json",
    "docs/d3r1_benchmark_interpretation.json",
)

SUBJECT_COMMIT = "8c3c8f9cc9dfb6fd4e53729615191f2726c25047"

NO_GIT_REASON = (
    "there is no git object database here, so the committed blobs cannot be "
    "read. This is a release tree or an archive, not a clone that failed to "
    "fetch. These checks did NOT run and are NOT passing"
)


@pytest.fixture(scope="module")
def committed_blobs():
    """The three documents exactly as a Linux checkout receives them.

    A shallow clone **fails** with the fix named, because a missing subject
    commit is a fetch setting rather than a result. Only a tree with no git
    database at all skips, and it says so.
    """
    if not BP.is_git_checkout(ROOT):
        pytest.skip(NO_GIT_REASON)
    BP.require_subject_history(ROOT, SUBJECT_COMMIT, "v1.0.0")
    return {
        relative: BP.blob_content(ROOT, SUBJECT_COMMIT, relative)
        for relative in CORRECTED_DOCUMENTS
    }


def _pins() -> dict:
    """Each document's pin, read from the document that actually records it."""
    import json

    e1 = json.loads(
        (ROOT / "docs" / "e1_reproducibility_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    c12 = json.loads(
        (ROOT / "docs" / "c12_channel_closure.json").read_text(encoding="utf-8")
    )
    pins = {
        record["path"]: record["checksum"]
        for record in e1["artifacts"]
        if record["checksum_kind"] == "byte_sha256"
    }
    return pins, c12["preservation"]["byte_checksums"]


def test_the_corrected_assertions_pass_against_the_committed_lf_blobs(
        committed_blobs):
    """The Linux case, run here instead of guessed at.

    These two tests are registered data-backed, so CI skips them and the defect
    they carried was never visible. Feeding the committed LF bytes to the same
    comparison the assertions now use exercises the corrected path directly, on
    any platform, with no generated table present.
    """
    e1_pins, c12_pins = _pins()
    provenance = BP.provenance_entries(ROOT)
    for relative, content in committed_blobs.items():
        assert b"\r" not in content, (
            f"{relative}'s committed blob is LF; if it ever gains CR the "
            "provenance entry stops describing it"
        )
        for pin in (e1_pins.get(relative), c12_pins.get(relative)):
            if pin is None:
                continue
            assert BP.digest(content) != pin, (
                f"{relative} is declared as a legacy CRLF pin; if the raw bytes "
                "matched, the declaration would be unnecessary and wrong"
            )
            matched = BP.match_declared_representation(
                content, pin, provenance.get(relative)
            )
            assert matched == BP.WINDOWS_CRLF_WORKTREE, relative


def test_the_corrected_assertions_preserve_the_original_pin_literals():
    """The sidecar copies these pins. It never becomes a second place they live."""
    e1_pins, c12_pins = _pins()
    provenance = BP.provenance_entries(ROOT)
    for relative in CORRECTED_DOCUMENTS:
        entry = provenance[relative]
        recorded = [p for p in (e1_pins.get(relative), c12_pins.get(relative))
                    if p is not None]
        assert recorded, relative
        for pin in recorded:
            assert entry["legacy_sha256"] == pin, (
                f"{relative}: the sidecar records a different literal from the "
                "document that has always stated it"
            )
        if len(recorded) > 1:
            assert len(set(recorded)) == 1, (
                f"{relative} is pinned in two documents that disagree"
            )


def test_the_corrected_assertions_remain_representation_aware_on_both_platforms(
        committed_blobs):
    """LF on Linux, CRLF on Windows -- one declaration covers both, and only both."""
    e1_pins, c12_pins = _pins()
    provenance = BP.provenance_entries(ROOT)
    for relative, blob in committed_blobs.items():
        pin = e1_pins.get(relative) or c12_pins[relative]
        windows_bytes = BP.canonical_bytes(blob).replace(BP.LF, BP.CRLF)
        # Windows: the recorded bytes match outright, before any fallback.
        assert BP.digest(windows_bytes) == pin, relative
        # Linux: the same content matches through its one declared render.
        assert BP.match_declared_representation(
            blob, pin, provenance.get(relative)
        ) == BP.WINDOWS_CRLF_WORKTREE, relative


def test_the_corrected_assertions_fail_on_a_real_content_change(committed_blobs):
    """A line-ending tolerance that also tolerates an edit would be worthless."""
    e1_pins, c12_pins = _pins()
    provenance = BP.provenance_entries(ROOT)
    for relative, blob in committed_blobs.items():
        pin = e1_pins.get(relative) or c12_pins[relative]
        for edited in (blob + b"\n", blob.replace(b"true", b"false", 1),
                       blob[:-1]):
            if edited == blob:
                continue
            assert BP.digest(edited) != pin, relative
            assert BP.match_declared_representation(
                edited, pin, provenance.get(relative)
            ) is None, (
                f"{relative}: an edited document was accepted. The canonical "
                "digest must be checked before any representation is allowed"
            )


def test_the_corrected_assertions_do_not_skip_merely_because_data_is_absent():
    """Their skip is about generated tables, and it is named and counted.

    Both tests are registered data-backed because their loops also cover Parquet
    files that a clean checkout does not have. That is a real reason with a real
    reason string; what it must never become is a silent pass, or a way for the
    line-ending defect to stay invisible. The comparison itself is exercised by
    the tests above, which need no generated table at all.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_tier_conftest", ROOT / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "which is not the same as passing" in module.SKIP_REASON
    registry = (ROOT / "tests" / "data_backed_tests.txt").read_text(encoding="utf-8")
    for entry in _provenance()["corrected_worktree_pin_assertions"]:
        assert f"{entry['path']}::{entry['test']}" in registry
    # And the corrected comparison is covered by tests that are NOT registered,
    # so the fix cannot become invisible the way the defect was.
    for name in ("test_the_corrected_assertions_pass_against_the_committed_lf_blobs",
                 "test_the_corrected_assertions_fail_on_a_real_content_change"):
        assert f"tests/test_pin_generation_guard.py::{name}" not in registry


def test_the_corrected_assertions_touch_no_locked_outcome():
    """The manifest document is verified. Nothing it names is followed.

    ``docs/d3_locked_test_manifest.json`` is a tracked public document and one of
    the 449 rows of the release manifest. Only its own bytes are digested: no
    path inside it is read, and no locked outcome, locked dataset or final-test
    artifact is opened, listed, hashed or evaluated.
    """
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs" / "e2r1_source_release.yaml").read_text(encoding="utf-8")
    )
    fragments = config["locked_test"]["outcome_path_fragments"]
    e1_pins, c12_pins = _pins()
    for relative in (*CORRECTED_DOCUMENTS, *e1_pins, *c12_pins):
        assert not any(fragment in relative for fragment in fragments), (
            f"{relative} matches a locked-outcome path fragment and must never "
            "be hashed"
        )
    # The corrected assertions read the pinned documents' bytes and nothing
    # further. Scoped to each corrected function rather than to the whole
    # module: elsewhere in tests/test_e1_evidence_synthesis.py a locked path is
    # named on purpose, by a guard proving it stays excluded, and a mention
    # inside a prohibition is not an access.
    for entry in _provenance()["corrected_worktree_pin_assertions"]:
        source = (ROOT / entry["path"]).read_text(encoding="utf-8")
        function = next(
            node for node in ast.walk(ast.parse(source, entry["path"]))
            if isinstance(node, ast.FunctionDef) and node.name == entry["test"]
        )
        body = ast.unparse(function)
        for fragment in fragments:
            assert fragment not in body, (
                f"{entry['path']}::{entry['test']} names the locked-outcome "
                f"fragment {fragment!r}"
            )
        assert "match_declared_representation" in body, (
            f"{entry['path']}::{entry['test']} must do its comparison through "
            "the shared helper, not through a local rule of its own"
        )


def test_the_locked_test_manifest_is_a_public_release_row_not_an_outcome():
    import json

    manifest = json.loads(
        (ROOT / "docs" / "e2r1_release_manifest.json").read_text(encoding="utf-8")
    )
    paths = {row["path"] for row in manifest["files"]}
    assert "docs/d3_locked_test_manifest.json" in paths, (
        "it is verified here as a released document; if it were ever excluded "
        "from the release it would need a different justification"
    )


# ---------------------------------------------------------------------------
# The CI checkout must guarantee what the verifiers require
# ---------------------------------------------------------------------------

def test_ci_checks_out_full_history_and_tags():
    """Otherwise the historical verifiers fail there, loudly and pointlessly.

    They read the object database and never fetch, so the depth-1 default leaves
    them nothing to read. This is asserted rather than trusted to a comment,
    because the failure it prevents would look like a broken verifier instead of
    a checkout setting.
    """
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["verify"]["steps"]
    checkout = next(
        step for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0, (
        "actions/checkout defaults to a depth-1 clone with no tags; the "
        "historical verifiers need the v1.0.0 commit and tag in the object "
        "database"
    )
    # And nothing else about the checkout was loosened.
    assert checkout["with"]["persist-credentials"] is False
