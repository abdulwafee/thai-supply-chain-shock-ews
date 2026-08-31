"""Task A2.1 — corrected overlap-window bridge validation (oie_overlap_bridge_v2).

This script supersedes `scripts/validate_oie_overlap.py` (v1). v1 is left on
disk, unmodified, and its outputs are preserved — v2 writes to its own
`*_v2` files. Nothing here rewrites a v1 result.

Four correctness defects in v1 are fixed here:

1. **Signed bias was gated instead of mean absolute error.** v1 checked
   `abs(mean_signed_diff)` against thresholds documented as *mean absolute
   difference*, letting positive and negative monthly errors cancel. v2 gates
   on `mean_abs_error` and reports `mean_signed_bias` separately as a
   non-gating diagnostic. The two are never conflated: nothing in v2 calls
   `abs(mean signed error)` a mean absolute error.

2. **Both components got index-number treatment.** MPI is an index number, so
   month-over-month movement is ratio growth. Capacity Utilization is already
   a rate in percent, so its movement is a percentage-POINT difference, and a
   multiplicative median-ratio link is not appropriate for it. v2 uses ratio
   growth + multiplicative linking for MPI, and pp differences + additive
   alignment for CapU, with additive alignment justified against no alignment.

3. **Linked levels were never validated.** v1 rebased each edition to its own
   first month — forcing both series to start at exactly 100 — and then gated
   only on correlation. That hides level error: IND-01 MPI passed v1 with a
   rebased mean absolute error of 8.88 index points. v2 computes metrics
   directly between `current` and the actually-linked older series.

4. **A mechanical outlier rule acted as proof of rejection.** v1 hard-rejected
   any pair with a flagged discontinuity while approving pairs carrying large
   persistent level error. v2 investigates each flagged month down to the TSIC
   division level, and where the cause cannot be established from the data
   alone, returns `Needs source review` rather than a confident rejection.

v2 additionally builds and checks the actual candidate spliced series that v1
never constructed, with separate switch months for levels, MoM and YoY.

Approval criteria live in `configs/bridge_criteria_v2.yaml`, written before
these metrics were computed and applied mechanically.

Restrictions honored: no ML model is trained, no Industry Stress Index is
constructed, B1 ingestion is not started.

Usage:
    python scripts/validate_oie_overlap_v2.py
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import yaml

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    print("matplotlib is required: pip install matplotlib", file=sys.stderr)
    raise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_target_sources as base_audit  # noqa: E402
import validate_oie_overlap as v1  # noqa: E402  (extraction primitives only; v1 is not modified)

CRITERIA_PATH = PROJECT_ROOT / "configs" / "bridge_criteria_v2.yaml"
CRITERIA = yaml.safe_load(CRITERIA_PATH.read_text(encoding="utf-8"))
BRIDGE_VERSION = CRITERIA["bridge_version"]

OVERLAP_START = date(2021, 1, 1)
OVERLAP_END = date(2023, 12, 1)
EXPECTED_OVERLAP_MONTHS = 36

HISTORY_START = CRITERIA["splice"]["history_start"]
HISTORY_END = CRITERIA["splice"]["history_end"]
LEVEL_SWITCH_MONTH = CRITERIA["splice"]["level_switch_month"]

CANDIDATE_INDUSTRIES = v1.CANDIDATE_INDUSTRIES
IND03_EXCLUDED_ID = v1.IND03_EXCLUDED_ID
COMPONENTS = ("MPI", "CapU")

# component id -> key in the criteria file
CRITERIA_KEY = {"MPI": "mpi", "CapU": "capacity_utilization"}

STATUS_APPROVED = "Approved"
STATUS_CONDITIONAL = "Conditional"
STATUS_NEEDS_REVIEW = "Needs source review"
STATUS_REJECTED = "Rejected"
STATUS_INSUFFICIENT = "Insufficient evidence"
STATUS_EXCLUDED = "Excluded due to composition change"
ALL_STATUSES = (
    STATUS_EXCLUDED,
    STATUS_INSUFFICIENT,
    STATUS_REJECTED,
    STATUS_NEEDS_REVIEW,
    STATUS_CONDITIONAL,
    STATUS_APPROVED,
)


# --- month helpers ------------------------------------------------------------


def month_range(start: date, end: date) -> list[str]:
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(date(y, m, 1).isoformat())
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


def add_months(iso_month: str, delta: int) -> str:
    d = date.fromisoformat(iso_month)
    total = (d.year * 12 + (d.month - 1)) + delta
    return date(total // 12, total % 12 + 1, 1).isoformat()


OVERLAP_MONTHS = month_range(OVERLAP_START, OVERLAP_END)
HISTORY_MONTHS = month_range(HISTORY_START, HISTORY_END)


# --- aggregation over an arbitrary month window ------------------------------


class SeriesIncompleteError(ValueError):
    """A required division-month value is absent. Never imputed or padded."""


def aggregate_over_months(
    series: v1.DivisionValueSeries,
    divisions: list[int],
    months: list[str],
    weight_override: dict[int, float] | None = None,
) -> tuple[dict[str, float], dict[int, float]]:
    """Official-weight aggregation over exactly `months`, with the weights
    renormalized to sum to 1 across `divisions`. Never equal-weighted; never
    silently skips a missing month.
    """
    weights_to_use = weight_override if weight_override is not None else series.weights
    raw_weights = {d: weights_to_use[d] for d in divisions}
    total = sum(raw_weights.values())
    if total <= 0:
        raise ValueError(f"Non-positive total weight for divisions {divisions}: {raw_weights}")
    normalized = {d: w / total for d, w in raw_weights.items()}

    per_division: dict[int, dict[str, float]] = {}
    for d in divisions:
        available = series.values.get(d, {})
        missing = [m for m in months if m not in available]
        if missing:
            raise SeriesIncompleteError(
                f"{series.edition_id}/{series.component} division {d}: missing "
                f"{len(missing)} month(s) in requested window, first={missing[0]} — "
                "refusing to impute."
            )
        per_division[d] = available

    aggregated = {m: sum(normalized[d] * per_division[d][m] for d in divisions) for m in months}
    return aggregated, normalized


def to_array(series_dict: dict[str, float], months: list[str]) -> np.ndarray:
    return np.array([series_dict[m] for m in months], dtype=float)


# --- component-appropriate transformations -----------------------------------
# MPI: index number      -> ratio growth, reported in percent
# CapU: percent rate     -> arithmetic difference, reported in percentage points


def mpi_mom_growth_pct(x: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    out[1:] = (x[1:] / x[:-1] - 1.0) * 100.0
    return out


def mpi_yoy_growth_pct(x: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) > 12:
        out[12:] = (x[12:] / x[:-12] - 1.0) * 100.0
    return out


def capu_mom_change_pp(x: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    out[1:] = x[1:] - x[:-1]
    return out


def capu_yoy_change_pp(x: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) > 12:
        out[12:] = x[12:] - x[:-12]
    return out


def component_mom(x: np.ndarray, component: str) -> np.ndarray:
    return mpi_mom_growth_pct(x) if component == "MPI" else capu_mom_change_pp(x)


def component_yoy(x: np.ndarray, component: str) -> np.ndarray:
    return mpi_yoy_growth_pct(x) if component == "MPI" else capu_yoy_change_pp(x)


# --- linking ------------------------------------------------------------------


def multiplicative_link_factor(current: np.ndarray, older: np.ndarray) -> float:
    """Robust median of current/older. Appropriate for an index-number series."""
    return float(np.median(current / older))


def additive_link_offset(current: np.ndarray, older: np.ndarray) -> float:
    """Robust median of current-older, in percentage points. Appropriate for a
    rate already expressed in percent.
    """
    return float(np.median(current - older))


def apply_link(older: np.ndarray, method: str, param: float) -> np.ndarray:
    if method == "multiplicative_median_ratio":
        return older * param
    if method == "additive_median_offset":
        return older + param
    if method == "none":
        return older.copy()
    raise ValueError(f"Unknown link method: {method}")


# --- metrics ------------------------------------------------------------------


@dataclass
class ErrorMetrics:
    """Every field is a distinct concept. `mean_abs_error` and
    `mean_signed_bias` are never substituted for one another.
    """

    n_valid: int
    pearson_r: float
    spearman_r: float
    mean_abs_error: float
    rmse: float
    median_abs_error: float
    mean_signed_bias: float
    max_abs_error: float
    normalized_mae_iqr: float = float("nan")
    normalized_bias_iqr: float = float("nan")
    per_year: dict[str, dict[str, float]] = field(default_factory=dict)
    discontinuity_months: list[str] = field(default_factory=list)


def compute_error_metrics(
    current: np.ndarray,
    other: np.ndarray,
    months: list[str],
    abs_floor: float = 0.0,
    reference_for_iqr: np.ndarray | None = None,
) -> ErrorMetrics:
    mask = ~(np.isnan(current) | np.isnan(other))
    n_valid = int(mask.sum())
    if n_valid == 0:
        nan = float("nan")
        return ErrorMetrics(0, nan, nan, nan, nan, nan, nan, nan)

    err = current[mask] - other[mask]
    abs_err = np.abs(err)

    iqr = float("nan")
    if reference_for_iqr is not None:
        ref = reference_for_iqr[~np.isnan(reference_for_iqr)]
        if len(ref) >= 4:
            iqr = float(np.percentile(ref, 75) - np.percentile(ref, 25))

    per_year: dict[str, dict[str, float]] = {}
    for year in sorted({m[:4] for m, keep in zip(months, mask, strict=True) if keep}):
        ymask = np.array(
            [keep and m.startswith(year) for m, keep in zip(months, mask, strict=True)]
        )
        year_err = current[ymask] - other[ymask]
        has_pair = ymask.sum() >= 2
        per_year[year] = {
            "n_valid": int(ymask.sum()),
            "pearson_r": (
                v1.pearson(current[ymask], other[ymask]) if has_pair else float("nan")
            ),
            "mean_abs_error": float(np.mean(np.abs(year_err))) if ymask.sum() else float("nan"),
            "mean_signed_bias": float(np.mean(year_err)) if ymask.sum() else float("nan"),
        }

    median_abs = float(np.median(abs_err))
    threshold = max(CRITERIA["discontinuity"]["multiplier"] * median_abs, abs_floor)
    discontinuity_months = []
    if threshold > 0:
        valid_months = [m for m, keep in zip(months, mask, strict=True) if keep]
        for m, ae in zip(valid_months, abs_err, strict=True):
            if ae > threshold:
                discontinuity_months.append(m)

    mae = float(np.mean(abs_err))
    bias = float(np.mean(err))
    return ErrorMetrics(
        n_valid=n_valid,
        pearson_r=v1.pearson(current, other),
        spearman_r=v1.spearman(current, other),
        mean_abs_error=mae,
        rmse=float(np.sqrt(np.mean(err**2))),
        median_abs_error=median_abs,
        mean_signed_bias=bias,
        max_abs_error=float(np.max(abs_err)),
        normalized_mae_iqr=(mae / iqr) if iqr and not math.isnan(iqr) and iqr > 0 else float("nan"),
        normalized_bias_iqr=(
            (abs(bias) / iqr) if iqr and not math.isnan(iqr) and iqr > 0 else float("nan")
        ),
        per_year=per_year,
        discontinuity_months=discontinuity_months,
    )


# --- discontinuity investigation ----------------------------------------------


def early_overlap_transient(
    current: np.ndarray, linked_older: np.ndarray, n_early: int = 6
) -> dict:
    """Diagnostic ONLY — never gates approval.

    Added during v2 investigation after noticing that IND-01/IND-02 MPI carry
    their largest linked-level residuals in the current edition's very first
    months, which would matter for switch-month choice if it were an
    edition-wide start-up artifact. Computed across every pair specifically to
    test that hypothesis rather than generalize from two cases. It is reported,
    not gated, because it was defined after seeing v2 residuals — using it to
    move an approval status would be fitting a threshold to the results.
    """
    resid = np.abs(current - linked_older)
    early = float(np.mean(resid[:n_early]))
    rest = float(np.mean(resid[n_early:]))
    return {
        "n_early_months": n_early,
        "early_mean_abs_error": early,
        "later_mean_abs_error": rest,
        "ratio_early_over_later": (early / rest) if rest > 0 else float("nan"),
        "gating": False,
    }


def investigate_discontinuity(
    month: str,
    divisions: list[int],
    current_series: v1.DivisionValueSeries,
    older_series: v1.DivisionValueSeries,
    weights_current: dict[int, float],
    weights_older: dict[int, float],
    method: str,
    param: float,
) -> dict:
    """Decompose one flagged month down to TSIC division level.

    The industry residual is exactly separable into per-division contributions
    for both link methods, because each edition's renormalized weights sum to
    1: for a multiplicative factor f, f * sum_d(w_d * o_d) = sum_d(f * w_d * o_d);
    for an additive offset k, sum_d(w_d * o_d) + k = sum_d(w_d * (o_d + k)).

    No observation is removed. Where the evidence cannot establish a cause,
    the cause is reported as unresolved rather than guessed.
    """
    prev_month = add_months(month, -1)
    contributions = []
    for d in divisions:
        c_val = current_series.values[d][month]
        o_val = older_series.values[d][month]
        wc, wo = weights_current[d], weights_older[d]
        if method == "multiplicative_median_ratio":
            linked_term = param * wo * o_val
        elif method == "additive_median_offset":
            linked_term = wo * (o_val + param)
        else:
            linked_term = wo * o_val
        contribution = wc * c_val - linked_term

        c_prev = current_series.values[d].get(prev_month)
        o_prev = older_series.values[d].get(prev_month)
        contributions.append(
            {
                "division": d,
                "current_value": c_val,
                "older_value": o_val,
                "weight_current": wc,
                "weight_older": wo,
                "weight_delta": wc - wo,
                "residual_contribution": contribution,
                "current_own_mom": (c_val - c_prev) if c_prev is not None else None,
                "older_own_mom": (o_val - o_prev) if o_prev is not None else None,
            }
        )

    contributions.sort(key=lambda r: abs(r["residual_contribution"]), reverse=True)
    top = contributions[0]

    # Which edition actually moved at this month?
    moved_edition = "indeterminate"
    if top["current_own_mom"] is not None and top["older_own_mom"] is not None:
        c_mom, o_mom = top["current_own_mom"], top["older_own_mom"]
        if abs(c_mom - o_mom) > 1e-9:
            moved_edition = "current" if abs(c_mom) > abs(o_mom) else "2016_based"

    parsing_ok = all(
        isinstance(r["current_value"], float) and isinstance(r["older_value"], float)
        and not math.isnan(r["current_value"]) and not math.isnan(r["older_value"])
        for r in contributions
    )

    if abs(top["weight_delta"]) > 0.10:
        cause = "aggregation_weight_difference"
        resolved = True
        note = (
            f"TSIC {top['division']} carries a within-industry weight of "
            f"{top['weight_current']:.3f} in the current edition vs "
            f"{top['weight_older']:.3f} in the 2016-based edition "
            f"(delta {top['weight_delta']:+.3f}) — the editions are aggregating "
            "the same divisions in materially different proportions."
        )
    elif not parsing_ok:
        cause = "parsing_or_missing_value"
        resolved = True
        note = "A non-numeric or missing division value was encountered at this month."
    elif moved_edition != "indeterminate":
        cause = "edition_specific_movement_cause_unresolved"
        resolved = False
        note = (
            f"TSIC {top['division']} moved in the {moved_edition} edition and not "
            "the other at this month. The data alone cannot distinguish a source "
            "revision from a genuine series-definition change; that requires an "
            "OIE methodology or revision note, which has not been located. "
            "Reported, not removed."
        )
    else:
        cause = "unresolved"
        resolved = False
        note = (
            "No single division dominates and no edition-specific movement is "
            "identifiable at this month. Cause unresolved."
        )

    return {
        "month": month,
        "dominant_division": top["division"],
        "dominant_residual_contribution": top["residual_contribution"],
        "which_edition_moved": moved_edition,
        "cause": cause,
        "cause_resolved": resolved,
        "note": note,
        "division_detail": contributions,
    }


# --- candidate splice ---------------------------------------------------------


def build_candidate_splice(
    current_full: dict[str, float],
    older_full: dict[str, float],
    component: str,
    method: str,
    param: float,
) -> dict:
    """Build the actual spliced monthly series v1 never constructed.

    Level: linked older-edition values before the switch, native current-edition
    values from the switch onward.

    MoM/YoY carry their OWN switch months, because the current edition cannot
    produce those lags at its own first months without borrowing a differently
    scaled edition's values:
      - the current edition has no 2020-12 observation, so its first native MoM
        is 2021-02, not 2021-01;
      - the current edition has no 2020 observations, so its first native YoY is
        2022-01, not 2021-01.
    A single universal switch month is therefore not claimed.
    """
    level: dict[str, float] = {}
    source_by_month: dict[str, str] = {}
    for m in HISTORY_MONTHS:
        if m < LEVEL_SWITCH_MONTH.isoformat():
            if m not in older_full:
                raise SeriesIncompleteError(f"older edition missing {m} for level splice")
            linked = apply_link(np.array([older_full[m]]), method, param)[0]
            level[m] = float(linked)
            source_by_month[m] = "2016_based_linked"
        else:
            if m not in current_full:
                raise SeriesIncompleteError(f"current edition missing {m} for level splice")
            level[m] = float(current_full[m])
            source_by_month[m] = "current_native"

    keys = list(level.keys())
    no_duplicates = len(keys) == len(set(keys))
    no_gaps = keys == HISTORY_MONTHS

    # --- boundary jump, measured in the component's own units ---------------
    switch = LEVEL_SWITCH_MONTH.isoformat()
    prev = add_months(switch, -1)
    if component == "MPI":
        boundary_jump = (level[switch] / level[prev] - 1.0) * 100.0
        ordinary = [
            (level[b] / level[a] - 1.0) * 100.0
            for a, b in zip(HISTORY_MONTHS, HISTORY_MONTHS[1:], strict=False)
            if not (a == prev and b == switch)
        ]
        unit = "percent_growth"
    else:
        boundary_jump = level[switch] - level[prev]
        ordinary = [
            level[b] - level[a]
            for a, b in zip(HISTORY_MONTHS, HISTORY_MONTHS[1:], strict=False)
            if not (a == prev and b == switch)
        ]
        unit = "percentage_points"

    abs_ordinary = np.abs(np.array(ordinary))
    p99 = float(np.percentile(abs_ordinary, 99))
    median_abs = float(np.median(abs_ordinary))
    abs_jump = abs(boundary_jump)
    pct_rank = float((abs_ordinary < abs_jump).mean() * 100.0)

    # --- MoM candidate: older-native through the switch, current-native after
    mom_switch = add_months(switch, 1)  # 2021-02
    mom: dict[str, float] = {}
    mom_source: dict[str, str] = {}
    for i, m in enumerate(HISTORY_MONTHS):
        if i == 0:
            continue  # no prior month exists at all
        prev_m = HISTORY_MONTHS[i - 1]
        if m < mom_switch:
            if m in older_full and prev_m in older_full:
                mom[m] = (
                    (older_full[m] / older_full[prev_m] - 1.0) * 100.0
                    if component == "MPI"
                    else older_full[m] - older_full[prev_m]
                )
                mom_source[m] = "2016_based_native"
        else:
            if m in current_full and prev_m in current_full:
                mom[m] = (
                    (current_full[m] / current_full[prev_m] - 1.0) * 100.0
                    if component == "MPI"
                    else current_full[m] - current_full[prev_m]
                )
                mom_source[m] = "current_native"

    # --- YoY candidate: older-native through 2021-12, current-native from 2022-01
    yoy_switch = "2022-01-01"
    yoy: dict[str, float] = {}
    yoy_source: dict[str, str] = {}
    for i, m in enumerate(HISTORY_MONTHS):
        if i < 12:
            continue
        lag_m = HISTORY_MONTHS[i - 12]
        if m < yoy_switch:
            if m in older_full and lag_m in older_full:
                yoy[m] = (
                    (older_full[m] / older_full[lag_m] - 1.0) * 100.0
                    if component == "MPI"
                    else older_full[m] - older_full[lag_m]
                )
                yoy_source[m] = "2016_based_native"
        else:
            if m in current_full and lag_m in current_full:
                yoy[m] = (
                    (current_full[m] / current_full[lag_m] - 1.0) * 100.0
                    if component == "MPI"
                    else current_full[m] - current_full[lag_m]
                )
                yoy_source[m] = "current_native"

    cross_edition_lag_used = any(
        (m in current_full) != (HISTORY_MONTHS[HISTORY_MONTHS.index(m) - 1] in current_full)
        and mom_source.get(m) == "current_native"
        for m in mom
    )

    return {
        "level_months": HISTORY_MONTHS,
        "level_values": level,
        "level_source_by_month": source_by_month,
        "level_switch_month": switch,
        "mom_switch_month": mom_switch,
        "yoy_switch_month": yoy_switch,
        "level_month_count": len(level),
        "level_no_duplicate_keys": no_duplicates,
        "level_no_gaps": no_gaps,
        "boundary_jump": boundary_jump,
        "boundary_jump_unit": unit,
        "boundary_jump_abs": abs_jump,
        "ordinary_abs_change_median": median_abs,
        "ordinary_abs_change_p99": p99,
        "boundary_jump_vs_p99_ratio": (abs_jump / p99) if p99 > 0 else float("nan"),
        "boundary_jump_percentile_rank": pct_rank,
        "mom_values": mom,
        "mom_source_by_month": mom_source,
        "mom_month_count": len(mom),
        "yoy_values": yoy,
        "yoy_source_by_month": yoy_source,
        "yoy_month_count": len(yoy),
        "invalid_cross_edition_lag_used": bool(cross_edition_lag_used),
    }


# --- approval -----------------------------------------------------------------


def apply_approval_criteria_v2(
    component: str,
    linked: ErrorMetrics,
    mom: ErrorMetrics,
    yoy: ErrorMetrics,
    splice: dict,
    findings: list[dict],
) -> tuple[str, list[str]]:
    """Mechanically apply configs/bridge_criteria_v2.yaml.

    Gating uses mean_abs_error. mean_signed_bias is reported but never
    substituted for it.
    """
    ck = CRITERIA[CRITERIA_KEY[component]]
    lvl_c = ck["linked_level"]
    mom_c = ck["mom_growth"] if component == "MPI" else ck["mom_change"]
    yoy_c = ck["yoy_growth"] if component == "MPI" else ck["yoy_change"]
    hard = CRITERIA["hard_fail"]
    reasons: list[str] = []

    if linked.n_valid < CRITERIA["evidence"]["min_valid_pairs"]:
        return STATUS_INSUFFICIENT, [
            f"Only {linked.n_valid} valid paired overlap months "
            f"(< {CRITERIA['evidence']['min_valid_pairs']})."
        ]

    # --- hard fails -> Rejected -------------------------------------------
    hard_reasons: list[str] = []
    if math.isnan(linked.pearson_r) or linked.pearson_r < hard["linked_level_min_pearson"]:
        hard_reasons.append(
            f"Linked-level Pearson r={linked.pearson_r:.3f} below hard-fail floor "
            f"{hard['linked_level_min_pearson']}."
        )
    gross = lvl_c["max_normalized_mae_iqr"] * hard["normalized_mae_iqr_multiple"]
    if not math.isnan(linked.normalized_mae_iqr) and linked.normalized_mae_iqr > gross:
        hard_reasons.append(
            f"Linked-level normalized MAE={linked.normalized_mae_iqr:.3f} exceeds gross-misfit "
            f"bound {gross:.3f} (MAE {linked.mean_abs_error:.3f} vs series IQR)."
        )
    jump_ratio = splice.get("boundary_jump_vs_p99_ratio", float("nan"))
    if not math.isnan(jump_ratio) and jump_ratio > CRITERIA["splice"]["max_boundary_jump_vs_p99"]:
        hard_reasons.append(
            f"Splice boundary jump {splice['boundary_jump']:.3f} "
            f"({splice['boundary_jump_unit']}) is {jump_ratio:.2f}x the 99th percentile of "
            "ordinary monthly changes — the splice itself would manufacture a shock."
        )
    if splice.get("invalid_cross_edition_lag_used"):
        hard_reasons.append("Candidate MoM series would use an invalid cross-edition lag.")
    if not splice.get("level_no_gaps") or not splice.get("level_no_duplicate_keys"):
        hard_reasons.append("Spliced level series has a gap or duplicate month key.")
    if hard_reasons:
        return STATUS_REJECTED, hard_reasons

    # --- soft criteria ------------------------------------------------------
    if linked.pearson_r < lvl_c["min_pearson"]:
        reasons.append(
            f"Linked-level Pearson r={linked.pearson_r:.3f} < {lvl_c['min_pearson']}."
        )
    if not math.isnan(linked.spearman_r) and linked.spearman_r < lvl_c["min_spearman"]:
        reasons.append(
            f"Linked-level Spearman r={linked.spearman_r:.3f} < {lvl_c['min_spearman']}."
        )
    if (
        not math.isnan(linked.normalized_mae_iqr)
        and linked.normalized_mae_iqr > lvl_c["max_normalized_mae_iqr"]
    ):
        reasons.append(
            f"Linked-level normalized MAE={linked.normalized_mae_iqr:.3f} > "
            f"{lvl_c['max_normalized_mae_iqr']} (mean absolute error "
            f"{linked.mean_abs_error:.3f} against the current series' IQR)."
        )
    if (
        not math.isnan(linked.normalized_bias_iqr)
        and linked.normalized_bias_iqr > lvl_c["max_abs_normalized_bias_iqr"]
    ):
        reasons.append(
            f"Linked-level normalized |bias|={linked.normalized_bias_iqr:.3f} > "
            f"{lvl_c['max_abs_normalized_bias_iqr']} (signed bias "
            f"{linked.mean_signed_bias:+.3f})."
        )
    for year, stats in linked.per_year.items():
        r = stats["pearson_r"]
        if not math.isnan(r) and r < CRITERIA["stability"]["min_year_linked_level_pearson"]:
            reasons.append(f"Year {year} linked-level Pearson r={r:.3f} below stability bar.")

    label = "growth" if component == "MPI" else "change"
    if math.isnan(mom.pearson_r) or mom.pearson_r < mom_c["min_pearson"]:
        reasons.append(f"MoM {label} Pearson r={mom.pearson_r:.3f} < {mom_c['min_pearson']}.")
    if mom.mean_abs_error > mom_c["max_mae_pp"]:
        reasons.append(
            f"MoM {label} mean ABSOLUTE error={mom.mean_abs_error:.3f}pp > "
            f"{mom_c['max_mae_pp']}pp (signed bias was {mom.mean_signed_bias:+.3f}pp — "
            "reported separately, not gated on)."
        )
    if math.isnan(yoy.pearson_r) or yoy.pearson_r < yoy_c["min_pearson"]:
        reasons.append(f"YoY {label} Pearson r={yoy.pearson_r:.3f} < {yoy_c['min_pearson']}.")
    if yoy.mean_abs_error > yoy_c["max_mae_pp"]:
        reasons.append(
            f"YoY {label} mean ABSOLUTE error={yoy.mean_abs_error:.3f}pp > "
            f"{yoy_c['max_mae_pp']}pp (signed bias was {yoy.mean_signed_bias:+.3f}pp — "
            "reported separately, not gated on)."
        )

    unresolved = [f for f in findings if not f["cause_resolved"]]
    if unresolved:
        months = [f["month"] for f in unresolved]
        reasons.append(
            f"Discontinuity at {months} investigated to division level but cause "
            "unresolved from the data alone — requires an OIE source/methodology check."
        )
        return STATUS_NEEDS_REVIEW, reasons

    if reasons:
        return STATUS_CONDITIONAL, reasons
    return STATUS_APPROVED, ["All criteria in configs/bridge_criteria_v2.yaml met."]


# --- plots --------------------------------------------------------------------


def make_pair_diagnostic_figure(result: dict, arrays: dict, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.5))
    ind, comp = result["industry_id"], result["component"]
    x = [date.fromisoformat(m) for m in OVERLAP_MONTHS]
    unit = "index points" if comp == "MPI" else "percentage points"

    ax = axes[0][0]
    ax.plot(x, arrays["current"], label="current", marker="o", markersize=2.5)
    ax.plot(x, arrays["linked_older"], label="2016-based (linked)", marker="s", markersize=2.5)
    ax.set_title(f"{ind} {comp} — linked levels ({result['link_method']})")
    ax.set_ylabel(unit)
    ax.legend(fontsize=8)

    ax = axes[0][1]
    resid = arrays["current"] - arrays["linked_older"]
    ax.plot(x, resid, color="crimson", marker="o", markersize=2.5)
    ax.axhline(0, color="black", linewidth=0.8)
    for m in result["linked_level_discontinuity_months"]:
        ax.axvline(date.fromisoformat(m), color="orange", linestyle="--", linewidth=1)
    ax.set_title(f"residuals (MAE={result['linked_mean_abs_error']:.2f} {unit})")

    ax = axes[0][2]
    ax.plot(x, arrays["cur_mom"], label="current", marker="o", markersize=2.5)
    ax.plot(x, arrays["old_mom"], label="2016-based", marker="s", markersize=2.5)
    ax.set_title(f"MoM ({'growth %' if comp == 'MPI' else 'pp change'}) "
                 f"MAE={result['mom_mean_abs_error_pp']:.2f}")
    ax.legend(fontsize=8)

    ax = axes[1][0]
    ax.plot(x, arrays["cur_yoy"], label="current", marker="o", markersize=2.5)
    ax.plot(x, arrays["old_yoy"], label="2016-based", marker="s", markersize=2.5)
    ax.set_title(f"YoY ({'growth %' if comp == 'MPI' else 'pp change'}) "
                 f"MAE={result['yoy_mean_abs_error_pp']:.2f}")
    ax.legend(fontsize=8)

    ax = axes[1][1]
    findings = result.get("discontinuity_findings", [])
    if findings:
        f0 = findings[0]
        detail = f0["division_detail"][:6]
        labels = [f"TSIC {r['division']}" for r in detail]
        ax.bar(labels, [r["residual_contribution"] for r in detail], color="steelblue")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(f"division residuals at {f0['month']}\n(moved: {f0['which_edition_moved']})",
                     fontsize=9)
        ax.tick_params(axis="x", rotation=45, labelsize=7)
    else:
        ax.text(0.5, 0.5, "no flagged discontinuity", ha="center", va="center")
        ax.set_axis_off()

    ax = axes[1][2]
    sp = result["splice"]
    hx = [date.fromisoformat(m) for m in sp["level_months"]]
    hv = [sp["level_values"][m] for m in sp["level_months"]]
    ax.plot(hx, hv, linewidth=1)
    ax.axvline(date.fromisoformat(sp["level_switch_month"]), color="red", linestyle="--",
               linewidth=1.2, label="level switch")
    ax.set_title(f"candidate splice — boundary jump {sp['boundary_jump']:.2f}\n"
                 f"({sp['boundary_jump_vs_p99_ratio']:.2f}x p99 ordinary)", fontsize=9)
    ax.legend(fontsize=8)

    fig.suptitle(f"{ind} — {comp} — {result['approval_status']}", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=72)
    plt.close(fig)


def make_splice_boundary_figure(result: dict, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.2))
    sp = result["splice"]
    hx = [date.fromisoformat(m) for m in sp["level_months"]]
    hv = [sp["level_values"][m] for m in sp["level_months"]]
    ax.plot(hx, hv, linewidth=1)
    ax.axvline(date.fromisoformat(sp["level_switch_month"]), color="red", linestyle="--",
               linewidth=1.2, label="level switch 2021-01")
    ax.set_title(f"{result['industry_id']} {result['component']} candidate splice — "
                 f"boundary jump {sp['boundary_jump']:.2f} "
                 f"({sp['boundary_jump_vs_p99_ratio']:.2f}x p99)", fontsize=9)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=72)
    plt.close(fig)


def make_summary_figure(results: list[dict], out_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, comp in zip(axes, COMPONENTS, strict=True):
        rows = [r for r in results if r["component"] == comp and "linked_normalized_mae_iqr" in r]
        rows.sort(key=lambda r: r["industry_id"])
        names = [r["industry_id"] for r in rows]
        vals = [r["linked_normalized_mae_iqr"] for r in rows]
        colors = {
            STATUS_APPROVED: "seagreen", STATUS_CONDITIONAL: "goldenrod",
            STATUS_NEEDS_REVIEW: "darkorange", STATUS_REJECTED: "firebrick",
        }
        ax.bar(names, vals, color=[colors.get(r["approval_status"], "grey") for r in rows])
        bar = CRITERIA[CRITERIA_KEY[comp]]["linked_level"]["max_normalized_mae_iqr"]
        ax.axhline(bar, color="red", linestyle="--", linewidth=1, label=f"bar {bar}")
        ax.set_title(f"{comp} — linked-level normalized MAE (lower is better)")
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.legend(fontsize=8)
    fig.suptitle("oie_overlap_bridge_v2 — linked-level error vs approval bar", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=72)
    plt.close(fig)


# --- json safety --------------------------------------------------------------


def json_safe(obj):
    """Convert non-finite floats to None so the output is strictly valid JSON."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, (np.floating, np.integer)):
        return json_safe(float(obj))
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


# --- orchestration ------------------------------------------------------------


def main() -> None:
    older_dir = (
        PROJECT_ROOT / "data" / "raw" / "OIE_MPI_HIST_2559_2566" / "2026-08-26" / "extracted"
    )
    series_by_key = {
        ("current", "MPI"): v1.extract_division_value_series(
            "current", "MPI", base_audit.resolve_retrieval_path("OIE_MPI")
        ),
        ("current", "CapU"): v1.extract_division_value_series(
            "current", "CapU", base_audit.resolve_retrieval_path("OIE_CAPU")
        ),
        ("2016_based", "MPI"): v1.extract_division_value_series(
            "2016_based", "MPI", older_dir / "Prodidx1.xlsx"
        ),
        ("2016_based", "CapU"): v1.extract_division_value_series(
            "2016_based", "CapU", older_dir / "capidx.xlsx"
        ),
    }

    plots_dir = PROJECT_ROOT / "docs" / "oie_overlap_plots_v2"
    plots_dir.mkdir(exist_ok=True)
    results: list[dict] = []

    current_native_months = month_range(date(2021, 1, 1), HISTORY_END)
    older_native_months = month_range(HISTORY_START, date(2023, 12, 1))

    for component in COMPONENTS:
        cur_series = series_by_key[("current", component)]
        old_series = series_by_key[("2016_based", component)]

        for industry_id, required in CANDIDATE_INDUSTRIES.items():
            divisions, consistent, reason = v1.effective_divisions_for_industry(
                required, cur_series, old_series
            )
            if not consistent:
                results.append({
                    "industry_id": industry_id, "component": component,
                    "approval_status": STATUS_EXCLUDED, "reasons": [reason],
                    "bridge_version": BRIDGE_VERSION,
                })
                continue

            try:
                cur_overlap, w_cur = aggregate_over_months(cur_series, divisions, OVERLAP_MONTHS)
                old_overlap, w_old = aggregate_over_months(old_series, divisions, OVERLAP_MONTHS)
                cur_full, _ = aggregate_over_months(cur_series, divisions, current_native_months)
                old_full, _ = aggregate_over_months(old_series, divisions, older_native_months)
            except SeriesIncompleteError as exc:
                results.append({
                    "industry_id": industry_id, "component": component,
                    "approval_status": STATUS_INSUFFICIENT, "reasons": [str(exc)],
                    "bridge_version": BRIDGE_VERSION,
                })
                continue

            current = to_array(cur_overlap, OVERLAP_MONTHS)
            older = to_array(old_overlap, OVERLAP_MONTHS)

            # --- linking, component-appropriate --------------------------------
            alignment_comparison = {}
            if component == "MPI":
                method = "multiplicative_median_ratio"
                param = multiplicative_link_factor(current, older)
                alignment_justification = (
                    "MPI is an index number; a multiplicative median-ratio factor puts the "
                    "older edition on the current edition's scale without distorting its "
                    "growth rates."
                )
            else:
                offset = additive_link_offset(current, older)
                mae_additive = float(np.mean(np.abs(current - (older + offset))))
                mae_none = float(np.mean(np.abs(current - older)))
                alignment_comparison = {
                    "additive_offset_pp": offset,
                    "linked_level_mae_with_additive": mae_additive,
                    "linked_level_mae_without_alignment": mae_none,
                    "selection_rule": CRITERIA["capacity_utilization"][
                        "alignment_selection_rule"
                    ],
                }
                if mae_additive < mae_none:
                    method, param = "additive_median_offset", offset
                    alignment_justification = (
                        f"Capacity Utilization is a percent rate, so alignment is additive. The "
                        f"median offset of {offset:+.3f}pp reduces linked-level mean absolute "
                        f"error from {mae_none:.3f} to {mae_additive:.3f}pp, so it is adopted."
                    )
                else:
                    method, param = "none", 0.0
                    alignment_justification = (
                        f"Capacity Utilization is a percent rate. The median additive offset "
                        f"({offset:+.3f}pp) does NOT reduce linked-level mean absolute error "
                        f"({mae_additive:.3f} vs {mae_none:.3f}pp unaligned), so per the "
                        "pre-stated selection rule no alignment is applied."
                    )

            linked_older = apply_link(older, method, param)

            # --- metrics on ACTUAL linked levels, not independently rebased ----
            linked_metrics = compute_error_metrics(
                current, linked_older, OVERLAP_MONTHS,
                abs_floor=CRITERIA["discontinuity"]["abs_floor_linked_level"],
                reference_for_iqr=current,
            )
            cur_mom = component_mom(current, component)
            old_mom = component_mom(older, component)
            cur_yoy = component_yoy(current, component)
            old_yoy = component_yoy(older, component)
            pct_floor = CRITERIA["discontinuity"]["abs_floor_pct"]
            mom_metrics = compute_error_metrics(
                cur_mom, old_mom, OVERLAP_MONTHS, abs_floor=pct_floor
            )
            yoy_metrics = compute_error_metrics(
                cur_yoy, old_yoy, OVERLAP_MONTHS, abs_floor=pct_floor
            )

            findings = [
                investigate_discontinuity(
                    m, divisions, cur_series, old_series, w_cur, w_old, method, param
                )
                for m in linked_metrics.discontinuity_months
            ]

            splice = build_candidate_splice(cur_full, old_full, component, method, param)
            status, reasons = apply_approval_criteria_v2(
                component, linked_metrics, mom_metrics, yoy_metrics, splice, findings
            )

            result = {
                "industry_id": industry_id,
                "component": component,
                "edition_a": "current",
                "edition_b": "2016_based",
                "source_checksums": {
                    "current": cur_series.sha256, "2016_based": old_series.sha256,
                },
                "overlap_start": OVERLAP_START.isoformat(),
                "overlap_end": OVERLAP_END.isoformat(),
                "overlap_months": EXPECTED_OVERLAP_MONTHS,
                "division_set": sorted(divisions),
                "weights_current_own": w_cur,
                "weights_2016_based_own": w_old,
                "series_type": CRITERIA[CRITERIA_KEY[component]]["series_type"],
                "link_method": method,
                "link_param": param,
                "alignment_comparison": alignment_comparison,
                "alignment_justification": alignment_justification,
                # linked levels (the representation v1 never evaluated)
                "linked_pearson_r": linked_metrics.pearson_r,
                "linked_spearman_r": linked_metrics.spearman_r,
                "linked_mean_abs_error": linked_metrics.mean_abs_error,
                "linked_rmse": linked_metrics.rmse,
                "linked_median_abs_error": linked_metrics.median_abs_error,
                "linked_mean_signed_bias": linked_metrics.mean_signed_bias,
                "linked_max_abs_error": linked_metrics.max_abs_error,
                "linked_normalized_mae_iqr": linked_metrics.normalized_mae_iqr,
                "linked_normalized_bias_iqr": linked_metrics.normalized_bias_iqr,
                "linked_n_valid": linked_metrics.n_valid,
                "linked_per_year": linked_metrics.per_year,
                "linked_level_discontinuity_months": linked_metrics.discontinuity_months,
                "discontinuity_findings": findings,
                "early_overlap_transient_diagnostic": early_overlap_transient(
                    current, linked_older
                ),
                # growth / change representations
                "mom_pearson_r": mom_metrics.pearson_r,
                "mom_mean_abs_error_pp": mom_metrics.mean_abs_error,
                "mom_mean_signed_bias_pp": mom_metrics.mean_signed_bias,
                "mom_n_valid": mom_metrics.n_valid,
                "yoy_pearson_r": yoy_metrics.pearson_r,
                "yoy_mean_abs_error_pp": yoy_metrics.mean_abs_error,
                "yoy_mean_signed_bias_pp": yoy_metrics.mean_signed_bias,
                "yoy_n_valid": yoy_metrics.n_valid,
                "splice": splice,
                "approval_status": status,
                "reasons": reasons,
                "bridge_version": BRIDGE_VERSION,
            }

            arrays = {
                "current": current, "linked_older": linked_older,
                "cur_mom": cur_mom, "old_mom": old_mom,
                "cur_yoy": cur_yoy, "old_yoy": old_yoy,
            }
            plot_paths = []
            if status != STATUS_APPROVED:
                p = plots_dir / f"{industry_id}_{component}_diagnostic.png"
                make_pair_diagnostic_figure(result, arrays, p)
                plot_paths.append(str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"))
            p2 = plots_dir / f"{industry_id}_{component}_splice_boundary.png"
            make_splice_boundary_figure(result, p2)
            plot_paths.append(str(p2.relative_to(PROJECT_ROOT)).replace("\\", "/"))
            result["diagnostic_plots"] = plot_paths
            results.append(result)

    make_summary_figure(results, plots_dir / "summary_linked_level_error.png")

    status_counts = {s: sum(1 for r in results if r["approval_status"] == s) for s in ALL_STATUSES}
    approved = {
        c: sorted(r["industry_id"] for r in results
                  if r["component"] == c and r["approval_status"] == STATUS_APPROVED)
        for c in COMPONENTS
    }
    both = sorted(set(approved["MPI"]) & set(approved["CapU"]))

    output = {
        "bridge_version": BRIDGE_VERSION,
        "supersedes": "oie_overlap_bridge_v1_2026-08-26",
        "v1_outputs_preserved": {
            "docs/oie_overlap_validation.md": "unmodified",
            "docs/oie_overlap_validation_output.json": "unmodified",
            "scripts/validate_oie_overlap.py": "unmodified",
        },
        "criteria_file": "configs/bridge_criteria_v2.yaml",
        "criteria": CRITERIA,
        "estimation_window": {
            "start": OVERLAP_START.isoformat(), "end": OVERLAP_END.isoformat(),
        },
        "evaluation_framing": "latest_vintage_historical_evaluation",
        "switch_months": {
            "level": LEVEL_SWITCH_MONTH.isoformat(),
            "mom": add_months(LEVEL_SWITCH_MONTH.isoformat(), 1),
            "yoy": "2022-01-01",
            "note": "Separate by representation. A single universal switch month is not claimed.",
        },
        "status_counts": status_counts,
        "result_row_count": len(results),
        "approved_by_component": approved,
        "approved_both_components": both,
        "results": results,
        "ind03_excluded": {
            "industry_id": IND03_EXCLUDED_ID,
            "status": "excluded_from_bridge_validation",
            "reason": "Composition differs across editions (current TSIC {16,17}; 2016-based "
                      "TSIC {17} only) — docs/task_a1_report.md §7.4.",
            "current_edition_only_max_months": 66,
            "future_choices": [
                "1. Keep current definition (TSIC 16+17), accept 66-month history.",
                "2. Narrow to TSIC 17 only for a consistent long history.",
                "3. Unbalanced panel with explicit safeguards.",
            ],
            "decision_made_in_this_task": False,
        },
    }

    out_path = PROJECT_ROOT / "docs" / "oie_overlap_validation_output_v2.json"
    out_path.write_text(
        json.dumps(json_safe(output), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"v2 results: {len(results)} rows")
    for r in sorted(results, key=lambda r: (r["component"], r["industry_id"])):
        if "linked_mean_abs_error" not in r:
            print(f"{r['industry_id']:8s} {r['component']:5s} -> {r['approval_status']}")
            continue
        sp = r["splice"]
        print(
            f"{r['industry_id']:8s} {r['component']:5s} "
            f"lvlMAE={r['linked_mean_abs_error']:6.2f} "
            f"nMAE={r['linked_normalized_mae_iqr']:5.3f} "
            f"momMAE={r['mom_mean_abs_error_pp']:5.2f} "
            f"yoyMAE={r['yoy_mean_abs_error_pp']:5.2f} "
            f"jump={sp['boundary_jump']:+6.2f}({sp['boundary_jump_vs_p99_ratio']:.2f}xp99) "
            f"-> {r['approval_status']}"
        )
    print("\nstatus counts:", {k: v for k, v in status_counts.items() if v})
    print("approved MPI :", approved["MPI"])
    print("approved CapU:", approved["CapU"])
    print("approved BOTH:", both)
    print(f"\nOutput: {out_path.relative_to(PROJECT_ROOT)}")
    print(f"Plots : {plots_dir.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
