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

from app.agentic.aggregate import aggregate_workflow
from app.agentic.observability import continue_or_start, worker_id
from app.agentic.orchestrator import (
    reclaim_expired_steps,
    transition_step,
    unlock_dependants,
)
from app.agentic.runtime import run_step
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


@celery.task(name="nur.agentic.recover", ignore_result=False)
def recover_agentic_steps_task(limit: int = 50) -> dict:
    """Sweep abandoned leases back to QUEUED.

    Runs without an owner context because it spans owners by design; the sweeper
    connects under a role whose RLS policy already confines it, and asking it to
    enumerate every owner first would be both slower and more privileged.
    """
    return asyncio.run(_recover(limit))


async def _recover(limit: int) -> dict:
    async with get_sessionmaker()() as db:
        reclaimed = await reclaim_expired_steps(db, limit=limit)
        # A workflow stuck reading FAILED or WAITING_APPROVAL because its only
        # active step was the one just reclaimed must not stay wrong once that
        # step is QUEUED again. One aggregate call per distinct workflow, not
        # per step — a workflow with two reclaimed steps needs recomputing once.
        seen: set[tuple] = set()
        for row in reclaimed:
            key = (row.owner_user_id, row.workflow_id)
            if key in seen:
                continue
            seen.add(key)
            await aggregate_workflow(
                db, owner_user_id=row.owner_user_id, workflow_id=row.workflow_id
            )
        await db.commit()
        if reclaimed:
            log(logger, "agentic steps reclaimed", count=len(reclaimed))
        return {"reclaimed": [str(row.step_id) for row in reclaimed]}


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
    "execute_agentic_step_task",
    "recover_agentic_steps_task",
    "unlock_agentic_dependants_task",
    "transition_step",
]
