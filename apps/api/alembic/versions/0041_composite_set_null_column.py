"""Column-specific ON DELETE SET NULL, and restore 0040's dropped FK on downgrade.

The composite audit FKs were declared `ON DELETE SET NULL` over
(step_id, workflow_id, owner_user_id). Plain SET NULL nulls *every* referencing
column, and workflow_id and owner_user_id are NOT NULL, so deleting a step would
fail rather than preserve the audit row.

It does not fail today, and the reason is worth recording: the legacy
single-column `(step_id) SET NULL` FK fires first, and once step_id is NULL the
composite constraint is satisfied without action under MATCH SIMPLE. The correct
behaviour is therefore an accident of a redundant-looking constraint. Dropping
that legacy FK as cleanup would turn every step deletion into an error.

PostgreSQL 16 supports a column list on the action, so the intent is stated
directly: null only the step reference, leave the ownership columns intact.

Also fixes 0040, whose upgrade dropped agent_approvals_step_id_fkey while its
downgrade never recreated it — a downgrade/upgrade cycle silently lost a
constraint.

Revision ID: 0041_composite_set_null_column
Revises: 0040_agentic_row_integrity
"""

from __future__ import annotations

from alembic import op

revision = "0041_composite_set_null_column"
down_revision = "0040_agentic_row_integrity"
branch_labels = None
depends_on = None

REBUILD = [
    ("agent_tool_calls", "fk_agent_tool_call_step_binding"),
    ("agent_run_events", "fk_agent_event_step_binding"),
]


def upgrade() -> None:
    for table, name in REBUILD:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
            "REFERENCES agent_steps (id, workflow_id, owner_user_id) "
            "ON DELETE SET NULL (step_id)"
        )


def downgrade() -> None:
    for table, name in REBUILD:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            "FOREIGN KEY (step_id, workflow_id, owner_user_id) "
            "REFERENCES agent_steps (id, workflow_id, owner_user_id) ON DELETE SET NULL"
        )
