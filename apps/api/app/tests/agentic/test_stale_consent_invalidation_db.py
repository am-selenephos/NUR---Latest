"""A stale APPROVED/EDITED row must be invalidated the moment `evaluate_resume`
refuses it for a reason that means the decision itself is stale — not merely
insufficient for this attempt.

Before this, a PLAN_REVISED refusal recorded an APPROVAL_REFUSED event and
minted a fresh PENDING card, but left the old APPROVED row exactly as it was:
an approval that looks live in any audit query, sitting beside a fresh card the
owner is being asked to decide again. Both cannot be true at once.
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


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_read_only_handlers()


@pytest.mark.asyncio
async def test_plan_revision_invalidates_the_stale_approval_and_mints_one_fresh_card(
    scoped, owner
):
    scoped.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL], auto_run_tools=[],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING", plan_version=1
    )
    scoped.add(workflow)
    await scoped.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    scoped.add(step)
    await scoped.flush()
    await scoped.commit()

    # Pauses, mints the v1-plan approval.
    outcome = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w1"
    )
    await scoped.commit()
    assert outcome["step_state"] == "WAITING_APPROVAL", outcome

    original = (
        await scoped.execute(
            text(
                "SELECT id, argument_digest, plan_version, call_version FROM agent_approvals "
                "WHERE step_id = :s AND decision = 'PENDING'"
            ),
            {"s": step.id},
        )
    ).mappings().one()

    result = await decide(
        scoped, owner_user_id=owner, approval_id=original["id"], decision="APPROVE",
        seen_digest=original["argument_digest"], seen_plan_version=original["plan_version"],
        seen_call_version=original["call_version"],
    )
    await scoped.commit()
    assert result.step_state == "QUEUED"

    # Simulate a re-plan: the workflow moved on to a new revision. Bumping the
    # column directly rather than going through the planner, which is out of
    # scope here — the runtime's reaction to plan_version having moved is what
    # is under test, not how it moves.
    await scoped.execute(
        text("UPDATE agent_workflows SET plan_version = 2 WHERE id = :w"), {"w": workflow.id}
    )
    await scoped.commit()

    # Re-enters: the held APPROVED row no longer matches the current plan
    # revision, so evaluate_resume refuses PLAN_REVISED.
    outcome2 = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w2"
    )
    await scoped.commit()
    assert outcome2["step_state"] == "WAITING_APPROVAL", outcome2

    rows = (
        await scoped.execute(
            text(
                "SELECT id, decision, invalidated_from, invalidated_at, invalidation_reason, "
                "plan_version, call_version, argument_digest FROM agent_approvals "
                "WHERE step_id = :s ORDER BY id"
            ),
            {"s": step.id},
        )
    ).mappings().all()
    assert len(rows) == 2, rows

    stale, fresh = rows[0], rows[1]
    assert stale["id"] == original["id"]
    assert stale["decision"] == "INVALIDATED"
    assert stale["invalidated_from"] == "APPROVED"
    assert stale["invalidated_at"] is not None
    assert stale["invalidation_reason"] == "stale: PLAN_REVISED"

    assert fresh["decision"] == "PENDING"
    assert fresh["plan_version"] == 2
    assert fresh["call_version"] != stale["call_version"]

    # Promotable without a unique violation: only one actionable row exists
    # (the stale one is no longer APPROVED/EDITED), so approving the fresh
    # card does not collide with uq_agent_approval_one_actionable.
    result2 = await decide(
        scoped, owner_user_id=owner, approval_id=fresh["id"], decision="APPROVE",
        seen_digest=fresh["argument_digest"],
        seen_plan_version=fresh["plan_version"], seen_call_version=fresh["call_version"],
    )
    await scoped.commit()
    assert result2.step_state == "QUEUED"

    outcome3 = await run_step(
        scoped, owner_user_id=owner, step_id=step.id, trace=new_trace(), worker="w3"
    )
    await scoped.commit()
    assert outcome3["step_state"] == "SUCCEEDED", outcome3
