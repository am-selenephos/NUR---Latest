"""Real ORM-to-PostgreSQL parity, both directions.

The previous version of this file compared `Base.metadata` with itself and
called it database parity. It could not detect a mapped column that does not
exist, which is exactly the defect it was written to prevent: a broad
string-replacement added plan_version and call_version to AgentToolCall, whose
table has neither, and every assertion still passed.

These query information_schema. A mapped column that does not exist in
PostgreSQL, or a NOT NULL column the ORM never maps, fails with a per-table diff.
"""

import asyncio
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
import app.models  # noqa: F401  - registers every mapper

AGENTIC_TABLES = [
    "agent_workflows", "agent_steps", "agent_approvals", "agent_run_events",
    "agent_checkpoints", "agent_tool_calls", "agent_policies",
    "agent_evaluations", "agent_dispatch_outbox",
]


def _url() -> str | None:
    # Only asyncpg is installed in this environment, so the driver stays async
    # and inspection runs through run_sync rather than a second sync driver.
    return os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")


# One loop for the module. A fresh loop per call closes the engine's pooled
# connections mid-operation, which surfaces as ConnectionDoesNotExistError
# rather than as anything to do with schema parity.
_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module")
def engine():
    url = _url()
    if not url:
        pytest.skip("no database configured; set ALEMBIC_DATABASE_URL for parity proof")

    async def probe():
        eng = create_async_engine(url)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return eng

    try:
        return _run(probe())
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"database unreachable: {exc}")


def _columns(engine, table: str) -> dict[str, dict]:
    async def go():
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_columns(table)
            )

    return {c["name"]: c for c in _run(go())}


def _fetch(engine, sql: str, params: dict | None = None):
    async def go():
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params or {})).all()

    return _run(go())


def db_columns(engine, table: str) -> dict[str, dict]:
    return _columns(engine, table)


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_no_mapped_column_is_missing_from_postgresql(engine, table):
    """Catches the AgentToolCall corruption: a column the ORM maps and the
    database does not have. Every SELECT through that mapper would raise
    UndefinedColumn at runtime."""
    mapped = {c.name for c in Base.metadata.tables[table].columns}
    actual = set(db_columns(engine, table))
    phantom = mapped - actual
    assert not phantom, f"{table}: ORM maps columns absent from PostgreSQL: {sorted(phantom)}"


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_no_required_database_column_is_unmapped(engine, table):
    """A NOT NULL column without a default that the ORM does not map makes every
    ORM insert fail."""
    mapped = {c.name for c in Base.metadata.tables[table].columns}
    required = {
        name
        for name, col in db_columns(engine, table).items()
        if not col["nullable"] and col.get("default") is None
    }
    unmapped = required - mapped
    assert not unmapped, f"{table}: required PostgreSQL columns unmapped: {sorted(unmapped)}"


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_nullability_matches(engine, table):
    actual = db_columns(engine, table)
    mismatches = []
    for column in Base.metadata.tables[table].columns:
        real = actual.get(column.name)
        if real is None:
            continue
        if column.nullable != real["nullable"]:
            mismatches.append(
                f"{column.name}: ORM nullable={column.nullable}, DB nullable={real['nullable']}"
            )
    assert not mismatches, f"{table}: {mismatches}"


def test_forced_rls_on_every_agentic_table(engine):
    rows = _fetch(
        engine,
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname = ANY(:names)",
        {"names": AGENTIC_TABLES},
    )
    seen = {name: (rls, forced) for name, rls, forced in rows}
    missing = [t for t in AGENTIC_TABLES if seen.get(t) != (True, True)]
    assert not missing, f"tables without forced RLS: {missing}"


def test_required_indexes_exist(engine):
    expected = {
        "uq_agent_steps_idempotency",
        "uq_agent_approval_one_pending",
        "uq_agent_dispatch_key",
        "uq_agent_policy_account",
        "uq_agent_policy_orbit",
        "uq_agent_policy_project",
        "ix_agent_run_events_workflow_seq",
    }
    present = {
        row[0]
        for row in _fetch(
            engine,
            "SELECT indexname FROM pg_indexes WHERE indexname = ANY(:names)",
            {"names": sorted(expected)},
        )
    }
    assert expected <= present, f"missing indexes: {sorted(expected - present)}"


def test_append_only_ledger_has_no_update_or_delete_grant(engine):
    grants = {
        row[0]
        for row in _fetch(
            engine,
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name = 'agent_run_events' AND grantee = 'nur_app'",
        )
    }
    assert grants == {"SELECT", "INSERT"}, grants
