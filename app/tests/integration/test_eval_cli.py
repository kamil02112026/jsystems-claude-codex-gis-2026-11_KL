"""T24: eval run / eval calibrate (ADR-000 §6; ADR-004 §3.7–§3.9, CAL-01, TAC-004-01, TAC-004-04, TAC-004-05)."""

from __future__ import annotations

import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from mapqa.cascade.ports import PortResult
from mapqa.cli.main import main
from mapqa.evaluation.metrics import EvaluationReport

pipeline = importlib.import_module("mapqa.pipeline")


class EchoPort:
    """Our port fake: answers '50' with probability depending on the image size (deterministic)."""

    def __init__(self) -> None:
        self.calls = 0

    def ask(self, *, level, model, reasoning_effort, image, question):
        self.calls += 1
        p = 0.55 + (len(image.data) % 40) / 100  # 0.55..0.94, deterministic per image
        return PortResult(answer="50", probability=p, parse_status="ok", cost_usd=Decimal("0"), response_body="{}")


@pytest.fixture
def cfg(tmp_path: Path, data_dir: Path, monkeypatch, repo_root: Path) -> Path:
    for var in ("MAPQA_SOURCE", "MAPQA_CONFIG", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(repo_root)
    p = tmp_path / "mapqa.toml"
    p.write_text(
        f"reports_dir = '{(tmp_path / 'reports').as_posix()}'\ncache_dir = '{(tmp_path / 'cache').as_posix()}'\n"
        f"labels_path = '{data_dir.as_posix()}'\n[sources.files]\ntype = 'files'\npath = '{data_dir.as_posix()}'\n"
        "[limits]\nmax_queries = 400\nmax_images = 200\nmax_usd = '10'\n",
        encoding="utf-8",
    )
    return p


def _eval(cfg: Path, capsys, *args: str) -> tuple[int, dict]:
    rc = main(["eval", *args, "--config", str(cfg), "--output", "json"])
    return rc, json.loads(capsys.readouterr().out)


def test_eval_requires_confirmation_without_tty(cfg, capsys, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "_stdin_is_tty", lambda: False)
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: EchoPort())
    rc, doc = _eval(cfg, capsys, "run")
    assert rc == 1 and doc["error"]["code"] == "confirmation_required"


def test_eval_run_test_split_writes_valid_evaluation(cfg, capsys, monkeypatch) -> None:
    port = EchoPort()
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: port)
    rc, doc = _eval(cfg, capsys, "run", "--yes")
    assert rc == 0
    out = Path(doc["result"]["output_dir"])
    report = EvaluationReport.model_validate_json((out / "evaluation.json").read_text(encoding="utf-8"))  # TAC-004-04
    assert report.split == "test"
    assert report.overall.cascade_accuracy.denominator > 0
    first = (out / "evaluation.json").read_bytes()
    queue1 = (out / "manual_queue.csv").read_bytes()
    # TAC-004-01 / TAC-05: second run on a warm cache → identical bytes, 0 new requests
    calls = port.calls
    rc2, doc2 = _eval(cfg, capsys, "run", "--yes")
    out2 = Path(doc2["result"]["output_dir"])
    assert port.calls == calls
    assert (out2 / "evaluation.json").read_bytes() == first
    assert (out2 / "manual_queue.csv").read_bytes() == queue1


def test_eval_calibrate_writes_calibration(cfg, capsys, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: EchoPort())
    rc, doc = _eval(cfg, capsys, "calibrate", "--yes")
    assert rc == 0
    out = Path(doc["result"]["output_dir"])
    cal = json.loads((out / "calibration.json").read_text(encoding="utf-8"))
    assert cal  # proposal from the calibration split only
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["params"]["split"] == "calibration"
