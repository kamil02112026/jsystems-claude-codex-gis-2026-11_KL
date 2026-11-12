"""Model port: the only seam between the cascade and real HTTP clients (ADR-003 §5)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from mapqa.models.image_prep import PreparedImage
from mapqa.questions.catalog import Question

ParseStatus = Literal["ok", "invalid_response", "model_unavailable"]


@dataclass(frozen=True)
class PortResult:
    answer: str | None
    probability: float | None
    parse_status: ParseStatus
    cost_usd: Decimal | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_class: str | None = None
    response_body: str | None = None


class ModelPort(Protocol):
    def ask(
        self,
        *,
        level: int,
        model: str,
        reasoning_effort: str | None,
        image: PreparedImage,
        question: Question,
    ) -> PortResult: ...
