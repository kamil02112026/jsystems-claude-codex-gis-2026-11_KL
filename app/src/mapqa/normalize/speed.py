"""Speed constants and equality (ADR-002 §3.5)."""

from __future__ import annotations

MPH_TO_KMH = 1.609344
SPEED_TOLERANCE_KMH = 0.5


def speeds_equal(a: float, b: float) -> bool:
    """Two km/h values are equal when |a - b| < 0.5."""
    return abs(a - b) < SPEED_TOLERANCE_KMH
