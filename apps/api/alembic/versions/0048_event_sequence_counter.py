"""A race-safe per-workflow event sequence allocator.

`COALESCE(MAX(sequence), 0) + 1` computed inside the INSERT is not safe under
concurrency, and the unique index on (workflow_id, sequence) is what makes that
visible rather than harmless. Two transactions appending an event to the same
workflow both read the same MAX — neither can see the other's uncommitted row —
both compute the same next value, and the second INSERT raises a unique
violation. In PostgreSQL that error aborts the whole transaction, so the domain
mutation the event was describing is rolled back too: a step that genuinely
executed reports as never having run, because the *ledger entry about it*
collided.

`event_seq` is a counter on the workflow row instead. Allocation is
`UPDATE ... SET event_seq = event_seq + 1 RETURNING event_seq`, which takes a row
lock: the second transaction blocks until the first commits and then reads the
committed value, so it receives a genuinely fresh number instead of a duplicate.
Different workflows touch different rows and never block each other.

Backfilled from each workflow's existing events so an append after this
migration continues the ledger rather than restarting it and colliding with
history.

Revision ID: 0048_event_sequence_counter
Revises: 0047_agent_ops_boundary
"""

from __future__ import annotations

from alembic import op

revision = "0048_event_sequence_counter"
down_revision = "0047_agent_ops_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_workflows ADD COLUMN IF NOT EXISTS event_seq integer "
        "NOT NULL DEFAULT 0"
    )
    # Continue existing ledgers rather than restarting at 1 and colliding with
    # the rows already there.
    op.execute(
        """
        UPDATE agent_workflows w
           SET event_seq = COALESCE(e.max_seq, 0)
          FROM (
              SELECT workflow_id, MAX(sequence) AS max_seq
                FROM agent_run_events GROUP BY workflow_id
          ) e
         WHERE e.workflow_id = w.id
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_workflows DROP COLUMN IF EXISTS event_seq")
