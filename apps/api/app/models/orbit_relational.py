"""The Orbit relational world: groups, edges, layout, threads, insights, signals.

These sit beside `Person` and `Orbit` rather than replacing them. `people` is
still the person entity — it gained the relational columns it lacked in migration
0050 — and `orbits` is still the context container. What lives here is the
structure neither of them expressed: which people are tied to which, what a group
is when it is not merely a container, where a node was dragged to, which threads
are open, and — most carefully — which relational readings are the owner's and
which are inferred.

`OrbitRelationalSignal.basis` is the column the whole surface depends on. A
signal that cannot say whether the owner stated it, a system measured it, or a
model guessed it is a relational assertion wearing a fact's clothes, so the
schema refuses to store one, and refuses an inferred signal with no evidence.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, Numeric, SmallInteger, String, Text, text
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


# ── Orbit levels. The band a person occupies, owner-owned. ──
ORBIT_LEVELS: tuple[str, ...] = ("INNER", "NEAR", "OUTER", "PERIPHERAL", "DORMANT")

RELATIONAL_STATES: tuple[str, ...] = (
    "STABLE", "DEEPENING", "RECONNECTING", "DRIFTING",
    "UNCLEAR", "TENSE", "REPAIRING", "DORMANT",
)

GROUP_PRIVACY_MODES: tuple[str, ...] = (
    "PRIVATE_ORGANIZER", "SHARED_CONTEXT", "GROUP_NUR", "WITNESS_ONLY",
)

THREAD_STATUSES: tuple[str, ...] = (
    "ACTIVE", "WAITING_ON_YOU", "WAITING_ON_OTHERS",
    "CONSULTATION", "RESOLVED", "DORMANT",
)

SIGNAL_KINDS: tuple[str, ...] = ("CONNECTION", "TRUST", "MOMENTUM", "TENSION")

# The three bases a relational reading can have. Kept as data so the API and the
# tests share one definition of what may be written.
SIGNAL_BASES: tuple[str, ...] = ("USER_STATED", "OBSERVED", "NUR_INFERRED")

CONTEXT_VISIBILITY: tuple[str, ...] = (
    "PRIVATE", "ORBIT_SHARED", "GROUP_SHARED", "CAPSULE_SHARED", "SYSTEM_SHARED",
)

MEMBER_CONSENT_SCOPES: tuple[str, ...] = ("CONTEXT_ONLY", "SHARED_MEMORY", "WITNESS_ONLY")


class OrbitGroup(Base):
    """A circle, not a large person.

    Groups are rendered as small constellations and reason about *shared* context
    only. `privacy_mode` is what decides how much of that is possible, and
    `group_nur_enabled` cannot be true while the mode is still a private
    organizer view — the database enforces that pairing, because it gates what
    the group assistant is allowed to read.
    """

    __tablename__ = "orbit_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    orbit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbits.id", ondelete="SET NULL")
    )

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    group_type: Mapped[str] = mapped_column(
        String(48), nullable=False, default="CIRCLE", server_default="CIRCLE"
    )
    privacy_mode: Mapped[str] = mapped_column(
        String(32), nullable=False,
        default="PRIVATE_ORGANIZER", server_default="PRIVATE_ORGANIZER",
    )
    shared_memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    group_nur_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    system_slug: Mapped[str | None] = mapped_column(String(48))
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()


class OrbitGroupMember(Base):
    """One person's membership, with that person's own consent scope.

    Consent is per member rather than per group: one member agreeing to shared
    memory does not speak for another, and a witness-only member contributes
    without leaving durable shared memory behind.
    """

    __tablename__ = "orbit_group_members"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbit_groups.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(80), nullable=False, default="MEMBER", server_default="MEMBER"
    )
    consent_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CONTEXT_ONLY", server_default="CONTEXT_ONLY"
    )
    joined_at: Mapped[dt.datetime] = _created()


class OrbitRelationship(Base):
    """An edge: person to person, or person to group.

    `strength_user` is the owner's own reading and the derived scores beside it
    never overwrite it. Exactly one target is set, so the renderer always knows
    what it is drawing a line to.
    """

    __tablename__ = "orbit_relationships"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    source_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    target_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE")
    )
    target_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbit_groups.id", ondelete="CASCADE")
    )

    relationship_type: Mapped[str | None] = mapped_column(String(80))
    strength_user: Mapped[int | None] = mapped_column(SmallInteger)
    activity_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    reciprocity_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    momentum_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    tension_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 3))
    evidence_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()


class OrbitContextLink(Base):
    """A link from a person or group to something already in NUR.

    `link_reason` is not decoration. A context item whose presence the owner
    cannot account for is one they cannot meaningfully unlink, so the reason
    travels with the link, and `visibility_scope` states what sharing it permits.
    """

    __tablename__ = "orbit_context_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE")
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbit_groups.id", ondelete="CASCADE")
    )
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    link_reason: Mapped[str | None] = mapped_column(Text)
    visibility_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PRIVATE", server_default="PRIVATE"
    )
    created_at: Mapped[dt.datetime] = _created()


class OrbitLayoutNode(Base):
    """Where the owner put a node, per viewport.

    Layout is keyed by viewport so a desktop arrangement does not dictate mobile,
    and `pinned` distinguishes a deliberate placement from one the field is free
    to relax.
    """

    __tablename__ = "orbit_layout_nodes"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    viewport: Mapped[str] = mapped_column(
        String(24), nullable=False, default="desktop", server_default="desktop"
    )
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    collapsed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    updated_at: Mapped[dt.datetime] = _updated()


class OrbitThread(Base):
    """An open relational thread.

    `WAITING_ON_YOU` and `WAITING_ON_OTHERS` are separate stored states rather
    than a rendering decision, because "who is blocked" is the question the
    Threads view exists to answer.
    """

    __tablename__ = "orbit_threads"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE")
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbit_groups.id", ondelete="CASCADE")
    )
    topic: Mapped[str] = mapped_column(String(400), nullable=False)
    participants: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    last_event_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_summary: Mapped[str | None] = mapped_column(Text)
    open_decision: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL")
    )
    system_slug: Mapped[str | None] = mapped_column(String(48))
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()


class OrbitRelationalInsight(Base):
    """A candidate relational reading, and where it might be wrong.

    `may_be_wrong_about` is NOT NULL with no default and a non-blank CHECK. An
    insight about a person that cannot state its own doubt is precisely the
    unlabelled relational guess this surface must not present, so it cannot be
    stored — the hardest sentence is a required field rather than an option.
    """

    __tablename__ = "orbit_relational_insights"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE")
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orbit_groups.id", ondelete="CASCADE")
    )
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 3))
    alternative_interpretation: Mapped[str | None] = mapped_column(Text)
    recommended_move: Mapped[str | None] = mapped_column(Text)
    may_be_wrong_about: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="CANDIDATE", server_default="CANDIDATE"
    )
    created_at: Mapped[dt.datetime] = _created()


class OrbitRelationalSignal(Base):
    """Connection, Trust, Momentum or Tension — and where it came from.

    `basis` is the load-bearing column: USER_STATED is the owner's own word,
    OBSERVED is something the system measured, NUR_INFERRED is a guess. They are
    rendered differently and consented to differently, and an inferred signal
    with an empty `evidence` array is rejected by the database, so nothing can
    reach "Why is NUR showing this?" with nothing behind it.

    `contradictory_evidence` is stored on the same row as `evidence` so the case
    against a reading is exactly as durable as the case for it.
    """

    __tablename__ = "orbit_relational_signals"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = _owner()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    signal_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[int | None] = mapped_column(SmallInteger)
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 3))
    basis: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    contradictory_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        Index("ix_orbit_signals_person_lookup", "person_id", "signal_kind"),
    )


__all__ = [
    "CONTEXT_VISIBILITY",
    "GROUP_PRIVACY_MODES",
    "MEMBER_CONSENT_SCOPES",
    "ORBIT_LEVELS",
    "RELATIONAL_STATES",
    "SIGNAL_BASES",
    "SIGNAL_KINDS",
    "THREAD_STATUSES",
    "OrbitContextLink",
    "OrbitGroup",
    "OrbitGroupMember",
    "OrbitLayoutNode",
    "OrbitRelationalInsight",
    "OrbitRelationalSignal",
    "OrbitRelationship",
    "OrbitThread",
]
