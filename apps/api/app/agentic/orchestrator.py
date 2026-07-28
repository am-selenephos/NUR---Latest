"""Step claiming, leases and the append-only run ledger.

The whole reliability story of the Agency Plane rests on one question: when two
workers are handed the same step — which happens, because at-least-once delivery
is the only kind Celery offers — how do we guarantee the work runs once?

The answer here is that the claim is a single conditional UPDATE. A worker does
not read a step and then update it; those are two statements with a race between
them, and the race is exactly wide enough for a duplicate delivery to slip
through. Instead the worker attempts an UPDATE guarded by the state it expects,
and Postgres decides the winner: exactly one UPDATE matches, the loser gets zero
rows and stops. No advisory locks, no application-level mutex, nothing that
evaporates when a process dies.

Leases exist for the other half of that problem. A worker that crashes holding a
RUNNING step leaves it indistinguishable from a worker that is simply slow. A
lease turns "is this still alive?" into a timestamp comparison, so recovery can
reclaim genuinely abandoned work without guessing about liveness.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.enums import (
    STEP_TERMINAL,
    StepState,
    WorkflowState,
    assert_step_transition,
    assert_workflow_transition,
)

# How long a worker may hold a step before recovery considers it abandoned.
# Longer than any single step's timeout, so a slow-but-alive worker is never
# reclaimed out from under itself.
DEFAULT_LEASE_SECONDS = 900


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def argument_digest(tool_key: str, tool_version: str, arguments: dict) -> str:
    """Stable digest binding an approval to one exact call.

    `sort_keys` matters: `{"a":1,"b":2}` and `{"b":2,"a":1}` are the same call
    and must produce the same digest, or an approval would be invalidated by
    nothing more than dict ordering. Conversely any change to a value changes
    the digest, which is the property the approval flow depends on.
    """
    payload = json.dumps(
        {"tool": tool_key, "version": tool_version, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    step_id: uuid.UUID | None
    reason: str


async def record_event(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    event_type: str,
    summary: str,
    step_id: uuid.UUID | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    detail: dict | None = None,
    actor: str = "SYSTEM",
    trace_id: str | None = None,
) -> int:
    """Append one event and return its sequence number.

    The sequence is allocated inside the INSERT rather than read-then-written,
    so two concurrent appends cannot both compute the same next value. The
    unique index on (workflow_id, sequence) is the backstop: if the allocation
    is ever wrong the insert fails loudly instead of silently overwriting the
    history of a run.
    """
    row = await db.execute(
        text(
            """
            INSERT INTO agent_run_events (
                owner_user_id, workflow_id, step_id, sequence, event_type,
                from_state, to_state, summary, detail, actor, trace_id
            )
            SELECT
                :owner, :workflow, :step,
                COALESCE(MAX(sequence), 0) + 1,
                :event_type, :from_state, :to_state, :summary,
                CAST(:detail AS jsonb), :actor, :trace_id
            FROM agent_run_events WHERE workflow_id = :workflow
            RETURNING sequence
            """
        ),
        {
            "owner": owner_user_id,
            "workflow": workflow_id,
            "step": step_id,
            "event_type": event_type,
            "from_state": from_state,
            "to_state": to_state,
            "summary": summary,
            "detail": json.dumps(detail or {}),
            "actor": actor,
            "trace_id": trace_id,
        },
    )
    return int(row.scalar_one())


async def claim_step(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> ClaimResult:
    """Atomically move one QUEUED step to RUNNING.

    The guard `state = 'QUEUED'` is what makes duplicate delivery safe. Two
    workers issuing this UPDATE concurrently produce exactly one row update; the
    second sees zero rows because the first already moved the state, and returns
    `claimed=False` rather than executing the step a second time.

    `attempt` is incremented in the same statement so the count cannot drift
    from reality if a later write fails.
    """
    result = await db.execute(
        text(
            """
            UPDATE agent_steps
               SET state = 'RUNNING',
                   worker_id = :worker,
                   attempt = attempt + 1,
                   started_at = now(),
                   lease_expires_at = now() + make_interval(secs => :lease),
                   updated_at = now()
             WHERE id = :step
               AND owner_user_id = :owner
               AND state = 'QUEUED'
            RETURNING id
            """
        ),
        {"step": step_id, "owner": owner_user_id, "worker": worker_id, "lease": lease_seconds},
    )
    row = result.first()
    if row is None:
        return ClaimResult(False, None, "step was not QUEUED — already claimed, cancelled or gone")
    return ClaimResult(True, row[0], "claimed")


async def heartbeat_step(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Extend a lease. Only the holding worker may do so.

    Matching on `worker_id` prevents a worker that was already reclaimed from
    quietly taking its step back and running alongside the replacement.
    """
    result = await db.execute(
        text(
            """
            UPDATE agent_steps
               SET lease_expires_at = now() + make_interval(secs => :lease),
                   updated_at = now()
             WHERE id = :step AND owner_user_id = :owner
               AND worker_id = :worker AND state = 'RUNNING'
            RETURNING id
            """
        ),
        {"step": step_id, "owner": owner_user_id, "worker": worker_id, "lease": lease_seconds},
    )
    return result.first() is not None


async def reclaim_expired_steps(db: AsyncSession, *, limit: int = 50) -> list[uuid.UUID]:
    """Return abandoned RUNNING steps to QUEUED.

    Deliberately not owner-scoped in its WHERE clause: this is the recovery
    sweep, and it runs under a role whose RLS policy already confines it. Adding
    an owner filter here would require the sweeper to know every owner in
    advance, which is worse.

    A reclaimed step keeps its attempt count, so a step that repeatedly kills
    its worker is visible as a rising attempt number rather than looking fresh
    each time.
    """
    result = await db.execute(
        text(
            """
            UPDATE agent_steps
               SET state = 'QUEUED',
                   worker_id = NULL,
                   lease_expires_at = NULL,
                   updated_at = now()
             WHERE id IN (
                 SELECT id FROM agent_steps
                  WHERE state = 'RUNNING'
                    AND lease_expires_at IS NOT NULL
                    AND lease_expires_at < now()
                  ORDER BY lease_expires_at
                  LIMIT :limit
                  FOR UPDATE SKIP LOCKED
             )
            RETURNING id
            """
        ),
        {"limit": limit},
    )
    return [row[0] for row in result.fetchall()]


async def transition_step(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    current: StepState,
    nxt: StepState,
) -> bool:
    """Move a step, refusing transitions the state machine forbids.

    Validated in Python *and* guarded in SQL. The Python check gives a clear
    error at the call site; the SQL guard is what actually holds when two
    processes race, because a check that ran before the UPDATE proves nothing
    about the row's state during it.
    """
    assert_step_transition(current, nxt)
    result = await db.execute(
        text(
            """
            UPDATE agent_steps
               SET state = :next,
                   completed_at = CASE WHEN :terminal THEN now() ELSE completed_at END,
                   updated_at = now()
             WHERE id = :step AND owner_user_id = :owner AND state = :current
            RETURNING id
            """
        ),
        {
            "step": step_id,
            "owner": owner_user_id,
            "current": current.value,
            "next": nxt.value,
            "terminal": nxt in STEP_TERMINAL,
        },
    )
    return result.first() is not None


async def transition_workflow(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    current: WorkflowState,
    nxt: WorkflowState,
) -> bool:
    assert_workflow_transition(current, nxt)
    result = await db.execute(
        text(
            """
            UPDATE agent_workflows
               SET state = :next, updated_at = now()
             WHERE id = :workflow AND owner_user_id = :owner AND state = :current
            RETURNING id
            """
        ),
        {
            "workflow": workflow_id,
            "owner": owner_user_id,
            "current": current.value,
            "next": nxt.value,
        },
    )
    return result.first() is not None


async def unlock_dependants(
    db: AsyncSession, *, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> list[uuid.UUID]:
    """Promote BLOCKED steps whose dependencies have all succeeded.

    Dependencies are step *keys*, not row ids, so re-planning a workflow does
    not require rewriting every reference. The `NOT EXISTS` finds steps with no
    remaining unsatisfied dependency, which is cheaper and more honest than
    counting: a dependency that was cancelled or skipped still counts as not
    succeeded, so its dependants stay blocked rather than silently proceeding.
    """
    result = await db.execute(
        text(
            """
            UPDATE agent_steps s
               SET state = 'READY', updated_at = now()
             WHERE s.workflow_id = :workflow
               AND s.owner_user_id = :owner
               AND s.state = 'BLOCKED'
               AND NOT EXISTS (
                   SELECT 1
                     FROM jsonb_array_elements_text(s.depends_on) AS dep(key)
                     LEFT JOIN agent_steps d
                            ON d.workflow_id = s.workflow_id AND d.key = dep.key
                    WHERE d.id IS NULL OR d.state <> 'SUCCEEDED'
               )
            RETURNING s.id
            """
        ),
        {"workflow": workflow_id, "owner": owner_user_id},
    )
    return [row[0] for row in result.fetchall()]
