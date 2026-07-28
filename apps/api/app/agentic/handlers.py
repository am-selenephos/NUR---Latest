"""Read-only tool handlers, bound to the services that already exist.

Every handler here delegates to the same function the HTTP route uses. That
import direction — agentic reaching into `api.v1` — is not the tidiest layering,
and it is deliberate. The alternative is a second implementation of the same
query, and a second implementation drifts from the first silently: the route and
the tool would answer the same question differently, and nothing would fail.
Sharing one function makes drift impossible rather than merely unlikely.

Only R0 tools are bound in this module. Every handler takes an already
RLS-scoped session and an owner id and returns plain data. None of them writes,
which is asserted structurally by the tests rather than promised here.

Tools without a handler stay unbound on purpose. `registry.handler` raises
`UnboundToolError` for those, so an unimplemented tool fails loudly instead of
returning an empty result a planner would treat as a completed step.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic import registry


async def get_map_neighbourhood(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    node_id: str | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    """The graph around one node, or the whole owner graph when none is named.

    Delegates to the map endpoint's own assembly so the tool and the Map lens
    can never disagree about what the owner's graph contains.
    """
    from app.api.v1.map import _map_snapshot

    snapshot = await _map_snapshot(db, owner_user_id)
    if not node_id:
        return snapshot

    nodes = {node["id"]: node for node in snapshot["nodes"]}
    if node_id not in nodes:
        # An unknown node is not an empty neighbourhood — saying "nothing is
        # connected to this" when the node does not exist would be a false
        # answer rather than a null one.
        return {
            "found": False,
            "node_id": node_id,
            "provenance_label": snapshot["provenance_label"],
        }

    keep = {node_id}
    frontier = {node_id}
    for _ in range(max(0, depth)):
        nxt: set[str] = set()
        for edge in snapshot["edges"]:
            if edge["source"] in frontier:
                nxt.add(edge["target"])
            elif edge["target"] in frontier:
                nxt.add(edge["source"])
        nxt -= keep
        if not nxt:
            break
        keep |= nxt
        frontier = nxt

    return {
        "found": True,
        "node_id": node_id,
        "depth": depth,
        "nodes": [nodes[key] for key in keep if key in nodes],
        "edges": [
            edge
            for edge in snapshot["edges"]
            if edge["source"] in keep and edge["target"] in keep
        ],
        "provenance_label": snapshot["provenance_label"],
    }


async def get_timeline(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Timeline events in a bounded window.

    The limit is clamped rather than trusted. A planner asking for everything
    would otherwise pull an owner's entire history into a model's context, which
    is both a cost problem and a minimisation problem.
    """
    from app.models.intelligence import TimelineEvent

    bounded = max(1, min(int(limit), 200))
    rows = (
        await db.execute(
            select(TimelineEvent)
            .where(TimelineEvent.owner_user_id == owner_user_id)
            .order_by(TimelineEvent.created_at.desc())
            .limit(bounded)
        )
    ).scalars().all()

    return {
        "count": len(rows),
        "limit": bounded,
        "events": [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "title": row.title,
                "time_kind": row.time_kind,
                "status": row.status,
                "importance": row.importance,
                "system_slug": row.system_slug,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else None,
            }
            for row in rows
        ],
        "provenance_label": "Owner timeline ledger",
    }


async def search_approved_memory(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Approved personal memory only — never candidates.

    The filter is the entire point of the tool. A candidate is something NUR
    proposed and the owner has not accepted; returning one here would let model
    output re-enter a later run wearing the authority of owner truth.
    """
    from app.models.memory import PersonalMemory

    bounded = max(1, min(int(limit), 100))
    statement = select(PersonalMemory).where(
        PersonalMemory.owner_user_id == owner_user_id
    )
    if hasattr(PersonalMemory, "status"):
        statement = statement.where(PersonalMemory.status == "APPROVED")
    if query:
        statement = statement.where(PersonalMemory.content.ilike(f"%{query}%"))

    rows = (await db.execute(statement.limit(bounded))).scalars().all()
    return {
        "count": len(rows),
        "query": query,
        "memories": [{"id": str(row.id), "content": row.content} for row in rows],
        "provenance_label": "Owner-approved memory only; candidates are excluded",
    }


def _owned(statement, model, owner_user_id):
    """Add an explicit owner filter when the model carries one.

    RLS already confines the session, so this is defence in depth rather than
    the primary control. It costs nothing and means a handler run against a
    session whose context was never set returns nothing instead of everything.
    """
    column = getattr(model, "owner_user_id", None)
    return statement.where(column == owner_user_id) if column is not None else statement


async def get_today_state(db: AsyncSession, owner_user_id: uuid.UUID) -> dict[str, Any]:
    """The owner's current day. Delegates to the same snapshot the Today route
    serves, so the tool and the screen cannot disagree."""
    from app.api.v1.living import today_snapshot

    return await today_snapshot(db, owner_user_id=owner_user_id)


async def get_plan(
    db: AsyncSession, owner_user_id: uuid.UUID, *, plan_id: str | None = None
) -> dict[str, Any]:
    from app.models.cognition import Plan, PlanStep

    statement = _owned(select(Plan), Plan, owner_user_id)
    if plan_id:
        statement = statement.where(Plan.id == uuid.UUID(plan_id))
    plans = (await db.execute(statement.limit(20))).scalars().all()
    if plan_id and not plans:
        return {"found": False, "plan_id": plan_id}

    out = []
    for plan in plans:
        steps = (
            await db.execute(
                select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.position)
            )
        ).scalars().all()
        out.append(
            {
                "id": str(plan.id),
                "title": plan.title,
                "status": plan.status,
                "steps": [
                    {"id": str(s.id), "title": s.title, "position": s.position, "done": s.done}
                    for s in steps
                ],
            }
        )
    return {"found": True, "count": len(out), "plans": out}


async def get_system_snapshot(
    db: AsyncSession, owner_user_id: uuid.UUID, *, system_slug: str
) -> dict[str, Any]:
    """One Star System's standing: its founder-locked definition plus the
    owner's goals inside it. The definition comes from the catalog rather than
    the database because it is not owner data and must not drift per owner."""
    from app.living.catalog import SYSTEMS
    from app.models.living import Goal

    definition = next((s for s in SYSTEMS if s.slug == system_slug), None)
    if definition is None:
        return {"found": False, "system_slug": system_slug}

    goals = (
        await db.execute(
            _owned(select(Goal), Goal, owner_user_id).where(Goal.system_slug == system_slug)
        )
    ).scalars().all()
    return {
        "found": True,
        "system_slug": system_slug,
        "title": definition.title,
        "definition": definition.definition,
        "goals": [
            {
                "id": str(g.id),
                "title": g.title,
                "status": g.status,
                "progress_percent": g.progress_percent,
            }
            for g in goals
        ],
    }


async def get_orbit(
    db: AsyncSession, owner_user_id: uuid.UUID, *, orbit_id: str | None = None
) -> dict[str, Any]:
    from app.models.orbit import Orbit

    statement = _owned(select(Orbit), Orbit, owner_user_id)
    if orbit_id:
        statement = statement.where(Orbit.id == uuid.UUID(orbit_id))
    rows = (await db.execute(statement.limit(50))).scalars().all()
    if orbit_id and not rows:
        return {"found": False, "orbit_id": orbit_id}
    return {
        "found": True,
        "count": len(rows),
        "orbits": [
            {
                "id": str(r.id),
                "title": r.title,
                "kind": str(r.kind),
                "status": str(r.status),
                "system_slug": r.system_slug,
                # privacy_scope is included because a tool result that omits it
                # would let a later step treat a shared Orbit as private.
                "privacy_scope": str(r.privacy_scope),
            }
            for r in rows
        ],
    }


async def get_project(
    db: AsyncSession, owner_user_id: uuid.UUID, *, project_id: str | None = None
) -> dict[str, Any]:
    from app.models.projects import AMProject

    statement = _owned(select(AMProject), AMProject, owner_user_id)
    if project_id:
        statement = statement.where(AMProject.id == uuid.UUID(project_id))
    rows = (await db.execute(statement.limit(50))).scalars().all()
    if project_id and not rows:
        return {"found": False, "project_id": project_id}
    return {
        "found": True,
        "count": len(rows),
        "projects": [
            {
                "id": str(r.id),
                "title": r.title,
                "objective": r.objective,
                "status": str(r.status),
                "system_slug": r.system_slug,
            }
            for r in rows
        ],
    }


async def get_project_evidence(
    db: AsyncSession, owner_user_id: uuid.UUID, *, project_id: str
) -> dict[str, Any]:
    """Evidence attached to a Project, with its verification status.

    `verification_status` is returned on every row and never filtered away: an
    unverified piece of evidence is still evidence, and hiding the distinction
    would let a later step cite it as though it had been checked.
    """
    from app.models.projects import AMProjectEvidence

    rows = (
        await db.execute(
            _owned(select(AMProjectEvidence), AMProjectEvidence, owner_user_id)
            .where(AMProjectEvidence.project_id == uuid.UUID(project_id))
            .limit(100)
        )
    ).scalars().all()
    return {
        "project_id": project_id,
        "count": len(rows),
        "evidence": [
            {
                "id": str(r.id),
                "kind": r.evidence_kind,
                "summary": r.summary,
                "verification_status": r.verification_status,
                "verifier": r.verifier,
            }
            for r in rows
        ],
    }


async def get_insight(
    db: AsyncSession, owner_user_id: uuid.UUID, *, insight_id: str | None = None
) -> dict[str, Any]:
    """An Insight with its doubt attached.

    `what_nur_may_be_wrong_about` and `counter_evidence` are returned alongside
    the claim, never separately. An Insight quoted without its own account of
    where it might be wrong is exactly the unlabelled certainty this product is
    built to refuse.
    """
    from app.models.intelligence import Insight

    statement = _owned(select(Insight), Insight, owner_user_id)
    if insight_id:
        statement = statement.where(Insight.id == uuid.UUID(insight_id))
    rows = (await db.execute(statement.limit(25))).scalars().all()
    if insight_id and not rows:
        return {"found": False, "insight_id": insight_id}
    return {
        "found": True,
        "count": len(rows),
        "insights": [
            {
                "id": str(r.id),
                "title": r.title,
                "claim": r.claim,
                "status": r.status,
                "confidence": r.confidence,
                "confidence_meaning": "Source coverage and evidence strength, not guaranteed truth",
                "evidence": r.evidence,
                "counter_evidence": r.counter_evidence,
                "what_nur_may_be_wrong_about": r.what_nur_may_be_wrong_about,
                "provenance_label": r.provenance_label,
            }
            for r in rows
        ],
    }


def bind_read_only_handlers() -> tuple[str, ...]:
    """Attach the handlers above. Returns the keys that are now callable.

    Called explicitly rather than at import time so a test can assert what is
    bound and what deliberately is not.
    """
    registry.bind("get_map_neighbourhood", get_map_neighbourhood)
    registry.bind("get_timeline", get_timeline)
    registry.bind("search_approved_memory", search_approved_memory)
    registry.bind("get_today_state", get_today_state)
    registry.bind("get_plan", get_plan)
    registry.bind("get_system_snapshot", get_system_snapshot)
    registry.bind("get_orbit", get_orbit)
    registry.bind("get_project", get_project)
    registry.bind("get_project_evidence", get_project_evidence)
    registry.bind("get_insight", get_insight)
    return registry.bound_keys()
