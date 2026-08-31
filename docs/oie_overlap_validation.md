# Task A2 — OIE Overlap-Window Bridge Validation

Empirical validation of whether the current (2021-based, TSIC) and 2016-based
(TSIC) OIE MPI/Capacity-Utilization editions can be bridged into one
consistent series, using their real 2021-01–2023-12 overlap (36 months).

**Scope.** Current vs. 2016-based edition only. The 2011-based edition is
labeled **ISIC**, not TSIC — `docs/task_a1_history_extension_output.json`
already marks `classification_compatible: "unresolved"` for any pair
touching it, and this script never loads it (`EXCLUDED_EDITIONS` in
`scripts/validate_oie_overlap.py`). It is out of scope here and remains
unapproved.

**Restrictions honored.** No ML model is trained. No final Industry Stress
Index is constructed. This is bridge-evidence generation only.

Reproduce with:

```bash
python scripts/validate_oie_overlap.py
```

Machine-readable output: [`oie_overlap_validation_output.json`](oie_overlap_validation_output.json).
Diagnostic plots: [`oie_overlap_plots/`](oie_overlap_plots/).

## 1. Provisional approval criteria (documented before results were computed)

These thresholds were written into `PROVISIONAL_APPROVAL_CRITERIA` in the
script before the metrics below were inspected, and applied mechanically —
they were not adjusted after seeing which industries would pass.

| Criterion | Threshold | Rationale |
|---|---|---|
| Rebased-level Pearson r | ≥ 0.90 | If the only difference between editions were rebasing arithmetic, correlation should be very close to 1. |
| MoM Pearson r | ≥ 0.70 | Period-over-period growth rates amplify noise relative to levels; a lower bar than levels is expected even for a trustworthy bridge. |
| MoM mean absolute bias | ≤ 2.0 pp | Roughly the scale of typical month-to-month movement for these series. |
| YoY Pearson r | ≥ 0.85 | Slightly stricter than MoM since YoY smooths short-term noise. |
| YoY mean absolute bias | ≤ 3.0 pp | Same reasoning as MoM, scaled for a 12-month horizon. |
| Per-year rebased-level Pearson r | ≥ 0.75 in **every** overlap year | Prevents one good year from masking a bad one in a 3-year average. |
| Discontinuity | no single-month \|diff\| > 4× the series' median \|diff\|, subject to a 1.0-point / 1.0-pp absolute floor | Catches one-off data errors without over-flagging near-noise-level series. |
| Minimum valid pairs | ≥ 30 of 36 months | Below this, status is capped at "Insufficient evidence" regardless of the other numbers. |

**Statuses:** Approved (all criteria met) / Conditional (soft misses only,
e.g. MoM or YoY below bar but levels solid) / Rejected (hard fail: rebased r
< 0.5, or a genuine discontinuity) / Insufficient evidence (too few valid
paired months).

A note on the discontinuity floor: the first run of this script, without an
absolute floor, wrongly rejected IND-04 CapU — its 2021–2022 values are
identical between editions to floating-point precision (median \|diff\| ≈
1e-14), so a 0.59-point difference in 2023 registered as ">4× the median"
and triggered a hard fail. An absolute floor (1.0 index point / 1.0 pp) was
added to fix this degenerate case in the detector itself; it is a robustness
fix to the mechanism, not a relaxation of the approval bar — the tolerance
it introduces (1.0 point) is smaller than every bias threshold already set
above. After the fix, IND-04 CapU correctly reads: rebased r = 1.000, MoM r
= 1.000, YoY r = 1.000 → **Approved**.

## 2. Level-linking vs. growth-rate-linking — why they are not competing options

Level-linking estimates a single scale factor (robust median ratio of
current ÷ older-edition raw values over the 36-month overlap) so the
older edition's raw values can be placed on the current edition's scale.
Growth-rate-linking instead chains the older edition's own MoM or YoY
percentage changes directly onto the current edition's.

**These two methods produce identical growth-rate series by construction.**
Multiplying a series by any constant factor (the level-link factor) does not
change its percentage change from one period to the next — the factor
cancels out of the ratio. So the MoM/YoY correlations reported below already
validate the growth-rate-linking approach; a separately "chained MoM" series
would be numerically indistinguishable from `older_raw × link_factor`'s own
MoM. The two methods only diverge in what they're used to build: a
**level** index needs the link factor to have a shared scale at all; a pure
growth-rate series does not need it.

**Candidate linking method: level-linking via median ratio.** This is what
`level_link_factor_own_weights` in the output records per industry ×
component. It is preferred over a mean ratio because it is robust to any
single anomalous overlap month.

**Lag-availability constraint at the switch boundary.** The current edition
cannot produce its own MoM change for its first native month (2021-01,
needing a 2020-12 value it doesn't have) or a YoY change until it has 12
months of its own history (through 2021-12). Under the recommended switch
month below, this is not actually a problem in practice: 2021-01 is the
**first** month at which native current-edition data exists, so there is no
current-edition MoM/YoY to compute before it — the lag is filled using the
level-linked **older**-edition series for 2020-12 and earlier, which is
validated evidence (an explicitly estimated linking factor), not raw
values from a differently scaled edition used without validation.

## 3. Results by industry × component

Sorted by industry; `Link factor` is the median-ratio level-link factor
(current ÷ 2016-based, own-weight aggregation).

| Industry | Component | Rebased r | MoM r | YoY r | MoM bias (pp) | YoY bias (pp) | Link factor | Status |
|---|---|---|---|---|---|---|---|---|
| IND-01 | MPI  | 0.958 | 0.959 | 0.974 | 0.14  | 1.83  | 0.9940 | Approved |
| IND-01 | CapU | 0.957 | 0.972 | 0.944 | -0.10 | -1.85 | 1.0513 | Approved |
| IND-02 | MPI  | 0.968 | 0.934 | 0.983 | 0.23  | 0.30  | 1.4104 | Approved |
| IND-02 | CapU | 0.968 | 0.956 | 0.984 | 0.12  | -0.14 | 1.2585 | Approved |
| IND-04 | MPI  | 0.993 | 0.993 | 0.994 | 0.18  | 2.48  | 1.0694 | Approved |
| IND-04 | CapU | 1.000 | 1.000 | 1.000 | 0.02  | 0.03  | 1.0000 | Approved |
| IND-05 | MPI  | 0.969 | 0.951 | 0.955 | 0.09  | 0.05  | 0.9542 | **Rejected** (discontinuity: 2023-01, 2023-08) |
| IND-05 | CapU | 0.983 | 0.962 | 0.956 | 0.06  | -0.12 | 0.9773 | Approved |
| IND-06 | MPI  | 0.843 | 0.938 | 0.903 | 0.24  | 2.89  | 1.0582 | Conditional (levels below bar) |
| IND-06 | CapU | 0.949 | 0.955 | 0.927 | 0.10  | 2.27  | 1.2246 | Approved |
| IND-07 | MPI  | 0.893 | 0.985 | 0.905 | 0.19  | 3.18  | 1.1041 | Conditional |
| IND-07 | CapU | 0.840 | 0.927 | 0.806 | 0.06  | 2.43  | 0.9873 | Conditional |
| IND-08 | MPI  | 0.970 | 0.963 | 0.863 | 0.49  | 3.51  | 1.0604 | Conditional (YoY bias over bar) |
| IND-08 | CapU | 0.977 | 0.965 | 0.873 | 0.34  | 2.79  | 1.0550 | Approved |
| IND-09 | MPI  | 0.992 | 0.990 | 0.960 | -0.25 | -1.56 | 0.9637 | Approved |
| IND-09 | CapU | 0.988 | 0.988 | 0.922 | -0.25 | -1.19 | 0.9669 | Approved |
| IND-10 | MPI  | 0.976 | 0.987 | 0.959 | 0.32  | -1.09 | 0.9820 | Approved |
| IND-10 | CapU | 0.967 | 0.983 | 0.973 | 0.16  | -2.13 | 0.9665 | Approved |
| IND-11 | MPI  | 0.986 | 0.995 | 0.990 | 0.24  | 2.11  | 1.1334 | **Rejected** (discontinuity: 2023-11) |
| IND-11 | CapU | 0.988 | 0.997 | 0.997 | -0.16 | -1.75 | 1.0069 | Approved |
| IND-12 | MPI  | 0.956 | 0.943 | 0.966 | 0.27  | 4.88  | 1.0262 | Conditional (YoY bias over bar) |
| IND-12 | CapU | 0.869 | 0.897 | 0.865 | 0.27  | 3.95  | **Rejected** (levels below bar + discontinuity) | 1.1652 |

No industry-component pair was hidden inside an aggregate average — every
row above is reported individually, including the three rejections.

## 4. The ten required statements

1. **Do levels align?** Yes for most pairs (17 of 22 pairs ≥ 0.90 rebased r), but not uniformly — IND-06 MPI, IND-07 (both), and IND-12 CapU fall meaningfully short, and two otherwise-strong pairs (IND-05 MPI, IND-11 MPI) carry a real single-month discontinuity in 2023.
2. **Does MoM align?** Generally well — every pair reaches at least 0.897 Pearson r, and biases are small (mostly under 0.5pp; largest is IND-08 MPI at 0.49pp).
3. **Does YoY align?** Weaker than MoM — several pairs exceed the 3.0pp bias bar (IND-07 MPI 3.18pp, IND-08 MPI 3.51pp, IND-12 both components 3.95/4.88pp), consistent with YoY compounding whatever small MoM discrepancies exist across 12 months.
4. **Most defensible linking method:** level-linking via median ratio over the 36-month overlap — see §2. It is mathematically equivalent to growth-rate-linking for MoM/YoY series and is additionally required to build a continuous rebased level index.
5. **Industries passing for MPI:** IND-01, IND-02, IND-04, IND-09, IND-10 (5 of 11).
6. **Industries passing for CapU:** IND-01, IND-02, IND-04, IND-05, IND-06, IND-08, IND-09, IND-10, IND-11 (9 of 11).
7. **Industries passing for both MPI and CapU:** IND-01, IND-02, IND-04, IND-09, IND-10 (5 of 11).
8. **Maximum approved historical span:** 126 months (2016-01 through 2026-06) — but **only** for the 5 industries approved on both components; for CapU-only-approved industries (IND-05, IND-06, IND-08, IND-11), only Capacity Utilization may claim 126 months, and MPI for those same industries is limited to the current edition's native 66 months unless independently re-reviewed.
9. **Recommended switch month:** 2021-01 — the first month with native current-edition data; no current-edition data exists before it, so there is nothing to prefer over the (level-linked) older edition for any earlier month.
10. **Remaining blocker before production multi-edition ingestion:** (a) Conditional-status pairs (IND-06/07/08/12 MPI, IND-07 CapU) need an explicit decision on whether "Conditional" is acceptable for production or requires deeper investigation; (b) Rejected pairs (IND-05/IND-11 MPI, IND-12 CapU) must not be bridged as-is — root cause of their 2023 discontinuities is unknown; (c) IND-03's definition question (§5) is unresolved; (d) this is a **latest-vintage historical evaluation**, not a real-time vintage backtest — no archived monthly-vintage history exists to validate how a live ingestion pipeline would have behaved historically.

## 5. IND-03 — reported separately, not redefined

IND-03's composition differs across editions (current: TSIC {16, 17};
2016-based: TSIC {17} only — `docs/task_a1_report.md` §7.4) and is excluded
from `CANDIDATE_INDUSTRIES` in this script. It is **not** redefined
automatically here. Status: current-edition-only, 66-month maximum history,
excluded from any bridged-history claim. Three future policy choices exist,
none selected by this task:

1. Keep the current definition (TSIC 16+17) and accept the shorter 66-month history.
2. Narrow the definition to TSIC 17 only, for a consistent long history.
3. Use an unbalanced panel with explicit safeguards.

## 6. Development/test discipline

The 2021-01–2023-12 overlap used here is **bridge-development data only**.
Once a bridge rule is actually selected and frozen (a separate, later
decision — this task only produces evidence), it must not be re-optimized
using the eventual final ML test period. The `bridge_version` field
(`oie_overlap_bridge_v1_2026-08-26`) and this document's estimation window
should be recorded alongside any spliced series built from this evidence.
Any resulting historical evaluation must be described as a **latest-vintage
historical evaluation**, not a real-time vintage backtest, since no archived
monthly-vintage history was found for either edition.

## 7. What this task explicitly did not do

- Did not train any ML model.
- Did not construct the final Industry Stress Index.
- Did not touch the 2011-based ISIC edition.
- Did not select among IND-03's three policy options.
- Did not claim a 126-month bridge for any industry-component pair based on matching division sets alone — every approval above is backed by the correlation/bias/stability/discontinuity evidence in §3.
