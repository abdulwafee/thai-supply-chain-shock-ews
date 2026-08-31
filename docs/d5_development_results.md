# Task D5 - Development-Only Pooled Fuel-Oil Interaction Results

*Generated 2026-08-30T02:26:29.047289+00:00. Config `d5_fuel_oil_interaction_v1`.*

Frozen protocol `13a0b1846df33f2d81eae8be8415b66bdeaef1bb20642e0a07645774c624483a`. Estimator `fixed_pooled_partial_ridge_v1`, lambda `1.0`, no search of any kind.

**Development-only and exploratory.** FO 600 and FO 1500 are reported
side by side as co-equal variants. No channel is selected, no purge
origin is evaluated, the locked test is closed, and no result here
approves a model feature or supports a confirmatory claim.

## Headline

| variant | h | model macro MAE | benchmark macro MAE | paired delta | 95% paired interval | MAE evidence | event safety | status |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `fo1500_direct_sector093` | 1 | 17.1114 | 17.0945 | 0.0169 | [-0.8221, 0.8474] | **inconclusive** | `False` | **inconclusive** |
| `fo1500_direct_sector093` | 3 | 18.2103 | 16.6338 | 1.5765 | [-0.0961, 3.5889] | **inconclusive** | `False` | **inconclusive** |
| `fo600_direct_sector093` | 1 | 17.1675 | 17.0945 | 0.0730 | [-0.7610, 0.9071] | **inconclusive** | `False` | **inconclusive** |
| `fo600_direct_sector093` | 3 | 18.2073 | 16.6338 | 1.5735 | [-0.0164, 3.5245] | **inconclusive** | `False` | **inconclusive** |

The sign convention is `delta = MAE_model - MAE_benchmark`, so negative
means the model is better. Support requires the **entire** interval below
zero; a lower point estimate whose interval still touches zero is
inconclusive, which on fifteen issue clusters is the common case.

## `fo1500_direct_sector093` - horizon 1

Primary benchmark `operational_persistence_latest_published`, full 180-row twelve-industry panel.

| metric | model | benchmark |
| --- | ---: | ---: |
| macro-industry MAE (primary) | 17.1114 | 17.0945 |
| pooled MAE | 17.1114 | 17.0945 |
| macro RMSE | 21.0317 | 20.7427 |
| pooled RMSE | 21.7763 | 21.3675 |
| median absolute error | 14.0104 | 14.9324 |
| Spearman correlation | 0.7210 | 0.6918 |
| clipped count | 19 | 0 |
| clipped rate | 0.1056 | 0.0000 |
| MAE skill vs primary benchmark | -0.0010 | - |

### Event safety (high stress >= 85, threshold frozen)

| quantity | model | benchmark |
| --- | ---: | ---: |
| observed events | 21 | 21 |
| predicted events | 18 | 23 |
| precision | 0.5556 | 0.5652 |
| recall | 0.4762 | 0.6190 |
| false negatives | **11** | **8** |
| false positives | 8 | 10 |

`event_safety_passed`: `False` (model false negatives <= benchmark false negatives). Severe stress >= 95 is descriptive only: observed 12, model predicted 8, benchmark predicted 12. It affects no decision.

### Uncertainty

| interval | low | point | high |
| --- | ---: | ---: | ---: |
| model macro MAE | 15.0914 | 17.1114 | 19.3892 |
| benchmark macro MAE | 15.2074 | 17.0945 | 19.0288 |
| paired model - benchmark | -0.8221 | 0.0169 | 0.8474 |

Method `issue_month_cluster_bootstrap`, block length 1, 1000 replications, seed 20260830, clustered by `issue_month` with all industries kept together. The model beats the benchmark in **6 of 15** issue months.

> Fifteen issue clusters provide limited uncertainty resolution; these intervals are wide by construction.

### Secondary comparator

Against `operational_no_contraction`: model macro MAE 17.1114 versus 19.4453, paired interval [-5.7310, 1.6961], evidence **inconclusive**.

## `fo1500_direct_sector093` - horizon 3

Primary benchmark `operational_persistence_trailing_3m_max`, full 180-row twelve-industry panel.

| metric | model | benchmark |
| --- | ---: | ---: |
| macro-industry MAE (primary) | 18.2103 | 16.6338 |
| pooled MAE | 18.2103 | 16.6338 |
| macro RMSE | 22.2278 | 21.2359 |
| pooled RMSE | 23.9207 | 22.8624 |
| median absolute error | 14.3185 | 13.2353 |
| Spearman correlation | 0.6850 | 0.6693 |
| clipped count | 13 | 0 |
| clipped rate | 0.0722 | 0.0000 |
| MAE skill vs primary benchmark | -0.0948 | - |

### Event safety (high stress >= 85, threshold frozen)

| quantity | model | benchmark |
| --- | ---: | ---: |
| observed events | 28 | 28 |
| predicted events | 29 | 40 |
| precision | 0.6207 | 0.6000 |
| recall | 0.6429 | 0.8571 |
| false negatives | **10** | **4** |
| false positives | 11 | 16 |

`event_safety_passed`: `False` (model false negatives <= benchmark false negatives). Severe stress >= 95 is descriptive only: observed 21, model predicted 15, benchmark predicted 29. It affects no decision.

### Uncertainty

| interval | low | point | high |
| --- | ---: | ---: | ---: |
| model macro MAE | 14.6610 | 18.2103 | 20.8779 |
| benchmark macro MAE | 13.5276 | 16.6338 | 18.5695 |
| paired model - benchmark | -0.0961 | 1.5765 | 3.5889 |

Method `moving_block_issue_month_bootstrap`, block length 3, 1000 replications, seed 20260830, clustered by `issue_month` with all industries kept together. The model beats the benchmark in **4 of 15** issue months.

> Fifteen issue clusters provide limited uncertainty resolution; these intervals are wide by construction.

### Secondary comparator

Against `operational_no_contraction`: model macro MAE 18.2103 versus 16.9791, paired interval [-3.1713, 3.7781], evidence **inconclusive**.

## `fo600_direct_sector093` - horizon 1

Primary benchmark `operational_persistence_latest_published`, full 180-row twelve-industry panel.

| metric | model | benchmark |
| --- | ---: | ---: |
| macro-industry MAE (primary) | 17.1675 | 17.0945 |
| pooled MAE | 17.1675 | 17.0945 |
| macro RMSE | 21.0499 | 20.7427 |
| pooled RMSE | 21.8090 | 21.3675 |
| median absolute error | 14.3625 | 14.9324 |
| Spearman correlation | 0.7202 | 0.6918 |
| clipped count | 18 | 0 |
| clipped rate | 0.1000 | 0.0000 |
| MAE skill vs primary benchmark | -0.0043 | - |

### Event safety (high stress >= 85, threshold frozen)

| quantity | model | benchmark |
| --- | ---: | ---: |
| observed events | 21 | 21 |
| predicted events | 18 | 23 |
| precision | 0.5556 | 0.5652 |
| recall | 0.4762 | 0.6190 |
| false negatives | **11** | **8** |
| false positives | 8 | 10 |

`event_safety_passed`: `False` (model false negatives <= benchmark false negatives). Severe stress >= 95 is descriptive only: observed 12, model predicted 8, benchmark predicted 12. It affects no decision.

### Uncertainty

| interval | low | point | high |
| --- | ---: | ---: | ---: |
| model macro MAE | 15.1072 | 17.1675 | 19.4619 |
| benchmark macro MAE | 15.2074 | 17.0945 | 19.0288 |
| paired model - benchmark | -0.7610 | 0.0730 | 0.9071 |

Method `issue_month_cluster_bootstrap`, block length 1, 1000 replications, seed 20260830, clustered by `issue_month` with all industries kept together. The model beats the benchmark in **8 of 15** issue months.

> Fifteen issue clusters provide limited uncertainty resolution; these intervals are wide by construction.

### Secondary comparator

Against `operational_no_contraction`: model macro MAE 17.1675 versus 19.4453, paired interval [-5.6759, 1.7442], evidence **inconclusive**.

## `fo600_direct_sector093` - horizon 3

Primary benchmark `operational_persistence_trailing_3m_max`, full 180-row twelve-industry panel.

| metric | model | benchmark |
| --- | ---: | ---: |
| macro-industry MAE (primary) | 18.2073 | 16.6338 |
| pooled MAE | 18.2073 | 16.6338 |
| macro RMSE | 22.1136 | 21.2359 |
| pooled RMSE | 23.8203 | 22.8624 |
| median absolute error | 13.9336 | 13.2353 |
| Spearman correlation | 0.6873 | 0.6693 |
| clipped count | 14 | 0 |
| clipped rate | 0.0778 | 0.0000 |
| MAE skill vs primary benchmark | -0.0946 | - |

### Event safety (high stress >= 85, threshold frozen)

| quantity | model | benchmark |
| --- | ---: | ---: |
| observed events | 28 | 28 |
| predicted events | 30 | 40 |
| precision | 0.6000 | 0.6000 |
| recall | 0.6429 | 0.8571 |
| false negatives | **10** | **4** |
| false positives | 12 | 16 |

`event_safety_passed`: `False` (model false negatives <= benchmark false negatives). Severe stress >= 95 is descriptive only: observed 21, model predicted 15, benchmark predicted 29. It affects no decision.

### Uncertainty

| interval | low | point | high |
| --- | ---: | ---: | ---: |
| model macro MAE | 14.7165 | 18.2073 | 20.7954 |
| benchmark macro MAE | 13.5276 | 16.6338 | 18.5695 |
| paired model - benchmark | -0.0164 | 1.5735 | 3.5245 |

Method `moving_block_issue_month_bootstrap`, block length 3, 1000 replications, seed 20260830, clustered by `issue_month` with all industries kept together. The model beats the benchmark in **3 of 15** issue months.

> Fifteen issue clusters provide limited uncertainty resolution; these intervals are wide by construction.

### Secondary comparator

Against `operational_no_contraction`: model macro MAE 18.2073 versus 16.9791, paired interval [-3.1032, 3.7166], evidence **inconclusive**.

## Eligible-only diagnostic (secondary, preregistered)

Eleven modelled industries, IND-04 excluded. This is a **diagnostic** and
cannot replace the full twelve-industry result above.

| variant | h | model macro MAE | benchmark macro MAE | paired interval | evidence |
| --- | ---: | ---: | ---: | --- | --- |
| `fo1500_direct_sector093` | 1 | 17.1483 | 17.1299 | [-0.8968, 0.9244] | inconclusive |
| `fo1500_direct_sector093` | 3 | 19.1372 | 17.4173 | [-0.1049, 3.9152] | inconclusive |
| `fo600_direct_sector093` | 1 | 17.2095 | 17.1299 | [-0.8302, 0.9895] | inconclusive |
| `fo600_direct_sector093` | 3 | 19.1339 | 17.4173 | [-0.0179, 3.8449] | inconclusive |

## Per-industry MAE, full panel

| variant | h | industry | model | benchmark |
| --- | ---: | --- | ---: | ---: |
| `fo1500_direct_sector093` | 1 | `IND-01` | 20.8738 | 21.7039 |
| `fo1500_direct_sector093` | 1 | `IND-02` | 16.1521 | 15.7450 |
| `fo1500_direct_sector093` | 1 | `IND-03` | 15.0032 | 13.5441 |
| `fo1500_direct_sector093` | 1 | `IND-04` | 16.7053 | 16.7053 |
| `fo1500_direct_sector093` | 1 | `IND-05` | 28.8101 | 22.6505 |
| `fo1500_direct_sector093` | 1 | `IND-06` | 21.0391 | 24.8361 |
| `fo1500_direct_sector093` | 1 | `IND-07` | 13.9835 | 16.0102 |
| `fo1500_direct_sector093` | 1 | `IND-08` | 12.7717 | 17.0385 |
| `fo1500_direct_sector093` | 1 | `IND-09` | 9.7937 | 9.8767 |
| `fo1500_direct_sector093` | 1 | `IND-10` | 15.2838 | 14.0461 |
| `fo1500_direct_sector093` | 1 | `IND-11` | 16.9354 | 14.6437 |
| `fo1500_direct_sector093` | 1 | `IND-12` | 17.9848 | 18.3336 |
| `fo1500_direct_sector093` | 3 | `IND-01` | 33.9837 | 32.1497 |
| `fo1500_direct_sector093` | 3 | `IND-02` | 14.1763 | 14.7921 |
| `fo1500_direct_sector093` | 3 | `IND-03` | 12.8312 | 10.2743 |
| `fo1500_direct_sector093` | 3 | `IND-04` | 8.0149 | 8.0149 |
| `fo1500_direct_sector093` | 3 | `IND-05` | 22.1843 | 17.3082 |
| `fo1500_direct_sector093` | 3 | `IND-06` | 19.6328 | 18.3714 |
| `fo1500_direct_sector093` | 3 | `IND-07` | 9.1563 | 12.3234 |
| `fo1500_direct_sector093` | 3 | `IND-08` | 17.3593 | 16.7020 |
| `fo1500_direct_sector093` | 3 | `IND-09` | 12.8551 | 16.0963 |
| `fo1500_direct_sector093` | 3 | `IND-10` | 30.1286 | 29.1788 |
| `fo1500_direct_sector093` | 3 | `IND-11` | 19.7080 | 12.3113 |
| `fo1500_direct_sector093` | 3 | `IND-12` | 18.4933 | 12.0832 |
| `fo600_direct_sector093` | 1 | `IND-01` | 21.1979 | 21.7039 |
| `fo600_direct_sector093` | 1 | `IND-02` | 16.3186 | 15.7450 |
| `fo600_direct_sector093` | 1 | `IND-03` | 14.8721 | 13.5441 |
| `fo600_direct_sector093` | 1 | `IND-04` | 16.7053 | 16.7053 |
| `fo600_direct_sector093` | 1 | `IND-05` | 28.8659 | 22.6505 |
| `fo600_direct_sector093` | 1 | `IND-06` | 21.0319 | 24.8361 |
| `fo600_direct_sector093` | 1 | `IND-07` | 14.1353 | 16.0102 |
| `fo600_direct_sector093` | 1 | `IND-08` | 12.7548 | 17.0385 |
| `fo600_direct_sector093` | 1 | `IND-09` | 9.7144 | 9.8767 |
| `fo600_direct_sector093` | 1 | `IND-10` | 15.5755 | 14.0461 |
| `fo600_direct_sector093` | 1 | `IND-11` | 16.9360 | 14.6437 |
| `fo600_direct_sector093` | 1 | `IND-12` | 17.9021 | 18.3336 |
| `fo600_direct_sector093` | 3 | `IND-01` | 34.0000 | 32.1497 |
| `fo600_direct_sector093` | 3 | `IND-02` | 13.8246 | 14.7921 |
| `fo600_direct_sector093` | 3 | `IND-03` | 12.4609 | 10.2743 |
| `fo600_direct_sector093` | 3 | `IND-04` | 8.0149 | 8.0149 |
| `fo600_direct_sector093` | 3 | `IND-05` | 22.4225 | 17.3082 |
| `fo600_direct_sector093` | 3 | `IND-06` | 19.7728 | 18.3714 |
| `fo600_direct_sector093` | 3 | `IND-07` | 9.2707 | 12.3234 |
| `fo600_direct_sector093` | 3 | `IND-08` | 17.2432 | 16.7020 |
| `fo600_direct_sector093` | 3 | `IND-09` | 12.5218 | 16.0963 |
| `fo600_direct_sector093` | 3 | `IND-10` | 30.1300 | 29.1788 |
| `fo600_direct_sector093` | 3 | `IND-11` | 20.0390 | 12.3113 |
| `fo600_direct_sector093` | 3 | `IND-12` | 18.7872 | 12.0832 |

## Decision

| field | value |
| --- | --- |
| `channel_selected` | `False` |
| `model_feature_approved` | `False` |
| `locked_evaluation_authorized` | `False` |
| `confirmatory_claim_made` | `False` |

> A development result of any sign selects no channel, approves no feature and opens no locked test. D5 holds none of those authorizations.

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

Content checksum `0eb3d613d34fdde2274a56c2bcd97695b652991da663ce6390b70d9e53deaf0e`.

