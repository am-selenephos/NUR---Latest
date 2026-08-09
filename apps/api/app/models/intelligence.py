"""Owner-scoped insight, timeline, and social-orbit ledgers."""

import datetime as dt
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.models._mixins import now_utc, uuid_pk


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created() -> Mapped[dt.datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        default=now_utc,
        nullable=False,
    )


class Person(Base):
    __tablename__ = "people"

    id = uuid_pk()
    owner_user_id = _owner()
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(240))
    relationship_type: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    privacy_scope: Mapped[str] = mapped_column(
        String(32), default="PRIVATE_ORBIT", server_default="PRIVATE_ORBIT", nullable=False
    )

    # ── Orbit relational columns (migration 0050). `people` is the Orbit person
    #    entity rather than a second table claiming the same thing. ──

    # The band, owner-owned. NULL means "not yet placed", which is the honest
    # state for someone imported from a Talk reference and not yet reviewed.
    orbit_level: Mapped[str | None] = mapped_column(String(16))
    # A suggestion is never an assignment. Both columns exist so the interface can
    # offer a move and explain it without having already performed it, and the
    # database refuses a suggestion with no reason.
    orbit_level_suggestion: Mapped[str | None] = mapped_column(String(16))
    orbit_level_suggestion_reason: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Kept apart deliberately: a generated summary must never overwrite the
    # owner's own words about a person.
    user_summary: Mapped[str | None] = mapped_column(Text)
    nur_summary: Mapped[str | None] = mapped_column(Text)
    relational_state: Mapped[str | None] = mapped_column(String(24))
    avatar_ref: Mapped[str | None] = mapped_column(String(400))

    # Permissions. Everything the owner has not granted defaults closed;
    # memory_allowed is the exception because a person the owner typed in is
    # already a durable private reference.
    memory_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    inference_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sharing_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    capsule_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_interaction_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    created_at = _created()
    updated_at = _created()


class OrbitMember(Base):
    __tablename__ = "orbit_members"

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(80), default="MEMBER", server_default="MEMBER", nullable=False)
    closeness_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    recent_activity_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    shared_goal_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    last_interaction_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()
    updated_at = _created()


class OrbitEvent(Base):
    __tablename__ = "orbit_events"

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(80))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=text("now()"), nullable=False
    )
    event_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at = _created()


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id = uuid_pk()
    owner_user_id = _owner()
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    time_kind: Mapped[str] = mapped_column(
        String(24), default="FUTURE", server_default="FUTURE", nullable=False
    )
    scheduled_for: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    system_slug: Mapped[str | None] = mapped_column(String(48))
    goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"))
    objective_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("objectives.id", ondelete="SET NULL"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("am_projects.id", ondelete="SET NULL"))
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"))
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="PLANNED", server_default="PLANNED", nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=50, server_default=text("50"), nullable=False)
    event_payload: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    # ── Added by migration 0052 so a Timeline entry carries a genuine truth
    # model rather than a single status string. `date_precision` is what stops
    # false clock precision: an item can be date-only, a window, before a date,
    # after a dependency, a flexible week, a horizon, or explicitly unscheduled —
    # and the database refuses to let an UNSCHEDULED row carry any date at all. ──
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    timezone_name: Mapped[str | None] = mapped_column(String(64))
    date_precision: Mapped[str] = mapped_column(
        String(24), default="EXACT", server_default="EXACT", nullable=False
    )
    earliest_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    latest_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: A quality verdict distinct from `status`. The database requires
    #: `actual_end_at` before this can be set — a verdict about something needs
    #: the something to have an end.
    completion_state: Mapped[str | None] = mapped_column(String(32))
    phase_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("timeline_phases.id", ondelete="SET NULL")
    )
    #: Same vocabulary as `MapAnnotation.visibility_scope` on purpose — one
    #: privacy word set across surfaces rather than a different one per page.
    visibility_scope: Mapped[str] = mapped_column(
        String(24), default="PRIVATE", server_default="PRIVATE", nullable=False
    )
    energy_type: Mapped[str | None] = mapped_column(String(24))
    created_at = _created()
    updated_at = _created()


class Insight(Base):
    __tablename__ = "insights"

    id = uuid_pk()
    owner_user_id = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL"))
    insight_type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[str] = mapped_column(String(48), default="DIRECT", server_default="DIRECT", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default=text("0.5"), nullable=False)
    valence: Mapped[str] = mapped_column(String(24), default="NEUTRAL", server_default="NEUTRAL", nullable=False)
    source_event_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    source_memory_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    source_research_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    affected_system_slug: Mapped[str | None] = mapped_column(String(48))
    affected_goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"))
    affected_project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("am_projects.id", ondelete="SET NULL"))
    affected_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"))
    evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    counter_evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False)
    what_nur_may_be_wrong_about: Mapped[str] = mapped_column(Text, nullable=False)
    positive_interpretation: Mapped[str | None] = mapped_column(Text)
    hard_interpretation: Mapped[str | None] = mapped_column(Text)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="CANDIDATE", server_default="CANDIDATE", nullable=False)
    correction: Mapped[str | None] = mapped_column(Text)
    provenance_label: Mapped[str] = mapped_column(
        String(64), default="INFERRED_OWNER_LEDGER", server_default="INFERRED_OWNER_LEDGER", nullable=False
    )
    pattern_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insight_patterns.id", ondelete="SET NULL")
    )
    parent_insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL")
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default="CANDIDATE", server_default="CANDIDATE", nullable=False
    )
    epistemic_state: Mapped[str] = mapped_column(
        String(32), default="INFERRED", server_default="INFERRED", nullable=False
    )
    insight_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    pattern_fingerprint: Mapped[str | None] = mapped_column(String(64))
    evidence_digest: Mapped[str | None] = mapped_column(String(64))
    time_scale: Mapped[str] = mapped_column(
        String(24), default="FAST", server_default="FAST", nullable=False
    )
    time_window_start: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    time_window_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source_domains: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    source_diversity: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    alternative_explanations: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    assumptions: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    contradictions: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    confidence_basis: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    quality_dimensions: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    quality_policy_version: Mapped[str] = mapped_column(
        String(48), default="agentic-insights-quality-v1",
        server_default="agentic-insights-quality-v1", nullable=False,
    )
    calibration_target: Mapped[str | None] = mapped_column(String(48))
    surfaced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    source_invalidated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()
    updated_at = _created()
