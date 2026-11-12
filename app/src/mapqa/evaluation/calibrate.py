"""Kalibracja progu pewności (ADR-004 §3.9): najniższy próg z trafnością >= cel i n >= min_n."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

GRID: tuple[float, ...] = tuple(i / 100 for i in range(50, 100))


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float
    n: int
    correct: int
    accuracy: float | None


class CalibrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float
    accuracy: float | None
    n: int
    bands: list[Band]
    warnings: list[str]


def calibrate(
    pairs: Sequence[tuple[float, bool]],
    target_accuracy: float = 0.90,
    min_n: int = 10,
    grid: Sequence[float] = GRID,
) -> CalibrationResult:
    """`pairs`: (prawdopodobieństwo, czy poprawna) dla odpowiedzi modelu; brak progu -> 1,00 + ostrzeżenie."""
    bands = []
    for t in grid:
        sel = [ok for p, ok in pairs if p >= t - 1e-9]
        n, correct = len(sel), sum(sel)
        bands.append(Band(threshold=t, n=n, correct=correct, accuracy=correct / n if n else None))
    for b in bands:
        if b.n >= min_n and b.accuracy is not None and b.accuracy >= target_accuracy:
            return CalibrationResult(threshold=b.threshold, accuracy=b.accuracy, n=b.n, bands=bands, warnings=[])
    warning = (
        f"Brak progu z trafnością >= {target_accuracy:.2f} przy co najmniej {min_n} odpowiedziach; "
        "ustawiono 1,00 (wszystko eskaluje)."
    )
    return CalibrationResult(threshold=1.0, accuracy=None, n=0, bands=bands, warnings=[warning])
