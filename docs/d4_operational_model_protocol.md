# Task D4 — Operational Model Protocol

The frozen specification for the release-aware commodity model, and the rules
that decide what its numbers are allowed to mean.

Contract: [`configs/d4_operational_model.yaml`](../configs/d4_operational_model.yaml).
Schema: [`schemas/operational_model_prediction.schema.yaml`](../schemas/operational_model_prediction.schema.yaml).
Results: [`d4_operational_model_results.md`](d4_operational_model_results.md).
Operational contract: [`d3_operational_evaluation_protocol.md`](d3_operational_evaluation_protocol.md).

```bash
python scripts/run_d4_operational_model.py
```

---

## 1. This is exploratory, and that is not a formality

The specification below — alpha 100.0, channel `none` — is D1's preregistered
conservative fallback. But **D1's development results had already been observed
when D4 froze it.** Choosing a specification after seeing outcomes is not
preregistration, whatever its provenance, so:

* `specification_frozen_after_d1_results: true`
* `confirmatory_evaluation: false`
* `exploratory_development_evaluation: true`
* `locked_test_eligible: false`

No result in D4 can make the model locked-test eligible or production-approved.
The fallback was reused precisely to **avoid inventing a tuning process** that
15 origins cannot support — D2 established the history cannot be extended, so a
genuine nested selection has nowhere to come from.

## 2. The frozen specification

One model, no knobs. `fit_fixed_operational_ridge` **raises** if a different
alpha or channel is passed; it does not quietly accept one.

| field | value |
| --- | --- |
| alpha | **100.0** |
| fit intercept | true |
| non-ferrous channel | **`none`** |
| commodities | Brent, Rubber RSS3 (where C3-R1 permits) |
| per industry / per horizon / refit per origin | yes |
| hyperparameter search | **none** |
| inner cross-validation | **none** |
| model averaging | **none** |
| outcome-based feature selection | **none** |

### Why Aluminum and Copper are excluded outright

They read the **same I/O sector 107** coefficient. Admitting either would allow
one shared exposure to be counted twice, a channel to be chosen on outcomes, and
two series to be reported as independent measurements. Excluding both removes
the choice rather than managing it. The exclusion is asserted separately against
the training matrix, the evaluation row, the scaler and the fitted artifact, so
no single check is load-bearing.

Excluded and ineligible predictors are **omitted, never zero-filled**. A zero is
a claim about the world; an omission is a claim about knowledge.

## 3. Predictors

All five registered C2 transformations for every eligible commodity:
`price_level`, `log_change_1m_pct`, `log_change_3m_pct`, `log_change_12m_pct`,
`realized_volatility_3m_pct`.

* **11 industries** are offered 5 Brent + 5 Rubber = **10** predictors.
* **IND-06** is offered **5 Brent only** — C3-R1 marks Rubber directionally
  ineligible there (`mixed_or_ambiguous`, null sign). Its five Rubber
  transformations are recorded in `omitted_ineligible_predictors`.

No imputation, forward-fill, interpolation, PCA, composite index, or
cross-commodity normalization.

### Structurally zero exposures

C3's **direct** exposure is exactly zero for many industry–commodity pairs. A
zero exposure makes the conditioned predictor a constant, and the registered
X-only zero-variance rule removes it. Where **every** predictor for an industry
is such a constant, no model can be fitted at all: the residual is `0.0` and the
prediction equals the D3 benchmark exactly, recorded as
`model_quality: degenerate_all_predictors_constant_benchmark_only`.

This follows D1's registered precedent for a degenerate design and is **not** a
tuning choice. It is reported prominently because it determines how much of the
panel the commodity features can influence at all.

## 4. Operational assembly

At outer issue origin *t* and historical training origin *u*:

| quantity | rule |
| --- | --- |
| calibrator | `stress_month <= t-1` |
| evaluation benchmark | D3 operational persistence at *t* (stress ≤ *t-1*) |
| historical benchmark | reconstructed at *u* using stress ≤ *u-1* |
| training labels | `target_available_month <= t` |
| historical features | `conditioned_available_month <= u` — **not** *t* |
| evaluation features | `conditioned_available_month <= t` |

The historical-feature rule is the subtle one and it is unchanged from D1's
hardest lesson: refreshing row *u* with everything known at *t* would make the
model learn from a version of history that never existed.

The evaluation target is read **only after** the calibrator, the D3 benchmark,
the feature snapshot, the scaler, the model and the prediction are all frozen.

## 5. Residual formula

At outer origin *t*, every permitted historical raw target is transformed with
the calibrator frozen at *t-1*, and so is the reconstructed historical
benchmark — a residual computed across two different scales would not be a
residual.

```
r_{i,u,h}^(t) = y_{i,u,h}^(t) − b_{i,u,h}^(t)
ŷ_{i,t,h}     = b_{i,t,h}^{D3} + r̂_{i,t,h}
```

Final scores are clipped deterministically to `[0, 100]`. The bounds are **not**
tuned.

## 6. Training counts

The lag-2 registered set first completes at **2022-03**, so origins 2022-01 and
2022-02 are excluded as `insufficient_registered_feature_history` — 24 rows per
horizon, retained in the audit and never imputed.

| horizon, outer origin | label-permitted | feature-usable | brief expected |
| --- | ---: | ---: | ---: |
| h=1 at 2024-01 | 276 | **252** | 252 ✔ |
| h=1 at 2025-03 | 444 | **420** | 420 ✔ |
| h=3 at 2024-01 | 252 | **216** | 228 ✘ |
| h=3 at 2025-03 | 420 | **384** | 396 ✘ |

**h=3 loses one origin the brief did not anticipate.** The operational h=3
benchmark reads `max(S_{u-3}, S_{u-2}, S_{u-1})`. At *u* = 2022-03 that window
reaches 2021-12, which is **before B3's stress series begins** in 2022-01, so no
achievable benchmark exists there and no residual can be defined against one.
That is a series-start boundary, not a release-timing violation, and the two are
kept as distinct exclusion reasons
(`insufficient_operational_benchmark_history`). The row is excluded and
reported, never imputed and never back-filled.

## 7. Variants

Exactly three. The combination `lag1 + total_requirement` is **not** built.

| variant | role |
| --- | --- |
| `primary_direct_lag2` | **determines the evidence status, alone** |
| `timing_sensitivity_direct_lag1` | reported separately |
| `structural_sensitivity_total_lag2` | reported separately |

### Day-level timing check

The lag-1 variant claims a feature for reference month *t-1* is usable at issue
month *t*. That is only true if the Pink Sheet issue carrying *t-1* was
published **on or before** the verified OIE issue date. Each origin is checked
against C1.5's archived-issue dates; an origin without verified day-level
evidence is marked **unavailable**, never imputed and never substituted with
primary values.

Sensitivities cannot replace the primary, change its status, or select a model,
lag, commodity or exposure definition.

## 8. Metrics and uncertainty

Primary: **macro industry MAE**. Also pooled MAE, macro and pooled RMSE, median
absolute error, pooled Spearman, per-industry MAE, DEV-1/2/3 blocks, and clipped
counts. High-stress events at **score ≥ 85** (never tuned); Severe ≥ 95
descriptive only.

Bootstrap: moving-block, clustered by **issue month**, all 12 industries kept
together, block length 3, 1,000 replications, fixed seed. 180 rows are **15
dependent clusters**, not 180 independent observations.

A **negative** paired difference means the model is better.

## 9. Two separate decisions

**MAE evidence**

* `incremental_signal_supported` — model MAE lower **and** the entire paired 95%
  CI below zero;
* `incremental_signal_inconclusive` — lower point estimate, CI includes zero;
* `incremental_signal_not_supported` — point estimate equal or worse.

**Event safety**

* `event_safety_passed` — model false negatives ≤ persistence;
* `event_safety_failed` — model false negatives exceed persistence.

They are separate because a model can be more accurate on average while missing
more high-stress months, and for an early-warning system that is the expensive
error. `development_candidate_supported` requires **both**.

Unconditionally, whatever the gates say: `approved_for_locked_test: false`,
`production_model_approved: false`, `confirmatory_result: false`.

## 10. Comparators

Primary comparator is the selected D3 operational persistence benchmark
(`operational_persistence_latest_published` at h=1,
`operational_persistence_trailing_3m_max` at h=3). Secondary comparator is
`operational_no_contraction`, reported alongside.

Per D3-R1, the persistence/no-contraction MAE difference is inconclusive on this
sample; that does **not** change which comparator is primary.

## 11. The locked final test

Not reachable. D4 evaluates development origins only, exposes no flag or
environment variable, and asserts `locked_test_accessed: false` on every row.
The locked final test remains **unopened**.
