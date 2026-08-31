"""Tests for thai_supply_chain_ews.config — real infrastructure, real tests.

Uses tmp_path fixtures to build tiny, clearly-artificial config directories
(not real project data) so the tests do not depend on this repository's
actual configs/ contents staying in any particular shape.
"""

from __future__ import annotations

import pytest

from thai_supply_chain_ews.config import (
    ConfigError,
    get_project_root,
    load_config,
)


def test_get_project_root_raises_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("THAI_SUPPLY_CHAIN_EWS_ROOT", raising=False)
    with pytest.raises(ConfigError, match="not set"):
        get_project_root()


def test_get_project_root_raises_when_path_not_a_directory(monkeypatch, tmp_path):
    not_a_dir = tmp_path / "does_not_exist"
    monkeypatch.setenv("THAI_SUPPLY_CHAIN_EWS_ROOT", str(not_a_dir))
    with pytest.raises(ConfigError, match="not a directory"):
        get_project_root()


def test_get_project_root_returns_resolved_path(monkeypatch, tmp_path):
    monkeypatch.setenv("THAI_SUPPLY_CHAIN_EWS_ROOT", str(tmp_path))
    assert get_project_root() == tmp_path.resolve()


def test_load_config_reads_yaml_mapping(tmp_path):
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "toy.yaml").write_text("schema_version: 1\nkey: value\n", encoding="utf-8")

    loaded = load_config("toy", root=tmp_path)

    assert loaded == {"schema_version": 1, "key": "value"}


def test_load_config_raises_when_file_missing(tmp_path):
    (tmp_path / "configs").mkdir()
    with pytest.raises(ConfigError, match="not found"):
        load_config("missing", root=tmp_path)


def test_load_config_raises_when_not_a_mapping(tmp_path):
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "toy.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config("toy", root=tmp_path)
