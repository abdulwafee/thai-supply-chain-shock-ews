# Third-party notices

This project depends on the packages listed below. Nothing here is vendored: no
third-party source code is copied into this repository, and every dependency is
installed from PyPI at the exact version pinned in `requirements.lock.txt` or
`requirements-dev.lock.txt`.

Each licence below was **read from the installed distribution's own metadata**
at the pinned version, not looked up from memory or copied from a project page.
Where a distribution states a licence expression, that expression is reproduced;
where it states only a classifier or a licence text, the first line of what it
states is reproduced and marked as such. A blank would have been more honest
than a guess, and a guess about a licence is the kind of error that matters.

## Runtime dependencies (`requirements.lock.txt`)

| package | version | licence as declared by the distribution |
| --- | --- | --- |
| contourpy | 1.3.3 | BSD 3-Clause |
| cycler | 0.12.1 | BSD 3-Clause (declared as a copyright header: "Copyright (c) 2015, matplotlib project") |
| et-xmlfile | 2.0.0 | MIT |
| fonttools | 4.63.0 | MIT |
| kiwisolver | 1.5.1 | BSD 3-Clause (the metadata carries the licence text rather than an expression) |
| matplotlib | 3.11.1 | Matplotlib License (a BSD-style licence, declared as "License agreement for matplotlib versions 1.3.0 and later") |
| numpy | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openpyxl | 3.1.5 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 3.0.5 | BSD 3-Clause |
| pillow | 12.3.0 | MIT-CMU |
| pyarrow | 25.0.1 | Apache-2.0 |
| pyparsing | 3.3.2 | MIT |
| pypdf | 6.16.2 | BSD-3-Clause |
| python-dateutil | 2.9.0.post0 | Dual licence: Apache-2.0 and BSD-3-Clause (declared as "Dual License") |
| pyyaml | 6.0.3 | MIT |
| six | 1.17.0 | MIT |
| tzdata | 2026.3 | Apache-2.0 |
| xlrd | 2.0.2 | BSD |

## Development and CI dependencies (`requirements-dev.lock.txt`)

| package | version | licence as declared by the distribution |
| --- | --- | --- |
| build | 1.6.0 | MIT |
| colorama | 0.4.6 | BSD |
| iniconfig | 2.3.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | MIT |
| pygments | 2.21.0 | BSD-2-Clause |
| pyproject-hooks | 1.2.0 | MIT |
| pytest | 9.1.1 | MIT |
| ruff | 0.16.5 | MIT |

## Release-audit tooling (installed on demand, in neither lock)

`detect-secrets` (Apache-2.0) and `pip-audit` (Apache-2.0) are used by
`scripts/run_e2_release_preparation.py`. They are deliberately absent from both
locks: nothing in `src/` imports them, and nobody needs them to install, run or
test this project. Install them only when running the release audit:

```bash
pip install detect-secrets pip-audit
```

`truststore` is used by the same script when it is available, so `pip-audit` can
verify TLS against the operating system's certificate store rather than the
bundled one. That changes *which* store is trusted, never *whether* the
certificate is verified.

## Direct dependencies, and why each one is here

- **pandas**, **numpy** — the panel and the arithmetic.
- **pyyaml** — every configuration and preregistered contract in `configs/`.
- **openpyxl** — reads OIE's `.xlsx` workbooks.
- **xlrd** — reads EPPO's legacy `.xls` price-structure workbooks from
  2021-01 to 2023-01. `openpyxl` cannot read the old BIFF format, so this is not
  a redundant second reader.
- **pypdf** — reads the NESDC input–output PDF and the archived World Bank Pink
  Sheet issues.
- **matplotlib** — the diagnostic figures under `docs/`.
- **pyarrow** — typed Parquet output, reached through the pandas
  `engine="pyarrow"` argument. No import statement names it, which is why it is
  recorded as a justified dependency rather than removed as an unused one.

## Third-party data

Data sources are a separate question from code licences and are handled in
[`DATA_SOURCES.md`](DATA_SOURCES.md) and `docs/e2_data_license_review.md`. No
publisher's file is redistributed here.

## This project's own licence, and the boundary around it

**MIT**, decided by the repository owner and applied under Task E2-R1. The text
is in [`LICENSE`](LICENSE); packaging metadata declares the SPDX expression
`MIT`.

The grant covers **this project's own code and documentation**: `src/`,
`scripts/`, `tests/`, `configs/`, `schemas/`, `docs/`, `data/mapping/` and the
retrieval manifests under `data/raw/_manifests/`.

**It does not reach anyone else's material, and does not relicense it.** It
grants no rights in:

- World Bank documents and datasets, including the Pink Sheet workbooks and the
  archived monthly issues;
- NESDC workbooks and publications, including the 2015 input–output table;
- OIE documents, index workbooks and the Manufacturing Production Index and
  Capacity Utilisation data derived from them;
- EPPO price-structure workbooks;
- any other third-party dataset or publication.

No file from any of those publishers is redistributed here, so in practice there
is nothing in the release that the MIT grant could be misread as covering. The
boundary is stated anyway — a reader should not have to derive it. What this
project owns is the code that retrieves and analyses that material, and the
analysis it produced; the underlying documents and the facts in them belong to
their publishers, whose terms are recorded, unresolved where they are
unresolved, in [`DATA_SOURCES.md`](DATA_SOURCES.md) and
`docs/e2_data_license_review.md`.

### Citation

There is no `CITATION.cff`. It requires a verified personal author and none is
available; the packaging metadata uses the collective attribution
`Thai Supply Chain Shock EWS contributors` rather than a fabricated individual.
No personal name, email address, ORCID or affiliation has been invented.
