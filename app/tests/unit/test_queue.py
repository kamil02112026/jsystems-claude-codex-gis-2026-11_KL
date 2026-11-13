"""Manual queue items, ids and ordering (ADR-004 §3.4; QUE-01, QUE-02)."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from mapqa.candidates.queue import COLUMNS, QueueItem, build_queue, queue_id_collisions
from mapqa.candidates.rules import CandidateInput, build_candidates
from mapqa.contract.models import AttributeValue, CascadeResult, ModelAttempt, PhotoRoadLink
from mapqa.normalize.maxspeed import normalize_maxspeed

EXPECTED_COLUMNS = (
    "item_id,typ,atrybut,priorytet,powod,photo_id,photo_path,photo_captured_at,photo_author,"
    "photo_license,photo_source_url,osm_way_id,overture_id,osm_raw,osm_normalized,overture_raw,"
    "overture_normalized,l1_model,l1_answer,l1_probability,l1_status,l2_model,l2_answer,"
    "l2_probability,l2_status,resolved_by,final_status,link_flags,decyzja,wartość_z_terenu,komentarz"
).split(",")


def make_input(
    answer: str | None = "40",
    osm: AttributeValue | None = None,
    *,
    resolved_by: str | None = "1",
    flags: list[str] | None = None,
    way: int | None = 7,
    final_status: str = "resolved",
    photo_id: str = "p1",
    sha: str = "a",
    attempts: list[ModelAttempt] | None = None,
) -> CandidateInput:
    level = 2 if resolved_by == "2" else 1
    return CandidateInput(
        photo_id=photo_id,
        link=PhotoRoadLink(photo_id=photo_id, osm_way_id=way, flags=flags or [], link_source="provided"),
        osm=osm if osm is not None else normalize_maxspeed("50"),
        cascade=CascadeResult(
            photo_sha256=sha * 64,
            question_id="speed_limit_value",
            attempts=attempts
            if attempts is not None
            else [ModelAttempt(level=level, model="m", answer=answer, probability=0.93, status="confident")],
            final_status=final_status,  # type: ignore[arg-type]
            resolved_by=resolved_by,  # type: ignore[arg-type]
            final_answer=answer,
        ),
    )


def unresolved(
    status: str, *, way: int | None = 7, osm: AttributeValue | None = None, photo_id: str = "u1"
) -> CandidateInput:
    attempts = [
        ModelAttempt(level=1, model="m1", answer="40", probability=0.5, status="below_threshold"),
        ModelAttempt(level=2, model="m2", answer=None, status="invalid_response"),
    ]
    return make_input(
        None, osm, resolved_by="human", final_status=status, way=way, photo_id=photo_id, sha="b", attempts=attempts
    )


def test_columns_exact() -> None:
    assert list(COLUMNS) == EXPECTED_COLUMNS


def test_candidate_item_fields() -> None:
    inp = replace(
        make_input(flags=["boundary_crossing", "service_way"]),
        photo_path="images/p1.jpg",
        photo_author="Jan, K.",
    )
    [item] = build_queue(build_candidates([inp]), [inp])
    assert item.typ == "kandydat_rozbieżności"
    assert item.atrybut == "speed_limit"
    assert item.priorytet == "średni"
    assert item.photo_path == "images/p1.jpg" and item.photo_author == "Jan, K."
    assert item.osm_way_id == "7"
    assert item.osm_raw == "50" and item.osm_normalized == "50"
    assert item.l1_model == "m" and item.l1_answer == "40" and item.l1_status == "confident"
    assert item.resolved_by == "1" and item.final_status == "resolved"
    assert item.link_flags == "boundary_crossing;service_way"
    assert (item.decyzja, item.wartość_z_terenu, item.komentarz) == ("", "", "")
    row = item.as_row()
    assert len(row) == len(COLUMNS) and row[-3:] == ("", "", "")


def test_implicit_osm_normalized_suffix() -> None:
    inp = make_input("40", normalize_maxspeed(None, maxspeed_type="PL:urban"))
    [item] = build_queue(build_candidates([inp]), [inp])
    assert item.osm_normalized == "50 (implicit)"


def test_item_id_formula() -> None:
    inp = make_input()
    [item] = build_queue(build_candidates([inp]), [inp])
    expected = hashlib.sha256(f"{'a' * 64}|speed_limit|7".encode()).hexdigest()[:16]
    assert item.item_id == expected and len(expected) == 16


def test_no_collision_ids_unchanged_and_no_collisions_reported() -> None:
    a = make_input("40", photo_id="a", sha="1")
    b = make_input("40", photo_id="b", sha="2")
    q = build_queue(build_candidates([a, b]), [a, b])
    expected = {
        hashlib.sha256(f"{sha * 64}|speed_limit|7".encode()).hexdigest()[:16] for sha in ("1", "2")
    }
    assert {i.item_id for i in q} == expected
    assert queue_id_collisions(q) == []


def test_same_sha_same_road_gets_distinct_deterministic_ids() -> None:
    a = make_input("40", photo_id="p1", sha="a")
    b = make_input("40", photo_id="p2", sha="a")
    q1 = build_queue(build_candidates([a, b]), [a, b])
    ids = [i.item_id for i in q1]
    assert len(ids) == 2 and len(set(ids)) == 2
    expected = {
        hashlib.sha256(f"{'a' * 64}|speed_limit|7|{pid}".encode()).hexdigest()[:16] for pid in ("p1", "p2")
    }
    assert set(ids) == expected
    rev = [b, a]
    q2 = build_queue(build_candidates(rev), rev)
    assert ids == [i.item_id for i in q2]
    assert queue_id_collisions(q1) == []
    forced = [replace(i, item_id="dup") for i in q1]
    assert queue_id_collisions(forced) == ["p1", "p2"]


@pytest.mark.parametrize("status", ["abstain", "model_unavailable", "budget_exceeded", "image_out_of_bounds"])
def test_que01_unresolved_items(status: str) -> None:
    [item] = build_queue([], [unresolved(status)])
    assert item.typ == "nierozstrzygnięty_odczyt"
    assert item.priorytet == "średni"  # OSM maxspeed=50 ok
    assert item.final_status == status and item.resolved_by == "human"
    assert item.powod.startswith("Brak pewnego odczytu: poziom 1 40 p=0,50 (below_threshold), poziom 2")
    assert item.l2_status == "invalid_response"


def test_unresolved_priority_low_without_osm_value() -> None:
    [item] = build_queue([], [unresolved("abstain", osm=AttributeValue(status="missing"))])
    assert item.priorytet == "niski"


def test_que01_skipped_no_model_and_no_road() -> None:
    assert build_queue([], [unresolved("skipped_no_model")]) == []
    assert build_queue([], [unresolved("abstain", way=None)]) == []


def test_resolved_agreement_gives_no_item() -> None:
    inp = make_input("50")
    assert build_queue(build_candidates([inp]), [inp]) == []


def test_que02_stable_ids_and_order() -> None:
    a = make_input("40", photo_id="a", sha="1")
    b = make_input("30", photo_id="b", resolved_by="2", sha="2")
    u = unresolved("abstain")
    inputs = [a, b, u]
    q1 = build_queue(build_candidates(inputs), inputs)
    rev = list(reversed(inputs))
    q2 = build_queue(build_candidates(rev), rev)
    assert [i.item_id for i in q1] == [i.item_id for i in q2]
    assert [(i.priorytet, i.typ) for i in q1] == [
        ("wysoki", "kandydat_rozbieżności"),
        ("średni", "kandydat_rozbieżności"),
        ("średni", "nierozstrzygnięty_odczyt"),
    ]


def test_queue_item_fields_match_columns() -> None:
    assert list(QueueItem.__dataclass_fields__) == EXPECTED_COLUMNS
