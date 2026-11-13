"""Append-only JSONL cost log, one line per attempt (ADR-003 §3.8)."""

from __future__ import annotations

from pathlib import Path

from mapqa.contract.models import CostLogEntry


class CostLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, entry: CostLogEntry) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")
