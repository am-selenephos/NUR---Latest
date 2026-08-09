"""Gate 3 Shared Orbit models (amendment §3 verbatim shapes)."""
import datetime as dt
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.models._mixins import uuid_pk, now_utc


def _created() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"), default=now_utc, nullable=False)


class OrbitSource(Base):
    __tablename__ = "orbit_sources"
    id = uuid_pk()
    orbit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_kind: Mapped[str] = mapped_column(PGEnum('COGNITIVE_EVENT', 'JOURNAL_ENTRY', 'PLAN', 'PLAN_STEP', 'OUTCOME', 'REFERENCE', 'DECISION', 'RESEARCH_DRAFT', name="orbit_source_kind", create_type=False), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    inclusion_mode: Mapped[str] = mapped_column(PGEnum('FULL', 'SUMMARY_ONLY', 'METADATA_ONLY', name="inclusion_mode", create_type=False), default="FULL", server_default="FULL")
    created_at = _created()


class ContextCapsule(Base):
    __tablename__ = "context_capsules"
    id = uuid_pk()
    orbit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    recipient_instructions: Mapped[str | None] = mapped_column(String)
    visibility: Mapped[str] = mapped_column(PGEnum('NAMED_RECIPIENTS_ONLY', 'LINK_WITH_PASSCODE', name="capsule_visibility", create_type=False), default="NAMED_RECIPIENTS_ONLY", server_default="NAMED_RECIPIENTS_ONLY")
    capability: Mapped[str] = mapped_column(PGEnum('READ_ONLY', 'ASK_SCOPED_QUESTIONS', 'COMMENT_ONLY', name="capsule_capability", create_type=False), default="READ_ONLY", server_default="READ_ONLY")
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at = _created()
    updated_at = _created()


class CapsuleSource(Base):
    __tablename__ = "capsule_sources"
    id = uuid_pk()
    capsule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("context_capsules.id", ondelete="CASCADE"), nullable=False)
    capsule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    orbit_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orbit_sources.id", ondelete="CASCADE"), nullable=False)
    included_representation: Mapped[str] = mapped_column(PGEnum('FULL', 'OWNER_APPROVED_SUMMARY', 'METADATA_ONLY', name="included_representation", create_type=False), default="FULL", server_default="FULL")
    created_at = _created()


class CapsuleGrant(Base):
    __tablename__ = "capsule_grants"
    id = uuid_pk()
    capsule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("context_capsules.id", ondelete="CASCADE"), nullable=False)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    recipient_email_hash: Mapped[str | None] = mapped_column(String)
    capability: Mapped[str] = mapped_column(PGEnum('READ_ONLY', 'ASK_SCOPED_QUESTIONS', 'COMMENT_ONLY', name="capsule_capability", create_type=False), default="READ_ONLY", server_default="READ_ONLY")
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()


class CapsuleAccessEvent(Base):
    __tablename__ = "capsule_access_events"
    id = uuid_pk()
    capsule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("context_capsules.id", ondelete="CASCADE"), nullable=False)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("capsule_grants.id", ondelete="SET NULL"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_kind: Mapped[str] = mapped_column(PGEnum('VIEWED', 'QUESTION_ASKED', 'ANSWER_SHOWN', 'COMMENT_CREATED', 'EXPORT_ATTEMPTED', 'REVOKED', 'EXPIRED', name="access_event_kind", create_type=False), nullable=False)
    created_at = _created()
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"))


class CapsuleQuestion(Base):
    __tablename__ = "capsule_questions"
    id = uuid_pk()
    capsule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("context_capsules.id", ondelete="CASCADE"), nullable=False)
    grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capsule_grants.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(PGEnum('PENDING', 'ANSWERED', 'NOT_AVAILABLE', 'REJECTED_BY_POLICY', name="question_status", create_type=False), default="PENDING", server_default="PENDING")
    created_at = _created()


class CapsuleAnswer(Base):
    __tablename__ = "capsule_answers"
    id = uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capsule_questions.id", ondelete="CASCADE"), nullable=False)
    answer_text: Mapped[str] = mapped_column(String, nullable=False)
    answer_mode: Mapped[str] = mapped_column(PGEnum('DIRECT_STATEMENT', 'APPROVED_CONTEXT_SUMMARY', 'INFERENCE', 'NOT_AVAILABLE', name="answer_mode", create_type=False), nullable=False)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric)
    policy_explanation: Mapped[str | None] = mapped_column(String)
    created_at = _created()


class CollaborationOutcome(Base):
    __tablename__ = "collaboration_outcomes"
    id = uuid_pk()
    capsule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("context_capsules.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    onboarding_faster: Mapped[bool | None] = mapped_column(Boolean)
    decisions_respected: Mapped[bool | None] = mapped_column(Boolean)
    answered_correctly: Mapped[bool | None] = mapped_column(Boolean)
    time_saved_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String)
    created_at = _created()
