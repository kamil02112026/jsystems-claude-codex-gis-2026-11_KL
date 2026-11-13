"""`files` source adapter for local course data (ADR-001 §3.3). Read-only."""

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path

from mapqa.config.schema import FilesSource
from mapqa.contract.bundle import DATA_BBOX, Bbox, PhotoLink, PhotoRecord, PhotosBundle, SignLink, SignRecord, SignsBundle
from mapqa.contract.db import connect, sql_path
from mapqa.contract.errors import ContractViolation, SourceUnavailable
from mapqa.contract.hashing import sha256_file
from mapqa.contract.models import RejectedRecord, SourceDescriptor

TABLE_FILES = {
    "osm_roads": "osm_roads.parquet",
    "overture_segments": "overture_segments.parquet",
    "photos": "photos.csv",
    "photo_road_links": "photo_road_links.csv",
    "traffic_signs": "traffic_signs.geojson",
}


_sha256 = sha256_file


def _coords(lon_text: str | None, lat_text: str | None) -> tuple[float, float] | None:
    """WGS84 lon/lat or None when empty, not finite or out of range (review finding: unvalidated coordinates)."""
    try:
        lon, lat = float(lon_text or ""), float(lat_text or "")
    except ValueError:
        return None
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def _opt(value: str | None) -> str | None:
    return value if value not in (None, "") else None


def _opt_float(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


def _flags(text: str | None) -> tuple[str, ...]:
    return tuple(f.strip() for f in (text or "").split(";") if f.strip())


PHOTO_IMAGE_DIRS = ("offline", "data/photos")  # ADR-001 §3.3: first existing wins


def _photo_image_rel(root: Path, filename: str) -> str | None:
    """Path relative to the data directory of the first existing image copy, or None."""
    for folder in PHOTO_IMAGE_DIRS:
        rel = f"{folder}/{filename}"
        if (root / rel).is_file():
            return rel
    return None


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
        dupes = sorted(pid for pid, n in Counter(r["photo_id"] for r in rows).items() if n > 1)
        if dupes:  # a dict would silently keep one row (review finding)
            raise ContractViolation(f"Powtórzone photo_id w signs/signs.csv: {', '.join(dupes[:5])}")
        for row in rows:
            coords = _coords(row.get("longitude"), row.get("latitude"))
            if coords is None:
                rejected.append(RejectedRecord(dataset="signs", record_id=row["photo_id"], reason="invalid_value", detail="niepoprawne współrzędne"))
                continue
            lon, lat = coords
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

    # ---- photos dataset (T32; PRD F2.1–F2.4, ADR-001 §3.3, §4) -----------------------------
    def load_photos(self, bbox: Bbox | None) -> PhotosBundle:
        self._require_root()
        photos_csv, links_csv = self.root / "photos.csv", self.root / "photo_road_links.csv"
        for f in (photos_csv, links_csv):
            if not f.is_file():
                raise SourceUnavailable(f"Brak pliku zestawu photos: {f}")
        if bbox is None:  # ADR-000 §6: --dataset photos defaults to the data bbox
            bbox = DATA_BBOX
        files_read = [str(photos_csv), str(links_csv)]
        rejected: list[RejectedRecord] = []
        records: list[PhotoRecord] = []

        with open(photos_csv, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        dupes = sorted(pid for pid, n in Counter(r["photo_id"] for r in rows).items() if n > 1)
        if dupes:
            raise ContractViolation(f"Powtórzone photo_id w photos.csv: {', '.join(dupes[:5])}")
        for row in rows:
            pid = row["photo_id"]
            coords = _coords(row.get("longitude"), row.get("latitude"))
            if coords is None:
                rejected.append(RejectedRecord(dataset="photos", record_id=pid, reason="invalid_value", detail="niepoprawne współrzędne"))
                continue
            lon, lat = coords
            if not bbox.contains(lon, lat):
                rejected.append(RejectedRecord(dataset="photos", record_id=pid, reason="outside_bbox"))
                continue
            rel = _photo_image_rel(self.root, row["filename"])
            status = "ok"
            if rel is None:
                status = "missing_file"
                rejected.append(RejectedRecord(dataset="photos", record_id=pid, reason="missing_file", detail=f"offline/{row['filename']}"))
            else:
                path = self.root / rel
                files_read.append(str(path))
                if _sha256(path).lower() != row["sha256"].strip().lower():
                    status = "hash_mismatch"
                    rejected.append(RejectedRecord(dataset="photos", record_id=pid, reason="hash_mismatch", detail=rel))
            records.append(
                PhotoRecord(
                    photo_id=pid,
                    source=row.get("source", ""),
                    filename=row["filename"],
                    longitude=lon,
                    latitude=lat,
                    heading=_opt_float(row.get("heading")),
                    captured_at=row.get("captured_at", ""),
                    sequence=row.get("sequence", ""),
                    author=row.get("author", ""),
                    license=row.get("license", ""),
                    license_url=row.get("license_url", ""),
                    source_url=row.get("source_url", ""),
                    sha256=row["sha256"].strip().lower(),
                    is_panorama=(row.get("is_panorama") or "").strip().lower() == "true",
                    horizontal_accuracy_m=_opt_float(row.get("horizontal_accuracy_m")),
                    image_path=rel,
                    image_status=status,  # type: ignore[arg-type]
                )
            )

        kept = {r.photo_id for r in records}
        with open(links_csv, encoding="utf-8", newline="") as handle:
            link_rows = [r for r in csv.DictReader(handle) if r["photo_id"] in kept]
        links = [
            PhotoLink(
                photo_id=r["photo_id"],
                osm_way_id=int(r["osm_way_id"]) if r.get("osm_way_id") else None,
                overture_id=_opt(r.get("overture_id")),
                distance_m=_opt_float(r.get("distance_m")),
                way_bearing=_opt_float(r.get("way_bearing")),
                bearing_diff=_opt_float(r.get("bearing_diff")),
                directed_bearing_diff=_opt_float(r.get("directed_bearing_diff")),
                overture_distance_m=_opt_float(r.get("overture_distance_m")),
                osm_candidate_count=int(r.get("osm_candidate_count") or 0),
                match_method=r.get("match_method", ""),
                candidate_flags=_flags(r.get("candidate_flags")),
            )
            for r in link_rows
        ]
        return PhotosBundle(photos=records, links=links, rejected=rejected, files_read=files_read)

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
