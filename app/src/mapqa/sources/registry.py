"""Adapter registry: source `type` → adapter (ADR-001 §3.2)."""

from __future__ import annotations

from pathlib import Path

from mapqa.config.schema import DatabricksSource, FilesSource, SourceConfig
from mapqa.contract.errors import MapQAError
from mapqa.sources.base import SourceAdapter
from mapqa.sources.files import FilesAdapter


def build_adapter(name: str, source: SourceConfig, cwd: Path) -> SourceAdapter:
    if isinstance(source, FilesSource):
        return FilesAdapter(name, source, cwd=cwd)
    if isinstance(source, DatabricksSource):
        raise MapQAError(
            f"Źródło '{name}' typu databricks będzie dostępne od przyrostu P1",
            code="source_type_not_implemented",
            hint="Użyj --source files",
        )
    raise MapQAError(f"Nieobsługiwany typ źródła: {name}")  # pragma: no cover
