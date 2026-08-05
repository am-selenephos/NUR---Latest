"""Brain-plane Pydantic schemas.

Every struct here crosses the Mind↔Brain boundary and is serialisable to JSON
for durable persistence in ``model_runs.run_metadata`` / ``brain_runs``.
No raw chain-of-thought is ever stored — only decision summaries.
"""
from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ── Profile keys ────────────────────────────────────────────────────────────

class BrainProfileKey(StrEnum):
    """Model profile identifiers; each maps to a concrete provider config."""
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    CRITIC = "critic"


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


class CognitiveResult(BaseModel):
    """Complete Brain output for one cognitive task.

    The Mind interprets this into owner-facing response + state updates.
    No chain-of-thought is stored — only the ``decision_summary``.
    """
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
    cost_estimate_cents: float = 0.0


# ── WorkflowProposal (Brain → Mind → Agency) ───────────────────────────────

class WorkflowStep(BaseModel):
    """A single proposed workflow step for Agency approval."""
    title: str
    description: str
    requires_approval: bool = True
    estimated_cost_cents: float = 0.0


class WorkflowProposal(BaseModel):
    """When the Brain determines the task requires multi-step execution,
    it proposes a workflow.  The Mind validates; Agency approves/rejects."""
    proposal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    title: str
    rationale: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    total_estimated_cost_cents: float = 0.0
    requires_owner_approval: bool = True
