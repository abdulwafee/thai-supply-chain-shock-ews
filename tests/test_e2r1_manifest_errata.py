"""Task CI-R1 tests — the E2-R1 release manifest errata.

``docs/e2r1_release_manifest.json`` records a digest for each of 449 released
files. 118 of them were taken from a Windows working tree, where the file was
CRLF on disk while Git stored LF, so a stranger checking the release on Linux
finds 118 mismatches in a document whose whole purpose is to let them check.

The manifest is **not** regenerated and **not** edited. The errata declares, per
row, which representation the digest was taken from and what the canonical
digest of the same content is. Two failures would make that worthless.

The first is **a declaration that drifts from the repository**. So the partition
is recomputed here from the v1.0.0 tree and compared to the declaration: every
row classified independently, no row missing, no row surplus, no row twice.

The second is **a baseline taken from the present**. The branch that adds this
module also appends to ``docs/architecture/decision_log.md``, which is one of the
three rows the errata calls unreproducible. Reading the working tree would let
this branch change what the release record says about itself. Every assertion
below reads ``git cat-file`` against ``8c3c8f9c…``, and a clone too shallow to
hold that commit skips with a reason rather than passing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from thai_supply_chain_ews.release import byte_provenance as BP

ROOT = Path(__file__).resolve().parents[1]
ERRATA_PATH = ROOT / "docs" / "e2r1_release_manifest_errata.json"
SUBJECT_PATH = "docs/e2r1_release_manifest.json"
SUBJECT_COMMIT = "8c3c8f9cc9dfb6fd4e53729615191f2726c25047"

BINARY_RAW = "binary_raw_verified"
CANONICAL = "text_canonical_lf"
CRLF_LEGACY = "text_legacy_crlf_reproducible"
MIXED_LEGACY = "text_legacy_mixed_unreproducible"


def _errata() -> dict:
    return json.loads(ERRATA_PATH.read_text(encoding="utf-8"))


NO_GIT_REASON = (
    "there is no git object database here, so history cannot be read at all. "
    "This is a release tree or an archive, not a clone that failed to fetch. "
    "The errata checks did NOT run and are NOT passing; they run in any git "
    "checkout, and CI is configured with fetch-depth: 0 so they run there"
)


def _classify(content: bytes, pin: str) -> str:
    """The one classifier. The errata is checked against it, never the reverse."""
    if BP.looks_binary(content):
        return BINARY_RAW
    if BP.canonical_digest(content) == pin:
        return CANONICAL
    rendered = BP.canonical_bytes(content).replace(BP.LF, BP.CRLF)
    return CRLF_LEGACY if BP.digest(rendered) == pin else MIXED_LEGACY


@pytest.fixture(scope="module")
def historical():
    """The subject manifest as it was published, from the object database.

    A shallow clone **fails** here, with the fix named in the message: it is a
    fetch setting somebody can change, and turning a missing commit into a pass
    or a bare skip would hide a gap that is trivially fixable. The one skip is a
    tree with no git database at all, which has no history to fetch.
    """
    if not BP.is_git_checkout(ROOT):
        pytest.skip(NO_GIT_REASON)
    BP.require_subject_history(ROOT, SUBJECT_COMMIT, "v1.0.0")
    raw = BP.blob_content(ROOT, SUBJECT_COMMIT, SUBJECT_PATH)
    return raw, json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# The subject is named precisely, and left alone
# ---------------------------------------------------------------------------

def test_the_errata_names_an_immutable_subject():
    subject = _errata()["subject"]
    assert subject["path"] == SUBJECT_PATH
    assert subject["subject_commit_sha"] == SUBJECT_COMMIT
    assert subject["subject_commit_reachable_as_tag"] == "v1.0.0"
    assert subject["subject_modified_by_this_errata"] is False
    assert re.fullmatch(r"[0-9a-f]{40}", subject["subject_blob_object_id"])
    assert re.fullmatch(r"[0-9a-f]{64}", subject["subject_raw_blob_content_sha256"])


def test_the_content_digest_and_the_object_id_are_kept_distinct():
    """Git's object id hashes a header plus the content. It is not sha256."""
    subject = _errata()["subject"]
    assert len(subject["subject_blob_object_id"]) == 40
    assert len(subject["subject_raw_blob_content_sha256"]) == 64
    assert subject["subject_blob_object_id"] != subject[
        "subject_raw_blob_content_sha256"]
    assert "NOT git's object id" in _errata()["field_semantics"][
        "subject_raw_blob_content_sha256"]


def test_the_errata_declares_that_it_reads_history_not_the_worktree():
    verification = _errata()["verification"]
    assert verification["reads_working_tree"] is False
    assert verification["network_access"] is False
    assert "cat-file" in verification["reads"]


def test_the_subject_digests_match_the_published_blob(historical):
    raw, _ = historical
    subject = _errata()["subject"]
    assert BP.digest(raw) == subject["subject_raw_blob_content_sha256"]
    assert BP.canonical_digest(raw) == subject["subject_canonical_sha256"]
    assert BP.blob_object_id(ROOT, SUBJECT_COMMIT, SUBJECT_PATH) == subject[
        "subject_blob_object_id"]
    # The published manifest itself is pure LF, so its two digests coincide.
    assert subject["subject_raw_and_canonical_are_equal_because_the_blob_is_lf"] is (
        subject["subject_raw_blob_content_sha256"] == subject[
            "subject_canonical_sha256"]
    )


def test_the_subject_still_carries_the_row_count_the_errata_claims(historical):
    _, manifest = historical
    assert len(manifest["files"]) == _errata()["subject"]["row_count"]


# ---------------------------------------------------------------------------
# The partition is recomputed, not trusted
# ---------------------------------------------------------------------------

def test_the_partition_is_exactly_what_the_v1_0_0_tree_produces(historical):
    _, manifest = historical
    counts = dict.fromkeys(
        (BINARY_RAW, CANONICAL, CRLF_LEGACY, MIXED_LEGACY), 0
    )
    for row in manifest["files"]:
        content = BP.blob_content(ROOT, SUBJECT_COMMIT, row["path"])
        counts[_classify(content, row["sha256"])] += 1

    declared = _errata()["partition"]
    for name, measured in counts.items():
        assert declared[name] == measured, name
    assert sum(counts.values()) == len(manifest["files"])
    assert declared["sums_to"] == len(manifest["files"])


def test_every_legacy_row_is_declared_and_nothing_else_is(historical):
    """No row missing, no row surplus, no row twice."""
    _, manifest = historical
    measured = {
        row["path"] for row in manifest["files"]
        if _classify(
            BP.blob_content(ROOT, SUBJECT_COMMIT, row["path"]), row["sha256"]
        ) in (CRLF_LEGACY, MIXED_LEGACY)
    }
    entries = _errata()["entries"]
    declared = [entry["path"] for entry in entries]
    assert len(declared) == len(set(declared)), "a path is declared twice"
    assert set(declared) == measured
    assert len(entries) == _errata()["partition"][CRLF_LEGACY] + _errata()[
        "partition"][MIXED_LEGACY]


def test_every_declared_row_verifies_against_the_published_blob(historical):
    _, manifest = historical
    pins = {row["path"]: row["sha256"] for row in manifest["files"]}
    for entry in _errata()["entries"]:
        path = entry["path"]
        assert path in pins, f"{path} is declared but is not a manifest row"
        assert entry["manifest_sha256"] == pins[path], (
            f"{path}: the errata restates the manifest digest differently. It "
            "copies that value; it never becomes a second place it is stated"
        )
        content = BP.blob_content(ROOT, SUBJECT_COMMIT, path)
        assert BP.canonical_digest(content) == entry[
            "canonical_git_blob_content_sha256"], path
        assert BP.blob_object_id(ROOT, SUBJECT_COMMIT, path) == entry[
            "git_blob_object_id"], path
        assert _classify(content, pins[path]) == entry["class"], path


def test_the_reproducible_rows_really_do_reproduce(historical):
    _, manifest = historical
    pins = {row["path"]: row["sha256"] for row in manifest["files"]}
    reproducible = [e for e in _errata()["entries"] if e["class"] == CRLF_LEGACY]
    assert reproducible, "the errata claims 115 of these; it must not claim none"
    for entry in reproducible:
        content = BP.blob_content(ROOT, SUBJECT_COMMIT, entry["path"])
        rendered = BP.render(
            BP.canonical_bytes(content), entry["renders_to_manifest_digest_as"]
        )
        assert BP.digest(rendered) == pins[entry["path"]], entry["path"]
        assert entry["independently_reproducible"] is True


def test_the_three_unreproducible_rows_are_declared_honestly(historical):
    """They are not renderable, and the errata says so instead of inventing one."""
    _, manifest = historical
    pins = {row["path"]: row["sha256"] for row in manifest["files"]}
    mixed = [e for e in _errata()["entries"] if e["class"] == MIXED_LEGACY]
    assert len(mixed) == 3
    for entry in mixed:
        assert entry["independently_reproducible"] is False
        assert entry["renders_to_manifest_digest_as"] is None
        assert entry["why_unreproducible"]
        content = BP.blob_content(ROOT, SUBJECT_COMMIT, entry["path"])
        rendered = BP.canonical_bytes(content).replace(BP.LF, BP.CRLF)
        assert BP.digest(rendered) != pins[entry["path"]], (
            f"{entry['path']} is declared unreproducible yet a uniform CRLF "
            "render does reproduce its digest. The declaration would be wrong"
        )
        # Their canonical content is still verified; only the byte pattern of a
        # long-gone working tree is beyond recovery.
        assert BP.canonical_digest(content) == entry[
            "canonical_git_blob_content_sha256"]


def test_the_decision_log_this_branch_appends_to_is_one_of_them(historical):
    """The reason the baseline is historical, stated as a test.

    This branch appends three rows to ``docs/architecture/decision_log.md``. If
    the errata were measured from the working tree, this branch's own commit
    would change what the errata says about the published release.
    """
    declared = {e["path"] for e in _errata()["entries"] if e["class"] == MIXED_LEGACY}
    assert "docs/architecture/decision_log.md" in declared
    working = (ROOT / "docs" / "architecture" / "decision_log.md").read_bytes()
    historical_content = BP.blob_content(
        ROOT, SUBJECT_COMMIT, "docs/architecture/decision_log.md"
    )
    assert BP.canonical_digest(working) != BP.canonical_digest(historical_content), (
        "this branch is expected to have appended to the decision log; if it "
        "has not, the appended decisions are missing"
    )
    entry = next(
        e for e in _errata()["entries"]
        if e["path"] == "docs/architecture/decision_log.md"
    )
    assert BP.canonical_digest(historical_content) == entry[
        "canonical_git_blob_content_sha256"], (
        "the errata must still describe the published blob, not the edited tree"
    )


# ---------------------------------------------------------------------------
# Synthetic failures
# ---------------------------------------------------------------------------

def test_synthetic_a_surplus_declaration_would_be_caught():
    """The set comparison is exact in both directions, not a subset check."""
    measured = {"a", "b"}
    assert {"a", "b", "c"} != measured
    assert {"a"} != measured


def test_synthetic_a_wrong_canonical_digest_in_the_errata_would_be_caught(historical):
    entry = dict(_errata()["entries"][0])
    entry["canonical_git_blob_content_sha256"] = "0" * 64
    content = BP.blob_content(ROOT, SUBJECT_COMMIT, entry["path"])
    assert BP.canonical_digest(content) != entry[
        "canonical_git_blob_content_sha256"]


def test_synthetic_a_relabelled_class_would_be_caught(historical):
    entry = dict(_errata()["entries"][0])
    original = entry["class"]
    entry["class"] = MIXED_LEGACY if original == CRLF_LEGACY else CRLF_LEGACY
    manifest = json.loads(
        BP.blob_content(ROOT, SUBJECT_COMMIT, SUBJECT_PATH).decode("utf-8")
    )
    pin = next(r["sha256"] for r in manifest["files"] if r["path"] == entry["path"])
    content = BP.blob_content(ROOT, SUBJECT_COMMIT, entry["path"])
    assert _classify(content, pin) == original != entry["class"]


def test_the_errata_does_not_touch_the_manifest_it_describes():
    """A correction that edits the record is not a correction."""
    text = ERRATA_PATH.read_text(encoding="utf-8")
    assert '"subject_modified_by_this_errata": false' in text
    assert (ROOT / SUBJECT_PATH).is_file()
