"""Overture speed normalization (ADR-002 §3.5, T48)."""

from math import isfinite

from mapqa.contract.models import AttributeValue
from mapqa.normalize.speed import MPH_TO_KMH, speeds_equal


def normalize_overture_speed(
    rules: list[dict] | None, *, position: float | None, heading: str | None
) -> AttributeValue:
    """Select limits at the camera projection; preserve the complete raw rules.

    ``heading`` is relative to segment direction, inferred by the caller only
    when camera alignment permits it. Missing selection context is incomparable.
    """
    values: list[float] = []
    notes: list[str] = []
    unresolved: list[str] = []
    for rule in rules or []:
        maximum = rule.get("max_speed")
        if maximum is None:
            continue

        between = rule.get("between")
        if between is not None and between != [0, 1]:
            if position is not None and not between[0] <= position <= between[1]:
                continue

        # DuckDB structs include absent conditions as keys with null values.
        when = {key: value for key, value in (rule.get("when") or {}).items() if value is not None}
        direction = when.get("heading")
        if direction is not None and heading is not None and direction != heading:
            continue

        if between is not None and between != [0, 1] and position is None:
            unresolved.append("brak pozycji rzutu aparatu dla reguły between")
            continue
        if direction is not None and heading is None:
            unresolved.append("nieznany kierunek heading")
            continue
        if when.keys() - {"heading"}:
            unresolved.append("nierozstrzygnięte warunki when")
            continue

        value, unit = maximum.get("value"), maximum.get("unit")
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not isfinite(value) or value < 0 or unit not in {"km/h", "mph"}):
            unresolved.append("nieobsługiwana wartość lub jednostka max_speed")
            continue
        if unit == "mph":
            value = round(value * MPH_TO_KMH, 2)
            notes.append("przeliczono z mph")
        if direction is not None:
            notes.append("kierunek wywnioskowany z heading")
        values.append(float(value))

    if unresolved:
        return AttributeValue(
            raw=rules, normalized=None, status="not_comparable", speed_source="explicit",
            note="; ".join(dict.fromkeys(unresolved + notes)),
        )
    if not values:
        return AttributeValue(raw=rules, normalized=None, status="missing")
    if not speeds_equal(min(values), max(values)):
        return AttributeValue(
            raw=rules, normalized=None, status="not_comparable", speed_source="explicit",
            note="różne obowiązujące ograniczenia prędkości",
        )
    return AttributeValue(
        raw=rules, normalized=values[0], status="ok", speed_source="explicit",
        note="; ".join(dict.fromkeys(notes)),
    )
