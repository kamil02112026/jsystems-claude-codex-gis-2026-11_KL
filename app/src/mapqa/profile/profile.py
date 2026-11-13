"""Input profile for the run (PRD F2.3, F3.5, §7 sample-bias note; ADR-004 §3.6 section 2; ADR-002 MAT-07, TAC-002-02)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from mapqa.contract.bundle import PhotosBundle, SignLink, SignsBundle
from mapqa.contract.models import PhotoRoadLink
from mapqa.normalize.lit import normalize_lit
from mapqa.normalize.osm import osm_speed_value

SAMPLE_NOTE = (
    "Próbka jest obciążona: zestaw signs dobrano przez widoczne znaki, a drogi przy zdjęciach mają maxspeed "
    "znacznie częściej niż całe OSM (95% vs 16,3% w profilu danych). Wyników nie uogólniamy na całe miasto."
)
AGREEMENT_TARGET = 0.95  # TAC-002-02: below this the agreement blocks closing P1


def _percent_text(numerator: int, denominator: int) -> str:
    pct = 100 * numerator / denominator if denominator else 0.0
    return f"{pct:.1f}% ({numerator}/{denominator})".replace(".", ",")


@dataclass(frozen=True)
class Completeness:
    numerator: int  # records with a usable value
    denominator: int  # all records of the set (explicit denominator, ADR-004 §3.6)
    with_number: int = 0  # links with a numeric maxspeed
    implicit_without_number: int = 0  # value only from a PL:* default

    def text(self) -> str:
        return _percent_text(self.numerator, self.denominator)


@dataclass(frozen=True)
class Agreement:
    numerator: int  # own osm_way_id equal to the provided one
    denominator: int  # photos with an osm_way_id in both sets

    def text(self) -> str:
        return _percent_text(self.numerator, self.denominator)


@dataclass
class Profile:
    counts: dict[str, dict[str, int]]
    rejected_by_reason: dict[str, int]
    maxspeed: Completeness
    warnings: list[str] = field(default_factory=list)
    sample_note: str = SAMPLE_NOTE
    surface: Completeness | None = None
    lit: Completeness | None = None
    agreement: Agreement | None = None


def build_profile(bundle: SignsBundle, *, bbox_text: str | None) -> Profile:
    reasons = Counter(r.reason for r in bundle.rejected)
    outside = reasons.get("outside_bbox", 0)
    total = len(bundle.signs) + outside
    links = {lk.photo_id: lk for lk in bundle.links}
    usable = with_number = implicit_only = 0
    for sign in bundle.signs:
        lk = links.get(sign.photo_id)
        if lk is None:
            continue
        value = osm_speed_value(lk)  # same logic as the comparison (incl. directional tags)
        if value.status == "ok":
            usable += 1
            if lk.maxspeed or lk.maxspeed_forward or lk.maxspeed_backward:
                with_number += 1
            else:
                implicit_only += 1
    warnings = []
    if bbox_text is None:
        warnings.append("Zestaw signs nie jest filtrowany bboxem (brak jawnego --bbox; ADR-000 D10-I2).")
    return Profile(
        counts={"signs": {"total": total, "in_bbox": len(bundle.signs)}},
        rejected_by_reason=dict(sorted(reasons.items())),
        maxspeed=Completeness(usable, len(bundle.signs), with_number, implicit_only),
        warnings=warnings,
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _road_link(photo_id: str, way_id: int, tags: Mapping[str, str | None]) -> SignLink:
    """Adapt the tags of a linked road to the shape `osm_speed_value` reads (one speed logic for all sets)."""
    return SignLink(
        photo_id=photo_id,
        osm_way_id=way_id,
        distance_m=None,
        heading_diff_deg=None,
        highway=_clean(tags.get("highway")),
        maxspeed=_clean(tags.get("maxspeed")),
        maxspeed_forward=_clean(tags.get("maxspeed:forward")),
        maxspeed_backward=_clean(tags.get("maxspeed:backward")),
        maxspeed_conditional=_clean(tags.get("maxspeed:conditional")),
        oneway=None,
        candidate_count=0,
        match_flags=(),
        osm_source="",
        osm_timestamp=None,
        maxspeed_type=_clean(tags.get("maxspeed:type")),
        source_maxspeed=_clean(tags.get("source:maxspeed")),
    )


def build_photos_profile(
    bundle: PhotosBundle,
    table_counts: Mapping[str, Mapping[str, int]],
    own_links: Mapping[str, PhotoRoadLink] | None,
    bbox_text: str | None,
    *,
    road_tags: Mapping[int, Mapping[str, str | None]] | None = None,
) -> Profile:
    """Full input profile of the photos set (F2.3, F3.5).

    `road_tags` maps osm_way_id to the OSM tags of that way (from osm_roads.parquet). Without it the road
    completeness is 0 and a warning says so.
    """
    warnings: list[str] = []
    if road_tags is None:
        warnings.append("Brak tagów dróg (osm_roads.parquet): kompletność maxspeed, surface i lit nie została policzona.")
        road_tags = {}
    if bbox_text is None:
        warnings.append("Zestaw photos bez jawnego --bbox: użyto domyślnego bboxu danych (ADR-000 §6).")

    reasons = Counter(r.reason for r in bundle.rejected)
    links = {lk.photo_id: lk for lk in bundle.links}
    denominator = len(bundle.photos)
    speed_ok = with_number = implicit_only = surface_ok = lit_ok = 0
    for photo in bundle.photos:
        link = links.get(photo.photo_id)
        way_id = link.osm_way_id if link else None
        if way_id is None:
            continue
        tags = road_tags.get(way_id, {})
        value = osm_speed_value(_road_link(photo.photo_id, way_id, tags))
        if value.status == "ok":
            speed_ok += 1
            if _clean(tags.get("maxspeed")) or _clean(tags.get("maxspeed:forward")) or _clean(tags.get("maxspeed:backward")):
                with_number += 1
            else:
                implicit_only += 1
        if _clean(tags.get("surface")) is not None:
            surface_ok += 1
        if normalize_lit(tags.get("lit")).status == "ok":
            lit_ok += 1

    agreement = None
    if own_links is not None:
        pairs = [
            (own_links[lk.photo_id].osm_way_id, lk.osm_way_id)
            for lk in bundle.links
            if lk.photo_id in own_links and own_links[lk.photo_id].osm_way_id is not None and lk.osm_way_id is not None
        ]
        agreement = Agreement(numerator=sum(own == provided for own, provided in pairs), denominator=len(pairs))
        if agreement.denominator and agreement.numerator / agreement.denominator < AGREEMENT_TARGET:
            warnings.append(
                f"Zgodność własnego dopasowania z photo_road_links.csv: {agreement.text()} (poniżej 95%, TAC-002-02); "
                "blokuje zamknięcie P1 do wyjaśnienia różnic."
            )

    return Profile(
        counts={name: dict(values) for name, values in table_counts.items()},
        rejected_by_reason=dict(sorted(reasons.items())),
        maxspeed=Completeness(speed_ok, denominator, with_number, implicit_only),
        warnings=warnings,
        surface=Completeness(surface_ok, denominator),
        lit=Completeness(lit_ok, denominator),
        agreement=agreement,
    )
