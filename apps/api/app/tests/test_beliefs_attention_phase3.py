"""Unit tests for Phase 3: Beliefs, User Model & Attention.

Tests:
1. Belief lifecycle: create, support, contest, correct, restore, stale detection
2. User model: claim promotion rules, sensitive inference blocking, owner correction precedence
3. Attention: scoring determinism, lifecycle transitions, dismissed items don't resurface
"""

import datetime as dt
import uuid

import pytest

from app.mind.beliefs import BeliefKind, BeliefService, BeliefStatus
from app.mind.user_model import ClaimClass, ClaimSensitivity, UserModelService
from app.mind.attention import (
    AttentionService,
    AttentionStatus,
    SalienceFeatures,
)


# ── Belief lifecycle tests ────────────────────────────────────────────────

class TestBeliefLifecycle:
    def test_create_candidate(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Owner prefers morning routines",
            kind=BeliefKind.INFERENCE,
            domain="lifestyle",
        )
        assert b.status == BeliefStatus.CANDIDATE
        assert b.kind == BeliefKind.INFERENCE
        assert b.confidence == 0.5
        assert b.version == 1

    def test_support_promotes_to_supported(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Owner exercises regularly",
            kind=BeliefKind.OBSERVATION,
        )
        updated = BeliefService.support_belief(b, new_evidence=["event:123"])
        assert updated.status == BeliefStatus.SUPPORTED
        assert "event:123" in updated.evidence_for
        assert updated.confidence > b.confidence
        assert updated.version == 2

    def test_contest_moves_to_contested(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Owner prefers tea over coffee",
            kind=BeliefKind.INFERENCE,
            confidence=0.7,
        )
        updated = BeliefService.contest_belief(b, counter_evidence=["event:456"])
        assert updated.status == BeliefStatus.CONTESTED
        assert "event:456" in updated.evidence_against
        assert updated.confidence < b.confidence
        assert updated.version == 2

    def test_owner_correction_takes_precedence(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Owner is vegetarian",
            kind=BeliefKind.INFERENCE,
            confidence=0.8,
        )
        corrected = BeliefService.correct_belief(b, correction_text="I am not vegetarian")
        assert corrected.status == BeliefStatus.OWNER_CORRECTED
        assert corrected.owner_correction_text == "I am not vegetarian"
        assert corrected.source_authority == "owner"
        assert corrected.correction_count == 1

    def test_retract_belief(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Test belief",
            kind=BeliefKind.HYPOTHESIS,
        )
        retracted = BeliefService.retract_belief(b, reason="No longer relevant")
        assert retracted.status == BeliefStatus.RETRACTED

    def test_restore_from_retracted(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Test belief",
            kind=BeliefKind.HYPOTHESIS,
        )
        retracted = BeliefService.retract_belief(b, reason="test")
        restored = BeliefService.restore_belief(retracted)
        assert restored.status == BeliefStatus.CANDIDATE

    def test_restore_from_corrected(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Test belief",
            kind=BeliefKind.INFERENCE,
        )
        corrected = BeliefService.correct_belief(b, correction_text="Wrong")
        restored = BeliefService.restore_belief(corrected)
        assert restored.status == BeliefStatus.CANDIDATE

    def test_restore_from_supported_raises(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Test belief",
            kind=BeliefKind.OBSERVATION,
        )
        supported = BeliefService.support_belief(b, new_evidence=["e1"])
        with pytest.raises(ValueError, match="Cannot restore"):
            BeliefService.restore_belief(supported)

    def test_staleness_detection(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Old belief",
            kind=BeliefKind.INFERENCE,
        )
        # Simulate old creation date
        old = b.model_copy(update={
            "created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100),
            "staleness_window_days": 90,
        })
        stale = BeliefService.check_staleness(old)
        assert stale.status == BeliefStatus.STALE

    def test_fresh_belief_not_stale(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Fresh belief",
            kind=BeliefKind.INFERENCE,
        )
        result = BeliefService.check_staleness(b)
        assert result.status == BeliefStatus.CANDIDATE  # unchanged

    def test_corrected_belief_immune_to_staleness(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Old but corrected",
            kind=BeliefKind.INFERENCE,
        )
        corrected = BeliefService.correct_belief(b, correction_text="Still valid")
        old = corrected.model_copy(update={
            "created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200),
        })
        result = BeliefService.check_staleness(old)
        assert result.status == BeliefStatus.OWNER_CORRECTED  # not stale

    def test_falsification_condition(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Owner will get promoted this quarter",
            kind=BeliefKind.PREDICTION,
            falsification_condition="Quarter ends without promotion",
        )
        assert b.falsification_condition == "Quarter ends without promotion"

    def test_version_increments(self):
        b = BeliefService.create_belief(
            owner_user_id=uuid.uuid4(),
            claim_text="Test",
            kind=BeliefKind.INFERENCE,
        )
        assert b.version == 1
        b2 = BeliefService.support_belief(b, new_evidence=["e1"])
        assert b2.version == 2
        b3 = BeliefService.contest_belief(b2, counter_evidence=["e2"])
        assert b3.version == 3
        b4 = BeliefService.correct_belief(b3, correction_text="Fix")
        assert b4.version == 4


# ── User Model tests ──────────────────────────────────────────────────────

class TestUserModel:
    def test_create_owner_stated_claim(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="I am a software engineer",
            claim_class=ClaimClass.OWNER_STATED,
            domain="career",
        )
        assert claim.claim_class == ClaimClass.OWNER_STATED
        assert claim.sensitivity == ClaimSensitivity.ELEVATED  # career = elevated

    def test_create_inference_on_general_domain(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="User prefers dark mode",
            claim_class=ClaimClass.NUR_INFERRED,
            domain="general",
        )
        assert claim.claim_class == ClaimClass.NUR_INFERRED
        assert claim.sensitivity == ClaimSensitivity.NORMAL

    def test_block_inference_on_medical_domain(self):
        """NUR_INFERRED claims on HIGH-sensitivity domains are blocked."""
        with pytest.raises(ValueError, match="high-sensitivity"):
            UserModelService.create_claim(
                owner_user_id=uuid.uuid4(),
                claim_text="User has anxiety disorder",
                claim_class=ClaimClass.NUR_INFERRED,
                domain="medical",
            )

    def test_block_inference_on_psychological_domain(self):
        with pytest.raises(ValueError, match="high-sensitivity"):
            UserModelService.create_claim(
                owner_user_id=uuid.uuid4(),
                claim_text="User shows signs of depression",
                claim_class=ClaimClass.NUR_INFERRED,
                domain="psychological",
            )

    def test_block_inference_on_political_domain(self):
        with pytest.raises(ValueError, match="high-sensitivity"):
            UserModelService.create_claim(
                owner_user_id=uuid.uuid4(),
                claim_text="User supports party X",
                claim_class=ClaimClass.NUR_INFERRED,
                domain="political",
            )

    def test_owner_stated_on_medical_allowed(self):
        """OWNER_STATED claims on sensitive domains are fine."""
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="I have a peanut allergy",
            claim_class=ClaimClass.OWNER_STATED,
            domain="medical",
        )
        assert claim.claim_class == ClaimClass.OWNER_STATED
        assert claim.sensitivity == ClaimSensitivity.HIGH

    def test_confirm_nur_inferred(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="User prefers concise answers",
            claim_class=ClaimClass.NUR_INFERRED,
        )
        confirmed = UserModelService.confirm_claim(claim)
        assert confirmed.claim_class == ClaimClass.OWNER_CONFIRMED
        assert confirmed.confidence == 1.0

    def test_confirm_non_inferred_raises(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="I said it myself",
            claim_class=ClaimClass.OWNER_STATED,
        )
        with pytest.raises(ValueError, match="Only NUR_INFERRED"):
            UserModelService.confirm_claim(claim)

    def test_correct_claim(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="User is a morning person",
            claim_class=ClaimClass.NUR_INFERRED,
        )
        corrected = UserModelService.correct_claim(claim, correction_text="I'm a night owl")
        assert corrected.claim_class == ClaimClass.OWNER_CORRECTED
        assert corrected.correction_text == "I'm a night owl"
        assert corrected.confidence == 1.0

    def test_retract_claim(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="Old claim",
            claim_class=ClaimClass.NUR_INFERRED,
        )
        retracted = UserModelService.retract_claim(claim, reason="No longer relevant")
        assert retracted.claim_class == ClaimClass.RETRACTED
        assert retracted.retraction_reason == "No longer relevant"

    def test_contradict_claim(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="User exercises daily",
            claim_class=ClaimClass.OBSERVED_PATTERN,
            confidence=0.8,
        )
        contradicted = UserModelService.contradict_claim(
            claim, counter_evidence=["event:no-exercise-week"]
        )
        assert contradicted.claim_class == ClaimClass.CONTRADICTED
        assert contradicted.confidence < claim.confidence

    def test_promotion_rules(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="Test",
            claim_class=ClaimClass.NUR_INFERRED,
        )
        assert UserModelService.can_promote(claim, ClaimClass.OWNER_CONFIRMED) is True
        assert UserModelService.can_promote(claim, ClaimClass.OWNER_CORRECTED) is True
        assert UserModelService.can_promote(claim, ClaimClass.OWNER_STATED) is False

    def test_owner_stated_cannot_promote_to_confirmed(self):
        claim = UserModelService.create_claim(
            owner_user_id=uuid.uuid4(),
            claim_text="I said it",
            claim_class=ClaimClass.OWNER_STATED,
        )
        assert UserModelService.can_promote(claim, ClaimClass.OWNER_CONFIRMED) is False
        assert UserModelService.can_promote(claim, ClaimClass.OWNER_CORRECTED) is True


# ── Attention tests ────────────────────────────────────────────────────────

class TestAttention:
    def test_create_candidate(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Review quarterly plan",
        )
        assert item.status == AttentionStatus.CANDIDATE
        assert item.computed_score == 0.0  # all features at zero
        assert item.version == 1

    def test_scoring_determinism(self):
        """Same features must produce same score."""
        features = SalienceFeatures(
            owner_pinned=0.0,
            explicit_urgency=0.8,
            deadline_proximity=0.5,
            risk_level=0.3,
        )
        score1 = features.compute_score()
        score2 = features.compute_score()
        assert score1 == score2

    def test_owner_pinned_dominates(self):
        """Owner-pinned items must score highest."""
        pinned = SalienceFeatures(owner_pinned=1.0)
        urgent = SalienceFeatures(explicit_urgency=1.0, deadline_proximity=1.0, risk_level=1.0)
        assert pinned.compute_score() > urgent.compute_score()

    def test_repetition_reduces_score(self):
        """Repeated items should score lower."""
        fresh = SalienceFeatures(recency=0.5)
        repeated = SalienceFeatures(recency=0.5, repetition_count=1.0)
        assert fresh.compute_score() > repeated.compute_score()

    def test_activate(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        active = AttentionService.activate(item)
        assert active.status == AttentionStatus.ACTIVE

    def test_snooze(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
        snoozed = AttentionService.snooze(item, until=future)
        assert snoozed.status == AttentionStatus.SNOOZED
        assert snoozed.snoozed_until == future

    def test_dismiss_prevents_resurface(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        dismissed = AttentionService.dismiss(item)
        assert dismissed.status == AttentionStatus.DISMISSED
        # Dismissed items should not appear in ranked list
        ranked = AttentionService.rank_items([dismissed])
        assert len(ranked) == 0

    def test_resolve(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        resolved = AttentionService.resolve(item)
        assert resolved.status == AttentionStatus.RESOLVED
        assert resolved.resolved_at is not None

    def test_expire(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        expired = AttentionService.expire(item)
        assert expired.status == AttentionStatus.EXPIRED

    def test_supersede(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        superseded = AttentionService.supersede(item)
        assert superseded.status == AttentionStatus.SUPERSEDED

    def test_rank_items_by_score(self):
        uid = uuid.uuid4()
        low = AttentionService.create_item(
            owner_user_id=uid,
            title="Low",
            features=SalienceFeatures(recency=0.1),
        )
        high = AttentionService.create_item(
            owner_user_id=uid,
            title="High",
            features=SalienceFeatures(owner_pinned=1.0),
        )
        mid = AttentionService.create_item(
            owner_user_id=uid,
            title="Mid",
            features=SalienceFeatures(explicit_urgency=0.5),
        )
        ranked = AttentionService.rank_items([low, high, mid])
        assert ranked[0].title == "High"
        assert ranked[-1].title == "Low"

    def test_rank_excludes_dismissed(self):
        uid = uuid.uuid4()
        active = AttentionService.create_item(owner_user_id=uid, title="Active")
        dismissed = AttentionService.dismiss(
            AttentionService.create_item(owner_user_id=uid, title="Dismissed")
        )
        ranked = AttentionService.rank_items([active, dismissed])
        assert len(ranked) == 1
        assert ranked[0].title == "Active"

    def test_unsnooze_due(self):
        uid = uuid.uuid4()
        past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)

        due = AttentionService.snooze(
            AttentionService.create_item(owner_user_id=uid, title="Due"),
            until=past,
        )
        not_due = AttentionService.snooze(
            AttentionService.create_item(owner_user_id=uid, title="Not due"),
            until=future,
        )
        result = AttentionService.unsnooze_due([due, not_due])
        assert len(result) == 1
        assert result[0].title == "Due"

    def test_version_increments(self):
        item = AttentionService.create_item(
            owner_user_id=uuid.uuid4(),
            title="Test",
        )
        assert item.version == 1
        active = AttentionService.activate(item)
        assert active.version == 2
        snoozed = AttentionService.snooze(
            active, until=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
        )
        assert snoozed.version == 3
