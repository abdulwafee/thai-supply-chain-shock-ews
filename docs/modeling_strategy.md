# Modeling Strategy — Global Panel Model

Status: design document. No model is trained in this step, and no performance number in this
document is a real result — every number that appears below is a placeholder or an illustrative
formula, never a claimed finding. This document specifies the modeling strategy that
`src/thai_supply_chain_ews/models/{baselines,train,predict}.py` will implement (currently stubs)
and that Phase 1 Groups E–G of `docs/project_roadmap.md` will execute.

**Revision note**: this revision confirms a **two-model architecture** — `global_model_1m` and
`global_model_3m` as independent, horizon-specific fitted pipelines, never a multi-output estimator
(§4). Sections carried over from the previous revision are otherwise unchanged except where noted.

**Naming notes** (kept together here so they don't fragment across revisions):
- This task's brief uses `reference_month`; this document uses `reference_period` throughout
  instead, because that is the field name already fixed across
  `docs/architecture/data_architecture.md`, `docs/architecture/data_contract_industry_month_panel.md`,
  and `schemas/*.yaml`. Same field, one name.
- This revision's horizon-config draft names target columns `target_stress_1m` /
  `target_stress_3m`. These are the **wide, horizon-specific** column names that exist inside each
  horizon pipeline's own `model_input` table — a `global_model_1m` training table has a
  `target_stress_1m` column and no `target_stress_3m` column, and vice versa for `global_model_3m`.
  This is *not* in conflict with the shared, long-format `targets/industry_month_targets.parquet`
  table from `docs/architecture/data_contract_industry_month_panel.md` (grain
  `(industry_id, prediction_date, horizon)`, single `stress_score` column, `horizon` disambiguates)
  — that table remains the canonical source of truth for both horizons; each horizon pipeline
  projects out its own single-target wide slice from it, renaming `stress_score` to
  `target_stress_1m` or `target_stress_3m` as it does so. §1 documents both views.
- A cross-reference bug from the previous revision is fixed in this one: several places referred to
  "§10" for the diagnostics table, which is actually §10 in this document now (it was §8 before this
  revision's new sections shifted the numbering) — every cross-reference below has been checked
  against the section it actually points to.

---

## 1. Panel-data definition

Two related views exist, and this document is explicit about which is which:

- **The shared feature+target panel** (conceptual superset, what `build_panel.py` /
  `build_features.py` produce before horizon-specific projection): one row per
  `(industry_id, prediction_date)`, carrying every feature group (§2) and *both* horizons' target
  columns, because feature generation is shared (§4) and computing both targets from the same
  realized-outcome history is cheap and keeps one source of truth.
- **Each horizon's `model_input` table** (what `global_model_1m` / `global_model_3m` actually
  train on): the same row set, *filtered* to that horizon's eligible rows (§7), with only that
  horizon's target column kept.

| Column | Group | Description | Leakage-safety note |
|---|---|---|---|
| `industry_id` | identifier | `IND-01`..`IND-12` | static, no risk |
| `prediction_date` | identifier | month `t` the row predicts from | static, no risk |
| `reference_period` | identifier | equal to `prediction_date`; kept as an explicit alias so this table reads consistently with `processed/industry_month_panel`'s own `reference_period` column | — |
| `available_as_of` | temporal | the row-level cutoff actually enforced when this row was built (equal to `cutoff_date` in `docs/architecture/data_architecture.md` §8) | **the single most load-bearing column in this table** — every feature value used to build the row must have its own `<feature>_asof <= available_as_of` |
| `<common feature>_value` / `_asof` | common time (§2.1) | e.g. Brent price, USD/THB | per-column `_asof`, checked against `available_as_of` |
| `<dynamic feature>_value` / `_asof` | industry-specific dynamic (§2.2) | e.g. industry PPI change, industry BSI | same |
| `<static attribute>` | industry-specific static (§2.3) | e.g. I-O dependency weight, energy-intensity ratio | no `_asof` needed if the value is genuinely static over the training window (see §2.3 caveat) |
| `<interaction feature>` | interaction (§2.4) | e.g. `oil_price_shock * energy_intensity` | derived; safe iff its two inputs are each already leakage-checked |
| `industry_id_onehot_*` / `industry_id_cat` | industry encoding (§5) | one-hot columns or a native categorical column, depending on model family | static, no risk |
| `lag_stress_1` .. `lag_stress_k` | lagged outcomes | `S(i, t)`, `S(i, t-1)`, … — the industry's own past realized stress score | must be lagged strictly, i.e. use only `reference_period <= t`; this is autoregressive **feature** use of an otherwise target-role variable, which is legitimate per `docs/architecture/data_architecture.md` §0's target/feature separation rule |
| `roll_mean_3`, `roll_std_3`, … | rolling statistics | trailing-window mean/std of stress or its components | trailing-only, per `data_architecture.md` §10 rule 12 — never centered |
| `target_stress_1m` | target (1m pipeline only) | `stress(i, t+1)` | never enters `features/`; see §6, §7 |
| `target_stress_3m` | target (3m pipeline only) | `max(stress(i,t+1), stress(i,t+2), stress(i,t+3))` | never enters `features/`; see §7's embargo discussion for why this target needs special split handling |
| `predicted_risk_level` / calibrated risk level (post-training) | derived | assigned from the score above via train-only thresholds, per horizon | thresholds fit only on the training partition of *that horizon's own* split, never globally and never shared across horizons (§4) |
| `data_quality_flag` | quality | bitmask/string of which quality checks this row passed (see `data/validate.py`) | informational; a row failing a hard rule (e.g. missing `available_as_of` on a populated value) should not reach this table at all, not be flagged-and-kept |
| `n_features_missing` | quality | count of expected feature columns that are null for this row | used in §10 diagnostics and in deciding whether a row is usable at all |

---

## 2. Feature groups

### 2.1 Common time features
Identical value across all 12 industries in a given month — e.g. Brent crude price/level and
month-over-month change (FRED, verified live), World Bank Pink Sheet global commodity indices not
yet mapped to a specific industry, USD/THB exchange rate (BOT). Implementation note: these are
computed once per month and broadcast to all 12 rows, not recomputed per industry. **Shared
identically across both horizon pipelines** (§4) — the feature *value* for a given
`(industry_id, prediction_date)` does not depend on which horizon will consume it.

### 2.2 Industry-specific dynamic features
Vary by both industry and month — e.g. the industry's own lagged MPI/CapU/PPI/export change, an
industry-specific commodity price if the industry's exposure basket is itself time-varying, and
industry-level BSI ("current conditions" sub-index only, per the leakage caveat already recorded in
`docs/data_source_inventory.md` row 19). Also shared across both horizon pipelines.

### 2.3 Industry-specific static features
Established once and held fixed (or updated only when the underlying source is refreshed, not
monthly) — I-O dependency weights (from the 12x12 Dependency Matrix, `matrices/dependency.py`, still
a stub blocked on the NESDC verification item), baseline import concentration, baseline
energy-intensity ratio, TSIC-division-derived indicators.

**Current state, stated plainly**: every one of `data/mapping/hs_to_industry.csv`,
`io_sector_to_industry.csv`, and `commodity_to_industry.csv` is currently an empty, schema-only file
(see `data/mapping/README.md`). This entire feature group is **designed but not yet populated** —
it depends on the same unresolved data-source items already tracked in
`docs/data_source_inventory.md` and `docs/architecture/decision_log.md`. This document specifies the
shape these features will take; it does not claim they exist yet.

### 2.4 Interaction features
Constructed as `common_time_feature x industry_static_attribute`, e.g. `brent_price_change x
energy_intensity_ratio`, `usdthb_change x import_dependence`, `pink_sheet_commodity_change x
commodity_exposure_weight`. This group is the mechanism that lets a *global* model represent "the
same shock hits different industries differently" without needing a separate model per industry —
see §3.

Interaction terms matter differently by model family: a linear model (Ridge/Elastic Net) **cannot**
discover an interaction on its own and will only benefit from this group if the terms are supplied
explicitly; a tree-based model can approximate interactions from splits on the raw common and static
columns even without being handed the product term explicitly, but an explicit interaction column
still helps it split more efficiently and makes the interaction directly visible in feature
importance (serving the "explain warning drivers" requirement). §10's diagnostic 8 tests whether
this group earns its place empirically rather than assuming it does.

---

## 3. Global-model rationale (industry pooling)

The MVP pools all 12 industries into one model per horizon rather than training 12 separate models
per horizon, for four reasons:

1. **Sample size.** Twelve industries with a monthly cadence and an unresolved-but-likely-short
   usable history (see `docs/data_source_inventory.md` §5) means any single industry's own history
   is a small-N, small-T problem — the same risk flagged repeatedly since this project's
   target-design phase. A global model multiplies the effective training sample roughly twelvefold
   by pooling across industries, which per-industry models cannot do by construction.
2. **Shared shock mechanism, industry-specific magnitude.** An oil-price shock plausibly propagates
   through a broadly similar *functional* channel across manufacturing industries (higher input
   cost → margin/production pressure), differing mainly in *magnitude* by how energy-intensive each
   industry is. A global model can learn the shared functional form from all 12 industries' history
   at once, then use static attributes and interaction features (§2.3, §2.4) to modulate magnitude
   per industry — this is more statistically efficient than asking each of 12 separate models to
   independently (and weakly) re-discover the same functional form from a twelfth of the data each.
3. **Direct methodological precedent.** This mirrors how the reference paper (*"Are Three Matrices
   All You Need To Beat the Market?"*) estimates its Markov-chain transition matrices and
   entropy-production diagnostics: pooled across the *entire* cross-section of stocks, not
   fit per-stock, specifically because pooling recovers statistical power that a per-name fit would
   lack, while conditioning on covariates (its Section 2.5–2.7) is what lets the pooled model still
   express cross-sectional heterogeneity — the exact same logic this project's static/interaction
   feature groups are for.
4. **Low-data industries benefit from cross-industry signal.** A global model can, in principle,
   produce a reasonable forecast for an industry with a shorter or noisier own-history by leaning on
   what it learned from the other 11 — §10's diagnostic 7 specifies how this is actually tested,
   not just asserted.

The acknowledged risk this design carries — that industries with larger stress-score variance could
dominate a pooled loss function — is not assumed away; it is one of the explicit diagnostics in §10
(item 3). This section is about pooling **across industries**; §4 covers the separate question of
pooling (or not) **across horizons**.

---

## 4. Two-horizon architecture: `global_model_1m` and `global_model_3m`

### Why two independent models, not one multi-output estimator

A multi-output estimator (predicting `target_stress_1m` and `target_stress_3m` simultaneously from
one fitted object) is **not used**, for reasons that follow directly from decisions already made
elsewhere in this design, not as an arbitrary preference:

- **The two targets need different eligible-row sets and different embargo boundaries** (§7). A
  multi-output estimator is fit once, on one row set — it cannot simultaneously honor "drop the last
  1 month of history" (1m's purge requirement) and "drop the last 3+ months of history" (3m's) within
  a single fit call without either wastefully purging the 1m target too hard or unsafely under-purging
  the 3m target.
- **Artifact isolation is a hard requirement of this task.** A multi-output estimator is, by
  construction, one fitted object — it cannot have "its own fitted preprocessor, trained estimator,
  calibration object" *per horizon* (§9) because there is only one object to begin with.
  Independently versioning, re-evaluating, or re-fitting one horizon without touching the other
  (a realistic operational need — e.g. a 3-month embargo policy change should not force a refit of
  the already-working 1-month model) is not possible with a shared estimator.
- **The two targets are not obviously the same kind of prediction problem.** `target_stress_1m` is a
  point forecast; `target_stress_3m` is a maximum-over-window forecast with materially different
  label statistics (higher, righter-skewed, more autocorrelated across neighboring rows — see §7).
  Forcing one shared internal representation onto both is an assumption this project has no evidence
  for, and the task's own instruction not to assume a design choice is beneficial without evidence
  applies here too.

### Shared vs. per-horizon components

| Shared across both pipelines | Independent per horizon |
|---|---|
| Source-data ingestion (`data/ingest.py`) | Eligible training rows (§7) |
| Point-in-time alignment / cutoff logic (`features/build_features.py`, `data_architecture.md` §8) | Split boundaries (validation/test start, §6) |
| Industry taxonomy (`configs/data.yaml`, `data/mapping/industry_map.csv`) | Embargo/purge width (§7 — 1m needs a 1-month gap, 3m needs a 3-month gap, plus a configurable extra embargo) |
| Feature *definitions* (§2 — the four feature groups, their formulas) | Hyperparameters |
| Preprocessing *code* (the transform logic itself — imputers, scalers, encoders) | Fitted preprocessing *state* — **see the rule below** |
| Industry encoding method (§5) | Fitted estimator artifacts |
| Base estimator interface (a common `fit(X, y) -> model`, `predict(model, X) -> scores` contract every candidate in §8 implements) | Risk-level calibration (train-only thresholds, per horizon) |
| Evaluation-report format (§9) | Evaluation results |
| Prediction-output schema (§11) | — |

### The one rule this section exists to state clearly

**Never reuse a fitted preprocessor (or any other fitted object) across horizons unless it was fitted
only on rows eligible for that specific horizon and split.** Concretely: an imputer or scaler fit on
`global_model_1m`'s training rows has seen a different row population than one fit on
`global_model_3m`'s training rows — not just a different row *count*, but a different **date range**,
because the two horizons purge different amounts of trailing history (§7). Reusing the 1m pipeline's
fitted scaler inside the 3m pipeline would let statistics computed over 1m's (less-purged, more
recent) training window leak into 3m's fitted state — a cross-horizon leakage channel that produces
no error, no obviously wrong number, and no test failure unless a test specifically checks for it
(§12, test 5's sibling check). Each horizon pipeline fits its **own** preprocessor object, from a
cold start, on its **own** eligible training rows only.

---

## 5. Industry representation — comparison and recommendation

*(Unchanged from the previous revision; applies identically to both horizon pipelines, since
industry encoding is a shared component per §4.)*

| Approach | Interpretable? | Leakage-safe? | Fit for this project (N=12 industries) |
|---|---|---|---|
| One-hot encoding of `industry_id` | Yes — each column is a named industry | Yes — static, deterministic | Fine at this cardinality (only 11 dummy columns); works for every model family including the linear baselines |
| Native categorical support (tree libraries) | Moderately — splits are on the category directly, still traceable | Yes | Efficient for tree models (HistGradientBoosting, LightGBM/XGBoost) but not usable by the linear baselines, so cannot be the *only* encoding if Ridge/Elastic Net are also being compared |
| Manually defined industry attributes (§2.3) | Yes, and economically meaningful — this is what actually explains *why* industries differ | Yes, once the mapping tables are populated (currently the blocking item) | This is not a substitute for an identity encoding — it is what lets the model differentiate industries' *response* to a shock; it does not by itself capture whatever idiosyncratic baseline level an industry has that its measured attributes don't explain |
| Target encoding (mean target per `industry_id`) | Low — an opaque numeric substitute for the label | **Only if strictly fold-computed** — the task's own restriction | At N=12 categories, one-hot already costs almost nothing, so target encoding's usual justification (taming a high-cardinality categorical) does not apply here. The complexity and leakage risk it adds is not paying for anything one-hot doesn't already provide at this scale. |

**MVP recommendation**: **one-hot encoding of `industry_id` for every model family**, used
*alongside* — not instead of — the manually defined static attributes and interaction features from
§2.3–§2.4. Native categorical support may be used as a secondary, tree-model-only diagnostic
variant. **Target encoding is not used in the MVP.** If a fitted target-encoding map is ever
introduced in a later phase, it must be fit per horizon *and* strictly inside each training fold,
per §4's rule and this task's own restriction.

---

## 6. Time-split design (calendar boundaries)

### Split rules (hard constraints)

- All rows sharing a calendar month (`prediction_date`) stay in the same split — enforced the same
  way `evaluation/splits.py`'s `time_based_split` already enforces it structurally: partitioning is
  by date, never by row, so it is not possible for two industries from the same month to land in
  different splits.
- No random row-level splitting, no shuffled K-fold — `time_based_split` has no shuffle parameter at
  all (by design, per its own module docstring from the scaffolding step).
- No preprocessing (scalers, thresholds, target encodings if ever used) fit on any month beyond the
  training partition's own boundary — enforced by `data_architecture.md` §10 rules 9 and 11.

### Windows (shared calendar boundaries; horizon-specific train_end derived from them, §7)

- **Initial training window**: from the earliest verified common start date (unresolved — see
  `docs/data_source_inventory.md` §5; this document does not invent one) through a shared
  `validation_start`.
- **Validation window**: `validation_start` through `test_start`, used for the small hand-justified
  hyperparameter grid (per `docs/project_roadmap.md` task F2) and for baseline-vs-candidate
  comparison — never the basis of a final claim.
- **Untouched final test window**: `test_start` through `test_end`, touched exactly once, at the
  end — mirroring the reference paper's own use of a late, non-overlapping, only-looked-at-once test
  window (its January 2025–July 2026 clean window), adopted for the same reason: repeated inspection
  of one held-out period is itself a leakage channel, even when every individual choice made against
  it was validated on an earlier period.
- **Rolling-origin / expanding-window evaluation**: rather than one static train/validation cut, the
  model is refit on an expanding window and evaluated forward at a fixed refit cadence (e.g.
  annually — echoing the reference paper's own `refit: 12 mo` walk-forward cadence, Table 1 of that
  paper), producing multiple out-of-sample evaluation points instead of one.

`validation_start`, `test_start`, and `test_end` are **shared** across both horizon pipelines (both
models are judged against the same calendar test period, which is what makes their evaluation
reports comparable). What differs per horizon is how much training data immediately *before*
`validation_start` gets purged — that is §7.

---

## 7. Boundary handling and embargo logic (horizon-specific)

### Eligible rows: excluding incomplete future windows

- **`global_model_1m`**: a row for `(industry_id, t)` is eligible only if `stress(i, t+1)` is a
  valid, realized observation. If it is missing (data gap, not-yet-occurred), the row is excluded
  from training *and* from evaluation — never imputed.
- **`global_model_3m`**: a row for `(industry_id, t)` is eligible only if **all three** of
  `stress(i,t+1)`, `stress(i,t+2)`, `stress(i,t+3)` are valid, realized observations.

**Default policy for a partially-missing 3-month window: exclude the row entirely.** Do not compute
`max()` over the 2 (or 1) months that *are* available. Two reasons, stated explicitly because this
policy is easy to get quietly wrong:

1. **Comparability.** A "max of 2 realized months" is not the same statistic as "max of 3 realized
   months" — it is systematically *lower* on average (fewer draws from the same distribution rarely
   exceed more draws), so silently mixing 2-month and 3-month maxima into one target column would
   inject a spurious, non-random source of variation that has nothing to do with actual stress.
2. **Missingness is plausibly not random here.** A data gap is arguably *more* likely during exactly
   the disrupted periods this system is meant to detect (e.g. a statistics office delaying a release
   during a crisis) — silently computing a maximum over fewer available months in exactly those
   periods would bias the target *downward* precisely when the true risk is highest. Excluding the
   row is the conservative, honest choice; imputing or partially-aggregating is not.

This is `require_complete_window: true` in the horizon configuration (§8) and is the MVP default for
both horizons (1-month trivially always requires its single month; stating it for 3-month is the
substantive case).

**Distinguishing "excluded from training" from "not yet realized" (live inference)**: at the recent
end of the available history, the most recent few `prediction_date`s will *always* lack a complete
future window simply because the wall-clock future hasn't happened yet — e.g. if the latest available
outcome month is `2026-06`, then `prediction_date = 2026-06` cannot have a `target_stress_3m` (it
would need `stress(i, 2026-09)`, unrealized). This is not a data-quality problem to fix — it is
*exactly* the row a live inference call is for: the model predicts precisely because the target does
not exist yet. Both cases produce a null target, for different reasons, and the prediction schema
(§11) reflects this: `actual_stress_score` is null for a live-inference row *by definition, until
later backfilled*, whereas a historically-incomplete-window row is null *permanently* and is simply
not part of any training or evaluation set at all.

### Why the 3-month max target needs purging/embargo at split boundaries

`target_stress_3m(i,t) = max(stress(i,t+1), stress(i,t+2), stress(i,t+3))` is built from **realized
outcomes up to three months after** the row's own `prediction_date`. This creates two distinct
problems at a split boundary that the 1-month target has to a much smaller degree:

1. **Direct target leakage across the boundary.** A training row with `prediction_date` close to
   `validation_start` can have a 3-month target window that reaches *into* the validation period.
   Even though that row's *features* are correctly cutoff-limited (no feature leakage), its *label*
   encodes realized information from calendar months that are supposed to be held out.
2. **Overlapping-window autocorrelation near the boundary.** Consecutive rows' 3-month windows share
   up to two of three months with their neighbors (the same mechanical-persistence effect flagged in
   this project's target-design phase for the 3-month horizon generally). Rows just inside the
   training side of a boundary are highly correlated with rows just inside the validation side —
   even after removing the rows with a directly-overlapping window, the *remaining* boundary-adjacent
   rows are still more similar to each other than a validation metric assumes.

### Purge rule (formalized, horizon-general)

For a horizon with `forecast_months = h`, a training row at `prediction_date = t` is **purged**
(excluded from training, though it may still be a valid row for a *different*, earlier fold) if:

```text
t + h  >=  validation_start   (using first-of-month dates throughout)
```

Equivalently, the last usable training `prediction_date` for that horizon is:

```text
last_eligible_train_date = validation_start - (h + 1) months
```

**Worked calendar example** (illustrative dates, not from real data): let
`validation_start = 2023-01-01`.

- For `global_model_1m` (`h = 1`): `last_eligible_train_date = 2023-01 - 2 months = 2022-11-01`.
  Its window is `[2022-12]`, which ends before `2023-01` — clean.
- For `global_model_3m` (`h = 3`): `last_eligible_train_date = 2023-01 - 4 months = 2022-09-01`.
  Its window is `[2022-10, 2022-11, 2022-12]`, which ends before `2023-01` — clean. A training row at
  `2022-10-01` would **not** be eligible for the 3-month model (its window `[2022-11, 2022-12,
  2023-01]` reaches into validation), even though it *would* still be eligible for the 1-month model
  (window `[2022-11]`, entirely pre-validation). This is the concrete instance of §4's "different
  eligible-row sets per horizon."

### Embargo (beyond the strict minimum)

In addition to the strict purge above, an `embargo_months` buffer (configurable per horizon, §8)
removes a few *additional* months immediately before `validation_start` from training, to further
damp the residual autocorrelation from point 2 above. The same purge-then-embargo logic is reapplied
at every fold boundary in the rolling-origin evaluation (§6), not just once at a single train/test
split.

### Assertions

Every split, for every horizon, must pass:

```text
assert max(train.prediction_date) + horizon.forecast_months + horizon.embargo_months
       < min(validation.prediction_date)

assert max(validation.prediction_date) + horizon.forecast_months + horizon.embargo_months
       < min(test.prediction_date)
```

i.e. "the latest target month any training row could reach into precedes the evaluation period" is
checked directly, not inferred from the split-boundary *parameters* alone — this is deliberately the
same defensive-recheck pattern `evaluation/splits.py`'s existing `time_based_split` already uses for
the (weaker, no-purge) 1-month-adjacent case, extended here to account for the forward-looking target
window.

**Implementation status**: this purge/embargo behavior is not yet implemented in
`evaluation/splits.py` — `time_based_split` as scaffolded takes no `purge_months`/`embargo_months`
argument. Extending it is a scoped Phase 1 Group E follow-up, not something this document assumes
already works. §12 specifies the tests that implementation must pass.

---

## 8. Horizon configuration (draft schema)

Integrated into the existing `configs/model.yaml` style (see that file for the live draft; the shape
below is the authoritative specification this document is responsible for):

```yaml
horizons:
  "1m":
    target_column: target_stress_1m
    forecast_months: 1
    aggregation: point
    require_complete_window: true
    embargo_months: 1          # placeholder default, not yet tuned — see §14
    model_artifact_name: global_model_1m
    definition: "target_stress_1m(i,t) = stress(i, t+1)"

  "3m":
    target_column: target_stress_3m
    forecast_months: 3
    aggregation: maximum
    require_complete_window: true
    embargo_months: 1          # placeholder default, not yet tuned — see §14
    model_artifact_name: global_model_3m
    definition: "target_stress_3m(i,t) = max(stress(i,t+1), stress(i,t+2), stress(i,t+3))"

incomplete_window_policy: exclude   # never compute max over fewer than forecast_months realized months
```

`aggregation: point` vs `aggregation: maximum` is what a target-construction function
(`targets/stress_index.py`'s still-stubbed `compute_horizon_targets`) dispatches on;
`require_complete_window` and `incomplete_window_policy` together implement §7's exclusion rule;
`embargo_months` and `forecast_months` together implement §7's purge/embargo formula;
`model_artifact_name` is the key into §9's artifact directory layout.

---

## 9. Baseline comparison plan

*(Unchanged from the previous revision; run independently per horizon per §4 — every candidate below
produces two fitted objects, one per horizon, never one shared object.)*

All of the following are evaluated under the *identical* embargo-respecting splits from §6–§7 — this
is Gate C from `docs/project_roadmap.md`, restated at the model-comparison level:

| Candidate | Family | Notes |
|---|---|---|
| Historical mean | naive | industry's own training-period mean `stress_score`, per horizon |
| Persistence | naive | last realized `S(i,t)` carried forward unchanged — **the benchmark every other candidate is compared against (Gate D)** |
| Seasonal | naive | applicable only where a real seasonal pattern is confirmed per industry (open decision, `docs/project_roadmap.md` §11) — not applied blanket to all 12 |
| Ridge / Elastic Net | linear, regularized | uses one-hot `industry_id` + all four feature groups including explicit interaction terms, since it cannot learn interactions itself |
| Random Forest / Extra Trees | tree ensemble | handles interactions implicitly; robust at modest sample size; feature importance "for free" |
| Histogram Gradient Boosting (`sklearn.ensemble.HistGradientBoostingRegressor`) | boosted trees | native categorical + native missing-value support; **no new heavy dependency** — already available via scikit-learn, which Ridge/Random Forest also need |
| XGBoost / LightGBM | boosted trees | **gated** — only adopted if HistGradientBoosting demonstrably underperforms on validation *and* a specific, documented reason exists to expect the alternative library to help; not adopted merely because it is popular. Same reasoning already applied to ruling out graph neural networks (`docs/project_roadmap.md` risk R-8) |

**No winner is selected in this document or before out-of-sample (test-period) evaluation**, and no
winner is selected jointly across horizons either — `global_model_1m` and `global_model_3m` may end
up being different model families if validation performance says so; there is no requirement that
both horizons use the same estimator type.

---

## 10. Evaluation

*(Unchanged from the previous revision, except the diagnostics cross-reference below now correctly
points to §10 in this document — the previous revision mistakenly said "§10" when the diagnostics
were actually in §8; they are still §10, but the fix is noted since the surrounding section numbers
have all shifted in this revision.)*

### Cuts
Every metric is computed on each of the following slices, not only "overall": **overall** (pooled
test rows) · **by industry** (12 separate breakdowns) · **by calendar period** (one breakdown per
rolling-origin fold) · **by horizon** (1-month and 3-month reported and judged separately, from two
separate models — never pooled together) · **during known shock periods** vs. **during normal
periods**, where "known shock period" means an independently-documented real event, never a
model-defined period.

### Regression metrics
MAE, RMSE, median absolute error, and Spearman rank correlation **across industries within each
calendar month** (`evaluation/metrics.py`'s existing `mae`, `rmse`, `spearman_correlation` functions,
applied per-month-group as an evaluation-harness detail, not a new formula).

### Warning metrics
High/Severe precision and recall, macro F1, false-alert rate, missed-event rate — already
implemented in `src/thai_supply_chain_ews/evaluation/metrics.py`.

### Uncertainty / confidence estimates
**Not included in the MVP** — deferred to Phase 2 (`docs/project_roadmap.md` P2-9), for the same
data-scarcity reason as before. If ever added, it too would need to be fit per horizon, per §4.

---

## 11. Prediction output schema

Long format, one row per `(target_industry_id, prediction_as_of, horizon, model_version)` — this is
the table that serves the dashboard and any monitoring/backtest report, and is the one place both
horizons' outputs sit side by side (everything upstream of this is horizon-separated per §4).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `prediction_as_of` | date | no | the month `t` this prediction is *for* — equivalent to `prediction_date` elsewhere in this document; named to match this task's requested schema |
| `target_industry_id` | string | no | `IND-01`..`IND-12`; equivalent to `industry_id` elsewhere |
| `horizon` | string | no | `"1m"` or `"3m"` |
| `predicted_stress_score` | float64 | no | 0–100, from the horizon-appropriate model (§9, test 9 checks the bound holds after calibration) |
| `predicted_risk_level` | string | no | `Normal`/`Watch`/`High`/`Severe`, from that horizon's own train-only thresholds (§9, test 10 checks consistency) |
| `actual_stress_score` | float64 | **yes** | null at prediction time; backfilled once the real `stress(i, t+h)` is realized. **Kept null during live inference** — never estimated, guessed, or backfilled with a placeholder |
| `actual_risk_level` | string | **yes** | same backfill timing as above |
| `model_version` | string | no | identifies the exact fitted artifact (§13) that produced this row — part of the primary key, since a re-fit model scoring the same `(industry, month, horizon)` again is a distinct, comparable prediction, not an overwrite |
| `feature_data_cutoff` | date | no | the `available_as_of`/`cutoff_date` boundary actually enforced when this row's features were built (§1) — the point-in-time audit trail carried through to the output |
| `generated_at` | timestamp | no | wall-clock time this row was produced by the pipeline — distinct from `prediction_as_of` (a business/domain date) and from `feature_data_cutoff` (a data-availability boundary); three different dates answering three different questions |
| `warning_drivers` | string (JSON array) | yes | the per-prediction "main contributing factors" output (`docs/project_roadmap.md` task G2) — null only for `Normal`-level predictions where no warning is being issued; required whenever `predicted_risk_level` is `Watch`, `High`, or `Severe` |
| `data_quality_flag` | string | no | carried from the source panel row (§1) |

Primary key: `(target_industry_id, prediction_as_of, horizon, model_version)`. This is well-defined
under the assumption that a given `model_version` is deterministic — identical inputs to the same
fitted artifact produce identical outputs, so re-running the same `model_version` against the same
inputs is idempotent, not a source of duplicate/conflicting rows.

---

## 12. Artifact isolation and versioned directory layout

Each horizon has its **own, completely separate** set of artifacts — nothing here is shared once
fitting begins (§4):

```text
models/
├── global_model_1m/
│   └── <model_version>/
│       ├── metadata.yaml            # model family, training window, config snapshot — tracked in Git
│       ├── feature_list.yaml        # exact feature columns this artifact expects — tracked in Git
│       ├── evaluation_report.md     # §10 metrics for this artifact — tracked in Git
│       ├── preprocessor.joblib      # fitted on global_model_1m's eligible rows only — NOT tracked
│       ├── estimator.joblib         # NOT tracked
│       └── calibration.joblib       # train-only risk-level thresholds — NOT tracked
└── global_model_3m/
    └── <model_version>/
        ├── metadata.yaml
        ├── feature_list.yaml
        ├── evaluation_report.md
        ├── preprocessor.joblib      # fitted on global_model_3m's eligible rows only — a DIFFERENT
        │                             # fitted object from global_model_1m's, per §4's rule
        ├── estimator.joblib
        └── calibration.joblib
```

- `<model_version>` is a directory name, not yet a fixed naming convention — see §14 (this reuses the
  still-open `run_id` naming decision, `docs/architecture/decision_log.md` AD-07).
- Binary artifacts (`*.joblib`, and any future `*.pkl`) are excluded from Git by the existing
  `.gitignore` (already global patterns, confirmed correct in the scaffolding step). The three
  human-readable files per version (`metadata.yaml`, `feature_list.yaml`, `evaluation_report.md`) are
  small text and **are** committed — nothing in `.gitignore` matches them, by design, the same
  "commit the small curated artifact, ignore the bulk regeneratable one" pattern already used for
  `data/mapping/` vs. `data/raw/`.
- `docs/project_roadmap.md` task F1's model-selection step and task F4's test-period scoring both
  write into this layout — one `<model_version>` directory per fitted run, never overwritten in
  place, mirroring `data/model_input/<run_id>/`'s own immutability convention.

---

## 13. Testing requirements

Specification only — these are the tests Phase 1 Groups B, E, and F must add once the corresponding
implementation (`targets/stress_index.py`, `evaluation/splits.py`'s purge extension,
`models/{train,predict}.py`) exists. None of them can be written as *passing* tests yet, since the
functions they target are still `NotImplementedError` stubs; writing them now would either mean
testing nothing real or quietly implementing the logic under the guise of a test, both of which this
step avoids.

| # | Requirement | Target function (once implemented) | Example calendar assertion |
|---|---|---|---|
| 1 | Correct 1-month target shifting | `compute_horizon_targets(..., horizon="1m")` | for `t = 2022-05`, `target_stress_1m` at `t` equals the realized `stress(i, 2022-06)`, and nothing else |
| 2 | Correct 3-month forward maximum | `compute_horizon_targets(..., horizon="3m")` | for `t = 2022-05` with realized `stress` values `[10, 40, 25]` at `2022-06/07/08`, `target_stress_3m` at `t` equals `40`, not the mean or the last value |
| 3 | Incomplete future-window removal | the eligibility filter feeding both `build_industry_month_panel` and the horizon-specific `model_input` builder | if `stress(i, 2022-08)` is missing, the row for `t = 2022-05` is **absent** from the 3-month eligible set entirely — not present with a max computed over the other two months |
| 4 | No future features | `data/validate.py::check_feature_respects_cutoff` | **already implemented and passing** (`tests/test_no_leakage.py::test_feature_row_that_reads_the_future_is_flagged`) — this requirement is satisfied by existing infrastructure; the only addition needed is confirming it is exercised identically for both horizons' feature tables, since feature generation is shared (§4) |
| 5 | No target-window overlap across split boundaries | the purge extension to `evaluation/splits.py` (§7) | with `validation_start = 2023-01-01` and `forecast_months = 3`, a training row at `t = 2022-10-01` (window reaching into `2023-01`) must be excluded; a row at `t = 2022-09-01` (window ending `2022-12`) must be kept — the worked example from §7, made concrete as a test |
| 6 | Same-month industry rows staying in one split | `evaluation/splits.py::time_based_split` | **structurally already guaranteed** (partitioning is date-based, not row-based) and indirectly covered by `tests/test_no_leakage.py`'s existing split tests; a new, explicit test with two-or-more industries sharing one `prediction_date` is recommended purely to make the guarantee unambiguous in the test suite, not because the current design is suspected to fail it |
| 7 | Correct model artifact selected by horizon | a `load_model(horizon)`-style loader once `models/predict.py` is implemented | requesting `horizon="1m"` never returns a `global_model_3m/` artifact and vice versa; requesting an unknown horizon string raises rather than silently defaulting |
| 8 | Prediction schema validation | a schema-check function analogous to `data/validate.py`'s existing pattern, applied to §11's table | every row has non-null `prediction_as_of`, `target_industry_id`, `horizon` in `{"1m","3m"}`, `model_version`; `actual_stress_score`/`actual_risk_level` are allowed null, everything else is not |
| 9 | Scores remain within 0–100 after calibration | the calibration step in `models/train.py`/`predict.py` | feeding a synthetic raw model output outside `[0, 100]` (e.g. an unclipped linear extrapolation) through calibration yields a value clipped to `[0, 100]`, never outside it |
| 10 | Risk labels match calibrated thresholds | the `assign_risk_level`-style function (design already given in `docs/architecture/data_architecture.md` §8 pseudocode) | given a fitted threshold object `{q60, q85, q97}` and a score exactly at each boundary, the returned label matches the documented `<`/`>=` convention consistently (no off-by-one at a boundary value) |

---

## 14. MVP modeling acceptance criteria

1. All baselines and candidates (§9) are evaluated under identical, embargo-respecting time splits
   (§6–§7), separately per horizon — no exceptions, checked by code review against
   `evaluation/splits.py`'s guarantees once the purge extension lands.
2. At least one candidate improves at least one early-warning metric over the persistence baseline
   on the untouched test period, **for each horizon independently** — a win on `global_model_1m`
   does not excuse `global_model_3m` from the same bar, and vice versa — **or** the absence of such
   an improvement is documented honestly for whichever horizon(s) it applies to. Gate D, extended to
   both horizons explicitly.
3. Item 2's comparison is reported **per industry**, not only pooled (diagnostic 6, §10).
4. Diagnostics 1–8 (§10) are run and reported for **both horizons separately**.
5. If target encoding was explored at all (against §5's recommendation), its fold-safety is proven —
   and proven **per horizon**, per §4's rule — before any result using it is reported.
6. Any uncertainty/confidence output present is accompanied by a documented calibration check;
   otherwise it is not labeled as an interval or a confidence estimate.
7. Feature importance and the per-prediction "main contributing factors" output are available for
   every Watch/High/Severe prediction in the test period, for both horizons.
8. Every test in §13 passes before either horizon's model is considered ready for Gate D evaluation.
9. `global_model_1m` and `global_model_3m` each have a fully isolated artifact directory (§12) — no
   shared `.joblib` file between them, confirmed by the file listing, not just by the code's intent.

---

## 15. Items deferred to Phase 2

- Target encoding of `industry_id`, if ever revisited — only with fold-strict, per-horizon
  computation, and only if a future change actually raises cardinality enough to justify it over
  one-hot.
- Uncertainty intervals and probability calibration (`docs/project_roadmap.md` P2-9).
- XGBoost/LightGBM adoption — gated on documented evidence per §9, not adopted speculatively.
- Dynamic (time-varying) trading-partner exposure weights, if the MVP ships with static weights.
- A full leave-one-industry-out ablation suite across all 12 industries (the MVP runs this only for
  the shortest-history industries, per diagnostic 7).
- Native-categorical-encoding variant as anything more than a secondary diagnostic comparison.
- A tuned, evidence-based `embargo_months` value per horizon — the MVP ships with a placeholder
  default (§8) pending a real sensitivity check once real data exists.
- Automated model-version promotion/rollback tooling — the MVP's artifact layout (§12) is versioned
  by hand, not served by any registry.

---

## 16. Unresolved decisions (this revision)

- `model_version` naming convention (§12) — reuses the still-open `run_id` naming question
  (`docs/architecture/decision_log.md` AD-07); not resolved by this revision.
- `embargo_months` default of `1` (§8) is a placeholder, not a tuned or justified value — no
  sensitivity analysis has been run, because no real target data exists yet to run one on.
- Whether `validation_start`/`test_start`/`test_end` should ever differ by horizon (this document
  assumes they are shared, §6) — kept as the default design, revisit only if a concrete reason
  emerges once real data and a real evaluation are in hand.
- Exact rolling-origin refit cadence (illustrated as "annually" in §6, matching the reference paper's
  own choice) is not yet chosen for this project specifically.

---

## Report

**Files modified this revision**: `docs/modeling_strategy.md` (restructured and extended — see
sections 4, 7, 8, 11, 12, 13, 16 for what is new; sections 1, 5, 9, 10 carry content forward with
horizon-architecture cross-references added; the "§10" cross-reference bug from the previous
revision is fixed throughout). `configs/model.yaml` and `.gitignore` are updated to match (see the
Thai summary for the exact diffs).

No model was trained, no training code was written, and no performance number in this document is a
real or fabricated result — every metric and every calendar date mentioned is a formula or an
illustrative example, not a value read from real data.
