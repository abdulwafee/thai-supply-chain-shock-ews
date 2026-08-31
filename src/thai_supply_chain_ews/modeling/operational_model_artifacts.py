"""Prediction records and artifact checksums for the D4 model (Task D4).

The prediction table is the evidence, so it carries enough lineage to be
re-derived without rerunning anything: which benchmark was used and what it
predicted, the residual the model added, the value before and after clipping,
the scaler and model checksums, and the C2/C3 lineage checksums the feature
vector came with.

The audit-column list is deliberately explicit rather than inferred from the
first record, so a silently dropped field fails loudly instead of vanishing.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "OPERATIONAL_MODEL_PREDICTION_COLUMNS",
    "checksum_mapping",
    "feature_snapshot_checksum",
]

OPERATIONAL_MODEL_PREDICTION_COLUMNS = [
    "forecast_origin_month",
    "forecast_issue_date",
    "latest_available_stress_month",
    "industry_id",
    "horizon_months",
    "model_name",
    "feature_variant",
    "d3_benchmark_name",
    "d3_benchmark_prediction",
    "predicted_residual",
    "model_quality",
    "unclipped_prediction",
    "predicted_score",
    "clipped",
    "observed_raw_target",
    "observed_score",
    "observed_risk_level",
    "calibration_reference_end",
    "calibration_fingerprint",
    "max_training_target_window_end",
    "max_training_target_available_month",
    "label_permitted_rows",
    "feature_usable_rows",
    "predictor_names",
    "predictor_count",
    "omitted_ineligible_predictors",
    "omitted_zero_variance_predictors",
    "fixed_alpha",
    "fixed_nonferrous_channel",
    "aluminum_predictors_present",
    "copper_predictors_present",
    "shared_io_sector_107_used",
    "scaler_checksum",
    "model_checksum",
    "feature_snapshot_checksum",
    "c2_lineage_checksums",
    "c3_exposure_checksums",
    "operational_contract_version",
    "model_version",
    "split_name",
    "exploratory_development_evaluation",
    "confirmatory_result",
    "locked_test_accessed",
]


def _stable(value) -> str:
    if isinstance(value, (list, tuple)):
        return json.dumps([str(v) for v in value], separators=(",", ":"))
    if isinstance(value, dict):
        return json.dumps(
            {str(k): str(v) for k, v in sorted(value.items())}, separators=(",", ":")
        )
    return repr(value)


def feature_snapshot_checksum(vector: dict) -> str:
    """Checksum the exact feature row a prediction was produced from."""
    payload = json.dumps(
        {
            "origin": str(vector.get("origin")),
            "industry_id": str(vector.get("industry_id")),
            "channel": str(vector.get("non_ferrous_channel")),
            "predictors": [str(n) for n in vector.get("predictor_names", ())],
            "values": [repr(float(v)) for v in vector.get("values", ())],
            "reference_months": [str(m) for m in vector.get("reference_months", ())],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def checksum_mapping(mapping) -> str:
    """Deterministic checksum of a lineage mapping or sequence."""
    return hashlib.sha256(_stable(mapping).encode("utf-8")).hexdigest()
