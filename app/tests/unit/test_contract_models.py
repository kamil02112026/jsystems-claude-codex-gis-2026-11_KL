"""T03: domain models and JSON envelope (ADR-000 §5, §6; TAC-02)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydValidationError

from mapqa.contract import errors
from mapqa.contract.models import (
    AttributeValue,
    CascadeResult,
    Envelope,
    ErrorInfo,
    ModelAttempt,
    PhotoRoadLink,
    RunLimits,
)


def test_envelope_ok_requires_result() -> None:
    env = Envelope(ok=True, command="sources list", exit_code=0, result={"sources": []})
    assert env.model_dump()["error"] is None
    with pytest.raises(PydValidationError):
        Envelope(ok=True, command="run", exit_code=0)


def test_envelope_error_requires_error_and_nonzero_code() -> None:
    env = Envelope(ok=False, command="run", exit_code=1, error=ErrorInfo(code="invalid_bbox", message="Zły bbox"))
    assert env.result is None
    with pytest.raises(PydValidationError):
        Envelope(ok=False, command="run", exit_code=0, error=ErrorInfo(code="x", message="y"))
    with pytest.raises(PydValidationError):
        Envelope(ok=False, command="run", exit_code=1)


def test_exit_code_3_is_ok_with_warnings() -> None:  # ADR-000 §6: code 3 = finished run with warnings
    env = Envelope(ok=True, command="run", exit_code=3, result={}, warnings=["budget_exceeded: 2 pytań"])
    assert env.ok and env.exit_code == 3


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (errors.ValidationError, 1),
        (errors.ConfigError, 1),
        (errors.ContractViolation, 1),
        (errors.ConfirmationRequired, 1),
        (errors.SourceUnavailable, 2),
        (errors.AuthFailed, 2),
        (errors.InputModified, 4),
    ],
)
def test_exceptions_map_to_exit_codes(exc: type[errors.MapQAError], code: int) -> None:
    assert exc("x").exit_code == code


def test_default_limits_match_prd() -> None:  # PRD F5.9, ADR-003 §3.6
    lim = RunLimits()
    assert (lim.max_queries, lim.max_images, str(lim.max_usd)) == (100, 25, "1.00")


def test_heading_diff_bounded_and_null_kept() -> None:
    link = PhotoRoadLink(photo_id="p", osm_way_id=None, distance_m=1.0, heading_diff_deg=None, candidate_count=0, flags=[], link_source="provided")
    assert link.heading_diff_deg is None
    with pytest.raises(PydValidationError):
        PhotoRoadLink(photo_id="p", distance_m=1.0, heading_diff_deg=120.0, candidate_count=1, flags=[], link_source="provided")


def test_attribute_value_statuses() -> None:
    AttributeValue(raw="50", normalized=50.0, speed_source="explicit", status="ok")
    with pytest.raises(PydValidationError):
        AttributeValue(raw="50", normalized=50.0, status="weird")


def test_cascade_result_final_statuses() -> None:
    attempt = ModelAttempt(level=1, model="typesafe/jev-1.14", status="confident", answer="50", probability=0.9, cache_hit=False)
    res = CascadeResult(photo_sha256="a" * 64, question_id="speed_limit_value", attempts=[attempt], final_status="resolved", resolved_by="1", final_answer="50")
    assert res.resolved_by == "1"
    CascadeResult(photo_sha256="a" * 64, question_id="q", attempts=[], final_status="skipped_no_model")
