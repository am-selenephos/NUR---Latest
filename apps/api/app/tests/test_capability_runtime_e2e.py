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
from unittest.mock import patch
import uuid
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.orchestrator import argument_digest
from app.cognition.intelligence_kernel import TalkProviderFailure
from app.core.config import get_settings
from app.db.rls import set_user_context
from app.mind.capabilities.dispatcher import WorkerDispatcher
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
        assert model_run.run_metadata["capability_version"] == "1"
        assert model_run.run_metadata["capability_resolution_source"] == "DETERMINISTIC_RULE"
        assert model_run.run_metadata["capability_confidence"] >= 0.82
        assert model_run.run_metadata["capability_resolution_reason"]
        assert model_run.response_metadata["available"] is False
        assert "deterministic Mind capability worker" in model_run.response_metadata["reason"]

        # 5. Verify persisted AgentWorkflow and AgentStep
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 1
        wf = workflows[0]
        assert wf.state == "PLAN_READY"
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
async def test_authenticated_explicit_capability_is_a_preview_without_save_intent(
    client,
    super_engine,
):
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])
    events = []

    async def event_sink(event_type, payload):
        events.append((event_type, payload))

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        result = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Explain the tradeoffs. Do not save or create anything.",
            requested_capability_id="capability:plan_from_conversation",
            event_sink=event_sink,
        )

        resolved = next(payload for name, payload in events if name == "talk.capability.resolved")
        assert resolved["capability_id"] == "capability:plan_from_conversation"
        assert resolved["resolution_source"] == "EXPLICIT_AUTHENTICATED"
        assert "Plan Preview" in result.output.direct_response
        assert (
            await db.execute(
                select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id)
            )
        ).scalars().all() == []


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
        refusal_event = next(e for e in events if e[0] == "workflow.refused")
        assert refusal_event[1]["reason_codes"] == ["POLICY_DENIED"]
        assert refusal_event[1]["retryable"] is False
        assert "task_id" in refusal_event[1]
        assert "errors" not in refusal_event[1]
        assert "exception" not in refusal_event[1]
        assert "Agency policy refused compilation" in result.output.direct_response
        assert "create_draft_plan" not in result.output.direct_response  # Internal tool name not leaked in refusal

        # 3. Verify NO workflow created in DB
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 0


@pytest.mark.asyncio
async def test_capability_runtime_e2e_full_approval_and_handler_execution(client, super_engine):
    """Prove full end-to-end lifecycle: Talk -> Proposal -> Decision -> Execution -> Plan/PlanStep rows -> Idempotency."""
    from app.agentic.handlers import bind_all_handlers
    bind_all_handlers()

    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    # 1. Setup policy permitting create_draft_plan (requires approval)
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

    # 2. Talk: "Let's draft a plan to deploy kernel\n- Run migrations\n- Verify tests"
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        response_event = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Let's draft a plan to deploy kernel\n- Run migrations\n- Verify tests",
            event_sink=event_sink,
        )
        assert response_event.response_event_id is not None

        # 3. CapabilityResolver selects plan_from_conversation
        event_dict = {e[0]: e[1] for e in events}
        assert event_dict["talk.capability.resolved"]["capability_id"] == "capability:plan_from_conversation"
        assert event_dict["workflow.proposed"]["requires_approval"] is True

        # 4. Agency compiler accepts, AgentWorkflow and AgentStep persisted
        workflows = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(workflows) == 1
        wf = workflows[0]
        assert wf.state == "PLAN_READY"

        steps = (
            await db.execute(select(AgentStep).where(AgentStep.workflow_id == wf.id))
        ).scalars().all()
        assert len(steps) == 1
        step = steps[0]
        assert step.tool_key == "create_draft_plan"
        assert step.state == "WAITING_APPROVAL"

        step_id = step.id
        wf_id = wf.id
        await db.commit()

    # 5. Read the exact approval binding before any dispatch is allowed.
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        appr = (
            await db.execute(
                select(AgentApproval).where(
                    AgentApproval.step_id == step_id,
                    AgentApproval.decision == "PENDING",
                )
            )
        ).scalar_one()

        seen_digest = appr.argument_digest
        seen_plan_version = int(appr.plan_version)
        seen_call_version = appr.call_version

        # 6. Call real decisions.decide(..., decision="APPROVE")
        from app.agentic.decisions import decide
        decision_res = await decide(
            db,
            owner_user_id=owner_user_id,
            approval_id=appr.id,
            decision="APPROVE",
            seen_digest=seen_digest,
            seen_plan_version=seen_plan_version,
            seen_call_version=seen_call_version,
            note="Approved by owner for kernel deployment",
        )
        await db.commit()

    # 7. Confirm step is now QUEUED and outbox intent exists
    assert decision_res.decision == "APPROVED"
    assert decision_res.step_state == "QUEUED"
    assert decision_res.outbox_intent_id is not None

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        outbox_row = (
            await db.execute(
                text("SELECT id, state, dispatch_key FROM agent_dispatch_outbox WHERE id = :id"),
                {"id": decision_res.outbox_intent_id},
            )
        ).mappings().first()
        assert outbox_row is not None

        # 8. The worker executes only after the owner-bound consent is durable.
        from app.agentic.observability import new_trace
        from app.agentic.runtime import run_step

        trace = new_trace()
        outcome2 = await run_step(
            db,
            owner_user_id=owner_user_id,
            step_id=step_id,
            worker="production-test-worker",
            trace=trace,
        )
        await db.commit()

    assert outcome2["executed"] is True
    assert outcome2["step_state"] == "SUCCEEDED"

    # 11. Verify Plan and PlanStep rows exist in DB with truthful content
    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        from app.models.cognition import Plan, PlanStep
        plans = (
            await db.execute(select(Plan).where(Plan.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(plans) == 1
        plan = plans[0]
        assert plan.title == "Deploy kernel"
        assert plan.status == "DRAFT"

        plan_steps = (
            await db.execute(
                select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.position.asc())
            )
        ).scalars().all()
        assert len(plan_steps) == 2
        assert plan_steps[0].title == "Run migrations"
        assert plan_steps[1].title == "Verify tests"

        # 12. Verify AgentStep SUCCEEDED
        reloaded_step = (
            await db.execute(select(AgentStep).where(AgentStep.id == step_id))
        ).scalar_one()
        assert reloaded_step.state == "SUCCEEDED"

        # 13. Verify workflow reaches correct aggregate state
        reloaded_wf = (
            await db.execute(select(AgentWorkflow).where(AgentWorkflow.id == wf_id))
        ).scalar_one()
        assert reloaded_wf.state == "SUCCEEDED"

        # 14. Verify Agency event ledger contains approval and execution events
        ledger_events = (
            await db.execute(
                text("SELECT event_type FROM agent_run_events WHERE workflow_id = :wf ORDER BY created_at ASC"),
                {"wf": wf_id},
            )
        ).scalars().all()
        assert "STEP_AWAITING_APPROVAL" in ledger_events
        assert "APPROVAL_APPROVED" in ledger_events
        assert "STEP_EXECUTED" in ledger_events
        assert "STEP_VERIFIED" in ledger_events

        # 15. Verify no second Plan is created on retry/idempotent delivery
        retry_outcome = await run_step(
            db,
            owner_user_id=owner_user_id,
            step_id=step_id,
            worker="production-test-retry-worker",
            trace=trace,
        )
        assert retry_outcome["executed"] is False

        plans_after_retry = (
            await db.execute(select(Plan).where(Plan.owner_user_id == owner_user_id))
        ).scalars().all()
        assert len(plans_after_retry) == 1


@pytest.mark.asyncio
async def test_capability_runtime_deterministic_provenance_and_configured_unused_provider(client, super_engine, monkeypatch):
    """Verify provider truth: when provider is configured, provider_available is True, but provider_invoked is False and model_used is None."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    # Simulate provider being configured
    s = get_settings()
    monkeypatch.setattr(s, "ai_provider", "mock")
    monkeypatch.setattr(s, "openai_model", "gpt-4o")

    class MockProvider:
        name = "mock"

    monkeypatch.setattr("app.cognition.intelligence_kernel.get_ai_provider", lambda: MockProvider())

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

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)
        result = await run_mind_cognitive_loop(
            db,
            owner_user_id=owner_user_id,
            user_line="Let's draft a plan to deploy the kernel\n- Step 1\n- Step 2",
        )
        assert "drafted a plan proposal" in result.output.direct_response

        model_run = (
            await db.execute(select(ModelRun).where(ModelRun.owner_user_id == owner_user_id))
        ).scalars().first()
        assert model_run is not None
        assert model_run.status == "COMPLETED"
        assert model_run.provider == "DETERMINISTIC_WORKER"
        assert model_run.model is None
        assert model_run.run_metadata["provider_configured"] is True
        assert model_run.run_metadata["provider_available"] is True
        assert model_run.run_metadata["provider_invoked"] is False
        assert model_run.run_metadata["model_used"] is None
        assert model_run.run_metadata["provider_model_used"] is None
        assert model_run.run_metadata["execution_provenance"] == "DETERMINISTIC_WORKER"
        assert model_run.response_metadata["available"] is True


@pytest.mark.asyncio
async def test_capability_runtime_deterministic_worker_failure_is_not_talk_provider_failure(client, super_engine):
    """Verify deterministic worker exception does not overwrite provider to ai_provider and does not raise TalkProviderFailure."""
    res, _, _ = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    events = []
    async def event_sink(event_type, payload):
        events.append((event_type, payload))

    async def faulty_dispatch(*args, **kwargs):
        raise ValueError("Deterministic worker internal validation crash")

    with patch.object(WorkerDispatcher, "dispatch", side_effect=faulty_dispatch):
        async with AsyncSession(super_engine) as db:
            await set_user_context(db, owner_user_id)
            with pytest.raises(ValueError) as exc_info:
                await run_mind_cognitive_loop(
                    db,
                    owner_user_id=owner_user_id,
                    user_line="Let's draft a plan to deploy the kernel\n- Step 1",
                    event_sink=event_sink,
                )
            assert not isinstance(exc_info.value, TalkProviderFailure)
            assert "Deterministic worker internal validation crash" in str(exc_info.value)

            model_run = (
                await db.execute(select(ModelRun).where(ModelRun.owner_user_id == owner_user_id))
            ).scalars().first()
            assert model_run is not None
            assert model_run.status == "ERROR"
            assert model_run.provider == "DETERMINISTIC_WORKER"
            assert model_run.model is None
            assert model_run.run_metadata["provider_invoked"] is False
            assert model_run.run_metadata["execution_provenance"] == "DETERMINISTIC_WORKER"
            assert model_run.run_metadata["model_used"] is None
            assert model_run.run_metadata["error_category"] == "worker_error"

            event_types = [e[0] for e in events]
            assert "talk.failed" in event_types
