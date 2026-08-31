"""Production OIE ingestion — manifest resolution, integrity gating, and the
division-month normalized table (Task B1).

Scope is deliberately narrow: the current 2021-based edition only. Older
editions are not bridged into the MVP core panel; the A1/A2 bridge validation
is preserved as research documentation and is not consumed here
(configs/sources.yaml `mvp_policy`).

Failure policy: a resolved file whose SHA-256 or edition does not match
`configs/sources.yaml` raises `SourceIntegrityError`. There is no warn-and-
continue path — silently ingesting an unexpected file is how a pipeline
starts producing confidently wrong numbers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from thai_supply_chain_ews.data import oie

__all__ = [
    "DivisionMonthTable",
    "SourceIntegrityError",
    "SourceSpec",
    "build_division_month_table",
    "default_sources_path",
    "load_source_config",
    "resolve_source_file",
    "verify_source_integrity",
]

DIVISION_MONTH_COLUMNS = [
    "reference_month",
    "component",
    "tsic_division",
    "tsic_label",
    "source_value",
    "source_weight",
    "source_edition",
    "source_base_year",
    "is_preliminary",
    "source_file",
    "source_sha256",
    "source_url",
    "retrieved_at",
    "release_date",
    "available_as_of",
    "data_quality_flag",
]

QUALITY_OK = "ok"
QUALITY_PRELIMINARY = "preliminary"
QUALITY_MISSING_VALUE = "missing_value"


class SourceIntegrityError(RuntimeError):
    """A resolved source file does not match its pinned checksum or edition."""


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    component: str
    manifest: Path
    expected_sha256: str
    expected_edition: str
    expected_base_year: int
    expected_classification: str
    source_url: str | None
    snapshot: dict


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_sources_path() -> Path:
    return project_root() / "configs" / "sources.yaml"


def load_source_config(path: Path | None = None) -> tuple[dict[str, SourceSpec], dict]:
    """Return the pinned source specs plus the raw config (for policy fields)."""
    path = Path(path) if path is not None else default_sources_path()
    if not path.is_file():
        raise FileNotFoundError(f"Source config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = project_root()
    specs = {
        source_id: SourceSpec(
            source_id=source_id,
            component=spec["component"],
            manifest=root / spec["manifest"],
            expected_sha256=spec["expected_sha256"],
            expected_edition=spec["expected_edition"],
            expected_base_year=int(spec["expected_base_year"]),
            expected_classification=spec["expected_classification"],
            source_url=spec.get("source_url"),
            snapshot=spec.get("snapshot", {}),
        )
        for source_id, spec in raw["sources"].items()
    }
    return specs, raw


def resolve_source_file(spec: SourceSpec) -> tuple[Path, dict]:
    """Resolve the file to ingest from its retrieval manifest.

    No hard-coded absolute path and no hard-coded retrieval date: the manifest's
    most recent entry is the record of what was actually retrieved. The manifest
    entry is returned alongside the path so provenance (retrieved_at, url)
    travels with the data instead of being re-guessed downstream.
    """
    if not spec.manifest.is_file():
        raise FileNotFoundError(
            f"Retrieval manifest missing for {spec.source_id}: {spec.manifest}. "
            "B1 resolves files through manifests only."
        )
    lines = [ln for ln in spec.manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise SourceIntegrityError(f"Manifest for {spec.source_id} is empty: {spec.manifest}")
    entry = json.loads(lines[-1])
    path = project_root() / entry["file_path"]
    if not path.is_file():
        raise FileNotFoundError(
            f"Manifest for {spec.source_id} points at a missing file: {path}"
        )
    return path, entry


def verify_source_integrity(spec: SourceSpec, path: Path, parsed: oie.ParsedWorkbook) -> None:
    """Fail loudly on checksum or edition mismatch."""
    if parsed.sha256 != spec.expected_sha256:
        raise SourceIntegrityError(
            f"{spec.source_id}: SHA-256 mismatch for {path.name}.\n"
            f"  expected {spec.expected_sha256}\n"
            f"  actual   {parsed.sha256}\n"
            "Refusing to ingest. If the source was deliberately refreshed, update "
            "expected_sha256 in configs/sources.yaml in the same commit."
        )
    observed_base_year = parsed.dates.earliest.year
    if spec.expected_base_year != 2021 and observed_base_year != spec.expected_base_year:
        raise SourceIntegrityError(
            f"{spec.source_id}: expected base year {spec.expected_base_year}"
        )
    expected_first = spec.snapshot.get("first_month")
    if expected_first:
        actual_first = f"{parsed.dates.earliest.year:04d}-{parsed.dates.earliest.month:02d}"
        if actual_first != expected_first:
            raise SourceIntegrityError(
                f"{spec.source_id}: edition mismatch — expected the "
                f"{spec.expected_edition} edition starting {expected_first}, "
                f"but the resolved file starts {actual_first}."
            )


@dataclass
class DivisionMonthTable:
    frame: pd.DataFrame
    parsed_by_component: dict[str, oie.ParsedWorkbook]
    provenance: dict[str, dict]

    @property
    def components(self) -> list[str]:
        return sorted(self.frame["component"].unique())


def build_division_month_table(
    sources_path: Path | None = None,
) -> DivisionMonthTable:
    """Parse every configured current-edition source into one long table.

    One row per (reference_month, component, tsic_division). `release_date` and
    `available_as_of` are emitted as NULL for every row: neither is present in
    the workbooks and no archived OIE release calendar was located, so inventing
    per-month values would manufacture point-in-time information this project
    does not have (configs/sources.yaml `temporal_verification`).
    """
    specs, raw_config = load_source_config(sources_path)
    temporal = raw_config.get("temporal_verification", {})
    release_verified = temporal.get("release_date", {}).get("verified", False)
    available_verified = temporal.get("available_as_of", {}).get("verified", False)

    records: list[dict] = []
    parsed_by_component: dict[str, oie.ParsedWorkbook] = {}
    provenance: dict[str, dict] = {}

    for source_id in sorted(specs):
        spec = specs[source_id]
        path, manifest_entry = resolve_source_file(spec)
        parsed = oie.parse_workbook(path)
        verify_source_integrity(spec, path, parsed)

        parsed_by_component[spec.component] = parsed
        retrieved_at = manifest_entry.get("retrieved_at")
        url = manifest_entry.get("official_url") or spec.source_url
        rel_path = str(path.relative_to(project_root())).replace("\\", "/")
        provenance[spec.component] = {
            "source_id": source_id,
            "source_file": rel_path,
            "source_sha256": parsed.sha256,
            "source_url": url,
            "retrieved_at": retrieved_at,
            "source_edition": spec.expected_edition,
            "source_base_year": spec.expected_base_year,
        }

        preliminary_by_month = dict(
            zip(parsed.dates.dates, parsed.dates.preliminary_flags, strict=True)
        )
        for division in parsed.division_numbers:
            row = parsed.divisions[division]
            for month in parsed.dates.dates:
                value = row.values_by_month.get(month)
                is_preliminary = bool(preliminary_by_month[month])
                if value is None:
                    flag = QUALITY_MISSING_VALUE
                elif is_preliminary:
                    flag = QUALITY_PRELIMINARY
                else:
                    flag = QUALITY_OK
                records.append(
                    {
                        "reference_month": month,
                        "component": spec.component,
                        "tsic_division": division,
                        "tsic_label": row.tsic_label,
                        "source_value": value,
                        "source_weight": row.source_weight,
                        "source_edition": spec.expected_edition,
                        "source_base_year": spec.expected_base_year,
                        "is_preliminary": is_preliminary,
                        "source_file": rel_path,
                        "source_sha256": parsed.sha256,
                        "source_url": url,
                        "retrieved_at": retrieved_at,
                        # Deliberately null — not verified. See module docstring.
                        "release_date": None if not release_verified else NotImplemented,
                        "available_as_of": None if not available_verified else NotImplemented,
                        "data_quality_flag": flag,
                    }
                )

    frame = pd.DataFrame.from_records(records, columns=DIVISION_MONTH_COLUMNS)
    frame = _cast_division_month_types(frame)
    frame = frame.sort_values(
        ["component", "reference_month", "tsic_division"], kind="mergesort"
    ).reset_index(drop=True)

    duplicated = frame.duplicated(subset=["reference_month", "component", "tsic_division"])
    if duplicated.any():
        offenders = frame.loc[duplicated, ["reference_month", "component", "tsic_division"]]
        raise oie.DuplicateDivisionError(
            f"Duplicate (month, component, division) keys in the division table:\n{offenders}"
        )

    return DivisionMonthTable(
        frame=frame, parsed_by_component=parsed_by_component, provenance=provenance
    )


def _cast_division_month_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Explicit dtypes so the Parquet schema is stable across runs."""
    frame = frame.copy()
    frame["reference_month"] = pd.to_datetime(frame["reference_month"]).dt.date
    frame["component"] = frame["component"].astype("string")
    frame["tsic_division"] = frame["tsic_division"].astype("int16")
    frame["tsic_label"] = frame["tsic_label"].astype("string")
    frame["source_value"] = frame["source_value"].astype("float64")
    frame["source_weight"] = frame["source_weight"].astype("float64")
    frame["source_edition"] = frame["source_edition"].astype("string")
    frame["source_base_year"] = frame["source_base_year"].astype("int16")
    frame["is_preliminary"] = frame["is_preliminary"].astype("bool")
    for col in ("source_file", "source_sha256", "source_url", "retrieved_at",
                "data_quality_flag"):
        frame[col] = frame[col].astype("string")
    for col in ("release_date", "available_as_of"):
        frame[col] = pd.Series([pd.NaT] * len(frame), dtype="datetime64[ns]")
    return frame


def fetch_source(source_id: str, *, output_dir: Path) -> Path:
    """Retrieve one source's raw data (Phase 1 task A3).

    Still not implemented. B1 ingests from files already retrieved and recorded
    in `data/raw/_manifests/`; automated re-retrieval is a separate task and is
    not required for the MVP core panel.
    """
    raise NotImplementedError(
        f"fetch_source({source_id!r}) is not implemented — B1 consumes files already "
        "recorded in data/raw/_manifests/. See docs/project_roadmap.md Phase 1 task A3."
    )
