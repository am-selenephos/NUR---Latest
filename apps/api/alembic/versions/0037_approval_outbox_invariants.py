"""One actionable approval per step, call-version binding, and outbox leases.

Two foundations the dispatcher will build on, so both land before it exists.

The pending-approval index shipped in 0036 keyed on
(owner, step, argument_digest). That prevents duplicate cards for the *same*
call while permitting two live cards for the same step with different digests —
which is the stale-approval problem rather than a fix for it. An owner could see
two actionable requests for one step and approve the one the plan had already
moved past. The invariant is one actionable approval per step, full stop.

`call_version` binds an approval to the plan revision that produced it. Tool key,
version and digest already bind the call; plan_version binds the *context*, so a
re-plan that happens to produce an identical call still invalidates the old
decision. Consent given against one plan is not consent against its successor.

Revision ID: 0037_approval_outbox_invariants
Revises: 0036_agentic_dispatch_outbox
"""

from __future__ import annotations

from alembic import op

revision = "0037_approval_outbox_invariants"
down_revision = "0036_agentic_dispatch_outbox"
branch_labels = None
depends_on = None

STATEMENTS = [
    # ── Approval: one actionable card per step ──
    "ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS plan_version integer NOT NULL DEFAULT 1",
    "ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS call_version text",
    # Backfill so the new index cannot fail on existing rows.
    # A digest rather than a concatenation: bounded length regardless of how
    # long a tool key becomes, and comparison is what this is for, not reading.
    "UPDATE agent_approvals SET call_version = 'cv:' || encode(sha256(convert_to("
    "plan_version || ':' || tool_key || ':' || tool_version || ':' || argument_digest, "
    "'UTF8')), 'hex') WHERE call_version IS NULL",
    "DROP INDEX IF EXISTS uq_agent_approval_pending",
    # The invariant: one PENDING approval per owner + step, regardless of digest.
    # A replacement must invalidate its predecessor rather than sit beside it.
    "CREATE UNIQUE INDEX uq_agent_approval_one_pending "
    "ON agent_approvals (owner_user_id, step_id) WHERE decision = 'PENDING'",
    "CREATE INDEX ix_agent_approval_call_version ON agent_approvals (step_id, call_version)",

    # ── Outbox: lease ownership ──
    # `state` already exists from 0036 with default RETRYABLE.
    "ALTER TABLE agent_dispatch_outbox ADD COLUMN IF NOT EXISTS claimed_by varchar(120)",
    "ALTER TABLE agent_dispatch_outbox ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz",
    "ALTER TABLE agent_dispatch_outbox ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz "
    "NOT NULL DEFAULT now()",
    # Claimable rows: RETRYABLE and due, or CLAIMED with a dead lease. The second
    # half is what stops a crashed dispatcher stranding work forever.
    "CREATE INDEX ix_agent_dispatch_claimable ON agent_dispatch_outbox "
    "(next_attempt_at) WHERE state IN ('RETRYABLE', 'CLAIMED')",
    "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state "
    "CHECK (state IN ('RETRYABLE', 'CLAIMED', 'SENT'))",
]


def upgrade() -> None:
    # asyncpg prepares each statement and a prepared statement holds one command.
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in [
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT IF EXISTS ck_agent_dispatch_state",
        "DROP INDEX IF EXISTS ix_agent_dispatch_claimable",
        "ALTER TABLE agent_dispatch_outbox DROP COLUMN IF EXISTS next_attempt_at",
        "ALTER TABLE agent_dispatch_outbox DROP COLUMN IF EXISTS lease_expires_at",
        "ALTER TABLE agent_dispatch_outbox DROP COLUMN IF EXISTS claimed_by",
        "DROP INDEX IF EXISTS ix_agent_approval_call_version",
        "DROP INDEX IF EXISTS uq_agent_approval_one_pending",
        "CREATE UNIQUE INDEX uq_agent_approval_pending "
        "ON agent_approvals (owner_user_id, step_id, argument_digest) "
        "WHERE decision = 'PENDING'",
        "ALTER TABLE agent_approvals DROP COLUMN IF EXISTS call_version",
        "ALTER TABLE agent_approvals DROP COLUMN IF EXISTS plan_version",
    ]:
        op.execute(statement)
