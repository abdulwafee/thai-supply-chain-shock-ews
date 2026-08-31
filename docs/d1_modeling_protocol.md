# Task D1 — Modeling Protocol

The preregistered rules for the first predictive model. Written before any model
was fitted and before any development metric was seen.

Contract: [`configs/d1_development_models.yaml`](../configs/d1_development_models.yaml).
Schema: [`schemas/development_model_prediction.schema.yaml`](../schemas/development_model_prediction.schema.yaml).
Assembly: [`d1_feature_target_assembly_audit.md`](d1_feature_target_assembly_audit.md).
Results: [`d1_development_results.md`](d1_development_results.md).

```bash
python scripts/run_d1_development_model.py
```

**D1 may conclude that commodity features do not beat persistence.** A negative
or inconclusive result is a valid outcome, and it must not be repaired by
widening the grid, adding transformations, or re-searching features.

---

## 1. The model

```
r = y - b                 residual beyond the benchmark
y_hat = b + r_hat         prediction
```

The model predicts what the benchmark **misses**, not the target. That framing
makes the benchmark the floor by construction: a model that learns nothing
predicts `r_hat = 0` and reproduces persistence exactly. The comparison then
asks the only question worth asking — does commodity information add anything
*beyond* what persistence already captures?

| Horizon | Benchmark offset |
|---|---|
| h=1 | `persistence_current_month` |
| h=3 | `persistence_trailing_3m_max` |

One ridge per **(outer origin, horizon, industry)**. Coefficients are **never
pooled across industries**: a coefficient fitted on food processing has no claim
on refineries. The benchmark comes from B4's own baseline implementation, reused
rather than copied, and the reproduction is asserted against B4's production
predictions.

Predictions are clipped to `[0, 100]` — the calibrated score is a percentile, so
anything outside is out of range by definition. The bounds are **not tuned**.

## 2. Two temporal cutoffs, enforced separately

**Label availability** — `target_window_end <= t`, per horizon. The rejected
alternative, `training_forecast_origin < t`, would admit a 3-month window still
*open* at *t*, handing the model an outcome it could not yet know.

**Historical feature availability** — `conditioned_available_month <= u`, where
*u* is the **historical** origin, not the outer origin *t*. This is the subtler
leak: refreshing a training row with everything known at *t* would make it carry
information published after the moment it claims to represent, and the model
would learn from a version of history that never existed.

The two are enforced by different arguments so they cannot drift into each
other, and both are exercised by synthetic failure tests.

**The target at *t* is read only after** features, calibrator, hyperparameters,
scaler, model and prediction are all frozen.

## 3. Feature history is gated, never imputed

Under the primary lag-2 contract the 12-month log change first exists for
reference month 2022-01, available **2022-03**. Earlier origins have an
incomplete registered set. They are **retained in the assembly audit** with
`insufficient_registered_feature_history` and excluded from fitting. Inventing a
12-month change would fabricate the very signal the model is asked to find.

Both counts are reported: labels permitted by `target_window_end`, and rows
usable after the feature gate.

## 4. Calibrator refits everywhere

A fresh `IndustryStressCalibrator` at **every** outer origin (`stress_month <= t`)
and **every** inner validation origin (`stress_month <= v`). Reusing the outer
calibrator inside inner validation would leak the outer origin's distribution
into every inner score, so the selection would be made with information the
inner fold was meant not to have.

Historical targets and historical benchmark offsets are expressed on the **same**
calibrator frozen at *t* — a residual computed across two different scales would
not be a residual.

### A conflict between the brief and the data

The brief expects the earliest inner validation origins to be **2023-03** (h=1)
and **2023-05** (h=3), giving ≥10 and ≥6 inner months at the first outer origin.
Those dates follow from the *feature* gate alone (2022-03 + 12 origins). They do
not account for the **calibrator's own** requirement.

B3's monthly stress series begins **2022-01**, so the 24th observation falls at
**2023-12** — the first month a calibrator can be fitted at all. Since D1 must
*"preserve the 24-observation minimum per industry"*, the earliest feasible inner
validation origin is **2023-12 for both horizons**, which leaves **1** inner
month for h=1 and **0** for h=3 at the first outer origin.

**The guard is kept and the expectation is reported as unmet**, rather than the
guard being weakened to reach a date.

Where fewer than **3** inner validation origins exist, D1 uses a preregistered
conservative fallback: **alpha = 100.0** (the most regularized value) and
**channel = none** (the fewest predictors). That shrinks the predicted residual
toward zero and therefore pulls the model *toward* the benchmark — the fallback
can only make the model look **worse**, never better, so it cannot manufacture
apparent skill where evidence is thinnest. Every use is recorded per origin.

## 5. Nested selection

At most **12** registered configurations: alpha ∈ {0.1, 1.0, 10.0, 100.0} ×
channel ∈ {none, aluminum, copper}. Selection is by expanding inner
walk-forward, entirely inside the outer training window, on **inner macro
industry MAE**.

Tie rule, in order: within `1e-6`, prefer fewer predictors; then the larger
alpha; then a deterministic configuration-ID order.

Outcome-based selection is permitted **here and only here** — inside the nested
procedure, on inner folds. It never reaches back into C2 source eligibility, C3
exposure eligibility, or C4 feature generation.

## 6. Aluminum and Copper

They share I/O sector 107, so **at most one may enter a model**. The channel is
chosen **globally** per outer origin and horizon — not industry by industry,
which would let one structural assumption be varied twelve ways to flatter the
score. Where the selected channel is ineligible for an industry under C3-R1, it
is **omitted** for that industry: never zeroed, never swapped for the other
metal.

`fit_ridge_residual` raises if both ever appear in one design matrix. No sum, no
average, no non-ferrous index, no PCA, and no claim of independent measurement.

## 7. Predictors and preprocessing

All five registered C2 transformations for every permitted channel. Individual
transformations are **never** selected on target outcomes.

1. Ineligible predictors are **omitted**, not zero-filled.
2. Eligible predictors require the complete registered history.
3. Zero-variance detection uses **X only** — using *y* would be outcome-based
   filtering.
4. Zero-variance predictors are omitted from fitting but preserved in the audit.
5. The scaler is fitted on **training rows only**.
6. The frozen scaler is applied to the evaluation row.
7. An intercept is fitted.

Prohibited: imputation, forward fill, target encoding, PCA, outcome-based
univariate filtering, whole-development scaling, and preprocessing fitted once
for all outer origins.

## 8. Three variants

| Variant | Policy | Exposure | Role |
|---|---|---|---|
| primary | lag 2 | direct | **primary** |
| timing sensitivity | lag 1 | direct | sensitivity only |
| structural sensitivity | lag 2 | total requirements | sensitivity only |

Sensitivities **reuse** the primary alpha and channel, refitting only
coefficients and preprocessing. They are reported separately, are never pooled
with the primary, cannot change primary selection, and **cannot rescue a failed
or inconclusive primary result**. No lag-1 + total-requirement combination is
created or evaluated.

## 9. Uncertainty and the verdict

B4's own moving-block bootstrap: clustered by forecast-origin month with all 12
industries travelling together, block length 3, 1,000 replications, seed
20260827. 180 industry-month rows are **not** 180 independent observations.

The verdict is mechanical:

| Status | Condition |
|---|---|
| `incremental_signal_supported` | Model macro MAE lower **and** paired 95% CI entirely below zero |
| `inconclusive` | Point estimate lower, but the CI includes zero |
| `incremental_signal_not_supported` | Model macro MAE equal to or worse than the benchmark |

High-stress metrics and sensitivity results may qualify the discussion. They
**may not override the rule**.

Regardless of outcome: `approved_for_locked_test` stays false, no C2/C3/C4
feature becomes model-approved, and the locked test stays unopened.

## 10. What D1 does not do

No MPI correlation, feature importance, mutual information, Granger causality,
predictive-performance-based feature selection, target distribution, or
high-stress-tuned threshold. No locked-test target row or metric is read; only
the locked-test **origin keys** are read, for a non-overlap assertion.

The runner takes **no command-line arguments**.
