"""Make exact-email sharing work on real installs without weakening FORCE RLS.

Revision ID: 0059_exact_email_lookup_runtime
Revises: 0058_agentic_insights_engine
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059_exact_email_lookup_runtime"
down_revision = "0058_agentic_insights_engine"
branch_labels = None
depends_on = None

LOOKUP_ROLE = "nur_email_lookup"
APP_ROLE = "nur_app"
MIGRATION_ROLE = "nur_admin"
FUNCTIONS = (
    (
        "fn_user_id_by_email(text)",
        "fn_user_id_by_email(em text)",
        "SELECT u.id FROM public.users AS u "
        "WHERE u.email = lower(btrim(em)) LIMIT 1",
    ),
    (
        "fn_active_user_id_by_email(text)",
        "fn_active_user_id_by_email(em text)",
        "SELECT u.id FROM public.users AS u "
        "WHERE u.email = lower(btrim(em)) AND u.status = 'active' LIMIT 1",
    ),
)


def _role_state(bind: sa.engine.Connection) -> tuple[bool, bool] | None:
    row = bind.execute(
        sa.text(
            "SELECT rolcanlogin, rolbypassrls FROM pg_roles WHERE rolname = :role"
        ),
        {"role": LOOKUP_ROLE},
    ).one_or_none()
    return None if row is None else (bool(row.rolcanlogin), bool(row.rolbypassrls))


def upgrade() -> None:
    bind = op.get_bind()
    role_state = _role_state(bind)
    is_member = bool(
        bind.execute(
            sa.text("SELECT pg_has_role(current_user, :role, 'MEMBER')"),
            {"role": LOOKUP_ROLE},
        ).scalar()
    ) if role_state is not None else False
    if role_state != (False, True) or not is_member:
        raise RuntimeError(
            "nur_email_lookup must exist as NOLOGIN BYPASSRLS and the migration "
            "role must be its member. Run infra/scripts/provision-email-lookup-role.sh "
            "as the PostgreSQL superuser, then retry this migration."
        )

    # Correct an unsafe grant made by the former provisioning script. The app
    # invokes the functions; it must never be able to SET ROLE to their owner.
    if bool(
        bind.execute(
            sa.text("SELECT pg_has_role(:app, :role, 'MEMBER')"),
            {"app": APP_ROLE, "role": LOOKUP_ROLE},
        ).scalar()
    ):
        op.execute(f"REVOKE {LOOKUP_ROLE} FROM {APP_ROLE}")
    op.execute(f"GRANT USAGE, CREATE ON SCHEMA public TO {LOOKUP_ROLE}")
    op.execute(f"REVOKE ALL PRIVILEGES ON TABLE public.users FROM {LOOKUP_ROLE}")
    op.execute(
        f"GRANT SELECT (id, email, status) ON TABLE public.users TO {LOOKUP_ROLE}"
    )

    for signature, declaration, body in FUNCTIONS:
        op.execute(
            f"CREATE OR REPLACE FUNCTION public.{declaration} RETURNS uuid "
            "LANGUAGE sql STABLE SECURITY DEFINER "
            "SET search_path = pg_catalog, public "
            f"AS $function${body}$function$"
        )
        op.execute(f"ALTER FUNCTION public.{signature} OWNER TO {LOOKUP_ROLE}")
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO {APP_ROLE}")

    # CREATE is needed only while transferring ownership. Keeping it would let
    # the lookup role create unrelated objects if somebody ever SET ROLEs to it.
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {LOOKUP_ROLE}")

    for signature, _, _ in FUNCTIONS:
        owner, secure, config = bind.execute(
            sa.text(
                "SELECT pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig "
                "FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' AND p.oid = CAST(:signature AS regprocedure)"
            ),
            {"signature": f"public.{signature}"},
        ).one()
        if owner != LOOKUP_ROLE or not secure or config != ["search_path=pg_catalog, public"]:
            raise RuntimeError(
                f"{signature} hardening did not persist: owner={owner}, "
                f"security_definer={secure}, config={config}"
            )

    # Deleting a Capsule recipient triggers two paths into the append-only
    # event: actor_user_id SET NULL and recipient grant CASCADE -> grant_id SET
    # NULL. PostgreSQL may run the actor update after deleting the grant but
    # before the grant_id action, so an immediate FK rejects a transaction that
    # is valid once both referential actions finish. Defer only that check.
    op.execute(
        "ALTER TABLE public.capsule_access_events ALTER CONSTRAINT "
        "capsule_access_events_grant_id_fkey DEFERRABLE INITIALLY DEFERRED"
    )


def downgrade() -> None:
    # 0034 already owns the active-only function with the lookup role. 0004's
    # broader Capsule lookup remains owned by the migration role before 0059.
    op.execute(f"GRANT CREATE ON SCHEMA public TO {LOOKUP_ROLE}")
    op.execute(
        f"ALTER FUNCTION public.fn_user_id_by_email(text) OWNER TO {MIGRATION_ROLE}"
    )
    op.execute(
        f"ALTER FUNCTION public.fn_active_user_id_by_email(text) OWNER TO {LOOKUP_ROLE}"
    )
    op.execute(
        "ALTER TABLE public.capsule_access_events ALTER CONSTRAINT "
        "capsule_access_events_grant_id_fkey NOT DEFERRABLE INITIALLY IMMEDIATE"
    )
