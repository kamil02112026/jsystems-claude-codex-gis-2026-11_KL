"""Katalog pytań zamkniętych (ADR-003 §3.1, D-003-1; PRD F5.2).

Zmiana tekstu, opcji lub kryteriów zmienia `prompt_version` automatycznie,
co unieważnia wpisy cache tylko dla tego pytania (ADR-003 §3.7).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

IMAGE_PREP_VERSION = "image_prep.v2"
SPEED_LIMIT_BASE_VERSION = "speed_limit_value.v1"


@dataclass(frozen=True)
class Question:
    question_id: str
    attribute: str
    prompt_version: str
    text: str
    options: tuple[str, ...]
    value_options: tuple[str, ...]
    criteria: dict[str, str]
    label_map: dict[str, str]


def prompt_version_for(
    text: str,
    options: Sequence[str],
    criteria: Mapping[str, str],
    base: str = SPEED_LIMIT_BASE_VERSION,
) -> str:
    """Wersja promptu: `base-<hash8>+image_prep.vN`, hash z kanonicznego JSON treści."""
    canonical = json.dumps(
        {"text": text, "options": list(options), "criteria": dict(criteria)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}+{IMAGE_PREP_VERSION}"


_SPEED_TEXT = "Jaka wartość jest na znaku ograniczenia prędkości?"
_SPEED_VALUES = ("20", "30", "40", "50", "60", "70", "80", "90", "100", "110", "120", "140")
_SPEED_CRITERIA: dict[str, str] = {
    **{v: f"Okrągły znak B-33 z wartością {v} km/h" for v in _SPEED_VALUES},
    "brak znaku": "Nie widać znaku ograniczenia prędkości B-33",
    "nieczytelny": "Znak ograniczenia prędkości jest w kadrze, ale wartości nie da się odczytać",
}
_SPEED_OPTIONS = (*_SPEED_VALUES, "brak znaku", "nieczytelny")

SPEED_LIMIT_VALUE = Question(
    question_id="speed_limit_value",
    attribute="speed_limit",
    prompt_version=prompt_version_for(_SPEED_TEXT, _SPEED_OPTIONS, _SPEED_CRITERIA),
    text=_SPEED_TEXT,
    options=_SPEED_OPTIONS,
    value_options=_SPEED_VALUES,
    criteria=_SPEED_CRITERIA,
    label_map={
        "none": "brak znaku",
        "unreadable": "nieczytelny",
        **{v: v for v in _SPEED_VALUES},
    },
)

STREET_LAMP_BASE_VERSION = "street_lamp_visible.v1"
_LAMP_TEXT = "Czy w kadrze widać oprawę lampy ulicznej?"
_LAMP_VALUES = ("tak", "nie")
_LAMP_CRITERIA: dict[str, str] = {
    "tak": "W kadrze widać oprawę lampy ulicznej, czyli rozpoznawalną lampę oświetleniową na słupie lub wysięgniku",
    "nie": "Widok pozwala ocenić, że w kadrze nie ma oprawy lampy ulicznej; sam słup energetyczny lub telefoniczny bez oprawy nie wystarcza",
    "nie widać": "Ujęcie nie pozwala rozstrzygnąć, czy w kadrze jest oprawa lampy ulicznej (np. ciemno, zasłonięte, zbyt daleko)",
}
_LAMP_OPTIONS = (*_LAMP_VALUES, "nie widać")

STREET_LAMP_VISIBLE = Question(
    question_id="street_lamp_visible",
    attribute="lit",
    prompt_version=prompt_version_for(
        _LAMP_TEXT, _LAMP_OPTIONS, _LAMP_CRITERIA, base=STREET_LAMP_BASE_VERSION
    ),
    text=_LAMP_TEXT,
    options=_LAMP_OPTIONS,
    value_options=_LAMP_VALUES,
    criteria=_LAMP_CRITERIA,
    label_map={"yes": "tak", "no": "nie"},
)

QUESTIONS: dict[str, Question] = {
    SPEED_LIMIT_VALUE.question_id: SPEED_LIMIT_VALUE,
    STREET_LAMP_VISIBLE.question_id: STREET_LAMP_VISIBLE,
}


def get_question(question_id: str) -> Question:
    """Zwraca pytanie z katalogu; nieznane `question_id` → KeyError."""
    return QUESTIONS[question_id]
