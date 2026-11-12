"""T19: capture script safety (ADR-003 D-003-6; AGENTS.md captures before mocks). No network in tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "capture_openrouter.py"


def _load():
    spec = importlib.util.spec_from_file_location("capture_openrouter", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


def test_plan_respects_hard_limits() -> None:
    mod = _load()
    plan = mod.build_plan()
    assert 1 <= len(plan) <= mod.MAX_REQUESTS == 6
    assert {p.model for p in plan} == {"typesafe/jev-1.14", "openai/gpt-6-luna-decisions", "openai/gpt-6-luna"}
    assert {p.image_format for p in plan if p.model == "typesafe/jev-1.14"} == {"state_image_url", "assets"}
    assert str(mod.MAX_USD) == "0.20"


@respx.mock(assert_all_mocked=True)
def test_dry_run_sends_nothing_and_prints_plan(capsys, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    mod = _load()
    assert mod.main([]) == 0
    out = capsys.readouterr().out
    assert "TRYB PRÓBNY" in out and "0.20" in out
    assert respx.calls.call_count == 0


def test_execute_without_key_fails_before_network(capsys, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    mod = _load()
    with respx.mock(assert_all_mocked=True) as router:
        assert mod.main(["--execute"]) == 2
        assert router.calls.call_count == 0


def test_capture_redacts_secret(tmp_path: Path) -> None:
    mod = _load()
    secret = "sk-or-TEST_SECRET_0123456789abcdef"
    rec = mod.capture_record(
        step=mod.build_plan()[0],
        url="https://openrouter.ai/api/alpha/decisions",
        request_body={"model": "m", "state": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "A" * 500}}]},
        response=httpx.Response(200, json={"ok": True}, headers={"x-request-id": "r1", "authorization": f"Bearer {secret}"}),
        secret=secret,
    )
    text = json.dumps(rec)
    assert secret not in text
    assert "A" * 100 not in text  # image bytes are not stored in the capture metadata
    assert rec["response"]["status_code"] == 200
