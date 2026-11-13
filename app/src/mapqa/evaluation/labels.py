"""Wczytanie etykiet znaków (ADR-004 §3.10: jedyny czytelnik pliku etykiet)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from mapqa.contract.errors import ContractViolation

NO_SIGN = "brak znaku"
UNREADABLE = "nieczytelny"
_VALUE_MAP = {"none": NO_SIGN, "unreadable": UNREADABLE}
# pytanie katalogu -> (pytanie w reference_labels.csv, mapowanie wartości etykiety na odpowiedź katalogu)
_REFERENCE_QUESTIONS: dict[str, tuple[str, dict[str, str]]] = {
    "speed_limit_value": ("speed_limit_value", _VALUE_MAP),
    "street_lamp_visible": ("street_lighting_visible", {"yes": "tak", "no": "nie"}),
}


@dataclass(frozen=True)
class Label:
    value: str
    status: str  # "certain" | "uncertain"
    negative_type: str = ""


def load_sign_labels(labels_path: Path) -> dict[str, Label]:
    """photo_id -> Label; wartość znormalizowana do opcji katalogu (none -> brak znaku)."""
    out: dict[str, Label] = {}
    with labels_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            raw = row["sign_value"].strip()
            out[row["photo_id"]] = Label(_VALUE_MAP.get(raw, raw), row["status"].strip(), row.get("negative_type", "").strip())
    return out


def load_reference_labels(labels_path: Path, question_id: str) -> dict[str, Label]:
    """photo_id -> Label dla pytania katalogu z reference_labels.csv (pełne kadry).

    `unknown` zawsze oznacza brak pewności (status `uncertain`, wykluczone z mianowników).
    """
    if question_id not in _REFERENCE_QUESTIONS:
        raise ContractViolation(f"Brak mapowania etykiet dla pytania {question_id}")
    label_question, value_map = _REFERENCE_QUESTIONS[question_id]
    out: dict[str, Label] = {}
    with labels_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["question"].strip() != label_question:
                continue
            raw = row["label"].strip()
            status = "uncertain" if raw == "unknown" else row["status"].strip()
            out[row["photo_id"].strip()] = Label(value_map.get(raw, raw), status)
    return out
