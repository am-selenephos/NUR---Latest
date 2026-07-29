"""One aggregate function, exercised across the full state matrix.

`runtime.py` and `decisions.py` each carried their own CASE statement over the
same step counts before this: the runtime's had no CANCELLED branch, so a
workflow every step of which had been rejected read RUNNING forever, and a fix
to one implementation was never a fix to the other. `aggregate.aggregate_workflow`
is now the one place this is computed, and this file is the proof for the
precedence itself — not just that the two call sites agree.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic.aggregate import aggregate_workflow
from app.models.agentic import AgentStep, AgentWorkflow
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


async def _workflow(db, owner: uuid.UUID) -> AgentWorkflow:
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    return workflow


async def _step(db, owner, workflow, *, key, state, ordinal, depends_on=None):
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=ordinal, key=key,
        state=state, role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={}, depends_on=depends_on or [],
    )
    db.add(step)
    await db.flush()
    return step


@pytest.mark.parametrize(
    "shapes,expected",
    [
        # Baselines.
        ([("SUCCEEDED", None)], "SUCCEEDED"),
        ([("SUCCEEDED", None), ("FAILED", None)], "FAILED"),
        ([("SUCCEEDED", None), ("WAITING_APPROVAL", None)], "WAITING_APPROVAL"),
        ([("SUCCEEDED", None), ("NEEDS_REVISION", None)], "NEEDS_REVISION"),
        ([("SUCCEEDED", None), ("QUEUED", None)], "RUNNING"),
        # The requested matrix.
        ([("CANCELLED", None), ("PENDING", None)], "RUNNING"),
        ([("CANCELLED", None), ("NEEDS_REVISION", None)], "NEEDS_REVISION"),
        ([("CANCELLED", None), ("SUCCEEDED", None)], "CANCELLED"),
        ([("CANCELLED", None), ("CANCELLED", None)], "CANCELLED"),
        ([("WAITING_APPROVAL", None), ("CANCELLED", None)], "WAITING_APPROVAL"),
    ],
)
@pytest.mark.asyncio
async def test_aggregate_matrix(scoped, owner, shapes, expected):
    workflow = await _workflow(scoped, owner)
    for index, (state, _dep) in enumerate(shapes):
        await _step(scoped, owner, workflow, key=f"s{index}", state=state, ordinal=index)

    result = await aggregate_workflow(scoped, owner_user_id=owner, workflow_id=workflow.id)
    assert result == expected, shapes

    persisted = (
        await scoped.execute(
            text("SELECT state FROM agent_workflows WHERE id = :w"), {"w": workflow.id}
        )
    ).scalar_one()
    assert persisted == expected


@pytest.mark.asyncio
async def test_cancelled_plus_blocked_does_not_zombie_at_running(scoped, owner):
    """A BLOCKED step whose only dependency was CANCELLED can never become
    READY — `unlock_dependants` only promotes when every dependency SUCCEEDED —
    so it must not be counted as active work still in flight."""
    workflow = await _workflow(scoped, owner)
    await _step(scoped, owner, workflow, key="a", state="CANCELLED", ordinal=1)
    await _step(
        scoped, owner, workflow, key="b", state="BLOCKED", ordinal=2, depends_on=["a"]
    )

    result = await aggregate_workflow(scoped, owner_user_id=owner, workflow_id=workflow.id)
    assert result == "CANCELLED"


@pytest.mark.asyncio
async def test_blocked_on_a_still_active_dependency_stays_running(scoped, owner):
    """The contrast case: a BLOCKED step whose dependency is merely not-yet-done
    (not terminally unrecoverable) is still real work in flight."""
    workflow = await _workflow(scoped, owner)
    await _step(scoped, owner, workflow, key="a", state="PENDING", ordinal=1)
    await _step(
        scoped, owner, workflow, key="b", state="BLOCKED", ordinal=2, depends_on=["a"]
    )

    result = await aggregate_workflow(scoped, owner_user_id=owner, workflow_id=workflow.id)
    assert result == "RUNNING"


@pytest.mark.asyncio
async def test_all_skipped_reads_succeeded(scoped, owner):
    """Nothing failed, nothing waiting, nothing revising, nothing active, and no
    CANCELLED step to explain an incomplete run: the honest default is that the
    workflow completed with nothing left to do."""
    workflow = await _workflow(scoped, owner)
    await _step(scoped, owner, workflow, key="a", state="SKIPPED", ordinal=1)

    result = await aggregate_workflow(scoped, owner_user_id=owner, workflow_id=workflow.id)
    assert result == "SUCCEEDED"
