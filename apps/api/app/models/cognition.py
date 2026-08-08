"""Gate 2 cognitive substrate models (owner-bound; RLS enforced in DB)."""
import datetime as dt
import decimal
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Numeric

from app.db.base import Base
from app.models._mixins import uuid_pk, now_utc


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _created() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False)


class CognitiveEvent(Base):
    __tablename__ = "cognitive_events"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    event_kind: Mapped[str] = mapped_column(PGEnum('TALK_TURN', 'JOURNAL_ENTRY', 'PLAN_CREATED', 'PLAN_STEP', 'OUTCOME_REPORTED', 'TOOL_OBSERVATION', 'RESEARCH_DRAFT', 'SYSTEM_EVENT', 'USER_CORRECTION', 'MODEL_RESPONSE', 'EVALUATION_EVENT', 'RESEARCH_BRIEF_CREATED', 'RESEARCH_SOURCE_NOTE_ADDED', 'COMMUNITY_NOTE_CREATED', 'WEB_SIGNAL_QUESTION_STAGED', 'WEB_SIGNAL_NOTE_ADDED', name="cognitive_event_kind", create_type=False), nullable=False)
    content_text: Mapped[str | None] = mapped_column(String)
    structured_payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    source_ref: Mapped[str | None] = mapped_column(String)
    scope: Mapped[str] = mapped_column(PGEnum('EPHEMERAL', 'PRIVATE_ORBIT', 'SYSTEM_SHARED', 'LEARNING_CANDIDATE', name="memory_scope", create_type=False), default="PRIVATE_ORBIT", server_default="PRIVATE_ORBIT")
    salience: Mapped[float] = mapped_column(Float, default=0, server_default=text("0"))
    novelty: Mapped[float] = mapped_column(Float, default=0, server_default=text("0"))
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    parent_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    created_at = _created()


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    created_at = _created()


class Plan(Base):
    __tablename__ = "plans"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="ACTIVE", server_default="ACTIVE")
    created_at = _created()
    updated_at = _created()


class PlanStep(Base):
    __tablename__ = "plan_steps"
    id = uuid_pk()
    owner_user_id = _owner()
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="SET NULL"))
    created_at = _created()


class Decision(Base):
    __tablename__ = "decisions"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE"), nullable=False)
    statement: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="HELD", server_default="HELD")
    decided_at = _created()
    created_at = _created()


class OrbitReference(Base):
    __tablename__ = "orbit_references"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(PGEnum('REFERENCE', 'CONSTRAINT', 'OPEN_QUESTION', name="reference_kind", create_type=False), default="REFERENCE", server_default="REFERENCE")
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    created_at = _created()


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(String, nullable=False)
    hypothesis_text: Mapped[str] = mapped_column(String, nullable=False)
    alternative_hypotheses: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    prediction: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    status: Mapped[str] = mapped_column(PGEnum('PROPOSED', 'TESTING', 'SUPPORTED', 'REFUTED', 'INCONCLUSIVE', 'ARCHIVED', name="hypothesis_status", create_type=False), default="PROPOSED", server_default="PROPOSED")
    linked_refs: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    created_at = _created()
    updated_at = _created()


class Experiment(Base):
    __tablename__ = "experiments"
    id = uuid_pk()
    owner_user_id = _owner()
    hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hypotheses.id", ondelete="SET NULL"))
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    intervention: Mapped[str] = mapped_column(String, nullable=False)
    success_criteria: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    failure_criteria: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    scope: Mapped[str] = mapped_column(PGEnum('EPHEMERAL', 'PRIVATE_ORBIT', 'SYSTEM_SHARED', 'LEARNING_CANDIDATE', name="memory_scope", create_type=False), default="PRIVATE_ORBIT", server_default="PRIVATE_ORBIT")
    consent_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(PGEnum('DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETED', 'ABANDONED', name="experiment_status", create_type=False), default="DRAFT", server_default="DRAFT")
    created_at = _created()
    updated_at = _created()


class Outcome(Base):
    __tablename__ = "outcomes"
    id = uuid_pk()
    owner_user_id = _owner()
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="SET NULL"))
    plan_step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_steps.id", ondelete="SET NULL"))
    observed_result: Mapped[str] = mapped_column(String, nullable=False)
    structured_measurements: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    self_reported: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    confidence: Mapped[float | None] = mapped_column(Float)
    difference_from_prediction: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at = _created()


class ResearchDraft(Base):
    __tablename__ = "research_drafts"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="STAGED", server_default="STAGED")
    created_at = _created()


class SemanticClaim(Base):
    __tablename__ = "semantic_claims"
    id = uuid_pk()
    owner_user_id = _owner()
    claim_text: Mapped[str] = mapped_column(String, nullable=False)
    subject_ref: Mapped[str | None] = mapped_column(String)
    predicate: Mapped[str | None] = mapped_column(String)
    object_value: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    status: Mapped[str] = mapped_column(PGEnum('EMERGING', 'MIXED', 'SUPPORTED', 'DISPUTED', 'ARCHIVED', name="claim_status", create_type=False), default="EMERGING", server_default="EMERGING")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    counterevidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_evaluated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    id = uuid_pk()
    owner_user_id = _owner()
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("semantic_claims.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    outcome_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("outcomes.id", ondelete="SET NULL"))
    supports: Mapped[bool] = mapped_column(Boolean, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1, server_default=text("1"))
    rationale: Mapped[str | None] = mapped_column(String)
    created_at = _created()


class ModelRun(Base):
    __tablename__ = "model_runs"
    id = uuid_pk()
    owner_user_id = _owner()
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, default="talk", server_default="talk")
    status: Mapped[str] = mapped_column(String, default="COMPLETED", server_default="COMPLETED")
    input_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    output_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    run_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    response_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    usage: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    error: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at = _created()


class ModelRunSource(Base):
    __tablename__ = "model_run_sources"
    id = uuid_pk()
    owner_user_id = _owner()
    model_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    excerpt: Mapped[str | None] = mapped_column(String)
    rank: Mapped[float] = mapped_column(Float, default=0, server_default=text("0"))
    created_at = _created()


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    id = uuid_pk()
    owner_user_id = _owner()
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="SET NULL"))
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    checks: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at = _created()


class UserCorrection(Base):
    __tablename__ = "user_corrections"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "id", name="uq_user_corrections_owner_id"),
    )
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    target_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    correction_text: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    created_at = _created()


class MemoryCandidate(Base):
    __tablename__ = "memory_candidates"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    candidate_text: Mapped[str] = mapped_column(String, nullable=False)
    original_text: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    scope: Mapped[str] = mapped_column(PGEnum('EPHEMERAL', 'PRIVATE_ORBIT', 'SYSTEM_SHARED', 'LEARNING_CANDIDATE', name="memory_scope", create_type=False), default="LEARNING_CANDIDATE", server_default="LEARNING_CANDIDATE")
    memory_type: Mapped[str] = mapped_column(String(32), default="SEMANTIC", server_default="SEMANTIC")
    provenance_label: Mapped[str] = mapped_column(String(40), default="MODEL_GENERATED", server_default="MODEL_GENERATED")
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    sensitivity: Mapped[str] = mapped_column(String(24), default="PRIVATE", server_default="PRIVATE")
    created_by: Mapped[str] = mapped_column(String(16), default="MODEL", server_default="MODEL")
    source_object_ids: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String, default="CANDIDATE", server_default="CANDIDATE")
    review_note: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    approved_memory_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="SET NULL"))
    created_at = _created()
    updated_at = _created()


class Prediction(Base):
    __tablename__ = "predictions"
    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    statement: Mapped[str] = mapped_column(String, nullable=False)
    expected_observation: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String, default="OPEN", server_default="OPEN")
    outcome_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # ── Added by migration 0051 so a prediction is reviewable rather than a bare
    # sentence. `confidence` is constrained in the database to sit strictly
    # between 0 and 1: a prediction cannot be stored as certainty. ──
    assumptions: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 3))
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    review_by: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED, set only once an outcome
    #: has actually been observed — the database requires `resolved_at` with it.
    resolution: Mapped[str | None] = mapped_column(String(24))
    learning: Mapped[str | None] = mapped_column(String)
    created_at = _created()
