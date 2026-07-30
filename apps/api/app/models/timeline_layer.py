"""Timeline — the temporal-intelligence layer over canonical records.

Nothing here is a life entity twice over. `timeline_events` (intelligence.py) and
`scheduled_actions` (living.py) already are the Event/Action/Time-Block object
model, and this migration extended `timeline_events` in place rather than
shadowing it, the same call as `predictions` for Map. Dependencies are not a
table here either — they reuse `map_edges` from 0051, because the Timeline spec
itself says to reuse Map's dependency structure, and `map_edges` already has
`DEPENDS_ON` in its vocabulary, `timeline_event` in its ref-type vocabulary, and
the `user_confirmed` column that keeps "NUR must never mass-reschedule silently"
a stored guarantee.

What lives here is only what genuinely had no home: a period of time
(`TimelinePhase`), a repeating rhythm (`TimelineRecurrence`), an append-only
reschedule history (`TimelineReschedule`), a persisted reflection session
(`TimelineReview`), an external-calendar link that carries no live provider
(`TimelineExternalLink` — see the router module docstring for the honesty label
this carries at runtime), and one preferences row per owner
(`TimelinePreference`).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, text
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


# ── Shared vocabularies. Kept as data so the migration, the API and the tests
# all agree on what may be written. ──

STATUS_VALUES: tuple[str, ...] = (
    "PLANNED", "SCHEDULED", "IN_PROGRESS", "DUE", "COMPLETED",
    "PARTIALLY_COMPLETED", "MISSED", "RESCHEDULED", "CANCELLED", "OBSERVED",
    "PREDICTED", "INFERRED", "IMPORTED", "ARCHIVED",
)

#: The critical rule from §5: NUR must never *silently* convert one of these
#: into another. Enforced by having no generic "PATCH status" route — only named
#: action endpoints, each of which is the explicit conversion.
NEVER_SILENT_TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("PLANNED", "COMPLETED"),
    ("PREDICTED", "OBSERVED"),
    ("INFERRED", "OBSERVED"),
    ("IMPORTED", "OBSERVED"),
)

DATE_PRECISIONS: tuple[str, ...] = (
    "EXACT", "DATE_ONLY", "WINDOW", "BEFORE_DATE", "AFTER_DEPENDENCY",
    "FLEXIBLE_WEEK", "HORIZON", "UNSCHEDULED",
)

COMPLETION_STATES: tuple[str, ...] = (
    "SUCCESSFUL", "PARTIALLY_SUCCESSFUL", "COMPLETED_BUT_INEFFECTIVE",
    "ABANDONED_INTENTIONALLY", "FAILED", "UNKNOWN",
)

ENERGY_TYPES: tuple[str, ...] = (
    "LOW_ENERGY", "MODERATE_FOCUS", "DEEP_WORK", "SOCIAL", "EMOTIONAL",
    "PHYSICAL", "ADMINISTRATIVE",
)

#: Identical to `map_layer.ANNOTATION_SCOPES` on purpose.
VISIBILITY_SCOPES: tuple[str, ...] = ("PRIVATE", "SHARED_ORBIT", "CAPSULE_ELIGIBLE")

PHASE_STATUSES: tuple[str, ...] = ("UPCOMING", "ACTIVE", "COMPLETED", "ARCHIVED")

RECURRENCE_MODES: tuple[str, ...] = ("EXACT", "FLEXIBLE")

RESCHEDULE_SOURCES: tuple[str, ...] = ("OWNER", "NUR_SUGGESTED", "RIPPLE", "IMPORT_SYNC")

REVIEW_TYPES: tuple[str, ...] = ("DAILY", "WEEKLY", "MONTHLY", "PROJECT", "PREDICTION")

SYNC_DIRECTIONS: tuple[str, ...] = ("IMPORT_ONLY", "TWO_WAY")

SYNC_STATUSES: tuple[str, ...] = ("CONNECTED", "DISCONNECTED", "ERROR")

VIEW_MODES: tuple[str, ...] = ("FLOW", "CALENDAR", "HORIZONS", "REVIEW")

ZOOM_LEVELS: tuple[str, ...] = ("LIFE_YEAR", "QUARTER", "MONTH", "WEEK", "DAY")

LANE_GROUPINGS: tuple[str, ...] = (
    "UNIFIED", "SYSTEM", "PLAN", "PERSON", "OBJECT_TYPE", "STATUS",
)

#: The dependency flavour, carried in `map_edges.edge_metadata["dependency_kind"]`
#: rather than as a new top-level `edge_type`, so reusing `map_edges` costs no
#: migration to 0051's CHECK constraint.
DEPENDENCY_KINDS: tuple[str, ...] = (
    "FINISH_BEFORE", "START_AFTER", "CAN_OVERLAP", "REQUIRES_DECISION",
    "REQUIRES_PERSON", "REQUIRES_RESOURCE", "REQUIRES_OUTCOME",
)


class TimelinePhase(Base):
    """A period of time — a span, not a point.

    Nothing else in NUR models a *span* as a first-class thing: a Plan is a
    container of steps with no dates of its own. A Phase is what "NUR Beta
    Completion, July 15 – August 20" needs to exist as.
    """

    __tablename__ = "timeline_phases"

    id = uuid_pk()
    owner_user_id = _owner()
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), default="UPCOMING", server_default="UPCOMING", nullable=False
    )
    primary_system_slug: Mapped[str | None] = mapped_column(String(48))
    phase_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at = _created()
    updated_at = _created()


class TimelineRecurrence(Base):
    """A repeating rhythm attached to one template entry.

    `recurrence_mode = 'FLEXIBLE'` requires a `target_frequency` — "three times a
    week, not fixed days" is measured against a count, never forced onto specific
    weekdays it never claimed to have.
    """

    __tablename__ = "timeline_recurrences"

    id = uuid_pk()
    owner_user_id = _owner()
    timeline_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("timeline_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    recurrence_rule: Mapped[str] = mapped_column(Text, nullable=False)
    recurrence_mode: Mapped[str] = mapped_column(
        String(16), default="EXACT", server_default="EXACT", nullable=False
    )
    target_frequency: Mapped[int | None] = mapped_column(Integer)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    recurrence_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at = _created()
    updated_at = _created()


class TimelineReschedule(Base):
    """Append-only history. A move overwrites nothing.

    §29 requires the original time, the new time and the reason to remain
    auditable; this is the row that makes that true instead of asserted.
    """

    __tablename__ = "timeline_reschedules"

    id = uuid_pk()
    owner_user_id = _owner()
    timeline_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("timeline_events.id", ondelete="CASCADE"), nullable=False
    )
    previous_start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    previous_end_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    new_start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    new_end_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(
        String(24), default="OWNER", server_default="OWNER", nullable=False
    )
    created_at = _created()


class TimelineReview(Base):
    """A persisted reflection session over a period."""

    __tablename__ = "timeline_reviews"

    id = uuid_pk()
    owner_user_id = _owner()
    review_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    accepted_changes: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    created_at = _created()


class TimelineExternalLink(Base):
    """A calendar-provider link.

    Schema only. No provider is connected in this repository, and none is
    requested here — see the timeline router's module docstring for the label
    every response carries at runtime.
    """

    __tablename__ = "timeline_external_links"

    id = uuid_pk()
    owner_user_id = _owner()
    timeline_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("timeline_events.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    sync_direction: Mapped[str] = mapped_column(
        String(16), default="IMPORT_ONLY", server_default="IMPORT_ONLY", nullable=False
    )
    sync_status: Mapped[str] = mapped_column(
        String(24), default="DISCONNECTED", server_default="DISCONNECTED", nullable=False
    )
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    external_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at = _created()
    updated_at = _created()


class TimelinePreference(Base):
    """One row per owner: view mode, zoom level, lane grouping, filters."""

    __tablename__ = "timeline_preferences"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    view_mode: Mapped[str] = mapped_column(
        String(16), default="FLOW", server_default="FLOW", nullable=False
    )
    zoom_level: Mapped[str] = mapped_column(
        String(16), default="MONTH", server_default="MONTH", nullable=False
    )
    lane_grouping: Mapped[str] = mapped_column(
        String(16), default="UNIFIED", server_default="UNIFIED", nullable=False
    )
    filters: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    timezone_name: Mapped[str | None] = mapped_column(String(64))
    updated_at = _created()
