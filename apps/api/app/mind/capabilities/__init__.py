"""NUR Mind Capabilities package.

Exposes schemas, registry, resolver, hydrator, dispatcher, and standard first-party capability definitions.
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
from app.mind.capabilities.hydrator import (
    ContextHydrator,
    HydratedCapabilityContext,
)
from app.mind.capabilities.dispatcher import (
    WorkerDispatcher,
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
    "ContextHydrator",
    "HydratedCapabilityContext",
    "WorkerDispatcher",
]
