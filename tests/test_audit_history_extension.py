"""Tests for scripts/audit_history_extension.py — the intersection-arithmetic
correction and per-industry bridge-feasibility logic.

All fixture data is synthetic (small toy division-number sets), never real
OIE figures, consistent with this project's restriction against fabricated
observations. These tests exist specifically to prevent the regression this
task was raised to fix: a manually-typed intersection count that silently
drifts from what the actual division lists support.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_history_extension.py"
_spec = importlib.util.spec_from_file_location("audit_history_extension", SCRIPT_PATH)
hist = importlib.util.module_from_spec(_spec)
sys.modules["audit_history_extension"] = hist
_spec.loader.exec_module(hist)


# --- real set-based intersection arithmetic --------------------------------


def test_pairwise_comparison_intersection_count_equals_list_length():
    """The one invariant this whole correction task is about: the reported
    count must always equal len() of the reported list, by construction,
    never typed in separately.
    """
    result = hist.compute_pairwise_comparison(
        "edition_a", [10, 11, 12, 13], "edition_b", [11, 12, 13, 14]
    )
    assert result["intersection_count"] == len(result["intersection"])
    assert result["intersection"] == [11, 12, 13]
    assert result["only_in_a"] == [10]
    assert result["only_in_b"] == [14]


def test_pairwise_comparison_reproduces_the_corrected_real_finding():
    """Regression test pinned to the actual real-data finding this task
    corrected: current (22 divisions, missing 18+33) vs. the 2016-based
    edition (21 divisions, missing 16+18+33) intersect at exactly 21, not
    18 or 19 as an earlier, manually-typed version of the report claimed.
    """
    current_divisions = sorted(set(range(10, 34)) - {18, 33})  # 22 divisions
    older_divisions = sorted(set(range(10, 34)) - {16, 18, 33})  # 21 divisions
    result = hist.compute_pairwise_comparison(
        "current", current_divisions, "2016_edition", older_divisions
    )
    assert result["intersection_count"] == 21
    assert result["only_in_a"] == [16]
    assert result["only_in_b"] == []


def test_pairwise_comparison_is_symmetric_in_content_if_not_in_labeling():
    a = hist.compute_pairwise_comparison("x", [10, 11, 12], "y", [11, 12, 13])
    b = hist.compute_pairwise_comparison("y", [11, 12, 13], "x", [10, 11, 12])
    assert a["intersection"] == b["intersection"]
    assert a["only_in_a"] == b["only_in_b"]
    assert a["only_in_b"] == b["only_in_a"]


# --- per-industry bridge feasibility ----------------------------------------


def _make_audit(divisions_found: list[int]) -> hist.EditionComponentAudit:
    return hist.EditionComponentAudit(
        edition_id="toy",
        component="MPI",
        file_path="toy.xlsx",
        classification_label="TSIC",
        divisions_found=sorted(divisions_found),
    )


def test_industry_bridge_flags_ind03_style_composition_change(monkeypatch):
    """The exact scenario this task named explicitly: an industry whose
    required set is {16, 17, 18}, present as {16, 17} in a newer edition but
    only {17} in an older one. This must NOT be classified as a clean
    bridge, regardless of each edition's own any/full/partial coverage.
    """
    monkeypatch.setattr(hist, "INDUSTRY_TSIC_DIVISIONS", {"IND-03": [16, 17, 18]})
    table = hist.build_industry_bridge_table(
        "current", _make_audit([16, 17, 19]), "older", _make_audit([17, 19])
    )
    assert table["IND-03"]["present_by_edition"]["current"] == [16, 17]
    assert table["IND-03"]["present_by_edition"]["older"] == [17]
    assert table["IND-03"]["composition_consistent"] is False
    assert table["IND-03"]["overlap_validated"] is False
    assert table["IND-03"]["bridge_approved"] is False
    assert "changes meaning" in table["IND-03"]["reason_if_blocked"]


def test_industry_bridge_allows_consistently_partial_coverage(monkeypatch):
    """The IND-12-style case: a division (e.g. 33) missing from EVERY
    edition consistently is not a composition change — the present set is
    identical across editions, so composition_consistent is True (a bridge
    remains structurally possible, pending empirical validation), unlike the
    IND-03 case above.
    """
    monkeypatch.setattr(hist, "INDUSTRY_TSIC_DIVISIONS", {"IND-12": [31, 32, 33]})
    table = hist.build_industry_bridge_table(
        "current", _make_audit([31, 32]), "older", _make_audit([31, 32])
    )
    assert table["IND-12"]["present_by_edition"]["current"] == [31, 32]
    assert table["IND-12"]["present_by_edition"]["older"] == [31, 32]
    assert table["IND-12"]["composition_consistent"] is True
    assert table["IND-12"]["classification_compatible"] is True  # both "TSIC" by default
    # Composition being consistent does NOT imply the bridge is approved —
    # that requires real overlap evidence this structural function never computes.
    assert table["IND-12"]["overlap_validated"] is False
    assert table["IND-12"]["bridge_approved"] is False
    assert table["IND-12"]["reason_if_blocked"] is None


def test_industry_bridge_flags_zero_coverage_as_not_possible(monkeypatch):
    monkeypatch.setattr(hist, "INDUSTRY_TSIC_DIVISIONS", {"IND-X": [40, 41]})
    table = hist.build_industry_bridge_table(
        "current", _make_audit([10, 11]), "older", _make_audit([10, 11])
    )
    assert table["IND-X"]["coverage_by_edition"] == {"current": "none", "older": "none"}
    assert table["IND-X"]["composition_consistent"] is False
    assert table["IND-X"]["bridge_approved"] is False


def test_industry_bridge_marks_classification_unresolved_for_isic_pair():
    """The exact requirement this task states explicitly: identical division
    numbers must NOT imply classification compatibility when the labels
    differ (TSIC vs. ISIC). `classification_compatible` must be the string
    "unresolved", not True and not False.
    """
    tsic_audit = hist.EditionComponentAudit(
        edition_id="tsic_ed",
        component="MPI",
        file_path="tsic.xlsx",
        classification_label="TSIC",
        divisions_found=[10, 11, 19],
    )
    isic_audit = hist.EditionComponentAudit(
        edition_id="isic_ed",
        component="MPI",
        file_path="isic.xlsx",
        classification_label="ISIC",
        divisions_found=[10, 11, 19],  # identical numbers on purpose
    )
    table = hist.build_industry_bridge_table("tsic_ed", tsic_audit, "isic_ed", isic_audit)
    for entry in table.values():
        assert entry["classification_compatible"] == "unresolved"
        assert entry["bridge_approved"] is False
    # IND-01 requires {10, 11}, present identically in both -> composition
    # is consistent, but classification incompatibility still blocks it.
    assert table["IND-01"]["composition_consistent"] is True
    assert "unresolved" in table["IND-01"]["reason_if_blocked"] or (
        "Classification label differs" in table["IND-01"]["reason_if_blocked"]
    )


# --- division-label generalization (TSIC vs. ISIC) --------------------------


def test_find_division_label_column_generalized_detects_isic():
    rows = [
        [None, None, None],
        [None, None, "ISIC : 10 การผลิตผลิตภัณฑ์อาหาร"],
    ]
    col, label_type = hist.find_division_label_column_generalized(rows)
    assert col == 2
    assert label_type == "ISIC"


def test_find_division_label_column_generalized_detects_tsic():
    rows = [
        [None, None, None],
        [None, "TSIC : 19 การผลิตถ่านโค้ก"],
    ]
    col, label_type = hist.find_division_label_column_generalized(rows)
    assert col == 1
    assert label_type == "TSIC"


def test_find_division_label_column_generalized_raises_when_neither_found():
    import pytest

    rows = [[None, "some unrelated text"], [None, None]]
    with pytest.raises(ValueError, match="TSIC- or ISIC-labeled"):
        hist.find_division_label_column_generalized(rows)
