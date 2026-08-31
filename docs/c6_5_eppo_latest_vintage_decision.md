# Task C6.5 - EPPO Latest-Vintage Use Decision

*Generated 2026-08-28T16:51:31.234074+00:00. Config `eppo_latest_vintage_policy_v1`.*

## Decision: `proceed_exploratory_release_lag_aware_latest_vintage`

EPPO ex-refinery prices may be used in a **release-lag-aware latest-vintage
exploratory** analysis, on the same footing D3 already put the MPI target.
That permission is narrow, and the fields below say exactly how narrow.

## Measured lag versus policy lag

| field | value |
| --- | --- |
| `minimum_verified_publication_lag_months` | **`None`** |
| `operational_policy_lag_months` | **2** |
| `operational_lag_is_measured` | **`False`** |
| `operational_lag_basis` | `conservative_project_policy` |

**No publication delay was measured.** The two-month lag is a conservative
assumption the project imposes on itself, not an observation about EPPO.

> At forecast issue month t, an EPPO monthly source observation may refer at latest to reference month t-2. This is a conservative policy assumption. It is NOT a measured publication delay.

| issue month *t* | latest permitted reference month |
| --- | --- |
| 2024-01 | **2023-11** |
| 2025-03 | **2025-01** |
| 2026-05 | **2026-03** |

`same_month_use_permitted: false`, `publication_lag_1m_use_permitted: false`.

## Availability fields stay separate

| reference month | `source_available_as_of` | `policy_available_month` | basis |
| --- | --- | --- | --- |
| 2022-01 | `None` | `2022-03` | `conservative_policy_not_historical_measurement` |
| 2024-01 | `None` | `2024-03` | `conservative_policy_not_historical_measurement` |
| 2026-05 | `None` | `2026-07` | `conservative_policy_not_historical_measurement` |

A policy-derived month is **never** written into `source_available_as_of`;
that field means the source is evidenced to have been public by that date,
and it stays null for every historical observation.

## Evidence boundaries

* `legacy_archive_status`: `tested_legacy_urls_no_longer_expose_original_archive`
* `historical_timing_status`: `not_reconstructable_from_sources_inspected_in_c6`
* `monthly_presence_coverage`: `complete`
* `complete_daily_document_validation`: `False`
* `point_in_time_values_supported`: `False`

> Absence from the inspected mechanisms is not proof that no historical publication evidence exists anywhere. C6 probed the current WordPress archive, its REST index, sitemaps, RSS and the legacy Joomla paths; other mechanisms, offline records or a direct request to EPPO were not exercised.

Superseded wording:
* ~~the legacy archive no longer exists~~
* ~~historical timing can never be verified~~
* ~~all daily values in the required window were validated~~
* ~~65/65 month coverage means a complete daily archive~~
* ~~archive depth alone makes every transformation feature-ready~~

## Archive presence is not complete ingestion

| level | status |
| --- | --- |
| `monthly_document_presence_verified` | `True` |
| `complete_daily_inventory_discovered` | `True` |
| `complete_daily_documents_downloaded` | `False` |
| `complete_daily_documents_validated` | `False` |
| `monthly_aggregation_contract_approved` | `False` |

> The 254 validated documents are an AUDIT SAMPLE spanning all required months. They are not a complete daily ingestion of the 1,315 discovered document-days, and the 722-row partial audit table is not a production price series.

## The 43 captures

| evidence class | records |
| --- | ---: |
| `capture_identity_unverified` | 43 |

* usable upper bounds: **0**
* any capture proves a first release: **`False`**
* archived bytes fetched: `False`, identity validated: `False`

> No first-release date is established by any capture, so the minimum verified publication lag stays null. Delay statistics below, if any, describe upper bounds only and are never used to set the operational lag.

## Rationale

**For:**
* the overall evaluation is already latest-vintage on the MPI target side
* D3 is explicitly a release-lag-aware latest-vintage evaluation, not a real-time backtest
* EPPO has strong structural alignment with I/O sector 093 (C5)
* required-month document presence is complete (65/65 and 53/53)
* the exact ex-refinery fields can be parsed, stage-separated from wholesale and retail
* no same-date revision was observed in the audited sample
* the policy imposes a conservative two-month delay
* all future results must remain exploratory

**Against:**
* complete daily archive validation is unfinished (254 of 1,315 document-days)
* release timing is unverified; every upload timestamp is a 2026 migration stamp
* absence of observed revisions does not prove no historical revision occurred
* migration may have changed filenames, metadata or bytes
* a two-month lag does not make latest-vintage values point-in-time
* the target side remains latest-vintage as well
* the source cannot support a fully real-time claim

## Series decisions

| series | exact label | C7 ingestion | semantic status |
| --- | --- | --- | --- |
| `eppo_ex_refinery_fo1500_2s` | `FO 1500 (2) 2%S` | `True` | `stable_in_audited_window` |
| `eppo_ex_refinery_fo600_2s` | `FO 600 (1) 2%S` | `True` | `stable_in_audited_window` |
| `eppo_ex_refinery_hsd` | `H-DIESEL` | `conditional` | `january_2024_definition_gap` |

H-DIESEL is **conditional**: 22 days in
January 2024 publish only blend definitions. `silent_blend_substitution_permitted: False`, 
`imputation_permitted: False`. The gap stands. January 2024 publishes only blend definitions, so ordinary H-DIESEL has no value those days. It is neither filled with a blend nor dropped silently.

## Transformation status

| transformation | historical depth sufficient | source ready |
| --- | --- | --- |
| `price_level` | `True` | `False` |
| `log_change_1m_pct` | `True` | `False` |
| `log_change_3m_pct` | `True` | `False` |
| `log_change_12m_pct` | `True` | `False` |
| `realized_volatility_3m_pct` | `True` | `False` |

Depth and readiness are different questions. Blockers:
* complete daily ingestion not performed
* monthly aggregation contract not approved
* availability policy not yet enforced in a built table

## C7 authorization boundary

* `c7_full_archive_ingestion_authorized`: `True`
* `c7_monthly_source_aggregation_authorized`: `conditional`
* `c7_predictive_feature_creation_authorized`: `False`
* `c7_target_join_authorized`: `False`
* `c7_modeling_authorized`: `False`

> Monthly aggregation stays conditional until C7 retrieves and validates the complete required daily archive.

`eligible_for_confirmatory_claims: False`, 
`eligible_for_locked_test: False`, 
`feature_semantics_approved: False`, 
`model_feature_approved: False`.
