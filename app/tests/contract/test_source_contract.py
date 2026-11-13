"""CON-01 (files part): photos and photo_road_links contract (ADR-001 §4, PRD F2.1–F2.4)."""

from __future__ import annotations

import pytest

from mapqa.config.schema import FilesSource
from mapqa.contract.bundle import DATA_BBOX, PhotosBundle
from mapqa.sources.files import FilesAdapter


@pytest.fixture(scope="module")
def photos(data_dir) -> PhotosBundle:
    return FilesAdapter("files", FilesSource(type="files", path=str(data_dir))).load_photos(bbox=None)


def test_con01_counts(photos: PhotosBundle) -> None:
    assert len(photos.photos) == 561
    assert len(photos.links) == 561
    # only 40 images ship in offline/; the other 521 are rejected as missing_file, rows stay (ADR-001 §3.3)
    assert {r.reason for r in photos.rejected} == {"missing_file"}
    assert len(photos.rejected) == 521


def test_con01_types_and_nulls(photos: PhotosBundle) -> None:
    for p in photos.photos:
        assert isinstance(p.photo_id, str) and p.photo_id
        assert isinstance(p.longitude, float) and isinstance(p.latitude, float)
        assert DATA_BBOX.contains(p.longitude, p.latitude)  # EPSG:4326, lon/lat
        assert p.heading is None or isinstance(p.heading, float)
        assert isinstance(p.is_panorama, bool)
        assert p.horizontal_accuracy_m is None or isinstance(p.horizontal_accuracy_m, float)
        assert p.image_status in {"ok", "missing_file", "hash_mismatch"}
        assert (p.image_path is None) == (p.image_status == "missing_file")


def test_con01_heading_null_is_not_zero(photos: PhotosBundle) -> None:
    assert sum(p.heading is None for p in photos.photos) == 15
    assert sum(p.heading == 0.0 for p in photos.photos) == 23


def test_con01_link_types_and_keys(photos: PhotosBundle) -> None:
    assert {lk.photo_id for lk in photos.links} <= {p.photo_id for p in photos.photos}
    for lk in photos.links:
        assert lk.osm_way_id is None or isinstance(lk.osm_way_id, int)
        assert isinstance(lk.osm_candidate_count, int)
        assert isinstance(lk.candidate_flags, tuple)
        assert all(isinstance(f, str) and f == f.strip() and f for f in lk.candidate_flags)
