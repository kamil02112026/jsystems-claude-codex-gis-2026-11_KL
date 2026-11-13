"""Request bodies for OpenRouter (ADR-003 §3.3). Only the image and the neutral question are sent (PRD F5.1)."""

from __future__ import annotations

import base64
from typing import Any, Literal

from mapqa.models.image_prep import PreparedImage
from mapqa.questions.catalog import Question

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
ImageFormat = Literal["state_image_url", "assets"]

CHAT_INSTRUCTION = (
    "Odpowiedz wyłącznie w formacie JSON zgodnym ze schematem. "
    "`probability` to Twoje prawdopodobieństwo, że odpowiedź jest poprawna."
)


def _data_url(image: PreparedImage) -> str:
    if image.mime not in ("image/jpeg", "image/png"):
        raise ValueError(f"unsupported image MIME type: {image.mime}")
    return f"data:{image.mime};base64," + base64.b64encode(image.data).decode("ascii")


def decisions_body(*, model: str, image: PreparedImage, question: Question, image_format: ImageFormat) -> dict[str, Any]:
    """Level 1 / comparison: Decisions API `choice` question; `state` carries only the image.

    Two image encodings exist in the docs (ADR-003 §2); the capture (D-003-6) decides which one the client keeps.
    """
    questions = {
        question.question_id: {
            "type": "choice",
            "instructions": question.text,
            "criteria": {opt: question.criteria[opt] for opt in question.options},
        }
    }
    if image_format == "state_image_url":
        return {"model": model, "state": [{"type": "image_url", "image_url": {"url": _data_url(image)}}], "questions": questions}
    formats = {"image/jpeg": "jpeg", "image/png": "png"}
    if image.mime not in formats:  # never mislabel bytes (review finding: hard-coded MIME)
        raise ValueError(f"unsupported image MIME type: {image.mime}")
    fmt = formats[image.mime]
    return {
        "model": model,
        "assets": {"image": {"type": "image", "format": fmt, "data_base64": base64.b64encode(image.data).decode("ascii")}},
        "state": [{"type": "asset", "asset": "image"}],
        "questions": questions,
    }


def chat_body(*, model: str, effort: str, image: PreparedImage, question: Question, max_tokens: int = 2048) -> dict[str, Any]:
    """Level 2: Chat Completions with a strict JSON schema; no system prompt, no history, no level-1 answer."""
    options = list(question.options)
    text = f"{question.text}\nDozwolone odpowiedzi: {', '.join(options)}.\n{CHAT_INSTRUCTION}"
    return {
        "model": model,
        "reasoning": {"effort": effort},
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": _data_url(image)}},
                ],
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": question.question_id,
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string", "enum": options},
                        "probability": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["answer", "probability"],
                    "additionalProperties": False,
                },
            },
        },
    }
