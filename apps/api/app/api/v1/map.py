"""Owner-derived NUR Map graph and persisted future-path predictions."""

import datetime as dt
import hashlib
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Identity, Scoped, require_csrf
from app.living.catalog import require_system
from app.living.service import (
    add_living_event,
    all_system_snapshots,
    owned_system_orbit,
)
from app.models import (
    AMProject,
    AMProjectTask,
    Decision,
    GlowAchievement,
    GlowTransaction,
    Goal,
    Insight,
    MapAnnotation,
    MapBlocker,
    MapDecisionOption,
    MapEdge,
    MapLayout,
    MapSuggestion,
    MapView,
    Objective,
    OmegaClaim,
    Outcome,
    Plan,
    PlanStep,
    Person,
    Prediction,
    ResearchSourceNote,
    Orbit,
    OrbitMember,
    SystemAction,
    TimelineEvent,
    WebSignalNote,
)

router = APIRouter(prefix="/map", tags=["map"])


class PredictPathIn(BaseModel):
    system_slug: str
    path_type: str = "continue"
    goal_id: uuid.UUID | None = None
    horizon_days: int = Field(default=30, ge=1, le=3650)


class MapSystemIn(BaseModel):
    system_slug: str


class MapSourceIn(BaseModel):
    source_id: uuid.UUID


def _stable_layout(node_id: str, kind: str, index: int) -> dict:
    if kind == "MASTER_STAR":
        return {"x": 0.0, "y": 0.0, "radius": 112, "exclusion_radius": 210}
    if kind == "SYSTEM":
        angle = -math.pi / 2 + index * (2 * math.pi / 7)
        return {
            "x": round(math.cos(angle) * 360, 2),
            "y": round(math.sin(angle) * 300, 2),
            "radius": 54,
            "exclusion_radius": 0,
        }
    seed = int(hashlib.sha256(node_id.encode()).hexdigest()[:12], 16)
    angle = (seed % 3600) / 3600 * 2 * math.pi
    ring = 470 + ((seed // 3600) % 4) * 115
    return {
        "x": round(math.cos(angle) * ring, 2),
        "y": round(math.sin(angle) * ring * 0.72, 2),
        "radius": 34 if kind in {"PERSON", "GROUP", "COUNCIL", "PROJECT"} else 24,
        "exclusion_radius": 0,
    }


def _system_signals(snapshot: dict, blockers: list) -> tuple[int, int, int, int]:
    """The four counts every System state is decided from, and nothing else."""
    open_blockers = sum(
        1
        for row in blockers
        if row.system_slug == snapshot["slug"] and row.status == "OPEN"
    )
    return (
        snapshot["active_goal_count"],
        snapshot["progress_percent"],
        snapshot["progress_sources"]["outcomes_returned"],
        open_blockers,
    )


def _system_state(snapshot: dict, blockers: list) -> str:
    """§10's state language, derived only from counts the owner's ledger holds.

    Deliberately not a score. "Creation — Active" is explainable; "Creation 83.7"
    is fake precision dressed as measurement, and §10 forbids it explicitly. Every
    branch here is reproducible from four integers and pairs with a sentence in
    `_system_state_reason` that cites those same integers.
    """
    goals, progress, outcomes, open_blockers = _system_signals(snapshot, blockers)
    if goals == 0 and progress == 0 and outcomes == 0:
        return "DORMANT"
    if open_blockers >= 2 or (open_blockers >= 1 and progress == 0):
        return "AT_RISK"
    if goals > 0 and progress == 0 and outcomes == 0:
        return "STALLED"
    if open_blockers >= 1 and outcomes > 0:
        return "RECOVERING"
    if outcomes > 0 and progress >= 60:
        return "STABLE"
    if outcomes > 0:
        return "ACTIVE"
    if progress > 0:
        return "BUILDING"
    return "UNCLEAR"


def _system_state_reason(snapshot: dict, blockers: list) -> str:
    """Why the System is in that state, in the owner's own numbers."""
    goals, progress, outcomes, open_blockers = _system_signals(snapshot, blockers)
    parts: list[str] = []
    parts.append(
        "No active goal" if goals == 0
        else f"{goals} active goal{'s' if goals != 1 else ''}"
    )
    parts.append(
        "no returned outcome yet" if outcomes == 0
        else f"{outcomes} returned outcome{'s' if outcomes != 1 else ''}"
    )
    parts.append(f"{progress}% verified progress")
    parts.append(
        "no unresolved blocker" if open_blockers == 0
        else f"{open_blockers} unresolved blocker{'s' if open_blockers != 1 else ''}"
    )
    return ". ".join([", ".join(parts[:3]), parts[3]]) + "."


async def _map_snapshot(
    db: Scoped, owner_user_id: uuid.UUID, *, view: MapView | None = None
) -> dict:
    systems = await all_system_snapshots(db, owner_user_id=owner_user_id)
    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id,
    ).order_by(Goal.created_at.desc()).limit(100))).scalars().all()
    objectives = (await db.execute(select(Objective).where(
        Objective.owner_user_id == owner_user_id,
    ).order_by(Objective.created_at.desc()).limit(200))).scalars().all()
    plans = (await db.execute(select(Plan).where(
        Plan.owner_user_id == owner_user_id,
    ).order_by(Plan.created_at.desc()).limit(80))).scalars().all()
    plan_steps = (await db.execute(select(PlanStep).where(
        PlanStep.owner_user_id == owner_user_id,
    ).order_by(PlanStep.created_at.desc()).limit(200))).scalars().all()
    actions = (await db.execute(select(SystemAction).where(
        SystemAction.owner_user_id == owner_user_id,
    ).order_by(SystemAction.created_at.desc()).limit(200))).scalars().all()
    outcomes = (await db.execute(select(Outcome).where(
        Outcome.owner_user_id == owner_user_id,
    ).order_by(Outcome.created_at.desc()).limit(100))).scalars().all()
    projects = (await db.execute(select(AMProject).where(
        AMProject.owner_user_id == owner_user_id,
    ).order_by(AMProject.updated_at.desc()).limit(80))).scalars().all()
    project_tasks = (await db.execute(select(AMProjectTask).where(
        AMProjectTask.owner_user_id == owner_user_id,
    ).order_by(AMProjectTask.priority.desc(), AMProjectTask.created_at).limit(300))).scalars().all()
    predictions = (await db.execute(select(Prediction).where(
        Prediction.owner_user_id == owner_user_id,
    ).order_by(Prediction.created_at.desc()).limit(50))).scalars().all()
    insights = (await db.execute(select(OmegaClaim).where(
        OmegaClaim.owner_user_id == owner_user_id,
    ).order_by(OmegaClaim.updated_at.desc()).limit(40))).scalars().all()
    dedicated_insights = (await db.execute(select(Insight).where(
        Insight.owner_user_id == owner_user_id,
        Insight.status.notin_(["REJECTED", "ARCHIVED"]),
    ).order_by(Insight.updated_at.desc()).limit(40))).scalars().all()
    social_orbits = (await db.execute(select(Orbit).where(
        Orbit.owner_user_id == owner_user_id,
        Orbit.kind.in_(["PERSON", "GROUP", "COUNCIL", "COMMUNITY"]),
        Orbit.status == "ACTIVE",
    ).order_by(Orbit.updated_at.desc()).limit(60))).scalars().all()
    social_orbit_ids = [row.id for row in social_orbits]
    orbit_members = (await db.execute(select(OrbitMember).where(
        OrbitMember.owner_user_id == owner_user_id,
        OrbitMember.orbit_id.in_(social_orbit_ids),
    ).order_by(OrbitMember.recent_activity_score.desc()).limit(200))).scalars().all()
    people_ids = list({row.person_id for row in orbit_members})
    people = (await db.execute(select(Person).where(
        Person.owner_user_id == owner_user_id,
        Person.id.in_(people_ids),
    ).order_by(Person.updated_at.desc()).limit(100))).scalars().all()
    timeline_events = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == owner_user_id,
        TimelineEvent.status.in_(["PLANNED", "DUE", "MISSED"]),
    ).order_by(TimelineEvent.scheduled_for.asc().nullslast()).limit(80))).scalars().all()
    research_sources = (await db.execute(select(ResearchSourceNote).where(
        ResearchSourceNote.owner_user_id == owner_user_id,
    ).order_by(ResearchSourceNote.updated_at.desc()).limit(30))).scalars().all()
    web_signals = (await db.execute(select(WebSignalNote).where(
        WebSignalNote.owner_user_id == owner_user_id,
    ).order_by(WebSignalNote.updated_at.desc()).limit(30))).scalars().all()
    achievements = (await db.execute(select(GlowAchievement).where(
        GlowAchievement.owner_user_id == owner_user_id,
    ).order_by(GlowAchievement.unlocked_at.desc()).limit(40))).scalars().all()
    total_glow = int((await db.execute(select(func.coalesce(
        func.sum(GlowTransaction.final_points), 0
    )).where(
        GlowTransaction.owner_user_id == owner_user_id,
        GlowTransaction.reversed.is_(False),
    ))).scalar_one())

    nodes: list[dict] = [{
        "id": "nur",
        "kind": "MASTER_STAR",
        "label": "NUR",
        "parent_id": None,
        "status": "ACTIVE",
        "data": {"total_glow": total_glow, "provenance_label": "OWNER_LEDGER"},
    }]
    edges: list[dict] = []
    # Proposals are kept out of `edges` on purpose. A candidate must render as a
    # candidate; merging it into structure is how an inference becomes a fact.
    candidate_edges: list[dict] = []
    for system in systems:
        node_id = f"system:{system['slug']}"
        nodes.append({
            "id": node_id,
            "kind": "SYSTEM",
            "label": system["title"],
            "parent_id": "nur",
            "status": "ACTIVE" if system["progress_percent"] > 0 else "READY",
            "data": {
                "orbit_id": system["orbit_id"],
                "progress_percent": system["progress_percent"],
                "glow_points": system["progress_sources"]["glow_points"],
                "outcomes_returned": system["progress_sources"]["outcomes_returned"],
                "active_goal_count": system["active_goal_count"],
                "blockers": system["blockers"],
                "next_move": system["next_move"],
                "prediction": system["prediction"],
            },
        })
        edges.append({
            "id": f"nur->{node_id}",
            "source": "nur",
            "target": node_id,
            "kind": "MASTER_TO_SYSTEM",
        })
    system_slug_by_orbit_id = {
        system["orbit_id"]: system["slug"] for system in systems
    }
    for goal in goals:
        node_id = f"goal:{goal.id}"
        system_id = f"system:{goal.system_slug}"
        nodes.append({
            "id": node_id,
            "kind": "GOAL",
            "label": goal.title,
            "parent_id": system_id,
            "status": goal.status,
            "data": {
                "progress_percent": goal.progress_percent,
                "target_date": goal.target_date,
                "why": goal.why,
            },
        })
        edges.append({
            "id": f"{system_id}->{node_id}",
            "source": system_id,
            "target": node_id,
            "kind": "SYSTEM_TO_GOAL",
        })
    goal_by_id = {row.id: row for row in goals}
    for objective in objectives:
        goal = goal_by_id.get(objective.goal_id)
        if goal is None:
            continue
        node_id = f"objective:{objective.id}"
        parent_id = f"goal:{goal.id}"
        nodes.append({
            "id": node_id,
            "kind": "OBJECTIVE",
            "label": objective.title,
            "parent_id": parent_id,
            "status": objective.status,
            "data": {"progress_percent": objective.progress_percent, "target_date": objective.target_date},
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "GOAL_TO_OBJECTIVE",
        })
    for plan in plans:
        node_id = f"plan:{plan.id}"
        system_slug = system_slug_by_orbit_id.get(
            str(plan.orbit_id) if plan.orbit_id else ""
        )
        parent_id = f"system:{system_slug}" if system_slug else "nur"
        nodes.append({
            "id": node_id,
            "kind": "PLAN",
            "label": plan.title,
            "parent_id": parent_id,
            "status": plan.status,
            "data": {
                "orbit_id": str(plan.orbit_id) if plan.orbit_id else None,
                "system_slug": system_slug,
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SYSTEM_TO_PLAN" if system_slug else "MASTER_TO_PLAN",
        })
    for step in plan_steps:
        node_id = f"plan-step:{step.id}"
        parent_id = f"plan:{step.plan_id}"
        nodes.append({
            "id": node_id,
            "kind": "PLAN_STEP",
            "label": step.title,
            "parent_id": parent_id,
            "status": "COMPLETED" if step.done else "OPEN",
            "data": {"position": step.position, "done_at": step.done_at},
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "PLAN_TO_STEP",
        })
    for action in actions:
        if action.status not in {"OPEN", "MISSED"}:
            continue
        node_id = f"action:{action.id}"
        parent_id = f"system:{action.system_slug}"
        nodes.append({
            "id": node_id,
            "kind": "BLOCKER" if action.status == "MISSED" else "ACTION",
            "label": action.title,
            "parent_id": parent_id,
            "status": action.status,
            "data": {"due_at": action.due_at, "effort_minutes": action.effort_minutes},
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SYSTEM_TO_BLOCKER" if action.status == "MISSED" else "SYSTEM_TO_ACTION",
        })
    for outcome in outcomes:
        system_slug = (outcome.structured_measurements or {}).get("system_slug")
        if system_slug not in system_slug_by_orbit_id.values():
            continue
        node_id = f"outcome:{outcome.id}"
        parent_id = f"system:{system_slug}"
        nodes.append({
            "id": node_id,
            "kind": "OUTCOME",
            "label": outcome.observed_result,
            "parent_id": parent_id,
            "status": "RETURNED",
            "data": {
                "confidence": outcome.confidence,
                "self_reported": outcome.self_reported,
                "system_action_id": (outcome.structured_measurements or {}).get(
                    "system_action_id"
                ),
                "provenance_label": "OWNER_RETURNED_OUTCOME",
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SYSTEM_TO_OUTCOME",
        })
    for project in projects:
        node_id = f"project:{project.id}"
        parent_id = f"system:{project.system_slug}" if project.system_slug else "nur"
        nodes.append({
            "id": node_id,
            "kind": "PROJECT",
            "label": project.title,
            "parent_id": parent_id,
            "status": project.status,
            "data": {
                "orbit_id": str(project.orbit_id),
                "objective": project.objective,
                "deadline": project.deadline,
                "budget_cents": project.budget_cents,
                "provenance_label": "OWNER_PROJECT_LEDGER",
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SYSTEM_TO_PROJECT" if project.system_slug else "MASTER_TO_PROJECT",
        })
    for task in project_tasks:
        parent_id = f"project:{task.project_id}"
        node_id = f"project-task:{task.id}"
        nodes.append({
            "id": node_id,
            "kind": "PROJECT_TASK",
            "label": task.title,
            "parent_id": parent_id,
            "status": task.status,
            "data": {
                "priority": task.priority,
                "assigned_role": task.assigned_role,
                "due_at": task.due_at,
                "acceptance_criteria": task.acceptance_criteria,
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "PROJECT_TO_TASK",
        })
    for prediction in predictions:
        node_id = f"prediction:{prediction.id}"
        parent_id = (
            f"system:{prediction.expected_observation.get('system_slug')}"
            if prediction.expected_observation.get("system_slug") else "nur"
        )
        nodes.append({
            "id": node_id,
            "kind": "PREDICTION",
            "label": prediction.statement,
            "parent_id": parent_id,
            "status": prediction.status,
            "data": prediction.expected_observation,
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "PATH_PREDICTION",
        })
    for person in people:
        node_id = f"person:{person.id}"
        nodes.append({
            "id": node_id,
            "kind": "PERSON",
            "label": person.display_name,
            "parent_id": "nur",
            "status": "ACTIVE",
            "data": {
                "handle": person.handle,
                "relationship_type": person.relationship_type,
                "privacy_scope": person.privacy_scope,
                "provenance_label": "OWNER_SOCIAL_LEDGER",
            },
        })
        edges.append({
            "id": f"nur->{node_id}",
            "source": "nur",
            "target": node_id,
            "kind": "INVOLVES_PERSON",
        })
    social_ids = {row.id for row in social_orbits}
    for orbit in social_orbits:
        node_id = f"orbit:{orbit.id}"
        parent_id = f"system:{orbit.system_slug}" if orbit.system_slug else "nur"
        nodes.append({
            "id": node_id,
            "kind": orbit.kind,
            "label": orbit.title,
            "parent_id": parent_id,
            "status": orbit.status,
            "data": {
                "description": orbit.description,
                "privacy_scope": orbit.privacy_scope,
                "provenance_label": "OWNER_SOCIAL_LEDGER",
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SYSTEM_TO_ORBIT" if orbit.system_slug else "MASTER_TO_ORBIT",
        })
    for member in orbit_members:
        edges.append({
            "id": f"orbit:{member.orbit_id}->person:{member.person_id}",
            "source": f"orbit:{member.orbit_id}",
            "target": f"person:{member.person_id}",
            "kind": "ORBIT_MEMBER",
            "data": {
                "role": member.role,
                "unresolved_count": member.unresolved_count,
                "shared_goal_count": member.shared_goal_count,
            },
        })
    for insight in dedicated_insights:
        node_id = f"dedicated-insight:{insight.id}"
        parent_id = (
            f"system:{insight.affected_system_slug}"
            if insight.affected_system_slug else "nur"
        )
        nodes.append({
            "id": node_id,
            "kind": "INSIGHT",
            "label": insight.title,
            "parent_id": parent_id,
            "status": insight.status,
            "data": {
                "insight_type": insight.insight_type,
                "confidence": insight.confidence,
                "evidence_count": len(insight.evidence),
                "suggested_action": insight.suggested_action,
                "provenance_label": insight.provenance_label,
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "GENERATED_INSIGHT",
        })
    for source in research_sources:
        node_id = f"research-source:{source.id}"
        nodes.append({
            "id": node_id,
            "kind": "RESEARCH_SOURCE",
            "label": source.title,
            "parent_id": "nur",
            "status": source.trust_state,
            "data": {
                "url": source.url,
                "provenance_label": source.provenance_label,
            },
        })
        edges.append({
            "id": f"nur->{node_id}",
            "source": "nur",
            "target": node_id,
            "kind": "CAME_FROM_RESEARCH",
        })
    for signal in web_signals:
        node_id = f"web-signal:{signal.id}"
        nodes.append({
            "id": node_id,
            "kind": "WEB_SIGNAL",
            "label": signal.title,
            "parent_id": "nur",
            "status": "SAVED",
            "data": {"url": signal.url, "provenance_label": signal.provenance_label},
        })
        edges.append({
            "id": f"nur->{node_id}",
            "source": "nur",
            "target": node_id,
            "kind": "WEB_SIGNAL_SAVED",
        })
    for event in timeline_events:
        node_id = f"timeline:{event.id}"
        if event.system_slug:
            parent_id = f"system:{event.system_slug}"
        elif event.project_id:
            parent_id = f"project:{event.project_id}"
        elif event.goal_id:
            parent_id = f"goal:{event.goal_id}"
        elif event.orbit_id in social_ids:
            parent_id = f"orbit:{event.orbit_id}"
        else:
            parent_id = "nur"
        nodes.append({
            "id": node_id,
            "kind": "TIMELINE_EVENT",
            "label": event.title,
            "parent_id": parent_id,
            "status": event.status,
            "data": {
                "time_kind": event.time_kind,
                "scheduled_for": event.scheduled_for,
                "importance": event.importance,
                "provenance_label": "OWNER_TIMELINE_LEDGER",
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SCHEDULED_ON_TIMELINE",
        })
    for insight in insights:
        nodes.append({
            "id": f"insight:{insight.id}",
            "kind": "INSIGHT",
            "label": insight.claim_text,
            "parent_id": "nur",
            "status": insight.truth_status,
            "data": {
                "confidence": insight.confidence,
                "provenance_label": f"OMEGA_{insight.truth_status}",
            },
        })
    for achievement in achievements:
        nodes.append({
            "id": f"achievement:{achievement.id}",
            "kind": "GLOW_MILESTONE",
            "label": achievement.achievement_metadata.get("label", achievement.achievement_key),
            "parent_id": "nur",
            "status": "UNLOCKED",
            "data": {"unlocked_at": achievement.unlocked_at},
        })

    # ── Decisions. The canonical `decisions` row carries the question; the
    # options, trade-offs and reversibility live in `map_decision_options`,
    # which is the half a decision was missing. An unresolved fork is the one
    # thing on this map that is waiting on the owner rather than on work. ──
    decisions = (await db.execute(select(Decision).where(
        Decision.owner_user_id == owner_user_id,
    ).order_by(Decision.created_at.desc()).limit(80))).scalars().all()
    decision_ids = [row.id for row in decisions]
    options = (await db.execute(select(MapDecisionOption).where(
        MapDecisionOption.owner_user_id == owner_user_id,
        MapDecisionOption.decision_id.in_(decision_ids),
    ).order_by(MapDecisionOption.position))).scalars().all() if decision_ids else []
    options_by_decision: dict[uuid.UUID, list[MapDecisionOption]] = {}
    for option in options:
        options_by_decision.setdefault(option.decision_id, []).append(option)
    for decision in decisions:
        node_id = f"decision:{decision.id}"
        own = options_by_decision.get(decision.id, [])
        chosen = next((row for row in own if row.chosen_at is not None), None)
        system_slug = system_slug_by_orbit_id.get(str(decision.orbit_id))
        parent_id = f"system:{system_slug}" if system_slug else "nur"
        nodes.append({
            "id": node_id,
            "kind": "DECISION",
            "label": decision.statement,
            "parent_id": parent_id,
            "status": "RESOLVED" if chosen else "UNRESOLVED",
            "data": {
                "option_count": len(own),
                "chosen_option_id": str(chosen.id) if chosen else None,
                "rationale": decision.rationale,
                "decision_status": decision.status,
                "provenance_label": "OWNER_DECISION_LEDGER",
            },
        })
        edges.append({
            "id": f"{parent_id}->{node_id}",
            "source": parent_id,
            "target": node_id,
            "kind": "SYSTEM_TO_DECISION" if system_slug else "MASTER_TO_DECISION",
        })
        for option in own:
            option_node = f"decision-option:{option.id}"
            nodes.append({
                "id": option_node,
                "kind": "DECISION_OPTION",
                "label": option.label,
                "parent_id": node_id,
                "status": "CHOSEN" if option.chosen_at else "OPEN",
                "data": {
                    "reversibility": option.reversibility,
                    "time_horizon": option.time_horizon,
                    "effort": option.effort,
                    "benefit_count": len(option.benefits or []),
                    "cost_count": len(option.costs or []),
                    "risk_count": len(option.risks or []),
                    "evidence_count": len(option.evidence or []),
                },
            })
            edges.append({
                "id": f"{node_id}->{option_node}",
                "source": node_id,
                "target": option_node,
                "kind": "LEADS_TO_OPTION",
            })

    # ── Addressable blockers. Distinct from the MISSED-action blockers above:
    # these know what they obstruct, what evidence they rest on, and whether the
    # owner has agreed they are real. A PROPOSED blocker is not asserted. ──
    blockers = (await db.execute(select(MapBlocker).where(
        MapBlocker.owner_user_id == owner_user_id,
        MapBlocker.status.notin_(["DISMISSED"]),
    ).order_by(MapBlocker.updated_at.desc()).limit(120))).scalars().all()
    for blocker in blockers:
        node_id = f"blocker:{blocker.id}"
        parent_id = (
            f"system:{blocker.system_slug}" if blocker.system_slug else "nur"
        )
        nodes.append({
            "id": node_id,
            "kind": "BLOCKER",
            "label": blocker.title,
            "parent_id": parent_id,
            "status": blocker.status,
            "data": {
                "category": blocker.category,
                "basis": blocker.basis,
                "confirmed_by_owner": blocker.confirmed_by_owner,
                "evidence_count": len(blocker.evidence or []),
                "affects": blocker.affects,
                "response_count": len(blocker.possible_responses or []),
                "addressable": True,
                "provenance_label": f"BLOCKER_{blocker.basis}",
            },
        })
        edges.append({
            "id": f"{node_id}->{parent_id}",
            "source": node_id,
            "target": parent_id,
            "kind": "BLOCKS",
        })
        # What the blocker actually obstructs, drawn from the row rather than
        # inferred from where it happens to sit on the canvas.
        for ref in (blocker.affects or []):
            if not isinstance(ref, dict):
                continue
            ref_type, ref_id = ref.get("type"), ref.get("id")
            if not ref_type or not ref_id:
                continue
            edges.append({
                "id": f"{node_id}->{ref_type}:{ref_id}",
                "source": node_id,
                "target": f"{ref_type}:{ref_id}",
                "kind": "BLOCKS",
            })

    # ── Semantic edges the owner drew or accepted. Unconfirmed ones are held
    # back and returned as candidates, because a proposal is not structure. ──
    semantic = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
    ).order_by(MapEdge.created_at.desc()).limit(400))).scalars().all()
    node_ids = {row["id"] for row in nodes}
    for edge in semantic:
        source = f"{edge.source_ref_type}:{edge.source_ref_id}"
        target = f"{edge.target_ref_type}:{edge.target_ref_id}"
        payload = {
            "id": f"semantic:{edge.id}",
            "source": source,
            "target": target,
            "kind": edge.edge_type,
            "semantic": True,
            "direction": edge.direction,
            "user_confirmed": edge.user_confirmed,
            "inference_source": edge.inference_source,
            "confidence": float(edge.confidence) if edge.confidence is not None else None,
            "note": edge.note,
            "resolvable": source in node_ids and target in node_ids,
        }
        if edge.user_confirmed:
            edges.append(payload)
        else:
            candidate_edges.append(payload)

    annotation_counts = dict((await db.execute(
        select(
            func.concat(
                MapAnnotation.entity_ref_type, ":", MapAnnotation.entity_ref_id
            ),
            func.count(),
        )
        .where(MapAnnotation.owner_user_id == owner_user_id)
        .group_by(MapAnnotation.entity_ref_type, MapAnnotation.entity_ref_id)
    )).all())
    for node in nodes:
        count = annotation_counts.get(node["id"], 0)
        if count:
            node["data"]["annotation_count"] = count

    pending = (await db.execute(select(MapSuggestion).where(
        MapSuggestion.owner_user_id == owner_user_id,
        MapSuggestion.status == "PENDING",
        MapSuggestion.suppressed_kind.is_(False),
    ).order_by(MapSuggestion.created_at.desc()).limit(60))).scalars().all()

    system_index = 0
    for index, node in enumerate(nodes):
        layout_index = system_index if node["kind"] == "SYSTEM" else index
        node["data"].setdefault(
            "layout", _stable_layout(node["id"], node["kind"], layout_index)
        )
        if node["kind"] == "SYSTEM":
            system_index += 1

    # ── Owner-positioned layout wins over the deterministic ring. Dragging a
    # node changes only where it sits: the override touches x/y/pinned and never
    # `parent_id`, so position can never silently reassign a System. ──
    layout_overrides = 0
    if view is not None:
        saved = (await db.execute(select(MapLayout).where(
            MapLayout.owner_user_id == owner_user_id,
            MapLayout.map_view_id == view.id,
        ))).scalars().all()
        by_ref = {
            f"{row.node_ref_type}:{row.node_ref_id}": row for row in saved
        }
        for node in nodes:
            row = by_ref.get(node["id"]) or (
                by_ref.get("nur:nur") if node["id"] == "nur" else None
            )
            if row is None:
                continue
            node["data"]["layout"] = {
                **node["data"]["layout"],
                "x": row.x,
                "y": row.y,
            }
            node["data"]["pinned"] = row.pinned
            node["data"]["collapsed"] = row.collapsed
            node["data"]["layer"] = row.layer
            layout_overrides += 1

    return {
        "generated_at": dt.datetime.now(dt.UTC),
        "provenance_label": "OWNER_LEDGER_DERIVED_GRAPH",
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "systems": len(systems),
            "goals": len(goals),
            "objectives": len(objectives),
            "plans": len(plans),
            "projects": len(projects),
            "project_tasks": len(project_tasks),
            "people": len(people),
            "social_orbits": len(social_orbits),
            "insights": len(dedicated_insights) + len(insights),
            "timeline_events": len(timeline_events),
            "research_sources": len(research_sources),
            "web_signals": len(web_signals),
            "open_predictions": sum(row.status == "OPEN" for row in predictions),
            "decisions": len(decisions),
            "unresolved_decisions": sum(
                1
                for row in decisions
                if not any(
                    option.chosen_at is not None
                    for option in options_by_decision.get(row.id, [])
                )
            ),
            "blockers": len(blockers),
            "open_blockers": sum(row.status == "OPEN" for row in blockers),
            "proposed_blockers": sum(row.status == "PROPOSED" for row in blockers),
            "semantic_edges": sum(1 for row in semantic if row.user_confirmed),
            "candidate_edges": len(candidate_edges),
            "pending_suggestions": len(pending),
            "layout_overrides": layout_overrides,
        },
        "nodes": nodes,
        "edges": edges,
        # ── §37: the field the canvas draws System territory from. Driven from
        # the canonical catalog, never a hardcoded list, so the Map shows exactly
        # the Systems NUR actually has (see CONFLICT-010). ──
        "system_regions": [
            {
                "slug": row["slug"],
                "title": row["title"],
                "node_id": f"system:{row['slug']}",
                "state": _system_state(row, blockers),
                "state_reason": _system_state_reason(row, blockers),
                "progress_percent": row["progress_percent"],
                "active_goal_count": row["active_goal_count"],
                "blocker_count": sum(
                    1
                    for blocker in blockers
                    if blocker.system_slug == row["slug"] and blocker.status == "OPEN"
                ),
                "next_move": row["next_move"],
                "layout": _stable_layout(f"system:{row['slug']}", "SYSTEM", index),
            }
            for index, row in enumerate(systems)
        ],
        # Candidates travel separately from structure the whole way to the canvas.
        "suggested_changes": {
            "candidate_edges": candidate_edges,
            "suggestions": [
                {
                    "id": str(row.id),
                    "suggestion_type": row.suggestion_type,
                    "source_refs": row.source_refs,
                    "proposed_payload": row.proposed_payload,
                    "explanation": row.explanation,
                    "may_be_wrong_about": row.may_be_wrong_about,
                    "confidence": (
                        float(row.confidence) if row.confidence is not None else None
                    ),
                    "created_at": row.created_at,
                    "requires_acceptance": True,
                }
                for row in pending
            ],
        },
        "selection_summary": None,
        "permissions": {
            "can_edit_layout": True,
            "can_draw_edges": True,
            "can_accept_suggestions": True,
            # Nothing in Map may move an owner's own decision for them.
            "can_resolve_decisions": True,
            "nur_may_assert_sensitive_blockers": False,
        },
        "staleness": {
            "view_id": str(view.id) if view is not None else None,
            "generated_at": dt.datetime.now(dt.UTC),
            "layout_is_owner_positioned": layout_overrides > 0,
            "unresolvable_semantic_edges": sum(
                1 for row in edges if row.get("semantic") and not row.get("resolvable")
            ),
        },
        "future_paths": [
            {
                "system_slug": row["slug"],
                "current_progress": row["progress_percent"],
                "if_continued": row["prediction"]["if_followed"],
                "if_ignored": row["prediction"]["if_ignored"],
                "basis": row["prediction"]["basis"],
            }
            for row in systems
        ],
    }


@router.get("")
async def map_graph(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    return await _map_snapshot(db, owner_user_id)


@router.post("/rebuild", dependencies=[Depends(require_csrf)])
async def rebuild_map(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    snapshot = await _map_snapshot(db, owner_user_id)
    snapshot["rebuild"] = {
        "status": "REBUILT_FROM_OWNER_LEDGER",
        "persisted_source_count": snapshot["counts"]["nodes"] - 1,
        "note": "The Map is a calculated view; no duplicate graph store was created.",
    }
    return snapshot


async def _persist_map_focus(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    node_id: str,
    source_kind: str,
    source_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
) -> dict:
    snapshot = await _map_snapshot(db, owner_user_id)
    node = next((row for row in snapshot["nodes"] if row["id"] == node_id), None)
    if node is None:
        raise HTTPException(404, "That owner source is not available on the Map.")
    event = add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        timeline_kind="MAP_FOCUS_CREATED",
        content=f"Map focus opened for {node['label']}.",
        object_type=source_kind.lower(),
        object_id=source_id,
        metadata={
            "map_node_id": node_id,
            "source_kind": source_kind,
            "provenance_label": "OWNER_LEDGER_MAP_FOCUS",
        },
    )
    await db.commit()
    return {
        "node": node,
        "map_event_id": event.id,
        "source_kind": source_kind,
        "appears_on_map": True,
        "graph_counts": snapshot["counts"],
        "provenance_label": "OWNER_LEDGER_MAP_FOCUS",
    }


@router.post("/from-system", status_code=201, dependencies=[Depends(require_csrf)])
async def map_from_system(payload: MapSystemIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    try:
        definition = require_system(payload.system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    orbit = await owned_system_orbit(db, owner_user_id=owner_user_id, system=definition)
    return await _persist_map_focus(
        db,
        owner_user_id=owner_user_id,
        node_id=f"system:{definition.slug}",
        source_kind="SYSTEM",
        source_id=orbit.id,
        orbit_id=orbit.id,
    )


@router.post("/from-goal", status_code=201, dependencies=[Depends(require_csrf)])
async def map_from_goal(payload: MapSourceIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(Goal).where(
        Goal.id == payload.source_id,
        Goal.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Goal not found.")
    return await _persist_map_focus(
        db,
        owner_user_id=owner_user_id,
        node_id=f"goal:{row.id}",
        source_kind="GOAL",
        source_id=row.id,
        orbit_id=row.orbit_id,
    )


@router.post("/from-plan", status_code=201, dependencies=[Depends(require_csrf)])
async def map_from_plan(payload: MapSourceIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(Plan).where(
        Plan.id == payload.source_id,
        Plan.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Plan not found.")
    return await _persist_map_focus(
        db,
        owner_user_id=owner_user_id,
        node_id=f"plan:{row.id}",
        source_kind="PLAN",
        source_id=row.id,
        orbit_id=row.orbit_id,
    )


@router.post("/from-insight", status_code=201, dependencies=[Depends(require_csrf)])
async def map_from_insight(payload: MapSourceIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(Insight).where(
        Insight.id == payload.source_id,
        Insight.owner_user_id == owner_user_id,
        Insight.status.notin_(["REJECTED", "ARCHIVED"]),
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Insight not found.")
    return await _persist_map_focus(
        db,
        owner_user_id=owner_user_id,
        node_id=f"dedicated-insight:{row.id}",
        source_kind="INSIGHT",
        source_id=row.id,
        orbit_id=row.orbit_id,
    )


@router.post("/predict-path", status_code=201, dependencies=[Depends(require_csrf)])
async def predict_path(
    payload: PredictPathIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    try:
        definition = require_system(payload.system_slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    path_type = payload.path_type.lower()
    if path_type not in {"continue", "ignore", "easier", "ambitious"}:
        raise HTTPException(422, "path_type must be continue, ignore, easier, or ambitious.")
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    system = next(
        row for row in await all_system_snapshots(db, owner_user_id=owner_user_id)
        if row["slug"] == payload.system_slug
    )
    goal = None
    if payload.goal_id:
        goal = (await db.execute(select(Goal).where(
            Goal.id == payload.goal_id,
            Goal.owner_user_id == owner_user_id,
            Goal.system_slug == payload.system_slug,
        ))).scalar_one_or_none()
        if goal is None:
            raise HTTPException(404, "Goal not found in this System.")
    statements = {
        "continue": definition.followed_prediction,
        "ignore": definition.ignored_prediction,
        "easier": "A smaller capacity-matched move is likely to preserve continuity and produce evidence.",
        "ambitious": (
            "An ambitious move may accelerate progress, but its failure risk rises when current "
            f"System progress is only {system['progress_percent']}%."
        ),
    }
    prediction = Prediction(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        statement=statements[path_type],
        expected_observation={
            "system_slug": payload.system_slug,
            "path_type": path_type,
            "horizon_days": payload.horizon_days,
            "current_progress": system["progress_percent"],
            "goal_id": str(goal.id) if goal else None,
            "observable": "System progress, completed actions, returned outcomes, and missed actions.",
            "provenance_label": "DETERMINISTIC_HYPOTHESIS",
        },
    )
    db.add(prediction)
    await db.flush()
    event = add_living_event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        timeline_kind="PREDICTION_MADE",
        content=prediction.statement,
        object_type="prediction",
        object_id=prediction.id,
        metadata={"system_slug": payload.system_slug, "path_type": path_type},
    )
    await db.flush()
    prediction.source_event_id = event.id
    await db.commit()
    return {
        "id": prediction.id,
        "statement": prediction.statement,
        "expected_observation": prediction.expected_observation,
        "status": prediction.status,
        "created_at": prediction.created_at,
        "provenance_label": "DETERMINISTIC_HYPOTHESIS",
    }
