"""T37: own link drives the comparison, provided flags are never dropped (ADR-002 MAT-08, PRD kryt. 5)."""

from mapqa.contract.models import PhotoRoadLink
from mapqa.datasets import _merge


def test_provided_flags_are_merged_into_own_link() -> None:
    own = PhotoRoadLink(photo_id="p", osm_way_id=1, flags=["junction_nearby"], link_source="own")
    provided = PhotoRoadLink(photo_id="p", osm_way_id=2, flags=["distance_mismatch", "ambiguous_candidates"], link_source="provided")
    merged = _merge(own, provided, "p")
    assert merged.osm_way_id == 1 and merged.link_source == "own"
    assert set(merged.flags) == {"junction_nearby", "distance_mismatch", "ambiguous_candidates"}


def test_missing_own_link_is_no_osm_and_keeps_provided_flags() -> None:
    provided = PhotoRoadLink(photo_id="p", osm_way_id=2, flags=["grade_separated"], link_source="provided")
    merged = _merge(None, provided, "p")
    assert merged.osm_way_id is None
    assert set(merged.flags) == {"no_osm_within_25m", "grade_separated"}
