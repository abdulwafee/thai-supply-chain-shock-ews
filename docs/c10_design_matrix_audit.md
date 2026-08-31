# Task C10 - Development-Only Design-Matrix Identifiability Audit

*Generated 2026-08-29T08:40:44.617205+00:00. Config `fuel_oil_development_matrix_v1`.*

Diagnostic contract `1c88cdd7f2017aa94ee1b069be436c469ee08adcf649fe6ad4c981f995eb2041`, frozen
before the values loaded and re-asserted after the diagnostics ran.

## Upstream invariants

All reproduced: **True** (30 checks).

| check | expected | actual |
| --- | --- | --- |
| `c9_conditioned_rows` | `7800` | `7800` |
| `c9_variants` | `['fo1500_direct_sector093', 'fo600_direct_sector093']` | `['fo1500_direct_sector093', 'fo600_direct_sector093']` |
| `c9_rows_per_variant` | `[3900]` | `[3900]` |
| `c9_industries` | `12` | `12` |
| `c9_transformations` | `5` | `5` |
| `c9_reference_months` | `65` | `65` |
| `c9_available_nonzero` | `6578` | `6578` |
| `c9_direction_ambiguity_rows` | `650` | `650` |
| `c9_source_null_rows` | `572` | `572` |
| `c9_phase_a_checksum` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` | `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703` |
| `c9_io_sector_code` | `['093']` | `['093']` |
| `c9_sector_031_used` | `False` | `False` |
| `c9_total_requirement_used` | `False` | `False` |
| `c9_ineligible_industries` | `['IND-04']` | `['IND-04']` |
| `c9_eligible_industries_per_channel` | `11` | `11` |
| `c9_eligible_exposures_strictly_positive` | `True` | `True` |
| `c9_ind04_direction_ambiguous` | `['mixed_or_ambiguous']` | `['mixed_or_ambiguous']` |
| `c9_ind04_multiplier_null` | `True` | `True` |
| `c9_source_available_as_of_null` | `True` | `True` |
| `c9_latest_vintage_used` | `True` | `True` |
| `c9_point_in_time_supported` | `False` | `False` |
| `c9_operational_lag_is_measured` | `False` | `False` |
| `snapshot_issue_months` | `15` | `15` |
| `snapshot_issue_month_range` | `['2024-01', '2025-03']` | `['2024-01', '2025-03']` |
| `snapshot_reference_month_range` | `['2023-11', '2025-01']` | `['2023-11', '2025-01']` |
| `snapshot_cells` | `1800` | `1800` |
| `snapshot_numeric_cells` | `1650` | `1650` |
| `snapshot_masked_cells` | `150` | `150` |
| `snapshot_source_gap_cells` | `0` | `0` |
| `snapshot_purge_or_locked_rows` | `0` | `0` |

## The structural finding

| field | value |
| --- | --- |
| `cross_industry_information_is_exposure_scaling_only` | `True` |
| `industry_conditioning_adds_temporal_degrees_of_freedom` | `False` |
| `all_designs_are_scalar_multiples_of_one_source_time_matrix` | `True` |
| `per_industry_standardization_removes_exposure_scale` | `True` |
| `unique_issue_months` | `15` |
| `stacked_eligible_rows` | `165` |
| `stacked_rows_are_independent_claim_permitted` | `False` |
| `temporal_independence_claim_permitted` | `False` |

> Each eligible industry's design is one 15x5 source-time matrix multiplied by a positive scalar exposure, so the 165-row stacked panel is eleven scaled copies of fifteen rows. This is a property of the design matrix established without reading any target; it is not a statement about predictive performance.

## `fo1500_direct_sector093`

Matrix **180 x 5** (900 cells): **825** numeric, **75** masked. 165 fully numeric rows, 15 fully masked (IND-04).

| diagnostic | value |
| --- | --- |
| unique temporal rows | **15** |
| source-time rank (15x5) | **5** |
| stacked panel | 165 rows, rank **5** |
| industry-matrix ranks | `[5]` |
| cross-sectional rank by issue | `[1]` (all 15 issue months) |
| singular values | 78.334416, 67.989289, 33.174838, 19.183147, 4.772391 |
| raw condition number | 16.414082 |
| standardized condition number | 4.997158 |
| exact duplicate columns | `none` |

### Variance (source-time matrix)

| transformation | sd | exact-zero variance | near-zero variance | exact-zero observations | retained |
| --- | --- | --- | --- | --- | --- |
| `log_change_12m_pct` | 15.313177 | `False` | `False` | 0 | `True` |
| `log_change_1m_pct` | 6.683181 | `False` | `False` | 0 | `True` |
| `log_change_3m_pct` | 13.870589 | `False` | `False` | 0 | `True` |
| `price_level` | 1.415554 | `False` | `False` | 0 | `True` |
| `realized_volatility_3m_pct` | 2.049374 | `False` | `False` | 0 | `True` |

All 11 eligible industries share one zero-variance classification: `True`.

### Pairwise correlations (descriptive only, 15 overlapping months)

| pair | Pearson | Spearman |
| --- | --- | --- |
| `log_change_12m_pct` vs `log_change_1m_pct` | 0.4448 | 0.2929 |
| `log_change_12m_pct` vs `log_change_3m_pct` | 0.6194 | 0.6071 |
| `log_change_12m_pct` vs `price_level` | 0.6885 | 0.6429 |
| `log_change_12m_pct` vs `realized_volatility_3m_pct` | -0.7495 | -0.5357 |
| `log_change_1m_pct` vs `log_change_3m_pct` | 0.6314 | 0.6179 |
| `log_change_1m_pct` vs `price_level` | 0.3563 | 0.4214 |
| `log_change_1m_pct` vs `realized_volatility_3m_pct` | -0.1982 | -0.2393 |
| `log_change_3m_pct` vs `price_level` | 0.7562 | 0.8143 |
| `log_change_3m_pct` vs `realized_volatility_3m_pct` | -0.4668 | -0.4750 |
| `price_level` vs `realized_volatility_3m_pct` | -0.5000 | -0.5000 |

No significance test is reported and no correlation selects a channel
or removes a transformation.

### Exposure normalisation and standardisation invariance

| field | value |
| --- | --- |
| eligible reconstructions | 11 |
| max reconstruction residual | 3.553e-15 |
| residual vs C8 source transformations | 1.776e-15 |
| distinct raw fingerprints | **11** |
| distinct normalized fingerprints | **1** |
| normalized equivalence classes at tolerance | **1** |
| all designs are scalar multiples | `True` |
| max standardized-design residual | 2.665e-15 |
| standardized equivalence classes at tolerance | **1** |
| distinct standardized fingerprints | **1** |
| fingerprint agrees with tolerance classes | `True` |
| identity decided by | `max_standardized_design_residual <= tolerance` |
| exposure survives standardization | `False` |
| industry-specific temporal pattern | `False` |

> For a positive scalar E, standardize(E X) == standardize(X) because the scalar cancels in both the mean and the standard deviation. Sector-093 exposure therefore affects raw scale and does not survive per-industry standardisation. This is a property of the design matrix, established without reading any target.

> The fingerprint rounds to a fixed number of significant digits, so a standardised value near zero is resolved far below double precision and two matrices that agree to 1e-15 can fingerprint differently. Where the two counts disagree the preregistered absolute tolerance governs; the fingerprint count is reported unchanged as observed.

### Availability and lineage

900 snapshot rows checked against the recorded fields: 0 lag-2 violations, 0 policy violations. Structural availability `2020-03-31` (reference year 2015), `backdated_to_reference_year`: `False`.

Lineage: 900 cells carry a checksum, 900 distinct.

## `fo600_direct_sector093`

Matrix **180 x 5** (900 cells): **825** numeric, **75** masked. 165 fully numeric rows, 15 fully masked (IND-04).

| diagnostic | value |
| --- | --- |
| unique temporal rows | **15** |
| source-time rank (15x5) | **5** |
| stacked panel | 165 rows, rank **5** |
| industry-matrix ranks | `[5]` |
| cross-sectional rank by issue | `[1]` (all 15 issue months) |
| singular values | 73.867018, 72.325755, 31.206003, 19.089520, 5.078793 |
| raw condition number | 14.544208 |
| standardized condition number | 5.294781 |
| exact duplicate columns | `none` |

### Variance (source-time matrix)

| transformation | sd | exact-zero variance | near-zero variance | exact-zero observations | retained |
| --- | --- | --- | --- | --- | --- |
| `log_change_12m_pct` | 15.575411 | `False` | `False` | 0 | `True` |
| `log_change_1m_pct` | 6.520401 | `False` | `False` | 0 | `True` |
| `log_change_3m_pct` | 13.012666 | `False` | `False` | 0 | `True` |
| `price_level` | 1.420131 | `False` | `False` | 0 | `True` |
| `realized_volatility_3m_pct` | 2.112987 | `False` | `False` | 0 | `True` |

All 11 eligible industries share one zero-variance classification: `True`.

### Pairwise correlations (descriptive only, 15 overlapping months)

| pair | Pearson | Spearman |
| --- | --- | --- |
| `log_change_12m_pct` vs `log_change_1m_pct` | 0.4563 | 0.3357 |
| `log_change_12m_pct` vs `log_change_3m_pct` | 0.6633 | 0.7107 |
| `log_change_12m_pct` vs `price_level` | 0.8190 | 0.8536 |
| `log_change_12m_pct` vs `realized_volatility_3m_pct` | -0.7415 | -0.6429 |
| `log_change_1m_pct` vs `log_change_3m_pct` | 0.6099 | 0.5250 |
| `log_change_1m_pct` vs `price_level` | 0.3229 | 0.2643 |
| `log_change_1m_pct` vs `realized_volatility_3m_pct` | -0.2387 | -0.2250 |
| `log_change_3m_pct` vs `price_level` | 0.7007 | 0.7179 |
| `log_change_3m_pct` vs `realized_volatility_3m_pct` | -0.5547 | -0.5964 |
| `price_level` vs `realized_volatility_3m_pct` | -0.6419 | -0.6071 |

No significance test is reported and no correlation selects a channel
or removes a transformation.

### Exposure normalisation and standardisation invariance

| field | value |
| --- | --- |
| eligible reconstructions | 11 |
| max reconstruction residual | 7.105e-15 |
| residual vs C8 source transformations | 3.553e-15 |
| distinct raw fingerprints | **11** |
| distinct normalized fingerprints | **1** |
| normalized equivalence classes at tolerance | **1** |
| all designs are scalar multiples | `True` |
| max standardized-design residual | 4.385e-15 |
| standardized equivalence classes at tolerance | **1** |
| distinct standardized fingerprints | **11** |
| fingerprint agrees with tolerance classes | `False` |
| identity decided by | `max_standardized_design_residual <= tolerance` |
| exposure survives standardization | `False` |
| industry-specific temporal pattern | `False` |

> For a positive scalar E, standardize(E X) == standardize(X) because the scalar cancels in both the mean and the standard deviation. Sector-093 exposure therefore affects raw scale and does not survive per-industry standardisation. This is a property of the design matrix, established without reading any target.

> The fingerprint rounds to a fixed number of significant digits, so a standardised value near zero is resolved far below double precision and two matrices that agree to 1e-15 can fingerprint differently. Where the two counts disagree the preregistered absolute tolerance governs; the fingerprint count is reported unchanged as observed.

### Availability and lineage

900 snapshot rows checked against the recorded fields: 0 lag-2 violations, 0 policy violations. Structural availability `2020-03-31` (reference year 2015), `backdated_to_reference_year`: `False`.

Lineage: 900 cells carry a checksum, 900 distinct.

## Preregistered expectations that did not reproduce

1 of the preregistered `expected_identities` values did not reproduce. No threshold was moved and no expectation was relaxed (`thresholds_changed_after_observation`: `False`, `expectations_relaxed_to_obtain_a_pass`: `False`).

| variant | field | preregistered | observed | decided by |
| --- | --- | --- | --- | --- |
| `fo600_direct_sector093` | `expected_distinct_standardized_fingerprints_per_variant` | `1` | `11` | the frozen absolute tolerance, not the fingerprint count |

> The fingerprint rounds to 13 significant digits, so a standardised value near zero is resolved below double precision. The preregistered tolerance test on the same matrices puts every eligible industry in one equivalence class, and that test decides.

## Channel separation

| field | value |
| --- | --- |
| `artifacts_kept_separate` | `True` |
| `side_by_side_reporting_permitted` | `True` |
| `preferred_channel_produced` | `False` |

Prohibited: `addition`, `averaging`, `pca_across_the_two_channels`, `composite_fuel_oil_index`, `ten_column_simultaneous_model_matrix`, `selection_on_rank_variance_correlation_or_condition_number`, `target_based_channel_selection`.

The two variants are reported side by side. No diagnostic here ranks one
variant against the other, and `preferred_channel_produced` above records
that none was produced.

## Units and interpretation

| transformation | unit |
| --- | --- |
| `price_level` | `baht_per_litre_x_io_coefficient` |
| `log_change_1m_pct` | `percentage_point_log_change_x_io_coefficient` |
| `log_change_3m_pct` | `percentage_point_log_change_x_io_coefficient` |
| `log_change_12m_pct` | `percentage_point_log_change_x_io_coefficient` |
| `realized_volatility_3m_pct` | `percentage_point_log_change_volatility_x_io_coefficient` |

| field | value |
| --- | --- |
| `structural_interaction_only` | `True` |
| `currency_cost_per_unit_of_industrial_output` | `False` |
| `elasticity` | `False` |
| `pass_through` | `False` |
| `causal_effect` | `False` |
| `forecast_coefficient` | `False` |
| `valuation_basis_alignment` | `partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price` |

## Decisions

| field | value |
| --- | --- |
| `development_matrix_assembled` | `True` |
| `conditioning_adds_cross_industry_scale` | `True` |
| `conditioning_adds_temporal_degrees_of_freedom` | `False` |
| `per_industry_standardization_removes_exposure_scale` | `True` |
| `predictive_utility_assessed` | `False` |
| `channel_selected` | `False` |
| `target_joined` | `False` |
| `model_trained` | `False` |
| `model_feature_approved` | `False` |
| `locked_test_accessed` | `False` |
| `target_join_authorized` | `False` |
| `modeling_authorized` | `False` |
| `variant_promoted_to_modeling_readiness` | `False` |

> A full-rank source-time matrix does not promote either variant to modeling readiness. Rank is a property of the design; approval is a separate decision that has not been taken.

Content checksum `bb520f9e74f49afbf6f50d934dea6630c81ea366c24f78b548d03f4a95c24d1c`.

