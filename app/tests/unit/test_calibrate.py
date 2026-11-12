"""CAL-01: wybór progu (ADR-004 §3.9)."""

from __future__ import annotations

from mapqa.evaluation.calibrate import calibrate


def test_lowest_threshold_with_target_accuracy() -> None:  # CAL-01
    pairs = [(0.60, False)] * 5 + [(0.70, True)] * 10 + [(0.80, True)] * 10
    res = calibrate(pairs)
    assert res.threshold == 0.61
    assert res.accuracy == 1.0 and res.n == 20
    assert res.warnings == []
    assert any(b.threshold == 0.50 and b.n == 25 and b.correct == 20 for b in res.bands)


def test_no_threshold_gives_one_and_warning() -> None:
    res = calibrate([(0.9, False)] * 20)
    assert res.threshold == 1.0
    assert len(res.warnings) == 1


def test_min_n_enforced() -> None:
    res = calibrate([(0.9, True)] * 9)
    assert res.threshold == 1.0 and res.warnings
