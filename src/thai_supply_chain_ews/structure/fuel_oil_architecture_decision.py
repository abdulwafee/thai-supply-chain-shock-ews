"""The C11 architecture decision: criteria, gates, guards and lineage.

C11 chooses how a fuel-oil correction would enter a model *if one were later
authorized*. It chooses on the estimand and the identification structure alone,
and it fits nothing.

**The criteria are frozen before the first candidate matrix exists.** The
estimand, the candidate set, the nine mandatory gates, the preprocessing
contract, the rank requirements and the decision ordering are hashed first;
:func:`assert_criteria_frozen` re-asserts the digest before the designs are
built and again after the identification audit. A gate rewritten once the ranks
are visible is not a gate.

**A failed gate is never traded for the expected answer.** The config records
``expected_selection: pooled_common_effect_plus_centered_sector093_interaction``
and, immediately beside it, ``expectation_overrides_a_failed_gate: false``.
:func:`select_architecture` returns ``None`` and names the blocker when any gate
fails, and there is no tie to break: Candidate B is rejected on an algebraic
identity rather than a comparison, and Candidate A is retained as a documented
alternative rather than ranked.

**Selecting an architecture grants no permission to run it.**
:func:`assert_authorization_not_granted` raises if the decision payload sets
target-join, modeling or locked-test authorization, so a selection cannot become
an execution by omission.

C10's fingerprint discrepancy is carried forward rather than tidied away: the
rounded significant-digit count and the absolute-tolerance equivalence-class
count are both reported, and :func:`assert_tolerance_rule_governs` raises if the
rounded count is used as the equivalence rule or if the discrepancy is dropped.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "ARCHITECTURE_DECISION_VERSION",
    "MANDATORY_GATES",
    "PROHIBITED_ARTIFACT_FRAGMENTS",
    "PROHIBITED_STATISTICS",
    "SELECTED_ARCHITECTURE_ID",
    "ArchitectureDecisionError",
    "AuthorizationError",
    "CriteriaError",
    "DecisionCriteria",
    "architecture_lineage_checksum",
    "architecture_lineage_record",
    "assert_authorization_not_granted",
    "assert_criteria_frozen",
    "assert_ind_04_not_converted",
    "assert_no_channel_preference",
    "assert_no_outcome_statistic",
    "assert_no_prohibited_artifact",
    "assert_predictive_not_causal",
    "assert_separate_conditioned_not_distinct",
    "assert_tolerance_rule_governs",
    "content_checksum",
    "criteria_checksum",
    "decision_checksum",
    "evaluate_gates",
    "select_architecture",
]

ARCHITECTURE_DECISION_VERSION = "c11_fuel_oil_architecture_decision_v1"

SELECTED_ARCHITECTURE_ID = "pooled_common_effect_plus_centered_sector093_interaction"

#: All nine must pass. There is no partial selection and no weighted score: a
#: gate is a structural precondition, not a criterion to trade off.
MANDATORY_GATES = (
    "matches_the_exposure_heterogeneity_estimand",
    "exposure_varies_across_eligible_industries",
    "pooled_interaction_survives_the_specified_preprocessing",
    "combined_feature_only_design_is_identifiable",
    "ind_04_excluded_without_conversion_to_zero",
    "source_channels_remain_separate",
    "no_outcome_or_model_result_used",
    "interpretation_remains_predictive_and_non_causal",
    "availability_and_lineage_intact",
)

#: Checked as substrings of a path, so a flag, an alternate directory or an
#: environment variable cannot route around the prohibition.
PROHIBITED_ARTIFACT_FRAGMENTS = (
    "target", "production_stress", "industry_month_panel", "prediction",
    "residual", "walk_forward", "locked", "holdout", "metrics",
    "_mae", "_rmse", "d1_development_results", "d3_operational",
    "d4_operational", "evaluation_prediction",
)

PROHIBITED_STATISTICS = (
    "mae", "rmse", "predictive_performance", "high_stress_outcome_rate",
    "correlation_with_a_target", "coefficient_estimate", "p_value",
    "confidence_interval", "effective_sample_size",
)


class ArchitectureDecisionError(ValueError):
    """A decision was asked to rest on something it may not rest on."""


class CriteriaError(ArchitectureDecisionError):
    """The decision criteria changed after the candidate matrices were built."""


class AuthorizationError(ArchitectureDecisionError):
    """A selection tried to become an execution permit."""


# ---------------------------------------------------------------------------
# The frozen criteria
# ---------------------------------------------------------------------------
@dataclass
class DecisionCriteria:
    """Everything fixed before a single candidate design matrix is built."""

    criteria_version: str
    estimand_statement: str = ""
    estimand_kind: str = "predictive_interaction"
    estimand_requires_exposure_heterogeneity: bool = True
    causal_effect_claimed: bool = False
    estimated_elasticity_claimed: bool = False
    monetary_cost_claimed: bool = False
    candidate_ids: list = field(default_factory=list)
    mandatory_gates: list = field(default_factory=list)
    all_gates_must_pass: bool = True
    decision_ordering: list = field(default_factory=list)
    tie_handling: str = ""
    expected_selection: str = ""
    expectation_overrides_a_failed_gate: bool = False
    exposure_centering_rule: str = ""
    exposure_centering_universe: str = ""
    source_scaling_rule: str = ""
    source_scaling_ddof: int = 0
    permitted_training_issue_months: list = field(default_factory=list)
    interaction_per_industry_standardization: bool = False
    industry_fixed_effect_coding: str = ""
    redundant_global_intercept: bool = False
    rank_tolerance: float = 1e-10
    duplicate_column_tolerance: float = 1e-12
    expected_source_block_rank: int = 5
    expected_interaction_block_rank: int = 5
    expected_combined_source_and_interaction_rank: int = 10
    expected_full_design_rank: int = 21
    expected_panel_rows: int = 165
    expected_unique_issue_months: int = 15
    expected_eligible_industries: int = 11
    equivalence_rule: str = "absolute_tolerance_equivalence_class"
    rounded_fingerprint_count_used_for_the_decision: bool = False
    channel_selection_permitted: bool = False
    transformation_removal_permitted: bool = False
    target_or_outcome_access_permitted: bool = False
    prohibited_artifacts: list = field(default_factory=list)
    prohibited_statistics: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def criteria_checksum(criteria) -> str:
    """Digest of the frozen criteria, over their fields in declared order."""
    payload = criteria.to_dict() if hasattr(criteria, "to_dict") else dict(criteria)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_criteria_frozen(criteria, expected_checksum: str) -> str:
    """Raise unless the criteria still hash to their frozen digest."""
    actual = criteria_checksum(criteria)
    if actual != expected_checksum:
        raise CriteriaError(
            f"the decision criteria now hash to {actual}, not the frozen "
            f"{expected_checksum}. The estimand, the gates, the preprocessing "
            "contract and the rank requirements may not change after a "
            "candidate design matrix has been inspected"
        )
    return actual


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def assert_no_prohibited_artifact(paths) -> None:
    """Raise if any path touches a target, prediction, metric or locked file."""
    for path in paths:
        text = str(path).replace("\\", "/").lower()
        for fragment in PROHIBITED_ARTIFACT_FRAGMENTS:
            if fragment in text:
                raise ArchitectureDecisionError(
                    f"{path} is a prohibited artifact ({fragment}). C11 decides "
                    "an architecture from the estimand and the identification "
                    "structure, and reads no target, prediction, metric or "
                    "locked outcome"
                )


def assert_no_outcome_statistic(names) -> None:
    """Raise if a decision input is an outcome-derived statistic."""
    for name in names:
        lowered = str(name).lower()
        for statistic in PROHIBITED_STATISTICS:
            if statistic in lowered:
                raise ArchitectureDecisionError(
                    f"{name!r} is an outcome statistic ({statistic}). The "
                    "architecture is selected on identification structure; a "
                    "development error would make it an outcome-based choice"
                )


def assert_predictive_not_causal(text: str) -> None:
    """Raise on wording that turns the interaction into an effect or a price.

    ``theta`` is an association between a national ex-refinery signal and a
    forecast correction whose amplitude is indexed by a frozen I/O coefficient.
    It is not an elasticity, not a pass-through rate, not a causal effect, and
    not baht of cost — the coefficient is in purchasers' prices while EPPO
    measures the ex-refinery stage, so their product has no currency reading.
    """
    lowered = str(text).lower()
    banned = (
        "causal effect", "causes", "elasticity", "pass-through rate",
        "pass through rate", "monetary cost", "baht cost per unit",
        "cost per unit of output", "baht of cost", "determines industrial stress",
        "the effect of fuel oil on", "marginal effect of the price",
    )
    for phrase in banned:
        if phrase in lowered:
            raise ArchitectureDecisionError(
                f"{phrase!r} describes the interaction causally or as a currency. "
                "C11 defines a NON-CAUSAL predictive estimand: an incremental "
                "forecast correction whose amplitude is indexed by frozen "
                "sector-093 purchases"
            )


def assert_no_channel_preference(decision: dict) -> None:
    """Raise if the decision ranks or prefers one fuel-oil variant."""
    if decision.get("primary_channel_selected"):
        raise ArchitectureDecisionError(
            "C11 selected a primary fuel-oil channel. FO 600 and FO 1500 are "
            "co-equal separate variants sharing one sector-093 vector; no "
            "structural basis for a preference exists and an outcome-based one "
            "is prohibited"
        )
    if decision.get("structural_basis_for_channel_preference_available"):
        raise ArchitectureDecisionError(
            "no structural basis for preferring one fuel-oil variant exists; "
            "both are conditioned on the identical exposure vector"
        )
    if decision.get("simultaneous_channel_entry_permitted"):
        raise ArchitectureDecisionError(
            "the two variants may not enter one model simultaneously: they "
            "carry the same sector-093 coefficient, so a joint design would "
            "count it twice"
        )


def assert_ind_04_not_converted(handling: dict) -> None:
    """Raise if IND-04's unresolved direction is turned into a number."""
    if handling.get("converted_to_observed_zero"):
        raise ArchitectureDecisionError(
            "IND-04 was converted to an observed-zero exposure. Its direction is "
            "mixed_or_ambiguous — it contains sector 093 itself — so its "
            "correction is structurally unavailable, not measured at zero"
        )
    if handling.get("direction_forced_to_plus_one"):
        raise ArchitectureDecisionError(
            "IND-04's direction was forced to +1. A higher refinery-product "
            "price is simultaneously its revenue and its input cost"
        )
    if handling.get("used_to_estimate_the_cost_pressure_interaction"):
        raise ArchitectureDecisionError(
            "IND-04 was used to estimate the cost-pressure interaction despite "
            "an unresolved direction"
        )
    if not handling.get("retains_operational_benchmark_prediction"):
        raise ArchitectureDecisionError(
            "IND-04 must keep the operational benchmark prediction; excluding it "
            "from the fuel-oil correction is not excluding it from the forecast"
        )
    if handling.get("silently_dropped_from_evaluation_denominators"):
        raise ArchitectureDecisionError(
            "IND-04 was dropped from the evaluation denominators. An industry "
            "that cannot receive a correction still has to be counted"
        )


def assert_separate_conditioned_not_distinct(report: dict,
                                             claimed_distinct: bool) -> None:
    """Raise if Candidate B is presented as its own architecture.

    The equivalence report either shows the two column spaces coinciding or it
    does not; claiming distinctness while they coincide is a claim about
    coefficients dressed up as a claim about designs.
    """
    if report.get("column_spaces_coincide") and claimed_distinct:
        raise ArchitectureDecisionError(
            "Candidate B was presented as a distinct architecture, but its "
            f"column space matches Candidate A's to "
            f"{report.get('column_space_projector_max_gap')!r}. Within one "
            "industry E_g is a positive scalar, so the two designs differ only "
            "in coordinates and per-industry standardisation removes even that"
        )
    if claimed_distinct and report.get(
            "per_industry_standardization_removes_exposure"):
        raise ArchitectureDecisionError(
            "Candidate B was presented as distinct even though per-industry "
            "standardisation reproduces Candidate A exactly"
        )


def assert_tolerance_rule_governs(discrepancy: dict) -> None:
    """Raise if C10's rounding discrepancy is hidden or used as the rule.

    C10 found eleven rounded fingerprints and one absolute-tolerance
    equivalence class for FO 600. Both are carried forward: the tolerance rule
    decides, and the rounded count is reported unchanged beside it.
    """
    required = (
        "rounded_fingerprint_count_fo600",
        "absolute_tolerance_equivalence_classes_fo600",
        "max_standardized_design_residual_fo600",
    )
    missing = [field_name for field_name in required if field_name not in discrepancy]
    if missing:
        raise ArchitectureDecisionError(
            f"C10's fingerprint discrepancy is incomplete: {sorted(missing)} "
            "absent. The discrepancy is preserved, not tidied away"
        )
    if not discrepancy.get("preserved") or discrepancy.get("discrepancy_suppressed"):
        raise ArchitectureDecisionError(
            "C10's fingerprint discrepancy was suppressed. It is reported in "
            "full: eleven rounded fingerprints, one tolerance equivalence class"
        )
    if discrepancy.get("c10_rewritten"):
        raise ArchitectureDecisionError("C10 may not be rewritten by C11")
    if discrepancy.get("rounded_fingerprint_count_used_for_the_decision"):
        raise ArchitectureDecisionError(
            "the rounded significant-digit fingerprint count was used as the "
            "equivalence rule. A fingerprint resolves a standardised value near "
            "zero below double precision; the preregistered ABSOLUTE tolerance "
            "governs"
        )
    if discrepancy.get("equivalence_rule_used_for_the_decision") != (
            "absolute_tolerance_equivalence_class"):
        raise ArchitectureDecisionError(
            "the architecture decision must use the absolute-tolerance "
            "equivalence rule, not "
            f"{discrepancy.get('equivalence_rule_used_for_the_decision')!r}"
        )


def assert_authorization_not_granted(authorization: dict) -> None:
    """Raise if selecting an architecture also granted permission to run it."""
    forbidden = (
        "target_values_read", "target_joined", "model_fitted",
        "predictive_performance_computed", "locked_test_accessed",
        "model_feature_approved", "target_join_authorized",
        "development_modeling_authorized", "locked_test_evaluation_authorized",
        "primary_channel_selected", "architecture_selected_from_outcomes",
    )
    granted = [name for name in forbidden if authorization.get(name)]
    if granted:
        raise AuthorizationError(
            f"selecting an architecture set {sorted(granted)} to true. C11 "
            "decides a design and grants no permission to execute it; each of "
            "those is a separate decision that has not been taken"
        )


# ---------------------------------------------------------------------------
# Gates and selection
# ---------------------------------------------------------------------------
def evaluate_gates(criteria, ranks, exposure_spread, collapse, constant_exposure,
                   duplicates, ind_04, channels, availability, lineage,
                   estimand, outcome_inputs_used: bool) -> dict:
    """Evaluate the nine mandatory gates from measured quantities only."""
    identifiable = (
        ranks["source_block_rank"] == criteria.expected_source_block_rank
        and ranks["interaction_block_rank"] == criteria.expected_interaction_block_rank
        and ranks["combined_source_and_interaction_rank"] ==
        criteria.expected_combined_source_and_interaction_rank
        and ranks["full_design_rank"] == criteria.expected_full_design_rank
        and ranks["full_design_rank"] == ranks["full_design_columns"]
        and not duplicates
    )
    # Gate 3 is about THE SPECIFIED preprocessing: the interaction must be
    # present, non-degenerate and not collinear with the main effect under the
    # contract in configs/fuel_oil_modeling_architecture.yaml. The counterfactual
    # -- what per-industry standardisation WOULD destroy -- is a separate
    # reported verification, not a condition of this gate: conditioning a gate
    # on a construction the contract forbids would make the gate depend on
    # something that never happens.
    survives = (
        ranks["interaction_block_rank"] ==
        criteria.expected_interaction_block_rank
        and ranks["combined_source_and_interaction_rank"] ==
        ranks["source_block_rank"] + ranks["interaction_block_rank"]
        and not criteria.interaction_per_industry_standardization
        and constant_exposure["constant_exposure_interaction_rank"] == 0
    )
    gates = {
        "matches_the_exposure_heterogeneity_estimand": bool(
            estimand.get("requires_exposure_associated_heterogeneity")
            and estimand.get("kind") == "predictive_interaction"
        ),
        "exposure_varies_across_eligible_industries": exposure_spread > 0,
        "pooled_interaction_survives_the_specified_preprocessing": bool(survives),
        "combined_feature_only_design_is_identifiable": bool(identifiable),
        "ind_04_excluded_without_conversion_to_zero": bool(
            ind_04.get("excluded_from_fuel_oil_correction")
            and not ind_04.get("converted_to_observed_zero")
            and not ind_04.get("direction_forced_to_plus_one")
            and ind_04.get("retains_operational_benchmark_prediction")
        ),
        "source_channels_remain_separate": bool(
            channels.get("co_equal_separate_structural_variants")
            and not channels.get("primary_channel_selected")
            and not channels.get("simultaneous_channel_entry_permitted")
        ),
        "no_outcome_or_model_result_used": not outcome_inputs_used,
        "interpretation_remains_predictive_and_non_causal": bool(
            not estimand.get("causal_effect")
            and not estimand.get("estimated_elasticity")
            and not estimand.get("monetary_cost_per_unit_of_output")
        ),
        "availability_and_lineage_intact": bool(
            availability.get("intact") and lineage.get("intact")
        ),
    }
    unknown = sorted(set(gates) ^ set(MANDATORY_GATES))
    if unknown:
        raise ArchitectureDecisionError(
            f"the evaluated gates do not match the frozen list: {unknown}"
        )
    return gates


def select_architecture(gates: dict, criteria) -> dict:
    """Apply the frozen decision rule. A failed gate selects nothing."""
    failed = sorted(name for name, passed in gates.items() if not passed)
    if failed:
        return {
            "modeling_architecture_selected": None,
            "selected_architecture": None,
            "all_gates_passed": False,
            "failed_gates": failed,
            "blocker": failed[0],
            "expectation_overridden": False,
            "reason": (
                f"{len(failed)} mandatory gate(s) failed: {failed}. The frozen "
                "rule selects nothing and reports the blocker; the expected "
                "selection does not override a failed gate."
            ),
        }
    return {
        "modeling_architecture_selected": SELECTED_ARCHITECTURE_ID,
        "selected_architecture": SELECTED_ARCHITECTURE_ID,
        "all_gates_passed": True,
        "failed_gates": [],
        "blocker": None,
        "expectation_overridden": False,
        "reason": (
            "All nine mandatory gates passed. Candidate B is rejected as a "
            "coefficient reparameterisation of Candidate A rather than compared "
            "against it, and Candidate A is retained as a documented "
            "alternative that does not meet the exposure-heterogeneity estimand."
        ),
    }


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------
LINEAGE_FIELDS = (
    "c10_content_checksum",
    "c10_diagnostic_contract_checksum",
    "c9_phase_a_checksum",
    "c9_conditioned_lineage_version",
    "c8_transformation_formula_version",
    "c7_5_semantic_checksum",
    "sector_093_exposure_vector_checksum",
    "nesdc_workbook_sha256",
    "industry_crosswalk_version",
    "structural_available_month",
    "candidate_design_formula_version",
    "exposure_centering_rule",
    "source_scaling_rule",
    "industry_fixed_effect_coding",
    "channel_separation_policy",
)


def architecture_lineage_record(references: dict, criteria_checksum_value: str,
                                design_checksums: dict) -> dict:
    """The complete provenance of the architecture decision."""
    missing = [f for f in LINEAGE_FIELDS if f not in references]
    if missing:
        raise ArchitectureDecisionError(
            f"the decision lineage is missing {sorted(missing)}; a decision "
            "traced through part of its chain is not traced"
        )
    empty = [f for f in LINEAGE_FIELDS if not references[f]]
    if empty:
        raise ArchitectureDecisionError(
            f"the decision lineage has empty references {sorted(empty)}"
        )
    return {
        "lineage_version": ARCHITECTURE_DECISION_VERSION,
        "criteria_checksum": criteria_checksum_value,
        "candidate_design_checksums": dict(sorted(design_checksums.items())),
        "references": {f: references[f] for f in LINEAGE_FIELDS},
    }


def architecture_lineage_checksum(record: dict) -> str:
    """SHA-256 over the whole provenance chain and the candidate designs."""
    payload = [record["lineage_version"], record["criteria_checksum"]]
    payload += [
        f"{k}={v}" for k, v in sorted(record["candidate_design_checksums"].items())
    ]
    payload += [f"{f}={record['references'][f]}" for f in LINEAGE_FIELDS]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decision_checksum(selection: dict, gates: dict, lineage_digest: str) -> str:
    """Digest of the decision itself: what was selected, why, and from what."""
    payload = {
        "version": ARCHITECTURE_DECISION_VERSION,
        "selected_architecture": selection.get("selected_architecture"),
        "all_gates_passed": selection.get("all_gates_passed"),
        "failed_gates": sorted(selection.get("failed_gates") or []),
        "gates": {k: bool(v) for k, v in sorted(gates.items())},
        "lineage_checksum": lineage_digest,
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
