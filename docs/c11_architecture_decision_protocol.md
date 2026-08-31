# Task C11 - Architecture-Decision Protocol

*Config `fuel_oil_modeling_architecture_v1`, criteria `c11_architecture_criteria_v1`.*

**Frozen decision-criteria checksum:** `0f81513566f98d1d5047dcb298935607f5abdb35510cf0e3c53c1bc6998d8397`

Every criterion below was written before the first candidate design
matrix existed. The runner hashes them, re-asserts the digest before the
designs are built and again after the identification audit, so a gate
rewritten once the ranks are visible raises rather than passing.

## The predictive estimand

> The incremental forecast correction associated with a common national ex-refinery fuel-oil signal, allowing the correction amplitude to vary across industries according to frozen direct purchases from NESDC sector 093.

The estimand is the incremental forecast correction associated with a common national ex-refinery fuel-oil signal, where the amplitude of that correction is allowed to vary across industries according to frozen direct purchases from NESDC sector 093. It is a predictive interaction. The sector-093 coefficient is a structural proxy taken as given, not a quantity this project estimates, and the interaction has no currency reading: the I/O coefficient is stated in purchasers' prices and is import-inclusive, while EPPO measures the ex-refinery stage. If a model is later authorized it would be evaluated on release-lag-aware latest-vintage data, which is not a point-in-time backtest. Nothing here asserts that fuel-oil prices drive industrial stress.

| field | value |
| --- | --- |
| `kind` | `predictive_interaction` |
| `causal_effect` | `False` |
| `estimated_elasticity` | `False` |
| `sector_093_exposure_is_a_structural_proxy` | `True` |
| `monetary_cost_per_unit_of_output` | `False` |
| `io_coefficient_basis` | `purchasers_price_import_inclusive` |
| `eppo_price_stage` | `ex_refinery` |
| `valuation_basis_alignment` | `partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price` |
| `evaluation_basis_if_later_authorized` | `release_lag_aware_latest_vintage` |
| `point_in_time_backtest` | `False` |
| `fuel_oil_determines_industrial_stress` | `False` |
| `requires_exposure_associated_heterogeneity` | `True` |

## Candidate architectures

| candidate | formula | exposure role |
| --- | --- | --- |
| `A_exposure_as_eligibility_gate` | `r[g,t,h] = alpha[g,h] + sum_f beta[g,h,f] * x[t,f]` | `eligibility_and_provenance_only` |
| `B_separate_conditioned_industry_models` | `r[g,t,h] = alpha[g,h] + sum_f gamma[g,h,f] * E[g] * x[t,f]` | `per_industry_positive_scalar` |
| `C_pooled_common_effect_plus_centered_exposure_interaction` | `r[g,t,h] = alpha[g,h] + sum_f beta[h,f] * xtilde[t,f] + sum_f theta[h,f] * ec[g] * xtilde[t,f]` | `centered_cross_industry_interaction` |

## Mandatory gates

1. `matches_the_exposure_heterogeneity_estimand`
2. `exposure_varies_across_eligible_industries`
3. `pooled_interaction_survives_the_specified_preprocessing`
4. `combined_feature_only_design_is_identifiable`
5. `ind_04_excluded_without_conversion_to_zero`
6. `source_channels_remain_separate`
7. `no_outcome_or_model_result_used`
8. `interpretation_remains_predictive_and_non_causal`
9. `availability_and_lineage_intact`

`all_gates_must_pass`: `True`. `expected_selection`: `pooled_common_effect_plus_centered_sector093_interaction`, with `expectation_overrides_a_failed_gate`: `False`.

### Ordering and ties

1. `reject_candidate_b_as_reparameterization`
2. `evaluate_candidate_c_gates`
3. `select_candidate_c_if_every_gate_passes`
4. `otherwise_select_nothing_and_report_the_blocker`

> There is no tie to break. Candidate B is rejected on an algebraic identity rather than a comparison, and Candidate A is retained as a documented alternative rather than ranked against C. If a mandatory gate fails, no architecture is selected; a failed gate is never broken in favour of the expected answer.

## Preprocessing contract (for the future architecture only)

| field | value |
| --- | --- |
| `source_scaling_rule` | `standardize_across_permitted_training_issue_months_only` |
| `source_scaling_ddof` | `0` |
| `permitted_training_issue_months` | `['2024-01', '2025-03']` |
| `exposure_centering_rule` | `subtract_the_mean_of_the_frozen_eligible_industry_exposure_vector` |
| `exposure_centering_universe` | `eleven_eligible_industries` |
| `interaction_per_industry_standardization` | `False` |
| `industry_fixed_effect_coding` | `industry_indicators_no_global_intercept` |
| `redundant_global_intercept` | `False` |

Exposure is time-invariant and structurally available before the
development window, so centring on the complete frozen eleven-industry
vector is not target leakage. Recomputing it from a target, an outcome
or a model fold would be, and the centring source is checked by name.

## Preregistered identification requirements

| field | value |
| --- | --- |
| `rank_tolerance` | `1e-10` |
| `duplicate_column_tolerance` | `1e-12` |
| `expected_panel_rows` | `165` |
| `expected_unique_issue_months` | `15` |
| `expected_eligible_industries` | `11` |
| `expected_source_block_rank` | `5` |
| `expected_interaction_block_rank` | `5` |
| `expected_combined_source_and_interaction_rank` | `10` |
| `expected_full_design_rank` | `21` |

On failure: `select_no_architecture_and_report_the_blocker`.

## C10's fingerprint discrepancy

| field | value |
| --- | --- |
| `rounded_fingerprint_count_fo600` | `11` |
| `absolute_tolerance_equivalence_classes_fo600` | `1` |
| `max_standardized_design_residual_fo600` | `4.385164106834871e-15` |
| `standardization_tolerance` | `1e-09` |
| `equivalence_rule_used_for_the_decision` | `absolute_tolerance_equivalence_class` |
| `rounded_fingerprint_count_used_for_the_decision` | `False` |
| `discrepancy_suppressed` | `False` |
| `c10_rewritten` | `False` |
| `thresholds_changed_after_observation` | `False` |

> The preregistered absolute-tolerance equivalence rule decides. The rounded significant-digit fingerprint count is reported unchanged beside it and is not used as the equivalence rule. C10 is neither rewritten nor suppressed.

## Prohibited inputs

Artifacts: `b3_target_values`, `forecast_target_raw`, `production_stress_month`, `industry_month_targets`, `industry_month_panel_with_target_outcomes`, `b4_walk_forward_predictions`, `d1_development_predictions`, `d1_development_results`, `d3_operational_baseline_results`, `d3_operational_predictions`, `d4_operational_model_predictions`, `d4_operational_model_results`, `locked_test_outcomes`.

Statistics: `mae`, `rmse`, `predictive_performance`, `high_stress_outcome_rate`, `correlation_with_a_target`, `coefficient_estimate`, `p_value`, `confidence_interval`.

