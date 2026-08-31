# Task A2.1 — Corrected Overlap-Window Bridge Validation (`oie_overlap_bridge_v2`)

Supersedes `oie_overlap_bridge_v1`. **v1 is preserved unmodified** —
`docs/oie_overlap_validation.md`, `docs/oie_overlap_validation_output.json`
and `scripts/validate_oie_overlap.py` are byte-identical to their v1 state,
pinned by SHA-256 in `tests/test_validate_oie_overlap_v2.py`. v2 writes only
to `*_v2` files.

- Script: `scripts/validate_oie_overlap_v2.py`
- Criteria: `configs/bridge_criteria_v2.yaml` (written before v2 metrics existed)
- Machine-readable: `docs/oie_overlap_validation_output_v2.json`
- Plots: `docs/oie_overlap_plots_v2/` (35 files, 2.2 MB)

Reproduce:

```bash
python scripts/validate_oie_overlap_v2.py
```

No ML model was trained. No Industry Stress Index was constructed. B1
ingestion has not started.

---

## 1. The four v1 defects — all confirmed against the real files

### 1.1 Signed bias was gated instead of mean absolute error — CONFIRMED

`apply_approval_criteria()` in v1 checked `abs(mom_metrics.mean_signed_diff)`
and `abs(yoy_metrics.mean_signed_diff)` against thresholds whose documented
intent was a mean *absolute* difference. Monthly errors of opposite sign
cancel in that statistic. The gap is not academic — from v1's own recorded
numbers:

| Pair | MoM MAE | MoM signed bias | v1 gated on | Cancellation |
|---|---|---|---|---|
| IND-02 MPI | 2.8054 | 0.2271 | 0.2271 | **12.4×** |
| IND-10 MPI | 2.5531 | 0.3211 | 0.3211 | 8.0× |
| IND-10 CapU | 2.3920 | 0.1584 | 0.1584 | 15.1× |
| IND-02 CapU | 2.1267 | 0.1199 | 0.1199 | 17.7× |
| IND-01 MPI | 2.0005 | 0.1396 | 0.1396 | 14.3× |

All five pairs the review named breach their MAE bar; v1 approved every one
of them. v2 gates on `mean_abs_error` and reports `mean_signed_bias` as a
separate, explicitly non-gating field. Nothing in v2 calls
`abs(mean signed error)` a mean absolute error.

### 1.2 Both components got index-number treatment — CONFIRMED

v1's `build_representations()` applied `100 × (x_t/x_{t-1} − 1)` to MPI **and**
Capacity Utilization, and labelled both outputs "pp". For a rate already
expressed in percent that is a relative change mislabelled as a
percentage-point change. v1 also applied a multiplicative median-ratio link
factor to CapU. v2 splits the treatment (§2).

### 1.3 Linked levels were never validated — CONFIRMED

v1 rebased each edition to *its own* first overlap month (`raw / raw[0] × 100`),
forcing both series to start at exactly 100, then gated only on correlation.
That representation cannot see a level offset, and v1 never compared
`current` against `older × link_factor` at all. For IND-01 MPI:

| Quantity | Value |
|---|---|
| v1 rebased Pearson r (what v1 gated on) | 0.958 → passed |
| v1 rebased mean absolute error | **8.88 index points** (never checked) |
| v2 linked-level mean absolute error | **3.62 index points** |
| v2 linked-level normalized MAE / IQR | **0.408** vs a 0.25 bar → fails |

The review's "≈8.9 index points" is the rebased-representation MAE. Both it
and the linked-level MAE are large enough to matter; v1 checked neither.

### 1.4 A mechanical outlier rule acted as proof of rejection — CONFIRMED

v1 hard-rejected any pair with a flagged discontinuity while approving pairs
carrying large persistent error. IND-05 MPI (linked MAE 1.25, nMAE 0.161 —
among the *better* pairs) was Rejected for two flagged months, while IND-01
MPI (nMAE 0.408) was Approved. v2 investigates every flagged month down to
TSIC division level and returns `Needs source review` where the cause cannot
be established from the data (§4), while magnitude criteria handle persistent
error independently.

---

## 2. Component-appropriate transformations and link methods

| | MPI | Capacity Utilization |
|---|---|---|
| Series type | index number | rate in percent |
| MoM | `100 × (x_t/x_{t−1} − 1)` (percent growth) | `x_t − x_{t−1}` (**percentage points**) |
| YoY | `100 × (x_t/x_{t−12} − 1)` | `x_t − x_{t−12}` (**percentage points**) |
| Link | multiplicative: `older × median(current/older)` | additive: `older + median(current − older)` |

**Additive alignment for CapU is justified against no alignment**, per the
selection rule pre-stated in the config (adopt additive only if it strictly
reduces linked-level MAE). It strictly reduced MAE for all 11 industries, so
it was adopted in all 11 — but the amount of work it does varies enormously:

| Industry | Offset | MAE unaligned | MAE aligned |
|---|---|---|---|
| IND-06 | **+10.93pp** | 11.16 | 1.06 |
| IND-02 | **+10.23pp** | 10.33 | 1.35 |
| IND-12 | **+7.31pp** | 7.60 | 2.22 |
| IND-01 | +2.67pp | 2.53 | 1.24 |
| IND-08 | +2.65pp | 2.63 | 1.18 |
| IND-09 | −2.47pp | 2.30 | 1.05 |
| IND-10 | −1.89pp | 2.88 | 2.47 |
| IND-05 | −1.78pp | 1.76 | 0.77 |
| IND-07 | −0.78pp | 1.62 | 1.53 |
| IND-11 | +0.51pp | 1.25 | 1.14 |
| IND-04 | +0.0004pp | 0.0162 | 0.0159 |

**A substantive finding, not just a method note:** for IND-06, IND-02 and
IND-12 the two editions disagree about the *absolute level* of capacity
utilisation by 7–11 percentage points. Their shapes align well once offset
(post-alignment MAE 1.06–2.22pp), so a bridged series is usable for
*changes*, but any future use of CapU **levels** across the bridge must treat
that offset as a real, unexplained redefinition of the capacity denominator,
not as noise. IND-04's offset is 0.0004pp — it satisfies the "strictly
reduces MAE" rule but has no practical effect.

---

## 3. Results

`nMAE/IQR` = linked-level mean absolute error divided by the current series'
own interquartile range (bar: 0.25; gross-misfit hard fail: 0.50).
`Jump (×p99)` = splice boundary jump, and its size relative to the 99th
percentile of ordinary monthly changes in the same series (hard fail: > 1.0).
MPI values are index points / percent growth; CapU values are percentage points.

#### MPI

| Industry | Link | Linked MAE | nMAE/IQR | RMSE | Bias | Max err | r | MoM MAE | YoY MAE | Jump (×p99) | v1 | v2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IND-01 | ×0.9940 | 3.62 | 0.408 | 4.76 | −0.96 | 12.19 | 0.958 | 2.00 | 1.90 | +3.91 (0.15) | Approved | **Needs source review** |
| IND-02 | ×1.4104 | 2.05 | 0.113 | 2.93 | −0.27 | 10.78 | 0.968 | 2.81 | 2.37 | −0.43 (0.02) | Approved | **Needs source review** |
| IND-04 | ×1.0694 | 1.86 | 0.104 | 2.14 | −0.03 | 4.40 | 0.993 | 1.03 | 2.69 | −6.49 (0.31) | Approved | **Approved** |
| IND-05 | ×0.9542 | 1.25 | 0.161 | 1.64 | +0.07 | 4.19 | 0.969 | 1.74 | 1.45 | +9.56 (0.59) | Rejected | **Needs source review** |
| IND-06 | ×1.0582 | 2.82 | **0.577** | 3.50 | +0.02 | 8.43 | 0.843 | 2.36 | 3.42 | +0.56 (0.03) | Conditional | **Rejected** |
| IND-07 | ×1.1041 | 2.46 | 0.288 | 3.28 | −1.04 | 8.31 | 0.893 | 1.19 | 3.48 | −2.94 (0.13) | Conditional | **Conditional** |
| IND-08 | ×1.0604 | 2.88 | 0.260 | 3.52 | −0.64 | 8.09 | 0.970 | 1.95 | 3.66 | +2.48 (0.12) | Conditional | **Conditional** |
| IND-09 | ×0.9637 | 1.64 | 0.098 | 1.91 | −0.09 | 4.71 | 0.992 | 1.15 | 2.14 | −0.83 (0.04) | Approved | **Approved** |
| IND-10 | ×0.9820 | 3.72 | 0.130 | 4.41 | −0.29 | 8.93 | 0.976 | 2.55 | 4.03 | +18.42 (0.38) | Approved | **Conditional** |
| IND-11 | ×1.1334 | 1.98 | 0.116 | 2.56 | +0.60 | 7.28 | 0.986 | 1.10 | 2.84 | +4.31 (0.06) | Rejected | **Needs source review** |
| IND-12 | ×1.0262 | 4.14 | 0.348 | 5.13 | +0.96 | 9.91 | 0.956 | 2.88 | 5.45 | +10.74 (0.33) | Conditional | **Conditional** |

#### Capacity Utilization

| Industry | Link | Linked MAE | nMAE/IQR | RMSE | Bias | Max err | r | MoM MAE | YoY MAE | Jump (×p99) | v1 | v2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IND-01 | +2.67pp | 1.24 | 0.183 | 1.63 | −0.23 | 3.51 | 0.957 | 0.77 | 1.15 | +3.13 (0.17) | Approved | **Approved** |
| IND-02 | +10.23pp | 1.35 | 0.161 | 1.63 | +0.11 | 3.31 | 0.968 | 1.11 | 1.90 | +1.90 (0.14) | Approved | **Approved** |
| IND-04 | +0.00pp | 0.02 | 0.004 | 0.08 | +0.02 | 0.50 | 1.000 | 0.02 | 0.02 | −0.15 (0.01) | Approved | **Approved** |
| IND-05 | −1.78pp | 0.77 | 0.120 | 0.95 | +0.02 | 1.95 | 0.983 | 0.97 | 1.03 | +4.49 (0.43) | Approved | **Approved** |
| IND-06 | +10.93pp | 1.06 | 0.175 | 1.29 | +0.23 | 2.72 | 0.949 | 1.33 | 1.01 | +1.03 (0.08) | Approved | **Approved** |
| IND-07 | −0.78pp | 1.53 | **0.355** | 1.83 | +0.04 | 4.20 | 0.840 | 1.43 | 1.75 | −1.01 (0.07) | Conditional | **Conditional** |
| IND-08 | +2.65pp | 1.18 | 0.183 | 1.46 | −0.06 | 3.32 | 0.977 | 0.96 | 1.61 | +3.39 (0.25) | Approved | **Approved** |
| IND-09 | −2.47pp | 1.05 | 0.079 | 1.39 | +0.24 | 3.07 | 0.988 | 0.84 | 1.75 | −1.10 (0.09) | Approved | **Needs source review** |
| IND-10 | −1.89pp | 2.47 | 0.149 | 2.93 | −0.30 | 5.86 | 0.967 | 1.49 | 2.61 | +9.42 (0.43) | Approved | **Approved** |
| IND-11 | +0.51pp | 1.14 | 0.102 | 1.45 | +0.06 | 4.03 | 0.988 | 0.64 | 1.30 | +5.42 (0.19) | Approved | **Approved** |
| IND-12 | +7.31pp | 2.22 | 0.242 | 2.98 | +0.29 | 7.60 | 0.869 | 2.20 | 3.06 | +2.01 (0.15) | Rejected | **Conditional** |

**8 of 22 pairs changed status.** v1's approval counts are invalidated.

| Status | Count |
|---|---|
| Approved | 10 |
| Conditional | 6 |
| Needs source review | 5 |
| Rejected | 1 |
| Insufficient evidence | 0 |
| Excluded due to composition change | 0 (IND-03 is excluded before scoring) |

---

## 4. Discontinuity investigations — all flagged months, none removed

Every flagged month was decomposed to TSIC division level. The industry
residual is exactly separable into per-division contributions for both link
methods, because each edition's renormalized weights sum to 1.

| Pair | Month | Dominant division | Which edition moved | Cause | Resolved |
|---|---|---|---|---|---|
| IND-01 MPI | 2021-01 | TSIC 10 | indeterminate | unresolved | No |
| IND-02 MPI | 2021-01 | TSIC 14 | indeterminate | unresolved | No |
| IND-02 MPI | 2021-08 | TSIC 13 | current | edition-specific movement | No |
| IND-05 MPI | 2023-01 | TSIC 20 | current | edition-specific movement | No |
| IND-05 MPI | 2023-08 | TSIC 20 | 2016-based | edition-specific movement | No |
| IND-11 MPI | 2023-11 | TSIC 29 | current | edition-specific movement | No |
| IND-09 CapU | 2022-05 | TSIC 27 | 2016-based | edition-specific movement | No |
| IND-09 CapU | 2023-12 | TSIC 26 | current | edition-specific movement | No |
| IND-12 CapU | 2021-06 | TSIC 31 | current | **aggregation weight difference** | **Yes** |
| IND-12 CapU | 2023-03 | TSIC 32 | current | **aggregation weight difference** | **Yes** |
| IND-12 CapU | 2023-05 | TSIC 32 | current | **aggregation weight difference** | **Yes** |
| IND-12 CapU | 2023-06 | TSIC 32 | current | **aggregation weight difference** | **Yes** |

**IND-12 CapU is the one resolved case.** TSIC 32 carries a within-industry
weight of 0.7164 in the current edition versus 0.6089 in the 2016-based
edition (TSIC 31: 0.2836 vs 0.3911). The editions aggregate the same two
divisions in materially different proportions, which fully accounts for the
flagged months — so IND-12 CapU is *not* sent to source review; it lands on
Conditional for missing its MoM (2.20 > 2.0pp) and YoY (3.06 > 3.0pp) bars.

**The 2021-01 flags for IND-01 and IND-02 MPI are `indeterminate` for a
structural reason**: 2021-01 is the current edition's first observation, so
its own month-over-month change cannot be computed, and there is no way to
tell from the data which edition moved. This is a genuine limit, reported as
such rather than guessed.

For the remaining seven, the evidence establishes *which edition moved and in
which division*, and rules out a parsing fault (all values parsed as finite
numbers). It cannot distinguish a **source revision** from a **genuine
series-definition change** — that requires an OIE methodology or revision
note, which has not been located. Those pairs are therefore
`Needs source review`, not Rejected.

### A hypothesis tested and rejected

IND-01 and IND-02 MPI show their largest residuals decaying away from the
current edition's first month (IND-01: −12.19, −9.34, −4.56, −1.19, −0.27),
which would suggest an edition-wide start-up artifact and argue for a later
switch month. **Tested across all 22 pairs, this does not hold**: the median
ratio of mean absolute error in the first 6 overlap months versus the
remaining 30 is **0.99**, and only 2 of 22 pairs exceed 2×. It is a
pair-specific effect, not an edition-wide one, so it is **not** grounds for
moving the switch month. Recorded per pair as
`early_overlap_transient_diagnostic` with `"gating": false` — it was defined
after seeing v2 residuals, so using it to move an approval status would be
fitting a threshold to results.

---

## 5. Candidate spliced series — built and checked

126 monthly observations, 2016-01 through 2026-06, for all 22 pairs. Every
series passed: no duplicate month keys, no gaps, chronological.

### Separate switch months per representation

A single universal switch month is **not** claimed.

| Representation | Switch | Why |
|---|---|---|
| **Level** | 2021-01 | First month with native current-edition data. Linked older-edition values before it. |
| **MoM** | 2021-02 | The current edition has no 2020-12 observation, so it cannot form a native MoM at 2021-01. 2021-01's MoM comes from the older edition's own 2020-12→2021-01, both values from one edition. |
| **YoY** | 2022-01 | The current edition has no 2020 observations, so it cannot form a native YoY before 2022-01. Older-edition-derived YoY is used through 2021-12. |

No candidate series uses a cross-edition lag — asserted per pair in the
machine-readable output (`invalid_cross_edition_lag_used: false`) and pinned
by tests.

### Boundary jump

Measured at the 2020-12 → 2021-01 level switch, in each component's own
units, against the distribution of ordinary monthly changes elsewhere in the
same 126-month series.

**No splice manufactures a shock.** The largest boundary jump relative to
ordinary variation is IND-05 MPI at **0.59× the 99th percentile** (jump
+9.56% against a p99 of 16.30%); every other pair is below 0.44×. Percentile
ranks run 4%–84%, i.e. each boundary jump is an ordinary-sized monthly move
for its own series. Absolute jumps look large for some pairs (IND-10 MPI
+18.42%) purely because those series are genuinely volatile month to month
(IND-10 MPI median |monthly change| is 13.77%).

---

## 6. The required statements

1. **Corrected MPI statuses** — Approved: IND-04, IND-09. Conditional: IND-07, IND-08, IND-10, IND-12. Needs source review: IND-01, IND-02, IND-05, IND-11. Rejected: IND-06.
2. **Corrected CapU statuses** — Approved: IND-01, IND-02, IND-04, IND-05, IND-06, IND-08, IND-10, IND-11. Conditional: IND-07, IND-12. Needs source review: IND-09. Rejected: none.
3. **Approved for both components: IND-04 only (1 of 11).** v1's "5 industries pass both" is **not** reproduced and is withdrawn.
4. **Link methods** — MPI: multiplicative median ratio. CapU: additive median offset, adopted for all 11 after strictly beating no-alignment.
5. **Switch months** — level 2021-01, MoM 2021-02, YoY 2022-01.
6. **Boundary jumps** — all within ordinary monthly variation; max 0.59× p99 (IND-05 MPI). No hard failures.
7. **Unresolved source discontinuities** — 8 months across 5 pairs (IND-01 MPI, IND-02 MPI ×2, IND-05 MPI ×2, IND-11 MPI, IND-09 CapU ×2). Cause requires an OIE methodology/revision note not yet located.
8. **Is a 126-month K=2 history defensible?** **Only for IND-04.** A K=2 equal-weight target needs both MPI and CapU bridges approved for the same industry, and only IND-04 clears both. For the 7 industries approved on CapU but not MPI, only Capacity Utilization has a defensible 126-month span; their MPI is limited to the current edition's native 66 months.
9. **May B1 begin?** Not on this evidence for the panel as a whole — see §7.
10. **IND-03** — unchanged: excluded before scoring, current-edition-only, 66-month cap, three policy options, none selected here.

---

## 7. What is still blocked

- **The 5 `Needs source review` pairs** need an OIE methodology or revision note to distinguish source revision from series-definition change. Until then their bridges are neither approved nor rejected.
- **IND-06 MPI is Rejected** on magnitude alone: linked-level normalized MAE 0.577 against a 0.500 gross-misfit bound. This is not a discontinuity artifact and will not be fixed by a source note.
- **The 6 `Conditional` pairs** need a policy decision on whether Conditional is acceptable for production ingestion. This task does not make that decision.
- **CapU level offsets of 7–11pp** (IND-02, IND-06, IND-12) are unexplained and matter for any future use of CapU *levels* across the bridge.
- **Evaluation framing** remains a **latest-vintage historical evaluation**, not a real-time vintage backtest — no archived monthly-vintage history exists for either edition.

## 8. Development/test discipline

The 2021-01–2023-12 overlap is bridge-development data only. `bridge_version`
(`oie_overlap_bridge_v2`) and the estimation window are recorded in every
result row. The selected bridge rule must be frozen before any final ML test
period and must not be re-optimized against it.
