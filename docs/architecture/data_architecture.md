# Data Architecture — Thai Supply Chain Shock Early Warning System

Status: design document only. No data has been downloaded in bulk, no pipeline code has been
written, no model has been trained. This document is the artifact to be reviewed before any of
that begins.

This architecture builds directly on three prior design decisions in this project:

- **Target design**: `stress_score_1m(i,t) = S(i,t+1)`, `stress_score_3m(i,t) = max[S(i,t+1),
  S(i,t+2), S(i,t+3)]`, each converted to a 4-level `risk_level` (Normal/Watch/High/Severe) via
  training-only thresholds.
- **Industry taxonomy**: 12 manufacturing industry groups, built from TSIC 2009 Section C
  (Divisions 10–33, verified against the official TSIC 2009 document), with TSIC Division 12
  (tobacco) still unassigned — carried into this architecture as an open mapping item.
- **Data source inventory**: a 19-source feasibility study with per-source verification status
  (see `docs/data_source_inventory.md`). This architecture treats every source's
  verification status as a first-class field, not an afterthought — a source marked "Needs
  verification" is wired into the same schema as a verified one, but its `available_as_of` values
  must be treated as provisional until confirmed.

---

## 1. Reference period vs. release date — the core distinction this architecture is built around

Two dates describe every time-varying observation, and they are not the same date, and the gap
between them is the entire reason a `raw` → `interim` → `processed` pipeline with explicit temporal
fields exists at all:

- **The month an observation describes** (`reference_period`): the calendar period the number is
  *about*. Example: "Manufacturing Production Index for March 2024" — `reference_period = 2024-03`.
- **The date the observation became knowable** (`release_date` / `available_as_of`): the calendar
  date on which that number was actually published and could have entered a model that was run in
  real time. Example, confirmed directly from an OIE press release read during the feasibility
  study: the March 2024 MPI figure was explicitly dated "ข้อมูล ณ วันที่ 30 เมษายน 2567" (data as of
  30 April 2024) — so `reference_period = 2024-03-01`, `release_date ≈ 2024-04-30`, a ~30-day gap.

A model making a prediction "as of" some date `t` can only ever see observations whose
`available_as_of <= t`. Collapsing the two dates into one — or worse, silently defaulting a missing
`release_date` to `reference_period` — is exactly the mechanism by which look-ahead bias enters a
panel that *looks* like a clean monthly time series but secretly lets March data answer a question
asked in March. This is why `available_as_of` is mandatory and why a missing value for it must
block the record from entering `features/`, not be silently filled in (see §9, restriction list).

---

## 2. Data layers

| Layer | Purpose | Grain | Format |
|---|---|---|---|
| `raw` | Byte-identical copy of what was retrieved, no parsing, no correction | one file/response per retrieval event | original format (PDF/XLSX/CSV/JSON, whatever the source returns) |
| `interim` | Parsed, standardized, one table per source, still atomic (no cross-source joins) | one row per (`source_series_id`, `industry_id` if applicable, `reference_period`, `retrieved_at`) | Parquet (numeric long panels) or CSV (small sources) |
| `mapping` | Classification crosswalks: HS, TSIC, I-O sector, country, commodity, industry | one row per mapped code | CSV (tabular many-to-one/many-to-many) or YAML (small structured lists) |
| `processed` | The monthly industry panel — one analytical table joining all sources by `(industry_id, reference_period)` | one row per (`industry_id`, `reference_period`) | Parquet |
| `features` | Leakage-safe model features, built with an explicit `cutoff_date` per row | one row per (`industry_id`, `prediction_date`) | Parquet |
| `targets` | Future Industry Stress Score targets, per horizon | one row per (`industry_id`, `prediction_date`, `horizon`) | Parquet |
| `model_input` | Versioned, joined, time-split training/inference tables | one row per (`industry_id`, `prediction_date`, `horizon`), partitioned into train/validation/test | Parquet, one immutable directory per `run_id` |

### Format recommendation

- **`raw`**: kept exactly as downloaded — never converted. This is the immutability guarantee the
  whole architecture depends on for reproducibility and for revision-auditing (§7).
- **CSV** for anything a human will routinely open, diff in a pull request, or hand-edit: the
  `mapping/` layer, and small config-adjacent reference tables. CSV's plain-text diffability in
  Git is a real advantage for a project where classification mappings will be corrected by hand as
  "Needs verification" items get resolved.
- **Parquet** for `interim`, `processed`, `features`, `targets`, `model_input`: typed, columnar,
  compact, and read natively by pandas/polars/DuckDB without a schema-guessing step the way CSV
  requires. This matters once the panel has repeated numeric columns per source variable plus
  several temporal columns each (§3) — CSV would work but wastes space and loses dtype fidelity
  (e.g., a date silently becoming a string).
- **YAML** for `config/` — human-readable, comments allowed, natural fit for nested settings
  (horizon definitions, source registries).
- **Lightweight database**: recommend **DuckDB** as an *optional* query layer over the Parquet
  files (embedded, zero-server, reads Parquet directly, plays well with a laptop-scale student
  project) — not as a replacement for the file layers. It is the right tool for ad-hoc joins across
  `processed` + `mapping` while prototyping the Dependency/Transmission/Risk-State matrices,
  without introducing a database server to operate. Treat this as optional tooling, not a required
  architectural layer — the file-based layers above are the source of truth regardless of whether
  DuckDB is used to query them.

---

## 3. Mandatory temporal fields — applied per layer

| Field | Meaning | Present in `interim` | Present in `processed` |
|---|---|---|---|
| `reference_period` | the month the value describes | yes | yes (part of primary key) |
| `release_date` | the date the source provider published this value | yes | no (kept in `interim` only — see below) |
| `available_as_of` | the date the value could first have been used in a real-time model — usually equal to `release_date`, but may lag it further if the pipeline itself only checks the source periodically | yes | **yes**, mirrored per source variable (`mpi_available_as_of`, `capu_available_as_of`, …) — this is the one field promoted to the wide table because it is the field the point-in-time cutoff logic (§8) actually needs at query time |
| `retrieved_at` | when *this project's* pipeline actually fetched the value | yes | no (audit trail lives in `interim` and `raw` manifests) |
| `source_revision` | a version/vintage marker if the provider revises published values | yes | no (see §7 — revision handling stays in `interim`; `processed` carries only the vintage selected by the project's stated revision policy) |
| `source_url` | the exact URL/endpoint the value came from | yes | no |

Design rationale for **why `processed` doesn't carry all six fields per variable**: `processed` is a
wide analytical table with potentially a dozen-plus source variables per industry-month. Repeating
five metadata columns per variable there would make the table unwieldy without adding traceability
value beyond what `interim` already provides — anyone needing the full audit trail for a given
value joins back to `interim` on `(source_series_id, industry_id, reference_period)`. Only
`available_as_of` earns a place in the wide table because §8's cutoff logic queries it directly and
repeatedly; making it a join-time lookup would be needlessly slow and error-prone for something
checked on every feature-construction call.

---

## 4. Core identifiers

None of the following are invented official codes. Where an official classification was actually
verified this project (TSIC divisions, ISO country codes), it is used directly. Where it was not
verified (OIE's own MPI reporting-group codes, NESDC's I-O sector codes), an explicitly
project-internal identifier is used instead, and the field name and a `mapping_status` column make
that distinction impossible to miss downstream.

| Identifier | Scheme | Source of truth | Status |
|---|---|---|---|
| `industry_id` | Project-internal, stable, never renumbered: `IND-01` … `IND-12` | This project's taxonomy design (prior turn), built from TSIC 2009 divisions | Internal identifier — TSIC divisions are official (verified); the 12-group aggregation itself is this project's own design choice, not an official OIE or NSO grouping |
| `industry_name` | Free text, `_en` and `_th` variants, versioned (a rename is a new row in a small history table, not an overwrite) | This project | Internal |
| `source_series_id` | Kept **exactly as the provider names it** — e.g. `DCOILBRENTEU` (FRED), a World Bank Pink Sheet column header verbatim, an OIE dataset resource ID once confirmed | Provider | Official, verbatim — never reformatted |
| `country_code` | ISO 3166-1 alpha-3 (e.g. `THA`, `CHN`, `USA`) | ISO standard | Official — safe to use directly, this is a real, stable, well-documented external standard, not a project invention |
| `commodity_id` | Project-internal: `COMM-xxxx`, mapped 1:1 to the exact World Bank Pink Sheet column name (kept verbatim in a `source_label` field) | This project, wrapping the World Bank's own (unstandardized-code) commodity names | Internal — World Bank Pink Sheet commodities are named, not numerically coded, so there is no official code to defer to |
| `hs_code` | Stored exactly as provided, **with an explicit `hs_level` field** (2/4/6/11-digit) since Thai national HS extends the 6-digit international HS to 11 digits | Provider (MOC/Customs) | Official, verbatim — never truncated or reformatted without recording the original level |
| `io_sector_code` | **Pending.** Placeholder scheme `IO-PENDING-xx` until NESDC's actual sector code list and latest edition year are confirmed (flagged Needs verification in the data source inventory) | NESDC, once confirmed | Internal placeholder — must not be presented as an official NESDC code until verified |

---

## 5. Proposed repository structure

```
thai-supply-chain-ews/
├── .gitignore
├── README.md
├── config/
│   ├── project.yaml
│   ├── paths.yaml
│   ├── industries.yaml
│   ├── sources.yaml
│   └── horizons.yaml
├── data/
│   ├── raw/
│   │   └── <source_id>/<retrieved_at_date>/<original_filename_or_response>
│   ├── interim/
│   │   └── <source_id>/<source_id>.parquet
│   ├── mapping/
│   │   ├── industry_map.csv
│   │   ├── hs_to_industry.csv
│   │   ├── io_sector_to_industry.csv
│   │   ├── commodity_to_industry.csv
│   │   └── country_reference.csv
│   ├── processed/
│   │   └── industry_month_panel.parquet
│   ├── features/
│   │   └── industry_month_features_<schema_version>.parquet
│   ├── targets/
│   │   └── industry_month_targets_<schema_version>.parquet
│   └── model_input/
│       └── <run_id>/
│           ├── manifest.yaml
│           ├── train.parquet
│           ├── validation.parquet
│           └── test.parquet
├── schemas/
│   ├── industry_month_panel.schema.yaml
│   ├── features_table.schema.yaml
│   └── targets_table.schema.yaml
└── docs/
    ├── data_sources/
    │   └── data_source_inventory.md        (prior deliverable)
    └── architecture/
        ├── data_architecture.md            (this document)
        ├── data_contract_industry_month_panel.md
        └── decision_log.md
```

Git policy (`.gitignore`, drafted in §11): `data/raw/`, `data/interim/`, `data/processed/`,
`data/features/`, `data/targets/`, and `data/model_input/` are excluded from version control — they
are regeneratable from `raw` plus code, and `raw` itself can be large. `data/mapping/` **is**
committed — these are small, hand-curated, code-like reference tables, not bulk data, and their
diffs are exactly what a reviewer needs to see when a classification decision changes.

---

## 6. Data flow, source to model

```
[ external provider ]
        |  (verified endpoint or manual download — see data_source_inventory.md)
        v
   data/raw/<source_id>/<retrieved_at>/...         <- immutable, byte-identical, one folder per retrieval
        |  (parse + standardize; attach reference_period, release_date, available_as_of,
        |   retrieved_at, source_revision, source_url)
        v
   data/interim/<source_id>/<source_id>.parquet    <- atomic, one source at a time, long format
        |
        |  <---- data/mapping/*.csv  (HS/TSIC/IO/country/commodity -> industry_id)
        v
   data/processed/industry_month_panel.parquet     <- joined across sources, wide,
        |                                              one row per (industry_id, reference_period)
        |
        |-----------------------------------------------------------------.
        v                                                                 v
   data/features/industry_month_features.parquet         data/targets/industry_month_targets.parquet
   (cutoff-filtered, point-in-time correct;                (built from realized S(i,t+1..t+3);
    see §8 pseudocode)                                      horizon-tagged; threshold-derived
        |                                                    risk_level uses TRAIN-ONLY thresholds)
        '-----------------------------.       .-------------'
                                        v     v
                            data/model_input/<run_id>/
                              manifest.yaml + train/validation/test.parquet
                              (time-based split, §9 — never random)
                                        |
                                        v
                              [ baseline / ML model — out of scope here ]
```

Two things this diagram is deliberately explicit about, because they are the two most common ways
this kind of pipeline silently breaks:

1. **`mapping/` feeds `processed/`, not the other way around.** Classification decisions are
   reviewed and versioned independently of any monthly data refresh.
2. **`features/` and `targets/` are built from the same `processed/` panel but under different
   rules** — `features/` is cutoff-filtered per §8; `targets/` is built from realized future values
   without a cutoff (because at *training* time the future is, by definition, already history) but
   is still not allowed to leak into `features/` for the same or an earlier `prediction_date` (see
   §10, target-leakage control).

---

## 7. Revision handling policy

`raw/` and `interim/` are **append-only**: a new retrieval of a previously-seen `reference_period`
is stored as a new row (or file) with its own `retrieved_at` and `source_revision`, never
overwriting the prior one. `processed/` then applies one explicit, documented vintage policy rather
than silently picking "whatever the last refresh returned":

- **Default policy for `features/` (training-time correctness): first-published vintage.** For a
  given `(source_series_id, reference_period)`, use the value whose `available_as_of` is earliest
  among all recorded vintages — i.e., what a real-time model would actually have seen. This is the
  standard fix for the "vintage data problem" flagged in this project's earlier target-design phase.
- **Optional, clearly separate view for descriptive analysis: latest-revised vintage.** Useful for
  understanding "what really happened," never used to build a training feature.

Both views are derivable from the same append-only `interim/` layer; they are not two separate
ingestion pipelines, only two different `SELECT` policies over one history.

---

## 8. Point-in-time alignment — pseudocode

```
# --- cutoff definition -------------------------------------------------
function feature_cutoff(prediction_date):
    # Convention: a model "run" for month t is assumed to happen at the end of
    # calendar month t. This is a project convention, not a per-source fact —
    # per-source facts (release_date/available_as_of) are what actually gate
    # which values pass the filter below.
    return last_calendar_day(prediction_date)


# --- feature construction (leakage-safe) --------------------------------
function build_feature_row(industry_id, prediction_date, interim_sources, mapping):
    cutoff = feature_cutoff(prediction_date)
    row = { "industry_id": industry_id, "prediction_date": prediction_date,
            "cutoff_date": cutoff }

    for source in interim_sources where source.role == "feature":   # never role == "target"
        candidates = source.records
            .filter(industry_id matches, via mapping if source is not industry-native)
            .filter(available_as_of <= cutoff)                      # <-- the leakage gate
        if candidates is empty:
            row[source.field_name] = null
            row[source.field_name + "_asof"] = null
            continue
        chosen = candidates.max_by(reference_period)   # most recent value legally usable
        assert chosen.available_as_of <= cutoff         # defensive re-check, not just a filter
        row[source.field_name] = chosen.value
        row[source.field_name + "_asof"] = chosen.available_as_of

    return row


# --- target construction (uses realized history; still horizon-scoped) --
function build_target_row(industry_id, prediction_date, horizon, processed_panel):
    if horizon == "1m":
        target_period = prediction_date + 1 month
        value = processed_panel.stress_score(industry_id, target_period)
        contributing_periods = [target_period]

    elif horizon == "3m":
        target_periods = [prediction_date + 1, prediction_date + 2, prediction_date + 3]  # months
        values = [processed_panel.stress_score(industry_id, p) for p in target_periods]
        value = max(values)
        contributing_periods = [p for p, v in zip(target_periods, values) if v == value]
        # record which month drove the max — needed later for explainability,
        # per this project's "results must be explainable" requirement from an earlier phase

    return { "industry_id": industry_id, "prediction_date": prediction_date,
             "horizon": horizon, "stress_score": value,
             "contributing_periods": contributing_periods }
    # risk_level is NOT computed here — it is a separate step (below) that must only ever
    # use thresholds fit on the training partition


# --- risk_level thresholding (train-only, never global) -----------------
function fit_risk_thresholds(targets_table, train_end_date):
    train_rows = targets_table.filter(prediction_date <= train_end_date)
    q60, q85, q97 = percentiles(train_rows.stress_score, [60, 85, 97])
    return { "q60": q60, "q85": q85, "q97": q97, "fit_range_end": train_end_date }
    # this returned object is itself persisted (see manifest.yaml, §5) so that applying it
    # to validation/test later is a lookup, not a recomputation

function assign_risk_level(stress_score, thresholds):
    if stress_score < thresholds.q60: return "Normal"
    elif stress_score < thresholds.q85: return "Watch"
    elif stress_score < thresholds.q97: return "High"
    else: return "Severe"


# --- time-based split (never random) -------------------------------------
function time_based_split(model_input_rows, train_end, validation_end, test_end):
    train = model_input_rows.filter(prediction_date <= train_end)
    validation = model_input_rows.filter(train_end < prediction_date <= validation_end)
    test = model_input_rows.filter(validation_end < prediction_date <= test_end)

    assert max(train.prediction_date) < min(validation.prediction_date)
    assert max(validation.prediction_date) < min(test.prediction_date)
    # any scaler, threshold, or encoding fit anywhere in the pipeline must take
    # train-only rows as input — this assertion is necessary but not sufficient;
    # see §10 for the corresponding validation rule that checks *fitted-parameter*
    # provenance, not just row membership
    return train, validation, test
```

---

## 9. Draft data contract — `processed/industry_month_panel`

Grain: **one row per (`industry_id`, `reference_period`).**

| Column | Type | Nullable | Description |
|---|---|---|---|
| `industry_id` | string | no | PK (part 1). References `mapping/industry_map.csv` |
| `reference_period` | date (first-of-month) | no | PK (part 2). The month this row describes |
| `mpi_value` | float | yes | Manufacturing Production Index level for this industry-month |
| `mpi_available_as_of` | date | yes* | See §3. *Non-null whenever `mpi_value` is non-null — a value with no known availability date must not be populated (§10) |
| `capu_value` | float | yes | Capacity Utilization Rate (%) |
| `capu_available_as_of` | date | yes* | as above |
| `ppi_value` | float | yes | Producer Price Index level |
| `ppi_available_as_of` | date | yes* | as above |
| `export_value_usd` | float | yes | Industry-level export value |
| `export_available_as_of` | date | yes* | as above |
| `vintage_policy` | string | no | `"first_published"` or `"latest_revised"` — which §7 policy produced this row's values (a `processed` table is built under exactly one policy; the two are never mixed within one table) |
| `source_row_refs` | string (JSON array) | no | Pointers back to the `interim` rows this row was built from, for traceability |
| `built_at` | timestamp | no | When this `processed` row was materialized (pipeline audit field, distinct from any source's own temporal fields) |

Additional source variables (energy, commodity, FX, logistics features) follow the identical
`<name>_value` / `<name>_available_as_of` column-pair convention and are appended as they are
onboarded — the schema is designed to grow by column addition, not by redesign, as more sources
from the inventory move from "Needs verification" to "Verified."

Primary key: `(industry_id, reference_period)`. Foreign key: `industry_id` → `mapping/industry_map.csv.industry_id`.

A companion, fuller data contract (with example rows, and the equivalent contracts for `features`,
`targets`, and `model_input`) is kept in
`docs/architecture/data_contract_industry_month_panel.md`.

---

## 10. Data validation rules

| # | Rule | Applies to | Failure action |
|---|---|---|---|
| 1 | `(industry_id, reference_period)` is unique | `processed` | reject/flag duplicate |
| 2 | Every `industry_id` used anywhere exists in `mapping/industry_map.csv` | all layers downstream of `mapping` | reject row |
| 3 | `available_as_of >= release_date >= end_of(reference_period)` when all three are present | `interim` | reject row — a value cannot be available before it was released, or released before the period it describes has ended |
| 4 | A populated `*_value` column never has a null matching `*_available_as_of` | `processed` | reject row (this is the direct implementation of the "missing release_date ≠ reference_period" restriction — a missing availability date blocks the value rather than silently defaulting it) |
| 5 | For every row in `features`, every underlying value's `available_as_of <= cutoff_date` | `features` | reject row; this is the automatable leakage audit, not just a design intention |
| 6 | No `source_series_id` tagged `role: target` in `configs/data.yaml` appears in `features` | `features` | reject at build time |
| 7 | `reference_period` has no unexpected gaps per `industry_id` (or gaps are explicitly recorded, not silently skipped) | `processed` | flag for manual review, do not auto-fill |
| 8 | `stress_score` ∈ [0, 100]; `risk_level` ∈ {Normal, Watch, High, Severe} | `targets` | reject row |
| 9 | Any persisted scaler/threshold object's `fit_range_end` is ≤ the train/validation boundary of the `run_id` it is used in | `model_input` manifest | reject the run |
| 10 | `max(train.prediction_date) < min(validation.prediction_date) < min(test.prediction_date)` (validated, not assumed) after every split | `model_input` | reject the run |
| 11 | No interpolation/fill operation reads a row on the opposite side of a train/validation/test boundary from the row it fills | `features`, `processed` | reject the run |
| 12 | Rolling/trailing window functions only reference `reference_period <= current row's reference_period` (never centered, never forward) | `interim`, `processed` | reject the transform |
| 13 | Revisiting the same `(source_series_id, reference_period)` in `raw` creates a new `retrieved_at` record rather than overwriting | `raw` manifest | reject overwrite |

---

## 11. Draft `.gitignore`

```gitignore
# Bulk/regeneratable data — never committed
data/raw/
data/interim/
data/processed/
data/features/
data/targets/
data/model_input/

# Mapping tables ARE committed (small, hand-curated, code-like) — explicit allow
!data/mapping/

# Local environment / secrets
.env
*.local.yaml

# Standard Python/OS noise
__pycache__/
*.pyc
.DS_Store
```

---

## 12. Matrix compatibility — data shapes required (math deferred to a later step)

| Matrix | Shape | Built from |
|---|---|---|
| **Industry Dependency Matrix** | 12 × 12, static/slowly-changing | `mapping/io_sector_to_industry.csv` aggregating NESDC I-O flows onto the 12 `industry_id`s (blocked on the "Needs verification" I-O edition/sector-list items) |
| **Shock Transmission Matrix** | 12 × 12 per `reference_period` (i.e., a stack of T matrices, or equivalently a long table `(reference_period, industry_from, industry_to, value)`) | `processed/industry_month_panel`'s stress/risk time series per industry, over a trailing estimation window |
| **Industry Risk-State Matrix** | 12 × T (industry × reference_period) | a pivot of `targets/industry_month_targets` (or of `processed`'s realized stress score, for the historical/nowcast reading) |
| **Monthly industry-feature panel (ML)** | 12 × T × F (industry × prediction_date × feature) | `features/industry_month_features`, long or wide |

No transition probabilities, entropy measures, or dependency weights are defined here — only the
tables and shapes that must exist before those can be computed, per this task's scope.

---

## 13. Unresolved architecture decisions

- Whether `processed/industry_month_panel` stays wide (current proposal) or should become long
  once the number of onboarded source variables grows large enough that a wide table becomes
  unwieldy to evolve.
- Whether DuckDB becomes a committed part of the toolchain (for matrix-construction querying) or
  remains optional/exploratory.
- How `oie_group_code` (OIE's own ~45-group MPI classification, still unverified) gets folded into
  `mapping/industry_map.csv` once/if a published crosswalk is found — currently no column reserved
  for it beyond the internal `industry_id`.
- Final resolution of TSIC Division 12 (tobacco) — assign to an existing `industry_id`, create a
  13th, or exclude from scope (carried over from the taxonomy design phase, still open).
- `io_sector_code` scheme is a placeholder until NESDC's latest I-O edition year and sector list
  are confirmed manually (per the data source inventory's open items) — the mapping table's shape
  may need to change once real codes replace `IO-PENDING-xx`.
- Exact confidence-weighting mechanism for many-to-many `hs_to_industry` mappings (a single HS code
  can plausibly feed more than one of the 12 industries) — the column exists in the proposed schema
  (`docs/architecture/data_contract_industry_month_panel.md`) but its computation method is not
  designed yet.
- `run_id` naming/versioning convention for `model_input/` (date-based vs. semantic vs. content-hash
  based) — not yet chosen.
- Whether feature engineering (YoY %, rolling windows, standardization) is computed once in
  `processed/` (available to all feature versions) or per-`features/`-version — currently leaning
  toward keeping `processed/` as raw-ish joined values and doing all transforms in `features/`, but
  not finalized.
- Formal schema enforcement mechanism (e.g., a schema-validation library) is intentionally deferred
  — `schemas/*.yaml` in this proposal are documentation, not yet executable checks.

---

## 14. Recommended implementation order

1. Scaffold the repository structure and `config/*.yaml` files (no data, no code logic yet).
2. Finalize `mapping/industry_map.csv` from the already-verified TSIC 2009 division list; explicitly
   record TSIC Division 12 as unresolved rather than silently omitting it.
3. Build the `raw` → `interim` path for the two fully-verified, no-auth sources first (FRED Brent,
   World Bank Pink Sheet) as a low-risk proof of the pipeline shape, before tackling sources that
   are blocked or unconfirmed.
4. Resolve the manual/"Needs verification" items for OIE, MOC, and NESDC (the target-side and
   dependency-matrix sources) before attempting to automate their ingestion — automating against an
   unconfirmed endpoint risks building on a guess, which this project's sourcing policy explicitly
   rules out.
5. Add `interim` parsers for each source as it moves from "Needs verification" to confirmed.
6. Build `processed/industry_month_panel` once MPI + CapU + at least one external feature source are
   flowing, and wire in the validation rules from §10 from the start rather than retrofitting them.
7. Implement the point-in-time feature builder (§8) and its leakage-audit rule (§10, rule 5).
8. Implement target construction (1-month point, 3-month max) and the train-only threshold fitting
   for `risk_level`.
9. Implement the time-based split and `model_input` versioning/manifest.
10. Only after 1–9 are in place and validated: begin baseline modeling (out of scope for this
    document).
