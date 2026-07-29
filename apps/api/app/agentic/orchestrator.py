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
# Strictly longer than the hard handler timeout (NUR_AGENTIC_STEP_TIMEOUT_SECONDS,
# default 120s), so a slow-but-alive worker is never reclaimed out from under
# itself, and short enough that a killed worker's step becomes runnable again in
# minutes rather than a quarter of an hour.
#
# There is deliberately no heartbeat. A periodic lease extension would need its
# own database connection per in-flight step — handlers here run on the caller's
# session, and issuing a concurrent statement on it is not safe — to buy nothing
# the timeout does not already guarantee: a handler that cannot outlive its lease
# cannot have its lease expire while it is alive.
DEFAULT_LEASE_SECONDS = 300


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
    # The token this claim was issued under. Every later write for this
    # attempt — completion, failure, terminal transition — must present it, so a
    # worker whose lease was reclaimed cannot finish work it no longer holds.
    execution_attempt: uuid.UUID | None = None


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

    The sequence comes from a counter on the workflow row, incremented under
    that row's lock. `COALESCE(MAX(sequence), 0) + 1` was not safe: two
    concurrent appends to the same workflow each read the same MAX — neither
    sees the other's uncommitted row — both computed the same value, and the
    loser's unique violation aborted its entire transaction, rolling back the
    domain mutation the event was merely describing. A step that really ran
    would report as never having run because its ledger entry collided.

    Incrementing the counter instead makes the second transaction wait on the
    row lock and then read a genuinely fresh value. Separate workflows touch
    separate rows and never block one another. The unique index on
    (workflow_id, sequence) stays as the backstop.
    """
    sequence = (
        await db.execute(
            text(
                "UPDATE agent_workflows SET event_seq = event_seq + 1 "
                "WHERE id = :workflow AND owner_user_id = :owner "
                "RETURNING event_seq"
            ),
            {"workflow": workflow_id, "owner": owner_user_id},
        )
    ).scalar_one()

    row = await db.execute(
        text(
            """
            INSERT INTO agent_run_events (
                owner_user_id, workflow_id, step_id, sequence, event_type,
                from_state, to_state, summary, detail, actor, trace_id
            ) VALUES (
                :owner, :workflow, :step, :sequence,
                :event_type, :from_state, :to_state, :summary,
                CAST(:detail AS jsonb), :actor, :trace_id
            )
            RETURNING sequence
            """
        ),
        {
            "sequence": sequence,
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

    A fresh `execution_attempt` is minted here and returned. The caller commits
    this claim before executing anything, so the claim survives the process
    dying mid-handler, and every subsequent write for the attempt is fenced on
    the token rather than on `worker_id` — which would still match the name of
    a worker whose lease had already been reclaimed.
    """
    result = await db.execute(
        text(
            """
            UPDATE agent_steps
               SET state = 'RUNNING',
                   worker_id = :worker,
                   attempt = attempt + 1,
                   execution_attempt = gen_random_uuid(),
                   started_at = now(),
                   lease_expires_at = now() + make_interval(secs => :lease),
                   updated_at = now()
             WHERE id = :step
               AND owner_user_id = :owner
               AND state = 'QUEUED'
            RETURNING id, execution_attempt
            """
        ),
        {"step": step_id, "owner": owner_user_id, "worker": worker_id, "lease": lease_seconds},
    )
    row = result.first()
    if row is None:
        return ClaimResult(False, None, "step was not QUEUED — already claimed, cancelled or gone")
    return ClaimResult(True, row[0], "claimed", execution_attempt=row[1])


async def attempt_still_current(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    execution_attempt: uuid.UUID,
) -> bool:
    """Whether this attempt still owns the step.

    Checked before a terminal write so a stale worker's completion is refused
    rather than overwriting the live attempt's outcome.
    """
    row = await db.execute(
        text(
            "SELECT 1 FROM agent_steps WHERE id = :step AND owner_user_id = :owner "
            "AND execution_attempt = :attempt"
        ),
        {"step": step_id, "owner": owner_user_id, "attempt": execution_attempt},
    )
    return row.first() is not None


@dataclass(frozen=True)
class ReclaimedStep:
    step_id: uuid.UUID
    workflow_id: uuid.UUID
    owner_user_id: uuid.UUID


async def reclaim_expired_steps(db: AsyncSession, *, limit: int = 50) -> list[ReclaimedStep]:
    """Return abandoned RUNNING steps to QUEUED, across owners.

    Goes through `agent_ops_reclaim_expired_steps`, a SECURITY DEFINER function
    owned by the schema owner, rather than issuing the UPDATE directly. A plain
    cross-owner UPDATE from `nur_app` matches zero rows: every agentic table has
    FORCE ROW LEVEL SECURITY, `nur_app` correctly holds no BYPASSRLS, and this
    sweep by design runs with no `app.current_user_id` set — so recovery
    silently reclaimed nothing in every environment. The alternative fixes were
    both worse: BYPASSRLS on `nur_app` would expose every owner's private data
    to the request-serving role, and running the sweep as the schema owner is
    the same escalation under another name.

    A reclaimed step keeps its attempt count, so a step that repeatedly kills
    its worker is visible as a rising attempt number rather than looking fresh
    each time. It receives a *new* `execution_attempt`, which is what stops the
    worker that abandoned it from later completing the attempt it lost.

    Returns workflow_id and owner_user_id alongside each step id so the caller
    can recompute the affected workflows' aggregate state — a workflow stuck
    reading FAILED or WAITING_APPROVAL because its only active step was the one
    just reclaimed must not stay wrong once that step is runnable again.
    """
    result = await db.execute(
        text(
            "SELECT step_id, workflow_id, owner_user_id "
            "FROM agent_ops_reclaim_expired_steps(:limit)"
        ),
        {"limit": limit},
    )
    return [
        ReclaimedStep(step_id=row[0], workflow_id=row[1], owner_user_id=row[2])
        for row in result.fetchall()
    ]


async def transition_step(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    current: StepState,
    nxt: StepState,
    execution_attempt: uuid.UUID | None = None,
) -> bool:
    """Move a step, refusing transitions the state machine forbids.

    Validated in Python *and* guarded in SQL. The Python check gives a clear
    error at the call site; the SQL guard is what actually holds when two
    processes race, because a check that ran before the UPDATE proves nothing
    about the row's state during it.

    `execution_attempt`, when supplied, fences the write to one claim. A worker
    whose lease expired mid-handler would otherwise still find the step RUNNING
    — because the replacement worker put it back there — and its terminal write
    would land on top of the live attempt's. Passing the token turns that into
    a zero-row update the caller can detect.
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
               AND (
                   CAST(:attempt AS uuid) IS NULL
                   OR execution_attempt = CAST(:attempt AS uuid)
               )
            RETURNING id
            """
        ),
        {
            "step": step_id,
            "owner": owner_user_id,
            "current": current.value,
            "next": nxt.value,
            "terminal": nxt in STEP_TERMINAL,
            "attempt": execution_attempt,
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


async def queue_ready_dependants(
    db: AsyncSession, *, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> list[dict]:
    """Move READY steps to QUEUED and write one dispatch intent each.

    This is the missing link that made the dependant pipeline dead:
    `unlock_dependants` promoted BLOCKED to READY, the worker published READY
    steps directly, and `claim_step` only ever claims QUEUED. Every dependant
    message therefore lost its claim and the child never executed.

    The transition and the intent are written in one transaction. Publishing
    before commit would let a rollback strand a message the database never
    agreed to; publishing after commit with no record would strand the step if
    the process died in between. The row is the durable middle.

    SKIP LOCKED so two schedulers running concurrently divide the work instead
    of blocking on each other.
    """
    rows = (
        await db.execute(
            text(
                """
                WITH claimed AS (
                    SELECT id FROM agent_steps
                     WHERE workflow_id = :workflow
                       AND owner_user_id = :owner
                       AND state = 'READY'
                     ORDER BY ordinal
                     FOR UPDATE SKIP LOCKED
                )
                UPDATE agent_steps s
                   SET state = 'QUEUED', queued_at = now(), updated_at = now()
                  FROM claimed
                 WHERE s.id = claimed.id
             RETURNING s.id, s.attempt
                """
            ),
            {"workflow": workflow_id, "owner": owner_user_id},
        )
    ).mappings().all()

    queued: list[dict] = []
    for row in rows:
        # One intent per step attempt. The unique dispatch_key makes a repeated
        # scheduler pass idempotent rather than duplicating the intent.
        await db.execute(
            text(
                """
                INSERT INTO agent_dispatch_outbox (
                    owner_user_id, workflow_id, step_id, dispatch_key, state
                ) VALUES (:owner, :workflow, :step, :key, 'RETRYABLE')
                ON CONFLICT (dispatch_key) DO NOTHING
                """
            ),
            {
                "owner": owner_user_id,
                "workflow": workflow_id,
                "step": row["id"],
                "key": f"{row['id']}:{row['attempt']}",
            },
        )
        await record_event(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow_id,
            step_id=row["id"],
            event_type="STEP_QUEUED",
            summary="dependant queued with a dispatch intent",
            from_state=StepState.READY.value,
            to_state=StepState.QUEUED.value,
        )
        queued.append({"step_id": row["id"], "attempt": row["attempt"]})
    return queued
