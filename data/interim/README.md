# data/interim

Parsed, standardized, one table per source — still atomic (no cross-source joins yet). This is the
layer where the mandatory temporal fields (`reference_period`, `release_date`, `available_as_of`,
`retrieved_at`, `source_revision`, `source_url`) are attached to every record; see
`docs/architecture/data_architecture.md` §3 for why all six live here even though only
`available_as_of` is later mirrored into `processed/`.

Append-only: a new retrieval of a previously-seen `reference_period` is a new row, never an
overwrite (§7 of the architecture doc — this is what makes both a "first published" and a "latest
revised" view derivable from the same history).

Excluded from Git. No data has been placed here yet.
