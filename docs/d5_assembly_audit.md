# Task D5 - Assembly Audit

*Generated 2026-08-30T02:26:29.047289+00:00. Config `d5_fuel_oil_interaction_v1`.*

Frozen protocol `13a0b1846df33f2d81eae8be8415b66bdeaef1bb20642e0a07645774c624483a`, verified from disk before the guarded target reader opened.

## The two-phase boundary

| field | value |
| --- | --- |
| `protocol_checksum` | `13a0b1846df33f2d81eae8be8415b66bdeaef1bb20642e0a07645774c624483a` |
| `protocol_verified_before_any_target_read` | `True` |
| `target_reads` | `720` |
| `target_reads_before_prediction_freeze` | `0` |
| `predictions_frozen` | `720` |

`target_reads_before_prediction_freeze` is the count that matters: every
observed value was read only after its prediction was final.

## Upstream invariants

All reproduced: **True** (29 checks).

| check | expected | actual |
| --- | --- | --- |
| `authorization.d5_protocol_preregistration_authorized` | `True` | `True` |
| `authorization.d5_development_target_join_authorized` | `True` | `True` |
| `authorization.d5_exploratory_modeling_authorized` | `True` | `True` |
| `authorization.d5_channel_selection_authorized` | `False` | `False` |
| `authorization.d5_confirmatory_claims_authorized` | `False` | `False` |
| `authorization.d5_purge_evaluation_authorized` | `False` | `False` |
| `authorization.d5_locked_test_evaluation_authorized` | `False` | `False` |
| `c11r1_content_checksum` | `a536dbb85444add1051e589e170bcc10756ff335ba1283723ac1644b4d36dbca` | `a536dbb85444add1051e589e170bcc10756ff335ba1283723ac1644b4d36dbca` |
| `c11r1_governance_checksum` | `81f18e8ad449283105ca6e0e8e6324280a4aaa4c6684e0f69635945c1c3a1851` | `81f18e8ad449283105ca6e0e8e6324280a4aaa4c6684e0f69635945c1c3a1851` |
| `c11_content_checksum` | `6d525648f0e7e30860dc065c17a896426a0cf008f7ef62096974d4954c9f6d77` | `6d525648f0e7e30860dc065c17a896426a0cf008f7ef62096974d4954c9f6d77` |
| `c11_decision_checksum` | `001b1d901311c1da0de1e707ca10a97f91e54584b21e52ee8c943421fc068403` | `001b1d901311c1da0de1e707ca10a97f91e54584b21e52ee8c943421fc068403` |
| `c11_selected_architecture` | `pooled_common_effect_plus_centered_sector093_interaction` | `pooled_common_effect_plus_centered_sector093_interaction` |
| `c11_architecture_status` | `exploratory_supported_after_documented_specification_correction` | `exploratory_supported_after_documented_specification_correction` |
| `c11_source_block_rank` | `[5]` | `[5]` |
| `c11_interaction_block_rank` | `[5]` | `[5]` |
| `c11_combined_source_and_interaction_rank` | `[10]` | `[10]` |
| `c11_full_design_rank` | `[21]` | `[21]` |
| `c11_full_design_columns` | `[21]` | `[21]` |
| `c11_candidate_b_is_distinct` | `False` | `False` |
| `c10_content_checksum` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` |
| `c10_diagnostic_contract_checksum` | `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041` | `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041` |
| `c10_unique_issue_months` | `[15]` | `[15]` |
| `c10_eligible_feature_rows_per_variant` | `[165]` | `[165]` |
| `c10_masked_ind_04_rows_per_variant` | `[15]` | `[15]` |
| `c9_phase_a_checksum` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` |
| `c9_eligible_industries` | `11` | `11` |
| `c9_ind_04_eligible` | `False` | `False` |
| `c9_ind_04_direction` | `mixed_or_ambiguous` | `mixed_or_ambiguous` |
| `c9_variants` | `['fo1500_direct_sector093', 'fo600_direct_sector093']` | `['fo1500_direct_sector093', 'fo600_direct_sector093']` |

## Prediction counts

| quantity | expected | observed |
| --- | ---: | ---: |
| total predictions | 720 | **720** |
| distinct canonical keys | 720 | **720** |
| pooled-model predictions | 660 | **660** |
| IND-04 benchmark passthrough | 60 | **60** |
| distinct lineage checksums | 720 | **720** |

Reconciled: **True**.

## Training-count reconciliation

| variant | h | outer issue | issues | expected | eligible rows | expected | all-industry | expected | ok |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `fo1500_direct_sector093` | 1 | `2024-01` | 21 | 21 | 231 | 231 | 252 | 252 | `True` |
| `fo1500_direct_sector093` | 1 | `2025-03` | 35 | 35 | 385 | 385 | 420 | 420 | `True` |
| `fo1500_direct_sector093` | 3 | `2024-01` | 18 | 18 | 198 | 198 | 216 | 216 | `True` |
| `fo1500_direct_sector093` | 3 | `2025-03` | 32 | 32 | 352 | 352 | 384 | 384 | `True` |
| `fo600_direct_sector093` | 1 | `2024-01` | 21 | 21 | 231 | 231 | 252 | 252 | `True` |
| `fo600_direct_sector093` | 1 | `2025-03` | 35 | 35 | 385 | 385 | 420 | 420 | `True` |
| `fo600_direct_sector093` | 3 | `2024-01` | 18 | 18 | 198 | 198 | 216 | 216 | `True` |
| `fo600_direct_sector093` | 3 | `2025-03` | 32 | 32 | 352 | 352 | 384 | 384 | `True` |

Exclusions are counted separately, because *not enough price history* and
*not enough stress history* are different facts and one total would hide
which is binding. At the first outer issue: 2 issues lacked a complete five-transformation feature row, 0 lacked operational benchmark history.

Maximum normal-equation residual across all fits: 8.882e-16.

## Exposure preprocessing

| industry | raw sector-093 exposure | centred | scaled |
| --- | ---: | ---: | ---: |
| `IND-01` | 0.008556 | -0.009271 | -0.540653 |
| `IND-02` | 0.011393 | -0.006434 | -0.375171 |
| `IND-03` | 0.010065 | -0.007762 | -0.452624 |
| `IND-05` | 0.064156 | 0.046329 | 2.701653 |
| `IND-06` | 0.014321 | -0.003506 | -0.204468 |
| `IND-07` | 0.034648 | 0.016821 | 0.980926 |
| `IND-08` | 0.026906 | 0.009079 | 0.529460 |
| `IND-09` | 0.005071 | -0.012756 | -0.743871 |
| `IND-10` | 0.007521 | -0.010306 | -0.600983 |
| `IND-11` | 0.008711 | -0.009116 | -0.531588 |
| `IND-12` | 0.004748 | -0.013079 | -0.762681 |

Mean 0.017827, structural standard deviation 0.017148, centring universe `eleven_eligible_industries` from `c9_phase_a_frozen_decision_table`. Fitted on targets: `False`. Changes the C11 estimand: `False`.

## IND-04

| field | value |
| --- | --- |
| `industry_id` | `IND-04` |
| `fuel_oil_predictors_created` | `False` |
| `industry_fixed_effect_fitted` | `False` |
| `residual_correction` | `0.0` |
| `final_prediction_equals_registered_benchmark` | `True` |
| `prediction_source` | `benchmark_passthrough_direction_ambiguous` |
| `in_primary_twelve_industry_denominator` | `True` |
| `structural_exclusion_lineage_preserved` | `True` |
| `described_as_a_fitted_zero_coefficient` | `False` |
| `converted_to_structural_zero` | `False` |
| `dropped_from_evaluation` | `False` |

## Lineage

720 predictions carry a checksum, 720 distinct, over 16 required references.

* `d5_protocol_checksum`
* `c11r1_authorization_checksum`
* `c11_architecture_checksum`
* `c10_design_matrix_checksum`
* `c9_conditioned_feature_row`
* `c8_transformation_lineage`
* `sector_093_exposure_and_centering_scaling_rule`
* `training_issue_keys`
* `scaler_statistics`
* `penalty_specification`
* `fitted_coefficient_checksum`
* `benchmark_lineage`
* `calibrator_cutoff`
* `label_availability_cutoff`
* `prediction_clipping_state`
* `ind_04_passthrough_reason`

## Scope

| field | value |
| --- | --- |
| `evaluation_scope` | `development_only` |
| `confirmatory_evaluation` | `False` |
| `latest_vintage_evaluation` | `True` |
| `fully_real_time_backtest` | `False` |
| `channel_selected` | `False` |
| `target_joined_for_authorized_development_evaluation` | `True` |
| `model_trained_for_authorized_development_evaluation` | `True` |
| `purge_evaluated` | `False` |
| `locked_test_accessed` | `False` |
| `locked_test_evaluation_authorized` | `False` |
| `model_feature_approved` | `False` |

Content checksum `77877c1dac708cb8d573aabd43253887b8295d4227c8f34f34e48e83f5258396`.

