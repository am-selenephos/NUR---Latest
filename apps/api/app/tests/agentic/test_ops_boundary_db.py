"""The least-privileged cross-owner boundary, and what it must not be able to do.

Dispatch and recovery are the only two Agency Plane operations that legitimately
span owners. Both previously ran as `nur_app` with no `app.current_user_id` set
and therefore swept zero rows under FORCE RLS — silently, everywhere. The two
easy fixes were both wrong: BYPASSRLS on `nur_app` would expose every owner's
private data to the request-serving role, and running the sweep as the schema
owner is the same escalation renamed.

So the boundary is four SECURITY DEFINER functions. That is real privilege, and
the point of this file is to pin down its exact edges: `nur_app` must gain
nothing beyond the ability to call them, the functions must not read owner
content, and a caller must not be able to widen them.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.agentic import AgentStep, AgentWorkflow
from app.tests.conftest import register_user

OPS_FUNCTIONS = [
    "agent_ops_claim_dispatch",
    "agent_ops_mark_dispatch_sent",
    "agent_ops_mark_dispatch_failed",
    "agent_ops_reclaim_expired_steps",
]

# Tables holding owner content the boundary has no business reaching. If a future
# edit references one of these inside a SECURITY DEFINER body, that is a
# BYPASSRLS-backed read of private data and this list is what catches it. Every
# name is asserted to be a real table by
# `test_the_forbidden_table_list_is_not_vacuous` — a typo here would silently
# turn the check below into a check of nothing.
FORBIDDEN_TABLES = [
    "journal_entries", "timeline_events", "memories", "memory_candidates",
    "insights", "omega_experiences", "context_capsules", "am_projects",
    "am_project_tasks", "community_messages",
]


@pytest.fixture()
async def owner(client) -> uuid.UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture()
async def scoped(app_engine, owner):
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        yield db


@pytest.mark.asyncio
async def test_the_app_role_still_has_no_bypassrls(super_engine):
    """The whole reason the boundary exists. If this ever flips, the boundary is
    pointless and every request-serving path can read every owner."""
    async with super_engine.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'nur_app'")
            )
        ).scalar_one() is False


@pytest.mark.asyncio
async def test_every_ops_function_is_security_definer_with_a_fixed_search_path(super_engine):
    """A SECURITY DEFINER function without a pinned search_path is a takeover
    primitive: a caller who can create objects in an earlier schema shadows
    `agent_dispatch_outbox` and has a BYPASSRLS-owned body operate on their own
    table."""
    async with super_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT p.proname, p.prosecdef, p.proconfig, r.rolname, r.rolbypassrls "
                    "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
                    "WHERE p.proname = ANY(:names)"
                ),
                {"names": OPS_FUNCTIONS},
            )
        ).mappings().all()

    seen = {row["proname"] for row in rows}
    assert seen == set(OPS_FUNCTIONS), f"missing ops functions: {set(OPS_FUNCTIONS) - seen}"

    for row in rows:
        assert row["prosecdef"] is True, f"{row['proname']} is not SECURITY DEFINER"
        config = row["proconfig"] or []
        assert any(c.startswith("search_path=") for c in config), (
            f"{row['proname']} has no pinned search_path: {config}"
        )
        # The definer must be the role that actually holds BYPASSRLS, or the
        # function body cannot cross owners and the boundary is decorative.
        assert row["rolbypassrls"] is True, (
            f"{row['proname']} is owned by {row['rolname']}, which cannot bypass RLS"
        )


@pytest.mark.asyncio
async def test_public_cannot_execute_the_ops_functions(super_engine):
    """PUBLIC holds EXECUTE on a new function by default; leaving it means every
    role in the cluster can drive dispatch and recovery."""
    async with super_engine.connect() as conn:
        for name in OPS_FUNCTIONS:
            granted = (
                await conn.execute(
                    text(
                        "SELECT has_function_privilege('public', p.oid, 'EXECUTE') "
                        "FROM pg_proc p WHERE p.proname = :name"
                    ),
                    {"name": name},
                )
            ).scalar_one()
            assert granted is False, f"PUBLIC can execute {name}"

            allowed = (
                await conn.execute(
                    text(
                        "SELECT has_function_privilege('nur_app', p.oid, 'EXECUTE') "
                        "FROM pg_proc p WHERE p.proname = :name"
                    ),
                    {"name": name},
                )
            ).scalar_one()
            assert allowed is True, f"nur_app cannot execute {name}"


@pytest.mark.asyncio
async def test_the_forbidden_table_list_is_not_vacuous(super_engine):
    """Guards the check below. A misspelled table name would make
    `test_the_boundary_reads_no_owner_content` assert that four function bodies
    do not contain eight strings that could never appear anywhere."""
    async with super_engine.connect() as conn:
        for table in FORBIDDEN_TABLES:
            exists = (
                await conn.execute(
                    text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}
                )
            ).scalar_one()
            assert exists is True, f"{table} is not a real table; the guard would be vacuous"


@pytest.mark.asyncio
async def test_the_boundary_reads_no_owner_content(super_engine):
    """Behavioural in the only way that matters here: the function *source* is
    the security surface, because a SECURITY DEFINER body can read anything its
    owner can. Any reference to an owner-content table is the defect."""
    async with super_engine.connect() as conn:
        for name in OPS_FUNCTIONS:
            body = (
                await conn.execute(
                    text("SELECT prosrc FROM pg_proc WHERE proname = :name"), {"name": name}
                )
            ).scalar_one().lower()
            for table in FORBIDDEN_TABLES:
                assert table not in body, f"{name} references owner-content table {table}"


@pytest.mark.asyncio
async def test_ordinary_app_role_still_cannot_cross_owners(scoped, owner, client, app_engine):
    """The boundary must not have widened direct table access. A second owner's
    rows stay invisible and immutable to this owner's session."""
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="mine", objective="o", state="RUNNING"
    )
    scoped.add(workflow)
    await scoped.flush()
    await scoped.commit()

    other, _e, _p = await register_user(client, chosen_name="Bee")
    stranger = uuid.UUID(other.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        assert (
            await db.execute(
                text("SELECT count(*) FROM agent_workflows WHERE id = :w"), {"w": workflow.id}
            )
        ).scalar() == 0, "another owner's workflow is visible"

        result = await db.execute(
            text("UPDATE agent_workflows SET title = 'hijacked' WHERE id = :w"),
            {"w": workflow.id},
        )
        assert result.rowcount == 0, "another owner's workflow is mutable"


@pytest.mark.asyncio
async def test_the_boundary_can_reclaim_across_owners(scoped, owner, client, app_engine):
    """The capability the boundary exists for, proven through the app role with
    no session variable set — exactly how the recovery task runs."""
    other, _e, _p = await register_user(client, chosen_name="Cee")
    stranger = uuid.UUID(other.json()["id"])

    expired_steps: list[uuid.UUID] = []
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    for who in (owner, stranger):
        async with maker() as db:
            await db.execute(
                text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(who)}
            )
            workflow = AgentWorkflow(
                owner_user_id=who, kind="T", title="t", objective="o", state="RUNNING"
            )
            db.add(workflow)
            await db.flush()
            step = AgentStep(
                owner_user_id=who, workflow_id=workflow.id, ordinal=1, key="a",
                state="RUNNING", role="operator", tool_key="get_timeline", tool_version="1",
                risk_class="R0_READ_ONLY", input_refs={}, depends_on=[], worker_id="dead",
            )
            db.add(step)
            await db.flush()
            # An expired lease: what an abandoned worker leaves behind.
            await db.execute(
                text(
                    "UPDATE agent_steps SET lease_expires_at = now() - interval '1 minute' "
                    "WHERE id = :s"
                ),
                {"s": step.id},
            )
            expired_steps.append(step.id)
            await db.commit()

    # No session variable — the recovery task's exact posture.
    async with maker() as sweep:
        rows = (
            await sweep.execute(
                text(
                    "SELECT step_id, owner_user_id FROM agent_ops_reclaim_expired_steps(100)"
                )
            )
        ).mappings().all()
        await sweep.commit()

    reclaimed = {row["step_id"] for row in rows}
    for step_id in expired_steps:
        assert step_id in reclaimed, "the boundary failed to reclaim across owners"

    owners_touched = {row["owner_user_id"] for row in rows}
    assert {owner, stranger} <= owners_touched, "the sweep did not span both owners"


@pytest.mark.asyncio
async def test_reclaim_issues_a_new_attempt_token(scoped, owner):
    """Recovery must fence the worker it took the step from, or that worker can
    still complete the attempt it lost."""
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    scoped.add(workflow)
    await scoped.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="a",
        state="RUNNING", role="operator", tool_key="get_timeline", tool_version="1",
        risk_class="R0_READ_ONLY", input_refs={}, depends_on=[], worker_id="dead",
    )
    scoped.add(step)
    await scoped.flush()
    before = (
        await scoped.execute(
            text(
                "UPDATE agent_steps SET lease_expires_at = now() - interval '1 minute' "
                "WHERE id = :s RETURNING execution_attempt"
            ),
            {"s": step.id},
        )
    ).scalar_one()
    await scoped.commit()

    await scoped.execute(text("SELECT agent_ops_reclaim_expired_steps(100)"))
    await scoped.commit()

    after = (
        await scoped.execute(
            text("SELECT state, execution_attempt, worker_id FROM agent_steps WHERE id = :s"),
            {"s": step.id},
        )
    ).mappings().one()
    assert after["state"] == "QUEUED"
    assert after["worker_id"] is None
    assert after["execution_attempt"] != before, (
        "a reclaimed step kept its token; the abandoning worker could still finish it"
    )


@pytest.mark.asyncio
async def test_a_forged_owner_argument_cannot_widen_the_boundary(scoped):
    """None of the functions accepts an owner id, so there is no scope argument
    to forge. This pins that shape: a signature that grew one would be a
    caller-controlled scope on a BYPASSRLS body."""
    rows = (
        await scoped.execute(
            text(
                "SELECT proname, pg_get_function_arguments(oid) AS args "
                "FROM pg_proc WHERE proname = ANY(:names)"
            ),
            {"names": OPS_FUNCTIONS},
        )
    ).mappings().all()
    for row in rows:
        assert "owner" not in row["args"].lower(), (
            f"{row['proname']} takes an owner argument: {row['args']}"
        )


@pytest.mark.asyncio
async def test_ops_permissions_survive_a_clean_migration(super_engine):
    """The grants come from the migration, not from a one-off fix-up. The test
    database is built by running Alembic from scratch, so their presence here is
    already proof the migration produced them — asserted explicitly so a future
    edit that drops the GRANT fails loudly."""
    async with super_engine.connect() as conn:
        version = (
            await conn.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
        assert version, "no alembic version recorded"

        for name in OPS_FUNCTIONS:
            exists = (
                await conn.execute(
                    text("SELECT count(*) FROM pg_proc WHERE proname = :name"), {"name": name}
                )
            ).scalar_one()
            assert exists == 1, f"{name} absent after a clean migration"
