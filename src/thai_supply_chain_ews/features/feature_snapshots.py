"""As-of feature snapshots for B4 development origins — Task C4.

At each forecast origin, take the LATEST reference month whose conditioned
feature was actually available by then:

    conditioned_available_month <= forecast_origin_month

That is an availability query, not a positional shift. "Take the value from
three months ago" happens to agree with the availability rule when publication
is perfectly regular and disagrees silently when it is not — and this project
measured the publication lag precisely so it would never have to guess. Where
availability metadata exists, positional shifting is prohibited.

No target is read. The snapshot is a predictor matrix and nothing else.
"""

from __future__ import annotations

__all__ = [
    "SnapshotError",
    "CELL_STATUSES",
    "development_origins",
    "build_development_snapshot",
]

# Distinct reasons a cell has no number. Collapsing them would hide the
# difference between "not published yet", "not enough history to compute" and
# "this pair may not generate a feature at all".
CELL_STATUSES = (
    "observed",
    "no_observation_available_at_origin",
    "insufficient_feature_history",
    "structurally_ineligible",
)


class SnapshotError(ValueError):
    """The snapshot could not be built as specified."""


def development_origins(first_origin: str, last_origin: str) -> list[str]:
    from thai_supply_chain_ews.features.conditioned_availability import add_months

    origins, cursor = [], first_origin
    while cursor <= last_origin:
        origins.append(cursor)
        cursor = add_months(cursor, 1)
    return origins


def build_development_snapshot(
    rows: list[dict],
    industries: list[str],
    commodities: list[str],
    base_features: list[str],
    eligible_pairs: set[tuple[str, str]],
    origins: list[str],
    matrix_variant: str = "primary_direct_lag2",
) -> dict:
    """Materialise the as-of primary snapshot over the development origins.

    Returns industry-origin rows plus an explicit eligibility mask. Ineligible
    cells stay NULL — never zero, because zero is a real exposure value here and
    would be indistinguishable from a structural exclusion.
    """
    selected = [row for row in rows if row["matrix_variant"] == matrix_variant]
    if not selected:
        raise SnapshotError(f"No rows for variant {matrix_variant!r}.")

    # index[(industry, commodity, feature)] -> [(available_month, reference_month, value)]
    index: dict[tuple[str, str, str], list[tuple[str, str, float]]] = {}
    for row in selected:
        key = (
            row["industry_id"], row["commodity_series_id"], row["base_feature_name"],
        )
        index.setdefault(key, []).append(
            (
                row["conditioned_available_month"],
                row["reference_month"],
                row["conditioned_feature_value"],
            )
        )
    for entries in index.values():
        entries.sort()

    snapshot_rows: list[dict] = []
    mask_rows: list[dict] = []
    counts = {status: 0 for status in CELL_STATUSES}

    for origin in origins:
        for industry in industries:
            entry = {"forecast_origin_month": origin, "industry_id": industry,
                     "matrix_variant": matrix_variant}
            for commodity in commodities:
                for feature in base_features:
                    column = f"{commodity}__{feature}"
                    pair = (industry, commodity)
                    if pair not in eligible_pairs:
                        entry[column] = None
                        status = "structurally_ineligible"
                    else:
                        candidates = [
                            item for item in index.get(
                                (industry, commodity, feature), []
                            )
                            if item[0] <= origin
                        ]
                        if not candidates:
                            entry[column] = None
                            status = "no_observation_available_at_origin"
                        else:
                            # Latest REFERENCE month among those available.
                            chosen = max(candidates, key=lambda item: item[1])
                            entry[column] = chosen[2]
                            entry[f"{column}__reference_month"] = chosen[1]
                            entry[f"{column}__available_month"] = chosen[0]
                            status = "observed"
                    entry[f"{column}__status"] = status
                    counts[status] += 1
                    mask_rows.append(
                        {
                            "forecast_origin_month": origin,
                            "industry_id": industry,
                            "commodity_series_id": commodity,
                            "base_feature_name": feature,
                            "eligible": pair in eligible_pairs,
                            "status": status,
                        }
                    )
            snapshot_rows.append(entry)

    expected_rows = len(origins) * len(industries)
    if len(snapshot_rows) != expected_rows:
        raise SnapshotError(
            f"Expected {expected_rows} industry-origin rows; built "
            f"{len(snapshot_rows)}."
        )

    eligible_cells = sum(1 for row in mask_rows if row["eligible"])
    ineligible_cells = len(mask_rows) - eligible_cells
    return {
        "matrix_variant": matrix_variant,
        "origins": origins,
        "industries": industries,
        "commodities": commodities,
        "base_features": base_features,
        "rows": snapshot_rows,
        "mask": mask_rows,
        "dimensions": {
            "origins": len(origins),
            "industries": len(industries),
            "industry_origin_rows": len(snapshot_rows),
            "commodity_feature_columns": len(commodities) * len(base_features),
            "eligible_feature_cells": eligible_cells,
            "ineligible_feature_cells": ineligible_cells,
            "total_cells": len(mask_rows),
        },
        "cell_status_counts": counts,
        "selection_rule": (
            "latest reference month with conditioned_available_month <= "
            "forecast_origin_month"
        ),
        "positional_shift_used": False,
        "target_columns_attached": False,
    }
