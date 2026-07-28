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

from app.agentic.enums import StepState
from app.agentic.observability import continue_or_start, worker_id
from app.agentic.orchestrator import (
    claim_step,
    reclaim_expired_steps,
    record_event,
    transition_step,
    unlock_dependants,
)
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
    trace = continue_or_start(traceparent).child()
    owner = uuid.UUID(owner_user_id)
    workflow = uuid.UUID(workflow_id)
    step = uuid.UUID(step_id)
    me = worker_id()

    async with get_sessionmaker()() as db:
        # RLS context first. Everything below re-fetches by id under the owner's
        # policy, so a wrong owner id yields nothing rather than another's data.
        await set_user_context(db, owner)

        claim = await claim_step(db, owner_user_id=owner, step_id=step, worker_id=me)
        if not claim.claimed:
            # Normal outcome for a duplicate delivery. Acknowledge and stop —
            # retrying here is how one step becomes two executions.
            await db.commit()
            log(
                logger,
                "agentic step claim skipped",
                step_id=step_id,
                reason=claim.reason,
                trace_id=trace.trace_id,
            )
            return {"claimed": False, "reason": claim.reason, "trace_id": trace.trace_id}

        await record_event(
            db,
            owner_user_id=owner,
            workflow_id=workflow,
            step_id=step,
            event_type="STEP_CLAIMED",
            summary=f"claimed by {me}",
            from_state=StepState.QUEUED.value,
            to_state=StepState.RUNNING.value,
            trace_id=trace.trace_id,
        )
        await db.commit()

        # Handler execution lands with the runtime phase. Until a tool handler is
        # bound, the step is left RUNNING under its lease rather than being
        # marked SUCCEEDED — recovery will reclaim it, which is the honest
        # behaviour for work that has not actually been performed.
        log(
            logger,
            "agentic step claimed",
            step_id=step_id,
            worker=me,
            trace_id=trace.trace_id,
        )
        return {"claimed": True, "step_id": step_id, "trace_id": trace.trace_id}


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
        await db.commit()
        if reclaimed:
            log(logger, "agentic steps reclaimed", count=len(reclaimed))
        return {"reclaimed": [str(step_id) for step_id in reclaimed]}


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
