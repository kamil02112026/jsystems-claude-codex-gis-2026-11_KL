"""QUE-03: manual_queue.csv (ADR-004 §3.4, D-004-2)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from test_report_md import make_item, make_vm

from mapqa.candidates.queue import COLUMNS, QueueItem
from mapqa.report.writer import write_run


def _write(tmp_path: Path, items: list[QueueItem]) -> Path:
    written = write_run(tmp_path, make_vm(), items, {"run_id": "x"}, None)
    assert set(written.values()) >= {"report.md", "manual_queue.csv", "run.json"}
    return tmp_path / "manual_queue.csv"


def _rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def test_bom_header_and_rows(tmp_path: Path) -> None:
    path = _write(tmp_path, [make_item(1), make_item(2)])
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and not raw.startswith(b"\xef\xbb\xbf\xef\xbb\xbf")
    rows = _rows(path)
    assert tuple(rows[0]) == COLUMNS
    assert len(rows) == 3
    assert rows[1][COLUMNS.index("decyzja")] == "" and rows[1][-1] == ""


def test_polish_chars_and_commas_preserved(tmp_path: Path) -> None:
    item = make_item(1, photo_author="Kowalski, Jan Żółć", powod='Zażółć gęślą jaźń, "cytat"')
    path = _write(tmp_path, [item])
    rows = list(csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))
    assert rows[0]["photo_author"] == "Kowalski, Jan Żółć"
    assert rows[0]["powod"] == 'Zażółć gęślą jaźń, "cytat"'
    assert "wartość_z_terenu" in rows[0]


def test_empty_queue_header_only(tmp_path: Path) -> None:
    assert len(_rows(_write(tmp_path, []))) == 1


def test_deterministic_and_evaluation_json(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        write_run(d, make_vm(), [make_item(1)], {"run_id": "x"}, {"z": 1, "a": "ł"})
    assert (a / "manual_queue.csv").read_bytes() == (b / "manual_queue.csv").read_bytes()
    assert (a / "evaluation.json").read_bytes() == (b / "evaluation.json").read_bytes()
    assert json.loads((a / "evaluation.json").read_text(encoding="utf-8")) == {"z": 1, "a": "ł"}
