# Task C7.5 - EPPO Product Semantics and Aggregation Contract Closure

*Generated 2026-08-29T03:33:08.280163+00:00. Config `eppo_product_semantics_v1`.*

Semantic decision and aggregation contract only. C7 raw documents, exact
displayed labels, canonical daily values and document checksums are
unchanged; everything here is a layer above them.

## C7 invariants

All reproduced: **True** (25 checks).

| check | expected | actual |
| --- | --- | --- |
| `discovered_media_records` | `1336` | `1336` |
| `distinct_document_days` | `1315` | `1315` |
| `http_successes` | `1333` | `1333` |
| `content_valid_files` | `1331` | `1331` |
| `byte_identical_duplicates` | `21` | `21` |
| `conflicting_same_date_values` | `0` | `0` |
| `wrong_date_attachments` | `2` | `2` |
| `failed_retrievals` | `3` | `3` |
| `valid_canonical_document_days` | `1310` | `1310` |
| `unresolved_document_days` | `5` | `5` |
| `canonical_daily_rows` | `3625` | `3625` |
| `monthly_rows` | `195` | `195` |
| `fo600_daily_rows` | `1310` | `1310` |
| `fo1500_daily_rows` | `1310` | `1310` |
| `hsd_daily_rows` | `1005` | `1005` |
| `fo600_monthly_approved` | `58` | `58` |
| `fo1500_monthly_approved` | `58` | `58` |
| `hsd_monthly_approved` | `46` | `46` |
| `fuel_oil_variant_document_days` | `66` | `66` |
| `ordinary_hsd_absent_document_days` | `305` | `305` |
| `hsd_gap_start` | `2023-09-18` | `2023-09-18` |
| `hsd_gap_end` | `2024-12-17` | `2024-12-17` |
| `aggregation_rule_version` | `c7_v1` | `c7_v1` |
| `monthly_aggregation_contract_approved` | `False` | `False` |
| `all_source_available_as_of_null` | `True` | `True` |

## Fuel-oil label equivalence

| canonical product | label A | label B | decision |
| --- | --- | --- | --- |
| `eppo_ex_refinery_fo600_2s` | `FO 600 (1) 2%S` | `FO 600  2%S` | **`equivalence_established`** |
| `eppo_ex_refinery_fo1500_2s` | `FO 1500 (2) 2%S` | `FO 1500 2%S` | **`equivalence_established`** |

### The eight-condition gate

| condition | `600` (`eppo_ex_refinery_fo600_2s`) | `1500` (`eppo_ex_refinery_fo1500_2s`) |
| --- | --- | --- |
| `direct_semantic_evidence_present` | `True` | `True` |
| `unit_unchanged` | `True` | `True` |
| `price_stage_unchanged` | `True` | `True` |
| `product_number_unchanged` | `True` | `True` |
| `sulphur_grade_unchanged` | `True` | `True` |
| `no_contradictory_evidence` | `True` | `True` |
| `labels_never_co_occur` | `True` | `True` |
| `structural_corroboration_consistent` | `True` | `True` |

### Direct semantic evidence

**`eppo_ex_refinery_fo600_2s`** - 2 direct item(s):

* `source_controlled_schema_or_data_dictionary` - The official workbook carries a Thai companion sheet whose product rows are formula-bound to the English sheet. Both English label forms are bound to one identical Thai product name, and that name carries no ordinal marker.
  * source: EPPO price-structure workbook, sheet โครงสร้างราคาน้ำมัน
  * observed in 471 documents, 2024-07-23 to 2026-05-31
  * quotation: `น้ำมันเตา 600 กำมะถันไม่เกิน 2%`
* `official_formula_document_names_product_without_ordinal` - In every variant-label document the Thai row's price cells are the formula ='Oil Price Structure'!C14, pointing at the exact cell that carries the English variant label. The publisher's own formula binds the ordinal-free Thai product name to the ordinal-free English row.
  * source: EPPO workbook internal formula reference
  * observed in 66 documents, 2024-07-23 to 2024-10-28
  * quotation: `='Oil Price Structure'!C14`

**`eppo_ex_refinery_fo1500_2s`** - 2 direct item(s):

* `source_controlled_schema_or_data_dictionary` - The official workbook carries a Thai companion sheet whose product rows are formula-bound to the English sheet. Both English label forms are bound to one identical Thai product name, and that name carries no ordinal marker.
  * source: EPPO price-structure workbook, sheet โครงสร้างราคาน้ำมัน
  * observed in 471 documents, 2024-07-23 to 2026-05-31
  * quotation: `น้ำมันเตา 1500 กำมะถันไม่เกิน 2%`
* `official_formula_document_names_product_without_ordinal` - In every variant-label document the Thai row's price cells are the formula ='Oil Price Structure'!C15, pointing at the exact cell that carries the English variant label. The publisher's own formula binds the ordinal-free Thai product name to the ordinal-free English row.
  * source: EPPO workbook internal formula reference
  * observed in 66 documents, 2024-07-23 to 2024-10-28
  * quotation: `='Oil Price Structure'!C15`

Numeric corroboration was recorded and is explicitly **not** load-bearing (`numeric_evidence_load_bearing`: `False`).

`ordinal_marker_meaning`: **`not_established_from_inspected_sources`**

> No workbook in the 1,331-document archive contains a note, comment, defined name, hidden row or glossary entry explaining (1) or (2), and no EPPO policy or formula document naming them was located through the official REST index, the official pages or the official oil API. That is a limit of the sources inspected, not proof that no explanation exists anywhere. The equivalence decision does not rest on knowing what they mean.

## Raw-label preservation

| field | value |
| --- | --- |
| raw labels overwritten | `False` |
| canonical identity is a layer above C7 | `True` |
| C7 daily parquet modified | `False` |
| C7 monthly audit artifact overwritten | `False` |

Labels retained verbatim: `FO 1500 (2) 2%S`, `FO 1500 2%S`, `FO 600 (1) 2%S`, `FO 600 2%S`, `H-DIESEL`.

## H-DIESEL

| field | value |
| --- | --- |
| `ordinary_label_gap_start` | `2023-09-18` |
| `ordinary_label_gap_end` | `2024-12-17` |
| `missing_document_days` | `305` |
| `affected_reference_months` | `2023-09 through 2024-12` |
| `blend_substitution_permitted` | `False` |
| `imputation_permitted` | `False` |
| `eligible_for_c8_primary_transformation` | `False` |
| `eligible_for_c8_sensitivity_transformation` | `False` |
| `status` | `not_ready_long_semantic_definition_gap` |
| `documents_invalid` | `False` |
| `blend_products_invalid` | `False` |
| `observations_preserved` | `True` |
| `blend_provenance_preserved` | `True` |

> The EPPO documents and the blend products are valid. Ordinary H-DIESEL simply cannot support a continuous, consistently defined source series across the required window.

## Bounded recovery of five unresolved document-days

Termination: Per target, stop when every permitted official channel has been inspected once, or when official corroboration independent of the filename is reached.

| listing date | media | status | recovered date | corroboration |
| --- | --- | --- | --- | --- |
| 2022-12-05 | 21054 | **`recovered_and_validated`** | 2022-12-06 | `parent_post_publication_date`, `parent_post_title_date`, `document_internal_date` |
| 2025-01-25 | 21759 | **`recovered_and_validated`** | 2025-01-24 | `parent_post_publication_date`, `parent_post_title_date`, `document_internal_date` |
| 2026-04-17 | 46232 | **`official_attachment_unretrievable`** | - | - |
| 2026-04-18 | 46231 | **`official_attachment_unretrievable`** | - | - |
| 2026-04-19 | 46230 | **`official_attachment_unretrievable`** | - | - |

Channels inspected per target: `wordpress_media_record`, `parent_post`, `parent_post_attached_media`, `attachment_page`, `wordpress_revision_metadata`, `guid_and_source_url`, `official_sitemap_entry`, `exact_date_rest_search`, `neighbouring_official_archive_entry`, `legacy_official_link`, `alternate_attachment_link_in_official_metadata`

`web_archive_used`: `False`, `silent_reassignment`: `False`.

## The three approvals, separated

| series | method semantics | full coverage | ready with explicit gaps |
| --- | --- | --- | --- |
| `eppo_ex_refinery_fo1500_2s` | `True` | `False` | `True` |
| `eppo_ex_refinery_fo600_2s` | `True` | `False` | `True` |
| `eppo_ex_refinery_hsd` | `True` | `False` | `False` |

Approving the **rule** is not a claim about **coverage**. Both fuel oils
carry an approved method and incomplete coverage at the same time.

## Monthly status after the decision

| status | product-months |
| --- | --- |
| `approved_complete_inventory` | 168 |
| `approved_with_source_label_variant` | 8 |
| `known_document_gap` | 3 |
| `semantic_definition_gap` | 16 |

### Every remaining incomplete month

| series | month | status | strict | descriptive | valid/discovered |
| --- | --- | --- | --- | --- | --- |
| `eppo_ex_refinery_fo1500_2s` | 2026-04 | `known_document_gap` | `None` | 21.6127 | 24/27 |
| `eppo_ex_refinery_fo600_2s` | 2026-04 | `known_document_gap` | `None` | 24.6477 | 24/27 |
| `eppo_ex_refinery_hsd` | 2023-09 | `semantic_definition_gap` | `None` | - | 11/21 |
| `eppo_ex_refinery_hsd` | 2023-10 | `semantic_definition_gap` | `None` | - | 0/20 |
| `eppo_ex_refinery_hsd` | 2023-11 | `semantic_definition_gap` | `None` | - | 0/22 |
| `eppo_ex_refinery_hsd` | 2023-12 | `semantic_definition_gap` | `None` | - | 0/18 |
| `eppo_ex_refinery_hsd` | 2024-01 | `semantic_definition_gap` | `None` | - | 0/22 |
| `eppo_ex_refinery_hsd` | 2024-02 | `semantic_definition_gap` | `None` | - | 0/20 |
| `eppo_ex_refinery_hsd` | 2024-03 | `semantic_definition_gap` | `None` | - | 0/21 |
| `eppo_ex_refinery_hsd` | 2024-04 | `semantic_definition_gap` | `None` | - | 0/18 |
| `eppo_ex_refinery_hsd` | 2024-05 | `semantic_definition_gap` | `None` | - | 0/20 |
| `eppo_ex_refinery_hsd` | 2024-06 | `semantic_definition_gap` | `None` | - | 0/19 |
| `eppo_ex_refinery_hsd` | 2024-07 | `semantic_definition_gap` | `None` | - | 0/21 |
| `eppo_ex_refinery_hsd` | 2024-08 | `semantic_definition_gap` | `None` | - | 0/21 |
| `eppo_ex_refinery_hsd` | 2024-09 | `semantic_definition_gap` | `None` | - | 0/21 |
| `eppo_ex_refinery_hsd` | 2024-10 | `semantic_definition_gap` | `None` | - | 0/21 |
| `eppo_ex_refinery_hsd` | 2024-11 | `semantic_definition_gap` | `None` | - | 0/21 |
| `eppo_ex_refinery_hsd` | 2024-12 | `semantic_definition_gap` | `None` | - | 8/18 |
| `eppo_ex_refinery_hsd` | 2026-04 | `known_document_gap` | `None` | 40.6078 | 24/27 |

## Full window versus operational relevance

Full source audit window: 2021-01 to 2026-05.

| split | issue months |
| --- | --- |
| `development` | 2024-01 .. 2025-03 |
| `purge` | 2025-04 .. 2025-06 |
| `locked_test` | 2025-07 .. 2026-04 |

Maximum preregistered issue month **2026-04**, so the maximum source reference month any existing key requires is **2026-02** under the two-month policy lag. Derived from issue-month ranges only; `target_outcomes_read`: `False`.

| series | month | direct reach | splits reached (level) | splits reached (12m prehistory) |
| --- | --- | --- | --- | --- |
| `eppo_ex_refinery_fo1500_2s` | 2026-04 | 2026-06 | **none** | **none** |
| `eppo_ex_refinery_fo600_2s` | 2026-04 | 2026-06 | **none** | **none** |
| `eppo_ex_refinery_hsd` | 2023-09 | 2023-11 | **none** | `development` |
| `eppo_ex_refinery_hsd` | 2023-10 | 2023-12 | **none** | `development` |
| `eppo_ex_refinery_hsd` | 2023-11 | 2024-01 | `development` | `development` |
| `eppo_ex_refinery_hsd` | 2023-12 | 2024-02 | `development` | `development` |
| `eppo_ex_refinery_hsd` | 2024-01 | 2024-03 | `development` | `development` |
| `eppo_ex_refinery_hsd` | 2024-02 | 2024-04 | `development` | `development`, `purge` |
| `eppo_ex_refinery_hsd` | 2024-03 | 2024-05 | `development` | `development`, `purge` |
| `eppo_ex_refinery_hsd` | 2024-04 | 2024-06 | `development` | `development`, `purge` |
| `eppo_ex_refinery_hsd` | 2024-05 | 2024-07 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-06 | 2024-08 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-07 | 2024-09 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-08 | 2024-10 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-09 | 2024-11 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-10 | 2024-12 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-11 | 2025-01 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2024-12 | 2025-02 | `development` | `development`, `purge`, `locked_test` |
| `eppo_ex_refinery_hsd` | 2026-04 | 2026-06 | **none** | **none** |

April 2026 is documented above even though no preregistered issue origin
requires it as a reference month.

## Shared fuel-oil channel

| field | value |
| --- | --- |
| `shared_price_stage_group` | `io_sector_093_fuel_oil` |
| `additive_aggregation_allowed` | `False` |
| `simple_average_allowed` | `False` |
| `automatic_composite_index_allowed` | `False` |
| `simultaneous_model_entry_approved` | `False` |
| `both_series_preserved` | `True` |
| `representation` | `separate_mutually_exclusive_channel_variants` |
| `selection_by_target_performance_allowed` | `False` |
| `selection_requires` | `independent_structural_rule` |

Both series are preserved because they are distinct products. They are
never added, never averaged, and never enter a model together.

## C8 authorization boundary

| field | value |
| --- | --- |
| `c8_fo600_transformation_authorized` | `True` |
| `c8_fo1500_transformation_authorized` | `True` |
| `c8_hsd_transformation_authorized` | `False` |
| `c8_industry_conditioning_authorized` | `False` |
| `c8_target_join_authorized` | `False` |
| `c8_modeling_authorized` | `False` |
| `c8_imputation_authorized` | `False` |
| `c8_outcome_based_channel_selection_authorized` | `False` |
| `c8_simultaneous_additive_fuel_oil_use_authorized` | `False` |
| `c8_locked_test_evaluation_authorized` | `False` |
| `c8_explicit_missing_month_propagation_authorized` | `True` |
| `c8_policy_lag_2_enforcement_authorized` | `True` |
| `c8_separate_mutually_exclusive_fuel_oil_variants_authorized` | `True` |

Semantic overlay `c7_5_semantic_v1`, 195 rows, `data/interim/c7_5_eppo_monthly_semantic.parquet` (git-ignored). It does not
overwrite the C7 monthly audit artifact.

Content checksum `8b36fd6e9ce7798905cb2b903b263908489a5632fdf54f41ba12b0a12b6bd24a`.

