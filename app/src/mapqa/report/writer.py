"""Writes the run directory files: report.md, manual_queue.csv, run.json, evaluation.json (ADR-004 §3.4-3.5).

No timestamps are generated here: same inputs give byte-identical output (TAC-004-01).
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from mapqa.candidates.queue import COLUMNS, QueueItem
from mapqa.report.viewmodel import ReportViewModel

QUEUE_LIMIT = 200
TEMPLATE_DIR = Path(__file__).parent / "templates"

_METRIC_LABELS = {
    "cascade_accuracy": "trafność kaskady",
    "handoff_rate": "odsetek przekazania człowiekowi",
    "escalation_rate": "odsetek eskalacji do poziomu 2",
    "level1_accuracy": "trafność poziomu 1",
    "level2_escalated_accuracy": "trafność poziomu 2 na eskalowanych",
    "coverage": "pokrycie",
    "level1_standalone_accuracy": "poziom 1 bez kaskady: trafność",
    "level1_standalone_coverage": "poziom 1 bez kaskady: pokrycie",
    "level1_standalone_abstain_rate": "poziom 1 bez kaskady: abstencje",
}


def _pl(value: object, digits: int = 2) -> str:
    """Polish number format (decimal comma); '' for None/empty."""
    if value is None or value == "":
        return ""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.{digits}f}".replace(".", ",")


def _usd(value: object) -> str:
    return _pl(Decimal(str(value)), 4)


def _pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return f"brak danych ({numerator}/{denominator})"
    text = f"{round(100 * numerator / denominator, 1):.1f}".removesuffix(".0").replace(".", ",")
    return f"{text}% ({numerator}/{denominator})"


def _cell(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def _safe_url(value: object) -> str:
    text = str(value).strip()
    if not text.startswith("https://"):
        return ""
    return text.replace(" ", "%20").replace(")", "%29").replace("(", "%28").replace("|", "%7C")


def _metric_rows(metric_set: Any) -> list[tuple[str, Any]]:
    return [(_METRIC_LABELS.get(name, name), getattr(metric_set, name)) for name in type(metric_set).model_fields]


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(pl=_pl, usd=_usd, cell=_cell, safe_url=_safe_url)
    env.globals.update(pct=_pct, metric_rows=_metric_rows)
    return env


def render_report(vm: ReportViewModel, queue: Sequence[QueueItem]) -> str:
    rejected = sorted(Counter(r.reason for r in vm.rejected).items())
    candidates_total = sum(sum(by.values()) for by in vm.candidates_by_priority.values())
    return _environment().get_template("report.md.j2").render(
        vm=vm,
        queue=list(queue),
        queue_limit=QUEUE_LIMIT,
        rejected_by_reason=rejected,
        candidates_total=candidates_total,
    )


def render_queue_csv(queue: Sequence[QueueItem]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for item in queue:
        writer.writerow(item.as_row())
    return buf.getvalue().encode("utf-8-sig")


def _json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n").encode("utf-8")


def write_run(
    out_dir: Path,
    vm: ReportViewModel,
    queue: list[QueueItem],
    run_json: dict[str, Any],
    evaluation_json: dict[str, Any] | None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {
        "report.md": render_report(vm, queue).encode("utf-8"),
        "manual_queue.csv": render_queue_csv(queue),
        "run.json": _json_bytes(run_json),
    }
    if evaluation_json is not None:
        files["evaluation.json"] = _json_bytes(evaluation_json)
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    return {name: name for name in files}
