"""Manual verification queue items (ADR-004 §3.4; PRD F6.5-F6.7). CSV writing is T13."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields

from mapqa.candidates.priority import unresolved_priority
from mapqa.candidates.reasons import is_implicit, raw_text, unresolved_reason
from mapqa.candidates.rules import CandidateInput
from mapqa.contract.models import AttributeValue, Candidate, ModelAttempt

TYPE_CANDIDATE = "kandydat_rozbieżności"
TYPE_UNRESOLVED = "nierozstrzygnięty_odczyt"
UNRESOLVED_STATUSES = frozenset({"abstain", "model_unavailable", "budget_exceeded", "image_out_of_bounds"})
_PRIORITY_RANK = {"wysoki": 0, "średni": 1, "niski": 2}
_TYPE_RANK = {TYPE_CANDIDATE: 0, TYPE_UNRESOLVED: 1}


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    typ: str
    atrybut: str
    priorytet: str
    powod: str
    photo_id: str
    photo_path: str
    photo_captured_at: str
    photo_author: str
    photo_license: str
    photo_source_url: str
    osm_way_id: str
    overture_id: str
    osm_raw: str
    osm_normalized: str
    overture_raw: str
    overture_normalized: str
    l1_model: str
    l1_answer: str
    l1_probability: str
    l1_status: str
    l2_model: str
    l2_answer: str
    l2_probability: str
    l2_status: str
    resolved_by: str
    final_status: str
    link_flags: str
    decyzja: str = ""
    wartość_z_terenu: str = ""
    komentarz: str = ""

    def as_row(self) -> tuple[str, ...]:
        return tuple(getattr(self, name) for name in COLUMNS)


COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(QueueItem))


def make_item_id(photo_sha256: str, attribute: str, osm_way_id: int | None, photo_id: str | None = None) -> str:
    """Stable item id (PRD F6.7). `photo_id` is appended only to disambiguate collisions."""
    key = f"{photo_sha256}|{attribute}|{osm_way_id}"
    if photo_id is not None:
        key = f"{key}|{photo_id}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def queue_id_collisions(items: Iterable[QueueItem]) -> list[str]:
    """Sorted photo_ids of every item whose item_id is shared with another item."""
    groups = Counter(item.item_id for item in items)
    return sorted({item.photo_id for item in items if groups[item.item_id] > 1})


def _osm_raw(osm: AttributeValue) -> str:
    if osm.raw is None:
        return ""
    return raw_text(osm, sep=";") if isinstance(osm.raw, dict) else str(osm.raw)


def _osm_normalized(osm: AttributeValue) -> str:
    value = osm.normalized
    if value is None:
        return ""
    text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    return f"{text} (implicit)" if is_implicit(osm) else text


def _level(attempts: Sequence[ModelAttempt], level: int) -> tuple[str, str, str, str]:
    a = next((x for x in reversed(attempts) if x.level == level), None)
    if a is None:
        return "", "", "", ""
    prob = "" if a.probability is None else str(a.probability)
    return a.model, a.answer or "", prob, a.status


def _base_id(inp: CandidateInput) -> str:
    return make_item_id(inp.cascade.photo_sha256, inp.attribute, inp.link.osm_way_id)


def _item(inp: CandidateInput, typ: str, prio: str, reason: str, *, salted: bool = False) -> QueueItem:
    c = inp.cascade
    l1, l2 = _level(c.attempts, 1), _level(c.attempts, 2)
    item_id = make_item_id(c.photo_sha256, inp.attribute, inp.link.osm_way_id, inp.photo_id if salted else None)
    return QueueItem(
        item_id=item_id,
        typ=typ,
        atrybut=inp.attribute,
        priorytet=prio,
        powod=reason,
        photo_id=inp.photo_id,
        photo_path=inp.photo_path,
        photo_captured_at=inp.photo_captured_at,
        photo_author=inp.photo_author,
        photo_license=inp.photo_license,
        photo_source_url=inp.photo_source_url,
        osm_way_id="" if inp.link.osm_way_id is None else str(inp.link.osm_way_id),
        overture_id=inp.link.overture_id or "",
        osm_raw=_osm_raw(inp.osm),
        osm_normalized=_osm_normalized(inp.osm),
        overture_raw="",
        overture_normalized="",
        l1_model=l1[0],
        l1_answer=l1[1],
        l1_probability=l1[2],
        l1_status=l1[3],
        l2_model=l2[0],
        l2_answer=l2[1],
        l2_probability=l2[2],
        l2_status=l2[3],
        resolved_by=c.resolved_by or "",
        final_status=c.final_status,
        link_flags=";".join(inp.link.flags),
    )


def _sort_key(item: QueueItem) -> tuple[int, int, str, str]:
    return _PRIORITY_RANK[item.priorytet], _TYPE_RANK[item.typ], item.atrybut, item.item_id


def build_queue(candidates: Iterable[Candidate], inputs: Iterable[CandidateInput]) -> list[QueueItem]:
    """Candidate items plus `nierozstrzygnięty_odczyt` items (D10-I4), deterministically sorted.

    `inputs` is the full list of photo x attribute inputs: it supplies the cascade/link/OSM
    details of each candidate and is scanned for unresolved readings.
    """
    by_key = {(i.photo_id, i.attribute): i for i in inputs}
    specs: list[tuple[CandidateInput, str, str, str]] = [
        (by_key[(c.photo_id, c.attribute)], TYPE_CANDIDATE, c.priority, c.reason_pl) for c in candidates
    ]
    for inp in by_key.values():
        if inp.link.osm_way_id is None or inp.cascade.final_status not in UNRESOLVED_STATUSES:
            continue
        reason = unresolved_reason(inp.cascade.attempts, inp.cascade.final_status, inp.link.flags)
        specs.append((inp, TYPE_UNRESOLVED, unresolved_priority(inp.osm.status), reason))
    base_counts = Counter(_base_id(inp) for inp, *_ in specs)
    items = [
        _item(inp, typ, prio, reason, salted=base_counts[_base_id(inp)] > 1)
        for inp, typ, prio, reason in specs
    ]
    return sorted(items, key=_sort_key)
