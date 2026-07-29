"""The registered Celery tasks themselves, not the coroutines behind them.

Every earlier transport test called `agentic_tasks._execute_step(...)` directly.
That proves the coroutine works and says nothing about whether a worker can ever
reach it — and it could not: `celery_app.include` listed only
`app.workers.tasks`, so a worker booted with `-A app.workers.celery_app`
registered no agentic task at all and the dispatcher's publish to
`nur.agentic.execute_step` would have been rejected as unknown. The registration
test below is the one that would have caught that.

Eager mode is labelled honestly: it proves registration, JSON round-tripping of
the payload, and that the task body runs — not that a broker carried anything.
The real-broker case lives in `test_real_broker_e2e_db.py`.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agentic import handlers
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user
from app.workers import agentic_tasks
from app.workers.celery_app import celery

TOOL = "get_timeline"

EXPECTED_TASKS = [
    "nur.agentic.dispatch",
    "nur.agentic.execute_step",
    "nur.agentic.recover",
    "nur.agentic.unlock",
]


@pytest.fixture(autouse=True)
def bound_handlers():
    handlers.bind_read_only_handlers()


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


async def _apply(task, args):
    """Run a registered task the way a prefork worker does: synchronously, in a
    thread with no running event loop, so the task's own `asyncio.run` works.

    Calling `.apply()` directly from an async test raises "asyncio.run() cannot
    be called from a running event loop" — a property of the test harness, not of
    the task, which in production is always entered from a plain worker thread.

    The process-global engine is disposed here first, from the loop its pooled
    connections actually belong to. A worker process only ever has one loop at a
    time, but this test process also has pytest's, and handing a connection
    opened on that loop to the task's fresh one raises "attached to a different
    loop". `run_task` disposes again on the way out, so the global is left clean
    either way.
    """
    import app.db.session as dbs

    if dbs._engine is not None:
        await dbs._engine.dispose()
        dbs._engine = None
        dbs._sessionmaker = None

    return await asyncio.to_thread(lambda: task.apply(args=args))


async def _seed(db, owner, *, auto_run=True, key="a"):
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
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key=key,
        state="QUEUED", role="operator", tool_key=TOOL, tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={"limit": 3}, depends_on=[],
    )
    db.add(step)
    await db.flush()
    await db.commit()
    return workflow.id, step.id


def test_a_real_worker_registers_every_agentic_task():
    """Boots the app exactly as `celery -A app.workers.celery_app worker` does.

    `import_default_modules()` is what a worker calls to resolve `include`. With
    `app.workers.agentic_tasks` missing from that list this returned none of the
    four names below, while every test that imported the module directly kept
    passing.
    """
    celery.loader.import_default_modules()
    celery.finalize()
    registered = set(celery.tasks)
    missing = [name for name in EXPECTED_TASKS if name not in registered]
    assert not missing, f"a real worker would not know these tasks: {missing}"


def test_both_background_loops_are_scheduled():
    """A registered task nothing ever calls is still inert. Beat is the caller."""
    schedule = celery.conf.beat_schedule or {}
    tasks = {entry["task"] for entry in schedule.values()}
    assert "nur.agentic.dispatch" in tasks, "nothing drains the outbox"
    assert "nur.agentic.recover" in tasks, "nothing reclaims abandoned leases"


def test_the_payload_is_ids_only():
    """The signature is the contract: no plan, no arguments, no owner text."""
    import inspect

    params = list(inspect.signature(agentic_tasks.execute_agentic_step_task).parameters)
    assert params == ["step_id", "owner_user_id", "workflow_id", "traceparent"], params


@pytest.mark.asyncio
async def test_registered_execution_task_runs_eagerly_end_to_end(scoped, owner):
    """EAGER MODE — proves registration, JSON serialisation of the payload and
    that the task body executes. It does not prove a broker carried the message;
    `test_real_broker_e2e_db.py` does that.

    Driven through `.apply()`, so the arguments go through Celery's own JSON
    serializer exactly as a published message would.
    """
    workflow_id, step_id = await _seed(scoped, owner)

    result = await _apply(
        agentic_tasks.execute_agentic_step_task,
        [str(step_id), str(owner), str(workflow_id), None],
    )
    assert result.successful(), result.traceback
    outcome = result.get()
    assert outcome["executed"] is True, outcome
    assert outcome["step_state"] == "SUCCEEDED", outcome

    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    row = (
        await scoped.execute(
            text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step_id}
        )
    ).scalar_one()
    assert row == "SUCCEEDED"

    calls = (
        await scoped.execute(
            text(
                "SELECT count(*) FROM agent_tool_calls "
                "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
            ),
            {"s": step_id},
        )
    ).scalar()
    assert calls == 1


@pytest.mark.asyncio
async def test_registered_dispatcher_task_claims_and_publishes(scoped, owner, monkeypatch):
    """The production dispatcher, driven as a registered task rather than by
    calling `dispatch_once` by hand.

    `.delay` is intercepted so the test does not need a broker; what is being
    proven here is that the registered dispatcher claims a committed intent and
    publishes an IDs-only payload for it.
    """
    workflow_id, step_id = await _seed(scoped, owner)
    await scoped.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
            "VALUES (:o, :w, :s, :k, 'RETRYABLE')"
        ),
        {"o": owner, "w": workflow_id, "s": step_id, "k": f"{step_id}:registered"},
    )
    await scoped.commit()

    published: list[tuple] = []
    monkeypatch.setattr(
        agentic_tasks.execute_agentic_step_task,
        "delay",
        lambda *args: published.append(args),
    )

    result = await _apply(agentic_tasks.dispatch_agentic_intents_task, [50])
    assert result.successful(), result.traceback

    mine = [p for p in published if p[0] == str(step_id)]
    assert len(mine) == 1, f"the dispatcher did not publish this step: {published}"
    assert mine[0][1] == str(owner)
    assert mine[0][2] == str(workflow_id)

    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    state = (
        await scoped.execute(
            text("SELECT state FROM agent_dispatch_outbox WHERE step_id = :s"), {"s": step_id}
        )
    ).scalar_one()
    assert state == "SENT"


@pytest.mark.asyncio
async def test_registered_recovery_task_reclaims_and_requeues(scoped, owner):
    """Recovery through the registered task, not through an internal SQL helper
    run as an admin role — the distinction that mattered, because as `nur_app`
    with no session variable the direct UPDATE silently swept nothing."""
    workflow_id, step_id = await _seed(scoped, owner)
    before = (
        await scoped.execute(
            text(
                "UPDATE agent_steps SET state = 'RUNNING', worker_id = 'dead', "
                "lease_expires_at = now() - interval '1 minute' "
                "WHERE id = :s RETURNING execution_attempt"
            ),
            {"s": step_id},
        )
    ).scalar_one()
    await scoped.commit()

    result = await _apply(agentic_tasks.recover_agentic_steps_task, [50])
    assert result.successful(), result.traceback
    outcome = result.get()
    assert str(step_id) in outcome["reclaimed"], outcome
    assert str(step_id) in outcome["requeued"], outcome

    await scoped.rollback()
    await scoped.execute(
        text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
    )
    row = (
        await scoped.execute(
            text(
                "SELECT state, worker_id, execution_attempt FROM agent_steps WHERE id = :s"
            ),
            {"s": step_id},
        )
    ).mappings().one()
    assert row["state"] == "QUEUED"
    assert row["worker_id"] is None
    assert row["execution_attempt"] != before, "the abandoning worker was not fenced"

    # Reclaiming without re-queueing would leave the step QUEUED with nothing
    # coming to execute it — recovery that looks like it worked and never does.
    intents = (
        await scoped.execute(
            text(
                "SELECT count(*) FROM agent_dispatch_outbox "
                "WHERE step_id = :s AND state = 'RETRYABLE'"
            ),
            {"s": step_id},
        )
    ).scalar()
    assert intents >= 1, "a reclaimed step has no dispatch intent"


@pytest.mark.asyncio
async def test_a_task_survives_being_invoked_repeatedly(scoped, owner):
    """A Beat-driven task runs thousands of times in one worker process.

    `asyncio.run` closes its loop on return while the database engine is a
    process-level singleton, so the pool stayed bound to the first loop and the
    *second* invocation raised "Event loop is closed" — verified directly against
    this codebase's engine before the fix. Every asyncio.run-based task in the
    worker was therefore a one-shot, which is invisible to a suite that calls each
    task once and fatal to a dispatcher scheduled every five seconds.

    Three passes, because the defect appears on the second.
    """
    for pass_number in range(3):
        result = await _apply(agentic_tasks.dispatch_agentic_intents_task, [5])
        assert result.successful(), (
            f"invocation {pass_number + 1} failed: {result.traceback}"
        )
