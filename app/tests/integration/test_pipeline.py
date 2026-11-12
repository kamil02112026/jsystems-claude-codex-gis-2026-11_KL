"""T14/T21: pipeline on the real signs data (ADR-004 E2E-01, INP-01; ADR-003 NOM-01, CNF-01, CAC-01, BUD-01; ADR-000 TAC-03, TAC-13, TAC-14, D11, D12)."""

from __future__ import annotations

import csv
import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from mapqa.cascade.ports import PortResult
from mapqa.cli.main import main

pipeline = importlib.import_module("mapqa.pipeline")


class FakePort:
    """Stands in for OUR ModelPort (not HTTP): answers every L1 question with the OSM-independent value '50'."""

    def __init__(self, probability: float = 0.95, fail_after: int | None = None) -> None:
        self.calls = 0
        self.probability = probability
        self.fail_after = fail_after

    def ask(self, *, level, model, reasoning_effort, image, question):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            return PortResult(answer=None, probability=None, parse_status="model_unavailable", error_class="503")
        return PortResult(answer="50", probability=self.probability, parse_status="ok", cost_usd=Decimal("0.001"), response_body="{}")


@pytest.fixture
def cfg(tmp_path: Path, data_dir: Path, monkeypatch, repo_root: Path) -> Path:
    for var in ("MAPQA_SOURCE", "MAPQA_CONFIG", "OPENROUTER_API_KEY", "DECISION_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(repo_root)
    p = tmp_path / "mapqa.toml"
    p.write_text(
        f"reports_dir = '{(tmp_path / 'reports').as_posix()}'\n"
        f"cache_dir = '{(tmp_path / 'cache').as_posix()}'\n"
        f"labels_path = '{data_dir.as_posix()}'\n"
        f"[sources.files]\ntype = 'files'\npath = '{data_dir.as_posix()}'\n",
        encoding="utf-8",
    )
    return p


def _run(cfg: Path, capsys, *extra: str) -> tuple[int, dict]:
    rc = main(["run", "--config", str(cfg), "--output", "json", *extra])
    return rc, json.loads(capsys.readouterr().out)


def test_e2e01_no_model_run_writes_report_and_queue(cfg: Path, capsys, monkeypatch) -> None:
    def no_port(*a, **k):
        raise AssertionError("no-model run must not build a model client (TAC-13)")

    monkeypatch.setattr(pipeline, "build_port", no_port)
    rc, doc = _run(cfg, capsys)
    assert rc == 0 and doc["ok"]
    res = doc["result"]
    out = Path(res["output_dir"])
    assert {"report.md", "manual_queue.csv", "run.json"} <= {p.name for p in out.iterdir()}
    assert res["model_reading"] is False
    assert res["funnel"]["skipped_no_model"] == 119
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "\n\nOdczyt modelem nie był uruchomiony" in report  # own paragraph, not glued to the list
    assert "baseline_mapillary" in report  # detector baseline is shown also without the model (PRD §9)
    with open(out / "manual_queue.csv", encoding="utf-8-sig", newline="") as f:
        assert list(csv.reader(f))[1:] == []  # QUE-01: skipped_no_model creates no queue items
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    hashes = run["source"]["input_hashes"]
    assert len(hashes) >= 121 and all(v["before"] == v["after"] for v in hashes.values())  # TAC-14


def test_inp01_input_changed_during_run_gives_code_4(cfg: Path, capsys, monkeypatch, tmp_path: Path, data_dir: Path) -> None:
    import shutil

    copy = tmp_path / "data"
    shutil.copytree(data_dir / "signs", copy / "signs", ignore=shutil.ignore_patterns("photos"))
    shutil.copy(data_dir / "osm_roads.parquet", copy / "osm_roads.parquet")
    cfg.write_text(cfg.read_text(encoding="utf-8").replace(data_dir.as_posix(), copy.as_posix()), encoding="utf-8")
    original = pipeline._write_outputs

    def tamper(*args, **kwargs):
        written = original(*args, **kwargs)
        victim = sorted((copy / "signs" / "crops").glob("*.jpg"))[0]
        victim.write_bytes(victim.read_bytes() + b"x")
        return written

    monkeypatch.setattr(pipeline, "_write_outputs", tamper)
    rc, doc = _run(cfg, capsys)
    assert rc == 4 and doc["error"]["code"] == "input_modified"
    out_dirs = list((tmp_path / "reports").iterdir())
    report = (out_dirs[0] / "report.md").read_text(encoding="utf-8")
    assert "niewiarygodne" in report.lower()


def test_cnf01_model_without_tty_and_yes_is_code_1_zero_calls(cfg: Path, capsys, monkeypatch) -> None:
    port = FakePort()
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: port)
    monkeypatch.setattr(pipeline, "_stdin_is_tty", lambda: False)
    rc, doc = _run(cfg, capsys, "--model")
    assert rc == 1 and doc["error"]["code"] == "confirmation_required"
    assert port.calls == 0
    assert not (Path(cfg).parent / "reports").exists() or not any((Path(cfg).parent / "reports").iterdir())


def test_model_run_with_yes_then_warm_cache(cfg: Path, capsys, monkeypatch) -> None:
    port = FakePort()
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: port)
    rc, doc = _run(cfg, capsys, "--model", "--yes", "--max-images", "5")
    assert rc == 3  # 119 images > max_images=5 → budget_exceeded for the rest (ADR-003 §3.6)
    first_calls = port.calls
    assert first_calls == 5  # only level 1, all confident
    assert doc["result"]["confirmation"] == "flag_yes"
    assert any(w.startswith("budget_exceeded") for w in doc["warnings"])
    assert doc["result"]["manifest"]["max_images"] == 5
    # CAC-01: same parameters again → the 5 cached images make no requests, 5 new ones are read
    rc2, doc2 = _run(cfg, capsys, "--model", "--yes", "--max-images", "5")
    assert port.calls == first_calls + 5
    assert doc2["result"]["funnel"]["cache_hits_l1"] == 5


def test_circuit_breaker_gives_code_3_and_report(cfg: Path, capsys, monkeypatch) -> None:
    port = FakePort(fail_after=2)
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: port)
    rc, doc = _run(cfg, capsys, "--model", "--yes")
    assert rc == 3
    assert port.calls == 3  # first error opens the breaker; no further requests (TAC-003-06)
    assert any(w.startswith("circuit_open") for w in doc["warnings"])
    report = (Path(doc["result"]["output_dir"]) / "report.md").read_text(encoding="utf-8")
    assert "Odczyt przerwany" in report or "503" in report


def test_declined_confirmation_gives_report_without_model(cfg: Path, capsys, monkeypatch) -> None:
    port = FakePort()
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: port)
    monkeypatch.setattr(pipeline, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    rc, doc = _run(cfg, capsys, "--model")
    assert rc == 0 and port.calls == 0
    assert doc["result"]["confirmation"] == "declined"
    assert "model_reading_declined" in doc["warnings"]
