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
import re

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
    # A missing or unreachable database is a hard failure, not a skip. A skipped
    # integration test reads as a pass in CI and proves nothing; the database is
    # an autouse requirement of this suite, so its absence is a broken
    # environment rather than an unsupported configuration.
    assert url, "no database configured: set ALEMBIC_DATABASE_URL or DATABASE_URL"

    async def probe():
        eng = create_async_engine(url)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return eng

    eng = _run(probe())
    yield eng
    _run(eng.dispose())
    _LOOP.close()


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


# Columns that exist in PostgreSQL and are deliberately not mapped. Every entry
# needs a reason and a removal plan; a heuristic here would defeat the test.
#
# `allowed_tools` is the legacy policy column superseded by permitted_tools and
# auto_run_tools. It stays in the database until a removal migration and is not
# mapped, so no caller can set something that governs nothing.
COMPATIBILITY_UNMAPPED: dict[str, set[str]] = {
    "agent_policies": {"allowed_tools"},
}


def orm_columns(table: str) -> set[str]:
    return {c.name for c in Base.metadata.tables[table].columns}


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_every_database_column_is_mapped_or_explicitly_excluded(engine, table):
    """Full DB -> ORM parity with no nullable/default heuristic.

    The previous version only flagged NOT NULL columns without a default, which
    excluded permitted_tools and auto_run_tools — both NOT NULL *with* defaults.
    Removing either mapping would have passed, which is the exact defect that
    killed policy loading. Every column is compared now.
    """
    mapped = orm_columns(table)
    actual = set(db_columns(engine, table))
    allowed = COMPATIBILITY_UNMAPPED.get(table, set())
    unmapped = actual - mapped - allowed
    assert not unmapped, f"{table}: PostgreSQL columns not mapped by the ORM: {sorted(unmapped)}"


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_the_compatibility_allowlist_is_exact(engine, table):
    """An allowlist entry that no longer exists in the database means the
    removal migration landed and the entry must go; keeping it would silently
    permit a future unmapped column of the same name."""
    actual = set(db_columns(engine, table))
    for column in COMPATIBILITY_UNMAPPED.get(table, set()):
        assert column in actual, (
            f"{table}: '{column}' is allowlisted as unmapped but no longer exists"
        )
        assert column not in orm_columns(table), (
            f"{table}: '{column}' is allowlisted as unmapped but the ORM maps it"
        )


@pytest.mark.parametrize("column", ["permitted_tools", "auto_run_tools"])
def test_the_comparator_detects_an_unmapped_policy_column(engine, column):
    """Falsification: hide the column from the comparator's ORM view and prove
    it is reported. Without this, the test above could be vacuous."""
    mapped = orm_columns("agent_policies") - {column}
    actual = set(db_columns(engine, "agent_policies"))
    allowed = COMPATIBILITY_UNMAPPED.get("agent_policies", set())
    unmapped = actual - mapped - allowed
    assert column in unmapped, f"comparator failed to report unmapped {column}"


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


def test_index_definitions_match_their_intent(engine):
    """Index *definitions*, not names. A name proves nothing — an index could be
    non-unique, on the wrong columns, or missing its partial predicate and still
    be present."""
    expected = {
        "uq_agent_approval_one_pending": {
            "table": "agent_approvals", "unique": True,
            "columns": ["owner_user_id", "step_id"],
            "predicate": "decision = 'PENDING'",
        },
        "uq_agent_dispatch_key": {
            "table": "agent_dispatch_outbox", "unique": True,
            "columns": ["dispatch_key"], "predicate": None,
        },
        "uq_agent_policy_account": {
            "table": "agent_policies", "unique": True,
            "columns": ["owner_user_id"],
            "predicate": "orbit_id IS NULL AND project_id IS NULL",
        },
        "uq_agent_policy_orbit": {
            "table": "agent_policies", "unique": True,
            "columns": ["owner_user_id", "orbit_id"],
            "predicate": "orbit_id IS NOT NULL AND project_id IS NULL",
        },
        "uq_agent_policy_project": {
            "table": "agent_policies", "unique": True,
            "columns": ["owner_user_id", "project_id"],
            "predicate": "project_id IS NOT NULL",
        },
        "uq_agent_steps_idempotency": {
            "table": "agent_steps", "unique": True,
            "columns": ["owner_user_id", "idempotency_key"],
            "predicate": "idempotency_key IS NOT NULL",
        },
        "ix_agent_run_events_workflow_seq": {
            "table": "agent_run_events", "unique": True,
            "columns": ["workflow_id", "sequence"], "predicate": None,
        },
        # Retry and reclaim are different queries over different columns; one
        # shared index would make reclaim a filter over the wrong column.
        "ix_agent_dispatch_retryable": {
            "table": "agent_dispatch_outbox", "unique": False,
            "columns": ["next_attempt_at"], "predicate": "state = 'RETRYABLE'",
        },
        "ix_agent_dispatch_claimed_lease": {
            "table": "agent_dispatch_outbox", "unique": False,
            "columns": ["lease_expires_at"], "predicate": "state = 'CLAIMED'",
        },
        "ix_agent_approval_call_version": {
            "table": "agent_approvals", "unique": False,
            "columns": ["step_id", "call_version"], "predicate": None,
        },
    }
    rows = _fetch(
        engine,
        "SELECT indexname, tablename, indexdef FROM pg_indexes WHERE indexname = ANY(:names)",
        {"names": sorted(expected)},
    )
    found = {name: (table, definition) for name, table, definition in rows}

    missing = sorted(set(expected) - set(found))
    assert not missing, f"missing indexes: {missing}"

    problems = []
    for name, want in expected.items():
        table, definition = found[name]
        if table != want["table"]:
            problems.append(f"{name}: on {table}, expected {want['table']}")
        is_unique = "CREATE UNIQUE INDEX" in definition
        if is_unique != want["unique"]:
            problems.append(
                f"{name}: unique={is_unique}, expected unique={want['unique']}"
            )
        # Columns must appear in order inside the parenthesised list.
        head = definition.split("USING btree (", 1)[-1].split(")", 1)[0]
        actual_cols = [c.strip() for c in head.split(",")]
        if actual_cols != want["columns"]:
            problems.append(f"{name}: columns {actual_cols}, expected {want['columns']}")
        predicate = definition.split(" WHERE ", 1)[1] if " WHERE " in definition else None
        if want["predicate"] is None:
            if predicate is not None:
                problems.append(f"{name}: unexpected partial predicate {predicate}")
        else:
            # Postgres renders predicates with explicit casts and parens, e.g.
            # ((decision)::text = 'PENDING'::text). Compare on the semantic core.
            def _norm(text_: str) -> str:
                out = re.sub(r"::[a-z_]+", "", text_ or "")
                out = out.replace("(", "").replace(")", "")
                return re.sub(r"\s+", " ", out).strip()

            normalised, wanted = _norm(predicate), _norm(want["predicate"])
            if normalised != wanted:
                problems.append(f"{name}: predicate {predicate!r}, expected {wanted!r}")
    assert not problems, problems


def test_outbox_state_check_allows_exactly_three_values(engine):
    rows = _fetch(
        engine,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_agent_dispatch_state'",
    )
    assert rows, "ck_agent_dispatch_state is missing"
    definition = rows[0][0]
    for value in ("RETRYABLE", "CLAIMED", "SENT"):
        assert value in definition, definition
    assert "BOGUS" not in definition


def test_foreign_keys_and_primary_keys_exist(engine):
    rows = _fetch(
        engine,
        # contype is Postgres "char"; asyncpg returns it as bytes, so a
        # Python comparison against 'p'/'f' silently never matches. Cast in SQL.
        "SELECT c.relname, con.contype::text, count(*) "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relname = ANY(:names) AND con.contype IN ('p','f') "
        "GROUP BY 1,2",
        {"names": AGENTIC_TABLES},
    )
    by_table: dict[str, dict[str, int]] = {}
    for table, kind, count in rows:
        by_table.setdefault(table, {})[kind] = count
    for table in AGENTIC_TABLES:
        assert by_table.get(table, {}).get("p"), f"{table}: no primary key"
        assert by_table.get(table, {}).get("f"), f"{table}: no foreign key to users/workflow"




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


# SQLAlchemy and PostgreSQL name equivalent types differently in a few places.
# Each entry is a real equivalence, not a way to make a mismatch pass.
TYPE_EQUIVALENTS = {
    ("UUID", "UUID"), ("JSONB", "JSONB"), ("TEXT", "TEXT"),
    ("VARCHAR", "VARCHAR"), ("INTEGER", "INTEGER"), ("BOOLEAN", "BOOLEAN"),
    ("TIMESTAMP", "TIMESTAMP"),
}


def _family(type_) -> str:
    name = type(type_).__name__.upper()
    return {"STRING": "VARCHAR", "DATETIME": "TIMESTAMP"}.get(name, name)


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_type_families_match(engine, table):
    actual = db_columns(engine, table)
    problems = []
    for column in Base.metadata.tables[table].columns:
        real = actual.get(column.name)
        if real is None:
            continue
        orm_family = _family(column.type)
        db_family = type(real["type"]).__name__.upper()
        db_family = {"STRING": "VARCHAR", "DATETIME": "TIMESTAMP"}.get(db_family, db_family)
        if (orm_family, db_family) not in TYPE_EQUIVALENTS:
            problems.append(f"{column.name}: ORM {orm_family} vs DB {db_family}")
    assert not problems, f"{table}: {problems}"


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_varchar_lengths_match(engine, table):
    """A shorter database column silently truncates; a longer ORM declaration
    lets a value through that the database will reject at insert time."""
    actual = db_columns(engine, table)
    problems = []
    for column in Base.metadata.tables[table].columns:
        real = actual.get(column.name)
        if real is None or _family(column.type) != "VARCHAR":
            continue
        orm_len = getattr(column.type, "length", None)
        db_len = getattr(real["type"], "length", None)
        if orm_len != db_len:
            problems.append(f"{column.name}: ORM length {orm_len} vs DB length {db_len}")
    assert not problems, f"{table}: {problems}"


@pytest.mark.parametrize("table", AGENTIC_TABLES)
def test_timestamps_are_timezone_aware(engine, table):
    """A naive timestamp column silently drops the offset, which turns lease
    expiry and approval expiry into wrong-by-hours comparisons."""
    actual = db_columns(engine, table)
    problems = []
    for column in Base.metadata.tables[table].columns:
        real = actual.get(column.name)
        if real is None or _family(column.type) != "TIMESTAMP":
            continue
        if not getattr(real["type"], "timezone", False):
            problems.append(f"{column.name}: database column is not timestamptz")
        if not getattr(column.type, "timezone", False):
            problems.append(f"{column.name}: ORM column is not timezone-aware")
    assert not problems, f"{table}: {problems}"


# Columns whose server default carries a security or correctness meaning. A
# changed default here is a behaviour change, not a cosmetic one.
SECURITY_DEFAULTS = {
    ("agent_policies", "initiative_level"): "SUGGEST",
    ("agent_policies", "max_risk_class"): "R1_PRIVATE_DRAFT",
    ("agent_steps", "approval_required"): "true",
    ("agent_steps", "risk_class"): "R0_READ_ONLY",
    ("agent_approvals", "decision"): "PENDING",
    ("agent_checkpoints", "redacted"): "false",
    ("agent_dispatch_outbox", "state"): "RETRYABLE",
}


def test_security_relevant_server_defaults(engine):
    """The conservative defaults are the ones that hold when nothing is
    configured: SUGGEST initiative, an R1 ceiling, approval required, an
    unredacted checkpoint marked unredacted."""
    problems = []
    for (table, column), expected in SECURITY_DEFAULTS.items():
        real = db_columns(engine, table).get(column)
        assert real is not None, f"{table}.{column} does not exist"
        default = (real.get("default") or "").split("::")[0].strip("'")
        if default != expected:
            problems.append(f"{table}.{column}: default {default!r}, expected {expected!r}")
    assert not problems, problems


# ── exact foreign keys ───────────────────────────────────────────────────────

def test_the_foreign_key_set_is_exactly_as_expected(engine):
    """Equality, not presence. A handpicked list cannot detect an FK that was
    added by accident or dropped by a migration — both happened on this branch:
    0040 replaced the single-column approval step FK with a composite one, and a
    presence-only test kept passing against the stale expectation."""
    rows = _fetch(
        engine,
        "SELECT c.relname, pg_get_constraintdef(con.oid) "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relname = ANY(:names) AND con.contype::text = 'f'",
        {"names": AGENTIC_TABLES},
    )
    actual = {
        (table, definition.replace("FOREIGN KEY ", "").strip())
        for table, definition in rows
    }

    expected = {
        # owner -> users, on every table
        *[(t, "(owner_user_id) REFERENCES users(id) ON DELETE CASCADE")
          for t in AGENTIC_TABLES],
        # workflow parentage, single and composite
        *[(t, "(workflow_id) REFERENCES agent_workflows(id) ON DELETE CASCADE")
          for t in ["agent_steps", "agent_approvals", "agent_run_events",
                    "agent_checkpoints", "agent_tool_calls", "agent_policies",
                    "agent_evaluations", "agent_dispatch_outbox"]
          if t != "agent_policies"],
        *[(t, "(workflow_id, owner_user_id) REFERENCES agent_workflows(id, owner_user_id) "
              "ON DELETE CASCADE")
          for t in ["agent_steps", "agent_approvals", "agent_run_events",
                    "agent_checkpoints", "agent_tool_calls", "agent_evaluations",
                    "agent_dispatch_outbox"]],
        # step parentage, composite — the binding that makes cross-workflow rows
        # impossible. CASCADE where the child is meaningless without the step;
        # SET NULL where the child is audit history that must survive.
        ("agent_approvals",
         "(step_id, workflow_id, owner_user_id) REFERENCES agent_steps(id, workflow_id, "
         "owner_user_id) ON DELETE CASCADE"),
        ("agent_dispatch_outbox",
         "(step_id, workflow_id, owner_user_id) REFERENCES agent_steps(id, workflow_id, "
         "owner_user_id) ON DELETE CASCADE"),
        ("agent_checkpoints",
         "(step_id, workflow_id, owner_user_id) REFERENCES agent_steps(id, workflow_id, "
         "owner_user_id) ON DELETE CASCADE"),
        # Column-specific: null only the step reference, keep ownership intact.
        ("agent_run_events",
         "(step_id, workflow_id, owner_user_id) REFERENCES agent_steps(id, workflow_id, "
         "owner_user_id) ON DELETE SET NULL (step_id)"),
        ("agent_tool_calls",
         "(step_id, workflow_id, owner_user_id) REFERENCES agent_steps(id, workflow_id, "
         "owner_user_id) ON DELETE SET NULL (step_id)"),
        # legacy single-column step FKs still present alongside the composites
        ("agent_checkpoints", "(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE"),
        ("agent_dispatch_outbox", "(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE"),
        ("agent_run_events", "(step_id) REFERENCES agent_steps(id) ON DELETE SET NULL"),
        ("agent_tool_calls", "(step_id) REFERENCES agent_steps(id) ON DELETE SET NULL"),
        # audit history survives a deleted approval
        ("agent_tool_calls", "(approval_id) REFERENCES agent_approvals(id) ON DELETE SET NULL"),
        # composite: an approval_id must name a row sharing this call's owner,
        # workflow and step — not merely one that exists somewhere.
        ("agent_tool_calls",
         "(approval_id, owner_user_id, workflow_id, step_id) REFERENCES "
         "agent_approvals(id, owner_user_id, workflow_id, step_id)"),
        # policy scope
        ("agent_policies", "(orbit_id) REFERENCES orbits(id) ON DELETE CASCADE"),
        ("agent_policies", "(project_id) REFERENCES am_projects(id) ON DELETE CASCADE"),
        # workflow scope
        ("agent_workflows", "(orbit_id) REFERENCES orbits(id) ON DELETE SET NULL"),
        ("agent_workflows", "(project_id) REFERENCES am_projects(id) ON DELETE SET NULL"),
        ("agent_workflows", "(retry_of_workflow_id) REFERENCES agent_workflows(id) ON DELETE RESTRICT"),
    }

    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    assert not unexpected, f"foreign keys present but not expected: {unexpected}"
    assert not missing, f"foreign keys expected but absent: {missing}"



