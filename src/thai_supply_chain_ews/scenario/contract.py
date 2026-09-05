"""The scenario input contract: what a user may ask, and what is refused.

This module is the trust boundary of the Structural Exposure Scenario CLI. A
scenario document is a file somebody wrote by hand, so it is treated the way
:mod:`thai_supply_chain_ews.vault.safety` treats a vault manifest — as untrusted
structured input that must prove itself before anything downstream sees it.

Four decisions shape everything here.

**Unknown fields are refused, never ignored.** A silently dropped field is a
scenario the author believes they ran and did not. ``duration_months`` and
``affected_trading_partner`` are the sharp cases: both are plausible, both would
look accepted, and neither can affect any number this project is able to compute.
They are refused by name with the reason, which is a different and more useful
answer than "unknown field".

**Two channels on one official I/O sector are refused, not merged.** Aluminum and
copper both resolve to sector 107, so their coefficients are identical by
construction and are the same measurement twice. Summing them double-counts.
Silently dropping one, or keeping the larger, answers a question nobody asked. The
document is refused and the message names both channels and the sector.

**Direction carries the sign; magnitude never does.** A negative magnitude is
ambiguous — it could mean a decrease, or a decrease of a decrease — so it is
refused, and ``direction`` is the only place a sign comes from. The bounds are
direction-sensitive because a 200% increase is merely extreme while a 200% decrease
is not a thing that can happen.

**``scenario_date`` is metadata and stays metadata.** It records when somebody
framed the scenario. It selects no data and it is not a vintage.
:data:`STRUCTURAL_REFERENCE_YEAR` is 2015 on every validated scenario regardless of
what the field says, and :func:`validate_scenario_document` copies it from policy
rather than from the document so there is no path by which a date could change it.

Every limit in :mod:`configs/structural_exposure_scenario.yaml` is declared
validation policy. None of it was estimated, fitted or learned, and the module says
so in :data:`ScenarioPolicy.limits_are_learned_thresholds`, which must be ``False``.

Phase 1 stops at a validated, canonically hashable input. Nothing here loads an
exposure artifact, computes anything, ranks anything or writes anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    localcontext,
)
from pathlib import Path

import yaml

__all__ = [
    "CONTRACT_ERROR_CODES",
    "DEFAULT_POLICY_PATH",
    "EXCLUDED_INPUT_FIELDS",
    "INPUT_SCHEMA_VERSION",
    "REGISTERED_CHANNELS",
    "SHOCK_OPTIONAL_FIELDS",
    "SHOCK_REQUIRED_FIELDS",
    "STRUCTURAL_REFERENCE_YEAR",
    "TOP_LEVEL_OPTIONAL_FIELDS",
    "TOP_LEVEL_REQUIRED_FIELDS",
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
    "decimal_text",
    "load_policy",
    "load_scenario_document",
    "validate_scenario_document",
]

#: The one accepted document schema version. There is no forward tolerance.
INPUT_SCHEMA_VERSION = "structural_exposure_scenario_v1"

#: Fixed on every validated scenario, copied from policy and never from the
#: document. The NESDC benchmark year is a property of the coefficients, not of
#: anything a user can write.
STRUCTURAL_REFERENCE_YEAR = 2015

#: The only channels this release recognises. The policy file restates them; a
#: policy that names any other channel is refused, which is what keeps I/O sector
#: 093 out of v1.2.0 whatever a configuration file happens to say.
REGISTERED_CHANNELS = frozenset(
    {"aluminum_usd_mt", "brent_crude_usd_bbl", "copper_usd_mt", "rubber_rss3_usd_kg"}
)

#: Never a channel in this release. Checked by code as well as by configuration,
#: because "the config did not list it" is a weaker guarantee than "the code
#: refuses it".
FORBIDDEN_IO_SECTOR_CODES = frozenset({"093"})

TOP_LEVEL_REQUIRED_FIELDS = frozenset({"schema_version", "scenario_id", "shocks"})
TOP_LEVEL_OPTIONAL_FIELDS = frozenset({"scenario_name", "scenario_date", "note"})
SHOCK_REQUIRED_FIELDS = frozenset({"channel", "direction", "magnitude", "magnitude_unit"})
SHOCK_OPTIONAL_FIELDS = frozenset({"note"})

ALLOWED_DIRECTIONS = ("increase", "decrease")
ALLOWED_MAGNITUDE_UNITS = ("percent", "fraction")

# The policy loader refuses any divisor but 100, so percent-to-fraction is a shift of
# the decimal point by two places. Both are stated here so the shift and the value it
# stands for cannot drift apart silently.
_PERCENT_DIVISOR = Decimal(100)
_PERCENT_PLACES = 2

#: Fields refused by name with a reason rather than as a generic unknown field.
#: Each one is a thing a reasonable person would try, and each one would be
#: accepted-and-ignored if this mapping did not exist.
#:
#: **FROZEN for** ``structural_exposure_scenario_v1``. Adding or removing an entry
#: is a visible contract change, not an editorial one: a document carrying that
#: field would stop being refused as ``excluded_field`` and start being refused as
#: ``unknown_field``, or the reverse, and a caller branching on the machine-readable
#: code would silently change behaviour without anything in the document changing.
#: A future incompatible change takes a NEW schema version rather than editing this
#: mapping in place. ``tests/test_scenario_contract.py`` pins the exact set.
EXCLUDED_INPUT_FIELDS = {
    "as_of_date": "superseded by scenario_date, which states plainly that it is metadata",
    "duration_months": (
        "no published artifact turns a duration into an exposure, so the field would be "
        "accepted and change nothing"
    ),
    "affected_trading_partner": "no country-to-industry exposure artifact exists",
    "basis": "the basis is an explicit command-line argument, never a document field",
    "company_id": "no company-level data exists in this project",
    "output_path": "an input document does not decide where output is written",
    "model": "no model is trained, loaded or consulted",
    "risk_threshold": (
        "the registered risk bands are defined over the production stress index, not over "
        "structural exposure"
    ),
}

#: Stable machine codes. A caller distinguishes failures by ``error.code`` and by
#: exception type, never by reading the message.
CONTRACT_ERROR_CODES = frozenset(
    {
        "unsupported_extension",
        "input_too_large",
        "unreadable_document",
        "malformed_document",
        "duplicate_mapping_key",
        "document_not_a_mapping",
        "unknown_field",
        "excluded_field",
        "missing_field",
        "bad_schema_version",
        "bad_scenario_id",
        "bad_field_type",
        "overlong_field",
        "empty_field",
        "bad_scenario_date",
        "no_shocks",
        "too_many_shocks",
        "shock_not_a_mapping",
        "unsupported_channel",
        "duplicate_channel",
        "shared_io_sector",
        "bad_direction",
        "unsupported_magnitude_unit",
        "magnitude_not_a_number",
        "magnitude_not_finite",
        "magnitude_negative",
        "magnitude_increase_above_ceiling",
        "magnitude_decrease_above_ceiling",
    }
)

#: Structured warning codes. Warnings never change a value; they say something the
#: reader needs in order to interpret one.
WARNING_CODES = frozenset({"zero_magnitude_no_discrimination", "extreme_increase_magnitude"})

_SCENARIO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: The one numeric grammar a scenario magnitude may be written in::
#:
#:     -? ( 0 | [1-9][0-9]* ) ( '.' [0-9]+ )? ( [eE] [+-]? [0-9]+ )?
#:
#: This is the JSON number grammar, and choosing it is the whole point: a scenario
#: means the same thing in both formats or the contract is not a contract. YAML 1.1
#: is far more generous — ``0x1e1`` is 481, ``017`` is 15, ``0b101`` is 5, ``1_000``
#: is a thousand, ``190:20:30.15`` is sexagesimal — and every one of those is a
#: syntax error in JSON. Accepting them because PyYAML happens to convert them would
#: make the same document mean two different things.
#:
#: Four exclusions are worth naming because each looks harmless:
#:
#: * a leading ``+`` (``+10``) is invalid JSON, and direction already carries the sign;
#: * a leading-dot decimal (``.5``) and a trailing-dot decimal (``1.``) are both
#:   invalid JSON;
#: * a leading zero (``017``) is invalid JSON and is octal in YAML 1.1, so it means
#:   two different numbers in the two formats;
#: * digit separators (``1_0.5``) are a YAML extension with no JSON equivalent.
#:
#: Used twice, and both uses matter. As a **constructor** check it decides whether a
#: lexeme becomes a :class:`Decimal` or is handed back as text to be refused by name.
#: As an **implicit resolver** it claims the exponent forms YAML 1.1 leaves as plain
#: strings. Being implicit confines it to plain scalars, so a quoted ``"1E+1"`` keeps
#: the string tag YAML gives it and is refused — the author wrote a string.
_STRICT_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")

#: ``src/thai_supply_chain_ews/scenario/contract.py`` -> repository root.
#:
#: Deliberately not :func:`thai_supply_chain_ews.config.get_project_root`, which
#: requires ``THAI_SUPPLY_CHAIN_EWS_ROOT`` and refuses to guess. That is right for a
#: pipeline and wrong for a command somebody types: a user-facing tool that fails
#: until an environment variable is exported is a tool nobody runs. This mirrors
#: ``scripts/build_obsidian_vault.py``, which resolves its root from ``__file__``.
DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "structural_exposure_scenario.yaml"
)


class ScenarioContractError(ValueError):
    """A scenario document does not satisfy the input contract.

    Carries a stable :attr:`code` from :data:`CONTRACT_ERROR_CODES` and, where one
    applies, the offending ``field``. The message is for a person; the code is for
    the caller, so a future command-line layer can map failures onto exit codes
    without pattern-matching prose.
    """

    code = "contract_violation"

    def __init__(self, message: str, *, code: str, field: str | None = None,
                 details: dict | None = None) -> None:
        super().__init__(message)
        if code not in CONTRACT_ERROR_CODES:
            raise ScenarioInternalError(
                f"{code!r} is not a declared contract error code; the taxonomy in "
                "CONTRACT_ERROR_CODES is the whole set a caller may branch on, so raising "
                "an unlisted one would give the caller a code it cannot handle"
            )
        self.code = code
        self.field = field
        self.details = dict(details or {})


class UnsupportedChannelError(ScenarioContractError):
    """The document names a channel this release does not recognise.

    A distinct type as well as a distinct code, because "you misspelled a channel"
    and "your document is malformed" deserve different answers and the caller
    should be able to separate them with ``except`` alone.
    """

    def __init__(self, message: str, *, field: str | None = None,
                 details: dict | None = None) -> None:
        super().__init__(message, code="unsupported_channel", field=field, details=details)


class ScenarioPolicyError(RuntimeError):
    """The policy configuration itself is malformed, incomplete or inconsistent.

    Separate from :class:`ScenarioContractError` because it is not the user's fault
    and cannot be fixed by editing the scenario. A shipped policy that fails to load
    is a packaging defect, and the two must never be reported as the same thing.
    """


class ScenarioInternalError(RuntimeError):
    """An impossible internal state: a defect in this module, not in any input.

    The third thing that can go wrong, and it deserves its own name. A malformed
    scenario is the user's to fix; a malformed policy is the packager's; this is
    neither. It is raised only where a value has already passed a boundary that
    should have made the state unreachable — an error code outside the declared set,
    or a non-finite magnitude surviving validation — so seeing one means an
    invariant is wrong rather than that somebody typed something odd.

    It must never be caught and re-reported as a contract violation. Telling a user
    their document is invalid when the defect is ours sends them to fix a file that
    is already correct, and buries the only evidence that something here is broken.
    """


def decimal_text(value: Decimal) -> str:
    """The canonical decimal string for a validated magnitude.

    One value, one spelling. ``0.30``, ``0.300`` and ``3.0E-1`` are the same number
    written three ways and all become ``"0.3"``; ``10``, ``10.0`` and ``1E+1`` become
    ``"10"``.

    Built entirely from :meth:`~decimal.Decimal.as_tuple` -- the sign, the digit tuple
    and the exponent -- with no arithmetic of any kind. That is the point rather than a
    matter of style. The obvious implementation, ``format(value.normalize(), "f")``, is
    **context-sensitive**: ``normalize`` rounds to the ambient precision, so under a
    precision-6 context a twenty-one digit exposure was written out as six digits,
    silently, in the document a reader quotes. Reading the stored representation cannot
    round, cannot depend on a global that some other library set, and keeps every
    significant digit the Decimal holds however long it is.

    Trailing zeros are dropped from the digit tuple with the exponent adjusted to
    compensate, which is exactly value-preserving, and the result is laid out in
    ordinary decimal notation, never exponent form. Zero is returned as ``"0"`` whatever
    its sign or scale, so ``-0``, ``-0.00`` and ``0E+5`` cannot produce three different
    digests for the same absence of a shock. Direction is a separate field, so a zero
    increase and a zero decrease still differ -- because the author said something
    different, not because of how a signed zero happens to encode.
    """
    if not value.is_finite():
        raise ScenarioInternalError(
            f"{value} is not finite; a validated magnitude cannot be, so reaching this "
            "means the magnitude check was bypassed rather than that a user wrote something "
            "unusual"
        )
    sign, digits, exponent = value.as_tuple()
    if not any(digits):
        return "0"

    significant = list(digits)
    while len(significant) > 1 and significant[-1] == 0:
        significant.pop()
        exponent += 1
    text = "".join(str(digit) for digit in significant)

    if exponent >= 0:
        body = text + "0" * exponent
    else:
        point = len(text) + exponent
        body = f"{text[:point]}.{text[point:]}" if point > 0 else f"0.{'0' * -point}{text}"
    return f"-{body}" if sign else body


def scale_down_by_power_of_ten(value: Decimal, places: int) -> Decimal:
    """``value`` divided by ``10 ** places``, exactly, without consulting a context.

    Dividing by a power of ten moves the decimal point and does not change a single
    digit, so the result is rebuilt from the sign, digits and exponent rather than
    calculated. ``value / Decimal(100)`` looks equivalent and is not: division is a
    context operation, so under the ambient precision a long magnitude comes back
    shortened -- a sixty-digit percentage would be scored as a twenty-eight digit one,
    with no error raised and nothing in the output to say the author's number was not
    the number used.
    """
    sign, digits, exponent = value.as_tuple()
    return Decimal((sign, digits, exponent - places))


# ---------------------------------------------------------------------------
# Exact decimal arithmetic
#
# Every Decimal operation consults a context, and the process-wide one belongs to
# whatever program is embedding this package. At its default precision the difference
# is invisible; at a precision some other library set, a coefficient silently loses
# digits and an exactness check fails on a value that was never wrong.
#
# The width is derived from the operands rather than fixed, because a fixed ceiling is
# a correctness boundary in disguise: the input contract bounds a magnitude's VALUE but
# not its digit count, so a contract-valid magnitude can be long, and any constant
# ceiling truncates somewhere.
#
# * a product of an m-digit and an n-digit decimal is exact in m + n digits;
# * a sum is exact across the span from the smallest exponent to the largest adjusted
#   exponent, with one place per term so no carry is lost.
#
# `Inexact` is TRAPPED in the exact contexts. If a derivation were ever short by one
# digit the operation raises instead of quietly rounding, so "this is exact" is enforced
# by the arithmetic rather than asserted in a comment.
#
# None of these helpers evaluate anything before entering their context, and none take
# an expression as an argument that a caller had to compute first. That is the whole
# hazard: `helper(-value)` negates in the CALLER's context, because arguments are
# evaluated before the callee opens its own.
_ARITHMETIC_EMIN = -999999
_ARITHMETIC_EMAX = 999999

#: Conditions that always mean a defect rather than a number needing rounding.
ARITHMETIC_ERROR_SIGNALS = (InvalidOperation, DivisionByZero, Overflow)
_EXACT_SIGNALS = (*ARITHMETIC_ERROR_SIGNALS, Inexact)


def fixed_context(precision: int) -> Context:
    """A context that rounds deterministically at a declared width.

    For quotients, where no precision is exact and the width is therefore a declared
    presentation choice rather than a fact about the operands.
    """
    return Context(
        prec=max(int(precision), 1), rounding=ROUND_HALF_EVEN,
        Emin=_ARITHMETIC_EMIN, Emax=_ARITHMETIC_EMAX,
        traps=list(ARITHMETIC_ERROR_SIGNALS),
    )


def exact_context(precision: int) -> Context:
    """A context wide enough that the operation about to run cannot round."""
    return Context(
        prec=max(int(precision), 1), rounding=ROUND_HALF_EVEN,
        Emin=_ARITHMETIC_EMIN, Emax=_ARITHMETIC_EMAX,
        traps=list(_EXACT_SIGNALS),
    )


def significant_digits(value: Decimal) -> int:
    """How many digits the value actually carries, read rather than computed."""
    return len(value.as_tuple().digits)


def exact_product(left: Decimal, right: Decimal) -> Decimal:
    """``left * right``, exactly. An m-digit by n-digit product needs m + n digits."""
    with localcontext(exact_context(significant_digits(left) + significant_digits(right))):
        return left * right


def exact_total(values) -> Decimal:
    """The exact sum of ``values``.

    Width is the span from the least significant exponent to the most significant
    digit, plus one place per term so no carry is lost.
    """
    values = list(values)
    contributing = [value for value in values if value != 0]
    if not contributing:
        return Decimal(0)
    high = max(value.adjusted() for value in contributing) + len(contributing)
    low = min(value.as_tuple().exponent for value in contributing)
    with localcontext(exact_context(high - low + 1)):
        running = Decimal(0)
        for value in values:
            running += value
        return running


def exact_difference(left: Decimal, right: Decimal) -> Decimal:
    """``left - right``, exactly.

    ``copy_negate`` rather than ``-right``: unary minus is a context operation, and the
    argument is evaluated before :func:`exact_total` enters its own context, so
    ``-right`` would already have been rounded to the caller's ambient precision on the
    way in. ``copy_negate`` only flips the sign bit and is defined to ignore the context.
    """
    return exact_total([left, right.copy_negate()])


@dataclass(frozen=True)
class ScenarioWarning:
    """Something true about a validated scenario that the reader needs to know.

    ``channel`` is what makes the association unambiguous when one code describes
    both a single shock and the whole scenario: a per-shock warning names its
    channel, and a scenario-level warning carries ``None``.
    """

    code: str
    message: str
    field: str | None = None
    channel: str | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "channel": self.channel,
        }

    @property
    def is_scenario_level(self) -> bool:
        return self.channel is None


@dataclass(frozen=True)
class ChannelPolicy:
    """One registered channel and the official I/O sector it resolves to."""

    channel: str
    io_sector_code: str
    io_sector_label: str
    scope_note: str


@dataclass(frozen=True)
class MagnitudePolicy:
    """Declared validation limits on magnitude. Not learned, not empirical.

    Every bound is a :class:`Decimal` built from the configuration file's own text,
    so a threshold is compared against a magnitude in the same arithmetic the
    magnitude was parsed in. A bound that arrived as a binary float would make
    "exactly 1000%" a question about rounding.
    """

    percent_to_fraction_divisor: Decimal
    increase_warn_above_fraction: Decimal
    increase_refuse_above_fraction: Decimal
    decrease_refuse_above_fraction: Decimal
    limits_are_validation_policy: bool
    limits_are_learned_thresholds: bool


@dataclass(frozen=True)
class ScenarioPolicy:
    """The validated policy configuration, as an immutable record."""

    config_version: str
    accepted_input_schema_version: str
    structural_reference_year: int
    accepted_input_extensions: tuple[str, ...]
    max_input_bytes: int
    min_shocks: int
    max_shocks: int
    max_scenario_name_length: int
    max_note_length: int
    scenario_id_pattern: str
    scenario_date_is_metadata_only: bool
    supported_bases: tuple[str, ...]
    registered_primary_basis: str
    total_requirement_role: str
    basis_must_be_explicit: bool
    allowed_magnitude_units: tuple[str, ...]
    allowed_directions: tuple[str, ...]
    shared_io_sector_policy: str
    channels: tuple[ChannelPolicy, ...]
    magnitude: MagnitudePolicy

    def channel(self, name: str) -> ChannelPolicy | None:
        for entry in self.channels:
            if entry.channel == name:
                return entry
        return None

    @property
    def channel_names(self) -> tuple[str, ...]:
        return tuple(sorted(entry.channel for entry in self.channels))


@dataclass(frozen=True)
class ValidatedShock:
    """One accepted shock.

    Both representations are kept on purpose. ``magnitude`` and ``magnitude_unit``
    are what the author wrote and are echoed back to them; ``magnitude_fraction``
    and ``signed_magnitude_fraction`` are what the calculation will use and what
    identifies the scenario.
    """

    channel: str
    io_sector_code: str
    direction: str
    magnitude: Decimal
    magnitude_unit: str
    magnitude_fraction: Decimal
    signed_magnitude_fraction: Decimal
    note: str | None = None

    @property
    def is_zero(self) -> bool:
        return self.magnitude_fraction == 0

    @property
    def canonical_signed_fraction(self) -> str:
        """The exact string this shock contributes to the canonical payload."""
        return decimal_text(self.signed_magnitude_fraction)


@dataclass(frozen=True)
class ValidatedScenario:
    """A scenario document that satisfied the contract.

    ``structural_reference_year`` and ``coefficient_vintage_is_scenario_date`` are
    fixed here and are not derived from ``scenario_date``. Two documents differing
    only in ``scenario_date`` therefore carry identical vintage metadata, which is
    the property that stops a date from quietly becoming a currency claim.
    """

    schema_version: str
    scenario_id: str
    shocks: tuple[ValidatedShock, ...]
    warnings: tuple[ScenarioWarning, ...]
    policy_version: str
    structural_reference_year: int
    scenario_name: str | None = None
    scenario_date: str | None = None
    note: str | None = None
    scenario_date_is_metadata_only: bool = True
    coefficient_vintage_is_scenario_date: bool = False

    @property
    def channels(self) -> tuple[str, ...]:
        return tuple(shock.channel for shock in self.shocks)

    @property
    def warning_codes(self) -> tuple[str, ...]:
        return tuple(warning.code for warning in self.warnings)

    @property
    def zero_magnitude_channels(self) -> tuple[str, ...]:
        """Channels whose magnitude is zero, in canonical channel order."""
        return tuple(shock.channel for shock in self.shocks if shock.is_zero)

    @property
    def all_shocks_are_zero(self) -> bool:
        """Whether nothing in this scenario can separate one industry from another.

        Structured rather than inferred from warning text, because the later ranking
        phase has to decide whether to produce a ranking at all and must not do that
        by reading prose.
        """
        return bool(self.shocks) and all(shock.is_zero for shock in self.shocks)

    def warnings_for(self, channel: str) -> tuple[ScenarioWarning, ...]:
        return tuple(warning for warning in self.warnings if warning.channel == channel)

    @property
    def scenario_level_warnings(self) -> tuple[ScenarioWarning, ...]:
        return tuple(warning for warning in self.warnings if warning.is_scenario_level)


# ---------------------------------------------------------------------------
# Parsing: duplicate keys and size are handled before anything else looks at the
# content, because both are ways a document can lie about what it says.
# ---------------------------------------------------------------------------


class _ScenarioInputLoader(yaml.SafeLoader):
    """Reads a user's scenario document. Strict, and deliberately unlike PyYAML.

    A scenario file is untrusted input, and YAML is a large language whose defaults
    were designed for convenience rather than for a document somebody will quote a
    number out of. Four of those defaults are overridden here.

    **Duplicate keys are refused.** ``yaml.safe_load`` keeps the last of two identical
    keys. A document with ``magnitude`` twice has two readings and PyYAML picks one
    without saying so.

    **Numbers are exact decimals, in one grammar.** Every float would otherwise be
    built by calling ``float()`` on the lexeme — a lossy step taken before this module
    sees the value, so a canonical digest would rest on IEEE rounding happening to
    agree. Worse, YAML 1.1 would quietly accept spellings JSON does not:
    ``0x1e1`` is 481, ``017`` is 15, ``1_000`` is a thousand. A scenario that means
    one thing as YAML and another as JSON is not a contract, so both constructors here
    accept exactly :data:`_STRICT_DECIMAL` — ordinary base-10, the JSON number grammar
    — and hand anything else back as the string it was written as, which the magnitude
    check then refuses by name.

    **Dates stay text.** PyYAML resolves ``2026-09-04`` to a ``datetime.date`` before
    validation can see it, so the field's own ISO rule never runs and an invalid date
    fails as a parse error. The lexeme is preserved instead and
    :func:`_scenario_date` decides.

    **Nothing but plain data is constructed.** Inherited from ``SafeLoader``: no
    arbitrary object construction, no ``!!python/`` tags.
    """


class _PolicyLoader(yaml.SafeLoader):
    """Reads this repository's own policy file, which is not user input.

    It shares the duplicate-key refusal — one key twice is ambiguous wherever it
    appears — and reads floats as exact decimals so a threshold is compared against a
    magnitude in the same arithmetic.

    It does **not** inherit the scenario loader's strict numeric grammar or its date
    handling, and that separation is the point. The two files have different authors
    and different risks: this one is version-controlled, reviewed and shipped, so the
    job here is exactness, not defence against spellings nobody will write. Sharing
    one loader would have meant either loosening the input contract or constraining
    the policy file for a reason that does not apply to it.
    """


def _construct_mapping_no_duplicates(loader: yaml.SafeLoader, node: yaml.MappingNode,
                                     deep: bool = False) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScenarioContractError(
                f"duplicate key {key!r} in the scenario document; a document with one key "
                "twice has two readings and this validator will not choose between them",
                code="duplicate_mapping_key",
                field=str(key),
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


def _construct_strict_decimal(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> Decimal | str:
    """Scenario input: a base-10 decimal, or the original text, and nothing in between.

    ``.inf``, ``-.inf`` and ``.nan`` become the corresponding non-finite decimals so
    the magnitude check refuses them as ``magnitude_not_finite`` — naming the field
    rather than reporting a broken file.

    Every other lexeme must match :data:`_STRICT_DECIMAL` exactly. A hexadecimal,
    octal, binary, digit-separated, sexagesimal or partial spelling is returned as the
    string it was written as, and fails later as ``magnitude_not_a_number`` with a
    message that says which notations are supported. Returning the text rather than
    raising here keeps the refusal attached to a field name: the file parsed fine, the
    number is the problem.
    """
    text = str(loader.construct_scalar(node))
    lowered = text.lower()
    if lowered in (".inf", "+.inf"):
        return Decimal("Infinity")
    if lowered == "-.inf":
        return Decimal("-Infinity")
    if lowered == ".nan":
        return Decimal("NaN")
    if _STRICT_DECIMAL.match(text):
        return Decimal(text)
    return text


def _construct_policy_decimal(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> Decimal | str:
    """Policy file: any lexeme :class:`Decimal` can hold, read from the text itself."""
    text = str(loader.construct_scalar(node))
    lexeme = text.replace("_", "")
    lowered = lexeme.lower()
    if lowered.endswith(".inf"):
        return Decimal("-Infinity") if lowered.startswith("-") else Decimal("Infinity")
    if lowered.endswith(".nan"):
        return Decimal("NaN")
    try:
        return Decimal(lexeme)
    except InvalidOperation:
        return text


def _construct_scalar_text(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> str:
    """Preserve a scalar exactly as written, whatever tag YAML resolved it to."""
    return str(loader.construct_scalar(node))


for _loader in (_ScenarioInputLoader, _PolicyLoader):
    _loader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_duplicates
    )

_PolicyLoader.add_constructor("tag:yaml.org,2002:float", _construct_policy_decimal)

_ScenarioInputLoader.add_constructor("tag:yaml.org,2002:float", _construct_strict_decimal)
# YAML 1.1 resolves ``10`` as an int and ``0x1e1`` as one too. Both arrive here, and
# only the first is a number this contract recognises.
_ScenarioInputLoader.add_constructor("tag:yaml.org,2002:int", _construct_strict_decimal)
# ``2026-09-04`` would otherwise become a ``datetime.date`` before the field's own ISO
# rule could run, and ``2026-02-30`` would fail as a parse error rather than as a bad
# date on a named field.
_ScenarioInputLoader.add_constructor("tag:yaml.org,2002:timestamp", _construct_scalar_text)

# Appended after PyYAML's own resolvers, so it only claims plain scalars none of them
# did: YAML 1.1 wants a decimal point AND a signed exponent for a float, leaving
# ``1e1``, ``1E+1`` and ``3E-1`` as plain strings even though JSON accepts all three.
# Sexagesimal, ``.inf`` and ``.nan`` still match YAML's own float resolver first.
_ScenarioInputLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float", _STRICT_DECIMAL, list("-0123456789")
)


def _json_object_pairs_no_duplicates(pairs: list) -> dict:
    mapping: dict = {}
    for key, value in pairs:
        if key in mapping:
            raise ScenarioContractError(
                f"duplicate key {key!r} in the scenario document; a document with one key "
                "twice has two readings and this validator will not choose between them",
                code="duplicate_mapping_key",
                field=str(key),
            )
        mapping[key] = value
    return mapping


def _parse_document_text(text: str, *, suffix: str) -> dict:
    """Parse YAML or JSON text into a mapping, refusing duplicate keys.

    Module-private. It exists because reading and validating are separate concerns,
    not because a caller needs it: the supported entry point is
    :func:`load_scenario_document`, and exporting a parse step would invite code to
    depend on a half-checked mapping.

    ``parse_float=Decimal`` is the JSON counterpart of the loader's float
    constructor. JSON integer literals stay :class:`int`, which converts to
    :class:`Decimal` exactly, so no numeric literal in either format passes through
    binary floating point on its way to a digest.

    ``parse_constant`` is a separate hook and is easy to miss: ``NaN``, ``Infinity``
    and ``-Infinity`` are handled by it rather than by ``parse_float``, so without
    this they would arrive as binary floats and be refused for the wrong reason. With
    it they arrive as non-finite decimals and the magnitude check names the field.

    Every parser failure becomes a :class:`ScenarioContractError` with a code, so a
    caller never has to catch a library exception to know the document was bad.
    """
    suffix = suffix.lower()
    try:
        if suffix == ".json":
            loaded = json.loads(
                text,
                object_pairs_hook=_json_object_pairs_no_duplicates,
                parse_float=Decimal,
                parse_constant=Decimal,
            )
        else:
            loaded = yaml.load(text, Loader=_ScenarioInputLoader)  # noqa: S506 - see loader
    except ScenarioContractError:
        raise
    except (yaml.YAMLError, json.JSONDecodeError, ValueError) as exc:
        raise ScenarioContractError(
            f"the scenario document could not be parsed: {exc}",
            code="malformed_document",
        ) from exc
    if loaded is None or not isinstance(loaded, dict):
        raise ScenarioContractError(
            "the scenario document must be a mapping at the top level",
            code="document_not_a_mapping",
        )
    return loaded


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def _require_decimal(mapping: dict, key: str, *, where: str) -> Decimal:
    """A policy threshold, as an exact decimal.

    The loader already produced a :class:`Decimal` for any float scalar in the file,
    so the usual path is a straight type check. An integer is converted exactly. A
    string is refused: a threshold spelled ``"ten"`` is a configuration defect, and
    coercing it would be the kind of helpfulness that hides one.
    """
    if key not in mapping:
        raise ScenarioPolicyError(f"{where}: required policy key {key!r} is missing")
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ScenarioPolicyError(
            f"{where}: {key!r} must be a number, got {type(value).__name__} {value!r}"
        )
    decimal_value = value if isinstance(value, Decimal) else Decimal(value)
    if not decimal_value.is_finite():
        raise ScenarioPolicyError(f"{where}: {key!r} must be finite, got {decimal_value}")
    return decimal_value


def _require(mapping: dict, key: str, kind: type, *, where: str):
    if key not in mapping:
        raise ScenarioPolicyError(f"{where}: required policy key {key!r} is missing")
    value = mapping[key]
    if kind is int and isinstance(value, bool):
        raise ScenarioPolicyError(f"{where}: {key!r} must be an integer, got {value!r}")
    if not isinstance(value, kind):
        raise ScenarioPolicyError(
            f"{where}: {key!r} must be {kind.__name__}, got {type(value).__name__}"
        )
    return value


def load_policy(path: Path | str | None = None) -> ScenarioPolicy:
    """Load and validate the scenario policy configuration, failing closed.

    Refuses a policy that is malformed, that omits a required key, that names a
    channel outside :data:`REGISTERED_CHANNELS`, that lists one channel twice, or
    that maps any channel to a forbidden I/O sector. A configuration file is
    infrastructure the user did not write, so a defect in it is reported as a
    :class:`ScenarioPolicyError` and never as a contract violation.
    """
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    if not policy_path.is_file():
        raise ScenarioPolicyError(f"scenario policy configuration not found: {policy_path}")
    try:
        raw = yaml.load(policy_path.read_text(encoding="utf-8"), Loader=_PolicyLoader)
    except ScenarioContractError as exc:
        raise ScenarioPolicyError(f"{policy_path}: {exc}") from exc
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        raise ScenarioPolicyError(f"{policy_path}: could not be read or parsed: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioPolicyError(f"{policy_path}: policy must be a mapping")

    where = str(policy_path)
    accepted = _require(raw, "accepted_input_schema_version", str, where=where)
    if accepted != INPUT_SCHEMA_VERSION:
        raise ScenarioPolicyError(
            f"{where}: accepted_input_schema_version is {accepted!r} but this validator "
            f"implements {INPUT_SCHEMA_VERSION!r}"
        )
    reference_year = _require(raw, "structural_reference_year", int, where=where)
    if reference_year != STRUCTURAL_REFERENCE_YEAR:
        raise ScenarioPolicyError(
            f"{where}: structural_reference_year is {reference_year} but the coefficients "
            f"are from {STRUCTURAL_REFERENCE_YEAR}"
        )

    magnitude_raw = _require(raw, "magnitude_policy", dict, where=where)
    at_magnitude = f"{where}:magnitude_policy"
    magnitude = MagnitudePolicy(
        percent_to_fraction_divisor=_require_decimal(
            magnitude_raw, "percent_to_fraction_divisor", where=at_magnitude
        ),
        increase_warn_above_fraction=_require_decimal(
            magnitude_raw, "increase_warn_above_fraction", where=at_magnitude
        ),
        increase_refuse_above_fraction=_require_decimal(
            magnitude_raw, "increase_refuse_above_fraction", where=at_magnitude
        ),
        decrease_refuse_above_fraction=_require_decimal(
            magnitude_raw, "decrease_refuse_above_fraction", where=at_magnitude
        ),
        limits_are_validation_policy=_require(
            magnitude_raw, "limits_are_validation_policy", bool, where=f"{where}:magnitude_policy"
        ),
        limits_are_learned_thresholds=_require(
            magnitude_raw, "limits_are_learned_thresholds", bool, where=f"{where}:magnitude_policy"
        ),
    )
    if magnitude.percent_to_fraction_divisor != Decimal(100):
        raise ScenarioPolicyError(f"{where}: percent_to_fraction_divisor must be 100")
    if magnitude.limits_are_learned_thresholds:
        raise ScenarioPolicyError(
            f"{where}: limits_are_learned_thresholds must be false — these bounds are declared "
            "validation policy and presenting them as estimated would be a false claim"
        )
    if not magnitude.limits_are_validation_policy:
        raise ScenarioPolicyError(f"{where}: limits_are_validation_policy must be true")
    if not 0 < magnitude.increase_warn_above_fraction <= magnitude.increase_refuse_above_fraction:
        raise ScenarioPolicyError(
            f"{where}: the increase warning threshold must be positive and no greater than the "
            "refusal ceiling"
        )
    if magnitude.decrease_refuse_above_fraction <= 0:
        raise ScenarioPolicyError(f"{where}: decrease_refuse_above_fraction must be positive")

    channels_raw = _require(raw, "channels", list, where=where)
    channels: list[ChannelPolicy] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(channels_raw):
        at = f"{where}:channels[{index}]"
        if not isinstance(entry, dict):
            raise ScenarioPolicyError(f"{at}: each channel must be a mapping")
        name = _require(entry, "channel", str, where=at)
        sector = _require(entry, "io_sector_code", str, where=at)
        label = _require(entry, "io_sector_label", str, where=at)
        if name not in REGISTERED_CHANNELS:
            raise ScenarioPolicyError(
                f"{at}: {name!r} is not a registered channel; this release recognises "
                f"{sorted(REGISTERED_CHANNELS)}"
            )
        if name in seen_names:
            raise ScenarioPolicyError(f"{at}: channel {name!r} is declared more than once")
        if sector in FORBIDDEN_IO_SECTOR_CODES:
            raise ScenarioPolicyError(
                f"{at}: I/O sector {sector!r} is not a channel in this release"
            )
        seen_names.add(name)
        channels.append(
            ChannelPolicy(
                channel=name,
                io_sector_code=sector,
                io_sector_label=label,
                scope_note=str(entry.get("scope_note", "")).strip(),
            )
        )
    if seen_names != set(REGISTERED_CHANNELS):
        missing = sorted(REGISTERED_CHANNELS - seen_names)
        raise ScenarioPolicyError(
            f"{where}: the policy must declare every registered channel; missing {missing}"
        )

    units = tuple(_require(raw, "allowed_magnitude_units", list, where=where))
    if tuple(units) != ALLOWED_MAGNITUDE_UNITS:
        raise ScenarioPolicyError(
            f"{where}: allowed_magnitude_units must be {list(ALLOWED_MAGNITUDE_UNITS)}"
        )
    directions = tuple(_require(raw, "allowed_directions", list, where=where))
    if tuple(directions) != ALLOWED_DIRECTIONS:
        raise ScenarioPolicyError(
            f"{where}: allowed_directions must be {list(ALLOWED_DIRECTIONS)}"
        )

    shared = _require(raw, "shared_io_sector_policy", str, where=where)
    if shared != "reject_scenario":
        raise ScenarioPolicyError(
            f"{where}: shared_io_sector_policy must be 'reject_scenario'; a policy that "
            "deduplicates, selects or sums shared-sector channels is not permitted"
        )

    bases = tuple(_require(raw, "supported_bases", list, where=where))
    if tuple(bases) != ("direct", "total_requirement"):
        raise ScenarioPolicyError(
            f"{where}: supported_bases must be ['direct', 'total_requirement']"
        )
    primary = _require(raw, "registered_primary_basis", str, where=where)
    if primary != "direct":
        raise ScenarioPolicyError(f"{where}: registered_primary_basis must be 'direct'")
    role = _require(raw, "total_requirement_role", str, where=where)
    if role != "structural_sensitivity_only":
        raise ScenarioPolicyError(
            f"{where}: total_requirement_role must be 'structural_sensitivity_only'"
        )
    if not _require(raw, "basis_must_be_explicit", bool, where=where):
        raise ScenarioPolicyError(f"{where}: basis_must_be_explicit must be true")
    if not _require(raw, "scenario_date_is_metadata_only", bool, where=where):
        raise ScenarioPolicyError(f"{where}: scenario_date_is_metadata_only must be true")

    extensions = tuple(_require(raw, "accepted_input_extensions", list, where=where))
    if tuple(extensions) != (".yaml", ".yml", ".json"):
        raise ScenarioPolicyError(
            f"{where}: accepted_input_extensions must be ['.yaml', '.yml', '.json']"
        )

    max_bytes = _require(raw, "max_input_bytes", int, where=where)
    min_shocks = _require(raw, "min_shocks", int, where=where)
    max_shocks = _require(raw, "max_shocks", int, where=where)
    if max_bytes <= 0 or min_shocks < 1 or max_shocks < min_shocks:
        raise ScenarioPolicyError(f"{where}: max_input_bytes and the shock bounds are inconsistent")

    return ScenarioPolicy(
        config_version=_require(raw, "config_version", str, where=where),
        accepted_input_schema_version=accepted,
        structural_reference_year=reference_year,
        accepted_input_extensions=tuple(str(item) for item in extensions),
        max_input_bytes=max_bytes,
        min_shocks=min_shocks,
        max_shocks=max_shocks,
        max_scenario_name_length=_require(raw, "max_scenario_name_length", int, where=where),
        max_note_length=_require(raw, "max_note_length", int, where=where),
        scenario_id_pattern=_require(raw, "scenario_id_pattern", str, where=where),
        scenario_date_is_metadata_only=True,
        supported_bases=tuple(str(item) for item in bases),
        registered_primary_basis=primary,
        total_requirement_role=role,
        basis_must_be_explicit=True,
        allowed_magnitude_units=tuple(str(item) for item in units),
        allowed_directions=tuple(str(item) for item in directions),
        shared_io_sector_policy=shared,
        channels=tuple(channels),
        magnitude=magnitude,
    )


# ---------------------------------------------------------------------------
# Field-level helpers
# ---------------------------------------------------------------------------


def _text(value, *, field: str, maximum: int, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ScenarioContractError(
            f"{field} must be a string, got {type(value).__name__}",
            code="bad_field_type",
            field=field,
        )
    if not allow_empty and not value.strip():
        raise ScenarioContractError(f"{field} must not be empty", code="empty_field", field=field)
    if len(value) > maximum:
        raise ScenarioContractError(
            f"{field} is {len(value)} characters; the limit is {maximum}",
            code="overlong_field",
            field=field,
        )
    return value


def _check_field_names(present: set[str], *, required: frozenset[str], optional: frozenset[str],
                       where: str) -> None:
    for name in sorted(present):
        if name in required or name in optional:
            continue
        if name in EXCLUDED_INPUT_FIELDS:
            raise ScenarioContractError(
                f"{where}: {name!r} is deliberately not part of this contract — "
                f"{EXCLUDED_INPUT_FIELDS[name]}",
                code="excluded_field",
                field=name,
            )
        raise ScenarioContractError(
            f"{where}: unknown field {name!r}; accepted fields are "
            f"{sorted(required | optional)}",
            code="unknown_field",
            field=name,
        )
    for name in sorted(required - present):
        raise ScenarioContractError(
            f"{where}: required field {name!r} is missing", code="missing_field", field=name
        )


def _scenario_date(value) -> str:
    """A calendar date, validated from the text the author wrote.

    The scenario loader hands this the original lexeme rather than a
    ``datetime.date``, so ``2026-09-04``, ``"2026-09-04"`` and ``'2026-09-04'`` are
    the same three characters-on-disk to this function and validate identically.

    Shape is checked before length so a full timestamp — ``2026-09-04T12:30:00`` — is
    refused as ``bad_scenario_date`` rather than as an overlong field. This field
    accepts a date; a time is not a near-miss on the length limit, it is the wrong
    kind of value.
    """
    field = "scenario_date"
    if not isinstance(value, str):
        raise ScenarioContractError(
            f"{field} must be an ISO calendar date written as YYYY-MM-DD, got "
            f"{type(value).__name__}",
            code="bad_scenario_date",
            field=field,
        )
    text = value
    if not _SCENARIO_DATE_PATTERN.match(text):
        raise ScenarioContractError(
            f"{field} must be an ISO calendar date, YYYY-MM-DD, got {text!r}. A date "
            "only: this field carries no time, and it selects no data",
            code="bad_scenario_date",
            field=field,
        )
    year, month, day = (int(part) for part in text.split("-"))
    try:
        date(year, month, day)
    except ValueError as exc:
        raise ScenarioContractError(
            f"{field} {text!r} is not a real calendar date: {exc}",
            code="bad_scenario_date",
            field=field,
        ) from exc
    return text


def _magnitude_decimal(value, *, field: str) -> Decimal:
    """The author's magnitude as an exact decimal, or a controlled refusal.

    A boolean is refused before the numeric check because ``bool`` is a subclass of
    ``int`` in Python: ``magnitude: true`` would otherwise be accepted as a shock of
    one, which is an authoring mistake silently turned into a calculation.

    ``float`` is refused as an input type rather than converted. Nothing upstream
    produces one — the YAML loader and the JSON parser both yield :class:`Decimal`
    for a fractional literal — so a float arriving here means a caller assembled the
    mapping by hand, and accepting it would reintroduce exactly the binary rounding
    this design removes.
    """
    if isinstance(value, bool):
        raise ScenarioContractError(
            f"{field} must be a number; a boolean is an authoring mistake, not a magnitude",
            code="magnitude_not_a_number",
            field=field,
        )
    if isinstance(value, Decimal):
        magnitude = value
    elif isinstance(value, int):
        magnitude = Decimal(value)
    elif isinstance(value, float):
        raise ScenarioContractError(
            f"{field} arrived as a binary float, which cannot represent most decimal "
            "magnitudes exactly; pass the document through the supported loader, or supply a "
            "Decimal, so the value that is validated is the value that was written",
            code="magnitude_not_a_number",
            field=field,
        )
    elif isinstance(value, str):
        raise ScenarioContractError(
            f"{field} is not a number this contract recognises: {value!r}. Write an "
            "ordinary base-10 decimal or scientific notation, as JSON would accept it "
            "— 10, 10.5, 0.001, 1e1, 1E+1, 3E-1. Hexadecimal, octal, binary, digit "
            "separators, sexagesimal, a leading '+' or '.', a trailing '.', and quoted "
            "numbers are not magnitudes",
            code="magnitude_not_a_number",
            field=field,
        )
    else:
        raise ScenarioContractError(
            f"{field} must be a number, got {type(value).__name__}",
            code="magnitude_not_a_number",
            field=field,
        )
    if not magnitude.is_finite():
        raise ScenarioContractError(
            f"{field} must be finite, got {magnitude}",
            code="magnitude_not_finite",
            field=field,
        )
    if magnitude < 0:
        raise ScenarioContractError(
            f"{field} must be non-negative; direction carries the sign, so a negative "
            "magnitude has no single reading",
            code="magnitude_negative",
            field=field,
        )
    return magnitude


def _magnitude_fraction(value, unit: str, *, policy: ScenarioPolicy,
                        where: str) -> tuple[Decimal, Decimal]:
    """Return the author's magnitude and its fraction, both exact.

    ``percent`` shifts the decimal point two places rather than dividing, which is the
    same value and, unlike division, cannot be shortened by the ambient precision. So
    ``0.1`` percent is ``0.001`` and not a value that merely rounds to it, and a long
    magnitude keeps every digit its author wrote.
    """
    field = f"{where}.magnitude"
    magnitude = _magnitude_decimal(value, field=field)
    if unit == "percent":
        divisor = policy.magnitude.percent_to_fraction_divisor
        if divisor != _PERCENT_DIVISOR:
            raise ScenarioInternalError(
                f"percent_to_fraction_divisor is {divisor}, not {_PERCENT_DIVISOR}; the policy "
                "loader refuses any other value, so reaching this means that check was bypassed"
            )
        return magnitude, scale_down_by_power_of_ten(magnitude, _PERCENT_PLACES)
    return magnitude, magnitude


def _bounds(fraction: Decimal, direction: str, *, channel: str, policy: ScenarioPolicy,
            where: str) -> ScenarioWarning | None:
    """Direction-sensitive bounds. Comparisons are exact decimal comparisons.

    "Exactly 1000%" and "exactly 100%" are accepted, and that is a statement about
    arithmetic as much as about policy: both sides are decimals built from text, so
    ``Decimal("10") > Decimal("10")`` is false for the reason a reader expects
    rather than because a binary representation happened to land the right way.
    """
    limits = policy.magnitude
    field = f"{where}.magnitude"
    if direction == "increase":
        if fraction > limits.increase_refuse_above_fraction:
            raise ScenarioContractError(
                f"{field}: an increase of {decimal_text(fraction)} as a fraction exceeds the "
                f"declared ceiling of {decimal_text(limits.increase_refuse_above_fraction)}. This "
                "is a validation limit set by the project, not an estimated threshold: a 2015 "
                "accounting ratio scaled that far stays arithmetic and stops being meaningful",
                code="magnitude_increase_above_ceiling",
                field=field,
                details={
                    "channel": channel,
                    "fraction": decimal_text(fraction),
                    "ceiling": decimal_text(limits.increase_refuse_above_fraction),
                },
            )
        if fraction > limits.increase_warn_above_fraction:
            return ScenarioWarning(
                code="extreme_increase_magnitude",
                message=(
                    f"the shock on {channel} is an increase of {decimal_text(fraction)} as a "
                    f"fraction, above the declared "
                    f"{decimal_text(limits.increase_warn_above_fraction)} warning level; the "
                    "structural coefficients are 2015 accounting ratios under fixed proportions "
                    "and no substitution, so a shock this large is outside the range in which "
                    "the linear scaling describes anything"
                ),
                field="magnitude",
                channel=channel,
            )
        return None
    if fraction > limits.decrease_refuse_above_fraction:
        raise ScenarioContractError(
            f"{field}: a decrease of {decimal_text(fraction)} as a fraction exceeds "
            f"{decimal_text(limits.decrease_refuse_above_fraction)}; a price cannot fall by more "
            "than all of itself",
            code="magnitude_decrease_above_ceiling",
            field=field,
            details={
                "channel": channel,
                "fraction": decimal_text(fraction),
                "ceiling": decimal_text(limits.decrease_refuse_above_fraction),
            },
        )
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_scenario_document(document: dict, *, policy: ScenarioPolicy) -> ValidatedScenario:
    """Validate an already-parsed scenario mapping against the policy.

    Returns an immutable :class:`ValidatedScenario` whose shocks are sorted by
    channel, so two documents that mean the same thing hash the same. Raises
    :class:`ScenarioContractError` — or :class:`UnsupportedChannelError`, which is
    one — on the first violation, with a code from :data:`CONTRACT_ERROR_CODES`.
    """
    if not isinstance(document, dict):
        raise ScenarioContractError(
            "the scenario document must be a mapping at the top level",
            code="document_not_a_mapping",
        )
    _check_field_names(
        set(document),
        required=TOP_LEVEL_REQUIRED_FIELDS,
        optional=TOP_LEVEL_OPTIONAL_FIELDS,
        where="scenario document",
    )

    schema_version = document["schema_version"]
    if schema_version != policy.accepted_input_schema_version:
        raise ScenarioContractError(
            f"schema_version must be {policy.accepted_input_schema_version!r}, got "
            f"{schema_version!r}",
            code="bad_schema_version",
            field="schema_version",
        )

    scenario_id = _text(document["scenario_id"], field="scenario_id", maximum=64,
                        allow_empty=False)
    if not re.match(policy.scenario_id_pattern, scenario_id):
        raise ScenarioContractError(
            f"scenario_id {scenario_id!r} does not match {policy.scenario_id_pattern}",
            code="bad_scenario_id",
            field="scenario_id",
        )

    scenario_name = None
    if "scenario_name" in document:
        scenario_name = _text(
            document["scenario_name"], field="scenario_name",
            maximum=policy.max_scenario_name_length, allow_empty=False,
        )
    note = None
    if "note" in document:
        note = _text(document["note"], field="note", maximum=policy.max_note_length)
    scenario_date = None
    if "scenario_date" in document:
        scenario_date = _scenario_date(document["scenario_date"])

    raw_shocks = document["shocks"]
    if not isinstance(raw_shocks, list):
        raise ScenarioContractError(
            f"shocks must be a list, got {type(raw_shocks).__name__}",
            code="bad_field_type",
            field="shocks",
        )
    if len(raw_shocks) < policy.min_shocks:
        raise ScenarioContractError(
            f"shocks must contain at least {policy.min_shocks} entry", code="no_shocks",
            field="shocks",
        )
    if len(raw_shocks) > policy.max_shocks:
        raise ScenarioContractError(
            f"shocks contains {len(raw_shocks)} entries; the limit is {policy.max_shocks}",
            code="too_many_shocks",
            field="shocks",
        )

    shocks: list[ValidatedShock] = []
    warnings: list[ScenarioWarning] = []
    seen_channels: dict[str, int] = {}
    seen_sectors: dict[str, str] = {}

    for index, raw in enumerate(raw_shocks):
        where = f"shocks[{index}]"
        if not isinstance(raw, dict):
            raise ScenarioContractError(
                f"{where} must be a mapping, got {type(raw).__name__}",
                code="shock_not_a_mapping",
                field=where,
            )
        _check_field_names(
            set(raw), required=SHOCK_REQUIRED_FIELDS, optional=SHOCK_OPTIONAL_FIELDS, where=where
        )

        channel_name = raw["channel"]
        if not isinstance(channel_name, str):
            raise ScenarioContractError(
                f"{where}.channel must be a string, got {type(channel_name).__name__}",
                code="bad_field_type",
                field=f"{where}.channel",
            )
        channel = policy.channel(channel_name)
        if channel is None:
            raise UnsupportedChannelError(
                f"{where}.channel {channel_name!r} is not a registered channel; this release "
                f"recognises {list(policy.channel_names)}",
                field=f"{where}.channel",
                details={"channel": channel_name, "registered": list(policy.channel_names)},
            )
        if channel_name in seen_channels:
            raise ScenarioContractError(
                f"{where}.channel {channel_name!r} already appears at "
                f"shocks[{seen_channels[channel_name]}]; one channel may be shocked once, and two "
                "entries for it are an authoring error rather than an instruction to add them",
                code="duplicate_channel",
                field=f"{where}.channel",
                details={"channel": channel_name},
            )
        if channel.io_sector_code in seen_sectors:
            other = seen_sectors[channel.io_sector_code]
            raise ScenarioContractError(
                f"{where}.channel {channel_name!r} and {other!r} both resolve to official I/O "
                f"sector {channel.io_sector_code} ({channel.io_sector_label}). They are the same "
                "measurement twice, so this scenario is refused rather than deduplicated, summed "
                "or silently reduced to one of them",
                code="shared_io_sector",
                field=f"{where}.channel",
                details={
                    "io_sector_code": channel.io_sector_code,
                    "channels": sorted([channel_name, other]),
                },
            )

        direction = raw["direction"]
        if direction not in policy.allowed_directions:
            raise ScenarioContractError(
                f"{where}.direction must be one of {list(policy.allowed_directions)}, got "
                f"{direction!r}",
                code="bad_direction",
                field=f"{where}.direction",
            )
        unit = raw["magnitude_unit"]
        if unit not in policy.allowed_magnitude_units:
            raise ScenarioContractError(
                f"{where}.magnitude_unit must be one of {list(policy.allowed_magnitude_units)}, "
                f"got {unit!r}. Absolute price units are refused because no base-price series "
                "ships with this repository, so there is nothing to convert against",
                code="unsupported_magnitude_unit",
                field=f"{where}.magnitude_unit",
            )

        magnitude, fraction = _magnitude_fraction(
            raw["magnitude"], unit, policy=policy, where=where
        )
        warning = _bounds(fraction, direction, channel=channel_name, policy=policy, where=where)
        if warning is not None:
            warnings.append(warning)
        if fraction == 0:
            warnings.append(
                ScenarioWarning(
                    code="zero_magnitude_no_discrimination",
                    message=(
                        f"the shock on {channel_name} has magnitude zero, so it contributes "
                        "nothing and cannot separate one industry from another"
                    ),
                    field="magnitude",
                    channel=channel_name,
                )
            )
        shock_note = None
        if "note" in raw:
            shock_note = _text(raw["note"], field=f"{where}.note", maximum=policy.max_note_length)

        # `copy_negate`, not `-fraction`: unary minus rounds to the ambient precision,
        # so a decrease could otherwise be stored shorter than the increase it mirrors.
        signed = fraction if direction == "increase" else fraction.copy_negate()
        seen_channels[channel_name] = index
        seen_sectors[channel.io_sector_code] = channel_name
        shocks.append(
            ValidatedShock(
                channel=channel_name,
                io_sector_code=channel.io_sector_code,
                direction=direction,
                magnitude=magnitude,
                magnitude_unit=unit,
                magnitude_fraction=fraction,
                signed_magnitude_fraction=signed,
                note=shock_note,
            )
        )

    shocks.sort(key=lambda shock: shock.channel)

    # Warnings are emitted in canonical channel order, then the scenario-level ones,
    # so the sequence depends on the scenario rather than on the order the author
    # happened to list the shocks in. ``list.sort`` is stable, so two warnings on one
    # channel keep the order they were raised in.
    order = {shock.channel: position for position, shock in enumerate(shocks)}
    warnings.sort(key=lambda item: order.get(item.channel, len(order)))

    if shocks and all(shock.is_zero for shock in shocks):
        warnings.append(
            ScenarioWarning(
                code="zero_magnitude_no_discrimination",
                message=(
                    "every shock in this scenario has magnitude zero, so it separates no industry "
                    "from any other; there is nothing to rank"
                ),
                field="shocks",
                channel=None,
            )
        )
    return ValidatedScenario(
        schema_version=schema_version,
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        scenario_date=scenario_date,
        note=note,
        shocks=tuple(shocks),
        warnings=tuple(warnings),
        policy_version=policy.config_version,
        structural_reference_year=policy.structural_reference_year,
        scenario_date_is_metadata_only=True,
        coefficient_vintage_is_scenario_date=False,
    )


def load_scenario_document(path: Path | str, *, policy: ScenarioPolicy) -> ValidatedScenario:
    """Read, parse and validate a scenario file.

    The extension is checked first and the size second, both before a single byte is
    parsed: a document too large to be a scenario should never reach a parser at all.
    """
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in policy.accepted_input_extensions:
        raise ScenarioContractError(
            f"{source.name}: {suffix or '(no extension)'} is not an accepted scenario format; "
            f"use one of {list(policy.accepted_input_extensions)}",
            code="unsupported_extension",
            field=str(source),
        )
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise ScenarioContractError(
            f"{source}: the scenario file could not be read: {exc}",
            code="unreadable_document",
            field=str(source),
        ) from exc
    if size > policy.max_input_bytes:
        raise ScenarioContractError(
            f"{source.name} is {size} bytes; the declared limit is {policy.max_input_bytes}. "
            "The file was not parsed",
            code="input_too_large",
            field=str(source),
            details={"size": size, "limit": policy.max_input_bytes},
        )
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScenarioContractError(
            f"{source}: the scenario file could not be read as UTF-8 text: {exc}",
            code="unreadable_document",
            field=str(source),
        ) from exc
    return validate_scenario_document(_parse_document_text(text, suffix=suffix), policy=policy)


# ---------------------------------------------------------------------------
# Canonical form
# ---------------------------------------------------------------------------


def canonical_scenario_payload(scenario: ValidatedScenario) -> dict:
    """The semantic content of a scenario, in a form that hashes deterministically.

    Excludes the source path and anything from the run: a scenario is the same
    scenario whichever file it arrived in and whenever it was read. Excludes the raw
    ``magnitude`` and ``magnitude_unit`` too, keeping only the signed fraction they
    normalise to, so ``30`` percent and ``0.30`` fraction are one scenario rather
    than two. Both raw values remain on :class:`ValidatedShock` for display.
    """
    return {
        "schema_version": scenario.schema_version,
        "scenario_id": scenario.scenario_id,
        "scenario_name": scenario.scenario_name,
        "scenario_date": scenario.scenario_date,
        "note": scenario.note,
        "shocks": [
            {
                "channel": shock.channel,
                "direction": shock.direction,
                "signed_magnitude_fraction": decimal_text(shock.signed_magnitude_fraction),
                "note": shock.note,
            }
            for shock in sorted(scenario.shocks, key=lambda item: item.channel)
        ],
    }


def canonical_input_sha256(scenario: ValidatedScenario) -> str:
    """SHA-256 over the canonical payload, as compact sorted-key JSON.

    The payload carries magnitudes as canonical decimal *strings*, so nothing is
    serialised through a binary float on the way to the digest. ``json.dumps``
    cannot encode a :class:`Decimal` at all, which means this property fails loudly
    rather than silently if a later change puts one in the payload.
    """
    text = json.dumps(
        canonical_scenario_payload(scenario),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
