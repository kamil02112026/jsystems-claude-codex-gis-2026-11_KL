"""Overture speed limits: ADR-002 NRM-04/06 and TAC-002-03."""

from copy import deepcopy
from pathlib import Path

import duckdb
import pytest

from mapqa.contract.models import AttributeValue
from mapqa.normalize.overture import normalize_overture_speed
from mapqa.normalize.speed import speeds_equal


def rule(value=50, *, unit="km/h", between=None, when=None):
    return {"max_speed": {"value": value, "unit": unit}, "between": between, "when": when}


@pytest.mark.parametrize("rules", [None, [], [{"min_speed": {"value": 30, "unit": "km/h"}}]])
def test_missing(rules):
    result = normalize_overture_speed(rules, position=None, heading=None)
    assert isinstance(result, AttributeValue)
    assert result.status == "missing"
    assert result.normalized is None
    assert result.raw == rules


@pytest.mark.parametrize("between", [None, [0, 1]])
def test_base_rule_needs_no_position(between):
    result = normalize_overture_speed([rule(between=between)], position=None, heading=None)
    assert result.status == "ok"
    assert result.normalized == 50
    assert result.speed_source == "explicit"


@pytest.mark.parametrize(
    "position,status",
    [(0, "missing"), (0.199999, "missing"), (0.2, "ok"), (0.5, "ok"),
     (0.8, "ok"), (0.800001, "missing"), (1, "missing"), (None, "not_comparable")],
)
def test_nrm04_between_closed_interval(position, status):
    result = normalize_overture_speed([rule(between=[0.2, 0.8])], position=position, heading=None)
    assert result.status == status
    assert result.normalized == (50 if status == "ok" else None)


def test_nrm04_shared_boundary_keeps_both_rules():
    rules = [rule(30, between=[0, 0.5]), rule(50, between=[0.5, 1])]
    assert normalize_overture_speed(rules, position=0.5, heading=None).status == "not_comparable"
    assert normalize_overture_speed(rules, position=0.49, heading=None).normalized == 30
    assert normalize_overture_speed(rules, position=0.51, heading=None).normalized == 50


@pytest.mark.parametrize(
    "required,heading,status",
    [("forward", "forward", "ok"), ("backward", "backward", "ok"),
     ("forward", "backward", "missing"), ("backward", "forward", "missing"),
     ("forward", None, "not_comparable"), ("backward", None, "not_comparable")],
)
def test_nrm04_heading(required, heading, status):
    result = normalize_overture_speed([rule(when={"heading": required})], position=0.5, heading=heading)
    assert result.status == status
    assert result.normalized == (50 if status == "ok" else None)
    if status == "ok":
        assert "heading" in result.note


def test_position_and_heading_filter_together():
    rules = [rule(30, between=[0, 0.4], when={"heading": "forward"}),
             rule(70, between=[0.4, 1], when={"heading": "backward"})]
    assert normalize_overture_speed(rules, position=0.2, heading="forward").normalized == 30
    assert normalize_overture_speed(rules, position=0.7, heading="forward").status == "missing"
    assert normalize_overture_speed(rules, position=0.2, heading=None).status == "not_comparable"


@pytest.mark.parametrize("condition", ["during", "mode", "vehicle", "using"])
@pytest.mark.parametrize("base", [False, True])
def test_other_when_not_comparable(condition, base):
    rules = ([rule()] if base else []) + [rule(30, when={condition: ["warunek"]})]
    before = deepcopy(rules)
    result = normalize_overture_speed(rules, position=0.5, heading="forward")
    assert result.status == "not_comparable"
    assert result.normalized is None
    assert result.note
    assert result.raw == rules == before


def test_irrelevant_conditional_rules_do_not_block():
    rules = [rule(), rule(30, between=[0.6, 1], when={"during": "night"}),
             rule(20, when={"heading": "backward", "vehicle": "truck"})]
    assert normalize_overture_speed(rules, position=0.2, heading="forward").normalized == 50


def test_null_when_fields_are_absent_conditions():
    result = normalize_overture_speed(
        [rule(when={"heading": "forward", "during": None, "vehicle": None})],
        position=0.5, heading="forward",
    )
    assert result.status == "ok"


@pytest.mark.parametrize("values,status", [([50, 50], "ok"), ([50, 50.4], "ok"),
                                          ([50, 50.5], "not_comparable"),
                                          ([50, 50.4, 49.6], "not_comparable")])
def test_nrm04_multiple_values(values, status):
    result = normalize_overture_speed([rule(value) for value in values], position=0.5, heading=None)
    assert result.status == status
    assert result.normalized == (50 if status == "ok" else None)


@pytest.mark.parametrize("osm,rules,equal", [(48.28, [rule(48)], True),
                                           (50, [rule(50.4)], True),
                                           (50, [rule(50.5)], False)])
def test_nrm06_equality(osm, rules, equal):
    result = normalize_overture_speed(rules, position=0.5, heading=None)
    assert result.status == "ok"
    assert speeds_equal(osm, result.normalized) is equal


def test_mph_conversion():
    result = normalize_overture_speed([rule(30, unit="mph")], position=None, heading=None)
    assert result.status == "ok"
    assert result.normalized == 48.28
    assert result.speed_source == "explicit"
    assert "mph" in result.note


@pytest.mark.parametrize("maximum", [{"value": 50, "unit": "knots"},
                                     {"value": None, "unit": "km/h"}])
def test_unsupported_maximum_keeps_raw(maximum):
    rules = [{"max_speed": maximum}]
    result = normalize_overture_speed(rules, position=0.5, heading=None)
    assert result.status == "not_comparable"
    assert result.normalized is None
    assert result.raw == rules


def test_tac00203_all_snapshot_rule_lists_preserve_raw():
    path = Path(__file__).resolve().parents[3] / "course-materials/exercise-data/map-qa/overture_segments.parquet"
    with duckdb.connect() as connection:
        rows = connection.execute(
            "SELECT speed_limits FROM read_parquet(?) WHERE len(speed_limits) > 0", [str(path)]
        ).fetchall()
    assert len(rows) == 12_847
    assert sum(len(rules) for (rules,) in rows) == 14_205
    for (rules,) in rows:
        before = deepcopy(rules)
        for position, heading in [(None, None), (0, "forward"), (0.5, "backward"), (1, "forward")]:
            result = normalize_overture_speed(rules, position=position, heading=heading)
            assert isinstance(result, AttributeValue)
            assert result.raw == before
            assert rules == before
