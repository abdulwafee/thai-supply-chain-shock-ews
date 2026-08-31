"""Feature-only candidate design matrices for the C11 architecture decision.

C10 established that within one industry the sector-093 exposure is a positive
scalar and nothing else: eleven raw designs collapse to one exposure-normalised
design, and per-industry standardisation erases the exposure entirely. That is
what makes Candidate B — fitting ``E_g x_t`` separately per industry — a
*reparameterisation* of Candidate A rather than a second architecture. The two
span the same column space within every industry, so no data can distinguish
them; only the printed coefficients differ.

The distinction that matters is a change of dimension, not of scale. In a
**pooled** panel, ``E_g x_t`` varies across industry *and* time, so an
interaction column is not proportional to the main-effect column. That is
Candidate C, and it is the only one of the three whose design can carry
exposure-associated slope heterogeneity.

Three ways to destroy that, all refused here:

* **Standardising the interaction inside each industry.** Within industry ``g``
  the interaction is ``e_g x̃``, so per-industry standardisation returns
  ``sign(e_g) · standardize(x̃)``: that industry's combined block collapses from
  rank ten to rank five. It does *not* show up as a global rank drop, because
  the centred exposures carry both signs and ``+x̃`` and ``-x̃`` span two
  directions — what is destroyed is the magnitude, with eleven
  exposure-proportional interaction blocks collapsing to two sign groups.
  :func:`per_industry_standardised_collapse` reports both measurements, because
  the per-industry rank alone understates the loss and the stacked rank alone
  hides it.
* **A constant exposure.** Centred exposure becomes exactly zero, the
  interaction block becomes a zero matrix of rank zero, and an interaction that
  identifies nothing would still look like a fitted model.
  :func:`assert_exposure_varies` raises first.
* **A redundant global intercept.** Eleven industry indicators plus an
  intercept sum to the intercept, so the design is rank-deficient by one while
  still reporting twenty-two columns.
  :func:`assert_valid_fixed_effect_coding` raises on that coding.

Nothing here fits anything. Every matrix in this module is feature-only: no
target, no prediction, no residual, no metric.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

__all__ = [
    "CANDIDATE_A",
    "CANDIDATE_B",
    "CANDIDATE_C",
    "CANDIDATE_DESIGN_VERSION",
    "CANDIDATE_IDS",
    "DEFAULT_DUPLICATE_TOLERANCE",
    "DEFAULT_RANK_TOLERANCE",
    "FIXED_EFFECT_CODINGS",
    "SOURCE_COLUMNS",
    "VALID_FIXED_EFFECT_CODING",
    "CandidateDesign",
    "CandidateDesignError",
    "assert_exposure_centering_source",
    "assert_exposure_varies",
    "assert_interaction_not_removed",
    "assert_main_effect_present",
    "assert_single_variant_design",
    "assert_valid_fixed_effect_coding",
    "block_ranks",
    "build_candidate_a_design",
    "build_candidate_b_design",
    "build_candidate_c_design",
    "candidate_b_equivalence_report",
    "center_exposures",
    "column_space_projection",
    "constant_exposure_interaction_report",
    "design_checksum",
    "duplicate_columns",
    "numerical_rank",
    "per_industry_standardised_collapse",
    "standardize_columns",
    "standardize_source_block",
]

CANDIDATE_DESIGN_VERSION = "c11_fuel_oil_candidate_design_v1"

CANDIDATE_A = "A_exposure_as_eligibility_gate"
CANDIDATE_B = "B_separate_conditioned_industry_models"
CANDIDATE_C = "C_pooled_common_effect_plus_centered_exposure_interaction"
CANDIDATE_IDS = (CANDIDATE_A, CANDIDATE_B, CANDIDATE_C)

#: Column order is fixed, matching C8 and C10, so a diagnostic that depends on
#: ordering cannot shift under a rename.
SOURCE_COLUMNS = (
    "log_change_12m_pct",
    "log_change_1m_pct",
    "log_change_3m_pct",
    "price_level",
    "realized_volatility_3m_pct",
)

VALID_FIXED_EFFECT_CODING = "industry_indicators_no_global_intercept"
FIXED_EFFECT_CODINGS = (
    VALID_FIXED_EFFECT_CODING,
    "reference_industry_dummies_plus_global_intercept",
    "global_intercept_plus_industry_indicators",
)

#: Preregistered in configs/fuel_oil_modeling_architecture.yaml before any
#: candidate matrix was built.
DEFAULT_RANK_TOLERANCE = 1e-10
DEFAULT_DUPLICATE_TOLERANCE = 1e-12

#: The only permitted origin of the exposure-centering mean. Anything else —
#: a target, a fold, a fitted residual — makes the centring outcome-dependent.
PERMITTED_CENTERING_SOURCE = "c9_phase_a_frozen_decision_table"


class CandidateDesignError(ValueError):
    """A candidate design was asked to carry information it does not carry."""


# ---------------------------------------------------------------------------
# Linear algebra. Local, so the diagnostic and the thing it checks do not share
# a code path with the assembly.
# ---------------------------------------------------------------------------
def _transpose(matrix):
    return [list(column) for column in zip(*matrix, strict=True)]


def _singular_values(matrix) -> list:
    import numpy as np

    return [float(v) for v in np.linalg.svd(np.asarray(matrix, dtype=float),
                                            compute_uv=False)]


def numerical_rank(matrix, tolerance: float = DEFAULT_RANK_TOLERANCE) -> int:
    """Rank at the preregistered relative tolerance.

    An all-zero matrix has rank zero rather than raising: a degenerate
    interaction block is a finding this module is required to report.
    """
    if not matrix or not matrix[0]:
        return 0
    values = _singular_values(matrix)
    if not values or values[0] == 0:
        return 0
    cutoff = values[0] * tolerance
    return sum(1 for value in values if value > cutoff)


def column_space_projection(matrix) -> list:
    """The orthogonal projector onto a matrix's column space.

    Two designs that project identically are the same design in different
    coordinates. This is how Candidate B is shown to be a reparameterisation
    rather than argued to be one.
    """
    import numpy as np

    array = np.asarray(matrix, dtype=float)
    rank = numerical_rank(matrix)
    if rank == 0:
        return np.zeros((array.shape[0], array.shape[0])).tolist()
    # SVD rather than QR: unpivoted QR does not order its basis by importance,
    # so truncating it to `rank` columns is only correct when the matrix has
    # full column rank. The left singular vectors are rank-revealing and give a
    # valid basis for a rank-deficient matrix too.
    left, _, _ = np.linalg.svd(array, full_matrices=False)
    basis = left[:, :rank]
    return (basis @ basis.T).tolist()


def duplicate_columns(matrix, columns,
                      tolerance: float = DEFAULT_DUPLICATE_TOLERANCE) -> list:
    """Exactly identical columns, checked algebraically rather than by correlation."""
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


def standardize_columns(matrix, ddof: int = 0) -> list:
    """Column-wise standardisation. A constant column is centred, not scaled."""
    rows = len(matrix)
    if rows <= ddof:
        raise CandidateDesignError(
            f"standardisation with ddof={ddof} needs more than {ddof} rows"
        )
    columns = _transpose(matrix)
    means = [sum(column) / rows for column in columns]
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


# ---------------------------------------------------------------------------
# Preprocessing, exactly as preregistered
# ---------------------------------------------------------------------------
def standardize_source_block(source_time, ddof: int = 0) -> dict:
    """Standardise the source transformations over the training issue months.

    Fitted on the source-time matrix **before** it is replicated across
    industries, so every eligible industry receives the identical scaling and
    the location/scale never depends on which industries happen to be present.
    """
    rows = len(source_time)
    if rows <= ddof:
        raise CandidateDesignError(
            f"source standardisation needs more than {ddof} training months"
        )
    columns = _transpose(source_time)
    means = [sum(column) / rows for column in columns]
    deviations = [
        math.sqrt(sum((v - m) ** 2 for v in column) / (rows - ddof))
        for column, m in zip(columns, means, strict=True)
    ]
    constant = [index for index, sd in enumerate(deviations) if sd == 0]
    if constant:
        raise CandidateDesignError(
            f"source columns {constant} are constant over the training issue "
            "months; standardising them would divide by zero, and removing them "
            "is a transformation decision C11 may not take"
        )
    return {
        "matrix": standardize_columns(source_time, ddof),
        "means": means,
        "standard_deviations": deviations,
        "ddof": ddof,
        "training_rows": rows,
        "fitted_on_targets_or_folds": False,
    }


def assert_exposure_centering_source(source: str) -> str:
    """Raise unless the centring mean comes from the frozen structural table.

    Exposure is time-invariant and structurally available before the
    development window, so using the complete frozen eligible-industry vector
    is not target leakage. Recomputing it from a target, a fold or a fitted
    residual would be.
    """
    if str(source) != PERMITTED_CENTERING_SOURCE:
        raise CandidateDesignError(
            f"exposure centring was fitted on {source!r}. The mean must come "
            f"from {PERMITTED_CENTERING_SOURCE!r} — the frozen eleven-industry "
            "structural vector — never from a target, an outcome or a model fold"
        )
    return str(source)


def center_exposures(exposures, eligible,
                     source: str = PERMITTED_CENTERING_SOURCE) -> dict:
    """``e_g = E_g - mean(E)`` over the frozen eligible-industry universe."""
    assert_exposure_centering_source(source)
    missing = [g for g in eligible if g not in exposures]
    if missing:
        raise CandidateDesignError(
            f"no exposure for {sorted(missing)}; the centring universe must be "
            "the complete frozen eligible-industry vector"
        )
    values = [float(exposures[g]) for g in eligible]
    if any(v <= 0 or not math.isfinite(v) for v in values):
        raise CandidateDesignError(
            "every eligible industry needs a strictly positive finite exposure"
        )
    mean = sum(values) / len(values)
    return {g: float(exposures[g]) - mean for g in eligible}


def assert_exposure_varies(centered, tolerance: float = 1e-12) -> float:
    """Raise if centred exposure is constant across the eligible industries.

    A constant exposure makes every centred value zero, so the interaction
    block is a zero matrix. It would still fit, and it would identify nothing.
    """
    values = list(centered.values())
    if not values:
        raise CandidateDesignError("no eligible industry to centre")
    spread = max(values) - min(values)
    if spread <= tolerance:
        raise CandidateDesignError(
            f"centred sector-093 exposure spans {spread!r} across "
            f"{len(values)} industries. With no cross-industry variation the "
            "interaction block is identically zero and cannot identify slope "
            "heterogeneity, whatever a fitted model would report"
        )
    return spread


# ---------------------------------------------------------------------------
# Guards on the design itself
# ---------------------------------------------------------------------------
def assert_single_variant_design(variant_ids, operation: str) -> str:
    """Raise unless exactly one fuel-oil variant is in the design.

    FO 600 and FO 1500 carry the SAME sector-093 exposure vector, so a design
    holding both would use one coefficient twice while presenting it as two
    independent structural channels.
    """
    variants = sorted(set(variant_ids))
    if not variants:
        raise CandidateDesignError(f"{operation!r} names no fuel-oil variant")
    if len(variants) > 1:
        raise CandidateDesignError(
            f"{operation!r} would place {variants} in one design. Both are "
            "conditioned on the same sector-093 exposure vector; they are "
            "co-equal mutually exclusive variants, not independent structural "
            "channels, and no feature diagnostic may choose between them"
        )
    return variants[0]


def assert_main_effect_present(block_names, estimand_changed: bool = False) -> None:
    """Raise if Candidate C drops the common source main effect silently.

    Without ``beta[h,f]`` the interaction no longer measures *deviation from*
    a common fuel-oil association; it becomes the association itself, which is
    a different estimand. Changing the estimand is permitted — doing it by
    deleting a block is not.
    """
    if "source" in set(block_names):
        return
    if not estimand_changed:
        raise CandidateDesignError(
            "Candidate C was built without the common source main effect while "
            "the estimand still reads 'correction amplitude varies around a "
            "common national signal'. Dropping the main effect changes what "
            "theta estimates; declare the new estimand rather than deleting a "
            "block"
        )


def assert_interaction_not_removed(block_names, removed) -> None:
    """Raise if preprocessing dropped the interaction block."""
    if "interaction" not in set(block_names) or removed:
        raise CandidateDesignError(
            f"the interaction block was removed by preprocessing ({sorted(removed)}). "
            "Candidate C exists to carry exposure-associated heterogeneity; a "
            "pipeline that deletes the interaction has silently selected "
            "Candidate A"
        )


def assert_valid_fixed_effect_coding(coding: str, columns: int, rank: int) -> None:
    """Raise on a fixed-effect coding that cannot be identified.

    Eleven industry indicators plus a global intercept sum to the intercept, so
    the design is rank-deficient by exactly one while still reporting
    twenty-two columns — a shape that looks correct in every summary.
    """
    if coding not in FIXED_EFFECT_CODINGS:
        raise CandidateDesignError(f"unknown fixed-effect coding {coding!r}")
    if coding == "global_intercept_plus_industry_indicators":
        raise CandidateDesignError(
            "an intercept alongside a full set of industry indicators is "
            f"rank-deficient: {columns} columns, rank {rank}. Use "
            f"{VALID_FIXED_EFFECT_CODING!r} or reference-industry dummies with "
            "one intercept"
        )
    if rank != columns:
        raise CandidateDesignError(
            f"coding {coding!r} produced {columns} columns at rank {rank}; a "
            "valid coding must be full rank"
        )


# ---------------------------------------------------------------------------
# The designs
# ---------------------------------------------------------------------------
@dataclass
class CandidateDesign:
    """One candidate's FEATURE-ONLY design. No target, ever."""

    variant_id: str
    candidate_id: str
    formula_version: str = CANDIDATE_DESIGN_VERSION
    issue_months: list = field(default_factory=list)
    industries: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    blocks: dict = field(default_factory=dict)
    matrix: list = field(default_factory=list)
    row_keys: list = field(default_factory=list)
    fixed_effect_coding: str = VALID_FIXED_EFFECT_CODING
    centered_exposure: dict = field(default_factory=dict)
    target_columns: int = 0
    prediction_columns: int = 0

    def to_dict(self, include_matrix: bool = False) -> dict:
        payload = asdict(self)
        if not include_matrix:
            payload.pop("matrix")
        return payload

    def block(self, name: str) -> list:
        indices = self.blocks[name]
        return [[row[i] for i in indices] for row in self.matrix]

    def block_columns(self, name: str) -> list:
        return [self.columns[i] for i in self.blocks[name]]

    def combined(self, *names) -> list:
        indices = [i for name in names for i in self.blocks[name]]
        return [[row[i] for i in indices] for row in self.matrix]


def build_candidate_a_design(standardized_source, issue_months, industry_id,
                             variant_id: str) -> CandidateDesign:
    """One industry's design under Candidate A: the common source series only."""
    assert_single_variant_design([variant_id], f"Candidate A for {industry_id}")
    columns = list(SOURCE_COLUMNS)
    return CandidateDesign(
        variant_id=variant_id,
        candidate_id=CANDIDATE_A,
        issue_months=list(issue_months),
        industries=[industry_id],
        columns=columns,
        blocks={"source": list(range(len(columns)))},
        matrix=[list(row) for row in standardized_source],
        row_keys=[(month, industry_id) for month in issue_months],
        fixed_effect_coding="per_industry_intercept",
    )


def build_candidate_b_design(standardized_source, issue_months, industry_id,
                             exposure: float, variant_id: str) -> CandidateDesign:
    """One industry's design under Candidate B: ``E_g`` times the same series."""
    assert_single_variant_design([variant_id], f"Candidate B for {industry_id}")
    if exposure is None or not math.isfinite(float(exposure)) or float(exposure) <= 0:
        raise CandidateDesignError(
            f"{industry_id} needs a strictly positive finite exposure, got "
            f"{exposure!r}"
        )
    scale = float(exposure)
    columns = list(SOURCE_COLUMNS)
    return CandidateDesign(
        variant_id=variant_id,
        candidate_id=CANDIDATE_B,
        issue_months=list(issue_months),
        industries=[industry_id],
        columns=columns,
        blocks={"source": list(range(len(columns)))},
        matrix=[[value * scale for value in row] for row in standardized_source],
        row_keys=[(month, industry_id) for month in issue_months],
        fixed_effect_coding="per_industry_intercept",
    )


def build_candidate_c_design(standardized_source, centered_exposure, issue_months,
                             industries, variant_id: str,
                             coding: str = VALID_FIXED_EFFECT_CODING,
                             estimand_changed: bool = False) -> CandidateDesign:
    """The pooled eligible panel: source, centred interaction, industry effects.

    Rows are ordered industry-major then issue month, so the 165 keys are
    reproducible and the panel can be re-derived independently.
    """
    assert_single_variant_design([variant_id], f"Candidate C for {variant_id}")
    if coding not in FIXED_EFFECT_CODINGS:
        raise CandidateDesignError(f"unknown fixed-effect coding {coding!r}")
    industries = list(industries)
    issue_months = list(issue_months)
    assert_exposure_varies(
        {g: centered_exposure[g] for g in industries}
    )

    source_columns = [f"src__{name}" for name in SOURCE_COLUMNS]
    interaction_columns = [f"int__e093_x_{name}" for name in SOURCE_COLUMNS]
    if coding == "global_intercept_plus_industry_indicators":
        effect_columns = ["fe__intercept"] + [f"fe__{g}" for g in industries]
    elif coding == "reference_industry_dummies_plus_global_intercept":
        effect_columns = ["fe__intercept"] + [f"fe__{g}" for g in industries[1:]]
    else:
        effect_columns = [f"fe__{g}" for g in industries]

    columns = source_columns + interaction_columns + effect_columns
    blocks = {
        "source": list(range(len(source_columns))),
        "interaction": list(range(len(source_columns),
                                  len(source_columns) + len(interaction_columns))),
        "fixed_effects": list(range(len(source_columns) + len(interaction_columns),
                                    len(columns))),
    }
    assert_main_effect_present(blocks, estimand_changed)

    matrix, row_keys = [], []
    for industry in industries:
        exposure = centered_exposure[industry]
        for index, month in enumerate(issue_months):
            source_row = list(standardized_source[index])
            # The interaction is built AFTER source standardisation and is never
            # re-standardised inside the industry.
            interaction_row = [exposure * value for value in source_row]
            if coding == "global_intercept_plus_industry_indicators":
                effects = [1.0] + [
                    1.0 if g == industry else 0.0 for g in industries
                ]
            elif coding == "reference_industry_dummies_plus_global_intercept":
                effects = [1.0] + [
                    1.0 if g == industry else 0.0 for g in industries[1:]
                ]
            else:
                effects = [1.0 if g == industry else 0.0 for g in industries]
            matrix.append(source_row + interaction_row + effects)
            row_keys.append((month, industry))

    return CandidateDesign(
        variant_id=variant_id,
        candidate_id=CANDIDATE_C,
        issue_months=issue_months,
        industries=industries,
        columns=columns,
        blocks=blocks,
        matrix=matrix,
        row_keys=row_keys,
        fixed_effect_coding=coding,
        centered_exposure={g: centered_exposure[g] for g in industries},
    )


# ---------------------------------------------------------------------------
# Identification reports
# ---------------------------------------------------------------------------
def block_ranks(design: CandidateDesign,
                tolerance: float = DEFAULT_RANK_TOLERANCE) -> dict:
    """Rank of each block, of source-plus-interaction, and of the whole design."""
    source = design.block("source")
    interaction = design.block("interaction")
    combined = design.combined("source", "interaction")
    return {
        "source_block_rank": numerical_rank(source, tolerance),
        "interaction_block_rank": numerical_rank(interaction, tolerance),
        "combined_source_and_interaction_rank": numerical_rank(combined, tolerance),
        "fixed_effect_block_rank": numerical_rank(
            design.block("fixed_effects"), tolerance
        ),
        "full_design_rank": numerical_rank(design.matrix, tolerance),
        "full_design_columns": len(design.columns),
        "rows": len(design.matrix),
        "rank_tolerance": tolerance,
    }


def _tolerance_classes(blocks, tolerance: float) -> int:
    """Count distinct matrices at an absolute tolerance, not by rounding.

    C10 established that a rounded significant-digit fingerprint can split
    matrices that agree to 1e-15, so the count that decides anything here is
    tolerance-based.
    """
    classes = []
    for block in blocks:
        for representative in classes:
            gap = max(
                abs(a - b)
                for row_a, row_b in zip(representative, block, strict=True)
                for a, b in zip(row_a, row_b, strict=True)
            )
            if gap <= tolerance:
                break
        else:
            classes.append(block)
    return len(classes)


def per_industry_standardised_collapse(
    design: CandidateDesign, tolerance: float = DEFAULT_RANK_TOLERANCE,
    equivalence_tolerance: float = 1e-9,
) -> dict:
    """What per-industry standardisation of the interaction would destroy.

    Within industry ``g`` the interaction is ``e_g x̃``, so standardising it
    inside that industry returns ``sign(e_g) · x̃``: the interaction column
    becomes collinear with the source column and the industry's combined block
    falls from rank ten to rank five.

    Stacking the industries does **not** show that as a global rank drop,
    because the centred exposures carry both signs and ``+x̃`` and ``-x̃`` span
    two directions. What is destroyed is the *magnitude*: eleven distinct
    exposure-proportional interaction blocks collapse to two sign groups, so
    ``theta`` could only be identified up to a two-group split rather than as an
    exposure-proportional pattern. Both measurements are reported, because the
    per-industry rank alone understates the loss and the stacked rank alone
    hides it.
    """
    source_indices = design.blocks["source"]
    interaction_indices = design.blocks["interaction"]
    width = len(source_indices)

    per_industry_rank, collapsed_rows, collapsed_blocks = {}, [], []
    intended_blocks, sign_residual = [], 0.0
    for industry in design.industries:
        rows = [
            row for key, row in zip(design.row_keys, design.matrix, strict=True)
            if key[1] == industry
        ]
        block = [
            [row[i] for i in source_indices] + [row[i] for i in interaction_indices]
            for row in rows
        ]
        intended_blocks.append([[row[i] for i in interaction_indices] for row in rows])
        standardized = standardize_columns(block, 0)
        per_industry_rank[industry] = numerical_rank(standardized, tolerance)
        collapsed_rows.extend(standardized)
        collapsed_blocks.append([row[width:] for row in standardized])
        # sign(e_g) * standardised source should reproduce the standardised
        # interaction exactly; this is the identity the collapse rests on.
        sign = 1.0 if design.centered_exposure[industry] > 0 else -1.0
        sign_residual = max(
            sign_residual,
            max(abs(row[width + i] - sign * row[i]) for row in standardized
                for i in range(width)),
        )

    intended = numerical_rank(design.combined("source", "interaction"), tolerance)
    intended_patterns = _tolerance_classes(intended_blocks, equivalence_tolerance)
    collapsed_patterns = _tolerance_classes(collapsed_blocks, equivalence_tolerance)
    ranks = sorted(set(per_industry_rank.values()))
    return {
        "intended_combined_rank": intended,
        "per_industry_combined_ranks": ranks,
        "per_industry_combined_rank_by_industry": per_industry_rank,
        "stacked_per_industry_standardized_combined_rank": numerical_rank(
            collapsed_rows, tolerance
        ),
        "distinct_intended_interaction_blocks": intended_patterns,
        "distinct_collapsed_interaction_blocks": collapsed_patterns,
        "sign_identity_residual": sign_residual,
        "per_industry_rank_lost": intended - max(ranks),
        "interaction_magnitudes_lost": intended_patterns - collapsed_patterns,
        "heterogeneity_collapses": (
            max(ranks) < intended and collapsed_patterns < intended_patterns
        ),
        "reason": (
            "Within industry g the interaction is e_g * xtilde, so per-industry "
            "standardisation returns sign(e_g) * standardize(xtilde) and that "
            "industry's combined block falls to rank "
            f"{max(ranks)} from {intended}. Stacking the industries does NOT "
            "show a global rank drop, because the centred exposures carry both "
            "signs and +xtilde and -xtilde span two directions. What is "
            f"destroyed is the magnitude: {intended_patterns} distinct "
            f"exposure-proportional interaction blocks collapse to "
            f"{collapsed_patterns} sign groups. The preprocessing contract "
            "therefore forbids standardising the interaction inside an industry."
        ),
    }


def constant_exposure_interaction_report(
    design: CandidateDesign, standardized_source, issue_months,
    tolerance: float = DEFAULT_RANK_TOLERANCE
) -> dict:
    """What the interaction block becomes when exposure does not vary.

    Built by replacing every exposure with one constant, which centres to
    exactly zero. The block is then a zero matrix of rank zero — the design
    would still fit and would identify nothing.
    """
    constant = {g: 0.0 for g in design.industries}
    block = [
        [constant[industry] * value for value in standardized_source[index]]
        for industry in design.industries
        for index, _ in enumerate(issue_months)
    ]
    return {
        "constant_exposure_interaction_rank": numerical_rank(block, tolerance),
        "all_zero": all(value == 0.0 for row in block for value in row),
        "identifies_heterogeneity": False,
        "reason": (
            "A constant exposure centres to zero for every industry, so the "
            "interaction block is identically zero. Reporting it as identifying "
            "slope heterogeneity would describe a column of zeros as evidence."
        ),
    }


def candidate_b_equivalence_report(candidate_a: CandidateDesign,
                                   candidate_b: CandidateDesign,
                                   exposure: float,
                                   tolerance: float = 1e-9) -> dict:
    """Show that Candidate B is Candidate A reparameterised, for one industry.

    Two demonstrations, because either alone is weaker than the pair: the
    column-space projectors coincide (so no data can prefer one), and the
    coefficient map ``gamma = beta / E_g`` recovers the other exactly.
    """
    if candidate_a.candidate_id != CANDIDATE_A:
        raise CandidateDesignError("the first design must be Candidate A")
    if candidate_b.candidate_id != CANDIDATE_B:
        raise CandidateDesignError("the second design must be Candidate B")
    scale = float(exposure)
    if scale <= 0:
        raise CandidateDesignError("Candidate B needs a positive exposure")

    projection_a = column_space_projection(candidate_a.matrix)
    projection_b = column_space_projection(candidate_b.matrix)
    projector_gap = max(
        abs(a - b)
        for row_a, row_b in zip(projection_a, projection_b, strict=True)
        for a, b in zip(row_a, row_b, strict=True)
    )
    rescaled_gap = max(
        abs(b - scale * a)
        for row_a, row_b in zip(candidate_a.matrix, candidate_b.matrix, strict=True)
        for a, b in zip(row_a, row_b, strict=True)
    )
    standardized_gap = max(
        abs(a - b)
        for row_a, row_b in zip(standardize_columns(candidate_a.matrix),
                                standardize_columns(candidate_b.matrix), strict=True)
        for a, b in zip(row_a, row_b, strict=True)
    )
    return {
        "industry_id": candidate_a.industries[0],
        "exposure": scale,
        "column_space_projector_max_gap": projector_gap,
        "column_spaces_coincide": projector_gap <= tolerance,
        "exact_column_rescaling_max_gap": rescaled_gap,
        "is_exact_column_rescaling": rescaled_gap <= tolerance * max(1.0, scale),
        "per_industry_standardized_max_gap": standardized_gap,
        "per_industry_standardization_removes_exposure": standardized_gap <= tolerance,
        "coefficient_map": "gamma[g,h,f] = beta[g,h,f] / E[g]",
        "separate_conditioned_model_is_distinct_architecture": False,
        "reason": (
            "Within one industry E_g is a positive scalar, so E_g x spans the "
            "same column space as x. The two designs are the same design in "
            "different coordinates: no data can distinguish them, and only the "
            "printed coefficients differ."
        ),
    }


def design_checksum(design: CandidateDesign, digits: int = 12) -> str:
    """Digest of a candidate design's shape, keys, blocks and values."""
    import hashlib
    import json

    payload = {
        "formula_version": design.formula_version,
        "variant_id": design.variant_id,
        "candidate_id": design.candidate_id,
        "issue_months": design.issue_months,
        "industries": design.industries,
        "columns": design.columns,
        "blocks": {k: list(v) for k, v in sorted(design.blocks.items())},
        "fixed_effect_coding": design.fixed_effect_coding,
        "row_keys": [list(key) for key in design.row_keys],
        "centered_exposure": {
            g: f"{v:.{digits}e}" for g, v in sorted(design.centered_exposure.items())
        },
        "matrix": [[f"{v:.{digits}e}" for v in row] for row in design.matrix],
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
