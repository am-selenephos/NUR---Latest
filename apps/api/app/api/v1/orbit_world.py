"""The Orbit relational surface: bands, groups, edges, layout, threads, insights.

This sits beside `orbits.py` rather than inside it. That module owns Project
Orbits as context containers and their source allowlist; this one owns the
relational world — which band a person occupies, which people are tied to which,
where the owner dragged a node, and which relational readings are theirs versus
inferred.

Two rules shape almost every handler here.

**An inference is never written as a fact.** A relational signal must declare its
`basis`, and a `NUR_INFERRED` signal is refused unless the person has
`inference_allowed` set *and* the signal carries evidence. The permission is a
stored column, so "no inference beyond explicit notes" is enforced per person
rather than being a preference the next service can forget.

**A suggested move is not a move.** `orbit_level` is only ever written from an
explicit owner request. A suggestion goes to `orbit_level_suggestion` with a
reason and waits there; accepting it is a separate call the owner makes.

Everything is owner-scoped through `Scoped`, which sets the RLS context, so a
wrong id returns nothing rather than another owner's relationships.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select

from app.api.deps import Identity, Scoped, require_csrf
from app.models import Person
from app.models.orbit_relational import (
    CONTEXT_VISIBILITY,
    GROUP_PRIVACY_MODES,
    MEMBER_CONSENT_SCOPES,
    ORBIT_LEVELS,
    RELATIONAL_STATES,
    SIGNAL_BASES,
    SIGNAL_KINDS,
    THREAD_STATUSES,
    OrbitContextLink,
    OrbitGroup,
    OrbitGroupMember,
    OrbitLayoutNode,
    OrbitRelationalInsight,
    OrbitRelationalSignal,
    OrbitRelationship,
    OrbitThread,
)

router = APIRouter(tags=["orbit-world"])


def _enum(value: str | None, allowed: tuple[str, ...], field: str) -> str | None:
    """Reject an unknown enum value rather than storing it and failing later.

    The database has CHECK constraints for all of these; validating here turns a
    500 from a constraint violation into a 422 that names the field.
    """
    if value is None:
        return None
    if value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"{field} must be one of {', '.join(allowed)}",
        )
    return value


async def _owned_person(db, user_id: uuid.UUID, person_id: uuid.UUID) -> Person:
    row = (
        await db.execute(
            select(Person).where(Person.id == person_id, Person.owner_user_id == user_id)
        )
    ).scalar_one_or_none()
    # 404 rather than 403: confirming a person exists but belongs to someone else
    # is itself a disclosure, and this surface is about people.
    if row is None:
        raise HTTPException(status_code=404, detail="person not found")
    return row


async def _owned_group(db, user_id: uuid.UUID, group_id: uuid.UUID) -> OrbitGroup:
    row = (
        await db.execute(
            select(OrbitGroup).where(
                OrbitGroup.id == group_id, OrbitGroup.owner_user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="group not found")
    return row


# ── people as orbit entities ─────────────────────────────────────────────────

class PersonPatch(BaseModel):
    """Owner edits. `orbit_level` is here because only the owner may set it."""

    display_name: str | None = Field(default=None, max_length=240)
    relationship_type: str | None = Field(default=None, max_length=80)
    orbit_level: str | None = None
    relational_state: str | None = None
    tags: list[str] | None = None
    user_summary: str | None = None
    avatar_ref: str | None = Field(default=None, max_length=400)
    memory_allowed: bool | None = None
    inference_allowed: bool | None = None
    sharing_allowed: bool | None = None
    capsule_eligible: bool | None = None

    @field_validator("tags")
    @classmethod
    def _bounded_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) > 24:
            raise ValueError("a person may carry at most 24 tags")
        return value


class PersonOut(BaseModel):
    id: uuid.UUID
    display_name: str
    handle: str | None
    relationship_type: str | None
    orbit_level: str | None
    orbit_level_suggestion: str | None
    orbit_level_suggestion_reason: str | None
    relational_state: str | None
    tags: list
    user_summary: str | None
    nur_summary: str | None
    avatar_ref: str | None
    memory_allowed: bool
    inference_allowed: bool
    sharing_allowed: bool
    capsule_eligible: bool
    archived_at: dt.datetime | None
    last_interaction_at: dt.datetime | None
    privacy_scope: str

    model_config = {"from_attributes": True}


@router.get("/orbit-entities", response_model=list[PersonOut])
async def list_entities(
    db: Scoped, identity: Identity, include_archived: bool = False
) -> list[PersonOut]:
    user_id, _ = identity
    statement = select(Person).where(Person.owner_user_id == user_id)
    if not include_archived:
        statement = statement.where(Person.archived_at.is_(None))
    rows = (
        await db.execute(statement.order_by(Person.display_name))
    ).scalars().all()
    return [PersonOut.model_validate(row) for row in rows]


@router.get("/orbit-entities/{person_id}", response_model=PersonOut)
async def get_entity(person_id: uuid.UUID, db: Scoped, identity: Identity) -> PersonOut:
    user_id, _ = identity
    return PersonOut.model_validate(await _owned_person(db, user_id, person_id))


@router.patch(
    "/orbit-entities/{person_id}",
    response_model=PersonOut,
    dependencies=[Depends(require_csrf)],
)
async def patch_entity(
    person_id: uuid.UUID, payload: PersonPatch, db: Scoped, identity: Identity
) -> PersonOut:
    """Apply an owner edit.

    Setting `orbit_level` here clears any pending suggestion: the owner has
    answered it, so leaving the suggestion visible would keep asking a question
    that has been decided.

    Turning `inference_allowed` off also deletes that person's existing inferred
    signals. Withdrawing permission has to remove what the permission produced,
    or the readings survive their own consent.
    """
    user_id, _ = identity
    person = await _owned_person(db, user_id, person_id)
    data = payload.model_dump(exclude_unset=True)

    if "orbit_level" in data:
        data["orbit_level"] = _enum(data["orbit_level"], ORBIT_LEVELS, "orbit_level")
        person.orbit_level_suggestion = None
        person.orbit_level_suggestion_reason = None
    if "relational_state" in data:
        data["relational_state"] = _enum(
            data["relational_state"], RELATIONAL_STATES, "relational_state"
        )

    revoking_inference = data.get("inference_allowed") is False and person.inference_allowed

    for key, value in data.items():
        setattr(person, key, value)
    person.updated_at = dt.datetime.now(dt.timezone.utc)

    if revoking_inference:
        await db.execute(
            delete(OrbitRelationalSignal).where(
                OrbitRelationalSignal.owner_user_id == user_id,
                OrbitRelationalSignal.person_id == person_id,
                OrbitRelationalSignal.basis == "NUR_INFERRED",
            )
        )

    # flush, not commit-then-refresh: `Scoped` arms app.current_user_id for the
    # current transaction only, so committing drops it and a refresh would then
    # re-read under no RLS context and find nothing. Flushing populates server
    # defaults while the context is still live.
    await db.flush()
    out = PersonOut.model_validate(person)
    await db.commit()
    return out


@router.post(
    "/orbit-entities/{person_id}/archive",
    response_model=PersonOut,
    dependencies=[Depends(require_csrf)],
)
async def archive_entity(
    person_id: uuid.UUID, db: Scoped, identity: Identity
) -> PersonOut:
    """Archiving is dormancy, not deletion — the relationship and its history stay."""
    user_id, _ = identity
    person = await _owned_person(db, user_id, person_id)
    person.archived_at = dt.datetime.now(dt.timezone.utc)
    person.orbit_level = "DORMANT"
    # flush, not commit-then-refresh: `Scoped` arms app.current_user_id for the
    # current transaction only, so committing drops it and a refresh would then
    # re-read under no RLS context and find nothing. Flushing populates server
    # defaults while the context is still live.
    await db.flush()
    out = PersonOut.model_validate(person)
    await db.commit()
    return out


class LevelSuggestionIn(BaseModel):
    """A suggestion the owner can see and refuse. It changes no placement."""

    orbit_level_suggestion: str
    reason: str = Field(min_length=4)


@router.post(
    "/orbit-entities/{person_id}/level-suggestion",
    response_model=PersonOut,
    dependencies=[Depends(require_csrf)],
)
async def suggest_level(
    person_id: uuid.UUID, payload: LevelSuggestionIn, db: Scoped, identity: Identity
) -> PersonOut:
    """Record a suggested band move without performing it.

    Deliberately a separate endpoint from the PATCH that sets `orbit_level`, so
    there is no code path where suggesting and moving are the same call. The
    reason is required by both this schema and the database.
    """
    user_id, _ = identity
    person = await _owned_person(db, user_id, person_id)
    person.orbit_level_suggestion = _enum(
        payload.orbit_level_suggestion, ORBIT_LEVELS, "orbit_level_suggestion"
    )
    person.orbit_level_suggestion_reason = payload.reason
    # flush, not commit-then-refresh: `Scoped` arms app.current_user_id for the
    # current transaction only, so committing drops it and a refresh would then
    # re-read under no RLS context and find nothing. Flushing populates server
    # defaults while the context is still live.
    await db.flush()
    out = PersonOut.model_validate(person)
    await db.commit()
    return out


# ── relationships ────────────────────────────────────────────────────────────

class RelationshipIn(BaseModel):
    source_person_id: uuid.UUID
    target_person_id: uuid.UUID | None = None
    target_group_id: uuid.UUID | None = None
    relationship_type: str | None = Field(default=None, max_length=80)
    strength_user: int | None = Field(default=None, ge=0, le=100)


class RelationshipOut(BaseModel):
    id: uuid.UUID
    source_person_id: uuid.UUID
    target_person_id: uuid.UUID | None
    target_group_id: uuid.UUID | None
    relationship_type: str | None
    strength_user: int | None
    activity_score: int
    reciprocity_score: int
    momentum_score: int
    tension_score: int
    confidence: float | None
    model_config = {"from_attributes": True}


@router.get("/orbit-relationships", response_model=list[RelationshipOut])
async def list_relationships(db: Scoped, identity: Identity) -> list[RelationshipOut]:
    user_id, _ = identity
    rows = (
        await db.execute(
            select(OrbitRelationship).where(OrbitRelationship.owner_user_id == user_id)
        )
    ).scalars().all()
    return [RelationshipOut.model_validate(row) for row in rows]


@router.post(
    "/orbit-relationships",
    response_model=RelationshipOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_relationship(
    payload: RelationshipIn, db: Scoped, identity: Identity
) -> RelationshipOut:
    """Create one edge. Both ends are verified to be the caller's own.

    The database also refuses two targets, no target, and a self-edge; checking
    ownership here is what stops an edge pointing at a person the caller cannot
    see, which RLS would otherwise turn into a confusing foreign-key error.
    """
    user_id, _ = identity
    if (payload.target_person_id is None) == (payload.target_group_id is None):
        raise HTTPException(
            status_code=422,
            detail="an edge needs exactly one of target_person_id or target_group_id",
        )
    await _owned_person(db, user_id, payload.source_person_id)
    if payload.target_person_id is not None:
        if payload.target_person_id == payload.source_person_id:
            raise HTTPException(status_code=422, detail="a person cannot orbit themselves")
        await _owned_person(db, user_id, payload.target_person_id)
    else:
        await _owned_group(db, user_id, payload.target_group_id)

    row = OrbitRelationship(owner_user_id=user_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = RelationshipOut.model_validate(row)
    await db.commit()
    return out


# ── groups ───────────────────────────────────────────────────────────────────

class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    purpose: str | None = None
    group_type: str = "CIRCLE"
    privacy_mode: str = "PRIVATE_ORGANIZER"
    shared_memory_enabled: bool = False
    group_nur_enabled: bool = False
    system_slug: str | None = Field(default=None, max_length=48)


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    purpose: str | None
    group_type: str
    privacy_mode: str
    shared_memory_enabled: bool
    group_nur_enabled: bool
    system_slug: str | None
    archived_at: dt.datetime | None
    member_count: int = 0
    model_config = {"from_attributes": True}


@router.get("/orbit-groups", response_model=list[GroupOut])
async def list_groups(db: Scoped, identity: Identity) -> list[GroupOut]:
    user_id, _ = identity
    counts = dict(
        (
            await db.execute(
                select(OrbitGroupMember.group_id, func.count())
                .where(OrbitGroupMember.owner_user_id == user_id)
                .group_by(OrbitGroupMember.group_id)
            )
        ).all()
    )
    rows = (
        await db.execute(
            select(OrbitGroup)
            .where(OrbitGroup.owner_user_id == user_id)
            .order_by(OrbitGroup.name)
        )
    ).scalars().all()
    out = []
    for row in rows:
        item = GroupOut.model_validate(row)
        item.member_count = counts.get(row.id, 0)
        out.append(item)
    return out


@router.post(
    "/orbit-groups", response_model=GroupOut, status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_group(payload: GroupIn, db: Scoped, identity: Identity) -> GroupOut:
    """Create a circle.

    Group NUR is refused unless the mode already shares context. The database
    enforces the same pairing; rejecting it here names the reason instead of
    surfacing a constraint violation.
    """
    user_id, _ = identity
    _enum(payload.privacy_mode, GROUP_PRIVACY_MODES, "privacy_mode")
    if payload.group_nur_enabled and payload.privacy_mode not in (
        "SHARED_CONTEXT", "GROUP_NUR"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Group NUR is a shared workspace and cannot run on a private "
                "organizer view; set privacy_mode to SHARED_CONTEXT or GROUP_NUR"
            ),
        )
    row = OrbitGroup(owner_user_id=user_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = GroupOut.model_validate(row)
    out.member_count = 0
    await db.commit()
    return out


class MemberIn(BaseModel):
    person_id: uuid.UUID
    role: str = Field(default="MEMBER", max_length=80)
    consent_scope: str = "CONTEXT_ONLY"


class MemberOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    person_id: uuid.UUID
    role: str
    consent_scope: str
    joined_at: dt.datetime
    model_config = {"from_attributes": True}


@router.get("/orbit-groups/{group_id}/members", response_model=list[MemberOut])
async def list_members(
    group_id: uuid.UUID, db: Scoped, identity: Identity
) -> list[MemberOut]:
    user_id, _ = identity
    await _owned_group(db, user_id, group_id)
    rows = (
        await db.execute(
            select(OrbitGroupMember).where(OrbitGroupMember.group_id == group_id)
        )
    ).scalars().all()
    return [MemberOut.model_validate(row) for row in rows]


@router.post(
    "/orbit-groups/{group_id}/members", response_model=MemberOut, status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def add_member(
    group_id: uuid.UUID, payload: MemberIn, db: Scoped, identity: Identity
) -> MemberOut:
    """Add a member with that member's own consent scope.

    A person whose `sharing_allowed` is false cannot be given SHARED_MEMORY
    consent: the group would then hold durable memory about someone the owner
    never agreed to share.
    """
    user_id, _ = identity
    await _owned_group(db, user_id, group_id)
    person = await _owned_person(db, user_id, payload.person_id)
    _enum(payload.consent_scope, MEMBER_CONSENT_SCOPES, "consent_scope")
    if payload.consent_scope == "SHARED_MEMORY" and not person.sharing_allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{person.display_name} is not marked shareable, so they cannot join "
                "with SHARED_MEMORY consent; enable sharing on the person first"
            ),
        )
    row = OrbitGroupMember(owner_user_id=user_id, group_id=group_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = MemberOut.model_validate(row)
    await db.commit()
    return out


@router.delete(
    "/orbit-groups/{group_id}/members/{person_id}", status_code=204,
    dependencies=[Depends(require_csrf)],
)
async def remove_member(
    group_id: uuid.UUID, person_id: uuid.UUID, db: Scoped, identity: Identity
) -> None:
    user_id, _ = identity
    await _owned_group(db, user_id, group_id)
    await db.execute(
        delete(OrbitGroupMember).where(
            OrbitGroupMember.owner_user_id == user_id,
            OrbitGroupMember.group_id == group_id,
            OrbitGroupMember.person_id == person_id,
        )
    )
    await db.commit()


# ── context links ────────────────────────────────────────────────────────────

class ContextLinkIn(BaseModel):
    person_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    source_type: str = Field(min_length=1, max_length=48)
    source_id: uuid.UUID | None = None
    link_reason: str | None = None
    visibility_scope: str = "PRIVATE"


class ContextLinkOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID | None
    group_id: uuid.UUID | None
    source_type: str
    source_id: uuid.UUID | None
    link_reason: str | None
    visibility_scope: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


@router.get("/orbit-entities/{person_id}/context", response_model=list[ContextLinkOut])
async def list_person_context(
    person_id: uuid.UUID, db: Scoped, identity: Identity
) -> list[ContextLinkOut]:
    user_id, _ = identity
    await _owned_person(db, user_id, person_id)
    rows = (
        await db.execute(
            select(OrbitContextLink)
            .where(OrbitContextLink.person_id == person_id)
            .order_by(OrbitContextLink.created_at.desc())
        )
    ).scalars().all()
    return [ContextLinkOut.model_validate(row) for row in rows]


@router.post(
    "/orbit-context-links", response_model=ContextLinkOut, status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_context_link(
    payload: ContextLinkIn, db: Scoped, identity: Identity
) -> ContextLinkOut:
    """Link existing NUR context to a person or group.

    A CAPSULE_SHARED link requires the person to be capsule-eligible, and any
    scope beyond PRIVATE requires them to be shareable. Scope is checked against
    the subject's stored permission rather than trusted from the request, because
    the request is what a UI bug would get wrong.
    """
    user_id, _ = identity
    if (payload.person_id is None) == (payload.group_id is None):
        raise HTTPException(
            status_code=422,
            detail="a context link needs exactly one of person_id or group_id",
        )
    _enum(payload.visibility_scope, CONTEXT_VISIBILITY, "visibility_scope")

    if payload.person_id is not None:
        person = await _owned_person(db, user_id, payload.person_id)
        if payload.visibility_scope == "CAPSULE_SHARED" and not person.capsule_eligible:
            raise HTTPException(
                status_code=422,
                detail=f"{person.display_name} is not Capsule-eligible",
            )
        if payload.visibility_scope != "PRIVATE" and not person.sharing_allowed:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{person.display_name} is private-reference only; enable sharing "
                    "before linking context at a wider scope"
                ),
            )
    else:
        group = await _owned_group(db, user_id, payload.group_id)
        if payload.visibility_scope == "GROUP_SHARED" and group.privacy_mode == (
            "PRIVATE_ORGANIZER"
        ):
            raise HTTPException(
                status_code=422,
                detail="a private organizer group has no shared scope to link into",
            )

    row = OrbitContextLink(owner_user_id=user_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = ContextLinkOut.model_validate(row)
    await db.commit()
    return out


@router.delete(
    "/orbit-context-links/{link_id}", status_code=204,
    dependencies=[Depends(require_csrf)],
)
async def unlink_context(link_id: uuid.UUID, db: Scoped, identity: Identity) -> None:
    user_id, _ = identity
    await db.execute(
        delete(OrbitContextLink).where(
            OrbitContextLink.owner_user_id == user_id, OrbitContextLink.id == link_id
        )
    )
    await db.commit()


# ── threads and insights ─────────────────────────────────────────────────────

class ThreadOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID | None
    group_id: uuid.UUID | None
    topic: str
    participants: list
    status: str
    last_event_at: dt.datetime | None
    last_event_summary: str | None
    open_decision: str | None
    next_action: str | None
    plan_id: uuid.UUID | None
    system_slug: str | None
    model_config = {"from_attributes": True}


@router.get("/orbit-threads", response_model=list[ThreadOut])
async def list_threads(
    db: Scoped, identity: Identity, status: str | None = None
) -> list[ThreadOut]:
    user_id, _ = identity
    statement = select(OrbitThread).where(OrbitThread.owner_user_id == user_id)
    if status:
        _enum(status, THREAD_STATUSES, "status")
        statement = statement.where(OrbitThread.status == status)
    rows = (
        await db.execute(statement.order_by(OrbitThread.last_event_at.desc().nullslast()))
    ).scalars().all()
    return [ThreadOut.model_validate(row) for row in rows]


@router.get("/orbit-entities/{person_id}/threads", response_model=list[ThreadOut])
async def list_person_threads(
    person_id: uuid.UUID, db: Scoped, identity: Identity
) -> list[ThreadOut]:
    user_id, _ = identity
    await _owned_person(db, user_id, person_id)
    rows = (
        await db.execute(
            select(OrbitThread).where(OrbitThread.person_id == person_id)
        )
    ).scalars().all()
    return [ThreadOut.model_validate(row) for row in rows]


class InsightOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID | None
    group_id: uuid.UUID | None
    observation: str
    evidence_refs: list
    confidence: float | None
    alternative_interpretation: str | None
    recommended_move: str | None
    may_be_wrong_about: str
    status: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


@router.get("/orbit-entities/{person_id}/insights", response_model=list[InsightOut])
async def list_person_insights(
    person_id: uuid.UUID, db: Scoped, identity: Identity
) -> list[InsightOut]:
    """Insights for a person.

    Nothing is generated here. Insight rows are written by the intelligence
    layer, and each one carries its own evidence and its own statement of what it
    may be wrong about — the schema will not store one without the latter.
    """
    user_id, _ = identity
    await _owned_person(db, user_id, person_id)
    rows = (
        await db.execute(
            select(OrbitRelationalInsight)
            .where(OrbitRelationalInsight.person_id == person_id)
            .order_by(OrbitRelationalInsight.created_at.desc())
        )
    ).scalars().all()
    return [InsightOut.model_validate(row) for row in rows]


# ── signals ──────────────────────────────────────────────────────────────────

class SignalIn(BaseModel):
    signal_kind: str
    basis: str
    value: int | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list = Field(default_factory=list)
    contradictory_evidence: list = Field(default_factory=list)


class SignalOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID
    signal_kind: str
    basis: str
    value: int | None
    confidence: float | None
    evidence: list
    contradictory_evidence: list
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


@router.get("/orbit-entities/{person_id}/signals", response_model=list[SignalOut])
async def list_signals(
    person_id: uuid.UUID, db: Scoped, identity: Identity
) -> list[SignalOut]:
    """Every signal, with its basis, so the interface can render an owner's own
    statement differently from a model's guess."""
    user_id, _ = identity
    await _owned_person(db, user_id, person_id)
    rows = (
        await db.execute(
            select(OrbitRelationalSignal).where(
                OrbitRelationalSignal.person_id == person_id
            )
        )
    ).scalars().all()
    return [SignalOut.model_validate(row) for row in rows]


@router.put(
    "/orbit-entities/{person_id}/signals", response_model=SignalOut,
    dependencies=[Depends(require_csrf)],
)
async def upsert_signal(
    person_id: uuid.UUID, payload: SignalIn, db: Scoped, identity: Identity
) -> SignalOut:
    """Write one signal for one basis.

    An inferred signal needs two things the others do not: the person's
    `inference_allowed` permission, and at least one piece of evidence. Both are
    refused rather than downgraded, because a reading that arrives without either
    is exactly what "never silently turn an inference into fact" forbids.

    Keyed on (person, kind, basis), so a USER_STATED trust reading and an inferred
    one coexist rather than overwriting each other — the interface shows both.
    """
    user_id, _ = identity
    person = await _owned_person(db, user_id, person_id)
    _enum(payload.signal_kind, SIGNAL_KINDS, "signal_kind")
    _enum(payload.basis, SIGNAL_BASES, "basis")

    if payload.basis == "NUR_INFERRED":
        if not person.inference_allowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"inference is not permitted for {person.display_name}; "
                    "only stated or observed signals may be recorded"
                ),
            )
        if not payload.evidence:
            raise HTTPException(
                status_code=422,
                detail="an inferred signal must carry the evidence it rests on",
            )

    existing = (
        await db.execute(
            select(OrbitRelationalSignal).where(
                OrbitRelationalSignal.person_id == person_id,
                OrbitRelationalSignal.signal_kind == payload.signal_kind,
                OrbitRelationalSignal.basis == payload.basis,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = OrbitRelationalSignal(
            owner_user_id=user_id, person_id=person_id, **payload.model_dump()
        )
        db.add(existing)
    else:
        for key, value in payload.model_dump().items():
            setattr(existing, key, value)
        existing.updated_at = dt.datetime.now(dt.timezone.utc)

    await db.flush()
    out = SignalOut.model_validate(existing)
    await db.commit()
    return out


# ── layout ───────────────────────────────────────────────────────────────────

class LayoutNodeIn(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    x: float
    y: float
    pinned: bool = False
    collapsed: bool = False


class LayoutNodeOut(LayoutNodeIn):
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


@router.get("/orbit-layout", response_model=list[LayoutNodeOut])
async def get_layout(
    db: Scoped, identity: Identity, viewport: str = "desktop"
) -> list[LayoutNodeOut]:
    user_id, _ = identity
    rows = (
        await db.execute(
            select(OrbitLayoutNode).where(
                OrbitLayoutNode.owner_user_id == user_id,
                OrbitLayoutNode.viewport == viewport,
            )
        )
    ).scalars().all()
    return [LayoutNodeOut.model_validate(row) for row in rows]


@router.put(
    "/orbit-layout", response_model=list[LayoutNodeOut],
    dependencies=[Depends(require_csrf)],
)
async def put_layout(
    payload: list[LayoutNodeIn], db: Scoped, identity: Identity, viewport: str = "desktop"
) -> list[LayoutNodeOut]:
    """Persist node positions for one viewport.

    Upsert rather than replace-all: a partial save from a drag must not delete
    the positions of nodes that were not part of that drag. Positions are visual
    only — moving a node here never changes its orbit level, which is why the
    band lives on the person and not in the layout.
    """
    user_id, _ = identity
    if len(payload) > 2000:
        raise HTTPException(status_code=422, detail="too many layout nodes in one save")

    out: list[LayoutNodeOut] = []
    for node in payload:
        _enum(node.entity_type, ("PERSON", "GROUP"), "entity_type")
        existing = (
            await db.execute(
                select(OrbitLayoutNode).where(
                    OrbitLayoutNode.owner_user_id == user_id,
                    OrbitLayoutNode.viewport == viewport,
                    OrbitLayoutNode.entity_type == node.entity_type,
                    OrbitLayoutNode.entity_id == node.entity_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = OrbitLayoutNode(
                owner_user_id=user_id, viewport=viewport, **node.model_dump()
            )
            db.add(existing)
        else:
            existing.x, existing.y = node.x, node.y
            existing.pinned, existing.collapsed = node.pinned, node.collapsed
            existing.updated_at = dt.datetime.now(dt.timezone.utc)
        await db.flush()
        out.append(LayoutNodeOut.model_validate(existing))
    await db.commit()
    return out


# ── the field ────────────────────────────────────────────────────────────────

class OrbitFieldOut(BaseModel):
    """One read for the whole field, so rendering is not N+1 requests.

    Counts are computed from real rows. There is no synthesised activity here: an
    owner with no relationships sees an empty field and the empty state, not
    invented gravity.
    """

    people: list[PersonOut]
    groups: list[GroupOut]
    relationships: list[RelationshipOut]
    layout: list[LayoutNodeOut]
    thread_counts: dict[str, int]


@router.get("/orbit-field", response_model=OrbitFieldOut)
async def get_field(
    db: Scoped, identity: Identity, viewport: str = "desktop"
) -> OrbitFieldOut:
    user_id, _ = identity
    thread_counts = dict(
        (
            await db.execute(
                select(OrbitThread.status, func.count())
                .where(OrbitThread.owner_user_id == user_id)
                .group_by(OrbitThread.status)
            )
        ).all()
    )
    return OrbitFieldOut(
        people=await list_entities(db, identity),
        groups=await list_groups(db, identity),
        relationships=await list_relationships(db, identity),
        layout=await get_layout(db, identity, viewport=viewport),
        thread_counts={key: int(value) for key, value in thread_counts.items()},
    )
