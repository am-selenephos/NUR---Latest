"""Canonical projections into the owner-scoped Timeline ledger."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TimelineEvent
from app.models._mixins import now_utc


async def record_observed_outcome(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    outcome_id: uuid.UUID,
    observed_result: str,
    occurred_at: dt.datetime | None = None,
    orbit_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    system_slug: str | None = None,
    provenance: dict | None = None,
) -> TimelineEvent:
    """Project one persisted Return into Timeline without duplicating its truth."""
    row = (
        await db.execute(
            select(TimelineEvent).where(
                TimelineEvent.owner_user_id == owner_user_id,
                TimelineEvent.source_type == "OUTCOME",
                TimelineEvent.source_id == outcome_id,
            )
        )
    ).scalar_one_or_none()
    instant = occurred_at or now_utc()
    title = observed_result.strip()[:500] or "Observed outcome"
    event_payload = {
        "outcome_id": str(outcome_id),
        **(provenance or {}),
    }

    if row is None:
        row = TimelineEvent(
            owner_user_id=owner_user_id,
            event_type="OUTCOME_REPORTED",
            title=title,
            time_kind="PAST",
            scheduled_for=instant,
            occurred_at=instant,
            source_type="OUTCOME",
            source_id=outcome_id,
            system_slug=system_slug,
            plan_id=plan_id,
            orbit_id=orbit_id,
            status="OBSERVED",
            importance=70,
            event_payload=event_payload,
            date_precision="EXACT",
            visibility_scope="PRIVATE",
        )
        db.add(row)
    else:
        row.title = title
        row.system_slug = system_slug or row.system_slug
        row.plan_id = plan_id or row.plan_id
        row.orbit_id = orbit_id or row.orbit_id
        row.event_payload = {**(row.event_payload or {}), **event_payload}
        row.updated_at = now_utc()

    await db.flush()
    return row
