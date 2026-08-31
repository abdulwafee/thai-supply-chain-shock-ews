# Task C3 — Crosswalks

Two crosswalks, both from official classifications, both preregistered in
[`configs/industry_exposure.yaml`](../configs/industry_exposure.yaml) before any
coefficient was read. Neither was revised on the basis of how it performs against
the target — no such comparison exists in C3.

---

## 1. Commodity → official I/O sector

Evidence: NESDC "Input-Output Description".

| Series | I/O | Official label | Type | Conf. |
|---|---|---|---|---|
| `brent_crude_usd_bbl` | **031** | Petroleum and natural gas | `official_broader_aggregate` | medium |
| `aluminum_usd_mt` | **107** | Non-ferrous metal | `official_broader_aggregate` | medium |
| `copper_usd_mt` | **107** | Non-ferrous metal | `official_broader_aggregate` | medium |
| `rubber_rss3_usd_kg` | **095** | Rubber sheet and block rubber | `official_broader_aggregate` | medium |

**No mapping is claimed to be exact.** Every one of the four is a broader
official aggregate than the commodity it stands for, and each is flagged as such.

### Brent — broader than crude

> *"This sector covers the exploration activities for crude petroleum **and
> natural gas**, the drilling, completing and equipping of wells… and the
> operation of oil and natural gas wells."*

The category prices two things; Brent prices one. The coefficient embeds natural
gas use that Brent does not track. **Flagged**, `broader_than_commodity: true`.
Sector 093 (Petroleum refineries) was considered and rejected — it is a
downstream *processor* of crude, not crude.

### Aluminum and Copper — the same sector

> *"…the manufacture of primary non-ferrous metal products consisting of primary
> and secondary smelting, alloying, refining, rolling and drawing, founding and
> casting."*

Both resolve to **107**, which combines *all* primary non-ferrous metals.
Aluminum cannot be separated from copper — or from zinc, lead or tin — inside it.

**Consequence, stated plainly: their coefficients are identical by construction.
They are one aggregate exposure reported twice, not two independently measured
commodity-specific cost shares.** All 24 affected rows carry
`shared_io_source_sector: true` and name each other in `shared_with`, and a test
asserts the flag is present wherever the coefficients coincide.

Sector 035 ("Other non-ferrous metals") was considered — its definition names
copper ore explicitly — but it is *ore extraction*, not the refined metal an LME
price quotes.

### Rubber RSS3 — distinguished from fabricated products

> *"This sector covers rubber sheets, block rubber, crepe rubber and other
> processed rubber."*

RSS3 is one grade within it, so the mapping is still an aggregate. But the
distinction that matters **is** preserved: this is *processed natural rubber*,
separated from **016** (agricultural latex, upstream), **096** (tyres and tubes)
and **097** (other rubber products — gloves, hoses, mats).

## 2. Project industry → official I/O sectors

All 12 industries reproduce `configs/industry_mapping.yaml` exactly — same ids,
names and TSIC divisions. The loader **refuses to run** if any of the three
differs, so a C3 mapping cannot drift from the dimension B1 and B3 use.

**91 I/O sectors** are mapped across the 12 industries, and no sector serves two
industries (a test rejects double assignment, which would double-count output).

| Industry | Name | TSIC | I/O sectors | Conf. | Largest components by output weight |
|---|---|---|---:|---|---|
| IND-01 | Food, Beverages and Tobacco | 10,11,12 | 25 | high | 042 0.15; 049 0.14 |
| IND-02 | Textiles, Apparel and Leather | 13,14,15 | 11 | high | 072 0.34; 068 0.22 |
| IND-03 | Wood and Paper | 16,17 | 4 | high | 081 0.36; 082 0.24 |
| IND-04 | Refined Petroleum Products | 19 | 2 | high | 093 0.95; 094 0.05 |
| IND-05 | Chemicals and Pharmaceuticals | 20,21 | 9 | high | 086 0.42; 084 0.20 |
| IND-06 | Rubber and Plastics | 22 | 4 | high | 098 0.52; 095 0.22 |
| IND-07 | Non-metallic Mineral Products | 23 | 6 | high | 100 0.29; 102 0.25 |
| IND-08 | Basic and Fabricated Metals | 24,25 | 6 | high | 111 0.29; 106 0.17 |
| IND-09 | Computer, Electronics and Electrical | 26,27 | 9 | **medium** | 118 0.52; 122 0.15 |
| IND-10 | Machinery and Equipment | 28 | 5 | **medium** | 116 0.79; 115 0.14 |
| IND-11 | Motor Vehicles and Other Transport | 29,30 | 5 | high | 125 0.85; 126 0.08 |
| IND-12 | Furniture and Other Manufacturing | 31,32 | 5 | high | 132 0.75; 134 0.12 |

### Documented scope differences

- **IND-09 / IND-10 are `medium`** because sector **116** ("Office and household
  machinery and appliances") straddles TSIC 26 office machinery and TSIC 27/28
  household appliances. The official label does not permit a clean split, so 116
  is assigned to IND-10, **not** double-counted, and the ambiguity is recorded
  rather than resolved by assertion. It dominates IND-10 at 79% of output, so the
  caveat is material there.
- **Furniture is split by material** in the I/O classification: **080** (wooden)
  and **109** (metal) both belong to TSIC 31 and are collected into IND-12 rather
  than left with wood or metals.
- **083** (Printing and publishing) is TSIC 18, which B1 excludes from the
  taxonomy entirely — so it is assigned to no industry here either.
- **127** (Repair of motor vehicles) is TSIC 45 trade-and-repair, not
  manufacturing, and is excluded.
- **125 and 126** carry the same official label ("Motor vehicles") under distinct
  codes; both are included in IND-11.

## 3. Aggregation weights — official, never equal

```
direct:  A[c][IND] = sum_j Z[c][j] / sum_j X[j]
total:   T[c][IND] = sum_j ( T[c][j] * X[j] ) / sum_j X[j]
```

Weights come from **official gross output (column 600)** in the same table as the
coefficients. `equal_weights_used: false`, asserted by test.

The direct formula is **not** a weighted mean of ratios — summing the numerator
and the denominator gives the *exact* aggregate technical coefficient for the
combined sector. No weight is invented.

The total-requirement formula **is** a weighted mean, and is labelled as one: the
Leontief inverse of an aggregated matrix is not the aggregate of the inverse, and
C3 does not pretend otherwise.

Where no defensible weight exists the code raises rather than falling back to
equal shares — an aggregation whose weights do not sum to one is not an
aggregation.

## 4. Confidence rules — preregistered, never target-informed

| Level | Criteria |
|---|---|
| **High** | Exact official one-to-one correspondence; compatible definitions; no material scope mismatch |
| **Medium** | Official broader aggregate; transparent many-to-one; scope difference documented |
| **Low** | Qualitative evidence only; no defensible quantitative crosswalk |
| **Unresolved** | Conflicting definitions; missing weights; ambiguous sector identity |

`based_on_target_performance: false`. A low or unresolved mapping is **never**
silently converted to zero: unresolved exposure stays null, and zero is written
only where the matrix supplies an *observed* zero.

All 48 commodity mappings land at **medium** — every commodity is a broader
official aggregate, so none qualifies as high, and all have quantitative
crosswalks, so none falls to low.


## 5. C3-R1 — the 180-to-58 crosswalk could not be established

NESDC publishes the 2015 table at 180, 58, 26 and 16 sectors. Aggregating the
180-sector table to 58 would be an independent check on every coefficient — but
it needs a concordance, and none was found.

Searched, and what each yielded:

| Source | Result |
|---|---|
| `Input-Output-Classification.pdf` | **0** mentions of "58" |
| `Book_IO2015_EN.pdf` (455 pages) | No classification or concordance section |
| WordPress media library | Aggregated **data** files only (x58/x26/x16), no mapping |
| Contiguous-partition hypothesis | **Fails** — 58-sector `003` equals 180-sector `004`, skipping `003` |

The last row is the informative one: the 58-sector scheme **regroups** rather than
concatenates, so the mapping cannot be read off code order.

**C3-R1 refuses to infer it.** A subset-sum search over gross output would fit
*a* partition, but fitting is not evidence and the solution is not unique —
and inferring from numeric proximity is precisely what this task forbids.
`build_180_to_58_crosswalk` raises `AggregationCrosswalkUnavailable` rather than
returning a guess.

The sector-level reconciliation is therefore recorded as
**`not_executed_official_crosswalk_unavailable`** — a third state, distinct from
passed and from failed. **No unexplained discrepancy was found, because no
sector-level comparison was run.**

What *was* compared needs no crosswalk: **12 partition-invariant grand totals**
(gross output, value added, intermediate transactions, imports, and all three
margins signed and absolute) matched **exactly**, at a tolerance of 0.5
preregistered from the source's thousand-Baht precision. The 180-sector
calculations are confirmed at every level the evidence supports.
