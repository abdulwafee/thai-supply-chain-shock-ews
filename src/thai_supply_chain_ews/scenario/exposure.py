"""The calculation: a validated scenario and pinned coefficients become a ranking.

Deterministic arithmetic over published input-output accounting ratios. Nothing here
estimates, fits, infers or predicts. The result says which industries were most exposed
to a shocked sector in the 2015 benchmark structure, scaled by the magnitude the user
stated — a rescaling of numbers somebody else published, not a claim about the future.

Four decisions carry the weight.

**The basis is chosen by the caller, never here.** ``configs/industry_exposure.yaml``
registers the direct matrix as primary and the total-requirement matrix as a
sensitivity view that must not silently replace it. So there is no default: a missing
or unsupported basis is refused, and the basis that was used is carried on the result
where a reader cannot miss it.

**The propagated component is derived, not read.** ``total_requirement - direct`` in
exact decimal, which makes ``direct + propagated == total_requirement`` true by
construction. The artifact's own ``indirect_exposure`` field disagrees with that
identity by up to 6e-17 because it was written by float64 arithmetic; it is preserved
as a published fact and is not what the arithmetic uses.

**An unusable pair is excluded, never zeroed.** A pair with no resolved direction sign,
or one the exposure matrix marks ineligible, is dropped from scoring with a
machine-readable reason and its identity intact. Treating it as a zero contribution
would assert that the industry has no exposure through that channel, which is a
different and much stronger claim than "this pair cannot be scored".

**Cancellation is shown, not netted away.** A scenario mixing an increase and a
decrease can produce a small net exposure out of two large opposing contributions. The
net alone would hide that, so every industry carries its gross absolute contribution
and the amount that cancelled beside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from thai_supply_chain_ews.scenario.artifacts import ArtifactBundle, ExposurePair
from thai_supply_chain_ews.scenario.contract import (
    ScenarioContractError,
    ScenarioInternalError,
    ScenarioPolicy,
    ValidatedScenario,
    decimal_text,
    exact_difference,
    exact_product,
    exact_total,
    fixed_context,
)

__all__ = [
    "BASIS_DIRECT",
    "BASIS_TOTAL_REQUIREMENT",
    "DIRECTION_LABELS",
    "EXCLUSION_REASONS",
    "NO_RANKING_REASONS",
    "SUPPORTED_BASES",
    "TIE_TOLERANCE",
    "ChannelContribution",
    "ExcludedPair",
    "IndustryExposure",
    "ScenarioExposureResult",
    "calculate_scenario_exposure",
]

BASIS_DIRECT = "direct"
BASIS_TOTAL_REQUIREMENT = "total_requirement"
SUPPORTED_BASES = (BASIS_DIRECT, BASIS_TOTAL_REQUIREMENT)

#: Why a published pair could not be scored. Stable and machine-readable, because a
#: caller has to be able to distinguish "we chose not to use this" from "there is
#: nothing here" without reading prose.
EXCLUSION_REASONS = frozenset(
    {
        "direction_sign_unresolved",
        "pair_not_feature_eligible",
        "pair_not_published",
    }
)

#: Why a scenario produced no ranking at all. Both are accepted outcomes, not errors.
NO_RANKING_REASONS = frozenset({"all_magnitudes_zero", "all_net_exposures_zero"})

DIRECTION_LABELS = ("stress_pressure", "relief_pressure", "neutral")

#: Two industries are tied when their absolute net exposures differ by no more than
#: this. Declared validation policy, not an estimated threshold: it exists because
#: decimal arithmetic over published coefficients can leave a difference far below any
#: quantity worth distinguishing, and a ranking that separates two industries by 1e-20
#: is reporting noise as order.
TIE_TOLERANCE = Decimal("1e-12")

# ---------------------------------------------------------------------------
# Arithmetic
#
# The exact operations live in `contract`, which `artifacts` can also import -- the
# loader needs the same guarantees and cannot import this module, since this one imports
# it. One implementation, used by both, rather than two copies of the same reasoning.
#
# Division is the exception and stays here, because its width is a property of this
# module's output rather than of the operands. The relative index and the cancellation
# ratio are genuine non-terminating quotients where no precision is exact, so the width
# is a presentation choice; 28 is the choice already shipped, and pinning it preserves
# every published figure rather than silently lengthening it.
_QUOTIENT_CONTEXT = fixed_context(28)


@dataclass(frozen=True)
class ChannelContribution:
    """One industry/channel contribution under the selected basis."""

    channel: str
    io_sector_code: str
    direction: str
    signed_magnitude_fraction: Decimal
    sign: int
    coefficient: Decimal
    contribution: Decimal
    direct_component: Decimal
    propagated_component: Decimal | None
    propagated_supported: bool
    published_indirect_exposure: Decimal
    proxy_fit_status: str
    quality_flag: str

    @property
    def canonical_contribution(self) -> str:
        # No context needed: `decimal_text` reads the stored representation and does no
        # arithmetic, so it cannot round whatever the ambient settings are.
        return decimal_text(self.contribution)


@dataclass(frozen=True)
class ExcludedPair:
    """A published pair that could not be scored, with its identity kept."""

    industry_id: str
    channel: str
    reason: str
    detail: str


@dataclass(frozen=True)
class IndustryExposure:
    """One industry's aggregate under the selected basis."""

    industry_id: str
    industry_name: str
    basis: str
    net_exposure: Decimal
    direct_component: Decimal
    propagated_component: Decimal | None
    propagated_supported: bool
    gross_absolute_contribution: Decimal
    contributions: tuple[ChannelContribution, ...]
    excluded_pairs: tuple[ExcludedPair, ...]
    rank: int | None = None
    relative_exposure_index: Decimal | None = None
    tied_with: tuple[str, ...] = ()

    @property
    def cancellation(self) -> Decimal:
        """How much opposing movement the net figure absorbed.

        A property, so it is computed wherever a reader touches it rather than inside
        the calculation. That is exactly why it derives its own precision: otherwise
        this one subtraction would be the only part of the result that depended on
        whatever the caller's ambient context happened to be.
        """
        return exact_difference(
            self.gross_absolute_contribution, self.net_exposure.copy_abs()
        )

    @property
    def cancellation_ratio(self) -> Decimal | None:
        if self.gross_absolute_contribution == 0:
            return None
        with localcontext(_QUOTIENT_CONTEXT):
            return self.cancellation / self.gross_absolute_contribution

    @property
    def direction(self) -> str:
        if self.net_exposure > 0:
            return "stress_pressure"
        if self.net_exposure < 0:
            return "relief_pressure"
        return "neutral"

    @property
    def canonical_net_exposure(self) -> str:
        return decimal_text(self.net_exposure)


@dataclass(frozen=True)
class ScenarioExposureResult:
    """Everything the calculation produced, with the basis it was produced under."""

    scenario_id: str
    basis: str
    basis_role: str
    registered_primary_basis: str
    structural_reference_year: int
    ranking: tuple[IndustryExposure, ...]
    unranked: tuple[IndustryExposure, ...]
    unscorable: tuple[IndustryExposure, ...]
    excluded_pairs: tuple[ExcludedPair, ...]
    no_ranking_reason: str | None
    relative_index_denominator: Decimal | None
    scenario_input_sha256: str
    artifact_digests: dict

    @property
    def has_ranking(self) -> bool:
        return bool(self.ranking)

    @property
    def industries(self) -> tuple[IndustryExposure, ...]:
        """Every industry the calculation produced a figure for, ranked or not."""
        return (self.ranking or self.unranked) + self.unscorable

    @property
    def unscorable_industry_ids(self) -> tuple[str, ...]:
        return tuple(entry.industry_id for entry in self.unscorable)

    def industry(self, industry_id: str) -> IndustryExposure | None:
        for entry in self.industries:
            if entry.industry_id == industry_id:
                return entry
        return None


def _require_basis(basis, policy: ScenarioPolicy) -> str:
    """The basis is the caller's decision and must be stated.

    Refused through the Phase 1 contract taxonomy, because from the user's point of
    view an omitted or misspelled ``--basis`` is a malformed request rather than a
    broken artifact.
    """
    if basis is None:
        raise ScenarioContractError(
            "a basis is required and has no default: "
            f"{policy.registered_primary_basis!r} is the registered primary matrix and "
            f"{BASIS_TOTAL_REQUIREMENT!r} is a structural sensitivity view. Choosing for you "
            "would be the silent promotion the policy exists to prevent",
            code="bad_field_type",
            field="basis",
        )
    if basis not in policy.supported_bases:
        raise ScenarioContractError(
            f"basis {basis!r} is not supported; expected one of {list(policy.supported_bases)}",
            code="bad_field_type",
            field="basis",
        )
    return basis


def calculate_scenario_exposure(scenario: ValidatedScenario, *, basis,
                                bundle: ArtifactBundle,
                                policy: ScenarioPolicy) -> ScenarioExposureResult:
    """Score a validated scenario against the pinned coefficients.

    Pure and deterministic: the same scenario, basis and bundle give the same result,
    the order the author listed the shocks in changes nothing because Phase 1 already
    sorted them canonically, and the caller's ambient decimal settings change nothing
    because every operation derives its own exact precision from its own operands.

    Each helper enters and leaves its context with ``localcontext``, which restores the
    caller's on the way out including when an operation raises, so scoring a scenario
    never leaves a program's arithmetic altered.
    """
    from thai_supply_chain_ews.scenario.contract import canonical_input_sha256

    basis = _require_basis(basis, policy)
    basis_role = (
        "registered_primary"
        if basis == policy.registered_primary_basis
        else policy.total_requirement_role
    )
    propagated_supported = basis == BASIS_TOTAL_REQUIREMENT

    industries = []
    all_excluded: list[ExcludedPair] = []
    for industry in bundle.industries:
        contributions = []
        excluded = []
        for shock in scenario.shocks:
            pair = bundle.pair(industry.industry_id, shock.channel)
            if pair is None:
                excluded.append(
                    ExcludedPair(
                        industry_id=industry.industry_id, channel=shock.channel,
                        reason="pair_not_published",
                        detail="the exposure matrix publishes no row for this industry and channel",
                    )
                )
                continue
            reason = _exclusion_reason(pair)
            if reason is not None:
                excluded.append(
                    ExcludedPair(
                        industry_id=industry.industry_id, channel=shock.channel,
                        reason=reason, detail=_exclusion_detail(reason, pair),
                    )
                )
                continue
            contributions.append(_contribution(pair, shock, basis, propagated_supported))
        all_excluded.extend(excluded)
        industries.append(
            _aggregate(industry, basis, tuple(contributions), tuple(excluded),
                       propagated_supported)
        )

    scorable = any(entry.contributions for entry in industries)
    if not scorable:
        raise ScenarioContractError(
            "no industry/channel pair in this scenario can be scored: every published pair is "
            "either ineligible or has no resolved direction sign. Nothing was coerced to zero, "
            "and the excluded pairs are reported with their reasons",
            code="no_shocks",
            field="shocks",
            details={
                "excluded": [
                    {"industry_id": e.industry_id, "channel": e.channel, "reason": e.reason}
                    for e in all_excluded
                ][:24],
                "condition": "no_scorable_pairs",
            },
        )

    # An industry every one of whose pairs was excluded has no figure at all. Ranking
    # it at zero would say "no exposure through this channel", which is precisely the
    # coercion the pair-level exclusion exists to avoid — the same mistake, one level up.
    scorable_industries = [entry for entry in industries if entry.contributions]
    unscorable = tuple(
        entry for entry in sorted(industries, key=lambda e: e.industry_id)
        if not entry.contributions
    )

    ranking, unranked, reason, denominator = _rank(scorable_industries, scenario)
    return ScenarioExposureResult(
        scenario_id=scenario.scenario_id,
        basis=basis,
        basis_role=basis_role,
        registered_primary_basis=policy.registered_primary_basis,
        structural_reference_year=bundle.structural_reference_year,
        ranking=ranking,
        unranked=unranked,
        unscorable=unscorable,
        excluded_pairs=tuple(all_excluded),
        no_ranking_reason=reason,
        relative_index_denominator=denominator,
        scenario_input_sha256=canonical_input_sha256(scenario),
        artifact_digests={d.name: d.sha256 for d in bundle.declarations},
    )


def _exclusion_reason(pair: ExposurePair) -> str | None:
    if pair.sign is None:
        return "direction_sign_unresolved"
    if not pair.feature_eligible:
        return "pair_not_feature_eligible"
    return None


def _exclusion_detail(reason: str, pair: ExposurePair) -> str:
    if reason == "direction_sign_unresolved":
        return (
            f"direction channel is {pair.direction_channel!r} with no published sign, so a signed "
            "contribution cannot be formed. The coefficient is preserved, not treated as zero"
        )
    return (
        f"the exposure matrix marks this pair ineligible (proxy fitness "
        f"{pair.proxy_fit_status!r}). The coefficient is preserved, not treated as zero"
    )


def _contribution(pair: ExposurePair, shock, basis: str,
                  propagated_supported: bool) -> ChannelContribution:
    coefficient = pair.coefficient(basis)
    scale = exact_product(Decimal(pair.sign), shock.signed_magnitude_fraction)
    contribution = exact_product(scale, coefficient)
    direct_component = exact_product(scale, pair.direct_exposure)
    # `pair.propagated_exposure` is itself an exact `total - direct`, so it is read
    # rather than re-derived here: two derivations of one quantity are two places for
    # it to drift.
    propagated_component = (
        exact_product(scale, pair.propagated_exposure) if propagated_supported else None
    )
    if propagated_supported:
        # Exact by construction: propagated is derived as total - direct, so the two
        # scaled components must reconstruct the scaled total with no residual at all.
        if exact_total([direct_component, propagated_component]) != contribution:
            raise ScenarioInternalError(
                f"{pair.industry_id}/{pair.channel}: direct + propagated does not reconstruct "
                f"the total-requirement contribution exactly "
                f"({direct_component} + {propagated_component} != {contribution})"
            )
    return ChannelContribution(
        channel=pair.channel,
        io_sector_code=pair.io_sector_code,
        direction=shock.direction,
        signed_magnitude_fraction=shock.signed_magnitude_fraction,
        sign=pair.sign,
        coefficient=coefficient,
        contribution=contribution,
        direct_component=direct_component,
        propagated_component=propagated_component,
        propagated_supported=propagated_supported,
        published_indirect_exposure=pair.published_indirect_exposure,
        proxy_fit_status=pair.proxy_fit_status,
        quality_flag=pair.quality_flag,
    )


def _aggregate(industry, basis: str, contributions, excluded,
               propagated_supported: bool) -> IndustryExposure:
    net = exact_total(c.contribution for c in contributions)
    direct = exact_total(c.direct_component for c in contributions)
    gross = exact_total(c.contribution.copy_abs() for c in contributions)
    propagated = None
    if propagated_supported:
        propagated = exact_total(c.propagated_component for c in contributions)
        if exact_total([direct, propagated]) != net:
            raise ScenarioInternalError(
                f"{industry.industry_id}: aggregate direct + propagated does not reconstruct the "
                f"net exposure exactly ({direct} + {propagated} != {net})"
            )
    return IndustryExposure(
        industry_id=industry.industry_id,
        industry_name=industry.name_en,
        basis=basis,
        net_exposure=net,
        direct_component=direct,
        propagated_component=propagated,
        propagated_supported=propagated_supported,
        gross_absolute_contribution=gross,
        contributions=tuple(contributions),
        excluded_pairs=tuple(excluded),
    )


def _index(net: Decimal, denominator: Decimal) -> Decimal:
    """``100 * net / denominator``, at the fixed presentation precision.

    The multiplication is exact; the division generally is not, so it is pinned rather
    than left to whatever precision the process happens to carry.
    """
    numerator = exact_product(Decimal(100), net)
    with localcontext(_QUOTIENT_CONTEXT):
        return numerator / denominator


def _rank(industries, scenario: ValidatedScenario):
    """Order by absolute net exposure, with competition ranks and anchored ties.

    Two industries are tied when their absolute net exposures are within
    :data:`TIE_TOLERANCE`. Each candidate is compared against the **anchor** of the
    open tie group rather than against its immediate predecessor, so a run of values
    each just inside the tolerance of the last cannot chain into one enormous tie —
    which is how a tolerance quietly becomes a claim that everything is equal.
    """
    if scenario.all_shocks_are_zero:
        unranked = tuple(sorted(industries, key=lambda e: e.industry_id))
        return (), unranked, "all_magnitudes_zero", None

    # `copy_abs`/`copy_negate` throughout: `abs()` and unary minus round to the ambient
    # precision, which at a low one would collapse distinct exposures into equal sort
    # keys and rank two industries by their identifiers instead of their exposure.
    ordered = sorted(
        industries,
        key=lambda e: (e.net_exposure.copy_abs().copy_negate(), e.industry_id),
    )
    denominator = max(
        (e.net_exposure.copy_abs() for e in ordered), default=Decimal(0)
    )
    if denominator == 0:
        unranked = tuple(sorted(industries, key=lambda e: e.industry_id))
        return (), unranked, "all_net_exposures_zero", None

    groups: list[list] = []
    anchor: Decimal | None = None
    for entry in ordered:
        magnitude = entry.net_exposure.copy_abs()
        if anchor is not None and exact_difference(anchor, magnitude) <= TIE_TOLERANCE:
            groups[-1].append(entry)
        else:
            groups.append([entry])
            anchor = magnitude

    ranked = []
    position = 1
    for group in groups:
        members = tuple(sorted(e.industry_id for e in group))
        for entry in group:
            ranked.append(
                IndustryExposure(
                    industry_id=entry.industry_id,
                    industry_name=entry.industry_name,
                    basis=entry.basis,
                    net_exposure=entry.net_exposure,
                    direct_component=entry.direct_component,
                    propagated_component=entry.propagated_component,
                    propagated_supported=entry.propagated_supported,
                    gross_absolute_contribution=entry.gross_absolute_contribution,
                    contributions=entry.contributions,
                    excluded_pairs=entry.excluded_pairs,
                    rank=position,
                    relative_exposure_index=_index(entry.net_exposure, denominator),
                    tied_with=tuple(m for m in members if m != entry.industry_id),
                )
            )
        position += len(group)
    return tuple(ranked), (), None, denominator
