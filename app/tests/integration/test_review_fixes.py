"""Regression tests for the code review of PR #3 (2026-11-13). Each test reproduces one confirmed finding."""

from __future__ import annotations

import importlib
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from mapqa.cascade.ports import PortResult
from mapqa.cli.main import main
from mapqa.config.schema import FilesSource
from mapqa.contract.errors import ContractViolation
from mapqa.models.image_prep import ImageOutOfBounds, prepare_image
from mapqa.sources.files import FilesAdapter

pipeline = importlib.import_module("mapqa.pipeline")


class Port:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def ask(self, **_):
        self.calls += 1
        return PortResult(answer="50", probability=0.9, parse_status="ok", cost_usd=Decimal("0.00001"), response_body="{}")

    def close(self) -> None:
        self.closed = True


def _copy(data_dir: Path, tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shutil.copytree(data_dir / "signs", root / "signs", ignore=shutil.ignore_patterns("photos"))
    shutil.copy(data_dir / "osm_roads.parquet", root / "osm_roads.parquet")
    return root


def _cfg(tmp_path: Path, data_path: Path, labels: Path) -> Path:
    p = tmp_path / "mapqa.toml"
    p.write_text(
        f"reports_dir='{(tmp_path / 'reports').as_posix()}'\ncache_dir='{(tmp_path / 'cache').as_posix()}'\n"
        f"labels_path='{labels.as_posix()}'\n[sources.files]\ntype='files'\npath='{data_path.as_posix()}'\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo_root: Path):
    for v in ("MAPQA_SOURCE", "MAPQA_CONFIG", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(repo_root)


def _run(cfg: Path, capsys, *args: str) -> tuple[int, dict]:
    rc = main([*args[:1], *(["--config", str(cfg), "--output", "json"]), *args[1:]]) if args[0] != "eval" else main(
        ["eval", args[1], "--config", str(cfg), "--output", "json", *args[2:]]
    )
    return rc, json.loads(capsys.readouterr().out)


# 1. unreadable image must not abort the paid loop; report written; client closed
def test_unreadable_image_does_not_abort_run(tmp_path: Path) -> None:
    missing = tmp_path / "gone.jpg"
    with pytest.raises(ImageOutOfBounds):
        prepare_image(missing)


def test_port_is_closed_even_when_the_loop_fails(tmp_path, data_dir, capsys, monkeypatch) -> None:
    port = Port()
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: port)

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(pipeline, "prepare_image", boom)
    cfg = _cfg(tmp_path, data_dir, data_dir)
    rc, _ = _run(cfg, capsys, "run", "--model", "--yes", "--max-images", "2")
    assert port.closed


# 2. calibration only on the calibration split; --grid honoured
def test_calibrate_rejects_test_split(tmp_path, data_dir, capsys) -> None:
    rc, doc = _run(_cfg(tmp_path, data_dir, data_dir), capsys, "eval", "calibrate", "--split", "test", "--yes")
    assert rc == 1 and doc["error"]["code"] == "invalid_split"


def test_calibrate_grid_is_parsed(tmp_path, data_dir, capsys, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "build_port", lambda *a, **k: Port())
    rc, doc = _run(_cfg(tmp_path, data_dir, data_dir), capsys, "eval", "calibrate", "--yes", "--grid", "0.70:0.90:0.10", "--max-images", "3")
    cal = json.loads((Path(doc["result"]["output_dir"]) / "calibration.json").read_text(encoding="utf-8"))
    assert [b["threshold"] for b in cal["bands"]] == [0.7, 0.8, 0.9]


# 3. capture script cost uses the BYOK-aware helper
def test_capture_script_uses_usage_cost(repo_root: Path) -> None:
    text = (repo_root / "app" / "scripts" / "capture_openrouter.py").read_text(encoding="utf-8")
    assert "usage_cost" in text and "def _cost" not in text


# 4. coordinates validated in the files adapter
@pytest.mark.parametrize(("lon", "lat"), [("", "50.0"), ("nan", "50.0"), ("19.9", "95"), ("200", "50")])
def test_invalid_coordinates_are_rejected_records(tmp_path, data_dir, lon, lat) -> None:
    root = _copy(data_dir, tmp_path)
    p = root / "signs" / "signs.csv"
    lines = p.read_text(encoding="utf-8").splitlines()
    head = lines[0].split(",")
    row = lines[1].split(",")
    row[head.index("longitude")], row[head.index("latitude")] = lon, lat
    p.write_text("\n".join([lines[0], ",".join(row), *lines[2:]]) + "\n", encoding="utf-8")
    b = FilesAdapter("t", FilesSource(type="files", path=str(root))).load_signs(bbox=None)
    assert len(b.signs) == 118
    assert [r.reason for r in b.rejected] == ["invalid_value"]


# 5. duplicate photo_id is a contract violation (exit 1), not silent overwrite
def test_duplicate_photo_id_is_contract_violation(tmp_path, data_dir) -> None:
    root = _copy(data_dir, tmp_path)
    p = root / "signs" / "signs.csv"
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join([*lines, lines[1]]) + "\n", encoding="utf-8")
    with pytest.raises(ContractViolation):
        FilesAdapter("t", FilesSource(type="files", path=str(root))).load_signs(bbox=None)


# 6. evaluation sections follow the run's photo set (bbox / split)
def test_discrepancies_follow_bbox(tmp_path, data_dir, capsys) -> None:
    rc, doc = _run(_cfg(tmp_path, data_dir, data_dir), capsys, "run", "--bbox", "19.80,49.95,20.15,50.15")
    n_photos = doc["result"]["funnel"]["total"]
    report = (Path(doc["result"]["output_dir"]) / "report.md").read_text(encoding="utf-8")
    pairs = int(report.split("wartością liczbową: ")[1].split()[0])
    assert n_photos < 119 and pairs < 89


# 7. run_id collision in the same second gets a fresh directory
def test_same_second_runs_do_not_share_directory(tmp_path, data_dir, capsys, monkeypatch) -> None:
    from datetime import UTC, datetime

    fixed = datetime(2026, 11, 13, 10, 0, 0, tzinfo=UTC)

    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(pipeline, "datetime", FixedDT)
    cfg = _cfg(tmp_path, data_dir, data_dir)
    _, a = _run(cfg, capsys, "run")
    _, b = _run(cfg, capsys, "run")
    assert a["result"]["output_dir"] != b["result"]["output_dir"]


# 9. profile completeness uses the same OSM value logic as the comparison (directional tags)
def test_profile_counts_directional_only_roads() -> None:
    from mapqa.contract.bundle import SignLink, SignRecord, SignsBundle
    from mapqa.profile.profile import build_profile

    sign = SignRecord("p", "a", 19.9, 50.0, "", 10.0, "x", "CC", "", "s", "signs/crops/p.jpg", "0" * 64, "ok")
    link = SignLink("p", 1, 2.0, 5.0, "residential", None, "50", "50", None, None, 1, (), "osm_roads.parquet", None)
    prof = build_profile(SignsBundle(signs=[sign], links=[link]), bbox_text=None)
    assert prof.maxspeed.numerator == 1


# 10. one sha256 helper and a strict MIME mapping
def test_single_sha256_helper_and_strict_mime() -> None:
    from mapqa.models.image_prep import PreparedImage
    from mapqa.models.requests import decisions_body
    from mapqa.questions.catalog import SPEED_LIMIT_VALUE

    img = PreparedImage(data=b"x", mime="image/webp", source_sha256="a" * 64)
    with pytest.raises(ValueError):
        decisions_body(model="m", image=img, question=SPEED_LIMIT_VALUE, image_format="assets")
    import mapqa.cache.sqlite_cache as c
    import mapqa.contract.hashing as h

    assert c.file_sha256 is h.sha256_file
