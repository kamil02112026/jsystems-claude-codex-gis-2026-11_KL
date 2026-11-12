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

QUESTIONS: dict[str, Question] = {SPEED_LIMIT_VALUE.question_id: SPEED_LIMIT_VALUE}


def get_question(question_id: str) -> Question:
    """Zwraca pytanie z katalogu; nieznane `question_id` → KeyError."""
    return QUESTIONS[question_id]
