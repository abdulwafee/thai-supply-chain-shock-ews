# Data and licence review

Two questions, kept apart because they have different answers and different
owners. **Who may use this project's code**, which only the repository owner can
decide. And **what may be republished from the third-party sources**, which the
publishers decide and which this review can only report on.

> **Revised by Task E2-R1 (2026-08-31).** Section 1 was written under Task E2,
> when no licence had been chosen and the code licence was the single live
> release blocker. The owner has since chosen **MIT**. Section 1 now records the
> decision and what it does and does not reach; the E2 position it replaces is
> quoted below rather than deleted. Section 2 is unchanged, because the owner's
> licence decision changes nothing about anybody else's data.

## 1. The code licence — decided: MIT

`LICENSE` exists and carries the MIT text with
`Copyright (c) 2026 Thai Supply Chain Shock EWS contributors`. Packaging
metadata declares the SPDX expression `MIT` together with `license-files`, and
the placeholder is gone.

`owner_license_decision_required: false`. `license_blocker_cleared: true`. This
is no longer a release blocker.

Under PEP 639 the SPDX expression supersedes the old
`License :: OSI Approved :: MIT License` classifier, and setuptools 77+ rejects
a build that declares both, so no classifier was added. Its absence is a
decision, not an omission.

### What the MIT grant covers

This project's own work, and only that: `src/`, `scripts/`, `tests/`,
`configs/`, `schemas/`, `docs/`, `data/mapping/`, and the retrieval manifests
under `data/raw/_manifests/`.

### What it does not cover

Nothing belonging to anyone else. It grants **no rights whatsoever** in World
Bank documents and datasets, NESDC workbooks and publications, OIE documents and
index workbooks, EPPO price-structure workbooks, or any other third-party
dataset or publication. This project holds no rights in that material and cannot
license it; a repository-wide licence claim would be a false statement about
rights it never held, not a generosity.

The question does not arise in practice for the released files, because **no
third-party byte is in the release**. It is stated anyway, in `LICENSE`, in
`THIRD_PARTY_NOTICES.md` and here, because a reader who clones the repository
should not have to work out the boundary for themselves — and because the
transformations, audits and figures derived from that material are this
project's work while the underlying facts are not.

### What the E2 position was, preserved

> There is no `LICENSE` file in this repository. `pyproject.toml` declares
> `license = { text = "Unlicensed - student portfolio project" }` and
> `authors = [{ name = "Project author" }]`. `owner_license_decision_required:
> true`. This is a **release blocker**, and it is the only one currently live.
> It has deliberately not been resolved here. Choosing a licence on someone's
> behalf is choosing what rights they give away, permanently and irrevocably to
> everyone who takes a copy while it stands. A recommendation is useful; a
> decision is not mine to make.
>
> **Recommendation, if the owner wants one: MIT for the code.** It is short
> enough to read, permissive enough that a recruiter or collaborator can use the
> work without asking, universally recognised, and compatible with every
> third-party dependency licence in `THIRD_PARTY_NOTICES.md`.

The recommendation was offered; the decision was the owner's, and they made it.

### Citation metadata, still deferred

`CITATION.cff` has **not** been created. It requires a verified personal author
and none is available. Packaging metadata now uses the collective attribution
`Thai Supply Chain Shock EWS contributors`; no personal name, email address,
ORCID or affiliation has been invented.

This is a documented non-blocking limitation rather than a blocker: a
source-checkout release does not require citation metadata, and a citation file
naming a person who has not approved it would be worse than none.

## 2. Third-party data — nothing is redistributed

**Public download access does not grant redistribution rights.** A file served
without a login is a file the publisher has made available for retrieval; that
is not the same as permission for a third party to republish it, and treating
the two as equivalent is the most common way an otherwise careful project ends
up hosting something it may not host.

Where terms are unresolved, this project takes the conservative route: **exclude
the raw bytes, publish the means to obtain them.** What ships is the acquisition
code, the source URLs, the publisher timestamps, the SHA-256 checksum of every
retrieved file, and the derived analysis. What does not ship is a single
workbook, PDF or archive from any publisher.

`raw_bytes_included_in_release: false`, verified: the release manifest contains
no `.xls`, `.xlsx`, `.pdf` or `.zip` row, and the only paths admitted from
`data/raw/` are the eight retrieval manifests and the directory README, each
enumerated as a literal path.

### Publisher-by-publisher position

| publisher | files | terms found | attribution | redistribution | commercial use |
| --- | --- | --- | --- | --- | --- |
| Office of Industrial Economics (OIE), Thailand | `.xlsx`, `.zip` | none stated on the portal | expected by convention | **unresolved** | not stated |
| World Bank | `.pdf`, `.xlsx` | no inline statement on the archived Pink Sheet pages | required | **likely permitted, not confirmed inline** | likely permitted under CC BY |
| NESDC, Thailand | `.xlsx`, `.pdf` | none stated on the download page | expected by convention | **unresolved** | not stated |
| Energy Policy and Planning Office (EPPO), Thailand | `.xls`, `.xlsx` | none stated on the portal | expected by convention | **unresolved** | not stated |

### Open questions, recorded rather than resolved

- **OIE**: no machine-readable terms of use are published alongside the
  industrial index.
- **World Bank**: World Bank datasets are generally offered under CC BY 4.0
  through the Open Data initiative, but the archived Pink Sheet issue pages
  consulted for this project carried no inline licence statement. The general
  policy is recorded as context; it has not been confirmed to apply to these
  specific archived PDFs.
- **NESDC**: the 2015 input–output workbook carries no licence file.
- **EPPO**: price-structure workbooks are served without any terms of use.

`unresolved` is a state of its own here. It does not mean "probably fine" and it
does not mean "forbidden". It means nobody has established the answer, and the
release behaves accordingly: it does not ship the bytes, and it does not claim
it may.

### Attribution

Every publisher is credited by name, with its portal URL, in
[`DATA_SOURCES.md`](../DATA_SOURCES.md). Attribution is offered by convention for
official statistics regardless of whether it is contractually required, and it
is required for the World Bank material.

## 3. What would change these answers

- ~~The owner adds a `LICENSE` file → the code blocker clears.~~ **Done under
  E2-R1**: MIT, `LICENSE` shipped, metadata updated. What remains contingent on
  the owner is `CITATION.cff`, which needs an identity nobody has supplied.
- A publisher states terms that permit redistribution → the corresponding row
  moves from `unresolved` to a resolved state, and the raw bytes could then be
  reconsidered for inclusion. Nothing about the current release depends on that
  happening.
- A publisher states terms that forbid redistribution → nothing changes. The
  bytes are already excluded.
