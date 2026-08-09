"""Owner Agent lifecycle, cancellation fencing, and deletion graph repair.

Revision ID: 0057_agent_owner_lifecycle
Revises: 0056_account_privacy_lifecycle
"""

from alembic import op

revision = "0057_agent_owner_lifecycle"
down_revision = "0056_account_privacy_lifecycle"
branch_labels = None
depends_on = None

OLD_OUTBOX_STATE = "CHECK (state IN ('RETRYABLE', 'CLAIMED', 'SENT'))"
NEW_OUTBOX_STATE = (
    "CHECK (state IN ('RETRYABLE', 'CLAIMED', 'SENT', 'CANCELLED'))"
)
OLD_OUTBOX_SHAPE = (
    "(state = 'RETRYABLE' AND claimed_by IS NULL AND claim_token IS NULL "
    "AND lease_expires_at IS NULL AND sent_at IS NULL) OR "
    "(state = 'CLAIMED' AND claimed_by IS NOT NULL AND claim_token IS NOT NULL "
    "AND lease_expires_at IS NOT NULL AND sent_at IS NULL) OR "
    "(state = 'SENT' AND claimed_by IS NOT NULL AND claim_token IS NOT NULL "
    "AND sent_at IS NOT NULL)"
)
NEW_OUTBOX_SHAPE = (
    f"{OLD_OUTBOX_SHAPE} OR "
    "(state = 'CANCELLED' AND claimed_by IS NULL AND claim_token IS NULL "
    "AND lease_expires_at IS NULL AND sent_at IS NULL)"
)


def upgrade() -> None:
    op.execute("ALTER TABLE agent_workflows ADD COLUMN request_id uuid")
    op.execute("ALTER TABLE agent_workflows ADD COLUMN request_digest varchar(64)")
    op.execute(
        "ALTER TABLE agent_workflows ADD COLUMN retry_of_workflow_id uuid "
        "REFERENCES agent_workflows(id) ON DELETE RESTRICT"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_workflow_owner_request "
        "ON agent_workflows(owner_user_id, request_id) WHERE request_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_agent_workflow_retry_lineage "
        "ON agent_workflows(owner_user_id, retry_of_workflow_id) "
        "WHERE retry_of_workflow_id IS NOT NULL"
    )
    op.execute("ALTER TABLE agent_policies ADD COLUMN version integer NOT NULL DEFAULT 1")
    op.execute(
        "ALTER TABLE agent_policies ADD CONSTRAINT ck_agent_policy_version "
        "CHECK (version >= 1)"
    )

    op.execute(
        "UPDATE capsule_access_events event SET actor_user_id = NULL "
        "WHERE actor_user_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM users WHERE users.id = event.actor_user_id)"
    )
    op.execute(
        "ALTER TABLE capsule_access_events ADD CONSTRAINT "
        "fk_capsule_access_actor_user FOREIGN KEY (actor_user_id) "
        "REFERENCES users(id) ON DELETE SET NULL"
    )

    op.execute(
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT ck_agent_dispatch_state_shape"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT ck_agent_dispatch_state"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state "
        f"{NEW_OUTBOX_STATE}"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state_shape "
        f"CHECK ({NEW_OUTBOX_SHAPE})"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agent_dispatch_outbox SET state = 'RETRYABLE' "
        "WHERE state = 'CANCELLED'"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT ck_agent_dispatch_state_shape"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT ck_agent_dispatch_state"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state "
        f"{OLD_OUTBOX_STATE}"
    )
    op.execute(
        "ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state_shape "
        f"CHECK ({OLD_OUTBOX_SHAPE})"
    )
    op.execute(
        "ALTER TABLE capsule_access_events DROP CONSTRAINT "
        "fk_capsule_access_actor_user"
    )
    op.execute("ALTER TABLE agent_policies DROP CONSTRAINT ck_agent_policy_version")
    op.execute("ALTER TABLE agent_policies DROP COLUMN version")
    op.execute("DROP INDEX ix_agent_workflow_retry_lineage")
    op.execute("DROP INDEX uq_agent_workflow_owner_request")
    op.execute("ALTER TABLE agent_workflows DROP COLUMN retry_of_workflow_id")
    op.execute("ALTER TABLE agent_workflows DROP COLUMN request_digest")
    op.execute("ALTER TABLE agent_workflows DROP COLUMN request_id")
