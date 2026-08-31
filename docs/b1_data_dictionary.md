# B1 Data Dictionary — Current-Edition OIE Ingestion

Covers the two datasets produced by `scripts/run_b1_ingestion.py`. Both are
written to `data/processed/` as typed Parquet and are **git-ignored** — only
schemas, metadata, fixtures, docs and code are committed.

- Code: `src/thai_supply_chain_ews/data/{oie,ingest,build_panel,taxonomy}.py`
- Config: `configs/sources.yaml`, `configs/industry_mapping.yaml`
- Run metadata: `docs/b1_ingestion_metadata.json`

**Data framing: latest-vintage historical data.** These are the values as
published in the currently retrieved files, not the values that were visible
in real time at each historical month. See §4.

---

## 1. `oie_division_month.parquet` — division-month normalized table

One row per `(reference_month, component, tsic_division)`.
Snapshot: 2,904 rows = 22 divisions × 66 months × 2 components.

| Column | Type | Null? | Description |
|---|---|---|---|
| `reference_month` | date | no | First day of the observation month (e.g. 2021-01-01). Converted from the workbook's Buddhist-Era year (BE − 543) and Thai month abbreviation. |
| `component` | string | no | `MPI` or `CapU`. |
| `tsic_division` | int16 | no | Two-digit TSIC 2009 Section C division. |
| `tsic_label` | string | no | The division label exactly as it appears in the workbook (`TSIC : NN <Thai name>`). |
| `source_value` | float64 | **yes** | The published value. Null when the source cell was non-numeric — never coerced to zero, never imputed. |
| `source_weight` | float64 | no | The official OIE value-added weight for that division and component. Parsing fails loudly if it is non-numeric or non-positive. |
| `source_edition` | string | no | `2021_based`. |
| `source_base_year` | int16 | no | `2021`. |
| `is_preliminary` | bool | no | True when the workbook marks the month with a trailing `*`. |
| `source_file` | string | no | Repo-relative path of the ingested workbook. |
| `source_sha256` | string | no | SHA-256 of that workbook, verified against `configs/sources.yaml`. |
| `source_url` | string | yes | From the retrieval manifest, falling back to the configured portal URL. |
| `retrieved_at` | string | no | Retrieval timestamp from the manifest. |
| `release_date` | datetime | **always null** | Not verified — see §4. |
| `available_as_of` | datetime | **always null** | Not verified — see §4. |
| `data_quality_flag` | string | no | `ok`, `preliminary`, or `missing_value`. |

## 2. `industry_month_panel.parquet` — industry-month panel

One row per `(reference_month, industry_id)`. Balanced: exactly 12 industries
in every month. Snapshot: 792 rows = 12 × 66.

| Column | Type | Null? | Description |
|---|---|---|---|
| `reference_month` | date | no | Observation month. |
| `industry_id` | string | no | `IND-01` … `IND-12`, stable identifiers, never renumbered. |
| `industry_name_en` | string | no | English name from `configs/industry_mapping.yaml`. |
| `industry_name_th` | string | no | Thai name from the same file. |
| `mpi_level` | float64 | yes | Official-weight aggregate of the constituent divisions' MPI. Null only if aggregation failed. |
| `capacity_utilization_rate` | float64 | yes | Same construction for Capacity Utilization, in percent. |
| `mpi_is_preliminary` | bool | no | True if any constituent MPI observation is preliminary. |
| `capu_is_preliminary` | bool | no | Same for Capacity Utilization. |
| `is_model_eligible` | bool | no | See §3. |
| `source_edition` | string | no | `2021_based`. |
| `source_base_year` | int16 | no | `2021`. |
| `mpi_source_sha256` | string | no | Checksum of the MPI workbook this row came from. |
| `capu_source_sha256` | string | no | Checksum of the CapU workbook. |
| `retrieved_at` | string | no | Retrieval timestamp. |
| `data_quality_flag` | string | no | `ok`, `preliminary`, or a `;`-joined list of aggregation failures. |

### Aggregation rule

For each industry-month-component:

1. Select the industry's configured constituent divisions.
2. Read those divisions' **official OIE source weights** for the same component and edition.
3. Renormalize them to sum to 1 across exactly those divisions.
4. Weighted sum of the division values.

Equal division weights are never used. A single-division industry (IND-04,
IND-06, IND-07, IND-10) takes weight 1.0 through the same code path, so it
reduces to the division value itself without a special case that could drift.
The effective divisions and normalized weights are preserved per
industry-month-component in `IndustryPanel.weights_used`.

Worked example — IND-01, MPI, 2021-01 (real snapshot values):

| Division | Value | Source weight | Normalized |
|---|---|---|---|
| 10 | 111.596758 | 16.671088 | 0.786086 |
| 11 | 89.600327 | 3.814524 | 0.179865 |
| 12 | 107.568855 | 0.722105 | 0.034049 |

`0.786086×111.596758 + 0.179865×89.600327 + 0.034049×107.568855 = 107.5032255799`
— identical to the panel's `mpi_level`.

## 3. `is_model_eligible`

False when **any** of these hold:

- either component is preliminary for that industry-month,
- a required value is missing,
- a constituent division is missing,
- a duplicate division record exists,
- source integrity failed.

Preliminary rows are **retained** in the panel with their values intact — they
are excluded from model-eligible output, never deleted. Snapshot: 792 total
rows, 12 preliminary (2026-06 × 12 industries), **780 model-eligible**.

## 4. What is deliberately null, and why

`release_date` and `available_as_of` are null for every row. The OIE workbooks
carry no per-month publication date and no archived release calendar was
located. Emitting a fabricated date would manufacture point-in-time
information this project does not have, and would silently license a
"real-time backtest" claim that the data cannot support.

Consequence: this dataset supports a **latest-vintage historical evaluation**
only. Any future point-in-time work must first obtain real vintage/release
metadata. A single press release observed during Task A1 suggested a ~30-day
lag; that is recorded in `configs/data.yaml` `release_lag` as an observation,
not applied here as a per-month fact.

## 5. What B1 deliberately does NOT compute

No MoM, no YoY, no robust z-scores, no Industry Stress Score, no forecast
targets, no risk levels. B1 stops at levels. Those transformations are
leakage-relevant and belong to their own design gates in later tasks.
