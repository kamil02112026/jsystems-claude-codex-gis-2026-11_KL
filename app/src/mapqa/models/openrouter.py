"""OpenRouter model port: Decisions API (level 1) and Chat Completions (level 2) (ADR-003 §3.3–§3.4, D-003-3).

Shapes verified against real captures (2026-11-13, app/tests/fixtures/captures/openrouter/):
- Decisions answer: answers.<qid> = {type: "choice", choice, probabilities{option: p}, confidence}.
- BYOK accounts report usage.cost = 0; the real cost is usage.cost_details.upstream_inference_cost.
- Jev rejects a 274×287 image with HTTP 400 "Invalid image dimensions" (min 280 px per side in practice).
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mapqa.cascade.ports import PortResult, PortTransportError
from mapqa.config.schema import AppConfig
from mapqa.contract.errors import AuthFailed
from mapqa.models.image_prep import PreparedImage
from mapqa.models.requests import CHAT_URL, DECISIONS_URL, chat_body, decisions_body
from mapqa.questions.catalog import Question

_INVALID = PortResult(answer=None, probability=None, parse_status="invalid_response")


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def usage_cost(usage: dict[str, Any]) -> Decimal | None:
    """Cost in USD. BYOK keys report cost 0 and the real price in cost_details.upstream_inference_cost."""
    if not usage:
        return None
    details = usage.get("cost_details") or {}
    upstream = _dec(details.get("upstream_inference_cost"))
    if usage.get("is_byok") and upstream is not None:
        return upstream
    return _dec(usage.get("cost"))


def _with_usage(result: PortResult, usage: dict[str, Any], body_text: str | None, *, chat: bool) -> PortResult:
    return PortResult(
        answer=result.answer,
        probability=result.probability,
        parse_status=result.parse_status,
        cost_usd=usage_cost(usage),
        input_tokens=usage.get("prompt_tokens" if chat else "input_tokens"),
        output_tokens=usage.get("completion_tokens" if chat else "output_tokens"),
        response_body=body_text,
    )


def parse_decision(body: dict[str, Any], question: Question, body_text: str | None = None) -> PortResult:
    """Level-1 validation (ADR-003 §3.4): all options, p in [0,1], sum in [0.99, 1.01], choice = argmax."""
    usage = body.get("usage") or {}
    answer = (body.get("answers") or {}).get(question.question_id)
    ok = isinstance(answer, dict) and answer.get("type") == "choice"
    probs = answer.get("probabilities") if ok else None
    choice = answer.get("choice") if ok else None
    if not ok or not isinstance(probs, dict) or choice not in question.options or set(probs) != set(question.options):
        return _with_usage(_INVALID, usage, body_text, chat=False)
    try:
        values = {k: float(v) for k, v in probs.items()}
    except (TypeError, ValueError):
        return _with_usage(_INVALID, usage, body_text, chat=False)
    if any(not 0 <= v <= 1 for v in values.values()) or not 0.99 <= sum(values.values()) <= 1.01:
        return _with_usage(_INVALID, usage, body_text, chat=False)
    top = max(values.values())
    if values[choice] < top:  # choice must be the (possibly tied) argmax
        return _with_usage(_INVALID, usage, body_text, chat=False)
    return _with_usage(PortResult(answer=choice, probability=top, parse_status="ok"), usage, body_text, chat=False)


def parse_chat(body: dict[str, Any], question: Question, body_text: str | None = None) -> PortResult:
    """Level-2 validation: strict JSON {answer ∈ options, probability ∈ [0,1]}, no extra fields."""
    usage = body.get("usage") or {}
    try:
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError):
        return _with_usage(_INVALID, usage, body_text, chat=True)
    if not isinstance(data, dict) or set(data) != {"answer", "probability"}:
        return _with_usage(_INVALID, usage, body_text, chat=True)
    answer, probability = data["answer"], data["probability"]
    if answer not in question.options or isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        return _with_usage(_INVALID, usage, body_text, chat=True)
    return _with_usage(PortResult(answer=answer, probability=float(probability), parse_status="ok"), usage, body_text, chat=True)


class OpenRouterPort:
    """Implements cascade.ports.ModelPort. One httpx client per run, timeout from config, no retries."""

    def __init__(self, *, api_key: str, config: AppConfig, timeout_s: int | None = None) -> None:
        self._client = httpx.Client(
            timeout=timeout_s or config.timeout_s,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=httpx.HTTPTransport(retries=0),
        )

    def __repr__(self) -> str:  # never expose the key
        return "OpenRouterPort(key=***)"

    @classmethod
    def from_env(cls, config: AppConfig) -> OpenRouterPort:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise AuthFailed("Brak zmiennej środowiskowej OPENROUTER_API_KEY", hint="Ustaw klucz w PowerShell albo uruchom bez --model.")
        return cls(api_key=key, config=config)

    def close(self) -> None:
        self._client.close()

    def ask(self, *, level: int, model: str, reasoning_effort: str | None, image: PreparedImage, question: Question) -> PortResult:
        if level == 1:
            url, payload = DECISIONS_URL, decisions_body(model=model, image=image, question=question, image_format="state_image_url")
        else:
            url, payload = CHAT_URL, chat_body(model=model, effort=reasoning_effort or "medium", image=image, question=question)
        started = time.monotonic()
        try:
            response = self._client.post(url, json=payload)
        except httpx.TimeoutException:
            raise PortTransportError("timeout") from None
        except httpx.TransportError:
            raise PortTransportError("connect_error") from None
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            return PortResult(answer=None, probability=None, parse_status="model_unavailable", error_class=str(response.status_code), latency_ms=latency)
        try:
            data = response.json()
        except ValueError:
            return PortResult(answer=None, probability=None, parse_status="invalid_response", latency_ms=latency, response_body=response.text)
        parsed = parse_decision(data, question, response.text) if level == 1 else parse_chat(data, question, response.text)
        return PortResult(**{**parsed.__dict__, "latency_ms": latency})
