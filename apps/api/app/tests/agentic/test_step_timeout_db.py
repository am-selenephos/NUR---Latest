"""A handler that hangs must fail explicitly, not hold a lease forever.

There is deliberately no heartbeat in this design, so the guarantee that no
RUNNING row is immortal rests entirely on a hard ceiling strictly below the
lease: a handler cannot outlive its lease, so recovery can never reclaim a step
from a worker that is still alive, and a hung handler becomes a FAILED step that
retry can pick up rather than a lease nobody will ever release.

The ceiling is exercised for real here — a handler that sleeps past it, bound to
a declared tool, then unbound again.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers, registry
from app.agentic.observability import new_trace
from app.agentic.orchestrator import DEFAULT_LEASE_SECONDS
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
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


@pytest.fixture()
def hanging_handler():
    """Bind a handler that never returns in time, then restore the real one.

    `registry.bind` is a process-global mutation with no reset, so the restore is
    not optional politeness — leaving a sleeping handler bound would make every
    later test in the process hang.
    """
    async def never_finishes(db, owner_user_id, **kwargs):
        await asyncio.sleep(30)
        return {"count": 0}

    registry.bind(TOOL, never_finishes)
    yield
    handlers.bind_all_handlers()


@pytest.mark.asyncio
async def test_a_hung_handler_fails_explicitly_within_its_ceiling(
    scoped, owner, hanging_handler
):
    """The step's own `timeout_seconds` bounds it, the failure is recorded as
    STEP_TIMEOUT, and the step lands in FAILED — which the state machine allows
    to be re-queued."""
    scoped.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL], auto_run_tools=[TOOL],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    scoped.add(workflow)
    await scoped.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
        timeout_seconds=1,
    )
    scoped.add(step)
    await scoped.flush()
    await scoped.commit()

    outcome = await asyncio.wait_for(
        run_step(
            scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
        ),
        # Generously above the step's 1s ceiling: if the ceiling did not fire this
        # raises here instead, which is still a failure rather than a hang.
        timeout=20,
    )
    await scoped.commit()

    assert outcome["executed"] is False, outcome
    assert outcome["step_state"] == "FAILED", outcome
    assert "timeout" in outcome["reason"].lower(), outcome

    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    row = (
        await scoped.execute(
            text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step.id}
        )
    ).scalar_one()
    assert row == "FAILED", "a hung handler left the step RUNNING forever"

    events = (
        await scoped.execute(
            text(
                "SELECT event_type FROM agent_run_events WHERE step_id = :s "
                "ORDER BY sequence"
            ),
            {"s": step.id},
        )
    ).scalars().all()
    assert "STEP_TIMEOUT" in events, events

    # Nothing was recorded as having succeeded: the work did not happen.
    succeeded = (
        await scoped.execute(
            text(
                "SELECT count(*) FROM agent_tool_calls "
                "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
            ),
            {"s": step.id},
        )
    ).scalar_one()
    assert succeeded == 0


def test_the_ceiling_is_always_below_the_lease():
    """The invariant the whole no-heartbeat design rests on. If the configured
    ceiling ever exceeds the lease, a live worker can be reclaimed mid-handler and
    two workers hold one step."""
    from app.core.config import get_settings

    assert get_settings().agentic_step_timeout_seconds < DEFAULT_LEASE_SECONDS


@pytest.mark.asyncio
async def test_a_failed_step_can_be_requeued(scoped, owner):
    """A timeout must be recoverable, not terminal-in-practice."""
    from app.agentic.enums import STEP_TRANSITIONS, StepState

    assert StepState.QUEUED in STEP_TRANSITIONS[StepState.FAILED]
