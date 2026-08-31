"""Exact structural path decomposition of commodity exposure (Task C5).

D4 found that direct Brent and Rubber exposure is structurally zero for six of
twelve industries. A zero direct coefficient is not an error and not an absence
of dependence: it says the industry does not buy **crude oil** or **raw sheet
rubber** across the factory gate. It may still buy refined fuel, electricity,
petrochemicals or transport, each of which carries the commodity's price.

This module answers *through what* by splitting the total requirement into the
first intermediate sector purchased:

.. math::

    T = A + TA
    \\text{direct}_{c,j}          = A_{c,j}
    \\text{indirect via }k        = T_{c,k} A_{k,j}
    \\text{indirect}_{c,j}        = \\sum_k T_{c,k} A_{k,j}
    \\text{total}_{c,j}           = A_{c,j} + \\sum_k T_{c,k} A_{k,j} = T_{c,j}

The identity is exact, so the decomposition is an **attribution, not a causal
claim**. ``T_{c,k}`` already contains every round of production including
cycles; splitting on the first purchased sector *k* assigns each unit of
requirement to the door it came through, nothing more.

Aggregation to the 12 industries uses C3's official gross-output weights. Those
weights make the weighted mean of ``A`` identical to C3's exact aggregate
``sum(Z)/sum(X)``, because ``A_{c,j} = Z_{c,j}/X_j`` — so direct, indirect and
total all reconcile under one convention rather than two.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "IDENTITY_TOLERANCE",
    "DecompositionError",
    "MediatorContribution",
    "PairDecomposition",
    "assert_column_orientation",
    "assert_identity",
    "decompose_pair",
    "decompose_sector",
    "industry_weights",
]

#: The task requires reconciliation to 1e-12; the matrices reconcile far tighter.
IDENTITY_TOLERANCE = 1e-12


class DecompositionError(ValueError):
    """A structural identity or orientation requirement was violated."""


def assert_identity(a: np.ndarray, t: np.ndarray, tolerance: float = IDENTITY_TOLERANCE) -> float:
    """Verify ``T = A + TA`` and return the observed maximum absolute residual.

    Both ``T = A + TA`` and ``T = A + AT`` hold algebraically for
    ``T = (I-A)^{-1} - I``, so this identity confirms the inverse is consistent
    but does **not** by itself pin the matrix orientation. Orientation is
    checked separately by :func:`assert_column_orientation` against the source
    table.
    """
    if a.shape != t.shape or a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise DecompositionError(f"A {a.shape} and T {t.shape} must be square and equal")
    residual = float(np.max(np.abs(t - (a + t @ a))))
    if residual > tolerance:
        raise DecompositionError(
            f"T = A + TA fails: residual {residual:.3e} exceeds {tolerance:.1e}"
        )
    return residual


def assert_column_orientation(
    a: np.ndarray, sector_codes, z_lookup, gross_output, samples: int = 12
) -> dict:
    """Confirm ``A[input, producing] == Z(input, producing) / X(producing)``.

    This is what actually pins the orientation. A transposed ``A`` still
    satisfies the Leontief identity but divides each flow by the **wrong**
    sector's output, so every coefficient is wrong while every self-consistency
    check still passes. Checking against the source flows is the only way to
    catch it.
    """
    index = {code: i for i, code in enumerate(sector_codes)}
    checked, worst = 0, 0.0
    for producing in sector_codes[:samples]:
        output = gross_output.get(producing, 0.0)
        if output <= 0:
            continue
        for supplying in sector_codes[:samples]:
            expected = z_lookup(supplying, producing) / output
            actual = float(a[index[supplying], index[producing]])
            worst = max(worst, abs(actual - expected))
            checked += 1
    if worst > 1e-9:
        raise DecompositionError(
            f"A is not column-oriented: max |A - Z/X| = {worst:.3e} over {checked} cells. "
            "A transposed matrix would divide each flow by the wrong sector's output."
        )
    return {"cells_checked": checked, "max_abs_deviation": worst, "orientation": "column"}


@dataclass(frozen=True)
class MediatorContribution:
    """One ``commodity -> intermediate sector -> industry`` path."""

    intermediate_sector_code: str
    intermediate_sector_label: str
    contribution: float
    share_of_indirect: float
    rank: int
    cumulative_share: float


@dataclass
class PairDecomposition:
    commodity_series_id: str
    commodity_sector_code: str
    industry_id: str
    direct_exposure: float
    indirect_exposure: float
    total_exposure: float
    mediators: list = field(default_factory=list)
    reconciliation_error: float = 0.0
    direct_is_observed_zero: bool = False
    indirect_material_despite_direct_zero: bool = False
    weights: dict = field(default_factory=dict)

    def cumulative_share(self, top: int) -> float:
        return sum(m.share_of_indirect for m in self.mediators[:top])


def decompose_sector(a: np.ndarray, t: np.ndarray, commodity_row: int, producing_col: int):
    """Per-mediator contribution vector for one producing sector column."""
    return t[commodity_row, :] * a[:, producing_col]


def industry_weights(component_codes, gross_output, sector_codes) -> dict:
    """C3's official gross-output shares over an industry's component sectors.

    Sectors absent from the coefficient matrix (the excluded zero-output sector)
    or without positive output are dropped before normalizing, exactly as C3
    does, so the weights sum to one over the sectors that actually exist.
    """
    available = set(sector_codes)
    usable = {
        code: float(gross_output.get(code, 0.0))
        for code in component_codes
        if code in available and gross_output.get(code, 0.0) > 0
    }
    total = sum(usable.values())
    if total <= 0:
        raise DecompositionError(
            "no component sector has positive gross output, so no defensible "
            "aggregation weight exists"
        )
    weights = {code: value / total for code, value in usable.items()}
    if abs(sum(weights.values()) - 1.0) > 1e-12:
        raise DecompositionError("gross-output weights do not sum to one")
    return weights


def decompose_pair(
    a: np.ndarray,
    t: np.ndarray,
    sector_codes,
    sector_labels: dict,
    commodity_series_id: str,
    commodity_sector_code: str,
    industry_id: str,
    component_codes,
    gross_output: dict,
    top_n: int = 10,
    materiality_threshold: float = 0.01,
) -> PairDecomposition:
    """Full decomposition for one commodity-industry pair.

    ``materiality_threshold`` is supplied by the caller from the preregistered
    config; it is never chosen here and never after inspecting an outcome.
    """
    index = {code: i for i, code in enumerate(sector_codes)}
    if commodity_sector_code not in index:
        raise DecompositionError(
            f"commodity sector {commodity_sector_code} is not in the coefficient matrix"
        )
    row = index[commodity_sector_code]
    weights = industry_weights(component_codes, gross_output, sector_codes)

    direct = 0.0
    total = 0.0
    contributions = np.zeros(len(sector_codes), dtype=float)
    for code, weight in weights.items():
        column = index[code]
        direct += weight * float(a[row, column])
        total += weight * float(t[row, column])
        contributions += weight * decompose_sector(a, t, row, column)

    indirect = float(contributions.sum())
    reconciliation_error = abs(direct + indirect - total)
    if reconciliation_error > IDENTITY_TOLERANCE:
        raise DecompositionError(
            f"{commodity_series_id} x {industry_id}: direct + indirect - total = "
            f"{reconciliation_error:.3e}, above {IDENTITY_TOLERANCE:.1e}"
        )

    order = np.argsort(-contributions)
    mediators, cumulative = [], 0.0
    for rank, position in enumerate(order[:top_n], start=1):
        value = float(contributions[position])
        if value <= 0.0:
            break
        share = value / indirect if indirect else 0.0
        cumulative += share
        code = sector_codes[position]
        mediators.append(
            MediatorContribution(
                intermediate_sector_code=code,
                intermediate_sector_label=sector_labels.get(code, "UNKNOWN"),
                contribution=value,
                share_of_indirect=share,
                rank=rank,
                cumulative_share=cumulative,
            )
        )

    direct_zero = direct == 0.0
    return PairDecomposition(
        commodity_series_id=commodity_series_id,
        commodity_sector_code=commodity_sector_code,
        industry_id=industry_id,
        direct_exposure=direct,
        indirect_exposure=indirect,
        total_exposure=total,
        mediators=mediators,
        reconciliation_error=reconciliation_error,
        direct_is_observed_zero=direct_zero,
        indirect_material_despite_direct_zero=bool(
            direct_zero and indirect >= materiality_threshold
        ),
        weights=weights,
    )
