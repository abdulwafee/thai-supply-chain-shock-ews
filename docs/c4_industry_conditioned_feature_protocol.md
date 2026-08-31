# Task C4 — Industry-Conditioned Feature Protocol

The preregistered rules for combining C2's point-in-time commodity features with
C3-R1's structural exposures. Written before any conditioned value was computed,
and before any association with the target *could* be computed — no target is
read anywhere in C4.

Contract: [`configs/industry_conditioned_features.yaml`](../configs/industry_conditioned_features.yaml).
Schema: [`schemas/industry_conditioned_feature.schema.yaml`](../schemas/industry_conditioned_feature.schema.yaml).
Results: [`c4_industry_conditioned_feature_audit.md`](c4_industry_conditioned_feature_audit.md).

```bash
python scripts/run_c4_industry_conditioned_features.py
```

---

## 1. What C4 approves

**Predictors.** C4 approves that a conditioned feature is computed correctly,
from inputs that existed at the time, with every provenance preserved.

It approves nothing about predictive usefulness. A feature that is perfectly
constructed and useless is a normal C4 outcome, and C4 has no way to tell the
difference — by design.

| Field | Set by | After C4 |
|---|---|---|
| `source_verified` | C1 | unchanged |
| `timing_approved` | C1.5-R3 | unchanged |
| `feature_construction_approved` | C2 | unchanged |
| `structural_exposure_approved` | C3-R1 | unchanged |
| **`conditioned_construction_approved`** | **C4** | **`true`** |
| `feature_semantics_approved` | later | `false` |
| `model_feature_approved` | later | `false` |

## 2. Inputs — verified, not assumed

**C2:** 4 commodity series × 5 base features × 306 observations = **1,224 rows**
per availability policy; primary `operational_lag_2m`, sensitivity
`publication_lag_1m`; archived first-release values only.

**C3-R1:** 12 industries × 4 commodities = **48 pairs**, **43 eligible**, **5
excluded**, 3 direction-ambiguous, 2 proxy-ineligible, 24 shared-sector rows;
direct exposure primary, total-requirement sensitivity-only.

The runner **stops** on any discrepancy rather than proceeding on a changed
input.

## 3. Structural availability — the leak that leaves no trace

The I/O table's **reference year is 2015**. That is the year it *describes*, not
the date it was *published*. Backdating the matrix to 2015 would hand a 2024
forecast origin four years of structure nobody could read — and because the
structure is constant, the leak would be invisible in every output.

Equally, the **download timestamp is not historical availability**: these files
were re-hosted during NESDC's 2025 site migration, and using that date would make
the matrix look unavailable throughout the development window.

What is used instead is the publisher's own stated publication date:

| Field | Value |
|---|---|
| Evidence type | Official NESDC download-page publication date |
| Evidence URL | `https://www.nesdc.go.th/download/i-o-table-of-thailand-2015/` |
| Raw value | `31 มี.ค. 2563` (Buddhist era 2563 = CE 2020) |
| **`structural_available_by`** | **2020-03-31** |
| Status | **`verified_before_development`** |
| First development origin | 2024-01 |

The Buddhist-era conversion is **verified against a known case**, not assumed:
the same field on the 2021 I/O page reads `25 ก.พ. 2568` = 2025-02-25, matching
that table's known release and its `2025/03` upload path.

**One caveat stated rather than glossed:** what is verified is that the 2015
*table* was published by 2020-03-31. The *bytes* now held were re-hosted in 2025,
so byte-level identity as of 2020 is **not** established
(`byte_identity_verified_at_that_date: false`).

`StructuralAvailability` raises if the availability date is not after the
reference year, and `assert_supports_primary` raises if the structure post-dates
the first development origin.

## 4. Eligible and excluded pairs

Conditioned features are created for the **43 eligible** pairs only. The five
excluded pairs are tracked in a separate exclusion audit:

| Pair | Reason |
|---|---|
| IND-12 × Aluminum | **commodity-proxy fitness** — jewellery-dominated aggregate |
| IND-12 × Copper | **commodity-proxy fitness** |
| IND-06 × Rubber RSS3 | **mixed/ambiguous direction** — contains I/O sector 095 |
| IND-08 × Aluminum | **mixed/ambiguous direction** — contains I/O sector 107 |
| IND-08 × Copper | **mixed/ambiguous direction** |

For each: the structural coefficient is **retained**, never zeroed, never
deleted, no default feature is generated, and no ambiguous sign is forced. A
validator raises if a row for an excluded pair ever appears.

## 5. Three variants, each varying exactly one assumption

| Variant | Policy | Exposure | Label |
|---|---|---|---|
| `primary_direct_lag2` | `operational_lag_2m` | `direct_exposure` | **primary** |
| `timing_sensitivity_direct_lag1` | `publication_lag_1m` | `direct_exposure` | `sensitivity_only` |
| `structural_sensitivity_total_lag2` | `operational_lag_2m` | `total_requirement_exposure` | `sensitivity_only` |

**There is deliberately no lag-1 + total-requirement variant.** Changing two
assumptions at once produces a difference nobody can attribute to either, and the
whole point of a sensitivity run is attribution. `MatrixVariant` counts the
varied assumptions and raises on anything but exactly one — so the forbidden
combination cannot be constructed, not merely discouraged.

No variant is selected using targets. `variant_selected_using_targets: false`.

## 6. The formula

```
conditioned = base_feature_value  x  exposure  x  price_increase_to_stress_sign
```

A primary feature is created only when **all** hold: the pair is eligible, proxy
fitness is allowed, direction is not ambiguous, the sign is finite and non-null,
the exposure is finite and non-null, the C2 value is finite, and availability
passes. **A missing sign is never inferred.**

## 7. Units — named honestly

| Base | Conditioned |
|---|---|
| `$/bbl`, `$/mt`, `$/kg` | `$/unit × exposure coefficient` |
| percent (log) | percentage-point log change × exposure coefficient |
| percent (volatility) | percentage-point volatility × exposure coefficient |

This is a **structural interaction feature**. It is **not** a monetary cost
amount, a price elasticity, a causal effect, or a forecast coefficient.
Multiplying a log change by an I/O coefficient does not make it money.

Conditioned features are **not normalized** across commodities or industries.

## 8. Counts

```
43 eligible pairs  x  306 observations                = 13,158 per variant
13,158  x  3 variants                                 = 39,474 canonical rows
```

The runner fails explicitly on any other count, and no rows are manufactured for
the five excluded pairs.

## 9. Zero, missing and ineligible — six different facts

| State | Meaning |
|---|---|
| `zero_due_to_exposure` | The industry genuinely uses none of it |
| `zero_due_to_base_feature` | The commodity price did not move |
| `zero_due_to_both` | Both |
| `not_generated_due_to_ineligibility` | No feature exists here at all |
| `no_observation_available_at_origin` | Not published yet |
| `insufficient_feature_history` | Not enough months to compute |

Collapsing any two would make an absence of knowledge look like a measurement.
An observed-zero exposure produces a **numeric zero**; an ineligible pair
produces **null**, never zero. Total-requirement exposure may be nonzero where
direct exposure is zero — that is the whole point of the structural sensitivity.

## 10. Availability

```
conditioned_available_month = max(base_feature_available_month,
                                  structural_available_by)
```

Never earlier than either input: a feature built from two things is only as
available as the slower one. Reference month, C2 source/policy/feature months,
`structural_available_by` and the conditioned month are all preserved. Future-
dated input raises.

## 11. Combined lineage

A SHA-256 over the ordered tuple of: C2 lineage checksum, industry, commodity, C3
exposure-row checksum, exposure value, direction sign, proxy-fit status,
eligibility, matrix variant, transformation version, structural source checksum.

**An incomplete lineage fails.** A blank C2 or C3 checksum would still produce a
well-formed digest for an untraceable feature, so each is checked for emptiness
before hashing. Every one of the 39,474 lineages is re-derived independently by
the runner.

## 12. Aluminum / Copper

Both read the **same** I/O sector 107 coefficient. Every affected row carries
`shared_io_source_sector: true`, `shared_exposure_group: io_sector_107`,
`additive_aggregation_allowed: false` and a `double_counting_risk`.

C4 keeps both price signals — they are genuinely different prices — but must not
sum their exposure weights, average them, build a combined non-ferrous shock
index, or claim they are independently measured.
`assert_no_duplicate_shared_sector_aggregate` raises on any aggregate containing
sector-107 exposure more than once, and the runner exercises it on real rows so
the guard is demonstrated, not merely present. No PCA, weighted average or
replacement non-ferrous factor is created.

## 13. Development snapshot

Primary variant, B4 development origins 2024-01 … 2025-03: **15 origins × 12
industries = 180 rows**, 20 commodity-feature columns, **3,225 eligible cells**
(43 × 5 × 15) and **375 structurally unavailable cells** (5 × 5 × 15).

Selection is `latest reference month with conditioned_available_month <=
forecast_origin_month`. **Positional shifting is prohibited**: a fixed shift
agrees with the availability rule only when publication is perfectly regular and
diverges silently when it is not — and this project measured the publication lag
precisely so it would never have to guess.

Ineligible cells stay **null with an explicit mask**, never zero. No target
column is attached.

## 14. What C4 does not compute

MPI correlation, feature importance, mutual information, Granger causality,
predictive performance, target distributions, high-stress event metrics, feature
selection, model coefficients. Locked-test target rows and metrics are not
inspected. The runner takes **no command-line arguments**.
