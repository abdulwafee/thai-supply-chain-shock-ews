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
import itertools
from decimal import Decimal
from pathlib import Path

import pytest

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


def test_no_phase_three_module_exists_yet():
    package = EXPOSURE_SOURCE.parent
    assert sorted(p.name for p in package.glob("*.py")) == [
        "__init__.py", "artifacts.py", "contract.py", "exposure.py"
    ]


def test_the_public_api_exposes_the_reviewed_phase_two_names_and_no_more():
    from thai_supply_chain_ews import scenario

    assert "calculate_scenario_exposure" in scenario.__all__
    assert "load_artifact_bundle" in scenario.__all__
    for name in ("main", "cli", "render", "report", "run", "predict", "forecast",
                 "fetch", "download"):
        assert name not in scenario.__all__
    for name in ("_rank", "_aggregate", "_contribution", "_require_basis",
                 "_exclusion_reason", "_exclusion_detail"):
        assert name not in scenario.__all__
        assert not hasattr(scenario, name)
        assert hasattr(ex, name)
