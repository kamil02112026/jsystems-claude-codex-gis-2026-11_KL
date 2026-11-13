"""T20: OpenRouter port on mocks derived ONLY from real captures (AGENTS.md; ADR-003 §3.3–§3.4; ISO-01, PAR-01, PAR-02, ERR-01, SEC-01, TAC-003-01).

Captures: app/tests/fixtures/captures/openrouter/*.json (recorded 2026-11-13, BYOK account).
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from mapqa.cascade.ports import PortTransportError
from mapqa.config.schema import AppConfig
from mapqa.contract.errors import AuthFailed
from mapqa.models.image_prep import PreparedImage
from mapqa.models.openrouter import OpenRouterPort, parse_chat, parse_decision, usage_cost
from mapqa.models.requests import CHAT_URL, DECISIONS_URL
from mapqa.questions.catalog import SPEED_LIMIT_VALUE as Q

CAPTURES = Path(__file__).resolve().parents[1] / "fixtures" / "captures" / "openrouter"
IMG = PreparedImage(data=b"\xff\xd8jpeg-bytes", mime="image/jpeg", source_sha256="c" * 64)
KEY = "sk-or-TEST_SECRET_0123456789abcdef"


def capture(name: str) -> dict:
    return json.loads((CAPTURES / f"{name}.json").read_text(encoding="utf-8"))


def body(name: str) -> dict:
    return json.loads(capture(name)["response"]["body"])


@pytest.fixture
def port() -> OpenRouterPort:
    return OpenRouterPort(api_key=KEY, config=AppConfig(), timeout_s=60)


# ---- parsing (from captured bodies, plus mutations of them) ----------------------------------
def test_par01_decision_valid_jev_capture() -> None:
    res = parse_decision(body("jev_state_image_url"), Q)
    assert res.parse_status == "ok" and res.answer == "30" and res.probability == pytest.approx(1.0)
    assert res.cost_usd == Decimal("0.000042462")  # BYOK: upstream_inference_cost, not usage.cost=0
    assert res.input_tokens == 1011


def test_par01_decision_valid_luna_capture() -> None:
    res = parse_decision(body("luna_decisions_state_image_url"), Q)
    assert res.parse_status == "ok" and res.answer == "30"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a.update(choice="35"),  # choice outside options
        lambda a: a["probabilities"].pop("30"),  # missing option
        lambda a: a["probabilities"].update({"999": 0.0}),  # extra option
        lambda a: a["probabilities"].update({"30": 0.5}),  # sum outside [0.99, 1.01]
        lambda a: a.update(type="noul"),
        lambda a: a.pop("probabilities"),
        lambda a: a.update(choice="40"),  # choice is not the argmax
    ],
)
def test_par01_decision_invalid_variants(mutate) -> None:
    b = copy.deepcopy(body("jev_state_image_url"))
    mutate(b["answers"]["speed_limit_value"])
    assert parse_decision(b, Q).parse_status == "invalid_response"


def test_par02_chat_valid_capture() -> None:
    res = parse_chat(body("luna_chat_medium"), Q)
    assert res.parse_status == "ok" and res.answer == "30" and res.probability == pytest.approx(0.99)
    assert res.cost_usd == Decimal("0.0000481")


@pytest.mark.parametrize(
    "content",
    ['{"answer":"35","probability":0.9}', '{"answer":"30","probability":1.5}', '{"answer":"30"}', "not json", '{"answer":"30","probability":0.9,"x":1}'],
)
def test_par02_chat_invalid_variants(content: str) -> None:
    b = copy.deepcopy(body("luna_chat_medium"))
    b["choices"][0]["message"]["content"] = content
    assert parse_chat(b, Q).parse_status == "invalid_response"


def test_usage_cost_prefers_upstream_for_byok_and_plain_cost_otherwise() -> None:
    assert usage_cost({"cost": 0, "is_byok": True, "cost_details": {"upstream_inference_cost": 4.2e-05}}) == Decimal("0.000042")
    assert usage_cost({"cost": 0.0012}) == Decimal("0.0012")
    assert usage_cost({}) is None


# ---- HTTP port (respx bodies = captured bodies) ------------------------------------------
@respx.mock
def test_level1_posts_decisions_with_only_image_and_question(port: OpenRouterPort) -> None:
    route = respx.post(DECISIONS_URL).mock(return_value=httpx.Response(200, text=capture("jev_state_image_url")["response"]["body"]))
    res = port.ask(level=1, model="typesafe/jev-1.14", reasoning_effort=None, image=IMG, question=Q)
    assert res.parse_status == "ok" and res.answer == "30"
    sent = json.loads(route.calls.last.request.content)
    assert set(sent) == {"model", "state", "questions"}  # ISO-01
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY}"
    assert "http-referer" not in route.calls.last.request.headers and "x-title" not in route.calls.last.request.headers
    assert IMG.source_sha256 not in route.calls.last.request.content.decode()


@respx.mock
def test_level2_posts_chat(port: OpenRouterPort) -> None:
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, text=capture("luna_chat_medium")["response"]["body"]))
    res = port.ask(level=2, model="openai/gpt-6-luna", reasoning_effort="medium", image=IMG, question=Q)
    assert res.parse_status == "ok" and res.probability == pytest.approx(0.99)
    assert json.loads(route.calls.last.request.content)["reasoning"] == {"effort": "medium"}


@respx.mock
def test_err01_http_400_capture_is_model_unavailable(port: OpenRouterPort) -> None:
    c = capture("jev_state_image_url-400-274x287")
    route = respx.post(DECISIONS_URL).mock(return_value=httpx.Response(c["response"]["status_code"], text=c["response"]["body"]))
    res = port.ask(level=1, model="typesafe/jev-1.14", reasoning_effort=None, image=IMG, question=Q)
    assert res.parse_status == "model_unavailable" and res.error_class == "400"
    assert route.call_count == 1  # no retries (D-003-3)


@respx.mock
def test_err02_timeout_raises_transport_error_once(port: OpenRouterPort) -> None:
    route = respx.post(DECISIONS_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(PortTransportError) as err:
        port.ask(level=1, model="typesafe/jev-1.14", reasoning_effort=None, image=IMG, question=Q)
    assert err.value.error_class == "timeout" and route.call_count == 1


def test_sec01_missing_key_is_auth_failed(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(AuthFailed):
        OpenRouterPort.from_env(AppConfig())


def test_sec01_key_never_in_repr(port: OpenRouterPort) -> None:
    assert KEY not in repr(port) and KEY not in str(port.__dict__.get("_safe", ""))


def test_tac07_every_capture_has_metadata_and_no_secret() -> None:
    files = sorted(CAPTURES.glob("*.json"))
    assert files
    for f in files:
        c = json.loads(f.read_text(encoding="utf-8"))
        assert {"captured_at", "model", "api"} <= set(c["meta"]), f.name
        text = f.read_text(encoding="utf-8")
        assert "sk-or-" not in text and "data:image" not in text, f.name
