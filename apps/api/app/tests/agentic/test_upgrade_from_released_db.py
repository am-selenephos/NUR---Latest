"""Upgrading an EXISTING database, not building a fresh one.

Every other migration test in this suite creates an empty database and runs the
whole chain, which is the one scenario where an edited-in-place revision still
works: it has never been applied, so the edit takes effect. A real deployment is
the opposite — most revisions are already recorded, and Alembic will never re-run
them no matter what their file now says.

That gap shipped a real outage. 0043 was released without the consent-provenance
columns and they were added to it afterwards, so a running instance stamped at
0048 reported those columns as applied while `agent_approvals` did not have them,
and the first step the worker executed raised
`column agent_approvals.invalidated_from does not exist`.

So this walks the chain the way a deployment does: stop at an intermediate
revision, then upgrade the rest of the way, and require that every column the ORM
maps actually exists afterwards. An edited revision earlier than the stopping
point cannot rescue itself, which is precisely the failure mode.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
# Imported for its side effect: the mappers must be registered on Base.metadata
# before the comparison below, or every table lookup is a KeyError.
import app.models  # noqa: F401
from app.tests.conftest import ADMIN_PW, API_DIR, SUPER_DSN

# Where a real database is likely to already be: past the agentic spine and its
# consent work, but before the newest revisions.
STOPPING_POINT = "0043_invalidate_legacy_consent"

AGENTIC_TABLES = [
    "agent_workflows", "agent_steps", "agent_approvals", "agent_tool_calls",
    "agent_policies", "agent_run_events", "agent_checkpoints",
    "agent_evaluations", "agent_dispatch_outbox",
]

UP_DB = f"nur_up_{uuid.uuid4().hex[:10]}"
_HOST = SUPER_DSN.split("@", 1)[1].split("/", 1)[0]
ADMIN_DSN = f"postgresql+asyncpg://nur_admin:{ADMIN_PW}@{_HOST}/{UP_DB}"
SUPER_ASYNC_DSN = (
    SUPER_DSN.replace("postgresql://", "postgresql+asyncpg://").rsplit("/", 1)[0] + f"/{UP_DB}"
)


def _psql(sql: str, db: str | None = None) -> None:
    dsn = SUPER_DSN if db is None else SUPER_DSN.rsplit("/", 1)[0] + f"/{db}"
    subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-q", "-c", sql], check=True)


def _alembic(*args: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "alembic.config", *args],
        cwd=API_DIR, capture_output=True, text=True,
        env={**os.environ, "ALEMBIC_DATABASE_URL": ADMIN_DSN},
    )
    assert proc.returncode == 0, f"alembic {args} failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.fixture()
def staged_db():
    _psql(f"DROP DATABASE IF EXISTS {UP_DB} WITH (FORCE)")
    _psql(f"CREATE DATABASE {UP_DB} OWNER nur_admin")
    _psql("ALTER SCHEMA public OWNER TO nur_admin", db=UP_DB)
    _psql("GRANT USAGE ON SCHEMA public TO nur_app", db=UP_DB)
    _psql("GRANT ALL ON SCHEMA public TO nur_email_lookup", db=UP_DB)
    _psql("GRANT nur_email_lookup TO nur_admin", db=UP_DB)
    yield
    _psql(f"DROP DATABASE IF EXISTS {UP_DB} WITH (FORCE)")


@pytest.mark.asyncio
async def test_an_existing_database_upgraded_to_head_has_every_mapped_column(staged_db):
    """The regression that shipped. Stop where a deployed database already is,
    then upgrade — and require the ORM to be satisfiable afterwards."""
    _alembic("upgrade", STOPPING_POINT)

    # Simulate the released state of that revision: strip the columns it only
    # gained by being edited after release. A real database stamped at 0043
    # never had them, and nothing downstream can make 0043 run again.
    _psql(
        "ALTER TABLE agent_approvals "
        "DROP COLUMN IF EXISTS invalidated_from, "
        "DROP COLUMN IF EXISTS invalidated_at, "
        "DROP COLUMN IF EXISTS invalidation_reason",
        db=UP_DB,
    )

    _alembic("upgrade", "head")

    engine = create_async_engine(SUPER_ASYNC_DSN)
    try:
        async with engine.connect() as conn:
            actual = await conn.run_sync(
                lambda sync: {
                    table: {c["name"] for c in inspect(sync).get_columns(table)}
                    for table in AGENTIC_TABLES
                }
            )
    finally:
        await engine.dispose()

    missing: list[str] = []
    for table in AGENTIC_TABLES:
        mapped = {c.name for c in Base.metadata.tables[table].columns}
        for column in sorted(mapped - actual[table]):
            missing.append(f"{table}.{column}")

    assert not missing, (
        "an upgraded database is missing columns the ORM maps, so every query "
        f"through those mappers raises UndefinedColumn: {missing}"
    )


@pytest.mark.asyncio
async def test_the_approval_mapper_can_actually_select_after_an_upgrade(staged_db):
    """The failure as the worker met it: `load_step_approval` selects the whole
    mapped row, so one absent column breaks every step execution. A column-set
    comparison is the diagnosis; this is the symptom."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy import select

    from app.models.agentic import AgentApproval

    _alembic("upgrade", STOPPING_POINT)
    _psql(
        "ALTER TABLE agent_approvals "
        "DROP COLUMN IF EXISTS invalidated_from, "
        "DROP COLUMN IF EXISTS invalidated_at, "
        "DROP COLUMN IF EXISTS invalidation_reason",
        db=UP_DB,
    )
    _alembic("upgrade", "head")

    engine = create_async_engine(SUPER_ASYNC_DSN)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            # Exactly the shape load_step_approval issues.
            await db.execute(
                select(AgentApproval).where(
                    AgentApproval.owner_user_id == uuid.uuid4(),
                    AgentApproval.step_id == uuid.uuid4(),
                    AgentApproval.decision.in_(["APPROVED", "EDITED"]),
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_head_is_reachable_from_every_recent_revision(staged_db):
    """A database sitting at any recent revision must be able to reach head.
    Walking one revision at a time also proves no step in the chain depends on a
    later one having already run."""
    _alembic("upgrade", STOPPING_POINT)
    for _ in range(20):
        current = subprocess.run(
            [sys.executable, "-m", "alembic.config", "current"],
            cwd=API_DIR, capture_output=True, text=True,
            env={**os.environ, "ALEMBIC_DATABASE_URL": ADMIN_DSN},
        ).stdout
        if "(head)" in current:
            break
        _alembic("upgrade", "+1")
    else:
        raise AssertionError("head was not reached within single-revision steps")
