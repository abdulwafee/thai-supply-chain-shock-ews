"""Phase 3 tests: the two result documents.

The properties that matter here are not about arithmetic — Phase 2 owns that — but about
what survives the trip from a computed result to a file somebody will quote.

Determinism is checked by rendering twice and comparing bytes, and by rendering the same
scenario written with its shocks in a different order. Decimal fidelity is checked by
walking every value in the JSON and refusing anything that is not a string, and by
parsing the JSON back with ``parse_float`` set to a function that fails: if a float ever
appears, the test cannot silently accept it.
"""

from __future__ import annotations

import ast
import decimal
import itertools
import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.scenario import artifacts as art
from thai_supply_chain_ews.scenario import contract
from thai_supply_chain_ews.scenario import exposure as ex
from thai_supply_chain_ews.scenario import report as rp

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "structural_exposure_scenario.yaml"
SCHEMA_PATH = ROOT / "schemas" / "scenario_result.schema.yaml"
REPORT_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "report.py"
EXAMPLES = ROOT / "examples" / "scenarios"


@pytest.fixture(scope="module")
def policy():
    return contract.load_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def bundle(policy):
    return art.load_artifact_bundle(ROOT, policy=policy, policy_path=POLICY_PATH)


def scenario_from(tmp_path, shocks, policy, *, scenario_id="report-case", date="2026-09-04"):
    lines = [
        "schema_version: structural_exposure_scenario_v1",
        f"scenario_id: {scenario_id}",
        f"scenario_date: {date}",
        "shocks:",
    ]
    for channel, direction, magnitude in shocks:
        lines += [
            f"  - channel: {channel}",
            f"    direction: {direction}",
            f"    magnitude: {magnitude}",
            "    magnitude_unit: percent",
        ]
    path = tmp_path / f"{scenario_id}.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return contract.load_scenario_document(path, policy=policy)


def scored(scenario, policy, bundle, basis="total_requirement"):
    return ex.calculate_scenario_exposure(scenario, basis=basis, bundle=bundle, policy=policy)


def result_document(tmp_path, policy, bundle, shocks, basis="total_requirement", **kwargs):
    scenario = scenario_from(tmp_path, shocks, policy, **kwargs)
    result = scored(scenario, policy, bundle, basis)
    return rp.build_scenario_result_document(scenario, result, bundle)


def every_scalar(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from every_scalar(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from every_scalar(value, f"{path}[{index}]")
    else:
        yield path, node


# ---------------------------------------------------------------------------
# Schema agreement
# ---------------------------------------------------------------------------


def test_the_result_document_matches_the_schema_field_set(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)])
    rp.validate_result_document(document)
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    declared = schema["documents"]["scenario_result"]
    assert declared["schema_version"] == rp.RESULT_SCHEMA_VERSION
    assert set(document) == set(declared["required"])


def test_the_explanation_document_matches_the_schema_field_set(tmp_path, policy, bundle):
    scenario = scenario_from(tmp_path, [("brent_crude_usd_bbl", "increase", 30)], policy)
    result = scored(scenario, policy, bundle)
    document = rp.build_industry_explanation_document(
        scenario, result, bundle, industry_id="IND-04", mediator_limit=5
    )
    rp.validate_result_document(document)
    declared = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))["documents"][
        "industry_explanation"
    ]
    assert declared["schema_version"] == rp.EXPLANATION_SCHEMA_VERSION
    assert set(document) == set(declared["required"])


def test_a_document_missing_a_required_field_is_refused(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)])
    del document["limitations"]
    with pytest.raises(contract.ScenarioInternalError, match="disagree with the schema"):
        rp.validate_result_document(document)


def test_a_document_carrying_a_forbidden_field_is_refused(tmp_path, policy, bundle):
    """Recursive: a nondeterministic field cannot hide inside a nested object."""
    document = result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)])
    document["ranking"]["industries"][0]["generated_at"] = "2026-09-04T00:00:00Z"
    with pytest.raises(contract.ScenarioInternalError, match="forbidden field"):
        rp.validate_result_document(document)


def test_an_unknown_schema_version_is_refused(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)])
    document["schema_version"] = "structural_exposure_result_v99"
    with pytest.raises(contract.ScenarioInternalError, match="not described"):
        rp.validate_result_document(document)


# ---------------------------------------------------------------------------
# Decimal fidelity
# ---------------------------------------------------------------------------


def test_no_numeric_value_is_serialised_as_a_json_float(tmp_path, policy, bundle):
    document = result_document(
        tmp_path, policy, bundle,
        [("brent_crude_usd_bbl", "increase", 25), ("rubber_rss3_usd_kg", "decrease", 15)],
    )
    floats = [path for path, value in every_scalar(document) if isinstance(value, float)]
    assert floats == []
    decimals = [path for path, value in every_scalar(document) if isinstance(value, Decimal)]
    assert decimals == [], "a Decimal would not survive json.dumps"


def test_reparsing_the_json_finds_no_float_literal(tmp_path, policy, bundle):
    def refuse(literal):
        raise AssertionError(f"a float literal reached the JSON: {literal!r}")

    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    text = rp.render_scenario_result_json(document)
    reparsed = json.loads(text, parse_float=refuse, parse_constant=refuse)
    assert reparsed == document


@pytest.mark.parametrize(
    "field",
    ["net_exposure", "direct_component", "gross_absolute_contribution", "cancellation"],
)
def test_every_industry_decimal_is_a_canonical_string(tmp_path, policy, bundle, field):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    for entry in document["ranking"]["industries"]:
        value = entry[field]
        assert isinstance(value, str)
        assert value == contract.decimal_text(Decimal(value))


def test_the_canonical_strings_round_trip_to_the_computed_decimals(tmp_path, policy, bundle):
    scenario = scenario_from(tmp_path, [("brent_crude_usd_bbl", "increase", 30)], policy)
    result = scored(scenario, policy, bundle)
    document = rp.build_scenario_result_document(scenario, result, bundle)
    by_id = {e["industry_id"]: e for e in document["ranking"]["industries"]}
    for entry in result.ranking:
        assert Decimal(by_id[entry.industry_id]["net_exposure"]) == entry.net_exposure
        assert Decimal(by_id[entry.industry_id]["direct_component"]) == entry.direct_component


def test_serialising_a_float_is_an_internal_error():
    with pytest.raises(contract.ScenarioInternalError, match="binary float"):
        rp._text(0.1)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("basis", ["direct", "total_requirement"])
def test_rendering_twice_gives_byte_identical_output(tmp_path, policy, bundle, basis):
    shocks = [("brent_crude_usd_bbl", "increase", 25), ("aluminum_usd_mt", "increase", 10)]
    renders = set()
    for _ in range(3):
        document = result_document(tmp_path, policy, bundle, shocks, basis)
        renders.add(
            (
                rp.render_scenario_result_json(document).encode("utf-8"),
                rp.render_scenario_result_markdown(document).encode("utf-8"),
            )
        )
    assert len(renders) == 1


def test_the_order_the_author_lists_shocks_in_changes_no_byte(tmp_path, policy, bundle):
    shocks = [("brent_crude_usd_bbl", "increase", 25), ("aluminum_usd_mt", "increase", 10),
              ("rubber_rss3_usd_kg", "decrease", 15)]
    # One scenario id throughout: it is part of the canonical digest, so varying it would
    # make the documents differ for a reason that has nothing to do with shock order.
    renders = set()
    for order in itertools.permutations(shocks):
        document = result_document(tmp_path, policy, bundle, list(order),
                                   scenario_id="order-invariance")
        renders.add(
            (rp.render_scenario_result_json(document),
             rp.render_scenario_result_markdown(document))
        )
    assert len(renders) == 1


def test_no_document_field_is_machine_specific_or_time_dependent(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    text = rp.render_scenario_result_json(document)
    for token in ("generated_at", "timestamp", "run_id", "run_identity", "hostname",
                  "elapsed", "duration_seconds"):
        assert f'"{token}"' not in text
    for path, value in every_scalar(document):
        if isinstance(value, str):
            assert not value.startswith("/"), path
            assert ":\\" not in value, path
            assert str(ROOT) not in value, path
            assert str(tmp_path) not in value, path


def test_the_markdown_is_ascii_only(tmp_path, policy, bundle):
    """Bytes that depend on the console or filesystem encoding are not deterministic.

    The JSON is ASCII by ``ensure_ascii``; this holds the Markdown to the same standard,
    which also means writing it to a legacy Windows console cannot fail.
    """
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    markdown = rp.render_scenario_result_markdown(document)
    offending = sorted({ch for ch in markdown if ord(ch) > 127})
    assert offending == []
    markdown.encode("ascii")


def test_rendered_text_uses_lf_and_ends_with_a_newline(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    for text in (rp.render_scenario_result_json(document),
                 rp.render_scenario_result_markdown(document)):
        assert "\r" not in text
        assert text.endswith("\n")


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


def test_the_direct_basis_reports_no_propagated_component(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)], "direct")
    assert document["basis"]["selected"] == "direct"
    assert document["basis"]["role"] == "registered_primary"
    for entry in document["ranking"]["industries"]:
        assert entry["propagated_supported"] is False
        assert entry["propagated_component"] is None


def test_the_total_requirement_basis_carries_the_sensitivity_role_and_exact_identity(
    tmp_path, policy, bundle
):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    assert document["basis"]["role"] == "structural_sensitivity_only"
    assert document["basis"]["registered_primary"] == "direct"
    for entry in document["ranking"]["industries"]:
        direct = Decimal(entry["direct_component"])
        propagated = Decimal(entry["propagated_component"])
        assert direct + propagated == Decimal(entry["net_exposure"])


def test_cancellation_is_reported_beside_the_net(tmp_path, policy, bundle):
    document = result_document(
        tmp_path, policy, bundle,
        [("brent_crude_usd_bbl", "increase", 25), ("rubber_rss3_usd_kg", "decrease", 15)],
    )
    entry = next(e for e in document["ranking"]["industries"] if e["industry_id"] == "IND-04")
    gross = Decimal(entry["gross_absolute_contribution"])
    net = Decimal(entry["net_exposure"])
    assert Decimal(entry["cancellation"]) == gross - abs(net)
    assert Decimal(entry["cancellation_ratio"]) == (gross - abs(net)) / gross
    assert entry["direction"] in ("stress_pressure", "relief_pressure", "neutral")
    markdown = rp.render_scenario_result_markdown(document)
    assert "cancellation" in markdown


def test_exclusions_and_unscorable_industries_are_reported(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("aluminum_usd_mt", "increase", 20)])
    reasons = {e["reason"] for e in document["exclusions"]}
    assert reasons <= ex.EXCLUSION_REASONS
    assert {e["industry_id"] for e in document["exclusions"]} == {"IND-08", "IND-12"}
    assert [e["industry_id"] for e in document["unscorable_industries"]] == ["IND-08", "IND-12"]
    ranked = {e["industry_id"] for e in document["ranking"]["industries"]}
    assert ranked.isdisjoint({"IND-08", "IND-12"})
    markdown = rp.render_scenario_result_markdown(document)
    assert "not treated as zero" in markdown


@pytest.mark.parametrize(
    ("shocks", "reason"),
    [
        ([("brent_crude_usd_bbl", "increase", 0)], "all_magnitudes_zero"),
    ],
)
def test_a_zero_magnitude_scenario_reports_its_no_ranking_reason(
    tmp_path, policy, bundle, shocks, reason
):
    document = result_document(tmp_path, policy, bundle, shocks)
    assert document["ranking"]["status"] == "not_ranked"
    assert document["ranking"]["no_ranking_reason"] == reason
    assert document["ranking"]["relative_index_denominator"] is None
    assert document["ranking"]["industries"], "unranked industries are still reported"
    markdown = rp.render_scenario_result_markdown(document)
    assert "accepted outcome, not an error" in markdown


def test_the_no_ranking_reasons_are_the_declared_ones(tmp_path, policy, bundle):
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(schema["ranking_block"]["no_ranking_reasons"]) == set(ex.NO_RANKING_REASONS)


def test_artifact_provenance_is_complete_and_repository_relative(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    artifacts = document["artifacts"]
    assert len(artifacts) == 4
    assert [a["name"] for a in artifacts] == sorted(art.ARTIFACT_NAMES)
    for entry in artifacts:
        assert entry["digest_representation"] == "canonical_lf"
        assert len(entry["sha256"]) == 64
        assert not Path(entry["path"]).is_absolute()
        assert entry["sha256"] == bundle.digest_of(entry["name"])
    markdown = rp.render_scenario_result_markdown(document)
    for entry in artifacts:
        assert entry["sha256"] in markdown


def test_the_fixed_limitations_are_present_in_both_renderings(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    assert document["limitations"] == list(rp.LIMITATIONS)
    markdown = rp.render_scenario_result_markdown(document)
    for limitation in rp.LIMITATIONS:
        assert limitation in markdown


def test_the_markdown_states_what_the_result_is_not(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle,
                               [("brent_crude_usd_bbl", "increase", 30)])
    markdown = rp.render_scenario_result_markdown(document)
    for phrase in ("not a probability", "not a forecast",
                   "not a predicted percentage change in production", "not a causal effect",
                   "not a risk band", "not an investment or production recommendation"):
        assert phrase in markdown
    assert "conditional structural exposure" in markdown


def test_scenario_date_is_labelled_metadata_and_changes_no_vintage(tmp_path, policy, bundle):
    early = result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)],
                            scenario_id="early", date="2016-01-31")
    late = result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)],
                           scenario_id="late", date="2026-09-04")
    for document in (early, late):
        assert document["scenario"]["scenario_date_is_metadata_only"] is True
        assert document["scenario"]["coefficient_vintage_is_scenario_date"] is False
        assert document["basis"]["structural_reference_year"] == 2015
    assert "metadata only" in rp.render_scenario_result_markdown(early)


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------


def explanation(tmp_path, policy, bundle, *, industry_id="IND-09", limit=5,
                shocks=(("brent_crude_usd_bbl", "increase", 30),)):
    scenario = scenario_from(tmp_path, list(shocks), policy)
    result = scored(scenario, policy, bundle)
    return rp.build_industry_explanation_document(
        scenario, result, bundle, industry_id=industry_id, mediator_limit=limit
    )


def test_the_default_limit_shows_exactly_five_mediators(tmp_path, policy, bundle):
    document = explanation(tmp_path, policy, bundle, limit=5)
    for channel in document["channels"]:
        assert channel["mediators_shown"] == 5
        assert channel["mediators_published"] == 10
        assert len(channel["mediators"]) == 5


def test_the_all_limit_shows_exactly_ten_mediators(tmp_path, policy, bundle):
    document = explanation(tmp_path, policy, bundle, limit=10)
    for channel in document["channels"]:
        assert channel["mediators_shown"] == 10
        assert len(channel["mediators"]) == 10


def test_mediators_are_the_published_rows_in_published_order(tmp_path, policy, bundle):
    """Nothing is reordered, summarised or invented."""
    document = explanation(tmp_path, policy, bundle, limit=10)
    for channel in document["channels"]:
        published = bundle.mediators_for("IND-09", channel["channel"])
        expected = sorted(published, key=lambda m: m.rank)
        assert [m["rank"] for m in channel["mediators"]] == [m.rank for m in expected]
        for shown, source in zip(channel["mediators"], expected, strict=True):
            assert shown["intermediate_sector_code"] == source.intermediate_sector_code
            assert shown["intermediate_sector_label"] == source.intermediate_sector_label
            assert Decimal(shown["contribution"]) == source.contribution
            assert Decimal(shown["share_of_indirect"]) == source.share_of_indirect
            assert Decimal(shown["cumulative_share"]) == source.cumulative_share


def test_the_first_five_mediators_are_a_prefix_of_all_ten(tmp_path, policy, bundle):
    five = explanation(tmp_path, policy, bundle, limit=5)["channels"][0]["mediators"]
    ten = explanation(tmp_path, policy, bundle, limit=10)["channels"][0]["mediators"]
    assert five == ten[:5]


def test_an_unknown_industry_is_refused(tmp_path, policy, bundle):
    with pytest.raises(contract.ScenarioContractError) as caught:
        explanation(tmp_path, policy, bundle, industry_id="IND-99")
    assert caught.value.field == "industry"
    assert "IND-99" in str(caught.value)


def test_an_industry_with_no_scorable_pair_is_refused_from_explain(tmp_path, policy, bundle):
    """IND-12's only aluminium pair is excluded, so it has no figures to explain."""
    with pytest.raises(contract.ScenarioContractError):
        explanation(tmp_path, policy, bundle, industry_id="IND-99",
                    shocks=(("aluminum_usd_mt", "increase", 20),))


def test_the_explanation_calls_mediators_corroboration_not_proof(tmp_path, policy, bundle):
    document = explanation(tmp_path, policy, bundle)
    assert "corroboration" in document["mediator_interpretation"]
    assert "not evidence of a causal path" in document["mediator_interpretation"]
    markdown = rp.render_industry_explanation_markdown(document)
    assert "not evidence of a causal path" in markdown
    assert "not a probability" in markdown
    assert sorted({ch for ch in markdown if ord(ch) > 127}) == []


def test_the_explanation_is_deterministic(tmp_path, policy, bundle):
    renders = {
        (rp.render_industry_explanation_json(explanation(tmp_path, policy, bundle)),
         rp.render_industry_explanation_markdown(explanation(tmp_path, policy, bundle)))
        for _ in range(3)
    }
    assert len(renders) == 1


# ---------------------------------------------------------------------------
# Semantic boundary
# ---------------------------------------------------------------------------


def test_no_document_key_makes_a_predictive_or_causal_claim(tmp_path, policy, bundle):
    """Keys, walked structurally — not a text search that would trip on the disclaimer."""
    documents = [
        result_document(tmp_path, policy, bundle, [("brent_crude_usd_bbl", "increase", 30)]),
        explanation(tmp_path, policy, bundle),
    ]
    forbidden = {"probability", "likelihood", "prediction", "predicted", "forecast",
                 "expected_return", "expected_loss", "risk_score", "risk_band", "risk_level",
                 "confidence", "causal_effect", "elasticity", "pass_through",
                 "company_exposure", "recommendation"}

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    for document in documents:
        found = set(keys(document))
        assert found & forbidden == set()
        for key in found:
            for token in ("probabil", "forecast", "predict", "elastic", "causal",
                          "recommend", "confidence"):
                assert token not in key, key


def test_the_report_module_imports_nothing_beyond_the_scenario_package():
    tree = ast.parse(REPORT_SOURCE.read_text(encoding="utf-8"))
    project, other = set(), set()
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
        "thai_supply_chain_ews.scenario.exposure",
    }
    assert not {name.split(".")[0] for name in other} & {
        "socket", "urllib", "http", "requests", "pandas", "numpy", "sklearn", "datetime",
        "time", "random", "uuid", "os", "platform", "getpass"
    }


def test_the_report_module_writes_no_file():
    tree = ast.parse(REPORT_SOURCE.read_text(encoding="utf-8"))
    calls = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in ("write_text", "write_bytes", "mkdir", "unlink", "replace", "rename"):
        assert forbidden not in calls, forbidden


def test_the_public_report_api_is_the_reviewed_set():
    from thai_supply_chain_ews import scenario

    for name in ("build_scenario_result_document", "build_industry_explanation_document",
                 "render_scenario_result_json", "render_scenario_result_markdown",
                 "render_industry_explanation_json", "render_industry_explanation_markdown",
                 "validate_result_document", "report"):
        assert name in scenario.__all__
    for name in ("main", "cli", "run", "rank", "score", "predict", "forecast"):
        assert name not in scenario.__all__
    for name in ("_text", "_shock", "_contribution", "_industry", "_json",
                 "_limitations_block", "_artifact_block", "_contains_key"):
        assert name not in rp.__all__
        assert not hasattr(scenario, name)
        assert hasattr(rp, name)


# ---------------------------------------------------------------------------
# The shipped examples
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["crude_oil_price_increase.yaml", "rubber_price_decrease.yaml",
     "multi_commodity_shock.yaml"],
)
def test_each_example_validates_and_produces_both_documents(policy, bundle, name):
    scenario = contract.load_scenario_document(EXAMPLES / name, policy=policy)
    for basis in ("direct", "total_requirement"):
        result = scored(scenario, policy, bundle, basis)
        document = rp.build_scenario_result_document(scenario, result, bundle)
        rp.validate_result_document(document)
        assert rp.render_scenario_result_json(document)
        assert rp.render_scenario_result_markdown(document)


def test_the_examples_carry_no_basis_or_output_setting():
    for path in sorted(EXAMPLES.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert set(document) <= {"schema_version", "scenario_id", "scenario_name",
                                 "scenario_date", "note", "shocks"}
        for field in ("basis", "output", "format", "duration_months",
                      "affected_trading_partner", "company_id", "probability",
                      "recommendation"):
            assert field not in document


def test_the_multi_commodity_example_does_not_pair_aluminium_with_copper():
    document = yaml.safe_load(
        (EXAMPLES / "multi_commodity_shock.yaml").read_text(encoding="utf-8")
    )
    channels = {shock["channel"] for shock in document["shocks"]}
    assert "aluminum_usd_mt" in channels
    assert "copper_usd_mt" not in channels
    assert channels == {"brent_crude_usd_bbl", "aluminum_usd_mt", "rubber_rss3_usd_kg"}


def test_the_examples_state_the_magnitudes_the_specification_names():
    expected = {
        "crude_oil_price_increase.yaml": {("brent_crude_usd_bbl", "increase", 30)},
        "rubber_price_decrease.yaml": {("rubber_rss3_usd_kg", "decrease", 20)},
        "multi_commodity_shock.yaml": {
            ("brent_crude_usd_bbl", "increase", 25),
            ("aluminum_usd_mt", "increase", 10),
            ("rubber_rss3_usd_kg", "decrease", 15),
        },
    }
    for name, wanted in expected.items():
        document = yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))
        found = {
            (s["channel"], s["direction"], s["magnitude"]) for s in document["shocks"]
        }
        assert found == wanted, name
        assert all(s["magnitude_unit"] == "percent" for s in document["shocks"])


# ---------------------------------------------------------------------------
# The rendered documents do not depend on the caller's decimal context
#
# Everything a reader quotes is produced here, so this is where a context leak would
# actually reach them. Serialisation itself performs no arithmetic -- `_text` hands the
# value to `contract.decimal_text`, which reads the stored digits -- so what these
# guards check is that the whole path from a parsed document to rendered bytes is
# context-free, not merely that this module avoids one operation.
# ---------------------------------------------------------------------------


AMBIENT_CONTEXTS = [
    (6, decimal.ROUND_DOWN),
    (9, decimal.ROUND_UP),
    (28, decimal.ROUND_HALF_EVEN),
    (50, decimal.ROUND_FLOOR),
    (80, decimal.ROUND_CEILING),
]

CONTEXT_SHOCKS = [
    ("brent_crude_usd_bbl", "increase", 25),
    ("rubber_rss3_usd_kg", "decrease", 15),
]


def under(prec, rounding, work):
    """Run ``work`` under an ambient context, restoring the caller's afterwards."""
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = prec, rounding
        return work()


def test_the_result_document_is_byte_identical_under_every_ambient_context(
    tmp_path, policy, bundle
):
    rendered = set()
    for prec, rounding in AMBIENT_CONTEXTS:
        document = under(
            prec,
            rounding,
            lambda: result_document(tmp_path, policy, bundle, CONTEXT_SHOCKS),
        )
        rendered.add(
            under(
                prec,
                rounding,
                lambda document=document: (
                    rp.render_scenario_result_json(document),
                    rp.render_scenario_result_markdown(document),
                ),
            )
        )
    assert len(rendered) == 1


def test_the_explanation_document_is_byte_identical_under_every_ambient_context(
    tmp_path, policy, bundle
):
    rendered = set()
    for prec, rounding in AMBIENT_CONTEXTS:
        def build():
            scenario = scenario_from(
                tmp_path, CONTEXT_SHOCKS, policy, scenario_id="explanation-context"
            )
            result = scored(scenario, policy, bundle)
            document = rp.build_industry_explanation_document(
                scenario, result, bundle, industry_id="IND-04", mediator_limit=5
            )
            return (
                rp.render_industry_explanation_json(document),
                rp.render_industry_explanation_markdown(document),
            )

        rendered.add(under(prec, rounding, build))
    assert len(rendered) == 1


def test_rendering_a_document_leaves_the_callers_context_untouched(tmp_path, policy, bundle):
    document = result_document(tmp_path, policy, bundle, CONTEXT_SHOCKS)
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = 11, decimal.ROUND_05UP
        rp.render_scenario_result_json(document)
        rp.render_scenario_result_markdown(document)
        assert decimal.getcontext().prec == 11
        assert decimal.getcontext().rounding == decimal.ROUND_05UP


def test_serialisation_declares_itself_context_free_and_holds_no_context_of_its_own():
    """The module states the property; this checks the statement is still earned.

    ``report`` once carried its own fixed context purely to stop ``decimal_text`` from
    rounding. With that fixed at the source the context here was redundant, and a
    redundant one is worse than none: it would look like the thing keeping the output
    stable while the real guarantee lived elsewhere.
    """
    assert rp._SERIALISATION_IS_CONTEXT_FREE is True
    source = REPORT_SOURCE.read_text(encoding="utf-8")
    assert "localcontext" not in source
    assert "_TEXT_CONTEXT" not in source


def test_a_long_magnitude_is_rendered_with_every_digit(tmp_path, policy, bundle):
    """A long input is contract-valid, so the report has to print it exactly.

    The JSON carries canonical strings, so a shortened number would not be flagged
    anywhere -- it would simply be a different figure presented as the answer.
    """
    long_magnitude = "0." + "1234567891" * 8
    document = result_document(
        tmp_path,
        policy,
        bundle,
        [("brent_crude_usd_bbl", "increase", long_magnitude)],
        scenario_id="long-render",
    )
    payload = json.loads(rp.render_scenario_result_json(document))
    top = payload["ranking"]["industries"][0]
    assert len(top["net_exposure"].split(".")[1]) > 60
    # Wide enough that the check itself cannot be what rounds: adding two seventy-digit
    # decimals at the default precision would fail here for the test's reasons, not the
    # module's.
    with decimal.localcontext() as ctx:
        ctx.prec = 5000
        assert Decimal(top["net_exposure"]) == Decimal(top["direct_component"]) + Decimal(
            top["propagated_component"]
        )
