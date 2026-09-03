"""Render harvested entities into Obsidian notes and a canvas.

Links are the whole value of a vault, so only real ones are emitted. A task
links to the documents it produced, the configs that governed it and the tasks
it superseded — relationships that exist in the repository. Nothing links to
anything merely because both are about commodities; a graph view cannot tell a
real edge from a decorative one, and a decorative edge is a claim.

The canvas is generated in Obsidian's own format rather than as an image, so it
opens as a pannable board where every node is the actual note and can be opened,
moved and annotated. Its layout is explicit: this graph has a left-to-right
reading order that a force simulation would scramble.
"""

from __future__ import annotations

import json

from .notes import Note, link, slug

__all__ = ["build_canvas", "build_notes"]

#: Obsidian canvas colours: 1 red, 2 orange, 3 yellow, 4 green, 5 cyan, 6 purple.
_CANVAS_FLOW = "5"
_CANVAS_GOV = "6"
_CANVAS_SEALED = "1"

#: Tasks whose conclusion a later task replaced. Read as "key was superseded by
#: value", and mirrored from the decision log's own supersession markers.
SUPERSESSION = {
    "C1.5": "C1.5-R3",
    "C3": "C3-R1",
    "C11": "C11-R1",
    "D1": "D3",
    "D3": "D3-R1",
    "E2": "E2-R1",
}

#: Which stage each task belongs to. The order is the dependency order, not a
#: presentation choice: each stage needed the one above it to exist first.
STAGES = [
    ("Acquire and verify the sources",
     ["B1", "C1", "C1.5", "C1.5-R1", "C1.5-R2", "C1.5-R3", "C6", "C6.5", "C7", "C7.5"]),
    ("Build the panel and the target", ["B2", "B3", "B4", "D2"]),
    ("Derive structure and features",
     ["C2", "C3", "C3-R1", "C4", "C5", "C8", "C9"]),
    ("Evaluate under a frozen protocol", ["D1", "D3", "D3-R1", "D4", "D5"]),
    ("Close, synthesise, release", ["C10", "C11", "C11-R1", "C12", "E1", "E2", "E2-R1"]),
]


def _fact(facts: dict, key: str, fallback: str = "unavailable"):
    value = facts.get(key)
    return fallback if value is None else value


def build_notes(data: dict, config: dict) -> list:
    """Every note the vault contains, in the order they are written."""
    facts = data["facts"]
    tasks = data["tasks"]
    notes = [_index(data, config)]
    notes += [_concept(entry) for entry in config["concepts"]]
    notes += [_source(entry, data) for entry in _publishers(data)]
    notes += [_task(code, entry, tasks) for code, entry in tasks.items()]
    notes += [_package(entry) for entry in data["packages"]]
    notes.append(_untagged(data))
    _ = facts  # facts are consumed by _index; named here for the reader
    return notes


# ---------------------------------------------------------------------------
# Publishers
# ---------------------------------------------------------------------------

_PUBLISHERS = {
    "OIE": {
        "title": "OIE — Office of Industrial Economics",
        "prefixes": ("OIE_",),
        "what": "Manufacturing Production Index and Capacity Utilisation.",
        "role": "The target series. Everything the project predicts is derived from it.",
        "terms": "No terms of use are stated on the portal. Redistribution unresolved.",
    },
    "WB": {
        "title": "World Bank — Pink Sheet",
        "prefixes": ("WB_",),
        "what": "Monthly commodity prices, plus archived monthly issues.",
        "role": "The commodity predictors, and the archived issues that make "
                "first-release vintages reconstructable.",
        "terms": "No licence stated inline on the archived issue pages. Likely CC BY, unconfirmed.",
    },
    "NESDC": {
        "title": "NESDC — input–output table",
        "prefixes": ("NESDC_",),
        "what": "The 2015 input–output table, 58 sectors.",
        "role": "The structural exposure of each industry to each commodity.",
        "terms": "No licence file accompanies the workbook. Redistribution unresolved.",
    },
    "EPPO": {
        "title": "EPPO — fuel price structure",
        "prefixes": ("EPPO_",),
        "what": "Weekly retail fuel price-structure workbooks.",
        "role": "The fuel-oil channel, evaluated in D5 and closed in C12.",
        "terms": "Workbooks are served without terms of use. Redistribution unresolved.",
    },
}


def _publishers(data: dict) -> list:
    out = []
    for key, meta in _PUBLISHERS.items():
        rows = [m for m in data["manifests"]
                if m["source_id"].startswith(meta["prefixes"])]
        out.append({"key": key, "meta": meta, "rows": rows})
    return out


def _source(entry: dict, data: dict) -> Note:
    meta, rows = entry["meta"], entry["rows"]
    total = sum(row["records"] for row in rows)
    lines = [
        f"> {meta['what']}",
        "",
        f"**Role in the project.** {meta['role']}",
        "",
        f"**Redistribution.** {meta['terms']} No byte of it is in the release; "
        "what ships is the retrieval code, the source URLs and a SHA-256 for "
        "every file retrieved.",
        "",
        f"## Retrieval record — {total} files",
        "",
        "| manifest | source id | files |",
        "| --- | --- | ---: |",
    ]
    for row in sorted(rows, key=lambda r: -r["records"]):
        name = row["manifest"].split("/")[-1]
        lines.append(f"| `{name}` | `{row['source_id']}` | {row['records']} |")
    lines += [
        "",
        "Each record carries the source URL, the publisher's last-modified date, "
        "the content length and a SHA-256. A checksum that stops matching means "
        "the publisher revised the file, which is a finding worth recording "
        "rather than a problem to work around.",
        "",
        "---",
        "",
        f"Related: {link('Five Distinct States')} · {link('Issue-Month Contract')}",
    ]
    return Note(
        title=meta["title"],
        kind="source",
        body="\n".join(lines),
        generated_from=["DATA_SOURCES.md"] + [row["manifest"] for row in rows],
        tags=["ews/source"],
        extra={"publisher": entry["key"], "files_retrieved": total,
               "redistribution": "unresolved"},
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _stage_of(code: str) -> tuple:
    for index, (name, members) in enumerate(STAGES, start=1):
        if code in members:
            return index, name
    return 0, "unplaced"


def _task(code: str, entry: dict, tasks: dict) -> Note:
    stage_n, stage_name = _stage_of(code)
    lines = []
    if entry["summary"]:
        lines += [f"> {entry['summary']}", ""]

    successor = SUPERSESSION.get(code)
    superseded = [k for k, v in SUPERSESSION.items() if v == code]
    if successor and successor in tasks:
        lines += [
            f"**Superseded by {link('Task ' + successor)}.** The conclusion here "
            "was replaced, and it stays exactly as written: a replaced record is "
            "still a record.",
            "",
        ]
    if superseded:
        joined = ", ".join(link("Task " + other) for other in superseded)
        lines += [f"**Supersedes** {joined}.", ""]

    if entry["runner"]:
        lines += [f"**Runner.** `{entry['runner']}` — takes no arguments.", ""]

    for label, key in (("Configuration", "configs"), ("Schemas", "schemas")):
        if entry[key]:
            joined = " · ".join(f"`{p}`" for p in entry[key])
            lines += [f"**{label}.** {joined}", ""]

    if entry["documents"]:
        lines += ["## Documents produced", ""]
        lines += [f"- `{path}`" for path in entry["documents"]]
        lines.append("")

    if entry["decisions"]:
        lines += [f"## Decisions ({len(entry['decisions'])})", ""]
        for decision in entry["decisions"]:
            # The "(Task C12)" suffix every row carries is what routed the
            # decision here; repeating it on this task's own page is noise.
            title = decision["title"].replace(f"(Task {code})", "").strip()
            lines.append(f"- **{decision['id']}** — {title} "
                         f"<small>{decision['date']}</small> ^{decision['id'].lower()}")
        lines += [
            "",
            "Each is a block reference: link to one with "
            f"`[[{slug('Task ' + code)}#^{entry['decisions'][0]['id'].lower()}]]`.",
            "",
        ]

    lines += [
        "---",
        "",
        f"Stage {stage_n} — {stage_name}. "
        f"Related: {link('Preregistration')} · {link('Supersession')}",
    ]

    return Note(
        title=f"Task {code}",
        kind="task",
        body="\n".join(lines),
        generated_from=(
            [entry["runner"]] if entry["runner"] else []
        ) + entry["documents"] + entry["configs"] + entry["schemas"]
        + ["docs/architecture/decision_log.md"],
        tags=["ews/task"],
        extra={
            "task": code,
            "stage": stage_n,
            "decisions": len(entry["decisions"]),
            "documents": len(entry["documents"]),
            "superseded_by": successor or "none",
        },
    )


# ---------------------------------------------------------------------------
# Packages, concepts, index, report
# ---------------------------------------------------------------------------

def _package(entry: dict) -> Note:
    lines = []
    if entry["summary"]:
        lines += [f"> {entry['summary']}", ""]
    lines += [f"**Path.** `{entry['path']}`", "",
              f"## Modules ({entry['module_count']})", ""]
    lines += [f"- `{name}`" for name in entry["modules"]]
    return Note(
        title=f"Package {entry['name']}",
        kind="package",
        body="\n".join(lines),
        generated_from=[entry["path"]],
        tags=["ews/package"],
        extra={"package": entry["name"], "modules": entry["module_count"]},
    )


def _concept(entry: dict) -> Note:
    body = entry["body"].strip()
    related = " · ".join(link(title) for title in entry.get("links", []))
    lines = [f"> {entry['summary']}", "", body]
    if related:
        lines += ["", "---", "", f"Related: {related}"]
    return Note(
        title=entry["title"],
        kind="concept",
        body="\n".join(lines),
        generated_from=["configs/obsidian_vault.yaml"],
        tags=["ews/concept"],
    )


def _untagged(data: dict) -> Note:
    rows = data["decisions"]["untagged"]
    lines = [
        f"> {len(rows)} of {data['decisions']['total']} decisions carry no "
        "`(Task X)` tag in the log.",
        "",
        "They are collected here rather than attached to a task that might not "
        "be theirs. Guessing an owner for a decision would put a conclusion "
        "under a heading nobody wrote it under.",
        "",
        "| decision | title | date |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        title = row["title"].replace("|", "\\|")
        lines.append(f"| `{row['id']}` | {title} | {row['date']} |")
    return Note(
        title="Decisions without a task tag",
        kind="report",
        body="\n".join(lines),
        generated_from=["docs/architecture/decision_log.md"],
        tags=["ews/report"],
        extra={"untagged": len(rows), "total": data["decisions"]["total"]},
    )


def _index(data: dict, config: dict) -> Note:
    facts, tasks = data["facts"], data["tasks"]
    lines = [
        "> A monthly early-warning study of twelve Thai manufacturing groups, "
        "and a record of how it was built and what it refused to claim.",
        "",
        "**Every note in this vault is generated** from a file in the "
        "repository and carries a checksum of its own body. Edit one and the "
        "generator will report it and leave it alone rather than overwrite it — "
        "but the edit will not travel back to the repository, so the repository "
        "stays the only source of truth.",
        "",
        "## Measured",
        "",
        "| | |",
        "| --- | --- |",
        f"| industries | {_fact(facts, 'industries')} |",
        f"| panel | {_fact(facts, 'month_count')} months, "
        f"{_fact(facts, 'first_month')} … {_fact(facts, 'last_month')} |",
        f"| panel rows | {_fact(facts, 'panel_rows')} |",
        f"| tasks | {len(tasks)} |",
        f"| decisions | {data['decisions']['total']} |",
        f"| registered claims | {_fact(facts, 'registered_claims')} |",
        f"| source modules | {_fact(facts, 'source_modules')} |",
        f"| configs · schemas · docs | {_fact(facts, 'config_files')} · "
        f"{_fact(facts, 'schema_files')} · {_fact(facts, 'doc_files')} |",
        f"| hermetic suite | {_fact(facts, 'hermetic_passed')} passed, "
        f"{_fact(facts, 'hermetic_skipped')} skipped |",
        f"| release | {_fact(facts, 'release_files')} files · "
        f"{_fact(facts, 'code_license')} · Python {_fact(facts, 'python')} |",
        f"| readiness | `{_fact(facts, 'readiness')}` |",
        "",
        "## Concepts",
        "",
    ]
    lines += [f"- {link(entry['title'])} — {entry['summary']}"
              for entry in config["concepts"]]

    lines += ["", "## Sources", ""]
    for entry in _publishers(data):
        total = sum(row["records"] for row in entry["rows"])
        lines.append(f"- {link(entry['meta']['title'])} — {total} files retrieved")

    lines += ["", "## Tasks by stage", ""]
    for index, (name, members) in enumerate(STAGES, start=1):
        present = [code for code in members if code in tasks]
        if not present:
            continue
        joined = " · ".join(link("Task " + code) for code in present)
        lines += [f"**{index}. {name}**", "", joined, ""]

    unplaced = [code for code in tasks if _stage_of(code)[0] == 0]
    if unplaced:
        lines += ["**Unplaced**", "",
                  " · ".join(link("Task " + code) for code in unplaced), ""]

    lines += ["## Packages", ""]
    for entry in data["packages"]:
        lines.append(f"- {link('Package ' + entry['name'])} — "
                     f"{entry['module_count']} modules")

    lines += [
        "",
        "## What this vault does not claim",
        "",
        "- Not that the project failed. The programme completed and produced a "
        "reproducible pipeline, a registered reference and four honest results; "
        "what did not happen is that a candidate earned promotion.",
        "- Not that commodities carry no signal. Inconclusive is not *no "
        "effect*, and not supported is not disproven.",
        "- Not that anything was validated on unseen data. See "
        f"{link('Locked Final Test')}.",
        "",
        f"Also here: {link('Decisions without a task tag')}.",
    ]
    return Note(
        title="Thai Supply Chain EWS",
        kind="index",
        body="\n".join(lines),
        generated_from=[
            "docs/architecture/decision_log.md",
            _fact(facts, "panel_source", "docs/b1_ingestion_metadata.json"),
            _fact(facts, "release_source", "docs/e2r1_source_release_decision.json"),
            _fact(facts, "ledger_source", "docs/e1_evidence_ledger.json"),
        ],
        tags=["ews"],
    )


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

def build_canvas(data: dict, folder: str) -> str:
    """An Obsidian canvas whose nodes are the real notes."""
    tasks = data["tasks"]
    nodes, edges = [], []
    width, height, gap_x, gap_y = 260, 90, 340, 118

    for column, (name, members) in enumerate(STAGES):
        present = [code for code in members if code in tasks]
        x = column * gap_x
        nodes.append({
            "id": f"stage{column}", "type": "text",
            "text": f"### {column + 1}. {name}",
            "x": x, "y": -140, "width": width, "height": 76,
        })
        for row, code in enumerate(present):
            nodes.append({
                "id": f"t{code}", "type": "file",
                "file": f"{folder}/{slug('Task ' + code)}.md",
                "x": x, "y": row * gap_y, "width": width, "height": height,
                "color": _CANVAS_GOV if column == 4 else _CANVAS_FLOW,
            })

    # Stage-to-stage edges: the dependency order the numbering encodes.
    for column in range(len(STAGES) - 1):
        left = [c for c in STAGES[column][1] if c in tasks]
        right = [c for c in STAGES[column + 1][1] if c in tasks]
        if left and right:
            edges.append({
                "id": f"s{column}", "fromNode": f"t{left[0]}", "fromSide": "right",
                "toNode": f"t{right[0]}", "toSide": "left", "label": "feeds",
            })

    # Supersession edges, which are the ones a reader most needs to see.
    for earlier, later in sorted(SUPERSESSION.items()):
        if earlier in tasks and later in tasks:
            edges.append({
                "id": f"sup{earlier}", "fromNode": f"t{later}", "fromSide": "bottom",
                "toNode": f"t{earlier}", "toSide": "bottom", "label": "supersedes",
                "color": _CANVAS_GOV,
            })

    sealed_y = max(len(members) for _, members in STAGES) * gap_y + 60
    nodes.append({
        "id": "sealed", "type": "text",
        "text": ("## Locked final test\n\nSealed and unopened. No edge in, no "
                 "edge out — and that is the result."),
        "x": 4 * gap_x, "y": sealed_y, "width": width, "height": 140,
        "color": _CANVAS_SEALED,
    })
    return json.dumps({"nodes": nodes, "edges": edges}, indent=2) + "\n"
