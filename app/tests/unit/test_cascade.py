"""Cascade orchestration on fake ports (ADR-003 §3.4-3.8; CAS-01..05, THR-01, TAC-003-02/05/06)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from mapqa.budget.budget import Budget
from mapqa.budget.cost_log import CostLog
from mapqa.cache.sqlite_cache import AnswerCache
from mapqa.cascade import Cascade, PortResult
from mapqa.config.schema import AppConfig
from mapqa.contract.models import RunLimits
from mapqa.models.image_prep import ImageOutOfBounds, PreparedImage
from mapqa.questions.catalog import SPEED_LIMIT_VALUE as Q

IMG = PreparedImage(data=b"jpeg", mime="image/jpeg", source_sha256="a" * 64)


def ok(answer: str, p: float, cost: str | None = "0.01") -> PortResult:
    return PortResult(
        answer=answer,
        probability=p,
        parse_status="ok",
        cost_usd=Decimal(cost) if cost else None,
        input_tokens=10,
        output_tokens=2,
        latency_ms=5,
    )


def invalid() -> PortResult:
    return PortResult(answer=None, probability=None, parse_status="invalid_response", cost_usd=Decimal("0.01"))


def unavailable(code: str = "503") -> PortResult:
    return PortResult(answer=None, probability=None, parse_status="model_unavailable", cost_usd=None, error_class=code)


class FakePort:
    def __init__(self, l1: list | None = None, l2: list | None = None) -> None:
        self.script = {1: list(l1 or []), 2: list(l2 or [])}
        self.calls: list[dict] = []

    def ask(self, *, level, model, reasoning_effort, image, question):
        self.calls.append({"level": level, "model": model, "effort": reasoning_effort})
        item = self.script[level].pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def cache(tmp_path: Path):
    with AnswerCache(tmp_path / "c.sqlite") as c:
        yield c


def make(tmp_path: Path, cache, port, config: AppConfig | None = None, limits: RunLimits | None = None):
    budget = Budget(limits or RunLimits())
    log_path = tmp_path / "costs.jsonl"
    cascade = Cascade(port, cache, budget, CostLog(log_path), config or AppConfig(), "run1")
    return cascade, budget, log_path


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def resolve(cascade: Cascade, sha: str = "a" * 64, image=IMG):
    return cascade.resolve(image_sha256=sha, image=image, question=Q, attribute="speed_limit")


def test_cas01_level1_confident(tmp_path, cache):
    port = FakePort(l1=[ok("50", 0.93)])
    cascade, _, _ = make(tmp_path, cache, port)
    r = resolve(cascade)
    assert (r.final_status, r.resolved_by, r.final_answer) == ("resolved", "1", "50")
    assert [c["level"] for c in port.calls] == [1]
    assert port.calls[0]["effort"] is None


def test_cas01_exact_threshold_is_confident(tmp_path, cache):
    cascade, _, _ = make(tmp_path, cache, FakePort(l1=[ok("50", 0.8)]))
    assert resolve(cascade).resolved_by == "1"


def test_cas02_escalates_below_threshold(tmp_path, cache):
    port = FakePort(l1=[ok("40", 0.5)], l2=[ok("50", 0.9)])
    cascade, _, _ = make(tmp_path, cache, port)
    r = resolve(cascade)
    assert (r.final_status, r.resolved_by, r.final_answer) == ("resolved", "2", "50")
    assert r.escalation_reason == "below_threshold"
    assert [a.level for a in r.attempts] == [1, 2]
    assert port.calls[1]["effort"] == "medium"
    assert port.calls[1]["model"] == "openai/gpt-6-luna"


def test_cas02_escalates_invalid_response(tmp_path, cache):
    cascade, _, _ = make(tmp_path, cache, FakePort(l1=[invalid()], l2=[ok("50", 0.9)]))
    r = resolve(cascade)
    assert r.escalation_reason == "invalid_response"
    assert r.resolved_by == "2"


def test_cas03_abstain(tmp_path, cache):
    cascade, _, _ = make(tmp_path, cache, FakePort(l1=[ok("40", 0.5)], l2=[ok("40", 0.6)]))
    r = resolve(cascade)
    assert (r.final_status, r.resolved_by, r.final_answer) == ("abstain", "human", None)


def test_cas03_level2_invalid_is_abstain(tmp_path, cache):
    cascade, _, _ = make(tmp_path, cache, FakePort(l1=[ok("40", 0.5)], l2=[invalid()]))
    r = resolve(cascade)
    assert (r.final_status, r.resolved_by) == ("abstain", "human")


def test_cas04_api_error_stops_without_level2_and_opens_circuit(tmp_path, cache):
    port = FakePort(l1=[unavailable("503")])
    cascade, budget, _ = make(tmp_path, cache, port)
    r = resolve(cascade, "b" * 64)
    assert r.final_status == "model_unavailable"
    assert r.resolved_by == "human"
    assert r.attempts[0].error_class == "503"
    assert [c["level"] for c in port.calls] == [1]
    assert budget.circuit_open and budget.circuit_error_class == "503"
    for sha in ("c" * 64, "d" * 64):
        r2 = resolve(cascade, sha)
        assert r2.final_status == "model_unavailable"
        assert r2.attempts[0].error_class == "circuit_open"
    assert len(port.calls) == 1


def test_cas04_circuit_still_serves_cache_hits(tmp_path, cache):
    port = FakePort(l1=[ok("50", 0.95), unavailable("timeout")])
    cascade, _, _ = make(tmp_path, cache, port)
    resolve(cascade, "b" * 64)  # warm cache
    resolve(cascade, "c" * 64)  # opens the circuit
    r = resolve(cascade, "b" * 64)
    assert r.resolved_by == "1" and r.attempts[0].cache_hit
    assert len(port.calls) == 2


def test_cas04_level2_timeout_opens_circuit(tmp_path, cache):
    port = FakePort(l1=[ok("40", 0.5)], l2=[unavailable("timeout")])
    cascade, budget, _ = make(tmp_path, cache, port)
    r = resolve(cascade)
    assert (r.final_status, r.resolved_by) == ("model_unavailable", "human")
    assert budget.circuit_open


def test_cas05_no_sign_is_confident(tmp_path, cache):
    cascade, _, _ = make(tmp_path, cache, FakePort(l1=[ok("brak znaku", 0.95)]))
    r = resolve(cascade)
    assert (r.resolved_by, r.final_answer) == ("1", "brak znaku")


def test_cas05_unreadable_below_threshold_escalates(tmp_path, cache):
    port = FakePort(l1=[ok("nieczytelny", 0.79)], l2=[ok("50", 0.9)])
    cascade, _, _ = make(tmp_path, cache, port)
    assert resolve(cascade).resolved_by == "2"


def test_thr01_threshold_per_model_with_warning(tmp_path, cache):
    cfg = AppConfig(thresholds={"level1": {"typesafe/jev-1.14": {"speed_limit": 0.9}}})
    cfg.models.level1 = "openai/gpt-6-luna-decisions"
    cascade, _, _ = make(tmp_path, cache, FakePort(l1=[ok("50", 0.85)]), cfg)
    assert resolve(cascade).resolved_by == "1"  # default 0.8, not 0.9
    assert cascade.uncalibrated_warnings() == [
        "próg niekalibrowany dla modelu openai/gpt-6-luna-decisions (poziom 1, speed_limit)"
    ]


def test_calibrated_threshold_gives_no_warning(tmp_path, cache):
    cfg = AppConfig(
        thresholds={
            "level1": {"typesafe/jev-1.14": {"speed_limit": 0.9}},
            "level2": {"openai/gpt-6-luna": {"speed_limit": 0.7}},
        }
    )
    port = FakePort(l1=[ok("50", 0.85)], l2=[ok("50", 0.75)])
    cascade, _, _ = make(tmp_path, cache, port, cfg)
    assert resolve(cascade).resolved_by == "2"
    assert cascade.uncalibrated_warnings() == []


def test_threshold_change_on_warm_cache_makes_zero_calls(tmp_path, cache):
    first, _, _ = make(tmp_path / "first", cache, FakePort(l1=[ok("50", 0.85), ok("50", 0.95)]))
    assert resolve(first).resolved_by == "1"
    strict = AppConfig(thresholds={"level1": {"typesafe/jev-1.14": {"speed_limit": 0.9}}})
    port = FakePort()
    second, _, _ = make(tmp_path / "second", cache, port, strict, RunLimits(max_queries=0))
    r = resolve(second)
    assert port.calls == []
    assert r.attempts[0].cache_hit and r.attempts[0].status == "below_threshold"
    assert r.attempts[1].status == "budget_exceeded"


def test_cache_hit_logged_with_zero_cost_and_no_budget(tmp_path, cache):
    resolve(make(tmp_path / "a", cache, FakePort(l1=[ok("50", 0.95)]))[0])
    cascade, budget, log = make(tmp_path / "b", cache, FakePort())
    resolve(cascade)
    assert budget.queries_used == 0
    row = rows(log)[0]
    assert row["cache"] == "hit" and Decimal(row["cost_usd"]) == 0


def test_budget_refusal_level1_stops(tmp_path, cache):
    port = FakePort()
    cascade, _, log = make(tmp_path, cache, port, limits=RunLimits(max_queries=0))
    r = resolve(cascade)
    assert r.final_status == "budget_exceeded" and r.resolved_by == "human"
    assert r.attempts[0].status == "budget_exceeded" and r.attempts[0].error_class == "max_queries"
    assert port.calls == []
    assert rows(log)[0]["status"] == "budget_exceeded"


def test_budget_refusal_level2_is_budget_exceeded(tmp_path, cache):
    port = FakePort(l1=[ok("40", 0.5)])
    cascade, _, _ = make(tmp_path, cache, port, limits=RunLimits(max_queries=1))
    r = resolve(cascade)
    assert r.final_status == "budget_exceeded"
    assert r.attempts[1].error_class == "max_queries"
    assert len(port.calls) == 1


def test_port_transport_error_is_model_unavailable_and_opens_breaker(tmp_path, cache):
    """Review #4: a transport/timeout error raised by the port must not escalate to L2 (ADR-003 §3.4, §3.5)."""
    from mapqa.cascade.ports import PortTransportError

    port = FakePort(l1=[PortTransportError("timeout")], l2=[ok("50", 0.9)])
    cascade, budget, _ = make(tmp_path, cache, port)
    r = resolve(cascade)
    assert r.final_status == "model_unavailable"
    assert [c["level"] for c in port.calls] == [1]
    assert r.attempts[0].error_class == "timeout"
    assert budget.circuit_open


def test_port_exception_becomes_invalid_response_and_run_continues(tmp_path, cache):
    port = FakePort(l1=[ValueError("boom")], l2=[ok("50", 0.9)])
    cascade, _, _ = make(tmp_path, cache, port)
    r = resolve(cascade)
    assert r.attempts[0].status == "invalid_response"
    assert r.attempts[0].error_class == "ValueError"
    assert r.resolved_by == "2"
    # a local exception is not a deterministic model answer: it must not be cached (ADR-003 §3.7)
    port2 = FakePort(l1=[ok("50", 0.9)])
    cascade2, _, _ = make(tmp_path, cache, port2)
    r2 = resolve(cascade2)
    assert r2.attempts[0].cache_hit is False and r2.resolved_by == "1"


def test_tac_003_02_port_calls_equal_miss_rows(tmp_path, cache):
    port = FakePort(l1=[ok("50", 0.9), ok("40", 0.5), ok("30", 0.4)], l2=[ok("40", 0.9)])
    cascade, _, log = make(tmp_path, cache, port, limits=RunLimits(max_queries=4))
    for sha in ("1" * 64, "2" * 64, "3" * 64):
        resolve(cascade, sha)
    entries = rows(log)
    miss = [r for r in entries if r["cache"] == "miss" and r["status"] != "budget_exceeded"]
    assert len(miss) == len(port.calls) == 4
    assert any(r["status"] == "budget_exceeded" for r in entries)


def test_cost_estimated_when_cost_missing(tmp_path, cache):
    cascade, budget, log = make(tmp_path, cache, FakePort(l1=[ok("50", 0.9, cost=None)]))
    resolve(cascade)
    assert rows(log)[0]["cost_estimated"] is True
    assert budget.cost_used_usd == Decimal("0.02")


def test_image_out_of_bounds(tmp_path, cache):
    port = FakePort()
    cascade, budget, _ = make(tmp_path, cache, port)
    r = resolve(cascade, image=ImageOutOfBounds("too small"))
    assert (r.final_status, r.resolved_by) == ("image_out_of_bounds", "human")
    assert r.attempts == [] and port.calls == [] and budget.queries_used == 0


def test_no_model_port_raises_and_skipped_helper(tmp_path, cache):
    cascade, _, _ = make(tmp_path, cache, None)
    with pytest.raises(RuntimeError, match="tryb bez modelu"):
        resolve(cascade)
    r = cascade.skipped("a" * 64, Q)
    assert r.final_status == "skipped_no_model" and r.attempts == []


def test_model_unavailable_not_cached(tmp_path, cache):
    resolve(make(tmp_path / "a", cache, FakePort(l1=[unavailable()]))[0])
    cascade, _, _ = make(tmp_path / "b", cache, FakePort(l1=[ok("50", 0.9)]))
    assert not resolve(cascade).attempts[0].cache_hit
