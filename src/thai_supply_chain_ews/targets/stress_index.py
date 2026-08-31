"""Industry Stress Index and target construction (Phase 1 Group B, tasks B1/B3/B4).

STUB — not implemented. The formula is already designed (see
docs/methodology.md and this project's target-design discussion): four
sign-aligned, industry-standardized, winsorized components combined as
`0.6 * max(components) + 0.4 * mean(components)`, mapped to 0-100 via an
empirical-CDF transform fit on the training partition only. Implementing it
is explicitly out of scope for this scaffolding step.
"""

from __future__ import annotations

import pandas as pd


def compute_raw_stress_index(components: pd.DataFrame) -> pd.Series:
    """Combine sign-aligned, standardized stress components into a raw index.

    `components` is expected to have one column per stress component
    (already winsorized and industry-standardized upstream). Not implemented.
    """
    raise NotImplementedError(
        "compute_raw_stress_index() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group B (task B1)."
    )


def compute_horizon_targets(stress_scores: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Compute stress_score_1m or stress_score_3m from a realized stress-score panel.

    `horizon` must be "1m" or "3m" (see configs/model.yaml). Not implemented.
    """
    raise NotImplementedError(
        "compute_horizon_targets() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group B (task B3)."
    )
