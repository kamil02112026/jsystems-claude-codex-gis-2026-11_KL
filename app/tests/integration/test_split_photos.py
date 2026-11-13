"""Podział kalibracja / test na pełnych kadrach `photos.csv` (ADR-004 §3.7, PRD §7, EVL-01)."""

from __future__ import annotations

from pathlib import Path

from mapqa.evaluation import photo_split
from mapqa.evaluation.split import load_sequences, split_by_sequence

MAP_QA = Path(__file__).resolve().parents[3] / "course-materials" / "exercise-data" / "map-qa"
PHOTOS = MAP_QA / "photos.csv"


def test_load_sequences_all_photos() -> None:
    seq = load_sequences(PHOTOS)
    assert len(seq) == 561
    assert len(set(seq.values())) == 108
    assert all(seq.values())


def test_no_sequence_in_both_splits_photos() -> None:  # EVL-01, TAC-004-05
    seq = load_sequences(PHOTOS)
    split = split_by_sequence(seq, "mapqa-2026-11")
    assert set(split) == set(seq)
    cal = {seq[p] for p, v in split.items() if v == "calibration"}
    test = {seq[p] for p, v in split.items() if v == "test"}
    assert cal and test and not (cal & test)


def test_photo_split_facade_photos_dataset() -> None:
    split = photo_split(MAP_QA, dataset="photos")
    seq = load_sequences(PHOTOS)
    assert set(split) == set(seq)
    cal = {seq[p] for p, v in split.items() if v == "calibration"}
    test = {seq[p] for p, v in split.items() if v == "test"}
    assert not (cal & test)
