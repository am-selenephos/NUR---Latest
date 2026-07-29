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
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
                """
                WITH due AS (
                    SELECT id FROM agent_dispatch_outbox
                     WHERE (state = 'RETRYABLE' AND next_attempt_at <= now())
                        OR (state = 'CLAIMED' AND lease_expires_at < now())
                     ORDER BY next_attempt_at
                     LIMIT :limit
                     FOR UPDATE SKIP LOCKED
                )
                UPDATE agent_dispatch_outbox o
                   SET state = 'CLAIMED',
                       claimed_by = :dispatcher,
                       lease_expires_at = now() + make_interval(secs => :lease)
                  FROM due
                 WHERE o.id = due.id
             RETURNING o.id, o.owner_user_id, o.workflow_id, o.step_id,
                       o.dispatch_key, o.attempts, o.traceparent
                """
            ),
            {"dispatcher": dispatcher_id, "lease": LEASE_SECONDS, "limit": limit},
        )
    ).mappings().all()
    return [DispatchIntent(**row) for row in rows]


async def mark_sent(db: AsyncSession, intent_id: uuid.UUID) -> None:
    """Record acceptance. claimed_by and lease are preserved so the row still
    says which dispatcher published it."""
    await db.execute(
        text(
            "UPDATE agent_dispatch_outbox SET state = 'SENT', sent_at = now() WHERE id = :id"
        ),
        {"id": intent_id},
    )


async def mark_failed(db: AsyncSession, intent: DispatchIntent, error: str) -> None:
    """Return the row to RETRYABLE with backoff.

    The CHECK forbids RETRYABLE carrying claim metadata, so the lease is cleared
    here — which is also correct: the dispatcher no longer holds it.
    """
    await db.execute(
        text(
            """
            UPDATE agent_dispatch_outbox
               SET state = 'RETRYABLE',
                   claimed_by = NULL,
                   lease_expires_at = NULL,
                   attempts = attempts + 1,
                   last_error = :error,
                   next_attempt_at = now() + make_interval(secs => :backoff)
             WHERE id = :id
            """
        ),
        {"id": intent.id, "error": error[:200], "backoff": backoff_for(intent.attempts)},
    )


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

    sent, failed = [], []
    for intent in intents:
        try:
            publish(
                str(intent.step_id),
                str(intent.owner_user_id),
                str(intent.workflow_id),
                intent.traceparent,
            )
        except Exception as error:  # noqa: BLE001 - recorded and retried
            await mark_failed(db, intent, f"{type(error).__name__}: {error}")
            failed.append(str(intent.id))
        else:
            await mark_sent(db, intent.id)
            sent.append(str(intent.id))
    await db.commit()
    return {"claimed": len(intents), "sent": sent, "failed": failed}
