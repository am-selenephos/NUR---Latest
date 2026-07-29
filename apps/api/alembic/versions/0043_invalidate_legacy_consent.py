"""Invalidate every pre-existing actionable decision at this boundary, keeping
its provenance and reconciling the step it was blocking.

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

`invalidated_from` / `invalidated_at` / `invalidation_reason` preserve what the
row was before this ran. Overwriting `decision` with no record of the original
value would make an APPROVED row indistinguishable from a PENDING one after the
fact — the audit trail is exactly the thing an invalidation must not destroy.

Invalidating an actionable row out from under a WAITING_APPROVAL step leaves
that step with nothing to resume: no actionable card in the inbox, no path back
to QUEUED, no dispatch intent. This upgrade closes that hole in the same
transaction that opens it: every step left in WAITING_APPROVAL by this exact
invalidation pass is returned to QUEUED with one durable RETRYABLE dispatch
intent, so the ordinary runtime picks it back up, re-evaluates policy, and
`_ensure_approval_row` mints a fresh canonical PENDING approval from the step's
actual `input_refs` and the workflow's current `plan_version` — never from
`redacted_arguments`, which is display-only and already lossy.

The dispatch_key embeds a `reconcile:0043` marker together with the step's
current attempt count, which is already one higher than the attempt any prior
SENT intent for this step used (claiming a step increments `attempt` before it
can ever reach WAITING_APPROVAL) — so this key cannot collide with one that
dispatcher already marked SENT.

Order matters: the actionable unique index from 0042 cannot be created while
duplicate APPROVED rows exist, so it is dropped, the rows are invalidated, and
it is recreated. 0042 created it before invalidating anything, which happened to
work only because nothing had accumulated yet.

None of this took effect anywhere before now: `nur_admin`, the role every
migration runs as, lacked BYPASSRLS, and every one of these tables has FORCE ROW
LEVEL SECURITY — which Postgres applies to the table owner too. A migration
never sets `app.current_user_id`, so the original UPDATE here silently affected
zero rows in any environment, on top of whatever encoding bug it also had. The
role fix lives in role provisioning (conftest.py, bootstrap-dev.sh), not here —
granting BYPASSRLS requires actual superuser, which CREATEROLE does not confer.

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

    "ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS invalidated_from varchar(20)",
    "ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS invalidated_at timestamptz",
    "ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS invalidation_reason text",

    # Invalidate, preserving provenance; requeue whatever step that invalidation
    # stranded in WAITING_APPROVAL; give each requeued step exactly one durable
    # dispatch intent. One statement so a crash mid-way cannot invalidate consent
    # without also requeuing the step it was blocking.
    """
    WITH invalidated AS (
        UPDATE agent_approvals
           SET invalidated_from = decision,
               invalidated_at = now(),
               invalidation_reason = 'pre-canonical binding',
               decision = 'INVALIDATED'
         WHERE decision IN ('PENDING', 'APPROVED', 'EDITED')
        RETURNING step_id
    ),
    stranded AS (
        SELECT DISTINCT s.id, s.owner_user_id, s.workflow_id, s.attempt
          FROM agent_steps s
          JOIN invalidated i ON i.step_id = s.id
         WHERE s.state = 'WAITING_APPROVAL'
    ),
    requeued AS (
        UPDATE agent_steps s
           SET state = 'QUEUED', queued_at = now(), updated_at = now()
          FROM stranded st
         WHERE s.id = st.id
        RETURNING s.id, s.owner_user_id, s.workflow_id, s.attempt
    )
    INSERT INTO agent_dispatch_outbox (owner_user_id, workflow_id, step_id, dispatch_key, state)
    SELECT owner_user_id, workflow_id, id,
           id::text || ':reconcile:0043:' || attempt,
           'RETRYABLE'
      FROM requeued
    ON CONFLICT (dispatch_key) DO NOTHING
    """,

    "CREATE UNIQUE INDEX uq_agent_approval_one_actionable "
    "ON agent_approvals (owner_user_id, step_id) "
    "WHERE decision IN ('APPROVED', 'EDITED')",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Invalidation is not reversible: the rows' original decisions are recorded
    # in invalidated_from/at/reason for audit, not restored to actionable, and
    # restoring them would restore consent that was deliberately revoked. The
    # steps this pass requeued are not rewound to WAITING_APPROVAL either — they
    # may have progressed since, and guessing backwards is the same mistake as
    # guessing a plan version. The index and the provenance columns are recreated
    # so the schema shape round-trips.
    op.execute("DROP INDEX IF EXISTS uq_agent_approval_one_actionable")
    op.execute("ALTER TABLE agent_approvals DROP COLUMN IF EXISTS invalidation_reason")
    op.execute("ALTER TABLE agent_approvals DROP COLUMN IF EXISTS invalidated_at")
    op.execute("ALTER TABLE agent_approvals DROP COLUMN IF EXISTS invalidated_from")
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_approval_one_actionable "
        "ON agent_approvals (owner_user_id, step_id) "
        "WHERE decision IN ('APPROVED', 'EDITED')"
    )
