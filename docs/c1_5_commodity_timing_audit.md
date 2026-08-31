# Task C1.5 — Pink Sheet Publication-Timing and Revision Audit

> **REVISED TWICE.**
>
> **C1.5-R1** withdrew the first run's claim that 62 of 65 required issues had
> no archived evidence. That was incomplete discovery, not evidence of absence.
>
> **C1.5-R2** withdraws R1's claim that **no distinct February 2025 issue
> exists**. That claim was also wrong, for a different reason: R1 downloaded the
> wrong file and then reported the consequence as a fact about the archive.
> February 2025 exists, is distinct, and is now validated. §1.3 gives the root
> cause; §8 lists every superseded conclusion.
>
> **C1.5-R3** corrects a third error, of a different kind. R1/R2 read the table
> token `a/` as an **estimate marker**. The Pink Sheet's own footnote block
> defines it as *"Included in the energy index"*. Index membership was mistaken
> for data provenance, which mislabelled every Brent observation and gave the
> LNG estimate statistics a name the evidence never supported. §10 has the
> correction (§9); the numerical revision results are unaffected.
>
> The pattern common to the first two errors is worth naming: **a retrieval
> failure was converted into a claim about the world.** §1.3 describes the check
> that now makes that conversion impossible. The third error is its cousin: **a
> symbol was read as evidence without checking what the document said it meant.**

Evidence for when each World Bank Pink Sheet reference month became publicly
available, and whether the latest historical workbook has revised what was first
published.

Numbers are read from
[`c1_5_commodity_timing_audit.json`](c1_5_commodity_timing_audit.json).
Contract: [`configs/commodity_timing.yaml`](../configs/commodity_timing.yaml).
Decision: [`c1_5_commodity_timing_decision.md`](c1_5_commodity_timing_decision.md).

```bash
python scripts/audit_c1_5_commodity_timing.py
```

No feature was created, nothing was joined to MPI, no target association was
computed, and B4's locked test was not touched.

---

## 1. Discovery

### 1.1 Why the first run was wrong

The first run searched only two pages — the commodity-markets landing page and
the report-archive page — and matched only the hyphenated filename form
`CMO-Pink-Sheet-<Month>-<Year>.pdf`. It found 3 issues and reported the other 62
as non-existent.

Two distinct mistakes:

1. **The wrong entry points.** Older issues are not linked from the landing page.
   They are exposed on individual **document-detail pages** and, in bulk, through
   the **RELATED** link list of a legacy Pink Sheet document page. Neither was
   consulted.
2. **The wrong filename pattern.** A detail page's **MAIN DOCUMENT** href uses a
   *squashed* filename — `CMOPinkSheetFebruary2021.pdf`, no hyphens — even
   though the anchor text shows the canonical hyphenated name. The old regex
   could not match it, so February 2021 was invisible even on the page that
   serves it.

Absence of evidence was reported as evidence of absence. It was not.

### 1.2 Entry points now used

| Seed page | Issues contributed |
|---|---|
| `.../804991612306143358-0050022021/CMO-Pink-Sheet-February-2021` (detail page) | 1 (MAIN DOCUMENT) |
| `.../5d903e848db1d1b83e0ec8f744e55570-0350012021/CMO-Pink-Sheet-March-2021` (legacy RELATED list) | 47 |
| `.../18675f1d1639c7a34d463f59263ba0a2-0050012025/world-bank-commodities-price-data-the-pink-sheet` | 12 |
| `.../74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet` | 5 |

Plus the original landing and report-archive pages, retained.

| Discovery method | Count |
|---|---|
| `official_related_href` | **63** |
| `official_detail_main_document` | **1** |
| `official_family_original_href` | **1** |
| `official_public_documents_search` | 0 (not needed — nothing was missing) |
| `pattern_probe_within_discovered_folder` | **0** |

No document hash is constructed or guessed. The pattern probe the first run
relied on is no longer used at all, and a probe can never outrank an official
link.

### 1.3 Why the February 2025 anchor produced the January file

R1 found the right *page* and still filed the wrong *bytes*. The full chain, as
recorded per candidate in `expected_issue_inventory[*].candidate_attempts`:

| Link in the chain | What R1 did |
|---|---|
| Discovery page | `.../18675f1d…-0050012025/world-bank-commodities-price-data-the-pink-sheet` — correct |
| Anchor text | `CMO-Pink-Sheet-February-2025` — correct |
| Hrefs present on that page | **both** `/original/CMO-Pink-Sheet-February-2025.pdf` **and** `/related/CMO-Pink-Sheet-February-2025.pdf` |
| Href selected | the **`/original/`** one |
| Requested URL | `.../18675f1d…-0050012025/original/CMO-Pink-Sheet-February-2025.pdf` |
| Redirects | none; HTTP 200 |
| Bytes served | January 2025's — 257,605 bytes, `b53a6b98…` |
| Local filename | `CMO-Pink-Sheet-February-2025.pdf` (basename only) |
| Manifest id / cache key | that same basename |
| Internal PDF date | 2025-01-03 — **never read** |
| Displayed header | Oct/Nov/Dec 2024 — **never compared** |
| Verdict recorded | `duplicate_content`, "no distinct February issue exists" |

**Root cause, in three parts.**

1. **`/original/` is filename-agnostic.** Under
   `/en/doc/<document-hash>/original/`, the World Bank serves that document
   family's *main* document no matter what filename follows. Proved directly:
   requesting `original/CMO-Pink-Sheet-NONSENSE-9999.pdf` under the same hash
   returns exactly the same bytes as `original/CMO-Pink-Sheet-June-2025.pdf`.
   On that path the filename is decorative; only the hash selects content. The
   `18675f1d…` family's main document was January's, so the February *name*
   fetched January's *bytes*.
2. **The href regex treated `/related/` and `/original/` as equivalent** and
   gave them the same method rank, so the first-seen match won. The correct
   `/related/` URL was on the same page and was discarded with no record.
3. **Nothing validated the file against its own contents.** The PDF states its
   creation date and its newest column. Either one would have rejected the
   file immediately. Neither was checked, so a fetch defect propagated
   unopposed into a coverage claim, a lag decision, and a config field.

The third part is the one that mattered. Parts 1 and 2 are ordinary bugs;
part 3 is what let a bug become a published statement about the World Bank's
archive.

**What now prevents it.**

- **Every** candidate href for an issue month is retained and ranked, so a
  `/related/` URL can no longer be shadowed by an equal-ranked `/original/` one.
- `official_family_original_href` is ranked **below** `/related/` and is
  explicitly documented as filename-agnostic — it may never be used to assert
  which issue a file is.
- Each downloaded candidate must pass `validate_issue_identity`: its internal
  `/CreationDate` must fall inside the expected issue month **and** its newest
  displayed monthly column must equal the expected issue month minus one. A
  failing candidate is rejected and the next is tried.
- Raw files and cache keys are keyed on `{document_hash}__{filename}`, not the
  basename, so two families' same-named PDFs cannot overwrite each other.
- A SHA-256 shared by two *different* validated issue months now **raises
  `IssueIdentityError`**. Both cannot be genuine, so the pipeline stops rather
  than silently choosing a `duplicate_content` story.

Under these rules February 2025 resolves via `official_related_href` to
`94f053ef…`, created 2025-02-04, newest column 2025-01 — and the `/original/`
variant survives in the record as a lower-ranked candidate rather than
vanishing.

## 2. Archive coverage — 65 of 65

Required issue range **February 2021 … June 2026** (65 issues), first exposing
reference months **2021-01 … 2026-05** (65 months).

| | Count |
|---|---|
| Expected issue months | **65** |
| Resolved to an official URL | **65** |
| Passed issue-identity validation | **65** |
| **Distinct issues obtained** | **65** |
| Distinct SHA-256 checksums | **65** |
| Duplicate content | **0** |
| Genuinely unreachable | **0** |

Derived, not assumed: the counts above are read back from
`expected_issue_inventory` in the audit JSON. 65 documents produced 65 distinct
checksums, so no two issue months share bytes.

By discovery method: `official_related_href` **63**,
`official_detail_main_document` **1**, `official_family_original_href` **1**.

Each was parsed, its internal creation date read, its newest displayed column
checked, and its checksum recorded in
`data/raw/_manifests/WB_PINKSHEET_VINTAGES_manifest.jsonl` (PDFs git-ignored,
~16 MB).

### February 2025 — R1's anomaly was a fetch defect, not an archive fact

R1 recorded February 2025 as `duplicate_content`, byte-identical to January.
**That was wrong.** The two issues are different documents:

| | January 2025 | February 2025 |
|---|---|---|
| URL path | `.../5d903e84…-0350012021/related/CMO-Pink-Sheet-January-2025.pdf` | `.../18675f1d…-0050012025/related/CMO-Pink-Sheet-February-2025.pdf` |
| Size | 257,605 bytes | 256,996 bytes |
| SHA-256 | `b53a6b98c921bdb8…` | `94f053ef4134d527…` |
| Internal `/CreationDate` | 2025-01-03 | 2025-02-04 |
| Newest displayed column | 2024-12 | **2025-01** |

Both figures match the independently observed values supplied with this task,
byte count and hash.

**Consequence of the correction:** reference month 2025-01 *does* have a t+1
issue. It is measured, not bounded. The upper-bound category is now empty, and
the lag that R1 derived from it does not survive.

## 3. Publication timing

Issue dates come from each PDF's own `/CreationDate`, never from the download
timestamp.

| Statistic | Value |
|---|---|
| Reference months with a **measured** first release | **65 / 65** |
| Upper-bound-only | **0** |
| No evidence at all | **0** |
| Publication delay, days after month end | min **1**, median **2**, max **25** |
| Measured months available in t+1 | **65 of 65** |

Delay distribution, in days after month end:

| Days | 1 | 2 | 3 | 4 | 5 | 6 | 9 | 25 |
|---|---|---|---|---|---|---|---|---|
| Months | 5 | 30 | 10 | 12 | 2 | 4 | 1 | 1 |

**Month *t* is first published in month *t+1***, usually within a week of month
end. All 65 months follow this pattern with no exception; the 25-day maximum is
a single month and still lands inside t+1.

### The lag that follows

| Field | Value |
|---|---|
| `typical_publication_lag_months` | **1** |
| **`minimum_publication_lag_months`** | **1** |
| `publication_timing_status` | **`verified`** |

Every month is measured and every one was available at t+1, so the smallest lag
sufficient for **all 65** is **1**. Nothing rests on a bound, which is why the
status is `verified` rather than `partially_verified`.

R1 published lag **2**. That number came entirely from January 2025 appearing to
have no t+1 issue — an artefact of downloading the wrong February file. It is
**not retained**: a lag must follow from the evidence, and correcting the
evidence changes the lag. Keeping 2 "to be safe" would have meant carrying a
defect forward as a policy.

What has *not* changed: `recommended_operational_lag_months` is **2** — the
measured requirement of 1 plus one month of margin for estimate settling. That
margin is a policy choice and is labelled as one. It is not a measured minimum,
and C2 must not cite it as one.

### Same-reference-month use

`same_reference_month_available_at_calendar_origin: false`,
`lag_zero_prohibited: true`.

Every verified month was first published **after its own month end**, so the
completed value for month *t* does not exist at any forecast origin inside month
*t*. This is structural, not a gap in evidence.

## 4. Forecast-origin contract

Unchanged from the first run and still correct. Read from configuration rather
than assumed: B4 defines `feature_available_month <= forecast_origin_month` with
`basis: month_based_latest_vintage` and
`is_real_time_release_date_rule: false`; B1 emits `release_date` and
`available_as_of` as NULL. The project operates a **calendar-boundary,
month-based** contract. An operational-release contract still cannot be
evaluated — verified historical MPI release dates do not exist here.

## 5. First-release reconstruction

Each issue newly completes exactly one reference month; the other two monthly
columns are revisions of already-published months. First-release values are
taken from the earliest verified issue for each month, never from a later one.

**Coverage: all 7 series across all 65 required reference months**, and **15 of
15** B4 development origins. Displayed text, precision, footnote marker and its
documented meaning, estimate status, unit, source label, issue date, evidence
URL and checksum are preserved per observation. There is no bounded month and no gap.

### A parsing bug this exposed

Older issues print an ellipsis for months a series has not yet reported — e.g.
Coal, Australia in the 2022 issues reads `… 183.9 197.0 … … … …`. The parser
originally took "the last three numbers", which silently reached back into the
**quarterly** columns and fabricated first-release values that were never
published. That produced an apparent **+118% coal revision** in an intermediate
pass.

The parser now tokenises number-**or**-missing cells, so an unpublished cell
produces **no observation**. The +118% figure was an artifact and does not
appear in the results below.

## 6. Revision audit

First-release values versus the C1 latest-vintage workbook, with the workbook
rounded to the precision the archived PDF displayed, so display rounding is
never counted as a revision.

Scoped to the **65-month required window** (2021-01 … 2026-05), so no series can
report more comparable months than the contract contains:

| Series | Comparable | Revised | Frequency | Max % |
|---|---|---|---|---|
| **lng_japan_usd_mmbtu** | 65 | **65** | **100%** | **34.10%** |
| palm_oil_usd_mt | 65 | 20 | 30.8% | 2.32% |
| coal_australia_usd_mt | 57 | 2 | 3.5% | 5.23% |
| copper_usd_mt | 65 | 2 | 3.1% | 0.06% |
| aluminum_usd_mt | 65 | 1 | 1.5% | 0.13% |
| brent_crude_usd_bbl | 65 | **0** | 0% | — |
| rubber_rss3_usd_kg | 65 | **0** | 0% | — |

Coal's 57 is below 65 because months governed by its documented definition break
are held out of numerical revision statistics (§7), not because evidence is
missing.

**Out-of-window months, reported separately.** The February 2021 issue also
displays **2020-11** and **2020-12**. Those two months fall outside the
contracted window: 14 observations, **0** revisions beyond rounding. R1 folded
them into the per-series totals, which is why its counts read 67 — more months
than the project has under contract. They are excluded from the table above and
recorded under `revision_window_scope` in the config.

### LNG Japan — differences from the current workbook

> **Terminology corrected in C1.5-R3.** This section previously reported "65
> estimate-to-final transitions". Both halves of that phrase were wrong: the
> estimate classification came from the `a/` index token, and no Pink Sheet
> issue establishes that any value is *final*. The numbers below are unchanged;
> what they are called is not. See §9.

Across all 65 reconstructed first releases:

- **65 of 65** in-window comparable months differ from the current workbook
  beyond display rounding
- median absolute difference **4.01%**, maximum **34.10%**
- largest moves: 2026-04 `11.67 → 15.65` (+34.1%), 2026-03 `14.85 → 11.42`
  (−23.1%), 2022-03 `18.03 → 15.11` (−16.2%)

LNG differs from the later vintage in *every* month.
`lng_japan_primary_feature_eligible: false` — and that exclusion rests on this
measured record, not on estimate labelling, so C1.5-R3 does not disturb it.

**Brent and Rubber RSS3 were never revised** across all 65 in-window months (nor
in the two out-of-window months) — materially better behaved than the first
run's three-month sample could show.

## 7. Definition breaks — still separate, and not what caused the coal figure

C1's semantic findings stand: Coal, Australian switches spot → futures at
**2022-02**; Palm oil changes grade/delivery basis at **2021-01, 2024-11,
2025-02**. Neither is counted as a numerical revision.

Attribution is deliberately narrow: a break is charged only when the regime now
governing a month **began after that month was first published** — the case
where the two vintages genuinely quote different things. A looser rule
over-attributes: palm oil's +1.34% move in 2025-11 (`970 → 983`) is a routine
revision to a month first published in December 2025, not a consequence of the
February 2025 benchmark change that was already in force when that month was
published.

**On this evidence, no observation met that test.** Whether each change was
disclosed in the issue of the month it took effect remains **unresolved** — the
issues are now in hand, but confirming disclosure requires reading each issue's
footnote history, which this task did not do.

Both series remain excluded from the primary feature set. C1.5 approves neither
as a model feature.

## 8. Superseded conclusions

**From the first C1.5 run** (withdrawn by R1):

| First-run conclusion | Status |
|---|---|
| "62 of 65 required reference months have no archived evidence" | **WITHDRAWN** — 0 months lack evidence; all 65 measured |
| "Only 3 archived issues are obtainable" | **WITHDRAWN** — 65 distinct issues obtained |
| "Zero archived issues cover the B4 development window" | **WITHDRAWN** — 15 of 15 origins measured |
| "`minimum_safe_lag_months` is null" | **SUPERSEDED** — split into a verified `minimum_publication_lag_months: 1` and a still-null `revision_safe_lag_months` |
| "Point-in-time reconstruction is not available" | **WITHDRAWN** — archived first releases cover all 65 months |
| LNG revision measured on 2 months (−18.33%, −8.11%) | **SUPERSEDED** — measured on 65 months, median 4.01%, max 34.10% |
| Coal "+118% revision" (intermediate R1 pass) | **WITHDRAWN** — extraction artifact, now fixed |

**From C1.5-R1** (withdrawn by R2):

| R1 conclusion | Status |
|---|---|
| "No distinct February 2025 issue exists" | **WITHDRAWN** — it exists: `94f053ef…`, created 2025-02-04, newest column 2025-01 |
| "The February RELATED link serves a PDF byte-identical to January" | **WITHDRAWN** — R1 requested the `/original/` variant, not the RELATED one; the RELATED URL serves the correct distinct file |
| `duplicate_content_issues: [2025-02-01]` | **WITHDRAWN** — no duplicate content anywhere; 65 issues, 65 distinct checksums |
| "Reference month 2025-01 is bounded at t+2, not measured" | **WITHDRAWN** — measured; first released 2025-02-04, i.e. t+1 |
| `minimum_publication_lag_months: 2` | **SUPERSEDED** — **1**; the 2 existed only because of the wrong February file |
| `publication_timing_status: partially_verified` | **SUPERSEDED** — **`verified`**; no month rests on a bound |
| `archived_first_release_backtest_eligible: false` | **SUPERSEDED** — **`true`**; 65/65 months, 15/15 origins |
| `point_in_time_values_supported: partially` | **SUPERSEDED** — `point_in_time_supported: full` (feature side only) |
| Per-series revision counts of 67 comparable months | **SUPERSEDED** — scoped to the 65-month window; out-of-window months reported separately |
| "`timing_status: partially_verified`" | **SUPERSEDED** — **`verified`** |

### What remained valid

- Month *t* is first published in month *t+1* (now 65/65 rather than 3/3).
- Same-reference-month use is structurally impossible; lag zero prohibited.
- The forecast contract is calendar-boundary, month-based, not operational-release.
- Latest-vintage data is not point-in-time merely because it is lagged.
- LNG is heavily revised and ineligible for the primary feature set.
- Coal and Palm oil definition breaks are semantic, not numerical revisions, and
  both series stay excluded.
- Rounding tolerance, estimate-marker preservation, checksum discipline, the
  refusal to interpolate missing months, and all leakage/locked-test protections.

## 9. C1.5-R3 — footnote and estimate semantics

### What was wrong

C1.5 set a boolean field named `estimate_marker` whenever a series row carried
the token `a/`. The archived issues define their own tokens, in a footnote block
present in every issue examined:

> `a/ Included in the energy index; b/ Included in the non-energy index;`
> `c/ Included in the precious metals index; d/ Metals and Minerals excluding iron ore.`

| Token | Documented meaning |
|---|---|
| `a/` | included in the **energy index** |
| `b/` | included in the **non-energy index** |
| `c/` | included in the **precious-metals index** |
| `d/` | **index-definition** footnote |

None of them says anything about whether a number is estimated. Brent carries
`a/` in all 65 issues because Brent is an energy commodity — and was therefore
labelled an estimate in all 65 issues, which the source never claims.

The source is not even consistent about printing the tokens: the Rubber RSS3 row
carries `b/` in **22** of the 65 issues and omits it in the other **43**. A
symbol the publisher applies inconsistently cannot carry provenance meaning, and
the marker is now recorded exactly as displayed rather than normalised.

### The independent evidence

Estimate status comes from a **Description** statement, not from the table:

> *"Liquefied natural gas (Japan), LNG, import price, cif; recent two months'
> averages are estimates."*

Present in **65 of 65** archived issues — matched, not assumed. Each observation
is classified by its position among the issue's own ordered monthly columns:

| Position among displayed months | Status |
|---|---|
| Newest, second-newest | `source_documented_estimate` |
| Third-newest and older | `not_covered_by_current_estimate_rule` |
| Series with no documented rule | `not_documented_as_estimate` |
| Rule statement absent from the issue | `unknown` |

`false` is deliberately absent from that vocabulary. An unparsed note means the
status is unobserved, not that the value is final — the same distinction whose
absence produced R1's February 2025 verdict.

### Corrected fields

`estimate_marker` is replaced by `source_footnote_marker` (raw token, verbatim),
`source_footnote_meaning` (documented index meaning only), `estimate_status`,
`estimate_evidence_type`, `estimate_evidence_text`, `estimate_rule_version`, and
`estimate_evidence_url`.

### Corrected LNG results

| Quantity | Value |
|---|---|
| First releases documented as estimates | **65** |
| Estimate status `unknown` | **0** |
| Estimates with a later non-estimated vintage | **63** |
| Estimates revised before that vintage | **63** |
| Estimates unchanged at that vintage | **0** |
| **Right-censored / unresolved** | **2** (2026-04, 2026-05) |
| Documented estimates differing from the current workbook | **65** |

Every LNG first release is the newest displayed column of its issue, so all 65
fall inside the two-month rule. The count 65 therefore survives — but it was
re-derived from Description evidence, not retained because it had been reported
before, and it now means something different.

**The transition count is 63, not 65.** For reference month *m*, the first issue
in which *m* leaves the two-month window is issue *m+3*. The archive ends at the
June 2026 issue, so 2026-04 and 2026-05 have no such issue and are
**right-censored** — reported as unresolved rather than folded into either
outcome.

`first_non_estimated_vintage` means only that the documented rule no longer
covers that month in that issue. It is **not** a claim of permanent finality,
and nothing in this project is described as final.

### What changed and what did not

| Previous conclusion | Status under R3 |
|---|---|
| Revision frequencies and maxima (LNG 65/65 max 34.10%; palm 20/65; coal 2/57; copper 2/65; aluminum 1/65; Brent and Rubber 0) | **NUMERICALLY VALID, UNCHANGED** — measured independently of any marker, re-verified identical |
| Publication lag 1, timing verified, 65/65 coverage, all checksums | **UNCHANGED** |
| `lng_estimate_to_final_transitions: 65` | **RENAMED AND SUPERSEDED** → `documented_estimates_differing_from_latest_vintage: 65` (workbook difference) and `estimates_with_a_later_non_estimated_vintage: 63` (the actual transition count) |
| `estimate_marker` (bool from `a/`) | **REPLACED** by seven explicit fields |
| Status value `first_release_estimate` | **RENAMED** → `first_release_documented_estimate` |
| "Brent observations are estimates" (implied by the marker) | **WITHDRAWN** — Brent is `not_documented_as_estimate` in all 65 issues |
| Whether LNG estimates settle after leaving the rule window | **BECAME UNRESOLVED for 2 months** — previously not asked |
| LNG excluded from the primary feature set | **UNCHANGED** — rests on the revision record |

### C2 compatibility

C2 already read the marker as a marker, never as an estimate flag. After the
correction it also carries `source_footnote_meaning` and `estimate_status`. All
four primary series are `not_documented_as_estimate`.

**Verified across all 2,448 rows (primary + sensitivity): feature values,
availability months, lineage checksums and row counts are identical.** The
canonical table's *content checksum* changed, because two metadata columns were
added and aluminum/copper now correctly show `b/` where the old boolean produced
an empty string. That is a **metadata-only checksum change**, not a feature-value
change, and the two are reported separately rather than collapsed.

## 10. Status

| Field | Value |
|---|---|
| `minimum_publication_lag_months` | **1** |
| `publication_timing_status` | **`verified`** |
| `publication_timing_verified` | **`true`** |
| `same_reference_month_available_at_calendar_origin` | `false` |
| `latest_vintage_backtest_eligible` | `true` |
| `latest_vintage_is_point_in_time` | `false` |
| `eligible_for_primary_backtest` | **`true`** |
| `eligible_for_sensitivity_analysis` | `true` |
| `point_in_time_supported` | **`full`** (feature side only) |
| `coverage_fraction` | **1.0** |
| `archived_first_release_backtest_eligible` | **`true`** |
| `archived_first_release_coverage` | **65/65 months, 15/15 origins** |
| `revision_status` | **`revisions_observed`** |
| `revision_safe_lag_months` | **`null`** |
| `recommended_operational_lag_months` | **2** (policy) |
| `timing_status` | **`verified`** |
| `timing_approved` | `true` |
| `feature_semantics_approved` | `false` |
| `model_feature_approved` | **`false`** |

`revision_safe_lag_months` stays null because no fixed lag is shown to guarantee
final values — LNG is revised in every in-window month. Crucially, that finding no
longer nulls the publication lag: the two answer different questions, and
conflating them was a defect of the first run.
