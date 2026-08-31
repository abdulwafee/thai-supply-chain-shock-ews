"""Industry-conditioned commodity features — Task C4.

    conditioned = commodity_feature_value  x  exposure  x  direction_sign

Three factors, three provenances, and one honest description: this is a
**structural interaction feature**. It is not a monetary cost, not a price
elasticity, not a causal effect, and not a forecast coefficient. Multiplying a
log change by an I/O coefficient does not make it money, and C4 must never
describe it as though it did.

What C4 creates and what it does not
------------------------------------
C4 creates PREDICTORS. It establishes nothing about predictive usefulness — no
target is read, no association computed, no feature selected on an outcome.

Three variants, each changing exactly ONE assumption from the primary
--------------------------------------------------------------------
``primary_direct_lag2``               operational lag 2, direct exposure
``timing_sensitivity_direct_lag1``    lag 1 instead        (timing varied)
``structural_sensitivity_total_lag2`` total requirements   (structure varied)

There is deliberately no lag-1 + total-requirement variant: changing two
assumptions at once produces a difference nobody can attribute to either.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from thai_supply_chain_ews.features.conditioned_availability import (
    assert_not_future_dated,
    conditioned_available_month,
)
from thai_supply_chain_ews.features.conditioned_lineage import (
    TRANSFORMATION_VERSION,
    ConditionedLineageInput,
    conditioned_lineage_checksum,
    exposure_row_checksum,
)

__all__ = [
    "ConditioningError",
    "IneligiblePairError",
    "AmbiguousDirectionError",
    "MATRIX_VARIANTS",
    "ZERO_REASONS",
    "CANONICAL_COLUMNS",
    "SHARED_EXPOSURE_GROUPS",
    "MatrixVariant",
    "conditioned_unit",
    "build_conditioned_matrix",
    "to_wide_table",
    "assert_no_duplicate_shared_sector_aggregate",
]


class ConditioningError(ValueError):
    """A conditioned feature could not be built as specified."""


class IneligiblePairError(ConditioningError):
    """A pair excluded by C3-R1 was requested for feature generation."""


class AmbiguousDirectionError(ConditioningError):
    """A null direction sign was requested for a signed feature."""


@dataclass(frozen=True)
class MatrixVariant:
    """One preregistered combination of assumptions."""

    name: str
    availability_policy: str
    exposure_field: str
    is_primary: bool
    label: str
    varies_from_primary: str

    def __post_init__(self) -> None:
        if self.is_primary and self.label == "sensitivity_only":
            raise ConditioningError(
                f"{self.name} cannot be both primary and sensitivity_only."
            )
        if not self.is_primary and self.label != "sensitivity_only":
            raise ConditioningError(
                f"Non-primary variant {self.name} must be labelled "
                f"'sensitivity_only', not {self.label!r}."
            )
        # Exactly one assumption may move, or attribution becomes impossible.
        varied = 0
        if self.availability_policy != "operational_lag_2m":
            varied += 1
        if self.exposure_field != "direct_exposure":
            varied += 1
        if not self.is_primary and varied != 1:
            raise ConditioningError(
                f"{self.name} varies {varied} assumptions from the primary. Each "
                "sensitivity variant must vary exactly one, or a difference "
                "cannot be attributed to either."
            )
        if self.is_primary and varied != 0:
            raise ConditioningError(
                f"The primary variant must use operational_lag_2m and "
                f"direct_exposure; {self.name} does not."
            )


MATRIX_VARIANTS: tuple[MatrixVariant, ...] = (
    MatrixVariant(
        name="primary_direct_lag2",
        availability_policy="operational_lag_2m",
        exposure_field="direct_exposure",
        is_primary=True,
        label="primary",
        varies_from_primary="none",
    ),
    MatrixVariant(
        name="timing_sensitivity_direct_lag1",
        availability_policy="publication_lag_1m",
        exposure_field="direct_exposure",
        is_primary=False,
        label="sensitivity_only",
        varies_from_primary="availability_policy",
    ),
    MatrixVariant(
        name="structural_sensitivity_total_lag2",
        availability_policy="operational_lag_2m",
        exposure_field="total_requirement_exposure",
        is_primary=False,
        label="sensitivity_only",
        varies_from_primary="exposure_field",
    ),
)

# Distinct states. A zero that means "this industry genuinely uses none of it"
# is not the same fact as a zero that means "the price did not move", and
# neither is the same as "no feature exists here at all".
ZERO_REASONS = (
    "not_zero",
    "zero_due_to_exposure",
    "zero_due_to_base_feature",
    "zero_due_to_both",
    "not_generated_due_to_ineligibility",
)

SHARED_EXPOSURE_GROUPS = {"107": "io_sector_107"}

CANONICAL_COLUMNS: tuple[str, ...] = (
    "industry_id",
    "industry_name",
    "commodity_series_id",
    "base_feature_name",
    "conditioned_feature_name",
    "reference_month",
    "base_feature_value",
    "exposure_value",
    "exposure_variant",
    "direction_channel",
    "price_increase_to_stress_sign",
    "conditioned_feature_value",
    "base_unit",
    "conditioned_unit",
    "availability_policy",
    "matrix_variant",
    "is_primary",
    "source_available_month",
    "policy_available_month",
    "base_feature_available_month",
    "structural_available_by",
    "conditioned_available_month",
    "proxy_fit_status",
    "shared_io_source_sector",
    "shared_exposure_group",
    "additive_aggregation_allowed",
    "zero_reason",
    "c2_lineage_checksum",
    "c3_exposure_checksum",
    "conditioned_lineage_checksum",
    "structural_reference_year",
    "time_invariant_assumption",
    "quality_flag",
    "model_feature_approved",
)


def conditioned_unit(base_unit: str) -> str:
    """Name the product honestly: a base unit TIMES a dimensionless coefficient."""
    if base_unit == "percent_log":
        return "percentage_point_log_change_x_exposure_coefficient"
    return f"{base_unit}_x_exposure_coefficient"


def _zero_reason(exposure: float, base_value: float) -> str:
    exposure_zero = exposure == 0.0
    base_zero = base_value == 0.0
    if exposure_zero and base_zero:
        return "zero_due_to_both"
    if exposure_zero:
        return "zero_due_to_exposure"
    if base_zero:
        return "zero_due_to_base_feature"
    return "not_zero"


def build_conditioned_matrix(
    c2_rows_by_policy: dict[str, list[dict]],
    exposure_rows: list[dict],
    availability,
    structural_source_checksum: str,
    variants: tuple[MatrixVariant, ...] = MATRIX_VARIANTS,
) -> list[dict]:
    """Build the canonical long table across every variant."""
    eligible = [row for row in exposure_rows if row["industry_pair_feature_eligible"]]
    ineligible = [
        row for row in exposure_rows if not row["industry_pair_feature_eligible"]
    ]
    if not eligible:
        raise ConditioningError("No eligible pairs; nothing to condition.")

    exposure_checksums = {
        (row["industry_id"], row["commodity_series_id"]): exposure_row_checksum(row)
        for row in exposure_rows
    }

    rows: list[dict] = []
    for variant in variants:
        c2_rows = c2_rows_by_policy.get(variant.availability_policy)
        if c2_rows is None:
            raise ConditioningError(
                f"{variant.name} needs C2 policy {variant.availability_policy!r}, "
                "which was not supplied."
            )
        by_series: dict[str, list[dict]] = {}
        for row in c2_rows:
            by_series.setdefault(row["series_id"], []).append(row)

        for pair in sorted(
            eligible, key=lambda r: (r["industry_id"], r["commodity_series_id"])
        ):
            sign = pair["price_increase_to_stress_sign"]
            if sign is None:
                # Should be unreachable: C3-R1 never marks a null-sign pair
                # eligible. Kept as a guard because a forced sign is the exact
                # failure this project must not commit.
                raise AmbiguousDirectionError(
                    f"{pair['industry_id']}/{pair['commodity_series_id']} is "
                    "eligible but carries a null sign. C4 does not infer one."
                )
            exposure = pair[variant.exposure_field]
            if exposure is None or not math.isfinite(exposure):
                raise ConditioningError(
                    f"{pair['industry_id']}/{pair['commodity_series_id']}: "
                    f"{variant.exposure_field} is {exposure!r}."
                )

            sector = pair["commodity_io_sector_code"]
            shared = bool(pair["shared_io_source_sector"])
            group = SHARED_EXPOSURE_GROUPS.get(sector) if shared else None

            for base in sorted(
                by_series[pair["commodity_series_id"]],
                key=lambda r: (r["feature_name"], r["reference_month"]),
            ):
                base_value = base["feature_value"]
                if not math.isfinite(base_value):
                    raise ConditioningError(
                        f"Non-finite C2 value at {base['series_id']}/"
                        f"{base['feature_name']}/{base['reference_month']}."
                    )

                available = conditioned_available_month(
                    base["feature_available_month"], availability
                )
                assert_not_future_dated(
                    base["reference_month"], available,
                    f"{pair['industry_id']}/{base['series_id']}/"
                    f"{base['feature_name']}/{base['reference_month']}",
                )

                value = base_value * exposure * sign
                if not math.isfinite(value):
                    raise ConditioningError("Non-finite conditioned value.")

                lineage = conditioned_lineage_checksum(
                    ConditionedLineageInput(
                        c2_lineage_checksum=base["input_lineage_checksum"],
                        industry_id=pair["industry_id"],
                        commodity_series_id=pair["commodity_series_id"],
                        c3_exposure_checksum=exposure_checksums[
                            (pair["industry_id"], pair["commodity_series_id"])
                        ],
                        exposure_value=exposure,
                        direction_sign=sign,
                        proxy_fit_status=pair["commodity_proxy_fit_status"],
                        eligibility_status=True,
                        matrix_variant=variant.name,
                        transformation_version=TRANSFORMATION_VERSION,
                        structural_source_checksum=structural_source_checksum,
                    )
                )

                rows.append(
                    {
                        "industry_id": pair["industry_id"],
                        "industry_name": pair["industry_name"],
                        "commodity_series_id": pair["commodity_series_id"],
                        "base_feature_name": base["feature_name"],
                        "conditioned_feature_name": (
                            f"{pair['industry_id']}__{pair['commodity_series_id']}"
                            f"__{base['feature_name']}"
                        ),
                        "reference_month": base["reference_month"],
                        "base_feature_value": base_value,
                        "exposure_value": exposure,
                        "exposure_variant": variant.exposure_field,
                        "direction_channel": pair["direction_channel"],
                        "price_increase_to_stress_sign": sign,
                        "conditioned_feature_value": value,
                        "base_unit": base["unit"],
                        "conditioned_unit": conditioned_unit(base["unit"]),
                        "availability_policy": variant.availability_policy,
                        "matrix_variant": variant.name,
                        "is_primary": variant.is_primary,
                        "source_available_month": base["source_available_month"],
                        "policy_available_month": base["policy_available_month"],
                        "base_feature_available_month": base[
                            "feature_available_month"
                        ],
                        "structural_available_by": availability.structural_available_by,
                        "conditioned_available_month": available,
                        "proxy_fit_status": pair["commodity_proxy_fit_status"],
                        "shared_io_source_sector": shared,
                        "shared_exposure_group": group,
                        # Shared-sector exposures are one coefficient read twice.
                        "additive_aggregation_allowed": not shared,
                        "zero_reason": _zero_reason(exposure, base_value),
                        "c2_lineage_checksum": base["input_lineage_checksum"],
                        "c3_exposure_checksum": exposure_checksums[
                            (pair["industry_id"], pair["commodity_series_id"])
                        ],
                        "conditioned_lineage_checksum": lineage,
                        "structural_reference_year": pair[
                            "structural_reference_year"
                        ],
                        "time_invariant_assumption": True,
                        "quality_flag": "ok",
                        "model_feature_approved": False,
                    }
                )

    rows.sort(
        key=lambda r: (
            r["matrix_variant"], r["industry_id"], r["commodity_series_id"],
            r["base_feature_name"], r["reference_month"],
        )
    )
    _validate(rows, eligible, ineligible, variants)
    return rows


def _validate(rows, eligible, ineligible, variants) -> None:
    """Fail loudly on any violation of the canonical contract."""
    per_variant = 306 * len(eligible)
    expected_total = per_variant * len(variants)
    if len(rows) != expected_total:
        raise ConditioningError(
            f"Expected {expected_total} rows ({len(eligible)} pairs x 306 "
            f"observations x {len(variants)} variants); built {len(rows)}."
        )

    keys = set()
    excluded = {(r["industry_id"], r["commodity_series_id"]) for r in ineligible}
    for row in rows:
        key = (
            row["industry_id"], row["commodity_series_id"],
            row["base_feature_name"], row["reference_month"],
            row["matrix_variant"],
        )
        if key in keys:
            raise ConditioningError(f"Duplicate canonical key {key}.")
        keys.add(key)

        if (row["industry_id"], row["commodity_series_id"]) in excluded:
            raise IneligiblePairError(
                f"{row['industry_id']}/{row['commodity_series_id']} is excluded by "
                "C3-R1 but produced a conditioned feature."
            )
        if row["price_increase_to_stress_sign"] is None:
            raise AmbiguousDirectionError("A conditioned row carries a null sign.")
        if row["direction_channel"] != "cost_pressure":
            raise ConditioningError(
                f"{row['industry_id']}/{row['commodity_series_id']}: conditioned "
                f"features require cost_pressure, got {row['direction_channel']!r}."
            )
        if row["conditioned_available_month"] < row["base_feature_available_month"]:
            raise ConditioningError("Conditioned feature predates its C2 input.")
        if row["conditioned_available_month"][:7] < row["structural_available_by"][:7]:
            raise ConditioningError("Conditioned feature predates the I/O source.")
        if row["shared_io_source_sector"] and row["additive_aggregation_allowed"]:
            raise ConditioningError(
                "A shared-sector row permits additive aggregation; sector-107 "
                "exposure would be double-counted."
            )
        if row["model_feature_approved"] is not False:
            raise ConditioningError("C4 must not set model_feature_approved true.")

    for variant in variants:
        count = sum(1 for r in rows if r["matrix_variant"] == variant.name)
        if count != per_variant:
            raise ConditioningError(
                f"{variant.name}: {count} rows, expected {per_variant}."
            )
        fields = {r["exposure_variant"] for r in rows if r["matrix_variant"] == variant.name}
        if fields != {variant.exposure_field}:
            raise ConditioningError(
                f"{variant.name} mixes exposure fields {fields}; a variant must "
                "use exactly one."
            )
        policies = {
            r["availability_policy"] for r in rows if r["matrix_variant"] == variant.name
        }
        if policies != {variant.availability_policy}:
            raise ConditioningError(f"{variant.name} mixes availability policies.")

    primaries = {r["matrix_variant"] for r in rows if r["is_primary"]}
    if primaries != {"primary_direct_lag2"}:
        raise ConditioningError(
            f"Exactly one variant may be primary; found {primaries}."
        )


def assert_no_duplicate_shared_sector_aggregate(
    component_rows: list[dict], context: str = "aggregate"
) -> None:
    """Reject any aggregate that draws sector-107 exposure more than once.

    Aluminum and Copper read the SAME coefficient. Summing both into one index
    counts that structure twice while looking like two independent signals.
    """
    seen: dict[tuple[str, str], list[str]] = {}
    for row in component_rows:
        group = row.get("shared_exposure_group")
        if not group:
            continue
        key = (row["industry_id"], group)
        seen.setdefault(key, []).append(row["commodity_series_id"])
    offenders = {
        key: sorted(set(series)) for key, series in seen.items() if len(set(series)) > 1
    }
    if offenders:
        raise ConditioningError(
            f"{context}: shared-sector exposure would be counted more than once — "
            f"{offenders}. Aluminum and Copper read the same I/O sector 107 "
            "coefficient and are not independently measured, so an aggregate may "
            "include it at most once."
        )


def to_wide_table(rows: list[dict], matrix_variant: str) -> list[dict]:
    """Pivot one variant of the canonical long table. No conditioning logic here."""
    selected = [row for row in rows if row["matrix_variant"] == matrix_variant]
    if not selected:
        raise ConditioningError(f"No rows for variant {matrix_variant!r}.")
    wide: dict[tuple[str, str], dict] = {}
    for row in selected:
        key = (row["reference_month"], row["industry_id"])
        entry = wide.setdefault(
            key,
            {
                "reference_month": row["reference_month"],
                "industry_id": row["industry_id"],
                "matrix_variant": matrix_variant,
            },
        )
        column = f"{row['commodity_series_id']}__{row['base_feature_name']}"
        entry[column] = row["conditioned_feature_value"]
        entry[f"{column}__available_month"] = row["conditioned_available_month"]
        entry[f"{column}__zero_reason"] = row["zero_reason"]
    return [wide[key] for key in sorted(wide)]
