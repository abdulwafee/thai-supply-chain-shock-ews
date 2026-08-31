"""Pooled fuel-oil panel assembly under the operational contract (Task D5).

Builds, for one variant, one horizon and one outer issue month ``t``, the
training panel the live system could actually have had at ``t``:

* every historical training issue ``u`` whose **label** was published by ``t``,
* whose **feature** reference month ``u-2`` carries all five transformations,
* and whose **benchmark** history was complete at ``u``.

Four ways this can silently go wrong, all refused here.

**A refreshed historical feature.** The row for training issue ``u`` must carry
the fuel-oil values as they stood at ``u`` — reference month ``u-2`` — not the
latest ones available at the outer issue ``t``. Re-reading a feature at ``t``
gives the past model information from its own future, and every metric
downstream still looks ordinary. :func:`assert_feature_frozen_at_issue` checks
the recorded reference month against ``u`` rather than against ``t``.

**A scaler fitted on the repeated panel.** The 11 industries share one source
series, so fitting mean and standard deviation on 231 stacked rows weights that
series 11 times and reports a sample size it does not have. The scaler is fitted
on the **unique** training issue months and then applied to every industry.

**An imputed source value.** An absent transformation is absent. Filling it
produces a training row that never existed, and the count reconciliation would
still balance.

**IND-04 in the fitted panel.** Its direction is unresolved, not zero. It is
excluded from the fit and carried through the benchmark instead, and
:func:`assert_ind_04_excluded` raises if it reaches the design.

Nothing here reads a target value. Residuals are supplied by the caller after
the labels have passed their own availability check.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

__all__ = [
    "IND_04",
    "POLICY_LAG_MONTHS",
    "SOURCE_COLUMNS",
    "PanelAssemblyError",
    "PooledPanel",
    "assert_all_eligible_industries_present",
    "assert_feature_frozen_at_issue",
    "assert_ind_04_excluded",
    "assert_no_imputation",
    "assert_reference_month_not_later_than",
    "build_pooled_design",
    "center_and_scale_exposure",
    "fit_source_scaler",
    "shift_month",
]

#: Column order is fixed and matches C8/C10/C11 so a diagnostic that depends on
#: ordering cannot shift under a rename.
SOURCE_COLUMNS = (
    "log_change_12m_pct",
    "log_change_1m_pct",
    "log_change_3m_pct",
    "price_level",
    "realized_volatility_3m_pct",
)

POLICY_LAG_MONTHS = 2
IND_04 = "IND-04"


class PanelAssemblyError(ValueError):
    """A temporal or structural rule of the pooled assembly was violated."""


def shift_month(month: str, delta: int) -> str:
    year, index = int(str(month)[:4]), int(str(month)[5:7])
    total = year * 12 + (index - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ---------------------------------------------------------------------------
# Temporal guards
# ---------------------------------------------------------------------------
def assert_feature_frozen_at_issue(issue_month: str, reference_month: str,
                                   lag: int = POLICY_LAG_MONTHS) -> None:
    """Raise unless a row's feature is the one available at its OWN issue month.

    Checked against the recorded reference month, never inferred by shifting
    rows: a positional shift reproduces the right answer on a complete table and
    hides the error on an incomplete one.
    """
    expected = shift_month(str(issue_month)[:7], -lag)
    actual = str(reference_month)[:7]
    if actual != expected:
        raise PanelAssemblyError(
            f"issue month {issue_month} carries feature reference month {actual}, "
            f"but the {lag}-month policy lag requires {expected}. A historical "
            "training row must hold the values available at its own issue month, "
            "not the latest ones available at the outer origin"
        )


def assert_reference_month_not_later_than(reference_month: str,
                                          outer_issue: str,
                                          lag: int = POLICY_LAG_MONTHS) -> None:
    """Raise if any feature is later than ``t - lag`` for the outer issue ``t``."""
    ceiling = shift_month(str(outer_issue)[:7], -lag)
    if str(reference_month)[:7] > ceiling:
        raise PanelAssemblyError(
            f"feature reference month {reference_month} is later than {ceiling}, "
            f"the latest month available at outer issue {outer_issue}"
        )


def assert_no_imputation(values, issue_month: str, industry_id: str) -> None:
    """Raise if any source value is absent. Absent is absent."""
    missing = [
        name for name, value in zip(SOURCE_COLUMNS, values, strict=True)
        if value is None or not np.isfinite(float(value))
    ]
    if missing:
        raise PanelAssemblyError(
            f"{industry_id} at issue {issue_month} is missing {sorted(missing)}. "
            "An unavailable source value is not imputed: a filled row is a "
            "training row that never existed, and the counts would still balance"
        )


def assert_ind_04_excluded(industry_ids, where: str) -> None:
    """Raise if IND-04 reaches the fitted panel."""
    if IND_04 in set(industry_ids):
        raise PanelAssemblyError(
            f"{IND_04} entered {where}. Its direction is mixed_or_ambiguous - "
            "unresolved, not zero - so it is excluded from the fit and carried "
            "through the registered benchmark instead"
        )


def assert_all_eligible_industries_present(industry_ids, eligible,
                                           issue_month: str) -> None:
    """Raise unless every eligible industry is present for an accepted issue.

    A partially populated issue month would make the pooled fit weight that
    month by however many industries happened to survive.
    """
    present = sorted(set(industry_ids))
    missing = sorted(set(eligible) - set(present))
    extra = sorted(set(present) - set(eligible))
    if missing or extra:
        raise PanelAssemblyError(
            f"training issue {issue_month} has industries {present}; expected "
            f"exactly the {len(eligible)} eligible ones "
            f"(missing {missing}, unexpected {extra})"
        )


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------
def fit_source_scaler(source_by_issue: dict, ddof: int = 0) -> dict:
    """Fit mean and standard deviation on the UNIQUE training issue months.

    ``source_by_issue`` maps issue month to that month's five source values, so
    each month contributes once regardless of how many industries repeat it.
    Fitting on the stacked panel instead would weight one series eleven times.
    """
    months = sorted(source_by_issue)
    if not months:
        raise PanelAssemblyError("no training issue months to fit the scaler on")
    matrix = np.array([source_by_issue[m] for m in months], dtype=float)
    if matrix.shape[0] <= ddof:
        raise PanelAssemblyError(
            f"source scaling with ddof={ddof} needs more than {ddof} issue months"
        )
    means = matrix.mean(axis=0)
    deviations = matrix.std(axis=0, ddof=ddof)
    degenerate = [
        SOURCE_COLUMNS[j] for j, sd in enumerate(deviations)
        if not np.isfinite(sd) or sd <= 0
    ]
    if degenerate:
        raise PanelAssemblyError(
            f"source predictors {sorted(degenerate)} have zero or invalid "
            "training variance over the unique issue months"
        )
    return {
        "issue_months": months,
        "unique_issue_month_count": len(months),
        "fitted_on_repeated_industry_panel": False,
        "ddof": int(ddof),
        "means": [float(v) for v in means],
        "standard_deviations": [float(v) for v in deviations],
        "columns": list(SOURCE_COLUMNS),
    }


def center_and_scale_exposure(exposures, eligible) -> dict:
    """``e_z[g] = (E[g] - mean(E)) / sd(E)`` over the frozen eligible universe.

    The scaling is a fixed column reparameterisation for numerical conditioning.
    It multiplies the interaction column by a constant and divides ``theta`` by
    the same constant, so the fitted interaction is unchanged and the C11
    estimand is untouched. Raw and centred values are both returned, because
    lineage has to be able to show what was divided by what.
    """
    missing = [g for g in eligible if g not in exposures]
    if missing:
        raise PanelAssemblyError(
            f"no sector-093 exposure for {sorted(missing)}; the centring universe "
            "must be the complete frozen eligible-industry vector"
        )
    raw = {g: float(exposures[g]) for g in eligible}
    if any(v <= 0 or not np.isfinite(v) for v in raw.values()):
        raise PanelAssemblyError(
            "every eligible industry needs a strictly positive finite exposure"
        )
    values = np.array([raw[g] for g in eligible], dtype=float)
    mean = float(values.mean())
    centered = {g: raw[g] - mean for g in eligible}
    deviation = float(np.array(list(centered.values())).std(ddof=0))
    if not np.isfinite(deviation) or deviation <= 0:
        raise PanelAssemblyError(
            f"centred sector-093 exposure has standard deviation {deviation!r}; "
            "with no cross-industry variation the interaction identifies nothing"
        )
    return {
        "raw_exposure": raw,
        "mean": mean,
        "centered_exposure": centered,
        "structural_standard_deviation": deviation,
        "scaled_exposure": {g: centered[g] / deviation for g in eligible},
        "centering_universe": "eleven_eligible_industries",
        "centering_source": "c9_phase_a_frozen_decision_table",
        "fitted_on_targets": False,
        "scaling_is_a_fixed_column_reparameterization": True,
        "changes_the_c11_estimand": False,
    }


# ---------------------------------------------------------------------------
# The design
# ---------------------------------------------------------------------------
@dataclass
class PooledPanel:
    """One (variant, horizon, outer issue) training design. Feature-side only."""

    variant_id: str
    horizon: int
    outer_issue: str
    eligible_industries: tuple = ()
    training_issue_months: tuple = ()
    column_names: tuple = ()
    blocks: tuple = ()
    matrix: np.ndarray = None
    row_keys: tuple = ()
    scaler: dict = field(default_factory=dict)
    exposure: dict = field(default_factory=dict)
    all_industry_rows: int = 0
    eligible_rows: int = 0
    omitted_ind_04_rows: int = 0
    excluded_issue_months: dict = field(default_factory=dict)
    imputed_values: int = 0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload.pop("matrix")
        return payload


def build_pooled_design(rows, eligible, scaler, exposure, variant_id: str,
                        horizon: int, outer_issue: str) -> PooledPanel:
    """Assemble the pooled design: source, centred interaction, industry effects.

    ``rows`` is an iterable of dicts carrying ``issue_month``, ``industry_id``,
    ``reference_month`` and the five raw source values. Every temporal rule is
    asserted per row rather than assumed from the caller's filtering.
    """
    eligible = list(eligible)
    assert_ind_04_excluded(eligible, "the eligible-industry list")
    ordered = sorted(rows, key=lambda r: (r["industry_id"], r["issue_month"]))
    by_issue = {}
    for row in ordered:
        by_issue.setdefault(row["issue_month"], []).append(row["industry_id"])
    for issue_month, industries in by_issue.items():
        assert_all_eligible_industries_present(industries, eligible, issue_month)

    source_columns = [f"src__{name}" for name in SOURCE_COLUMNS]
    interaction_columns = [f"int__e093z_x_{name}" for name in SOURCE_COLUMNS]
    effect_columns = [f"fe__{g}" for g in eligible]
    column_names = tuple(source_columns + interaction_columns + effect_columns)
    blocks = tuple(
        ["source"] * len(source_columns)
        + ["interaction"] * len(interaction_columns)
        + ["industry_fixed_effect"] * len(effect_columns)
    )

    means = np.array(scaler["means"], dtype=float)
    deviations = np.array(scaler["standard_deviations"], dtype=float)
    scaled = exposure["scaled_exposure"]

    matrix, row_keys = [], []
    for row in ordered:
        industry_id = row["industry_id"]
        assert_ind_04_excluded([industry_id], "the pooled training design")
        assert_feature_frozen_at_issue(row["issue_month"], row["reference_month"])
        assert_reference_month_not_later_than(row["reference_month"], outer_issue)
        values = [row[name] for name in SOURCE_COLUMNS]
        assert_no_imputation(values, row["issue_month"], industry_id)
        standardized = (np.array(values, dtype=float) - means) / deviations
        # The interaction is built AFTER source standardisation and is never
        # re-standardised inside the industry.
        interaction = scaled[industry_id] * standardized
        effects = [1.0 if g == industry_id else 0.0 for g in eligible]
        matrix.append(list(standardized) + list(interaction) + effects)
        row_keys.append((row["issue_month"], industry_id))

    return PooledPanel(
        variant_id=variant_id,
        horizon=int(horizon),
        outer_issue=str(outer_issue),
        eligible_industries=tuple(eligible),
        training_issue_months=tuple(sorted(by_issue)),
        column_names=column_names,
        blocks=blocks,
        matrix=np.array(matrix, dtype=float) if matrix else np.zeros((0, len(blocks))),
        row_keys=tuple(row_keys),
        scaler=scaler,
        exposure=exposure,
        all_industry_rows=len(by_issue) * (len(eligible) + 1),
        eligible_rows=len(matrix),
        omitted_ind_04_rows=len(by_issue),
        imputed_values=0,
    )
