"""T06: files adapter for the signs dataset (ADR-001 §3.2–§3.3, §4; FIL-01..06, CON-01 files part)."""

from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path

import pytest

from mapqa.config.schema import FilesSource
from mapqa.contract.bundle import Bbox
from mapqa.contract.errors import ContractViolation, SourceUnavailable
from mapqa.sources.files import FilesAdapter

KRAKOW = Bbox(19.80, 49.95, 20.15, 50.15)


@pytest.fixture(scope="module")
def adapter(data_dir: Path) -> FilesAdapter:
    return FilesAdapter("files", FilesSource(type="files", path=str(data_dir)))


@pytest.fixture(scope="module")
def signs(adapter: FilesAdapter):
    return adapter.load_signs(bbox=None)


def _tree_state(root: Path) -> dict[str, tuple[int, str]]:
    return {
        str(p.relative_to(root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in root.rglob("*")
        if p.is_file() and "data" not in p.relative_to(root).parts
    }


def test_fil01_check_counts(adapter: FilesAdapter) -> None:
    counts = adapter.check(KRAKOW)
    assert {k: v["total"] for k, v in counts.items()} == {
        "osm_roads": 99768,
        "overture_segments": 85405,
        "photos": 561,
        "photo_road_links": 561,
        "traffic_signs": 1730,
    }
    assert counts["photos"]["in_bbox"] == 561


def test_fil01_partial_bbox_reduces_in_bbox(adapter: FilesAdapter) -> None:
    counts = adapter.check(Bbox(19.93, 50.05, 19.95, 50.07))
    assert 0 < counts["osm_roads"]["in_bbox"] < counts["osm_roads"]["total"]
    assert counts["photos"]["in_bbox"] < 561


def test_con01_signs_contract(signs) -> None:
    assert len(signs.signs) == 119
    assert len(signs.links) == 119
    s = signs.signs[0]
    assert s.photo_id and s.sequence and s.license and s.author
    assert all(r.image_status == "ok" for r in signs.signs)
    assert signs.rejected == []


def test_heading_mapped_from_compass_angle_and_null_kept(signs, data_dir: Path) -> None:
    import csv

    with open(data_dir / "signs" / "signs.csv", encoding="utf-8") as f:
        raw = {r["photo_id"]: r["compass_angle"] for r in csv.DictReader(f)}
    for s in signs.signs:
        expected = None if raw[s.photo_id] == "" else float(raw[s.photo_id])
        assert s.heading == expected  # null never becomes 0 (FIL-02)


def test_u1_type_tags_joined_from_osm_roads(signs) -> None:
    typed = [lk for lk in signs.links if lk.maxspeed_type or lk.source_maxspeed]
    assert len(typed) == 73  # verified in the plan (§1): 73 of 119 after the join
    assert sum(1 for lk in signs.links if lk.osm_source == "osm_api") == 24


def test_adapter_does_not_read_label_files(signs) -> None:
    assert not any("labels" in Path(p).name for p in signs.files_read)
    assert any(p.endswith("nearest_osm.csv") for p in signs.files_read)
    assert sum(1 for p in signs.files_read if "/crops/" in p.replace("\\", "/")) == 119


def test_signs_not_bbox_filtered_by_default_but_with_explicit_bbox(adapter: FilesAdapter, signs) -> None:
    filtered = adapter.load_signs(bbox=KRAKOW)
    assert len(signs.signs) == 119
    assert len(filtered.signs) < 119
    outside = [r for r in filtered.rejected if r.reason == "outside_bbox"]
    assert len(filtered.signs) + len(outside) == 119


def _copy_signs(data_dir: Path, tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shutil.copytree(data_dir / "signs", root / "signs", ignore=shutil.ignore_patterns("photos"))
    shutil.copy(data_dir / "osm_roads.parquet", root / "osm_roads.parquet")
    return root


def test_fil03_missing_file_is_rejected_and_run_continues(data_dir: Path, tmp_path: Path) -> None:
    root = _copy_signs(data_dir, tmp_path)
    victim = sorted((root / "signs" / "crops").glob("*.jpg"))[0]
    victim.unlink()
    res = FilesAdapter("t", FilesSource(type="files", path=str(root))).load_signs(bbox=None)
    assert len(res.signs) == 119
    bad = [r for r in res.rejected if r.reason == "missing_file"]
    assert len(bad) == 1 and bad[0].record_id == victim.stem
    assert next(s for s in res.signs if s.photo_id == victim.stem).image_status == "missing_file"


def test_fil04_hash_mismatch(data_dir: Path, tmp_path: Path) -> None:
    root = _copy_signs(data_dir, tmp_path)
    victim = sorted((root / "signs" / "crops").glob("*.jpg"))[1]
    data = bytearray(victim.read_bytes())
    data[-1] ^= 0xFF
    victim.write_bytes(bytes(data))
    res = FilesAdapter("t", FilesSource(type="files", path=str(root))).load_signs(bbox=None)
    assert [r.reason for r in res.rejected] == ["hash_mismatch"]


def test_fil06_read_only(data_dir: Path, tmp_path: Path) -> None:
    root = _copy_signs(data_dir, tmp_path)
    before = _tree_state(root)
    FilesAdapter("t", FilesSource(type="files", path=str(root))).load_signs(bbox=None)
    assert _tree_state(root) == before


def test_missing_directory_is_source_unavailable(tmp_path: Path) -> None:
    with pytest.raises(SourceUnavailable):
        FilesAdapter("t", FilesSource(type="files", path=str(tmp_path / "nope"))).load_signs(bbox=None)


def test_describe_has_no_secrets(adapter: FilesAdapter) -> None:
    d = adapter.describe()
    assert d.type == "files" and d.access == "local"


# ---- photos dataset (T32, PRD F2.1–F2.4; ADR-001 §3.3, §4) ------------------------------------
@pytest.fixture(scope="module")
def photos(adapter: FilesAdapter):
    return adapter.load_photos(bbox=None)


def _offline_names(data_dir: Path) -> list[str]:
    return sorted(p.name for p in (data_dir / "offline").glob("*.jpg"))


def _copy_photos(data_dir: Path, tmp_path: Path, images: list[str] = ()) -> Path:
    root = tmp_path / "data"
    (root / "offline").mkdir(parents=True)
    shutil.copy(data_dir / "photos.csv", root / "photos.csv")
    shutil.copy(data_dir / "photo_road_links.csv", root / "photo_road_links.csv")
    for name in images:
        shutil.copy(data_dir / "offline" / name, root / "offline" / name)
    return root


def test_fil02_heading_null_and_zero_kept_apart(photos, data_dir: Path) -> None:
    with open(data_dir / "photos.csv", encoding="utf-8", newline="") as f:
        raw = {r["photo_id"]: r["heading"] for r in csv.DictReader(f)}
    for p in photos.photos:
        expected = None if raw[p.photo_id] == "" else float(raw[p.photo_id])
        assert p.heading == expected  # empty stays None, 0.0 stays 0.0
    assert sum(p.heading is None for p in photos.photos) == 15
    assert sum(p.heading == 0.0 for p in photos.photos) == 23


def test_fil03_missing_image_is_rejected_and_run_continues(data_dir: Path, tmp_path: Path) -> None:
    names = _offline_names(data_dir)[:2]
    root = _copy_photos(data_dir, tmp_path, images=names)
    res = FilesAdapter("t", FilesSource(type="files", path=str(root))).load_photos(bbox=None)
    assert len(res.photos) == 561
    missing = [r for r in res.rejected if r.reason == "missing_file"]
    assert len(missing) == 561 - len(names)
    ok = [p for p in res.photos if p.image_status == "ok"]
    assert {p.filename for p in ok} == set(names)
    assert all(p.image_path == f"offline/{p.filename}" for p in ok)
    assert {r.record_id for r in missing} == {p.photo_id for p in res.photos if p.image_status == "missing_file"}


def test_fil04_hash_mismatch_on_changed_byte(data_dir: Path, tmp_path: Path) -> None:
    names = _offline_names(data_dir)[:2]
    root = _copy_photos(data_dir, tmp_path, images=names)
    victim = root / "offline" / names[0]
    data = bytearray(victim.read_bytes())
    data[-1] ^= 0xFF
    victim.write_bytes(bytes(data))
    res = FilesAdapter("t", FilesSource(type="files", path=str(root))).load_photos(bbox=None)
    bad = [r for r in res.rejected if r.reason == "hash_mismatch"]
    victim_id = next(p.photo_id for p in res.photos if p.filename == names[0])
    other_id = next(p.photo_id for p in res.photos if p.filename == names[1])
    assert [r.record_id for r in bad] == [victim_id]
    by_id = {p.photo_id: p for p in res.photos}
    assert by_id[victim_id].image_status == "hash_mismatch"
    assert by_id[other_id].image_status == "ok"


def test_photos_outside_small_bbox_rejected(adapter: FilesAdapter, photos) -> None:
    small = Bbox(19.80, 49.95, 19.95, 50.15)  # west half of the data bbox: 348 of 561 inside
    res = adapter.load_photos(bbox=small)
    outside = [r for r in res.rejected if r.reason == "outside_bbox"]
    assert 0 < len(res.photos) < 561
    assert len(res.photos) + len(outside) == 561
    assert all(small.contains(p.longitude, p.latitude) for p in res.photos)
    assert {lk.photo_id for lk in res.links} <= {p.photo_id for p in res.photos}


def test_duplicate_photo_id_is_contract_violation(data_dir: Path, tmp_path: Path) -> None:
    root = _copy_photos(data_dir, tmp_path)
    csv_path = root / "photos.csv"
    lines = csv_path.read_text(encoding="utf-8").splitlines(keepends=True)
    csv_path.write_text("".join(lines + [lines[1]]), encoding="utf-8")
    with pytest.raises(ContractViolation):
        FilesAdapter("t", FilesSource(type="files", path=str(root))).load_photos(bbox=None)


def test_photo_links_flags_split_and_empty_is_empty_tuple(photos) -> None:
    by_photo = {lk.photo_id: lk for lk in photos.links}
    assert by_photo["panoramax_646ecfdd-ab57-4a28-b411-fb112ced3c97"].candidate_flags == ("poor_heading_alignment",)
    assert by_photo["panoramax_334a574d-18cb-4c2e-be3f-f99307e080d9"].candidate_flags == ()
    assert by_photo["panoramax_646ecfdd-ab57-4a28-b411-fb112ced3c97"].osm_way_id == 648167637
