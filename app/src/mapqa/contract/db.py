"""In-process DuckDB connection with the spatial extension (ADR-000 D2, §3)."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

_REPO_ROOT = Path(__file__).resolve().parents[4]
# git-ignored cache directory from ADR-000 §3; one shared location so the extension is
# downloaded once, also when tests point the adapter at a temporary copy of the data.
EXTENSION_DIR = Path(
    os.environ.get("MAPQA_DUCKDB_EXTENSION_DIR")
    or _REPO_ROOT / "course-materials" / "exercise-data" / "map-qa" / "data" / ".duckdb_extensions"
)


def connect(data_dir: Path | None = None) -> duckdb.DuckDBPyConnection:  # noqa: ARG001 - kept for call-site clarity
    """Open an in-memory DuckDB connection with `spatial` loaded."""
    con = duckdb.connect()
    EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET extension_directory = '{EXTENSION_DIR.as_posix()}'")
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def sql_path(path: Path) -> str:
    """Quote a filesystem path as a DuckDB string literal."""
    return "'" + Path(path).as_posix().replace("'", "''") + "'"
