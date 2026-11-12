"""Ewaluacja odczytu modelu (ADR-004 §3.7–§3.10). Jedyny moduł czytający pliki etykiet.

Inne moduły korzystają wyłącznie z tej fasady i nigdy nie dotykają plików etykiet ani `evaluation.labels` (TAC-004-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mapqa.contract.models import CascadeResult
from mapqa.evaluation.baseline import OsmDiscrepancies, load_signs, mapillary_baseline, osm_discrepancies
from mapqa.evaluation.calibrate import calibrate
from mapqa.evaluation.labels import load_sign_labels
from mapqa.evaluation.metrics import EvaluationReport, evaluate
from mapqa.evaluation.split import split_by_sequence


def _paths(labels_path: Path) -> tuple[Path, Path, Path]:
    root = Path(labels_path) / "signs"
    return root / "labels.csv", root / "signs.csv", root / "nearest_osm.csv"


def evaluation_input_files(labels_path: Path) -> list[Path]:
    """Pliki czytane przez ewaluator (do manifestu wejść runu, ADR-000 D12)."""
    return [p for p in _paths(labels_path) if p.is_file()]


def photo_split(labels_path: Path) -> dict[str, str]:
    """photo_id → 'calibration' | 'test' według sekwencji (ADR-004 §3.7)."""
    _, signs_csv, _ = _paths(labels_path)
    return split_by_sequence({pid: row.sequence for pid, row in load_signs(signs_csv).items()})


@dataclass
class EvaluationOutput:
    report: EvaluationReport | None
    discrepancies: OsmDiscrepancies | None


def run_evaluation(
    labels_path: Path,
    results: dict[str, CascadeResult],
    *,
    split_name: str | None,
    with_model: bool,
) -> EvaluationOutput:
    labels_csv, signs_csv, nearest_csv = _paths(labels_path)
    if not labels_csv.is_file():
        return EvaluationOutput(None, None)
    labels = load_sign_labels(labels_csv)
    signs = load_signs(signs_csv)
    split = split_by_sequence({pid: row.sequence for pid, row in signs.items()}) if split_name else None
    baseline = mapillary_baseline(labels, signs, split, split_name)
    discrepancies = osm_discrepancies(labels, nearest_csv)
    report = evaluate(results, labels, split, split_name, baseline) if with_model else None
    return EvaluationOutput(report, discrepancies)


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
