"""Budget gate and limits (ADR-003 §3.5, §3.6; D-003-5; BUD-01..03, TAC-003-03, TAC-003-06)."""

from __future__ import annotations

from decimal import Decimal

from mapqa.budget.budget import Budget
from mapqa.contract.models import RunLimits


def _reserves(level1: str = "0.02", level2: str = "0.04", compare: str = "0.02") -> dict[str, Decimal]:
    return {"level1": Decimal(level1), "level2": Decimal(level2), "compare": Decimal(compare)}


def test_bud01_max_queries_stops_after_limit() -> None:
    budget = Budget(RunLimits(max_queries=5))
    sent = 0
    reasons = []
    for i in range(20):
        reason = budget.can_send("level1", f"img{i}")
        reasons.append(reason)
        if reason is None:
            budget.register("level1", f"img{i}")
            budget.commit(None, "level1")
            sent += 1
    assert sent == 5
    assert budget.queries_used == 5
    assert reasons[5:] == ["max_queries"] * 15


def test_bud02_max_usd_refuses_exactly_when_next_reserve_exceeds() -> None:
    budget = Budget(RunLimits(max_usd=Decimal("0.05"), reserve_usd=_reserves()))
    sent = 0
    for i in range(5):
        if budget.can_send("level1", f"img{i}") is None:
            budget.register("level1", f"img{i}")
            budget.commit(Decimal("0.02"), "level1")
            sent += 1
    # 0.02 + 0.02 <= 0.05 allowed; 0.04 + 0.02 = 0.06 > 0.05 refused
    assert sent == 2
    assert budget.cost_used_usd == Decimal("0.04")
    assert budget.can_send("level1", "imgX") == "max_usd"


def test_bud02_level2_reserve_is_used_for_level2_role() -> None:
    budget = Budget(RunLimits(max_usd=Decimal("0.05"), reserve_usd=_reserves()))
    assert budget.can_send("level2", "img0") is None
    budget.register("level2", "img0")
    budget.commit(None, "level2")
    assert budget.cost_used_usd == Decimal("0.04")
    # 0.04 + 0.02 (level1 reserve) = 0.06 > 0.05
    assert budget.can_send("level1", "img1") == "max_usd"


def test_bud03_max_images_counts_new_images_only() -> None:
    budget = Budget(RunLimits(max_images=3))
    results = []
    for i in range(5):
        reason = budget.can_send("level1", f"img{i}")
        results.append(reason)
        if reason is None:
            budget.register("level1", f"img{i}")
            budget.commit(None, "level1")
    assert results == [None, None, None, "max_images", "max_images"]
    assert budget.images_used == 3
    # a further query for an already-counted image is not a new image
    assert budget.can_send("level1", "img0") is None


def test_missing_cost_adds_reserve_and_flags_estimated() -> None:
    budget = Budget(RunLimits(reserve_usd=_reserves()))
    budget.register("level2", "img0")
    estimated = budget.commit(None, "level2")
    assert estimated is True
    assert budget.cost_used_usd == Decimal("0.04")


def test_reported_cost_is_added_and_not_estimated() -> None:
    budget = Budget(RunLimits(reserve_usd=_reserves()))
    budget.register("level1", "img0")
    estimated = budget.commit(Decimal("0.013"), "level1")
    assert estimated is False
    assert budget.cost_used_usd == Decimal("0.013")


def test_error_response_counts_as_query_with_full_reserve() -> None:
    budget = Budget(RunLimits(reserve_usd=_reserves()))
    budget.register("level1", "img0")
    budget.commit(None, "level1")
    assert budget.queries_used == 1
    assert budget.cost_used_usd == Decimal("0.02")


def test_circuit_open_refuses_everything_and_keeps_first_error() -> None:
    budget = Budget(RunLimits())
    assert budget.circuit_open is False
    budget.open_circuit("524")
    budget.open_circuit("timeout")
    assert budget.circuit_open is True
    assert budget.circuit_error_class == "524"
    assert budget.can_send("level1", "img0") == "circuit_open"
    assert budget.can_send("level2", "img1") == "circuit_open"
