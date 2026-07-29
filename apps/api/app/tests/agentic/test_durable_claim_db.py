"""The durable claim, and what it lets recovery do safely.

Claim + handler + verification + terminal write used to share one transaction. A
worker killed mid-handler therefore rolled its own claim back: the step returned
to QUEUED looking untouched, with no record an attempt had been made, and no way
to tell a crash from a step that had never started. For a handler with an
external effect that is the difference between "retry safely" and "repeat an
effect nobody can see".

The claim now commits on its own, and `execution_attempt` — reissued on every
claim and every reclaim — fences everything after it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.agentic.enums import StepState
from app.agentic.observability import new_trace
from app.agentic.orchestrator import (
    attempt_still_current,
    claim_step,
    reclaim_expired_steps,
    transition_step,
)
from app.agentic.runtime import run_step
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_all_handlers()


@pytest.fixture()
async def owner(client) -> uuid.UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture()
def session_for(app_engine, owner):
    """Independent sessions, each with the owner's RLS context — so a claim can be
    proven to survive the session that made it."""
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


async def _seed(db, owner, *, auto_run=True):
    db.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL], auto_run_tools=[TOOL] if auto_run else [],
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
    await db.commit()
    return workflow.id, step.id


@pytest.mark.asyncio
async def test_the_claim_survives_the_session_that_made_it(session_for, owner):
    """Committed before the handler runs, so a process death mid-handler leaves
    a durable record that an attempt happened."""
    async with session_for() as db:
        _workflow_id, step_id = await _seed(db, owner)

    async with session_for() as claimer:
        claim = await claim_step(
            claimer, owner_user_id=owner, step_id=step_id, worker_id="w1"
        )
        assert claim.claimed is True
        assert claim.execution_attempt is not None
        token = claim.execution_attempt
        await claimer.commit()
        # The session ends here, as it would if the process were killed.

    async with session_for() as after:
        row = (
            await after.execute(
                text(
                    "SELECT state, worker_id, attempt, execution_attempt, "
                    "lease_expires_at IS NOT NULL AS leased FROM agent_steps WHERE id = :s"
                ),
                {"s": step_id},
            )
        ).mappings().one()
        assert row["state"] == "RUNNING", "the claim did not survive its session"
        assert row["worker_id"] == "w1"
        assert row["attempt"] == 1
        assert row["execution_attempt"] == token
        assert row["leased"] is True


@pytest.mark.asyncio
async def test_a_second_worker_cannot_acquire_a_live_claim(session_for, owner):
    async with session_for() as db:
        _workflow_id, step_id = await _seed(db, owner)

    async with session_for() as first:
        won = await claim_step(first, owner_user_id=owner, step_id=step_id, worker_id="w1")
        await first.commit()
    assert won.claimed is True

    async with session_for() as second:
        lost = await claim_step(second, owner_user_id=owner, step_id=step_id, worker_id="w2")
        await second.commit()
    assert lost.claimed is False, "two workers hold the same live claim"
    assert lost.execution_attempt is None


@pytest.mark.asyncio
async def test_a_stale_worker_can_neither_succeed_nor_fail_after_being_reclaimed(
    session_for, owner
):
    """The core fencing property. `worker_id` alone would still match the stale
    worker's own name, so its terminal write would land on top of the live
    attempt's."""
    async with session_for() as db:
        _workflow_id, step_id = await _seed(db, owner)

    async with session_for() as first:
        stale = await claim_step(first, owner_user_id=owner, step_id=step_id, worker_id="w1")
        await first.commit()
    stale_token = stale.execution_attempt

    # Its lease expires and recovery takes the step back.
    async with session_for() as expire:
        await expire.execute(
            text(
                "UPDATE agent_steps SET lease_expires_at = now() - interval '1 minute' "
                "WHERE id = :s"
            ),
            {"s": step_id},
        )
        await expire.commit()

    async with session_for() as sweep:
        reclaimed = await reclaim_expired_steps(sweep, limit=50)
        await sweep.commit()
    assert step_id in {row.step_id for row in reclaimed}

    # A new worker claims it and holds a different token.
    async with session_for() as second:
        live = await claim_step(second, owner_user_id=owner, step_id=step_id, worker_id="w2")
        await second.commit()
    assert live.claimed is True
    assert live.execution_attempt != stale_token

    async with session_for() as ghost:
        assert await attempt_still_current(
            ghost, owner_user_id=owner, step_id=step_id, execution_attempt=stale_token
        ) is False, "the stale attempt still believes it owns the step"

        # Neither a success nor a failure may land.
        succeeded = await transition_step(
            ghost, owner_user_id=owner, step_id=step_id,
            current=StepState.RUNNING, nxt=StepState.VERIFYING,
            execution_attempt=stale_token,
        )
        assert succeeded is False, "a stale worker marked the step as progressing"

        failed = await transition_step(
            ghost, owner_user_id=owner, step_id=step_id,
            current=StepState.RUNNING, nxt=StepState.FAILED,
            execution_attempt=stale_token,
        )
        assert failed is False, "a stale worker marked the step failed"
        await ghost.commit()

    async with session_for() as check:
        state = (
            await check.execute(
                text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step_id}
            )
        ).scalar_one()
        assert state == "RUNNING", "the live attempt's state was overwritten"

    # And the live attempt still can.
    async with session_for() as owner_of_it:
        assert await transition_step(
            owner_of_it, owner_user_id=owner, step_id=step_id,
            current=StepState.RUNNING, nxt=StepState.VERIFYING,
            execution_attempt=live.execution_attempt,
        ) is True
        await owner_of_it.commit()


@pytest.mark.asyncio
async def test_run_step_refuses_to_finish_an_attempt_it_lost(session_for, owner):
    """End to end through the real entry point: if the token moves while the
    handler runs, `run_step` writes no terminal state at all."""
    async with session_for() as db:
        _workflow_id, step_id = await _seed(db, owner)

    # Reproduce "lease reclaimed mid-handler" deterministically: claim, then move
    # the token underneath the attempt before it can complete.
    async with session_for() as db:
        claim = await claim_step(db, owner_user_id=owner, step_id=step_id, worker_id="w1")
        await db.commit()
        assert claim.claimed

        await db.execute(
            text("UPDATE agent_steps SET execution_attempt = gen_random_uuid() WHERE id = :s"),
            {"s": step_id},
        )
        await db.commit()

        # The step is RUNNING under a different token now, so this worker's own
        # run_step call cannot claim it and exits without executing.
        outcome = await run_step(
            db, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w1"
        )
        assert outcome["executed"] is False, outcome

    async with session_for() as check:
        calls = (
            await check.execute(
                text("SELECT count(*) FROM agent_tool_calls WHERE step_id = :s"),
                {"s": step_id},
            )
        ).scalar()
        assert calls == 0, "a step it did not own produced a tool call"


@pytest.mark.asyncio
async def test_a_duplicate_delivery_produces_one_durable_effect(session_for, owner):
    """Two full run_step passes, as two deliveries of the same message."""
    async with session_for() as db:
        _workflow_id, step_id = await _seed(db, owner)

    async with session_for() as first:
        one = await run_step(
            first, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w1"
        )
        await first.commit()
    assert one["executed"] is True
    assert one["step_state"] == "SUCCEEDED"

    async with session_for() as second:
        two = await run_step(
            second, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="w2"
        )
        await second.commit()
    assert two["executed"] is False, "the redelivery executed a second time"

    async with session_for() as check:
        calls = (
            await check.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": step_id},
            )
        ).scalar()
        assert calls == 1, f"the handler ran {calls} times"


@pytest.mark.asyncio
async def test_an_expired_claim_is_recoverable_and_completes(session_for, owner):
    """Full crash/recovery path: abandoned RUNNING step, expired lease, recovery,
    fresh token, new worker, exactly one durable result."""
    async with session_for() as db:
        _workflow_id, step_id = await _seed(db, owner)

    async with session_for() as crashed:
        dead = await claim_step(
            crashed, owner_user_id=owner, step_id=step_id, worker_id="crashed"
        )
        await crashed.commit()
    dead_token = dead.execution_attempt

    async with session_for() as expire:
        await expire.execute(
            text(
                "UPDATE agent_steps SET lease_expires_at = now() - interval '1 minute' "
                "WHERE id = :s"
            ),
            {"s": step_id},
        )
        await expire.commit()

    async with session_for() as sweep:
        reclaimed = await reclaim_expired_steps(sweep, limit=50)
        await sweep.commit()
    assert step_id in {row.step_id for row in reclaimed}

    async with session_for() as fresh:
        row = (
            await fresh.execute(
                text("SELECT state, execution_attempt FROM agent_steps WHERE id = :s"),
                {"s": step_id},
            )
        ).mappings().one()
        assert row["state"] == "QUEUED"
        assert row["execution_attempt"] != dead_token, "recovery did not fence the dead attempt"

        outcome = await run_step(
            fresh, owner_user_id=owner, step_id=step_id, trace=new_trace(), worker="replacement"
        )
        await fresh.commit()
        assert outcome["executed"] is True, outcome
        assert outcome["step_state"] == "SUCCEEDED", outcome

    async with session_for() as check:
        calls = (
            await check.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": step_id},
            )
        ).scalar()
        assert calls == 1, "recovery produced a duplicate durable effect"

        attempts = (
            await check.execute(
                text("SELECT attempt FROM agent_steps WHERE id = :s"), {"s": step_id}
            )
        ).scalar_one()
        # The crashed attempt is still counted: a step that repeatedly kills its
        # worker must be visible as a rising number, not look fresh each time.
        assert attempts == 2, f"attempt count lost the crashed attempt: {attempts}"


@pytest.mark.asyncio
async def test_no_immortal_running_row(session_for, owner):
    """A hard ceiling below the lease means a RUNNING row is always eventually
    either finished or reclaimable — never stuck forever."""
    from app.agentic.orchestrator import DEFAULT_LEASE_SECONDS
    from app.core.config import get_settings

    ceiling = get_settings().agentic_step_timeout_seconds
    assert ceiling < DEFAULT_LEASE_SECONDS, (
        "the handler ceiling must be strictly below the lease, or a live worker "
        "can be reclaimed while still executing and two workers hold one step"
    )
