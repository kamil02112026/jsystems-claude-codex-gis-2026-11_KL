"""T37 → M4: `mapqa run --dataset photos` without the model, real process on course data, offline.

PRD F1, F2.3, F3.3–F3.5, §6 (≤ 2 min), kryt. 1–5, 20; ADR-002 MAT-07, MAT-08; ADR-004 E2E-01.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pytest

from test_mvp_e2e import _cli  # shared clean-environment runner (no PYTHONUTF8/PYTHONIOENCODING, closed stdin)

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def photos_run(repo_root: Path, tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path, float]:
    tmp = tmp_path_factory.mktemp("photos")
    config = tmp / "mapqa.toml"
    config.write_text(
        f"reports_dir = '{(tmp / 'reports').as_posix()}'\ncache_dir = '{(tmp / 'cache').as_posix()}'\n", encoding="utf-8"
    )
    t0 = time.monotonic()
    proc = _cli(repo_root, "run", "--dataset", "photos", "--attributes", "speed_limit", "--no-model", "--config", str(config), "--output", "json")
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    return doc, Path(doc["result"]["output_dir"]), elapsed


def test_photos_run_is_offline_and_within_two_minutes(photos_run) -> None:  # PRD §6, TAC-13
    doc, _, elapsed = photos_run
    result = doc["result"]
    assert result["model_reading"] is False and result["queries_used"] == 0 and result["cost_usd"] == "0"
    assert result["funnel"]["total"] == 561 and result["funnel"]["skipped_no_model"] == 561
    assert elapsed <= 120, f"run took {elapsed:.0f} s"


def test_profile_counts_completeness_and_agreement(photos_run) -> None:  # F2.3, F3.5, MAT-07
    _, out, _ = photos_run
    report = (out / "report.md").read_text(encoding="utf-8")
    for table, total in (("osm_roads", 99768), ("overture_segments", 85405), ("photos", 561), ("photo_road_links", 561), ("traffic_signs", 1730)):
        assert f"| {table} | {total} |" in report
    for attribute in ("maxspeed", "surface", "lit"):
        assert f"- {attribute}: " in report and "/561)" in report
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    agreement = run["link_agreement"]
    assert agreement["denominator"] >= 550
    assert agreement["numerator"] / agreement["denominator"] >= 0.95  # TAC-002-02
    assert "Zgodność własnego dopasowania" in report


def test_provided_flags_are_not_dropped(photos_run, data_dir: Path) -> None:  # MAT-08, kryt. 5
    _, out, _ = photos_run
    report = (out / "report.md").read_text(encoding="utf-8")
    with (data_dir / "photo_road_links.csv").open(encoding="utf-8", newline="") as fh:
        provided = {f for row in csv.DictReader(fh) for f in (x.strip() for x in (row["candidate_flags"] or "").split(";")) if f}
    for flag in provided:
        assert f"- `{flag}`: " in report, flag
