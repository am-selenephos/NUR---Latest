"""NUR Mind Memory Steward — governed multi-plane memory with provenance.

Implements directive §8.11: memory candidates require source event, scope,
sensitivity, reason to remember, and conflicting record detection.

CRITICAL RULES:
- No silent memory: personal durable memory requires explicit owner action
- Rejection records prevent repeated proposals
- Contradiction detection before promotion
- Temporal versioning: memories have freshness and staleness
- Deletion propagation: deleting a memory cascades to dependent records
"""
from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


# ── Memory candidate types ─────────────────────────────────────────────────

class MemoryCandidateType(StrEnum):
    """Classification of what kind of memory is being proposed."""
    FACT = "fact"
    PREFERENCE = "preference"
    BOUNDARY = "boundary"
    PERSON = "person"
    DECISION = "decision"
    PROJECT = "project"
    GOAL = "goal"
    PATTERN = "pattern"
    OUTCOME = "outcome"
    CORRECTION = "correction"
    PROCEDURE = "procedure"


class MemoryStatus(StrEnum):
    """Lifecycle states for memory records."""
    CANDIDATE = "candidate"             # proposed, awaiting review
    VALIDATED = "validated"             # system-validated, ready for owner review
    OWNER_APPROVED = "owner_approved"   # owner explicitly approved (Keep/Save)
    ACTIVE = "active"                   # in use for retrieval
    REJECTED = "rejected"               # owner rejected (do not re-propose)
    CONTRADICTED = "contradicted"       # newer evidence contradicts
    STALE = "stale"                     # not refreshed within staleness window
    DELETED = "deleted"                 # owner deleted


class MemorySensitivity(StrEnum):
    """Sensitivity level for memory records."""
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"


# ── Memory Candidate ──────────────────────────────────────────────────────

class MemoryCandidate(BaseModel):
    """A proposed memory record with full provenance.

    Directive §8.11: "No silent memory — personal durable memory requires
    explicit Keep, Save, or owner approval."
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    owner_user_id: uuid.UUID
    memory_type: MemoryCandidateType
    status: MemoryStatus = MemoryStatus.CANDIDATE

    # Content
    content: str
    summary: str = ""
    domain: str = "general"
    sensitivity: MemorySensitivity = MemorySensitivity.NORMAL

    # Provenance
    source_event_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    scope_id: str | None = None
    reason_to_remember: str = ""

    # Conflict detection
    conflicting_records: list[str] = Field(default_factory=list)
    supersedes: str | None = None

    # Rejection tracking (prevent repeated proposals)
    rejection_reason: str | None = None
    rejection_count: int = 0

    # Temporal versioning
    version: int = 1
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    last_accessed_at: dt.datetime | None = None
    staleness_window_days: int = 180

    # Deletion cascade
    dependent_record_ids: list[str] = Field(default_factory=list)


# ── Memory Steward Service ────────────────────────────────────────────────

class MemoryStewardService:
    """Governs the lifecycle of memory records with full provenance tracking."""

    @staticmethod
    def create_candidate(
        *,
        owner_user_id: uuid.UUID,
        content: str,
        memory_type: MemoryCandidateType | str,
        domain: str = "general",
        source_event_id: str | None = None,
        source_refs: list[str] | None = None,
        scope_id: str | None = None,
        reason_to_remember: str = "",
        sensitivity: MemorySensitivity | str = MemorySensitivity.NORMAL,
    ) -> MemoryCandidate:
        """Create a new memory candidate.

        Requires reason_to_remember — empty reasons are rejected.
        """
        if not reason_to_remember.strip():
            raise ValueError(
                "Memory candidates must include a reason_to_remember. "
                "No silent memory is permitted."
            )

        mt = MemoryCandidateType(memory_type) if isinstance(memory_type, str) else memory_type
        sens = MemorySensitivity(sensitivity) if isinstance(sensitivity, str) else sensitivity

        return MemoryCandidate(
            owner_user_id=owner_user_id,
            memory_type=mt,
            status=MemoryStatus.CANDIDATE,
            content=content,
            domain=domain,
            sensitivity=sens,
            source_event_id=source_event_id,
            source_refs=source_refs or [],
            scope_id=scope_id,
            reason_to_remember=reason_to_remember,
        )

    @staticmethod
    def validate_candidate(
        candidate: MemoryCandidate,
        *,
        conflicting_records: list[str] | None = None,
    ) -> MemoryCandidate:
        """System validation step — checks for conflicts before owner review."""
        return candidate.model_copy(update={
            "status": MemoryStatus.VALIDATED,
            "conflicting_records": conflicting_records or [],
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": candidate.version + 1,
        })

    @staticmethod
    def approve(candidate: MemoryCandidate) -> MemoryCandidate:
        """Owner explicitly approves the memory (Keep/Save action)."""
        if candidate.status not in (MemoryStatus.CANDIDATE, MemoryStatus.VALIDATED):
            raise ValueError(f"Cannot approve memory in {candidate.status} status.")
        return candidate.model_copy(update={
            "status": MemoryStatus.OWNER_APPROVED,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": candidate.version + 1,
        })

    @staticmethod
    def activate(candidate: MemoryCandidate) -> MemoryCandidate:
        """Promote approved memory to active retrieval."""
        if candidate.status != MemoryStatus.OWNER_APPROVED:
            raise ValueError("Only OWNER_APPROVED memories can be activated.")
        return candidate.model_copy(update={
            "status": MemoryStatus.ACTIVE,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": candidate.version + 1,
        })

    @staticmethod
    def reject(
        candidate: MemoryCandidate,
        *,
        reason: str,
    ) -> MemoryCandidate:
        """Owner rejects — records rejection to prevent re-proposal."""
        return candidate.model_copy(update={
            "status": MemoryStatus.REJECTED,
            "rejection_reason": reason,
            "rejection_count": candidate.rejection_count + 1,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": candidate.version + 1,
        })

    @staticmethod
    def is_previously_rejected(
        content: str,
        rejected_records: list[MemoryCandidate],
    ) -> bool:
        """Check if similar content has been previously rejected.

        Prevents repeated proposals for the same memory.
        """
        content_lower = content.lower().strip()
        return any(
            r.content.lower().strip() == content_lower
            and r.status == MemoryStatus.REJECTED
            for r in rejected_records
        )

    @staticmethod
    def detect_contradictions(
        candidate: MemoryCandidate,
        existing_records: list[MemoryCandidate],
    ) -> list[str]:
        """Detect records that may conflict with the candidate.

        Returns IDs of potentially conflicting records.
        Simple content-similarity check; can be enhanced with semantic matching.
        """
        conflicts: list[str] = []
        candidate_lower = candidate.content.lower()
        for existing in existing_records:
            if existing.status not in (MemoryStatus.ACTIVE, MemoryStatus.OWNER_APPROVED):
                continue
            if existing.memory_type != candidate.memory_type:
                continue
            if existing.domain != candidate.domain:
                continue
            # Simple overlap check — real implementation would use semantic similarity
            existing_lower = existing.content.lower()
            if candidate_lower in existing_lower or existing_lower in candidate_lower:
                conflicts.append(str(existing.id))
        return conflicts

    @staticmethod
    def delete(
        record: MemoryCandidate,
    ) -> tuple[MemoryCandidate, list[str]]:
        """Delete a memory record and return dependent records for cascade.

        Returns the deleted record and a list of dependent record IDs to cascade.
        """
        deleted = record.model_copy(update={
            "status": MemoryStatus.DELETED,
            "updated_at": dt.datetime.now(dt.timezone.utc),
            "version": record.version + 1,
        })
        return deleted, record.dependent_record_ids

    @staticmethod
    def check_staleness(record: MemoryCandidate) -> MemoryCandidate:
        """Check if a memory record has gone stale."""
        if record.status in (MemoryStatus.DELETED, MemoryStatus.REJECTED):
            return record

        last_access = record.last_accessed_at or record.created_at
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=record.staleness_window_days)
        if last_access < cutoff:
            return record.model_copy(update={
                "status": MemoryStatus.STALE,
                "updated_at": dt.datetime.now(dt.timezone.utc),
                "version": record.version + 1,
            })
        return record

    @staticmethod
    def record_access(record: MemoryCandidate) -> MemoryCandidate:
        """Record that a memory was accessed (for staleness tracking)."""
        return record.model_copy(update={
            "last_accessed_at": dt.datetime.now(dt.timezone.utc),
        })
