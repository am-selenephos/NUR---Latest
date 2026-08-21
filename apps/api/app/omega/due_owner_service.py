import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import bounded_active_user_ids


async def omega_consolidation_due_owner_ids(db: AsyncSession, *, limit: int = 50) -> list[uuid.UUID]:
    """Return owner IDs only for the scheduled worker.

    The scheduler never receives raw private text. It uses the existing auth
    context read policy to enumerate active user IDs, then each owner run sets
    app.current_user_id before touching owner-scoped Omega tables.
    """
    return await bounded_active_user_ids(db, limit=limit)
