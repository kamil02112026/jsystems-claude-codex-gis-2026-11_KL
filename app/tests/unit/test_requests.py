"""Request bodies (ADR-003 §3.3; ISO-01 part; PRD F5.1)."""

from __future__ import annotations

import json

import pytest

from mapqa.models.image_prep import PreparedImage
from mapqa.models.requests import chat_body, decisions_body
from mapqa.questions.catalog import SPEED_LIMIT_VALUE

IMG = PreparedImage(data=b"\xff\xd8fakejpeg", mime="image/jpeg", source_sha256="ab" * 32)


@pytest.mark.parametrize("fmt", ["state_image_url", "assets"])
def test_decisions_body_has_only_image_and_question(fmt: str) -> None:
    body = decisions_body(model="typesafe/jev-1.14", image=IMG, question=SPEED_LIMIT_VALUE, image_format=fmt)
    assert set(body) <= {"model", "state", "questions", "assets"}
    q = body["questions"]["speed_limit_value"]
    assert q["type"] == "choice"
    assert q["instructions"] == SPEED_LIMIT_VALUE.text
    assert list(q["criteria"]) == list(SPEED_LIMIT_VALUE.options)
    text = json.dumps(body)
    for forbidden in ("photo_id", "session_id", "user", "trace", "provider", IMG.source_sha256, ".jpg"):
        assert forbidden not in text


def test_chat_body_schema_and_no_context() -> None:
    body = chat_body(model="openai/gpt-6-luna", effort="medium", image=IMG, question=SPEED_LIMIT_VALUE, max_tokens=2048)
    assert body["reasoning"] == {"effort": "medium"}
    assert body["max_tokens"] == 2048
    assert len(body["messages"]) == 1 and body["messages"][0]["role"] == "user"
    parts = body["messages"][0]["content"]
    assert [p["type"] for p in parts] == ["text", "image_url"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    schema = body["response_format"]["json_schema"]
    assert body["response_format"]["type"] == "json_schema" and schema["strict"] is True
    props = schema["schema"]["properties"]
    assert props["answer"]["enum"] == list(SPEED_LIMIT_VALUE.options)
    assert schema["schema"]["additionalProperties"] is False
    assert IMG.source_sha256 not in json.dumps(body)
