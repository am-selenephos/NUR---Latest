"""Own the exact-email lookup with a role that is exempt from row security.

`fn_active_user_id_by_email` could only ever see the caller's own row, because
it is SECURITY DEFINER owned by `nur_app` and `users` carries FORCE ROW LEVEL
SECURITY — which applies to the table owner too. Every invite-by-email path
returned "No active NUR account exists for that exact email" for accounts that
plainly existed. 0033 documents the full diagnosis and the options.

This takes the narrowest of them. A dedicated role, `nur_email_lookup`, owns
this one function and nothing else. FORCE stays on `users`, `nur_app` keeps
exactly the privileges it had, and the only thing that gains an exemption is a
function whose entire body is:

    SELECT id FROM users WHERE email = lower(trim(em)) AND status = 'active'

Given one exact, already-known address it returns one opaque id or NULL. It
cannot enumerate, cannot return any other column, and cannot be called by anyone
who is not already authenticated — every caller still enforces its own
authorisation afterwards. The role has NOLOGIN, so nothing can connect as it.

The migration creates the role itself where it is permitted to — CI, and any
deployment that migrates as a superuser. Where the migration role may not create
roles, provision it once per database beforehand:

    CREATE ROLE nur_email_lookup NOLOGIN BYPASSRLS;
    GRANT nur_email_lookup TO <migration_role>;

`infra/scripts/provision-email-lookup-role.sh` does exactly that. If the role is
absent and cannot be created, this migration warns and skips rather than failing
the chain — the function keeps the behaviour it already had, and the warning
names the remedy.
"""

import warnings

import sqlalchemy as sa
from alembic import op

revision = "0034_email_lookup_role"
down_revision = "0033_email_lookup_bypasses_rls"
branch_labels = None
depends_on = None

LOOKUP_ROLE = "nur_email_lookup"
APP_ROLE = "nur_app"
BODY = "SELECT id FROM users WHERE email = lower(trim(em)) AND status = 'active'"
SIGNATURE = "fn_active_user_id_by_email(text)"


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": LOOKUP_ROLE}
    ).scalar()

    if not exists:
        # Where the migration role may create roles — CI, and any deployment
        # that migrates as a superuser — provision it here so the chain is
        # self-contained. Where it may not, fall through to the instruction
        # below rather than guessing.
        try:
            with bind.begin_nested():
                bind.execute(sa.text(
                    f"CREATE ROLE {LOOKUP_ROLE} NOLOGIN BYPASSRLS"
                ))
                bind.execute(sa.text(f"GRANT {LOOKUP_ROLE} TO CURRENT_USER"))
                bind.execute(sa.text(
                    f"GRANT USAGE, CREATE ON SCHEMA public TO {LOOKUP_ROLE}"
                ))
                bind.execute(sa.text(f"GRANT SELECT ON users TO {LOOKUP_ROLE}"))
            exists = True
        except Exception:
            exists = False

    if not exists:
        # Refusing outright was worse than the bug: it makes the whole chain
        # unrunnable for anyone migrating without role-creation rights, which
        # includes CI. The migration skips instead, loudly. Nothing regresses —
        # the function keeps the behaviour it already had — and the remedy is one
        # documented command away.
        warnings.warn(
            f"{LOOKUP_ROLE} does not exist and this role cannot create it, so "
            "exact-email lookup stays broken: invite-by-email, Capsule sharing "
            "and Group Research verifiers will report 'No active NUR account "
            "exists for that exact email' for accounts that do exist. Fix with "
            "infra/scripts/provision-email-lookup-role.sh, then re-run this "
            "migration.",
            RuntimeWarning,
            stacklevel=2,
        )
        return

    # The body reads `users`, and validating it runs under the migration role's
    # own row security, so validation is disabled for these statements only.
    op.execute("SET LOCAL check_function_bodies = off")
    op.execute(
        f"CREATE OR REPLACE FUNCTION {SIGNATURE.replace('(text)', '(em text)')} "
        f"RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER AS $${BODY}$$"
    )
    op.execute(f"ALTER FUNCTION {SIGNATURE} OWNER TO {LOOKUP_ROLE}")

    # Only the app role may call it; PUBLIC gets nothing.
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {APP_ROLE}")

    owner = bind.execute(sa.text(
        "SELECT r.rolname FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
        "WHERE p.proname = 'fn_active_user_id_by_email'"
    )).scalar()
    if owner != LOOKUP_ROLE:
        raise RuntimeError(f"function owner is {owner}, expected {LOOKUP_ROLE}")


def downgrade() -> None:
    op.execute("SET LOCAL check_function_bodies = off")
    op.execute(f"ALTER FUNCTION {SIGNATURE} OWNER TO {APP_ROLE}")
