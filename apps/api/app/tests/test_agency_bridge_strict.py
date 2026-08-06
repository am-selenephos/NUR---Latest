"""Tests for hardened agency_bridge.py with strict tool validation and zero silent fallbacks."""
import ast
from pathlib import Path
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import WorkflowProposal, WorkflowStepProposal
from app.db.rls import set_user_context
from app.mind.agency_bridge import AgencyBridgeError, submit_workflow_proposal
from app.models.agentic import AgentPolicy, AgentStep, AgentApproval
from app.tests.conftest import register_user


def test_ast_agency_bridge_no_create_draft_plan_fallback():
    """Prove that 'create_draft_plan' is never used as a default/fallback expression in agency_bridge.py."""
    bridge_path = Path(__file__).resolve().parent.parent / "mind" / "agency_bridge.py"
    assert bridge_path.exists(), f"File not found: {bridge_path}"

    tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # Look for any BoolOp (e.g. x or "create_draft_plan") or default arg
        if isinstance(node, ast.BoolOp):
            for val in node.values:
                if isinstance(val, ast.Constant) and val.value == "create_draft_plan":
                    pytest.fail("Found 'create_draft_plan' fallback expression in agency_bridge.py AST!")
        elif isinstance(node, ast.Constant) and node.value == "create_draft_plan":
            pytest.fail("Found string literal 'create_draft_plan' in agency_bridge.py - no hardcoded fallbacks permitted!")


@pytest.mark.asyncio
async def test_agency_bridge_rejects_missing_tool_key(client: AsyncClient, super_engine):
    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        # Proposal with empty tool_key must raise AgencyBridgeError, NOT silently map to create_draft_plan
        proposal = WorkflowProposal(
            task_id=uuid.uuid4(),
            title="Invalid step proposal",
            rationale="Testing missing tool key",
            steps=[
                WorkflowStepProposal(
                    key="step_1",
                    title="Do something mysterious",
                    description="No tool specified",
                    tool_key="",  # Empty tool key
                    requires_approval=True,
                )
            ],
        )

        with pytest.raises(AgencyBridgeError) as exc_info:
            await submit_workflow_proposal(db, owner_user_id=owner_user_id, proposal=proposal)

        assert "missing required 'tool_key'" in str(exc_info.value)
        assert "Zero silent fallback" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agency_bridge_rejects_unknown_tool_via_compiler(client: AsyncClient, super_engine):
    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        # Step referencing unknown tool key must raise AgencyBridgeError
        proposal = WorkflowProposal(
            task_id=uuid.uuid4(),
            title="Unknown tool step",
            rationale="Testing unknown tool",
            steps=[
                WorkflowStepProposal(
                    key="step_1",
                    title="Unknown action",
                    description="Calls non-existent tool",
                    tool_key="non_existent_tool_12345",
                    arguments={"title": "test"},
                    requires_approval=True,
                )
            ],
        )

        with pytest.raises(AgencyBridgeError) as exc_info:
            await submit_workflow_proposal(db, owner_user_id=owner_user_id, proposal=proposal)

        assert "Unregistered Agency tool" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agency_bridge_rejects_invalid_arguments_schema(client: AsyncClient, super_engine):
    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        # Passing unknown field 'objective' must fail validation
        proposal = WorkflowProposal(
            task_id=uuid.uuid4(),
            title="Invalid args workflow",
            rationale="Testing invalid args",
            steps=[
                WorkflowStepProposal(
                    key="step_1",
                    title="Draft plan with invalid objective",
                    description="Calls create_draft_plan with extra field",
                    tool_key="create_draft_plan",
                    arguments={"title": "Plan", "objective": "Invalid field"},
                    requires_approval=True,
                )
            ],
        )

        with pytest.raises(AgencyBridgeError) as exc_info:
            await submit_workflow_proposal(db, owner_user_id=owner_user_id, proposal=proposal)

        assert "Argument validation failed" in str(exc_info.value)
        assert "unknown field 'objective'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agency_bridge_rejects_cyclic_dependencies(client: AsyncClient, super_engine):
    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        db.add(AgentPolicy(
            owner_user_id=owner_user_id,
            initiative_level="SUGGEST",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=["create_draft_plan"],
            auto_run_tools=[],
        ))
        await db.flush()

        # Step 1 depends on Step 2, and Step 2 depends on Step 1
        proposal = WorkflowProposal(
            task_id=uuid.uuid4(),
            title="Cyclic workflow",
            rationale="Testing cycle detection",
            steps=[
                WorkflowStepProposal(
                    key="step_1",
                    title="Step 1",
                    description="Depends on step 2",
                    tool_key="create_draft_plan",
                    arguments={"title": "Step 1", "steps": ["Task 1"]},
                    dependencies=["step_2"],
                    requires_approval=True,
                ),
                WorkflowStepProposal(
                    key="step_2",
                    title="Step 2",
                    description="Depends on step 1",
                    tool_key="create_draft_plan",
                    arguments={"title": "Step 2", "steps": ["Task 2"]},
                    dependencies=["step_1"],
                    requires_approval=True,
                ),
            ],
        )

        workflow, compile_res = await submit_workflow_proposal(
            db, owner_user_id=owner_user_id, proposal=proposal
        )

        assert compile_res.ok is False
        assert workflow is None
        assert any("CYCLIC" in err.code for err in compile_res.errors)


@pytest.mark.asyncio
async def test_agency_bridge_strict_arguments_and_approval(client: AsyncClient, super_engine):
    res, email, password = await register_user(client)
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
        await db.flush()

        proposal = WorkflowProposal(
            task_id=uuid.uuid4(),
            title="Valid strict workflow",
            rationale="Strict argument forwarding",
            steps=[
                WorkflowStepProposal(
                    key="step_1",
                    title="Draft custom plan",
                    description="Create a draft plan with specific title",
                    tool_key="create_draft_plan",
                    arguments={"title": "Q3 Engineering Roadmap", "steps": ["Ship Capability Runtime"]},
                    requires_approval=True,
                    estimated_cost_cents=2,
                )
            ],
            total_estimated_cost_cents=2,
        )

        workflow, compile_res = await submit_workflow_proposal(
            db, owner_user_id=owner_user_id, proposal=proposal
        )

        assert compile_res.ok is True
        assert workflow is not None
        assert workflow.state == "BLOCKED_ON_APPROVAL"
        assert workflow.budget_cents == 2

        from sqlalchemy import select
        stmt = select(AgentStep).where(AgentStep.workflow_id == workflow.id)
        db_steps = (await db.execute(stmt)).scalars().all()
        assert len(db_steps) == 1
        assert db_steps[0].tool_key == "create_draft_plan"
        assert db_steps[0].input_refs["title"] == "Q3 Engineering Roadmap"
        assert db_steps[0].input_refs["steps"] == ["Ship Capability Runtime"]

        stmt_app = select(AgentApproval).where(AgentApproval.workflow_id == workflow.id)
        db_approvals = (await db.execute(stmt_app)).scalars().all()
        assert len(db_approvals) == 1
        assert db_approvals[0].tool_key == "create_draft_plan"
        assert db_approvals[0].decision == "PENDING"
        assert db_approvals[0].argument_digest is not None
        assert db_approvals[0].redacted_arguments["title"] == "Q3 Engineering Roadmap"


@pytest.mark.asyncio
async def test_agency_step_dependency_state_persists_blocked(client: AsyncClient, super_engine):
    """Prove that when step B depends on step A (which is auto-run/no approval), B persists BLOCKED."""
    res, email, password = await register_user(client)
    owner_user_id = uuid.UUID(res.json()["id"])

    async with AsyncSession(super_engine) as db:
        await set_user_context(db, owner_user_id)

        # Policy allows create_draft_plan to auto-run (no approval)
        db.add(AgentPolicy(
            owner_user_id=owner_user_id,
            initiative_level="DELEGATED",
            max_risk_class="R1_PRIVATE_DRAFT",
            permitted_tools=["create_draft_plan"],
            auto_run_tools=["create_draft_plan"],
        ))
        await db.flush()

        # Step A is root (READY). Step B depends on A (BLOCKED on dependency).
        proposal = WorkflowProposal(
            task_id=uuid.uuid4(),
            title="Dependency chain workflow",
            rationale="Test dependency blocking",
            steps=[
                WorkflowStepProposal(
                    key="step_a",
                    title="Root step",
                    description="Creates initial plan",
                    tool_key="create_draft_plan",
                    arguments={"title": "Step A Plan", "steps": ["Task A"]},
                    requires_approval=False,
                ),
                WorkflowStepProposal(
                    key="step_b",
                    title="Dependent step",
                    description="Creates follow-up plan",
                    tool_key="create_draft_plan",
                    arguments={"title": "Step B Plan", "steps": ["Task B"]},
                    dependencies=["step_a"],
                    requires_approval=False,
                ),
            ],
        )

        workflow, compile_res = await submit_workflow_proposal(
            db, owner_user_id=owner_user_id, proposal=proposal
        )

        assert compile_res.ok is True
        assert workflow is not None

        from sqlalchemy import select
        stmt = select(AgentStep).where(AgentStep.workflow_id == workflow.id)
        db_steps = {s.key: s for s in (await db.execute(stmt)).scalars().all()}
        assert "step_a" in db_steps
        assert "step_b" in db_steps
        # Step A is root: READY
        assert db_steps["step_a"].state == "READY"
        # Step B depends on A: MUST persist BLOCKED by compiler authority
        assert db_steps["step_b"].state == "BLOCKED"


