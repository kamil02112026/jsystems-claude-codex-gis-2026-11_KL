"""Shared test fixtures and paths."""

from __future__ import annotations

from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
DATA_DIR = REPO_ROOT / "course-materials" / "exercise-data" / "map-qa"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
