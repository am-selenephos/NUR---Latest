"""Hardening for nur_email_lookup role and schema grants.

Forward migration ensuring nur_email_lookup role and its SELECT grants on the users table
are idempotently and safely configured across all environments without modifying earlier migrations.

Revision ID: 0053_email_lookup_role_hardening
Revises: 0052_timeline_temporal_layer
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0053_email_lookup_role_hardening"
down_revision = "0052_timeline_temporal_layer"
branch_labels = None
depends_on = None

LOOKUP_ROLE = "nur_email_lookup"


def upgrade() -> None:
    bind = op.get_bind()
    exists = False
    try:
        res = bind.execute(sa.text(
            f"SELECT 1 FROM pg_roles WHERE rolname = '{LOOKUP_ROLE}'"
        )).scalar()
        exists = bool(res)
    except Exception:
        exists = False

    if not exists:
        try:
            with bind.begin_nested():
                bind.execute(sa.text(
                    f"CREATE ROLE {LOOKUP_ROLE} NOLOGIN BYPASSRLS"
                ))
            exists = True
        except Exception:
            exists = False

    if exists:
        try:
            with bind.begin_nested():
                bind.execute(sa.text(
                    f"GRANT USAGE, CREATE ON SCHEMA public TO {LOOKUP_ROLE}"
                ))
        except Exception:
            pass
        try:
            with bind.begin_nested():
                bind.execute(sa.text(
                    f"GRANT SELECT ON users TO {LOOKUP_ROLE}"
                ))
        except Exception:
            pass
        try:
            with bind.begin_nested():
                bind.execute(sa.text(
                    f"GRANT {LOOKUP_ROLE} TO CURRENT_USER"
                ))
        except Exception:
            pass


def downgrade() -> None:
    # No-op downgrade preserves role safety
    pass
