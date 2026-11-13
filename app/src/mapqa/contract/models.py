"""Domain models (ADR-000 §5) and the JSON envelope (ADR-000 §6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SpeedSource = Literal["explicit", "implicit"]
ValueStatus = Literal["ok", "missing", "not_comparable"]
AttemptStatus = Literal["confident", "below_threshold", "invalid_response", "model_unavailable", "budget_exceeded"]
FinalStatus = Literal["resolved", "abstain", "model_unavailable", "budget_exceeded", "image_out_of_bounds", "skipped_no_model"]
RejectReason = Literal["missing_file", "hash_mismatch", "missing_geometry", "outside_bbox", "invalid_value"]
Confirmation = Literal["interactive", "flag_yes", "cache_only", "declined"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorInfo(_Model):
    code: str
    message: str
    hint: str | None = None


class Envelope(_Model):
    """Single JSON document printed on stdout with --output json (TAC-02)."""

    ok: bool
    command: str
    exit_code: int = Field(ge=0, le=4)
    result: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Envelope:
        if self.ok:
            if self.result is None or self.error is not None:
                raise ValueError("ok=true wymaga result i braku error")
            if self.exit_code not in (0, 3):
                raise ValueError("ok=true tylko z kodem 0 albo 3")
        else:
            if self.error is None or self.exit_code == 0:
                raise ValueError("ok=false wymaga error i kodu ≠ 0")
        return self


class RunLimits(_Model):
    max_queries: int = Field(default=100, ge=0)
    max_images: int = Field(default=25, ge=0)
    max_usd: Decimal = Field(default=Decimal("1.00"), ge=0)
    reserve_usd: dict[str, Decimal] = Field(
        default_factory=lambda: {"level1": Decimal("0.02"), "level2": Decimal("0.04"), "compare": Decimal("0.02")}
    )


class RejectedRecord(_Model):
    dataset: str
    record_id: str
    reason: RejectReason
    detail: str = ""


class SourceDescriptor(_Model):
    name: str
    type: str
    access: Literal["local", "rest", "cli"]
    tables_or_paths: list[str] = Field(default_factory=list)
    read_started_at: str | None = None
    read_finished_at: str | None = None
    input_hashes: dict[str, dict[str, str | None]] = Field(default_factory=dict)


class PhotoRoadLink(_Model):
    photo_id: str
    osm_way_id: int | None = None
    overture_id: str | None = None
    distance_m: float | None = None
    heading_diff_deg: float | None = Field(default=None, ge=0, le=90)
    candidate_count: int = 0
    flags: list[str] = Field(default_factory=list)
    link_source: Literal["own", "provided"]


class AttributeValue(_Model):
    raw: Any = None
    normalized: float | str | None = None
    speed_source: SpeedSource | None = None
    status: ValueStatus
    note: str = ""
    flags: list[str] = Field(default_factory=list)


class ModelAttempt(_Model):
    level: Literal[1, 2]
    model: str
    reasoning_effort: str | None = None
    answer: str | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    status: AttemptStatus
    cache_hit: bool = False
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    error_class: str | None = None


class CascadeResult(_Model):
    photo_sha256: str
    question_id: str
    attempts: list[ModelAttempt] = Field(default_factory=list)
    final_status: FinalStatus
    resolved_by: Literal["1", "2", "human"] | None = None
    final_answer: str | None = None
    escalation_reason: str | None = None


class Candidate(_Model):
    attribute: str
    rule: Literal["photo_vs_osm", "sources_disagree_photo_supports", "osm_missing_photo_confident", "sources_only"]
    priority: Literal["wysoki", "średni", "niski"]
    reason_pl: str
    photo_id: str
    osm_way_id: int | None = None


class CostLogEntry(_Model):
    ts: str
    run_id: str
    level: int
    model: str
    reasoning_effort: str | None = None
    question_id: str
    image_sha256: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
    cost_estimated: bool = False
    cache: Literal["hit", "miss"]
    status: str
