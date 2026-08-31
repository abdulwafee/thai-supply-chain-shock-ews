# Task D2 — Target Publication-Timing Decision

*Generated 2026-08-28T04:36:06.992253+00:00.*

## Contract

| field | value |
| --- | --- |
| `contract_status` | `resolved` |
| `months_total` | `127` |
| `months_with_credible_evidence` | `111` |
| `coverage_start` | `2016-01` |
| `coverage_end` | `2026-07` |
| `credible_coverage_start` | `2017-04` |
| `credible_coverage_end` | `2026-07` |
| `publication_lag_days_min` | `23` |
| `publication_lag_days_median` | `29` |
| `publication_lag_days_max` | `66` |
| `publishes_in_month_after_reference` | `False` |
| `availability_lag_months` | `1` |
| `same_month_availability_supported` | `False` |
| `required_window_start` | `2020-04` |
| `required_window_end` | `2025-06` |
| `required_window_fully_evidenced` | `True` |

## Directly observed release

Reference month **2026-07** was observed becoming public during this audit.
The live workbook gained exactly one month between the two snapshots and
its `Last-Modified` moved from `2026-07-27T04:37:30Z` to `2026-08-27T05:12:16Z`, with the checksum changing.
The marker glyph moved from `2026-06` to `2026-07`.

The live workbook is overwritten in place. A release adds the new reference month and moves the marker glyph forward; the previous vintage is not retained at this URL.

## Marker semantics

`marker_semantics_documented: False`

The live workbook marks its newest reference month (2026-06) with a trailing glyph, and the marker moves to the next month on the following release while the previous month keeps a value. No legend for the glyph appears in the workbook, so its meaning is recorded as observed behaviour, not asserted as a preliminary flag.

## Consequence for B4

**Assumption:** current-month stress is known at forecast origin t

**Status: `violated`.**

OIE first publishes reference month t a median of 29 days after the end of t, i.e. during month t+1. At forecast origin t the most recent published reference month is therefore t-1, not t.

* `affects_b4_baselines`: `True`
* `affects_d1_feature_assembly`: `True`
* `b4_split_changed`: `False`
* `remedy_deferred`: `True`

D2 is an audit. The split, the targets and the D1 models are left untouched; correcting the assumption is a separate, deliberate decision.

## Evidence outcome: `timing_only_supported`

## Follow-up

The D1 fallback correction recorded here is maintained as a sidecar
erratum: [`d1_development_results.errata.md`](d1_development_results.errata.md).
The two generated D1 documents were restored in Task D3 by reversing the
known D2 insertion; the original pre-D2 digest was unavailable, so exact
historical byte identity cannot be independently proven. The resulting
files are pinned from D3 onward in `d3_restored_d1_checksums.json`.

This section is emitted by the D2 generator itself, so regenerating this
document cannot erase the link — the same failure mode that moved the D1
correction out of its generated result file.

Task D3 acts on the violated assumption above by building a release-aware
operational contract — see
[`d3_operational_evaluation_protocol.md`](d3_operational_evaluation_protocol.md)
and [`d3_operational_baseline_results.md`](d3_operational_baseline_results.md).
