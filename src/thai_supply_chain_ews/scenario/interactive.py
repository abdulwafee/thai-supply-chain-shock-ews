"""Numbered prompts that build a scenario, for people who do not want to write YAML.

This module collects answers and nothing else. It reads no exposure artifact, scores
nothing, renders nothing and opens no output file; it hands back a
:class:`~thai_supply_chain_ews.scenario.contract.ValidatedScenario` and three choices,
and ``__main__`` puts those through exactly the same execution path a file-based ``run``
takes. That division is the point of the module: interactive mode is a way of *writing*
a scenario, not a second way of *computing* one.

Four rules follow from that, and each of them is a refusal.

**The contract is not relaxed to make typing easier.** The answers are assembled into an
ordinary mapping and submitted to the public :func:`validate_scenario_document`. No
temporary file is written, no private parser is called, and nothing skips a check because
a human is on the other end. A scenario that would be refused in a file is refused here,
with the same message and the same exit code.

**Prompts are stderr; the document is stdout.** So ``interactive > result.md`` captures
the report and nothing else, while the questions stay visible in the terminal. Nothing
here writes to stdout at all — the rendered document leaves through ``__main__``'s single
controlled byte writer, on the same path as every other command.

**Nothing is chosen for the reader.** The basis in particular is asked, never defaulted,
for the same reason the flag has no default: ``direct`` is the registered primary matrix
and ``total_requirement`` is a sensitivity view, and a tool that quietly picked one would
be making a governance decision every time it ran. The scenario date is never filled in
with today's date: a scenario date is metadata the author asserts, and inventing one would
put a claim in the record that nobody made.

**Cancelling is an outcome, not a success.** ``q``, ``quit``, answering ``n`` at the
confirmation, and end-of-input all stop before any artifact is read and return
:data:`EXIT_CANCELLED`, which is its own code precisely so that a script cannot mistake a
cancelled session for a completed calculation.

Only the standard library is used. There is no ANSI escape, no cursor movement, no screen
clearing and no terminal-size assumption anywhere in this file, so the session behaves the
same in classic ``cmd.exe`` as in PowerShell, a Linux terminal or a macOS one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TextIO

from thai_supply_chain_ews.scenario.contract import (
    ScenarioPolicy,
    ValidatedScenario,
    canonical_input_sha256,
    validate_scenario_document,
)

#: Answers that cancel the session wherever a question is asked.
CANCEL_ANSWERS = frozenset({"q", "quit"})

#: Affirmative and negative answers, compared case-insensitively.
YES_ANSWERS = frozenset({"y", "yes"})
NO_ANSWERS = frozenset({"n", "no"})

#: The numeric grammar a magnitude may be written in, kept identical to the one the
#: scenario contract enforces: the JSON number grammar, so a scenario means the same
#: thing typed here as it does in a committed file. It is restated rather than imported
#: because the contract's copy is private; ``tests/test_scenario_cli_interactive.py``
#: pins the two together, so drift fails a test rather than silently widening what
#: interactive mode accepts.
MAGNITUDE_GRAMMAR = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")

#: Human-readable names for the registered channels. The identifier is always shown
#: beside the name, so the reader can see the value that will land in the document and
#: can copy it into a file-based scenario later. A channel with no entry here still
#: appears, under its own identifier.
CHANNEL_DISPLAY_NAMES = {
    "brent_crude_usd_bbl": "Brent crude oil",
    "aluminum_usd_mt": "Aluminium",
    "copper_usd_mt": "Copper",
    "rubber_rss3_usd_kg": "Rubber RSS3",
}

#: Labels for the two output destinations. ``-`` is the same stdout target the
#: ``--output`` flag accepts; interactive mode does not invent a second spelling.
STDOUT_TARGET = "-"


class InteractiveCancelled(Exception):
    """The reader cancelled, or input ended. Never an error, never a calculation."""


@dataclass(frozen=True)
class InteractiveRequest:
    """Everything a run needs, once the reader has confirmed it.

    The scenario is already validated against the contract, so by the time this record
    exists the only work left is the work a file-based ``run`` would also do.
    """

    scenario: ValidatedScenario
    basis: str
    output_format: str
    output_target: str


class PromptIO:
    """Reads answers from an explicit stdin and writes questions to an explicit stderr.

    Both streams are parameters rather than ``sys.stdin`` and ``sys.stderr`` so the tests
    can drive a whole session in process with ``StringIO``. Nothing global is
    reconfigured and neither stream is reassigned or closed; this object does not own a
    stream it was handed.

    ``input()`` is deliberately not used: its prompt goes to stdout, which is reserved
    here for the rendered document.
    """

    def __init__(self, stdin: TextIO, stderr: TextIO) -> None:
        self._stdin = stdin
        self._stderr = stderr

    def say(self, text: str = "") -> None:
        self._stderr.write(f"{text}\n")

    def ask(self, prompt: str) -> str:
        """Show ``prompt`` and return one stripped line, or cancel at end of input.

        stderr is flushed before the read so the question is on screen before the
        terminal blocks. The line is stripped of surrounding whitespace and of a
        trailing ``\\r`` — a Windows pipe can deliver one — but nothing inside the
        answer is touched, so a path containing spaces arrives intact and needs no
        shell-style quoting.
        """
        self._stderr.write(prompt)
        self._stderr.flush()
        line = self._stdin.readline()
        if line == "":
            raise InteractiveCancelled("input ended before the scenario was complete")
        return line.rstrip("\n").rstrip("\r").strip()

    def refuse(self, explanation: str) -> None:
        """Explain why an answer was not accepted, in one line, before asking again."""
        self._stderr.write(f"  ! {explanation}\n")


def _cancelled(answer: str) -> bool:
    return answer.casefold() in CANCEL_ANSWERS


def _ask_choice(io: PromptIO, heading: str, options: list[tuple[str, str]]) -> str:
    """Ask a numbered question and return the chosen value, reprompting until valid.

    ``options`` is a list of ``(value, label)`` pairs in the order they are shown. The
    order is the caller's, and for channels it is the policy's own declaration order, so
    the menu numbering is stable across runs and can be tested.
    """
    io.say(heading)
    width = max(len(label) for _, label in options)
    for number, (value, label) in enumerate(options, start=1):
        io.say(f"  {number}. {label.ljust(width)}  ({value})")
    while True:
        answer = io.ask("Choice: ")
        if _cancelled(answer):
            raise InteractiveCancelled("cancelled at a menu")
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        io.refuse(f"enter a number from 1 to {len(options)}, or q to cancel")


def _ask_yes_no(io: PromptIO, prompt: str) -> bool:
    while True:
        answer = io.ask(prompt).casefold()
        if answer in CANCEL_ANSWERS:
            raise InteractiveCancelled("cancelled at a yes/no question")
        if answer in YES_ANSWERS:
            return True
        if answer in NO_ANSWERS:
            return False
        io.refuse("answer y or n, or q to cancel")


def _ask_required_text(io: PromptIO, prompt: str, *, pattern: str, explanation: str) -> str:
    """Ask for a value the contract constrains, and check it here as well.

    Checking the pattern at the prompt is not a second contract — the same rule is
    enforced again by :func:`validate_scenario_document` — it is what lets the reader fix
    a typo in place instead of losing every answer they have already given.
    """
    compiled = re.compile(pattern)
    while True:
        answer = io.ask(prompt)
        if _cancelled(answer):
            raise InteractiveCancelled("cancelled at a required value")
        if answer and compiled.match(answer):
            return answer
        io.refuse(explanation)


def _ask_optional_text(io: PromptIO, prompt: str, *, maximum: int) -> str | None:
    """Ask for a field the contract allows to be absent. Enter omits it entirely.

    An omitted field is left out of the mapping rather than sent as an empty string, so
    the document interactive mode builds is the document a careful author would write.
    """
    while True:
        answer = io.ask(prompt)
        if _cancelled(answer):
            raise InteractiveCancelled("cancelled at an optional value")
        if answer == "":
            return None
        if len(answer) <= maximum:
            return answer
        io.refuse(f"at most {maximum} characters, or Enter to omit")


def _ask_optional_date(io: PromptIO, prompt: str) -> str | None:
    """Ask for the scenario date. Never filled in with today's date."""
    while True:
        answer = io.ask(prompt)
        if _cancelled(answer):
            raise InteractiveCancelled("cancelled at the scenario date")
        if answer == "":
            return None
        if re.match(r"^\d{4}-\d{2}-\d{2}$", answer):
            return answer
        io.refuse("write the date as YYYY-MM-DD, or Enter to omit")


def _ask_magnitude(io: PromptIO) -> Decimal:
    """Ask for a magnitude and return it as an exact :class:`~decimal.Decimal`.

    The text is matched against the contract's own numeric grammar and then handed to
    ``Decimal`` directly. It never passes through ``float``: the whole scenario pipeline
    is exact decimal arithmetic, and a magnitude that had been through binary floating
    point would already have lost the value the reader typed.
    """
    while True:
        answer = io.ask("Magnitude: ")
        if _cancelled(answer):
            raise InteractiveCancelled("cancelled at a magnitude")
        if not MAGNITUDE_GRAMMAR.match(answer):
            io.refuse(
                "write an ordinary base-10 decimal or scientific notation, as JSON would "
                "accept it - 10, 10.5, 0.001, 1e1, 3E-1"
            )
            continue
        try:
            magnitude = Decimal(answer)
        except InvalidOperation:  # pragma: no cover - the grammar already excludes these
            io.refuse("that is not a number this contract recognises")
            continue
        if not magnitude.is_finite():  # pragma: no cover - the grammar excludes inf/nan
            io.refuse("the magnitude must be finite")
            continue
        if magnitude < 0:
            io.refuse("the magnitude must be non-negative; direction carries the sign")
            continue
        return magnitude


def _channel_options(policy: ScenarioPolicy) -> list[tuple[str, str]]:
    """The registered channels, in the policy's own declaration order."""
    return [(entry.channel, CHANNEL_DISPLAY_NAMES.get(entry.channel, entry.channel))
            for entry in policy.channels]


def _ask_channel(io: PromptIO, policy: ScenarioPolicy, chosen: dict[str, str]) -> str:
    """Ask for a channel, refusing one already used and one sharing an official sector.

    Two channels resolving to one official sector are the same measurement twice, so the
    contract refuses such a scenario outright. Catching it at the prompt means the reader
    is told immediately, while they can still pick a different commodity, rather than
    after every remaining answer has been collected.
    """
    options = _channel_options(policy)
    while True:
        channel = _ask_choice(io, "Select commodity / เลือกสินค้า:", options)
        if channel in chosen:
            io.refuse(f"{channel} is already in this scenario; choose a different commodity")
            continue
        entry = policy.channel(channel)
        sector = entry.io_sector_code if entry is not None else None
        clash = next((other for other, code in chosen.items() if code == sector), None)
        if clash is not None:
            io.refuse(
                f"{channel} and {clash} both resolve to official sector {sector}; they are "
                "the same measurement twice, so they cannot appear in one scenario"
            )
            continue
        return channel


def _shock_summary(shock) -> str:
    return (f"  {shock.channel:22} {shock.direction:8} {shock.magnitude} "
            f"{shock.magnitude_unit} -> {shock.canonical_signed_fraction}")


def _review(io: PromptIO, scenario: ValidatedScenario, *, basis: str, output_format: str,
            output_target: str) -> None:
    """Show everything that was decided, before anything is read or computed."""
    io.say()
    io.say("Review / ตรวจทาน:")
    io.say(f"  scenario_id            {scenario.scenario_id}")
    io.say(f"  scenario_name          {scenario.scenario_name or '(omitted)'}")
    io.say(f"  scenario_date          {scenario.scenario_date or '(omitted)'}")
    io.say(f"  schema_version         {scenario.schema_version}")
    io.say(f"  canonical_input_sha256 {canonical_input_sha256(scenario)}")
    io.say(f"  shocks                 {len(scenario.shocks)}")
    for shock in scenario.shocks:
        io.say(_shock_summary(shock))
    io.say(f"  warnings               {len(scenario.warnings)}")
    for warning in scenario.warnings:
        io.say(f"  {warning.code:34} {warning.channel or '(scenario)'}")
    io.say(f"  basis                  {basis}")
    io.say(f"  format                 {output_format}")
    io.say(f"  output                 "
           f"{'terminal (stdout)' if output_target == STDOUT_TARGET else output_target}")
    io.say()


def collect_request(*, policy: ScenarioPolicy, stdin: TextIO, stderr: TextIO,
                    ) -> InteractiveRequest:
    """Run one session and return a confirmed, validated request.

    Raises :class:`InteractiveCancelled` if the reader cancels at any point, including at
    the final confirmation. Nothing outside this function is touched: no artifact is
    loaded, no calculation is started and no file is created, so a cancelled session
    leaves the machine exactly as it found it.

    One invocation collects one scenario. There is no outer loop, because a tool that
    keeps asking after it has answered is a tool that is hard to stop.
    """
    io = PromptIO(stdin, stderr)
    io.say("Thai Supply Chain Shock EWS - Interactive Scenario")
    io.say("Answer the numbered prompts. Enter q at any question to cancel.")
    io.say()

    scenario_id = _ask_required_text(
        io, "Scenario ID: ",
        pattern=policy.scenario_id_pattern,
        explanation=(
            f"the identifier must match {policy.scenario_id_pattern} - lowercase letters, "
            "digits, hyphen and underscore, 3 to 64 characters"
        ),
    )
    scenario_name = _ask_optional_text(
        io, "Scenario name (optional; Enter to omit): ",
        maximum=policy.max_scenario_name_length,
    )
    scenario_date = _ask_optional_date(
        io, "Scenario date YYYY-MM-DD (optional; Enter to omit): ")

    shocks: list[dict] = []
    chosen: dict[str, str] = {}
    while True:
        io.say()
        channel = _ask_channel(io, policy, chosen)
        direction = _ask_choice(
            io, "Select direction / เลือกทิศทาง:",
            [(value, value.capitalize()) for value in policy.allowed_directions],
        )
        magnitude = _ask_magnitude(io)
        unit = _ask_choice(
            io, "Select unit / เลือกหน่วย:",
            [(value, value.capitalize()) for value in policy.allowed_magnitude_units],
        )
        shocks.append({"channel": channel, "direction": direction,
                       "magnitude": magnitude, "magnitude_unit": unit})
        entry = policy.channel(channel)
        chosen[channel] = entry.io_sector_code if entry is not None else ""
        if len(shocks) >= policy.max_shocks:
            io.say(f"  ({policy.max_shocks} shocks is the declared limit for one scenario)")
            break
        io.say()
        if not _ask_yes_no(io, "Add another shock? [y/n]: "):
            break

    io.say()
    basis = _ask_choice(
        io, "Select calculation basis / เลือกฐานการคำนวณ:",
        [(value, value.replace("_", " ").capitalize()) for value in policy.supported_bases],
    )
    io.say()
    output_format = _ask_choice(io, "Select output format / เลือกรูปแบบผลลัพธ์:",
                                [("json", "JSON"), ("markdown", "Markdown")])
    io.say()
    destination = _ask_choice(io, "Select output destination / เลือกปลายทาง:",
                              [("terminal", "Terminal"), ("file", "New file")])
    if destination == "terminal":
        output_target = STDOUT_TARGET
    else:
        while True:
            answer = io.ask("Output file path: ")
            if _cancelled(answer):
                raise InteractiveCancelled("cancelled at the output path")
            if answer:
                output_target = answer
                break
            io.refuse("enter a path that does not exist yet, or q to cancel")

    document: dict = {
        "schema_version": policy.accepted_input_schema_version,
        "scenario_id": scenario_id,
        "shocks": shocks,
    }
    if scenario_name is not None:
        document["scenario_name"] = scenario_name
    if scenario_date is not None:
        document["scenario_date"] = scenario_date

    # The same public entry point a file-based scenario reaches, on an in-memory mapping.
    # Nothing was written to disk to get here and nothing is written to get past it.
    scenario = validate_scenario_document(document, policy=policy)

    _review(io, scenario, basis=basis, output_format=output_format,
            output_target=output_target)
    if not _ask_yes_no(io, "Run this scenario? [y/n]: "):
        raise InteractiveCancelled("not confirmed at the review step")

    return InteractiveRequest(scenario=scenario, basis=basis, output_format=output_format,
                              output_target=output_target)


__all__ = [
    "CANCEL_ANSWERS",
    "CHANNEL_DISPLAY_NAMES",
    "MAGNITUDE_GRAMMAR",
    "STDOUT_TARGET",
    "InteractiveCancelled",
    "InteractiveRequest",
    "PromptIO",
    "collect_request",
]
