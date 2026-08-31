# Task C8 - EPPO Fuel-Oil Transformation Audit

*Generated 2026-08-29T04:01:05.103144+00:00. Config `eppo_fuel_oil_transformations_v1`.*

## C7.5 invariants

All reproduced: **True** (25 checks).

| check | expected | actual |
| --- | --- | --- |
| `semantic_monthly_rows` | `195` | `195` |
| `overlay_parquet_rows` | `195` | `195` |
| `reference_months_per_series` | `[65]` | `[65]` |
| `reference_month_range` | `['2021-01', '2026-05']` | `['2021-01', '2026-05']` |
| `approved_complete_inventory_rows` | `168` | `168` |
| `approved_with_source_label_variant_rows` | `8` | `8` |
| `semantic_definition_gap_rows` | `16` | `16` |
| `known_document_gap_rows` | `3` | `3` |
| `fo600_equivalence_established` | `equivalence_established` | `equivalence_established` |
| `fo1500_equivalence_established` | `equivalence_established` | `equivalence_established` |
| `raw_labels_preserved` | `False` | `False` |
| `hsd_not_transformation_ready` | `False` | `False` |
| `fo600_transformation_ready` | `True` | `True` |
| `fo1500_transformation_ready` | `True` | `True` |
| `fo600_strict_null_2026_04` | `None` | `None` |
| `fo1500_strict_null_2026_04` | `None` | `None` |
| `fo_variant_months_2024_07_to_2024_10` | `['2024-07', '2024-08', '2024-09', '2024-10']` | `['2024-07', '2024-08', '2024-09', '2024-10']` |
| `hsd_gap_2023_09_to_2024_12` | `['2023-09', '2024-12', 16]` | `['2023-09', '2024-12', 16]` |
| `operational_policy_lag_months` | `2` | `2` |
| `operational_lag_is_measured` | `False` | `False` |
| `every_source_available_as_of_null` | `True` | `True` |
| `simultaneous_additive_fuel_oil_use_prohibited` | `False` | `False` |
| `c8_fo600_authorized` | `True` | `True` |
| `c8_fo1500_authorized` | `True` | `True` |
| `c8_hsd_not_authorized` | `False` | `False` |

## Counts

Grid **650** rows, **598** finite, **52** null. Reconciled: **True**.

| transformation | preregistered finite/null | derived finite/null | fo600 finite/null | fo1500 finite/null |
| --- | --- | --- | --- | --- |
| `price_level` | 64/1 | 64/1 | 64/1 | 64/1 |
| `log_change_1m_pct` | 62/3 | 62/3 | 62/3 | 62/3 |
| `log_change_3m_pct` | 61/4 | 61/4 | 61/4 | 61/4 |
| `log_change_12m_pct` | 52/13 | 52/13 | 52/13 | 52/13 |
| `realized_volatility_3m_pct` | 60/5 | 60/5 | 60/5 | 60/5 |

## Missingness

| status | rows |
| --- | --- |
| `available_numeric` | 598 |
| `current_month_source_gap` | 10 |
| `input_window_source_gap` | 4 |
| `insufficient_feature_history` | 38 |

### Every null cell, by channel

**`eppo_fo1500_channel`**

* `current_month_source_gap` (5): 2026-04 `log_change_12m_pct`, 2026-04 `log_change_1m_pct`, 2026-04 `log_change_3m_pct`, 2026-04 `price_level`, 2026-04 `realized_volatility_3m_pct`
* `input_window_source_gap` (2): 2026-05 `log_change_1m_pct`, 2026-05 `realized_volatility_3m_pct`
* `insufficient_feature_history` (19): 2021-01 `log_change_12m_pct`, 2021-01 `log_change_1m_pct`, 2021-01 `log_change_3m_pct`, 2021-01 `realized_volatility_3m_pct`, 2021-02 `log_change_12m_pct`, 2021-02 `log_change_3m_pct`, 2021-02 `realized_volatility_3m_pct`, 2021-03 `log_change_12m_pct`, 2021-03 `log_change_3m_pct`, 2021-03 `realized_volatility_3m_pct`, 2021-04 `log_change_12m_pct`, 2021-05 `log_change_12m_pct`, 2021-06 `log_change_12m_pct`, 2021-07 `log_change_12m_pct`, 2021-08 `log_change_12m_pct`, 2021-09 `log_change_12m_pct`, 2021-10 `log_change_12m_pct`, 2021-11 `log_change_12m_pct`, 2021-12 `log_change_12m_pct`

**`eppo_fo600_channel`**

* `current_month_source_gap` (5): 2026-04 `log_change_12m_pct`, 2026-04 `log_change_1m_pct`, 2026-04 `log_change_3m_pct`, 2026-04 `price_level`, 2026-04 `realized_volatility_3m_pct`
* `input_window_source_gap` (2): 2026-05 `log_change_1m_pct`, 2026-05 `realized_volatility_3m_pct`
* `insufficient_feature_history` (19): 2021-01 `log_change_12m_pct`, 2021-01 `log_change_1m_pct`, 2021-01 `log_change_3m_pct`, 2021-01 `realized_volatility_3m_pct`, 2021-02 `log_change_12m_pct`, 2021-02 `log_change_3m_pct`, 2021-02 `realized_volatility_3m_pct`, 2021-03 `log_change_12m_pct`, 2021-03 `log_change_3m_pct`, 2021-03 `realized_volatility_3m_pct`, 2021-04 `log_change_12m_pct`, 2021-05 `log_change_12m_pct`, 2021-06 `log_change_12m_pct`, 2021-07 `log_change_12m_pct`, 2021-08 `log_change_12m_pct`, 2021-09 `log_change_12m_pct`, 2021-10 `log_change_12m_pct`, 2021-11 `log_change_12m_pct`, 2021-12 `log_change_12m_pct`

## April 2026

Null rows retained: **10**. Statuses: `current_month_source_gap` 10.

Selected by a registered issue key: **False**. `removed_because_operationally_unused`: `False`.

> The maximum registered issue month is 2026-04 and the policy lag is 2, so no registered key reaches reference month 2026-04. The gap is kept and reported anyway.

## Availability

`source_available_as_of` is null in 650 of 650 rows. The equality `policy_available_month == reference_month + 2 months` was verified on every row.

| issue month | latest permitted reference month | rows returned | max reference month returned |
| --- | --- | --- | --- |
| 2024-01 | **2023-11** | 156 | 2023-11 |
| 2025-03 | **2025-01** | 226 | 2025-01 |
| 2026-04 | **2026-02** | 291 | 2026-02 |

## Issue-key coverage

Derived from preregistered issue-month ranges and the policy lag only; no
target value, prediction or metric was read.

| split | channel | issue months | with a blocked transformation | latest permitted reference range |
| --- | --- | --- | --- | --- |
| `development` | `eppo_fo1500_channel` | 15 | 0 | 2023-11 .. 2025-01 |
| `development` | `eppo_fo600_channel` | 15 | 0 | 2023-11 .. 2025-01 |
| `purge` | `eppo_fo1500_channel` | 3 | 0 | 2025-02 .. 2025-04 |
| `purge` | `eppo_fo600_channel` | 3 | 0 | 2025-02 .. 2025-04 |
| `locked_test` | `eppo_fo1500_channel` | 10 | 0 | 2025-05 .. 2026-02 |
| `locked_test` | `eppo_fo600_channel` | 10 | 0 | 2025-05 .. 2026-02 |

## C2 reconciliation

`formula_compatible_with_c2`: `True`, `source_timing_contract_differs_from_c2`: `True`.

Shared production implementation:

* `thai_supply_chain_ews.features.commodity_features.log_change_pct`
* `thai_supply_chain_ews.features.commodity_features.realized_volatility_pct`
* `thai_supply_chain_ews.features.commodity_features.FEATURE_DEFINITIONS`

| aspect | C2 | C8 |
| --- | --- | --- |
| values | archived first-release | latest vintage |
| publication timing | measured | policy-based |
| point-in-time supported | `True` | `False` |

Matching formulas do not imply matching evidence quality.

## Channels

| field | value |
| --- | --- |
| `additive_aggregation_allowed` | `False` |
| `simple_average_allowed` | `False` |
| `automatic_composite_index_allowed` | `False` |
| `simultaneous_model_entry_approved` | `False` |
| `outcome_based_channel_selection_allowed` | `False` |
| `both_channels_in_one_source_audit_table_allowed` | `True` |

Shared group `io_sector_093_fuel_oil`; channels `eppo_fo1500_channel`, `eppo_fo600_channel`.

## Lineage

`c8_eppo_transformation_lineage_v1` - 650 rows carry a checksum, 650 distinct, 52 null rows carry complete lineage naming their expected, available and missing months.

## Readiness

| channel | rows | finite | null | ready for structural conditioning |
| --- | --- | --- | --- | --- |
| `eppo_fo1500_channel` | 325 | 299 | 26 | `True` |
| `eppo_fo600_channel` | 325 | 299 | 26 | `True` |

`industry_conditioned_features_created`, `feature_semantics_approved` and
`model_feature_approved` are all `False`. Readiness for structural
conditioning is not approval as a model feature.

Content checksum `89195c01ba56b0b30c6bcd68eb9af069bf80da49da1192b03b899445379c46fe`.

