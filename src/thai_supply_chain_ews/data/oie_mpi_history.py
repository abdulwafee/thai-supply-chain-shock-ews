"""Historical-extension feasibility and base-year compatibility (Task D2).

D1 could not run its nested protocol on six origins because too little
pre-origin calibration history existed. The obvious remedy is to extend MPI
history backwards. This module decides whether that remedy is actually
available, and it is deliberately hard to satisfy.

Extending history means joining editions. OIE publishes three: a 2011-based
edition (ISIC labels), a 2016-based edition, and the live 2021-based edition
that B1 ingested. Two editions may be spliced only if, over the months they
share, one is a fixed rescaling of the other -- a pure rebasing. If the ratio
moves from month to month, the index was **re-estimated**, and splicing would
manufacture history that OIE never published.

:func:`evaluate_base_year_compatibility` measures that ratio per division and
reports the coefficient of variation. :func:`assess_history_extension` combines
it with the coverage and division-set requirements. Neither will approve a
splice because the calendar requirement demands one -- the requirement is what
gets reported as unmet.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

__all__ = [
    "DivisionRatioResult",
    "EditionProfile",
    "assess_history_extension",
    "evaluate_base_year_compatibility",
    "month_sequence",
    "profile_edition",
]


def month_sequence(start, end):
    """Inclusive ``YYYY-MM`` sequence."""
    year, month = int(start[:4]), int(start[5:7])
    out = []
    while f"{year:04d}-{month:02d}" <= end:
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


@dataclass
class EditionProfile:
    edition_id: str
    path: str
    base_year: int = None
    classification_scheme: str = None
    coverage_start: str = None
    coverage_end: str = None
    readable_end: str = None
    divisions: list = field(default_factory=list)
    marked_months: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def profile_edition(edition_id, reader, path=None):
    """Structural profile of one edition. Reads no value beyond the cutoff."""
    start, end = reader.coverage()
    readable = [
        c.reference_month for c in reader.structure()
        if reader.is_readable(c.reference_month)
    ]
    return EditionProfile(
        edition_id=edition_id,
        path=str(path if path is not None else reader.path),
        base_year=reader.base_year(),
        classification_scheme=reader.classification_scheme(),
        coverage_start=start,
        coverage_end=end,
        readable_end=max(readable) if readable else None,
        divisions=reader.divisions(),
        marked_months=reader.marked_months(),
    )


@dataclass
class DivisionRatioResult:
    division: int
    overlap_months: int
    ratio_mean: float = None
    ratio_cv_percent: float = None
    ratio_min: float = None
    ratio_max: float = None
    verdict: str = "not_evaluated"

    def to_dict(self):
        return asdict(self)


def evaluate_base_year_compatibility(older_reader, newer_reader, config):
    """Test whether two editions differ by a pure rescaling on their overlap.

    Only months at or before the numerical cutoff are read, so this test never
    depends on the months the locked evaluation protects.
    """
    gate = config["base_year_compatibility_gate"]
    older_divisions = set(older_reader.divisions())
    newer_divisions = set(newer_reader.divisions())
    shared = sorted(older_divisions & newer_divisions)

    results, passing = [], 0
    for division in shared:
        older = older_reader.division_series(division)
        newer = newer_reader.division_series(division)
        months = sorted(
            m for m in set(older) & set(newer) if older.get(m)
        )
        if len(months) < gate["min_overlap_months"]:
            results.append(
                DivisionRatioResult(division, len(months), verdict="insufficient_overlap")
            )
            continue
        ratios = [newer[m] / older[m] for m in months]
        mean = statistics.fmean(ratios)
        cv = (statistics.pstdev(ratios) / mean * 100.0) if mean else float("inf")
        verdict = "pure_rescaling" if cv < gate["max_ratio_cv_percent"] else "re_estimated"
        if verdict == "pure_rescaling":
            passing += 1
        results.append(
            DivisionRatioResult(
                division=division,
                overlap_months=len(months),
                ratio_mean=mean,
                ratio_cv_percent=cv,
                ratio_min=min(ratios),
                ratio_max=max(ratios),
                verdict=verdict,
            )
        )

    evaluated = [r for r in results if r.verdict in {"pure_rescaling", "re_estimated"}]
    fraction = (passing / len(evaluated)) if evaluated else 0.0
    identical_divisions = older_divisions == newer_divisions

    blockers = []
    if gate["require_identical_division_sets"] and not identical_divisions:
        blockers.append(
            f"division sets differ: "
            f"only_in_newer={sorted(newer_divisions - older_divisions)} "
            f"only_in_older={sorted(older_divisions - newer_divisions)}"
        )
    if fraction < gate["min_fraction_divisions_passing"]:
        blockers.append(
            f"only {passing} of {len(evaluated)} evaluated divisions are a pure "
            f"rescaling (required fraction "
            f"{gate['min_fraction_divisions_passing']:.2f})"
        )
    if not evaluated:
        blockers.append("no division had sufficient overlap to evaluate")

    return {
        "older_edition": older_reader.base_year(),
        "newer_edition": newer_reader.base_year(),
        "older_scheme": older_reader.classification_scheme(),
        "newer_scheme": newer_reader.classification_scheme(),
        "shared_divisions": shared,
        "only_in_newer": sorted(newer_divisions - older_divisions),
        "only_in_older": sorted(older_divisions - newer_divisions),
        "identical_division_sets": identical_divisions,
        "divisions_evaluated": len(evaluated),
        "divisions_pure_rescaling": passing,
        "divisions_re_estimated": len(evaluated) - passing,
        "fraction_passing": fraction,
        "median_ratio_cv_percent": (
            statistics.median([r.ratio_cv_percent for r in evaluated]) if evaluated else None
        ),
        "max_ratio_cv_percent_observed": (
            max(r.ratio_cv_percent for r in evaluated) if evaluated else None
        ),
        "per_division": [r.to_dict() for r in results],
        "splice_admissible": not blockers,
        "blockers": blockers,
        "silent_splicing_permitted": gate["silent_splicing_permitted"],
    }


def assess_history_extension(profiles, compatibility, config):
    """Decide whether MPI history can honestly reach the required start month."""
    requirements = config["history_extension_requirements"]
    raw_required = requirements["raw_start_required"]
    stress_required = requirements["stress_start_required"]
    required_divisions = set(requirements["required_divisions"])

    primary = max(profiles, key=lambda p: (p.coverage_end or ""))
    primary_reaches = primary.coverage_start is not None and primary.coverage_start <= raw_required

    reaching = [p for p in profiles if p.coverage_start and p.coverage_start <= raw_required]
    complete = [p for p in reaching if required_divisions <= set(p.divisions)]

    blockers = []
    if not primary_reaches:
        blockers.append(
            f"primary edition (base {primary.base_year}) starts "
            f"{primary.coverage_start}, after the required {raw_required}; "
            "reaching it requires joining an older edition"
        )
    for profile in reaching:
        missing = sorted(required_divisions - set(profile.divisions))
        if missing:
            blockers.append(
                f"edition base {profile.base_year} reaches "
                f"{profile.coverage_start} but is missing required "
                f"division(s) {missing}"
            )
    if not primary_reaches and not compatibility.get("splice_admissible"):
        blockers.extend(
            f"base-year splice inadmissible: {item}"
            for item in compatibility.get("blockers", [])
        )

    schemes = {p.classification_scheme for p in profiles if p.classification_scheme}
    if len(schemes) > 1:
        blockers.append(
            f"editions use different classification schemes {sorted(schemes)}; "
            "a scheme change is not a revision and cannot be spliced"
        )

    feasible = not blockers
    return {
        "raw_start_required": raw_required,
        "stress_start_required": stress_required,
        "calibrator_warmup_months": requirements["calibrator_warmup_months"],
        "primary_edition_base_year": primary.base_year,
        "primary_edition_coverage_start": primary.coverage_start,
        "primary_edition_reaches_required_start": primary_reaches,
        "editions_reaching_required_start": [p.edition_id for p in reaching],
        "editions_reaching_start_with_all_divisions": [p.edition_id for p in complete],
        "point_in_time_extension_feasible": False,
        "latest_vintage_extension_feasible": feasible,
        "blockers": blockers,
        "d1_fallback_remedied": feasible,
    }
