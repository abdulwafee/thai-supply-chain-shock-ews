"""Phase 2 tests: the arithmetic, the exclusions and the ranking.

Most properties are clearer against a small synthetic bundle where the coefficients are
chosen to make one thing obvious — an exact tie, an exact cancellation, a null sign —
than against real coefficients that happen to be near each other. The synthetic bundles
are built from the same immutable record types the loader produces, so nothing here
exercises a shape the real loader could not emit.

Two integration tests run against the real pinned artifacts, because a synthetic fixture
proves the arithmetic and not that the arithmetic is wired to the published numbers.
"""

from __future__ import annotations

import ast
import decimal
import itertools
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.scenario import artifacts as art
from thai_supply_chain_ews.scenario import contract
from thai_supply_chain_ews.scenario import exposure as ex

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "structural_exposure_scenario.yaml"
EXPOSURE_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "exposure.py"

CHANNEL_SECTORS = {
    "aluminum_usd_mt": "107",
    "brent_crude_usd_bbl": "031",
    "copper_usd_mt": "107",
    "rubber_rss3_usd_kg": "095",
}


@pytest.fixture
def policy() -> contract.ScenarioPolicy:
    return contract.load_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def real_bundle():
    return art.load_artifact_bundle(
        ROOT, policy=contract.load_policy(POLICY_PATH), policy_path=POLICY_PATH
    )


def industry(number: int) -> art.Industry:
    return art.Industry(
        industry_id=f"IND-{number:02d}", name_en=f"Industry {number}",
        tsic_divisions=("10",), status="active",
    )


def pair(industry_id, channel, direct, total, *, sign=1, eligible=True,
         direction="cost_pressure", published_indirect=None) -> art.ExposurePair:
    direct, total = Decimal(direct), Decimal(total)
    return art.ExposurePair(
        industry_id=industry_id,
        industry_name=f"Industry {int(industry_id.split('-')[1])}",
        channel=channel,
        io_sector_code=CHANNEL_SECTORS[channel],
        direct_exposure=direct,
        total_requirement_exposure=total,
        published_indirect_exposure=(
            total - direct if published_indirect is None else Decimal(published_indirect)
        ),
        sign=sign,
        direction_channel=direction,
        feature_eligible=eligible,
        proxy_fit_status="broad_proxy_use_with_caution",
        quality_flag="ok",
    )


def bundle_of(*pairs, industries=None) -> art.ArtifactBundle:
    ids = sorted({p.industry_id for p in pairs})
    return art.ArtifactBundle(
        declarations=(
            art.ArtifactDeclaration(
                name="exposure_matrix", path="docs/c3_commodity_exposure_matrix.json",
                fmt="json", sha256="0" * 64, digest_representation="canonical_lf", role="test",
            ),
        ),
        industries=tuple(
            industries or (industry(int(i.split("-")[1])) for i in ids)
        ),
        pairs=tuple(pairs),
        mediators=(),
        price_stages=(),
        channel_sectors=dict(CHANNEL_SECTORS),
        structural_reference_year=2015,
    )


def scenario_for(tmp_path, shocks, policy, scenario_id="synthetic-case"):
    lines = [
        "schema_version: structural_exposure_scenario_v1",
        f"scenario_id: {scenario_id}",
        "shocks:",
    ]
    for channel, direction, magnitude in shocks:
        lines += [
            f"  - channel: {channel}",
            f"    direction: {direction}",
            f"    magnitude: {magnitude}",
            "    magnitude_unit: fraction",
        ]
    path = tmp_path / f"{scenario_id}.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return contract.load_scenario_document(path, policy=policy)


# ---------------------------------------------------------------------------
# The basis is the caller's decision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("basis", ["direct", "total_requirement"])
def test_both_registered_bases_are_accepted(tmp_path, policy, basis):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis=basis, bundle=bundle, policy=policy)
    assert result.basis == basis


def test_an_omitted_basis_is_refused_and_never_defaulted(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.1")], policy)
    with pytest.raises(contract.ScenarioContractError) as caught:
        ex.calculate_scenario_exposure(scenario, basis=None, bundle=bundle, policy=policy)
    assert caught.value.field == "basis"
    assert "no default" in str(caught.value)


@pytest.mark.parametrize("basis", ["Direct", "total", "indirect", "", "propagated", "primary"])
def test_an_unsupported_basis_is_refused(tmp_path, policy, basis):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.1")], policy)
    with pytest.raises(contract.ScenarioContractError):
        ex.calculate_scenario_exposure(scenario, basis=basis, bundle=bundle, policy=policy)


def test_the_total_requirement_basis_is_labelled_sensitivity_only(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.1")], policy)
    sensitivity = ex.calculate_scenario_exposure(
        scenario, basis="total_requirement", bundle=bundle, policy=policy
    )
    primary = ex.calculate_scenario_exposure(
        scenario, basis="direct", bundle=bundle, policy=policy
    )
    assert sensitivity.basis_role == "structural_sensitivity_only"
    assert primary.basis_role == "registered_primary"
    assert sensitivity.registered_primary_basis == "direct"


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


def test_a_contribution_is_sign_times_magnitude_times_the_selected_coefficient(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.25")], policy)

    direct = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert direct.ranking[0].net_exposure == Decimal("0.25") * Decimal("0.2") == Decimal("0.050")

    total = ex.calculate_scenario_exposure(scenario, basis="total_requirement", bundle=bundle,
                                           policy=policy)
    assert total.ranking[0].net_exposure == Decimal("0.25") * Decimal("0.5") == Decimal("0.125")


def test_a_decrease_produces_a_negative_contribution_and_relief_pressure(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "decrease", "0.25")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    entry = result.ranking[0]
    assert entry.net_exposure == Decimal("-0.050")
    assert entry.direction == "relief_pressure"
    assert entry.relative_exposure_index == Decimal(-100)


def test_every_arithmetic_value_is_a_decimal_and_never_a_float(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="total_requirement", bundle=bundle,
                                            policy=policy)
    entry = result.ranking[0]
    for value in (entry.net_exposure, entry.direct_component, entry.propagated_component,
                  entry.gross_absolute_contribution, entry.cancellation,
                  entry.relative_exposure_index, result.relative_index_denominator):
        assert isinstance(value, Decimal)
        assert not isinstance(value, float)
    for contribution in entry.contributions:
        for value in (contribution.contribution, contribution.coefficient,
                      contribution.direct_component, contribution.propagated_component):
            assert isinstance(value, Decimal)


def test_the_direct_basis_reports_no_propagated_component(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    entry = result.ranking[0]
    assert entry.propagated_supported is False
    assert entry.propagated_component is None
    assert entry.contributions[0].propagated_component is None
    assert entry.net_exposure == entry.direct_component


def test_the_total_requirement_basis_splits_direct_and_propagated_exactly(tmp_path, policy):
    """The identity holds with no residual because propagated is derived, not read."""
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.0002181634956282774",
             "0.010584864831580304"),
        pair("IND-02", "brent_crude_usd_bbl", "0", "0.129149"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.3")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="total_requirement", bundle=bundle,
                                            policy=policy)
    for entry in result.ranking:
        assert entry.direct_component + entry.propagated_component == entry.net_exposure
        for contribution in entry.contributions:
            assert (
                contribution.direct_component + contribution.propagated_component
                == contribution.contribution
            )


def test_multiple_channels_sum_and_the_gross_is_the_absolute_total(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.4"),
        pair("IND-01", "rubber_rss3_usd_kg", "0.1", "0.3"),
    )
    scenario = scenario_for(
        tmp_path,
        [("brent_crude_usd_bbl", "increase", "0.5"), ("rubber_rss3_usd_kg", "increase", "0.2")],
        policy,
    )
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    entry = result.ranking[0]
    assert len(entry.contributions) == 2
    assert entry.net_exposure == Decimal("0.5") * Decimal("0.2") + Decimal("0.2") * Decimal("0.1")
    assert entry.gross_absolute_contribution == entry.net_exposure
    assert entry.cancellation == 0
    assert entry.cancellation_ratio == 0


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_partial_cancellation_is_reported_beside_the_net(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.4", "0.4"),
        pair("IND-01", "rubber_rss3_usd_kg", "0.3", "0.3"),
    )
    scenario = scenario_for(
        tmp_path,
        [("brent_crude_usd_bbl", "increase", "0.5"), ("rubber_rss3_usd_kg", "decrease", "0.5")],
        policy,
    )
    entry = ex.calculate_scenario_exposure(
        scenario, basis="direct", bundle=bundle, policy=policy
    ).ranking[0]
    assert entry.net_exposure == Decimal("0.05")
    assert entry.gross_absolute_contribution == Decimal("0.35")
    assert entry.cancellation == Decimal("0.30")
    assert entry.cancellation_ratio == Decimal("0.30") / Decimal("0.35")
    assert entry.direction == "stress_pressure"


def test_exact_cancellation_is_visible_rather_than_hidden_behind_a_zero(tmp_path, policy):
    """Two large opposing contributions that net to nothing is the case a net alone hides."""
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.4", "0.4"),
        pair("IND-01", "rubber_rss3_usd_kg", "0.4", "0.4"),
    )
    scenario = scenario_for(
        tmp_path,
        [("brent_crude_usd_bbl", "increase", "0.5"), ("rubber_rss3_usd_kg", "decrease", "0.5")],
        policy,
    )
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    entry = result.industry("IND-01")
    assert entry.net_exposure == 0
    assert entry.gross_absolute_contribution == Decimal("0.4")
    assert entry.cancellation == Decimal("0.4")
    assert entry.cancellation_ratio == 1
    assert entry.direction == "neutral"
    assert [c.channel for c in entry.contributions] == [
        "brent_crude_usd_bbl", "rubber_rss3_usd_kg"
    ]
    assert result.no_ranking_reason == "all_net_exposures_zero"


def test_a_zero_gross_contribution_has_no_cancellation_ratio(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0", "0"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.5")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    entry = result.industries[0]
    assert entry.gross_absolute_contribution == 0
    assert entry.cancellation_ratio is None
    assert entry.direction == "neutral"


# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------


def test_an_ineligible_pair_is_excluded_with_a_reason_not_scored_as_zero(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "aluminum_usd_mt", "0.5", "0.9", eligible=False),
        pair("IND-02", "aluminum_usd_mt", "0.1", "0.2"),
    )
    scenario = scenario_for(tmp_path, [("aluminum_usd_mt", "increase", "0.5")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.industry_id for e in result.ranking] == ["IND-02"]
    assert result.unscorable_industry_ids == ("IND-01",)
    excluded = result.excluded_pairs
    assert [(e.industry_id, e.channel, e.reason) for e in excluded] == [
        ("IND-01", "aluminum_usd_mt", "pair_not_feature_eligible")
    ]
    assert "not treated as zero" in excluded[0].detail


def test_a_null_sign_pair_is_excluded_with_its_own_reason(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "aluminum_usd_mt", "0.5", "0.9", sign=None, eligible=False,
             direction="mixed_or_ambiguous"),
        pair("IND-02", "aluminum_usd_mt", "0.1", "0.2"),
    )
    scenario = scenario_for(tmp_path, [("aluminum_usd_mt", "increase", "0.5")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.reason for e in result.excluded_pairs] == ["direction_sign_unresolved"]
    assert result.excluded_pairs[0].reason in ex.EXCLUSION_REASONS


def test_an_industry_whose_only_pair_is_excluded_is_not_ranked_at_zero(tmp_path, policy):
    """Ranking it at zero would be the same coercion, one level up."""
    bundle = bundle_of(
        pair("IND-01", "aluminum_usd_mt", "0.5", "0.9", eligible=False),
        pair("IND-02", "aluminum_usd_mt", "0.1", "0.2"),
    )
    scenario = scenario_for(tmp_path, [("aluminum_usd_mt", "increase", "0.5")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert "IND-01" not in [e.industry_id for e in result.ranking]
    unscorable = result.unscorable[0]
    assert unscorable.industry_id == "IND-01"
    assert unscorable.contributions == ()
    assert unscorable.rank is None
    assert unscorable.relative_exposure_index is None
    assert [e.reason for e in unscorable.excluded_pairs] == ["pair_not_feature_eligible"]


def test_a_published_zero_coefficient_is_scored_and_is_not_an_exclusion(tmp_path, policy):
    """An observed zero is a measurement; an exclusion is the absence of one."""
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0", "0.1"),
        pair("IND-02", "brent_crude_usd_bbl", "0.2", "0.3"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.5")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert result.excluded_pairs == ()
    entry = result.industry("IND-01")
    assert entry.contributions and entry.net_exposure == 0
    assert entry.rank is not None


def test_a_scenario_with_no_scorable_pair_raises_the_no_scorable_pairs_condition(
    tmp_path, policy
):
    bundle = bundle_of(
        pair("IND-01", "aluminum_usd_mt", "0.5", "0.9", sign=None, eligible=False,
             direction="mixed_or_ambiguous"),
        pair("IND-02", "aluminum_usd_mt", "0.4", "0.8", eligible=False),
    )
    scenario = scenario_for(tmp_path, [("aluminum_usd_mt", "increase", "0.5")], policy)
    with pytest.raises(contract.ScenarioContractError) as caught:
        ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle, policy=policy)
    assert caught.value.details["condition"] == "no_scorable_pairs"
    assert {e["reason"] for e in caught.value.details["excluded"]} <= ex.EXCLUSION_REASONS


# ---------------------------------------------------------------------------
# No ranking
# ---------------------------------------------------------------------------


def test_an_all_zero_scenario_produces_no_ranking_and_keeps_its_phase_one_warning(
    tmp_path, policy
):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.2", "0.5"),
        pair("IND-02", "brent_crude_usd_bbl", "0.4", "0.7"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0")], policy)
    assert "zero_magnitude_no_discrimination" in scenario.warning_codes
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert result.ranking == ()
    assert result.has_ranking is False
    assert result.no_ranking_reason == "all_magnitudes_zero"
    assert result.no_ranking_reason in ex.NO_RANKING_REASONS
    assert result.relative_index_denominator is None
    assert len(result.unranked) == 2
    assert all(e.rank is None and e.relative_exposure_index is None for e in result.unranked)


def test_all_net_exposures_cancelling_gives_its_own_no_ranking_reason(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.4", "0.4"),
        pair("IND-01", "rubber_rss3_usd_kg", "0.4", "0.4"),
        pair("IND-02", "brent_crude_usd_bbl", "0.2", "0.2"),
        pair("IND-02", "rubber_rss3_usd_kg", "0.2", "0.2"),
    )
    scenario = scenario_for(
        tmp_path,
        [("brent_crude_usd_bbl", "increase", "0.5"), ("rubber_rss3_usd_kg", "decrease", "0.5")],
        policy,
    )
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert result.ranking == ()
    assert result.no_ranking_reason == "all_net_exposures_zero"
    assert result.no_ranking_reason != "all_magnitudes_zero"
    assert all(e.gross_absolute_contribution > 0 for e in result.unranked)


def test_no_ranking_never_divides_by_zero(tmp_path, policy):
    bundle = bundle_of(pair("IND-01", "brent_crude_usd_bbl", "0", "0"))
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.5")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert result.relative_index_denominator is None
    assert result.no_ranking_reason == "all_net_exposures_zero"


# ---------------------------------------------------------------------------
# Ranking, index and ties
# ---------------------------------------------------------------------------


def test_ranking_is_descending_by_absolute_net_exposure(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.1", "0.1"),
        pair("IND-02", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-03", "brent_crude_usd_bbl", "0.3", "0.3"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.industry_id for e in result.ranking] == ["IND-02", "IND-03", "IND-01"]
    assert [e.rank for e in result.ranking] == [1, 2, 3]


def test_a_negative_net_ranks_by_magnitude_and_keeps_its_sign(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.9", "0.9"),
        pair("IND-02", "brent_crude_usd_bbl", "0.2", "0.2"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "decrease", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.industry_id for e in result.ranking] == ["IND-01", "IND-02"]
    assert result.ranking[0].net_exposure < 0
    assert result.ranking[0].relative_exposure_index == Decimal(-100)
    assert all(e.relative_exposure_index < 0 for e in result.ranking)


def test_the_relative_index_is_signed_and_scaled_by_the_largest_absolute_net(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.4", "0.4"),
        pair("IND-02", "brent_crude_usd_bbl", "0.1", "0.1"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert result.relative_index_denominator == Decimal("0.4")
    assert result.ranking[0].relative_exposure_index == Decimal(100)
    assert result.ranking[1].relative_exposure_index == Decimal(25)


def test_industry_id_breaks_ties_deterministically(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-03", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-01", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-02", "brent_crude_usd_bbl", "0.5", "0.5"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.industry_id for e in result.ranking] == ["IND-01", "IND-02", "IND-03"]


def test_exact_ties_share_a_competition_rank(tmp_path, policy):
    """1, 1, 3 — not 1, 1, 2."""
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-02", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-03", "brent_crude_usd_bbl", "0.1", "0.1"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.rank for e in result.ranking] == [1, 1, 3]
    assert result.ranking[0].tied_with == ("IND-02",)
    assert result.ranking[1].tied_with == ("IND-01",)
    assert result.ranking[2].tied_with == ()


def test_values_within_the_tolerance_are_tied(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-02", "brent_crude_usd_bbl", "0.5000000000001", "0.5000000000001"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert abs(result.ranking[0].net_exposure - result.ranking[1].net_exposure) <= ex.TIE_TOLERANCE
    assert [e.rank for e in result.ranking] == [1, 1]


def test_values_outside_the_tolerance_are_not_tied(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.5", "0.5"),
        pair("IND-02", "brent_crude_usd_bbl", "0.500000001", "0.500000001"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert [e.rank for e in result.ranking] == [1, 2]
    assert all(e.tied_with == () for e in result.ranking)


def test_a_chain_of_near_equal_values_does_not_collapse_into_one_tie(tmp_path, policy):
    """Each step is inside the tolerance of the last; the ends are far apart.

    Comparing against the previous value would swallow all four into one group and
    announce that four different numbers are equal. Comparing against the group anchor
    is what keeps a tolerance from becoming a claim.
    """
    step = Decimal("0.0000000000009")  # just inside 1e-12
    values = [Decimal("0.5") - step * n for n in range(4)]
    bundle = bundle_of(
        *(pair(f"IND-0{n + 1}", "brent_crude_usd_bbl", v, v) for n, v in enumerate(values))
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "1")], policy)
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=bundle,
                                            policy=policy)
    assert abs(values[0] - values[-1]) > ex.TIE_TOLERANCE
    assert result.ranking[0].rank != result.ranking[-1].rank
    assert [e.rank for e in result.ranking] == [1, 1, 3, 3]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_the_order_the_author_lists_shocks_in_changes_nothing(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.3", "0.6"),
        pair("IND-01", "rubber_rss3_usd_kg", "0.2", "0.4"),
        pair("IND-02", "brent_crude_usd_bbl", "0.1", "0.2"),
        pair("IND-02", "rubber_rss3_usd_kg", "0.5", "0.9"),
    )
    shocks = [("brent_crude_usd_bbl", "increase", "0.4"),
              ("rubber_rss3_usd_kg", "decrease", "0.2")]
    seen = set()
    for index, order in enumerate(itertools.permutations(shocks)):
        scenario = scenario_for(tmp_path, list(order), policy, scenario_id=f"order-{index}")
        result = ex.calculate_scenario_exposure(scenario, basis="total_requirement",
                                                bundle=bundle, policy=policy)
        seen.add(
            tuple(
                (e.industry_id, e.rank, str(e.net_exposure), str(e.direct_component),
                 str(e.propagated_component), str(e.gross_absolute_contribution),
                 str(e.cancellation), e.direction, str(e.relative_exposure_index),
                 tuple((c.channel, str(c.contribution)) for c in e.contributions))
                for e in result.ranking
            )
        )
    assert len(seen) == 1


def test_repeating_the_same_calculation_gives_the_same_result(tmp_path, policy):
    bundle = bundle_of(
        pair("IND-01", "brent_crude_usd_bbl", "0.3", "0.6"),
        pair("IND-02", "brent_crude_usd_bbl", "0.1", "0.2"),
    )
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.4")], policy)
    digests = {
        tuple(
            (e.industry_id, e.rank, str(e.net_exposure), str(e.relative_exposure_index))
            for e in ex.calculate_scenario_exposure(
                scenario, basis="total_requirement", bundle=bundle, policy=policy
            ).ranking
        )
        for _ in range(5)
    }
    assert len(digests) == 1


# ---------------------------------------------------------------------------
# Ownership of the shared-sector rule
# ---------------------------------------------------------------------------


def test_aluminum_and_copper_together_are_refused_before_the_engine_is_reached(tmp_path, policy):
    """The shared-sector rule stays where Phase 1 put it: in the input contract."""
    path = tmp_path / "shared.yaml"
    path.write_text(
        "schema_version: structural_exposure_scenario_v1\nscenario_id: shared-sector\nshocks:\n"
        "  - channel: aluminum_usd_mt\n    direction: increase\n"
        "    magnitude: 0.2\n    magnitude_unit: fraction\n"
        "  - channel: copper_usd_mt\n    direction: increase\n"
        "    magnitude: 0.2\n    magnitude_unit: fraction\n",
        encoding="utf-8", newline="\n",
    )
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(path, policy=policy)
    assert caught.value.code == "shared_io_sector"
    source = EXPOSURE_SOURCE.read_text(encoding="utf-8")
    assert "shared_io_sector" not in source


# ---------------------------------------------------------------------------
# Integration against the real pinned artifacts
# ---------------------------------------------------------------------------


def test_a_real_brent_shock_ranks_refined_petroleum_first(tmp_path, policy, real_bundle):
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.3")], policy,
                            scenario_id="real-brent")
    result = ex.calculate_scenario_exposure(scenario, basis="total_requirement",
                                            bundle=real_bundle, policy=policy)
    assert len(result.ranking) == 12
    assert result.ranking[0].industry_id == "IND-04"
    assert result.ranking[0].relative_exposure_index == Decimal(100)
    assert result.ranking[0].net_exposure == Decimal("0.3") * real_bundle.pair(
        "IND-04", "brent_crude_usd_bbl"
    ).total_requirement_exposure
    for entry in result.ranking:
        assert entry.direct_component + entry.propagated_component == entry.net_exposure
        assert entry.direction == "stress_pressure"


def test_a_real_aluminum_shock_excludes_the_two_published_ineligible_industries(
    tmp_path, policy, real_bundle
):
    scenario = scenario_for(tmp_path, [("aluminum_usd_mt", "increase", "0.2")], policy,
                            scenario_id="real-aluminum")
    result = ex.calculate_scenario_exposure(scenario, basis="total_requirement",
                                            bundle=real_bundle, policy=policy)
    excluded = {(e.industry_id, e.reason) for e in result.excluded_pairs}
    assert excluded == {
        ("IND-08", "direction_sign_unresolved"),
        ("IND-12", "pair_not_feature_eligible"),
    }
    assert result.unscorable_industry_ids == ("IND-08", "IND-12")
    assert {e.industry_id for e in result.ranking}.isdisjoint({"IND-08", "IND-12"})
    assert len(result.ranking) == 10


def test_the_real_direct_basis_is_degenerate_for_crude_and_says_so_honestly(
    tmp_path, policy, real_bundle
):
    """Ten of twelve industries publish an observed-zero direct coefficient for crude.

    They are scored, not excluded — an observed zero is a measurement — and the result
    is a large neutral tie, which is the honest answer on this basis rather than a
    defect.
    """
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.3")], policy,
                            scenario_id="real-direct")
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=real_bundle,
                                            policy=policy)
    neutral = [e for e in result.ranking if e.net_exposure == 0]
    assert len(neutral) == 10
    assert all(e.direction == "neutral" for e in neutral)
    assert result.excluded_pairs == ()
    assert len({e.rank for e in neutral}) == 1


def test_the_result_carries_the_provenance_of_what_produced_it(tmp_path, policy, real_bundle):
    scenario = scenario_for(tmp_path, [("brent_crude_usd_bbl", "increase", "0.3")], policy,
                            scenario_id="real-provenance")
    result = ex.calculate_scenario_exposure(scenario, basis="direct", bundle=real_bundle,
                                            policy=policy)
    assert result.scenario_input_sha256 == contract.canonical_input_sha256(scenario)
    assert set(result.artifact_digests) == set(art.ARTIFACT_NAMES)
    assert result.structural_reference_year == 2015
    for name, value in result.artifact_digests.items():
        assert value == real_bundle.digest_of(name)


# ---------------------------------------------------------------------------
# Semantic boundary
# ---------------------------------------------------------------------------


def public_field_names() -> set:
    """Field and property names on every public result record, by AST."""
    tree = ast.parse(EXPOSURE_SOURCE.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    names.add(statement.target.id)
                if isinstance(statement, ast.FunctionDef) and any(
                    isinstance(d, ast.Name) and d.id == "property"
                    for d in statement.decorator_list
                ):
                    names.add(statement.name)
    return names


def test_no_public_result_field_makes_a_predictive_or_causal_claim():
    """Field names, read from the AST — not a text search over prose.

    A raw-text ban would fail on this module's own docstrings, which have to be able to
    say what the calculation is *not*.
    """
    forbidden = {
        "probability", "likelihood", "prediction", "predicted", "forecast", "expected_return",
        "expected_loss", "predicted_percentage_impact", "risk_score", "risk_band", "risk_level",
        "confidence", "causal_effect", "elasticity", "pass_through", "company_exposure",
        "supplier_cascade", "customer_cascade", "recommendation", "buy", "sell", "hold",
    }
    fields = public_field_names()
    assert fields & forbidden == set()
    for name in fields:
        for token in ("probabil", "forecast", "predict", "elastic", "causal", "risk_",
                      "recommend", "company", "confidence"):
            assert token not in name, name


def test_the_engine_imports_no_model_target_or_external_data_module():
    tree = ast.parse(EXPOSURE_SOURCE.read_text(encoding="utf-8"))
    project = set()
    other = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            other.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            (project if node.module.startswith("thai_supply_chain_ews.") else other).add(
                node.module
            )
    assert project == {
        "thai_supply_chain_ews.scenario.artifacts",
        "thai_supply_chain_ews.scenario.contract",
    }
    assert not {name.split(".")[0] for name in other} & {
        "socket", "urllib", "http", "requests", "pandas", "numpy", "sklearn", "joblib", "pickle"
    }


def test_the_package_ships_only_reviewed_modules():
    """The same closed set the contract tests assert, checked from the engine's side."""
    package = EXPOSURE_SOURCE.parent
    assert sorted(p.name for p in package.glob("*.py")) == [
        "__init__.py", "__main__.py", "artifacts.py", "contract.py", "exposure.py",
        "interactive.py", "report.py",
    ]


def test_the_public_api_exposes_the_reviewed_phase_two_names_and_no_more():
    from thai_supply_chain_ews import scenario

    assert "calculate_scenario_exposure" in scenario.__all__
    assert "load_artifact_bundle" in scenario.__all__
    # `report` completed in Phase 3 and is exported as a reviewed submodule. `main`
    # is not: the command-line entry point is reached through `python -m`, never
    # imported, so exporting it would invite a dependency nobody reviewed.
    assert "report" in scenario.__all__
    for name in ("main", "cli", "render", "run", "predict", "forecast",
                 "fetch", "download"):
        assert name not in scenario.__all__
    for name in ("_rank", "_aggregate", "_contribution", "_require_basis",
                 "_exclusion_reason", "_exclusion_detail"):
        assert name not in scenario.__all__
        assert not hasattr(scenario, name)
        assert hasattr(ex, name)


# ---------------------------------------------------------------------------
# The arithmetic does not depend on the caller's decimal context
# ---------------------------------------------------------------------------


def context_scenario(tmp_path, policy):
    """A scenario whose index and cancellation ratio are both non-terminating.

    Two channels in opposite directions, so the net is a real cancellation of two
    contributions and the ratio is a genuine division; twelve industries, so the
    relative index divides by a denominator it does not divide evenly into.
    """
    return scenario_for(
        tmp_path,
        [("brent_crude_usd_bbl", "increase", "0.25"), ("rubber_rss3_usd_kg", "decrease", "0.15")],
        policy,
        scenario_id="ambient-context",
    )


AMBIENT_CONTEXTS = [
    (6, decimal.ROUND_DOWN),
    (28, decimal.ROUND_HALF_EVEN),
    (80, decimal.ROUND_CEILING),
    (9, decimal.ROUND_UP),
    (50, decimal.ROUND_FLOOR),
]


def under(prec, rounding, work):
    """Run ``work`` with an ambient context, always restoring the caller's."""
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = prec, rounding
        return work()


def test_the_result_is_identical_under_every_ambient_decimal_context(
    tmp_path, policy, real_bundle
):
    """The defect this guards: at precision 6 the calculation used to raise outright."""
    scenario = context_scenario(tmp_path, policy)
    results = [
        under(prec, rounding,
              lambda: ex.calculate_scenario_exposure(
                  scenario, basis="total_requirement", bundle=real_bundle, policy=policy))
        for prec, rounding in AMBIENT_CONTEXTS
    ]
    first = results[0]
    for other in results[1:]:
        assert other == first


def test_every_canonical_value_is_identical_under_every_ambient_context(
    tmp_path, policy, real_bundle
):
    scenario = context_scenario(tmp_path, policy)
    seen = set()
    for prec, rounding in AMBIENT_CONTEXTS:
        result = under(prec, rounding,
                       lambda: ex.calculate_scenario_exposure(
                           scenario, basis="total_requirement", bundle=real_bundle,
                           policy=policy))
        seen.add(
            tuple(
                (e.industry_id, e.rank, str(e.net_exposure), str(e.direct_component),
                 str(e.propagated_component), str(e.gross_absolute_contribution),
                 str(e.cancellation), str(e.cancellation_ratio),
                 str(e.relative_exposure_index), e.direction, e.canonical_net_exposure,
                 tuple(c.canonical_contribution for c in e.contributions))
                for e in result.ranking
            )
        )
    assert len(seen) == 1


def test_both_renderings_are_byte_identical_under_every_ambient_context(
    tmp_path, policy, real_bundle
):
    from thai_supply_chain_ews.scenario import report as rp

    scenario = context_scenario(tmp_path, policy)
    renders = set()
    for prec, rounding in AMBIENT_CONTEXTS:
        def build():
            result = ex.calculate_scenario_exposure(
                scenario, basis="total_requirement", bundle=real_bundle, policy=policy
            )
            document = rp.build_scenario_result_document(scenario, result, real_bundle)
            return (rp.render_scenario_result_json(document).encode("utf-8"),
                    rp.render_scenario_result_markdown(document).encode("utf-8"))

        renders.add(under(prec, rounding, build))
    assert len(renders) == 1


def test_ranks_and_tie_groups_are_identical_under_every_ambient_context(
    tmp_path, policy, real_bundle
):
    scenario = context_scenario(tmp_path, policy)
    orders = {
        under(prec, rounding,
              lambda: tuple(
                  (e.industry_id, e.rank, e.tied_with)
                  for e in ex.calculate_scenario_exposure(
                      scenario, basis="total_requirement", bundle=real_bundle,
                      policy=policy).ranking))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(orders) == 1


def test_the_exact_identity_survives_every_ambient_context(tmp_path, policy, real_bundle):
    """Checked inside the engine's own context.

    A caller who adds two of these decimals in a precision-6 context gets a precision-6
    sum -- that is the caller's arithmetic, not a wrong stored value -- so the comparison
    is made where the engine makes it.
    """
    scenario = context_scenario(tmp_path, policy)
    for prec, rounding in AMBIENT_CONTEXTS:
        result = under(prec, rounding,
                       lambda: ex.calculate_scenario_exposure(
                           scenario, basis="total_requirement", bundle=real_bundle,
                           policy=policy))
        for entry in result.ranking:
            assert contract.exact_total([entry.direct_component, entry.propagated_component]) == (
                entry.net_exposure
            )
            for contribution in entry.contributions:
                assert contract.exact_total(
                    [contribution.direct_component, contribution.propagated_component]
                ) == contribution.contribution


def test_a_successful_calculation_leaves_the_callers_context_untouched(
    tmp_path, policy, real_bundle
):
    scenario = context_scenario(tmp_path, policy)
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = 11, decimal.ROUND_05UP
        before = (decimal.getcontext().prec, decimal.getcontext().rounding,
                  dict(decimal.getcontext().traps))
        ex.calculate_scenario_exposure(scenario, basis="total_requirement",
                                       bundle=real_bundle, policy=policy)
        after = (decimal.getcontext().prec, decimal.getcontext().rounding,
                 dict(decimal.getcontext().traps))
        assert before == after
        assert after[0] == 11 and after[1] == decimal.ROUND_05UP


def test_a_raising_calculation_also_restores_the_callers_context(
    tmp_path, policy, real_bundle
):
    scenario = context_scenario(tmp_path, policy)
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = 13, decimal.ROUND_FLOOR
        with pytest.raises(contract.ScenarioContractError):
            ex.calculate_scenario_exposure(scenario, basis="not-a-basis",
                                           bundle=real_bundle, policy=policy)
        assert decimal.getcontext().prec == 13
        assert decimal.getcontext().rounding == decimal.ROUND_FLOOR


def test_reading_a_property_does_not_alter_the_callers_context(tmp_path, policy, real_bundle):
    """``cancellation`` and its ratio are computed when a reader touches them."""
    scenario = context_scenario(tmp_path, policy)
    result = ex.calculate_scenario_exposure(scenario, basis="total_requirement",
                                            bundle=real_bundle, policy=policy)
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = 7, decimal.ROUND_UP
        entry = result.ranking[0]
        touched = (entry.cancellation, entry.cancellation_ratio, entry.direction,
                   entry.canonical_net_exposure)
        assert touched is not None
        assert decimal.getcontext().prec == 7
        assert decimal.getcontext().rounding == decimal.ROUND_UP


def test_the_declared_contexts_are_explicit_and_private():
    """Two kinds of context, with deliberately different trap sets.

    The exact ones trap ``Inexact``, because rounding there would mean a precision
    derivation was wrong and the module would be returning a number it calls exact. The
    quotient one does not, because a non-terminating quotient has to be rounded
    somewhere and 28 digits is the declared place.

    The exact helpers live in ``contract`` rather than here: ``artifacts`` needs the same
    guarantees and cannot import this module, so one implementation serves both.
    """
    for context in (ex._QUOTIENT_CONTEXT, contract.exact_context(17),
                    contract.exact_context(200)):
        assert isinstance(context, decimal.Context)
        assert context.rounding == decimal.ROUND_HALF_EVEN
        assert context.Emin == -999999
        assert context.Emax == 999999
        for signal in (decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow):
            assert context.traps[signal] is True

    assert ex._QUOTIENT_CONTEXT.prec == 28
    assert ex._QUOTIENT_CONTEXT.traps[decimal.Inexact] is False
    assert contract.exact_context(17).traps[decimal.Inexact] is True
    assert not hasattr(ex, "_EXACT_CONTEXT"), "a fixed ceiling is the defect, not the fix"

    from thai_supply_chain_ews import scenario

    for name in ("_QUOTIENT_CONTEXT", "exact_context", "exact_product", "exact_total",
                 "exact_difference", "fixed_context", "significant_digits"):
        assert name not in ex.__all__
        assert name not in contract.__all__
        assert name not in scenario.__all__


def test_removing_the_fixed_context_would_make_these_tests_fail(tmp_path, policy, real_bundle):
    """Mutation check: the pinning is load-bearing, not decoration.

    The same three values are recomputed the way the module would if the
    ``localcontext`` wrappers were deleted -- straight into the ambient context. If that
    produced the same answers everywhere, every test above would pass whether or not the
    fix existed.
    """
    scenario = context_scenario(tmp_path, policy)
    result = ex.calculate_scenario_exposure(scenario, basis="total_requirement",
                                            bundle=real_bundle, policy=policy)
    entry = result.ranking[1]
    denominator = result.relative_index_denominator

    unpinned = set()
    for prec, rounding in AMBIENT_CONTEXTS:
        def recompute():
            index = (Decimal(100) * entry.net_exposure) / denominator
            gross = entry.gross_absolute_contribution
            ratio = (gross - abs(entry.net_exposure)) / gross
            return (str(index), str(ratio), contract.decimal_text(entry.net_exposure))

        unpinned.add(under(prec, rounding, recompute))
    assert len(unpinned) > 1, "if this collapses to one, the guard proves nothing"

    pinned = {
        under(prec, rounding,
              lambda: (str(entry.relative_exposure_index), str(entry.cancellation_ratio),
                       entry.canonical_net_exposure))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(pinned) == 1


# ---------------------------------------------------------------------------
# The precision is derived from the operands, not fixed
#
# The first version of the fix above pinned one context at 60 digits. That removed the
# dependence on the caller's settings and replaced it with a ceiling: Phase 1 bounds a
# magnitude's value but not its digit count, so a contract-valid magnitude can be long,
# and a 60-digit magnitude times a 16-digit coefficient needs 76 digits. At 60 the
# product was silently truncated and the exact decomposition it feeds became a rounded
# one. Deriving the width from the operands removes the boundary rather than moving it.
#
# `Inexact` is trapped in those derived contexts, so a derivation that was ever short by
# one digit would raise instead of rounding. The long-magnitude cases below are what
# demonstrate it does not fire.
# ---------------------------------------------------------------------------


#: Longer than any precision in AMBIENT_CONTEXTS and longer than the 60-digit ceiling
#: the first fix carried, so a fixed-width context must lose digits from its products.
LONG_MAGNITUDE = "0." + "1234567891" * 8


def long_scenario(tmp_path, policy, direction="decrease", tag="long"):
    return scenario_for(
        tmp_path,
        [("brent_crude_usd_bbl", direction, LONG_MAGNITUDE)],
        policy,
        scenario_id=tag,
    )


def test_a_long_magnitude_is_scored_without_rounding(tmp_path, policy, real_bundle):
    """The product keeps every digit both operands contribute.

    A magnitude of m digits against a coefficient of n needs m + n; anything narrower
    would either round -- which the trapped ``Inexact`` turns into a raise -- or, before
    the trap existed, quietly return a shortened number.
    """
    scenario = long_scenario(tmp_path, policy)
    result = ex.calculate_scenario_exposure(
        scenario, basis="total_requirement", bundle=real_bundle, policy=policy
    )
    entry = result.ranking[0]
    contribution = entry.contributions[0]

    pair = real_bundle.pair(entry.industry_id, "brent_crude_usd_bbl")
    with decimal.localcontext() as ctx:
        ctx.prec = 5000
        reference = (
            Decimal(pair.sign)
            * scenario.shocks[0].signed_magnitude_fraction
            * pair.total_requirement_exposure
        )
    assert contribution.contribution == reference

    magnitude_digits = len(scenario.shocks[0].signed_magnitude_fraction.as_tuple().digits)
    coefficient_digits = len(pair.total_requirement_exposure.as_tuple().digits)
    assert magnitude_digits > 60
    assert len(contribution.contribution.as_tuple().digits) > 60
    assert len(contribution.contribution.as_tuple().digits) <= (
        magnitude_digits + coefficient_digits
    )


def test_the_exact_decomposition_holds_for_a_long_magnitude(tmp_path, policy, real_bundle):
    """``direct + propagated == total`` is the claim the report prints; it must not be
    true only for short inputs."""
    scenario = long_scenario(tmp_path, policy, tag="long-decomposition")
    result = ex.calculate_scenario_exposure(
        scenario, basis="total_requirement", bundle=real_bundle, policy=policy
    )
    for entry in result.ranking:
        assert contract.exact_total([entry.direct_component, entry.propagated_component]) == (
            entry.net_exposure
        )
        for contribution in entry.contributions:
            assert contract.exact_total(
                [contribution.direct_component, contribution.propagated_component]
            ) == contribution.contribution


def test_a_long_magnitude_gives_the_same_answer_in_every_ambient_context(
    tmp_path, policy, real_bundle
):
    scenario = long_scenario(tmp_path, policy, tag="long-ambient")
    seen = {
        under(
            prec,
            rounding,
            lambda: tuple(
                (entry.industry_id, entry.canonical_net_exposure, str(entry.rank))
                for entry in ex.calculate_scenario_exposure(
                    scenario, basis="total_requirement", bundle=real_bundle, policy=policy
                ).ranking
            ),
        )
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(seen) == 1


def test_a_fixed_sixty_digit_context_would_have_truncated_that_product(
    tmp_path, policy, real_bundle
):
    """Mutation check on the ceiling itself, not on the ambient context.

    This is the arithmetic the module performed while one context was pinned at 60
    digits. It is well-defined and deterministic -- which is exactly why the defect was
    invisible -- and it is not the exact answer.
    """
    scenario = long_scenario(tmp_path, policy, tag="long-ceiling")
    result = ex.calculate_scenario_exposure(
        scenario, basis="total_requirement", bundle=real_bundle, policy=policy
    )
    contribution = result.ranking[0].contributions[0]
    pair = real_bundle.pair(result.ranking[0].industry_id, "brent_crude_usd_bbl")

    ceiling = decimal.Context(prec=60, rounding=decimal.ROUND_HALF_EVEN)
    with decimal.localcontext(ceiling):
        truncated = (
            Decimal(pair.sign)
            * scenario.shocks[0].signed_magnitude_fraction
            * pair.total_requirement_exposure
        )
    assert truncated != contribution.contribution
    assert len(truncated.as_tuple().digits) == 60


def test_the_derived_precision_never_rounds(tmp_path, policy, real_bundle):
    """``Inexact`` is trapped, so a short derivation raises rather than rounding.

    Asserting the trap is set proves the intent; running the long scenario through the
    engine proves the derivations are actually wide enough for the trap not to fire.
    """
    for width in (1, 2, 17, 60, 200):
        context = contract.exact_context(width)
        assert context.traps[decimal.Inexact] is True
        assert context.prec == width

    scenario = long_scenario(tmp_path, policy, tag="long-trap")
    ex.calculate_scenario_exposure(
        scenario, basis="total_requirement", bundle=real_bundle, policy=policy
    )
    ex.calculate_scenario_exposure(
        scenario, basis="direct", bundle=real_bundle, policy=policy
    )


def test_the_quotients_keep_the_precision_they_shipped_with(tmp_path, policy, real_bundle):
    """The index and the ratio do not terminate, so their width is a presentation choice.

    Widening it would change every published figure. 28 is what shipped, so 28 is what
    these must still be -- including when the magnitude driving them is long.
    """
    assert ex._QUOTIENT_CONTEXT.prec == 28

    scenario = context_scenario(tmp_path, policy)
    result = ex.calculate_scenario_exposure(
        scenario, basis="total_requirement", bundle=real_bundle, policy=policy
    )
    entry = result.ranking[1]
    assert str(entry.relative_exposure_index) == "23.27169836798944487889057774"
    assert str(entry.cancellation_ratio) == "0.006815722200303706405239369890"

    long_result = ex.calculate_scenario_exposure(
        long_scenario(tmp_path, policy, tag="long-quotient"),
        basis="total_requirement",
        bundle=real_bundle,
        policy=policy,
    )
    for ranked in long_result.ranking:
        assert len(ranked.relative_exposure_index.as_tuple().digits) <= 28


def test_sign_and_magnitude_are_taken_without_a_context(tmp_path, policy, real_bundle):
    """``abs()`` and unary minus round; ``copy_abs`` and ``copy_negate`` do not.

    Both appear in the ranking key and in the cancellation, so at a low precision the
    unfixed forms would collapse distinct exposures into equal keys and rank industries
    by identifier instead of by exposure.
    """
    value = Decimal("0.0027230587343272067")
    rounded = {
        under(prec, rounding, lambda: str(abs(value))) for prec, rounding in AMBIENT_CONTEXTS
    }
    exact = {
        under(prec, rounding, lambda: str(value.copy_abs()))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(rounded) > 1, "if abs() were context-free this guard would prove nothing"
    assert len(exact) == 1

    scenario = context_scenario(tmp_path, policy)
    cancellations = {
        under(
            prec,
            rounding,
            lambda: tuple(
                contract.decimal_text(entry.cancellation)
                for entry in ex.calculate_scenario_exposure(
                    scenario, basis="total_requirement", bundle=real_bundle, policy=policy
                ).ranking
            ),
        )
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(cancellations) == 1


# ---------------------------------------------------------------------------
# The artifact loader is context-independent too
#
# The loader was the last place an ambient context still reached. Its coefficient
# agreement check computed `abs(left - right)` -- two context operations in one
# expression -- and `ExposurePair.propagated_exposure` computed `total - direct` in
# whatever context its reader happened to carry.
#
# The agreement check is not cosmetic: it decides whether a published artifact is
# accepted at all. A comparison that depends on a global some other library set is a
# validation decision made by something outside the project.
# ---------------------------------------------------------------------------


SCENARIO_MODULES = ("contract.py", "artifacts.py", "exposure.py", "report.py", "__main__.py")
SCENARIO_SOURCE_DIR = ROOT / "src" / "thai_supply_chain_ews" / "scenario"

#: Integer operands that may legitimately be negated. Keyed by (module, function, name)
#: so an addition anywhere else still has to be justified rather than inheriting an
#: exemption from a name that happens to match.
INTEGER_UNARY_ALLOWLIST = {
    # `point` is the index of the decimal point within a digit string: an int used to
    # build a slice, never a Decimal.
    ("contract.py", "decimal_text", "point"),
}


def unsafe_sign_operations(source: str, module: str) -> list[tuple[int, str]]:
    """Every unary minus/plus and builtin ``abs()`` that is not provably not a Decimal.

    Fail-closed on purpose. Deciding an operand's type statically is not possible in
    general, so anything that is not obviously an integer is reported and has to be
    either rewritten with ``copy_negate``/``copy_abs`` or declared in the allowlist
    above with a reason. Constants and ``len(...)`` are allowed outright because neither
    can produce a Decimal.

    This reads the syntax tree, so the prose in this file -- which necessarily writes
    ``abs()`` and ``-value`` in order to describe them -- is not matched.
    """
    tree = ast.parse(source)
    owner: dict[int, str] = {}
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(function):
                owner[id(node)] = function.name

    def provably_not_decimal(node) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return True
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "len"
        )

    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            operand, label = node.operand, "unary sign"
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "abs"
        ):
            operand, label = (node.args[0] if node.args else None), "builtin abs()"
        else:
            continue
        if operand is not None and provably_not_decimal(operand):
            continue
        if isinstance(operand, ast.Name) and (
            module, owner.get(id(node), "<module>"), operand.id
        ) in INTEGER_UNARY_ALLOWLIST:
            continue
        findings.append((node.lineno, label))
    return findings


def test_no_scenario_module_signs_a_decimal_through_the_ambient_context():
    """``-x`` and ``abs(x)`` round; ``copy_negate`` and ``copy_abs`` do not.

    Both defects that reached the published figures were of exactly this shape, and one
    of them hid inside an argument -- ``helper(-value)`` negates in the *caller's*
    context, because arguments are evaluated before the callee opens its own. A reviewer
    will not reliably spot that, so it is checked mechanically.
    """
    offences = {}
    for module in SCENARIO_MODULES:
        source = (SCENARIO_SOURCE_DIR / module).read_text(encoding="utf-8")
        findings = unsafe_sign_operations(source, module)
        if findings:
            offences[module] = findings
    assert not offences, (
        "use copy_negate()/copy_abs(), or declare an integer operand in "
        f"INTEGER_UNARY_ALLOWLIST: {offences}"
    )


def test_that_guard_would_catch_a_reintroduced_defect():
    """Mutation check on the guard itself.

    Each snippet is a form that actually shipped and had to be corrected. If the guard
    passed them, the test above would be decoration.
    """
    reintroduced = [
        "def f(a, b):\n    return total([a, -b])\n",
        "def f(x):\n    return abs(x)\n",
        "def f(x, y):\n    return sorted(v, key=lambda e: (-abs(e.net_exposure), e.id))\n",
        "def f(fraction, direction):\n"
        '    return fraction if direction == "increase" else -fraction\n',
    ]
    for snippet in reintroduced:
        assert unsafe_sign_operations(snippet, "contract.py"), snippet

    permitted = [
        "def f(xs):\n    return xs[-1]\n",
        "EMIN = -999999\n",
        "def decimal_text(s, point):\n    return s[:point] if point > 0 else -point\n",
        "def f(xs):\n    return abs(len(xs))\n",
        "def f(v):\n    return v.copy_negate().copy_abs()\n",
    ]
    for snippet in permitted:
        module = "contract.py" if "point" in snippet else "exposure.py"
        assert not unsafe_sign_operations(snippet, module), snippet


def test_the_allowlist_names_only_operands_that_still_exist():
    """A stale exemption is a hole. Each entry must still match a real function."""
    for module, function, name in INTEGER_UNARY_ALLOWLIST:
        tree = ast.parse((SCENARIO_SOURCE_DIR / module).read_text(encoding="utf-8"))
        target = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == function
            ),
            None,
        )
        assert target is not None, f"{module}:{function} no longer exists"
        assert any(
            isinstance(node, ast.Name) and node.id == name for node in ast.walk(target)
        ), f"{module}:{function} no longer uses {name}"


def bundle_fingerprint(bundle) -> tuple:
    """Every Decimal the loader produced, as text, plus the declared digests."""
    return (
        tuple(
            (
                pair.industry_id,
                pair.channel,
                str(pair.direct_exposure),
                str(pair.total_requirement_exposure),
                str(pair.published_indirect_exposure),
                str(pair.propagated_exposure),
                contract.decimal_text(pair.propagated_exposure),
                str(pair.sign),
            )
            for pair in sorted(bundle.pairs, key=lambda p: p.key)
        ),
        tuple(
            (declaration.name, declaration.sha256, declaration.digest_representation)
            for declaration in sorted(bundle.declarations, key=lambda d: d.name)
        ),
    )


def test_loading_the_bundle_is_identical_under_every_ambient_context():
    """The whole loader, including the agreement check it runs on the way through."""
    policy = contract.load_policy(POLICY_PATH)
    fingerprints = {
        under(
            prec,
            rounding,
            lambda: bundle_fingerprint(
                art.load_artifact_bundle(ROOT, policy=policy, policy_path=POLICY_PATH)
            ),
        )
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(fingerprints) == 1


def test_the_agreement_tolerance_decision_is_identical_under_every_ambient_context(
    real_bundle,
):
    """C3 stays authoritative and the 1e-15 bound is unchanged; only the arithmetic moved.

    The differences in the published artifacts are around 1e-17, so the check must keep
    accepting them, and it must accept them for the same reason in every context.
    """
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["cross_artifact_agreement"]
    assert raw["authoritative_coefficient_source"] == "exposure_matrix"
    assert Decimal(str(raw["coefficient_agreement_tolerance"])) == Decimal("1.0e-15")

    tolerance = Decimal("1.0e-15")
    mediators = {(m.industry_id, m.channel): m for m in real_bundle.mediators}
    decisions = set()
    for prec, rounding in AMBIENT_CONTEXTS:

        def decide():
            verdicts = []
            for pair in sorted(real_bundle.pairs, key=lambda p: p.key):
                mediator = mediators.get(pair.key)
                if mediator is None:
                    continue
                for left, right in (
                    (pair.direct_exposure, mediator.pair_direct_exposure),
                    (pair.total_requirement_exposure, mediator.pair_total_exposure),
                ):
                    difference = contract.exact_difference(left, right).copy_abs()
                    verdicts.append((str(difference), difference > tolerance))
            return tuple(verdicts)

        decisions.add(under(prec, rounding, decide))
    assert len(decisions) == 1
    assert not any(exceeded for _, exceeded in next(iter(decisions)))


def test_the_replaced_expressions_really_were_context_sensitive(real_bundle):
    """Mutation check on both halves of the expression that was removed.

    Worth being precise about what this does and does not show. For the artifacts as
    published, the agreement differences are around 1e-17 and carry so few significant
    digits that rounding them could not have flipped an accept into a reject: the fix
    removes a latent dependence rather than correcting a decision that was wrong. The
    dependence is real all the same, and on values with a full complement of digits --
    the coefficients themselves, and the subtraction behind ``propagated_exposure`` --
    both ``abs()`` and ``-`` visibly round.
    """
    pair = max(real_bundle.pairs, key=lambda p: len(p.direct_exposure.as_tuple().digits))
    assert len(pair.direct_exposure.as_tuple().digits) > 6

    ambient_abs = {
        under(prec, rounding, lambda: str(abs(pair.direct_exposure)))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    exact_abs = {
        under(prec, rounding, lambda: str(pair.direct_exposure.copy_abs()))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(ambient_abs) > 1, "if abs() were context-free this guard proves nothing"
    assert len(exact_abs) == 1

    ambient_sub = {
        under(
            prec,
            rounding,
            lambda: str(pair.total_requirement_exposure - pair.direct_exposure),
        )
        for prec, rounding in AMBIENT_CONTEXTS
    }
    exact_sub = {
        under(prec, rounding, lambda: str(pair.propagated_exposure))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(ambient_sub) > 1, "if subtraction were context-free this proves nothing"
    assert len(exact_sub) == 1


def test_the_propagated_exposure_property_is_identical_under_every_ambient_context(
    real_bundle,
):
    """It is public on an immutable record, so any reader can touch it in any context."""
    for pair in real_bundle.pairs:
        rendered = {
            under(prec, rounding, lambda pair=pair: str(pair.propagated_exposure))
            for prec, rounding in AMBIENT_CONTEXTS
        }
        assert len(rendered) == 1, pair.key
        assert contract.exact_total(
            [pair.direct_exposure, pair.propagated_exposure]
        ) == pair.total_requirement_exposure


def result_fingerprint(result) -> tuple:
    """Every Decimal the engine stored, in raw form, plus the order it ranked them in.

    ``str`` rather than the canonical spelling on purpose: canonicalisation strips
    trailing zeros, so it would hide a value that came back with a different scale
    because something rounded it. This is the strictest comparison available.
    """
    return (
        str(result.relative_index_denominator),
        result.no_ranking_reason,
        tuple(entry.industry_id for entry in result.ranking),
        tuple(
            (
                entry.industry_id,
                entry.rank,
                entry.direction,
                str(entry.net_exposure),
                str(entry.direct_component),
                str(entry.propagated_component),
                str(entry.gross_absolute_contribution),
                str(entry.cancellation),
                str(entry.cancellation_ratio),
                str(entry.relative_exposure_index),
                tuple(
                    (
                        channel.channel,
                        str(channel.contribution),
                        str(channel.direct_component),
                        str(channel.propagated_component),
                    )
                    for channel in entry.contributions
                ),
            )
            for entry in result.industries
        ),
    )


@pytest.mark.parametrize("basis", ["direct", "total_requirement"])
def test_every_stored_decimal_and_the_ranking_order_survive_any_context(
    basis, tmp_path, policy, real_bundle
):
    scenario = context_scenario(tmp_path, policy)
    fingerprints = {
        under(
            prec,
            rounding,
            lambda: result_fingerprint(
                ex.calculate_scenario_exposure(
                    scenario, basis=basis, bundle=real_bundle, policy=policy
                )
            ),
        )
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(fingerprints) == 1

    fingerprint = next(iter(fingerprints))
    assert fingerprint[0] != "None"
    assert len(fingerprint[2]) > 1


def test_the_index_denominator_is_the_largest_absolute_net_in_every_context(
    tmp_path, policy, real_bundle
):
    """The denominator sets the scale of every published index, so it must not move."""
    scenario = context_scenario(tmp_path, policy)
    for prec, rounding in AMBIENT_CONTEXTS:
        result = under(
            prec,
            rounding,
            lambda: ex.calculate_scenario_exposure(
                scenario, basis="total_requirement", bundle=real_bundle, policy=policy
            ),
        )
        largest = max(entry.net_exposure.copy_abs() for entry in result.ranking)
        assert result.relative_index_denominator == largest
        assert str(result.relative_index_denominator) == str(largest)
        assert result.ranking[0].relative_exposure_index.copy_abs() == Decimal(100)
