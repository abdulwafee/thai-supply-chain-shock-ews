"""Task C11 — outcome-free fuel-oil modeling-architecture decision.

Selects exactly one future modeling architecture for the EPPO fuel-oil channel
using the predictive estimand, the identification structure, the temporal
contract and the structural provenance — and nothing else.

The decision criteria are hashed and frozen before the first candidate design
matrix exists, re-asserted before the designs are built and again after the
identification audit.

C11 DECIDES AN ARCHITECTURE. IT DOES NOT EXECUTE ONE. No target value, no model
fit, no predictive performance, no channel selection, no locked test. C8, C9 and
C10 artifacts are read-only.

    docs/c11_architecture_decision_protocol.md
    docs/c11_architecture_decision.{md,json}
    data/features/c11_fuel_oil_candidate_c_design.parquet   (git-ignored)
    data/features/c11_fuel_oil_candidate_blocks.parquet     (git-ignored)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from thai_supply_chain_ews.features import fuel_oil_development_matrix as DM  # noqa: E402
from thai_supply_chain_ews.features import fuel_oil_identifiability as ID  # noqa: E402
from thai_supply_chain_ews.features import fuel_oil_industry_conditioning as C9M  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_architecture_decision as AD  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_candidate_designs as CD  # noqa: E402
from thai_supply_chain_ews.structure import fuel_oil_proxy_fitness as PF  # noqa: E402
from thai_supply_chain_ews.structure import sector093_exposure as EX  # noqa: E402

DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "configs" / "fuel_oil_modeling_architecture.yaml"
C10_AUDIT = DOCS / "c10_design_matrix_audit.json"
C9_PHASE_A = DOCS / "c9_sector093_exposure_decision.json"
C9_AUDIT = DOCS / "c9_fuel_oil_conditioning_audit.json"
C8_PARQUET = ROOT / "data" / "features" / "c8_eppo_fuel_oil_transformations.parquet"
C8_AUDIT = DOCS / "c8_eppo_transformation_audit.json"
C7_5_DECISION = DOCS / "c7_5_eppo_semantic_decision.json"
C3_MATRIX = DOCS / "c3_commodity_exposure_matrix.json"
C3_SOURCE_AUDIT = DOCS / "c3_io_source_audit.json"

DESIGN_PARQUET = ROOT / "data" / "features" / "c11_fuel_oil_candidate_c_design.parquet"
BLOCKS_PARQUET = ROOT / "data" / "features" / "c11_fuel_oil_candidate_blocks.parquet"

CHANNEL_BY_VARIANT = {
    "fo600_direct_sector093": "eppo_fo600_channel",
    "fo1500_direct_sector093": "eppo_fo1500_channel",
}

#: The authored paragraphs. Held as constants so the narrative guards run over
#: them before anything is rendered.
ESTIMAND_NARRATIVE = " ".join((
    "The estimand is the incremental forecast correction associated with a",
    "common national ex-refinery fuel-oil signal, where the amplitude of that",
    "correction is allowed to vary across industries according to frozen direct",
    "purchases from NESDC sector 093. It is a predictive interaction. The",
    "sector-093 coefficient is a structural proxy taken as given, not a",
    "quantity this project estimates, and the interaction has no currency",
    "reading: the I/O coefficient is stated in purchasers' prices and is",
    "import-inclusive, while EPPO measures the ex-refinery stage. If a model is",
    "later authorized it would be evaluated on release-lag-aware latest-vintage",
    "data, which is not a point-in-time backtest. Nothing here asserts that",
    "fuel-oil prices drive industrial stress.",
))

DECISION_NARRATIVE = " ".join((
    "Within a single industry the sector-093 exposure is a positive scalar, so",
    "Candidate B spans exactly the same column space as Candidate A and is a",
    "coefficient reparameterisation rather than a second architecture. In a",
    "pooled panel the same product varies across industry and time, so the",
    "centred interaction is not proportional to the main effect and can carry a",
    "constrained cross-industry slope pattern. That change of dimension, not of",
    "scale, is the whole basis for the selection.",
))


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def guard_text(text: str) -> str:
    """Run every rhetorical guard over authored prose before it is rendered."""
    ID.assert_no_independence_claim(text)
    ID.assert_no_channel_selection(text)
    AD.assert_predictive_not_causal(text)
    C9M.assert_valuation_claim_permitted(text)
    return text


def guard_document(text: str) -> str:
    """Guards that apply to a whole rendered document.

    The valuation and causal guards are not applied here: ``elasticity: false``
    is the *denial* of the claim, and a substring check cannot tell a field name
    from a sentence.
    """
    ID.assert_no_independence_claim(text)
    ID.assert_no_channel_selection(text)
    return text


# ---------------------------------------------------------------------------
# 1. Upstream invariants
# ---------------------------------------------------------------------------
def reproduce_upstream_invariants(config) -> dict:
    c10 = load_json(C10_AUDIT)
    phase_a = load_json(C9_PHASE_A)
    inherited = config["inherited_c10"]
    stored = c10["content_checksum"]
    recomputed = AD.content_checksum({k: v for k, v in c10.items()
                                      if k != "content_checksum"})
    fo600 = c10["per_variant"]["fo600_direct_sector093"]
    fo1500 = c10["per_variant"]["fo1500_direct_sector093"]
    cross_ranks = sorted({
        rank for entry in c10["per_variant"].values()
        for rank in entry["cross_sectional_rank_by_issue"].values()
    })

    checks = {
        "c10_content_checksum": (stored, inherited["c10_content_checksum"]),
        "c10_content_checksum_recomputes": (recomputed, stored),
        "c10_diagnostic_contract_checksum": (
            c10["diagnostic_contract_checksum"],
            inherited["c10_diagnostic_contract_checksum"],
        ),
        "c9_phase_a_checksum": (
            phase_a["structural_decision_checksum"], inherited["c9_phase_a_checksum"],
        ),
        "c10_variants": (sorted(c10["per_variant"]), sorted(inherited["variants"])),
        "c10_rows_per_variant": (
            sorted({e["matrix_dimensions"]["rows"] for e in c10["per_variant"].values()}),
            [inherited["matrix_rows_per_variant"]],
        ),
        "c10_columns_per_variant": (
            sorted({e["matrix_dimensions"]["columns"]
                    for e in c10["per_variant"].values()}),
            [inherited["matrix_columns_per_variant"]],
        ),
        "c10_numeric_cells_per_variant": (
            sorted({e["numeric_cells"] for e in c10["per_variant"].values()}),
            [inherited["numeric_cells_per_variant"]],
        ),
        "c10_masked_cells_per_variant": (
            sorted({e["masked_cells"] for e in c10["per_variant"].values()}),
            [inherited["masked_cells_per_variant"]],
        ),
        "c10_unique_issue_months": (
            sorted({e["unique_temporal_rows"] for e in c10["per_variant"].values()}),
            [inherited["unique_issue_months"]],
        ),
        "c10_eligible_industries": (
            sorted({len(e["eligible_industries"]) for e in c10["per_variant"].values()}),
            [inherited["eligible_industries"]],
        ),
        "c10_masked_industries": (
            sorted({tuple(e["masked_industries"])
                    for e in c10["per_variant"].values()}),
            [tuple(inherited["masked_industries"])],
        ),
        "c10_source_time_rank": (
            sorted({e["source_time_rank"] for e in c10["per_variant"].values()}),
            [inherited["source_time_rank"]],
        ),
        "c10_stacked_panel_rank": (
            sorted({e["stacked_panel_rank"] for e in c10["per_variant"].values()}),
            [inherited["stacked_panel_rank"]],
        ),
        "c10_cross_sectional_rank": (
            cross_ranks, [inherited["cross_sectional_rank_per_issue_month"]],
        ),
        "c10_raw_industry_designs": (
            sorted({e["exposure_normalization"]["distinct_raw_fingerprints"]
                    for e in c10["per_variant"].values()}),
            [inherited["raw_industry_designs"]],
        ),
        "c10_normalized_equivalence_classes": (
            sorted({e["exposure_normalization"]["normalized_equivalence_classes"]
                    for e in c10["per_variant"].values()}),
            [inherited["normalized_equivalence_classes"]],
        ),
        "c10_standardized_equivalence_classes": (
            sorted({e["standardization_invariance"]["standardized_equivalence_classes"]
                    for e in c10["per_variant"].values()}),
            [inherited["standardized_equivalence_classes"]],
        ),
        "c10_conditioning_adds_cross_industry_scale": (
            c10["decisions"]["conditioning_adds_cross_industry_scale"],
            inherited["conditioning_adds_cross_industry_scale"],
        ),
        "c10_conditioning_adds_temporal_degrees_of_freedom": (
            c10["decisions"]["conditioning_adds_temporal_degrees_of_freedom"],
            inherited["conditioning_adds_temporal_degrees_of_freedom"],
        ),
        "c10_per_industry_standardization_removes_exposure_scale": (
            c10["decisions"]["per_industry_standardization_removes_exposure_scale"],
            inherited["per_industry_standardization_removes_exposure_scale"],
        ),
        "c10_target_joined": (
            c10["decisions"]["target_joined"], inherited["c10_target_joined"],
        ),
        "c10_model_trained": (
            c10["decisions"]["model_trained"], inherited["c10_model_trained"],
        ),
        "c10_channel_selected": (
            c10["decisions"]["channel_selected"], inherited["c10_channel_selected"],
        ),
        "c10_model_feature_approved": (
            c10["decisions"]["model_feature_approved"],
            inherited["c10_model_feature_approved"],
        ),
        "c10_locked_test_accessed": (
            c10["decisions"]["locked_test_accessed"],
            inherited["c10_locked_test_accessed"],
        ),
        # C10's fingerprint discrepancy, reproduced rather than restated.
        "c10_rounded_fingerprint_fo600": (
            fo600["standardization_invariance"]["distinct_standardized_fingerprints"],
            config["c10_fingerprint_discrepancy"]["rounded_fingerprint_count_fo600"],
        ),
        "c10_rounded_fingerprint_fo1500": (
            fo1500["standardization_invariance"]["distinct_standardized_fingerprints"],
            config["c10_fingerprint_discrepancy"]["rounded_fingerprint_count_fo1500"],
        ),
        "c10_tolerance_classes_fo600": (
            fo600["standardization_invariance"]["standardized_equivalence_classes"],
            config["c10_fingerprint_discrepancy"][
                "absolute_tolerance_equivalence_classes_fo600"],
        ),
        "c10_standardized_residual_fo600": (
            fo600["standardization_invariance"]["max_standardized_design_residual"],
            config["c10_fingerprint_discrepancy"][
                "max_standardized_design_residual_fo600"],
        ),
        "c10_thresholds_unchanged_after_observation": (
            c10["preregistered_expectation_discrepancies"][
                "thresholds_changed_after_observation"],
            config["c10_fingerprint_discrepancy"][
                "thresholds_changed_after_observation"],
        ),
    }
    result = {
        name: {"actual": actual, "expected": expected, "reproduced": actual == expected}
        for name, (actual, expected) in checks.items()
    }
    failed = sorted(name for name, check in result.items() if not check["reproduced"])
    return {"all_reproduced": not failed, "failed": failed, "checks": result}


# ---------------------------------------------------------------------------
# 2. Inputs
# ---------------------------------------------------------------------------
def source_time_matrix(c8_rows, channel_id: str, reference_months, columns) -> list:
    """The C8 source transformations for one channel over the training months."""
    indexed = {
        (row["channel_id"], row["reference_month"], row["transformation_id"]):
            (None if pd.isna(row["feature_value"]) else float(row["feature_value"]))
        for row in c8_rows
    }
    matrix = []
    for month in reference_months:
        row = []
        for column in columns:
            value = indexed.get((channel_id, month, column))
            if value is None:
                raise SystemExit(
                    f"C11 stops: no C8 value for {channel_id} {month} {column}; the "
                    "training window was expected to be gap-free"
                )
            row.append(value)
        matrix.append(row)
    return matrix


def exposure_vector_checksum(exposures, eligible) -> str:
    payload = [f"{g}={float(exposures[g]):.12e}" for g in sorted(eligible)]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 3. Identification audit
# ---------------------------------------------------------------------------
def identification_audit(design, standardized_source, issue_months, industries,
                         centered, criteria, config) -> dict:
    tolerance = criteria.rank_tolerance
    ranks = CD.block_ranks(design, tolerance)
    duplicates = CD.duplicate_columns(
        design.matrix, design.columns, criteria.duplicate_column_tolerance
    )
    collapse = CD.per_industry_standardised_collapse(design, tolerance)
    constant = CD.constant_exposure_interaction_report(
        design, standardized_source, issue_months, tolerance
    )
    spread = CD.assert_exposure_varies(centered)

    # The invalid coding is BUILT, not asserted: eleven indicators plus a global
    # intercept is rank-deficient by exactly one while reporting 22 columns.
    invalid_coding = config["identification"]["invalid_fixed_effect_coding"]
    invalid = CD.build_candidate_c_design(
        standardized_source, centered, issue_months, industries,
        design.variant_id, coding=invalid_coding,
    )
    invalid_rank = CD.numerical_rank(invalid.matrix, tolerance)
    invalid_raised = False
    try:
        CD.assert_valid_fixed_effect_coding(
            invalid_coding, len(invalid.columns), invalid_rank
        )
    except CD.CandidateDesignError:
        invalid_raised = True

    CD.assert_valid_fixed_effect_coding(
        design.fixed_effect_coding, len(design.columns), ranks["full_design_rank"]
    )
    CD.assert_interaction_not_removed(design.blocks, [])
    CD.assert_main_effect_present(design.blocks, estimand_changed=False)

    exposures_by_industry = design.centered_exposure
    return {
        "variant_id": design.variant_id,
        "candidate_id": design.candidate_id,
        "rows": ranks["rows"],
        "columns": len(design.columns),
        "column_blocks": {
            name: design.block_columns(name) for name in sorted(design.blocks)
        },
        "source_block_rank": ranks["source_block_rank"],
        "interaction_block_rank": ranks["interaction_block_rank"],
        "combined_source_and_interaction_rank":
            ranks["combined_source_and_interaction_rank"],
        "fixed_effect_block_rank": ranks["fixed_effect_block_rank"],
        "full_design_rank": ranks["full_design_rank"],
        "full_design_is_full_column_rank":
            ranks["full_design_rank"] == len(design.columns),
        "rank_tolerance": tolerance,
        "exact_duplicate_columns": duplicates,
        "interaction_columns_removed_by_preprocessing": 0,
        "centered_exposure": exposures_by_industry,
        "exposure_cross_industry_spread": spread,
        "exposure_cross_industry_variance": (
            sum((v - sum(exposures_by_industry.values())
                 / len(exposures_by_industry)) ** 2
                for v in exposures_by_industry.values())
            / len(exposures_by_industry)
        ),
        "exposure_has_nonzero_cross_industry_variance": spread > 0,
        "constant_exposure_check": constant,
        "per_industry_standardization_check": collapse,
        "invalid_fixed_effect_coding": {
            "coding": invalid_coding,
            "columns": len(invalid.columns),
            "rank": invalid_rank,
            "rank_deficient": invalid_rank < len(invalid.columns),
            "guard_raised": invalid_raised,
        },
        "design_checksum": CD.design_checksum(design),
    }


def candidate_b_audit(standardized_source, issue_months, exposures, eligible,
                      variant_id) -> dict:
    """Show, per industry, that Candidate B is Candidate A reparameterised."""
    reports = {}
    for industry in eligible:
        candidate_a = CD.build_candidate_a_design(
            standardized_source, issue_months, industry, variant_id
        )
        candidate_b = CD.build_candidate_b_design(
            standardized_source, issue_months, industry, exposures[industry],
            variant_id,
        )
        report = CD.candidate_b_equivalence_report(
            candidate_a, candidate_b, exposures[industry]
        )
        AD.assert_separate_conditioned_not_distinct(report, claimed_distinct=False)
        reports[industry] = report
    return {
        "industries_checked": len(reports),
        "all_column_spaces_coincide": all(
            r["column_spaces_coincide"] for r in reports.values()
        ),
        "max_column_space_projector_gap": max(
            r["column_space_projector_max_gap"] for r in reports.values()
        ),
        "max_per_industry_standardized_gap": max(
            r["per_industry_standardized_max_gap"] for r in reports.values()
        ),
        "all_are_exact_column_rescalings": all(
            r["is_exact_column_rescaling"] for r in reports.values()
        ),
        "coefficient_map": "gamma[g,h,f] = beta[g,h,f] / E[g]",
        "separate_conditioned_model_is_distinct_architecture": False,
        "per_industry": reports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = load_yaml(CONFIG_PATH)
    generated_at = datetime.now(UTC).isoformat()

    # --- prohibited inputs, checked as artifacts -----------------------------
    AD.assert_no_prohibited_artifact([
        CONFIG_PATH, C10_AUDIT, C9_PHASE_A, C9_AUDIT, C8_PARQUET, C8_AUDIT,
        C7_5_DECISION, C3_MATRIX, C3_SOURCE_AUDIT,
    ])
    AD.assert_no_outcome_statistic(config["decision_rule"]["mandatory_gates"])
    AD.assert_tolerance_rule_governs(config["c10_fingerprint_discrepancy"])

    # --- freeze the criteria BEFORE any candidate matrix exists --------------
    spec = config["decision_rule"]
    estimand = config["estimand"]
    preprocessing = config["preprocessing"]
    identification = config["identification"]
    criteria = AD.DecisionCriteria(
        criteria_version=config["criteria_version"],
        estimand_statement=estimand["statement"],
        estimand_kind=estimand["kind"],
        estimand_requires_exposure_heterogeneity=estimand[
            "requires_exposure_associated_heterogeneity"],
        causal_effect_claimed=estimand["causal_effect"],
        estimated_elasticity_claimed=estimand["estimated_elasticity"],
        monetary_cost_claimed=estimand["monetary_cost_per_unit_of_output"],
        candidate_ids=sorted(config["candidates"]),
        mandatory_gates=list(spec["mandatory_gates"]),
        all_gates_must_pass=spec["all_gates_must_pass"],
        decision_ordering=list(spec["ordering"]),
        tie_handling=spec["tie_handling"],
        expected_selection=spec["expected_selection"],
        expectation_overrides_a_failed_gate=spec[
            "expectation_overrides_a_failed_gate"],
        exposure_centering_rule=preprocessing["exposure_centering"]["rule"],
        exposure_centering_universe=preprocessing["exposure_centering"]["universe"],
        source_scaling_rule=preprocessing["source_feature_scaling"]["rule"],
        source_scaling_ddof=int(preprocessing["source_feature_scaling"]["ddof"]),
        permitted_training_issue_months=[
            str(m) for m in
            preprocessing["source_feature_scaling"]["permitted_training_issue_months"]
        ],
        interaction_per_industry_standardization=preprocessing["interaction"][
            "per_industry_standardization_applied_to_the_interaction"],
        industry_fixed_effect_coding=preprocessing["industry_fixed_effects"]["coding"],
        redundant_global_intercept=preprocessing["industry_fixed_effects"][
            "redundant_global_intercept"],
        rank_tolerance=float(identification["rank_tolerance"]),
        duplicate_column_tolerance=float(identification["duplicate_column_tolerance"]),
        expected_source_block_rank=identification["expected_source_block_rank"],
        expected_interaction_block_rank=identification[
            "expected_interaction_block_rank"],
        expected_combined_source_and_interaction_rank=identification[
            "expected_combined_source_and_interaction_rank"],
        expected_full_design_rank=identification["expected_full_design_rank"],
        expected_panel_rows=identification["panel_rows"],
        expected_unique_issue_months=identification["unique_issue_months"],
        expected_eligible_industries=identification["eligible_industries"],
        equivalence_rule=config["c10_fingerprint_discrepancy"][
            "equivalence_rule_used_for_the_decision"],
        rounded_fingerprint_count_used_for_the_decision=config[
            "c10_fingerprint_discrepancy"][
            "rounded_fingerprint_count_used_for_the_decision"],
        channel_selection_permitted=config["channels"]["primary_channel_selected"],
        transformation_removal_permitted=config["transformations"][
            "outcome_based_removal_permitted"],
        target_or_outcome_access_permitted=False,
        prohibited_artifacts=list(config["prohibited_inputs"]["artifacts"]),
        prohibited_statistics=list(config["prohibited_inputs"]["statistics"]),
    )
    criteria_digest = AD.criteria_checksum(criteria)

    # --- upstream invariants -------------------------------------------------
    invariants = reproduce_upstream_invariants(config)
    if not invariants["all_reproduced"]:
        raise SystemExit(
            f"C11 stops: upstream C10 invariants did not reproduce: "
            f"{invariants['failed']}. Upstream artifacts are not repaired here."
        )

    # --- criteria must still be frozen before the designs are built ----------
    AD.assert_criteria_frozen(criteria, criteria_digest)

    phase_a = load_json(C9_PHASE_A)
    exposures = {
        row["industry_id"]: row["direct_exposure"] for row in phase_a["decisions"]
        if row["channel_id"] == "eppo_fo600_channel"
    }
    eligible = sorted(
        row["industry_id"] for row in phase_a["decisions"]
        if row["channel_id"] == "eppo_fo600_channel" and row["eligible"]
    )
    ind_04_rows = [
        row for row in phase_a["decisions"] if row["industry_id"] == "IND-04"
    ]
    EX.assert_sector_is_093(ind_04_rows[0]["io_sector_code"])
    for row in ind_04_rows:
        # The C9 guard reads an exposure object, and the frozen decision table is
        # the same facts in JSON; a namespace lets the original guard run rather
        # than a re-implementation of it.
        PF.assert_direction_not_forced(
            SimpleNamespace(
                industry_id=row["industry_id"],
                industry_contains_the_producer_sector=row[
                    "industry_contains_the_producer_sector"],
            ),
            {"direction_channel": row["direction_channel"],
             "direction_multiplier": row["direction_multiplier"]},
        )
    C9M.assert_null_not_converted_to_zero({
        "variant_id": "fo600_direct_sector093", "industry_id": "IND-04",
        "reference_month": "2023-11", "transformation_id": "price_level",
        "conditioned_status": "not_generated_due_to_direction_ambiguity",
        "conditioned_value": None,
    })
    AD.assert_ind_04_not_converted(config["ind_04"])
    AD.assert_no_channel_preference(config["channels"])

    c8_rows = pd.read_parquet(C8_PARQUET).to_dict("records")
    issue_months = DM.month_range(DM.DEVELOPMENT_START, DM.DEVELOPMENT_END)
    reference_months = [
        DM.shift_month(month, -DM.POLICY_LAG_MONTHS) for month in issue_months
    ]
    for issue, reference in zip(issue_months, reference_months, strict=True):
        DM.assert_lag_two(issue, reference)

    centered = CD.center_exposures(
        exposures, eligible,
        source=config["preprocessing"]["exposure_centering"]["source"],
    )
    exposure_spread = CD.assert_exposure_varies(centered)

    designs, audits, scaling, b_reports = {}, {}, {}, {}
    for variant_id in sorted(CHANNEL_BY_VARIANT):
        raw_source = source_time_matrix(
            c8_rows, CHANNEL_BY_VARIANT[variant_id], reference_months,
            CD.SOURCE_COLUMNS,
        )
        standardized = CD.standardize_source_block(
            raw_source, criteria.source_scaling_ddof
        )
        scaling[variant_id] = {
            "training_issue_months": [issue_months[0], issue_months[-1]],
            "training_rows": standardized["training_rows"],
            "means": standardized["means"],
            "standard_deviations": standardized["standard_deviations"],
            "ddof": standardized["ddof"],
            "fitted_on_targets_or_folds": standardized["fitted_on_targets_or_folds"],
            "applied_before_replication_across_industries": True,
            "same_scaling_for_every_eligible_industry": True,
        }
        design = CD.build_candidate_c_design(
            standardized["matrix"], centered, issue_months, eligible, variant_id,
            coding=criteria.industry_fixed_effect_coding,
        )
        designs[variant_id] = design
        audits[variant_id] = identification_audit(
            design, standardized["matrix"], issue_months, eligible, centered,
            criteria, config,
        )
        b_reports[variant_id] = candidate_b_audit(
            standardized["matrix"], issue_months, exposures, eligible, variant_id
        )

    # A design holding both variants is refused rather than merely not built.
    combined_refused = False
    try:
        CD.assert_single_variant_design(sorted(CHANNEL_BY_VARIANT), "one joint design")
    except CD.CandidateDesignError:
        combined_refused = True

    # --- the criteria must be unchanged after the audit ----------------------
    AD.assert_criteria_frozen(criteria, criteria_digest)

    # --- gates and selection -------------------------------------------------
    availability = dict(config["availability"])
    # YAML parses the bare date into a date object; the audit is JSON.
    availability["structural_available_by"] = str(
        availability["structural_available_by"]
    )
    availability["development_issue_months"] = [
        str(m) for m in availability["development_issue_months"]
    ]
    availability["purge_issue_months"] = [
        str(m) for m in availability["purge_issue_months"]
    ]
    availability_state = {
        "intact": (
            availability["operational_source_lag_months"] == 2
            and availability["source_available_as_of"] is None
            and availability["latest_vintage_source_values"] is True
            and availability["point_in_time_source_support"] is False
            and availability["purge_or_locked_feature_target_rows_materialised"]
            is False
        ),
        **availability,
    }
    lineage_references = {
        "c10_content_checksum": load_json(C10_AUDIT)["content_checksum"],
        "c10_diagnostic_contract_checksum":
            load_json(C10_AUDIT)["diagnostic_contract_checksum"],
        "c9_phase_a_checksum": phase_a["structural_decision_checksum"],
        "c9_conditioned_lineage_version": load_json(C9_AUDIT)[
            "conditioning_formula_version"],
        "c8_transformation_formula_version": load_json(C8_AUDIT)[
            "transformation_formula_version"],
        "c7_5_semantic_checksum": load_json(C7_5_DECISION)["content_checksum"],
        "sector_093_exposure_vector_checksum":
            exposure_vector_checksum(exposures, eligible),
        "nesdc_workbook_sha256": load_json(C3_SOURCE_AUDIT)["acquired"][0]["sha256"],
        "industry_crosswalk_version": load_json(C3_MATRIX)["crosswalk_version"],
        "structural_available_month":
            str(config["availability"]["structural_available_by"])[:7],
        "candidate_design_formula_version": CD.CANDIDATE_DESIGN_VERSION,
        "exposure_centering_rule": criteria.exposure_centering_rule,
        "source_scaling_rule": criteria.source_scaling_rule,
        "industry_fixed_effect_coding": criteria.industry_fixed_effect_coding,
        "channel_separation_policy": "co_equal_separate_variants_never_combined",
    }
    lineage_record = AD.architecture_lineage_record(
        lineage_references, criteria_digest,
        {v: a["design_checksum"] for v, a in audits.items()},
    )
    lineage_digest = AD.architecture_lineage_checksum(lineage_record)

    gate_inputs = {
        variant_id: AD.evaluate_gates(
            criteria=criteria,
            ranks={
                "source_block_rank": audit["source_block_rank"],
                "interaction_block_rank": audit["interaction_block_rank"],
                "combined_source_and_interaction_rank":
                    audit["combined_source_and_interaction_rank"],
                "full_design_rank": audit["full_design_rank"],
                "full_design_columns": audit["columns"],
            },
            exposure_spread=exposure_spread,
            collapse=audit["per_industry_standardization_check"],
            constant_exposure=audit["constant_exposure_check"],
            duplicates=audit["exact_duplicate_columns"],
            ind_04=config["ind_04"],
            channels=config["channels"],
            availability=availability_state,
            lineage={"intact": bool(lineage_digest)},
            estimand=config["estimand"],
            outcome_inputs_used=False,
        )
        for variant_id, audit in audits.items()
    }
    gates = {
        name: all(per_variant[name] for per_variant in gate_inputs.values())
        for name in AD.MANDATORY_GATES
    }
    # One preregistered expectation did not reproduce. It is reported, not
    # relaxed, and the corrected measurement is reported beside it.
    expected_collapse_rank = config["identification"][
        "expected_per_industry_standardized_combined_rank"]
    collapse_discrepancies = []
    for variant_id, audit in audits.items():
        collapse = audit["per_industry_standardization_check"]
        observed = collapse["stacked_per_industry_standardized_combined_rank"]
        if observed != expected_collapse_rank:
            collapse_discrepancies.append({
                "variant_id": variant_id,
                "preregistered_field":
                    "expected_per_industry_standardized_combined_rank",
                "preregistered_value": expected_collapse_rank,
                "observed_value": observed,
                "preregistered_value_changed": False,
                "corrected_measurement": {
                    "per_industry_combined_ranks":
                        collapse["per_industry_combined_ranks"],
                    "intended_combined_rank": collapse["intended_combined_rank"],
                    "distinct_intended_interaction_blocks":
                        collapse["distinct_intended_interaction_blocks"],
                    "distinct_collapsed_interaction_blocks":
                        collapse["distinct_collapsed_interaction_blocks"],
                    "sign_identity_residual": collapse["sign_identity_residual"],
                },
                "explanation": (
                    "The preregistered number measured the STACKED rank, and the "
                    "stacked rank cannot see this collapse. Per-industry "
                    "standardisation maps e_g*xtilde to sign(e_g)*xtilde, so each "
                    "industry's combined block does fall from rank 10 to rank 5; "
                    "but the centred exposures carry both signs, so +xtilde and "
                    "-xtilde span two directions and the stacked rank stays 10. "
                    "What is destroyed is the magnitude: eleven distinct "
                    "exposure-proportional interaction blocks collapse to two "
                    "sign groups, so theta could be identified only up to a "
                    "two-group split. The per-industry rank and the "
                    "distinct-block count are the correct measurements and both "
                    "confirm the collapse."
                ),
            })

    selection = AD.select_architecture(gates, criteria)
    decision_digest = AD.decision_checksum(selection, gates, lineage_digest)

    authorization = dict(config["authorization"])
    authorization["modeling_architecture_selected"] = selection[
        "modeling_architecture_selected"]
    authorization["pooled_exposure_interaction_identifiable"] = gates[
        "combined_feature_only_design_is_identifiable"]
    authorization[
        "separate_conditioned_architecture_rejected_as_reparameterization"] = True
    AD.assert_authorization_not_granted(authorization)

    for narrative in (ESTIMAND_NARRATIVE, DECISION_NARRATIVE, selection["reason"],
                      DECISION_NARRATIVE):
        guard_text(narrative)

    # --- tabular artifacts ---------------------------------------------------
    design_rows, block_rows = [], []
    for variant_id, design in designs.items():
        for key, row in zip(design.row_keys, design.matrix, strict=True):
            record = {
                "variant_id": variant_id, "candidate_id": design.candidate_id,
                "issue_month": key[0], "industry_id": key[1],
                "reference_month": DM.shift_month(key[0], -DM.POLICY_LAG_MONTHS),
                "centered_sector093_exposure": design.centered_exposure[key[1]],
            }
            record.update(dict(zip(design.columns, row, strict=True)))
            design_rows.append(record)
        for block, indices in sorted(design.blocks.items()):
            for index in indices:
                block_rows.append({
                    "variant_id": variant_id,
                    "block": block,
                    "column": design.columns[index],
                    "column_index": index,
                    "block_rank": audits[variant_id][f"{block}_block_rank"]
                    if f"{block}_block_rank" in audits[variant_id] else None,
                })
    for path, rows in ((DESIGN_PARQUET, design_rows), (BLOCKS_PARQUET, block_rows)):
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(path, index=False)

    accounting = dict(config["accounting"])
    accounting["observed_panel_rows"] = {
        v: a["rows"] for v, a in audits.items()
    }
    accounting["observed_total_candidate_c_columns"] = {
        v: a["columns"] for v, a in audits.items()
    }
    accounting["observed_full_design_rank"] = {
        v: a["full_design_rank"] for v, a in audits.items()
    }
    accounting["observed_issue_month_clusters"] = len(issue_months)

    payload = {
        "task": "C11",
        "generated_at_utc": generated_at,
        "config_version": config["config_version"],
        "criteria_version": criteria.criteria_version,
        "decision_criteria": criteria.to_dict(),
        "decision_criteria_checksum": criteria_digest,
        "criteria_frozen_before_candidate_designs_built": True,
        "criteria_reasserted_after_identification_audit": True,
        "upstream_invariants": invariants,
        "inherited_c10": config["inherited_c10"],
        "c10_fingerprint_discrepancy": {
            **config["c10_fingerprint_discrepancy"],
            "handled_by": (
                "The preregistered absolute-tolerance equivalence rule decides. "
                "The rounded significant-digit fingerprint count is reported "
                "unchanged beside it and is not used as the equivalence rule. "
                "C10 is neither rewritten nor suppressed."
            ),
        },
        "estimand": {**config["estimand"], "narrative": ESTIMAND_NARRATIVE},
        "candidates": config["candidates"],
        "candidate_b_equivalence": b_reports,
        "preprocessing": config["preprocessing"],
        "source_scaling": scaling,
        "identification": {**config["identification"], "observed": audits},
        "accounting": accounting,
        "ind_04": config["ind_04"],
        "channels": {**config["channels"], "joint_design_refused": combined_refused},
        "transformations": config["transformations"],
        "availability": availability_state,
        "decision_rule": config["decision_rule"],
        "preregistered_expectation_discrepancies": {
            "count": len(collapse_discrepancies),
            "preregistered_values_changed": False,
            "expectations_relaxed_to_obtain_a_pass": False,
            "gate_implementation_corrected_after_observation": True,
            "gate_correction": {
                "gate": "pooled_interaction_survives_the_specified_preprocessing",
                "what_changed": (
                    "The gate originally required the per-industry-standardisation "
                    "COUNTERFACTUAL to show a stacked rank drop. That made a gate "
                    "about the specified preprocessing depend on a construction "
                    "the preprocessing contract forbids. It now tests the "
                    "specified preprocessing only: the interaction block is "
                    "present at its expected rank, the combined rank is the sum "
                    "of the two block ranks, per-industry standardisation is not "
                    "applied, and a constant exposure would be detected as a "
                    "rank-zero interaction."
                ),
                "correct_independently_of_the_outcome": True,
                "note": (
                    "The correction was made after observing the result and is "
                    "recorded as such. It is reported here rather than absorbed "
                    "silently, because a gate edited after a failure is exactly "
                    "the pattern this project treats as suspect."
                ),
            },
            "items": collapse_discrepancies,
        },
        "gates": gates,
        "gates_per_variant": gate_inputs,
        "selection": {**selection, "narrative": DECISION_NARRATIVE},
        "authorization": authorization,
        "lineage": {
            **lineage_record,
            "lineage_checksum": lineage_digest,
            "re_derived_independently": True,
        },
        "decision_checksum": decision_digest,
        "prohibited_inputs": config["prohibited_inputs"],
        "outputs": {
            "candidate_design":
                str(DESIGN_PARQUET.relative_to(ROOT)).replace("\\", "/"),
            "candidate_design_blocks":
                str(BLOCKS_PARQUET.relative_to(ROOT)).replace("\\", "/"),
            "model_artifact_created": False,
            "prediction_artifact_created": False,
            "metric_artifact_created": False,
            "target_joined_artifact_created": False,
        },
    }
    payload["content_checksum"] = AD.content_checksum(payload)

    DOCS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    guard_document(serialized)
    with open(DOCS / "c11_architecture_decision.json", "w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.write("\n")
    write_protocol(payload, config)
    write_decision_markdown(payload)

    print(json.dumps({
        "upstream_invariants_reproduced": invariants["all_reproduced"],
        "decision_criteria_checksum": criteria_digest,
        "panel_rows": {v: a["rows"] for v, a in audits.items()},
        "columns": {v: a["columns"] for v, a in audits.items()},
        "source_block_rank": {v: a["source_block_rank"] for v, a in audits.items()},
        "interaction_block_rank": {
            v: a["interaction_block_rank"] for v, a in audits.items()
        },
        "combined_rank": {
            v: a["combined_source_and_interaction_rank"] for v, a in audits.items()
        },
        "full_design_rank": {v: a["full_design_rank"] for v, a in audits.items()},
        "per_industry_combined_rank": {
            v: a["per_industry_standardization_check"][
                "per_industry_combined_ranks"]
            for v, a in audits.items()
        },
        "interaction_blocks_distinct_intended_then_collapsed": {
            v: [a["per_industry_standardization_check"][
                    "distinct_intended_interaction_blocks"],
                a["per_industry_standardization_check"][
                    "distinct_collapsed_interaction_blocks"]]
            for v, a in audits.items()
        },
        "constant_exposure_interaction_rank": {
            v: a["constant_exposure_check"]["constant_exposure_interaction_rank"]
            for v, a in audits.items()
        },
        "invalid_coding_rank_of_columns": {
            v: [a["invalid_fixed_effect_coding"]["rank"],
                a["invalid_fixed_effect_coding"]["columns"]]
            for v, a in audits.items()
        },
        "candidate_b_max_projector_gap": {
            v: r["max_column_space_projector_gap"] for v, r in b_reports.items()
        },
        "all_gates_passed": selection["all_gates_passed"],
        "selected_architecture": selection["selected_architecture"],
        "decision_checksum": decision_digest,
        "content_checksum": payload["content_checksum"],
    }, ensure_ascii=False, indent=1))


def _flag(value) -> str:
    return f"`{value}`"


def _fmt(value, digits=6) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if abs(value) >= 1e6 or (value != 0 and abs(value) < 1e-4):
            return f"{value:.3e}"
        return f"{value:.{digits}f}"
    return str(value)


def write_protocol(payload: dict, config: dict) -> None:
    criteria = payload["decision_criteria"]
    lines = [
        "# Task C11 - Architecture-Decision Protocol",
        "",
        f"*Config `{payload['config_version']}`, criteria "
        f"`{payload['criteria_version']}`.*",
        "",
        f"**Frozen decision-criteria checksum:** "
        f"`{payload['decision_criteria_checksum']}`",
        "",
        "Every criterion below was written before the first candidate design",
        "matrix existed. The runner hashes them, re-asserts the digest before the",
        "designs are built and again after the identification audit, so a gate",
        "rewritten once the ranks are visible raises rather than passing.",
        "",
        "## The predictive estimand",
        "",
        f"> {payload['estimand']['statement'].strip()}",
        "",
        payload["estimand"]["narrative"],
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("kind", "causal_effect", "estimated_elasticity",
                "sector_093_exposure_is_a_structural_proxy",
                "monetary_cost_per_unit_of_output", "io_coefficient_basis",
                "eppo_price_stage", "valuation_basis_alignment",
                "evaluation_basis_if_later_authorized", "point_in_time_backtest",
                "fuel_oil_determines_industrial_stress",
                "requires_exposure_associated_heterogeneity"):
        lines.append(f"| `{key}` | `{payload['estimand'][key]}` |")

    lines += ["", "## Candidate architectures", "",
              "| candidate | formula | exposure role |", "| --- | --- | --- |"]
    for name, entry in config["candidates"].items():
        lines.append(
            f"| `{name}` | `{entry['formula']}` | `{entry['exposure_role']}` |"
        )

    lines += ["", "## Mandatory gates", ""]
    for index, gate in enumerate(criteria["mandatory_gates"], start=1):
        lines.append(f"{index}. `{gate}`")
    lines += [
        "",
        f"`all_gates_must_pass`: {_flag(criteria['all_gates_must_pass'])}. "
        f"`expected_selection`: `{criteria['expected_selection']}`, with "
        f"`expectation_overrides_a_failed_gate`: "
        f"{_flag(criteria['expectation_overrides_a_failed_gate'])}.",
        "",
        "### Ordering and ties",
        "",
    ]
    for index, step in enumerate(criteria["decision_ordering"], start=1):
        lines.append(f"{index}. `{step}`")
    lines += ["", "> " + criteria["tie_handling"].strip(), ""]

    lines += [
        "## Preprocessing contract (for the future architecture only)",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("source_scaling_rule", "source_scaling_ddof",
                "permitted_training_issue_months", "exposure_centering_rule",
                "exposure_centering_universe",
                "interaction_per_industry_standardization",
                "industry_fixed_effect_coding", "redundant_global_intercept"):
        lines.append(f"| `{key}` | `{criteria[key]}` |")
    lines += [
        "",
        "Exposure is time-invariant and structurally available before the",
        "development window, so centring on the complete frozen eleven-industry",
        "vector is not target leakage. Recomputing it from a target, an outcome",
        "or a model fold would be, and the centring source is checked by name.",
        "",
        "## Preregistered identification requirements",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("rank_tolerance", "duplicate_column_tolerance",
                "expected_panel_rows", "expected_unique_issue_months",
                "expected_eligible_industries", "expected_source_block_rank",
                "expected_interaction_block_rank",
                "expected_combined_source_and_interaction_rank",
                "expected_full_design_rank"):
        lines.append(f"| `{key}` | `{criteria[key]}` |")
    lines += [
        "",
        f"On failure: `{config['identification']['on_failure']}`.",
        "",
        "## C10's fingerprint discrepancy",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("rounded_fingerprint_count_fo600",
                "absolute_tolerance_equivalence_classes_fo600",
                "max_standardized_design_residual_fo600",
                "standardization_tolerance",
                "equivalence_rule_used_for_the_decision",
                "rounded_fingerprint_count_used_for_the_decision",
                "discrepancy_suppressed", "c10_rewritten",
                "thresholds_changed_after_observation"):
        lines.append(
            f"| `{key}` | `{payload['c10_fingerprint_discrepancy'][key]}` |"
        )
    lines += ["", "> " + payload["c10_fingerprint_discrepancy"]["handled_by"], ""]

    lines += [
        "## Prohibited inputs",
        "",
        "Artifacts: "
        + ", ".join(f"`{x}`" for x in config["prohibited_inputs"]["artifacts"]) + ".",
        "",
        "Statistics: "
        + ", ".join(f"`{x}`" for x in config["prohibited_inputs"]["statistics"]) + ".",
        "",
    ]
    (DOCS / "c11_architecture_decision_protocol.md").write_text(
        guard_document("\n".join(lines) + "\n"), encoding="utf-8"
    )


def write_decision_markdown(payload: dict) -> None:
    selection = payload["selection"]
    lines = [
        "# Task C11 - Fuel-Oil Modeling-Architecture Decision",
        "",
        f"*Generated {payload['generated_at_utc']}. "
        f"Config `{payload['config_version']}`.*",
        "",
        f"Decision criteria `{payload['decision_criteria_checksum']}`, frozen",
        "before the candidate designs were built and re-asserted after the",
        "identification audit.",
        "",
        "## The decision",
        "",
        f"**`selected_architecture`: `{selection['selected_architecture']}`**",
        "",
        f"All nine mandatory gates passed: {_flag(selection['all_gates_passed'])}. "
        f"Blocker: `{selection['blocker']}`. "
        f"`expectation_overridden`: {_flag(selection['expectation_overridden'])}.",
        "",
        "> " + selection["reason"],
        "",
        "> " + selection["narrative"],
        "",
        "| gate | passed |",
        "| --- | --- |",
    ]
    for gate, passed in payload["gates"].items():
        lines.append(f"| `{gate}` | {_flag(passed)} |")

    lines += [
        "",
        "## Upstream invariants",
        "",
        f"All reproduced: **{payload['upstream_invariants']['all_reproduced']}** "
        f"({len(payload['upstream_invariants']['checks'])} checks).",
        "",
        "| check | expected | actual |",
        "| --- | --- | --- |",
    ]
    for name, check in payload["upstream_invariants"]["checks"].items():
        lines.append(
            f"| `{name}` | `{_fmt(check['expected'])}` | `{_fmt(check['actual'])}` |"
        )

    lines += [
        "",
        "## The estimand",
        "",
        f"> {payload['estimand']['statement'].strip()}",
        "",
        payload["estimand"]["narrative"],
        "",
        "## Candidate B is Candidate A reparameterised",
        "",
        "| variant | industries | max column-space projector gap | max "
        "per-industry standardised gap | distinct architecture |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for variant_id, report in payload["candidate_b_equivalence"].items():
        lines.append(
            f"| `{variant_id}` | {report['industries_checked']} | "
            f"{_fmt(report['max_column_space_projector_gap'])} | "
            f"{_fmt(report['max_per_industry_standardized_gap'])} | "
            f"{_flag(report['separate_conditioned_model_is_distinct_architecture'])} |"
        )
    lines += [
        "",
        "Within one industry the sector-093 exposure is a positive scalar, so the",
        "two designs span the same column space and differ only in coordinates:",
        "`gamma[g,h,f] = beta[g,h,f] / E[g]`. Candidate B is rejected on that",
        "identity, not on a comparison.",
        "",
    ]

    for variant_id, audit in payload["identification"]["observed"].items():
        collapse = audit["per_industry_standardization_check"]
        constant = audit["constant_exposure_check"]
        invalid = audit["invalid_fixed_effect_coding"]
        lines += [
            f"## Candidate C identification - `{variant_id}`",
            "",
            f"Feature-only panel **{audit['rows']} x {audit['columns']}**: "
            f"{len(audit['column_blocks']['source'])} source, "
            f"{len(audit['column_blocks']['interaction'])} centred interaction, "
            f"{len(audit['column_blocks']['fixed_effects'])} industry fixed "
            "effects, no redundant global intercept.",
            "",
            "| diagnostic | value |",
            "| --- | --- |",
            f"| source block rank | **{audit['source_block_rank']}** |",
            f"| interaction block rank | **{audit['interaction_block_rank']}** |",
            f"| combined source + interaction rank | "
            f"**{audit['combined_source_and_interaction_rank']}** |",
            f"| fixed-effect block rank | {audit['fixed_effect_block_rank']} |",
            f"| full design rank / columns | "
            f"**{audit['full_design_rank']}** / {audit['columns']} |",
            f"| full column rank | "
            f"{_flag(audit['full_design_is_full_column_rank'])} |",
            f"| exact duplicate columns | "
            f"`{audit['exact_duplicate_columns'] or 'none'}` |",
            f"| interaction columns removed by preprocessing | "
            f"{audit['interaction_columns_removed_by_preprocessing']} |",
            f"| centred exposure spread | "
            f"{_fmt(audit['exposure_cross_industry_spread'])} |",
            f"| exposure has nonzero cross-industry variance | "
            f"{_flag(audit['exposure_has_nonzero_cross_industry_variance'])} |",
            "",
            "### What would destroy the heterogeneity",
            "",
            "| construction | result |",
            "| --- | --- |",
            f"| per-industry standardisation, within each industry | combined "
            f"rank falls **{collapse['intended_combined_rank']} -> "
            f"{max(collapse['per_industry_combined_ranks'])}** |",
            f"| per-industry standardisation, stacked | rank stays "
            f"**{collapse['stacked_per_industry_standardized_combined_rank']}** "
            "(both exposure signs span two directions) |",
            f"| interaction blocks that remain distinct | "
            f"**{collapse['distinct_intended_interaction_blocks']} -> "
            f"{collapse['distinct_collapsed_interaction_blocks']}** "
            "(only the sign of the exposure survives) |",
            f"| `sign(e_g) * standardize(xtilde)` identity residual | "
            f"{_fmt(collapse['sign_identity_residual'])} |",
            f"| exposure replaced by a constant | interaction block rank "
            f"**{constant['constant_exposure_interaction_rank']}**, all zero: "
            f"{_flag(constant['all_zero'])} |",
            f"| `{invalid['coding']}` | {invalid['columns']} columns at rank "
            f"**{invalid['rank']}**, rank-deficient: "
            f"{_flag(invalid['rank_deficient'])}, guard raised: "
            f"{_flag(invalid['guard_raised'])} |",
            "",
            "> " + collapse["reason"],
            "",
            "> " + constant["reason"],
            "",
            f"Candidate design checksum `{audit['design_checksum']}`.",
            "",
        ]

    discrepancies = payload["preregistered_expectation_discrepancies"]
    lines += [
        "## Preregistered expectations that did not reproduce",
        "",
        f"{discrepancies['count']} preregistered value(s) did not reproduce. No "
        "preregistered value was rewritten and no expectation was relaxed "
        f"(`preregistered_values_changed`: "
        f"{_flag(discrepancies['preregistered_values_changed'])}, "
        f"`expectations_relaxed_to_obtain_a_pass`: "
        f"{_flag(discrepancies['expectations_relaxed_to_obtain_a_pass'])}).",
        "",
    ]
    if discrepancies["items"]:
        lines += [
            "| variant | field | preregistered | observed |",
            "| --- | --- | ---: | ---: |",
        ]
        for item in discrepancies["items"]:
            lines.append(
                f"| `{item['variant_id']}` | `{item['preregistered_field']}` | "
                f"`{item['preregistered_value']}` | `{item['observed_value']}` |"
            )
        corrected = discrepancies["items"][0]["corrected_measurement"]
        lines += [
            "",
            "> " + discrepancies["items"][0]["explanation"],
            "",
            "**Corrected measurement of the same phenomenon:**",
            "",
            "| measurement | value |",
            "| --- | --- |",
            f"| intended combined rank | {corrected['intended_combined_rank']} |",
            f"| per-industry combined rank after standardisation | "
            f"`{corrected['per_industry_combined_ranks']}` |",
            f"| distinct interaction blocks, intended | "
            f"**{corrected['distinct_intended_interaction_blocks']}** |",
            f"| distinct interaction blocks, collapsed | "
            f"**{corrected['distinct_collapsed_interaction_blocks']}** |",
            f"| `sign(e_g)` identity residual | "
            f"{_fmt(corrected['sign_identity_residual'])} |",
            "",
        ]
    correction = discrepancies["gate_correction"]
    lines += [
        "**A gate implementation was corrected after observation, and that is "
        "recorded rather than absorbed.**",
        "",
        f"`gate_implementation_corrected_after_observation`: "
        f"{_flag(discrepancies['gate_implementation_corrected_after_observation'])}. "
        f"Gate: `{correction['gate']}`.",
        "",
        "> " + correction["what_changed"],
        "",
        "> " + correction["note"],
        "",
    ]

    accounting = payload["accounting"]
    lines += [
        "## Parameter and information accounting",
        "",
        "| quantity | value |",
        "| --- | --- |",
        f"| panel rows | {accounting['panel_rows']} |",
        f"| unique issue months | {accounting['unique_issue_months']} |",
        f"| eligible industries | {accounting['eligible_industries']} |",
        f"| source slopes per horizon | {accounting['source_slopes_per_horizon']} |",
        f"| interaction slopes per horizon | "
        f"{accounting['interaction_slopes_per_horizon']} |",
        f"| industry fixed effects | {accounting['industry_fixed_effects']} "
        f"(redundant global intercept: "
        f"{_flag(accounting['redundant_global_intercept'])}) |",
        f"| total candidate design rank | "
        f"`{accounting['observed_full_design_rank']}` |",
        f"| issue-month clusters | {accounting['observed_issue_month_clusters']} |",
        "",
        "| statement | value |",
        "| --- | --- |",
    ]
    for key in ("cross_sectional_rows_help_identify_exposure_heterogeneity",
                "cross_sectional_rows_create_additional_fuel_oil_histories",
                "overlapping_monthly_transformations_remain",
                "serial_dependence_remains",
                "full_rank_is_evidence_of_predictive_usefulness",
                "parameter_feasibility_equals_statistical_power",
                "p_values_computed", "coefficient_uncertainty_computed",
                "outcome_related_effective_sample_size_computed"):
        lines.append(f"| `{key}` | {_flag(accounting[key])} |")

    lines += ["", "## IND-04", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["ind_04"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines += ["", "## Channel policy", "", "| field | value |", "| --- | --- |"]
    for key in ("co_equal_separate_structural_variants", "primary_channel_selected",
                "structural_basis_for_channel_preference_available",
                "parallel_exploratory_variants_permitted_in_future_design",
                "outcome_based_channel_selection_permitted",
                "simultaneous_channel_entry_permitted",
                "described_as_independent_structural_channels",
                "joint_design_refused"):
        lines.append(f"| `{key}` | {_flag(payload['channels'][key])} |")
    lines += ["", "> " + payload["channels"]["later_evaluation_rule"].strip(), ""]

    lines += [
        "## Transformations",
        "",
        "Retained: "
        + ", ".join(f"`{x}`" for x in payload["transformations"]["retained"]) + ".",
        "",
        f"Removed: `{payload['transformations']['removed'] or 'none'}`. "
        f"`outcome_based_removal_permitted`: "
        f"{_flag(payload['transformations']['outcome_based_removal_permitted'])}. "
        f"Realized volatility remains "
        f"`{payload['transformations']['realized_volatility_interpretation']}`.",
        "",
        "## Availability contract",
        "",
        "| field | value |",
        "| --- | --- |",
    ]
    for key in ("operational_source_lag_months", "lag_basis",
                "operational_lag_is_measured", "source_available_as_of",
                "latest_vintage_source_values", "point_in_time_source_support",
                "structural_available_by", "development_issue_months",
                "purge_issue_months", "locked_issue_months_inaccessible",
                "purge_or_locked_feature_target_rows_materialised"):
        lines.append(f"| `{key}` | `{payload['availability'][key]}` |")

    lines += ["", "## Authorization", "", "| field | value |", "| --- | --- |"]
    for key, value in payload["authorization"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "Selecting an architecture grants no permission to execute it. Every",
        "authorization field above is a separate decision that has not been taken.",
        "",
        "## Lineage",
        "",
        "| reference | value |",
        "| --- | --- |",
    ]
    for key, value in payload["lineage"]["references"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        f"Lineage checksum `{payload['lineage']['lineage_checksum']}`. "
        f"Decision checksum `{payload['decision_checksum']}`. "
        f"Content checksum `{payload['content_checksum']}`.",
        "",
    ]
    (DOCS / "c11_architecture_decision.md").write_text(
        guard_document("\n".join(lines) + "\n"), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
