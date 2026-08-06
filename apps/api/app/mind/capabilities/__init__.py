"""NUR Mind Capabilities package (Kernel).

Exposes schemas, registry, resolver, and standard first-party capability definitions.
"""
from __future__ import annotations

from app.mind.capabilities.schemas import (
    CapabilitySpec,
    ContextHydrationRecipe,
    ExecutionMode,
)
from app.mind.capabilities.registry import (
    CapabilityRegistry,
    DuplicateCapabilityError,
    InvalidCapabilitySpecError,
    get_default_registry,
)
from app.mind.capabilities.resolver import (
    AbstentionReasonCode,
    CapabilityResolution,
    CapabilityResolver,
    ResolutionFallbackMode,
)

__all__ = [
    "CapabilitySpec",
    "ContextHydrationRecipe",
    "ExecutionMode",
    "CapabilityRegistry",
    "DuplicateCapabilityError",
    "InvalidCapabilitySpecError",
    "get_default_registry",
    "AbstentionReasonCode",
    "CapabilityResolution",
    "CapabilityResolver",
    "ResolutionFallbackMode",
]
