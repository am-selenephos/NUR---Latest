"""Composite ownership binding and the full RLS matrix.

Independent foreign keys plus RLS do not express "this child's owner and
workflow must match its parent's". A composite unique key on the parent plus a
composite foreign key from the child does, in the database, for every writer.

The RLS matrix covers every owner-scoped Agency table rather than one, because a
single-table result says nothing about the other eight.
"""

import datetime as dt
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.agentic import AgentStep, AgentWorkflow
from app.tests.conftest import register_user

OWNER_SCOPED_TABLES = [
    "agent_workflows", "agent_steps", "agent_approvals", "agent_tool_calls",
    "agent_policies", "agent_run_events", "agent_checkpoints",
    "agent_evaluations", "agent_dispatch_outbox",
]


@pytest.fixture()
async def owner(client) -> UUID:
    response, _e, _p = await register_user(client)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


@pytest.fixture()
async def scoped(app_engine, owner):
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(owner)}
        )
        yield db


async def _seed(db, owner: UUID):
    workflow = AgentWorkflow(
        owner_user_id=owner, kind="T", title="t", objective="o", state="RUNNING"
    )
    db.add(workflow)
    await db.flush()
    step = AgentStep(
        owner_user_id=owner, workflow_id=workflow.id, ordinal=1, key="s1",
        state="QUEUED", role="operator",
    )
    db.add(step)
    await db.flush()
    return workflow, step


# ── composite binding ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_step_cannot_claim_a_workflow_it_does_not_own(scoped, owner, client, app_engine):
    """A step row naming another owner's workflow must be refused even though
    both single-column foreign keys resolve."""
    workflow, _step = await _seed(scoped, owner)
    await scoped.commit()

    other, _e, _p = await register_user(client, chosen_name="Bee")
    stranger = UUID(other.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        with pytest.raises(Exception) as caught:
            await db.execute(
                text(
                    "INSERT INTO agent_steps (owner_user_id, workflow_id, ordinal, key, "
                    "state, role) VALUES (:o, :w, 1, 'x', 'QUEUED', 'operator')"
                ),
                {"o": stranger, "w": workflow.id},
            )
        assert "fk_agent_step_workflow_owner" in str(caught.value) or "violates" in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "table,columns,extra",
    [
        ("agent_dispatch_outbox", "dispatch_key, state", "'k1', 'RETRYABLE'"),
        (
            "agent_approvals",
            "tool_key, tool_version, argument_digest, rationale, risk_class, "
            "decision, call_version",
            "'t', '1', 'sha256:aaa', 'r', 'R2_DURABLE_PRIVATE', 'PENDING', 'cv:x'",
        ),
        ("agent_tool_calls",
         "tool_key, tool_version, risk_class, argument_digest, outcome",
         "'t', '1', 'R0_READ_ONLY', 'sha256:aaa', 'SUCCEEDED'"),
        ("agent_run_events", "sequence, event_type, summary", "1, 'E', 's'"),
        ("agent_checkpoints", "kind", "'PLANNER'"),
    ],
)
async def test_child_rows_cannot_pair_a_step_with_the_wrong_workflow(
    scoped, owner, table, columns, extra
):
    """The composite key is what forbids a child naming a step from a different
    workflow; independent FKs are each satisfied."""
    first, _ = await _seed(scoped, owner)
    second, step_of_second = await _seed(scoped, owner)

    with pytest.raises(Exception) as caught:
        await scoped.execute(
            text(
                f"INSERT INTO {table} (owner_user_id, workflow_id, step_id, {columns}) "
                f"VALUES (:o, :w, :s, {extra})"
            ),
            {"o": owner, "w": first.id, "s": step_of_second.id},
        )
    message = str(caught.value)
    assert "binding" in message or "violates" in message, message


@pytest.mark.asyncio
async def test_correctly_bound_child_rows_are_accepted(scoped, owner):
    """Guards the rejection tests from passing because everything is rejected."""
    workflow, step = await _seed(scoped, owner)
    await scoped.execute(
        text(
            "INSERT INTO agent_dispatch_outbox "
            "(owner_user_id, workflow_id, step_id, dispatch_key, state) "
            "VALUES (:o, :w, :s, 'ok', 'RETRYABLE')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id},
    )
    kept = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_dispatch_outbox WHERE step_id = :s"), {"s": step.id}
        )
    ).scalar()
    assert kept == 1


# ── full RLS matrix ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("table", OWNER_SCOPED_TABLES)
async def test_another_owner_cannot_select_or_update(
    scoped, owner, client, app_engine, table
):
    """Every owner-scoped Agency table, not one."""
    workflow, step = await _seed(scoped, owner)
    now = dt.datetime.now(dt.timezone.utc)
    seeds = {
        "agent_workflows": None,
        "agent_steps": None,
        "agent_approvals": (
            "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
            "tool_version, argument_digest, rationale, risk_class, decision, call_version) "
            "VALUES (:o, :w, :s, 't', '1', 'sha256:a', 'r', 'R2_DURABLE_PRIVATE', "
            "'PENDING', 'cv:x')"
        ),
        "agent_tool_calls": (
            "INSERT INTO agent_tool_calls (owner_user_id, workflow_id, step_id, tool_key, "
            "tool_version, risk_class, argument_digest, outcome) "
            "VALUES (:o, :w, :s, 't', '1', 'R0_READ_ONLY', 'sha256:a', 'SUCCEEDED')"
        ),
        "agent_policies": "INSERT INTO agent_policies (owner_user_id) VALUES (:o)",
        "agent_run_events": (
            "INSERT INTO agent_run_events (owner_user_id, workflow_id, step_id, sequence, "
            "event_type, summary) VALUES (:o, :w, :s, 1, 'E', 's')"
        ),
        "agent_checkpoints": (
            "INSERT INTO agent_checkpoints (owner_user_id, workflow_id, step_id, kind) "
            "VALUES (:o, :w, :s, 'PLANNER')"
        ),
        "agent_evaluations": (
            "INSERT INTO agent_evaluations (owner_user_id, workflow_id, dimension, verdict) "
            "VALUES (:o, :w, 'goal_fidelity', 'PASS')"
        ),
        "agent_dispatch_outbox": (
            "INSERT INTO agent_dispatch_outbox (owner_user_id, workflow_id, step_id, "
            "dispatch_key, state) VALUES (:o, :w, :s, 'k', 'RETRYABLE')"
        ),
    }
    sql = seeds[table]
    if sql:
        await scoped.execute(text(sql), {"o": owner, "w": workflow.id, "s": step.id})
    await scoped.commit()

    # The owner can see their own row.
    mine = (
        await scoped.execute(
            text(f"SELECT count(*) FROM {table} WHERE owner_user_id = :o"), {"o": owner}
        )
    ).scalar()
    assert mine >= 1, f"{table}: owner cannot see their own row"

    other, _e, _p = await register_user(client, chosen_name="Bee")
    stranger = UUID(other.json()["id"])
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        seen = (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
        assert seen == 0, f"{table}: another owner sees {seen} rows"

        if table == "agent_run_events":
            # The ledger is append-only at the privilege level: UPDATE is not
            # granted at all, which is a stronger guarantee than RLS returning
            # zero rows. Asserting rowcount here would understate it.
            with pytest.raises(Exception) as caught:
                await db.execute(
                    text(f"UPDATE {table} SET summary = 'x' WHERE owner_user_id = :o"),
                    {"o": owner},
                )
            assert "permission denied" in str(caught.value), str(caught.value)
        else:
            updated = await db.execute(
                text(
                    f"UPDATE {table} SET owner_user_id = owner_user_id "
                    f"WHERE owner_user_id = :o"
                ),
                {"o": owner},
            )
            assert updated.rowcount == 0, (
                f"{table}: another owner updated {updated.rowcount} rows"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["agent_workflows", "agent_policies"])
async def test_forged_owner_insert_is_rejected(scoped, owner, client, app_engine, table):
    """WITH CHECK must refuse a row that claims another owner."""
    other, _e, _p = await register_user(client, chosen_name="Cee")
    stranger = UUID(other.json()["id"])

    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as db:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(stranger)}
        )
        sql = {
            "agent_workflows": (
                "INSERT INTO agent_workflows (owner_user_id, kind, title, objective) "
                "VALUES (:forged, 'T', 't', 'o')"
            ),
            "agent_policies": "INSERT INTO agent_policies (owner_user_id) VALUES (:forged)",
        }[table]
        with pytest.raises(Exception) as caught:
            await db.execute(text(sql), {"forged": owner})
        assert "row-level security" in str(caught.value), str(caught.value)


@pytest.mark.asyncio
async def test_deleting_a_step_preserves_audit_rows(scoped, owner):
    """A tool call and a run event must survive their step's deletion with only
    step_id nulled.

    The composite FKs were declared plain ON DELETE SET NULL, which nulls every
    referencing column — and workflow_id and owner_user_id are NOT NULL.

    It did not fail, and the reason matters: the legacy single-column FK fired
    first, and once step_id was NULL the composite was vacuously satisfied under
    MATCH SIMPLE. Correct behaviour by accident of a redundant constraint.
    `test_composite_step_fks_null_only_the_step_column` asserts the action is
    now column-specific, which is what keeps this true if the legacy FKs are
    ever dropped as cleanup.
    """
    workflow, step = await _seed(scoped, owner)
    await scoped.execute(
        text(
            "INSERT INTO agent_tool_calls (owner_user_id, workflow_id, step_id, tool_key, "
            "tool_version, risk_class, argument_digest, outcome) "
            "VALUES (:o, :w, :s, 't', '1', 'R0_READ_ONLY', 'sha256:a', 'SUCCEEDED')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id},
    )
    await scoped.execute(
        text(
            "INSERT INTO agent_run_events (owner_user_id, workflow_id, step_id, sequence, "
            "event_type, summary) VALUES (:o, :w, :s, 1, 'E', 's')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id},
    )
    await scoped.execute(text("DELETE FROM agent_steps WHERE id = :s"), {"s": step.id})

    for table in ("agent_tool_calls", "agent_run_events"):
        row = (
            await scoped.execute(
                text(
                    f"SELECT step_id, workflow_id, owner_user_id FROM {table} "
                    f"WHERE workflow_id = :w"
                ),
                {"w": workflow.id},
            )
        ).one()
        assert row.step_id is None, f"{table}: step reference not cleared"
        assert row.workflow_id == workflow.id, f"{table}: workflow reference destroyed"
        assert row.owner_user_id == owner, f"{table}: owner reference destroyed"

    await scoped.rollback()


@pytest.mark.asyncio
async def test_deleting_a_workflow_still_cascades(scoped, owner):
    """The audit exemption is for steps only; a deleted workflow still takes its
    rows with it."""
    workflow, step = await _seed(scoped, owner)
    await scoped.execute(
        text(
            "INSERT INTO agent_tool_calls (owner_user_id, workflow_id, step_id, tool_key, "
            "tool_version, risk_class, argument_digest, outcome) "
            "VALUES (:o, :w, :s, 't', '1', 'R0_READ_ONLY', 'sha256:a', 'SUCCEEDED')"
        ),
        {"o": owner, "w": workflow.id, "s": step.id},
    )
    await scoped.execute(text("DELETE FROM agent_workflows WHERE id = :w"), {"w": workflow.id})
    remaining = (
        await scoped.execute(
            text("SELECT count(*) FROM agent_tool_calls WHERE workflow_id = :w"),
            {"w": workflow.id},
        )
    ).scalar()
    assert remaining == 0


@pytest.mark.asyncio
async def test_composite_step_fks_null_only_the_step_column(scoped):
    """Column-specific action, so audit rows survive even if the legacy
    single-column FKs are dropped."""
    rows = (
        await scoped.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname IN ('fk_agent_tool_call_step_binding', "
                "'fk_agent_event_step_binding')"
            )
        )
    ).all()
    assert len(rows) == 2
    for name, definition in rows:
        assert "ON DELETE SET NULL (step_id)" in definition, f"{name}: {definition}"
