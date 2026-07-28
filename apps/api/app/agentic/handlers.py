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


def bind_read_only_handlers() -> tuple[str, ...]:
    """Attach the handlers above. Returns the keys that are now callable.

    Called explicitly rather than at import time so a test can assert what is
    bound and what deliberately is not.
    """
    registry.bind("get_map_neighbourhood", get_map_neighbourhood)
    registry.bind("get_timeline", get_timeline)
    registry.bind("search_approved_memory", search_approved_memory)
    return registry.bound_keys()
