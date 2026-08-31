"""Availability of EPPO source transformations at a forecast issue month (C8).

A transformation reads several source months, so its availability is the
availability of its *latest* input — not of its reference month. Under the
two-month policy both happen to coincide at ``m + 2``, and that coincidence is
verified here rather than assumed: :func:`transformation_policy_available_month`
takes the maximum over the declared window and
:func:`assert_policy_month_matches_reference_rule` checks the equality, so a
formula that ever reaches forward would be caught instead of silently inheriting
its reference month's stamp.

Two fields stay apart, exactly as they have since C6.5. ``source_available_as_of``
means the source is *evidenced* to have been public by a date, and it is ``None``
for every EPPO observation because that timing was never measured.
``policy_available_month`` is the conservative assumption the project imposes.
Turning the second into the first would manufacture a release date, so
:func:`assert_policy_month_is_not_a_release_date` refuses it.

The selector returns only numeric rows for exactly one channel. Both fuel oils
read one I/O sector coefficient, so a request naming both is refused rather than
served and filtered later.
"""

from __future__ import annotations

from thai_supply_chain_ews.features.eppo_fuel_oil_transformations import (
    SERIES_BY_CHANNEL,
    TransformationError,
    assert_single_fuel_oil_channel,
    shift_month,
)

__all__ = [
    "AVAILABILITY_BASIS",
    "AVAILABILITY_POLICY_VERSION",
    "OPERATIONAL_POLICY_LAG_MONTHS",
    "AvailabilityPolicyError",
    "assert_policy_month_is_not_a_release_date",
    "assert_policy_month_matches_reference_rule",
    "issue_key_coverage",
    "latest_permitted_reference_month",
    "select_source_transformations_available_at_issue",
    "transformation_policy_available_month",
]

AVAILABILITY_POLICY_VERSION = "c6_5_conservative_policy_lag_2_v1"

#: A project policy, never a measurement. C6.5 established that no EPPO
#: publication delay was ever observed.
OPERATIONAL_POLICY_LAG_MONTHS = 2

AVAILABILITY_BASIS = "conservative_policy_not_historical_measurement"


class AvailabilityPolicyError(TransformationError):
    """The availability policy was asked to permit or assert something it forbids."""


def transformation_policy_available_month(
    input_months, lag_months: int = OPERATIONAL_POLICY_LAG_MONTHS
) -> str:
    """The policy month of the latest input the formula declares.

    Taking the maximum rather than the reference month's own stamp is what makes
    this correct for a hypothetical forward-reaching window; under the current
    definitions every window ends at the reference month, and the equality is
    checked, not assumed.
    """
    months = sorted(str(m)[:7] for m in input_months)
    if not months:
        raise AvailabilityPolicyError(
            "a transformation with no declared input months has no availability"
        )
    return shift_month(months[-1], lag_months)


def assert_policy_month_matches_reference_rule(
    reference_month: str, policy_month: str,
    lag_months: int = OPERATIONAL_POLICY_LAG_MONTHS
) -> None:
    """Verify ``policy_available_month == reference_month + lag``.

    Stated as a check rather than a definition: if a future transformation read
    a month after its reference month, this would fail instead of quietly
    publishing an availability date that is too early.
    """
    expected = shift_month(reference_month, lag_months)
    if str(policy_month)[:7] != expected:
        raise AvailabilityPolicyError(
            f"reference month {reference_month} carries policy_available_month "
            f"{policy_month}, but the {lag_months}-month policy over the declared "
            f"input window gives {expected}"
        )


def assert_policy_month_is_not_a_release_date(row: dict) -> None:
    """Raise if the policy month has been written into an evidence field."""
    if row.get("source_available_as_of") is not None:
        raise AvailabilityPolicyError(
            f"{row.get('channel_id')} {row.get('reference_month')} "
            f"{row.get('transformation_id')} carries source_available_as_of "
            f"{row['source_available_as_of']!r}. EPPO release timing was never "
            "measured; the conservative policy month is not a release date"
        )
    if row.get("operational_lag_is_measured"):
        raise AvailabilityPolicyError(
            "operational_lag_is_measured is true, but the two-month lag is a "
            "conservative project policy that no observation established"
        )
    basis = row.get("availability_basis")
    if basis is not None and basis != AVAILABILITY_BASIS:
        raise AvailabilityPolicyError(
            f"availability_basis is {basis!r}; it must be {AVAILABILITY_BASIS!r}"
        )


def latest_permitted_reference_month(
    issue_month: str, lag_months: int = OPERATIONAL_POLICY_LAG_MONTHS
) -> str:
    """Latest source reference month readable at issue month *t*: ``t - lag``."""
    return shift_month(str(issue_month)[:7], -lag_months)


def select_source_transformations_available_at_issue(
    source_feature_table, issue_month: str, channel_id: str,
    lag_months: int = OPERATIONAL_POLICY_LAG_MONTHS,
) -> list:
    """Rows a forecast issued in ``issue_month`` may read from one channel.

    Only numeric rows qualify: a null row carries no value, and returning it
    would invite a caller to treat its absence as a zero. Rows are filtered on
    the stored ``policy_available_month``, and a row whose stamp disagrees with
    the reference-month rule raises rather than being accepted — a mis-stamped
    row is precisely how a leak would enter unnoticed.

    No target value, prediction or evaluation artifact is read.
    """
    channel = assert_single_fuel_oil_channel(
        [channel_id] if isinstance(channel_id, str) else channel_id,
        f"selection at issue month {issue_month}",
    )
    issue = str(issue_month)[:7]
    latest = latest_permitted_reference_month(issue, lag_months)

    selected = []
    for row in source_feature_table:
        if row.get("channel_id") != channel:
            continue
        assert_policy_month_is_not_a_release_date(row)
        reference = str(row.get("reference_month"))[:7]
        stamped = str(row.get("policy_available_month"))[:7]
        assert_policy_month_matches_reference_rule(reference, stamped, lag_months)
        if row.get("feature_value") is None:
            continue
        if row.get("transformation_status") != "available_numeric":
            continue
        if stamped <= issue and reference <= latest:
            selected.append(row)
    selected.sort(key=lambda r: (r["reference_month"], r["transformation_id"]))
    return selected


def issue_key_coverage(source_feature_table, issue_months, channel_id: str,
                       lag_months: int = OPERATIONAL_POLICY_LAG_MONTHS) -> dict:
    """Per-issue-month coverage for one channel, from timing metadata only.

    Reads preregistered issue-month keys and the policy lag. It does not open a
    target table, a prediction table or a metric.
    """
    channel = assert_single_fuel_oil_channel([channel_id], "issue-key coverage")
    per_issue, gaps = {}, set()
    for issue in sorted(issue_months):
        rows = select_source_transformations_available_at_issue(
            source_feature_table, issue, channel, lag_months
        )
        latest = latest_permitted_reference_month(issue, lag_months)
        available = {r["transformation_id"] for r in rows
                     if r["reference_month"] == latest}
        blocked = [
            r for r in source_feature_table
            if r.get("channel_id") == channel
            and r["reference_month"] == latest
            and r.get("feature_value") is None
        ]
        if blocked:
            gaps.add(latest)
        per_issue[issue] = {
            "latest_permitted_reference_month": latest,
            "rows_available": len(rows),
            "transformations_available_at_the_latest_permitted_month": sorted(available),
            "transformations_blocked_at_the_latest_permitted_month": sorted(
                r["transformation_id"] for r in blocked
            ),
        }
    return {
        "channel_id": channel,
        "issue_months": len(per_issue),
        "per_issue_month": per_issue,
        "reference_months_with_a_blocked_transformation": sorted(gaps),
        "target_values_read": False,
        "model_predictions_read": False,
        "locked_test_outcomes_read": False,
    }


def assert_channel_is_authorized(channel_id: str) -> str:
    """Raise unless the channel is one of the two C7.5-approved fuel oils."""
    if channel_id not in SERIES_BY_CHANNEL:
        raise AvailabilityPolicyError(
            f"{channel_id!r} is not an authorized C8 fuel-oil channel"
        )
    return channel_id
