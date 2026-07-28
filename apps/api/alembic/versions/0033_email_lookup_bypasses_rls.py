"""Restore the exact-email lookup and record why it cannot be fixed here.

`fn_active_user_id_by_email` resolves one account id from one exact email. Every
invite-by-email path goes through it: adding a recipient to a bounded Group NUR
room, sharing a Capsule, naming a Group Research verifier.

It is SECURITY DEFINER and owned by `nur_app`, and `users` carries FORCE ROW
LEVEL SECURITY. FORCE applies to the table owner too, so the function runs under
the caller's own owner-scoped policy and can only ever see the caller's own row.
Resolving anybody else returns NULL and the caller is told:

    404 No active NUR account exists for that exact email.

while the account plainly exists and is active. Reproduced on a database
migrated from empty and confirmed on the existing development database, so the
invite paths have been broken for every owner, not only on new installs.

`SET row_security = off` inside the function does not help. PostgreSQL refuses
it and says so directly:

    ERROR: query would be affected by row-level security policy for table "users"
    HINT:  To disable the policy for the table's owner, use
           ALTER TABLE NO FORCE ROW LEVEL SECURITY.

That was tried here and reverted; this migration is deliberately a no-op that
restores the original definition, so the chain stays linear and nothing claims a
fix that does not work.

Three real options remain, and each is an infrastructure decision rather than a
schema edit:

  1. Own the function with a dedicated BYPASSRLS role. Narrowest, and preserves
     FORCE everywhere. Needs a superuser to provision the role, which this
     migration role is not.
  2. Add a SELECT policy on `users` for `nur_app`. Rejected: a policy cannot be
     column-scoped, so it would expose every active user row to the app role to
     make one id lookup work.
  3. `ALTER TABLE users NO FORCE ROW LEVEL SECURITY`. Rejected: forced RLS is a
     stated invariant of this product.

Option 1 is the recommendation. It is left for a founder decision because it
provisions a new database role.
"""

from alembic import op

revision = "0033_email_lookup_bypasses_rls"
down_revision = "0032_glow_write_grants"
branch_labels = None
depends_on = None

BODY = "SELECT id FROM users WHERE email = lower(trim(em)) AND status = 'active'"
DEFINITION = (
    "CREATE OR REPLACE FUNCTION fn_active_user_id_by_email(em text) "
    "RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER AS $$" + BODY + "$$"
)


def upgrade() -> None:
    # Body validation runs under the migration role's RLS, which is the same
    # obstacle described above, so it is disabled for this statement only.
    op.execute("SET LOCAL check_function_bodies = off")
    op.execute(DEFINITION)


def downgrade() -> None:
    op.execute("SET LOCAL check_function_bodies = off")
    op.execute(DEFINITION)
