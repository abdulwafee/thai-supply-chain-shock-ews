"""Target publication-timing contract and its consequence for B4 (Task D2).

Two lags are separate facts and are stored separately:

* **publication lag** -- days from the end of reference month *t* until OIE first
  publishes *t*.
* **availability lag in months** -- how many whole months must pass before *t*
  is usable at a forecast origin. This is the number a modelling protocol
  consumes, and it is derived from the publication lag, never assumed.

The consequence matters. B4 built its baselines assuming current-month stress is
known at forecast origin *t*. If OIE first publishes month *t* near the end of
month *t+1*, that assumption is false: at origin *t* the most recent published
month is *t-1*. :func:`evaluate_b4_assumption` states that plainly.

This module records the finding. It does not change the B4 split, rebuild
targets, or rerun a model -- D2 is an audit, and the remedy is a later decision
that must be made deliberately rather than as a side effect of measuring.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

__all__ = [
    "TimingContract",
    "evaluate_b4_assumption",
    "build_timing_contract",
]


@dataclass
class TimingContract:
    months_with_credible_evidence: int = 0
    months_total: int = 0
    evidence_class_counts: dict = field(default_factory=dict)
    coverage_start: str = None
    coverage_end: str = None
    credible_coverage_start: str = None
    credible_coverage_end: str = None
    publication_lag_days_min: int = None
    publication_lag_days_max: int = None
    publication_lag_days_median: float = None
    publication_lag_days_mean: float = None
    publishes_in_month_after_reference: bool = None
    availability_lag_months: int = None
    same_month_availability_supported: bool = False
    required_window_start: str = None
    required_window_end: str = None
    required_window_fully_evidenced: bool = False
    required_window_missing_months: list = field(default_factory=list)
    directly_observed_release: dict = None
    marker_semantics_documented: bool = False
    marker_note: str = None
    contract_status: str = "unresolved"
    blockers: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def build_timing_contract(
    records,
    required_window_start,
    required_window_end,
    directly_observed=None,
    marker_months=(),
):
    """Derive the publication-timing contract from classified release records."""
    from .oie_mpi_release_inventory import month_end  # local import: avoids cycle

    contract = TimingContract()
    contract.months_total = len(records)

    counts = {}
    for record in records:
        counts[record.timing_evidence_class] = counts.get(record.timing_evidence_class, 0) + 1
    contract.evidence_class_counts = dict(sorted(counts.items()))

    months = sorted(r.reference_month for r in records if r.reference_month)
    if months:
        contract.coverage_start, contract.coverage_end = months[0], months[-1]

    credible = [
        r
        for r in records
        if r.first_publication_is_credible
        and r.reference_month
        and r.publication_lag_days is not None
    ]
    contract.months_with_credible_evidence = len(credible)
    if credible:
        credible_months = sorted(r.reference_month for r in credible)
        contract.credible_coverage_start = credible_months[0]
        contract.credible_coverage_end = credible_months[-1]
        lags = [r.publication_lag_days for r in credible]
        contract.publication_lag_days_min = min(lags)
        contract.publication_lag_days_max = max(lags)
        contract.publication_lag_days_median = statistics.median(lags)
        contract.publication_lag_days_mean = statistics.fmean(lags)

        # Does first publication of month t land inside month t+1?
        in_next_month = []
        for record in credible:
            estimate = record.first_publication_estimate_utc
            if not estimate:
                continue
            month_end(record.reference_month)
            days = (
                record.publication_lag_days
                if record.publication_lag_days is not None
                else None
            )
            if days is None:
                continue
            in_next_month.append(0 < days <= 62)
        contract.publishes_in_month_after_reference = (
            all(in_next_month) if in_next_month else None
        )

        # A month published after its own month has ended is never available
        # within that month. One whole month must pass.
        contract.availability_lag_months = 1 if contract.publication_lag_days_min > 0 else 0
        contract.same_month_availability_supported = contract.publication_lag_days_min <= 0

    contract.required_window_start = required_window_start
    contract.required_window_end = required_window_end
    evidenced = {r.reference_month for r in credible}
    from .oie_mpi_history import month_sequence

    required = month_sequence(required_window_start, required_window_end)
    missing = [m for m in required if m not in evidenced]
    contract.required_window_missing_months = missing
    contract.required_window_fully_evidenced = not missing

    if directly_observed:
        contract.directly_observed_release = directly_observed

    # The workbook marks its newest month with a glyph but carries no legend for
    # it anywhere in the file. Observed behaviour is recorded; the meaning is not
    # asserted, because no OIE document consulted in this audit defines it.
    contract.marker_semantics_documented = False
    if marker_months:
        contract.marker_note = (
            "The live workbook marks its newest reference month ({}) with a "
            "trailing glyph, and the marker moves to the next month on the "
            "following release while the previous month keeps a value. No legend "
            "for the glyph appears in the workbook, so its meaning is recorded as "
            "observed behaviour, not asserted as a preliminary flag."
            .format(", ".join(marker_months))
        )

    blockers = []
    if not contract.required_window_fully_evidenced:
        blockers.append(
            f"{len(missing)} month(s) in the required window lack credible "
            "first-publication evidence"
        )
    if contract.publication_lag_days_median is None:
        blockers.append("no credible publication lag could be measured")
    contract.blockers = blockers
    contract.contract_status = "resolved" if not blockers else "unresolved"
    return contract


def evaluate_b4_assumption(contract):
    """State whether B4's current-month-stress assumption survives the evidence."""
    if contract.availability_lag_months is None:
        return {
            "b4_assumption": "current-month stress is known at forecast origin t",
            "assumption_status": "not_evaluated",
            "reason": "no credible publication lag was measured",
            "b4_split_changed": False,
        }
    holds = contract.same_month_availability_supported
    return {
        "b4_assumption": "current-month stress is known at forecast origin t",
        "assumption_status": "holds" if holds else "violated",
        "measured_availability_lag_months": contract.availability_lag_months,
        "measured_publication_lag_days_median": contract.publication_lag_days_median,
        "explanation": (
            "OIE first publishes reference month t a median of "
            f"{contract.publication_lag_days_median} days after the end "
            "of t, i.e. during month t+1. At forecast origin t the most recent "
            "published reference month is therefore t-1, not t."
        )
        if not holds
        else "Publication occurs within the reference month itself.",
        "affects_b4_baselines": not holds,
        "affects_d1_feature_assembly": not holds,
        "b4_split_changed": False,
        "remedy_deferred": True,
        "remedy_note": (
            "D2 is an audit. The split, the targets and the D1 models are left "
            "untouched; correcting the assumption is a separate, deliberate decision."
        ),
    }
