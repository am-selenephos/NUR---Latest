"""Integration tests for NUR Mind Capability Runtime in Cognitive Loop."""
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import AIProviderResult, NURTalkOutput
from app.db.rls import set_user_context
from app.mind.cognitive_loop import run_mind_cognitive_loop
from app.models import ModelRun
from app.models.agentic import AgentApproval, AgentPolicy, AgentWorkflow
from app.tests.conftest import register_user


@pytest.mark.asyncio
async def test_capability_loop_direct_dialogue(client, super_engine, monkeypatch):
    """Conversational dialogue runs through COGNITIVE_SYNTHESIS."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async def mock_dialogue_provider(request, event_sink=None):
        return AIProviderResult(
            provider="openai",
            model="gpt-5.4-mini",
            available=True,
            output=NURTalkOutput(
                direct_response="Hello! I am NUR, your cognitive companion.",
                observed=[],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move=None,
                memory_candidates=[],
                source_refs=[],
            ),
        )

    class MockProvider:
        name = "openai"
        async def complete_private_talk(self, request, event_sink=None):
            return await mock_dialogue_provider(request, event_sink=event_sink)

    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: MockProvider())

    events = []
    async def event_sink(event_type, payload):
        events.append((event_type, payload))

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        result = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Hello NUR, how are you today?",
            event_sink=event_sink,
        )

        assert "cognitive companion" in result.output.direct_response
        event_types = [e[0] for e in events]
        assert "talk.scope.resolved" in event_types
        assert "talk.capability.resolved" in event_types
        assert "talk.accepted" in event_types
        assert "talk.validated" in event_types

        # Verify model run recorded
        model_run = (
            await db.execute(select(ModelRun).where(ModelRun.owner_user_id == owner_user_id))
        ).scalars().first()
        assert model_run is not None
        assert model_run.status == "COMPLETED"


@pytest.mark.asyncio
async def test_capability_loop_contextual_answer_resolution(client, super_engine, monkeypatch):
    """Specific explanation query routes to contextual_answer capability."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async def mock_dialogue_provider(request, event_sink=None):
        return AIProviderResult(
            provider="openai",
            model="gpt-5.4-mini",
            available=True,
            output=NURTalkOutput(
                direct_response="The architecture uses a 22-step cognitive loop.",
                observed=[],
                inferred=[],
                hypotheses=[],
                uncertainty=[],
                next_move=None,
                memory_candidates=[],
                source_refs=[],
            ),
        )

    class MockProvider:
        name = "openai"
        async def complete_private_talk(self, request, event_sink=None):
            return await mock_dialogue_provider(request, event_sink=event_sink)

    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: MockProvider())

    events = []
    async def event_sink(event_type, payload):
        events.append((event_type, payload))

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        result = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="explain how this architecture works",
            event_sink=event_sink,
        )

        assert "22-step cognitive loop" in result.output.direct_response
        event_types = [e[0] for e in events]
        assert "talk.scope.resolved" in event_types
        assert "talk.capability.resolved" in event_types

        cap_events = [p for e, p in events if e == "talk.capability.resolved"]
        assert len(cap_events) == 1
        assert cap_events[0]["capability_id"] == "capability:contextual_answer"
        assert cap_events[0]["confidence_score"] >= 0.82

        # Model run should have capability_id recorded in metadata
        model_run = (
            await db.execute(select(ModelRun).where(ModelRun.owner_user_id == owner_user_id))
        ).scalars().first()
        assert model_run is not None
        assert model_run.status == "COMPLETED"
        assert model_run.run_metadata.get("capability_id") == "capability:contextual_answer"


@pytest.mark.asyncio
async def test_capability_loop_workflow_proposal_submission(client, super_engine):
    """Plan intent routes to WORKFLOW_PROPOSAL and creates BLOCKED_ON_APPROVAL workflow in Agency."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        # Policy allowing create_draft_plan under R1
        db.add(AgentPolicy(
            owner_user_id=owner_user_id,
            initiative_level="SUGGEST",
            max_risk_class="R1_PRIVATE_DRAFT",
            permitted_tools=["create_draft_plan"],
            auto_run_tools=[],
        ))
        await db.commit()

    events = []
    async def event_sink(event_type, payload):
        events.append((event_type, payload))

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        result = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Let's draft a plan to refactor the agentic core",
            event_sink=event_sink,
        )

        assert "drafted a plan proposal" in result.output.direct_response
        event_types = [e[0] for e in events]
        assert "workflow.proposed" in event_types

        # Verify AgentWorkflow and AgentApproval in DB
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 1
        assert workflows[0].state == "BLOCKED_ON_APPROVAL"

        approvals = (
            await db.execute(select(AgentApproval).where(AgentApproval.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(approvals) == 1
        assert approvals[0].decision == "PENDING"
