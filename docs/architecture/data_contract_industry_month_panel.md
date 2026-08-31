# Data Contract — Industry-Month Panel and Downstream Tables

Companion to `data_architecture.md`. Full column-level contracts for `processed`, `features`,
`targets`, and `model_input`, with illustrative (non-real) example rows — no real observation
values appear in this document.

---

## `processed/industry_month_panel.parquet`

Grain: one row per `(industry_id, reference_period)`.
Primary key: `(industry_id, reference_period)`.
Foreign key: `industry_id -> mapping/industry_map.csv.industry_id`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `industry_id` | string | no | e.g. `IND-11` |
| `reference_period` | date | no | first day of month, e.g. `2024-03-01` |
| `mpi_value` | float64 | yes | |
| `mpi_available_as_of` | date | yes* | must be non-null whenever `mpi_value` is non-null |
| `capu_value` | float64 | yes | |
| `capu_available_as_of` | date | yes* | |
| `ppi_value` | float64 | yes | |
| `ppi_available_as_of` | date | yes* | |
| `export_value_usd` | float64 | yes | |
| `export_available_as_of` | date | yes* | |
| `vintage_policy` | string | no | `first_published` \| `latest_revised` |
| `source_row_refs` | string (JSON array) | no | traceability pointers into `interim` |
| `built_at` | timestamp | no | pipeline audit field |

Illustrative example row (values are placeholders, not real data):

```
industry_id: IND-11
reference_period: 2024-03-01
mpi_value: <placeholder>
mpi_available_as_of: 2024-04-30
capu_value: <placeholder>
capu_available_as_of: 2024-04-30
ppi_value: <placeholder>
ppi_available_as_of: <needs verification>
export_value_usd: <placeholder>
export_available_as_of: <needs verification>
vintage_policy: first_published
source_row_refs: ["interim/OIE_MPI#row123", "interim/OIE_CAPU#row123"]
built_at: 2026-08-26T00:00:00Z
```

---

## `features/industry_month_features.parquet`

Grain: one row per `(industry_id, prediction_date)`.
Primary key: `(industry_id, prediction_date)`.
Foreign key: `industry_id -> mapping/industry_map.csv.industry_id`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `industry_id` | string | no | |
| `prediction_date` | date | no | the month `t` a forecast is made from |
| `cutoff_date` | date | no | per §8 pseudocode; the actual boundary enforced for every value in this row |
| `<feature_name>_value` | float64 | yes | one pair of columns per onboarded feature |
| `<feature_name>_asof` | date | yes* | must satisfy `<= cutoff_date`; enforced by validation rule §10.5 |
| `feature_schema_version` | string | no | ties this row to a `schemas/features_table.schema.yaml` version |
| `built_at` | timestamp | no | |

No `role: target`-tagged source (per `configs/data.yaml`) may contribute a `<feature_name>_value`
column for the *same or a future* `reference_period` relative to `prediction_date` — this is the
mechanical form of the target/feature separation designed in this project's target-design phase.

---

## `targets/industry_month_targets.parquet`

Grain: one row per `(industry_id, prediction_date, horizon)`.
Primary key: `(industry_id, prediction_date, horizon)`.
Foreign key: `industry_id -> mapping/industry_map.csv.industry_id`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `industry_id` | string | no | |
| `prediction_date` | date | no | month `t` |
| `horizon` | string | no | `1m` \| `3m` |
| `stress_score` | float64 | no | 0–100 |
| `risk_level` | string | yes | populated only after §8's train-only threshold step runs; null until then |
| `contributing_periods` | string (JSON array) | no | which `reference_period`(s) produced this value — for `1m` always one period; for `3m` the period(s) achieving the max |
| `threshold_manifest_ref` | string | yes | pointer to the `model_input/<run_id>/manifest.yaml` threshold object used, once `risk_level` is populated |
| `built_at` | timestamp | no | |

---

## `model_input/<run_id>/{train,validation,test}.parquet`

Grain: one row per `(industry_id, prediction_date, horizon)` — the join of `features` and `targets`
for that `run_id`'s configuration.
Primary key: `(industry_id, prediction_date, horizon)`.
Foreign keys: `industry_id`, plus implicit lineage back to the exact `features`/`targets` schema
versions recorded in `manifest.yaml`.

`model_input/<run_id>/manifest.yaml` (illustrative structure):

```yaml
run_id: "2026-08-26_v1"
created_at: "2026-08-26T00:00:00Z"
features_schema_version: "<pending>"
targets_schema_version: "<pending>"
split:
  train_end: "<pending>"
  validation_end: "<pending>"
  test_end: "<pending>"
risk_thresholds:
  q60: "<pending>"
  q85: "<pending>"
  q97: "<pending>"
  fit_range_end: "<pending>"   # must equal split.train_end
notes: "manifest fields are placeholders until the architecture is implemented"
```

Every `model_input` run is immutable once written: re-running the pipeline with different data or
config produces a new `run_id` directory, never an in-place overwrite. This is what makes a given
training run fully reproducible from its manifest alone.
