"""Schema contract of course input files (ADR-001 §3.7, SCH-01, SCH-02)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from mapqa.contract.db import connect, sql_path
from mapqa.contract.errors import ContractViolation

CONTRACT_FILES: dict[str, str] = {
    "osm_roads.parquet": "read_parquet",
    "overture_segments.parquet": "read_parquet",
    "photos.csv": "read_csv",
    "photo_road_links.csv": "read_csv",
    "signs/signs.csv": "read_csv",
    "signs/nearest_osm.csv": "read_csv",
}

__all__ = ["ContractViolation", "CONTRACT_FILES", "describe_inputs", "distinct_values", "sha256_file", "verify_schema"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_inputs(data_dir: Path) -> dict[str, list[list[str]]]:
    """Real DESCRIBE of each contract file: [[column, type], ...]."""
    con = connect(data_dir)
    out: dict[str, list[list[str]]] = {}
    for rel, reader in CONTRACT_FILES.items():
        rows = con.execute(f"DESCRIBE SELECT * FROM {reader}({sql_path(Path(data_dir) / rel)})").fetchall()
        out[rel] = [[r[0], r[1]] for r in rows]
    return out


def distinct_values(data_dir: Path) -> dict[str, list[str]]:
    """Dictionary values whose spelling the rules depend on (SCH-02)."""
    con = connect(data_dir)
    d = Path(data_dir)

    def split_flags(rel: str, column: str) -> list[str]:
        rows = con.execute(
            f"SELECT DISTINCT trim(f) FROM (SELECT unnest(string_split({column}, ';')) AS f "
            f"FROM read_csv({sql_path(d / rel)}, all_varchar=true) WHERE {column} IS NOT NULL AND {column} <> '') "
            "WHERE trim(f) <> '' ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]

    surface = con.execute(
        f"SELECT DISTINCT s.value FROM (SELECT unnest(road_surface) AS s FROM read_parquet({sql_path(d / 'overture_segments.parquet')})) "
        "WHERE s.value IS NOT NULL ORDER BY 1"
    ).fetchall()
    return {
        "candidate_flags": split_flags("photo_road_links.csv", "candidate_flags"),
        "match_flags": split_flags("signs/nearest_osm.csv", "match_flags"),
        "road_surface_value": [r[0] for r in surface],
    }


def verify_schema(data_dir: Path, expected: dict) -> None:
    """Compare the real DESCRIBE with the snapshot; raise ContractViolation on any drift."""
    actual = describe_inputs(data_dir)
    problems: list[str] = []
    for rel, spec in expected["tables"].items():
        want = {c: t for c, t in spec["columns"]}
        have = {c: t for c, t in actual.get(rel, [])}
        if rel not in actual:
            problems.append(f"{rel}: brak pliku w kontrakcie")
            continue
        for col, typ in want.items():
            if col not in have:
                problems.append(f"{rel}.{col}: brak kolumny")
            elif have[col] != typ:
                problems.append(f"{rel}.{col}: typ {have[col]} zamiast {typ}")
    if problems:
        raise ContractViolation("Naruszenie kontraktu schematu: " + "; ".join(problems))
