"""Dane kursu: podział i baseline znaków (TAC-004-05, PRD §7/§9)."""

from __future__ import annotations

from pathlib import Path

from mapqa.evaluation.baseline import load_signs, mapillary_baseline, osm_discrepancies
from mapqa.evaluation.labels import load_sign_labels
from mapqa.evaluation.split import split_by_sequence

SIGNS = Path(__file__).resolve().parents[3] / "course-materials" / "exercise-data" / "map-qa" / "signs"


def test_label_counts() -> None:
    labels = load_sign_labels(SIGNS / "labels.csv")
    assert len(labels) == 119
    assert sum(1 for x in labels.values() if x.status == "certain") == 115
    assert sum(1 for x in labels.values() if x.status == "uncertain") == 4


def test_no_sequence_in_both_splits() -> None:  # TAC-004-05, EVL-01
    signs = load_signs(SIGNS / "signs.csv")
    seq = {p: s.sequence for p, s in signs.items()}
    assert len(set(seq.values())) == 103
    split = split_by_sequence(seq, "mapqa-2026-11")
    cal = {seq[p] for p, v in split.items() if v == "calibration"}
    test = {seq[p] for p, v in split.items() if v == "test"}
    assert cal and test and not (cal & test)


def test_osm_discrepancy_breakdown() -> None:
    labels = load_sign_labels(SIGNS / "labels.csv")
    d = osm_discrepancies(labels, SIGNS / "nearest_osm.csv")
    assert (d.numeric_certain, d.equal, d.differ, d.no_maxspeed) == (89, 25, 46, 18)


def test_mapillary_baseline_shape() -> None:
    labels = load_sign_labels(SIGNS / "labels.csv")
    signs = load_signs(SIGNS / "signs.csv")
    m = mapillary_baseline(labels, signs)
    assert 0 < m.numerator <= m.denominator <= 115
    assert m.value == m.numerator / m.denominator
