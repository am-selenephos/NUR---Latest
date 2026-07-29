"""A real broker carries the message and a real worker process consumes it.

Everything else in this suite proves the pieces: eager mode proves the task is
registered and its body runs, `dispatch_once` proves the claim, `run_step` proves
execution. None of that proves a message survived serialisation, travelled
through Redis, and was picked up by a separate OS process that had to resolve the
task by name from its own `include` list — which is exactly the step that was
broken, because `app.workers.agentic_tasks` was absent from that list and a real
worker would have rejected `nur.agentic.execute_step` as unknown.

So this test starts an actual `celery worker` subprocess against the real Redis
this repository already runs, publishes through the real dispatcher, and waits
for PostgreSQL to show the work done. Nothing here is mocked or eager.

If Redis is unreachable the test FAILS rather than skipping. A silent skip is how
an integration guarantee quietly stops being tested.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow
from app.tests.conftest import register_user

TOOL = "get_timeline"
API_DIR = pathlib.Path(__file__).resolve().parents[3]
BOOT_TIMEOUT = 60
WORK_TIMEOUT = 60


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


def _require_redis() -> str:
    """A missing broker is a hard failure, never a skip."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    import redis as sync_redis

    client = sync_redis.Redis.from_url(url)
    try:
        assert client.ping() is True, f"Redis at {url} did not answer PING"
    finally:
        client.close()
    return url


class _Worker:
    """A real `celery worker` subprocess, resolving tasks from its own include list."""

    def __init__(self, queue: str) -> None:
        self.queue = queue
        self.process: subprocess.Popen | None = None
        self.log = API_DIR / f".nur-runtime/celery-{queue}.log"

    def start(self) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        handle = self.log.open("w")
        self.process = subprocess.Popen(
            [
                sys.executable, "-m", "celery",
                "-A", "app.workers.celery_app", "worker",
                "--loglevel=info",
                # solo: one task at a time in the main thread, which is also the
                # pool that makes the task's own asyncio.run correct.
                "--pool=solo",
                "--concurrency=1",
                "-Q", self.queue,
                "-n", f"probe-{self.queue}@%h",
                "--without-gossip", "--without-mingle", "--without-heartbeat",
            ],
            cwd=str(API_DIR),
            env={**os.environ},
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + BOOT_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(
                    f"worker exited during boot:\n{self.log.read_text()[-4000:]}"
                )
            text_log = self.log.read_text() if self.log.exists() else ""
            if "ready" in text_log.lower():
                # The task must be in the banner's registered list, or the
                # message will be rejected as unknown at delivery time.
                assert "nur.agentic.execute_step" in text_log, (
                    f"worker booted without the agentic tasks:\n{text_log[-4000:]}"
                )
                return
            time.sleep(0.5)
        raise AssertionError(f"worker never became ready:\n{self.log.read_text()[-4000:]}")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)

    def tail(self) -> str:
        return self.log.read_text()[-4000:] if self.log.exists() else "(no log)"


async def _seed(db, owner, *, key: str) -> tuple[uuid.UUID, uuid.UUID]:
    db.add(
        AgentPolicy(
            owner_user_id=owner, initiative_level="INTERNAL",
            max_risk_class="R2_DURABLE_PRIVATE",
            permitted_tools=[TOOL], auto_run_tools=[TOOL],
        )
    )
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="broker", objective="o", state="RUNNING"
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


async def _await_state(scoped, owner, step_id, wanted: set[str], *, worker: _Worker) -> str:
    """Poll PostgreSQL until the step reaches one of `wanted`."""
    deadline = time.monotonic() + WORK_TIMEOUT
    last = None
    while time.monotonic() < deadline:
        await scoped.rollback()
        await scoped.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        last = (
            await scoped.execute(
                text("SELECT state FROM agent_steps WHERE id = :s"), {"s": step_id}
            )
        ).scalar_one()
        if last in wanted:
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(
        f"step stayed {last}, never reached {wanted}\nworker log:\n{worker.tail()}"
    )


@pytest.mark.asyncio
async def test_a_real_broker_and_real_worker_complete_the_work(scoped, owner):
    """REAL BROKER: Redis carries the message, a separate `celery worker`
    process consumes it, PostgreSQL records the result.

    The queue name is unique per run so a developer's own worker on the same
    Redis cannot consume this test's message and make it look green.
    """
    _require_redis()
    queue = f"nurtest_{uuid.uuid4().hex[:10]}"
    workflow_id, step_id = await _seed(scoped, owner, key="a")

    worker = _Worker(queue)
    worker.start()
    try:
        from app.workers.agentic_tasks import execute_agentic_step_task

        # A real publish onto the real broker — not .apply(), not eager.
        execute_agentic_step_task.apply_async(
            args=[str(step_id), str(owner), str(workflow_id), None], queue=queue
        )

        state = await _await_state(
            scoped, owner, step_id, {"SUCCEEDED", "FAILED"}, worker=worker
        )
        assert state == "SUCCEEDED", f"worker log:\n{worker.tail()}"

        calls = (
            await scoped.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": step_id},
            )
        ).scalar()
        assert calls == 1, "the handler did not run exactly once"
    finally:
        worker.stop()


@pytest.mark.asyncio
async def test_broker_redelivery_produces_one_durable_effect(scoped, owner):
    """REAL BROKER: the same logical work published twice.

    At-least-once is the only delivery Celery offers, so the guarantee has to
    come from the step claim: the second message loses the conditional UPDATE and
    exits. One durable effect, two deliveries — never "exactly-once publication".
    """
    _require_redis()
    queue = f"nurtest_{uuid.uuid4().hex[:10]}"
    workflow_id, step_id = await _seed(scoped, owner, key="a")

    worker = _Worker(queue)
    worker.start()
    try:
        from app.workers.agentic_tasks import execute_agentic_step_task

        for _ in range(3):
            execute_agentic_step_task.apply_async(
                args=[str(step_id), str(owner), str(workflow_id), None], queue=queue
            )

        state = await _await_state(
            scoped, owner, step_id, {"SUCCEEDED", "FAILED"}, worker=worker
        )
        assert state == "SUCCEEDED", f"worker log:\n{worker.tail()}"

        # Give the redundant deliveries time to be consumed and lose the claim.
        await asyncio.sleep(3)
        await scoped.rollback()
        await scoped.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        calls = (
            await scoped.execute(
                text(
                    "SELECT count(*) FROM agent_tool_calls "
                    "WHERE step_id = :s AND outcome = 'SUCCEEDED'"
                ),
                {"s": step_id},
            )
        ).scalar()
        assert calls == 1, (
            f"three deliveries produced {calls} durable effects\n{worker.tail()}"
        )
    finally:
        worker.stop()


@pytest.mark.asyncio
async def test_a_restarted_worker_still_completes_committed_work(scoped, owner):
    """REAL BROKER: nothing is held in worker memory.

    The message is published while no worker is listening, then a worker starts
    for the first time and finds it. Restart-safety here means the durable state
    plus the broker are sufficient — a worker that had to have been running when
    the work was created would lose everything on deploy.
    """
    _require_redis()
    queue = f"nurtest_{uuid.uuid4().hex[:10]}"
    workflow_id, step_id = await _seed(scoped, owner, key="a")

    from app.workers.agentic_tasks import execute_agentic_step_task

    # Published first, with no consumer alive.
    execute_agentic_step_task.apply_async(
        args=[str(step_id), str(owner), str(workflow_id), None], queue=queue
    )

    worker = _Worker(queue)
    worker.start()
    try:
        state = await _await_state(
            scoped, owner, step_id, {"SUCCEEDED", "FAILED"}, worker=worker
        )
        assert state == "SUCCEEDED", f"worker log:\n{worker.tail()}"
    finally:
        worker.stop()
