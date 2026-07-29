"""Durable records for the NUR Agency Plane.

Deliberately NUR-wide, sitting above the existing `am_project_*` tables rather
than replacing them. `AMProjectRun` is already a good single-step primitive —
idempotency key, attempt, worker id, requested/approved capabilities, budget,
timeout, failure code, cost. What it has no notion of is a *graph*: a plan with
dependencies, an approval that pauses mid-flight, a checkpoint you can resume
from, or an append-only account of what actually happened.

Three shapes here exist because of specific failure modes:

`AgentApproval.argument_digest` binds an approval to the exact redacted
arguments the owner saw. Approving "schedule this event on Friday" must not
authorise "schedule this event on Friday" with a different payload swapped in
after the fact. Any mutation changes the digest and invalidates the approval.

`AgentRunEvent` is append-only. A run's history cannot be edited into looking
cleaner than it was — which is the difference between an audit trail and a
status field.

`AgentCheckpoint` holds serialised planner and agent run state so a workflow
survives worker restart, but is explicitly never a place for secrets; the
`redaction` module is responsible for what may enter it.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.models._mixins import now_utc, uuid_pk


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def _created() -> Mapped[dt.datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False
    )


def _updated() -> Mapped[dt.datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False
    )


class AgentWorkflow(Base):
    """One bounded objective and its versioned plan."""

    __tablename__ = "agent_workflows"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    plan_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    # What triggered this, and what the owner may see about why it exists at all.
    trigger_kind: Mapped[str | None] = mapped_column(String(64))
    trigger_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    initiative_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUGGEST", server_default="SUGGEST"
    )

    # The inspectable manifest of what context was included AND excluded. The
    # exclusions matter as much as the inclusions: they are how an owner checks
    # that a workflow did not reach into an unrelated part of their Orbit.
    context_manifest: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    success_criteria: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PRIVATE", server_default="PRIVATE"
    )
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("am_projects.id", ondelete="SET NULL")
    )

    budget_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cost_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_risk_class: Mapped[str] = mapped_column(
        String(24), nullable=False, default="R1_PRIVATE_DRAFT", server_default="R1_PRIVATE_DRAFT"
    )

    trace_id: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Per-workflow ledger allocator. Incremented under a row lock rather than
    # derived from MAX(sequence), which collided under concurrency and took the
    # domain mutation down with the failed event insert.
    event_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        Index("ix_agent_workflows_owner_state", "owner_user_id", "state"),
    )


class AgentStep(Base):
    """One node of the workflow DAG."""

    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default="PENDING"
    )
    # Dependencies are step keys, not row ids, so a re-planned workflow version
    # can be compiled without rewriting every reference.
    depends_on: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    role: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_key: Mapped[str | None] = mapped_column(String(120))
    tool_version: Mapped[str | None] = mapped_column(String(32))
    risk_class: Mapped[str] = mapped_column(
        String(24), nullable=False, default="R0_READ_ONLY", server_default="R0_READ_ONLY"
    )
    requested_capabilities: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    provider: Mapped[str | None] = mapped_column(String(48))
    model: Mapped[str | None] = mapped_column(String(80))
    input_refs: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict | None] = mapped_column(JSONB)
    verification_verdict: Mapped[str | None] = mapped_column(String(32))

    # Execution bookkeeping. `lease_expires_at` is what recovery uses to tell a
    # genuinely running step from one whose worker died holding it.
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    worker_id: Mapped[str | None] = mapped_column(String(120))
    # Reissued on every claim and every reclaim. Completion, failure and
    # heartbeat writes match on it, so a worker whose lease was reclaimed
    # cannot finish the attempt it no longer owns — worker_id alone would
    # still match its own name.
    execution_attempt: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int | None] = mapped_column(Integer)
    budget_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cost_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failure_code: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))

    artifact_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    queued_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        Index("ix_agent_steps_workflow_state", "workflow_id", "state"),
        Index("ix_agent_steps_owner_lease", "owner_user_id", "lease_expires_at"),
    )


class AgentApproval(Base):
    """An owner decision bound to one exact call.

    `argument_digest` is the load-bearing column. An approval authorises the
    precise redacted arguments the owner was shown; if anything about the call
    changes afterwards the digest no longer matches and the approval cannot be
    replayed against the new arguments.
    """

    __tablename__ = "agent_approvals"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="CASCADE")
    )

    tool_key: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    argument_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    # Binds the approval to the plan revision that produced it, so a re-plan
    # invalidates consent even when it regenerates an identical call.
    plan_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    call_version: Mapped[str | None] = mapped_column(Text)
    redacted_arguments: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    # What the owner is actually being asked to weigh.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str | None] = mapped_column(Text)
    risk_class: Mapped[str] = mapped_column(String(24), nullable=False)
    reversible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    scope_summary: Mapped[str | None] = mapped_column(Text)
    cost_ceiling_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="PENDING"
    )
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decided_note: Mapped[str | None] = mapped_column(Text)
    edited_arguments: Mapped[dict | None] = mapped_column(JSONB)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # What this row was before an invalidation pass revoked it. NULL for a row
    # that has never been invalidated.
    invalidated_from: Mapped[str | None] = mapped_column(String(20))
    invalidated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        Index("ix_agent_approvals_owner_decision", "owner_user_id", "decision"),
    )


class AgentRunEvent(Base):
    """Append-only account of what happened. Never updated, never deleted.

    A mutable history is a status field wearing an audit trail's clothes.
    """

    __tablename__ = "agent_run_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="SET NULL")
    )

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str | None] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    actor: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SYSTEM", server_default="SYSTEM"
    )
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        Index("ix_agent_run_events_workflow_seq", "workflow_id", "sequence", unique=True),
    )


class AgentCheckpoint(Base):
    """Resumable planner and agent run state. Never secrets."""

    __tablename__ = "agent_checkpoints"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="CASCADE")
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    state_blob: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Set by the redaction pass. A checkpoint that has not been through it is
    # not resumable, so an unredacted blob cannot be silently replayed.
    redacted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        Index("ix_agent_checkpoints_workflow_step", "workflow_id", "step_id"),
    )


class AgentToolCall(Base):
    """Every tool invocation, whether it was permitted or denied."""

    __tablename__ = "agent_tool_calls"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="SET NULL")
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_approvals.id", ondelete="SET NULL")
    )

    tool_key: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(24), nullable=False)
    argument_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    redacted_arguments: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    denial_reason: Mapped[str | None] = mapped_column(String(120))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        Index("ix_agent_tool_calls_owner_tool", "owner_user_id", "tool_key"),
    )


class AgentPolicy(Base):
    """Owner-configurable initiative and capability limits."""

    __tablename__ = "agent_policies"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()

    # NULL orbit and project means the account-level default.
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("am_projects.id", ondelete="CASCADE")
    )

    initiative_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUGGEST", server_default="SUGGEST"
    )
    max_risk_class: Mapped[str] = mapped_column(
        String(24), nullable=False, default="R1_PRIVATE_DRAFT", server_default="R1_PRIVATE_DRAFT"
    )
    # Two independent questions, two columns. `allowed_tools` still exists in the
    # database and is deliberately left unmapped: an ORM attribute that no longer
    # governs anything is a trap for the next reader, and removing the column
    # needs its own migration once nothing reads it.
    permitted_tools: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    auto_run_tools: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    denied_tools: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    daily_budget_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_proposals_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    cooldown_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=180, server_default=text("180")
    )
    quiet_hours: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        Index("ix_agent_policies_owner_scope", "owner_user_id", "orbit_id", "project_id"),
    )


class AgentEvaluation(Base):
    """Scored run quality. Separate from verification: a step can verify clean
    and still have been the wrong step to take."""

    __tablename__ = "agent_evaluations"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )

    dimension: Mapped[str] = mapped_column(String(48), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Owner correction outranks any model self-assessment.
    owner_marked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        Index("ix_agent_evaluations_workflow_dim", "workflow_id", "dimension"),
    )


class AgentDispatchOutbox(Base):
    """Dispatch intent, written in the same transaction as the decision.

    Publishing to a broker inside a transaction is a bug waiting for a rollback;
    publishing after commit with no record strands the step if the process dies
    in between. The row is the durable middle: committed with the decision,
    published afterwards by a dispatcher that can be restarted.

    The guarantee is at-least-once publication plus runtime claim idempotency,
    which together give exactly-once durable effect. `dispatch_key` prevents
    duplicate intent rows; it does not prevent duplicate publication.
    """

    __tablename__ = "agent_dispatch_outbox"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=False
    )

    dispatch_key: Mapped[str] = mapped_column(String(220), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="RETRYABLE", server_default="RETRYABLE"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Lease ownership: who holds it and until when. A dead lease is how recovery
    # tells a crashed dispatcher from a slow one.
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False
    )
    # Fencing token, reissued on every claim. `claimed_by` is an identity, not a
    # token: a stalled dispatcher whose lease was reclaimed would still match by
    # name and could acknowledge work it no longer owns.
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
    traceparent: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = _created()
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
