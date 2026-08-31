# Release checklist — Task E2

**Run date: 2026-08-31.** This is the one hand-maintained date in the release
record. E2's generated documents carry no generation timestamp, because a
timestamp inside a released document would make the release-manifest checksum
differ on every run.

**Status: `release_candidate_blocked`** — one blocker, and it is the owner's to
clear. Everything else was measured and passed.

Nothing was published. No commit, no tag, no push, no PyPI upload, no GitHub
release.

---

## The blocker

- [ ] **Choose a licence for the code.** No `LICENSE` file exists and
      `pyproject.toml` carries the placeholder
      `Unlicensed - student portfolio project`. Until the owner decides, readers
      cannot tell whether they may run this. A recommendation (MIT) and the
      alternative are in [`e2_data_license_review.md`](e2_data_license_review.md);
      the decision has not been made on the owner's behalf.

      Once decided, three things follow: add `LICENSE`, update
      `pyproject.toml`'s `license` and `authors` with metadata the owner
      supplies, and write `CITATION.cff` — which is blocked today because it
      needs a real name and the metadata has a placeholder.

---

## What was verified

### Inventory and allowlist

- [x] Inventory built from the **filesystem and git**, never inferred from
      documentation. 1,909 files, 117.9 MiB on disk.
- [x] Intended public release: **441 files, 13.9 MiB**, in 21 categories.
- [x] Allowlist **fails closed**: an unmatched path is excluded, not admitted.
      **0** paths currently fall through to the fail-closed rule — every path on
      disk is deliberately classified.
- [x] Exclusion beats inclusion. The fourteen files that escape a
      directory-wide exclusion (eight retrieval manifests, six data-directory
      READMEs) are enumerated as **literal paths** and must also match an include
      glob: two independent decisions to admit anything from an excluded
      directory.
- [x] No `.parquet`, `.xls`, `.xlsx`, `.pdf`, `.zip`, `.pkl`, `.joblib` or
      `.pyc` in the release. No `.venv`, no IDE files, no cached HTTP responses,
      no captured response headers.

### Locked final test

- [x] **Sealed and unopened.** No locked outcome was opened, hashed, scanned,
      packaged or copied. Locked paths are matched by name and are never even
      stat-ed: a size read is already an inference about contents.
- [x] The only locked documents on disk are the two **key-only** reservation
      manifests, which carry origin months and row counts and no observation.
- [x] Git history: **0 commits**, so there is no history to scan and no
      possibility a locked outcome was ever tracked. Measured, not assumed.

### Dependencies

- [x] Every third-party import is declared. **`pypdf` was undeclared and is now
      declared** — it worked locally only because it happened to be installed,
      which is exactly the defect a clean-tree install exists to catch.
- [x] Every declared dependency is used or justified. **`python-dotenv` was
      declared and never imported, and was removed**; nothing calls
      `load_dotenv`, and a declaration nothing uses is a claim about the code
      that is not true. `pyarrow` stays, justified: it is reached through the
      pandas `engine="pyarrow"` argument and no import will ever name it.
- [x] One dependency manager. pip with setuptools, as before; no poetry, uv,
      pdm or pipenv lock was introduced.
- [x] Runtime and development locks separated: **19** and **9** pins.
- [x] Every pin's declared `Requires-Python` admits the CI interpreter.

### Tests

- [x] Full working-directory suite: **1,879 passed, 0 skipped**.
- [x] Hermetic suite in the isolated release tree: **1,608 passed, 271 skipped,
      0 failed**. Counts parsed from pytest's own summary line.
- [x] The data-backed registry (**109 entries**) is **verified, not trusted**:
      with it removed, every entry fails, nothing else fails, and every failure
      names a missing input. No test was weakened to obtain a green result.
- [x] The release tree's checksum is **identical before and after** the test
      run. A suite that writes into its own source tree is a suite whose second
      run differs from its first.

### Package

- [x] Wheel and sdist built in a temporary directory. **Nothing published.**
- [x] Neither archive contains a prohibited file type, a raw-data path, a local
      environment path or a locked-test member.
- [x] Two builds produce **identical member sets**. Archive member timestamps
      differ because both formats record a build clock; that is documented
      rather than claimed away.
- [x] Metadata matches the contract: `thai-supply-chain-ews` 0.1.0,
      `requires-python >=3.11`.

### Security and privacy

- [x] **0 credential findings.** Two scanners ran: this project's own pattern
      set and `detect-secrets` 1.5.0 as an independent second opinion.
- [x] Every high-entropy finding is accounted for. The ones separated as
      published content checksums pass a check, not a dismissal: a hex digest
      counts only when its own line, an adjacent line or an enclosing mapping
      key names it as a checksum. The count is deliberately not quoted here —
      this repository publishes checksums by the hundred, so the number moves
      whenever a document does, and what matters is that nothing is left
      unexplained.
- [x] **2** findings reviewed and identified as non-credential (the scanner
      matching its own name in a configuration setting; a public EPPO document
      identifier). **0 unreviewed.**
- [x] No secret value appears in any report. Findings carry a family, a path, a
      line, a length and a truncated fingerprint, and the rendered report is
      re-checked against the values that were found.
- [x] `pip-audit` 2.10.1 ran against both locks on 2026-08-31: **0
      vulnerabilities** across 19 runtime and 9 development packages. A clean
      audit is one database on one day, not a property of the pinned set.

### Continuous integration

- [x] `.github/workflows/ci.yml`, `permissions: contents: read`.
- [x] Every action pinned to a **40-character commit SHA**, not a movable tag.
- [x] No repository secret. No official dataset download. No purge or
      locked-test artifact.
- [x] Explicit timeouts on the job and on every step.
- [x] pip cache keyed by the checksum of both lock files, so a dependency change
      invalidates it instead of silently reusing wheels for versions no longer
      pinned.
- [x] The workflow confirms the worktree is clean after building.

### Reproducibility

- [x] Release manifest: **438 of 441 files hashed**. Recomputed within the run
      and byte-identical across two consecutive full runs. The checksum lives in
      the manifest and the readiness report, not in this checklist: a document
      that quotes it and is also hashed by it could never settle.
- [x] Three self-referential documents ship but are not rows: they quote the
      manifest checksum, and a manifest covering them could never reach a fixed
      point.
- [x] No acquisition or generation timestamp enters the checksum.

---

## Documented non-blocking limitations

Each names something that was **not** verified. None is a finding that was
talked out of being one.

1. **`lock_is_platform_and_interpreter_scoped`** — the lock was resolved and
   verified on CPython 3.14.3 / Windows AMD64. It pins versions, not platform
   wheels, and has not been installed here on Linux.
2. **`declared_python_floor_unverified`** — `pyproject.toml` declares
   `>=3.11`; the verified lock admits 3.12 and above, set by `numpy==2.5.2`. No
   3.11 interpreter exists on this machine, so the declared floor was not
   exercised. Recorded rather than narrowed: changing a package's supported
   range is the owner's decision.
3. **`wheel_install_imports_but_cannot_resolve_project_resources`** — the wheel
   installs and imports, but `configs/`, `docs/` and `data/mapping/` are
   repository content rather than package data, and fifteen modules locate them
   beside the source tree. The supported installation is a source checkout.
   Making the distribution self-contained is a packaging change with its own
   test surface and belongs in its own task.
4. **`archive_member_timestamps_differ_between_builds`** — content and member
   sets match; archive bytes do not, because the format stores a build clock.
5. **`dependency_audit_is_a_snapshot`** — one advisory database, one day.

---

## Recommended follow-ups, in priority order

1. **The licence decision** (blocker, above).
2. **Resolve the source-terms questions** with the four publishers, so
   `redistribution_status` can move off `unresolved`. Nothing in the current
   release depends on it: the raw bytes are already excluded.
3. **Decide the supported Python range.** Either raise `requires-python` to
   `>=3.12` to match the verified lock, or add an unlocked 3.11 CI leg that
   actually exercises the declared floor. Today the floor is a claim nobody has
   tested.
4. **Make project resources resolvable from an installed distribution** — a
   shared root helper instead of fifteen `parents[3]` expressions, with a
   fallback when `configs/` is not a sibling. Behaviour-preserving in a source
   tree, and it would let the wheel be more than importable.
5. **Consider a first commit.** The repository has no history, which is why the
   history scan is trivially clean; that will stop being true.

---

## What this checklist does not claim

- Not that the package is secure. Two scanners found nothing today.
- Not that the third-party sources may be redistributed. Their terms are
  unresolved and their bytes are excluded.
- Not that the project beat its baseline, produced a deployable model, or
  validated anything on the locked final test. The development programme closed
  at E1 without a supported incremental commodity model, and E2 changed no
  scientific conclusion — every upstream result artifact was re-checked against
  its frozen checksum before this preparation began.
