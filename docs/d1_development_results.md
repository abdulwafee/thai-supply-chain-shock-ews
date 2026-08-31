# Task D1 — Development Results

**The commodity features do not beat persistence.** At both horizons the
residual-correction model is *worse* than the B4 benchmark, and the paired 95%
confidence interval excludes zero in the benchmark's favour. Under the
preregistered rule this is `incremental_signal_not_supported`.

That is a valid outcome, reported as found. It was not repaired by widening the
grid, adding transformations, or re-searching features.

Protocol: [`d1_modeling_protocol.md`](d1_modeling_protocol.md).
Numbers: [`d1_development_results.json`](d1_development_results.json).

The locked final test remains **unopened**.

---

## 1. Headline

| | h=1 | h=3 |
|---|---|---|
| Benchmark | `persistence_current_month` | `persistence_trailing_3m_max` |
| **Model macro MAE** | **15.3073** | **16.1072** |
| **Benchmark macro MAE** | **14.5287** | **14.6985** |
| MAE skill | **−0.0536** | **−0.0958** |
| Paired difference (model − benchmark) | **+0.7786** | **+1.4087** |
| Paired 95% CI | **[0.4932, 1.1678]** | **[0.7319, 1.9405]** |
| CI verdict | excludes zero | excludes zero |
| **Evidence status** | **`incremental_signal_not_supported`** | **`incremental_signal_not_supported`** |

The interval excluding zero here is evidence **against** the model, not for it:
the difference is positive, and positive means worse.

Only **2 of 15** origins favoured the model at each horizon.

## 2. Full metrics

| Metric | h=1 model | h=1 benchmark | h=3 model | h=3 benchmark |
|---|---:|---:|---:|---:|
| Macro industry MAE | 15.3073 | **14.5287** | 16.1072 | **14.6985** |
| Pooled MAE | 15.3073 | **14.5287** | 16.1072 | **14.6985** |
| Macro industry RMSE | 19.3477 | **18.4315** | 20.1669 | **18.7163** |
| Pooled RMSE | 20.4924 | **19.5968** | 21.2570 | **19.8138** |
| Median absolute error | 10.4364 | **10.0000** | 13.0062 | **10.7718** |
| Pooled Spearman | 0.7247 | **0.7384** | 0.7209 | **0.7381** |
| Clipped predictions | 5 | — | 10 | — |

**Macro and pooled MAE are identical** here because the development panel is
balanced — 15 origins × 12 industries with no gaps. They are still reported
separately, because that identity is a property of this panel, not of the
metrics.

Model macro-MAE bootstrap CIs: h=1 **[13.9959, 17.4191]**, h=3 **[13.1849,
17.8679]**.

Per-industry MAE and DEV-1/DEV-2/DEV-3 block metrics are in the JSON.

## 3. High-stress events (score ≥ 85, threshold never tuned)

| | h=1 model | h=1 benchmark | h=3 model | h=3 benchmark |
|---|---:|---:|---:|---:|
| Observed events | 20 | 20 | 29 | 29 |
| Predicted events | 27 | 21 | 42 | 37 |
| Precision | 0.5185 | **0.6190** | 0.6190 | **0.6486** |
| Recall | **0.7000** | 0.6500 | **0.8966** | 0.8276 |
| F1 | 0.5957 | — | 0.7324 | — |
| **False negatives** | **6** | 7 | **3** | 5 |

This is the one place the model looks better: it catches more events (recall
0.70 vs 0.65 at h=1; 0.90 vs 0.83 at h=3) and misses fewer, by predicting more
events and accepting worse precision.

**It does not change the verdict.** The preregistered rule is explicit that
high-stress metrics may qualify the discussion but never override the MAE
decision, and the rule was fixed before these numbers existed.

## 4. Selection

| Horizon | Alpha | Channel | Inner origins |
|---|---|---|---|
| h=1 | 100.0 ×12, 10.0 ×3 | `none` ×7, `copper` ×8 | 0 → 15 |
| h=3 | 100.0 ×15 | `none` ×5, `copper` ×10 | 0 → 13 |

Alpha 100.0 — the **most regularized** value in the grid — was selected at 27 of
30 origin-horizons. The nested procedure was, in effect, choosing to shrink the
commodity correction as close to zero as the grid allowed. That is the selection
telling the same story the MAE does.

Copper was the selected non-ferrous channel at 18 of 30. **Aluminum was never
selected**, and aluminum and copper never appear together in any model — a
constraint asserted on all 1,080 predictions.

Six origin-horizons used the preregistered conservative fallback (alpha 100.0,
channel `none`) because fewer than 3 inner validation origins existed: h=1 at
2024-01/02 and h=3 at 2024-01 through 2024-04. See §7.

## 5. Sensitivities — separate, and they change nothing

| Variant | h=1 macro MAE | h=3 macro MAE |
|---|---:|---:|
| **Primary** | **15.3073** | **16.1072** |
| Timing (lag 1) | 15.6007 | 16.1329 |
| Structural (total requirements) | 15.7170 | 16.1196 |

Both sensitivities are **also worse** than the primary, which is itself worse
than the benchmark. They reuse the primary's alpha and channel and refit only
coefficients and preprocessing.

They are reported here separately and are **not** pooled with the primary result,
did not influence selection, and cannot rescue the primary conclusion. Had one
of them beaten the benchmark, the answer would still be
`incremental_signal_not_supported` — that is what preregistration is for.

## 6. Assembly

| | Label-permitted | Feature-usable |
|---|---:|---:|
| h=1 at 2024-01 | 288 | **264** |
| h=1 at 2025-03 | 456 | **432** |
| h=3 at 2024-01 | 264 | **240** |
| h=3 at 2025-03 | 432 | **408** |

Every feature-usable count matches the brief's expectation exactly. The gap in
each row is the 24 industry-rows (2 origins × 12) excluded by the feature-history
gate with `insufficient_registered_feature_history` — retained in the audit, not
silently dropped, and never imputed.

The first origin with the complete registered set is **2022-03**, as expected.

Calibrators: **30** (15 origins × 2 horizons), 15 distinct fits, each with
`calibration_reference_end` at or before its origin. The first spans 2022-01 …
2024-01 with 300 observations.

## 7. The one place the brief and the data disagree

The brief expects earliest inner validation origins of **2023-03** (h=1) and
**2023-05** (h=3), giving ≥10 and ≥6 inner months at the first outer origin.
Those dates follow from the *feature* gate alone. They do not account for the
**calibrator's** 24-observation minimum.

B3's monthly stress starts **2022-01**, so the 24th observation is at
**2023-12** — the first month any calibrator can be fitted. The earliest feasible
inner validation origin is therefore 2023-12 for both horizons, leaving **1**
inner month for h=1 and **0** for h=3 at the first outer origin.

D1 **kept the 24-observation guard** and reports the expectation as unmet, rather
than weakening a validity guard to reach a date. Where fewer than 3 inner origins
exist it falls back to alpha 100.0 / channel `none` — the most regularized and
smallest configuration, which pulls the model *toward* the benchmark and so can
only make it look worse, never better.

## 8. Reading the result honestly

The model is worse, the interval is conclusive, and the selection kept choosing
maximum regularization. The straightforward reading is that **on 15 development
months, these commodity features add nothing beyond persistence** — and the
residual framing means that is a clean statement: the model had persistence for
free and still lost ground by adding to it.

What this does **not** establish: that commodity prices are irrelevant to Thai
industrial production. The specific chain tested here is narrow — four broad
proxies, a static 2015 exposure structure, 15 effective months, and a
latest-vintage target. Any of those could hide a real relationship.

## 9. Limitations

- **15 effective development months.** Fifteen origin clusters is a small sample
  for a bootstrap; the CIs are wide, and the model CI at h=3 spans 13.18–17.87.
- **Overlapping targets.** h=3 windows overlap across consecutive origins, which
  is why the bootstrap resamples whole origin months in 3-month blocks rather
  than treating 180 rows as independent.
- **Static 2015 structural coefficients**, applied to 2024–2025 under an explicit
  time-invariance assumption.
- **Broad commodity proxies.** Brent's sector includes natural gas; aluminum and
  copper share one sector; RSS3 is one grade among several.
- **Latest-vintage MPI targets.** B1 emits `release_date` and `available_as_of`
  as NULL, so the features are point-in-time but the target is not. This is not
  a real-time backtest.
- **Short calibration history** — the constraint in §7 is a symptom of the same
  problem: B3's stress series is barely longer than the calibrator needs.

## 10. Scope

| Guard | State |
|---|---|
| Locked-test outcomes read | **false** |
| Locked-test origins in any D1 table | **none** |
| Purge-buffer origins in any D1 table | **none** |
| Approved for locked test | **false** |
| Target association / feature selection on outcomes | **false** |
| Aluminum and copper in one model | **never** (1,080 predictions checked) |

Only the locked-test **origin keys** were read, for the non-overlap assertion.
