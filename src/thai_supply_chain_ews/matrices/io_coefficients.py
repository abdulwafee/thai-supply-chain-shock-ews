"""Technical coefficients and the Leontief inverse — Task C3.

Two matrices, and the distinction between them matters:

``A`` — technical coefficients, ``A[i][j] = Z[i][j] / X[j]``
    The DIRECT input of sector *i* required per unit of sector *j*'s output.

``L = (I - A)^-1``, and ``T = L - I``
    TOTAL requirements, direct plus every indirect round, with the identity term
    removed so a sector's own unit of output is not counted as a requirement of
    itself.

What these numbers are not
--------------------------
They are STRUCTURAL ACCOUNTING RATIOS from one benchmark year. They are not
price pass-through elasticities, not causal effects, and not forecasts. A
Leontief coefficient answers "how much of *i* was embodied per unit of *j* in
the benchmark year", under fixed proportions and no substitution. Nothing in
C3 may describe them otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "CoefficientError",
    "SingularMatrixError",
    "CoefficientMatrices",
    "build_technical_coefficients",
    "leontief_inverse",
]

# A column of A summing to >= 1 means intermediate inputs alone consume the whole
# unit of output, leaving nothing for value added. One such column makes (I-A)
# singular or near-singular.
MAX_PLAUSIBLE_COLUMN_SUM = 1.0
CONDITION_NUMBER_LIMIT = 1e12
RECONSTRUCTION_TOLERANCE = 1e-8


class CoefficientError(ValueError):
    """The coefficient matrix failed a structural validation."""


class SingularMatrixError(CoefficientError):
    """(I - A) cannot be inverted stably.

    Raised rather than regularized. Quietly nudging a singular matrix would
    produce numbers that look like requirements but are artifacts of the nudge.
    """


@dataclass
class CoefficientMatrices:
    """Validated A, L and T over a fixed, deterministic sector ordering."""

    sector_codes: list[str]
    a: np.ndarray
    leontief: np.ndarray
    total_requirement: np.ndarray
    excluded_sectors: list[str]
    diagnostics: dict = field(default_factory=dict)

    def index(self, code: str) -> int:
        return self.sector_codes.index(code)

    def direct(self, input_code: str, producing_code: str) -> float:
        return float(self.a[self.index(input_code), self.index(producing_code)])

    def total(self, input_code: str, producing_code: str) -> float:
        return float(
            self.total_requirement[self.index(input_code), self.index(producing_code)]
        )


def build_technical_coefficients(
    table,
    measure: str = "purchaser",
) -> tuple[list[str], np.ndarray, dict]:
    """Build ``A`` from the intermediate block only.

    Sectors with non-positive gross output are EXCLUDED, not divided by. Their
    coefficients are undefined, and substituting zero would assert that such a
    sector requires nothing — a claim the table does not make.
    """
    usable = [code for code in table.sector_codes if table.gross_output[code] > 0]
    excluded = [code for code in table.sector_codes if table.gross_output[code] <= 0]

    if len(set(usable)) != len(usable):
        raise CoefficientError("Duplicate sector codes in the coefficient ordering.")

    size = len(usable)
    z = np.zeros((size, size), dtype=float)
    for row_index, row_code in enumerate(usable):
        for col_index, col_code in enumerate(usable):
            z[row_index, col_index] = table.z(row_code, col_code, measure)

    x = np.array([table.gross_output[code] for code in usable], dtype=float)
    if not np.all(x > 0):
        raise CoefficientError("Non-positive gross output survived the filter.")

    a = z / x[np.newaxis, :]  # divide COLUMN j by X_j

    if not np.all(np.isfinite(a)):
        raise CoefficientError("Non-finite technical coefficients.")

    column_sums = a.sum(axis=0)
    implausible = [
        (usable[i], float(column_sums[i]))
        for i in range(size)
        if column_sums[i] >= MAX_PLAUSIBLE_COLUMN_SUM
    ]
    negative = [
        (usable[i], usable[j], float(a[i, j]))
        for i, j in zip(*np.where(a < -1e-12), strict=True)
    ]

    diagnostics = {
        "measure": measure,
        "sectors_used": size,
        "sectors_excluded_zero_output": excluded,
        "column_sum_min": float(column_sums.min()),
        "column_sum_max": float(column_sums.max()),
        "column_sum_mean": float(column_sums.mean()),
        "columns_with_sum_ge_1": implausible,
        "negative_coefficients": negative[:20],
        "negative_coefficient_count": len(negative),
        "nonzero_coefficients": int(np.count_nonzero(a)),
        "observed_zero_coefficients": int(a.size - np.count_nonzero(a)),
    }
    return usable, a, diagnostics


def leontief_inverse(
    sector_codes: list[str], a: np.ndarray, diagnostics: dict | None = None
) -> CoefficientMatrices:
    """Invert ``(I - A)`` and return L and ``T = L - I``, with residuals reported."""
    size = a.shape[0]
    if a.shape != (size, size):
        raise CoefficientError(f"A must be square; got {a.shape}.")
    if len(sector_codes) != size:
        raise CoefficientError(
            f"{len(sector_codes)} sector codes for a {size}x{size} matrix."
        )

    identity = np.eye(size)
    im_a = identity - a

    condition = float(np.linalg.cond(im_a))
    if not np.isfinite(condition) or condition > CONDITION_NUMBER_LIMIT:
        raise SingularMatrixError(
            f"(I - A) is ill-conditioned (condition number {condition:.3e} > "
            f"{CONDITION_NUMBER_LIMIT:.0e}). C3 stops rather than applying an "
            "undocumented regularization."
        )
    try:
        leontief = np.linalg.inv(im_a)
    except np.linalg.LinAlgError as exc:
        raise SingularMatrixError(f"(I - A) is singular: {exc}") from exc

    residual = float(np.abs(im_a @ leontief - identity).max())
    if residual > RECONSTRUCTION_TOLERANCE:
        raise SingularMatrixError(
            f"(I - A)L deviates from I by {residual:.3e}, above the documented "
            f"tolerance {RECONSTRUCTION_TOLERANCE:.0e}."
        )
    if not np.all(np.isfinite(leontief)):
        raise CoefficientError("Non-finite values in the Leontief inverse.")

    # Remove the identity term: a sector's own unit of output is not one of its
    # own input requirements.
    total_requirement = leontief - identity

    negative = int(np.sum(total_requirement < -1e-9))
    combined = dict(diagnostics or {})
    combined.update(
        {
            "matrix_size": size,
            "condition_number": condition,
            "reconstruction_residual_max_abs": residual,
            "reconstruction_tolerance": RECONSTRUCTION_TOLERANCE,
            "identity_term_removed": True,
            "leontief_diagonal_min": float(np.diag(leontief).min()),
            "total_requirement_negative_cells": negative,
            "total_requirement_min": float(total_requirement.min()),
            "total_requirement_max": float(total_requirement.max()),
            "interpretation": (
                "Structural accounting ratios from one benchmark year under "
                "fixed proportions. NOT price pass-through elasticities and NOT "
                "causal effects."
            ),
        }
    )
    return CoefficientMatrices(
        sector_codes=list(sector_codes),
        a=a,
        leontief=leontief,
        total_requirement=total_requirement,
        excluded_sectors=list(combined.get("sectors_excluded_zero_output", [])),
        diagnostics=combined,
    )
