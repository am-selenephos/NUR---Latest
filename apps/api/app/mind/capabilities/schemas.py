"""NUR Capability Runtime — Capability Schemas.

Defines the declarative specification for cognitive capabilities in the Mind plane.
"""
from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, Field


class ExecutionMode(enum.StrEnum):
    READ_ONLY_WORKER = "READ_ONLY_WORKER"
    COGNITIVE_SYNTHESIS = "COGNITIVE_SYNTHESIS"
    WORKFLOW_PROPOSAL = "WORKFLOW_PROPOSAL"
    HYBRID = "HYBRID"


class ContextHydrationRecipe(BaseModel):
    """Declarative specification of data layers required by a capability."""
    include_workspace_frame: bool = True
    hybrid_retrieval_limit: int = 6
    required_record_classes: list[str] = Field(default_factory=list)
    required_entity_types: list[str] = Field(default_factory=list)
    fetch_orbit_context: bool = False
    fetch_active_plans: bool = False
    fetch_timeline_window_days: int = 0
    max_context_tokens: int = 4000


class CapabilitySpec(BaseModel):
    """Specification of a discrete cognitive capability."""
    capability_id: str = Field(..., description="Unique slug, e.g., 'capability:plan_from_conversation'")
    name: str
    description: str
    intent_signatures: list[str] = Field(
        ..., description="Exemplar phrases used for semantic similarity matching"
    )
    allowed_surfaces: list[str] = Field(
        default_factory=lambda: ["talk"],
        description="Surfaces where this capability is permitted ('talk', 'plan', 'research', etc.)"
    )
    sensitivity_ceiling: str = Field(
        default="NORMAL",
        description="Maximum sensitivity allowed ('LOW', 'NORMAL', 'ELEVATED', 'HIGH')"
    )
    execution_mode: ExecutionMode
    required_tools: list[str] = Field(
        default_factory=list,
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
