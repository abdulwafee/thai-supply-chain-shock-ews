"""Closure policy for the EPPO sector-093 fuel-oil modeling channel (Task C12).

D5 evaluated the C11 architecture on the registered development window and found
no incremental signal: no variant-horizon point estimate beat its benchmark,
every paired interval straddled zero, and event safety failed in all four cases.
The preregistered stop rule closes the channel to further modeling.

Three distinctions do the work here, and each of them is a place where a
reasonable-sounding sentence would say something false.

**Inconclusive is not absence.** Fifteen issue-month clusters cannot rule an
effect out, and nothing in D5 tried to. :func:`assert_no_absence_claim` raises on
"has no effect", "no predictive relationship exists", "null hypothesis proven"
and the rest, because closure is a decision about where to spend effort, not a
finding about the world.

**A failed model does not invalidate a source.** The EPPO documents, the C7.5
semantics, the C8 transformations and the sector-093 exposure are all still
correct and reproducible. :func:`assert_source_validity_preserved` raises if
closure is used to mark any of them erroneous.

**A new specification is not new evidence.** Another alpha, another estimator, a
nonlinear term, a favourable subgroup, dropping IND-04 from the denominator —
each is the same evidence re-described. :func:`assert_reopening_evidence` accepts
only external evidence that could not have been used by D5, and requires it to
say why.

The enforcement guard refuses **modeling** entry and permits everything else:
audit, reproduction, documentation and source-quality work all continue, and D5
itself must stay reproducible. A closed feature is refused with a stated reason,
never reported as missing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

__all__ = [
    "BLOCKED_PURPOSES",
    "CHANNEL_ID",
    "CLOSURE_CONCLUSION",
    "CLOSURE_STATUS",
    "CLOSURE_VERSION",
    "PERMITTED_PURPOSES",
    "PROHIBITED_CONCLUSIONS",
    "REOPENING_EVIDENCE_FIELDS",
    "REQUIRED_CLOSURE_FIELDS",
    "VARIANTS",
    "ChannelClosureError",
    "ClosedChannelError",
    "ClosureRecord",
    "ReopeningEvidenceError",
    "assert_artifacts_preserved",
    "assert_both_variants_closed",
    "assert_modeling_entry_permitted",
    "assert_no_absence_claim",
    "assert_no_channel_preference",
    "assert_prohibited_reopening_reason",
    "assert_reopening_evidence",
    "assert_source_validity_preserved",
    "closure_checksum",
    "content_checksum",
    "normalise_feature_id",
]

CLOSURE_VERSION = "c12_eppo_fuel_oil_channel_closure_v1"

CHANNEL_ID = "eppo_sector093_fuel_oil"
VARIANTS = ("fo600_direct_sector093", "fo1500_direct_sector093")

CLOSURE_STATUS = "closed_after_registered_development_evaluation"
CLOSURE_CONCLUSION = (
    "incremental_signal_not_demonstrated_in_registered_development_evaluation"
)

#: Each of these turns "we found nothing" into "there is nothing". D5 had
#: fifteen issue-month clusters; it could not have established any of them.
PROHIBITED_CONCLUSIONS = (
    "fuel_oil_has_no_effect",
    "fuel_oil_is_unrelated_to_industrial_stress",
    "null_hypothesis_proven",
    "structural_exposure_is_invalid",
    "eppo_data_is_invalid",
    "no_predictive_relationship_exists",
)

#: Prose forms of the same overreach, caught in rendered documents.
_ABSENCE_PHRASES = (
    "has no effect", "no effect on", "is unrelated to", "null hypothesis proven",
    "proves the null", "no predictive relationship", "there is no relationship",
    "disproved", "ruled out", "shown to be irrelevant", "proven absent",
    "absence of an effect was proven", "eppo data is invalid",
    "structural exposure is invalid",
)

REQUIRED_CLOSURE_FIELDS = {
    "channel_status": CLOSURE_STATUS,
    "development_evidence_status": "incremental_signal_not_demonstrated",
    "carried_forward_to_operational_modeling": False,
    "development_candidate_supported": False,
    "model_feature_approved": False,
    "confirmatory_claim_authorized": False,
    "purge_evaluation_authorized": False,
    "locked_test_evaluation_authorized": False,
    "locked_test_should_be_opened_for_this_channel": False,
    "additional_model_grid_authorized": False,
    "channel_selection_authorized": False,
    "source_pipeline_remains_valid": True,
    "structural_audit_remains_valid": True,
    "absence_of_effect_proven": False,
}

BLOCKED_PURPOSES = (
    "modeling", "model_training", "target_assembly", "feature_selection",
    "operational_modeling", "locked_test_evaluation",
)

PERMITTED_PURPOSES = (
    "audit", "reproduction", "documentation", "source_quality",
    "provenance_verification", "historical_d5_reproduction",
)

REOPENING_EVIDENCE_FIELDS = (
    "new_evidence_id",
    "source",
    "checksum",
    "availability_date",
    "why_unavailable_to_d5",
    "affected_assumption",
    "expected_artifact_impact",
    "not_selected_from_d5_outcomes",
    "superseding_decision_log_entry",
)

#: Fields whose presence in a reopening record means the "new evidence" is a
#: reading of D5's own result.
_D5_OUTCOME_FIELDS = (
    "d5_macro_mae", "d5_paired_ci", "d5_mae_evidence", "d5_event_safety",
    "observed_mae", "model_mae", "benchmark_mae", "paired_ci_low",
    "paired_ci_high", "false_negatives", "mae_skill", "d5_coefficient",
)


class ChannelClosureError(ValueError):
    """A closure record was asked to say something it may not say."""


class ClosedChannelError(ChannelClosureError):
    """A closed feature was requested for a purpose the closure blocks."""


class ReopeningEvidenceError(ChannelClosureError):
    """A reopening request was not supported by qualifying new evidence."""


# ---------------------------------------------------------------------------
# Language guards
# ---------------------------------------------------------------------------
def _strip_named_terms(text: str) -> str:
    """Remove backticked and quoted spans, which NAME a term rather than assert it.

    The closure has to be able to publish its own prohibition list. A guard that
    cannot tell ``fuel_oil_has_no_effect`` inside a list of forbidden phrases
    from the same words in a sentence would forbid documenting the rule.
    """
    import re

    without_code = re.sub(r"`[^`]*`", " ", str(text))
    return re.sub(r'"[^"]*"', " ", without_code)


def assert_no_absence_claim(text, strip_named_terms: bool = True) -> None:
    """Raise on wording that turns an inconclusive result into proof of absence.

    D5's intervals straddled zero on fifteen clusters. That is a failure to
    demonstrate, not a demonstration of failure, and the two are not
    interchangeable however the sentence is arranged.
    """
    lowered = (_strip_named_terms(text) if strip_named_terms else str(text)).lower()
    for phrase in PROHIBITED_CONCLUSIONS:
        if phrase.replace("_", " ") in lowered.replace("_", " "):
            raise ChannelClosureError(
                f"{phrase!r} claims proof of absence. D5 was inconclusive on "
                "fifteen issue-month clusters; closure is a decision about where "
                "to spend effort, not a finding about the world"
            )
    for phrase in _ABSENCE_PHRASES:
        if phrase in lowered:
            raise ChannelClosureError(
                f"{phrase!r} states that no effect exists. The registered "
                "development evaluation did not demonstrate incremental signal; "
                "it did not and could not rule an effect out"
            )


def assert_source_validity_preserved(validity: dict) -> None:
    """Raise if closure was used to mark a source or structure erroneous.

    Whether the EPPO documents are valid evidence and whether the channel may
    enter modeling are different questions. A failed model answers only the
    second.
    """
    must_hold = (
        "official_eppo_source_documents_still_valid_evidence",
        "c7_c7_5_semantic_decisions_retained",
        "c8_transformations_reproducible",
        "sector_093_exposure_reproducible",
        "interaction_architecture_mathematically_identifiable",
    )
    for field_name in must_hold:
        if not validity.get(field_name):
            raise ChannelClosureError(
                f"{field_name} is false. Closure applies to MODELING USE; the "
                "source pipeline and the structural audit remain valid within "
                "their stated limitations"
            )
    must_not_hold = (
        "source_rows_marked_erroneous_because_the_model_failed",
        "transformations_marked_erroneous_because_the_model_failed",
        "exposures_marked_erroneous_because_the_model_failed",
    )
    for field_name in must_not_hold:
        if validity.get(field_name):
            raise ChannelClosureError(
                f"{field_name} is true. A model that failed to beat a benchmark "
                "says nothing about whether its inputs were measured correctly"
            )
    if validity.get("predictive_utility_demonstrated_on_development_data"):
        raise ChannelClosureError(
            "predictive utility is recorded as demonstrated. D5 found no "
            "variant-horizon where the model beat its benchmark"
        )
    for field_name in ("may_enter_further_operational_modeling",
                      "may_open_the_locked_test_for_this_channel"):
        if validity.get(field_name):
            raise ChannelClosureError(f"{field_name} is true under a closed channel")


def assert_no_channel_preference(closure: dict) -> None:
    """Raise if one variant is singled out as better, primary or less bad."""
    for field_name in ("primary_channel", "preferred_channel", "selected_variant",
                       "less_bad_channel", "best_variant"):
        if closure.get(field_name):
            raise ChannelClosureError(
                f"{field_name} names a fuel-oil variant. Both are closed on the "
                "same evidence and neither is preferred, primary or less bad"
            )
    if closure.get("channel_selection_authorized"):
        raise ChannelClosureError(
            "channel selection is authorized under a closed channel"
        )
    if closure.get("either_variant_labelled_preferred_primary_or_less_bad"):
        raise ChannelClosureError("a variant was labelled preferred or primary")


def assert_both_variants_closed(closure: dict, variants=VARIANTS) -> None:
    """Raise unless the identical closure applies to both variants."""
    applied = sorted(closure.get("variants") or [])
    if applied != sorted(variants):
        raise ChannelClosureError(
            f"closure names variants {applied}, expected {sorted(variants)}. Both "
            "are closed on the same evidence"
        )
    if not closure.get("applied_identically_to_both_variants"):
        raise ChannelClosureError(
            "the closure is not recorded as applying identically to both variants"
        )


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------
def assert_artifacts_preserved(pinned: dict, observed: dict) -> dict:
    """Raise if any C7-D5 artifact was deleted or changed.

    Content checksums are the durable identity; byte digests are a forward
    integrity baseline for the generated tables. Either one moving means the
    historical record moved, and a closure that rewrote its own evidence would
    be worthless.
    """
    missing = sorted(set(pinned) - set(observed))
    if missing:
        raise ChannelClosureError(
            f"preserved artifacts are absent: {missing}. Closure preserves the "
            "evidence chain; it does not delete it"
        )
    changed = sorted(name for name, value in pinned.items()
                     if observed.get(name) != value)
    if changed:
        raise ChannelClosureError(
            f"preserved artifacts changed: {changed}. C7 through D5 are read-only "
            "here, and a closure that rewrote its own evidence would prove nothing"
        )
    return {
        "artifacts_pinned": len(pinned),
        "artifacts_deleted": 0,
        "artifacts_modified": 0,
        "all_unchanged": True,
    }


# ---------------------------------------------------------------------------
# Reopening
# ---------------------------------------------------------------------------
def assert_prohibited_reasons_recorded(reasons) -> None:
    """Raise if the prohibited-reason list lost the ones that matter most."""
    required = {
        "trying_another_alpha", "expanding_an_alpha_grid",
        "replacing_ridge_with_another_estimator",
        "selecting_fo600_or_fo1500_from_observed_mae",
        "combining_the_two_channels", "removing_ind_04_from_denominators",
        "switching_direct_exposure_to_total_requirement_because_d5_failed",
        "opening_purge_or_locked_origins",
    }
    missing = sorted(required - set(reasons))
    if missing:
        raise ChannelClosureError(
            f"the prohibited-reopening list is missing {missing}"
        )


def assert_prohibited_reopening_reason(reason: str, prohibited) -> None:
    """Raise if a reopening rests on a respecification of the same evidence."""
    if str(reason) in set(prohibited):
        raise ReopeningEvidenceError(
            f"{reason!r} is a prohibited reopening reason. It re-describes the "
            "evidence D5 already produced; a new specification alone is not new "
            "evidence"
        )


def assert_reopening_evidence(record: dict, prohibited=()) -> dict:
    """Raise unless a reopening request carries qualifying external evidence.

    Provenance, an availability date, and an explicit account of why D5 could
    not have used it. Evidence chosen *because* D5 failed is D5's result wearing
    a different label, so a record that carries a D5 outcome field is refused.
    """
    missing = [f for f in REOPENING_EVIDENCE_FIELDS if f not in record]
    if missing:
        raise ReopeningEvidenceError(
            f"the reopening request is missing {sorted(missing)}. Without "
            "provenance, an availability date and a superseding decision, this is "
            "an intention rather than evidence"
        )
    empty = [
        f for f in REOPENING_EVIDENCE_FIELDS
        if f != "not_selected_from_d5_outcomes" and not record[f]
    ]
    if empty:
        raise ReopeningEvidenceError(
            f"the reopening request has empty {sorted(empty)}"
        )
    if not record["not_selected_from_d5_outcomes"]:
        raise ReopeningEvidenceError(
            "the reopening evidence is recorded as selected from D5 outcomes. "
            "Evidence chosen because a model failed is that model's result under "
            "another name"
        )
    leaked = sorted(f for f in _D5_OUTCOME_FIELDS if f in record)
    if leaked:
        raise ReopeningEvidenceError(
            f"the reopening record carries D5 outcome field(s) {leaked}. New "
            "evidence must be external to D5's performance"
        )
    if str(record.get("reason", "")) and prohibited:
        assert_prohibited_reopening_reason(record["reason"], prohibited)
    return {
        "new_evidence_id": record["new_evidence_id"],
        "qualifies": True,
        "superseding_decision_log_entry": record["superseding_decision_log_entry"],
    }


# ---------------------------------------------------------------------------
# The enforcement guard
# ---------------------------------------------------------------------------
def normalise_feature_id(feature_id: str) -> str:
    """Lowercase and strip separators, so an alias cannot walk past by spelling."""
    return "".join(ch for ch in str(feature_id).lower() if ch.isalnum())


def assert_modeling_entry_permitted(feature_ids, purpose: str, policy: dict,
                                    superseding_decision: dict = None) -> dict:
    """The guard on every future modeling or target-assembly entry point.

    Refuses the closed features for a modeling purpose, and refuses **nothing**
    otherwise: audit, reproduction, documentation, source-quality work and the
    historical D5 reproduction all pass through untouched. A refused feature is
    reported with its closure reason, never as missing — "not found" would send
    the next person looking for a bug that does not exist.
    """
    purpose = str(purpose)
    if purpose in set(policy.get("permitted_purposes", PERMITTED_PURPOSES)):
        return {
            "permitted": True, "purpose": purpose,
            "reason": "permitted_purpose_closure_applies_to_modeling_only",
            "blocked_feature_ids": [],
        }
    if purpose not in set(policy.get("blocked_purposes", BLOCKED_PURPOSES)):
        raise ClosedChannelError(
            f"unknown purpose {purpose!r}; the closure policy enumerates both "
            "permitted and blocked purposes so an unlisted one cannot default to "
            "allowed"
        )

    closed = set()
    for group in ("closed_feature_ids", "closed_aliases", "closed_composite_forms",
                  "closed_upstream_feature_tables"):
        closed |= {normalise_feature_id(f) for f in policy.get(group, ())}
    requested = {normalise_feature_id(f): f for f in feature_ids}
    blocked = sorted(
        original for key, original in requested.items()
        if key in closed or any(key.startswith(c) or c in key for c in closed)
    )
    if not blocked:
        return {
            "permitted": True, "purpose": purpose, "reason": "no_closed_feature",
            "blocked_feature_ids": [],
        }

    if superseding_decision:
        assert_reopening_evidence(
            superseding_decision,
            policy.get("prohibited_reopening_reasons", ()),
        )
        if not superseding_decision.get("active"):
            raise ReopeningEvidenceError(
                "the superseding decision is not active; a drafted reopening does "
                "not open the channel"
            )
        return {
            "permitted": True, "purpose": purpose,
            "reason": "superseded_by_qualifying_new_evidence",
            "new_evidence_id": superseding_decision["new_evidence_id"],
            "blocked_feature_ids": [],
        }

    raise ClosedChannelError(
        f"{blocked} belong to the {CHANNEL_ID} channel, which is "
        f"{CLOSURE_STATUS} ({CLOSURE_CONCLUSION}). They are present and "
        "reproducible, and they are refused for the purpose "
        f"{purpose!r} — not missing. Audit, reproduction, documentation and "
        "source-quality work remain permitted. Reopening requires a new decision "
        "supported by genuinely new external evidence."
    )


# ---------------------------------------------------------------------------
@dataclass
class ClosureRecord:
    """The closure decision itself."""

    closure_version: str = CLOSURE_VERSION
    channel_id: str = CHANNEL_ID
    variants: tuple = VARIANTS
    conclusion: str = CLOSURE_CONCLUSION
    fields: dict = field(default_factory=dict)
    terminal_evidence_checksums: dict = field(default_factory=dict)
    preserved_artifacts: dict = field(default_factory=dict)
    metrics_recomputed: bool = False
    d5_rerun: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def assert_closure_fields(fields: dict) -> None:
    """Raise unless every closure field carries its required value."""
    missing = [f for f in REQUIRED_CLOSURE_FIELDS if f not in fields]
    if missing:
        raise ChannelClosureError(f"the closure is missing {sorted(missing)}")
    for name, expected in REQUIRED_CLOSURE_FIELDS.items():
        if fields[name] != expected:
            raise ChannelClosureError(
                f"{name} is {fields[name]!r}, expected {expected!r}"
            )


def closure_checksum(record) -> str:
    """Digest of the closure decision, its evidence pins and its guards."""
    payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
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
