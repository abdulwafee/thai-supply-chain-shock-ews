"""Task CI-R1 tests — the canonical digest rule and the historical pins.

Three failures here would each turn a corrected record back into a broken one.

The first is **a pin quietly rewritten**. The ten historical checksums were
correct measurements of the wrong thing: a Windows working tree, where the file
was CRLF on disk while Git stored LF. The fix is a declaration of what each pin
was taken from, not a new value. So every test below reads the pin from the
document that has always recorded it and fails if the sidecar states anything
else.

The second is **a rule that accepts too much**. "Try both line endings and take
whichever matches" would make every pin in the project unable to detect a change
that alters only line endings, forever, for the sake of ten files. The rule here
names one representation for one path, requires the canonical content to agree
first, and requires the declared render to reproduce the original pin exactly.
The synthetic cases below plant each way that could go wrong and prove it fails.

The third is **a claim about history taken from the present**. The branch that
adds this module also appends to ``docs/architecture/decision_log.md``, which is
itself one of the affected paths. Every historical assertion therefore reads
``git cat-file`` against commit ``8c3c8f9c…`` -- the immutable v1.0.0 tree -- and
never the working tree, so nothing this branch does can change what the record
says. A clone too shallow to hold that commit **skips with a reason**; it does
not pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.release import byte_provenance as BP

ROOT = Path(__file__).resolve().parents[1]
SUBJECT_COMMIT = "8c3c8f9cc9dfb6fd4e53729615191f2726c25047"

TEXT = b"first\nsecond\nthird\n"
CRLF_TEXT = b"first\r\nsecond\r\nthird\r\n"
MIXED = b"first\r\nsecond\nthird\r\n"
BINARY = b"PK\x03\x04\x00\x00hello\x00world"


def _provenance() -> dict:
    return BP.load_provenance(ROOT)


def _entries() -> list:
    return _provenance()["entries"]


NO_GIT_REASON = (
    "there is no git object database here, so history cannot be read at all. "
    "This is a release tree or an archive, not a clone that failed to fetch. "
    "The historical checks did NOT run and are NOT passing; they run in any git "
    "checkout, and CI is configured with fetch-depth: 0 so they run there"
)


@pytest.fixture(scope="module")
def subject_history():
    """Require the v1.0.0 commit and tag, and fail loudly when they are absent.

    A shallow clone is a fetch setting somebody can change, so it is a
    **failure** with the fix named in the message -- never a pass, and never a
    bare skip that looks tidy while hiding a fixable gap. The one skip is a tree
    with no git database at all, which cannot have history to fetch.
    """
    if not BP.is_git_checkout(ROOT):
        pytest.skip(NO_GIT_REASON)
    return BP.require_subject_history(ROOT, SUBJECT_COMMIT, "v1.0.0")


# ---------------------------------------------------------------------------
# The bytes themselves
# ---------------------------------------------------------------------------

def test_canonicalisation_is_idempotent_and_collapses_only_crlf():
    assert BP.canonical_bytes(CRLF_TEXT) == TEXT
    assert BP.canonical_bytes(TEXT) == TEXT
    assert BP.canonical_bytes(BP.canonical_bytes(CRLF_TEXT)) == TEXT
    # A lone CR is not a line ending here and is left exactly as it is.
    assert BP.canonical_bytes(b"a\rb") == b"a\rb"


def test_the_two_digests_are_different_facts():
    """The whole defect in one assertion: same text, different bytes."""
    assert BP.digest(CRLF_TEXT) != BP.digest(TEXT)
    assert BP.canonical_digest(CRLF_TEXT) == BP.canonical_digest(TEXT)
    assert BP.canonical_digest(CRLF_TEXT) == BP.digest(TEXT)


def test_rendering_round_trips_for_the_declared_representation():
    canonical = BP.canonical_bytes(CRLF_TEXT)
    assert BP.render(canonical, BP.CANONICAL_LF) == TEXT
    assert BP.render(canonical, BP.WINDOWS_CRLF_WORKTREE) == CRLF_TEXT
    assert BP.digest(BP.render(canonical, BP.WINDOWS_CRLF_WORKTREE)) == BP.digest(
        CRLF_TEXT
    )


def test_the_unreproducible_representation_has_no_renderer():
    """Inventing one would repeat the original mistake in a new place."""
    with pytest.raises(BP.LineEndingError, match="fabrication"):
        BP.render(TEXT, BP.UNREPRODUCIBLE)
    with pytest.raises(BP.LineEndingError, match="cannot be rendered"):
        BP.render(TEXT, "some_other_platform")


def test_mixed_line_endings_are_reported_rather_than_guessed_at():
    assert BP.is_pure(TEXT) is True
    assert BP.is_pure(CRLF_TEXT) is True
    assert BP.is_pure(MIXED) is False
    assert BP.bare_lf_count(MIXED) == 1
    assert BP.bare_lf_count(CRLF_TEXT) == 0
    assert BP.bare_lf_count(TEXT) == 3


def test_binary_content_is_hashed_raw_and_text_canonically():
    assert BP.looks_binary(BINARY) is True
    assert BP.looks_binary(CRLF_TEXT) is False
    assert BP.release_digest(BINARY) == (BP.digest(BINARY), BP.RAW_BYTES)
    assert BP.release_digest(CRLF_TEXT) == (BP.digest(TEXT), BP.CANONICAL_LF)
    # Canonicalising a binary would corrupt it, so the raw bytes survive.
    assert BP.release_digest(BINARY)[0] == hashlib.sha256(BINARY).hexdigest()


# ---------------------------------------------------------------------------
# The sidecar is a copy, never a second source
# ---------------------------------------------------------------------------

def test_the_sidecar_declares_the_canonical_rule_and_forbids_new_legacy_pins():
    provenance = _provenance()
    assert provenance["canonical_representation"] == BP.CANONICAL_LF
    assert provenance["new_pins_may_declare_a_legacy_representation"] is False
    assert provenance["subject_commit"] == SUBJECT_COMMIT
    assert provenance["reads_working_tree_for_historical_paths"] is False
    assert provenance["network_access_during_verification"] is False


def test_every_declared_pin_still_matches_the_document_that_records_it():
    """The sidecar copies each pin from its source. A copy that drifts is a bug.

    Read back from the four documents that have always held these values, so a
    sidecar edited to make a test pass fails instead.
    """
    config = yaml.safe_load(
        (ROOT / "configs" / "e2r1_source_release.yaml").read_text(encoding="utf-8")
    )
    e2_pins = config["supersession"]["pinned_artifact_checksums"]
    governance = json.loads(
        (ROOT / "docs" / "c11r1_governance_decision.json").read_text(encoding="utf-8")
    )
    c11 = governance["preserved_c11_record"]["artifacts"]
    oie_source = (
        ROOT / "tests" / "test_validate_oie_overlap_v2.py"
    ).read_text(encoding="utf-8")
    e1 = json.loads(
        (ROOT / "docs" / "e1_reproducibility_manifest.json").read_text(
            encoding="utf-8")
    )
    e1_pins = {record["path"]: record["checksum"] for record in e1["artifacts"]
               if record["checksum_kind"] == "byte_sha256"}

    recorded = {
        "docs/e2_release_candidate_manifest.json":
            e2_pins["docs/e2_release_candidate_manifest.json"],
        "docs/e2_release_readiness.json": e2_pins["docs/e2_release_readiness.json"],
        "docs/e2_release_readiness.md": e2_pins["docs/e2_release_readiness.md"],
        "docs/c11_architecture_decision.json": c11["decision_json"]["byte_sha256"],
        "docs/c11_architecture_decision.md": c11["decision_markdown"]["byte_sha256"],
        "docs/c11_architecture_decision_protocol.md":
            c11["protocol_markdown"]["byte_sha256"],
        "docs/oie_overlap_validation_output.json": re.search(
            r'"docs/oie_overlap_validation_output\.json":\s*\n\s*"([0-9a-f]{64})"',
            oie_source,
        ).group(1),
        "docs/d5_frozen_protocol.json": e1_pins["docs/d5_frozen_protocol.json"],
        "docs/d3_locked_test_manifest.json":
            e1_pins["docs/d3_locked_test_manifest.json"],
        "docs/d3r1_benchmark_interpretation.json":
            e1_pins["docs/d3r1_benchmark_interpretation.json"],
    }

    entries = {entry["path"]: entry for entry in _entries()}
    assert set(entries) == set(recorded), (
        "the sidecar covers exactly the pins that need it, no more"
    )
    for path, pin in recorded.items():
        assert entries[path]["legacy_sha256"] == pin, path


def test_every_entry_names_where_its_pin_is_actually_stated():
    for entry in _entries():
        source = ROOT / entry["pinned_in_path"]
        assert source.is_file(), entry["pinned_in_path"]
        assert entry["legacy_sha256"] in source.read_text(encoding="utf-8"), (
            f"{entry['path']} says its pin lives in {entry['pinned_in_path']}, "
            "but that file does not contain it"
        )
        assert entry["legacy_representation"] in (
            BP.WINDOWS_CRLF_WORKTREE, BP.UNREPRODUCIBLE
        )
        assert entry["canonical_git_blob_content_sha256"] != entry["legacy_sha256"]
        assert re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_object_id"])


def test_the_object_id_is_not_confused_with_a_content_digest():
    """Git's id is sha1 over a header plus content. It is a different thing."""
    for entry in _entries():
        assert len(entry["git_blob_object_id"]) == 40
        assert len(entry["canonical_git_blob_content_sha256"]) == 64
        assert entry["git_blob_object_id"] not in (
            entry["legacy_sha256"], entry["canonical_git_blob_content_sha256"]
        )


# ---------------------------------------------------------------------------
# Against the immutable v1.0.0 tree
# ---------------------------------------------------------------------------

def test_the_subject_commit_is_the_published_tag(subject_history):
    assert subject_history["commit"] == SUBJECT_COMMIT
    assert subject_history["dereferences_to"] == SUBJECT_COMMIT
    assert BP.require_commit_present(ROOT, SUBJECT_COMMIT) == SUBJECT_COMMIT
    assert BP.resolve(ROOT, "v1.0.0") == SUBJECT_COMMIT, (
        "the errata and the sidecar describe the published release, so the tag "
        "must still point where they say it does"
    )
    # An annotated tag is its own object, distinct from the commit it names.
    assert subject_history["tag_object"] != SUBJECT_COMMIT


def test_a_shallow_clone_fails_loudly_rather_than_skipping(subject_history):
    """The behaviour the CI configuration depends on, proved here.

    A missing subject commit or tag must raise with the fix named, so it can
    never become a pass or a bare skip.
    """
    with pytest.raises(BP.LineEndingError, match="fetch-depth: 0"):
        BP.require_subject_history(ROOT, "0" * 40, "v1.0.0")
    with pytest.raises(BP.LineEndingError, match="fetch-depth: 0"):
        BP.require_subject_history(ROOT, SUBJECT_COMMIT, "v0.0.0-absent")
    # And a tag that names a different commit is refused rather than followed.
    # Any commit reachable here other than the subject one demonstrates it; the
    # feature branch's tip is real, present, and is not what v1.0.0 points at.
    other = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "rev-list", "--all", "--max-count=50"], cwd=str(ROOT),
        capture_output=True, check=False,
    ).stdout.decode().split()
    different = next((c for c in other if c != SUBJECT_COMMIT), None)
    if different is None:
        pytest.skip(
            "this clone holds only the subject commit, so a tag pointing "
            "elsewhere cannot be constructed without writing to the repository. "
            "Not run here; the missing-commit and missing-tag cases above did run"
        )
    with pytest.raises(BP.LineEndingError, match="dereferences to"):
        BP.require_subject_history(ROOT, different, "v1.0.0")


def test_every_historical_pin_verifies_against_the_v1_0_0_blob(subject_history):
    for entry in _entries():
        path = entry["path"]
        result = BP.verify_legacy_pin(
            ROOT, path, entry["legacy_sha256"], entry, SUBJECT_COMMIT
        )
        assert result["canonical_verified"] is True, path
        assert result["representation"] == entry["legacy_representation"], path
        content = BP.blob_content(ROOT, SUBJECT_COMMIT, path)
        assert BP.canonical_digest(content) == entry[
            "canonical_git_blob_content_sha256"], path
        assert BP.blob_object_id(ROOT, SUBJECT_COMMIT, path) == entry[
            "git_blob_object_id"], path
        # The committed blob is LF. The CRLF was only ever on someone's disk.
        assert b"\r" not in content, path


def test_a_missing_object_is_reported_and_never_fetched(subject_history):
    absent = "0" * 40
    with pytest.raises(BP.LineEndingError, match="does not resolve to a commit"):
        BP.resolve(ROOT, absent)
    with pytest.raises(BP.LineEndingError, match="not present in the tree"):
        BP.blob_content(ROOT, SUBJECT_COMMIT, "docs/no_such_document.json")


def test_an_abbreviated_subject_commit_is_refused(subject_history):
    """A pin anchored to a prefix is anchored to nothing durable."""
    with pytest.raises(BP.LineEndingError, match="full immutable id"):
        BP.require_commit_present(ROOT, SUBJECT_COMMIT[:12])


# ---------------------------------------------------------------------------
# Synthetic failures: each plants the defect and proves the guard fires
# ---------------------------------------------------------------------------

def test_synthetic_a_content_edit_is_not_excused_by_a_line_ending_claim():
    entry = {"path": "docs/x.md", "legacy_sha256": BP.digest(CRLF_TEXT),
             "legacy_representation": BP.WINDOWS_CRLF_WORKTREE,
             "canonical_git_blob_content_sha256": BP.digest(TEXT)}
    edited = b"first\r\nSECOND\r\nthird\r\n"
    assert BP.match_declared_representation(
        BP.canonical_bytes(edited), entry["legacy_sha256"], entry
    ) is None


def test_synthetic_an_undeclared_path_gets_no_tolerance():
    """The rule is per-path. It never becomes a general amnesty."""
    assert BP.match_declared_representation(TEXT, BP.digest(CRLF_TEXT), None) is None


def test_synthetic_a_sidecar_that_restates_the_pin_is_refused():
    entry = {"path": "docs/x.md", "legacy_sha256": BP.digest(b"something else"),
             "legacy_representation": BP.WINDOWS_CRLF_WORKTREE,
             "canonical_git_blob_content_sha256": BP.digest(TEXT)}
    assert BP.match_declared_representation(TEXT, BP.digest(CRLF_TEXT), entry) is None


def test_synthetic_a_wrong_canonical_digest_is_refused():
    entry = {"path": "docs/x.md", "legacy_sha256": BP.digest(CRLF_TEXT),
             "legacy_representation": BP.WINDOWS_CRLF_WORKTREE,
             "canonical_git_blob_content_sha256": BP.digest(b"not this")}
    assert BP.match_declared_representation(TEXT, BP.digest(CRLF_TEXT), entry) is None


def test_synthetic_a_mixed_worktree_cannot_claim_a_uniform_representation():
    entry = {"path": "docs/x.md", "legacy_sha256": BP.digest(MIXED),
             "legacy_representation": BP.WINDOWS_CRLF_WORKTREE,
             "canonical_git_blob_content_sha256": BP.canonical_digest(MIXED)}
    assert BP.match_declared_representation(MIXED, BP.digest(MIXED), entry) is None


def test_synthetic_an_unreproducible_entry_must_say_so_in_its_own_fields():
    entry = {"path": "docs/x.md", "legacy_sha256": "deadbeef",
             "legacy_representation": BP.UNREPRODUCIBLE,
             "canonical_git_blob_content_sha256": BP.canonical_digest(MIXED)}
    # Without the explicit refusal it is not accepted at all.
    assert BP.match_declared_representation(MIXED, "deadbeef", entry) is None
    entry["independently_reproducible"] = False
    assert BP.match_declared_representation(
        MIXED, "deadbeef", entry
    ) == BP.UNREPRODUCIBLE


def test_synthetic_relabelling_an_unreproducible_row_as_crlf_is_caught(
        subject_history):
    """A row that really is reproducible may not hide as unreproducible.

    Verification actively asserts the CRLF render does *not* reproduce the pin,
    so ``unreproducible`` cannot become a place to park an awkward path.
    """
    entry = dict(_entries()[0])
    entry["legacy_representation"] = BP.UNREPRODUCIBLE
    entry["independently_reproducible"] = False
    with pytest.raises(BP.LineEndingError, match="declaration is wrong"):
        BP.verify_legacy_pin(
            ROOT, entry["path"], entry["legacy_sha256"], entry, SUBJECT_COMMIT
        )


def test_synthetic_a_tree_without_the_sidecar_grants_nothing():
    assert BP.provenance_entries(ROOT / "nonexistent_subtree") == {}


# ---------------------------------------------------------------------------
# The generation rule the sidecar declares
# ---------------------------------------------------------------------------

def test_the_declared_raw_byte_sites_all_exist_and_hash_binaries():
    provenance = _provenance()
    for allowed in provenance["raw_byte_hashing_allowed"]:
        assert (ROOT / allowed["path"]).is_file(), allowed["path"]
        assert allowed["reason"]
        assert allowed["hashes"].startswith(("downloaded_", "generated_"))


def test_the_frozen_historical_runners_all_exist_and_are_named():
    provenance = _provenance()
    for frozen in provenance["frozen_historical_hashing"]:
        assert (ROOT / frozen["path"]).is_file(), frozen["path"]
        assert frozen["reason"]
    paths = {frozen["path"] for frozen in provenance["frozen_historical_hashing"]}
    assert "scripts/run_e2_release_preparation.py" in paths, (
        "the superseded E2 runner produced three of these pins and must stay "
        "listed as frozen"
    )
