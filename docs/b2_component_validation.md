# Task B2 — MPI–CapU Redundancy Validation and Component Approval

Every number below is read from
[`b2_component_validation_output.json`](b2_component_validation_output.json),
produced by `scripts/run_b2_component_validation.py`. Thresholds come from
[`configs/component_redundancy_gate.yaml`](../configs/component_redundancy_gate.yaml),
**written and committed before any result here was computed**.

```bash
python scripts/run_b2_component_validation.py
```

**Headline: the pair is classified `redundant`, so a K=2 equal-weight composite is
`rejected`.** Both components individually passed their semantics gate. This
outcome contradicts the project's earlier working assumption of a two-component
equal-weight index, and the thresholds were not adjusted after seeing it.

No Stress Index was built. No target labels, features, or models were created.

---

## 1. B1 invariants — independently reproduced

Re-derived from `data/processed/industry_month_panel.parquet` itself, not from
the prior report.

| Invariant | Expected | Found |
|---|---|---|
| industries | 12 | 12 ✓ |
| months | 66 (2021-01 … 2026-06) | 66, 2021-01-01 … 2026-06-01 ✓ |
| panel rows | 792 | 792 ✓ |
| model-eligible rows | 780 | 780 ✓ |
| preliminary rows | 12, all 2026-06 | 12, all 2026-06-01 ✓ |
| non-preliminary months | 65 (through 2026-05) | 65 ✓ |
| edition scope | current 2021-based only | `['2021_based']` ✓ |
| duplicate keys / MPI nulls / CapU nulls / non-positive MPI | 0 | 0 ✓ |

All reproduced. B2 proceeded. Had any material invariant failed, `validate_b1_invariants`
raises `B2InvariantError` and B2 stops rather than repairing the data.

## 2. Component semantics

| | MPI | Capacity Utilization |
|---|---|---|
| adverse transform | `-100 × (mpi_t / mpi_{t-12} − 1)` | `-(capu_t − capu_{t-12})` |
| unit | percent | **percentage points** |
| positive means | production deterioration | utilization deterioration |
| verification | 100 → 90 gives **+10.0** | 60 → 55 gives **+5.0 pp** |

CapU uses an additive percentage-point difference. The same 60 → 55 movement
expressed as a *relative* change would be +8.333%, a different quantity in a
different unit; the implementation asserts these are not equal, and the gate
config forbids the relative and multiplicative forms outright. A zero or
non-positive MPI denominator raises rather than producing an infinity.

Both components: `component_semantics_approved: true`.

## 3. Diagnostic sample

- **636 observations** = 12 industries × **53 months**
- **2022-01** through **2026-05**
- The first 12 months of each industry (2021-01 … 2021-12) have no 12-month lag
  source and are **absent, not imputed**.
- Preliminary 2026-06 excluded; every retained row is model-eligible.

### Diagnostic normalization — not leakage-safe, by design

The two components have different units and cannot be compared before
normalization, so each is converted to an industry-relative percentile rank
labelled **`diagnostic_only_full_sample_rank`** (average ties;
`percentile = average_ascending_rank / n`). These ranks use the whole B2 sample
and are therefore **not** leakage-safe. They are never written into the
production panel and are never model features — a test asserts no column
containing `rank` or `diagnostic` exists in the B1 panel. Leakage-safe
training-only / expanding-history normalization is Task B3's job.

## 4. Results

### 4.1 Data quality

**Zero quality flags raised** across all 24 industry × component series: no
insufficient coverage, no missingness, no constant or near-constant series, no
value exceeding 10× its series MAD. Nothing was deleted or winsorized —
`auto_winsorize` and `auto_delete_outliers` are both false in the gate.

### 4.2–4.4 Per-industry dependence and high-stress overlap

High-stress = top 20% within industry × component; with n=53 that is the 11
highest months. `best lag` is from §4.3.

| Industry | Pearson | Spearman | 95% CI | Jaccard | shared | MPI-only | CapU-only | best lag |
|---|---|---|---|---|---|---|---|---|
| IND-01 | 0.884 | 0.852 | [0.65, 0.97] | 0.571 | 8 | 3 | 3 | 0 |
| IND-02 | 0.986 | 0.986 | [0.96, 0.99] | **1.000** | 11 | **0** | **0** | 0 |
| IND-03 | 0.988 | 0.987 | [0.96, 0.99] | **1.000** | 11 | **0** | **0** | 0 |
| IND-04 | 0.819 | 0.715 | [0.47, 0.89] | 0.571 | 8 | 3 | 3 | 0 |
| IND-05 | 0.940 | 0.903 | [0.82, 0.97] | 0.692 | 9 | 2 | 2 | 0 |
| IND-06 | 0.917 | 0.893 | [0.76, 0.96] | 0.833 | 10 | 1 | 1 | 0 |
| IND-07 | 0.829 | 0.771 | [0.54, 0.87] | **0.222** | 4 | 7 | 7 | 0 |
| IND-08 | 0.985 | 0.982 | [0.96, 1.00] | 0.833 | 10 | 1 | 1 | 0 |
| IND-09 | 0.959 | 0.959 | [0.87, 0.97] | 0.571 | 8 | 3 | 3 | 0 |
| IND-10 | 0.929 | 0.930 | [0.83, 0.97] | 0.833 | 10 | 1 | 1 | 0 |
| IND-11 | 0.950 | 0.948 | [0.87, 0.98] | 0.571 | 8 | 3 | 3 | 0 |
| IND-12 | 0.523 | **0.396** | **[−0.06, 0.77]** | 0.375 | 6 | 5 | 5 | 0 |

Industry Spearman: **median 0.917**, range **0.396 … 0.987**.
IND-12 is the only industry whose confidence interval includes zero.

Confidence intervals are deterministic moving-block bootstraps: block length 6
months, 1,000 replications, seed 20260827, blocks resampling (MPI, CapU) pairs
jointly so short-run autocorrelation is retained.

### Pooled dependence

| Basis | Pearson | Spearman |
|---|---|---|
| **Industry-relative diagnostic ranks (primary)** | **0.8601** | **0.8601** |
| Naive pooled raw changes (secondary contrast only) | 0.8626 | 0.8446 |

The two primary figures are identical to full precision, which is expected
rather than a copy-paste error: with a balanced panel and no within-industry
ties, each percentile value `k/53` appears exactly 12 times, so re-ranking the
pooled percentiles is an exactly affine transform — and Pearson is invariant
under affine transforms.

The naive pooled figure is reported only for contrast; it confounds
industry-level scale differences with the dependence being measured and is not
the primary result.

### 4.3 Lead–lag

Sign convention, stated once and applied everywhere:
`corr(k) = Spearman(mpi_adverse[t], capu_adverse[t + k])`. **k > 0 reads CapU at
a later month than MPI, i.e. MPI leads CapU**; k < 0 means CapU leads MPI.

| lag k | −3 | −2 | −1 | **0** | +1 | +2 | +3 |
|---|---|---|---|---|---|---|---|
| pooled Spearman | 0.415 | 0.464 | 0.585 | **0.860** | 0.599 | 0.486 | 0.429 |

The strongest association is **contemporaneous (k = 0, ρ = 0.860)**, and this
holds for **all 12 of 12 industries individually**. Dependence falls away
roughly symmetrically on both sides, so the contemporaneous conclusion does not
change materially at nearby lags — neither component leads the other.

**This is descriptive association only. No causal or shock-transmission claim
follows from it,** and none is made.

### 4.5 Stability

| Subperiod | Months | Obs | Pooled ρ (ranks) | Median industry ρ | Range |
|---|---|---|---|---|---|
| early (2022-01 … 2023-12) | 24 | 288 | 0.903 | 0.941 | 0.659 … 0.989 |
| late (2024-01 … 2026-05) | 29 | 348 | 0.823 | 0.924 | 0.082 … 0.978 |

Direction and approximate magnitude are **stable**: strong positive dependence
in both windows, with the late window somewhat weaker. Both windows are small,
and per the gate a wide subperiod interval is explicitly *not* grounds to reject
a component.

## 5. Classification

All three `redundant` conditions are met, so the verdict is `redundant`:

| Condition | Threshold | Observed | Margin | Passed |
|---|---|---|---|---|
| pooled \|Spearman\| on ranks | ≥ 0.85 | **0.8601** | +0.0101 | ✓ |
| industries with \|ρ\| ≥ 0.75 | ≥ 9 of 12 | **10** | +1 | ✓ |
| median Jaccard (top-20% months) | ≥ 0.60 | **0.6319** | +0.0319 | ✓ |

### The verdict is genuinely marginal — stated plainly

Two of the three conditions passed by small margins, and **failing any one of
the three would have flipped the classification to `non_redundant`** (the
non-redundant conditions otherwise all hold: 10/12 industries carry MPI-only
high-stress months and 10/12 carry CapU-only months, against a bar of 6). Had
the pooled bar been set at 0.87 instead of 0.85, or the Jaccard bar at 0.65
instead of 0.60, the composite would have been approved.

This is exactly why the gate was pre-registered. The thresholds were fixed
before the data were seen and have not been moved.

### What the pooled verdict hides

A single project-wide verdict conceals real heterogeneity:

- **Near-duplicative**: IND-02 and IND-03 have ρ ≈ 0.986 and Jaccard = **1.000** —
  their top-20% stress months are *identical*. For these, a second component adds
  essentially nothing.
- **Clearly not duplicative**: IND-12 (ρ = 0.396, CI includes zero) and IND-07
  (Jaccard = 0.222, 7 MPI-only and 7 CapU-only months). For these, the two
  components genuinely disagree about when the industry is stressed.

A per-industry component policy is therefore a plausible future direction. **B2
does not choose it** — the gate is project-wide by design, and changing that
design after seeing results would be the same error as moving a threshold.

### Interpretation guardrail

`redundant` here means *empirically duplicative under this gate*, on this
53-month sample. Conversely, `non_redundant` would **not** have meant
statistical independence: capacity utilization is bounded by production, so the
two are strongly dependent by construction regardless of the verdict.

## 6. Decisions recorded

Four separate fields — no boolean carries more than one meaning.

| Field | MPI | CapU |
|---|---|---|
| `source_verified` | true (unchanged, Task A1) | true (unchanged, Task A1) |
| `component_semantics_approved` | **true** (new, B2) | **true** (new, B2) |
| `target_approved` | false | false |

| Composite field | Value |
|---|---|
| `redundancy_status` | **`redundant`** |
| `equal_weight_composite_status` | **`rejected`** |
| `equal_weight_is_design_choice_not_estimated` | true |
| `composite_index_built` | false |

Equal weighting was never fitted or optimized; it is an MVP design choice that
would only ever be applied *after* industry-relative normalization. It is
rejected here because the pair is duplicative under the gate, not because a
better weighting was estimated.

Task A2 bridge conclusions are untouched — they remain separate Phase 2 research
evidence.

## 7. Limitations

- **Small sample.** 53 months per industry, 636 observations. Subperiod windows
  are 24 and 29 months. Interval estimates are correspondingly wide, most
  visibly for IND-12.
- **Autocorrelation.** Monthly YoY changes are serially correlated, which is why
  the bootstrap resamples 6-month blocks rather than individual months. The
  effective sample size is well below 53.
- **Overlapping YoY windows.** Consecutive YoY observations share 11 of 12
  months of underlying data, further reducing independent information.
- **Latest-vintage data.** The panel is latest-vintage historical data, not
  point-in-time; `release_date` and `available_as_of` are null throughout. These
  diagnostics describe the data as published now, not as it appeared in real time.
- **Correlation is not causation, and not mechanism.** CapU is bounded by
  production by construction, so a high correlation is partly mechanical. The
  lead-lag table is descriptive only.
- **Diagnostic ranks are full-sample.** Appropriate for a diagnostic, unusable
  for modelling. Task B3 must build leakage-safe normalization separately.
- **The verdict is marginal**, as quantified in §5.

## 8. Artifacts

| File | Role |
|---|---|
| `configs/component_redundancy_gate.yaml` | Pre-registered thresholds |
| `src/thai_supply_chain_ews/targets/component_diagnostics.py` | Production logic |
| `scripts/run_b2_component_validation.py` | Runner + plots |
| `tests/test_b2_component_validation.py` | 41 tests |
| `docs/b2_component_validation_output.json` | Machine-readable results |
| `docs/b2_plots/` | 4 diagnostic plots |
