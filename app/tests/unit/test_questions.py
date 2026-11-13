"""T09: katalog pytań (ADR-003 §3.1, D-003-1; PRD F5.2)."""

from __future__ import annotations

import dataclasses
import re

import pytest

from mapqa.questions.catalog import (
    IMAGE_PREP_VERSION,
    QUESTIONS,
    SPEED_LIMIT_VALUE,
    get_question,
    prompt_version_for,
)

EXPECTED_OPTIONS = (
    "20", "30", "40", "50", "60", "70", "80", "90", "100", "110", "120", "140",
    "brak znaku", "nieczytelny",
)
EXPECTED_VALUES = tuple(str(v) for v in (20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140))


def test_speed_limit_question_matches_adr_table() -> None:
    q = SPEED_LIMIT_VALUE
    assert q.question_id == "speed_limit_value"
    assert q.attribute == "speed_limit"
    assert q.text == "Jaka wartość jest na znaku ograniczenia prędkości?"
    assert q.options == EXPECTED_OPTIONS
    assert len(q.options) == 14
    assert q.value_options == EXPECTED_VALUES


def test_label_map_maps_reference_labels_to_options() -> None:
    q = SPEED_LIMIT_VALUE
    assert q.label_map["none"] == "brak znaku"
    assert q.label_map["unreadable"] == "nieczytelny"
    for value in EXPECTED_VALUES:
        assert q.label_map[value] == value


def test_criteria_cover_every_option_with_text() -> None:
    q = SPEED_LIMIT_VALUE
    assert set(q.criteria) == set(q.options)
    assert all(text.strip() for text in q.criteria.values())
    assert q.criteria["nieczytelny"] == "Znak ograniczenia prędkości jest w kadrze, ale wartości nie da się odczytać"
    assert q.criteria["brak znaku"] == "Nie widać znaku ograniczenia prędkości B-33"
    assert q.criteria["50"] == "Okrągły znak B-33 z wartością 50 km/h"


def test_prompt_version_includes_image_prep_version() -> None:
    assert IMAGE_PREP_VERSION == "image_prep.v2"
    assert re.fullmatch(r"speed_limit_value\.v1-[0-9a-f]{8}\+image_prep\.v2", SPEED_LIMIT_VALUE.prompt_version)


def test_prompt_version_changes_when_text_changes() -> None:
    changed = dataclasses.replace(SPEED_LIMIT_VALUE, text="Jaki znak widać na drodze?")
    original_version = prompt_version_for(SPEED_LIMIT_VALUE.text, SPEED_LIMIT_VALUE.options, SPEED_LIMIT_VALUE.criteria)
    assert prompt_version_for(changed.text, changed.options, changed.criteria) != original_version


def test_prompt_version_changes_when_options_or_criteria_change() -> None:
    base = (SPEED_LIMIT_VALUE.text, SPEED_LIMIT_VALUE.options, SPEED_LIMIT_VALUE.criteria)
    v0 = prompt_version_for(*base)
    assert prompt_version_for(base[0], base[1][:-1], base[2]) != v0
    assert prompt_version_for(base[0], base[1], {**base[2], "50": "inny opis"}) != v0


def test_prompt_version_is_stable_for_same_content() -> None:
    args = (SPEED_LIMIT_VALUE.text, SPEED_LIMIT_VALUE.options, SPEED_LIMIT_VALUE.criteria)
    assert prompt_version_for(*args) == prompt_version_for(*args)


def test_registry_and_lookup() -> None:
    assert QUESTIONS["speed_limit_value"] is SPEED_LIMIT_VALUE
    assert get_question("speed_limit_value") is SPEED_LIMIT_VALUE
    with pytest.raises(KeyError):
        get_question("nieistniejace")


def test_question_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        SPEED_LIMIT_VALUE.text = "x"  # type: ignore[misc]


STREET_LAMP_OPTIONS = ("tak", "nie", "nie widać")


def test_street_lamp_question_matches_adr_and_prd() -> None:
    from mapqa.questions.catalog import STREET_LAMP_VISIBLE

    q = STREET_LAMP_VISIBLE
    assert q.question_id == "street_lamp_visible"
    assert q.attribute == "lit"
    assert q.text == "Czy w kadrze widać oprawę lampy ulicznej?"
    assert q.options == STREET_LAMP_OPTIONS
    assert q.value_options == ("tak", "nie")
    assert q.label_map == {"yes": "tak", "no": "nie"}


def test_street_lamp_criteria_cover_every_option_with_text() -> None:
    from mapqa.questions.catalog import STREET_LAMP_VISIBLE

    q = STREET_LAMP_VISIBLE
    assert set(q.criteria) == set(q.options)
    assert all(text.strip() for text in q.criteria.values())
    assert "słup" in q.criteria["nie"] or "słup" in q.criteria["tak"]


def test_street_lamp_prompt_version_has_own_base_and_image_prep() -> None:
    from mapqa.questions.catalog import STREET_LAMP_VISIBLE

    assert re.fullmatch(r"street_lamp_visible\.v1-[0-9a-f]{8}\+image_prep\.v2", STREET_LAMP_VISIBLE.prompt_version)


def test_street_lamp_is_registered() -> None:
    from mapqa.questions.catalog import STREET_LAMP_VISIBLE

    assert QUESTIONS["street_lamp_visible"] is STREET_LAMP_VISIBLE
    assert get_question("street_lamp_visible") is STREET_LAMP_VISIBLE


def test_speed_prompt_version_unchanged() -> None:
    # Zmiana tej wartości unieważnia cache speed_limit_value (ADR-003 §3.7).
    assert SPEED_LIMIT_VALUE.prompt_version == "speed_limit_value.v1-b6da2dc6+image_prep.v2"
