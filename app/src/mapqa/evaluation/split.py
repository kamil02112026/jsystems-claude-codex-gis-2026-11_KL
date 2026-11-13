"""Podział kalibracja / test po sequence (ADR-004 §3.7)."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Literal

from mapqa.contract.errors import ContractViolation

Split = Literal["calibration", "test"]
DEFAULT_SEED = "mapqa-2026-11"


def _assign(sequence: str, seed: str) -> Split:
    digest = hashlib.sha256(f"{seed}|{sequence}".encode()).hexdigest()
    return "calibration" if int(digest[:8], 16) % 100 < 50 else "test"


def split_by_sequence(photo_to_sequence: dict[str, str], seed: str = DEFAULT_SEED) -> dict[str, Split]:
    """Cała sekwencja trafia do jednej części; reguła: int(sha256(seed|sequence)[:8], 16) % 100 < 50."""
    out: dict[str, Split] = {}
    for photo_id, sequence in photo_to_sequence.items():
        if not sequence:
            raise ContractViolation(f"Puste pole sequence dla zdjęcia {photo_id}")
        out[photo_id] = _assign(sequence, seed)
    return out


def load_sequences(photos_csv: Path) -> dict[str, str]:
    """photo_id -> sequence z `photos.csv` (cały zbiór zdjęć, nie tylko etykietowane)."""
    with photos_csv.open(encoding="utf-8-sig", newline="") as fh:
        return {r["photo_id"].strip(): r["sequence"].strip() for r in csv.DictReader(fh)}
