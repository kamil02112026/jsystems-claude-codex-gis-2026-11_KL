"""Provided photo→road links (signs/nearest_osm.csv) as PhotoRoadLink (ADR-002 §3.4, MVP)."""

from __future__ import annotations

from mapqa.contract.bundle import SignsBundle
from mapqa.contract.models import PhotoRoadLink


def map_provided_links(bundle: SignsBundle) -> dict[str, PhotoRoadLink]:
    """One link per sign photo; flags are carried over unchanged, nothing is dropped (F3.3, kryt. 5)."""
    by_photo = {lk.photo_id: lk for lk in bundle.links}
    out: dict[str, PhotoRoadLink] = {}
    for sign in bundle.signs:
        row = by_photo.get(sign.photo_id)
        flags: list[str] = list(row.match_flags) if row else []
        if sign.heading is None and "missing_heading" not in flags:
            flags.append("missing_heading")  # never for heading == 0.0 (F2.4)
        if row is None or row.osm_way_id is None:
            if "no_osm_within_25m" not in flags:
                flags.append("no_osm_within_25m")
            out[sign.photo_id] = PhotoRoadLink(photo_id=sign.photo_id, flags=flags, link_source="provided")
            continue
        out[sign.photo_id] = PhotoRoadLink(
            photo_id=sign.photo_id,
            osm_way_id=row.osm_way_id,
            distance_m=row.distance_m,
            heading_diff_deg=row.heading_diff_deg,
            candidate_count=row.candidate_count,
            flags=flags,
            link_source="provided",
        )
    return out
