# Task D4 — Frozen-Specification Operational Model Results

*Generated 2026-08-28T08:32:55.235267+00:00. Model `operational_fixed_ridge_residual_v1`.*

> **Exploratory, not confirmatory.** The specification was frozen *after* D1's
> development results were observed, so nothing here is a confirmatory test and
> no outcome makes the model locked-test eligible.

## Frozen specification

alpha **100.0**, channel **`none`**, commodities **brent_crude_usd_bbl, rubber_rss3_usd_kg**.
Aluminum and Copper excluded (`shared_io_sector_107_used: False`). No hyperparameter search, no inner
validation, no model averaging, no outcome-based feature selection.

## Prediction counts

* `primary_direct_lag2__h1`: 180
* `primary_direct_lag2__h3`: 180
* `structural_sensitivity_total_lag2__h1`: 180
* `structural_sensitivity_total_lag2__h3`: 180
* `timing_sensitivity_direct_lag1__h1`: 180
* `timing_sensitivity_direct_lag1__h3`: 180
* **total**: 1080

## h=1

| series | macro MAE | pooled MAE | macro RMSE | median AE | Spearman | FN | clipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **model** | 17.5616 | 17.5616 | 21.5176 | 15.6745 | 0.6838 | 6 | 6 |
| `operational_persistence_latest_published` | 17.0945 | 17.0945 | 20.7427 | 14.9324 | 0.6918 | 8 | 0 |
| `operational_no_contraction` | 19.4453 | 19.4453 | 23.3315 | 14.4958 | 0.6059 | 21 | 0 |

Model macro MAE 95% CI: **[15.1720, 20.1148]**.

* vs operational persistence: paired **+0.4672** CI [-0.2060, 1.3736] (inconclusive); skill -0.0273
* vs no-contraction: paired **-1.8837** CI [-6.3428, 3.1151] (inconclusive); skill +0.0969

**MAE evidence: `incremental_signal_not_supported`.**
**Event safety: `event_safety_passed`** (model 6 FN vs benchmark 8 FN).
**Development candidate supported: `False`.**

### Sensitivities — reported separately, cannot change the primary status

| variant | rows | macro MAE | FN |
| --- | ---: | ---: | ---: |
| `structural_sensitivity_total_lag2` | 180 | 18.0460 | 6 |
| `timing_sensitivity_direct_lag1` | 180 | 17.0253 | 6 |

## h=3

| series | macro MAE | pooled MAE | macro RMSE | median AE | Spearman | FN | clipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **model** | 17.9051 | 17.9051 | 22.7863 | 13.9093 | 0.6550 | 1 | 1 |
| `operational_persistence_trailing_3m_max` | 16.6338 | 16.6338 | 21.2359 | 13.2353 | 0.6693 | 4 | 0 |
| `operational_no_contraction` | 16.9791 | 16.9791 | 19.9844 | 12.7016 | 0.7034 | 28 | 0 |

Model macro MAE 95% CI: **[14.5564, 20.4065]**.

* vs operational persistence: paired **+1.2713** CI [0.4317, 2.1098] (excludes_zero); skill -0.0764
* vs no-contraction: paired **+0.9260** CI [-3.7284, 3.5007] (inconclusive); skill -0.0545

**MAE evidence: `incremental_signal_not_supported`.**
**Event safety: `event_safety_passed`** (model 1 FN vs benchmark 4 FN).
**Development candidate supported: `False`.**

### Sensitivities — reported separately, cannot change the primary status

| variant | rows | macro MAE | FN |
| --- | ---: | ---: | ---: |
| `structural_sensitivity_total_lag2` | 180 | 18.1751 | 1 |
| `timing_sensitivity_direct_lag1` | 180 | 17.3063 | 1 |

## Safety

* `approved_for_locked_test`: `False`
* `production_model_approved`: `False`
* `confirmatory_result`: `False`
* `upstream_feature_eligibility_modified`: `False`
* `locked_test_accessed`: `False`
