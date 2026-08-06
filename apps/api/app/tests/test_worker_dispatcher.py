"""Unit tests for NUR Mind WorkerDispatcher."""
import ast
import uuid
from pathlib import Path
import pytest
from unittest.mock import AsyncMock

from app.ai.schemas import EvidenceRef
from app.brain.schemas import BrainProfileKey, ContextManifest, ScopeEnvelope
from app.mind.capabilities.dispatcher import WorkerDispatcher
from app.mind.capabilities.hydrator import HydratedCapabilityContext
from app.mind.capabilities.schemas import CapabilitySpec, ExecutionMode


def test_structural_dispatcher_imports():
    """Prove dispatcher does not import prohibited side-effect or provider modules."""
    dispatcher_path = Path(__file__).resolve().parent.parent / "mind" / "capabilities" / "dispatcher.py"
    assert dispatcher_path.exists(), f"File not found: {dispatcher_path}"

    tree = ast.parse(dispatcher_path.read_text(encoding="utf-8"))
    prohibited_prefixes = (
        "app.agentic.handlers",
        "app.agentic.registry.handler",
        "celery",
        "openai",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prohibited in prohibited_prefixes:
                    assert not alias.name.startswith(prohibited), f"Prohibited import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for prohibited in prohibited_prefixes:
                assert not mod.startswith(prohibited), f"Prohibited from-import: {mod}"


@pytest.mark.asyncio
async def test_worker_dispatcher_cognitive_synthesis_returns_none():
    db_mock = AsyncMock()
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    manifest = ContextManifest(scope_statement="Private", token_budget=2000)
    ctx = HydratedCapabilityContext(
        capability_id="capability:contextual_answer",
        scope_envelope=scope,
        manifest=manifest,
    )

    spec = CapabilitySpec(
        capability_id="capability:contextual_answer",
        name="Contextual Answer",
        description="Conversational dialogue",
        intent_signatures=["chat", "talk"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
    )

    result = await WorkerDispatcher.dispatch(
        db_mock,
        owner_user_id=owner_id,
        capability=spec,
        hydrated_context=ctx,
        query="What is my schedule?",
    )

    # Standard cognitive synthesis passes through to Brain provider loop
    assert result is None


@pytest.mark.asyncio
async def test_worker_dispatcher_read_only_worker():
    from app.mind.capabilities.dispatcher import register_read_only_worker
    from app.brain.schemas import BrainProfileKey, CognitiveClaim, CognitiveResult

    async def _custom_worker(cap, ctx, q, tid):
        plans = ctx.active_plans or []
        return CognitiveResult(
            task_id=tid,
            profile_used=BrainProfileKey.FAST,
            direct_response=f"Active Plans: {len(plans)} - Cognitive Runtime PR",
            workflow_proposal=None,
            decision_summary="Test worker summary",
            claims=[CognitiveClaim(claim_text=f"Active plans: {len(plans)}", claim_kind="observed", confidence=1.0)],
            cost_estimate_cents=0,
        )

    register_read_only_worker("capability:test_read_only_worker", _custom_worker)

    db_mock = AsyncMock()
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    manifest = ContextManifest(scope_statement="Private", token_budget=2000)
    ctx = HydratedCapabilityContext(
        capability_id="capability:test_read_only_worker",
        scope_envelope=scope,
        manifest=manifest,
        retrieval_refs=[EvidenceRef(kind="note", id="note-1", excerpt="Summary note", rank=1.0)],
        today_state={"phase": "Flow", "focus": "Complete Task PR-2"},
        active_plans=[{"title": "Cognitive Runtime PR"}],
        timeline_events=[{"title": "Reviewed PR-1"}],
    )

    spec = CapabilitySpec(
        capability_id="capability:test_read_only_worker",
        name="Test Worker",
        description="Read only test worker",
        intent_signatures=["test status"],
        execution_mode=ExecutionMode.READ_ONLY_WORKER,
        required_tools=[],
    )

    task_id = uuid.uuid4()
    result = await WorkerDispatcher.dispatch(
        db_mock,
        owner_user_id=owner_id,
        capability=spec,
        hydrated_context=ctx,
        query="Give me a summary of project status",
        task_id=task_id,
    )

    assert result is not None
    assert result.task_id == task_id
    assert result.profile_used == BrainProfileKey.FAST
    assert "Active Plans: 1" in result.direct_response
    assert "Cognitive Runtime PR" in result.direct_response
    assert len(result.claims) == 1
    assert result.workflow_proposal is None


@pytest.mark.asyncio
async def test_worker_dispatcher_workflow_proposal_worker():
    db_mock = AsyncMock()
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    manifest = ContextManifest(scope_statement="Private", token_budget=2000)
    ctx = HydratedCapabilityContext(
        capability_id="capability:plan_from_conversation",
        scope_envelope=scope,
        manifest=manifest,
    )

    spec = CapabilitySpec(
        capability_id="capability:plan_from_conversation",
        name="Plan from Conversation",
        description="Structured plan proposals",
        intent_signatures=["draft a plan", "plan"],
        execution_mode=ExecutionMode.WORKFLOW_PROPOSAL,
        required_tools=["create_draft_plan", "get_plan"],
    )

    task_id = uuid.uuid4()
    result = await WorkerDispatcher.dispatch(
        db_mock,
        owner_user_id=owner_id,
        capability=spec,
        hydrated_context=ctx,
        query="Let's draft a plan to release the new cognitive runtime",
        task_id=task_id,
    )

    assert result is not None
    assert result.task_id == task_id
    assert result.profile_used == BrainProfileKey.BALANCED
    assert result.workflow_proposal is not None
    assert "Release the new cognitive runtime" in result.workflow_proposal.title
    assert len(result.workflow_proposal.steps) == 1
    step = result.workflow_proposal.steps[0]
    assert step.tool_key == "create_draft_plan"
    assert step.requires_approval is True
    assert step.arguments["title"] == "Release the new cognitive runtime"
    assert "steps" in step.arguments
    assert "objective" not in step.arguments

