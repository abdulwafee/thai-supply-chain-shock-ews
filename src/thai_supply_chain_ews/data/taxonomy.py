"""Industry taxonomy loading and validation (Task B1).

Loads `configs/industry_mapping.yaml` — the FINAL current-edition taxonomy —
and enforces its coverage contract at load time rather than trusting the file.

The earlier draft mapping (which omitted TSIC 12 entirely and included the
unreported divisions 18 and 33) is deliberately NOT loaded here. It survives,
frozen, only inside `scripts/audit_target_sources.py`, so the preserved A1/A2
bridge-validation evidence stays byte-reproducible. See
docs/architecture/decision_log.md AD-R12.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = [
    "Industry",
    "IndustryTaxonomy",
    "TaxonomyError",
    "default_mapping_path",
    "load_taxonomy",
]


class TaxonomyError(ValueError):
    """The industry mapping violates its own coverage contract."""


@dataclass(frozen=True)
class Industry:
    industry_id: str
    name_en: str
    name_th: str
    tsic_divisions: tuple[int, ...]

    @property
    def is_single_division(self) -> bool:
        return len(self.tsic_divisions) == 1


@dataclass(frozen=True)
class IndustryTaxonomy:
    version: str
    industries: dict[str, Industry]
    expected_division_coverage: tuple[int, ...]
    excluded_divisions: dict[int, str]
    source_path: Path

    @property
    def industry_ids(self) -> list[str]:
        return sorted(self.industries)

    @property
    def all_divisions(self) -> list[int]:
        return sorted(d for ind in self.industries.values() for d in ind.tsic_divisions)

    def industry_for_division(self, division: int) -> str | None:
        for industry in self.industries.values():
            if division in industry.tsic_divisions:
                return industry.industry_id
        return None


def default_mapping_path() -> Path:
    """configs/industry_mapping.yaml, resolved from this file's location."""
    return Path(__file__).resolve().parents[3] / "configs" / "industry_mapping.yaml"


def load_taxonomy(path: Path | None = None) -> IndustryTaxonomy:
    """Load and validate the taxonomy.

    Validation is not optional: a mapping that double-assigns a division, or
    that does not cover exactly the declared division set, is a defect that
    would silently corrupt every downstream aggregate.
    """
    path = Path(path) if path is not None else default_mapping_path()
    if not path.is_file():
        raise FileNotFoundError(f"Industry mapping not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    industries: dict[str, Industry] = {}
    seen: dict[int, str] = {}
    for industry_id, spec in raw["industries"].items():
        divisions = tuple(int(d) for d in spec["tsic_divisions"])
        if not divisions:
            raise TaxonomyError(f"{industry_id} has no TSIC divisions")
        for division in divisions:
            if division in seen:
                raise TaxonomyError(
                    f"TSIC division {division} is assigned to both {seen[division]} and "
                    f"{industry_id} — a division must belong to exactly one industry."
                )
            seen[division] = industry_id
        industries[industry_id] = Industry(
            industry_id=industry_id,
            name_en=spec["name_en"],
            name_th=spec["name_th"],
            tsic_divisions=divisions,
        )

    expected = tuple(int(d) for d in raw["expected_division_coverage"])
    covered = tuple(sorted(seen))
    if covered != tuple(sorted(expected)):
        missing = sorted(set(expected) - set(covered))
        extra = sorted(set(covered) - set(expected))
        raise TaxonomyError(
            f"Mapping coverage does not match expected_division_coverage. "
            f"Missing: {missing}. Unexpected: {extra}."
        )

    excluded = {
        int(k): v.get("reason", "") for k, v in (raw.get("excluded_divisions") or {}).items()
    }
    overlap = set(excluded) & set(covered)
    if overlap:
        raise TaxonomyError(
            f"Divisions {sorted(overlap)} are both mapped to an industry and listed as excluded."
        )

    return IndustryTaxonomy(
        version=raw["taxonomy_version"],
        industries=industries,
        expected_division_coverage=tuple(sorted(expected)),
        excluded_divisions=excluded,
        source_path=path,
    )
