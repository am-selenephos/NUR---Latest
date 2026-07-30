"""Owner-controlled future/history Timeline ledger."""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Identity, Scoped, require_csrf
from app.models import CognitiveEvent, Goal, Outcome, Plan, PlanStep, TimelineEvent
from app.models._mixins import now_utc
from app.models.timeline_layer import (
    DATE_PRECISIONS,
    ENERGY_TYPES,
    STATUS_VALUES,
    VISIBILITY_SCOPES,
)
from app.services.glow_service import award_glow_if_eligible

router = APIRouter(prefix="/timeline", tags=["timeline"])


class TimelineEventIn(BaseModel):
    event_type: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    time_kind: str = "FUTURE"
    scheduled_for: dt.datetime | None = None
    source_type: str = "OWNER"
    source_id: uuid.UUID | None = None
    system_slug: str | None = None
    goal_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    orbit_id: uuid.UUID | None = None
    prediction_id: uuid.UUID | None = None
    importance: int = Field(default=50, ge=0, le=100)
    payload: dict = Field(default_factory=dict)
    # ── §5's truth model: an item can be created already in one of the
    # non-default states (PREDICTED from Map, INFERRED from Talk, IMPORTED from
    # a calendar link, DUE from Insights) rather than always starting PLANNED. ──
    status: str = "PLANNED"
    ends_at: dt.datetime | None = None
    all_day: bool = False
    timezone_name: str | None = None
    date_precision: str = "EXACT"
    earliest_at: dt.datetime | None = None
    latest_at: dt.datetime | None = None
    visibility_scope: str = "PRIVATE"
    energy_type: str | None = None


class TimelineEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    title: str
    description: str | None
    time_kind: str
    scheduled_for: dt.datetime | None
    occurred_at: dt.datetime | None
    source_type: str
    source_id: uuid.UUID | None
    system_slug: str | None
    goal_id: uuid.UUID | None
    objective_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    project_id: uuid.UUID | None
    person_id: uuid.UUID | None
    ends_at: dt.datetime | None = None
    all_day: bool = False
    timezone_name: str | None = None
    date_precision: str = "EXACT"
    earliest_at: dt.datetime | None = None
    latest_at: dt.datetime | None = None
    actual_start_at: dt.datetime | None = None
    actual_end_at: dt.datetime | None = None
    completion_state: str | None = None
    phase_id: uuid.UUID | None = None
    visibility_scope: str = "PRIVATE"
    energy_type: str | None = None
    group_id: uuid.UUID | None
    orbit_id: uuid.UUID | None
    prediction_id: uuid.UUID | None
    status: str
    importance: int
    event_payload: dict
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class FromPlanIn(BaseModel):
    plan_id: uuid.UUID
    first_due_at: dt.datetime
    interval_days: int = Field(default=1, ge=0, le=90)


class FromGoalIn(BaseModel):
    goal_id: uuid.UUID
    scheduled_for: dt.datetime | None = None


class RescheduleIn(BaseModel):
    scheduled_for: dt.datetime


class AttachOutcomeIn(BaseModel):
    observed_result: str = Field(min_length=1, max_length=4000)


class EasierTimelineIn(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    scheduled_for: dt.datetime | None = None
    effort_minutes: int | None = Field(default=None, ge=1, le=1440)


class TimelinePlanIn(BaseModel):
    title: str | None = Field(default=None, max_length=500)


def _normalize_time_kind(value: str) -> str:
    normalized = value.upper().strip()
    allowed = {"PAST", "PRESENT", "FUTURE", "PREDICTION", "PROJECT", "PEOPLE", "SYSTEM"}
    if normalized not in allowed:
        raise HTTPException(422, f"time_kind must be one of: {', '.join(sorted(allowed))}.")
    return normalized


async def _owned_event(db: Scoped, owner_user_id: uuid.UUID, event_id: uuid.UUID) -> TimelineEvent:
    row = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.id == event_id,
        TimelineEvent.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Timeline event not found.")
    return row


def _audit_event(db: Scoped, owner_user_id: uuid.UUID, row: TimelineEvent, kind: str) -> None:
    db.add(CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=row.orbit_id,
        event_kind="SYSTEM_EVENT",
        content_text=f"{kind.replace('_', ' ').title()}: {row.title}",
        source_ref=f"timeline_event:{row.id}",
        structured_payload={
            "timeline_kind": kind,
            "timeline_event_id": str(row.id),
            "provenance_label": "OWNER_TIMELINE_LEDGER",
        },
    ))


@router.get("", response_model=list[TimelineEventOut])
async def list_timeline(
    db: Scoped,
    identity: Identity,
    time_kind: str | None = None,
    system_slug: str | None = None,
    orbit_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[TimelineEventOut]:
    owner_user_id, _ = identity
    query = select(TimelineEvent).where(TimelineEvent.owner_user_id == owner_user_id)
    if time_kind:
        query = query.where(TimelineEvent.time_kind == _normalize_time_kind(time_kind))
    if system_slug:
        query = query.where(TimelineEvent.system_slug == system_slug)
    if orbit_id:
        query = query.where(TimelineEvent.orbit_id == orbit_id)
    query = query.order_by(
        TimelineEvent.scheduled_for.asc().nullslast(),
        TimelineEvent.created_at.desc(),
    ).limit(min(limit, 250))
    rows = (await db.execute(query)).scalars().all()
    return [TimelineEventOut.model_validate(row) for row in rows]


def _validate_creation_truth_fields(payload: TimelineEventIn) -> None:
    if payload.status not in STATUS_VALUES:
        raise HTTPException(422, f"status must be one of: {', '.join(STATUS_VALUES)}.")
    if payload.date_precision not in DATE_PRECISIONS:
        raise HTTPException(
            422, f"date_precision must be one of: {', '.join(DATE_PRECISIONS)}."
        )
    if payload.visibility_scope not in VISIBILITY_SCOPES:
        raise HTTPException(
            422, f"visibility_scope must be one of: {', '.join(VISIBILITY_SCOPES)}."
        )
    if payload.energy_type is not None and payload.energy_type not in ENERGY_TYPES:
        raise HTTPException(422, f"energy_type must be one of: {', '.join(ENERGY_TYPES)}.")
    if payload.date_precision == "UNSCHEDULED" and (
        payload.scheduled_for or payload.ends_at or payload.earliest_at or payload.latest_at
    ):
        raise HTTPException(
            422, "An UNSCHEDULED entry cannot carry a scheduled_for, ends_at, earliest_at or latest_at."
        )


@router.post("/events", response_model=TimelineEventOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_timeline_event(payload: TimelineEventIn, db: Scoped, identity: Identity) -> TimelineEventOut:
    owner_user_id, _ = identity
    _validate_creation_truth_fields(payload)
    row = TimelineEvent(
        owner_user_id=owner_user_id,
        event_type=payload.event_type.upper().strip(),
        title=payload.title.strip(),
        description=payload.description,
        time_kind=_normalize_time_kind(payload.time_kind),
        scheduled_for=payload.scheduled_for,
        source_type=payload.source_type.upper().strip(),
        source_id=payload.source_id,
        system_slug=payload.system_slug,
        goal_id=payload.goal_id,
        objective_id=payload.objective_id,
        plan_id=payload.plan_id,
        project_id=payload.project_id,
        person_id=payload.person_id,
        group_id=payload.group_id,
        orbit_id=payload.orbit_id,
        prediction_id=payload.prediction_id,
        importance=payload.importance,
        event_payload=payload.payload,
        status=payload.status,
        ends_at=payload.ends_at,
        all_day=payload.all_day,
        timezone_name=payload.timezone_name,
        date_precision=payload.date_precision,
        earliest_at=payload.earliest_at,
        latest_at=payload.latest_at,
        visibility_scope=payload.visibility_scope,
        energy_type=payload.energy_type,
    )
    db.add(row)
    await db.flush()
    _audit_event(db, owner_user_id, row, "TIMELINE_EVENT_CREATED")
    await db.commit()
    return TimelineEventOut.model_validate(row)


@router.post("/from-plan", response_model=list[TimelineEventOut], status_code=201, dependencies=[Depends(require_csrf)])
async def timeline_from_plan(payload: FromPlanIn, db: Scoped, identity: Identity) -> list[TimelineEventOut]:
    owner_user_id, _ = identity
    plan = (await db.execute(select(Plan).where(
        Plan.id == payload.plan_id,
        Plan.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    steps = (await db.execute(select(PlanStep).where(
        PlanStep.plan_id == plan.id,
        PlanStep.owner_user_id == owner_user_id,
        PlanStep.done.is_(False),
    ).order_by(PlanStep.position))).scalars().all()
    rows: list[TimelineEvent] = []
    for index, step in enumerate(steps):
        due_at = payload.first_due_at + dt.timedelta(days=index * payload.interval_days)
        row = TimelineEvent(
            owner_user_id=owner_user_id,
            event_type="PLAN_STEP_DUE",
            title=step.title,
            description=step.body,
            time_kind="FUTURE",
            scheduled_for=due_at,
            source_type="PLAN_STEP",
            source_id=step.id,
            plan_id=plan.id,
            orbit_id=plan.orbit_id,
            event_payload={"plan_step_id": str(step.id), "plan_title": plan.title},
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    for row in rows:
        _audit_event(db, owner_user_id, row, "PLAN_STEP_SCHEDULED")
    await db.commit()
    return [TimelineEventOut.model_validate(row) for row in rows]


@router.post("/from-goal", response_model=TimelineEventOut, status_code=201, dependencies=[Depends(require_csrf)])
async def timeline_from_goal(payload: FromGoalIn, db: Scoped, identity: Identity) -> TimelineEventOut:
    owner_user_id, _ = identity
    goal = (await db.execute(select(Goal).where(
        Goal.id == payload.goal_id,
        Goal.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if goal is None:
        raise HTTPException(404, "Goal not found.")
    due_at = payload.scheduled_for
    if due_at is None and goal.target_date:
        due_at = dt.datetime.combine(goal.target_date, dt.time(17, 0), tzinfo=dt.UTC)
    row = TimelineEvent(
        owner_user_id=owner_user_id,
        event_type="GOAL_MILESTONE",
        title=goal.title,
        description=goal.why,
        time_kind="FUTURE",
        scheduled_for=due_at,
        source_type="GOAL",
        source_id=goal.id,
        system_slug=goal.system_slug,
        goal_id=goal.id,
        orbit_id=goal.orbit_id,
        event_payload={"progress_percent": goal.progress_percent},
    )
    db.add(row)
    await db.flush()
    _audit_event(db, owner_user_id, row, "GOAL_SCHEDULED")
    await db.commit()
    return TimelineEventOut.model_validate(row)


async def _change_status(event_id: uuid.UUID, status: str, db: Scoped, identity: Identity) -> TimelineEventOut:
    owner_user_id, _ = identity
    row = await _owned_event(db, owner_user_id, event_id)
    row.status = status
    row.updated_at = now_utc()
    if status == "COMPLETED":
        row.occurred_at = now_utc()
        row.time_kind = "PAST"
    _audit_event(db, owner_user_id, row, f"TIMELINE_EVENT_{status}")
    await db.commit()
    return TimelineEventOut.model_validate(row)


@router.post("/{event_id}/complete", response_model=TimelineEventOut, dependencies=[Depends(require_csrf)])
async def complete_timeline_event(event_id: uuid.UUID, db: Scoped, identity: Identity) -> TimelineEventOut:
    return await _change_status(event_id, "COMPLETED", db, identity)


@router.post("/{event_id}/miss", response_model=TimelineEventOut, dependencies=[Depends(require_csrf)])
async def miss_timeline_event(event_id: uuid.UUID, db: Scoped, identity: Identity) -> TimelineEventOut:
    return await _change_status(event_id, "MISSED", db, identity)


@router.post("/{event_id}/reschedule", response_model=TimelineEventOut, dependencies=[Depends(require_csrf)])
async def reschedule_timeline_event(
    event_id: uuid.UUID, payload: RescheduleIn, db: Scoped, identity: Identity
) -> TimelineEventOut:
    owner_user_id, _ = identity
    row = await _owned_event(db, owner_user_id, event_id)
    row.scheduled_for = payload.scheduled_for
    row.status = "PLANNED"
    row.time_kind = "FUTURE"
    row.updated_at = now_utc()
    _audit_event(db, owner_user_id, row, "TIMELINE_EVENT_RESCHEDULED")
    await db.commit()
    return TimelineEventOut.model_validate(row)


@router.post("/{event_id}/attach-outcome", dependencies=[Depends(require_csrf)])
@router.post("/{event_id}/outcome", dependencies=[Depends(require_csrf)])
async def attach_timeline_outcome(
    event_id: uuid.UUID, payload: AttachOutcomeIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_event(db, owner_user_id, event_id)
    step_id = row.event_payload.get("plan_step_id")
    outcome = Outcome(
        owner_user_id=owner_user_id,
        plan_step_id=uuid.UUID(step_id) if step_id else None,
        observed_result=payload.observed_result.strip(),
        structured_measurements={"timeline_event_id": str(row.id)},
    )
    db.add(outcome)
    await db.flush()
    row.status = "COMPLETED"
    row.time_kind = "PAST"
    row.occurred_at = now_utc()
    row.updated_at = now_utc()
    row.event_payload = {**row.event_payload, "outcome_id": str(outcome.id)}
    _audit_event(db, owner_user_id, row, "OUTCOME_RETURNED")
    await award_glow_if_eligible(
        db,
        owner_user_id=owner_user_id,
        event_type="outcome_returned",
        source_kind="OUTCOME",
        source_id=outcome.id,
        orbit_id=row.orbit_id,
        idempotency_key=f"outcome:{outcome.id}:returned",
    )
    await db.commit()
    return {
        "timeline_event": TimelineEventOut.model_validate(row),
        "outcome": {"id": outcome.id, "observed_result": outcome.observed_result},
    }


@router.post("/{event_id}/make-easier", response_model=TimelineEventOut, status_code=201, dependencies=[Depends(require_csrf)])
async def make_timeline_event_easier(
    event_id: uuid.UUID,
    payload: EasierTimelineIn,
    db: Scoped,
    identity: Identity,
) -> TimelineEventOut:
    owner_user_id, _ = identity
    original = await _owned_event(db, owner_user_id, event_id)
    if original.status == "COMPLETED":
        raise HTTPException(409, "A completed Timeline event cannot be replaced.")
    original.status = "CANCELLED"
    original.updated_at = now_utc()
    easier = TimelineEvent(
        owner_user_id=owner_user_id,
        event_type="EASIER_NEXT_MOVE",
        title=payload.title or f"Smaller: {original.title}",
        description=original.description,
        time_kind="FUTURE",
        scheduled_for=payload.scheduled_for or original.scheduled_for,
        source_type="TIMELINE_EVENT",
        source_id=original.id,
        system_slug=original.system_slug,
        goal_id=original.goal_id,
        objective_id=original.objective_id,
        plan_id=original.plan_id,
        project_id=original.project_id,
        person_id=original.person_id,
        group_id=original.group_id,
        orbit_id=original.orbit_id,
        status="PLANNED",
        importance=max(1, original.importance - 10),
        event_payload={
            **original.event_payload,
            "made_easier_from": str(original.id),
            "effort_minutes": payload.effort_minutes,
            "provenance_label": "OWNER_EASIER_REPLACEMENT",
        },
    )
    db.add(easier)
    await db.flush()
    _audit_event(db, owner_user_id, original, "TIMELINE_EVENT_REPLACED")
    _audit_event(db, owner_user_id, easier, "TIMELINE_EASIER_MOVE_CREATED")
    await db.commit()
    return TimelineEventOut.model_validate(easier)


@router.post("/{event_id}/turn-into-plan", status_code=201, dependencies=[Depends(require_csrf)])
async def timeline_event_to_plan(
    event_id: uuid.UUID,
    payload: TimelinePlanIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_event(db, owner_user_id, event_id)
    plan = Plan(
        owner_user_id=owner_user_id,
        orbit_id=row.orbit_id,
        title=payload.title or row.title,
    )
    db.add(plan)
    await db.flush()
    step = PlanStep(
        owner_user_id=owner_user_id,
        plan_id=plan.id,
        title=row.title,
        body=row.description,
        position=0,
    )
    db.add(step)
    await db.flush()
    row.plan_id = plan.id
    row.event_payload = {
        **row.event_payload,
        "converted_plan_id": str(plan.id),
        "converted_plan_step_id": str(step.id),
    }
    row.updated_at = now_utc()
    _audit_event(db, owner_user_id, row, "TIMELINE_EVENT_CONVERTED_TO_PLAN")
    await db.commit()
    return {
        "plan_id": plan.id,
        "plan_step_id": step.id,
        "timeline_event_id": row.id,
        "route": "/plan",
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    }
