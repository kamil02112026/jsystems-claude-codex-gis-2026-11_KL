"""Candidate rules, priorities and reasons (ADR-004 §3.1-3.3; CND-01..07)."""

from __future__ import annotations

import pytest

from mapqa.candidates.priority import priority
from mapqa.candidates.rules import CandidateInput, build_candidates
from mapqa.contract.models import AttributeValue, CascadeResult, ModelAttempt, PhotoRoadLink
from mapqa.normalize.maxspeed import normalize_maxspeed


def make_input(
    answer: str | None = "40",
    osm: AttributeValue | None = None,
    *,
    resolved_by: str | None = "1",
    flags: list[str] | None = None,
    way: int | None = 7,
    final_status: str = "resolved",
    probability: float = 0.93,
    photo_id: str = "p1",
) -> CandidateInput:
    level = 2 if resolved_by == "2" else 1
    attempt = ModelAttempt(
        level=level, model="m", answer=answer, probability=probability, status="confident"
    )
    return CandidateInput(
        photo_id=photo_id,
        link=PhotoRoadLink(photo_id=photo_id, osm_way_id=way, flags=flags or [], link_source="provided"),
        osm=osm if osm is not None else normalize_maxspeed("50"),
        cascade=CascadeResult(
            photo_sha256="a" * 64,
            question_id="speed_limit_value",
            attempts=[attempt],
            final_status=final_status,  # type: ignore[arg-type]
            resolved_by=resolved_by,  # type: ignore[arg-type]
            final_answer=answer,
        ),
    )


def test_cnd01_photo_vs_osm_high() -> None:
    [c] = build_candidates([make_input()])
    assert c.rule == "photo_vs_osm"
    assert c.priority == "wysoki"
    assert c.attribute == "speed_limit"
    assert c.photo_id == "p1" and c.osm_way_id == 7
    assert c.reason_pl == "Znak 40 na zdjęciu (poziom 1, p=0,93), OSM `maxspeed=50`."


def test_cnd01_boundary_crossing_still_high() -> None:
    [c] = build_candidates([make_input(flags=["boundary_crossing"])])
    assert c.priority == "wysoki"
    assert c.reason_pl.endswith("Flagi: `boundary_crossing`.")


@pytest.mark.parametrize(
    "kwargs",
    [{"resolved_by": "2"}, {"flags": ["ambiguous_candidates"]}],
)
def test_cnd02_medium(kwargs: dict) -> None:
    [c] = build_candidates([make_input(**kwargs)])
    assert c.priority == "średni"


def test_cnd02_conditional_rule_medium() -> None:
    osm = normalize_maxspeed("50", conditional="30 @ (Mo-Fr 07:00-16:00)")
    [c] = build_candidates([make_input("40", osm)])
    assert c.priority == "średni"


def test_cnd02_level2_reason_and_flags_list() -> None:
    [c] = build_candidates([make_input(resolved_by="2", flags=["ambiguous_candidates", "service_way"])])
    assert "(poziom 2, p=0,93)" in c.reason_pl
    assert c.reason_pl.endswith("Flagi: `ambiguous_candidates`, `service_way`.")


def test_priority_function() -> None:
    assert priority("1", [], []) == "wysoki"
    assert priority("1", ["boundary_crossing"], ["type_value_conflict"]) == "wysoki"
    assert priority("2", [], []) == "średni"
    assert priority("1", ["service_way"], []) == "średni"
    assert priority("1", [], ["conditional_rule_present"]) == "średni"


def test_cnd03_osm_missing() -> None:
    osm = AttributeValue(status="missing")
    [c] = build_candidates([make_input("30", osm)])
    assert c.rule == "osm_missing_photo_confident"
    assert c.priority == "wysoki"
    assert c.reason_pl == "Znak 30 na zdjęciu (poziom 1, p=0,93), OSM bez `maxspeed`."


def test_cnd03_osm_not_comparable_no_candidate() -> None:
    osm = AttributeValue(status="not_comparable", note="x")
    assert build_candidates([make_input("30", osm)]) == []


@pytest.mark.parametrize("answer", ["brak znaku", "nieczytelny", "nie widać"])
def test_cnd04_answers_without_value(answer: str) -> None:
    assert build_candidates([make_input(answer)]) == []


def test_cnd05_agreement_no_candidate() -> None:
    assert build_candidates([make_input("50")]) == []


def test_cnd05_mph_differs() -> None:
    osm = normalize_maxspeed("30 mph")  # 48.28 km/h, |50 - 48.28| >= 0.5
    [c] = build_candidates([make_input("50", osm)])
    assert c.rule == "photo_vs_osm"
    assert "`maxspeed=30 mph`" in c.reason_pl


def test_cnd06_no_road() -> None:
    assert build_candidates([make_input(way=None)]) == []


def test_cnd07_implicit() -> None:
    osm = normalize_maxspeed(None, maxspeed_type="PL:urban")
    [c] = build_candidates([make_input("40", osm)])
    assert c.rule == "photo_vs_osm"
    assert "(implicit, 50 km/h)" in c.reason_pl
    assert "Porównanie z wartością domyślną, nie ze znakiem." in c.reason_pl


def test_cnd07_implicit_agreement_no_candidate() -> None:
    osm = normalize_maxspeed(None, maxspeed_type="PL:urban")
    assert build_candidates([make_input("50", osm)]) == []


@pytest.mark.parametrize(
    "status",
    ["abstain", "model_unavailable", "budget_exceeded", "image_out_of_bounds", "skipped_no_model"],
)
def test_unresolved_cascade_no_candidate(status: str) -> None:
    assert build_candidates([make_input(None, resolved_by="human", final_status=status)]) == []


def test_order_is_preserved() -> None:
    inputs = [make_input("40", photo_id="b"), make_input("30", photo_id="a")]
    assert [c.photo_id for c in build_candidates(inputs)] == ["b", "a"]
