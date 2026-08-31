# Task D3 — Operational Evaluation Protocol

The preregistered rules for the release-aware evaluation contract. Written
before any operational metric was produced.

Contract: [`configs/operational_evaluation.yaml`](../configs/operational_evaluation.yaml).
Schema: [`schemas/operational_prediction.schema.yaml`](../schemas/operational_prediction.schema.yaml).
Results: [`d3_operational_baseline_results.md`](d3_operational_baseline_results.md).
Timing evidence: [`d2_target_timing_decision.md`](d2_target_timing_decision.md).

```bash
python scripts/run_d3_operational_baselines.py
```

---

## 1. Why B4 had to be replaced

B4 issued a forecast at origin *t* using stress month *t*. D2 (AD-R59) measured
what OIE actually does: reference month *t* is first published a **median 29
days after *t* ends**, during month *t+1*. At origin *t* that value did not
exist. B4's benchmark was therefore reading a number from the future — by one
month, consistently, at every origin.

B4 and D1 are **not deleted and not edited**. They remain reproducible exactly
as they were, relabelled `non_operational_calendar_boundary_experiment`.
Rewriting them would have destroyed the evidence that the defect existed. D3 is
a **new versioned contract**, `operational_contract_v1`, that runs alongside.

## 2. The operational forecast origin

At forecast **issue month** *t*:

| concept | value |
| --- | --- |
| `forecast_issue_date` | the verified OIE release, during *t*, of reference month *t-1* |
| `latest_available_stress_month` | *t-1* |
| `calibration_reference_end` | *t-1* |
| h=1 target | *t+1* |
| h=3 target window | *t+1* … *t+3* |

The forecast is issued **near the end of month *t***, after OIE publishes
*t-1*. **It is not a nowcast of month *t*.** Month *t* is unobserved at issue
time, is never predicted, and is simply skipped over — the model jumps from the
last published month *t-1* to the target at *t+1*.

### Seven concepts, kept distinct

Collapsing any two of these is precisely how the original error entered, so they
are separate fields in the contract, the schema and the prediction table:

1. **reference month** — the month an MPI value describes
2. **publication date** — when OIE first published it
3. **publication month** — the calendar month containing that date
4. **forecast issue month** — *t*
5. **latest observable stress month** — *t-1*
6. **target month / window** — *t+1*, or *t+1…t+3*
7. **target availability month** — `target_window_end + 1`

### What raises

Nothing degrades quietly to a "safe" value, because a quiet degradation is
indistinguishable from the bug it prevents. The contract raises on: an
unresolved release date; a release record whose reference month is not *t-1*;
publication after the registered issue date; any request for current-month
stress; a later stress month entering calibration or baseline construction; and
a training label whose availability month exceeds the issue month.

## 3. Three cutoffs, three separate enforcement points

They are enforced in three different places on purpose, so they cannot silently
drift into one another:

| # | cutoff | rule | enforced in |
| --- | --- | --- | --- |
| 1 | stress map | `reference_month <= t-1` | `assert_no_future_stress` |
| 2 | calibrator | `training_cutoff_month = t-1` | `operational_walk_forward` |
| 3 | training labels | `target_available_month <= t` | `assert_labels_available` |

## 4. Calibration

A **fresh** `IndustryStressCalibrator` at every origin, fitted on
`stress_month <= t-1`, minimum **24** observations per industry, frozen before
any prediction is produced. Historical labels are transformed with that same
frozen calibrator; the evaluation target is transformed **only after every
prediction at the origin is frozen**.

| issue origin | reference end | observations per industry |
| --- | --- | ---: |
| 2024-01 | 2023-12 | 24 |
| 2025-03 | 2025-02 | 38 |

Fifteen origins produce **fifteen distinct** calibrator fingerprints; reusing
one global calibrator is a failure, not an optimisation.

### Why B3's calibrated scores are not reused

B3's raw target windows and raw values **are** reused, unchanged. Its
*calibrated* scores are not, because B3's calibrator ran through month *t* while
D3's stops at *t-1*. Reusing them would carry an unpublished month back into the
scale after the whole point of this task was to remove it.

One visible consequence: observed high-stress event counts shift slightly
against B4 (h=1 21 vs 20; h=3 28 vs 29). That is the calibration scale moving,
**not** a target value changing.

## 5. Operational label availability

A label is not available merely because its window closed. If a window ends at
month *e*, its final MPI observation is published during *e+1*:

```
target_available_month = target_window_end + 1 month
target_available_month <= forecast_issue_month
```

This **replaces** B4's `target_window_end <= t`, which admitted exactly 12 rows
per origin (one per industry) whose last observation had not been published.

| horizon, issue origin | latest permitted label origin | rows |
| --- | --- | ---: |
| h=1 at 2024-01 | 2023-11 | 276 |
| h=1 at 2025-03 | 2025-01 | 444 |
| h=3 at 2024-01 | 2023-09 | 252 |
| h=3 at 2025-03 | 2024-11 | 420 |

A label failing the rule **raises**. Silently dropping it would make an
unavailable label indistinguishable from one that never existed.

## 6. The five operational baselines

Two shift by one month; three reuse the production formula unchanged, so there
is one definition of each formula in the codebase.

| baseline | horizons | formula | reused |
| --- | --- | --- | --- |
| `operational_persistence_latest_published` | 1, 3 | `C_t(S_{t-1})` | new |
| `operational_persistence_trailing_3m_max` | 3 | `max{C_t(S_{t-3}), C_t(S_{t-2}), C_t(S_{t-1})}` | new |
| `operational_industry_historical_mean` | 1, 3 | mean of available labels, same industry only | yes |
| `operational_seasonal_naive` | 1, 3 | h=1 `C_t(S_{t-11})`; h=3 `C_t(max(S_{t-11..t-9}))` | yes |
| `operational_no_contraction` | 1, 3 | `C_t(0)` | yes |

`seasonal_naive` needs no shift: *t-11* and *t-9* are both at or before *t-1*.
Publication is enforced **structurally** — the stress map holds only months at
or before *t-1*, so a baseline reaching for *t* raises rather than returning
something. Industries are never pooled and there is no cross-industry fallback.

Nothing is tuned, blended, or weight-averaged.

## 7. Expected counts

| horizon | baselines | rows per baseline | total |
| --- | ---: | ---: | ---: |
| h=1 | 4 | 180 | 720 |
| h=3 | 5 | 180 | 900 |
| combined | — | — | **1,620** |

h=3 carries five because the latest-published persistence runs **alongside** the
trailing-three-month one. Keys are unique on
`(origin, industry, horizon, baseline)`, ordering is deterministic, and no purge
or locked origin appears.

## 8. Metrics and uncertainty

Primary: **macro industry MAE**. Secondary: pooled MAE, macro and pooled RMSE,
median absolute error, pooled Spearman, per-industry MAE, and DEV-1/DEV-2/DEV-3
blocks. High-stress events at **score ≥ 85** (threshold never tuned): observed
and predicted counts, precision, recall, F1, PR-AUC where defined, and false
negatives. Severe ≥ 95 is descriptive only.

Bootstrap: B4's moving-block procedure, clustered by **issue month**, all 12
industries kept together, block length **3**, **1,000** replications, fixed
documented seed.

## 9. Benchmark selection

Independently per horizon, on **development data only**:

1. lowest macro industry MAE;
2. if effectively tied (`1e-6`), fewer false negatives at score ≥ 85;
3. if still tied, the simpler baseline.

Purge outcomes, locked outcomes, D1 model performance, sensitivity variants and
B4's current-month persistence are all excluded from selection. B4's benchmark
appears **only** as a historical non-operational reference.

```
operational penalty = D3 selected benchmark MAE − B4 selected benchmark MAE
```

**This is not attributable to publication lag alone.** The calibrator cutoff and
the label-availability rule changed in the same step, so the penalty is a joint
effect of all three changes.

## 10. Contract status

`operational_month_timing_supported` requires all development issue dates
verified, every input obeying release timing, no same-month stress used, and
label availability enforced.

Reported **separately, never merged into one boolean**:

* `point_in_time_values_supported: false`
* `latest_vintage_evaluation: true`
* `fully_real_time_backtest: false`

Honest timing is not point-in-time data. D2 (AD-R62) found no complete
12-industry MPI vintages exist, so the target **values** remain latest-vintage.
The framing is `release_lag_aware_latest_vintage_evaluation` and must not be
described as a real-time or point-in-time backtest.

## 11. The locked final test

Locked months are rejected inside `build_origin_contracts` **before any data is
read** — no end-stage filter is load-bearing. The runner exposes no flag,
environment variable, function argument or alternate code path that reaches a
locked origin. [`d3_locked_test_manifest.json`](d3_locked_test_manifest.json) is
key-only: reserved month keys, no observed value, prediction or metric.

The locked final test remains **unopened**.
