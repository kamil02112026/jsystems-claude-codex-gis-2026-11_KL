"""NRM-01/02/03 and speed equality (ADR-002 §3.5)."""

from __future__ import annotations

import pytest

from mapqa.normalize.maxspeed import normalize_directional, normalize_maxspeed
from mapqa.normalize.speed import MPH_TO_KMH, speeds_equal

# (maxspeed, type, source, normalized, status, speed_source, flags)
TABLE = [
    ("50", "PL:urban", None, 50, "ok", "implicit", []),
    ("30", "PL:zone30", None, 30, "ok", "implicit", []),
    ("70", "PL:urban", None, 70, "ok", "explicit", ["type_value_conflict"]),
    ("60", None, None, 60, "ok", "explicit", []),
    ("60", "sign", None, 60, "ok", "explicit", []),
    ("60", "PL:sign", None, 60, "ok", "explicit", []),
    ("30 mph", None, None, 48.28, "ok", "explicit", []),
    ("30mph", None, None, 48.28, "ok", "explicit", []),
    ("50 MPH", None, None, 80.47, "ok", "explicit", []),
    ("50 km/h", None, None, 50, "ok", "explicit", []),
    (" 50 ", None, None, 50, "ok", "explicit", []),
    (None, "PL:urban", None, 50, "ok", "implicit", []),
    (None, "PL:rural", None, 90, "ok", "implicit", []),
    (None, "PL:zone40", None, 40, "ok", "implicit", []),
    (None, "PL:zone:30", None, 30, "ok", "implicit", []),
    (None, "PL:motorway", None, 140, "ok", "implicit", []),
    (None, "PL:expressway", None, 120, "ok", "implicit", []),
    (None, "PL:living_street", None, 20, "ok", "implicit", []),
    (None, "sign", None, None, "not_comparable", None, []),
    (None, "PL:sign", None, None, "not_comparable", None, []),
    (None, "PL:trunk", None, None, "not_comparable", "implicit", []),
    ("50;70", None, None, None, "not_comparable", None, []),
    ("none", None, None, None, "not_comparable", None, []),
    ("signals", None, None, None, "not_comparable", None, []),
    ("variable", None, None, None, "not_comparable", None, []),
    ("walk", None, None, None, "not_comparable", None, []),
    ("zzz", None, None, None, "not_comparable", None, []),
    (None, None, None, None, "missing", None, []),
    ("", None, None, None, "missing", None, []),
    (None, None, "PL:urban", 50, "ok", "implicit", []),
    ("PL:urban", None, None, 50, "ok", "implicit", []),
]


@pytest.mark.parametrize(("ms", "typ", "src", "norm", "status", "source", "flags"), TABLE)
def test_table(ms, typ, src, norm, status, source, flags):
    r = normalize_maxspeed(ms, maxspeed_type=typ, source_maxspeed=src)
    assert r.normalized == norm
    assert r.status == status
    assert r.speed_source == source
    assert r.flags == flags
    if status == "not_comparable":
        assert r.note


def test_raw_unchanged_single_input():
    assert normalize_maxspeed(" 50 ").raw == " 50 "
    assert normalize_maxspeed("30mph").raw == "30mph"


def test_raw_dict_for_combined_inputs():
    r = normalize_maxspeed("70", maxspeed_type="PL:urban")
    assert r.raw == {"maxspeed": "70", "maxspeed:type": "PL:urban"}


def test_missing_never_zero():
    assert normalize_maxspeed(None).normalized is None


def test_conflict_note():
    r = normalize_maxspeed("70", maxspeed_type="PL:urban")
    assert r.note == "typ PL:urban (domyślnie 50 km/h) ≠ maxspeed 70"


def test_mph_note_and_formula():
    r = normalize_maxspeed("30 mph")
    assert r.note == "przeliczono z mph"
    assert r.normalized == round(30 * MPH_TO_KMH, 2)


def test_notes_for_defaults():
    assert "PL:urban" in normalize_maxspeed(None, maxspeed_type="PL:urban").note
    assert normalize_maxspeed("50", maxspeed_type="PL:urban").note == "wartość domyślna PL:urban"
    assert normalize_maxspeed(None, maxspeed_type="sign").note == (
        "unknown: oznaczenie znaku bez wartości"
    )
    assert normalize_maxspeed(None, maxspeed_type="PL:trunk").note == "nieznany kod PL:*"


def test_type_wins_over_source_and_note_mentions_both():
    r = normalize_maxspeed(None, maxspeed_type="PL:rural", source_maxspeed="PL:urban")
    assert r.normalized == 90
    assert "PL:rural" in r.note and "PL:urban" in r.note


def test_source_used_when_no_type_and_same_not_noted_twice():
    r = normalize_maxspeed(None, maxspeed_type="PL:urban", source_maxspeed="PL:urban")
    assert r.normalized == 50
    assert r.note.count("PL:urban") == 1 or "source:maxspeed" not in r.note


def test_case_and_whitespace_tolerant_type():
    r = normalize_maxspeed(None, maxspeed_type=" pl:URBAN ")
    assert r.normalized == 50


# NRM-03
def test_conditional():
    cond = "30 @ (Mo-Fr 07:00-17:00)"
    r = normalize_maxspeed("50", conditional=cond)
    assert r.normalized == 50
    assert r.status == "ok"
    assert "conditional_rule_present" in r.flags
    assert cond in r.note
    assert r.raw == {"maxspeed": "50", "maxspeed:conditional": cond}


# NRM-02
def test_directional_none():
    assert normalize_directional(None, None) is None


def test_directional_differ():
    r = normalize_directional("50", "70")
    assert r is not None
    assert r.status == "not_comparable"
    assert r.normalized is None
    assert r.note == "kierunek nieznany (MVP)"
    assert r.raw == {"maxspeed:forward": "50", "maxspeed:backward": "70"}


def test_directional_equal():
    r = normalize_directional("50", "50")
    assert r is not None and r.status == "ok" and r.normalized == 50


def test_directional_equal_after_normalization():
    r = normalize_directional("PL:urban", "50")
    assert r is not None and r.status == "ok" and r.normalized == 50


def test_directional_pl_urban_backward_only():
    r = normalize_directional(None, "PL:urban")
    assert r is not None
    assert r.normalized == 50 and r.speed_source == "implicit" and r.status == "ok"
    assert r.raw == {"maxspeed:backward": "PL:urban"}


def test_directional_one_unparseable_differs():
    r = normalize_directional("50", "zzz")
    assert r is not None and r.status == "not_comparable"


# NRM-02 with camera direction (ADR-002 §3.5, D-002-3): forward when directed diff <= 90, else backward
def test_directional_heading_picks_forward():
    r = normalize_directional("50", "70", directed_bearing_diff=10)
    assert r is not None
    assert r.normalized == 50 and r.status == "ok" and r.speed_source == "explicit"
    assert r.note.startswith("kierunek wywnioskowany z heading")
    assert "forward" in r.note
    assert r.raw == {"maxspeed:forward": "50", "maxspeed:backward": "70"}


def test_directional_heading_picks_backward():
    r = normalize_directional("50", "70", directed_bearing_diff=170)
    assert r is not None
    assert r.normalized == 70 and r.status == "ok"
    assert r.note.startswith("kierunek wywnioskowany z heading")
    assert "backward" in r.note


def test_directional_heading_none_stays_not_comparable():
    r = normalize_directional("50", "70", directed_bearing_diff=None)
    assert r is not None and r.status == "not_comparable"
    assert r.note == "kierunek nieznany (MVP)"


def test_directional_heading_gate_bearing_over_30_not_comparable():
    # bearing_diff = min(60, 120) = 60 > 30 -> direction not inferred (D-002-3)
    r = normalize_directional("50", "70", directed_bearing_diff=60)
    assert r is not None and r.status == "not_comparable" and r.normalized is None
    assert r.note.startswith("kierunek nieznany")


def test_directional_heading_gate_uses_bearing_diff_both_sides():
    # directed 155 -> bearing_diff 25 <= 30 -> backward; directed 25 -> forward
    assert normalize_directional("50", "70", directed_bearing_diff=155).normalized == 70
    assert normalize_directional("50", "70", directed_bearing_diff=25).normalized == 50


def test_directional_equal_ignores_heading():
    r = normalize_directional("50", "50", directed_bearing_diff=170)
    assert r is not None and r.status == "ok" and r.normalized == 50
    assert "heading" not in r.note


def test_osm_speed_value_passes_heading_through():
    from mapqa.contract.bundle import SignLink
    from mapqa.normalize.osm import osm_speed_value

    link = SignLink(
        photo_id="p1", osm_way_id=1, distance_m=1.0, heading_diff_deg=None, highway="primary",
        maxspeed=None, maxspeed_forward="50", maxspeed_backward="70", maxspeed_conditional=None,
        oneway=None, candidate_count=1, match_flags=(), osm_source="x", osm_timestamp=None,
    )
    assert osm_speed_value(link).status == "not_comparable"  # MVP behaviour without heading
    r = osm_speed_value(link, directed_bearing_diff=170)
    assert r.normalized == 70 and r.status == "ok"


# equality
@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(50, 50, True), (50, 50.49, True), (50, 50.5, False), (50.5, 50, False),
     (48.28, 48, True), (50, 50.4, True)],
)
def test_speeds_equal(a, b, expected):
    assert speeds_equal(a, b) is expected
