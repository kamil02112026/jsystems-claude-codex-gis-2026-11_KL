"""T01: packaging contract (ADR-000 §2 pinned versions, §3 layout, D13 argparse entry point)."""

from __future__ import annotations

import tomllib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]

RUNTIME_PINS = {
    "duckdb": "1.5.6",
    "pyarrow": "23.0.1",
    "httpx": "0.28.1",
    "pydantic": "2.14.2",
    "jinja2": "3.1.6",
    "pillow": "12.0.0",
}
DEV_PINS = {
    "pytest": "9.2.0",
    "respx": "0.23.1",
    "geopandas": "1.2.0",
    "pyproj": "3.8.0",
}


def _pins(requirements: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for req in requirements:
        name, sep, version = req.partition("==")
        assert sep, f"dependency not pinned with '==': {req}"
        pins[name.strip().lower()] = version.strip()
    return pins


def _pyproject() -> dict:
    return tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))


def test_runtime_dependencies_are_pinned_exactly() -> None:
    assert _pins(_pyproject()["project"]["dependencies"]) == RUNTIME_PINS


def test_dev_dependencies_are_pinned_exactly() -> None:
    assert _pins(_pyproject()["dependency-groups"]["dev"]) == DEV_PINS


def test_python_is_312() -> None:
    assert _pyproject()["project"]["requires-python"] == ">=3.12,<3.13"


def test_console_script_points_to_cli() -> None:
    assert _pyproject()["project"]["scripts"]["mapqa"] == "mapqa.cli:entry_point"


def test_lockfile_exists() -> None:
    assert (APP_DIR / "uv.lock").is_file()


def test_help_returns_zero(capsys) -> None:
    from mapqa.cli import main

    assert main(["--help"]) == 0
    assert "mapqa" in capsys.readouterr().out
