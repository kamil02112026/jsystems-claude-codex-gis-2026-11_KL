"""T36: full input profile for the photos dataset (PRD F2.3, F3.5; ADR-004 §3.6 section 2; ADR-002 MAT-07, TAC-002-02)."""

from __future__ import annotations

from pathlib import Path

from mapqa.config.schema import FilesSource
from mapqa.contract.bundle import DATA_BBOX, PhotoLink, PhotoRecord, PhotosBundle
from mapqa.contract.models import PhotoRoadLink, RejectedRecord
from mapqa.profile.profile import build_photos_profile
from mapqa.sources.files import FilesAdapter

BBOX_TEXT = "19.8,49.95,20.15,50.15"
COUNTS = {
    "osm_roads": {"total": 10, "in_bbox": 5},
    "overture_segments": {"total": 8, "in_bbox": 4},
    "photos": {"total": 3, "in_bbox": 3},
    "photo_road_links": {"total": 3, "in_bbox": 3},
    "traffic_signs": {"total": 2, "in_bbox": 1},
}


def _photo(pid: str) -> PhotoRecord:
    return PhotoRecord(
        photo_id=pid,
        source="mapillary",
        filename=f"{pid}.jpg",
        longitude=20.0,
        latitude=50.0,
        heading=None,
        captured_at="",
        sequence="",
        author="",
        license="",
        license_url="",
        source_url="",
        sha256="0" * 64,
        is_panorama=False,
        horizontal_accuracy_m=None,
        image_path=None,
        image_status="ok",
    )


def _link(pid: str, way: int | None) -> PhotoLink:
    return PhotoLink(
        photo_id=pid,
        osm_way_id=way,
        overture_id=None,
        distance_m=None,
        way_bearing=None,
        bearing_diff=None,
        directed_bearing_diff=None,
        overture_distance_m=None,
        osm_candidate_count=0,
        match_method="provided",
        candidate_flags=(),
    )


def _own(pid: str, way: int | None) -> PhotoRoadLink:
    return PhotoRoadLink(photo_id=pid, osm_way_id=way, link_source="own")


def test_counts_pass_through_for_all_five_tables() -> None:
    bundle = PhotosBundle(photos=[_photo("p1")], links=[_link("p1", 1)])
    prof = build_photos_profile(bundle, COUNTS, None, BBOX_TEXT, road_tags={})
    assert prof.counts == COUNTS


def test_rejected_records_grouped_by_reason() -> None:
    rejected = [
        RejectedRecord(dataset="photos", record_id="a", reason="missing_file"),
        RejectedRecord(dataset="photos", record_id="b", reason="outside_bbox"),
        RejectedRecord(dataset="photos", record_id="c", reason="missing_file"),
    ]
    bundle = PhotosBundle(photos=[], links=[], rejected=rejected)
    prof = build_photos_profile(bundle, COUNTS, None, BBOX_TEXT, road_tags={})
    assert prof.rejected_by_reason == {"missing_file": 2, "outside_bbox": 1}


def test_agreement_counts_only_photos_with_an_id_on_both_sides() -> None:
    photos = [_photo(p) for p in ("p1", "p2", "p3", "p4", "p5")]
    bundle = PhotosBundle(
        photos=photos,
        links=[_link("p1", 1), _link("p2", 9), _link("p3", None), _link("p4", 4), _link("p5", 5)],
    )
    own = {
        "p1": _own("p1", 1),  # agrees
        "p2": _own("p2", 2),  # disagrees
        "p3": _own("p3", 3),  # provided id missing -> excluded
        "p4": _own("p4", None),  # own id missing -> excluded
        "p5": _own("p5", 5),  # agrees
    }
    prof = build_photos_profile(bundle, COUNTS, own, BBOX_TEXT, road_tags={})
    assert prof.agreement is not None
    assert (prof.agreement.numerator, prof.agreement.denominator) == (2, 3)
    assert prof.agreement.text() == "66,7% (2/3)"


def test_agreement_is_absent_without_own_links() -> None:
    bundle = PhotosBundle(photos=[_photo("p1")], links=[_link("p1", 1)])
    prof = build_photos_profile(bundle, COUNTS, None, BBOX_TEXT, road_tags={})
    assert prof.agreement is None


def test_agreement_below_95_percent_is_warned() -> None:
    bundle = PhotosBundle(photos=[_photo("p1"), _photo("p2")], links=[_link("p1", 1), _link("p2", 2)])
    own = {"p1": _own("p1", 1), "p2": _own("p2", 3)}
    prof = build_photos_profile(bundle, COUNTS, own, BBOX_TEXT, road_tags={})
    assert prof.agreement is not None and prof.agreement.text() == "50,0% (1/2)"
    assert any("TAC-002-02" in w for w in prof.warnings)


def test_road_completeness_uses_tags_of_linked_roads_with_explicit_denominator() -> None:
    photos = [_photo("p1"), _photo("p2"), _photo("p3")]
    bundle = PhotosBundle(photos=photos, links=[_link("p1", 1), _link("p2", 2), _link("p3", None)])
    tags = {
        1: {"maxspeed": "50", "surface": "asphalt", "lit": "yes"},
        2: {"maxspeed:type": "PL:urban", "surface": "", "lit": None},
    }
    prof = build_photos_profile(bundle, COUNTS, None, BBOX_TEXT, road_tags=tags)
    assert (prof.maxspeed.numerator, prof.maxspeed.denominator) == (2, 3)
    assert prof.maxspeed.with_number == 1
    assert prof.maxspeed.implicit_without_number == 1
    assert prof.maxspeed.text() == "66,7% (2/3)"
    assert prof.surface is not None and (prof.surface.numerator, prof.surface.denominator) == (1, 3)
    assert prof.surface.text() == "33,3% (1/3)"
    assert prof.lit is not None and (prof.lit.numerator, prof.lit.denominator) == (1, 3)


def test_missing_road_tags_are_reported_as_warning() -> None:
    bundle = PhotosBundle(photos=[_photo("p1")], links=[_link("p1", 1)])
    prof = build_photos_profile(bundle, COUNTS, None, BBOX_TEXT, road_tags=None)
    assert prof.maxspeed.numerator == 0
    assert any("tagów" in w for w in prof.warnings)


def test_warns_when_bbox_is_not_given() -> None:
    bundle = PhotosBundle(photos=[_photo("p1")], links=[_link("p1", 1)])
    prof = build_photos_profile(bundle, COUNTS, None, None, road_tags={})
    assert any("bbox" in w for w in prof.warnings)


def test_real_data_counts_and_missing_files_before_download(data_dir: Path) -> None:
    adapter = FilesAdapter("files", FilesSource(type="files", path=str(data_dir)))
    counts = adapter.check(DATA_BBOX)
    assert {t: counts[t]["total"] for t in ("osm_roads", "overture_segments", "photos", "photo_road_links", "traffic_signs")} == {
        "osm_roads": 99768,
        "overture_segments": 85405,
        "photos": 561,
        "photo_road_links": 561,
        "traffic_signs": 1730,
    }
    bundle = adapter.load_photos(None)
    prof = build_photos_profile(bundle, counts, None, DATA_BBOX.as_text(), road_tags={})
    assert prof.rejected_by_reason.get("missing_file") == 521
