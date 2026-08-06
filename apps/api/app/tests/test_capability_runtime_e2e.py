"""Comprehensive End-to-End Tests for NUR Mind Capability Runtime (No Mocks).

Validates complete flow:
  1. Intent resolution -> Capability matching
  2. Context hydration
  3. Worker Dispatcher execution (deterministic & proposal)
  4. Agency Bridge validation against authoritative schemas
  5. Agency Compiler & DB persistence (AgentWorkflow, AgentStep, AgentApproval)
  6. ModelRun provenance and provider truth
  7. Preview vs Persist semantics
  8. Policy compile refusal handling & truthfulness
"""
import hashlib
import json
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.orchestrator import argument_digest
from app.db.rls import set_user_context
from app.mind.cognitive_loop import run_mind_cognitive_loop
from app.models import ModelRun
from app.models.agentic import AgentApproval, AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user


@pytest.mark.asyncio
async def test_capability_runtime_e2e_deterministic_plan_proposal(client, super_engine):
    """End-to-end execution of plan drafting through Capability Runtime without AI provider mocks."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    # 1. Setup policy permitting create_draft_plan
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
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

    # 2. Run cognitive loop with a plan drafting request
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        result = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Let's draft a plan to deploy the cognitive kernel\n- Run DB migrations\n- Verify tests",
            event_sink=event_sink,
        )

        # 3. Assert output and events
        assert "drafted a plan proposal" in result.output.direct_response
        assert "Deploy the cognitive kernel" in result.output.direct_response
        event_dict = {e[0]: e[1] for e in events}
        assert "talk.capability.resolved" in event_dict
        assert event_dict["talk.capability.resolved"]["capability_id"] == "capability:plan_from_conversation"
        assert "workflow.proposed" in event_dict
        assert event_dict["workflow.proposed"]["requires_approval"] is True

        # 4. Verify ModelRun record truthfulness
        model_run = (
            await db.execute(select(ModelRun).where(ModelRun.owner_user_id == owner_user_id))
        ).scalars().first()
        assert model_run is not None
        assert model_run.status == "COMPLETED"
        assert model_run.provider == "DETERMINISTIC_WORKER"
        assert model_run.model is None
        assert model_run.run_metadata["provider_invoked"] is False
        assert model_run.run_metadata["execution_provenance"] == "DETERMINISTIC_WORKER"
        assert model_run.run_metadata["capability_id"] == "capability:plan_from_conversation"
        assert model_run.response_metadata["available"] is False
        assert "deterministic Mind capability worker" in model_run.response_metadata["reason"]

        # 5. Verify persisted AgentWorkflow and AgentStep
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 1
        wf = workflows[0]
        assert wf.state == "BLOCKED_ON_APPROVAL"
        assert wf.title == "Plan: Deploy the cognitive kernel"

        steps = (
            await db.execute(select(AgentStep).where(AgentStep.workflow_id == wf.id))
        ).scalars().all()
        assert len(steps) == 1
        step = steps[0]
        assert step.tool_key == "create_draft_plan"
        assert step.tool_version == "1"
        assert step.input_refs["title"] == "Deploy the cognitive kernel"
        assert step.input_refs["steps"] == ["Run DB migrations", "Verify tests"]
        assert "objective" not in step.input_refs  # Ensure forbidden argument is not present

        # 6. Verify persisted AgentApproval
        approvals = (
            await db.execute(select(AgentApproval).where(AgentApproval.workflow_id == wf.id))
        ).scalars().all()
        assert len(approvals) == 1
        appr = approvals[0]
        assert appr.tool_key == "create_draft_plan"
        assert appr.decision == "PENDING"
        assert appr.redacted_arguments["title"] == "Deploy the cognitive kernel"
        assert appr.redacted_arguments["steps"] == ["Run DB migrations", "Verify tests"]

        # Verify argument_digest integrity
        expected_digest = argument_digest(appr.tool_key, appr.tool_version, appr.redacted_arguments)
        assert appr.argument_digest == expected_digest


@pytest.mark.asyncio
async def test_capability_runtime_e2e_preview_mode_no_persistence(client, super_engine):
    """Conversational plan inquiries produce previews without creating Agency workflows."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
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
            user_line="Show me a plan for the migration\n- Backup database\n- Run scripts",
            event_sink=event_sink,
        )

        assert "Plan Preview:" in result.output.direct_response
        assert "conversational preview" in result.output.direct_response
        event_types = [e[0] for e in events]
        assert "workflow.proposed" not in event_types

        # Verify NO AgentWorkflow was persisted
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 0


@pytest.mark.asyncio
async def test_capability_runtime_e2e_policy_compile_refusal(client, super_engine):
    """When policy refuses the tool, cognitive loop handles compile refusal truthfully."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    # 1. Setup policy that does NOT permit create_draft_plan
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        db.add(AgentPolicy(
            owner_user_id=owner_user_id,
            initiative_level="SUGGEST",
            max_risk_class="R0_READ_ONLY",  # R0 refuses R1 create_draft_plan
            permitted_tools=[],
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
            user_line="Let's draft a plan to refactor policy engine",
            event_sink=event_sink,
        )

        # 2. Check refusal event and truthful message
        event_types = [e[0] for e in events]
        assert "workflow.refused" in event_types
        assert "Agency policy refused compilation" in result.output.direct_response

        # 3. Verify NO workflow created in DB
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 0
