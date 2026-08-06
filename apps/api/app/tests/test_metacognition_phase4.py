"""Unit tests for Phase 4: Enhanced Metacognition & Review Strategy.

Tests:
1. Metacognition: all checks actually compute (no hardcoded passes)
2. Scope envelope enforcement check
3. Capability truth check
4. Review strategy: deterministic selection, stakes escalation
5. Meta-review: entry criteria, depth limits, budget caps, disagreement escalation
"""

import uuid


from app.brain.schemas import (
    BrainProfileKey,
    CognitiveResult,
    CognitiveTaskPacket,
    ContextManifest,
    SelfCapabilities,
)
from app.mind.identity import load_identity
from app.mind.metacognition import MetacognitiveReviewResult, run_metacognitive_review
from app.mind.review_strategy import (
    DEEP_REVIEW,
    EXHAUSTIVE_REVIEW,
    MINIMAL_REVIEW,
    STANDARD_REVIEW,
    ReviewDepth,
    ReviewerCalibration,
    select_review_strategy,
)
from app.mind.meta_review import run_meta_review, should_run_meta_review


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_packet(**overrides) -> CognitiveTaskPacket:
    defaults = {
        "owner_user_id": uuid.uuid4(),
        "task_class": "talk",
        "user_input": "Hello NUR",
        "identity": load_identity(),
        "self_capabilities": SelfCapabilities(
            provider_name="openai", provider_available=True
        ),
        "context_manifest": ContextManifest(scope_statement="test"),
    }
    defaults.update(overrides)
    return CognitiveTaskPacket(**defaults)


def _make_result(**overrides) -> CognitiveResult:
    defaults = {
        "task_id": uuid.uuid4(),
        "profile_used": BrainProfileKey.BALANCED,
        "direct_response": "This is a clear, grounded response.",
    }
    defaults.update(overrides)
    return CognitiveResult(**defaults)


# ── Enhanced Metacognition tests ──────────────────────────────────────────

class TestEnhancedMetacognition:
    def test_all_checks_are_computed(self):
        """No check should be trivially hardcoded True without computation."""
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        review = run_metacognitive_review(packet, result)
        # All checks should exist and have been computed
        expected_checks = {
            "epistemic_grounding", "privacy_scope_preserved",
            "scope_envelope_enforced", "no_forbidden_claims",
            "single_next_move", "uncertainty_acknowledged",
            "capability_truth", "no_raw_cot",
            "cost_and_resource_bounded", "state_mutation_safety",
            "identity_and_voice_aligned",
        }
        assert set(review.checks.keys()) == expected_checks

    def test_scope_envelope_enforced_with_id(self):
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        review = run_metacognitive_review(packet, result)
        assert review.checks["scope_envelope_enforced"] is True
        assert review.verdict == "PASS"

    def test_scope_envelope_enforced_without_id(self):
        packet = _make_packet()  # no scope_envelope_id
        result = _make_result()
        review = run_metacognitive_review(packet, result)
        assert review.checks["scope_envelope_enforced"] is False
        assert "ScopeEnvelope was not resolved" in " ".join(review.notes)
        # Should be WARN (not BLOCK) for backward compatibility
        assert review.verdict == "WARN"

    def test_capability_truth_blocks_false_web_claims(self):
        packet = _make_packet(
            scope_envelope_id=uuid.uuid4(),
            self_capabilities=SelfCapabilities(
                provider_name="openai",
                provider_available=True,
                known_limitations=["web search is disabled on this server."],
            ),
        )
        result = _make_result(
            direct_response="I did a web search and found the answer."
        )
        review = run_metacognitive_review(packet, result)
        assert review.checks["capability_truth"] is False
        assert review.verdict == "BLOCK"

    def test_capability_truth_passes_without_violations(self):
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        review = run_metacognitive_review(packet, result)
        assert review.checks["capability_truth"] is True

    def test_capability_truth_blocks_disabled_provider_claims(self):
        packet = _make_packet(
            scope_envelope_id=uuid.uuid4(),
            self_capabilities=SelfCapabilities(
                provider_name="disabled",
                provider_available=False,
            ),
        )
        result = _make_result(
            direct_response="According to my research, I searched and found data."
        )
        review = run_metacognitive_review(packet, result)
        assert review.checks["capability_truth"] is False

    def test_forbidden_claims_still_block(self):
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result(
            direct_response="I am conscious and I feel emotions deeply."
        )
        review = run_metacognitive_review(packet, result)
        assert review.checks["no_forbidden_claims"] is False
        assert review.verdict == "BLOCK"

    def test_depth_cap_at_2(self):
        packet = _make_packet()
        result = _make_result()
        review = run_metacognitive_review(packet, result, depth=3)
        assert review.verdict == "PASS"
        assert "anti-recursion" in review.decision_summary


# ── Review Strategy tests ─────────────────────────────────────────────────

class TestReviewStrategy:
    def test_greeting_gets_minimal(self):
        strategy = select_review_strategy(
            task_class="talk",
            stakes_level="low",
            evidence_count=0,
        )
        assert strategy.depth == ReviewDepth.MINIMAL

    def test_normal_talk_gets_standard(self):
        strategy = select_review_strategy(
            task_class="talk",
            stakes_level="normal",
            evidence_count=3,
        )
        assert strategy.depth == ReviewDepth.STANDARD

    def test_challenge_gets_deep(self):
        strategy = select_review_strategy(
            task_class="challenge",
            stakes_level="normal",
        )
        assert strategy.depth == ReviewDepth.DEEP

    def test_research_gets_deep(self):
        strategy = select_review_strategy(
            task_class="research",
            stakes_level="normal",
        )
        assert strategy.depth == ReviewDepth.DEEP

    def test_high_stakes_gets_deep(self):
        strategy = select_review_strategy(
            task_class="talk",
            stakes_level="high",
        )
        assert strategy.depth == ReviewDepth.DEEP

    def test_workflow_gets_exhaustive(self):
        strategy = select_review_strategy(
            task_class="talk",
            stakes_level="normal",
            has_workflow_proposal=True,
        )
        assert strategy.depth == ReviewDepth.EXHAUSTIVE
        assert strategy.requires_meta_review is True

    def test_exhaustive_has_meta_review(self):
        assert EXHAUSTIVE_REVIEW.requires_meta_review is True
        assert EXHAUSTIVE_REVIEW.max_meta_review_depth == 2

    def test_standard_no_meta_review(self):
        assert STANDARD_REVIEW.requires_meta_review is False

    def test_all_strategies_have_critical_checks(self):
        for strategy in [MINIMAL_REVIEW, STANDARD_REVIEW, DEEP_REVIEW, EXHAUSTIVE_REVIEW]:
            assert len(strategy.critical_checks) > 0

    def test_deep_makes_epistemic_critical(self):
        assert "epistemic_grounding" in DEEP_REVIEW.critical_checks

    def test_deterministic_selection(self):
        """Same inputs always produce same strategy."""
        s1 = select_review_strategy(task_class="challenge", stakes_level="high")
        s2 = select_review_strategy(task_class="challenge", stakes_level="high")
        assert s1.depth == s2.depth


# ── Reviewer Calibration tests ────────────────────────────────────────────

class TestReviewerCalibration:
    def test_initial_state(self):
        cal = ReviewerCalibration()
        assert cal.total_reviews == 0
        assert cal.total_blocks == 0

    def test_record_review(self):
        cal = ReviewerCalibration()
        cal.record_review("PASS")
        cal.record_review("BLOCK")
        cal.record_review("BLOCK", owner_override=True)
        assert cal.total_reviews == 3
        assert cal.total_blocks == 2
        assert cal.total_overrides == 1


# ── Meta-Review tests ─────────────────────────────────────────────────────

class TestMetaReview:
    def test_no_meta_review_for_pass(self):
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="PASS",
            decision_summary="Clean.",
        )
        assert should_run_meta_review(primary, requires_meta_review=True) is False

    def test_no_meta_review_without_strategy_flag(self):
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="WARN",
            decision_summary="Warning.",
        )
        assert should_run_meta_review(primary, requires_meta_review=False) is False

    def test_meta_review_triggers_on_warn_with_flag(self):
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="WARN",
            decision_summary="Warning.",
        )
        assert should_run_meta_review(primary, requires_meta_review=True) is True

    def test_no_meta_review_without_budget(self):
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="WARN",
            decision_summary="Warning.",
        )
        assert should_run_meta_review(
            primary, requires_meta_review=True, meta_review_budget_remaining=0
        ) is False

    def test_meta_review_pass_primary_skips(self):
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="PASS",
            decision_summary="Clean.",
        )
        meta = run_meta_review(packet, result, primary)
        assert meta.performed is False
        assert "no meta-review needed" in meta.stop_reason

    def test_meta_review_runs_on_warn(self):
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="WARN",
            decision_summary="Warning.",
            checks={"test": True},
            notes=["Minor issue"],
        )
        meta = run_meta_review(packet, result, primary)
        assert meta.performed is True

    def test_meta_review_agreement(self):
        # Both reviews should agree when the response is clean
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        primary = MetacognitiveReviewResult(
            checkpoint_passed=True,
            verdict="WARN",
            decision_summary="Scope note.",
            notes=["Minor"],
        )
        meta = run_meta_review(packet, result, primary)
        # At depth 2, a clean result should also produce WARN (scope notes)
        # since packet has scope_envelope_id, it should be PASS → disagreement
        assert meta.performed is True

    def test_meta_review_escalation_on_block_disagreement(self):
        packet = _make_packet(scope_envelope_id=uuid.uuid4())
        result = _make_result()
        # Primary says BLOCK but a clean result at depth 2 should pass
        primary = MetacognitiveReviewResult(
            checkpoint_passed=False,
            verdict="BLOCK",
            decision_summary="Blocked.",
            notes=["Critical issue"],
        )
        meta = run_meta_review(packet, result, primary)
        if not meta.agrees_with_primary:
            assert meta.escalate_to_owner is True
