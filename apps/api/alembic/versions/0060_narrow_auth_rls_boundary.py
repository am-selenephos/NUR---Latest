"""Replace forgeable broad auth-context policies with exact lookup boundaries.

Revision ID: 0060_narrow_auth_rls_boundary
Revises: 0059_exact_email_lookup_runtime
"""

from __future__ import annotations

from alembic import op

revision = "0060_narrow_auth_rls_boundary"
down_revision = "0059_exact_email_lookup_runtime"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

LOOKUP_FUNCTIONS = (
    (
        "fn_user_id_by_session(uuid)",
        "fn_user_id_by_session(p_session_id uuid)",
        "RETURNS uuid",
        "SELECT s.user_id FROM public.sessions AS s "
        "WHERE s.id = p_session_id LIMIT 1",
    ),
    (
        "fn_user_id_by_password_reset_digest(text)",
        "fn_user_id_by_password_reset_digest(p_digest text)",
        "RETURNS uuid",
        "SELECT c.user_id FROM public.password_reset_challenges AS c "
        "WHERE c.token_digest = p_digest LIMIT 1",
    ),
    (
        "fn_active_user_ids(integer)",
        "fn_active_user_ids(p_limit integer)",
        "RETURNS TABLE (owner_user_id uuid)",
        "SELECT u.id FROM public.users AS u WHERE u.status = 'active' "
        "ORDER BY u.created_at, u.id LIMIT greatest(1, least(p_limit, 100))",
    ),
)


def _owner_insert(table: str, name: str, column: str) -> None:
    op.execute(
        f"CREATE POLICY {name} ON {table} FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({HAS_USER} AND {column} = {OWNER_UUID})"
    )


def upgrade() -> None:
    for policy, table in (
        ("p_users_auth_select", "users"),
        ("p_users_auth_insert", "users"),
        ("p_profiles_auth_insert", "profiles"),
        ("p_sessions_auth_select", "sessions"),
        ("p_sessions_auth_insert", "sessions"),
        ("p_sessions_auth_update", "sessions"),
        ("p_orbits_auth_insert", "orbits"),
        ("p_consent_auth_insert", "consent_records"),
        ("p_password_reset_auth_select", "password_reset_challenges"),
        ("p_password_reset_auth_insert", "password_reset_challenges"),
        ("p_password_reset_auth_update", "password_reset_challenges"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")

    _owner_insert("users", "p_users_exact_owner_insert", "id")
    _owner_insert("profiles", "p_profiles_exact_owner_insert", "user_id")
    _owner_insert("sessions", "p_sessions_exact_owner_insert", "user_id")
    # p_orbits_owner_insert already exists from 0003 and has this exact scope.
    _owner_insert("consent_records", "p_consent_exact_owner_insert", "user_id")
    _owner_insert(
        "password_reset_challenges",
        "p_password_reset_owner_insert",
        "user_id",
    )
    op.execute(
        f"CREATE POLICY p_password_reset_owner_select ON password_reset_challenges "
        f"FOR SELECT TO {APP_ROLE} USING ({HAS_USER} AND user_id = {OWNER_UUID})"
    )
    op.execute(
        f"CREATE POLICY p_password_reset_owner_update ON password_reset_challenges "
        f"FOR UPDATE TO {APP_ROLE} USING ({HAS_USER} AND user_id = {OWNER_UUID}) "
        f"WITH CHECK (user_id = {OWNER_UUID})"
    )

    op.execute("DROP POLICY IF EXISTS p_audit_insert ON audit_events")
    op.execute(
        f"CREATE POLICY p_audit_insert ON audit_events FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK (actor_user_id IS NULL OR "
        f"({HAS_USER} AND actor_user_id = {OWNER_UUID}))"
    )

    for signature, declaration, returns, body in LOOKUP_FUNCTIONS:
        op.execute(
            f"CREATE OR REPLACE FUNCTION public.{declaration} {returns} "
            "LANGUAGE sql STABLE SECURITY DEFINER "
            "SET search_path = pg_catalog, public "
            f"AS $function${body}$function$"
        )
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO {APP_ROLE}")


def downgrade() -> None:
    for signature, _, _, _ in LOOKUP_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{signature}")

    for policy, table in (
        ("p_users_exact_owner_insert", "users"),
        ("p_profiles_exact_owner_insert", "profiles"),
        ("p_sessions_exact_owner_insert", "sessions"),
        ("p_consent_exact_owner_insert", "consent_records"),
        ("p_password_reset_owner_insert", "password_reset_challenges"),
        ("p_password_reset_owner_select", "password_reset_challenges"),
        ("p_password_reset_owner_update", "password_reset_challenges"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")

    auth_ctx = "current_setting('app.auth_context', true) = 'on'"
    op.execute(
        f"CREATE POLICY p_users_auth_select ON users FOR SELECT TO {APP_ROLE} "
        f"USING ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_users_auth_insert ON users FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_profiles_auth_insert ON profiles FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_sessions_auth_select ON sessions FOR SELECT TO {APP_ROLE} "
        f"USING ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_sessions_auth_insert ON sessions FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_sessions_auth_update ON sessions FOR UPDATE TO {APP_ROLE} "
        f"USING ({auth_ctx}) WITH CHECK ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_orbits_auth_insert ON orbits FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({auth_ctx})"
    )
    op.execute(
        f"CREATE POLICY p_consent_auth_insert ON consent_records FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({auth_ctx})"
    )
    for action in ("SELECT", "INSERT", "UPDATE"):
        op.execute(
            f"CREATE POLICY p_password_reset_auth_{action.lower()} "
            f"ON password_reset_challenges FOR {action} TO {APP_ROLE} "
            + (f"USING ({auth_ctx}) WITH CHECK ({auth_ctx})" if action == "UPDATE" else (
                f"USING ({auth_ctx})" if action == "SELECT" else f"WITH CHECK ({auth_ctx})"
            ))
        )
    op.execute("DROP POLICY IF EXISTS p_audit_insert ON audit_events")
    op.execute(
        f"CREATE POLICY p_audit_insert ON audit_events FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({auth_ctx} OR ({HAS_USER} AND "
        f"(actor_user_id IS NULL OR actor_user_id = {OWNER_UUID})))"
    )
