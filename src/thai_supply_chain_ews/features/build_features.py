"""Point-in-time feature construction (Phase 1 Group D, tasks D1/D2).

STUB — not implemented. The cutoff logic this will implement is already
specified as pseudocode in docs/architecture/data_architecture.md §8:
for each (industry_id, prediction_date), select only source values whose
`available_as_of <= cutoff_date`, never the source's role-tagged as
"target" values for the same or a future reference_period.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


def feature_cutoff(prediction_date: date) -> date:
    """Return the cutoff date for a given prediction_date.

    Convention (see configs/features.yaml `cutoff_rule`): a prediction "for
    month t" is assumed to be run at the end of calendar month t. Per-source
    available_as_of is what actually gates which values may be used — this
    function only fixes the reference point that is compared against.
    """
    raise NotImplementedError(
        "feature_cutoff() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group D (task D1)."
    )


def build_feature_row(
    industry_id: str, prediction_date: date, processed_panel: pd.DataFrame
) -> dict:
    """Build one leakage-safe feature row, per docs/architecture/data_architecture.md §8."""
    raise NotImplementedError(
        "build_feature_row() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group D (task D1)."
    )
