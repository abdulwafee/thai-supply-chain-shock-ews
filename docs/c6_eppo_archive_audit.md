# Task C6 - EPPO Ex-Refinery Archive Audit

*Generated 2026-08-28T10:13:02.250196+00:00. Config `eppo_ex_refinery_archive_v1`.*

## Outcome: `values_retrievable_timing_unresolved`

The archive is deep and complete. What cannot be established is **when each
document became public**, and those are different questions.

## Discovery

* mechanism: `official_wordpress_rest`
* termination: **`api_termination_400_at_page_54`** (an observed, bounded condition)
* documents discovered: **5233**
* distinct effective dates: **4976**
* span: **2002-02-03 .. 2026-08-28**
* guessed paths counted as discovery: **0**
* search-engine seeds counted: **0**

| entry point | state |
| --- | --- |
| `category_archive` | `not_probed_offline_run` |
| `current_landing` | `not_probed_offline_run` |
| `legacy_joomla` | `not_probed_offline_run` |
| `robots` | `not_probed_offline_run` |
| `rss_feed` | `not_probed_offline_run` |
| `sitemap_index` | `not_probed_offline_run` |
| `wordpress_rest_media` | `not_probed_offline_run` |
| `wordpress_rest_posts` | `not_probed_offline_run` |

## Required windows

| window | months | document-days | missing months |
| --- | --- | ---: | --- |
| `operational_level_price` | 53/53 | 1076 | none |
| `transformation_parity` | 65/65 | 1315 | none |

Coverage from 2022-01 is **not** sufficient for every transformation: a
twelve-month change referencing 2022-01 needs 2021-01 prehistory, which is
why both windows are reported separately.

## Retrieval and validation

* retrieved: **256**, valid **254**, rejected **2**
* format counts: {'xls_ole2': 141, 'xlsx_zip': 115}
* duplicate-content groups: **5**, spanning incompatible dates: **0**
* rejected — wrong_date_attachment: document says 2022-12-06, archive item says 2022-12-05: 1
* rejected — wrong_date_attachment: document says 2025-01-24, archive item says 2025-01-25: 1

## Semantic regimes

| series | exact label | layout | start | end | n |
| --- | --- | --- | --- | --- | ---: |
| `eppo_ex_refinery_fo1500_2s` | `FO 1500 (2) 2%S` | `xls_2021` | 2021-01-04 | 2023-01-31 | 140 |
| `eppo_ex_refinery_fo1500_2s` | `FO 1500 (2) 2%S` | `xlsx_2023` | 2023-07-03 | 2026-05-31 | 114 |
| `eppo_ex_refinery_fo600_2s` | `FO 600 (1) 2%S` | `xls_2021` | 2021-01-04 | 2023-01-31 | 140 |
| `eppo_ex_refinery_fo600_2s` | `FO 600 (1) 2%S` | `xlsx_2023` | 2023-07-03 | 2026-05-31 | 114 |
| `eppo_ex_refinery_hsd` | `H-DIESEL` | `xls_2021` | 2021-01-04 | 2023-01-31 | 140 |
| `eppo_ex_refinery_hsd` | `H-DIESEL` | `xlsx_2023` | 2023-07-03 | 2026-05-31 | 92 |

## Availability

**Point-in-time: `not_supported`** — 0 of 254 observations carry supporting evidence (0.0%).

| evidence status | issues |
| --- | ---: |
| `migration_timestamp_only` | 254 |

> Every WordPress media upload timestamp falls in 2026, the site migration window. A migration timestamp records re-hosting, not first publication, and is never used as availability.

## Revisions

| class | keys |
| --- | ---: |
| `duplicate_document` | 15 |
| `single_vintage_only` | 707 |

> A different value on a different effective date is ordinary market or policy price movement, not a revision, and never enters this classification.

## Eligibility

* `current_document_semantics_verified`: `True`
* `historical_archive_verified`: `True`
* `historical_values_retrievable`: `True`
* `historical_release_timing_verified`: `False`
* `point_in_time_values_supported`: `not_supported`
* `level_price_history_eligible`: `True`
* `one_month_change_history_eligible`: `True`
* `three_month_change_history_eligible`: `True`
* `three_month_volatility_history_eligible`: `True`
* `twelve_month_change_history_eligible`: `True`
* `monthly_aggregation_contract_approved`: `False`
* `feature_semantics_approved`: `False`
* `model_feature_approved`: `False`

History eligibility is about PREHISTORY DEPTH only. Every transformation remains gated on release timing, which is not verified for the archive as a whole.
