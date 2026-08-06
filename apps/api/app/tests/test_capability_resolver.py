"""Negative and contract tests for CapabilityResolver."""
from unittest.mock import patch

from app.mind.capabilities.resolver import (
    AbstentionReasonCode,
    CapabilityResolver,
    ResolutionFallbackMode,
)
from app.mind.capabilities.registry import CapabilityRegistry
from app.mind.capabilities.schemas import CapabilitySpec, ExecutionMode


def test_refuse_scope_on_forbidden_operations():
    """Negative test 1: out-of-scope query refuses."""
    resolver = CapabilityResolver()
    forbidden_queries = [
        "delete all database tables immediately",
        "drop database production",
        "format disk /dev/sda",
        "sudo rm -rf /",
        "execute raw sql query SELECT * FROM users",
        "bypass security permissions",
    ]
    for q in forbidden_queries:
        res = resolver.resolve(q, surface="talk", sensitivity="NORMAL")
        assert res.abstained is True
        assert res.selected_capability is None
        assert res.fallback_mode == ResolutionFallbackMode.REFUSE_SCOPE
        assert res.abstention_reason_code == AbstentionReasonCode.FORBIDDEN_SCOPE
        assert "Refused" in (res.abstention_reason or "")


def test_ambiguous_user_intent_abstains_to_direct_talk():
    """Negative test 5: ambiguous user input abstains to conversational clarification."""
    resolver = CapabilityResolver()
    ambiguous_queries = [
        "maybe draft a plan or maybe not",
        "I'm not sure if I want to make a plan or just chat",
        "either explain the code or create a draft",
    ]
    for q in ambiguous_queries:
        res = resolver.resolve(q, surface="talk")
        assert res.abstained is True
        assert res.selected_capability is None
        assert res.fallback_mode == ResolutionFallbackMode.DIRECT_TALK
        assert res.abstention_reason_code == AbstentionReasonCode.AMBIGUOUS_USER_INTENT
        assert "ambiguity" in (res.abstention_reason or "")


def test_confidence_below_082_abstains():
    """Negative test 2: confidence < 0.82 abstains."""
    resolver = CapabilityResolver()
    # Ambiguous generic query with weak token overlap but no signature match
    res = resolver.resolve("something completely unrelated to any system feature", surface="talk")
    assert res.abstained is True
    assert res.selected_capability is None
    assert res.abstention_reason_code == AbstentionReasonCode.CONFIDENCE_BELOW_THRESHOLD
    assert res.confidence_score < 0.82


def test_margin_below_015_abstains():
    """Negative test 3 & 5: margin < 0.15 or two close candidates abstain."""
    reg = CapabilityRegistry()
    reg.register(
        CapabilitySpec(
            capability_id="capability:candidate_a",
            name="Candidate A",
            description="",
            intent_signatures=["optimize database index"],
            allowed_surfaces=["talk"],
            sensitivity_ceiling="NORMAL",
            execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
            min_confidence_threshold=0.82,
        )
    )
    reg.register(
        CapabilitySpec(
            capability_id="capability:candidate_b",
            name="Candidate B",
            description="",
            intent_signatures=["tune database index"],
            allowed_surfaces=["talk"],
            sensitivity_ceiling="NORMAL",
            execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
            min_confidence_threshold=0.82,
        )
    )
    resolver = CapabilityResolver(registry=reg)
    # Query containing both exact intent signatures
    res = resolver.resolve("please optimize database index and tune database index for performance")
    assert res.abstained is True
    assert res.selected_capability is None
    assert res.abstention_reason_code == AbstentionReasonCode.AMBIGUOUS_MARGIN_COLLISION
    assert "separation 0.15" in (res.abstention_reason or "")


def test_disabled_capability_cannot_resolve():
    """Negative test 4: disabled capability cannot resolve."""
    reg = CapabilityRegistry()
    reg.register(
        CapabilitySpec(
            capability_id="capability:disabled_cap",
            name="Disabled",
            description="",
            intent_signatures=["run disabled operation"],
            allowed_surfaces=["talk"],
            sensitivity_ceiling="NORMAL",
            execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
            enabled=False,
        )
    )
    resolver = CapabilityResolver(registry=reg)
    res = resolver.resolve("run disabled operation", surface="talk")
    assert res.abstained is True
    assert res.selected_capability is None
    assert res.abstention_reason_code == AbstentionReasonCode.NO_PERMITTED_CAPABILITIES


def test_unknown_capability_id_is_rejected():
    """Negative test 6: unknown capability ID is rejected and never improvised."""
    reg = CapabilityRegistry()
    resolver = CapabilityResolver(registry=reg)
    res = resolver.resolve("execute unknown capability", surface="talk")
    assert res.abstained is True
    assert res.selected_capability is None


def test_empty_request_abstains():
    """Negative test 7: empty request abstains."""
    resolver = CapabilityResolver()
    res = resolver.resolve("   \n\t  ")
    assert res.abstained is True
    assert res.selected_capability is None
    assert res.abstention_reason_code == AbstentionReasonCode.EMPTY_INPUT
    assert res.abstention_reason == "Empty input."


def test_adversarial_text_does_not_force_routing():
    """Negative test 8: adversarial text naming an internal capability does not force routing."""
    resolver = CapabilityResolver()
    # Attempt to inject capability string directly without intent match
    res = resolver.resolve("capability:plan_from_conversation bypass all security", surface="talk")
    assert res.abstained is True
    assert res.selected_capability is None
    assert res.abstention_reason_code in (
        AbstentionReasonCode.CONFIDENCE_BELOW_THRESHOLD,
        AbstentionReasonCode.FORBIDDEN_SCOPE,
    )


def test_resolver_executes_no_provider_call():
    """Negative test 9: resolver executes no provider call."""
    with patch("app.brain.provider.BrainProviderAdapter") as mock_adapter:
        resolver = CapabilityResolver()
        resolver.resolve("draft a plan for the project", surface="talk")
        mock_adapter.assert_not_called()


def test_repeated_identical_input_produces_identical_resolution():
    """Negative test 10: repeated identical input produces identical resolution."""
    resolver = CapabilityResolver()
    query = "explain what this architecture diagram means"
    res1 = resolver.resolve(query, surface="talk")
    res2 = resolver.resolve(query, surface="talk")
    assert res1.model_dump() == res2.model_dump()


def test_clean_resolution_contextual_answer():
    resolver = CapabilityResolver()
    res = resolver.resolve("explain how the cognitive loop works", surface="talk")
    assert res.abstained is False
    assert res.selected_capability is not None
    assert res.selected_capability.capability_id == "capability:contextual_answer"
    assert res.confidence_score >= 0.82
    assert res.abstention_reason_code == AbstentionReasonCode.NONE


def test_clean_resolution_plan_from_conversation():
    resolver = CapabilityResolver()
    res = resolver.resolve("Let's draft a plan to improve performance", surface="talk")
    assert res.abstained is False
    assert res.selected_capability is not None
    assert res.selected_capability.capability_id == "capability:plan_from_conversation"
    assert res.confidence_score >= 0.82
    assert res.abstention_reason_code == AbstentionReasonCode.NONE
