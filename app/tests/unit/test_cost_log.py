"""Cost log JSONL (ADR-003 §3.8, ADR-000 §5; LOG-01)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from mapqa.budget.cost_log import CostLog
from mapqa.contract.models import CostLogEntry

FAKE_KEY = "sk-or-TEST_SECRET_0123456789"
FAKE_BASE64 = "iVBORw0KGgo" + "A" * 5000


def _entry(i: int, cache: str = "miss", cost: Decimal | None = Decimal("0.02")) -> CostLogEntry:
    return CostLogEntry(
        ts=f"2026-11-12T10:00:0{i}Z",
        run_id="run-test",
        level=1,
        model="typesafe/jev-1.14",
        reasoning_effort=None,
        question_id="speed_limit_value",
        image_sha256="a" * 64,
        input_tokens=100,
        output_tokens=5,
        cost_usd=cost,
        cost_estimated=cost is None,
        cache=cache,  # type: ignore[arg-type]
        status="confident",
    )


def test_log01_one_line_per_attempt_with_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "map-qa" / "run-test" / "costs.jsonl"
    log = CostLog(path)
    log.append(_entry(1))
    log.append(_entry(2, cache="hit", cost=Decimal("0")))
    log.append(_entry(3, cost=None))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    expected_fields = set(CostLogEntry.model_fields)
    for line in lines:
        assert set(json.loads(line)) == expected_fields
    assert json.loads(lines[1])["cache"] == "hit"
    assert json.loads(lines[2])["cost_estimated"] is True


def test_decimal_cost_is_serialized_as_string(tmp_path: Path) -> None:
    path = tmp_path / "costs.jsonl"
    CostLog(path).append(_entry(1, cost=Decimal("0.02")))
    assert json.loads(path.read_text(encoding="utf-8"))["cost_usd"] == "0.02"


def test_log01_no_secret_or_image_bytes_reach_the_file(tmp_path: Path) -> None:
    path = tmp_path / "costs.jsonl"
    CostLog(path).append(_entry(1))
    text = path.read_text(encoding="utf-8")
    assert FAKE_KEY not in text
    assert FAKE_BASE64[:200] not in text


def test_log01_model_rejects_fields_outside_the_contract() -> None:
    data = _entry(1).model_dump()
    data["api_key"] = FAKE_KEY
    with pytest.raises(ValidationError):
        CostLogEntry.model_validate(data)
