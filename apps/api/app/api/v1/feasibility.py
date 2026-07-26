"""Evidence-based feasibility checks using persisted Today/System state."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Identity, Scoped, require_csrf
from app.living.catalog import require_system
from app.living.service import add_living_event, owned_system_orbit, today_snapshot
from app.models import FeasibilityAssessment, Plan, PlanStep, TimelineEvent
from app.models._mixins import now_utc
from app.services.glow_service import award_glow

router = APIRouter(prefix="/feasibility", tags=["feasibility"])


class FeasibilityIn(BaseModel):
    system_slug: str
    subject_kind: str = Field(default="IDEA", min_length=1, max_length=48)
    subject_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    desired_outcome: str = Field(min_length=1, max_length=8000)
    capacity_required: int = Field(ge=0, le=100)
    time_required_minutes: int = Field(ge=0, le=525600)
    time_available_minutes: int = Field(ge=0, le=525600)
    money_required_cents: int = Field(ge=0)
    money_available_cents: int = Field(ge=0)
    risk_level: str = "MEDIUM"


class FeasibilityConvertIn(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    scheduled_for: str | None = None


def _out(row: FeasibilityAssessment) -> dict:
    return {
        "id": row.id,
        "orbit_id": row.orbit_id,
        "system_slug": row.system_slug,
        "subject_kind": row.subject_kind,
        "subject_id": row.subject_id,
        "title": row.title,
        "desired_outcome": row.desired_outcome,
        "capacity_required": row.capacity_required,
        "current_capacity": row.current_capacity,
        "time_required_minutes": row.time_required_minutes,
        "time_available_minutes": row.time_available_minutes,
        "money_required_cents": row.money_required_cents,
        "money_available_cents": row.money_available_cents,
        "risk_level": row.risk_level,
        "result": row.result,
        "rationale": row.rationale,
        "checks": row.checks,
        "suggestions": row.suggestions,
        "source_refs": row.source_refs,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "provenance_label": "DETERMINISTIC_OWNER_LEDGER_ASSESSMENT",
    }


def _capacity_for(system_slug: str, today: dict) -> tuple[int, list[str]]:
    if system_slug == "introspection":
        return today["body"]["score"], ["today.body"]
    if system_slug in {"ambition", "growth"}:
        return today["mind"]["score"], ["today.mind"]
    if system_slug in {"connection", "creation"}:
        return today["life"]["score"], ["today.life"]
    return round(
        (today["body"]["score"] + today["mind"]["score"] + today["life"]["score"]) / 3
    ), ["today.body", "today.mind", "today.life"]


@router.get("")
async def list_assessments(
    db: Scoped,
    identity: Identity,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
) -> list[dict]:
    owner_user_id, _ = identity
    query = select(FeasibilityAssessment).where(
        FeasibilityAssessment.owner_user_id == owner_user_id,
    )
    if target_type:
        query = query.where(FeasibilityAssessment.subject_kind == target_type.upper())
    if target_id:
        query = query.where(FeasibilityAssessment.subject_id == target_id)
    rows = (await db.execute(
        query.order_by(FeasibilityAssessment.created_at.desc()).limit(100)
    )).scalars().all()
    return [_out(row) for row in rows]


@router.post("", status_code=201, dependencies=[Depends(require_csrf)])
@router.post("/assess", status_code=201, dependencies=[Depends(require_csrf)])
async def assess(payload: FeasibilityIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    try:
        definition = require_system(payload.system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    risk_level = payload.risk_level.upper()
    if risk_level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise HTTPException(422, "risk_level must be LOW, MEDIUM, HIGH, or CRITICAL.")
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    today = await today_snapshot(db, owner_user_id=owner_user_id)
    current_capacity, capacity_sources = _capacity_for(payload.system_slug, today)
    checks = {
        "capacity": {
            "passes": current_capacity >= payload.capacity_required,
            "required": payload.capacity_required,
            "available": current_capacity,
        },
        "time": {
            "passes": payload.time_available_minutes >= payload.time_required_minutes,
            "required_minutes": payload.time_required_minutes,
            "available_minutes": payload.time_available_minutes,
        },
        "money": {
            "passes": payload.money_available_cents >= payload.money_required_cents,
            "required_cents": payload.money_required_cents,
            "available_cents": payload.money_available_cents,
        },
        "risk": {
            "passes": risk_level != "CRITICAL",
            "level": risk_level,
            "note": "Critical risk requires an explicit risk reduction before movement.",
        },
    }
    core_passes = sum(checks[key]["passes"] for key in ("capacity", "time", "money"))
    if core_passes == 3 and checks["risk"]["passes"]:
        result = "FEASIBLE"
        rationale = "Current owner-ledger capacity, time, and money meet the stated requirements."
    elif core_passes >= 2 and risk_level != "CRITICAL":
        result = "FEASIBLE_IF_SMALLER"
        rationale = "Most constraints pass, but at least one requirement must be reduced or rescheduled."
    else:
        result = "NOT_FEASIBLE_NOW"
        rationale = "The stated move exceeds multiple current constraints or carries unresolved critical risk."
    suggestions: list[str] = []
    if not checks["capacity"]["passes"]:
        suggestions.append(
            f"Reduce required capacity from {payload.capacity_required}% toward {current_capacity}%."
        )
    if not checks["time"]["passes"]:
        suggestions.append(
            f"Reduce or split {payload.time_required_minutes} minutes into the available {payload.time_available_minutes}."
        )
    if not checks["money"]["passes"]:
        suggestions.append("Reduce cost, create a funding step, or defer spending.")
    if risk_level == "CRITICAL":
        suggestions.append("Resolve or contain the critical risk before scheduling execution.")
    if not suggestions:
        suggestions.append("Create one scheduled System action and return its outcome.")

    row = FeasibilityAssessment(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        system_slug=payload.system_slug,
        subject_kind=payload.subject_kind.upper(),
        subject_id=payload.subject_id,
        title=payload.title,
        desired_outcome=payload.desired_outcome,
        capacity_required=payload.capacity_required,
        current_capacity=current_capacity,
        time_required_minutes=payload.time_required_minutes,
        time_available_minutes=payload.time_available_minutes,
        money_required_cents=payload.money_required_cents,
        money_available_cents=payload.money_available_cents,
        risk_level=risk_level,
        result=result,
        rationale=rationale,
        checks=checks,
        suggestions=suggestions,
        source_refs=capacity_sources,
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="FEASIBILITY_CREATED",
        content=f"{result.replace('_', ' ').title()}: {row.title}",
        object_type="feasibility_assessment",
        object_id=row.id,
        metadata={"system_slug": row.system_slug, "result": row.result},
    )
    # A verified cap/anti-spam Glow gate must never undo the persisted
    # assessment itself — the reward is skipped, the action stands.
    try:
        glow = await award_glow(
            db,
            owner_user_id=owner_user_id,
            event_type="feasibility.created",
            source_kind="FEASIBILITY",
            source_id=row.id,
            orbit_id=orbit.id,
            idempotency_key=f"feasibility:{row.id}:created",
        )
        glow_out = {
            "transaction_id": glow.transaction.id,
            "awarded_points": glow.transaction.final_points,
            "balance": glow.balance.balance,
        }
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        glow_out = {"awarded_points": 0, "status": "GLOW_GATED", "note": str(exc.detail)}
    await db.commit()
    return {**_out(row), "glow": glow_out}


async def _owned_assessment(
    db: Scoped,
    owner_user_id: uuid.UUID,
    assessment_id: uuid.UUID,
) -> FeasibilityAssessment:
    row = (await db.execute(select(FeasibilityAssessment).where(
        FeasibilityAssessment.id == assessment_id,
        FeasibilityAssessment.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Feasibility assessment not found.")
    return row


@router.post("/{assessment_id}/convert-to-plan", status_code=201, dependencies=[Depends(require_csrf)])
async def feasibility_to_plan(
    assessment_id: uuid.UUID,
    payload: FeasibilityConvertIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    assessment = await _owned_assessment(db, owner_user_id, assessment_id)
    plan = Plan(
        owner_user_id=owner_user_id,
        orbit_id=assessment.orbit_id,
        title=payload.title or f"Feasible route: {assessment.title}",
    )
    db.add(plan)
    await db.flush()
    first_move = assessment.suggestions[0] if assessment.suggestions else assessment.desired_outcome
    step = PlanStep(
        owner_user_id=owner_user_id,
        plan_id=plan.id,
        title=first_move[:500],
        body=(
            f"Assessment: {assessment.result}. {assessment.rationale} "
            f"Desired outcome: {assessment.desired_outcome}"
        ),
        position=0,
    )
    db.add(step)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=assessment.orbit_id,
        timeline_kind="FEASIBILITY_CONVERTED_TO_PLAN",
        content=f"Created Plan from feasibility: {plan.title}",
        object_type="plan",
        object_id=plan.id,
        metadata={"feasibility_id": str(assessment.id), "system_slug": assessment.system_slug},
    )
    await db.commit()
    return {
        "plan_id": plan.id,
        "plan_step_id": step.id,
        "route": "/plan",
        "provenance_label": "FEASIBILITY_OWNER_LEDGER_CONVERSION",
    }


@router.post("/{assessment_id}/add-to-timeline", status_code=201, dependencies=[Depends(require_csrf)])
async def feasibility_to_timeline(
    assessment_id: uuid.UUID,
    payload: FeasibilityConvertIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    assessment = await _owned_assessment(db, owner_user_id, assessment_id)
    scheduled_for = None
    if payload.scheduled_for:
        try:
            import datetime as dt

            scheduled_for = dt.datetime.fromisoformat(payload.scheduled_for.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(422, "scheduled_for must be an ISO-8601 datetime.") from exc
    row = TimelineEvent(
        owner_user_id=owner_user_id,
        event_type="FEASIBILITY_NEXT_MOVE",
        title=payload.title or assessment.title,
        description=assessment.suggestions[0] if assessment.suggestions else assessment.rationale,
        time_kind="FUTURE",
        scheduled_for=scheduled_for,
        source_type="FEASIBILITY",
        source_id=assessment.id,
        system_slug=assessment.system_slug,
        orbit_id=assessment.orbit_id,
        status="PLANNED",
        event_payload={
            "feasibility_id": str(assessment.id),
            "result": assessment.result,
            "provenance_label": "DETERMINISTIC_OWNER_LEDGER_ASSESSMENT",
        },
    )
    db.add(row)
    await db.flush()
    add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=assessment.orbit_id,
        timeline_kind="FEASIBILITY_ADDED_TO_TIMELINE",
        content=f"Feasibility move added to Timeline: {row.title}",
        object_type="timeline_event",
        object_id=row.id,
        metadata={"feasibility_id": str(assessment.id), "system_slug": assessment.system_slug},
    )
    row.updated_at = now_utc()
    await db.commit()
    return {
        "timeline_event_id": row.id,
        "route": "/universe/timeline",
        "provenance_label": "FEASIBILITY_OWNER_LEDGER_CONVERSION",
    }
