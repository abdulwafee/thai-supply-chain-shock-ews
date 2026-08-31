"""Identifiability and rank diagnostics for the conditioned fuel oils (C10).

C9 built a 165-row eligible panel per variant. It is tempting to read that as 165
observations. It is not: every eligible industry's design is the *same* 15 x 5
source-time matrix multiplied by a positive scalar, its sector-093 exposure. So
the panel is eleven scaled copies of fifteen rows, its rank equals the rank of
those fifteen rows, and treating it as 165 independent observations would inflate
the apparent sample elevenfold while adding nothing.

Every primary diagnostic here therefore runs on the **15 x 5 source-time matrix**.
:func:`assert_primary_input_is_source_time` raises if a caller hands the stacked
panel to a rank or correlation routine, and
:func:`assert_no_independence_claim` raises on wording that presents the stacked
rows as independent.

Three findings are kept apart because they have different causes:

* an **exact rank deficiency** — a column is an algebraic combination of others;
* a **high sample correlation** over fifteen overlapping monthly observations,
  which is descriptive and carries no significance claim;
* an **exact-zero value count**, which is about observations, not about a column
  being constant.

Correlations here can select nothing. A channel is never chosen on rank, variance
or a condition number, and no transformation is removed on a diagnostic.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

__all__ = [
    "DEFAULT_NEAR_ZERO_VARIANCE",
    "DEFAULT_RANK_TOLERANCE",
    "IdentifiabilityError",
    "MatrixDiagnostics",
    "assert_no_channel_selection",
    "assert_no_independence_claim",
    "assert_primary_input_is_source_time",
    "condition_number",
    "correlation_matrix",
    "cross_sectional_rank",
    "fingerprint",
    "numerical_rank",
    "singular_values",
    "spearman_matrix",
    "variance_report",
]

#: Preregistered. Relative to the largest singular value, so it does not move
#: with the scale of the matrix.
DEFAULT_RANK_TOLERANCE = 1e-10

DEFAULT_NEAR_ZERO_VARIANCE = 1e-12


class IdentifiabilityError(ValueError):
    """A diagnostic was asked to support a claim its input cannot carry."""


def assert_primary_input_is_source_time(matrix, expected_rows: int,
                                        operation: str) -> None:
    """Raise unless a primary diagnostic is running on the source-time matrix.

    A rank or a correlation computed on the repeated stacked panel is not wrong
    arithmetically — it is wrong *rhetorically*, because it reports fifteen
    distinct temporal rows as though there were 165.
    """
    rows = len(matrix)
    if rows != expected_rows:
        raise IdentifiabilityError(
            f"{operation!r} received a {rows}-row matrix; the primary diagnostic "
            f"input is the {expected_rows}-row source-time matrix. The stacked "
            "eligible panel is that same matrix scaled once per industry and "
            "would inflate the apparent sample size"
        )


def assert_no_independence_claim(text: str) -> None:
    """Raise on wording that presents the stacked rows as independent."""
    lowered = str(text).lower()
    banned = (
        "165 independent", "independent observations", "independent temporal",
        "165 observations", "independent samples", "effective sample size of 165",
    )
    for phrase in banned:
        if phrase in lowered:
            raise IdentifiabilityError(
                f"{phrase!r} presents the stacked panel as independent. It holds "
                "fifteen distinct temporal rows repeated across eleven industries, "
                "and adjacent transformations overlap in time"
            )


def assert_no_channel_selection(text: str) -> None:
    """Raise on wording that picks a variant using a feature diagnostic."""
    lowered = str(text).lower()
    banned = (
        "preferred channel", "select the channel", "choose the channel",
        "better conditioned channel", "primary variant", "winning variant",
        "select the variant", "choose the variant", "better rank",
    )
    for phrase in banned:
        if phrase in lowered:
            raise IdentifiabilityError(
                f"{phrase!r} selects a fuel-oil channel. Rank, variance, "
                "correlation and condition number are descriptive; C10 selects "
                "nothing, and outcome-based selection is prohibited outright"
            )


def _transpose(matrix):
    return [list(column) for column in zip(*matrix, strict=True)]


def _column_means(matrix):
    rows = len(matrix)
    return [sum(column) / rows for column in _transpose(matrix)]


def singular_values(matrix) -> list:
    """Singular values, largest first, via the Gram matrix eigenvalues.

    Implemented locally rather than borrowed so the diagnostic and the thing it
    checks do not share a code path.
    """
    import numpy as np

    return [float(v) for v in np.linalg.svd(np.asarray(matrix, dtype=float),
                                            compute_uv=False)]


def numerical_rank(matrix, tolerance: float = DEFAULT_RANK_TOLERANCE) -> int:
    """Rank at the preregistered relative tolerance."""
    values = singular_values(matrix)
    if not values or values[0] == 0:
        return 0
    cutoff = values[0] * tolerance
    return sum(1 for value in values if value > cutoff)


def condition_number(matrix) -> float:
    """Ratio of the largest to the smallest singular value."""
    values = singular_values(matrix)
    if not values or values[-1] == 0:
        return math.inf
    return values[0] / values[-1]


def standardize(matrix, ddof: int = 0) -> list:
    """Column-wise standardisation. A constant column is left centred, not scaled.

    Dividing a zero standard deviation would manufacture a value; leaving the
    column at zero keeps the degeneracy visible in the standardised matrix.
    """
    rows = len(matrix)
    if rows <= ddof:
        raise IdentifiabilityError(
            f"standardisation with ddof={ddof} needs more than {ddof} rows"
        )
    means = _column_means(matrix)
    columns = _transpose(matrix)
    deviations = [
        math.sqrt(sum((value - mean) ** 2 for value in column) / (rows - ddof))
        for column, mean in zip(columns, means, strict=True)
    ]
    return [
        [
            (value - means[index]) / (deviations[index] if deviations[index] > 0 else 1.0)
            for index, value in enumerate(row)
        ]
        for row in matrix
    ]


def variance_report(matrix, columns, near_zero: float = DEFAULT_NEAR_ZERO_VARIANCE,
                    ddof: int = 0) -> dict:
    """Exact-zero and near-zero variance per column, plus exact-zero value counts.

    A column of constant values and a column containing zeros are different
    facts and are counted separately.
    """
    rows = len(matrix)
    transposed = _transpose(matrix)
    report = {}
    for name, column in zip(columns, transposed, strict=True):
        mean = sum(column) / rows
        variance = sum((value - mean) ** 2 for value in column) / (rows - ddof)
        report[name] = {
            "variance": variance,
            "standard_deviation": math.sqrt(variance),
            "exact_zero_variance": variance == 0.0,
            "near_zero_variance": variance <= near_zero,
            "exact_zero_observations": sum(1 for value in column if value == 0.0),
            "minimum": min(column),
            "maximum": max(column),
            "retained": True,
        }
    return report


def _pearson(a, b) -> float:
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    da = [x - mean_a for x in a]
    db = [y - mean_b for y in b]
    denominator = math.sqrt(sum(x * x for x in da)) * math.sqrt(sum(y * y for y in db))
    if denominator == 0:
        return float("nan")
    return sum(x * y for x, y in zip(da, db, strict=True)) / denominator


def _rank_transform(values) -> list:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while (stop + 1 < len(order)
               and values[order[stop + 1]] == values[order[index]]):
            stop += 1
        average = (index + stop) / 2 + 1
        for position in range(index, stop + 1):
            ranks[order[position]] = average
        index = stop + 1
    return ranks


def correlation_matrix(matrix, columns) -> dict:
    """Pairwise Pearson correlations. Descriptive only, no significance."""
    transposed = _transpose(matrix)
    result = {}
    for i, first in enumerate(columns):
        for j, second in enumerate(columns):
            if j <= i:
                continue
            result[f"{first}|{second}"] = _pearson(transposed[i], transposed[j])
    return result


def spearman_matrix(matrix, columns) -> dict:
    """Pairwise Spearman correlations over the same fifteen observations."""
    transposed = [_rank_transform(column) for column in _transpose(matrix)]
    result = {}
    for i, first in enumerate(columns):
        for j, second in enumerate(columns):
            if j <= i:
                continue
            result[f"{first}|{second}"] = _pearson(transposed[i], transposed[j])
    return result


def duplicate_columns(matrix, columns, tolerance: float = 1e-12) -> list:
    """Exactly identical columns, checked algebraically rather than by correlation.

    A correlation of 1.0 and an algebraic duplicate are different findings: the
    first can arise from fifteen overlapping observations, the second is an
    exact rank deficiency.
    """
    transposed = _transpose(matrix)
    duplicates = []
    for i, first in enumerate(columns):
        for j, second in enumerate(columns):
            if j <= i:
                continue
            gap = max(
                abs(a - b) for a, b in zip(transposed[i], transposed[j], strict=True)
            )
            if gap <= tolerance:
                duplicates.append({"columns": [first, second], "max_abs_gap": gap})
    return duplicates


def cross_sectional_rank(designs, issue_index: int,
                         tolerance: float = DEFAULT_RANK_TOLERANCE) -> int:
    """Rank of the eligible-industry cross-section at one issue month.

    ``designs`` maps industry to its 15 x 5 matrix. The cross-section is the
    outer product ``E x^T``, so a correct build gives rank one; anything higher
    means a conditioning, exposure, alignment or pivot error.
    """
    cross_section = [design[issue_index] for design in designs.values()]
    return numerical_rank(cross_section, tolerance)


def fingerprint(matrix, digits: int = 12) -> str:
    """A rounded, order-preserving signature of a matrix.

    Used to count how many *distinct* designs exist across industries. Rounding
    is deliberate and preregistered: exposure normalisation is exact only to
    floating-point, and two designs differing at 1e-15 are one design.
    """
    return "|".join(
        ";".join(f"{value:.{digits}e}" for value in row) for row in matrix
    )


@dataclass
class MatrixDiagnostics:
    """Every reported diagnostic for one variant, on the source-time matrix."""

    variant_id: str
    primary_input: str = "source_time_matrix_15x5"
    source_time_rows: int = 0
    source_time_columns: int = 0
    singular_values: list = field(default_factory=list)
    numerical_rank: int = 0
    rank_tolerance: float = DEFAULT_RANK_TOLERANCE
    raw_condition_number: float = 0.0
    standardized_condition_number: float = 0.0
    variance: dict = field(default_factory=dict)
    pearson: dict = field(default_factory=dict)
    spearman: dict = field(default_factory=dict)
    exact_duplicate_columns: list = field(default_factory=list)
    industry_matrix_ranks: dict = field(default_factory=dict)
    stacked_panel_rows: int = 0
    stacked_panel_rank: int = 0
    unique_issue_months: int = 0
    cross_sectional_rank_by_issue: dict = field(default_factory=dict)
    stacked_rows_are_independent_claim_permitted: bool = False
    temporal_independence_claim_permitted: bool = False
    significance_tested: bool = False
    features_removed: list = field(default_factory=list)
    channel_selected: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
