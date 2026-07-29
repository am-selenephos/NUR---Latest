"""ORM insert-and-reload against PostgreSQL as the constrained app role.

Metadata comparison cannot prove a mapper issues valid SQL; only running it can.
AgentToolCall mapped two columns its table lacks, and every SELECT through that
mapper would have raised UndefinedColumn while every metadata assertion passed.

These use the harness the suite already has: `register_user` creates the owner
through the real registration endpoint, and `app_engine` connects as nur_app so
forced RLS is in effect. A skip here is a failure — the database is an autouse
requirement of this suite.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic.policy import Decision, evaluate
from app.agentic.policy_store import load_policy
from app.agentic.registry import contract
from app.models.agentic import (
    AgentApproval,
    AgentDispatchOutbox,
    AgentPolicy,
    AgentStep,
    AgentToolCall,
    AgentWorkflow,
)
from app.tests.conftest import register_user


@pytest.fixture()
async def owner(client) -> UUID:
    response, _email, _password = await register_user(client)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


@pytest.fixture()
async def scoped(app_engine, owner):
    """A session as nur_app with the owner's RLS context set."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        yield db


async def _workflow(db, owner: UUID, *, plan_version: int = 1) -> AgentWorkflow:
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="TEST", title="round trip",
        objective="prove the mapper", state="RUNNING", plan_version=plan_version,
    )
    db.add(workflow)
    await db.flush()
    return workflow


@pytest.mark.asyncio
async def test_agent_policy_roundtrip_and_decisions(scoped, owner):
    scoped.add(
        AgentPolicy(
            owner_user_id=owner,
            initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=["get_timeline", "create_draft_plan"],
            auto_run_tools=["get_timeline"],
        )
    )
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    reloaded = (
        await scoped.execute(select(AgentPolicy).where(AgentPolicy.owner_user_id == owner))
    ).scalar_one()
    assert reloaded.permitted_tools == ["get_timeline", "create_draft_plan"]
    assert reloaded.auto_run_tools == ["get_timeline"]

    policy = await load_policy(scoped, owner_user_id=owner)
    assert policy.permitted_tools == frozenset({"get_timeline", "create_draft_plan"})
    assert policy.auto_run_tools == frozenset({"get_timeline"})
    assert policy.granted_capabilities == frozenset({"read_timeline", "draft_plans"})

    assert evaluate(contract("get_timeline"), policy).decision is Decision.ALLOW
    assert evaluate(contract("create_draft_plan"), policy).decision is Decision.REQUIRE_APPROVAL
    assert evaluate(contract("get_insight"), policy).decision is Decision.DENY


@pytest.mark.asyncio
async def test_workflow_and_step_roundtrip(scoped, owner):
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator", tool_key="get_timeline",
        tool_version="1", risk_class="R0_READ_ONLY", input_refs={"limit": 5},
    )
    scoped.add(step)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (await scoped.execute(select(AgentStep).where(AgentStep.id == step.id))).scalar_one()
    assert back.key == "s1"
    assert back.input_refs == {"limit": 5}
    assert back.workflow_id == workflow.id


@pytest.mark.asyncio
async def test_agent_approval_roundtrip_with_call_version(scoped, owner):
    workflow = await _workflow(scoped, owner, plan_version=2)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="WAITING_APPROVAL", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    approval = AgentApproval(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        tool_key="activate_plan", tool_version="1",
        argument_digest="sha256:" + "a" * 64,
        rationale="test", risk_class="R2_DURABLE_PRIVATE", decision="PENDING",
        plan_version=workflow.plan_version,
        call_version="cv:" + "b" * 64,
    )
    scoped.add(approval)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (
        await scoped.execute(select(AgentApproval).where(AgentApproval.id == approval.id))
    ).scalar_one()
    assert back.plan_version == 2
    assert back.call_version == "cv:" + "b" * 64
    assert back.decision == "PENDING"


@pytest.mark.asyncio
async def test_agent_tool_call_roundtrip(scoped, owner):
    """The exact operation the corrupted mapper would have failed."""
    workflow = await _workflow(scoped, owner)
    call = AgentToolCall(
        owner_user_id=owner, workflow_id=workflow.id,
        tool_key="get_timeline", tool_version="1", risk_class="R0_READ_ONLY",
        argument_digest="sha256:" + "0" * 64,
        redacted_arguments={"limit": 5}, outcome="SUCCEEDED", duration_ms=12,
    )
    scoped.add(call)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (
        await scoped.execute(select(AgentToolCall).where(AgentToolCall.id == call.id))
    ).scalar_one()
    assert back.tool_key == "get_timeline"
    assert back.outcome == "SUCCEEDED"
    assert back.redacted_arguments == {"limit": 5}
    assert not hasattr(back, "call_version")


@pytest.mark.asyncio
async def test_outbox_roundtrip_with_lease_state(scoped, owner):
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    row = AgentDispatchOutbox(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        dispatch_key=f"{step.id}:1", state="CLAIMED", attempts=1,
        claimed_by="worker-a", traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01",
    )
    scoped.add(row)
    await scoped.commit()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    back = (
        await scoped.execute(
            select(AgentDispatchOutbox).where(AgentDispatchOutbox.id == row.id)
        )
    ).scalar_one()
    assert back.state == "CLAIMED"
    assert back.claimed_by == "worker-a"
    assert back.attempts == 1
    assert back.next_attempt_at is not None


@pytest.mark.asyncio
async def test_cross_owner_rows_are_invisible_under_forced_rls(scoped, owner, app_engine):
    """Forced RLS must hide another owner's rows from the app role."""
    workflow = await _workflow(scoped, owner)
    await scoped.commit()

    stranger = uuid4()
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as other:
        await other.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        found = (
            await other.execute(select(AgentWorkflow).where(AgentWorkflow.id == workflow.id))
        ).scalar_one_or_none()
        assert found is None, "another owner could read this workflow"

        # And cannot mutate it.
        result = await other.execute(
            text("UPDATE agent_workflows SET title = 'hijacked' WHERE id = :w"),
            {"w": workflow.id},
        )
        assert result.rowcount == 0, "another owner could update this workflow"


@pytest.mark.asyncio
async def test_outbox_state_check_accepts_exactly_three_values(scoped, owner):
    """Behavioural proof of the CHECK, not a string search in its definition."""
    workflow = await _workflow(scoped, owner)
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    scoped.add(step)
    await scoped.flush()

    for index, state in enumerate(("RETRYABLE", "CLAIMED", "SENT")):
        await scoped.execute(
            text(
                "INSERT INTO agent_dispatch_outbox "
                "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
                "VALUES (:o, :w, :s, :k, :st)"
            ),
            {"o": owner, "w": workflow.id, "s": step.id, "k": f"ok-{index}", "st": state},
        )

    for bad in ("PENDING", "retryable", "SENT ", "", "DONE"):
        with pytest.raises(Exception) as caught:
            await scoped.execute(
                text(
                    "INSERT INTO agent_dispatch_outbox "
                    "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
                    "VALUES (:o, :w, :s, :k, :st)"
                ),
                {"o": owner, "w": workflow.id, "s": step.id, "k": f"bad-{bad}", "st": bad},
            )
        assert "ck_agent_dispatch_state" in str(caught.value), bad
        await scoped.rollback()
        await scoped.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )


@pytest.mark.asyncio
async def test_pending_approval_requires_step_and_call_version(scoped, owner):
    workflow = await _workflow(scoped, owner)

    # PENDING with no step_id.
    with pytest.raises(Exception) as caught:
        await scoped.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, call_version) "
                "VALUES (:o, :w, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', 'PENDING', 'cv:x')"
            ),
            {"o": owner, "w": workflow.id, "d": "sha256:" + "a" * 64},
        )
    assert "ck_agent_approval_pending_bound" in str(caught.value)
    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )

    # plan_version below 1.
    with pytest.raises(Exception) as caught:
        await scoped.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, plan_version) "
                "VALUES (:o, :w, 't', '1', :d, 'r', 'R2_DURABLE_PRIVATE', 'REJECTED', 0)"
            ),
            {"o": owner, "w": workflow.id, "d": "sha256:" + "a" * 64},
        )
    assert "ck_agent_approval_plan_version" in str(caught.value)
