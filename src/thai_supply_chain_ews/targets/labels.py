"""Forecast target labels for the Industry Production Stress Score (Task B3).

Builds RAW horizon labels only. These are static: they need no fitted statistical
calibration, so they can be persisted once and reused across folds.

Calibrated scores are deliberately NOT built here. The production workflow is:

    1. build raw horizon labels            (this module)
    2. define a temporal training fold
    3. fit IndustryStressCalibrator on permitted history only
    4. transform training and evaluation targets with that FROZEN calibrator
    5. derive risk levels from the frozen scores

Producing one full-sample calibrated score and calling it leakage-safe would
collapse steps 2-4 into a single leak.

Horizon semantics, stated once:
  * A row represents information available at forecast-origin month t.
  * The origin month itself must carry a valid observed mpi_adverse_yoy.
  * target_raw_1m(i,t) = mpi_adverse_yoy(i, t+1)
  * target_raw_3m(i,t) = max over t+1..t+3 — "the worst observed production
    stress during the next three months".
  * A window that would reach a preliminary month is DROPPED, never truncated:
    a 3-month maximum computed over 2 available months is a different quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

__all__ = [
    "LABEL_COLUMNS",
    "ForecastLabels",
    "add_months",
    "build_forecast_labels",
]

LABEL_COLUMNS = [
    "forecast_origin_month",
    "industry_id",
    "horizon_months",
    "target_window_start",
    "target_window_end",
    "target_peak_month",
    "target_peak_lead_month",
    "target_raw_value",
    "target_raw_unit",
    "target_definition_version",
]


def add_months(iso_month: str, delta: int) -> str:
    d = date.fromisoformat(str(iso_month))
    total = d.year * 12 + (d.month - 1) + delta
    return date(total // 12, total % 12 + 1, 1).isoformat()


@dataclass
class ForecastLabels:
    frame: pd.DataFrame
    config: dict

    def for_horizon(self, horizon: int) -> pd.DataFrame:
        return self.frame[self.frame["horizon_months"] == horizon]


def build_forecast_labels(
    monthly_stress: pd.DataFrame, config: dict
) -> ForecastLabels:
    """Build the combined long-format raw label table for all configured horizons."""
    unit = config["raw_stress"]["unit"]
    version = config["target_definition_version"]
    excluded_months = {str(m) for m in config.get("excluded_target_months", [])}

    rows: list[dict] = []
    for industry_id, sub in monthly_stress.groupby("industry_id", observed=True):
        sub = sub.sort_values("reference_month", kind="mergesort")
        by_month = dict(
            zip(
                sub["reference_month"].astype(str),
                sub["mpi_adverse_yoy"].astype(float),
                strict=True,
            )
        )
        available = set(by_month)

        for horizon in config["horizons_months"]:
            offsets = [int(o) for o in config["horizons"][horizon]["window_offsets"]]
            for origin in sorted(available):
                window_months = [add_months(origin, o) for o in offsets]
                # every window month must be a real, non-preliminary observation
                if any(m in excluded_months or m not in available for m in window_months):
                    continue
                window_values = [by_month[m] for m in window_months]

                peak_value = max(window_values)
                # deterministic tie rule: earliest peak month wins
                peak_index = window_values.index(peak_value)
                peak_month = window_months[peak_index]

                rows.append(
                    {
                        "forecast_origin_month": origin,
                        "industry_id": str(industry_id),
                        "horizon_months": int(horizon),
                        "target_window_start": window_months[0],
                        "target_window_end": window_months[-1],
                        "target_peak_month": peak_month,
                        "target_peak_lead_month": offsets[peak_index],
                        "target_raw_value": float(peak_value),
                        "target_raw_unit": unit,
                        "target_definition_version": version,
                    }
                )

    frame = pd.DataFrame.from_records(rows, columns=LABEL_COLUMNS)
    frame = frame.sort_values(
        ["horizon_months", "industry_id", "forecast_origin_month"], kind="mergesort"
    ).reset_index(drop=True)

    _assert_label_expectations(frame, config)
    return ForecastLabels(frame=frame, config=config)


def _assert_label_expectations(frame: pd.DataFrame, config: dict) -> None:
    from thai_supply_chain_ews.targets.production_stress import B3InvariantError

    failures: list[str] = []
    for horizon in config["horizons_months"]:
        expected = config["horizons"][horizon]["expected"]
        sub = frame[frame["horizon_months"] == horizon]
        if len(sub) != expected["rows"]:
            failures.append(f"h={horizon} rows: expected {expected['rows']}, found {len(sub)}")
        per_industry = sub.groupby("industry_id", observed=True).size()
        if set(per_industry.unique().tolist()) != {expected["origins_per_industry"]}:
            failures.append(
                f"h={horizon} origins per industry: expected "
                f"{expected['origins_per_industry']}, found "
                f"{sorted(per_industry.unique().tolist())}"
            )
        origins = sorted(sub["forecast_origin_month"].unique().tolist())
        if origins and origins[0] != str(expected["first_origin"]):
            failures.append(
                f"h={horizon} first origin: expected {expected['first_origin']}, found {origins[0]}"
            )
        if origins and origins[-1] != str(expected["last_origin"]):
            failures.append(
                f"h={horizon} last origin: expected {expected['last_origin']}, found {origins[-1]}"
            )

    total_expected = config["expected_combined_label_rows"]
    if len(frame) != total_expected:
        failures.append(f"combined rows: expected {total_expected}, found {len(frame)}")

    excluded = {str(m) for m in config.get("excluded_target_months", [])}
    for column in ("target_window_start", "target_window_end", "target_peak_month"):
        offending = sorted(set(frame[column]) & excluded)
        if offending:
            failures.append(f"{column} reaches an excluded month: {offending}")

    if frame.duplicated(
        subset=["forecast_origin_month", "industry_id", "horizon_months"]
    ).any():
        failures.append("duplicate (origin, industry, horizon) keys")

    if failures:
        raise B3InvariantError(
            "Forecast label table does not match the preregistered expectations:\n  - "
            + "\n  - ".join(failures)
        )
