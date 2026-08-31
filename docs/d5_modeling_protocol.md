# Task D5 - Pooled Fuel-Oil Interaction Modeling Protocol

*Config `d5_fuel_oil_interaction_v1`, protocol `d5_pooled_fuel_oil_interaction_protocol_v1`.*

**Frozen protocol checksum:** `13a0b1846df33f2d81eae8be8415b66bdeaef1bb20642e0a07645774c624483a`

Everything below was written, hashed and **read back from disk** before
the guarded target reader opened. A target value requested before that
checksum is verified raises and terminates the run, so the specification
cannot still be editable while an outcome is visible.

Authorized by C11-R1 as a **development-only exploratory** evaluation.
Channel selection, purge metrics, confirmatory claims and the locked test
are outside the grant and stay outside it whatever the numbers say.

## The model

Residual: `r[g,t,h] = y[g,t,h] - b[g,t,h]`

Fit: `rhat[g,t,h] = alpha[g,h] + sum_f beta[h,f] * xtilde[t,f] + sum_f theta[h,f] * ez[g] * xtilde[t,f]`

Prediction: `yhat[g,t,h] = clip(b[g,t,h] + rhat[g,t,h], 0, 100)`

| field | value |
| --- | --- |
| `pooled_across_eligible_industries` | `['beta', 'theta']` |
| `industry_specific` | `['alpha']` |
| `horizons_fit_separately` | `True` |
| `variants_fit_separately` | `True` |
| `clip_lower` | `0.0` |
| `clip_upper` | `100.0` |
| `clipping_bounds_tuned` | `False` |
| `estimand_changed_from_c11` | `False` |
| `interpretation` | `non_causal_predictive_interaction` |

## The estimator

| field | value |
| --- | --- |
| `name` | `fixed_pooled_partial_ridge_v1` |
| `loss` | `(1/n) * sum_i (r_i - rhat_i)^2 + lambda * (||beta||^2 + ||theta||^2)` |
| `lambda` | `1.0` |
| `loss_normalised_by_n` | `True` |
| `lambda_meaning_invariant_to_panel_size` | `True` |
| `penalized_blocks` | `['source', 'interaction']` |
| `penalized_coefficient_count` | `10` |
| `unpenalized_blocks` | `['industry_fixed_effects']` |
| `unpenalized_coefficient_count` | `11` |
| `redundant_global_intercept` | `False` |
| `alpha_grid` | `False` |
| `inner_cv` | `False` |
| `model_averaging` | `False` |
| `fallback_estimator` | `False` |
| `hyperparameter_search` | `False` |
| `outcome_based_feature_removal` | `False` |
| `solver` | `explicit_penalty_matrix_normal_equations` |
| `normal_equation_residual_tolerance` | `1e-08` |

The loss is averaged by `n`. With an unnormalised sum the same `lambda`
would be a weaker penalty on every larger training panel - and the panel
grows from 231 rows to 385 across the walk-forward - so the specification
would drift without a single number being edited. Industry fixed effects
are unpenalised: shrinking an industry intercept toward zero shrinks it
toward a stress score of zero, which is a strong claim rather than a
neutral prior.

## Preprocessing

| field | value |
| --- | --- |
| `source_scaler.fitted_on` | `unique_permitted_training_issue_months` |
| `source_scaler.fitted_on_repeated_industry_panel` | `False` |
| `source_scaler.ddof` | `0` |
| `source_scaler.applied_identically_to_every_eligible_industry` | `True` |
| `source_scaler.refit_per` | `['outer_issue', 'horizon', 'variant']` |
| `source_scaler.zero_or_invalid_training_variance` | `raise` |
| `exposure.centering_universe` | `eleven_eligible_industries` |
| `exposure.centering_source` | `c9_phase_a_frozen_decision_table` |
| `exposure.scaled_by` | `frozen_structural_standard_deviation` |
| `exposure.scaling_is_a_fixed_column_reparameterization` | `True` |
| `exposure.changes_the_c11_estimand` | `False` |
| `exposure.fitted_on_targets` | `False` |
| `exposure.recomputed_per_fold` | `False` |
| `exposure.raw_and_centered_preserved_in_lineage` | `True` |
| `interaction.constructed_after_source_standardization` | `True` |
| `interaction.standardized_separately_by_industry` | `False` |
| `fitted_using_targets` | `False` |

The source scaler is fitted on the **unique** permitted training issue
months. Fitting it on the stacked panel would weight one national series
eleven times and report a sample size the data does not have. Exposure
scaling is a fixed column reparameterisation for numerical conditioning:
it multiplies the interaction column by a constant and divides theta by
the same constant, so the C11 estimand is unchanged.

## Training rules

| field | value |
| --- | --- |
| `feature_reference_month_rule` | `reference_month(u) = u - 2` |
| `feature_available_by` | `u` |
| `benchmark_history_available_by` | `u` |
| `label_available_by` | `t` |
| `imputation_of_unavailable_source_values` | `False` |
| `ind_04_in_fitted_panel` | `False` |
| `all_eligible_industries_required_per_accepted_issue` | `True` |
| `eligible_industries_per_issue` | `11` |
| `grouped_by_issue_month_in_all_audits` | `True` |
| `all_five_transformations_required` | `True` |
| `first_reference_month_with_all_five_finite` | `2022-01` |
| `h3_start_constrained_by` | `operational_benchmark_history` |
| `pre_2022_stress_history_synthesized` | `False` |

| horizon and outer issue | unique training issues | eligible rows | all-industry rows |
| --- | ---: | ---: | ---: |
| `h1_at_2024_01` | 21 | 231 | 252 |
| `h1_at_2025_03` | 35 | 385 | 420 |
| `h3_at_2024_01` | 18 | 198 | 216 |
| `h3_at_2025_03` | 32 | 352 | 384 |

## Evaluation contract and benchmarks

| field | value |
| --- | --- |
| `operational_contract_version` | `operational_contract_v1` |
| `latest_available_stress_month` | `t - 1` |
| `stress_month_t_used_at_issue_t` | `False` |
| `fo_reference_month` | `t - 2` |
| `horizon_1_target` | `stress at t+1` |
| `horizon_3_target` | `max stress over t+1, t+2, t+3` |
| `calibrator_cutoff_max` | `t - 1` |
| `training_features_frozen_at_their_own_issue_month` | `True` |
| `historical_feature_refreshed_at_outer_issue` | `False` |
| `evaluation_target_read_after_prediction_freeze` | `True` |
| `independent_cutoff_assertion` | `True` |

| benchmark | formula |
| --- | --- |
| `operational_persistence_latest_published` | `C_t(S_{t-1})` |
| `operational_persistence_trailing_3m_max` | `max C_t(S_{t-3}, S_{t-2}, S_{t-1})` |
| `operational_no_contraction` | `registered no-contraction floor formula` |

Primary h=1: `operational_persistence_latest_published`. Primary h=3: `operational_persistence_trailing_3m_max`. Secondary comparator: `operational_no_contraction`.

Benchmarks are **reproduced from their registered formulas** by running
the operational walk-forward, not copied from a D3 result artifact. No D3
metric is a model input or an optimisation criterion.

## Metrics, event safety and uncertainty

| field | value |
| --- | --- |
| `metrics.primary` | `macro_industry_mae` |
| `metrics.panel` | `full_twelve_industry` |
| `metrics.report` | `['macro_industry_mae', 'pooled_mae', 'macro_industry_rmse', 'pooled_rmse', 'median_absolute_error', 'spearman_correlation', 'clipped_count', 'clipped_rate', 'paired_model_minus_primary_benchmark_mae_difference', 'mae_skill_relative_to_primary_benchmark']` |
| `metrics.eligible_only_diagnostic` | `{'industries': 11, 'status': 'secondary_structurally_preregistered', 'may_replace_the_full_panel_result': False}` |
| `metrics.panel_rows_treated_as_independent_observations` | `False` |
| `event_safety.high_stress_threshold` | `85` |
| `event_safety.severe_stress_threshold` | `95` |
| `event_safety.severe_is_descriptive_only` | `True` |
| `event_safety.severe_affects_any_decision` | `False` |
| `event_safety.thresholds_tuned` | `False` |
| `event_safety.report` | `['observed_event_count', 'predicted_event_count', 'precision', 'recall', 'false_negatives', 'false_positives']` |
| `event_safety.rule` | `event_safety_passed = model_false_negatives <= benchmark_false_negatives` |
| `event_safety.precision_trade_off_reported_explicitly` | `True` |
| `bootstrap.cluster_unit` | `issue_month` |
| `bootstrap.keep_all_industries_together` | `True` |
| `bootstrap.resample_individual_industry_rows` | `False` |
| `bootstrap.paired_resamples_identical_for_model_and_benchmark` | `True` |
| `bootstrap.random_seed` | `20260830` |
| `bootstrap.replications` | `1000` |
| `bootstrap.confidence_level` | `0.95` |
| `bootstrap.block_length_by_horizon` | `{'1': 1, '3': 3}` |
| `bootstrap.method_by_horizon` | `{'1': 'issue_month_cluster_bootstrap', '3': 'moving_block_issue_month_bootstrap'}` |
| `bootstrap.report` | `['model_mae_interval', 'benchmark_mae_interval', 'paired_model_minus_benchmark_mae_interval', 'issue_months_where_model_beats_benchmark']` |
| `bootstrap.resolution_note` | `Fifteen issue clusters provide limited uncertainty resolution. Intervals here are wide by construction and are reported as such.` |

## Decision rules

| field | value |
| --- | --- |
| `paired_difference` | `delta = MAE_model - MAE_benchmark` |
| `sign_convention` | `negative_means_the_model_is_better` |
| `mae_evidence` | `{'supported': 'entire_paired_95_interval_below_zero', 'adverse': 'entire_paired_95_interval_above_zero', 'inconclusive': 'otherwise'}` |
| `overall_status` | `{'exploratory_incremental_signal_supported': 'mae_evidence_supported_and_event_safety_passed', 'incremental_signal_not_supported': 'mae_evidence_adverse', 'inconclusive': 'otherwise'}` |
| `applied_separately_to_every_variant_and_horizon` | `True` |
| `regardless_of_result` | `{'channel_selected': False, 'model_feature_approved': False, 'locked_evaluation_authorized': False, 'confirmatory_claim_made': False}` |

## Guards

* `stress_month_t_used_at_issue_t`
* `feature_later_than_t_minus_2`
* `historical_training_feature_refreshed_at_outer_issue`
* `label_used_before_its_d3_availability_month`
* `calibrator_includes_stress_after_t_minus_1`
* `evaluation_target_read_before_prediction_freeze`
* `purge_or_locked_origin_in_any_metric`
* `scaling_uses_development_evaluation_rows_outside_the_training_set`
* `industry_rows_shuffled_across_time_for_validation_or_bootstrap`
* `target_outcomes_alter_preprocessing_or_estimator_configuration`

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

