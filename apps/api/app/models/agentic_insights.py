"""Owner-scoped persistence for Agentic Insights projection and review."""

import datetime as dt
import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
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
        DateTime(timezone=True), server_default=text("now()"), default=now_utc,
        nullable=False,
    )


class InsightPattern(Base):
    __tablename__ = "insight_patterns"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "fingerprint", name="uq_insight_patterns_owner_fingerprint"),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(48), nullable=False)
    time_scale: Mapped[str] = mapped_column(String(24), nullable=False)
    source_domains: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    feature_summary: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    support_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    counter_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    source_diversity: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    first_observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", server_default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at = _created()
    updated_at = _created()


class InsightEvidenceRelation(Base):
    __tablename__ = "insight_evidence_relations"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "insight_id", "source_kind", "source_id", "relation",
            "insight_version", name="uq_insight_evidence_relation",
        ),
    )

    id = uuid_pk()
    owner_user_id = _owner()
    insight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="CASCADE"), nullable=False
    )
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("omega_experiences.id", ondelete="SET NULL")
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cognitive_events.id", ondelete="SET NULL")
    )
    source_domain_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_events.id", ondelete="SET NULL")
    )
    source_insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL")
    )
    source_feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insight_feedback.id", ondelete="SET NULL")
    )
    source_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_domain: Mapped[str] = mapped_column(String(48), nullable=False)
    relation: Mapped[str] = mapped_column(String(24), nullable=False)
    provenance_label: Mapped[str] = mapped_column(String(64), nullable=False)
    explicitness: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"))
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    evidence_summary: Mapped[str | None] = mapped_column(String(1000))
    source_occurred_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    insight_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    invalidated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(160))
    created_at = _created()


class InsightFeedback(Base):
    __tablename__ = "insight_feedback"

    id = uuid_pk()
    owner_user_id = _owner()
    insight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    correction_text: Mapped[str | None] = mapped_column(Text)
    prior_lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    next_lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_digest: Mapped[str | None] = mapped_column(String(64))
    insight_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_correction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_corrections.id", ondelete="SET NULL")
    )
    created_at = _created()


class InsightProjectionCheckpoint(Base):
    __tablename__ = "insight_projection_checkpoints"

    id = uuid_pk()
    owner_user_id = _owner()
    last_cognitive_event_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_cognitive_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_domain_event_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_domain_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    pending_event_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    pending_since: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    next_eligible_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(24))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    claimed_by: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default=text("5"))
    last_error_class: Mapped[str | None] = mapped_column(String(120))
    created_at = _created()
    updated_at = _created()


class InsightProjectionRun(Base):
    __tablename__ = "insight_projection_runs"

    id = uuid_pk()
    owner_user_id = _owner()
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    run_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="STARTED", server_default="STARTED")
    max_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_observations: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    invalidated_relations: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    generated_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    surfaced_insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL")
    )
    self_insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL")
    )
    suppressed_insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL")
    )
    suppressed_reason: Mapped[str | None] = mapped_column(String(80))
    quality_policy_version: Mapped[str] = mapped_column(String(48), nullable=False)
    input_counts: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    error_class: Mapped[str | None] = mapped_column(String(120))
    created_at = _created()
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class WhyChangedRecordRow(Base):
    __tablename__ = "why_changed_records"

    id = uuid_pk()
    owner_user_id = _owner()
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    previous_version: Mapped[str | None] = mapped_column(String)
    new_version: Mapped[str | None] = mapped_column(String)
    change_class: Mapped[str] = mapped_column(String, nullable=False)
    trigger: Mapped[str] = mapped_column(String, default="", server_default="")
    supporting_evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    counter_evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    owner_correction: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    model_version: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)
    policy_version: Mapped[str | None] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String, default="system", server_default="system")
    affected_future_behavior: Mapped[str] = mapped_column(String, default="", server_default="")
    rollback_target: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()")
    )
    created_at = _created()
