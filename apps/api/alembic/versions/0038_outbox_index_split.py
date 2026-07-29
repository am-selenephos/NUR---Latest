"""Split the outbox claim indexes and constrain pending approvals.

One index on next_attempt_at served both the due-retry scan and the dead-lease
reclaim. Those are different queries: retry filters RETRYABLE by next_attempt_at,
reclaim filters CLAIMED by lease_expires_at. A single index makes the reclaim
path a filter over the wrong column, and — worse — implies recovery was an
afterthought rather than a designed path.

The approval CHECKs make the actionable invariant enforceable rather than
conventional: a PENDING row without a step or a call_version is not something a
service should be able to write, because the runtime would treat it as an
actionable card it cannot bind to a call.

Revision ID: 0038_outbox_index_split
Revises: 0037_approval_outbox_invariants
"""

from __future__ import annotations

from alembic import op

revision = "0038_outbox_index_split"
down_revision = "0037_approval_outbox_invariants"
branch_labels = None
depends_on = None

STATEMENTS = [
    "DROP INDEX IF EXISTS ix_agent_dispatch_claimable",
    "DROP INDEX IF EXISTS ix_agent_dispatch_pending",
    # Due retries: RETRYABLE ordered by when they may next be attempted.
    "CREATE INDEX ix_agent_dispatch_retryable ON agent_dispatch_outbox "
    "(next_attempt_at) WHERE state = 'RETRYABLE'",
    # Dead leases: CLAIMED ordered by when the lease expired.
    "CREATE INDEX ix_agent_dispatch_claimed_lease ON agent_dispatch_outbox "
    "(lease_expires_at) WHERE state = 'CLAIMED'",

    # A PENDING approval the runtime cannot bind to a call is not actionable.
    "ALTER TABLE agent_approvals ADD CONSTRAINT ck_agent_approval_pending_bound "
    "CHECK (decision <> 'PENDING' OR (step_id IS NOT NULL AND call_version IS NOT NULL))",
    "ALTER TABLE agent_approvals ADD CONSTRAINT ck_agent_approval_plan_version "
    "CHECK (plan_version >= 1)",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in [
        "ALTER TABLE agent_approvals DROP CONSTRAINT IF EXISTS ck_agent_approval_plan_version",
        "ALTER TABLE agent_approvals DROP CONSTRAINT IF EXISTS ck_agent_approval_pending_bound",
        "DROP INDEX IF EXISTS ix_agent_dispatch_claimed_lease",
        "DROP INDEX IF EXISTS ix_agent_dispatch_retryable",
        "CREATE INDEX ix_agent_dispatch_claimable ON agent_dispatch_outbox "
        "(next_attempt_at) WHERE state IN ('RETRYABLE', 'CLAIMED')",
    ]:
        op.execute(statement)
