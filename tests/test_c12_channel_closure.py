"""Task C12 tests — EPPO fuel-oil modeling-channel closure.

Three failures here would produce a closure record that reads as reasonable and
says something false.

**Turning "we found nothing" into "there is nothing".** D5 had fifteen
issue-month clusters and intervals that straddled zero. That is a failure to
demonstrate, not a demonstration of failure, and no rearrangement of the
sentence changes which one happened. The language guard refuses the overreach in
both its field form and its prose form — while still letting the closure publish
its own prohibition list, because a guard that cannot tell a named term from an
asserted one would forbid documenting the rule.

**Letting a failed model condemn its inputs.** Whether the EPPO documents are
valid evidence and whether the channel may enter modeling are different
questions, and a model that did not beat a benchmark answers only the second.

**Accepting a respecification as new evidence.** Another alpha, another
estimator, a favourable subgroup, dropping IND-04 from the denominator, picking
whichever fuel oil scored better — each re-describes the evidence D5 already
produced. Reopening needs something external that D5 could not have used, and
the record has to say why.

The enforcement guard is exercised from both sides: every blocked purpose must
be refused with a stated reason, and every permitted purpose — audit,
reproduction, documentation, source-quality work, the historical D5 reproduction
— must pass through untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.structure import fuel_oil_channel_closure as CL

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "fuel_oil_channel_closure.yaml"
CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
CLOSURE_SCHEMA = ROOT / "schemas" / "fuel_oil_channel_closure.schema.yaml"
REOPENING_SCHEMA = ROOT / "schemas" / "fuel_oil_reopening_evidence.schema.yaml"
CLOSURE = ROOT / "docs" / "c12_channel_closure.json"
CLOSURE_MD = ROOT / "docs" / "c12_channel_closure.md"
RUNNER = ROOT / "scripts" / "run_c12_channel_closure.py"
D5_RESULTS = ROOT / "docs" / "d5_development_results.json"
D5_AUDIT = ROOT / "docs" / "d5_assembly_audit.json"
DECISION_LOG = ROOT / "docs" / "architecture" / "decision_log.md"

V600, V1500 = "fo600_direct_sector093", "fo1500_direct_sector093"

requires_run = pytest.mark.skipif(not CLOSURE.is_file(), reason="C12 has not been run")


def _closure():
    return json.loads(CLOSURE.read_text(encoding="utf-8"))


def _policy(**overrides):
    policy = dict(CONFIG["enforcement"])
    policy["prohibited_reopening_reasons"] = CONFIG["prohibited_reopening_reasons"]
    policy.update(overrides)
    return policy


def _closure_fields(**overrides):
    fields = dict(CONFIG["closure"]["fields"])
    fields.update(overrides)
    return fields


def _validity(**overrides):
    validity = dict(CONFIG["validity_versus_eligibility"])
    validity.update(overrides)
    return validity


def _reopening(**overrides):
    record = {
        "new_evidence_id": "EPPO-CONSUMPTION-CROSSWALK-2027",
        "source": "https://www.eppo.go.th/index.php/en/en-energystatistics",
        "checksum": "a" * 64,
        "availability_date": "2027-02-01",
        "why_unavailable_to_d5": (
            "published after the D5 evaluation window closed"
        ),
        "affected_assumption": "sector_093_is_a_broad_refinery_product_proxy",
        "expected_artifact_impact": "rebuild from C9 onward",
        "not_selected_from_d5_outcomes": True,
        "superseding_decision_log_entry": "AD-R200",
        "active": True,
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# Configuration and schemas
# ---------------------------------------------------------------------------
def test_the_config_parses_and_states_the_precise_conclusion():
    assert CONFIG["conclusion"]["statement"] == CL.CLOSURE_CONCLUSION
    record = CONFIG["conclusion"]["explicit_record"]
    assert record["development_evidence_is_inconclusive_not_proof_of_absence"] is True
    assert record["closure_is_a_project_governance_decision"] is True
    assert record["closure_is_a_population_level_scientific_conclusion"] is False
    assert record["absence_of_effect_proven"] is False
    assert record["fifteen_issue_month_clusters_limit_uncertainty_resolution"] is True


def test_the_schemas_parse_and_forbid_the_merging_fields():
    closure = yaml.safe_load(CLOSURE_SCHEMA.read_text(encoding="utf-8"))
    reopening = yaml.safe_load(REOPENING_SCHEMA.read_text(encoding="utf-8"))
    banned = set(closure["prohibited_fields"]["fields"])
    assert {"fuel_oil_has_no_effect", "no_predictive_relationship_exists",
            "primary_channel", "preferred_channel"} <= banned
    required = {f["name"] for f in reopening["required_fields"]}
    assert set(CL.REOPENING_EVIDENCE_FIELDS) == required
    assert set(reopening["prohibited_fields"]["fields"]) >= {
        "d5_macro_mae", "model_mae", "benchmark_mae"
    }


def test_the_closure_fields_carry_their_required_values():
    CL.assert_closure_fields(_closure_fields())
    for name, expected in CL.REQUIRED_CLOSURE_FIELDS.items():
        assert CONFIG["closure"]["fields"][name] == expected, name


def test_both_variants_are_closed_identically():
    CL.assert_both_variants_closed(CONFIG["closure"])
    assert sorted(CONFIG["closure"]["variants"]) == sorted(CL.VARIANTS)
    assert CONFIG["closure"]["applied_identically_to_both_variants"] is True
    assert CONFIG["closure"][
        "either_variant_labelled_preferred_primary_or_less_bad"] is False


def test_the_language_guard_separates_naming_from_asserting():
    """The closure must be able to publish the list of what it may not say."""
    CL.assert_no_absence_claim(
        "Prohibited conclusions: `fuel_oil_has_no_effect`, "
        "`no_predictive_relationship_exists`."
    )
    with pytest.raises(CL.ChannelClosureError):
        CL.assert_no_absence_claim("fuel oil has no effect on industrial stress")
    with pytest.raises(CL.ChannelClosureError):
        CL.assert_no_absence_claim(
            "Prohibited conclusions: `fuel_oil_has_no_effect`.",
            strip_named_terms=False,
        )


def test_source_validity_survives_the_closure():
    CL.assert_source_validity_preserved(_validity())
    assert CONFIG["validity_versus_eligibility"][
        "official_eppo_source_documents_still_valid_evidence"] is True
    assert CONFIG["validity_versus_eligibility"][
        "may_enter_further_operational_modeling"] is False


# ---------------------------------------------------------------------------
# The enforcement guard, from both sides
# ---------------------------------------------------------------------------
def test_every_permitted_purpose_passes_through_untouched():
    policy = _policy()
    for purpose in policy["permitted_purposes"]:
        outcome = CL.assert_modeling_entry_permitted(
            policy["closed_feature_ids"] + policy["closed_aliases"],
            purpose, policy,
        )
        assert outcome["permitted"] is True, purpose
        assert outcome["blocked_feature_ids"] == []


def test_every_blocked_purpose_is_refused_with_a_reason():
    policy = _policy()
    for purpose in policy["blocked_purposes"]:
        for group in ("closed_feature_ids", "closed_aliases",
                      "closed_composite_forms", "closed_upstream_feature_tables"):
            with pytest.raises(CL.ClosedChannelError) as error:
                CL.assert_modeling_entry_permitted(policy[group], purpose, policy)
            message = str(error.value)
            assert CL.CLOSURE_STATUS in message
            assert "not missing" in message
            assert "reproducible" in message


def test_an_unknown_purpose_cannot_default_to_allowed():
    with pytest.raises(CL.ClosedChannelError, match="unknown purpose"):
        CL.assert_modeling_entry_permitted(
            [V600], "some_new_pipeline_stage", _policy()
        )


def test_unrelated_features_are_untouched_by_the_closure():
    outcome = CL.assert_modeling_entry_permitted(
        ["brent_usd_bbl", "rubber_rss3_usd_kg", "IND-05"], "modeling", _policy()
    )
    assert outcome["permitted"] is True
    assert outcome["reason"] == "no_closed_feature"


def test_aliases_and_composites_cannot_walk_past_by_spelling():
    policy = _policy()
    for alias in ("FO-600", "fo_600_2s", "Fuel Oil 1500", "sector093_fuel_oil_composite",
                  "eppo_ex_refinery_fo600_2s"):
        with pytest.raises(CL.ClosedChannelError):
            CL.assert_modeling_entry_permitted([alias], "modeling", policy)


def test_an_active_superseding_decision_opens_the_channel():
    outcome = CL.assert_modeling_entry_permitted(
        [V600], "modeling", _policy(), superseding_decision=_reopening()
    )
    assert outcome["permitted"] is True
    assert outcome["reason"] == "superseded_by_qualifying_new_evidence"
    assert outcome["new_evidence_id"] == "EPPO-CONSUMPTION-CROSSWALK-2027"


def test_a_drafted_reopening_does_not_open_the_channel():
    with pytest.raises(CL.ReopeningEvidenceError, match="not active"):
        CL.assert_modeling_entry_permitted(
            [V600], "modeling", _policy(),
            superseding_decision=_reopening(active=False),
        )


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------
def test_preservation_detects_a_changed_artifact():
    pinned = {"content:d5_development_results": "a" * 64}
    CL.assert_artifacts_preserved(pinned, dict(pinned))
    with pytest.raises(CL.ChannelClosureError, match="changed"):
        CL.assert_artifacts_preserved(
            pinned, {"content:d5_development_results": "b" * 64}
        )
    with pytest.raises(CL.ChannelClosureError, match="absent"):
        CL.assert_artifacts_preserved(pinned, {})


@requires_run
def test_the_pinned_artifacts_are_all_present_and_unchanged():
    preservation = _closure()["preservation"]
    assert preservation["artifacts_deleted"] == 0
    assert preservation["artifacts_modified"] == 0
    assert preservation["all_unchanged"] is True
    assert preservation["preservation_implies_continued_modeling_eligibility"] is False
    for name, digest in preservation["content_checksums"].items():
        path = ROOT / "docs" / f"{name}.json"
        assert path.is_file(), name
        assert json.loads(path.read_text(encoding="utf-8"))["content_checksum"] == digest
    for relative, digest in preservation["byte_checksums"].items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


# ---------------------------------------------------------------------------
# The generated closure record
# ---------------------------------------------------------------------------
@requires_run
def test_the_terminal_d5_evidence_reproduced():
    evidence = _closure()["terminal_evidence"]["reproduction"]
    assert evidence["all_reproduced"] is True
    assert evidence["failed"] == []
    assert len(evidence["checks"]) >= 40
    assert evidence["metrics_recomputed_in_c12"] is False
    assert evidence["d5_rerun_in_c12"] is False
    per = evidence["per_variant_horizon"]
    assert len(per) == 4
    for entry in per.values():
        assert entry["mae_evidence"] == "inconclusive"
        assert entry["event_safety_passed"] is False
        assert entry["overall_status"] == "inconclusive"
        assert entry["model_macro_mae"] > entry["benchmark_macro_mae"]
        assert entry["paired_ci_low"] <= 0.0 <= entry["paired_ci_high"]


@requires_run
def test_the_aggregate_expectations_match_the_task_table():
    checks = _closure()["terminal_evidence"]["reproduction"]["checks"]
    assert checks["model_worse_than_benchmark_on_point_estimate"]["actual"] == 4
    assert checks["paired_intervals_including_zero"]["actual"] == 4
    assert checks["event_safety_gates_failed"]["actual"] == 4
    assert checks["any_result_reached_supported"]["actual"] is False
    assert checks["prediction_rows"]["actual"] == 720
    assert checks["modeled_predictions"]["actual"] == 660
    assert checks["ind_04_benchmark_passthrough"]["actual"] == 60
    assert checks["variant_selected"]["actual"] is False
    assert checks["purge_evaluated"]["actual"] is False
    assert checks["locked_test_accessed"]["actual"] is False
    assert checks["target_reads_before_prediction_freeze"]["actual"] == 0
    for variant in (V600, V1500):
        assert checks[f"{variant}.h1_model_false_negatives"]["actual"] == 11
        assert checks[f"{variant}.h1_benchmark_false_negatives"]["actual"] == 8


@requires_run
def test_the_evidence_chain_attributes_c10_and_d5_correctly():
    chain = _closure()["evidence_chain"]
    assert chain["attribution"]["c10_established"] == "a_design_limitation"
    assert chain["attribution"]["d5_supplied"] == "the_development_evidence"
    assert chain["c10"]["c10_alone_demonstrates_predictive_uselessness"] is False
    assert chain["c10"]["conditioning_adds_cross_industry_scale"] is True
    assert chain["c10"]["conditioning_adds_temporal_degrees_of_freedom"] is False
    assert chain["c9"]["exposure_is_a_broad_refinery_product_proxy"] is True
    assert chain["c9"]["exposure_is_product_specific_fuel_oil_consumption"] is False
    assert chain["c8"]["missing_source_months_propagated_without_imputation"] is True
    assert chain["c7_c7_5"]["fo600_and_fo1500_are_distinct_products"] is True
    assert chain["d5"]["any_variant_horizon_point_estimate_beat_the_benchmark"] is False


@requires_run
def test_the_enforcement_was_exercised_from_both_sides():
    exercised = _closure()["enforcement"]["exercised"]
    assert exercised["permitted_purposes_all_allowed"] is True
    assert exercised["blocked_purposes_all_refused"] is True
    assert exercised["closure_reason_is_specific"] is True
    assert exercised["closed_features_reported_as_missing"] is False
    assert exercised["unrelated_features_unaffected"] is True
    assert exercised["generic_upstream_feature_creation_altered"] is False
    assert exercised["historical_d5_reproducibility_preserved"] is True
    assert len(exercised["probes"]) >= 20


@requires_run
def test_the_final_declaration_is_complete():
    payload = _closure()
    required = {
        "eppo_fuel_oil_modeling_channel_closed",
        "incremental_signal_was_not_demonstrated",
        "absence_of_an_effect_was_not_proven",
        "official_source_and_structural_artifacts_remain_preserved_and_valid_"
        "within_their_stated_limitations",
        "neither_fuel_oil_variant_is_selected",
        "no_further_specification_search_is_authorized",
        "locked_final_test_remains_unopened",
        "reopening_requires_genuinely_new_external_evidence",
    }
    assert set(payload["final_declaration"]) == required
    text = CLOSURE_MD.read_text(encoding="utf-8")
    assert "Absence of an effect was not proven." in text
    assert "The locked final test remains unopened." in text
    assert "Neither fuel-oil variant is selected." in text


@requires_run
def test_no_prohibited_artifact_was_created():
    outputs = _closure()["outputs"]
    assert outputs["prediction_artifact_created"] is False
    assert outputs["model_artifact_created"] is False
    assert outputs["metric_artifact_created"] is False
    assert outputs["target_joined_artifact_created"] is False


@requires_run
def test_the_content_checksum_reproduces():
    payload = _closure()
    stored = payload.pop("content_checksum")
    assert CL.content_checksum(payload) == stored


def test_prior_decision_log_entries_are_untouched():
    text = DECISION_LOG.read_text(encoding="utf-8")
    for entry in ("AD-R144", "AD-R145", "AD-R146", "AD-R147", "AD-R148"):
        assert text.count(f"| {entry} |") == 1, entry
    assert "AD-R149" in text, "C12 must append rather than edit"


@pytest.mark.skipif(not RUNNER.is_file(), reason="the C12 runner is absent")
def test_the_runner_fits_nothing_and_computes_no_metric():
    text = RUNNER.read_text(encoding="utf-8").lower()
    for fragment in ("lstsq", ".fit(", "ridge", "regress", "sklearn",
                     "macro_industry_mae(", "bootstrap(", "train_test_split"):
        assert fragment not in text, fragment


# ===========================================================================
# The eighteen required synthetic failures.
# ===========================================================================
def test_synthetic_1_a_channel_is_marked_model_approved():
    with pytest.raises(CL.ChannelClosureError, match="model_feature_approved"):
        CL.assert_closure_fields(_closure_fields(model_feature_approved=True))
    with pytest.raises(CL.ChannelClosureError, match="carried_forward"):
        CL.assert_closure_fields(
            _closure_fields(carried_forward_to_operational_modeling=True)
        )


def test_synthetic_2_a_channel_is_called_primary_or_preferred():
    for field in ("primary_channel", "preferred_channel", "selected_variant",
                  "less_bad_channel", "best_variant"):
        with pytest.raises(CL.ChannelClosureError, match="names a fuel-oil variant"):
            CL.assert_no_channel_preference({field: V600})
    with pytest.raises(CL.ChannelClosureError, match="labelled preferred"):
        CL.assert_no_channel_preference({
            "either_variant_labelled_preferred_primary_or_less_bad": True
        })
    with pytest.raises(CL.ChannelClosureError, match="channel selection"):
        CL.assert_no_channel_preference({"channel_selection_authorized": True})


def test_synthetic_3_inconclusive_is_described_as_proof_of_no_effect():
    for claim in ("the fuel-oil channel has no effect on industrial stress",
                  "there is no predictive relationship",
                  "the null hypothesis proven by D5",
                  "fuel oil is unrelated to industrial stress",
                  "the effect was ruled out",
                  "absence of an effect was proven"):
        with pytest.raises(CL.ChannelClosureError):
            CL.assert_no_absence_claim(claim)


def test_synthetic_4_the_source_pipeline_is_marked_invalid():
    for field in ("official_eppo_source_documents_still_valid_evidence",
                  "c7_c7_5_semantic_decisions_retained",
                  "c8_transformations_reproducible",
                  "sector_093_exposure_reproducible",
                  "interaction_architecture_mathematically_identifiable"):
        with pytest.raises(CL.ChannelClosureError, match="MODELING USE"):
            CL.assert_source_validity_preserved(_validity(**{field: False}))
    for field in ("source_rows_marked_erroneous_because_the_model_failed",
                  "transformations_marked_erroneous_because_the_model_failed",
                  "exposures_marked_erroneous_because_the_model_failed"):
        with pytest.raises(CL.ChannelClosureError, match="measured correctly"):
            CL.assert_source_validity_preserved(_validity(**{field: True}))


def test_synthetic_5_a_new_estimator_or_alpha_grid_is_authorized():
    with pytest.raises(CL.ChannelClosureError, match="additional_model_grid"):
        CL.assert_closure_fields(_closure_fields(additional_model_grid_authorized=True))
    for reason in ("trying_another_alpha", "expanding_an_alpha_grid",
                   "replacing_ridge_with_another_estimator"):
        with pytest.raises(CL.ReopeningEvidenceError, match="prohibited reopening"):
            CL.assert_prohibited_reopening_reason(
                reason, CONFIG["prohibited_reopening_reasons"]
            )


def test_synthetic_6_a_channel_is_reopened_from_d5_performance():
    with pytest.raises(CL.ReopeningEvidenceError, match="under another name"):
        CL.assert_reopening_evidence(_reopening(not_selected_from_d5_outcomes=False))
    for field in ("d5_macro_mae", "model_mae", "paired_ci_low", "mae_skill"):
        with pytest.raises(CL.ReopeningEvidenceError, match="D5 outcome field"):
            CL.assert_reopening_evidence(_reopening(**{field: 17.1}))


def test_synthetic_7_total_requirement_exposure_is_substituted_after_the_result():
    reason = "switching_direct_exposure_to_total_requirement_because_d5_failed"
    assert reason in CONFIG["prohibited_reopening_reasons"]
    with pytest.raises(CL.ReopeningEvidenceError, match="prohibited reopening"):
        CL.assert_prohibited_reopening_reason(
            reason, CONFIG["prohibited_reopening_reasons"]
        )
    with pytest.raises(CL.ReopeningEvidenceError):
        CL.assert_reopening_evidence(
            _reopening(reason=reason), CONFIG["prohibited_reopening_reasons"]
        )


def test_synthetic_8_ind_04_is_removed_from_the_historical_denominator():
    reason = "removing_ind_04_from_denominators"
    assert reason in CONFIG["prohibited_reopening_reasons"]
    with pytest.raises(CL.ReopeningEvidenceError):
        CL.assert_reopening_evidence(
            _reopening(reason=reason), CONFIG["prohibited_reopening_reasons"]
        )
    d5 = json.loads(D5_AUDIT.read_text(encoding="utf-8"))
    assert d5["ind_04"]["in_primary_twelve_industry_denominator"] is True
    assert d5["ind_04"]["dropped_from_evaluation"] is False
    assert d5["ind_04"]["converted_to_structural_zero"] is False


def test_synthetic_9_purge_or_locked_evaluation_is_authorized():
    for field in ("purge_evaluation_authorized", "locked_test_evaluation_authorized",
                  "locked_test_should_be_opened_for_this_channel"):
        with pytest.raises(CL.ChannelClosureError, match=field):
            CL.assert_closure_fields(_closure_fields(**{field: True}))
    with pytest.raises(CL.ReopeningEvidenceError):
        CL.assert_reopening_evidence(
            _reopening(reason="opening_purge_or_locked_origins"),
            CONFIG["prohibited_reopening_reasons"],
        )


def test_synthetic_10_a_modeling_assembler_accepts_a_closed_feature():
    policy = _policy()
    for purpose in policy["blocked_purposes"]:
        with pytest.raises(CL.ClosedChannelError, match=CL.CLOSURE_STATUS):
            CL.assert_modeling_entry_permitted([V600, V1500], purpose, policy)
    with pytest.raises(CL.ReopeningEvidenceError, match="missing"):
        CL.assert_modeling_entry_permitted(
            [V600], "modeling", policy,
            superseding_decision={"new_evidence_id": "X", "active": True},
        )


def test_synthetic_11_an_audit_or_reproduction_task_is_blocked():
    policy = _policy()
    for purpose in ("audit", "reproduction", "documentation", "source_quality",
                    "provenance_verification", "historical_d5_reproduction"):
        outcome = CL.assert_modeling_entry_permitted(
            policy["closed_feature_ids"] + policy["closed_upstream_feature_tables"],
            purpose, policy,
        )
        assert outcome["permitted"] is True, purpose
        assert "modeling_only" in outcome["reason"]


def test_synthetic_12_historical_artifacts_are_deleted_or_rewritten():
    pinned = {
        "content:d5_development_results": "a" * 64,
        "byte:data/model_input/d5_fuel_oil_predictions.parquet": "b" * 64,
    }
    CL.assert_artifacts_preserved(pinned, dict(pinned))
    with pytest.raises(CL.ChannelClosureError, match="absent"):
        CL.assert_artifacts_preserved(
            pinned, {"content:d5_development_results": "a" * 64}
        )
    with pytest.raises(CL.ChannelClosureError, match="rewrote its own evidence"):
        CL.assert_artifacts_preserved(
            pinned, {**pinned, "content:d5_development_results": "c" * 64}
        )


def test_synthetic_13_reopening_evidence_lacks_provenance_or_availability():
    for omitted in ("source", "checksum", "availability_date",
                    "why_unavailable_to_d5", "superseding_decision_log_entry"):
        record = {k: v for k, v in _reopening().items() if k != omitted}
        with pytest.raises(CL.ReopeningEvidenceError, match="missing"):
            CL.assert_reopening_evidence(record)
    for emptied in ("source", "checksum", "availability_date"):
        with pytest.raises(CL.ReopeningEvidenceError, match="empty"):
            CL.assert_reopening_evidence(_reopening(**{emptied: ""}))


def test_synthetic_14_a_new_evidence_record_depends_on_d5_outcome_fields():
    for field in ("d5_paired_ci", "d5_mae_evidence", "d5_event_safety",
                  "benchmark_mae", "false_negatives", "d5_coefficient"):
        with pytest.raises(CL.ReopeningEvidenceError, match="external to D5"):
            CL.assert_reopening_evidence(_reopening(**{field: "anything"}))


def test_synthetic_15_fo600_and_fo1500_are_combined():
    reason = "combining_the_two_channels"
    assert reason in CONFIG["prohibited_reopening_reasons"]
    with pytest.raises(CL.ReopeningEvidenceError):
        CL.assert_reopening_evidence(
            _reopening(reason=reason), CONFIG["prohibited_reopening_reasons"]
        )
    policy = _policy()
    for composite in policy["closed_composite_forms"]:
        with pytest.raises(CL.ClosedChannelError):
            CL.assert_modeling_entry_permitted([composite], "modeling", policy)


def test_synthetic_16_closure_language_claims_an_effect_is_absent():
    with pytest.raises(CL.ChannelClosureError, match="proof of absence"):
        CL.assert_no_absence_claim("fuel_oil_has_no_effect")
    with pytest.raises(CL.ChannelClosureError, match="proof of absence"):
        CL.assert_no_absence_claim("structural_exposure_is_invalid")
    with pytest.raises(CL.ChannelClosureError, match="proof of absence"):
        CL.assert_no_absence_claim("eppo_data_is_invalid")
    # The permitted conclusion is the one that survives.
    CL.assert_no_absence_claim(CL.CLOSURE_CONCLUSION)


@requires_run
def test_synthetic_17_d5_metrics_are_recomputed_or_changed_in_c12():
    payload = _closure()
    assert payload["terminal_evidence"]["metrics_recomputed_in_c12"] is False
    assert payload["terminal_evidence"]["d5_rerun_in_c12"] is False
    d5 = json.loads(D5_RESULTS.read_text(encoding="utf-8"))
    for key, entry in payload["terminal_evidence"]["reproduction"][
            "per_variant_horizon"].items():
        assert entry["model_macro_mae"] == (
            d5["results"][key]["model"]["macro_industry_mae"]
        )
        assert entry["benchmark_macro_mae"] == (
            d5["results"][key]["benchmark"]["macro_industry_mae"]
        )
    assert d5["content_checksum"] == payload["preservation"][
        "content_checksums"]["d5_development_results"]


@requires_run
def test_synthetic_18_a_clean_rerun_upgrades_d5_into_confirmatory_evidence():
    payload = _closure()
    d5 = json.loads(D5_RESULTS.read_text(encoding="utf-8"))
    assert d5["scope"]["confirmatory_evaluation"] is False
    assert payload["closure"]["fields"]["confirmatory_claim_authorized"] is False
    assert payload["conclusion"]["explicit_record"][
        "closure_is_a_population_level_scientific_conclusion"] is False
    with pytest.raises(CL.ChannelClosureError, match="confirmatory_claim_authorized"):
        CL.assert_closure_fields(_closure_fields(confirmatory_claim_authorized=True))
    # Rerunning D5 reproduces the same inconclusive result; it does not promote it.
    for entry in payload["terminal_evidence"]["reproduction"][
            "per_variant_horizon"].values():
        assert entry["overall_status"] == "inconclusive"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_the_closure_checksum_is_deterministic_and_sensitive():
    record = CL.ClosureRecord(fields=_closure_fields())
    assert CL.closure_checksum(record) == CL.closure_checksum(record)
    other = CL.ClosureRecord(fields=_closure_fields(), variants=(V600,))
    assert CL.closure_checksum(other) != CL.closure_checksum(record)


def test_content_checksum_ignores_the_generation_timestamp():
    assert CL.content_checksum({"a": 1, "generated_at_utc": "2026-01-01"}) == (
        CL.content_checksum({"a": 1, "generated_at_utc": "2026-08-30"})
    )
