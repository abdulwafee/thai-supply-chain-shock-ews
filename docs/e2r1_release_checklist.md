# Source-release checklist — Task E2-R1

**Run date: 2026-08-31.** The one hand-maintained date in the release record.
The generated documents carry no generation timestamp, because a timestamp
inside a released document would make the release-manifest checksum differ on
every run.

**Supersedes the Task E2 release decision.** It does not replace E2's evidence:
E2's blocked status, its missing-licence finding, its original interpreter
expectation and the correction that followed are pinned by checksum and
re-verified before this task does anything.

Nothing was published. No commit, no tag, no push, no GitHub repository, no PyPI
upload, no release.

---

## The three owner decisions, applied

- [x] **Code licence: MIT.** `LICENSE` created with
      `Copyright (c) 2026 Thai Supply Chain Shock EWS contributors`. Packaging
      metadata declares the SPDX expression `MIT` and `license-files`; the
      placeholder `Unlicensed - student portfolio project` is gone. No
      deprecated OSI classifier was added — under PEP 639 an SPDX expression
      supersedes it and setuptools 77+ rejects both together.
- [x] **Release scope: public GitHub source checkout.** Supported install is a
      clone plus an editable install from the locks. The wheel and sdist are
      built for content inspection and labelled diagnostic artifacts; neither is
      a supported runtime, and both are excluded from the release manifest.
- [x] **Python floor: 3.12.** Applied to packaging metadata, the ruff target,
      both regenerated locks, CI, the README and the reproducibility guide, and
      verified by reading all seven and comparing them.

## The licence, and what it does not cover

- [x] The MIT grant covers this project's own code and documentation:
      `src/`, `scripts/`, `tests/`, `configs/`, `schemas/`, `docs/`,
      `data/mapping/` and the retrieval manifests.
- [x] It grants nothing in World Bank, NESDC, OIE or EPPO material. `LICENSE`
      says so in its own scope section, and a guard raises on any sentence in a
      released document that extends the grant to third-party data.
- [x] No third-party raw byte is in the release, so there is nothing to
      mislicense. Their terms remain the publishers' to state, and remain
      unresolved where they are unresolved.

## Citation

- [ ] `CITATION.cff` **not created**, deliberately. It requires a verified
      personal author and none is available. Packaging metadata uses the
      collective attribution `Thai Supply Chain Shock EWS contributors` rather
      than a fabricated individual, and no name, email, ORCID or affiliation was
      invented. This is a documented non-blocking limitation, not a blocker: a
      source-checkout release does not require citation metadata, and a citation
      file naming a person who has not approved it would be worse than none.

## What was verified

### Supersession

- [x] Seven E2 artifacts pinned by SHA-256 and re-checked before anything else.
      A mismatch stops the run.
- [x] Eight upstream scientific result artifacts re-checked against the content
      checksums they declare. Applying an owner decision changes no scientific
      conclusion.

### The Python contract

- [x] `requires-python = ">=3.12"`; ruff `target-version = "py312"`; both lock
      headers record CPython 3.12; CI uses 3.12; README and the reproducibility
      guide lead with 3.12.
- [x] Every pin's declared `Requires-Python` admits 3.12 — including
      `numpy==2.5.2`, the pin that made 3.11 impossible.
- [x] No active claim that 3.11 is supported survives. The *record* that E2
      expected it, and that it was found incompatible, is preserved.
- [x] 3.13 and later are permitted by metadata and are **not** claimed as
      tested. Permitted is not tested.

### Dependencies

- [x] Both locks regenerated in a pristine Python 3.12 environment; resolver
      version recorded in each header.
- [x] Runtime and development locks separated; transitive requirements pinned.
- [x] `pypdf` remains declared. `python-dotenv` remains removed — nothing
      imports it.
- [x] Direct dependencies match the imports found by an AST scan; `pyarrow` and
      `xlrd` remain the two documented justified declarations.
- [x] Clean installation uses the lock contract only: `--no-deps` on the project
      install, so nothing re-resolves what the locks fixed.

### Clean source-checkout verification

- [x] A fresh isolated tree built from the fail-closed allowlist, on **CPython
      3.12.14**: fresh environment, locked runtime and development installs,
      editable source install, every public module imported, hermetic suite,
      ruff, every config and schema parsed, CLI smoke checks, documentation
      links resolved.
- [x] Hermetic suite there: **1,653 passed, 297 skipped, 0 failed**. Full
      working-directory suite: **1,925 passed, 25 skipped** — the skips are the
      Task E2 report assertions, which describe the tree as it was under E2 and
      are guarded by checksum instead.
- [x] Release-tree checksum **identical before and after** the test run.
- [x] Collected, passed, skipped, failed, install duration and test duration are
      all measured from the commands themselves and recorded in
      `e2r1_source_release_decision.json`.
- [x] Re-running the superseded E2 runner is **refused**: it would overwrite a
      record E2-R1 pinned. A supersession promise that depends on nobody
      happening to run the old script is not a guarantee.

### Allowlist

- [x] Fail-closed: an unmatched path is excluded and reported, never admitted.
      **1,920 files on disk; 452 admitted, 449 of them hashed** in the manifest —
      the three E2-R1 review documents ship but are not rows, because each quotes
      the manifest checksum. **0** paths fell through the fail-closed rule.
- [x] Includes `LICENSE`, source, hermetic tests and fixtures, configurations,
      schemas, portfolio and closeout documentation, both locks, the CI
      workflow, third-party notices, the reproducibility guide and this
      decision.
- [x] Excludes wheels and sdists, `dist/` and `build/`, raw third-party
      documents, generated Parquet, predictions and models, caches and
      environments, locked outcomes, local credentials and absolute paths, and
      anything whose redistribution status is unresolved.

### Security and licence re-verification

- [x] Secret and privacy scan over the new allowlist; absolute-path scan; both
      locks audited for vulnerabilities; diagnostic package contents inspected;
      raw-data and locked-path exclusion confirmed; licence consistency checked;
      third-party notices cover every pinned distribution. **0 credential
      findings, 0 absolute-path findings, 0 unreviewed findings, 0 dependency
      advisories.**
- [x] **155** released documents checked by the language guards: **0** claims
      extending MIT to third-party data, presenting the wheel as a runtime, or
      asserting `Python 3.11 is supported`. (Backticked, because the guard
      strips quoted spans — which is what lets this line name the rule it is
      reporting on.) **98** relative documentation links resolve.
- [x] No locked outcome was opened, hashed or handed to a scanner.
- [x] The MIT licence is not attributed to any third-party dataset.

### Continuous integration

- [x] Python 3.12; installs from the regenerated locks; editable source-checkout
      install; hermetic tests only; the data-backed tier reported separately
      rather than pretended to have passed; ruff; config and schema validation;
      worktree cleanliness after the run.
- [x] Actions pinned to commit SHAs; `permissions: contents: read`; no
      repository secret; no official data, purge data or locked outcome; no
      publication step.
- [x] No active Python 3.11 reference remains in the workflow.

---

## Documented non-blocking limitations

Each names something that was **not** done or **not** verified. None is a
finding that was talked out of being one.

1. **`citation_metadata_deferred`** — no `CITATION.cff` while the owner's
   identity is unverified.
2. **`standalone_distribution_not_supported`** — fifteen modules resolve
   repository resources through paths relative to the source tree, so the wheel
   installs and imports but cannot reach configs, docs or mapping tables. No
   refactor was performed and none was authorised. This limitation is
   **blocking for a PyPI release** and is exactly why PyPI publication is
   neither supported nor authorised; it is **not** blocking for the
   source-checkout scope the owner chose.
3. **`python_311_not_supported`** — 3.12 is the floor and the only tested
   version.
4. **`data_backed_reproduction_requires_external_official_files`** — the
   registered data-backed tests need official downloads and are skipped, by
   name and with a reason, when those are absent.
5. **`unresolved_third_party_redistribution_terms`** — OIE, NESDC and EPPO
   state no terms; the archived World Bank pages state none inline. No raw byte
   ships.
6. **`lock_is_platform_scoped`** — both locks were verified on CPython 3.12 /
   Windows AMD64 and pin versions rather than platform wheels.
7. **`dependency_audit_coverage_is_incomplete`** — 26 of the 27 distinct
   pinned distributions were covered by the vulnerability audit. `packaging` was not:
   pip-audit omits packages that are also dependencies of its own environment.
   The gap is named rather than hidden, because a clean audit of most of a set
   is not a clean audit of the set.

---

## What is left, and what comes next

The one recommended next task is **E3 — Owner-Approved Public GitHub Repository
Release**. Before it may commit, tag, create or push a repository, or create a
release, it must obtain the owner's explicit confirmation of: the GitHub account
or organisation, the repository name, public visibility, the initial release
version, commit and tag authorisation, the author identity Git should use, and
the final public-release manifest checksum.

Longer-term, and outside this scope: making project resources resolvable from an
installed distribution would remove the one limitation that blocks a PyPI
release, and resolving the four publishers' redistribution terms would let the
`unresolved` status move. Neither is required for the release the owner chose.

## What this checklist does not claim

- Not that the wheel is a usable runtime.
- Not that anyone else's data is MIT licensed.
- Not that the release is secure — two scanners found nothing today.
- Not that the project beat its baseline, produced a deployable model, or
  validated anything on the locked final test. The development programme closed
  at E1 without a supported incremental commodity model; D3's persistence
  forecasts are the registered operational reference; the evaluation was
  latest-vintage rather than a real-time backtest; and the locked final test
  remains sealed and unopened.
