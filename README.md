# Thai Supply Chain Shock Early Warning System

A monthly early-warning model that estimates, for 12 Thai manufacturing industry groups, which
industries are likely to be affected by a supply-chain shock (raw materials, energy, imports,
trading-partner countries, logistics), how severe the effect is likely to be, and when.

**Project status: development programme CLOSED (B1–E1). No commodity model earned
promotion; the locked final test was never opened.**

| | |
| --- | --- |
| development programme | closed without a supported incremental commodity model |
| registered operational reference | persistence forecasts, both horizons |
| operational model selected | no |
| production deployment authorized | no |
| locked final test | **sealed, unopened** |
| evaluation basis | latest-vintage targets; not a real-time backtest |
| reopening | requires genuinely new external evidence and a new preregistration |

**The registered operational reference** (development, macro-industry MAE on the
0–100 score, under the release-aware issue-month contract): **17.09** at 1 month
(`operational_persistence_latest_published`) and **16.63** at 3 months
(`operational_persistence_trailing_3m_max`). Earlier figures of 14.53 and 14.70
came from a superseded evaluation that predated the timing contract and are not
comparable to these.

Three candidates were evaluated across the fifteen registered development issue
months and none beat its benchmark; every paired interval crossed zero or sat
above it. That is a negative result and it is reported as one — inconclusive
where the intervals were inconclusive, never as proof that these signals carry
nothing.

### Where to start reading

| you want | read |
| --- | --- |
| the short, non-technical story | [`docs/e1_portfolio_case_study.md`](docs/e1_portfolio_case_study.md) |
| the summary and CV bullets | [`docs/e1_executive_summary.md`](docs/e1_executive_summary.md) |
| the full technical closeout | [`docs/e1_technical_closeout.md`](docs/e1_technical_closeout.md) |
| every claim with its evidence pointer | [`docs/e1_evidence_ledger.json`](docs/e1_evidence_ledger.json) |
| how to reproduce it | [`docs/e1_reproducibility_manifest.json`](docs/e1_reproducibility_manifest.json) |
| the decision history | [`docs/architecture/decision_log.md`](docs/architecture/decision_log.md) |
| methods in depth | [`docs/methodology.md`](docs/methodology.md) |

**Running it yourself, and what ships (Task E2-R1).** The source-release
candidate is prepared and verified but **not published**: no commit, tag, push,
GitHub repository, PyPI upload or release. It is **MIT licensed**, released as a
**public GitHub source checkout**, and requires **Python 3.12**.

| you want | read |
| --- | --- |
| how to install and run it, in three tiers | [`docs/e2r1_reproducibility_guide.md`](docs/e2r1_reproducibility_guide.md) |
| what was verified, and what is still open | [`docs/e2r1_release_checklist.md`](docs/e2r1_release_checklist.md) |
| the release decision and its evidence | [`docs/e2r1_source_release_decision.md`](docs/e2r1_source_release_decision.md) |
| every released file with its checksum | [`docs/e2r1_release_manifest.json`](docs/e2r1_release_manifest.json) |
| where the data comes from | [`DATA_SOURCES.md`](DATA_SOURCES.md) |
| the licence position, code and data | [`docs/e2_data_license_review.md`](docs/e2_data_license_review.md) |
| dependency licences | [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |
| the superseded E2 decision, preserved unedited | [`docs/e2_release_readiness.md`](docs/e2_release_readiness.md) |

**No third-party data is redistributed here.** The four publishers' workbooks,
PDFs and archives are excluded because their redistribution terms are
unresolved; what ships is the acquisition code, the source URLs and a SHA-256
checksum for every file retrieved, which is enough to fetch the same bytes and
prove you got the same bytes. Public download access is not a redistribution
right.

**Target (Task B3):** the predicted outcome is the **Industry Production Stress
Score** — adverse year-over-year MPI change, calibrated to each industry's own
history. It is a *production-stress* outcome, not a comprehensive supply-chain
index: MPI measures the consequence of a shock, while the shocks themselves will
be represented by future input features.

Task B2 classified MPI and Capacity Utilization as **`redundant`**, so the
planned K=2 equal-weight composite stays **`rejected`**; B3 redefined the target
around **MPI alone (K=1)** rather than retaining a duplicative second component.
CapU remains in the panel as an auxiliary indicator. See
`docs/b3_target_definition.md` and `docs/b2_component_validation.md`.

What exists now:

- Real OIE source files retrieved, checksummed, and recorded in retrieval manifests.
- A production ingestion pipeline (`thai_supply_chain_ews.data.{oie,ingest,build_panel,taxonomy}`)
  that parses the current 2021-based OIE edition into a division-month table and a balanced
  **12-industry × 66-month panel** (2021-01 … 2026-06), using official OIE weights.
- Source-verification and bridge-validation research evidence for older editions
  (`docs/oie_overlap_validation_v2.md`), which is **not** used by the MVP panel.

What exists after B3: raw monthly production stress (636 observations) and raw forecast labels for
the 1- and 3-month horizons (1,224 rows), plus a leakage-safe industry-relative calibrator.

What exists after B4: out-of-fold development predictions for five deterministic baselines under a
leakage-controlled walk-forward protocol, with clustered bootstrap intervals.

What exists after C1: the World Bank Pink Sheet commodity price data, verified and ingested as
levels (5,269 rows, 7 series, 1960-01 … 2026-07). Five series are `source_verified`; two are
`conditional` because their pricing benchmark changed inside the modelled window. **No commodity
series is an approved model feature** — `model_feature_approved` is false for all of them, and none
has been joined to the target.

What exists after C1.5 (revised twice, in C1.5-R1 and C1.5-R2): a verified timing contract built on
**all 65 archived Pink Sheet issues**, each validated against its own internal date and displayed
columns. Two corrections were needed to get here — the first run wrongly reported 62 issues as
missing (incomplete discovery, AD-R39), and R1 wrongly reported February 2025 as a duplicate of
January after fetching the wrong URL (AD-R40). Reference month *t* is first published in month
*t+1*, so same-month use is structurally impossible and lag zero is prohibited. The **verified
`minimum_publication_lag_months` is 1** — all 65 months are measured, none bounded — with 2
recommended as labelled policy margin; `revision_safe_lag_months` stays null because revisions are
common. **Point-in-time first-release values cover all 65 reference months and all 15 development
origins.** LNG Japan differs from the later vintage in 100% of in-window months and is excluded from
the primary feature set; **Brent and Rubber RSS3 never differ**.

A third correction (**C1.5-R3**, AD-R45) fixed a semantic error rather than a retrieval one: the
table token `a/` had been read as an *estimate marker*, when the issues' own footnotes define it as
"included in the energy index". Estimate status now comes from a separate Description statement
(*"recent two months' averages are estimates"*), giving LNG 65 documented first-release estimates,
**63** observed transitions and **2 right-censored** months. All numerical revision results, and all
1,224 C2 feature values, were verified unchanged.

What exists after C2: a **point-in-time commodity feature table** — 1,224 canonical rows, four
series (Brent, aluminum, copper, rubber RSS3) × five preregistered transformations (price level;
1-, 3- and 12-month natural-log changes in percent; 3-month realized volatility at `ddof=0`). Every
row records the archived first-release observations it consumed, their publication months, and a
lineage checksum. Availability is `max(reference month + 2, every input's publication month)`, where
1 month is measured and the second is labelled policy margin. LNG, coal and palm oil stay excluded
with no substitutes. `feature_construction_approved: true`; `model_feature_approved` remains
**false** for every series — C2 approves correct construction, not predictive usefulness.

What exists after C3: a **commodity–industry structural exposure matrix** — 48 rows (12 industries ×
4 commodities) built from NESDC's official **Input–Output Table of Thailand 2015**. Each row carries
direct, indirect and total-requirement coefficients, the official sector codes and definitions behind
them, a mapping type and confidence, and a direction channel. Highlights: refined petroleum embodies
**0.71** of its input value as crude directly; chemicals reach crude almost entirely *indirectly*
(0.006 direct, 0.194 total); basic metals show an **observed zero direct with 0.169 indirect** — zero
direct is not zero exposure. Aluminum and Copper resolve to the **same** official sector, so their
rows are identical by construction and flagged as one aggregate reported twice. `model_feature_approved`
remains **false** on all 48 rows: C3 approves structure, not usefulness.

**Corrected in C3-R1** (AD-R50): C3 wrongly reported that no official 58-sector 2015 workbook exists
— it does, in NESDC's media library, which C3's download-page-only discovery never queried. The
180-sector table remains primary, and the 58-sector file now serves as an independent check: **12 of
12 partition-invariant totals match exactly**. C3-R1 also adds a **commodity-proxy fitness gate**,
because a valid coefficient can still be a poor proxy — IND-12's non-ferrous exposure is 95.7%
jewellery, i.e. precious metals, so it is marked `not_fit_for_commodity_specific_use` while keeping
its number. **43 of 48** pairs are feature-eligible; no exposure value changed.

What exists after C4: the **industry-conditioned feature matrix** — 39,474 rows (43 eligible pairs ×
306 observations × 3 variants), each value a C2 commodity feature multiplied by a C3-R1 exposure and
a direction sign, with combined lineage back to the archived PDF and the I/O workbook. The I/O
structure is dated by its **publication** (2020-03-31), never its 2015 reference year — backdating it
would have leaked four years of structure invisibly. A development snapshot materialises 15 origins ×
12 industries = 180 rows with 3,225 eligible and 375 structurally unavailable cells, selected by
availability metadata rather than positional shifting. `model_feature_approved` remains **false**.

What exists after D1: the **first predictive model**, and a **negative result**. An industry-specific
ridge residual correction on top of the B4 persistence benchmarks scores macro MAE **15.31 vs 14.53**
(h=1) and **16.11 vs 14.70** (h=3) — worse at both horizons, with the paired 95% CI excluding zero in
the *benchmark's* favour and only 2 of 15 origins favouring the model. Under the preregistered rule
both horizons are **`incremental_signal_not_supported`**. The nested selection agreed independently:
the most regularized alpha was chosen at 27 of 30 origin-horizons. The model does catch more
high-stress events (recall 0.70 vs 0.65 at h=1) at worse precision, but the rule fixed in advance says
that qualifies the discussion without overriding the verdict.

This is reported as found. It was not repaired by widening the grid or re-searching features, and it
does **not** show that commodity prices are irrelevant to Thai production — only that this narrow
chain, on 15 development months, adds nothing beyond persistence.

The **locked final test remains unopened**, and no feature is model-approved. No result in this repository is a model result, and no feature has been compared with the
target.

What exists after D2: an audit of the **target's** own publication timing, and two findings that
constrain everything above. First, OIE first publishes reference month *t* a median **29 days** after
*t* ends — during month *t+1*. B4 assumed current-month stress is known at forecast origin *t*; it is
not, so at origin *t* the latest published month is *t-1*. The finding is recorded and the split is
deliberately **left unchanged** — correcting it is a separate decision, not a side effect of measuring.
Second, D1's fallback on 6 origins was caused by too little pre-origin history, and that **cannot be
remedied by extending history**: reaching the required 2020-04 start means splicing base-year editions
whose overlap shows **19 of 21 divisions re-estimated** rather than rebased, with TSIC division 16
missing from both older editions and the oldest labelled ISIC rather than TSIC. Evidence outcome:
**`timing_only_supported`** — no complete 12-industry point-in-time vintage was found, so a future
target reconstruction cannot be called point-in-time.

D2 also **withdraws a D1 claim**: that the fallback (alpha 100, channel `none`) "can only make the
model look worse, never better". Ridge at alpha 100 still fits an intercept and can retain predictors,
so it shrinks toward the benchmark with **no guaranteed error direction**
(`fallback_effect_direction: unknown`). The D1 verdict itself is unchanged. The original wording is
left in place with a correction beside it rather than edited away.
That correction now lives in a sidecar erratum, [`docs/d1_development_results.errata.md`](docs/d1_development_results.errata.md), so a later regeneration of the D1 documents cannot silently erase it. The two D1 files were restored by reversing the known D2 insertion; the original pre-D2 digest was unavailable, so exact historical byte identity cannot be independently proven — the restored files are pinned from D3 onward in `docs/d3_restored_d1_checksums.json`.

What exists after D3: a **release-aware operational contract** replacing B4's non-operational
forecast origin. At issue month *t* the forecast is made after OIE publishes month *t-1*, the newest
observable stress is *t-1*, and a training label counts only once `target_window_end + 1 month <= t`.
Rebuilt on the same 15 development issue months, the operational benchmarks are
**`operational_persistence_latest_published`** at h=1 (macro MAE **17.0945**) and
**`operational_persistence_trailing_3m_max`** at h=3 (**16.6338**) — an operational penalty of
**+2.57** and **+1.94** against B4's non-operational numbers. That gap is *not* attributable to
publication lag alone: the calibrator cutoff and the label-availability rule moved at the same time.

Framing: **`release_lag_aware_latest_vintage_evaluation`**. Timing is now honest; the target *values*
are still latest-vintage, so this is **not** a point-in-time or fully real-time backtest. B4 and D1
remain reproducible and are relabelled non-operational rather than deleted.

On macro MAE those benchmarks are **effectively tied with `operational_no_contraction`** within
uncertainty (h=1 paired +2.3509, CI [−2.6478, 6.5716]; h=3 +0.3453, CI [−2.6858, 4.6333]). The
preregistered tie-break on high-stress false negatives settles it decisively — **8 vs 21** at h=1
and **4 vs 28** at h=3 — so the selection stands, and no second test was run on the same sample.
No-contraction is retained as a **secondary** comparator; future models must beat persistence as the
primary comparator and report both.

What exists after D4: the operational version of D1's question, and the same answer. A **frozen**
ridge residual correction (alpha 100, channel `none`, Brent + Rubber only) run under the D3
release-aware contract scores macro MAE **17.5616 vs 17.0945** (h=1) and **17.9051 vs 16.6338**
(h=3) against the operational persistence benchmarks — worse at both horizons, with the h=3 paired
interval excluding zero *against* the model. Both horizons are
**`incremental_signal_not_supported`**. Event safety **passed** (6 vs 8 and 1 vs 4 false negatives:
the model catches more events at worse precision), but advancement needs both gates, so
`development_candidate_supported: false`.

This is **exploratory, not confirmatory** — the specification was frozen after D1's results were
already observed — and no outcome makes it locked-test eligible. The single most important
diagnostic: C3's *direct* exposure is zero for 16 of 24 Brent/Rubber pairs, so for **6 of 12
industries** every predictor is a structural constant and the model reduces to the benchmark
exactly. Half the panel carries no commodity signal at all.

What exists after C5: the structural explanation for D4's zeros. Using the official 2015 I/O table,
**Brent direct exposure is zero for 10 of 12 industries** — but indirect exposure is **7–17%**,
mediated by **Electricity**, **Petroleum refineries** and **Petrochemicals**. Industries buy refined
fuel and power, not crude, so Brent is `stage_misaligned` wherever direct exposure is zero. The
decomposition reconciles with C3 to **2.8e-17**.

Four official source families were audited for the missing stage. **EPPO's ex-refinery petroleum
price** (BAHT/LITRE, before excise, municipal tax, oil fund and wholesale margin) is the one family
passing all ten preregistered criteria and is recommended for a later C6 ingestion audit. Ministry
of Commerce PPI (403) and ERC (timeout) are recorded as **blocked, not absent**. Selection used no
target outcome and no D4 metric.

What exists after C6: an audited EPPO archive, and a split verdict. The official WordPress REST index
yields **5,233 ex-refinery price workbooks from 2002 to 2026**, covering **65/65 months** of the
2021-01 parity window and **53/53** of the 2022-01 operational window with no gaps — but **every
upload timestamp comes from the 2026 site migration**, so when each document became public cannot be
established. Independent captures corroborate only 43 dates, none overlapping the validated sample.
Outcome: **`values_retrievable_timing_unresolved`** — the values are there, the release timing is not. C6.5 converts that into an explicit policy: EPPO is approved for **release-lag-aware latest-vintage exploratory** use under a **conservative two-month policy lag that is not a measured delay**, with `minimum_verified_publication_lag_months` left null. The timing limit is a limit of the sources inspected, not a proof that no evidence exists anywhere.

254 of 256 retrieved documents validated; two were rejected because the date inside the workbook
disagreed with the archive item. Two layout regimes and a real product break (2024-01 publishes only
diesel blends, no plain H-DIESEL) are recorded as explicit semantic regimes rather than spliced.
`feature_semantics_approved: false`, `model_feature_approved: false`.

C7 then ingested the rest of it. All **1,315** officially discovered document-days in
2021-01…2026-05 were attempted: 1,333 retrieved, 1,331 content-valid, **1,310 valid canonical
document-days**, **5 unresolved** — three whose official media records point at files that return
404, and two whose internal date disagrees with the listing date and are neither reassigned nor
counted. The full archive corrects two things the sample could not show: **ordinary H-DIESEL is
absent for 305 document-days, 2023-09-18 to 2024-12-17**, not the 22 days C6 saw (C6 sampled no other
day inside the absence — it is extended, not contradicted), and **both fuel-oil labels drop their
ordinal index for 66 days in 2024**, which is surfaced as an unconfirmed label variant rather than
silently merged.

The monthly source table (195 rows, `arithmetic_mean_of_validated_observed_official_document_days`)
exists, but **`monthly_aggregation_contract_approved` is `false`**: 162 of 195 product-months pass
and the gate is reported as failed rather than forced. `source_available_as_of` is null everywhere,
`policy_available_month` is `reference_month + 2`, and no transformation, target join or model was
created.

C7.5 closed what C7 left open. The fuel-oil label question is settled on the publisher's own evidence:
the workbook's Thai companion sheet is formula-bound to the English rows and gives **one identical,
ordinal-free product name for both label forms**, so `equivalence_established` — with the raw labels
preserved and numeric continuity explicitly not load-bearing. What `(1)` and `(2)` mean is still
`not_established_from_inspected_sources`, and the decision does not rest on it. Two of the five
unresolved document-days were **recovered** on official evidence independent of the filename (each
attachment's parent post is titled and dated to match the document's own internal date); the three
April 2026 files remain unretrievable and are recorded as such. H-DIESEL is excluded as
`not_ready_long_semantic_definition_gap` — the documents are valid, the series cannot be continuous.

C7's single approval boolean became three, because it was answering three questions at once: the
**method** is approved for all three series, **coverage** is complete for none of them, and
**transformation readiness with explicit gaps** is granted to the two fuel oils only. Every month
carries a strict value (null unless its whole inventory validated, and the only value a transformation
may read) beside a descriptive one that is always labelled incomplete.

C8 turned the two approved fuel-oil series into source-level transformations — price level, 1m/3m/12m
log change and 3m realized volatility — reusing C2's production formulas rather than re-implementing
them. The grid is complete on purpose: **650 rows, 598 finite, 52 null**, with every null carrying a
status that says whether it is insufficient prehistory or an actual source gap, and lineage that names
the expected, available and missing months. Nothing is imputed or carried forward. The formulas match
C2's; the **evidence does not** — C2's inputs are archived first-release values with measured timing,
C8's are latest-vintage under an unmeasured two-month policy lag, and both facts are recorded side by
side.

C9 closed the loop C5 opened. C3 had measured exposure to **crude** and found ten of twelve industries
at direct-zero; C9 measures exposure to **sector 093, Petroleum refineries** and finds **every
industry buys it** — 0.0047 to 0.0642, no observed zeros — because factories buy refined fuel, not
crude. The exposure is derived twice by different routes and reconciles to 1.4e-17.

The task runs in two enforced phases: the structural decision is made, hashed and frozen **before** any
C8 price is loaded, and the digest is re-checked before and after conditioning. Sector 093 is a basket
of nine products in NESDC's own words, so fuel oil stands in for the whole basket and every industry is
`broad_proxy_use_with_caution`, never better. **IND-04 contains sector 093 itself**, so its direction is
mixed rather than forced to +1, and it is ineligible and retained. The conditioned grid is 7,800 rows
with an absence taxonomy that keeps "ineligible", "source missing" and "measured zero" strictly apart.
Nothing is joined to a target and nothing is model-approved.

C10 then asked what those conditioned features actually contain, still without opening a target. C9
gives 165 eligible rows per fuel oil over the development window, and it is tempting to read that as
165 observations. It is not: the conditioning is `D = E · X`, so every eligible industry's design is
**one 15 x 5 source-time matrix multiplied by its own positive exposure**. The audit confirms that
three ways — cross-sectional rank is **1** at all 15 issue months, the source-time matrix and every
industry matrix and the 165-row stacked panel all have rank **5**, and exposure normalisation recovers
the same matrix from all eleven industries to within 7e-15. Per-industry standardisation then erases
the exposure entirely, because a positive scalar cancels in both the mean and the standard deviation.

So the industry conditioning contributes **cross-industry scale and no new temporal shape**. That is a
statement about the design matrix, not about how a model would perform — C10 never reads a target,
a prediction or a metric. Every threshold was hashed before the first value loaded and re-checked
after the diagnostics; one preregistered expectation failed and is published as a discrepancy rather
than quietly relaxed. Both fuel oils are reported side by side with no preferred channel, IND-04 stays
in the matrix behind an explicit mask, no transformation is removed, and all 1,800 cells are traced
back through both provenance chains.

C11 turned that finding into a design decision, still without opening a target. If exposure is only a
per-industry scalar, then fitting the conditioned feature separately per industry is not a second
architecture — it is the same design in different coordinates, and C11 shows it: the column-space
projectors agree to 6.5e-16 across all eleven eligible industries. What *is* different in kind is
pooling. In a panel, exposure × price varies across industry **and** time, so a centred interaction is
not proportional to the main effect and can carry a constrained cross-industry slope pattern. The
selected architecture is a pooled common fuel-oil effect plus a centred sector-093 interaction, with
industry fixed effects: a feature-only 165 × 21 design of rank 21, source block 5, interaction block 5,
combined exactly 10.

Three ways to wreck that were built rather than argued — a constant exposure (interaction rank 0), a
redundant global intercept (21 of 22 columns), and standardising the interaction inside each industry
(which keeps only the *sign* of the exposure, collapsing eleven amplitudes to two groups). One
preregistered expectation failed along the way: the stacked rank does not fall the way the config
predicted, because the centred exposures carry both signs. The number was the wrong measurement of a
real collapse, so the measurement was corrected, the preregistered value was left as written, and the
gate that had depended on it is recorded as having been fixed after the fact.

Selecting an architecture authorizes nothing. No target was read, no model was fitted, no channel was
preferred, and the locked test stays closed.

C11-R1 then corrected the *status* of that decision without touching its mathematics. Two things C11
had reported together turn out to be different facts, and they are now recorded separately.

The first is the gate. C11 said all nine of its mandatory gates passed. That is true of the **corrected**
gate set and not of the **originally preregistered** one: the original gate expected a stacked rank to
fall from 10 to 5 under a preprocessing the contract forbids, and it does not, because the centred
exposures carry both signs. The collapse C11 claimed is real — within an industry the combined block
does fall to rank 5, and eleven exposure-proportional interaction blocks collapse to two sign groups —
but the stacked rank was the wrong place to look for it. No tolerance moved; the gate was measuring
the wrong quantity. That correction was made after the result was visible, and the record now says so:
`architecture_decision_cleanly_preregistered: false`.

The second is the access. During C11 a development metric artifact was opened, which was not needed —
the benchmark name it was opened for was already in the decision log. No metric value reached the
configuration, the matrices, any checksum or the selection, and C11-R1 reproduces the whole decision
from C8/C9 alone with zero D-series paths opened, an AST pass over every read call site, and arbitrary
fabricated metrics injected into an isolated fixture that leave the architecture unmoved. So the
decision is **dependency-clean**. The execution was **not outcome-blind**, a guard added afterwards
does not reach backwards, and there is no umbrella `outcome_free` flag anywhere.

The resulting status is *exploratory, supported after a documented specification correction*. An
imperfect process does not invalidate a reproduced identity, and a convincing correction does not
upgrade an exploratory selection. On that basis D5 is authorized as a development-only exploratory
evaluation — target join and modeling yes; channel selection, purge metrics, confirmatory claims and
the locked test, no.

D5 then ran the one evaluation C11-R1 authorized, and the fuel-oil channel did not earn its place. The
pooled model corrects the operational persistence benchmark using a common national fuel-oil signal
whose amplitude varies with each industry's sector-093 purchases. On the fifteen development issue
months it is **not better than the benchmark anywhere**: macro MAE 17.11 and 17.17 against 17.09 at one
month, 18.21 and 18.21 against 16.63 at three months. Every paired 95% interval, resampled by whole
issue months, straddles zero, and the model missed more high-stress months than the benchmark did in
all four cases. Under the rule frozen before any target was read, the verdict is `inconclusive` for
both fuel oils at both horizons.

Getting to an honest "inconclusive" was most of the work. The protocol was written to disk, read back
and hashed before the target reader would return a single value, and that reader also refused to score
any prediction that had not yet been frozen — 720 reads, none early. The estimator is one fixed ridge
with no grid and no cross-validation, its loss averaged by `n` so the same penalty means the same thing
when the training panel grows from 231 rows to 385. Training counts, prediction counts and lineage
checksums all reconcile to the numbers preregistered for them, and the benchmark was reproduced from
its registered formula rather than copied from an earlier result.

FO 600 and FO 1500 were fitted separately and are reported side by side with no winner; IND-04 keeps
the benchmark untouched because its direction is unresolved. Nothing here approves a feature, selects a
channel or opens the locked test.

C12 closed the channel. That word is doing precise work: the EPPO fuel-oil features may no longer enter
modeling or target assembly, and the locked test stays shut for them — but nothing about the source
pipeline is retracted. The official documents are still valid evidence, the semantic decisions stand,
the transformations and the sector-093 exposure remain reproducible, and the interaction architecture
is still mathematically identifiable. A model that failed to beat a benchmark says nothing about
whether its inputs were measured correctly, and a guard raises if the closure is ever used to say
otherwise.

Nor is the closure a finding about fuel oil. The recorded conclusion is that incremental signal was
*not demonstrated* in the registered development evaluation. Fifteen issue-month clusters cannot rule
an effect out, and D5 never tried to; six over-reaching phrasings are refused by name. Attributing the
outcome to C10 alone would also be wrong — C10 established a property of the design matrix without
reading any target, and it was D5 that supplied the evidence.

Nineteen artifacts from C7 through D5 are pinned, none deleted or modified, so every historical task
stays reproducible. Reopening needs evidence external to D5's performance — a product-specific
consumption crosswalk, a newer I/O table, verified release vintages, a longer target history, a proven
implementation error — carrying provenance, an availability date and a superseding decision. Another
alpha is not evidence.

Two limitations that shape everything downstream:

- The panel is **latest-vintage historical data**, not point-in-time. D2 has since established a
  verified release calendar for the **MPI target** (111 credible months, median 29-day lag), but no
  point-in-time *vintages* exist for it and commodity `release_date`/`available_as_of` remain null, so
  a real-time backtest is still not supported.
- Preliminary months are retained but excluded from model-eligible rows.

Run ingestion with:

```bash
python scripts/run_b1_ingestion.py
```

Run component validation with:

```bash
python scripts/run_b2_component_validation.py
```

Build the target with:

```bash
python scripts/run_b3_target_build.py
```

Run the walk-forward baselines with:

```bash
python scripts/run_b4_baselines.py
```

Verify and ingest the commodity sources with:

```bash
python scripts/audit_world_bank_commodities.py
```

```bash
python scripts/run_c1_commodity_ingestion.py
```

Audit commodity publication timing with:

```bash
python scripts/audit_c1_5_commodity_timing.py
```

## Setup

> **This repository is released as a reproducible source-checkout research
> project. Standalone wheel/PyPI installation is not currently supported
> because several audit modules intentionally resolve repository-level evidence
> and configuration paths.**

**Requires Python 3.12.** That is the supported floor and the only tested
version: both dependency locks were regenerated and verified on it. Later
versions are permitted by metadata and are not tested.

### Linux and macOS

```bash
git clone <repository-url> thai-supply-chain-ews
```

```bash
cd thai-supply-chain-ews && python3.12 -m venv .venv
```

```bash
.venv/bin/python -m pip install -r requirements.lock.txt -r requirements-dev.lock.txt
```

```bash
.venv/bin/python -m pip install --no-deps -e .
```

```bash
.venv/bin/python -m pytest -q
```

### Windows (PowerShell)

```bash
py -3.12 -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt -r requirements-dev.lock.txt
```

```bash
.venv\Scripts\python.exe -m pip install --no-deps -e .
```

```bash
.venv\Scripts\python.exe -m pytest -q
```

`--no-deps` is deliberate: the locks already fixed every version, including
transitive ones, and a project install that re-resolves them is not installing
from the lock. `-e` is deliberate too: the configurations, mapping tables,
documentation and evidence artifacts live in the repository rather than inside a
wheel, and an editable install is the arrangement in which those paths resolve.

The tests need no data. Those that do are skipped by name with a reason — see
[`docs/e2r1_reproducibility_guide.md`](docs/e2r1_reproducibility_guide.md) for
the three reproduction tiers and how to obtain the source layer.

To run the acquisition and evaluation scripts, export the project root, which
this project never guesses:

```bash
export THAI_SUPPLY_CHAIN_EWS_ROOT=/absolute/path/to/thai-supply-chain-ews
```

`.env.example` documents the variable. Nothing loads a `.env` file
automatically, so export it in your shell.

## Licence

**MIT** — see [`LICENSE`](LICENSE). It covers this project's own code and
documentation. It grants no rights in the World Bank, NESDC, OIE or EPPO
material this project analyses, none of which is redistributed here; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
[`DATA_SOURCES.md`](DATA_SOURCES.md).

## Repository map

- `docs/data_source_inventory.md` — verified/unverified status of every candidate data source
  (official Thai government data first, then authoritative international public data).
- `docs/architecture/` — data layer design, data contract, and the architecture decision log.
- `docs/project_roadmap.md` — two-phase work breakdown, gates, and Definition of Done.
- `docs/modeling_strategy.md` — the global panel model design, including the two independent
  horizon-specific models (`global_model_1m`, `global_model_3m`), split/embargo logic, and required
  tests.
- `docs/target_definition.md` — the Industry Stress Score's two-stage design (industry-relative
  robust-z normalization, then global logistic calibration to a common 0–100 scale and one shared
  risk-threshold set), walk-forward calibration behavior, and required tests.
- `docs/methodology.md` — method summary (draft), pointing into the documents above.
- `configs/` — `data.yaml`, `features.yaml`, `model.yaml`, `targets.yaml`: adjustable settings, with
  unresolved items explicitly marked rather than silently defaulted.
- `src/thai_supply_chain_ews/` — the installable package. Most modules are currently stubs
  (`raise NotImplementedError`) — see each module's docstring for what it will do and which
  roadmap task implements it. `config.py`, `data/validate.py`, and `evaluation/{splits,metrics}.py`
  contain real, tested logic (generic infrastructure, not business logic).
- `tests/` — automated tests for the infrastructure that does exist (config loading, data-quality
  and leakage-check utilities).
- `notebooks/` — EDA/research only; nothing here is production logic.
- `app/` — the dashboard application (not yet implemented).
- `data/` — the seven data layers. All empty except `data/mapping/`, which holds the hand-curated,
  Git-tracked classification tables (also currently empty of real codes pending source
  verification — see `docs/data_source_inventory.md`).

## Method

This project adapts, to Thai industrial supply-chain shock propagation (not portfolio optimization
or stock selection), several ideas from Igor Halperin's *"Are Three Matrices All You Need To Beat
the Market?"* (2026) — specifically its distance-matrix / Markov-chain transition-matrix
representation, its walk-forward validation discipline, and its explicit stance against look-ahead
bias and target leakage. See `docs/methodology.md` (draft) for the adaptation notes and the points
where the source paper's methods were deliberately **not** carried over.
