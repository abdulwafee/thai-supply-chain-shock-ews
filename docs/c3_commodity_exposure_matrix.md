# Task C3 — Commodity–Industry Structural Exposure Matrix

> **REVISED (C3-R1).** C3 marked all 48 pairs "resolved, medium confidence" and
> stopped. That conflated two questions: *is the coefficient available?* and
> *does the I/O category actually represent this commodity for this industry?*
> A **commodity-proxy fitness gate** now answers them separately — §12. No
> numeric exposure changed.

A **structural prior** from Thailand's official national accounts: how much of
each commodity each project industry embodied per unit of output in the benchmark
year. Not a causal estimate, not a current cost share, not evidence of predictive
value.

Sources: [`c3_io_source_audit.md`](c3_io_source_audit.md).
Crosswalks: [`c3_industry_crosswalk.md`](c3_industry_crosswalk.md).
Numbers: [`c3_commodity_exposure_matrix.json`](c3_commodity_exposure_matrix.json).

```bash
python scripts/audit_c3_io_sources.py
python scripts/run_c3_industry_exposure.py
```

No target was joined, no association was computed, no weight was tuned on an
outcome, no model was trained, and B4's locked test was not opened.

---

## 1. Construction

| Step | Result |
|---|---|
| Project industries reproduced | **12 / 12**, ids, names and TSIC divisions matched exactly |
| Official I/O sectors | 180; **179** usable |
| `A[i][j] = Z[i][j] / X[j]` | 179 × 179 |
| Sector excluded (zero gross output) | **179** — undefined, never zero-filled |
| Column sums of `A` | 0.0000 … **0.9017** (all < 1) |
| Negative coefficients | **0** |
| Condition number of `(I − A)` | **7.839** |
| `L = (I − A)⁻¹`, reconstruction residual | **1.110e-15** (tolerance 1e-8) |
| `T = L − I`, identity term removed | yes |
| Negative cells in `T` | **0** |

The accounting identity `Z + value added = gross output` holds with residual
**exactly 0** across all 180 sectors, and gross output equals the total-input row
for every sector.

## 2. Definitions

```
direct   [c][IND] = A[c][IND]                 aggregated as sum(Z)/sum(X)
total    [c][IND] = T[c][IND] = (L − I)[c][IND]
indirect [c][IND] = total − direct
```

`direct + indirect = total` holds for all 48 rows to 1e-12, by test.

**These are structural accounting ratios under fixed proportions and no
substitution.** They are not price pass-through elasticities, not causal effects,
and not forecasts. C3 records that guard in the artifact itself.

## 3. Coverage

| | |
|---|---|
| Canonical rows | **48** = 12 industries × 4 commodities |
| Unique keys | **48** |
| Resolved | **48** |
| Unresolved (null exposure) | **0** |
| **Observed zeros** (numeric 0.0) | **18** |
| Mapping confidence | **medium × 48** |
| Rows carrying `shared_io_source_sector` | **24** |

**Zero and unresolved are different states and stay different.** The 18 zeros are
*observed* zeros — the industry genuinely bought none of that input in 2015 —
carrying `quality_flag: observed_zero_direct_exposure`. They are not missing data,
and no unresolved mapping was converted into one.

Zeros by commodity: Brent 10, Rubber 6, Aluminum 1, Copper 1.

## 4. Ranges

| Measure | Min | Max |
|---|---|---|
| Direct | **0.000000** | **0.710250** |
| Indirect | 0.000747 | 0.296583 |
| Total | 0.000916 | 0.857110 |

## 5. Largest structural exposures

| Industry | Commodity | Direct | Indirect | Total |
|---|---|---:|---:|---:|
| IND-04 Refined Petroleum | Brent | **0.710250** | 0.146860 | **0.857110** |
| IND-12 Furniture & Other Mfg | Aluminum¹ | 0.209637 | 0.296583 | 0.506219 |
| IND-12 Furniture & Other Mfg | Copper¹ | 0.209637 | 0.296583 | 0.506219 |
| IND-05 Chemicals & Pharma | Brent | 0.006385 | **0.193626** | 0.200011 |
| IND-09 Electronics & Electrical | Aluminum¹ | 0.075695 | 0.122367 | 0.198062 |
| IND-10 Machinery | Aluminum¹ | 0.060859 | 0.131984 | 0.192843 |
| IND-08 Basic & Fabricated Metals | Brent | **0.000000** | 0.168730 | 0.168730 |

¹ *Identical to the Copper row by construction — see §6.*

Three of these say something worth reading carefully:

- **IND-04 × Brent (0.71 direct)** is the sanity check the whole matrix has to
  pass. Refineries buying 71% of their input value as crude petroleum is exactly
  what the structure should show.
- **IND-05 × Brent** is 0.006 direct but **0.194 total** — chemicals reach crude
  almost entirely *through refineries*, not by buying it. This is the case the
  secondary matrix exists to reveal, and the case a direct-only view would miss.
- **IND-08 × Brent is an observed zero direct with 0.169 indirect** — basic metals
  buy no crude at all, yet embody a great deal of it through energy and
  petrochemical inputs. Zero direct is not zero exposure.

## 6. The Aluminum/Copper overlap

Both series resolve to the same official sector, **107 Non-ferrous metal**, which
combines all primary non-ferrous metals. **Their 24 rows are pairwise identical by
construction** — one aggregate exposure reported twice, not two independent
measurements. Every affected row carries `shared_io_source_sector: true` and names
its partner in `shared_with`; a test asserts the flag is present wherever the
coefficients coincide.

**This is the matrix's sharpest interpretive caveat, and IND-12 shows why.** Its
0.2096 "aluminum" exposure comes overwhelmingly from **Jewellery (sector 132)**,
which is **74.7%** of IND-12's output and has a 0.2685 coefficient on sector 107.
For a jewellery producer, what flows out of "Non-ferrous metal" is largely
**gold** — not aluminum and not copper. The number is a correct reading of the
official table and a poor proxy for either LME price. It must not be used as
though it measured aluminum intensity.

## 7. Direction

| Channel | Rows |
|---|---:|
| `cost_pressure` (sign **+1**) | **45** |
| `mixed_or_ambiguous` (sign **null**) | **3** |

`price_increase_to_stress_sign = +1` is a **domain direction for cost pressure**,
derived from the classification — not an empirically estimated target sign.
Nothing was fitted.

The three ambiguous pairs are those where the industry **contains the commodity's
own I/O sector**, making it both producer and consumer:

- **IND-06 × Rubber** — IND-06 contains sector 095
- **IND-08 × Aluminum** — IND-08 contains sector 107
- **IND-08 × Copper** — IND-08 contains sector 107

Their sign is **left null**. Forcing a producer/consumer industry into a single
sign would assert a net effect the classification does not establish, and a wrong
sign is worse than an absent one.

## 8. Matrix variants

| Variant | Definition | Status |
|---|---|---|
| **Primary** | Direct technical coefficients `A[c][IND]` | primary |
| **Secondary** | Total requirements `T = L − I` | structural sensitivity view |

The secondary matrix does **not** silently replace the primary one, and neither
was selected on the basis of target outcomes — `selection_based_on_target_outcomes:
false`.

## 9. No normalization

The four exposures are **absolute** coefficients.
`normalization.across_commodities: none`.

Normalizing them to sum to one would turn "how much crude does this industry use"
into "what share of these four commodities is crude" — inventing a comparability
the I/O table does not provide and destroying the magnitude information that makes
a coefficient meaningful. A validator raises if any industry's four direct
exposures ever sum to 1, and a synthetic test exercises it.

## 10. Scope

| Guard | State |
|---|---|
| Joined to MPI targets | **false** |
| Target association computed | **false** |
| Exposure weights tuned on outcomes | **false** |
| Predictive interactions created | **false** |
| Model trained / B4 compared | **false** |
| Locked final test accessed | **false** |
| Industry-conditioned feature matrix | **false** |
| `model_feature_approved` | **false** (all 48 rows) |

## 11. Limitations

- **The structural reference year is 2015.** These coefficients describe Thailand
  a decade before the 2021–2026 window the project models. Applying them is an
  explicit `time_invariant_assumption: true`, and it is an assumption, not a
  finding. A newer official 2021 table exists, is audited and is structurally
  compatible — adopting it is a separate decision.
- **Sector aggregation is the dominant limitation.** All four commodities map to
  broader official categories: Brent carries natural gas, Aluminum and Copper are
  one sector, RSS3 is one grade among several. §6 shows how badly that can bite.
- **116 dominates IND-10** at 79% of output while straddling two TSIC divisions,
  so IND-10's exposures inherit that ambiguity.
- **Fixed proportions.** Leontief assumes no substitution: an industry facing a
  price spike cannot switch inputs in this model, though it would in reality.
- **Import-inclusive Leontief.** The inverse measures technology-sense total
  requirements including rounds embodied in imports; it is not a domestic output
  multiplier.
- **The classification document is the 2021 edition**, applied to the 2015 table.
  Code-universe compatibility is verified; definitional identity is not.
- **Nothing here shows any of these exposures predicts Thai industrial
  production.** C3 approves structure, not usefulness.


## 12. C3-R1 — the commodity-proxy fitness gate

### Why a valid coefficient is not a valid proxy

Every one of the 48 coefficients is correctly computed. That says nothing about
whether the broad I/O category stands in for the *named commodity* in a
particular industry. The clearest case is IND-12: its exposure to "Non-ferrous
metal" is **95.7%** driven by sector 132, Jewellery, whose official definition
reads *"jewellery using **precious metals**… silverware and plotted ware using
**silver, gold** and other precious metal plating"*. A correct number, and a bad
proxy for the LME aluminum or copper price. Treating `medium` crosswalk
confidence as feature eligibility would have carried it straight into a model.

### The two questions, now separate

| Field | Answers |
|---|---|
| `quantitative_coefficient_status` | Is the coefficient available? |
| `commodity_proxy_fit_status` | Does the category represent this commodity here? |
| `commodity_proxy_scope` | What the aggregate actually spans |
| `commodity_proxy_evidence` | The official evidence behind the verdict |
| `industry_pair_feature_eligible` | May it generate a default C4 feature? |
| `feature_eligibility_reason` | Why, in words |
| `shared_io_source_sector` | Does another commodity read the same coefficient? |
| `double_counting_risk` | Consequence of that sharing |

The verdict is derived from the industry's **dominant purchasing component** in
the official table, checked against that component's official **definition** — not
from judgement and not from any target. `determined_from_target_information:
false`.

### Results

| Proxy fitness | Pairs |
|---|---:|
| `fit_for_structural_use` | **2** |
| `broad_proxy_use_with_caution` | **44** |
| `not_fit_for_commodity_specific_use` | **2** |
| `unresolved` | 0 |
| **Feature-eligible** | **43 / 48** |

Only two pairs earn commodity-specific fitness, both on official evidence:

- **IND-04 × Brent** — 100% of its purchases from sector 031 are made by
  Petroleum refineries, where crude is the defining input, so the
  crude-plus-gas aggregate is crude-dominated here.
- **IND-06 × Rubber** — 68.5% via Tyres and tubes, manufactured principally from
  natural rubber.

### The five ineligible pairs — documented, never deleted

| Pair | Fitness | Direction | Direct | Why ineligible |
|---|---|---|---:|---|
| IND-12 × Aluminum | `not_fit_for_commodity_specific_use` | cost_pressure | 0.209637 | Jewellery-dominated; the aggregate is precious metals here |
| IND-12 × Copper | `not_fit_for_commodity_specific_use` | cost_pressure | 0.209637 | Same |
| IND-06 × Rubber | `fit_for_structural_use` | **mixed_or_ambiguous** | 0.083088 | Null sign — IND-06 contains sector 095 and both produces and consumes it |
| IND-08 × Aluminum | `broad_proxy_use_with_caution` | **mixed_or_ambiguous** | 0.102801 | Null sign — IND-08 contains sector 107 |
| IND-08 × Copper | `broad_proxy_use_with_caution` | **mixed_or_ambiguous** | 0.102801 | Same |

**Every one keeps its coefficient.** Eligibility is a *usage* decision;
deleting or zeroing the number would destroy evidence and make "not suitable"
indistinguishable from "no exposure". A validator raises if an ineligible pair is
found with its coefficient removed, and another raises if the table drops below
48 rows.

Note the two failure modes are different, and stay different: IND-12 is gated on
**proxy fitness** (the number is fine, the meaning is wrong), IND-06/IND-08 on
**direction** (the meaning is fine, the sign is genuinely ambiguous).

### Aluminum / Copper double counting

**24 rows** carry `shared_io_source_sector: true` and
`double_counting_risk: shared_io_sector_must_not_be_summed_or_averaged`. The two
series read the **same** coefficient from sector 107; they are **not independently
measured**, must not be summed, and must not be averaged. Any later aggregate
shock index may include the sector-107 exposure **at most once**, however many of
the two series it draws on. Proxy fitness is still evaluated **per industry** —
IND-12 is gated while IND-09 is not.

### Preregistered C4 policy — C4 is NOT built here

| Rule | Setting |
|---|---|
| Primary structural matrix | **`direct_exposure`** |
| Sensitivity matrix | `total_requirement_exposure`, never the default |
| Default C4 membership | `industry_pair_feature_eligible: true` **only** |
| Ineligible / unresolved | Documented; generate **no** default feature |
| Ambiguous direction | Stays **null** |
| Prohibited | Forcing `mixed_or_ambiguous` into cost pressure; forcing missing fitness into sign zero; forcing a producer channel into a consumer-cost channel |

`c4_matrix_created_in_this_task: false`.
