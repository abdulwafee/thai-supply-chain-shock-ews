"""Phase 1 tests: the scenario input contract, and only that.

Hermetic. Every scenario document is written into ``tmp_path``; nothing here reads
an exposure artifact, opens a locked outcome, touches the vault or needs a network.

Two habits worth naming, because both are easy to get wrong in a test suite whose
whole subject is claim discipline.

**Structure, not prose.** The guards below read the module's abstract syntax tree —
its imports, its path-shaped string constants — rather than grepping the file for
forbidden words. A text ban would fail on this very docstring, and worse, it would
fail on a legitimate disclaimer that has to contain the words "not a probability"
in order to say anything at all.

**The schema and the validator are compared to each other.** Two files describing
one contract drift apart quietly, each looking correct on its own, so
:func:`test_schema_and_runtime_field_sets_agree` requires them to state the same
field sets and the same required sets.
"""

from __future__ import annotations

import ast
import decimal
import json
import os
import re
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from thai_supply_chain_ews.scenario import contract

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "structural_exposure_scenario.yaml"
SCHEMA_PATH = ROOT / "schemas" / "scenario_input.schema.yaml"
CONTRACT_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "contract.py"
PACKAGE_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "__init__.py"


@pytest.fixture
def policy() -> contract.ScenarioPolicy:
    return contract.load_policy(POLICY_PATH)


def document(**overrides) -> dict:
    """A minimal valid document, before overrides."""
    base = {
        "schema_version": contract.INPUT_SCHEMA_VERSION,
        "scenario_id": "crude-oil-plus-30",
        "shocks": [
            {
                "channel": "brent_crude_usd_bbl",
                "direction": "increase",
                "magnitude": 30,
                "magnitude_unit": "percent",
            }
        ],
    }
    base.update(overrides)
    return base


def write(tmp_path: Path, payload, *, name: str = "scenario.yaml") -> Path:
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8", newline="\n")
    elif path.suffix == ".json":
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    else:
        path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8", newline="\n")
    return path


def refuse(payload, policy_obj) -> contract.ScenarioContractError:
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.validate_scenario_document(payload, policy=policy_obj)
    return caught.value


def tree_snapshot(root: Path) -> dict:
    """Every path under ``root``, with its exact content, size, mtime and kind.

    The content is kept as raw bytes and compared directly. It is deliberately **not**
    hashed: ``tests/test_pin_generation_guard.py`` requires every file-byte hashing
    site to be declared in ``configs/line_ending_provenance.yaml``, and it is right
    to — an undeclared one is the next checksum that will disagree with itself. A
    comparison needs no digest, so this site simply does not create one.

    All four facts are recorded because each catches something the others miss.
    Content catches a same-length edit that a size check would wave through.
    ``st_mtime_ns`` catches a rewrite that reproduces identical bytes, which content
    alone cannot see. Size is a cheap independent cross-check on truncation, and the
    kind marker separates a file from a directory of the same name. Missing and added
    paths show up as key differences.
    """
    out = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            out[relative] = ("dir", None, None, None)
            continue
        stat = path.stat()
        out[relative] = ("file", path.read_bytes(), stat.st_size, stat.st_mtime_ns)
    return out


# ---------------------------------------------------------------------------
# 1-5  Valid documents, equivalence and canonical ordering
# ---------------------------------------------------------------------------


def test_a_valid_yaml_document_is_accepted(tmp_path, policy):
    path = write(tmp_path, document(scenario_name="Brent +30%", note="one channel"))
    result = contract.load_scenario_document(path, policy=policy)
    assert result.scenario_id == "crude-oil-plus-30"
    assert result.channels == ("brent_crude_usd_bbl",)
    assert result.shocks[0].magnitude == Decimal(30)
    assert result.shocks[0].magnitude_unit == "percent"
    assert result.shocks[0].magnitude_fraction == Decimal("0.3")
    assert result.shocks[0].signed_magnitude_fraction == Decimal("0.3")
    assert isinstance(result.shocks[0].magnitude_fraction, Decimal)
    assert result.shocks[0].canonical_signed_fraction == "0.3"
    assert result.shocks[0].io_sector_code == "031"
    assert result.warnings == ()


def test_a_valid_json_document_is_accepted(tmp_path, policy):
    path = write(tmp_path, document(), name="scenario.json")
    result = contract.load_scenario_document(path, policy=policy)
    assert result.channels == ("brent_crude_usd_bbl",)


def test_yaml_and_json_with_the_same_meaning_hash_identically(tmp_path, policy):
    payload = document(scenario_name="Brent +30%", scenario_date="2026-09-04")
    as_yaml = contract.load_scenario_document(write(tmp_path, payload), policy=policy)
    as_json = contract.load_scenario_document(
        write(tmp_path, payload, name="scenario.json"), policy=policy
    )
    assert contract.canonical_input_sha256(as_yaml) == contract.canonical_input_sha256(as_json)


def scenario_text(magnitude: str, unit: str = "percent", *, fmt: str = "yaml") -> str:
    """A scenario document with the magnitude written exactly as given.

    Built as text rather than dumped from a dict, because the thing under test is how
    a *spelling* is read. ``yaml.safe_dump`` would normalise the number first and the
    test would prove nothing.
    """
    if fmt == "json":
        return (
            '{"schema_version": "structural_exposure_scenario_v1",'
            ' "scenario_id": "numeric-spelling",'
            ' "shocks": [{"channel": "brent_crude_usd_bbl", "direction": "increase",'
            f' "magnitude": {magnitude}, "magnitude_unit": "{unit}"}}]}}'
        )
    return (
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: numeric-spelling\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        "    direction: increase\n"
        f"    magnitude: {magnitude}\n"
        f"    magnitude_unit: {unit}\n"
    )


def digest_of(tmp_path, magnitude, unit="percent", *, fmt="yaml", policy=None, tag="a"):
    name = f"{tag}.json" if fmt == "json" else f"{tag}.yaml"
    path = write(tmp_path, scenario_text(magnitude, unit, fmt=fmt), name=name)
    return contract.canonical_input_sha256(contract.load_scenario_document(path, policy=policy))


@pytest.mark.parametrize(
    ("percent", "fraction", "expected"),
    [
        ("30", "0.30", "0.3"),
        ("33", "0.33", "0.33"),
        ("12.5", "0.125", "0.125"),
        ("0.1", "0.001", "0.001"),
        ("1000", "10", "10"),
    ],
)
def test_percent_and_fraction_of_equal_meaning_hash_identically(
    tmp_path, policy, percent, fraction, expected
):
    """The identity is exact decimal arithmetic, not IEEE rounding that happens to agree.

    ``0.1`` percent is the case that matters most: neither ``0.1`` nor ``0.001`` is
    representable in binary, so under floats this equality would hold by luck rather
    than by construction.
    """
    as_percent = contract.load_scenario_document(
        write(tmp_path, scenario_text(percent, "percent"), name="pct.yaml"), policy=policy
    )
    as_fraction = contract.load_scenario_document(
        write(tmp_path, scenario_text(fraction, "fraction"), name="frac.yaml"), policy=policy
    )
    assert as_percent.shocks[0].magnitude_unit == "percent"
    assert as_fraction.shocks[0].magnitude_unit == "fraction"
    assert as_percent.shocks[0].magnitude_fraction == as_fraction.shocks[0].magnitude_fraction
    assert as_percent.shocks[0].canonical_signed_fraction == expected
    assert contract.canonical_input_sha256(as_percent) == contract.canonical_input_sha256(
        as_fraction
    )


@pytest.mark.parametrize(
    "spellings",
    [
        ["0.3", "0.30", "0.300", "3.0e-1", "3E-1", "0.3000000", "30e-2"],
        ["10", "10.0", "10.00", "1E+1", "1e1", "1.0e1", "0.1e2"],
        ["0", "0.0", "0.00", "-0", "-0.0", "0e0", "-0.0e5"],
        ["2.5", "2.50", "2.500", "2.5e0", "0.25e1", "25e-1"],
        ["1", "1.0", "1.00", "1e0", "0.1e1"],
    ],
)
def test_every_yaml_spelling_of_one_value_produces_one_digest(tmp_path, policy, spellings):
    """Integer, decimal, exponent, trailing-zero and signed-zero spellings all agree.

    The exponent forms are included because the loader adds a strict grammar for
    them; PyYAML's own YAML 1.1 resolver would leave most of these as plain strings.
    """
    digests = {
        digest_of(tmp_path, spelling, "fraction", policy=policy, tag=f"s{index}")
        for index, spelling in enumerate(spellings)
    }
    assert len(digests) == 1


@pytest.mark.parametrize(
    "spellings",
    [
        ["0.3", "0.30", "3.0e-1", "3E-1", "0.3000000"],
        ["10", "10.0", "1.0e1", "1E+1", "1e1"],
        ["0", "0.0", "-0", "-0.0", "0e0"],
        ["2.5", "2.50", "2.5e0", "0.25e1"],
    ],
)
def test_every_json_spelling_of_one_value_produces_one_digest(tmp_path, policy, spellings):
    """JSON's grammar admits the unsigned and point-free exponent forms YAML does not."""
    digests = {
        digest_of(tmp_path, spelling, "fraction", fmt="json", policy=policy, tag=f"j{index}")
        for index, spelling in enumerate(spellings)
    }
    assert len(digests) == 1


@pytest.mark.parametrize("spelling", ["1E+1", "1e1", "1.0e1", "2.5e0", "0e0", "3E-1", "2.5e-1"])
def test_plain_yaml_scientific_notation_and_json_agree_exactly(tmp_path, policy, spelling):
    """The same exponent form means the same thing in both formats.

    PyYAML's YAML 1.1 resolver would leave most of these as plain strings. The loader
    adds a strict grammar for ordinary decimal scientific notation so the input
    contract does not expose that quirk as a user-facing difference between YAML and
    JSON.
    """
    from_yaml = contract.load_scenario_document(
        write(tmp_path, scenario_text(spelling, "fraction"), name="y.yaml"), policy=policy
    )
    from_json = contract.load_scenario_document(
        write(tmp_path, scenario_text(spelling, "fraction", fmt="json"), name="j.json"),
        policy=policy,
    )
    assert from_yaml.shocks[0].magnitude_fraction == from_json.shocks[0].magnitude_fraction
    assert (
        from_yaml.shocks[0].canonical_signed_fraction
        == from_json.shocks[0].canonical_signed_fraction
    )
    assert contract.canonical_input_sha256(from_yaml) == contract.canonical_input_sha256(from_json)


@pytest.mark.parametrize(
    ("spelling", "expected"),
    [("1E+1", "10"), ("1e1", "10"), ("1.0e1", "10"), ("2.5e0", "2.5"), ("0e0", "0"),
     ("3E-1", "0.3"), ("25e-1", "2.5"), ("0.5e0", "0.5"), ("1.05", "1.05"),
     ("0.001", "0.001"), ("-0", "0"), ("-0.0", "0")],
)
def test_exponent_forms_reach_the_expected_exact_decimal(tmp_path, policy, spelling, expected):
    loaded = contract.load_scenario_document(
        write(tmp_path, scenario_text(spelling, "fraction")), policy=policy
    )
    assert loaded.shocks[0].canonical_signed_fraction == expected
    assert isinstance(loaded.shocks[0].magnitude_fraction, Decimal)


def test_an_exponent_percent_equals_its_fraction_equivalent(tmp_path, policy):
    """3E+1 percent and 3E-1 fraction are the same shock written two ways."""
    as_percent = contract.load_scenario_document(
        write(tmp_path, scenario_text("3E+1", "percent"), name="p.yaml"), policy=policy
    )
    as_fraction = contract.load_scenario_document(
        write(tmp_path, scenario_text("3E-1", "fraction"), name="f.yaml"), policy=policy
    )
    assert as_percent.shocks[0].canonical_signed_fraction == "0.3"
    assert contract.canonical_input_sha256(as_percent) == contract.canonical_input_sha256(
        as_fraction
    )


@pytest.mark.parametrize("quoting", ['"{}"', "'{}'"])
def test_a_quoted_yaml_number_stays_a_string_and_is_refused(tmp_path, policy, quoting):
    """The resolver is implicit, so it never touches a scalar the author quoted.

    Quoting is how a YAML author says "this is text". Reading it as a number anyway
    would mean the document said one thing to PyYAML and another to this module.
    """
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(quoting.format("1E+1"), "fraction")), policy=policy
        )
    assert caught.value.code == "magnitude_not_a_number"


@pytest.mark.parametrize(
    "spelling",
    ["1e", "1e+", "1e-", "e1", ".e1", "1..0e1", "1e1.5", "--1e1", "1E+1x", "1_e1",
     "1e1_", "_1e1", "1.0e", "+-1e1", "1e1e1", "1.2.3e1"],
)
def test_a_malformed_exponent_form_is_refused_not_guessed(tmp_path, policy, spelling):
    """The grammar is strict. A partial or malformed form is a string, not a number."""
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(spelling, "fraction")), policy=policy
        )
    assert caught.value.code == "magnitude_not_a_number"


@pytest.mark.parametrize(
    ("spelling", "why"),
    [
        ("0x1e1", "hexadecimal: YAML 1.1 reads it as 481, JSON rejects it outright"),
        ("017", "YAML 1.1 leading-zero octal: 15 here, invalid JSON"),
        ("0b101", "binary: 5 in YAML 1.1, invalid JSON"),
        ("0o17", "YAML 1.2 octal spelling, which YAML 1.1 leaves as a string"),
        ("1_000", "digit separators are a YAML extension with no JSON equivalent"),
        ("1_0.5", "digit separators inside a fraction"),
        (".5", "leading-dot decimal: invalid JSON"),
        ("1.", "trailing-dot decimal: invalid JSON"),
        ("190:20:30.15", "YAML 1.1 sexagesimal"),
        ("+10", "leading plus: invalid JSON, and direction already carries the sign"),
        ("+1.5", "leading plus on a fraction"),
    ],
)
def test_a_yaml_only_numeric_spelling_is_refused_rather_than_reinterpreted(
    tmp_path, policy, spelling, why
):
    """Every one of these means something in YAML 1.1 and nothing in JSON.

    Accepting them because PyYAML happens to convert them would make the same
    document mean two different things depending on the format it was written in,
    which is precisely what a contract is supposed to prevent. The refusal names the
    field and says which notations are supported.
    """
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(spelling, "percent")), policy=policy
        )
    assert caught.value.code == "magnitude_not_a_number", why
    assert caught.value.field == "shocks[0].magnitude"
    assert "base-10" in str(caught.value)


@pytest.mark.parametrize("quoting", ['"{}"', "'{}'"])
@pytest.mark.parametrize("spelling", ["10", "1E+1", "0.5"])
def test_a_quoted_numeric_string_is_not_a_number(tmp_path, policy, quoting, spelling):
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(quoting.format(spelling), "percent")), policy=policy
        )
    assert caught.value.code == "magnitude_not_a_number"


@pytest.mark.parametrize("spelling", ["-1", "-0.5", "-1e1"])
def test_an_actually_negative_magnitude_is_still_refused(tmp_path, policy, spelling):
    """The grammar admits a leading minus; the contract still refuses a negative value.

    Parsing and validation are different jobs. ``-0`` gets through because it is zero.
    """
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(spelling, "percent")), policy=policy
        )
    assert caught.value.code == "magnitude_negative"


@pytest.mark.parametrize("spelling", ["-0", "-0.0", "-0.000", "-0e5"])
def test_negative_zero_is_accepted_and_canonicalizes_to_zero(tmp_path, policy, spelling):
    loaded = contract.load_scenario_document(
        write(tmp_path, scenario_text(spelling, "percent")), policy=policy
    )
    assert loaded.shocks[0].canonical_signed_fraction == "0"
    assert loaded.shocks[0].is_zero is True


# ---------------------------------------------------------------------------
# scenario_date: quoted or not, it is the same three-part date
# ---------------------------------------------------------------------------


def dated_scenario_text(date_literal: str) -> str:
    return (
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: dated-scenario\n"
        f"scenario_date: {date_literal}\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        "    direction: increase\n"
        "    magnitude: 30\n"
        "    magnitude_unit: percent\n"
    )


@pytest.mark.parametrize("literal", ["2026-09-04", '"2026-09-04"', "'2026-09-04'"])
def test_an_iso_scenario_date_is_accepted_however_it_is_quoted(tmp_path, policy, literal):
    loaded = contract.load_scenario_document(
        write(tmp_path, dated_scenario_text(literal)), policy=policy
    )
    assert loaded.scenario_date == "2026-09-04"
    assert isinstance(loaded.scenario_date, str)


def test_the_three_date_spellings_share_one_payload_and_one_digest(tmp_path, policy):
    """PyYAML would turn the unquoted form into a ``datetime.date`` before validation.

    The loader preserves the lexeme instead, so all three spellings are the same nine
    characters by the time the field's ISO rule runs.
    """
    results = [
        contract.load_scenario_document(
            write(tmp_path, dated_scenario_text(literal), name=f"d{index}.yaml"), policy=policy
        )
        for index, literal in enumerate(["2026-09-04", '"2026-09-04"', "'2026-09-04'"])
    ]
    payloads = {json.dumps(contract.canonical_scenario_payload(r), sort_keys=True)
                for r in results}
    digests = {contract.canonical_input_sha256(r) for r in results}
    assert len(payloads) == 1
    assert len(digests) == 1
    assert {r.scenario_date for r in results} == {"2026-09-04"}


@pytest.mark.parametrize(
    "literal", ["2026-02-30", "2025-02-29", "2026-13-01", "2026-00-10", "2026-09-31"]
)
def test_an_unquoted_invalid_calendar_date_is_refused_by_the_field_rule(
    tmp_path, policy, literal
):
    """Unquoted, PyYAML would raise a parse error here. The field reports it instead."""
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, dated_scenario_text(literal)),
                                        policy=policy)
    assert caught.value.code == "bad_scenario_date"
    assert caught.value.field == "scenario_date"


@pytest.mark.parametrize(
    "literal",
    ["2026-09-04T12:30:00", "2026-09-04 12:30:00", "2026-09-04T12:30:00Z", "2026-09-04t12:30:00"],
)
def test_a_timestamp_is_refused_because_the_field_accepts_a_date(tmp_path, policy, literal):
    """A time is not a near-miss on the length limit; it is the wrong kind of value."""
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, dated_scenario_text(literal)),
                                        policy=policy)
    assert caught.value.code == "bad_scenario_date"
    assert caught.value.field == "scenario_date"


def test_an_unquoted_date_still_changes_nothing_about_the_coefficient_vintage(tmp_path, policy):
    loaded = contract.load_scenario_document(
        write(tmp_path, dated_scenario_text("2026-09-04")), policy=policy
    )
    assert loaded.structural_reference_year == contract.STRUCTURAL_REFERENCE_YEAR == 2015
    assert loaded.scenario_date_is_metadata_only is True
    assert loaded.coefficient_vintage_is_scenario_date is False


# ---------------------------------------------------------------------------
# Two loaders, two jobs
# ---------------------------------------------------------------------------


def test_the_scenario_and_policy_loaders_are_distinct_private_classes():
    scenario_loader = contract._ScenarioInputLoader
    policy_loader = contract._PolicyLoader
    assert scenario_loader is not policy_loader
    assert not issubclass(scenario_loader, policy_loader)
    assert not issubclass(policy_loader, scenario_loader)
    assert issubclass(scenario_loader, yaml.SafeLoader)
    assert issubclass(policy_loader, yaml.SafeLoader)

    float_tag, int_tag, stamp_tag = (
        "tag:yaml.org,2002:float", "tag:yaml.org,2002:int", "tag:yaml.org,2002:timestamp",
    )
    # The scenario loader constrains numbers and preserves dates; the policy loader
    # does neither, because a repository-owned file is not untrusted input.
    assert (
        scenario_loader.yaml_constructors[float_tag]
        is not policy_loader.yaml_constructors[float_tag]
    )
    assert scenario_loader.yaml_constructors[int_tag] is not yaml.SafeLoader.yaml_constructors[
        int_tag
    ]
    assert policy_loader.yaml_constructors[int_tag] is yaml.SafeLoader.yaml_constructors[int_tag]
    assert scenario_loader.yaml_constructors[stamp_tag] is not (
        yaml.SafeLoader.yaml_constructors[stamp_tag]
    )
    assert policy_loader.yaml_constructors[stamp_tag] is (
        yaml.SafeLoader.yaml_constructors[stamp_tag]
    )


def test_neither_loader_is_exported():
    from thai_supply_chain_ews import scenario

    for name in ("_ScenarioInputLoader", "_PolicyLoader", "_NoDuplicateKeyLoader"):
        assert name not in contract.__all__
        assert name not in scenario.__all__
        assert not hasattr(scenario, name)
    assert hasattr(contract, "_ScenarioInputLoader")
    assert hasattr(contract, "_PolicyLoader")


def test_both_loaders_refuse_duplicate_keys(tmp_path, policy):
    text = (
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: duplicated-key\n"
        "scenario_id: duplicated-again\n"
        "shocks:\n  - channel: brent_crude_usd_bbl\n    direction: increase\n"
        "    magnitude: 30\n    magnitude_unit: percent\n"
    )
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text), policy=policy)
    assert caught.value.code == "duplicate_mapping_key"

    duplicated_policy = tmp_path / "policy.yaml"
    duplicated_policy.write_text(
        POLICY_PATH.read_text(encoding="utf-8") + "\nmax_input_bytes: 999\n",
        encoding="utf-8", newline="\n",
    )
    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(duplicated_policy)


def test_the_scenario_loader_constructs_no_arbitrary_object(tmp_path, policy):
    """SafeLoader refuses a python object tag; the scenario loader inherits that."""
    text = (
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: tagged-object\n"
        "shocks: !!python/object/apply:os.system ['echo unsafe']\n"
    )
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text), policy=policy)
    assert caught.value.code == "malformed_document"


def test_the_shipped_policy_still_loads_with_identical_semantics(policy):
    reloaded = contract.load_policy(POLICY_PATH)
    assert reloaded == policy
    assert reloaded.channel_names == tuple(sorted(contract.REGISTERED_CHANNELS))
    assert reloaded.magnitude.increase_warn_above_fraction == Decimal("1.0")
    assert reloaded.magnitude.increase_refuse_above_fraction == Decimal("10.0")
    assert reloaded.magnitude.decrease_refuse_above_fraction == Decimal("1.0")
    assert reloaded.magnitude.percent_to_fraction_divisor == Decimal(100)
    assert reloaded.structural_reference_year == 2015
    assert reloaded.max_input_bytes == 262144
    assert reloaded.min_shocks == 1 and reloaded.max_shocks == 8


# ---------------------------------------------------------------------------
# The strict grammar is load-bearing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spelling", "relaxed_value"),
    [("0x1e1", 481), ("017", 15), ("0b101", 5), ("1_000", 1000)],
)
def test_relaxing_the_numeric_grammar_would_change_what_a_document_means(spelling, relaxed_value):
    """Proof that the strictness matters rather than merely existing.

    PyYAML's own SafeLoader — the relaxed behaviour this contract declines — reads
    each of these as a number, and a different number from the one JSON would refuse
    to read at all. The scenario loader hands back the text instead, which is what
    makes the refusal possible.
    """
    assert yaml.safe_load(f"a: {spelling}\n")["a"] == relaxed_value
    strict = contract._parse_document_text(f"a: {spelling}\n", suffix=".yaml")["a"]
    assert isinstance(strict, str)
    assert strict == spelling


def test_the_schemas_declared_numeric_examples_match_the_implementation(tmp_path, policy):
    """The schema names accepted and rejected spellings; both lists are executed.

    A schema that lists examples nobody runs is documentation that drifts. Each entry
    below is loaded through the real path, so the file cannot claim a behaviour the
    validator does not have.
    """
    canon = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))["canonicalization"]
    assert canon["numeric_grammar_name"] == "json_number_base_10"
    assert canon["quoted_numbers_are_not_numbers"] is True

    for index, value in enumerate(canon["accepted_examples"]):
        loaded = contract.load_scenario_document(
            write(tmp_path, scenario_text(value, "percent"), name=f"ok{index}.yaml"),
            policy=policy,
        )
        assert isinstance(loaded.shocks[0].magnitude_fraction, Decimal)

    for index, entry in enumerate(canon["rejected_examples"]):
        with pytest.raises(contract.ScenarioContractError) as caught:
            contract.load_scenario_document(
                write(tmp_path, scenario_text(entry["value"], "percent"), name=f"no{index}.yaml"),
                policy=policy,
            )
        assert caught.value.code == "magnitude_not_a_number", entry["reason"]


def test_the_schema_declares_the_date_and_loader_semantics_that_were_implemented():
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    field = {entry["name"]: entry for entry in schema["top_level"]["fields"]}["scenario_date"]
    assert field["date_only"] is True
    assert field["timestamp_accepted"] is False
    assert field["quoting_is_semantically_irrelevant"] is True
    assert "loaders" in schema["canonicalization"]
    assert set(schema["canonicalization"]["unsupported_yaml_numeric_dialects"]) == {
        "hexadecimal", "octal", "binary", "digit_separators", "sexagesimal",
        "leading_plus", "leading_dot", "trailing_dot",
    }


def test_relaxing_the_date_handling_would_change_what_a_document_means():
    """PyYAML resolves an unquoted ISO date to a date object before validation runs."""
    import datetime

    assert yaml.safe_load("a: 2026-09-04\n")["a"] == datetime.date(2026, 9, 4)
    strict = contract._parse_document_text("a: 2026-09-04\n", suffix=".yaml")["a"]
    assert isinstance(strict, str)
    assert strict == "2026-09-04"


def test_no_binary_float_appears_anywhere_in_the_validated_path(tmp_path, policy):
    """Every numeric value on a validated scenario is a Decimal, never a float."""
    loaded = contract.load_scenario_document(
        write(
            tmp_path,
            "schema_version: structural_exposure_scenario_v1\n"
            "scenario_id: no-floats-anywhere\n"
            "shocks:\n"
            "  - channel: brent_crude_usd_bbl\n    direction: increase\n"
            "    magnitude: 1.0e1\n    magnitude_unit: percent\n"
            "  - channel: rubber_rss3_usd_kg\n    direction: decrease\n"
            "    magnitude: 0.1\n    magnitude_unit: percent\n",
        ),
        policy=policy,
    )
    for entry in loaded.shocks:
        for value in (entry.magnitude, entry.magnitude_fraction, entry.signed_magnitude_fraction):
            assert isinstance(value, Decimal)
            assert not isinstance(value, float)
    for value in (
        policy.magnitude.percent_to_fraction_divisor,
        policy.magnitude.increase_warn_above_fraction,
        policy.magnitude.increase_refuse_above_fraction,
        policy.magnitude.decrease_refuse_above_fraction,
    ):
        assert isinstance(value, Decimal)
    payload = contract.canonical_scenario_payload(loaded)
    assert all(
        isinstance(entry["signed_magnitude_fraction"], str) for entry in payload["shocks"]
    )


def test_negative_zero_canonicalizes_to_plain_zero(tmp_path, policy):
    for spelling in ["-0", "-0.0", "-0.00", "0", "0.0"]:
        loaded = contract.load_scenario_document(
            write(tmp_path, scenario_text(spelling, "fraction"), name="z.yaml"), policy=policy
        )
        assert loaded.shocks[0].canonical_signed_fraction == "0"
        payload = contract.canonical_scenario_payload(loaded)
        assert payload["shocks"][0]["signed_magnitude_fraction"] == "0"


def test_a_zero_increase_and_a_zero_decrease_still_differ_by_direction(tmp_path, policy):
    """Both serialize the magnitude as "0"; the author said two different things."""
    up = contract.load_scenario_document(
        write(tmp_path, scenario_text("0", "fraction"), name="u.yaml"), policy=policy
    )
    down_text = scenario_text("0", "fraction").replace("increase", "decrease")
    down = contract.load_scenario_document(
        write(tmp_path, down_text, name="d.yaml"), policy=policy
    )
    assert up.shocks[0].canonical_signed_fraction == "0"
    assert down.shocks[0].canonical_signed_fraction == "0"
    assert contract.canonical_input_sha256(up) != contract.canonical_input_sha256(down)


@pytest.mark.parametrize(
    ("yaml_spelling", "json_spelling"),
    [("0.30", "0.30"), ("0.3", "0.300"), ("3.0e-1", "0.3"), ("10", "10.0"), ("0", "-0.0")],
)
def test_yaml_and_json_numeric_spellings_hash_identically(
    tmp_path, policy, yaml_spelling, json_spelling
):
    from_yaml = digest_of(tmp_path, yaml_spelling, "fraction", fmt="yaml", policy=policy, tag="y")
    from_json = digest_of(tmp_path, json_spelling, "fraction", fmt="json", policy=policy, tag="j")
    assert from_yaml == from_json


@pytest.mark.parametrize(
    ("first", "second"),
    [("0.3", "0.31"), ("0.001", "0.0011"), ("1", "1.0000001"), ("0.125", "0.1250001")],
)
def test_genuinely_different_magnitudes_do_not_collide(tmp_path, policy, first, second):
    """No rounding to a fixed number of decimal places anywhere in the pipeline."""
    assert digest_of(tmp_path, first, "fraction", policy=policy, tag="a") != digest_of(
        tmp_path, second, "fraction", policy=policy, tag="b"
    )


def test_the_canonical_payload_serializes_magnitudes_as_strings_not_floats(tmp_path, policy):
    loaded = contract.load_scenario_document(
        write(tmp_path, scenario_text("0.1", "percent")), policy=policy
    )
    payload = contract.canonical_scenario_payload(loaded)
    value = payload["shocks"][0]["signed_magnitude_fraction"]
    assert isinstance(value, str)
    assert value == "0.001"
    assert json.dumps(payload)  # would raise on a Decimal


def test_a_binary_float_handed_straight_to_the_validator_is_refused(policy):
    """Nothing upstream produces one, so a float here means a caller bypassed the loader."""
    error = refuse(
        document(
            shocks=[{"channel": "brent_crude_usd_bbl", "direction": "increase",
                     "magnitude": 0.30, "magnitude_unit": "fraction"}]
        ),
        policy,
    )
    assert error.code == "magnitude_not_a_number"


def test_shocks_are_canonically_sorted_by_channel(policy):
    result = contract.validate_scenario_document(
        document(
            shocks=[
                {"channel": "rubber_rss3_usd_kg", "direction": "decrease", "magnitude": 10,
                 "magnitude_unit": "percent"},
                {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 30,
                 "magnitude_unit": "percent"},
                {"channel": "aluminum_usd_mt", "direction": "increase", "magnitude": 20,
                 "magnitude_unit": "percent"},
            ]
        ),
        policy=policy,
    )
    assert result.channels == ("aluminum_usd_mt", "brent_crude_usd_bbl", "rubber_rss3_usd_kg")
    payload = contract.canonical_scenario_payload(result)
    assert [entry["channel"] for entry in payload["shocks"]] == list(result.channels)


# ---------------------------------------------------------------------------
# 6-13  Field-set and cardinality violations
# ---------------------------------------------------------------------------


def test_unknown_top_level_field_is_refused(policy):
    error = refuse(document(colour="blue"), policy)
    assert error.code == "unknown_field"
    assert error.field == "colour"


def test_unknown_per_shock_field_is_refused(policy):
    error = refuse(
        document(
            shocks=[{"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 30,
                     "magnitude_unit": "percent", "weight": 2}]
        ),
        policy,
    )
    assert error.code == "unknown_field"
    assert error.field == "weight"


def test_missing_required_top_level_field_is_refused(policy):
    payload = document()
    del payload["scenario_id"]
    error = refuse(payload, policy)
    assert error.code == "missing_field"
    assert error.field == "scenario_id"


def test_missing_required_shock_field_is_refused(policy):
    error = refuse(
        document(shocks=[{"channel": "brent_crude_usd_bbl", "direction": "increase",
                          "magnitude": 30}]),
        policy,
    )
    assert error.code == "missing_field"
    assert error.field == "magnitude_unit"


def test_wrong_schema_version_is_refused(policy):
    error = refuse(document(schema_version="structural_exposure_scenario_v2"), policy)
    assert error.code == "bad_schema_version"


@pytest.mark.parametrize(
    "scenario_id", ["ab", "Has-Capitals", "trailing space", "under_score_ok!", "-leading-dash",
                    "x" * 65]
)
def test_invalid_scenario_id_is_refused(policy, scenario_id):
    error = refuse(document(scenario_id=scenario_id), policy)
    assert error.code in {"bad_scenario_id", "overlong_field"}


def test_empty_shock_list_is_refused(policy):
    error = refuse(document(shocks=[]), policy)
    assert error.code == "no_shocks"


def test_more_than_eight_shocks_is_refused(policy):
    nine = [
        {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 1,
         "magnitude_unit": "percent"}
        for _ in range(9)
    ]
    error = refuse(document(shocks=nine), policy)
    assert error.code == "too_many_shocks"


# ---------------------------------------------------------------------------
# 14-16  Channels: unsupported, duplicated, and sharing one official sector
# ---------------------------------------------------------------------------


def test_unsupported_channel_uses_its_own_error_type_and_code(policy):
    with pytest.raises(contract.UnsupportedChannelError) as caught:
        contract.validate_scenario_document(
            document(
                shocks=[{"channel": "natural_gas_usd_mmbtu", "direction": "increase",
                         "magnitude": 30, "magnitude_unit": "percent"}]
            ),
            policy=policy,
        )
    error = caught.value
    assert error.code == "unsupported_channel"
    assert isinstance(error, contract.ScenarioContractError)
    assert error.details["registered"] == sorted(contract.REGISTERED_CHANNELS)


def test_a_repeated_channel_is_refused(policy):
    error = refuse(
        document(
            shocks=[
                {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 30,
                 "magnitude_unit": "percent"},
                {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 10,
                 "magnitude_unit": "percent"},
            ]
        ),
        policy,
    )
    assert error.code == "duplicate_channel"


@pytest.mark.parametrize(
    ("first", "second"),
    [("aluminum_usd_mt", "copper_usd_mt"), ("copper_usd_mt", "aluminum_usd_mt")],
)
def test_aluminum_and_copper_together_are_refused_for_sharing_sector_107(policy, first, second):
    error = refuse(
        document(
            shocks=[
                {"channel": first, "direction": "increase", "magnitude": 20,
                 "magnitude_unit": "percent"},
                {"channel": second, "direction": "increase", "magnitude": 20,
                 "magnitude_unit": "percent"},
            ]
        ),
        policy,
    )
    assert error.code == "shared_io_sector"
    assert error.details["io_sector_code"] == "107"
    assert error.details["channels"] == ["aluminum_usd_mt", "copper_usd_mt"]


def test_identical_magnitudes_do_not_make_a_shared_sector_acceptable(policy):
    """The refusal is about the sector, not about disagreeing numbers."""
    error = refuse(
        document(
            shocks=[
                {"channel": "aluminum_usd_mt", "direction": "increase", "magnitude": 20,
                 "magnitude_unit": "percent"},
                {"channel": "copper_usd_mt", "direction": "increase", "magnitude": 20,
                 "magnitude_unit": "percent"},
            ]
        ),
        policy,
    )
    assert error.code == "shared_io_sector"


# ---------------------------------------------------------------------------
# 17-27  Magnitude
# ---------------------------------------------------------------------------


def shock(**overrides) -> dict:
    base = {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 30,
            "magnitude_unit": "percent"}
    base.update(overrides)
    return base


@pytest.mark.parametrize("value", [True, False])
def test_boolean_magnitude_is_refused(policy, value):
    error = refuse(document(shocks=[shock(magnitude=value)]), policy)
    assert error.code == "magnitude_not_a_number"


def test_negative_magnitude_is_refused(policy):
    error = refuse(document(shocks=[shock(magnitude=-5)]), policy)
    assert error.code == "magnitude_negative"


def test_nan_magnitude_is_refused(policy):
    error = refuse(document(shocks=[shock(magnitude=Decimal("NaN"))]), policy)
    assert error.code == "magnitude_not_finite"


@pytest.mark.parametrize("value", [Decimal("Infinity"), Decimal("-Infinity")])
def test_infinite_magnitude_is_refused(policy, value):
    error = refuse(document(shocks=[shock(magnitude=value)]), policy)
    assert error.code == "magnitude_not_finite"


@pytest.mark.parametrize("spelling", [".nan", ".inf", "-.inf"])
def test_a_non_finite_yaml_lexeme_is_refused_through_the_real_loading_path(
    tmp_path, policy, spelling
):
    """``.nan`` and ``.inf`` reach the validator as non-finite decimals, not as parse errors.

    The refusal then names the field, which is a better answer than "the file was
    malformed" — the file is fine, the number is not.
    """
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(spelling, "fraction")), policy=policy
        )
    assert caught.value.code == "magnitude_not_finite"
    assert caught.value.field == "shocks[0].magnitude"


@pytest.mark.parametrize("spelling", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_json_literal_is_refused(tmp_path, policy, spelling):
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text(spelling, "fraction", fmt="json"), name="n.json"),
            policy=policy,
        )
    assert caught.value.code == "magnitude_not_finite"


def test_a_sexagesimal_yaml_float_is_refused_as_a_magnitude(tmp_path, policy):
    """YAML 1.1 resolves ``190:20:30.15`` as a float. Decimal cannot hold it exactly.

    It comes through as the original text and is refused by the magnitude check, so
    the message names the field rather than reporting a malformed document.
    """
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(
            write(tmp_path, scenario_text("190:20:30.15", "fraction")), policy=policy
        )
    assert caught.value.code == "magnitude_not_a_number"


def test_an_increase_of_exactly_one_hundred_percent_carries_no_extreme_warning(policy):
    result = contract.validate_scenario_document(
        document(shocks=[shock(magnitude=100)]), policy=policy
    )
    assert result.shocks[0].magnitude_fraction == pytest.approx(1.0)
    assert result.warning_codes == ()


def test_an_increase_above_one_hundred_percent_is_accepted_with_a_warning(policy):
    result = contract.validate_scenario_document(
        document(shocks=[shock(magnitude=250)]), policy=policy
    )
    assert result.warning_codes == ("extreme_increase_magnitude",)


def test_an_increase_of_exactly_one_thousand_percent_is_accepted_with_a_warning(policy):
    result = contract.validate_scenario_document(
        document(shocks=[shock(magnitude=1000)]), policy=policy
    )
    assert result.shocks[0].magnitude_fraction == pytest.approx(10.0)
    assert result.warning_codes == ("extreme_increase_magnitude",)


def test_an_increase_above_one_thousand_percent_is_refused(policy):
    error = refuse(document(shocks=[shock(magnitude=Decimal("1000.1"))]), policy)
    assert error.code == "magnitude_increase_above_ceiling"
    assert error.details["channel"] == "brent_crude_usd_bbl"
    assert error.details["ceiling"] == "10"


def test_a_decrease_of_exactly_one_hundred_percent_is_accepted(policy):
    result = contract.validate_scenario_document(
        document(shocks=[shock(direction="decrease", magnitude=100)]), policy=policy
    )
    assert result.shocks[0].signed_magnitude_fraction == pytest.approx(-1.0)
    assert result.warning_codes == ()


def test_a_decrease_above_one_hundred_percent_is_refused(policy):
    error = refuse(
        document(shocks=[shock(direction="decrease", magnitude=Decimal("100.1"))]), policy
    )
    assert error.code == "magnitude_decrease_above_ceiling"
    assert error.details["channel"] == "brent_crude_usd_bbl"


# ---------------------------------------------------------------------------
# Zero-magnitude warnings: per shock, and for the scenario
# ---------------------------------------------------------------------------


def test_a_single_zero_shock_warns_for_that_channel_and_for_the_scenario(policy):
    result = contract.validate_scenario_document(
        document(shocks=[shock(magnitude=0)]), policy=policy
    )
    assert result.warning_codes == (
        "zero_magnitude_no_discrimination",
        "zero_magnitude_no_discrimination",
    )
    per_shock, scenario_level = result.warnings
    assert per_shock.channel == "brent_crude_usd_bbl"
    assert per_shock.field == "magnitude"
    assert per_shock.is_scenario_level is False
    assert scenario_level.channel is None
    assert scenario_level.field == "shocks"
    assert scenario_level.is_scenario_level is True
    assert result.all_shocks_are_zero is True
    assert result.zero_magnitude_channels == ("brent_crude_usd_bbl",)
    assert result.shocks[0].signed_magnitude_fraction == Decimal(0)
    assert result.shocks[0].is_zero is True


def test_a_mixed_scenario_still_reports_the_zero_shock(policy):
    """One zero beside one real shock is the case a scenario-level-only warning misses."""
    result = contract.validate_scenario_document(
        document(
            shocks=[
                {"channel": "rubber_rss3_usd_kg", "direction": "increase", "magnitude": 0,
                 "magnitude_unit": "percent"},
                {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 30,
                 "magnitude_unit": "percent"},
            ]
        ),
        policy=policy,
    )
    assert result.all_shocks_are_zero is False
    assert result.zero_magnitude_channels == ("rubber_rss3_usd_kg",)
    assert result.warning_codes == ("zero_magnitude_no_discrimination",)
    warning = result.warnings[0]
    assert warning.channel == "rubber_rss3_usd_kg"
    assert warning.is_scenario_level is False
    assert result.scenario_level_warnings == ()
    assert result.warnings_for("rubber_rss3_usd_kg") == (warning,)
    assert result.warnings_for("brent_crude_usd_bbl") == ()


def test_every_zero_shock_warns_and_the_scenario_warning_comes_last(policy):
    result = contract.validate_scenario_document(
        document(
            shocks=[
                {"channel": "rubber_rss3_usd_kg", "direction": "decrease", "magnitude": 0,
                 "magnitude_unit": "percent"},
                {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 0,
                 "magnitude_unit": "fraction"},
            ]
        ),
        policy=policy,
    )
    assert result.all_shocks_are_zero is True
    assert result.zero_magnitude_channels == ("brent_crude_usd_bbl", "rubber_rss3_usd_kg")
    assert [w.channel for w in result.warnings] == [
        "brent_crude_usd_bbl",
        "rubber_rss3_usd_kg",
        None,
    ]
    assert len(result.scenario_level_warnings) == 1


def test_warning_order_follows_canonical_channel_order_not_document_order(policy):
    """Two documents differing only in the order the author listed the shocks."""
    first = {"channel": "rubber_rss3_usd_kg", "direction": "increase", "magnitude": 0,
             "magnitude_unit": "percent"}
    second = {"channel": "aluminum_usd_mt", "direction": "increase", "magnitude": 0,
              "magnitude_unit": "percent"}
    one = contract.validate_scenario_document(document(shocks=[first, second]), policy=policy)
    two = contract.validate_scenario_document(document(shocks=[second, first]), policy=policy)
    assert [w.channel for w in one.warnings] == [w.channel for w in two.warnings]
    assert [w.channel for w in one.warnings] == ["aluminum_usd_mt", "rubber_rss3_usd_kg", None]
    assert contract.canonical_input_sha256(one) == contract.canonical_input_sha256(two)


def test_an_extreme_warning_names_its_channel(policy):
    result = contract.validate_scenario_document(
        document(
            shocks=[
                {"channel": "brent_crude_usd_bbl", "direction": "increase", "magnitude": 250,
                 "magnitude_unit": "percent"},
                {"channel": "aluminum_usd_mt", "direction": "increase", "magnitude": 20,
                 "magnitude_unit": "percent"},
            ]
        ),
        policy=policy,
    )
    assert result.warning_codes == ("extreme_increase_magnitude",)
    assert result.warnings[0].channel == "brent_crude_usd_bbl"
    assert result.warnings_for("aluminum_usd_mt") == ()


def test_a_scenario_with_no_zero_shock_carries_no_zero_warning(policy):
    result = contract.validate_scenario_document(document(), policy=policy)
    assert result.warnings == ()
    assert result.all_shocks_are_zero is False
    assert result.zero_magnitude_channels == ()


# ---------------------------------------------------------------------------
# 28-33  Units, direction, dates and text limits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("unit", ["usd_per_bbl", "index_points", "percentage", "", "PERCENT"])
def test_unsupported_magnitude_unit_is_refused(policy, unit):
    error = refuse(document(shocks=[shock(magnitude_unit=unit)]), policy)
    assert error.code == "unsupported_magnitude_unit"


@pytest.mark.parametrize("direction", ["up", "rise", "Increase", "", "neutral"])
def test_invalid_direction_is_refused(policy, direction):
    error = refuse(document(shocks=[shock(direction=direction)]), policy)
    assert error.code == "bad_direction"


@pytest.mark.parametrize(
    "value", ["2026-02-30", "2025-02-29", "2026-13-01", "2026-00-10", "04-09-2026", "2026-9-4"]
)
def test_a_scenario_date_that_is_not_a_real_calendar_date_is_refused(policy, value):
    error = refuse(document(scenario_date=value), policy)
    assert error.code == "bad_scenario_date"


def test_a_valid_leap_day_is_accepted(policy):
    result = contract.validate_scenario_document(document(scenario_date="2024-02-29"),
                                                 policy=policy)
    assert result.scenario_date == "2024-02-29"


def test_scenario_date_never_becomes_a_coefficient_vintage_claim(policy):
    early = contract.validate_scenario_document(document(scenario_date="2016-01-31"),
                                                policy=policy)
    late = contract.validate_scenario_document(document(scenario_date="2026-09-04"), policy=policy)
    without = contract.validate_scenario_document(document(), policy=policy)
    for result in (early, late, without):
        assert result.structural_reference_year == contract.STRUCTURAL_REFERENCE_YEAR == 2015
        assert result.scenario_date_is_metadata_only is True
        assert result.coefficient_vintage_is_scenario_date is False
    assert early.structural_reference_year == late.structural_reference_year


def test_an_overlong_scenario_name_is_refused(policy):
    error = refuse(document(scenario_name="x" * 121), policy)
    assert error.code == "overlong_field"
    assert error.field == "scenario_name"


def test_an_overlong_note_is_refused(policy):
    error = refuse(document(note="x" * 501), policy)
    assert error.code == "overlong_field"


def test_an_overlong_shock_note_is_refused(policy):
    error = refuse(document(shocks=[shock(note="x" * 501)]), policy)
    assert error.code == "overlong_field"


# ---------------------------------------------------------------------------
# 34-38  The parsing trust boundary
# ---------------------------------------------------------------------------


def test_a_duplicate_yaml_key_is_refused_rather_than_silently_resolved(tmp_path, policy):
    text = (
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: crude-oil-plus-30\n"
        "scenario_id: crude-oil-plus-40\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        "    direction: increase\n"
        "    magnitude: 30\n"
        "    magnitude_unit: percent\n"
    )
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text), policy=policy)
    assert caught.value.code == "duplicate_mapping_key"
    assert caught.value.field == "scenario_id"


def test_a_duplicate_key_inside_a_shock_is_refused(tmp_path, policy):
    text = (
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: crude-oil-plus-30\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        "    direction: increase\n"
        "    magnitude: 30\n"
        "    magnitude: 40\n"
        "    magnitude_unit: percent\n"
    )
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text), policy=policy)
    assert caught.value.code == "duplicate_mapping_key"


def test_a_duplicate_json_key_is_refused(tmp_path, policy):
    text = (
        '{"schema_version": "structural_exposure_scenario_v1",'
        ' "scenario_id": "crude-oil-plus-30",'
        ' "scenario_id": "crude-oil-plus-40",'
        ' "shocks": [{"channel": "brent_crude_usd_bbl", "direction": "increase",'
        ' "magnitude": 30, "magnitude_unit": "percent"}]}'
    )
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text, name="scenario.json"), policy=policy)
    assert caught.value.code == "duplicate_mapping_key"


@pytest.mark.parametrize("name", ["scenario.txt", "scenario.toml", "scenario", "scenario.yaml.bak"])
def test_an_unsupported_file_extension_is_refused(tmp_path, policy, name):
    path = tmp_path / name
    path.write_text("schema_version: structural_exposure_scenario_v1\n", encoding="utf-8")
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(path, policy=policy)
    assert caught.value.code == "unsupported_extension"


def test_an_oversized_input_is_refused_before_it_is_parsed(tmp_path, policy):
    path = tmp_path / "scenario.yaml"
    # Unparseable on purpose: reaching the parser would report a malformed document
    # instead, so the code that comes back proves the size check ran first.
    path.write_text("{" * (policy.max_input_bytes + 1024), encoding="utf-8")
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(path, policy=policy)
    assert caught.value.code == "input_too_large"
    assert caught.value.details["limit"] == policy.max_input_bytes


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("scenario.yaml", "shocks: [\n  - broken\n"),
        ("scenario.yaml", "\tnot: yaml\n"),
        ("scenario.json", '{"schema_version": '),
        ("scenario.json", "not json at all"),
    ],
)
def test_a_malformed_document_returns_a_controlled_contract_error(tmp_path, policy, name, text):
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text, name=name), policy=policy)
    assert caught.value.code in {"malformed_document", "document_not_a_mapping"}


@pytest.mark.parametrize("text", ["- a\n- b\n", "just a string\n", "42\n", ""])
def test_a_document_that_is_not_a_mapping_is_refused(tmp_path, policy, text):
    with pytest.raises(contract.ScenarioContractError) as caught:
        contract.load_scenario_document(write(tmp_path, text), policy=policy)
    assert caught.value.code in {"document_not_a_mapping", "malformed_document"}


# ---------------------------------------------------------------------------
# 39-42, 46  Policy configuration and schema agreement
# ---------------------------------------------------------------------------


def raw_policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


def write_policy(tmp_path: Path, mutate) -> Path:
    data = raw_policy()
    mutate(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    return path


def test_the_shipped_policy_loads_and_declares_what_the_validator_implements(policy):
    assert policy.accepted_input_schema_version == contract.INPUT_SCHEMA_VERSION
    assert policy.structural_reference_year == 2015
    assert policy.channel_names == tuple(sorted(contract.REGISTERED_CHANNELS))
    assert policy.registered_primary_basis == "direct"
    assert policy.total_requirement_role == "structural_sensitivity_only"
    assert policy.basis_must_be_explicit is True
    assert policy.shared_io_sector_policy == "reject_scenario"
    assert policy.magnitude.limits_are_learned_thresholds is False
    assert policy.magnitude.limits_are_validation_policy is True


@pytest.mark.parametrize(
    "key",
    ["channels", "magnitude_policy", "accepted_input_schema_version", "structural_reference_year",
     "allowed_magnitude_units", "allowed_directions", "shared_io_sector_policy",
     "supported_bases", "registered_primary_basis", "max_input_bytes"],
)
def test_a_policy_missing_a_required_key_is_refused(tmp_path, key):
    path = write_policy(tmp_path, lambda data: data.pop(key))
    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(path)


def test_a_policy_that_declares_a_channel_twice_is_refused(tmp_path):
    def mutate(data):
        data["channels"].append(dict(data["channels"][0]))

    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, mutate))


def test_a_policy_that_names_an_unregistered_channel_is_refused(tmp_path):
    def mutate(data):
        data["channels"].append(
            {"channel": "natural_gas_usd_mmbtu", "io_sector_code": "031",
             "io_sector_label": "Petroleum and natural gas"}
        )

    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, mutate))


def test_a_policy_that_drops_a_registered_channel_is_refused(tmp_path):
    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, lambda data: data["channels"].pop()))


def test_a_policy_that_reintroduces_sector_093_is_refused(tmp_path):
    def mutate(data):
        data["channels"][0]["io_sector_code"] = "093"

    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, mutate))


@pytest.mark.parametrize(
    "mutation",
    [
        {"limits_are_learned_thresholds": True},
        {"limits_are_validation_policy": False},
        {"percent_to_fraction_divisor": 1000},
        {"increase_warn_above_fraction": 0},
        {"increase_warn_above_fraction": 50.0},
        {"decrease_refuse_above_fraction": 0},
        {"increase_refuse_above_fraction": "ten"},
    ],
)
def test_a_malformed_magnitude_policy_is_refused(tmp_path, mutation):
    def mutate(data):
        data["magnitude_policy"].update(mutation)

    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, mutate))


@pytest.mark.parametrize(
    "mutation",
    [
        {"shared_io_sector_policy": "deduplicate"},
        {"shared_io_sector_policy": "keep_largest"},
        {"registered_primary_basis": "total_requirement"},
        {"total_requirement_role": "primary"},
        {"basis_must_be_explicit": False},
        {"scenario_date_is_metadata_only": False},
        {"accepted_input_schema_version": "structural_exposure_scenario_v2"},
        {"structural_reference_year": 2021},
        {"allowed_magnitude_units": ["percent", "fraction", "usd_per_bbl"]},
        {"accepted_input_extensions": [".yaml", ".yml", ".json", ".txt"]},
    ],
)
def test_a_policy_that_weakens_a_governance_rule_is_refused(tmp_path, mutation):
    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, lambda data: data.update(mutation)))


def test_sector_093_appears_nowhere_as_a_channel(policy):
    assert "093" not in {entry.io_sector_code for entry in policy.channels}
    declared = raw_policy()
    assert [entry["io_sector_code"] for entry in declared["channels"]] == ["031", "107", "107",
                                                                          "095"]
    excluded = {entry["io_sector_code"] for entry in declared["excluded_channels"]}
    assert "093" in excluded


def test_schema_and_runtime_field_sets_agree():
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["document_schema_version"] == contract.INPUT_SCHEMA_VERSION
    assert set(schema["top_level"]["required"]) == set(contract.TOP_LEVEL_REQUIRED_FIELDS)
    assert set(schema["top_level"]["optional"]) == set(contract.TOP_LEVEL_OPTIONAL_FIELDS)
    assert set(schema["shock"]["required"]) == set(contract.SHOCK_REQUIRED_FIELDS)
    assert set(schema["shock"]["optional"]) == set(contract.SHOCK_OPTIONAL_FIELDS)

    top_fields = {entry["name"] for entry in schema["top_level"]["fields"]}
    assert top_fields == set(
        contract.TOP_LEVEL_REQUIRED_FIELDS | contract.TOP_LEVEL_OPTIONAL_FIELDS
    )
    shock_fields = {entry["name"] for entry in schema["shock"]["fields"]}
    assert shock_fields == set(contract.SHOCK_REQUIRED_FIELDS | contract.SHOCK_OPTIONAL_FIELDS)

    by_name = {entry["name"]: entry for entry in schema["shock"]["fields"]}
    assert set(by_name["channel"]["allowed"]) == set(contract.REGISTERED_CHANNELS)
    assert tuple(by_name["direction"]["allowed"]) == contract.ALLOWED_DIRECTIONS
    assert tuple(by_name["magnitude_unit"]["allowed"]) == contract.ALLOWED_MAGNITUDE_UNITS
    assert {entry["name"] for entry in schema["excluded_fields"]} == set(
        contract.EXCLUDED_INPUT_FIELDS
    )


# ---------------------------------------------------------------------------
# 43-45  Structural guards on the module itself
# ---------------------------------------------------------------------------


def test_validation_writes_nothing(tmp_path, policy):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "other.txt").write_bytes(b"untouched")
    path = write(tmp_path, document())
    before = tree_snapshot(tmp_path)
    contract.load_scenario_document(path, policy=policy)
    for payload in (document(colour="blue"), document(shocks=[])):
        with pytest.raises(contract.ScenarioContractError):
            contract.validate_scenario_document(payload, policy=policy)
    assert tree_snapshot(tmp_path) == before


def test_the_no_write_snapshot_detects_every_kind_of_change(tmp_path):
    """The snapshot above passes; this proves it is capable of failing.

    Six mutations, each chosen because at least one weaker snapshot would miss it. A
    size-only snapshot misses the same-length edit; a content-only snapshot misses
    the identical-byte rewrite; neither sees a directory appear.
    """
    target = tmp_path / "file.txt"
    target.write_bytes(b"aaaa")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "kept.txt").write_bytes(b"kept")
    baseline = tree_snapshot(tmp_path)
    assert tree_snapshot(tmp_path) == baseline  # stable when nothing happens

    # 1. same-length content replacement — identical st_size, different bytes
    target.write_bytes(b"bbbb")
    assert target.stat().st_size == 4
    assert tree_snapshot(tmp_path) != baseline
    target.write_bytes(b"aaaa")

    # 2. identical-byte rewrite with a changed mtime — identical bytes and size
    restored = tree_snapshot(tmp_path)
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert target.read_bytes() == b"aaaa"
    assert tree_snapshot(tmp_path) != restored

    # 3. an added file
    after_touch = tree_snapshot(tmp_path)
    added = tmp_path / "added.txt"
    added.write_bytes(b"new")
    assert tree_snapshot(tmp_path) != after_touch

    # 4. a deleted file
    with_added = tree_snapshot(tmp_path)
    added.unlink()
    assert tree_snapshot(tmp_path) != with_added

    # 5. an added directory
    without_added = tree_snapshot(tmp_path)
    (tmp_path / "fresh").mkdir()
    assert tree_snapshot(tmp_path) != without_added

    # 6. a deleted directory
    with_fresh = tree_snapshot(tmp_path)
    (tmp_path / "fresh").rmdir()
    assert tree_snapshot(tmp_path) != with_fresh
    assert tree_snapshot(tmp_path) == without_added


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


#: Directory names this repository actually has. A constant equal to one of these
#: is a path segment; the same word inside a sentence is not, which is why the
#: match is on the whole value.
_PATH_SEGMENT_NAMES = frozenset(
    {"configs", "schemas", "docs", "scripts", "src", "tests", "examples", "results",
     "data", "raw", "features", "interim", "targets", "processed", "model_input", "models",
     ".obsidian", ".venv"}
)
#: ``.parquet`` is seven characters. An earlier version of this pattern allowed six
#: and silently failed to recognise the single most important artifact extension in
#: the project, which is why the planted-reach test below exists.
_FILENAME_SHAPE = re.compile(r"^\.?[A-Za-z0-9_][\w\-]*(\.[A-Za-z0-9]{1,8})+$")
_REGEX_METACHARACTERS = frozenset("^$*+?()[]{}|")


def _looks_like_a_path(value: str) -> bool:
    """Whether a string constant could name something on disk.

    Excludes anything containing whitespace — a sentence mentioning ``I/O`` is prose,
    not a path — and anything carrying regular-expression metacharacters, because the
    date pattern contains backslashes and is not a Windows path.
    """
    if not value or any(character.isspace() for character in value):
        return False
    if set(value) & _REGEX_METACHARACTERS:
        return False
    return (
        "/" in value
        or "\\" in value
        or value in _PATH_SEGMENT_NAMES
        or bool(_FILENAME_SHAPE.match(value))
    )


def filesystem_constants(path: Path) -> set[str]:
    """String constants that could name a file or directory, docstrings excluded.

    A path is usually built segment by segment — ``Path(...) / "data" / "raw"`` — so
    looking only for constants containing a separator finds almost nothing and
    proves almost nothing. This collects every constant that could *be* a segment or
    a filename, and the test whitelists the result. Whitelisting is the fail-closed
    direction: a new path the module did not previously reach shows up as a failure
    rather than as silence.

    Docstrings are dropped first. A module or function docstring is documentation,
    and a guard that fails because prose names a directory is the failure mode this
    project has already hit twice.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
                node.body[0].value, ast.Constant
            ) and isinstance(node.body[0].value.value, str):
                node.body[0].value.value = ""
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _looks_like_a_path(node.value)
    }


@pytest.mark.parametrize("source", [CONTRACT_SOURCE, PACKAGE_SOURCE])
def test_the_scenario_package_imports_nothing_that_reaches_a_network(source):
    forbidden = {"socket", "ssl", "urllib", "urllib.request", "http", "http.client", "requests",
                 "httpx", "ftplib", "smtplib", "telnetlib", "xmlrpc", "webbrowser"}
    imported = imported_modules(source)
    assert not {name.split(".")[0] for name in imported} & {n.split(".")[0] for n in forbidden}


@pytest.mark.parametrize("source", [CONTRACT_SOURCE, PACKAGE_SOURCE])
def test_the_scenario_package_imports_no_model_target_vault_or_data_module(source):
    forbidden_prefixes = (
        "thai_supply_chain_ews.models",
        "thai_supply_chain_ews.modeling",
        "thai_supply_chain_ews.targets",
        "thai_supply_chain_ews.evaluation",
        "thai_supply_chain_ews.vault",
        "thai_supply_chain_ews.data",
        "thai_supply_chain_ews.features",
        "thai_supply_chain_ews.matrices",
        "thai_supply_chain_ews.structure",
        "thai_supply_chain_ews.synthesis",
        "thai_supply_chain_ews.release",
    )
    offending = [name for name in imported_modules(source) if name.startswith(forbidden_prefixes)]
    assert offending == []


def test_the_contract_module_can_reach_exactly_one_file_and_it_is_the_policy():
    """A whitelist, not a blacklist.

    The module is allowed to name ``configs`` and its own policy file. Anything else
    that could be a path segment or a filename is a finding, whether or not anybody
    thought to forbid it in advance — which is the point: a blacklist only catches
    the reaches somebody predicted.
    """
    assert filesystem_constants(CONTRACT_SOURCE) == {"configs", "structural_exposure_scenario.yaml"}


def test_the_package_init_names_no_file_at_all():
    assert filesystem_constants(PACKAGE_SOURCE) == set()


@pytest.mark.parametrize("source", [CONTRACT_SOURCE, PACKAGE_SOURCE])
def test_no_constant_reaches_data_a_locked_outcome_or_a_generated_table(source):
    forbidden_fragments = ("data/", "raw", "features", "interim", "targets", "model_input",
                           "processed", "locked", "final_test", ".parquet", ".joblib", ".pkl",
                           ".obsidian", ".venv")
    offending = [
        value
        for value in filesystem_constants(source)
        if any(fragment in value for fragment in forbidden_fragments)
    ]
    assert offending == []


def test_the_filesystem_guard_would_actually_catch_a_reach(tmp_path):
    """The guard above passes; this proves it is capable of failing.

    A guard whose only evidence is that it passed on clean code is not evidence. The
    fixture below is exactly the shape the real risk takes — a path assembled from
    separate segments, none of which contains a separator — and it must be caught.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""A docstring naming data/raw/secret.parquet, which must be ignored."""\n'
        "from pathlib import Path\n"
        'GOOD = Path(__file__) / "configs" / "structural_exposure_scenario.yaml"\n'
        'BAD = Path(__file__) / "data" / "raw" / "locked_outcome.parquet"\n',
        encoding="utf-8",
    )
    found = filesystem_constants(planted)
    assert {"data", "raw", "locked_outcome.parquet"} <= found
    assert "data/raw/secret.parquet" not in found  # the docstring was dropped
    assert {"configs", "structural_exposure_scenario.yaml"} <= found


def test_phase_three_ships_only_reviewed_modules_and_no_unreviewed_module():
    # Phase 3 deliberately added the report builders and the command-line entry point.
    # The set stays closed: any module nobody reviewed must still make this fail, which
    # a subset, prefix or count assertion would not.
    package = CONTRACT_SOURCE.parent
    present = sorted(path.name for path in package.glob("*.py"))
    assert present == [
        "__init__.py",
        "__main__.py",
        "artifacts.py",
        "contract.py",
        "exposure.py",
        "report.py",
    ]


def test_the_public_api_exposes_only_reviewed_phase_one_two_and_three_names():
    from thai_supply_chain_ews import scenario

    # Two sentinels have now been completed by a reviewed phase and left this set:
    # `exposure` in Phase 2 and `report` in Phase 3, both exported as submodules exactly
    # as `contract` is. Everything still listed is unbuilt, and `main` stays listed
    # because the command-line entry point is deliberately not part of the API.
    unfinished = {"run", "rank", "score", "render", "explain", "main", "cli",
                  "load_artifacts", "predict", "forecast"}
    assert not set(scenario.__all__) & unfinished
    assert {"artifacts", "contract", "exposure", "report"} <= set(scenario.__all__)


def test_the_parsing_helper_is_not_part_of_the_public_api():
    """A parse step is a seam, not an interface.

    Exporting it would let later code depend on a mapping that has been read but not
    checked, which is the one intermediate state this module exists to keep private.
    The duplicate-key and malformed-document tests all go through
    ``load_scenario_document`` and files under ``tmp_path``, so nothing needs it.
    """
    from thai_supply_chain_ews import scenario

    assert "parse_document_text" not in scenario.__all__
    assert "parse_document_text" not in contract.__all__
    assert not hasattr(scenario, "parse_document_text")
    assert not hasattr(contract, "parse_document_text")
    assert hasattr(contract, "_parse_document_text")


def test_the_excluded_field_set_is_frozen_for_schema_v1():
    """Changing this set changes which machine-readable code a document receives.

    A caller branching on ``excluded_field`` versus ``unknown_field`` would change
    behaviour without its document changing, so for ``structural_exposure_scenario_v1``
    the set is pinned in three places at once and a future change takes a new schema
    version instead.
    """
    frozen = {"as_of_date", "duration_months", "affected_trading_partner", "basis",
              "company_id", "output_path", "model", "risk_threshold"}
    assert set(contract.EXCLUDED_INPUT_FIELDS) == frozen
    assert contract.INPUT_SCHEMA_VERSION == "structural_exposure_scenario_v1"

    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["excluded_fields_are_frozen_for_this_schema_version"] is True
    assert {entry["name"] for entry in schema["excluded_fields"]} == frozen

    declared = raw_policy()
    assert declared["excluded_input_fields_are_frozen_for_this_schema_version"] is True
    assert set(declared["excluded_input_fields"]) == frozen


# ---------------------------------------------------------------------------
# 47-48  Fields refused by name, with a reason
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_months", 6), ("affected_trading_partner", "CHN"), ("as_of_date", "2026-09-04"),
     ("company_id", "ACME"), ("output_path", "out.json"), ("model", "ridge"),
     ("risk_threshold", 85)],
)
def test_an_excluded_top_level_field_is_refused_by_name_with_its_reason(policy, field, value):
    error = refuse(document(**{field: value}), policy)
    assert error.code == "excluded_field"
    assert error.field == field
    assert contract.EXCLUDED_INPUT_FIELDS[field] in str(error)


def test_basis_inside_the_input_document_is_refused(policy):
    error = refuse(document(basis="total_requirement"), policy)
    assert error.code == "excluded_field"
    assert error.field == "basis"


def test_basis_inside_a_shock_is_refused(policy):
    error = refuse(document(shocks=[dict(shock(), basis="direct")]), policy)
    assert error.code == "excluded_field"


# ---------------------------------------------------------------------------
# Canonical form
# ---------------------------------------------------------------------------


def test_the_canonical_payload_excludes_the_source_path_and_the_raw_unit(tmp_path, policy):
    first = contract.load_scenario_document(write(tmp_path, document()), policy=policy)
    second = contract.load_scenario_document(
        write(tmp_path, document(), name="elsewhere.yaml"), policy=policy
    )
    assert contract.canonical_input_sha256(first) == contract.canonical_input_sha256(second)
    payload = contract.canonical_scenario_payload(first)
    assert "magnitude_unit" not in payload["shocks"][0]
    assert "magnitude" not in payload["shocks"][0]
    assert set(payload) == {"schema_version", "scenario_id", "scenario_name", "scenario_date",
                            "note", "shocks"}


def test_the_digest_is_stable_across_repeated_validation(policy):
    digests = {
        contract.canonical_input_sha256(
            contract.validate_scenario_document(document(), policy=policy)
        )
        for _ in range(5)
    }
    assert len(digests) == 1


def test_direction_changes_the_digest(policy):
    up = contract.validate_scenario_document(document(), policy=policy)
    down = contract.validate_scenario_document(
        document(shocks=[shock(direction="decrease")]), policy=policy
    )
    assert contract.canonical_input_sha256(up) != contract.canonical_input_sha256(down)


def test_every_declared_error_code_is_a_known_code():
    assert contract.ScenarioContractError("x", code="unknown_field").code in (
        contract.CONTRACT_ERROR_CODES
    )


# ---------------------------------------------------------------------------
# The exception taxonomy: four kinds of wrong, four kinds of answer
# ---------------------------------------------------------------------------


def test_an_undeclared_error_code_is_an_internal_defect_not_a_policy_problem():
    """Raising a code no caller can branch on is a bug here, not a bad config.

    Reporting it as a policy error would send somebody to inspect a configuration
    file that is perfectly correct.
    """
    with pytest.raises(contract.ScenarioInternalError):
        contract.ScenarioContractError("x", code="invented_code")


def test_a_non_finite_decimal_reaching_the_formatter_is_an_internal_defect():
    """Validated magnitudes cannot be non-finite, so arriving here means a bypass."""
    for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(contract.ScenarioInternalError):
            contract.decimal_text(value)


def test_decimal_text_accepts_every_finite_decimal_it_promises_to():
    assert contract.decimal_text(Decimal("0.30")) == "0.3"
    assert contract.decimal_text(Decimal("-0.00")) == "0"
    assert contract.decimal_text(Decimal("1E+1")) == "10"
    assert contract.decimal_text(Decimal("-2.500")) == "-2.5"


def test_the_four_error_kinds_are_distinct_types():
    assert issubclass(contract.UnsupportedChannelError, contract.ScenarioContractError)
    assert issubclass(contract.ScenarioContractError, ValueError)
    assert issubclass(contract.ScenarioPolicyError, RuntimeError)
    assert issubclass(contract.ScenarioInternalError, RuntimeError)
    # An internal defect is never a contract violation, so `except ScenarioContractError`
    # around a validation call cannot swallow one.
    assert not issubclass(contract.ScenarioInternalError, contract.ScenarioContractError)
    assert not issubclass(contract.ScenarioInternalError, contract.ScenarioPolicyError)
    assert not issubclass(contract.ScenarioPolicyError, contract.ScenarioInternalError)
    assert not issubclass(contract.ScenarioContractError, RuntimeError)


def test_malformed_input_still_raises_a_contract_error_not_an_internal_one(policy):
    for payload in (document(colour="blue"), document(shocks=[]), document(scenario_id="ab")):
        with pytest.raises(contract.ScenarioContractError):
            contract.validate_scenario_document(payload, policy=policy)
    with pytest.raises(contract.UnsupportedChannelError):
        contract.validate_scenario_document(
            document(shocks=[shock(channel="natural_gas_usd_mmbtu")]), policy=policy
        )


def test_malformed_policy_still_raises_a_policy_error_not_an_internal_one(tmp_path):
    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(write_policy(tmp_path, lambda data: data.pop("channels")))
    with pytest.raises(contract.ScenarioPolicyError):
        contract.load_policy(tmp_path / "does-not-exist.yaml")


def test_warning_codes_are_declared(policy):
    result = contract.validate_scenario_document(
        document(shocks=[shock(magnitude=0)]), policy=policy
    )
    assert set(result.warning_codes) <= contract.WARNING_CODES


# ---------------------------------------------------------------------------
# The canonical form does not depend on the caller's decimal context
#
# `decimal_text` decides how every magnitude is spelled, and that spelling goes into
# the canonical payload and therefore into the digest that identifies a scenario. It
# used to be `format(value.normalize(), "f")`, and `normalize` rounds to the ambient
# precision: under a precision-6 context the same shock produced a different string
# and a different digest than it did under the default one. Two people would then
# disagree about what a scenario *is* because of a global neither of them set.
#
# The same hazard reached the values themselves. Percent-to-fraction was a division
# and a decrease was a unary minus, both context operations, so a long magnitude was
# silently shortened on the way in.
# ---------------------------------------------------------------------------


AMBIENT_CONTEXTS = [
    (6, decimal.ROUND_DOWN),
    (9, decimal.ROUND_UP),
    (28, decimal.ROUND_HALF_EVEN),
    (50, decimal.ROUND_FLOOR),
    (80, decimal.ROUND_CEILING),
]

#: A magnitude far longer than any precision tried above, so a context-sensitive
#: operation anywhere in the path must lose digits from it. The run deliberately ends
#: in a non-zero digit: a trailing zero is not significant and canonicalisation drops
#: it, which would make a lost digit indistinguishable from a correctly stripped one.
LONG_DIGITS = "1234567891" * 12
LONG_FRACTION = "0." + LONG_DIGITS


def under(prec, rounding, work):
    """Run ``work`` under an ambient context, restoring the caller's afterwards."""
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.rounding = prec, rounding
        return work()


def test_decimal_text_is_identical_under_every_ambient_context():
    values = [
        Decimal("0.214130850110323640005"),
        Decimal(LONG_FRACTION),
        Decimal("-2.500"),
        Decimal("1E+1"),
        Decimal("0.30"),
        Decimal("123456789012345678901234567890"),
    ]
    for value in values:
        rendered = {
            under(prec, rounding, lambda value=value: contract.decimal_text(value))
            for prec, rounding in AMBIENT_CONTEXTS
        }
        assert len(rendered) == 1, f"{value!r} rendered {len(rendered)} different ways"


def test_decimal_text_keeps_every_significant_digit_of_a_long_decimal():
    text = contract.decimal_text(Decimal(LONG_FRACTION))
    assert text == LONG_FRACTION
    assert text.split(".")[1] == LONG_DIGITS
    assert Decimal(text) == Decimal(LONG_FRACTION)


def test_decimal_text_canonicalises_every_spelling_of_zero():
    for spelling in ("0", "-0", "0.0", "-0.00", "0E+5", "-0E-7", "0.000"):
        assert contract.decimal_text(Decimal(spelling)) == "0", spelling


def test_decimal_text_reads_the_representation_and_does_no_arithmetic():
    """Structural, not textual: the defect was a method call, so the guard reads calls.

    A comment saying "context-free" is not enforceable. ``normalize``, ``quantize``,
    ``scaleb`` and unary plus all round to the ambient precision, so none of them may
    appear, and ``as_tuple`` must, because reading the stored digits is the whole
    mechanism by which the function avoids them.
    """
    tree = ast.parse(CONTRACT_SOURCE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "decimal_text"
    )
    called = {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "as_tuple" in called
    assert not called & {"normalize", "quantize", "scaleb", "fma", "to_integral_value"}
    assert not [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd)
    ]


#: Canonical strings and digests produced by the implementation shipped in the Phase 1
#: commit, recorded before the context fix and asserted unchanged after it. The fix was
#: meant to remove a dependency on a global, not to renumber anything: if an ordinary
#: scenario's identity moved, every digest a reader already holds would be wrong.
PINNED_CANONICAL = {
    ("0.3", "fraction", "increase"): (
        "0.3", "0cbf497566546b5d1f2d075248f6be218efec4ca5faddaa844bbd328d2d86d3c",
    ),
    ("0.3", "fraction", "decrease"): (
        "-0.3", "213e70bd831fa8dd93132f0414166df1a54be95d8aa79462319a326fdc4ecde0",
    ),
    ("30", "percent", "increase"): (
        "0.3", "0cbf497566546b5d1f2d075248f6be218efec4ca5faddaa844bbd328d2d86d3c",
    ),
    ("30", "percent", "decrease"): (
        "-0.3", "213e70bd831fa8dd93132f0414166df1a54be95d8aa79462319a326fdc4ecde0",
    ),
    ("0.1", "percent", "increase"): (
        "0.001", "ca4d843d168c7113dd2201711ef11027aaa4b9c9814f13095f13a3d68e7035cf",
    ),
    ("0.1", "percent", "decrease"): (
        "-0.001", "d438fee0bf6d4dddbb587b5e43d23c3a7ee4222eb3a6348a9ebba58b51f646d8",
    ),
    ("25", "percent", "increase"): (
        "0.25", "ee463f5c27bf1f9e62b7b81f36e3b114c509569f2eca4ae3a535214a07ab2ae5",
    ),
    ("25", "percent", "decrease"): (
        "-0.25", "bd00cca873f01b5e6d2443c3ccd79901f9a5292aaee622406e9f09513ec14ea1",
    ),
    ("15", "percent", "increase"): (
        "0.15", "72d40d5e5f853e53347d1303f8a8d022e6ed1d86d79f8684941e70266c2c6da0",
    ),
    ("15", "percent", "decrease"): (
        "-0.15", "6e0f884a0d377d07b519ae03a43aeabb68101b3a0aeb6fe000f5c78178ef8d2a",
    ),
    ("2.5", "percent", "increase"): (
        "0.025", "c32ac7edb0897bfc9cb3feaae3278952ca9fdb530a2ed8099aae069607ca9ee7",
    ),
    ("2.5", "percent", "decrease"): (
        "-0.025", "488e79306484a797862ec8ea5e56e3fb969951786aa2b13204349796d811436d",
    ),
    ("1000", "percent", "increase"): (
        "10", "ea68068a20e57388299e5f3b43545f1309f122badb2fa5f6f30c510e1e0104dc",
    ),
    ("0", "fraction", "increase"): (
        "0", "e8bc7314ca89187cc438cedf79be8556b4307be4d3555e9113383ac088efda21",
    ),
    ("0", "fraction", "decrease"): (
        "0", "24f88afe235bf0e91d13ed32605f736267cc3f6732417f5bfcabb90c04699cdf",
    ),
    ("0.000", "percent", "increase"): (
        "0", "e8bc7314ca89187cc438cedf79be8556b4307be4d3555e9113383ac088efda21",
    ),
    ("1E+1", "percent", "increase"): (
        "0.1", "a9963c6b1a4d6f79880af0671d7028dc5c7b7d701792acb4bf2b5e0f1cd81455",
    ),
}


def pinned_scenario(tmp_path, magnitude, unit, direction, policy, name):
    path = write(
        tmp_path,
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: pinned-canonical\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        f"    direction: {direction}\n"
        f"    magnitude: {magnitude}\n"
        f"    magnitude_unit: {unit}\n",
        name=name,
    )
    return contract.load_scenario_document(path, policy=policy)


@pytest.mark.parametrize(("case", "expected"), sorted(PINNED_CANONICAL.items()))
def test_ordinary_canonical_strings_and_digests_are_unchanged(case, expected, tmp_path, policy):
    magnitude, unit, direction = case
    loaded = pinned_scenario(tmp_path, magnitude, unit, direction, policy, "pinned.yaml")
    assert loaded.shocks[0].canonical_signed_fraction == expected[0]
    assert contract.canonical_input_sha256(loaded) == expected[1]


@pytest.mark.parametrize(("case", "expected"), sorted(PINNED_CANONICAL.items()))
def test_ordinary_digests_are_also_unchanged_under_a_hostile_context(
    case, expected, tmp_path, policy
):
    """The pinned values are the answer in every context, not only the default one."""
    magnitude, unit, direction = case
    for index, (prec, rounding) in enumerate(AMBIENT_CONTEXTS):
        loaded = under(
            prec,
            rounding,
            lambda index=index: pinned_scenario(
                tmp_path, magnitude, unit, direction, policy, f"pinned{index}.yaml"
            ),
        )
        assert loaded.shocks[0].canonical_signed_fraction == expected[0]
        assert contract.canonical_input_sha256(loaded) == expected[1]


def test_a_long_percent_magnitude_keeps_every_digit_its_author_wrote(tmp_path, policy):
    """Percent-to-fraction shifts the point; it must not shorten the number.

    ``0.1234...`` percent is ``0.001234...`` with the same digits. A division would
    have produced the ambient precision's worth of them and raised nothing.
    """
    written = LONG_FRACTION
    loaded = pinned_scenario(tmp_path, written, "percent", "increase", policy, "long.yaml")
    accepted = loaded.shocks[0]
    assert accepted.magnitude == Decimal(written)
    assert accepted.canonical_signed_fraction == "0.00" + LONG_DIGITS
    assert len(accepted.magnitude_fraction.as_tuple().digits) == len(LONG_DIGITS)


def test_a_long_decrease_is_the_exact_mirror_of_its_increase(tmp_path, policy):
    """The negation is ``copy_negate``, so a decrease cannot be stored shorter."""
    up = pinned_scenario(tmp_path, LONG_FRACTION, "percent", "increase", policy, "up.yaml")
    down = pinned_scenario(tmp_path, LONG_FRACTION, "percent", "decrease", policy, "down.yaml")
    assert down.shocks[0].canonical_signed_fraction == (
        "-" + up.shocks[0].canonical_signed_fraction
    )
    assert (
        down.shocks[0].signed_magnitude_fraction.copy_negate()
        == up.shocks[0].signed_magnitude_fraction
    )


def test_a_long_magnitude_is_identical_under_every_ambient_context(tmp_path, policy):
    seen = set()
    for index, (prec, rounding) in enumerate(AMBIENT_CONTEXTS):
        loaded = under(
            prec,
            rounding,
            lambda index=index: pinned_scenario(
                tmp_path, LONG_FRACTION, "percent", "decrease", policy, f"long{index}.yaml"
            ),
        )
        seen.add(
            (
                loaded.shocks[0].canonical_signed_fraction,
                contract.canonical_input_sha256(loaded),
            )
        )
    assert len(seen) == 1
    assert len(next(iter(seen))[0].split(".")[1]) == len(LONG_DIGITS) + 2


def test_removing_the_context_free_conversions_would_make_these_tests_fail():
    """Mutation check: each replaced operation really is context-sensitive.

    The three operations the fix removed are performed here the way the module used to
    perform them. If any of them gave one answer in every context, the corresponding
    test above would pass whether or not the fix existed.
    """
    long_value = Decimal(LONG_FRACTION)
    hundred = Decimal(100)

    normalised = {
        under(prec, rounding, lambda: format(long_value.normalize(), "f"))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    divided = {
        under(prec, rounding, lambda: str(long_value / hundred))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    negated = {
        under(prec, rounding, lambda: str(-long_value)) for prec, rounding in AMBIENT_CONTEXTS
    }
    for label, mutated in (("normalize", normalised), ("divide", divided), ("negate", negated)):
        assert len(mutated) > 1, f"{label} collapsed to one answer; the guard proves nothing"

    fixed = {
        under(prec, rounding, lambda: contract.decimal_text(long_value))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    shifted = {
        under(prec, rounding, lambda: str(contract.scale_down_by_power_of_ten(long_value, 2)))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    flipped = {
        under(prec, rounding, lambda: str(long_value.copy_negate()))
        for prec, rounding in AMBIENT_CONTEXTS
    }
    assert len(fixed) == len(shifted) == len(flipped) == 1
