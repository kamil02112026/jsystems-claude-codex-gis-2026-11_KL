"""In-process DuckDB connection with the spatial extension (ADR-000 D2, §3)."""

from __future__ import annotations

from pathlib import Path

import duckdb


def connect(data_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with `spatial` loaded.

    Extensions are kept in `<data_dir>/data/.duckdb_extensions` (git-ignored, ADR-000 §3)
    when a data directory is given, so the course data folder stays the only place with
    downloaded artifacts.
    """
    con = duckdb.connect()
    if data_dir is not None:
        ext_dir = Path(data_dir) / "data" / ".duckdb_extensions"
        ext_dir.mkdir(parents=True, exist_ok=True)
        con.execute(f"SET extension_directory = '{ext_dir.as_posix()}'")
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def sql_path(path: Path) -> str:
    """Quote a filesystem path as a DuckDB string literal."""
    return "'" + Path(path).as_posix().replace("'", "''") + "'"
