"""NUR Mind Beliefs — typed belief lifecycle with evidence governance.

Implements directive §8.8: beliefs, hypotheses, and predictions are typed,
with explicit lifecycle, evidence for/against, owner corrections, and
falsification conditions.

A belief is NOT a model output. It is a Mind-plane record of what NUR
considers to be true/likely about the owner's world, subject to
correction and evidence review.
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


# ── Belief lifecycle ───────────────────────────────────────────────────────

class BeliefStatus(StrEnum):
    """Lifecycle states for a Mind belief."""
    CANDIDATE = "candidate"              # proposed, not yet supported
    SUPPORTED = "supported"              # evidence supports it
    CONTESTED = "contested"              # conflicting evidence exists
    CONTRADICTED = "contradicted"        # strong counter-evidence
    OWNER_CORRECTED = "owner_corrected"  # owner explicitly corrected
    STALE = "stale"                      # not refreshed within staleness window
    RETRACTED = "retracted"              # withdrawn (by system or owner)


class BeliefKind(StrEnum):
    """Classification of belief types."""
    OBSERVATION = "observation"          # from evidence or owner statement
    INFERENCE = "inference"              # NUR-derived from evidence
    HYPOTHESIS = "hypothesis"            # speculative, needs testing
    PREDICTION = "prediction"            # future-directed, testable


# ── Belief model ───────────────────────────────────────────────────────────

class Belief(BaseModel):
    """A typed Mind-plane belief with evidence governance.

    Each belief tracks its own evidence base, lifecycle, and owner authority.
    Owner corrections outrank all model confidence.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID
    kind: BeliefKind
    status: BeliefStatus = BeliefStatus.CANDIDATE

    # Content
    claim_text: str
    domain: str = "general"  # "health", "career", "finance", "relationship", etc.

    # Evidence
    evidence_for: list[str] = Field(default_factory=list)  # source_ref IDs
    evidence_against: list[str] = Field(default_factory=list)
    source_authority: str = "model"  # "owner", "model", "research", "outcome"

    # Confidence
    confidence: float = 0.5
    uncertainty_kind: str | None = None

    # Falsification
    falsification_condition: str | None = None  # what would disprove this

    # Owner corrections
    owner_correction_text: str | None = None
    correction_count: int = 0

    # Freshness
    last_evidence_at: dt.datetime | None = None
    staleness_window_days: int = 90

    # Timing
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    # Version
    version: int = 1


# ── Belief service ─────────────────────────────────────────────────────────

class BeliefService:
    """Service for managing the lifecycle of Mind beliefs."""

    @staticmethod
    def create_belief(
        *,
        owner_user_id: uuid.UUID,
        claim_text: str,
        kind: BeliefKind | str = BeliefKind.INFERENCE,
        domain: str = "general",
        evidence_for: list[str] | None = None,
        source_authority: str = "model",
        confidence: float = 0.5,
        falsification_condition: str | None = None,
    ) -> Belief:
        """Create a new belief in CANDIDATE status."""
        return Belief(
            owner_user_id=owner_user_id,
            kind=BeliefKind(kind) if isinstance(kind, str) else kind,
            status=BeliefStatus.CANDIDATE,
            claim_text=claim_text,
            domain=domain,
            evidence_for=evidence_for or [],
            source_authority=source_authority,
            confidence=confidence,
            falsification_condition=falsification_condition,
        )

    @staticmethod
    def support_belief(
        belief: Belief,
        *,
        new_evidence: list[str],
        new_confidence: float | None = None,
    ) -> Belief:
        """Add supporting evidence; promote to SUPPORTED if sufficient."""
        updated = belief.model_copy(update={
            "evidence_for": belief.evidence_for + new_evidence,
            "confidence": new_confidence or min(1.0, belief.confidence + 0.1),
            "last_evidence_at": dt.datetime.now(dt.timezone.utc),
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": belief.version + 1,
            "status": BeliefStatus.SUPPORTED,
        })
        return updated

    @staticmethod
    def contest_belief(
        belief: Belief,
        *,
        counter_evidence: list[str],
        new_confidence: float | None = None,
    ) -> Belief:
        """Add counter-evidence; move to CONTESTED."""
        return belief.model_copy(update={
            "evidence_against": belief.evidence_against + counter_evidence,
            "confidence": new_confidence or max(0.0, belief.confidence - 0.2),
            "status": BeliefStatus.CONTESTED,
            "last_evidence_at": dt.datetime.now(dt.timezone.utc),
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": belief.version + 1,
        })

    @staticmethod
    def correct_belief(
        belief: Belief,
        *,
        correction_text: str,
    ) -> Belief:
        """Owner correction — always takes precedence over model confidence."""
        return belief.model_copy(update={
            "status": BeliefStatus.OWNER_CORRECTED,
            "owner_correction_text": correction_text,
            "correction_count": belief.correction_count + 1,
            "source_authority": "owner",
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": belief.version + 1,
        })

    @staticmethod
    def retract_belief(belief: Belief, *, reason: str = "") -> Belief:
        """Retract a belief entirely."""
        return belief.model_copy(update={
            "status": BeliefStatus.RETRACTED,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": belief.version + 1,
        })

    @staticmethod
    def restore_belief(belief: Belief) -> Belief:
        """Restore a retracted or corrected belief to CANDIDATE for re-evaluation."""
        if belief.status not in (BeliefStatus.RETRACTED, BeliefStatus.OWNER_CORRECTED):
            raise ValueError(f"Cannot restore belief in {belief.status} status.")
        return belief.model_copy(update={
            "status": BeliefStatus.CANDIDATE,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": belief.version + 1,
        })

    @staticmethod
    def check_staleness(belief: Belief) -> Belief:
        """Check if a belief is stale based on its staleness window."""
        if belief.status in (BeliefStatus.RETRACTED, BeliefStatus.OWNER_CORRECTED):
            return belief  # don't stale corrected/retracted beliefs

        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=belief.staleness_window_days)
        last = belief.last_evidence_at or belief.created_at
        if last < cutoff:
            return belief.model_copy(update={
                "status": BeliefStatus.STALE,
                "updated_at": dt.datetime.now(dt.timezone.utc),
                "version": belief.version + 1,
            })
        return belief
