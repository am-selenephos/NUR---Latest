"""Brain-plane Pydantic schemas.

Every struct here crosses the Mind↔Brain boundary and is serialisable to JSON
for durable persistence in ``model_runs.run_metadata`` / ``brain_runs``.
No raw chain-of-thought is ever stored — only decision summaries.
"""
from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ── Profile keys ────────────────────────────────────────────────────────────

class BrainProfileKey(StrEnum):
    """Model profile identifiers; each maps to a concrete provider config."""
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    CRITIC = "critic"


# ── Typed uncertainty (§3 — uncertainty is typed) ───────────────────────────

class UncertaintyKind(StrEnum):
    """Distinct uncertainty types per directive §3.

    Each kind drives different UI treatment and different remediation paths.
    """
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    STALE_EVIDENCE = "stale_evidence"
    DISAGREEMENT = "disagreement"
    MODEL_LIMITATION = "model_limitation"
    CONFLICTING_OWNER_STATE = "conflicting_owner_state"


# ── ScopeEnvelope (§8.1 — scope before retrieval) ──────────────────────────

class ScopeEnvelope(BaseModel):
    """First-class scope contract resolved before any retrieval or provider call.

    Directive §8.1: "Scope resolution occurs before retrieval and before
    provider invocation."  No memory, research, connector, project, or social
    context is fetched until an explicit ScopeEnvelope exists.
    """
    scope_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID
    surface: str = "talk"  # "talk", "journal", "plan", "research", "today", etc.

    # Record-class boundaries
    allowed_record_classes: list[str] = Field(default_factory=list)
    allowed_entity_ids: list[str] = Field(default_factory=list)
    excluded_record_classes: list[str] = Field(default_factory=list)

    # Sharing and connector boundaries
    sharing_boundary: str = "PRIVATE"  # "PRIVATE", "ORBIT", "PROJECT", "CAPSULE", "COMMUNITY"
    connector_boundary: str | None = None

    # Memory and retention policies
    memory_read_policy: str = "SCOPED"  # "SCOPED", "FULL_PRIVATE", "NONE"
    memory_write_policy: str = "EPHEMERAL"  # "EPHEMERAL", "REVIEW", "AUTO_APPROVED"
    retention_policy: str = "DEFAULT"

    # Privacy
    sensitivity_ceiling: str = "NORMAL"  # "LOW", "NORMAL", "ELEVATED", "HIGH"

    # Orbit/Project/Capsule scope
    orbit_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    capsule_id: uuid.UUID | None = None
    community_id: uuid.UUID | None = None

    # Audit
    reason: str = ""
    policy_versions: dict[str, str] = Field(default_factory=dict)


# ── CognitiveTaskPacket (Mind → Brain) ──────────────────────────────────────

class IdentitySnapshot(BaseModel):
    """Frozen identity context passed to the Brain per request."""
    version: str
    name: str
    voice_rules: list[str] = Field(default_factory=list)
    epistemic_rules: list[str] = Field(default_factory=list)
    privacy_rules: list[str] = Field(default_factory=list)
    initiative_rules: list[str] = Field(default_factory=list)
    language_behaviour: dict[str, str] = Field(default_factory=dict)
    forbidden_claims: list[str] = Field(default_factory=list)


class SelfCapabilities(BaseModel):
    """Truthful summary of NUR's current operational state."""
    provider_name: str
    provider_available: bool
    model: str | None = None
    reasoning_effort: str = "high"
    daily_budget_remaining: int = 0
    known_limitations: list[str] = Field(default_factory=list)
    recent_failures: list[str] = Field(default_factory=list)


class ContextSource(BaseModel):
    """A single included/excluded source in the context manifest."""
    kind: str
    id: str
    reason: str
    scope: str = "PRIVATE"
    status: Literal[
        "INCLUDED",
        "EXCLUDED",
        "DEGRADED",
        "FAILED",
        "SKIPPED",
        "TRUNCATED",
    ] = "INCLUDED"
    owner_user_id: uuid.UUID | None = None
    token_estimate: int = Field(default=0, ge=0)
    truncated: bool = False
    degraded: bool = False
    freshness: str | None = None
    provenance: str | None = None


class ContextManifest(BaseModel):
    """Transparent record of what the Brain receives — and what was withheld."""
    scope_statement: str
    included: list[ContextSource] = Field(default_factory=list)
    excluded: list[ContextSource] = Field(default_factory=list)
    degraded: list[ContextSource] = Field(default_factory=list)
    token_budget: int = Field(default=0, ge=0)
    token_used: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def enforce_hard_budget(self) -> "ContextManifest":
        if self.token_used > self.token_budget:
            raise ValueError(
                f"context token usage exceeds hard budget ({self.token_used} > {self.token_budget})"
            )
        return self


class CognitiveTaskPacket(BaseModel):
    """The complete, frozen instruction set from Mind → Brain for one run.

    This is the *only* input the Brain sees.  It never reaches into the
    database or into the owner's raw content.
    """
    task_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID
    orbit_id: uuid.UUID | None = None
    scope_envelope_id: uuid.UUID | None = None  # lineage to the governing ScopeEnvelope
    task_class: str  # "talk", "challenge", "reflect", "summarize", "plan", "research"
    user_input: str
    locale: str = "en"
    writing_preference: str = "default"
    identity: IdentitySnapshot
    self_capabilities: SelfCapabilities
    context_manifest: ContextManifest
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    omega_context: dict[str, Any] = Field(default_factory=dict)
    active_beliefs: list[str] = Field(default_factory=list)
    active_hypotheses: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    max_turns: int = 1


# ── RouteDecision ───────────────────────────────────────────────────────────

class RouteDecision(BaseModel):
    """Recorded justification for profile selection."""
    task_class: str
    selected_profile: BrainProfileKey
    reason: str
    stakes_level: str = "normal"  # "low", "normal", "high", "critical"
    estimated_tokens: int = 0


# ── CognitiveResult (Brain → Mind) ─────────────────────────────────────────

class CognitiveClaim(BaseModel):
    """A single claim produced by the Brain, with source linkage."""
    claim_text: str
    claim_kind: str = "inferred"  # "observed", "inferred", "hypothesis"
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    uncertainty_kind: UncertaintyKind | None = None


# ── WorkflowProposal (Brain → Mind → Agency) ───────────────────────────────

class WorkflowRole(StrEnum):
    """Closed execution and independent-review roles carried into Agency."""
    OPERATOR = "operator"
    RESEARCHER = "researcher"
    IMPLEMENTER = "implementer"
    WRITER = "writer"
    TRANSLATOR = "translator"
    VERIFIER = "verifier"
    CRITIC = "critic"
    QA = "qa"
    SECURITY_REVIEWER = "security_reviewer"
    VISUAL_REVIEWER = "visual_reviewer"


class WorkflowStepProposal(BaseModel):
    """A single proposed workflow step for Agency approval."""
    key: str = ""
    title: str
    role: WorkflowRole = WorkflowRole.OPERATOR
    description: str
    tool_key: str
    tool_version: str
    risk_class: str = "R1_PRIVATE_DRAFT"
    requires_approval: bool = True
    arguments: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    estimated_tokens: int = Field(default=0, ge=0)
    estimated_cost_cents: int = 0
    timeout_seconds: int = 30
    idempotency_key: str | None = None


# Backward-compatible alias
WorkflowStep = WorkflowStepProposal


class WorkflowProposal(BaseModel):
    """When the Brain determines the task requires multi-step execution,
    it proposes a workflow. The Mind validates; Agency approves/rejects."""
    proposal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    title: str
    rationale: str
    steps: list[WorkflowStepProposal] = Field(default_factory=list)
    total_estimated_cost_cents: int = 0
    requires_owner_approval: bool = True


# ── CognitiveResult ─────────────────────────────────────────────────────────

class CognitiveResult(BaseModel):
    """Brain output for a single cognitive step.  Strictly typed."""
    task_id: uuid.UUID
    profile_used: BrainProfileKey
    direct_response: str
    claims: list[CognitiveClaim] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    next_move: str | None = None
    memory_candidates: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    decision_summary: str = ""
    critic_verdict: str | None = None
    critic_notes: list[str] = Field(default_factory=list)
    cost_estimate_cents: int = 0
    workflow_proposal: WorkflowProposal | None = None
    proposed_actions: list[str] = Field(default_factory=list)


class OwnerIdentitySnapshot(BaseModel):
    """Owner and governing scope identity frozen at packet construction time."""

    owner_user_id: uuid.UUID
    orbit_id: uuid.UUID | None = None
    scope_envelope_id: uuid.UUID | None = None


class UserModelSnapshot(BaseModel):
    """Correctable owner-model claims admitted by the current scope."""

    claims: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)


class WorldModelSnapshot(BaseModel):
    """Current scoped environment, never a global or cross-owner world dump."""

    orbit: dict[str, Any] = Field(default_factory=dict)
    today: dict[str, Any] = Field(default_factory=dict)
    workspace: dict[str, Any] = Field(default_factory=dict)


class ProjectModelSnapshot(BaseModel):
    """Current owner projects admitted to the task scope."""

    projects: list[dict[str, Any]] = Field(default_factory=list)


class BeliefSnapshot(BaseModel):
    id: str
    claim: str
    status: str = "EMERGING"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    counterevidence: list[dict[str, Any]] = Field(default_factory=list)


class GoalSnapshot(BaseModel):
    id: str
    title: str
    status: str = "ACTIVE"
    why: str | None = None
    orbit_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class IntentionSnapshot(BaseModel):
    """Intent precedence is explicit and inspectable."""

    explicit_owner_intent: str
    inferred_intentions: list[str] = Field(default_factory=list)
    effective_intent: str
    precedence: Literal["explicit_owner_intent", "inferred_intent"] = "explicit_owner_intent"


class CognitiveBudget(BaseModel):
    """Hard limits carried across Mind and Brain for this one task."""

    max_context_tokens: int = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=2_000, ge=1)
    max_model_calls: int = Field(default=1, ge=1, le=32)
    max_cost_cents: int = Field(default=0, ge=0)
    deadline_seconds: float = Field(default=30.0, gt=0)


class ContextLineage(BaseModel):
    scope_envelope_id: uuid.UUID | None = None
    capability_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    excluded_source_ids: list[str] = Field(default_factory=list)
    degradation_reasons: list[str] = Field(default_factory=list)


class SemanticRoutingSnapshot(BaseModel):
    """Non-mutating planner/research/specialist preflight supplied to the provider."""

    planner_candidates: list[dict[str, Any]] = Field(default_factory=list)
    simulation: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] = Field(default_factory=dict)
    specialists: list[dict[str, Any]] = Field(default_factory=list)


class CognitiveTaskPacketV2(CognitiveTaskPacket):
    """Rich, owner-scoped Mind→Brain contract with a lossless v1 adapter."""

    contract_version: Literal["cognitive-task-v2"] = "cognitive-task-v2"
    owner_identity: OwnerIdentitySnapshot | None = None
    user_model: UserModelSnapshot = Field(default_factory=UserModelSnapshot)
    world_model: WorldModelSnapshot = Field(default_factory=WorldModelSnapshot)
    project_model: ProjectModelSnapshot = Field(default_factory=ProjectModelSnapshot)
    beliefs: list[BeliefSnapshot] = Field(default_factory=list)
    goals: list[GoalSnapshot] = Field(default_factory=list)
    intention: IntentionSnapshot | None = None
    approved_memory: list[dict[str, Any]] = Field(default_factory=list)
    research_context: list[dict[str, Any]] = Field(default_factory=list)
    budget: CognitiveBudget = Field(default_factory=CognitiveBudget)
    context_lineage: ContextLineage = Field(default_factory=ContextLineage)
    semantic_routing: SemanticRoutingSnapshot = Field(default_factory=SemanticRoutingSnapshot)

    @classmethod
    def from_v1(cls, packet: CognitiveTaskPacket) -> "CognitiveTaskPacketV2":
        payload = packet.model_dump()
        payload.update(
            owner_identity=OwnerIdentitySnapshot(
                owner_user_id=packet.owner_user_id,
                orbit_id=packet.orbit_id,
                scope_envelope_id=packet.scope_envelope_id,
            ),
            intention=IntentionSnapshot(
                explicit_owner_intent=packet.user_input,
                effective_intent=packet.user_input,
            ),
            budget=CognitiveBudget(
                max_context_tokens=packet.context_manifest.token_budget,
                max_model_calls=max(1, packet.max_turns),
            ),
            context_lineage=ContextLineage(
                scope_envelope_id=packet.scope_envelope_id,
                source_ids=[source.id for source in packet.context_manifest.included],
                excluded_source_ids=[source.id for source in packet.context_manifest.excluded],
            ),
        )
        return cls.model_validate(payload)


class CognitiveResultV2(CognitiveResult):
    """Versioned Brain→Mind result; visible response fields remain unchanged."""

    contract_version: Literal["cognitive-result-v2"] = "cognitive-result-v2"

    @classmethod
    def from_v1(cls, *, task_id: uuid.UUID, result: dict[str, Any]) -> "CognitiveResultV2":
        return cls.model_validate({"task_id": task_id, **result})


class WorkflowProposalV2(WorkflowProposal):
    """Canonical proposal version with an explicit Agency projection."""

    contract_version: Literal["workflow-proposal-v2"] = "workflow-proposal-v2"

    @classmethod
    def from_v1(cls, proposal: WorkflowProposal) -> "WorkflowProposalV2":
        return cls.model_validate(proposal.model_dump())

    def to_agency_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "key": step.key or f"step-{index}",
                "role": step.role.value,
                "tool_key": step.tool_key,
                "depends_on": list(step.dependencies),
                "input_refs": dict(step.arguments),
                "rationale": step.description,
            }
            for index, step in enumerate(self.steps, start=1)
        ]
