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
    # only below_threshold / invalid_response go to level 2 (ADR-003 §3.5); model_unavailable on L1 does not (f)
    assert (o.escalation_rate.numerator, o.escalation_rate.denominator) == (2, 5)
    assert (o.level1_accuracy.numerator, o.level1_accuracy.denominator) == (1, 2)
    assert (o.level2_escalated_accuracy.numerator, o.level2_escalated_accuracy.denominator) == (1, 1)
    assert (o.coverage.numerator, o.coverage.denominator) == (2, 5)
    assert (o.level1_standalone_accuracy.numerator, o.level1_standalone_accuracy.denominator) == (1, 2)
    assert (o.level1_standalone_coverage.numerator, o.level1_standalone_coverage.denominator) == (1, 5)
    assert o.level1_standalone_abstain_rate.numerator == 3
    assert o.cascade_accuracy.value == pytest.approx(2 / 3)


def test_budget_exceeded_is_not_escalation() -> None:
    """Found in the first paid run (2026-11-13): 94 budget refusals were reported as 'escalated to level 2'."""
    labels = {"a": Label("50", "certain", ""), "b": Label("30", "certain", "")}
    results = {
        "a": _res("a", "resolved", "50", [_att(1, "50", "confident")], "1"),
        "b": _res("b", "budget_exceeded", None, [_att(1, None, "budget_exceeded", None)], "human"),
    }
    o = evaluate(results, labels).overall
    assert (o.escalation_rate.numerator, o.escalation_rate.denominator) == (0, 2)
    assert o.handoff_rate.numerator == 1  # budget_exceeded still counts as handed to a human (D10-I4)


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


# --- T45: etykiety zdjęć (pełne kadry): oświetlenie i prędkość ---------------------------------

from mapqa.evaluation import evaluation_input_files, run_evaluation  # noqa: E402
from mapqa.evaluation.labels import load_reference_labels  # noqa: E402

MAP_QA = Path(__file__).resolve().parents[3] / "course-materials" / "exercise-data" / "map-qa"
REFERENCE = MAP_QA / "reference_labels.csv"


def _lit_res(photo: str, answer: str | None, final: str = "resolved") -> CascadeResult:
    attempts = [ModelAttempt(level=1, model="m", answer=answer, probability=0.95, status="confident")]  # type: ignore[arg-type]
    return CascadeResult(
        photo_sha256=photo,
        question_id="street_lamp_visible",
        attempts=attempts,
        final_status=final,  # type: ignore[arg-type]
        final_answer=answer,
        resolved_by="1" if final == "resolved" else None,  # type: ignore[arg-type]
    )


def test_reference_lit_mapping_and_counts_real_file() -> None:
    labels = load_reference_labels(REFERENCE, "street_lamp_visible")
    assert len(labels) == 100
    certain = [x for x in labels.values() if x.status == "certain"]
    assert len(certain) == 79
    assert sum(1 for x in certain if x.value == "tak") == 54
    assert sum(1 for x in certain if x.value == "nie") == 25
    assert sum(1 for x in labels.values() if x.status == "uncertain") == 21


def test_reference_speed_full_frames_real_file() -> None:
    labels = load_reference_labels(REFERENCE, "speed_limit_value")
    assert len(labels) == 20
    certain = [x for x in labels.values() if x.status == "certain"]
    assert len(certain) == 14
    assert {x.value for x in certain} == {"30", "70", "brak znaku"}


def test_reference_labels_one_row_per_photo_and_question() -> None:
    import csv

    with REFERENCE.open(encoding="utf-8-sig", newline="") as fh:
        keys = [(r["photo_id"], r["question"]) for r in csv.DictReader(fh)]
    assert len(keys) == len(set(keys))


def test_load_reference_labels_maps_yes_no_unknown(tmp_path: Path) -> None:
    p = tmp_path / "reference_labels.csv"
    p.write_text(
        "photo_id,question,label,status,method,reviewer,reviewed_at,note\n"
        "p1,street_lighting_visible,yes,certain,m,r,,\n"
        "p2,street_lighting_visible,no,certain,m,r,,\n"
        "p3,street_lighting_visible,unknown,uncertain,m,r,,\n"
        "p1,surface,paved,certain,m,r,,\n",
        encoding="utf-8",
    )
    got = load_reference_labels(p, "street_lamp_visible")
    assert got == {
        "p1": Label("tak", "certain", ""),
        "p2": Label("nie", "certain", ""),
        "p3": Label("unknown", "uncertain", ""),
    }


def test_load_reference_labels_speed_full_frame_mapping(tmp_path: Path) -> None:
    p = tmp_path / "reference_labels.csv"
    p.write_text(
        "photo_id,question,label,status,method,reviewer,reviewed_at,note\n"
        "p1,speed_limit_value,none,certain,m,r,,\n"
        "p2,speed_limit_value,30,certain,m,r,,\n"
        "p3,speed_limit_value,unreadable,certain,m,r,,\n",
        encoding="utf-8",
    )
    got = load_reference_labels(p, "speed_limit_value")
    assert got["p1"].value == "brak znaku"
    assert got["p2"].value == "30"
    assert got["p3"].value == "nieczytelny"


def test_load_reference_labels_unknown_question_raises() -> None:
    with pytest.raises(ContractViolation):
        load_reference_labels(REFERENCE, "no_such_question")


def test_lit_denominators_on_real_labels() -> None:
    labels = load_reference_labels(REFERENCE, "street_lamp_visible")
    certain = {p for p, x in labels.items() if x.status == "certain"}
    # every certain photo resolved with its label -> accuracy 79/79; 21 uncertain excluded
    results = {p: _lit_res(p, labels[p].value) for p in labels}
    rep = evaluate(results, labels, question_id="street_lamp_visible")
    assert rep.question_id == "street_lamp_visible"
    assert rep.counts.certain == 79 and rep.counts.uncertain_excluded == 21
    assert (rep.overall.cascade_accuracy.numerator, rep.overall.cascade_accuracy.denominator) == (79, 79)
    assert (rep.overall.handoff_rate.numerator, rep.overall.handoff_rate.denominator) == (0, 79)
    assert rep.overall.coverage.denominator == len(certain) == 79


def test_lit_subgroups_tak_and_nie() -> None:
    labels = {"a": Label("tak", "certain"), "b": Label("tak", "certain"), "c": Label("nie", "certain")}
    results = {"a": _lit_res("a", "tak"), "b": _lit_res("b", "nie"), "c": _lit_res("c", "nie")}
    rep = evaluate(results, labels, question_id="street_lamp_visible")
    assert set(rep.subgroups) == {"tak", "nie"}
    assert (rep.subgroups["tak"].cascade_accuracy.numerator, rep.subgroups["tak"].cascade_accuracy.denominator) == (1, 2)
    assert (rep.subgroups["nie"].cascade_accuracy.numerator, rep.subgroups["nie"].cascade_accuracy.denominator) == (1, 1)


def test_speed_subgroups_unchanged_by_default() -> None:
    rep = evaluate(_results(), _labels())
    assert set(rep.subgroups) == {"numbers", "none"}
    assert rep.question_id == "speed_limit_value"


def test_run_evaluation_photos_lit_facade() -> None:
    labels = load_reference_labels(REFERENCE, "street_lamp_visible")
    results = {p: _lit_res(p, x.value) for p, x in labels.items() if x.status == "certain"}
    out = run_evaluation(
        MAP_QA, results, split_name=None, with_model=True, question_id="street_lamp_visible", dataset="photos"
    )
    assert out.report is not None
    assert out.report.counts.certain == 79
    assert out.baseline_mapillary is None and out.discrepancies is None


def test_evaluation_input_files_photos_includes_reference_and_photos() -> None:
    files = evaluation_input_files(MAP_QA, dataset="photos")
    names = {p.name for p in files}
    assert {"reference_labels.csv", "photos.csv"} <= names


def test_evaluation_input_files_signs_default_unchanged() -> None:
    names = {p.name for p in evaluation_input_files(MAP_QA)}
    assert "labels.csv" in names and "reference_labels.csv" not in names


def test_full_frame_speed_is_descriptive_without_thresholds() -> None:  # PRD §7: pełne kadry opisowo
    labels = load_reference_labels(REFERENCE, "speed_limit_value")
    results = {p: _res(p, "resolved", x.value, [_att(1, x.value, "confident")], "1") for p, x in labels.items() if x.status == "certain"}
    out = run_evaluation(MAP_QA, results, split_name=None, with_model=True, question_id="speed_limit_value", dataset="photos")
    assert out.report is not None and out.report.counts.certain == 14
    assert all(v is None for v in out.report.acceptance.values())


def test_lit_photos_use_lighting_thresholds() -> None:  # PRD §7: oświetlenie ma progi jak prędkość na wycinkach
    labels = load_reference_labels(REFERENCE, "street_lamp_visible")
    results = {p: _lit_res(p, x.value) for p, x in labels.items() if x.status == "certain"}
    out = run_evaluation(MAP_QA, results, split_name=None, with_model=True, question_id="street_lamp_visible", dataset="photos")
    assert out.report is not None and out.report.acceptance["cascade_accuracy"] is True
