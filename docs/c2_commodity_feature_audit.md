# Task C2 — Commodity Feature Construction Audit

Results of building the point-in-time commodity feature table. Rules and
rationale: [`c2_commodity_feature_protocol.md`](c2_commodity_feature_protocol.md).
Numbers are read from
[`c2_commodity_feature_audit.json`](c2_commodity_feature_audit.json).

No target was joined, no association was computed, no industry mapping was
applied, no model was trained, and B4's locked test was not opened.

```bash
python scripts/run_c2_commodity_features.py
```

---

## 1. Input

| Property | Required | Observed |
|---|---|---|
| Dataset | C1.5-R2 archived first releases | `docs/c1_5_commodity_timing_audit.json` |
| Reference window | 2021-01 … 2026-05 | **2021-01-01 … 2026-05-01** |
| Reference months | 65 | **65** |
| Archived issue coverage | 65/65 | **65/65** |
| `point_in_time_supported` | full | **full** |
| `minimum_publication_lag_months` | 1 | **1** |
| `publication_timing_verified` | true | **true** |
| Monthly inputs per primary series | 65 | **65, 65, 65, 65** |

Every property is checked by the loader, not assumed. Latest-vintage
substitution is refused: a month whose `is_true_first_release` flag is not
`true` raises rather than falling back.

**No missing, non-positive, or non-finite input observations** were found in any
of the four primary series across all 65 months. Nothing was imputed, because
nothing needed to be.

## 2. Series

**Included (4):**

| Series | Label in source | Unit | Rows |
|---|---|---|---:|
| `brent_crude_usd_bbl` | Crude oil, Brent | $/bbl | 306 |
| `aluminum_usd_mt` | Aluminum | $/mt | 306 |
| `copper_usd_mt` | Copper | $/mt | 306 |
| `rubber_rss3_usd_kg` | Rubber, RSS3 | $/kg | 306 |

Each spans 2021-01 … 2026-05.

**Excluded (3), no substitutes:** `lng_japan_usd_mmbtu` (revised 65/65 months,
max 34.10%), `coal_australia_usd_mt` (2022-02 spot → futures break),
`palm_oil_usd_mt` (three grade/delivery-basis changes). None appears in the
canonical table.

## 3. Lag

| Field | Value | Status |
|---|---|---|
| `minimum_publication_lag_months` | **1** | **Measured** (C1.5-R2, all 65 months at t+1) |
| `operational_lag_months` | **2** | **Policy** — measured lag plus one month of revision margin |
| Lag zero | prohibited | Structural (AD-R36); the policy object refuses to construct |

Every row in the primary table carries `operational_lag_months: 2` and
`minimum_publication_lag_months: 1`. The two are stored separately so the policy
margin can never be read back as a measurement.

## 4. Features

| Feature | Formula | Inputs | Rows/series | Total | Reference range | First usable |
|---|---|---:|---:|---:|---|---|
| `price_level` | \(p_m\) | 1 | 65 | 260 | 2021-01 … 2026-05 | 2021-03 |
| `log_change_1m_pct` | \(100(\ln p_m-\ln p_{m-1})\) | 2 | 64 | 256 | 2021-02 … 2026-05 | 2021-04 |
| `log_change_3m_pct` | \(100(\ln p_m-\ln p_{m-3})\) | 2 | 62 | 248 | 2021-04 … 2026-05 | 2021-06 |
| `log_change_12m_pct` | \(100(\ln p_m-\ln p_{m-12})\) | 2 | 53 | 212 | 2022-01 … 2026-05 | 2022-03 |
| `realized_volatility_3m_pct` | \(\operatorname{std}_{ddof=0}(r_{m-2},r_{m-1},r_m)\) | **4** | 62 | 248 | 2021-04 … 2026-05 | 2021-06 |
| | | | **306** | **1,224** | | |

**Canonical total: 1,224 rows** — exactly 306 × 4, matching the preregistered
expectation. The runner fails explicitly on any other count, and the expected
counts are derived from the declared input lags rather than hard-coded.

Volatility reads **four** months because \(r_{m-2}\) is itself a change from
\(m-3\). Declaring three would understate the lineage and let the feature claim
availability a month too early.

The "first usable" column is `feature_available_month` at each transformation's
earliest reference month — the policy month, since no input was published late.

## 5. Availability and lineage

| Check | Result |
|---|---|
| Unique canonical keys | **1,224 / 1,224** |
| All feature values finite | **yes** |
| `source_available_month` ≤ `feature_available_month` | **all rows** |
| `policy_available_month` ≤ `feature_available_month` | **all rows** |
| Distinct lineage checksums | **1,224** |
| Distinct `source_available_month` values | **> 50** |
| B4 development origins fully covered | **15 / 15** |

That last-but-one row is the check that availability is real rather than
nominal: every archived issue in this repository was downloaded in the same
month, so if availability were derived from the download date all 65 source
months would collapse to one value. They do not.

"Fully covered" for an origin means every one of the 20 series/feature pairs has
at least one reference month usable by then — not merely that *some* feature
exists, which would be trivially true and would hide a series that starts late.

## 6. Primary vs sensitivity

| Table | Lag | Label | Rows |
|---|---:|---|---:|
| `operational_lag_2m` | 2 | **primary** | 1,224 |
| `publication_lag_1m` | 1 | **sensitivity_only** | 1,224 |

`availability_policy` is part of the canonical key, so the two coexist across
2,448 unique keys with neither shadowing the other. The sensitivity table rests
on the same archived publication evidence; it simply carries no revision margin.
It was **not compared against any target** in C2.

## 7. Determinism and reconciliation

| Verification | Result |
|---|---|
| Long ↔ wide reconciliation | **1,224 cells, 0 mismatches** |
| Repeated build, identical content digest | **yes** |
| Two full runs, content checksums compared | **identical** |
| Canonical long content checksum | `29e44c520f2e6db1…` |
| Wide content checksum | `f881f76f2e6b2ca1…` |
| Sensitivity content checksum | `48ffa380efd16069…` |

The wide table contains no transformation logic — a test asserts `to_wide_table`
holds no `math.log`, no formula call, and no standard-deviation call. It is a
pivot, and every number in it was computed once, in the long table.

## 8. Data handling

Imputation, forward-fill, interpolation, clipping, winsorization and rounding of
calculated features: **all none**, in configuration and in code. The feature
module is asserted to contain no `fillna`, `ffill`, `bfill`, `interpolate`,
`clip` or `winsor` call.

Missing inputs, non-positive prices and non-finite results each raise a distinct
error. Each of those guards is exercised against a deliberately broken fixture,
because a rule that has never been seen to reject anything is an assumption
rather than a safeguard.

## 9. A C1.5 field that was mislabelled — since corrected

C2 found that C1.5 stored a boolean named **`estimate_marker`**, set when a
series row carries the token `a/`. The archived PDFs' own footnote block defines
what `a/` means:

> `a/ Included in the energy index; b/ Included in the non-energy index; …`

It is an **index-membership marker, not an estimate flag**. Among the four
primary series Brent carries `a/` (energy index) and aluminum and copper carry
`b/` (non-energy index). Rubber RSS3 is printed inconsistently by the source —
`b/` in 22 of the 65 issues, absent in the other 43 — which is itself a reason
the token cannot carry provenance meaning. The marker is recorded exactly as
each issue displays it and is not normalised.

**Resolved by C1.5-R3** (AD-R45). `estimate_marker` was replaced with separate
index-membership and estimate-status fields, and LNG estimate status is now
derived from the Description statement *"recent two months' averages are
estimates"*. C2 reads `source_footnote_marker`, `source_footnote_meaning` and
`estimate_status` as three distinct things and never infers one from another;
all four primary series are `not_documented_as_estimate`.

**No C2 number moved.** Feature values, availability months, lineage checksums
and row counts were verified identical across all 2,448 primary and sensitivity
rows. The canonical table's content checksum changed because two metadata
columns were added and aluminum/copper now correctly report `b/` — a
metadata-only change, reported as such rather than as a feature-value change.

## 10. Scope

| Guard | State |
|---|---|
| Industry dependency matrix created | **false** |
| Features joined to target | **false** |
| Target association computed | **false** |
| Feature selection using target outcomes | **false** |
| Model trained | **false** |
| B4 baselines compared | **false** |
| Locked final test accessed | **false** |
| `feature_semantics_approved` set | **false** |
| `model_feature_approved` set | **false** (all four series) |

`feature_construction_approved: true` is the only approval C2 grants.

## 11. Limitations

- **Display precision.** Feature inputs are the PDF's *printed* values — Brent
  to one decimal, metals to whole dollars. A one-month log change on a
  whole-dollar metal price carries roughly ±0.02% of quantisation noise at
  current levels. This is the actual historical evidence, and increasing its
  precision would fabricate information, so the noise is accepted and recorded
  rather than smoothed away.
- **The target is still latest-vintage.** B1 emits `release_date` and
  `available_as_of` as NULL because no MPI release calendar has been verified.
  Point-in-time features paired with a latest-vintage target are **not** a
  real-time backtest, and no result built on this table may be described as one.
- **The archive is the World Bank's to reorganise.** Reproducing this table
  depends on the C1.5 manifest checksums, not on those pages staying put.
- **Four series is a narrow view of upstream shocks.** Energy is represented by
  Brent alone once LNG is excluded, and no freight, fertiliser, or food series
  is present. That is a consequence of the C1 verification standard, not an
  assessment of what matters.
- **Construction, not usefulness.** Nothing here shows that any of these 1,224
  values predicts Thai industrial production.
