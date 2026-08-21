"""Bounded owner-ID discovery for scheduled Insight consolidation."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import bounded_active_user_ids


async def insight_consolidation_owner_ids(
    db: AsyncSession, *, limit: int
) -> list[uuid.UUID]:
    """Enumerate active owner IDs only; owner data is loaded after RLS context."""
    return await bounded_active_user_ids(db, limit=limit)
