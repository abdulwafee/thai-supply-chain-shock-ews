"""Operational forecast-origin contract (Task D3).

B4 evaluated at forecast origin *t* using stress month *t*. D2 established that
OIE first publishes reference month *t* a median 29 days after *t* ends, so that
value did not exist when the forecast was supposedly issued. B4 and D1 are kept
and remain reproducible, but as **non-operational calendar-boundary
experiments**; this module defines the release-aware replacement.

Seven concepts are kept distinct, because collapsing any two of them is exactly
how the original error entered:

===========================  ==================================================
reference month              the month an MPI value describes
publication date             the date OIE first published that value
publication month            the calendar month containing that date
forecast issue month  (*t*)  the month the forecast is issued in
latest observable stress     *t-1* — the newest month published by issue time
target month / window        *t+1*, or *t+1..t+3*
target availability month    ``target_window_end + 1``
===========================  ==================================================

The forecast is issued **near the end of month t**, after OIE publishes month
*t-1*. It is not a nowcast of month *t*: month *t* is unobserved at issue time,
is never predicted, and is simply skipped over.

Every guard here raises. Nothing degrades quietly to a "safe" value, because a
quiet degradation is indistinguishable from the bug it is meant to prevent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from thai_supply_chain_ews.evaluation.splits import add_months


def month_label(iso_month) -> str:
    """``YYYY-MM-01`` -> ``YYYY-MM``, for reports and config comparisons."""
    return str(iso_month)[:7]

__all__ = [
    "DEFAULT_OPERATIONAL_CONFIG_PATH",
    "CurrentMonthStressError",
    "LockedOriginError",
    "OperationalContractError",
    "OriginContract",
    "ReleaseTimingError",
    "UnresolvedReleaseError",
    "build_origin_contracts",
    "default_release_inventory_path",
    "load_operational_config",
    "load_release_index",
    "month_label",
    "release_inventory_checksum",
]

DEFAULT_OPERATIONAL_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "operational_evaluation.yaml"
)


class OperationalContractError(ValueError):
    """Base class for a violation of the operational forecast-origin contract."""


class UnresolvedReleaseError(OperationalContractError):
    """No credible OIE release date is available for the required month."""


class ReleaseTimingError(OperationalContractError):
    """A release date does not sit where the contract requires it to sit."""


class CurrentMonthStressError(OperationalContractError):
    """Stress month t (or later) was requested at forecast issue month t."""


class LockedOriginError(OperationalContractError):
    """A locked-test origin reached the operational evaluation path."""


def load_operational_config(path=None) -> dict:
    target = Path(path) if path is not None else DEFAULT_OPERATIONAL_CONFIG_PATH
    with open(target, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def default_release_inventory_path() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "docs" / "d2_oie_mpi_source_audit.json"
    )


def load_release_index(path=None) -> dict:
    """Map reference month -> verified D2 release record.

    Only records D2 classified as credible are admitted. A month whose only
    evidence is a migration batch timestamp has no usable release date, and this
    returns nothing for it rather than a plausible-looking guess.
    """
    target = Path(path) if path is not None else default_release_inventory_path()
    with open(target, encoding="utf-8") as handle:
        audit = json.load(handle)
    index = {}
    for record in audit["release_inventory"]["records"]:
        month = record.get("reference_month")
        if not month or not record.get("first_publication_is_credible"):
            continue
        estimate = record.get("first_publication_estimate_utc")
        if not estimate:
            continue
        index[month + "-01"] = {
            "reference_month": month + "-01",
            "release_datetime_utc": estimate,
            "release_date": estimate[:10],
            "publication_month": estimate[:7],
            "timing_evidence_class": record.get("timing_evidence_class"),
            "publication_lag_days": record.get("publication_lag_days"),
        }
    return index


def release_inventory_checksum(path=None) -> str:
    """Checksum of the D2 evidence this contract depends on."""
    import hashlib

    target = Path(path) if path is not None else default_release_inventory_path()
    with open(target, encoding="utf-8") as handle:
        audit = json.load(handle)
    payload = json.dumps(
        audit["release_inventory"]["records"], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OriginContract:
    """The information boundary at one forecast issue month."""

    forecast_origin_month: str
    forecast_issue_date: str
    forecast_issue_datetime_utc: str
    latest_available_stress_month: str
    calibration_reference_end: str
    release_reference_month: str
    publication_month: str
    publication_lag_days: int
    timing_evidence_class: str
    target_months: dict = field(default_factory=dict)
    split_name: str = None

    def target_window(self, horizon: int):
        start, end = self.target_months[int(horizon)]
        return start, end

    def assert_stress_month_permitted(self, stress_month: str) -> None:
        """Reject any stress month the issue date could not have seen."""
        if stress_month > self.latest_available_stress_month:
            raise CurrentMonthStressError(
                f"stress month {stress_month} is not published at forecast issue "
                f"month {self.forecast_origin_month} (issued "
                f"{self.forecast_issue_date}; latest published reference month "
                f"is {self.latest_available_stress_month})"
            )

    def to_dict(self) -> dict:
        return asdict(self)


def build_origin_contracts(
    origins,
    config,
    release_index,
    plan=None,
) -> dict:
    """Build and validate one contract per forecast issue month.

    Raises on any origin whose release evidence does not satisfy the contract.
    Locked origins are rejected here, at the contract layer, so no later filter
    is load-bearing.
    """
    contract_config = config["forecast_origin_contract"]
    horizons = {int(k): v for k, v in contract_config["horizons"].items()}
    locked = _locked_month_set(config)

    contracts = {}
    for origin in origins:
        month = str(origin)
        if month_label(month) in locked:
            raise LockedOriginError(
                f"origin {month} belongs to the locked final test and cannot be evaluated"
            )

        required_reference = add_months(month, -1)
        record = release_index.get(required_reference)
        if record is None:
            raise UnresolvedReleaseError(
                f"no credible OIE release date for reference month "
                f"{required_reference}, required to issue a forecast at {month}"
            )
        if record["reference_month"] != required_reference:
            raise ReleaseTimingError(
                "release record for issue month {} describes reference month {}, "
                "expected {}".format(month, record["reference_month"], required_reference)
            )
        if record["publication_month"] != month_label(month):
            raise ReleaseTimingError(
                "reference month {} was published in {}, not during issue month {}; "
                "the forecast could not have been issued as specified".format(
                    required_reference, record["publication_month"], month
                )
            )

        target_months = {}
        for horizon, spec in horizons.items():
            start = add_months(month, int(spec["target_window_start_offset"]))
            end = add_months(month, int(spec["target_window_end_offset"]))
            target_months[horizon] = (start, end)

        contracts[month] = OriginContract(
            forecast_origin_month=month,
            forecast_issue_date=record["release_date"],
            forecast_issue_datetime_utc=record["release_datetime_utc"],
            latest_available_stress_month=required_reference,
            calibration_reference_end=required_reference,
            release_reference_month=required_reference,
            publication_month=record["publication_month"],
            publication_lag_days=record["publication_lag_days"],
            timing_evidence_class=record["timing_evidence_class"],
            target_months=target_months,
            split_name=plan.block_for_origin(origin) if plan is not None else None,
        )
    return contracts


def assert_issue_date_not_before_release(contract: OriginContract, release_index) -> None:
    """A forecast may not be issued before the release it claims to follow."""
    record = release_index.get(contract.release_reference_month)
    if record is None:
        raise UnresolvedReleaseError(
            f"no release record for {contract.release_reference_month}"
        )
    if contract.forecast_issue_date < record["release_date"]:
        raise ReleaseTimingError(
            "issue date {} precedes the OIE release of {} on {}".format(
                contract.forecast_issue_date,
                contract.release_reference_month,
                record["release_date"],
            )
        )


def _locked_month_set(config) -> set:
    locked = set()
    for spec in config["split"]["locked_test"]["horizons"].values():
        month = spec["start"] + "-01"
        while month_label(month) <= spec["end"]:
            locked.add(month_label(month))
            month = add_months(month, 1)
    return locked


def locked_month_set(config) -> set:
    """Public view of the reserved months, for manifests and assertions."""
    return set(_locked_month_set(config))


def purge_month_set(config) -> set:
    purge = config["split"]["purge"]
    months, month = set(), purge["start"]
    while month <= purge["end"]:
        months.add(month)
        month = add_months(month + "-01", 1)[:7]
    return months
