"""Signal service for capturing and validating learning signals in the Hardness plane."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.schemas import LearningSignalKind
from app.models.hardness import LearningSignalRecord


async def persist_learning_signal(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    signal_kind: LearningSignalKind,
    task_class: str,
    summary: str,
    orbit_id: uuid.UUID | None = None,
    source_event_id: uuid.UUID | None = None,
    capability_id: str | None = None,
    structured_payload: dict[str, Any] | None = None,
) -> LearningSignalRecord:
    """Persist a typed learning signal under the owner's isolation boundary."""
    record = LearningSignalRecord(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        source_event_id=source_event_id,
        signal_kind=signal_kind.value,
        capability_id=capability_id,
        task_class=task_class,
        summary=summary,
        structured_payload=structured_payload or {},
    )
    db.add(record)
    await db.flush()
    return record


async def create_signal_from_owner_correction(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    correction_text: str,
    reason: str | None = None,
    target_event_id: uuid.UUID | None = None,
    capability_id: str | None = None,
    task_class: str = "general_cognition",
) -> LearningSignalRecord:
    """Hook called when an owner correction occurs."""
    summary = f"Owner correction: {correction_text[:120]}"
    payload = {
        "correction_text": correction_text,
        "reason": reason,
        "target_event_id": str(target_event_id) if target_event_id else None,
        "provenance": "OWNER_EXPLICIT",
    }
    return await persist_learning_signal(
        db,
        owner_user_id=owner_user_id,
        signal_kind=LearningSignalKind.OWNER_CORRECTION,
        task_class=task_class,
        summary=summary,
        orbit_id=orbit_id,
        source_event_id=target_event_id,
        capability_id=capability_id,
        structured_payload=payload,
    )
