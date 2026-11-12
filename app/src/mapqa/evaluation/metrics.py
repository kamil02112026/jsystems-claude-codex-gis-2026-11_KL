"""Metryki ewaluacji (ADR-004 §3.8): jawne liczniki i mianowniki."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from pydantic import BaseModel, ConfigDict

from mapqa.contract.models import CascadeResult, ModelAttempt
from mapqa.evaluation.labels import NO_SIGN, Label

HANDOFF_STATUSES = frozenset({"abstain", "model_unavailable", "budget_exceeded", "image_out_of_bounds"})
# Progi akceptacji (PRD §7): (kierunek, próg)
ACCEPTANCE: dict[str, tuple[str, float]] = {
    "cascade_accuracy": (">=", 0.90),
    "handoff_rate": ("<=", 0.30),
    "level2_escalated_accuracy": (">=", 0.90),
}


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metric(_M):
    numerator: int
    denominator: int
    value: float | None


class Counts(_M):
    certain: int = 0
    uncertain_excluded: int = 0
    abstain: int = 0
    model_unavailable: int = 0
    budget_exceeded: int = 0
    image_out_of_bounds: int = 0


class MetricSet(_M):
    cascade_accuracy: Metric
    handoff_rate: Metric
    escalation_rate: Metric
    level1_accuracy: Metric
    level2_escalated_accuracy: Metric
    coverage: Metric
    level1_standalone_accuracy: Metric
    level1_standalone_coverage: Metric
    level1_standalone_abstain_rate: Metric


class EvaluationReport(_M):
    question_id: str = "speed_limit_value"
    split: str | None = None
    counts: Counts
    overall: MetricSet
    subgroups: dict[str, MetricSet]
    baseline_mapillary: Metric | None = None
    acceptance: dict[str, bool | None]


def make_metric(numerator: int, denominator: int) -> Metric:
    return Metric(numerator=numerator, denominator=denominator, value=numerator / denominator if denominator else None)


def _level(result: CascadeResult, level: int) -> ModelAttempt | None:
    return next((a for a in result.attempts if a.level == level), None)


def _confident(a: ModelAttempt | None) -> bool:
    return a is not None and a.status == "confident"


Pair = tuple[Label, CascadeResult]


def _count(pairs: Iterable[Pair], pred: Callable[[Label, CascadeResult], bool]) -> int:
    return sum(1 for label, res in pairs if pred(label, res))


def _metric_set(pairs: list[Pair]) -> MetricSet:
    n = len(pairs)

    def resolved(_l: Label, r: CascadeResult) -> bool:
        return r.final_status == "resolved"

    def correct(l: Label, r: CascadeResult) -> bool:
        return resolved(l, r) and r.final_answer == l.value

    def l1_conf(_l: Label, r: CascadeResult) -> bool:
        return _confident(_level(r, 1))

    def l1_correct(l: Label, r: CascadeResult) -> bool:
        a = _level(r, 1)
        return _confident(a) and a is not None and a.answer == l.value

    def l1_not_conf(_l: Label, r: CascadeResult) -> bool:
        a = _level(r, 1)
        return a is not None and a.status != "confident"

    def l2_conf(l: Label, r: CascadeResult) -> bool:
        return l1_not_conf(l, r) and _confident(_level(r, 2))

    def l2_correct(l: Label, r: CascadeResult) -> bool:
        a = _level(r, 2)
        return l2_conf(l, r) and a is not None and a.answer == l.value

    c_correct = _count(pairs, correct)
    l1_n = _count(pairs, l1_conf)
    l1_ok = _count(pairs, l1_correct)
    return MetricSet(
        cascade_accuracy=make_metric(c_correct, _count(pairs, resolved)),
        handoff_rate=make_metric(_count(pairs, lambda _l, r: r.final_status in HANDOFF_STATUSES), n),
        escalation_rate=make_metric(_count(pairs, l1_not_conf), n),
        level1_accuracy=make_metric(l1_ok, l1_n),
        level2_escalated_accuracy=make_metric(_count(pairs, l2_correct), _count(pairs, l2_conf)),
        coverage=make_metric(c_correct, n),
        level1_standalone_accuracy=make_metric(l1_ok, l1_n),
        level1_standalone_coverage=make_metric(l1_ok, n),
        level1_standalone_abstain_rate=make_metric(n - l1_n, n),
    )


def _acceptance(overall: MetricSet) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {}
    for name, (op, limit) in ACCEPTANCE.items():
        value = getattr(overall, name).value
        out[name] = None if value is None else (value >= limit if op == ">=" else value <= limit)
    return out


def evaluate(
    results: dict[str, CascadeResult],
    labels: dict[str, Label],
    split: dict[str, str] | None = None,
    split_name: str | None = None,
    baseline_mapillary: Metric | None = None,
) -> EvaluationReport:
    """Metryki dla wyników kaskady (klucz: photo_id) wobec etykiet; tylko `certain` w mianownikach."""
    certain: list[tuple[str, Label, CascadeResult]] = []
    uncertain = 0
    for photo_id, res in results.items():
        label = labels.get(photo_id)
        if label is None or (split_name is not None and (split or {}).get(photo_id) != split_name):
            continue
        if label.status == "certain":
            certain.append((photo_id, label, res))
        else:
            uncertain += 1
    pairs = [(label, res) for _, label, res in certain]
    final = [res.final_status for _, _, res in certain]
    counts = Counts(
        certain=len(pairs),
        uncertain_excluded=uncertain,
        **{k: final.count(k) for k in ("abstain", "model_unavailable", "budget_exceeded", "image_out_of_bounds")},
    )
    overall = _metric_set(pairs)
    subgroups = {
        "numbers": _metric_set([p for p in pairs if p[0].value.isdigit()]),
        "none": _metric_set([p for p in pairs if p[0].value == NO_SIGN]),
    }
    return EvaluationReport(
        split=split_name,
        counts=counts,
        overall=overall,
        subgroups=subgroups,
        baseline_mapillary=baseline_mapillary,
        acceptance=_acceptance(overall),
    )
