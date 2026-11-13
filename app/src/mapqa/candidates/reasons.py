"""Polish referral reasons (ADR-004 §3.3)."""

from __future__ import annotations

from collections.abc import Sequence

from mapqa.contract.models import AttributeValue, ModelAttempt

IMPLICIT_NOTE = "Porównanie z wartością domyślną, nie ze znakiem."
LIT_CONDITIONAL_NOTE = "(`lit` warunkowe)"
LIT_ATTRIBUTE = "lit"
LIT_PHOTO_PHRASE = {"tak": "Lampa widoczna na zdjęciu", "nie": "Lampa niewidoczna na zdjęciu"}


def fmt_number(value: float) -> str:
    """Polish decimal comma; integers without decimals."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".replace(".", ",")


def fmt_probability(p: float | None) -> str:
    return "brak" if p is None else f"{p:.2f}".replace(".", ",")


def raw_text(osm: AttributeValue, *, sep: str = ", ", key: str = "maxspeed") -> str:
    """Raw OSM tags as `key=value` (a bare string is the `key` tag, `maxspeed` by default)."""
    raw = osm.raw
    if isinstance(raw, dict):
        return sep.join(f"{k}={v}" for k, v in raw.items())
    return f"{key}={raw}"


def is_implicit(osm: AttributeValue) -> bool:
    return osm.speed_source == "implicit"


def _osm_phrase(osm: AttributeValue, attribute: str = "speed_limit") -> str:
    if attribute == LIT_ATTRIBUTE:
        return _lit_osm_phrase(osm)
    if osm.status == "missing":
        return "OSM bez `maxspeed`"
    phrase = f"OSM `{raw_text(osm)}`"
    if is_implicit(osm) and osm.normalized is not None:
        phrase += f" (implicit, {fmt_number(float(osm.normalized))} km/h)"
    return phrase


def _lit_osm_phrase(osm: AttributeValue) -> str:
    if osm.status == "missing":
        return "OSM bez `lit`"
    phrase = f"OSM `{raw_text(osm, key='lit')}`"
    if osm.normalized == "yes_conditional":
        phrase += f" {LIT_CONDITIONAL_NOTE}"
    return phrase


def _photo_phrase(answer: str, attribute: str) -> str:
    if attribute == LIT_ATTRIBUTE:
        return LIT_PHOTO_PHRASE[answer]
    return f"Znak {answer} na zdjęciu"


def _flags_sentence(link_flags: Sequence[str]) -> str:
    return f" Flagi: {', '.join(f'`{f}`' for f in link_flags)}." if link_flags else ""


def candidate_reason(
    answer: str,
    attempt: ModelAttempt | None,
    osm: AttributeValue,
    link_flags: Sequence[str],
    attribute: str = "speed_limit",
) -> str:
    level = attempt.level if attempt else "?"
    p = fmt_probability(attempt.probability if attempt else None)
    text = f"{_photo_phrase(answer, attribute)} (poziom {level}, p={p}), {_osm_phrase(osm, attribute)}."
    if is_implicit(osm) and osm.status == "ok":
        text += f" {IMPLICIT_NOTE}"
    return text + _flags_sentence(link_flags)


def _level_part(level: int, attempts: Sequence[ModelAttempt]) -> str | None:
    last = next((a for a in reversed(attempts) if a.level == level), None)
    if last is None:
        return None
    return f"poziom {level} {last.answer or 'brak odpowiedzi'} p={fmt_probability(last.probability)} ({last.status})"


def unresolved_reason(attempts: Sequence[ModelAttempt], final_status: str, link_flags: Sequence[str]) -> str:
    parts = [p for p in (_level_part(1, attempts), _level_part(2, attempts)) if p]
    body = ", ".join(parts) if parts else final_status
    return f"Brak pewnego odczytu: {body}." + _flags_sentence(link_flags)
