"""Industry-month panel construction (Task B1).

Aggregates the division-month table into a balanced 12-industry monthly panel
using each component's OFFICIAL OIE source weights, renormalized within the
industry. Equal division weights are never used — not as a default, not as a
fallback. A missing or duplicated constituent division is an error, not a
silently smaller denominator.

This module deliberately stops at levels. It does not compute MoM, YoY, robust
z-scores, stress scores, forecast targets, or risk levels — those belong to
later tasks and would be leakage-relevant transformations that need their own
design gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from thai_supply_chain_ews.data.ingest import (
    DivisionMonthTable,
    build_division_month_table,
)
from thai_supply_chain_ews.data.taxonomy import IndustryTaxonomy, load_taxonomy

__all__ = [
    "AggregationError",
    "IndustryPanel",
    "PANEL_COLUMNS",
    "aggregate_industry_value",
    "build_industry_panel",
    "write_outputs",
]

PANEL_COLUMNS = [
    "reference_month",
    "industry_id",
    "industry_name_en",
    "industry_name_th",
    "mpi_level",
    "capacity_utilization_rate",
    "mpi_is_preliminary",
    "capu_is_preliminary",
    "is_model_eligible",
    "source_edition",
    "source_base_year",
    "mpi_source_sha256",
    "capu_source_sha256",
    "retrieved_at",
    "data_quality_flag",
]

QUALITY_OK = "ok"
QUALITY_PRELIMINARY = "preliminary"


class AggregationError(ValueError):
    """A required division-month record is missing, duplicated, or unusable."""


@dataclass(frozen=True)
class AggregationResult:
    value: float
    effective_divisions: tuple[int, ...]
    normalized_weights: dict[int, float]
    is_preliminary: bool


def aggregate_industry_value(
    records: pd.DataFrame,
    industry_id: str,
    required_divisions: tuple[int, ...],
    reference_month,
    component: str,
) -> AggregationResult:
    """Official-weight aggregation for one industry-month-component.

    Weights are renormalized to sum to 1 across exactly the required divisions.
    A single-division industry therefore receives weight 1.0 and reduces to the
    division value itself — by the same code path, not a special case that could
    drift.
    """
    subset = records[records["tsic_division"].isin(required_divisions)]

    duplicated = subset.duplicated(subset=["tsic_division"])
    if duplicated.any():
        dups = sorted(subset.loc[duplicated, "tsic_division"].unique())
        raise AggregationError(
            f"{industry_id} {component} {reference_month}: duplicate division rows {dups}."
        )

    present = set(subset["tsic_division"])
    missing = sorted(set(required_divisions) - present)
    if missing:
        raise AggregationError(
            f"{industry_id} {component} {reference_month}: missing division(s) {missing} — "
            "refusing to aggregate over a partial set."
        )

    if subset["source_value"].isna().any():
        blank = sorted(subset.loc[subset["source_value"].isna(), "tsic_division"])
        raise AggregationError(
            f"{industry_id} {component} {reference_month}: division(s) {blank} have no "
            "numeric value — refusing to impute."
        )

    weights = dict(zip(subset["tsic_division"], subset["source_weight"], strict=True))
    total = sum(weights.values())
    if total <= 0:
        raise AggregationError(
            f"{industry_id} {component} {reference_month}: non-positive total weight {total}."
        )
    normalized = {int(d): float(w) / float(total) for d, w in weights.items()}

    values = dict(zip(subset["tsic_division"], subset["source_value"], strict=True))
    value = sum(normalized[int(d)] * float(v) for d, v in values.items())

    return AggregationResult(
        value=float(value),
        effective_divisions=tuple(sorted(int(d) for d in required_divisions)),
        normalized_weights=normalized,
        is_preliminary=bool(subset["is_preliminary"].any()),
    )


@dataclass
class IndustryPanel:
    frame: pd.DataFrame
    weights_used: list[dict] = field(default_factory=list)
    taxonomy_version: str = ""
    division_table: DivisionMonthTable | None = None

    @property
    def model_eligible_frame(self) -> pd.DataFrame:
        return self.frame[self.frame["is_model_eligible"]]


def build_industry_panel(
    division_table: DivisionMonthTable | None = None,
    taxonomy: IndustryTaxonomy | None = None,
) -> IndustryPanel:
    """Build the balanced industry-month panel.

    `is_model_eligible` is False when either component is preliminary, a
    required value is missing, a division is missing, a duplicate exists, or
    source integrity failed. Preliminary rows are RETAINED — excluded from
    model-eligible output, never dropped from the panel.
    """
    division_table = division_table or build_division_month_table()
    taxonomy = taxonomy or load_taxonomy()
    frame = division_table.frame

    reported = set(frame["tsic_division"].unique())
    mapped = set(taxonomy.all_divisions)
    if mapped != reported:
        raise AggregationError(
            "Taxonomy does not match the divisions actually reported by the source. "
            f"Mapped-but-absent: {sorted(mapped - reported)}. "
            f"Reported-but-unmapped: {sorted(reported - mapped)}."
        )

    provenance = division_table.provenance
    mpi_prov = provenance.get("MPI", {})
    capu_prov = provenance.get("CapU", {})

    by_component = {
        component: sub for component, sub in frame.groupby("component", observed=True)
    }
    months = sorted(frame["reference_month"].unique())

    rows: list[dict] = []
    weights_used: list[dict] = []

    for month in months:
        month_slices = {
            component: sub[sub["reference_month"] == month]
            for component, sub in by_component.items()
        }
        for industry_id in taxonomy.industry_ids:
            industry = taxonomy.industries[industry_id]
            values: dict[str, float | None] = {}
            preliminary: dict[str, bool] = {}
            failures: list[str] = []

            for component in ("MPI", "CapU"):
                records = month_slices.get(component)
                if records is None or records.empty:
                    values[component] = None
                    preliminary[component] = False
                    failures.append(f"{component}:no_records")
                    continue
                try:
                    result = aggregate_industry_value(
                        records, industry_id, industry.tsic_divisions, month, component
                    )
                except AggregationError as exc:
                    values[component] = None
                    preliminary[component] = False
                    failures.append(f"{component}:{type(exc).__name__}")
                    continue
                values[component] = result.value
                preliminary[component] = result.is_preliminary
                weights_used.append(
                    {
                        "reference_month": month,
                        "industry_id": industry_id,
                        "component": component,
                        "effective_divisions": list(result.effective_divisions),
                        "normalized_weights": {
                            str(k): v for k, v in sorted(result.normalized_weights.items())
                        },
                    }
                )

            any_preliminary = bool(preliminary.get("MPI") or preliminary.get("CapU"))
            complete = values.get("MPI") is not None and values.get("CapU") is not None
            eligible = complete and not any_preliminary and not failures

            if failures:
                flag = ";".join(sorted(failures))
            elif any_preliminary:
                flag = QUALITY_PRELIMINARY
            else:
                flag = QUALITY_OK

            rows.append(
                {
                    "reference_month": month,
                    "industry_id": industry_id,
                    "industry_name_en": industry.name_en,
                    "industry_name_th": industry.name_th,
                    "mpi_level": values.get("MPI"),
                    "capacity_utilization_rate": values.get("CapU"),
                    "mpi_is_preliminary": bool(preliminary.get("MPI", False)),
                    "capu_is_preliminary": bool(preliminary.get("CapU", False)),
                    "is_model_eligible": bool(eligible),
                    "source_edition": mpi_prov.get("source_edition"),
                    "source_base_year": mpi_prov.get("source_base_year"),
                    "mpi_source_sha256": mpi_prov.get("source_sha256"),
                    "capu_source_sha256": capu_prov.get("source_sha256"),
                    "retrieved_at": mpi_prov.get("retrieved_at"),
                    "data_quality_flag": flag,
                }
            )

    panel = pd.DataFrame.from_records(rows, columns=PANEL_COLUMNS)
    panel = _cast_panel_types(panel)
    panel = panel.sort_values(["reference_month", "industry_id"], kind="mergesort").reset_index(
        drop=True
    )

    duplicated = panel.duplicated(subset=["reference_month", "industry_id"])
    if duplicated.any():
        raise AggregationError(
            "Duplicate (reference_month, industry_id) keys:\n"
            f"{panel.loc[duplicated, ['reference_month', 'industry_id']]}"
        )

    return IndustryPanel(
        frame=panel,
        weights_used=weights_used,
        taxonomy_version=taxonomy.version,
        division_table=division_table,
    )


def _cast_panel_types(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["reference_month"] = pd.to_datetime(frame["reference_month"]).dt.date
    for col in ("industry_id", "industry_name_en", "industry_name_th", "source_edition",
                "mpi_source_sha256", "capu_source_sha256", "retrieved_at",
                "data_quality_flag"):
        frame[col] = frame[col].astype("string")
    for col in ("mpi_level", "capacity_utilization_rate"):
        frame[col] = frame[col].astype("float64")
    for col in ("mpi_is_preliminary", "capu_is_preliminary", "is_model_eligible"):
        frame[col] = frame[col].astype("bool")
    frame["source_base_year"] = frame["source_base_year"].astype("int16")
    return frame


def write_outputs(
    panel: IndustryPanel,
    processed_dir: Path | None = None,
    write_csv_preview: bool = True,
) -> dict[str, Path]:
    """Write typed Parquet outputs (plus an optional small CSV preview).

    Generated datasets live under data/processed/, which is git-ignored — only
    schemas, metadata, fixtures, docs and code are committed.
    """
    root = Path(__file__).resolve().parents[3]
    processed_dir = processed_dir or root / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    division_path = processed_dir / "oie_division_month.parquet"
    division_frame = panel.division_table.frame
    division_frame.to_parquet(division_path, index=False, engine="pyarrow")
    written["division_month"] = division_path

    panel_path = processed_dir / "industry_month_panel.parquet"
    panel.frame.to_parquet(panel_path, index=False, engine="pyarrow")
    written["industry_panel"] = panel_path

    if write_csv_preview:
        preview_path = processed_dir / "industry_month_panel_preview.csv"
        panel.frame.head(24).to_csv(preview_path, index=False, encoding="utf-8")
        written["preview"] = preview_path

    return written
