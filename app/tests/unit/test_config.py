"""T04: configuration and source precedence (PRD F8.1–F8.2, F8.8; ADR-001 §3.1, CFG-01..04; TAC-10)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mapqa.config import load
from mapqa.contract.errors import ConfigError

PRD_EXAMPLE = """
default_source = "local"

[sources.local]
type = "files"
path = "course-materials/exercise-data/map-qa"

[sources.course-databricks]
type = "databricks"
access = "rest"
host_env = "DATABRICKS_HOST"
token_env = "DATABRICKS_TOKEN"
warehouse_id_env = "DATABRICKS_SQL_WAREHOUSE_ID"
schema = "workspace.map_qa"
photos_dir = "course-materials/exercise-data/map-qa/data/photos"
"""


@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    p = tmp_path / "mapqa.toml"
    p.write_text(PRD_EXAMPLE, encoding="utf-8")
    return p


@pytest.mark.parametrize(
    ("flag", "env", "expected", "resolved_by"),
    [
        ("course-databricks", "local", "course-databricks", "flag"),
        (None, "course-databricks", "course-databricks", "env"),
        (None, "", "local", "config"),  # empty MAPQA_SOURCE = unset
        (None, None, "local", "config"),
    ],
)
def test_cfg01_precedence(cfg_file: Path, flag, env, expected, resolved_by) -> None:
    environ = {"MAPQA_CONFIG": str(cfg_file)}
    if env is not None:
        environ["MAPQA_SOURCE"] = env
    loaded = load(source=flag, config_path=None, env=environ, cwd=cfg_file.parent.parent)
    assert loaded.source_name == expected
    assert loaded.resolved_by == resolved_by


def test_cfg04_builtin_files_without_config(tmp_path: Path) -> None:
    loaded = load(source=None, config_path=None, env={}, cwd=tmp_path)
    assert loaded.source_name == "files"
    assert loaded.resolved_by == "builtin"
    assert loaded.source.type == "files"
    assert loaded.source.path == "course-materials/exercise-data/map-qa"
    assert loaded.config_path is None


def test_cfg04_explicit_missing_config_is_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as err:
        load(source=None, config_path=str(tmp_path / "nope.toml"), env={}, cwd=tmp_path)
    assert err.value.code == "config_not_found"
    assert err.value.exit_code == 1


def test_mapqa_toml_in_cwd_is_used(cfg_file: Path) -> None:
    loaded = load(source=None, config_path=None, env={}, cwd=cfg_file.parent)
    assert loaded.source_name == "local"
    assert loaded.config_path == cfg_file


def test_builtin_files_always_available_with_config(cfg_file: Path) -> None:
    loaded = load(source="files", config_path=str(cfg_file), env={}, cwd=cfg_file.parent)
    assert loaded.source.type == "files"
    assert sorted(loaded.config.sources) == ["course-databricks", "files", "local"]


def test_cfg02_unknown_source_lists_names(cfg_file: Path) -> None:
    with pytest.raises(ConfigError) as err:
        load(source="nope", config_path=str(cfg_file), env={}, cwd=cfg_file.parent)
    assert err.value.code == "unknown_source"
    assert err.value.hint == "Dostępne źródła: course-databricks, files, local"


def test_cfg02_typo_in_default_source(tmp_path: Path) -> None:
    p = tmp_path / "mapqa.toml"
    p.write_text('default_source = "lokal"\n', encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        load(source=None, config_path=str(p), env={}, cwd=tmp_path)
    assert err.value.code == "unknown_source"


@pytest.mark.parametrize("bad", ["dapi1234567890abcdef", "databricks_token"])
def test_cfg03_env_names_validated(tmp_path: Path, bad: str) -> None:
    p = tmp_path / "mapqa.toml"
    p.write_text(PRD_EXAMPLE.replace('token_env = "DATABRICKS_TOKEN"', f'token_env = "{bad}"'), encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        load(source=None, config_path=str(p), env={}, cwd=tmp_path)
    assert err.value.code == "config_invalid"
    assert bad not in err.value.message  # never echo a value that may be a secret


def test_unknown_keys_rejected(tmp_path: Path) -> None:
    p = tmp_path / "mapqa.toml"
    p.write_text("defualt_source = 'x'\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load(source=None, config_path=str(p), env={}, cwd=tmp_path)


def test_tac10_defaults_from_prd(tmp_path: Path) -> None:
    c = load(source=None, config_path=None, env={}, cwd=tmp_path).config
    assert c.model_reading is False
    assert (c.limits.max_queries, c.limits.max_images, c.limits.max_usd) == (100, 25, Decimal("1.00"))
    assert c.models.level1 == "typesafe/jev-1.14"
    assert c.models.level2 == "openai/gpt-6-luna"
    assert c.models.level2_effort == "medium"
    assert c.models.comparison == "openai/gpt-6-luna-decisions"
    assert c.threshold(level=1, model="typesafe/jev-1.14", attribute="speed_limit") == 0.8
    assert c.timeout_s == 60


def test_env_models_override_defaults(tmp_path: Path) -> None:
    env = {"DECISION_MODEL": "openai/gpt-6-luna-decisions", "LLM_MODEL": "x/y"}
    c = load(source=None, config_path=None, env=env, cwd=tmp_path).config
    assert c.models.level1 == "openai/gpt-6-luna-decisions"
    assert c.models.level2 == "x/y"


def test_example_toml_is_valid_and_matches_defaults(repo_root: Path) -> None:
    example = repo_root / "app" / "mapqa.example.toml"
    loaded = load(source=None, config_path=str(example), env={}, cwd=repo_root)
    defaults = load(source=None, config_path=None, env={}, cwd=repo_root / "app").config
    assert loaded.config.limits == defaults.limits
    assert loaded.config.models == defaults.models
    assert loaded.config.threshold(level=2, model="openai/gpt-6-luna", attribute="speed_limit") == 0.8
