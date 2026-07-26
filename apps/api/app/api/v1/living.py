"""Real owner-ledger APIs for Today, the seven Systems, goals, and schedules."""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Identity, Scoped, require_csrf
from app.living.catalog import require_system
from app.living.service import (
    add_living_event,
    all_system_snapshots,
    owner_now,
    owned_system_orbit,
    system_snapshot,
    today_snapshot,
)
from app.models import (
    Goal,
    Objective,
    Outcome,
    PlanStep,
    ScheduledAction,
    SystemAction,
    SystemDiagnostic,
    TodayCheckIn,
)
from app.models._mixins import now_utc
from app.services.glow_service import AwardResult, award_glow

router = APIRouter(tags=["living-system"])


class GoalIn(BaseModel):
    system_slug: str
    title: str = Field(min_length=1, max_length=500)
    why: str | None = Field(default=None, max_length=8000)
    target_date: dt.date | None = None


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    why: str | None = Field(default=None, max_length=8000)
    status: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    target_date: dt.date | None = None


class ObjectiveIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    target_date: dt.date | None = None


class ObjectivePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    target_date: dt.date | None = None


class DiagnosticIn(BaseModel):
    answers: dict = Field(default_factory=dict)
    ratings: dict[str, int] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list, max_length=20)
    strengths: list[str] = Field(default_factory=list, max_length=20)


class SystemActionIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=8000)
    diagnostic_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None
    due_at: dt.datetime | None = None
    effort_minutes: int | None = Field(default=None, ge=1, le=1440)


class SystemActionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=8000)
    status: str | None = None
    due_at: dt.datetime | None = None
    effort_minutes: int | None = Field(default=None, ge=1, le=1440)
    outcome_id: uuid.UUID | None = None


class TodayCheckInIn(BaseModel):
    energy: int = Field(ge=0, le=10)
    pain: int = Field(ge=0, le=10)
    sleep_quality: int = Field(ge=0, le=10)
    nourishment: int = Field(ge=0, le=10)
    movement: int = Field(ge=0, le=10)
    emotional_load: int = Field(ge=0, le=10)
    clarity: int = Field(ge=0, le=10)
    note: str | None = Field(default=None, max_length=8000)


class ActionRefIn(BaseModel):
    action_id: uuid.UUID


class MakeEasierIn(BaseModel):
    action_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    effort_minutes: int = Field(ge=1, le=180)


class SystemReturnIn(BaseModel):
    observed_result: str = Field(min_length=1, max_length=8000)
    structured_measurements: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SystemReturnCorrectionIn(BaseModel):
    observed_result: str = Field(min_length=1, max_length=8000)
    reason: str = Field(min_length=1, max_length=1000)
    structured_measurements: dict | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ScheduleIn(BaseModel):
    system_slug: str
    title: str = Field(min_length=1, max_length=500)
    scheduled_for: dt.datetime
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    goal_id: uuid.UUID | None = None
    objective_id: uuid.UUID | None = None
    system_action_id: uuid.UUID | None = None
    plan_step_id: uuid.UUID | None = None


class SchedulePatch(BaseModel):
    status: str


class PlanDayIn(BaseModel):
    actions: list[ScheduleIn] = Field(min_length=1, max_length=12)


def _goal_dict(row: Goal) -> dict:
    return {
        "id": row.id,
        "orbit_id": row.orbit_id,
        "system_slug": row.system_slug,
        "title": row.title,
        "why": row.why,
        "status": row.status,
        "progress_percent": row.progress_percent,
        "target_date": row.target_date,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _objective_dict(row: Objective) -> dict:
    return {
        "id": row.id,
        "goal_id": row.goal_id,
        "title": row.title,
        "status": row.status,
        "progress_percent": row.progress_percent,
        "target_date": row.target_date,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _action_dict(row: SystemAction) -> dict:
    return {
        "id": row.id,
        "orbit_id": row.orbit_id,
        "system_slug": row.system_slug,
        "diagnostic_id": row.diagnostic_id,
        "goal_id": row.goal_id,
        "objective_id": row.objective_id,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "due_at": row.due_at,
        "effort_minutes": row.effort_minutes,
        "completed_at": row.completed_at,
        "missed_at": row.missed_at,
        "easier_from_id": row.easier_from_id,
        "outcome_id": row.outcome_id,
        "action_metadata": row.action_metadata,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _schedule_dict(row: ScheduledAction) -> dict:
    return {
        "id": row.id,
        "orbit_id": row.orbit_id,
        "system_slug": row.system_slug,
        "goal_id": row.goal_id,
        "objective_id": row.objective_id,
        "system_action_id": row.system_action_id,
        "plan_step_id": row.plan_step_id,
        "title": row.title,
        "scheduled_for": row.scheduled_for,
        "duration_minutes": row.duration_minutes,
        "status": row.status,
        "completed_at": row.completed_at,
        "missed_at": row.missed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _outcome_dict(row: Outcome) -> dict:
    return {
        "id": row.id,
        "observed_result": row.observed_result,
        "structured_measurements": row.structured_measurements,
        "confidence": row.confidence,
        "created_at": row.created_at,
    }


def _glow_dict(result: AwardResult | None, note: str | None = None) -> dict:
    if result is None:
        return {"awarded_points": 0, "status": "CAP_OR_SPAM_GATED", "note": note}
    return {
        "awarded_points": result.transaction.final_points,
        "transaction_id": result.transaction.id,
        "balance": result.balance.balance,
        "idempotent_replay": result.idempotent_replay,
        "achievements_unlocked": [row.achievement_key for row in result.achievements],
        "status": "AWARDED",
    }


async def _auto_award(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    event_type: str,
    source_kind: str,
    source_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    idempotency_key: str,
    system_slug: str | None = None,
) -> tuple[AwardResult | None, str | None]:
    try:
        return await award_glow(
            db,
            owner_user_id=owner_user_id,
            event_type=event_type,
            source_kind=source_kind,
            source_id=source_id,
            orbit_id=orbit_id,
            idempotency_key=idempotency_key,
            system_slug_override=system_slug,
        ), None
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == 409 and (
            "cap" in detail.lower() or "anti-spam" in detail.lower()
        ):
            return None, detail
        raise


async def _owned_goal(db: Scoped, owner_user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
    row = (await db.execute(select(Goal).where(
        Goal.id == goal_id,
        Goal.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Goal not found.")
    return row


async def _owned_action(
    db: Scoped, owner_user_id: uuid.UUID, action_id: uuid.UUID
) -> SystemAction:
    row = (await db.execute(select(SystemAction).where(
        SystemAction.id == action_id,
        SystemAction.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "System action not found.")
    return row


async def _owned_outcome(
    db: Scoped, owner_user_id: uuid.UUID, outcome_id: uuid.UUID
) -> Outcome:
    row = (await db.execute(select(Outcome).where(
        Outcome.id == outcome_id,
        Outcome.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Outcome not found.")
    return row


async def _validate_links(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    system_slug: str,
    goal_id: uuid.UUID | None,
    objective_id: uuid.UUID | None,
) -> None:
    if goal_id:
        goal = await _owned_goal(db, owner_user_id, goal_id)
        if goal.system_slug != system_slug:
            raise HTTPException(409, "Goal belongs to a different System.")
    if objective_id:
        objective = (await db.execute(select(Objective).where(
            Objective.id == objective_id,
            Objective.owner_user_id == owner_user_id,
        ))).scalar_one_or_none()
        if objective is None:
            raise HTTPException(404, "Objective not found.")
        goal = await _owned_goal(db, owner_user_id, objective.goal_id)
        if goal.system_slug != system_slug or (goal_id and goal.id != goal_id):
            raise HTTPException(409, "Objective belongs to a different Goal or System.")


@router.get("/systems")
async def systems(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = await all_system_snapshots(db, owner_user_id=owner_user_id)
    return {
        "provenance_label": "OWNER_LEDGER_CALCULATION",
        "systems": rows,
    }


@router.get("/systems/{system_slug}")
async def system_detail(system_slug: str, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    try:
        return await system_snapshot(
            db, owner_user_id=owner_user_id, slug=system_slug
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post(
    "/systems/{system_slug}/diagnostics",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_diagnostic(
    system_slug: str, payload: DiagnosticIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    try:
        definition = require_system(system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not payload.ratings:
        raise HTTPException(422, "At least one 0-10 diagnostic rating is required.")
    if any(value < 0 or value > 10 for value in payload.ratings.values()):
        raise HTTPException(422, "Diagnostic ratings must be between 0 and 10.")
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    score = round(sum(payload.ratings.values()) / len(payload.ratings) * 10)
    row = SystemDiagnostic(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        system_slug=system_slug,
        answers={"answers": payload.answers, "ratings": payload.ratings},
        score=score,
        blockers=payload.blockers,
        strengths=payload.strengths,
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="SYSTEM_DIAGNOSTIC_RECORDED",
        content=f"{definition.title} diagnostic recorded at {score}%.",
        object_type="system_diagnostic",
        object_id=row.id,
        metadata={"system_slug": system_slug, "score": score},
    )
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="system.checklist_answered",
        source_kind="SYSTEM_DIAGNOSTIC",
        source_id=row.id,
        orbit_id=orbit.id,
        idempotency_key=f"system-diagnostic:{row.id}:answered",
    )
    await db.commit()
    return {
        "id": row.id,
        "system_slug": row.system_slug,
        "score": row.score,
        "answers": row.answers,
        "blockers": row.blockers,
        "strengths": row.strengths,
        "created_at": row.created_at,
        "glow": _glow_dict(glow, note),
    }


@router.post(
    "/systems/{system_slug}/actions",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_system_action(
    system_slug: str, payload: SystemActionIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    try:
        definition = require_system(system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    await _validate_links(
        db,
        owner_user_id=owner_user_id,
        system_slug=system_slug,
        goal_id=payload.goal_id,
        objective_id=payload.objective_id,
    )
    if payload.diagnostic_id:
        diagnostic = (await db.execute(select(SystemDiagnostic).where(
            SystemDiagnostic.id == payload.diagnostic_id,
            SystemDiagnostic.owner_user_id == owner_user_id,
            SystemDiagnostic.system_slug == system_slug,
        ))).scalar_one_or_none()
        if diagnostic is None:
            raise HTTPException(404, "System diagnostic not found.")
    row = SystemAction(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        system_slug=system_slug,
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="SYSTEM_ACTION_CREATED",
        content=f"{definition.title}: {row.title}",
        object_type="system_action",
        object_id=row.id,
        metadata={"system_slug": system_slug},
    )
    await db.commit()
    return _action_dict(row)


async def _complete_action(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    row: SystemAction,
) -> dict:
    if row.status == "COMPLETED":
        glow, note = await _auto_award(
            db,
            owner_user_id=owner_user_id,
            event_type="system.action_marked",
            source_kind="SYSTEM_ACTION",
            source_id=row.id,
            orbit_id=row.orbit_id,
            idempotency_key=f"system-action:{row.id}:completed",
        )
        return {"action": _action_dict(row), "glow": _glow_dict(glow, note)}
    returned_from_missed = row.status == "MISSED"
    row.status = "COMPLETED"
    row.completed_at = now_utc()
    row.action_metadata = {
        **(row.action_metadata or {}),
        "returned_from_missed": returned_from_missed,
    }
    row.updated_at = now_utc()
    linked = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.owner_user_id == owner_user_id,
        ScheduledAction.system_action_id == row.id,
        ScheduledAction.status.in_(["SCHEDULED", "MISSED"]),
    ))).scalars().all()
    for schedule in linked:
        schedule.status = "COMPLETED"
        schedule.completed_at = row.completed_at
        schedule.updated_at = now_utc()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=row.orbit_id,
        timeline_kind="SYSTEM_ACTION_COMPLETED",
        content=f"Completed: {row.title}",
        object_type="system_action",
        object_id=row.id,
        metadata={
            "system_slug": row.system_slug,
            "returned_from_missed": returned_from_missed,
        },
    )
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="system.action_marked",
        source_kind="SYSTEM_ACTION",
        source_id=row.id,
        orbit_id=row.orbit_id,
        idempotency_key=f"system-action:{row.id}:completed",
    )
    bonus = None
    bonus_note = None
    if returned_from_missed:
        bonus, bonus_note = await _auto_award(
            db,
            owner_user_id=owner_user_id,
            event_type="missed_step_returned",
            source_kind="SYSTEM_ACTION",
            source_id=row.id,
            orbit_id=row.orbit_id,
            idempotency_key=f"system-action:{row.id}:returned",
        )
    return {
        "action": _action_dict(row),
        "glow": _glow_dict(glow, note),
        "return_glow": _glow_dict(bonus, bonus_note) if returned_from_missed else None,
    }


async def _miss_action(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    row: SystemAction,
) -> dict:
    if row.status == "COMPLETED":
        raise HTTPException(409, "A completed action cannot be marked missed.")
    row.status = "MISSED"
    row.missed_at = now_utc()
    row.updated_at = now_utc()
    linked = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.owner_user_id == owner_user_id,
        ScheduledAction.system_action_id == row.id,
        ScheduledAction.status == "SCHEDULED",
    ))).scalars().all()
    for schedule in linked:
        schedule.status = "MISSED"
        schedule.missed_at = row.missed_at
        schedule.updated_at = now_utc()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=row.orbit_id,
        timeline_kind="SYSTEM_ACTION_MISSED",
        content=f"Missed without erasure: {row.title}",
        object_type="system_action",
        object_id=row.id,
        metadata={"system_slug": row.system_slug},
    )
    return {"action": _action_dict(row), "glow": {"awarded_points": 0, "status": "NO_GLOW_FOR_MISS"}}


@router.patch(
    "/system-actions/{action_id}",
    dependencies=[Depends(require_csrf)],
)
async def patch_system_action(
    action_id: uuid.UUID,
    payload: SystemActionPatch,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_action(db, owner_user_id, action_id)
    if payload.title is not None:
        row.title = payload.title
    if payload.description is not None:
        row.description = payload.description
    if payload.due_at is not None:
        row.due_at = payload.due_at
    if payload.effort_minutes is not None:
        row.effort_minutes = payload.effort_minutes
    if payload.outcome_id is not None:
        await _owned_outcome(db, owner_user_id, payload.outcome_id)
        raise HTTPException(
            409,
            "Use the System Return endpoint so outcome evidence and audit stay linked.",
        )
    result = {"action": _action_dict(row), "glow": None}
    if payload.status:
        status = payload.status.upper()
        if status == "COMPLETED":
            result = await _complete_action(db, owner_user_id=owner_user_id, row=row)
        elif status == "MISSED":
            result = await _miss_action(db, owner_user_id=owner_user_id, row=row)
        elif status in {"OPEN", "CANCELLED"}:
            row.status = status
            row.updated_at = now_utc()
            result["action"] = _action_dict(row)
        else:
            raise HTTPException(422, "Unknown System action status.")
    await db.commit()
    result["action"] = _action_dict(row)
    return result


@router.post(
    "/systems/{system_slug}/actions/{action_id}/return",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def return_system_action(
    system_slug: str,
    action_id: uuid.UUID,
    payload: SystemReturnIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    try:
        require_system(system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    action = await _owned_action(db, owner_user_id, action_id)
    if action.system_slug != system_slug:
        raise HTTPException(404, "System action not found.")
    if action.status != "COMPLETED":
        raise HTTPException(409, "Complete the System action before returning its outcome.")

    if action.outcome_id is not None:
        outcome = await _owned_outcome(db, owner_user_id, action.outcome_id)
        glow, note = await _auto_award(
            db,
            owner_user_id=owner_user_id,
            event_type="outcome_returned",
            source_kind="OUTCOME",
            source_id=outcome.id,
            orbit_id=action.orbit_id,
            idempotency_key=f"system-action:{action.id}:outcome-returned",
            system_slug=system_slug,
        )
        await db.commit()
        return {
            "system_slug": system_slug,
            "action_id": action.id,
            "outcome": _outcome_dict(outcome),
            "glow": _glow_dict(glow, note),
            "idempotent_replay": True,
        }

    observed_result = payload.observed_result.strip()
    if not observed_result:
        raise HTTPException(422, "A real observed result is required.")
    outcome = Outcome(
        owner_user_id=owner_user_id,
        observed_result=observed_result,
        structured_measurements={
            **payload.structured_measurements,
            "system_slug": system_slug,
            "system_action_id": str(action.id),
        },
        confidence=payload.confidence,
        self_reported=True,
    )
    db.add(outcome)
    await db.flush()
    action.outcome_id = outcome.id
    action.updated_at = now_utc()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=action.orbit_id,
        timeline_kind="OUTCOME_RETURNED",
        content=observed_result,
        object_type="outcome",
        object_id=outcome.id,
        metadata={
            "system_slug": system_slug,
            "system_action_id": str(action.id),
        },
    )
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="outcome_returned",
        source_kind="OUTCOME",
        source_id=outcome.id,
        orbit_id=action.orbit_id,
        idempotency_key=f"system-action:{action.id}:outcome-returned",
        system_slug=system_slug,
    )
    await db.commit()
    return {
        "system_slug": system_slug,
        "action_id": action.id,
        "outcome": _outcome_dict(outcome),
        "glow": _glow_dict(glow, note),
        "idempotent_replay": False,
    }


@router.patch(
    "/systems/{system_slug}/actions/{action_id}/return",
    dependencies=[Depends(require_csrf)],
)
async def correct_system_action_return(
    system_slug: str,
    action_id: uuid.UUID,
    payload: SystemReturnCorrectionIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    try:
        require_system(system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    action = await _owned_action(db, owner_user_id, action_id)
    if action.system_slug != system_slug or action.outcome_id is None:
        raise HTTPException(404, "System action Return not found.")
    outcome = await _owned_outcome(db, owner_user_id, action.outcome_id)
    observed_result = payload.observed_result.strip()
    reason = payload.reason.strip()
    if not observed_result or not reason:
        raise HTTPException(422, "A corrected result and correction reason are required.")

    previous_measurements = outcome.structured_measurements or {}
    corrections = list(previous_measurements.get("corrections", []))
    corrections.append({
        "corrected_at": now_utc().isoformat(),
        "reason": reason,
        "previous_observed_result": outcome.observed_result,
        "previous_confidence": outcome.confidence,
        "previous_measurements": {
            key: value
            for key, value in previous_measurements.items()
            if key not in {"corrections", "system_slug", "system_action_id"}
        },
    })
    outcome.observed_result = observed_result
    if payload.confidence is not None:
        outcome.confidence = payload.confidence
    measurements = (
        payload.structured_measurements
        if payload.structured_measurements is not None
        else {
            key: value
            for key, value in previous_measurements.items()
            if key not in {"corrections", "system_slug", "system_action_id"}
        }
    )
    outcome.structured_measurements = {
        **measurements,
        "system_slug": system_slug,
        "system_action_id": str(action.id),
        "corrections": corrections[-20:],
    }
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=action.orbit_id,
        timeline_kind="OUTCOME_CORRECTED",
        content=f"Corrected Return: {observed_result}",
        object_type="outcome",
        object_id=outcome.id,
        metadata={
            "system_slug": system_slug,
            "system_action_id": str(action.id),
            "correction_reason": reason,
        },
    )
    await db.commit()
    return {
        "system_slug": system_slug,
        "action_id": action.id,
        "outcome": _outcome_dict(outcome),
        "correction_count": len(corrections[-20:]),
        "glow": {
            "awarded_points": 0,
            "status": "CORRECTION_AUDITED_NO_DUPLICATE_REWARD",
        },
    }


@router.get("/goals")
async def list_goals(db: Scoped, identity: Identity) -> list[dict]:
    owner_user_id, _ = identity
    rows = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id,
    ).order_by(Goal.created_at.desc()))).scalars().all()
    return [_goal_dict(row) for row in rows]


@router.post("/goals", status_code=201, dependencies=[Depends(require_csrf)])
async def create_goal(payload: GoalIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    try:
        definition = require_system(payload.system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    row = Goal(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="GOAL_CREATED",
        content=f"{definition.title} goal: {row.title}",
        object_type="goal",
        object_id=row.id,
        metadata={"system_slug": row.system_slug},
    )
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="goal.created",
        source_kind="GOAL",
        source_id=row.id,
        orbit_id=orbit.id,
        idempotency_key=f"goal:{row.id}:created",
    )
    await db.commit()
    return {**_goal_dict(row), "glow": _glow_dict(glow, note)}


@router.patch("/goals/{goal_id}", dependencies=[Depends(require_csrf)])
async def patch_goal(
    goal_id: uuid.UUID, payload: GoalPatch, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_goal(db, owner_user_id, goal_id)
    if payload.status and payload.status.upper() not in {"ACTIVE", "COMPLETED", "PAUSED", "ARCHIVED"}:
        raise HTTPException(422, "Unknown Goal status.")
    for field in ("title", "why", "progress_percent", "target_date"):
        if field in payload.model_fields_set:
            setattr(row, field, getattr(payload, field))
    if payload.status:
        row.status = payload.status.upper()
        if row.status == "COMPLETED":
            row.progress_percent = 100
    row.updated_at = now_utc()
    await db.commit()
    return _goal_dict(row)


@router.post(
    "/goals/{goal_id}/objectives",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_objective(
    goal_id: uuid.UUID, payload: ObjectiveIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    goal = await _owned_goal(db, owner_user_id, goal_id)
    row = Objective(
        owner_user_id=owner_user_id,
        goal_id=goal.id,
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=goal.orbit_id,
        timeline_kind="OBJECTIVE_CREATED",
        content=f"Objective: {row.title}",
        object_type="objective",
        object_id=row.id,
        metadata={"goal_id": str(goal.id), "system_slug": goal.system_slug},
    )
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="objective.created",
        source_kind="OBJECTIVE",
        source_id=row.id,
        orbit_id=goal.orbit_id,
        idempotency_key=f"objective:{row.id}:created",
    )
    await db.commit()
    return {**_objective_dict(row), "glow": _glow_dict(glow, note)}


@router.patch("/objectives/{objective_id}", dependencies=[Depends(require_csrf)])
async def patch_objective(
    objective_id: uuid.UUID,
    payload: ObjectivePatch,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(Objective).where(
        Objective.id == objective_id,
        Objective.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Objective not found.")
    if payload.status and payload.status.upper() not in {"ACTIVE", "COMPLETED", "PAUSED", "ARCHIVED"}:
        raise HTTPException(422, "Unknown Objective status.")
    for field in ("title", "progress_percent", "target_date"):
        if field in payload.model_fields_set:
            setattr(row, field, getattr(payload, field))
    if payload.status:
        row.status = payload.status.upper()
        if row.status == "COMPLETED":
            row.progress_percent = 100
    row.updated_at = now_utc()
    await db.flush()
    siblings = (await db.execute(select(Objective).where(
        Objective.owner_user_id == owner_user_id,
        Objective.goal_id == row.goal_id,
    ))).scalars().all()
    goal = await _owned_goal(db, owner_user_id, row.goal_id)
    goal.progress_percent = round(
        sum(sibling.progress_percent for sibling in siblings) / len(siblings)
    )
    if goal.progress_percent == 100:
        goal.status = "COMPLETED"
    goal.updated_at = now_utc()
    await db.commit()
    return {**_objective_dict(row), "goal_progress_percent": goal.progress_percent}


async def _create_schedule_row(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    payload: ScheduleIn,
) -> tuple[ScheduledAction, dict]:
    try:
        definition = require_system(payload.system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    await _validate_links(
        db,
        owner_user_id=owner_user_id,
        system_slug=payload.system_slug,
        goal_id=payload.goal_id,
        objective_id=payload.objective_id,
    )
    if payload.system_action_id:
        action = await _owned_action(db, owner_user_id, payload.system_action_id)
        if action.system_slug != payload.system_slug:
            raise HTTPException(409, "Scheduled action belongs to a different System.")
    if payload.plan_step_id:
        plan_step = (await db.execute(select(PlanStep).where(
            PlanStep.id == payload.plan_step_id,
            PlanStep.owner_user_id == owner_user_id,
        ))).scalar_one_or_none()
        if plan_step is None:
            raise HTTPException(404, "Plan step not found.")
    row = ScheduledAction(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="SCHEDULE_CREATED",
        content=f"Scheduled: {row.title}",
        object_type="scheduled_action",
        object_id=row.id,
        metadata={"system_slug": row.system_slug, "scheduled_for": row.scheduled_for.isoformat()},
    )
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="schedule.created",
        source_kind="SCHEDULED_ACTION",
        source_id=row.id,
        orbit_id=orbit.id,
        idempotency_key=f"schedule:{row.id}:created",
    )
    return row, _glow_dict(glow, note)


@router.get("/schedules")
async def list_schedules(db: Scoped, identity: Identity) -> list[dict]:
    owner_user_id, _ = identity
    rows = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.owner_user_id == owner_user_id,
    ).order_by(ScheduledAction.scheduled_for.asc()).limit(200))).scalars().all()
    return [_schedule_dict(row) for row in rows]


@router.post("/schedules", status_code=201, dependencies=[Depends(require_csrf)])
async def create_schedule(payload: ScheduleIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row, glow = await _create_schedule_row(
        db, owner_user_id=owner_user_id, payload=payload
    )
    await db.commit()
    return {**_schedule_dict(row), "glow": glow}


@router.patch("/schedules/{schedule_id}", dependencies=[Depends(require_csrf)])
async def patch_schedule(
    schedule_id: uuid.UUID,
    payload: SchedulePatch,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.id == schedule_id,
        ScheduledAction.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Schedule not found.")
    status = payload.status.upper()
    if status not in {"SCHEDULED", "COMPLETED", "MISSED", "CANCELLED"}:
        raise HTTPException(422, "Unknown Schedule status.")
    row.status = status
    row.updated_at = now_utc()
    if status == "COMPLETED":
        row.completed_at = now_utc()
    elif status == "MISSED":
        row.missed_at = now_utc()
    await db.commit()
    return _schedule_dict(row)


@router.get("/today")
async def today(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    return await today_snapshot(db, owner_user_id=owner_user_id)


@router.post("/today/check-in", dependencies=[Depends(require_csrf)])
async def today_check_in(
    payload: TodayCheckInIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    now, _ = await owner_now(db, owner_user_id)
    # The daily check-in records self-reported state, which is Introspection's
    # scope now that Body has been folded into it.
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system="introspection"
    )
    row = (await db.execute(select(TodayCheckIn).where(
        TodayCheckIn.owner_user_id == owner_user_id,
        TodayCheckIn.checkin_date == now.date(),
    ))).scalar_one_or_none()
    if row is None:
        row = TodayCheckIn(
            owner_user_id=owner_user_id,
            orbit_id=orbit.id,
            checkin_date=now.date(),
            **payload.model_dump(),
        )
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        row.updated_at = now_utc()
    await db.flush()
    event = add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="TODAY_CHECKIN",
        content=f"Body check-in: energy {row.energy}/10, load {row.pain}/10.",
        object_type="today_checkin",
        object_id=row.id,
        metadata={
            "checkin_date": row.checkin_date.isoformat(),
            "system_slug": "introspection",
        },
    )
    await db.flush()
    glow, note = await _auto_award(
        db,
        owner_user_id=owner_user_id,
        event_type="daily_checkin",
        source_kind="COGNITIVE_EVENT",
        source_id=event.id,
        orbit_id=orbit.id,
        # Without this the check-in's Glow was recorded against no System at
        # all, so it never appeared on the scoreboard for the System that
        # actually owns self-reported state.
        system_slug="introspection",
        idempotency_key=f"today-checkin:{row.checkin_date}:daily",
    )
    refreshed_today = await today_snapshot(db, owner_user_id=owner_user_id)
    await db.commit()
    return {
        "checkin": {
            "id": row.id,
            "date": row.checkin_date,
            **payload.model_dump(),
        },
        "glow": _glow_dict(glow, note),
        "today": refreshed_today,
    }


@router.post("/today/complete-action", dependencies=[Depends(require_csrf)])
async def today_complete_action(
    payload: ActionRefIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_action(db, owner_user_id, payload.action_id)
    result = await _complete_action(db, owner_user_id=owner_user_id, row=row)
    refreshed_today = await today_snapshot(db, owner_user_id=owner_user_id)
    await db.commit()
    result["action"] = _action_dict(row)
    result["today"] = refreshed_today
    return result


@router.post("/today/miss-action", dependencies=[Depends(require_csrf)])
async def today_miss_action(
    payload: ActionRefIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_action(db, owner_user_id, payload.action_id)
    result = await _miss_action(db, owner_user_id=owner_user_id, row=row)
    refreshed_today = await today_snapshot(db, owner_user_id=owner_user_id)
    await db.commit()
    result["action"] = _action_dict(row)
    result["today"] = refreshed_today
    return result


@router.post("/today/make-easier", status_code=201, dependencies=[Depends(require_csrf)])
async def today_make_easier(
    payload: MakeEasierIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    original = await _owned_action(db, owner_user_id, payload.action_id)
    replacement = SystemAction(
        owner_user_id=owner_user_id,
        orbit_id=original.orbit_id,
        system_slug=original.system_slug,
        diagnostic_id=original.diagnostic_id,
        goal_id=original.goal_id,
        objective_id=original.objective_id,
        title=payload.title,
        description=f"Smaller return from: {original.title}",
        due_at=original.due_at,
        effort_minutes=payload.effort_minutes,
        easier_from_id=original.id,
        action_metadata={"made_easier": True, "original_action_id": str(original.id)},
    )
    db.add(replacement)
    await db.flush()
    original.status = "CANCELLED"
    original.action_metadata = {
        **(original.action_metadata or {}),
        "easier_replacement_id": str(replacement.id),
    }
    original.updated_at = now_utc()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=original.orbit_id,
        timeline_kind="ACTION_MADE_EASIER",
        content=f"Made easier: {replacement.title}",
        object_type="system_action",
        object_id=replacement.id,
        metadata={"original_action_id": str(original.id), "system_slug": original.system_slug},
    )
    await db.commit()
    return {
        "original": _action_dict(original),
        "replacement": _action_dict(replacement),
        "glow": {"awarded_points": 0, "status": "PERSISTS_FIRST_REWARD_ON_COMPLETION"},
    }


@router.post("/today/plan-day", status_code=201, dependencies=[Depends(require_csrf)])
async def today_plan_day(
    payload: PlanDayIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    rows: list[dict] = []
    for draft in payload.actions:
        row, glow = await _create_schedule_row(
            db, owner_user_id=owner_user_id, payload=draft
        )
        rows.append({**_schedule_dict(row), "glow": glow})
    refreshed_today = await today_snapshot(db, owner_user_id=owner_user_id)
    await db.commit()
    return {
        "scheduled": rows,
        "today": refreshed_today,
    }
