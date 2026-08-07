"""NUR Capability Registry — in-memory validated catalog of first-party capabilities.

Enforces tool contract validation, prevents duplicate registration, enforces seal lifecycle,
and provides scope/surface filtering.
"""
from __future__ import annotations

from app.agentic.registry import spec as get_tool_spec, UnknownToolError
from app.mind.capabilities.schemas import (
    CapabilitySpec,
    KNOWN_CONTEXT_SOURCE_KEYS,
)


class RegistrySealedError(RuntimeError):
    """Raised when attempting to register a capability in a sealed registry."""


class DuplicateCapabilityError(RuntimeError):
    """Raised when two specs register the same capability_id."""


class InvalidCapabilitySpecError(ValueError):
    """Raised when a CapabilitySpec references unknown tools or invalid configuration."""


class CapabilityRegistry:
    """In-memory validated catalog of all first-party NUR capabilities."""

    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}
        self._sealed: bool = False

    @property
    def is_sealed(self) -> bool:
        """Whether this registry has been sealed to prevent runtime mutation."""
        return self._sealed

    def seal(self) -> CapabilityRegistry:
        """Seal registry to forbid further registrations."""
        self._sealed = True
        return self

    def register(self, capability: CapabilitySpec) -> None:
        """Register a CapabilitySpec with strict validation of required tools and context sources."""
        if self._sealed:
            raise RegistrySealedError("Cannot register capability on a sealed registry.")

        if capability.capability_id in self._specs:
            raise DuplicateCapabilityError(f"Duplicate capability registered: {capability.capability_id}")

        # Validate context sources classification and namespace
        recipe = capability.hydration_recipe
        req_set = set(recipe.required_source_keys)
        opt_set = set(recipe.optional_source_keys)
        src_set = set(recipe.source_keys)

        # Invariant 1: source_keys must equal required UNION optional (no undeclared or unclassified sources)
        if src_set != (req_set | opt_set):
            raise InvalidCapabilitySpecError(
                f"Capability '{capability.capability_id}' source_keys ({src_set}) does not match "
                f"required ({req_set}) union optional ({opt_set})"
            )

        # Invariant 2: required and optional must be disjoint (empty intersection)
        if req_set & opt_set:
            raise InvalidCapabilitySpecError(
                f"Capability '{capability.capability_id}' has overlapping required and optional source keys: "
                f"{req_set & opt_set}"
            )

        # Invariant 3: every declared source must map to an implemented V1 context loader
        for sk in src_set:
            if sk not in KNOWN_CONTEXT_SOURCE_KEYS:
                raise InvalidCapabilitySpecError(
                    f"Capability '{capability.capability_id}' references unknown context source '{sk}'"
                )

        # Verify that all declared required tools exist in the Agency registry
        for tool_key in capability.required_tools:
            if tool_key in KNOWN_CONTEXT_SOURCE_KEYS:
                raise InvalidCapabilitySpecError(
                    f"Capability '{capability.capability_id}' declared context source key '{tool_key}' as an Agency tool"
                )
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

    def all(self) -> tuple[CapabilitySpec, ...]:
        """Return all registered capabilities as an immutable tuple."""
        return tuple(self._specs.values())

    def filter_by_surface_and_scope(self, surface: str, sensitivity: str) -> tuple[CapabilitySpec, ...]:
        """Filter enabled capabilities by allowed surface and sensitivity ceiling."""
        return tuple(
            cap for cap in self._specs.values()
            if cap.enabled and surface in cap.allowed_surfaces and self._sensitivity_allowed(cap.sensitivity_ceiling, sensitivity)
        )

    @staticmethod
    def _sensitivity_allowed(cap_ceiling: str, current_sensitivity: str) -> bool:
        order = {"LOW": 1, "NORMAL": 2, "ELEVATED": 3, "HIGH": 4}
        return order.get(cap_ceiling.upper(), 2) >= order.get(current_sensitivity.upper(), 2)


_DEFAULT_REGISTRY: CapabilityRegistry | None = None


def get_default_registry() -> CapabilityRegistry:
    """Return the global default capability registry with standard capabilities loaded and sealed."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        reg = CapabilityRegistry()
        from app.mind.capabilities.definitions.contextual_answer import CONTEXTUAL_ANSWER_SPEC
        from app.mind.capabilities.definitions.plan_from_conversation import PLAN_FROM_CONVERSATION_SPEC

        reg.register(CONTEXTUAL_ANSWER_SPEC)
        reg.register(PLAN_FROM_CONVERSATION_SPEC)
        reg.seal()
        _DEFAULT_REGISTRY = reg
    return _DEFAULT_REGISTRY
