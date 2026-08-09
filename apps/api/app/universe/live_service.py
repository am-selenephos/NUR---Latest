"""Calculated Live Universe view over existing owner-scoped ledgers.

The view does not create a second source of truth. Every row is selected under
the current PostgreSQL owner context and carries an explicit provenance label.
"""

import datetime as dt
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.living.service import all_system_snapshots, today_snapshot
from app.models import (
    AMProject,
    AMProjectTask,
    CognitiveEvent,
    CommunityConsultationNote,
    CommunityMembership,
    CommunityRoom,
    GlowBalance,
    GlowStreak,
    Goal,
    Insight,
    Objective,
    OmegaClaim,
    OmegaContradiction,
    OmegaReviewQueue,
    Orbit,
    OrbitMember,
    Plan,
    PlanStep,
    Profile,
    ResearchBrief,
    ResearchSourceNote,
    ScheduledAction,
    SystemAction,
    TimelineEvent,
    User,
    WebSignalNote,
    WebSignalQuestion,
)
from app.models._mixins import now_utc


def _event_route(kind: str) -> str:
    if kind in {"TALK_TURN", "MODEL_RESPONSE"}:
        return "/talk"
    if kind.startswith("PROJECT_"):
        return "/universe/orbits"
    if kind.startswith("RESEARCH_"):
        return "/universe/research"
    if kind.startswith("WEB_SIGNAL_"):
        return "/universe/web-signals"
    if kind.startswith("COMMUNITY_"):
        return "/universe/community"
    if kind.startswith("OMEGA_") or kind.startswith("INSIGHT_"):
        return "/universe/insights"
    if kind in {"PREDICTION_MADE", "FEASIBILITY_CREATED"}:
        return "/universe/map"
    if kind.startswith("PLAN_") or kind in {"OUTCOME_RETURNED", "OUTCOME_REPORTED"}:
        return "/plan"
    return "/universe/timeline"


def _event_dict(row: CognitiveEvent) -> dict:
    kind = str(row.structured_payload.get("timeline_kind", row.event_kind))
    return {
        "id": str(row.id),
        "kind": kind,
        "title": kind.replace("_", " ").title(),
        "body": row.content_text or "Persisted owner-ledger event.",
        "created_at": row.created_at,
        "route": _event_route(kind),
        "provenance_label": row.structured_payload.get(
            "provenance_label", "OWNER_LEDGER"
        ),
    }


def _latest_timestamp(rows: list[object], generated_at: dt.datetime) -> dt.datetime:
    candidates: list[dt.datetime] = []
    for row in rows:
        for key in ("updated_at", "created_at", "scheduled_for"):
            value = getattr(row, key, None)
            if isinstance(value, dt.datetime):
                candidates.append(value)
                break
    return max(candidates, default=generated_at)


async def build_live_universe(
    db: AsyncSession, *, owner_user_id: uuid.UUID
) -> dict:
    generated_at = now_utc()
    user = (await db.execute(select(User).where(User.id == owner_user_id))).scalar_one()
    profile = (await db.execute(
        select(Profile).where(Profile.user_id == owner_user_id)
    )).scalar_one()

    systems = await all_system_snapshots(db, owner_user_id=owner_user_id)
    today = await today_snapshot(
        db, owner_user_id=owner_user_id, systems=systems
    )

    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id,
        Goal.status == "ACTIVE",
    ).order_by(Goal.created_at.desc()).limit(40))).scalars().all()
    goal_ids = [row.id for row in goals]
    objectives = (await db.execute(select(Objective).where(
        Objective.owner_user_id == owner_user_id,
        Objective.status == "ACTIVE",
        Objective.goal_id.in_(goal_ids),
    ).order_by(Objective.created_at.desc()).limit(80))).scalars().all()
    goal_by_id = {row.id: row for row in goals}

    plans = (await db.execute(select(Plan).where(
        Plan.owner_user_id == owner_user_id,
        Plan.status == "ACTIVE",
    ).order_by(Plan.updated_at.desc()).limit(40))).scalars().all()
    plan_ids = [row.id for row in plans]
    plan_steps = (await db.execute(select(PlanStep).where(
        PlanStep.owner_user_id == owner_user_id,
        PlanStep.plan_id.in_(plan_ids),
    ).order_by(PlanStep.plan_id, PlanStep.position))).scalars().all()
    steps_by_plan: dict[uuid.UUID, list[PlanStep]] = {}
    for step in plan_steps:
        steps_by_plan.setdefault(step.plan_id, []).append(step)

    projects = (await db.execute(select(AMProject).where(
        AMProject.owner_user_id == owner_user_id,
        AMProject.status.in_(["ACTIVE", "PAUSED"]),
    ).order_by(AMProject.updated_at.desc()).limit(40))).scalars().all()
    project_ids = [row.id for row in projects]
    project_tasks = (await db.execute(select(AMProjectTask).where(
        AMProjectTask.owner_user_id == owner_user_id,
        AMProjectTask.project_id.in_(project_ids),
    ).order_by(
        AMProjectTask.priority.desc(), AMProjectTask.created_at.asc()
    ))).scalars().all()
    tasks_by_project: dict[uuid.UUID, list[AMProjectTask]] = {}
    for task in project_tasks:
        tasks_by_project.setdefault(task.project_id, []).append(task)

    claims = (await db.execute(select(OmegaClaim).where(
        OmegaClaim.owner_user_id == owner_user_id,
        OmegaClaim.truth_status.notin_(["RETIRED", "SUPERSEDED"]),
    ).order_by(OmegaClaim.updated_at.desc()).limit(8))).scalars().all()
    contradictions = (await db.execute(select(OmegaContradiction).where(
        OmegaContradiction.owner_user_id == owner_user_id,
        OmegaContradiction.status == "OPEN",
    ).order_by(OmegaContradiction.created_at.desc()).limit(8))).scalars().all()
    reviews = (await db.execute(select(OmegaReviewQueue).where(
        OmegaReviewQueue.owner_user_id == owner_user_id,
        OmegaReviewQueue.status == "PENDING_REVIEW",
    ).order_by(OmegaReviewQueue.created_at.desc()).limit(8))).scalars().all()
    dedicated_insights = (await db.execute(select(Insight).where(
        Insight.owner_user_id == owner_user_id,
        Insight.lifecycle_status.notin_(["OWNER_REJECTED", "SUPERSEDED", "RETRACTED"]),
    ).order_by(Insight.updated_at.desc()).limit(8))).scalars().all()

    social_orbits = (await db.execute(select(Orbit).where(
        Orbit.owner_user_id == owner_user_id,
        Orbit.kind.in_(["PERSON", "GROUP", "COUNCIL", "COMMUNITY"]),
        Orbit.status == "ACTIVE",
    ).order_by(Orbit.updated_at.desc()).limit(24))).scalars().all()
    social_orbit_ids = [row.id for row in social_orbits]
    social_members = (await db.execute(select(OrbitMember).where(
        OrbitMember.owner_user_id == owner_user_id,
        OrbitMember.orbit_id.in_(social_orbit_ids),
    ).order_by(OrbitMember.recent_activity_score.desc()))).scalars().all()
    members_by_orbit: dict[uuid.UUID, list[OrbitMember]] = {}
    for member in social_members:
        members_by_orbit.setdefault(member.orbit_id, []).append(member)

    events = (await db.execute(select(CognitiveEvent).where(
        CognitiveEvent.owner_user_id == owner_user_id,
    ).order_by(CognitiveEvent.created_at.desc()).limit(30))).scalars().all()
    upcoming = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.owner_user_id == owner_user_id,
        ScheduledAction.status == "SCHEDULED",
        ScheduledAction.scheduled_for >= generated_at,
    ).order_by(ScheduledAction.scheduled_for.asc()).limit(12))).scalars().all()
    timeline_events = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == owner_user_id,
    ).order_by(
        TimelineEvent.scheduled_for.asc().nullslast(),
        TimelineEvent.created_at.desc(),
    ).limit(30))).scalars().all()
    open_actions = (await db.execute(select(SystemAction).where(
        SystemAction.owner_user_id == owner_user_id,
        SystemAction.status.in_(["OPEN", "MISSED"]),
    ).order_by(SystemAction.created_at.desc()).limit(20))).scalars().all()

    research_briefs = (await db.execute(select(ResearchBrief).where(
        ResearchBrief.owner_user_id == owner_user_id,
    ).order_by(ResearchBrief.updated_at.desc()).limit(6))).scalars().all()
    research_notes = (await db.execute(select(ResearchSourceNote).where(
        ResearchSourceNote.owner_user_id == owner_user_id,
    ).order_by(ResearchSourceNote.updated_at.desc()).limit(6))).scalars().all()
    web_questions = (await db.execute(select(WebSignalQuestion).where(
        WebSignalQuestion.owner_user_id == owner_user_id,
    ).order_by(WebSignalQuestion.updated_at.desc()).limit(6))).scalars().all()
    web_notes = (await db.execute(select(WebSignalNote).where(
        WebSignalNote.owner_user_id == owner_user_id,
    ).order_by(WebSignalNote.updated_at.desc()).limit(6))).scalars().all()
    community_notes = (await db.execute(select(CommunityConsultationNote).where(
        CommunityConsultationNote.owner_user_id == owner_user_id,
    ).order_by(CommunityConsultationNote.updated_at.desc()).limit(8))).scalars().all()
    community_room_rows = (await db.execute(
        select(CommunityRoom, CommunityMembership.role)
        .join(CommunityMembership, CommunityMembership.room_id == CommunityRoom.id)
        .where(
            CommunityMembership.user_id == owner_user_id,
            CommunityRoom.status == "ACTIVE",
        )
        .order_by(CommunityRoom.updated_at.desc())
        .limit(12)
    )).all()

    glow_balance = (await db.execute(select(GlowBalance).where(
        GlowBalance.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    streaks = (await db.execute(select(GlowStreak).where(
        GlowStreak.owner_user_id == owner_user_id,
    ).order_by(GlowStreak.current_count.desc()).limit(8))).scalars().all()

    active_goals = [{
        "id": str(row.id),
        "title": row.title,
        "system_slug": row.system_slug,
        "progress_percent": row.progress_percent,
        "target_date": row.target_date,
        "why": row.why,
        "route": "/universe/map",
        "provenance_label": "OWNER_LEDGER",
    } for row in goals]
    active_objectives = [{
        "id": str(row.id),
        "goal_id": str(row.goal_id),
        "goal_title": goal_by_id[row.goal_id].title,
        "system_slug": goal_by_id[row.goal_id].system_slug,
        "title": row.title,
        "progress_percent": row.progress_percent,
        "target_date": row.target_date,
        "route": "/universe/map",
        "provenance_label": "OWNER_LEDGER",
    } for row in objectives]
    active_plans = []
    for row in plans:
        steps = steps_by_plan.get(row.id, [])
        open_steps = [step for step in steps if not step.done]
        active_plans.append({
            "id": str(row.id),
            "title": row.title,
            "orbit_id": str(row.orbit_id) if row.orbit_id else None,
            "open_step_count": len(open_steps),
            "completed_step_count": len(steps) - len(open_steps),
            "next_step": ({
                "id": str(open_steps[0].id),
                "title": open_steps[0].title,
            } if open_steps else None),
            "route": "/plan",
            "provenance_label": "OWNER_LEDGER",
        })

    project_rows = []
    for row in projects:
        tasks = tasks_by_project.get(row.id, [])
        counts = Counter(task.status for task in tasks)
        next_tasks = [task for task in tasks if task.status not in {"DONE", "CANCELLED"}]
        project_rows.append({
            "id": str(row.id),
            "orbit_id": str(row.orbit_id),
            "title": row.title,
            "objective": row.objective,
            "status": row.status,
            "system_slug": row.system_slug,
            "deadline": row.deadline,
            "task_counts": dict(counts),
            "next_task": ({
                "id": str(next_tasks[0].id),
                "title": next_tasks[0].title,
                "status": next_tasks[0].status,
            } if next_tasks else None),
            "route": "/universe/orbits",
            "provenance_label": "OWNER_PROJECT_LEDGER",
        })

    latest_insights = [{
        "record_kind": "DEDICATED_INSIGHT",
        "id": str(row.id),
        "title": row.title,
        "insight_type": row.insight_type,
        "claim": row.claim,
        "status": row.status,
        "lifecycle_status": row.lifecycle_status,
        "epistemic_state": row.epistemic_state,
        "insight_version": row.insight_version,
        "confidence": row.confidence,
        "evidence_count": len(row.evidence),
        "counter_evidence_count": len(row.counter_evidence),
        "what_nur_may_be_wrong_about": row.what_nur_may_be_wrong_about,
        "suggested_action": row.suggested_action,
        "route": f"/universe/insights/{row.id}",
        "provenance_label": row.provenance_label,
    } for row in dedicated_insights]
    latest_insights.extend({
        "record_kind": "OMEGA_CLAIM",
        "id": str(row.id),
        "title": row.claim_text[:120],
        "insight_type": row.claim_type,
        "claim": row.claim_text,
        "truth_status": row.truth_status,
        "confidence": row.confidence,
        "support_count": row.support_count,
        "contradiction_count": row.contradiction_count,
        "route": f"/universe/omega/why-changed/{row.id}",
        "provenance_label": f"OMEGA_{row.truth_status}",
    } for row in claims)

    timeline_highlights = [_event_dict(row) for row in events[:10]]
    timeline_highlights.extend({
        "id": str(row.id),
        "kind": "SCHEDULE_DUE",
        "title": row.title,
        "body": f"{row.system_slug.replace('-', ' ').title()} schedule",
        "created_at": row.created_at,
        "scheduled_for": row.scheduled_for,
        "route": "/universe/timeline",
        "provenance_label": "OWNER_SCHEDULE",
    } for row in upcoming[:6])
    timeline_highlights.extend({
        "id": str(row.id),
        "kind": row.event_type,
        "title": row.title,
        "body": row.description or "Persisted Timeline event.",
        "created_at": row.created_at,
        "scheduled_for": row.scheduled_for,
        "route": "/universe/timeline",
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    } for row in timeline_events[:10])

    open_loops = [{
        "id": str(row.id),
        "kind": "SYSTEM_ACTION",
        "title": row.title,
        "status": row.status,
        "system_slug": row.system_slug,
        "route": "/systems",
        "provenance_label": "OWNER_LEDGER",
    } for row in open_actions]
    open_loops.extend({
        "id": str(row.id),
        "kind": "PLAN_STEP",
        "title": row.title,
        "status": "OPEN",
        "route": "/plan",
        "provenance_label": "OWNER_LEDGER",
    } for row in plan_steps if not row.done)
    open_loops.extend({
        "id": str(row.id),
        "kind": "PROJECT_TASK",
        "title": row.title,
        "status": row.status,
        "route": "/universe/orbits",
        "provenance_label": "OWNER_PROJECT_LEDGER",
    } for row in project_tasks if row.status not in {"DONE", "CANCELLED"})
    open_loops.extend({
        "id": str(row.id),
        "kind": "CONTRADICTION",
        "title": row.description,
        "status": row.status,
        "route": "/universe/insights",
        "provenance_label": "OMEGA_OWNER_LEDGER",
    } for row in contradictions)
    open_loops.extend({
        "id": str(row.id),
        "kind": "INSIGHT_REVIEW",
        "title": row.candidate_claim_text,
        "status": row.status,
        "route": "/universe/omega/review",
        "provenance_label": "OMEGA_OWNER_LEDGER",
    } for row in reviews)
    open_loops.extend({
        "id": str(row.id),
        "kind": "TIMELINE_EVENT",
        "title": row.title,
        "status": row.status,
        "route": "/universe/timeline",
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    } for row in timeline_events if row.status in {"PLANNED", "DUE", "MISSED"})

    social_rows = []
    for row in social_orbits:
        members = members_by_orbit.get(row.id, [])
        social_rows.append({
            "id": str(row.id),
            "title": row.title,
            "kind": row.kind,
            "description": row.description,
            "privacy_scope": row.privacy_scope,
            "member_count": len(members),
            "unresolved_count": sum(member.unresolved_count for member in members),
            "shared_goal_count": sum(member.shared_goal_count for member in members),
            "recent_activity_score": max(
                (member.recent_activity_score for member in members), default=0
            ),
            "route": "/universe/orbits",
            "provenance_label": "OWNER_SOCIAL_LEDGER",
        })

    next_moves: list[dict] = []
    if today["next_move"]:
        next_moves.append({
            **today["next_move"],
            "why": "This is the earliest persisted open move in today's owner ledger.",
            "route": "/today",
            "provenance_label": "OWNER_LEDGER_CALCULATION",
        })
    seen_titles = {row["title"] for row in next_moves}
    for system in systems:
        move = system["next_move"]
        if move["title"] in seen_titles:
            continue
        next_moves.append({
            **move,
            "system_slug": system["slug"],
            "why": f"{system['title']} has a persisted or checklist-derived next move.",
            "route": "/systems",
            "provenance_label": move.get(
                "provenance_label", "OWNER_LEDGER_OR_CATALOG_SUGGESTION"
            ),
        })
        seen_titles.add(move["title"])
        if len(next_moves) >= 6:
            break

    signals: list[dict] = []
    signals.extend({
        "id": str(row.id),
        "kind": "RESEARCH_BRIEF",
        "title": row.question,
        "status": row.status,
        "provider_status": row.provider_status,
        "route": "/universe/research",
        "provenance_label": row.provenance_label,
    } for row in research_briefs)
    signals.extend({
        "id": str(row.id),
        "kind": "RESEARCH_SOURCE_NOTE",
        "title": row.title,
        "status": row.trust_state,
        "url": row.url,
        "route": "/universe/research",
        "provenance_label": row.provenance_label,
    } for row in research_notes)
    signals.extend({
        "id": str(row.id),
        "kind": "WEB_SIGNAL_QUESTION",
        "title": row.question,
        "status": row.status,
        "provider_status": row.provider_status,
        "route": "/universe/web-signals",
        "provenance_label": row.provenance_label,
    } for row in web_questions)
    signals.extend({
        "id": str(row.id),
        "kind": "WEB_SIGNAL_NOTE",
        "title": row.title,
        "url": row.url,
        "route": "/universe/web-signals",
        "provenance_label": row.provenance_label,
    } for row in web_notes)

    source_count = (
        len(events)
        + len(goals)
        + len(objectives)
        + len(plans)
        + len(projects)
        + len(claims)
        + len(dedicated_insights)
        + len(social_orbits)
        + len(timeline_events)
        + len(research_briefs)
        + len(research_notes)
        + len(web_questions)
        + len(web_notes)
        + len(community_notes)
        + len(community_room_rows)
    )
    if today["next_move"]:
        synthesis = f"The clearest persisted next move is: {today['next_move']['title']}"
    elif goals:
        synthesis = f"{len(goals)} active goal{'s' if len(goals) != 1 else ''} need a persisted next move."
    else:
        synthesis = "No next move is persisted yet. NUR will not invent one."

    changed = [{
        **_event_dict(row),
        "change_window": "recent_owner_ledger_not_verified_last_visit",
    } for row in events[:8]]
    latest_note = community_notes[0] if community_notes else None
    bounded_rooms = [{
        "id": str(room.id),
        "title": room.title,
        "room_kind": room.room_kind,
        "current_user_role": role,
        "language_tag": room.language_tag,
        "is_demo": room.is_demo,
        "route": "/universe/community",
        "provenance_label": "BOUNDED_COMMUNITY_ROOM",
    } for room, role in community_room_rows]
    source_rows: list[object] = [
        *goals,
        *objectives,
        *plans,
        *projects,
        *dedicated_insights,
        *social_orbits,
        *timeline_events,
        *events,
        *research_briefs,
        *research_notes,
        *web_questions,
        *web_notes,
        *community_notes,
        *(room for room, _role in community_room_rows),
    ]

    return {
        "generated_at": generated_at,
        "provenance_label": "OWNER_LEDGER_AGGREGATE",
        "owner": {
            "id": str(user.id),
            "email": user.email,
            "chosen_name": profile.chosen_name,
            "timezone": profile.timezone or "UTC",
            "locale": profile.locale or "en",
            "writing_preference": profile.writing_preference,
            "default_boundary": profile.default_boundary,
        },
        "state": {
            "summary": synthesis,
            "source_count": source_count,
            "confidence": round(min(1.0, source_count / 12), 2),
            "confidence_kind": "source_coverage_not_truth_probability",
            "last_updated": _latest_timestamp(source_rows, generated_at),
            "today": today,
            "provenance_label": "DETERMINISTIC_OWNER_LEDGER_SYNTHESIS",
        },
        "active_systems": systems,
        "active_goals": active_goals,
        "active_objectives": active_objectives,
        "active_plans": active_plans,
        "people_orbits": [row for row in social_rows if row["kind"] == "PERSON"],
        "group_orbits": [row for row in social_rows if row["kind"] != "PERSON"],
        "projects": project_rows,
        "latest_insights": latest_insights,
        "timeline_highlights": timeline_highlights,
        "open_loops": open_loops[:30],
        "next_moves": next_moves,
        "glow": {
            "balance": glow_balance.balance if glow_balance else 0,
            "lifetime_points": glow_balance.lifetime_points if glow_balance else 0,
            "today_points": today["glow_today"],
            "streaks": [{
                "key": row.streak_key,
                "current_count": row.current_count,
                "best_count": row.best_count,
                "last_event_date": row.last_event_date,
            } for row in streaks],
            "provenance_label": "GLOW_OWNER_LEDGER",
        },
        "signals": signals[:20],
        "community": {
            "live_connected": bool(bounded_rooms),
            "bounded_rooms_connected": bool(bounded_rooms),
            "external_public_feed_connected": False,
            "status": "BOUNDED_GROUP_NUR_CONNECTED" if bounded_rooms else "LOCAL_NOTES_ONLY",
            "room_count": len(bounded_rooms),
            "rooms": bounded_rooms,
            "note_count": len(community_notes),
            "latest_note": ({
                "id": str(latest_note.id),
                "title": latest_note.title,
                "note": latest_note.note,
                "collaborator_label": latest_note.collaborator_label,
                "route": "/universe/community",
                "provenance_label": latest_note.provenance_label,
            } if latest_note else None),
            "honest_state": (
                "Persisted bounded Group NUR rooms are connected. External public "
                "community data is not connected."
                if bounded_rooms else
                "Community live data is not connected. Only owner-written local "
                "consultation notes appear here."
            ),
        },
        "what_changed": changed,
    }
