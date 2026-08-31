"""Configuration loading for the Thai Supply Chain Shock Early Warning System.

Resolves the project root from an environment variable (never a hard-coded
absolute path — see docs/architecture/data_architecture.md and
configs/data.yaml's `project_root_env_var` setting) and loads the YAML files
in configs/. This module is infrastructure, not business logic: it does not
know anything about industries, targets, or models beyond what the YAML files
themselves say.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT_ENV_VAR = "THAI_SUPPLY_CHAIN_EWS_ROOT"
CONFIG_DIR_NAME = "configs"


class ConfigError(RuntimeError):
    """Raised when the project root or a config file cannot be resolved."""


def get_project_root() -> Path:
    """Return the project root, resolved from the environment variable.

    Deliberately fails loudly rather than falling back to a guessed local
    path such as the current working directory. A silent fallback here is
    exactly the kind of "works on my machine" bug this project's own
    reproducibility requirements (docs/project_roadmap.md Definition of Done)
    are meant to rule out.
    """
    raw = os.environ.get(PROJECT_ROOT_ENV_VAR)
    if not raw:
        raise ConfigError(
            f"Environment variable {PROJECT_ROOT_ENV_VAR} is not set. "
            "Copy .env.example to .env and set it, or export it in your shell. "
            "This project does not guess a project root."
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"{PROJECT_ROOT_ENV_VAR}={raw!r} is not a directory.")
    return root


def load_config(name: str, *, root: Path | None = None) -> dict[str, Any]:
    """Load one config file (e.g. "data", "features", "model") from configs/.

    `name` is the file stem, without `.yaml`. Raises ConfigError if the file
    is missing or does not parse to a mapping.
    """
    root = root if root is not None else get_project_root()
    path = root / CONFIG_DIR_NAME / f"{name}.yaml"
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    if not isinstance(loaded, dict):
        raise ConfigError(f"Config file {path} did not parse to a mapping.")
    return loaded


@dataclass(frozen=True)
class ProjectConfig:
    """Convenience bundle of the three config files, loaded together."""

    data: dict[str, Any]
    features: dict[str, Any]
    model: dict[str, Any]

    @classmethod
    def load(cls, *, root: Path | None = None) -> ProjectConfig:
        root = root if root is not None else get_project_root()
        return cls(
            data=load_config("data", root=root),
            features=load_config("features", root=root),
            model=load_config("model", root=root),
        )
