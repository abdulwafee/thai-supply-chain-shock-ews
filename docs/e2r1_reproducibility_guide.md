# Reproducibility guide — Task E2-R1

This repository is released as a reproducible **source-checkout** research
project. Standalone wheel or PyPI installation is not currently supported,
because several audit modules intentionally resolve repository-level evidence
and configuration paths.

**Python 3.12 is the supported floor and the only tested version.** Both
dependency locks were regenerated and verified on it. Metadata permits 3.13 and
later to install; nothing here has been run on them, so nothing here says they
work.

Three tiers, in order of what they cost and what they prove. The locked final
test is excluded from all three: it is sealed and unopened, and no tier reaches
it.

---

## Tier 1 — code verification

**What it proves:** the published files install from the lock contract on their
own, import, lint, pass the hermetic test suite, and parse every configuration
and schema.

**What it does not prove:** anything about the data. No official download is
fetched and no generated table is rebuilt.

- **Network:** needed once, to clone and to install the pinned dependencies.
- **Storage:** about 15 MiB for the tree, plus roughly 300 MiB for the virtual
  environment — pandas, numpy, pyarrow and matplotlib carry large binary wheels.
- **Time:** a few minutes, most of it installing.

### Linux and macOS

```bash
git clone <repository-url> thai-supply-chain-ews
```

```bash
cd thai-supply-chain-ews && python3.12 -m venv .venv
```

```bash
.venv/bin/python -m pip install -r requirements.lock.txt -r requirements-dev.lock.txt
```

```bash
.venv/bin/python -m pip install --no-deps -e .
```

```bash
.venv/bin/python -m pytest -q
```

### Windows (PowerShell)

```bash
py -3.12 -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt -r requirements-dev.lock.txt
```

```bash
.venv\Scripts\python.exe -m pip install --no-deps -e .
```

```bash
.venv\Scripts\python.exe -m pytest -q
```

**`--no-deps` is deliberate and load-bearing.** The locks already fixed every
version, including transitive ones. A project install that re-resolves them is
not installing from the lock, and the environment you end up with is not the one
anything was verified against.

**`-e` is also deliberate.** This project's configurations, mapping tables,
documentation and evidence artifacts live in the repository, not inside a wheel,
and fifteen modules locate them beside the source tree. An editable install
points the package at the checkout, which is the only arrangement in which those
paths resolve.

**Expected result:** the suite passes, with the data-backed tests skipped by
name and with a reason. The exact numbers move as tests are added; they are
measured from pytest's own summary line rather than quoted, and the current
figures are in `docs/e2r1_source_release_decision.md`.

### What the skips mean

`tests/conftest.py` skips the tests listed in `tests/data_backed_tests.txt`
**only when the local inputs are actually absent**, decided by looking at the
filesystem rather than at a flag. In a full working tree nothing is skipped and
every test runs.

A skipped test is reported as skipped and never folded into the passing total:
"did not run" and "passed" are different facts, and only one of them is
evidence. The registry itself is verified on every release run by removing it
and requiring that every entry fails without it, that nothing else fails, and
that every failure names a missing input.

---

## Tier 2 — source audit reproduction

**What it proves:** the official documents this project used can be re-fetched,
that their checksums match what was recorded at retrieval time, that the
archives parse, and that the source-layer transformations reproduce.

**What it does not prove:** anything about model performance.

- **Network:** required. Four publishers, listed in `DATA_SOURCES.md`.
- **Storage:** about 110 MiB of downloads on top of tier 1.
- **Time:** dominated by the EPPO archive — 1,336 weekly price-structure
  workbooks.

Set the project root, which this project never guesses:

```bash
export THAI_SUPPLY_CHAIN_EWS_ROOT=/absolute/path/to/thai-supply-chain-ews
```

On Windows PowerShell:

```bash
$env:THAI_SUPPLY_CHAIN_EWS_ROOT = "D:\path\to\thai-supply-chain-ews"
```

`.env.example` documents the variable. Nothing loads a `.env` file
automatically, so export it in your shell.

Then run the acquisition scripts under `scripts/` and verify each downloaded
file against the `sha256` recorded for it in `data/raw/_manifests/*.jsonl`.

**A checksum mismatch is a finding, not a failure to work around.** It means the
publisher revised the file after this project retrieved it, and that is worth
recording — silently accepting the new bytes would erase the only evidence that
the input changed.

With the downloads in place, the data-backed tests stop skipping and the full
suite runs with nothing skipped.

---

## Tier 3 — full historical development reproduction

**What it proves:** the feature build, the development walk-forward evaluations
(B4, D1, D3, D4, D5) and the E1 evidence ledger reproduce from tier 2's outputs.

**What it does not prove:** anything about the locked final test, which stays
sealed.

- **Network:** required (tier 2 first).
- **Storage:** about 130 MiB total.
- **Time:** hours, dominated by the walk-forward evaluations.

Run the task runners in order — `scripts/run_b1_*` through `scripts/run_e1_*` —
each of which takes no arguments and exposes no flag that could reach a locked
origin. Their results carry content checksums, and the release runners re-check
those checksums before doing anything else.

---

## Why the wheel is not the answer

`python -m build` produces a wheel and an sdist, and CI builds them on every
run. They are **diagnostic artifacts**: they exist so their contents can be
audited — no raw data, no generated tables, no locked-test members — and they
are not deliverables.

An installed distribution contains the Python package and nothing else. The
`configs/`, `docs/` and `data/mapping/` trees are repository content rather than
package data, and fifteen modules locate them relative to the source tree, so an
isolated installed distribution imports but cannot resolve project resources.
Making the distribution self-contained is a packaging change with its own test
surface; it has not been done, and it is the reason PyPI publication is not
supported.

---

## What is not deterministic, and why

- **Archive member timestamps** in the diagnostic wheel and sdist. Both formats
  record a build clock, so two builds produce identical member sets and
  identical file content but not identical archive bytes.
- **Retrieval timestamps** in the acquisition manifests. `retrieved_at` records
  when a file was fetched, which is information about the fetch and not about
  the file. Content checksums exclude it.
- **Generation timestamps** are absent from the shipped release documents
  altogether. A timestamp inside a released document would make the release
  manifest checksum differ on every run, and a manifest that changes when
  nothing changed cannot tell anyone whether anything changed. The run date is
  recorded once, by hand, in `docs/e2r1_release_checklist.md`.

## The dependency locks

`requirements.lock.txt` and `requirements-dev.lock.txt` pin exact versions,
resolved in a pristine Python 3.12 virtual environment and recorded from what
was actually installed there. Each header names the interpreter, the platform
and the resolver.

This is a **platform-scoped lock, not a universal one.** pandas, numpy, pyarrow
and matplotlib ship platform-specific binary wheels, so the files pin versions
rather than guaranteeing an identical byte-for-byte environment elsewhere.

## Verifying what you received

`docs/e2r1_release_manifest.json` lists every released file with its SHA-256. It
does not list itself or the two decision documents, because all three quote the
manifest checksum and a manifest covering them could never reach a fixed point —
the same reason a checksum-list file omits itself.
