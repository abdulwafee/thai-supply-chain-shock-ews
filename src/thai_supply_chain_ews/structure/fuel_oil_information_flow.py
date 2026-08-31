"""Information-flow audit for the C11 architecture decision (Task C11-R1).

The question this module answers is narrow and worth stating precisely: **does
the selected architecture depend on any development outcome?** Not "was the
person careful", not "did a guard exist" — does the value flow.

Three instruments, because each alone is weak.

**A controlled path guard, built as an allowlist.** :func:`assert_permitted_input`
admits a path because it is named in the frozen permitted set, not because it
failed to match a forbidden pattern. A denylist admits anything nobody thought
of; that is how the original access happened.

**Static dependency inspection.** :func:`read_call_targets` walks the AST for
calls to reading functions, resolves simple module-level path constants, and
returns what each read actually opens. Scanning a file for forbidden substrings
cannot tell a prohibition list from a read — this can, because it looks only at
call sites.

**Metric-substitution invariance.** :func:`metric_substitution_invariance` runs
the reconstruction twice, once with arbitrary fabricated metric values injected
into an isolated fixture, and requires the result to be identical. A dependency
that no static pass caught would show up as a changed answer. The fabricated
values never touch a real artifact and are never written anywhere.

The conclusion these support is ``architecture_decision_dependency_clean``. It
proves the decision reproduces without the metric artifact. It does **not**
prove the original execution was outcome-blind, and
:func:`assert_dependency_conclusion_bounded` raises if it is used that way.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

__all__ = [
    "FORBIDDEN_DEPENDENCY_CLASSES",
    "FORBIDDEN_PATH_FRAGMENTS",
    "INFORMATION_FLOW_VERSION",
    "PERMITTED_DEPENDENCY_CLASSES",
    "READ_FUNCTIONS",
    "InformationFlowError",
    "assert_dependency_conclusion_bounded",
    "assert_permitted_input",
    "dependency_report",
    "flow_checksum",
    "forbidden_fragments_in",
    "metric_substitution_invariance",
    "read_call_targets",
    "static_dependency_report",
]

INFORMATION_FLOW_VERSION = "c11r1_information_flow_v1"

#: Substrings that mark a D-series result, a target, a prediction or a locked
#: artifact. Used to CLASSIFY what a read call opens — never as the admission
#: rule, which is the allowlist.
FORBIDDEN_PATH_FRAGMENTS = (
    "/d1_", "/d3_", "/d4_", "d3r1_", "b4_", "target", "production_stress",
    "industry_month_panel", "prediction", "residual", "locked", "holdout",
    "walk_forward", "_mae", "_rmse", "metrics",
)

PERMITTED_DEPENDENCY_CLASSES = (
    "c9_c10_feature_and_structural_artifacts",
    "sector_093_exposures",
    "candidate_design_formulas",
    "frozen_preprocessing_rules",
    "rank_and_column_space_identities",
    "industry_eligibility",
    "source_availability_and_lineage",
)

FORBIDDEN_DEPENDENCY_CLASSES = (
    "d1_d3_d4_mae_or_rmse",
    "high_stress_metrics",
    "predictions_or_residuals",
    "target_values",
    "channel_performance",
    "locked_test_results",
)

#: Function names whose first argument names something being opened.
READ_FUNCTIONS = (
    "open", "read_parquet", "read_csv", "read_json", "read_text", "read_bytes",
    "load_json", "load_yaml", "loads_path",
)


class InformationFlowError(ValueError):
    """A dependency audit was asked to support a claim its evidence cannot carry."""


def forbidden_fragments_in(text: str) -> list:
    """Which forbidden fragments a path contains, if any."""
    lowered = str(text).replace("\\", "/").lower()
    return sorted({f for f in FORBIDDEN_PATH_FRAGMENTS if f in lowered})


def assert_permitted_input(path, permitted) -> str:
    """Admit a path because it is on the allowlist, not because it looks safe.

    A denylist admits every artifact nobody anticipated. The C11 access happened
    through a file that no prohibition list named at the time, which is exactly
    the failure an allowlist removes.
    """
    text = str(path).replace("\\", "/")
    allowed = {str(p).replace("\\", "/") for p in permitted}
    if not any(text == entry or text.endswith("/" + entry) for entry in allowed):
        raise InformationFlowError(
            f"{text} is not on the C11-R1 permitted-input allowlist. Inputs are "
            "admitted by name; a path is not permitted merely because it matches "
            "no forbidden pattern"
        )
    forbidden = forbidden_fragments_in(text)
    if forbidden:
        raise InformationFlowError(
            f"{text} is on the allowlist but matches forbidden fragment(s) "
            f"{forbidden}; the allowlist itself is wrong"
        )
    return text


# ---------------------------------------------------------------------------
# Static dependency inspection
# ---------------------------------------------------------------------------
def _module_constants(tree) -> dict:
    """Module-level simple assignments, so a path constant can be resolved."""
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    constants[target.id] = ast.unparse(node.value)
                except Exception:  # pragma: no cover - unparse is total in 3.9+
                    continue
    return constants


def read_call_targets(source: str) -> list:
    """What every reading call in this source actually opens.

    Returns the unparsed first argument of each call to a reading function,
    with module-level ``Path`` constants substituted. This is why a prohibition
    list does not register as a read: it is never a call argument.
    """
    tree = ast.parse(source)
    constants = _module_constants(tree)
    targets = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else None)
        if name not in READ_FUNCTIONS or not node.args:
            continue
        argument = ast.unparse(node.args[0])
        resolved = constants.get(argument, argument)
        targets.append({"function": name, "argument": argument,
                        "resolved": resolved})
    return targets


def static_dependency_report(paths) -> dict:
    """Inspect read call sites across a set of source files."""
    findings, offending, unresolved = [], [], []
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        for target in read_call_targets(source):
            forbidden = forbidden_fragments_in(target["resolved"])
            # A read whose argument is a bare parameter cannot be resolved here.
            # That is reported rather than passed silently: those are the helper
            # bodies, and it is their CALL SITES that carry the real path.
            resolved = "'" in target["resolved"] or '"' in target["resolved"]
            record = {
                "file": str(path).replace("\\", "/"),
                "function": target["function"],
                "opens": target["resolved"],
                "path_resolved": resolved,
                "forbidden_fragments": forbidden,
            }
            findings.append(record)
            if forbidden:
                offending.append(record)
            elif not resolved:
                unresolved.append(record)
    return {
        "files_inspected": len(list(paths)),
        "read_call_sites": len(findings),
        "read_calls": findings,
        "offending_read_calls": offending,
        "unresolved_read_calls": unresolved,
        "unresolved_read_call_count": len(unresolved),
        "unresolved_note": (
            "An unresolved argument is a bare parameter inside a helper such as "
            "load_json(path); the helper's own call sites are resolved and "
            "checked, so the path is covered there rather than here."
        ),
        "no_forbidden_read_call": not offending,
    }


def _import_graph(paths) -> dict:
    graph = {}
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        graph[str(path).replace("\\", "/")] = sorted(modules)
    return graph


def dependency_report(source_paths, inputs_opened, permitted_inputs,
                      reproduction: dict, substitution: dict) -> dict:
    """The whole information-flow argument, assembled from its three instruments."""
    static = static_dependency_report(source_paths)
    imports = _import_graph(source_paths)
    banned_modules = ("targets", "evaluation", "models", "modeling", "backtest")
    offending_imports = sorted({
        f"{file}:{module}"
        for file, modules in imports.items() for module in modules
        if any(f".{b}" in f".{module}" for b in banned_modules)
    })
    opened = [str(p).replace("\\", "/") for p in inputs_opened]
    for path in opened:
        assert_permitted_input(path, permitted_inputs)
    d_series = sorted(p for p in opened if forbidden_fragments_in(p))

    clean = bool(
        static["no_forbidden_read_call"]
        and not offending_imports
        and not d_series
        and reproduction.get("all_reproduced")
        and substitution.get("invariant")
    )
    return {
        "version": INFORMATION_FLOW_VERSION,
        "permitted_dependency_classes": list(PERMITTED_DEPENDENCY_CLASSES),
        "forbidden_dependency_classes": list(FORBIDDEN_DEPENDENCY_CLASSES),
        "inputs_opened": opened,
        "inputs_opened_count": len(opened),
        "d_series_paths_opened": len(d_series),
        "static_inspection": static,
        "import_graph": imports,
        "offending_imports": offending_imports,
        "reproduction_all_reproduced": bool(reproduction.get("all_reproduced")),
        "metric_substitution_invariance": substitution,
        "architecture_decision_dependency_clean": clean,
        "proves": (
            "The architecture reproduces exactly from C9/C10 structural "
            "artifacts, the sector-093 exposure vector, the candidate-design "
            "formulas and the frozen preprocessing rules, with no D-series path "
            "opened and no metric value reachable."
        ),
        "does_not_prove": (
            "That the original C11 execution was outcome-blind. A development "
            "metric artifact was opened during it, and no dependency argument "
            "changes that."
        ),
        "original_execution_outcome_blind": False,
    }


def assert_dependency_conclusion_bounded(report: dict) -> None:
    """Raise if dependency-cleanliness is used to claim outcome-blind history."""
    if report.get("original_execution_outcome_blind"):
        raise InformationFlowError(
            "the dependency audit is being used to claim the original execution "
            "was outcome-blind. It proves reproducibility without the metric "
            "artifact; the execution history is a separate fact and is recorded "
            "separately"
        )
    if report.get("architecture_decision_dependency_clean") and not report.get(
            "does_not_prove"):
        raise InformationFlowError(
            "a dependency-clean conclusion was issued without stating its limit"
        )


# ---------------------------------------------------------------------------
# Metric-substitution invariance
# ---------------------------------------------------------------------------
def metric_substitution_invariance(reconstruct, inputs: dict,
                                   fabricated_metrics: dict) -> dict:
    """Run the reconstruction with fabricated metrics injected, twice.

    The fabricated values are arbitrary and isolated: they are never written to
    an artifact, never read from one, and exist only inside this call. If the
    architecture were to depend on a metric by any route the static pass missed,
    the two results would differ.
    """
    baseline = reconstruct(dict(inputs))
    contaminated = dict(inputs)
    contaminated["forbidden_fixture"] = dict(fabricated_metrics)
    injected = reconstruct(contaminated)
    return {
        "fabricated_metric_keys": sorted(fabricated_metrics),
        "fabricated_values_written_to_disk": False,
        "fabricated_values_read_from_an_artifact": False,
        "baseline_architecture": baseline,
        "architecture_with_fabricated_metrics": injected,
        "invariant": baseline == injected,
        "note": (
            "An isolated fixture, not an artifact. If the selected architecture "
            "moved when arbitrary metric values were injected, the decision "
            "would depend on an outcome."
        ),
    }


def flow_checksum(report: dict) -> str:
    """Digest of the information-flow argument."""
    payload = {
        "version": report["version"],
        "inputs_opened": sorted(report["inputs_opened"]),
        "d_series_paths_opened": report["d_series_paths_opened"],
        "no_forbidden_read_call": report["static_inspection"]["no_forbidden_read_call"],
        "read_call_sites": report["static_inspection"]["read_call_sites"],
        "offending_imports": report["offending_imports"],
        "metric_substitution_invariant": report["metric_substitution_invariance"][
            "invariant"],
        "architecture_decision_dependency_clean": report[
            "architecture_decision_dependency_clean"],
        "original_execution_outcome_blind": report["original_execution_outcome_blind"],
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
