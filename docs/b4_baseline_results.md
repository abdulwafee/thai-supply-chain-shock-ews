# Task B4 — Development Baseline Results

Every number here is read from
[`b4_baseline_results.json`](b4_baseline_results.json). Protocol:
[`b4_evaluation_protocol.md`](b4_evaluation_protocol.md).

**Development only.** The locked final test period (h=1: 2025-07…2026-04;
h=3: 2025-07…2026-02) was **not evaluated** — see
[`b4_locked_test_manifest.json`](b4_locked_test_manifest.json), which holds only
keys, counts and a checksum.

- 15 development origins, 2024-01 … 2025-03
- 180 out-of-fold rows per horizon per baseline (15 × 12 industries)
- 1,620 prediction rows total across 9 baseline-horizon combinations
- B3 invariants independently reproduced before anything was computed

---

## 1. Horizon 1 month

Score scale 0–100. `FN@85` = false negatives at the high-stress threshold.
Skill is versus `industry_historical_mean`.

| Baseline | macro MAE | 95% CI | pooled MAE | macro RMSE | median AE | Spearman | skill | FN@85 |
|---|---|---|---|---|---|---|---|---|
| **persistence_current_month** | **14.53** | [13.02, 16.70] | 14.53 | 18.43 | 10.00 | +0.738 | +0.468 | **7** |
| no_contraction | 19.90 | [17.49, 21.99] | 19.90 | 23.87 | 15.38 | +0.555 | +0.272 | 20 |
| industry_historical_mean | 27.32 | [24.07, 31.37] | 27.32 | 31.02 | 27.41 | −0.511 | 0.000 | 20 |
| seasonal_naive | 40.33 | [35.25, 45.85] | 40.33 | 46.45 | 37.34 | −0.262 | −0.476 | 19 |

**High-stress events (score ≥ 85): 20 observed.**

| Baseline | Precision | Recall | F1 | PR-AUC | FN |
|---|---|---|---|---|---|
| persistence_current_month | 0.619 | 0.650 | 0.634 | 0.597 | 7 |
| no_contraction | — (predicts none) | 0.000 | — | 0.250 | 20 |
| industry_historical_mean | — (predicts none) | 0.000 | — | 0.067 | 20 |
| seasonal_naive | 0.036 | 0.050 | 0.042 | 0.099 | 19 |

Severe (≥ 95): 11 observed — descriptive count only.

**Selected benchmark: `persistence_current_month`** — lowest macro MAE, and the
paired difference against the runner-up (`no_contraction`) **excludes zero**, so
the choice is conclusive on this sample.

Per-block macro MAE for the selected benchmark: DEV-1 12.17, DEV-2 15.68,
DEV-3 15.74 — stable, mildly worsening across the period.

## 2. Horizon 3 months

| Baseline | macro MAE | 95% CI | pooled MAE | macro RMSE | median AE | Spearman | skill | FN@85 |
|---|---|---|---|---|---|---|---|---|
| **persistence_trailing_3m_max** | **14.70** | [11.98, 16.40] | 14.70 | 18.72 | 10.77 | +0.738 | +0.487 | **5** |
| persistence_current_month | 16.63 | [14.05, 20.15] | 16.63 | 20.72 | 12.96 | +0.749 | +0.420 | 12 |
| no_contraction | 17.35 | [15.95, 19.03] | 17.35 | 20.41 | 12.90 | +0.662 | +0.395 | 29 |
| industry_historical_mean | 28.67 | [23.64, 33.75] | 28.67 | 31.75 | 27.03 | −0.297 | 0.000 | 29 |
| seasonal_naive | 37.58 | [31.13, 44.98] | 37.58 | 42.27 | 36.49 | −0.162 | −0.311 | 20 |

**High-stress events (score ≥ 85): 29 observed.**

| Baseline | Precision | Recall | F1 | PR-AUC | FN |
|---|---|---|---|---|---|
| persistence_trailing_3m_max | 0.649 | 0.828 | 0.727 | 0.654 | 5 |
| persistence_current_month | 0.810 | 0.586 | 0.680 | 0.731 | 12 |
| no_contraction | — (predicts none) | 0.000 | — | 0.367 | 29 |
| industry_historical_mean | — (predicts none) | 0.000 | — | 0.137 | 29 |
| seasonal_naive | 0.136 | 0.310 | 0.189 | 0.159 | 20 |

Severe (≥ 95): 21 observed — descriptive count only.

**Selected benchmark: `persistence_trailing_3m_max`.**

**This choice is NOT conclusive.** The paired bootstrap difference against
`persistence_current_month` **includes zero**, so on 15 origin months the two
are statistically indistinguishable on macro MAE. The tie-break rule then
applies: the trailing variant has far fewer false negatives at the high-stress
threshold (5 vs 12) and higher recall (0.828 vs 0.586), and it also happened to
have the lower point estimate. Note the trade-off honestly — the current-month
variant has *higher precision* (0.810 vs 0.649) and a *higher PR-AUC* (0.731 vs
0.654). The selection rule prioritises missed events, which is the defensible
choice for an early-warning system, but it is a policy choice, not a finding.

Per-block macro MAE for the selected benchmark: DEV-1 14.83, DEV-2 12.21,
DEV-3 17.05.

## 3. What these numbers do and do not say

**A hard floor now exists.** Any future ML model must beat macro MAE **14.53**
(h=1) and **14.70** (h=3) on the same protocol, or it is not worth its
complexity.

**Two baselines are surprisingly strong, and one is surprisingly bad:**

- **Persistence dominates.** Production stress is highly autocorrelated, so
  "next month looks like this month" is hard to beat. A model must add
  information beyond persistence to be worth anything.
- **`industry_historical_mean` is poor** (skill 0.000 by construction, but MAE
  27–29 and *negative* Spearman). Predicting an industry's average stress level
  is worse than useless for ranking months — it has no time-varying signal at
  all, and the negative correlation reflects that the calibrated target is
  roughly mean-reverting around the reference distribution. It remains the skill
  reference because that is what a skill score is *for*, but it should not be
  mistaken for a competitive benchmark.
- **`seasonal_naive` is the worst baseline by a wide margin** (MAE 37–40,
  negative skill). Last year's stress in the same calendar month is actively
  misleading here — unsurprising given that YoY changes already remove the
  seasonal component, so the seasonal lag mostly re-injects noise from a
  different shock regime.
- **`no_contraction` never predicts a high-stress event**, so its recall is 0
  and its precision is undefined. It is a useful reference for the score scale,
  not a candidate.

**The 3-month comparison is unresolved.** Do not read the 1.9-point macro-MAE
gap between the two persistence variants as a real difference — the interval
says otherwise on this sample.

## 4. Limitations

- **15 origin months.** After clustering by month (the correct unit — see §6 of
  the protocol), the effective sample for every interval here is 15, not 180.
  Intervals are correspondingly wide and small differences are not resolvable.
- **Overlapping targets.** Consecutive YoY observations share 11 of 12 months;
  consecutive 3-month windows share 2 of 3 months. Adjacent origins are strongly
  dependent, which the 3-month block bootstrap accounts for but cannot remove.
- **Latest-vintage timing.** `release_date` and `available_as_of` are null
  throughout, so the availability rule is month-based, not release-date-based.
  This is a latest-vintage historical evaluation, not a real-time backtest, and
  no result here should be described as one.
- **Calibrated-score targets move with the calibrator.** The observed score at
  an origin depends on that origin's frozen reference distribution, which grows
  by one month each step. This is the correct leakage-safe construction, but it
  means the target scale is not perfectly constant across origins.
- **Few high-stress events.** 20 (h=1) and 29 (h=3) observed events, and only 11
  and 21 severe ones. Precision/recall differences of a few points rest on a
  handful of months.
- **No features exist yet.** These baselines use only the target's own history.
  A model with genuine upstream shock features has not been tested and may or
  may not beat them.
