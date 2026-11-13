"""OSM `lit` normalization (ADR-002 §3.5 oświetlenie [P2])."""

from __future__ import annotations

from mapqa.contract.models import AttributeValue

_YES = frozenset({"yes"})
_YES_CONDITIONAL = frozenset({"automatic", "24/7", "sunset-sunrise", "limited", "interval"})
_NO = frozenset({"no", "disused"})


def normalize_lit(value: str | None) -> AttributeValue:
    """Map a raw OSM `lit` value to yes / yes_conditional / no / unknown_value / missing."""
    text = value.strip() if value is not None else ""
    if not text:
        return AttributeValue(raw=value, normalized=None, status="missing")
    key = text.lower()
    if key in _YES:
        return AttributeValue(raw=value, normalized="yes", status="ok")
    if key in _YES_CONDITIONAL:
        return AttributeValue(
            raw=value, normalized="yes_conditional", status="ok", note="lit warunkowe"
        )
    if key in _NO:
        return AttributeValue(raw=value, normalized="no", status="ok")
    return AttributeValue(
        raw=value,
        normalized="unknown_value",
        status="not_comparable",
        note="nieznana wartość lit",
    )
