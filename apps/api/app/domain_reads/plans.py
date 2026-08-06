"""Canonical domain read service for owner Plans."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cognition import Plan, PlanStep


async def read_plans(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    plan_id: str | None = None,
    status: str | None = None,
    orbit_id: uuid.UUID | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Owner-scoped plan reader."""
    bounded = max(1, min(int(limit), 100))
    statement = select(Plan).where(Plan.owner_user_id == owner_user_id)
    if plan_id:
        statement = statement.where(Plan.id == uuid.UUID(plan_id))
    if status:
        statement = statement.where(Plan.status == status)
    if orbit_id:
        statement = statement.where(Plan.orbit_id == orbit_id)

    statement = statement.order_by(Plan.created_at.desc()).limit(bounded)
    plans = (await db.execute(statement)).scalars().all()
    if plan_id and not plans:
        return {"found": False, "plan_id": plan_id, "count": 0, "plans": []}

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
                "orbit_id": str(plan.orbit_id) if plan.orbit_id else None,
                "steps": [
                    {"id": str(s.id), "title": s.title, "position": s.position, "done": s.done}
                    for s in steps
                ],
            }
        )
    return {"found": True, "count": len(out), "plans": out}
