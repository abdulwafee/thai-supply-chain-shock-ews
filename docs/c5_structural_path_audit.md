# Task C5 - Structural Path Audit

*Generated 2026-08-28T09:04:32.779802+00:00. Config `price_stage_source_candidates_v1`.*

## Why direct exposure is zero

A zero direct coefficient is **not** an error and **not** an absence of
dependence. It says the industry does not buy the raw commodity across its
factory gate. It may still buy refined fuel, electricity, petrochemicals or
transport, each carrying the commodity price at a different stage.

## Decomposition

```
T = A + TA
direct(c,j)         = A[c,j]
indirect_via(c,k,j) = T[c,k] * A[k,j]
indirect(c,j)       = sum_k T[c,k] * A[k,j]
total(c,j)          = A[c,j] + sum_k T[c,k] * A[k,j] = T[c,j]
```

* identity residual: **6.661e-16** (tolerance 1e-12)
* worst reconciliation vs C3: **2.776e-17**
* orientation: `column`, max |A - Z/X| = 0.000e+00 over 144 cells
* sectors: **179**, excluded zero-output ['179']
* final demand, imports and value added are **excluded** as intermediate sectors

> Both T = A + TA and T = A + AT hold algebraically for T = (I-A)^-1 - I, so this identity alone does not pin orientation.

The decomposition is an exact attribution of the Leontief identity. It is
**not a causal claim**: `T[c,k]` already contains every production round
including cycles, and splitting on the first purchased sector assigns each
unit of requirement to the door it came through, nothing more.

## Direct-zero cases

**18 of 48** commodity-industry pairs have an observed direct zero; **11** of those still carry indirect exposure at or above the preregistered materiality threshold 0.01.

| commodity | direct-zero industries |
| --- | ---: |
| `aluminum_usd_mt` | 1 |
| `brent_crude_usd_bbl` | 10 |
| `copper_usd_mt` | 1 |
| `rubber_rss3_usd_kg` | 6 |

## Leading mediators for direct-zero pairs

| commodity | industry | direct | indirect | total | leading mediator | share |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| `aluminum_usd_mt` | IND-04 | 0.000000 | 0.006703 | 0.006703 | 031 Petroleum and natural gas | 80.7% |
| `brent_crude_usd_bbl` | IND-01 | 0.000000 | 0.072823 | 0.072823 | 135 Electricity | 12.0% |
| `brent_crude_usd_bbl` | IND-02 | 0.000000 | 0.129149 | 0.129149 | 068 Weaving | 23.2% |
| `brent_crude_usd_bbl` | IND-03 | 0.000000 | 0.077691 | 0.077691 | 081 Pulp, paper and paperboard | 28.7% |
| `brent_crude_usd_bbl` | IND-06 | 0.000000 | 0.144442 | 0.144442 | 086 Petrochemical products | 54.9% |
| `brent_crude_usd_bbl` | IND-07 | 0.000000 | 0.143638 | 0.143638 | 093 Petroleum refineries | 21.5% |
| `brent_crude_usd_bbl` | IND-08 | 0.000000 | 0.168730 | 0.168730 | 106 Secondary steel products | 31.0% |
| `brent_crude_usd_bbl` | IND-09 | 0.000000 | 0.101563 | 0.101563 | 118 Radio, television and communication equipment and apparatus | 33.4% |
| `brent_crude_usd_bbl` | IND-10 | 0.000000 | 0.108089 | 0.108089 | 116 Office and household machinery and appliances | 31.6% |
| `brent_crude_usd_bbl` | IND-11 | 0.000000 | 0.116854 | 0.116854 | 106 Secondary steel products | 22.3% |
| `brent_crude_usd_bbl` | IND-12 | 0.000000 | 0.099690 | 0.099690 | 132 Jewellery and related articles | 30.7% |
| `copper_usd_mt` | IND-04 | 0.000000 | 0.006703 | 0.006703 | 031 Petroleum and natural gas | 80.7% |
| `rubber_rss3_usd_kg` | IND-01 | 0.000000 | 0.000916 | 0.000916 | 098 Plastic ware | 22.7% |
| `rubber_rss3_usd_kg` | IND-03 | 0.000000 | 0.001109 | 0.001109 | 081 Pulp, paper and paperboard | 26.7% |
| `rubber_rss3_usd_kg` | IND-05 | 0.000000 | 0.001140 | 0.001140 | 098 Plastic ware | 19.9% |
| `rubber_rss3_usd_kg` | IND-07 | 0.000000 | 0.001699 | 0.001699 | 040 Stone quarrying | 23.1% |
| `rubber_rss3_usd_kg` | IND-10 | 0.000000 | 0.003172 | 0.003172 | 116 Office and household machinery and appliances | 28.9% |
| `rubber_rss3_usd_kg` | IND-11 | 0.000000 | 0.012501 | 0.012501 | 096 Tyres and tubes | 51.0% |

## D4 no-predictor state

* `model_fitted`: `False`
* `prediction_source`: `benchmark_passthrough_no_eligible_predictor`
* `residual_correction`: `0.0`
* `correction_needed`: `False`
* `d4_recomputed`: `False`

D4 already separates these rows with model_quality='degenerate_all_predictors_constant_benchmark_only', records predicted_residual exactly 0.0 and predictor_count 0, and its schema states the prediction equals the benchmark. It never describes them as a fitted ridge with an intercept. C5 therefore records the equivalent vocabulary (model_fitted=false, prediction_source=benchmark_passthrough_no_eligible_predictor, residual_correction=0.0) as a metadata clarification only. No D4 prediction or metric was recomputed.
