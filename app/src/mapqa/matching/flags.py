"""Road-tag flag predicates shared by own and provided links (ADR-002 §3.3) — one copy only."""

from __future__ import annotations

from collections.abc import Mapping

RESTRICTED_VALUES = frozenset({"private", "no", "destination"})


def grade_separated_tags(tags: Mapping[str, object]) -> bool:
    """grade_separated (tag part): bridge/tunnel other than `no`, or a numeric layer != 0."""
    if any(str(tags.get(k) or "") not in ("", "no") for k in ("bridge", "tunnel")):
        return True
    layer = str(tags.get("layer") or "").strip()
    try:
        return bool(layer) and float(layer) != 0
    except ValueError:  # e.g. "-1;0" — not a number, no flag rather than a crash
        return False


def service_or_restricted_tags(tags: Mapping[str, object]) -> bool:
    """service_or_restricted: highway=service, or access/motor_vehicle private/no/destination."""
    if tags.get("highway") == "service":
        return True
    return any(tags.get(k) in RESTRICTED_VALUES for k in ("access", "motor_vehicle"))
