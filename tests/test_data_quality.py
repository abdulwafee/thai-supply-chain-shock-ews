"""Tests for thai_supply_chain_ews.data.validate and .evaluation.metrics.

All input data below is deliberately tiny and abstract (toy dates/values
picked only to exercise the logic) — none of it represents or resembles real
Thai economic data, per this project's restriction against synthetic
datasets standing in for real observations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thai_supply_chain_ews.data.validate import (
    check_available_as_of_after_reference_period,
    check_feature_respects_cutoff,
    check_no_missing_available_as_of,
    check_primary_key_unique,
    check_referential_integrity,
    check_split_boundaries_ordered,
)
from thai_supply_chain_ews.evaluation.metrics import (
    false_alert_rate,
    macro_f1,
    mae,
    missed_event_rate,
    recall_precision_for_levels,
    rmse,
    spearman_correlation,
)

# --- validate.py --------------------------------------------------------


def test_check_primary_key_unique_flags_duplicates():
    df = pd.DataFrame({"id": ["A", "A", "B"], "period": ["p1", "p1", "p1"]})
    violations = check_primary_key_unique(df, ["id", "period"])
    assert violations == [0, 1]


def test_check_primary_key_unique_passes_when_unique():
    df = pd.DataFrame({"id": ["A", "B"], "period": ["p1", "p1"]})
    assert check_primary_key_unique(df, ["id", "period"]) == []


def test_check_referential_integrity_flags_unknown_and_null():
    df = pd.DataFrame({"industry_id": ["IND-01", "IND-99", None]})
    violations = check_referential_integrity(df, "industry_id", {"IND-01", "IND-02"})
    assert violations == [1, 2]


def test_check_no_missing_available_as_of_flags_populated_value_with_null_asof():
    df = pd.DataFrame(
        {
            "mpi_value": [1.0, np.nan, 2.0],
            "mpi_available_as_of": [pd.Timestamp("2020-01-01"), None, None],
        }
    )
    violations = check_no_missing_available_as_of(df, "mpi_value", "mpi_available_as_of")
    assert violations == [2]  # row 1 is fine: value itself is null, nothing to leak


def test_check_available_as_of_after_reference_period_flags_backwards_dates():
    df = pd.DataFrame(
        {
            "reference_period": [pd.Timestamp("2020-03-01"), pd.Timestamp("2020-03-01")],
            "available_as_of": [pd.Timestamp("2020-04-30"), pd.Timestamp("2020-02-01")],
        }
    )
    violations = check_available_as_of_after_reference_period(
        df, "reference_period", "available_as_of"
    )
    assert violations == [1]


def test_check_feature_respects_cutoff_flags_future_leak():
    df = pd.DataFrame(
        {
            "available_as_of": [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-03-01")],
            "cutoff_date": [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-01-31")],
        }
    )
    violations = check_feature_respects_cutoff(df, "available_as_of", "cutoff_date")
    assert violations == [1]


def test_check_split_boundaries_ordered_detects_overlap():
    train = pd.Series(pd.to_datetime(["2020-01-01", "2020-06-01"]))
    validation = pd.Series(pd.to_datetime(["2020-05-01", "2020-08-01"]))  # overlaps train
    test = pd.Series(pd.to_datetime(["2020-09-01"]))
    violations = check_split_boundaries_ordered(train, validation, test)
    assert len(violations) == 1
    assert "train max" in violations[0]


def test_check_split_boundaries_ordered_passes_when_clean():
    train = pd.Series(pd.to_datetime(["2020-01-01", "2020-03-01"]))
    validation = pd.Series(pd.to_datetime(["2020-04-01", "2020-05-01"]))
    test = pd.Series(pd.to_datetime(["2020-06-01"]))
    assert check_split_boundaries_ordered(train, validation, test) == []


# --- evaluation/metrics.py ------------------------------------------------


def test_mae_rmse_basic():
    y_true = [1.0, 2.0, 3.0]
    y_pred = [1.0, 2.0, 5.0]
    assert mae(y_true, y_pred) == pytest.approx(2.0 / 3.0)
    assert rmse(y_true, y_pred) == pytest.approx((4.0 / 3.0) ** 0.5)


def test_spearman_perfect_correlation():
    assert spearman_correlation([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_spearman_perfect_negative_correlation():
    assert spearman_correlation([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_recall_precision_for_levels():
    y_true = ["Normal", "Watch", "High", "Severe"]
    y_pred = ["Normal", "Normal", "High", "Watch"]
    result = recall_precision_for_levels(y_true, y_pred, positive_levels=("High", "Severe"))
    # true positives among {High, Severe}: only "High" row (index 2) predicted High -> tp=1
    # "Severe" row predicted "Watch" -> false negative
    assert result["tp"] == 1
    assert result["fn"] == 1
    assert result["fp"] == 0


def test_macro_f1_perfect_prediction_is_one():
    levels = ["Normal", "Watch", "High", "Severe"]
    assert macro_f1(levels, levels) == pytest.approx(1.0)


def test_false_alert_rate():
    y_true = ["Normal", "Normal", "Watch"]
    y_pred = ["Normal", "High", "Watch"]
    assert false_alert_rate(y_true, y_pred) == pytest.approx(0.5)


def test_missed_event_rate():
    y_true = ["Severe", "Severe", "Normal"]
    y_pred = ["Watch", "Severe", "Normal"]
    assert missed_event_rate(y_true, y_pred) == pytest.approx(0.5)
