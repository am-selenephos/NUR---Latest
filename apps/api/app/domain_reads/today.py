"""Canonical domain read service for owner Today state."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.living.service import today_snapshot


async def read_today_state(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
) -> dict[str, Any]:
    """The owner's current day state snapshot."""
    return await today_snapshot(db, owner_user_id=owner_user_id)
