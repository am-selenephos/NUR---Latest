"""A tool call's approval_id must name an approval that actually authorised
*this* call — same owner, same workflow, same step — not merely a row that
exists somewhere in agent_approvals.

The single-column FK from 0035 only proves the referenced id exists. Writing
approval_id on every call site (runtime.py's `_record_tool_call`) is not the
same claim as this one: nothing before 0045 stopped a tool call from citing
another owner's approval, or one bound to a different workflow or step, as
long as the id happened to resolve.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.decisions import decide
from app.agentic.observability import new_trace
from app.agentic.runtime import run_step
from app.models.agentic import AgentApproval, AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"


@pytest.fixture()
async def owner(client) -> uuid.UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture()
async def scoped(app_engine, owner):
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        yield db


async def _add_step(db, owner: uuid.UUID, workflow, *, key: str, ordinal: int = 1):
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=ordinal, key=key,
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={},
    )
    db.add(step)
    await db.flush()
    return step


async def _seed(db, owner: uuid.UUID, *, key: str = "s1"):
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    step = await _add_step(db, owner, workflow, key=key)
    return workflow, step


async def _approval(db, owner: uuid.UUID, workflow, step, *, decision="APPROVED"):
    row = AgentApproval(
        owner_user_id=owner, workflow_id=workflow.id, step_id=step.id,
        tool_key=TOOL, tool_version="1", argument_digest="sha256:a",
        rationale="r", risk_class="R0_READ_ONLY", decision=decision,
        plan_version=1, call_version="cv:test",
    )
    db.add(row)
    await db.flush()
    return row


async def _tool_call_sql(db, *, owner, workflow, step, approval_id):
    await db.execute(
        text(
            "INSERT INTO agent_tool_calls (owner_user_id, workflow_id, step_id, tool_key, "
            "tool_version, risk_class, argument_digest, outcome, approval_id) "
            "VALUES (:o, :w, :s, 't', '1', 'R0_READ_ONLY', 'sha256:a', 'SUCCEEDED', :a)"
        ),
        {"o": owner, "w": workflow.id, "s": step.id, "a": approval_id},
    )


@pytest.mark.asyncio
async def test_a_correctly_bound_approval_is_accepted(scoped, owner):
    workflow, step = await _seed(scoped, owner)
    approval = await _approval(scoped, owner, workflow, step)
    await _tool_call_sql(scoped, owner=owner, workflow=workflow, step=step, approval_id=approval.id)
    kept = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_tool_calls WHERE approval_id = :a"),
            {"a": approval.id},
        )
    ).scalar()
    assert kept == 1


@pytest.mark.asyncio
async def test_a_null_approval_is_accepted_regardless(scoped, owner):
    """Auto-run and any path with no consent to cite must not be forced to
    reference something that doesn't exist."""
    workflow, step = await _seed(scoped, owner)
    await _tool_call_sql(scoped, owner=owner, workflow=workflow, step=step, approval_id=None)
    kept = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_tool_calls WHERE step_id = :s"),
            {"s": step.id},
        )
    ).scalar()
    assert kept == 1


@pytest.mark.asyncio
async def test_approval_cannot_bind_to_a_call_from_a_different_step(scoped, owner):
    """Same workflow, different step: the pre-existing approval-binding trigger
    (0039) already keeps an approval's own workflow_id/step_id consistent, so
    the case worth proving here is the composite FK catching a *tool call* that
    cites another step's approval within the same workflow."""
    workflow, step_a = await _seed(scoped, owner, key="a")
    step_b = await _add_step(scoped, owner, workflow, key="b", ordinal=2)
    approval_on_b = await _approval(scoped, owner, workflow, step_b)

    with pytest.raises(Exception) as caught:
        await _tool_call_sql(
            scoped, owner=owner, workflow=workflow, step=step_a, approval_id=approval_on_b.id
        )
    assert "fk_agent_tool_call_approval_binding" in str(caught.value) or "violates" in str(
        caught.value
    )


@pytest.mark.asyncio
async def test_approval_cannot_bind_to_a_call_from_a_different_workflow(scoped, owner):
    workflow_a, step_a = await _seed(scoped, owner, key="a")
    workflow_b, step_b = await _seed(scoped, owner, key="b")
    approval_on_b = await _approval(scoped, owner, workflow_b, step_b)

    with pytest.raises(Exception) as caught:
        # Same owner, same step id coincidence avoided by using step_a's own
        # workflow — the mismatch under test is workflow_id.
        await scoped.execute(
            text(
                "INSERT INTO agent_tool_calls (owner_user_id, workflow_id, step_id, tool_key, "
                "tool_version, risk_class, argument_digest, outcome, approval_id) "
                "VALUES (:o, :w, :s, 't', '1', 'R0_READ_ONLY', 'sha256:a', 'SUCCEEDED', :a)"
            ),
            {"o": owner, "w": workflow_a.id, "s": step_a.id, "a": approval_on_b.id},
        )
    assert "fk_agent_tool_call_approval_binding" in str(caught.value) or "violates" in str(
        caught.value
    )


@pytest.mark.asyncio
async def test_approval_cannot_bind_to_another_owners_call(
    scoped, owner, client, app_engine
):
    workflow, step = await _seed(scoped, owner)
    approval = await _approval(scoped, owner, workflow, step)
    await scoped.commit()

    other, _e, _p = await register_user(client, chosen_name="Bee")
    stranger = uuid.UUID(other.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        stranger_workflow, stranger_step = await _seed(db, stranger)
        with pytest.raises(Exception) as caught:
            await _tool_call_sql(
                db, owner=stranger, workflow=stranger_workflow, step=stranger_step,
                approval_id=approval.id,
            )
        assert "fk_agent_tool_call_approval_binding" in str(caught.value) or "violates" in str(
            caught.value
        )


@pytest.mark.asyncio
async def test_approve_then_execute_writes_a_correctly_bound_approval_id(
    client, app_engine
):
    """The real runtime, not a hand-written INSERT: approve a paused step
    through `decide()`, let the ordinary loop execute it, and check the
    resulting SUCCEEDED tool_call's approval_id names the approval that
    actually authorised it."""
    handlers.bind_read_only_handlers()
    response, _e, _p = await register_user(client)
    owner = uuid.UUID(response.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        db.add(
            AgentPolicy(
                owner_user_id=owner, initiative_level="INTERNAL",
                max_risk_class="R2_DURABLE_PRIVATE",
                permitted_tools=[TOOL], auto_run_tools=[],
            )
        )
        workflow = AgentWorkflow(
            owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
        )
        db.add(workflow)
        await db.flush()
        step = AgentStep(
            owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
            state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
            risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
        )
        db.add(step)
        await db.flush()
        step_id = step.id
        await db.commit()

        # First pass: pauses and mints a PENDING approval.
        outcome = await run_step(
            db, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w1"
        )
        await db.commit()
        assert outcome["step_state"] == "WAITING_APPROVAL", outcome

        approval_row = (
            await db.execute(
                text(
                    "SELECT id, argument_digest, plan_version, call_version "
                    "FROM agent_approvals WHERE step_id = :s AND decision = 'PENDING'"
                ),
                {"s": step_id},
            )
        ).mappings().one()

        result = await decide(
            db, owner_user_id=owner, approval_id=approval_row["id"], decision="APPROVE",
            seen_digest=approval_row["argument_digest"],
            seen_plan_version=approval_row["plan_version"],
            seen_call_version=approval_row["call_version"],
        )
        await db.commit()
        assert result.step_state == "QUEUED"

        outcome2 = await run_step(
            db, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w2"
        )
        await db.commit()
        assert outcome2["step_state"] == "SUCCEEDED", outcome2

        bound = (
            await db.execute(
                text(
                    "SELECT approval_id FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": step_id},
            )
        ).mappings().one()
        assert bound["approval_id"] == approval_row["id"]


@pytest.mark.asyncio
async def test_auto_run_tool_call_has_no_approval_id(client, app_engine):
    handlers.bind_read_only_handlers()
    response, _e, _p = await register_user(client)
    owner = uuid.UUID(response.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        db.add(
            AgentPolicy(
                owner_user_id=owner, initiative_level="INTERNAL",
                max_risk_class="R2_DURABLE_PRIVATE",
                permitted_tools=[TOOL], auto_run_tools=[TOOL],
            )
        )
        workflow = AgentWorkflow(
            owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
        )
        db.add(workflow)
        await db.flush()
        step = AgentStep(
            owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
            state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
            risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
        )
        db.add(step)
        await db.flush()
        step_id = step.id
        await db.commit()

        outcome = await run_step(
            db, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w1"
        )
        await db.commit()
        assert outcome["step_state"] == "SUCCEEDED", outcome

        bound = (
            await db.execute(
                text("SELECT approval_id FROM agent_tool_calls WHERE step_id = :s"),
                {"s": step_id},
            )
        ).mappings().one()
        assert bound["approval_id"] is None
