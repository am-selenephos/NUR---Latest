"""Map — the compositional layer over canonical NUR records.

Nothing here is a life entity. Systems, goals, objectives, plans, plan steps,
actions, decisions, outcomes, predictions, research, signals, people and timeline
events are all canonical and live elsewhere; these seven tables only add what
Map genuinely needs and nowhere had: saved views, owner-positioned layout, the
semantic edges the owner drew or accepted, candidate suggestions awaiting review,
notes, the *options* of a decision, and a blocker that can actually be addressed.

Two of these deserve their existence stated plainly, because "reuse first" would
otherwise be the wrong call:

`MapDecisionOption` — the canonical `decisions` row stores a statement, a
rationale and a status. It has no options, so there is nothing to compare, no
reversibility, and no way to record which fork was taken. Options are the
missing half of a decision, not a second decision.

`MapBlocker` — today a blocker in the graph is any `system_actions` row whose
status is MISSED, or a bare string inside `system_diagnostics.blockers`. Neither
can say what it affects, what evidence it rests on, whether the owner agrees it
is real, or how it was resolved. A blocker that cannot be pointed at cannot be
removed.

`basis` on `MapBlocker` carries the same weight `basis` carries on an Orbit
signal, and the same schema rule: an inference must name its evidence, and an
inferred emotional, psychological or relational blocker cannot be asserted as
OPEN at all — it waits at PROPOSED for the owner.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Numeric

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


# ── Shared vocabularies. Kept as data so the migration, the API, the graph
# composer and the tests all agree on what may be written. ──

VIEW_TYPES: tuple[str, ...] = ("UNIVERSE", "FOCUS", "PATHS", "DECISIONS")

#: Canonical entity kinds a Map row may point at. Mirrors `REF_TYPES` in
#: migration 0051; a value absent here is rejected by a CHECK constraint.
REF_TYPES: tuple[str, ...] = (
    "nur",
    "system",
    "goal",
    "objective",
    "plan",
    "plan_step",
    "action",
    "scheduled_action",
    "decision",
    "decision_option",
    "blocker",
    "outcome",
    "prediction",
    "insight",
    "person",
    "group",
    "orbit",
    "timeline_event",
    "research_source",
    "web_signal",
    "project",
    "project_task",
    "journal_entry",
    "experiment",
    "hypothesis",
)

#: The semantic relationships Map understands. An edge with no meaning is a line.
EDGE_TYPES: tuple[str, ...] = (
    "PART_OF",
    "DEPENDS_ON",
    "SUPPORTS",
    "ENABLES",
    "BLOCKS",
    "CONTRADICTS",
    "LEADS_TO",
    "EVIDENCE_FOR",
    "INVOLVES",
    "PREDICTED_TO_PRODUCE",
)

EDGE_DIRECTIONS: tuple[str, ...] = ("DIRECTED", "BIDIRECTIONAL")

SUGGESTION_TYPES: tuple[str, ...] = (
    "CONNECTION",
    "DEPENDENCY",
    "BLOCKER",
    "CONFLICTING_GOAL",
    "DUPLICATE_PLAN",
    "STALE_ASSUMPTION",
    "PATH",
    "SYSTEM_IMBALANCE",
)

SUGGESTION_STATUSES: tuple[str, ...] = ("PENDING", "ACCEPTED", "REJECTED", "SUPERSEDED")

ANNOTATION_SCOPES: tuple[str, ...] = ("PRIVATE", "SHARED_ORBIT", "CAPSULE_ELIGIBLE")

#: How costly it is to walk an action back. Deliberately words, not a number —
#: §19 says avoid fake numerical precision, and reversibility is exactly the kind
#: of judgement a decimal would falsely dignify.
REVERSIBILITY: tuple[str, ...] = ("EASY", "COSTLY", "MOSTLY_IRREVERSIBLE")

#: The three bases a blocker reading can have — identical vocabulary to an Orbit
#: relational signal, on purpose: the owner should learn one word set, not two.
BLOCKER_BASES: tuple[str, ...] = ("USER_STATED", "OBSERVED", "NUR_INFERRED")

BLOCKER_CATEGORIES: tuple[str, ...] = (
    "PRACTICAL",
    "TECHNICAL",
    "FINANCIAL",
    "TIME",
    "KNOWLEDGE",
    "EMOTIONAL",
    "PSYCHOLOGICAL",
    "RELATIONAL",
    "HEALTH",
    "EXTERNAL",
)

#: The categories NUR may never assert unaided. §20: do not label an emotional or
#: psychological condition as fact. Enforced by
#: `ck_map_blocker_sensitive_needs_owner`, not merely by convention here.
SENSITIVE_BLOCKER_CATEGORIES: tuple[str, ...] = (
    "EMOTIONAL",
    "PSYCHOLOGICAL",
    "RELATIONAL",
)

BLOCKER_STATUSES: tuple[str, ...] = (
    "PROPOSED",
    "OPEN",
    "RESOLVED",
    "CHALLENGED",
    "DISMISSED",
)

#: The verdict an observed outcome delivers on a prediction. Stored on the
#: canonical `predictions` row, which 0051 extended rather than shadowed.
PREDICTION_RESOLUTIONS: tuple[str, ...] = (
    "CONFIRMED",
    "PARTIALLY_CONFIRMED",
    "CONTRADICTED",
)


class MapView(Base):
    """A saved way of looking at the map.

    A FOCUS view is focus *on* something, so the database refuses one without a
    root entity — otherwise it would render the whole Universe while claiming to
    be focused, which is the kind of quiet lie that makes a view untrustworthy.
    """

    __tablename__ = "map_views"

    id = uuid_pk()
    owner_user_id = _owner()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    view_type: Mapped[str] = mapped_column(String(24), nullable=False)
    root_entity_type: Mapped[str | None] = mapped_column(String(32))
    root_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    filters: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at = _created()
    updated_at = _created()


class MapLayout(Base):
    """Where the owner put a node.

    Position is presentation and nothing else. Moving a goal near Money does not
    make it a Money goal — that stays an explicit, confirmable change — so this
    table carries coordinates and never a System, a parent or a relationship.
    """

    __tablename__ = "map_layouts"

    id = uuid_pk()
    owner_user_id = _owner()
    map_view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("map_views.id", ondelete="CASCADE"), nullable=False
    )
    viewport_key: Mapped[str] = mapped_column(
        String(32), default="desktop", server_default="desktop", nullable=False
    )
    node_ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    node_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    collapsed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    layer: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    updated_at = _created()


class MapEdge(Base):
    """A semantic relationship, with its provenance attached.

    `user_confirmed` is the whole point. NUR may propose an edge, but a proposal
    is not part of the map: an unconfirmed edge must name what it was inferred
    from, and the graph renders it as a candidate rather than as structure. That
    keeps "never infer and permanently create a relationship without user
    acceptance" a column rather than a code path someone can forget.
    """

    __tablename__ = "map_edges"

    id = uuid_pk()
    owner_user_id = _owner()
    source_ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(16), default="DIRECTED", server_default="DIRECTED", nullable=False
    )
    user_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    inference_source: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 3))
    note: Mapped[str | None] = mapped_column(Text)
    edge_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at = _created()
    updated_at = _created()


class MapSuggestion(Base):
    """A candidate change, never an applied one.

    `explanation` and `may_be_wrong_about` are both NOT NULL and both refused
    blank by the schema, because every candidate on the canvas offers a "Why?"
    action and a suggestion that cannot answer it should not have been storable.
    """

    __tablename__ = "map_suggestions"

    id = uuid_pk()
    owner_user_id = _owner()
    suggestion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_refs: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    proposed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    may_be_wrong_about: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[decimal.Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(
        String(16), default="PENDING", server_default="PENDING", nullable=False
    )
    suppressed_kind: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at = _created()
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class MapAnnotation(Base):
    """An owner note on any canonical entity."""

    __tablename__ = "map_annotations"

    id = uuid_pk()
    owner_user_id = _owner()
    entity_ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_scope: Mapped[str] = mapped_column(
        String(24), default="PRIVATE", server_default="PRIVATE", nullable=False
    )
    created_at = _created()
    updated_at = _created()


class MapDecisionOption(Base):
    """One fork of a canonical `decisions` row.

    A partial unique index allows exactly one option per decision to carry
    `chosen_at`, because a decision with two winners was never resolved.
    """

    __tablename__ = "map_decision_options"

    id = uuid_pk()
    owner_user_id = _owner()
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    benefits: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    costs: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    risks: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    dependencies: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    evidence: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    predicted_consequences: Mapped[str | None] = mapped_column(Text)
    reversibility: Mapped[str] = mapped_column(
        String(24), default="EASY", server_default="EASY", nullable=False
    )
    time_horizon: Mapped[str | None] = mapped_column(String(48))
    effort: Mapped[str | None] = mapped_column(String(24))
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    chosen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at = _created()
    updated_at = _created()


class MapBlocker(Base):
    """Something stopping movement, stated so it can be removed.

    `affects` holds the refs this blocker obstructs, so the panel can answer
    "what does this block?" from the row rather than by guessing from position.
    `possible_responses` holds candidate ways out, which is what makes a blocker
    actionable instead of merely reported.
    """

    __tablename__ = "map_blockers"

    id = uuid_pk()
    owner_user_id = _owner()
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_slug: Mapped[str | None] = mapped_column(String(48))
    category: Mapped[str] = mapped_column(
        String(32), default="PRACTICAL", server_default="PRACTICAL", nullable=False
    )
    basis: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    affects: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    possible_responses: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="PROPOSED", server_default="PROPOSED", nullable=False
    )
    confirmed_by_owner: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at = _created()
    updated_at = _created()
