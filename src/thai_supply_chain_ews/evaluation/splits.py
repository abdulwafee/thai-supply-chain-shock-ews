"""Time-based train/validation/test splitting.

Implements the `time_based_split` pseudocode from
docs/architecture/data_architecture.md §8 for real. Deliberately contains no
random-row splitting option at all — not even as a parameter — because this
project's restrictions explicitly forbid it (see docs/project_roadmap.md
"Restrictions" and Gate C).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TimeSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


class SplitOrderError(ValueError):
    """Raised when the resulting partitions are not strictly time-ordered."""


def time_based_split(
    df: pd.DataFrame,
    date_column: str,
    train_end,
    validation_end,
    test_end,
) -> TimeSplit:
    """Partition `df` into train/validation/test by `date_column`, strictly time-ordered.

    - train:      date_column <= train_end
    - validation: train_end   <  date_column <= validation_end
    - test:       validation_end < date_column <= test_end

    Raises SplitOrderError in two independent ways: (1) if the boundary
    parameters themselves are not strictly ordered (train_end < validation_end
    < test_end), checked upfront regardless of what data is present — a
    validation partition that happens to be empty for a given DataFrame must
    not let a bad boundary argument silently pass; and (2) as a defensive
    re-check on the resulting partitions once built, matching
    docs/architecture/data_architecture.md §10 rule 10.
    """
    if date_column not in df.columns:
        raise ValueError(f"Missing column: {date_column}")

    if not (train_end < validation_end < test_end):
        raise SplitOrderError(
            f"Split boundaries must satisfy train_end < validation_end < test_end; "
            f"got train_end={train_end}, validation_end={validation_end}, test_end={test_end}"
        )

    dates = df[date_column]
    train = df[dates <= train_end]
    validation = df[(dates > train_end) & (dates <= validation_end)]
    test = df[(dates > validation_end) & (dates <= test_end)]

    if len(train) and len(validation) and train[date_column].max() >= validation[date_column].min():
        raise SplitOrderError(
            f"train max ({train[date_column].max()}) is not before "
            f"validation min ({validation[date_column].min()})"
        )
    if len(validation) and len(test) and validation[date_column].max() >= test[date_column].min():
        raise SplitOrderError(
            f"validation max ({validation[date_column].max()}) is not before "
            f"test min ({test[date_column].min()})"
        )

    return TimeSplit(train=train, validation=validation, test=test)


# --- Task B4: preregistered walk-forward split plan -------------------------
# Appended, not replacing `time_based_split` above — that generic utility is
# still the enforcement primitive for ordinary train/validation/test work. What
# follows loads the PREREGISTERED plan in configs/evaluation_splits.yaml and
# exposes it as an object the harness can query.

from pathlib import Path  # noqa: E402

import yaml  # noqa: E402

DEFAULT_SPLIT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "evaluation_splits.yaml"
)


class LockedTestAccessError(RuntimeError):
    """An attempt was made to evaluate the reserved final test period.

    B4 reserves the locked test and produces only a manifest for it. There is no
    flag, argument, or default path in the B4 runner that evaluates it —
    unlocking is a later, explicit task.
    """


def month_range(first: str, last: str) -> list[str]:
    """Inclusive list of first-of-month ISO strings."""
    from datetime import date

    start, end = date.fromisoformat(str(first)), date.fromisoformat(str(last))
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(date(year, month, 1).isoformat())
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return months


def add_months(iso_month: str, delta: int) -> str:
    from datetime import date

    d = date.fromisoformat(str(iso_month))
    total = d.year * 12 + (d.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1).isoformat()


@dataclass(frozen=True)
class WalkForwardPlan:
    config: dict

    @property
    def harness_version(self) -> str:
        return self.config["evaluation_harness_version"]

    @property
    def horizons(self) -> list[int]:
        return [int(h) for h in self.config["horizons_months"]]

    @property
    def development_origins(self) -> list[str]:
        dev = self.config["development"]
        return month_range(dev["first_origin"], dev["last_origin"])

    @property
    def purge_origins(self) -> list[str]:
        purge = self.config["purge_buffer"]
        return month_range(purge["first_origin"], purge["last_origin"])

    def locked_test_origins(self, horizon: int) -> list[str]:
        spec = self.config["locked_test"]["horizons"][int(horizon)]
        return month_range(spec["first_origin"], spec["last_origin"])

    def block_for_origin(self, origin: str) -> str:
        for block in self.config["development"]["blocks"]:
            if str(block["first_origin"]) <= origin <= str(block["last_origin"]):
                return block["name"]
        return "OUT_OF_DEVELOPMENT"

    def assert_not_locked_test(self, origins) -> None:
        """Guard: refuse to proceed if any origin falls in the reserved period."""
        locked = set()
        for horizon in self.horizons:
            locked.update(self.locked_test_origins(horizon))
        offending = sorted(set(str(o) for o in origins) & locked)
        if offending:
            raise LockedTestAccessError(
                f"{len(offending)} origin(s) fall inside the reserved locked test period "
                f"(first: {offending[0]}). B4 reserves this period and does not evaluate it."
            )


def load_walk_forward_plan(path: Path | None = None) -> WalkForwardPlan:
    path = Path(path) if path is not None else DEFAULT_SPLIT_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation split config not found: {path}")
    return WalkForwardPlan(config=yaml.safe_load(path.read_text(encoding="utf-8")))
