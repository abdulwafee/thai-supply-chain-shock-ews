"""Structural exposure scenarios: a user states a hypothetical upstream shock.

The question this package will answer is narrow on purpose: given a hypothetical
price movement in an upstream commodity, which of the twelve Thai manufacturing
industry groups were, in the 2015 NESDC benchmark structure, most exposed to it.
That is a statement about accounting ratios, not about the future. It is not a
probability, not a forecast, not an elasticity, not a causal effect and not a
predicted percentage change in anything, and no artifact in this repository would
support any of those.

**Phase 1 is the input contract.** :mod:`contract` reads the
policy in ``configs/structural_exposure_scenario.yaml``, validates a scenario
document against ``schemas/scenario_input.schema.yaml``, and produces an immutable
:class:`~contract.ValidatedScenario` with a canonical digest. It loads no exposure
artifact, computes no exposure, ranks nothing, renders nothing and writes nothing.
The calculation, reporting and command-line layers are later phases and are
deliberately absent rather than stubbed: an entry point that exists and does not
work is worse than one that is not there yet.

**Phase 2 adds the artifacts and the arithmetic.** :mod:`artifacts` verifies and loads
the four pinned public documents the calculation may read — nothing else, no directory
scan, no fallback. :mod:`exposure` turns a validated scenario, an explicitly chosen
basis and that verified bundle into signed structural contributions, industry
aggregates and a ranking. Both are pure: they read the pinned files, compute in exact
decimal, and write nothing.

There is still no command-line layer, no renderer and no result schema. Those are a
later phase and are deliberately absent rather than stubbed.

Only the reviewed surface is exported here, so nothing downstream can come to depend on
an interface that has not been agreed.
"""

from __future__ import annotations

from thai_supply_chain_ews.scenario.artifacts import (
    ARTIFACT_NAMES,
    SUPPORTED_DIGEST_REPRESENTATIONS,
    ArtifactBundle,
    ArtifactDeclaration,
    ArtifactIntegrityError,
    ExposurePair,
    Industry,
    Mediator,
    PriceStage,
    load_artifact_bundle,
    read_artifact_declarations,
)
from thai_supply_chain_ews.scenario.contract import (
    CONTRACT_ERROR_CODES,
    DEFAULT_POLICY_PATH,
    INPUT_SCHEMA_VERSION,
    REGISTERED_CHANNELS,
    STRUCTURAL_REFERENCE_YEAR,
    WARNING_CODES,
    ChannelPolicy,
    MagnitudePolicy,
    ScenarioContractError,
    ScenarioInternalError,
    ScenarioPolicy,
    ScenarioPolicyError,
    ScenarioWarning,
    UnsupportedChannelError,
    ValidatedScenario,
    ValidatedShock,
    canonical_input_sha256,
    canonical_scenario_payload,
    decimal_text,
    load_policy,
    load_scenario_document,
    validate_scenario_document,
)
from thai_supply_chain_ews.scenario.exposure import (
    BASIS_DIRECT,
    BASIS_TOTAL_REQUIREMENT,
    DIRECTION_LABELS,
    EXCLUSION_REASONS,
    NO_RANKING_REASONS,
    SUPPORTED_BASES,
    TIE_TOLERANCE,
    ChannelContribution,
    ExcludedPair,
    IndustryExposure,
    ScenarioExposureResult,
    calculate_scenario_exposure,
)

__all__ = [
    # --- Phase 1: the input contract ---
    "CONTRACT_ERROR_CODES",
    "DEFAULT_POLICY_PATH",
    "INPUT_SCHEMA_VERSION",
    "REGISTERED_CHANNELS",
    "STRUCTURAL_REFERENCE_YEAR",
    "WARNING_CODES",
    "ChannelPolicy",
    "MagnitudePolicy",
    "ScenarioContractError",
    "ScenarioInternalError",
    "ScenarioPolicy",
    "ScenarioPolicyError",
    "ScenarioWarning",
    "UnsupportedChannelError",
    "ValidatedScenario",
    "ValidatedShock",
    "canonical_input_sha256",
    "canonical_scenario_payload",
    "contract",
    "decimal_text",
    "load_policy",
    "load_scenario_document",
    "validate_scenario_document",
    # --- Phase 2: pinned artifacts and the calculation ---
    "ARTIFACT_NAMES",
    "BASIS_DIRECT",
    "BASIS_TOTAL_REQUIREMENT",
    "DIRECTION_LABELS",
    "EXCLUSION_REASONS",
    "NO_RANKING_REASONS",
    "SUPPORTED_BASES",
    "SUPPORTED_DIGEST_REPRESENTATIONS",
    "TIE_TOLERANCE",
    "ArtifactBundle",
    "ArtifactDeclaration",
    "ArtifactIntegrityError",
    "ChannelContribution",
    "ExcludedPair",
    "ExposurePair",
    "Industry",
    "IndustryExposure",
    "Mediator",
    "PriceStage",
    "ScenarioExposureResult",
    "artifacts",
    "calculate_scenario_exposure",
    "exposure",
    "load_artifact_bundle",
    "read_artifact_declarations",
]
