"""T26: real CLI process on course data, offline (ADR-000 TAC-01, TAC-04, TAC-09; ADR-004 E2E-01, TAC-004-03, TAC-004-06)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _cli(repo_root: Path, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith(("MAPQA_", "OPENROUTER"))}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "mapqa.cli", *args],
        cwd=repo_root,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


@pytest.fixture
def cfg(tmp_path: Path, data_dir: Path) -> Path:
    p = tmp_path / "mapqa.toml"
    p.write_text(
        f"reports_dir = '{(tmp_path / 'reports').as_posix()}'\ncache_dir = '{(tmp_path / 'cache').as_posix()}'\n",
        encoding="utf-8",
    )
    return p


def test_help_exit_0(repo_root: Path) -> None:  # TAC-09
    assert _cli(repo_root, "--help").returncode == 0


def test_no_model_run_real_process(repo_root: Path, cfg: Path) -> None:  # E2E-01, TAC-04
    t0 = time.monotonic()
    proc = _cli(repo_root, "run", "--config", str(cfg), "--output", "json")
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)  # exactly one JSON document on stdout
    assert doc["ok"] and doc["result"]["model_reading"] is False
    assert elapsed <= 120
    out = Path(doc["result"]["output_dir"])
    report = (out / "report.md").read_text(encoding="utf-8")
    for link in re.findall(r"\]\((thumbs/[^)]+)\)", report):  # TAC-004-03
        assert (out / link).is_file()
    assert "data:image" not in report


def test_source_unavailable_exit_2(repo_root: Path, cfg: Path, tmp_path: Path) -> None:
    cfg.write_text(cfg.read_text(encoding="utf-8") + f"[sources.files]\ntype='files'\npath='{(tmp_path / 'missing').as_posix()}'\n", encoding="utf-8")
    proc = _cli(repo_root, "run", "--config", str(cfg), "--output", "json")
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["error"]["code"] == "source_unavailable"


def test_model_without_yes_non_tty_exit_1(repo_root: Path, cfg: Path) -> None:  # TAC-13, CNF-01
    proc = _cli(repo_root, "run", "--model", "--config", str(cfg), "--output", "json", env_extra={"OPENROUTER_API_KEY": "TEST_SECRET_0123456789abcdef"})
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["error"]["code"] == "confirmation_required"
    assert "TEST_SECRET" not in proc.stdout + proc.stderr


def test_reports_are_git_ignored(repo_root: Path) -> None:  # TAC-004-06
    proc = subprocess.run(["git", "check-ignore", "-q", "reports/map-qa/x/report.md"], cwd=repo_root)
    assert proc.returncode == 0
    keep = subprocess.run(["git", "check-ignore", "-q", "reports/map-qa/profile.md"], cwd=repo_root)
    assert keep.returncode == 1
