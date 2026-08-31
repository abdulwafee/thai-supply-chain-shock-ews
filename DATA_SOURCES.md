# Data sources

Every input this project uses comes from an official publisher and is downloaded
by code in `src/thai_supply_chain_ews/data/`. **No third-party file is
redistributed here.** What ships instead is the acquisition code, the source
URLs, the publisher timestamps and the SHA-256 checksum of every file that was
retrieved — enough to fetch the same bytes and prove you got the same bytes,
without this repository republishing anything it has not been given permission
to republish.

The retrieval record lives in `data/raw/_manifests/*.jsonl`, one JSON object per
downloaded file, carrying `source_id`, `file_path`, `source_url`, `retrieved_at`,
`http_last_modified`, `content_length` and `sha256`.

## What is published, and what is not

| | ships in this repository | reason |
| --- | --- | --- |
| acquisition code | yes | this project's own work |
| source URLs and retrieval timestamps | yes | metadata about a public document, not the document |
| SHA-256 checksums of downloaded files | yes | lets you verify your own download matched ours |
| derived documentation, audits and figures | yes | this project's own analysis |
| the downloaded workbooks, PDFs and archives | **no** | redistribution terms are unresolved — see `docs/e2_data_license_review.md` |
| generated Parquet tables built from them | **no** | derived from files we may not redistribute, and rebuildable from source |

**Public download access is not a redistribution right.** A file being available
without a login says nothing about whether a third party may republish it. Where
the terms are unresolved, this project excludes the bytes and publishes the
means to obtain them.

## Publishers

### Office of Industrial Economics (OIE), Thailand

Manufacturing Production Index and Capacity Utilisation, the target series and
the industry panel this project is built on.

- Portal: <https://www.oie.go.th/view/1/industrial_index/TH-TH>
- Current monthly workbooks: `Prodidx1.xlsx` (MPI), `capidx.xlsx` (CapU),
  served from `https://www.oie.go.th/assets/portals/1/fileups/2/files/Industrial%20index/indexes/month/`
- Historical archives: `index2554_2561.zip` (2011–2018) and
  `index2559_2566.zip` (2016–2023), retrieved as ZIP bundles
- Manifests: `OIE_MPI_manifest.jsonl`, `OIE_CAPU_manifest.jsonl`,
  `OIE_MPI_HIST_2554_2011_manifest.jsonl`, `OIE_MPI_HIST_2559_2016_manifest.jsonl`
- File types: `.xlsx`, `.zip`
- Terms of use: **not stated on the portal.** No machine-readable licence
  accompanies the index.
- Attribution: expected by convention for official statistics.
- Redistribution: **unresolved.** Raw bytes excluded.

### World Bank

Monthly commodity prices ("Pink Sheet"), both the current historical workbook
and the archived monthly issues used to reconstruct first-release vintages.

- Programme page: <https://www.worldbank.org/en/research/commodity-markets>
- Historical workbook: `CMO-Historical-Data-Monthly.xlsx`
- Archived monthly issues: `CMOPinkSheet<Month><Year>.pdf`, served from
  `https://thedocs.worldbank.org/en/doc/...`
- Manifests: `WB_PINKSHEET_manifest.jsonl` (1 record),
  `WB_PINKSHEET_VINTAGES_manifest.jsonl` (65 archived issues)
- File types: `.xlsx`, `.pdf`
- Terms of use: World Bank datasets are generally offered under **CC BY 4.0**
  through the Open Data initiative, but the archived Pink Sheet pages consulted
  here **did not state a licence inline**. The general policy is recorded as
  context, not as a finding about these specific files.
- Attribution: required.
- Redistribution: **likely permitted but not confirmed inline.** Raw bytes
  excluded pending confirmation.

### Office of the National Economic and Social Development Council (NESDC), Thailand

The 2015 input–output table, the source of the industry exposure structure.

- Download page: <https://www.nesdc.go.th/download/i-o-table-of-thailand-2015/>
- Files: `DataIO2015x58.xlsx` (58-sector table), `Book_IO2015_EN.pdf`
- Manifest: `NESDC_IO_manifest.jsonl`
- File types: `.xlsx`, `.pdf`
- Terms of use: **not stated on the download page.** The workbook carries no
  licence file.
- Attribution: expected by convention for official statistics.
- Redistribution: **unresolved.** Raw bytes excluded.

### Energy Policy and Planning Office (EPPO), Thailand

Retail fuel price-structure workbooks, the fuel-oil channel evaluated and closed
in Task C12.

- Portal: <https://www.eppo.go.th/index.php/en/en-energystatistics>
- Files: weekly `pt-price-st-*.xls` / `.xlsx` price-structure workbooks,
  1,336 documents from 2021-01 onward
- Manifest: `EPPO_PRICE_STRUCTURE_manifest.jsonl`
- File types: `.xls` (legacy BIFF, which is why `xlrd` is a dependency), `.xlsx`
- Terms of use: **not stated on the portal.** Workbooks are served without terms.
- Attribution: expected by convention for official statistics.
- Redistribution: **unresolved.** Raw bytes excluded.

## Reproducing the source layer

`docs/e2_reproducibility_guide.md` describes the three tiers. Tier 2 rebuilds
this layer: run the acquisition scripts, then verify every downloaded file
against the `sha256` recorded in its manifest. A checksum mismatch means the
publisher revised the file, which is itself a finding worth recording rather
than a failure to work around.

## A note on what the manifests are for

The EPPO manifest is about a megabyte — the largest tracked file in this
repository — and that is a deliberate trade. The raw workbooks are regenerable
from the official index; the manifest is the only durable record of which media
identifier produced which checksum on which date. Losing the bytes costs a
download. Losing the manifest costs the ability to prove what was downloaded.
