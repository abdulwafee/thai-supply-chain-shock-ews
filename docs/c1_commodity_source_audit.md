# Task C1 — Upstream Commodity Source Audit

First upstream shock source family: monthly global energy and industrial
raw-material prices from the **World Bank Commodity Price Data ("Pink Sheet")**.

Every number here is read from
[`c1_commodity_source_audit.json`](c1_commodity_source_audit.json) and
[`c1_commodity_ingestion_metadata.json`](c1_commodity_ingestion_metadata.json).
Gate: [`configs/upstream_commodity_sources.yaml`](../configs/upstream_commodity_sources.yaml).

```bash
python scripts/audit_world_bank_commodities.py
python scripts/run_c1_commodity_ingestion.py
```

**This task establishes reproducible source ingestion only.** It does not claim
any series improves forecasting. No feature was engineered, no commodity series
was joined to the target, no target correlation was computed, no model was
trained, and B4's locked test was not touched.

---

## 1. Source resolution and provenance

The download URL was **discovered**, not assumed: the official landing page is
fetched and the `CMO-Historical-Data-Monthly.xlsx` href extracted from its HTML.
This matters because the World Bank rotates a document hash in the path each
month, so last month's URL is not evidence about this month.

| | |
|---|---|
| Landing page | `https://www.worldbank.org/en/research/commodity-markets` |
| Discovery method | `extract_href_from_landing_page_html` (1 candidate URL found) |
| Resolved URL | `https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx` |
| HTTP status | 200 |
| Content-Type | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| Content-Length | 577,979 bytes |
| Last-Modified | Tue, 04 Aug 2026 19:23:23 GMT |
| Raw file | `data/raw/WB_PINKSHEET/2026-08-27/CMO-Historical-Data-Monthly.xlsx` (git-ignored) |
| SHA-256 | `7902a77505ebdc5d202ce65f666c2ee1b04b626f042d7738ed3e6f7d112c8433` |
| Downloaded at (UTC) | 2026-08-27T03:50:59Z |
| Pink Sheet vintage | July-2026 release; workbook states "Updated on August 04, 2026" |
| Manifest | `data/raw/_manifests/WB_PINKSHEET_manifest.jsonl` (tracked, 1 line, idempotent by checksum) |
| License | CC BY 4.0 |

### Sheets inspected

`AFOSHEET`, **`Monthly Prices`** (data), `Monthly Indices`, **`Description`**
(definitions/footnotes), `Index Weights`.

`Monthly Prices` carries 71 labelled series columns over 799 observation rows,
1960-01 through 2026-07. Layout verified rather than assumed: labels on row 4,
units on row 5, data from row 6, period codes like `1960M01` in column 0, and
missing values written as the ellipsis character `…`.

## 2. Candidate audit

Labels below are the workbook's **exact** labels. Note the coal discrepancy:
the task named *"Coal, Australia"*, but the workbook says **"Coal, Australian"**
— the resolved label is what the parser matches on; no silent substitution was
made.

Required window for coverage/missingness is 2020-01 … 2026-05 (77 months).

| Candidate | Exact label | Unit | Coverage | Req. window | Missing | Status |
|---|---|---|---|---|---|---|
| `brent_crude_usd_bbl` | Crude oil, Brent | $/bbl | 1960-01 … 2026-07 (799) | 77/77 | 0.00% | **source_verified** |
| `coal_australia_usd_mt` | **Coal, Australian** | $/mt | 1970-01 … 2026-07 (679) | 77/77 | 0.00% | **conditional** |
| `lng_japan_usd_mmbtu` | Liquefied natural gas, Japan | $/mmbtu | 1977-01 … 2026-07 (595) | 77/77 | 0.00% | **source_verified** |
| `aluminum_usd_mt` | Aluminum | $/mt | 1960-01 … 2026-07 (799) | 77/77 | 0.00% | **source_verified** |
| `copper_usd_mt` | Copper | $/mt | 1960-01 … 2026-07 (799) | 77/77 | 0.00% | **source_verified** |
| `rubber_rss3_usd_kg` | Rubber, RSS3 | $/kg | 1960-01 … 2026-07 (799) | 77/77 | 0.00% | **source_verified** |
| `palm_oil_usd_mt` | Palm oil | $/mt | 1960-01 … 2026-07 (799) | 77/77 | 0.00% | **conditional** |

**5 source_verified, 2 conditional, 0 rejected.** Every candidate has zero
missingness and zero duplicate months in the required window; the two
`conditional` outcomes are caused entirely by documented *semantic* problems,
not by data quality.

### Descriptive statistics

| Candidate | Min | Max | Median | Non-positive | Largest 1-month move | Date |
|---|---|---|---|---|---|---|
| brent_crude_usd_bbl | 1.2 | 133.9 | 24.1 | 0 | 217.1% | 1974-01 |
| coal_australia_usd_mt | 7.8 | 430.8 | 39.5 | 0 | 58.6% | 1975-01 |
| lng_japan_usd_mmbtu | 2.72 | 23.73 | 5.55 | 0 | 54.5% | 1980-01 |
| aluminum_usd_mt | 496.0 | 3666.0 | 1466.0 | 0 | 27.8% | 1988-07 |
| copper_usd_mt | 607.0 | 13552.0 | 2037.0 | 0 | 29.5% | 2008-10 |
| rubber_rss3_usd_kg | 0.29 | 6.26 | 0.98 | 0 | 32.2% | 2008-10 |
| palm_oil_usd_mt | 142.0 | 1777.0 | 500.0 | 0 | 31.5% | 1983-08 |

The largest moves are real historical events — the 1974 oil shock, the 1970s
coal and LNG repricing, the 2008 crash — not data errors. They are **flagged and
kept**: nothing was deleted, clipped or winsorized.

## 3. Definition and unit changes found

Criterion 9 disqualifies a series whose definition or pricing benchmark changed
inside **2021-01 … 2026-05** without resolution. Two candidates trip it.

### `coal_australia_usd_mt` — conditional

The Description sheet states: *"from February 2022, port thermal, f.o.b.
Newcastle, 6000 kcal/kg **futures** price. From 2015 to January 2022, ... 6000
kcal/kg **spot** price."*

The series switches from a **spot** to a **futures** benchmark at the
January/February 2022 boundary — inside the window. Spot and futures prices for
the same physical commodity are not the same quantity, so a level or change
computed across that boundary mixes two definitions.

Detected boundary months: `2022-01`, `2022-02`.

### `palm_oil_usd_mt` — conditional

The Description sheet documents **three** regime changes touching the window:

- January 2021 – October 2024: RBD, FOB Malaysia Ports
- November 2024 – January 2025: 5% Bulk, CIF North West Europe
- from February 2025: Crude, DAP

Detected boundary months: `2021-01`, `2024-10`, `2024-11`, `2025-01`, `2025-02`.
Both the product grade and the delivery basis change, twice, in the middle of
the period this project models.

### Series with changes safely outside the window

Aluminum ("settlement price beginning 2005"; previously cash price) and Rubber
RSS3 (SICOM nearby contract beginning 2004; earlier Singapore/Malaysia RSS1)
both changed well before 2021. Brent and Copper carry no dated change.

### A revision caveat that is not a definition break

The workbook states for LNG (Japan): *"recent two months' averages are
**estimates**."* This does not change the definition, so it does not fail
criterion 9 — but it means the two most recent observations of that series
**will be revised**. It is recorded as the flag
`source_states_recent_months_are_estimates`, and it is a concrete reason the
timing question in §5 cannot be waved through.

### No unit changes

Every candidate's unit matched its expected unit exactly. No unit conversion was
applied — C1 stores published units as published.

## 4. World Bank – FRED Brent cross-check — NOT EXECUTED

**Status: `not_executed_source_unreachable`.**

FRED was unreachable from this environment. Three endpoints were attempted and
all failed the same way:

| Endpoint | Result |
|---|---|
| `https://fred.stlouisfed.org/graph/fredgraph.csv?id=MCOILBRENTEU` | HTTP 000, connection reset after ~20s |
| `https://fred.stlouisfed.org/data/MCOILBRENTEU.txt` | HTTP 000, connection reset |
| `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU` | HTTP 000, connection reset |

The Python client reports `ConnectionResetError: [WinError 10054] An existing
connection was forcibly closed by the remote host`. Notably, the project's own
`docs/data_source_inventory.md` records this exact CSV mechanism working in an
earlier session, so this is a current host-level network blocker, not a bad URL
or a retired series.

**No cross-check numbers are reported.** Common month count, correlations,
absolute differences and discrepancy months are all absent because they were
never measured. Reporting them as "conditional" would misrepresent a missing
measurement as a middling result, which is why the config defines
`not_executed_source_unreachable` as a state distinct from the three outcome
classes.

**The comparison logic is implemented and tested.** `compute_cross_check_metrics`
and `classify_cross_check` are complete, and synthetic tests exercise the
`consistent`, `inconsistent`, `conditional` and date-misalignment boundaries. The
check will run unchanged once FRED is reachable.

**The World Bank Brent series was not replaced or altered**, per the standing
instruction not to auto-replace on cross-check failure — and in any case nothing
failed here; nothing ran.

**FRED Brent is not, and must not become, a second Brent feature.** The config
records `may_enter_production_feature_table: false` and
`is_second_brent_predictor: false`, and a test asserts the canonical table
contains exactly one Brent series and no FRED-sourced rows.

## 5. Timing and latest-vintage limitations

Recorded explicitly in config and in every emitted row:

- The Pink Sheet is a **latest-vintage historical dataset**. Historical
  observations may be revised — the workbook says so itself for LNG.
- A workbook downloaded today does **not** prove what value was visible at a
  past forecast origin.
- **Same-month availability has not been verified.**
- `release_date` and `available_as_of` are **null on every row**, and the
  download date is deliberately *not* used as a proxy for historical
  availability. Dataset-level publication metadata lives in the manifest,
  separate from observation-level availability.
- `point_in_time_supported: false`.

| Field | Value |
|---|---|
| `latest_vintage_only` | `true` |
| `point_in_time_backtest_supported` | `false` |
| `same_month_availability_verified` | `false` |
| `minimum_safe_lag_months` | `null` |
| `timing_status` | `unresolved` |

**The lag is not chosen in C1.** C2 must default to lagged use unless stronger
publication evidence is found.

## 6. Canonical table

`data/interim/commodity_month.parquet` (git-ignored), schema in
`schemas/commodity_month.schema.yaml`.

- **5,269 rows**, 7 series, **1960-01 … 2026-07**
- One row per `(series_id, month)`, keys unique, deterministically ordered
- Levels only — the full valid source history is kept, not just the required
  window, so later tasks are not silently constrained
- Missing months are **absent**: no forward-fill, no interpolation
- No unit conversion; no MoM, YoY, lag, volatility, z-score or shock flag

Rows per series: aluminum 799, brent 799, coal 679, copper 799, LNG 595, palm
oil 799, rubber 799.

Note that `conditional` series are still ingested and carry
`source_verified: false` in the table itself — ingesting them keeps the audit
trail complete, while the flag prevents a later task from mistaking them for
cleared inputs.

## 7. Approval state — three distinct fields

| Candidate | `source_verified` | `feature_semantics_approved` | `model_feature_approved` |
|---|---|---|---|
| brent_crude_usd_bbl | ✅ true | ❌ false | ❌ false |
| lng_japan_usd_mmbtu | ✅ true | ❌ false | ❌ false |
| aluminum_usd_mt | ✅ true | ❌ false | ❌ false |
| copper_usd_mt | ✅ true | ❌ false | ❌ false |
| rubber_rss3_usd_kg | ✅ true | ❌ false | ❌ false |
| coal_australia_usd_mt | ❌ false (conditional) | ❌ false | ❌ false |
| palm_oil_usd_mt | ❌ false (conditional) | ❌ false | ❌ false |

**A verified source is not an approved predictive feature.**
`feature_semantics_approved` and `model_feature_approved` are false for every
candidate without exception, because transformation and timing semantics have
not been evaluated. That is C2's job.

## 8. What C1 did not do

No feature engineering; no unit conversion; no join to the Industry Production
Stress target; no correlation, feature importance, Granger causality or mutual
information against the target; no model; no baseline evaluation; no access to
B4's locked final test. All of these are asserted in the ingestion metadata and
covered by tests.

Every prior decision is untouched: the MPI-only K=1 target, CapU's auxiliary
role, B2's redundancy findings, B3's formulas and calibrator, B4's
development/purge/locked periods and baseline selection, and the locked-test
protection.
