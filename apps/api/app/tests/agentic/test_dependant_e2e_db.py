"""A two-step workflow executing end to end through real PostgreSQL.

This is the test the dependant pipeline could never have passed. `unlock_dependants`
promoted BLOCKED to READY, the worker published READY steps directly, and
`claim_step` only ever claims QUEUED — so every dependant message lost its claim
and the child never ran.

No mocked database seam: real registered owner, nur_app under forced RLS, the
real runtime entry point, and a real registered read-only handler.
"""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers, registry
from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.observability import new_trace
from app.agentic.policy import OwnerPolicy
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_read_only_handlers()


@pytest.fixture()
async def owner(client) -> UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


@pytest.fixture()
async def db(app_engine, owner):
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        # A policy that permits and auto-runs the read tool, so the loop is
        # exercised rather than parked on an approval.
        session.add(
            AgentPolicy(
                owner_user_id=owner,
                initiative_level=InitiativeLevel.INTERNAL.value,
                max_risk_class=RiskClass.R2_DURABLE_PRIVATE.value,
                permitted_tools=[TOOL],
                auto_run_tools=[TOOL],
            )
        )
        await session.commit()
        await session.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        yield session


async def _two_step_workflow(db, owner: UUID):
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="TEST", title="A then B",
        objective="prove the dependant pipeline", state="RUNNING",
    )
    db.add(workflow)
    await db.flush()

    parent = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    child = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=2, key="b",
        state="BLOCKED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=["a"],
    )
    db.add_all([parent, child])
    await db.flush()
    return workflow, parent, child


async def _state(db, step_id) -> str:
    return (
        await db.execute(text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step_id})
    ).scalar_one()


@pytest.mark.asyncio
async def test_two_step_workflow_runs_parent_then_dependant(db, owner):
    workflow, parent, child = await _two_step_workflow(db, owner)
    assert await _state(db, parent.id) == "QUEUED"
    assert await _state(db, child.id) == "BLOCKED"

    outcome = await run_step(
        db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1"
    )
    assert outcome["executed"] is True, outcome
    assert outcome["step_state"] == "SUCCEEDED", outcome

    # BLOCKED -> READY -> QUEUED, in one transaction with the dispatch intent.
    assert str(child.id) in outcome["unlocked"], outcome
    assert str(child.id) in outcome["queued"], outcome
    assert await _state(db, child.id) == "QUEUED"

    intents = (
        await db.execute(
            text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
            {"s": child.id},
        )
    ).scalar()
    assert intents == 1, "exactly one dispatch intent per step attempt"

    child_outcome = await run_step(
        db, owner_user_id=owner, step_id=child.id, trace=new_trace(), worker="w2"
    )
    assert child_outcome["executed"] is True, child_outcome
    assert child_outcome["step_state"] == "SUCCEEDED", child_outcome
    assert child_outcome["workflow_state"] == "SUCCEEDED", child_outcome


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_execute_the_child_twice(db, owner):
    workflow, parent, child = await _two_step_workflow(db, owner)
    await run_step(db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1")
    assert await _state(db, child.id) == "QUEUED"

    first = await run_step(
        db, owner_user_id=owner, step_id=child.id, trace=new_trace(), worker="w2"
    )
    assert first["executed"] is True

    # A redelivery of the same message: the step is no longer QUEUED, so the
    # claim is lost and nothing runs.
    second = await run_step(
        db, owner_user_id=owner, step_id=child.id, trace=new_trace(), worker="w3"
    )
    assert second["executed"] is False, second

    calls = (
        await db.execute(
            text("SELECT count(*) FROM agent_tool_calls WHERE step_id = :s AND outcome = 'SUCCEEDED'"),
            {"s": child.id},
        )
    ).scalar()
    assert calls == 1, f"child handler ran {calls} times"


@pytest.mark.asyncio
async def test_a_ready_step_cannot_be_claimed(db, owner):
    """The reason the old pipeline was dead, asserted directly."""
    workflow, parent, child = await _two_step_workflow(db, owner)
    await db.execute(
        text("UPDATE agent_steps SET state = 'READY' WHERE id = :s"), {"s": child.id}
    )
    outcome = await run_step(
        db, owner_user_id=owner, step_id=child.id, trace=new_trace(), worker="w9"
    )
    assert outcome["executed"] is False
    assert "not QUEUED" in outcome["reason"]


@pytest.mark.asyncio
async def test_a_dependant_stays_blocked_until_its_parent_succeeds(db, owner):
    """A parent that fails must not release its subtree."""
    workflow, parent, child = await _two_step_workflow(db, owner)
    await db.execute(
        text("UPDATE agent_steps SET tool_key = NULL WHERE id = :s"), {"s": parent.id}
    )
    outcome = await run_step(
        db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1"
    )
    assert outcome["executed"] is False
    assert await _state(db, child.id) == "BLOCKED"
    intents = (
        await db.execute(
            text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"),
            {"s": child.id},
        )
    ).scalar()
    assert intents == 0
