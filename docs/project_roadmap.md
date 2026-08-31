# Project Roadmap — Thai Supply Chain Shock Early Warning System

Status: planning document. No ML or data-ingestion code is written in this step. This roadmap
sequences the work already scoped in `docs/data_source_inventory.md` and
`docs/architecture/*` into an executable, two-phase plan with explicit gates.

**Guiding principle**: Phase 1 must stand alone as a complete, honest, defensible resume project
even if Phase 2 never happens. Nothing in Phase 1 depends on Phase 2 existing. Phase 2 depends
entirely on Phase 1 being done, reproducible, and evaluated honestly — including the honest
possibility that the ML model does not beat the baselines, which is itself an acceptable Phase 1
outcome as long as it is measured and reported correctly (see Gate D).

---

## 1. Phase Gates

These are hard checkpoints, not milestones to note in passing. A gate that fails sends work back
to the task group behind it, not forward past it.

| Gate | Condition to pass | Evidence required |
|---|---|---|
| **A — Data feasibility** | The core monthly target-side datasets (MPI, CapU, export, PPI) and the Dependency Matrix source (I-O table) are each either verified-accessible or have a documented, non-fabricated manual fallback | An updated `data_source_inventory.md` with every MVP-critical row moved out of "Needs verification," or an explicit fallback recorded per §8 (Risks) |
| **B — Target validity** | The Industry Stress Index, computed only from information dated at or before each period's own `available_as_of`, visibly rises during at least one independently-known past stress episode for the relevant industry (e.g., 2020 COVID, a confirmed energy-price shock) | A dated case-study note comparing the computed stress score's trajectory against the known episode, with the feature-cutoff logic active (not a lookback shortcut) |
| **C — Baseline integrity** | Every baseline (historical mean, persistence, seasonal, regularized linear regression, simple tree) runs under the identical time split and the identical point-in-time data-availability rule as the MVP model | One evaluation table with all baselines and the MVP model side by side, same test window, same feature-availability constraints |
| **D — MVP model value** | The selected tree-based model improves at least one early-warning metric (recall or precision for High/Severe, macro F1, or missed-event rate) over the persistence baseline on the **untouched test period**, without an unacceptable rise in false-alert rate | The Phase 1 evaluation report (§4), test-period numbers only — not validation numbers |
| **E — Advanced-method justification** | The full MVP (data → features → targets → baselines → model → evaluation → dashboard → docs) is reproducible end-to-end from the documented commands | A clean re-run log plus the Phase 1 Definition of Done (§9) fully checked off |

Gate D explicitly does **not** require the ML model to win. If it does not beat the persistence
baseline, that is a valid, reportable Phase 1 result — the task instruction "do not assume an
advanced model is useful unless it beats baselines" cuts both ways: a documented loss is honest
work, an undocumented or untested win-by-assumption is not.

---

## 2. Phase 1 — MVP Work Breakdown Structure

Grouped by the gate each group feeds. Task IDs encode order; within a group, tasks are listed in
dependency order. Difficulty: **Low / Medium / High**.

### Group A — Data Foundation (feeds Gate A)

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| A1 | Resolve the MVP-critical "Needs verification" items from the data source inventory: OIE MPI/CapU bulk-access mechanism, MOC export bulk/API export, NESDC I-O latest edition year and sector list, BOT API auth flow on the new portal | Updated rows in `data_source_inventory.md`; each MVP source reclassified `verified_live` or given a documented fallback | — | High (two sources are currently bot-blocked; this is manual, not automatable) |
| A2 | Populate `data/mapping/hs_to_industry.csv` and `data/mapping/io_sector_to_industry.csv` with real codes once A1 resolves the underlying classifications | Filled mapping tables, still hand-reviewable in Git | A1 | Medium |
| A3 | Build `raw/` ingestion for the MVP source set — automated where verified with no auth (FRED, World Bank Pink Sheet), scripted-manual where official but bot-blocked or auth-gated (OIE, NESDC, BOT) | Ingestion scripts/notebooks per `source_id`; retrieval manifest entries | A1 | Medium |
| A4 | Build `interim/` parsers per source: standardize columns, attach `reference_period`, `release_date`, `available_as_of`, `retrieved_at`, `source_revision`, `source_url` per `data_architecture.md` §3 | One parser per source, one Parquet output per source | A3 | Medium |
| **Gate A checkpoint** | Confirm the minimum viable source set (§ MVP dataset in the inventory) is actually flowing into `interim/` | Sign-off note in this roadmap's decision log entry | A1–A4 | — |

### Group B — Target Construction (feeds Gate B)

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| B1 | Implement the Raw Industry Stress Index formula from the target-design phase (winsorized, industry-standardized component blend, `0.6·max + 0.4·mean`) | A pure function, unit-testable independent of the pipeline | A4 | Medium |
| B2 | Build `processed/industry_month_panel.parquet` by joining `interim/` sources through `mapping/` | Populated processed table matching the schema in `data_contract_industry_month_panel.md` | A4, A2 | Medium |
| B3 | Compute `stress_score_1m` (`S(i,t+1)`) and `stress_score_3m` (`max[S(i,t+1..t+3)]`), with `contributing_periods` recorded for the 3-month max | `targets/industry_month_targets.parquet` | B1, B2 | Medium |
| B4 | Fit `risk_level` thresholds on the training partition only (percentiles 60/85/97) and apply them; implement the absolute-floor gate for `Severe` from the target-design phase | Populated `risk_level` column, persisted threshold object in a run manifest | B3, E1 (needs the split boundary first) | Medium |
| B5 | **Gate B checkpoint**: validate the stress index against at least one known historical stress episode, using only cutoff-respecting data | Case-study note; a chart is optional but the underlying data must be point-in-time correct | B1–B3 | Medium |

### Group C — Dependency Matrix (parallel to B; needs A's I-O source)

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| C1 | Build the static 12×12 Dependency Matrix from the I-O table via `io_sector_to_industry.csv` | A 12×12 numeric matrix (industry × industry), stored alongside `mapping/` | A2 | High (blocked on the I-O edition/sector-list verification from A1) |
| C2 | Sanity-check the matrix against known real linkages (e.g., IND-04 Refined Petroleum should show measurable weight into IND-06 Rubber and Plastics; IND-09 Electronics should show measurable import-dependency, consistent with the OIE press-release evidence already gathered) | Short validation note | C1 | Low |

### Group D — Feature Engineering (feeds Gate C/D)

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| D1 | Implement the point-in-time feature builder (`feature_cutoff`, per-source `available_as_of` filter) exactly per the pseudocode in `data_architecture.md` §8 | `features/industry_month_features.parquet` | B2 | Medium |
| D2 | Engineer features per external-shock category from the MVP source set: energy (Brent level/change), raw material (World Bank Pink Sheet relevant series), FX (USD/THB), trading-partner proxy if available | Additional feature columns, each following the `<name>_value` / `<name>_asof` convention | D1 | Medium |
| D3 | Implement the data-quality validation rules from `data_architecture.md` §10 as actual automated checks (not just documentation) — at minimum rules 1–6 and 12–13 | A runnable validation script with a pass/fail report | D1, B2 | Medium |
| **Gate C prerequisite** | D1–D3 must run under the same split boundaries as baselines will use | — | E1 | — |

### Group E — Splits and Baselines (feeds Gate C)

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| E1 | Fix the train / validation / test boundaries once the earliest common start date is resolved (currently unverified per the data source inventory — this task cannot fully close until A1 resolves the MPI series continuity question) | Recorded split dates in a `model_input/<run_id>/manifest.yaml` | A1, B2 | Medium |
| E2 | Implement baseline models: historical mean, last-observed/persistence, seasonal baseline (if a seasonal pattern is confirmed relevant per industry), regularized linear regression (Ridge or Lasso), a simple tree baseline (shallow decision tree) | One evaluation-ready prediction table per baseline | D1, E1 | Low |
| E3 | Run every baseline under identical split/availability rules; assemble the comparison table | Baseline comparison table (regression + early-warning metrics, §4) | E2 | Low |
| **Gate C checkpoint** | Confirm no baseline was accidentally given information a real-time model would not have had | Manual review against `data_architecture.md` §10 rules 5 and 9–11 | E3 | — |

### Group F — MVP Model (feeds Gate D)

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| F1 | Select and implement one tree-based model (gradient boosting, e.g. LightGBM/XGBoost, or Random Forest as a lower-complexity alternative) for both horizons | Trained model artifact(s), one per horizon (or one multi-output model if the library supports it) | E1, D3 | Low–Medium |
| F2 | Hyperparameters chosen from a small, hand-justified grid, validated on the validation partition only — explicitly avoid an unconstrained automated search, consistent with the over-fitting risk this project's own reference-paper review flagged for exactly this kind of small-N panel | A short note listing the grid and the chosen values, plus validation-period scores for each candidate | F1 | Low |
| F3 | Implement walk-forward / rolling-origin evaluation (refit on an expanding or rolling window, forecast forward, never fit past the point being scored) | Evaluation harness, reusable for both baselines and the MVP model | E1 | Medium |
| F4 | Score the finalized model on the untouched test period once, computing every metric in §4 | Test-period metrics table | F1–F3 | Low |
| **Gate D checkpoint** | Compare F4's test metrics against E3's baseline metrics; confirm improvement on at least one early-warning metric without an unacceptable false-alert increase, OR document that no such improvement was found | Final comparison table + one-paragraph honest verdict | E3, F4 | — |

### Group G — Explainability

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| G1 | Extract built-in feature importance from the tree model per horizon | Ranked feature-importance table/chart | F1 | Low |
| G2 | Produce a per-prediction "main contributing factors" output (top-N features by importance × deviation-from-normal, per industry-month) satisfying the project goal's explicit "main factors contributing to the warning" output | A row-level explanation table joinable to `targets/` predictions | G1, D2 | Medium |

SHAP-based explanations are explicitly **not** required for the MVP (§5, excluded items) — built-in
tree importance plus G2's simple contribution ranking is sufficient to satisfy the "explainable, not
just a prediction score" requirement carried since the project's first design turn.

### Group H — Dashboard

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| H1 | Build a simple interactive dashboard (Streamlit recommended: Python-native, no separate frontend build, fast to stand up for a portfolio project) showing a 12-industry × time risk-level view, per-industry stress-score trend, and the Dependency Matrix | Runnable dashboard app | F4, G2, C1 | Low–Medium |
| H2 | Dashboard reads only from versioned `model_input`/prediction output tables — no live recomputation, so the dashboard cannot silently drift from the evaluated model | Confirmed in code review, not just described | H1 | Low |

### Group I — Reproducibility and Documentation

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| I1 | Reproducible commands: a small CLI or a `Makefile`/task-runner exposing `data`, `features`, `targets`, `train`, `evaluate`, `dashboard` steps | Documented commands that work from a clean checkout given the raw-data prerequisites | A–H complete | Low |
| I2 | README documentation appropriate for recruiters: problem statement, method summary (including the explicit, honest adaptation notes from the reference paper), architecture diagram or link, headline results (with the caveat if the model did not beat baseline), how to run, repository map | Updated top-level `README.md` | I1, F4 | Low |
| I3 | Final MVP acceptance review against the Phase 1 Definition of Done (§9) | Sign-off note | all above | — |

---

## 3. Phase 1 Acceptance Criteria (by milestone)

| Milestone | Criteria |
|---|---|
| Gate A passed | MVP source set flowing into `interim/`; no fabricated classification codes anywhere in `mapping/` |
| Gate B passed | Stress index rises visibly during at least one known historical episode, using only cutoff-legal data |
| Gate C passed | All baselines and the MVP model share identical split boundaries and availability rules, confirmed by code review against the validation rules, not by assumption |
| Gate D passed (or honestly failed) | Test-period comparison table exists and is the basis of any claim of improvement — no claim is made from validation-period numbers |
| Dashboard milestone | Dashboard renders all 12 industries, both horizons, and links each Watch/High/Severe cell to its top contributing factors |
| Documentation milestone | A reader unfamiliar with the project can run the pipeline from the README alone |

---

## 4. Phase 1 Evaluation Metrics (reference)

Regression: MAE, RMSE, Spearman rank correlation across the 12 industries (per prediction date), error broken out by industry, error broken out by horizon (1-month vs. 3-month).

Early-warning: recall for {High, Severe} combined, precision for {High, Severe} combined, macro F1
across all four risk levels, false-alert rate (predicted Watch/High/Severe when actual was Normal),
missed-event rate (predicted Normal/Watch when actual was Severe), average warning lead time where
measurable (requires knowing how many months before a Severe reference_period the model first
raised the risk level — only computable retrospectively, on realized history).

All of the above are computed on the untouched test period and reported against the persistence
baseline, not in isolation.

---

## 5. Items Explicitly Excluded from the MVP

- Deep learning or graph neural networks of any kind.
- Any Phase 2 item (§6) by definition.
- SHAP or other post-hoc explainability libraries — built-in tree importance plus the simple
  contribution ranking (G2) is the MVP bar.
- Automated, scheduled monthly data refresh — MVP ingestion may be run manually.
- Paid data sources of any kind (full PMI history, Freightos paid tier, CEIC/Statista as pipeline
  inputs) — consistent with the confirmed source-priority policy.
- Company- or stock-level prediction — out of scope since the project's original framing.
- Uncertainty intervals / probability calibration.
- Dynamic (time-varying) dependency structure — the MVP Dependency Matrix is static.

---

## 6. Phase 2 — Advanced Extensions Work Breakdown Structure

Begins only after Gate E passes. Tasks are grouped, not strictly ordered against each other except
where a dependency is noted — a team could reasonably reorder within Phase 2 based on what Phase 1
revealed as most valuable.

| ID | Task | Deliverable | Depends on | Difficulty |
|---|---|---|---|---|
| P2-1 | Dynamic Shock Transmission Matrix: a 12×12 matrix per period built from a Markov chain over discretized risk states, adapting the reference paper's transition-matrix construction | Time-stacked transmission matrices, one estimation window at a time | Phase 1 complete | High |
| P2-2 | Conditional transition probabilities using covariates (log-linear/conditional-logit form, per the reference paper's Markov-chain-with-covariates method) | Conditioned transition model, walk-forward refit | P2-1 | High |
| P2-3 | Distance Matrix between industry stress dynamics (arccos-of-correlation style geometry, adapted from the reference paper's distance-matrix construction, applied to the 12-industry stress series rather than stock returns) | 12×12 distance matrix per period | Phase 1 complete | Medium–High |
| P2-4 | Network centrality / upstream-vulnerability features derived from P2-3 and the static Dependency Matrix (C1) | New feature columns, re-evaluated through the same walk-forward harness (F3) — not just added and assumed helpful | P2-3, C1 | Medium |
| P2-5 | Lead-lag / transfer-entropy analysis between candidate covariates and the risk-state process (adapting the reference paper's transfer-entropy diagnostic) | Directional-influence report per covariate; explicit small-sample caution given only 12 industries (flagged as a real risk in this project's earlier target-design phase) | Phase 1 complete | High |
| P2-6 | Dynamic dependency adjustment: let the Dependency Matrix (C1) update on a rolling basis rather than stay static | Time-varying dependency matrix, with a documented re-estimation cadence | P2-1, C1 | Medium–High |
| P2-7 | Advanced gradient boosting or temporal models (e.g., a properly tuned GBM variant, or a simple sequence model) compared under the *same* walk-forward harness as the Phase 1 tree model | A new evaluation row added to the Phase 1 comparison table — not a separate, incomparable report | F3 | Medium |
| P2-8 | Graph-based models — **gated**: only attempted if a data-volume justification is documented first (12 nodes is a small graph; a GNN's usual sample-efficiency advantage is unlikely to apply here) | Either a justified graph-model result, or a written decision *not* to pursue this, which is itself an acceptable Phase 2 deliverable | P2-4 | High (and possibly not justified — see §7 risk R-8) |
| P2-9 | Uncertainty intervals and probability calibration (e.g., conformal prediction or calibrated quantile outputs on the stress score) | Calibrated interval outputs, with a calibration-quality check (e.g., reliability diagram) | Phase 1 complete | Medium |
| P2-10 | Automated monthly data refresh (scheduled ingestion, replacing Group A's manual scripts where the underlying source allows it) | A scheduled job definition; explicitly excludes the sources still bot-blocked as of this roadmap unless independently re-verified | Phase 1 complete, A1's blocked sources re-checked | Medium |
| P2-11 | Historical shock case studies (narrative write-ups pairing known real events — e.g., 2011 floods, 2020 COVID, a confirmed energy-price shock — against the system's retrospective output) | 2–4 written case studies, portfolio-narrative quality | Phase 1 complete, B5's case-study method reused | Low–Medium |

---

## 7. Major Risks and Fallback Options

| ID | Risk | Likelihood | Fallback |
|---|---|---|---|
| R-1 | NESDC I-O table stays bot-blocked or its latest edition year is never confirmed | Medium–High (already observed this session) | Use the older, by-name-confirmed edition (e.g. the "I/O 2000" page found during the feasibility study) with an explicitly documented staleness caveat, or fall back to a coarser aggregation level; as a last resort, a domain-expert-assigned qualitative dependency matrix, clearly labeled as a proxy and never presented as I-O-derived |
| R-2 | OIE's own MPI sub-group-to-TSIC crosswalk is never published | Medium | Manually cross-reference OIE's monthly press releases (which do name specific sub-industries, as already confirmed) against TSIC divisions; record each mapping's confidence explicitly in `hs_to_industry.csv`-style `mapping_status` |
| R-3 | Earliest common start date for the target series turns out to be short, leaving too few months for a meaningful train/validation/test split | Medium | Shrink the number of `risk_level` classes (e.g., merge High and Severe) to increase per-class sample size; widen reported confidence intervals; lean more on the baseline comparison than on model sophistication |
| R-4 | PMI / logistics feature sources remain paid or unverified | High (already observed) | Drop from the MVP feature set entirely (already the plan); revisit in Phase 2 only if a free official source is later found |
| R-5 | The tree-based model does not beat the persistence baseline (Gate D "honest failure" case) | Medium | This is an acceptable MVP outcome per Gate D's own definition — document it, explain the likely reason (e.g., insufficient history, weak external-shock signal at this level of aggregation), and still ship the rest of the MVP (dashboard, docs) around the honest result |
| R-6 | `Severe` class has too few historical examples for any reliable recall/precision estimate | High (flagged since the target-design phase) | Report Severe metrics with explicit sample-size caveats; consider a combined {High, Severe} evaluation as the headline early-warning metric instead of Severe alone |
| R-7 | EPPO and other bot-protected sources block even the manual-fallback ingestion path long-term | Low–Medium | Use the data.go.th mirror confirmed reachable during the feasibility study, or accept a lower-frequency manual download cadence as a documented operational limitation, not a blocker |
| R-8 | Phase 2 graph-based models get attempted "because it sounds advanced" rather than because the data supports them | Managed by process, not chance | P2-8 is explicitly gated on a written data-volume justification before any implementation begins; the default expectation, stated here directly, is that 12 nodes likely does **not** justify a GNN |

---

## 8. Recommended Git Commit Sequence

One reviewable unit per commit, in dependency order. Scaffold commits already exist informally as
files on disk from the architecture-design step; the sequence below assumes those are committed
first as the baseline.

1. `chore: initial repository scaffold (config, schemas, empty data layers, architecture docs)`
2. `docs: data source feasibility study`
3. `docs: data architecture, data contract, decision log`
4. `docs: project roadmap` *(this document)*
5. `feat(mapping): finalize industry_map and resolve MVP-critical source verification (A1, A2)`
6. `feat(ingestion): raw retrieval for verified no-auth sources (FRED, World Bank Pink Sheet)` (A3, partial)
7. `feat(ingestion): raw retrieval for OIE/MOC/NESDC/BOT sources (manual-fallback paths)` (A3, remainder)
8. `feat(interim): source parsers with temporal-field attachment` (A4)
9. `feat(processed): industry-month panel builder` (B2)
10. `feat(targets): stress index and 1m/3m target construction` (B1, B3)
11. `test(targets): historical stress-episode validation case study` (B5, Gate B evidence)
12. `feat(mapping): 12x12 static dependency matrix from I-O table` (C1, C2)
13. `feat(features): point-in-time feature builder and cutoff enforcement` (D1, D2)
14. `test(quality): automated data validation rules` (D3)
15. `feat(splits): time-based train/validation/test boundaries` (E1)
16. `feat(baselines): historical mean, persistence, seasonal, ridge, shallow tree` (E2, E3)
17. `feat(model): tree-based MVP model with walk-forward evaluation` (F1–F4)
18. `feat(explainability): feature importance and per-prediction contribution ranking` (G1, G2)
19. `feat(dashboard): Streamlit MVP dashboard` (H1, H2)
20. `chore: reproducible run commands` (I1)
21. `docs: recruiter-facing README with headline results` (I2)
22. `chore: Phase 1 MVP tag` — e.g. `v1.0-mvp`, marking the reproducible state Gate E checks against

Phase 2 commits follow the same one-unit-per-task pattern against `P2-*` task IDs, each compared
back to the Phase 1 evaluation table rather than reported in isolation.

---

## 9. Definition of Done — Phase 1

Phase 1 is done when **all** of the following hold:

1. Every MVP data source is either verified-live or has a documented, non-fabricated fallback (Gate A).
2. The Industry Stress Index passes its historical-episode sanity check (Gate B).
3. `data/mapping/` contains no invented official codes — only verified codes or explicit
   `IO-PENDING-xx`-style internal placeholders, consistent with the architecture's identifier policy.
4. All required baselines (historical mean, persistence, seasonal where relevant, regularized
   linear regression, simple tree) run under identical time-based splits and identical
   point-in-time availability rules as the MVP model (Gate C).
5. The MVP tree-based model has been scored exactly once on the untouched test period, and that
   scoring — win, loss, or draw against the persistence baseline — is reported honestly (Gate D).
6. Feature importance and a per-prediction "main contributing factors" output exist for every
   Watch/High/Severe prediction.
7. A dashboard runs locally, showing all 12 industries and both horizons, sourced from versioned
   output tables only.
8. The full pipeline is runnable end-to-end from documented commands on a clean checkout (given the
   raw-data prerequisites).
9. The README is written for a recruiter audience: it states the problem, the method (with the
   explicit reference-paper adaptation notes), the honest headline result, and how to reproduce it.
10. No random train/test splitting, no scaler/threshold fit on non-training data, and no rolling
    window that reads forward exist anywhere in the shipped code — verified by the data-quality
    validation suite (D3), not merely by design intent.

Phase 1 being "done" does **not** require the ML model to have beaten the baseline. It requires the
comparison to have been made correctly and reported honestly.

---

## 10. Definition of Done — Phase 2

Phase 2 is done, for whichever subset of P2-1..P2-11 was pursued, when:

1. Gate E's precondition held at the start: the Phase 1 MVP was fully reproducible before any
   Phase 2 work began.
2. Every Phase 2 model or feature addition was evaluated through the *same* walk-forward harness
   and test period discipline as Phase 1 (P2-7's explicit requirement, applied project-wide) — no
   Phase 2 result is reported in a separate, incomparable evaluation setup.
3. Every Phase 2 result is compared back to the Phase 1 baseline/MVP comparison table, not reported
   as if Phase 1 did not exist.
4. Graph-based methods (P2-8) were either justified in writing by a data-volume argument before
   implementation, or explicitly not pursued, with that decision documented.
5. Any new external data source introduced in Phase 2 follows the same source-priority policy
   (official Thai first, then authoritative international, no paid/proprietary/social-media/news
   datasets) as Phase 1.
6. Case studies (P2-11), if produced, reference real, independently-known events — never a
   synthetic or assumed scenario.
7. The roadmap's decision log is updated to close out whichever `AD-*` items (from
   `docs/architecture/decision_log.md`) each Phase 2 task resolved.

---

## 11. Unresolved Decisions Carried Into Implementation

These are decisions this roadmap deliberately leaves open, cross-referenced to
`docs/architecture/decision_log.md` where the same item already appears:

- Earliest common monthly start date for the target series (blocks finalizing E1's split
  boundaries) — AD-05-adjacent, tracked here as a Group A/E blocker specifically.
- NESDC I-O latest edition year and sector list (blocks C1) — AD-05.
- OIE MPI sub-group crosswalk to TSIC (blocks A2's full population of `hs_to_industry.csv`-style
  confidence) — new item, not previously logged; should be added to the decision log as AD-10.
- Whether a seasonal baseline is actually warranted per industry (some of the 12 groups plausibly
  have real seasonality — e.g. agro-adjacent food processing — others likely do not) — a Group E
  task-level decision, not yet made.
- Exact library choice for the tree-based MVP model (LightGBM vs. XGBoost vs. scikit-learn Random
  Forest) — a Group F implementation detail, deliberately left open here since it does not affect
  the architecture.
- Whether G2's "main contributing factors" output is computed per-industry-month at prediction time
  or only on demand in the dashboard — affects H1's design slightly, not yet decided.

---

## 12. Report

**Files created**: `docs/project_roadmap.md` (this file). No other files were created or modified —
the existing repository (`config/`, `data/`, `docs/data_sources/`, `docs/architecture/`, `schemas/`,
`.gitignore`, `README.md`) was inspected first and left untouched, per this task's instruction.

**Unresolved decisions**: see §11 above, plus the carried-over items already logged in
`docs/architecture/decision_log.md` (AD-01 through AD-09).

**Recommended next single action**: start Group A, task A1 — resolve the MVP-critical data-access
questions (OIE MPI/CapU access mechanism, MOC export bulk export, NESDC I-O edition/sector list,
BOT API auth flow). Every other task in Phase 1 either directly depends on A1 or depends on
something that does; there is no productive parallel work available until at least the target-side
and dependency-matrix data questions are answered.
