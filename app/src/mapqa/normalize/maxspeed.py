"""OSM maxspeed normalization (ADR-002 §3.5, D-002-4)."""

from __future__ import annotations

import re
from typing import Any

from mapqa.contract.models import AttributeValue
from mapqa.normalize.speed import MPH_TO_KMH, speeds_equal

CONDITIONAL_FLAG = "conditional_rule_present"
CONFLICT_FLAG = "type_value_conflict"

_NUM = r"(\d+(?:[.,]\d+)?)"
_RE_PLAIN = re.compile(rf"^{_NUM}$")
_RE_KMH = re.compile(rf"^{_NUM}\s*km/h$")
_RE_MPH = re.compile(rf"^{_NUM}\s*mph$")
_RE_ZONE = re.compile(r"^pl:zone:?(\d+)$")

_DEFAULTS: dict[str, tuple[int, str]] = {
    "pl:urban": (50, "wartość domyślna PL:urban (obszar zabudowany)"),
    "pl:rural": (90, "wartość domyślna PL:rural (poza obszarem zabudowanym)"),
    "pl:motorway": (140, "wartość domyślna PL:motorway"),
    "pl:expressway": (120, "wartość domyślna PL:expressway (dwujezdniowa)"),
    "pl:living_street": (20, "wartość domyślna PL:living_street (strefa zamieszkania)"),
}

_Core = tuple[float | None, str, str | None, str, list[str]]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _is_sign(t: str) -> bool:
    return t == "sign" or t.startswith("pl:sign")


def _type_default(t: str, label: str) -> tuple[int, str] | None:
    """Default km/h and 'no number' note for a known PL type, else None."""
    if t in _DEFAULTS:
        return _DEFAULTS[t]
    m = _RE_ZONE.match(t)
    if m:
        return int(m.group(1)), f"strefa {label}"
    return None


def _parse_number(text: str) -> tuple[float, bool] | None:
    """Return (km/h, was_mph) for a numeric value, else None."""
    t = text.strip().lower()
    for rx, mph in ((_RE_PLAIN, False), (_RE_KMH, False), (_RE_MPH, True)):
        m = rx.match(t)
        if m:
            n = float(m.group(1).replace(",", "."))
            return (round(n * MPH_TO_KMH, 2) if mph else n), mph
    return None


def _raw(tags: dict[str, str | None]) -> Any:
    given = {k: v for k, v in tags.items() if v is not None}
    if len(given) == 1 and "maxspeed" in given:
        return given["maxspeed"]
    return given or None


def _join(*notes: str) -> str:
    return "; ".join(n for n in notes if n)


def _pick_type(maxspeed_type: str | None, source: str | None) -> tuple[str | None, str]:
    t, s = _clean(maxspeed_type), _clean(source)
    if t and s and t.lower() != s.lower():
        return t, f"maxspeed:type={t}, source:maxspeed={s}"
    return t or s, ""


def _text_reason(text: str | None) -> str | None:
    """Reason for non-numeric, non-type values (none, signals, 50;70, ...)."""
    text = _clean(text)
    if text is None or _parse_number(text) is not None:
        return None
    tl = text.lower()
    if tl.startswith("pl:") or _is_sign(tl):
        return None
    if ";" in text:
        return f"wiele wartości: {text}"
    if tl in {"none", "signals", "variable", "walk"}:
        return f"wartość niemierzalna: {text}"
    return f"niepoprawna wartość maxspeed: {text}"


def _normalize_core(text: str | None, typ: str | None, type_note: str) -> _Core:
    flags: list[str] = []
    text = _clean(text)
    number = _parse_number(text) if text is not None else None
    if text is not None and number is None and typ is None:
        typ = text  # PL:* / sign given directly as the value (directional tags)

    if number is not None:
        kmh, mph = number
        note = "przeliczono z mph" if mph else ""
        source = "explicit"
        tl = typ.lower() if typ else None
        default = _type_default(tl, typ) if typ and tl and not _is_sign(tl) else None
        if default is not None:
            d = default[0]
            if speeds_equal(kmh, d):
                source, note = "implicit", _join(note, f"wartość domyślna {typ}")
            else:
                flags.append(CONFLICT_FLAG)
                note = _join(note, f"typ {typ} (domyślnie {d} km/h) ≠ maxspeed {kmh:g}")
        return kmh, "ok", source, _join(note, type_note), flags

    if typ is None:
        return None, "missing", None, "", flags
    tl = typ.lower()
    if _is_sign(tl):
        note = "unknown: oznaczenie znaku bez wartości"
        return None, "not_comparable", None, _join(note, type_note), flags
    default = _type_default(tl, typ)
    if default is not None:
        return float(default[0]), "ok", "implicit", _join(default[1], type_note), flags
    return None, "not_comparable", "implicit", _join("nieznany kod PL:*", type_note), flags


def normalize_maxspeed(
    maxspeed: str | None,
    *,
    maxspeed_type: str | None = None,
    source_maxspeed: str | None = None,
    conditional: str | None = None,
) -> AttributeValue:
    raw = _raw(
        {
            "maxspeed": maxspeed,
            "maxspeed:type": maxspeed_type,
            "source:maxspeed": source_maxspeed,
            "maxspeed:conditional": conditional,
        }
    )
    typ, type_note = _pick_type(maxspeed_type, source_maxspeed)
    reason = _text_reason(maxspeed)
    if reason is not None:
        core: _Core = (None, "not_comparable", None, _join(reason, type_note), [])
    else:
        core = _normalize_core(maxspeed, typ, type_note)
    norm, status, source, note, flags = core
    cond = _clean(conditional)
    if cond:
        flags = [*flags, CONDITIONAL_FLAG]
        note = _join(note, f"warunkowe: {cond}")
    return AttributeValue(
        raw=raw,
        normalized=norm,
        speed_source=source,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        note=note,
        flags=flags,
    )


HEADING_GATE_DEG = 30.0  # ADR-002 §3.5 / D-002-3: direction inferred only when bearing_diff <= 30


def _by_heading(
    f: AttributeValue, b: AttributeValue, directed_bearing_diff: float, raw: dict[str, str]
) -> AttributeValue:
    """ADR-002 §3.5: forward when the camera points at most 90 deg from the way direction, else backward."""
    bearing_diff = min(directed_bearing_diff, 180 - directed_bearing_diff)
    if bearing_diff > HEADING_GATE_DEG:
        return AttributeValue(
            raw=raw,
            normalized=None,
            status="not_comparable",
            note=f"kierunek nieznany: kurs kamery odbiega od drogi o {bearing_diff:.0f}° (> {HEADING_GATE_DEG:.0f}°)",
        )
    chosen, side = (f, "forward") if directed_bearing_diff <= 90 else (b, "backward")
    return chosen.model_copy(
        update={"raw": raw, "note": _join(chosen.note, f"kierunek wywnioskowany z heading: {side}")}
    )


def normalize_directional(
    forward: str | None,
    backward: str | None,
    *,
    maxspeed_type: str | None = None,
    source_maxspeed: str | None = None,
    directed_bearing_diff: float | None = None,
) -> AttributeValue | None:
    """Directional maxspeed (ADR-002 §3.5). Differing directions need the camera-vs-way angle
    (0–180 deg); without it they stay not comparable (MVP)."""
    has_f, has_b = _clean(forward) is not None, _clean(backward) is not None
    if not has_f and not has_b:
        return None
    raw = {
        k: v
        for k, v in (("maxspeed:forward", forward), ("maxspeed:backward", backward))
        if v is not None
    }
    f = normalize_maxspeed(forward, maxspeed_type=maxspeed_type, source_maxspeed=source_maxspeed)
    b = normalize_maxspeed(backward, maxspeed_type=maxspeed_type, source_maxspeed=source_maxspeed)
    if not (has_f and has_b):
        return (f if has_f else b).model_copy(update={"raw": raw})
    equal = (
        f.status == b.status == "ok"
        and f.normalized is not None
        and b.normalized is not None
        and speeds_equal(float(f.normalized), float(b.normalized))
    )
    if equal:
        source = "implicit" if f.speed_source == b.speed_source == "implicit" else "explicit"
        return f.model_copy(update={"raw": raw, "speed_source": source})
    if directed_bearing_diff is not None:
        return _by_heading(f, b, directed_bearing_diff, raw)
    return AttributeValue(
        raw=raw, normalized=None, status="not_comparable", note="kierunek nieznany (MVP)"
    )
