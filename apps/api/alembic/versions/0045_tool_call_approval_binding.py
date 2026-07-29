"""Database-bind a tool call's approval_id to the same owner, workflow and step.

`agent_tool_calls.approval_id` has carried a single-column FK to
`agent_approvals(id)` since 0035, and the runtime has written it on every call
site since the approval_id-write fix. Neither is semantic binding: a single-
column FK only proves the referenced approval row exists somewhere, not that it
authorised *this* call. Nothing in the database stopped a tool call from
citing another owner's approval, or one bound to a different workflow or step,
as long as the id happened to exist.

The composite FK expresses the actual invariant: approval_id is null (auto-run,
denied-before-approval, or any path with no consent to cite) or it names a row
in `agent_approvals` that shares this call's owner, workflow and step. MATCH
SIMPLE — the only mode Postgres offers for a multi-column FK — treats any null
in the referencing tuple as "skip the check", not just approval_id specifically.
That is still exactly the intended semantics here: the only way
`agent_tool_calls.step_id` becomes null is the existing ON DELETE SET NULL from
a step's deletion, and deleting a step already CASCADE-deletes its approvals
(0040), which already SET NULLs `approval_id` through the pre-existing
single-column FK in the same cascade. The two nulls always arrive together, so
there is no window where step_id is null while approval_id still names a live,
uncompared approval.

Revision ID: 0045_tool_call_approval_binding
Revises: 0044_dispatch_claim_token_shape
"""

from __future__ import annotations

from alembic import op

revision = "0045_tool_call_approval_binding"
down_revision = "0044_dispatch_claim_token_shape"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE agent_approvals ADD CONSTRAINT uq_agent_approval_binding "
    "UNIQUE (id, owner_user_id, workflow_id, step_id)",
    "ALTER TABLE agent_tool_calls ADD CONSTRAINT fk_agent_tool_call_approval_binding "
    "FOREIGN KEY (approval_id, owner_user_id, workflow_id, step_id) "
    "REFERENCES agent_approvals (id, owner_user_id, workflow_id, step_id)",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE agent_tool_calls DROP CONSTRAINT IF EXISTS "
        "fk_agent_tool_call_approval_binding"
    )
    op.execute(
        "ALTER TABLE agent_approvals DROP CONSTRAINT IF EXISTS uq_agent_approval_binding"
    )
