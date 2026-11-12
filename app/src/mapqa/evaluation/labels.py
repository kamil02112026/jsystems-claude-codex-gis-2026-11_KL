"""Wczytanie etykiet znaków (ADR-004 §3.10: jedyny czytelnik pliku etykiet)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

NO_SIGN = "brak znaku"
UNREADABLE = "nieczytelny"
_VALUE_MAP = {"none": NO_SIGN, "unreadable": UNREADABLE}


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
