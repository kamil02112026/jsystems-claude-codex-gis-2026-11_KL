"""Domain exceptions mapped to CLI exit codes (ADR-000 §6, ADR-001 §3.2)."""

from __future__ import annotations


class MapQAError(Exception):
    """Base error with a stable code, exit code and optional hint."""

    exit_code: int = 1
    code: str = "error"

    def __init__(self, message: str, *, hint: str | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        if code is not None:
            self.code = code


class ValidationError(MapQAError):
    exit_code = 1
    code = "invalid_input"


class ConfigError(MapQAError):
    exit_code = 1
    code = "config_invalid"


class ContractViolation(MapQAError):
    exit_code = 1
    code = "contract_violation"


class ConfirmationRequired(MapQAError):
    exit_code = 1
    code = "confirmation_required"


class SourceUnavailable(MapQAError):
    exit_code = 2
    code = "source_unavailable"


class AuthFailed(MapQAError):
    exit_code = 2
    code = "auth_failed"
