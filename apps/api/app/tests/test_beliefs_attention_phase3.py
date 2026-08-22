"""Unit tests for Phase 3: Beliefs, User Model & Attention.

Tests:
1. User model: claim promotion rules, sensitive inference blocking, owner correction precedence
2. Attention: scoring determinism, lifecycle transitions, dismissed items don't resurface

Durable belief lifecycle coverage lives in ``test_outcome_learning_loop.py``.
The former in-memory belief service was removed so ``SemanticClaim`` and
``ClaimEvidence`` remain the single Mind belief authority.
"""

import datetime as dt
import uuid

import pytest

from app.mind.user_model import ClaimClass, ClaimSensitivity, UserModelService
from app.mind.attention import (
    AttentionService,
    AttentionStatus,
    SalienceFeatures,
)


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
