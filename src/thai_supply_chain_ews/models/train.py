"""MVP tree-based model training with walk-forward evaluation (Phase 1 Group F).

STUB — not implemented. No model library is added to pyproject.toml yet —
that dependency will be added when this task actually begins (see
docs/project_roadmap.md task F1 and the pyproject.toml comment on minimal
dependencies).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def train_walk_forward(model_input: pd.DataFrame, horizon: str, run_id: str, output_dir: Path):
    """Fit the MVP model under walk-forward / rolling-origin evaluation. Not implemented."""
    raise NotImplementedError(
        "train_walk_forward() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group F (tasks F1-F3)."
    )
