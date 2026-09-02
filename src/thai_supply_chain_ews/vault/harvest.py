"""Read the repository into the entities the vault renders.

Everything here is a measurement. Where a value cannot be read it is recorded as
``unavailable`` rather than estimated, because an estimate in a knowledge graph
is indistinguishable from a fact once it is rendered.

Task codes are the spine. They appear in four different shapes across the
repository — a runner filename (``run_c11r1_governance_closure.py``), a document
prefix (``c11r1_governance_decision.md``), a config stem
(``e2r1_source_release.yaml``) and a decision-log tag (``(Task C11-R1)``) — and
:func:`normalise_task` is the one place that reconciles them. Fifty of the
hundred and seventy decisions carry no task tag at all; those are collected
rather than force-fitted to a task that might not be theirs.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

__all__ = [
    "harvest",
    "normalise_task",
    "read_decisions",
    "read_facts",
    "read_manifests",
    "read_packages",
    "read_tasks",
]

#: `b1`, `c1_5`, `c11r1`, `e2r1` -> `B1`, `C1.5`, `C11-R1`, `E2-R1`.
_STEM = re.compile(r"^([a-z])(\d+)(?:_(\d+))?(?:r(\d+))?$")
_DECISION_ROW = re.compile(r"^\|\s*(AD-R\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*([\d-]+)\s*\|\s*$")
_TASK_TAG = re.compile(r"\(Task ([A-Z0-9.\-]+)\)")


def normalise_task(stem: str) -> str:
    """The canonical task code for a filename stem, or an empty string."""
    match = _STEM.match(stem.lower())
    if not match:
        return ""
    letter, number, minor, revision = match.groups()
    code = f"{letter.upper()}{number}"
    if minor:
        code += f".{minor}"
    if revision:
        code += f"-R{revision}"
    return code


def _leading_stem(name: str) -> str:
    """The task-shaped prefix of a filename, if it has one."""
    parts = name.split("_")
    for take in (3, 2, 1):
        if len(parts) >= take:
            candidate = "_".join(parts[:take])
            if _STEM.match(candidate.lower()):
                return candidate
    return ""


def read_decisions(root: Path) -> dict:
    """Every decision-log row, grouped by the task it names."""
    path = Path(root) / "docs" / "architecture" / "decision_log.md"
    by_task, untagged, total = {}, [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _DECISION_ROW.match(line)
        if not match:
            continue
        total += 1
        identifier, title, body, date = match.groups()
        tag = _TASK_TAG.search(title) or _TASK_TAG.search(body)
        entry = {
            "id": identifier,
            "title": re.sub(r"\*\*(.*?)\*\*", r"\1", title).strip(),
            "date": date,
            "words": len(body.split()),
        }
        if tag:
            by_task.setdefault(tag.group(1), []).append(entry)
        else:
            untagged.append(entry)
    return {
        "by_task": by_task,
        "untagged": untagged,
        "total": total,
        "source": "docs/architecture/decision_log.md",
    }


def read_tasks(root: Path, decisions: dict) -> dict:
    """Each task: its runner, its documents, its configs and its decisions."""
    root = Path(root)
    tasks = {}

    def slot(code):
        return tasks.setdefault(code, {
            "code": code, "runner": "", "summary": "",
            "documents": [], "configs": [], "schemas": [], "decisions": [],
        })

    for path in sorted((root / "scripts").glob("run_*.py")):
        code = normalise_task(_leading_stem(path.stem[len("run_"):]))
        if not code:
            continue
        entry = slot(code)
        entry["runner"] = f"scripts/{path.name}"
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        first = docstring.strip().splitlines()[0] if docstring.strip() else ""
        entry["summary"] = first.strip()

    for folder, key, suffixes in (
        ("docs", "documents", (".md", ".json")),
        ("configs", "configs", (".yaml",)),
        ("schemas", "schemas", (".yaml",)),
    ):
        for path in sorted((root / folder).glob("*")):
            if path.suffix not in suffixes or not path.is_file():
                continue
            code = normalise_task(_leading_stem(path.stem))
            if code:
                slot(code)[key].append(f"{folder}/{path.name}")

    for code, entries in decisions["by_task"].items():
        slot(code)["decisions"] = entries

    return dict(sorted(tasks.items()))


def read_packages(root: Path) -> list:
    """Each source subpackage, its module count and its own description."""
    base = Path(root) / "src" / "thai_supply_chain_ews"
    packages = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        if folder.name.startswith((".", "__")) or folder.name.endswith("egg-info"):
            continue
        modules = sorted(p.name for p in folder.glob("*.py") if p.name != "__init__.py")
        initial = folder / "__init__.py"
        docstring = ""
        if initial.exists():
            docstring = ast.get_docstring(
                ast.parse(initial.read_text(encoding="utf-8"))
            ) or ""
        packages.append({
            "name": folder.name,
            "modules": modules,
            "module_count": len(modules),
            "summary": docstring.strip().splitlines()[0] if docstring.strip() else "",
            "path": f"src/thai_supply_chain_ews/{folder.name}/",
        })
    return packages


def read_manifests(root: Path) -> list:
    """The retrieval manifests: one publisher family each, counted from the file."""
    folder = Path(root) / "data" / "raw" / "_manifests"
    out = []
    for path in sorted(folder.glob("*.jsonl")):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        first = json.loads(lines[0]) if lines else {}
        out.append({
            "source_id": first.get("source_id", path.stem),
            "records": len(lines),
            "manifest": f"data/raw/_manifests/{path.name}",
            "example_url": first.get("source_url", ""),
        })
    return out


def _load(path: Path):
    if not path.exists():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_facts(root: Path) -> dict:
    """Measured project facts. A value that cannot be read stays unavailable."""
    root = Path(root)
    facts = {}

    panel = _load(root / "docs" / "b1_ingestion_metadata.json")
    if panel:
        facts["industries"] = len(panel.get("industries") or [])
        facts["first_month"] = panel.get("first_month")
        facts["last_month"] = panel.get("last_month")
        facts["month_count"] = panel.get("month_count")
        facts["panel_rows"] = panel.get("panel_row_count")
        facts["panel_source"] = "docs/b1_ingestion_metadata.json"

    release = _load(root / "docs" / "e2r1_source_release_decision.json")
    if release:
        counts = release["clean_tree"]["hermetic_tests"]["counts"]
        facts["hermetic_passed"] = counts.get("passed")
        facts["hermetic_skipped"] = counts.get("skipped")
        facts["release_files"] = release["inventory"]["release_files"]
        facts["readiness"] = release["readiness"]["status"]
        facts["code_license"] = release["license"]["code_license"]
        facts["python"] = release["python_contract"]["minimum_supported_python"]
        facts["release_source"] = "docs/e2r1_source_release_decision.json"

    ledger = _load(root / "docs" / "e1_evidence_ledger.json")
    if ledger:
        facts["registered_claims"] = len(ledger.get("claims") or [])
        facts["ledger_source"] = "docs/e1_evidence_ledger.json"

    facts["source_modules"] = sum(1 for _ in (root / "src").rglob("*.py"))
    facts["config_files"] = sum(1 for _ in (root / "configs").glob("*.yaml"))
    facts["schema_files"] = sum(1 for _ in (root / "schemas").glob("*.yaml"))
    facts["doc_files"] = sum(1 for _ in (root / "docs").rglob("*.md"))
    return facts


def harvest(root: Path) -> dict:
    """Everything the emitter needs, read in one pass."""
    root = Path(root)
    decisions = read_decisions(root)
    return {
        "root": root,
        "decisions": decisions,
        "tasks": read_tasks(root, decisions),
        "packages": read_packages(root),
        "manifests": read_manifests(root),
        "facts": read_facts(root),
    }
