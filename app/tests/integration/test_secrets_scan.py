"""TAC-06 / TAC-001-03: fake secrets never appear in run outputs, cache, stdout or stderr."""

from __future__ import annotations

import importlib
import re
from decimal import Decimal
from pathlib import Path

from mapqa.cascade.ports import PortResult
from mapqa.cli.main import main

pipeline = importlib.import_module("mapqa.pipeline")
SECRET = "TEST_SECRET_0123456789abcdef"
PATTERN = re.compile(rb"TEST_SECRET_[0-9a-f]{16}")


class Port:
    def ask(self, **_):
        return PortResult(answer="40", probability=0.9, parse_status="ok", cost_usd=Decimal("0.001"), response_body='{"ok":1}')


def test_no_secret_in_any_output(tmp_path: Path, data_dir: Path, repo_root: Path, monkeypatch, capfd) -> None:
    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("DATABRICKS_TOKEN", SECRET)
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: Port())
    cfg = tmp_path / "mapqa.toml"
    cfg.write_text(
        f"reports_dir = '{(tmp_path / 'reports').as_posix()}'\ncache_dir = '{(tmp_path / 'cache').as_posix()}'\n"
        f"[sources.files]\ntype='files'\npath='{data_dir.as_posix()}'\n",
        encoding="utf-8",
    )
    rc = main(["run", "--model", "--yes", "--config", str(cfg), "--output", "json", "--max-images", "3"])
    assert rc in (0, 3)
    captured = capfd.readouterr()
    assert not PATTERN.search((captured.out + captured.err).encode())
    files = [p for p in tmp_path.rglob("*") if p.is_file() and p.name != "mapqa.toml"]
    assert any(p.name == "llm_cache.sqlite" for p in files)
    for p in files:
        assert not PATTERN.search(p.read_bytes()), p
