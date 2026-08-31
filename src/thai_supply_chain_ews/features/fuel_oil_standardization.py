"""Exposure-normalisation and standardisation-invariance checks (Task C10).

Two identities decide what industry conditioning actually contributed, and both
are checked numerically rather than argued.

**Exposure normalisation.** C9 built ``D_g = E_g X`` for each eligible industry
``g``, where ``X`` is one 15 x 5 source-time matrix and ``E_g`` is a positive
scalar. Dividing each industry's design by its own exposure must therefore
recover the *same* ``X`` from all eleven of them. If two reconstructions disagree,
something is wrong with an exposure, an alignment or a pivot — and the resulting
matrix would still look like a design matrix, which is why this is checked.

**Standardisation invariance.** For ``E_g > 0``,
``standardize(E_g X) == standardize(X)`` column-wise, because a positive scalar
cancels in both the mean and the standard deviation. So a model that standardises
its predictors per industry sees exactly the same design for every eligible
industry: the exposure affects raw scale and nothing else.

That is a statement about the design, not a prediction about performance.
:func:`assert_no_performance_claim` raises on wording that turns it into one.

IND-04 is never divided. Its conditioned values are structurally ineligible, its
multiplier is null, and normalising an unresolved design would produce a number
with no meaning.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from thai_supply_chain_ews.features.fuel_oil_identifiability import (
    IdentifiabilityError,
    fingerprint,
    standardize,
)

__all__ = [
    "DEFAULT_RECONSTRUCTION_TOLERANCE",
    "DEFAULT_STANDARDIZATION_TOLERANCE",
    "STANDARDIZATION_DDOF",
    "InvarianceReport",
    "StandardizationError",
    "assert_no_performance_claim",
    "assert_positive_exposure",
    "equivalence_classes",
    "exposure_normalized_design",
    "reconstruction_report",
    "standardization_invariance_report",
]

#: Preregistered before any value was read.
DEFAULT_RECONSTRUCTION_TOLERANCE = 1e-9
DEFAULT_STANDARDIZATION_TOLERANCE = 1e-9

#: Population standard deviation, matching C2's volatility convention so a
#: standardised design and a realized volatility do not use different estimators.
STANDARDIZATION_DDOF = 0


class StandardizationError(IdentifiabilityError):
    """A normalisation was asked to divide by something it may not divide by."""


def assert_positive_exposure(industry_id: str, exposure, eligible: bool) -> float:
    """Raise unless this industry's exposure may be divided by.

    An ineligible industry is refused by name: IND-04's conditioned values are
    structurally unresolved, so dividing them by its exposure would produce a
    reconstruction of a design that does not exist.
    """
    if not eligible:
        raise StandardizationError(
            f"{industry_id} is structurally ineligible; its conditioned values are "
            "unresolved and may not be exposure-normalised"
        )
    if exposure is None:
        raise StandardizationError(f"{industry_id} has no exposure")
    value = float(exposure)
    if not math.isfinite(value) or value <= 0:
        raise StandardizationError(
            f"{industry_id} has exposure {value}; normalisation needs a strictly "
            "positive finite scalar"
        )
    return value


def assert_no_performance_claim(text: str) -> None:
    """Raise on wording that turns a design identity into a performance claim."""
    lowered = str(text).lower()
    banned = (
        "will not predict", "will predict", "no predictive value",
        "predictive power", "will perform", "improves accuracy",
        "reduces error", "adds no signal", "adds signal",
    )
    for phrase in banned:
        if phrase in lowered:
            raise IdentifiabilityError(
                f"{phrase!r} is a predictive claim. C10 establishes a property of "
                "the design matrix without reading any target, and cannot say "
                "what a model would do"
            )


def exposure_normalized_design(design, exposure: float) -> list:
    """``D_g / E_g``. The reconstruction of the shared source-time matrix."""
    if exposure <= 0:
        raise StandardizationError(f"exposure {exposure} is not strictly positive")
    return [[value / exposure for value in row] for row in design]


def equivalence_classes(matrices, tolerance: float) -> list:
    """Group matrices that agree to within ``tolerance``, element-wise.

    This is the decision-relevant count. :func:`~...fingerprint` rounds to a
    fixed number of *significant* digits, so it resolves a standardised value of
    5e-4 down to 1e-17 - below double precision - and can split matrices that
    the preregistered absolute tolerance calls identical. The fingerprint count
    is still reported, but it does not decide anything.
    """
    classes = []
    for key, matrix in matrices.items():
        for group in classes:
            if _max_abs_difference(group["representative"], matrix) <= tolerance:
                group["members"].append(key)
                break
        else:
            classes.append({"representative": matrix, "members": [key]})
    return [sorted(group["members"]) for group in classes]


def _max_abs_difference(first, second) -> float:
    return max(
        abs(a - b)
        for row_a, row_b in zip(first, second, strict=True)
        for a, b in zip(row_a, row_b, strict=True)
    )


@dataclass
class InvarianceReport:
    """What the two identities actually produced for one variant."""

    variant_id: str
    eligible_industries: int = 0
    tolerance: float = DEFAULT_RECONSTRUCTION_TOLERANCE
    max_residual: float = 0.0
    per_industry_residual: dict = field(default_factory=dict)
    distinct_raw_fingerprints: int = 0
    distinct_normalized_fingerprints: int = 0
    normalized_equivalence_classes: int = 0
    distinct_standardized_fingerprints: int = 0
    all_designs_are_scalar_multiples: bool = False
    exposure_survives_standardization: bool = True
    industry_specific_temporal_pattern_present: bool = True
    ineligible_industries_normalized: list = field(default_factory=list)
    source_reconciliation_residual: float = None

    def to_dict(self) -> dict:
        return asdict(self)


def reconstruction_report(matrix, exposures, eligible, source_time=None,
                          tolerance: float = DEFAULT_RECONSTRUCTION_TOLERANCE
                          ) -> InvarianceReport:
    """Reconstruct the shared source-time matrix from every eligible industry.

    All reconstructions must agree with one another, and — when the C8 source
    transformations are supplied — with them too, within the preregistered
    tolerance.
    """
    designs, normalized = {}, {}
    for industry_id in eligible:
        exposure = assert_positive_exposure(
            industry_id, exposures.get(industry_id), True
        )
        design = matrix.industry_design(industry_id)
        designs[industry_id] = design
        normalized[industry_id] = exposure_normalized_design(design, exposure)

    if not normalized:
        raise StandardizationError("no eligible industry to reconstruct from")

    reference = normalized[eligible[0]]
    residuals = {
        industry_id: _max_abs_difference(reference, candidate)
        for industry_id, candidate in normalized.items()
    }
    worst = max(residuals.values())

    report = InvarianceReport(
        variant_id=matrix.variant_id,
        eligible_industries=len(eligible),
        tolerance=tolerance,
        max_residual=worst,
        per_industry_residual=residuals,
        distinct_raw_fingerprints=len({fingerprint(d) for d in designs.values()}),
        distinct_normalized_fingerprints=len({
            fingerprint(d) for d in normalized.values()
        }),
        normalized_equivalence_classes=len(
            equivalence_classes(normalized, tolerance)
        ),
        all_designs_are_scalar_multiples=worst <= tolerance,
        ineligible_industries_normalized=[],
    )
    if worst > tolerance:
        raise StandardizationError(
            f"{matrix.variant_id}: exposure-normalised reconstructions differ by "
            f"{worst!r}, above {tolerance}. Every eligible industry's design must "
            "be the same source-time matrix scaled by its own exposure"
        )
    if source_time is not None:
        report.source_reconciliation_residual = _max_abs_difference(
            reference, source_time
        )
        if report.source_reconciliation_residual > tolerance:
            raise StandardizationError(
                f"{matrix.variant_id}: the reconstruction differs from the C8 "
                f"source transformations by {report.source_reconciliation_residual!r}"
            )
    return report


def standardization_invariance_report(
    matrix, exposures, eligible,
    tolerance: float = DEFAULT_STANDARDIZATION_TOLERANCE,
    ddof: int = STANDARDIZATION_DDOF,
) -> dict:
    """Check ``standardize(E_g X) == standardize(X)`` for every eligible industry.

    If the identity holds, a per-industry standardised design carries no trace of
    the exposure — the conditioning contributed cross-industry *scale* and no new
    temporal shape.
    """
    designs = {g: matrix.industry_design(g) for g in eligible}
    standardized = {g: standardize(d, ddof) for g, d in designs.items()}
    reference_industry = eligible[0]
    reference_exposure = assert_positive_exposure(
        reference_industry, exposures.get(reference_industry), True
    )
    source_time = exposure_normalized_design(
        designs[reference_industry], reference_exposure
    )
    reference = standardize(source_time, ddof)

    residuals = {
        g: _max_abs_difference(reference, candidate)
        for g, candidate in standardized.items()
    }
    worst = max(residuals.values())
    distinct = len({fingerprint(m) for m in standardized.values()})
    classes = equivalence_classes(standardized, tolerance)
    identity_holds = worst <= tolerance and len(classes) == 1
    return {
        "variant_id": matrix.variant_id,
        "ddof": ddof,
        "tolerance": tolerance,
        "max_standardized_design_residual": worst,
        "per_industry_residual": residuals,
        "standardized_equivalence_classes": len(classes),
        "distinct_standardized_fingerprints": distinct,
        "fingerprint_agrees_with_tolerance_classes": distinct == len(classes),
        "identity_holds": identity_holds,
        "identity_decided_by": "max_standardized_design_residual <= tolerance",
        "exposure_survives_per_industry_standardization": not identity_holds,
        "industry_specific_temporal_pattern_present": len(classes) > 1,
        "note": (
            "For a positive scalar E, standardize(E X) == standardize(X) because "
            "the scalar cancels in both the mean and the standard deviation. "
            "Sector-093 exposure therefore affects raw scale and does not survive "
            "per-industry standardisation. This is a property of the design "
            "matrix, established without reading any target."
        ),
        "fingerprint_note": (
            "The fingerprint rounds to a fixed number of significant digits, so a "
            "standardised value near zero is resolved far below double precision "
            "and two matrices that agree to 1e-15 can fingerprint differently. "
            "Where the two counts disagree the preregistered absolute tolerance "
            "governs; the fingerprint count is reported unchanged as observed."
        ),
    }
