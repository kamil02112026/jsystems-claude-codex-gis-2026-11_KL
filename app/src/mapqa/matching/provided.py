"""Provided photo→road links as PhotoRoadLink (ADR-002 §3.3–§3.4).

MVP: signs/nearest_osm.csv. P1: photo_road_links.csv, with distance and road-tag flags recomputed
from osm_roads.parquet in EPSG:2180.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from mapqa.contract.bundle import PhotoRecord, PhotosBundle, SignsBundle
from mapqa.contract.db import sql_path
from mapqa.contract.models import PhotoRoadLink
from mapqa.matching.crs import to_2180_sql
from mapqa.matching.flags import grade_separated_tags, service_or_restricted_tags

__all__ = ["grade_separated_tags", "map_provided_links", "map_provided_photo_links", "service_or_restricted_tags"]

DISTANCE_TOLERANCE_M = 0.5  # ADR-002 §3.3 distance_mismatch
_ROAD_TAGS = ("highway", "bridge", "tunnel", "layer", "access", "motor_vehicle")


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


def map_provided_photo_links(
    con: duckdb.DuckDBPyConnection, data_dir: Path, bundle: PhotosBundle
) -> dict[str, PhotoRoadLink]:
    """P1 provided links from photo_road_links.csv (ADR-002 §3.3–§3.4).

    Flags from the CSV are carried over unchanged. The camera→way distance is recomputed in EPSG:2180;
    a difference above 0,5 m adds `distance_mismatch`. Road tags of the provided way add
    `grade_separated` and `service_or_restricted`. The stored `distance_m` is kept as delivered.
    """
    photos = {p.photo_id: p for p in bundle.photos}
    measured = _measure_ways(con, data_dir, [(lk.photo_id, lk.osm_way_id, photos.get(lk.photo_id)) for lk in bundle.links])
    out: dict[str, PhotoRoadLink] = {}
    for lk in bundle.links:
        flags = list(lk.candidate_flags)
        found = measured.get(lk.photo_id)
        if found is not None:
            distance, tags = found
            if lk.distance_m is not None and abs(distance - lk.distance_m) > DISTANCE_TOLERANCE_M:
                flags.append("distance_mismatch")
            if grade_separated_tags(tags):
                flags.append("grade_separated")
            if service_or_restricted_tags(tags):
                flags.append("service_or_restricted")
        out[lk.photo_id] = PhotoRoadLink(
            photo_id=lk.photo_id,
            osm_way_id=lk.osm_way_id,
            overture_id=lk.overture_id,
            distance_m=lk.distance_m,
            heading_diff_deg=lk.bearing_diff,
            candidate_count=lk.osm_candidate_count,
            flags=sorted(set(flags)),
            link_source="provided",
        )
    return out


def _measure_ways(
    con: duckdb.DuckDBPyConnection,
    data_dir: Path,
    requests: list[tuple[str, int | None, PhotoRecord | None]],
) -> dict[str, tuple[float, dict[str, str | None]]]:
    """photo_id -> (EPSG:2180 distance photo→way, road tags) for links with a way and a photo."""
    rows = [(pid, way, ph.longitude, ph.latitude) for pid, way, ph in requests if way is not None and ph is not None]
    if not rows:
        return {}
    values = ", ".join("(?, ?, ?, ?)" for _ in rows)
    params = [v for row in rows for v in row]
    roads = sql_path(Path(data_dir) / "osm_roads.parquet")
    result = con.execute(
        f"""
        WITH pts(photo_id, osm_way_id, longitude, latitude) AS (VALUES {values}),
        ways AS (
            SELECT osm_id, {", ".join(_ROAD_TAGS)},
                {to_2180_sql("geometry::GEOMETRY")} AS geom_2180
            FROM read_parquet({roads})
            WHERE osm_id IN (SELECT CAST(osm_way_id AS BIGINT) FROM pts)
        )
        SELECT pts.photo_id, ways.{", ways.".join(_ROAD_TAGS)},
            ST_Distance(ways.geom_2180, {to_2180_sql("ST_Point(pts.longitude, pts.latitude)")}) AS distance_2180
        FROM pts JOIN ways ON ways.osm_id = CAST(pts.osm_way_id AS BIGINT)
        """,
        params,
    ).fetchall()
    out: dict[str, tuple[float, dict[str, str | None]]] = {}
    for pid, *tag_values, distance in result:
        out[pid] = (float(distance), dict(zip(_ROAD_TAGS, tag_values, strict=True)))
    return out

