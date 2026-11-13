"""Data handed from a source adapter to the pipeline (ADR-000 §5 DataBundle, ADR-001 §4).

The MVP slice works on the `signs` dataset only, so the bundle carries typed records for it.
Reference labels are deliberately absent (ADR-004 §3.10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mapqa.contract.errors import ValidationError
from mapqa.contract.models import RejectedRecord

ImageStatus = Literal["ok", "missing_file", "hash_mismatch"]


@dataclass(frozen=True)
class Bbox:
    minx: float
    miny: float
    maxx: float
    maxy: float

    @classmethod
    def parse(cls, text: str) -> Bbox:
        """Parse `minx,miny,maxx,maxy` in WGS84 and validate (PRD F1.1)."""
        try:
            parts = [float(p) for p in text.split(",")]
        except ValueError:
            raise ValidationError("Niepoprawny bbox: oczekiwano czterech liczb minx,miny,maxx,maxy", code="invalid_bbox") from None
        if len(parts) != 4:
            raise ValidationError("Niepoprawny bbox: oczekiwano czterech liczb minx,miny,maxx,maxy", code="invalid_bbox")
        bbox = cls(*parts)
        if not (-180 <= bbox.minx <= 180 and -180 <= bbox.maxx <= 180 and -90 <= bbox.miny <= 90 and -90 <= bbox.maxy <= 90):
            raise ValidationError("Niepoprawny bbox: współrzędne poza zakresem WGS84", code="invalid_bbox")
        if bbox.minx >= bbox.maxx or bbox.miny >= bbox.maxy:
            raise ValidationError("Niepoprawny bbox: odwrócone granice (minx < maxx, miny < maxy)", code="invalid_bbox")
        return bbox

    def contains(self, lon: float, lat: float) -> bool:
        return self.minx <= lon <= self.maxx and self.miny <= lat <= self.maxy

    def as_text(self) -> str:
        return f"{self.minx:g},{self.miny:g},{self.maxx:g},{self.maxy:g}"


DATA_BBOX = Bbox(19.80, 49.95, 20.15, 50.15)


@dataclass(frozen=True)
class SignRecord:
    """One photo of the `signs` set (signs/signs.csv mapped to the photos contract)."""

    photo_id: str
    area: str
    longitude: float
    latitude: float
    captured_at: str
    heading: float | None  # from compass_angle; null stays null (F2.4)
    author: str  # from creator
    license: str
    source_url: str
    sequence: str
    crop_path: str  # path relative to the data directory
    crop_sha256: str
    image_status: ImageStatus


@dataclass(frozen=True)
class SignLink:
    """Provided photo→OSM candidate (signs/nearest_osm.csv) with OSM type tags joined (plan U1)."""

    photo_id: str
    osm_way_id: int | None
    distance_m: float | None
    heading_diff_deg: float | None
    highway: str | None
    maxspeed: str | None
    maxspeed_forward: str | None
    maxspeed_backward: str | None
    maxspeed_conditional: str | None
    oneway: str | None
    candidate_count: int
    match_flags: tuple[str, ...]
    osm_source: str
    osm_timestamp: str | None
    maxspeed_type: str | None = None
    source_maxspeed: str | None = None


@dataclass
class SignsBundle:
    signs: list[SignRecord]
    links: list[SignLink]
    rejected: list[RejectedRecord] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)  # absolute paths of every input file read


@dataclass(frozen=True)
class PhotoRecord:
    """One row of photos.csv (ADR-001 §4 `photos`). heading None means empty in the file, never 0 (F2.4)."""

    photo_id: str
    source: str
    filename: str
    longitude: float
    latitude: float
    heading: float | None
    captured_at: str
    sequence: str
    author: str
    license: str
    license_url: str
    source_url: str
    sha256: str
    is_panorama: bool
    horizontal_accuracy_m: float | None
    image_path: str | None  # relative to the data directory; None when the file is missing
    image_status: ImageStatus


@dataclass(frozen=True)
class PhotoLink:
    """One row of photo_road_links.csv (ADR-001 §4), all 11 columns."""

    photo_id: str
    osm_way_id: int | None
    overture_id: str | None
    distance_m: float | None
    way_bearing: float | None
    bearing_diff: float | None
    directed_bearing_diff: float | None
    overture_distance_m: float | None
    osm_candidate_count: int
    match_method: str
    candidate_flags: tuple[str, ...]


@dataclass
class PhotosBundle:
    photos: list[PhotoRecord]
    links: list[PhotoLink]
    rejected: list[RejectedRecord] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)  # absolute paths of every input file read
