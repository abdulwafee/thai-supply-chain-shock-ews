"""Task D3 — release-aware operational baseline evaluation.

Runs the operational walk-forward on the B4 **development** period only, scores
the operational baselines, selects one operational benchmark per horizon, and
writes:

    docs/d3_operational_baseline_results.{md,json}
    docs/d3_locked_test_manifest.json
    data/model_input/d3_operational_predictions.parquet   (git-ignored)

This script trains no model, reads no commodity feature, changes no B3 target
window, and does not evaluate D1. The locked final test is not reachable from
here: locked months are rejected inside the contract layer, and this script
exposes no flag, environment variable or argument that could reach them.

B4 and D1 outputs are never overwritten. D3 is an additional versioned contract
alongside them, not a replacement of their files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from thai_supply_chain_ews.evaluation import bootstrap as BS  # noqa: E402
from thai_supply_chain_ews.evaluation import metrics as MT  # noqa: E402
from thai_supply_chain_ews.evaluation.operational_baselines import (  # noqa: E402
    OPERATIONAL_BASELINES_BY_HORIZON,
)
from thai_supply_chain_ews.evaluation.operational_contract import (  # noqa: E402
    load_operational_config,
    locked_month_set,
    month_label,
    purge_month_set,
)
from thai_supply_chain_ews.evaluation.operational_walk_forward import (  # noqa: E402
    run_operational_walk_forward,
)

DOCS = ROOT / "docs"
PREDICTIONS_PATH = ROOT / "data" / "model_input" / "d3_operational_predictions.parquet"
REFERENCE_BASELINE = "operational_industry_historical_mean"


def _frame(predictions, horizon, baseline):
    return predictions[
        (predictions["horizon_months"] == horizon)
        & (predictions["baseline_name"] == baseline)
    ]


def evaluate(predictions, config):
    """Development metrics for every horizon and operational baseline."""
    bootstrap_config = config["bootstrap"]
    threshold = float(config["metrics"]["high_stress"]["threshold"])
    severe = float(config["metrics"]["high_stress"]["severe_threshold"])

    results = {}
    for horizon in (1, 3):
        per_baseline = {}
        matrices = {}
        for name in OPERATIONAL_BASELINES_BY_HORIZON[horizon]:
            frame = _frame(predictions, horizon, name)
            matrix = BS.build_error_matrix(frame)
            matrices[name] = matrix
            high = MT.high_stress_event_metrics(frame, threshold=threshold)
            per_baseline[name] = {
                "macro_industry_mae": MT.macro_industry_mae(frame),
                "pooled_mae": MT.pooled_mae(frame),
                "macro_industry_rmse": MT.macro_industry_rmse(frame),
                "pooled_rmse": MT.pooled_rmse(frame),
                "median_absolute_error": MT.median_absolute_error(frame),
                "pooled_spearman": MT.spearman_correlation(
                    frame["observed_score"].to_numpy(float),
                    frame["predicted_score"].to_numpy(float),
                ),
                "per_industry_mae": MT.per_industry_mae(frame),
                "by_development_block": {
                    block: MT.macro_industry_mae(sub)
                    for block, sub in frame.groupby("split_name", observed=True)
                },
                "high_stress": high,
                "severe_counts": MT.severe_event_counts(frame, threshold=severe),
                "rows": int(len(frame)),
            }

        # bootstrap: macro MAE interval, skill vs the reference baseline, and
        # paired differences between every operational pair
        reference_matrix = matrices[REFERENCE_BASELINE]
        for index, (name, matrix) in enumerate(sorted(matrices.items())):
            interval = BS.bootstrap_macro_mae_ci(matrix, bootstrap_config, seed_offset=index)
            per_baseline[name]["macro_mae_ci"] = interval
            per_baseline[name]["mae_skill_vs_reference"] = MT.mae_skill(
                per_baseline[name]["macro_industry_mae"],
                per_baseline[REFERENCE_BASELINE]["macro_industry_mae"],
            )
            if name != REFERENCE_BASELINE:
                per_baseline[name]["paired_vs_reference"] = (
                    BS.bootstrap_paired_macro_mae_difference(
                        matrix, reference_matrix, bootstrap_config, seed_offset=index
                    )
                )

        names = sorted(matrices)
        paired = {}
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                paired[f"{left}__vs__{right}"] = (
                    BS.bootstrap_paired_macro_mae_difference(
                        matrices[left], matrices[right], bootstrap_config, seed_offset=i
                    )
                )
        results[horizon] = {"baselines": per_baseline, "paired_differences": paired}
    return results


def select_benchmark(per_baseline, config):
    """Lowest macro MAE; ties broken by false negatives, then simplicity."""
    selection = config["benchmark_selection"]
    tolerance = float(selection["tie_tolerance"])
    order = list(selection["simplicity_order"])

    ranked = sorted(per_baseline.items(), key=lambda kv: kv[1]["macro_industry_mae"])
    best_mae = ranked[0][1]["macro_industry_mae"]
    tied = [
        (name, payload)
        for name, payload in ranked
        if abs(payload["macro_industry_mae"] - best_mae) <= tolerance
    ]
    rule_applied = "lowest_macro_industry_mae"

    if len(tied) > 1:
        rule_applied = "fewer_false_negatives_at_score_85"
        fewest = min(p["high_stress"]["false_negative"] for _, p in tied)
        tied = [
            (n, p) for n, p in tied if p["high_stress"]["false_negative"] == fewest
        ]
        if len(tied) > 1:
            rule_applied = "simpler_baseline"
            tied.sort(key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order))

    name = tied[0][0]
    return {
        "selected_benchmark": name,
        "rule_applied": rule_applied,
        "macro_industry_mae": per_baseline[name]["macro_industry_mae"],
        "candidates_considered": [n for n, _ in ranked],
        "tie_tolerance": tolerance,
        "selection_used_only_development_data": True,
        "excluded_from_selection": list(selection["may_not_use"]),
    }


def b4_reference_mae():
    """B4's selected benchmark MAE per horizon, read for context only.

    Historical, NON-OPERATIONAL reference. B4 allowed stress month t at origin
    t, so its number is not a like-for-like operational result. It is never used
    to select anything here.
    """
    path = DOCS / "b4_baseline_results.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for horizon in (1, 3):
        block = payload.get("by_horizon", {}).get(str(horizon))
        if not block:
            continue
        name = block.get("selected_benchmark")
        entry = (block.get("baselines") or {}).get(name)
        if name and entry and "macro_industry_mae" in entry:
            out[horizon] = {
                "baseline_name": name,
                "macro_industry_mae": float(entry["macro_industry_mae"]),
                "role": "historical_non_operational_reference_only",
            }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-only", action="store_true", help="compute and print without writing files"
    )
    args = parser.parse_args()

    config = load_operational_config()
    result = run_operational_walk_forward(config=config)
    predictions = result.predictions
    metrics = evaluate(predictions, config)

    b4 = b4_reference_mae()
    selections = {}
    for horizon in (1, 3):
        chosen = select_benchmark(metrics[horizon]["baselines"], config)
        reference = b4.get(horizon)
        if reference:
            chosen["b4_reference_baseline"] = reference["baseline_name"]
            chosen["b4_reference_macro_industry_mae"] = reference["macro_industry_mae"]
            chosen["operational_penalty"] = (
                chosen["macro_industry_mae"] - reference["macro_industry_mae"]
            )
        chosen["operational_penalty_attribution"] = config["benchmark_selection"][
            "operational_penalty_attribution"
        ]
        selections[horizon] = chosen

    contract_status = _contract_status(result, predictions, config)

    payload = {
        "task": "D3",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "operational_contract_version": config["operational_contract_version"],
        "evaluation_framing": config["evaluation_framing"],
        "dataset_flags": result.dataset_flags,
        "contract_status": contract_status,
        "split": {
            "development_issue_months": [str(o) for o in result.origins],
            "development_issue_month_count": len(result.origins),
            "purge_months": sorted(purge_month_set(config)),
            "purge_metrics_calculated": False,
            "locked_test_months": sorted(locked_month_set(config)),
            "locked_test_evaluated": False,
            "locked_test_outcomes_read": False,
        },
        "origin_contracts": [c.to_dict() for _, c in sorted(result.contracts.items())],
        "label_availability": [a.to_dict() for a in result.availability],
        "prediction_counts": {
            "total": int(len(predictions)),
            "horizon_1": int((predictions["horizon_months"] == 1).sum()),
            "horizon_3": int((predictions["horizon_months"] == 3).sum()),
            "per_horizon_baseline": {
                f"h{h}_{n}": int(len(_frame(predictions, h, n)))
                for h in (1, 3)
                for n in OPERATIONAL_BASELINES_BY_HORIZON[h]
            },
        },
        "metrics": {str(h): metrics[h] for h in (1, 3)},
        "benchmark_selection": {str(h): selections[h] for h in (1, 3)},
        "calibrator_fingerprints": result.calibrator_fingerprints,
        "b3_invariants_reproduced": result.b3_findings,
    }
    payload["content_checksum"] = hashlib.sha256(
        json.dumps(_stable(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    if args.print_only:
        _print_summary(payload, predictions)
        return 0

    PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(PREDICTIONS_PATH, index=False)
    payload["outputs"] = {
        "predictions_path": str(PREDICTIONS_PATH.relative_to(ROOT)).replace("\\", "/"),
        "predictions_sha256": hashlib.sha256(
            pd.util.hash_pandas_object(predictions, index=False).values.tobytes()
        ).hexdigest(),
    }

    _write_json(DOCS / "d3_operational_baseline_results.json", payload)
    _write_locked_manifest(DOCS / "d3_locked_test_manifest.json", config, result)
    _write_markdown(DOCS / "d3_operational_baseline_results.md", payload)
    _print_summary(payload, predictions)
    return 0


def _stable(payload):
    """Drop volatile fields before checksumming, so reruns are comparable."""
    clone = dict(payload)
    clone.pop("generated_at_utc", None)
    clone.pop("content_checksum", None)
    clone.pop("outputs", None)
    return clone


def _contract_status(result, predictions, config):
    issue_dates_verified = all(
        c.forecast_issue_date and c.publication_month == month_label(c.forecast_origin_month)
        for c in result.contracts.values()
    )
    no_same_month = bool(
        (
            predictions["latest_available_stress_month"] < predictions["forecast_origin_month"]
        ).all()
    )
    labels_enforced = all(
        a.max_target_available_month is None
        or a.max_target_available_month <= a.forecast_origin_month
        for a in result.availability
    )
    supported = issue_dates_verified and no_same_month and labels_enforced
    return {
        "status": (
            "operational_month_timing_supported" if supported else "operational_timing_unverified"
        ),
        "all_development_issue_dates_verified": issue_dates_verified,
        "every_input_obeys_release_timing": no_same_month,
        "no_same_month_stress_used": no_same_month,
        "label_availability_enforced": labels_enforced,
        # Timing validity and vintage validity are reported separately on
        # purpose. A timing fix is not a point-in-time backtest.
        "point_in_time_values_supported": False,
        "latest_vintage_evaluation": True,
        "fully_real_time_backtest": False,
    }


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def _write_locked_manifest(path, config, result):
    locked = config["split"]["locked_test"]
    manifest = {
        "task": "D3",
        "purpose": (
            "Key-only reservation of the locked final test. Contains no target "
            "outcome, no prediction and no metric."
        ),
        "operational_contract_version": config["operational_contract_version"],
        "locked_test_evaluated": False,
        "locked_test_outcomes_read": False,
        "runner_can_reach_locked_origins": False,
        "horizons": {
            str(h): {
                "start": spec["start"],
                "end": spec["end"],
                "issue_months": _month_range(spec["start"], spec["end"]),
            }
            for h, spec in locked["horizons"].items()
        },
        "reserved_months": sorted(locked_month_set(config)),
        "purge_months": sorted(purge_month_set(config)),
        "development_months_evaluated": [month_label(o) for o in result.origins],
        "note": (
            "Locked months are rejected inside build_origin_contracts, before any "
            "data is read. There is no argument, environment variable or alternate "
            "code path in the D3 runner that evaluates them."
        ),
    }
    _write_json(path, manifest)


def _month_range(start, end):
    from thai_supply_chain_ews.evaluation.splits import add_months

    months, month = [], start + "-01"
    while month_label(month) <= end:
        months.append(month_label(month))
        month = add_months(month, 1)
    return months


def _write_markdown(path, payload):
    lines = []
    add = lines.append
    status = payload["contract_status"]
    add("# Task D3 — Operational Baseline Results")
    add("")
    add("*Generated {}. Contract `{}`.*".format(
        payload["generated_at_utc"], payload["operational_contract_version"]))
    add("")
    add("**Framing: `{}`.**".format(payload["evaluation_framing"]))
    add("")
    add("Release timing is now honoured: at forecast issue month *t* the newest")
    add("published MPI stress month is *t-1*, and the forecast is issued after the")
    add("verified OIE release of *t-1*. The target **values** are still latest-vintage,")
    add("because D2 found no complete 12-industry MPI vintages exist. This is **not** a")
    add("fully real-time or point-in-time backtest.")
    add("")
    add("| flag | value |")
    add("| --- | --- |")
    for key, value in payload["dataset_flags"].items():
        add(f"| `{key}` | `{value}` |")
    add("")
    add("## Contract status: `{}`".format(status["status"]))
    add("")
    for key in ("all_development_issue_dates_verified", "no_same_month_stress_used",
                "label_availability_enforced", "point_in_time_values_supported",
                "latest_vintage_evaluation", "fully_real_time_backtest"):
        add(f"* `{key}`: `{status[key]}`")
    add("")
    add("## Forecast origins")
    add("")
    add("| issue month *t* | issue date | latest stress *t-1* | calib end |"
        " obs | h=1 target | h=3 window |")
    add("| --- | --- | --- | --- | ---: | --- | --- |")
    for contract in payload["origin_contracts"]:
        targets = contract["target_months"]
        h1 = targets.get("1") or targets.get(1)
        h3 = targets.get("3") or targets.get(3)
        add("| {} | {} | {} | {} | — | {} | {}..{} |".format(
            month_label(contract["forecast_origin_month"]),
            contract["forecast_issue_date"],
            month_label(contract["latest_available_stress_month"]),
            month_label(contract["calibration_reference_end"]),
            month_label(h1[0]), month_label(h3[0]), month_label(h3[1])))
    add("")
    add("## Prediction counts")
    add("")
    counts = payload["prediction_counts"]
    add(
        f"h=1 **{counts['horizon_1']}**, h=3 **{counts['horizon_3']}**, "
        f"combined **{counts['total']}**."
    )
    add("")
    for horizon in (1, 3):
        block = payload["metrics"][str(horizon)]["baselines"]
        add(f"## h={horizon} development metrics")
        add("")
        add("| baseline | macro MAE | pooled MAE | macro RMSE | pooled RMSE |"
            " median AE | Spearman |")
        add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for name in sorted(block, key=lambda n: block[n]["macro_industry_mae"]):
            m = block[name]
            add("| `{}` | **{:.4f}** | {:.4f} | {:.4f} | {:.4f} | {:.4f} | {:.4f} |".format(
                name, m["macro_industry_mae"], m["pooled_mae"], m["macro_industry_rmse"],
                m["pooled_rmse"], m["median_absolute_error"], m["pooled_spearman"]))
        add("")
        add("### High-stress events (score >= 85)")
        add("")
        add("| baseline | observed | predicted | precision | recall | F1 | FN |")
        add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for name in sorted(block, key=lambda n: block[n]["macro_industry_mae"]):
            h = block[name]["high_stress"]
            add("| `{}` | {} | {} | {} | {} | {} | {} |".format(
                name, h.get("observed_events"), h.get("predicted_events"),
                _fmt(h.get("precision")), _fmt(h.get("recall")), _fmt(h.get("f1")),
                h.get("false_negative")))
        add("")
        add("### Macro MAE 95% bootstrap intervals")
        add("")
        add("| baseline | macro MAE | 95% CI |")
        add("| --- | ---: | --- |")
        for name in sorted(block, key=lambda n: block[n]["macro_industry_mae"]):
            ci = block[name]["macro_mae_ci"]
            add("| `{}` | {:.4f} | [{:.4f}, {:.4f}] |".format(
                name, block[name]["macro_industry_mae"],
                ci["ci_low"], ci["ci_high"]))
        add("")
        selection = payload["benchmark_selection"][str(horizon)]
        add("### Selected operational benchmark")
        add("")
        add("**`{}`** — macro MAE **{:.4f}**, by rule `{}`.".format(
            selection["selected_benchmark"], selection["macro_industry_mae"],
            selection["rule_applied"]))
        if "operational_penalty" in selection:
            add("")
            add("Operational penalty vs B4's `{}` ({:.4f}): **{:+.4f}**.".format(
                selection["b4_reference_baseline"],
                selection["b4_reference_macro_industry_mae"],
                selection["operational_penalty"]))
            add("")
            add("> {}".format(selection["operational_penalty_attribution"]))
        add("")
    add("## Locked final test")
    add("")
    add("Reserved and **unopened**. `locked_test_evaluated: false`,")
    add("`locked_test_outcomes_read: false`. See")
    add("[`d3_locked_test_manifest.json`](d3_locked_test_manifest.json).")
    add("")
    add("## Related")
    add("")
    add("* [`d3_operational_evaluation_protocol.md`](d3_operational_evaluation_protocol.md)")
    add("* [`d1_development_results.errata.md`](d1_development_results.errata.md)")
    add("* [`d2_target_timing_decision.md`](d2_target_timing_decision.md)")
    add("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _fmt(value):
    return "—" if value is None else f"{float(value):.4f}"


def _print_summary(payload, predictions):
    print("D3 operational evaluation complete.")
    print("  framing            :", payload["evaluation_framing"])
    print("  contract status    :", payload["contract_status"]["status"])
    print("  issue months       :", payload["split"]["development_issue_month_count"])
    totals = payload["prediction_counts"]
    print(
        "  predictions        :", totals["total"],
        f"(h1 {totals['horizon_1']} / h3 {totals['horizon_3']})",
    )
    for horizon in (1, 3):
        selection = payload["benchmark_selection"][str(horizon)]
        line = (
            f"  h={horizon} benchmark      : {selection['selected_benchmark']}"
            f"  macroMAE={selection['macro_industry_mae']:.4f}"
            f"  rule={selection['rule_applied']}"
        )
        if "operational_penalty" in selection:
            line += "  penalty={:+.4f}".format(selection["operational_penalty"])
        print(line)
    print("  locked test opened :", payload["split"]["locked_test_evaluated"])
    print("  checksum           :", payload["content_checksum"])


if __name__ == "__main__":
    raise SystemExit(main())
