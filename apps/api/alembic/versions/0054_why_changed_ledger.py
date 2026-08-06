"""WhyChanged ledger — append-only change explanation table with forced RLS.

Implements directive §8.12: generic append-only change explanation contract for
belief, user-model claim, plan, recommendation, route policy, prompt, identity,
memory, and review strategy.

Revision ID: 0054_why_changed_ledger
Revises: 0053_email_lookup_role_hardening
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0054_why_changed_ledger"
down_revision = "0053_email_lookup_role_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create the why_changed_records table ────────────────────────────
    op.create_table(
        "why_changed_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),

        # What changed
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("previous_version", sa.String, nullable=True),
        sa.Column("new_version", sa.String, nullable=True),

        # How it changed
        sa.Column("change_class", sa.String, nullable=False),

        # Why it changed
        sa.Column("trigger", sa.String, nullable=False, server_default=""),
        sa.Column("supporting_evidence", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("counter_evidence", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("owner_correction", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Context at time of change
        sa.Column("model_version", sa.String, nullable=True),
        sa.Column("prompt_version", sa.String, nullable=True),
        sa.Column("policy_version", sa.String, nullable=True),

        # Actor
        sa.Column("actor", sa.String, nullable=False, server_default="system"),

        # Impact
        sa.Column("affected_future_behavior", sa.String, nullable=False, server_default=""),
        sa.Column("rollback_target", sa.String, nullable=True),

        # Timing
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── Indexes ────────────────────────────────────────────────────────
    op.create_index(
        "ix_why_changed_entity",
        "why_changed_records",
        ["owner_user_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_why_changed_occurred",
        "why_changed_records",
        ["owner_user_id", "occurred_at"],
    )

    # ── Forced RLS (§3 — cross-owner denial is a database invariant) ──
    op.execute("ALTER TABLE why_changed_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE why_changed_records FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY why_changed_owner_isolation ON why_changed_records
        USING (owner_user_id = current_setting('app.current_user_id')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS why_changed_owner_isolation ON why_changed_records")
    op.execute("ALTER TABLE why_changed_records DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_why_changed_occurred", table_name="why_changed_records")
    op.drop_index("ix_why_changed_entity", table_name="why_changed_records")
    op.drop_table("why_changed_records")
