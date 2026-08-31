"""Generic, reusable data-quality and leakage-check utilities.

These functions are intentionally generic — they operate on any DataFrame
with the named columns, independent of which source or layer it came from.
This is infrastructure ("automated tests for data quality and leakage" per
the project's confirmed code organization), not data-ingestion or
feature/target business logic, which is why it is implemented now while
`ingest.py`, `build_panel.py`, and the `targets`/`features`/`models`
subpackages remain stubs.

Each function returns the list of violating row indices (empty list = pass)
rather than raising, so callers can decide whether a violation is fatal.
See docs/architecture/data_architecture.md §10 for the full validation-rule
list these functions implement a subset of.
"""

from __future__ import annotations

import pandas as pd


def check_primary_key_unique(df: pd.DataFrame, key_columns: list[str]) -> list[int]:
    """Rule 1: the given columns must uniquely identify each row.

    Returns the positional index of every row that participates in a
    duplicate key (all occurrences, not just the second-and-later ones).
    """
    if not key_columns:
        raise ValueError("key_columns must not be empty")
    missing = [c for c in key_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing key columns: {missing}")
    duplicated_mask = df.duplicated(subset=key_columns, keep=False)
    return df.index[duplicated_mask].tolist()


def check_referential_integrity(df: pd.DataFrame, fk_column: str, valid_ids: set[str]) -> list[int]:
    """Rule 2: every value in `fk_column` must exist in `valid_ids`.

    Null values are treated as violations too — a foreign key column should
    not be silently null when the row is meant to reference something.
    """
    if fk_column not in df.columns:
        raise ValueError(f"Missing column: {fk_column}")
    is_invalid = ~df[fk_column].isin(valid_ids) | df[fk_column].isna()
    return df.index[is_invalid].tolist()


def check_no_missing_available_as_of(
    df: pd.DataFrame, value_column: str, available_as_of_column: str
) -> list[int]:
    """Rule 4: a populated value column must never have a null `*_available_as_of`.

    This is the direct implementation of the project restriction "do not
    treat a missing release_date as identical to reference_period" — a
    missing availability date is a validation failure, not something to be
    silently defaulted.
    """
    for col in (value_column, available_as_of_column):
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
    value_present = df[value_column].notna()
    asof_missing = df[available_as_of_column].isna()
    return df.index[value_present & asof_missing].tolist()


def check_available_as_of_after_reference_period(
    df: pd.DataFrame,
    reference_period_column: str,
    available_as_of_column: str,
) -> list[int]:
    """Rule 3 (partial): `available_as_of` must not precede `reference_period`.

    A value cannot be available before the period it describes has even
    started. This does not check against `release_date` (the fuller rule
    also involves the end of the reference period and release_date, which
    are not always both present) — it is a minimal, always-checkable subset.
    """
    for col in (reference_period_column, available_as_of_column):
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
    both_present = df[reference_period_column].notna() & df[available_as_of_column].notna()
    violates = both_present & (df[available_as_of_column] < df[reference_period_column])
    return df.index[violates].tolist()


def check_feature_respects_cutoff(
    df: pd.DataFrame,
    available_as_of_column: str,
    cutoff_column: str,
) -> list[int]:
    """Rule 5: every feature value's `available_as_of` must be <= its row's `cutoff_date`.

    This is the automatable leakage audit for the features table — it checks
    the actual data, not just the design intent of the point-in-time builder
    in docs/architecture/data_architecture.md §8.
    """
    for col in (available_as_of_column, cutoff_column):
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
    both_present = df[available_as_of_column].notna() & df[cutoff_column].notna()
    violates = both_present & (df[available_as_of_column] > df[cutoff_column])
    return df.index[violates].tolist()


def check_split_boundaries_ordered(
    train_dates: pd.Series, validation_dates: pd.Series, test_dates: pd.Series
) -> list[str]:
    """Rule 10: max(train) < min(validation) < min(test), checked explicitly.

    Returns a list of human-readable violation messages (empty = pass).
    Deliberately does not check test's max against anything — a test set may
    legitimately be shorter or longer than the other two.
    """
    violations: list[str] = []
    if len(train_dates) and len(validation_dates):
        if train_dates.max() >= validation_dates.min():
            violations.append(
                f"train max ({train_dates.max()}) is not before validation min "
                f"({validation_dates.min()})"
            )
    if len(validation_dates) and len(test_dates):
        if validation_dates.max() >= test_dates.min():
            violations.append(
                f"validation max ({validation_dates.max()}) is not before test min "
                f"({test_dates.min()})"
            )
    return violations
