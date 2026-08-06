"""Canonical domain read service for owner Timeline events."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence import TimelineEvent


async def read_timeline(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    limit: int = 50,
    window_days: int | None = None,
    orbit_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Timeline events in a bounded window.

    The limit is clamped to [1, 200].
    If window_days is specified (>0), events are filtered by created_at >= (now - window_days).
    If orbit_id is specified, events are filtered by orbit_id.
    """
    bounded = max(1, min(int(limit), 200))
    statement = (
        select(TimelineEvent)
        .where(TimelineEvent.owner_user_id == owner_user_id)
    )
    if window_days is not None and window_days > 0:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=window_days)
        statement = statement.where(TimelineEvent.created_at >= cutoff)
    if orbit_id is not None:
        statement = statement.where(TimelineEvent.orbit_id == orbit_id)

    statement = statement.order_by(TimelineEvent.created_at.desc()).limit(bounded)
    rows = (await db.execute(statement)).scalars().all()

    return {
        "count": len(rows),
        "limit": bounded,
        "events": [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "title": row.title,
                "description": row.description,
                "time_kind": row.time_kind,
                "status": row.status,
                "importance": row.importance,
                "system_slug": row.system_slug,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else None,
                "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
            }
            for row in rows
        ],
        "provenance_label": "Owner timeline ledger",
    }
