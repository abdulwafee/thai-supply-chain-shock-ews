# Task C12 - EPPO Fuel-Oil Modeling-Channel Closure

*Generated 2026-08-30T08:02:30.372046+00:00. Config `fuel_oil_channel_closure_v1`.*

**Channel `eppo_sector093_fuel_oil` is `closed_after_registered_development_evaluation`.**

Conclusion: **`incremental_signal_not_demonstrated_in_registered_development_evaluation`**

The registered development evaluation did not demonstrate incremental signal for either fuel-oil variant at either horizon. No point estimate beat its benchmark, every paired interval straddled zero, and event safety failed in all four cases. Fifteen issue-month clusters cannot settle the question either way, so this is a failure to demonstrate rather than a demonstration of failure. The preregistered stop rule nevertheless supports closing further investment in this channel: that is a project-governance decision about where to spend effort, and it is not a population-level scientific conclusion.

The closure applies to **predictive modeling use**. It does not
invalidate or delete the EPPO archive, the semantic decisions, the
transformations, the structural exposure or any provenance artifact.

## 1. Terminal D5 evidence

Reproduced from the frozen artifacts: **True** (46 checks). `metrics_recomputed_in_c12`: `False`, `d5_rerun_in_c12`: `False`.

| variant | h | model macro MAE | benchmark | paired 95% interval | MAE evidence | event safety | status |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| `fo1500_direct_sector093` | 1 | 17.111 | 17.094 | [-0.822, 0.847] | inconclusive | `False` | inconclusive |
| `fo1500_direct_sector093` | 3 | 18.210 | 16.634 | [-0.096, 3.589] | inconclusive | `False` | inconclusive |
| `fo600_direct_sector093` | 1 | 17.167 | 17.094 | [-0.761, 0.907] | inconclusive | `False` | inconclusive |
| `fo600_direct_sector093` | 3 | 18.207 | 16.634 | [-0.016, 3.525] | inconclusive | `False` | inconclusive |

| aggregate | value |
| --- | ---: |
| `model_worse_than_benchmark_on_point_estimate` | `4` |
| `paired_intervals_including_zero` | `4` |
| `event_safety_gates_failed` | `4` |
| `variant_horizons_evaluated` | `4` |
| `h1_benchmark_false_negatives` | `8` |
| `any_result_reached_supported` | `False` |
| `prediction_rows` | `720` |
| `modeled_predictions` | `660` |
| `ind_04_benchmark_passthrough` | `60` |
| `variants_combined` | `False` |
| `variant_selected` | `False` |
| `purge_evaluated` | `False` |
| `locked_test_accessed` | `False` |
| `protocol_frozen_before_target_access` | `True` |
| `target_reads_before_prediction_freeze` | `0` |
| `confirmatory_evaluation` | `False` |
| `h1_model_false_negatives` | `{'fo600_direct_sector093': 11, 'fo1500_direct_sector093': 11}` |

## 2. What this conclusion does and does not say

| field | value |
| --- | --- |
| `development_evidence_is_inconclusive_not_proof_of_absence` | `True` |
| `point_estimates_provide_no_positive_development_support` | `True` |
| `event_safety_fails_in_all_four_registered_evaluations` | `True` |
| `fifteen_issue_month_clusters_limit_uncertainty_resolution` | `True` |
| `preregistered_stop_rule_supports_closing_further_investment` | `True` |
| `closure_is_a_project_governance_decision` | `True` |
| `closure_is_a_population_level_scientific_conclusion` | `False` |
| `absence_of_effect_proven` | `False` |

Prohibited conclusions, refused by name: `fuel_oil_has_no_effect`, `fuel_oil_is_unrelated_to_industrial_stress`, `null_hypothesis_proven`, `structural_exposure_is_invalid`, `EPPO_data_is_invalid`, `no_predictive_relationship_exists`.

## 3. The evidence chain

C10 established a design limitation - the industry conditioning contributes cross-industry scale and no temporal degrees of freedom - as a property of the design matrix, without reading any target. That is not the same as showing the channel carries nothing. D5 supplied the development evidence, and D5 was inconclusive. Attributing the closure to C10 alone would overstate what a rank identity can establish, and attributing it to D5 alone would lose the reason the architecture was constrained to begin with.

### C7/C7/5

| field | value |
| --- | --- |
| `source_documents_remain_valid` | `True` |
| `semantic_mapping_remains_valid` | `True` |
| `latest_vintage_values` | `True` |
| `publication_timing_basis` | `policy_not_historically_measured` |
| `fo600_and_fo1500_are_distinct_products` | `True` |
| `fo600_and_fo1500_remain_separate_variants` | `True` |

### C8

| field | value |
| --- | --- |
| `five_source_transformations_constructed_correctly` | `True` |
| `missing_source_months_propagated_without_imputation` | `True` |
| `source_level_transformation_validity_unchanged` | `True` |

### C9

| field | value |
| --- | --- |
| `sector_093_exposure_constructed_correctly` | `True` |
| `exposure_is_a_broad_refinery_product_proxy` | `True` |
| `exposure_is_product_specific_fuel_oil_consumption` | `False` |
| `valuation_basis_alignment` | `partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price` |
| `ind_04_direction_ambiguous` | `True` |

### C10

| field | value |
| --- | --- |
| `industry_conditioned_histories_are_scalar_copies_of_one_source_time_matrix` | `True` |
| `conditioning_adds_cross_industry_scale` | `True` |
| `conditioning_adds_temporal_degrees_of_freedom` | `False` |
| `per_industry_standardization_removes_exposure_magnitude` | `True` |
| `c10_alone_demonstrates_predictive_uselessness` | `False` |

### C11/C11R1

| field | value |
| --- | --- |
| `selected_architecture` | `pooled_common_effect_plus_centered_sector093_interaction` |
| `preserves_exposure_associated_heterogeneity` | `True` |
| `mathematical_identification_supported` | `True` |
| `selection_status` | `exploratory_supported_after_documented_specification_correction` |
| `alternative_architecture_authorized_from_development_outcomes` | `False` |

### D5

| field | value |
| --- | --- |
| `selected_architecture_demonstrated_improvement` | `False` |
| `any_variant_horizon_point_estimate_beat_the_benchmark` | `False` |
| `uncertainty_intervals_inconclusive` | `True` |
| `event_safety_failed_everywhere` | `True` |

> C10 established that the industry conditioning contributes cross-industry scale and no temporal degrees of freedom - a property of the design matrix, established without reading any target. It did not and could not show that the channel has no predictive value. D5 is what supplied the development evidence, and D5's evidence is inconclusive rather than negative.

## 4. The closure decision

Applied identically to both variants: `True`. Either variant labelled preferred, primary or less bad: `False`.

| field | value |
| --- | --- |
| `channel_id` | `eppo_sector093_fuel_oil` |
| `variants` | `['fo600_direct_sector093', 'fo1500_direct_sector093']` |
| `channel_status` | `closed_after_registered_development_evaluation` |
| `development_evidence_status` | `incremental_signal_not_demonstrated` |
| `carried_forward_to_operational_modeling` | `False` |
| `development_candidate_supported` | `False` |
| `model_feature_approved` | `False` |
| `confirmatory_claim_authorized` | `False` |
| `purge_evaluation_authorized` | `False` |
| `locked_test_evaluation_authorized` | `False` |
| `locked_test_should_be_opened_for_this_channel` | `False` |
| `additional_model_grid_authorized` | `False` |
| `channel_selection_authorized` | `False` |
| `source_pipeline_remains_valid` | `True` |
| `structural_audit_remains_valid` | `True` |
| `absence_of_effect_proven` | `False` |

Closure checksum `33991fe41a242e5f202fdcb4c67965c2765ade10c1370c3e56b99ccc4f866657`.

## 5. Preservation

Every artifact from C7 through D5 is preserved unchanged and pinned here. Preservation supports audit and portfolio reproducibility; it does not imply continued modeling eligibility, and the existing runners remain able to reproduce their historical outputs under their own frozen contracts.

**19** artifacts pinned, **0** deleted, **0** modified. `preservation_implies_continued_modeling_eligibility`: `False`.

| artifact | content checksum |
| --- | --- |
| `c7_eppo_full_archive_audit` | `79f8d35579c14e8d16eea868a837e12d21f6c42162cf09d41057865648953a7d` |
| `c7_5_eppo_semantic_decision` | `8b36fd6e9ce7798905cb2b903b263908489a5632fdf54f41ba12b0a12b6bd24a` |
| `c8_eppo_transformation_audit` | `89195c01ba56b0b30c6bcd68eb9af069bf80da49da1192b03b899445379c46fe` |
| `c9_sector093_exposure_decision` | `8cb4209b8c93f9d1f478452791dfda25bfbc9b73ec148aee2d6773de431373e1` |
| `c9_fuel_oil_conditioning_audit` | `711461e78ff83048b13ed4852211fccd6008f87dfd4276312a2b26754064527e` |
| `c10_design_matrix_audit` | `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c` |
| `c11_architecture_decision` | `6d525648f0e7e30860dc065c17a896426a0cf008f7ef62096974d4954c9f6d77` |
| `c11r1_governance_decision` | `a536dbb85444add1051e589e170bcc10756ff335ba1283723ac1644b4d36dbca` |
| `d5_assembly_audit` | `77877c1dac708cb8d573aabd43253887b8295d4227c8f34f34e48e83f5258396` |
| `d5_development_results` | `0eb3d613d34fdde2274a56c2bcd97695b652991da663ce6390b70d9e53deaf0e` |

| generated table | byte checksum |
| --- | --- |
| `docs/d5_frozen_protocol.json` | `22e37b46693d4934432aa19da80888b9fe7304a2f7ecf39f3639601768113198` |
| `data/interim/c7_eppo_daily_prices.parquet` | `1b77aa7fb370716adebf0dc1ab54fb174df96545b25352802c1ddfb1b3bd07f5` |
| `data/interim/c7_eppo_monthly_source.parquet` | `97c484da0e290827f623a9e50c7d3769724e9b872006cf491b85f4e6f5f666f5` |
| `data/interim/c7_5_eppo_monthly_semantic.parquet` | `16e9747c5b2c1315cb6c1977321270e44bf0548fdf2ec07565b73e278b8baf4b` |
| `data/features/c8_eppo_fuel_oil_transformations.parquet` | `7d6ca77a7c1c35634a06ed116c8b2938b65bf3f7ee57075f28a3150cc7d76076` |
| `data/features/c9_fuel_oil_conditioned.parquet` | `6e1b78c3758c70315b2c5c67978ed88ae3fa18c4b7a20198195a2eeb3c576985` |
| `data/features/c9_fuel_oil_development_snapshot.parquet` | `1afb62ce0548c14d305b5bc9f886d14b47f3734bba2f30b370bb40003f5b1deb` |
| `data/model_input/d5_fuel_oil_predictions.parquet` | `930f348d0b66b293ee9f3a892c22d58d7307f2c9ea6f8a07730cf825826184ed` |
| `data/model_input/d5_fuel_oil_coefficients.parquet` | `26b3234ca6a4150ea93f0801ffa1461a88a7d60d18e0150c7d750176ef90b4c4` |

## 6. Source validity is not modeling eligibility

| question | status |
| --- | --- |
| Are the official EPPO source documents still valid evidence? | **Yes** |
| Are C7/C7.5 semantic decisions retained? | **Yes** |
| Are C8 transformations reproducible? | **Yes** |
| Is sector-093 exposure reproducible? | **Yes** |
| Is the interaction architecture mathematically identifiable? | **Yes** |
| Was predictive utility demonstrated on development data? | **No** |
| May the channel enter further operational modeling? | **No** |
| May the locked test be opened for this channel? | **No** |

## 7. Prohibited reopening reasons

A new specification alone is not new evidence (`new_specification_alone_is_new_evidence`: `False`). Each of these re-describes the evidence D5 already produced:

* `trying_another_alpha`
* `expanding_an_alpha_grid`
* `replacing_ridge_with_another_estimator`
* `adding_nonlinear_terms_after_seeing_d5`
* `feature_selection_based_on_d5`
* `removing_transformations_based_on_d5_coefficients`
* `selecting_fo600_or_fo1500_from_observed_mae`
* `combining_the_two_channels`
* `using_pca_or_a_composite_index`
* `tuning_high_stress_thresholds`
* `evaluating_a_favorable_subgroup`
* `removing_ind_04_from_denominators`
* `switching_direct_exposure_to_total_requirement_because_d5_failed`
* `reducing_publication_lag`
* `opening_purge_or_locked_origins`
* `rephrasing_an_inconclusive_result_as_evidence_for_another_specification`

## 8. Permitted reopening evidence

* **`product_specific_consumption_crosswalk`** - An official product-specific industrial fuel-consumption crosswalk distinguishing FO 600 or FO 1500 use by industry.
* **`newer_compatible_io_table`** - A newer compatible I/O table materially changing sector-093 exposure and available before the evaluation period.
* **`point_in_time_release_evidence`** - Verified point-in-time EPPO release evidence or historical vintages that change the availability contract.
* **`longer_compatible_target_history`** - A materially longer compatible development target history obtained without using purge or locked origins.
* **`proven_implementation_error`** - A proven source, target, alignment or implementation error that materially affected D5.
* **`new_external_hypothesis`** - A genuinely new external hypothesis registered BEFORE inspecting any corresponding development result.

Every reopening request must carry all of:

* `new_evidence_id`
* `source`
* `checksum`
* `availability_date`
* `why_unavailable_to_d5`
* `affected_assumption`
* `expected_artifact_impact`
* `not_selected_from_d5_outcomes`
* `superseding_decision_log_entry`

Without them, modeling entry `raise`s.

## 9. Enforcement

| field | value |
| --- | --- |
| `permitted_purposes_all_allowed` | `True` |
| `blocked_purposes_all_refused` | `True` |
| `closure_reason_is_specific` | `True` |
| `closed_features_reported_as_missing` | `False` |
| `unrelated_features_unaffected` | `True` |
| `generic_upstream_feature_creation_altered` | `False` |
| `historical_d5_reproducibility_preserved` | `True` |

30 guard probes run against permitted and prohibited consumers. Blocked: `modeling`, `model_training`, `target_assembly`, `feature_selection`, `operational_modeling`, `locked_test_evaluation`. Permitted: `audit`, `reproduction`, `documentation`, `source_quality`, `provenance_verification`, `historical_d5_reproduction`.

A closed feature is refused **with its closure reason**, never reported
as missing - "not found" would send the next reader looking for a bug
that does not exist.

## 10. Final declaration

* **The EPPO fuel-oil modeling channel is closed.**
* **Incremental signal was not demonstrated.**
* **Absence of an effect was not proven.**
* **Official source and structural artifacts remain preserved and valid within their stated limitations.**
* **Neither fuel-oil variant is selected.**
* **No further specification search is authorized.**
* **The locked final test remains unopened.**
* **Reopening requires genuinely new external evidence.**

Content checksum `ee26a8552d595544c72340aa1ad78987582ad3d266f0e5acc4240d09124f8320`.

