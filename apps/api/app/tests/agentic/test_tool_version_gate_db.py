"""A step compiled against a tool version the registry no longer serves must
never execute against the newer version silently — not even for an auto-run
tool, which would otherwise sail straight through the policy gate to ALLOW
without ever passing through approval's own version check.

Placed before the policy gate in `execute_step`, so it catches every path: the
auto-run case here, and the REQUIRE_APPROVAL case, which would otherwise only
be caught later and indirectly by `evaluate_resume` comparing against the
*approval's* recorded version rather than the step's own.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.observability import new_trace
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"
CURRENT_VERSION = "1"
STALE_VERSION = "0"


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


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_read_only_handlers()


async def _seed(db, owner, *, tool_version: str, auto_run: bool, key: str):
    db.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL],
            auto_run_tools=[TOOL] if auto_run else [],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key=key,
        state="QUEUED", role="operator", tool_key=TOOL, tool_version=tool_version,
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    db.add(step)
    await db.flush()
    return workflow, step


@pytest.mark.asyncio
async def test_stale_version_auto_run_step_never_executes(scoped, owner):
    """The interesting new case: auto-run would otherwise ALLOW unconditionally."""
    workflow, step = await _seed(
        scoped, owner, tool_version=STALE_VERSION, auto_run=True, key="a"
    )
    await scoped.commit()

    outcome = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await scoped.commit()

    assert outcome["executed"] is False, outcome
    assert outcome["step_state"] == "NEEDS_REVISION", outcome
    assert outcome["workflow_state"] == "NEEDS_REVISION", outcome

    tool_calls = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_tool_calls WHERE step_id = :s"), {"s": step.id}
        )
    ).scalar()
    assert tool_calls == 0, "the handler must never have been invoked"

    event = (
        await scoped.execute(
            text(
                "SELECT summary FROM agent_run_events "
                "WHERE step_id = :s AND event_type = 'TOOL_VERSION_CHANGED'"
            ),
            {"s": step.id},
        )
    ).mappings().one()
    assert STALE_VERSION in event["summary"]
    assert CURRENT_VERSION in event["summary"]

    step_row = (
        await scoped.execute(
            text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step.id}
        )
    ).scalar_one()
    assert step_row == "NEEDS_REVISION"


@pytest.mark.asyncio
async def test_stale_version_approval_gated_step_never_executes(scoped, owner):
    """Not just the auto-run path: a step that would otherwise pause for
    approval is caught first, before any approval bookkeeping happens."""
    workflow, step = await _seed(
        scoped, owner, tool_version=STALE_VERSION, auto_run=False, key="a"
    )
    await scoped.commit()

    outcome = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await scoped.commit()

    assert outcome["executed"] is False, outcome
    assert outcome["step_state"] == "NEEDS_REVISION", outcome

    approvals = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_approvals WHERE step_id = :s"), {"s": step.id}
        )
    ).scalar()
    assert approvals == 0, "no approval should ever have been minted for a stale-version step"


@pytest.mark.asyncio
async def test_freshly_compiled_current_version_step_executes(scoped, owner):
    """The contrast case: the gate only blocks drift, not the ordinary path."""
    workflow, step = await _seed(
        scoped, owner, tool_version=CURRENT_VERSION, auto_run=True, key="a"
    )
    await scoped.commit()

    outcome = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await scoped.commit()

    assert outcome["executed"] is True, outcome
    assert outcome["step_state"] == "SUCCEEDED", outcome

    tool_calls = (
        await scoped.execute(
            text(
                "SELECT count(*) FROM agent_tool_calls "
                "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
            ),
            {"s": step.id},
        )
    ).scalar()
    assert tool_calls == 1
