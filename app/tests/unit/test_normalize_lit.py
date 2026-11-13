"""NRM-05 (`lit`) — ADR-002 §3.5 oświetlenie [P2]."""

from __future__ import annotations

import pytest

from mapqa.normalize.lit import normalize_lit

# (raw, normalized, status)
TABLE = [
    ("yes", "yes", "ok"),
    ("automatic", "yes_conditional", "ok"),
    ("24/7", "yes_conditional", "ok"),
    ("sunset-sunrise", "yes_conditional", "ok"),
    ("limited", "yes_conditional", "ok"),
    ("interval", "yes_conditional", "ok"),
    ("no", "no", "ok"),
    ("disused", "no", "ok"),
    ("xyz", "unknown_value", "not_comparable"),
]


@pytest.mark.parametrize(("raw", "normalized", "status"), TABLE)
def test_lit_table_rows(raw: str, normalized: str, status: str) -> None:
    result = normalize_lit(raw)
    assert result.normalized == normalized
    assert result.status == status
    assert result.raw == raw


@pytest.mark.parametrize(("raw", "normalized"), [("Yes", "yes"), (" YES ", "yes"), ("Automatic", "yes_conditional"), ("  no\t", "no")])
def test_lit_ignores_case_and_outer_whitespace(raw: str, normalized: str) -> None:
    result = normalize_lit(raw)
    assert result.normalized == normalized
    assert result.raw == raw


def test_lit_missing_tag_is_missing_never_no() -> None:
    result = normalize_lit(None)
    assert result.status == "missing"
    assert result.normalized is None
    assert result.raw is None


@pytest.mark.parametrize("raw", ["", "   "])
def test_lit_blank_value_is_missing(raw: str) -> None:
    result = normalize_lit(raw)
    assert result.status == "missing"
    assert result.normalized is None


def test_lit_unknown_value_keeps_raw_and_explains() -> None:
    result = normalize_lit("xyz")
    assert result.raw == "xyz"
    assert result.note == "nieznana wartość lit"


def test_lit_conditional_value_carries_note() -> None:
    result = normalize_lit("automatic")
    assert result.status == "ok"
    assert "lit warunkowe" in result.note


def test_lit_result_has_no_speed_source_or_flags() -> None:
    result = normalize_lit("yes")
    assert result.speed_source is None
    assert result.flags == []
