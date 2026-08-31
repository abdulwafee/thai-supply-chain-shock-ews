# Erratum — Task D1 Development Results

**Status:** active correction to a claim made in D1 reporting.
**Raised by:** Task D2. **Relocated here by:** Task D3.
**Applies to:** [`d1_development_results.md`](d1_development_results.md) §7 and
[`d1_modeling_protocol.md`](d1_modeling_protocol.md) §4.

This erratum is a **sidecar**. Corrections live here instead of being edited
into a generated file — otherwise a later regeneration would silently erase the
correction, and the record of what D1 actually claimed would be lost.

**Restoration evidence, stated precisely.** Task D2 inserted a correction block
into both generated D1 documents; Task D3 removed exactly those blocks. The
pre-D2 checksum snapshot had been deleted, so the original digests were
unavailable: **restored by reversing the known D2 insertion; the original pre-D2
digest was unavailable, so exact historical byte identity cannot be
independently proven.** What *is* verified is that the inserted block is absent,
that the original wording is retained, and that the resulting files are pinned
from D3 onward in
[`d3_restored_d1_checksums.json`](d3_restored_d1_checksums.json). Those pinned
digests are a forward integrity baseline — they are **not** evidence of the
unknown historical checksum.

---

## The incorrect claim

D1 stated that the preregistered conservative fallback — `alpha = 100.0`,
`nonferrous_channel = none` — "can only make the model look **worse**, never
better", and therefore could not manufacture apparent skill.

## Why it is wrong

Ridge at `alpha = 100.0` **still fits an intercept**, and it can **still retain
the Brent and Rubber predictors**. Heavy shrinkage pulls the predicted residual
toward zero and therefore biases the prediction toward the benchmark, but it does
**not** fix the sign of the resulting error. On any given origin the shrunken
correction may land closer to the observed target than a less regularized fit
would have. The direction of the effect on measured performance is therefore not
determined by the configuration.

The narrower statement that survives is that the fallback **strongly shrinks
toward the benchmark**. The stronger statement — that it can only worsen the
result — was never established and is withdrawn.

## Corrected record

| Field | Value |
| --- | --- |
| `d1_primary_result` | `incremental_signal_not_supported` |
| `d1_nested_protocol_fully_executed` | `false` |
| `d1_fallback_count` | `6` of `30` origin-horizon selections |
| `d1_protocol_deviation_reason` | `insufficient_pre_origin_calibration_history` |
| `fallback_strongly_shrinks_toward_benchmark` | `true` |
| `fallback_guaranteed_to_worsen_model` | `false` |
| `fallback_effect_direction` | `unknown` |
| `d1_approved_for_locked_test` | `false` |

The six fallback selections were h=1 at 2024-01 and 2024-02, and h=3 at 2024-01
through 2024-04 — **6 of the 30** origin-horizon selections (15 origins × 2
horizons).

## What is unaffected

**D1's primary result stands.** The commodity features did not beat persistence:
macro MAE 15.3073 vs 14.5287 (h=1) and 16.1072 vs 14.6985 (h=3), with the paired
95% confidence interval excluding zero in the benchmark's favour at both
horizons. The verdict remains `incremental_signal_not_supported`, and **D1
remains ineligible for locked-test evaluation** (`d1_approved_for_locked_test:
false`). The locked final test is unopened.

This erratum narrows a supporting argument. It does not rehabilitate the model,
and it is not grounds for re-running D1.

## Superseding record

Decision-log entries **AD-R59 through AD-R67** (Task D2) supersede the incorrect
fallback interpretation. AD-R66 is the entry that withdraws the claim
specifically. Historical entries AD-R39 through AD-R58 are preserved unchanged —
the correction is recorded by addition, never by rewriting what was decided at
the time.

Related D2 findings that bear on how D1 should be read:

* **AD-R59** — OIE publishes reference month *t* during month *t+1*, so B4 and
  D1 both used a stress month that was not yet published at their forecast
  origin. Both are **non-operational** calendar-boundary experiments. Task D3
  builds the release-aware replacement.
* **AD-R65** — D1's fallback was caused by insufficient pre-origin calibration
  history, and D2 established that history **cannot** be honestly extended. The
  protocol deviation is therefore not remediable by extending the sample.

## Cross-references

* [`d2_target_timing_decision.md`](d2_target_timing_decision.md)
* [`d2_oie_mpi_source_audit.md`](d2_oie_mpi_source_audit.md)
* [`d3_operational_evaluation_protocol.md`](d3_operational_evaluation_protocol.md)
* [`architecture/decision_log.md`](architecture/decision_log.md) — AD-R59…AD-R67, AD-R68
