"""Owner account export, session inventory, and scheduled deletion lifecycle.

Revision ID: 0056_account_privacy_lifecycle
Revises: 0055_hardness_learning_plane

Account deletion is intentionally two-phase. The owner loses access immediately,
then a leased worker performs idempotent object cleanup before deleting the user
row. The deletion request survives as a token-protected, non-PII receipt.
"""

from alembic import op

revision = "0056_account_privacy_lifecycle"
down_revision = "0055_hardness_learning_plane"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)


def _owner_policies(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY p_{table}_owner_select ON {table} FOR SELECT TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {OWNER_UUID})"
    )
    op.execute(
        f"CREATE POLICY p_{table}_owner_insert ON {table} FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({HAS_USER} AND owner_user_id = {OWNER_UUID})"
    )
    op.execute(
        f"CREATE POLICY p_{table}_owner_update ON {table} FOR UPDATE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {OWNER_UUID}) "
        f"WITH CHECK (owner_user_id = {OWNER_UUID})"
    )
    op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE account_deletion_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            account_ref varchar(32) NOT NULL UNIQUE,
            receipt_token_digest varchar(64) NOT NULL,
            status varchar(48) NOT NULL DEFAULT 'PENDING',
            requested_at timestamptz NOT NULL DEFAULT now(),
            purge_after timestamptz NOT NULL,
            cancelled_at timestamptz,
            purge_started_at timestamptz,
            purged_at timestamptz,
            lease_expires_at timestamptz,
            claim_token uuid,
            attempt_count integer NOT NULL DEFAULT 0,
            failure_code varchar(80),
            cleanup_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_account_deletion_request_status CHECK (
                status IN (
                    'PENDING', 'PURGING', 'CANCELLED', 'PURGED',
                    'PURGED_EXTERNAL_ACTION_REQUIRED'
                )
            ),
            CONSTRAINT ck_account_deletion_attempt_count CHECK (attempt_count >= 0)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_account_deletion_active_owner "
        "ON account_deletion_requests(owner_user_id) "
        "WHERE owner_user_id IS NOT NULL AND status IN ('PENDING','PURGING')"
    )
    op.execute(
        "CREATE INDEX ix_account_deletion_due "
        "ON account_deletion_requests(status,purge_after,lease_expires_at)"
    )

    op.execute(
        """
        CREATE TABLE account_cleanup_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            deletion_request_id uuid NOT NULL REFERENCES account_deletion_requests(id) ON DELETE CASCADE,
            owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            cleanup_kind varchar(48) NOT NULL,
            provider varchar(32),
            resource_ref text,
            resource_ref_hash varchar(64) NOT NULL,
            status varchar(24) NOT NULL DEFAULT 'PENDING',
            attempt_count integer NOT NULL DEFAULT 0,
            last_error_code varchar(80),
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_account_cleanup_resource UNIQUE (
                deletion_request_id, cleanup_kind, resource_ref_hash
            ),
            CONSTRAINT ck_account_cleanup_kind CHECK (
                cleanup_kind IN (
                    'LOCAL_OBJECT', 'EXTERNAL_OBJECT',
                    'EXTERNAL_BILLING_CUSTOMER', 'EXTERNAL_BILLING_SUBSCRIPTION'
                )
            ),
            CONSTRAINT ck_account_cleanup_status CHECK (
                status IN ('PENDING','DONE','BLOCKED','FAILED','CANCELLED')
            ),
            CONSTRAINT ck_account_cleanup_attempt_count CHECK (attempt_count >= 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_account_cleanup_request_status "
        "ON account_cleanup_items(deletion_request_id,status)"
    )

    _owner_policies("account_deletion_requests")
    _owner_policies("account_cleanup_items")

    op.execute(f"GRANT DELETE ON users TO {APP_ROLE}")
    op.execute(
        f"CREATE POLICY p_users_owner_delete ON users FOR DELETE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND id = {OWNER_UUID})"
    )

    op.execute(
        """
        CREATE FUNCTION fn_due_account_deletion_owners(batch_limit integer)
        RETURNS TABLE(owner_user_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public, pg_temp
        AS $$
            SELECT request.owner_user_id
            FROM account_deletion_requests AS request
            WHERE request.owner_user_id IS NOT NULL
              AND request.purge_after <= now()
              AND (
                  request.status = 'PENDING'
                  OR (
                      request.status = 'PURGING'
                      AND request.lease_expires_at IS NOT NULL
                      AND request.lease_expires_at <= now()
                  )
              )
            ORDER BY request.purge_after, request.id
            LIMIT LEAST(GREATEST(batch_limit, 1), 100)
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fn_due_account_deletion_owners(integer) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION fn_due_account_deletion_owners(integer) TO {APP_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION fn_account_deletion_receipt(request_uuid uuid, supplied_digest varchar)
        RETURNS TABLE(
            request_id uuid,
            status varchar,
            requested_at timestamptz,
            purge_after timestamptz,
            cancelled_at timestamptz,
            purged_at timestamptz,
            cleanup_summary jsonb
        )
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public, pg_temp
        AS $$
            SELECT
                request.id,
                request.status,
                request.requested_at,
                request.purge_after,
                request.cancelled_at,
                request.purged_at,
                request.cleanup_summary
            FROM account_deletion_requests AS request
            WHERE request.id = request_uuid
              AND request.receipt_token_digest = supplied_digest
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION fn_account_deletion_receipt(uuid,varchar) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION fn_account_deletion_receipt(uuid,varchar) TO {APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fn_account_deletion_receipt(uuid,varchar)")
    op.execute("DROP FUNCTION IF EXISTS fn_due_account_deletion_owners(integer)")
    op.execute("DROP POLICY IF EXISTS p_users_owner_delete ON users")
    op.execute(f"REVOKE DELETE ON users FROM {APP_ROLE}")
    for table in ("account_cleanup_items", "account_deletion_requests"):
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_select ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_update ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
