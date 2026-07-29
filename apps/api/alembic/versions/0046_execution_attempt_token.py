"""A per-claim execution token, so a stale worker cannot finish work it lost.

`worker_id` identifies *who* holds a step; it does not identify *which claim*.
A worker that claims a step, stalls past its lease, has the step reclaimed, and
then wakes up and writes SUCCEEDED would be accepted on a name match alone —
`worker_id` still equals its own name, and the state is still RUNNING because
the replacement worker put it back there. The completion of a dead attempt
would overwrite the live one.

`execution_attempt` is reissued on every claim and on every reclaim, so a
completion, failure or heartbeat write can require the token it was issued
under. A stale attempt's writes then match zero rows, which the caller can
detect and report rather than silently double-recording work.

Defaulted with `gen_random_uuid()` and NOT NULL: an existing step row must not
sit with a NULL token that any attempt would match. The default applies to
rows already present when this runs.

Revision ID: 0046_execution_attempt_token
Revises: 0045_tool_call_approval_binding
"""

from __future__ import annotations

from alembic import op

revision = "0046_execution_attempt_token"
down_revision = "0045_tool_call_approval_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_steps ADD COLUMN IF NOT EXISTS execution_attempt uuid "
        "NOT NULL DEFAULT gen_random_uuid()"
    )
    # Completion and heartbeat writes match on (id, execution_attempt); without
    # this the fencing predicate is a sequential scan on a hot path.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_steps_execution_attempt "
        "ON agent_steps (id, execution_attempt)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_steps_execution_attempt")
    op.execute("ALTER TABLE agent_steps DROP COLUMN IF EXISTS execution_attempt")
