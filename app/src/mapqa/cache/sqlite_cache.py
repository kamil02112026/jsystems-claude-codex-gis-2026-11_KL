"""Cache odpowiedzi modeli w SQLite (ADR-003 §3.7, D-003-4; ADR-000 D5).

Klucz: poziom, sha256 obrazu źródłowego, pytanie, model, reasoning_effort, prompt_version.
Próg nie wchodzi do klucza — status `confident`/`below_threshold` przelicza `CacheEntry.status_for`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from mapqa.contract.hashing import sha256_file

STORABLE_STATUSES = frozenset({"confident", "below_threshold", "invalid_response"})
_SEPARATOR = "\x1f"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answer_cache (
    key_hash TEXT PRIMARY KEY,
    level INTEGER NOT NULL,
    image_sha256 TEXT NOT NULL,
    question_id TEXT NOT NULL,
    model TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    parsed_answer TEXT,
    probability REAL,
    status TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd TEXT,
    response_body TEXT,
    created_at TEXT NOT NULL
)
"""


file_sha256 = sha256_file  # single shared helper (contract.hashing)


@dataclass(frozen=True)
class CacheKey:
    level: int
    image_sha256: str
    question_id: str
    model: str
    reasoning_effort: str
    prompt_version: str

    def digest(self) -> str:
        parts = (
            str(self.level),
            self.image_sha256,
            self.question_id,
            self.model,
            self.reasoning_effort,
            self.prompt_version,
        )
        return hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    parsed_answer: str | None
    probability: float | None
    status: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None
    response_body: str | None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def status_for(self, threshold: float) -> str:
        """Status przy progu: `confident` gdy probability ≥ threshold, inaczej `below_threshold`."""
        if self.status not in ("confident", "below_threshold"):
            return self.status
        if self.probability is None:
            raise ValueError("status confident/below_threshold wymaga probability")
        return "confident" if self.probability >= threshold else "below_threshold"


class AnswerCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        with self._conn:
            self._conn.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> AnswerCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, key: CacheKey) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT parsed_answer, probability, status, input_tokens, output_tokens, "
            "cost_usd, response_body, created_at FROM answer_cache WHERE key_hash = ?",
            (key.digest(),),
        ).fetchone()
        if row is None:
            return None
        parsed, probability, status, in_tok, out_tok, cost, body, created = row
        return CacheEntry(
            parsed_answer=parsed,
            probability=probability,
            status=status,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=Decimal(cost) if cost is not None else None,
            response_body=body,
            created_at=created,
        )

    def put(self, key: CacheKey, entry: CacheEntry) -> None:
        """Zapisuje wynik deterministyczny; `model_unavailable`/`budget_exceeded` są pomijane (CAC-03)."""
        if entry.status not in STORABLE_STATUSES:
            return
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO answer_cache (key_hash, level, image_sha256, question_id, model, "
                "reasoning_effort, prompt_version, parsed_answer, probability, status, input_tokens, "
                "output_tokens, cost_usd, response_body, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key.digest(),
                    key.level,
                    key.image_sha256,
                    key.question_id,
                    key.model,
                    key.reasoning_effort,
                    key.prompt_version,
                    entry.parsed_answer,
                    entry.probability,
                    entry.status,
                    entry.input_tokens,
                    entry.output_tokens,
                    str(entry.cost_usd) if entry.cost_usd is not None else None,
                    entry.response_body,
                    entry.created_at,
                ),
            )
