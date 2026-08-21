"""User correction service with atomic Hardness learning signal emission."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.signals import create_signal_from_owner_correction
from app.learning.outcome_loop import reconcile_owner_correction
from app.models import CognitiveEvent, UserCorrection


class CorrectionTargetNotFound(LookupError):
    """The requested source event is absent from the current owner's scope."""


async def persist_user_correction(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    target_event_id: uuid.UUID | None,
    correction_text: str,
    reason: str | None = None,
) -> UserCorrection:
    """Persist a user correction, cognitive event, and Hardness learning signal atomically.

    Policy:
    In Slice 1, user correction persistence is strictly ATOMIC with Hardness learning signal emission.
    The UserCorrection, CognitiveEvent, and LearningSignalRecord are written in the same database transaction.
    If learning signal insertion fails, the entire transaction is rolled back and no UserCorrection is persisted.
    """
    if target_event_id is not None:
        target = await db.scalar(
            select(CognitiveEvent).where(
                CognitiveEvent.id == target_event_id,
                CognitiveEvent.owner_user_id == owner_user_id,
            )
        )
        if target is None:
            raise CorrectionTargetNotFound("Correction target not found.")

    row = UserCorrection(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        target_event_id=target_event_id,
        correction_text=correction_text,
        reason=reason,
    )
    db.add(row)
    await db.flush()
    correction_event = CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_kind="USER_CORRECTION",
        content_text=correction_text,
        structured_payload={
            "target_event_id": str(target_event_id) if target_event_id else None,
            "reason": reason,
        },
        source_ref=f"user_correction:{row.id}",
    )
    db.add(correction_event)
    await db.flush()

    # Emit learning signal for Hardness plane atomically linked to source_correction_id
    signal = await create_signal_from_owner_correction(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        correction_text=correction_text,
        reason=reason,
        target_event_id=target_event_id,
        source_event_id=correction_event.id,
        source_correction_id=row.id,
    )
    await reconcile_owner_correction(
        db,
        correction=row,
        correction_event=correction_event,
        signal=signal,
    )
    return row
