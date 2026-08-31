"""Static 12x12 Industry Dependency Matrix from Thailand's Input-Output table
(Phase 1 Group C, tasks C1/C2).

STUB — not implemented. Blocked on docs/data_source_inventory.md's open item:
the latest NESDC I-O edition year and its sector list are not yet verified,
and `data/mapping/io_sector_to_industry.csv` is currently an empty schema-only
file for exactly that reason. Do not populate this function with an invented
or guessed mapping — see the project's restriction against fabricating
official classification mappings.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_dependency_matrix(io_table_path: Path, io_sector_mapping_path: Path) -> pd.DataFrame:
    """Aggregate NESDC I-O flows onto the 12 industry_ids via the sector mapping.

    Returns a 12x12 DataFrame (industry_id x industry_id) once implemented.
    Not implemented. Raises NotImplementedError until Phase 1 task C1, which
    itself depends on resolving the I-O source-verification blocker above.
    """
    raise NotImplementedError(
        "build_dependency_matrix() is not implemented yet — see "
        "docs/project_roadmap.md Phase 1 Group C (task C1), blocked on the "
        "NESDC I-O verification item in docs/data_source_inventory.md."
    )
