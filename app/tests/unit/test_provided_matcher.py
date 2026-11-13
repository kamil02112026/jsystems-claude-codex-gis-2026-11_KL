"""T10: provided links → PhotoRoadLink (ADR-002 §3.4)."""

from __future__ import annotations

from mapqa.contract.bundle import SignLink, SignRecord, SignsBundle
from mapqa.matching.provided import map_provided_links


def _sign(pid: str, heading: float | None) -> SignRecord:
    return SignRecord(pid, "Kraków", 19.9, 50.0, "", heading, "a", "CC BY-SA 4.0", "", "s1", f"signs/crops/{pid}.jpg", "0" * 64, "ok")


def _link(pid: str, way: int | None, flags: tuple[str, ...] = ()) -> SignLink:
    return SignLink(pid, way, 3.0 if way else None, 10.0, "residential", "50", None, None, None, None, 1, flags, "osm_roads.parquet", None)


def test_flags_copied_and_heading_zero_is_not_missing() -> None:
    b = SignsBundle(signs=[_sign("a", 0.0), _sign("b", None)], links=[_link("a", 1, ("service_way",)), _link("b", 2)])
    links = map_provided_links(b)
    assert links["a"].flags == ["service_way"]
    assert links["b"].flags == ["missing_heading"]
    assert links["a"].osm_way_id == 1 and links["a"].link_source == "provided"


def test_photo_without_link_row_gets_no_osm_link() -> None:
    b = SignsBundle(signs=[_sign("a", 10.0)], links=[])
    lk = map_provided_links(b)["a"]
    assert lk.osm_way_id is None and "no_osm_within_25m" in lk.flags
