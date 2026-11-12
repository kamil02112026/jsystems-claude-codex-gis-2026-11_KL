"""Input profile for the run (PRD F2.3 for the signs dataset, §7 sample-bias note; ADR-004 §3.6 section 2)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mapqa.contract.bundle import SignsBundle
from mapqa.normalize.maxspeed import normalize_maxspeed

SAMPLE_NOTE = (
    "Próbka jest obciążona: zestaw signs dobrano przez widoczne znaki, a drogi przy zdjęciach mają maxspeed "
    "znacznie częściej niż całe OSM (95% vs 16,3% w profilu danych). Wyników nie uogólniamy na całe miasto."
)


@dataclass(frozen=True)
class Completeness:
    numerator: int  # links with a usable OSM speed (number or PL:* default)
    denominator: int  # all sign photos
    with_number: int  # links with a numeric maxspeed
    implicit_without_number: int  # value only from a PL:* default

    def text(self) -> str:
        pct = 100 * self.numerator / self.denominator if self.denominator else 0.0
        return f"{pct:.1f}% ({self.numerator}/{self.denominator})".replace(".", ",")


@dataclass
class Profile:
    counts: dict[str, dict[str, int]]
    rejected_by_reason: dict[str, int]
    maxspeed: Completeness
    warnings: list[str] = field(default_factory=list)
    sample_note: str = SAMPLE_NOTE


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
        value = normalize_maxspeed(lk.maxspeed, maxspeed_type=lk.maxspeed_type, source_maxspeed=lk.source_maxspeed)
        if value.status == "ok":
            usable += 1
            if lk.maxspeed:
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
