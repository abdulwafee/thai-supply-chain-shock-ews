# Task B3 — Industry Production Stress Score

The MVP target definition, replacing the K=2 MPI+CapU equal-weight composite
that Task B2 rejected.

- Config: [`configs/production_stress_target.yaml`](../configs/production_stress_target.yaml)
- Code: `src/thai_supply_chain_ews/targets/{production_stress,labels,calibration}.py`
- Metadata: [`b3_target_build_metadata.json`](b3_target_build_metadata.json)
- Schemas: `schemas/production_stress_month.schema.yaml`, `schemas/forecast_target.schema.yaml`

```bash
python scripts/run_b3_target_build.py
```

---

## 1. Naming — and what this target is not

| Concept | Name |
|---|---|
| System | **Thai Supply Chain Shock Early Warning System** |
| Predicted outcome | **Industry Production Stress Score** (คะแนนความเครียดด้านการผลิตของอุตสาหกรรม) |
| Raw stress measure | `mpi_adverse_yoy` |

**This is deliberately not called a "Supply Chain Stress Index."** MPI measures
manufacturing production. It captures the *consequence* that a supply-chain
shock is expected to produce, not the shock itself, and not every dimension of
disruption. The system's future **input features** are what will represent
raw-material, energy, import, trading-partner and logistics shocks; the
**predicted outcome** is production stress. Calling an MPI-only outcome a
comprehensive supply-chain index would overstate what the data supports.

## 2. Why MPI alone, and why CapU is kept but excluded

Task B2 classified MPI and CapU as **`redundant`** under a preregistered gate
(pooled |Spearman| 0.8601 ≥ 0.85; 10/12 industries |ρ| ≥ 0.75; median Jaccard
0.6319 ≥ 0.60), so the K=2 equal-weight composite was **`rejected`**. All of
that stands unchanged — B2 was not re-run, and its thresholds were not moved.
Three B2 facts remain on the record and matter here:

- the verdict was **close to the thresholds** — failing any one condition would
  have flipped it to `non_redundant`;
- MPI and CapU still **differ materially in some industries** (IND-12 ρ = 0.396
  with a CI spanning zero; IND-07 Jaccard = 0.222), even while IND-02 and IND-03
  have *identical* top-20% stress months;
- both components individually **passed their semantics checks**.

Given a duplicative pair, the options were to keep a second component that adds
little, to reopen B2's thresholds until the answer changed, or to define the
target around one component. B3 takes the third: **K = 1, MPI only.**

MPI is the primary because it measures production directly, in an index whose
YoY change has an unambiguous adverse direction, and because it is the quantity
the system exists to warn about.

**CapU is not deleted.** It stays in the B1 panel with:

| Field | Value |
|---|---|
| `target_role` | `auxiliary` |
| `included_in_primary_target` | `false` |
| `allowed_future_use` | `robustness_outcome_or_lagged_feature` |
| `contemporaneous_or_future_use_prohibited` | `true` |

CapU at t+1, t+2 or t+3 must never be added to an MPI-derived target — that
would reintroduce the rejected composite through the back door. Any later use of
*lagged* CapU as a predictor supports **latest-vintage historical evaluation
only**, because `release_date` and `available_as_of` are null throughout the
panel and CapU's publication timing has never been verified.

**Export and PPI are not replacement target components for the MVP.** Both are
still `source_verified: false`. Upstream indicators will be evaluated as
*predictors* in a later phase, not promoted into the target.

## 3. Source invariants — reproduced

Re-derived from `data/processed/industry_month_panel.parquet`: 12 industries,
66 months (2021-01 … 2026-06), 792 rows, 780 model-eligible, 12 preliminary rows
all in 2026-06, 65 non-preliminary months through 2026-05, edition `2021_based`
only, MPI present/numeric/strictly positive, no duplicate industry-month keys.
No historical-edition bridge data is used. A material failure raises and stops
B3 rather than being repaired.

## 4. Raw monthly production stress

```
mpi_adverse_yoy(i,t) = -100 × (mpi_t / mpi_{t-12} − 1)
```

Positive = MPI declined versus the same month a year earlier; zero = unchanged;
negative = production improved. Unit: percentage change with the adverse
direction made positive.

- Preliminary and non-model-eligible observations excluded.
- A zero or non-positive denominator **raises** rather than producing an infinity.
- The first 12 months of each industry are **absent, never imputed**.
- No winsorizing, clipping, or automatic removal of extremes. The observed range
  is −69.61 to +29.21 and those values are retained as published.
- `mpi_level`, `mpi_level_lagged` and `lag_source_month` are kept for auditability.

**Coverage: 2022-01 … 2026-05, 53 months per industry, 636 rows.**

## 5. Forecast horizons

A row represents information available at forecast-origin month *t*, and the
origin itself must carry a valid observed `mpi_adverse_yoy` — so the earliest
permissible origin is 2022-01.

| Horizon | Definition | Origins | Per industry | Rows |
|---|---|---|---|---|
| 1 month | `target_raw_1m(i,t) = mpi_adverse_yoy(i, t+1)` | 2022-01 … **2026-04** | 52 | **624** |
| 3 months | `target_raw_3m(i,t) = max(mpi_adverse_yoy(i, t+1..t+3))` | 2022-01 … **2026-02** | 50 | **600** |

**Combined: 1,224 rows.**

The 3-month target means **the worst observed production stress during the next
three months**.

**2026-06 is excluded** because it is preliminary. A window that would reach it
is **dropped, never truncated** — a maximum over two months is a different
quantity from a maximum over three. That is why the 3-month origins stop at
2026-02 rather than 2026-04.

Stored per row: `forecast_origin_month`, `industry_id`, `horizon_months`,
`target_window_start`, `target_window_end`, `target_peak_month`,
`target_peak_lead_month`, `target_raw_value`, `target_raw_unit`,
`target_definition_version`. **Ties resolve to the earliest peak month**,
deterministically.

## 6. Leakage-safe calibration

Raw stress is not directly comparable across industries — the same −5% means
something different in a volatile industry than in a stable one. So the
user-facing score is an **industry-relative empirical percentile**:

```
score = 100 × (count(reference < x) + 0.5 × count(reference == x)) / n
```

`IndustryStressCalibrator` has an explicit **fit / transform** split:

- **fit** takes reference observations *and an explicit training cutoff*. Any
  observation dated after the cutoff raises `LeakageError` — it is **not**
  silently trimmed, so a caller who accidentally passes validation or test
  months finds out immediately.
- Per industry it stores: observation count, sorted reference values, reference
  start and end month, a SHA-256 fingerprint, and the calibrator version.
- **Minimum 24 reference observations.** An industry below it is **recorded in
  `excluded_industries` with a reason, not silently dropped**; transforming it
  raises `InsufficientReferenceError`.
- **transform** never refits and never mutates fitted state. Output is 0–100:
  a value below all reference observations scores 0, above all scores 100.
- An **unseen industry raises** `UnknownIndustryError` — there is no pooled
  fallback distribution.
- Serialization is byte-deterministic (explicit `newline="\n"`, so the same fit
  produces identical bytes on Windows and POSIX).

B2's `diagnostic_only_full_sample_rank` is **not reused**. It was full-sample by
construction and explicitly labelled not leakage-safe.

### Static labels vs fold-specific scores

Raw horizon labels are persisted because they need no fitted statistic.
**Calibrated scores are not persisted as production outputs.** The workflow is:

1. build raw horizon labels (static);
2. define a temporal training fold;
3. fit the calibrator on permitted history only;
4. transform training and evaluation targets with that **frozen** calibrator;
5. derive risk levels from the frozen scores.

Producing one full-sample calibrated score and presenting it as leakage-safe
would collapse steps 2–4 into a single leak. `docs/b3_example_calibrator.json`
is a **worked example** at cutoff 2024-12, included so the mechanism is
inspectable and testable — it is not a project-wide split decision.

## 7. Risk levels

| Score | Risk level |
|---:|---|
| 0 – <70 | `Normal` |
| 70 – <85 | `Watch` |
| 85 – <95 | `High` |
| 95 – 100 | `Severe` |

These are **preregistered policy thresholds, not naturally observed
ground-truth classes**. Accordingly:

- the primary ML task remains **continuous prediction**;
- risk levels are **derived presentation outputs**;
- thresholds **must not be tuned on the final test period**;
- class frequencies may be **imbalanced by design** — in the worked example fold
  (360 holdout label rows) the split was Normal 263, Watch 52, Severe 26,
  High 19.

For the 3-month horizon, scoring each future monthly value and taking the
maximum score agrees exactly with scoring the maximum raw value, because the
ECDF is monotone non-decreasing. This equivalence is asserted in tests.

## 8. Limitations

- **Small history.** 53 monthly stress observations per industry; the calibrator
  reference in the worked fold is 36 months. Empirical percentiles from that
  many points are coarse, and the extreme tail is estimated from very few
  observations.
- **Latest-vintage only.** `release_date` and `available_as_of` are null, so
  every evaluation built on this target is a latest-vintage historical
  evaluation, **not** a real-time vintage backtest.
- **Overlapping YoY windows.** Consecutive observations share 11 of 12 months of
  underlying data, and 3-month maxima overlap further, so effective sample size
  is well below the row count.
- **One component.** K=1 means the target inherits every limitation of MPI,
  including whatever supply-chain stress does not show up in production volume.
- **Risk bands are policy.** The four levels are a presentation choice; their
  frequencies are not a property of the world.

## 9. What B3 did not do

No upstream feature collection, no dependency matrices, no model training, and
no persisted full-sample calibrated scores.
