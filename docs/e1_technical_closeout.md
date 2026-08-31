# Technical Closeout - Thai Industrial Stress Early-Warning Research

*Task E1. Generated 2026-08-30T08:45:05.449684+00:00. Synthesis contract `f23396b36b0cb7e8c362bbea1e65d11a98d588830d548c83a816a0c44ef11c1e`.*

## 1. Executive summary

A leakage-aware, release-aware research pipeline was built from official
Thai and international sources, and used to test whether commodity and
refinery-price signals could improve a one- and three-month-ahead
industrial-stress forecast. **They could not, on the evidence available.**

Three candidate models were evaluated on the registered development
window. None beat its benchmark on the primary error metric. The
registered operational reference is therefore a persistence forecast, and
the locked final test was never opened, because no candidate earned
access to it.

That is the whole result, and it is a real one: the project establishes
which plausible signals fail under realistic data availability, and it
leaves an unused final test behind rather than a number that was fitted
until it looked good.

| field | value |
| --- | --- |
| `development_program_status` | `closed_without_supported_incremental_commodity_model` |
| `registered_operational_reference_available` | `True` |
| `registered_operational_reference_source` | `D3` |
| `operational_model_selected` | `False` |
| `production_deployment_authorized` | `False` |
| `commodity_incremental_signal_supported` | `False` |
| `model_feature_approved` | `False` |
| `confirmatory_claim_authorized` | `False` |
| `locked_test_status` | `sealed_unopened` |
| `locked_test_outcomes_read` | `False` |
| `fully_real_time_backtest` | `False` |
| `latest_vintage_target_evaluation` | `True` |
| `future_reopening_requires_new_external_evidence` | `True` |

## 2. Problem definition

Forecast a monthly industrial-stress score per industry, one and three
months ahead, for twelve Thai manufacturing industries. Stress is derived
from the OIE Manufacturing Production Index; the question is whether
commodity input prices carry information about it that a naive forecast
does not already contain.

The hypothesis is structural rather than statistical: industries that buy
more of a commodity should react more to its price. Input-output
coefficients from the national accounts supply that 'more'.

## 3. Forecast-origin and horizon contract

| element | rule |
| --- | --- |
| issue month | the month a forecast is made, `t` |
| latest publishable stress | `t - 1`; month `t` is never used at `t` |
| commodity/fuel feature | reference month `t - 2` under the policy lag |
| horizon 1 target | stress at `t + 1` |
| horizon 3 target | maximum stress over `t + 1 .. t + 3` |
| label availability | `target_window_end + 1 month` |
| calibrator cutoff | fitted on stress through `t - 1`, then frozen |
| development issues | 2024-01 .. 2025-03, fifteen months |
| purge buffer | 2025-04 .. 2025-06, never evaluated |
| locked final test | 2025-07 onward, never opened |

## 4. Data-source and vintage architecture

Evidence quality is **not** equal across these sources, and the table
records where each one is weak.

| source family | values | historical timing | point-in-time status | main limitation |
| --- | --- | --- | --- | --- |
| OIE MPI target | latest vintage | month t+1 timing supported for the audited period | target vintages unavailable | not a real-time target panel |
| World Bank Pink Sheet | archived first release | verified monthly publication timing | feature side supported | target side remains latest vintage |
| NESDC I/O | official 2015 Final structure | structurally available by 2020-03-31 | time-invariant structural input | old benchmark and broad sectors |
| EPPO refinery prices | historical latest-vintage documents | historical first-release timing unverified | not point-in-time | policy lag 2 and broad proxy |

The asymmetry that matters: commodity **features** are archived
first-release values with verified publication dates, so the feature side
is genuinely point-in-time. The **target** is latest vintage for every
source, because no MPI vintages exist. The evaluation is therefore
release-aware but not a point-in-time backtest, and no result in this
report should be read as one.

## 5. Feature construction

Five transformations per commodity series: price level, one-, three- and
twelve-month log changes, and three-month realised volatility. Volatility
is a non-negative disruption magnitude and never a direction.

Missing source months are propagated as missing. Nothing is imputed,
interpolated, forward-filled or substituted from a sibling series: an
absent price multiplied by any exposure is still absent.

## 6. Structural exposure methodology

| finding | value |
| --- | --- |
| `nesdc_2015_final_uses_purchasers_prices` | `True` |
| `nesdc_2015_final_is_import_inclusive` | `True` |
| `structural_coefficients_treated_as_time_invariant` | `True` |
| `world_bank_commodity_mappings_are_broad_proxies` | `True` |
| `aluminum_and_copper_share_sector_107` | `True` |
| `aluminum_and_copper_are_independent_exposure_measurements` | `False` |
| `sector_031_crude_exposure_often_direct_zero` | `True` |
| `sector_093_refinery_product_exposure_positive_for_all_12_industries` | `True` |
| `eppo_ex_refinery_versus_purchasers_price_partial_mismatch` | `True` |
| `fo600_and_fo1500_are_distinct_channels_sharing_one_exposure` | `True` |
| `ind_04_producer_consumer_direction_ambiguous` | `True` |
| `c10_conditioning_adds_scale_not_temporal_degrees_of_freedom` | `True` |
| `c11_pooled_interaction_identifiable` | `True` |
| `c11_selection_status` | `exploratory_supported_after_documented_specification_correction` |
| `structural_attribution_described_as_causal_transmission` | `False` |

The input-output table is the official NESDC 2015 Final structure, read
column-wise as `A[i,j] = Z[i,j] / X_j`, gross-output weighted across the
sectors that map to each industry. Coefficients are purchasers' price and
import-inclusive, and are treated as time-invariant.

This is **structural attribution**, not causal transmission. A positive
coefficient says an industry buys from a sector; it does not say a price
move propagates to output, and no result here is interpreted that way.

## 7. Leakage controls

* Stress from month `t` is never used at issue `t`; the guard raises.
* A historical training row carries the features available at **its own**
  issue month, not the latest ones available at the outer origin.
* Labels enter training only after their publication month.
* The calibrator is refitted per origin, cut at `t - 1`, then frozen.
* Scalers are fitted on the training panel only, and on unique issue
  months rather than on the repeated industry panel.
* Purge and locked origins are rejected before any data is read.
* The D5 target reader refuses to return a value until the protocol
  checksum is verified **and** the prediction for that key is frozen.

## 8. Walk-forward evaluation design

Expanding-window walk-forward over fifteen issue months, refitting at
every origin. The primary metric is macro-industry MAE: per-industry MAE
first, then an equal average across industries, so one volatile industry
cannot dominate. Uncertainty is a paired bootstrap clustered by **issue
month**, keeping all industries together - twelve industries in one month
share a national signal, a calibrator and a release date, and resampling
them independently would shrink every interval by roughly the square root
of twelve.

Fifteen clusters is a small number. Every interval in this report is wide
for that reason, and the limit is stated wherever an interval appears.

## 9. Development results

### 9.1 Original commodity evaluation (D1) - superseded

| horizon | model macro MAE | benchmark macro MAE |
| --- | ---: | ---: |
| 1 | 15.3073 | 14.5287 |
| 3 | 16.1072 | 14.6985 |

Status **not_supported**, superseded by `D3/D4` for operational interpretation.

Three limitations travel with these numbers. The evaluation was **not**
operationally release-timing correct - it predates the issue-month
contract. The nested selection protocol was **not fully executed**:
**6 of 30**
origin-horizon selections fell back to the conservative configuration
because there was not enough inner history, and the **direction of that
fallback's effect is unknown**. D1 is not a fully executed confirmatory
evaluation and is not presented as one.

### 9.2 Operational reference baselines (D3)

| horizon | registered reference | macro MAE | no-contraction macro MAE |
| --- | --- | ---: | ---: |
| 1 | `operational_persistence_latest_published` | 17.0945 | 19.4453 |
| 3 | `operational_persistence_trailing_3m_max` | 16.6338 | 16.9791 |

The paired comparison against the no-contraction comparator was
**inconclusive** at both horizons. Persistence remained the registered
reference through the preregistered false-negative tie-break, which is a
selection rule and not a demonstration of statistical superiority.

D3 established an operational **evaluation reference**. It is not a
deployed system and nothing was put into service.

### 9.3 Commodity model under the operational contract (D4)

| horizon | model | reference | paired 95% interval | MAE evidence | event safety |
| --- | ---: | ---: | --- | --- | --- |
| 1 | 17.5616 | 17.0945 | [-0.2060, 1.3736] | incremental_signal_not_supported | event_safety_passed |
| 3 | 17.9051 | 16.6338 | [0.4317, 2.1098] | incremental_signal_not_supported | event_safety_passed |

Incremental signal was **not supported** at either horizon. The
event-safety gate passed at both, and that does **not** override the
primary error result: both gates were required and one failed.

**180 of 360** primary-panel rows were
benchmark passthrough, because for six industries every eligible direct
predictor is a structural constant - their exposure coefficient is zero,
so the zero-variance rule removes all of them and the prediction reduces
to the benchmark exactly. Half the panel was therefore not a model
prediction at all. D4 remained exploratory and did not earn promotion.

### 9.4 Refinery-price interaction (D5)

| variant | h | model | reference | paired interval | evidence | event safety |
| --- | ---: | ---: | ---: | --- | --- | --- |
| FO 1500 | 1 | 17.111 | 17.094 | [-0.822, 0.847] | inconclusive | failed |
| FO 600 | 1 | 17.167 | 17.094 | [-0.761, 0.907] | inconclusive | failed |
| FO 1500 | 3 | 18.210 | 16.634 | [-0.096, 3.589] | inconclusive | failed |
| FO 600 | 3 | 18.207 | 16.634 | [-0.016, 3.525] | inconclusive | failed |

No point estimate beat the benchmark (0 of 4). All four intervals
crossed zero. Event safety failed in all four. Incremental signal was
**not demonstrated**, and **absence of an effect was not proven** - those
are different statements and only the first is supported.

## 10. Negative-result interpretation

Each of these statuses means something specific, and the report uses the
vocabulary rather than collapsing it:

* **`inconclusive_into_no_effect`** - An interval that crosses zero is a failure to demonstrate, not a demonstration of failure.
* **`not_supported_into_disproven`** - A model that did not beat its benchmark has not disproved the hypothesis it encoded.
* **`unresolved_into_absent`** - A quantity nobody measured is unresolved. Recording it as zero asserts a measurement that was never made.
* **`selected_reference_into_proven_superiority`** - D3's persistence benchmarks are the REGISTERED reference. The paired comparison against no-contraction was inconclusive at both horizons.
* **`development_evaluation_into_production_validation`** - A development walk-forward is not a production validation, and no model was deployed.
* **`latest_vintage_into_real_time_backtesting`** - Latest-vintage targets cannot reproduce what was knowable at the time. The project is release-aware, not point-in-time on the target side.

Three reasons the negative results are informative rather than merely
disappointing.

**The commodity features were structurally degenerate for half the
panel.** Six of twelve industries have a zero direct coefficient on the
mapped commodity sectors, so their 'model' prediction was the benchmark.
That is a property of the official input-output structure, discovered
before any outcome was consulted.

**Per-industry conditioning added scale, not information.** Multiplying
one national price series by a per-industry constant produces eleven
scaled copies of the same fifteen-row history. The cross-section has rank
one at every issue month; the panel has no more temporal degrees of
freedom than the series it came from. This was established by rank
identities, without reading a single target value.

**Fifteen issue-month clusters cannot settle a small effect.** Every
interval in this report is wide by construction. An inconclusive result
on this much data is the expected outcome of an honest test, not a
surprise, and it is reported as inconclusive rather than as absence.

## 11. Reproducibility and testing

| check | result |
| --- | --- |
| test suite | **1794 passed**, 0 failed |
| lint (`ruff check .`) | passing |
| configs parsed | 33 |
| schemas parsed | 37 |
| result documents parsed | 45 |
| artifacts pinned | 23 |

The test count above was **measured by running the suite**, not copied
from a previous report: a number typed into a reproducibility manifest
drifts the moment a test is added, and a stale count looks like evidence.

Every task freezes its contract to disk and re-verifies the digest before
reading values; every generated row carries a lineage checksum over both
its provenance chains; and each stage's expected counts were preregistered
and reconciled rather than reported after the fact.

## 12. Limitations

* **Targets are latest vintage.** No MPI vintages exist, so the target
  side cannot be point-in-time and this is not a real-time backtest.
* **Refinery-price release timing was never measured.** The two-month lag
  is a conservative policy assumption, not an observed publication delay.
* **Structural coefficients are time-invariant** and come from a 2015
  benchmark table read at a broad sector granularity.
* **Commodity mappings are proxies.** Aluminium and copper share one
  sector and are not independent exposure measurements; sector 093 is a
  nine-product basket, so fuel oil stands in for the whole basket.
* **Fifteen development issue months** bound every uncertainty interval.
* **One industry is structurally excluded** from the refinery-price
  correction because it both produces and consumes refinery products; its
  direction is unresolved rather than zero.

## 13. Final decision

| field | value |
| --- | --- |
| `development_program_status` | `closed_without_supported_incremental_commodity_model` |
| `registered_operational_reference_available` | `True` |
| `registered_operational_reference_source` | `D3` |
| `operational_model_selected` | `False` |
| `production_deployment_authorized` | `False` |
| `commodity_incremental_signal_supported` | `False` |
| `model_feature_approved` | `False` |
| `confirmatory_claim_authorized` | `False` |
| `locked_test_status` | `sealed_unopened` |
| `locked_test_outcomes_read` | `False` |
| `fully_real_time_backtest` | `False` |
| `latest_vintage_target_evaluation` | `True` |
| `future_reopening_requires_new_external_evidence` | `True` |

### Locked-test closeout

| field | value |
| --- | --- |
| `status` | `sealed_unopened` |
| `manifest_is_key_only` | `True` |
| `locked_test_outcomes_read` | `False` |
| `any_candidate_locked_test_evaluation_authorized` | `False` |
| `prediction_or_metric_exists_for_locked_origins` | `False` |
| `outcomes_opened_hashed_or_summarised` | `False` |
| horizon 1 reservation | `['2025-07', '2026-04']` |
| horizon 3 reservation | `['2025-07', '2026-02']` |

> The locked final test was intentionally left unopened because no independently preregistered candidate earned access through development evidence.

## 14. Reopening conditions

A different specification is not new evidence. Reopening requires
something external that the evaluation could not have used, with
provenance, an availability date, an account of why it was unavailable,
and a superseding recorded decision. Qualifying categories are a
product-specific industrial fuel-consumption crosswalk; a newer compatible
input-output table available before the evaluation period; verified
point-in-time release evidence; a materially longer compatible target
history obtained without touching the purge or locked windows; a proven
material implementation error; or a genuinely new external hypothesis
registered before any corresponding result is inspected.

## 15. Architecture

```
  official sources          timing / vintage contracts
  ----------------          --------------------------
  OIE MPI            -->    latest vintage, t+1 release timing
  World Bank Pink Sheet -->  archived first release, verified dates
  NESDC 2015 I/O     -->    time-invariant, available by 2020-03
  EPPO price docs    -->    latest vintage, policy lag 2 (unmeasured)
                                      |
                                      v
                              transformations
                    (level, 1m/3m/12m log change, 3m volatility;
                     missing months propagated, never imputed)
                                      |
                                      v
                            structural exposure
                  (I/O coefficients, gross-output weighted,
                   purchasers' price, attribution not causation)
                                      |
                                      v
                       development walk-forward (15 issues)
                  (expanding window, refit per origin, paired
                   issue-month cluster bootstrap)
                                      |
                                      v
                          evidence-based closure
         no candidate beat its benchmark -> baseline-only reference
                                      |
                                      v
                    LOCKED FINAL TEST -- NEVER OPENED
                    (reserved, key-only, no model deployed)
```

No stage of this diagram ends in deployment. The final box is a
reservation, not a result.

## 16. Final declaration

* **The development programme is complete.**
* **The data, timing, lineage and evaluation infrastructure is reproducible.**
* **Persistence forecasts remain the registered operational reference.**
* **No commodity model demonstrated sufficient incremental development evidence.**
* **No model or feature was approved for operational deployment.**
* **The locked final test remains sealed.**
* **Future reopening requires genuinely new external evidence and a new independent preregistration.**

## Appendix - task codes and evidence links

| stage | task | artifact |
| --- | --- | --- |
| foundation | `B1` | `docs/b1_ingestion_metadata.json` (source ingestion) |
| foundation | `B3` | `docs/b3_target_build_metadata.json` (target definition) |
| foundation | `B4` | `docs/b4_baseline_results.json` (split and baselines) |
| foundation | `D2` | `docs/d2_target_timing_decision.json` (release timing) |
| foundation | `D3` | `docs/d3_operational_baseline_results.json` (operational contract and reference baselines) |
| foundation | `D3R1` | `docs/d3r1_benchmark_interpretation.json` (benchmark-selection correction) |
| foundation | `D3_LOCKED` | `docs/d3_locked_test_manifest.json` (key-only locked-test reservation) |
| world_bank_path | `C1` | `docs/c1_commodity_source_audit.json` (source timing) |
| world_bank_path | `C2` | `docs/c2_commodity_feature_audit.json` (transformations) |
| world_bank_path | `C3` | `docs/c3_commodity_exposure_matrix.json` (I/O exposure) |
| world_bank_path | `C4` | `docs/c4_industry_conditioned_feature_audit.json` (conditioned matrix) |
| world_bank_path | `D1` | `docs/d1_development_results.json` (original development evaluation) |
| world_bank_path | `D4` | `docs/d4_operational_model_results.json` (operational fixed-specification evaluation) |
| eppo_path | `C5` | `docs/c5_price_stage_source_audit.json` (stage alignment) |
| eppo_path | `C7` | `docs/c7_eppo_full_archive_audit.json` (full ingestion) |
| eppo_path | `C7_5` | `docs/c7_5_eppo_semantic_decision.json` (semantic closure) |
| eppo_path | `C8` | `docs/c8_eppo_transformation_audit.json` (source transformations) |
| eppo_path | `C9` | `docs/c9_fuel_oil_conditioning_audit.json` (structural conditioning) |
| eppo_path | `C9_EXPOSURE` | `docs/c9_sector093_exposure_decision.json` (sector-093 structural decision) |
| eppo_path | `C10` | `docs/c10_design_matrix_audit.json` (identifiability audit) |
| eppo_path | `C11` | `docs/c11_architecture_decision.json` (architecture decision) |
| eppo_path | `C11R1` | `docs/c11r1_governance_decision.json` (governance correction) |
| eppo_path | `D5` | `docs/d5_development_results.json` (authorized development evaluation) |
| eppo_path | `C12` | `docs/c12_channel_closure.json` (channel closure) |

Evidence ledger checksum `09d3a0b59734c131361ebe899fec0e8431d624c3658e4ac4ed6251714e436eef`. Reproducibility manifest checksum `29c4ef0ac18cb2064ae1474838747d8cc9ce18f69ba3d1dbdea6db1e1b340e08`.

