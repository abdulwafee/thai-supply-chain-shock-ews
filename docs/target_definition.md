# Target Definition — Industry Stress Score, Two-Stage Design

Status: design document. No target pipeline is implemented in this step
(`src/thai_supply_chain_ews/targets/stress_index.py` remains a stub), and no value in this document
is a real or fabricated observation — every formula below uses symbolic notation, and every
parameter (median, MAD, logistic scale, thresholds) is described as *fit from training data*, never
given an illustrative number that could be mistaken for a result. Per this project's own policy, the
full target pipeline is not implemented until the four source columns in §1 have verified bulk-access
(they currently do not — see `docs/data_source_inventory.md`).

This document **supersedes and formalizes** the informal target-construction description in the
target-design phase and in `docs/methodology.md`'s "Target construction" summary. Two elements are
**revised** from that earlier design: the global calibration function (§6, revised in the previous
update) and, in this revision, the component-aggregation weighting scheme (§5) — a confirmed policy
decision to use **equal weights** across all approved components, replacing the earlier
`0.6*max + 0.4*mean` blend. §1 is also substantially expanded in this revision into a full,
measurable eligibility audit, per the confirmed component-weighting policy's own requirement that no
component be approved before source verification.

---

## 1. Target components — eligibility audit

### 1.1 Measurable eligibility criteria

A component must satisfy **all** of the following before it can be marked `enabled: true` in
`configs/targets.yaml`. These are placeholders in the sense that none has been validated against real
data yet (no bulk pull has happened for any of the four candidates), but they are concrete,
checkable numbers, not vague standards:

| Criterion | Threshold | Rationale |
|---|---|---|
| Minimum time coverage | ≥ 60 months of continuous, consistently-classified history | Enough for an initial training window plus several annual walk-forward folds (`docs/modeling_strategy.md` §6) plus a held-out test window — the minimum shape a genuine walk-forward evaluation needs, not an arbitrary round number |
| Minimum industry coverage | ≥ 11 of 12 industries natively covered | A global panel model (`docs/modeling_strategy.md` §3) needs near-complete industry coverage for a component to be usable as a shared, equally-weighted input; a lone uncovered industry is absorbed by the existing missing-component fallback (§5.3), but more than one is a coverage failure, not a fallback case |
| Maximum acceptable missingness | ≤ 10% of industry-months null within the eligible window | Beyond this, a component starts materially reducing how many rows meet the ≥2-of-K minimum (§5.3), undermining its own usefulness as a shared component |
| Mapping reliability | Either an official published crosswalk, or a documented manually-derived crosswalk with a recorded confidence level (e.g. cross-referencing named sub-industries in an OIE press release, as already demonstrated feasible for MPI/CapU) | A component eligibility check, not a values check — an unmapped or guessed classification makes every downstream row unreliable regardless of the underlying data's own quality |
| No critical structural break without a documented adjustment | Either no known break in the eligible window, or a documented, verified bridging correction, or enough **post-break** history to independently satisfy the time-coverage minimum on its own | Ties directly to §4's normalization fallback — an eligibility check exists so this is decided once, in advance, not rediscovered ad hoc during normalization |

### 1.2 Audit against the four candidates

| Criterion | MPI | Capacity Utilization | Export | Producer/input-cost (PPI) |
|---|---|---|---|---|
| Official source availability | OIE — landing page confirmed reachable | OIE — same release as MPI, confirmed reachable | MOC — landing page confirmed reachable | MOC/NSO — StatHub SDMX dataflow located, confirmed reachable |
| Monthly frequency | **Confirmed** — a real OIE press release, read during the feasibility study, shows a live monthly release with a March-2024 print | Confirmed — published in the same release as MPI | Believed monthly per the portal's structure; not confirmed against an actual sample document the way MPI was | Believed monthly per the portal's structure; not confirmed against an actual sample document |
| Historical coverage ≥ 60mo | **Unverified** — the earliest continuous, TSIC-2009-consistent start date is not established (`docs/data_source_inventory.md` §5) | Same as MPI | Unverified | Unverified |
| Industry coverage ≥ 11/12 | **Unverified** — OIE's own ~45-group reporting breakdown has not been crosswalked to this project's 12 groups | Same as MPI | Unverified — depends entirely on the HS-to-industry mapping, which is currently an **empty** file (`data/mapping/hs_to_industry.csv`, zero rows) | Unverified — no CPA-to-industry mapping work has even been started (no file exists for it yet) |
| Mapping reliability | **Partial pass** — TSIC division-level mapping is verified (`data/mapping/industry_map.csv`); OIE's own reporting-group crosswalk is not | Same as MPI | Fails today — mapping table exists but is unpopulated | Fails today — mapping table does not exist |
| Publication lag | ~30 days, empirically observed **once**, from one real document — not a confirmed SLA | Assumed same as MPI (same release) | Unresolved (a secondary, unconfirmed source mentioned "~2 months" for detailed data) | Unresolved |
| Revision risk | Unverified whether OIE revises published monthly figures | Unverified | Unverified | Unverified |
| Missingness | Unverified — no bulk data pulled yet for any candidate | Unverified | Unverified | Unverified |
| Seasonal behavior | Real evidence of tourism/harvest-linked seasonality in named sub-industries, from the actual press release read during the feasibility study | Same source, level-based | Plausibly similar; not directly confirmed | Plausibly less seasonal (cost-side); not confirmed |
| Realized impact, not merely an upstream signal | **Clear pass** — a direct output measure | **Clear pass** — a direct capacity measure | **Clear pass**, for the exporting industry itself — its own export decline is a realized hit to that industry | **Ambiguous — see §1.3**, a dedicated discussion, not a quick pass/fail |
| Duplicates another component | Partial conceptual overlap with CapU expected (§5.1) — not disqualifying on its own | Partial conceptual overlap with MPI expected (§5.1) | Distinct economic channel (external demand) — low overlap concern | Distinct channel (cost-side) — low overlap concern, but see §1.3 |

### 1.3 Producer/input-cost pressure: target or feature?

This is the one candidate this audit does not resolve with a clean pass. MPI, CapU, and export
decline all measure the industry's own **output or activity** — the thing this whole system exists
to protect. Producer/input-cost pressure is different in kind: a rise in an industry's own input
costs is a real, already-realized economic burden (so there is a genuine case for treating it as a
realized-outcome target component, as originally designed) — but it is also plausibly a **leading**
signal for the *other three* components (higher costs today plausibly cause a production cut or
export-competitiveness loss one to three months later), which is closer to how this project treats
*feature* variables elsewhere (e.g. commodity and energy prices in `docs/modeling_strategy.md` §2).
Folding a leading-indicator-like signal directly into the same target the model is also given
upstream commodity/energy/FX features to predict *from* risks a form of definitional circularity —
not a temporal leakage violation, but a redundancy the model would be partly "predicting a proxy of
itself." §5.1's redundancy check 3 is designed specifically to test this empirically once real data
exists, rather than resolve it by assumption now. Until that check runs, PPI is **provisionally
retained** in the candidate set, not rejected — see §12's explicit unresolved-decision entry.

### 1.4 Verdict

**Superseded by real verification, then corrected by a quality-gate re-audit.** Task A1
(`docs/task_a1_report.md`) has downloaded and inspected the actual MPI and CapU source files (twice
— an initial audit, then a hardened re-audit that fixed two real defects: an industry-coverage
overclaim and a silent-overwrite risk in duplicate-row handling) and live-tested the Export and PPI
endpoints.

**Source access vs. target-component approval are two separate claims, tracked separately in
`configs/targets.yaml` (`source_verified` / `target_approved`)**:

- **MPI and Capacity Utilization: `source_verified: true`, `target_approved: false`.** Source access
  is genuinely strong (66 chronologically-ordered, gap-free, duplicate-free months; 0.00%
  missingness across all 22 found TSIC divisions; official native TSIC labeling and official
  value-added weights, no manual crosswalk needed). But **10 of 12 industries have full coverage and
  2 (IND-03, IND-12) have only partial coverage** — this is not the same claim as "12/12 fully
  covered," which an earlier revision of the audit incorrectly implied. Target approval is further
  blocked on: the weighted-aggregation rule for multi-division industries (designed, not
  implemented — §5.4/§4.1 of `docs/task_a1_report.md`), the IND-03/IND-12 scope decision, the
  MPI-vs-CapU redundancy test (not yet run), and the fact that only latest-vintage data has been
  inspected, not point-in-time vintages (`docs/task_a1_report.md` §6 — this project's evaluation
  must be described as "latest-vintage historical evaluation," not a true real-time backtest, until
  that changes).
- **Export and PPI: `source_verified: false`, `target_approved: false`.** Both have a confirmed,
  real, live data endpoint (an improvement over the original inventory's landing-page-only
  verification), but historical depth and classification-to-TSIC mapping remain open for Export, and
  historical depth and publication lag remain open for PPI.

See `docs/task_a1_report.md` for the full evidence table; this section is not restated in full here
to avoid the two documents drifting apart.

Practical consequence: `configs/targets.yaml`'s `minimum_components_required: 2` is met by MPI +
CapU's *source access* alone, but **no component currently has `target_approved: true`** — the
equal-weight Stress Index (§5) cannot yet be constructed from real data. Workbook parsing/ingestion
work (Phase 1 task B1's data-handling mechanics) may begin now that the hierarchy, dates, and weight
column are understood; `compute_raw_stress_index` itself stays blocked until target approval closes.

**No fifth component is added.** Candidates considered and explicitly rejected for the MVP without
further justification: employment/labor statistics and inventory-to-sales ratio were raised during
the original target-design phase and set aside for lack of a verified monthly Thai source at
industry granularity — that decision stands. Business Sentiment Index (BSI) remains a **feature**
candidate (current-conditions sub-index only, per the leakage caveat in
`docs/data_source_inventory.md` row 19), not a target component — it is a survey of perception, not
a realized outcome, and mixing perception into the realized-stress target would blur the
target/feature boundary this project has held since `docs/architecture/data_architecture.md` §0.

---

## 2. Direction of stress

Every raw component is oriented so a **higher** value always means **greater** stress, before any
normalization:

```text
r_MPI(i,t)    = -YoY%Δ MPI(i,t)                                    # production decline -> +stress
r_CapU(i,t)   = -Δ_pp CapU(i,t)  [vs. trailing 12-month own mean]  # utilization decline -> +stress
r_Export(i,t) = -YoY%Δ Export(i,t)                                 # export decline -> +stress
r_PPI(i,t)    = +(YoY%Δ PPI(i,t) - trailing12mo_avg(YoY%Δ PPI(i,t)))  # abnormal cost increase -> +stress
```

`r_PPI` is deliberately **not** raw YoY inflation — it is the *excess* over the component's own
recent trend, so a sustained-but-expected inflation regime (e.g. a multi-year period of generally
elevated prices) is not itself flagged as abnormal; only a departure from that industry's own recent
cost trajectory is.

---

## 3. Seasonal transformation

| Method | Needs no future months? | Robust to Thai seasonal patterns? | History required | Notes |
|---|---|---|---|---|
| Month-over-month (MoM) change | Yes | **No** — a normal seasonal dip (e.g. a post-holiday production slowdown, or the tourism-linked seasonality the OIE press release itself shows for food and petroleum) reads as a shock | Minimal (2 months) | Rejected as the primary transform for exactly this reason |
| Year-over-year (YoY) change | Yes | Yes, to first order — a stable seasonal pattern cancels by construction | 13 months minimum | Matches OIE's **own** published reporting convention (confirmed directly: the real OIE press release read during the feasibility study compares "เมื่อเทียบกับช่วงเดียวกันของปีก่อน" — the same period a year earlier) |
| Deviation from a rolling seasonal baseline (e.g. trailing multi-year average of the same calendar month) | Yes, **if implemented as trailing-only** | Yes, and more statistically stable than a single-prior-year YoY comparison (averages out one noisy base year) | Several years — more than YoY needs | Real trap: a *conventional* two-sided seasonal decomposition (X-13ARIMA-SEATS, STL, or any method that estimates a seasonal factor from the whole series) is normally computed with a **centered** window or using the full series — doing that naively here would read future months and violate this project's explicit restriction. Only a strictly trailing/expanding version is admissible |
| Official seasonally-adjusted series, if published | Yes | Best available, if it exists and is genuinely SA | Depends on the provider | **Needs verification** — it is not currently confirmed whether OIE publishes a seasonally-adjusted MPI/CapU variant alongside the raw series; this document does not assume one exists |

**Recommendation for the MVP**: **YoY change** for MPI and Export (matches the source's own
convention, needs no forward-looking window, needs no seasonal-decomposition machinery to get
wrong), and **point-change vs. trailing 12-month own mean** for CapU (already a bounded
percentage-of-capacity level, not a growth rate — a "% change of a %" is a less meaningful
transform for a level series, the same reasoning applied when this component was first designed).
`r_PPI` (§2) is a trend-deviation, not a raw YoY figure, for the reason given there.

**Acknowledged limitation of YoY**: a "base effect" — if the prior-year comparison month was itself
unusually depressed or elevated (e.g. a comparison against a COVID-affected month), the resulting YoY
reading can be distorted independent of the current month's true condition. A trailing multi-year
seasonal baseline (row 3 above) would reduce this, but needs more history than may currently be
available (the earliest common start date remains unverified per `docs/data_source_inventory.md`
§5) — flagged as a Phase 2 candidate refinement, not adopted now for lack of a confirmed data budget
to support it.

---

## 4. Industry-relative normalization

| Method | Robust to outliers? | Preserves magnitude for blending? | Explainable? |
|---|---|---|---|
| Standard z-score (mean, std) | **No** — a single crisis month inflates the estimated std for that industry, which then *compresses* all subsequent normal-range readings toward zero, directly undermining this project's stated goal (an industry's true typical volatility must not be contaminated by the very extreme events being detected) | Yes | Yes |
| **Robust z-score (median, MAD)** | Yes — up to 50% breakdown point on both center and spread | Yes — still expressed in deviation units, so a downstream max/mean blend across four differently-scaled components remains meaningful | Yes — "how many typical-deviations from this industry's own normal" is a one-sentence explanation |
| Percentile-based transformation (rank within own industry's training history) | Yes — fully rank-based | **No** — discards magnitude entirely; blending four *ranks* via max/mean is a different, less interpretable operation than blending four *deviation-in-sigma-units* values, and the project's global calibration stage (§6) already applies a percentile-style idea once — doing it twice loses information the second stage could use | Yes, but less suited to this pipeline position |
| Expanding-window normalization | N/A — this is a question of **refit cadence**, not of estimator choice; it answers *when* the robust-z parameters are refit (at each walk-forward fold, §8), not *what formula* computes them | — | — |

**MVP recommendation**: **robust z-score using median and MAD**, per `(industry_id, component)` pair,
refit at each walk-forward fold on that fold's own expanding training window only (§8):

```text
z_k(i,t) = (r_k(i,t) - median_k^train(i)) / (1.4826 * MAD_k^train(i))
```

The constant `1.4826` is the standard consistency correction that makes MAD-based scale comparable to
a standard deviation under a roughly normal distribution — used only to keep `z_k` on a familiar
"sigma-like" scale, not because normality is assumed anywhere else in this pipeline.

`z_k(i,t)` is then **winsorized to `[-3, 3]`** (unchanged from the earlier design) — the robust
estimator protects the *baseline* distribution parameters from contamination by one extreme month;
winsorizing the *output* additionally protects the downstream blend (§5) from any single remaining
extreme value dominating the `max()` operation.

### Fallback policy (this revision's addition — not previously specified)

| Situation | Fallback |
|---|---|
| `MAD_k^train(i) < ε` (near-zero or exactly zero; `ε` a small placeholder relative to that component's own scale, not yet tuned) | First retry with standard deviation for that specific `(industry, component)` pair only. If std is *also* effectively zero (a genuinely constant series over the training window), the component is uninformative for that industry in that window — treat it as **missing** for that row (see the missing-component fallback in §5), flagged in `data_quality_flag`, never silently set to `z_k = 0` (a false "no stress" reading) |
| Insufficient history for a given `(industry, component)` pair (fewer than a minimum number of training months — placeholder: 24, not yet tuned, pending the still-unverified real history length) | MVP default: treat the component as missing for that industry until enough history accumulates (same reduction as above); a cross-industry pooled-statistic fallback (borrowing the other 11 industries' median/MAD for that component as a temporary substitute) is noted as a defensible Phase 2 refinement, not adopted now to avoid adding an un-simple mechanism before it is known how large the real sparsity problem actually is |
| A newly-tracked industry-component series (data collection for that pair only starts partway through history) | Same mechanism as insufficient history — this is that situation's zero-months special case, not a separate rule |
| A documented structural break spans the training window (TSIC revision, MPI base-year rebase, I-O benchmark revision, HS code revision, COVID-19 — the list already tracked in `docs/data_source_inventory.md` §7) | **Do not span a known break silently.** Default: restart the expanding training window immediately after the most recent documented break date, losing pre-break history for normalization purposes rather than mixing two measurement regimes into one median/MAD estimate. If a verified, documented bridging correction exists for a specific break, it may be applied instead — but only once verified, never invented. No automatic statistical changepoint detector is added for this in the MVP; an *undetected* break is an explicit, named limitation (§10), not something this design claims to catch on its own |

---

## 5. Component aggregation

**This section revises the earlier design.** The target-design phase originally specified a
`0.6*max + 0.4*mean` blend, chosen to lean toward the worst single channel. This revision's
confirmed component-weighting policy replaces that with **equal weighting** across all approved
components. This is not a preference restatement — the a priori `max`-leaning blend is exactly the
kind of "expert-assigned unequal weight" this revision's policy explicitly rules out, and a
`max()`-dominated statistic is also harder to reconcile with several of this revision's other hard
requirements (identical weight in training/validation/test, weights stored and summing to one,
weights that do not change silently between months) than a plain average is. Equal weighting is the
simplest scheme that satisfies every constraint in the confirmed policy simultaneously, which is why
it is adopted for the MVP rather than derived from any data-driven comparison — PCA-derived and
optimized weights are explicitly out of scope for the MVP (§5.2) and are Phase-2-only questions.

### 5.1 Formula

For industry `i`, month `t`, and the set of components actually available for that row (§5.3):

```text
raw_stress(i,t) = (1 / K_available(i,t)) * sum_{k in available(i,t)} [ z̃_k(i,t) ]
```

where `z̃_k(i,t)` is component `k`'s winsorized robust z-score (§4) and `K_available(i,t)` is the
count of components available for that specific row. If all `K` approved components are approved and
available, this is the plain equal-weight mean over all of them — "if three components are approved,
use one-third each; if four, one-quarter each," exactly as specified.

### 5.2 Equal-weight requirements — how each is satisfied

| Requirement | How this design satisfies it |
|---|---|
| Same weight across all industries | Weights (`1/K`) do not depend on `industry_id` at all — there is no per-industry parameter in the formula |
| Same weight across all months | Weights do not depend on `t` — no monthly refit of the *weights themselves* (the underlying `z̃_k` values are refit per fold, per §8, but the weighting scheme is fixed) |
| Same weight in training, validation, and testing | The weighting scheme (`1/K`) is a fixed formula, not a fitted parameter — nothing about it is estimated from any split, so there is nothing that *could* differ across splits |
| Weights stored in configuration | `configs/targets.yaml`'s `aggregation.method: equal_weight` and the `components[].enabled` list together fully determine `K` and every weight |
| Weights included in model metadata | The approved component list (which determines `K` at fit time) is persisted as part of each `calibration_version` bundle (§8) |
| Sum to one | `K * (1/K) = 1` by construction whenever all `K` approved components are available for a row; §5.3 addresses what happens when they are not |
| Fixed for a model version | The approved component set is decided once per `calibration_version` and frozen with it, per §8's freeze rule |

### 5.3 Missing-component handling — and the distinction this revision requires being explicit about

A **minimum of 2 approved components** must be available for `raw_stress(i,t)` to be computed at all
(unchanged from the earlier design) — below that, the row is excluded (`insufficient_components`),
never computed from a single component.

Between that floor and the full approved set, two designs are possible, and this revision's own
restriction — "do not describe unequal effective weighting as equal weighting when missing values
cause some rows to use a different component set" — means the choice must be stated precisely, not
glossed over:

- **(a) Fixed denominator**: always divide by the full approved `K`, even when fewer components are
  available (a missing component implicitly contributes 0). **Rejected** — this silently
  understates `raw_stress` whenever a component happens to be missing, and is a real bias risk in
  exactly the periods a data source might be more likely to lag (a disrupted, high-stress period).
- **(b) Dynamic denominator**: divide by `K_available(i,t)`, the count actually present for that row
  (the formula in §5.1). **Recommended** — each row is an equal-weight average *among whichever
  components were available for it*, which keeps the statistic well-defined and unbiased, but it
  means a 2-component row and a 4-component row are not, strictly, using "the same weighting" in the
  sense of an identical set of nonzero coefficients — they are using the same *scheme* (equal weight
  among available components) applied to different component sets. This distinction must be visible,
  not hidden: every computed row carries a `components_used` field (the exact list of `component_id`s
  that contributed) alongside `data_quality_flag`, so a reader of the data can always tell a
  full-`K` row from a partial one — the requirement is transparency, not that every row secretly uses
  identical coefficients regardless of what was actually available.

**This choice is recorded as a confirmed recommendation but is explicitly flagged as a decision still
requiring final confirmation before implementation** — see §12.

### 5.4 Redundancy checks

Methodology only — these run once real, verified component data exists; results are documentation
and eligibility inputs, **never an automatic weight change**, per this revision's explicit
restriction.

| Check | Method | Use of the result |
|---|---|---|
| MPI vs. Capacity Utilization overlap | Correlation (Spearman, for the same robustness reason normalization uses rank/robust statistics) between `z̃_MPI` and `z̃_CapU`, pooled across industries and training months | Documented finding only. A high correlation is *expected* to some degree — CapU is mechanically related to realized output over capacity — and is not, by itself, a reason to drop either; it is however a reason to prioritize the "remove MPI" and "remove CapU" ablations (§5.5) to see empirically whether one is redundant given the other |
| Export dominance for export-oriented industries | Split industries by an export-intensity measure (once available — plausibly from the I-O table or a trade-share statistic, both currently unverified dependencies) into higher- vs. lower-export-intensity groups; compare the variance/informativeness of `z̃_Export` between the two groups | Documented finding only. If export-light industries show a near-flat, noise-dominated `z̃_Export`, that motivates a **Phase 2 feature** (a static export-intensity interaction term, per `docs/modeling_strategy.md` §2.4) — not an industry-specific target weight, which this revision's policy explicitly forbids |
| Input-cost pressure as feature vs. outcome | Cross-correlate `z̃_PPI(t)` against the other three components at lags `t, t+1, t+2` (a simpler cousin of the transfer-entropy lead-lag diagnostic this project's reference paper uses); if `z̃_PPI(t)` correlates more strongly with *future* declines than with the *contemporaneous* ones, that is evidence for the feature-like reading in §1.3 | Directly feeds the still-open §1.3/§12 decision on whether PPI stays a target component or moves to the feature set |
| Residual variance after normalization | Compare pooled (post-winsorization) MAD or std of each `z̃_k` across all four components | Documented finding only. A component with markedly larger post-normalization spread is disproportionately influencing the equal-weight mean's *variance* even though its *nominal* weight is identical — worth knowing, not a trigger to reweight |

### 5.5 Sensitivity analysis plan

Validation-only, per this revision's explicit restriction — **the final test period is never used to
choose the component set**, exactly mirroring Gate D's rule that the test period is never used to
choose a model.

1. **Remove one component at a time**: recompute `raw_stress` with `K-1` approved components
   (equal weight among the rest), for each of the `K` components in turn.
2. **Compare against known historical stress periods**: for each `K-1` variant, check whether it
   still tracks at least one independently-documented real episode (the same case-study method as
   Gate B), and whether removing a specific component visibly weakens that tracking.
3. **Compare event counts by risk level**: does removing a component materially change how many
   Watch/High/Severe months result, once thresholds (§7) are refit on the `K-1` variant's own
   training distribution.
4. **Compare score stability**: correlation between the full-`K` `Score` series and each `K-1`
   variant's series — a component that is genuinely redundant should leave this correlation high.
5. **Compare downstream validation performance**: once a real baseline/candidate model exists
   (`docs/modeling_strategy.md` §9), compare validation-period predictive metrics under each
   component-set variant.
6. **Inspect industry-specific score distributions**: check whether removing a component
   disproportionately changes the score distribution for particular industries (e.g. removing export
   decline plausibly matters more for IND-09 Electronics than for a domestically-oriented industry) —
   documentation only, never converted into an industry-specific weight.

---

## 6. Global score calibration

**This section revises the earlier design.** The target-design phase originally specified an
empirical-CDF transform (`Score = 100 * F_train(RawStress)`, pooled across industries). That method
is monotonic, fit-only-on-training, and explainable — but it does not satisfy this revision's
explicit new requirement that calibration be "capable of transforming future values beyond the
original training range": an empirical CDF has no defined behavior beyond the most extreme training
observation without an added, separately-designed extrapolation rule. This is a genuine new
constraint, not a preference change, so the method is revised rather than patched.

| Method | Monotonic? | Handles beyond-training-range inputs? | Fit complexity | Explainable? |
|---|---|---|---|---|
| Empirical percentile (CDF) calibration | Yes | **No**, not without an added extrapolation rule | Low (no parameters, just the training sample) | Yes — "percentile of training history" |
| Clipped linear mapping (`(x - train_min)/(train_max - train_min)`, clipped) | Yes | Only by clipping to the boundary, same saturation problem as empirical CDF, and additionally **extremely outlier-sensitive** since `train_min`/`train_max` are literally the single most extreme historical points — one crisis month sets the scale for everything else | Lowest | Yes, but for a method with real weaknesses |
| **Logistic (or Normal-CDF) mapping** | Yes, by construction | **Yes** — a sigmoid/CDF is defined and monotonic for every real input; it approaches but never exactly saturates at 0/100, so it can still order "very extreme" against "even more extreme" in the tail | Low (2 parameters: location, scale) | Yes — one closed-form formula |
| A hybrid (empirical CDF interior + a fitted tail extrapolation beyond a threshold) | Yes, if the stitching is done carefully | Yes | Higher — needs a continuity/smoothness condition at the stitch point | Less simple to state in one line |

**MVP recommendation: logistic mapping**, fit on the pooled training-period `RawStress` distribution
using **robust** location and scale estimators (median and a MAD-based scale, for the same
contamination-resistance reason as §4 — not the ordinary mean/std):

```text
Score(i,t) = 100 / (1 + exp(-(RawStress(i,t) - c) / s))

c = median_train(RawStress)          # pooled across all 12 industries
s = 1.4826 * MAD_train(RawStress)    # pooled; a placeholder scale estimator, not yet tuned
```

This satisfies every explicit requirement at once (monotonic, fit-only-on-training, fixed during
evaluation, gracefully handles out-of-range future values, reproducible from two persisted numbers,
explainable in one formula) with less implementation complexity than the hybrid alternative. The
hybrid is noted as a Phase 2 candidate if, once real data exists, the logistic's symmetric-tail
shape assumption turns out to fit the true (likely right-skewed, since it is built from a `max()`
operation) distribution poorly — that would be an empirical finding to check, not assumed now.

---

## 7. Risk thresholds

| Scheme | Interpretability given an already-0–100 calibrated score | Notes |
|---|---|---|
| **Percentile / upper-tail quantile of the calibrated Score** (e.g. `q60`, `q85`, `q97` of the training-period pooled `Score` distribution) | High — thresholds are stated directly on the same 0–100 scale the score already lives on, e.g. "Severe = roughly the top 3% of training history" | Recommended — this is the natural threshold scheme once §6 already did the work of making the score comparable and bounded |
| Robust statistical cutoffs in MAD units of the *calibrated Score* (e.g. `median(Score) + k * MAD(Score)`) | Lower — introduces a second, different unit ("MAD of an already-bounded 0–100 score") on top of a scale that was just carefully made directly interpretable | Redundant with the percentile scheme once calibration is logistic-based; not adopted |

**MVP recommendation**: fixed percentile cut-points of the pooled training-period `Score`
distribution — `q60` (Normal/Watch boundary), `q85` (Watch/High), `q97` (High/Severe) — **carried
forward unchanged** from the target-design phase, now applied to the (revised) logistic-calibrated
score rather than the empirical-CDF one. Two safeguards from that phase also carry forward unchanged
and remain load-bearing for this revision's explicit requirements:

- **Absolute-floor gate for `Severe`**: quantile membership alone is not sufficient — at least 2 of
  the approved raw components (§1) must also exceed a fixed, domain-set absolute bar (values not yet
  defined — pending domain-expert input, an explicit open item, §12) before a row is assigned
  `Severe`, even if it falls in the top training percentile. This is what prevents a training window
  drawn entirely from a calm period from manufacturing `Severe` labels by percentile alone — directly
  satisfying "must not force a Severe warning every month."
- **Training-window diversity and calibration sanity-check**: the training window should ideally
  span at least one independently-known real stress episode so the percentile cut-points are
  calibrated against a genuine event, not only calm-period noise; and once real data exists, the
  fitted thresholds should be sanity-checked against known historical episodes (the same case-study
  method as `docs/modeling_strategy.md` Gate B), not treated as correct merely because the code ran.

Thresholds are **identical across all 12 industries within one model/calibration version** (the
entire point of the two-stage design — see §8's versioning) and are **never tuned on the validation
or test period** — only ever fit on that fold's training partition, per §8.

---

## 8. Walk-forward calibration behavior

A single, shared insight resolves most of the subtlety here: the **Stress Index construction (§2–§7)
is horizon-agnostic infrastructure**. `S(i,t)` (the calibrated 0–100 score for realized month `t`) is
computed once per walk-forward fold and shared by both `global_model_1m` and `global_model_3m` — the
horizon-specific purge/embargo rules from `docs/modeling_strategy.md` §7 govern which **rows** of
this shared `S(i,t)` series are eligible to form a training example for a given horizon; they do not
change how `S(i,t)` itself is computed.

At every walk-forward fold (expanding window, same refit cadence as
`docs/modeling_strategy.md` §6):

1. **Determine eligible training months** — this fold's expanding training window, per §6 of the
   modeling strategy.
2. **Fit industry normalizers on training history** — per-`(industry, component)` median/MAD (§4),
   using only this fold's training rows, with §4's fallback rules applied wherever a pair is
   degenerate or thin.
3. **Construct/transform the training stress values** — apply the fitted normalizers, winsorize,
   and blend (§5) to produce `RawStress(i,t)` for every eligible `t`, including any `t` that only
   just became computable since the previous fold.
4. **Fit the global 0–100 calibration on training stress values** — the logistic `(c, s)` pair (§6),
   fit on this fold's pooled training `RawStress`.
5. **Determine the common risk thresholds** — `q60`/`q85`/`q97` plus the absolute-floor gate
   parameters (§7), fit on this fold's training `Score` distribution.
6. **Freeze all calibration objects** — bundle {per-`(industry,component)` normalizer parameters,
   the approved component set and the equal-weight scheme it implies (§5 — documented, not fit), the
   logistic `(c, s)`, the thresholds and floor-gate parameters} into one versioned
   `calibration_version` artifact.
7. **Transform validation/test observations** — apply this frozen bundle, unchanged, to compute
   `RawStress`, `Score`, and `risk_level` for validation/test rows. Never refit any part of the
   bundle on validation or test data, at any step.
8. **Record the calibration version** — every computed target row (train, validation, and test
   alike) is tagged with the `calibration_version` that produced it.

### Must historical target values be recomputed as the training window expands?

**No — freeze each row's calibrated target value permanently, the first time it becomes computable,
under whichever `calibration_version` is current at that fold. Never retroactively recompute an
already-frozen historical target under a later fold's refit calibration.**

Reasoning:
- **Consistency with this project's own established data-vintage policy.** Raw source data already
  follows a "first-published vintage" rule (`docs/architecture/data_architecture.md` §7) — the
  historical record is built from what was knowable at the time, not silently rewritten as later,
  revised data arrives. Applying the same discipline to the *derived* target is the principled
  extension of a rule this project already committed to, not a new one invented here.
- **Evaluation interpretability.** If historical targets moved every time the training window
  expanded, a change in a walk-forward fold's apparent performance could be caused by the model
  changing, by the *target definition* silently shifting under it, or both — impossible to tell
  apart. Freezing removes that confound.
- **Matches real production behavior.** A live system, once deployed, will score each new month once
  under its then-current calibration and move on — it will not (and should not) reach back and
  re-score last year's already-published risk levels every time it retrains. Backtesting under the
  freeze-once rule is therefore not just a modeling convenience, it is a faithful simulation of how
  the deployed system actually behaves.

The acknowledged cost — early folds' calibration is fit on less data and is noisier, and that
noisiness is then locked in for those rows permanently — is a real, named tradeoff (§10), and is the
same tradeoff any genuine walk-forward methodology accepts (including the reference paper's own
walk-forward refit design, which does not retroactively re-score its own early history either).

`targets/industry_month_targets.parquet`'s existing `threshold_manifest_ref` column (per
`docs/architecture/data_contract_industry_month_panel.md`) is **renamed to `calibration_version`** in
`schemas/targets_table.schema.yaml` to reflect that it now points to the full bundle from step 6
above, not only the risk thresholds — this is a documentation-schema rename only (the field has never
been populated by real code), not a breaking change to any implementation.

---

## 9. Missing-data policy (summary — see §4, §5 for the underlying rules)

| Situation | Row-level outcome |
|---|---|
| One or more approved components missing, ≥2 still available | `raw_stress` computed as the equal-weight mean over the available components only (§5.3); `components_used` records which ones |
| Fewer than 2 approved components available | Row excluded (`insufficient_components`) |
| `MAD` (and fallback `std`) degenerate for a component | That component treated as missing for the affected industry (reduces to the row above) |
| Insufficient per-industry history for a component | Component treated as missing until enough history accumulates |
| A row's future target window incomplete (3-month horizon) | Row excluded — see `docs/modeling_strategy.md` §7, unchanged by this document |
| Any excluded/degenerate case | Recorded in `data_quality_flag`, never silently imputed, never defaulted to a value implying "no stress" |

---

## 10. Known limitations

- YoY's base-effect distortion (§3) is not corrected for in the MVP.
- The `ε` (MAD-degeneracy threshold), the minimum-history-months threshold, and the logistic scale
  estimator are all placeholders pending real data — none has been tuned or validated yet.
- The absolute-floor gate's specific component thresholds (§7) are not yet defined — pending
  domain-expert input, tracked as an open item (§12).
- Structural breaks are only handled if their date is already documented
  (`docs/data_source_inventory.md` §7); an undetected break would silently degrade normalization
  quality across it. No automatic changepoint detection is included in the MVP.
- The logistic calibration's symmetric-tail assumption (§6) has not been checked against real data,
  since none is verified yet.
- Freezing historical targets (§8) means early-fold calibration noise is permanent for those rows —
  an accepted, named tradeoff, not an oversight.

---

## 11. Required automated tests

Specification only, per this project's established practice when the underlying implementation is
still a stub (`docs/modeling_strategy.md` §13 used the same approach) — writing these as *passing*
tests now would mean testing nothing real.

| # | Requirement | Target function (once implemented) | Example check |
|---|---|---|---|
| 1 | No validation/test observations used in normalization | the fold-level normalizer fit step (§8, step 2) | fitting on a training-only slice and a training+validation slice must yield different `median`/`MAD` whenever the added validation rows differ from the training rows — used as a canary: if they're ever identical when they shouldn't be, the fit likely leaked |
| 2 | No validation/test observations used in winsorization | the winsorize-bounds step (§4) | the `[-3, 3]` clip bounds (or any future data-derived bound) must be computed only from the training slice; same canary pattern as test 1 |
| 3 | No validation/test observations used in score calibration | the logistic-fit step (§6) | `(c, s)` fit on training-only vs. training+validation must differ whenever the underlying data differs |
| 4 | No validation/test observations used in threshold selection | the threshold-fit step (§7) | `q60`/`q85`/`q97` fit on training-only vs. training+validation must differ whenever the underlying data differs; and a direct assertion that threshold-fitting is never called with a validation/test-tagged frame |
| 5 | Higher adverse input always produces equal or higher stress | `compute_raw_stress_index` (monotonicity of the whole pipeline in each raw component, holding others fixed) | increasing any single `r_k(i,t)` while holding the other three and the fitted calibration fixed must never *decrease* the resulting `Score(i,t)` |
| 6 | Scores constrained to 0–100 | the logistic calibration step | for a wide synthetic sweep of `RawStress` inputs, including values far outside any plausible training range, `Score` stays within `[0, 100]` (holds automatically for a logistic by construction — this test exists to catch an implementation bug, e.g. a missing `100 *` factor, not to validate the math) |
| 7 | Identical thresholds across industries | the threshold-application step | `q60`/`q85`/`q97` applied to two different industries' scores in the same `calibration_version` must be the literal same three numbers |
| 8 | No forced monthly Severe category | an end-to-end check on a synthetic calm-period training sample | a training window constructed to be uniformly calm must not produce a `Severe`-labeled row that fails the absolute-floor gate — this directly tests §7's safeguard, not just its existence |
| 9 | Zero-variance industry handling | the fallback logic in §4 | a synthetic `(industry, component)` series with `MAD = 0` must fall back to `std`, then to "missing," never raise an unhandled exception and never silently produce `z_k = 0` |
| 10 | Missing-component handling | the aggregation step (§5) | a row with exactly 1 available component is excluded (`insufficient_components`); a row with exactly 2 is included, computed over those 2 only |
| 11 | Deterministic calibration | the full fold-level fit-and-freeze pipeline (§8) | running steps 2–6 twice on the identical training slice must produce bit-identical (or floating-point-tolerance-identical) `calibration_version` parameters — no hidden randomness anywhere in this pipeline (unlike model training, which has `random_seed`, this pipeline should need none) |
| 12 | Serialization and reloading of calibration objects | the `calibration_version` persistence format (§8, extending the `model_input/<run_id>/manifest.yaml` pattern already used for risk thresholds) | a bundle written to disk and reloaded reproduces identical `Score`/`risk_level` outputs on a fixed synthetic input set, compared to the in-memory object that produced the file |

### 11.1 Component-weighting and eligibility tests (this revision's addition)

| # | Requirement | Target function (once implemented) | Example check |
|---|---|---|---|
| 13 | Enabled weights sum to one | the weight-derivation step (`1/K_available`, §5.1) | for a synthetic row with all `K` approved components available, the sum of the applied weights equals `1.0` within floating-point tolerance |
| 14 | Equal weights within numerical tolerance | same | every applied weight for a given row equals `1/K_available` within a small fixed tolerance (e.g. `1e-9`) — no weight differs from another within the same row |
| 15 | Identical weights across industries | the weight-derivation step, called for two different `industry_id`s with the same `K_available` | returns the literal same weight value, independent of `industry_id` |
| 16 | Identical weights across horizons | same, called once for a `1m`-pipeline row and once for a `3m`-pipeline row with the same `K_available` | returns the literal same weight value — the Stress Index and its weighting are horizon-agnostic infrastructure (§8), so this should be trivially true by construction, and the test exists to keep it that way |
| 17 | Stable weights after serialization | the `calibration_version` persistence format (shared with test 12) | the approved component set and `K` reload identically from disk, and the weight computed from the reloaded `K` matches the pre-serialization value exactly |
| 18 | Correct adverse-direction orientation | each `r_k` formula (§2) | for a synthetic input where a component's underlying series worsens (e.g. `MPI` YoY change goes more negative), the resulting `r_k` and downstream `z̃_k` do not decrease — the same monotonicity property as test 5, checked per raw component before normalization rather than end-to-end after |
| 19 | Disabled components never enter the target | the component-selection step reading `configs/targets.yaml`'s `components[].enabled` | a component explicitly set `enabled: false` never appears in `components_used` for any row, and never contributes to `K_available`, even if its underlying data happens to be present |
| 20 | No feature-only variable enters the target accidentally | a registry cross-check against `config/sources.yaml`'s `role` field (`docs/architecture/data_architecture.md` §10 rule 6, extended here to the target-construction step specifically) | attempting to register a `role: feature`-tagged source (e.g. Brent crude, BSI) as a target component raises at configuration-load time, not silently at some later step |
| 21 | No validation/test optimization of component selection | the `enabled`/eligibility-decision process itself | a code-level assertion (or, at minimum, a documented manual review checklist) confirming the approved component set was fixed using only training-period diagnostics and the sensitivity analysis (§5.5) — never by checking validation or test metrics first and picking components that happen to score well there |
| 22 | Missing-component behavior is explicit | the aggregation step (§5.1, §5.3) | every computed row carries a non-null `components_used` list; a row computed from fewer than the full approved `K` is distinguishable from a full-`K` row by inspecting that field, never only inferable from the score's magnitude |

---

## 12. Unresolved decisions

- Numeric placeholders not yet tuned: `ε` (MAD-degeneracy threshold), minimum-history-months (24,
  placeholder), the absolute-floor gate's per-component thresholds, the logistic scale estimator's
  exact formula (`1.4826 * MAD` vs. an IQR-based alternative).
- Whether the cross-industry pooled-statistic fallback for sparse history (§4, noted but not
  adopted) should be added once the real data-sparsity extent is known.
- Whether a hybrid empirical-CDF/parametric-tail calibration (§6) should replace the pure logistic
  once real `RawStress` data can be inspected for skewness.
- Exact `calibration_version` naming/storage convention — reuses the still-open `run_id`/
  `model_version` naming question (`docs/architecture/decision_log.md` AD-07,
  `docs/modeling_strategy.md` §16), not resolved here either.
- Whether an official seasonally-adjusted MPI/CapU series exists from OIE (§3) — unverified; if
  confirmed available, it would likely replace the YoY transform as the preferred seasonal method.
- **Final component set approval** — no component currently passes the full eligibility bar (§1.4);
  this is the single most consequential open item, since it blocks everything downstream.
- **Whether PPI is a target component or a feature** (§1.3) — provisionally retained as a target
  component pending the redundancy check 3 lead-lag analysis (§5.4), which itself cannot run before
  real, verified data exists.
- **Fixed vs. dynamic denominator for missing components** (§5.3) — the dynamic-denominator design
  (`K_available`, with a mandatory `components_used` field) is recommended, but is explicitly flagged
  as still requiring final confirmation before implementation, per this revision's own instruction to
  record it as an open decision rather than treat it as already settled.
- The absolute-floor gate's specific per-component bounds (carried over, still undefined).
- Numeric placeholders carried over from the previous revision, still unresolved: `ε`
  (MAD-degeneracy threshold), minimum-history-months (60 for eligibility per §1.1, 24 for the
  per-industry normalization fallback per §4 — these are two different placeholders for two
  different purposes and should not be conflated), the logistic scale estimator's exact formula.

---

## Report

**Files created**: `docs/target_definition.md` (this file, canonical target methodology reference).

**Files modified this revision**: §1 (full eligibility audit, replacing the earlier feasibility
table), §5 (equal-weight aggregation, replacing the `0.6*max + 0.4*mean` blend, plus new §5.1–§5.5
covering the formula, requirement-by-requirement compliance, missing-component handling, redundancy
checks, and the sensitivity-analysis plan), §11 (12 tests carried over unchanged, 10 new tests added
as §11.1), §12 (new unresolved items added). §2, §3, §4, §6, §7, §8 (minor cross-reference fixes
only), §9, §10 are otherwise unchanged from the previous revision. `configs/targets.yaml` and
`docs/methodology.md` are updated to match (see the Thai summary for what changed in each).

No target pipeline was implemented, no component was approved, and no value in this document is a
real or fabricated observation.
