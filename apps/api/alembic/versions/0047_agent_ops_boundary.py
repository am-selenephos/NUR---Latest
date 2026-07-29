"""A least-privileged cross-owner boundary for dispatch and recovery.

The dispatcher and the recovery sweep are the only two operations in the Agency
Plane that legitimately span owners: a dispatcher claims whatever work is due,
and recovery reclaims whatever lease has expired, neither of which can enumerate
every owner first. Both previously ran as `nur_app` with no
`app.current_user_id` set — and `nur_app` correctly does not hold BYPASSRLS,
because it is the role that serves owner HTTP requests. Under FORCE ROW LEVEL
SECURITY that means both swept exactly zero rows, silently, in every
environment.

Two fixes were available and one of them is wrong. Granting BYPASSRLS to
`nur_app` would make every request-serving code path able to read every owner's
private data, to fix a background sweep — the blast radius is the entire
product. Running the sweep as the schema owner is the same mistake wearing a
different role name.

So the boundary is a small set of SECURITY DEFINER functions instead. They are
owned by `nur_admin` (which does hold BYPASSRLS), so their *bodies* see across
owners, while `nur_app` itself gains no new table privilege whatsoever. What
`nur_app` gains is permission to call four functions whose entire text is in
this migration and reviewable here.

What the boundary deliberately cannot do:

  * read Talk, Journal, Timeline, Memory, Omega, Insights or any other owner
    content — no function here references those tables at all;
  * return owner text of any kind. Every return value is an identifier, a
    state, an attempt count or a traceparent;
  * be widened by a caller's argument. No function interpolates a caller string
    into SQL, and none accepts an owner id as a scope parameter, so a forged
    owner identifier has nothing to forge against.

`SET search_path = pg_catalog, public` is fixed on every function. Without it, a
caller who can create objects in an earlier schema on the search path could
shadow `agent_dispatch_outbox` and have a BYPASSRLS-owned function operate on
their own table instead. `REVOKE ALL ... FROM PUBLIC` before the grant means the
default PUBLIC execute privilege on new functions is removed rather than left.

Revision ID: 0047_agent_ops_boundary
Revises: 0046_execution_attempt_token
"""

from __future__ import annotations

from alembic import op

revision = "0047_agent_ops_boundary"
down_revision = "0046_execution_attempt_token"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"

FUNCTIONS = [
    # ── Claim due dispatch work, across owners. ──
    """
    CREATE OR REPLACE FUNCTION agent_ops_claim_dispatch(
        p_dispatcher text, p_lease_seconds integer, p_limit integer
    )
    RETURNS TABLE (
        id uuid, owner_user_id uuid, workflow_id uuid, step_id uuid,
        dispatch_key varchar, attempts integer, traceparent varchar,
        claim_token uuid
    )
    LANGUAGE sql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
        WITH due AS (
            SELECT o.id FROM agent_dispatch_outbox o
             WHERE (o.state = 'RETRYABLE' AND o.next_attempt_at <= now())
                OR (o.state = 'CLAIMED' AND o.lease_expires_at < now())
             ORDER BY o.next_attempt_at
             LIMIT p_limit
             FOR UPDATE SKIP LOCKED
        )
        UPDATE agent_dispatch_outbox o
           SET state = 'CLAIMED',
               claimed_by = p_dispatcher,
               claim_token = gen_random_uuid(),
               lease_expires_at = now() + make_interval(secs => p_lease_seconds)
          FROM due
         WHERE o.id = due.id
        RETURNING o.id, o.owner_user_id, o.workflow_id, o.step_id,
                  o.dispatch_key, o.attempts, o.traceparent, o.claim_token;
    $$
    """,
    # ── Acknowledge a claimed row, fenced by its token. ──
    """
    CREATE OR REPLACE FUNCTION agent_ops_mark_dispatch_sent(
        p_id uuid, p_token uuid
    )
    RETURNS boolean
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
    DECLARE
        affected integer;
    BEGIN
        UPDATE agent_dispatch_outbox
           SET state = 'SENT', sent_at = now()
         WHERE id = p_id AND state = 'CLAIMED' AND claim_token = p_token;
        GET DIAGNOSTICS affected = ROW_COUNT;
        RETURN affected = 1;
    END;
    $$
    """,
    # ── Return a claimed row to RETRYABLE with backoff, fenced by its token. ──
    """
    CREATE OR REPLACE FUNCTION agent_ops_mark_dispatch_failed(
        p_id uuid, p_token uuid, p_error text, p_backoff integer
    )
    RETURNS boolean
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
    DECLARE
        affected integer;
    BEGIN
        UPDATE agent_dispatch_outbox
           SET state = 'RETRYABLE',
               claimed_by = NULL,
               claim_token = NULL,
               lease_expires_at = NULL,
               attempts = attempts + 1,
               last_error = left(p_error, 200),
               next_attempt_at = now() + make_interval(secs => p_backoff)
         WHERE id = p_id AND state = 'CLAIMED' AND claim_token = p_token;
        GET DIAGNOSTICS affected = ROW_COUNT;
        RETURN affected = 1;
    END;
    $$
    """,
    # ── Reclaim abandoned step leases, across owners.
    #    A new execution_attempt is minted so the stale worker that still holds
    #    the old one cannot complete or fail the step it no longer owns. ──
    """
    CREATE OR REPLACE FUNCTION agent_ops_reclaim_expired_steps(p_limit integer)
    RETURNS TABLE (step_id uuid, workflow_id uuid, owner_user_id uuid)
    LANGUAGE sql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
        WITH expired AS (
            SELECT s.id FROM agent_steps s
             WHERE s.state = 'RUNNING'
               AND s.lease_expires_at IS NOT NULL
               AND s.lease_expires_at < now()
             ORDER BY s.lease_expires_at
             LIMIT p_limit
             FOR UPDATE SKIP LOCKED
        )
        UPDATE agent_steps s
           SET state = 'QUEUED',
               worker_id = NULL,
               lease_expires_at = NULL,
               execution_attempt = gen_random_uuid(),
               updated_at = now()
          FROM expired
         WHERE s.id = expired.id
        RETURNING s.id, s.workflow_id, s.owner_user_id;
    $$
    """,
]

SIGNATURES = [
    "agent_ops_claim_dispatch(text, integer, integer)",
    "agent_ops_mark_dispatch_sent(uuid, uuid)",
    "agent_ops_mark_dispatch_failed(uuid, uuid, text, integer)",
    "agent_ops_reclaim_expired_steps(integer)",
]


def upgrade() -> None:
    for statement in FUNCTIONS:
        op.execute(statement)

    for signature in SIGNATURES:
        # PUBLIC holds EXECUTE on a new function by default. Revoke before
        # granting, so the privilege set is exactly what is intended rather
        # than "the default, plus what we added".
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP_ROLE}")


def downgrade() -> None:
    for signature in SIGNATURES:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
