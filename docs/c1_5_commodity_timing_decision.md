# Task C1.5 — Timing Decision and Production Policy for C2

> **REVISED THREE TIMES.**
>
> **C1.5-R1** replaced the first version, which rested on an incomplete archive
> search that found 3 of 65 issues.
>
> **C1.5-R2** replaces R1. R1 concluded that no distinct February 2025 issue
> existed and set the minimum publication lag to 2 on that basis. Both were
> wrong: R1 had requested the filename-agnostic `/original/` URL and received
> January's bytes. February 2025 exists and is distinct, all 65 reference months
> are measured, and the lag is **1**. See
> [`c1_5_commodity_timing_audit.md`](c1_5_commodity_timing_audit.md) §1.3 for
> the root cause and §8 for every superseded conclusion.
>
> **C1.5-R3** corrects the footnote and estimate semantics: `a/` denotes
> ENERGY-INDEX MEMBERSHIP, not estimation. Estimate status now comes from the
> issues' Description statement. Numerical revision results, the lag, and the
> coverage findings are unaffected. See §4 and audit §9.

Evidence: [`c1_5_commodity_timing_audit.md`](c1_5_commodity_timing_audit.md).
Contract: [`configs/commodity_timing.yaml`](../configs/commodity_timing.yaml).

None of this is based on correlation with the target. No target association was
computed in C1, C1.5, C1.5-R1, C1.5-R2 or C1.5-R3.

---

## The decision in one line

**A complete point-in-time commodity feature series is available: archived
first-release values cover all 65 required reference months and all 15 B4
development origins. C2 should build on those at a minimum publication lag of
1 month, with 2 recommended as policy margin. Latest-vintage values are
permitted only for clearly-labelled sensitivity analysis. No commodity series is
yet an approved model feature.**

## 1. Archived first-release values — use them

**Recommendation: yes, as the primary series.**
`eligible_for_primary_backtest: true`.

- **65 of 65** required reference months (2021-01 … 2026-05) have a *measured*
  first release from the earliest issue that published them.
- **15 of 15** B4 development origins are covered. Nothing is bounded; nothing
  is interpolated.
- Each value carries its issue, issue date, displayed precision, footnote
  marker and its documented meaning, estimate status, evidence URL and checksum.
- Each source issue was validated against its own PDF creation date and newest
  displayed column before any value was taken from it.

This makes a real point-in-time evaluation possible for the first time in this
project — **on the feature side**. The asymmetry matters: the **MPI target
remains latest-vintage**, because no MPI release calendar has been verified. A
point-in-time feature paired with a latest-vintage target is still not a
real-time backtest, and must not be described as one.

## 2. Latest-vintage values — sensitivity analysis only

**Recommendation: not the primary series.** `eligible_for_sensitivity_analysis:
true`, and that is the whole of their permitted use. They differ materially from
what was knowable at the time: LNG is revised in **100%** of in-window months
(max 34.1%), palm oil in 30.8%.

Their legitimate use is a labelled comparison — fit on first-release, refit on
latest-vintage, report whether conclusions move. With 65 paired months that
comparison is worth running.

**Lagging latest-vintage data does not make it point-in-time.**
`latest_vintage_is_point_in_time: false`.

## 3. Which lag is permitted

| Field | Value | Status |
|---|---|---|
| `typical_publication_lag_months` | 1 | Measured (65 of 65 months) |
| **`minimum_publication_lag_months`** | **1** | **Measured for all 65 months** |
| `revision_safe_lag_months` | **null** | No fixed lag guarantees finality |
| `recommended_operational_lag_months` | **2** | **Policy choice, not measurement** |

- **Lag 0 is prohibited.** Month *t* is published after month *t* ends.
- **Lag 1 is the measured case for every one of the 65 months.** All were
  available in month *t+1*, 1–25 days after month end (median 2). Nothing rests
  on a bound, so `publication_timing_status: verified`.
- **Lag 2 is recommended** operationally: the measured requirement plus one
  month of margin, because the newest months of each issue are estimates. The
  margin is a judgement call and is labelled as one. C2 must not cite it as a
  verified minimum.

**Why lag 2 is no longer the floor.** R1 set the minimum to 2 because January
2025 appeared to have no *t+1* issue. That appearance was produced by
downloading the wrong February file — not by the archive. Retaining 2 "to be
safe" would have meant preserving a pipeline defect as a permanent policy and
misrepresenting a measured quantity. The lag follows the evidence; the evidence
changed, so the lag changed. The conservative margin is still available, and is
expressed where it belongs: in the *recommended operational* lag, labelled
policy.

**A lag fixes publication timing, not revision.** With archived first releases
that distinction largely stops mattering, because the first-release value *is*
what was knowable. It matters entirely if latest-vintage values are used.

## 4. How estimates are flagged

> **Corrected in C1.5-R3.** This section previously instructed that the `a/`
> token be treated as an estimate marker. `a/` means "included in the energy
> index" and says nothing about estimation.

- A footnote token (`a/`, `b/`, `c/`, `d/`) maps **only** to its documented
  index meaning. Estimate status is never inferred from it, in either direction.
- Estimate status comes from the issue's **Description** statement. For LNG:
  *"recent two months' averages are estimates"*, present in all 65 issues. The
  two newest displayed months are `source_documented_estimate`; older displayed
  months are `not_covered_by_current_estimate_rule`. A missing statement yields
  `unknown`, never `false`.
- Any observation whose `estimate_status` is `source_documented_estimate` must
  carry that status through to any feature built from it.
- **LNG Japan is not eligible for the primary feature set**
  (`lng_japan_primary_feature_eligible: false`): all 65 in-window months differ
  from the current workbook, median 4.01%, max 34.10%. That exclusion rests on
  the measured difference record and is unaffected by the semantic correction.
- **Brent and Rubber RSS3 never differ** from the later vintage across all 65
  months. They are the best-behaved candidates on this evidence. Brent carries
  `a/` and is **not** an estimate.

## 5. How missing archived vintages are handled

**There are none.** All 65 expected issues were obtained and validated, and all
65 reference months are measured rather than bounded.

The rule that made R1's February claim survivable is now inverted: the rules no
longer merely *record* an anomaly, they *refuse* one. A file is counted as an
issue only when its own internal date and newest displayed column agree with the
issue it claims to be, and a checksum shared by two different validated issue
months raises `IssueIdentityError` rather than being written down as
`duplicate_content`. Had that check existed in R1, the wrong February file would
have been rejected on arrival and the correct one fetched from the next
candidate.

If a future month genuinely has no obtainable issue, it is bounded from the
earliest issue that carries it — as an upper bound, never as a measured first
release, and never interpolated.

## 6. Coal and Palm oil

**Both remain excluded from the primary feature set.** Their C1 `conditional`
status is unchanged: the definition breaks are semantic, not numerical
revisions, and are never counted as revisions.

The archived issues are in hand, so confirming *when each change was disclosed*
is possible — but this task did not do it, and the status stays `unresolved`
rather than being assumed.

## 7. What C2 must not do

- Must not set `model_feature_approved: true` on the basis of this task. Every
  series carries `model_feature_approved: false`, restated per series in the
  config.
- Must not use same-reference-month commodity values.
- Must not use a lag below 1 month.
- Must not describe an evaluation as real-time: the target is still
  latest-vintage even where the features are point-in-time.
- Must not treat a month label as a release timestamp.
- Must not cite `recommended_operational_lag_months` as a verified minimum.
- Must not use a `/original/` URL to assert which issue a file is.

## 8. What would change this decision

| Evidence | Effect |
|---|---|
| Verified historical MPI release dates | Would allow an operational-release contract and a genuinely real-time backtest on both sides |
| Footnote-history review of each archived issue | Would resolve when the Coal and Palm oil definition changes were disclosed, and could clear one or both |
| Forward vintage capture from now on | Would extend point-in-time coverage past 2026-05 without depending on the World Bank continuing to host old issues |

The last point deserves emphasis: this task depends on pages the World Bank
could reorganise at any time. The archive was nearly missed once, and once
misread — the checksums recorded in the manifest are what make either failure
detectable next time.
