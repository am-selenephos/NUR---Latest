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
    INSIGHT = "insight"


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

    model_config = {"from_attributes": True}


class WhyChangedService:
    """Append-only, owner-scoped state-transition explanations."""

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

        from app.models import WhyChangedRecordRow

        row = WhyChangedRecordRow(
            **record.model_dump(exclude={"entity_type", "change_class"}),
            entity_type=record.entity_type.value,
            change_class=record.change_class.value,
        )
        db.add(row)
        await db.flush()
        return WhyChangedRecord.model_validate(row)

    @staticmethod
    async def get_change_history(
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        entity_type: str,
        entity_id: str,
        limit: int = 50,
    ) -> list[WhyChangedRecord]:
        """Retrieve one entity's governed history, newest first."""
        from app.models import WhyChangedRecordRow
        from sqlalchemy import desc

        stmt = (
            select(WhyChangedRecordRow)
            .where(
                WhyChangedRecordRow.owner_user_id == owner_user_id,
                WhyChangedRecordRow.entity_type == entity_type,
                WhyChangedRecordRow.entity_id == entity_id,
            )
            .order_by(desc(WhyChangedRecordRow.occurred_at))
            .limit(min(max(limit, 1), 200))
        )
        result = await db.execute(stmt)
        return [WhyChangedRecord.model_validate(row) for row in result.scalars()]
