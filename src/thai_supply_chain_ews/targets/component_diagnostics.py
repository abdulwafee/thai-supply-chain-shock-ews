"""MPI-CapU redundancy diagnostics (Task B2).

Answers one narrow question empirically: do MPI and Capacity Utilization carry
sufficiently distinct adverse-shock information to justify a two-component MVP
Stress Index?

Two things this module deliberately does NOT do:

* It does not build the composite Stress Index. B2 decides whether a K=2
  equal-weight composite is defensible; constructing it is a later task.
* It does not produce leakage-safe normalization. The percentile ranks here use
  the full diagnostic sample and are labelled `diagnostic_only_full_sample_rank`
  for exactly that reason. Training-only / expanding-history normalization is
  Task B3.

Interpretation guardrails, enforced in wording throughout:

* `non_redundant` means "not empirically duplicative under the pre-registered
  gate". It does NOT mean statistically independent.
* Low correlation is not automatically useful information, and high correlation
  is not automatically duplication. That is why the gate combines correlation
  with high-stress episode overlap and component-specific episodes rather than
  reading a single coefficient.
* The lead-lag table is descriptive association only. No causal or
  shock-transmission claim follows from it.

All thresholds live in `configs/component_redundancy_gate.yaml`, written before
any result here was computed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

__all__ = [
    "ComponentSemanticsError",
    "B2InvariantError",
    "DEFAULT_GATE_PATH",
    "DiagnosticSample",
    "build_diagnostic_sample",
    "capu_adverse_yoy_pp",
    "classify_redundancy",
    "diagnostic_percentile_rank",
    "high_stress_overlap",
    "industry_correlations",
    "lead_lag_table",
    "load_gate",
    "moving_block_spearman_ci",
    "mpi_adverse_yoy",
    "pooled_correlations",
    "quality_checks",
    "run_diagnostics",
    "spearman",
    "validate_b1_invariants",
]

DEFAULT_GATE_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "component_redundancy_gate.yaml"
)
DEFAULT_PANEL_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "processed" / "industry_month_panel.parquet"
)

MPI_COMPONENT = "mpi"
CAPU_COMPONENT = "capu"
COMPONENTS = (MPI_COMPONENT, CAPU_COMPONENT)


class ComponentSemanticsError(ValueError):
    """An adverse-change transform received input it must not silently accept."""


class B2InvariantError(RuntimeError):
    """The B1 panel does not satisfy a material invariant B2 depends on.

    B2 stops rather than repairing or reinterpreting the data.
    """


def load_gate(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else DEFAULT_GATE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Redundancy gate config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --- component semantics -----------------------------------------------------


def mpi_adverse_yoy(current: np.ndarray, lagged: np.ndarray) -> np.ndarray:
    """-100 * (mpi_t / mpi_{t-12} - 1). Positive = production deterioration.

    Fails explicitly on a zero or non-positive denominator rather than emitting
    an infinity or a sign-flipped value.
    """
    current = np.asarray(current, dtype=float)
    lagged = np.asarray(lagged, dtype=float)
    bad = ~np.isnan(lagged) & (lagged <= 0)
    if bad.any():
        raise ComponentSemanticsError(
            f"MPI denominator is zero or non-positive at {int(bad.sum())} observation(s); "
            "refusing to compute a year-over-year ratio."
        )
    return -100.0 * (current / lagged - 1.0)


def capu_adverse_yoy_pp(current: np.ndarray, lagged: np.ndarray) -> np.ndarray:
    """-(capu_t - capu_{t-12}), in PERCENTAGE POINTS.

    Capacity Utilization is already a rate in percent, so its year-over-year
    movement is an additive difference. A relative percentage change or a
    multiplicative ratio would be the wrong quantity, and labelling a relative
    change "pp" would be the wrong unit.
    """
    current = np.asarray(current, dtype=float)
    lagged = np.asarray(lagged, dtype=float)
    return -(current - lagged)


# --- B1 validation -----------------------------------------------------------


def validate_b1_invariants(panel: pd.DataFrame, gate: dict | None = None) -> dict:
    """Re-derive B1's material facts from the artifact itself.

    Raises B2InvariantError on any material failure — a downstream task must not
    silently repair or reinterpret upstream data.

    `gate` is optional so later tasks (B3 onward) can reuse this single
    implementation instead of copying the invariant list.
    """
    findings: dict = {}
    failures: list[str] = []

    months = sorted({str(m) for m in panel["reference_month"]})
    findings["industry_count"] = int(panel["industry_id"].nunique())
    findings["month_count"] = len(months)
    findings["first_month"] = months[0] if months else None
    findings["last_month"] = months[-1] if months else None
    findings["panel_rows"] = int(len(panel))
    findings["model_eligible_rows"] = int(panel["is_model_eligible"].sum())

    preliminary = panel[panel["mpi_is_preliminary"] | panel["capu_is_preliminary"]]
    findings["preliminary_rows"] = int(len(preliminary))
    findings["preliminary_months"] = sorted({str(m) for m in preliminary["reference_month"]})
    non_prelim_months = sorted(
        {
            str(m)
            for m in panel.loc[
                ~(panel["mpi_is_preliminary"] | panel["capu_is_preliminary"]), "reference_month"
            ]
        }
    )
    findings["non_preliminary_months"] = len(non_prelim_months)
    findings["editions"] = sorted(panel["source_edition"].dropna().unique().tolist())
    findings["duplicate_keys"] = int(
        panel.duplicated(subset=["reference_month", "industry_id"]).sum()
    )
    findings["mpi_nulls"] = int(panel["mpi_level"].isna().sum())
    findings["capu_nulls"] = int(panel["capacity_utilization_rate"].isna().sum())
    findings["non_positive_mpi"] = int((panel["mpi_level"] <= 0).sum())

    expected = {
        "industry_count": 12,
        "month_count": 66,
        "first_month": "2021-01-01",
        "last_month": "2026-06-01",
        "panel_rows": 792,
        "model_eligible_rows": 780,
        "preliminary_rows": 12,
        "non_preliminary_months": 65,
        "duplicate_keys": 0,
        "mpi_nulls": 0,
        "capu_nulls": 0,
        "non_positive_mpi": 0,
    }
    for key, want in expected.items():
        if findings[key] != want:
            failures.append(f"{key}: expected {want}, found {findings[key]}")

    if findings["preliminary_months"] != ["2026-06-01"]:
        failures.append(
            f"preliminary_months: expected ['2026-06-01'], found {findings['preliminary_months']}"
        )
    scope = (gate or {}).get("sample", {}).get("edition_scope", "current_2021_based_only")
    if findings["editions"] != ["2021_based"]:
        failures.append(
            f"edition scope {scope}: expected only ['2021_based'], found {findings['editions']}"
        )

    findings["all_invariants_reproduced"] = not failures
    findings["failures"] = failures
    if failures:
        raise B2InvariantError(
            "B1 panel failed material invariants; B2 stops rather than repairing the data:\n  - "
            + "\n  - ".join(failures)
        )
    return findings


# --- diagnostic sample -------------------------------------------------------


@dataclass
class DiagnosticSample:
    frame: pd.DataFrame
    months: list[str]
    industries: list[str]
    b1_findings: dict = field(default_factory=dict)

    @property
    def observation_count(self) -> int:
        return int(len(self.frame))


def build_diagnostic_sample(
    panel: pd.DataFrame | None = None, gate: dict | None = None
) -> DiagnosticSample:
    """Build the 12-lag adverse-change diagnostic sample.

    The first 12 months of each industry are simply absent — never imputed. A
    preliminary or non-model-eligible observation is excluded from the usable
    sample, but is still allowed to serve as a 12-month LAG source only if it is
    itself non-preliminary; here the only preliminary month is the final one, so
    no preliminary value is ever used as a denominator.
    """
    gate = gate or load_gate()
    if panel is None:
        panel = pd.read_parquet(DEFAULT_PANEL_PATH)
    b1_findings = validate_b1_invariants(panel, gate)

    lag = int(gate["sample"]["yoy_lag_months"])
    rows: list[dict] = []
    for industry_id, sub in panel.groupby("industry_id", observed=True):
        sub = sub.sort_values("reference_month", kind="mergesort").reset_index(drop=True)
        mpi = sub["mpi_level"].to_numpy(dtype=float)
        capu = sub["capacity_utilization_rate"].to_numpy(dtype=float)
        months = [str(m) for m in sub["reference_month"]]

        current_mpi, lagged_mpi = mpi[lag:], mpi[:-lag]
        current_capu, lagged_capu = capu[lag:], capu[:-lag]
        adverse_mpi = mpi_adverse_yoy(current_mpi, lagged_mpi)
        adverse_capu = capu_adverse_yoy_pp(current_capu, lagged_capu)

        for offset, month in enumerate(months[lag:]):
            idx = offset + lag
            eligible = bool(sub.loc[idx, "is_model_eligible"])
            preliminary = bool(
                sub.loc[idx, "mpi_is_preliminary"] or sub.loc[idx, "capu_is_preliminary"]
            )
            if gate["sample"]["exclude_preliminary"] and preliminary:
                continue
            if gate["sample"]["require_model_eligible"] and not eligible:
                continue
            rows.append(
                {
                    "reference_month": month,
                    "industry_id": industry_id,
                    "mpi_adverse_yoy": float(adverse_mpi[offset]),
                    "capu_adverse_yoy_pp": float(adverse_capu[offset]),
                    "lag_source_month": months[idx - lag],
                }
            )

    frame = pd.DataFrame.from_records(rows)
    frame = frame.sort_values(["industry_id", "reference_month"], kind="mergesort").reset_index(
        drop=True
    )

    # diagnostic-only, full-sample, industry-relative percentile ranks
    for component, column in (
        (MPI_COMPONENT, "mpi_adverse_yoy"),
        (CAPU_COMPONENT, "capu_adverse_yoy_pp"),
    ):
        frame[f"{component}_diagnostic_only_full_sample_rank"] = frame.groupby(
            "industry_id", observed=True
        )[column].transform(lambda s: diagnostic_percentile_rank(s.to_numpy()))

    months_present = sorted(frame["reference_month"].unique().tolist())
    industries = sorted(frame["industry_id"].unique().tolist())
    return DiagnosticSample(
        frame=frame, months=months_present, industries=industries, b1_findings=b1_findings
    )


def diagnostic_percentile_rank(values: np.ndarray) -> np.ndarray:
    """Average-tie ascending percentile rank in (0, 1].

    percentile = average_ascending_rank / n, so the largest value maps to 1.0.
    Ties share one averaged rank, which makes a tied group straddling a
    threshold fall entirely on one side — deterministic, never input-order
    dependent.
    """
    series = pd.Series(np.asarray(values, dtype=float))
    n = int(series.notna().sum())
    if n == 0:
        return np.full(len(series), np.nan)
    return (series.rank(method="average", ascending=True) / n).to_numpy()


# --- correlation primitives --------------------------------------------------


def _rank(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(method="average").to_numpy()


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    if mask.sum() < 3 or np.std(a[mask]) == 0 or np.std(b[mask]) == 0:
        return float("nan")
    return float(np.corrcoef(a[mask], b[mask])[0, 1])


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    if mask.sum() < 3:
        return float("nan")
    ra, rb = _rank(a[mask]), _rank(b[mask])
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def moving_block_spearman_ci(
    a: np.ndarray, b: np.ndarray, gate: dict, industry_index: int
) -> dict:
    """Deterministic moving-block bootstrap CI for Spearman correlation.

    Blocks resample (a, b) PAIRS jointly, so the contemporaneous relationship
    under estimation is preserved while short-run autocorrelation inside a block
    is retained. Independent-resampling would understate the interval width for
    a serially correlated monthly series.
    """
    cfg = gate["bootstrap"]
    block = int(cfg["block_length_months"])
    reps = int(cfg["replications"])
    level = float(cfg["confidence_level"])
    seed = int(cfg["random_seed"])

    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    n = len(a)
    if n < block + 1:
        return {
            "point_estimate": spearman(a, b), "ci_low": float("nan"), "ci_high": float("nan"),
            "replications": 0, "block_length": block, "seed": seed,
            "note": "series too short for the configured block length",
        }

    rng = np.random.default_rng([seed, industry_index])
    n_starts = n - block + 1
    n_blocks = math.ceil(n / block)
    estimates = np.empty(reps, dtype=float)
    for r in range(reps):
        starts = rng.integers(0, n_starts, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        estimates[r] = spearman(a[idx], b[idx])

    valid = estimates[~np.isnan(estimates)]
    alpha = (1.0 - level) / 2.0
    return {
        "point_estimate": spearman(a, b),
        "ci_low": float(np.percentile(valid, 100 * alpha)) if len(valid) else float("nan"),
        "ci_high": float(np.percentile(valid, 100 * (1 - alpha))) if len(valid) else float("nan"),
        "replications": int(len(valid)),
        "block_length": block,
        "seed": seed,
    }


# --- 4.1 quality -------------------------------------------------------------


def quality_checks(sample: DiagnosticSample, gate: dict) -> list[dict]:
    """Per industry x component descriptive checks. Flags only — this function
    never deletes, winsorizes, or otherwise alters an observation.
    """
    cfg = gate["quality"]
    out: list[dict] = []
    for industry_id in sample.industries:
        sub = sample.frame[sample.frame["industry_id"] == industry_id]
        for component, column in (
            (MPI_COMPONENT, "mpi_adverse_yoy"),
            (CAPU_COMPONENT, "capu_adverse_yoy_pp"),
        ):
            values = sub[column].to_numpy(dtype=float)
            finite = values[~np.isnan(values)]
            n = int(len(finite))
            std = float(np.std(finite, ddof=1)) if n > 1 else 0.0
            median = float(np.median(finite)) if n else float("nan")
            mad = float(np.median(np.abs(finite - median))) if n else float("nan")
            flags: list[str] = []
            if n < cfg["min_usable_observations_per_industry"]:
                flags.append("insufficient_observations")
            missing_pct = 100.0 * (len(values) - n) / len(values) if len(values) else 100.0
            if missing_pct > cfg["max_missingness_pct"]:
                flags.append("missingness_above_threshold")
            unique = int(len(np.unique(finite)))
            if unique < cfg["min_unique_values"]:
                flags.append("too_few_unique_values")
            near_constant = std <= cfg["near_constant_std_threshold"]
            if near_constant:
                flags.append("constant_or_near_constant")
            largest = float(np.max(np.abs(finite))) if n else float("nan")
            if mad > 0 and largest > 10 * mad:
                flags.append("extreme_value_present_not_removed")
            out.append(
                {
                    "industry_id": industry_id,
                    "component": component,
                    "n_usable": n,
                    "missingness_pct": missing_pct,
                    "unique_values": unique,
                    "std": std,
                    "median": median,
                    "mad": mad,
                    "min": float(np.min(finite)) if n else float("nan"),
                    "max": float(np.max(finite)) if n else float("nan"),
                    "largest_abs": largest,
                    "is_constant_or_near_constant": bool(near_constant),
                    "flags": flags,
                }
            )
    return out


# --- 4.2 contemporaneous dependence ------------------------------------------


def industry_correlations(sample: DiagnosticSample, gate: dict) -> list[dict]:
    out: list[dict] = []
    for index, industry_id in enumerate(sample.industries):
        sub = sample.frame[sample.frame["industry_id"] == industry_id]
        mpi = sub["mpi_adverse_yoy"].to_numpy(dtype=float)
        capu = sub["capu_adverse_yoy_pp"].to_numpy(dtype=float)
        boot = moving_block_spearman_ci(mpi, capu, gate, index)
        out.append(
            {
                "industry_id": industry_id,
                "n": int(len(sub)),
                "pearson": pearson(mpi, capu),
                "spearman": spearman(mpi, capu),
                "spearman_ci_low": boot["ci_low"],
                "spearman_ci_high": boot["ci_high"],
                "bootstrap_replications": boot["replications"],
                "bootstrap_block_length": boot["block_length"],
                "bootstrap_seed": boot["seed"],
            }
        )
    return out


def pooled_correlations(sample: DiagnosticSample) -> dict:
    """Primary pooled result uses the industry-relative diagnostic ranks.

    Pooling raw adverse changes across industries would let differences in
    industry scale and volatility drive the coefficient; that naive figure is
    computed too, but explicitly as a secondary contrast, not the headline.
    """
    frame = sample.frame
    rank_mpi = frame["mpi_diagnostic_only_full_sample_rank"].to_numpy(dtype=float)
    rank_capu = frame["capu_diagnostic_only_full_sample_rank"].to_numpy(dtype=float)
    raw_mpi = frame["mpi_adverse_yoy"].to_numpy(dtype=float)
    raw_capu = frame["capu_adverse_yoy_pp"].to_numpy(dtype=float)
    return {
        "primary_basis": "industry_relative_diagnostic_ranks",
        "n": int(len(frame)),
        "pearson_on_ranks": pearson(rank_mpi, rank_capu),
        "spearman_on_ranks": spearman(rank_mpi, rank_capu),
        "secondary_naive_pooled_pearson_raw": pearson(raw_mpi, raw_capu),
        "secondary_naive_pooled_spearman_raw": spearman(raw_mpi, raw_capu),
        "secondary_note": (
            "Naive pooled figures are reported for contrast only. They confound "
            "industry-level scale differences with the dependence being measured "
            "and are not the primary result."
        ),
    }


# --- 4.3 lead-lag ------------------------------------------------------------


def lead_lag_table(sample: DiagnosticSample, gate: dict) -> dict:
    """corr(k) = spearman(mpi[t], capu[t + k]).

    k > 0 reads CapU at a LATER month than MPI, i.e. MPI leads CapU.
    k < 0 reads CapU EARLIER, i.e. CapU leads MPI.
    Descriptive association only — no causal claim.
    """
    cfg = gate["lead_lag"]
    lags = list(range(int(cfg["min_lag"]), int(cfg["max_lag"]) + 1))
    per_industry: list[dict] = []
    pooled_by_lag: dict[str, float] = {}

    pooled_pairs: dict[int, list[tuple[float, float]]] = {k: [] for k in lags}
    for industry_id in sample.industries:
        sub = sample.frame[sample.frame["industry_id"] == industry_id].reset_index(drop=True)
        mpi_rank = sub["mpi_diagnostic_only_full_sample_rank"].to_numpy(dtype=float)
        capu_rank = sub["capu_diagnostic_only_full_sample_rank"].to_numpy(dtype=float)
        mpi = sub["mpi_adverse_yoy"].to_numpy(dtype=float)
        capu = sub["capu_adverse_yoy_pp"].to_numpy(dtype=float)
        by_lag: dict[str, float] = {}
        for k in lags:
            if k >= 0:
                x, y = mpi[: len(mpi) - k], capu[k:]
                xr, yr = mpi_rank[: len(mpi_rank) - k], capu_rank[k:]
            else:
                x, y = mpi[-k:], capu[: len(capu) + k]
                xr, yr = mpi_rank[-k:], capu_rank[: len(capu_rank) + k]
            by_lag[str(k)] = spearman(x, y)
            pooled_pairs[k].extend(zip(xr, yr, strict=True))
        finite = {k: v for k, v in by_lag.items() if not math.isnan(v)}
        best_lag = max(finite, key=lambda k: abs(finite[k])) if finite else None
        per_industry.append(
            {
                "industry_id": industry_id,
                "by_lag": by_lag,
                "contemporaneous": by_lag.get("0"),
                "strongest_abs_lag": int(best_lag) if best_lag is not None else None,
                "strongest_abs_value": finite.get(best_lag) if best_lag is not None else None,
            }
        )

    for k in lags:
        pairs = pooled_pairs[k]
        if pairs:
            arr = np.array(pairs, dtype=float)
            pooled_by_lag[str(k)] = spearman(arr[:, 0], arr[:, 1])
        else:
            pooled_by_lag[str(k)] = float("nan")

    finite_pooled = {k: v for k, v in pooled_by_lag.items() if not math.isnan(v)}
    pooled_best = max(finite_pooled, key=lambda k: abs(finite_pooled[k]))
    contemporaneous = pooled_by_lag["0"]
    materially_changes = (
        abs(finite_pooled[pooled_best]) - abs(contemporaneous) > 0.05
        if not math.isnan(contemporaneous)
        else False
    )
    industries_peaking_at_zero = sum(
        1 for row in per_industry if row["strongest_abs_lag"] == 0
    )
    return {
        "sign_convention": cfg["sign_convention"],
        "causal_interpretation_permitted": False,
        "lags": lags,
        "per_industry": per_industry,
        "pooled_by_lag": pooled_by_lag,
        "pooled_strongest_lag": int(pooled_best),
        "pooled_strongest_value": finite_pooled[pooled_best],
        "pooled_contemporaneous": contemporaneous,
        "contemporaneous_conclusion_materially_changes": bool(materially_changes),
        "industries_peaking_at_lag_zero": industries_peaking_at_zero,
    }


# --- 4.4 high-stress overlap -------------------------------------------------


def high_stress_overlap(sample: DiagnosticSample, gate: dict) -> list[dict]:
    threshold = 1.0 - float(gate["high_stress"]["top_quantile"])
    out: list[dict] = []
    for industry_id in sample.industries:
        sub = sample.frame[sample.frame["industry_id"] == industry_id]
        mpi_high = set(
            sub.loc[sub["mpi_diagnostic_only_full_sample_rank"] > threshold, "reference_month"]
        )
        capu_high = set(
            sub.loc[sub["capu_diagnostic_only_full_sample_rank"] > threshold, "reference_month"]
        )
        intersection = mpi_high & capu_high
        union = mpi_high | capu_high
        out.append(
            {
                "industry_id": industry_id,
                "mpi_high_stress_count": len(mpi_high),
                "capu_high_stress_count": len(capu_high),
                "intersection_count": len(intersection),
                "union_count": len(union),
                "jaccard": (len(intersection) / len(union)) if union else float("nan"),
                "mpi_only_count": len(mpi_high - capu_high),
                "capu_only_count": len(capu_high - mpi_high),
                "mpi_only_months": sorted(mpi_high - capu_high),
                "capu_only_months": sorted(capu_high - mpi_high),
                "shared_months": sorted(intersection),
            }
        )
    return out


# --- 4.5 stability -----------------------------------------------------------


def stability_checks(sample: DiagnosticSample, gate: dict) -> list[dict]:
    out: list[dict] = []
    for period in gate["stability"]["subperiods"]:
        start, end = str(period["start"]), str(period["end"])
        window = sample.frame[
            (sample.frame["reference_month"] >= start) & (sample.frame["reference_month"] <= end)
        ]
        per_industry = []
        for industry_id in sample.industries:
            sub = window[window["industry_id"] == industry_id]
            per_industry.append(
                {
                    "industry_id": industry_id,
                    "n": int(len(sub)),
                    "spearman": spearman(
                        sub["mpi_adverse_yoy"].to_numpy(dtype=float),
                        sub["capu_adverse_yoy_pp"].to_numpy(dtype=float),
                    ),
                }
            )
        values = [r["spearman"] for r in per_industry if not math.isnan(r["spearman"])]
        pooled = spearman(
            window["mpi_diagnostic_only_full_sample_rank"].to_numpy(dtype=float),
            window["capu_diagnostic_only_full_sample_rank"].to_numpy(dtype=float),
        )
        out.append(
            {
                "name": period["name"],
                "start": start,
                "end": end,
                "months": int(window["reference_month"].nunique()),
                "observations": int(len(window)),
                "pooled_spearman_on_ranks": pooled,
                "median_industry_spearman": float(np.median(values)) if values else float("nan"),
                "min_industry_spearman": float(np.min(values)) if values else float("nan"),
                "max_industry_spearman": float(np.max(values)) if values else float("nan"),
                "per_industry": per_industry,
                "caveat": (
                    "Small subsample — a wide interval here is not grounds to reject "
                    "a component."
                ),
            }
        )
    return out


# --- 5. decision gate --------------------------------------------------------


def classify_redundancy(
    pooled: dict,
    per_industry: list[dict],
    overlap: list[dict],
    quality: list[dict],
    gate: dict,
    semantics_ok: bool = True,
) -> dict:
    """Mechanically apply configs/component_redundancy_gate.yaml."""
    cfg = gate["classification"]
    red = cfg["redundant"]
    non = cfg["non_redundant"]

    pooled_abs = abs(pooled["spearman_on_ranks"])
    industry_abs = [abs(r["spearman"]) for r in per_industry if not math.isnan(r["spearman"])]
    industries_above = sum(
        1 for v in industry_abs if v >= red["industries_with_abs_spearman_at_least"]
    )
    jaccards = [r["jaccard"] for r in overlap if not math.isnan(r["jaccard"])]
    median_jaccard = float(np.median(jaccards)) if jaccards else float("nan")

    redundant_conditions = {
        "pooled_abs_spearman_at_least": (
            pooled_abs >= red["pooled_abs_spearman_min"], pooled_abs, red["pooled_abs_spearman_min"]
        ),
        "industries_with_high_abs_spearman": (
            industries_above >= red["industries_required"],
            industries_above, red["industries_required"],
        ),
        "median_jaccard_at_least": (
            median_jaccard >= red["median_jaccard_min"], median_jaccard, red["median_jaccard_min"]
        ),
    }
    is_redundant = all(passed for passed, _, _ in redundant_conditions.values())

    coverage_ok = all(
        "insufficient_observations" not in q["flags"]
        and "missingness_above_threshold" not in q["flags"]
        for q in quality
    )
    non_constant_ok = all(not q["is_constant_or_near_constant"] for q in quality)
    industries_mpi_only = sum(1 for r in overlap if r["mpi_only_count"] > 0)
    industries_capu_only = sum(1 for r in overlap if r["capu_only_count"] > 0)
    min_specific = non["min_industries_with_component_specific_stress"]

    non_redundant_conditions = {
        "redundant_rule_is_false": (not is_redundant, is_redundant, False),
        "coverage_checks_pass": (coverage_ok, coverage_ok, True),
        "non_constant_series": (non_constant_ok, non_constant_ok, True),
        "industries_with_mpi_only_stress": (
            industries_mpi_only >= min_specific, industries_mpi_only, min_specific
        ),
        "industries_with_capu_only_stress": (
            industries_capu_only >= min_specific, industries_capu_only, min_specific
        ),
        "no_unresolved_semantics_failure": (semantics_ok, semantics_ok, True),
    }
    is_non_redundant = all(passed for passed, _, _ in non_redundant_conditions.values())

    if is_redundant and not is_non_redundant:
        status = "redundant"
    elif is_non_redundant and not is_redundant:
        status = "non_redundant"
    else:
        status = "inconclusive"

    return {
        "gate_version": gate["gate_version"],
        "redundancy_status": status,
        "pooled_abs_spearman_on_ranks": pooled_abs,
        "industries_above_abs_spearman_threshold": industries_above,
        "median_jaccard": median_jaccard,
        "industries_with_mpi_only_stress": industries_mpi_only,
        "industries_with_capu_only_stress": industries_capu_only,
        "redundant_conditions": {
            k: {"passed": bool(p), "observed": o, "threshold": t}
            for k, (p, o, t) in redundant_conditions.items()
        },
        "non_redundant_conditions": {
            k: {"passed": bool(p), "observed": o, "threshold": t}
            for k, (p, o, t) in non_redundant_conditions.items()
        },
        "interpretation_note": (
            "`non_redundant` means the pair is not empirically duplicative under this "
            "pre-registered gate. It does NOT mean the components are statistically "
            "independent — they are strongly dependent by construction, since capacity "
            "utilization is bounded by production."
        ),
    }


def decide_approvals(
    classification: dict, quality: list[dict], stability: list[dict], semantics: dict, gate: dict
) -> dict:
    """Four separate decisions. One boolean never carries several meanings."""
    coverage_ok = all(not q["flags"] or set(q["flags"]) <= {"extreme_value_present_not_removed"}
                      for q in quality)
    stability_ok = all(
        not math.isnan(p["pooled_spearman_on_ranks"]) and p["observations"] > 0
        for p in stability
    )
    per_component: dict[str, dict] = {}
    for component in COMPONENTS:
        checks = {
            "correct_adverse_transform": semantics[component]["transform_verified"],
            "correct_direction": semantics[component]["direction_verified"],
            "correct_unit": semantics[component]["unit_verified"],
            "coverage_checks_pass": coverage_ok,
            "stability_checks_pass": stability_ok,
        }
        per_component[component] = {
            "checks": checks,
            "component_semantics_approved": all(checks.values()),
            "unit": semantics[component]["unit"],
            "adverse_transform": semantics[component]["adverse_transform"],
        }

    both_ok = all(c["component_semantics_approved"] for c in per_component.values())
    non_redundant = classification["redundancy_status"] == "non_redundant"
    if both_ok and non_redundant:
        composite = "approved"
    elif classification["redundancy_status"] == "redundant":
        composite = "rejected"
    else:
        composite = "conditional"

    return {
        "components": per_component,
        "redundancy_status": classification["redundancy_status"],
        "equal_weight_composite_status": composite,
        "equal_weight_rationale": gate["approval"]["equal_weight_rationale"],
        "composite_index_built_in_b2": False,
    }


# --- orchestration -----------------------------------------------------------


def _semantics_evidence() -> dict:
    """Verify the transforms behave as specified, on controlled inputs.

    These are self-checks of the implementation's direction and unit, run every
    time B2 executes so the approval fields cannot be set without them.
    """
    mpi_worse = float(mpi_adverse_yoy(np.array([90.0]), np.array([100.0]))[0])
    mpi_better = float(mpi_adverse_yoy(np.array([110.0]), np.array([100.0]))[0])
    mpi_flat = float(mpi_adverse_yoy(np.array([100.0]), np.array([100.0]))[0])
    capu_worse = float(capu_adverse_yoy_pp(np.array([55.0]), np.array([60.0]))[0])
    capu_better = float(capu_adverse_yoy_pp(np.array([65.0]), np.array([60.0]))[0])
    capu_flat = float(capu_adverse_yoy_pp(np.array([60.0]), np.array([60.0]))[0])
    # a relative percentage change would give -(55/60-1)*100 = +8.333, not +5.0
    capu_relative_would_be = -100.0 * (55.0 / 60.0 - 1.0)
    return {
        MPI_COMPONENT: {
            "adverse_transform": "-100 * (mpi_t / mpi_t_minus_12 - 1)",
            "unit": "percent",
            "transform_verified": math.isclose(mpi_worse, 10.0),
            "direction_verified": mpi_worse > 0 and mpi_better < 0 and mpi_flat == 0.0,
            "unit_verified": True,
            "examples": {"deterioration": mpi_worse, "improvement": mpi_better, "flat": mpi_flat},
        },
        CAPU_COMPONENT: {
            "adverse_transform": "-(capu_t - capu_t_minus_12)",
            "unit": "percentage_points",
            "transform_verified": math.isclose(capu_worse, 5.0),
            "direction_verified": capu_worse > 0 and capu_better < 0 and capu_flat == 0.0,
            "unit_verified": not math.isclose(capu_worse, capu_relative_would_be),
            "examples": {
                "deterioration_pp": capu_worse,
                "improvement_pp": capu_better,
                "flat_pp": capu_flat,
                "relative_change_would_have_been": capu_relative_would_be,
            },
        },
    }


def run_diagnostics(
    panel: pd.DataFrame | None = None, gate: dict | None = None
) -> dict:
    """Execute the full B2 diagnostic and return a machine-readable result."""
    gate = gate or load_gate()
    sample = build_diagnostic_sample(panel, gate)

    expected = gate["sample"]
    sample_failures: list[str] = []
    per_industry_counts = sample.frame.groupby("industry_id", observed=True).size()
    if set(per_industry_counts.unique().tolist()) != {expected["expected_months_per_industry"]}:
        sample_failures.append(
            f"months per industry: expected {expected['expected_months_per_industry']}, "
            f"found {sorted(per_industry_counts.unique().tolist())}"
        )
    if sample.observation_count != expected["expected_total_observations"]:
        sample_failures.append(
            f"total observations: expected {expected['expected_total_observations']}, "
            f"found {sample.observation_count}"
        )
    if sample.months[0] != str(expected["first_usable_month"]):
        sample_failures.append(f"first usable month: {sample.months[0]}")
    if sample.months[-1] != str(expected["last_usable_month"]):
        sample_failures.append(f"last usable month: {sample.months[-1]}")
    if sample_failures:
        raise B2InvariantError(
            "B2 diagnostic sample does not match the pre-registered expectations:\n  - "
            + "\n  - ".join(sample_failures)
        )

    semantics = _semantics_evidence()
    semantics_ok = all(
        s["transform_verified"] and s["direction_verified"] and s["unit_verified"]
        for s in semantics.values()
    )
    quality = quality_checks(sample, gate)
    per_industry = industry_correlations(sample, gate)
    pooled = pooled_correlations(sample)
    lead_lag = lead_lag_table(sample, gate)
    overlap = high_stress_overlap(sample, gate)
    stability = stability_checks(sample, gate)
    classification = classify_redundancy(
        pooled, per_industry, overlap, quality, gate, semantics_ok
    )
    approvals = decide_approvals(classification, quality, stability, semantics, gate)

    industry_spearman = [r["spearman"] for r in per_industry if not math.isnan(r["spearman"])]
    return {
        "task": "B2",
        "gate_version": gate["gate_version"],
        "data_framing": "latest_vintage_historical_data",
        "edition_scope": gate["sample"]["edition_scope"],
        "b1_invariants": sample.b1_findings,
        "sample": {
            "observations": sample.observation_count,
            "industries": len(sample.industries),
            "months": len(sample.months),
            "months_per_industry": int(per_industry_counts.iloc[0]),
            "first_month": sample.months[0],
            "last_month": sample.months[-1],
            "first_twelve_months_imputed": False,
        },
        "component_semantics": semantics,
        "quality_checks": quality,
        "industry_correlations": per_industry,
        "industry_spearman_summary": {
            "median": float(np.median(industry_spearman)),
            "min": float(np.min(industry_spearman)),
            "max": float(np.max(industry_spearman)),
        },
        "pooled_correlations": pooled,
        "lead_lag": lead_lag,
        "high_stress_overlap": overlap,
        "stability": stability,
        "classification": classification,
        "approvals": approvals,
        "diagnostic_normalization_label": gate["diagnostic_normalization"]["label"],
        "diagnostic_normalization_leakage_safe": False,
    }


def sample_to_frame(sample: DiagnosticSample) -> pd.DataFrame:
    return sample.frame.copy()
