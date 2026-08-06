"""NUR Mind User Model — typed correctable claim graph.

Implements directive §8.5: the user model is a typed, correctable claim graph.
Claims have classes, promotion rules, sensitivity rules, and owner authority.

CRITICAL RULES:
- NUR_INFERRED cannot become OWNER_CONFIRMED without explicit owner confirmation
- Medical/psychological/political inferences have elevated sensitivity
- Owner corrections outrank all model confidence
- Retracted claims are preserved (not deleted) with retraction reason
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


# ── Claim classes ──────────────────────────────────────────────────────────

class ClaimClass(StrEnum):
    """Classification of how a user-model claim was established."""
    OWNER_STATED = "owner_stated"           # owner explicitly said it
    OWNER_CONFIRMED = "owner_confirmed"     # owner confirmed NUR's inference
    OWNER_CORRECTED = "owner_corrected"     # owner corrected a previous claim
    OBSERVED_PATTERN = "observed_pattern"   # observed from repeated behavior
    NUR_INFERRED = "nur_inferred"           # NUR inferred from evidence
    RESEARCH_DERIVED = "research_derived"   # from external research/data
    CONTRADICTED = "contradicted"           # contradicted by newer evidence
    RETRACTED = "retracted"                 # withdrawn (by owner or system)


class ClaimSensitivity(StrEnum):
    """Sensitivity level for user-model claims."""
    NORMAL = "normal"
    ELEVATED = "elevated"      # financial, career
    HIGH = "high"              # medical, psychological, political, religious


# ── Sensitive domains that automatically get ELEVATED or HIGH ──────────────

_SENSITIVE_DOMAINS: dict[str, ClaimSensitivity] = {
    "medical": ClaimSensitivity.HIGH,
    "health": ClaimSensitivity.HIGH,
    "mental_health": ClaimSensitivity.HIGH,
    "psychological": ClaimSensitivity.HIGH,
    "political": ClaimSensitivity.HIGH,
    "religious": ClaimSensitivity.HIGH,
    "sexual": ClaimSensitivity.HIGH,
    "financial": ClaimSensitivity.ELEVATED,
    "career": ClaimSensitivity.ELEVATED,
    "legal": ClaimSensitivity.ELEVATED,
}


# ── UserModelClaim ─────────────────────────────────────────────────────────

class UserModelClaim(BaseModel):
    """A single claim in the user model graph.

    The user model is NOT a flat key-value store. It's a claim graph where
    each claim has provenance, sensitivity, and authority tracking.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID
    claim_class: ClaimClass
    claim_text: str
    domain: str = "general"
    sensitivity: ClaimSensitivity = ClaimSensitivity.NORMAL

    # Provenance
    source_event_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    # Confidence
    confidence: float = 0.5

    # Corrections
    correction_text: str | None = None
    correction_count: int = 0

    # Retraction
    retraction_reason: str | None = None

    # Versioning
    version: int = 1
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


# ── User Model Service ────────────────────────────────────────────────────

class UserModelService:
    """Service for managing the typed correctable claim graph."""

    @staticmethod
    def create_claim(
        *,
        owner_user_id: uuid.UUID,
        claim_text: str,
        claim_class: ClaimClass | str,
        domain: str = "general",
        source_event_id: str | None = None,
        source_refs: list[str] | None = None,
        confidence: float = 0.5,
    ) -> UserModelClaim:
        """Create a new user-model claim with auto-sensitivity detection."""
        cc = ClaimClass(claim_class) if isinstance(claim_class, str) else claim_class

        # Auto-detect sensitivity from domain
        sensitivity = _SENSITIVE_DOMAINS.get(domain, ClaimSensitivity.NORMAL)

        # Block NUR_INFERRED claims on HIGH sensitivity domains
        if cc == ClaimClass.NUR_INFERRED and sensitivity == ClaimSensitivity.HIGH:
            raise ValueError(
                f"NUR_INFERRED claims are not allowed on high-sensitivity domain '{domain}'. "
                "Only OWNER_STATED or OWNER_CONFIRMED claims are permitted."
            )

        return UserModelClaim(
            owner_user_id=owner_user_id,
            claim_class=cc,
            claim_text=claim_text,
            domain=domain,
            sensitivity=sensitivity,
            source_event_id=source_event_id,
            source_refs=source_refs or [],
            confidence=confidence,
        )

    @staticmethod
    def confirm_claim(claim: UserModelClaim) -> UserModelClaim:
        """Owner confirms a NUR inference → OWNER_CONFIRMED.

        This is the ONLY way NUR_INFERRED becomes OWNER_CONFIRMED.
        """
        if claim.claim_class != ClaimClass.NUR_INFERRED:
            raise ValueError(
                f"Only NUR_INFERRED claims can be confirmed. "
                f"This claim is {claim.claim_class}."
            )
        return claim.model_copy(update={
            "claim_class": ClaimClass.OWNER_CONFIRMED,
            "confidence": 1.0,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": claim.version + 1,
        })

    @staticmethod
    def correct_claim(
        claim: UserModelClaim,
        *,
        correction_text: str,
    ) -> UserModelClaim:
        """Owner corrects a claim — always takes precedence."""
        return claim.model_copy(update={
            "claim_class": ClaimClass.OWNER_CORRECTED,
            "correction_text": correction_text,
            "correction_count": claim.correction_count + 1,
            "confidence": 1.0,  # owner is always authority
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": claim.version + 1,
        })

    @staticmethod
    def retract_claim(
        claim: UserModelClaim,
        *,
        reason: str,
    ) -> UserModelClaim:
        """Retract a claim (preserved, not deleted)."""
        return claim.model_copy(update={
            "claim_class": ClaimClass.RETRACTED,
            "retraction_reason": reason,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": claim.version + 1,
        })

    @staticmethod
    def contradict_claim(
        claim: UserModelClaim,
        *,
        counter_evidence: list[str],
    ) -> UserModelClaim:
        """Mark a claim as contradicted by new evidence."""
        return claim.model_copy(update={
            "claim_class": ClaimClass.CONTRADICTED,
            "source_refs": claim.source_refs + counter_evidence,
            "confidence": max(0.0, claim.confidence - 0.3),
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": claim.version + 1,
        })

    @staticmethod
    def can_promote(claim: UserModelClaim, target_class: ClaimClass) -> bool:
        """Check whether a claim can be promoted to the target class.

        KEY RULE: NUR_INFERRED → OWNER_CONFIRMED requires explicit owner action.
        """
        allowed_promotions: dict[ClaimClass, set[ClaimClass]] = {
            ClaimClass.NUR_INFERRED: {ClaimClass.OWNER_CONFIRMED, ClaimClass.OWNER_CORRECTED},
            ClaimClass.OBSERVED_PATTERN: {ClaimClass.OWNER_CONFIRMED, ClaimClass.OWNER_CORRECTED},
            ClaimClass.RESEARCH_DERIVED: {ClaimClass.OWNER_CONFIRMED, ClaimClass.OWNER_CORRECTED},
            ClaimClass.OWNER_STATED: {ClaimClass.OWNER_CORRECTED},
            ClaimClass.OWNER_CONFIRMED: {ClaimClass.OWNER_CORRECTED},
        }
        return target_class in allowed_promotions.get(claim.claim_class, set())
