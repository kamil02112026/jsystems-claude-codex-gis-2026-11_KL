"""T05/T07: CLI skeleton, JSON envelope, exit codes, sources commands (ADR-000 §6, D13; TAC-02, TAC-03; PRD F8.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mapqa.cli.main import main
from mapqa.contract.models import Envelope


def _json(capsys) -> dict:
    out = capsys.readouterr().out
    doc = json.loads(out)  # exactly one JSON document on stdout
    Envelope.model_validate(doc)  # TAC-02
    return doc


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, repo_root: Path):
    for var in ("MAPQA_SOURCE", "MAPQA_CONFIG", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(repo_root)


@pytest.mark.parametrize("bbox", ["20.15,49.95,19.80,50.15", "19.8,49.9,200,50", "1,2,3", "a,b,c,d"])
def test_invalid_bbox_exit_1_before_any_source(bbox: str, capsys, monkeypatch) -> None:
    import importlib

    called = []
    monkeypatch.setattr(importlib.import_module("mapqa.cli.main"), "build_adapter", lambda *a, **k: called.append(1))
    assert main(["run", "--bbox", bbox, "--output", "json"]) == 1
    doc = _json(capsys)
    assert doc["error"]["code"] == "invalid_bbox"
    assert not called


def test_unknown_source_exit_1_with_hint(capsys) -> None:
    assert main(["sources", "check", "--source", "nope", "--output", "json"]) == 1
    doc = _json(capsys)
    assert doc["error"]["code"] == "unknown_source"
    assert "files" in doc["error"]["hint"]


def test_sources_list_json(capsys) -> None:
    assert main(["sources", "list", "--output", "json"]) == 0
    doc = _json(capsys)
    src = doc["result"]["sources"]
    assert {"name": "files", "type": "files", "access": "local", "is_default": True, "resolved_by": "builtin"} in src


def test_sources_list_example_config_two_sources(capsys) -> None:  # TAC-001-02
    assert main(["sources", "list", "--config", "app/mapqa.example.toml", "--output", "json"]) == 0
    names = {s["name"]: s for s in _json(capsys)["result"]["sources"]}
    assert set(names) == {"files", "course-databricks"}
    assert names["course-databricks"]["access"] == "rest"
    assert names["files"]["is_default"] is True


def test_sources_check_counts(capsys) -> None:
    assert main(["sources", "check", "--output", "json"]) == 0
    tables = _json(capsys)["result"]["tables"]
    assert tables["photos"]["total"] == 561 and tables["traffic_signs"]["total"] == 1730


def test_databricks_source_not_in_mvp(capsys) -> None:
    rc = main(["sources", "check", "--config", "app/mapqa.example.toml", "--source", "course-databricks", "--output", "json"])
    assert rc == 1
    assert _json(capsys)["error"]["code"] == "source_type_not_implemented"


def test_text_output_is_human_readable(capsys) -> None:
    assert main(["sources", "list"]) == 0
    out = capsys.readouterr().out
    assert "files" in out and not out.lstrip().startswith("{")


def test_unknown_attribute_exit_1(capsys) -> None:
    assert main(["run", "--attributes", "speed_limit,colour", "--output", "json"]) == 1
    assert _json(capsys)["error"]["code"] == "invalid_attribute"


def test_mvp_rejects_photos_dataset(capsys) -> None:
    assert main(["run", "--dataset", "photos", "--output", "json"]) == 1
    assert _json(capsys)["error"]["code"] == "dataset_not_available"


def test_argparse_error_is_exit_1_json(capsys) -> None:
    assert main(["run", "--max-queries", "abc", "--output", "json"]) == 1
