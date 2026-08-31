# data/features

Leakage-safe model features — one row per `(industry_id, prediction_date)`, each carrying an
explicit `cutoff_date` and a per-feature `_asof` column so that every value's availability can be
audited, not just trusted. See `docs/architecture/data_architecture.md` §8 for the point-in-time
construction logic and §10 rule 5 for the corresponding validation check.

No source tagged `role: target` in `configs/data.yaml` may contribute a value here for the same
or a future `reference_period` relative to `prediction_date`.

Excluded from Git. No data has been placed here yet.
