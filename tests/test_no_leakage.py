"""Leakage-focused tests: point-in-time cutoff enforcement and time-based splitting.

Distinct from test_data_quality.py's broader validation-rule coverage: this
file specifically targets the leakage-prevention mechanisms this project's
architecture (docs/architecture/data_architecture.md §8, §10) treats as
non-negotiable — no future data in a feature row, no random splitting, no
overlapping split boundaries.

As in the other test files, all dates/values below are toy fixtures, not
real observations.
"""

from __future__ import annotations

import pandas as pd
import pytest

from thai_supply_chain_ews.data.validate import check_feature_respects_cutoff
from thai_supply_chain_ews.evaluation.splits import (
    SplitOrderError,
    time_based_split,
)


def test_time_based_split_produces_correct_partitions():
    df = pd.DataFrame(
        {
            "prediction_date": pd.to_datetime(
                ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01", "2020-05-01"]
            ),
            "value": [1, 2, 3, 4, 5],
        }
    )
    result = time_based_split(
        df,
        date_column="prediction_date",
        train_end=pd.Timestamp("2020-02-01"),
        validation_end=pd.Timestamp("2020-03-01"),
        test_end=pd.Timestamp("2020-05-01"),
    )
    assert list(result.train["value"]) == [1, 2]
    assert list(result.validation["value"]) == [3]
    assert list(result.test["value"]) == [4, 5]


def test_time_based_split_never_shuffles_or_randomizes():
    """Row order and membership must be fully determined by the date column alone.

    Running the split twice on the same input must give identical output —
    unlike a random split, there is no seed to vary.
    """
    df = pd.DataFrame(
        {
            "prediction_date": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]),
            "value": [10, 20, 30],
        }
    )
    kwargs = dict(
        date_column="prediction_date",
        train_end=pd.Timestamp("2020-01-01"),
        validation_end=pd.Timestamp("2020-02-01"),
        test_end=pd.Timestamp("2020-03-01"),
    )
    first = time_based_split(df, **kwargs)
    second = time_based_split(df, **kwargs)
    pd.testing.assert_frame_equal(first.train, second.train)
    pd.testing.assert_frame_equal(first.validation, second.validation)
    pd.testing.assert_frame_equal(first.test, second.test)


def test_time_based_split_raises_on_overlapping_boundaries():
    """A caller who passes overlapping train/validation boundaries must get an
    explicit error, not silently-overlapping partitions.
    """
    df = pd.DataFrame(
        {
            "prediction_date": pd.to_datetime(["2020-01-01", "2020-01-15", "2020-02-01"]),
            "value": [1, 2, 3],
        }
    )
    with pytest.raises(SplitOrderError):
        time_based_split(
            df,
            date_column="prediction_date",
            train_end=pd.Timestamp("2020-01-20"),  # deliberately overlaps validation below
            validation_end=pd.Timestamp("2020-01-10"),
            test_end=pd.Timestamp("2020-02-01"),
        )


def test_feature_row_that_reads_the_future_is_flagged():
    """A feature row whose value became available AFTER its own cutoff_date
    is exactly the look-ahead-bias scenario this project's architecture
    (§8) is built to prevent — this asserts the check actually catches it,
    not just that the design document says it should.
    """
    leaky_features = pd.DataFrame(
        {
            "industry_id": ["IND-01", "IND-01"],
            "prediction_date": pd.to_datetime(["2020-01-31", "2020-02-29"]),
            "cutoff_date": pd.to_datetime(["2020-01-31", "2020-02-29"]),
            # second row's value was "available" a month after its own cutoff:
            "some_feature_asof": pd.to_datetime(["2020-01-31", "2020-03-31"]),
        }
    )
    violations = check_feature_respects_cutoff(leaky_features, "some_feature_asof", "cutoff_date")
    assert violations == [1]


def test_feature_row_that_respects_cutoff_is_not_flagged():
    clean_features = pd.DataFrame(
        {
            "cutoff_date": pd.to_datetime(["2020-01-31", "2020-02-29"]),
            "some_feature_asof": pd.to_datetime(["2020-01-15", "2020-02-28"]),
        }
    )
    violations = check_feature_respects_cutoff(clean_features, "some_feature_asof", "cutoff_date")
    assert violations == []
