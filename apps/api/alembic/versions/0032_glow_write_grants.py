"""Grant the app role write access to the two Glow ledger tables.

A database migrated from empty to head cannot award Glow. The first System
diagnostic fails with:

    InsufficientPrivilegeError: permission denied for table glow_transactions

`glow_transactions` and `glow_reward_events` are the only two tables in the
schema the app role can read but not write:

    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND NOT (has_table_privilege('nur_app', c.oid, 'INSERT')
               AND has_table_privilege('nur_app', c.oid, 'UPDATE'));
    -> glow_reward_events, glow_transactions

Every other owner-scoped table goes through `_owner_policies()` in 0026, which
grants and creates the RLS policies together. These two were created without it.

This never surfaced on the existing development database, which has the
privileges from an earlier manual grant, so only a genuinely fresh migration
chain reveals it — and a fresh deploy would have hit it on the first diagnostic.

Idempotent: the grants are safe to repeat, and each policy is dropped before it
is created so a database that already has them is unaffected.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_glow_write_grants"
down_revision = "0031_six_star_systems"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
UID = "current_setting('app.current_user_id', true)::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL AND "
    "current_setting('app.current_user_id', true) <> ''"
)

# glow_transactions is updated as balances settle; reward events are append-only
# and are deliberately not granted UPDATE.
TABLES = (
    ("glow_transactions", True),
    ("glow_reward_events", False),
)


def upgrade() -> None:
    for table, updatable in TABLES:
        privileges = "SELECT, INSERT, UPDATE" if updatable else "SELECT, INSERT"
        op.execute(f"GRANT {privileges} ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_select ON {table}")
        op.execute(
            f"CREATE POLICY p_{table}_owner_select ON {table} FOR SELECT TO {APP_ROLE} "
            f"USING ({HAS_USER} AND owner_user_id = {UID})"
        )
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_insert ON {table}")
        op.execute(
            f"CREATE POLICY p_{table}_owner_insert ON {table} FOR INSERT TO {APP_ROLE} "
            f"WITH CHECK ({HAS_USER} AND owner_user_id = {UID})"
        )
        if updatable:
            op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_update ON {table}")
            op.execute(
                f"CREATE POLICY p_{table}_owner_update ON {table} FOR UPDATE TO {APP_ROLE} "
                f"USING ({HAS_USER} AND owner_user_id = {UID}) "
                f"WITH CHECK ({HAS_USER} AND owner_user_id = {UID})"
            )

    # Fail loudly rather than leaving a database that looks migrated but cannot
    # award Glow.
    remaining = op.get_bind().execute(
        sa.text(
            "SELECT string_agg(c.relname, ', ') FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND c.relname IN ('glow_transactions', 'glow_reward_events') "
            "AND NOT has_table_privilege(:role, c.oid, 'INSERT')"
        ),
        {"role": APP_ROLE},
    ).scalar()
    if remaining:
        raise RuntimeError(f"app role still cannot insert into: {remaining}")


def downgrade() -> None:
    for table, updatable in TABLES:
        if updatable:
            op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_select ON {table}")
        op.execute(f"REVOKE SELECT, INSERT, UPDATE ON {table} FROM {APP_ROLE}")
