# Task C10 - Design-Matrix Audit Protocol

*Config `fuel_oil_development_matrix_v1`, contract `c10_diagnostic_contract_v1`.*

**Frozen diagnostic-contract checksum:** `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041`

Every threshold below was written before a single C9 feature value was
read. The runner hashes the contract, re-asserts the digest immediately
before loading values and again after the diagnostics run, so a tolerance
moved after seeing a singular value raises rather than passing.

## Frozen thresholds

| field | value |
| --- | --- |
| `rank_tolerance` | `1e-10` |
| `near_zero_variance_threshold` | `1e-12` |
| `reconstruction_tolerance` | `1e-09` |
| `standardization_tolerance` | `1e-09` |
| `standardization_ddof` | `0` |
| `standardization_formula` | `(x - mean) / std` |
| `primary_diagnostic_input` | `source_time_matrix_15x5` |

## Expected shape

| field | value |
| --- | --- |
| `matrix_key` | `['issue_month', 'industry_id']` |
| `expected_variants` | `['fo600_direct_sector093', 'fo1500_direct_sector093']` |
| `expected_issue_months` | `15` |
| `expected_industries` | `12` |
| `expected_transformation_columns` | `['log_change_12m_pct', 'log_change_1m_pct', 'log_change_3m_pct', 'price_level', 'realized_volatility_3m_pct']` |
| `expected_rows_per_variant` | `180` |
| `expected_cells_per_variant` | `900` |
| `expected_numeric_cells_per_variant` | `825` |
| `expected_masked_cells_per_variant` | `75` |

## Preregistered identities

| field | value |
| --- | --- |
| `conditioning_formula` | `D[v,g] = E[g] * X[v]` |
| `exposure_normalization` | `Xhat[v,g] = D[v,g] / E[g]` |
| `standardization_invariance` | `standardize(E*X) == standardize(X) for E > 0` |
| `expected_distinct_raw_fingerprints_per_variant` | `11` |
| `expected_distinct_normalized_fingerprints_per_variant` | `1` |
| `expected_distinct_standardized_fingerprints_per_variant` | `1` |
| `conditioning_adds_cross_industry_scale` | `expected_true` |
| `conditioning_adds_temporal_degrees_of_freedom` | `expected_false` |
| `per_industry_standardization_removes_exposure_scale` | `expected_true` |

## What decides, and what is only described

The **decision rule** for both identities is the preregistered absolute
residual tolerance above. The fingerprint counts are **descriptive**: a
fingerprint rounds to a fixed number of *significant* digits, so it
resolves a standardised value near zero far below double precision and
can split matrices that agree to 1e-15. Both counts are published; where
they disagree the tolerance governs, and any preregistered expectation
that does not reproduce is reported as a discrepancy rather than
relaxed.

## Missingness precedence

1. `structural_ineligibility`
2. `source_transformation_null`
3. `observed_zero_exposure`
4. `available_numeric_value`

## Permitted statistics

* `singular_values`
* `numerical_rank`
* `raw_condition_number`
* `standardized_condition_number`
* `pearson_correlation`
* `spearman_correlation`
* `exact_duplicate_column_check`
* `column_variance`
* `exact_zero_observation_count`
* `cross_sectional_rank`
* `exposure_normalization_residual`
* `standardization_invariance_residual`
* `design_fingerprint_count`

## Prohibitions

| field | value |
| --- | --- |
| `channel_selection_permitted` | `False` |
| `feature_removal_permitted` | `False` |
| `target_or_model_access_permitted` | `False` |
| `significance_testing_permitted` | `False` |

Prohibited artifacts: `b3_target_values`, `industry_month_panel_with_target_outcomes`, `d1_development_predictions`, `d3_operational_predictions`, `d4_operational_model_predictions`, `b4_walk_forward_predictions`, `forecast_target_raw`, `production_stress_month`, `locked_test_outcomes`, `correlations_with_stress_outcomes`.

## What the audit is measuring

C9 built `D[v,g] = E[g] * X[v]`: each eligible industry's design is one source-time matrix multiplied by a positive scalar exposure. The audit checks that identity two ways - by reconstructing `X` from every eligible industry, and by confirming that per-industry standardisation leaves no trace of `E`. Both are properties of the design matrix, established without reading any target, and neither is a statement about what a model would do.

