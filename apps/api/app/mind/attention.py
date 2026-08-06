"""NUR Mind Attention — deterministic attention queue with salience scoring.

Implements directive §8.3: deterministic attention with explicit feature
vector scoring and lifecycle management.

The attention system is NOT AI-generated salience. It is a deterministic
scoring function that ranks items by explicit, auditable features.
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


# ── Attention lifecycle ────────────────────────────────────────────────────

class AttentionStatus(StrEnum):
    """Lifecycle states for attention items."""
    CANDIDATE = "candidate"      # newly surfaced, not yet prioritized
    ACTIVE = "active"            # in active attention queue
    SNOOZED = "snoozed"         # temporarily deferred
    DISMISSED = "dismissed"      # owner dismissed (does not resurface)
    RESOLVED = "resolved"        # naturally completed
    EXPIRED = "expired"          # time-based expiration
    SUPERSEDED = "superseded"    # replaced by newer item


# ── Salience feature vector ───────────────────────────────────────────────

class SalienceFeatures(BaseModel):
    """Deterministic, auditable salience scoring features.

    Each feature is a float [0.0, 1.0]. The total score is a weighted sum.
    No neural scoring — only explicit features.
    """
    owner_pinned: float = 0.0          # 1.0 if owner explicitly pinned
    explicit_urgency: float = 0.0      # stated by owner
    deadline_proximity: float = 0.0    # 1.0 if deadline is today, decays
    risk_level: float = 0.0            # high-stakes flag
    goal_relevance: float = 0.0        # aligned with active goals
    recency: float = 0.0              # recent items score higher
    evidence_strength: float = 0.0     # how much evidence supports attention
    correction_relevance: float = 0.0  # related to recent owner corrections
    repetition_count: float = 0.0      # how many times this surfaced

    def compute_score(self) -> float:
        """Compute weighted salience score.

        Weights are explicit, auditable, and deterministic.
        Owner-pinned items always dominate.
        """
        weights = {
            "owner_pinned": 20.0,     # owner authority dominates all other features
            "explicit_urgency": 5.0,
            "deadline_proximity": 4.0,
            "risk_level": 3.0,
            "goal_relevance": 2.0,
            "recency": 1.5,
            "evidence_strength": 1.0,
            "correction_relevance": 2.0,
            "repetition_count": -0.5,  # repeated items score lower
        }
        return sum(
            getattr(self, feature) * weight
            for feature, weight in weights.items()
        )


# ── AttentionItem ──────────────────────────────────────────────────────────

class AttentionItem(BaseModel):
    """A single item in the deterministic attention queue."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID
    status: AttentionStatus = AttentionStatus.CANDIDATE

    # Content
    title: str
    description: str = ""
    domain: str = "general"
    source_ref: str | None = None

    # Scoring
    features: SalienceFeatures = Field(default_factory=SalienceFeatures)
    computed_score: float = 0.0

    # Deadline
    deadline: dt.datetime | None = None

    # Snooze
    snoozed_until: dt.datetime | None = None

    # Relations
    related_belief_ids: list[str] = Field(default_factory=list)
    related_goal_ids: list[str] = Field(default_factory=list)

    # Timing
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    resolved_at: dt.datetime | None = None

    # Version
    version: int = 1


# ── Attention Service ──────────────────────────────────────────────────────

class AttentionService:
    """Deterministic attention queue manager."""

    @staticmethod
    def create_item(
        *,
        owner_user_id: uuid.UUID,
        title: str,
        description: str = "",
        domain: str = "general",
        source_ref: str | None = None,
        features: SalienceFeatures | None = None,
        deadline: dt.datetime | None = None,
    ) -> AttentionItem:
        """Create a new attention item in CANDIDATE status with computed score."""
        feat = features or SalienceFeatures()
        return AttentionItem(
            owner_user_id=owner_user_id,
            status=AttentionStatus.CANDIDATE,
            title=title,
            description=description,
            domain=domain,
            source_ref=source_ref,
            features=feat,
            computed_score=feat.compute_score(),
            deadline=deadline,
        )

    @staticmethod
    def activate(item: AttentionItem) -> AttentionItem:
        """Promote to ACTIVE attention queue."""
        return item.model_copy(update={
            "status": AttentionStatus.ACTIVE,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": item.version + 1,
        })

    @staticmethod
    def snooze(
        item: AttentionItem,
        *,
        until: dt.datetime,
    ) -> AttentionItem:
        """Snooze until a specific time."""
        return item.model_copy(update={
            "status": AttentionStatus.SNOOZED,
            "snoozed_until": until,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": item.version + 1,
        })

    @staticmethod
    def dismiss(item: AttentionItem) -> AttentionItem:
        """Owner dismisses — MUST NOT resurface automatically."""
        return item.model_copy(update={
            "status": AttentionStatus.DISMISSED,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": item.version + 1,
        })

    @staticmethod
    def resolve(item: AttentionItem) -> AttentionItem:
        """Mark as naturally resolved."""
        return item.model_copy(update={
            "status": AttentionStatus.RESOLVED,
            "resolved_at": dt.datetime.now(dt.timezone.utc),
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": item.version + 1,
        })

    @staticmethod
    def expire(item: AttentionItem) -> AttentionItem:
        """Time-based expiration."""
        return item.model_copy(update={
            "status": AttentionStatus.EXPIRED,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": item.version + 1,
        })

    @staticmethod
    def supersede(item: AttentionItem) -> AttentionItem:
        """Replace with newer item."""
        return item.model_copy(update={
            "status": AttentionStatus.SUPERSEDED,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": item.version + 1,
        })

    @staticmethod
    def rank_items(items: list[AttentionItem]) -> list[AttentionItem]:
        """Rank items by computed salience score, highest first.

        Only ACTIVE and CANDIDATE items are ranked.
        Dismissed items are excluded.
        """
        rankable = [
            i for i in items
            if i.status in (AttentionStatus.ACTIVE, AttentionStatus.CANDIDATE)
        ]
        # Recompute scores for freshness
        for item in rankable:
            item.computed_score = item.features.compute_score()
        return sorted(rankable, key=lambda x: x.computed_score, reverse=True)

    @staticmethod
    def unsnooze_due(items: list[AttentionItem]) -> list[AttentionItem]:
        """Return snoozed items whose snooze window has expired."""
        now = dt.datetime.now(dt.timezone.utc)
        return [
            i for i in items
            if i.status == AttentionStatus.SNOOZED
            and i.snoozed_until is not None
            and i.snoozed_until <= now
        ]
