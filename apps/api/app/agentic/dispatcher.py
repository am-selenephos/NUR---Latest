"""Consume committed dispatch intents and publish them.

The outbox exists because publishing inside a transaction is a bug waiting for a
rollback, and publishing after commit with no record strands the step if the
process dies in between. This is the half that reads what was committed.

The durability contract is deliberately modest and stated in one place:

    at-least-once delivery + step claim/idempotency = one durable execution effect

Nothing here claims exactly-once publication. A crash between `basic_publish`
returning and the SENT write committing produces a second delivery, and that is
fine precisely because `claim_step` makes the second one a no-op. Claiming more
than that would be a lie the recovery path cannot honour.

Two commits per row, not one. The lease claim commits before the broker call so
a crash mid-publish leaves a CLAIMED row with a lease that expires and is
reclaimed — rather than a row still marked RETRYABLE that a second dispatcher
picks up while the first is mid-flight.
"""

from __future__ import annotations

import uuid
import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.limits import DAGExecutionLimits, DAGValidationResult, validate_dag_limits
from app.db.rls import set_user_context

# Bounded backoff. Capped so a poison row is retried forever at a low rate
# rather than escalating into an unbounded wait nobody notices.
BACKOFF_SECONDS = (5, 30, 120, 600, 1800)
MAX_ATTEMPTS = len(BACKOFF_SECONDS)
LEASE_SECONDS = 120


def backoff_for(attempts: int) -> int:
    return BACKOFF_SECONDS[min(attempts, MAX_ATTEMPTS - 1)]


@dataclass(frozen=True)
class DispatchIntent:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    workflow_id: uuid.UUID
    step_id: uuid.UUID
    dispatch_key: str
    attempts: int
    traceparent: str | None
    claim_token: uuid.UUID


async def claim_intents(
    db: AsyncSession, *, dispatcher_id: str, limit: int = 20
) -> list[DispatchIntent]:
    """Atomically take ownership of due work.

    One statement covers both cases: RETRYABLE rows whose next attempt is due,
    and CLAIMED rows whose lease has expired. Reclaiming the second is what stops
    a crashed dispatcher stranding work forever, and doing it in the same claim
    means recovery is not a separate path that can rot unused.
    """
    rows = (
        await db.execute(
            text(
                "SELECT id, owner_user_id, workflow_id, step_id, dispatch_key, "
                "attempts, traceparent, claim_token "
                "FROM agent_ops_claim_dispatch(:dispatcher, :lease, :limit)"
            ),
            {"dispatcher": dispatcher_id, "lease": LEASE_SECONDS, "limit": limit},
        )
    ).mappings().all()
    return [DispatchIntent(**row) for row in rows]


async def mark_sent(db: AsyncSession, intent: DispatchIntent) -> bool:
    """Record acceptance, fenced by the claim token.

    `claimed_by` is an identity, not a token. A dispatcher that stalls, has its
    lease reclaimed by another, then wakes and writes SENT would be accepted on
    a name match alone. The token is reissued on every claim, so a stale
    acknowledgement updates zero rows and the caller can tell.
    """
    return bool(
        (
            await db.execute(
                text("SELECT agent_ops_mark_dispatch_sent(:id, :token)"),
                {"id": intent.id, "token": intent.claim_token},
            )
        ).scalar_one()
    )


async def mark_failed(db: AsyncSession, intent: DispatchIntent, error: str) -> bool:
    """Return the row to RETRYABLE with backoff, fenced by the claim token.

    The CHECK forbids RETRYABLE carrying claim metadata, so the lease and token
    are cleared here — which is also correct: the dispatcher no longer holds it.
    """
    return bool(
        (
            await db.execute(
                text(
                    "SELECT agent_ops_mark_dispatch_failed(:id, :token, :error, :backoff)"
                ),
                {
                    "id": intent.id,
                    "token": intent.claim_token,
                    "error": error[:200],
                    "backoff": backoff_for(intent.attempts),
                },
            )
        ).scalar_one()
    )


async def mark_cancelled(db: AsyncSession, intent: DispatchIntent, reason: str) -> bool:
    """Permanently refuse a claimed intent that fails runtime admission."""
    result = await db.execute(
        text(
            "UPDATE agent_dispatch_outbox SET state = 'CANCELLED', "
            "claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL, "
            "last_error = :reason "
            "WHERE id = :id AND owner_user_id = :owner "
            "AND state = 'CLAIMED' AND claim_token = :token"
        ),
        {
            "id": intent.id,
            "owner": intent.owner_user_id,
            "token": intent.claim_token,
            "reason": reason[:200],
        },
    )
    return bool(result.rowcount == 1)


async def load_dispatch_snapshot(db: AsyncSession, intent: DispatchIntent) -> dict[str, Any] | None:
    """Load the owner-scoped workflow and its complete DAG after a trusted claim."""
    await set_user_context(db, intent.owner_user_id)
    row = (
        await db.execute(
            text(
                "SELECT w.state AS workflow_state, s.state AS step_state, "
                "w.created_at, w.expires_at, w.cost_cents, w.context_manifest, "
                "COALESCE((SELECT jsonb_agg(jsonb_build_object("
                "'key', n.key, 'depends_on', n.depends_on, 'state', n.state) "
                "ORDER BY n.ordinal) FROM agent_steps n "
                "WHERE n.owner_user_id = w.owner_user_id AND n.workflow_id = w.id), "
                "'[]'::jsonb) AS actual_nodes "
                "FROM agent_workflows w JOIN agent_steps s "
                "ON s.workflow_id = w.id AND s.owner_user_id = w.owner_user_id "
                "WHERE w.id = :workflow AND s.id = :step AND w.owner_user_id = :owner"
            ),
            {
                "workflow": intent.workflow_id,
                "step": intent.step_id,
                "owner": intent.owner_user_id,
            },
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    manifest = dict(row["context_manifest"] or {})
    actual_nodes = [dict(item) for item in (row["actual_nodes"] or [])]
    actual_by_key = {str(item.get("key")): item for item in actual_nodes}
    planned_nodes = [dict(item) for item in manifest.get("dag_nodes", [])]
    nodes = planned_nodes or actual_nodes
    for node in nodes:
        actual = actual_by_key.get(str(node.get("key")), {})
        state = str(actual.get("state") or node.get("state") or "")
        node["state"] = state
        node["failed"] = state in {"FAILED", "CANCELLED"}
    return {
        "workflow_state": row["workflow_state"],
        "step_state": row["step_state"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "cost_cents": row["cost_cents"],
        "limits": manifest.get("dag_limits") or DAGExecutionLimits().model_dump(),
        "nodes": nodes,
    }


def validate_dispatch_snapshot(
    snapshot: dict[str, Any] | None,
    *,
    now: dt.datetime | None = None,
) -> DAGValidationResult:
    """Revalidate persisted DAG limits immediately before broker publication."""
    if snapshot is None:
        return DAGValidationResult(allowed=False, violations=["MISSING_RUNTIME_CONTEXT"])
    try:
        limits = DAGExecutionLimits.model_validate(snapshot.get("limits") or {})
    except Exception:
        return DAGValidationResult(allowed=False, violations=["INVALID_RUNTIME_LIMITS"])

    current = now or dt.datetime.now(dt.timezone.utc)
    created_at = snapshot.get("created_at")
    elapsed = 0.0
    if isinstance(created_at, dt.datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=dt.timezone.utc)
        elapsed = max(0.0, (current - created_at).total_seconds())
    workflow_state = str(snapshot.get("workflow_state") or "")
    step_state = str(snapshot.get("step_state") or "")
    cancellation_requested = workflow_state in {"CANCEL_REQUESTED", "CANCELLED"} or step_state == "CANCELLED"
    nodes = [dict(item) for item in snapshot.get("nodes") or []]
    result = validate_dag_limits(
        nodes,
        limits=limits,
        elapsed_seconds=elapsed,
        cancellation_requested=cancellation_requested,
    )
    violations = list(result.violations)
    expires_at = snapshot.get("expires_at")
    if isinstance(expires_at, dt.datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
        if expires_at <= current and "DEADLINE" not in violations:
            violations.append("DEADLINE")
    if int(snapshot.get("cost_cents") or 0) > limits.max_cost_cents and "MAX_COST" not in violations:
        violations.append("MAX_COST")
    if not nodes:
        violations.append("MISSING_DAG")
    return result.model_copy(update={"allowed": not violations, "violations": violations})


async def dispatch_once(
    db: AsyncSession,
    *,
    dispatcher_id: str,
    publish,
    limit: int = 20,
) -> dict:
    """Claim, commit the claim, publish, then record the outcome.

    `publish` is injected so the transport can be a real Celery `.delay` in
    production and a recording callable in tests, without the surrounding
    durability logic differing between them.
    """
    intents = await claim_intents(db, dispatcher_id=dispatcher_id, limit=limit)
    # Commit the lease before touching the broker. A crash during publish then
    # leaves a CLAIMED row that expires and is reclaimed, rather than a RETRYABLE
    # row a second dispatcher grabs while the first is still in flight.
    await db.commit()

    sent, failed, fenced, cancelled = [], [], [], []
    for intent in intents:
        snapshot = await load_dispatch_snapshot(db, intent)
        admission = validate_dispatch_snapshot(snapshot)
        if not admission.allowed:
            reason = "runtime admission refused: " + ",".join(admission.violations)
            if await mark_cancelled(db, intent, reason):
                cancelled.append(str(intent.id))
            else:
                fenced.append(str(intent.id))
            continue
        try:
            publish(
                str(intent.step_id),
                str(intent.owner_user_id),
                str(intent.workflow_id),
                intent.traceparent,
            )
        except Exception as error:  # noqa: BLE001 - recorded and retried
            if await mark_failed(db, intent, f"{type(error).__name__}: {error}"):
                failed.append(str(intent.id))
            else:
                fenced.append(str(intent.id))
        else:
            if await mark_sent(db, intent):
                sent.append(str(intent.id))
            else:
                # Our lease was reclaimed while we were publishing. The message
                # may still arrive; the step claim makes that harmless.
                fenced.append(str(intent.id))
    await db.commit()
    return {
        "claimed": len(intents),
        "sent": sent,
        "failed": failed,
        "fenced": fenced,
        "cancelled": cancelled,
    }
