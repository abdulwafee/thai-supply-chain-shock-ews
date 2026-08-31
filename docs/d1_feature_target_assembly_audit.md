# Task D1 — Feature–Target Assembly Audit

How training rows were selected, and what was excluded. Numbers are read from
[`d1_feature_target_assembly_audit.json`](d1_feature_target_assembly_audit.json).

---

## 1. Two cutoffs, enforced separately

| Rule | Cutoff |
|---|---|
| Label may enter training | `target_window_end <= t`, per horizon |
| Historical feature vector for origin *u* | `conditioned_available_month <= u` |
| Current evaluation row | `conditioned_available_month <= t` |

The second is the one that would leak silently. A training row belonging to *u*
must be built from what was known **at u** — refreshing it with everything known
at *t* would let the model learn from a version of history that never existed.
The two rules take different arguments so they cannot drift into each other, and
both have synthetic failure tests.

The label rule is strictly stronger than the rejected alternative: at 2024-01
for h=3 it permits origins up to **2023-10**, where selecting on the origin alone
would have admitted up to 2023-12 — three windows still open at the cutoff.

## 2. Counts

| | Label-permitted | Feature-usable | Excluded by feature gate |
|---|---:|---:|---:|
| h=1 at 2024-01 | 288 | **264** | 24 |
| h=1 at 2025-03 | 456 | **432** | 24 |
| h=3 at 2024-01 | 264 | **240** | 24 |
| h=3 at 2025-03 | 432 | **408** | 24 |

Every feature-usable count matches the brief's expectation exactly (22/36/20/34
origins × 12 industries).

Both counts are reported. The difference is never silent: each excluded row
carries `insufficient_registered_feature_history`, and nothing is imputed.

## 3. The feature-history gate

Under the primary lag-2 contract, the 12-month log change first exists for
reference month 2022-01 and becomes available **2022-03**. Origins 2022-01 and
2022-02 therefore have an incomplete registered set and are excluded — that is
the 24 rows in each row of the table above.

Inventing a 12-month change for those months would fabricate exactly the signal
the model is being asked to find.

## 4. Calibrators

**30 records** (15 origins × 2 horizons), **15 distinct fits**. Every one has
`calibration_reference_end` at or before its own origin. The earliest spans
2022-01 … 2024-01 with 300 observations across 12 industries.

Historical targets and historical benchmark offsets are transformed with the
**same** calibrator frozen at the outer origin — a residual computed across two
different scales would not be a residual.

## 5. The calibrator minimum binds earlier than the brief expected

B3's monthly stress begins 2022-01, so the 24-observation minimum is first met
at **2023-12**. This is why the brief's expected inner validation origins
(2023-03 / 2023-05) are unreachable: they were derived from the feature gate
alone. The guard was kept; the expectation is reported as unmet. See
`d1_development_results.md` §7.
