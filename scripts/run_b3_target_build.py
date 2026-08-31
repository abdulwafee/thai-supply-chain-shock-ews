"""Run Task B3: build the Industry Production Stress Score target.

Produces the STATIC artifacts only — monthly raw stress and raw horizon labels.
Calibrated scores are fold-specific and are NOT persisted as production outputs;
this script demonstrates the fit/transform workflow on one worked example fold
so the mechanism is documented and testable, and writes that calibrator as a
deterministic artifact.

Does not collect upstream features, build dependency matrices, or train models.

Usage:
    python scripts/run_b3_target_build.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from thai_supply_chain_ews.targets.calibration import (  # noqa: E402
    IndustryStressCalibrator,
    assign_risk_levels,
)
from thai_supply_chain_ews.targets.labels import build_forecast_labels  # noqa: E402
from thai_supply_chain_ews.targets.production_stress import (  # noqa: E402
    DEFAULT_PANEL_PATH,
    build_monthly_stress,
    load_target_config,
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "targets"
METADATA_PATH = PROJECT_ROOT / "docs" / "b3_target_build_metadata.json"
CALIBRATOR_PATH = PROJECT_ROOT / "docs" / "b3_example_calibrator.json"

# Worked-example fold used ONLY to demonstrate and test the fit/transform
# mechanism. It is not a project-wide train/test split decision — that belongs
# to the evaluation task.
EXAMPLE_TRAINING_CUTOFF = "2024-12-01"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    config = load_target_config()
    panel_before = sha256_of(DEFAULT_PANEL_PATH)

    monthly = build_monthly_stress()
    labels = build_forecast_labels(monthly.frame, config)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    monthly_path = PROCESSED_DIR / "production_stress_month.parquet"
    labels_path = PROCESSED_DIR / "forecast_target_raw.parquet"
    monthly.frame.to_parquet(monthly_path, index=False, engine="pyarrow")
    labels.frame.to_parquet(labels_path, index=False, engine="pyarrow")

    # --- worked example of the leakage-safe workflow ------------------------
    reference = monthly.frame[
        monthly.frame["reference_month"] <= EXAMPLE_TRAINING_CUTOFF
    ]
    calibration_cfg = config["calibration"]
    calibrator = IndustryStressCalibrator(
        min_reference_observations=int(calibration_cfg["min_reference_observations"]),
        version=calibration_cfg["calibrator_version"],
    ).fit(reference, training_cutoff_month=EXAMPLE_TRAINING_CUTOFF)
    calibrator.to_json(CALIBRATOR_PATH)

    holdout = labels.frame[labels.frame["forecast_origin_month"] > EXAMPLE_TRAINING_CUTOFF].copy()
    holdout["score"] = calibrator.transform_frame(holdout, value_column="target_raw_value")
    holdout["risk_level"] = assign_risk_levels(
        holdout["score"].to_numpy(), config["risk_levels"]
    )
    risk_counts = holdout["risk_level"].value_counts().to_dict()

    panel_after = sha256_of(DEFAULT_PANEL_PATH)

    metadata = {
        "task": "B3",
        "target_name": config["target_name"],
        "target_name_th": config["target_name_th"],
        "target_definition_version": config["target_definition_version"],
        "primary_component": config["primary_component"],
        "primary_component_count": config["primary_component_count"],
        "b1_invariants": monthly.b1_findings,
        "monthly_raw_stress": {
            "rows": int(len(monthly.frame)),
            "industries": len(monthly.industries),
            "months_per_industry": int(
                monthly.frame.groupby("industry_id", observed=True).size().iloc[0]
            ),
            "first_month": monthly.months[0],
            "last_month": monthly.months[-1],
        },
        "forecast_labels": {
            "combined_rows": int(len(labels.frame)),
            "by_horizon": {
                str(h): {
                    "rows": int(len(labels.for_horizon(h))),
                    "first_origin": sorted(
                        labels.for_horizon(h)["forecast_origin_month"].unique().tolist()
                    )[0],
                    "last_origin": sorted(
                        labels.for_horizon(h)["forecast_origin_month"].unique().tolist()
                    )[-1],
                    "origins_per_industry": int(
                        labels.for_horizon(h)
                        .groupby("industry_id", observed=True)
                        .size()
                        .iloc[0]
                    ),
                }
                for h in config["horizons_months"]
            },
        },
        "excluded_target_months": [str(m) for m in config["excluded_target_months"]],
        "example_fold": {
            "purpose": (
                "Demonstrates the fit/transform workflow only. Not a project-wide "
                "train/test split decision."
            ),
            "training_cutoff_month": EXAMPLE_TRAINING_CUTOFF,
            "calibrator_version": calibrator.version,
            "min_reference_observations": calibrator.min_reference_observations,
            "fitted_industries": len(calibrator.fitted_industries),
            "excluded_industries": calibrator.excluded_industries,
            "holdout_label_rows_scored": int(len(holdout)),
            "risk_level_counts": {k: int(v) for k, v in sorted(risk_counts.items())},
            "calibrator_artifact": str(CALIBRATOR_PATH.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "calibrator_sha256": sha256_of(CALIBRATOR_PATH),
        },
        "calibrated_scores_persisted_as_production_output": False,
        "latest_vintage_only": config["latest_vintage_only"],
        "point_in_time_backtest_supported": config["point_in_time_backtest_supported"],
        "b1_panel_sha256_before": panel_before,
        "b1_panel_sha256_after": panel_after,
        "b1_panel_unmodified": panel_before == panel_after,
    }
    METADATA_PATH.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print("=== Task B3 — Industry Production Stress Score ===")
    print(f"target            : {config['target_name']} (K={config['primary_component_count']}, "
          f"{config['primary_component']})")
    print(f"B1 invariants     : reproduced={monthly.b1_findings['all_invariants_reproduced']}")
    print(f"monthly raw stress: {len(monthly.frame)} rows, "
          f"{metadata['monthly_raw_stress']['months_per_industry']}/industry, "
          f"{monthly.months[0]} .. {monthly.months[-1]}")
    for horizon in config["horizons_months"]:
        info = metadata["forecast_labels"]["by_horizon"][str(horizon)]
        print(f"  h={horizon}m targets    : {info['rows']} rows, "
              f"{info['origins_per_industry']}/industry, "
              f"{info['first_origin']} .. {info['last_origin']}")
    print(f"combined labels   : {len(labels.frame)} rows")
    print(f"excluded months   : {metadata['excluded_target_months']}")
    print(f"example fold      : cutoff {EXAMPLE_TRAINING_CUTOFF}, "
          f"{len(calibrator.fitted_industries)} industries fitted, "
          f"{len(calibrator.excluded_industries)} excluded")
    print(f"  holdout scored  : {len(holdout)} label rows -> "
          f"{metadata['example_fold']['risk_level_counts']}")
    print(f"B1 panel unmodified: {metadata['b1_panel_unmodified']}")
    print("\nwritten:")
    for path in (monthly_path, labels_path, CALIBRATOR_PATH, METADATA_PATH):
        print(f"  {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
