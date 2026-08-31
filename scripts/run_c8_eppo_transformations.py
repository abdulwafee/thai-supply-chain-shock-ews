"""Task C8 — EPPO fuel-oil source-level transformations.

Builds the complete 2 x 65 x 5 transformation grid for the two fuel-oil series
C7.5 approved, from ``monthly_value_strict`` only, propagating every source gap
according to each formula's declared input window.

SOURCE-LEVEL TRANSFORMATION ONLY. No industry exposure multiplication, no
industry-conditioned matrix, no MPI join, no target association, no model, no
locked-test access. C7 and C7.5 artifacts are read-only here.

    data/features/c8_eppo_fuel_oil_transformations.parquet   (git-ignored)
    docs/c8_eppo_transformation_protocol.md
    docs/c8_eppo_transformation_audit.{md,json}
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.features import (  # noqa: E402
    eppo_fuel_oil_transformations as T,
)
from thai_supply_chain_ews.features import (  # noqa: E402
    eppo_transformation_availability as AV,
)
from thai_supply_chain_ews.features import (  # noqa: E402
    eppo_transformation_lineage as LIN,
)

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "eppo_fuel_oil_transformations.yaml"
SPLITS_CONFIG = ROOT / "configs" / "operational_evaluation.yaml"
C7_5_DECISION = DOCS / "c7_5_eppo_semantic_decision.json"
SEMANTIC_PARQUET = ROOT / "data" / "interim" / "c7_5_eppo_monthly_semantic.parquet"
FEATURE_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"

FO600 = "eppo_ex_refinery_fo600_2s"
FO1500 = "eppo_ex_refinery_fo1500_2s"
HSD = "eppo_ex_refinery_hsd"


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 1. C7.5 invariants. C8 may not proceed on a source whose facts moved, and may
#    not silently repair a C7.5 artifact.
# ---------------------------------------------------------------------------
def reproduce_c7_5_invariants() -> dict:
    decision = load_json(C7_5_DECISION)
    overlay = pd.read_parquet(SEMANTIC_PARQUET)
    rows = decision["monthly_rows"]
    statuses = Counter(r["aggregation_status"] for r in rows)
    approvals = decision["separated_approvals"]
    equivalence = {
        d["canonical_product_id"]: d["decision"]
        for d in decision["equivalence"]["decisions"]
    }
    months = {
        series: sorted(r["reference_month"] for r in rows if r["series_id"] == series)
        for series in (FO600, FO1500, HSD)
    }
    fo_variant_months = sorted({
        r["reference_month"] for r in rows
        if r["aggregation_status"] == "approved_with_source_label_variant"
    })
    hsd_gap = sorted(
        r["reference_month"] for r in rows
        if r["series_id"] == HSD and r["aggregation_status"] == "semantic_definition_gap"
    )
    strict_null_2026_04 = {
        series: next(
            r["monthly_value_strict"] for r in rows
            if r["series_id"] == series and r["reference_month"] == "2026-04"
        )
        for series in (FO600, FO1500)
    }

    checks = {
        "semantic_monthly_rows": (len(rows), 195),
        "overlay_parquet_rows": (len(overlay), 195),
        "reference_months_per_series": (
            sorted({len(v) for v in months.values()}), [65],
        ),
        "reference_month_range": (
            [months[FO600][0], months[FO600][-1]], ["2021-01", "2026-05"],
        ),
        "approved_complete_inventory_rows": (statuses["approved_complete_inventory"], 168),
        "approved_with_source_label_variant_rows": (
            statuses["approved_with_source_label_variant"], 8,
        ),
        "semantic_definition_gap_rows": (statuses["semantic_definition_gap"], 16),
        "known_document_gap_rows": (statuses["known_document_gap"], 3),
        "fo600_equivalence_established": (
            equivalence[FO600], "equivalence_established",
        ),
        "fo1500_equivalence_established": (
            equivalence[FO1500], "equivalence_established",
        ),
        "raw_labels_preserved": (
            decision["raw_label_preservation"]["raw_labels_overwritten"], False,
        ),
        "hsd_not_transformation_ready": (
            approvals[HSD]["series_ready_for_transformation_with_explicit_gaps"], False,
        ),
        "fo600_transformation_ready": (
            approvals[FO600]["series_ready_for_transformation_with_explicit_gaps"], True,
        ),
        "fo1500_transformation_ready": (
            approvals[FO1500]["series_ready_for_transformation_with_explicit_gaps"], True,
        ),
        "fo600_strict_null_2026_04": (strict_null_2026_04[FO600], None),
        "fo1500_strict_null_2026_04": (strict_null_2026_04[FO1500], None),
        "fo_variant_months_2024_07_to_2024_10": (
            fo_variant_months, ["2024-07", "2024-08", "2024-09", "2024-10"],
        ),
        "hsd_gap_2023_09_to_2024_12": (
            [hsd_gap[0], hsd_gap[-1], len(hsd_gap)], ["2023-09", "2024-12", 16],
        ),
        "operational_policy_lag_months": (
            decision["inherited_policy"]["operational_policy_lag_months"], 2,
        ),
        "operational_lag_is_measured": (
            decision["inherited_policy"]["operational_lag_is_measured"], False,
        ),
        "every_source_available_as_of_null": (
            all(r["source_available_as_of"] is None for r in rows), True,
        ),
        "simultaneous_additive_fuel_oil_use_prohibited": (
            decision["c8_authorization"][
                "c8_simultaneous_additive_fuel_oil_use_authorized"], False,
        ),
        "c8_fo600_authorized": (
            decision["c8_authorization"]["c8_fo600_transformation_authorized"], True,
        ),
        "c8_fo1500_authorized": (
            decision["c8_authorization"]["c8_fo1500_transformation_authorized"], True,
        ),
        "c8_hsd_not_authorized": (
            decision["c8_authorization"]["c8_hsd_transformation_authorized"], False,
        ),
    }
    result = {
        name: {"actual": actual, "expected": expected, "reproduced": actual == expected}
        for name, (actual, expected) in checks.items()
    }
    failed = sorted(n for n, c in result.items() if not c["reproduced"])
    return {"all_reproduced": not failed, "failed": failed, "checks": result}


# ---------------------------------------------------------------------------
# 2. Source observations. Strict values only.
# ---------------------------------------------------------------------------
def load_source_months(config: dict) -> list:
    overlay = pd.read_parquet(SEMANTIC_PARQUET)
    authorized = set(config["input"]["series"])
    observations = []
    for row in overlay.to_dict("records"):
        if row["series_id"] not in authorized:
            continue
        value = row["monthly_value_strict"]
        if value is not None and pd.isna(value):
            value = None
        # A parquet list column comes back as a numpy array; `or []` on one
        # raises rather than falling through, so length is tested explicitly.
        raw_labels = row["source_product_labels_raw"]
        labels = [] if raw_labels is None else [str(x) for x in raw_labels]
        rule = row["semantic_equivalence_rule_id"]
        observations.append(T.SourceMonth(
            series_id=row["series_id"],
            reference_month=row["reference_month"],
            monthly_value_strict=None if value is None else float(value),
            approved_transformation_input=bool(row["approved_transformation_input"]),
            unit=config["input"]["required_unit"],
            source_product_label=" | ".join(labels) if labels else None,
            canonical_product_id=row["canonical_product_id"],
            semantic_equivalence_rule_id=None if rule is None or pd.isna(rule) else rule,
            aggregation_rule_version=row["aggregation_rule_version"],
            aggregation_status=row["aggregation_status"],
            monthly_lineage_checksum=row["lineage_checksum"],
            policy_available_month=row["policy_available_month"],
        ))
    return observations


def build_grid(observations, config: dict):
    indexed = {(o.series_id, o.reference_month): o for o in observations}
    months = T.month_range(
        config["input"]["reference_month_start"], config["input"]["reference_month_end"]
    )
    lag = config["timing_policy"]["operational_policy_lag_months"]

    def policy_month(window):
        return AV.transformation_policy_available_month(window, lag)

    def lineage(row, source_index):
        available = [
            LIN.source_input_lineage(source_index[(row.series_id, month)])
            for month in row.required_input_months
            if (row.series_id, month) in source_index
            and month not in row.missing_input_months
        ]
        record = LIN.transformation_lineage_record(
            transformation_id=row.transformation_id,
            transformation_formula_version=row.transformation_formula_version,
            channel_id=row.channel_id,
            reference_month=row.reference_month,
            required_input_months=row.required_input_months,
            available_inputs=available,
            missing_input_months=row.missing_input_months,
            feature_value=row.feature_value,
            transformation_status=row.transformation_status,
            availability_policy_version=AV.AVAILABILITY_POLICY_VERSION,
            feature_unit=row.feature_unit,
        )
        row_records[(row.channel_id, row.reference_month, row.transformation_id)] = record
        return LIN.transformation_lineage_checksum(record)

    row_records = {}
    rows = T.build_transformation_grid(
        observations, sorted(config["input"]["series"]), months,
        series_start=config["input"]["reference_month_start"],
        policy_month_fn=policy_month, lineage_fn=lineage,
    )
    _ = indexed
    return rows, row_records, months


# ---------------------------------------------------------------------------
# 3. Count reconciliation. Preregistered, derived, and observed must all agree.
# ---------------------------------------------------------------------------
def reconcile_counts(rows, config: dict) -> dict:
    preregistered = config["expected_counts"]
    derived = T.expected_counts(
        months=config["input"]["reference_months"],
        gap_months=tuple(preregistered["known_strict_source_gaps"]),
        series_start=config["input"]["reference_month_start"],
        series_end=config["input"]["reference_month_end"],
    )
    observed = defaultdict(lambda: defaultdict(lambda: {"finite": 0, "null_rows": 0}))
    for row in rows:
        bucket = "finite" if row.feature_value is not None else "null_rows"
        observed[row.channel_id][row.transformation_id][bucket] += 1

    disagreements = []
    for channel_id, per_transformation in observed.items():
        for transformation_id, counts in per_transformation.items():
            expected = preregistered["per_series"][transformation_id]
            if (counts["finite"] != expected["finite"]
                    or counts["null_rows"] != expected["null_rows"]):
                disagreements.append({
                    "channel_id": channel_id, "transformation_id": transformation_id,
                    "observed": dict(counts), "preregistered": dict(expected),
                })
            if derived[transformation_id] != {
                "finite": expected["finite"], "null_rows": expected["null_rows"]
            }:
                disagreements.append({
                    "transformation_id": transformation_id,
                    "derived": derived[transformation_id],
                    "preregistered": dict(expected),
                    "note": "derived counts disagree with the preregistered table",
                })

    totals = {
        "feature_grid_rows": len(rows),
        "finite_feature_rows": sum(1 for r in rows if r.feature_value is not None),
        "null_feature_rows": sum(1 for r in rows if r.feature_value is None),
    }
    for key, expected in preregistered["both_series"].items():
        if totals[key] != expected:
            disagreements.append({
                "total": key, "observed": totals[key], "preregistered": expected,
            })
    return {
        "preregistered": preregistered,
        "derived_from_declared_lags": derived,
        "observed_by_channel": {
            channel: {k: dict(v) for k, v in per.items()}
            for channel, per in observed.items()
        },
        "totals": totals,
        "disagreements": disagreements,
        "counts_reconciled": not disagreements,
        "counts_altered_after_observing_output": False,
    }


# ---------------------------------------------------------------------------
# 4. Operational issue-key audit. Issue-month RANGES only.
# ---------------------------------------------------------------------------
def split_issue_months() -> dict:
    splits = load_yaml(SPLITS_CONFIG)["split"]
    locked = splits["locked_test"]["horizons"]
    return {
        "development": T.month_range(
            splits["development"]["start"], splits["development"]["end"]
        ),
        "purge": T.month_range(splits["purge"]["start"], splits["purge"]["end"]),
        "locked_test": T.month_range(
            min(h["start"] for h in locked.values()),
            max(h["end"] for h in locked.values()),
        ),
    }


def issue_key_audit(table, splits) -> dict:
    coverage = {}
    for split_name, issue_months in splits.items():
        coverage[split_name] = {}
        for channel_id in sorted(T.SERIES_BY_CHANNEL):
            report = AV.issue_key_coverage(table, issue_months, channel_id)
            per_issue = report["per_issue_month"]
            fully = [
                month for month, entry in per_issue.items()
                if not entry["transformations_blocked_at_the_latest_permitted_month"]
            ]
            coverage[split_name][channel_id] = {
                "issue_months": len(per_issue),
                "issue_months_with_no_blocked_transformation": len(fully),
                "issue_months_with_a_blocked_transformation": sorted(
                    set(per_issue) - set(fully)
                ),
                "latest_permitted_reference_month_range": [
                    per_issue[min(per_issue)]["latest_permitted_reference_month"],
                    per_issue[max(per_issue)]["latest_permitted_reference_month"],
                ],
                "reference_months_with_a_blocked_transformation":
                    report["reference_months_with_a_blocked_transformation"],
                "target_values_read": False,
            }
    return coverage


def april_2026_audit(table, splits) -> dict:
    """Whether any registered issue key can select the 2026-04 source gap."""
    selected = []
    for split_name, issue_months in splits.items():
        for channel_id in sorted(T.SERIES_BY_CHANNEL):
            for issue in issue_months:
                rows = AV.select_source_transformations_available_at_issue(
                    table, issue, channel_id
                )
                hits = [r for r in rows if r["reference_month"] == "2026-04"]
                if hits:
                    selected.append({
                        "split": split_name, "channel_id": channel_id,
                        "issue_month": issue, "rows": len(hits),
                    })
    gap_rows = [
        r for r in table
        if r["reference_month"] == "2026-04" and r["feature_value"] is None
    ]
    return {
        "reference_month": "2026-04",
        "selected_by_any_registered_issue_key": bool(selected),
        "selections": selected,
        "null_rows_retained_in_the_grid": len(gap_rows),
        "statuses": dict(Counter(r["transformation_status"] for r in gap_rows)),
        "removed_because_operationally_unused": False,
        "note": (
            "The maximum registered issue month is 2026-04 and the policy lag is "
            "2, so no registered key reaches reference month 2026-04. The gap is "
            "kept and reported anyway."
        ),
    }


# ---------------------------------------------------------------------------
# 5. Output.
# ---------------------------------------------------------------------------
def write_parquet(rows):
    frame = pd.DataFrame(rows)
    for column in ("required_input_months", "missing_input_months",
                   "source_monthly_lineage_checksums"):
        frame[column] = frame[column].apply(lambda v: list(v or []))
    FEATURE_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(FEATURE_PARQUET, index=False)
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    invariants = reproduce_c7_5_invariants()
    if not invariants["all_reproduced"]:
        raise SystemExit(
            f"C8 stops: C7.5 invariants did not reproduce: {invariants['failed']}. "
            "C7.5 artifacts are not repaired here."
        )

    compatibility = T.assert_c2_formula_compatibility()
    observations = load_source_months(config)
    rows, lineage_records, months = build_grid(observations, config)
    table = [row.to_dict() for row in rows]

    counts = reconcile_counts(rows, config)
    if not counts["counts_reconciled"]:
        raise SystemExit(
            "C8 stops: count reconciliation failed. "
            f"{json.dumps(counts['disagreements'], ensure_ascii=False)}. "
            "Expected counts were preregistered and are not altered after the run; "
            "an upstream invariant must be reviewed."
        )

    # Availability is asserted per row rather than assumed from the config.
    lag = config["timing_policy"]["operational_policy_lag_months"]
    for row in table:
        AV.assert_policy_month_is_not_a_release_date(row)
        AV.assert_policy_month_matches_reference_rule(
            row["reference_month"], row["policy_available_month"], lag
        )

    splits = split_issue_months()
    coverage = issue_key_audit(table, splits)
    april = april_2026_audit(table, splits)

    selector_examples = []
    for issue, expected in (("2024-01", "2023-11"), ("2025-03", "2025-01"),
                            ("2026-04", "2026-02")):
        latest = AV.latest_permitted_reference_month(issue)
        rows_at_issue = AV.select_source_transformations_available_at_issue(
            table, issue, "eppo_fo600_channel"
        )
        selector_examples.append({
            "issue_month": issue,
            "latest_permitted_reference_month": latest,
            "matches_expected": latest == expected,
            "rows_returned": len(rows_at_issue),
            "max_reference_month_returned": max(
                (r["reference_month"] for r in rows_at_issue), default=None
            ),
        })

    frame = write_parquet(table)

    missingness = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.feature_value is None:
            missingness[row.channel_id][row.transformation_status].append({
                "reference_month": row.reference_month,
                "transformation_id": row.transformation_id,
                "missing_input_months": row.missing_input_months,
                "required_input_months": row.required_input_months,
            })

    readiness = {}
    for channel_id in sorted(T.SERIES_BY_CHANNEL):
        channel_rows = [r for r in rows if r.channel_id == channel_id]
        readiness[channel_id] = {
            "source_transformations_created": True,
            "source_transformations_ready_for_structural_conditioning": bool(
                counts["counts_reconciled"]
                and all(r.transformation_lineage_checksum for r in channel_rows)
                and all(r.source_available_as_of is None for r in channel_rows)
                and all(not r.additive_aggregation_allowed for r in channel_rows)
            ),
            "industry_conditioned_features_created": False,
            "feature_semantics_approved": False,
            "model_feature_approved": False,
            "rows": len(channel_rows),
            "finite_rows": sum(1 for r in channel_rows if r.feature_value is not None),
            "null_rows": sum(1 for r in channel_rows if r.feature_value is None),
        }

    payload = {
        "task": "C8",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "transformation_formula_version": T.TRANSFORMATION_FORMULA_VERSION,
        "authorizations": config["authorizations"],
        "timing_policy": config["timing_policy"],
        "provenance": config["provenance"],
        "preserved_decisions": config["preserved_decisions"],
        "c7_5_invariants": invariants,
        "input": {
            **{k: v for k, v in config["input"].items() if k != "series"},
            "series": config["input"]["series"],
            "source_months_loaded": len(observations),
            "approved_transformation_inputs": sum(1 for o in observations if o.usable),
            "strict_gaps": sorted({
                o.reference_month for o in observations if not o.usable
            }),
            "descriptive_value_read": False,
            "hsd_read": False,
        },
        "transformations": config["transformations"],
        "numerical_rules": config["numerical_rules"],
        "c2_reconciliation": {**config["c2_reconciliation"], **compatibility},
        "missingness": {
            "status_precedence": list(T.TRANSFORMATION_STATUSES),
            "status_counts": dict(Counter(r.transformation_status for r in rows)),
            "by_channel": {
                channel: {status: sorted(
                    (item["reference_month"], item["transformation_id"])
                    for item in items
                ) for status, items in sorted(per.items())}
                for channel, per in missingness.items()
            },
        },
        "counts": counts,
        "availability": {
            **config["availability"],
            "policy_month_equality_verified_rows": len(table),
            "source_available_as_of_null_rows": sum(
                1 for r in table if r["source_available_as_of"] is None
            ),
            "selector_examples": selector_examples,
        },
        "issue_key_coverage": coverage,
        "april_2026": april,
        "channels": {
            **config["channel_restrictions"],
            "shared_price_stage_group": T.SHARED_PRICE_STAGE_GROUP,
            "channel_ids": sorted(T.SERIES_BY_CHANNEL),
        },
        "feature_table": {
            "rows": len(table),
            "unique_key": ["channel_id", "reference_month", "transformation_id"],
            "output": str(FEATURE_PARQUET.relative_to(ROOT)).replace("\\", "/"),
            "model_feature_approved_rows": sum(
                1 for r in table if r["model_feature_approved"]
            ),
            "units": dict(sorted(Counter(
                (r["transformation_id"], r["feature_unit"]) for r in table
            ).items(), key=lambda kv: kv[0])) and {
                t: T.TRANSFORMATION_UNITS[t] for t in T.TRANSFORMATION_IDS
            },
        },
        "lineage": {
            "lineage_version": LIN.LINEAGE_VERSION,
            "rows_with_a_checksum": sum(
                1 for r in rows if r.transformation_lineage_checksum
            ),
            "null_rows_with_complete_lineage": sum(
                1 for key, record in lineage_records.items()
                if record["output_value"] is None
                and record["expected_input_months"] is not None
                and record["missingness_reason"]
            ),
            "distinct_checksums": len({
                r.transformation_lineage_checksum for r in rows
            }),
            "source_input_fields": list(LIN.SOURCE_INPUT_FIELDS),
        },
        "readiness": readiness,
        "c9_boundary": {
            "industry_conditioning_authorized": False,
            "target_join_authorized": False,
            "modeling_authorized": False,
            "outcome_based_channel_selection_authorized": False,
            "simultaneous_additive_fuel_oil_use_authorized": False,
            "locked_test_evaluation_authorized": False,
            "note": (
                "C8 produced source-level transformed data. Conditioning it on "
                "industry exposure is a separate decision that has not been taken."
            ),
        },
    }
    payload["content_checksum"] = LIN.content_checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    with open(DOCS / "c8_eppo_transformation_audit.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
    write_protocol(payload, config)
    write_audit_markdown(payload)

    print(json.dumps({
        "c7_5_invariants_reproduced": invariants["all_reproduced"],
        "grid_rows": payload["counts"]["totals"]["feature_grid_rows"],
        "finite_rows": payload["counts"]["totals"]["finite_feature_rows"],
        "null_rows": payload["counts"]["totals"]["null_feature_rows"],
        "counts_reconciled": counts["counts_reconciled"],
        "status_counts": payload["missingness"]["status_counts"],
        "april_2026_selected_by_any_issue_key": april[
            "selected_by_any_registered_issue_key"],
        "readiness": {
            k: v["source_transformations_ready_for_structural_conditioning"]
            for k, v in readiness.items()
        },
        "content_checksum": payload["content_checksum"],
        "parquet_shape": list(frame.shape),
        "months": len(months),
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def write_protocol(payload: dict, config: dict) -> None:
    lines = [
        "# Task C8 - EPPO Fuel-Oil Transformation Protocol",
        "",
        f"*Config `{payload['config_version']}`, formula version "
        f"`{payload['transformation_formula_version']}`.*",
        "",
        "Preregistered before the run: the formulas, the input windows, the status",
        "vocabulary and precedence, and the expected finite/null counts. The counts",
        "are also derived from the declared input lags at run time, and the runner",
        "fails if the two disagree.",
        "",
        "## Input",
        "",
        f"`{config['input']['dataset']}` ({config['input']['dataset_task']}), field",
        f"**`{config['input']['value_field']}`**, gated on",
        f"**`{config['input']['required_gate_field']}`**, unit",
        f"`{config['input']['required_unit']}`.",
        "",
        "Never read: "
        + ", ".join(f"`{x}`" for x in config["input"]["never_use"]) + ".",
        "",
        "## Formulas",
        "",
        "| transformation | formula | input lags | required inputs | unit |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, spec in config["transformations"].items():
        lines.append(
            f"| `{name}` | `{spec['formula']}` | `{spec['input_lags']}` | "
            f"{spec['required_input_count']} | `{spec['unit']}` |"
        )
    lines += [
        "",
        "Natural logarithm, scaled by 100, volatility with `ddof=0`. The volatility",
        "declares **four** price levels because `r_{m-2}` is itself a change from",
        "`m-3`; declaring three would understate the lineage and the availability",
        "requirement.",
        "",
        "## Missingness precedence",
        "",
        "The first condition that holds decides the status:",
        "",
    ]
    for index, status in enumerate(payload["missingness"]["status_precedence"], start=1):
        lines.append(f"{index}. `{status}`")
    lines += [
        "",
        "Insufficient prehistory is never labelled as a source gap: a month before",
        "the series begins is a property of the window, not of the archive.",
        "",
        "## Preregistered counts",
        "",
        "| transformation | finite | null |",
        "| --- | --- | --- |",
    ]
    for name, spec in config["expected_counts"]["per_series"].items():
        lines.append(f"| `{name}` | {spec['finite']} | {spec['null_rows']} |")
    both = config["expected_counts"]["both_series"]
    lines += [
        "",
        f"Across both channels: **{both['feature_grid_rows']}** grid rows, "
        f"**{both['finite_feature_rows']}** finite, "
        f"**{both['null_feature_rows']}** null.",
        "",
        "## Availability",
        "",
        f"`policy_available_month` = {config['availability']['policy_available_month_rule']}.",
        f"The equality `{config['availability']['expected_equality']}` is **verified**,",
        "not hard-coded.",
        "",
        "`source_available_as_of` stays null: EPPO release timing was never measured,",
        "and the conservative policy month is not a release date.",
        "",
        "## What C8 does not do",
        "",
        "No industry exposure multiplication, no industry-conditioned matrix, no MPI",
        "join, no target association, no model, no locked-test access. The two fuel",
        "oils share I/O sector 093 and are never added, averaged, indexed or entered",
        "together.",
        "",
    ]
    (DOCS / "c8_eppo_transformation_protocol.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_audit_markdown(payload: dict) -> None:
    counts = payload["counts"]
    lines = [
        "# Task C8 - EPPO Fuel-Oil Transformation Audit",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        "## C7.5 invariants",
        "",
        f"All reproduced: **{payload['c7_5_invariants']['all_reproduced']}** "
        f"({len(payload['c7_5_invariants']['checks'])} checks).",
        "",
        "| check | expected | actual |",
        "| --- | --- | --- |",
    ]
    for name, check in payload["c7_5_invariants"]["checks"].items():
        lines.append(f"| `{name}` | `{check['expected']}` | `{check['actual']}` |")

    lines += [
        "",
        "## Counts",
        "",
        f"Grid **{counts['totals']['feature_grid_rows']}** rows, "
        f"**{counts['totals']['finite_feature_rows']}** finite, "
        f"**{counts['totals']['null_feature_rows']}** null. "
        f"Reconciled: **{counts['counts_reconciled']}**.",
        "",
        "| transformation | preregistered finite/null | derived finite/null "
        "| fo600 finite/null | fo1500 finite/null |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in payload["transformations"]:
        pre = counts["preregistered"]["per_series"][name]
        der = counts["derived_from_declared_lags"][name]
        fo600 = counts["observed_by_channel"]["eppo_fo600_channel"][name]
        fo1500 = counts["observed_by_channel"]["eppo_fo1500_channel"][name]
        lines.append(
            f"| `{name}` | {pre['finite']}/{pre['null_rows']} "
            f"| {der['finite']}/{der['null_rows']} "
            f"| {fo600['finite']}/{fo600['null_rows']} "
            f"| {fo1500['finite']}/{fo1500['null_rows']} |"
        )

    lines += [
        "",
        "## Missingness",
        "",
        "| status | rows |",
        "| --- | --- |",
    ]
    for status, count in sorted(payload["missingness"]["status_counts"].items()):
        lines.append(f"| `{status}` | {count} |")
    lines += ["", "### Every null cell, by channel", ""]
    for channel, per_status in payload["missingness"]["by_channel"].items():
        lines.append(f"**`{channel}`**")
        lines.append("")
        for status, items in per_status.items():
            listed = ", ".join(f"{month} `{name}`" for month, name in items)
            lines.append(f"* `{status}` ({len(items)}): {listed}")
        lines.append("")

    april = payload["april_2026"]
    lines += [
        "## April 2026",
        "",
        f"Null rows retained: **{april['null_rows_retained_in_the_grid']}**. "
        f"Statuses: " + ", ".join(f"`{k}` {v}" for k, v in april["statuses"].items())
        + ".",
        "",
        f"Selected by a registered issue key: "
        f"**{april['selected_by_any_registered_issue_key']}**. "
        f"`removed_because_operationally_unused`: "
        f"{_flag(april['removed_because_operationally_unused'])}.",
        "",
        "> " + april["note"],
        "",
        "## Availability",
        "",
        f"`source_available_as_of` is null in "
        f"{payload['availability']['source_available_as_of_null_rows']} of "
        f"{payload['feature_table']['rows']} rows. The equality "
        f"`{payload['availability']['expected_equality']}` was verified on every row.",
        "",
        "| issue month | latest permitted reference month | rows returned "
        "| max reference month returned |",
        "| --- | --- | --- | --- |",
    ]
    for example in payload["availability"]["selector_examples"]:
        lines.append(
            f"| {example['issue_month']} | **{example['latest_permitted_reference_month']}** "
            f"| {example['rows_returned']} | {example['max_reference_month_returned']} |"
        )

    lines += [
        "",
        "## Issue-key coverage",
        "",
        "Derived from preregistered issue-month ranges and the policy lag only; no",
        "target value, prediction or metric was read.",
        "",
        "| split | channel | issue months | with a blocked transformation "
        "| latest permitted reference range |",
        "| --- | --- | --- | --- | --- |",
    ]
    for split_name, per_channel in payload["issue_key_coverage"].items():
        for channel_id, entry in per_channel.items():
            lines.append(
                f"| `{split_name}` | `{channel_id}` | {entry['issue_months']} | "
                f"{len(entry['issue_months_with_a_blocked_transformation'])} | "
                f"{entry['latest_permitted_reference_month_range'][0]} .. "
                f"{entry['latest_permitted_reference_month_range'][1]} |"
            )

    lines += [
        "",
        "## C2 reconciliation",
        "",
        f"`formula_compatible_with_c2`: "
        f"{_flag(payload['c2_reconciliation']['formula_compatible_with_c2'])}, "
        f"`source_timing_contract_differs_from_c2`: "
        f"{_flag(payload['c2_reconciliation']['source_timing_contract_differs_from_c2'])}.",
        "",
        "Shared production implementation:",
        "",
    ]
    for item in payload["c2_reconciliation"]["shared_production_implementation"]:
        lines.append(f"* `{item}`")
    lines += [
        "",
        "| aspect | C2 | C8 |",
        "| --- | --- | --- |",
        "| values | archived first-release | latest vintage |",
        "| publication timing | measured | policy-based |",
        "| point-in-time supported | `True` | `False` |",
        "",
        "Matching formulas do not imply matching evidence quality.",
        "",
        "## Channels",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key, value in payload["channels"].items():
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {_flag(value)} |")
    lines += [
        "",
        f"Shared group `{payload['channels']['shared_price_stage_group']}`; channels "
        + ", ".join(f"`{c}`" for c in payload["channels"]["channel_ids"]) + ".",
        "",
        "## Lineage",
        "",
        f"`{payload['lineage']['lineage_version']}` - "
        f"{payload['lineage']['rows_with_a_checksum']} rows carry a checksum, "
        f"{payload['lineage']['distinct_checksums']} distinct, "
        f"{payload['lineage']['null_rows_with_complete_lineage']} null rows carry "
        "complete lineage naming their expected, available and missing months.",
        "",
        "## Readiness",
        "",
        "| channel | rows | finite | null | ready for structural conditioning |",
        "| --- | --- | --- | --- | --- |",
    ]
    for channel_id, entry in payload["readiness"].items():
        lines.append(
            f"| `{channel_id}` | {entry['rows']} | {entry['finite_rows']} | "
            f"{entry['null_rows']} | "
            f"{_flag(entry['source_transformations_ready_for_structural_conditioning'])} |"
        )
    lines += [
        "",
        "`industry_conditioned_features_created`, `feature_semantics_approved` and",
        "`model_feature_approved` are all `False`. Readiness for structural",
        "conditioning is not approval as a model feature.",
        "",
        f"Content checksum `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c8_eppo_transformation_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
