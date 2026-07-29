"""Two transactions appending to one workflow's ledger, concurrently.

`COALESCE(MAX(sequence), 0) + 1` inside the INSERT was the defect, and the unique
index on (workflow_id, sequence) is what made it visible rather than harmless:
both transactions read the same MAX — neither can see the other's uncommitted
row — both computed the same next value, and the loser's unique violation aborted
its *entire transaction*. So the domain mutation the event merely described was
rolled back too: a step that genuinely executed reported as never having run
because its ledger entry collided.

The allocator is now a counter on the workflow row, incremented under that row's
lock, so the second transaction waits and then reads a committed value.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic.orchestrator import record_event
from app.models.agentic import AgentWorkflow
from app.tests.conftest import register_user


@pytest.fixture()
async def owner(client) -> uuid.UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture()
def session_for(app_engine, owner):
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


async def _workflow(db, owner) -> uuid.UUID:
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    await db.commit()
    return workflow.id


@pytest.mark.asyncio
async def test_concurrent_appends_never_duplicate_a_sequence(session_for, owner):
    """Twelve genuinely concurrent transactions, each appending one event and
    committing. Every sequence must be distinct and every commit must survive."""
    async with session_for() as db:
        workflow_id = await _workflow(db, owner)

    async def append(index: int) -> int:
        async with session_for() as db:
            sequence = await record_event(
                db,
                owner_user_id=owner,
                workflow_id=workflow_id,
                event_type="CONCURRENT",
                summary=f"append {index}",
            )
            await db.commit()
            return sequence

    sequences = await asyncio.gather(*(append(i) for i in range(12)))

    assert len(set(sequences)) == len(sequences), (
        f"duplicate sequence allocated: {sorted(sequences)}"
    )

    async with session_for() as check:
        rows = (
            await check.execute(
                text(
                    "SELECT sequence FROM agent_run_events "
                    "WHERE workflow_id = :w ORDER BY sequence"
                ),
                {"w": workflow_id},
            )
        ).scalars().all()

    # Every append landed: none was lost to a rolled-back unique violation.
    assert len(rows) == 12, f"only {len(rows)} of 12 events persisted"
    assert rows == sorted(rows), "the ledger is not ordered"
    assert rows == list(range(1, 13)), f"sequence is not strictly increasing: {rows}"


@pytest.mark.asyncio
async def test_a_failed_event_append_does_not_roll_back_the_domain_mutation(
    session_for, owner
):
    """The consequence that made the old allocator dangerous, asserted directly:
    a concurrent append must not take an unrelated committed write down with it.

    Each transaction writes a durable domain change (bumping plan_version) and
    then appends its event. If allocation collided, the unique violation would
    abort the transaction and the plan_version bump would vanish.
    """
    async with session_for() as db:
        workflow_id = await _workflow(db, owner)

    async def mutate_and_append(index: int) -> None:
        async with session_for() as db:
            await db.execute(
                text(
                    "UPDATE agent_workflows SET cost_cents = cost_cents + 1 "
                    "WHERE id = :w AND owner_user_id = :o"
                ),
                {"w": workflow_id, "o": owner},
            )
            await record_event(
                db,
                owner_user_id=owner,
                workflow_id=workflow_id,
                event_type="MUTATION",
                summary=f"mutation {index}",
            )
            await db.commit()

    await asyncio.gather(*(mutate_and_append(i) for i in range(8)))

    async with session_for() as check:
        cost = (
            await check.execute(
                text("SELECT cost_cents FROM agent_workflows WHERE id = :w"),
                {"w": workflow_id},
            )
        ).scalar_one()
        events = (
            await check.execute(
                text("SELECT count(*) FROM agent_run_events WHERE workflow_id = :w"),
                {"w": workflow_id},
            )
        ).scalar_one()

    assert cost == 8, f"a domain mutation was lost to event allocation: cost={cost}"
    assert events == 8, f"an event was lost: {events}"


@pytest.mark.asyncio
async def test_separate_workflows_do_not_block_each_other(session_for, owner):
    """The counter is per workflow, so two workflows allocate independently and
    each starts its own ledger at 1 — a global sequence would serialise every
    append in the product behind one row."""
    async with session_for() as db:
        first = await _workflow(db, owner)
        second = await _workflow(db, owner)

    async def append(workflow_id: uuid.UUID, index: int) -> int:
        async with session_for() as db:
            sequence = await record_event(
                db,
                owner_user_id=owner,
                workflow_id=workflow_id,
                event_type="PARALLEL",
                summary=f"append {index}",
            )
            await db.commit()
            return sequence

    results = await asyncio.gather(
        *[append(first, i) for i in range(5)],
        *[append(second, i) for i in range(5)],
    )
    assert sorted(results[:5]) == [1, 2, 3, 4, 5]
    assert sorted(results[5:]) == [1, 2, 3, 4, 5], (
        "the second workflow's ledger did not start at 1; the counter is not per workflow"
    )


@pytest.mark.asyncio
async def test_the_ledger_remains_append_only(session_for, owner):
    """The allocator changed; the privilege model must not have. `nur_app` holds
    no UPDATE or DELETE on the ledger, so history cannot be rewritten even by a
    service that tries."""
    async with session_for() as db:
        workflow_id = await _workflow(db, owner)
        await record_event(
            db, owner_user_id=owner, workflow_id=workflow_id,
            event_type="APPEND", summary="original",
        )
        await db.commit()

    async with session_for() as db:
        for statement in (
            "UPDATE agent_run_events SET summary = 'rewritten' WHERE workflow_id = :w",
            "DELETE FROM agent_run_events WHERE workflow_id = :w",
        ):
            with pytest.raises(Exception) as caught:
                await db.execute(text(statement), {"w": workflow_id})
            assert "permission denied" in str(caught.value).lower(), str(caught.value)
            await db.rollback()
            await db.execute(
                text("SELECT set_config('app.current_user_id', :o, false)"),
                {"o": str(owner)},
            )
