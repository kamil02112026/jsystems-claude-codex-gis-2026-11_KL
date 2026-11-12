"""Cascade orchestration: cache -> circuit breaker -> budget -> port, level 1 then level 2 (ADR-003 §3.5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from mapqa.budget.budget import Budget
from mapqa.budget.cost_log import CostLog
from mapqa.cache.sqlite_cache import AnswerCache, CacheEntry, CacheKey
from mapqa.cascade.ports import ModelPort, PortResult
from mapqa.config.schema import AppConfig
from mapqa.contract.models import CascadeResult, CostLogEntry, ModelAttempt
from mapqa.models.image_prep import ImageOutOfBounds, PreparedImage
from mapqa.questions.catalog import Question

_ROLES = {1: "level1", 2: "level2"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Cascade:
    def __init__(
        self,
        port: ModelPort | None,
        cache: AnswerCache,
        budget: Budget,
        cost_log: CostLog | None,
        config: AppConfig,
        run_id: str,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._port = port
        self._cache = cache
        self._budget = budget
        self._cost_log = cost_log
        self._config = config
        self._run_id = run_id
        self._clock = clock
        self._uncalibrated: set[tuple[int, str, str]] = set()

    def skipped(self, image_sha256: str, question: Question) -> CascadeResult:
        return CascadeResult(photo_sha256=image_sha256, question_id=question.question_id, final_status="skipped_no_model")

    def uncalibrated_warnings(self) -> list[str]:
        return [
            f"próg niekalibrowany dla modelu {model} (poziom {level}, {attribute})"
            for level, model, attribute in sorted(self._uncalibrated)
        ]

    def resolve(
        self,
        *,
        image_sha256: str,
        image: PreparedImage | ImageOutOfBounds,
        question: Question,
        attribute: str,
    ) -> CascadeResult:
        if self._port is None:
            raise RuntimeError("tryb bez modelu: kaskada nie może być wywołana (użyj skipped())")
        base = {"photo_sha256": image_sha256, "question_id": question.question_id}
        if isinstance(image, ImageOutOfBounds):
            return CascadeResult(**base, final_status="image_out_of_bounds", resolved_by="human")

        first = self._attempt(1, image_sha256, image, question, attribute)
        attempts = [first]
        if first.status == "confident":
            return self._done(base, attempts, "resolved", "1", first.answer)
        if first.status in ("model_unavailable", "budget_exceeded"):
            return self._done(base, attempts, first.status, "human")

        reason = first.status
        second = self._attempt(2, image_sha256, image, question, attribute)
        attempts.append(second)
        if second.status == "confident":
            return self._done(base, attempts, "resolved", "2", second.answer, reason)
        if "model_unavailable" in (first.status, second.status):
            final = "model_unavailable"
        elif second.status == "budget_exceeded":
            final = "budget_exceeded"
        else:
            final = "abstain"
        return self._done(base, attempts, final, "human", None, reason)

    @staticmethod
    def _done(base, attempts, final, resolved_by, answer=None, reason=None) -> CascadeResult:
        return CascadeResult(
            **base,
            attempts=attempts,
            final_status=final,
            resolved_by=resolved_by,
            final_answer=answer,
            escalation_reason=reason,
        )

    def _model_for(self, level: int) -> tuple[str, str | None]:
        models = self._config.models
        return (models.level1, None) if level == 1 else (models.level2, models.level2_effort)

    def _attempt(
        self, level: int, sha: str, image: PreparedImage, question: Question, attribute: str
    ) -> ModelAttempt:
        model, effort = self._model_for(level)
        threshold = self._config.threshold(level=level, model=model, attribute=attribute)
        if not self._config.calibrated(level=level, model=model, attribute=attribute):
            self._uncalibrated.add((level, model, attribute))
        key = CacheKey(level, sha, question.question_id, model, effort or "", question.prompt_version)

        entry = self._cache.get(key)
        if entry is not None:
            attempt = ModelAttempt(
                level=level,  # type: ignore[arg-type]
                model=model,
                reasoning_effort=effort,
                answer=entry.parsed_answer,
                probability=entry.probability,
                status=entry.status_for(threshold),  # type: ignore[arg-type]
                cache_hit=True,
                cost_usd=Decimal("0"),
            )
            self._log(attempt, question, sha, entry.input_tokens, entry.output_tokens, False)
            return attempt

        role = _ROLES[level]
        refusal = self._budget.can_send(role, sha)
        if refusal == "circuit_open":
            # no request, no cost: not a cost-log row (keeps TAC-003-02 equality)
            return ModelAttempt(
                level=level,  # type: ignore[arg-type]
                model=model,
                reasoning_effort=effort,
                status="model_unavailable",
                error_class="circuit_open",
            )
        if refusal is not None:
            attempt = ModelAttempt(
                level=level,  # type: ignore[arg-type]
                model=model,
                reasoning_effort=effort,
                status="budget_exceeded",
                error_class=refusal,
            )
            self._log(attempt, question, sha, None, None, False)
            return attempt

        self._budget.register(role, sha)
        result = self._call(level, model, effort, image, question)
        estimated = self._budget.commit(result.cost_usd, role)
        attempt = self._classify(level, model, effort, result, threshold)
        if result.parse_status == "model_unavailable":
            self._budget.open_circuit(result.error_class or "unknown")
        self._store(key, attempt, result)
        self._log(attempt, question, sha, result.input_tokens, result.output_tokens, estimated)
        return attempt

    def _call(
        self, level: int, model: str, effort: str | None, image: PreparedImage, question: Question
    ) -> PortResult:
        assert self._port is not None
        try:
            return self._port.ask(level=level, model=model, reasoning_effort=effort, image=image, question=question)
        except Exception as exc:  # F5.7: one bad question must not stop the run
            return PortResult(
                answer=None, probability=None, parse_status="invalid_response", error_class=type(exc).__name__
            )

    @staticmethod
    def _classify(level: int, model: str, effort: str | None, result: PortResult, threshold: float) -> ModelAttempt:
        status = result.parse_status
        probability = result.probability
        if status == "ok":
            if result.answer is None or probability is None:
                status = "invalid_response"
            else:
                status = "confident" if probability >= threshold else "below_threshold"
        return ModelAttempt(
            level=level,  # type: ignore[arg-type]
            model=model,
            reasoning_effort=effort,
            answer=result.answer,
            probability=probability,
            status=status,  # type: ignore[arg-type]
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
            error_class=result.error_class,
        )

    def _store(self, key: CacheKey, attempt: ModelAttempt, result: PortResult) -> None:
        if result.parse_status != "ok" and result.response_body is None:
            # local exception / transport problem: not a deterministic model answer (ADR-003 §3.7)
            return
        self._cache.put(
            key,
            CacheEntry(
                parsed_answer=attempt.answer,
                probability=attempt.probability,
                status=attempt.status,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                response_body=result.response_body,
            ),
        )

    def _log(
        self,
        attempt: ModelAttempt,
        question: Question,
        sha: str,
        input_tokens: int | None,
        output_tokens: int | None,
        estimated: bool,
    ) -> None:
        if self._cost_log is None:
            return
        self._cost_log.append(
            CostLogEntry(
                ts=self._clock().isoformat(),
                run_id=self._run_id,
                level=attempt.level,
                model=attempt.model,
                reasoning_effort=attempt.reasoning_effort,
                question_id=question.question_id,
                image_sha256=sha,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=attempt.cost_usd,
                cost_estimated=estimated,
                cache="hit" if attempt.cache_hit else "miss",
                status=attempt.status,
            )
        )
