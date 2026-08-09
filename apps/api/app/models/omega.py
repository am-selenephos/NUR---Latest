"""NUR-Omega research layer models.

These tables are owner-bound and RLS-enforced in PostgreSQL. They store
structured research state only: no chain-of-thought, no recipient grant data,
and no hidden autonomous action state.
"""
import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.models._mixins import now_utc, uuid_pk


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _created() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False)


def _updated() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False)


class OmegaExperience(Base):
    __tablename__ = "omega_experiences"
    __table_args__ = (
        CheckConstraint("provenance_label IN ('OWNER_WRITTEN','OBSERVED_OUTCOME','MODEL_GENERATED','SYSTEM_MEASURED','USER_CORRECTION')", name="ck_omega_experience_provenance"),
        CheckConstraint("sensitivity IN ('LOW','PRIVATE','SENSITIVE','SECRET_EXCLUDED')", name="ck_omega_experience_sensitivity"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    event_kind: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False, default="PRIVATE_ORBIT", server_default="PRIVATE_ORBIT")
    language_tag: Mapped[str] = mapped_column(String, default="und", server_default="und")
    summary: Mapped[str] = mapped_column(String, nullable=False)
    raw_ref: Mapped[dict | None] = mapped_column(JSONB)
    provenance_label: Mapped[str] = mapped_column(String, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String, nullable=False, default="PRIVATE", server_default="PRIVATE")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default=text("1.0"))
    source_domain: Mapped[str] = mapped_column(
        String(48), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    explicitness: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SYSTEM_OBSERVED", server_default="SYSTEM_OBSERVED"
    )
    retention_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SOURCE_BOUND", server_default="SOURCE_BOUND"
    )
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc, server_default=text("now()")
    )
    invalidated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at = _created()


class OmegaClaim(Base):
    __tablename__ = "omega_claims"
    __table_args__ = (
        CheckConstraint("claim_type IN ('FACT','PREFERENCE','CONSTRAINT','DECISION','PATTERN','RISK','HYPOTHESIS','UNKNOWN')", name="ck_omega_claim_type"),
        CheckConstraint("truth_status IN ('OBSERVED','INFERRED','HYPOTHESIS','CONTRADICTED','SUPERSEDED','RETIRED')", name="ck_omega_claim_truth"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    claim_text: Mapped[str] = mapped_column(String, nullable=False)
    claim_type: Mapped[str] = mapped_column(String, nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    truth_status: Mapped[str] = mapped_column(String, nullable=False, default="HYPOTHESIS", server_default="HYPOTHESIS")
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    support_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_supported_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_contradicted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()
    updated_at = _updated()


class OmegaEvidenceEdge(Base):
    __tablename__ = "omega_evidence_edges"
    __table_args__ = (
        CheckConstraint("evidence_kind IN ('EXPERIENCE','OUTCOME','CORRECTION','MODEL_RUN','DECISION','REFERENCE','PLAN_STEP')", name="ck_omega_evidence_kind"),
        CheckConstraint("relation IN ('SUPPORTS','CONTRADICTS','QUALIFIES','SUPERSEDES','CAUSED_BY','DERIVED_FROM')", name="ck_omega_evidence_relation"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omega_claims.id", ondelete="CASCADE"), nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String, nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation: Mapped[str] = mapped_column(String, nullable=False)
    strength: Mapped[float] = mapped_column(Float, default=1.0, server_default=text("1.0"))
    note: Mapped[str | None] = mapped_column(String)
    created_at = _created()


class OmegaContradiction(Base):
    __tablename__ = "omega_contradictions"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','REVIEWED','RESOLVED','ACCEPTED_PARADOX','RETIRED')", name="ck_omega_contradiction_status"),
        CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_omega_contradiction_severity"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    claim_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omega_claims.id", ondelete="CASCADE"), nullable=False)
    claim_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omega_claims.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN", server_default="OPEN")
    severity: Mapped[str] = mapped_column(String, nullable=False, default="MEDIUM", server_default="MEDIUM")
    description: Mapped[str] = mapped_column(String, nullable=False)
    proposed_resolution: Mapped[str | None] = mapped_column(String)
    resolved_by_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = _created()
    updated_at = _updated()


class OmegaWorkspaceFrame(Base):
    __tablename__ = "omega_workspace_frames"
    __table_args__ = (
        CheckConstraint("status IN ('CREATED','USED','EVALUATED','RETIRED')", name="ck_omega_workspace_status"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    task_mode: Mapped[str] = mapped_column(String, nullable=False)
    trigger_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL"))
    active_goal: Mapped[str | None] = mapped_column(String)
    active_question: Mapped[str] = mapped_column(String, nullable=False)
    attention_items: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    retrieved_claim_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, server_default=text("ARRAY[]::uuid[]"))
    retrieved_experience_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, server_default=text("ARRAY[]::uuid[]"))
    active_hypothesis_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, server_default=text("ARRAY[]::uuid[]"))
    active_contradiction_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, server_default=text("ARRAY[]::uuid[]"))
    risk_flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("ARRAY[]::text[]"))
    scope_statement: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="CREATED", server_default="CREATED")
    created_at = _created()


class OmegaPrediction(Base):
    __tablename__ = "omega_predictions"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','CONFIRMED','DISCONFIRMED','PARTIAL','EXPIRED','RETIRED')", name="ck_omega_prediction_status"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="SET NULL"))
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("omega_claims.id", ondelete="SET NULL"))
    plan_step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_steps.id", ondelete="SET NULL"))
    prediction_text: Mapped[str] = mapped_column(String, nullable=False)
    expected_observation: Mapped[str] = mapped_column(String, nullable=False)
    metric: Mapped[str | None] = mapped_column(String)
    time_window: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN", server_default="OPEN")
    outcome_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("outcomes.id", ondelete="SET NULL"))
    prediction_error: Mapped[float | None] = mapped_column(Float)
    created_at = _created()
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class OmegaLearningProposal(Base):
    __tablename__ = "omega_learning_proposals"
    __table_args__ = (
        CheckConstraint("proposal_kind IN ('RETRIEVAL_WEIGHT','PROMPT_RULE','UI_HINT','MEMORY_POLICY','HYPOTHESIS_POLICY','PLANNING_HEURISTIC')", name="ck_omega_learning_kind"),
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH','FORBIDDEN')", name="ck_omega_learning_risk"),
        CheckConstraint("status IN ('PROPOSED','SHADOW_TESTING','APPROVED','REJECTED','ROLLED_BACK')", name="ck_omega_learning_status"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    proposal_kind: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(String, nullable=False)
    supporting_evaluation_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, server_default=text("ARRAY[]::uuid[]"))
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="LOW", server_default="LOW")
    status: Mapped[str] = mapped_column(String, nullable=False, default="PROPOSED", server_default="PROPOSED")
    approved_by_owner: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    created_at = _created()
    updated_at = _updated()


class OmegaConsolidationRun(Base):
    __tablename__ = "omega_consolidation_runs"
    __table_args__ = (
        CheckConstraint("run_kind IN ('DAILY','MANUAL','ORBIT','POST_OUTCOME')", name="ck_omega_consolidation_kind"),
        CheckConstraint("status IN ('STARTED','COMPLETED','FAILED')", name="ck_omega_consolidation_status"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    run_kind: Mapped[str] = mapped_column(String, nullable=False, default="MANUAL", server_default="MANUAL")
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    input_counts: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_claims: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    updated_claims: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    contradictions_found: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    predictions_resolved: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    proposals_created: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="STARTED", server_default="STARTED")
    created_at = _created()
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String)


class OmegaReviewQueue(Base):
    __tablename__ = "omega_review_queue"
    __table_args__ = (
        CheckConstraint("candidate_claim_type IN ('FACT','PREFERENCE','CONSTRAINT','DECISION','PATTERN','RISK','HYPOTHESIS','UNKNOWN')", name="ck_omega_review_claim_type"),
        CheckConstraint("candidate_truth_status IN ('INFERRED','HYPOTHESIS')", name="ck_omega_review_truth"),
        CheckConstraint("sensitivity IN ('LOW','PRIVATE','SENSITIVE','SECRET_EXCLUDED')", name="ck_omega_review_sensitivity"),
        CheckConstraint("status IN ('PENDING_REVIEW','APPROVED','REJECTED','EDITED')", name="ck_omega_review_status"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    experience_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("omega_experiences.id", ondelete="SET NULL"))
    candidate_claim_text: Mapped[str] = mapped_column(String, nullable=False)
    candidate_claim_type: Mapped[str] = mapped_column(String, nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    candidate_truth_status: Mapped[str] = mapped_column(String, nullable=False, default="HYPOTHESIS", server_default="HYPOTHESIS")
    sensitivity: Mapped[str] = mapped_column(String, nullable=False, default="SENSITIVE", server_default="SENSITIVE")
    reason: Mapped[str] = mapped_column(String, nullable=False)
    model_candidate: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING_REVIEW", server_default="PENDING_REVIEW")
    created_claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("omega_claims.id", ondelete="SET NULL"))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()
    updated_at = _updated()
