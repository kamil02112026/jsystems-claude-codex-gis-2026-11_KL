"""T02: schema contract from the real DESCRIBE (ADR-001 §3.7, SCH-01, SCH-02, TAC-001-07)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mapqa.contract.schema import ContractViolation, describe_inputs, distinct_values, verify_schema

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "schema_expected.json"


@pytest.fixture(scope="module")
def expected() -> dict:
    assert FIXTURE.is_file(), "run app/scripts/snapshot_schema.py once to create the fixture"
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_has_metadata(expected: dict) -> None:  # TAC-001-07
    assert expected["generated_at"]
    assert expected["source"] == "duckdb DESCRIBE on course data files"
    for entry in expected["tables"].values():
        assert len(entry["sha256"]) == 64
        assert entry["columns"]
    assert set(expected["distinct_values"]) == {"candidate_flags", "match_flags", "road_surface_value"}


def test_column_counts_match_profile(expected: dict) -> None:
    counts = {name: len(t["columns"]) for name, t in expected["tables"].items()}
    assert counts["osm_roads.parquet"] == 26
    assert counts["overture_segments.parquet"] == 14
    assert counts["photos.csv"] == 21
    assert counts["photo_road_links.csv"] == 11


def test_sch01_real_files_match_fixture(data_dir: Path, expected: dict) -> None:
    verify_schema(data_dir, expected)  # raises ContractViolation on drift


def test_sch02_distinct_values_match(data_dir: Path, expected: dict) -> None:
    assert distinct_values(data_dir) == expected["distinct_values"]


def test_sch01_detects_type_change(tmp_path: Path, data_dir: Path, expected: dict) -> None:
    # controlled mutation on a copy: photo_road_links.distance_m becomes text
    copy = tmp_path / "data"
    (copy / "signs").mkdir(parents=True)
    for name in ["osm_roads.parquet", "overture_segments.parquet", "photos.csv"]:
        shutil.copy(data_dir / name, copy / name)
    for name in ["signs.csv", "nearest_osm.csv"]:
        shutil.copy(data_dir / "signs" / name, copy / "signs" / name)
    lines = (data_dir / "photo_road_links.csv").read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    idx = header.index("distance_m")
    row = lines[1].split(",")
    row[idx] = "far"
    (copy / "photo_road_links.csv").write_text("\n".join([lines[0], ",".join(row), *lines[2:]]) + "\n", encoding="utf-8")
    with pytest.raises(ContractViolation) as err:
        verify_schema(copy, expected)
    assert "photo_road_links.csv" in str(err.value)
    assert "distance_m" in str(err.value)


def test_describe_lists_all_contract_files(data_dir: Path) -> None:
    assert set(describe_inputs(data_dir)) == {
        "osm_roads.parquet",
        "overture_segments.parquet",
        "photos.csv",
        "photo_road_links.csv",
        "signs/signs.csv",
        "signs/nearest_osm.csv",
    }
