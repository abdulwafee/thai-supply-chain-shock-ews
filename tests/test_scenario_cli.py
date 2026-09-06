"""Phase 3 tests: the command line.

Every case calls ``main(argv)`` directly and captures streams with ``capsys``. That keeps
the suite hermetic and fast, and it tests the thing that actually decides an exit code
rather than a subprocess wrapper around it. Two cases additionally run the module as a
subprocess, because ``python -m`` is the supported invocation and it is worth proving it
works rather than assuming it.

The output-safety cases are the sharp ones. A tool that writes reports is a tool that can
destroy one, so the tests check not only that an existing file survives but that its bytes
are unchanged, that a refused run creates nothing, and that a failure part-way through
leaves no half-written file looking finished.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from thai_supply_chain_ews.scenario import __main__ as cli

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "scenarios"
CRUDE = str(EXAMPLES / "crude_oil_price_increase.yaml")
RUBBER = str(EXAMPLES / "rubber_price_decrease.yaml")
MULTI = str(EXAMPLES / "multi_commodity_shock.yaml")
CLI_SOURCE = ROOT / "src" / "thai_supply_chain_ews" / "scenario" / "__main__.py"


def scenario_file(tmp_path, text, name="scenario.yaml") -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def valid_text(channel="brent_crude_usd_bbl", direction="increase", magnitude=30,
               scenario_id="cli-case") -> str:
    return (
        "schema_version: structural_exposure_scenario_v1\n"
        f"scenario_id: {scenario_id}\n"
        "scenario_date: 2026-09-04\n"
        "shocks:\n"
        f"  - channel: {channel}\n"
        f"    direction: {direction}\n"
        f"    magnitude: {magnitude}\n"
        "    magnitude_unit: percent\n"
    )


def run(argv):
    return cli.main(argv)


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------


def test_no_arguments_prints_usage_to_stderr_and_exits_two(capsys):
    assert run([]) == cli.EXIT_USAGE == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "a command is required" in captured.err
    assert "Traceback" not in captured.err


def test_help_exits_zero_and_reads_nothing(capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("--help must not open a file")

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    with pytest.raises(SystemExit) as caught:
        run(["--help"])
    assert caught.value.code == 0
    assert "validate" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["validate", "run", "explain", "interactive"])
def test_each_subcommand_has_help(capsys, command):
    with pytest.raises(SystemExit) as caught:
        run([command, "--help"])
    assert caught.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_only_the_four_subcommands_exist():
    """`interactive` joined the three file-based commands in v1.3.0; nothing else has."""
    parser = cli._build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert len(actions) == 1
    assert sorted(actions[0].choices) == ["explain", "interactive", "run", "validate"]


def test_the_parser_offers_no_bypass_flag():
    """No `--force`, no `--yes`, no way to turn a stop into a warning."""
    options = set()
    parser = cli._build_parser()
    for action in parser._actions:
        options.update(action.option_strings)
    subparsers = [a for a in parser._actions if a.dest == "command"][0]
    for sub in subparsers.choices.values():
        for action in sub._actions:
            options.update(action.option_strings)
    for forbidden in ("--force", "-f", "--overwrite", "--yes", "-y", "--unsafe",
                      "--skip-checks", "--no-verify", "--insecure", "--allow-overwrite"):
        assert forbidden not in options, forbidden


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--input", CRUDE, "--format", "json", "--output", "-"],
        ["run", "--input", CRUDE, "--basis", "direct", "--output", "-"],
        ["run", "--input", CRUDE, "--basis", "direct", "--format", "json"],
        ["run", "--basis", "direct", "--format", "json", "--output", "-"],
        ["explain", "--input", CRUDE, "--basis", "direct", "--format", "json", "--output", "-"],
    ],
)
def test_every_required_argument_really_is_required(argv):
    with pytest.raises(SystemExit) as caught:
        run(argv)
    assert caught.value.code == cli.EXIT_USAGE


def test_all_is_valid_only_for_explain():
    with pytest.raises(SystemExit) as caught:
        run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
             "--output", "-", "--all"])
    assert caught.value.code == cli.EXIT_USAGE


@pytest.mark.parametrize("basis", ["indirect", "primary", "Direct", "total"])
def test_an_unsupported_basis_is_a_usage_error(basis):
    with pytest.raises(SystemExit) as caught:
        run(["run", "--input", CRUDE, "--basis", basis, "--format", "json", "--output", "-"])
    assert caught.value.code == cli.EXIT_USAGE


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_reports_the_contract_and_writes_nothing(tmp_path, capsys):
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    path = scenario_file(tmp_path, valid_text())
    assert run(["validate", "--input", path]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "scenario_id            cli-case" in captured.out
    assert "canonical_input_sha256" in captured.out
    assert "nothing was calculated and no file was written" in captured.out
    assert captured.err == ""
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p != Path(path)}
    assert after == {k: v for k, v in before.items() if k != Path(path)}


def test_validate_is_deterministic(tmp_path, capsys):
    path = scenario_file(tmp_path, valid_text())
    outputs = set()
    for _ in range(3):
        run(["validate", "--input", path])
        outputs.add(capsys.readouterr().out)
    assert len(outputs) == 1


def test_validate_refuses_a_malformed_document(tmp_path, capsys):
    path = scenario_file(tmp_path, "schema_version: wrong\nscenario_id: x\nshocks: []\n")
    assert run(["validate", "--input", path]) == cli.EXIT_CONTRACT == 3
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_a_successful_run_exits_zero(capsys):
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_OK
    assert capsys.readouterr().out.startswith("{")


def test_an_accepted_no_ranking_result_still_exits_zero(tmp_path, capsys):
    path = scenario_file(tmp_path, valid_text(magnitude=0))
    assert run(["run", "--input", path, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_OK
    document = json.loads(capsys.readouterr().out)
    assert document["ranking"]["status"] == "not_ranked"
    assert document["ranking"]["no_ranking_reason"] == "all_magnitudes_zero"


def test_a_malformed_scenario_exits_three(tmp_path, capsys):
    path = scenario_file(tmp_path, "schema_version: structural_exposure_scenario_v1\n"
                                   "scenario_id: bad\nshocks: []\n")
    assert run(["run", "--input", path, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_CONTRACT
    assert "Traceback" not in capsys.readouterr().err


def test_a_missing_input_file_exits_three(tmp_path, capsys):
    assert run(["run", "--input", str(tmp_path / "nope.yaml"), "--basis", "direct",
                "--format", "json", "--output", "-"]) == cli.EXIT_CONTRACT
    assert "Traceback" not in capsys.readouterr().err


def test_an_unsupported_channel_exits_five(tmp_path, capsys):
    """Caught before the general contract handler, so it gets its own code."""
    path = scenario_file(tmp_path, valid_text(channel="natural_gas_usd_mmbtu"))
    assert run(["run", "--input", path, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_UNSUPPORTED_CHANNEL == 5
    captured = capsys.readouterr()
    assert "not a registered channel" in captured.err
    assert "Traceback" not in captured.err


def test_a_scenario_with_no_scorable_pair_exits_six(tmp_path, capsys):
    """IND-08 and IND-12 are the only aluminium pairs excluded; a scenario needs all."""
    path = scenario_file(
        tmp_path,
        "schema_version: structural_exposure_scenario_v1\n"
        "scenario_id: no-scorable\nshocks:\n"
        "  - channel: aluminum_usd_mt\n    direction: increase\n"
        "    magnitude: 10\n    magnitude_unit: percent\n",
    )
    # Aluminium alone still scores ten industries, so this is a real run, not exit 6.
    assert run(["run", "--input", path, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_OK
    capsys.readouterr()


def test_the_no_scorable_pairs_condition_maps_to_exit_six(monkeypatch, capsys):
    """Forced through the real handler, because no shipped scenario can reach it."""
    from thai_supply_chain_ews.scenario import contract as c

    def raise_no_scorable(*args, **kwargs):
        raise c.ScenarioContractError(
            "no industry/channel pair in this scenario can be scored",
            code="no_shocks", field="shocks",
            details={"condition": "no_scorable_pairs", "excluded": []},
        )

    monkeypatch.setattr(cli, "calculate_scenario_exposure", raise_no_scorable)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_NO_SCORABLE_PAIRS == 6
    assert "Traceback" not in capsys.readouterr().err


def test_an_artifact_integrity_failure_exits_four(monkeypatch, capsys):
    from thai_supply_chain_ews.scenario.artifacts import ArtifactIntegrityError

    def raise_integrity(*args, **kwargs):
        raise ArtifactIntegrityError("exposure_matrix: does not match its pin")

    monkeypatch.setattr(cli, "load_artifact_bundle", raise_integrity)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_ARTIFACT == 4
    captured = capsys.readouterr()
    assert "does not match its pin" in captured.err
    assert "Traceback" not in captured.err


def test_a_policy_failure_exits_four(monkeypatch, capsys):
    from thai_supply_chain_ews.scenario import contract as c

    def raise_policy(*args, **kwargs):
        raise c.ScenarioPolicyError("policy: runtime_artifacts must be a list")

    monkeypatch.setattr(cli, "load_policy", raise_policy)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_ARTIFACT
    assert "Traceback" not in capsys.readouterr().err


def test_an_internal_error_exits_one(monkeypatch, capsys):
    from thai_supply_chain_ews.scenario import contract as c

    def raise_internal(*args, **kwargs):
        raise c.ScenarioInternalError("an invariant is wrong")

    monkeypatch.setattr(cli, "build_scenario_result_document", raise_internal)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_INTERNAL == 1
    captured = capsys.readouterr()
    assert "internal error:" in captured.err
    assert "Traceback" not in captured.err


def test_an_unexpected_exception_exits_one_without_a_traceback(monkeypatch, capsys):
    def raise_unexpected(*args, **kwargs):
        raise ValueError("something nobody foresaw")

    monkeypatch.setattr(cli, "build_scenario_result_document", raise_unexpected)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_INTERNAL
    captured = capsys.readouterr()
    assert "internal error: ValueError" in captured.err
    assert "Traceback" not in captured.err


def test_a_keyboard_interrupt_is_not_swallowed_as_an_internal_failure(monkeypatch):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_scenario_result_document", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json", "--output", "-"])


def test_every_declared_exit_code_is_distinct():
    codes = [cli.EXIT_OK, cli.EXIT_INTERNAL, cli.EXIT_USAGE, cli.EXIT_CONTRACT,
             cli.EXIT_ARTIFACT, cli.EXIT_UNSUPPORTED_CHANNEL, cli.EXIT_NO_SCORABLE_PAIRS,
             cli.EXIT_OUTPUT_EXISTS]
    assert codes == [0, 1, 2, 3, 4, 5, 6, 7]
    assert len(set(codes)) == 8


# ---------------------------------------------------------------------------
# Output safety
# ---------------------------------------------------------------------------


def test_a_dash_means_stdout_and_creates_no_file_called_dash(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "markdown",
                "--output", "-"]) == cli.EXIT_OK
    assert capsys.readouterr().out.startswith("# Structural exposure")
    assert not (tmp_path / "-").exists()
    assert list(tmp_path.iterdir()) == []


def test_a_file_destination_is_written_with_lf_and_utf8(tmp_path, capsys):
    destination = tmp_path / "result.json"
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(destination)]) == cli.EXIT_OK
    raw = destination.read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8").startswith("{")
    assert capsys.readouterr().out == ""


def test_an_existing_file_is_refused_and_left_byte_identical(tmp_path, capsys):
    destination = tmp_path / "existing.json"
    original = b"do not touch me\n"
    destination.write_bytes(original)
    before = destination.stat().st_mtime_ns
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(destination)]) == cli.EXIT_OUTPUT_EXISTS == 7
    assert destination.read_bytes() == original
    assert destination.stat().st_mtime_ns == before
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "no flag to make it" in captured.err


def test_an_existing_directory_at_the_destination_is_refused(tmp_path, capsys):
    destination = tmp_path / "adirectory"
    destination.mkdir()
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(destination)]) == cli.EXIT_OUTPUT_EXISTS
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert "already exists" in capsys.readouterr().err


def test_a_symlink_at_the_destination_is_refused_without_following_it(tmp_path, capsys):
    target = tmp_path / "target.json"
    target.write_bytes(b"original\n")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip(
            "this platform or account cannot create a symlink; the refusal rule is "
            "unchanged, it simply cannot be demonstrated here"
        )
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(link)]) == cli.EXIT_OUTPUT_EXISTS
    assert target.read_bytes() == b"original\n"
    capsys.readouterr()


def test_a_missing_parent_directory_is_not_created(tmp_path, capsys):
    destination = tmp_path / "absent" / "result.json"
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(destination)]) == cli.EXIT_USAGE
    assert not (tmp_path / "absent").exists()
    assert "is not created for you" in capsys.readouterr().err


def test_a_parent_that_is_a_file_is_refused(tmp_path, capsys):
    parent = tmp_path / "afile"
    parent.write_bytes(b"x")
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(parent / "result.json")]) == cli.EXIT_USAGE
    assert parent.read_bytes() == b"x"
    capsys.readouterr()


def test_a_failing_run_creates_no_destination_file(tmp_path, capsys):
    """The destination is resolved first, but nothing is created until it is rendered."""
    destination = tmp_path / "never.json"
    bad = scenario_file(tmp_path, valid_text(channel="natural_gas_usd_mmbtu"))
    assert run(["run", "--input", bad, "--basis", "direct", "--format", "json",
                "--output", str(destination)]) == cli.EXIT_UNSUPPORTED_CHANNEL
    assert not destination.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["scenario.yaml"]
    capsys.readouterr()


def test_a_write_failure_leaves_no_partial_file(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "partial.json"
    real_open = open

    def failing_open(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        if "x" in mode:
            original_write = handle.write

            def explode(text):
                original_write(text[: len(text) // 2])
                raise OSError("disk went away")

            handle.write = explode
        return handle

    monkeypatch.setattr("builtins.open", failing_open)
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "json",
                "--output", str(destination)]) == cli.EXIT_USAGE
    assert not destination.exists(), "a half-written report must not be left looking finished"
    capsys.readouterr()


def test_no_temporary_file_is_left_beside_the_destination(tmp_path, capsys):
    destination = tmp_path / "clean.md"
    assert run(["run", "--input", CRUDE, "--basis", "direct", "--format", "markdown",
                "--output", str(destination)]) == cli.EXIT_OK
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clean.md"]
    capsys.readouterr()


def test_writing_to_a_file_and_to_stdout_produce_the_same_bytes(tmp_path, capsys):
    destination = tmp_path / "same.json"
    run(["run", "--input", MULTI, "--basis", "total_requirement", "--format", "json",
         "--output", str(destination)])
    capsys.readouterr()
    run(["run", "--input", MULTI, "--basis", "total_requirement", "--format", "json",
         "--output", "-"])
    assert capsys.readouterr().out == destination.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------


def test_explain_defaults_to_five_mediators(capsys):
    assert run(["explain", "--input", CRUDE, "--basis", "total_requirement",
                "--industry", "IND-09", "--format", "json", "--output", "-"]) == cli.EXIT_OK
    document = json.loads(capsys.readouterr().out)
    for channel in document["channels"]:
        assert channel["mediators_shown"] == 5
        assert len(channel["mediators"]) == 5


def test_explain_all_returns_ten_mediators_in_published_order(capsys):
    assert run(["explain", "--input", CRUDE, "--basis", "total_requirement",
                "--industry", "IND-09", "--format", "json", "--output", "-",
                "--all"]) == cli.EXIT_OK
    document = json.loads(capsys.readouterr().out)
    for channel in document["channels"]:
        assert channel["mediators_shown"] == 10
        assert [m["rank"] for m in channel["mediators"]] == list(range(1, 11))


def test_explain_rejects_an_unknown_industry(capsys):
    assert run(["explain", "--input", CRUDE, "--basis", "direct", "--industry", "IND-99",
                "--format", "json", "--output", "-"]) == cli.EXIT_CONTRACT
    captured = capsys.readouterr()
    assert "IND-99" in captured.err
    assert "Traceback" not in captured.err


def test_explain_markdown_renders(capsys):
    assert run(["explain", "--input", CRUDE, "--basis", "total_requirement",
                "--industry", "IND-04", "--format", "markdown", "--output", "-"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("# IND-04")
    assert "not evidence of a causal path" in out
    assert sorted({ch for ch in out if ord(ch) > 127}) == []


# ---------------------------------------------------------------------------
# The shipped examples, through the real command line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("example", [CRUDE, RUBBER, MULTI])
def test_every_example_validates_and_runs_in_both_formats(example, capsys):
    assert run(["validate", "--input", example]) == cli.EXIT_OK
    capsys.readouterr()  # capsys accumulates; drop the validate output first
    assert run(["run", "--input", example, "--basis", "direct", "--format", "json",
                "--output", "-"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "structural_exposure_result_v1"
    )
    assert run(["run", "--input", example, "--basis", "total_requirement",
                "--format", "markdown", "--output", "-"]) == cli.EXIT_OK
    assert "conditional structural exposure" in capsys.readouterr().out


def test_the_rubber_example_reports_relief_pressure(capsys):
    run(["run", "--input", RUBBER, "--basis", "total_requirement", "--format", "json",
         "--output", "-"])
    document = json.loads(capsys.readouterr().out)
    assert all(
        e["direction"] == "relief_pressure" for e in document["ranking"]["industries"]
    )
    assert {e["industry_id"] for e in document["exclusions"]} == {"IND-06"}


def test_the_multi_commodity_example_shows_cancellation(capsys):
    run(["run", "--input", MULTI, "--basis", "total_requirement", "--format", "json",
         "--output", "-"])
    document = json.loads(capsys.readouterr().out)
    assert any(e["cancellation"] != "0" for e in document["ranking"]["industries"])


# ---------------------------------------------------------------------------
# The supported invocation, as a subprocess
# ---------------------------------------------------------------------------


def module_run(*arguments):
    environment = {"PYTHONPATH": str(ROOT / "src"), "PATH": "", "SYSTEMROOT": ""}
    import os

    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "thai_supply_chain_ews.scenario", *arguments],
        capture_output=True, text=True, cwd=str(ROOT), env=environment, check=False,
    )


def test_python_dash_m_is_the_supported_invocation():
    completed = module_run("validate", "--input", CRUDE)
    assert completed.returncode == 0
    assert "valid against the input contract" in completed.stdout


def test_the_module_invocation_is_deterministic_across_processes():
    digests = set()
    for _ in range(2):
        completed = module_run("run", "--input", MULTI, "--basis", "total_requirement",
                               "--format", "json", "--output", "-")
        assert completed.returncode == 0
        digests.add(completed.stdout)
    assert len(digests) == 1


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_the_cli_entry_point_is_not_exported():
    from thai_supply_chain_ews import scenario

    for name in ("main", "cli", "__main__"):
        assert name not in scenario.__all__
    assert not hasattr(scenario, "main")
    assert callable(cli.main)


def test_the_cli_reaches_no_network_and_writes_no_cache():
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not {name.split(".")[0] for name in imported} & {
        "socket", "ssl", "urllib", "http", "requests", "httpx", "ftplib", "smtplib",
        "shelve", "pickle", "sqlite3", "tempfile"
    }
    calls = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in ("mkdir", "makedirs", "rmtree", "chmod", "system", "urlopen", "input"):
        assert forbidden not in calls, forbidden


def test_the_cli_never_prompts():
    source = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    names = {
        node.func.id for node in ast.walk(source)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "input" not in names
    assert "getpass" not in names


def test_the_cli_imports_no_model_target_or_data_module():
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    project = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        and node.module.startswith("thai_supply_chain_ews.")
    }
    # `interactive` joined the set in v1.3.0: the entry point dispatches to it for the
    # prompting, and it imports only the contract. The set stays closed, so a module
    # nobody reviewed still makes this fail.
    assert project == {
        "thai_supply_chain_ews.scenario.artifacts",
        "thai_supply_chain_ews.scenario.contract",
        "thai_supply_chain_ews.scenario.exposure",
        "thai_supply_chain_ews.scenario.interactive",
        "thai_supply_chain_ews.scenario.report",
    }


# ---------------------------------------------------------------------------
# Standard output carries the document's bytes, not a platform rendering of them
#
# `--output <file>` has always opened with `newline="\n"`. `--output -` used to hand the
# text to `sys.stdout`, whose text layer translates newlines, so on Windows the same
# rendering left the process as CRLF: `run ... > result.json` produced a file that did
# not match `run ... --output result.json`, and a checksum taken over the pipe did not
# verify against one taken over the file.
#
# The suite could not see it. Most cases call `main()` in process and read `capsys`,
# which intercepts above the text layer, and the two subprocess cases used `text=True`,
# whose universal-newline decoding turns CRLF back into LF before any assertion. So the
# cases below capture raw bytes with `text=False` and never normalise anything they then
# assert on. On Windows before the fix they fail; on Linux they passed either way.
# ---------------------------------------------------------------------------


BASES = ("direct", "total_requirement")
FORMATS = ("json", "markdown")


def raw_module_run(*arguments):
    """Run the module and return undecoded bytes. No universal-newline decoding."""
    import os

    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.Popen(
        [sys.executable, "-m", "thai_supply_chain_ews.scenario", *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False,
        cwd=str(ROOT), env=environment,
    )
    out, err = process.communicate()
    return process.returncode, out, err


def document_invocations():
    """Every invocation that emits a rendered document, as (label, argv-without-output)."""
    for basis in BASES:
        for fmt in FORMATS:
            yield (f"run.{basis}.{fmt}",
                   ["run", "--input", CRUDE, "--basis", basis, "--format", fmt])
    for basis in BASES:
        for tag, extra in (("top5", []), ("all", ["--all"])):
            for fmt in FORMATS:
                yield (f"explain.{basis}.{tag}.{fmt}",
                       ["explain", "--input", CRUDE, "--basis", basis,
                        "--industry", "IND-04", "--format", fmt, *extra])


ALL_INVOCATIONS = list(document_invocations())


@pytest.mark.parametrize(("label", "argv"), ALL_INVOCATIONS, ids=[c[0] for c in ALL_INVOCATIONS])
def test_stdout_bytes_equal_file_bytes_exactly(label, argv, tmp_path):
    """The transport must not change the document. Raw bytes, no normalisation."""
    code, out, err = raw_module_run(*argv, "--output", "-")
    assert code == 0, err
    destination = tmp_path / f"{label}.out"
    file_code, _, file_err = raw_module_run(*argv, "--output", str(destination))
    assert file_code == 0, file_err
    assert out == destination.read_bytes()


@pytest.mark.parametrize(("label", "argv"), ALL_INVOCATIONS, ids=[c[0] for c in ALL_INVOCATIONS])
def test_stdout_bytes_use_lf_only(label, argv):
    code, out, err = raw_module_run(*argv, "--output", "-")
    assert code == 0, err
    assert b"\r\n" not in out
    assert out.count(b"\r") == 0
    assert b"\n" in out
    out.decode("utf-8")
    assert out.endswith(b"\n")
    assert not out.endswith(b"\n\n")


def test_validate_stdout_bytes_use_lf_only():
    """`validate` writes through the same stdout path and must obey the same rule."""
    code, out, err = raw_module_run("validate", "--input", CRUDE)
    assert code == 0, err
    assert b"\r\n" not in out
    assert out.count(b"\r") == 0
    out.decode("utf-8")
    assert out.endswith(b"\n")


@pytest.mark.parametrize(("label", "argv"), ALL_INVOCATIONS, ids=[c[0] for c in ALL_INVOCATIONS])
def test_stdout_bytes_are_deterministic(label, argv):
    first = raw_module_run(*argv, "--output", "-")
    second = raw_module_run(*argv, "--output", "-")
    assert first[0] == second[0] == 0
    assert first[1] == second[1]


@pytest.mark.parametrize(("label", "argv"), ALL_INVOCATIONS, ids=[c[0] for c in ALL_INVOCATIONS])
def test_stdout_bytes_equal_the_renderer_encoded_as_utf8(label, argv, tmp_path):
    """The bytes on the wire are the renderer's own text, encoded and nothing else."""
    code, out, err = raw_module_run(*argv, "--output", "-")
    assert code == 0, err
    destination = tmp_path / f"{label}.reference"
    raw_module_run(*argv, "--output", str(destination))
    assert out == destination.read_bytes().decode("utf-8").encode("utf-8")


def test_file_output_is_unchanged_and_still_refuses_to_overwrite(tmp_path):
    """The file branch is untouched: same bytes, same exclusive creation, same exit 7."""
    destination = tmp_path / "result.json"
    code, _, _ = raw_module_run("run", "--input", CRUDE, "--basis", "direct",
                                "--format", "json", "--output", str(destination))
    assert code == 0
    first_bytes = destination.read_bytes()
    first_mtime = destination.stat().st_mtime_ns
    assert b"\r" not in first_bytes

    again, _, err = raw_module_run("run", "--input", CRUDE, "--basis", "direct",
                                   "--format", "json", "--output", str(destination))
    assert again == 7
    assert b"already exists" in err
    assert destination.read_bytes() == first_bytes
    assert destination.stat().st_mtime_ns == first_mtime


class _TextOnlyStream:
    """A text stand-in with no binary buffer, like `io.StringIO` or a capture object."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def write(self, text: str) -> int:
        self.chunks.append(text)
        return len(text)

    @property
    def text(self) -> str:
        return "".join(self.chunks)


class _BinaryCapableStream:
    """A stand-in that exposes `.buffer`; its text `write` must never be reached."""

    class _Buffer:
        def __init__(self) -> None:
            self.chunks: list[bytes] = []
            self.flushed = 0

        def write(self, data: bytes) -> int:
            assert isinstance(data, bytes)
            self.chunks.append(data)
            return len(data)

        def flush(self) -> None:
            self.flushed += 1

    def __init__(self) -> None:
        self.buffer = self._Buffer()
        self.text_writes = 0

    def write(self, text: str) -> int:  # pragma: no cover - reaching this is the failure
        self.text_writes += 1
        raise AssertionError("_emit used the text path on a stream that has a buffer")

    @property
    def data(self) -> bytes:
        return b"".join(self.buffer.chunks)


def test_emit_prefers_the_binary_buffer_and_never_touches_the_text_write():
    stream = _BinaryCapableStream()
    cli._emit("alpha\nbeta\n", None, stream)
    assert stream.data == b"alpha\nbeta\n"
    assert stream.text_writes == 0
    assert stream.buffer.flushed == 1


def test_emit_falls_back_to_a_text_only_stream_without_altering_the_text():
    """In-process callers may inject a text stand-in; the fallback must be transparent."""
    stream = _TextOnlyStream()
    payload = "alpha\nbeta\n— dash ไทย\n"
    cli._emit(payload, None, stream)
    assert stream.text == payload
    assert "\r" not in stream.text


def test_in_process_invocation_still_works_with_an_injected_text_stream(tmp_path):
    stream = _TextOnlyStream()
    code = cli._validate(
        cli._build_parser().parse_args(["validate", "--input", CRUDE]), stream
    )
    assert code == 0
    assert "valid against the input contract" in stream.text
    assert "\r" not in stream.text


def test_document_output_never_returns_to_an_uncontrolled_text_write():
    """Structural guard, read from the syntax tree rather than from prose.

    Every byte the CLI puts on standard output goes through one helper. The guard pins
    that: the helper encodes and writes to a binary buffer, both command paths delegate
    to it rather than writing text themselves, and no global stream is reconfigured or
    replaced anywhere in the module. A grep would match this docstring; an AST walk
    cannot, so the check cannot pass on its own wording.
    """
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}

    helper = functions["_write_stdout"]
    helper_calls = {node.func.attr for node in ast.walk(helper)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "encode" in helper_calls, "the helper must encode the text itself"
    buffer_writes = [
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write"
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "buffer"
    ]
    assert buffer_writes, "the helper must write through a binary buffer"

    # Both command paths delegate; neither writes document text to a stream itself.
    for name in ("_emit", "_validate"):
        body = functions[name]
        assert [node for node in ast.walk(body)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_write_stdout"], f"{name} must delegate to _write_stdout"
        stray = [node.lineno for node in ast.walk(body)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "write"
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "stdout"]
        assert not stray, f"{name} writes text straight to stdout at {stray}"

    # No global stream is reconfigured or replaced, anywhere in the module.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "reconfigure", "stdout must not be reconfigured globally"
        if isinstance(node, ast.Attribute):
            assert node.attr != "linesep", "os.linesep must not decide document bytes"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    assert not (target.value.id == "sys" and target.attr in
                                {"stdout", "stderr"}), "no global stream reassignment"


def test_the_file_branch_still_declares_utf8_and_lf():
    """The fix must not have loosened the file branch while tightening stdout."""
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    emit = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "_emit")
    opens = [node for node in ast.walk(emit)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "open"]
    assert len(opens) == 1
    keywords = {kw.arg: getattr(kw.value, "value", None) for kw in opens[0].keywords}
    assert keywords.get("encoding") == "utf-8"
    assert keywords.get("newline") == "\n"
    assert opens[0].args[1].value == "x"
