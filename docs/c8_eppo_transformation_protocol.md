# Task C8 - EPPO Fuel-Oil Transformation Protocol

*Config `eppo_fuel_oil_transformations_v1`, formula version `c8_eppo_fuel_oil_transformations_v1`.*

Preregistered before the run: the formulas, the input windows, the status
vocabulary and precedence, and the expected finite/null counts. The counts
are also derived from the declared input lags at run time, and the runner
fails if the two disagree.

## Input

`data/interim/c7_5_eppo_monthly_semantic.parquet` (C7.5), field
**`monthly_value_strict`**, gated on
**`approved_transformation_input`**, unit
`BAHT/LITRE`.

Never read: `monthly_value_descriptive`, `eppo_ex_refinery_hsd`, `blend_diesel`, `wholesale_price`, `retail_price`, `incomplete_source_month`, `imputed_or_interpolated_value`.

## Formulas

| transformation | formula | input lags | required inputs | unit |
| --- | --- | --- | --- | --- |
| `price_level` | `x_m = p_m` | `[0]` | 1 | `baht_per_litre` |
| `log_change_1m_pct` | `r_m = 100 * (ln p_m - ln p_{m-1})` | `[1, 0]` | 2 | `percentage_point_log_change` |
| `log_change_3m_pct` | `c3_m = 100 * (ln p_m - ln p_{m-3})` | `[3, 0]` | 2 | `percentage_point_log_change` |
| `log_change_12m_pct` | `c12_m = 100 * (ln p_m - ln p_{m-12})` | `[12, 0]` | 2 | `percentage_point_log_change` |
| `realized_volatility_3m_pct` | `v3_m = std_ddof0(r_{m-2}, r_{m-1}, r_m)` | `[3, 2, 1, 0]` | 4 | `percentage_point_log_change_volatility` |

Natural logarithm, scaled by 100, volatility with `ddof=0`. The volatility
declares **four** price levels because `r_{m-2}` is itself a change from
`m-3`; declaring three would understate the lineage and the availability
requirement.

## Missingness precedence

The first condition that holds decides the status:

1. `unauthorized_source_series`
2. `source_unit_mismatch`
3. `insufficient_feature_history`
4. `current_month_source_gap`
5. `input_window_source_gap`
6. `nonpositive_source_value`
7. `available_numeric`

Insufficient prehistory is never labelled as a source gap: a month before
the series begins is a property of the window, not of the archive.

## Preregistered counts

| transformation | finite | null |
| --- | --- | --- |
| `price_level` | 64 | 1 |
| `log_change_1m_pct` | 62 | 3 |
| `log_change_3m_pct` | 61 | 4 |
| `log_change_12m_pct` | 52 | 13 |
| `realized_volatility_3m_pct` | 60 | 5 |
| `total` | 299 | 26 |

Across both channels: **650** grid rows, **598** finite, **52** null.

## Availability

`policy_available_month` = max_policy_month_over_required_source_inputs.
The equality `policy_available_month == reference_month + 2 months` is **verified**,
not hard-coded.

`source_available_as_of` stays null: EPPO release timing was never measured,
and the conservative policy month is not a release date.

## What C8 does not do

No industry exposure multiplication, no industry-conditioned matrix, no MPI
join, no target association, no model, no locked-test access. The two fuel
oils share I/O sector 093 and are never added, averaged, indexed or entered
together.

