# Task C4 — Industry-Conditioned Feature Audit

Results of combining C2's point-in-time commodity features with C3-R1's
structural exposures. Rules: [`c4_industry_conditioned_feature_protocol.md`](c4_industry_conditioned_feature_protocol.md).
Numbers: [`c4_industry_conditioned_feature_audit.json`](c4_industry_conditioned_feature_audit.json).

No target was joined, no association computed, no feature selected on an
outcome, no model trained, and B4's locked test was not opened.

---

## 1. Inputs, verified

| C2 | Required | Observed |
|---|---|---|
| Commodity series | 4 | **4** |
| Base feature definitions | 5 | **5** |
| Observations per series | 306 | **306** |
| Rows per availability policy | 1,224 | **1,224** |
| Primary policy | `operational_lag_2m` | ✔ |
| Sensitivity policy | `publication_lag_1m` | ✔ |
| Archived first-release only | yes | ✔ |

| C3-R1 | Required | Observed |
|---|---|---|
| Industries × commodities | 12 × 4 = 48 | **48** |
| Eligible pairs | 43 | **43** |
| Excluded pairs | 5 | **5** |
| Direction-ambiguous | 3 | **3** |
| Proxy-ineligible | 2 | **2** |
| Shared-sector rows | 24 | **24** |

The runner stops on any discrepancy rather than proceeding on a changed input.

## 2. Structural availability

| Field | Value |
|---|---|
| Reference year | **2015** — what the table *describes* |
| **`structural_available_by`** | **2020-03-31** — when it became readable |
| Status | **`verified_before_development`** |
| Evidence | Official NESDC download-page publication date, `31 มี.ค. 2563` |
| First development origin | 2024-01 |
| Reference year used as publication date | **false** |
| Download timestamp used as availability | **false** |
| Byte identity verified at that date | **false** |

2020-03-31 precedes every development origin, so the **primary matrix is
permitted**.

**It is still not fully real-time**, and the audit says so
(`fully_real_time: false`): the MPI target remains latest-vintage, and a single
2015 benchmark structure is applied across the whole window.

## 3. Pairs

**43 eligible** pairs generate features. **5 excluded**, with coefficients
retained:

| Pair | Reason | Direct exposure retained |
|---|---|---:|
| IND-06 × Rubber | mixed/ambiguous direction | 0.083088 |
| IND-08 × Aluminum | mixed/ambiguous direction | 0.102801 |
| IND-08 × Copper | mixed/ambiguous direction | 0.102801 |
| IND-12 × Aluminum | commodity-proxy fitness | 0.209637 |
| IND-12 × Copper | commodity-proxy fitness | 0.209637 |

None converted to zero, none deleted, none given a default feature, no ambiguous
sign forced. Zero conditioned features generated for all five.

## 4. Variants and counts

| Variant | Policy | Exposure | Primary | Rows |
|---|---|---|---|---:|
| `primary_direct_lag2` | lag 2 | direct | **yes** | **13,158** |
| `timing_sensitivity_direct_lag1` | lag 1 | direct | no | **13,158** |
| `structural_sensitivity_total_lag2` | lag 2 | total | no | **13,158** |
| | | | | **39,474** |

43 × 306 = 13,158 exactly, and 13,158 × 3 = 39,474 exactly. Each sensitivity
variant varies exactly one assumption; the combined lag-1 + total-requirement
variant does not exist and cannot be constructed.

## 5. Zero, missing and ineligible

| Zero reason | Rows |
|---|---:|
| `not_zero` | 28,381 |
| `zero_due_to_exposure` | **11,000** |
| `zero_due_to_base_feature` | 77 |
| `zero_due_to_both` | 16 |
| | **39,474** |

The 11,000 structural zeros are **numeric zeros** — the industry genuinely bought
none of that input in 2015. The 77 flat-price zeros are a different fact and stay
separate. Neither is confusable with the five excluded pairs, which produce **no
rows at all**.

## 6. Availability and lineage

| Check | Result |
|---|---|
| `conditioned_available_month = max(base, structural)` | all 39,474 rows |
| Never earlier than the C2 input | ✔ |
| Never earlier than the structural source | ✔ |
| Available month strictly after reference month | ✔ |
| **Lineage re-derived independently** | **39,474 / 39,474 match** |

Every lineage binds the C2 checksum, the C3 exposure-row checksum and the
structural source checksum. An incomplete lineage raises rather than emitting an
untraceable feature.

## 7. Aluminum / Copper

**18,360 rows** carry `shared_io_source_sector: true`,
`shared_exposure_group: io_sector_107` and `additive_aggregation_allowed: false`.

The duplicate-aggregate validator was **exercised on real rows and fires**
(`duplicate_aggregate_validator_fires: true`) — an aggregate containing both
aluminum and copper sector-107 exposure for one industry is rejected. No combined
non-ferrous index, PCA or weighted-average replacement was created.

Both price signals are kept, because they are genuinely different prices. What is
forbidden is treating one shared coefficient as two independent exposures.

## 8. Development snapshot

| Dimension | Expected | Observed |
|---|---:|---:|
| Origins (2024-01 … 2025-03) | 15 | **15** |
| Industries | 12 | **12** |
| Industry-origin rows | 180 | **180** |
| Commodity-feature columns | 20 | **20** |
| **Eligible feature cells** | 3,225 | **3,225** |
| **Structurally unavailable cells** | 375 | **375** |
| Total cells | 3,600 | **3,600** |

Cell statuses: 3,225 `observed`, 375 `structurally_ineligible`, 0
`no_observation_available_at_origin`, 0 `insufficient_feature_history`.

Selection uses the availability rule, not a positional shift
(`positional_shift_used: false`). Ineligible cells are **null with an explicit
mask**, never zero. No target column is attached.

## 9. Outputs and determinism

| Artifact | Rows | Content checksum |
|---|---:|---|
| Canonical long | 39,474 | `0f48186b8906225d…` |
| Wide (primary) | 780 | `d2e46b5814e3796d…` |
| Development snapshot | 180 | `802fb68a83f1f5af…` |
| Development mask | 3,600 | `60b976b4fe51d887…` |

Long ↔ wide reconciled: **780 rows, 0 mismatches**, derived from the long table
with no conditioning logic duplicated. Parquet outputs are git-ignored.

## 10. Scope

| Guard | State |
|---|---|
| Joined to MPI targets | **false** |
| Target association computed | **false** |
| Feature selection using outcomes | **false** |
| Model trained / B4 compared | **false** |
| Locked final test accessed | **false** |
| Normalized across commodities or industries | **false** |
| `model_feature_approved` | **false** (all 39,474 rows) |

## 11. Limitations

- **The structure is a single 2015 benchmark**, applied to a 2021–2026 window
  under an explicit `time_invariant_assumption`. Thai industry has changed in a
  decade; this matrix cannot see that.
- **The commodity proxies are broad.** Brent stands for a sector that also
  contains natural gas; aluminum and copper share one non-ferrous sector; RSS3 is
  one grade within processed natural rubber. C3-R1's gate records where that
  bites hardest, but a `broad_proxy_use_with_caution` feature is exactly what its
  name says.
- **Not fully real-time.** The features are point-in-time on the commodity side
  and the structure was readable from 2020, but the MPI target remains
  latest-vintage. No evaluation built on this may be described as a real-time
  backtest.
- **Byte identity of the 2015 file in 2020 is unverified** — only that the table
  was published by then.
- **43 of 48 pairs** carry features; five industries–commodity combinations are
  deliberately dark, and any downstream aggregate must handle that rather than
  assume a full grid.
- **Nothing here shows that any of these 39,474 values predicts Thai industrial
  production.** C4 builds predictors; it does not evaluate them.
