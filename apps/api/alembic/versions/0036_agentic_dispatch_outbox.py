"""Durable dispatch outbox and approval/policy uniqueness.

Enqueueing to Celery inside a transaction is a correctness bug waiting for a
rollback: the broker has no idea the database changed its mind, so the worker
runs against state that was never committed. Conversely, publishing after commit
without a record means a crash in that window strands the step forever — the
approval says QUEUED and nothing is coming.

The outbox closes both. The approval decision, the step transition and the
dispatch intent commit in one transaction; a separate dispatcher publishes what
is committed. A crash before publishing leaves a RETRYABLE row, not silence.

`dispatch_key` is unique, so two dispatcher runs cannot publish the same logical
step attempt twice.

Revision ID: 0036_agentic_dispatch_outbox
Revises: 0035_agentic_spine
"""

from __future__ import annotations

from alembic import op

revision = "0036_agentic_dispatch_outbox"
down_revision = "0035_agentic_spine"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
UID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_UID = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

STATEMENTS = [
    """
    CREATE TABLE agent_dispatch_outbox (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
        step_id uuid NOT NULL REFERENCES agent_steps(id) ON DELETE CASCADE,
        dispatch_key varchar(220) NOT NULL,
        state varchar(16) NOT NULL DEFAULT 'RETRYABLE',
        attempts integer NOT NULL DEFAULT 0,
        last_error varchar(200),
        traceparent varchar(64),
        created_at timestamptz NOT NULL DEFAULT now(),
        sent_at timestamptz
    )
    """,
    # One row per logical step attempt. Two dispatchers racing cannot both
    # publish; the loser violates this and rolls back its own claim.
    "CREATE UNIQUE INDEX uq_agent_dispatch_key ON agent_dispatch_outbox (dispatch_key)",
    "CREATE INDEX ix_agent_dispatch_pending ON agent_dispatch_outbox (state, created_at) "
    "WHERE state = 'RETRYABLE'",

    # One live pending approval per owner + step + effective digest. Concurrent
    # workers reaching WAITING_APPROVAL cannot stack duplicate inbox cards.
    "CREATE UNIQUE INDEX uq_agent_approval_pending "
    "ON agent_approvals (owner_user_id, step_id, argument_digest) "
    "WHERE decision = 'PENDING'",

    # Deterministic policy scope: exactly one row per level.
    "CREATE UNIQUE INDEX uq_agent_policy_account ON agent_policies (owner_user_id) "
    "WHERE orbit_id IS NULL AND project_id IS NULL",
    "CREATE UNIQUE INDEX uq_agent_policy_orbit ON agent_policies (owner_user_id, orbit_id) "
    "WHERE orbit_id IS NOT NULL AND project_id IS NULL",
    "CREATE UNIQUE INDEX uq_agent_policy_project ON agent_policies (owner_user_id, project_id) "
    "WHERE project_id IS NOT NULL",

    # Permission and auto-run are different questions and must not share a
    # column. `allowed_tools` previously decided both what may be offered for
    # approval and what may run unattended.
    "ALTER TABLE agent_policies ADD COLUMN permitted_tools jsonb NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE agent_policies ADD COLUMN auto_run_tools jsonb NOT NULL DEFAULT '[]'::jsonb",
]


def upgrade() -> None:
    # asyncpg prepares each statement and a prepared statement holds one command.
    for statement in STATEMENTS:
        op.execute(statement.strip())

    op.execute("ALTER TABLE agent_dispatch_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_dispatch_outbox FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY agent_dispatch_outbox_owner ON agent_dispatch_outbox "
        f"USING ({HAS_UID} AND owner_user_id = {UID}) "
        f"WITH CHECK ({HAS_UID} AND owner_user_id = {UID})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON agent_dispatch_outbox TO {APP_ROLE}")

    # Existing allowed_tools becomes the permitted set, not the auto-run set.
    # Migrating it the other way would silently widen unattended execution for
    # every policy that already exists.
    op.execute("UPDATE agent_policies SET permitted_tools = allowed_tools")


def downgrade() -> None:
    for statement in [
        "DROP TABLE IF EXISTS agent_dispatch_outbox CASCADE",
        "DROP INDEX IF EXISTS uq_agent_approval_pending",
        "DROP INDEX IF EXISTS uq_agent_policy_account",
        "DROP INDEX IF EXISTS uq_agent_policy_orbit",
        "DROP INDEX IF EXISTS uq_agent_policy_project",
        "ALTER TABLE agent_policies DROP COLUMN IF EXISTS permitted_tools",
        "ALTER TABLE agent_policies DROP COLUMN IF EXISTS auto_run_tools",
    ]:
        op.execute(statement)
