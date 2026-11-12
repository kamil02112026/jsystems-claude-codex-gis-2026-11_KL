"""Per-run budget gate: query, image, cost and circuit-breaker checks (ADR-003 §3.5, §3.6)."""

from __future__ import annotations

from decimal import Decimal

from mapqa.contract.models import RunLimits


class Budget:
    def __init__(self, limits: RunLimits) -> None:
        self._limits = limits
        self.queries_used = 0
        self.images_used = 0
        self.cost_used_usd = Decimal("0")
        self.circuit_error_class: str | None = None
        self._counted_images: set[str] = set()

    @property
    def circuit_open(self) -> bool:
        return self.circuit_error_class is not None

    def open_circuit(self, error_class: str) -> None:
        """Open the breaker for the rest of the run; the first error class is kept."""
        if self.circuit_error_class is None:
            self.circuit_error_class = error_class

    def can_send(self, role: str, image_sha256: str) -> str | None:
        """Return None when a request may be sent, otherwise the refusal reason."""
        if self.circuit_open:
            return "circuit_open"
        if self.queries_used + 1 > self._limits.max_queries:
            return "max_queries"
        if self.cost_used_usd + self._reserve(role) > self._limits.max_usd:
            return "max_usd"
        if image_sha256 not in self._counted_images and self.images_used + 1 > self._limits.max_images:
            return "max_images"
        return None

    def register(self, role: str, image_sha256: str) -> None:
        """Count a request (and its image, if new) right before it is sent."""
        self.queries_used += 1
        if image_sha256 not in self._counted_images:
            self._counted_images.add(image_sha256)
            self.images_used += 1

    def commit(self, cost: Decimal | None, role: str) -> bool:
        """Add the actual cost, or the role reserve when unknown. Returns cost_estimated."""
        if cost is None:
            self.cost_used_usd += self._reserve(role)
            return True
        self.cost_used_usd += cost
        return False

    def _reserve(self, role: str) -> Decimal:
        return self._limits.reserve_usd[role]
