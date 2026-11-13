"""Own photo-to-road matching in EPSG:2180 (ADR-002 §3.1–3.3)."""
from __future__ import annotations

from functools import cmp_to_key
from pathlib import Path
import re
from uuid import uuid4

import duckdb

from mapqa.contract.bundle import PhotoRecord
from mapqa.contract.db import sql_path
from mapqa.contract.models import PhotoRoadLink
from mapqa.matching.crs import distance_sql, initial_bearing, to_2180_sql


class SpatialMatcher:
    def __init__(self, con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
        self.con = con
        # Private temporary tables keep separate matchers on one connection independent.
        suffix = uuid4().hex
        self.roads = f'match_roads_{suffix}_2180'
        self.segments = f'match_segments_{suffix}_2180'
        self.junctions = f'match_junctions_{suffix}_2180'
        con.execute(f'''CREATE TEMP TABLE {self.roads} AS
            SELECT * EXCLUDE (geometry), {to_2180_sql('geometry::GEOMETRY')} AS geom_2180
            FROM read_parquet({sql_path(Path(data_dir) / 'osm_roads.parquet')})''')
        con.execute(f'''CREATE TEMP TABLE {self.segments} AS
            SELECT id, sources, level_rules, {to_2180_sql('geometry::GEOMETRY')} AS geom_2180
            FROM read_parquet({sql_path(Path(data_dir) / 'overture_segments.parquet')})''')
        con.execute(f'''CREATE TEMP TABLE {self.junctions} AS
            WITH nodes AS (
                SELECT osm_id, node_ids[i] AS node_id,
                    ST_PointN(geom_2180, i::INTEGER) AS geom_2180
                FROM {self.roads}, UNNEST(range(1, len(node_ids)+1)) AS n(i)
            )
            SELECT node_id, first(geom_2180 ORDER BY osm_id) AS geom_2180
            FROM nodes GROUP BY node_id HAVING count(DISTINCT osm_id) >= 3''')

    def _candidates(self, photo: PhotoRecord) -> list[dict]:
        query = f'''
            WITH photo AS (SELECT {to_2180_sql('point_4326')} AS geom_2180
                FROM (SELECT ST_Point(?, ?) AS point_4326)),
            nearby AS (
                SELECT r.*, p.geom_2180 AS photo_2180,
                    {distance_sql('r.geom_2180', 'p.geom_2180')} AS distance_2180,
                    ST_Length(r.geom_2180) AS length_2180,
                    ST_LineLocatePoint(r.geom_2180, p.geom_2180) AS fraction
                FROM {self.roads} r CROSS JOIN photo p
                WHERE ST_DWithin(r.geom_2180, p.geom_2180, 25)
                    AND ST_Length(r.geom_2180) > 0
            ), tangent AS (
                SELECT *, ST_LineInterpolatePoint(geom_2180, fraction) AS projection_2180,
                    ST_LineSubstring(geom_2180,
                        greatest(0, fraction - 5 / length_2180),
                        least(1, fraction + 5 / length_2180)) AS tangent_2180
                FROM nearby
            ), geographic AS (
                SELECT *, ST_Transform(tangent_2180, 'EPSG:2180', 'EPSG:4326',
                    always_xy := true) AS tangent_4326 FROM tangent
            )
            SELECT osm_id, distance_2180, highway, oneway, boundary_crossing,
                bridge, tunnel, layer, access, motor_vehicle,
                ST_X(ST_StartPoint(tangent_4326)) AS lon1,
                ST_Y(ST_StartPoint(tangent_4326)) AS lat1,
                ST_X(ST_EndPoint(tangent_4326)) AS lon2,
                ST_Y(ST_EndPoint(tangent_4326)) AS lat2,
                EXISTS (SELECT 1 FROM {self.junctions} j
                    WHERE ST_DWithin(j.geom_2180, geographic.projection_2180, 15)) AS junction_nearby
            FROM geographic
        '''
        result = self.con.execute(query, [photo.longitude, photo.latitude])
        names = [column[0] for column in result.description]
        candidates = [dict(zip(names, row)) for row in result.fetchall()]
        for row in candidates:
            bearing = initial_bearing(row['lon1'], row['lat1'], row['lon2'], row['lat2'])
            directed = None if photo.heading is None else abs((photo.heading-bearing+180) % 360-180)
            diff = None if directed is None else min(directed, 180-directed)
            row.update(directed=directed, diff=diff,
                       rank=row['distance_2180'] + (5 if diff is None else diff / 9))
        return sorted(candidates, key=cmp_to_key(_compare_candidates))

    def _overture(self, photo: PhotoRecord, osm_id: int | None) -> tuple[str | None, bool, bool]:
        result = self.con.execute(f'''
            WITH photo AS (SELECT {to_2180_sql('point_4326')} AS geom_2180
                FROM (SELECT ST_Point(?, ?) AS point_4326))
            SELECT s.id, s.sources, s.level_rules,
                {distance_sql('s.geom_2180', 'p.geom_2180')} AS distance_2180
            FROM {self.segments} s CROSS JOIN photo p
            WHERE ST_DWithin(s.geom_2180, p.geom_2180, 25)
            ''', [photo.longitude, photo.latitude]).fetchall()
        ranked = []
        for sid, sources, levels, distance in result:
            reference = osm_id is not None and any(
                re.fullmatch(rf'w{osm_id}@\d+', source.get('record_id') or '')
                for source in sources or []
            )
            ranked.append((not reference, distance, sid, bool(levels)))
        if not ranked:
            return None, False, False
        fallback, _, sid, grade = min(ranked)
        return sid, fallback, grade

    def match(self, photos: list[PhotoRecord]) -> dict[str, PhotoRoadLink]:
        links = {}
        for photo in sorted(photos, key=lambda p: p.photo_id):
            candidates = self._candidates(photo)
            best = candidates[0] if candidates else None
            flags = set()
            if photo.heading is None:
                flags.add('missing_heading')
            if photo.is_panorama:
                flags.add('panorama_heading_ambiguous')
            if best is None:
                flags.add('no_osm_within_25m')
            else:
                if len(candidates) > 1 and candidates[1]['rank'] <= best['rank'] + 2:
                    flags.add('ambiguous_candidates')
                if best['junction_nearby']:
                    flags.add('junction_nearby')
                if best['boundary_crossing']:
                    flags.add('boundary_crossing')
                if best['highway'] in {'service', 'track'}:
                    flags.add('service_way')
                if best['highway'] == 'service' or any(
                    best[tag] in {'private', 'no', 'destination'} for tag in ('access', 'motor_vehicle')
                ):
                    flags.add('service_or_restricted')
                if any(best[tag] not in (None, '', 'no') for tag in ('bridge', 'tunnel')) or (
                    best['layer'] not in (None, '') and float(best['layer']) != 0
                ):
                    flags.add('grade_separated')
                if best['diff'] is not None and best['diff'] > 30:
                    flags.add('poor_heading_alignment')
                if best['directed'] is not None and best['directed'] > 90 and best['oneway'] == 'yes':
                    flags.add('camera_against_way_direction')
            osm_id = best['osm_id'] if best else None
            overture_id, fallback, grade = self._overture(photo, osm_id)
            if fallback:
                flags.add('overture_spatial_only')
            if grade:
                flags.add('grade_separated')
            links[photo.photo_id] = PhotoRoadLink(
                photo_id=photo.photo_id, osm_way_id=osm_id, overture_id=overture_id,
                distance_m=best['distance_2180'] if best else None,
                heading_diff_deg=best['diff'] if best else None,
                candidate_count=len(candidates), flags=sorted(flags), link_source='own',
            )
        return links


def _compare_candidates(a: dict, b: dict) -> int:
    if abs(a['rank'] - b['rank']) >= 1e-9:
        return -1 if a['rank'] < b['rank'] else 1
    a_key, b_key = (a['distance_2180'], a['osm_id']), (b['distance_2180'], b['osm_id'])
    return (a_key > b_key) - (a_key < b_key)

