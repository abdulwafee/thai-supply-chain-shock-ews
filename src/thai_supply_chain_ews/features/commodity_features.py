"""Point-in-time commodity features from archived first releases — Task C2.

The single implementation of every C2 transformation. Scripts call this module;
nothing recomputes a formula of its own, and the wide table is a pivot of the
canonical long table rather than a second code path.

What C2 is and is not
---------------------
C2 approves DETERMINISTIC CONSTRUCTION — that a feature is computed correctly
from evidence that existed at the time. It says nothing about whether a feature
predicts anything. No target is read, no industry mapping is applied, and
``model_feature_approved`` stays false for every series.

Input discipline
----------------
Values come only from the C1.5-R2 archived FIRST-RELEASE dataset: the value the
world could actually see in the issue that first published that month. The C1
latest-vintage workbook is never substituted, because a latest-vintage number
for an old month is a number nobody had at the time.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from thai_supply_chain_ews.features.feature_availability import (
    AvailabilityPolicy,
    add_months,
    assert_inputs_published_by,
    feature_available_month,
    policy_available_month,
)
from thai_supply_chain_ews.features.feature_lineage import (
    LineageInput,
    lineage_checksum,
)

__all__ = [
    "CommodityFeatureError",
    "ExcludedSeriesError",
    "MissingInputError",
    "NonPositivePriceError",
    "DuplicateFeatureKeyError",
    "LatestVintageSubstitutionError",
    "InputCoverageError",
    "PRIMARY_SERIES",
    "EXCLUDED_SERIES",
    "FEATURE_DEFINITIONS",
    "CANONICAL_COLUMNS",
    "FEATURE_DEFINITION_VERSION",
    "REQUIRED_REFERENCE_START",
    "REQUIRED_REFERENCE_END",
    "REQUIRED_REFERENCE_MONTHS",
    "log_change_pct",
    "realized_volatility_pct",
    "load_first_release_observations",
    "build_feature_table",
    "to_wide_table",
    "expected_row_counts",
]

FEATURE_DEFINITION_VERSION = "c2_commodity_features_v1"

REQUIRED_REFERENCE_START = "2021-01-01"
REQUIRED_REFERENCE_END = "2026-05-01"
REQUIRED_REFERENCE_MONTHS = 65

# --- series policy -----------------------------------------------------------
# Exactly four series. The exclusions are C1/C1.5 findings and are NOT reopened
# here, nor are excluded series replaced with substitutes: C2 builds features
# from what was already cleared, it does not re-select sources.
PRIMARY_SERIES: tuple[str, ...] = (
    "brent_crude_usd_bbl",
    "aluminum_usd_mt",
    "copper_usd_mt",
    "rubber_rss3_usd_kg",
)

EXCLUDED_SERIES: dict[str, str] = {
    "lng_japan_usd_mmbtu": (
        "First-release values were revised in 65 of 65 required months, by up to "
        "34.10% (C1.5-R2). Constructing a point-in-time feature from a number "
        "that always moves would encode noise as signal."
    ),
    "coal_australia_usd_mt": (
        "Definition break at 2022-02: the benchmark switches from spot to "
        "futures inside the modelled window (C1, AD-R30). A log change across "
        "that boundary compares two different things."
    ),
    "palm_oil_usd_mt": (
        "Three grade and delivery-basis changes (2021-01, 2024-11, 2025-02) "
        "inside the modelled window (C1, AD-R30)."
    ),
}


class CommodityFeatureError(ValueError):
    """Base class for C2 construction failures."""


class ExcludedSeriesError(CommodityFeatureError):
    """An excluded series was requested for the primary table."""


class MissingInputError(CommodityFeatureError):
    """A required production input observation is absent.

    Raised rather than imputed. C2 performs no forward-fill, interpolation or
    substitution of any kind: a feature that cannot be computed from real
    observations is simply not emitted, and a REQUIRED one failing is an error.
    """


class NonPositivePriceError(CommodityFeatureError):
    """A price input is zero or negative, so its logarithm is undefined."""


class DuplicateFeatureKeyError(CommodityFeatureError):
    """The canonical key is not unique."""


class LatestVintageSubstitutionError(CommodityFeatureError):
    """A value did not come from an archived first release."""


class InputCoverageError(CommodityFeatureError):
    """The input dataset does not meet the C1.5-R2 contract."""


# --- transformations ---------------------------------------------------------


def log_change_pct(later: float, earlier: float) -> float:
    """100 * (ln(later) - ln(earlier)).

    Natural logarithm, scaled to percent. Not log10, and not a simple percentage
    change: the two agree only for small moves, and commodity moves are not
    always small.
    """
    if later <= 0 or earlier <= 0:
        raise NonPositivePriceError(
            f"Log change needs strictly positive prices; got {earlier} -> {later}."
        )
    return 100.0 * (math.log(later) - math.log(earlier))


def realized_volatility_pct(log_changes: list[float]) -> float:
    """Population standard deviation (ddof=0) of consecutive log changes.

    ddof=0 by preregistration. The sample estimator (ddof=1) would inflate every
    value by sqrt(3/2) on a 3-observation window — a ~22% level shift that is a
    definitional choice, not a property of the market.
    """
    n = len(log_changes)
    if n == 0:
        raise CommodityFeatureError("Realized volatility needs at least one log change.")
    mean = sum(log_changes) / n
    variance = sum((x - mean) ** 2 for x in log_changes) / n
    return math.sqrt(variance)


@dataclass(frozen=True)
class FeatureDefinition:
    """One preregistered transformation.

    ``input_lags`` lists every month the formula reads, as offsets back from the
    reference month, oldest first. It drives lineage, the input window, and
    availability — so a formula cannot quietly consume a month it did not
    declare.
    """

    name: str
    description: str
    unit_kind: str
    input_lags: tuple[int, ...]

    @property
    def min_history_months(self) -> int:
        return max(self.input_lags)


FEATURE_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        name="price_level",
        description="Archived first-release price for the reference month.",
        unit_kind="source_unit",
        input_lags=(0,),
    ),
    FeatureDefinition(
        name="log_change_1m_pct",
        description="100 * (ln p_m - ln p_{m-1}).",
        unit_kind="percent_log",
        input_lags=(1, 0),
    ),
    FeatureDefinition(
        name="log_change_3m_pct",
        description="100 * (ln p_m - ln p_{m-3}).",
        unit_kind="percent_log",
        input_lags=(3, 0),
    ),
    FeatureDefinition(
        name="log_change_12m_pct",
        description="100 * (ln p_m - ln p_{m-12}).",
        unit_kind="percent_log",
        input_lags=(12, 0),
    ),
    FeatureDefinition(
        name="realized_volatility_3m_pct",
        # Needs p_{m-3} as well as p_{m-2..m}, because r_{m-2} is itself a
        # change from m-3. Declaring only three months would understate both the
        # lineage and the availability requirement.
        description=(
            "Population std (ddof=0) of the three one-month log changes ending "
            "at m: std(r_{m-2}, r_{m-1}, r_m)."
        ),
        unit_kind="percent_log",
        input_lags=(3, 2, 1, 0),
    ),
)

CANONICAL_COLUMNS: tuple[str, ...] = (
    "series_id",
    "source_series_label",
    "feature_name",
    "feature_value",
    "unit",
    "reference_month",
    "input_window_start",
    "input_window_end",
    "input_observation_count",
    "source_available_month",
    "policy_available_month",
    "feature_available_month",
    "minimum_publication_lag_months",
    "operational_lag_months",
    "availability_policy",
    "availability_policy_label",
    "point_in_time_supported",
    "source_value_type",
    "source_issue_name",
    "source_issue_date",
    "source_issue_url",
    "source_issue_sha256",
    "source_footnote_marker",
    "source_footnote_meaning",
    "estimate_status",
    "input_lineage_checksum",
    "feature_definition_version",
    "quality_flag",
)


def expected_row_counts(n_months: int = REQUIRED_REFERENCE_MONTHS) -> dict[str, int]:
    """Rows each feature can produce from ``n_months`` consecutive observations.

    Derived from the definitions rather than hard-coded, so a changed lag cannot
    disagree with a stale constant.
    """
    return {
        definition.name: max(0, n_months - definition.min_history_months)
        for definition in FEATURE_DEFINITIONS
    }


# --- input loading -----------------------------------------------------------


def load_first_release_observations(audit_path: Path) -> dict:
    """Read the C1.5-R2 archived first-release dataset and enforce its contract.

    Returns ``{"observations": {series_id: {month: record}}, "contract": {...}}``.
    The contract fields are checked here rather than trusted, because C2's whole
    claim to be point-in-time rests on them.
    """
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))

    decisions = audit["timing_decisions"]
    problems = []
    if decisions.get("point_in_time_supported") != "full":
        problems.append(
            f"point_in_time_supported is {decisions.get('point_in_time_supported')!r}, "
            "expected 'full'"
        )
    if decisions.get("minimum_publication_lag_months") != 1:
        problems.append(
            "minimum_publication_lag_months is "
            f"{decisions.get('minimum_publication_lag_months')!r}, expected 1"
        )
    if decisions.get("publication_timing_verified") is not True:
        problems.append("publication_timing_verified is not True")
    coverage = audit["coverage"]
    if coverage.get("distinct_issues_obtained") != 65:
        problems.append(
            f"distinct_issues_obtained is {coverage.get('distinct_issues_obtained')!r}, "
            "expected 65"
        )
    if problems:
        raise InputCoverageError(
            "The C1.5-R2 dataset does not meet the properties C2 requires: "
            + "; ".join(problems)
        )

    issues_by_name = {issue["issue_name"]: issue for issue in audit["issues"]}
    availability = {
        row["reference_month"]: row for row in audit["publication_timing"]
    }

    required_months = []
    cursor = REQUIRED_REFERENCE_START
    while cursor <= REQUIRED_REFERENCE_END:
        required_months.append(cursor)
        cursor = add_months(cursor, 1)
    if len(required_months) != REQUIRED_REFERENCE_MONTHS:
        raise InputCoverageError(
            f"Required window yields {len(required_months)} months, expected "
            f"{REQUIRED_REFERENCE_MONTHS}."
        )

    observations: dict[str, dict[str, dict]] = {}
    for month in required_months:
        issue_name = audit["first_release_index"].get(month)
        if issue_name is None:
            raise MissingInputError(
                f"Reference month {month} has no first-release issue in the "
                "C1.5-R2 index. C2 does not impute."
            )
        issue = issues_by_name[issue_name]
        timing = availability.get(month)
        if timing is None or timing.get("is_true_first_release") is not True:
            raise LatestVintageSubstitutionError(
                f"Reference month {month} is not a verified TRUE first release "
                f"(status {timing and timing.get('availability_status')!r}). Only "
                "measured first releases may enter the primary C2 table."
            )
        for series_id, records in issue["observations"].items():
            record = next(
                (r for r in records if r["reference_month"] == month), None
            )
            if record is None:
                continue
            if record["displayed_value"] is None:
                continue
            observations.setdefault(series_id, {})[month] = {
                "series_id": series_id,
                "reference_month": month,
                "displayed_value": float(record["displayed_value"]),
                "displayed_text": record["displayed_text"],
                "decimal_places": int(record["decimal_places"]),
                "unit": record["unit"],
                "source_series_label": record["pdf_label"],
                # The raw index-membership token, carried through verbatim.
                # C1.5-R3 corrected the upstream field: "a/" means "included in
                # the energy index", never "estimated". C2 reads the marker and
                # its documented MEANING, and reads estimate status from the
                # separate field that carries independent evidence — it never
                # infers one from the other.
                "source_footnote_marker": record["source_footnote_marker"],
                "source_footnote_meaning": record["source_footnote_meaning"],
                "estimate_status": record["estimate_status"],
                "source_issue_name": issue["issue_name"],
                "source_issue_date": issue["issue_date"],
                "source_issue_url": issue["url"],
                "source_issue_sha256": issue["sha256"],
                "source_available_month": timing["available_month"],
                "source_value_type": "archived_first_release",
            }

    for series_id in PRIMARY_SERIES:
        found = len(observations.get(series_id, {}))
        if found != REQUIRED_REFERENCE_MONTHS:
            raise InputCoverageError(
                f"{series_id}: {found} archived first-release months, expected "
                f"{REQUIRED_REFERENCE_MONTHS} across "
                f"{REQUIRED_REFERENCE_START}..{REQUIRED_REFERENCE_END}."
            )

    return {
        "observations": observations,
        "required_months": required_months,
        "contract": {
            "point_in_time_supported": decisions["point_in_time_supported"],
            "minimum_publication_lag_months": decisions[
                "minimum_publication_lag_months"
            ],
            "publication_timing_verified": decisions["publication_timing_verified"],
            "coverage_fraction": decisions["coverage_fraction"],
            "distinct_issues_obtained": coverage["distinct_issues_obtained"],
        },
    }


def assert_primary_inputs_complete(
    observations: dict[str, dict[str, dict]],
    required_months: list[str],
    series_ids: tuple[str, ...] = PRIMARY_SERIES,
) -> None:
    """Every requested series must cover every required month, strictly positive.

    Checks the window it was GIVEN rather than a hard-coded 65, so the same code
    path guards production (65 months) and fixtures. Production still gets the
    65-month contract, because that is the window ``load_first_release_observations``
    builds.
    """
    for series_id in series_ids:
        months = observations.get(series_id, {})
        missing = [m for m in required_months if m not in months]
        if missing:
            raise MissingInputError(
                f"{series_id}: {len(missing)} required month(s) absent from the "
                f"archived first-release dataset, e.g. {missing[:3]}. C2 fails "
                "rather than imputing."
            )
        bad = [m for m in required_months if months[m]["displayed_value"] <= 0]
        if bad:
            raise NonPositivePriceError(
                f"{series_id}: non-positive price(s) at {bad}. Logarithms are "
                "undefined there; C2 fails rather than clipping."
            )


# --- construction ------------------------------------------------------------


def _lineage_for(
    definition: FeatureDefinition,
    series_months: dict[str, dict],
    reference_month: str,
) -> list[LineageInput]:
    """Collect every declared input, oldest first, failing on any absence."""
    inputs: list[LineageInput] = []
    for lag in sorted(definition.input_lags, reverse=True):
        month = add_months(reference_month, -lag)
        record = series_months.get(month)
        if record is None:
            raise MissingInputError(
                f"{definition.name} at {reference_month} needs {month}, which is "
                "not present in the archived first-release dataset."
            )
        inputs.append(
            LineageInput(
                series_id=record["series_id"],
                reference_month=month,
                displayed_value=record["displayed_value"],
                displayed_text=record["displayed_text"],
                decimal_places=record["decimal_places"],
                source_issue_name=record["source_issue_name"],
                source_issue_date=record["source_issue_date"],
                source_issue_url=record["source_issue_url"],
                source_issue_sha256=record["source_issue_sha256"],
                source_available_month=record["source_available_month"],
                source_footnote_marker=record["source_footnote_marker"],
                source_footnote_meaning=record["source_footnote_meaning"],
                estimate_status=record["estimate_status"],
            )
        )
    return inputs


def _compute(definition: FeatureDefinition, inputs: list[LineageInput]) -> float:
    """Apply the preregistered formula to its declared inputs."""
    values = [item.displayed_value for item in inputs]
    if definition.name == "price_level":
        return values[-1]
    if definition.name in ("log_change_1m_pct", "log_change_3m_pct",
                           "log_change_12m_pct"):
        return log_change_pct(values[-1], values[0])
    if definition.name == "realized_volatility_3m_pct":
        changes = [
            log_change_pct(values[i], values[i - 1]) for i in range(1, len(values))
        ]
        return realized_volatility_pct(changes)
    raise CommodityFeatureError(f"No implementation for {definition.name!r}.")


def build_feature_table(
    observations: dict[str, dict[str, dict]],
    required_months: list[str],
    policy: AvailabilityPolicy,
    series_ids: tuple[str, ...] = PRIMARY_SERIES,
    point_in_time_supported: str = "full",
) -> list[dict]:
    """Build the canonical long-format feature table for one availability policy."""
    for series_id in series_ids:
        if series_id in EXCLUDED_SERIES:
            raise ExcludedSeriesError(
                f"{series_id} is excluded from the C2 primary feature set: "
                f"{EXCLUDED_SERIES[series_id]}"
            )

    assert_primary_inputs_complete(observations, required_months, series_ids)

    rows: list[dict] = []
    for series_id in series_ids:
        series_months = observations[series_id]
        for definition in FEATURE_DEFINITIONS:
            for reference_month in required_months:
                # Skip only where history genuinely does not exist. No value is
                # manufactured to reach an expected count.
                earliest = add_months(
                    required_months[0], definition.min_history_months
                )
                if reference_month < earliest:
                    continue

                inputs = _lineage_for(definition, series_months, reference_month)
                value = _compute(definition, inputs)
                if not math.isfinite(value):
                    raise CommodityFeatureError(
                        f"{series_id}/{definition.name}/{reference_month} produced "
                        f"a non-finite value {value!r}."
                    )

                source_months = [item.source_available_month for item in inputs]
                available = feature_available_month(
                    reference_month, source_months, policy
                )
                assert_inputs_published_by(
                    available,
                    source_months,
                    f"{series_id}/{definition.name}/{reference_month}",
                )

                binding = inputs[-1]
                latest_source = max(source_months)
                markers = sorted({i.source_footnote_marker for i in inputs} - {""})
                meanings = sorted(
                    {i.source_footnote_meaning for i in inputs} - {""}
                )
                # Aggregated across every input month. Index membership and
                # estimate status are reported side by side and never derived
                # from one another (C1.5-R3).
                statuses = sorted({i.estimate_status for i in inputs})
                rows.append(
                    {
                        "series_id": series_id,
                        "source_series_label": series_months[reference_month][
                            "source_series_label"
                        ],
                        "feature_name": definition.name,
                        "feature_value": value,
                        "unit": (
                            series_months[reference_month]["unit"]
                            if definition.unit_kind == "source_unit"
                            else "percent_log"
                        ),
                        "reference_month": reference_month,
                        "input_window_start": inputs[0].reference_month,
                        "input_window_end": inputs[-1].reference_month,
                        "input_observation_count": len(inputs),
                        "source_available_month": latest_source,
                        "policy_available_month": policy_available_month(
                            reference_month, policy
                        ),
                        "feature_available_month": available,
                        "minimum_publication_lag_months": (
                            policy.minimum_publication_lag_months
                        ),
                        "operational_lag_months": policy.operational_lag_months,
                        "availability_policy": policy.name,
                        "availability_policy_label": policy.label,
                        "point_in_time_supported": point_in_time_supported,
                        "source_value_type": "archived_first_release",
                        "source_issue_name": binding.source_issue_name,
                        "source_issue_date": binding.source_issue_date,
                        "source_issue_url": binding.source_issue_url,
                        "source_issue_sha256": binding.source_issue_sha256,
                        "source_footnote_marker": ";".join(markers),
                        "source_footnote_meaning": ";".join(meanings),
                        "estimate_status": ";".join(statuses),
                        "input_lineage_checksum": lineage_checksum(inputs),
                        "feature_definition_version": FEATURE_DEFINITION_VERSION,
                        "quality_flag": "ok",
                    }
                )

    rows.sort(key=lambda r: (r["series_id"], r["feature_name"], r["reference_month"]))
    _assert_unique_keys(rows)
    return rows


def _assert_unique_keys(rows: list[dict]) -> None:
    seen: set[tuple] = set()
    for row in rows:
        key = (
            row["series_id"],
            row["feature_name"],
            row["reference_month"],
            row["availability_policy"],
        )
        if key in seen:
            raise DuplicateFeatureKeyError(
                f"Duplicate canonical key {key}. The grain "
                "(series_id, feature_name, reference_month, availability_policy) "
                "must be unique."
            )
        seen.add(key)


def to_wide_table(rows: list[dict]) -> list[dict]:
    """Pivot the canonical long table. No transformation logic lives here.

    The wide table is a VIEW: every number in it was computed once, in
    ``build_feature_table``. Reimplementing a formula for the wide path is how
    two tables that should agree quietly stop agreeing.
    """
    wide: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["reference_month"], row["series_id"])
        entry = wide.setdefault(
            key,
            {
                "reference_month": row["reference_month"],
                "series_id": row["series_id"],
                "availability_policy": row["availability_policy"],
            },
        )
        entry[f"{row['series_id']}__{row['feature_name']}"] = row["feature_value"]
        entry[f"{row['series_id']}__{row['feature_name']}__available_month"] = row[
            "feature_available_month"
        ]
    return [wide[key] for key in sorted(wide)]
