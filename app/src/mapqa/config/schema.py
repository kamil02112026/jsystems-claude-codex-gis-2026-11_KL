"""Configuration models (PRD F8.2, ADR-001 §3.1, ADR-000 §5 RunParams defaults)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from mapqa.contract.models import RunLimits

ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
DEFAULT_DATA_PATH = "course-materials/exercise-data/map-qa"
DEFAULT_THRESHOLD = 0.8


def _env_name(value: str) -> str:
    if not ENV_NAME.match(value):
        # never echo the value: it may be a pasted secret (PRD F8.8)
        raise ValueError("pole *_env musi zawierać nazwę zmiennej środowiskowej (np. DATABRICKS_TOKEN), nie wartość")
    return value


EnvName = Annotated[str, AfterValidator(_env_name)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilesSource(_Strict):
    type: Literal["files"]
    path: str = DEFAULT_DATA_PATH


class DatabricksSource(_Strict):
    type: Literal["databricks"]
    access: Literal["rest", "cli"]
    host_env: EnvName
    warehouse_id_env: EnvName
    token_env: EnvName | None = None
    schema_: str = Field(alias="schema", pattern=r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
    photos_dir: str
    query_timeout_s: int = 180
    poll_interval_s: int = 2
    wait_timeout_s: int = Field(default=30, ge=5, le=50)


SourceConfig = Annotated[FilesSource | DatabricksSource, Field(discriminator="type")]


class ModelsConfig(_Strict):
    level1: str = "typesafe/jev-1.14"
    level2: str = "openai/gpt-6-luna"
    level2_effort: str = "medium"
    comparison: str = "openai/gpt-6-luna-decisions"


class AppConfig(_Strict):
    default_source: str | None = None
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    model_reading: bool = False
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    limits: RunLimits = Field(default_factory=RunLimits)
    # thresholds[level][model][attribute]; missing entries fall back to DEFAULT_THRESHOLD (PRD F5.6)
    thresholds: dict[str, dict[str, dict[str, float]]] = Field(default_factory=dict)
    timeout_s: int = 60
    cache_dir: str = f"{DEFAULT_DATA_PATH}/data/cache"
    reports_dir: str = "reports/map-qa"
    labels_path: str = DEFAULT_DATA_PATH

    def threshold(self, *, level: int, model: str, attribute: str) -> float:
        return self.thresholds.get(f"level{level}", {}).get(model, {}).get(attribute, DEFAULT_THRESHOLD)

    def calibrated(self, *, level: int, model: str, attribute: str) -> bool:
        return attribute in self.thresholds.get(f"level{level}", {}).get(model, {})


__all__ = [
    "AppConfig",
    "DatabricksSource",
    "DEFAULT_THRESHOLD",
    "Decimal",
    "FilesSource",
    "ModelsConfig",
    "SourceConfig",
]
