"""Monthly raw production stress (Task B3).

Builds the monthly `mpi_adverse_yoy` table that the Industry Production Stress
Score is derived from.

The adverse-change formula itself is NOT redefined here — it is imported from
`component_diagnostics`, which owns the single implementation validated in Task
B2. Duplicating it across modules is exactly how a sign or unit error creeps
into one copy and not the other.

Naming, used consistently:
  system            : Thai Supply Chain Shock Early Warning System
  predicted outcome : Industry Production Stress Score
  raw stress measure: mpi_adverse_yoy

MPI alone does not measure every dimension of supply-chain disruption, so this
outcome is deliberately not called a comprehensive "Supply Chain Stress Index".
It measures the PRODUCTION CONSEQUENCE that upstream shocks are expected to
cause.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from thai_supply_chain_ews.targets.component_diagnostics import (
    B2InvariantError,
    ComponentSemanticsError,
    mpi_adverse_yoy,
    validate_b1_invariants,
)

__all__ = [
    "B3InvariantError",
    "ComponentSemanticsError",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_PANEL_PATH",
    "MONTHLY_STRESS_COLUMNS",
    "MonthlyStress",
    "build_monthly_stress",
    "load_target_config",
    "mpi_adverse_yoy",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "production_stress_target.yaml"
DEFAULT_PANEL_PATH = PROJECT_ROOT / "data" / "processed" / "industry_month_panel.parquet"

MONTHLY_STRESS_COLUMNS = [
    "reference_month",
    "industry_id",
    "mpi_adverse_yoy",
    "mpi_level",
    "mpi_level_lagged",
    "lag_source_month",
    "raw_stress_unit",
    "source_edition",
    "target_definition_version",
]

# B3InvariantError is an alias so callers can catch one upstream-data error type
# regardless of which task first defined it.
B3InvariantError = B2InvariantError


def load_target_config(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Target config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class MonthlyStress:
    frame: pd.DataFrame
    b1_findings: dict
    config: dict

    @property
    def months(self) -> list[str]:
        return sorted(self.frame["reference_month"].unique().tolist())

    @property
    def industries(self) -> list[str]:
        return sorted(self.frame["industry_id"].unique().tolist())


def build_monthly_stress(
    panel: pd.DataFrame | None = None, config: dict | None = None
) -> MonthlyStress:
    """Build the monthly raw production-stress table.

    Excludes preliminary and non-model-eligible observations. The first 12
    months of each industry have no 12-month lag source and are simply absent —
    never imputed. Extremes are retained as-is: no winsorizing, clipping, or
    automatic removal.
    """
    config = config or load_target_config()
    if panel is None:
        panel = pd.read_parquet(DEFAULT_PANEL_PATH)

    b1_findings = validate_b1_invariants(panel)

    raw_cfg = config["raw_stress"]
    lag = int(raw_cfg["yoy_lag_months"])
    version = config["target_definition_version"]
    unit = raw_cfg["unit"]

    rows: list[dict] = []
    for industry_id, sub in panel.groupby("industry_id", observed=True):
        sub = sub.sort_values("reference_month", kind="mergesort").reset_index(drop=True)
        months = [str(m) for m in sub["reference_month"]]
        mpi = sub["mpi_level"].to_numpy(dtype=float)

        current, lagged = mpi[lag:], mpi[:-lag]
        adverse = mpi_adverse_yoy(current, lagged)  # raises on a bad denominator

        for offset, month in enumerate(months[lag:]):
            idx = offset + lag
            preliminary = bool(
                sub.loc[idx, "mpi_is_preliminary"] or sub.loc[idx, "capu_is_preliminary"]
            )
            eligible = bool(sub.loc[idx, "is_model_eligible"])
            if raw_cfg["exclude_preliminary"] and preliminary:
                continue
            if raw_cfg["require_model_eligible"] and not eligible:
                continue
            rows.append(
                {
                    "reference_month": month,
                    "industry_id": industry_id,
                    "mpi_adverse_yoy": float(adverse[offset]),
                    "mpi_level": float(current[offset]),
                    "mpi_level_lagged": float(lagged[offset]),
                    "lag_source_month": months[idx - lag],
                    "raw_stress_unit": unit,
                    "source_edition": str(sub.loc[idx, "source_edition"]),
                    "target_definition_version": version,
                }
            )

    frame = pd.DataFrame.from_records(rows, columns=MONTHLY_STRESS_COLUMNS)
    frame = frame.sort_values(["industry_id", "reference_month"], kind="mergesort").reset_index(
        drop=True
    )

    _assert_monthly_expectations(frame, raw_cfg)
    return MonthlyStress(frame=frame, b1_findings=b1_findings, config=config)


def _assert_monthly_expectations(frame: pd.DataFrame, raw_cfg: dict) -> None:
    expected = raw_cfg["expected"]
    failures: list[str] = []

    if len(frame) != expected["rows"]:
        failures.append(f"rows: expected {expected['rows']}, found {len(frame)}")
    per_industry = frame.groupby("industry_id", observed=True).size()
    if set(per_industry.unique().tolist()) != {expected["months_per_industry"]}:
        failures.append(
            f"months per industry: expected {expected['months_per_industry']}, "
            f"found {sorted(per_industry.unique().tolist())}"
        )
    months = sorted(frame["reference_month"].unique().tolist())
    if months and months[0] != str(expected["first_month"]):
        failures.append(f"first month: expected {expected['first_month']}, found {months[0]}")
    if months and months[-1] != str(expected["last_month"]):
        failures.append(f"last month: expected {expected['last_month']}, found {months[-1]}")
    if frame["mpi_adverse_yoy"].isna().any():
        failures.append("mpi_adverse_yoy contains nulls")
    if frame.duplicated(subset=["reference_month", "industry_id"]).any():
        failures.append("duplicate (reference_month, industry_id) keys")

    if failures:
        raise B3InvariantError(
            "Monthly raw-stress table does not match the preregistered expectations:\n  - "
            + "\n  - ".join(failures)
        )
