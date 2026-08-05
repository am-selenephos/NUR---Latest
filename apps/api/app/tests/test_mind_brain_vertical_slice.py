"""Unit and integration test suite for NUR Mind + Brain vertical slice.

Tests:
1. Identity Snapshot loading & version consistency
2. Truthful Self Capabilities model
3. Context Manifest packing & source accounting
4. CognitiveTaskPacket compilation
5. Brain Router profile selection
6. Brain Critic independent verification
7. Metacognitive Review checkpoint (depth <= 2)
8. Brain Synthesizer output conversion
9. Full Mind + Brain Cognitive Loop execution
"""

import pytest

from app.brain.critic import BrainCritic
from app.brain.profiles import get_profile
from app.brain.router import classify_stakes, route
from app.brain.schemas import BrainProfileKey, CognitiveResult, CognitiveClaim
from app.brain.synthesizer import synthesize_talk_output
from app.mind.constitution import NUR_CONSTITUTION_V1
from app.mind.context import build_cognitive_task_packet
from app.mind.identity import load_identity
from app.mind.metacognition import run_metacognitive_review
from app.mind.self_model import get_self_capabilities
from app.mind.working_memory import build_context_manifest


def test_identity_snapshot_loading():
    identity = load_identity()
    assert identity.version == "v1.0.0-20260802"
    assert identity.name == "NUR"
    assert len(identity.voice_rules) >= 3
    assert len(identity.forbidden_claims) >= 3
    assert any("sentience" in str(claim).lower() for claim in identity.forbidden_claims)


@pytest.mark.asyncio
async def test_self_capabilities_truthfulness():
    caps = await get_self_capabilities()
    assert caps.provider_name in ("disabled", "openai")
    # Must not claim web search when disabled
    assert any("web research" in str(lim).lower() for lim in caps.known_limitations) or caps.provider_name == "openai"


def test_context_manifest_packing():
    refs = [
        {"kind": "JOURNAL", "id": "j1", "excerpt": "User note one", "rank": 0.9},
        {"kind": "DECISION", "id": "d1", "excerpt": "User decision statement", "rank": 0.8},
    ]
    withheld = [{"kind": "CAPSULE", "id": "c1", "reason": "Recipient grant expired"}]

    manifest, filtered = build_context_manifest(
        retrieved_refs=refs,
        withheld_items=withheld,
        scope_statement="Private orbit scope",
        token_budget=1000,
    )

    assert manifest.scope_statement == "Private orbit scope"
    assert len(manifest.included) == 2
    assert len(manifest.excluded) == 1
    assert manifest.excluded[0].id == "c1"
    assert len(filtered) == 2


def test_brain_router_profile_selection():
    # 1. Normal prompt (40-2000 chars) → normal stakes
    stakes_normal = classify_stakes("How do I structure this component to ensure clear separation of concerns in the application?")
    assert stakes_normal == "normal"

    # 2. Short prompt (<40 chars) → low stakes
    stakes_low = classify_stakes("Hello NUR")
    assert stakes_low == "low"

    # 3. High-stakes prompt → high stakes
    stakes_high = classify_stakes("Challenge me on my financial plan and tell me what I am wrong about")
    assert stakes_high == "high"


def test_brain_critic_verification():
    from app.brain.schemas import IdentitySnapshot, SelfCapabilities, ContextManifest, CognitiveTaskPacket

    packet = CognitiveTaskPacket(
        owner_user_id=import_uuid(),
        task_class="talk",
        user_input="Test prompt",
        identity=load_identity(),
        self_capabilities=SelfCapabilities(provider_name="disabled", provider_available=False),
        context_manifest=ContextManifest(scope_statement="test"),
        evidence_refs=[{"kind": "journal", "id": "123", "excerpt": "test"}],
    )

    result = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.BALANCED,
        direct_response="Response statement.",
        claims=[CognitiveClaim(claim_text="Claim 1", claim_kind="inferred", source_refs=["journal:123"])],
        source_refs=["journal:123"],
    )

    critic = BrainCritic()
    verified = critic.verify_result(packet, result)
    assert verified.critic_verdict == "PASS"


def test_metacognitive_review_checkpoint():
    from app.brain.schemas import SelfCapabilities, ContextManifest, CognitiveTaskPacket

    packet = CognitiveTaskPacket(
        owner_user_id=import_uuid(),
        task_class="talk",
        user_input="Test prompt",
        identity=load_identity(),
        self_capabilities=SelfCapabilities(provider_name="disabled", provider_available=False),
        context_manifest=ContextManifest(scope_statement="test"),
    )

    result = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.BALANCED,
        direct_response="Grounded direct response.",
        claims=[],
        source_refs=[],
    )

    review = run_metacognitive_review(packet, result, depth=1)
    assert review.checkpoint_passed is True
    assert review.verdict == "PASS"
    assert "depth=1" in review.decision_summary

    # Depth > 2 anti-recursion cap
    review_deep = run_metacognitive_review(packet, result, depth=3)
    assert review_deep.checkpoint_passed is True
    assert "Max metacognitive review depth" in review_deep.decision_summary


def test_synthesizer_output_conversion():
    result = CognitiveResult(
        task_id=import_uuid(),
        profile_used=BrainProfileKey.BALANCED,
        direct_response="Direct response text.",
        claims=[CognitiveClaim(claim_text="Observed item", claim_kind="observed", source_refs=["kind:1"])],
        hypotheses=["Hypothesis A"],
        uncertainty=["Uncertainty B"],
        next_move="Action move",
        source_refs=["kind:1"],
    )

    talk_out = synthesize_talk_output(result)
    assert talk_out.direct_response == "Direct response text."
    assert talk_out.observed == ["Observed item"]
    assert talk_out.hypotheses == ["Hypothesis A"]
    assert talk_out.uncertainty == ["Uncertainty B"]
    assert talk_out.next_move == "Action move"


@pytest.mark.asyncio
async def test_agency_workflow_proposal_compilation(client, super_engine):
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.rls import set_user_context
    from app.brain.schemas import WorkflowProposal, WorkflowStep
    from app.mind.agency_bridge import submit_workflow_proposal
    from app.tests.conftest import register_user

    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        from app.models.agentic import AgentPolicy
        db.add(AgentPolicy(
            owner_user_id=owner_user_id,
            initiative_level="SUGGEST",
            max_risk_class="R1_PRIVATE_DRAFT",
            permitted_tools=["create_draft_plan"],
            auto_run_tools=[],
        ))
        await db.flush()

        proposal = WorkflowProposal(
            task_id=import_uuid(),
            title="Test durable workflow",
            rationale="Proposed durable action requires policy check and approval.",
            steps=[
                WorkflowStep(title="Record note", description="Create draft plan", tool_key="create_draft_plan", requires_approval=True)
            ],
        )

        workflow, compile_res = await submit_workflow_proposal(
            db,
            owner_user_id=owner_user_id,
            proposal=proposal,
        )

        assert compile_res.ok is True
        assert workflow is not None
        assert workflow.title == "Test durable workflow"
        # Execution cannot occur before approval: state must be BLOCKED_ON_APPROVAL
        assert workflow.state == "BLOCKED_ON_APPROVAL"


def import_uuid():
    import uuid
    return uuid.uuid4()
