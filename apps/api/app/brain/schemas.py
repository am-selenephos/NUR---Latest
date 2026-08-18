"""Brain-plane Pydantic schemas.

Every struct here crosses the Mind↔Brain boundary and is serialisable to JSON
for durable persistence in ``model_runs.run_metadata`` / ``brain_runs``.
No raw chain-of-thought is ever stored — only decision summaries.
"""
from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class ContextManifest(BaseModel):
    """Transparent record of what the Brain receives — and what was withheld."""
    scope_statement: str
    included: list[ContextSource] = Field(default_factory=list)
    excluded: list[ContextSource] = Field(default_factory=list)
    token_budget: int = 0
    token_used: int = 0


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

class WorkflowStepProposal(BaseModel):
    """A single proposed workflow step for Agency approval."""
    key: str = ""
    title: str
    description: str
    tool_key: str
    tool_version: str
    risk_class: str = "R1_PRIVATE_DRAFT"
    requires_approval: bool = True
    arguments: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
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


class CognitiveTaskPacketV2(CognitiveTaskPacket):
    """Versioned Mind→Brain boundary with a lossless v1 projection."""

    contract_version: Literal["cognitive-task-v2"] = "cognitive-task-v2"

    @classmethod
    def from_v1(cls, packet: CognitiveTaskPacket) -> "CognitiveTaskPacketV2":
        return cls.model_validate(packet.model_dump())


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
                "role": "operator",
                "tool_key": step.tool_key,
                "depends_on": list(step.dependencies),
                "input_refs": dict(step.arguments),
                "rationale": step.description,
            }
            for index, step in enumerate(self.steps, start=1)
        ]
