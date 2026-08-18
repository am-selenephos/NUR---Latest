"""NUR Capability Runtime — Capability Schemas.

Defines the declarative, immutable specification for cognitive capabilities in the Mind plane.
"""
from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutionMode(enum.StrEnum):
    READ_ONLY_WORKER = "READ_ONLY_WORKER"
    COGNITIVE_SYNTHESIS = "COGNITIVE_SYNTHESIS"
    WORKFLOW_PROPOSAL = "WORKFLOW_PROPOSAL"
    HYBRID = "HYBRID"


class HydrationFailurePolicy(enum.StrEnum):
    FAIL_REQUIRED_DEGRADE_OPTIONAL = "FAIL_REQUIRED_DEGRADE_OPTIONAL"
    FAIL_ANY = "FAIL_ANY"
    BEST_EFFORT = "BEST_EFFORT"


class HydrationStatus(enum.StrEnum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


KNOWN_CONTEXT_SOURCE_KEYS = frozenset({
    "workspace_frame",
    "hybrid_retrieval",
    "active_plans",
    "timeline",
    "today_state",
    "orbit_context",
    "approved_memory",
    "beliefs",
    "user_model",
    "research",
    "semantic_context",
})


class HydrationIssue(BaseModel):
    """Audit record of an issue encountered during context hydration."""
    model_config = ConfigDict(frozen=True)

    issue_type: str
    source_key: str
    message: str
    fatal: bool = False


class HydrationSourceResult(BaseModel):
    """Status and token accounting for a single hydration source."""
    model_config = ConfigDict(frozen=True)

    source_key: str
    status: str
    count: int = 0
    estimated_tokens: int = 0
    error_message: str | None = None


class HydrationReport(BaseModel):
    """Complete audit summary of context hydration execution."""
    model_config = ConfigDict(frozen=True)

    status: HydrationStatus
    total_tokens_used: int = 0
    per_source: tuple[HydrationSourceResult, ...] = Field(default_factory=tuple)
    issues: tuple[HydrationIssue, ...] = Field(default_factory=tuple)
    included_sources: tuple[str, ...] = Field(default_factory=tuple)
    excluded_sources: tuple[str, ...] = Field(default_factory=tuple)
    degraded_sources: tuple[str, ...] = Field(default_factory=tuple)
    truncated_sources: tuple[str, ...] = Field(default_factory=tuple)


class ContextHydrationRecipe(BaseModel):
    """Declarative, deeply immutable specification of data layers required by a capability."""
    model_config = ConfigDict(frozen=True)

    source_keys: tuple[str, ...] = Field(default_factory=tuple)
    required_source_keys: tuple[str, ...] = Field(default_factory=tuple)
    optional_source_keys: tuple[str, ...] = Field(default_factory=tuple)
    max_items_per_source: tuple[tuple[str, int], ...] = Field(default_factory=tuple)
    max_total_tokens: int = 4000
    failure_policy: HydrationFailurePolicy = HydrationFailurePolicy.FAIL_REQUIRED_DEGRADE_OPTIONAL

    # Filtering & extraction boundaries
    include_workspace_frame: bool = True
    hybrid_retrieval_limit: int = 6
    required_record_classes: tuple[str, ...] = Field(default_factory=tuple)
    excluded_record_classes: tuple[str, ...] = Field(default_factory=tuple)
    allowed_entity_ids: tuple[str, ...] = Field(default_factory=tuple)
    fetch_orbit_context: bool = False
    fetch_active_plans: bool = False
    fetch_timeline_window_days: int = 0
    max_context_tokens: int = 4000

    @field_validator("max_items_per_source", mode="before")
    @classmethod
    def _coerce_max_items(cls, v: Any) -> tuple[tuple[str, int], ...]:
        if isinstance(v, dict):
            return tuple(sorted((str(k), int(val)) for k, val in v.items()))
        if isinstance(v, (list, tuple)):
            return tuple((str(k), int(val)) for k, val in v)
        return tuple()

    @property
    def items_per_source_map(self) -> dict[str, int]:
        return dict(self.max_items_per_source)


class CapabilitySpec(BaseModel):
    """Specification of a discrete cognitive capability."""
    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(..., description="Unique slug, e.g., 'capability:plan_from_conversation'")
    version: str = Field(default="1", min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
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
    min_confidence_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=30, gt=0)
    estimated_cost_cents: int = Field(default=0, ge=0)
    abstention_prompt: str = Field(
        default="I notice you may want a plan, but I need more details before drafting one."
    )
    enabled: bool = Field(default=True, description="Whether this capability is active for resolution")
