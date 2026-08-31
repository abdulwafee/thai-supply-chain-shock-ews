# Methodology (DRAFT)

Status: draft outline. Summarizes decisions already made in earlier design phases of this project;
contains no results, since none exist yet. Do not read any number in this document as an actual
finding — none are present by design.

## Problem framing

Given information available at the end of month `t`, estimate for each of 12 Thai manufacturing
industry groups: a 0–100 Industry Stress Score at `t+1`; the maximum Industry Stress Score expected
over `t+1..t+3`; a 4-level risk classification (Normal/Watch/High/Severe); and the main contributing
factors behind each warning.

## Relationship to the reference paper

This project adapts ideas from Igor Halperin's *"Are Three Matrices All You Need To Beat the
Market?"* (2026), which represents a market of stocks with three fixed-size matrices (a geodesic
distance matrix of return correlations, and two Markov-chain transition matrices ranking stocks by
trailing return and volatility) for dynamic portfolio optimization.

**Carried over**: the distance-matrix idea (adapted to a Dependency/Distance Matrix between
industries rather than stocks — Phase 2), the Markov-chain-with-covariates framework (adapted to a
Shock Transmission Matrix over discretized risk states — Phase 2), rank/percentile-bucketing for
outlier-robust discretization, strict walk-forward validation, and the paper's explicit discipline
around look-ahead bias, non-overlapping test windows, and not trusting an unconstrained
hyperparameter search.

**Deliberately not carried over**: portfolio construction and trading mechanics (no-trade bands,
long-short sleeves, position sizing) — not applicable, this project does not trade; cross-sectional
decile ranking at the paper's scale (built for ~300+ stocks, not appropriate for a 12-industry
universe — see the target-design phase's discussion of why a regime-aware, absolute-threshold
construction was chosen instead of market-neutral cross-sectional ranking); survivorship-bias
framing specific to equity index membership.

## Industry taxonomy

12 project-internal industry groups (`IND-01`..`IND-12`), built from the **22 TSIC 2009 Section C
divisions the current OIE edition actually reports**: 10–17 and 19–32. The canonical, machine-
readable definition is `configs/industry_mapping.yaml`, loaded and validated by
`thai_supply_chain_ews.data.taxonomy`; `data/mapping/industry_map.csv` mirrors it for CSV consumers.

Finalized in Task B1 (`docs/architecture/decision_log.md` AD-R6..AD-R8):

- **TSIC 12 (tobacco) is assigned to IND-01**, which is named "Food, Beverages and Tobacco". This
  closes AD-04. The earlier draft mapping omitted division 12 from every industry — a real coverage
  gap, not a deliberate exclusion.
- **TSIC 18 and 33 are excluded.** Neither appears as a division-total row in either verified
  current-edition workbook. They are excluded rather than imputed; whether OIE folds that activity
  into another category is unknown, since no methodology document was located.
- Each division belongs to exactly one industry, and the union covers exactly those 22 divisions.
  Both properties are asserted at config-load time, not left to review.

The draft taxonomy used during Tasks A1/A2 differs from this one and is deliberately frozen inside
the audit scripts so the preserved bridge-validation evidence stays reproducible (AD-R12). Do not
read A1/A2 industry results as if they used the taxonomy above.

## Data ingestion (Task B1 — implemented)

The MVP core panel uses the **current 2021-based OIE edition only** (AD-R5). Older editions are not
bridged in: Task A2.1 approved a both-component bridge for only 1 of 11 industries, so a bridged
panel would be unbalanced and largely unapproved. The A1/A2 bridge validation is preserved as
research documentation and is not consumed by production code.

- Source files are resolved through their retrieval manifests and gated on a pinned SHA-256 and
  edition; a mismatch aborts ingestion rather than warning and continuing.
- Industry values are official-weight aggregates of their constituent divisions, with weights
  renormalized to sum to 1 within the industry. Equal division weights are never used.
- Preliminary observations are **retained** with values intact and marked `is_model_eligible=false`
  (AD-R9) — not deleted, and not treated as final.
- `release_date` and `available_as_of` are emitted NULL because neither could be verified. This
  limits the project to a **latest-vintage historical evaluation**, not a real-time vintage
  backtest (AD-R11).

See `docs/b1_data_dictionary.md` for the full column-level contract.

## Component validation (Task B2 — implemented)

Before any Stress Index could be built, the two candidate components had to be
checked for correct adverse-shock semantics and for whether they carry distinct
information. Thresholds were pre-registered in
`configs/component_redundancy_gate.yaml` before results were computed.

**Adverse-change semantics** (positive = deterioration for both, so they are
directionally comparable after normalization):

- MPI: `-100 × (mpi_t / mpi_{t-12} − 1)`, unit percent.
- CapU: `-(capu_t − capu_{t-12})`, unit **percentage points** — additive, because
  capacity utilization is already a rate. A relative percentage change would be a
  different quantity in a different unit and is forbidden by the gate.

Both components passed: `component_semantics_approved: true`.

**Redundancy verdict: `redundant`** — pooled |Spearman| on industry-relative
ranks 0.8601 (bar 0.85), 10/12 industries |ρ| ≥ 0.75 (bar 9), median Jaccard of
top-20% stress months 0.6319 (bar 0.60). Dependence is strongest
contemporaneously in all 12 industries, and stable across both subperiods.

**Consequence: the K=2 equal-weight composite is `rejected` (AD-R15).** This
supersedes the project's earlier working assumption of a two-component
equal-weight MVP index. The verdict is marginal — failing any one of the three
conditions would have flipped it — and it hides real heterogeneity (IND-02 and
IND-03 have identical high-stress months; IND-12 and IND-07 clearly do not).
The thresholds were not moved after seeing this.

`redundant` means empirically duplicative under this gate on a 53-month sample.
It is not a claim about causation, and the converse verdict would not have meant
statistical independence — CapU is bounded by production by construction.

Full detail: `docs/b2_component_validation.md`.

## Target definition (Task B3 — implemented)

**Predicted outcome: the Industry Production Stress Score**
(คะแนนความเครียดด้านการผลิตของอุตสาหกรรม), raw measure `mpi_adverse_yoy`.

The system is the *Thai Supply Chain Shock Early Warning System*, but this
outcome is deliberately **not** called a "Supply Chain Stress Index". MPI
measures the production *consequence* of a shock. The shocks themselves —
raw materials, energy, imports, trading partners, logistics — will be
represented by future **input features**, not by the target.

Because B2 rejected the K=2 composite, the target is defined on **one component
(K=1): MPI**. CapU stays in the panel as an auxiliary indicator and possible
lagged feature, but never enters the target — including at t+1/t+2/t+3
(AD-R19). Export and PPI are not replacement target components for the MVP.

- **Raw stress**: `-100 × (mpi_t / mpi_{t-12} − 1)`, positive = deterioration.
  636 monthly observations, 2022-01 … 2026-05, 53 per industry.
- **Horizons**: 1 month (624 labels) and 3 months (600 labels, maximum over
  t+1..t+3 = "worst stress in the next three months"); 1,224 combined. Windows
  that would reach the preliminary 2026-06 are dropped, never truncated.
- **Calibration**: industry-relative empirical CDF with an explicit fit/transform
  split and a declared training cutoff; `fit` raises on post-cutoff data rather
  than trimming it. Minimum 24 reference observations. B2's full-sample
  diagnostic rank is not reused.
- **Risk levels**: Normal [0,70), Watch [70,85), High [85,95), Severe [95,100] —
  preregistered presentation bands, not ground-truth classes. The primary ML
  task remains continuous prediction.
- Raw labels are persisted; **calibrated scores are fold-specific and are not
  persisted as production outputs** (AD-R22).

Full detail: `docs/b3_target_definition.md`.

## Evaluation protocol and baselines (Task B4 — implemented)

Development origins **2024-01 … 2025-03** (15 months, 180 out-of-fold rows per
horizon), a **purge buffer 2025-04 … 2025-06** with no metrics reported, and a
**locked final test reserved and not evaluated** (h=1 120 rows, h=3 96 rows).

Leakage control at every origin: the calibrator is refitted and frozen per
origin (never once across development); calibration uses `stress_month <= t`;
training labels use `target_window_end <= t` enforced per horizon, not the
label's origin date. A month-based feature-availability contract is defined for
later tasks — explicitly not a real-time release-date rule, since verified
publication dates do not exist.

Primary metric is **macro-industry MAE** on the 0–100 score. Uncertainty comes
from a moving-block bootstrap that resamples **whole origin months**, because
180 industry-month rows are not independent.

**Development benchmarks any future model must beat**: `persistence_current_month`
at macro MAE **14.53** (h=1) and `persistence_trailing_3m_max` at **14.70**
(h=3). Persistence is strong because production stress is highly
autocorrelated; `seasonal_naive` and `industry_historical_mean` are far worse.
The 3-month choice between the two persistence variants is **not statistically
conclusive** and was settled by the preregistered false-negative tie-break.

Full detail: `docs/b4_evaluation_protocol.md`, `docs/b4_baseline_results.md`.

## Upstream shock sources (Task C1 — source verification only)

The first upstream shock family is the **World Bank Pink Sheet** monthly
commodity price data. C1 verifies and ingests it; it does **not** claim any
series improves forecasting, and no commodity series has been joined to the
target or correlated with it.

The download URL is discovered from the official landing page on each run rather
than hard-coded, because the World Bank rotates a document hash in the path
monthly.

Seven candidates were chosen on **domain relevance only**, never on observed
association with the target. Five are `source_verified` (Brent, LNG Japan,
Aluminum, Copper, Rubber RSS3). Two are `conditional` because their pricing
benchmark changed *inside* the modelled window: **Coal, Australian** switches
from a spot to a futures price at February 2022, and **Palm oil** changes grade
and delivery basis three times (Jan 2021, Nov 2024, Feb 2025). Data quality
itself is clean for all seven — 0% missingness, no duplicate months.

Three approval fields are kept distinct: `source_verified`,
`feature_semantics_approved`, `model_feature_approved`. **The latter two are
false for every candidate** — a downloadable series is not a cleared model
input.

Timing is explicitly **unresolved**: this is latest-vintage data,
same-month availability is unverified, `release_date`/`available_as_of` are null,
and the download date is not used as a proxy for historical availability. C2
must default to lagged use.

The independent FRED Brent cross-check **did not run** — FRED was unreachable
from this environment — and is recorded as `not_executed_source_unreachable`
rather than being reported as a middling result. FRED Brent must never become a
second Brent feature alongside the World Bank series.

Full detail: `docs/c1_commodity_source_audit.md`.

## Commodity feature timing (Task C1.5, revised C1.5-R1)

Before any commodity series could become a feature, the question "when was this
number actually public?" had to be answered from archived evidence.

**Two corrections first.** The initial C1.5 run reported that 62 of 65 archived
issues did not exist. That was incomplete discovery, not absence: it searched
only two pages and matched only one of the two filename forms the World Bank
uses. Parsing official document-detail pages and RELATED link lists yields **all
65 issues, none missing** (AD-R39).

C1.5-R1 then reported that no distinct February 2025 issue existed, because the
file it downloaded was byte-identical to January's. That was also wrong, and for
an instructive reason: R1 had requested the `/original/` variant of the URL,
which serves a document family's main file **regardless of the filename in the
path**. The correct `/related/` URL was on the same page and had been discarded
as an equal-ranked duplicate. February 2025 exists and is distinct (AD-R40).

The common failure in both cases was converting a **retrieval failure** into a
**claim about the world**. Every downloaded issue is now validated against its
own internal creation date and its newest displayed column before it counts, and
a checksum shared by two different validated issue months raises an error rather
than being written down as a duplicate.

**Publication timing is verified.** Reference month t is first published in month
**t+1**, usually within a week of month end (median 2 days), in **all 65 of 65**
cases. The **verified minimum publication lag is therefore 1 month**. Lag zero
stays prohibited — a month's completed value never exists at an origin inside
that month.

R1 published a lag of 2. That figure existed only because January 2025 appeared
to have no t+1 issue, which was an artefact of the wrong February download. It
was not retained: a lag follows from the evidence, and keeping 2 "to be safe"
would have preserved a pipeline defect as policy. The conservative margin lives
where it belongs instead — `recommended_operational_lag_months: 2`, explicitly
labelled a policy choice rather than a measurement.

**Publication timing and revision safety are separate decisions.** The first run
collapsed them and let revision findings null the publication lag. They answer
different questions: `minimum_publication_lag_months` is 1 and verified;
`revision_safe_lag_months` remains null because no fixed lag guarantees final
values.

**Point-in-time features are available.** First-release values are reconstructed
for all 65 required reference months and all 15 B4 development origins. Note the
asymmetry: the MPI target is still latest-vintage, so an evaluation using both is
not a real-time backtest.

**Revisions, measured over 65 months rather than 3**, and scoped to the
contracted reference window so no series can report more months than the project
uses. LNG Japan is revised in **100%** of in-window months (median 4.01%, max
34.1%) and stays ineligible for the primary feature set. Palm oil 30.8%, coal
3.5%, copper 3.1%, aluminum 1.5%. **Brent and Rubber RSS3 were never revised.**
The two pre-window months some issues display (2020-11, 2020-12) are reported
separately rather than folded into the totals.

Full detail: `docs/c1_5_commodity_timing_audit.md`,
`docs/c1_5_commodity_timing_decision.md`.

## Commodity features (Task C2 — implemented)

The archived first releases become features, and nothing more than features.

**Four series, five transformations.** Brent, aluminum, copper and rubber RSS3 —
LNG, coal and palm oil stay excluded on their C1/C1.5 findings, and no substitute
is introduced for them, because replacing an excluded series would be a new
source decision made without the verification that justifies one. Each series
gets a price level, one-/three-/twelve-month natural-log changes in percent, and
a three-month realized volatility using the population standard deviation
(`ddof=0`). **1,224 canonical rows**, matching the preregistered count exactly.

**Three availability months, kept apart.** `source_available_month` is when the
observation was actually published; `policy_available_month` is the reference
month plus the operational lag; `feature_available_month` is the later of the
two, taken over **every** input. A twelve-month change is only as available as
its oldest input, not its reference month — collapsing those is precisely how a
feature becomes usable before its evidence existed. The measured publication lag
(1) and the operational lag (2) are stored in different fields so the policy
margin can never be read back as a measurement.

**Availability is not derived from the download date.** Every archived issue here
was downloaded in the same month; if availability came from that, all 65 source
months would collapse to one value. More than 50 distinct ones appear, which is
the check that the timing is real rather than nominal.

**Lineage is hashed, not asserted.** Each row carries a SHA-256 over its ordered
input tuples — series, month, displayed text, value, issue date, issue checksum.
Omit an input, change a value, or reorder the months and the digest moves. All
1,224 rows carry distinct checksums.

**No imputation, clipping, winsorization, or rounding of calculated features.** A
missing input, a non-positive price, or a non-finite result each raises. Each
guard is exercised against a deliberately broken fixture, because a rule that has
never rejected anything is an assumption rather than a safeguard.

**A lag-1 sensitivity table exists** on the same archived evidence, labelled
`sensitivity_only`, never the default, and not compared with any target here.

C2 approves **construction, not usefulness**. No correlation, mutual information,
Granger test, feature importance, or predictive comparison was computed; the
locked test was not opened; `model_feature_approved` stays false for all four
series. A feature that is perfectly constructed and useless is a normal C2
outcome, and C2 has no way to tell the difference — by design.

One incidental finding, since **corrected in C1.5-R3**: C1.5's boolean
`estimate_marker` was set by the token `a/`, which the archived PDFs' own
footnotes define as "Included in the energy index". It is an index-membership
marker, not an estimate flag.

## Footnote and estimate semantics (Task C1.5-R3 — implemented)

A symbol was read as evidence without checking what the document said it meant.
`a/`, `b/`, `c/` and `d/` denote membership of the energy, non-energy and
precious-metals indices and an index definition — never estimation. Brent
carries `a/` in all 65 issues and was, on that basis alone, labelled an estimate
throughout. The source does not even print the tokens consistently: Rubber RSS3
shows `b/` in 22 issues and omits it in 43.

Estimate status now comes from an independent **Description** statement —
*"Liquefied natural gas (Japan), LNG, import price, cif; recent two months'
averages are estimates"*, matched in all 65 issues rather than assumed. Position
within each issue's own ordered columns decides the status: the two newest
displayed months are documented estimates, older displayed months fall outside
the rule, and an issue lacking the statement yields **`unknown`** — never
`false`, because an unparsed note means the status is unobserved, not that the
value is final.

Terminology was corrected alongside it. `estimate_to_final_transitions` claimed
finality that no issue establishes. The replacement,
`first_non_estimated_vintage`, records only the first archived issue in which the
two-month rule no longer covers a month. Under that rule LNG has **65** first
releases documented as estimates but only **63** observed transitions: reference
months 2026-04 and 2026-05 have no qualifying later issue in the archive and are
reported as **right-censored**, not as unchanged.

**The numerical revision results are untouched** — LNG 65/65 (max 34.10%), palm
oil 20/65, coal 2/57, copper 2/65, aluminum 1/65, Brent and Rubber RSS3 zero.
They were always measured independently of any marker, and were re-verified
identical. LNG stays excluded on that record. C2's 1,224 feature values,
availability months and lineage checksums were likewise verified unchanged
across all 2,448 rows; only metadata columns moved.

Full detail: `docs/c1_5_commodity_timing_audit.md` §10.

Full detail: `docs/c2_commodity_feature_protocol.md`,
`docs/c2_commodity_feature_audit.md`.

## Commodity–industry structural exposure (Task C3 — implemented)

The four approved commodity series are connected to the twelve project industries
through Thailand's own national accounts, not through correlation.

**Source.** NESDC's **Input–Output Table of Thailand 2015 (Final)**, 180 sectors,
discovered by walking NESDC's own sitemap rather than a remembered URL — the
historical I/O page now serves a WordPress page with no I/O links on it. A newer
official **2021** table exists and is structurally compatible; it is **audited and
not substituted**, because changing the structural reference year is an explicit
decision rather than a silent default.

**Extraction.** The published file is a sparse *long* table, not a matrix, and its
column codes hide subtotals: 309/409/509 subtotal the codes above them, and
190/600/700 are grand totals. Folding any of them into the intermediate block
would put final demand, imports or value added inside the technical coefficients,
so the block is selected by explicit sector-code membership and any unknown code
raises. The accounting identity `Z + value added = gross output` holds with
residual **exactly zero**.

**Coefficients.** `A[i][j] = Z[i][j] / X[j]`; `L = (I − A)⁻¹`; `T = L − I` with the
identity term removed, because a sector's own unit of output is not one of its own
requirements. Column sums run 0.0000–0.9017, condition number **7.839**,
reconstruction residual **1.11e-15**. Sector 179 has zero gross output, so its
column is *undefined* — it is excluded, never zero-filled, since writing zero
would assert it requires nothing.

**Crosswalks.** No commodity mapping is exact. Brent's sector prices crude *and*
natural gas; Aluminum and Copper resolve to the **same** sector, making their
coefficients identical by construction — one aggregate reported twice, flagged as
such on all 24 affected rows; RSS3 is one grade within its category but is
correctly separated from latex, tyres and fabricated goods. Industry aggregation
uses **official gross output**, never equal weights: summing numerator and
denominator gives the exact aggregate coefficient, so no weight is invented.

**Direction is domain knowledge, not estimation.** 45 pairs are `cost_pressure`
with sign +1. Three are `mixed_or_ambiguous` with a **null** sign, because the
industry contains the commodity's own sector and is therefore both producer and
consumer — a wrong sign is worse than an absent one.

**The sharpest caveat.** IND-12's 0.21 "aluminum" exposure comes from Jewellery,
74.7% of that industry's output, whose purchases from "Non-ferrous metal" are
largely **gold**. It is a correct reading of the official table and a poor proxy
for either LME price. Sector aggregation, not data quality, is this matrix's main
limitation — alongside a 2015 reference year applied to a 2021–2026 window under an
explicit time-invariance assumption.

These are structural accounting ratios under fixed proportions: **not** price
pass-through elasticities, **not** causal effects, and **not** evidence that any
exposure predicts anything.

Full detail: `docs/c3_commodity_exposure_matrix.md`,
`docs/c3_industry_crosswalk.md`, `docs/c3_io_source_audit.md`.

## Source and proxy corrections (Task C3-R1 — implemented)

Two corrections, one about a source and one about meaning.

**The 58-sector workbook exists.** C3 reported that NESDC publishes only a
180-sector 2015 table. In fact it publishes four aggregation levels, and
`DataIO2015x58.xlsx` sits in the WordPress media library — which C3's discovery,
scoped to download pages and their file redirects, never queried. The 2015
download page carries exactly one link, so that path could never have found it.
The transport handling was not at fault; the WAF retry, redirect and
404-with-body logic all worked. What made an ordinary bug consequential was the
same step as in C1.5-R1: **"my one mechanism did not find it" was written down as
"it does not exist officially".**

The 180-sector table **remains primary**, because 58 sectors cannot separate
wooden from metal furniture or refineries from other petroleum products. The
58-sector file serves as an independent check, and it is a good one: **12 of 12
partition-invariant grand totals match exactly**, at a tolerance preregistered
from the source's thousand-Baht precision. A sector-level comparison would need
an official 180-to-58 concordance; none exists in the classification PDF, the
455-page official publication, or the media library, and the 58-sector scheme
regroups rather than concatenates. Rather than fit a partition by subset-sum —
which is not evidence and would not be unique — that reconciliation is recorded
as **not executed**, a third state distinct from passed and failed.

**A valid coefficient is not a valid proxy.** C3 marked all 48 pairs "resolved,
medium confidence" and stopped, conflating *is the coefficient available?* with
*does this category represent this commodity here?* A gate now separates them,
deriving each verdict from the industry's dominant purchasing component checked
against that component's official definition.

Only **2** pairs earn commodity-specific fitness — refineries buying crude, and
tyres buying natural rubber. **44** are broad proxies. **2** are not fit at all:
IND-12's non-ferrous exposure is 95.7% driven by Jewellery, whose official
definition names *precious metals, silver, gold* — a correct number and a bad
proxy for either LME price. **43 of 48** pairs are feature-eligible; the five
that are not fail for two reasons kept deliberately distinct: two on proxy
fitness (the number is fine, the meaning is wrong) and three on direction (the
meaning is fine, the sign is genuinely ambiguous where an industry both produces
and consumes the commodity).

**Every ineligible pair keeps its coefficient.** Eligibility is a usage decision;
zeroing or deleting would make "not suitable" indistinguishable from "no
exposure". And the 24 shared-sector rows now carry an explicit double-counting
flag: aluminum and copper read the *same* coefficient, so an aggregate shock
index may include it at most once.

No C3 number moved — all 48 exposures, directions and signs are byte-identical.

Full detail: `docs/c3_io_source_audit.md` §9–11,
`docs/c3_commodity_exposure_matrix.md` §12.

## Industry-conditioned commodity features (Task C4 — implemented)

The commodity features and the structural exposures finally meet:

```
conditioned = commodity_feature_value  x  exposure  x  direction_sign
```

**43 eligible pairs × 306 observations × 3 variants = 39,474 rows.** The five
pairs C3-R1 excluded generate nothing, keep their coefficients, and are tracked
in a separate exclusion audit — an ineligible pair is never filled with zero,
because zero is a real exposure value here and would be indistinguishable from a
structural exclusion.

**The availability question is the one that could have gone wrong invisibly.**
The I/O table's reference year is 2015, but that is what it *describes*, not when
it was published. Backdating it would have handed every 2024 forecast origin four
years of structure nobody could read — and because the structure is constant, the
leak would leave no trace in any output. The publisher's own download page dates
the release `31 มี.ค. 2563` = **2020-03-31**, verified against a known case (the
same field on the 2021 page reads 2025-02-25, matching that table's known
release). That precedes every development origin, so the primary matrix proceeds
— but `fully_real_time` stays **false**, because the MPI target is still
latest-vintage. Availability is then `max(feature month, structural month)`: a
feature built from two things is only as available as the slower one.

**Three variants, each varying exactly one assumption** — primary (lag 2,
direct), timing sensitivity (lag 1), structural sensitivity (total
requirements). There is deliberately no lag-1-plus-total variant: changing two
assumptions at once produces a difference nobody can attribute to either, and the
variant class refuses to construct it.

**Six kinds of absence are kept apart**: a structural zero (the industry uses
none of it — 11,000 rows), a flat price (77 rows), both, an ineligible pair, an
observation not yet published, and insufficient history to compute. Collapsing
any two would make an absence of knowledge look like a measurement.

**The development snapshot uses availability metadata, not positional shifting.**
15 origins × 12 industries = 180 rows, 3,225 eligible cells and 375 structurally
unavailable ones, each cell selected as the latest reference month whose
conditioned feature was actually available by that origin. A fixed shift would
agree only while publication stayed regular and diverge silently when it did not
— and this project measured the publication lag precisely so it would never have
to guess.

Aluminum and copper keep separate price signals but share one I/O coefficient, so
18,360 rows forbid additive aggregation and a validator — exercised on real rows,
not merely written — rejects any aggregate containing sector-107 exposure twice.

The result is a **structural interaction feature**: not a monetary cost, not an
elasticity, not a causal effect. C4 builds predictors and evaluates none of them.

Full detail: `docs/c4_industry_conditioned_feature_protocol.md`,
`docs/c4_industry_conditioned_feature_audit.md`.

## First predictive model (Task D1 — implemented, negative result)

The commodity features were finally put to the test, and **they lost**.

**Design.** A residual correction on top of the B4 persistence benchmarks:
`r = y - b`, `y_hat = b + r_hat`, one ridge per outer origin, horizon and
industry, coefficients never pooled. Framing it as a residual makes the benchmark
the floor by construction — a model that learns nothing reproduces persistence
exactly — so the comparison asks only whether commodity information adds anything
*beyond* what persistence already captures.

**Result.** It does not. Macro MAE 15.31 vs 14.53 at h=1 and 16.11 vs 14.70 at
h=3; skill −5.4% and −9.6%; the paired 95% CI excludes zero in the *benchmark's*
favour at both horizons; only 2 of 15 origins favoured the model. Under the
preregistered rule both horizons are `incremental_signal_not_supported`.

The nested selection told the same story independently: alpha 100.0 — the most
regularized value in the grid — was chosen at 27 of 30 origin-horizons. The
procedure was shrinking the commodity correction as close to zero as it could.

**One asymmetry worth recording.** The model catches more high-stress events than
the benchmark (recall 0.70 vs 0.65 at h=1, 0.90 vs 0.83 at h=3, with fewer false
negatives) by predicting more events at worse precision. The preregistered rule
says high-stress metrics may qualify the discussion but never override the MAE
verdict — and the rule was fixed before those numbers existed. Both sensitivity
variants were also worse than the primary, and by design could not have rescued
it either.

**Two leakage rules did the real work.** Labels enter training only when
`target_window_end <= t` — selecting on the origin alone would admit a 3-month
window still open at the cutoff. And a training row belonging to historical
origin *u* is built from what was known **at u**, not at *t*; refreshing it would
let the model learn from a version of history that never existed. Both have
synthetic failure tests, as do scaling on the whole development period, selecting
alpha on the outer target, fitting aluminum and copper together, and zero-filling
an ineligible feature.

**A conflict with the brief, resolved in favour of the guard.** The brief expected
inner validation to start at 2023-03/2023-05. B3's stress series begins 2022-01,
so the calibrator's 24-observation minimum is not met until 2023-12 — leaving 1
inner month at h=1 and 0 at h=3 for the first outer origin. D1 kept the guard,
reported the expectation as unmet, and fell back at six origin-horizons to the
most regularized, smallest configuration: a fallback that pulls the model *toward*
the benchmark and so can only make it look worse.

**What this does not establish** is that commodity prices are irrelevant to Thai
industrial production. The chain tested is narrow: four broad proxies, a static
2015 exposure structure, 15 effective months, and a latest-vintage target.

The locked final test remains **unopened**, and no feature is model-approved.

Full detail: `docs/d1_modeling_protocol.md`, `docs/d1_development_results.md`.

## Target construction (summary — see `docs/target_definition.md` for the full, canonical design)

A two-stage design, with an explicit, verification-gated eligibility audit sitting in front of it.
**Component eligibility**: four candidate components (production decline, capacity-utilization
decline, export decline, abnormal producer-cost increase) are evaluated against measurable
criteria (minimum time coverage, minimum industry coverage, maximum missingness, mapping
reliability, no unadjusted structural break) — as of this revision, **none currently passes**, so
none is marked enabled yet; MPI and Capacity Utilization are the most feasible on current evidence,
Export is next, and input-cost pressure is least advanced and additionally carries an open question
about whether it is a realized outcome or more of a leading feature (`docs/target_definition.md`
§1.3). **Stage 1 (industry-relative normalization)**: whichever components are approved are each
normalized *per industry* using a robust z-score (median and MAD, not mean/std, so that one past
crisis month cannot inflate an industry's estimated "normal" volatility and desensitize it going
forward), winsorized to `[-3, 3]`, then combined with **equal weight** (`1/K` for `K` approved
components — a confirmed policy decision, replacing an earlier `0.6*max + 0.4*mean` blend
specifically because equal weighting is the simplest scheme that satisfies every constraint in that
policy — same weight across industries, months, and splits, no PCA or optimized weighting in the
MVP). **Stage 2 (global calibration)**: the blended `RawStress` is mapped to a 0–100
`Score` via a **logistic function** fit on the pooled training-period distribution (robust
location/scale, i.e. median and MAD-based) — revised from an earlier empirical-CDF design
specifically because a logistic handles future values beyond the training range gracefully, which an
empirical CDF does not without added machinery. Risk levels are assigned by training-only percentile
thresholds (60/85/97) of the calibrated score, identical across all 12 industries, with an
absolute-floor gate required for the `Severe` class so that a quiet training period cannot
manufacture `Severe` labels by definition alone. Every fitted parameter at both stages is refit at
each walk-forward fold on that fold's training data only and frozen for validation/test — including
a specific rule that **already-computed historical target values are never retroactively
recalculated** when the training window later expands (the same "first-published vintage" discipline
this project already applies to raw source data, extended to the derived target).

Forecast horizons: `stress_score_1m(i,t) = S(i,t+1)` (point forecast); `stress_score_3m(i,t) =
max[S(i,t+1), S(i,t+2), S(i,t+3)]` (worst-case-in-window, chosen over a point forecast at `t+3`
because an early-warning system must catch a shock at any point in the quarter). The two horizons are
implemented as two independent fitted models, `global_model_1m` and `global_model_3m` — never a
shared multi-output estimator — with their own purge/embargo boundaries; see
`docs/modeling_strategy.md` for the full two-horizon architecture.

## Data

See `docs/data_source_inventory.md` for the full, verification-status-tagged source list, and
`docs/architecture/data_architecture.md` for the point-in-time pipeline design (`raw` → `interim` →
`mapping` → `processed` → `features` → `targets` → `model_input`) that enforces it.

## Evaluation (planned, not yet executed)

Regression metrics (MAE, RMSE, Spearman rank correlation across industries, error by industry, error
by horizon) and early-warning metrics (recall/precision for High+Severe, macro F1, false-alert rate,
missed-event rate, warning lead time where measurable), computed on an untouched test period and
compared against a persistence baseline — never claimed from validation-period numbers. See
`docs/project_roadmap.md` §4 for the full metric list and Gate D for the acceptance rule (the model
is not assumed useful unless it beats baseline; a documented loss is an acceptable Phase 1 outcome).

## Target publication timing and history extension (Task D2 — implemented, audit only)

D2 audited the OIE MPI **target** source family. It built no feature, joined no
target, tuned nothing, changed no split and left the locked test closed. A hard
guard (`numerical_audit_cutoff_month = 2025-06`) is enforced in code by
`GuardedMonthlyReader`, which raises `NumericalCutoffError` rather than returning
an index value for a later month. Structural metadata — month labels, marker
glyphs, checksums, headers — stays readable, which is what a timing audit needs.

**The B4 current-month assumption is violated.** OIE first publishes reference
month *t* a median **29 days** after *t* ends (min 23, max 66, n=111 credible
months), i.e. during month *t+1*. So `availability_lag_months = 1` and at
forecast origin *t* the most recent published month is **t-1**, not *t*. B4
baselines and D1 feature assembly both rest on the assumption that current-month
stress is known at *t*. The finding is recorded; **the split is not changed and
no model is rerun**, because correcting it is a separate deliberate decision, not
a side effect of measuring.

**History cannot be honestly extended, so the D1 fallback cannot be remedied this
way.** D1 fell back on 6 of 15 origins for lack of pre-origin calibration
history. Extending MPI history backwards was the candidate remedy. The live
2021-based edition starts **2021-01**, after the required **2020-04**, so
reaching the requirement means joining an older edition — and every route fails
the preregistered compatibility gate:

* over the 36 shared months of the 2016- and 2021-based editions, only **2 of 21**
  divisions are a pure rescaling; **19 are re-estimated** (median ratio CV
  **3.12%**, max **6.45%**), so a constant-factor splice would fabricate history;
* TSIC division **16 is absent from both older editions**, while IND-03 requires
  divisions 16+17;
* the 2011-based edition labels divisions **ISIC**, not TSIC — a classification
  change, not a revision.

`silent_splicing_permitted: false`. The gate was **not** weakened to make D1
rerunnable, which the config forbids and a test asserts.

**Evidence outcome: `timing_only_supported`.** Timing is established; complete
12-industry point-in-time vintages are not available. A future target
reconstruction therefore **cannot** be described as point-in-time.

**Correction carried from D1.** D1 reporting claimed the fallback configuration
(alpha 100, channel `none`) "can only make the model look worse, never better".
That is withdrawn as unsupported: ridge at alpha 100 still fits an intercept and
can retain the Brent and Rubber predictors, so it shrinks strongly toward the
benchmark **without** a guaranteed error direction —
`fallback_effect_direction: unknown`. The D1 headline is unchanged:
`incremental_signal_not_supported`, `d1_approved_for_locked_test: false`. See
AD-R66; the original D1 wording is left in place with a correction notice beside
it rather than edited away.

Detail: `docs/d2_oie_mpi_source_audit.md`, `docs/d2_target_timing_decision.md`.

## Operational forecast-origin contract (Task D3 — implemented)

D2 showed B4's forecast origin was not operational: it used stress month *t* at origin *t*, which OIE
does not publish until month *t+1*. D3 builds the replacement as a **new versioned contract**; B4 and
D1 are untouched and remain reproducible, relabelled `non_operational_calendar_boundary_experiment`.

At forecast issue month *t*: the forecast is issued after the verified OIE release of month *t-1*,
the latest observable stress month is *t-1*, the calibrator reference ends at *t-1*, h=1 predicts
*t+1* and h=3 predicts max stress over *t+1..t+3*. It is **not** a nowcast of *t* — month *t* is
unobserved at issue time and is skipped.

Three cutoffs moved together, enforced in three separate places so they cannot drift into one
another: the stress map (`reference_month <= t-1`), the calibrator (`training_cutoff_month = t-1`),
and training labels (`target_available_month <= t`, where `target_available_month =
target_window_end + 1 month`). The last replaces B4's `target_window_end <= t`, which admitted a label
whose final MPI observation had not been published.

All 15 development issue dates are verified against the D2 release inventory and fall inside their
own issue month (lags 25–30 days). B3 raw target windows and raw values are reused **unchanged**;
B3's *calibrated* scores are not, because the D3 calibrator has the stricter *t-1* cutoff.

Operational benchmarks selected on development data only: **`operational_persistence_latest_published`**
at h=1 (macro MAE **17.0945**) and **`operational_persistence_trailing_3m_max`** at h=3 (**16.6338**).
Operational penalty vs B4: **+2.5658** and **+1.9353** — a joint effect of the publication lag, the
calibrator cutoff and the label rule, and **not** attributable to lag alone.

Contract status **`operational_month_timing_supported`**. Reported separately, never merged into one
boolean: `point_in_time_values_supported: false`, `latest_vintage_evaluation: true`,
`fully_real_time_backtest: false`. The locked final test remains unopened.

The D1 fallback correction raised in D2 now lives in
[`d1_development_results.errata.md`](d1_development_results.errata.md), so a later regeneration
cannot silently erase it. The two D1 documents were **restored by reversing the known D2
insertion; the original pre-D2 digest was unavailable, so exact historical byte identity cannot be
independently proven.** The restored files are pinned from D3 onward in
[`d3_restored_d1_checksums.json`](d3_restored_d1_checksums.json) as a forward integrity baseline,
which is not evidence of the unknown historical checksum.

Detail: `docs/d3_operational_evaluation_protocol.md`, `docs/d3_operational_baseline_results.md`.

## Verification closure and interpretation correction (Task D3-R1)

Three D3 reporting claims were wrong and are corrected here.

**Ruff.** D3 said its own files passed and the repository's remaining **79** violations were
"pre-existing". Measured with `ruff check .` (ruff 0.16.4, `pyproject.toml`,
`select = [E, F, I, UP, B]`, no exclusions, 98 files in scope), **all 79 were in the seven files
Task D2 created and never linted** — 45 in the D2 audit script alone. None were pre-existing. The
label was applied with no snapshot or recorded output behind it. All 79 are now fixed and
`ruff check .` reports **All checks passed**, with no config weakening, no exclusion, no disabled
rule family and no mass `noqa`.

Fixes were text-preserving, and behaviour was verified rather than assumed: D2 was rerun and
compared field by field (semantically identical, every blocker string included), and D3 was rerun
twice with predictions, metrics, selection and Parquet checksum unchanged. Rerunning D2 also
revealed that it **erased** the erratum link D3 had appended to its generated decision document —
the same failure mode that moved the D1 correction into a sidecar. The link is now emitted by the
D2 generator itself.

**D1 restoration evidence.** `.d2_before.json` had been deleted, so the original pre-D2 digests were
unavailable. D3 nonetheless claimed byte-level identity with the pre-D2 originals, which overstated
what could be shown. The honest
record: *restored by reversing the known D2 insertion; the original pre-D2 digest was unavailable,
so exact historical byte identity cannot be independently proven.* What is verified is that the
inserted block is absent and the original wording retained. The pinned digests
(`54a66c41…`, `80761aab…`) are a **forward** integrity baseline, not evidence of the historical
checksum.

**Artifact inventory.** D3 wrote "modified 6 files" while listing seven paths. The inventory is now
generated from the worktree (`docs/d3r1_artifact_inventory.json`): **14 created, 4 modified,
2 restored** for D3. The blanket phrase is replaced by *B1–D2 production artifacts unchanged, with
explicitly documented D1/D2 documentation exceptions*.

**Benchmark interpretation.** On macro MAE, persistence and no-contraction are **effectively tied
within uncertainty** at both horizons (h=1 paired +2.3509, CI [−2.6478, 6.5716]; h=3 +0.3453,
CI [−2.6858, 4.6333]). No further test was run on the same development sample. The preregistered
tie-break on high-stress false negatives resolves it decisively — **8 vs 21** at h=1 and **4 vs 28**
at h=3 — so the selected benchmarks are unchanged. An inconclusive MAE difference does **not** make
persistence weak: it wins on point-estimate MAE at both horizons and misses far fewer high-stress
events, while no-contraction never predicts one at all. No-contraction is **retained as a secondary
comparator**; future models must beat persistence as primary and report both.

Detail: `docs/d3r1_artifact_inventory.json`, `docs/d3r1_benchmark_interpretation.json`.

## Frozen-specification operational commodity model (Task D4 — implemented, negative result)

D4 asks the operational version of D1's question: after using only what was genuinely available at
issue month *t*, do the verified Brent and Rubber features improve on the selected D3 persistence
benchmark? The answer, on 15 development origins, is **no** at both horizons.

**Exploratory, not confirmatory.** The specification — alpha 100.0, channel `none` — is D1's
registered conservative fallback, but D1's development results had already been seen when D4 froze
it. Choosing a specification after observing outcomes is not preregistration, so
`confirmatory_evaluation: false` and `locked_test_eligible: false` regardless of the result. The
fallback was reused to avoid inventing a tuning process that 15 origins cannot support.

**Aluminum and Copper are excluded outright**, not chosen between. They read the same I/O sector 107
coefficient, so admitting either would let one shared exposure be counted twice and a channel be
picked on outcomes. The exclusion is asserted separately against the training matrix, the evaluation
row, the scaler and the fitted artifact.

**Results (primary variant, macro industry MAE):**

| | model | persistence | no-contraction | paired vs persistence | status |
| --- | ---: | ---: | ---: | --- | --- |
| h=1 | 17.5616 | **17.0945** | 19.4453 | +0.4672 [−0.2060, 1.3736] | `incremental_signal_not_supported` |
| h=3 | 17.9051 | **16.6338** | 16.9791 | +1.2713 [0.4317, 2.1098] | `incremental_signal_not_supported` |

At h=3 the paired interval excludes zero **against** the model. Event safety **passed** at both
horizons (false negatives 6 vs 8 at h=1, 1 vs 4 at h=3): the model catches more high-stress months
at worse precision, the same trade-off D1 showed. Advancement requires both gates, so
`development_candidate_supported: false`.

**The finding that shapes everything else:** C3's *direct* exposure is exactly zero for 16 of the 24
Brent/Rubber industry pairs. For **6 of 12 industries** every eligible conditioned predictor is
therefore a structural constant, the X-only zero-variance rule removes all of them, and the model
reduces to the benchmark exactly — half the primary panel carries no commodity signal at all. Only
IND-04 receives the full 10 predictors; five industries receive 5.

Two count deviations from the brief are reported rather than smoothed: h=3 feature-usable is 216 and
384 (not 228 and 396) because the operational h=3 benchmark window reaches 2021-12 at *u* = 2022-03,
before B3's stress series begins. That is a series-start boundary, kept distinct from a
release-timing violation, and the row is excluded rather than imputed.

Sensitivities are reported separately and cannot change the primary status: timing (lag-1) 17.0253 /
17.3063, structural (total requirements) 18.0460 / 18.1751. All 15 origins passed the **day-level**
commodity publication check against C1.5's archived issue dates.

The locked final test remains unopened.

Detail: `docs/d4_operational_model_protocol.md`, `docs/d4_operational_model_results.md`.

## Structural price-stage alignment (Task C5 — implemented, structural audit)

D4 found direct Brent/Rubber exposure structurally zero for 6 of 12 industries. C5 asked the
official 2015 NESDC input-output table *why*, and the answer is not that the dependence is absent.

**Brent direct exposure is zero for 10 of 12 industries** (only IND-04 petroleum and IND-05
chemicals buy crude across the factory gate), yet indirect exposure runs **7–17%**. Decomposing by
the first intermediate sector purchased, using `T = A + TA`:

```
direct(c,j)         = A[c,j]
indirect_via(c,k,j) = T[c,k] * A[k,j]
total(c,j)          = A[c,j] + sum_k T[c,k] * A[k,j] = T[c,j]
```

the mediators are **Electricity (135)**, **Petroleum refineries (093)** and **Petrochemical products
(086)** — IND-06 reaches crude 54.9% through petrochemicals, IND-07 21.5% through refineries, and
electricity mediates in nearly every industry. Industries buy **refined fuel and power, not crude**.

Identity residual **6.66e-16**; worst reconciliation against C3's published direct and total values
**2.78e-17**, both far inside the 1e-12 tolerance. Orientation is pinned against the source flows
(`A = Z/X`) rather than by the identity, which a transposed matrix would also satisfy. 18 of 48
pairs are direct-zero; 11 retain material indirect exposure at the preregistered 0.01 threshold.

**Consequence for the existing features:** Brent is `stage_misaligned` for all 10 direct-zero
industries — a crude price standing in for a refined-fuel and electricity cost. Aluminum and copper
remain `broad_proxy_with_caution`; they share I/O sector 107, so their exposures are still never
summed. Nothing about C3's coefficients, C3-R1's eligibility or C4's variants changed, and
`direct_exposure` remains the registered primary exposure — total requirement was **not** promoted
because D4 went badly.

**Source audit.** Four official families were probed. Only **EPPO's petroleum price structure**
could be verified end-to-end: its `EX-REFIN.` column is an **ex-refinery producer price in
BAHT/LITRE**, reported separately from excise tax, municipal tax, oil fund and wholesale — exactly
the stage sector 093 represents. MOC's PPI returned 403 on every entry point and ERC timed out; both
are recorded as blocked, **not** as absent, and are ineligible only because an unverifiable
definition cannot satisfy the gate. BOT's exchange rate is audited as an import-price transmission
factor and is explicitly **not** an I/O commodity sector price.

`EPPO_PETROLEUM` is the single family recommended for C6, passing all ten preregistered criteria.
Its coverage limitation is explicit and unresolved: only recent daily files are exposed, and because
2018 retail files are served from a 2026 upload folder, folder-date inference cannot establish
archive depth. Resolving that is C6's first job. The recommendation is ingestion approval only —
`feature_semantics_approved: false`, `model_feature_approved: false`.

Detail: `docs/c5_structural_path_audit.md`, `docs/c5_price_stage_source_audit.md`,
`docs/c5_source_recommendation.md`.

## EPPO ex-refinery archive audit (Task C6 — implemented, source audit)

C5 selected EPPO for auditing. C6 asked whether a reproducible, availability-safe historical source
actually exists behind it, and the two halves of that question came back with opposite answers.

**The archive is deep and complete.** The WordPress REST media index — an official EPPO mechanism —
yielded **5,233 price-structure workbooks spanning 2002-02-03 to 2026-08-28**, walked to a bounded
terminal condition (`api_termination_400_at_page_54`). Coverage is **65 of 65 months** for the
2021-01…2026-05 transformation-parity window and **53 of 53** for the 2022-01…2026-05 operational
window, with **no missing months** in either. The weekday profile (Mon–Fri 259–281 each, Sat/Sun 12
each) indicates working-day publication; no official schedule document was located, so weekday gaps
are recorded `schedule_unresolved` rather than counted as missing issues.

**Release timing is not established.** Every WordPress upload timestamp falls in 2026 — the site
migration window. A migration timestamp records re-hosting, not first publication, exactly as D2
found on the OIE i-Index. Independent third-party captures corroborate only **43 archive dates**
(2020-06/07, 2022-06–08, 2026-08), and none of them coincide with the 254 validated documents in the
audited months. Point-in-time is therefore **`not_supported`** for the audited subset, and the
outcome is **`values_retrievable_timing_unresolved`**.

**Document validation.** 256 documents retrieved across 12 complete months, **254 valid**. Two were
rejected as `wrong_date_attachment` — the workbook's internal date disagreed with the archive item by
one day, which is precisely the defect filename-trust would have missed. All five duplicate-content
groups are same-date duplicates (`duplicate_document`); none span incompatible dates.

**Semantic regimes.** Two layout regimes: `.xls` (2021-01…2023-01, sheet `โครงสร้างราคา`, tax column
`TAX`) and `.xlsx` (2023-07 onward, sheet `Oil Price Structure`, tax column `EXCISE TAX`). Product
definitions move too: **2024-01 publishes only H-DIESEL B7/B10/B20 and no plain H-DIESEL**, so the
HSD series has a real gap there — filling it with a blend would be exactly the prohibited
substitution. `FO 600 (1) 2%S` and `FO 1500 (2) 2%S` carry identical labels across both regimes.

**Revisions.** Classified only on `(series_id, effective_date, semantic_regime_id)`: 707
`single_vintage_only`, 15 `duplicate_document`, and **zero `same_date_revised_value`**. No ordinary
daily price movement was miscounted as a revision.

**Eligibility is per transformation.** History depth supports level, 1m, 3m, volatility and 12m
changes — the archive reaches 2002, far behind the 2021-01 prehistory a 12-month change needs. But
every one remains gated on timing, which is unverified, and
`monthly_aggregation_contract_approved: false`. A partial audit table of **722 unique observations**
exists; it is labelled partial and is not a feature table.
`feature_semantics_approved: false`, `model_feature_approved: false`.

Detail: `docs/c6_eppo_archive_audit.md`, `docs/c6_eppo_aggregation_decision.md`.

## EPPO latest-vintage use decision (Task C6.5 — implemented, policy decision)

C6 left two facts pulling in opposite directions: the ex-refinery values are retrievable with
complete monthly presence, and their historical release timing cannot be reconstructed from the
sources inspected. C6.5 turns that into an explicit decision rather than letting it drift.

**Decision: `proceed_exploratory_release_lag_aware_latest_vintage`.** EPPO may be used on the same
footing D3 already put the MPI target — release-lag-aware, latest-vintage, exploratory. All 21 C6
invariants were reproduced from production artifacts before the decision was recorded.

**Measured lag versus policy lag, kept apart.** No publication delay was measured, so
`minimum_verified_publication_lag_months` is **null** and stays null. The project imposes
`operational_policy_lag_months: 2` with `operational_lag_is_measured: false` and
`operational_lag_basis: conservative_project_policy`. At issue month *t* an EPPO observation may
refer at latest to reference month **t-2**; lag 0 and lag 1 are both rejected. This is an assumption
the project makes about itself, not an observation about EPPO.

**Availability fields never collapse.** `source_available_as_of` means the source is *evidenced* to
have been public by that date and stays **null** for every historical observation;
`policy_available_month` carries `reference_month + 2`; `availability_basis` names which is which.
Writing a policy date into `source_available_as_of` raises.

**The 43 captures prove less than they appear to.** Re-audited, all 43 classify as
`capture_identity_unverified`: the CDX index was read but the archived bytes were never fetched and
document identity never validated, so **zero** usable upper bounds remain. Even a validated capture
would give an upper bound, never a first-release date. Delay statistics are computed from upper
bounds only, and the minimum verified lag is not derived from them.

**Evidence-boundary corrections.** C6 wording that outran its evidence is superseded:
`legacy_archive_status: tested_legacy_urls_no_longer_expose_original_archive` (not "the archive no
longer exists"), and `historical_timing_status: not_reconstructable_from_sources_inspected_in_c6`
(not "can never be verified"). **Absence from the inspected mechanisms is not proof that no
historical publication evidence exists anywhere.**

**Presence is not ingestion.** Five states are now tracked separately:
`monthly_document_presence_verified: true`, `complete_daily_inventory_discovered: true`,
`complete_daily_documents_downloaded: false`, `complete_daily_documents_validated: false`,
`monthly_aggregation_contract_approved: false`. The 254 validated documents are an audit sample
spanning all required months, **not** a daily ingestion of the 1,315 discovered document-days, and
the 722-row table remains a partial audit table.

**Series decisions.** `FO 600 (1) 2%S` and `FO 1500 (2) 2%S` are eligible for C7 full-archive
ingestion (`stable_in_audited_window`). **H-DIESEL is conditional**: 22 days in January 2024 publish
only blend definitions, so the gap stands — `silent_blend_substitution_permitted: false`,
`imputation_permitted: false`.

**Transformation status is now two fields, not one.** Every candidate has
`historical_depth_sufficient: true` but `source_ready_for_transformation: false`, blocked on daily
ingestion, the aggregation contract and availability enforcement. No transformation was created.

**C7 boundary.** `c7_full_archive_ingestion_authorized: true`,
`c7_monthly_source_aggregation_authorized: conditional`,
`c7_predictive_feature_creation_authorized: false`, `c7_target_join_authorized: false`,
`c7_modeling_authorized: false`. `eligible_for_confirmatory_claims: false`,
`eligible_for_locked_test: false`.

Detail: `docs/c6_5_eppo_latest_vintage_decision.md`.

## Full EPPO archive ingestion and monthly source table (Task C7 — implemented, source ingestion)

C6 sampled the archive and C6.5 decided how it may be used. C7 retrieved the rest of it: every
officially discovered document-day in 2021-01-01 … 2026-05-31, validated against its own content,
then aggregated to a monthly source table under the C6.5 policy. All 21 C6/C6.5 invariants were
reproduced from production artifacts before anything was computed; the run stops if one fails.

**The denominator stays honest.** 1,315 distinct document-days were discovered across 1,336 media
records (19 days carry more than one attachment). 1,336 retrieval attempts produced 1,333 successes,
1,331 content-valid documents and **1,310 valid canonical document-days**. Five discovered
document-days remain unresolved and are reported as such, never as absent. A discovered day is never
reported as a validated day.

**Three unretrievable inventory items.** The official media records for 2026-04-17, 2026-04-18 and
2026-04-19 exist and return HTTP 200 from the REST API with a declared file size, but the files at
their own `source_url` return 404 on every attempt. That is an *actual unresolved inventory item*,
not a schedule gap, and it blocks approval for 2026-04.

**Two wrong-date attachments, neither reassigned.** `pt-price-st-2022-12-5.xls` contains a document
dated 2022-12-06 and `pt-price-st-2025-1-25.xlsx` contains one dated 2025-01-24. Each is rejected for
its listing date and **not** moved to its internal date. Neither date is covered by any separately
valid official document, so both days stay unresolved.

**Layouts were discovered, not assumed.** Every sheet of every document was inspected and every price
stage resolved by column label; there is no positional fallback, and a stage collision raises. The
February–June 2023 interval C6 never sampled resolves cleanly into the two known regimes, with the
container change falling between **2023-06-02** (last `.xls`) and **2023-06-06** (first `.xlsx`). One
further document — 2024-03-07 — carries a third signature (`.xlsx` container, Thai sheet name,
`EXCISE TAX` column) and is registered as a newly observed regime because an actual document supports
it. Tax-column renaming was not the only layout change: the workbook also grows from one sheet to
three from 2024-07-23.

**Two semantic findings the sample could not show.**

* **Ordinary `H-DIESEL` is absent for 305 consecutive document-days, 2023-09-18 to 2024-12-17.** C6
  reported it absent for 22 audited days in January 2024; every C6-sampled day inside the absence was
  in that month, so C6 was correct about what it observed and understated the extent. Blend
  definitions (`B7`, `B10`, `B20`) are published throughout and **none is substituted**. Fourteen
  H-DIESEL months carry a null value with `semantic_definition_gap`, and the two months that straddle
  the boundary (2023-09, 2024-12) are also null rather than a mean over the surviving days.
* **Both fuel-oil labels drop their ordinal index for 66 document-days, 2024-07-23 to 2024-10-28**
  (`FO 600 2%S`, `FO 1500 2%S`), never on the same day as the ordinal label. The documents are parsed
  and kept, the rows are flagged `unconfirmed_label_variant`, and all eight affected product-months
  are blocked with `unit_or_definition_break`. Whether the two labels name the same series is a
  semantic equivalence decision, and an ingestion task may surface it but not settle it.

**The monthly rule.** `arithmetic_mean_of_validated_observed_official_document_days`, version
`c7_v1`, preregistered before retrieval and selected from source semantics, archive completeness and
deterministic reproducibility — never from predictive performance, of which none exists here. Each
distinct valid official document-day counts once. Nothing is synthesised for a weekend, no unchanged
price is carried forward, no value is duration-weighted, and no partial issue month is used. The
number is the **mean ex-refinery price across validated official EPPO document-days observed in the
completed reference month** — not a calendar-day mean, not a trading-day mean, not a transaction
price, not a point-in-time value.

**Approval is a gate and it failed.** 162 of 195 product-months are `approved`; 16 are
`semantic_definition_gap`, 8 `unit_or_definition_break`, 6 `unresolved_document_identity` and 3
`unresolved_document_retrieval`. Because 2022-12, 2025-01, 2026-04 and 2024-07…2024-10 do not pass for
the fuel oils, **`monthly_aggregation_contract_approved` is `false`**. It is reported as a failure
rather than forced, and no H-DIESEL value was fabricated to unblock anything.

**Availability is executed, not restated.** `source_available_as_of` is null in all 195 monthly rows
and all 3,625 daily rows; `policy_available_month` is `reference_month + 2` in every row;
`availability_basis` stays `conservative_policy_not_historical_measurement`. The daily table names its
policy column `candidate_monthly_policy_available_month` because the policy is defined for a monthly
observation and reusing the monthly name at daily granularity would read as a measured date.
`select_monthly_source_available_at_issue` returns only rows with
`policy_available_month <= issue_month`; at issue 2024-01 the latest permitted reference month is
2023-11, at 2025-03 it is 2025-01, at 2026-05 it is 2026-03.

**Nothing predictive was built.** No log change, percentage change, lagged price, realized volatility,
z-score, shock flag, exposure interaction, correlation, mutual information, Granger test, feature
importance or predictive metric was calculated. No MPI target was joined, no model trained, no locked
test touched. `source_ready_for_transformation` is `false` for all three series.

Detail: `docs/c7_eppo_full_archive_audit.md`, `docs/c7_eppo_monthly_source_decision.md`.

## EPPO product semantics and aggregation closure (Task C7.5 — implemented, semantic decision)

C7 delivered the archive and left four blockers. C7.5 resolves what can be resolved on evidence and
records the rest as unresolved. All 24 C7 invariants were reproduced from production artifacts before
anything was decided; C7's raw documents, exact displayed labels, canonical daily values and document
checksums are untouched, and everything here is a layer above them.

**The fuel-oil label question is answered by the publisher's own bilingual sheet.** From 2024-07-23
the official workbook carries a Thai companion sheet whose product rows are *formula-bound* to the
English sheet — the Thai row 14 price cell literally reads `='Oil Price Structure'!C14`. Across all
471 three-sheet documents that Thai name is byte-identical, `น้ำมันเตา 600 กำมะถันไม่เกิน 2%`
("fuel oil 600, sulphur not exceeding 2%"), and it is bound to `FO 600 (1) 2%S` in 405 documents and
to `FO 600  2%S` in the other 66. One product name, no ordinal, both English forms. That is a
source-controlled data dictionary inside the official document, so the gate's direct-evidence
requirement is met by evidence rather than by inference.

Everything else is corroboration and is labelled as such: unit `UNIT: BAHT/LITRE` and stage
`EX-REFIN.` in all 745 documents, product number and `2%S` unchanged, the same row neighbours, the
same excise/municipal/fund treatment, the two forms never co-occurring in any valid document, and the
ordinal-free form occupying exactly 2024-07-23…2024-10-28 with the ordinal form resuming on
2024-10-29. **Numeric continuity was recorded and is explicitly not load-bearing**
(`numeric_evidence_load_bearing: false`), because a different product at the same table position
would look just as continuous.

**Decision: `equivalence_established`** for both grades, rule `fo_ordinal_index_dropped_v1`. The raw
displayed label is never overwritten — `FO 600  2%S` stays in the row and `canonical_product_id`
sits beside it. What `(1)` and `(2)` actually *mean* is a different question and remains
**`not_established_from_inspected_sources`**: no workbook in the 1,331-document archive carries a
note, comment, defined name, hidden row or glossary entry explaining them (the `คำอธิบาย` glossary
explains the eleven *columns*), and no EPPO policy document naming them was found through the REST
index, the official pages or the official oil API. That is a limit of the sources inspected, not
proof that no explanation exists — and the decision does not depend on knowing.

**Two of the five unresolved document-days were recovered, on official evidence independent of the
filename.** The parent post of `pt-price-st-2022-12-5.xls` is titled
`โครงสร้างราคาขายปลีกน้ำมัน 6 ธันวาคม 2565` and was published `2022-12-06` — both agreeing with the
document's own internal date of 2022-12-06, and disagreeing with the filename. The same pattern holds
for `pt-price-st-2025-1-25.xlsx`, whose parent post is dated and titled 2025-01-24. Two independent
official sources plus the document's own content is a documented recovery; the filename alone would
have been the silent reassignment C7 refused, and `classify_recovery` **raises** the weaker case as
`wrong_date_attachment_unresolved`. December 2022 and January 2025 are now complete.

**The three April 2026 days were not recovered.** Their media records still return HTTP 200 from the
REST API with a declared file size, but the files 404 on the production host *and* on the
`eppo.d-gis.com` host recorded in their own `guid`; the parent post lists them; no alternate media
record exists; the attachment pages are 404. Recorded as `official_attachment_unretrievable` with the
required wording `official_document_not_recovered_from_inspected_channels` — never as a claim that
the documents never existed.

**H-DIESEL is excluded, and the exclusion says what it is about.** The ordinary label is absent for
305 consecutive document-days, 2023-09-18 to 2024-12-17, spanning sixteen reference months.
`eligible_for_c8_primary_transformation: false`, `eligible_for_c8_sensitivity_transformation: false`,
`status: not_ready_long_semantic_definition_gap`. This is not a finding that the documents or the
blend products are invalid — both are valid — only that ordinary H-DIESEL cannot support a
continuous, consistently defined source series. Every observation and all blend provenance are kept.

**One approval boolean became three.** C7's `monthly_aggregation_contract_approved` was answering
three questions at once, so it reported a sound method as a failed one. They are now separate:
`aggregation_method_semantics_approved` (the rule is valid and reproducible — **true** for all three
series), `full_requested_window_coverage_complete` (**false** for all three, because April 2026 and
the H-DIESEL gap remain), and `series_ready_for_transformation_with_explicit_gaps` (**true** for both
fuel oils, **false** for H-DIESEL). `assert_method_approval_is_not_coverage` raises on any wording
that reads the first as the second.

Every month now carries **two values**: a `monthly_value_strict`, null unless the month's entire
discovered inventory validated and the only value a transformation may read, and a
`monthly_value_descriptive`, which may summarise the days that do exist and is always labelled
incomplete. `assert_transformation_input_permitted` raises if a descriptive value is offered as an
input. After the decision: **168 `approved_complete_inventory`, 8 `approved_with_source_label_variant`,
16 `semantic_definition_gap` and 3 `known_document_gap`** across 195 product-months.

**Coverage is reported in two views.** The full source audit window is 2021-01…2026-05. The maximum
preregistered issue origin is **2026-04** (locked test, h=1), so under the two-month policy lag the
maximum source reference month any existing key requires is **2026-02** — derived from issue-month
ranges and the lag alone, with no target outcome read. April 2026 therefore reaches **no currently
preregistered issue origin** and is documented anyway. The H-DIESEL gap months 2023-11…2024-12 reach
development origins directly, and with twelve months of prehistory they reach purge and locked-test
origins too.

**The two fuel oils stay apart.** Both map to I/O sector 093 and the shared coefficient cannot
separate them, so `additive_aggregation_allowed`, `simple_average_allowed`,
`automatic_composite_index_allowed` and `simultaneous_model_entry_approved` are all false and
`assert_no_additive_fuel_oil_aggregate` raises on any attempt to combine them. They are preserved as
separate, mutually exclusive channel variants, and choosing between them by target performance is
prohibited.

C8 is authorized for FO 600 and FO 1500 source-level transformations only, with gaps propagating.
`c8_hsd_transformation_authorized`, `c8_industry_conditioning_authorized`,
`c8_target_join_authorized`, `c8_modeling_authorized`, `c8_imputation_authorized`,
`c8_outcome_based_channel_selection_authorized` and
`c8_simultaneous_additive_fuel_oil_use_authorized` are all **false**.

Detail: `docs/c7_5_eppo_semantic_decision.md`.

## EPPO fuel-oil source transformations (Task C8 — implemented, source-level only)

C7.5 approved FO 600 and FO 1500 for transformation *with explicit gaps*. C8 builds them, and the
qualifier is the design: a transformation is numeric only when every month its formula declares is
present and approved, and otherwise it is null with a status naming which kind of absence it was. All
24 C7.5 invariants were reproduced from production artifacts before anything was computed.

**The formulas are C2's, imported rather than re-implemented.** `log_change_pct`,
`realized_volatility_pct` and the preregistered `FEATURE_DEFINITIONS` all come from
`features.commodity_features`, and `assert_c2_formula_compatibility` re-checks the input-lag tuples
so a change on either side fails loudly instead of drifting. Natural logarithm, scaled by 100,
volatility with `ddof=0`. Realized volatility declares **four** price levels, not three, because
`r_{m-2}` is itself a change from `m-3`.

**Matching formulas are not matching evidence, and the audit says so separately.** C2's World Bank
inputs are archived first-release values with a *measured* publication lag and full point-in-time
support; C8's EPPO inputs are latest-vintage values under a two-month *policy* lag that was never
measured and support no point-in-time claim. `formula_compatible_with_c2: true` and
`source_timing_contract_differs_from_c2: true` are both recorded, and
`equivalent_timing_quality_implied: false`.

**The grid is complete by construction: 2 channels x 65 months x 5 transformations = 650 rows.** No
cell is dropped for being undefined, because an omitted row and a null row are indistinguishable
downstream only when the null row is missing. **598 rows carry a finite value and 52 are null.** Those
counts were preregistered before the run *and* are derived independently from the declared lags at
run time; the runner stops if the two disagree, and they matched exactly — 64/62/61/52/60 finite per
series for price level, 1m, 3m, 12m and volatility.

**Missingness has a total precedence order**, so two runs cannot disagree about which kind of absence
a cell has: unauthorized series, unit mismatch, insufficient prehistory, current-month source gap,
input-window source gap, non-positive value, then numeric. Of the 52 nulls, **38 are
`insufficient_feature_history`** (a window reaching before 2021-01 — a property of the window, never
labelled as an archive gap), **10 are `current_month_source_gap`** (every transformation at 2026-04),
and **4 are `input_window_source_gap`** (the one-month change and the volatility at 2026-05, each
missing 2026-04). Nothing is imputed, interpolated, forward-filled, back-filled, clipped, winsorized
or borrowed from the other fuel oil.

**Availability is computed from the window, not from the reference month.**
`policy_available_month` is the maximum policy month over every declared input, and the equality with
`reference_month + 2` is *verified on all 650 rows* rather than hard-coded — a formula that ever
reached forward would fail the check instead of inheriting a stamp that is too early.
`source_available_as_of` stays null everywhere: EPPO release timing was never measured and the policy
month is not a release date. The selector returns only numeric rows, for exactly one channel, and
refuses a request naming both; at issue 2024-01 the latest reference month is 2023-11, at 2025-03 it
is 2025-01, at 2026-04 it is 2026-02.

**Issue-key coverage was audited from preregistered issue-month ranges alone** — no target value,
prediction or metric was read. All 15 development, 3 purge and 10 locked-test issue months have every
transformation available at their latest permitted reference month, for both channels. **The 2026-04
gap is reachable by no registered issue key** (the maximum issue month is 2026-04 and the lag is 2),
and it is kept and reported anyway rather than removed for being operationally unused.

**Every row carries lineage, including the 52 nulls.** A C8 digest hashes the specification as well as
the inputs — transformation, formula version, channel, reference month, unit, availability-policy
version, input ordering, output value or null status, missingness reason, and the expected, available
and missing input months — so a null row still explains itself and two nulls with different causes do
not collide. All 650 digests are distinct.

**The two fuel oils stay apart.** Both read I/O sector 093, so `additive_aggregation_allowed`,
`simple_average_allowed`, `automatic_composite_index_allowed` and
`simultaneous_model_entry_approved` are all false, and `assert_single_fuel_oil_channel` raises on any
attempt to sum, average, index or request them together. Keeping both in one audit table is safe only
because the channel ID is part of the key.

Both channels are `source_transformations_ready_for_structural_conditioning: true`. That is not model
approval: `industry_conditioned_features_created`, `feature_semantics_approved` and
`model_feature_approved` are all false, and no exposure coefficient, MPI target, model or locked-test
outcome was read.

Detail: `docs/c8_eppo_transformation_protocol.md`, `docs/c8_eppo_transformation_audit.md`.

## Sector-093 exposure and industry-conditioned fuel oil (Task C9 — implemented, structural)

C3 measured exposure to sector **031**, crude, and C5 explained the ten direct-zeros it produced:
factories buy refined fuel and power, not crude. C9 derives exposure to sector **093**, *Petroleum
refineries*, from the same official table, the same column orientation and the same gross-output
weights, then conditions the C8 fuel-oil transformations on it.

**The task runs in two phases and the boundary is enforced, not promised.** Phase A reads the NESDC
matrix, the sector definitions, the C3 crosswalk and C5's structural findings — and nothing else.
`assert_no_numeric_source_values` raises if a C8 price, a monthly value or a conditioned value reaches
a Phase-A function, and the Phase-A module imports no `features` module at all. The decision table is
then hashed, written, re-read from disk and re-verified **before** the C8 parquet is opened, and
verified again **after** conditioning. Frozen digest:
`d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703`.

**Exposure is derived twice, by different routes.** The output-weighted mean of the component-sector
coefficients and the exact ratio of summed flows to summed output are algebraically identical, so a
disagreement means a weight, a filter or the orientation is wrong. Worst observed residual across the
twelve industries: **1.39e-17**, far inside the 1e-12 requirement. Sector 031 is refused by name,
total requirement is never computed, and no exposure is normalised across industries.

**Every industry buys refinery products.** Direct sector-093 exposure runs from **0.00475** (IND-12)
to **0.06416** (IND-05), median **0.00993**, with **zero** observed-zero exposures and none
unresolved — the exact opposite of the sector-031 picture, and the clearest confirmation of C5's
finding. The heaviest are chemicals (IND-05, 0.0642, four fifths of it through petrochemicals),
non-metallic minerals (IND-07, 0.0346, led by cement and glass) and metals (IND-08, 0.0269, led by
iron and steel).

**Sector 093 is a basket, and the official definition says so.** NESDC's own text lists the products
as *gasoline, jet oil, LPG, asphalt, paraffin, sulfur, kerosene, diesel and fuel oil* — nine, of which
fuel oil is one. A positive coefficient therefore proves purchase from the refinery-products sector
and **not** purchase of FO 600 or FO 1500; `assert_not_inferred_from_coefficient` raises on that
inference. The 179-sector table does not split refinery products by type, and no source Phase A is
permitted to read identifies which product an industry buys, so **all twelve industries are
`broad_proxy_use_with_caution` at `medium` confidence** — never `fit_for_structural_use`, never
`high`. That absence is a limit of the permitted sources, not proof that no such evidence exists.

**Direction is structural and IND-04 is not forced.** Eleven industries buy refinery products without
producing them: `cost_pressure`, multiplier **+1**. **IND-04 contains sector 093 itself**, so a higher
refinery-product price is simultaneously its revenue and its input cost — `mixed_or_ambiguous` with a
**null** multiplier, ineligible for the default conditioned feature, and `assert_direction_not_forced`
raises on any attempt to give it +1. Realized volatility carries a separate reading throughout,
`disruption_magnitude_nonnegative`, so the sign of a level is never conflated with the size of a
wobble.

**The price stage and the valuation basis do not match, and the audit says so.** EPPO measures the
ex-refinery stage — before excise tax, municipal tax, the oil and conservation funds, wholesale, VAT
and margins — while the I/O coefficient is in purchasers' prices, import-inclusive. The product is
recorded as `partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price`,
`structural_interaction_only: true`, `monetary_cost_measure: false`, and
`assert_valuation_claim_permitted` raises on any description as baht of cost per unit of output, an
elasticity, a pass-through rate or a causal effect.

**The conditioned grid is complete: 2 variants x 12 industries x 65 months x 5 transformations =
7,800 rows**, and none is dropped for being ineligible, null or zero. Counts were preregistered from
the frozen eligibility before any value loaded and reconciled exactly: **6,578** numeric
(598 x 11 eligible industries), **572** source gaps (52 x 11) and **650** ineligible (650 x 1). The
status precedence keeps three absences apart — structural ineligibility first, then a missing source,
then a zero exposure, then a value — and `assert_null_not_converted_to_zero` raises on the two
collapses that would turn "we do not know" into "zero".

**Availability is the later of the two chains.** `conditioned_policy_available_month =
max(source policy month, 2020-03)`; the structural month is the I/O table's *publication*, never its
2015 reference year, and never a download timestamp. The source policy dominates in all 7,800 rows.
`source_available_as_of` stays null throughout, `latest_vintage_used` true, `point_in_time_supported`
false, `fully_real_time_backtest` false.

**Lineage hashes both chains.** Every row — including all 1,222 null ones — carries the C8
transformation digest and its declared input window, the C7.5 semantic digest, the sector-093 row, the
NESDC workbook checksum, the crosswalk and gross-output weights, the exposure arithmetic, the proxy
and direction decisions, the frozen Phase-A digest and the structural availability evidence. All 7,800
digests are distinct.

**The development snapshot is 1,800 cells** (15 issue months x 2 variants x 12 industries x 5
transformations), taking the latest reference month permitted by the two-month lag. 1,650 are numeric
and 150 are `masked_ineligible` (IND-04); none is rejected for a source null, because every
development reference month 2023-11…2025-01 has complete source data. Purge and locked coverage is
reported from **issue-key ranges only** and nothing is materialised for them.

**The two variants never meet.** They carry the *same* sector-093 vector, which is exactly why summing
or averaging them would double-count one coefficient while looking like two measurements.
`assert_no_fuel_oil_combination` raises on any sum, mean, composite index, PCA or simultaneous
request, including one framed as picking the better-performing channel.

`industry_conditioned_features_created: true`; `feature_semantics_approved`,
`model_feature_approved`, `target_join_authorized`, `modeling_authorized` and
`locked_test_evaluation_authorized` all remain **false**. A structurally conditioned feature is not
automatically predictive.

Detail: `docs/c9_sector093_exposure_decision.md`, `docs/c9_fuel_oil_conditioning_audit.md`.

## Development-only design-matrix identifiability audit (Task C10 — implemented, structural)

C9 produced 165 eligible rows per fuel-oil variant over the development window. It is tempting to read
that as 165 observations. C10 exists to establish, arithmetically and **before any target is joined**,
what those rows actually contain.

**The contract is frozen before the values load.** Rank tolerance `1e-10`, near-zero variance
threshold `1e-12`, reconstruction and standardisation tolerances `1e-9`, standardisation `ddof = 0`,
the expected dimensions, the missingness precedence and the list of permitted statistics were written
into `configs/fuel_oil_development_matrix.yaml` and hashed to `1c88cdd7…` before a single C9 feature
value was read. The runner re-asserts that digest immediately before the load and again after the
diagnostics, so a tolerance chosen to fit an observed singular value raises instead of passing.

**The identity.** C9's conditioning is `D[v,g] = E[g] · X[v]` — one 15 x 5 source-time matrix `X[v]`
per variant, multiplied by industry `g`'s positive sector-093 exposure scalar. Three consequences
follow, and each is verified numerically rather than argued:

1. **Cross-sectional rank one.** The eligible cross-section at a single issue month is the outer
   product `E x[v,t]ᵀ`, so its rank is one. Observed: rank 1 at all 15 issue months, both variants. A
   rank above one would mean a conditioning, exposure, alignment or pivot error.
2. **Rank equality.** The source-time matrix, every industry-specific matrix and the stacked eligible
   panel all have rank **5**. The 165-row panel adds rank because it repeats, not because it informs.
3. **Standardisation invariance.** For `E > 0`, `standardize(E·X) == standardize(X)` column-wise,
   because the scalar cancels in both the mean and the standard deviation. Observed residual 4.39e-15
   (fo600) and 2.66e-15 (fo1500) against a 1e-9 tolerance, and 11 distinct raw designs collapse to
   **one** equivalence class once normalised and once standardised.

Together: **the industry conditioning contributes cross-industry scale and no new temporal shape.**
That is a property of the design matrix, established without reading any target. It is not a statement
about what a model would do, and `assert_no_performance_claim` raises on wording that turns it into
one.

**The primary diagnostic input is the 15 x 5 source-time matrix, never the 165-row panel.**
`assert_primary_input_is_source_time` raises if a rank or correlation routine is handed the stacked
panel, and `assert_no_independence_claim` raises on wording that presents those rows as independent.
Adjacent transformations overlap in time anyway — a 3-month change and a 12-month change share
endpoints, and a 3-month volatility reads four consecutive price levels — so
`temporal_independence_claim_permitted` is false as well.

**Degeneracy is a finding, not a licence to edit the design.** No exact-zero and no near-zero variance
column in either variant, no exact algebraic duplicate, and all eleven eligible industries agree on the
classification. Exact-zero *observations* are counted separately from constant *columns*, because a
column of zeros and a column that never moves are different facts. Pairwise Pearson and Spearman
correlations are descriptive only: no significance test is reported, no channel is chosen and
`assert_no_feature_removal` raises if a transformation is dropped on a diagnostic.

**A preregistered expectation failed and was reported, not relaxed.** The config expected one distinct
standardised fingerprint per variant; fo600 gave 11. The fingerprint rounds to 13 *significant* digits,
so a standardised value near zero is resolved below double precision — two `price_level` cells split
matrices that agree to 4e-15. The decision rule is the frozen *absolute* tolerance, which puts all
eleven industries in one class. The fingerprint count is published unchanged beside it.

**IND-04 stays.** Its direction is unresolved, not zero and not absent. Dropping its 15 rows per
variant would make the table rectangular by deleting the one row that records a structural limitation;
zero-filling them would assert an exposure nobody measured; dividing them by its exposure would
reconstruct a design that does not exist. All three are refused by name.

**The two variants are never one matrix.** They share the sector-093 exposure vector, so a ten-column
table holding both would present one coefficient as two independent measurements. They are reported
side by side and no preferred variant is produced.

Lineage was re-derived independently for all **1,800** development cells, each hashing both provenance
branches and the variant/issue-month selection rule; masked cells included. Availability was checked
against the recorded fields rather than by positional shifting: 0 lag-2 violations, 0 policy
violations.

`development_matrix_assembled: true`. `predictive_utility_assessed`, `channel_selected`,
`target_joined`, `model_trained`, `model_feature_approved`, `locked_test_accessed`,
`target_join_authorized` and `modeling_authorized` all remain **false**. A full-rank design matrix is
not modeling readiness; approval is a separate decision and has not been taken.

Detail: `docs/c10_design_matrix_protocol.md`, `docs/c10_design_matrix_audit.md`.

## Fuel-oil modeling-architecture decision (Task C11 — implemented, structural)

C10 established that the industry conditioning contributes cross-industry scale and no new temporal
shape. C11 answers the question that follows: given that, **how** should a fuel-oil correction enter a
model — decided on the estimand and the identification structure, before any target is joined.

**The criteria are frozen before the first candidate matrix exists.** The estimand, the candidate set,
the nine mandatory gates, the preprocessing contract, the rank requirements and the decision ordering
were hashed to `0f815135…` and re-asserted before the designs were built and again after the audit.
`expected_selection` is recorded in the config and, immediately beside it,
`expectation_overrides_a_failed_gate: false` — a failed gate selects nothing and names the blocker.

**The estimand is a predictive interaction, not an effect.** The incremental forecast correction
associated with a common national ex-refinery fuel-oil signal, with the correction amplitude allowed to
vary across industries according to frozen direct purchases from NESDC sector 093. The I/O coefficient
is a structural proxy taken as given, in purchasers' prices and import-inclusive, while EPPO measures
the ex-refinery stage — so the product has no currency reading and
`assert_predictive_not_causal` raises on "causal effect", "elasticity", "pass-through rate" and
"monetary cost".

**Candidate B is rejected on an identity, not a comparison.** Fitting `E[g]·x[t]` separately per
industry spans exactly the same column space as fitting `x[t]`: the orthogonal projectors agree to
6.5e-16 across all eleven eligible industries, and `gamma[g,f] = beta[g,f] / E[g]` recovers one from
the other. It is the same design in different coordinates, so no data can distinguish them.
`separate_conditioned_model_is_distinct_architecture: false`.

**Candidate C differs in kind, not in scale.** Within one industry `E[g]` is a constant. In a pooled
panel `E[g]·x[t]` varies across industry *and* time, so the centred interaction is not proportional to
the main effect and can carry a constrained cross-industry slope pattern. Verified per variant on a
feature-only 165 × 21 panel: source block rank **5**, interaction block rank **5**, combined **10**,
full design rank **21 of 21 columns**, no exact duplicate columns.

**Three ways to destroy that, all constructed and all refused.** Replacing exposure with a constant
centres it to exactly zero and makes the interaction block rank **0** — a design that still fits and
identifies nothing. Adding a global intercept to eleven industry indicators is rank-deficient by
exactly one, **21 of 22 columns**, a shape that looks correct in every summary. Standardising the
interaction *inside* each industry maps `e[g]·x̃` to `sign(e[g])·x̃`, collapsing that industry's
combined block from rank 10 to **5** and reducing eleven exposure-proportional interaction blocks to
**two** sign groups, so θ could be identified only up to a two-group split.

**A preregistered expectation failed and is reported rather than relaxed.** The config expected the
per-industry-standardisation counterfactual to drop the *stacked* rank from 10 to 5; the stacked rank
stayed 10, because the centred exposures carry both signs and `+x̃` and `−x̃` span two directions. The
preregistered number was the wrong measurement of a real collapse. It was not rewritten; the correct
measurements — per-industry rank 5, distinct interaction blocks 11 → 2, sign identity residual 4.4e-16
— are reported beside it, and the gate that had wrongly depended on the counterfactual was corrected
with `gate_implementation_corrected_after_observation: true` recorded in the decision artifact.

**Accounting stays honest about what 165 rows are.** Fifteen unique issue months and fifteen
issue-month clusters. Cross-sectional rows help identify exposure heterogeneity; they create no
additional fuel-oil histories. Overlapping monthly transformations and serial dependence remain, a
full-rank design is not evidence of predictive usefulness, and parameter-count feasibility is not
statistical power. No p-value, coefficient uncertainty or outcome-related effective sample size is
computed.

**Nothing is authorized.** `selected_architecture:
pooled_common_effect_plus_centered_sector093_interaction`; `architecture_selected_from_outcomes`,
`primary_channel_selected`, `target_joined`, `model_fitted`, `predictive_performance_computed`,
`model_feature_approved`, `target_join_authorized`, `development_modeling_authorized` and
`locked_test_evaluation_authorized` all remain **false**, and
`assert_authorization_not_granted` raises if a selection sets any of them.

Detail: `docs/c11_architecture_decision_protocol.md`, `docs/c11_architecture_decision.md`.

## Specification-correction and outcome-access governance closure (Task C11-R1 — implemented)

C11-R1 corrects the formal methodological status of the C11 architecture decision. It changes none of
C11's mathematics and removes none of its disclosures; the C11 documents are left byte-identical and
pinned, and the correction lives in a sidecar erratum, because a correction edited into a generated
file is erased by the next regeneration.

**Two facts C11 reported together are different facts.** The decision is *dependency-clean*: it
reproduces exactly from C8/C9 structural artifacts and the frozen sector-093 exposure vector, with no
D-series file opened. The original *execution* was not outcome-blind: a development metric artifact was
opened during it. No umbrella `outcome_free: true` appears anywhere in C11-R1, and
`assert_no_umbrella_outcome_free_claim` walks the whole payload and raises on one.

**One of the nine gates did not pass as preregistered.** `pooled_interaction_survives_the_specified_
preprocessing` was preregistered as *"per-industry standardization would reduce the STACKED combined
rank from 10 to 5"*. The observed stacked rank was **10**, so the gate as implemented did not pass. The
record now carries `original_preregistered_gate_set_passed: false`,
`original_gate_implementation_valid: false`, `gate_implementation_corrected_after_observation: true`,
`corrected_gate_set_passed: true` and `architecture_decision_cleanly_preregistered: false`. The
original nine gates are never described as passing without qualification.

**The correction changed which quantity was measured, not a tolerance.** Two questions were being
confused. *Does the prohibited preprocessing force the entire stacked matrix to rank five?* — **false**,
because the centred exposures carry both signs (3 positive, 8 negative), so `+x̃` and `−x̃` span two
directions. *Does per-industry standardisation preserve continuous exposure magnitude within an
industry?* — also **false**: `standardize(E_g X)` is `standardize(X)` for `E_g > 0` and `−standardize(X)`
for `E_g < 0`, so only the sign survives. Measured on both variants: within-industry combined rank
falls 10 → 5, distinct interaction blocks collapse 11 → 2, sign-identity residual 4.44e-16, while the
*selected* preprocessing retains interaction rank 5. No rank, duplicate-column or residual tolerance
moved, and `assert_not_described_as_a_tolerance_change` raises on wording that says otherwise —
including the passive forms.

**The information-flow audit uses three instruments, because each alone is weak.** A **controlled path
guard** built as an *allowlist*: an input is admitted because it is named, not because it matched no
forbidden pattern — a denylist admits every artifact nobody anticipated, which is exactly how the
access happened. **Static dependency inspection**: an AST pass over the C11 and C11-R1 chain resolving
module-level path constants at 24 read call sites, examining only call-site arguments so a prohibition
list never registers as a read, and *counting* rather than swallowing arguments it cannot resolve.
**Metric-substitution invariance**: arbitrary fabricated metric values injected into an isolated
fixture, never written to disk and never read from an artifact — the selected architecture does not
move. Result: 0 D-series paths opened, 0 forbidden read calls, 0 offending imports,
`architecture_decision_dependency_clean: true`. `assert_dependency_conclusion_bounded` raises if that
conclusion is ever used to claim the original execution was outcome-blind.

**The reproduction is exact.** Rebuilt from C8/C9 alone, both variants: source rank 5, interaction rank
5, combined 10, full design 21 of 21, constant-exposure interaction rank 0, invalid coding 21 of 22,
Candidate-B projector residual ≤ 1.1e-15, 165 panel rows, IND-04 ineligible — and the reproduced
candidate-design checksums match C11's exactly. One implementation detail is disclosed rather than
smoothed over: C11's column-space projector used unpivoted QR truncated to rank, which is only correct
at full column rank; C11-R1 uses the rank-revealing SVD basis. Every real C11 design *is* full column
rank, so the conclusion is unaffected, but the residuals differ in their last digits and both satisfy
the preregistered bound.

**Status: `exploratory_supported_after_documented_specification_correction`.** The architecture is
mathematically supported and not confirmatory. An imperfect process does not invalidate a reproduced
identity, and a convincing correction does not upgrade an exploratory selection —
`assert_status_is_exploratory` raises in both directions. `eligible_for_confirmatory_claims` and
`eligible_for_locked_test` are false.

**Bounded D5 authorization.** All nine closure gates passed, so D5 is authorized as a development-only
exploratory evaluation of the Candidate-C pooled architecture, both fuel-oil variants kept as separate
parallel variants, IND-04 in the evaluation denominators with benchmark passthrough, validation
clustered by issue month, and operational benchmarks reproduced from their registered formulas.
`d5_protocol_preregistration_authorized`, `d5_development_target_join_authorized` and
`d5_exploratory_modeling_authorized` are true; `d5_channel_selection_authorized`,
`d5_confirmatory_claims_authorized`, `d5_purge_evaluation_authorized` and
`d5_locked_test_evaluation_authorized` are false. There is no partial grant: a failed closure gate
returns every field false.

Detail: `docs/c11r1_governance_decision.md`, `docs/c11_architecture_decision.errata.md`.

## Development-only pooled fuel-oil interaction evaluation (Task D5 — implemented, exploratory)

C11-R1 authorized exactly one thing: a development-only exploratory evaluation of the Candidate-C
pooled architecture. D5 runs it, and the answer is **inconclusive for all four variant-horizons**.

**Two phases, and the boundary is a lock rather than a convention.** Phase A reproduces the C11-R1
authorization and the C9/C10/C11 invariants, writes the frozen protocol to disk, reads it back and
hashes what is actually on disk — an in-memory digest proves nothing about the artifact a later reader
would see. Only then does the guarded target reader open, and it keeps two locks: the protocol lock,
shut until that checksum matches, and a per-prediction freeze lock, so an observed value is returned
only for a key already registered as final. Observed: 720 target reads, 720 predictions frozen,
`target_reads_before_prediction_freeze: 0`.

**One estimator, and the `1/n` is what keeps it one.** `fixed_pooled_partial_ridge_v1` minimises
`(1/n)·Σ(r − r̂)² + λ(‖β‖² + ‖θ‖²)` at `λ = 1.0` — no alpha grid, no inner CV, no model averaging, no
fallback, no outcome-based feature removal. With an unnormalised sum the same λ would be a weaker
penalty on every larger panel, and the panel grows from 231 rows to 385 across the walk-forward, so the
specification would drift without a number being edited. The penalty matrix is explicit and checked
block by block: five source and five interaction coefficients penalised, the eleven industry fixed
effects not — shrinking an industry intercept toward zero shrinks it toward a stress score of zero,
which is a strong claim rather than a neutral prior. Maximum normal-equation residual across all sixty
fits: 8.88e-16.

**Preprocessing is fitted on X and structural metadata only.** The source scaler is refitted at every
outer issue on the **unique** permitted training issue months, `ddof=0`, then applied identically to
every eligible industry; fitting it on the stacked panel would weight one national series eleven times.
Sector-093 exposure is centred on the frozen eleven-industry vector and divided by its structural
standard deviation — a fixed column reparameterization for conditioning that multiplies the interaction
column by a constant and divides θ by the same constant, so the C11 estimand is unchanged. The
interaction is built after source standardisation and never re-standardised inside an industry.

**Counts reconcile exactly.** 720 predictions (2 variants × 2 horizons × 15 issues × 12 industries),
720 distinct canonical keys, 720 distinct lineage checksums, 660 modelled and 60 IND-04 passthrough.
Training issues match the preregistered table for both variants: h=1 gives 21 issues / 231 eligible
rows / 252 all-industry at 2024-01 and 35 / 385 / 420 at 2025-03; h=3 gives 18 / 198 / 216 and
32 / 352 / 384. Three clocks must agree for an issue to train — label published by `t`, feature
reference `u−2` carrying all five transformations (first such month 2022-01, which is exactly what
removes one h=1 issue at each end), and complete operational benchmark history at `u`. The two
exclusion reasons are counted separately, because "not enough price history" and "not enough stress
history" are different facts and one total would hide that h=3's start is bound by the benchmark.

**The result.** Macro-industry MAE on the full twelve-industry panel, model versus primary benchmark:

| variant | h | model | benchmark | paired 95% interval | evidence | event safety |
| --- | ---: | ---: | ---: | --- | --- | --- |
| FO 1500 | 1 | 17.111 | 17.094 | [−0.822, 0.847] | inconclusive | failed |
| FO 600 | 1 | 17.167 | 17.094 | [−0.761, 0.907] | inconclusive | failed |
| FO 1500 | 3 | 18.210 | 16.634 | [−0.096, 3.589] | inconclusive | failed |
| FO 600 | 3 | 18.207 | 16.634 | [−0.016, 3.525] | inconclusive | failed |

The model is not better on the point estimate anywhere, and every paired interval straddles zero. Under
the frozen rule — supported only if the entire interval lies below zero, adverse only if entirely above
— the MAE evidence is `inconclusive` in all four cases, and event safety failed in all four because the
model missed more high-stress months than the benchmark did. Overall status is `inconclusive`
everywhere; `exploratory_incremental_signal_supported` was never reached.

The h=1 benchmark macro MAE of 17.094469 reproduces D3's registered value exactly — from the formula,
by running the operational walk-forward, not by copying a metric artifact. An independent check
reproduced all 720 benchmark scores from B3 stress at a maximum gap of 0.0.

**Uncertainty is clustered by issue month, never by industry row.** Twelve industries at one issue
month share a national signal, a calibrator and a release date; resampling them independently would
shrink every interval by roughly √12 and could turn "inconclusive" into "supported" with no change in
the data. h=1 uses a plain issue-month cluster bootstrap, h=3 a moving-block bootstrap with block
length 3 because adjacent three-month target windows overlap by construction. Model and benchmark see
identical resamples. Fifteen clusters give limited resolution, and that is stated with every interval.

**IND-04 passes through.** No fuel-oil predictor, no fitted fixed effect, a residual correction of
exactly 0.0, and a final prediction equal to the registered benchmark — verified identical across all
60 rows. That is a structural exclusion, not a coefficient estimated at zero, and the lineage guard
raises on the second description. It stays in the primary twelve-industry denominator; the
eleven-industry figure is a preregistered secondary diagnostic that cannot replace it.

**Nothing is approved and no channel is chosen.** FO 600 and FO 1500 were fitted independently and are
reported side by side with no winner. `channel_selected`, `confirmatory_evaluation`, `purge_evaluated`,
`locked_test_accessed`, `locked_test_evaluation_authorized` and `model_feature_approved` are all false,
and the guards raise on any attempt to set them from a development number.

Detail: `docs/d5_modeling_protocol.md`, `docs/d5_assembly_audit.md`, `docs/d5_development_results.md`.

## EPPO fuel-oil modeling-channel closure (Task C12 — implemented, governance)

D5 evaluated the C11 architecture on the registered development window and found no incremental
signal. C12 records and enforces the closure of the EPPO sector-093 fuel-oil channel for further
predictive modeling. It reruns no model, recomputes no metric, tunes no specification, selects no
channel, evaluates no purge origin and opens no locked test.

**The conclusion is stated precisely, and the imprecise alternatives are refused by name.** The
recorded conclusion is `incremental_signal_not_demonstrated_in_registered_development_evaluation` —
not `fuel_oil_has_no_effect`, not `no_predictive_relationship_exists`, not `null_hypothesis_proven`,
not `structural_exposure_is_invalid`, not `EPPO_data_is_invalid`. Development evidence was
**inconclusive, not proof of absence**: fifteen issue-month clusters cannot rule an effect out, and D5
never tried to. The preregistered stop rule nevertheless supports closing further investment, and that
is a project-governance decision about where to spend effort rather than a population-level scientific
conclusion.

`assert_no_absence_claim` enforces this in both the field form and the prose form. It strips backticked
and quoted spans before checking, because the closure has to be able to *publish* its own prohibition
list — a guard that could not tell a named forbidden term from an asserted one would forbid documenting
the rule it enforces.

**The evidence chain is recorded stage by stage, because the short version is wrong in both
directions.** "C10 proved exposure is useless" misstates two stages at once. C10 established a **design
limitation** — the industry conditioning contributes cross-industry scale and no temporal degrees of
freedom, a property of the design matrix established without reading any target — and it neither did
nor could show that the channel carries nothing. **D5 supplied the development evidence**, and that
evidence was inconclusive. Attributing the closure to C10 alone overstates what a rank identity can
establish; attributing it to D5 alone loses the reason the architecture was constrained to begin with.

**Closure applies to modeling use, and nothing else.** Eight questions, answered separately: the
official EPPO source documents are still valid evidence (yes), the C7/C7.5 semantic decisions are
retained (yes), the C8 transformations are reproducible (yes), sector-093 exposure is reproducible
(yes), the interaction architecture is mathematically identifiable (yes) — while predictive utility was
demonstrated on development data (no), the channel may enter further operational modeling (no), and the
locked test may be opened for it (no). `assert_source_validity_preserved` raises if closure is used to
mark a source row, a transformation or an exposure erroneous: a model that failed to beat a benchmark
says nothing about whether its inputs were measured correctly.

**Nineteen artifacts pinned, none deleted, none modified**, spanning C7 through D5 — ten content
checksums as the durable identity and nine byte digests as a forward integrity baseline for the
generated tables. Preservation supports audit and portfolio reproducibility;
`preservation_implies_continued_modeling_eligibility` is false, and every historical runner remains
able to reproduce its own outputs under its own frozen contract.

**A new specification is not new evidence.** Sixteen reopening reasons are prohibited by name because
each re-describes what D5 already produced: another alpha, an expanded grid, a different estimator,
nonlinear terms added after the fact, feature selection or transformation removal from D5 coefficients,
picking whichever fuel oil scored better, combining the channels, PCA, tuning the high-stress
threshold, a favourable subgroup, dropping IND-04 from the denominator, switching to total-requirement
exposure *because D5 failed*, shortening the publication lag, opening purge or locked origins, and
rephrasing an inconclusive result as support for a different specification.

Reopening requires evidence **external to D5's performance**, in one of six categories: a
product-specific industrial fuel-consumption crosswalk, a newer compatible I/O table available before
the evaluation period, verified point-in-time release evidence, a materially longer compatible target
history obtained without purge or locked origins, a proven material implementation error, or a
genuinely new external hypothesis registered before any corresponding result is inspected. Every
request must carry nine fields — including a checksum, an availability date, an explicit account of why
D5 could not have used it, an attestation that it was not selected from D5 outcomes, and a superseding
decision-log entry. The guard raises on a missing or empty field, on a false attestation, and on any
record carrying a D5 outcome field such as `model_mae` or `paired_ci_low`.

**The enforcement guard refuses modeling and permits everything else.** It rejects both variants, their
aliases (matched after case- and separator-normalisation, so a respelling cannot walk past), their
composite forms, and direct access to the C8/C9/C10/C11 feature tables — for `modeling`,
`model_training`, `target_assembly`, `feature_selection`, `operational_modeling` and
`locked_test_evaluation`. It permits `audit`, `reproduction`, `documentation`, `source_quality`,
`provenance_verification` and `historical_d5_reproduction` untouched, and an unknown purpose raises
rather than defaulting to allowed. A refused feature is reported **with its closure reason and the
statement that it is present and reproducible** — never as missing, because "not found" would send the
next reader hunting a bug that does not exist. Thirty guard probes were run from both sides at closure
time; unrelated commodity features are unaffected and generic upstream feature creation is untouched.

Detail: `docs/c12_channel_closure.md`, `schemas/fuel_oil_reopening_evidence.schema.yaml`.

## Development-programme closeout (Task E1 — implemented, synthesis)

E1 closes the development programme with a machine-verifiable technical report, a portfolio case study
and an evidence ledger in which every material claim carries a pointer to the artifact that supports
it. It reruns no model, recomputes no metric from raw predictions, fits nothing, selects nothing, reads
no purge outcome and never opens the locked test.

**The synthesis contract is frozen before any result artifact is read.** Included tasks, evidence-status
vocabulary, required tables, claim-registry schema, supersession rules, prohibited claims, portfolio
wording constraints, locked-test guards and expected project-status fields are all hashed first.

**The final status.** `development_program_status: closed_without_supported_incremental_commodity_model`;
the registered operational reference is D3's persistence forecasts; `operational_model_selected: false`,
`production_deployment_authorized: false`, `model_feature_approved: false`,
`confirmatory_claim_authorized: false`, `locked_test_status: sealed_unopened`,
`fully_real_time_backtest: false`, `latest_vintage_target_evaluation: true`. The phrase *project failed*
is refused by name: the engineering and evaluation programme completed and produced a reproducible
pipeline, a registered reference and four honest results — what did not happen is that a candidate
earned promotion, and those are different sentences.

**Six collapses are refused individually**, because a single instruction to be careful catches none of
them. Inconclusive is not no effect. Not supported is not disproven. Unresolved is not absent. A
selected reference is not a proven superior — D3's paired comparison against no-contraction was
*inconclusive* at both horizons and persistence is the registered reference through a preregistered
tie-break. A development evaluation is not a production validation. A latest-vintage evaluation is not
a real-time backtest. Each guard strips backticked and quoted spans and skips negated occurrences, so
the report can publish its own prohibition list and write "has not disproved" without tripping the rule
it is stating; the production guard also permits "production data", which in this domain means
manufacturing output.

**The development ledger keeps every result, including the negative and superseded ones.**

| task | h=1 model | h=1 reference | h=3 model | h=3 reference | status |
| --- | ---: | ---: | ---: | ---: | --- |
| D1 (superseded) | 15.3073 | 14.5287 | 16.1072 | 14.6985 | not supported |
| D4 | 17.5616 | 17.0945 | 17.9051 | 16.6338 | not supported |
| D5 FO 1500 | 17.111 | 17.094 | 18.210 | 16.634 | inconclusive |
| D5 FO 600 | 17.167 | 17.094 | 18.207 | 16.634 | inconclusive |

D1's numbers travel with three limitations: the evaluation was not release-timing correct, the nested
protocol was not fully executed, and 6 of 30 origin-horizon selections used the conservative fallback
whose effect direction is unknown. It is superseded by D3/D4 for operational interpretation and stays
in the ledger with that marker — deleting a negative result is how a record starts lying. D4's paired
intervals were [−0.2060, 1.3736] and [0.4317, 2.1098]; its event-safety gate passed at both horizons
and `event_safety_overrides_mae_result` is false, because both gates were required and one failed; 180
of 360 primary-panel rows were benchmark passthrough. D5's four intervals all crossed zero and event
safety failed in all four.

**The locked test is verified sealed without being opened.** The reservation is key-only, so the
horizon-1 range 2025-07..2026-04, the horizon-3 range 2025-07..2026-02, the ten reserved months and the
2025-04..2025-06 purge buffer are all confirmable from keys alone. Hashing an outcome would still be
reading it, so the guard raises on any outcome-shaped field and the reproducibility manifest records no
locked path. No candidate holds locked-test authorization.

**Every claim carries its evidence.** Twenty-six numeric claims were resolved against their artifacts
and reconciled at 0.001; twenty-six claims are registered with a status from the seven-value
vocabulary, a pointer into a loaded artifact, the limitations that artifact requires, and
`locked_test_dependency: false`. The registry refuses a pointer into a file nobody opened, a superseded
status without its successor, a duplicate claim id, a claim that omits a required limitation, and any
passage comparing D1 with D3/D4/D5 without saying the evaluation contracts differ.

**The test count is measured, not quoted.** The manifest runs the suite and parses its own summary
line; a supplied literal raises, because a number typed into a reproducibility manifest drifts the
moment a test is added and a stale count looks like evidence. Raw retrieval manifests are referenced
rather than duplicated.

Detail: `docs/e1_technical_closeout.md`, `docs/e1_portfolio_case_study.md`,
`docs/e1_evidence_ledger.json`, `docs/e1_reproducibility_manifest.json`.

## Open questions

Tracked in `docs/architecture/decision_log.md` and `docs/project_roadmap.md` §11 — not duplicated
here to avoid the two lists drifting out of sync.
