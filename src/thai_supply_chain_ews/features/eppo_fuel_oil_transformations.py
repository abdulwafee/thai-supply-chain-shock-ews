"""Source-level transformations of the EPPO fuel-oil series (Task C8).

C7.5 approved two series for transformation *with explicit gaps*, and that
qualifier is the whole design here. A transformation is numeric only when every
month its formula declares is present and approved; otherwise it is null with a
status that says which kind of absence it was. Nothing is filled, carried
forward, or computed from a shortened window.

**The formulas are C2's, not a copy of C2's.** :func:`log_change_pct` and
:func:`realized_volatility_pct` are imported from
:mod:`thai_supply_chain_ews.features.commodity_features`, and so are the
preregistered :data:`FEATURE_DEFINITIONS` with their input lags. A second
implementation would eventually drift — a ``ddof`` here, a ``log10`` there — and
the drift would be invisible because both sides would still produce plausible
numbers. :func:`assert_c2_formula_compatibility` re-checks the lag tuples at
import time so a change on either side fails loudly.

Matching formulas do **not** mean matching evidence, and the audit says so
separately. C2's World Bank inputs are archived first-release values with a
measured publication lag and full point-in-time support; C8's EPPO inputs are
latest-vintage values under a two-month *policy* lag that was never measured and
support no point-in-time claim. Identical arithmetic on differently-evidenced
inputs is still differently-evidenced.

The two fuel oils stay apart. They share I/O sector 093, so a sum, a mean or a
composite index would double-count one coefficient;
:func:`assert_single_fuel_oil_channel` raises on any attempt to treat them as
one quantity.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from thai_supply_chain_ews.features.commodity_features import (
    FEATURE_DEFINITIONS,
    log_change_pct,
    realized_volatility_pct,
)

__all__ = [
    "AUTHORIZED_SERIES",
    "CHANNEL_BY_SERIES",
    "FEATURE_DEFINITIONS",
    "REQUIRED_INPUT_UNIT",
    "SERIES_BY_CHANNEL",
    "SHARED_PRICE_STAGE_GROUP",
    "TRANSFORMATION_FORMULA_VERSION",
    "TRANSFORMATION_IDS",
    "TRANSFORMATION_STATUSES",
    "TRANSFORMATION_UNITS",
    "SourceMonth",
    "TransformationError",
    "TransformationRow",
    "UnauthorizedSeriesError",
    "assert_c2_formula_compatibility",
    "assert_single_fuel_oil_channel",
    "assert_strict_input",
    "build_transformation_grid",
    "compute_transformation",
    "expected_counts",
    "log_change_pct",
    "month_range",
    "realized_volatility_pct",
    "required_input_months",
    "shift_month",
]

TRANSFORMATION_FORMULA_VERSION = "c8_eppo_fuel_oil_transformations_v1"

#: Only the two series C7.5 granted. H-DIESEL is absent by decision, not by
#: oversight: its ordinary label is unpublished for fifteen months.
AUTHORIZED_SERIES = ("eppo_ex_refinery_fo600_2s", "eppo_ex_refinery_fo1500_2s")

CHANNEL_BY_SERIES = {
    "eppo_ex_refinery_fo600_2s": "eppo_fo600_channel",
    "eppo_ex_refinery_fo1500_2s": "eppo_fo1500_channel",
}
SERIES_BY_CHANNEL = {channel: series for series, channel in CHANNEL_BY_SERIES.items()}

SHARED_PRICE_STAGE_GROUP = "io_sector_093_fuel_oil"

REQUIRED_INPUT_UNIT = "BAHT/LITRE"

TRANSFORMATION_IDS = tuple(definition.name for definition in FEATURE_DEFINITIONS)

#: C8 reports units in its own vocabulary; the arithmetic is C2's.
TRANSFORMATION_UNITS = {
    "price_level": "baht_per_litre",
    "log_change_1m_pct": "percentage_point_log_change",
    "log_change_3m_pct": "percentage_point_log_change",
    "log_change_12m_pct": "percentage_point_log_change",
    "realized_volatility_3m_pct": "percentage_point_log_change_volatility",
}

#: Ordered by precedence: the first condition that holds decides the status.
TRANSFORMATION_STATUSES = (
    "unauthorized_source_series",
    "source_unit_mismatch",
    "insufficient_feature_history",
    "current_month_source_gap",
    "input_window_source_gap",
    "nonpositive_source_value",
    "available_numeric",
)

#: The lag tuples C8 requires. Checked against C2 rather than trusted.
REQUIRED_INPUT_LAGS = {
    "price_level": (0,),
    "log_change_1m_pct": (1, 0),
    "log_change_3m_pct": (3, 0),
    "log_change_12m_pct": (12, 0),
    # Four price levels, not three: r_{m-2} is itself a change from m-3.
    "realized_volatility_3m_pct": (3, 2, 1, 0),
}


class TransformationError(ValueError):
    """A transformation was asked to produce a value its inputs cannot support."""


class UnauthorizedSeriesError(TransformationError):
    """A series outside the C7.5 authorization was offered for transformation."""


def assert_c2_formula_compatibility() -> dict:
    """Raise unless C2's definitions still match what C8 declares it needs.

    The failure this prevents is silent divergence: if C2 changed the volatility
    window to three price levels, C8 would keep declaring four and the two
    tables would disagree while both looked correct.
    """
    definitions = {d.name: tuple(d.input_lags) for d in FEATURE_DEFINITIONS}
    if set(definitions) != set(REQUIRED_INPUT_LAGS):
        raise TransformationError(
            f"C2 defines {sorted(definitions)} but C8 requires "
            f"{sorted(REQUIRED_INPUT_LAGS)}"
        )
    for name, lags in REQUIRED_INPUT_LAGS.items():
        if definitions[name] != lags:
            raise TransformationError(
                f"{name}: C2 declares input lags {definitions[name]}, C8 requires "
                f"{lags}. The formulas must not diverge."
            )
    return {
        "formula_compatible_with_c2": True,
        "shared_implementation": [
            "thai_supply_chain_ews.features.commodity_features.log_change_pct",
            "thai_supply_chain_ews.features.commodity_features."
            "realized_volatility_pct",
            "thai_supply_chain_ews.features.commodity_features.FEATURE_DEFINITIONS",
        ],
        "input_lags": {name: list(lags) for name, lags in definitions.items()},
        "natural_logarithm": True,
        "scaled_by_100": True,
        "volatility_ddof": 0,
        "volatility_required_price_levels": 4,
        "source_timing_contract_differs_from_c2": True,
    }


def shift_month(month: str, delta: int) -> str:
    year, index = int(str(month)[:4]), int(str(month)[5:7])
    total = year * 12 + (index - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_range(start: str, end: str) -> list:
    months, cursor = [], str(start)[:7]
    while cursor <= str(end)[:7]:
        months.append(cursor)
        cursor = shift_month(cursor, 1)
    return months


def required_input_months(transformation_id: str, reference_month: str) -> list:
    """Months the formula reads, oldest first.

    Derived from the declared lags, so a formula cannot consume a month it did
    not declare and lineage cannot understate the window.
    """
    if transformation_id not in REQUIRED_INPUT_LAGS:
        raise TransformationError(f"unknown transformation {transformation_id!r}")
    lags = REQUIRED_INPUT_LAGS[transformation_id]
    return [shift_month(reference_month, -lag) for lag in sorted(lags, reverse=True)]


def expected_counts(months: int = 65, gap_months=("2026-04",),
                    series_start: str = "2021-01", series_end: str = "2026-05") -> dict:
    """Finite and null counts each transformation can produce, derived not typed.

    Computed from the declared lags and the known strict gaps, so a stale
    constant cannot disagree with the definitions. The runner compares this
    against the preregistered table and against what it actually built.
    """
    calendar = month_range(series_start, series_end)
    if len(calendar) != months:
        raise TransformationError(
            f"{series_start}..{series_end} spans {len(calendar)} months, not {months}"
        )
    gaps = set(gap_months)
    counts = {}
    for transformation_id in TRANSFORMATION_IDS:
        finite = 0
        for month in calendar:
            window = required_input_months(transformation_id, month)
            if any(m < calendar[0] for m in window):
                continue
            if any(m in gaps for m in window):
                continue
            finite += 1
        counts[transformation_id] = {
            "finite": finite, "null_rows": len(calendar) - finite,
        }
    counts["total"] = {
        "finite": sum(v["finite"] for v in counts.values()),
        "null_rows": sum(v["null_rows"] for v in counts.values()),
    }
    return counts


@dataclass
class SourceMonth:
    """One approved monthly source observation, as C7.5 published it."""

    series_id: str
    reference_month: str
    monthly_value_strict: float
    approved_transformation_input: bool
    unit: str = REQUIRED_INPUT_UNIT
    source_product_label: str = None
    canonical_product_id: str = None
    semantic_equivalence_rule_id: str = None
    aggregation_rule_version: str = None
    aggregation_status: str = None
    monthly_lineage_checksum: str = None
    policy_available_month: str = None

    @property
    def usable(self) -> bool:
        return bool(
            self.approved_transformation_input
            and self.monthly_value_strict is not None
            and isinstance(self.monthly_value_strict, (int, float))
            and math.isfinite(self.monthly_value_strict)
        )

    def to_dict(self) -> dict:
        return asdict(self)


def assert_strict_input(observation: SourceMonth) -> float:
    """Raise unless this observation may be read as a transformation input.

    The descriptive monthly value is refused here by construction: it never
    reaches this function, because only ``monthly_value_strict`` is carried on
    :class:`SourceMonth`. What this guards is everything else — an unauthorized
    series, a wrong unit, a value that is not a finite positive number, and an
    observation C7.5 did not approve.
    """
    if observation.series_id not in AUTHORIZED_SERIES:
        raise UnauthorizedSeriesError(
            f"{observation.series_id!r} is not authorized for C8 transformation; "
            f"only {list(AUTHORIZED_SERIES)} are"
        )
    if observation.unit != REQUIRED_INPUT_UNIT:
        raise TransformationError(
            f"{observation.series_id} {observation.reference_month}: unit "
            f"{observation.unit!r} is not {REQUIRED_INPUT_UNIT!r}"
        )
    if not observation.approved_transformation_input:
        raise TransformationError(
            f"{observation.series_id} {observation.reference_month} is not an "
            "approved transformation input; its gap must propagate"
        )
    value = observation.monthly_value_strict
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TransformationError(
            f"{observation.series_id} {observation.reference_month}: "
            f"{value!r} is not a numeric price"
        )
    value = float(value)
    if not math.isfinite(value):
        raise TransformationError(
            f"{observation.series_id} {observation.reference_month}: "
            f"price {value} is not finite"
        )
    if value <= 0:
        raise TransformationError(
            f"{observation.series_id} {observation.reference_month}: "
            f"price {value} is not strictly positive; a log change is undefined"
        )
    return value


def assert_single_fuel_oil_channel(channel_ids, operation: str) -> str:
    """Raise unless exactly one fuel-oil channel is in play.

    FO 600 and FO 1500 read the same I/O sector 093 coefficient. Combining them
    — added, averaged, indexed or entered together — would count one exposure
    twice while looking like two independent measurements.
    """
    channels = sorted(set(channel_ids))
    unknown = [c for c in channels if c not in SERIES_BY_CHANNEL]
    if unknown:
        raise TransformationError(f"unknown fuel-oil channel(s) {unknown}")
    if not channels:
        raise TransformationError(f"{operation!r} names no fuel-oil channel")
    if len(channels) > 1:
        raise TransformationError(
            f"{operation!r} would use {channels} together. FO 600 and FO 1500 are "
            f"distinct products sharing {SHARED_PRICE_STAGE_GROUP}; they are "
            "mutually exclusive channel variants and are never combined"
        )
    return channels[0]


def compute_transformation(transformation_id: str, prices: list) -> float:
    """Apply one formula to its ordered price window, oldest first.

    ``prices`` must already be the exact declared window; this function does not
    look anything up, so it cannot silently substitute a neighbouring month.
    """
    window = required_input_months(transformation_id, "2000-01")
    if len(prices) != len(window):
        raise TransformationError(
            f"{transformation_id} needs {len(window)} price levels, got {len(prices)}"
        )
    values = [float(p) for p in prices]
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise TransformationError(
            f"{transformation_id}: every input price must be finite and positive; "
            f"got {values}"
        )
    if transformation_id == "price_level":
        return values[0]
    if transformation_id in ("log_change_1m_pct", "log_change_3m_pct",
                             "log_change_12m_pct"):
        return log_change_pct(values[-1], values[0])
    if transformation_id == "realized_volatility_3m_pct":
        changes = [
            log_change_pct(values[i], values[i - 1]) for i in range(1, len(values))
        ]
        return realized_volatility_pct(changes)
    raise TransformationError(f"unknown transformation {transformation_id!r}")


@dataclass
class TransformationRow:
    """One grid cell: a value or an explained absence, never a silent one."""

    channel_id: str
    shared_price_stage_group: str
    series_id: str
    canonical_product_id: str
    source_product_label: str
    reference_month: str
    transformation_id: str
    transformation_formula_version: str
    feature_value: float = None
    feature_unit: str = None
    transformation_status: str = "available_numeric"
    required_input_count: int = 0
    required_input_months: list = field(default_factory=list)
    available_input_count: int = 0
    missing_input_months: list = field(default_factory=list)
    policy_available_month: str = None
    source_available_as_of: str = None
    availability_basis: str = "conservative_policy_not_historical_measurement"
    latest_vintage_used: bool = True
    point_in_time_supported: bool = False
    operational_lag_is_measured: bool = False
    additive_aggregation_allowed: bool = False
    simultaneous_model_entry_approved: bool = False
    source_monthly_lineage_checksums: list = field(default_factory=list)
    transformation_lineage_checksum: str = None
    model_feature_approved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def classify_window(transformation_id: str, reference_month: str, observations: dict,
                    series_id: str, series_start: str) -> tuple:
    """Decide the status of one grid cell and return its usable prices.

    Precedence is fixed and total, so two runs can never disagree about which
    kind of absence a cell has:

    1. the series is not authorized;
    2. an available input carries the wrong unit;
    3. the window reaches before the series begins — *prehistory*, not a gap;
    4. the reference month itself has no approved value;
    5. some earlier month in the window has none;
    6. an available input is not strictly positive;
    7. otherwise the value is computable.
    """
    window = required_input_months(transformation_id, reference_month)
    if series_id not in AUTHORIZED_SERIES:
        return "unauthorized_source_series", window, [], list(window)

    present = {m: observations.get((series_id, m)) for m in window}
    wrong_unit = [
        m for m, o in present.items()
        if o is not None and o.unit != REQUIRED_INPUT_UNIT
    ]
    if wrong_unit:
        return "source_unit_mismatch", window, [], sorted(wrong_unit)

    before_start = [m for m in window if m < series_start]
    if before_start:
        return "insufficient_feature_history", window, [], sorted(before_start)

    missing = sorted(m for m, o in present.items() if o is None or not o.usable)
    if reference_month in missing:
        return "current_month_source_gap", window, [], missing
    if missing:
        return "input_window_source_gap", window, [], missing

    nonpositive = sorted(
        m for m, o in present.items() if float(o.monthly_value_strict) <= 0
    )
    if nonpositive:
        return "nonpositive_source_value", window, [], nonpositive

    return "available_numeric", window, [present[m] for m in window], []


def build_transformation_grid(observations, series_ids, months,
                              series_start: str,
                              policy_month_fn,
                              lineage_fn) -> list:
    """The complete grid: every series, month and transformation, always present.

    A cell is never dropped for being undefined. An omitted row and a null row
    look identical downstream only if the null row is missing, which is exactly
    how a gap becomes invisible.
    """
    assert_c2_formula_compatibility()
    indexed = {(o.series_id, o.reference_month): o for o in observations}
    if len(indexed) != len(list(observations)):
        raise TransformationError(
            "duplicate (series_id, reference_month) key in the source observations"
        )

    rows = []
    for series_id in sorted(series_ids):
        channel_id = CHANNEL_BY_SERIES.get(series_id)
        if channel_id is None:
            raise UnauthorizedSeriesError(
                f"{series_id!r} has no authorized C8 channel"
            )
        for reference_month in months:
            for transformation_id in TRANSFORMATION_IDS:
                status, window, prices, missing = classify_window(
                    transformation_id, reference_month, indexed, series_id,
                    series_start,
                )
                value = None
                if status == "available_numeric":
                    value = compute_transformation(
                        transformation_id,
                        [assert_strict_input(p) for p in prices],
                    )
                anchor = indexed.get((series_id, reference_month))
                row = TransformationRow(
                    channel_id=channel_id,
                    shared_price_stage_group=SHARED_PRICE_STAGE_GROUP,
                    series_id=series_id,
                    canonical_product_id=(
                        anchor.canonical_product_id if anchor else series_id
                    ),
                    source_product_label=(
                        anchor.source_product_label if anchor else None
                    ),
                    reference_month=reference_month,
                    transformation_id=transformation_id,
                    transformation_formula_version=TRANSFORMATION_FORMULA_VERSION,
                    feature_value=value,
                    feature_unit=TRANSFORMATION_UNITS[transformation_id],
                    transformation_status=status,
                    required_input_count=len(window),
                    required_input_months=list(window),
                    available_input_count=len(window) - len(missing),
                    missing_input_months=list(missing),
                    policy_available_month=policy_month_fn(window),
                    source_monthly_lineage_checksums=[
                        indexed[(series_id, m)].monthly_lineage_checksum
                        for m in window if (series_id, m) in indexed
                    ],
                )
                row.transformation_lineage_checksum = lineage_fn(row, indexed)
                rows.append(row)

    keys = [(r.channel_id, r.reference_month, r.transformation_id) for r in rows]
    if len(keys) != len(set(keys)):
        raise TransformationError("duplicate transformation grid key")
    rows.sort(key=lambda r: (r.channel_id, r.reference_month, r.transformation_id))
    return rows
