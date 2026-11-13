"""One view of a dataset for the run pipeline: photos, links, OSM values and the input profile.

`signs` (MVP): crops + provided links from `signs/nearest_osm.csv`.
`photos` (P1): full frames, own matching in EPSG:2180 (ADR-002 §3.1–§3.3) with the provided
`photo_road_links.csv` as a reference (F3.5, MAT-07); provided flags are merged, never dropped (MAT-08).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from mapqa.contract.bundle import DATA_BBOX, Bbox, PhotosBundle, SignsBundle
from mapqa.contract.db import connect, sql_path
from mapqa.contract.models import AttributeValue, PhotoRoadLink, RejectedRecord
from mapqa.matching.provided import map_provided_links, map_provided_photo_links
from mapqa.matching.spatial import SpatialMatcher
from mapqa.normalize.osm import osm_speed_value
from mapqa.profile.profile import Profile, build_photos_profile, road_link, build_profile

ROAD_TABLES = ("osm_roads.parquet", "overture_segments.parquet")


@dataclass(frozen=True)
class PhotoMeta:
    path: str  # relative to the data directory ("" when unknown)
    sha256: str
    image_ok: bool
    captured_at: str
    author: str
    license: str
    source_url: str


@dataclass
class DatasetView:
    name: str
    photo_ids: list[str]  # all photos of the run (after --bbox), sorted
    meta: dict[str, PhotoMeta]
    links: dict[str, PhotoRoadLink]
    osm_values: dict[str, AttributeValue]
    profile: Profile
    rejected: list[RejectedRecord]
    files_read: list[str]
    warnings: list[str] = field(default_factory=list)


def signs_view(bundle: SignsBundle, bbox: Bbox | None) -> DatasetView:
    link_rows = {lk.photo_id: lk for lk in bundle.links}
    ids = sorted(s.photo_id for s in bundle.signs)
    meta = {
        s.photo_id: PhotoMeta(s.crop_path, s.crop_sha256, s.image_status == "ok", s.captured_at, s.author, s.license, s.source_url)
        for s in bundle.signs
    }
    return DatasetView(
        name="signs",
        photo_ids=ids,
        meta=meta,
        links=map_provided_links(bundle),
        osm_values={pid: osm_speed_value(link_rows.get(pid)) for pid in ids},
        profile=build_profile(bundle, bbox_text=bbox.as_text() if bbox else None),
        rejected=bundle.rejected,
        files_read=list(bundle.files_read),
    )


def load_road_tags(con, data_dir: Path, way_ids: Iterable[int]) -> dict[int, dict[str, str | None]]:  # noqa: ANN001
    """osm_way_id → all OSM tags of that way (the JSON `tags` column, ADR-001 §4)."""
    ids = sorted({int(w) for w in way_ids})
    if not ids:
        return {}
    rows = con.execute(
        f"SELECT osm_id, tags FROM read_parquet({sql_path(Path(data_dir) / 'osm_roads.parquet')}) "
        f"WHERE osm_id IN (SELECT unnest(?::BIGINT[]))",
        [ids],
    ).fetchall()
    out: dict[int, dict[str, str | None]] = {}
    for osm_id, tags in rows:
        parsed = json.loads(tags) if isinstance(tags, str) else dict(tags or {})
        out[int(osm_id)] = {str(k): (None if v is None else str(v)) for k, v in parsed.items()}
    return out


def _merge(own: PhotoRoadLink | None, provided: PhotoRoadLink | None, photo_id: str) -> PhotoRoadLink:
    """Own link drives the comparison; provided flags (incl. distance_mismatch) are added (MAT-08, kryt. 5)."""
    if own is None:
        own = PhotoRoadLink(photo_id=photo_id, flags=["no_osm_within_25m"], link_source="own")
    flags = sorted(set(own.flags) | set(provided.flags if provided else ()))
    return own.model_copy(update={"flags": flags})


def photos_view(
    bundle: PhotosBundle,
    data_dir: Path,
    bbox: Bbox | None,
    table_counts: dict[str, dict[str, int]],
) -> DatasetView:
    con = connect(data_dir)
    try:
        own = SpatialMatcher(con, data_dir).match(bundle.photos)
        provided = map_provided_photo_links(con, data_dir, bundle)
        ids = sorted(p.photo_id for p in bundle.photos)
        links = {pid: _merge(own.get(pid), provided.get(pid), pid) for pid in ids}
        tags = load_road_tags(con, data_dir, [lk.osm_way_id for lk in links.values() if lk.osm_way_id is not None])
    finally:
        con.close()

    raw = {lk.photo_id: lk for lk in bundle.links}
    osm_values: dict[str, AttributeValue] = {}
    for pid in ids:
        lk = links[pid]
        if lk.osm_way_id is None:
            osm_values[pid] = AttributeValue(status="missing", note="brak połączenia z drogą OSM")
            continue
        ref = raw.get(pid)
        # direction of travel vs way: taken from the provided link only when it points at the same way
        directed = ref.directed_bearing_diff if ref is not None and ref.osm_way_id == lk.osm_way_id else None
        osm_values[pid] = osm_speed_value(road_link(pid, lk.osm_way_id, tags.get(lk.osm_way_id, {})), directed)

    profile = build_photos_profile(
        bundle, table_counts, own, bbox.as_text() if bbox else None, road_tags=tags
    )
    meta = {
        p.photo_id: PhotoMeta(
            p.image_path or "", p.sha256, p.image_status == "ok", p.captured_at, p.author, p.license, p.source_url
        )
        for p in bundle.photos
    }
    missing = sum(1 for m in meta.values() if not m.image_ok)
    warnings = [f"photos_without_image: {missing} z {len(meta)} (pobierz zdjęcia: download_photos.py)"] if missing else []
    return DatasetView(
        name="photos",
        photo_ids=ids,
        meta=meta,
        links=links,
        osm_values=osm_values,
        profile=profile,
        rejected=bundle.rejected,
        files_read=list(bundle.files_read) + [str(Path(data_dir) / t) for t in ROAD_TABLES],
        warnings=warnings,
    )


def photos_bbox(bbox: Bbox | None) -> Bbox:
    """ADR-000 §6: --dataset photos defaults to the data bbox."""
    return bbox or DATA_BBOX
