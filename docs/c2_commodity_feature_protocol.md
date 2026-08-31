# Task C2 — Commodity Feature Protocol

The preregistered rules for turning archived first-release Pink Sheet prices
into point-in-time features. Written before any feature was computed, and
before any association with the target *could* be computed — no target is read
anywhere in C2.

Contract: [`configs/commodity_features.yaml`](../configs/commodity_features.yaml).
Schema: [`schemas/commodity_feature.schema.yaml`](../schemas/commodity_feature.schema.yaml).
Results: [`c2_commodity_feature_audit.md`](c2_commodity_feature_audit.md).

```bash
python scripts/run_c2_commodity_features.py
```

---

## 1. What C2 approves, and what it does not

C2 approves **deterministic construction**: that each feature is computed
correctly, from evidence that existed at the time, reproducibly, with every
input named.

It does **not** approve predictive usefulness. That distinction is the whole
point of keeping the approval fields separate:

| Field | Set by | State after C2 |
|---|---|---|
| `source_verified` | C1 | unchanged (5 verified, 2 conditional) |
| `timing_approved` | C1.5-R2 | unchanged (`true`) |
| **`feature_construction_approved`** | **C2** | **`true`** |
| `feature_semantics_approved` | C3 | `false` |
| `model_feature_approved` | later | `false` |

A feature that is perfectly constructed and useless is a normal C2 outcome. C2
has no way to tell the difference, by design.

## 2. Input

Archived **first-release** values only, from the C1.5-R2 dataset: 65 reference
months (2021-01 … 2026-05), 65/65 archived issues, `point_in_time_supported:
full`, measured publication lag 1, every observation carrying its issue, issue
date, URL and checksum.

The loader **checks** these properties rather than trusting them, and raises
`InputCoverageError` if any is absent. C2's claim to be point-in-time rests
entirely on them, so they are verified at the door.

**The C1 latest-vintage workbook is never substituted.** A latest-vintage number
for an old month is a number nobody had at the time; using one would silently
convert a point-in-time table into a retrospective one. A month whose
`is_true_first_release` flag is not `true` raises
`LatestVintageSubstitutionError`.

**Displayed precision is preserved, never increased.** The PDF's printed text is
the evidence and travels with every observation.

## 3. Series

**Primary (exactly four):** `brent_crude_usd_bbl`, `aluminum_usd_mt`,
`copper_usd_mt`, `rubber_rss3_usd_kg`.

**Excluded, with no substitutes:**

| Series | Why |
|---|---|
| `lng_japan_usd_mmbtu` | First releases revised in **65 of 65** months, up to **34.10%** (C1.5-R2). A feature built on a number that always moves encodes revision noise. |
| `coal_australia_usd_mt` | Definition break at **2022-02**, spot → futures, inside the modelled window. A log change across that boundary compares two different things. |
| `palm_oil_usd_mt` | Three grade/delivery-basis changes (**2021-01, 2024-11, 2025-02**) inside the window. |

No replacement series is introduced. C2 builds features from sources already
cleared in C1; it does not re-select sources, because doing so would be a new
source decision made without the C1 verification that justifies one.

Requesting an excluded series raises `ExcludedSeriesError`.

## 4. Availability

Three months are tracked separately, because collapsing them is exactly how a
feature becomes available before its evidence existed.

| Field | Meaning |
|---|---|
| `source_available_month` | When the latest required input was **actually published**, from the archived issue's own internal date |
| `policy_available_month` | `reference_month + operational_lag_months` — a **policy** month |
| `feature_available_month` | `max(policy_available_month, every input's source_available_month)` |

```
minimum_publication_lag_months = 1   MEASURED (C1.5-R2, all 65 months at t+1)
operational_lag_months         = 2   POLICY   (measured lag + 1 month margin)
policy_available_month         = m + 2 calendar months
feature_available_month        = max(policy month, ALL input source months)
```

Three rules follow, and each is enforced rather than documented:

- **Lag zero is prohibited.** Month *t*'s completed value does not exist at any
  forecast origin inside month *t* (AD-R36). `AvailabilityPolicy` raises
  `LagZeroProhibitedError` on construction, so a zero-lag policy cannot exist to
  be used by accident.
- **A lag below the measured publication lag is rejected**, so policy can never
  outrun evidence.
- **Availability is never derived from the download date.** Every issue in this
  repository was downloaded in the same month; if availability came from that,
  all 65 source months would collapse to one. They do not — there are more than
  50 distinct source-available months in the table.

### Multi-month transformations

A 12-month change is only as available as its **oldest** required input, not its
reference month. Taking only the final month would let a feature publish before
one of its own inputs existed whenever an early input was delayed. Every
declared input's publication month enters the `max`, and
`assert_inputs_published_by` raises if any input was first published after the
feature's available month.

### Primary vs sensitivity

| Policy | Lag | Label | Status |
|---|---|---|---|
| `operational_lag_2m` | 2 | `primary` | The default output |
| `publication_lag_1m` | 1 | `sensitivity_only` | Never the default |

The lag-1 table rests on the same archived publication evidence, so it is not
speculative — it simply carries no revision margin. It is **not compared against
any target in C2**, does not replace the primary table, and cannot be
mislabelled: a policy that is `is_primary=False` but labelled `primary` raises.
`availability_policy` is part of the canonical key, so both tables coexist
without either shadowing the other.

## 5. The five transformations

Let \(p_m\) be the archived first-release price for reference month \(m\).

| Feature | Formula | Inputs read | Unit |
|---|---|---|---|
| `price_level` | \(p_m\) | 1 | source unit |
| `log_change_1m_pct` | \(100(\ln p_m - \ln p_{m-1})\) | 2 | percent (log) |
| `log_change_3m_pct` | \(100(\ln p_m - \ln p_{m-3})\) | 2 | percent (log) |
| `log_change_12m_pct` | \(100(\ln p_m - \ln p_{m-12})\) | 2 | percent (log) |
| `realized_volatility_3m_pct` | \(\operatorname{std}_{ddof=0}(r_{m-2}, r_{m-1}, r_m)\) | **4** | percent (log) |

where \(r_j = 100(\ln p_j - \ln p_{j-1})\).

Two details that are easy to get wrong and are pinned by test:

- **Volatility reads four months, not three.** \(r_{m-2}\) is itself a change
  from \(m-3\), so \(p_{m-3}\) is consumed. Declaring three inputs would
  understate both the lineage and the availability requirement.
- **`ddof=0`, by preregistration.** On a three-observation window the sample
  estimator would inflate every value by \(\sqrt{3/2}\) — about 22%. That is a
  definitional choice, not a property of the market, so it is fixed in advance.

Logarithms are **natural**, scaled by 100. Not log10, and not a simple
percentage change; the two agree only for small moves.

**Nothing else is created in C2** — no other window, rolling z-score, shock
flag, moving average, interaction term, or direction adjustment. Industry
exposure and sign belong to C3.

## 6. Coverage

No value is manufactured to reach a count. A transformation simply produces no
row before its first computable month.

| Feature | Rows per series | First reference month |
|---|---:|---|
| `price_level` | 65 | 2021-01 |
| `log_change_1m_pct` | 64 | 2021-02 |
| `log_change_3m_pct` | 62 | 2021-04 |
| `log_change_12m_pct` | 53 | 2022-01 |
| `realized_volatility_3m_pct` | 62 | 2021-04 |
| **Total per series** | **306** | |

**Canonical total: 306 × 4 = 1,224 rows.** The runner fails explicitly if the
result differs, and the expected counts are *derived from the declared lags*
rather than hard-coded, so a changed lag cannot disagree with a stale constant.

## 7. Lineage

Every calculated feature names the exact observations it consumed.
`input_lineage_checksum` is a SHA-256 over the ordered tuples:

```
(series_id, input reference month, displayed text, displayed value,
 source issue date, source issue checksum)
```

Ordered oldest-first, because a transformation reading the same months in a
different order is a different transformation. Both the displayed **text** and
the float are hashed: the printed precision is the actual evidence, and two
different printed strings must never collide onto one digest.

Change any input value, issue date, or source checksum — or omit an input — and
the digest moves. All 1,224 rows carry distinct checksums.

## 8. Data handling

| Operation | Policy |
|---|---|
| Imputation, forward-fill, interpolation | **none** |
| Clipping, winsorization | **none** |
| Rounding of calculated features | **none** |
| Missing production input | **fail** (`MissingInputError`) |
| Non-positive price input | **fail** (`NonPositivePriceError`) |
| Non-finite feature value | **fail** |

Calculated features are deliberately not rounded: rounding a derived value would
invent precision of a different kind from the source's displayed precision, and
the two would be indistinguishable downstream.

## 9. Outputs

- **Canonical long table** — the single source of truth. Key:
  `(series_id, feature_name, reference_month, availability_policy)`.
- **Wide table** — a **pivot** of the long table. No transformation logic exists
  on the wide path; a test asserts `to_wide_table` contains no formula at all.
  Reimplementing a formula there is how two tables that should agree quietly
  stop agreeing.
- **Sensitivity long table** — lag-1, labelled `sensitivity_only`.

Parquet files are git-ignored. The tracked artifact
(`c2_commodity_feature_audit.json`) carries schema, row counts, checksums and
metadata — not the dataset.

## 10. What C2 does not compute

None of the following is calculated anywhere in C2: correlation with MPI,
mutual information, Granger causality, feature importance, predictive
performance, high-stress event statistics, target distributions, industry
signs or weights, a dependency matrix, or any feature-target join. The locked
final test is not opened.

**No feature was removed for looking weak against the target** — no such
comparison exists to have informed a removal. Selection informed by the target
is how leakage enters a project that has otherwise been careful, so the
prohibition is recorded in configuration and asserted by test, not left to
discipline.

The runner takes **no command-line arguments**, for the same reason the B4
runner takes none: there is no flag that can widen the allowlist, lower the lag,
promote the sensitivity table, or reach a target.
