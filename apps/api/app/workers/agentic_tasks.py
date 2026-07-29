"""Celery tasks for the Agency Plane. ID-only payloads, claim-then-act.

Two rules govern everything here and both are load-bearing.

**Queue IDs, never the graph.** A payload carries a step id, an owner id and a
traceparent. It never carries the workflow DAG, tool arguments, or any owner
text. Serialising the graph would put private content in Redis, make the payload
grow with the plan, and — worst — let a stale queued message resurrect a plan
version the owner has already revised. Re-fetching by id after setting the RLS
context means the worker always acts on current state.

**Claim before acting, exit quietly when the claim fails.** `claim_step` is a
single conditional UPDATE; a duplicate delivery loses the race and returns
`claimed=False`. That is a normal outcome, not an error, so the task returns
rather than retrying — retrying a lost claim is how one logical step becomes two
executions.

`acks_late=True` on every task: the message is acknowledged after the work, so a
worker killed mid-step leaves the message to be redelivered. That is safe
precisely because the claim makes redelivery idempotent, and the lease makes an
abandoned step reclaimable.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import text

from app.agentic.aggregate import aggregate_workflow
from app.agentic.observability import continue_or_start, worker_id
from app.agentic.orchestrator import (
    reclaim_expired_steps,
    transition_step,
    unlock_dependants,
)
from app.agentic.runtime import run_step
from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.rls import set_user_context
from app.db.session import get_sessionmaker
from app.workers.celery_app import celery

configure_logging()
logger = logging.getLogger("nur.worker.agentic")


@celery.task(name="nur.agentic.execute_step", ignore_result=False, acks_late=True)
def execute_agentic_step_task(
    step_id: str,
    owner_user_id: str,
    workflow_id: str,
    traceparent: str | None = None,
) -> dict:
    """Execute one claimed step. Payload is IDs plus a traceparent, nothing else."""
    return asyncio.run(_execute_step(step_id, owner_user_id, workflow_id, traceparent))


async def _execute_step(
    step_id: str,
    owner_user_id: str,
    workflow_id: str,
    traceparent: str | None,
) -> dict:
    """Set the owner RLS context, then hand off to the one runtime entry point.

    The worker does not claim. There is exactly one claim site in the system and
    it lives inside `runtime.execute_step`. An earlier version of this task
    claimed here as well, which meant the runtime — reached later — would find
    the step already RUNNING and refuse to execute it. Two claim sites is not a
    duplicated line; it is a loop that cannot run.
    """
    trace = continue_or_start(traceparent).child()
    owner = uuid.UUID(owner_user_id)
    me = worker_id()

    async with get_sessionmaker()() as db:
        # RLS context first. Everything below re-fetches by id under the owner's
        # policy, so a wrong owner id yields nothing rather than another's data.
        await set_user_context(db, owner)

        # Policy and approval are resolved inside the runtime, after the claim.
        # Loading them here would read state that may change before the step
        # actually runs, so an owner revoking a policy or rejecting an approval
        # in that window would have their decision ignored.
        outcome = await run_step(
            db,
            owner_user_id=owner,
            step_id=uuid.UUID(step_id),
            trace=trace,
            worker=me,
        )
        await db.commit()

        log(
            logger,
            "agentic step finished",
            step_id=step_id,
            executed=outcome.get("executed"),
            step_state=outcome.get("step_state"),
            workflow_state=outcome.get("workflow_state"),
            trace_id=trace.trace_id,
        )

        # No direct dispatch. A READY step cannot be claimed, and publishing work
        # the database has not committed is how a rollback leaves a message
        # nothing will honour. The runtime queues dependants and writes a durable
        # dispatch intent in the same transaction; transport consumes that.
        return outcome


@celery.task(name="nur.agentic.dispatch", ignore_result=False)
def dispatch_agentic_intents_task(limit: int | None = None) -> dict:
    """Drain committed outbox intents onto the queue.

    This is the production dispatcher. Celery Beat runs it on
    `NUR_AGENTIC_DISPATCH_INTERVAL_SECONDS`; nothing calls `dispatch_once`
    by hand. Before this existed the outbox was a table nothing drained: the
    runtime committed intents correctly and they sat there forever.

    Publishing goes through `execute_agentic_step_task.delay`, so the payload is
    IDs plus a traceparent and never the plan or any owner text.
    """
    return asyncio.run(_dispatch(limit))


async def _dispatch(limit: int | None) -> dict:
    from app.agentic import dispatcher

    settings = get_settings()
    batch = int(limit) if limit is not None else int(settings.agentic_dispatch_batch)
    me = worker_id()

    def publish(step_id: str, owner_user_id: str, workflow_id: str, traceparent: str | None):
        # The broker call. Raising here returns the row to RETRYABLE with
        # bounded backoff rather than losing the intent.
        execute_agentic_step_task.delay(step_id, owner_user_id, workflow_id, traceparent)

    async with get_sessionmaker()() as db:
        # No owner RLS context: claiming spans owners by design, and it goes
        # through the SECURITY DEFINER ops boundary rather than a privileged
        # role. `nur_app` gains no table privilege from this.
        outcome = await dispatcher.dispatch_once(
            db, dispatcher_id=me, publish=publish, limit=batch
        )

    if outcome["claimed"]:
        log(
            logger,
            "agentic dispatch pass",
            claimed=outcome["claimed"],
            sent=len(outcome["sent"]),
            failed=len(outcome["failed"]),
            fenced=len(outcome["fenced"]),
            dispatcher=me,
        )
    return outcome


@celery.task(name="nur.agentic.recover", ignore_result=False)
def recover_agentic_steps_task(limit: int = 50) -> dict:
    """Sweep abandoned leases back to QUEUED, and re-queue them for dispatch.

    Runs without an owner context because it spans owners by design, through the
    SECURITY DEFINER ops boundary rather than under a role that can read owner
    content. Reclaiming alone is not recovery: the step also needs a dispatch
    intent, or it returns to QUEUED with nothing coming to execute it.
    """
    return asyncio.run(_recover(limit))


async def _recover(limit: int) -> dict:
    async with get_sessionmaker()() as db:
        reclaimed = await reclaim_expired_steps(db, limit=limit)

        requeued: list[str] = []
        seen: set[tuple] = set()
        for row in reclaimed:
            # Per-owner RLS context for the owner-scoped writes. Reclaiming is
            # the only cross-owner act; everything after it is done *as* that
            # owner, which keeps one aggregate implementation and needs no
            # further cross-owner privilege.
            await set_user_context(db, row.owner_user_id)

            # A reclaimed step is QUEUED with nothing coming unless an intent
            # exists. `attempt` was incremented by the claim it lost, so this
            # dispatch_key cannot collide with the one already marked SENT for
            # the previous attempt.
            attempt = (
                await db.execute(
                    text("SELECT attempt FROM agent_steps WHERE id = :s"), {"s": row.step_id}
                )
            ).scalar_one()
            await db.execute(
                text(
                    """
                    INSERT INTO agent_dispatch_outbox (
                        owner_user_id, workflow_id, step_id, dispatch_key, state
                    ) VALUES (:o, :w, :s, :key, 'RETRYABLE')
                    ON CONFLICT (dispatch_key) DO NOTHING
                    """
                ),
                {
                    "o": row.owner_user_id, "w": row.workflow_id, "s": row.step_id,
                    "key": f"{row.step_id}:recovered:{attempt}",
                },
            )
            requeued.append(str(row.step_id))

            # A workflow stuck reading FAILED or WAITING_APPROVAL because its
            # only active step was the one just reclaimed must not stay wrong
            # once that step is QUEUED again. One aggregate call per distinct
            # workflow — two reclaimed steps in one workflow recompute once.
            key = (row.owner_user_id, row.workflow_id)
            if key not in seen:
                seen.add(key)
                await aggregate_workflow(
                    db, owner_user_id=row.owner_user_id, workflow_id=row.workflow_id
                )
        await db.commit()
        if reclaimed:
            log(logger, "agentic steps reclaimed", count=len(reclaimed))
        return {
            "reclaimed": [str(row.step_id) for row in reclaimed],
            "requeued": requeued,
        }


@celery.task(name="nur.agentic.unlock", ignore_result=False)
def unlock_agentic_dependants_task(owner_user_id: str, workflow_id: str) -> dict:
    """Promote BLOCKED steps whose dependencies have all succeeded."""
    return asyncio.run(_unlock(owner_user_id, workflow_id))


async def _unlock(owner_user_id: str, workflow_id: str) -> dict:
    owner = uuid.UUID(owner_user_id)
    async with get_sessionmaker()() as db:
        await set_user_context(db, owner)
        unlocked = await unlock_dependants(
            db, owner_user_id=owner, workflow_id=uuid.UUID(workflow_id)
        )
        await db.commit()
        return {"unlocked": [str(step_id) for step_id in unlocked]}


__all__ = [
    "dispatch_agentic_intents_task",
    "execute_agentic_step_task",
    "recover_agentic_steps_task",
    "unlock_agentic_dependants_task",
    "transition_step",
]
