"""Load configuration with source precedence: --source > MAPQA_SOURCE > default_source > files (PRD F8.1)."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from mapqa.config.schema import AppConfig, FilesSource, SourceConfig
from mapqa.contract.errors import ConfigError

ResolvedBy = Literal["flag", "env", "config", "builtin"]
BUILTIN = "files"


@dataclass(frozen=True)
class LoadedConfig:
    config: AppConfig
    source_name: str
    source: SourceConfig
    resolved_by: ResolvedBy
    config_path: Path | None


def _find_config(config_path: str | None, env: Mapping[str, str], cwd: Path) -> Path | None:
    explicit = config_path or env.get("MAPQA_CONFIG") or None
    if explicit:
        p = Path(explicit)
        p = p if p.is_absolute() else cwd / p
        if not p.is_file():
            raise ConfigError(f"Nie znaleziono pliku konfiguracyjnego: {explicit}", code="config_not_found")
        return p
    local = cwd / "mapqa.toml"
    return local if local.is_file() else None


def _read(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Niepoprawny plik TOML {path.name}: {exc}") from exc


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"])
        parts.append(f"{loc}: {e['msg']}")  # pydantic messages do not include input values here
    return "Niepoprawna konfiguracja: " + "; ".join(parts)


def load(
    *,
    source: str | None,
    config_path: str | None,
    env: Mapping[str, str],
    cwd: Path,
) -> LoadedConfig:
    path = _find_config(config_path, env, cwd)
    raw = _read(path)
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_validation_message(exc)) from None

    if BUILTIN not in config.sources:
        config.sources[BUILTIN] = FilesSource(type="files")

    models = config.models
    if "models" not in raw or "level1" not in raw.get("models", {}):
        if env.get("DECISION_MODEL"):
            models.level1 = env["DECISION_MODEL"]
    if "models" not in raw or "level2" not in raw.get("models", {}):
        if env.get("LLM_MODEL"):
            models.level2 = env["LLM_MODEL"]

    resolved_by: ResolvedBy
    if source:
        name, resolved_by = source, "flag"
    elif env.get("MAPQA_SOURCE"):
        name, resolved_by = env["MAPQA_SOURCE"], "env"
    elif config.default_source:
        name, resolved_by = config.default_source, "config"
    else:
        name, resolved_by = BUILTIN, "builtin"

    if name not in config.sources:
        raise ConfigError(
            f"Nieznane źródło danych: {name}",
            code="unknown_source",
            hint="Dostępne źródła: " + ", ".join(sorted(config.sources)),
        )
    return LoadedConfig(config=config, source_name=name, source=config.sources[name], resolved_by=resolved_by, config_path=path)
