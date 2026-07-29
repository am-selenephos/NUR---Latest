"""Invalidate pre-canonical consent, enforce one actionable approval, add fencing.

Three changes that share a theme: a decision must be unambiguous about what it
authorises and who may act on it.

Approvals created before canonical call-version support carry no call_version, or
one computed from a DEFAULT plan_version rather than the workflow's real
revision. Their creation-time plan provenance is unknowable, so they are
invalidated rather than backfilled. Guessing a plan version would manufacture
consent that was never given.

The pending index already permits one PENDING row per step. Nothing prevented
several APPROVED rows accumulating, which puts the fail-closed loader into a
permanent deadlock: it refuses to choose, and no code path clears the extras.
A second partial unique index makes the state unreachable — but its creation
does not belong here. This migration's own invalidation only catches
`call_version IS NULL`, so a duplicate pair with a non-NULL legacy
call_version — exactly the shape that made the index necessary — would still
be sitting there when `CREATE UNIQUE INDEX` ran, and the migration would abort
with a unique violation before 0043 ever got a chance to invalidate it
correctly. 0043 already drops-invalidates-recreates in the right order and
with the right predicate (unconditional, not `call_version IS NULL`), so the
index's creation is owned there alone, immediately downstream, rather than
duplicated here where it can fail.

`claim_token` fences dispatcher acknowledgements. `claimed_by` is an identity,
not a token: a dispatcher that stalls, has its lease reclaimed, then wakes and
writes SENT would be accepted because the name still matches. A token issued per
claim makes a stale acknowledgement affect zero rows.

Revision ID: 0042_consent_and_fencing
Revises: 0041_composite_set_null_column
"""

from __future__ import annotations

from alembic import op

revision = "0042_consent_and_fencing"
down_revision = "0041_composite_set_null_column"
branch_labels = None
depends_on = None

STATEMENTS = [
    # Pre-canonical actionable consent cannot be trusted. History is preserved;
    # only its actionability is revoked. Narrower than 0043's later pass —
    # this one predates the discovery that the encoding mismatch made this
    # predicate match nothing in practice — but it is still correct as far as
    # it goes, and 0043 supersedes it unconditionally regardless.
    "UPDATE agent_approvals SET decision = 'INVALIDATED' "
    "WHERE decision IN ('PENDING', 'APPROVED', 'EDITED') AND call_version IS NULL",

    "ALTER TABLE agent_dispatch_outbox ADD COLUMN IF NOT EXISTS claim_token uuid",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE agent_dispatch_outbox DROP COLUMN IF EXISTS claim_token")
