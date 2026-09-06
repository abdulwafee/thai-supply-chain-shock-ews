"""Phase 4 tests: the interactive scenario builder.

Sessions are driven in process with injected ``StringIO`` streams, which keeps the suite
fast and lets a case assert on the exact prompt text. Two cases additionally run the real
subprocess with ``text=False``, because the promise interactive mode makes is about
*bytes* — prompts on stderr, document on stdout, LF only, identical to the file-based
command — and a promise about bytes cannot be checked through a decoding layer.

The sharp cases are the ones about what interactive mode must *not* do: it must not invent
a scenario date, must not accept a magnitude the contract would refuse, must not compute
anything before the reader confirms, must not leave a file behind when a session is
cancelled, and must not put a single character of prompt text on standard output.
"""

from __future__ import annotations

import ast
import io
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from thai_supply_chain_ews.scenario import __main__ as cli
from thai_supply_chain_ews.scenario import contract as contract_module
from thai_supply_chain_ews.scenario import interactive as interactive_module
from thai_supply_chain_ews.scenario.contract import load_policy
from thai_supply_chain_ews.scenario.interactive import InteractiveCancelled, collect_request

ROOT = Path(__file__).resolve().parents[1]
CLI_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "__main__.py"
INTERACTIVE_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "interactive.py"

# Menu positions, taken from the policy's own declaration order rather than assumed.
BRENT, ALUMINIUM, COPPER, RUBBER = "1", "2", "3", "4"
INCREASE, DECREASE = "1", "2"
PERCENT, FRACTION = "1", "2"
DIRECT, TOTAL_REQUIREMENT = "1", "2"
JSON_FORMAT, MARKDOWN_FORMAT = "1", "2"
TERMINAL, NEW_FILE = "1", "2"


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def script(*, scenario_id="interactive-case", name="", date="", commodity=BRENT,
           direction=INCREASE, magnitude="30", unit=PERCENT, more="n", basis=DIRECT,
           output_format=JSON_FORMAT, destination=TERMINAL, path=None, confirm="y"):
    """The answers for one ordinary single-shock session, in prompt order."""
    lines = [scenario_id, name, date, commodity, direction, magnitude, unit, more,
             basis, output_format, destination]
    if path is not None:
        lines.append(path)
    lines.append(confirm)
    return lines


def session(lines, *, policy):
    """Run one collection session and return (request, prompt text)."""
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stderr = io.StringIO()
    request = collect_request(policy=policy, stdin=stdin, stderr=stderr)
    return request, stderr.getvalue()


def cancelled(lines, *, policy):
    """Run a session expected to cancel and return (exception, prompt text)."""
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stderr = io.StringIO()
    with pytest.raises(InteractiveCancelled) as caught:
        collect_request(policy=policy, stdin=stdin, stderr=stderr)
    return caught.value, stderr.getvalue()


class BinaryStream(io.StringIO):
    """A text stream with a real binary buffer, like the production ``sys.stdout``."""

    def __init__(self) -> None:
        super().__init__()
        self.buffer = io.BytesIO()


def drive(lines, *, capture_bytes=True):
    """Run the whole ``interactive`` command in process and return (code, out, err)."""
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stderr = io.StringIO()
    stdout = BinaryStream() if capture_bytes else io.StringIO()
    arguments = cli._build_parser().parse_args(["interactive"])
    code = cli._interactive(arguments, stdout, stdin=stdin, stderr=stderr)
    out = stdout.buffer.getvalue() if capture_bytes else stdout.getvalue().encode("utf-8")
    return code, out, stderr.getvalue()


# ---------------------------------------------------------------------------
# 1-3. The command exists, its help reads nothing, the old contracts are intact
# ---------------------------------------------------------------------------


def test_root_help_lists_interactive(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["--help"])
    assert caught.value.code == 0
    assert "interactive" in capsys.readouterr().out


def test_interactive_help_reads_nothing(capsys, monkeypatch):
    """No policy, no scenario file, no exposure artifact. Help is not a calculation."""
    def refuse(*args, **kwargs):
        raise AssertionError("interactive --help must not open a file")

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    with pytest.raises(SystemExit) as caught:
        cli.main(["interactive", "--help"])
    assert caught.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_interactive_takes_no_options():
    """Every choice is a prompt, so the subcommand carries no flag but ``--help``."""
    parser = cli._build_parser()
    subparsers = [a for a in parser._actions if a.dest == "command"][0]
    options = {o for a in subparsers.choices["interactive"]._actions for o in a.option_strings}
    assert options == {"-h", "--help"}


def test_the_existing_command_contracts_are_unchanged():
    """v1.2.1's parser surface for the three file-based commands, unaltered."""
    parser = cli._build_parser()
    subparsers = [a for a in parser._actions if a.dest == "command"][0]
    expected = {
        "validate": {"--input"},
        "run": {"--input", "--basis", "--format", "--output"},
        "explain": {"--input", "--basis", "--format", "--output", "--industry"},
    }
    for name, required in expected.items():
        actions = subparsers.choices[name]._actions
        got = {o for a in actions if a.required for o in a.option_strings
               if o.startswith("--")}
        assert got == required, name
        for action in actions:
            if action.option_strings and action.dest != "help":
                assert action.default in (None, False), (name, action.option_strings)
    optional = {o for a in subparsers.choices["explain"]._actions if not a.required
                for o in a.option_strings if o.startswith("--") and o != "--help"}
    assert optional == {"--all"}


# ---------------------------------------------------------------------------
# 4-12. The happy paths across every axis
# ---------------------------------------------------------------------------


def test_a_complete_single_shock_session_succeeds(policy):
    request, prompts = session(script(), policy=policy)
    assert request.scenario.scenario_id == "interactive-case"
    assert len(request.scenario.shocks) == 1
    assert request.basis == "direct"
    assert request.output_format == "json"
    assert request.output_target == cli.STDOUT_TARGET
    assert "Review" in prompts


@pytest.mark.parametrize(("choice", "channel"), [
    (BRENT, "brent_crude_usd_bbl"),
    (ALUMINIUM, "aluminum_usd_mt"),
    (COPPER, "copper_usd_mt"),
    (RUBBER, "rubber_rss3_usd_kg"),
])
def test_every_commodity_can_be_selected(policy, choice, channel):
    request, _ = session(script(commodity=choice), policy=policy)
    assert [s.channel for s in request.scenario.shocks] == [channel]


def test_the_menu_order_is_the_policy_declaration_order(policy):
    """A stable numbering is part of the interface; a reordering must fail a test."""
    assert [value for value, _ in interactive_module._channel_options(policy)] == [
        "brent_crude_usd_bbl", "aluminum_usd_mt", "copper_usd_mt", "rubber_rss3_usd_kg"]
    assert set(interactive_module.CHANNEL_DISPLAY_NAMES) == {e.channel for e in policy.channels}


@pytest.mark.parametrize(("choice", "direction"), [(INCREASE, "increase"),
                                                   (DECREASE, "decrease")])
def test_both_directions_work(policy, choice, direction):
    request, _ = session(script(direction=choice), policy=policy)
    assert request.scenario.shocks[0].direction == direction


@pytest.mark.parametrize(("choice", "unit"), [(PERCENT, "percent"), (FRACTION, "fraction")])
def test_both_magnitude_units_work(policy, choice, unit):
    magnitude = "30" if choice == PERCENT else "0.3"
    request, _ = session(script(magnitude=magnitude, unit=choice), policy=policy)
    shock = request.scenario.shocks[0]
    assert shock.magnitude_unit == unit
    assert shock.magnitude_fraction == Decimal("0.3")


def test_magnitude_stays_an_exact_decimal_and_never_becomes_a_float(policy):
    """0.1 has no exact binary representation; if it went through ``float`` it would show."""
    request, _ = session(script(magnitude="0.1", unit=FRACTION), policy=policy)
    shock = request.scenario.shocks[0]
    assert isinstance(shock.magnitude, Decimal)
    assert not isinstance(shock.magnitude, float)
    assert shock.magnitude == Decimal("0.1")
    assert str(shock.magnitude) == "0.1"
    assert shock.magnitude_fraction == Decimal("0.1")
    assert shock.magnitude - Decimal("0.1") == 0


def test_a_long_decimal_magnitude_keeps_every_digit(policy):
    text = "12.3456789012345678901234567890"
    request, _ = session(script(magnitude=text, unit=PERCENT), policy=policy)
    assert str(request.scenario.shocks[0].magnitude) == text


@pytest.mark.parametrize(("choice", "basis"), [(DIRECT, "direct"),
                                               (TOTAL_REQUIREMENT, "total_requirement")])
def test_both_bases_work(policy, choice, basis):
    request, _ = session(script(basis=choice), policy=policy)
    assert request.basis == basis


@pytest.mark.parametrize(("choice", "fmt"), [(JSON_FORMAT, "json"),
                                             (MARKDOWN_FORMAT, "markdown")])
def test_both_output_formats_work(policy, choice, fmt):
    request, _ = session(script(output_format=choice), policy=policy)
    assert request.output_format == fmt


def test_the_terminal_destination_uses_the_existing_stdout_target(policy):
    request, _ = session(script(destination=TERMINAL), policy=policy)
    assert request.output_target == cli.STDOUT_TARGET == "-"


def test_a_file_destination_is_asked_for_explicitly(tmp_path, policy):
    target = tmp_path / "report.json"
    request, _ = session(script(destination=NEW_FILE, path=str(target)), policy=policy)
    assert request.output_target == str(target)
    assert not target.exists(), "collecting answers must not create the file"


def test_a_path_containing_spaces_needs_no_quoting(tmp_path, policy):
    target = tmp_path / "a folder with spaces" / "the report.md"
    target.parent.mkdir()
    request, _ = session(script(destination=NEW_FILE, path=str(target)), policy=policy)
    assert request.output_target == str(target)
    assert " " in request.output_target


def test_a_multiple_shock_scenario_succeeds(policy):
    lines = ["multi-shock-case", "", "",
             BRENT, INCREASE, "30", PERCENT, "y",
             RUBBER, DECREASE, "10", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, _ = session(lines, policy=policy)
    assert {s.channel for s in request.scenario.shocks} == {
        "brent_crude_usd_bbl", "rubber_rss3_usd_kg"}
    assert len(request.scenario.shocks) == 2


# ---------------------------------------------------------------------------
# 13-17. Refusals and reprompting
# ---------------------------------------------------------------------------


def test_a_duplicate_channel_is_reprompted(policy):
    lines = ["duplicate-case", "", "",
             BRENT, INCREASE, "30", PERCENT, "y",
             BRENT,                      # refused: already in this scenario
             RUBBER, DECREASE, "10", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "already in this scenario" in prompts
    assert len(request.scenario.shocks) == 2


def test_aluminium_plus_copper_is_refused_before_any_calculation(policy):
    lines = ["shared-sector-case", "", "",
             ALUMINIUM, INCREASE, "30", PERCENT, "y",
             COPPER,                     # refused: sector 107 twice
             RUBBER, INCREASE, "10", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "107" in prompts
    assert "same measurement twice" in prompts
    assert {s.channel for s in request.scenario.shocks} == {
        "aluminum_usd_mt", "rubber_rss3_usd_kg"}


def test_the_shared_sector_refusal_happens_at_the_prompt(policy, monkeypatch):
    """It must be caught while the reader can still choose again, not after scoring."""
    monkeypatch.setattr(cli, "load_artifact_bundle", lambda *a, **k: pytest.fail(
        "no artifact may be loaded while answers are still being collected"))
    lines = ["shared-sector-early", "", "",
             ALUMINIUM, INCREASE, "30", PERCENT, "y",
             COPPER, RUBBER, INCREASE, "10", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    session(lines, policy=policy)


@pytest.mark.parametrize("bad", ["0", "5", "x", "", "1.5", "-1", " "])
def test_an_invalid_menu_choice_is_reprompted(policy, bad):
    lines = ["menu-retry-case", "", "", bad, BRENT, INCREASE, "30", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "enter a number from 1 to 4" in prompts
    assert request.scenario.shocks[0].channel == "brent_crude_usd_bbl"


@pytest.mark.parametrize("bad", ["", "AB", "no spaces here", "x", "-leading",
                                 "UPPERCASE", "a" * 65])
def test_an_invalid_scenario_id_is_reprompted(policy, bad):
    lines = [bad, "ok-after-retry", "", "", BRENT, INCREASE, "30", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "the identifier must match" in prompts
    assert request.scenario.scenario_id == "ok-after-retry"


@pytest.mark.parametrize("bad", ["2026-13-01x", "06-09-2026", "2026/09/06", "today",
                                 "2026-9-6"])
def test_an_invalid_scenario_date_is_reprompted(policy, bad):
    lines = ["date-retry-case", "", bad, "2026-09-06", BRENT, INCREASE, "30", PERCENT,
             "n", DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "YYYY-MM-DD" in prompts
    assert request.scenario.scenario_date == "2026-09-06"


@pytest.mark.parametrize("bad", ["ten", "0x1e", "1_000", ".5", "1.", "+10", "017",
                                 "1e", "", "inf", "nan", "-5"])
def test_an_invalid_magnitude_is_reprompted(policy, bad):
    lines = ["magnitude-retry-case", "", "", BRENT, INCREASE, bad, "30", PERCENT, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "as JSON would accept it" in prompts or "non-negative" in prompts
    assert request.scenario.shocks[0].magnitude == Decimal(30)


def test_the_interactive_grammar_matches_the_contract_grammar():
    """Pin the restated grammar to the contract's own, so drift fails here."""
    assert (interactive_module.MAGNITUDE_GRAMMAR.pattern
            == contract_module._STRICT_DECIMAL.pattern)


@pytest.mark.parametrize("bad", ["maybe", "yeah", "1", "", "true"])
def test_an_invalid_yes_no_answer_is_reprompted(policy, bad):
    lines = ["yesno-retry-case", "", "", BRENT, INCREASE, "30", PERCENT, bad, "n",
             DIRECT, JSON_FORMAT, TERMINAL, "y"]
    request, prompts = session(lines, policy=policy)
    assert "answer y or n" in prompts
    assert len(request.scenario.shocks) == 1


def test_the_optional_name_and_date_can_be_omitted(policy):
    request, _ = session(script(name="", date=""), policy=policy)
    assert request.scenario.scenario_name is None
    assert request.scenario.scenario_date is None


def test_the_scenario_date_is_never_filled_in_automatically(policy):
    """An omitted date stays omitted. Today's date is a claim nobody made."""
    request, prompts = session(script(date=""), policy=policy)
    assert request.scenario.scenario_date is None
    assert "(omitted)" in prompts


def test_a_thai_scenario_name_survives_unchanged(policy):
    name = "สถานการณ์ราคาน้ำมันดิบเบรนต์ +30%"
    request, _ = session(script(name=name), policy=policy)
    assert request.scenario.scenario_name == name


# ---------------------------------------------------------------------------
# 19-21. Cancellation, interruption and output safety
# ---------------------------------------------------------------------------


def test_refusing_at_the_confirmation_computes_nothing(policy, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_artifact_bundle", lambda *a, **k: pytest.fail(
        "a refused confirmation must not load an exposure artifact"))
    target = tmp_path / "never.json"
    reason, prompts = cancelled(
        script(destination=NEW_FILE, path=str(target), confirm="n"), policy=policy)
    assert "not confirmed" in str(reason)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("answer", ["q", "quit", "Q", "QUIT"])
def test_quit_cancels_at_any_prompt(policy, answer):
    reason, _ = cancelled(["cancel-case", "", "", answer], policy=policy)
    assert isinstance(reason, InteractiveCancelled)


def test_end_of_input_cancels_cleanly(policy):
    reason, _ = cancelled(["truncated-case", ""], policy=policy)
    assert "input ended" in str(reason)


def test_the_command_maps_cancellation_to_its_own_exit_code(tmp_path, capsys):
    stdin = io.StringIO("cancel-code-case\n\n\n1\n1\n30\n1\nn\n1\n1\n1\nn\n")
    stderr = io.StringIO()
    stdout = BinaryStream()
    arguments = cli._build_parser().parse_args(["interactive"])
    with pytest.raises(InteractiveCancelled):
        cli._interactive(arguments, stdout, stdin=stdin, stderr=stderr)
    assert stdout.buffer.getvalue() == b""


def test_main_returns_the_cancellation_exit_code(monkeypatch, capsys):
    answers = "".join(f"{line}\n" for line in script(scenario_id="cancel-main-case",
                                                     confirm="n"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(answers))
    code = cli.main(["interactive"])
    assert code == cli.EXIT_CANCELLED == 8
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cancelled" in captured.err
    assert "Traceback" not in captured.err


def test_the_cancellation_code_is_not_a_success_and_not_an_existing_code():
    assert cli.EXIT_CANCELLED not in {
        cli.EXIT_OK, cli.EXIT_INTERNAL, cli.EXIT_USAGE, cli.EXIT_CONTRACT,
        cli.EXIT_ARTIFACT, cli.EXIT_UNSUPPORTED_CHANNEL, cli.EXIT_NO_SCORABLE_PAIRS,
        cli.EXIT_OUTPUT_EXISTS,
    }


def test_ctrl_c_ends_without_a_traceback(monkeypatch, capsys, tmp_path):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "collect_request", interrupt)
    code = cli.main(["interactive"])
    captured = capsys.readouterr()
    assert code == cli.EXIT_INTERRUPTED == 130
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "cancelled" in captured.err
    assert list(tmp_path.iterdir()) == []


def test_ctrl_c_still_propagates_for_the_file_based_commands(monkeypatch):
    """Unchanged v1.2.1 behaviour: elsewhere an interrupt is not an answer."""
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run", interrupt)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["run", "--input", "x.yaml", "--basis", "direct", "--format", "json",
                  "--output", "-"])


def test_an_existing_output_path_returns_the_documented_refusal(tmp_path, monkeypatch,
                                                                capsys):
    target = tmp_path / "taken.json"
    target.write_bytes(b"original bytes\n")
    before = target.read_bytes()
    before_mtime = target.stat().st_mtime_ns

    monkeypatch.setattr(sys, "stdin", io.StringIO(
        "".join(f"{line}\n" for line in
                script(destination=NEW_FILE, path=str(target)))))
    code = cli.main(["interactive"])
    assert code == cli.EXIT_OUTPUT_EXISTS == 7
    assert target.read_bytes() == before
    assert target.stat().st_mtime_ns == before_mtime
    assert "already exists" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 22-28. Streams, bytes, determinism and equivalence
# ---------------------------------------------------------------------------


def test_prompts_never_appear_on_stdout(tmp_path):
    code, out, err = drive(script())
    assert code == cli.EXIT_OK
    text = out.decode("utf-8")
    for fragment in ("Scenario ID:", "Select commodity", "Review", "Choice:",
                     "Run this scenario?", "เลือกสินค้า"):
        assert fragment not in text, fragment
        assert fragment in err, fragment


def test_the_interactive_report_contains_no_cr_bytes():
    code, out, _ = drive(script())
    assert code == cli.EXIT_OK
    assert out.count(b"\r") == 0
    assert b"\r\n" not in out
    assert out.endswith(b"\n") and not out.endswith(b"\n\n")
    out.decode("utf-8")


def test_interactive_stdout_bytes_equal_interactive_file_bytes(tmp_path):
    target = tmp_path / "from-file-destination.json"
    stdout_code, stdout_bytes, _ = drive(script())
    file_code, file_stdout, _ = drive(script(destination=NEW_FILE, path=str(target)))
    assert stdout_code == file_code == cli.EXIT_OK
    assert file_stdout == b"", "a file destination writes nothing to stdout"
    assert stdout_bytes == target.read_bytes()


def test_interactive_results_are_deterministic():
    first_code, first, _ = drive(script())
    second_code, second, _ = drive(script())
    assert first_code == second_code == cli.EXIT_OK
    assert first == second


@pytest.mark.parametrize(("basis_choice", "basis"), [(DIRECT, "direct"),
                                                     (TOTAL_REQUIREMENT, "total_requirement")])
@pytest.mark.parametrize(("format_choice", "fmt"), [(JSON_FORMAT, "json"),
                                                    (MARKDOWN_FORMAT, "markdown")])
def test_an_interactive_result_matches_the_equivalent_file_based_run(
        tmp_path, basis_choice, basis, format_choice, fmt):
    """The whole architectural claim, checked as bytes rather than asserted in prose."""
    document = tmp_path / "equivalent.yaml"
    document.write_text(
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: equivalence-case\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        "    direction: increase\n"
        "    magnitude: 30\n"
        "    magnitude_unit: percent\n",
        encoding="utf-8", newline="\n")

    code, interactive_bytes, _ = drive(script(
        scenario_id="equivalence-case", basis=basis_choice, output_format=format_choice))
    assert code == cli.EXIT_OK

    stdout = BinaryStream()
    arguments = cli._build_parser().parse_args(
        ["run", "--input", str(document), "--basis", basis, "--format", fmt, "--output", "-"])
    assert cli._run(arguments, stdout) == cli.EXIT_OK
    assert interactive_bytes == stdout.buffer.getvalue()


def test_no_file_named_dash_is_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, _ = drive(script())
    assert code == cli.EXIT_OK
    assert not (tmp_path / "-").exists()
    assert list(tmp_path.iterdir()) == []
    assert out


def test_no_temporary_scenario_document_is_created(tmp_path, monkeypatch, policy):
    """The mapping goes straight to the validator; nothing is serialised on the way."""
    monkeypatch.chdir(tmp_path)
    opened: list[str] = []
    real_open = io.open

    def watch(file, *args, **kwargs):
        mode = kwargs.get("mode", args[0] if args else "r")
        if any(flag in str(mode) for flag in ("w", "x", "a", "+")):
            opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(io, "open", watch)
    session(script(), policy=policy)
    assert opened == []
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 29-30 and the structural guards
# ---------------------------------------------------------------------------


STDLIB_ONLY = {"re", "io", "sys", "dataclasses", "decimal", "typing", "__future__"}


def test_the_interactive_module_imports_no_third_party_package():
    tree = ast.parse(INTERACTIVE_SOURCE.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert roots <= STDLIB_ONLY | {"thai_supply_chain_ews"}, sorted(roots)


def test_no_python_313_only_api_is_used():
    """``Path.read_text(newline=...)`` is 3.13+; CI runs 3.12. Guard both new sources."""
    for source in (INTERACTIVE_SOURCE, CLI_SOURCE):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"read_text", "write_text"}):
                keywords = {k.arg for k in node.keywords}
                assert "newline" not in keywords, f"{source.name}: {node.func.attr}(newline=)"


def test_prompts_cannot_reach_stdout():
    """Structural guard, read from the syntax tree rather than from prose.

    Every assertion here walks the AST, so the module's own docstring — which says it
    reconfigures no stream — cannot be what makes the check pass.
    """
    tree = ast.parse(INTERACTIVE_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in {"stdout", "stderr", "stdin"}:
                assert not (isinstance(node.value, ast.Name) and node.value.id == "sys"), (
                    "the prompting module must not reach for a global stream")
            assert node.attr != "reconfigure", "no stream may be reconfigured"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"print", "input"}, node.func.id
        # No assignment to a `sys.<stream>` attribute anywhere in the module.
        targets = (list(node.targets) if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AugAssign) else [])
        for target in targets:
            assert not (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "sys"), "no global stream reassignment"


def test_interactive_output_still_reaches_the_controlled_byte_writer():
    """The interactive path must not grow a second way out of the process."""
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}

    emit_calls = [node for node in ast.walk(functions["execute_run"])
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                  and node.func.id == "_emit"]
    assert emit_calls, "execute_run must emit through _emit"

    interactive = functions["_interactive"]
    called = {node.func.id for node in ast.walk(interactive)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "execute_run" in called, "interactive must reuse the shared run path"
    assert "_resolve_output" in called, "interactive must reuse the output-safety check"
    for forbidden in ("_write_stdout", "print", "open"):
        assert forbidden not in called, forbidden

    run_body = functions["_run"]
    run_called = {node.func.id for node in ast.walk(run_body)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "execute_run" in run_called, "run and interactive must share one path"


# ---------------------------------------------------------------------------
# The real subprocess: bytes, end to end
# ---------------------------------------------------------------------------


def raw_interactive(answers, *extra):
    """Run the module for real and return undecoded bytes. No newline decoding."""
    import os

    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.Popen(
        [sys.executable, "-m", "thai_supply_chain_ews.scenario", "interactive", *extra],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=False, cwd=str(ROOT), env=environment,
    )
    payload = "".join(f"{line}\n" for line in answers).encode("utf-8")
    out, err = process.communicate(payload)
    return process.returncode, out, err


def test_a_real_subprocess_session_emits_pure_utf8_lf_document_bytes():
    code, out, err = raw_interactive(script(scenario_id="subprocess-case"))
    assert code == 0, err.decode("utf-8", "replace")
    assert out.count(b"\r") == 0
    assert b"\r\n" not in out
    assert out.endswith(b"\n") and not out.endswith(b"\n\n")
    document = json.loads(out.decode("utf-8"))
    assert document["scenario"]["scenario_id"] == "subprocess-case"
    assert b"Select commodity" in err
    assert b"Select commodity" not in out


def test_a_real_subprocess_session_matches_the_file_based_command(tmp_path):
    document = tmp_path / "subprocess-equivalent.yaml"
    document.write_text(
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: subprocess-equivalence\n"
        "shocks:\n"
        "  - channel: brent_crude_usd_bbl\n"
        "    direction: increase\n"
        "    magnitude: 30\n"
        "    magnitude_unit: percent\n",
        encoding="utf-8", newline="\n")
    code, interactive_bytes, err = raw_interactive(
        script(scenario_id="subprocess-equivalence", output_format=MARKDOWN_FORMAT))
    assert code == 0, err.decode("utf-8", "replace")

    import os

    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.Popen(
        [sys.executable, "-m", "thai_supply_chain_ews.scenario", "run",
         "--input", str(document), "--basis", "direct", "--format", "markdown",
         "--output", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False,
        cwd=str(ROOT), env=environment,
    )
    file_bytes, file_err = process.communicate()
    assert process.returncode == 0, file_err.decode("utf-8", "replace")
    assert interactive_bytes == file_bytes


def test_a_real_subprocess_cancellation_returns_the_cancellation_code():
    code, out, err = raw_interactive(script(confirm="n"))
    assert code == cli.EXIT_CANCELLED
    assert out == b""
    assert b"Traceback" not in err
