# Task C7 - Monthly EPPO Source Aggregation Decision

*Generated 2026-08-28T17:50:30.610419+00:00. Config `eppo_monthly_source_v1`.*

## The rule

`arithmetic_mean_of_validated_observed_official_document_days`, version `c7_v1`.

Preregistered before the archive was retrieved, and selected from source
publication semantics, archive completeness and deterministic
reproducibility. It was **not** selected from predictive performance;
no predictive quantity exists in this task.

> Mean ex-refinery price across validated official EPPO document-days observed in the completed reference month.

### What the rule refuses

| refusal | reason |
| --- | --- |
| no weekend or holiday observation is synthesised | the archive publishes on working days; a synthetic day would be our number, not EPPO's |
| no forward fill of an unchanged price | that would silently convert the statistic into a calendar-day mean |
| no duration weighting | it would require proof that a published price stays in force until superseded, which this project does not have |
| no partial issue-month observation | the same reference month would otherwise take different values depending on when it was computed |
| each document-day counted once | byte-identical or content-equivalent republications are one observation, not two |

## Approval gate

`monthly_aggregation_contract_approved`: **False**

The gate **fails**. It is reported as a failure rather than forced:

* `eppo_ex_refinery_fo1500_2s`:
  * 2022-12 - `unresolved_document_identity`
  * 2024-07 - `unit_or_definition_break`
  * 2024-08 - `unit_or_definition_break`
  * 2024-09 - `unit_or_definition_break`
  * 2024-10 - `unit_or_definition_break`
  * 2025-01 - `unresolved_document_identity`
  * 2026-04 - `unresolved_document_retrieval`
* `eppo_ex_refinery_fo600_2s`:
  * 2022-12 - `unresolved_document_identity`
  * 2024-07 - `unit_or_definition_break`
  * 2024-08 - `unit_or_definition_break`
  * 2024-09 - `unit_or_definition_break`
  * 2024-10 - `unit_or_definition_break`
  * 2025-01 - `unresolved_document_identity`
  * 2026-04 - `unresolved_document_retrieval`
* `eppo_ex_refinery_hsd`:
  * 2022-12 - `unresolved_document_identity`
  * 2023-09 - `semantic_definition_gap`
  * 2023-10 - `semantic_definition_gap`
  * 2023-11 - `semantic_definition_gap`
  * 2023-12 - `semantic_definition_gap`
  * 2024-01 - `semantic_definition_gap`
  * 2024-02 - `semantic_definition_gap`
  * 2024-03 - `semantic_definition_gap`
  * 2024-04 - `semantic_definition_gap`
  * 2024-05 - `semantic_definition_gap`
  * 2024-06 - `semantic_definition_gap`
  * 2024-07 - `semantic_definition_gap`
  * 2024-08 - `semantic_definition_gap`
  * 2024-09 - `semantic_definition_gap`
  * 2024-10 - `semantic_definition_gap`
  * 2024-11 - `semantic_definition_gap`
  * 2024-12 - `semantic_definition_gap`
  * 2025-01 - `unresolved_document_identity`
  * 2026-04 - `unresolved_document_retrieval`

## Why each month failed

| cause | months | what it means |
| --- | --- | --- |
| `unresolved_document_retrieval` | every discovered attachment for the day returned an error | the official media record exists but its file does not; an actual unresolved inventory item, not a schedule gap |
| `unresolved_document_identity` | the attachment's internal date belongs to another day | not reassigned, not counted for the listing date |
| `unit_or_definition_break` | the month rests on a label variant whose equivalence with the audited label is not established | averaging it would assert an equivalence nobody made |
| `semantic_definition_gap` | the product was not published on some or all validated document-days | a blend price is never substituted |

## H-DIESEL

H-DIESEL is a conditional series. It never blocks the fuel oils, and no
value is fabricated to make one of its months pass.

* Ordinary `H-DIESEL` is absent from 2023-09-18 to 2024-12-17 (305 document-days).

C6 reported the product absent for 22 audited document-days in January
2024. That was true of every day C6 sampled. The full archive shows the
absence is longer; C6 is extended, not contradicted.

## Availability

| field | value |
| --- | --- |
| `source_available_as_of` | `None` in every row |
| `policy_available_month` | reference month + 2 months |
| `availability_basis` | `conservative_policy_not_historical_measurement` |
| `operational_lag_is_measured` | `False` |
| `minimum_verified_publication_lag_months` | `None` |
| `latest_vintage_used` | `True` |
| `point_in_time_supported` | `False` |

## What C7 did not do

| field | value |
| --- | --- |
| `feature_transformations_created` | `False` |
| `industry_conditioned_matrix_created` | `False` |
| `model_feature_approved` | `False` |
| `source_ready_for_transformation_reported_by_series` | `True` |
| `feature_semantics_approved` | `False` |
| `industry_conditioned_features_created` | `False` |
| `locked_test_accessed` | `False` |
| `model_feature_approved` | `False` |
| `model_trained` | `False` |
| `predictive_transformations_created` | `False` |
| `target_association_computed` | `False` |
| `target_joined` | `False` |

A monthly source-level mean is an ingestion aggregation. It is not
authorization for predictive feature engineering, and the next task must
take that decision explicitly.

