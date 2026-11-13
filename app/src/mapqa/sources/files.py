"""`files` source adapter for local course data (ADR-001 §3.3). Read-only."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from mapqa.config.schema import FilesSource
from mapqa.contract.bundle import Bbox, SignLink, SignRecord, SignsBundle
from mapqa.contract.db import connect, sql_path
from mapqa.contract.errors import SourceUnavailable
from mapqa.contract.models import RejectedRecord, SourceDescriptor

TABLE_FILES = {
    "osm_roads": "osm_roads.parquet",
    "overture_segments": "overture_segments.parquet",
    "photos": "photos.csv",
    "photo_road_links": "photo_road_links.csv",
    "traffic_signs": "traffic_signs.geojson",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _opt(value: str | None) -> str | None:
    return value if value not in (None, "") else None


def _opt_float(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


class FilesAdapter:
    def __init__(self, name: str, source: FilesSource, cwd: Path | None = None) -> None:
        self.name = name
        root = Path(source.path)
        self.root = root if root.is_absolute() else (cwd or Path.cwd()) / root

    def _require_root(self) -> None:
        if not self.root.is_dir():
            raise SourceUnavailable(
                f"Katalog danych źródła '{self.name}' nie istnieje: {self.root}",
                hint="Sprawdź pole path w konfiguracji albo uruchom polecenie z katalogu głównego repozytorium.",
            )

    def describe(self) -> SourceDescriptor:
        return SourceDescriptor(name=self.name, type="files", access="local", tables_or_paths=[str(self.root)])

    # ---- sources check (F8.9) -------------------------------------------------------------
    def check(self, bbox: Bbox) -> dict[str, dict[str, int]]:
        self._require_root()
        con = connect(self.root)
        p = {k: sql_path(self.root / v) for k, v in TABLE_FILES.items()}
        env = "ST_MakeEnvelope(?, ?, ?, ?)"
        args = [bbox.minx, bbox.miny, bbox.maxx, bbox.maxy]
        point = "longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?"
        pargs = [bbox.minx, bbox.maxx, bbox.miny, bbox.maxy]
        queries = {
            "osm_roads": (f"SELECT count(*), count(*) FILTER (WHERE ST_Intersects(geometry, {env})) FROM read_parquet({p['osm_roads']})", args),
            "overture_segments": (f"SELECT count(*), count(*) FILTER (WHERE ST_Intersects(geometry, {env})) FROM read_parquet({p['overture_segments']})", args),
            "photos": (f"SELECT count(*), count(*) FILTER (WHERE {point}) FROM read_csv({p['photos']})", pargs),
            "photo_road_links": (
                f"SELECT count(*), count(*) FILTER (WHERE {point}) FROM read_csv({p['photo_road_links']}) l "
                f"JOIN read_csv({p['photos']}) USING (photo_id)",
                pargs,
            ),
            "traffic_signs": (f"SELECT count(*), count(*) FILTER (WHERE ST_Intersects(geom, {env})) FROM ST_Read({p['traffic_signs']})", args),
        }
        out: dict[str, dict[str, int]] = {}
        for table, (sql, params) in queries.items():
            total, in_bbox = con.execute(sql, params).fetchone()
            out[table] = {"total": int(total), "in_bbox": int(in_bbox)}
        return out

    # ---- signs dataset (MVP) ---------------------------------------------------------------
    def load_signs(self, bbox: Bbox | None) -> SignsBundle:
        self._require_root()
        signs_dir = self.root / "signs"
        signs_csv, nearest_csv = signs_dir / "signs.csv", signs_dir / "nearest_osm.csv"
        for f in (signs_csv, nearest_csv):
            if not f.is_file():
                raise SourceUnavailable(f"Brak pliku zestawu signs: {f}")
        files_read = [str(signs_csv), str(nearest_csv)]
        rejected: list[RejectedRecord] = []
        records: list[SignRecord] = []

        with open(signs_csv, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            lon, lat = float(row["longitude"]), float(row["latitude"])
            if bbox is not None and not bbox.contains(lon, lat):
                rejected.append(RejectedRecord(dataset="signs", record_id=row["photo_id"], reason="outside_bbox"))
                continue
            rel = f"signs/crops/{row['photo_id']}.jpg"
            path = self.root / rel
            status = "ok"
            if not path.is_file():
                status = "missing_file"
                rejected.append(RejectedRecord(dataset="signs", record_id=row["photo_id"], reason="missing_file", detail=rel))
            else:
                files_read.append(str(path))
                if _sha256(path).lower() != row["crop_sha256"].strip().lower():
                    status = "hash_mismatch"
                    rejected.append(RejectedRecord(dataset="signs", record_id=row["photo_id"], reason="hash_mismatch", detail=rel))
            records.append(
                SignRecord(
                    photo_id=row["photo_id"],
                    area=row.get("area", ""),
                    longitude=lon,
                    latitude=lat,
                    captured_at=row.get("captured_at", ""),
                    heading=_opt_float(row.get("compass_angle")),
                    author=row.get("creator", ""),
                    license=row.get("license", ""),
                    source_url=row.get("source_url", ""),
                    sequence=row.get("sequence", ""),
                    crop_path=rel,
                    crop_sha256=row["crop_sha256"].strip().lower(),
                    image_status=status,  # type: ignore[arg-type]
                )
            )

        kept = {r.photo_id for r in records}
        with open(nearest_csv, encoding="utf-8", newline="") as handle:
            near = [r for r in csv.DictReader(handle) if r["photo_id"] in kept]
        types = self._osm_type_tags({int(r["osm_way_id"]) for r in near if r.get("osm_way_id")})
        if types is not None:
            files_read.append(str(self.root / "osm_roads.parquet"))
        links = []
        for r in near:
            way = int(r["osm_way_id"]) if r.get("osm_way_id") else None
            t_type, t_source = (types or {}).get(way, (None, None)) if way is not None else (None, None)
            links.append(
                SignLink(
                    photo_id=r["photo_id"],
                    osm_way_id=way,
                    distance_m=_opt_float(r.get("distance_m")),
                    heading_diff_deg=_opt_float(r.get("heading_diff_deg")),
                    highway=_opt(r.get("highway")),
                    maxspeed=_opt(r.get("maxspeed")),
                    maxspeed_forward=_opt(r.get("maxspeed_forward")),
                    maxspeed_backward=_opt(r.get("maxspeed_backward")),
                    maxspeed_conditional=_opt(r.get("maxspeed_conditional")),
                    oneway=_opt(r.get("oneway")),
                    candidate_count=int(r.get("candidate_count") or 0),
                    match_flags=tuple(f.strip() for f in (r.get("match_flags") or "").split(";") if f.strip()),
                    osm_source=r.get("source", ""),
                    osm_timestamp=_opt(r.get("osm_timestamp")),
                    maxspeed_type=t_type,
                    source_maxspeed=t_source,
                )
            )
        return SignsBundle(signs=records, links=links, rejected=rejected, files_read=files_read)

    def _osm_type_tags(self, way_ids: set[int]) -> dict[int, tuple[str | None, str | None]] | None:
        """maxspeed:type and source:maxspeed for the given ways from osm_roads.parquet (plan decision U1)."""
        parquet = self.root / "osm_roads.parquet"
        if not way_ids or not parquet.is_file():
            return None
        con = connect(self.root)
        rows = con.execute(
            "SELECT osm_id, json_extract_string(tags, '$.\"maxspeed:type\"'), json_extract_string(tags, '$.\"source:maxspeed\"') "
            f"FROM read_parquet({sql_path(parquet)}) WHERE list_contains(?, osm_id)",
            [sorted(way_ids)],
        ).fetchall()
        return {int(r[0]): (r[1], r[2]) for r in rows}
