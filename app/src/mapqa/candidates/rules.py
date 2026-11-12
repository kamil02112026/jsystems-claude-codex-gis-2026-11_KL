"""Candidate rules (ADR-004 §3.1; ADR-000 D10-I1). MVP: `speed_limit` only."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from mapqa.candidates.priority import priority
from mapqa.candidates.reasons import candidate_reason
from mapqa.contract.models import AttributeValue, Candidate, CascadeResult, ModelAttempt, PhotoRoadLink
from mapqa.normalize.speed import speeds_equal
from mapqa.questions.catalog import SPEED_LIMIT_VALUE

ATTRIBUTE = "speed_limit"
# TODO(P3): `sources_disagree_photo_supports` and `sources_only` need Overture values.


@dataclass(frozen=True)
class CandidateInput:
    """One photo x attribute, with everything needed for a candidate or a queue item."""

    photo_id: str
    link: PhotoRoadLink
    osm: AttributeValue
    cascade: CascadeResult
    attribute: str = ATTRIBUTE
    photo_path: str = ""
    photo_captured_at: str = ""
    photo_author: str = ""
    photo_license: str = ""
    photo_source_url: str = ""


def resolving_attempt(cascade: CascadeResult) -> ModelAttempt | None:
    """Last attempt of the resolving level that gave the final answer."""
    if cascade.resolved_by not in ("1", "2"):
        return None
    level = int(cascade.resolved_by)
    return next(
        (a for a in reversed(cascade.attempts) if a.level == level and a.answer == cascade.final_answer),
        None,
    )


def confident_value(cascade: CascadeResult) -> str | None:
    """Confident value reading: resolved and answer is a value option (D10-I1)."""
    if cascade.final_status == "resolved" and cascade.final_answer in SPEED_LIMIT_VALUE.value_options:
        return cascade.final_answer
    return None


def _rule(answer: str, osm: AttributeValue) -> str | None:
    if osm.status == "missing":
        return "osm_missing_photo_confident"
    if osm.status == "ok" and osm.normalized is not None:
        return None if speeds_equal(float(answer), float(osm.normalized)) else "photo_vs_osm"
    return None


def build_candidates(inputs: Iterable[CandidateInput]) -> list[Candidate]:
    result: list[Candidate] = []
    for inp in inputs:
        if inp.link.osm_way_id is None:
            continue
        answer = confident_value(inp.cascade)
        if answer is None:
            continue
        rule = _rule(answer, inp.osm)
        if rule is None:
            continue
        result.append(
            Candidate(
                attribute=inp.attribute,
                rule=rule,  # type: ignore[arg-type]
                priority=priority(inp.cascade.resolved_by, inp.link.flags, inp.osm.flags),
                reason_pl=candidate_reason(answer, resolving_attempt(inp.cascade), inp.osm, inp.link.flags),
                photo_id=inp.photo_id,
                osm_way_id=inp.link.osm_way_id,
            )
        )
    return result
