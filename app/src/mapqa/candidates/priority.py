"""Candidate priority (ADR-004 §3.2, ADR-002 §3.3 'czyste połączenie')."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from mapqa.normalize.maxspeed import CONDITIONAL_FLAG

Priority = Literal["wysoki", "średni", "niski"]
CLEAN_LINK_FLAGS = frozenset({"boundary_crossing"})


def is_clean_link(link_flags: Sequence[str]) -> bool:
    """Clean link = no flags, or only `boundary_crossing`."""
    return set(link_flags) <= CLEAN_LINK_FLAGS


def priority(resolved_by: str | None, link_flags: Sequence[str], osm_flags: Sequence[str]) -> Priority:
    """Priority of a confident-reading candidate (`sources_only` is always `niski`, P3)."""
    if resolved_by == "1" and is_clean_link(link_flags) and CONDITIONAL_FLAG not in osm_flags:
        return "wysoki"
    return "średni"


def unresolved_priority(osm_status: str) -> Priority:
    """`nierozstrzygnięty_odczyt`: `średni` when OSM has the attribute value, else `niski`."""
    return "średni" if osm_status == "ok" else "niski"
