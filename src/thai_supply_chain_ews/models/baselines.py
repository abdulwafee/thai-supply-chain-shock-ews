"""Required baseline models (Phase 1 Group E, task E2).

STUB — not implemented. Required candidates, per configs/model.yaml and
docs/project_roadmap.md: historical mean, last-observed/persistence, a
seasonal baseline where applicable, regularized linear regression, and a
simple tree baseline. All must run under the same time splits and
data-availability rules as the MVP model (Gate C) — implemented together so
that guarantee is easy to check, rather than as separate ad hoc scripts.
"""

from __future__ import annotations

import pandas as pd


def historical_mean_baseline(train_targets: pd.DataFrame) -> pd.Series:
    """Predict each industry's training-period mean stress score. Not implemented."""
    raise NotImplementedError(
        "historical_mean_baseline() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group E (task E2)."
    )


def persistence_baseline(industry_id: str, prediction_date, processed_panel: pd.DataFrame) -> float:
    """Predict the most recently observed stress score, unchanged. Not implemented.

    This is the baseline every Gate D comparison is made against.
    """
    raise NotImplementedError(
        "persistence_baseline() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group E (task E2)."
    )
