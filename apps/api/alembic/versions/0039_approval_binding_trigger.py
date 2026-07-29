"""Enforce that an approval's step belongs to the same owner and workflow.

Three independent foreign keys cannot express this. approval.step_id -> steps.id
and approval.workflow_id -> workflows.id are each satisfied by rows that have
nothing to do with each other, so an approval can legally point at a step from a
different workflow — or, with a wrong owner id, at another person's step. RLS
narrows what a session can see; it does not constrain the relationship between
columns in a row the session may legitimately write.

A trigger is used rather than service-level validation because the invariant
must hold for every writer, including a future migration or a fix-up script that
never goes through the service.

Revision ID: 0039_approval_binding_trigger
Revises: 0038_outbox_index_split
"""

from __future__ import annotations

from alembic import op

revision = "0039_approval_binding_trigger"
down_revision = "0038_outbox_index_split"
branch_labels = None
depends_on = None

FUNCTION = """
CREATE OR REPLACE FUNCTION fn_agent_approval_binding() RETURNS trigger AS $$
DECLARE
    step_owner uuid;
    step_workflow uuid;
BEGIN
    IF NEW.step_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Read the step directly. SECURITY DEFINER is not used: the trigger runs in
    -- the writer's context and only needs the two ids it is comparing.
    SELECT owner_user_id, workflow_id INTO step_owner, step_workflow
      FROM agent_steps WHERE id = NEW.step_id;

    IF step_owner IS NULL THEN
        RAISE EXCEPTION 'agent_approval_binding: step % is not visible', NEW.step_id
            USING ERRCODE = '23514';
    END IF;

    IF step_owner <> NEW.owner_user_id THEN
        RAISE EXCEPTION 'agent_approval_binding: step owner does not match approval owner'
            USING ERRCODE = '23514';
    END IF;

    IF step_workflow <> NEW.workflow_id THEN
        RAISE EXCEPTION 'agent_approval_binding: step belongs to a different workflow'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER tr_agent_approval_binding
BEFORE INSERT OR UPDATE OF step_id, workflow_id, owner_user_id ON agent_approvals
FOR EACH ROW EXECUTE FUNCTION fn_agent_approval_binding();
"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_agent_approval_binding ON agent_approvals")
    op.execute("DROP FUNCTION IF EXISTS fn_agent_approval_binding()")
