"""Database-enforce claim_token shape on agent_dispatch_outbox.

`ck_agent_dispatch_state_shape` (0040) constrains claimed_by, lease_expires_at
and sent_at together with state, but claim_token — added afterward in 0042 —
was never added to it. The dispatcher fences every acknowledgement against the
token at the application layer (`mark_sent`/`mark_failed` require `state =
'CLAIMED' AND claim_token = :token`), but nothing stopped a CLAIMED or SENT row
existing in the database with no token at all, which is not a shape the
fencing logic can ever have produced through the ordinary path — only a
migration, a fix-up script, or a bug reaching the table directly.

The tightened CHECK:

  * RETRYABLE requires claimed_by, claim_token, lease_expires_at and sent_at
    all NULL — a row not currently held by any dispatcher carries no
    dispatcher's fencing token either.
  * CLAIMED requires claimed_by, claim_token and lease_expires_at all NOT NULL,
    sent_at NULL.
  * SENT requires claimed_by, claim_token and sent_at all NOT NULL. Previously
    SENT required only sent_at — claimed_by and claim_token were preserved by
    convention (`mark_sent` never clears them) but not required by the
    database, so a SENT row with no record of who sent it would have passed.

Revision ID: 0044_dispatch_claim_token_shape
Revises: 0043_invalidate_legacy_consent
"""

from __future__ import annotations

from alembic import op

revision = "0044_dispatch_claim_token_shape"
down_revision = "0043_invalidate_legacy_consent"
branch_labels = None
depends_on = None

OLD_CHECK = (
    "(state = 'RETRYABLE' AND sent_at IS NULL"
    "   AND claimed_by IS NULL AND lease_expires_at IS NULL)"
    " OR (state = 'CLAIMED' AND claimed_by IS NOT NULL"
    "   AND lease_expires_at IS NOT NULL AND sent_at IS NULL)"
    " OR (state = 'SENT' AND sent_at IS NOT NULL)"
)

NEW_CHECK = (
    "(state = 'RETRYABLE' AND claimed_by IS NULL AND claim_token IS NULL"
    "   AND lease_expires_at IS NULL AND sent_at IS NULL)"
    " OR (state = 'CLAIMED' AND claimed_by IS NOT NULL AND claim_token IS NOT NULL"
    "   AND lease_expires_at IS NOT NULL AND sent_at IS NULL)"
    " OR (state = 'SENT' AND claimed_by IS NOT NULL AND claim_token IS NOT NULL"
    "   AND sent_at IS NOT NULL)"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT ck_agent_dispatch_state_shape"
    )
    op.execute(
        f"ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state_shape "
        f"CHECK ({NEW_CHECK})"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE agent_dispatch_outbox DROP CONSTRAINT ck_agent_dispatch_state_shape"
    )
    op.execute(
        f"ALTER TABLE agent_dispatch_outbox ADD CONSTRAINT ck_agent_dispatch_state_shape "
        f"CHECK ({OLD_CHECK})"
    )
