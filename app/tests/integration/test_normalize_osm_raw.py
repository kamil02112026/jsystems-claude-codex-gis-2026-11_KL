"""TAC-002-03: raw is unchanged for every distinct maxspeed in the course data."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from mapqa.normalize.maxspeed import normalize_maxspeed

PARQUET = (
    Path(__file__).resolve().parents[3]
    / "course-materials" / "exercise-data" / "map-qa" / "osm_roads.parquet"
)


@pytest.mark.skipif(not PARQUET.exists(), reason="course data missing")
def test_raw_unchanged_for_all_distinct_values():
    rows = duckdb.sql(
        f"SELECT DISTINCT maxspeed FROM read_parquet('{PARQUET.as_posix()}')"
    ).fetchall()
    assert rows
    for (value,) in rows:
        raw = None if value is None else str(value)
        r = normalize_maxspeed(raw)
        assert r.raw == raw
        assert r.status in {"ok", "missing", "not_comparable"}
        if r.status == "missing":
            assert r.normalized is None
