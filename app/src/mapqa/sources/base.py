"""Source adapter port (ADR-001 §3.2)."""

from __future__ import annotations

from typing import Protocol

from mapqa.contract.bundle import Bbox, SignsBundle
from mapqa.contract.models import SourceDescriptor


class SourceAdapter(Protocol):
    name: str

    def describe(self) -> SourceDescriptor: ...

    def check(self, bbox: Bbox) -> dict[str, dict[str, int]]: ...

    def load_signs(self, bbox: Bbox | None) -> SignsBundle: ...
