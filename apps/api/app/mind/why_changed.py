"""NUR Mind WhyChanged Ledger — append-only change explanation contract.

Implements directive §8.12: a generic append-only change explanation for
belief, user-model claim, plan, recommendation, route policy, prompt,
identity, memory, and review strategy.

The record is an explanation of the state transition, not chain-of-thought.
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ── Change classes ─────────────────────────────────────────────────────────

class ChangeClass(StrEnum):
    """Classification of how an entity changed."""
    CREATED = "created"
    UPDATED = "updated"
    CORRECTED = "corrected"              # owner correction
    CONTRADICTED = "contradicted"        # new evidence contradicts
    RETRACTED = "retracted"              # withdrawn entirely
    RESTORED = "restored"                # rolled back to a previous version
    PROMOTED = "promoted"                # candidate → accepted
    DEMOTED = "demoted"                  # accepted → contested/stale
    SUPERSEDED = "superseded"            # replaced by newer version
    EXPIRED = "expired"                  # time-based invalidation
    POLICY_CHANGE = "policy_change"      # system policy changed behavior
    DEPLOYMENT = "deployment"            # model/prompt/config deployed
    EXPERIMENT_VALIDATED = "experiment_validated"  # dry-run / orchestration validation
    PROPOSED = "proposed"                # candidate proposal evaluated


class EntityType(StrEnum):
    """Entity types that support why-changed tracking."""
    BELIEF = "belief"
    USER_MODEL_CLAIM = "user_model_claim"
    WORLD_EDGE = "world_edge"
    PLAN = "plan"
    RECOMMENDATION = "recommendation"
    ROUTE_POLICY = "route_policy"
    PROMPT = "prompt"
    IDENTITY = "identity"
    MEMORY = "memory"
    REVIEW_STRATEGY = "review_strategy"
    PREDICTION = "prediction"
    ATTENTION_ITEM = "attention_item"
    MODEL_CHECKPOINT = "model_checkpoint"
    CURRICULUM = "curriculum"


# ── WhyChangedRecord Pydantic model ───────────────────────────────────────

class WhyChangedRecord(BaseModel):
    """Append-only explanation of a state transition.

    This record is NOT chain-of-thought. It documents:
    - what changed (entity_type, entity_id, versions)
    - why it changed (trigger, evidence, correction)
    - who/what caused it (actor)
    - what it affects (affected_future_behavior, rollback_target)
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID

    # What changed
    entity_type: EntityType
    entity_id: str
    previous_version: str | None = None
    new_version: str | None = None

    # How it changed
    change_class: ChangeClass

    # Why it changed
    trigger: str = ""                              # what caused the change
    supporting_evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    owner_correction: bool = False

    # Context at time of change
    model_version: str | None = None
    prompt_version: str | None = None
    policy_version: str | None = None

    # Actor
    actor: str = "system"  # "system", "owner", "reviewer", "scheduler"

    # Impact
    affected_future_behavior: str = ""
    rollback_target: str | None = None

    # Timing
    occurred_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


# ── In-memory service (until migration adds DB table) ─────────────────────
# This service works with the Pydantic model. Phase 2 migration will add
# the database table and this will be upgraded to persist.

class WhyChangedService:
    """Service for recording and querying why-changed entries.

    Currently stores records in the cognitive_events table as structured payloads
    until the dedicated table is created by migration 0054.
    """

    @staticmethod
    async def record_change(
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        entity_type: EntityType | str,
        entity_id: str,
        change_class: ChangeClass | str,
        trigger: str = "",
        previous_version: str | None = None,
        new_version: str | None = None,
        supporting_evidence: list[str] | None = None,
        counter_evidence: list[str] | None = None,
        owner_correction: bool = False,
        actor: str = "system",
        affected_future_behavior: str = "",
        rollback_target: str | None = None,
        model_version: str | None = None,
        prompt_version: str | None = None,
        policy_version: str | None = None,
    ) -> WhyChangedRecord:
        """Create and persist a why-changed record.

        Returns the created record with its generated ID.
        """
        record = WhyChangedRecord(
            owner_user_id=owner_user_id,
            entity_type=EntityType(entity_type) if isinstance(entity_type, str) else entity_type,
            entity_id=entity_id,
            change_class=ChangeClass(change_class) if isinstance(change_class, str) else change_class,
            trigger=trigger,
            previous_version=previous_version,
            new_version=new_version,
            supporting_evidence=supporting_evidence or [],
            counter_evidence=counter_evidence or [],
            owner_correction=owner_correction,
            actor=actor,
            affected_future_behavior=affected_future_behavior,
            rollback_target=rollback_target,
            model_version=model_version,
            prompt_version=prompt_version,
            policy_version=policy_version,
        )

        # Persist as a CognitiveEvent until dedicated table exists
        from app.models import CognitiveEvent
        event = CognitiveEvent(
            owner_user_id=owner_user_id,
            event_kind="SYSTEM_EVENT",
            content_text=f"WhyChanged: {entity_type}/{entity_id} — {change_class}",
            structured_payload={
                "why_changed": record.model_dump(mode="json"),
            },
            source_ref=f"why_changed:{record.id}",
            scope="PRIVATE_ORBIT",
        )
        db.add(event)
        await db.flush()
        return record

    @staticmethod
    async def get_change_history(
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        entity_type: str,
        entity_id: str,
        limit: int = 50,
    ) -> list[WhyChangedRecord]:
        """Retrieve the change history for an entity, newest first.

        Queries CognitiveEvent records with why_changed structured payloads.
        """
        from app.models import CognitiveEvent
        from sqlalchemy import desc

        stmt = (
            select(CognitiveEvent)
            .where(
                CognitiveEvent.owner_user_id == owner_user_id,
                CognitiveEvent.event_kind == "SYSTEM_EVENT",
                CognitiveEvent.source_ref.like("why_changed:%"),
            )
            .order_by(desc(CognitiveEvent.created_at))
            .limit(limit * 3)  # over-fetch since we filter in Python
        )
        result = await db.execute(stmt)
        events = result.scalars().all()

        records: list[WhyChangedRecord] = []
        for event in events:
            payload = event.structured_payload or {}
            wc_data = payload.get("why_changed", {})
            if (
                wc_data.get("entity_type") == entity_type
                and wc_data.get("entity_id") == entity_id
            ):
                try:
                    records.append(WhyChangedRecord.model_validate(wc_data))
                except Exception:
                    continue
            if len(records) >= limit:
                break

        return records
