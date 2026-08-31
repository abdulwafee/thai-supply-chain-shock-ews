"""Prediction lineage and decision rules for the D5 development evaluation.

Every one of the 720 predictions has to be able to explain itself along the
whole chain: which frozen protocol produced it, which authorization permitted
it, which architecture it implements, which conditioned feature row and which
C8 transformation it rests on, which exposure vector and centring rule scaled
it, which training issues were used, which scaler statistics and penalty
specification were in force, which coefficients came out, which benchmark it
corrected, and where the calibrator and label availability were cut.

A digest over part of that chain is not lineage. Two predictions that differ
only in the training window, or only in the calibrator cutoff, would collide,
and the collision would look like reproducibility.

**IND-04 is a different kind of row and says so.** It carries no fuel-oil
predictor, no fitted fixed effect and a residual correction of exactly zero,
because the benchmark passes through untouched. That is a structural exclusion,
not a coefficient that happened to be estimated at zero, and
:func:`assert_passthrough_not_a_fitted_zero` raises on the second description.

The decision rules live here too, frozen before any target value was read: an
interval entirely below zero is support, entirely above is adverse, and anything
touching zero is inconclusive. No result reachable through this module selects a
channel, approves a feature or opens the locked test.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "IND_04_PREDICTION_SOURCE",
    "LINEAGE_FIELDS",
    "MAE_EVIDENCE_STATUSES",
    "OVERALL_STATUSES",
    "PREDICTION_COLUMNS",
    "LineageError",
    "assert_no_channel_promotion",
    "assert_no_confirmatory_claim",
    "assert_passthrough_not_a_fitted_zero",
    "classify_mae_evidence",
    "content_checksum",
    "event_safety_status",
    "overall_status",
    "prediction_lineage_checksum",
    "prediction_lineage_record",
]

IND_04_PREDICTION_SOURCE = "benchmark_passthrough_direction_ambiguous"

MAE_EVIDENCE_STATUSES = ("supported", "adverse", "inconclusive")

OVERALL_STATUSES = (
    "exploratory_incremental_signal_supported",
    "incremental_signal_not_supported",
    "inconclusive",
)

#: Every field is required. A prediction traced through part of its chain is
#: not traced, and the missing part is exactly where two rows would collide.
LINEAGE_FIELDS = (
    "d5_protocol_checksum",
    "c11r1_authorization_checksum",
    "c11_architecture_checksum",
    "c10_design_matrix_checksum",
    "c9_conditioned_feature_row",
    "c8_transformation_lineage",
    "sector_093_exposure_and_centering_scaling_rule",
    "training_issue_keys",
    "scaler_statistics",
    "penalty_specification",
    "fitted_coefficient_checksum",
    "benchmark_lineage",
    "calibrator_cutoff",
    "label_availability_cutoff",
    "prediction_clipping_state",
    "ind_04_passthrough_reason",
)

PREDICTION_COLUMNS = (
    "variant_id", "horizon", "issue_month", "industry_id", "reference_month",
    "prediction_source", "benchmark_name", "benchmark_score", "residual_correction",
    "predicted_score", "clipped", "observed_score", "latest_available_stress_month",
    "calibration_reference_end", "target_window_start", "target_window_end",
    "target_available_month", "training_issue_count", "training_row_count",
    "fitted_coefficient_checksum", "prediction_lineage_checksum",
)


class LineageError(ValueError):
    """A prediction was asked to justify itself with part of its chain."""


def assert_passthrough_not_a_fitted_zero(record: dict) -> None:
    """Raise if IND-04's passthrough is described as an estimated coefficient.

    Its correction is zero because no correction exists for it, not because a
    fitted parameter landed there. Collapsing the two would turn a structural
    limitation into a measurement.
    """
    if record.get("industry_id") != "IND-04":
        return
    if record.get("prediction_source") != IND_04_PREDICTION_SOURCE:
        raise LineageError(
            f"IND-04 carries prediction_source "
            f"{record.get('prediction_source')!r}, expected "
            f"{IND_04_PREDICTION_SOURCE!r}"
        )
    if record.get("residual_correction") not in (0, 0.0):
        raise LineageError(
            f"IND-04 carries a residual correction of "
            f"{record.get('residual_correction')!r}. The benchmark passes through "
            "untouched"
        )
    if record.get("industry_fixed_effect_fitted"):
        raise LineageError(
            "IND-04 was given a fitted industry effect. It is excluded from the "
            "fit; its zero correction is a structural exclusion, not a "
            "coefficient that happened to be estimated at zero"
        )
    reason = str(record.get("ind_04_passthrough_reason", "")).lower()
    if "fitted" in reason or "coefficient" in reason:
        raise LineageError(
            f"IND-04's passthrough reason {record.get('ind_04_passthrough_reason')!r} "
            "describes it as a fitted zero coefficient"
        )


def prediction_lineage_record(prediction: dict, references: dict) -> dict:
    """The complete provenance of one prediction, modelled or passthrough."""
    missing = [field for field in LINEAGE_FIELDS if field not in references]
    if missing:
        raise LineageError(
            f"prediction lineage is missing {sorted(missing)}; a prediction traced "
            "through part of its chain is not traced"
        )
    for field in LINEAGE_FIELDS:
        if field == "ind_04_passthrough_reason":
            continue
        if references[field] in (None, "", [], {}):
            raise LineageError(f"prediction lineage has an empty {field}")
    if prediction.get("industry_id") == "IND-04":
        if not references["ind_04_passthrough_reason"]:
            raise LineageError(
                "IND-04 needs a passthrough reason in its lineage"
            )
    assert_passthrough_not_a_fitted_zero({**prediction, **references})
    return {
        "variant_id": prediction["variant_id"],
        "horizon": int(prediction["horizon"]),
        "issue_month": prediction["issue_month"],
        "industry_id": prediction["industry_id"],
        "reference_month": prediction["reference_month"],
        "prediction_source": prediction["prediction_source"],
        "benchmark_name": prediction["benchmark_name"],
        "predicted_score": prediction["predicted_score"],
        "residual_correction": prediction["residual_correction"],
        "clipped": bool(prediction["clipped"]),
        "references": {field: references[field] for field in LINEAGE_FIELDS},
    }


def _token(value):
    if value is None:
        return "\x00null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.12e}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\x1e".join(_token(item) for item in value)
    if isinstance(value, dict):
        return "\x1e".join(f"{k}={_token(v)}" for k, v in sorted(value.items()))
    return str(value)


def prediction_lineage_checksum(record: dict) -> str:
    """SHA-256 over the prediction and every reference in its chain."""
    payload = [
        record["variant_id"], str(record["horizon"]), record["issue_month"],
        record["industry_id"], record["reference_month"],
        record["prediction_source"], _token(record["benchmark_name"]),
        _token(record["predicted_score"]), _token(record["residual_correction"]),
        _token(record["clipped"]),
    ]
    payload += [_token(record["references"][field]) for field in LINEAGE_FIELDS]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Frozen decision rules
# ---------------------------------------------------------------------------
def classify_mae_evidence(paired_ci_low: float, paired_ci_high: float) -> str:
    """The interval decides, not the point estimate.

    ``delta = MAE_model - MAE_benchmark``, so an interval entirely below zero is
    support and entirely above is adverse. A lower point estimate whose interval
    still touches zero is inconclusive, which is the common case on fifteen
    clusters.
    """
    if paired_ci_high is None or paired_ci_low is None:
        return "inconclusive"
    if paired_ci_high < 0.0:
        return "supported"
    if paired_ci_low > 0.0:
        return "adverse"
    return "inconclusive"


def event_safety_status(model_false_negatives: int,
                        benchmark_false_negatives: int) -> dict:
    """A missed high-stress month is the expensive error; count them."""
    passed = int(model_false_negatives) <= int(benchmark_false_negatives)
    return {
        "model_false_negatives": int(model_false_negatives),
        "benchmark_false_negatives": int(benchmark_false_negatives),
        "event_safety_passed": passed,
        "threshold": 85,
        "threshold_tuned": False,
    }


def overall_status(mae_evidence: str, event_safety_passed: bool) -> str:
    """Support needs both gates; adverse needs only the MAE interval."""
    if mae_evidence not in MAE_EVIDENCE_STATUSES:
        raise LineageError(f"unknown MAE evidence status {mae_evidence!r}")
    if mae_evidence == "supported" and event_safety_passed:
        return "exploratory_incremental_signal_supported"
    if mae_evidence == "adverse":
        return "incremental_signal_not_supported"
    return "inconclusive"


def assert_no_channel_promotion(decision: dict) -> None:
    """Raise if a result promoted, ranked or preferred one fuel-oil variant."""
    if decision.get("channel_selected") or decision.get("primary_channel_selected"):
        raise LineageError(
            "a fuel-oil channel was selected. FO 600 and FO 1500 are co-equal "
            "separate variants reported side by side; D5 has no channel-selection "
            "authorization"
        )
    if decision.get("channels_ranked_by_mae") or decision.get(
            "channels_ranked_by_event_metrics"):
        raise LineageError(
            "the two variants were ranked against each other on a development "
            "metric, which is channel selection under another name"
        )


def assert_no_confirmatory_claim(decision: dict) -> None:
    """Raise if a development result was treated as confirmatory or approving."""
    for field in ("confirmatory_evaluation", "model_feature_approved",
                  "locked_test_evaluation_authorized", "locked_test_accessed",
                  "purge_evaluated"):
        if decision.get(field):
            raise LineageError(
                f"{field} is true. D5 is a development-only exploratory "
                "evaluation: it approves no feature, opens no locked test and "
                "supports no confirmatory claim, whatever the numbers say"
            )


def content_checksum(payload) -> str:
    """Stable digest of a JSON payload, generation timestamps excluded."""
    dropped = {"generated_at_utc", "run_started_at_utc", "run_finished_at_utc"}

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in dropped}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    text = json.dumps(strip(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
