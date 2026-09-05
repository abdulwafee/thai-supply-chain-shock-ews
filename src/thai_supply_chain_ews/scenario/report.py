"""Result documents: what the calculation produced, written down without embellishment.

Phase 2 produced numbers. This module turns them into two documents -- one for a person
and one for a program -- and adds nothing that was not computed or published.

**Nothing here is nondeterministic.** No timestamp, no run identity, no hostname, no
absolute path, no random value. The same scenario, basis and artifacts produce
byte-identical JSON and byte-identical Markdown, every time and on every machine. A
document that changes between two runs of the same calculation cannot be diffed,
cached or quoted, and a timestamp is the usual reason one does.

**Every number is a canonical decimal string.** Serialising a coefficient as a JSON
float would undo the exact-decimal arithmetic the two previous phases were built
around, at the last possible moment and invisibly. ``json.dumps`` cannot encode a
:class:`~decimal.Decimal` at all, so this property fails loudly rather than silently if
a later change puts one in a payload.

**The Markdown says what the number is not.** A ranked table of scores invites every
reading the project has spent its life refusing -- probability, forecast, predicted
output loss, risk band, a recommendation. The disclaimer is fixed, is emitted with
every document, and cannot be switched off.

Mediator rows in an explanation are *corroboration*: they say which intermediate sector
a requirement came through in the 2015 benchmark table. They are an attribution of an
exact identity, not evidence of a causal path, and the documents say so.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import yaml

from thai_supply_chain_ews.scenario.artifacts import ArtifactBundle
from thai_supply_chain_ews.scenario.contract import (
    ScenarioContractError,
    ScenarioInternalError,
    ValidatedScenario,
    decimal_text,
)
from thai_supply_chain_ews.scenario.exposure import ScenarioExposureResult

__all__ = [
    "EXPLANATION_SCHEMA_VERSION",
    "LIMITATIONS",
    "RESULT_SCHEMA_PATH",
    "RESULT_SCHEMA_VERSION",
    "build_industry_explanation_document",
    "build_scenario_result_document",
    "render_industry_explanation_json",
    "render_industry_explanation_markdown",
    "render_scenario_result_json",
    "render_scenario_result_markdown",
    "validate_result_document",
]

RESULT_SCHEMA_VERSION = "structural_exposure_result_v1"
EXPLANATION_SCHEMA_VERSION = "structural_exposure_explanation_v1"

#: ``src/thai_supply_chain_ews/scenario/report.py`` -> repository root -> schemas/.
RESULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "scenario_result.schema.yaml"
)

#: Emitted verbatim on every document. Fixed, ordered, and not configurable: a caveat a
#: caller can turn off is a caveat that will be turned off.
LIMITATIONS = (
    "This is a structural exposure calculation over published input-output accounting "
    "ratios. It is not a probability, not a forecast, not a predicted percentage change "
    "in production, revenue or stress, not a causal effect, not an elasticity, not a "
    "registered risk band, and not a production or investment recommendation.",
    "The coefficients come from the NESDC Input-Output Table of Thailand 2015 and are "
    "held time-invariant under fixed proportions and no substitution. They describe 2015 "
    "purchasing patterns, not the date in the scenario.",
    "Results are conditional on the magnitudes the scenario states. The scenario is a "
    "hypothesis supplied by the reader; nothing here estimates how likely it is.",
    "Every industry/channel mapping is medium confidence and broader than the commodity "
    "it stands for. Aluminium and copper resolve to one official sector and are never "
    "independent evidence.",
    "The direct basis is the registered primary matrix. The total-requirement basis is a "
    "structural sensitivity view and does not replace it.",
    "Mediator rows attribute an exact accounting identity to the first intermediate "
    "sector purchased. They are corroboration, not evidence of a causal path.",
    "No model was trained, loaded or consulted. The locked final test remains sealed, no "
    "model is promoted, and no production deployment is authorised.",
)

#: The order channels appear in every document: canonical, so two runs cannot differ.
_CHANNEL_ORDER = "channel"

#: No serialisation context is needed. ``decimal_text`` builds its result from the
#: stored sign, digits and exponent and performs no arithmetic, so it cannot round
#: and cannot depend on ambient settings. It used to call ``normalize()``, which
#: does both, and this module carried a fixed context to contain that; the
#: containment moved to the source, where it belongs, and a wrapper here would now
#: be decoration.
_SERIALISATION_IS_CONTEXT_FREE = True


def _text(value) -> str | None:
    """A canonical decimal string, or ``None``. Never a float."""
    if value is None:
        return None
    if isinstance(value, float):
        raise ScenarioInternalError(
            f"a binary float ({value!r}) reached document serialisation; every numeric "
            "value in a result document must be an exact decimal"
        )
    if not isinstance(value, Decimal):
        raise ScenarioInternalError(
            f"expected a Decimal for serialisation, got {type(value).__name__}"
        )
    return decimal_text(value)


def _shock(shock) -> dict:
    return {
        "channel": shock.channel,
        "io_sector_code": shock.io_sector_code,
        "direction": shock.direction,
        "magnitude": _text(shock.magnitude),
        "magnitude_unit": shock.magnitude_unit,
        "magnitude_fraction": _text(shock.magnitude_fraction),
        "signed_magnitude_fraction": _text(shock.signed_magnitude_fraction),
        "note": shock.note,
    }


def _contribution(entry) -> dict:
    return {
        "channel": entry.channel,
        "io_sector_code": entry.io_sector_code,
        "direction": entry.direction,
        "sign": entry.sign,
        "signed_magnitude_fraction": _text(entry.signed_magnitude_fraction),
        "coefficient": _text(entry.coefficient),
        "contribution": _text(entry.contribution),
        "direct_component": _text(entry.direct_component),
        "propagated_component": _text(entry.propagated_component),
        "propagated_supported": entry.propagated_supported,
        "published_indirect_exposure": _text(entry.published_indirect_exposure),
        "proxy_fit_status": entry.proxy_fit_status,
        "quality_flag": entry.quality_flag,
    }


def _industry(entry) -> dict:
    return {
        "rank": entry.rank,
        "industry_id": entry.industry_id,
        "industry_name": entry.industry_name,
        "direction": entry.direction,
        "net_exposure": _text(entry.net_exposure),
        "relative_exposure_index": _text(entry.relative_exposure_index),
        "direct_component": _text(entry.direct_component),
        "propagated_component": _text(entry.propagated_component),
        "propagated_supported": entry.propagated_supported,
        "gross_absolute_contribution": _text(entry.gross_absolute_contribution),
        "cancellation": _text(entry.cancellation),
        "cancellation_ratio": _text(entry.cancellation_ratio),
        "tied_with": list(entry.tied_with),
        "contributions": [
            _contribution(c)
            for c in sorted(entry.contributions, key=lambda c: getattr(c, _CHANNEL_ORDER))
        ],
        "excluded_pairs": [
            {"channel": e.channel, "reason": e.reason, "detail": e.detail}
            for e in sorted(entry.excluded_pairs, key=lambda e: e.channel)
        ],
    }


def build_scenario_result_document(scenario: ValidatedScenario,
                                   result: ScenarioExposureResult,
                                   bundle: ArtifactBundle) -> dict:
    """The machine-readable result, fully determined by its three inputs."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "scenario_name": scenario.scenario_name,
            "scenario_date": scenario.scenario_date,
            "scenario_date_is_metadata_only": scenario.scenario_date_is_metadata_only,
            "coefficient_vintage_is_scenario_date": scenario.coefficient_vintage_is_scenario_date,
            "note": scenario.note,
            "canonical_input_sha256": result.scenario_input_sha256,
            "shocks": [_shock(s) for s in scenario.shocks],
            "warnings": [
                {"code": w.code, "message": w.message, "field": w.field, "channel": w.channel}
                for w in scenario.warnings
            ],
        },
        "basis": {
            "selected": result.basis,
            "role": result.basis_role,
            "registered_primary": result.registered_primary_basis,
            "structural_reference_year": result.structural_reference_year,
        },
        "artifacts": [
            {
                "name": d.name,
                "path": d.path,
                "sha256": d.sha256,
                "digest_representation": d.digest_representation,
            }
            for d in sorted(bundle.declarations, key=lambda d: d.name)
        ],
        "ranking": {
            "status": "ranked" if result.has_ranking else "not_ranked",
            "no_ranking_reason": result.no_ranking_reason,
            "relative_index_denominator": _text(result.relative_index_denominator),
            "industries": [_industry(e) for e in (result.ranking or result.unranked)],
        },
        "unscorable_industries": [_industry(e) for e in result.unscorable],
        "exclusions": [
            {
                "industry_id": e.industry_id,
                "channel": e.channel,
                "reason": e.reason,
                "detail": e.detail,
            }
            for e in sorted(result.excluded_pairs, key=lambda e: (e.industry_id, e.channel))
        ],
        "limitations": list(LIMITATIONS),
    }


def build_industry_explanation_document(scenario: ValidatedScenario,
                                        result: ScenarioExposureResult,
                                        bundle: ArtifactBundle, *, industry_id: str,
                                        mediator_limit: int) -> dict:
    """One industry's figures, with the published mediator rows behind each channel.

    ``mediator_limit`` is the caller's explicit choice. Nothing is summarised, reordered
    or interpolated: the rows are the pinned artifact's own, in its own rank order.
    """
    entry = result.industry(industry_id)
    if entry is None:
        known = sorted({e.industry_id for e in result.industries})
        raise ScenarioContractError(
            f"industry {industry_id!r} is not in this result; this scenario covers {known}",
            code="bad_field_type",
            field="industry",
            details={"industry_id": industry_id, "known": known},
        )
    channels = []
    for contribution in sorted(entry.contributions, key=lambda c: getattr(c, _CHANNEL_ORDER)):
        published = bundle.mediators_for(industry_id, contribution.channel)
        stage = bundle.price_stage_for(industry_id, contribution.channel)
        channels.append(
            {
                **_contribution(contribution),
                "price_stage": None if stage is None else stage.price_stage,
                "alignment_status": None if stage is None else stage.alignment_status,
                "shared_source_sector_warning": (
                    None if stage is None else stage.shared_source_sector_warning
                ),
                "mediators_shown": min(mediator_limit, len(published)),
                "mediators_published": len(published),
                "mediators": [
                    {
                        "rank": m.rank,
                        "intermediate_sector_code": m.intermediate_sector_code,
                        "intermediate_sector_label": m.intermediate_sector_label,
                        "contribution": _text(m.contribution),
                        "share_of_indirect": _text(m.share_of_indirect),
                        "cumulative_share": _text(m.cumulative_share),
                    }
                    for m in sorted(published, key=lambda m: m.rank)[:mediator_limit]
                ],
            }
        )
    return {
        "schema_version": EXPLANATION_SCHEMA_VERSION,
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "scenario_date": scenario.scenario_date,
            "canonical_input_sha256": result.scenario_input_sha256,
        },
        "basis": {
            "selected": result.basis,
            "role": result.basis_role,
            "registered_primary": result.registered_primary_basis,
            "structural_reference_year": result.structural_reference_year,
        },
        "artifacts": [
            {
                "name": d.name,
                "path": d.path,
                "sha256": d.sha256,
                "digest_representation": d.digest_representation,
            }
            for d in sorted(bundle.declarations, key=lambda d: d.name)
        ],
        "industry": {
            "industry_id": entry.industry_id,
            "industry_name": entry.industry_name,
            "rank": entry.rank,
            "direction": entry.direction,
            "net_exposure": _text(entry.net_exposure),
            "relative_exposure_index": _text(entry.relative_exposure_index),
            "direct_component": _text(entry.direct_component),
            "propagated_component": _text(entry.propagated_component),
            "propagated_supported": entry.propagated_supported,
            "gross_absolute_contribution": _text(entry.gross_absolute_contribution),
            "cancellation": _text(entry.cancellation),
            "cancellation_ratio": _text(entry.cancellation_ratio),
            "tied_with": list(entry.tied_with),
        },
        "channels": channels,
        "exclusions": [
            {"channel": e.channel, "reason": e.reason, "detail": e.detail}
            for e in sorted(entry.excluded_pairs, key=lambda e: e.channel)
        ],
        "mediator_interpretation": (
            "Mediator rows attribute an exact accounting identity to the first intermediate "
            "sector purchased in the 2015 benchmark table. They are structural corroboration, "
            "not evidence of a causal path."
        ),
        "limitations": list(LIMITATIONS),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _json(document: dict) -> str:
    """Compact-keyed, sorted, ASCII-safe JSON with a trailing newline."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def render_scenario_result_json(document: dict) -> str:
    return _json(document)


def render_industry_explanation_json(document: dict) -> str:
    return _json(document)


def _limitations_block(document: dict) -> list[str]:
    lines = ["## Limitations", ""]
    lines += [f"- {item}" for item in document["limitations"]]
    return lines


def _basis_block(document: dict) -> list[str]:
    basis = document["basis"]
    role = (
        "registered primary matrix"
        if basis["role"] == "registered_primary"
        else "structural sensitivity view -- it does not replace the registered primary matrix"
    )
    return [
        f"- **Basis:** `{basis['selected']}` -- {role}.",
        f"- **Registered primary basis:** `{basis['registered_primary']}`.",
        f"- **Structural reference year:** {basis['structural_reference_year']}.",
    ]


def _artifact_block(document: dict) -> list[str]:
    lines = ["## Artifact provenance", "",
             "| artifact | path | representation | sha256 |",
             "| --- | --- | --- | --- |"]
    for entry in document["artifacts"]:
        lines.append(
            f"| {entry['name']} | `{entry['path']}` | {entry['digest_representation']} "
            f"| `{entry['sha256']}` |"
        )
    return lines


def render_scenario_result_markdown(document: dict) -> str:
    """The same content as the JSON, arranged for a person. Deterministic."""
    scenario = document["scenario"]
    ranking = document["ranking"]
    lines: list[str] = [
        f"# Structural exposure -- {scenario['scenario_id']}",
        "",
        "**This is a conditional structural exposure calculation. It is not a probability, "
        "not a forecast, not a predicted percentage change in production, not a causal "
        "effect, not a risk band, and not an investment or production recommendation.**",
        "",
    ]
    if scenario["scenario_name"]:
        lines += [f"*{scenario['scenario_name']}*", ""]
    lines += ["## Scenario", ""]
    if scenario["scenario_date"]:
        lines.append(
            f"- **Scenario date:** {scenario['scenario_date']} -- metadata only; it selects no "
            "data and is not the vintage of the coefficients."
        )
    lines += _basis_block(document)
    lines.append(f"- **Canonical input digest:** `{scenario['canonical_input_sha256']}`")
    lines += ["", "| channel | I/O sector | direction | magnitude | as a fraction |",
              "| --- | --- | --- | --- | --- |"]
    for shock in scenario["shocks"]:
        lines.append(
            f"| `{shock['channel']}` | {shock['io_sector_code']} | {shock['direction']} "
            f"| {shock['magnitude']} {shock['magnitude_unit']} "
            f"| {shock['signed_magnitude_fraction']} |"
        )
    if scenario["warnings"]:
        lines += ["", "### Input warnings", ""]
        for warning in scenario["warnings"]:
            where = f" ({warning['channel']})" if warning["channel"] else ""
            lines.append(f"- `{warning['code']}`{where}: {warning['message']}")

    lines += ["", "## Ranking", ""]
    if ranking["status"] == "not_ranked":
        lines += [
            f"No ranking was produced: `{ranking['no_ranking_reason']}`.",
            "",
            "This is an accepted outcome, not an error. The figures below are reported "
            "without an order because nothing in this scenario separates one industry from "
            "another.",
            "",
        ]
    else:
        lines.append(
            f"Relative index denominator: `{ranking['relative_index_denominator']}` "
            "(the largest absolute net exposure in this scenario; the index is relative to it "
            "and has no absolute meaning)."
        )
        lines.append("")
    lines += ["| rank | industry | direction | net exposure | index | direct | propagated "
              "| gross | cancellation |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for entry in ranking["industries"]:
        propagated = entry["propagated_component"] or "n/a"
        lines.append(
            f"| {entry['rank'] if entry['rank'] is not None else '--'} "
            f"| {entry['industry_id']} {entry['industry_name']} | {entry['direction']} "
            f"| {entry['net_exposure']} | {entry['relative_exposure_index'] or '--'} "
            f"| {entry['direct_component']} | {propagated} "
            f"| {entry['gross_absolute_contribution']} | {entry['cancellation']} |"
        )

    if document["unscorable_industries"]:
        lines += ["", "## Industries with no scorable pair", "",
                  "These are **not** ranked at zero. Every published pair for them was "
                  "excluded, which is different from an exposure of nothing.", "",
                  "| industry | excluded channels |", "| --- | --- |"]
        for entry in document["unscorable_industries"]:
            channels = ", ".join(f"`{e['channel']}`" for e in entry["excluded_pairs"])
            lines.append(f"| {entry['industry_id']} {entry['industry_name']} | {channels} |")

    if document["exclusions"]:
        lines += ["", "## Excluded pairs", "",
                  "Excluded, not treated as zero. A coefficient that cannot be signed or is "
                  "marked ineligible is preserved and left out of the score.", "",
                  "| industry | channel | reason |", "| --- | --- |  --- |"]
        for entry in document["exclusions"]:
            lines.append(
                f"| {entry['industry_id']} | `{entry['channel']}` | `{entry['reason']}` |"
            )

    lines += [""] + _artifact_block(document) + [""] + _limitations_block(document) + [""]
    return "\n".join(lines)


def render_industry_explanation_markdown(document: dict) -> str:
    industry = document["industry"]
    lines: list[str] = [
        f"# {industry['industry_id']} {industry['industry_name']} -- structural exposure",
        "",
        "**This is a conditional structural exposure calculation. It is not a probability, "
        "not a forecast, not a predicted percentage change in production, not a causal "
        "effect, not a risk band, and not an investment or production recommendation.**",
        "",
        "## Position",
        "",
        f"- **Scenario:** `{document['scenario']['scenario_id']}`",
    ]
    lines += _basis_block(document)
    lines += [
        f"- **Rank:** {industry['rank'] if industry['rank'] is not None else 'not ranked'}",
        f"- **Direction:** {industry['direction']}",
        f"- **Net exposure:** {industry['net_exposure']}",
        f"- **Relative index:** {industry['relative_exposure_index'] or '--'}",
        f"- **Direct component:** {industry['direct_component']}",
        f"- **Propagated component:** {industry['propagated_component'] or 'n/a on this basis'}",
        f"- **Gross absolute contribution:** {industry['gross_absolute_contribution']}",
        f"- **Cancellation:** {industry['cancellation']} "
        f"(ratio {industry['cancellation_ratio'] or '--'})",
        "",
        "## Channels",
        "",
    ]
    for channel in document["channels"]:
        lines += [
            f"### `{channel['channel']}` -- I/O sector {channel['io_sector_code']}",
            "",
            f"- Direction {channel['direction']}, sign {channel['sign']}, "
            f"magnitude fraction {channel['signed_magnitude_fraction']}",
            f"- Coefficient {channel['coefficient']} -> contribution "
            f"{channel['contribution']}",
            f"- Direct {channel['direct_component']}, propagated "
            f"{channel['propagated_component'] or 'n/a on this basis'}",
            f"- Proxy fitness `{channel['proxy_fit_status']}`, quality "
            f"`{channel['quality_flag']}`",
        ]
        if channel["price_stage"]:
            lines.append(
                f"- Price stage `{channel['price_stage']}`, alignment "
                f"`{channel['alignment_status']}`"
            )
        if channel["shared_source_sector_warning"]:
            lines.append(f"- {channel['shared_source_sector_warning']}")
        lines += [
            "",
            f"Showing {channel['mediators_shown']} of {channel['mediators_published']} "
            "published mediators, in the artifact's own rank order.",
            "",
            "| rank | intermediate sector | contribution | share of indirect | cumulative |",
            "| --- | --- | --- | --- | --- |",
        ]
        for mediator in channel["mediators"]:
            lines.append(
                f"| {mediator['rank']} | {mediator['intermediate_sector_code']} "
                f"{mediator['intermediate_sector_label']} | {mediator['contribution']} "
                f"| {mediator['share_of_indirect']} | {mediator['cumulative_share']} |"
            )
        lines.append("")
    lines += [document["mediator_interpretation"], ""]
    if document["exclusions"]:
        lines += ["## Excluded pairs", "", "| channel | reason |", "| --- | --- |"]
        for entry in document["exclusions"]:
            lines.append(f"| `{entry['channel']}` | `{entry['reason']}` |")
        lines.append("")
    lines += _artifact_block(document) + [""] + _limitations_block(document) + [""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schema agreement
# ---------------------------------------------------------------------------


def validate_result_document(document: dict, *, schema_path: Path | str | None = None) -> None:
    """Check a document against ``schemas/scenario_result.schema.yaml``.

    Field-set validation in the project's own style -- the schema files here are
    descriptive YAML rather than JSON Schema, and adding a validator dependency to check
    a document this module also writes would buy very little. What it does buy is that
    the schema cannot drift away from the code while both look correct.
    """
    path = Path(schema_path) if schema_path is not None else RESULT_SCHEMA_PATH
    if not path.is_file():
        raise ScenarioInternalError(f"result schema not found: {path}")
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = document.get("schema_version")
    documents = schema.get("documents", {})
    declared = next(
        (entry for entry in documents.values() if entry.get("schema_version") == version), None
    )
    if declared is None:
        raise ScenarioInternalError(
            f"schema_version {version!r} is not described in {path.name}"
        )
    missing = sorted(set(declared["required"]) - set(document))
    known = set(declared["required"]) | set(declared.get("optional", []))
    unexpected = sorted(set(document) - known)
    if missing or unexpected:
        raise ScenarioInternalError(
            f"{version}: document fields disagree with the schema; missing {missing}, "
            f"unexpected {unexpected}"
        )
    for name in declared.get("forbidden", ()):
        if _contains_key(document, name):
            raise ScenarioInternalError(
                f"{version}: forbidden field {name!r} appears in the document"
            )


def _contains_key(node, name: str) -> bool:
    if isinstance(node, dict):
        return name in node or any(_contains_key(v, name) for v in node.values())
    if isinstance(node, list):
        return any(_contains_key(item, name) for item in node)
    return False
