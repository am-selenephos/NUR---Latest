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
from app.brain.router import classify_stakes
from app.brain.schemas import BrainProfileKey, CognitiveResult, CognitiveClaim
from app.brain.synthesizer import synthesize_talk_output
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
    from app.brain.schemas import SelfCapabilities, ContextManifest, CognitiveTaskPacket

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
        scope_envelope_id=import_uuid(),  # Phase 1: scope must be resolved
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


@pytest.mark.asyncio
async def test_metacognitive_ten_checkpoints():
    import uuid
    from app.brain.schemas import CognitiveTaskPacket, CognitiveResult, BrainProfileKey, SelfCapabilities, ContextManifest
    from app.mind.identity import load_identity
    from app.mind.metacognition import run_metacognitive_review

    identity = load_identity()
    packet = CognitiveTaskPacket(
        task_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        task_class="talk",
        identity=identity,
        user_input="Hello NUR",
        self_capabilities=SelfCapabilities(provider_name="openai", provider_available=True),
        context_manifest=ContextManifest(scope_statement="Private owner scope"),
        evidence_refs=[],
        scope_envelope_id=uuid.uuid4(),  # Phase 1: scope must be resolved
    )

    # 1. Clean valid result -> PASS
    clean_result = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.FAST,
        direct_response="Hello! I am NUR, your companion.",
        claims=[],
        hypotheses=[],
        uncertainty=[],
        next_move=None,
        memory_candidates=[],
        source_refs=[],
    )
    rev = run_metacognitive_review(packet, clean_result)
    assert rev.checkpoint_passed is True
    assert rev.verdict == "PASS"
    assert len(rev.checks) == 11  # 10 original + scope_envelope_enforced
    assert all(rev.checks.values()) is True

    # 2. Forbidden claim -> BLOCK
    forbidden_result = clean_result.model_copy(update={
        "direct_response": "I am sentient and have real human feelings and emotions.",
    })
    rev_forbidden = run_metacognitive_review(packet, forbidden_result)
    assert rev_forbidden.checkpoint_passed is False
    assert rev_forbidden.verdict == "BLOCK"
    assert rev_forbidden.checks["no_forbidden_claims"] is False

    # 3. Durable action missing WorkflowProposal container -> BLOCK
    unsafe_action_result = clean_result.model_copy(update={
        "proposed_actions": ["delete all files"],
        "workflow_proposal": None,
    })
    rev_unsafe = run_metacognitive_review(packet, unsafe_action_result)
    assert rev_unsafe.checkpoint_passed is False
    assert rev_unsafe.verdict == "BLOCK"
    assert rev_unsafe.checks["state_mutation_safety"] is False


@pytest.mark.asyncio
async def test_deterministic_evidence_validator():
    import uuid
    from app.brain.critic import DeterministicEvidenceValidator
    from app.brain.schemas import CognitiveTaskPacket, CognitiveResult, BrainProfileKey, CognitiveClaim, SelfCapabilities, ContextManifest
    from app.mind.identity import load_identity

    validator = DeterministicEvidenceValidator()
    packet = CognitiveTaskPacket(
        task_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        task_class="talk",
        identity=load_identity(),
        user_input="What did I work on?",
        self_capabilities=SelfCapabilities(provider_name="openai", provider_available=True),
        context_manifest=ContextManifest(scope_statement="Private owner scope"),
        evidence_refs=[{"kind": "memory", "id": "m1", "excerpt": "Worked on NUR"}],
    )

    # 1. Properly cited -> PASS
    valid_res = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.FAST,
        direct_response="You worked on NUR.",
        claims=[CognitiveClaim(claim_text="Worked on NUR", claim_kind="observed", source_refs=["memory:m1"])],
        source_refs=["memory:m1"],
    )
    res_pass = validator.verify_result(packet, valid_res)
    assert res_pass.critic_verdict == "PASS"

    # 2. Uncited claim -> WARN
    uncited_res = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.FAST,
        direct_response="You worked on NUR.",
        claims=[CognitiveClaim(claim_text="Worked on NUR", claim_kind="observed", source_refs=[])],
        source_refs=[],
    )
    res_warn = validator.verify_result(packet, uncited_res)
    assert res_warn.critic_verdict == "WARN"

    # 3. Missing cited ref (hallucinated ref) -> BLOCK
    hallucinated_res = CognitiveResult(
        task_id=packet.task_id,
        profile_used=BrainProfileKey.FAST,
        direct_response="You worked on NUR.",
        claims=[CognitiveClaim(claim_text="Worked on NUR", claim_kind="observed", source_refs=["memory:m999"])],
        source_refs=["memory:m999"],
    )
    res_block = validator.verify_result(packet, hallucinated_res)
    assert res_block.critic_verdict == "BLOCK"


@pytest.mark.asyncio
async def test_openai_talk_provider_privileged_system_prompt_and_profile_params():
    from pydantic import SecretStr
    from app.ai.openai_provider import OpenAITalkProvider
    from app.ai.schemas import TalkProviderRequest
    from app.core.config import Settings

    custom_settings = Settings(
        openai_api_key=SecretStr("sk-test-key-12345"),
        openai_model="gpt-5.4-mini",
        openai_reasoning_effort="low",
    )

    provider = OpenAITalkProvider(settings=custom_settings)

    req = TalkProviderRequest(
        user_line="Hello",
        system_prompt="PRIVILEGED SYSTEM IDENTITY PROMPT",
        reasoning_effort="high",
        max_output_tokens=1500,
        model="gpt-5.4-full",
        output_schema={"type": "json_object"},
    )

    payload = provider._payload(req)

    # Verify privileged system prompt is passed as top-level system message
    assert payload["input"][0]["role"] == "system"
    assert payload["input"][0]["content"] == "PRIVILEGED SYSTEM IDENTITY PROMPT"

    # Verify model override
    assert payload["model"] == "gpt-5.4-full"

    # Verify max_output_tokens
    assert payload["max_output_tokens"] == 1500

    # Verify custom format schema
    assert payload["text"]["format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_mind_loop_ordinary_talk_vs_durable_action(client, super_engine, monkeypatch):
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select

    from app.db.rls import set_user_context
    from app.models.agentic import AgentWorkflow, AgentPolicy, AgentApproval
    from app.mind.cognitive_loop import run_mind_cognitive_loop
    from app.tests.conftest import register_user
    from app.ai.schemas import NURTalkOutput, AIProviderResult

    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        # Provision policy allowing create_draft_plan
        db.add(AgentPolicy(
            owner_user_id=owner_user_id,
            initiative_level="SUGGEST",
            max_risk_class="R1_PRIVATE_DRAFT",
            permitted_tools=["create_draft_plan"],
            auto_run_tools=[],
        ))
        await db.commit()

    class MockProvider:
        name = "openai"

        def __init__(self, output_fn):
            self.output_fn = output_fn

        async def complete_private_talk(self, request, event_sink=None):
            return await self.output_fn(request, event_sink=event_sink)

    # Case 1: Ordinary Talk -> No WorkflowProposal created
    async def mock_ordinary_talk(request, event_sink=None):
        return AIProviderResult(
            provider="openai",
            model="gpt-5.4-mini",
            available=True,
            output=NURTalkOutput(
                direct_response="This is an ordinary talk response.",
                observed=[],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move=None,
                memory_candidates=[],
                source_refs=[],
            ),
        )

    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: MockProvider(mock_ordinary_talk))

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        res1 = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Hello NUR",
        )
        assert res1.output.direct_response == "This is an ordinary talk response."

        # Verify no workflow was created
        workflows = (await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))).scalars().all()
        assert len(workflows) == 0

    # Case 2: Durable Action intent in next_move -> WorkflowProposal submitted to Agency in BLOCKED_ON_APPROVAL state
    async def mock_action_talk(request, event_sink=None):
        return AIProviderResult(
            provider="openai",
            model="gpt-5.4-mini",
            available=True,
            output=NURTalkOutput(
                direct_response="I will prepare a draft plan for you.",
                observed=[],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move="create a draft project plan for migration",
                memory_candidates=[],
                source_refs=[],
            ),
        )

    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: MockProvider(mock_action_talk))

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        res2 = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Please draft the project plan",
        )
        assert res2.output.direct_response == "I will prepare a draft plan for you."

        # Verify a workflow was created in BLOCKED_ON_APPROVAL state
        workflows = (await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))).scalars().all()
        assert len(workflows) == 1
        wf = workflows[0]
        assert wf.state == "BLOCKED_ON_APPROVAL"

        # Verify an AgentApproval was persisted in PENDING decision state
        approvals = (await db.execute(select(AgentApproval).where(AgentApproval.owner_user_id == owner_user_id))).scalars().all()
        assert len(approvals) >= 1
        assert any(a.decision == "PENDING" for a in approvals)
