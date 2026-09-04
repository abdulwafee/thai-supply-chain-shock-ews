"""Phase 2 tests: the pinned artifacts, and nothing the loader is not allowed to read.

Hermetic. Most cases build a small fake repository root under ``tmp_path`` by copying
the four real artifacts into it, so a corruption can be injected without touching the
repository. A handful of integration tests read the real tree, because a pin that is
only ever checked against a copy of itself is not checking much.

The pins are re-derived here from the **committed blobs** with ``git cat-file`` rather
than from the working tree. On Windows two of these files are checked out CRLF while
Git stores them LF, so a test that measured the working tree would pass on one platform
and fail on the other — which is the defect the canonical representation exists to
prevent, reintroduced in the test suite instead of the code.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.release.byte_provenance import canonical_digest, digest
from thai_supply_chain_ews.scenario import artifacts as art
from thai_supply_chain_ews.scenario import contract

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "structural_exposure_scenario.yaml"
ARTIFACTS_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "artifacts.py"

DECLARED_PATHS = {
    "exposure_matrix": "docs/c3_commodity_exposure_matrix.json",
    "structural_path_audit": "docs/c5_structural_path_audit.json",
    "price_stage_source_audit": "docs/c5_price_stage_source_audit.json",
    "industry_map": "data/mapping/industry_map.csv",
}


@pytest.fixture
def policy() -> contract.ScenarioPolicy:
    return contract.load_policy(POLICY_PATH)


@pytest.fixture
def declarations():
    return art.read_artifact_declarations(POLICY_PATH)


def committed_blob(relative: str) -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{relative}"],
        cwd=str(ROOT), capture_output=True, check=True,
    ).stdout


def fake_root(tmp_path: Path) -> Path:
    """A minimal tree containing exactly the four pinned artifacts."""
    root = tmp_path / "repo"
    for relative in DECLARED_PATHS.values():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


def policy_with(tmp_path: Path, mutate) -> Path:
    data = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def test_the_allowlist_is_exactly_four_named_artifacts(declarations):
    assert len(declarations) == 4
    assert {d.name for d in declarations} == set(art.ARTIFACT_NAMES)
    assert {d.name: d.path for d in declarations} == DECLARED_PATHS
    assert len({d.path for d in declarations}) == 4


def test_every_declaration_names_its_digest_representation(declarations):
    for declaration in declarations:
        assert declaration.digest_representation in art.SUPPORTED_DIGEST_REPRESENTATIONS
        assert declaration.digest_representation == "canonical_lf"
        assert len(declaration.sha256) == 64
        assert declaration.role


def test_each_pin_equals_the_canonical_digest_of_the_committed_blob(declarations):
    """Derived from Git, not from the working tree, so the check is platform-neutral."""
    for declaration in declarations:
        blob = committed_blob(declaration.path)
        assert canonical_digest(blob) == declaration.sha256, declaration.name


def test_each_pin_also_verifies_against_the_working_tree_on_this_platform(declarations):
    for declaration in declarations:
        data = (ROOT / declaration.path).read_bytes()
        assert declaration.digest_of(data) == declaration.sha256, declaration.name


def test_a_crlf_checkout_and_an_lf_checkout_verify_identically(tmp_path, declarations, policy):
    """The property that makes the canonical representation the right choice.

    Two of these artifacts are stored LF and checked out CRLF on Windows. Both spellings
    are constructed here and both must satisfy the same pin; a raw-byte pin could not.
    """
    for declaration in declarations:
        blob = committed_blob(declaration.path)
        lf = blob.replace(b"\r\n", b"\n")
        crlf = lf.replace(b"\n", b"\r\n")
        assert declaration.digest_of(lf) == declaration.sha256
        assert declaration.digest_of(crlf) == declaration.sha256
        if b"\n" in lf:
            assert digest(lf) != digest(crlf)  # the raw bytes really do differ

    root = tmp_path / "crlf"
    for relative in DECLARED_PATHS.values():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        body = committed_blob(relative).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        target.write_bytes(body)
    bundle = art.load_artifact_bundle(root, policy=policy, policy_path=POLICY_PATH)
    assert len(bundle.pairs) == art.EXPECTED_PAIR_COUNT


def test_the_pins_agree_with_the_ci_r1_errata_where_it_records_them(declarations):
    """Agreement with the historical record, checked — not depended on at runtime."""
    errata = json.loads(
        (ROOT / "docs" / "e2r1_release_manifest_errata.json").read_text(encoding="utf-8")
    )
    rows = {entry["path"]: entry for entry in errata["entries"]}
    checked = 0
    for declaration in declarations:
        row = rows.get(declaration.path)
        if row is None:
            continue
        assert row["canonical_git_blob_content_sha256"] == declaration.sha256, declaration.name
        checked += 1
    assert checked >= 2, "the two CRLF-affected artifacts should both appear in the errata"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.pop("runtime_artifacts"),
        lambda data: data.update({"runtime_artifacts_are_a_closed_set": False}),
        lambda data: data.update({"runtime_artifacts_discovered_by_scan": True}),
        lambda data: data.update({"runtime_artifacts_fall_back_to_unpinned": True}),
        lambda data: data.update({"historical_release_manifest_is_a_runtime_registry": True}),
        lambda data: data["runtime_artifacts"].pop(),
    ],
)
def test_a_policy_that_weakens_the_artifact_declarations_is_refused(tmp_path, mutate):
    with pytest.raises(contract.ScenarioPolicyError):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


def test_a_duplicate_logical_artifact_name_is_refused(tmp_path):
    def mutate(data):
        data["runtime_artifacts"].append(dict(data["runtime_artifacts"][0]))

    with pytest.raises(contract.ScenarioPolicyError, match="duplicate logical"):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


def test_a_duplicate_artifact_path_is_refused(tmp_path):
    def mutate(data):
        clone = dict(data["runtime_artifacts"][1])
        clone["name"] = "industry_map"
        data["runtime_artifacts"][3] = clone

    with pytest.raises(contract.ScenarioPolicyError, match="duplicate artifact path"):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


def test_an_unexpected_artifact_name_is_refused(tmp_path):
    def mutate(data):
        entry = dict(data["runtime_artifacts"][0])
        entry["name"] = "locked_test_manifest"
        entry["path"] = "docs/d3_locked_test_manifest.json"
        data["runtime_artifacts"].append(entry)

    with pytest.raises(contract.ScenarioPolicyError, match="not a runtime artifact"):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


@pytest.mark.parametrize("representation", ["sha256", "raw", "canonical", "utf8", ""])
def test_an_unsupported_digest_representation_is_refused(tmp_path, representation):
    def mutate(data):
        data["runtime_artifacts"][0]["digest_representation"] = representation

    with pytest.raises(contract.ScenarioPolicyError):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


@pytest.mark.parametrize(
    "field", ["name", "path", "format", "sha256", "digest_representation"]
)
def test_a_declaration_missing_a_required_field_is_refused(tmp_path, field):
    def mutate(data):
        data["runtime_artifacts"][0].pop(field)

    with pytest.raises(contract.ScenarioPolicyError):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


@pytest.mark.parametrize("value", ["deadbeef", "Z" * 64, "9204C3C9" + "a" * 56, ""])
def test_a_malformed_digest_value_is_refused(tmp_path, value):
    def mutate(data):
        data["runtime_artifacts"][0]["sha256"] = value

    with pytest.raises(contract.ScenarioPolicyError):
        art.read_artifact_declarations(policy_with(tmp_path, mutate))


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "/etc/passwd",
        "\\\\server\\share\\file.json",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        "../outside.json",
        "docs/../../outside.json",
        "/docs/c3_commodity_exposure_matrix.json",
        "\\docs\\c3_commodity_exposure_matrix.json",
    ],
)
def test_an_escaping_artifact_path_is_refused(tmp_path, policy, bad):
    def mutate(data):
        data["runtime_artifacts"][0]["path"] = bad

    root = fake_root(tmp_path)
    with pytest.raises((art.ArtifactIntegrityError, contract.ScenarioPolicyError)):
        art.load_artifact_bundle(root, policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))


def test_a_padded_declared_path_is_normalised_rather_than_refused(tmp_path, policy):
    """Incidental whitespace around a YAML scalar is stripped, then every rule applies.

    Recorded because it is a real behaviour of the policy reader rather than an
    accident: the stripped value still has to satisfy confinement and its own pin.
    """
    def mutate(data):
        data["runtime_artifacts"][0]["path"] = "  docs/c3_commodity_exposure_matrix.json  "

    bundle = art.load_artifact_bundle(fake_root(tmp_path), policy=policy,
                                      policy_path=policy_with(tmp_path, mutate))
    assert len(bundle.pairs) == 48


def test_a_symlink_that_escapes_the_repository_root_is_refused(tmp_path, policy):
    """Spelling stays inside the root; resolution does not."""
    root = fake_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copyfile(ROOT / DECLARED_PATHS["industry_map"], outside / "industry_map.csv")
    link = root / "data" / "mapping" / "linked.csv"
    try:
        link.symlink_to(outside / "industry_map.csv")
    except (OSError, NotImplementedError):
        pytest.skip(
            "this platform or account cannot create a symlink; the confinement rule is "
            "unchanged, it simply cannot be demonstrated here"
        )

    def mutate(data):
        for entry in data["runtime_artifacts"]:
            if entry["name"] == "industry_map":
                entry["path"] = "data/mapping/linked.csv"

    # The link resolves to a file whose bytes match the pin, so only the resolved-path
    # rule can refuse it. If confinement were spelling-only this would load happily.
    with pytest.raises(art.ArtifactIntegrityError, match="outside the repository root"):
        art.load_artifact_bundle(root, policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))


def test_a_directory_where_a_file_is_declared_is_refused(tmp_path, policy):
    root = fake_root(tmp_path)
    target = root / DECLARED_PATHS["industry_map"]
    target.unlink()
    target.mkdir()
    with pytest.raises(art.ArtifactIntegrityError, match="is not a file"):
        art.load_artifact_bundle(root, policy=policy, policy_path=POLICY_PATH)


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DECLARED_PATHS))
def test_a_missing_artifact_is_refused_with_no_fallback(tmp_path, policy, name):
    root = fake_root(tmp_path)
    (root / DECLARED_PATHS[name]).unlink()
    with pytest.raises(art.ArtifactIntegrityError) as caught:
        art.load_artifact_bundle(root, policy=policy, policy_path=POLICY_PATH)
    assert "is missing" in str(caught.value)
    assert "no unpinned fallback" in str(caught.value)


@pytest.mark.parametrize("name", sorted(DECLARED_PATHS))
def test_a_single_changed_byte_is_refused(tmp_path, policy, name):
    root = fake_root(tmp_path)
    target = root / DECLARED_PATHS[name]
    data = bytearray(target.read_bytes())
    index = next(i for i, byte in enumerate(data) if chr(byte).isdigit())
    data[index] = ord("9") if data[index] != ord("9") else ord("8")
    target.write_bytes(bytes(data))
    with pytest.raises(art.ArtifactIntegrityError, match="does not match its pin"):
        art.load_artifact_bundle(root, policy=policy, policy_path=POLICY_PATH)


def test_a_wrong_declared_digest_is_refused(tmp_path, policy):
    def mutate(data):
        data["runtime_artifacts"][0]["sha256"] = "0" * 64

    root = fake_root(tmp_path)
    with pytest.raises(art.ArtifactIntegrityError, match="does not match its pin"):
        art.load_artifact_bundle(root, policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))


def test_the_loader_never_repairs_or_regenerates_an_artifact(tmp_path, policy):
    root = fake_root(tmp_path)
    target = root / DECLARED_PATHS["industry_map"]
    target.write_bytes(b"industry_id,name_en\n")
    before = target.read_bytes()
    with pytest.raises(art.ArtifactIntegrityError):
        art.load_artifact_bundle(root, policy=policy, policy_path=POLICY_PATH)
    assert target.read_bytes() == before


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("exposure_matrix", b"{not json"),
        ("exposure_matrix", b"[]"),
        ("structural_path_audit", b"{}"),
        ("price_stage_source_audit", b'{"price_stage_alignment": []}'),
    ],
)
def test_malformed_json_is_refused(tmp_path, policy, name, body):
    root = fake_root(tmp_path)
    target = root / DECLARED_PATHS[name]
    target.write_bytes(body)

    def mutate(data):
        for entry in data["runtime_artifacts"]:
            if entry["name"] == name:
                entry["sha256"] = canonical_digest(body)

    with pytest.raises(art.ArtifactIntegrityError):
        art.load_artifact_bundle(root, policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))


@pytest.mark.parametrize(
    "body",
    [
        b"wrong,columns\n1,2\n",
        b"industry_id,name_en,name_th,tsic_divisions,status,source_of_truth\n",
        b"industry_id,name_en,name_th,tsic_divisions,status,source_of_truth\nIND-01,,,,,\n",
    ],
)
def test_malformed_csv_is_refused(tmp_path, policy, body):
    root = fake_root(tmp_path)
    (root / DECLARED_PATHS["industry_map"]).write_bytes(body)

    def mutate(data):
        for entry in data["runtime_artifacts"]:
            if entry["name"] == "industry_map":
                entry["sha256"] = canonical_digest(body)

    with pytest.raises(art.ArtifactIntegrityError):
        art.load_artifact_bundle(root, policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))


def test_a_missing_repository_root_is_refused(tmp_path, policy):
    with pytest.raises(art.ArtifactIntegrityError, match="is not a directory"):
        art.load_artifact_bundle(tmp_path / "nope", policy=policy, policy_path=POLICY_PATH)


# ---------------------------------------------------------------------------
# Dataset shape, against the real artifacts
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bundle():
    return art.load_artifact_bundle(ROOT, policy=contract.load_policy(POLICY_PATH),
                                    policy_path=POLICY_PATH)


def test_the_real_bundle_has_the_published_shape(bundle):
    assert len(bundle.industries) == art.EXPECTED_INDUSTRY_COUNT == 12
    assert len(bundle.pairs) == art.EXPECTED_PAIR_COUNT == 48
    assert len(bundle.mediators) == 48 * art.EXPECTED_MEDIATORS_PER_PAIR == 480
    assert len(bundle.price_stages) == 48
    assert bundle.structural_reference_year == 2015


def test_every_industry_channel_pair_is_present_exactly_once(bundle):
    keys = [pair.key for pair in bundle.pairs]
    assert len(keys) == len(set(keys)) == 48
    expected = {(i, c) for i in bundle.industry_ids for c in bundle.channel_sectors}
    assert set(keys) == expected


def test_every_pair_has_exactly_ten_ranked_mediators(bundle):
    for industry in bundle.industry_ids:
        for channel in bundle.channel_sectors:
            mediators = bundle.mediators_for(industry, channel)
            assert len(mediators) == 10
            assert sorted(m.rank for m in mediators) == list(range(1, 11))


def test_every_pair_has_exactly_one_price_stage_record(bundle):
    for industry in bundle.industry_ids:
        for channel in bundle.channel_sectors:
            assert bundle.price_stage_for(industry, channel) is not None


def test_the_industry_map_and_the_exposure_matrix_agree(bundle):
    names = bundle.industry_names
    assert sorted(names) == [f"IND-{n:02d}" for n in range(1, 13)]
    for pair in bundle.pairs:
        assert pair.industry_name == names[pair.industry_id]


def test_channels_and_sectors_match_the_policy_and_exclude_093(bundle):
    assert set(bundle.channel_sectors) == set(contract.REGISTERED_CHANNELS)
    assert bundle.channel_sectors["aluminum_usd_mt"] == "107"
    assert bundle.channel_sectors["copper_usd_mt"] == "107"
    assert bundle.channel_sectors["brent_crude_usd_bbl"] == "031"
    assert bundle.channel_sectors["rubber_rss3_usd_kg"] == "095"
    assert "093" not in set(bundle.channel_sectors.values())
    for pair in bundle.pairs:
        assert pair.io_sector_code == bundle.channel_sectors[pair.channel]


def test_coefficients_are_exact_decimals_never_floats(bundle):
    for pair in bundle.pairs:
        for value in (pair.direct_exposure, pair.total_requirement_exposure,
                      pair.published_indirect_exposure, pair.propagated_exposure):
            assert isinstance(value, Decimal)
            assert not isinstance(value, float)
    for mediator in bundle.mediators[:20]:
        assert isinstance(mediator.contribution, Decimal)


def test_the_derived_propagated_component_satisfies_the_identity_exactly(bundle):
    """Derived as total - direct, so the identity holds with no residual at all."""
    for pair in bundle.pairs:
        assert pair.direct_exposure + pair.propagated_exposure == pair.total_requirement_exposure
        assert pair.propagated_exposure >= 0


def test_the_published_indirect_field_does_not_satisfy_that_identity(bundle):
    """Why the component is derived rather than read.

    The artifact's three coefficients came from float64 arithmetic and disagree by a
    tiny amount. Preserved as a published fact, and not what the arithmetic uses.
    """
    residuals = [
        abs(p.direct_exposure + p.published_indirect_exposure - p.total_requirement_exposure)
        for p in bundle.pairs
    ]
    assert any(r != 0 for r in residuals), "if this ever becomes exact, prefer the published field"
    assert max(residuals) < Decimal("1e-15")


def test_eligibility_and_sign_are_internally_coherent(bundle):
    for pair in bundle.pairs:
        if pair.feature_eligible:
            assert pair.sign is not None
        if pair.sign is None:
            assert not pair.feature_eligible
            assert pair.direction_channel == "mixed_or_ambiguous"
    ineligible = {p.key for p in bundle.pairs if not p.feature_eligible}
    assert ineligible == {
        ("IND-06", "rubber_rss3_usd_kg"),
        ("IND-08", "aluminum_usd_mt"),
        ("IND-08", "copper_usd_mt"),
        ("IND-12", "aluminum_usd_mt"),
        ("IND-12", "copper_usd_mt"),
    }


# ---------------------------------------------------------------------------
# What the loader is allowed to touch
# ---------------------------------------------------------------------------


def test_loading_reads_only_the_four_artifacts_and_the_policy(monkeypatch, policy):
    """Recorded from the filesystem calls themselves, not asserted by inspection."""
    opened: list[str] = []
    real_bytes, real_text = Path.read_bytes, Path.read_text

    def record_bytes(self, *args, **kwargs):
        opened.append(str(self))
        return real_bytes(self, *args, **kwargs)

    def record_text(self, *args, **kwargs):
        opened.append(str(self))
        return real_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", record_bytes)
    monkeypatch.setattr(Path, "read_text", record_text)
    art.load_artifact_bundle(ROOT, policy=policy, policy_path=POLICY_PATH)

    allowed = {(ROOT / relative).resolve() for relative in DECLARED_PATHS.values()}
    allowed.add(POLICY_PATH.resolve())
    unexpected = sorted({p for p in opened if Path(p).resolve() not in allowed})
    assert unexpected == []


def test_the_loader_performs_no_discovery_and_reaches_no_network():
    tree = ast.parse(ARTIFACTS_SOURCE.read_text(encoding="utf-8"))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in ("glob", "rglob", "iterdir", "walk", "scandir", "listdir",
                      "urlopen", "urlretrieve"):
        assert forbidden not in calls, forbidden

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not {name.split(".")[0] for name in imported} & {
        "socket", "ssl", "urllib", "http", "requests", "httpx", "ftplib", "smtplib"
    }


def test_the_loader_imports_no_model_target_vault_or_data_module():
    """One deliberate exception, named: the repository's byte-provenance convention.

    ``release.byte_provenance`` is a pure hashing utility with no side effects, and
    reusing it is what keeps one definition of "canonical digest" in the project rather
    than two that can drift.
    """
    tree = ast.parse(ARTIFACTS_SOURCE.read_text(encoding="utf-8"))
    project = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
            "thai_supply_chain_ews."
        ):
            project.add(node.module)
    assert project == {
        "thai_supply_chain_ews.release.byte_provenance",
        "thai_supply_chain_ews.scenario.contract",
    }
    for forbidden in ("models", "modeling", "targets", "evaluation", "vault", "data",
                      "features", "matrices", "structure", "synthesis"):
        assert not any(m.startswith(f"thai_supply_chain_ews.{forbidden}") for m in project)


def test_no_locked_test_or_raw_data_path_appears_in_the_loader():
    source = ARTIFACTS_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
                node.body[0].value, ast.Constant
            ) and isinstance(node.body[0].value.value, str):
                node.body[0].value.value = ""
    constants = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for fragment in ("locked", "final_test", "data/raw", "data/features", ".parquet",
                     ".obsidian"):
        assert not any(fragment in value for value in constants), fragment


def test_the_private_parsers_are_not_exported():
    from thai_supply_chain_ews import scenario

    for name in ("_json_document", "_industries", "_exposure_pairs", "_mediators",
                 "_price_stages", "_cross_check", "_resolve_within", "_verified_bytes",
                 "_policy_mapping"):
        assert name not in art.__all__
        assert name not in scenario.__all__
        assert not hasattr(scenario, name)
        assert hasattr(art, name)


def test_a_cross_artifact_disagreement_beyond_tolerance_is_refused(tmp_path, policy):
    """C5's own coefficients corroborate C3's; a real divergence must not pass."""
    root = fake_root(tmp_path)
    target = root / DECLARED_PATHS["price_stage_source_audit"]
    document = json.loads(target.read_text(encoding="utf-8"))
    document["price_stage_alignment"][0]["total_exposure"] = 0.5
    body = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    target.write_bytes(body)

    def mutate(data):
        for entry in data["runtime_artifacts"]:
            if entry["name"] == "price_stage_source_audit":
                entry["sha256"] = canonical_digest(body)

    with pytest.raises(art.ArtifactIntegrityError, match="agreement tolerance"):
        art.load_artifact_bundle(root, policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))


def test_the_agreement_tolerance_is_declared_policy_not_an_estimate():
    declared = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["cross_artifact_agreement"]
    assert declared["tolerance_is_validation_policy"] is True
    assert declared["tolerance_is_a_learned_threshold"] is False
    assert declared["authoritative_coefficient_source"] == "exposure_matrix"
    assert declared["supporting_artifacts_are_scored"] is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only path spelling")
def test_posix_absolute_paths_are_refused_on_posix(tmp_path, policy):
    def mutate(data):
        data["runtime_artifacts"][0]["path"] = "/tmp/exposure.json"

    with pytest.raises(art.ArtifactIntegrityError, match="absolute"):
        art.load_artifact_bundle(fake_root(tmp_path), policy=policy,
                                 policy_path=policy_with(tmp_path, mutate))
