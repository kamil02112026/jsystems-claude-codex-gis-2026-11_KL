"""Record real OpenRouter responses before writing clients and mocks (ADR-003 D-003-6; AGENTS.md).

Default = DRY RUN: prints the request plan and the hard cost cap, sends nothing.
Sending requires `--execute` AND the owner's explicit consent (plan gate G2). Hard limits: 6 requests, 0.20 USD.
The API key is read only from OPENROUTER_API_KEY and never printed or stored.

    uv run --project app python app/scripts/capture_openrouter.py            # dry run
    uv run --project app python app/scripts/capture_openrouter.py --execute  # after consent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from mapqa.models.image_prep import prepare_image
from mapqa.models.openrouter import usage_cost
from mapqa.models.requests import CHAT_URL, DECISIONS_URL, chat_body, decisions_body
from mapqa.questions.catalog import SPEED_LIMIT_VALUE

REPO = Path(__file__).resolve().parents[2]
CROP = REPO / "course-materials" / "exercise-data" / "map-qa" / "signs" / "crops"
OUT = REPO / "app" / "tests" / "fixtures" / "captures" / "openrouter"
MAX_REQUESTS = 6
MAX_USD = Decimal("0.20")
RESERVE_USD = Decimal("0.04")  # highest per-request reserve (level 2, ADR-003 §3.6)
TIMEOUT_S = 60


@dataclass(frozen=True)
class Step:
    name: str
    api: str  # "decisions" | "chat"
    model: str
    image_format: str  # decisions: state_image_url | assets; chat: n/a


def build_plan(only: list[str] | None = None) -> list[Step]:
    steps = [
        Step("jev_state_image_url", "decisions", "typesafe/jev-1.14", "state_image_url"),
        Step("jev_assets", "decisions", "typesafe/jev-1.14", "assets"),
        Step("luna_decisions_state_image_url", "decisions", "openai/gpt-6-luna-decisions", "state_image_url"),
        Step("luna_decisions_assets", "decisions", "openai/gpt-6-luna-decisions", "assets"),
        Step("luna_chat_medium", "chat", "openai/gpt-6-luna", "-"),
    ]
    return [s for s in steps if s.name in only] if only else steps


def _crop() -> Path:
    # first crop in sorted order (deterministic; CC BY-SA 4.0, no personal data) — not hand-picked
    return sorted(CROP.glob("*.jpg"))[0]


def capture_record(*, step: Step, url: str, request_body: dict[str, Any], response: httpx.Response, secret: str | None) -> dict[str, Any]:
    def scrub(value: str) -> str:
        return value.replace(secret, "***") if secret else value

    headers = {k: scrub(v) for k, v in response.headers.items() if k.lower() not in ("authorization", "set-cookie")}
    body_text = scrub(response.text)
    redacted_request = json.loads(json.dumps(request_body))
    for part in redacted_request.get("state", []):
        if isinstance(part, dict) and "image_url" in part:
            part["image_url"]["url"] = "<data-url redacted>"
    for asset in redacted_request.get("assets", {}).values():
        asset["data_base64"] = "<redacted>"
    for msg in redacted_request.get("messages", []):
        for part in msg.get("content", []):
            if part.get("type") == "image_url":
                part["image_url"]["url"] = "<data-url redacted>"
    return {
        "meta": {
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "step": step.name,
            "api": step.api,
            "model": step.model,
            "image_format": step.image_format,
            "question_id": SPEED_LIMIT_VALUE.question_id,
            "prompt_version": SPEED_LIMIT_VALUE.prompt_version,
            "httpx": httpx.__version__,
        },
        "request": {"url": url, "body": redacted_request},
        "response": {"status_code": response.status_code, "headers": headers, "body": body_text},
    }


def _response_cost(body: str) -> Decimal | None:
    """BYOK-aware cost via the client's helper (review finding: a copied helper ignored cost_details)."""
    try:
        return usage_cost(json.loads(body).get("usage") or {})
    except (ValueError, AttributeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="wyślij prawdziwe zapytania (tylko za zgodą właściciela)")
    parser.add_argument("--only", help="lista kroków po przecinku (np. jev_state_image_url,luna_chat_medium)")
    parser.add_argument("--continue-on-error", action="store_true", help="nie przerywaj po odpowiedzi ≠ 200 (nadal bez ponowień)")
    args = parser.parse_args(argv)
    plan = build_plan(args.only.split(",") if args.only else None)
    crop = _crop()
    image = prepare_image(crop)
    print(f"Plan nagrania: {len(plan)} zapytań (limit {MAX_REQUESTS}), maks. koszt {MAX_USD} USD, timeout {TIMEOUT_S} s, bez ponowień.")
    print(f"Obraz: wycinek {crop.name} (sha256 {hashlib.sha256(crop.read_bytes()).hexdigest()[:12]}…), przygotowany {len(image.data)} B JPEG.")
    for i, step in enumerate(plan, 1):
        print(f"  {i}. {step.api:9} {step.model:32} {step.image_format}")
    if not args.execute:
        print("TRYB PRÓBNY: nic nie wysłano. Uruchom z --execute dopiero po zgodzie właściciela (bramka G2).")
        return 0

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("Brak zmiennej OPENROUTER_API_KEY — nic nie wysłano.", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    spent = Decimal("0")
    with httpx.Client(timeout=TIMEOUT_S, headers={"Authorization": f"Bearer {key}"}, transport=httpx.HTTPTransport(retries=0)) as client:
        for i, step in enumerate(plan[:MAX_REQUESTS], 1):
            if spent >= MAX_USD:
                print(f"Stop: osiągnięto limit kosztu {MAX_USD} USD.")
                break
            if step.api == "decisions":
                body = decisions_body(model=step.model, image=image, question=SPEED_LIMIT_VALUE, image_format=step.image_format)  # type: ignore[arg-type]
                url = DECISIONS_URL
            else:
                body = chat_body(model=step.model, effort="medium", image=image, question=SPEED_LIMIT_VALUE)
                url = CHAT_URL
            try:
                response = client.post(url, json=body)
            except httpx.HTTPError as exc:
                print(f"  {i}. {step.name}: błąd transportu {type(exc).__name__} — przerywam (bez ponowień).")
                break
            record = capture_record(step=step, url=url, request_body=body, response=response, secret=key)
            (OUT / f"{step.name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            cost = _response_cost(response.text)
            # missing usage.cost counts as the conservative per-request reserve, so the 0.20 USD cap still holds
            spent += cost if cost is not None else RESERVE_USD
            print(f"  {i}. {step.name}: HTTP {response.status_code}, usage.cost={cost}")
            if response.status_code != 200 and not args.continue_on_error:
                print("  Odpowiedź ≠ 200 — przerywam (zachowanie jak bezpiecznik, ADR-003 §3.5).")
                break
    print(f"Łączny koszt wg usage.cost: {spent} USD. Nagrania: {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
