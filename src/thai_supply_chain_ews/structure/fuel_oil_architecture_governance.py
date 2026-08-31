"""Task C11-R1 — governance closure over the C11 architecture decision.

C11 reported two things as if they were one. They are not, and separating them
is this module's entire job.

**The decision is dependency-clean.** Nothing in the selected architecture
depends on a target, a prediction or a development metric: it follows from rank
and column-space identities over C8/C9/C10 artifacts and the frozen sector-093
exposure vector, and it reproduces exactly without opening a single D-series
file.

**The execution was not outcome-blind.** During C11 a development metric
artifact was opened. A guard added afterwards prevents recurrence; it does not
alter what happened, and :func:`assert_guard_does_not_erase_history` raises on
any claim that it does. There is no umbrella ``outcome_free: true`` anywhere in
C11-R1, because a dependency-clean decision and an outcome-blind execution
history are different facts.

The same separation applies to the corrected gate. C11's original preregistered
gate expected the *stacked* rank to fall from ten to five under a prohibited
preprocessing. It does not — the centred exposures carry both signs, so ``+x̃``
and ``-x̃`` span two directions. The collapse is real but sits elsewhere: within
an industry ``standardize(E_g X)`` is ``±standardize(X)``, so only the sign
survives and eleven exposure-proportional interaction blocks become two sign
groups. The corrected gate is mathematically valid. It is still a
post-observation specification correction, and
:func:`assert_correction_not_presented_as_preregistered` raises if it is dressed
up as anything else.

Nothing here fits a model, joins a target, computes a metric, selects a channel
or opens the locked test.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "CLOSURE_GATES",
    "D5_AUTHORIZATION_FIELDS",
    "DECISION_STATUS",
    "GOVERNANCE_VERSION",
    "REQUIRED_CORRECT_MEASUREMENTS",
    "REQUIRED_GATE_STATUS_FIELDS",
    "REQUIRED_INCIDENT_STATUS_FIELDS",
    "AuthorizationError",
    "CorrectedGateSpecification",
    "GovernanceError",
    "PreservationError",
    "assert_c11_record_preserved",
    "assert_correct_measurements_present",
    "assert_correction_frozen",
    "assert_correction_not_presented_as_preregistered",
    "assert_guard_does_not_erase_history",
    "assert_incident_recorded",
    "assert_no_umbrella_outcome_free_claim",
    "assert_not_described_as_a_tolerance_change",
    "assert_original_gate_set_not_reported_as_passing",
    "assert_status_is_exploratory",
    "authorize_d5",
    "content_checksum",
    "correction_checksum",
    "evaluate_closure_gates",
    "governance_checksum",
]

GOVERNANCE_VERSION = "c11r1_fuel_oil_architecture_governance_v1"

DECISION_STATUS = "exploratory_supported_after_documented_specification_correction"

CLOSURE_GATES = (
    "c11_original_record_preserved",
    "original_and_corrected_gate_sets_kept_separate",
    "correction_not_presented_as_preregistered",
    "outcome_access_incident_recorded_accurately",
    "architecture_reproduced_without_d_series_access",
    "architecture_decision_dependency_clean",
    "decision_status_is_exploratory_not_confirmatory",
    "architecture_scope_preserved",
    "no_model_prediction_target_or_metric_artifact_created",
)

#: Every one must be present and must carry the stated value. A missing field
#: is a softened record, which is the failure mode this task exists to prevent.
REQUIRED_GATE_STATUS_FIELDS = {
    "original_preregistered_stacked_rank_expectation": 5,
    "observed_stacked_rank_under_prohibited_preprocessing": 10,
    "original_gate_implementation_valid": False,
    "original_preregistered_gate_set_passed": False,
    "gate_implementation_corrected_after_observation": True,
    "corrected_gate_set_passed": True,
    "thresholds_changed_after_observation": False,
    "expectations_rewritten_as_preregistered": False,
    "architecture_decision_cleanly_preregistered": False,
}

REQUIRED_INCIDENT_STATUS_FIELDS = {
    "development_metric_artifact_accessed": True,
    "development_target_values_accessed": False,
    "locked_test_accessed": False,
    "metric_values_used_in_architecture_decision": False,
    "metric_artifact_required_for_decision": False,
    "outcome_free_execution": False,
    "decision_reproducible_without_metric_artifact": True,
    "later_guard_retroactively_erases_access": False,
    "clean_rerun_restores_original_outcome_blindness": False,
}

#: The measurements that actually establish the collapse. Reporting the stacked
#: rank alone hides it; reporting the per-industry rank alone understates it.
REQUIRED_CORRECT_MEASUREMENTS = (
    "within_industry_combined_rank",
    "intended_combined_rank",
    "interaction_blocks_intended",
    "interaction_blocks_after_prohibited_preprocessing",
    "sign_equivalence_groups",
    "sign_identity_residual_approx",
    "selected_preprocessing_retains_interaction_rank",
    "prohibited_preprocessing_destroys_continuous_exposure_magnitude",
)

D5_AUTHORIZATION_FIELDS = {
    "d5_protocol_preregistration_authorized": True,
    "d5_development_target_join_authorized": True,
    "d5_exploratory_modeling_authorized": True,
    "d5_channel_selection_authorized": False,
    "d5_confirmatory_claims_authorized": False,
    "d5_purge_evaluation_authorized": False,
    "d5_locked_test_evaluation_authorized": False,
}


class GovernanceError(ValueError):
    """A governance record was asked to say something it may not say."""


class PreservationError(GovernanceError):
    """The preserved original record changed."""


class AuthorizationError(GovernanceError):
    """An authorization was granted that closure does not support."""


# ---------------------------------------------------------------------------
# The frozen corrected-gate specification
# ---------------------------------------------------------------------------
@dataclass
class CorrectedGateSpecification:
    """The original gate, the observation, and the corrected gate — separately."""

    correction_version: str
    gate: str = ""
    original_preregistered_expectation: str = ""
    original_preregistered_stacked_rank_expectation: int = 5
    original_gate_condition: str = ""
    original_gate_implementation_valid: bool = False
    original_preregistered_gate_set_passed: bool = False
    observed_stacked_rank_under_prohibited_preprocessing: int = 10
    centered_exposures_contain_both_signs: bool = True
    correct_measurements: dict = field(default_factory=dict)
    corrected_gate_condition: str = ""
    corrected_gate_set_passed: bool = True
    gate_implementation_corrected_after_observation: bool = True
    thresholds_changed_after_observation: bool = False
    numerical_tolerance_changed: bool = False
    expectations_rewritten_as_preregistered: bool = False
    architecture_decision_cleanly_preregistered: bool = False
    incorrect_question: str = ""
    correct_question: str = ""
    conclusion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def correction_checksum(specification) -> str:
    """Digest of the frozen corrected-gate specification."""
    payload = (specification.to_dict() if hasattr(specification, "to_dict")
               else dict(specification))
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_correction_frozen(specification, expected_checksum: str) -> str:
    """Raise unless the corrected-gate specification still hashes to its digest."""
    actual = correction_checksum(specification)
    if actual != expected_checksum:
        raise GovernanceError(
            f"the corrected-gate specification now hashes to {actual}, not the "
            f"frozen {expected_checksum}. The record of what was originally "
            "preregistered and what was corrected afterwards may not move"
        )
    return actual


# ---------------------------------------------------------------------------
# Guards on how the correction may be described
# ---------------------------------------------------------------------------
def assert_original_gate_set_not_reported_as_passing(status: dict) -> None:
    """Raise if the original nine gates are reported as having passed.

    They did not. The gate that was later corrected did not pass as originally
    implemented, and saying otherwise turns a corrected specification into a
    clean one.
    """
    if status.get("original_preregistered_gate_set_passed"):
        raise GovernanceError(
            "the ORIGINAL preregistered gate set is reported as passing. The "
            "gate `pooled_interaction_survives_the_specified_preprocessing` did "
            "not pass as originally implemented: it required a stacked rank drop "
            "from 10 to 5 that does not occur"
        )
    if status.get("original_gate_implementation_valid"):
        raise GovernanceError(
            "the original gate implementation is reported as valid. It "
            "conditioned a gate about the SPECIFIED preprocessing on a "
            "counterfactual the preprocessing contract forbids"
        )
    if status.get("original_nine_gates_passed_without_qualification"):
        raise GovernanceError(
            "the original nine gates are described as passing without "
            "qualification"
        )


def assert_correction_not_presented_as_preregistered(status: dict) -> None:
    """Raise if the post-observation correction is dressed as preregistration."""
    if not status.get("gate_implementation_corrected_after_observation"):
        raise GovernanceError(
            "the gate correction is not recorded as having been made after "
            "observation. It was, and reproducibility does not convert a "
            "post-observation correction into preregistration"
        )
    if status.get("expectations_rewritten_as_preregistered"):
        raise GovernanceError(
            "a post-observation expectation is recorded as preregistered"
        )
    if status.get("architecture_decision_cleanly_preregistered"):
        raise GovernanceError(
            "the architecture decision is described as cleanly preregistered. "
            "One of its nine gates was corrected after the result was visible"
        )


def assert_not_described_as_a_tolerance_change(text) -> None:
    """Raise on wording that recasts a specification fix as a threshold move.

    No tolerance moved. The rank tolerance, the duplicate-column tolerance and
    every residual tolerance are exactly as preregistered; what changed is which
    *quantity* the gate measured.
    """
    lowered = str(text).lower()
    banned = (
        "loosened the tolerance", "relaxed the tolerance", "changed the tolerance",
        "adjusted the tolerance", "tolerance was changed", "tolerance was relaxed",
        "tolerance was loosened", "tolerance was widened", "raised the threshold",
        "lowered the threshold", "changed the threshold", "adjusted the threshold",
        "relaxed the threshold", "widened the tolerance", "threshold was relaxed",
        "threshold was changed", "threshold was raised", "threshold was lowered",
        "threshold was adjusted",
    )
    for phrase in banned:
        if phrase in lowered:
            raise GovernanceError(
                f"{phrase!r} describes the correction as a numerical change. No "
                "tolerance or threshold moved: the gate was measuring the wrong "
                "quantity, and the quantity was corrected"
            )


def assert_correct_measurements_present(measurements: dict) -> None:
    """Raise if the within-industry or sign-group collapse is omitted."""
    missing = [f for f in REQUIRED_CORRECT_MEASUREMENTS if f not in measurements]
    if missing:
        raise GovernanceError(
            f"the corrected measurement is incomplete: {sorted(missing)} absent. "
            "The stacked rank alone hides the collapse and the per-industry rank "
            "alone understates it; both, plus the sign-group count, are required"
        )
    if measurements["within_industry_combined_rank"] >= (
            measurements["intended_combined_rank"]):
        raise GovernanceError(
            "the within-industry combined rank does not fall below the intended "
            "combined rank, so no collapse is being reported"
        )
    if measurements["interaction_blocks_after_prohibited_preprocessing"] >= (
            measurements["interaction_blocks_intended"]):
        raise GovernanceError(
            "the interaction-block count does not collapse, so the loss of "
            "continuous exposure magnitude is not being reported"
        )
    if not measurements["prohibited_preprocessing_destroys_continuous_exposure_magnitude"]:
        raise GovernanceError(
            "the prohibited preprocessing is recorded as preserving exposure "
            "magnitude; within an industry only the sign survives"
        )


# ---------------------------------------------------------------------------
# Guards on the incident record
# ---------------------------------------------------------------------------
def assert_incident_recorded(status: dict) -> None:
    """Raise unless the outcome-access incident is recorded as it happened."""
    missing = [f for f in REQUIRED_INCIDENT_STATUS_FIELDS if f not in status]
    if missing:
        raise GovernanceError(
            f"the outcome-access incident record is missing {sorted(missing)}"
        )
    for name, expected in REQUIRED_INCIDENT_STATUS_FIELDS.items():
        if bool(status[name]) != expected:
            raise GovernanceError(
                f"{name} is recorded as {status[name]!r}, not {expected!r}. The "
                "incident is recorded as it happened, in both directions"
            )


def assert_guard_does_not_erase_history(status: dict) -> None:
    """Raise on any claim that a later guard undid the original access."""
    if status.get("later_guard_retroactively_erases_access"):
        raise GovernanceError(
            "a guard added after the fact is claimed to erase the original "
            "access. It prevents recurrence; it does not change what happened"
        )
    if status.get("clean_rerun_restores_original_outcome_blindness"):
        raise GovernanceError(
            "a clean rerun is claimed to restore historical outcome blindness. A "
            "rerun demonstrates the decision is reproducible without the metric "
            "artifact; the original execution history is unchanged by it"
        )
    if status.get("outcome_free_execution"):
        raise GovernanceError(
            "the C11 execution is recorded as outcome-free. A development metric "
            "artifact was opened during it"
        )


def assert_no_umbrella_outcome_free_claim(payload) -> None:
    """Raise if an umbrella ``outcome_free: true`` appears anywhere.

    ``outcome_free`` conflates the dependency question with the history
    question. C11-R1 answers them separately and never with one flag.
    """
    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "outcome_free" and value is True:
                    raise GovernanceError(
                        f"an umbrella `outcome_free: true` appears at {path}. A "
                        "dependency-clean decision and an outcome-blind "
                        "execution history are different facts and are recorded "
                        "as separate fields"
                    )
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload)


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------
def assert_c11_record_preserved(pinned: dict, observed: dict) -> dict:
    """Raise if C11's durable identity changed.

    Two kinds of pin. A **content checksum** excludes generation timestamps and
    is the durable identity: a change there means the record itself changed. A
    **byte digest** is a forward integrity baseline only, because the Markdown
    and JSON carry a timestamp and a legitimate rerun moves them. A byte drift
    is reported as a regeneration, not asserted as an overwrite.
    """
    changed = [
        name for name, value in pinned["durable_checksums"].items()
        if observed["durable_checksums"].get(name) != value
    ]
    if changed:
        raise PreservationError(
            f"C11's durable checksums changed: {sorted(changed)}. C11-R1 is an "
            "overlay; it preserves the original record rather than rewriting it"
        )
    regenerated = sorted(
        name for name, entry in pinned["artifacts"].items()
        if observed["artifacts"].get(name, {}).get("byte_sha256") != entry["byte_sha256"]
    )
    for name in regenerated:
        if not pinned["artifacts"][name]["carries_generation_timestamp"]:
            raise PreservationError(
                f"{name} has no generation timestamp yet its bytes changed; that "
                "is an edit, not a regeneration"
            )
    return {
        "durable_checksums_unchanged": True,
        "byte_identical": not regenerated,
        "regenerated_with_a_new_timestamp": regenerated,
        "artifacts_edited": [],
    }


# ---------------------------------------------------------------------------
# Status and authorization
# ---------------------------------------------------------------------------
def assert_status_is_exploratory(status: dict) -> None:
    """Raise if the decision is upgraded to confirmatory, or written off."""
    if status.get("architecture_decision_status") != DECISION_STATUS:
        raise GovernanceError(
            f"the decision status is {status.get('architecture_decision_status')!r}, "
            f"not {DECISION_STATUS!r}"
        )
    for name in ("architecture_confirmatorily_selected", "eligible_for_confirmatory_claims",
                 "eligible_for_locked_test", "original_process_outcome_blind"):
        if status.get(name):
            raise GovernanceError(
                f"{name} is true. The correction is mathematically convincing and "
                "that does not make the selection confirmatory, nor does it make "
                "the original execution outcome-blind"
            )
    if not status.get("architecture_mathematically_supported"):
        raise GovernanceError(
            "the architecture is recorded as unsupported. The process was "
            "imperfect; the mathematics reproduces exactly, and an imperfect "
            "process does not invalidate a reproduced identity"
        )


def evaluate_closure_gates(preservation: dict, gate_status: dict, incident: dict,
                           reproduction: dict, dependency: dict, status: dict,
                           scope: dict, outputs: dict) -> dict:
    """Evaluate the nine closure gates from measured quantities only."""
    gates = {
        "c11_original_record_preserved": bool(
            preservation.get("durable_checksums_unchanged")
            and not preservation.get("artifacts_edited")
        ),
        "original_and_corrected_gate_sets_kept_separate": bool(
            gate_status.get("original_preregistered_gate_set_passed") is False
            and gate_status.get("corrected_gate_set_passed") is True
            and gate_status.get("original_gate_implementation_valid") is False
        ),
        "correction_not_presented_as_preregistered": bool(
            gate_status.get("gate_implementation_corrected_after_observation")
            and not gate_status.get("expectations_rewritten_as_preregistered")
            and not gate_status.get("architecture_decision_cleanly_preregistered")
        ),
        "outcome_access_incident_recorded_accurately": bool(
            incident.get("development_metric_artifact_accessed")
            and incident.get("outcome_free_execution") is False
            and incident.get("metric_values_used_in_architecture_decision") is False
            and incident.get("later_guard_retroactively_erases_access") is False
        ),
        "architecture_reproduced_without_d_series_access": bool(
            reproduction.get("all_reproduced")
            and reproduction.get("d_series_paths_opened") == 0
            and reproduction.get("architecture")
            == reproduction.get("expected_architecture")
        ),
        "architecture_decision_dependency_clean": bool(
            dependency.get("architecture_decision_dependency_clean")
        ),
        "decision_status_is_exploratory_not_confirmatory": bool(
            status.get("architecture_decision_status") == DECISION_STATUS
            and not status.get("architecture_confirmatorily_selected")
            and not status.get("eligible_for_confirmatory_claims")
        ),
        "architecture_scope_preserved": bool(
            scope.get("per_industry_interaction_standardization") is False
            and scope.get("industry_fixed_effects_without_redundant_global_intercept")
            and scope.get("ind_04_benchmark_passthrough")
            and scope.get("fo600_and_fo1500_separate_variants")
            and scope.get("simultaneous_channel_entry") is False
            and scope.get("outcome_based_channel_promotion") is False
        ),
        "no_model_prediction_target_or_metric_artifact_created": not any((
            outputs.get("model_artifact_created"),
            outputs.get("prediction_artifact_created"),
            outputs.get("metric_artifact_created"),
            outputs.get("target_joined_artifact_created"),
        )),
    }
    unknown = sorted(set(gates) ^ set(CLOSURE_GATES))
    if unknown:
        raise GovernanceError(f"closure gates do not match the frozen list: {unknown}")
    return gates


def authorize_d5(closure_gates: dict) -> dict:
    """Issue the bounded D5 authorization, or none at all.

    Every field is false unless every closure gate passes. There is no partial
    authorization: a failed dependency reconstruction voids the whole grant.
    """
    failed = sorted(name for name, passed in closure_gates.items() if not passed)
    if failed:
        return {
            **dict.fromkeys(D5_AUTHORIZATION_FIELDS, False),
            "all_closure_gates_passed": False,
            "failed_closure_gates": failed,
            "blocker": failed[0],
            "reason": (
                f"{len(failed)} closure gate(s) failed: {failed}. No D5 "
                "authorization is issued; a failed dependency-clean "
                "reconstruction voids the grant entirely."
            ),
        }
    return {
        **D5_AUTHORIZATION_FIELDS,
        "all_closure_gates_passed": True,
        "failed_closure_gates": [],
        "blocker": None,
        "reason": (
            "All nine closure gates passed. D5 is authorized as a "
            "development-only exploratory evaluation of the Candidate-C pooled "
            "architecture, with both fuel-oil variants kept as separate parallel "
            "variants. Channel selection, purge metrics, confirmatory claims and "
            "the locked test remain unauthorized."
        ),
    }


def assert_d5_authorization_bounded(authorization: dict) -> None:
    """Raise if D5 received a permission this closure does not grant."""
    for name in ("d5_channel_selection_authorized", "d5_confirmatory_claims_authorized",
                 "d5_purge_evaluation_authorized",
                 "d5_locked_test_evaluation_authorized"):
        if authorization.get(name):
            raise AuthorizationError(
                f"{name} is true. D5 is authorized as a development-only "
                "exploratory evaluation; channel selection, purge metrics, "
                "confirmatory claims and the locked test are outside the grant"
            )
    if not authorization.get("all_closure_gates_passed"):
        granted = sorted(
            name for name in D5_AUTHORIZATION_FIELDS if authorization.get(name)
        )
        if granted:
            raise AuthorizationError(
                f"{granted} granted despite a failed closure gate "
                f"({authorization.get('blocker')})"
            )


# ---------------------------------------------------------------------------
def governance_checksum(preservation: dict, correction_digest: str,
                        incident: dict, dependency_digest: str,
                        closure_gates: dict, authorization: dict) -> str:
    """Digest of the governance decision: what was corrected, disclosed, granted."""
    payload = {
        "version": GOVERNANCE_VERSION,
        "correction_checksum": correction_digest,
        "dependency_checksum": dependency_digest,
        "durable_checksums_unchanged": preservation.get("durable_checksums_unchanged"),
        "incident": {k: incident[k] for k in sorted(REQUIRED_INCIDENT_STATUS_FIELDS)},
        "closure_gates": {k: bool(v) for k, v in sorted(closure_gates.items())},
        "authorization": {
            k: authorization.get(k) for k in sorted(D5_AUTHORIZATION_FIELDS)
        },
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
