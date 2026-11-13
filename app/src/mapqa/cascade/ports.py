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


class PortTransportError(Exception):
    """Raised by a port for HTTP ≠ 200, timeouts and connection errors when it does not return a
    `model_unavailable` PortResult itself. The cascade maps it to `model_unavailable`, opens the breaker
    and does NOT escalate (ADR-003 §3.4, §3.5). Any other exception is treated as `invalid_response` (F5.7).
    """

    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class


class ModelPort(Protocol):
    """Contract for T20 clients: transport problems → `model_unavailable` result or PortTransportError."""

    def ask(
        self,
        *,
        level: int,
        model: str,
        reasoning_effort: str | None,
        image: PreparedImage,
        question: Question,
    ) -> PortResult: ...
