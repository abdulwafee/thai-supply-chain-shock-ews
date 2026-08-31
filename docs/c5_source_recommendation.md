# Task C5 - Source Recommendation for C6

## Recommended family: `EPPO_PETROLEUM`

**Energy Policy and Planning Office, Ministry of Energy**

* published label: `PRICE STRUCTURE OF PETROLEUM PRODUCTS - EX-REFIN.`
* unit: `BAHT/LITRE (LPG in BAHT/KILOGRAM)`
* price basis: `ex_refinery_producer_price_before_excise_municipal_tax_oil_fund_and_retail_margin`
* geography: Thailand, Bangkok reference structure
* frequency: `daily_snapshot_one_workbook_per_effective_date`
* mapped I/O sector: **093 Petroleum refineries**

### Taxes and margins

EXCLUDED from the ex-refinery column. The workbook reports EXCISE TAX, MUNICIPAL TAX, OIL FUND, CONSERVATION FUND and WHOLESALE separately, so the producer stage is explicitly separable from the retail stage.

### Structural gap addressed

Sector 093 is a leading mediator for every direct-zero Brent industry and the single largest for IND-07. Ex-refinery diesel and fuel oil price the stage industries actually buy, which Brent does not.

### Coverage limitation - explicit and unresolved

EXPLICIT AND UNRESOLVED. Only the most recent daily files are exposed on the page. Probing the observed /uploads/YYYY/MM/ pattern returned 404 for 2022-2025, but that is NOT evidence of absence: 2018 retail files are served from a 2026 upload folder, so the site re-hosts historical files under migration-time folders and folder-date inference is unreliable. Archive depth back to 2022-01 is UNESTABLISHED and is exactly what C6 must resolve before any feature is built.

### Publication timing evidence

Each workbook carries its own effective date in-sheet (row 4) and in its filename. HEAD is blocked site-wide, so Last-Modified is unavailable; the in-sheet effective date is the timing evidence and is not a download time.

### Proxy limitations

Ex-refinery is a national reference structure, not an industry-specific contract price; large industrial buyers negotiate away from it.

## Why the others were not selected

### `MOC_PPI`

* state: `not_executed_source_unreachable`
* failed criteria: series_definition_and_unit_documented, maps_to_purchased_intermediate_sector, operational_timing_establishable, coverage_adequate_or_limitations_explicit, no_unresolved_definition_break, availability_representable_without_download_time

indexpr.moc.go.th and price.moc.go.th both returned HTTP 403 to every request, including with full browser headers; tradereport.moc.go.th returned 200 but is a trade-statistics portal, not the PPI series. The 403 is a bot filter, a fact about this mechanism at this moment. The PPI is very likely published; it simply could not be verified here, so its exact series label, unit and coverage remain undocumented.

### `ERC_ELECTRICITY`

* state: `not_executed_source_unreachable`
* failed criteria: series_definition_and_unit_documented, operational_timing_establishable, coverage_adequate_or_limitations_explicit, no_unresolved_definition_break, availability_representable_without_download_time

erc.or.th timed out on the landing page and returned 404 on the tariff path probed. EPPO mirrors Ft and retail/wholesale tariff pages, but the workbook served there (pt-price-st) is the petroleum structure file, so no distinct electricity series was verified. Electricity (sector 135) is the most widespread mediator, so this gap matters and remains open.

### `BOT_FX`

* state: `reachable_but_out_of_scope`
* failed criteria: maps_to_purchased_intermediate_sector, addresses_documented_structural_gap

Audited only as an import-price transmission factor, as instructed. An exchange rate is not the price of an I/O commodity sector and must never be mapped to one; it modulates the baht cost of imported inputs. It therefore fails the purchased-intermediate-sector criterion by construction, not by quality.

## What this recommendation is

* `source_selected_for_c6_audit`: `True`
* `feature_semantics_approved`: `False`
* `model_feature_approved`: `False`
* `ingested_into_production`: `False`

## Selection provenance

* `selection_used_target_outcomes`: `False`
* `d4_metrics_used_for_source_ranking`: `False`
* `locked_test_accessed`: `False`

Ranking used structural and provenance evidence only. The gate refuses to
run if any candidate carries a performance field, so no series could be
preferred because it once produced a lower MAE.
