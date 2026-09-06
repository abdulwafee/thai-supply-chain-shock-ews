# Running structural exposure scenarios

`python -m thai_supply_chain_ews.scenario` answers one question: **if a named upstream
commodity price moved by a stated amount, which of the twelve Thai manufacturing industry
groups are most structurally exposed to that move, according to the published 2015
input-output accounting ratios?**

It is an accounting comparison, not a prediction. What that means precisely is in
[What the numbers are not](#what-the-numbers-are-not), and the tool repeats it in every
document it writes.

## Prerequisites

Run it from a source checkout. The package is **not published to PyPI**, and a standalone
wheel install is not supported, because the command resolves repository-level artifacts and
configuration relative to the checkout. Python **3.12 or newer** is required.

Set the environment up as described in the README's *Setup* section, then run the module.
Examples below use the Windows interpreter path; on Linux and macOS substitute
`.venv/bin/python`.

## The four commands

| command | what it does | reads artifacts? | writes a file? |
| --- | --- | --- | --- |
| `validate` | checks a scenario document against the input contract | no | no |
| `run` | scores the scenario and ranks every industry | yes | yes, unless `--output -` |
| `explain` | shows one industry's channel contributions and their published mediators | yes | yes, unless `--output -` |
| `interactive` | builds one scenario from numbered prompts, then runs it | yes, after you confirm | only if you choose a file |

`validate` computes nothing and opens no exposure artifact. It is the cheap way to check a
document you just wrote.

The three file-based commands remain the recommended interface for automation and for
committed reproducibility: a scenario file can be reviewed, diffed, committed and re-run
byte-for-byte later, and `interactive` produces no such record of its own.

### Arguments

- `validate` requires `--input`.
- `run` requires `--input`, `--basis`, `--format` and `--output`.
- `explain` requires those four plus `--industry`, and accepts `--all`.
- `interactive` takes no arguments at all: every choice is a prompt.

**No argument has a default.** In particular `--basis` must be stated every time: the two
bases answer different questions, and picking one silently would make the answer depend on a
default nobody chose.

### `--help` reads nothing

`--help` on the root command or any subcommand builds the parser and exits. It opens no
exposure artifact, no policy file and no scenario document, so it is safe to run in a
checkout where those are absent:

```text
python -m thai_supply_chain_ews.scenario --help
python -m thai_supply_chain_ews.scenario validate --help
python -m thai_supply_chain_ews.scenario run --help
python -m thai_supply_chain_ews.scenario explain --help
python -m thai_supply_chain_ews.scenario interactive --help
```

## Copyable examples

Three validated scenarios are committed under [`examples/scenarios/`](../examples/scenarios).
Each is a small YAML document you can copy and edit.

```powershell
# 1. Check the document. Computes nothing, writes nothing.
.venv\Scripts\python.exe -m thai_supply_chain_ews.scenario validate `
  --input examples/scenarios/crude_oil_price_increase.yaml

# 2. Score it on the registered primary basis, printing JSON to the terminal.
.venv\Scripts\python.exe -m thai_supply_chain_ews.scenario run `
  --input examples/scenarios/crude_oil_price_increase.yaml `
  --basis direct --format json --output -

# 3. The same scenario on the structural-sensitivity basis, written as Markdown.
.venv\Scripts\python.exe -m thai_supply_chain_ews.scenario run `
  --input examples/scenarios/crude_oil_price_increase.yaml `
  --basis total_requirement --format markdown --output crude_total.md

# 4. Why one industry ranks where it does, with its published mediators.
.venv\Scripts\python.exe -m thai_supply_chain_ews.scenario explain `
  --input examples/scenarios/crude_oil_price_increase.yaml `
  --basis total_requirement --industry IND-04 --format markdown --output -
```

The other two examples are `rubber_price_decrease.yaml` (a single decrease, which produces
relief rather than stress) and `multi_commodity_shock.yaml` (three channels at once, which
demonstrates cancellation and per-pair exclusions).

## Writing a scenario document

A scenario is YAML or JSON with a fixed shape:

```yaml
schema_version: structural_exposure_scenario_v1
scenario_id: crude-oil-price-increase
scenario_name: Brent crude sustained +30%
scenario_date: 2026-09-04
shocks:
  - channel: brent_crude_usd_bbl
    direction: increase
    magnitude: 30
    magnitude_unit: percent
```

`direction` is `increase` or `decrease`; `magnitude_unit` is `percent` or `fraction`.
A magnitude above 100% warns; an increase above 1000% or a decrease above 100% is refused —
a price cannot fall by more than all of itself.

**Validation is strict and fails closed.** An unknown field is refused rather than ignored,
at the top level and inside every shock, because a silently dropped field is a scenario you
think you ran and did not. Numbers are parsed as exact decimals, never through binary
floating point. The accepted shape is described in
[`schemas/scenario_input.schema.yaml`](../schemas/scenario_input.schema.yaml), which is
checked against the validator by test so the two cannot drift apart while both look correct.

`scenario_date` is **metadata only**. It records when you wrote the document. It does not
select a coefficient vintage — the coefficients are the published 2015 input-output ratios
regardless of what date you put here, and the result document says so in
`scenario_date_is_metadata_only` and `coefficient_vintage_is_scenario_date`.

## The four registered channels

Only these four commodity channels exist. Anything else is refused.

| channel | I/O sector | sector label |
| --- | --- | --- |
| `brent_crude_usd_bbl` | `031` | Petroleum and natural gas |
| `aluminum_usd_mt` | `107` | Non-ferrous metal |
| `copper_usd_mt` | `107` | Non-ferrous metal |
| `rubber_rss3_usd_kg` | `095` | Rubber sheet and block rubber |

Each mapping is coarser than the price it carries, and the result document repeats the scope
note for every channel you use. Sector `031` covers crude petroleum *and* natural gas, so a
Brent price is priced against a coefficient that embeds gas use. `095` covers block rubber
and crepe as well as RSS3. That is a property of the official accounts, not something the
tool can refine.

### Aluminium and copper cannot appear together

Both map to sector `107`, so they are **identical by construction** in these accounts and are
never independent evidence. A scenario naming both is refused outright rather than scored
with a warning, because the two shocks would be double-counting one coefficient. Score them
in separate scenarios and compare the results yourself.

## Choosing a basis

| basis | what it is | status |
| --- | --- | --- |
| `direct` | the industry's direct purchases of the commodity's sector | **registered primary basis** |
| `total_requirement` | direct purchases plus everything drawn in through intermediates | structural sensitivity only |

`total_requirement` does **not** replace `direct`. It answers a wider question — how much of
the commodity an industry ultimately embodies once the supply chain is unwound — and the
result document labels its role explicitly so a reader cannot mistake it for the registered
figure. When `total_requirement` is selected, the result also decomposes each figure into a
direct and a propagated component.

### Why a crude scenario looks empty on the `direct` basis

Running `crude_oil_price_increase.yaml` with `--basis direct` ranks only two industries above
zero. The other ten have net exposure of **exactly zero** and share **competition rank 3**,
all reported as `neutral` with a null cancellation ratio.

That is an honest structural result, not a ranking defect. Factories do not buy crude oil
across the factory gate; they buy refined fuel, electricity, petrochemicals and transport.
Ten of the twelve industries publish an observed-zero *direct* coefficient for crude. On the
`total_requirement` basis the same scenario separates all twelve, because the exposure
arrives through those intermediates. Both answers are correct and they answer different
questions — which is exactly why `--basis` has no default.

## Output

`--format json` produces the machine-readable document described by
[`schemas/scenario_result.schema.yaml`](../schemas/scenario_result.schema.yaml).
`--format markdown` produces the same content as a report you can read or paste into a
document. Every number in the JSON is a **string**, never a JSON float, so no value is
serialised through binary floating point on its way to a reader.

`--output -` writes to standard output. Any other value is a file path.

Standard output carries **UTF-8 bytes with LF line endings on every supported platform**,
including Windows. Those bytes are exactly the bytes the same invocation would write with
`--output <path>`, so redirecting in a shell -- `> result.json` on Windows included --
produces the same verifiable document, and a checksum taken over the pipe matches a
checksum taken over the file. Only the document goes to standard output; diagnostics go
to standard error, which carries no cross-platform byte guarantee.

### An existing output path is never overwritten

File output uses exclusive creation. If the destination already exists — as a file, a
directory or a symlink — the command refuses with exit code **7** and leaves the existing
bytes and modification time untouched. There is no `--force`, no `--overwrite` and no bypass
flag of any kind. Choose a new path, or delete the old one yourself.

### Deterministic and reproducible

The same scenario, basis and format produce **byte-identical** output every time. There is no
timestamp, run identifier, hostname, username or absolute path anywhere in a result document.
Listing the shocks in a different order changes nothing, because the contract sorts them
canonically before scoring. All arithmetic is exact decimal with precision derived from the
operands, so results do not depend on the decimal settings of whatever program is embedding
the package. Rendered text is LF-terminated, and stays LF-terminated through both output
transports -- a file and standard output produce identical bytes.

### Pinned artifacts, offline

The command reads a **closed set of four** published artifacts, each pinned by a
`canonical_lf` SHA-256 digest declared in
[`configs/structural_exposure_scenario.yaml`](../configs/structural_exposure_scenario.yaml):
the commodity exposure matrix, the structural path audit, the price-stage source audit and
the industry map. Every one is verified against its digest before use, and their digests are
reproduced in the result document so a reader can confirm which bytes produced which number.

There is no unpinned fallback, no regeneration path, no cache, no network access and no
discovery of alternative files. If an artifact is missing or its digest does not match, the
command fails rather than proceeding with something else.

## `explain`

`explain` takes one industry and shows, per channel, the coefficient used, the contribution
it produced, and the published structural mediators behind it — the intermediate sectors
through which the exposure travels.

By default it shows the **top 5** mediators per channel. `--all` shows all **10** published
rows. The default list is exactly the first five of the full list; nothing is summarised,
reordered or interpolated, and the rows are the pinned artifact's own in its own rank order.

Mediator rows are **corroboration, not causation**. They say which intermediate sector the
accounting runs through, not that a price moved because of it.

## `interactive`

`interactive` asks numbered questions and builds one scenario from the answers. It exists
for people working in a terminal who do not want to write YAML first; it is a convenience
layer over the same contract, not a second engine.

```text
python -m thai_supply_chain_ews.scenario interactive
```

On Windows, in either `cmd.exe` or PowerShell:

```text
py -m thai_supply_chain_ews.scenario interactive
```

### A representative session

Questions and the review summary go to **standard error**; only the finished document goes
to standard output. Answers are typed after each prompt.

```text
Thai Supply Chain Shock EWS - Interactive Scenario
Answer the numbered prompts. Enter q at any question to cancel.

Scenario ID: brent-plus-30
Scenario name (optional; Enter to omit):
Scenario date YYYY-MM-DD (optional; Enter to omit):

Select commodity / เลือกสินค้า:
  1. Brent crude oil  (brent_crude_usd_bbl)
  2. Aluminium        (aluminum_usd_mt)
  3. Copper           (copper_usd_mt)
  4. Rubber RSS3      (rubber_rss3_usd_kg)
Choice: 1
Select direction / เลือกทิศทาง:
  1. Increase  (increase)
  2. Decrease  (decrease)
Choice: 1
Magnitude: 30
Select unit / เลือกหน่วย:
  1. Percent   (percent)
  2. Fraction  (fraction)
Choice: 1

Add another shock? [y/n]: n

Select calculation basis / เลือกฐานการคำนวณ:
  1. Direct             (direct)
  2. Total requirement  (total_requirement)
Choice: 1

Select output format / เลือกรูปแบบผลลัพธ์:
  1. JSON      (json)
  2. Markdown  (markdown)
Choice: 2

Select output destination / เลือกปลายทาง:
  1. Terminal  (terminal)
  2. New file  (file)
Choice: 1

Review / ตรวจทาน:
  scenario_id            brent-plus-30
  scenario_name          (omitted)
  scenario_date          (omitted)
  schema_version         structural_exposure_scenario_v1
  canonical_input_sha256 9c898d63...
  shocks                 1
  brent_crude_usd_bbl    increase 30 percent -> 0.3
  warnings               0
  basis                  direct
  format                 markdown
  output                 terminal (stdout)

Run this scenario? [y/n]: y
```

The identifier is always printed beside the friendly name, so the value that lands in the
document is visible and can be copied into a scenario file later.

### Prompts are stderr, the document is stdout

Because the two streams are separated, the report can be redirected on its own while the
questions stay on screen:

```text
python -m thai_supply_chain_ews.scenario interactive > result.md
```

`result.md` contains the report and nothing else — no prompt, no menu, no review summary.

### The same contract, in memory

The answers are assembled into an ordinary scenario mapping and submitted to the same
public validator a scenario file goes through. No temporary YAML or JSON file is written,
nothing bypasses the contract, and no rule is relaxed because a person is typing: a
scenario that would be refused in a file is refused here, with the same message.

After you confirm, the validated scenario takes the identical path a file-based `run`
takes — the same pinned artifacts, the same exact-decimal calculation, the same result
schema check, the same renderer and the same output writer. **An interactive run and the
equivalent `run --input <file>` produce byte-identical output**, including UTF-8 encoding
and LF line endings on Windows, and including the equality between `--output -` bytes and
`--output <path>` bytes described under [Output](#output).

### What it will not decide for you

- The **scenario ID** is asked; it is never invented.
- The **scenario date** is optional and is never filled in with today's date. A scenario
  date is metadata you assert, and inventing one would put a claim in the record that
  nobody made.
- The **basis**, **format** and **destination** are each asked. Nothing is defaulted, for
  the same reason the flags have no defaults.
- A magnitude is read as an exact decimal in the same numeric language a scenario file
  accepts, and never passes through binary floating point.
- Two channels that resolve to one official sector — aluminium and copper both map to
  `107` — are refused at the prompt, so you can choose again before anything is computed.
- A duplicate commodity is refused and re-asked.

Invalid menu choices, identifiers, dates, magnitudes and yes/no answers are re-asked with
a one-line explanation, so a typo costs one line rather than the whole session.

### Cancelling

`q` or `quit` at any question, `n` at the final confirmation, or end of input all cancel.
A cancelled session exits **`8`**: no exposure artifact is loaded, nothing is calculated
and no file is created. Ctrl+C ends the session with exit **`130`**, the conventional
status for an interrupted command, with no traceback and no partial output.

Nothing is read or written before you answer `y` at the review step. Choosing a file
destination does not create the file while you are still answering questions, and an
existing path is refused exactly as it is for `run` — exit `7`, with the file on disk
untouched.

One invocation builds and runs one scenario. There is no loop that keeps asking.

### When to use a file instead

Use a scenario file for anything that must be repeated, reviewed or automated. A committed
document is the record of what was asked; an interactive session leaves none of its own.
The review summary prints the same `canonical_input_sha256` a file-based scenario would
have, so a scenario built here can be written into a file later and confirmed identical.


## Reading a result

**Net exposure** is signed. A positive figure means the shock pushes toward cost stress for
that industry; a negative figure means relief. The sign follows from the direction you
specified and the published direction sign of the pair.

**Direction label** is one of `stress_pressure`, `relief_pressure` or `neutral`. `neutral`
means the net figure is exactly zero, not that it is small.

**Relative exposure index** is signed and scaled so the largest absolute net exposure in the
run is 100. It is a within-run comparison. An index of 50 means *half the largest exposure in
this scenario*, not half of anything absolute, and indexes are not comparable between
scenarios.

**Ranks are competition ranks.** Tied industries share a rank and the next rank skips
accordingly, so three industries tied at rank 3 are followed by rank 6. Ties are compared
against a group anchor with a tolerance of `1e-12`, so near-equalities cannot chain into one
undifferentiated block. Within a tie group, industries are ordered by identifier — that is
presentation order only and carries no ranking meaning.

**Direct and propagated components** appear when `--basis total_requirement` is selected.
They satisfy `direct + propagated = net` exactly, by construction: the propagated part is
derived as total minus direct rather than read from the artifact's own `indirect_exposure`
field, which disagrees with that identity by up to 6e-17 because it was written by float64
arithmetic. The published field is preserved in the output as a fact; it is not what the
arithmetic uses.

**Gross absolute contribution** is the sum of the absolute channel contributions.
**Cancellation** is `gross - |net|`: how much opposing movement the net figure absorbed. The
**cancellation ratio** is that amount over gross, between 0 and 1, and is null when gross is
zero. A ratio near zero means the channels pushed the same way; a large ratio means a small
net figure is hiding two large opposing movements, and the net alone would mislead you.

**Exclusions** are per-pair and are listed with a stable reason:
`direction_sign_unresolved` (the published direction sign is missing, so the contribution
cannot be signed), `pair_not_feature_eligible`, or `pair_not_published`. An excluded pair is
**excluded, never treated as zero** — a coefficient that cannot be signed is not the same as
a coefficient of zero.

**Unscorable industries** are listed separately and are **not ranked**. An industry becomes
unscorable when every one of its pairs was excluded. Ranking it at zero would state that it
has no exposure, when the truth is that its exposure could not be determined.

If nothing can be ranked at all, the result says so with a reason — `all_magnitudes_zero` or
`all_net_exposures_zero` — rather than emitting an arbitrary order.

**Input warnings** are carried on the result: `zero_magnitude_no_discrimination` (a zero
magnitude contributes nothing and cannot separate one industry from another) and
`extreme_increase_magnitude`.

## Exit codes

| code | meaning |
| --- | --- |
| `0` | success |
| `1` | internal error — an invariant the implementation guarantees did not hold |
| `2` | usage error — a missing or invalid argument, no command given, or an unwritable output parent |
| `3` | the scenario document violated the input contract |
| `4` | an artifact or policy problem — a failed digest, a missing pinned artifact, or an invalid policy |
| `5` | the scenario named a channel that is not registered |
| `6` | the scenario is contract-valid but has no scorable pair |
| `7` | the output path already exists; nothing was written or overwritten |
| `8` | an interactive session was cancelled; nothing was read, computed or written |
| `130` | an interactive session was interrupted with Ctrl+C |

Foreseen failures print a one-line `error:` message to standard error and return one of these
codes. No traceback is ever printed to a user for a foreseen failure.

Codes `0`-`7` mean exactly what they meant in v1.2.1, for every command including
`interactive`. Cancellation has its own code precisely so that a script cannot mistake a
session somebody stopped for a calculation that finished: exit `8` means no artifact was
read, nothing was computed and no file was created.

## What the numbers are not

Every document this tool writes carries the same boundary, and it is worth stating plainly
here too. A result is a **conditional structural exposure comparison** computed from
published accounting ratios. It is:

- **not a probability** — nothing here estimates how likely any price move is
- **not a forecast** — no time dimension, no prediction of what will happen
- **not a predicted percentage change in production** — the figure is an exposure ratio, not an output response
- **not a causal effect** — accounting shares are not elasticities
- **not a risk band** — no threshold, tier or rating is assigned
- **not an investment or production recommendation**

No model is trained, loaded or consulted. The locked final test remains sealed. Results are
industry-group level; there is no company-level cascade, and no industry-to-industry
propagation beyond what the published total-requirement coefficients already contain.

## Related

- [`docs/methodology.md`](methodology.md) — method summary and the documents behind it
- [`schemas/scenario_input.schema.yaml`](../schemas/scenario_input.schema.yaml) — the accepted input shape
- [`schemas/scenario_result.schema.yaml`](../schemas/scenario_result.schema.yaml) — the result and explanation documents
- [`configs/structural_exposure_scenario.yaml`](../configs/structural_exposure_scenario.yaml) — channel registry, pinned artifacts and magnitude policy
- [`examples/scenarios/`](../examples/scenarios) — the three committed examples
- [`docs/c3_commodity_exposure_matrix.md`](c3_commodity_exposure_matrix.md) — how the exposure matrix was built
- [`docs/c5_structural_path_audit.md`](c5_structural_path_audit.md) — the mediator rows `explain` reports
