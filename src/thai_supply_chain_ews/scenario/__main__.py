"""The command line: four subcommands, no defaults, no way to skip a check.

``python -m thai_supply_chain_ews.scenario`` — there is deliberately no console-script
entry point, so the package's install contract is unchanged by this feature.

``interactive`` is a way of *writing* a scenario, not a second way of *computing* one: it
asks numbered questions, validates the answers through the same public contract entry
point a file goes through, and then joins the identical scoring, schema-validation,
rendering and output path. For semantically identical input its bytes are the bytes
``run`` would have produced.

Four rules shape the surface, and each of them is a refusal.

**Nothing is chosen for the user.** No default subcommand, no default basis, no default
format, no default output. The basis in particular: the direct matrix is registered as
primary and the total-requirement matrix as a sensitivity view, so a tool that picked
one would be making a governance decision on the reader's behalf, quietly, every time.

**There is no bypass.** No ``--force``, ``--overwrite``, ``--yes``, ``--unsafe`` or
``--skip-checks``. An artifact whose digest does not match is not a prompt to answer, it
is a stop; a flag that turns that into a warning is a flag that will be used.

**An existing output node is never touched.** Not overwritten, not appended to, not
opened for writing at all — the command exits 7 and the file on disk is exactly what it
was. Rendering completes in memory before anything is created, so a failure halfway
through cannot leave a half-written report that looks finished.

**An expected failure is an answer, not a crash.** Every condition this tool can foresee
maps to an exit code and a single line on stderr. A traceback is reserved for the case
where the tool itself is wrong, which is the only case where a stack trace tells the
reader something they can act on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from thai_supply_chain_ews.scenario.artifacts import ArtifactIntegrityError, load_artifact_bundle
from thai_supply_chain_ews.scenario.contract import (
    ScenarioContractError,
    ScenarioInternalError,
    ScenarioPolicyError,
    UnsupportedChannelError,
    load_policy,
    load_scenario_document,
)
from thai_supply_chain_ews.scenario.exposure import SUPPORTED_BASES, calculate_scenario_exposure
from thai_supply_chain_ews.scenario.interactive import InteractiveCancelled, collect_request
from thai_supply_chain_ews.scenario.report import (
    build_industry_explanation_document,
    build_scenario_result_document,
    render_industry_explanation_json,
    render_industry_explanation_markdown,
    render_scenario_result_json,
    render_scenario_result_markdown,
    validate_result_document,
)

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_CONTRACT = 3
EXIT_ARTIFACT = 4
EXIT_UNSUPPORTED_CHANNEL = 5
EXIT_NO_SCORABLE_PAIRS = 6
EXIT_OUTPUT_EXISTS = 7

#: An interactive session the reader stopped: ``q``/``quit``, ``n`` at the confirmation,
#: or end of input. It is deliberately not 0. A cancelled session read no artifact,
#: computed nothing and wrote nothing, and a script that treated that as a completed
#: calculation would be reading a result that does not exist. Codes 0-7 keep their
#: existing meanings for every command, including this one.
EXIT_CANCELLED = 8

#: Ctrl+C during an interactive session. 128 + SIGINT, the conventional shell status for
#: a process ended by an interrupt, so a shell reports it the way it reports any other
#: interrupted command rather than as an application error.
EXIT_INTERRUPTED = 130

STDOUT_TARGET = "-"
DEFAULT_MEDIATORS = 5
ALL_MEDIATORS = 10

#: ``src/thai_supply_chain_ews/scenario/__main__.py`` -> repository root.
#:
#: Resolved from ``__file__`` rather than from ``THAI_SUPPLY_CHAIN_EWS_ROOT``. A command
#: somebody types should not fail until an environment variable is exported, and this
#: mirrors what ``scripts/build_obsidian_vault.py`` already does.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class _OutputError(Exception):
    """A destination cannot be used. Carries the exit code it maps to."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m thai_supply_chain_ews.scenario",
        description=(
            "Rank Thai manufacturing industry groups by structural exposure to a "
            "hypothetical upstream commodity shock, using published 2015 input-output "
            "accounting ratios. Not a probability, not a forecast, not a predicted "
            "percentage change, not a causal effect, not a risk band, and not an "
            "investment or production recommendation."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    validate = subparsers.add_parser(
        "validate",
        help="check a scenario document against the input contract; compute nothing",
        description=(
            "Validate a scenario document against the Phase 1 input contract. Reads no "
            "exposure artifact, computes nothing and writes no file."
        ),
    )
    validate.add_argument("--input", required=True, metavar="PATH",
                          help="scenario document (.yaml, .yml or .json)")

    for name, help_text in (
        ("run", "score a scenario and rank every industry"),
        ("explain", "show one industry's contributions and their published mediators"),
    ):
        command = subparsers.add_parser(
            name, help=help_text,
            description=(
                help_text[0].upper() + help_text[1:] + ". The basis is required and has no "
                "default: `direct` is the registered primary matrix and `total_requirement` "
                "is a structural sensitivity view that does not replace it."
            ),
        )
        command.add_argument("--input", required=True, metavar="PATH",
                             help="scenario document (.yaml, .yml or .json)")
        command.add_argument("--basis", required=True, choices=list(SUPPORTED_BASES),
                             help="which published exposure matrix to score against")
        command.add_argument("--format", required=True, choices=["json", "markdown"],
                             dest="output_format", help="result document format")
        command.add_argument("--output", required=True, metavar="PATH",
                             help="destination file, or '-' for stdout")
        if name == "explain":
            command.add_argument("--industry", required=True, metavar="IND-XX",
                                 help="industry identifier, for example IND-04")
            command.add_argument(
                "--all", action="store_true", dest="all_mediators",
                help=(
                    f"show all {ALL_MEDIATORS} published mediators per channel instead of "
                    f"the top {DEFAULT_MEDIATORS}"
                ),
            )

    subparsers.add_parser(
        "interactive",
        help="build and run one scenario by answering numbered prompts",
        description=(
            "Build a scenario by answering numbered prompts, then run it. The answers are "
            "validated against the same input contract a scenario file goes through, and "
            "the result takes the same scoring, rendering and output path, so an "
            "equivalent interactive and file-based run produce identical bytes. Prompts go "
            "to stderr and only the final document goes to stdout, so the report can be "
            f"redirected on its own. Cancelling exits {EXIT_CANCELLED} and computes "
            "nothing. This command takes no options: every choice is a prompt."
        ),
    )
    return parser


def _resolve_output(target: str):
    """Decide where a rendered document goes, before it is rendered.

    ``-`` means stdout and never creates a file named ``-``. For a real path, every
    refusal happens here: an existing node of any kind, a missing parent, or a parent
    that is not a directory. Nothing is created and nothing is opened.
    """
    if target == STDOUT_TARGET:
        return None
    path = Path(target)
    parent = path.parent if str(path.parent) else Path(".")
    if path.is_symlink() or path.exists():
        raise _OutputError(
            f"{path} already exists; this command never overwrites, and there is no flag to "
            "make it. Choose a path that does not exist",
            EXIT_OUTPUT_EXISTS,
        )
    if not parent.exists():
        raise _OutputError(
            f"the parent directory {parent} does not exist; it is not created for you",
            EXIT_USAGE,
        )
    if not parent.is_dir():
        raise _OutputError(f"the parent path {parent} is not a directory", EXIT_USAGE)
    return path


def _write_stdout(text: str, stdout) -> None:
    """Put ``text`` on the stream as UTF-8 bytes, without newline translation.

    A text stream translates newlines on the way out, so on Windows ``\n`` would leave the
    process as ``\r\n``: a redirected document would not match the same document written
    to a file, and a checksum taken over a pipe would not verify against one taken over the
    file. Writing bytes bypasses that layer, so one rendering produces one byte sequence
    whichever transport carries it and whichever platform runs it.

    The stream is a parameter rather than ``sys.stdout`` because the tests drive the
    commands in process, and some of those stand-ins are text-only. When no usable binary
    buffer is present the text is written unchanged: that path adds, removes and normalises
    nothing itself, and it is never the production path, because the real ``sys.stdout``
    always exposes ``.buffer``. Nothing global is reconfigured; this function does not own
    a stream it was handed.
    """
    buffer = getattr(stdout, "buffer", None)
    if buffer is None:
        stdout.write(text)
        return
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def _emit(text: str, destination, stdout) -> None:
    """Write a fully rendered document as UTF-8 with LF endings, on both branches.

    **To a file:** exclusive creation, ``encoding="utf-8"``, ``newline="\n"``. The
    document is complete before this is called, so the only way to leave a partial file
    is an I/O failure mid-write — and that file is removed rather than left looking
    finished. No temporary file is created, so there is none to clean up.

    **To standard output:** through :func:`_write_stdout`, which encodes the document and
    writes the bytes, so the transport cannot change what was rendered. A file and a pipe
    carry the same bytes, on every supported platform.
    """
    if destination is None:
        _write_stdout(text, stdout)
        return
    handle = None
    try:
        handle = open(destination, "x", encoding="utf-8", newline="\n")  # noqa: SIM115
        handle.write(text)
    except FileExistsError as exc:
        raise _OutputError(
            f"{destination} already exists; this command never overwrites", EXIT_OUTPUT_EXISTS
        ) from exc
    except OSError as exc:
        if handle is not None:
            handle.close()
            handle = None
            destination.unlink(missing_ok=True)
        raise _OutputError(f"{destination} could not be written: {exc}", EXIT_USAGE) from exc
    finally:
        if handle is not None:
            handle.close()


def _validate(arguments, stdout) -> int:
    policy = load_policy()
    scenario = load_scenario_document(arguments.input, policy=policy)
    # Assembled and emitted once, through the same helper the rendered documents use, so
    # the summary a reader redirects to a file has the same bytes on every platform.
    lines = [
        f"scenario_id            {scenario.scenario_id}\n",
        f"schema_version         {scenario.schema_version}\n",
        f"scenario_date          {scenario.scenario_date or '(none)'}\n",
        f"canonical_input_sha256 {_digest(scenario)}\n",
        f"shocks                 {len(scenario.shocks)}\n",
    ]
    for shock in scenario.shocks:
        # The magnitude is echoed exactly as written, because that is the author's own
        # text. The fraction is printed in its canonical spelling rather than as a bare
        # Decimal: it is the value the digest on the line above is computed from, and a
        # number should not appear here in one form and inside the digest in another.
        lines.append(
            f"  {shock.channel:22} {shock.direction:8} {shock.magnitude} "
            f"{shock.magnitude_unit} -> {shock.canonical_signed_fraction}\n"
        )
    lines.append(f"warnings               {len(scenario.warnings)}\n")
    for warning in scenario.warnings:
        where = warning.channel or "(scenario)"
        lines.append(f"  {warning.code:34} {where}\n")
    lines.append("result                 valid against the input contract\n")
    lines.append("note                   nothing was calculated and no file was written\n")
    _write_stdout("".join(lines), stdout)
    return EXIT_OK


def _digest(scenario) -> str:
    from thai_supply_chain_ews.scenario.contract import canonical_input_sha256

    return canonical_input_sha256(scenario)


def _score(scenario, *, basis, policy):
    """Load the pinned artifacts and score an already-validated scenario.

    Takes a :class:`ValidatedScenario` rather than a path, because by this point it makes
    no difference whether the scenario was read from a file or assembled from answers —
    and the calculation must not be able to tell.
    """
    bundle = load_artifact_bundle(REPOSITORY_ROOT, policy=policy)
    result = calculate_scenario_exposure(scenario, basis=basis, bundle=bundle, policy=policy)
    return bundle, result


def _scored(arguments):
    policy = load_policy()
    scenario = load_scenario_document(arguments.input, policy=policy)
    bundle, result = _score(scenario, basis=arguments.basis, policy=policy)
    return scenario, bundle, result


def execute_run(scenario, *, policy, basis, output_format, destination, stdout) -> int:
    """Score, build, schema-check, render and emit one validated scenario.

    The single path from a validated scenario to bytes on a stream. ``run`` reaches it
    with a scenario read from a file and ``interactive`` with one assembled from answers;
    everything after that point — the artifact bundle, the calculation, the result
    document, its schema validation, the renderer and :func:`_emit` — is the same code
    running on the same inputs, which is why the two produce identical bytes rather than
    merely similar ones.
    """
    bundle, result = _score(scenario, basis=basis, policy=policy)
    document = build_scenario_result_document(scenario, result, bundle)
    validate_result_document(document)
    text = (
        render_scenario_result_json(document)
        if output_format == "json"
        else render_scenario_result_markdown(document)
    )
    _emit(text, destination, stdout)
    return EXIT_OK


def _run(arguments, stdout) -> int:
    destination = _resolve_output(arguments.output)
    policy = load_policy()
    scenario = load_scenario_document(arguments.input, policy=policy)
    return execute_run(scenario, policy=policy, basis=arguments.basis,
                       output_format=arguments.output_format, destination=destination,
                       stdout=stdout)


def _explain(arguments, stdout) -> int:
    destination = _resolve_output(arguments.output)
    scenario, bundle, result = _scored(arguments)
    limit = ALL_MEDIATORS if arguments.all_mediators else DEFAULT_MEDIATORS
    document = build_industry_explanation_document(
        scenario, result, bundle, industry_id=arguments.industry, mediator_limit=limit
    )
    validate_result_document(document)
    text = (
        render_industry_explanation_json(document)
        if arguments.output_format == "json"
        else render_industry_explanation_markdown(document)
    )
    _emit(text, destination, stdout)
    return EXIT_OK


def _interactive(arguments, stdout, stdin=None, stderr=None) -> int:  # noqa: ARG001
    """Ask, validate, confirm, then join the ordinary run path.

    The streams are parameters so a session can be driven in process by the tests. The
    order here mirrors ``_run`` exactly: the destination is resolved — and an existing
    path refused — before any artifact is loaded, so a scenario that cannot be written
    is not one that gets computed first.
    """
    stdin = sys.stdin if stdin is None else stdin
    stderr = sys.stderr if stderr is None else stderr
    policy = load_policy()
    request = collect_request(policy=policy, stdin=stdin, stderr=stderr)
    destination = _resolve_output(request.output_target)
    return execute_run(request.scenario, policy=policy, basis=request.basis,
                       output_format=request.output_format, destination=destination,
                       stdout=stdout)


def main(argv=None) -> int:
    """Run one command and return its exit code. Never raises for a foreseen failure."""
    stdout = sys.stdout
    stderr = sys.stderr
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_usage(stderr)
        stderr.write(
            "error: a command is required: validate, run, explain or interactive\n")
        return EXIT_USAGE

    handlers = {"validate": _validate, "run": _run, "explain": _explain,
                "interactive": _interactive}
    try:
        return handlers[arguments.command](arguments, stdout)
    except InteractiveCancelled as reason:
        # Not an error and not a result. Nothing was read, computed or written.
        stderr.write(f"cancelled: {reason}\n")
        return EXIT_CANCELLED
    except KeyboardInterrupt:
        # Ctrl+C is a foreseen way to stop an interactive session, so it ends the way any
        # interrupted command ends: a newline, one line of explanation, no traceback. For
        # every other command it keeps propagating exactly as it did before, because
        # there it interrupts work rather than answering a question.
        if arguments.command != "interactive":
            raise
        stderr.write("\ncancelled: interrupted\n")
        return EXIT_INTERRUPTED
    except _OutputError as error:
        stderr.write(f"error: {error}\n")
        return error.code
    except UnsupportedChannelError as error:
        stderr.write(f"error: {error}\n")
        return EXIT_UNSUPPORTED_CHANNEL
    except ScenarioContractError as error:
        if error.details.get("condition") == "no_scorable_pairs":
            stderr.write(f"error: {error}\n")
            return EXIT_NO_SCORABLE_PAIRS
        stderr.write(f"error: {error}\n")
        return EXIT_CONTRACT
    except (ScenarioPolicyError, ArtifactIntegrityError) as error:
        stderr.write(f"error: {error}\n")
        return EXIT_ARTIFACT
    except ScenarioInternalError as error:
        stderr.write(f"internal error: {error}\n")
        return EXIT_INTERNAL
    except Exception as error:  # noqa: BLE001 - the boundary that must not leak a traceback
        stderr.write(f"internal error: {type(error).__name__}: {error}\n")
        return EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
