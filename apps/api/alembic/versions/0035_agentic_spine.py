"""Agency Plane durable spine, owner-scoped under forced RLS.

FORCE ROW LEVEL SECURITY applies to the table owner too, which is the point: an
agent worker connecting as the app role cannot read across owners even if a
query forgets its filter. Every table here carries `owner_user_id` and a policy
keyed on `app.current_user_id`, matching the idiom established in 0028.

`agent_run_events` is deliberately INSERT and SELECT only — no UPDATE, no DELETE
grant. An audit trail that can be edited is a status field. Postgres enforces
that here rather than trusting every future service to be careful.

Revision ID: 0035_agentic_spine
Revises: 0034_email_lookup_role
"""

from __future__ import annotations

from alembic import op

revision = "0035_agentic_spine"
down_revision = "0034_email_lookup_role"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
UID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_UID = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

# Every table except the append-only ledger gets full owner CRUD.
OWNER_TABLES = (
    "agent_workflows",
    "agent_steps",
    "agent_approvals",
    "agent_checkpoints",
    "agent_tool_calls",
    "agent_policies",
    "agent_evaluations",
)
APPEND_ONLY = "agent_run_events"

DDL = """
CREATE TABLE agent_workflows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind varchar(64) NOT NULL,
    title varchar(400) NOT NULL,
    objective text NOT NULL,
    state varchar(24) NOT NULL DEFAULT 'DRAFT',
    plan_version integer NOT NULL DEFAULT 1,
    trigger_kind varchar(64),
    trigger_ref uuid,
    initiative_level varchar(16) NOT NULL DEFAULT 'SUGGEST',
    context_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    success_criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
    scope varchar(32) NOT NULL DEFAULT 'PRIVATE',
    orbit_id uuid REFERENCES orbits(id) ON DELETE SET NULL,
    project_id uuid REFERENCES am_projects(id) ON DELETE SET NULL,
    budget_cents integer NOT NULL DEFAULT 0,
    cost_cents integer NOT NULL DEFAULT 0,
    max_risk_class varchar(24) NOT NULL DEFAULT 'R1_PRIVATE_DRAFT',
    trace_id varchar(64),
    failure_code varchar(64),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_workflows_owner_state ON agent_workflows (owner_user_id, state);

CREATE TABLE agent_steps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    key varchar(120) NOT NULL,
    state varchar(24) NOT NULL DEFAULT 'PENDING',
    depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
    role varchar(64) NOT NULL,
    tool_key varchar(120),
    tool_version varchar(32),
    risk_class varchar(24) NOT NULL DEFAULT 'R0_READ_ONLY',
    requested_capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
    approval_required boolean NOT NULL DEFAULT true,
    provider varchar(48),
    model varchar(80),
    input_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb,
    verification_verdict varchar(32),
    attempt integer NOT NULL DEFAULT 0,
    idempotency_key varchar(200),
    worker_id varchar(120),
    lease_expires_at timestamptz,
    timeout_seconds integer,
    budget_cents integer NOT NULL DEFAULT 0,
    cost_cents integer NOT NULL DEFAULT 0,
    failure_code varchar(64),
    trace_id varchar(64),
    artifact_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    queued_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_agent_steps_workflow_key UNIQUE (workflow_id, key)
);
CREATE INDEX ix_agent_steps_workflow_state ON agent_steps (workflow_id, state);
CREATE INDEX ix_agent_steps_owner_lease ON agent_steps (owner_user_id, lease_expires_at);
-- One live claim per idempotency key: duplicate queue delivery cannot start the
-- same unit of work twice.
CREATE UNIQUE INDEX uq_agent_steps_idempotency
    ON agent_steps (owner_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE agent_approvals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(id) ON DELETE CASCADE,
    tool_key varchar(120) NOT NULL,
    tool_version varchar(32) NOT NULL,
    argument_digest varchar(71) NOT NULL,
    redacted_arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
    rationale text NOT NULL,
    expected_result text,
    risk_class varchar(24) NOT NULL,
    reversible boolean NOT NULL DEFAULT true,
    scope_summary text,
    cost_ceiling_cents integer NOT NULL DEFAULT 0,
    decision varchar(20) NOT NULL DEFAULT 'PENDING',
    decided_at timestamptz,
    decided_note text,
    edited_arguments jsonb,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_approvals_owner_decision ON agent_approvals (owner_user_id, decision);

CREATE TABLE agent_run_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(id) ON DELETE SET NULL,
    sequence integer NOT NULL,
    event_type varchar(64) NOT NULL,
    from_state varchar(24),
    to_state varchar(24),
    summary text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor varchar(32) NOT NULL DEFAULT 'SYSTEM',
    trace_id varchar(64),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ix_agent_run_events_workflow_seq
    ON agent_run_events (workflow_id, sequence);

CREATE TABLE agent_checkpoints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(id) ON DELETE CASCADE,
    kind varchar(32) NOT NULL,
    attempt integer NOT NULL DEFAULT 0,
    state_blob jsonb NOT NULL DEFAULT '{}'::jsonb,
    redacted boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_checkpoints_workflow_step ON agent_checkpoints (workflow_id, step_id);

CREATE TABLE agent_tool_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(id) ON DELETE SET NULL,
    approval_id uuid REFERENCES agent_approvals(id) ON DELETE SET NULL,
    tool_key varchar(120) NOT NULL,
    tool_version varchar(32) NOT NULL,
    risk_class varchar(24) NOT NULL,
    argument_digest varchar(71) NOT NULL,
    redacted_arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
    outcome varchar(24) NOT NULL,
    denial_reason varchar(120),
    idempotency_key varchar(200),
    duration_ms integer,
    cost_cents integer NOT NULL DEFAULT 0,
    trace_id varchar(64),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_tool_calls_owner_tool ON agent_tool_calls (owner_user_id, tool_key);

CREATE TABLE agent_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    orbit_id uuid REFERENCES orbits(id) ON DELETE CASCADE,
    project_id uuid REFERENCES am_projects(id) ON DELETE CASCADE,
    initiative_level varchar(16) NOT NULL DEFAULT 'SUGGEST',
    max_risk_class varchar(24) NOT NULL DEFAULT 'R1_PRIVATE_DRAFT',
    allowed_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
    denied_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
    daily_budget_cents integer NOT NULL DEFAULT 0,
    max_proposals_per_day integer NOT NULL DEFAULT 3,
    cooldown_minutes integer NOT NULL DEFAULT 180,
    quiet_hours jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_policies_owner_scope
    ON agent_policies (owner_user_id, orbit_id, project_id);

CREATE TABLE agent_evaluations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workflow_id uuid NOT NULL REFERENCES agent_workflows(id) ON DELETE CASCADE,
    dimension varchar(48) NOT NULL,
    score integer,
    verdict varchar(24) NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    owner_marked boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_evaluations_workflow_dim
    ON agent_evaluations (workflow_id, dimension);
"""


def upgrade() -> None:
    # asyncpg prepares every statement, and a prepared statement may hold exactly
    # one command — a single multi-statement block raises
    # "cannot insert multiple commands into a prepared statement". The DDL is
    # kept as one readable document and split here rather than fragmented into
    # dozens of op.execute calls.
    for statement in (part.strip() for part in DDL.split(";")):
        if statement:
            op.execute(statement)

    for table in (*OWNER_TABLES, APPEND_ONLY):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE applies the policy to the table owner as well, so a superuser-ish
        # connection cannot quietly bypass owner scoping.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} "
            f"USING ({HAS_UID} AND owner_user_id = {UID}) "
            f"WITH CHECK ({HAS_UID} AND owner_user_id = {UID})"
        )

    for table in OWNER_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")

    # The ledger is append-only at the privilege level. Without UPDATE or DELETE
    # granted, a future service cannot rewrite history even by accident.
    op.execute(f"GRANT SELECT, INSERT ON {APPEND_ONLY} TO {APP_ROLE}")


def downgrade() -> None:
    for table in (
        "agent_evaluations",
        "agent_policies",
        "agent_tool_calls",
        "agent_checkpoints",
        "agent_run_events",
        "agent_approvals",
        "agent_steps",
        "agent_workflows",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
