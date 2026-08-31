# Task C9 Phase A - Sector-093 Exposure and Structural Decision

*Generated 2026-08-29T07:55:17.174184+00:00. Config `fuel_oil_industry_conditioning_v1`, version `c9_phase_a_structural_decision_v1`.*

Decided from I/O and domain evidence only. No C8 numeric value, MPI value,
target, prediction or metric was read; the table below was hashed and frozen
before Phase B opened the C8 file.

**Frozen structural decision checksum:** `d528aba4aedcb8b8051ad618d66d49c71239267fb26fd2ead292ee90b12c9703`

## The sector

`093` **Petroleum refineries**

> This sector covers oil-processing refineries. Products of this sector are gasoline, jet oil, LPG, asphalt, paraffin, sulfur, kerosene, diesel and fuel oil.

Fuel oil is **one of nine** named products in that basket, which is why a
positive coefficient proves purchase from the refinery-products sector and
not purchase of FO 600 or FO 1500.

## Exposure formula

* direct: `A[093,j] = Z[093,j] / X_j`
* weighted: `E[093,g] = sum_j (X_j / sum_l X_l) * A[093,j]`
* exact:    `E[093,g] = sum_j Z[093,j] / sum_j X_j`

Both aggregation forms are calculated independently and must agree within
`1e-12`. Observed worst residual: **1.388e-17**.

## Exposure by industry

| industry | name | direct exposure | observed zero | contains 093 |
| --- | --- | --- | --- | --- |
| `IND-01` | Food, Beverages and Tobacco | 0.0085557229 | `False` | `False` |
| `IND-02` | Textiles, Apparel and Leather | 0.0113934632 | `False` | `False` |
| `IND-03` | Wood and Paper | 0.0100652664 | `False` | `False` |
| `IND-04` | Refined Petroleum Products | 0.0097966621 | `False` | `True` |
| `IND-05` | Chemicals and Pharmaceuticals | 0.0641559533 | `False` | `False` |
| `IND-06` | Rubber and Plastics | 0.0143207364 | `False` | `False` |
| `IND-07` | Non-metallic Mineral Products | 0.0346482970 | `False` | `False` |
| `IND-08` | Basic and Fabricated Metals | 0.0269063935 | `False` | `False` |
| `IND-09` | Computer, Electronics and Electrical Equipment | 0.0050708572 | `False` | `False` |
| `IND-10` | Machinery and Equipment | 0.0075211586 | `False` | `False` |
| `IND-11` | Motor Vehicles and Other Transport Equipment | 0.0087111719 | `False` | `False` |
| `IND-12` | Furniture and Other Manufacturing | 0.0047482929 | `False` | `False` |

minimum 0.0047482929, median 0.0099309642, maximum 0.0641559533; observed zeros **0**; unresolved **0**.

> Baht of sector-093 output purchased per baht of industry gross output, purchasers' prices, import-inclusive, one 2015 benchmark under fixed proportions. Not an elasticity, not a pass-through rate, not a causal effect. A large exposure is a structural fact, not an error.

## Price stage versus valuation basis

| field | value |
| --- | --- |
| EPPO price stage | `ex_refinery` |
| I/O valuation basis | `purchasers_prices` |
| I/O import treatment | `import_inclusive` |
| alignment | `partial_mismatch_purchasers_price_coefficient_x_ex_refinery_price` |
| structural interaction only | `True` |
| monetary cost measure | `False` |
| elasticity | `False` |
| causal effect | `False` |

> Multiplying the EPPO price by the I/O coefficient does NOT produce baht cost per unit of industrial output. The price stage and the valuation basis differ.

## Proxy fitness, direction and eligibility

| industry | proxy fit | confidence | direction | multiplier | eligible | exclusion reason |
| --- | --- | --- | --- | --- | --- | --- |
| `IND-01` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-02` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-03` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-04` | `broad_proxy_use_with_caution` | `medium` | `mixed_or_ambiguous` | `None` | `False` | `direction_ambiguous_industry_contains_producer_sector` |
| `IND-05` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-06` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-07` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-08` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-09` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-10` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-11` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |
| `IND-12` | `broad_proxy_use_with_caution` | `medium` | `cost_pressure` | `1` | `True` | `None` |

Both channels receive identical structural decisions: the exposure vector
and the direction depend on the industry, not on which fuel oil is used.

Eligible industries per channel: **11** (IND-01, IND-02, IND-03, IND-05, IND-06, IND-07, IND-08, IND-09, IND-10, IND-11, IND-12).

Ineligible: **1** (IND-04).

## Preregistered Phase-B counts

| field | rows |
| --- | --- |
| `full_grid_rows` | 7800 |
| `source_numeric_rows` | 6578 |
| `source_gap_rows` | 572 |
| `ineligible_rows` | 650 |

Derived from the frozen eligibility before any C8 value was read, and not
edited afterwards.

