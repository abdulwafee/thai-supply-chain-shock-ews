# Task B4 — Walk-Forward Evaluation Protocol

The rules a future ML model must be evaluated under. Results live in
[`b4_baseline_results.md`](b4_baseline_results.md); this document is the
protocol itself.

- Config: [`configs/evaluation_splits.yaml`](../configs/evaluation_splits.yaml),
  [`configs/baselines.yaml`](../configs/baselines.yaml)
- Code: `src/thai_supply_chain_ews/evaluation/{splits,walk_forward,baselines,metrics,bootstrap}.py`
- Schema: `schemas/evaluation_prediction.schema.yaml`

```bash
python scripts/run_b4_baselines.py
```

---

## 1. Periods

| Period | Origins | Purpose |
|---|---|---|
| **Development** | 2024-01 … 2025-03 (15 months) | Out-of-fold predictions, metrics, baseline selection |
| **Purge / model-selection buffer** | 2025-04 … 2025-06 (3 months) | No metrics reported. Guarantees every 3-month development window closes before the locked period begins |
| **Locked final test** (h=1) | 2025-07 … 2026-04 (10 months, 120 rows) | **RESERVED — not evaluated** |
| **Locked final test** (h=3) | 2025-07 … 2026-02 (8 months, 96 rows) | **RESERVED — not evaluated** |

Development is grouped into **DEV-1** (2024-01…2024-05), **DEV-2**
(2024-06…2024-10) and **DEV-3** (2024-11…2025-03) for reporting only. They are
not random train/validation splits and not separate fitting regimes — the
calibrator and every baseline's information set are rebuilt independently at
**every monthly origin**, regardless of block.

### The locked test was not opened

`docs/b4_locked_test_manifest.json` contains only origin ranges, row counts, and
a SHA-256 over the key list. No target distribution, metric, risk-level
frequency, plot, or model comparison was computed on it. The runner takes **no
command-line arguments at all** — there is no `--include-test` to typo — and
`run_walk_forward` calls `plan.assert_not_locked_test(origins)`, which raises
`LockedTestAccessError` if a reserved origin ever reaches it. A test asserts the
runner imports no argument parser and that `main()` accepts no parameters.

## 2. Information rules

### Calibration cutoff

```
stress_month <= forecast_origin_month
```

The origin month's **own** observation is allowed: the historical-evaluation
contract assumes the monthly value at the forecast origin is in hand when the
forecast is made. Nothing after the origin may enter, and `fit` raises
`LeakageError` rather than trimming. Minimum 24 reference observations per
industry — satisfied from the first development origin (2022-01…2024-01 = 25).

A **fresh calibrator is fitted at every origin** and then frozen. Fitting one
calibrator across the development period is explicitly forbidden in config and
asserted in tests: all 15 origins produce 15 distinct reference fingerprints.

### Training-label cutoff

```
target_window_end <= forecast_origin_month
```

Enforced on the **window end**, per horizon — never on the label's origin date.
This is the rule that actually does the work for the 3-month horizon: a label
originating at t−1 has a window ending at t+2, so it is still incomplete at t,
and selecting by origin date would feed the model the very outcome it is being
asked to predict. A test compares both selections and confirms every row the
naive rule would add reaches past the origin.

### Evaluation label

The current origin's target is transformed **only after** the baseline
prediction exists and the calibrator is frozen. It is never part of the training
set at its own origin.

### Feature availability (contract for later tasks)

```
feature_available_month <= forecast_origin_month
```

B4 ships no features, but `assert_feature_availability` defines the contract
now. Violations **raise**; rows are never silently dropped, because a quietly
shrinking feature table is how a leakage bug turns into an apparent accuracy
gain.

**This is a month-based latest-vintage rule, not a real-time release-date
rule.** Verified publication dates do not exist for these sources, so a value
published late within its own reference month is indistinguishable from one
published on time. The rule catches obvious future-dating; it does not turn the
evaluation into a real-time backtest.

## 3. One prediction at a time

At each development origin, for each horizon:

1. select monthly stress with `stress_month <= t`;
2. select completed labels with `target_window_end <= t`;
3. fit a fresh calibrator on the permitted stress only;
4. freeze it;
5. transform the permitted historical labels with that frozen state;
6. produce baseline predictions for all 12 industries;
7. freeze the predictions;
8. **only then** transform the observed future target with the same calibrator;
9. store prediction, observed score, raw target, risk level and full audit metadata;
10. advance.

Every prediction row carries its calibration reference start/end, observation
count, and fingerprint; the maximum training window end; the training label
count; the split name; and both the target-definition and harness versions — so
any row can be re-derived and audited without re-running the harness.

## 4. Baselines

| Baseline | Horizons | Rule |
|---|---|---|
| `no_contraction` | 1, 3 | Predict raw 0.0, then calibrate it — "nothing bad happens" |
| `persistence_current_month` | 1, 3 | Future score = the origin month's calibrated score |
| `persistence_trailing_3m_max` | 3 | Max calibrated monthly stress over t−2, t−1, t |
| `industry_historical_mean` | 1, 3 | Mean calibrated target score over that industry's completed labels (skill reference) |
| `seasonal_naive` | 1, 3 | Last year's raw stress for the corresponding window, then calibrated |

None is tuned, searched, or blended — tuning a benchmark quietly consumes
development data. `industry_historical_mean` never pools industries; missing
history raises `InsufficientHistoryError` rather than borrowing another
industry's values.

## 5. Metrics

**Primary: macro-industry MAE on the 0–100 score.** Each industry's MAE is
computed first, then the 12 are averaged with equal weight, so one volatile
industry cannot dominate model selection. R² is not used as the primary metric.

Secondary: pooled MAE, macro RMSE, pooled RMSE, median absolute error, pooled
Spearman, per-industry MAE, and per-block breakdowns.

> **On macro vs pooled**: in this development sample the two are numerically
> identical, because the panel is perfectly balanced (15 origins × 12 industries,
> one row each) — the mean of per-industry means equals the pooled mean exactly.
> That is an arithmetic identity of a balanced panel, not a bug and not a sign
> the distinction is cosmetic. A test builds an unbalanced fixture where pooled
> = 3.0 and macro = 5.0 to prove the two implementations really differ.

**High-stress events**: `score >= 85` (High + Severe combined). Precision,
recall, F1, PR-AUC and false-negative count are reported. PR-AUC is emitted as
`null` with an explicit reason when undefined (no observed positives), never as
a fabricated 0.0 that would read as a real, poor score. **Severe (`>= 95`) is
reported as descriptive counts only** — too few events for stable rates.

**Skill**: `1 − model_mae / historical_mean_mae`, against
`industry_historical_mean`, with paired differences by forecast origin.

## 6. Uncertainty

180 industry-month rows are **not** 180 independent observations: industries
share calendar shocks, YoY observations overlap by 11 of 12 months, and 3-month
windows overlap further. So the bootstrap resamples **whole origin months** —
all 12 industries of a drawn month travel together — in **3-month moving
blocks**, 1,000 replications, seed 20260827.

95% intervals are reported for macro MAE, MAE skill, and paired MAE differences
between baselines. **A CI crossing zero means the comparison is inconclusive on
this sample** — not that the baselines are equivalent. No significance or causal
claim is made from this design.

## 7. Baseline selection

Per horizon, using development data only:

1. lowest development macro-industry MAE;
2. if effectively tied (paired bootstrap CI includes zero), lower false-negative
   count at score ≥ 85;
3. if still tied, the simpler baseline.

The selected benchmark is the floor a future ML model must clear. No locked-test
information enters the choice, and that is asserted in the results JSON and in
tests.
