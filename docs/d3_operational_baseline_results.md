# Task D3 — Operational Baseline Results

*Generated 2026-08-28T04:42:11.801367+00:00. Contract `operational_contract_v1`.*

**Framing: `release_lag_aware_latest_vintage_evaluation`.**

Release timing is now honoured: at forecast issue month *t* the newest
published MPI stress month is *t-1*, and the forecast is issued after the
verified OIE release of *t-1*. The target **values** are still latest-vintage,
because D2 found no complete 12-industry MPI vintages exist. This is **not** a
fully real-time or point-in-time backtest.

| flag | value |
| --- | --- |
| `evaluation_framing` | `release_lag_aware_latest_vintage_evaluation` |
| `release_timing_aware` | `True` |
| `latest_vintage_target_values` | `True` |
| `point_in_time_target_values` | `False` |
| `fully_real_time_backtest` | `False` |
| `same_month_stress_used` | `False` |
| `locked_test_accessed` | `False` |

## Contract status: `operational_month_timing_supported`

* `all_development_issue_dates_verified`: `True`
* `no_same_month_stress_used`: `True`
* `label_availability_enforced`: `True`
* `point_in_time_values_supported`: `False`
* `latest_vintage_evaluation`: `True`
* `fully_real_time_backtest`: `False`

## Forecast origins

| issue month *t* | issue date | latest stress *t-1* | calib end | obs | h=1 target | h=3 window |
| --- | --- | --- | --- | ---: | --- | --- |
| 2024-01 | 2024-01-31 | 2023-12 | 2023-12 | — | 2024-02 | 2024-02..2024-04 |
| 2024-02 | 2024-02-29 | 2024-01 | 2024-01 | — | 2024-03 | 2024-03..2024-05 |
| 2024-03 | 2024-03-28 | 2024-02 | 2024-02 | — | 2024-04 | 2024-04..2024-06 |
| 2024-04 | 2024-04-30 | 2024-03 | 2024-03 | — | 2024-05 | 2024-05..2024-07 |
| 2024-05 | 2024-05-30 | 2024-04 | 2024-04 | — | 2024-06 | 2024-06..2024-08 |
| 2024-06 | 2024-06-28 | 2024-05 | 2024-05 | — | 2024-07 | 2024-07..2024-09 |
| 2024-07 | 2024-07-31 | 2024-06 | 2024-06 | — | 2024-08 | 2024-08..2024-10 |
| 2024-08 | 2024-08-30 | 2024-07 | 2024-07 | — | 2024-09 | 2024-09..2024-11 |
| 2024-09 | 2024-09-26 | 2024-08 | 2024-08 | — | 2024-10 | 2024-10..2024-12 |
| 2024-10 | 2024-10-30 | 2024-09 | 2024-09 | — | 2024-11 | 2024-11..2025-01 |
| 2024-11 | 2024-11-27 | 2024-10 | 2024-10 | — | 2024-12 | 2024-12..2025-02 |
| 2024-12 | 2024-12-27 | 2024-11 | 2024-11 | — | 2025-01 | 2025-01..2025-03 |
| 2025-01 | 2025-01-30 | 2024-12 | 2024-12 | — | 2025-02 | 2025-02..2025-04 |
| 2025-02 | 2025-02-27 | 2025-01 | 2025-01 | — | 2025-03 | 2025-03..2025-05 |
| 2025-03 | 2025-03-28 | 2025-02 | 2025-02 | — | 2025-04 | 2025-04..2025-06 |

## Prediction counts

h=1 **720**, h=3 **900**, combined **1620**.

## h=1 development metrics

| baseline | macro MAE | pooled MAE | macro RMSE | pooled RMSE | median AE | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `operational_persistence_latest_published` | **17.0945** | 17.0945 | 20.7427 | 21.3675 | 14.9324 | 0.6918 |
| `operational_no_contraction` | **19.4453** | 19.4453 | 23.3315 | 24.6617 | 14.4958 | 0.6059 |
| `operational_industry_historical_mean` | **27.9676** | 27.9676 | 31.7173 | 32.2969 | 28.6987 | -0.5601 |
| `operational_seasonal_naive` | **40.1300** | 40.1300 | 46.3414 | 46.7784 | 36.2069 | -0.2294 |

### High-stress events (score >= 85)

| baseline | observed | predicted | precision | recall | F1 | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `operational_persistence_latest_published` | 21 | 23 | 0.5652 | 0.6190 | 0.5909 | 8 |
| `operational_no_contraction` | 21 | 0 | — | 0.0000 | — | 21 |
| `operational_industry_historical_mean` | 21 | 0 | — | 0.0000 | — | 21 |
| `operational_seasonal_naive` | 21 | 29 | 0.0345 | 0.0476 | 0.0400 | 20 |

### Macro MAE 95% bootstrap intervals

| baseline | macro MAE | 95% CI |
| --- | ---: | --- |
| `operational_persistence_latest_published` | 17.0945 | [14.8919, 19.4720] |
| `operational_no_contraction` | 19.4453 | [16.7676, 21.5157] |
| `operational_industry_historical_mean` | 27.9676 | [24.2529, 32.4295] |
| `operational_seasonal_naive` | 40.1300 | [34.7708, 45.9667] |

### Selected operational benchmark

**`operational_persistence_latest_published`** — macro MAE **17.0945**, by rule `lowest_macro_industry_mae`.

Operational penalty vs B4's `persistence_current_month` (14.5287): **+2.5658**.

> NOT attributable solely to publication lag. The calibrator cutoff and the training-label availability rule changed at the same time, so the difference is a joint effect of all three changes.

## h=3 development metrics

| baseline | macro MAE | pooled MAE | macro RMSE | pooled RMSE | median AE | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `operational_persistence_trailing_3m_max` | **16.6338** | 16.6338 | 21.2359 | 22.8624 | 13.2353 | 0.6693 |
| `operational_no_contraction` | **16.9791** | 16.9791 | 19.9844 | 22.4820 | 12.7016 | 0.7034 |
| `operational_persistence_latest_published` | **18.3670** | 18.3670 | 22.3386 | 23.4388 | 15.8929 | 0.6922 |
| `operational_industry_historical_mean` | **29.6379** | 29.6379 | 32.8404 | 34.8008 | 26.7495 | -0.3193 |
| `operational_seasonal_naive` | **37.6109** | 37.6109 | 42.4381 | 44.3580 | 36.4858 | -0.1158 |

### High-stress events (score >= 85)

| baseline | observed | predicted | precision | recall | F1 | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `operational_persistence_trailing_3m_max` | 28 | 40 | 0.6000 | 0.8571 | 0.7059 | 4 |
| `operational_no_contraction` | 28 | 0 | — | 0.0000 | — | 28 |
| `operational_persistence_latest_published` | 28 | 23 | 0.7826 | 0.6429 | 0.7059 | 10 |
| `operational_industry_historical_mean` | 28 | 0 | — | 0.0000 | — | 28 |
| `operational_seasonal_naive` | 28 | 68 | 0.1324 | 0.3214 | 0.1875 | 19 |

### Macro MAE 95% bootstrap intervals

| baseline | macro MAE | 95% CI |
| --- | ---: | --- |
| `operational_persistence_trailing_3m_max` | 16.6338 | [13.5341, 18.7993] |
| `operational_no_contraction` | 16.9791 | [15.3619, 18.4723] |
| `operational_persistence_latest_published` | 18.3670 | [15.8432, 21.8700] |
| `operational_industry_historical_mean` | 29.6379 | [24.0374, 35.2664] |
| `operational_seasonal_naive` | 37.6109 | [30.5158, 44.5430] |

### Selected operational benchmark

**`operational_persistence_trailing_3m_max`** — macro MAE **16.6338**, by rule `lowest_macro_industry_mae`.

Operational penalty vs B4's `persistence_trailing_3m_max` (14.6985): **+1.9353**.

> NOT attributable solely to publication lag. The calibrator cutoff and the training-label availability rule changed at the same time, so the difference is a joint effect of all three changes.

## Locked final test

Reserved and **unopened**. `locked_test_evaluated: false`,
`locked_test_outcomes_read: false`. See
[`d3_locked_test_manifest.json`](d3_locked_test_manifest.json).

## Related

* [`d3_operational_evaluation_protocol.md`](d3_operational_evaluation_protocol.md)
* [`d1_development_results.errata.md`](d1_development_results.errata.md)
* [`d2_target_timing_decision.md`](d2_target_timing_decision.md)
