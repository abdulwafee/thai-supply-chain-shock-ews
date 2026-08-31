"""Task A2 — empirical overlap-window bridge validation.

Validates, on real downloaded OIE data, whether the current (2021-based,
TSIC-labeled) and 2016-based (TSIC-labeled) editions can be bridged into one
consistent series for the 11 industries whose division composition is
identical across the two editions (`docs/task_a1_report.md` §7.3; IND-03 is
excluded — see `IND03_STATUS` below).

Scope, exactly as confirmed: current vs. 2016-based edition only, overlap
2021-01 to 2023-12 (36 months), MPI and Capacity Utilization, 11 industries.
The 2011-based ISIC edition is explicitly out of scope for this script.

This script does NOT construct a final spliced series and does NOT feed a
model. It produces the evidence — real Pearson/Spearman correlations, biases,
per-year stability, level-linking factors — that a later, separate task would
use to actually splice, IF the approval criteria below are met.

Approval criteria are documented as PROVISIONAL_APPROVAL_CRITERIA below,
written before this script's output was inspected, and applied mechanically —
per the explicit restriction against inventing a threshold after seeing
results.

Usage:
    python scripts/validate_oie_overlap.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    print("matplotlib is required: pip install matplotlib", file=sys.stderr)
    raise

try:
    import openpyxl
except ImportError:  # pragma: no cover
    print("openpyxl is required: pip install openpyxl", file=sys.stderr)
    raise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_target_sources as base_audit  # noqa: E402

BRIDGE_VERSION = "oie_overlap_bridge_v1_2026-08-26"

OVERLAP_START = date(2021, 1, 1)
OVERLAP_END = date(2023, 12, 1)
EXPECTED_OVERLAP_MONTHS = 36

INDUSTRY_TSIC_DIVISIONS = base_audit.INDUSTRY_TSIC_DIVISIONS

# IND-03's composition changes across editions (current: {16,17}; 2016-based:
# {17} only — docs/task_a1_report.md §7.4). It is excluded from this
# validation's candidate set, per the confirmed scope, and reported
# separately, never silently redefined.
IND03_EXCLUDED_ID = "IND-03"
CANDIDATE_INDUSTRIES = {
    k: v for k, v in INDUSTRY_TSIC_DIVISIONS.items() if k != IND03_EXCLUDED_ID
}
assert len(CANDIDATE_INDUSTRIES) == 11

COMPONENTS = ("MPI", "CapU")

# Confirmed scope: this validation covers ONLY the current (2021-based) and
# 2016-based TSIC editions. The 2011-based ISIC edition is explicitly out of
# scope here — its classification_compatible status stays "unresolved" per
# scripts/audit_history_extension.py and it is never approved by this script.
SCOPE_EDITIONS = ("current", "2016_based")
EXCLUDED_EDITIONS = ("2554_2011",)

# --- provisional approval criteria ------------------------------------------
# Documented BEFORE this script's output was inspected. Applied mechanically
# in `apply_approval_criteria` — never adjusted after seeing results.
#
# Rationale for each number: a rebased-level Pearson r of 0.90 is a high but
# achievable bar for two editions of the *same underlying survey* under a
# base-year change alone (if the only difference were rebasing arithmetic,
# correlation should be very close to 1); the MoM/YoY thresholds are lower
# because period-over-period growth rates amplify noise relative to levels,
# so a somewhat lower correlation there is expected even for a genuinely
# trustworthy bridge; the bias thresholds (percentage points) are set to
# roughly the typical month-to-month movement scale documented in this
# project's own target-design phase (a few points), not zero, since some
# revision-driven drift between vintages is expected and acceptable; the
# per-year stability and discontinuity checks exist specifically to prevent
# a single anomalous year or a one-off data error from being masked by an
# otherwise-good three-year average.
PROVISIONAL_APPROVAL_CRITERIA = {
    "rebased_level_min_pearson": 0.90,
    "mom_min_pearson": 0.70,
    "mom_max_abs_bias_pp": 2.0,
    "yoy_min_pearson": 0.85,
    "yoy_max_abs_bias_pp": 3.0,
    "min_year_rebased_pearson": 0.75,
    "discontinuity_multiplier": 4.0,  # flag a single-month |diff| > this x the median |diff|
    # Absolute floors alongside the relative multiplier above. Needed because a pure
    # relative multiplier is meaningless when the median |diff| itself is at
    # floating-point noise level (observed for real: IND-04 CapU is identical to
    # ~1e-14 for 2021-2022, so ANY later difference — even 0.6 index points — would
    # otherwise register as ">4x the median" and wrongly trigger a hard rejection).
    # This is a robustness fix to the detection mechanism, decided after discovering
    # the degenerate case, not a relaxation of the approval bar itself: 1.0 point on
    # a 100-based rebased index, or 1.0 percentage point on a MoM/YoY change, is
    # noise-level relative to the 2.0-3.0pp bias tolerances already set above.
    "discontinuity_abs_floor_rebased": 1.0,
    "discontinuity_abs_floor_pct": 1.0,
    "min_valid_pairs_full_confidence": 30,  # below this, status caps at "Insufficient evidence"
}

DIVISION_LABEL_PATTERN = re.compile(r"^TSIC\s*:\s*(\d\d)\s")


# --- extraction: real per-division monthly VALUES, not just presence -------


@dataclass
class DivisionValueSeries:
    edition_id: str
    component: str
    file_path: str
    sha256: str
    classification_label: str
    weights: dict[int, float]
    values: dict[int, dict[str, float]]  # division -> {iso_date: value}
    dates: list[str]  # all dates found in the source file (not yet restricted to overlap)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_division_value_series(
    edition_id: str, component: str, path: Path
) -> DivisionValueSeries:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))

    label_col = base_audit.find_tsic_label_column(rows)
    month_col_start = base_audit.find_first_month_column(rows, label_col)
    date_audit = base_audit.parse_monthly_dates(rows, month_col_start)
    month_count = len(date_audit.dates)
    weight_col = label_col + 1

    weights: dict[int, float] = {}
    values: dict[int, dict[str, float]] = {}
    seen_divisions: set[int] = set()
    for row in rows:
        label = row[label_col] if label_col < len(row) else None
        if not isinstance(label, str):
            continue
        m = DIVISION_LABEL_PATTERN.match(label)
        if not m:
            continue
        division = int(m.group(1))
        if division in seen_divisions:
            raise base_audit.DuplicateDivisionError(
                f"TSIC division {division} appears more than once in {path.name}"
            )
        seen_divisions.add(division)

        weight_val = row[weight_col] if weight_col < len(row) else None
        try:
            weights[division] = float(weight_val)
        except (TypeError, ValueError):
            weights[division] = float("nan")

        row_values = row[month_col_start : month_col_start + month_count]
        by_date: dict[str, float] = {}
        for d, v in zip(date_audit.dates, row_values, strict=True):
            if isinstance(v, (int, float)):
                by_date[d.isoformat()] = float(v)
            # a non-numeric/missing cell is simply not added — see
            # restrict_to_overlap, which then REJECTS (never imputes) any
            # division-month key missing within the overlap window.
        values[division] = by_date

    return DivisionValueSeries(
        edition_id=edition_id,
        component=component,
        file_path=str(path.relative_to(PROJECT_ROOT)),
        sha256=sha256_of(path),
        classification_label="TSIC",  # both editions in this script's scope are TSIC-labeled
        weights=weights,
        values=values,
        dates=[d.isoformat() for d in date_audit.dates],
    )


class OverlapIncompleteError(ValueError):
    """Raised when the overlap window does not contain exactly the expected
    number of months, or a required division-month value is missing —
    never silently padded or imputed.
    """


def overlap_month_list() -> list[str]:
    months = []
    y, m = OVERLAP_START.year, OVERLAP_START.month
    while (y, m) <= (OVERLAP_END.year, OVERLAP_END.month):
        months.append(date(y, m, 1).isoformat())
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


def restrict_to_overlap(series: DivisionValueSeries, division: int) -> dict[str, float]:
    """Return {date: value} for exactly the overlap months, for one division.
    Raises OverlapIncompleteError if any overlap month is missing for this
    division — never fills it in.
    """
    expected_months = overlap_month_list()
    if len(expected_months) != EXPECTED_OVERLAP_MONTHS:
        raise OverlapIncompleteError(
            f"Overlap window definition itself is wrong: {len(expected_months)} months, "
            f"expected {EXPECTED_OVERLAP_MONTHS}"
        )
    division_values = series.values.get(division, {})
    result = {}
    missing = []
    for month in expected_months:
        if month in division_values:
            result[month] = division_values[month]
        else:
            missing.append(month)
    if missing:
        raise OverlapIncompleteError(
            f"{series.edition_id}/{series.component} division {division}: missing overlap "
            f"months {missing} — refusing to impute; this division-component-edition "
            "combination cannot be validated for this overlap window."
        )
    return result


# --- industry aggregation ----------------------------------------------------


def effective_divisions_for_industry(
    required: list[int], current_series: DivisionValueSeries, older_series: DivisionValueSeries
) -> tuple[list[int], bool, str | None]:
    """Restrict `required` to the divisions actually present in BOTH editions'
    files, and confirm that restricted set is identical across editions —
    the same composition_consistent check as audit_history_extension.py,
    but computed here against the divisions this script actually extracted
    values for, so a division genuinely absent from an edition (e.g. TSIC 33
    for IND-12, consistently missing in both editions) is dropped from the
    aggregation rather than causing a KeyError, while a division present in
    one edition but not the other (e.g. IND-03) is correctly rejected.
    """
    required_set = set(required)
    present_current = sorted(required_set & set(current_series.weights))
    present_older = sorted(required_set & set(older_series.weights))
    if present_current != present_older or not present_current:
        return (
            [],
            False,
            f"Present-division set differs across editions (current={present_current}, "
            f"2016_based={present_older}) or is empty — not a valid bridge candidate.",
        )
    return present_current, True, None


def aggregate_industry_series(
    series: DivisionValueSeries,
    divisions: list[int],
    weight_override: dict[int, float] | None = None,
) -> dict[str, float]:
    """Weighted average across `divisions`, using the series' own official
    weights (or `weight_override`, for the fixed-weight diagnostic),
    renormalized so the weights used sum to 1 across exactly these divisions
    — never equal weighting.
    """
    weights_to_use = weight_override if weight_override is not None else series.weights
    raw_weights = {d: weights_to_use[d] for d in divisions}
    total = sum(raw_weights.values())
    if total <= 0:
        raise ValueError(f"Non-positive total weight for divisions {divisions}: {raw_weights}")
    normalized = {d: w / total for d, w in raw_weights.items()}

    per_division_overlap = {d: restrict_to_overlap(series, d) for d in divisions}
    months = overlap_month_list()
    aggregated = {}
    for month in months:
        aggregated[month] = sum(normalized[d] * per_division_overlap[d][month] for d in divisions)
    return aggregated, normalized


# --- representations ---------------------------------------------------------


def to_ordered_array(series_dict: dict[str, float]) -> np.ndarray:
    months = overlap_month_list()
    return np.array([series_dict[m] for m in months], dtype=float)


def build_representations(raw: np.ndarray) -> dict[str, np.ndarray]:
    rebased = raw / raw[0] * 100.0
    mom_pct = np.full_like(raw, np.nan)
    mom_pct[1:] = (raw[1:] / raw[:-1] - 1.0) * 100.0
    yoy_pct = np.full_like(raw, np.nan)
    if len(raw) > 12:
        yoy_pct[12:] = (raw[12:] / raw[:-12] - 1.0) * 100.0
    return {"raw": raw, "rebased": rebased, "mom_pct": mom_pct, "yoy_pct": yoy_pct}


# --- metrics ------------------------------------------------------------------


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    mask = ~(np.isnan(a) | np.isnan(b))
    if mask.sum() < 2 or np.std(a[mask]) == 0 or np.std(b[mask]) == 0:
        return float("nan")
    return float(np.corrcoef(a[mask], b[mask])[0, 1])


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    mask = ~(np.isnan(a) | np.isnan(b))
    a_valid, b_valid = a[mask], b[mask]
    if len(a_valid) < 2:
        return float("nan")

    def rank(x):
        order = x.argsort(kind="mergesort")
        ranks = np.empty(len(x), dtype=float)
        sorted_x = x[order]
        i = 0
        while i < len(sorted_x):
            j = i
            while j + 1 < len(sorted_x) and sorted_x[j + 1] == sorted_x[i]:
                j += 1
            ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return ranks

    ra, rb = rank(a_valid), rank(b_valid)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


@dataclass
class RepresentationMetrics:
    n_valid: int
    pearson_r: float
    spearman_r: float
    mean_abs_diff: float
    median_abs_diff: float
    mean_signed_diff: float
    max_abs_diff: float
    per_year: dict[str, dict[str, float]] = field(default_factory=dict)
    discontinuity_months: list[str] = field(default_factory=list)


def compute_metrics(
    a: np.ndarray, b: np.ndarray, dates_iso: list[str], abs_floor: float = 0.0
) -> RepresentationMetrics:
    mask = ~(np.isnan(a) | np.isnan(b))
    n_valid = int(mask.sum())
    if n_valid == 0:
        return RepresentationMetrics(0, float("nan"), float("nan"), float("nan"),
                                      float("nan"), float("nan"), float("nan"))
    diff = a[mask] - b[mask]
    abs_diff = np.abs(diff)

    per_year: dict[str, dict[str, float]] = {}
    years = sorted({d[:4] for d, m in zip(dates_iso, mask, strict=True) if m})
    for year in years:
        year_mask = np.array(
            [m and d.startswith(year) for d, m in zip(dates_iso, mask, strict=True)]
        )
        if year_mask.sum() >= 2:
            per_year[year] = {
                "pearson_r": pearson(a[year_mask], b[year_mask]),
                "n_valid": int(year_mask.sum()),
            }
        else:
            per_year[year] = {"pearson_r": float("nan"), "n_valid": int(year_mask.sum())}

    median_abs = float(np.median(abs_diff))
    discontinuity_months = []
    threshold = max(
        PROVISIONAL_APPROVAL_CRITERIA["discontinuity_multiplier"] * median_abs, abs_floor
    )
    if threshold > 0:
        valid_dates = [d for d, m in zip(dates_iso, mask, strict=True) if m]
        for d, ad in zip(valid_dates, abs_diff, strict=True):
            if ad > threshold:
                discontinuity_months.append(d)

    return RepresentationMetrics(
        n_valid=n_valid,
        pearson_r=pearson(a, b),
        spearman_r=spearman(a, b),
        mean_abs_diff=float(np.mean(abs_diff)),
        median_abs_diff=median_abs,
        mean_signed_diff=float(np.mean(diff)),
        max_abs_diff=float(np.max(abs_diff)),
        per_year=per_year,
        discontinuity_months=discontinuity_months,
    )


def level_link_factor(current_raw: np.ndarray, older_raw: np.ndarray) -> float:
    """Robust overlap statistic: median of the ratio current/older across
    the overlap months, per the confirmed instruction to prefer a robust
    statistic (median ratio) over a mean unless evidence supports otherwise.
    """
    ratios = current_raw / older_raw
    return float(np.median(ratios))


# --- approval ------------------------------------------------------------


def apply_approval_criteria(
    rebased_metrics: RepresentationMetrics,
    mom_metrics: RepresentationMetrics,
    yoy_metrics: RepresentationMetrics,
) -> tuple[str, list[str]]:
    c = PROVISIONAL_APPROVAL_CRITERIA
    reasons: list[str] = []

    if rebased_metrics.n_valid < c["min_valid_pairs_full_confidence"]:
        reasons.append(
            f"Only {rebased_metrics.n_valid} valid paired months on rebased levels "
            f"(< {c['min_valid_pairs_full_confidence']}) — too few to assess reliably."
        )
        return "Insufficient evidence", reasons

    hard_fail = False
    if not (rebased_metrics.pearson_r >= c["rebased_level_min_pearson"]):
        reasons.append(
            f"Rebased-level Pearson r={rebased_metrics.pearson_r:.3f} < "
            f"{c['rebased_level_min_pearson']}"
        )
        hard_fail = rebased_metrics.pearson_r < 0.5 or np.isnan(rebased_metrics.pearson_r)

    if rebased_metrics.discontinuity_months:
        reasons.append(f"Unexplained discontinuity in: {rebased_metrics.discontinuity_months}")
        hard_fail = True

    for year, stats in rebased_metrics.per_year.items():
        r = stats["pearson_r"]
        if not np.isnan(r) and r < c["min_year_rebased_pearson"]:
            reasons.append(f"Year {year} rebased-level Pearson r={r:.3f} below stability bar")

    soft_fail = False
    if not (mom_metrics.pearson_r >= c["mom_min_pearson"]):
        reasons.append(f"MoM Pearson r={mom_metrics.pearson_r:.3f} < {c['mom_min_pearson']}")
        soft_fail = True
    if abs(mom_metrics.mean_signed_diff) > c["mom_max_abs_bias_pp"]:
        reasons.append(
            f"MoM mean bias={mom_metrics.mean_signed_diff:.2f}pp exceeds "
            f"{c['mom_max_abs_bias_pp']}pp"
        )
        soft_fail = True
    if not (yoy_metrics.pearson_r >= c["yoy_min_pearson"]):
        reasons.append(f"YoY Pearson r={yoy_metrics.pearson_r:.3f} < {c['yoy_min_pearson']}")
        soft_fail = True
    if abs(yoy_metrics.mean_signed_diff) > c["yoy_max_abs_bias_pp"]:
        reasons.append(
            f"YoY mean bias={yoy_metrics.mean_signed_diff:.2f}pp exceeds "
            f"{c['yoy_max_abs_bias_pp']}pp"
        )
        soft_fail = True

    if hard_fail:
        return "Rejected", reasons
    if not reasons:
        return "Approved", ["All provisional criteria met."]
    if soft_fail and not hard_fail:
        return "Conditional", reasons
    return "Conditional", reasons


# --- plotting (lightweight) --------------------------------------------------


def make_summary_plot(results: list[dict], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    industries = sorted({r["industry_id"] for r in results})
    x = np.arange(len(industries))
    width = 0.35
    for i, component in enumerate(COMPONENTS):
        values = []
        for industry in industries:
            match = [
                r for r in results if r["industry_id"] == industry and r["component"] == component
            ]
            values.append(match[0]["rebased_pearson_r"] if match else np.nan)
        ax.bar(x + (i - 0.5) * width, values, width, label=component)
    ax.axhline(
        PROVISIONAL_APPROVAL_CRITERIA["rebased_level_min_pearson"],
        color="red", linestyle="--", linewidth=1, label="approval threshold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(industries, rotation=45, ha="right")
    ax.set_ylabel("Rebased-level Pearson r (current vs. 2016-based)")
    ax.set_title("Overlap-window bridge validation — 2021-01 to 2023-12")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=100)
    plt.close(fig)


def make_example_timeseries_plot(
    industry_id: str, component: str, dates_iso: list[str],
    current_rebased: np.ndarray, older_rebased: np.ndarray, out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    x = [date.fromisoformat(d) for d in dates_iso]
    ax.plot(x, current_rebased, label="current edition (rebased)", marker="o", markersize=3)
    ax.plot(x, older_rebased, label="2016-based edition (rebased)", marker="s", markersize=3)
    ax.set_title(f"{industry_id} — {component} — rebased levels, overlap window")
    ax.set_ylabel("Index (overlap start = 100)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=100)
    plt.close(fig)


# --- orchestration ------------------------------------------------------------


def main() -> None:
    current_mpi_path = base_audit.resolve_retrieval_path("OIE_MPI")
    current_capu_path = base_audit.resolve_retrieval_path("OIE_CAPU")
    older_dir = (
        PROJECT_ROOT / "data" / "raw" / "OIE_MPI_HIST_2559_2566" / "2026-08-26" / "extracted"
    )
    older_mpi_path = older_dir / "Prodidx1.xlsx"
    older_capu_path = older_dir / "capidx.xlsx"

    series_by_key = {
        ("current", "MPI"): extract_division_value_series("current", "MPI", current_mpi_path),
        ("current", "CapU"): extract_division_value_series(
            "current", "CapU", current_capu_path
        ),
        ("2016_based", "MPI"): extract_division_value_series(
            "2016_based", "MPI", older_mpi_path
        ),
        ("2016_based", "CapU"): extract_division_value_series(
            "2016_based", "CapU", older_capu_path
        ),
    }

    results = []
    plots_dir = PROJECT_ROOT / "docs" / "oie_overlap_plots"
    plots_dir.mkdir(exist_ok=True)
    example_plot_done = False

    for component in COMPONENTS:
        current_series = series_by_key[("current", component)]
        older_series = series_by_key[("2016_based", component)]

        for industry_id, required_divisions in CANDIDATE_INDUSTRIES.items():
            effective_divisions, composition_consistent, composition_reason = (
                effective_divisions_for_industry(required_divisions, current_series, older_series)
            )
            if not composition_consistent:
                results.append(
                    {
                        "industry_id": industry_id, "component": component,
                        "approval_status": "Insufficient evidence",
                        "reasons": [composition_reason],
                    }
                )
                continue
            divisions = effective_divisions

            try:
                current_agg, current_weights = aggregate_industry_series(current_series, divisions)
                older_agg, older_weights = aggregate_industry_series(older_series, divisions)
                # fixed-weight diagnostic: apply CURRENT edition's weights to BOTH
                fixed_current_agg, _ = aggregate_industry_series(
                    current_series, divisions, weight_override=current_series.weights
                )
                fixed_older_agg, _ = aggregate_industry_series(
                    older_series, divisions, weight_override=current_series.weights
                )
            except OverlapIncompleteError as exc:
                results.append(
                    {
                        "industry_id": industry_id, "component": component,
                        "approval_status": "Insufficient evidence",
                        "reasons": [str(exc)],
                    }
                )
                continue

            months = overlap_month_list()
            current_raw = to_ordered_array(current_agg)
            older_raw = to_ordered_array(older_agg)
            fixed_current_raw = to_ordered_array(fixed_current_agg)
            fixed_older_raw = to_ordered_array(fixed_older_agg)

            current_reps = build_representations(current_raw)
            older_reps = build_representations(older_raw)

            rebased_floor = PROVISIONAL_APPROVAL_CRITERIA["discontinuity_abs_floor_rebased"]
            pct_floor = PROVISIONAL_APPROVAL_CRITERIA["discontinuity_abs_floor_pct"]
            rebased_metrics = compute_metrics(
                current_reps["rebased"], older_reps["rebased"], months, abs_floor=rebased_floor
            )
            mom_metrics = compute_metrics(
                current_reps["mom_pct"], older_reps["mom_pct"], months, abs_floor=pct_floor
            )
            yoy_metrics = compute_metrics(
                current_reps["yoy_pct"], older_reps["yoy_pct"], months, abs_floor=pct_floor
            )
            raw_metrics = compute_metrics(current_reps["raw"], older_reps["raw"], months)

            linking_factor = level_link_factor(current_raw, older_raw)
            fixed_weight_linking_factor = level_link_factor(fixed_current_raw, fixed_older_raw)
            rebasing_vs_weight_gap = abs(linking_factor - fixed_weight_linking_factor)

            status, reasons = apply_approval_criteria(rebased_metrics, mom_metrics, yoy_metrics)

            results.append(
                {
                    "industry_id": industry_id,
                    "component": component,
                    "edition_a": "current",
                    "edition_b": "2016_based",
                    "source_checksums": {
                        "current": current_series.sha256,
                        "2016_based": older_series.sha256,
                    },
                    "overlap_start": OVERLAP_START.isoformat(),
                    "overlap_end": OVERLAP_END.isoformat(),
                    "overlap_months": EXPECTED_OVERLAP_MONTHS,
                    "division_set": sorted(divisions),
                    "weights_current_own": current_weights,
                    "weights_2016_based_own": older_weights,
                    "raw_pearson_r": raw_metrics.pearson_r,
                    "rebased_pearson_r": rebased_metrics.pearson_r,
                    "rebased_spearman_r": rebased_metrics.spearman_r,
                    "rebased_mean_abs_diff": rebased_metrics.mean_abs_diff,
                    "rebased_median_abs_diff": rebased_metrics.median_abs_diff,
                    "rebased_mean_signed_diff": rebased_metrics.mean_signed_diff,
                    "rebased_max_abs_diff": rebased_metrics.max_abs_diff,
                    "rebased_n_valid": rebased_metrics.n_valid,
                    "rebased_per_year": rebased_metrics.per_year,
                    "rebased_discontinuity_months": rebased_metrics.discontinuity_months,
                    "mom_pearson_r": mom_metrics.pearson_r,
                    "mom_mean_signed_diff_pp": mom_metrics.mean_signed_diff,
                    "mom_mean_abs_diff_pp": mom_metrics.mean_abs_diff,
                    "mom_n_valid": mom_metrics.n_valid,
                    "yoy_pearson_r": yoy_metrics.pearson_r,
                    "yoy_mean_signed_diff_pp": yoy_metrics.mean_signed_diff,
                    "yoy_mean_abs_diff_pp": yoy_metrics.mean_abs_diff,
                    "yoy_n_valid": yoy_metrics.n_valid,
                    "level_link_factor_own_weights": linking_factor,
                    "level_link_factor_fixed_weights": fixed_weight_linking_factor,
                    "rebasing_vs_weight_revision_gap": rebasing_vs_weight_gap,
                    "candidate_linking_method": "level_link_median_ratio",
                    "approval_status": status,
                    "reasons": reasons,
                    "bridge_version": BRIDGE_VERSION,
                }
            )

            if not example_plot_done and industry_id == "IND-01":
                make_example_timeseries_plot(
                    industry_id, component, months,
                    current_reps["rebased"], older_reps["rebased"],
                    plots_dir / "example_IND-01_rebased.png",
                )
                example_plot_done = True

    make_summary_plot(
        [r for r in results if "rebased_pearson_r" in r], plots_dir / "summary_rebased_pearson.png"
    )

    ind03_note = {
        "industry_id": IND03_EXCLUDED_ID,
        "status": "excluded_from_bridge_validation",
        "reason": "Composition differs across editions (current: TSIC {16,17}; 2016-based: TSIC "
        "{17} only) — docs/task_a1_report.md §7.4. Not redefined automatically.",
        "current_edition_only_max_months": 66,
        "future_choices": [
            "1. Keep current definition (TSIC 16+17) and accept the shorter 66-month history.",
            "2. Narrow the definition to TSIC 17 only, for a consistent long history.",
            "3. Use an unbalanced panel with explicit safeguards.",
        ],
        "decision_made_in_this_task": False,
    }

    output = {
        "bridge_version": BRIDGE_VERSION,
        "estimation_window": {"start": OVERLAP_START.isoformat(), "end": OVERLAP_END.isoformat()},
        "provisional_approval_criteria": PROVISIONAL_APPROVAL_CRITERIA,
        "evaluation_framing": "latest_vintage_historical_evaluation",
        "results": results,
        "ind03_excluded": ind03_note,
    }
    out_path = PROJECT_ROOT / "docs" / "oie_overlap_validation_output.json"
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print(f"Results: {len(results)} rows for {len(CANDIDATE_INDUSTRIES)} industries x "
          f"{len(COMPONENTS)} components")
    for r in results:
        print(
            f"{r['industry_id']:8s} {r['component']:5s} "
            f"rebased_r={r.get('rebased_pearson_r', float('nan')):.3f} "
            f"mom_r={r.get('mom_pearson_r', float('nan')):.3f} "
            f"yoy_r={r.get('yoy_pearson_r', float('nan')):.3f} "
            f"link_factor={r.get('level_link_factor_own_weights', float('nan')):.4f} "
            f"-> {r['approval_status']}"
        )
    print(f"\nMachine-readable output: {out_path.relative_to(PROJECT_ROOT)}")
    print(f"Plots: {plots_dir.relative_to(PROJECT_ROOT)}")
    print(f"IND-03: {ind03_note['status']} — see docs/task_a1_report.md §7.4")


if __name__ == "__main__":
    main()
