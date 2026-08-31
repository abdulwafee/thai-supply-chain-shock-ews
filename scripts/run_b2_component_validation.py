"""Run Task B2: MPI-CapU redundancy validation and component approval.

Thin runner. All logic lives in
`thai_supply_chain_ews.targets.component_diagnostics`; this script wires it to
the B1 panel, writes the machine-readable JSON that the Markdown report reads
from, and renders four diagnostic plots.

Does NOT build the Stress Index and does NOT modify the B1 panel.

Usage:
    python scripts/run_b2_component_validation.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from thai_supply_chain_ews.targets.component_diagnostics import (  # noqa: E402
    DEFAULT_PANEL_PATH,
    build_diagnostic_sample,
    load_gate,
    run_diagnostics,
)

PLOTS_DIR = PROJECT_ROOT / "docs" / "b2_plots"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "b2_component_validation_output.json"


def json_safe(obj):
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return json_safe(float(obj))
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def plot_pooled_scatter(sample_frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.scatter(
        sample_frame["mpi_diagnostic_only_full_sample_rank"],
        sample_frame["capu_diagnostic_only_full_sample_rank"],
        s=6, alpha=0.35, color="steelblue", edgecolors="none",
    )
    ax.plot([0, 1], [0, 1], color="grey", linewidth=0.8, linestyle="--")
    ax.set_xlabel("MPI adverse — industry-relative rank")
    ax.set_ylabel("CapU adverse — industry-relative rank")
    ax.set_title("Pooled diagnostic ranks (n=636)\ndiagnostic_only_full_sample_rank", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=85)
    plt.close(fig)


def plot_industry_correlations(result: dict, path: Path) -> None:
    rows = sorted(result["industry_correlations"], key=lambda r: r["industry_id"])
    names = [r["industry_id"] for r in rows]
    y = np.arange(len(rows))
    spear = [r["spearman"] for r in rows]
    lows = [r["spearman"] - r["spearman_ci_low"] for r in rows]
    highs = [r["spearman_ci_high"] - r["spearman"] for r in rows]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.errorbar(spear, y, xerr=[lows, highs], fmt="o", color="steelblue",
                ecolor="lightsteelblue", capsize=3, markersize=5, label="Spearman (95% CI)")
    ax.scatter([r["pearson"] for r in rows], y, marker="x", color="darkorange",
               s=30, label="Pearson")
    bar = load_gate()["classification"]["redundant"]["industries_with_abs_spearman_at_least"]
    ax.axvline(bar, color="red", linestyle="--", linewidth=1, label=f"redundancy bar {bar}")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("Correlation of adverse changes (MPI vs CapU)")
    ax.set_title("Contemporaneous dependence by industry", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=85)
    plt.close(fig)


def plot_high_stress_overlap(result: dict, path: Path) -> None:
    rows = sorted(result["high_stress_overlap"], key=lambda r: r["industry_id"])
    names = [r["industry_id"] for r in rows]
    x = np.arange(len(rows))
    shared = [r["intersection_count"] for r in rows]
    mpi_only = [r["mpi_only_count"] for r in rows]
    capu_only = [r["capu_only_count"] for r in rows]

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax.bar(x, shared, label="shared", color="seagreen")
    ax.bar(x, mpi_only, bottom=shared, label="MPI-only", color="steelblue")
    ax.bar(x, capu_only, bottom=np.array(shared) + np.array(mpi_only),
           label="CapU-only", color="darkorange")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("high-stress months (top 20%)")
    ax.set_title("High-stress episode composition", fontsize=10)
    ax.legend(fontsize=8)

    jac = [r["jaccard"] for r in rows]
    ax2.bar(x, jac, color="slategray")
    bar = load_gate()["classification"]["redundant"]["median_jaccard_min"]
    ax2.axhline(bar, color="red", linestyle="--", linewidth=1, label=f"redundancy bar {bar}")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax2.set_ylabel("Jaccard similarity")
    ax2.set_title("Overlap of high-stress months", fontsize=10)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=85)
    plt.close(fig)


def plot_lead_lag(result: dict, path: Path) -> None:
    lead_lag = result["lead_lag"]
    lags = lead_lag["lags"]
    fig, ax = plt.subplots(figsize=(7, 4))
    for row in sorted(lead_lag["per_industry"], key=lambda r: r["industry_id"]):
        ax.plot(lags, [row["by_lag"][str(k)] for k in lags], color="lightsteelblue",
                linewidth=0.9, alpha=0.8)
    pooled = [lead_lag["pooled_by_lag"][str(k)] for k in lags]
    ax.plot(lags, pooled, color="crimson", linewidth=2.2, marker="o", label="pooled (ranks)")
    ax.axvline(0, color="grey", linewidth=0.8, linestyle="--")
    ax.set_xlabel("lag k    (k>0: CapU read later → MPI leads CapU)")
    ax.set_ylabel("Spearman correlation")
    ax.set_title("Lead–lag dependence — descriptive association only, not causal", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=85)
    plt.close(fig)


def main() -> None:
    gate = load_gate()
    panel_before = pd.read_parquet(DEFAULT_PANEL_PATH)
    panel_checksum_before = pd.util.hash_pandas_object(panel_before, index=True).sum()

    result = run_diagnostics(panel_before.copy(), gate)
    sample = build_diagnostic_sample(panel_before.copy(), gate)

    PLOTS_DIR.mkdir(exist_ok=True)
    plot_pooled_scatter(sample.frame, PLOTS_DIR / "pooled_rank_scatter.png")
    plot_industry_correlations(result, PLOTS_DIR / "industry_correlations.png")
    plot_high_stress_overlap(result, PLOTS_DIR / "high_stress_overlap.png")
    plot_lead_lag(result, PLOTS_DIR / "lead_lag.png")
    result["plots"] = [
        f"docs/b2_plots/{name}"
        for name in ("pooled_rank_scatter.png", "industry_correlations.png",
                     "high_stress_overlap.png", "lead_lag.png")
    ]

    panel_after = pd.read_parquet(DEFAULT_PANEL_PATH)
    panel_checksum_after = pd.util.hash_pandas_object(panel_after, index=True).sum()
    result["b1_panel_unmodified"] = bool(panel_checksum_before == panel_checksum_after)

    OUTPUT_PATH.write_text(
        json.dumps(json_safe(result), indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )

    cls = result["classification"]
    app = result["approvals"]
    pooled = result["pooled_correlations"]
    summary = result["industry_spearman_summary"]

    print("=== Task B2 — MPI vs CapU redundancy validation ===")
    print(f"B1 invariants reproduced : {result['b1_invariants']['all_invariants_reproduced']}")
    print(f"sample                   : {result['sample']['observations']} obs, "
          f"{result['sample']['months_per_industry']}/industry, "
          f"{result['sample']['first_month']} .. {result['sample']['last_month']}")
    print(f"pooled Pearson  (ranks)  : {pooled['pearson_on_ranks']:.4f}")
    print(f"pooled Spearman (ranks)  : {pooled['spearman_on_ranks']:.4f}")
    print(f"  naive pooled raw Spearman (secondary): "
          f"{pooled['secondary_naive_pooled_spearman_raw']:.4f}")
    print(f"industry Spearman        : median {summary['median']:.4f}, "
          f"range [{summary['min']:.4f}, {summary['max']:.4f}]")
    print(f"industries |rho| >= 0.75 : {cls['industries_above_abs_spearman_threshold']}/12")
    print(f"median Jaccard           : {cls['median_jaccard']:.4f}")
    print(f"industries MPI-only      : {cls['industries_with_mpi_only_stress']}/12")
    print(f"industries CapU-only     : {cls['industries_with_capu_only_stress']}/12")
    ll = result["lead_lag"]
    print(f"lead-lag strongest       : lag {ll['pooled_strongest_lag']} "
          f"(rho={ll['pooled_strongest_value']:.4f}); contemporaneous "
          f"{ll['pooled_contemporaneous']:.4f}")
    for period in result["stability"]:
        print(f"stability {period['name']:5s}          : pooled rho "
              f"{period['pooled_spearman_on_ranks']:.4f} over {period['months']} months")
    print(f"\nCLASSIFICATION           : {cls['redundancy_status']}")
    for component, info in app["components"].items():
        print(f"  {component:4s} semantics approved : {info['component_semantics_approved']}")
    print(f"equal-weight K=2 composite: {app['equal_weight_composite_status']}")
    print(f"B1 panel unmodified       : {result['b1_panel_unmodified']}")
    print(f"\noutput: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"plots : {PLOTS_DIR.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
