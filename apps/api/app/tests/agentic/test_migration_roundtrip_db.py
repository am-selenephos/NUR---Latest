"""Clean upgrade from base to head, and a lossless downgrade/upgrade cycle.

A migration that cannot be rolled back and re-applied is a migration nobody can
deploy twice, and a downgrade that quietly drops a constraint it never restores
leaves the schema weaker than before while reporting success — 0040 did exactly
that until it was caught.

This runs against its own disposable database: the shared per-run one is migrated
once at session start, so a round-trip performed on it would leave every other
test running against a schema this test had rebuilt.

The consent invalidation in 0043 is deliberately irreversible and documented as
such — its downgrade restores schema shape, never revoked consent. So the
fingerprint below is structural (functions, constraints, columns), which is what
a round-trip must actually preserve.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tests.conftest import ADMIN_PW, API_DIR, SUPER_DSN

RT_DB = f"nur_rt_{uuid.uuid4().hex[:10]}"
_HOST = SUPER_DSN.split("@", 1)[1].split("/", 1)[0]
ADMIN_DSN = f"postgresql+asyncpg://nur_admin:{ADMIN_PW}@{_HOST}/{RT_DB}"
SUPER_ASYNC_DSN = (
    SUPER_DSN.replace("postgresql://", "postgresql+asyncpg://").rsplit("/", 1)[0] + f"/{RT_DB}"
)

FINGERPRINT = """
SELECT
  (SELECT count(*) FROM pg_proc WHERE proname LIKE 'agent_ops%') AS ops_functions,
  (SELECT count(*) FROM pg_constraint WHERE contype = 'f'
     AND conrelid::regclass::text LIKE 'agent_%') AS agentic_foreign_keys,
  (SELECT count(*) FROM pg_constraint WHERE contype = 'c'
     AND conrelid::regclass::text LIKE 'agent_%') AS agentic_checks,
  (SELECT count(*) FROM pg_indexes WHERE tablename LIKE 'agent_%') AS agentic_indexes,
  (SELECT count(*) FROM information_schema.columns
     WHERE table_name LIKE 'agent_%') AS agentic_columns
"""


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
def roundtrip_db():
    _psql(f"DROP DATABASE IF EXISTS {RT_DB} WITH (FORCE)")
    _psql(f"CREATE DATABASE {RT_DB} OWNER nur_admin")
    _psql("ALTER SCHEMA public OWNER TO nur_admin", db=RT_DB)
    _psql("GRANT USAGE ON SCHEMA public TO nur_app", db=RT_DB)
    yield
    _psql(f"DROP DATABASE IF EXISTS {RT_DB} WITH (FORCE)")


async def _snapshot() -> dict:
    engine = create_async_engine(SUPER_ASYNC_DSN)
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(text(FINGERPRINT))).mappings().one()
            head = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        return {**dict(row), "head": head}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clean_upgrade_then_lossless_downgrade_upgrade_cycle(roundtrip_db):
    """A fresh database reaches head, and rolling the recent migrations back and
    forward returns the exact same structure."""
    _alembic("upgrade", "head")
    before = await _snapshot()

    assert before["ops_functions"] == 4, (
        f"the ops boundary is incomplete after a clean upgrade: {before}"
    )
    assert before["agentic_foreign_keys"] > 0
    assert before["agentic_checks"] > 0

    # The five migrations added in this PR's latest phase, rolled back and
    # re-applied. Anything a downgrade forgets to restore shows up as a
    # fingerprint mismatch rather than as a silently weaker schema.
    _alembic("downgrade", "-5")
    _alembic("upgrade", "head")
    after = await _snapshot()

    assert after == before, (
        "the downgrade/upgrade cycle changed the schema:\n"
        f"  before={before}\n  after ={after}"
    )


@pytest.mark.asyncio
async def test_every_ops_function_returns_after_a_round_trip(roundtrip_db):
    """Not just the count: each function must exist by name and still be
    SECURITY DEFINER with its search_path pinned. A downgrade that recreated
    them as plain functions would keep the count and lose the boundary."""
    _alembic("upgrade", "head")
    _alembic("downgrade", "-5")
    _alembic("upgrade", "head")

    engine = create_async_engine(SUPER_ASYNC_DSN)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT proname, prosecdef, proconfig FROM pg_proc "
                        "WHERE proname LIKE 'agent_ops%' ORDER BY proname"
                    )
                )
            ).mappings().all()
    finally:
        await engine.dispose()

    names = [row["proname"] for row in rows]
    assert names == [
        "agent_ops_claim_dispatch",
        "agent_ops_mark_dispatch_failed",
        "agent_ops_mark_dispatch_sent",
        "agent_ops_reclaim_expired_steps",
    ], names
    for row in rows:
        assert row["prosecdef"] is True, f"{row['proname']} lost SECURITY DEFINER"
        assert any(
            c.startswith("search_path=") for c in (row["proconfig"] or [])
        ), f"{row['proname']} lost its pinned search_path"
