# Task C9 Phase B - Industry-Conditioned Fuel-Oil Features

*Generated 2026-08-29T07:55:17.174184+00:00. Config `fuel_oil_industry_conditioning_v1`, formula `c9_fuel_oil_direct_sector093_v1`.*

Phase-A decision checksum `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703`, reasserted before the C8 values were loaded and again after conditioning.

## Upstream invariants

All reproduced: **True** (29 checks).

| check | expected | actual |
| --- | --- | --- |
| `c8_source_transformation_rows` | `650` | `650` |
| `c8_finite_rows` | `598` | `598` |
| `c8_null_rows` | `52` | `52` |
| `c8_rows_per_channel` | `[325]` | `[325]` |
| `c8_finite_per_channel` | `[299]` | `[299]` |
| `c8_null_per_channel` | `[26]` | `[26]` |
| `c8_transformation_definitions` | `5` | `5` |
| `c8_policy_lag_months` | `2` | `2` |
| `c8_lag_is_measured` | `False` | `False` |
| `c8_source_available_as_of_null_rows` | `650` | `650` |
| `c8_latest_vintage_used` | `True` | `True` |
| `c8_point_in_time_supported` | `False` | `False` |
| `c8_shared_price_stage_group` | `io_sector_093_fuel_oil` | `io_sector_093_fuel_oil` |
| `c8_channels` | `['eppo_fo1500_channel', 'eppo_fo600_channel']` | `['eppo_fo1500_channel', 'eppo_fo600_channel']` |
| `c8_hsd_absent` | `True` | `True` |
| `c8_fo600_ready` | `True` | `True` |
| `c8_fo1500_ready` | `True` | `True` |
| `c3_valid_io_sectors` | `179` | `179` |
| `c3_excluded_zero_output_sector` | `['179']` | `['179']` |
| `c3_coefficient_measure` | `purchaser` | `purchaser` |
| `c3_valuation_price_basis` | `purchasers_prices` | `purchasers_prices` |
| `c3_import_treatment` | `import_inclusive` | `import_inclusive` |
| `c3_production_industries` | `12` | `12` |
| `c3_no_duplicate_sector_assignment` | `True` | `True` |
| `c3_structural_available_by` | `2020-03-31` | `2020-03-31` |
| `c3_target_outcomes_used_in_crosswalk` | `False` | `False` |
| `sector_093_present_exactly_once` | `1` | `1` |
| `sector_093_official_label` | `Petroleum refineries` | `Petroleum refineries` |
| `gross_output_positive_for_every_used_sector` | `True` | `True` |

## Conditioned grid

`data/features/c9_fuel_oil_conditioned.parquet` - **7800** rows, key `variant_id + industry_id + reference_month + transformation_id`. Counts reconciled: **True**.

| field | expected | observed |
| --- | --- | --- |
| `full_grid_rows` | 7800 | 7800 |
| `ineligible_rows` | 650 | 650 |
| `source_gap_rows` | 572 | 572 |
| `source_numeric_rows` | 6578 | 6578 |

| status | rows |
| --- | --- |
| `available_nonzero` | 6578 |
| `not_generated_due_to_direction_ambiguity` | 650 |
| `source_current_month_gap` | 110 |
| `source_input_window_gap` | 44 |
| `source_insufficient_history` | 418 |

### By variant

| variant | `available_nonzero` | `not_generated_due_to_direction_ambiguity` | `source_current_month_gap` | `source_input_window_gap` | `source_insufficient_history` |
| --- | --- | --- | --- | --- | --- |
| `fo1500_direct_sector093` | 3289 | 325 | 55 | 22 | 209 |
| `fo600_direct_sector093` | 3289 | 325 | 55 | 22 | 209 |

## Conditioning formula and units

`z[g,c,m,f] = x[c,m,f] * E093[g] * s[g,c]`

| transformation | conditioned unit |
| --- | --- |
| `price_level` | `baht_per_litre_x_io_coefficient` |
| `log_change_1m_pct` | `percentage_point_log_change_x_io_coefficient` |
| `log_change_3m_pct` | `percentage_point_log_change_x_io_coefficient` |
| `log_change_12m_pct` | `percentage_point_log_change_x_io_coefficient` |
| `realized_volatility_3m_pct` | `percentage_point_log_change_volatility_x_io_coefficient` |

`not_a_currency_cost`: `True`, `not_an_elasticity`: `True`, `not_a_forecast_coefficient`: `True`.

Status precedence: `structural_ineligibility` -> `source_transformation_null` -> `structural_exposure_zero` -> `available_nonzero`.

## Variants

Shared exposure group `io_sector_093`; both variants carry the SAME sector-093 vector, which is exactly why they
are never combined.

| field | value |
| --- | --- |
| `additive_aggregation_allowed` | `False` |
| `simple_average_allowed` | `False` |
| `automatic_composite_index_allowed` | `False` |
| `simultaneous_model_entry_approved` | `False` |
| `outcome_based_variant_selection_allowed` | `False` |

## Availability

`conditioned_policy_available_month = max(source policy_available_month, structural available month)`. Structural availability **2020-03-31** (reference year 2015); `backdated_to_reference_year`: `False`, `download_timestamp_used`: `False`.

The source policy dominates in 7800 of 7800 rows; `source_available_as_of` is null in 7800.

## Lineage

`c9_fuel_oil_conditioned_lineage_v1` - 7800 rows carry a checksum, 7800 distinct, and 1222 null rows carry the full source and structural chains.

## Development snapshot

`data/features/c9_fuel_oil_development_snapshot.parquet` - 15 issue months x 2 variants x 12 industries x 5 transformations = **1800** cells.

| cell state | cells |
| --- | --- |
| `masked_ineligible` | 150 |
| `numeric` | 1650 |

## Issue-key coverage

From key ranges only; no target value, prediction or metric was read.

| split | variant | issue months | reference range | materialised |
| --- | --- | --- | --- | --- |
| `development` | `fo1500_direct_sector093` | 15 | 2023-11 .. 2025-01 | `True` |
| `development` | `fo600_direct_sector093` | 15 | 2023-11 .. 2025-01 | `True` |
| `locked_test` | `fo1500_direct_sector093` | 10 | 2025-05 .. 2026-02 | `False` |
| `locked_test` | `fo600_direct_sector093` | 10 | 2025-05 .. 2026-02 | `False` |
| `purge` | `fo1500_direct_sector093` | 3 | 2025-02 .. 2025-04 | `False` |
| `purge` | `fo600_direct_sector093` | 3 | 2025-02 .. 2025-04 | `False` |

## Readiness and authorization

| variant | rows | numeric | null | ready for development-only assembly |
| --- | --- | --- | --- | --- |
| `fo1500_direct_sector093` | 3900 | 3289 | 611 | `True` |
| `fo600_direct_sector093` | 3900 | 3289 | 611 | `True` |

| field | value |
| --- | --- |
| `industry_conditioned_features_created` | `True` |
| `feature_semantics_approved` | `False` |
| `model_feature_approved` | `False` |
| `target_join_authorized` | `False` |
| `modeling_authorized` | `False` |
| `locked_test_evaluation_authorized` | `False` |

> A structurally conditioned feature is not automatically predictive or model-approved.

Content checksum `711461e78ff83048b13ed4852211fccd6008f87dfd4276312a2b26754064527e`.

