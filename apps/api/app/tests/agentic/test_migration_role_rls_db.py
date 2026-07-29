"""nur_admin — the role every Alembic migration runs as — must be able to see
and mutate rows across every owner with no `app.current_user_id` ever set.

Every agentic table carries `FORCE ROW LEVEL SECURITY`, and Postgres applies a
forced policy to the table owner too, unless the owner holds BYPASSRLS. nur_admin
owns these tables and previously had NOBYPASSRLS: a direct probe against this
exact schema confirmed that `UPDATE agent_approvals SET decision = 'INVALIDATED'
WHERE decision IN (...)` — the literal statement 0037/0042/0043 execute — updated
zero rows when run as nur_admin with no session variable set, which is exactly
how Alembic connects. Every migration-time bulk data statement across the nine
agentic tables was therefore a silent no-op regardless of what its SQL appeared
to say, on top of whichever encoding or predicate bug it also had.

The fix is `ALTER ROLE nur_admin BYPASSRLS`, granted during role provisioning
(conftest.py for tests, infra/scripts/bootstrap-dev.sh for dev) — never inside a
migration, since only an actual superuser may grant BYPASSRLS; CREATEROLE is not
enough.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.agentic import AgentApproval, AgentStep, AgentWorkflow
from app.tests.conftest import register_user


@pytest.mark.asyncio
async def test_migration_role_holds_bypassrls(super_engine):
    """The specific grant the fix depends on, asserted directly rather than
    inferred from behaviour alone."""
    async with super_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'nur_admin'")
            )
        ).one()
        assert row.rolbypassrls is True


@pytest.mark.asyncio
async def test_migration_role_mutates_rows_across_owners_with_no_session_var(
    client, app_engine, admin_engine
):
    """The behavioural proof: a migration-shaped UPDATE, issued exactly as
    Alembic issues it, actually lands — across two different owners in the
    same statement, with no `app.current_user_id` ever set on that connection.

    Falsified against the prior defect: before the BYPASSRLS grant, this exact
    statement against these exact rows updated zero of them (confirmed by a
    direct probe against this schema), while `agent_approvals` unfiltered by
    RLS still showed the rows as PENDING. If the grant regresses, this test
    goes back to failing the same way.
    """
    owner_ids: list[uuid.UUID] = []
    app_maker = async_sessionmaker(app_engine, expire_on_commit=False)
    for _ in range(2):
        response, _e, _p = await register_user(client)
        assert response.status_code == 201, response.text
        owner_id = uuid.UUID(response.json()["id"])
        owner_ids.append(owner_id)

        async with app_maker() as db:
            await db.execute(
                text("SELECT set_config('app.current_user_id', :o, false)"),
                {"o": str(owner_id)},
            )
            workflow = AgentWorkflow(
                owner_user_id=owner_id, kind="T", title="t", objective="o", state="RUNNING"
            )
            db.add(workflow)
            await db.flush()
            step = AgentStep(
                owner_user_id=owner_id, workflow_id=workflow.id, ordinal=1, key="a",
                state="WAITING_APPROVAL", role="operator", tool_key="get_timeline",
                tool_version="1", risk_class="R0_READ_ONLY", input_refs={}, depends_on=[],
            )
            db.add(step)
            await db.flush()
            db.add(
                AgentApproval(
                    owner_user_id=owner_id, workflow_id=workflow.id, step_id=step.id,
                    tool_key="get_timeline", tool_version="1", argument_digest="sha256:a",
                    rationale="r", risk_class="R0_READ_ONLY", decision="PENDING",
                    plan_version=1, call_version="cv:legacy",
                )
            )
            await db.commit()

    # A brand new connection as nur_admin, no session variable set — the exact
    # shape of every Alembic connection.
    admin_maker = async_sessionmaker(admin_engine, expire_on_commit=False)
    async with admin_maker() as admin_db:
        result = await admin_db.execute(
            text(
                "UPDATE agent_approvals SET decision = 'INVALIDATED' "
                "WHERE decision IN ('PENDING', 'APPROVED', 'EDITED') "
                "AND owner_user_id = ANY(:owners) "
                "RETURNING owner_user_id"
            ),
            {"owners": owner_ids},
        )
        touched = {row[0] for row in result.fetchall()}
        await admin_db.commit()

    assert touched == set(owner_ids), (
        "nur_admin must mutate rows across every owner with no session var set; "
        f"touched {touched}, expected {set(owner_ids)}"
    )
