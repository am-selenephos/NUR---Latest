"""Bounded, RLS-safe discovery for project-run recovery."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import bounded_active_user_ids
from app.models import AMProjectRun


async def project_recovery_owner_ids(
    db: AsyncSession, *, limit: int
) -> list[uuid.UUID]:
    """Enumerate active owner IDs only; no owner content leaves this query."""
    return await bounded_active_user_ids(db, limit=limit)


async def queued_project_run_ids(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int
) -> list[uuid.UUID]:
    """Return queued IDs inside an already owner-scoped RLS transaction."""
    rows = (
        await db.execute(
            select(AMProjectRun.id)
            .where(
                AMProjectRun.owner_user_id == owner_user_id,
                AMProjectRun.status == "QUEUED",
            )
            .order_by(AMProjectRun.queued_at.asc().nullsfirst(), AMProjectRun.id.asc())
            .limit(min(max(limit, 1), 100))
        )
    ).scalars()
    return list(rows)
