"""Feature–target assembly under two separate time cutoffs — Task D1.

Two rules, and conflating them is the leak this module exists to prevent.

**Label availability** — a label may enter training only when its target window
has CLOSED by the outer origin::

    target_window_end <= t

Selecting on ``training_forecast_origin < t`` instead would admit a 3-month
window that is still open at *t*, handing the model an outcome it could not yet
know.

**Historical feature availability** — the feature vector belonging to a
historical training origin *u* must be reconstructed as it stood **at u**::

    conditioned_available_month <= u        (NOT <= t)

Refreshing that vector with everything known at *t* is the subtler leak: the
training row would carry information published after the moment it claims to
represent, and the model would learn from a version of history that never
existed. The two cutoffs are enforced by different arguments so they cannot
drift into each other.

Early history is not imputed. A 12-month log change simply does not exist before
enough months have accumulated, and inventing one would fabricate the very
signal the model is being asked to find.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AssemblyError",
    "FutureFeatureError",
    "InsufficientFeatureHistoryError",
    "REGISTERED_TRANSFORMATIONS",
    "NON_FERROUS_CHANNELS",
    "SHARED_NON_FERROUS_COMMODITIES",
    "FeatureIndex",
    "build_feature_index",
    "features_as_of",
    "label_permitted_origins",
    "assemble_training_matrix",
    "predictor_name",
]

# The five C2 transformations, used in full. Selecting among them on target
# outcomes is prohibited, so the set is fixed here rather than searched.
REGISTERED_TRANSFORMATIONS: tuple[str, ...] = (
    "price_level",
    "log_change_1m_pct",
    "log_change_3m_pct",
    "log_change_12m_pct",
    "realized_volatility_3m_pct",
)

# Aluminum and Copper read the SAME I/O sector 107 coefficient (C3-R1). At most
# one may enter a model, chosen globally per outer origin and horizon.
SHARED_NON_FERROUS_COMMODITIES: tuple[str, ...] = ("aluminum_usd_mt", "copper_usd_mt")
NON_FERROUS_CHANNELS: tuple[str, ...] = ("none", "aluminum", "copper")
_CHANNEL_TO_COMMODITY = {
    "aluminum": "aluminum_usd_mt",
    "copper": "copper_usd_mt",
    "none": None,
}


class AssemblyError(ValueError):
    """Assembly could not proceed as specified."""


class FutureFeatureError(AssemblyError):
    """A feature would be used before it was published."""


class InsufficientFeatureHistoryError(AssemblyError):
    """The complete registered transformation set is not yet available."""


def predictor_name(commodity_series_id: str, base_feature_name: str) -> str:
    return f"{commodity_series_id}__{base_feature_name}"


@dataclass
class FeatureIndex:
    """As-of lookup for one C4 matrix variant.

    ``entries[(industry, commodity, feature)]`` is a list of
    ``(available_month, reference_month, value, c2_lineage, c3_checksum)``
    sorted by availability, so an as-of query is a filter plus a max.
    """

    variant: str
    entries: dict[tuple[str, str, str], list[tuple]]
    eligible_pairs: set[tuple[str, str]]
    industries: tuple[str, ...]
    commodities: tuple[str, ...]
    diagnostics: dict = field(default_factory=dict)
    # (origin, industry, channel) -> vector. The nested loop asks the same
    # question thousands of times; the answer cannot change, because the index
    # is immutable once built.
    _cache: dict = field(default_factory=dict, repr=False)


def build_feature_index(rows, variant: str) -> FeatureIndex:
    """Index one variant's conditioned features for as-of retrieval."""
    entries: dict[tuple[str, str, str], list[tuple]] = {}
    eligible: set[tuple[str, str]] = set()
    for row in rows:
        if row["matrix_variant"] != variant:
            continue
        key = (
            str(row["industry_id"]),
            str(row["commodity_series_id"]),
            str(row["base_feature_name"]),
        )
        entries.setdefault(key, []).append(
            (
                str(row["conditioned_available_month"])[:10],
                str(row["reference_month"])[:10],
                float(row["conditioned_feature_value"]),
                str(row["c2_lineage_checksum"]),
                str(row["c3_exposure_checksum"]),
            )
        )
        eligible.add((str(row["industry_id"]), str(row["commodity_series_id"])))
    if not entries:
        raise AssemblyError(f"No conditioned rows for variant {variant!r}.")
    for value in entries.values():
        value.sort()

    industries = tuple(sorted({key[0] for key in entries}))
    commodities = tuple(sorted({key[1] for key in entries}))
    return FeatureIndex(
        variant=variant,
        entries=entries,
        eligible_pairs=eligible,
        industries=industries,
        commodities=commodities,
        diagnostics={
            "rows_indexed": sum(len(v) for v in entries.values()),
            "series_keys": len(entries),
            "eligible_pairs": len(eligible),
        },
    )


def features_as_of(
    index: FeatureIndex,
    origin: str,
    industry_id: str,
    non_ferrous_channel: str = "none",
    require_complete: bool = True,
) -> dict | None:
    """The feature vector for ``industry_id`` exactly as it stood at ``origin``.

    ``origin`` is the month whose information set applies — the HISTORICAL
    origin *u* for a training row, not the outer origin *t*.

    Returns ``None`` when the complete registered set is unavailable, so the
    caller can record `insufficient_registered_feature_history` rather than
    receive a silently short vector.
    """
    if non_ferrous_channel not in NON_FERROUS_CHANNELS:
        raise AssemblyError(f"Unknown non-ferrous channel {non_ferrous_channel!r}.")
    origin = str(origin)[:10]
    cache_key = (origin, industry_id, non_ferrous_channel, require_complete)
    if cache_key in index._cache:
        return index._cache[cache_key]
    chosen_metal = _CHANNEL_TO_COMMODITY[non_ferrous_channel]

    names: list[str] = []
    values: list[float] = []
    reference_months: dict[str, str] = {}
    c2_lineage: list[str] = []
    c3_lineage: list[str] = []
    omitted_ineligible: list[str] = []
    incomplete: list[str] = []

    for commodity in index.commodities:
        if commodity in SHARED_NON_FERROUS_COMMODITIES and commodity != chosen_metal:
            # Excluded by the global channel choice, not by eligibility.
            continue
        pair = (industry_id, commodity)
        if pair not in index.eligible_pairs:
            # Structurally ineligible under C3-R1: OMITTED, never zero-filled.
            omitted_ineligible.extend(
                predictor_name(commodity, feature)
                for feature in REGISTERED_TRANSFORMATIONS
            )
            continue
        for feature in REGISTERED_TRANSFORMATIONS:
            history = index.entries.get((industry_id, commodity, feature))
            if not history:
                incomplete.append(predictor_name(commodity, feature))
                continue
            usable = [item for item in history if item[0] <= origin]
            if not usable:
                incomplete.append(predictor_name(commodity, feature))
                continue
            available, reference, value, c2_checksum, c3_checksum = max(
                usable, key=lambda item: item[1]
            )
            if available > origin:
                raise FutureFeatureError(
                    f"{industry_id}/{commodity}/{feature}: available {available} "
                    f"is after origin {origin}."
                )
            # A conditioned feature describing month m cannot be usable at or
            # before m: the month has not finished. This is the check that can
            # actually catch a corrupted availability column — the one above is
            # unreachable, because `usable` is already filtered on it.
            if available <= reference:
                raise FutureFeatureError(
                    f"{industry_id}/{commodity}/{feature}: available "
                    f"{available} is not after the reference month {reference} "
                    "it describes."
                )
            names.append(predictor_name(commodity, feature))
            values.append(value)
            reference_months[predictor_name(commodity, feature)] = reference
            c2_lineage.append(c2_checksum)
            c3_lineage.append(c3_checksum)

    if require_complete and incomplete:
        index._cache[cache_key] = None
        return None
    if not names:
        index._cache[cache_key] = None
        return None
    vector = {
        "origin": origin,
        "industry_id": industry_id,
        "predictor_names": names,
        "values": values,
        "reference_months": reference_months,
        "c2_lineage_checksums": sorted(set(c2_lineage)),
        "c3_exposure_checksums": sorted(set(c3_lineage)),
        "omitted_ineligible_predictors": sorted(set(omitted_ineligible)),
        "incomplete_predictors": sorted(set(incomplete)),
        "non_ferrous_channel": non_ferrous_channel,
    }
    index._cache[cache_key] = vector
    return vector


def label_permitted_origins(labels, cutoff_origin: str, horizon: int) -> list[str]:
    """Training origins whose target window has CLOSED by ``cutoff_origin``.

    Enforced per horizon: the same outer origin permits fewer h=3 windows than
    h=1 windows, and treating them alike would admit an open 3-month window.
    """
    cutoff = str(cutoff_origin)[:10]
    permitted = {
        str(row["forecast_origin_month"])[:10]
        for row in labels
        if int(row["horizon_months"]) == int(horizon)
        and str(row["target_window_end"])[:10] <= cutoff
    }
    return sorted(permitted)


def assemble_training_matrix(
    index: FeatureIndex,
    labels_by_key: dict,
    permitted_origins: list[str],
    industry_id: str,
    horizon: int,
    non_ferrous_channel: str,
    cutoff_origin: str,
) -> dict:
    """Build one industry's training rows for one outer (or inner) origin.

    Every historical row is built at ITS OWN origin. Rows without the complete
    registered set are excluded with an explicit reason and counted, never
    silently dropped.
    """
    cutoff = str(cutoff_origin)[:10]
    rows, excluded = [], []
    for origin in permitted_origins:
        if origin > cutoff:
            raise AssemblyError(
                f"Training origin {origin} is after cutoff {cutoff}."
            )
        label = labels_by_key.get((industry_id, origin, int(horizon)))
        if label is None:
            excluded.append({"origin": origin, "reason": "no_label_for_industry"})
            continue
        if str(label["target_window_end"])[:10] > cutoff:
            raise AssemblyError(
                f"Label at {origin} closes {label['target_window_end']}, after "
                f"cutoff {cutoff}. The label gate failed."
            )
        vector = features_as_of(index, origin, industry_id, non_ferrous_channel)
        if vector is None:
            excluded.append(
                {
                    "origin": origin,
                    "reason": "insufficient_registered_feature_history",
                }
            )
            continue
        rows.append({"origin": origin, "label": label, "features": vector})

    if rows:
        reference = rows[0]["features"]["predictor_names"]
        for row in rows:
            if row["features"]["predictor_names"] != reference:
                raise AssemblyError(
                    f"{industry_id}: predictor set changes across training "
                    f"origins ({row['origin']}). A moving design matrix would "
                    "make coefficients incomparable."
                )
    return {
        "industry_id": industry_id,
        "horizon": int(horizon),
        "cutoff_origin": cutoff,
        "non_ferrous_channel": non_ferrous_channel,
        "rows": rows,
        "excluded": excluded,
        "label_permitted_origins": len(permitted_origins),
        "feature_usable_rows": len(rows),
        "excluded_for_feature_history": sum(
            1 for item in excluded
            if item["reason"] == "insufficient_registered_feature_history"
        ),
        "earliest_usable_origin": rows[0]["origin"] if rows else None,
        "latest_usable_origin": rows[-1]["origin"] if rows else None,
        "max_training_target_window_end": (
            max(str(r["label"]["target_window_end"])[:10] for r in rows)
            if rows else None
        ),
    }
