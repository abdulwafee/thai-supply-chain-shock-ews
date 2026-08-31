# data/model_input

Versioned, joined, time-split training/inference tables. One immutable subdirectory per `run_id`,
each with its own `manifest.yaml` recording the split boundaries, schema versions, and the
train-only-fitted risk thresholds used — see
`docs/architecture/data_contract_industry_month_panel.md`.

Splits are always time-based (`prediction_date` ordered), never random-row. A run is never
overwritten in place; re-running with different data or config produces a new `run_id`.

Excluded from Git. No data has been placed here yet.
