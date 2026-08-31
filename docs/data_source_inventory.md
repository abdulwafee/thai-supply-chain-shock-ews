# Data Source Feasibility Study — Thai Supply Chain Shock Early Warning System

Status: read-only research artifact. **Update (2026-08-26, Task A1 execution + quality-gate
re-audit)**: the four target-component rows (OIE MPI, OIE CapU, MOC Export, NSO PPI) below are
superseded by `docs/task_a1_report.md`, which reflects real downloaded/inspected data rather than
the landing-page-only verification this file originally recorded — see that report for the current
verification status, real coverage statistics, and evidence. **Source access** is confirmed for OIE
MPI and OIE CapU (real files in `data/raw/`, 66 verified chronological months, 0.00% missingness);
MOC Export and NSO PPI have a confirmed live endpoint but unconfirmed depth. **Source access is not
the same claim as target-component approval** — per `configs/targets.yaml`'s `source_verified` /
`target_approved` fields, none of the four is yet approved as a Stress Index target component; MPI
and CapU are the closest, blocked on an aggregation-rule implementation, a redundancy test, and a
vintage/revision limitation (latest-vintage data only, not point-in-time archives) documented in
`docs/task_a1_report.md` §6. **Revision 3** of that report additionally corrects an arithmetic error
in the original history-extension analysis (the current↔2016-edition TSIC division intersection is
**21**, computed with real `set` operations via `scripts/audit_history_extension.py` — not 18 or 19
as an earlier hand-typed version stated) and confirms, separately for MPI and CapU, that 11 of the
12 industries can reach a consistent ~126-month span across editions while **IND-03 cannot** without
changing its definition (see `docs/task_a1_report.md` §7). The rows below are left as originally
written for historical traceability of what was known before that audit, not corrected in place.

Original status line (pre-A1): read-only research artifact, no pipeline built, no data
bulk-downloaded, no model trained. Verification date: 2026-08-25/26 (session date). All "Verified"
statuses below reflect what was
directly confirmed on this date via a live HTTP request (HEAD/GET, header or small-sample only) or
a direct fetch of official page content. Anything not confirmed this way is explicitly marked
**Needs verification** — it is not asserted as fact.

Verification method used per source (see "Verification Evidence Log" at the end of this file for
raw results): official landing page located via search, then (where technically safe) a `curl -I`
or small `curl` sample against the page or a linked file, or a `WebFetch` of the rendered page
content. No bulk download was performed. No endpoint was tested that was not first found in
search results or on an official page — i.e. no URL in this document was fabricated.

---

## 1. Data Source Inventory

Legend for **Role**: `Target` = manufacturing outcome the model predicts · `Feature` = leading/exogenous
signal · `Static Dependency Matrix` = low-frequency structural input (not a monthly feed).

Legend for **Verification Status**: `Verified (live)` = URL returned HTTP 200 and content matched
expectation on this date · `Verified (page located, access unconfirmed)` = official page/dataset
confirmed to exist and be reachable, but the actual bulk/API export mechanism was not exercised ·
`Blocked (bot protection)` = official site returned 403 or an anti-bot redirect loop when queried
programmatically · `Needs verification` = could not be confirmed in this session at all.

| # | Dataset | Provider | Official URL | Role | Frequency | Available History | Latest Available Period | Publication Lag | Revision Risk | Industry/Product Classification | Geography | File/API Format | Authentication | Licensing/Usage Notes | Mapping Required | Verification Status | Main Limitation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Manufacturing Production Index (MPI), by industry | Office of Industry Economics (OIE, สศอ.) | https://www.oie.go.th/view/1/mpi/TH-TH ; mirrored at https://data.go.th/dataset/mpi-index-2566 | Target | Monthly | Needs verification (TSIC 2009 rebasing may reset series; see §6) | Confirmed via a real OIE press release: March 2024 data, i.e. at least through early 2024 | Confirmed empirically: March-2024 data was dated "as of 30 April 2024" in the source press release → ≈30 days | Needs verification (OIE states monthly + quarterly figures; whether monthly prints are later revised was not confirmed) | TSIC 2009, Section C, Divisions 10–33 (verified against the official TSIC 2009 document) — but the exact OIE reporting-group list (~45 groups, per an earlier open-data listing) and its crosswalk to TSIC codes was **not** located as a published table | Thailand, national | HTML press releases (PDF) confirmed; data.go.th page returned HTTP 200 but the actual CSV/resource link was not confirmed reachable in this session | None apparent for the public press releases; data.go.th generally requires no auth | Government open data; exact license terms not read | Aggregating OIE's named sub-industries into the 12 proposed groups | Verified (page located, access unconfirmed) | No confirmed machine-readable bulk file located this session — press releases are narrative PDFs; the CSV dataset link needs direct confirmation |
| 2 | Capacity Utilization Rate (CapU), by industry | OIE | https://data.go.th/dataset/gdpublish-48_08 | Target (component) | Monthly | Needs verification | Same as MPI (published in the same release) | Same as MPI, ≈30 days (empirical) | Needs verification | Same TSIC 2009 basis as MPI, ~45 groups mentioned in an open-data listing (unconfirmed exact list) | Thailand, national | Dataset page returned HTTP 200; resource format (CSV) referenced in an earlier open-data listing but not independently confirmed downloadable this session | Needs verification | Needs verification | Same as MPI | Verified (page located, access unconfirmed) | Same as MPI |
| 3 | Producer Price Index (PPI) | Bureau of Trade and Economic Indices, Ministry of Commerce; distributed via NSO StatHub | Landing: NSO StatHub dataflow `DF_14DI_PPI` at https://stathub.nso.go.th (exact query URL found via search, not independently re-verified this session) | Target (component) | Monthly | Needs verification | Needs verification | Needs verification | Needs verification | Classification by CPA (Central Product Classification, Thailand-adapted) — crosswalk to the 12 manufacturing groups **not verified** | Thailand, national | StatHub exposes an SDMX-style dataflow viewer (`vis?...df[id]=DF_14DI_PPI...`), suggesting a machine-readable SDMX API exists | Needs verification | Needs verification | CPA → TSIC → 12-group mapping | Verified (page located, access unconfirmed) | CPA-to-TSIC concordance not located; SDMX endpoint not sample-tested this session |
| 4 | Industry-level export value | Ministry of Commerce (MOC), Trade Policy and Strategy Office | https://tradereport.moc.go.th/en/documentpublish (confirmed reachable, HTTP 200) | Target (component) / Feature | Monthly | Needs verification | Needs verification | Reported elsewhere as "source data delayed by up to 2 months" for detailed HS-level figures; MOC also holds an early monthly press briefing (timing not independently confirmed) | Needs verification | MOC operates **two parallel classification systems**: "ComCode" (MOC's own product structure) and Thai national HS (11-digit, extends international HS 6-digit) — confirmed via search, not independently inspected this session | Thailand, national, with partner-country breakdown available | Web query/report portal; whether a direct bulk CSV/API export exists (vs. only on-screen query + manual export) was **not confirmed** | Needs verification | Needs verification | HS/ComCode → TSIC 12-group mapping; this is a nontrivial many-to-one aggregation exercise | Verified (page located, access unconfirmed) | Likely a web query UI rather than a documented API; bulk/API export mechanism unconfirmed |
| 5 | Thailand Input-Output Table | NESDC (Office of the National Economic and Social Development Council) | https://www.nesdc.go.th/main.php?filename=io_page (redirects); English info page: https://www.nesdc.go.th/en/info/input-output-tables-i-o-tables-en/ | Static Dependency Matrix | Benchmark table, published roughly every ~5 years (not monthly) | Confirmed to exist at 4 aggregation levels: 180 / 58 / 26 / 16 sectors (search-confirmed); earliest edition found by name was **1975**; a page specifically for "I/O 2000 (16, 26, 58, 180)" was found | **Latest edition year is unconfirmed.** The task brief assumes a "2021 table" exists; this session found no page or document directly confirming a 2021 (or later) full benchmark edition — only earlier editions (2000, and a general series back to 1975) were located by name. This must be treated as unverified, not assumed. | Not applicable (benchmark table, not a recurring monthly release) | Low frequency of revision by design, but sector definitions can shift between benchmark editions | Sector classification is NESDC's own I-O sector list; relationship to TSIC 2009 not verified | Thailand, national | PDF/Excel reports on nesdc.go.th (based on file types seen for older editions); could not confirm current-edition format because the site blocked automated access this session | Needs verification | Needs verification | I-O sector list → 12 TSIC-based manufacturing groups | **Blocked (bot protection)** — `curl` to the NESDC IO page looped on repeated HTTP 302 redirects (session/cookie gate); an independent WebFetch attempt separately failed with "too many redirects" | Cannot confirm the latest available edition year or the exact sector list at each aggregation level without a manual (browser) visit |
| 6 | Monthly trade value by HS code, partner-country breakdown | MOC (public reports) / Customs Department | MOC: as row 4. Customs Department own portal referenced as an "Open Data Portal for Monitoring... under National Strategy" but its direct URL was **not located** in this session | Feature | Monthly | Needs verification | Needs verification | See row 4 | Needs verification | 11-digit Thai HS (extension of 6-digit international HS) | Thailand, with partner-country breakdown (confirmed to exist as a queryable dimension) | Needs verification | Needs verification | Needs verification | HS → industry mapping, same as row 4, plus a separate partner-country dimension | Needs verification | Customs Department's own open-data endpoint could not be located directly; MOC's portal is the more concretely confirmed path |
| 7 | UN Comtrade (international trade, cross-check / partner-country backup) | UN Statistics Division | https://comtradeplus.un.org (public portal); a REST API is documented to exist (confirmed via search: third-party wrapper packages such as `comtradeapicall` reference it) | Feature (backup/cross-check) | Monthly (since ~2000) and annual (since 1988) | 1988 (annual) / 2000 (monthly), per search-confirmed documentation | Needs verification | Needs verification | Low (UN-published statistical data) | HS-coded, standard international classification | Global, importer/exporter/partner triangulation | JSON API (SDMX-adjacent); exact endpoint path **not independently confirmed** — a guessed endpoint path (`comtradeapi.un.org/public/v1/preview/C/M/HS`) returned HTTP 404 in this session, so that specific path is confirmed **not** correct and must not be reused | Free tier: no key needed but capped (500 records/query per search-confirmed docs); higher limits (250,000 records/query) with a free registered subscription key | UN Comtrade terms of use apply (not read in full this session) | HS → TSIC 12-group mapping | Verified (page located, access unconfirmed); one candidate endpoint path explicitly disconfirmed | Exact working API root/path not established this session; must be obtained from official API documentation before use |
| 8 | Crude Oil Prices: Brent – Europe (`DCOILBRENTEU`, daily; `MCOILBRENTEU`, monthly) | FRED (Federal Reserve Bank of St. Louis), original source EIA | https://fred.stlouisfed.org/series/DCOILBRENTEU ; CSV export: https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU | Feature | Daily (also monthly series `MCOILBRENTEU` available) | **Confirmed live**: series starts 1987-05-20 (read directly from the downloaded CSV header rows) | Confirmed live: through 2026-08-18 (per FRED series metadata found in search) | Effectively same-day to 1-day (market price series) | Low — spot price series, not typically revised | Not applicable (single global benchmark price) | Global (Brent benchmark) | **Confirmed live**: `Content-Type: application/csv`, direct file download, columns `observation_date,DCOILBRENTEU` | **None required** — confirmed: the `fredgraph.csv` export returned HTTP 200 with no authentication | FRED data is public; individual series inherit their original source's license (EIA, U.S. government — public domain) | None (used as-is as a global energy shock proxy) | **Verified (live)** — HTTP 200, correct content-type, sample rows inspected directly | Reflects the global benchmark, not Thailand's actual landed/retail energy cost — needs pairing with a Thailand-specific retail price series for full relevance |
| 9 | Henry Hub Natural Gas Spot Price (`MHHNGSP`) | FRED, original source EIA | https://fred.stlouisfed.org/series/MHHNGSP | Feature | Monthly | Needs verification (not independently pulled this session, only confirmed to exist via search) | Needs verification | Low (spot price) | Low | Not applicable | US benchmark (proxy for global gas price pressure, not Thailand-specific) | CSV export via the same `fredgraph.csv` mechanism confirmed working for the Brent series; presumed to work identically for this series ID | None required (same mechanism as row 8) | Public domain (EIA) | None | Verified (page located; same access mechanism as a verified sibling series, but this specific series ID not independently pulled) | US benchmark, not directly Thailand's gas cost; Thailand's own LNG import cost / energy tariff needed for local relevance |
| 10 | Thailand retail diesel and fuel price | Energy Policy and Planning Office (EPPO, สนพ.) | https://www.eppo.go.th/data-energy-statistic/energy-price-th/ | Feature | Confirmed at least monthly (EPPO also publishes daily retail pump prices; monthly "energy status" reports also exist) | Needs verification | Needs verification | Needs verification | Needs verification | Not applicable (fuel-type series, not industry-classified) | Thailand, national | Needs verification (website presentation, not confirmed as downloadable file) | Needs verification | Needs verification | None (used directly as a feature) | **Blocked (bot protection)** — `curl` to eppo.go.th returned HTTP 403 on this session (likely a WAF); an EPPO organization page does exist on data.go.th (HTTP 200), suggesting an alternate, non-blocked path | Direct site scraping is blocked; must use the data.go.th mirror or manual download, per this task's own instruction not to scrape when an official channel is blocked |
| 11 | Thailand electricity tariff (Ft adjustment / industrial rate) | Energy Regulatory Commission (ERC) / MEA / PEA | Not located to a specific verified URL this session | Feature | Typically adjusted quarterly (Ft surcharge), base tariff less frequently | Needs verification | Needs verification | Needs verification | Needs verification | Not applicable | Thailand, national | Needs verification | Needs verification | Needs verification | None | **Needs verification** — not searched/confirmed this session | Entirely unverified; flagged only because the task explicitly asks about electricity/industrial energy cost |
| 12 | World Bank Commodity Markets ("Pink Sheet") — Energy, Agriculture, Fertilizers, Metals & Minerals | World Bank | Landing: https://www.worldbank.org/en/research/commodity-markets ; direct file (current as of this session): https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx | Feature | Monthly | Well-documented publicly to extend back several decades (not individually re-verified per series this session) | **Confirmed live**: file dated August 2026 in its own URL path | ~1 month (report cadence is monthly, e.g. "CMO-Pink-Sheet-August-2026") | Low (published index, not typically revised) | Covers named commodities (e.g. crude oil, natural gas, coal, rubber, base metals, specific agricultural commodities) — not TSIC-coded, needs manual mapping to "which commodity feeds which of the 12 industries" | Global (with some region-specific series) | **Confirmed live**: `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, 577,979 bytes, HTTP 200, no redirect | **None required** — confirmed via direct HEAD request | Confirmed via search: Creative Commons CC BY 4.0 | Commodity → upstream industry linkage (e.g. rubber price → TSIC Division 22) | **Verified (live)** — HTTP 200, correct file type and size confirmed by direct request | Global prices only; does not reflect Thailand-specific import cost, freight, or FX pass-through — needs combining with THB/USD FX (row 14) |
| 13 | Thailand-specific agricultural commodity prices (cassava, sugarcane, rubber, etc.) | Office of Agricultural Economics (OAE, สศก.) | Not located to a specific verified URL this session | Feature | Needs verification (OAE data is often tied to crop/harvest cycles rather than a strict monthly cadence) | Needs verification | Needs verification | Needs verification | Needs verification | Commodity-specific, not TSIC-coded | Thailand, national/regional | Needs verification | Needs verification | Needs verification | Commodity → industry (e.g. cassava → TSIC 10 starch products, confirmed relevant by an actual OIE press release citing cassava/starch as an MPI driver) | **Needs verification** — provider identified from general knowledge, not independently confirmed reachable this session | Frequency/seasonality risk flagged in the prior design phase (§ Target Design v1) applies here too |
| 14 | Thailand Manufacturing PMI (headline value) | S&P Global (formerly IHS Markit) | https://www.pmi.spglobal.com/Public/Home/PressRelease/be03c42425f5413c8bd958ba6b8ca35c (confirmed to exist via search) | Feature | Monthly, released on the first business day of the following month (per search-confirmed industry practice) | Search-confirmed collection start: December 2015 | Needs verification (not pulled this session) | ~1–3 days (very fast — released at the start of the month following the reference month) | Low (headline figure typically not revised) | Not applicable (single composite index) | Thailand (and, for partner-country versions, China Caixin PMI, US ISM PMI, etc. — each needs separate sourcing) | Only the **headline monthly value** is released free via press release; the full historical time series is a paid S&P Global product | Free press release: none. Full series: subscription | Full historical series requires a commercial license — must not be bulk-scraped from paid aggregators (TradingEconomics, CEIC) for redistribution | None (used as a scalar feature) | Verified (page located, access unconfirmed for historical series) | Only the newest headline print is free each month; a usable multi-year training feature requires either a paid subscription or accepting a much shorter free history collected prospectively |
| 15 | USD/THB and partner-country exchange rates | Bank of Thailand (BOT) | New API portal: https://portal.api.bot.or.th/ (old portal at apiportal.bot.or.th is stated to be discontinued after 2025-12-31, i.e. already retired as of this session's date) | Feature | Daily | Needs verification (BOT states "highly frequent data" disseminated since 2017-07-17 for some series) | Needs verification | Needs verification | Low (market rate, not revised) | Not applicable | Thailand vs. major/regional currencies | REST/API (exact schema not sample-tested this session) | **Confirmed required**: BOT's documentation describes a registration-based API; exact auth flow on the *new* portal was not exercised this session | Needs verification | None (used directly) | **Verified (page located, access unconfirmed)** — new portal returned HTTP 200; auth flow not exercised | Migration from the old to the new BOT API portal is time-sensitive; any code or docs referencing the old `apiportal.bot.or.th` domain are stale and must be updated |
| 16 | IMF Direction of Trade Statistics (DOTS) | International Monetary Fund | https://data.imf.org/?sk=9D6028D4-F14A-464C-A2F2-59B2CD424B85 (search-confirmed); root portal https://data.imf.org redirects (HTTP 301) to a documentation page, not a data endpoint | Feature (backup/cross-check for partner-country trade) | Monthly and quarterly (search-confirmed); annual since 1947 | Monthly/quarterly since 1960 (search-confirmed) | Needs verification | Needs verification | Low | Country-level, not industry-coded | Global, partner-country pairs | SDMX-based API confirmed to exist by IMF's own documentation (per search); exact endpoint root not exercised this session | Needs verification (IMF states free access; API key requirements for the SDMX endpoint not confirmed) | IMF data generally free for non-commercial use; full terms not read | None (country/FX level, not industry level) | Verified (page located; root API endpoint redirects, exact data endpoint not exercised) | Confirmed as a partner-country/macro source, not an industry-level one — usable only as a coarse trading-partner-shock feature |
| 17 | Freightos Baltic Index (FBX) | Freightos | https://www.freightos.com/enterprise/terminal/freightos-baltic-index-global-container-pricing-index/ ; data terminal at https://data.freightos.com/ | Feature | Daily (aggregated to monthly for this project) | Needs verification | Needs verification | Near real-time (daily index) | Low | Not applicable (route-level freight index, e.g. China–North Europe) | Global shipping lanes, several of which touch Thailand's export routes indirectly (not Thailand-specific) | Some headline metrics free on the public site; bulk export and granular API access confirmed (via search) to require a paid account | Free tier: limited headline metrics only. Paid: full API | Paid tier required for systematic/bulk use | None (route-level, not industry level) | Verified (page located, access unconfirmed for the free tier's actual data granularity) | No Thailand-specific lane confirmed free; likely usable only as a coarse global freight-cost proxy unless a paid tier is adopted |
| 18 | Laem Chabang / Bangkok Port container throughput | Port Authority of Thailand (PAT) | https://www.port.co.th (confirmed reachable, HTTP 200); the specific statistics sub-page was **not** located this session | Feature | Monthly (commonly reported at this cadence by secondary sources; PAT's own native cadence not confirmed) | Needs verification | Needs verification | Needs verification | Needs verification | Not applicable (port-level, not industry-level) | Thailand (Laem Chabang and Bangkok ports specifically) | Needs verification — likely PDF/annual-report format based on how the figures are typically cited by secondary sources (Statista, CEIC) rather than a live dataset | Needs verification | Needs verification | None (port-level, used directly as a logistics-congestion proxy) | **Verified (page located, access unconfirmed)** — root domain reachable; the actual statistics/download page not found in this session | Most third-party citations of this data (Statista, CEIC) are paid aggregators; the primary PAT statistics page/download format still needs to be located directly |
| 19 | BOT Business Sentiment Index (BSI), by sector | Bank of Thailand | Confirmed to exist via search (secondary aggregator CEIC cited); primary BOT statistics page not independently re-verified this session (see prior design-phase research) | Feature (diagnostic/cross-check only — see leakage caveat below) | Monthly | Needs verification | Needs verification | Needs verification | Needs verification | Sector breakdown exists (manufacturing vs. non-manufacturing, and finer); exact granularity vs. the 12 TSIC groups not verified | Thailand, national with sector breakdown | Needs verification | Needs verification | Needs verification | Sector breakdown → 12-group mapping | Needs verification | **Leakage caveat carried over from the target-design phase**: only the "current conditions" sub-index may be used as a feature; the "next-3-months expectation" sub-index must never be used as a feature for a 3-month-horizon target, since it asks respondents directly about the future |

---

## 2. Recommended Minimum Viable Dataset

Selected only from rows with **Verified (live)** or **Verified (page located, access unconfirmed)**
status, and only where the remaining "Needs verification" items are operational details (exact
file/API mechanics) rather than open questions about whether the data exists at all:

| Purpose | Dataset | Row |
|---|---|---|
| Target (primary) | MPI + CapU by industry (OIE) | 1, 2 |
| Target (secondary/loss-severity component) | Industry-level export value (MOC) | 4 |
| Target (secondary/loss-severity component) | PPI (MOC/NSO) | 3 |
| Static Dependency Matrix | Thailand Input-Output Table (NESDC), aggregation level TBD pending edition-year confirmation | 5 |
| Feature — energy shock | Brent crude oil price (FRED) | 8 |
| Feature — raw-material shock | World Bank Pink Sheet (agriculture, rubber, metals) | 12 |
| Feature — FX / trading-partner shock | USD/THB exchange rate (BOT API) | 15 |

This set is deliberately narrow: every item on it has at least a confirmed-reachable official page,
and two items (Brent oil, World Bank Pink Sheet) are fully verified end-to-end with no authentication
barrier. It is sufficient to build the Dependency Matrix, the Shock Transmission Matrix's target side,
and a first external-shock feature set spanning energy, raw materials, and FX — one signal per major
external-shock category the project scope requires, deferring the harder-to-source categories
(logistics, trading-partner PMI/industrial production) to the optional list below.

## 3. Optional Datasets for Later Versions

- Thailand Manufacturing PMI + partner-country PMI (row 14) — real signal, but the usable free
  history is short (only the newest print each month is free); adopting this properly likely means
  either a paid subscription or accepting a shorter, prospectively-collected series.
- Freightos Baltic Index / logistics cost proxies (row 17) — free tier is headline-only; treat as
  v2 unless the paid tier is approved.
- Port throughput (row 18) — plausible logistics-congestion proxy but its native download format is
  still unconfirmed; worth a manual follow-up before committing to it.
- IMF DOTS / UN Comtrade (rows 16, 7) — useful for cross-checking or filling partner-country gaps in
  MOC's own trade data, but redundant with row 4/6 for the MVP; hold in reserve as a backup/validation
  source rather than a primary pipeline input.
- BOT Business Sentiment Index, "current conditions" sub-index only (row 19) — a plausible
  cross-check signal for the nowcast target itself, not for the forecasting features.
- Thailand-specific agricultural commodity prices from OAE (row 13) — would sharpen the raw-material
  shock signal beyond the global World Bank proxy, but the exact access path needs to be found first.

## 4. Sources to Reject, and Why

- **Third-party trade-data resellers** (Volza, Tendata, eximtradedata, ImportGlobals, tradeimex,
  GlobalTradeData, and similar "Thailand import/export data" vendors found repeatedly in search
  results) — reject as primary sources. They resell bill-of-lading-derived or scraped data of
  unclear methodology, sit behind unclear licensing, and duplicate what an official channel (MOC,
  Customs) already provides. The task explicitly prioritizes official sources; these should not be
  used even as a stopgap while the official API/export mechanics are pinned down.
- **CEIC, Statista, TradingEconomics as data-pipeline inputs** — reject for the same reason: they are
  paid, licensed aggregators whose terms typically do not permit bulk reuse in a redistributed
  project/portfolio artifact. They remain useful only as a *discovery* aid (as used in this study to
  locate official primary sources), never as the actual ingestion source.
- **Scraping EPPO or NESDC by bypassing their bot protection** — reject. Both returned bot-protection
  responses (HTTP 403 for EPPO, a redirect loop for NESDC) to a simple, low-volume request in this
  session. Per the task's own restriction against scraping when an official channel exists, the
  correct path is either the data.go.th mirror (for EPPO, confirmed reachable) or a manual periodic
  download from the official site (for NESDC's I-O table, which is a low-frequency static resource
  anyway and does not need automation).
- **Shanghai Containerized Freight Index (SCFI) from any source found this session** — reject for now.
  No verified free, official access point was found; every reference located was either a
  description of the index or a paid data-vendor listing.

## 5. Earliest Common Monthly Start Date Supported by the Core Datasets

**This cannot be stated as a confirmed date.** Two different constraints are in play, and they are
not the same:

- The **feature-side, global series** (Brent oil, World Bank Pink Sheet) are confirmed to extend
  back decades (Brent: verified live to 1987-05-20; Pink Sheet: well-documented publicly to extend
  much further back, though not re-verified series-by-series this session). These are **not** the
  limiting factor.
- The **target-side, Thai official series** (MPI, CapU, PPI, industry exports) are the actual
  constraint, and their true start date for a *continuous, consistently-classified* series is
  **unverified**. TSIC was revised in 2009 (confirmed from the official document), which typically
  forces a rebasing or reclassification of production indices — whether OIE back-cast its current
  MPI series under the new TSIC codes, or whether continuity only holds from some point in the 2010s
  onward, was not established this session.

The honest answer at this stage is: **the earliest usable common start date is currently unknown and
must be confirmed directly from OIE's MPI methodology documentation** (specifically, its stated base
year and the date from which the current TSIC-2009-based series is continuous) before any training
window is fixed.

## 6. Proposed Train / Validation / Final Test Period

Framed conditionally, pending the confirmation in §5, and structured the same way the reference
methodology (walk-forward, a validation period distinct from a genuinely untouched final test window)
was used earlier in this project's design phase:

- **Train**: from the confirmed continuous-series start date (§5, pending) through approximately
  3 years before the present.
- **Validation**: the following ~1.5–2 years, used to select hyperparameters (thresholds, blend
  weights, etc. — as designed in the target-design phase), never to select the feature set itself.
- **Final test (clean holdout)**: the most recent ~12 months of fully available, non-revised data,
  touched only once, at the end — mirroring the reference paper's own use of a late, non-overlapping
  test window (its January 2025–July 2026 clean window) specifically to avoid the repeated-inspection
  leakage it documents for its first out-of-sample period.

Given today's date, if the MPI series turns out to be usable from (for instance) some point in the
2010s, the final test window would land in roughly 2025–2026 — but this is illustrative only, not a
commitment, until §5 is resolved.

## 7. Known Structural Breaks or Classification Changes

- **TSIC revision (2009 edition, confirmed to exist)** — a classification revision of this kind
  typically changes division boundaries and can force a break in any production index computed under
  the old classification. Needs verification: how OIE handled continuity across this boundary for MPI.
- **MPI base-year rebasing** — production indices are periodically rebased (e.g., a new "= 100" base
  year); this changes index *levels* even when underlying activity is continuous. Current base year
  not confirmed this session.
- **I-O Table benchmark revisions** — NESDC publishes full benchmark tables roughly every five years
  (1975, 2000, and others found by name); sector definitions can shift between editions, which is a
  direct structural-break risk for the Dependency Matrix specifically, not just the target series.
- **HS code revisions** — the international Harmonized System itself is revised roughly every five
  years (e.g., HS2017, HS2022); if MOC's trade classification vintage changes over the sample period,
  a bridge table is needed to keep the industry-export target continuous. Which HS vintage MOC
  currently reports under, and whether historical bridges exist, is unconfirmed.
- **COVID-19 (2020–2021)** — not a classification break, but a confirmed real-world structural break
  across essentially every series in this inventory (production, trade, freight, PMI). Must be
  handled explicitly in the eventual train/validation/test design, consistent with the
  non-stationarity discussion already raised in this project's target-design phase.

## 8. Missing Information Requiring Manual Confirmation

- OIE's exact MPI/CapU reporting-group list (the ~45 groups referenced in one open-data listing) and
  its official crosswalk to TSIC 2009 codes — no such table was located as a published document.
- NESDC I-O table: the actual latest benchmark edition year (2021 assumed by the task brief but not
  independently confirmed), and the sector name list at each of the 180/58/26/16 aggregation levels.
- tradereport.moc.go.th: whether a genuine bulk/API export exists, or only an on-screen query with
  manual export — not established this session.
- Thailand Customs Department's own open-data endpoint — referenced to exist by a third party but its
  direct URL was not located.
- PPI's exact publication lag and whether the NSO StatHub SDMX dataflow is truly machine-readable
  end-to-end (the dataflow ID was found, but not queried this session).
- EPPO and NESDC: both blocked simple automated access this session (403 / redirect loop
  respectively) — needs a manual browser session to confirm what data these sites actually expose,
  and whether a non-blocked mirror (e.g., data.go.th for EPPO) carries the full dataset or only a
  subset.
- BOT API: the exact authentication/registration flow on the new portal (`portal.api.bot.or.th`),
  since the old portal it replaces is stated to be already retired.
- UN Comtrade and IMF: exact working API root paths — one guessed Comtrade path was tested and
  confirmed *not* to work (HTTP 404); the correct path must come from each provider's own current
  API documentation, not be guessed again.
- Port Authority of Thailand: the actual statistics/download sub-page (only the root domain was
  confirmed reachable).
- Thailand-specific agricultural commodity price source (OAE) — provider identified from general
  knowledge but no URL was verified this session.

## 9. Can This Project Be Completed Using Only Public Data?

**Yes, with an operational caveat.** Every dataset in the recommended MVP (§2) traces to an official
public provider, and two of them (Brent crude via FRED, World Bank Pink Sheet) are fully verified,
open, and require no authentication at all. The Dependency Matrix source (NESDC I-O table) is public
in principle but is a low-frequency, manually-refreshed input by nature, so the fact that it currently
resists automated access is a minor operational inconvenience, not a blocker. The target-side data
(MPI, CapU, PPI, exports) is confirmed to be officially published; what remains unverified is only the
*mechanics* of bulk access (API vs. manual export), not whether the data itself is public.

The main caveat: at least two official Thai sites (EPPO, NESDC) actively blocked simple automated
requests in this session. This means full pipeline automation is **not** currently achievable for
every source — some ingestion will need to be a scheduled *manual* download rather than a live feed,
which is an operational design point to carry into the eventual pipeline (e.g., a documented monthly
manual-refresh step for blocked sources), not a reason to substitute paid or unofficial data.

The weakest category for public-only completion is **logistics** (row 17, 18): no fully free,
official, machine-readable logistics-cost or congestion series was confirmed this session. This is
consistent with logistics being the category most likely to end up as an optional/v2 addition (§3)
rather than part of the MVP.

---

## Verification Evidence Log

Raw evidence collected this session, in support of the "Verified (live)" statuses above. All requests
were single HEAD/GET calls or one small sample fetch — no bulk download was performed.

```
GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU
  -> HTTP 200, Content-Type: application/csv
  -> first data rows: "observation_date,DCOILBRENTEU" / "1987-05-20,18.63" / "1987-05-21,18.45" ...

HEAD https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx
  -> HTTP 200, Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
     Content-Length: 577979

HEAD https://data.go.th/dataset/mpi-index-2566            -> HTTP 200
HEAD https://gdcatalog.go.th/dataset/gdpublish-43_02       -> HTTP 200 (headers only; body served by
                                                               Incapsula bot-protection challenge page)
HEAD https://data.go.th/dataset/gdpublish-48_08            -> HTTP 200
HEAD https://tradereport.moc.go.th/en/documentpublish      -> HTTP 200
HEAD https://portal.api.bot.or.th/                         -> HTTP 200
HEAD https://www.port.co.th                                -> HTTP 200
HEAD https://data.go.th/organization/eppo                  -> HTTP 200
HEAD https://www.eppo.go.th/                                -> HTTP 403 Forbidden
HEAD https://www.eppo.go.th/data-energy-statistic/energy-price-th/ -> HTTP 403 Forbidden
GET  https://www.nesdc.go.th/main.php?filename=io_page (with redirects followed)
  -> looped on repeated HTTP 302 (session-cookie gate); did not resolve to final content
GET  https://comtradeapi.un.org/public/v1/preview/C/M/HS   -> HTTP 404 (confirms this specific
                                                               guessed path is wrong; not reused)
HEAD https://data.imf.org/ifs                               -> HTTP 301 -> redirects to a
                                                                 documentation/news page, not a data
                                                                 endpoint

OIE press release (PDF, extracted and read directly):
  https://www.oie.go.th/assets/portals/1/fileups/2/files/news_oiepr/press_MPI_March2024.pdf
  -> confirms MPI + CapU published together monthly; March 2024 figures explicitly dated
     "ข้อมูล ณ วันที่ 30 เมษายน 2567" (data as of 30 April 2024) => ~30-day publication lag
  -> confirms named sub-industries reported: petroleum refining (+5.32% YoY), starch/cassava
     products (+47.65% YoY), animal feed (+8.45% YoY), automotive (-22.63% YoY), sugar (-25.26% YoY),
     electronic parts/integrated circuits (-15.33% YoY)
  -> confirms OIE runs its own "Industrial Economic Early Warning System" with a stated signal level
     of "เฝ้าระวัง" (Watch) for March 2024 — an existing official precedent for this project's concept

TSIC 2009 official document (PDF, extracted and read directly):
  https://eservice.dede.go.th/files/TSIC2009.pdf
  -> confirms Section C (Manufacturing) Divisions 10-33, exact Thai names read directly from the
     source document (see prior design-phase output for the full division list and 12-group mapping)
```

---

## Task C1 update (2026-08-27) — World Bank Pink Sheet productionized, FRED blocked

**World Bank Pink Sheet (row 12): now VERIFIED END-TO-END AND INGESTED.** The
direct URL previously recorded here was re-resolved by discovery from the
landing page rather than trusted; it is still current. Vintage July-2026,
`Updated on August 04, 2026`, 577,979 bytes, SHA-256 `7902a775...`, recorded in
`data/raw/_manifests/WB_PINKSHEET_manifest.jsonl`. Seven candidate series
audited: 5 `source_verified`, 2 `conditional` (coal and palm oil, both due to
pricing-benchmark changes inside 2021-01…2026-05). See
`docs/c1_commodity_source_audit.md`.

**FRED (rows 8–9): CURRENTLY UNREACHABLE from this environment.** This row
previously recorded `fredgraph.csv` as confirmed live. As of 2026-08-27 all
three attempted endpoints (`fredgraph.csv?id=MCOILBRENTEU`,
`data/MCOILBRENTEU.txt`, `fredgraph.csv?id=DCOILBRENTEU`) fail with a connection
reset (`WinError 10054`, HTTP 000) after roughly 20 seconds. The earlier
verification is not retracted — the mechanism worked then — but the source
cannot be reached now, so the Brent cross-check did not run. Re-test before
relying on FRED for anything.

## Task C3 update (2026-08-27) — NESDC Input–Output Table acquired

A third official source family joins OIE (targets) and the World Bank Pink Sheet
(commodities): **NESDC's Input–Output Table of Thailand**, used to build a
structural exposure prior, never as a target or a feature value.

| Item | Value |
|---|---|
| Publisher | National Economic and Social Development Council (NESDC) |
| Primary table | **Input-Output Table of Thailand 2015 (Final)** |
| File | `INPUT-OUTPUT_TABLE_2015.xlsx`, 665,344 bytes |
| SHA-256 | `7da4b4dca118af760844abd6c78ae01a83f313c8898321ac69e72be730e93c81` |
| Classification | `06.3-Input-Output-Description.pdf`, 167,647 bytes, `87a65982fa12b643…` |
| Newer table | I/O Table 2021 (180 Sectors), `451340133b02afc7…` — **audited, not substituted**; status **unresolved** |
| Aggregation check | `DataIO2015x58.xlsx`, 239,507 bytes, `67c921a83fae15ed…` (added in C3-R1) |
| Official publication | `Book_IO2015_EN.pdf`, 4,924,243 bytes, `d5bc805c487341d9…` |
| Sectors | **180** primary; NESDC also publishes 58 / 26 / 16-sector versions |
| Unit | **Thousand Baht** (from `Book_IO2015_EN.pdf`) |
| Valuation | Purchasers' prices, import-inclusive, margins itemised |
| Manifest | `data/raw/_manifests/NESDC_IO_manifest.jsonl` |
| Raw files | git-ignored |

**Discovery is not hard-coded.** NESDC migrated to WordPress and the historical
`main.php?filename=io_page` now serves a page with no I/O links at all. URLs are
resolved by walking NESDC's own sitemap (41 sections, 7,918 download URLs, 21 I/O
pages) to each download page's `?p=&ddl=` redirect. Two transport quirks are
handled explicitly and recorded: a WAF cookie challenge, and a router that
answers content pages with HTTP 404 while serving a full body — accepted only for
HTML, never for a file download.

**Availability answer:** yes, entirely public and free, no registration. The
constraint is not access but **vintage**: the newest final table is 2015, applied
to a 2021–2026 modelling window under an explicit time-invariance assumption.

Detail: `docs/c3_io_source_audit.md`.


### C3-R1 correction (2026-08-27)

C3 reported that no official 58-sector 2015 workbook exists. **It does.**
`DataIO2015x58.xlsx` is published in NESDC's WordPress **media library**, which
C3's download-page-only discovery never queried — the 2015 download page carries
exactly one file link, the 180-sector table. Discovery now also queries the
official media REST API and searches the published `x58`/`x26`/`x16` filename
patterns.

The 180-sector table **remains the primary source** — 58 sectors are too coarse
to separate, for example, wooden from metal furniture. The 58-sector file is an
**aggregation validation source**: all **12** partition-invariant grand totals
match it **exactly**. A sector-level comparison would need an official 180-to-58
concordance, and none exists in any NESDC document located; that reconciliation
is recorded as **not executed**, not as passed.


### D2 — OIE MPI publication timing and vintage audit (2026-08-28)

The MPI **target** source family was audited the same way the commodity sources
were in C1.5. Three findings change how the target must be described.

**1. Publication timing is establishable, and it is later than B4 assumed.**
The i-Index monthly archive (`https://i.index.oie.go.th/List_industrial.aspx`)
holds **127 entries covering 2016-01..2026-07 with no gaps**. Across the **111
months with credible evidence**, OIE first publishes reference month *t* a
**median 29 days** (min 23, max 66) after *t* ends — i.e. during month *t+1*.
This was confirmed by a **directly observed release**: re-fetching the live
workbook on 2026-08-28 showed exactly one new month (2026-07) versus the
2026-08-26 snapshot, `Last-Modified` moving 2026-07-27 -> 2026-08-27.

**2. The archive listing timestamp is not a publication date.** 37 of 127
entries sit in shared-timestamp migration batches (2017-06-13 x16,
2023-07-27 x15). The attached PDF is stronger evidence, cross-checked between
its HTTP `Last-Modified` and the upload stamp encoded in its filename. Seven
distinct evidence classes are recorded; the 2016-01..2017-03 block retains no
surviving first-publication evidence.

**3. No complete 12-industry vintage exists via the mechanisms exercised.**
Archive attachments are selective press-release overviews (0 TSIC division codes
paired with values; 4-6 of 13 industry keywords, a different subset each month).
The live workbook is overwritten in place. The data.go.th OIE records point at
those same live URLs, and the per-month data.go.th MPI files published by the
Electrical and Electronics Institute contain electrical/electronics product rows
only. This is a statement about those mechanisms, **not** proof that no vintage
archive exists anywhere.

A parsing note worth recording: **July appears in two spellings** in entry
titles (`กรกฎาคม` and the variant `กรกฏาคม`, 5 entries). Accepting only the
standard spelling reports five coverage gaps that do not exist.

Detail: `docs/d2_oie_mpi_source_audit.md`, `docs/d2_target_timing_decision.md`.


### C5 price-stage source audit (2026-08-28)

Four official families were probed for the price stages industries actually purchase.

| family | publisher | state | gate |
| --- | --- | --- | ---: |
| `EPPO_PETROLEUM` | Energy Policy and Planning Office | **verified** | **10/10** |
| `BOT_FX` | Bank of Thailand | reachable, out of scope | 8/10 |
| `ERC_ELECTRICITY` | Energy Regulatory Commission | timeout / 404 | 5/10 |
| `MOC_PPI` | Ministry of Commerce | HTTP 403 on all entry points | 4/10 |

**Verified series:** `PRICE STRUCTURE OF PETROLEUM PRODUCTS — EX-REFIN.`, unit **BAHT/LITRE** (LPG
BAHT/KILOGRAM), an **ex-refinery producer price** reported separately from EXCISE TAX, MUNICIPAL
TAX, OIL FUND, CONSERVATION FUND and WHOLESALE. Products include H-DIESEL, H-DIESEL B20,
FO 600 2%S and FO 1500 2%S. Maps to I/O sector **093 Petroleum refineries**. Daily snapshot, one
workbook per effective date, with the date in-sheet and in the filename.

**Coverage limitation, explicit and unresolved:** only recent daily files are exposed. Probing the
observed `/uploads/YYYY/MM/` pattern returned 404 for 2022–2025, but that is **not** evidence of
absence — 2018 retail files are served from a **2026** upload folder, so the site re-hosts
historical files under migration-time folders and folder-date inference is unreliable. HEAD is
blocked site-wide, so a 403 there is a method restriction, not a missing file.

MOC and ERC are recorded as **blocked**, never as absent. They are ineligible because an
unverifiable series definition cannot satisfy the gate — a statement about the evidence, not the
publisher. BOT's exchange rate is audited only as an import-price transmission factor and is
explicitly not an I/O commodity sector price.

Detail: `docs/c5_price_stage_source_audit.md`, `docs/c5_source_recommendation.md`.


### C6 EPPO ex-refinery archive audit (2026-08-28)

| entry point | mechanism | result |
| --- | --- | --- |
| `wp-json/wp/v2/media` | `official_wordpress_rest` | **5,233 workbooks**, terminated `api_termination_400_at_page_54` |
| `wp-sitemap.xml` | `official_wordpress_sitemap` | 25 sub-sitemaps, reachable |
| `/feed/` | `official_rss_feed` | reachable |
| category archive / landing | `official_current_archive_href` | reachable, exposes only recent files |
| legacy Joomla paths | `official_legacy_archive_href` | tested legacy URLs now serve the modern site and no longer expose the original archive |

**Archive span:** 2002-02-03 … 2026-08-28, 4,976 distinct effective dates, ~240/year consistent with
working-day publication.

**Coverage:** transformation-parity window 2021-01…2026-05 **65/65 months**; operational window
2022-01…2026-05 **53/53 months**. No missing months in either.

**Availability:** every media upload timestamp is from the 2026 migration, so
`migration_timestamp_only` for all 254 validated documents. Independent captures exist for 43 archive
dates but none overlap the validated sample. **Point-in-time `not_supported`.**

**Products:** `H-DIESEL`, `FO 600 (1) 2%S`, `FO 1500 (2) 2%S`, all BAHT/LITRE, ex-refinery column
kept distinct from wholesale, VAT and retail. LPG (BAHT/KILOGRAM) excluded. Diesel blends B7/B10/B20
are separate products and never substituted.

Detail: `docs/c6_eppo_archive_audit.md`.


### C6.5 evidence-boundary correction (2026-08-28)

C6 wording that outran its evidence is superseded here. The corrected statements are:

* `legacy_archive_status: tested_legacy_urls_no_longer_expose_original_archive` — the URLs probed no
  longer expose it; that is not the same as the archive not existing anywhere.
* `historical_timing_status: not_reconstructable_from_sources_inspected_in_c6` — C6 probed the
  current WordPress archive, its REST index, sitemaps, RSS and the legacy Joomla paths. Offline
  records and a direct request to EPPO were never exercised, so this is a limit of the inspection,
  **not** a permanent impossibility.
* `monthly_presence_coverage: complete` but `complete_daily_document_validation: false` — 65/65 and
  53/53 month presence means at least one document per month, **not** a validated daily archive.
  254 of 1,315 discovered document-days were validated; the 722-row table is a partial audit table.
* Archive depth alone does not make any transformation feature-ready. Depth and readiness are now
  tracked as two separate fields.

**Absence from the inspected mechanisms is not proof that no historical publication evidence exists
anywhere.**

Detail: `docs/c6_5_eppo_latest_vintage_decision.md`.


### C7 EPPO full daily archive ingestion (2026-08-29)

The audit sample became a full ingestion. Every officially discovered document-day in
2021-01-01 … 2026-05-31 was attempted.

| state | count |
| --- | --- |
| discovered media records | 1,336 |
| distinct document-days | 1,315 |
| days with more than one attachment | 19 |
| retrieval attempts | 1,336 |
| HTTP successes | 1,333 |
| content-valid documents | 1,331 |
| valid canonical document-days | **1,310** |
| unresolved document-days | **5** |

Raw workbooks live in `data/raw/EPPO_PRICE_STRUCTURE/` (git-ignored, ~54 MB). Provenance survives in
`data/raw/_manifests/EPPO_PRICE_STRUCTURE_manifest.jsonl` — 1,336 lines, about 1 MB, larger than the
other manifests because it is the only durable record of what was retrieved and what each file hashed
to.

**Unresolved inventory items.** 2026-04-17, 2026-04-18 and 2026-04-19 have official media records
that the REST API still serves, but their attachment URLs return 404. 2022-12-05 and 2025-01-25 list
attachments whose internal dates are 2022-12-06 and 2025-01-24; neither is reassigned, and no
separately valid official document covers either date.

**Layout regimes.** `xls_2021` 2021-01-04…2023-06-02, `xlsx_2023` 2023-06-06…2026-05-31, plus one
document (2024-03-07) in a third signature. The previously unsampled February–June 2023 interval
resolved into the two known regimes with no additional regime inside it.

**Ordinary `H-DIESEL` is absent 2023-09-18 … 2024-12-17 (305 document-days).** C6's 22-day January
2024 finding was every sampled day inside that absence; it is extended, not contradicted. Blend
prices are never substituted.

**Both fuel-oil labels drop their ordinal index 2024-07-23 … 2024-10-28** (`FO 600 2%S`,
`FO 1500 2%S`). Rows are kept and flagged `unconfirmed_label_variant`; the equivalence is not
asserted and the affected months are blocked.

**Monthly source table.** 195 rows (3 series x 65 months), rule
`arithmetic_mean_of_validated_observed_official_document_days` version `c7_v1`. 162 product-months
approved. **`monthly_aggregation_contract_approved: false`** — the gate failed and was not forced.
`source_available_as_of` is null everywhere; `policy_available_month` is `reference_month + 2`.

No predictive transformation, no exposure multiplication, no MPI join, no model.

Detail: `docs/c7_eppo_full_archive_audit.md`.


### C7.5 EPPO product semantics and aggregation closure (2026-08-29)

The four blockers C7 reported are now resolved or explicitly recorded as unresolved. C7's raw
documents, labels, values and checksums are unchanged.

**Fuel-oil labels: `equivalence_established`.** The workbook's Thai companion sheet is formula-bound
to the English rows (`='Oil Price Structure'!C14`) and gives one identical, ordinal-free product name
— `น้ำมันเตา 600 กำมะถันไม่เกิน 2%` — for both English forms, across 471 documents. Raw labels are
preserved verbatim; `canonical_product_id` is a layer above them. What `(1)` and `(2)` mean is
**`not_established_from_inspected_sources`**, and the decision does not depend on it.

**Recovery of the five unresolved document-days: 2 recovered, 3 not.**

| listing date | outcome | detail |
| --- | --- | --- |
| 2022-12-05 | `recovered_and_validated` → **2022-12-06** | parent post titled and dated 2022-12-06, matching the document's internal date |
| 2025-01-25 | `recovered_and_validated` → **2025-01-24** | parent post titled and dated 2025-01-24, matching the internal date |
| 2026-04-17/18/19 | `official_attachment_unretrievable` | 404 on the production host and on the `guid` host; parent post lists them; no alternate media record |

**H-DIESEL:** `not_ready_long_semantic_definition_gap`. 305 document-days, 2023-09-18…2024-12-17,
sixteen reference months. Documents and blend products remain valid; the series simply cannot be
continuous. All observations and blend provenance retained.

**Three approvals replace one.** `aggregation_method_semantics_approved: true` for all three series;
`full_requested_window_coverage_complete: false` for all three;
`series_ready_for_transformation_with_explicit_gaps` true for both fuel oils, false for H-DIESEL.
Monthly statuses: 168 `approved_complete_inventory`, 8 `approved_with_source_label_variant`,
16 `semantic_definition_gap`, 3 `known_document_gap`.

**Coverage views.** Full source window 2021-01…2026-05. Maximum preregistered issue origin 2026-04,
so the maximum required source reference month is 2026-02. April 2026 reaches no preregistered issue
origin and is documented regardless.

Semantic overlay: `data/interim/c7_5_eppo_monthly_semantic.parquet` (git-ignored, 195 rows). It does
not overwrite the C7 monthly audit artifact. Detail: `docs/c7_5_eppo_semantic_decision.md`.


### C8 EPPO fuel-oil source transformations (2026-08-29)

The two C7.5-approved fuel oils now have source-level transformations. Source layer only — no
exposure multiplication, no MPI join, no model.

| | |
| --- | --- |
| input | `data/interim/c7_5_eppo_monthly_semantic.parquet`, field `monthly_value_strict` |
| channels | `eppo_fo600_channel`, `eppo_fo1500_channel` |
| transformations | price level, 1m / 3m / 12m log change, 3m realized volatility |
| grid | **650** rows (2 x 65 x 5) |
| finite / null | **598 / 52** |
| output | `data/features/c8_eppo_fuel_oil_transformations.parquet` (git-ignored) |

Finite counts per series: price level 64, 1m 62, 3m 61, 12m 52, volatility 60 — preregistered before
the run and independently derived from the declared input lags at run time, matching exactly.

**Null breakdown:** 38 `insufficient_feature_history` (window reaches before 2021-01), 10
`current_month_source_gap` (all five transformations at 2026-04), 4 `input_window_source_gap` (the 1m
change and the volatility at 2026-05, each missing 2026-04). Insufficient prehistory is never
labelled as a source gap.

**Formulas** are imported from C2 (`log_change_pct`, `realized_volatility_pct`,
`FEATURE_DEFINITIONS`): natural log, scaled by 100, `ddof=0`, and **four** price levels for the
volatility. `formula_compatible_with_c2: true` but `source_timing_contract_differs_from_c2: true` —
C2 uses archived first-release values with measured timing and point-in-time support, C8 uses
latest-vintage values under an unmeasured two-month policy lag.

**Availability:** `policy_available_month` is the maximum over the declared input window, verified
equal to `reference_month + 2` on all 650 rows. `source_available_as_of` is null everywhere. All 15
development, 3 purge and 10 locked-test issue months are fully covered for both channels, and the
2026-04 gap is reachable by no registered issue key — kept and reported regardless.

`model_feature_approved` is false on every row. Detail: `docs/c8_eppo_transformation_audit.md`.


### C9 sector-093 exposure and industry-conditioned fuel oil (2026-08-29)

The C8 fuel-oil transformations are now conditioned on **direct** exposure to I/O sector **093**,
*Petroleum refineries* — not the sector-031 crude exposure C3 measured, and not total requirement.

**Direct exposure, all twelve industries** (baht of sector-093 output per baht of industry gross
output, purchasers' prices, 2015 benchmark):

| industry | exposure | | industry | exposure |
| --- | ---: | --- | --- | ---: |
| IND-01 Food | 0.008556 | | IND-07 Non-metallic minerals | **0.034648** |
| IND-02 Textiles | 0.011393 | | IND-08 Metals | **0.026906** |
| IND-03 Wood and paper | 0.010065 | | IND-09 Electronics | 0.005071 |
| IND-04 Refined petroleum | 0.009797 | | IND-10 Machinery | 0.007521 |
| IND-05 Chemicals | **0.064156** | | IND-11 Motor vehicles | 0.008711 |
| IND-06 Rubber and plastics | 0.014321 | | IND-12 Furniture and other | 0.004748 |

Minimum 0.004748, median 0.009931, maximum 0.064156. **Observed zeros: 0. Unresolved: 0.** Both
aggregation forms — output-weighted mean and summed-flow ratio — agree to **1.39e-17**.

Every industry buys refinery products directly, which is the mirror image of the sector-031 result
where ten of twelve were direct-zero, and confirms C5's finding that factories buy refined fuel rather
than crude.

**Proxy fitness.** NESDC's own definition of sector 093 names nine products — gasoline, jet oil, LPG,
asphalt, paraffin, sulfur, kerosene, diesel and fuel oil. A positive coefficient proves purchase from
the refinery-products sector, not of FO 600 or FO 1500. All twelve industries are therefore
`broad_proxy_use_with_caution` at `medium` confidence; none is `high`, and none claims
product-specific evidence.

**Direction and eligibility.** Eleven industries: `cost_pressure`, multiplier +1, eligible. **IND-04
contains sector 093 itself** → `mixed_or_ambiguous`, multiplier `null`, **ineligible** and retained in
the audit table.

**Conditioned grid.** 7,800 rows (2 variants x 12 industries x 65 months x 5 transformations):
**6,578** numeric, **572** source gaps, **650** ineligible. Frozen Phase-A checksum
`d528aba4…`. Development snapshot 1,800 cells (1,650 numeric, 150 masked).

`source_available_as_of` null everywhere; structural availability **2020-03-31**, never backdated to
the 2015 reference year. Both variants share the sector-093 vector and are never added, averaged or
entered together. `model_feature_approved` false on every row.

Detail: `docs/c9_sector093_exposure_decision.md`, `docs/c9_fuel_oil_conditioning_audit.md`.

### C10 development-only design-matrix identifiability audit (2026-08-29)

No new source was acquired. C10 assembles the C9 development snapshot into **two strictly separate**
180 x 5 matrices — one per fuel-oil variant, never a ten-column table — and measures how much distinct
design information the industry conditioning actually creates, **without reading any target,
prediction, metric or locked outcome**.

Every threshold was written into `configs/fuel_oil_development_matrix.yaml` before a single C9 value
was read, hashed to `1c88cdd7…`, and re-asserted before the load and again after the diagnostics.

**Shape, per variant.** 180 rows x 5 columns = 900 cells: **825** numeric, **75** masked. 165 fully
numeric rows and 15 fully masked rows, all IND-04, kept in place with an explicit mask — not dropped
and not zero-filled. All twelve industries and all five transformations are retained; nothing was
removed on a rank or a correlation.

**The structural finding.** C9 built `D[v,g] = E[g] · X[v]`: every eligible industry's design is one
15 x 5 source-time matrix multiplied by its own positive sector-093 exposure. Three independent
numerical checks confirm it, per variant:

| check | fo600 | fo1500 |
| --- | ---: | ---: |
| cross-sectional rank at each of the 15 issue months | 1 | 1 |
| source-time rank / every industry rank / stacked-panel rank | 5 / 5 / 5 | 5 / 5 / 5 |
| max exposure-normalisation residual (tolerance 1e-9) | 7.11e-15 | 3.55e-15 |
| residual against the C8 source transformations | 3.55e-15 | 1.78e-15 |
| max per-industry standardisation residual (tolerance 1e-9) | 4.39e-15 | 2.66e-15 |
| distinct raw designs → normalised → standardised | 11 → 1 → 1 | 11 → 1 → 1 |

So the **165-row stacked panel is eleven scaled copies of fifteen rows**, and it is never reported as
165 independent observations; every rank, condition number, variance and correlation figure is
computed on the 15 x 5 source-time matrix instead.

**Degeneracy.** No exact-zero and no near-zero variance column in either variant, no exact algebraic
duplicate, and all eleven eligible industries produce the same zero-variance classification. Singular
values 73.87 / 72.33 / 31.21 / 19.09 / 5.08 (fo600) and 78.33 / 67.99 / 33.17 / 19.18 / 4.77 (fo1500);
raw condition numbers 14.54 and 16.41, standardised 5.29 and 5.00. Pairwise Pearson and Spearman
correlations are reported for completeness and **select nothing** — no significance test, no channel
choice, no column dropped.

**One preregistered expectation did not reproduce and is reported rather than relaxed.** The frozen
config expected one distinct standardised fingerprint per variant; fo600 produced **11**. The cause is
the fingerprint, not the design: it rounds to 13 significant digits, so two `price_level` cells whose
standardised values sit near zero are resolved below double precision. The preregistered absolute
tolerance on the same matrices puts all eleven industries in **one** equivalence class at a residual of
4.39e-15, and that test decides. No threshold was moved.

**Lineage.** All **1,800** development cells were re-derived independently, each hashing *both*
provenance branches — EPPO → C7 → C7.5 → C8 on one side, NESDC → C3 → C9 Phase A on the other — plus
the variant and issue-month selection rule. Masked cells carry lineage too.

Availability was checked against the recorded fields, never by shifting rows: 0 lag-2 violations and 0
policy violations across all 1,800 cells. `source_available_as_of` stays null, `point_in_time_supported`
false, structural availability 2020-03-31 and never backdated to 2015.

Nothing here promotes either variant to modeling readiness. `predictive_utility_assessed`,
`channel_selected`, `target_joined`, `model_trained`, `model_feature_approved`,
`locked_test_accessed`, `target_join_authorized` and `modeling_authorized` are all **false**.

Detail: `docs/c10_design_matrix_protocol.md`, `docs/c10_design_matrix_audit.md`.

### C11 fuel-oil modeling-architecture decision (2026-08-30)

No new source was acquired and nothing was fitted. C11 selects **how** a fuel-oil correction would
enter a model if one were later authorized, using the predictive estimand and the identification
structure alone — no target value, no model, no predictive performance, no channel selection, and the
locked test stays closed.

All criteria were written into `configs/fuel_oil_modeling_architecture.yaml` before the first
candidate design matrix existed, hashed to `0f815135…`, and re-asserted before the designs were built
and again after the identification audit.

**The estimand** is non-causal: the incremental forecast correction associated with a common national
ex-refinery fuel-oil signal, with the correction amplitude allowed to vary across industries according
to frozen direct purchases from NESDC sector 093. Sector-093 exposure is a structural proxy taken as
given, not an estimated elasticity, and the interaction has no currency reading — the I/O coefficient
is in purchasers' prices and import-inclusive while EPPO measures the ex-refinery stage.

**Three candidates, and why only one survives.**

| candidate | design | verdict |
| --- | --- | --- |
| A — exposure as an eligibility gate | `r = a[g] + sum_f b[g,f] x[t,f]` | Retained as a documented alternative; estimates no exposure-proportional heterogeneity |
| B — separate conditioned industry models | `r = a[g] + sum_f c[g,f] E[g] x[t,f]` | **Rejected as a reparameterisation of A** |
| C — pooled common effect + centred interaction | `r = a[g] + sum_f b[f] x̃[t,f] + sum_f θ[f] e[g] x̃[t,f]` | **Selected** |

Candidate B is rejected on an algebraic identity, not a comparison. Within one industry `E[g]` is a
positive scalar, so B spans exactly A's column space: the orthogonal projectors agree to **6.5e-16**
(FO 600) and **4.4e-16** (FO 1500) across all eleven eligible industries, and `c[g,f] = b[g,f] / E[g]`
recovers one from the other. No data can distinguish them; only the printed coefficients differ.

**Why C is different in kind.** Within one industry `E[g] x[t]` is a rescaling. In a *pooled* panel it
varies across industry **and** time, so the centred interaction is not proportional to the main effect.
That is a change of dimension, not of scale, and it is the whole basis for the selection.

**Feature-only identification audit** (per variant, 165 panel rows × 21 columns — 5 source, 5 centred
interaction, 11 industry indicators, no redundant global intercept):

| check | expected | observed |
| --- | ---: | ---: |
| source block rank | 5 | **5** |
| interaction block rank | 5 | **5** |
| combined source + interaction rank | 10 | **10** |
| full design rank / columns | 21 / 21 | **21 / 21** |
| exact duplicate columns | 0 | **0** |
| exposure replaced by a constant → interaction rank | 0 | **0** |
| global intercept + 11 indicators → rank of 22 columns | rank-deficient | **21 of 22** |

**One preregistered expectation did not reproduce, and it is reported rather than relaxed.** The config
expected per-industry standardisation of the interaction to drop the *stacked* combined rank from 10 to
5; the observed stacked rank stayed **10**. The preregistered number was the wrong measurement, not a
wrong finding: per-industry standardisation maps `e[g]·x̃` to `sign(e[g])·x̃`, so each industry's combined
block does fall from rank 10 to **rank 5** — but the centred exposures carry both signs, so `+x̃` and
`−x̃` span two directions and the stack keeps rank 10. What is destroyed is the *magnitude*: **eleven**
distinct exposure-proportional interaction blocks collapse to **two** sign groups, so θ could be
identified only up to a two-group split. The sign identity holds to 4.4e-16. The preregistered value
was not rewritten; the gate that wrongly depended on the counterfactual was corrected, and that
correction is recorded in the decision artifact as having been made after observation.

**Accounting, kept honest.** 165 panel rows, but only **15** unique issue months and 15 issue-month
clusters. Cross-sectional rows help identify exposure heterogeneity; they create no additional
fuel-oil histories. Overlapping monthly transformations and serial dependence remain. A full-rank
design is not evidence of predictive usefulness, and parameter-count feasibility is not statistical
power. No p-value, coefficient uncertainty or outcome-related effective sample size was computed.

**IND-04** stays excluded from the correction because its direction is `mixed_or_ambiguous`, keeps the
operational benchmark prediction, is never converted to an observed zero or forced to +1, and must not
be dropped from evaluation denominators. **FO 600 and FO 1500** remain co-equal separate variants:
`primary_channel_selected: false`, `structural_basis_for_channel_preference_available: false`, and a
design holding both is refused by name.

Selecting an architecture grants no permission to run it. `target_join_authorized`,
`development_modeling_authorized`, `locked_test_evaluation_authorized`, `model_fitted` and
`predictive_performance_computed` are all **false**.

Detail: `docs/c11_architecture_decision_protocol.md`, `docs/c11_architecture_decision.md`.

### C11-R1 governance closure over the C11 status (2026-08-30)

No source was acquired and nothing was fitted. C11-R1 corrects how the C11 architecture decision may be
described, changing none of its mathematics and removing none of its disclosures. The C11 files are
left **byte-identical** and pinned; the correction is a **sidecar erratum**, because a correction
written into a generated document is erased by the next regeneration.

Two facts C11 reported together are recorded separately here. The decision is **dependency-clean** — it
reproduces exactly from C8/C9 with **0** D-series paths opened. The original execution was **not
outcome-blind** — a development metric artifact was opened during it. No umbrella `outcome_free: true`
appears anywhere.

One of the nine mandatory gates did not pass as preregistered: it expected a *stacked* rank to fall
from 10 to 5 under a forbidden preprocessing, and the stacked rank stayed **10** because the centred
exposures carry both signs. The collapse is real but sits elsewhere — within-industry combined rank
falls **10 → 5** and eleven exposure-proportional interaction blocks collapse to **two** sign groups.
No tolerance moved; the gate was measuring the wrong quantity, and it was corrected after the result
was visible. `architecture_decision_cleanly_preregistered: false`.

Status: **`exploratory_supported_after_documented_specification_correction`**. D5 is authorized as a
development-only exploratory evaluation; channel selection, purge metrics, confirmatory claims and the
locked test are not.

Detail: `docs/c11r1_governance_decision.md`, `docs/c11_architecture_decision.errata.md`.

### D5 development-only pooled fuel-oil interaction evaluation (2026-08-30)

No source was acquired. D5 executes the one thing C11-R1 authorized: a development-only exploratory
evaluation of the Candidate-C pooled architecture on the fifteen registered issue months, with FO 600
and FO 1500 as co-equal separate variants.

**The answer is inconclusive for all four variant-horizons.** The model is not better than the
operational D3 benchmark on the point estimate anywhere — h=1 macro MAE 17.111 and 17.167 against
17.094; h=3 18.210 and 18.207 against 16.634 — and every paired 95% interval, clustered by issue month,
straddles zero. Event safety failed in all four cases: the model missed more high-stress months (≥85)
than the benchmark did. Under the frozen decision rule the status is `inconclusive` everywhere.

Counts reconcile exactly: 720 predictions, 720 distinct keys, 720 distinct lineage checksums, 660
modelled and 60 IND-04 passthrough; training issues 21/35 (h=1) and 18/32 (h=3) at the first and last
outer issues, matching the preregistered table for both variants. The h=1 benchmark reproduces D3's
registered macro MAE of 17.094469 from the formula rather than by copying a metric artifact, verified
independently at a maximum gap of 0.0 across all 720 benchmark scores.

The protocol was frozen to disk, read back and hashed before the guarded target reader opened:
720 target reads, 0 before a prediction was frozen. Nothing is approved — `channel_selected`,
`purge_evaluated`, `locked_test_accessed` and `model_feature_approved` are all false.

Detail: `docs/d5_modeling_protocol.md`, `docs/d5_assembly_audit.md`, `docs/d5_development_results.md`.

### C12 EPPO fuel-oil modeling-channel closure (2026-08-30)

No source was acquired and nothing was recomputed. C12 closes the EPPO sector-093 fuel-oil channel for
further predictive modeling after D5 failed to demonstrate incremental signal, and it does so without
rerunning a model, recomputing a metric, selecting a channel, evaluating a purge origin or opening the
locked test.

**The conclusion is `incremental_signal_not_demonstrated_in_registered_development_evaluation`.** It is
not a claim that fuel oil has no effect. Fifteen issue-month clusters cannot rule an effect out, and D5
never tried to; six over-reaching conclusions are refused by name and in prose form.

**Closure applies to modeling use only.** The official EPPO documents remain valid evidence, the
C7/C7.5 semantic decisions are retained, the C8 transformations and sector-093 exposure remain
reproducible, and the interaction architecture remains mathematically identifiable. What is closed is
entry into further operational modeling and any locked-test access for this channel. A guard raises if
closure is used to mark a source row, transformation or exposure erroneous.

**19 artifacts pinned across C7 through D5; 0 deleted, 0 modified.** Preservation supports audit and
portfolio reproducibility and implies no continued modeling eligibility. Reopening requires evidence
external to D5's performance — a product-specific consumption crosswalk, a newer compatible I/O table,
verified point-in-time release evidence, a longer compatible target history, a proven material
implementation error, or a pre-registered new external hypothesis — carrying nine required fields
including a checksum, an availability date and a superseding decision-log entry. A new specification
alone is not new evidence.

Detail: `docs/c12_channel_closure.md`, `schemas/fuel_oil_reopening_evidence.schema.yaml`.

### E1 development-programme closeout (2026-08-30) — navigation

No source was acquired and no metric was recomputed. E1 synthesises the registered results from B1
through C12 into a technical closeout, a portfolio case study and an evidence ledger.

Nothing in this inventory is reinterpreted by E1. Each source entry above stands as written; the
closeout adds only navigation and a consolidated view of what each source's timing evidence supports:

| source family | values | point-in-time status | main limitation |
| --- | --- | --- | --- |
| OIE MPI target | latest vintage | target vintages unavailable | not a real-time target panel |
| World Bank Pink Sheet | archived first release | feature side supported | target side latest vintage |
| NESDC I/O | official 2015 Final | time-invariant structural input | old benchmark, broad sectors |
| EPPO refinery prices | latest-vintage documents | not point-in-time | policy lag 2, broad proxy |

Evidence quality is **not** equal across these four merely because the transformation formulas match.

Detail: `docs/e1_technical_closeout.md`, `docs/e1_evidence_ledger.json`.
