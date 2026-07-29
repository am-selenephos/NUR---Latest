"""Committed outbox intent -> dispatcher -> worker task, across sessions.

The runtime/database test calls run_step for the child directly in the same
session. That proves orchestration, not transport. Here the parent's transaction
commits, a *new* session sees the intent, the dispatcher claims and publishes it,
and the child executes through the real worker entry function in its own session.
"""

import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import dispatcher, handlers
from app.agentic.enums import InitiativeLevel, RiskClass
from app.agentic.observability import new_trace
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user
from app.workers import agentic_tasks

TOOL = "get_timeline"


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_read_only_handlers()


@pytest.fixture()
async def owner(client) -> UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201
    return UUID(response.json()["id"])


@pytest.fixture()
def session_for(app_engine, owner):
    """A factory for independent sessions, each with the owner's RLS context."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)

    def make():
        class Scoped:
            async def __aenter__(self):
                self.db = maker()
                await self.db.__aenter__()
                await self.db.execute(
                    text("SELECT set_config('app.current_user_id', :o, false)"),
                    {"o": str(owner)},
                )
                return self.db

            async def __aexit__(self, *exc):
                await self.db.__aexit__(*exc)

        return Scoped()

    return make


async def _seed_two_steps(db, owner: UUID):
    db.add(
        AgentPolicy(
            owner_user_id=owner,
            initiative_level=InitiativeLevel.INTERNAL.value,
            max_risk_class=RiskClass.R2_DURABLE_PRIVATE.value,
            permitted_tools=[TOOL],
            auto_run_tools=[TOOL],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="TEST", title="transport", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    parent = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a", state="QUEUED",
        role="operator", tool_key=TOOL, tool_version="1", risk_class="R0_READ_ONLY",
        input_refs={"limit": 3}, depends_on=[],
    )
    child = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=2, key="b", state="BLOCKED",
        role="operator", tool_key=TOOL, tool_version="1", risk_class="R0_READ_ONLY",
        input_refs={"limit": 3}, depends_on=["a"],
    )
    db.add_all([parent, child])
    await db.flush()
    return workflow, parent, child


@pytest.mark.asyncio
async def test_committed_intent_is_dispatched_and_the_child_runs(session_for, owner):
    async with session_for() as db:
        workflow, parent, child = await _seed_two_steps(db, owner)
        await run_step(db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1")
        await db.commit()
        workflow_id, parent_id, child_id = workflow.id, parent.id, child.id

    # A genuinely new session: nothing is carried over in identity map or txn.
    async with session_for() as fresh:
        row = (
            await fresh.execute(
                text(
                    "SELECT state, next_attempt_at <= now() AS due FROM agent_dispatch_outbox "
                    "WHERE step_id = :s"
                ),
                {"s": child_id},
            )
        ).mappings().one()
        assert row["state"] == "RETRYABLE"
        assert row["due"] is True
        assert (
            await fresh.execute(text("SELECT state FROM agent_steps WHERE id = :s"),
                                {"s": child_id})
        ).scalar_one() == "QUEUED"

    published: list[tuple] = []
    async with session_for() as dispatch_db:
        result = await dispatcher.dispatch_once(
            dispatch_db,
            dispatcher_id="d1",
            publish=lambda *args: published.append(args),
        )
        assert result["claimed"] == 1, result
        assert len(result["sent"]) == 1, result

    assert len(published) == 1
    step_arg, owner_arg, workflow_arg, _trace = published[0]
    assert UUID(step_arg) == child_id
    assert UUID(owner_arg) == owner
    assert UUID(workflow_arg) == workflow_id

    async with session_for() as check:
        assert (
            await check.execute(
                text("SELECT state FROM agent_dispatch_outbox WHERE step_id = :s"),
                {"s": child_id},
            )
        ).scalar_one() == "SENT"

    # The real worker coroutine, in its own session.
    outcome = await agentic_tasks._execute_step(
        str(child_id), str(owner), str(workflow_id), None
    )
    assert outcome["executed"] is True, outcome
    assert outcome["step_state"] == "SUCCEEDED", outcome
    assert outcome["workflow_state"] == "SUCCEEDED", outcome

    async with session_for() as final:
        calls = (
            await final.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": child_id},
            )
        ).scalar()
        assert calls == 1


@pytest.mark.asyncio
async def test_duplicate_broker_delivery_produces_one_effect(session_for, owner):
    async with session_for() as db:
        workflow, parent, child = await _seed_two_steps(db, owner)
        await run_step(db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1")
        await db.commit()
        workflow_id, child_id = workflow.id, child.id

    first = await agentic_tasks._execute_step(
        str(child_id), str(owner), str(workflow_id), None
    )
    second = await agentic_tasks._execute_step(
        str(child_id), str(owner), str(workflow_id), None
    )
    assert first["executed"] is True
    assert second["executed"] is False, second

    async with session_for() as check:
        calls = (
            await check.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": child_id},
            )
        ).scalar()
        assert calls == 1, f"handler ran {calls} times"


@pytest.mark.asyncio
async def test_broker_failure_leaves_a_recoverable_row(session_for, owner):
    async with session_for() as db:
        workflow, parent, child = await _seed_two_steps(db, owner)
        await run_step(db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1")
        await db.commit()
        child_id = child.id

    def exploding(*_args):
        raise ConnectionError("broker unavailable")

    async with session_for() as dispatch_db:
        result = await dispatcher.dispatch_once(
            dispatch_db, dispatcher_id="d1", publish=exploding
        )
        assert result["claimed"] == 1
        assert len(result["failed"]) == 1

    async with session_for() as check:
        row = (
            await check.execute(
                text(
                    "SELECT state, attempts, last_error, next_attempt_at > now() AS backing_off "
                    "FROM agent_dispatch_outbox WHERE step_id = :s"
                ),
                {"s": child_id},
            )
        ).mappings().one()
        assert row["state"] == "RETRYABLE", "a failed publish must remain recoverable"
        assert row["attempts"] == 1
        assert "ConnectionError" in row["last_error"]
        assert row["backing_off"] is True


@pytest.mark.asyncio
async def test_an_expired_lease_is_reclaimed_by_another_dispatcher(session_for, owner):
    """A dispatcher that dies mid-publish must not strand the intent."""
    async with session_for() as db:
        workflow, parent, child = await _seed_two_steps(db, owner)
        await run_step(db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1")
        await db.commit()
        child_id = child.id

    async with session_for() as dead:
        await dead.execute(
            text(
                "UPDATE agent_dispatch_outbox SET state = 'CLAIMED', claimed_by = 'dead', "
                "lease_expires_at = now() - interval '1 minute' WHERE step_id = :s"
            ),
            {"s": child_id},
        )
        await dead.commit()

    published: list[tuple] = []
    async with session_for() as rescuer:
        result = await dispatcher.dispatch_once(
            rescuer, dispatcher_id="d2", publish=lambda *a: published.append(a)
        )
        assert result["claimed"] == 1, "an expired lease must be reclaimable"
        assert len(result["sent"]) == 1

    assert len(published) == 1
    async with session_for() as check:
        row = (
            await check.execute(
                text(
                    "SELECT state, claimed_by FROM agent_dispatch_outbox WHERE step_id = :s"
                ),
                {"s": child_id},
            )
        ).mappings().one()
        assert row["state"] == "SENT"
        assert row["claimed_by"] == "d2"


@pytest.mark.asyncio
async def test_a_sent_row_is_not_republished(session_for, owner):
    async with session_for() as db:
        workflow, parent, child = await _seed_two_steps(db, owner)
        await run_step(db, owner_user_id=owner, step_id=parent.id, trace=new_trace(), worker="w1")
        await db.commit()

    async with session_for() as first:
        await dispatcher.dispatch_once(first, dispatcher_id="d1", publish=lambda *a: None)

    async with session_for() as second:
        again = await dispatcher.dispatch_once(
            second, dispatcher_id="d1", publish=lambda *a: None
        )
        assert again["claimed"] == 0, "SENT rows must not be picked up again"
