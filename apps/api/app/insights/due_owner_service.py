"""Bounded owner-ID discovery for scheduled Insight consolidation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_auth_context
from app.models import User


async def insight_consolidation_owner_ids(
    db: AsyncSession, *, limit: int
) -> list[uuid.UUID]:
    """Enumerate active owner IDs only; owner data is loaded after RLS context."""
    await set_auth_context(db)
    rows = (
        await db.execute(
            select(User.id)
            .where(User.status == "active")
            .order_by(User.created_at.asc(), User.id.asc())
            .limit(min(max(limit, 1), 100))
        )
    ).scalars()
    return list(rows)
