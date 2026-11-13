"""P1 provided photo→road links on real course data (ADR-002 §3.3–§3.4, MAT-09, MAT-10; plan T35)."""

from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

import pytest

from mapqa.config.schema import FilesSource
from mapqa.contract.bundle import PhotosBundle
from mapqa.contract.db import connect, sql_path
from mapqa.matching.provided import (
    grade_separated_tags,
    map_provided_photo_links,
    service_or_restricted_tags,
)
from mapqa.sources.files import FilesAdapter


@pytest.fixture(scope="module")
def bundle(data_dir: Path) -> PhotosBundle:
    return FilesAdapter("files", FilesSource(type="files", path=str(data_dir))).load_photos(None)


@pytest.fixture(scope="module")
def con():
    c = connect()
    yield c
    c.close()


def _oracle_distance(con, data_dir: Path, photo, osm_way_id: int) -> float:
    """Independent EPSG:2180 distance photo -> way, computed directly in DuckDB for the test."""
    roads = sql_path(Path(data_dir) / "osm_roads.parquet")
    return con.execute(
        f"""
        WITH pt AS (SELECT ST_Transform(ST_Point({photo.longitude!r}, {photo.latitude!r}),
                        'EPSG:4326', 'EPSG:2180', always_xy := true) AS g),
        w AS (SELECT ST_Transform(geometry::GEOMETRY, 'EPSG:4326', 'EPSG:2180', always_xy := true) AS g
              FROM read_parquet({roads}) WHERE osm_id = {int(osm_way_id)})
        SELECT ST_Distance(w.g, pt.g) FROM w, pt
        """
    ).fetchone()[0]


def _seeded_pairs(bundle: PhotosBundle) -> list:
    photos = {p.photo_id: p for p in bundle.photos}
    with_way = sorted((lk for lk in bundle.links if lk.osm_way_id is not None and lk.photo_id in photos),
                      key=lambda lk: lk.photo_id)
    return random.Random(34).sample(with_way, 3)


def _subset(bundle: PhotosBundle, links) -> PhotosBundle:
    ids = {lk.photo_id for lk in links}
    return replace(bundle, photos=[p for p in bundle.photos if p.photo_id in ids], links=list(links))


def test_mat10_tolerance_half_metre_no_flag_above_flags(bundle, con, data_dir: Path) -> None:
    pairs = _seeded_pairs(bundle)
    photos = {p.photo_id: p for p in bundle.photos}
    assert len(pairs) == 3
    for lk in pairs:
        recomputed = _oracle_distance(con, data_dir, photos[lk.photo_id], lk.osm_way_id)
        near = replace(lk, distance_m=recomputed + 0.4)
        far = replace(lk, distance_m=recomputed + 0.6)
        out_near = map_provided_photo_links(con, data_dir, _subset(bundle, [near]))[lk.photo_id]
        out_far = map_provided_photo_links(con, data_dir, _subset(bundle, [far]))[lk.photo_id]
        assert "distance_mismatch" not in out_near.flags
        assert "distance_mismatch" in out_far.flags
        assert out_far.distance_m == pytest.approx(recomputed + 0.6)  # stored value carried, not replaced


def test_all_links_kept_provided_and_flags_carried(bundle, con, data_dir: Path) -> None:
    out = map_provided_photo_links(con, data_dir, bundle)
    assert len(out) == 561
    assert {lk.link_source for lk in out.values()} == {"provided"}
    for link in bundle.links:
        result = out[link.photo_id]
        assert result.osm_way_id == link.osm_way_id
        assert set(link.candidate_flags) <= set(result.flags)


def test_no_way_rows_get_no_distance_check(bundle, con, data_dir: Path) -> None:
    no_way = [lk for lk in bundle.links if lk.osm_way_id is None]
    assert no_way, "course data has photos without a road candidate"
    out = map_provided_photo_links(con, data_dir, _subset(bundle, no_way))
    for lk in no_way:
        assert out[lk.photo_id].osm_way_id is None
        assert "distance_mismatch" not in out[lk.photo_id].flags


def test_grade_separated_tags() -> None:  # MAT-09
    assert grade_separated_tags({"bridge": "yes"})
    assert grade_separated_tags({"tunnel": "building_passage"})
    assert grade_separated_tags({"layer": "1"})
    assert not grade_separated_tags({"layer": "0", "bridge": "no"})
    assert not grade_separated_tags({"bridge": None, "tunnel": "no", "layer": None})


def test_service_or_restricted_tags() -> None:  # MAT-05
    assert service_or_restricted_tags({"highway": "service"})
    assert service_or_restricted_tags({"highway": "residential", "access": "private"})
    assert service_or_restricted_tags({"highway": "residential", "motor_vehicle": "destination"})
    assert not service_or_restricted_tags({"highway": "track"})
    assert not service_or_restricted_tags({"highway": "residential", "access": "yes"})
