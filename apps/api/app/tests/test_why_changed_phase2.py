"""Unit tests for Phase 2: WhyChanged Ledger & Typed Uncertainty.

Tests:
1. WhyChangedRecord construction and field defaults
2. ChangeClass enum coverage
3. EntityType enum coverage
4. Record serialization roundtrip
5. Owner correction tracking
6. Rollback target tracking
7. Evidence for/against tracking
"""

import uuid


from app.mind.why_changed import (
    ChangeClass,
    EntityType,
    WhyChangedRecord,
)


# ── ChangeClass tests ──────────────────────────────────────────────────────

class TestChangeClass:
    def test_all_classes_exist(self):
        expected = {
            "created", "updated", "corrected", "contradicted", "retracted",
            "restored", "promoted", "demoted", "superseded", "expired",
            "policy_change", "deployment",
        }
        actual = {c.value for c in ChangeClass}
        assert actual == expected

    def test_str_enum_behavior(self):
        assert str(ChangeClass.CREATED) == "created"
        assert ChangeClass("corrected") == ChangeClass.CORRECTED


# ── EntityType tests ───────────────────────────────────────────────────────

class TestEntityType:
    def test_all_types_exist(self):
        expected = {
            "belief", "user_model_claim", "world_edge", "plan",
            "recommendation", "route_policy", "prompt", "identity",
            "memory", "review_strategy", "prediction", "attention_item",
            "model_checkpoint", "curriculum", "insight", "outcome",
            "learning_candidate",
        }
        actual = {t.value for t in EntityType}
        assert actual == expected

    def test_str_enum_behavior(self):
        assert str(EntityType.BELIEF) == "belief"
        assert EntityType("memory") == EntityType.MEMORY


# ── WhyChangedRecord model tests ──────────────────────────────────────────

class TestWhyChangedRecord:
    def test_construction_with_defaults(self):
        uid = uuid.uuid4()
        record = WhyChangedRecord(
            owner_user_id=uid,
            entity_type=EntityType.BELIEF,
            entity_id="belief-123",
            change_class=ChangeClass.CREATED,
        )
        assert record.owner_user_id == uid
        assert record.entity_type == EntityType.BELIEF
        assert record.entity_id == "belief-123"
        assert record.change_class == ChangeClass.CREATED
        assert record.trigger == ""
        assert record.supporting_evidence == []
        assert record.counter_evidence == []
        assert record.owner_correction is False
        assert record.actor == "system"
        assert record.affected_future_behavior == ""
        assert record.rollback_target is None
        assert record.id is not None
        assert record.occurred_at is not None

    def test_unique_ids(self):
        uid = uuid.uuid4()
        r1 = WhyChangedRecord(
            owner_user_id=uid,
            entity_type=EntityType.BELIEF,
            entity_id="b1",
            change_class=ChangeClass.CREATED,
        )
        r2 = WhyChangedRecord(
            owner_user_id=uid,
            entity_type=EntityType.BELIEF,
            entity_id="b1",
            change_class=ChangeClass.UPDATED,
        )
        assert r1.id != r2.id

    def test_owner_correction(self):
        record = WhyChangedRecord(
            owner_user_id=uuid.uuid4(),
            entity_type=EntityType.USER_MODEL_CLAIM,
            entity_id="claim-456",
            change_class=ChangeClass.CORRECTED,
            trigger="Owner corrected inference about dietary preference",
            owner_correction=True,
            actor="owner",
            previous_version="v1",
            new_version="v2",
        )
        assert record.owner_correction is True
        assert record.actor == "owner"
        assert record.change_class == ChangeClass.CORRECTED
        assert record.previous_version == "v1"
        assert record.new_version == "v2"

    def test_evidence_tracking(self):
        record = WhyChangedRecord(
            owner_user_id=uuid.uuid4(),
            entity_type=EntityType.BELIEF,
            entity_id="b1",
            change_class=ChangeClass.CONTRADICTED,
            trigger="New research evidence contradicts existing belief",
            supporting_evidence=["source:research-001", "source:research-002"],
            counter_evidence=["source:original-belief-basis"],
        )
        assert len(record.supporting_evidence) == 2
        assert len(record.counter_evidence) == 1

    def test_rollback_target(self):
        record = WhyChangedRecord(
            owner_user_id=uuid.uuid4(),
            entity_type=EntityType.PLAN,
            entity_id="plan-789",
            change_class=ChangeClass.RESTORED,
            trigger="Owner requested rollback",
            rollback_target="plan-789-v1",
            actor="owner",
        )
        assert record.rollback_target == "plan-789-v1"
        assert record.change_class == ChangeClass.RESTORED

    def test_deployment_change(self):
        record = WhyChangedRecord(
            owner_user_id=uuid.uuid4(),
            entity_type=EntityType.PROMPT,
            entity_id="system-prompt-v2",
            change_class=ChangeClass.DEPLOYMENT,
            trigger="Reviewed prompt change approved",
            model_version="gpt-4o-2026-08-01",
            prompt_version="v2.1.0",
            policy_version="policy-3.0",
            affected_future_behavior="Response style updated for research tasks",
        )
        assert record.model_version == "gpt-4o-2026-08-01"
        assert record.prompt_version == "v2.1.0"
        assert record.policy_version == "policy-3.0"
        assert "research tasks" in record.affected_future_behavior

    def test_serialization_roundtrip(self):
        record = WhyChangedRecord(
            owner_user_id=uuid.uuid4(),
            entity_type=EntityType.MEMORY,
            entity_id="mem-001",
            change_class=ChangeClass.PROMOTED,
            trigger="Owner approved memory candidate",
            supporting_evidence=["event:turn-123"],
            owner_correction=False,
            actor="owner",
            previous_version="CANDIDATE",
            new_version="ACTIVE",
            affected_future_behavior="Memory will be retrieved in future Talk turns",
        )
        data = record.model_dump(mode="json")
        restored = WhyChangedRecord.model_validate(data)
        assert restored.id == record.id
        assert restored.entity_type == EntityType.MEMORY
        assert restored.change_class == ChangeClass.PROMOTED
        assert restored.supporting_evidence == ["event:turn-123"]
        assert restored.previous_version == "CANDIDATE"
        assert restored.new_version == "ACTIVE"

    def test_all_entity_types_with_change_classes(self):
        """Verify every entity type can be paired with every change class."""
        uid = uuid.uuid4()
        for entity_type in EntityType:
            for change_class in ChangeClass:
                record = WhyChangedRecord(
                    owner_user_id=uid,
                    entity_type=entity_type,
                    entity_id=f"test-{entity_type.value}",
                    change_class=change_class,
                )
                assert record.entity_type == entity_type
                assert record.change_class == change_class

    def test_timestamp_is_utc(self):
        record = WhyChangedRecord(
            owner_user_id=uuid.uuid4(),
            entity_type=EntityType.BELIEF,
            entity_id="b1",
            change_class=ChangeClass.CREATED,
        )
        assert record.occurred_at.tzinfo is not None

    def test_superseded_chain(self):
        """Test recording a version supersession chain."""
        uid = uuid.uuid4()
        records = []
        for i in range(3):
            records.append(
                WhyChangedRecord(
                    owner_user_id=uid,
                    entity_type=EntityType.IDENTITY,
                    entity_id="nur-constitution",
                    change_class=ChangeClass.SUPERSEDED if i > 0 else ChangeClass.CREATED,
                    previous_version=f"v{i}" if i > 0 else None,
                    new_version=f"v{i + 1}",
                    trigger=f"Identity update {i + 1}",
                )
            )
        assert records[0].change_class == ChangeClass.CREATED
        assert records[1].change_class == ChangeClass.SUPERSEDED
        assert records[2].previous_version == "v2"
        assert records[2].new_version == "v3"
