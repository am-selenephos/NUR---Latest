"""NUR Capability Runtime — Capability Schemas.

Defines the declarative, immutable specification for cognitive capabilities in the Mind plane.
"""
from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ExecutionMode(enum.StrEnum):
    READ_ONLY_WORKER = "READ_ONLY_WORKER"
    COGNITIVE_SYNTHESIS = "COGNITIVE_SYNTHESIS"
    WORKFLOW_PROPOSAL = "WORKFLOW_PROPOSAL"
    HYBRID = "HYBRID"


class HydrationFailurePolicy(enum.StrEnum):
    FAIL_REQUIRED_DEGRADE_OPTIONAL = "FAIL_REQUIRED_DEGRADE_OPTIONAL"
    FAIL_ANY = "FAIL_ANY"
    BEST_EFFORT = "BEST_EFFORT"


KNOWN_CONTEXT_SOURCE_KEYS = frozenset({
    "workspace_frame",
    "hybrid_retrieval",
    "personal_memory",
    "active_plans",
    "timeline",
    "today_state",
    "orbit_context",
    "beliefs",
})


class ContextHydrationRecipe(BaseModel):
    """Declarative, immutable specification of data layers required by a capability."""
    model_config = ConfigDict(frozen=True)

    source_keys: tuple[str, ...] = Field(default_factory=tuple)
    required_source_keys: tuple[str, ...] = Field(default_factory=tuple)
    optional_source_keys: tuple[str, ...] = Field(default_factory=tuple)
    max_items_per_source: dict[str, int] = Field(default_factory=dict)
    max_total_tokens: int = 4000
    failure_policy: HydrationFailurePolicy = HydrationFailurePolicy.FAIL_REQUIRED_DEGRADE_OPTIONAL

    # Filtering & extraction boundaries
    include_workspace_frame: bool = True
    hybrid_retrieval_limit: int = 6
    required_record_classes: tuple[str, ...] = Field(default_factory=tuple)
    excluded_record_classes: tuple[str, ...] = Field(default_factory=tuple)
    required_entity_types: tuple[str, ...] = Field(default_factory=tuple)
    allowed_entity_ids: tuple[str, ...] = Field(default_factory=tuple)
    fetch_orbit_context: bool = False
    fetch_active_plans: bool = False
    fetch_timeline_window_days: int = 0
    max_context_tokens: int = 4000


class CapabilitySpec(BaseModel):
    """Specification of a discrete cognitive capability."""
    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(..., description="Unique slug, e.g., 'capability:plan_from_conversation'")
    name: str
    description: str
    intent_signatures: tuple[str, ...] = Field(
        ..., description="Exemplar phrases used for semantic similarity matching"
    )
    allowed_surfaces: tuple[str, ...] = Field(
        default=("talk",),
        description="Surfaces where this capability is permitted ('talk', 'plan', 'research', etc.)"
    )
    sensitivity_ceiling: str = Field(
        default="NORMAL",
        description="Maximum sensitivity allowed ('LOW', 'NORMAL', 'ELEVATED', 'HIGH')"
    )
    execution_mode: ExecutionMode
    required_tools: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Tool keys from app.agentic.tools.ALL_TOOLS required during execution"
    )
    worker_role: str = Field(default="SPECIALIST")
    hydration_recipe: ContextHydrationRecipe = Field(default_factory=ContextHydrationRecipe)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    min_confidence_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=30, gt=0)
    estimated_cost_cents: float = Field(default=0.0, ge=0.0)
    abstention_prompt: str = Field(
        default="I notice you may want a plan, but I need more details before drafting one."
    )
    enabled: bool = Field(default=True, description="Whether this capability is active for resolution")
