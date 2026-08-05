"""0043 must not strand a WAITING_APPROVAL step behind the actionable approval
it just invalidated.

This runs against its own disposable database rather than the shared per-run
one: proving migration BEHAVIOUR — not just its resulting schema shape —
requires seeding rows before 0043 runs and then running it, and the shared
database only ever applies each migration once, at session start, before any
test has seeded anything.

Three shapes are seeded at revision 0041 (before 0042's unique index and before
0043's fix), the same encoding the real defect left behind:

  * a step WAITING_APPROVAL behind a single PENDING approval — the ordinary
    case, and the one the black hole stranded;
  * a step WAITING_APPROVAL behind two APPROVED rows for the same step — the
    kind of duplicate that could only exist before 0042's unique index, and
    must not produce two requeues or two dispatch intents for one step;
  * a step already SUCCEEDED with a leftover PENDING approval — proving the
    migration invalidates the row without touching a step it has no business
    moving.

Then head is applied, and the proof continues in a session that shares no
Python object with the seeding phase — a fresh engine, a fresh AsyncSession —
so the resumption is provably driven by PostgreSQL alone, not by anything the
test happened to keep in memory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tests.conftest import ADMIN_PW, API_DIR, APP_PW, SUPER_DSN

MIG_DB = f"nur_migtest_{uuid.uuid4().hex[:10]}"
_HOST = SUPER_DSN.split("@", 1)[1].split("/", 1)[0]
ADMIN_DSN = f"postgresql+asyncpg://nur_admin:{ADMIN_PW}@{_HOST}/{MIG_DB}"
APP_DSN = f"postgresql+asyncpg://nur_app:{APP_PW}@{_HOST}/{MIG_DB}"
SUPER_ASYNC_DSN = (
    SUPER_DSN.replace("postgresql://", "postgresql+asyncpg://").rsplit("/", 1)[0] + f"/{MIG_DB}"
)

OWNER = uuid.uuid4()
WORKFLOW = uuid.uuid4()
STEP_PENDING = uuid.uuid4()      # (a) single PENDING, WAITING_APPROVAL
STEP_DUPLICATE = uuid.uuid4()    # (b) two APPROVED, WAITING_APPROVAL
STEP_DONE = uuid.uuid4()         # (c) SUCCEEDED, stale PENDING left behind


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
def migration_db():
    _psql(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)")
    _psql(f"CREATE DATABASE {MIG_DB} OWNER nur_admin")
    _psql("ALTER SCHEMA public OWNER TO nur_admin", db=MIG_DB)
    _psql("GRANT USAGE ON SCHEMA public TO nur_app", db=MIG_DB)
    _psql("GRANT ALL ON SCHEMA public TO nur_email_lookup", db=MIG_DB)
    _psql("GRANT nur_email_lookup TO nur_admin", db=MIG_DB)
    # Before 0042's unique index existed, so the duplicate-APPROVED-rows shape
    # below can actually be seeded — exactly the shape that made the index
    # necessary in the first place.
    _alembic("upgrade", "0041_composite_set_null_column")
    yield
    _psql(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)")


async def _seed_legacy_state() -> None:
    engine = create_async_engine(SUPER_ASYNC_DSN)
    async with engine.begin() as db:
        await db.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:o, :e, 'x')"),
            {"o": OWNER, "e": f"migprobe-{OWNER.hex[:8]}@example.com"},
        )
    await engine.dispose()

    # nur_admin holds BYPASSRLS (the fix under test elsewhere), so no session
    # variable is needed to seed across the owner-scoped tables here.
    admin = create_async_engine(ADMIN_DSN)
    async with admin.begin() as db:
        await db.execute(
            text(
                "INSERT INTO agent_workflows (id, owner_user_id, kind, title, objective, "
                "state, plan_version) VALUES (:w, :o, 'TEST', 't', 'o', 'RUNNING', 1)"
            ),
            {"w": WORKFLOW, "o": OWNER},
        )
        await db.execute(
            text(
                "INSERT INTO agent_policies (owner_user_id, initiative_level, max_risk_class, "
                "permitted_tools, auto_run_tools) VALUES "
                "(:o, 'INTERNAL', 'R2_DURABLE_PRIVATE', '[\"get_timeline\"]'::jsonb, '[]'::jsonb)"
            ),
            {"o": OWNER},
        )
        for step_id, key, state, attempt in (
            (STEP_PENDING, "a", "WAITING_APPROVAL", 1),
            (STEP_DUPLICATE, "b", "WAITING_APPROVAL", 1),
            (STEP_DONE, "c", "SUCCEEDED", 1),
        ):
            await db.execute(
                text(
                    "INSERT INTO agent_steps (id, owner_user_id, workflow_id, ordinal, key, "
                    "state, role, tool_key, tool_version, risk_class, input_refs, depends_on, "
                    "attempt) VALUES (:s, :o, :w, 1, :k, :st, 'operator', 'get_timeline', '1', "
                    "'R0_READ_ONLY', '{}'::jsonb, '[]'::jsonb, :att)"
                ),
                {"s": step_id, "o": OWNER, "w": WORKFLOW, "k": key, "st": state, "att": attempt},
            )

        # (a) the ordinary black-hole shape: one PENDING approval.
        await db.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, plan_version, "
                "call_version) VALUES (:o, :w, :s, 'get_timeline', '1', 'sha256:a', 'r', "
                "'R0_READ_ONLY', 'PENDING', 1, 'plan:tool:version:digest')"
            ),
            {"o": OWNER, "w": WORKFLOW, "s": STEP_PENDING},
        )
        # (b) two APPROVED rows for the same step — only possible pre-0042.
        for suffix in ("x", "y"):
            await db.execute(
                text(
                    "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
                    "tool_version, argument_digest, rationale, risk_class, decision, "
                    "plan_version, call_version) VALUES (:o, :w, :s, 'get_timeline', '1', :d, "
                    "'r', 'R0_READ_ONLY', 'APPROVED', 1, :cv)"
                ),
                {
                    "o": OWNER, "w": WORKFLOW, "s": STEP_DUPLICATE,
                    "d": f"sha256:{suffix}", "cv": f"plan:tool:version:digest-{suffix}",
                },
            )
        # (c) a stale PENDING approval on a step that already finished some
        # other way. Must be invalidated; the step must not move.
        await db.execute(
            text(
                "INSERT INTO agent_approvals (owner_user_id, workflow_id, step_id, tool_key, "
                "tool_version, argument_digest, rationale, risk_class, decision, plan_version, "
                "call_version) VALUES (:o, :w, :s, 'get_timeline', '1', 'sha256:c', 'r', "
                "'R0_READ_ONLY', 'PENDING', 1, 'plan:tool:version:digest-c')"
            ),
            {"o": OWNER, "w": WORKFLOW, "s": STEP_DONE},
        )
    await admin.dispose()


@pytest.mark.asyncio
async def test_0043_reconciles_stranded_waiting_approval_steps(migration_db):
    await _seed_legacy_state()
    _alembic("upgrade", "head")

    super_engine = create_async_engine(SUPER_ASYNC_DSN)
    async with super_engine.connect() as db:
        approvals = (
            await db.execute(
                text(
                    "SELECT step_id, decision, invalidated_from, invalidated_at, "
                    "invalidation_reason FROM agent_approvals ORDER BY step_id, id"
                )
            )
        ).mappings().all()
        steps = {
            row["id"]: row
            for row in (
                await db.execute(
                    text("SELECT id, state FROM agent_steps")
                )
            ).mappings().all()
        }
        outbox = (
            await db.execute(
                text("SELECT step_id, state, dispatch_key FROM agent_dispatch_outbox")
            )
        ).mappings().all()
    await super_engine.dispose()

    by_step: dict[uuid.UUID, list] = {}
    for row in approvals:
        by_step.setdefault(row["step_id"], []).append(row)

    # (a) single PENDING invalidated with provenance; step requeued; one intent.
    (a_row,) = by_step[STEP_PENDING]
    assert a_row["decision"] == "INVALIDATED"
    assert a_row["invalidated_from"] == "PENDING"
    assert a_row["invalidated_at"] is not None
    assert a_row["invalidation_reason"] == "pre-canonical binding"
    assert steps[STEP_PENDING]["state"] == "QUEUED"
    a_outbox = [r for r in outbox if r["step_id"] == STEP_PENDING]
    assert len(a_outbox) == 1, a_outbox
    assert a_outbox[0]["state"] == "RETRYABLE"
    assert "reconcile:0043" in a_outbox[0]["dispatch_key"]

    # (b) both duplicates invalidated, provenance per-row; exactly one requeue,
    # one intent — not two, despite two invalidated rows for the same step.
    b_rows = by_step[STEP_DUPLICATE]
    assert len(b_rows) == 2
    assert {r["decision"] for r in b_rows} == {"INVALIDATED"}
    assert {r["invalidated_from"] for r in b_rows} == {"APPROVED"}
    assert steps[STEP_DUPLICATE]["state"] == "QUEUED"
    b_outbox = [r for r in outbox if r["step_id"] == STEP_DUPLICATE]
    assert len(b_outbox) == 1, b_outbox

    # (c) invalidated, but a step with no business moving does not move, and
    # gets no dispatch intent.
    (c_row,) = by_step[STEP_DONE]
    assert c_row["decision"] == "INVALIDATED"
    assert c_row["invalidated_from"] == "PENDING"
    assert steps[STEP_DONE]["state"] == "SUCCEEDED"
    assert not [r for r in outbox if r["step_id"] == STEP_DONE]

    # ── Restart, from PostgreSQL alone. Fresh engine, fresh session: nothing
    #    here is the seeding phase's Python object. ──
    from app.agentic import handlers
    from app.agentic.observability import new_trace
    from app.agentic.runtime import run_step

    handlers.bind_read_only_handlers()

    from sqlalchemy.ext.asyncio import async_sessionmaker

    app_engine = create_async_engine(APP_DSN)
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as fresh:
        await fresh.execute(
            text("SELECT set_config('app.current_user_id', :o, false)"), {"o": str(OWNER)}
        )
        outcome = await run_step(
            fresh, owner_user_id=OWNER, step_id=STEP_PENDING,
            trace=new_trace(), worker="restart-w1",
        )
        await fresh.commit()
    await app_engine.dispose()

    # Paused again, not executed without consent: the invalidated row cannot
    # authorise anything, so the gate asks fresh rather than running the tool.
    assert outcome["executed"] is False, outcome
    assert outcome["step_state"] == "WAITING_APPROVAL", outcome

    super_engine = create_async_engine(SUPER_ASYNC_DSN)
    async with super_engine.connect() as db:
        fresh_rows = (
            await db.execute(
                text(
                    "SELECT decision, call_version, plan_version FROM agent_approvals "
                    "WHERE step_id = :s AND decision = 'PENDING'"
                ),
                {"s": STEP_PENDING},
            )
        ).mappings().all()
        step_row = (
            await db.execute(
                text("SELECT state FROM agent_steps WHERE id = :s"), {"s": STEP_PENDING}
            )
        ).mappings().one()
        tool_calls = (
            await db.execute(
                text("SELECT count(*) FROM agent_tool_calls WHERE step_id = :s"),
                {"s": STEP_PENDING},
            )
        ).scalar()
    await super_engine.dispose()

    # Exactly one fresh, canonical PENDING card — not zero, not the old one.
    assert len(fresh_rows) == 1, fresh_rows
    assert fresh_rows[0]["call_version"].startswith("cv:")
    assert fresh_rows[0]["call_version"] != "plan:tool:version:digest"
    assert fresh_rows[0]["plan_version"] == 1
    assert step_row["state"] == "WAITING_APPROVAL"
    # No tool call recorded: the handler never ran without a held approval.
    assert tool_calls == 0
