import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.signals import create_signal_from_owner_correction
from app.models import CognitiveEvent, UserCorrection


async def persist_user_correction(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    target_event_id: uuid.UUID | None,
    correction_text: str,
    reason: str | None = None,
) -> UserCorrection:
    row = UserCorrection(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        target_event_id=target_event_id,
        correction_text=correction_text,
        reason=reason,
    )
    db.add(row)
    db.add(
        CognitiveEvent(
            owner_user_id=owner_user_id,
            orbit_id=orbit_id,
            event_kind="USER_CORRECTION",
            content_text=correction_text,
            structured_payload={"target_event_id": str(target_event_id) if target_event_id else None, "reason": reason},
            source_ref=f"cognitive_event:{target_event_id}" if target_event_id else None,
        )
    )
    # Emit learning signal for Hardness plane
    await create_signal_from_owner_correction(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        correction_text=correction_text,
        reason=reason,
        target_event_id=target_event_id,
    )
    return row
