"""Outbox state invariants and composite ownership binding.

Two classes of hole, both of which a passing round-trip test walked straight
through.

An outbox row could be CLAIMED with a NULL lease_expires_at. Nothing rejects it,
and no lease-expiry query can ever reclaim it, so the step is stranded forever
in a state that looks healthy. The state column and the columns that give it
meaning have to be constrained together.

Ownership was enforced by independent foreign keys plus RLS. Neither expresses
"this child row's owner and workflow must match its parent's". A composite
unique key on the parent plus a composite foreign key from the child does
express exactly that, in the database, for every writer — including a migration
or a fix-up script that never passes through a service.

Composite FKs are used rather than triggers wherever the parent can carry a
composite unique key, because they are declarative and cost nothing at write
time beyond the index that already exists.

CLAIMED bookkeeping is deliberately preserved on SENT: claimed_by and
lease_expires_at are not cleared, so the record still says which worker
published it. The CHECK therefore constrains SENT only by requiring sent_at.

Revision ID: 0040_agentic_row_integrity
Revises: 0039_approval_binding_trigger
"""

from __future__ import annotations

from alembic import op

revision = "0040_agentic_row_integrity"
down_revision = "0039_approval_binding_trigger"
branch_labels = None
depends_on = None

STATEMENTS = [
    # ── Outbox state invariants ──
    "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state_shape CHECK ("
    "  (state = 'RETRYABLE' AND sent_at IS NULL"
    "     AND claimed_by IS NULL AND lease_expires_at IS NULL)"
    "  OR (state = 'CLAIMED' AND claimed_by IS NOT NULL"
    "     AND lease_expires_at IS NOT NULL AND sent_at IS NULL)"
    "  OR (state = 'SENT' AND sent_at IS NOT NULL)"
    ")",

    # ── Composite parents ──
    "ALTER TABLE agent_workflows ADD CONSTRAINT uq_agent_workflow_owner "
    "UNIQUE (id, owner_user_id)",
    "ALTER TABLE agent_steps ADD CONSTRAINT uq_agent_step_workflow_owner "
    "UNIQUE (id, workflow_id, owner_user_id)",

    # ── Composite children: workflow ownership ──
    "ALTER TABLE agent_steps ADD CONSTRAINT fk_agent_step_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_run_events ADD CONSTRAINT fk_agent_event_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_checkpoints ADD CONSTRAINT fk_agent_checkpoint_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_evaluations ADD CONSTRAINT fk_agent_evaluation_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_tool_calls ADD CONSTRAINT fk_agent_tool_call_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT fk_agent_dispatch_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_approvals ADD CONSTRAINT fk_agent_approval_workflow_owner "
    "FOREIGN KEY (workflow_id, owner_user_id) "
    "REFERENCES agent_workflows (id, owner_user_id) ON DELETE CASCADE",

    # ── Composite children: step must belong to the same workflow AND owner ──
    "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT fk_agent_dispatch_step_binding "
    "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
    "REFERENCES agent_steps (id, workflow_id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_approvals ADD CONSTRAINT fk_agent_approval_step_binding "
    "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
    "REFERENCES agent_steps (id, workflow_id, owner_user_id) ON DELETE CASCADE",
    "ALTER TABLE agent_tool_calls ADD CONSTRAINT fk_agent_tool_call_step_binding "
    "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
    "REFERENCES agent_steps (id, workflow_id, owner_user_id) ON DELETE SET NULL",
    "ALTER TABLE agent_run_events ADD CONSTRAINT fk_agent_event_step_binding "
    "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
    "REFERENCES agent_steps (id, workflow_id, owner_user_id) ON DELETE SET NULL",
    "ALTER TABLE agent_checkpoints ADD CONSTRAINT fk_agent_checkpoint_step_binding "
    "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
    "REFERENCES agent_steps (id, workflow_id, owner_user_id) ON DELETE CASCADE",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    # The single-column step FK is now subsumed by the composite binding; the
    # trigger from 0039 stays as defence in depth for the NULL-step case the
    # composite FK does not cover.
    op.execute("ALTER TABLE agent_approvals DROP CONSTRAINT IF EXISTS agent_approvals_step_id_fkey")


def downgrade() -> None:
    for name, table in [
        ("fk_agent_checkpoint_step_binding", "agent_checkpoints"),
        ("fk_agent_event_step_binding", "agent_run_events"),
        ("fk_agent_tool_call_step_binding", "agent_tool_calls"),
        ("fk_agent_approval_step_binding", "agent_approvals"),
        ("fk_agent_dispatch_step_binding", "agent_dispatch_outbox"),
        ("fk_agent_approval_workflow_owner", "agent_approvals"),
        ("fk_agent_dispatch_workflow_owner", "agent_dispatch_outbox"),
        ("fk_agent_tool_call_workflow_owner", "agent_tool_calls"),
        ("fk_agent_evaluation_workflow_owner", "agent_evaluations"),
        ("fk_agent_checkpoint_workflow_owner", "agent_checkpoints"),
        ("fk_agent_event_workflow_owner", "agent_run_events"),
        ("fk_agent_step_workflow_owner", "agent_steps"),
        ("uq_agent_step_workflow_owner", "agent_steps"),
        ("uq_agent_workflow_owner", "agent_workflows"),
        ("ck_agent_dispatch_state_shape", "agent_dispatch_outbox"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
