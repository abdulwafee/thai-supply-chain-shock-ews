# Task C7 - Full EPPO Daily Archive Ingestion

*Generated 2026-08-28T17:50:30.610419+00:00. Config `eppo_monthly_source_v1`.*

Source ingestion and source-level aggregation only. A monthly mean of a
published price is not a predictive feature, and none was created.

## Upstream invariants

All C6/C6.5 invariants reproduced: **True** (21 checks).

| check | expected | actual |
| --- | --- | --- |
| `discovered_media_documents` | `5233` | `5233` |
| `distinct_effective_dates` | `4976` | `4976` |
| `parity_document_days` | `1315` | `1315` |
| `operational_document_days` | `1076` | `1076` |
| `parity_months` | `65` | `65` |
| `operational_months` | `53` | `53` |
| `c6_documents_retrieved` | `256` | `256` |
| `c6_documents_validated` | `254` | `254` |
| `c6_partial_audit_rows` | `722` | `722` |
| `c6_table_is_partial_audit` | `True` | `True` |
| `c6_daily_ingestion_incomplete` | `False` | `False` |
| `c6_daily_validation_incomplete` | `False` | `False` |
| `monthly_aggregation_unapproved_upstream` | `False` | `False` |
| `operational_policy_lag_months` | `2` | `2` |
| `operational_lag_is_measured` | `False` | `False` |
| `minimum_verified_publication_lag_months` | `None` | `None` |
| `point_in_time_values_supported` | `False` | `False` |
| `hsd_missing_days_january_2024` | `22` | `22` |
| `hsd_gaps_all_in_january_2024` | `True` | `True` |
| `fo600_label_stable` | `['FO 600 (1) 2%S']` | `['FO 600 (1) 2%S']` |
| `fo1500_label_stable` | `['FO 1500 (2) 2%S']` | `['FO 1500 (2) 2%S']` |

## Ingestion denominator

The denominator is the officially discovered inventory, and each stage
can only shrink. A discovered day is **not** a validated day.

| state | count |
| --- | --- |
| `discovered_media_records` | 1336 |
| `distinct_document_days` | 1315 |
| `document_days_with_one_attachment` | 1296 |
| `document_days_with_multiple_attachment_candidates` | 19 |
| `retrieval_attempts` | 1336 |
| `http_successes` | 1333 |
| `format_valid_files` | 1333 |
| `content_valid_files` | 1331 |
| `rejected_attachments` | 2 |
| `duplicate_files` | 21 |
| `content_equivalent_duplicate_files` | 0 |
| `conflicting_same_date_files` | 0 |
| `valid_canonical_document_days` | 1310 |
| `unresolved_document_days` | 5 |

`discovered_days_reported_as_validated`: `False`

Retrieval status counts: `cached_checksum_verified` 1333, `http_error` 3

## Workbook layout regimes

Every sheet of every document was inspected and every column resolved by
label. No positional fallback exists, so an unrecognised layout is
rejected rather than guessed.

| regime | status | sheet | tax column | first | last | documents |
| --- | --- | --- | --- | --- | --- | --- |
| `xls_2021` | `known_regime` | `โครงสร้างราคา ` | `TAX` | 2021-01-04 | 2023-06-02 | 584 |
| `xlsx_2023` | `known_regime` | `Oil Price Structure` | `EXCISE TAX` | 2023-06-06 | 2026-05-31 | 746 |
| `xlsx_zip|โครงสร้างราคา|excise_tax` | `newly_observed_regime` | `โครงสร้างราคา` | `EXCISE TAX` | 2024-03-07 | 2024-03-07 | 1 |

### February-June 2023, previously unsampled

Prior status `unsampled_transition_interval`. 99 documents inspected, 99 valid. Resolution: `resolved_into_known_regimes`.

| regime | documents | first | last |
| --- | --- | --- | --- |
| `xls_2021` | 80 | 2023-02-01 | 2023-06-02 |
| `xlsx_2023` | 19 | 2023-06-06 | 2023-06-30 |

Additional regime discovered inside the interval: `none`.

## Product identity

Price stage `EX-REFIN.`, unit `BAHT/LITRE`. Units observed: `BAHT/LITRE`.

| series | exact labels in the daily table |
| --- | --- |
| `eppo_ex_refinery_fo1500_2s` | `FO 1500 (2) 2%S`, `FO 1500 2%S` |
| `eppo_ex_refinery_fo600_2s` | `FO 600 (1) 2%S`, `FO 600 2%S` |
| `eppo_ex_refinery_hsd` | `H-DIESEL` |

### Every label the archive published

| exact label | days | first | last | audited series | blend |
| --- | --- | --- | --- | --- | --- |
| `FO 1500 (2) 2%S` | 1244 | 2021-01-04 | 2026-05-31 | `eppo_ex_refinery_fo1500_2s` | `False` |
| `FO 1500 2%S` | 66 | 2024-07-23 | 2024-10-28 | `eppo_ex_refinery_fo1500_2s` (variant) | `False` |
| `FO 600 (1) 2%S` | 1244 | 2021-01-04 | 2026-05-31 | `eppo_ex_refinery_fo600_2s` | `False` |
| `FO 600 2%S` | 66 | 2024-07-23 | 2024-10-28 | `eppo_ex_refinery_fo600_2s` (variant) | `False` |
| `H-DIESEL` | 1005 | 2021-01-04 | 2026-05-31 | `eppo_ex_refinery_hsd` | `False` |
| `H-DIESEL 20` | 4 | 2026-03-27 | 2026-04-01 | `-` | `True` |
| `H-DIESEL B10` | 151 | 2023-09-18 | 2024-04-30 | `-` | `True` |
| `H-DIESEL B20` | 972 | 2021-01-04 | 2026-05-31 | `-` | `True` |
| `H-DIESEL B7` | 948 | 2021-01-04 | 2024-12-17 | `-` | `True` |

### Unconfirmed fuel-oil label variant

132 daily rows carry a label that drops the
table's ordinal index. The documents are kept; the equivalence is not
asserted (`equivalence_established`: `False`),
and every month that touches one is blocked from approval.

> The archive drops the table's ordinal index from both fuel-oil labels for a bounded interval. C7 keeps the documents, marks the rows, and refuses to average a month that touches one; whether the labels name the same series is a semantic decision outside an ingestion task.

## Ordinary H-DIESEL availability

Ordinary `H-DIESEL` is published on 1005 of
1310 validated document-days. On
305 days only blend-specific products appear.

| absence span | document-days |
| --- | --- |
| 2023-09-18 .. 2024-12-17 | 305 |

Blend labels published during the absence: `H-DIESEL B10` (151 days), `H-DIESEL B20` (276 days), `H-DIESEL B7` (305 days).

> C6 sampled 254 of 1,315 document-days. The only sampled days that fell inside the absence were the 22 in January 2024, so C6's finding was correct for what it observed and understated the extent. No blend price is substituted for any of these days.

### January 2024, the month C6 reported

| field | value |
| --- | --- |
| valid document-days in month | 22 |
| days with ordinary H-DIESEL | 0 |
| days with blend only | 22 |
| absent for the entire month | `True` |
| monthly value | `None` |
| aggregation status | `semantic_definition_gap` |
| quality flag | `ordinary_h_diesel_not_published_blend_substitution_prohibited` |
| blend substitution permitted | `False` |
| interpolation permitted | `False` |
| month removed silently | `False` |
| zero stored | `False` |

## Duplicates, conflicts and wrong-date attachments

| finding | count |
| --- | --- |
| byte-identical duplicate documents | 21 |
| content-equivalent duplicates | 0 |
| same-date conflicting values | 0 |
| wrong-date attachments | 2 |
| unresolved document-days | 5 |

* `pt-price-st-2022-12-5.xls` is listed under 2022-12-05 but its
  content is dated 2022-12-06. It is not reassigned and not
  counted for the listing date. A separately valid official document
  covers the listing date: `False`; the internal date: `False`.
* `pt-price-st-2025-1-25.xlsx` is listed under 2025-01-25 but its
  content is dated 2025-01-24. It is not reassigned and not
  counted for the listing date. A separately valid official document
  covers the listing date: `False`; the internal date: `False`.

Unresolved document-days (discovered officially, attachment not usable): 2022-12-05, 2025-01-25, 2026-04-17, 2026-04-18, 2026-04-19.

## Canonical daily table

`data/interim/c7_eppo_daily_prices.parquet` - 3625 rows, key `series_id + effective_date + semantic_regime_id`, 2021-01-04 to 2026-05-31.

| series | rows |
| --- | --- |
| `eppo_ex_refinery_fo1500_2s` | 1310 |
| `eppo_ex_refinery_fo600_2s` | 1310 |
| `eppo_ex_refinery_hsd` | 1005 |

## Monthly aggregation

Rule `arithmetic_mean_of_validated_observed_official_document_days` (version `c7_v1`), unit `BAHT/LITRE`.

> Mean ex-refinery price across validated official EPPO document-days observed in the completed reference month.

It is not a calendar-day mean, not a trading-day mean, not a transaction
price, and not a point-in-time value.

195 rows covering 2021-01 to 2026-05.

| status | product-months |
| --- | --- |
| `approved` | 162 |
| `semantic_definition_gap` | 16 |
| `unit_or_definition_break` | 8 |
| `unresolved_document_identity` | 6 |
| `unresolved_document_retrieval` | 3 |

### Approval

`monthly_aggregation_contract_approved`: **False**. Blocking series: `eppo_ex_refinery_fo1500_2s`, `eppo_ex_refinery_fo600_2s`, `eppo_ex_refinery_hsd`

| series | approved months | not approved | series approved |
| --- | --- | --- | --- |
| `eppo_ex_refinery_fo1500_2s` | 58/65 | 2022-12 `unresolved_document_identity`, 2024-07 `unit_or_definition_break`, 2024-08 `unit_or_definition_break`, 2024-09 `unit_or_definition_break`, 2024-10 `unit_or_definition_break`, 2025-01 `unresolved_document_identity`, 2026-04 `unresolved_document_retrieval` | `False` |
| `eppo_ex_refinery_fo600_2s` | 58/65 | 2022-12 `unresolved_document_identity`, 2024-07 `unit_or_definition_break`, 2024-08 `unit_or_definition_break`, 2024-09 `unit_or_definition_break`, 2024-10 `unit_or_definition_break`, 2025-01 `unresolved_document_identity`, 2026-04 `unresolved_document_retrieval` | `False` |
| `eppo_ex_refinery_hsd` | 46/65 | 2022-12 `unresolved_document_identity`, 2023-09 `semantic_definition_gap`, 2023-10 `semantic_definition_gap`, 2023-11 `semantic_definition_gap`, 2023-12 `semantic_definition_gap`, 2024-01 `semantic_definition_gap`, 2024-02 `semantic_definition_gap`, 2024-03 `semantic_definition_gap`, 2024-04 `semantic_definition_gap`, 2024-05 `semantic_definition_gap`, 2024-06 `semantic_definition_gap`, 2024-07 `semantic_definition_gap`, 2024-08 `semantic_definition_gap`, 2024-09 `semantic_definition_gap`, 2024-10 `semantic_definition_gap`, 2024-11 `semantic_definition_gap`, 2024-12 `semantic_definition_gap`, 2025-01 `unresolved_document_identity`, 2026-04 `unresolved_document_retrieval` | `False` |

## Availability

`source_available_as_of` is null in 195 of 195 monthly rows.

| issue month | latest permitted reference month |
| --- | --- |
| 2024-01 | **2023-11** |
| 2025-03 | **2025-01** |
| 2026-05 | **2026-03** |

`policy_available_month` = reference month + 2 months, basis `conservative_policy_not_historical_measurement`, `operational_lag_is_measured` `False`, `minimum_verified_publication_lag_months` `None`.

## Transformation status

| series | source ready for transformation | feature created |
| --- | --- | --- |
| `eppo_ex_refinery_fo1500_2s` | `False` | `False` |
| `eppo_ex_refinery_fo600_2s` | `False` | `False` |
| `eppo_ex_refinery_hsd` | `False` | `False` |

No log change, percentage change, lagged price, realized volatility,
z-score, shock flag, exposure interaction, correlation, mutual
information, Granger test, feature importance or predictive metric was
calculated. No MPI target was joined and no model was trained.

Content checksum `79f8d35579c14e8d16eea868a837e12d21f6c42162cf09d41057865648953a7d`.

