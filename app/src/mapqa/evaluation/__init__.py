"""Ewaluacja odczytu modelu (ADR-004 §3.7–§3.10). Jedyny moduł czytający pliki etykiet.

Inne moduły korzystają wyłącznie z tej fasady i nigdy nie dotykają plików etykiet ani `evaluation.labels` (TAC-004-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mapqa.contract.models import CascadeResult
from mapqa.evaluation.baseline import OsmDiscrepancies, load_signs, mapillary_baseline, osm_discrepancies
from mapqa.evaluation.calibrate import calibrate
from mapqa.evaluation.labels import load_reference_labels, load_sign_labels
from mapqa.evaluation.metrics import EvaluationReport, Metric, evaluate
from mapqa.evaluation.split import load_sequences, split_by_sequence

Dataset = Literal["signs", "photos"]


def _paths(labels_path: Path) -> tuple[Path, Path, Path]:
    root = Path(labels_path) / "signs"
    return root / "labels.csv", root / "signs.csv", root / "nearest_osm.csv"


def _photo_paths(labels_path: Path) -> tuple[Path, Path]:
    """Pełne kadry: etykiety i sekwencje z katalogu danych kursu (`reference_labels.csv`, `photos.csv`)."""
    root = Path(labels_path)
    return root / "reference_labels.csv", root / "photos.csv"


def evaluation_input_files(labels_path: Path, dataset: Dataset = "signs") -> list[Path]:
    """Pliki czytane przez ewaluator (do manifestu wejść runu, ADR-000 D12)."""
    paths = _photo_paths(labels_path) if dataset == "photos" else _paths(labels_path)
    return [p for p in paths if p.is_file()]


def photo_split(labels_path: Path, dataset: Dataset = "signs") -> dict[str, str]:
    """photo_id → 'calibration' | 'test' według sekwencji (ADR-004 §3.7)."""
    if dataset == "photos":
        _, photos_csv = _photo_paths(labels_path)
        return split_by_sequence(load_sequences(photos_csv))
    _, signs_csv, _ = _paths(labels_path)
    return split_by_sequence({pid: row.sequence for pid, row in load_signs(signs_csv).items()})


@dataclass
class EvaluationOutput:
    report: EvaluationReport | None
    discrepancies: OsmDiscrepancies | None
    baseline_mapillary: Metric | None = None


def run_evaluation(
    labels_path: Path,
    results: dict[str, CascadeResult],
    *,
    split_name: str | None,
    with_model: bool,
    photo_ids: set[str] | None = None,
    question_id: str = "speed_limit_value",
    dataset: Dataset = "signs",
) -> EvaluationOutput:
    """`photo_ids` = the run's photo set (after --bbox / --split), so every report section counts the same photos.

    `dataset="photos"`: pełne kadry (`reference_labels.csv`) dla `question_id`; baseline i rozbieżności OSM nie dotyczą.
    Prędkość na pełnych kadrach jest raportowana opisowo, bez progów akceptacji (PRD §7).
    """
    if dataset == "photos":
        return _run_photos(labels_path, results, split_name, with_model, photo_ids, question_id)
    labels_csv, signs_csv, nearest_csv = _paths(labels_path)
    if not labels_csv.is_file():
        return EvaluationOutput(None, None)
    labels = load_sign_labels(labels_csv)
    if photo_ids is not None:
        labels = {pid: lab for pid, lab in labels.items() if pid in photo_ids}
    signs = load_signs(signs_csv)
    split = split_by_sequence({pid: row.sequence for pid, row in signs.items()}) if split_name else None
    baseline = mapillary_baseline(labels, signs, split, split_name)
    discrepancies = osm_discrepancies(labels, nearest_csv)
    report = evaluate(results, labels, split, split_name, baseline) if with_model else None
    return EvaluationOutput(report, discrepancies, baseline)


def _run_photos(
    labels_path: Path,
    results: dict[str, CascadeResult],
    split_name: str | None,
    with_model: bool,
    photo_ids: set[str] | None,
    question_id: str,
) -> EvaluationOutput:
    labels_csv, photos_csv = _photo_paths(labels_path)
    if not labels_csv.is_file():
        return EvaluationOutput(None, None)
    labels = load_reference_labels(labels_csv, question_id)
    if photo_ids is not None:
        labels = {pid: lab for pid, lab in labels.items() if pid in photo_ids}
    split = split_by_sequence(load_sequences(photos_csv)) if split_name else None
    descriptive = question_id == "speed_limit_value"
    report = (
        evaluate(results, labels, split, split_name, question_id=question_id, with_acceptance=not descriptive)
        if with_model
        else None
    )
    return EvaluationOutput(report, None, None)


def calibration_pairs(labels_path: Path, results: dict[str, CascadeResult], level: int) -> list[tuple[float, bool]]:
    """(prawdopodobieństwo, czy poprawna) dla odpowiedzi poziomu n na zdjęciach z etykietą certain (ADR-004 §3.9)."""
    labels_csv, _, _ = _paths(labels_path)
    labels = load_sign_labels(labels_csv)
    pairs: list[tuple[float, bool]] = []
    for pid, res in results.items():
        lab = labels.get(pid)
        attempt = next((a for a in res.attempts if a.level == level and a.probability is not None), None)
        if lab is None or lab.status != "certain" or attempt is None or attempt.answer is None:
            continue
        pairs.append((attempt.probability, attempt.answer == lab.value))
    return pairs


__all__ = [
    "EvaluationOutput",
    "EvaluationReport",
    "OsmDiscrepancies",
    "calibrate",
    "calibration_pairs",
    "evaluation_input_files",
    "photo_split",
    "run_evaluation",
]
