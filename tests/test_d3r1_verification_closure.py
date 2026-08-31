"""Task D3-R1 tests — verification closure and interpretation correction.

Three things went wrong in D3 reporting and are locked down here: a
repository-wide lint status that was asserted rather than measured, a
restoration claim stronger than its evidence, and an artifact count that did not
match its own list. Each has a test that fails if the mistake returns.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "d3r1_artifact_inventory.json"
INTERPRETATION = ROOT / "docs" / "d3r1_benchmark_interpretation.json"
RESTORATION = ROOT / "docs" / "d3_restored_d1_checksums.json"
D3_RESULTS = ROOT / "docs" / "d3_operational_baseline_results.json"
ERRATUM = ROOT / "docs" / "d1_development_results.errata.md"
PYPROJECT = ROOT / "pyproject.toml"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Repository-wide lint really passes
# ---------------------------------------------------------------------------
def test_full_repository_ruff_passes():
    """The whole repo, not a hand-picked subset."""
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 0, (
        f"ruff check . failed:\n{completed.stdout}\n{completed.stderr}"
    )
    assert "All checks passed" in completed.stdout


def test_ruff_config_has_no_broad_exclusion():
    """A green lint must not be bought with exclusions."""
    text = PYPROJECT.read_text(encoding="utf-8")
    ruff_section = text[text.index("[tool.ruff]"):]
    for forbidden in ("exclude", "extend-exclude", "per-file-ignores", "ignore ="):
        assert forbidden not in ruff_section.split("[tool.pytest")[0], forbidden


def test_ruff_still_selects_the_original_rule_families():
    text = PYPROJECT.read_text(encoding="utf-8")
    assert 'select = ["E", "F", "I", "UP", "B"]' in text


def test_d2_files_are_not_hidden_from_lint():
    """The 79 violations were all in D2 files; they must stay in scope."""
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--show-files"],
        cwd=ROOT, capture_output=True, text=True,
    )
    listed = completed.stdout.replace("\\", "/")
    for d2_file in (
        "src/thai_supply_chain_ews/data/oie_mpi_discovery.py",
        "src/thai_supply_chain_ews/data/oie_mpi_history.py",
        "src/thai_supply_chain_ews/data/oie_mpi_release_inventory.py",
        "src/thai_supply_chain_ews/data/oie_mpi_vintages.py",
        "src/thai_supply_chain_ews/data/target_timing_contract.py",
        "scripts/audit_d2_oie_mpi_timing.py",
        "tests/test_d2_oie_mpi_timing.py",
    ):
        assert d2_file in listed, d2_file


#: Files D3-R1 lint-corrected. The fix had to be real, not suppressed.
LINT_CORRECTED = (
    "src/thai_supply_chain_ews/data/oie_mpi_discovery.py",
    "src/thai_supply_chain_ews/data/oie_mpi_history.py",
    "src/thai_supply_chain_ews/data/oie_mpi_release_inventory.py",
    "src/thai_supply_chain_ews/data/oie_mpi_vintages.py",
    "src/thai_supply_chain_ews/data/target_timing_contract.py",
    "tests/test_d2_oie_mpi_timing.py",
)


@pytest.mark.parametrize("relative", LINT_CORRECTED)
def test_no_noqa_suppression_in_lint_corrected_files(relative):
    """The 79 violations were fixed, not silenced."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert not re.search(r"#\s*noqa", text), f"{relative} suppresses a rule"


def test_audit_script_noqa_is_only_the_established_import_pattern():
    """scripts/ use `# noqa: E402` after sys.path insertion; nothing broader."""
    text = (ROOT / "scripts" / "audit_d2_oie_mpi_timing.py").read_text(encoding="utf-8")
    codes = set(re.findall(r"#\s*noqa:\s*([A-Z]+[0-9]+)", text))
    bare = re.findall(r"#\s*noqa(?!:)", text)
    assert codes <= {"E402"}, codes
    assert not bare, "bare noqa suppresses every rule"


def test_no_blanket_ruff_disable_comment():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "ruff: noqa" not in text, path


# ---------------------------------------------------------------------------
# 2. D3 numerical results are unchanged
# ---------------------------------------------------------------------------
EXPECTED = {
    1: {
        "selected": "operational_persistence_latest_published",
        "mae": 17.0945,
        "no_contraction_mae": 19.4453,
        "fn": 8,
        "no_contraction_fn": 21,
    },
    3: {
        "selected": "operational_persistence_trailing_3m_max",
        "mae": 16.6338,
        "no_contraction_mae": 16.9791,
        "fn": 4,
        "no_contraction_fn": 28,
    },
}


@pytest.mark.parametrize("horizon", [1, 3])
def test_d3_metrics_unchanged(horizon):
    results = _load(D3_RESULTS)
    block = results["metrics"][str(horizon)]["baselines"]
    expected = EXPECTED[horizon]
    assert block[expected["selected"]]["macro_industry_mae"] == pytest.approx(
        expected["mae"], abs=1e-4
    )
    assert block["operational_no_contraction"]["macro_industry_mae"] == pytest.approx(
        expected["no_contraction_mae"], abs=1e-4
    )
    assert block[expected["selected"]]["high_stress"]["false_negative"] == expected["fn"]
    assert (
        block["operational_no_contraction"]["high_stress"]["false_negative"]
        == expected["no_contraction_fn"]
    )


@pytest.mark.parametrize("horizon", [1, 3])
def test_selected_benchmark_unchanged(horizon):
    results = _load(D3_RESULTS)
    assert (
        results["benchmark_selection"][str(horizon)]["selected_benchmark"]
        == EXPECTED[horizon]["selected"]
    )


def test_d3_prediction_counts_and_checksum_present():
    results = _load(D3_RESULTS)
    assert results["prediction_counts"]["total"] == 1620
    assert results["prediction_counts"]["horizon_1"] == 720
    assert results["prediction_counts"]["horizon_3"] == 900
    assert results["outputs"]["predictions_sha256"]


def test_d3_prediction_parquet_matches_recorded_checksum():
    import hashlib

    import pandas as pd

    results = _load(D3_RESULTS)
    frame = pd.read_parquet(ROOT / results["outputs"]["predictions_path"])
    digest = hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=False).values.tobytes()
    ).hexdigest()
    assert digest == results["outputs"]["predictions_sha256"]
    assert len(frame) == 1620


# ---------------------------------------------------------------------------
# 3. Benchmark interpretation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("horizon", ["1", "3"])
def test_required_interpretation_fields(horizon):
    block = _load(INTERPRETATION)["horizons"][horizon]
    assert block["mae_difference_conclusive"] is False
    assert block["mae_superiority_over_no_contraction"] == "inconclusive"
    assert block["tie_break_applied"] == "high_stress_false_negative_count"
    assert block["selected_operational_benchmark_unchanged"] is True
    assert block["benchmark_selection_robust_to_tie_interpretation"] is True
    assert block["no_contraction_retained_as_secondary_reference"] is True
    assert block["additional_test_on_same_development_sample_required"] is False


@pytest.mark.parametrize("horizon,fn,other", [("1", 8, 21), ("3", 4, 28)])
def test_false_negative_tie_break_recorded(horizon, fn, other):
    block = _load(INTERPRETATION)["horizons"][horizon]
    assert block["persistence_false_negatives"] == fn
    assert block["no_contraction_false_negatives"] == other
    assert block["false_negative_margin"] == other - fn
    assert block["paired_ci_crosses_zero"] is True


def test_no_second_statistical_test_was_introduced():
    payload = _load(INTERPRETATION)
    assert payload["no_new_statistic_computed"] is True
    for forbidden in (
        "new_hypothesis_test",
        "another_bootstrap_seed",
        "different_block_length",
        "one_sided_interval",
        "post_hoc_subgroup",
        "new_tie_threshold",
    ):
        assert forbidden in payload["prohibited_and_not_performed"]


def test_no_contraction_is_retained_not_deleted():
    """Synthetic failure: dropping no-contraction because it lost on MAE."""
    payload = _load(INTERPRETATION)
    assert payload["future_model_comparator_policy"]["no_contraction_removed"] is False
    assert (
        payload["future_model_comparator_policy"]["secondary_comparator"]
        == "operational_no_contraction"
    )
    results = _load(D3_RESULTS)
    for horizon in ("1", "3"):
        assert "operational_no_contraction" in results["metrics"][horizon]["baselines"]


def test_bootstrap_seed_and_block_length_were_not_changed():
    """Synthetic failure: re-searching with a new seed or block length."""
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs" / "operational_evaluation.yaml").read_text(encoding="utf-8")
    )
    assert config["bootstrap"]["random_seed"] == 20260828
    assert config["bootstrap"]["block_length_months"] == 3
    assert config["bootstrap"]["replications"] == 1000
    results = _load(D3_RESULTS)
    interval = results["metrics"]["1"]["baselines"]["operational_no_contraction"]["macro_mae_ci"]
    assert interval["seed"] == 20260828
    assert interval["block_length_months"] == 3


def test_persistence_is_not_described_as_weak():
    payload = _load(INTERPRETATION)
    assert "not evidence of a weak benchmark" in payload["why_persistence_is_not_weak"]


# ---------------------------------------------------------------------------
# 4. Restoration evidence is stated honestly
# ---------------------------------------------------------------------------
def test_restoration_fields_are_honest():
    payload = _load(RESTORATION)
    assert payload["original_pre_d2_checksum_available"] is False
    assert payload["restoration_method"] == "inverse_of_known_inserted_block"
    assert payload["inserted_block_absent_after_restoration"] is True
    assert payload["original_text_retained_after_inverse_patch"] is True
    assert payload["exact_pre_d2_byte_identity_proven"] is False
    assert payload["post_restoration_checksum_pinned"] is True
    assert payload["post_restoration_results_checksum"].startswith("54a66c41")
    assert payload["post_restoration_protocol_checksum"].startswith("80761aab")


def test_pinned_digest_is_not_presented_as_historical_proof():
    """Synthetic failure: a new checksum offered as proof of the old one."""
    payload = _load(RESTORATION)
    meaning = payload["meaning_of_pinned_digests"]
    assert "not evidence of the unknown historical" in meaning
    assert payload["exact_pre_d2_byte_identity_proven"] is False


@pytest.mark.parametrize(
    "relative",
    ["README.md", "docs/methodology.md", "docs/d1_development_results.errata.md",
     "docs/d2_target_timing_decision.md"],
)
def test_no_document_claims_pre_d2_byte_identity(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    for forbidden in (
        "byte-identical to pre-D2",
        "original checksum matched",
        "restored exactly by checksum",
        "verified byte-identical",
        "restored byte-for-byte",
    ):
        assert forbidden not in text, f"{relative} claims {forbidden!r}"


def test_erratum_states_the_restoration_limit():
    text = ERRATUM.read_text(encoding="utf-8")
    assert "cannot be" in text and "byte identity" in text
    assert "d3_restored_d1_checksums.json" in text


def test_erratum_remains_outside_the_generated_d1_files():
    for relative in ("docs/d1_development_results.md", "docs/d1_modeling_protocol.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "AD-R66" not in text
        assert "Task D2" not in text
        assert "never better" in text


def test_d2_decision_document_emits_the_erratum_link_from_its_generator():
    """The link must survive regenerating D2, which is how D3 lost it once."""
    source = (ROOT / "scripts" / "audit_d2_oie_mpi_timing.py").read_text(encoding="utf-8")
    assert "d1_development_results.errata.md" in source
    rendered = (ROOT / "docs" / "d2_target_timing_decision.md").read_text(encoding="utf-8")
    assert "d1_development_results.errata.md" in rendered


# ---------------------------------------------------------------------------
# 5. Artifact inventory matches the worktree
# ---------------------------------------------------------------------------
def test_inventory_counts_equal_actual_path_lists():
    inv = _load(INVENTORY)
    assert len(inv["created"]["by_d3"]) == inv["created"]["count_d3"]
    assert len(inv["created"]["by_d3r1"]) == inv["created"]["count_d3r1"]
    assert len(inv["modified"]["by_d3"]) == inv["modified"]["count_d3"]
    assert len(inv["modified"]["by_d3r1"]) == inv["modified"]["count_d3r1"]
    assert (
        len(inv["restored_by_inverse_patch"]["paths"])
        == inv["restored_by_inverse_patch"]["count"]
    )
    assert len(inv["regenerated_by_rerun"]["paths"]) == inv["regenerated_by_rerun"]["count"]
    assert len(inv["unchanged_verified"]["paths"]) == inv["unchanged_verified"]["count"]


def test_every_inventory_path_exists_in_the_worktree():
    inv = _load(INVENTORY)
    missing = []
    for group in ("created", "modified"):
        for key in inv[group]:
            if key.startswith("by_"):
                missing += [p for p in inv[group][key] if not (ROOT / p).exists()]
    for group in ("restored_by_inverse_patch", "regenerated_by_rerun", "unchanged_verified"):
        missing += [p for p in inv[group]["paths"] if not (ROOT / p).exists()]
    assert not missing, missing


def test_inventory_records_the_d3_prose_count_error():
    inv = _load(INVENTORY)
    correction = inv["d3_prose_count_correction"]
    assert correction["d3_reported"] == "modified 6 files"
    assert correction["d3_actually_listed"] == 7
    assert correction["corrected_d3_modified_paths"] == 4
    assert correction["corrected_d3_restored_paths"] == 2


def test_documentation_exceptions_are_listed_explicitly():
    """Synthetic failure: claiming every B1-D2 path was untouched."""
    inv = _load(INVENTORY)
    assert "with explicitly documented D1/D2 documentation exceptions" in inv["b1_to_d2_statement"]
    assert inv["documentation_exceptions"]["d1"]["paths"]
    assert inv["documentation_exceptions"]["d2"]["paths"]


@pytest.mark.parametrize("relative", ["README.md", "docs/methodology.md"])
def test_no_document_claims_all_b1_to_d2_untouched(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    for forbidden in (
        "B1–D2 artifacts were untouched",
        "B1-D2 artifacts were untouched",
        "all B1–D2 artifacts unchanged",
    ):
        assert forbidden not in text, relative


def test_inventory_records_the_deleted_snapshot():
    inv = _load(INVENTORY)
    assert ".d2_before.json" in inv["deleted"]["paths"]
    assert "cannot be proven" in inv["deleted"]["consequence"]


def test_generated_artifacts_are_gitignored():
    inv = _load(INVENTORY)
    for path in inv["generated_gitignored"]["paths"]:
        completed = subprocess.run(
            ["git", "check-ignore", path], cwd=ROOT, capture_output=True, text=True
        )
        assert completed.returncode == 0, f"{path} is not gitignored"


# ---------------------------------------------------------------------------
# 6. Locked test still unreachable
# ---------------------------------------------------------------------------
def test_locked_test_remains_unopened():
    manifest = _load(ROOT / "docs" / "d3_locked_test_manifest.json")
    assert manifest["locked_test_evaluated"] is False
    assert manifest["locked_test_outcomes_read"] is False
    assert manifest["runner_can_reach_locked_origins"] is False
    results = _load(D3_RESULTS)
    assert results["dataset_flags"]["locked_test_accessed"] is False
    assert results["split"]["locked_test_evaluated"] is False
