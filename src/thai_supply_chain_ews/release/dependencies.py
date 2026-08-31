"""Dependency reconciliation and lock verification (Task E2).

Three questions, kept apart because they fail differently:

1. **Is every third-party import declared?** An undeclared runtime import is a
   release failure. It works locally only because the package happens to be
   installed, and it is exactly the defect a clean-tree install exists to catch.
2. **Is every declared dependency used?** An unused declaration is a failure
   unless there is a documented operational reason. Some genuinely have one:
   ``pyarrow`` is reached through the pandas ``engine="pyarrow"`` argument and
   no import statement will ever name it, so the reason has to be recorded
   rather than assumed.
3. **Does the lock apply where it will be used?** The lock is resolved on one
   interpreter and one platform. This module measures what it can (each pinned
   distribution's declared ``Requires-Python``) and refuses to claim what it
   cannot (that the pinned wheels install on the CI interpreter or on Linux).

The repository already builds with setuptools and installs with pip. No second
dependency manager is introduced, because two managers means two answers to the
same question and no way to tell which one CI believed.
"""

from __future__ import annotations

import ast
import hashlib
import re
import sys
from importlib import metadata
from pathlib import Path

__all__ = [
    "IMPORT_TO_DISTRIBUTION",
    "DependencyError",
    "assert_single_dependency_manager",
    "declared_dependencies",
    "lock_checksum",
    "reconcile",
    "render_lock",
    "requires_python_admits",
    "resolve_locked_set",
    "scan_imports",
]

#: Import names differ from distribution names often enough that guessing is a
#: bug. These are the project's own, stated rather than inferred.
IMPORT_TO_DISTRIBUTION = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "sklearn": "scikit-learn",
    "PIL": "pillow",
}


class DependencyError(ValueError):
    """The declared dependency set and the code disagree."""


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _requirement_name(text: str) -> str:
    return _normalise(re.split(r"[<>=!~\[;( ]", text, maxsplit=1)[0])


def scan_imports(roots, package_name: str, local_module_names=()) -> dict:
    """Every top-level third-party import, by distribution name, with call sites.

    Uses the AST rather than a text search: ``import pypdf`` written inside a
    docstring that explains why pypdf is optional is not an import, and a
    substring scan cannot tell the difference.
    """
    standard = set(sys.stdlib_module_names)
    local = {package_name, *local_module_names}
    found = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        # A sibling script importing another script by stem is a local import,
        # not a dependency.
        local_stems = {path.stem for path in root.glob("*.py")}
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    if top in standard or top in local or top in local_stems:
                        continue
                    distribution = _normalise(IMPORT_TO_DISTRIBUTION.get(top, top))
                    entry = found.setdefault(distribution, {"import_name": top, "sites": []})
                    entry["sites"].append(f"{path.as_posix()}:{node.lineno}")
    return {key: found[key] for key in sorted(found)}


def declared_dependencies(pyproject_text: str) -> dict:
    """Runtime and development requirement names, read from pyproject.toml."""
    import tomllib

    data = tomllib.loads(pyproject_text)
    project = data.get("project", {})
    return {
        "runtime": {_requirement_name(r) for r in project.get("dependencies", [])},
        "development": {
            _requirement_name(r)
            for r in project.get("optional-dependencies", {}).get("dev", [])
        },
        "requires_python": project.get("requires-python", ""),
        "name": project.get("name", ""),
        "version": project.get("version", ""),
    }


def reconcile(imports: dict, declared: dict, justified: dict, development_only=()) -> dict:
    """Compare imports against declarations. Both directions are failures."""
    development_only = {_normalise(name) for name in development_only}
    runtime_imports = {
        name: entry for name, entry in imports.items() if name not in development_only
    }
    declared_all = declared["runtime"] | declared["development"]
    undeclared = sorted(set(runtime_imports) - declared_all)
    unused = sorted(declared["runtime"] - set(imports))
    justified_names = {_normalise(name) for name in justified}
    return {
        "imported_distributions": sorted(imports),
        "declared_runtime": sorted(declared["runtime"]),
        "declared_development": sorted(declared["development"]),
        "undeclared_runtime_imports": undeclared,
        "unused_declared_dependencies": unused,
        "unused_but_justified": sorted(n for n in unused if n in justified_names),
        "unused_and_unjustified": sorted(n for n in unused if n not in justified_names),
        "import_sites": {name: entry["sites"] for name, entry in sorted(imports.items())},
        "reconciled": not undeclared
        and not [n for n in unused if n not in justified_names],
    }


def resolve_locked_set(names) -> dict:
    """Pin each named distribution and its transitive requirements.

    Reads the *installed* metadata rather than asking a resolver to re-solve.
    The point of a lock is to record the set that was actually verified here,
    and a fresh resolution could quietly pick something nothing has run against.

    Returns ``{"pins": ..., "conditional_not_installed": ...}``. The second key
    is not noise: a requirement gated by ``python_version < "3.11"`` is absent
    here on purpose, and confusing that with a missing dependency would either
    break the lock or hide a real gap.
    """
    pinned = {}
    # Requirements gated by an environment marker are pinned only if the marker
    # was satisfied here -- which is observable without a marker evaluator,
    # because pip already made that decision when it built this environment.
    conditional = set()
    pending = [(_normalise(name), False) for name in names]
    seen = set()
    while pending:
        name, gated = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            if gated:
                conditional.add(name)
                continue
            pinned[name] = {"version": None, "requires_python": None, "installed": False}
            continue
        pinned[name] = {
            "version": distribution.version,
            "requires_python": distribution.metadata.get("Requires-Python") or "",
            "installed": True,
        }
        for requirement in distribution.requires or []:
            # Extras-gated requirements are not part of the base install;
            # pinning them would lock more than pip would ever install.
            if "extra ==" in requirement:
                continue
            pending.append((_requirement_name(requirement), ";" in requirement))
    return {
        "pins": {key: pinned[key] for key in sorted(pinned)},
        "conditional_not_installed": sorted(conditional - set(pinned)),
    }


def requires_python_admits(specifier: str, version: str) -> bool:
    """Whether a ``Requires-Python`` specifier admits ``version``.

    A missing specifier admits everything, which is what pip does too. An
    operator this cannot parse returns ``False`` rather than guessing, because
    an unreadable constraint is not a satisfied one.
    """
    if not specifier:
        return True
    target = tuple(int(part) for part in version.split("."))
    for clause in specifier.split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = re.match(r"(>=|<=|==|!=|~=|<|>)\s*([0-9][0-9.]*)", clause)
        if not match:
            return False
        operator, raw = match.groups()
        bound = tuple(int(part) for part in raw.rstrip(".").split("."))
        truncated = target[: len(bound)]
        if operator == ">=" and not target >= bound:
            return False
        if operator == ">" and not target > bound:
            return False
        if operator == "<=" and not target <= bound:
            return False
        if operator == "<" and not target < bound:
            return False
        if operator == "==" and truncated != bound:
            return False
        if operator == "!=" and truncated == bound:
            return False
        if operator == "~=" and not (
            target >= bound and target[: len(bound) - 1] == bound[: len(bound) - 1]
        ):
            return False
    return True


def render_lock(pinned: dict, header_lines) -> str:
    """A pip-installable lock file, deterministically ordered."""
    missing = sorted(name for name, info in pinned.items() if not info["version"])
    if missing:
        raise DependencyError(
            f"cannot pin {missing}: not installed in the resolving environment, "
            "so no version was ever verified here"
        )
    lines = [f"# {line}" for line in header_lines]
    lines.append("#")
    lines.extend(f"{name}=={info['version']}" for name, info in sorted(pinned.items()))
    return "\n".join(lines) + "\n"


def lock_checksum(text: str) -> str:
    """Digest over the pinned lines only, so a comment edit is not a lock change."""
    pins = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return hashlib.sha256("\n".join(pins).encode("utf-8")).hexdigest()


def assert_single_dependency_manager(root: Path, permitted: str) -> None:
    """Raise if a competing lock or manager file appeared alongside pip's."""
    competitors = {
        "poetry.lock": "poetry",
        "uv.lock": "uv",
        "pdm.lock": "pdm",
        "Pipfile.lock": "pipenv",
        "conda-lock.yml": "conda-lock",
    }
    present = sorted(
        f"{name} ({manager})"
        for name, manager in competitors.items()
        if (Path(root) / name).exists()
    )
    if present:
        raise DependencyError(
            f"a second dependency manager is present ({present}) alongside "
            f"{permitted}. Two managers means two answers to the same question "
            "and no way to tell which one CI believed"
        )
