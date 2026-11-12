"""Baseline detektora Mapillary i rozbieżności znak - OSM (PRD §7, §9)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from mapqa.evaluation.labels import NO_SIGN, Label
from mapqa.evaluation.metrics import Metric, make_metric
from mapqa.normalize.speed import speeds_equal

_SPEED_CLASS = re.compile(r"^regulatory--maximum-speed-limit-(\d+)--")


@dataclass(frozen=True)
class SignRow:
    sequence: str
    mapillary_value: str


class OsmDiscrepancies(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numeric_certain: int
    equal: int
    differ: int
    no_maxspeed: int


def mapillary_speed(value: str) -> str | None:
    """Klasa Mapillary -> odpowiedź: liczba, `brak znaku` (inna klasa) albo None (brak detekcji)."""
    value = value.strip()
    if not value:
        return None
    m = _SPEED_CLASS.match(value)
    return m.group(1) if m else NO_SIGN


def load_signs(signs_path: Path) -> dict[str, SignRow]:
    with signs_path.open(encoding="utf-8", newline="") as fh:
        return {
            r["photo_id"]: SignRow(r["sequence"].strip(), r["mapillary_value"].strip()) for r in csv.DictReader(fh)
        }


def mapillary_baseline(
    labels: dict[str, Label],
    signs: dict[str, SignRow],
    split: dict[str, str] | None = None,
    split_name: str | None = None,
) -> Metric:
    """Trafność detektora wobec etykiet `certain` z detekcją."""
    num = den = 0
    for photo_id, label in labels.items():
        if label.status != "certain" or photo_id not in signs:
            continue
        if split_name is not None and (split or {}).get(photo_id) != split_name:
            continue
        predicted = mapillary_speed(signs[photo_id].mapillary_value)
        if predicted is None:
            continue
        den += 1
        num += predicted == label.value
    return make_metric(num, den)


def osm_discrepancies(labels: dict[str, Label], nearest_osm_path: Path) -> OsmDiscrepancies:
    """Liczbowe etykiety `certain` vs zwykły `maxspeed` najbliższej drogi OSM."""
    with nearest_osm_path.open(encoding="utf-8", newline="") as fh:
        maxspeed = {r["photo_id"]: r["maxspeed"].strip() for r in csv.DictReader(fh)}
    equal = differ = missing = 0
    for photo_id, label in labels.items():
        if label.status != "certain" or not label.value.isdigit():
            continue
        raw = maxspeed.get(photo_id, "")
        if not raw:
            missing += 1
            continue
        try:
            same = speeds_equal(float(label.value), float(raw))
        except ValueError:
            same = False
        equal += same
        differ += not same
    return OsmDiscrepancies(numeric_certain=equal + differ + missing, equal=equal, differ=differ, no_maxspeed=missing)
