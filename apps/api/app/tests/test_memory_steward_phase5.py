"""Unit tests for Phase 5: Memory Steward & Intent Classification.

Tests:
1. Memory steward: candidate lifecycle, rejection persistence, contradiction detection
2. Memory steward: deletion propagation, staleness, no-silent-memory enforcement
"""

import datetime as dt
import uuid

import pytest

from app.mind.memory_steward import (
    MemoryCandidateType,
    MemoryStatus,
    MemoryStewardService,
)


class TestMemoryCandidate:
    def test_create_candidate(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Owner prefers morning coffee",
            memory_type=MemoryCandidateType.PREFERENCE,
            reason_to_remember="Owner mentioned this in conversation",
        )
        assert c.status == MemoryStatus.CANDIDATE
        assert c.memory_type == MemoryCandidateType.PREFERENCE
        assert c.reason_to_remember != ""
        assert c.rejection_count == 0

    def test_no_silent_memory(self):
        """Directive: no memory without explicit reason."""
        with pytest.raises(ValueError, match="reason_to_remember"):
            MemoryStewardService.create_candidate(
                owner_user_id=uuid.uuid4(),
                content="Secret memory",
                memory_type=MemoryCandidateType.FACT,
                reason_to_remember="",
            )

    def test_no_silent_memory_whitespace(self):
        with pytest.raises(ValueError, match="reason_to_remember"):
            MemoryStewardService.create_candidate(
                owner_user_id=uuid.uuid4(),
                content="Secret memory",
                memory_type="fact",
                reason_to_remember="   ",
            )


class TestMemoryLifecycle:
    def test_validate_candidate(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test reason",
        )
        validated = MemoryStewardService.validate_candidate(c)
        assert validated.status == MemoryStatus.VALIDATED
        assert validated.version == 2

    def test_approve(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test reason",
        )
        validated = MemoryStewardService.validate_candidate(c)
        approved = MemoryStewardService.approve(validated)
        assert approved.status == MemoryStatus.OWNER_APPROVED
        assert approved.version == 3

    def test_activate(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test reason",
        )
        validated = MemoryStewardService.validate_candidate(c)
        approved = MemoryStewardService.approve(validated)
        active = MemoryStewardService.activate(approved)
        assert active.status == MemoryStatus.ACTIVE
        assert active.version == 4

    def test_activate_requires_approval(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test reason",
        )
        with pytest.raises(ValueError, match="Only OWNER_APPROVED"):
            MemoryStewardService.activate(c)

    def test_reject_records_reason(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test reason",
        )
        rejected = MemoryStewardService.reject(c, reason="I don't want this stored")
        assert rejected.status == MemoryStatus.REJECTED
        assert rejected.rejection_reason == "I don't want this stored"
        assert rejected.rejection_count == 1

    def test_rejection_prevents_reproposal(self):
        uid = uuid.uuid4()
        c = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Morning coffee preference",
            memory_type=MemoryCandidateType.PREFERENCE,
            reason_to_remember="Test",
        )
        rejected = MemoryStewardService.reject(c, reason="No thanks")

        assert MemoryStewardService.is_previously_rejected(
            "Morning coffee preference",
            [rejected],
        ) is True

    def test_different_content_not_rejected(self):
        uid = uuid.uuid4()
        c = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Morning coffee",
            memory_type=MemoryCandidateType.PREFERENCE,
            reason_to_remember="Test",
        )
        rejected = MemoryStewardService.reject(c, reason="No")

        assert MemoryStewardService.is_previously_rejected(
            "Evening tea preference",
            [rejected],
        ) is False


class TestConflictDetection:
    def test_detect_contradictions(self):
        uid = uuid.uuid4()
        existing = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Owner prefers coffee",
            memory_type=MemoryCandidateType.PREFERENCE,
            domain="food",
            reason_to_remember="Stated",
        )
        existing_active = existing.model_copy(update={"status": MemoryStatus.ACTIVE})

        candidate = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Owner prefers coffee in the morning",
            memory_type=MemoryCandidateType.PREFERENCE,
            domain="food",
            reason_to_remember="More specific version",
        )

        conflicts = MemoryStewardService.detect_contradictions(
            candidate, [existing_active]
        )
        assert len(conflicts) == 1

    def test_no_conflict_different_domains(self):
        uid = uuid.uuid4()
        existing = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Owner prefers coffee",
            memory_type=MemoryCandidateType.PREFERENCE,
            domain="food",
            reason_to_remember="Stated",
        )
        existing_active = existing.model_copy(update={"status": MemoryStatus.ACTIVE})

        candidate = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Owner prefers dark mode",
            memory_type=MemoryCandidateType.PREFERENCE,
            domain="ui",
            reason_to_remember="Observed",
        )

        conflicts = MemoryStewardService.detect_contradictions(
            candidate, [existing_active]
        )
        assert len(conflicts) == 0

    def test_no_conflict_with_rejected(self):
        uid = uuid.uuid4()
        existing = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Owner prefers coffee",
            memory_type=MemoryCandidateType.PREFERENCE,
            domain="food",
            reason_to_remember="Stated",
        )
        existing_rejected = existing.model_copy(update={"status": MemoryStatus.REJECTED})

        candidate = MemoryStewardService.create_candidate(
            owner_user_id=uid,
            content="Owner prefers coffee",
            memory_type=MemoryCandidateType.PREFERENCE,
            domain="food",
            reason_to_remember="Test",
        )

        conflicts = MemoryStewardService.detect_contradictions(
            candidate, [existing_rejected]
        )
        assert len(conflicts) == 0


class TestDeletionAndStaleness:
    def test_delete_returns_dependents(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test",
        )
        c_with_deps = c.model_copy(update={
            "dependent_record_ids": ["dep-1", "dep-2"],
        })
        deleted, dependents = MemoryStewardService.delete(c_with_deps)
        assert deleted.status == MemoryStatus.DELETED
        assert dependents == ["dep-1", "dep-2"]

    def test_staleness_detection(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Old memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test",
        )
        active = c.model_copy(update={
            "status": MemoryStatus.ACTIVE,
            "created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200),
            "staleness_window_days": 180,
        })
        stale = MemoryStewardService.check_staleness(active)
        assert stale.status == MemoryStatus.STALE

    def test_fresh_not_stale(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Fresh memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test",
        )
        active = c.model_copy(update={"status": MemoryStatus.ACTIVE})
        result = MemoryStewardService.check_staleness(active)
        assert result.status == MemoryStatus.ACTIVE

    def test_deleted_immune_to_staleness(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Deleted memory",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test",
        )
        deleted = c.model_copy(update={
            "status": MemoryStatus.DELETED,
            "created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=500),
        })
        result = MemoryStewardService.check_staleness(deleted)
        assert result.status == MemoryStatus.DELETED

    def test_record_access_updates_timestamp(self):
        c = MemoryStewardService.create_candidate(
            owner_user_id=uuid.uuid4(),
            content="Test",
            memory_type=MemoryCandidateType.FACT,
            reason_to_remember="Test",
        )
        accessed = MemoryStewardService.record_access(c)
        assert accessed.last_accessed_at is not None


class TestAllMemoryTypes:
    def test_all_types_create(self):
        uid = uuid.uuid4()
        for mt in MemoryCandidateType:
            c = MemoryStewardService.create_candidate(
                owner_user_id=uid,
                content=f"Test {mt.value}",
                memory_type=mt,
                reason_to_remember=f"Testing {mt.value}",
            )
            assert c.memory_type == mt

    def test_all_statuses_exist(self):
        expected = {
            "candidate", "validated", "owner_approved", "active",
            "rejected", "contradicted", "stale", "deleted",
        }
        actual = {s.value for s in MemoryStatus}
        assert actual == expected
