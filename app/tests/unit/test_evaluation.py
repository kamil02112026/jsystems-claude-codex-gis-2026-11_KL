"""Ewaluacja etykiet znaków (ADR-004 §3.7-3.10; EVL-01..03)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from mapqa.contract.errors import ContractViolation
from mapqa.contract.models import CascadeResult, ModelAttempt
from mapqa.evaluation.baseline import mapillary_speed
from mapqa.evaluation.labels import Label, load_sign_labels
from mapqa.evaluation.metrics import EvaluationReport, Metric, evaluate
from mapqa.evaluation.split import split_by_sequence


def _att(level: int, answer: str | None, status: str, p: float | None = 0.95) -> ModelAttempt:
    return ModelAttempt(level=level, model="m", answer=answer, probability=p, status=status)  # type: ignore[arg-type]


def _res(photo: str, final: str, answer: str | None, attempts: list[ModelAttempt], by: str | None = None) -> CascadeResult:
    return CascadeResult(
        photo_sha256=photo,
        question_id="speed_limit_value",
        attempts=attempts,
        final_status=final,  # type: ignore[arg-type]
        final_answer=answer,
        resolved_by=by,  # type: ignore[arg-type]
    )


def _labels() -> dict[str, Label]:
    return {
        "a": Label("50", "certain", ""),
        "b": Label("50", "certain", ""),
        "c": Label("brak znaku", "certain", "no_entry"),
        "d": Label("30", "certain", ""),
        "e": Label("brak znaku", "uncertain", "zone"),
        "f": Label("70", "certain", ""),
    }


def _results() -> dict[str, CascadeResult]:
    return {
        "a": _res("a", "resolved", "50", [_att(1, "50", "confident")], "1"),
        "b": _res("b", "resolved", "60", [_att(1, "60", "confident")], "1"),  # wrong
        "c": _res(
            "c", "resolved", "brak znaku",
            [_att(1, "30", "below_threshold"), _att(2, "brak znaku", "confident")], "2",
        ),
        "d": _res("d", "abstain", None, [_att(1, None, "below_threshold"), _att(2, None, "below_threshold")]),
        "e": _res("e", "resolved", "brak znaku", [_att(1, "brak znaku", "confident")], "1"),
        "f": _res("f", "model_unavailable", None, [_att(1, None, "model_unavailable", None)]),
    }


def test_load_labels_normalizes_values(tmp_path: Path) -> None:
    p = tmp_path / "l.csv"
    p.write_text(
        "photo_id,sign_value,status,method,reviewers,note,negative_type\n"
        "p1,40,certain,m,r,,\np2,none,certain,m,r,,no_entry\n"
        "p3,unreadable,certain,m,r,,unreadable\np4,none,uncertain,m,r,x,zone\n",
        encoding="utf-8",
    )
    got = load_sign_labels(p)
    assert got["p1"] == Label("40", "certain", "")
    assert got["p2"].value == "brak znaku" and got["p2"].negative_type == "no_entry"
    assert got["p3"].value == "nieczytelny"
    assert got["p4"].status == "uncertain"


def test_split_deterministic_whole_sequences() -> None:  # EVL-01
    seqs = {f"p{i}": f"s{i // 3}" for i in range(60)}
    a = split_by_sequence(seqs, "seed1")
    assert a == split_by_sequence(seqs, "seed1")
    for s in set(seqs.values()):
        assert len({a[p] for p, sq in seqs.items() if sq == s}) == 1
    assert set(a.values()) == {"calibration", "test"}
    assert a != split_by_sequence(seqs, "seed2")


def test_split_rule_matches_adr() -> None:
    h = int(hashlib.sha256(b"seedX|sq").hexdigest()[:8], 16) % 100
    expected = "calibration" if h < 50 else "test"
    assert split_by_sequence({"p": "sq"}, "seedX") == {"p": expected}


def test_split_empty_sequence_raises() -> None:
    with pytest.raises(ContractViolation):
        split_by_sequence({"p": ""}, "s")


def test_evaluate_denominators() -> None:  # EVL-02
    rep = evaluate(_results(), _labels())
    assert rep.counts.certain == 5
    assert rep.counts.uncertain_excluded == 1
    assert rep.counts.abstain == 1
    assert rep.counts.model_unavailable == 1
    assert rep.counts.budget_exceeded == 0
    o = rep.overall
    assert (o.cascade_accuracy.numerator, o.cascade_accuracy.denominator) == (2, 3)
    assert (o.handoff_rate.numerator, o.handoff_rate.denominator) == (2, 5)
    assert (o.escalation_rate.numerator, o.escalation_rate.denominator) == (3, 5)
    assert (o.level1_accuracy.numerator, o.level1_accuracy.denominator) == (1, 2)
    assert (o.level2_escalated_accuracy.numerator, o.level2_escalated_accuracy.denominator) == (1, 1)
    assert (o.coverage.numerator, o.coverage.denominator) == (2, 5)
    assert (o.level1_standalone_accuracy.numerator, o.level1_standalone_accuracy.denominator) == (1, 2)
    assert (o.level1_standalone_coverage.numerator, o.level1_standalone_coverage.denominator) == (1, 5)
    assert o.level1_standalone_abstain_rate.numerator == 3
    assert o.cascade_accuracy.value == pytest.approx(2 / 3)


def test_evaluate_subgroups() -> None:
    rep = evaluate(_results(), _labels())
    assert rep.subgroups["numbers"].cascade_accuracy.denominator == 2
    assert rep.subgroups["none"].cascade_accuracy.numerator == 1
    assert rep.subgroups["none"].coverage.denominator == 1


def test_zero_denominator_value_none() -> None:
    rep = evaluate({}, _labels())
    assert rep.overall.cascade_accuracy.denominator == 0
    assert rep.overall.cascade_accuracy.value is None
    assert rep.acceptance["cascade_accuracy"] is None


def test_split_filter() -> None:
    split = {"a": "test", "b": "calibration", "c": "test", "d": "calibration", "e": "test", "f": "calibration"}
    rep = evaluate(_results(), _labels(), split, "test")
    assert rep.split == "test"
    assert rep.counts.certain == 2 and rep.counts.uncertain_excluded == 1


def test_report_validates_and_roundtrips() -> None:  # TAC-004-04
    rep = evaluate(_results(), _labels())
    again = EvaluationReport.model_validate_json(rep.model_dump_json())
    assert again == rep
    with pytest.raises(ValidationError):
        Metric(numerator=1, denominator=2, value=0.5, extra=1)  # type: ignore[call-arg]


def test_mapillary_speed_value() -> None:  # EVL-03
    assert mapillary_speed("regulatory--maximum-speed-limit-40--g1") == "40"
    assert mapillary_speed("regulatory--no-entry--g1") == "brak znaku"
    assert mapillary_speed("regulatory--end-of-maximum-speed-limit-60--g1") == "brak znaku"
    assert mapillary_speed("") is None
