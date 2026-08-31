# app/

The dashboard application (Phase 1 Group H — see `docs/project_roadmap.md`). Not yet implemented.

Planned: a Streamlit app, reading only from versioned `data/model_input/<run_id>/` output tables
(never recomputing predictions live), showing the 12-industry x risk-level view for both horizons,
per-industry stress-score trends, the Dependency Matrix, and per-warning contributing factors.

Streamlit is not yet added as a dependency (see `pyproject.toml`) — it will be added when this task
actually begins, not speculatively now.
