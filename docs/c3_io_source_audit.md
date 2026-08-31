# Task C3 — Official I/O Source Audit

> **REVISED (C3-R1).** This audit originally stated that no official 58-sector
> 2015 workbook exists. **That was wrong.** `DataIO2015x58.xlsx` is published by
> NESDC and is now acquired, identity-validated and manifest-tracked. §9 gives
> the root cause; §10 the reconciliation it makes possible.
>
> The failure is the same shape as C1.5-R1's February 2025 verdict: **a negative
> result from one discovery mechanism was reported as a fact about the
> publisher.** Not finding something is not evidence that it does not exist.

How the NESDC Input–Output Table was discovered, retrieved and validated.
Numbers are read from [`c3_io_source_audit.json`](c3_io_source_audit.json).

```bash
python scripts/audit_c3_io_sources.py
```

---

## 1. Discovery

The historical NESDC I/O page — `main.php?filename=io_page` — **no longer serves
the tables.** NESDC migrated to WordPress; that URL now returns a general page
with zero I/O download links on it. Hard-coding a remembered file URL would have
either failed or, worse, silently fetched something else.

Discovery therefore walks NESDC's **own sitemap**:

```
https://www.nesdc.go.th/sitemap.xml
  └── 41 downloads-sitemap sections   (7,918 download URLs)
        └── 21 official I/O download pages
              └── each page's ?p=<post>&ddl=<file> redirect
                    └── the actual file
```

`hard_coded_file_url_used: false`. 21 I/O download pages were discovered,
covering every published vintage from 1975 to 2021.

**Transport note.** `www.nesdc.go.th` sits behind a WAF that answers a first
request with a `Set-Cookie` and a 302 back to the *same* URL, and its page router
answers content pages with HTTP **404 while serving a full, correct body**. Both
are handled explicitly: a bounded cookie retry, and a 404-with-body accepted
**only for HTML pages** — a 404 on a *file* download stays fatal, so a missing
workbook can never be mistaken for a served one.

## 2. Files acquired

| Role | File | Bytes | SHA-256 |
|---|---|---:|---|
| **Primary I/O table** | `INPUT-OUTPUT_TABLE_2015.xlsx` | 665,344 | `7da4b4dca118af76…` |
| Sector classification | `06.3-Input-Output-Description.pdf` | 167,647 | `87a65982fa12b643…` |
| Newer table (audited) | `article_file_20250225150332.xlsx` | 626,886 | `451340133b02afc7…` |
| **Aggregation validation (C3-R1)** | `DataIO2015x58.xlsx` | **239,507** | `67c921a83fae15ed…` |
| Official publication (C3-R1) | `Book_IO2015_EN.pdf` | 4,924,243 | `d5bc805c487341d9…` |

All five are manifest-tracked under `NESDC_IO` with HTTP metadata, acquisition
timestamp and checksum. Raw XLSX/PDF files are git-ignored.

**The unit is resolved.** C3 could not determine it from the data sheet and said
so. `Book_IO2015_EN.pdf` states *"Table of Input Structure (180 Sectors) (in
Thousand Baht)"* — values are **thousand Baht**. Coefficients are ratios and so
were never affected, but the ambiguity is now closed rather than carried.

## 3. What the brief expected vs what NESDC publishes

> **CORRECTED (C3-R1).** This section previously read: *"The brief named a
> 58-sector workbook. No such file exists on the official 2015 page."* The first
> sentence of that was true only of the **download page**; the second was a false
> generalisation. See §9.

NESDC publishes the 2015 table at **four** aggregation levels:

| File | Sectors | Role here |
|---|---:|---|
| `INPUT-OUTPUT_TABLE_2015.xlsx` | **180** | **Primary structural source** |
| `DataIO2015x58.xlsx` | **58** | **Aggregation validation source** |
| `DataIO2015x26.xlsx` | 26 | Published, not used |
| `DataIO2015x16.xlsx` | 16 | Published, not used |

The 180-sector table **remains primary**: its finer resolution is what makes the
12-industry crosswalk possible — 58 sectors cannot separate wooden from metal
furniture, or refineries from other petroleum products. The 58-sector table is
an **independent check**, not a replacement, and was not substituted
automatically.

## 4. Workbook layout

The file is **not** a rectangular matrix. It is a sparse **long** table, one row
per cell:

```
ROW | COLUMN | PURCHASER | WHOLESALE | RETAIL | TRANSPORT | IMPORT
```

Sheet `Data IO2015 Final`, **13,786 data cells**, header located by label rather
than by row number.

| Code block | Meaning |
|---|---|
| `001`–`180` | Production sectors |
| rows `201`–`204` | Value-added components |
| row `209` | Total value added |
| rows/cols `190` | Total intermediate |
| row `210` | Total input |
| cols `301`–`306` | Final demand components |
| cols `401`–`404` | **Imports, entered negative** |
| cols `501`–`503` | Stock changes |
| col `600` | **Gross output** |
| cols `309`, `409`, `509`, `310`, `700` | **Subtotals** |

**The subtotal trap.** `309`, `409` and `509` are subtotals of the codes directly
above them, and `190`/`600`/`700` are grand totals. Summing `301`–`309`
double-counts; folding any of them into the intermediate block would put final
demand, imports or value added inside the technical coefficients. The parser
selects the intermediate block by explicit sector-code membership and **rejects
any code outside its documented universe** rather than guessing what it is.

## 5. Valuation

| Property | Value |
|---|---|
| Price basis | **Purchasers' prices** |
| Import treatment | **Import-inclusive** |
| Import-specific coefficients | **Available** (per-cell `IMPORT` field) |
| Margins | Itemised: wholesale, retail, transport |
| Producers' price | Derivable: `PURCHASER − WHOLESALE − RETAIL − TRANSPORT` |
| Domestic-only | Derivable: `PURCHASER − IMPORT` |

Import-specific coefficients are **reported as available** because the source
genuinely provides them; nothing is inferred.

C3's primary measure is `PURCHASER`, import-inclusive. Cost pressure from a
*world* commodity price reaches a producer whether the input was imported or
bought domestically, and Thailand imports most of its crude oil, aluminum and
copper — a domestic-only matrix would report near-zero crude exposure and
understate precisely the channel C3 exists to describe. The consequence is stated
rather than hidden: inverting an import-inclusive `A` measures total requirements
in a **technology** sense including rounds embodied in imports, so it is **not** a
domestic output multiplier.

## 6. Accounting validation

| Check | Result |
|---|---|
| Duplicate `(ROW, COLUMN)` keys | **0** |
| Gross output (col 600) == total input (row 210) | **all 180 sectors** |
| Column identity `Z + value added = X` | **residual 0.000e+00** (exact) |
| Codes outside the documented universe | **0** |
| Sector labels parsed from the classification PDF | **180 / 180** |

Two structural facts, found and reported rather than smoothed:

- **Sector 179 has zero gross output** and appears nowhere in the table. Its
  coefficient column is *undefined*, so it is **excluded**, never divided by and
  never zero-filled — writing zero would assert it requires nothing.
- **Sector 145** sells its entire output to stock change, so its total-supply
  column is empty. This is why the demand-side identity is stated over
  non-subtotal columns only.

## 7. The newer 2021 table — audited, not substituted

An official **I/O Table of Thailand 2021 (180 Sectors)** exists, published
2025-02-25. It was downloaded, checksummed and parsed.

| Question | Answer |
|---|---|
| Structurally compatible with 2015? | **Yes** — identical column header, identical `001`–`180` code universe |
| Complete? | Accounting identity holds |
| Final? | **Unresolved.** The 2015 file titles itself "(Final)"; the 2021 file carries no such marker, so its status is not established by the file itself |
| Used as C3's primary source? | **No** |

The brief designates 2015 as the primary source. Changing the structural
reference year is a decision that belongs to an explicit task, not to a silent
default — so the newer table is recorded as audited-and-available, and 2015 is
what C3 computes on.

## 8. A classification-vintage caveat

NESDC publishes **one** "I/O Classification and Definition" document, and its
current edition is headed **2021**. C3 applies it to the **2015** table.

*What supports this:* both workbooks use the same `001`–`180` code universe and
the same column header, and every code C3's crosswalks use resolves to a label in
this document.

*What it does not establish:* whether any individual sector **definition** changed
between the 2015 and 2021 vintages. That is **not** verified by the evidence in
hand, and is recorded as a limitation rather than asserted away.


## 9. C3-R1 — why the 58-sector workbook was missed

**The claim.** C3 reported: *"The brief named a 58-sector workbook. No such file
exists on the official 2015 page… NESDC publishes a 180-sector table."*

**The file.** `DataIO2015x58.xlsx`, 239,507 bytes, SHA-256
`67c921a83fae15edb52d02e36dc05a83f8f26bbf15826a4b201d0b3a947b5190`, sheet
`DataIO2015x58`, internal title *"INPUT - OUTPUT TABLE OF THAILAND 2015 (58
Sectors)"*, at
`https://www.nesdc.go.th/wordpress/wp-content/uploads/2025/06/DataIO2015x58.xlsx`.

### Root cause

**Discovery was scoped to a single mechanism.** C3 walked the sitemap to
`/download/` pages and resolved each page's `?p=&ddl=` redirect. The aggregated
workbooks live in the WordPress **media library** and are not linked from any
`/download/` page at all. The 2015 download page carries exactly **one** ddl
link — the 180-sector file — so no amount of retrying that path could ever have
found the 58-sector table.

Contributing causes:

| Cause | Effect |
|---|---|
| `_DOWNLOAD_SLUG` matched only `/download/` sitemap entries | Media-library uploads never appear in the downloads sitemap |
| Caller took `matching[0]`, the first Excel link per page | **Latent defect** — not operative here (one link exists) but would have hidden a second workbook on any page listing two |
| No filename-pattern search for `x58` / `x26` / `x16` | The published aggregation suffixes were never looked for |
| The media REST API was never queried | The publisher's own file index went unread |

### Causes investigated and ruled out

**None of the transport handling was at fault.** The WAF cookie retry works — the
58-sector file downloads on the first attempt (`waf_attempts: 1`). Same-URL
redirect handling works. The 404-with-body handling works, and restricting that
leniency to HTML pages while keeping it fatal for file downloads was and remains
correct.

### The error that mattered

The bugs above are ordinary. What made them consequential is the same step that
made C1.5-R1's February verdict consequential: **"my one mechanism did not find
it" was written down as "it does not exist officially".** Discovery now queries
the media API, searches the published aggregation filename patterns, retains all
ddl candidates, and validates every downloaded workbook's own internal title and
sheet name before accepting it.

## 10. C3-R1 — reconciliation against the official 58-sector table

### What can be compared without a crosswalk

Grand totals are **partition-invariant**: identical under any correct
aggregation, whatever the mapping. All **12** were compared at a tolerance of
**0.5** — half the last published digit in thousand Baht, **preregistered** from
source precision before any comparison ran.

| Quantity | Result |
|---|---|
| Gross output, value added | **exact** |
| Intermediate transactions (purchaser) | **exact** |
| Import content | **exact** |
| Wholesale / retail / transport margins, signed and absolute | **exact** |
| **12 of 12 checks** | **exact match, max absolute difference 0** |

The 180-sector calculations are therefore **confirmed** at every level the
evidence supports, and the 180-sector exposure matrix **remains approved**.

### What cannot be compared, and why it is not claimed

Sector-level comparison needs to know which 180 sectors compose each 58 sector.
**No official NESDC concordance could be found.** Searched:

- the Input-Output Description PDF — **0** mentions of "58";
- `Book_IO2015_EN.pdf`, 455 pages — no classification or concordance section;
- the media library — the aggregated **data** files only, no mapping document;
- the contiguous-partition hypothesis — **fails**: 58-sector `003` equals
  180-sector `004`, skipping `003` entirely, so the scheme regroups rather than
  concatenates.

A subset-sum search over gross output would fit *a* partition, but fitting is not
evidence and the result would not be unique — and inferring from numeric
proximity is exactly what this task forbids. The sector-level reconciliation is
therefore recorded as **`not_executed_official_crosswalk_unavailable`**: a third
state, distinct from passed and from failed. **No unexplained discrepancy was
found, because no sector-level comparison was run.**

## 11. C3-R1 — 2021 workbook status

| Table | Internal title | Sheet | Status |
|---|---|---|---|
| 2015 | `… THAILAND 2015 (Final)` | `Data IO2015 Final` | **Final**, marked twice |
| 2021 | `… THAILAND 2021` | `DataIO2021` | **Unresolved** — no marker |

No official NESDC metadata located in this task states whether the 2021 table is
final, preliminary, revised or experimental. **Finality is not inferred from
structural compatibility** — sharing a layout and a code universe says nothing
about whether figures are final. It stays **audit-only** and does not replace the
2015 Final production source.
