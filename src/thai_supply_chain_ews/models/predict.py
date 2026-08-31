"""Inference with a trained MVP model (Phase 1 Group F).

STUB — not implemented.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def predict(model_path: Path, features: pd.DataFrame) -> pd.DataFrame:
    """Score `features` with a trained model.

    Returns stress_score and risk_level per row. Not implemented.
    """
    raise NotImplementedError(
        "predict() is not implemented yet — see docs/project_roadmap.md Phase 1 Group F."
    )
