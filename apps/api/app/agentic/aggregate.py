"""One workflow state, derived from its steps, computed in exactly one place.

Runtime completion, approval rejection and approval waiting each used to carry
their own CASE statement over the same step counts, and they disagreed: the
runtime's had no CANCELLED branch at all, so a workflow every step of which had
been rejected stayed RUNNING forever; `decisions.decide()`'s reject path had
one, but it was never shared, so a fix to one was never a fix to the other.

The precedence, most urgent first:

  1. Any step FAILED -> FAILED. A hard failure outranks everything.
  2. Any step WAITING_APPROVAL -> WAITING_APPROVAL. The owner has something to
     decide, whatever else is also true.
  3. Any step NEEDS_REVISION -> NEEDS_REVISION. A revising step holds its
     subtree — dependants stay BLOCKED, since `unlock_dependants` only
     promotes on SUCCEEDED — so this is real, actionable work outstanding.
  4. Anything still active -> RUNNING. "Active" is PENDING, READY, QUEUED,
     RUNNING or VERIFYING, plus any BLOCKED step that can still, in principle,
     become READY. A BLOCKED step whose dependency is FAILED, CANCELLED or
     SKIPPED never will — `unlock_dependants` only promotes when every
     dependency SUCCEEDED — so counting it as active would zombie the
     workflow at RUNNING forever behind a dependency that will never resolve.
  5. Otherwise every step is SUCCEEDED, CANCELLED, SKIPPED, FAILED-already-
     handled-above, or a permanently-stuck BLOCKED: SUCCEEDED if every step is
     SUCCEEDED, else CANCELLED if any step is CANCELLED, else SUCCEEDED (an
     all-SKIPPED workflow completed with nothing left to do).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ACTIVE_STATES = ("PENDING", "READY", "QUEUED", "RUNNING", "VERIFYING")


async def aggregate_workflow(
    db: AsyncSession, *, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> str:
    """Recompute and persist the workflow's state from its steps. Returns it."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE state = 'FAILED') AS failed,
                  count(*) FILTER (WHERE state = 'WAITING_APPROVAL') AS waiting,
                  count(*) FILTER (WHERE state = 'NEEDS_REVISION') AS revising,
                  count(*) FILTER (WHERE state = ANY(:active)) AS active,
                  -- A BLOCKED step is still active only if it can, in principle,
                  -- still become READY: none of its declared dependencies has
                  -- already resolved into a state it can never recover from.
                  count(*) FILTER (
                    WHERE state = 'BLOCKED'
                      AND NOT EXISTS (
                        SELECT 1
                          FROM jsonb_array_elements_text(s.depends_on) AS dep(key)
                          JOIN agent_steps d
                            ON d.workflow_id = s.workflow_id AND d.key = dep.key
                         WHERE d.state IN ('FAILED', 'CANCELLED', 'SKIPPED')
                      )
                  ) AS blocked_recoverable,
                  count(*) FILTER (WHERE state = 'CANCELLED') AS cancelled,
                  count(*) FILTER (WHERE state = 'SUCCEEDED') AS succeeded,
                  count(*) AS total
                FROM agent_steps s
                WHERE workflow_id = :workflow AND owner_user_id = :owner
                """
            ),
            {"workflow": workflow_id, "owner": owner_user_id, "active": list(ACTIVE_STATES)},
        )
    ).mappings().one()

    if row["failed"]:
        state = "FAILED"
    elif row["waiting"]:
        state = "WAITING_APPROVAL"
    elif row["revising"]:
        state = "NEEDS_REVISION"
    elif row["active"] or row["blocked_recoverable"]:
        state = "RUNNING"
    elif row["total"] and row["succeeded"] == row["total"]:
        state = "SUCCEEDED"
    elif row["cancelled"]:
        state = "CANCELLED"
    else:
        state = "SUCCEEDED"

    await db.execute(
        text(
            "UPDATE agent_workflows SET state = :state, updated_at = now() "
            "WHERE id = :workflow AND owner_user_id = :owner"
        ),
        {"state": state, "workflow": workflow_id, "owner": owner_user_id},
    )
    return state
