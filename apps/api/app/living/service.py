"""Calculations and owner-bound helpers for Today and Star Systems."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.living.catalog import BY_SLUG, SYSTEMS, SystemDefinition, require_system
from app.models import (
    AMProject,
    AuditEvent,
    CognitiveEvent,
    GlowTransaction,
    Goal,
    OmegaClaim,
    Orbit,
    Outcome,
    Plan,
    Profile,
    ScheduledAction,
    SystemAction,
    SystemDiagnostic,
    TodayCheckIn,
)


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _daypart(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _capacity_band(score: int) -> tuple[str, int]:
    if score < 35:
        return "LOW", 10
    if score < 60:
        return "LIMITED", 20
    if score < 80:
        return "STEADY", 45
    return "STRONG", 90


def _operating_boundary(slug: str) -> dict:
    if slug == "introspection":
        return {
            "scope": "SELF_REPORTED_CAPACITY_SUPPORT",
            "statement": (
                "NUR organizes self-reported capacity and smaller next moves; "
                "it does not diagnose, prescribe, or replace qualified medical care."
            ),
        }
    if slug == "growth":
        return {
            "scope": "FINANCIAL_ORGANIZATION_ONLY",
            "statement": (
                "NUR can organize owner-entered financial facts and research, but "
                "does not provide licensed financial advice or move money."
            ),
        }
    return {
        "scope": "OWNER_DECISION_SUPPORT",
        "statement": "NUR organizes owner evidence and leaves consequential choices with the owner.",
    }


async def owner_now(
    db: AsyncSession, owner_user_id: uuid.UUID
) -> tuple[dt.datetime, str]:
    timezone = (await db.execute(
        select(Profile.timezone).where(Profile.user_id == owner_user_id)
    )).scalar_one_or_none()
    timezone = timezone or "UTC"
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
        timezone = "UTC"
    return dt.datetime.now(zone), timezone


async def owned_system_orbit(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    system: SystemDefinition | str,
) -> Orbit:
    definition = require_system(system) if isinstance(system, str) else system
    orbit = (await db.execute(select(Orbit).where(
        Orbit.owner_user_id == owner_user_id,
        Orbit.title == definition.title,
        Orbit.status == "ACTIVE",
    ))).scalar_one_or_none()
    if orbit is None:
        raise HTTPException(404, f"{definition.title} System not found.")
    return orbit


def add_living_event(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    timeline_kind: str,
    content: str,
    object_type: str,
    object_id: uuid.UUID,
    metadata: dict | None = None,
) -> CognitiveEvent:
    payload = {
        "type": timeline_kind.lower(),
        "timeline_kind": timeline_kind,
        "object_type": object_type,
        "object_id": str(object_id),
        "provenance_label": "OWNER_WRITTEN",
        **(metadata or {}),
    }
    event = CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_kind="SYSTEM_EVENT",
        content_text=content,
        structured_payload=payload,
        source_ref=f"{object_type}:{object_id}",
    )
    db.add(event)
    db.add(AuditEvent(
        actor_user_id=owner_user_id,
        event_type=timeline_kind.lower(),
        object_type=object_type,
        object_id=object_id,
        event_metadata={
            "orbit_id": str(orbit_id) if orbit_id else None,
            "provenance_label": "OWNER_WRITTEN",
            **(metadata or {}),
        },
    ))
    return event


async def system_snapshot(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    slug: str,
) -> dict:
    definition = require_system(slug)
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    actions = (await db.execute(select(SystemAction).where(
        SystemAction.owner_user_id == owner_user_id,
        SystemAction.system_slug == slug,
    ).order_by(SystemAction.created_at.desc()).limit(100))).scalars().all()
    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id,
        Goal.system_slug == slug,
    ).order_by(Goal.created_at.desc()).limit(50))).scalars().all()
    latest_diagnostic = (await db.execute(select(SystemDiagnostic).where(
        SystemDiagnostic.owner_user_id == owner_user_id,
        SystemDiagnostic.system_slug == slug,
    ).order_by(SystemDiagnostic.created_at.desc()).limit(1))).scalar_one_or_none()
    glow_points = int((await db.execute(select(func.coalesce(
        func.sum(GlowTransaction.final_points), 0
    )).where(
        GlowTransaction.owner_user_id == owner_user_id,
        GlowTransaction.system_slug == slug,
        GlowTransaction.reversed.is_(False),
    ))).scalar_one())
    related_projects = []
    if slug == "creation":
        related_projects = (await db.execute(select(AMProject).where(
            AMProject.owner_user_id == owner_user_id,
            AMProject.system_slug == slug,
        ).order_by(AMProject.updated_at.desc()).limit(10))).scalars().all()

    total_actions = len(actions)
    completed_actions = sum(row.status == "COMPLETED" for row in actions)
    missed_actions = [row for row in actions if row.status == "MISSED"]
    returned_outcomes = sum(
        row.status == "COMPLETED" and row.outcome_id is not None for row in actions
    )
    action_score = 100 * completed_actions / total_actions if total_actions else 0
    outcome_return_score = (
        100 * returned_outcomes / completed_actions if completed_actions else 0
    )
    goal_score = (
        sum(row.progress_percent for row in goals) / len(goals) if goals else 0
    )
    diagnostic_score = latest_diagnostic.score if latest_diagnostic else 0
    glow_score = min(100, glow_points * 2)
    diagnostic_blockers = list(
        latest_diagnostic.blockers if latest_diagnostic else []
    )
    unresolved_blocker_penalty = min(10, len(diagnostic_blockers) * 2)
    missed_return_penalty = min(10, len(missed_actions) * 5)
    progress = _clamp(
        action_score * 0.40
        + goal_score * 0.20
        + diagnostic_score * 0.15
        + outcome_return_score * 0.15
        + glow_score * 0.10
        - unresolved_blocker_penalty
        - missed_return_penalty
    )
    open_actions = [row for row in reversed(actions) if row.status == "OPEN"]
    next_move = (
        {
            "kind": "SYSTEM_ACTION",
            "id": str(open_actions[0].id),
            "title": open_actions[0].title,
        }
        if open_actions
        else {
            "kind": "CHECKLIST_SUGGESTION",
            "id": None,
            "title": definition.checklist[min(completed_actions, len(definition.checklist) - 1)],
        }
    )
    blockers = diagnostic_blockers
    blockers.extend(row.title for row in missed_actions[:3])
    return {
        "slug": slug,
        "title": definition.title,
        "definition": definition.definition,
        "operating_boundary": _operating_boundary(slug),
        "orbit_id": str(orbit.id),
        "questions": list(definition.questions),
        "checklist": list(definition.checklist),
        "progress_percent": progress,
        "progress_sources": {
            "completed_actions": completed_actions,
            "total_actions": total_actions,
            "action_completion_percent": round(action_score),
            "goal_progress_percent": round(goal_score),
            "latest_diagnostic_score": diagnostic_score,
            "outcomes_returned": returned_outcomes,
            "outcome_return_percent": round(outcome_return_score),
            "glow_points": glow_points,
            "unresolved_blocker_penalty": unresolved_blocker_penalty,
            "missed_return_penalty": missed_return_penalty,
            "formula_version": "v5-beta-2",
            "formula": (
                "40% actions + 20% goals + 15% diagnostic + 15% returned "
                "outcomes + 10% Glow activity - blocker and missed-Return penalties"
            ),
        },
        "active_goal_count": sum(row.status == "ACTIVE" for row in goals),
        "related_projects": [
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "objective": row.objective,
                "updated_at": row.updated_at,
            }
            for row in related_projects
        ],
        "goals": [
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "progress_percent": row.progress_percent,
                "target_date": row.target_date,
            }
            for row in goals[:10]
        ],
        "actions": [
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "due_at": row.due_at,
                "effort_minutes": row.effort_minutes,
                "completed_at": row.completed_at,
                "missed_at": row.missed_at,
            }
            for row in actions[:20]
        ],
        "blockers": blockers[:8],
        "next_move": next_move,
        "prediction": {
            "if_ignored": definition.ignored_prediction,
            "if_followed": definition.followed_prediction,
            "basis": {
                "progress_percent": progress,
                "missed_actions": len(missed_actions),
                "open_actions": len(open_actions),
            },
            "provenance_label": "DETERMINISTIC_INFERENCE",
        },
    }


async def all_system_snapshots(
    db: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[dict]:
    return [
        await system_snapshot(db, owner_user_id=owner_user_id, slug=system.slug)
        for system in SYSTEMS
    ]


def _checkin_body(checkin: TodayCheckIn) -> int:
    return _clamp(
        checkin.energy * 10 * 0.30
        + (10 - checkin.pain) * 10 * 0.25
        + checkin.sleep_quality * 10 * 0.20
        + checkin.nourishment * 10 * 0.15
        + checkin.movement * 10 * 0.10
    )


def _checkin_mind(checkin: TodayCheckIn) -> int:
    return _clamp(
        checkin.clarity * 10 * 0.55
        + (10 - checkin.emotional_load) * 10 * 0.45
    )


def _blend(evidence_score: int | None, system_score: float) -> int:
    if evidence_score is None:
        return _clamp(system_score)
    return _clamp(evidence_score * 0.65 + system_score * 0.35)


async def today_snapshot(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    systems: list[dict] | None = None,
) -> dict:
    now, timezone = await owner_now(db, owner_user_id)
    today = now.date()
    start_utc = dt.datetime.combine(today, dt.time.min, tzinfo=now.tzinfo).astimezone(dt.UTC)
    end_utc = start_utc + dt.timedelta(days=1)
    systems = systems or await all_system_snapshots(
        db, owner_user_id=owner_user_id
    )
    by_slug = {row["slug"]: row for row in systems}
    checkin = (await db.execute(select(TodayCheckIn).where(
        TodayCheckIn.owner_user_id == owner_user_id,
        TodayCheckIn.checkin_date == today,
    ))).scalar_one_or_none()

    mind_system = sum(
        by_slug[slug]["progress_percent"]
        for slug in ("ambition", "growth", "rebuild")
    ) / 3
    life_system = sum(
        by_slug[slug]["progress_percent"]
        for slug in ("connection", "creation", "rebuild")
    ) / 3
    body_evidence = _checkin_body(checkin) if checkin else None
    mind_evidence = _checkin_mind(checkin) if checkin else None
    body_score = _blend(body_evidence, by_slug["introspection"]["progress_percent"])
    capacity_band, capacity_action_limit = _capacity_band(body_score)
    mind_score = _blend(mind_evidence, mind_system)
    life_score = _clamp(life_system)

    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id,
        Goal.status == "ACTIVE",
    ).order_by(Goal.created_at.desc()).limit(20))).scalars().all()
    plans = (await db.execute(select(Plan).where(
        Plan.owner_user_id == owner_user_id,
        Plan.status == "ACTIVE",
    ).order_by(Plan.created_at.desc()).limit(20))).scalars().all()
    actions = (await db.execute(select(SystemAction).where(
        SystemAction.owner_user_id == owner_user_id,
    ).order_by(SystemAction.created_at.desc()).limit(200))).scalars().all()
    scheduled = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.owner_user_id == owner_user_id,
        ScheduledAction.scheduled_for >= start_utc,
        ScheduledAction.scheduled_for < end_utc,
    ).order_by(ScheduledAction.scheduled_for.asc()))).scalars().all()
    glow_today = int((await db.execute(select(func.coalesce(
        func.sum(GlowTransaction.final_points), 0
    )).where(
        GlowTransaction.owner_user_id == owner_user_id,
        GlowTransaction.reversed.is_(False),
        GlowTransaction.created_at >= start_utc,
        GlowTransaction.created_at < end_utc,
    ))).scalar_one())
    latest_insight = (await db.execute(select(OmegaClaim).where(
        OmegaClaim.owner_user_id == owner_user_id,
    ).order_by(OmegaClaim.updated_at.desc()).limit(1))).scalar_one_or_none()
    latest_event = (await db.execute(select(CognitiveEvent).where(
        CognitiveEvent.owner_user_id == owner_user_id,
    ).order_by(CognitiveEvent.created_at.desc()).limit(1))).scalar_one_or_none()
    latest_outcome = (await db.execute(select(Outcome).where(
        Outcome.owner_user_id == owner_user_id,
    ).order_by(Outcome.created_at.desc()).limit(1))).scalar_one_or_none()

    completed_today = [
        row for row in actions
        if row.completed_at and start_utc <= row.completed_at < end_utc
    ]
    missed_today = [
        row for row in actions
        if row.status == "MISSED"
        and row.missed_at
        and start_utc <= row.missed_at < end_utc
    ]
    open_today = [row for row in scheduled if row.status == "SCHEDULED"]
    open_actions = [row for row in reversed(actions) if row.status == "OPEN"]
    return_actions = [row for row in reversed(actions) if row.status == "MISSED"]
    action_by_id = {str(row.id): row for row in actions}
    next_move = None
    if open_today:
        next_move = {
            "kind": "SYSTEM_ACTION" if open_today[0].system_action_id else "SCHEDULED_ACTION",
            "id": str(open_today[0].system_action_id or open_today[0].id),
            "title": open_today[0].title,
            "scheduled_for": open_today[0].scheduled_for,
            "schedule_id": str(open_today[0].id),
        }
    elif open_actions:
        next_move = {
            "kind": "SYSTEM_ACTION",
            "id": str(open_actions[0].id),
            "title": open_actions[0].title,
            "scheduled_for": open_actions[0].due_at,
        }
    elif return_actions:
        next_move = {
            "kind": "SYSTEM_ACTION",
            "id": str(return_actions[0].id),
            "title": f"Return to: {return_actions[0].title}",
            "scheduled_for": return_actions[0].due_at,
            "returning_from_missed": True,
        }
    if next_move and next_move["kind"] == "SYSTEM_ACTION":
        next_action = action_by_id.get(next_move["id"])
        if next_action is not None:
            next_move["body_capacity"] = {
                "score": body_score,
                "band": capacity_band,
                "action_limit_minutes": capacity_action_limit,
                "effort_minutes": next_action.effort_minutes,
                "exceeds_current_guidance": bool(
                    next_action.effort_minutes
                    and next_action.effort_minutes > capacity_action_limit
                ),
                "provenance_label": "OWNER_CHECKIN_DERIVED_GUIDANCE",
            }

    system_slug_by_orbit_id = {
        row["orbit_id"]: row["slug"] for row in systems
    }

    def plan_capacity(plan: Plan) -> dict:
        plan_orbit_id = str(plan.orbit_id) if plan.orbit_id else None
        plan_actions = [
            row
            for row in actions
            if row.status == "OPEN"
            and plan_orbit_id is not None
            and str(row.orbit_id) == plan_orbit_id
        ]
        return {
            "body_score": body_score,
            "band": capacity_band,
            "action_limit_minutes": capacity_action_limit,
            "open_actions_above_guidance": sum(
                bool(row.effort_minutes and row.effort_minutes > capacity_action_limit)
                for row in plan_actions
            ),
            "provenance_label": "OWNER_CHECKIN_DERIVED_GUIDANCE",
            "not_medical_advice": True,
        }

    return {
        "date": today,
        "day_label": now.strftime("%A"),
        "local_time": now.isoformat(),
        "timezone": timezone,
        "daypart": _daypart(now.hour),
        "body": {
            "score": body_score,
            "capacity_band": capacity_band,
            "action_limit_minutes": capacity_action_limit,
            "operating_boundary": _operating_boundary("introspection"),
            "sources": {
                "today_checkin": body_evidence,
                "introspection_system": by_slug["introspection"]["progress_percent"],
            },
            "calculation": "65% today's body check-in + 35% persisted Introspection System progress when a check-in exists",
        },
        "mind": {
            "score": mind_score,
            "sources": {
                "today_checkin": mind_evidence,
                "ambition": by_slug["ambition"]["progress_percent"],
                "growth": by_slug["growth"]["progress_percent"],
                "rebuild": by_slug["rebuild"]["progress_percent"],
            },
            "calculation": "check-in clarity/load blended with Ambition, Growth, and Rebuild",
        },
        "life": {
            "score": life_score,
            "sources": {
                slug: by_slug[slug]["progress_percent"]
                for slug in ("connection", "creation", "rebuild")
            },
            "calculation": "mean persisted progress of Connection, Creation, and Rebuild",
        },
        "glow_today": glow_today,
        "active_systems": [
            {
                "slug": row["slug"],
                "title": row["title"],
                "progress_percent": row["progress_percent"],
                "next_move": row["next_move"],
            }
            for row in systems
            if row["progress_sources"]["total_actions"]
            or row["active_goal_count"]
            or row["progress_sources"]["latest_diagnostic_score"]
        ],
        "active_goals": [
            {
                "id": str(row.id),
                "title": row.title,
                "system_slug": row.system_slug,
                "progress_percent": row.progress_percent,
                "target_date": row.target_date,
            }
            for row in goals
        ],
        "active_plans": [
            {
                "id": str(row.id),
                "title": row.title,
                "orbit_id": str(row.orbit_id) if row.orbit_id else None,
                "system_slug": system_slug_by_orbit_id.get(
                    str(row.orbit_id) if row.orbit_id else ""
                ),
                "body_capacity": plan_capacity(row),
            }
            for row in plans
        ],
        "scheduled_today": [
            {
                "id": str(row.id),
                "title": row.title,
                "system_slug": row.system_slug,
                "status": row.status,
                "scheduled_for": row.scheduled_for,
            }
            for row in scheduled
        ],
        "completed_today": [
            {"id": str(row.id), "title": row.title, "system_slug": row.system_slug}
            for row in completed_today
        ],
        "missed_today": [
            {"id": str(row.id), "title": row.title, "system_slug": row.system_slug}
            for row in missed_today
        ],
        "daily_quest": {
            "key": "return_one_real_move",
            "title": (
                f"Complete one persisted move within {capacity_action_limit} minutes."
            ),
            "completed": bool(completed_today),
            "progress": 1 if completed_today else 0,
            "target": 1,
            "capacity_band": capacity_band,
        },
        "next_move": next_move,
        "latest_insight": (
            {
                "id": str(latest_insight.id),
                "text": latest_insight.claim_text,
                "truth_status": latest_insight.truth_status,
                "provenance_label": f"OMEGA_{latest_insight.truth_status}",
            }
            if latest_insight else None
        ),
        "latest_timeline_event": (
            {
                "id": str(latest_event.id),
                "kind": latest_event.structured_payload.get("timeline_kind", latest_event.event_kind),
                "text": latest_event.content_text,
                "created_at": latest_event.created_at,
            }
            if latest_event else None
        ),
        "return_check": (
            {
                "outcome_id": str(latest_outcome.id),
                "observed_result": latest_outcome.observed_result,
                "created_at": latest_outcome.created_at,
            }
            if latest_outcome else None
        ),
        "provenance_label": "OWNER_LEDGER_CALCULATION",
    }


def system_exists(slug: str) -> bool:
    return slug in BY_SLUG
