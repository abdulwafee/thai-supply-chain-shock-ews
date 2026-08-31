# Task C11 - Fuel-Oil Modeling-Architecture Decision

*Generated 2026-08-30T01:24:26.741496+00:00. Config `fuel_oil_modeling_architecture_v1`.*

Decision criteria `0f81513566f98d1d5047dcb298935607f5abdb35510cf0e3c53c1bc6998d8397`, frozen
before the candidate designs were built and re-asserted after the
identification audit.

## The decision

**`selected_architecture`: `pooled_common_effect_plus_centered_sector093_interaction`**

All nine mandatory gates passed: `True`. Blocker: `None`. `expectation_overridden`: `False`.

> All nine mandatory gates passed. Candidate B is rejected as a coefficient reparameterisation of Candidate A rather than compared against it, and Candidate A is retained as a documented alternative that does not meet the exposure-heterogeneity estimand.

> Within a single industry the sector-093 exposure is a positive scalar, so Candidate B spans exactly the same column space as Candidate A and is a coefficient reparameterisation rather than a second architecture. In a pooled panel the same product varies across industry and time, so the centred interaction is not proportional to the main effect and can carry a constrained cross-industry slope pattern. That change of dimension, not of scale, is the whole basis for the selection.

| gate | passed |
| --- | --- |
| `matches_the_exposure_heterogeneity_estimand` | `True` |
| `exposure_varies_across_eligible_industries` | `True` |
| `pooled_interaction_survives_the_specified_preprocessing` | `True` |
| `combined_feature_only_design_is_identifiable` | `True` |
| `ind_04_excluded_without_conversion_to_zero` | `True` |
| `source_channels_remain_separate` | `True` |
| `no_outcome_or_model_result_used` | `True` |
| `interpretation_remains_predictive_and_non_causal` | `True` |
| `availability_and_lineage_intact` | `True` |

## Upstream invariants

All reproduced: **True** (31 checks).

| check | expected | actual |
| --- | --- | --- |
| `c10_content_checksum` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` |
| `c10_content_checksum_recomputes` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` |
| `c10_diagnostic_contract_checksum` | `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041` | `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041` |
| `c9_phase_a_checksum` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` |
| `c10_variants` | `['fo1500_direct_sector093', 'fo600_direct_sector093']` | `['fo1500_direct_sector093', 'fo600_direct_sector093']` |
| `c10_rows_per_variant` | `[180]` | `[180]` |
| `c10_columns_per_variant` | `[5]` | `[5]` |
| `c10_numeric_cells_per_variant` | `[825]` | `[825]` |
| `c10_masked_cells_per_variant` | `[75]` | `[75]` |
| `c10_unique_issue_months` | `[15]` | `[15]` |
| `c10_eligible_industries` | `[11]` | `[11]` |
| `c10_masked_industries` | `[('IND-04',)]` | `[('IND-04',)]` |
| `c10_source_time_rank` | `[5]` | `[5]` |
| `c10_stacked_panel_rank` | `[5]` | `[5]` |
| `c10_cross_sectional_rank` | `[1]` | `[1]` |
| `c10_raw_industry_designs` | `[11]` | `[11]` |
| `c10_normalized_equivalence_classes` | `[1]` | `[1]` |
| `c10_standardized_equivalence_classes` | `[1]` | `[1]` |
| `c10_conditioning_adds_cross_industry_scale` | `True` | `True` |
| `c10_conditioning_adds_temporal_degrees_of_freedom` | `False` | `False` |
| `c10_per_industry_standardization_removes_exposure_scale` | `True` | `True` |
| `c10_target_joined` | `False` | `False` |
| `c10_model_trained` | `False` | `False` |
| `c10_channel_selected` | `False` | `False` |
| `c10_model_feature_approved` | `False` | `False` |
| `c10_locked_test_accessed` | `False` | `False` |
| `c10_rounded_fingerprint_fo600` | `11` | `11` |
| `c10_rounded_fingerprint_fo1500` | `1` | `1` |
| `c10_tolerance_classes_fo600` | `1` | `1` |
| `c10_standardized_residual_fo600` | `4.385e-15` | `4.385e-15` |
| `c10_thresholds_unchanged_after_observation` | `False` | `False` |

## The estimand

> The incremental forecast correction associated with a common national ex-refinery fuel-oil signal, allowing the correction amplitude to vary across industries according to frozen direct purchases from NESDC sector 093.

The estimand is the incremental forecast correction associated with a common national ex-refinery fuel-oil signal, where the amplitude of that correction is allowed to vary across industries according to frozen direct purchases from NESDC sector 093. It is a predictive interaction. The sector-093 coefficient is a structural proxy taken as given, not a quantity this project estimates, and the interaction has no currency reading: the I/O coefficient is stated in purchasers' prices and is import-inclusive, while EPPO measures the ex-refinery stage. If a model is later authorized it would be evaluated on release-lag-aware latest-vintage data, which is not a point-in-time backtest. Nothing here asserts that fuel-oil prices drive industrial stress.

## Candidate B is Candidate A reparameterised

| variant | industries | max column-space projector gap | max per-industry standardised gap | distinct architecture |
| --- | ---: | ---: | ---: | --- |
| `fo1500_direct_sector093` | 11 | 4.441e-16 | 4.441e-16 | `False` |
| `fo600_direct_sector093` | 11 | 6.523e-16 | 4.441e-16 | `False` |

Within one industry the sector-093 exposure is a positive scalar, so the
two designs span the same column space and differ only in coordinates:
`gamma[g,h,f] = beta[g,h,f] / E[g]`. Candidate B is rejected on that
identity, not on a comparison.

## Candidate C identification - `fo1500_direct_sector093`

Feature-only panel **165 x 21**: 5 source, 5 centred interaction, 11 industry fixed effects, no redundant global intercept.

| diagnostic | value |
| --- | --- |
| source block rank | **5** |
| interaction block rank | **5** |
| combined source + interaction rank | **10** |
| fixed-effect block rank | 11 |
| full design rank / columns | **21** / 21 |
| full column rank | `True` |
| exact duplicate columns | `none` |
| interaction columns removed by preprocessing | 0 |
| centred exposure spread | 0.059408 |
| exposure has nonzero cross-industry variance | `True` |

### What would destroy the heterogeneity

| construction | result |
| --- | --- |
| per-industry standardisation, within each industry | combined rank falls **10 -> 5** |
| per-industry standardisation, stacked | rank stays **10** (both exposure signs span two directions) |
| interaction blocks that remain distinct | **11 -> 2** (only the sign of the exposure survives) |
| `sign(e_g) * standardize(xtilde)` identity residual | 4.441e-16 |
| exposure replaced by a constant | interaction block rank **0**, all zero: `True` |
| `global_intercept_plus_industry_indicators` | 22 columns at rank **21**, rank-deficient: `True`, guard raised: `True` |

> Within industry g the interaction is e_g * xtilde, so per-industry standardisation returns sign(e_g) * standardize(xtilde) and that industry's combined block falls to rank 5 from 10. Stacking the industries does NOT show a global rank drop, because the centred exposures carry both signs and +xtilde and -xtilde span two directions. What is destroyed is the magnitude: 11 distinct exposure-proportional interaction blocks collapse to 2 sign groups. The preprocessing contract therefore forbids standardising the interaction inside an industry.

> A constant exposure centres to zero for every industry, so the interaction block is identically zero. Reporting it as identifying slope heterogeneity would describe a column of zeros as evidence.

Candidate design checksum `6807f4ca258b43bde4e4fced4cfddf1f53dccc350ccdeecb690f50fa4f4688a9`.

## Candidate C identification - `fo600_direct_sector093`

Feature-only panel **165 x 21**: 5 source, 5 centred interaction, 11 industry fixed effects, no redundant global intercept.

| diagnostic | value |
| --- | --- |
| source block rank | **5** |
| interaction block rank | **5** |
| combined source + interaction rank | **10** |
| fixed-effect block rank | 11 |
| full design rank / columns | **21** / 21 |
| full column rank | `True` |
| exact duplicate columns | `none` |
| interaction columns removed by preprocessing | 0 |
| centred exposure spread | 0.059408 |
| exposure has nonzero cross-industry variance | `True` |

### What would destroy the heterogeneity

| construction | result |
| --- | --- |
| per-industry standardisation, within each industry | combined rank falls **10 -> 5** |
| per-industry standardisation, stacked | rank stays **10** (both exposure signs span two directions) |
| interaction blocks that remain distinct | **11 -> 2** (only the sign of the exposure survives) |
| `sign(e_g) * standardize(xtilde)` identity residual | 4.441e-16 |
| exposure replaced by a constant | interaction block rank **0**, all zero: `True` |
| `global_intercept_plus_industry_indicators` | 22 columns at rank **21**, rank-deficient: `True`, guard raised: `True` |

> Within industry g the interaction is e_g * xtilde, so per-industry standardisation returns sign(e_g) * standardize(xtilde) and that industry's combined block falls to rank 5 from 10. Stacking the industries does NOT show a global rank drop, because the centred exposures carry both signs and +xtilde and -xtilde span two directions. What is destroyed is the magnitude: 11 distinct exposure-proportional interaction blocks collapse to 2 sign groups. The preprocessing contract therefore forbids standardising the interaction inside an industry.

> A constant exposure centres to zero for every industry, so the interaction block is identically zero. Reporting it as identifying slope heterogeneity would describe a column of zeros as evidence.

Candidate design checksum `cd28fc267f197a6ee240f9eece2c8049535b8c4224f46e957a756c69aeb972ed`.

## Preregistered expectations that did not reproduce

2 preregistered value(s) did not reproduce. No preregistered value was rewritten and no expectation was relaxed (`preregistered_values_changed`: `False`, `expectations_relaxed_to_obtain_a_pass`: `False`).

| variant | field | preregistered | observed |
| --- | --- | ---: | ---: |
| `fo1500_direct_sector093` | `expected_per_industry_standardized_combined_rank` | `5` | `10` |
| `fo600_direct_sector093` | `expected_per_industry_standardized_combined_rank` | `5` | `10` |

> The preregistered number measured the STACKED rank, and the stacked rank cannot see this collapse. Per-industry standardisation maps e_g*xtilde to sign(e_g)*xtilde, so each industry's combined block does fall from rank 10 to rank 5; but the centred exposures carry both signs, so +xtilde and -xtilde span two directions and the stacked rank stays 10. What is destroyed is the magnitude: eleven distinct exposure-proportional interaction blocks collapse to two sign groups, so theta could be identified only up to a two-group split. The per-industry rank and the distinct-block count are the correct measurements and both confirm the collapse.

**Corrected measurement of the same phenomenon:**

| measurement | value |
| --- | --- |
| intended combined rank | 10 |
| per-industry combined rank after standardisation | `[5]` |
| distinct interaction blocks, intended | **11** |
| distinct interaction blocks, collapsed | **2** |
| `sign(e_g)` identity residual | 4.441e-16 |

**A gate implementation was corrected after observation, and that is recorded rather than absorbed.**

`gate_implementation_corrected_after_observation`: `True`. Gate: `pooled_interaction_survives_the_specified_preprocessing`.

> The gate originally required the per-industry-standardisation COUNTERFACTUAL to show a stacked rank drop. That made a gate about the specified preprocessing depend on a construction the preprocessing contract forbids. It now tests the specified preprocessing only: the interaction block is present at its expected rank, the combined rank is the sum of the two block ranks, per-industry standardisation is not applied, and a constant exposure would be detected as a rank-zero interaction.

> The correction was made after observing the result and is recorded as such. It is reported here rather than absorbed silently, because a gate edited after a failure is exactly the pattern this project treats as suspect.

## Parameter and information accounting

| quantity | value |
| --- | --- |
| panel rows | 165 |
| unique issue months | 15 |
| eligible industries | 11 |
| source slopes per horizon | 5 |
| interaction slopes per horizon | 5 |
| industry fixed effects | 11 (redundant global intercept: `False`) |
| total candidate design rank | `{'fo1500_direct_sector093': 21, 'fo600_direct_sector093': 21}` |
| issue-month clusters | 15 |

| statement | value |
| --- | --- |
| `cross_sectional_rows_help_identify_exposure_heterogeneity` | `True` |
| `cross_sectional_rows_create_additional_fuel_oil_histories` | `False` |
| `overlapping_monthly_transformations_remain` | `True` |
| `serial_dependence_remains` | `True` |
| `full_rank_is_evidence_of_predictive_usefulness` | `False` |
| `parameter_feasibility_equals_statistical_power` | `False` |
| `p_values_computed` | `False` |
| `coefficient_uncertainty_computed` | `False` |
| `outcome_related_effective_sample_size_computed` | `False` |

## IND-04

| field | value |
| --- | --- |
| `industry_id` | `IND-04` |
| `direction_channel` | `mixed_or_ambiguous` |
| `direction_multiplier` | `None` |
| `excluded_from_fuel_oil_correction` | `True` |
| `exclusion_reason` | `direction_is_mixed_not_zero_exposure` |
| `retains_operational_benchmark_prediction` | `True` |
| `fuel_oil_residual_correction` | `structurally_unavailable` |
| `converted_to_observed_zero` | `False` |
| `used_to_estimate_the_cost_pressure_interaction` | `False` |
| `visible_in_audit_and_prediction_reconciliation` | `True` |
| `silently_dropped_from_evaluation_denominators` | `False` |
| `direction_forced_to_plus_one` | `False` |

## Channel policy

| field | value |
| --- | --- |
| `co_equal_separate_structural_variants` | `True` |
| `primary_channel_selected` | `False` |
| `structural_basis_for_channel_preference_available` | `False` |
| `parallel_exploratory_variants_permitted_in_future_design` | `True` |
| `outcome_based_channel_selection_permitted` | `False` |
| `simultaneous_channel_entry_permitted` | `False` |
| `described_as_independent_structural_channels` | `False` |
| `joint_design_refused` | `True` |

> A later development task that evaluates both must report them separately and must not promote the better result as a confirmatory channel selection.

## Transformations

Retained: `price_level`, `log_change_1m_pct`, `log_change_3m_pct`, `log_change_12m_pct`, `realized_volatility_3m_pct`.

Removed: `none`. `outcome_based_removal_permitted`: `False`. Realized volatility remains `nonnegative_disruption_magnitude`.

## Availability contract

| field | value |
| --- | --- |
| `operational_source_lag_months` | `2` |
| `lag_basis` | `conservative_policy_not_historical_measurement` |
| `operational_lag_is_measured` | `False` |
| `source_available_as_of` | `None` |
| `latest_vintage_source_values` | `True` |
| `point_in_time_source_support` | `False` |
| `structural_available_by` | `2020-03-31` |
| `development_issue_months` | `['2024-01', '2025-03']` |
| `purge_issue_months` | `['2025-04', '2025-06']` |
| `locked_issue_months_inaccessible` | `True` |
| `purge_or_locked_feature_target_rows_materialised` | `False` |

## Authorization

| field | value |
| --- | --- |
| `architecture_selected_from_outcomes` | `False` |
| `predictive_estimand_defined` | `True` |
| `primary_channel_selected` | `False` |
| `target_values_read` | `False` |
| `target_joined` | `False` |
| `model_fitted` | `False` |
| `predictive_performance_computed` | `False` |
| `locked_test_accessed` | `False` |
| `model_feature_approved` | `False` |
| `target_join_authorized` | `False` |
| `development_modeling_authorized` | `False` |
| `locked_test_evaluation_authorized` | `False` |
| `modeling_architecture_selected` | `pooled_common_effect_plus_centered_sector093_interaction` |
| `pooled_exposure_interaction_identifiable` | `True` |
| `separate_conditioned_architecture_rejected_as_reparameterization` | `True` |

Selecting an architecture grants no permission to execute it. Every
authorization field above is a separate decision that has not been taken.

## Lineage

| reference | value |
| --- | --- |
| `c10_content_checksum` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` |
| `c10_diagnostic_contract_checksum` | `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041` |
| `c9_phase_a_checksum` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` |
| `c9_conditioned_lineage_version` | `c9_fuel_oil_direct_sector093_v1` |
| `c8_transformation_formula_version` | `c8_eppo_fuel_oil_transformations_v1` |
| `c7_5_semantic_checksum` | `8b36fd6e9ce7798905cb2b903b263908489a5632fdf54f41ba12b0a12b6bd24a` |
| `sector_093_exposure_vector_checksum` | `94a6f07df433e101747d45ec50e4ab1caaa6fcb7d320db7308c2eeb742c824bb` |
| `nesdc_workbook_sha256` | `7da4b4dca118af760844abd6c78ae01a83f313c8898321ac69e72be730e93c81` |
| `industry_crosswalk_version` | `c3_industry_exposure_v1` |
| `structural_available_month` | `2020-03` |
| `candidate_design_formula_version` | `c11_fuel_oil_candidate_design_v1` |
| `exposure_centering_rule` | `subtract_the_mean_of_the_frozen_eligible_industry_exposure_vector` |
| `source_scaling_rule` | `standardize_across_permitted_training_issue_months_only` |
| `industry_fixed_effect_coding` | `industry_indicators_no_global_intercept` |
| `channel_separation_policy` | `co_equal_separate_variants_never_combined` |

Lineage checksum `73a3b1e6f680e2ea2be1f9f50d5fbcb7b21e53d0064dcfee222c725b49e33a4b`. Decision checksum `001b1d901311c1da0de1e707ca10a97f91e54584b21e52ee8c943421fc068403`. Content checksum `6d525648f0e7e30860dc065c17a896426a0cf008f7ef62096974d4954c9f6d77`.

