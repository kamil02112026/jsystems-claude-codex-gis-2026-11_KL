"""The OSM speed value of a provided link — one function shared by the comparison and the profile."""

from __future__ import annotations

from mapqa.contract.bundle import SignLink
from mapqa.contract.models import AttributeValue
from mapqa.normalize.maxspeed import normalize_directional, normalize_maxspeed


def osm_speed_value(link: SignLink | None) -> AttributeValue:
    """maxspeed with PL:* type tags; directional tags when there is no plain maxspeed (ADR-002 §3.5)."""
    if link is None:
        return AttributeValue(status="missing", note="brak połączenia z drogą OSM")
    if link.maxspeed is None and (link.maxspeed_forward or link.maxspeed_backward):
        directional = normalize_directional(
            link.maxspeed_forward, link.maxspeed_backward, maxspeed_type=link.maxspeed_type, source_maxspeed=link.source_maxspeed
        )
        if directional is not None:
            return directional
    return normalize_maxspeed(
        link.maxspeed, maxspeed_type=link.maxspeed_type, source_maxspeed=link.source_maxspeed, conditional=link.maxspeed_conditional
    )
