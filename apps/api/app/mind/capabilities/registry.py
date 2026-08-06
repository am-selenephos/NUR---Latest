"""NUR Capability Registry — in-memory validated catalog of first-party capabilities.

Enforces tool contract validation, prevents duplicate registration, and provides
scope/surface filtering.
"""
from __future__ import annotations

from app.agentic.registry import spec as get_tool_spec, UnknownToolError
from app.mind.capabilities.schemas import CapabilitySpec


class DuplicateCapabilityError(RuntimeError):
    """Raised when two specs register the same capability_id."""


class InvalidCapabilitySpecError(ValueError):
    """Raised when a CapabilitySpec references unknown tools or invalid configuration."""


class CapabilityRegistry:
    """In-memory validated catalog of all first-party NUR capabilities."""

    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}

    def register(self, capability: CapabilitySpec) -> None:
        """Register a CapabilitySpec with strict validation of required tools."""
        if capability.capability_id in self._specs:
            raise DuplicateCapabilityError(f"Duplicate capability registered: {capability.capability_id}")

        # Verify that all declared required tools exist in the Agency registry
        for tool_key in capability.required_tools:
            try:
                get_tool_spec(tool_key)
            except UnknownToolError as exc:
                raise InvalidCapabilitySpecError(
                    f"Capability '{capability.capability_id}' references unknown tool '{tool_key}'"
                ) from exc

        self._specs[capability.capability_id] = capability

    def get(self, capability_id: str) -> CapabilitySpec:
        """Fetch a capability by ID or raise KeyError."""
        if capability_id not in self._specs:
            raise KeyError(f"Unknown capability: {capability_id}")
        return self._specs[capability_id]

    def all(self) -> list[CapabilitySpec]:
        """Return all registered capabilities."""
        return list(self._specs.values())

    def filter_by_surface_and_scope(self, surface: str, sensitivity: str) -> list[CapabilitySpec]:
        """Filter enabled capabilities by allowed surface and sensitivity ceiling."""
        return [
            cap for cap in self._specs.values()
            if cap.enabled and surface in cap.allowed_surfaces and self._sensitivity_allowed(cap.sensitivity_ceiling, sensitivity)
        ]

    @staticmethod
    def _sensitivity_allowed(cap_ceiling: str, current_sensitivity: str) -> bool:
        order = {"LOW": 1, "NORMAL": 2, "ELEVATED": 3, "HIGH": 4}
        return order.get(cap_ceiling.upper(), 2) >= order.get(current_sensitivity.upper(), 2)


_DEFAULT_REGISTRY: CapabilityRegistry | None = None


def get_default_registry() -> CapabilityRegistry:
    """Return the global default capability registry with standard capabilities loaded."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        reg = CapabilityRegistry()
        from app.mind.capabilities.definitions.contextual_answer import CONTEXTUAL_ANSWER_SPEC
        from app.mind.capabilities.definitions.plan_from_conversation import PLAN_FROM_CONVERSATION_SPEC

        reg.register(CONTEXTUAL_ANSWER_SPEC)
        reg.register(PLAN_FROM_CONVERSATION_SPEC)
        _DEFAULT_REGISTRY = reg
    return _DEFAULT_REGISTRY
