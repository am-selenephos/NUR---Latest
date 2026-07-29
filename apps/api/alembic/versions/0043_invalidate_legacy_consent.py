"""Invalidate every pre-existing actionable decision at this boundary.

0042 tried to do this with `WHERE call_version IS NULL` and matched nothing:
0037 had already backfilled every NULL, using a different encoding from
canonical compute_call_version — `plan:tool:version:digest` against
`plan|tool|version|digest`. So the rows it claimed to invalidate kept a
call_version that looks canonical, is not, and can never match a recomputed one.

The correct treatment is not to reinterpret those values but to stop trusting
them. Every PENDING, APPROVED and EDITED row that exists at this boundary is
invalidated regardless of what its call_version says. Creation-time plan
provenance is unknowable, and a decision whose binding cannot be verified is not
consent.

Order matters: the actionable unique index from 0042 cannot be created while
duplicate APPROVED rows exist, so it is dropped, the rows are invalidated, and
it is recreated. 0042 created it before invalidating anything, which happened to
work only because nothing had accumulated yet.

Revision ID: 0043_invalidate_legacy_consent
Revises: 0042_consent_and_fencing
"""

from __future__ import annotations

from alembic import op

revision = "0043_invalidate_legacy_consent"
down_revision = "0042_consent_and_fencing"
branch_labels = None
depends_on = None

STATEMENTS = [
    "DROP INDEX IF EXISTS uq_agent_approval_one_actionable",
    # No predicate on call_version. Every actionable row, whatever it claims.
    "UPDATE agent_approvals SET decision = 'INVALIDATED' "
    "WHERE decision IN ('PENDING', 'APPROVED', 'EDITED')",
    "CREATE UNIQUE INDEX uq_agent_approval_one_actionable "
    "ON agent_approvals (owner_user_id, step_id) "
    "WHERE decision IN ('APPROVED', 'EDITED')",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Invalidation is not reversible: the rows' original decisions are gone by
    # design, and restoring them would restore consent that was deliberately
    # revoked. The index is recreated so the schema shape round-trips.
    op.execute("DROP INDEX IF EXISTS uq_agent_approval_one_actionable")
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_approval_one_actionable "
        "ON agent_approvals (owner_user_id, step_id) "
        "WHERE decision IN ('APPROVED', 'EDITED')"
    )
