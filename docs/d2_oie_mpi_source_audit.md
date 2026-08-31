# Task D2 — OIE MPI Source, Publication-Timing and Vintage Audit

*Generated 2026-08-28T04:36:06.992253+00:00. Evidence only: no target rebuilt, no model rerun, no locked
test opened, no numerical value read after the cutoff.*

## Evidence outcome: `timing_only_supported`

Publication timing is established authentically. Complete 12-industry
point-in-time vintages are not available, and monthly history cannot be
honestly extended to the month the D1 protocol would have needed.

## 1. Numerical guard

`numerical_audit_cutoff_month = 2025-06`. Structural metadata (month labels,
marker glyphs, checksums, HTTP headers) is read for every month; index
**values** are refused beyond the cutoff by `GuardedMonthlyReader`, which
raises `NumericalCutoffError` rather than returning a number.

## 2. Entry-point discovery

| entry point | state |
| --- | --- |
| `iindex_archive` | `reachable` |
| `iindex_detail` | `reachable` |
| `oie_live_workbook` | `reachable` |
| `ckan_oie_value_added` | `reachable` |
| `ckan_oie_production_value` | `reachable` |
| `indexes_oie_home` | `tls_hostname_mismatch` |

No probe state in this audit means "the source does not exist". A DNS or
TLS failure is a property of one mechanism at one moment. Two earlier tasks
(C1.5-R1, C3-R1) were corrected for exactly that conflation.

## 3. Release inventory

Archive walk terminated on `empty_page_at_12`; 127 entries, 127 distinct ids.
Coverage **2016-01 .. 2026-07**, 127 months, no gaps.

July appears in two spellings in entry titles — the standard `กรกฎาคม` and
the variant `กรกฏาคม`. Five entries use the variant; accepting only the
standard spelling would have reported five coverage gaps that do not exist.

| timing evidence class | months |
| --- | ---: |
| `attachment_corroborated` | 80 |
| `attachment_last_modified_only` | 9 |
| `directly_observed_release` | 1 |
| `listing_timestamp_only` | 1 |
| `migration_batch_contaminated` | 15 |
| `rehosted_listing_later_than_attachment` | 21 |

### Why the listing timestamp is not the publication date

Migration batches (one listing date shared across many entries):

* `2017-06-13` — 16 entries
* `2023-07-27` — 15 entries

The 2016-01…2017-03 block all carries a single 2017-06-13 listing stamp, and
its attachments were re-created at the same moment, so no first-publication
evidence survives for those months. Where a page was merely edited later, the
attachment keeps the original date and is preferred: the June-2022 entry is
listed as 2023-07-27 but its attachment is dated 2022-08-01.

## 4. Vintage availability

**No complete 12-industry vintage was found.** Evidence:

* Archive attachments inspected for two pre-cutoff months (2025-06, 2022-06) contain 0 TSIC division codes paired with values, no tabular sector breakdown, and name only 4-6 of 13 industry keywords - a differing subset each month, i.e. selected highlights.
* The live workbook is a single URL overwritten on each release; the 2026-08-26 and 2026-08-28 snapshots differ in checksum and the earlier vintage is not retained.
* data.go.th OIE records (gdpublish-43_011, gdpublish-43_02) point at those same overwritten URLs, so they are catalogue metadata rather than vintages.
* data.go.th per-month MPI files published by the Electrical and Electronics Institute contain electrical/electronics product rows only, not the national 12-industry index, and the 2019-2023 years were uploaded in bulk back-fill batches rather than contemporaneously.

Scope of that statement: No complete 12-industry vintage was found through the mechanisms exercised here (archive walk, detail pages, attachments, live workbook, CKAN search). This is a statement about those mechanisms, not proof that no vintage archive exists anywhere.

## 5. Editions and base-year compatibility

| edition | base | scheme | coverage | divisions |
| --- | ---: | --- | --- | ---: |
| `live_2021_base` | 2021 | TSIC | 2021-01 .. 2026-06 | 22 |
| `hist_2016_base` | 2016 | TSIC | 2016-01 .. 2023-12 | 21 |
| `hist_2011_base` | 2011 | ISIC | 2011-01 .. 2018-12 | 21 |

Splicing the 2016-based and 2021-based editions is admissible only if their
ratio is constant per division over the shared months — a pure rebasing.
Measured over 36 shared months:

* divisions evaluated: **21**
* pure rescaling: **2**
* re-estimated: **19**
* median ratio CV: **3.12%**
* max ratio CV: **6.45%**

**Splice admissible: `False`.**
* division sets differ: only_in_newer=[16] only_in_older=[]
* only 2 of 21 evaluated divisions are a pure rescaling (required fraction 1.00)

## 6. Historical-extension feasibility

Required: raw MPI from **2020-04**, stress from **2021-04**.
The primary (2021-based) edition starts **2021-01**, so reaching the requirement
means joining an older edition.

**Extension feasible: `False`.** Blockers:
* primary edition (base 2021) starts 2021-01, after the required 2020-04; reaching it requires joining an older edition
* edition base 2016 reaches 2016-01 but is missing required division(s) [16]
* edition base 2011 reaches 2011-01 but is missing required division(s) [16]
* base-year splice inadmissible: division sets differ: only_in_newer=[16] only_in_older=[]
* base-year splice inadmissible: only 2 of 21 evaluated divisions are a pure rescaling (required fraction 1.00)
* editions use different classification schemes ['ISIC', 'TSIC']; a scheme change is not a revision and cannot be spliced

## 7. D1 limitation recorded

* `d1_primary_result`: `incremental_signal_not_supported`
* `d1_nested_protocol_fully_executed`: `False`
* `d1_fallback_count`: `6`
* `d1_protocol_deviation_reason`: `insufficient_pre_origin_calibration_history`
* `fallback_strongly_shrinks_toward_benchmark`: `True`
* `fallback_guaranteed_to_worsen_model`: `False`
* `fallback_effect_direction`: `unknown`
* `d1_approved_for_locked_test`: `False`

D1 reporting (docs/d1_development_results.md section 7 and docs/d1_modeling_protocol.md section 4) stated that the fallback configuration (alpha=100, nonferrous_channel=none) could only make the model look worse and never better. That claim is withdrawn here as unsupported. Ridge with alpha=100 still fits an intercept and can retain Brent and Rubber predictors, so heavy shrinkage biases predictions toward the benchmark without guaranteeing a direction for the resulting error. The effect is recorded as unknown.

AD-R39 through AD-R58 are preserved byte-for-byte. This correction is recorded as a new decision, not by editing the historical record.
