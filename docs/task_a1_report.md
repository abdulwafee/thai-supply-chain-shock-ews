# Task A1 Report — Target Component Source Verification

**Revision 5 (Task A2.1 — §10 SUPERSEDED).** An independent review found four
correctness defects in the Task A2 (v1) methodology that produced §10's numbers:
approval gated on signed bias rather than mean absolute error (letting monthly
errors cancel), Capacity Utilization was treated as an index number rather than a
percent rate, the actually-linked older series was never compared against the
current series, and a mechanical outlier rule was treated as proof of rejection.
All four were confirmed against the real files and corrected in
`oie_overlap_bridge_v2`. **§10's headline result does not survive: "5 industries
pass both components" is withdrawn — the corrected figure is 1 (IND-04 only).**
Read §10 only alongside `docs/oie_overlap_validation_v2.md`, which is now the
authoritative bridge result. The v1 evidence files are deliberately preserved
unmodified for audit.

**Revision 4 (Task A2 — empirical overlap-window bridge validation).** Revision 3 ended §7.6 by
naming the overlap-window validation as the one thing still missing before any 126-month bridge
claim could be trusted. That validation has now been run — see new §10 and
`docs/oie_overlap_validation.md` for the full evidence. **The headline correction this revision
makes to Revision 3: the 126-month, 11-industry bridge claim in §7.7 was correct about division
composition but not yet backed by empirical evidence — it is not. Only 5 of those 11 industries pass
on both MPI and CapU; 2 fail outright (Rejected) on MPI; the rest are Conditional.** No ML model was
trained and no final Industry Stress Index was constructed in this revision — restated per the
explicit restriction on this task.

**Revision 3 (history-extension correction).** Revision 2's history-extension section (formerly §7)
contained a real arithmetic contradiction (stating both 18 and 19 as the current↔2016-edition TSIC
division intersection, without ever computing it in code) and two real gaps (Capacity Utilization
was never inspected for the older editions; the 2011-based edition was never downloaded). This
revision fixes all three with a dedicated script, `scripts/audit_history_extension.py`, which
downloads and persists both older editions with full manifests, audits MPI and CapU **separately**
for every edition, and computes every division-set comparison with real Python `set` operations —
nothing in §7 below is typed in by hand. See `docs/task_a1_history_extension_output.json` for the
full machine-readable evidence.

**Revision 2 (quality gate).** This revision corrects two overclaims in Revision 1 and adds four
analyses Revision 1 did not attempt (TSIC hierarchy/duplicate audit, explicit date parsing, vintage
risk, history-extension feasibility). Every real number below was re-derived from the same two real
files already in `data/raw/`, re-parsed by a hardened version of `scripts/audit_target_sources.py`.
Nothing here is estimated or carried over unchanged from Revision 1 without re-verification.

**The central correction**: Revision 1 said MPI and CapU "Pass." That conflated two different
claims. This revision separates them explicitly, per the confirmed interpretation for this task:

| Claim | MPI | CapU |
|---|---|---|
| **Source access verified** | **Yes** | **Yes** |
| **Target-component approved** | **No — Conditional** | **No — Conditional** |

Source access being verified does not mean the component is approved for the Stress Index. Four
things still block approval for both MPI and CapU (detailed in §5–§6 below): the weighted-
aggregation rule for multi-division industries is designed but not implemented; IND-03/IND-12's
partial-coverage scope is undecided; the MPI-vs-CapU redundancy test has not run; and only
latest-vintage data has been inspected, not point-in-time vintages.

---

## 1. Corrected industry-coverage language

Revision 1 reported "12/12 industries covered." That is true only for the *original, coarser*
"any coverage" eligibility bar (`minimum_industry_coverage: 11` in `configs/targets.yaml`) — it is
not the same claim as "ready to construct all 12 industry values." The three measures, kept
permanently separate from here on (never collapsed into one number again):

| Measure | MPI | CapU |
|---|---|---|
| Industries with **any** coverage (full or partial) | 12 / 12 | 12 / 12 |
| Industries with **full** coverage (every constituent TSIC division present) | **10 / 12** | **10 / 12** |
| Industries with **partial** coverage (at least one constituent division missing) | **2 / 12** (IND-03, IND-12) | **2 / 12** (IND-03, IND-12) |

`scripts/audit_target_sources.py`'s `IndustryCoverage` dataclass now exposes `any_coverage_count`,
`full_coverage_count`, and `partial_coverage_count` as three separate properties — there is no
single "coverage" field left to accidentally report out of context.

---

## 2. TSIC hierarchy and duplicate-row audit

**Question asked**: does each TSIC division have one row or multiple, could the original
dict-based `missingness[division] = value` have silently overwritten an earlier row, and do MPI and
CapU share the same hierarchy?

**Findings, from direct inspection of both real files**:

- **No duplicate division labels exist in either file** — checked explicitly (every occurrence of a
  `"TSIC : NN "` pattern was counted per division; every division from 10–32 that appears, appears
  exactly once). The original script's dict-based storage was not, in fact, silently overwriting
  anything in these two specific files. That does not make the original code correct: it assumed
  this without checking. The hardened script now **raises `DuplicateDivisionError`** the instant a
  second occurrence of any division label is seen, rather than continuing to assume uniqueness.
  `tests/test_audit_target_sources.py::test_audit_oie_file_raises_on_duplicate_division_label`
  proves this on a synthetic duplicate.
- **Row hierarchy, confirmed for both files**: Total (`ดัชนีรวม...`, weight 100) → Division
  (`TSIC : NN`, 2-digit, e.g. `TSIC : 10`) → Group (`TSIC : NNNN`, 4-digit) → Class (5-digit numeric
  label, no `TSIC :` prefix) → Product (a named line item with its own product code, e.g. `010`).
  The **division-level row is the correct one to use as each TSIC division's index** — it is the
  row this project's `INDUSTRY_TSIC_DIVISIONS` mapping already targets, and it is the row whose
  weight is a share of the true grand total (see next point), not a sub-share within a group.
- **MPI and CapU use the identical hierarchy and the identical 22 divisions, in the identical row
  order** — the only structural difference is the column offset of the label (`TSIC :` text sits in
  column index 2 in the MPI file, column index 0 in the CapU file); the script auto-detects this
  rather than assuming one offset.
- **Official weights exist and were extracted**: the column immediately right of each division's
  label holds a numeric weight (e.g. `16.671088444837988` for TSIC 10 in MPI, `16.67109` in CapU —
  same weight, different rounding). **These 22 division-level weights sum to exactly 100.0000 in
  both files**, matching the grand-total row's own weight of 100. This is the evidence-backed
  aggregation rule input for §4: OIE already publishes the value-added weight share needed for a
  weighted (not equal) aggregation across divisions within a composite industry — and the exact
  100.0000 sum, with no residual, is also the strongest evidence available that TSIC 18 and 33 are
  **not** folded into another division's reported weight (see §4.2).

---

## 3. Explicit parsed calendar-date verification

Revision 1 verified a *count* of month columns (and, in its first run, miscounted it — see the
history in the git log / prior conversation turn). This revision parses **actual Gregorian dates**
from the workbook's Buddhist-Era year row and Thai-month-abbreviation row, not a column count.

| Check | MPI | CapU |
|---|---|---|
| Earliest month | **2021-01-01** | **2021-01-01** |
| Latest month | **2026-06-01** (flagged preliminary, `*`) | **2026-06-01** (flagged preliminary) |
| Unique month count | **66** | **66** |
| Chronological order | **True** | **True** |
| Duplicate months | **False** | **False** |
| Missing months (gaps) within the span | **None** | **None** |
| Buddhist→Gregorian conversion | `2564 − 543 = 2021`, verified against the printed month sequence | same |

This is now a fully verified, gap-free, duplicate-free, chronologically-ordered 66-month panel for
both series — the strongest single finding in this report. `tests/test_audit_target_sources.py`
covers BE→CE conversion, preliminary-marker stripping, chronological-order detection, and gap
detection independently, each against a synthetic (non-real) fixture.

---

## 4. Aggregation requirements — per industry

### 4.1 Per-industry documentation

| Industry | Included divisions | Present | Missing | Source rows used | Official weight available? | Proposed rule |
|---|---|---|---|---|---|---|
| IND-01 | 10, 11 | 10, 11 | — | division-level rows | Yes (16.67, 3.81) | Weighted average by OIE weight |
| IND-02 | 13, 14, 15 | 13, 14, 15 | — | division-level rows | Yes | Weighted average |
| IND-03 | 16, 17, 18 | 16, 17 | **18** | division-level rows for 16, 17 | Yes for 16, 17 | Weighted average over 16+17 only — see §4.2 for the scope question this raises |
| IND-04 | 19 | 19 | — | single row, no aggregation needed | Yes (10.74) | Direct (K=1, no weighting decision) |
| IND-05 | 20, 21 | 20, 21 | — | division-level rows | Yes | Weighted average |
| IND-06 | 22 | 22 | — | single row | Yes | Direct |
| IND-07 | 23 | 23 | — | single row | Yes | Direct |
| IND-08 | 24, 25 | 24, 25 | — | division-level rows | Yes | Weighted average |
| IND-09 | 26, 27 | 26, 27 | — | division-level rows | Yes | Weighted average |
| IND-10 | 28 | 28 | — | single row | Yes | Direct |
| IND-11 | 29, 30 | 29, 30 | — | division-level rows | Yes | Weighted average |
| IND-12 | 31, 32, 33 | 31, 32 | **33** | division-level rows for 31, 32 | Yes for 31, 32 | Weighted average over 31+32 only — see §4.2 |

**Proposed aggregation rule (evidence-backed, not adopted by default)**: for any industry built from
more than one TSIC division, use the **OIE-published value-added weight as the aggregation weight**
(a weighted average of the constituent divisions' index values, weights renormalized to sum to 1
over just the *present* divisions for IND-03 and IND-12), **not a simple/equal average across
divisions**. Equal weighting across divisions was never justified and is explicitly not used here —
this satisfies the instruction not to average TSIC divisions equally without justification. This
rule is *proposed and evidence-backed*, not yet implemented — `compute_raw_stress_index` remains a
stub, and no 12-industry value has been constructed under this rule yet.

### 4.2 TSIC 18 and TSIC 33: absent, not hidden

Investigated directly: are these two divisions absent, folded into another subtotal, published
elsewhere, or should the taxonomy change?

**Corrected wording (this revision): the evidence supports a narrower claim than "absent, not
hidden."** The 22 present divisions' weights summing to **exactly** 100.0000, matching the
grand-total row's own weight of 100, proves only that **these 22 divisions form the complete
weighted universe of this particular file** — every reported percentage point is accounted for by a
division that is actually listed. It does **not**, by itself, prove that the economic activity
belonging to TSIC 18 or 33 was never folded into a neighboring division's figures: a 100.0000 sum is
exactly what would also be observed if, say, a small amount of printing-related output were counted
inside TSIC 17's (Paper) reported value under a boundary convention not stated anywhere in the file.
No methodology document was found in any of the three OIE editions' archives (§7.1) to confirm or
rule this out. **The interpretation "TSIC 18 and 33 are out of scope by survey design" remains
explicitly conditional**, pending OIE's own methodology documentation — it is the more parsimonious
reading, not a proven one, and must not be treated as settled in any downstream document.

**Consequence for the taxonomy**: per the explicit instruction not to change the taxonomy silently,
**no change is made**. The finding is recorded as a decision point: IND-03 and IND-12 can be
constructed today only from their remaining divisions (16+17, and 31+32 respectively), which means
either (a) documenting these two industries' MPI/CapU-derived values as a **partial proxy** for the
full taxonomy definition, explicitly labeled as such, or (b) formally narrowing IND-03/IND-12's
*scope* for this data source only (not renaming the project-wide taxonomy). This decision is left
open — see §12 (Unresolved) in `docs/target_definition.md`.

---

## 5. Configuration semantics: source-access vs. target-approval

`configs/targets.yaml` previously used one ambiguous `enabled: true/unresolved` flag. This revision
(`schema_version: 4`) replaces it with two explicit, independent fields:

```yaml
source_verified: true    # can we reliably read this source's data?
target_approved: false   # is this component approved for the Stress Index?
```

Current state for all four components:

| Component | `source_verified` | `target_approved` |
|---|---|---|
| MPI contraction | **true** | **false** |
| Capacity Utilization decline | **true** | **false** |
| Export contraction | false | false |
| Input-cost pressure | false | false |

This is the smallest change that fixes the ambiguity: no field was renamed out from under existing
references (nothing in `src/` reads this file yet, since `targets/stress_index.py` is still a stub),
and the eligibility-criteria block, component formulas, and weighting policy are all untouched.

---

## 6. Vintage/revision risk — an honest limitation, not eliminated by lag-handling alone

**What was checked**: whether the downloaded files are the current latest-vintage release, an
archived point-in-time release, or a revised historical series.

**Finding**: the files in `data/raw/OIE_MPI/` and `data/raw/OIE_CAPU/` are **current latest-vintage
files** — a single download of "the MPI series as OIE publishes it today," covering 2021–2026. OIE's
website was searched for an archive of **monthly point-in-time vintages** (e.g., "the March 2024
MPI release, as it appeared in April 2024, before any later revision") — none was found. The older
editions found (§7) are archived by **base-year regime**, not by **release date** — they are still
each a single current-as-of-their-own-publication snapshot of a multi-year span, not a vintage
history of successive monthly releases.

**Consequence, stated plainly**: this project cannot currently claim a true point-in-time vintage
backtest. If OIE ever revises a previously-published monthly figure (common practice at many
statistical agencies, unconfirmed either way for OIE specifically), a model trained on today's
downloaded file would be trained on **revised** historical values for lagged/autoregressive
features, not on what would have actually been knowable in real time at each historical month. This
does not make `available_as_of`/publication-lag handling (`docs/architecture/data_architecture.md`
§3, §7) pointless — it still correctly prevents *future* information from entering a *feature* row
— but it does not by itself eliminate **revision leakage** in historical backtesting, which is a
distinct risk. Going forward, this project must describe its evaluation using the honest phrase
**"latest-vintage historical evaluation,"** not "real-time backtest" or "point-in-time backtest,"
until an actual vintage archive is found or built (e.g., by this project's own pipeline
snapshotting each month's release going forward, which only accrues real vintages from here on,
not retroactively).

---

## 7. History-extension feasibility (corrected in Revision 3 — previously contained an arithmetic error)

**What Revision 2 got wrong**: it stated the current↔2016-edition TSIC division intersection as both
"18" and "19" in different places, neither computed in code, and it only inspected the older
edition's *MPI* file, leaving Capacity Utilization and the 2011-based edition entirely unaudited.
`scripts/audit_history_extension.py` fixes all three: both older editions were downloaded for real
(manifests below), MPI and CapU were audited separately for every edition, and every comparison uses
real Python `set` operations (`tests/test_audit_history_extension.py` pins the corrected numbers as
a regression test).

### 7.1 Editions inspected — real, persisted, manifested

| Edition | Manifest | Classification label | Date range (parsed) | Months | TSIC/ISIC divisions found |
|---|---|---|---|---|---|
| Current | `data/raw/_manifests/OIE_MPI_manifest.jsonl`, `OIE_CAPU_manifest.jsonl` | **TSIC** | 2021-01-01 – 2026-06-01 | 66 | 22 (`10,11,12,13,14,15,16,17,19–32`) |
| 2016-based (`index2559_2566.zip`) | `data/raw/_manifests/OIE_MPI_HIST_2559_2016_manifest.jsonl` | **TSIC** | **2016-01-01 – 2023-12-01** (parsed and verified: chronological, no gaps, no duplicate months, no duplicate division labels) | **96** | **21** (`10,11,12,13,14,15,17,19–32`, i.e. missing 16, 18, 33) |
| 2011-based (`index2554_2561.zip`) | `data/raw/_manifests/OIE_MPI_HIST_2554_2011_manifest.jsonl` | **ISIC** ⚠ | **2011-01-01 – 2018-12-01** (parsed and verified, same integrity checks) | **96** | **21** (identical set to the 2016 edition — `10,11,12,13,14,15,17,19–32`) |

Both older editions' manifests record the official URL, retrieval timestamp, HTTP status (200 for
both), file name, file size, SHA-256, edition/base-year label, and the full archive file listing —
not a temporary file deleted before the result could be reproduced. SHA-256 was independently
re-verified against the files on disk (matched exactly) as part of this revision's verification pass.

**New finding, not in Revision 2**: the 2011-based edition labels every division row **"ISIC :"**,
not "TSIC :" — the two later editions both use "TSIC :". This is recorded as a fact
(`classification_label` field in the audit output), **not normalized away**. No methodology document
was found in any of the three archives' file listings (each contains only the index workbooks
themselves — `Prodidx1/2.xlsx`, `capidx.xlsx`, `Shipidx.xlsx`, `Invidx.xlsx`, `Invratio.xlsx`,
`labidx.xlsx`/`labaprod(2).xlsx` — no PDF, DOC, or other documentation file). Whether "ISIC" here
denotes the same division boundaries as "TSIC 2009" is therefore **an open question, treated as
unconfirmed**, not assumed true because the division *numbers* happen to intersect cleanly (§7.2).

### 7.2 Corrected intersection counts — computed, not typed

| Comparison | Component | Intersection count | Only in first | Only in second |
|---|---|---|---|---|
| Current vs. 2016-based | MPI | **21** | `[16]` | `[]` |
| Current vs. 2011-based | MPI | **21** | `[16]` | `[]` |
| 2016-based vs. 2011-based | MPI | **21** | `[]` | `[]` (identical sets) |
| Current vs. 2016-based | CapU | **21** | `[16]` | `[]` |
| Current vs. 2011-based | CapU | **21** | `[16]` | `[]` |
| 2016-based vs. 2011-based | CapU | **21** | `[]` | `[]` (identical sets) |

**The correct number is 21, not 18 and not 19.** The two older editions have *identical* division
coverage to each other (both missing exactly 16, 18, 33); the current edition differs from both by
exactly one division (16, present only in the current edition). This holds identically for MPI and
CapU — the two components' division availability tracks together within each edition, though this
was verified independently for each, not assumed from the MPI result.

### 7.3 Bridge feasibility by industry (computed per component, not asserted at the division level alone)

`build_industry_bridge_table()` checks, per industry, whether the *set* of present divisions is
identical across all three editions — not merely whether each edition individually clears a coverage
bar. Result, identical for MPI and CapU:

| Result | Industries | Reason |
|---|---|---|
| **Bridgeable** (composition identical across all 3 editions) | **11 of 12**: IND-01, IND-02, IND-04, IND-05, IND-06, IND-07, IND-08, IND-09, IND-10, IND-11, **IND-12** | Present-division set is the same in every edition |
| **NOT bridgeable** | **IND-03** | Composition changes across editions — see §7.4 |

**IND-12 is bridgeable, and the reason is instructive by contrast with IND-03**: IND-12 requires
divisions {31, 32, 33}. Division 33 is missing from *every* edition, current included — so the
present set is {31, 32} consistently across all three editions. A consistently-missing division does
not break a bridge; a division that is present in one edition and absent in another does.

### 7.4 IND-03 — confirmed, in code, not a clean bridge

IND-03 requires {16, 17, 18}. Division 18 is absent from every edition (consistent, like IND-12's
33). Division 16, however, is present in the **current** edition but **absent from both older
editions**:

| Edition | Present divisions for IND-03 |
|---|---|
| Current | `{16, 17}` |
| 2016-based | `{17}` |
| 2011-based | `{17}` |

**This is not classified as a clean bridge.** A series built from TSIC 17 alone before ~2021 and
from TSIC 16+17 from 2021 onward changes what it measures at the bridge date — exactly the concern
raised in this task. `build_industry_bridge_table()` returns `bridge_possible: false` for IND-03
with the reason `"Present-division set differs across editions..."`, and
`tests/test_audit_history_extension.py::test_industry_bridge_flags_ind03_style_composition_change`
pins this behavior against a synthetic reproduction of exactly this scenario.

### 7.5 Bridge feasibility by component

Evaluated independently, as required — a long MPI span does not imply an equally long CapU span:

| Component | Bridgeable industries | Max span if current+2016-based bridged (pending §7.6) | Max span if all 3 editions bridged (pending §7.6 AND the ISIC/TSIC question) |
|---|---|---|---|
| MPI | 11/12 | 2016-01 to 2026-06 = **126 months** | 2011-01 to 2026-06 = **186 months** |
| CapU | 11/12 | 2016-01 to 2026-06 = **126 months** | 2011-01 to 2026-06 = **186 months** |

Both components reach the same bridgeable-industry count and the same candidate spans — this was
checked, not assumed from MPI alone, per the explicit instruction.

### 7.6 What is still not done — no splicing performed

Per the explicit restriction, **no level-linking or growth-rate-linking was performed**. What remains
before any of the spans in §7.5 can be used:

1. **The overlap-window validation** (36 months, 2021–2023, between current and the 2016-based
   edition; and 2016–2018 between the two older editions) — has not been run. This is what would
   determine whether level-linking or growth-rate-linking produces a more internally consistent
   joined series.
2. **The ISIC-vs-TSIC classification question for the 2011-based edition** (§7.1) is unresolved. The
   186-month span requires trusting that "ISIC : NN" in the 2011 file means the same thing as
   "TSIC : NN" in the later files — plausible (Thai TSIC is built on ISIC, and the division numbers
   intersect perfectly), but not confirmed by any methodology document found in this session. The
   126-month span (current + 2016-based only) does **not** depend on this question, since both of
   those editions use "TSIC" labeling.
3. **IND-03's taxonomy decision** (§7.4) is unresolved and independent of the above — even once
   linking is validated, IND-03 specifically cannot use the full 11-industry bridge without either
   redefining its scope (accepting TSIC 17-only across the bridged history) or accepting a shorter,
   current-edition-only span (66 months) for that one industry specifically.

### 7.7 Maximum defensible common period — stated per scope, not as one number for all 12

- **11 of 12 industries** (all except IND-03), for **both MPI and CapU**: up to **126 months**
  (2016-01 to 2026-06) using only TSIC-labeled editions (no ISIC question to resolve), **pending**
  the overlap-window linking validation in §7.6 point 1. This **exceeds the 120-month preferred
  target**.
- **IND-03 specifically**: capped at the **current edition's own 66 months** unless a taxonomy
  decision changes its definition — it cannot join the 126-month bridge without changing what it
  measures.
- **186 months (2011–2026, 11/12 industries)** is a plausible upper bound, additionally gated on the
  unresolved ISIC/TSIC equivalence question.
- **60 months = minimum prototype eligibility** — already met by the current edition alone (66
  months) for every industry, including IND-03, independent of any bridging decision.
- **If bridging is not ultimately pursued or validated**: all 12 industries still have the current
  edition's 66 months, which clears the 60-month prototype minimum but not the 120-month preferred
  target — in that case, per the confirmed policy, this project should favor simpler models and
  narrower claims (§7 of Revision 2, unchanged reasoning: persistence/historical-mean/regularized-
  linear baselines, wider confidence intervals, caution around rare-event recall claims).

---

## 8. Redundancy plan (MPI vs. Capacity Utilization) — designed, not executed

Per the explicit instruction, **equal-weight MPI + CapU as a final K=2 target is not yet approved.**
The following leakage-safe test is documented as the gate that must run before it is:

1. **Correlation of adverse MPI changes and CapU declines**, computed on the sign-aligned,
   industry-standardized components (`z_MPI`, `z_CapU` from `docs/target_definition.md` §4) —
   **overall** (pooled across industries and months) and **by industry** separately, since the two
   are mechanically related (CapU ≈ output ÷ capacity, so a CapU decline at constant capacity
   mechanically tracks an MPI decline) but not necessarily to the same degree in every industry.
2. **Rolling correlation stability** — compute the correlation within rolling windows over time, not
   only as one pooled number, to check whether the relationship is stable or regime-dependent (e.g.
   tighter during a demand-side shock, looser during a capacity-expansion period).
3. **Whether both components respond to the same production mechanism** — a qualitative read
   alongside the quantitative correlation: if a known historical episode (e.g. the automotive
   slowdown referenced in the OIE press release read during the original feasibility study) moved
   both MPI and CapU together for the same industry, that is consistent with shared mechanism; if
   an episode moved one without the other, that is evidence of distinct information content.
4. **Whether the second component adds distinct known-shock information** — for at least one
   independently-documented real event, check whether CapU alone, MPI alone, or the equal-weight
   blend of both best matches the known severity/timing, using the same case-study method as Gate B.
5. **Leave-one-component-out sensitivity** — compare the equal-weight `K=2` score's behavior against
   an MPI-only (`K=1`, hypothetically, for testing purposes only) and a CapU-only reading, on the
   **training/validation split only**.

**The final test period is explicitly reserved and not touched by this analysis** — this redundancy
test, like the sensitivity analysis in `docs/target_definition.md` §5.5, runs on validation data
only, consistent with Gate C/D discipline. None of this has been executed yet; it is blocked on the
same aggregation-rule implementation as §4.

---

## 9. Audit-code quality changes

- **Constant duplication is no longer silent.** `check_eligibility_constants_match_config()` loads
  `configs/targets.yaml` at the start of every run and raises `EligibilityConstantMismatchError` if
  the script's hard-coded `MIN_TIME_COVERAGE_MONTHS`, `MIN_INDUSTRY_COVERAGE`, `MAX_MISSINGNESS_PCT`,
  or `PREFERRED_HISTORY_MONTHS` ever drift from the config file's `eligibility_criteria` block. This
  does not eliminate the duplication (the script must still run standalone without importing
  production config-loading internals that do not exist yet), but it makes drift a loud failure
  instead of a silent inconsistency.
- **No hard-coded retrieval date.** `resolve_retrieval_path(source_id)` reads the actual file path
  out of `data/raw/_manifests/<source_id>_manifest.jsonl` (falling back to the newest dated
  subdirectory only if no manifest exists) instead of a literal `"2026-08-26"` string — a future
  re-retrieval on a different date requires no script edit.
- **This script remains a one-off audit tool, not a pipeline component.** It is not imported by
  `src/thai_supply_chain_ews/`, and `data/ingest.py` remains an unimplemented stub — hardening this
  script is not a substitute for building the real ingestion path.

---

## 10. Task A2 — empirical overlap-window bridge validation (new in Revision 4)

> **SUPERSEDED by Task A2.1 (`oie_overlap_bridge_v2`) — see
> `docs/oie_overlap_validation_v2.md`.** The counts below were produced by a
> methodology with four confirmed correctness defects (see the Revision 5 note at
> the top of this report). Corrected results: **MPI approved 2/11** (IND-04,
> IND-09), **CapU approved 8/11**, **both components approved: IND-04 only**.
> 8 of 22 industry-component pairs changed status. The section is retained
> unedited below as the historical v1 record, not as a current claim.

Full detail, per-industry table, and the documented-before-computed approval criteria live in
`docs/oie_overlap_validation.md`; machine-readable evidence in
`docs/oie_overlap_validation_output.json`. Summary:

- **Scope**: current (2021-based, TSIC) vs. 2016-based (TSIC) editions only, 2021-01–2023-12 overlap
  (36 months), MPI and CapU, the 11 industries whose division composition is identical across these
  two editions (IND-03 excluded — §7.4, unchanged). The 2011-based ISIC edition remains untouched and
  unapproved.
- **Passing MPI** (rebased-level r ≥ 0.90, MoM/YoY correlation and bias within documented bounds, no
  unexplained discontinuity, stable across all 3 overlap years): **IND-01, IND-02, IND-04, IND-09,
  IND-10 (5 of 11)**.
- **Passing CapU**: **IND-01, IND-02, IND-04, IND-05, IND-06, IND-08, IND-09, IND-10, IND-11 (9 of
  11)**.
- **Passing both MPI and CapU** — the only industries that may claim the full 126-month bridge on
  both target components: **IND-01, IND-02, IND-04, IND-09, IND-10 (5 of 11)**.
- **Rejected outright** (real, evidence-backed discontinuities, not composition artifacts): IND-05
  MPI (2023-01, 2023-08), IND-11 MPI (2023-11), IND-12 CapU (below the levels bar and a 2023
  discontinuity).
- **Conditional** (softer misses, mostly YoY bias above the 3.0pp documented threshold): IND-06/07/08
  MPI, IND-07 CapU, IND-12 MPI.
- **Linking method**: level-linking via median ratio over the overlap. Growth-rate-linking produces
  an identical MoM/YoY series to level-linking by construction (a constant scale factor cancels out
  of any percentage change) — the two are not competing options, only different uses of the same
  evidence (§2 of `docs/oie_overlap_validation.md`).
- **Recommended switch month**: 2021-01 — the first month with native current-edition data.
- **§7.7's 126-month claim is now qualified, not withdrawn**: it is empirically supported for the 5
  both-approved industries; for the other 6, at most one component (or neither) may claim it, per the
  breakdown above. **This correction is the point of this revision** — do not read §7.7 in isolation
  from this section.
- **Still open**: whether "Conditional" status is acceptable for production ingestion is a policy
  decision this task does not make; the 3 Rejected pairs need root-cause investigation before any
  further attempt; IND-03's 3-way policy choice (§7.4) remains unmade; the 2011 ISIC edition remains
  fully out of scope.

---

## Required report items

1. **Source-access status**: MPI — verified. CapU — verified. Export — endpoint verified, depth
   unconfirmed (Conditional). PPI — data viewed live, depth/lag/auth unconfirmed (Conditional).
2. **Target-approval status**: **All four remain unapproved.** MPI and CapU are Conditional (source
   verified, four specific blockers listed in the summary box at the top of this report). Export and
   PPI are Conditional at the source-access level already.
3. **Full vs. partial industry coverage**: 10/12 full, 2/12 partial (IND-03 missing TSIC 18, IND-12
   missing TSIC 33), 12/12 any-coverage — for both MPI and CapU identically (§1).
4. **Explicit parsed date coverage**: 2021-01-01 to 2026-06-01, 66 unique chronological months, zero
   gaps, zero duplicates, for both MPI and CapU (§3).
5. **TSIC hierarchy and aggregation findings**: division-level row confirmed as the correct
   aggregation input; no duplicate division labels found (checked, guarded going forward); official
   value-added weights found and extracted, summing to exactly 100.0000; TSIC 18/33 appear
   structurally outside the survey's scope, not hidden elsewhere (§2, §4).
6. **Vintage/revision limitation**: only latest-vintage files were obtained; no point-in-time vintage
   archive was found; this project must describe its evaluation as **latest-vintage historical
   evaluation**, not a true real-time backtest, until vintages are found or accrued going forward
   (§6).
7. **History-extension feasibility (corrected)**: both older editions (2016-based, 96 months; and
   2011-based, 96 months, labeled "ISIC" not "TSIC") were downloaded, persisted with full manifests,
   and inspected for MPI **and** CapU separately. The corrected current↔2016-edition intersection is
   **21 divisions** (computed in code — not 18, not 19). **11 of 12 industries** (all except IND-03)
   have identical division composition across all three editions for both components, supporting up
   to a **126-month span** (2016–2026, TSIC-labeled editions only) or a **186-month span** (2011–2026,
   pending the unresolved ISIC/TSIC equivalence question). **IND-03 cannot bridge** without changing
   its meaning (TSIC {16,17} currently vs. {17} only historically) — confirmed in code, not asserted.
   No splicing was performed (§7).
8. **Remaining Task A1 scope**: Export and PPI still need the monthly-depth/mapping/lag/auth
   questions resolved (unchanged from Revision 1); NESDC I-O and BOT API remain entirely open,
   outside this revision's scope.
9. **Whether B1 parsing may begin**: **Yes, narrowly** — the workbook hierarchy, weight column, and
   date structure are now understood well enough to write a real `data/ingest.py` / interim parser
   for MPI and CapU specifically. This is parsing/ingestion mechanics only.
10. **Whether final Stress Index construction may begin**: **No.** `compute_raw_stress_index`
    remains blocked until the weighted-aggregation rule is implemented and validated, the
    IND-03/IND-12 scope decision is made, the MPI-vs-CapU redundancy test (§8) has run, and
    `target_approved` is flipped to `true` for at least two components in `configs/targets.yaml`.
11. **Task A2 empirical overlap-window bridge validation (Revision 4)**: 5/11 industries pass for
    MPI, 9/11 for CapU, 5/11 for both (the only ones that may claim the full 126-month bridge on both
    target components); level-linking via median ratio is the best-supported linking method, and is
    mathematically equivalent to growth-rate-linking for MoM/YoY series; recommended switch month is
    2021-01; IND-03 remains excluded and unresolved (three future policy options, none selected);
    full detail in §10 and `docs/oie_overlap_validation.md`. **No 126-month bridge is claimed for any
    industry-component pair based on matching division sets alone — every claim above is backed by
    the correlation/bias/stability/discontinuity evidence in that document.**

---

## Files created or modified (Revision 3, this update)

- `scripts/audit_history_extension.py` (new) — downloads and persists both older OIE editions with
  full manifests, audits MPI and CapU separately per edition, computes every division-set comparison
  with real `set` operations, builds the per-industry bridge-feasibility table.
- `tests/test_audit_history_extension.py` (new) — 9 tests, including a regression test pinning the
  corrected 21-division intersection and dedicated tests for the IND-03 (composition-changes) and
  IND-12 (consistently-partial-but-bridgeable) cases.
- `data/raw/OIE_MPI_HIST_2559_2566/2026-08-26/index2559_2566.zip` and
  `data/raw/OIE_MPI_HIST_2554_2561/2026-08-26/index2554_2561.zip` (new, real files, persisted —
  **not** a temporary location deleted before reproducibility, correcting Revision 2's approach —
  git-ignored per the existing `data/raw/*` policy).
- `data/raw/_manifests/OIE_MPI_HIST_2559_2016_manifest.jsonl`,
  `OIE_MPI_HIST_2554_2011_manifest.jsonl` (new) — full retrieval manifests (URL, timestamp, HTTP
  status, filename, size, SHA-256 — independently re-verified against the files on disk — edition
  label, archive contents).
- `docs/task_a1_history_extension_output.json`, `docs/task_a1_history_extension_output.txt` (new) —
  the machine-readable and human-readable evidence §7 is built from; re-run twice, byte-identical.
- `docs/task_a1_report.md` (this file) — §7 fully rewritten with corrected, code-verified numbers;
  the weight-sum evidentiary claim in §4.2 softened to what the evidence actually supports.

Prior revision's changes (`scripts/audit_target_sources.py` hardening, `configs/targets.yaml`
`source_verified`/`target_approved` split, etc.) are unchanged by this update — see the file's own
git history / prior conversation turn for those.

## Files created or modified (Revision 4, Task A2)

- `scripts/validate_oie_overlap.py` (new) — extracts real division-level monthly values (not just
  presence), builds official-weight industry aggregates (plus a fixed-weight rebasing-vs-weight-
  revision diagnostic), builds 4 representations (raw/rebased/MoM%/YoY%), computes the full metric
  suite, evaluates level-linking, and applies the documented-before-computed approval criteria.
- `tests/test_validate_oie_overlap.py` (new) — 22 tests covering all 15 required cases (overlap-month
  count, composition consistency, IND-03 exclusion, ISIC-edition exclusion, no duplicate
  industry-month keys, weighted aggregation, renormalization, MoM/YoY calculation, level-linking,
  no invalid cross-edition lag, metric calculation with missing pairs, criteria-driven approval,
  machine-readable row count, determinism) plus a regression test for the discontinuity-floor fix
  described below.
- `scripts/audit_history_extension.py` (modified) — `main()` now patches the current-vs-2016-based
  bridge tables' `overlap_validated`/`bridge_approved` fields with the real Task A2 evidence when
  `docs/oie_overlap_validation_output.json` is present; ISIC-involving pairs are untouched and remain
  `False`, never inferred from composition alone.
- `docs/oie_overlap_validation.md`, `docs/oie_overlap_validation_output.json` (new) — the human- and
  machine-readable Task A2 evidence; §10 above is a summary of it.
- `docs/oie_overlap_plots/example_IND-01_rebased.png`, `summary_rebased_pearson.png` (new) —
  lightweight diagnostic plots, git-safe sizes (<100KB combined).
- `docs/task_a1_history_extension_output.json`, `.txt` (regenerated) — now include the patched
  overlap-evidence fields for the current-vs-2016-based pairs.
- **Discontinuity-detector edge case found and fixed**: the first run of `validate_oie_overlap.py`
  wrongly rejected IND-04 CapU (its 2021–2022 values are identical between editions to floating-point
  precision, so a real but tiny 0.59-point 2023 divergence registered as an "infinite-multiplier"
  discontinuity). Fixed by adding an absolute floor (1.0 index point / 1.0pp) alongside the relative
  multiplier — a robustness fix to the detection mechanism, made before computing final approval
  labels, not a relaxation of the approval bar itself (see `docs/oie_overlap_validation.md` §1).
