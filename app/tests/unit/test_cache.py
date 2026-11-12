"""T17: cache odpowiedzi SQLite (ADR-003 §3.7, D-003-4; CAC-02, CAC-03; ADR-000 D5)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from mapqa.cache.sqlite_cache import AnswerCache, CacheEntry, CacheKey, file_sha256


def _key(**overrides: object) -> CacheKey:
    base = dict(
        level=2,
        image_sha256="a" * 64,
        question_id="speed_limit_value",
        model="openai/gpt-6-luna",
        reasoning_effort="medium",
        prompt_version="speed_limit_value.v1-deadbeef+image_prep.v2",
    )
    base.update(overrides)
    return CacheKey(**base)  # type: ignore[arg-type]


def _entry(status: str = "confident", probability: float | None = 0.93) -> CacheEntry:
    return CacheEntry(
        parsed_answer="50",
        probability=probability,
        status=status,
        input_tokens=1200,
        output_tokens=7,
        cost_usd=Decimal("0.00005"),
        response_body='{"choices": []}',
        created_at="2026-11-12T10:00:00+00:00",
    )


@pytest.fixture
def cache(tmp_path: Path) -> AnswerCache:
    c = AnswerCache(tmp_path / "cache" / "llm_cache.sqlite")
    yield c
    c.close()


def test_open_creates_parent_dir_and_file(tmp_path: Path) -> None:
    path = tmp_path / "x" / "y" / "llm_cache.sqlite"
    AnswerCache(path).close()
    assert path.exists()


def test_put_then_get_hit(cache: AnswerCache) -> None:
    cache.put(_key(), _entry())
    got = cache.get(_key())
    assert got is not None
    assert got.parsed_answer == "50"
    assert got.probability == pytest.approx(0.93)
    assert got.status == "confident"
    assert got.input_tokens == 1200
    assert got.output_tokens == 7
    assert got.cost_usd == Decimal("0.00005")
    assert got.response_body == '{"choices": []}'
    assert got.created_at == "2026-11-12T10:00:00+00:00"


def test_miss_on_empty_cache(cache: AnswerCache) -> None:
    assert cache.get(_key()) is None


@pytest.mark.parametrize(
    "override",
    [
        {"level": 1},
        {"image_sha256": "b" * 64},
        {"question_id": "surface_paved"},
        {"model": "typesafe/jev-1.14"},
        {"reasoning_effort": "high"},
        {"prompt_version": "speed_limit_value.v2-deadbeef+image_prep.v2"},
        {"prompt_version": "speed_limit_value.v1-deadbeef+image_prep.v1"},
    ],
    ids=["level", "image", "question", "model", "effort", "prompt_version", "image_prep"],
)
def test_each_key_component_change_is_a_miss(cache: AnswerCache, override: dict[str, object]) -> None:  # CAC-02
    cache.put(_key(), _entry())
    assert cache.get(_key(**override)) is None


def test_same_image_bytes_under_other_filename_hit(cache: AnswerCache, tmp_path: Path) -> None:  # CAC-02
    data = b"\xff\xd8\xff\xe0 same jpeg bytes"
    first = tmp_path / "sign_001.jpg"
    second = tmp_path / "renamed_copy.jpg"
    first.write_bytes(data)
    second.write_bytes(data)
    assert file_sha256(first) == file_sha256(second)
    cache.put(_key(image_sha256=file_sha256(first)), _entry())
    assert cache.get(_key(image_sha256=file_sha256(second))) is not None


def test_level1_key_uses_empty_reasoning_effort(cache: AnswerCache) -> None:
    cache.put(_key(level=1, reasoning_effort=""), _entry())
    assert cache.get(_key(level=1, reasoning_effort="")) is not None
    assert cache.get(_key(level=1, reasoning_effort="medium")) is None


@pytest.mark.parametrize("status", ["model_unavailable", "budget_exceeded"])
def test_transient_statuses_are_not_stored(cache: AnswerCache, status: str) -> None:  # CAC-03
    cache.put(_key(), _entry(status=status, probability=None))
    assert cache.get(_key()) is None


@pytest.mark.parametrize("status", ["confident", "below_threshold", "invalid_response"])
def test_deterministic_statuses_are_stored(cache: AnswerCache, status: str) -> None:
    probability = None if status == "invalid_response" else 0.5
    cache.put(_key(), _entry(status=status, probability=probability))
    got = cache.get(_key())
    assert got is not None and got.status == status


def test_put_replaces_existing_entry(cache: AnswerCache) -> None:
    cache.put(_key(), _entry(probability=0.5, status="below_threshold"))
    cache.put(_key(), _entry(probability=0.95, status="confident"))
    got = cache.get(_key())
    assert got is not None
    assert got.probability == pytest.approx(0.95)
    assert got.status == "confident"


def test_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "llm_cache.sqlite"
    first = AnswerCache(path)
    first.put(_key(), _entry())
    first.close()
    second = AnswerCache(path)
    try:
        assert second.get(_key()) is not None
    finally:
        second.close()


def test_status_for_recomputes_from_threshold() -> None:
    assert _entry(probability=0.85).status_for(0.8) == "confident"
    assert _entry(probability=0.8).status_for(0.8) == "confident"
    assert _entry(probability=0.79).status_for(0.8) == "below_threshold"
    assert _entry(status="below_threshold", probability=0.9).status_for(0.95) == "below_threshold"


def test_status_for_keeps_invalid_response() -> None:
    entry = _entry(status="invalid_response", probability=None)
    assert entry.status_for(0.8) == "invalid_response"


def test_entry_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _entry().status = "x"  # type: ignore[misc]
